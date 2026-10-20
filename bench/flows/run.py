import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'analyzer'))

from cortex_graph.analyze import analyze, is_test

CLONES = Path.home() / '.cache' / 'cortex-bench' / 'flows'
FLOW_EDGES = {'http', 'rpc', 'handles', 'event', 'data', 'env', 'depends'}
VIA = ('endpoint', 'topic', 'variable')
OUTER = ('module', 'doc', 'package', 'dependency')
KINDS = ('route', 'http', 'rpc', 'event', 'data', 'env', 'service')
ENV_NAME = re.compile(r'\benv\s+([A-Za-z_]\w*)')
SAMPLE = 10
LOOKAHEAD = 3
LABEL_EDGES = {'route': {'handles'}, 'http': {'http', 'handles'}, 'rpc': {'rpc', 'handles'}, 'event': {'event'},
               'data': {'data'}, 'env': {'env'}, 'service': {'depends'}}
SPLITS = {'': 'ajuste ronda 1', 'control': 'ajuste ronda 2', 'control2': 'ajuste ronda 3', 'control3': 'ajuste ronda 4',
          'control4': 'ajuste ronda 5', 'control5': 'ajuste ronda 6', 'control6': 'control 6 (ciego)'}
BLIND = {'control6'}  # examen ciego pendiente: nunca se clona, analiza ni se leen sus etiquetas salvo que se pida con --only
CODE_EXT = ('.py', '.js', '.ts', '.tsx', '.jsx', '.mjs', '.cjs', '.mts', '.vue', '.svelte', '.go', '.java', '.kt', '.kts', '.cs', '.rb',
            '.php', '.rs', '.ex', '.exs', '.dart', '.swift', '.scala')


def checkout(repo, clones):
    dest = clones / repo['name']
    git = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'advice.detachedHead=false']
    if not (dest / '.git').is_dir():
        subprocess.run(git + ['clone', '-q', '--filter=blob:none', repo['url'], str(dest)], check=True, stdin=subprocess.DEVNULL)
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=dest, capture_output=True, text=True).stdout.strip()
    if head != repo['commit']:
        subprocess.run(git + ['checkout', '-q', '--force', repo['commit']], cwd=dest, check=True, stdin=subprocess.DEVNULL)
    return dest


def compact(out):
    keys = {n['id']: n['key'] for n in out['nodes']}
    nodes = {n['key']: {k: n[k] for k in ('kind', 'name', 'file', 'line', 'end', 'table', 'route') if k in n} for n in out['nodes']}
    edges = sorted({(keys[e['a']], keys[e['b']], e['kind']) for e in out['edges'] if e['kind'] in FLOW_EDGES})
    return {'nodes': nodes, 'edges': edges}


def load_graph(repo, src, cache, reuse):
    path = cache / f"{repo['name']}.json"
    if reuse and path.is_file():
        data = json.loads(path.read_text())
        data['edges'] = [tuple(e) for e in data['edges']]
        return data, 0.0
    t0 = time.time()
    data = compact(analyze(src, project=repo['name'], git=False))
    cache.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False))
    return data, time.time() - t0


class View:
    def __init__(self, data, root=None):
        self.root, self.lines = root, {}
        self.nodes = data['nodes']
        self.adj = defaultdict(set)
        self.flow = []
        for a, b, k in data['edges']:
            if a not in self.nodes or b not in self.nodes:
                continue
            if k == 'depends' and any(self.nodes[x]['kind'] in ('package', 'dependency') for x in (a, b)):
                continue
            self.adj[a].add((b, k))
            self.adj[b].add((a, k))
            self.flow.append((a, b, k))
        self.by_file = defaultdict(list)
        for nid, m in self.nodes.items():
            if m.get('file'):
                self.by_file[m['file']].append(nid)

    def module(self, rel):
        return next((n for n in (f'm:{rel}', f'd:{rel}') if n in self.nodes), None)

    def covering(self, rel, line):
        out, ahead = [], []
        for nid in self.by_file.get(rel, []):
            m = self.nodes[nid]
            if m['kind'] in VIA + OUTER or m.get('line') is None:
                continue
            start, end = m['line'], m.get('end') or m['line']
            if start <= line <= end:
                out.append((start, -end, nid))
            elif 0 < start - line <= LOOKAHEAD:
                ahead.append((start, nid))
        found = [n for _, _, n in sorted(out, reverse=True)]
        if not self.annotation(rel, line):
            return found
        # línea de anotación/decorador: el nodo decorado (el que empieza tras el bloque de anotaciones), aunque un nodo exterior
        # (la clase) cubra la línea; el analizador puede situar la declaración en la anotación o en su palabra clave
        decl = self.decorated_line(rel, line)
        own = [n for n in self.by_file.get(rel, []) if self.nodes[n]['kind'] not in VIA + OUTER
               and decl is not None and self.nodes[n].get('line') in (decl, decl - 1) and (self.nodes[n].get('line') or 0) > line]
        inner = [n for n in found if self.nodes[n]['line'] == line]
        if inner or own:
            return (inner or own) + [n for n in found if n not in inner]
        # lo decorado no es un nodo (un campo): el nodo que cubre la línea o, si no hay, el siguiente
        return found or [n for _, n in sorted(ahead)[:1]]

    def decorated_line(self, rel, line):
        lines, depth = self.lines.get(rel) or [], 0
        for i in range(line - 1, min(len(lines), line + 80)):
            text = lines[i].strip()
            if depth == 0 and i >= line and text and not text.startswith(('@', '[', '#[', '//', '/*', '*')):
                return i + 1
            depth = max(0, depth + text.count('(') + text.count('{') + text.count('[') - text.count(')') - text.count('}') - text.count(']'))
        return None

    def annotation(self, rel, line):
        if self.root is None:
            return False
        if rel not in self.lines:
            try:
                self.lines[rel] = (self.root / rel).read_text(errors='replace').split('\n')
            except OSError:
                self.lines[rel] = []
        text = self.lines[rel][line - 1].strip() if 0 < line <= len(self.lines[rel]) else ''
        return text.startswith(('@', '[', '#['))

    def via_at(self, rel, line, span=2):
        return [n for n in self.by_file.get(rel, []) if self.nodes[n]['kind'] in VIA
                and abs((self.nodes[n].get('line') or 0) - line) <= span]

    def is_via(self, nid):
        m = self.nodes[nid]
        return m['kind'] in VIA or bool(m.get('table'))

    def paths(self, srcs, dsts, kind=None, detail=None):
        dsts, found, allowed = set(dsts), [], LABEL_EDGES.get(kind)
        for s in srcs:
            if kind == 'route' and s in dsts and detail:
                # ruta declarada sobre el propio handler (anotación de verbo sin ruta y ruta en la clase): el endpoint del handler
                # debe tener el mismo verbo y una ruta que sea sufijo de la etiquetada
                own = sorted(n1 for n1, k1 in self.adj.get(s, ()) if k1 == 'handles' and self.nodes[n1]['kind'] == 'endpoint'
                             and same_route(self.nodes[n1]['name'], detail))
                if own:
                    found.append(((own[0], s, 'handles'),))
                    continue
            if kind == 'event' and s in dsts:
                # registro sobre el propio handler (decorador/anotación justo encima): origen y destino son el mismo nodo, que
                # debe estar suscrito a un topic
                own = sorted((n1, k1) for n1, k1 in self.adj.get(s, ()) if k1 in allowed and self.nodes[n1]['kind'] == 'topic')
                if own:
                    found.append(((s, own[0][0], own[0][1]),))
                    continue
            for n1, k1 in self.adj.get(s, ()):
                if allowed and k1 not in allowed:
                    continue
                if n1 in dsts and n1 != s:
                    found.append(((s, n1, k1),))
                if n1 == s or not self.is_via(n1):
                    continue
                for n2, k2 in self.adj.get(n1, ()):
                    if allowed and k2 not in allowed:
                        continue
                    if n2 in dsts and n2 not in (s, n1):
                        found.append(((s, n1, k1), (n1, n2, k2)))
        return found


def route_segments(path):
    segs = [x for x in re.sub(r'[?#].*$', '', path).strip('/').split('/') if x]
    return [':' if x.startswith((':', '{', '<')) else x for x in segs]


def same_route(name, detail):
    a, b = name.split(' ', 1) if ' ' in name else ('', name), detail.split(' ', 1) if ' ' in (detail or '') else ('', detail or '')
    if a[0] != b[0] or not a[0]:
        return False
    ea, eb = route_segments(a[1]), route_segments(b[1])
    return bool(ea) and len(ea) <= len(eb) and eb[len(eb) - len(ea):] == ea


def symbol_tail(sym):
    return re.split(r'[.#:]', sym or '')[-1]


def from_cands(v, lab):
    f = lab['from']
    rel, line = f['file'], f.get('line') or 1
    inner = v.covering(rel, line)
    cands = [inner[0] if inner else v.module(rel)]
    if lab['kind'] in ('route', 'rpc', 'event', 'service', 'env'):
        cands += v.via_at(rel, line)
    if lab['kind'] in ('data', 'service') and inner:
        cands += inner[1:]
    return [c for c in dict.fromkeys(cands) if c]


def to_cands(v, lab):
    t = lab['to']
    rel, line = t['file'], t.get('line') or 1
    inner = v.covering(rel, line)
    cands = [inner[0] if inner else v.module(rel)]
    tail = symbol_tail(t.get('symbol'))
    if tail:
        cands += [n for n in v.by_file.get(rel, []) if v.nodes[n]['kind'] not in VIA + OUTER
                  and v.nodes[n]['name'].rsplit('.', 1)[-1] == tail and abs((v.nodes[n].get('line') or 0) - line) <= 10]
    if lab['kind'] == 'data':
        cands += inner[1:]
        cands += [n for n in v.by_file.get(rel, []) if v.nodes[n].get('table') and v.nodes[n].get('line') == line]
    if lab['kind'] == 'env':
        cands.append(v.module(rel))
        m = ENV_NAME.search(lab.get('detail') or '')
        if m and v.nodes.get(f'v:{m.group(1)}', {}).get('file') == rel:
            cands.append(f'v:{m.group(1)}')
    if lab['kind'] == 'service':
        cands += inner[1:] + v.via_at(rel, line)
        if line == 1:  # destino a nivel de fichero (Dockerfile, script de entrada): el módulo, aunque la línea 1 abra un bloque
            cands.append(v.module(rel))
    return [c for c in dict.fromkeys(cands) if c]


def in_scope(rel, scope):
    for s in scope:
        rx = re.escape(s.rstrip('/')).replace(r'\*', '[^/]*')
        if re.match(rx + ('(?:/|$)' if s.endswith('/') else '$'), rel):
            return True
    return not scope


def reason(v, lab, srcs, dsts):
    kind = lab['kind']
    out = lambda ns: [e for n in ns for e in v.adj.get(n, ())]
    if kind == 'route':
        eps = v.via_at(lab['from']['file'], lab['from'].get('line') or 1)
        if not eps:
            return 'ruta no detectada'
        if not any(k == 'handles' for e in eps for _, k in v.adj.get(e, ())):
            return 'endpoint sin handler'
        return 'handler distinto'
    if kind == 'http':
        hits = [n for n, k in out(srcs[:1]) if k == 'http']
        if not hits:
            return 'llamada no detectada'
        if not any(k == 'handles' and n in dsts for h in hits for n, k in v.adj.get(h, ())):
            return 'otro endpoint o endpoint sin handler'
    a, b = bool(out(srcs)), bool(out(dsts))
    if not a and not b:
        return 'origen y destino sin aristas de flujo'
    if not a:
        return 'origen sin aristas de flujo'
    if not b:
        return 'destino sin aristas de flujo'
    return 'conectados por separado, sin camino'


def edge_kind(v, a, b, k):
    if k == 'handles':
        return 'rpc' if v.nodes[a]['name'].startswith('RPC ') else 'route'
    if k == 'data':
        return 'data'
    if k == 'depends':
        return 'service'
    if k == 'env':
        return 'env' if (v.nodes[a].get('file') or '').endswith(CODE_EXT) else None
    return k if k in KINDS else None



def where(v, nid):
    m = v.nodes.get(nid) or {}
    return f"{m.get('file')}:{m.get('line')} {m.get('name')}"


def sample_key(name, e):
    return hashlib.sha1('|'.join((name,) + tuple(e)).encode()).hexdigest()


def evaluate(repo, data, review, root=None):
    v = View(data, root)
    kinds, scope = repo.get('kinds') or KINDS, repo.get('scope') or ()
    labels = [json.loads(x) for x in (HERE / 'labels' / f"{repo['name']}.jsonl").read_text().splitlines() if x.strip()]
    per, fns, used = defaultdict(Counter), defaultdict(list), set()
    for lab in labels:
        kind = lab['kind']
        if kind not in kinds or not (in_scope(lab['from']['file'], scope) or in_scope(lab['to']['file'], scope)):
            continue
        srcs, dsts = from_cands(v, lab), to_cands(v, lab)
        found = v.paths(srcs, dsts, kind, lab.get('detail'))
        per[kind]['total'] += 1
        if found:
            per[kind]['found'] += 1
            for p in found:
                used.update(p)
        else:
            f, t = lab['from'], lab['to']
            fns[f"{kind} · {reason(v, lab, srcs, dsts)}"].append(
                f"{f['file']}:{f.get('line')} → {t['file']}:{t.get('line')} ({lab.get('detail') or ''})")
    flows, unmatched = Counter(), []
    for a, b, k in v.flow:
        kind = edge_kind(v, a, b, k)
        rel = v.nodes[a].get('file') or ''
        if kind not in kinds or not in_scope(rel, scope) or is_test(rel):
            continue
        flows[kind] += 1
        if (a, b, k) in used or (b, a, k) in used:
            flows[kind + ':ok'] += 1
        else:
            unmatched.append((kind, a, b, k))
    unmatched.sort(key=lambda e: sample_key(repo['name'], e))
    sample = []
    for kind, a, b, k in unmatched[:SAMPLE]:
        r = review.get((repo['name'], a, b, k)) or {}
        sample.append({'kind': kind, 'a': a, 'b': b, 'edge': k, 'from': where(v, a), 'to': where(v, b),
                       'verdict': r.get('verdict'), 'note': r.get('note', '')})
    total = sum(c['total'] for c in per.values())
    found = sum(c['found'] for c in per.values())
    return {
        'recall': {k: {'found': per[k]['found'], 'total': per[k]['total']} for k in KINDS if per[k]['total']},
        'found': found, 'total': total,
        'fn': {k: {'n': len(x), 'examples': x[:4]} for k, x in sorted(fns.items(), key=lambda kv: (-len(kv[1]), kv[0]))},
        'flows': sum(flows[k] for k in KINDS), 'matched': sum(flows[k + ':ok'] for k in KINDS),
        'flows_by_kind': {k: [flows[k + ':ok'], flows[k]] for k in KINDS if flows[k]},
        'unmatched': len(unmatched), 'sample': sample,
    }


def pct(a, b):
    return f'{100 * a / b:.1f} %' if b else '—'


def precision(results):
    flows = sum(r['flows'] for r in results.values() if 'flows' in r)
    matched = sum(r['matched'] for r in results.values() if 'matched' in r)
    reviewed = [s for r in results.values() for s in r.get('sample', []) if s['verdict']]
    fp = sum(1 for s in reviewed if s['verdict'] == 'fp')
    unmatched = flows - matched
    rate = fp / len(reviewed) if reviewed else None
    est = (matched + unmatched * (1 - rate)) / flows if flows and rate is not None else None
    worst = min(1.0, (fp + 3) / len(reviewed)) if reviewed else None
    safe = (matched + unmatched * (1 - worst)) / flows if flows and worst is not None else None
    return {'flows': flows, 'matched': matched, 'unmatched': unmatched, 'reviewed': len(reviewed), 'fp': fp,
            'fp_rate_unmatched': rate, 'estimate': est, 'conservative': safe, 'lower_bound': matched / flows if flows else None}


def split_name(r):
    return SPLITS.get(r.get('split') or '', r.get('split') or '')


def recall_cells(group):
    tot = defaultdict(Counter)
    for r in group.values():
        for k, c in r['recall'].items():
            tot[k]['found'] += c['found']
            tot[k]['total'] += c['total']
    cells = [f"{pct(tot[k]['found'], tot[k]['total'])} ({tot[k]['found']}/{tot[k]['total']})" if tot[k]['total'] else '' for k in KINDS]
    found, total = sum(t['found'] for t in tot.values()), sum(t['total'] for t in tot.values())
    return cells, found, total


def round_table(ok, splits, path, title, intro, tuned_split, tuned_name):
    if not path.is_file():
        return []
    data = json.loads(path.read_text())
    old, secs = data.get('results', {}), data.get('seconds', {})
    lines = ['', f'## {title}', '', intro, '', '| repo | conjunto | antes | después | s antes | s después |', '|---|---|---|---|---|---|']
    after = lambda n, r: (secs.get(n) or {}).get('after', r.get('seconds', ''))
    before_s = lambda n, o: (secs.get(n) or {}).get('before', o.get('seconds', ''))
    for name, r in ok.items():
        o = old.get(name)
        if o and 'total' in o:
            lines.append(f"| {name} | {split_name(r)} | {pct(o['found'], o['total'])} ({o['found']}/{o['total']}) | "
                         f"{pct(r['found'], r['total'])} ({r['found']}/{r['total']}) | {before_s(name, o)} | {after(name, r)} |")
    for split, group in splits.items():
        before = [(n, old[n]) for n in group if n in old and 'total' in old[n]]
        if before:
            bf, bt = sum(o['found'] for _, o in before), sum(o['total'] for _, o in before)
            af, at = sum(r['found'] for r in group.values()), sum(r['total'] for r in group.values())
            bs = sum(float(before_s(n, o) or 0) for n, o in before)
            ss = sum(float(after(n, group[n]) or 0) for n, _ in before)
            lines.append(f'| **{split}** | | **{pct(bf, bt)}** ({bf}/{bt}) | **{pct(af, at)}** ({af}/{at}) | {bs:.1f} | {ss:.1f} |')
    tuned = {n: r for n, r in ok.items() if r.get('split') == tuned_split and n in old}
    if tuned:
        lines += ['', f'{tuned_name} por tipo (antes → después):', '', '| repo | ' + ' | '.join(KINDS) + ' |', '|---|' + '---|' * len(KINDS)]
        for name, r in tuned.items():
            o = old[name].get('recall', {})
            cells = [f"{o[k]['found'] if k in o else 0}/{c['total']} → {c['found']}/{c['total']}" if (c := r['recall'].get(k)) else ''
                     for k in KINDS]
            lines.append(f'| {name} | ' + ' | '.join(cells) + ' |')
        cells = []
        for k in KINDS:
            bt = sum(old[n].get('recall', {}).get(k, {}).get('found', 0) for n in tuned)
            tot = sum(r['recall'].get(k, {}).get('total', 0) for r in tuned.values())
            af = sum(r['recall'].get(k, {}).get('found', 0) for r in tuned.values())
            cells.append(f'**{pct(bt, tot)} → {pct(af, tot)}**' if tot else '')
        lines.append('| **total** | ' + ' | '.join(cells) + ' |')
    return lines


def markdown(results, meta):
    ok = {k: r for k, r in results.items() if 'recall' in r}
    lines = [
        '# Córtex · benchmark de flujos entre componentes',
        '',
        f"Generado: {meta['date']} · Córtex analizado con `analyze()` (sin git) · verdad de referencia: "
        '`bench/flows/labels/*.jsonl` (etiquetado manual independiente).',
        '',
        'Un flujo cuenta como encontrado si Córtex une el nodo de origen con el de destino por aristas de flujo '
        '(`http`, `rpc`, `handles`, `event`, `data`, `env`, `depends`, según el tipo de etiqueta), directamente o a través de un '
        'nodo intermedio endpoint/topic/variable/tabla (máx. 2 saltos). No cuentan `contains`, `import`, `call` ni `cochange`.',
        '',
        '## Exhaustividad (recall) por repo y tipo',
        '',
        'Conjuntos: «ajuste ronda 1» = los 11 repos usados para afinar en la primera ronda; «ajuste ronda 2» = los 6 repos del '
        'antiguo control (`split = "control"`), usados para afinar en la segunda ronda; «ajuste ronda 3» = los 6 repos del examen '
        'final de la ronda 2 (`split = "control2"`), usados para afinar en la tercera; «ajuste ronda 4» = los 7 repos del examen '
        'ciego de la ronda 3 (`split = "control3"`), usados para afinar en la cuarta; «ajuste ronda 5» = los 7 repos del examen ciego de '
        'la ronda 4 (`split = "control4"`), usados para afinar en la quinta; «ajuste ronda 6» = los 7 repos del examen ciego de la '
        'ronda 5 (`split = "control5"`), usados para afinar en la sexta. Los conjuntos de `repos.toml` sin entrada en `SPLITS` o '
        'marcados en `BLIND` (exámenes ciegos pendientes, como `control6`) no se analizan salvo con `--only`.',
        '',
        '| repo | conjunto | ' + ' | '.join(KINDS) + ' | total |',
        '|---|---|' + '---|' * (len(KINDS) + 1),
    ]
    for name, r in ok.items():
        cells = [f"{pct(c['found'], c['total'])} ({c['found']}/{c['total']})" if (c := r['recall'].get(k)) else '' for k in KINDS]
        lines.append(f'| {name} | {split_name(r)} | ' + ' | '.join(cells) + f" | **{pct(r['found'], r['total'])}** ({r['found']}/{r['total']}) |")
    cells, g_found, g_total = recall_cells(ok)
    lines.append('| **global** | | ' + ' | '.join(f'**{c}**' if c else '' for c in cells) + f' | **{pct(g_found, g_total)}** ({g_found}/{g_total}) |')
    splits = defaultdict(dict)
    for name, r in ok.items():
        splits[split_name(r)][name] = r
    lines += ['', '### Resumen por conjunto', '',
              '| conjunto | repos | ' + ' | '.join(KINDS) + ' | total | media por repo | peor repo |',
              '|---|---|' + '---|' * (len(KINDS) + 3)]
    for split in sorted(splits, key=lambda s: list(SPLITS.values()).index(s) if s in SPLITS.values() else 99):
        group = splits[split]
        cells, found, total = recall_cells(group)
        rates = {n: r['found'] / r['total'] for n, r in group.items() if r['total']}
        worst = min(rates, key=rates.get) if rates else ''
        mean = sum(rates.values()) / len(rates) if rates else 0
        lines.append(f'| {split} | {len(group)} | ' + ' | '.join(cells) + f' | **{pct(found, total)}** ({found}/{total}) | '
                     f'{100 * mean:.1f} % | {worst} ({100 * rates.get(worst, 0):.1f} %) |')
    p = precision(ok)
    lines += [
        '',
        '## Precisión estimada',
        '',
        'Unidades: aristas de flujo de Córtex dentro del `scope`/`kinds` etiquetado de cada repo (lecturas de env desde código, '
        'no las definiciones). Una arista está *emparejada* si forma parte del camino de alguna etiqueta encontrada. De las no '
        f'emparejadas se toma una muestra determinista (hasta {SAMPLE} por repo, orden por hash) y se revisa leyendo el código: '
        '`fp` = conexión falsa, `ok` = flujo real que el etiquetado no recoge (omisión). Veredictos en `bench/flows/review.jsonl`.',
        '',
        f"- Aristas de flujo en alcance: {p['flows']} · emparejadas: {p['matched']} · sin emparejar: {p['unmatched']}",
        f"- Muestra revisada: {p['reviewed']} · falsos positivos: {p['fp']}"
        + (f" ({100 * p['fp_rate_unmatched']:.0f} % de las no emparejadas)" if p['fp_rate_unmatched'] is not None else ''),
        f"- Cota inferior (solo emparejadas): {pct(p['matched'], p['flows'])}"
        + (f" · **precisión estimada: {100 * p['estimate']:.1f} %**" if p['estimate'] is not None else '')
        + (f" · conservadora (tasa de FP de la muestra + 3/n, regla del tres al 95 %): {100 * p['conservative']:.1f} %"
           if p.get('conservative') is not None else ''),
        '',
        '| conjunto | aristas | emparejadas | muestra revisada | fp | precisión estimada | conservadora |',
        '|---|---|---|---|---|---|---|',
    ]
    for split, group in splits.items():
        q = precision(group)
        est = f"{100 * q['estimate']:.1f} %" if q['estimate'] is not None else '—'
        safe = f"{100 * q['conservative']:.1f} %" if q['conservative'] is not None else '—'
        lines.append(f"| {split} | {q['flows']} | {pct(q['matched'], q['flows'])} | {q['reviewed']} | {q['fp']} | {est} | {safe} |")
    lines += ['', '| repo | conjunto | aristas | emparejadas | por tipo (emparejadas/total) |', '|---|---|---|---|---|']
    for name, r in ok.items():
        kinds = ' · '.join(f'{k} {a}/{b}' for k, (a, b) in r['flows_by_kind'].items())
        lines.append(f"| {name} | {split_name(r)} | {r['flows']} | {pct(r['matched'], r['flows'])} | {kinds} |")
    base = HERE / 'results' / 'baseline.json'
    if base.is_file():
        old = json.loads(base.read_text()).get('results', {})
        lines += ['', '## Línea base (antes de los cambios en Córtex)', '',
                  'Primera ejecución del arnés sobre el Córtex de partida (solo los repos de la ronda 1). Aquella versión del arnés '
                  'aceptaba además caminos por claves foráneas entre tablas (`ref`) y cualquier tipo de arista para cualquier etiqueta, '
                  'así que la base está, si acaso, algo inflada.', '', '| repo | línea base | final |', '|---|---|---|']
        for name, r in ok.items():
            if name in old:
                o = old[name]
                lines.append(f"| {name} | {pct(o.get('found', 0), o.get('total', 0))} | {pct(r['found'], r['total'])} |")
        of = sum(o.get('found', 0) for o in old.values())
        ot = sum(o.get('total', 0) for o in old.values())
        nf = sum(r['found'] for n, r in ok.items() if n in old)
        nt = sum(r['total'] for n, r in ok.items() if n in old)
        lines.append(f"| **global** | {pct(of, ot)} | {pct(nf, nt)} |")
    base2 = HERE / 'results' / 'baseline_r2.json'
    if base2.is_file():
        old = json.loads(base2.read_text()).get('results', {})
        lines += ['', '## Ronda 2 (antes → después)', '',
                  'Ejecución del arnés al empezar la ronda 2 (Córtex al final de la ronda 1, mismas etiquetas salvo las correcciones '
                  'documentadas en el README) frente a la actual.', '',
                  '| repo | conjunto | antes | después |', '|---|---|---|---|']
        for name, r in ok.items():
            o = old.get(name)
            if o and 'total' in o:
                lines.append(f"| {name} | {split_name(r)} | {pct(o['found'], o['total'])} ({o['found']}/{o['total']}) | "
                             f"{pct(r['found'], r['total'])} ({r['found']}/{r['total']}) |")
        for split, group in splits.items():
            before = [old[n] for n in group if n in old and 'total' in old[n]]
            if before:
                bf, bt = sum(o['found'] for o in before), sum(o['total'] for o in before)
                af, at = sum(r['found'] for r in group.values()), sum(r['total'] for r in group.values())
                lines.append(f'| **{split}** | | **{pct(bf, bt)}** ({bf}/{bt}) | **{pct(af, at)}** ({af}/{at}) |')
    lines += round_table(ok, splits, HERE / 'results' / 'baseline_r3.json', 'Ronda 3 (antes → después)',
                         'Ejecución del arnés al empezar la ronda 3 (Córtex al final de la ronda 2, mismas etiquetas) frente a la actual, con el '
                         'tiempo de `analyze()` de cada repo en segundos (medido intercalando el `bridges.py` de partida y el actual dos veces '
                         'en la misma máquina; se guarda el mínimo de cada uno).', 'control2', 'Ajuste ronda 3')
    lines += round_table(ok, splits, HERE / 'results' / 'baseline_r4.json', 'Ronda 4 (antes → después)',
                         'Ejecución del arnés al empezar la ronda 4 (Córtex al final de la ronda 3, mismas etiquetas) frente a la actual. Los '
                         'segundos de «antes» y «después» son el tiempo de `analyze()` medido intercalando el `bridges.py` de partida y el '
                         'actual dos veces en la misma máquina (mínimo de cada uno); ver el README.', 'control3', 'Ajuste ronda 4')
    lines += round_table(ok, splits, HERE / 'results' / 'baseline_r5.json', 'Ronda 5 (antes → después)',
                         'Ejecución del arnés al empezar la ronda 5 (Córtex al final de la ronda 4) frente a la actual, con las mismas reglas de '
                         'puntuación y etiquetas que la ejecución final (ver «Ronda 5» en el README: dos correcciones de etiquetas y dos ajustes '
                         'de puntuación). Los segundos son el tiempo de `analyze()` medido intercalando el `bridges.py`/`structural.py` de '
                         'partida y el actual en la misma máquina (mínimo de dos pasadas) en los repos medidos; en el resto, el de la ejecución.',
                         'control4', 'Ajuste ronda 5')
    lines += ['', '### Muestra de aristas sin etiqueta', '', '| repo | tipo | origen | destino | veredicto | nota |', '|---|---|---|---|---|---|']
    for name, r in ok.items():
        for s in r['sample']:
            lines.append(f"| {name} | {s['kind']} | {s['from']} | {s['to']} | {s['verdict'] or 'pendiente'} | {s['note']} |")
    for name, r in results.items():
        lines += ['', f'## {name}', '']
        if 'error' in r:
            lines.append(f"Error: {r['error']}")
            continue
        lines += [f"Encontrados {r['found']}/{r['total']} · análisis {r['seconds']} s", '',
                  '| n | patrón de falso negativo | ejemplos |', '|---|---|---|']
        for pat, x in list(r['fn'].items())[:8]:
            lines.append(f"| {x['n']} | {pat} | " + '<br>'.join(e.replace('|', '¦') for e in x['examples']) + ' |')
    return '\n'.join(lines) + '\n'


def load_review(path):
    out = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                out[(r['repo'], r['a'], r['b'], r['edge'])] = r
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description='Benchmark de flujos entre componentes de Córtex')
    p.add_argument('--repos', default=str(HERE / 'repos.toml'))
    p.add_argument('--only', action='append', default=[])
    p.add_argument('--clones', default=str(CLONES))
    p.add_argument('--cache', default=None, help='carpeta para los grafos analizados (por defecto junto a los clones)')
    p.add_argument('--reuse', action='store_true', help='reutiliza los grafos ya analizados')
    p.add_argument('--out', default=str(HERE / 'results'))
    args = p.parse_args(argv)
    clones = Path(args.clones)
    cache = Path(args.cache) if args.cache else clones.resolve().parent / 'work' / 'flow-graphs'
    outdir = Path(args.out)
    review = load_review(HERE / 'review.jsonl')
    repos = tomllib.loads(Path(args.repos).read_text())['repo']
    prev_path = outdir / 'results.json'
    prev = json.loads(prev_path.read_text()).get('results', {}) if prev_path.is_file() else {}
    results = {}
    for repo in repos:
        if args.only and repo['name'] not in args.only:
            continue
        if not args.only and ((repo.get('split') or '') not in SPLITS or (repo.get('split') or '') in BLIND):
            continue  # examen ciego pendiente: ni se clona ni se analiza ni se leen sus etiquetas
        try:
            src = checkout(repo, clones)
            data, secs = load_graph(repo, src, cache, args.reuse)
            r = evaluate(repo, data, review, src)
            r['seconds'] = round(secs, 1) if secs or not args.reuse else prev.get(repo['name'], {}).get('seconds', 0.0)
        except Exception as exc:
            r = {'error': f'{type(exc).__name__}: {exc}'}
        r.update({'stack': repo.get('stack'), 'commit': repo['commit'], 'split': repo.get('split') or ''})
        results[repo['name']] = r
        print(f"{repo['name']}: " + (r.get('error') or f"recall {pct(r['found'], r['total'])} · "
                                    + ' '.join(f"{k} {c['found']}/{c['total']}" for k, c in r['recall'].items())
                                    + f" · emparejadas {r['matched']}/{r['flows']}"))
    outdir.mkdir(parents=True, exist_ok=True)
    previous = outdir / 'results.json'
    if args.only and previous.is_file():
        order = [r['name'] for r in repos]
        merged = {**json.loads(previous.read_text()).get('results', {}), **results}
        results = {k: merged[k] for k in order if k in merged}
    results = {k: r for k, r in results.items() if (r.get('split') or '') in SPLITS and (r.get('split') or '') not in BLIND or k in args.only}
    meta = {'date': time.strftime('%Y-%m-%d'), 'precision': precision({k: r for k, r in results.items() if 'recall' in r})}
    (outdir / 'results.json').write_text(json.dumps({'meta': meta, 'results': results}, ensure_ascii=False, indent=1, sort_keys=True) + '\n')
    (outdir / 'RESULTS.md').write_text(markdown(results, meta))
    return 0


if __name__ == '__main__':
    sys.exit(main())
