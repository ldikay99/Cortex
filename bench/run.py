import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'analyzer'))

from cortex_graph import scip
from cortex_graph.analyze import analyze
from cortex_graph.common import Graph

FILE_KINDS = ('module',)
CALL_KINDS = ('call', 'tests')
SKIP_FILE_EDGES = ('contains', 'cochange')
IMPORT_LINE = re.compile(r'\s*(import|from|use|require|include|using)\b')


def sh(cmd, cwd, env=None):
    subprocess.run(cmd, cwd=cwd, env=env, check=True, stdin=subprocess.DEVNULL)


def checkout(repo, work):
    dest = work / 'repos' / repo['name']
    git = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'advice.detachedHead=false']
    if not (dest / '.git').is_dir():
        dest.mkdir(parents=True, exist_ok=True)
        sh(git + ['init', '-q'], dest)
        sh(git + ['remote', 'add', 'origin', repo['url']], dest)
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=dest, capture_output=True, text=True).stdout.strip()
    if head != repo['commit']:
        sh(git + ['fetch', '-q', '--depth', '1', 'origin', repo['commit']], dest)
        sh(git + ['checkout', '-q', '--force', 'FETCH_HEAD'], dest)
    return dest / repo['subdir'] if repo.get('subdir') else dest


def fill(text, values):
    for k, v in values.items():
        text = text.replace('{' + k + '}', str(v))
    return text


def build_index(repo, src, work, tools, reuse):
    index = work / 'indexes' / f"{repo['name']}.scip"
    if reuse and index.is_file():
        return index
    index.parent.mkdir(parents=True, exist_ok=True)
    (work / 'empty-env.json').write_text('[]\n')
    values = {'src': src, 'index': index, 'work': work}
    env = dict(os.environ)
    extra = [str(p) for p in (tools / 'bin', tools / 'node_modules' / '.bin') if p.is_dir()] if tools else []
    env['PATH'] = os.pathsep.join(extra + [env.get('PATH', '')])
    env.update({k: fill(v, values) for k, v in (repo.get('env') or {}).items()})
    cwd = src if repo.get('cwd') == 'src' else work
    if repo.get('prepare') and not (src / 'node_modules').is_dir():
        sh(shlex.split(fill(repo['prepare'], values)), src, env)
    sh(['nice', '-n', '19'] + shlex.split(fill(repo['indexer'], values)), cwd, env)
    return index


def to_graph(out):
    g = Graph()
    by_id = {}
    for n in out['nodes']:
        g.nodes[n['key']] = {k: v for k, v in n.items() if k not in ('id', 'key', 'pos', 'c', 'deg')}
        by_id[n['id']] = n['key']
    for e in out['edges']:
        g.edges[(by_id[e['a']], by_id[e['b']], e['kind'])] = e['w']
    return g


def contains(outer, s):
    return (outer[0], outer[1]) <= (s[0], s[1]) and (s[2], s[3]) <= (outer[2], outer[3])


def ground_truth(docs, root):
    defs, scopes, implementers = {}, defaultdict(list), defaultdict(set)
    for d in docs:
        for sym, ifaces in d['implements'].items():
            for iface in ifaces:
                implementers[iface].add(sym)
        for rng, sym, roles, enclosing in d['occurrences']:
            kind, s = scip.kind_of(sym), scip.span(rng)
            if not (roles & scip.DEFINITION) or not kind or not s:
                continue
            outer = scip.span(enclosing)
            if outer and kind in ('callable', 'type'):
                scopes[d['path']].append((outer, sym, s[0] + 1))
            defs.setdefault(sym, {'file': d['path'], 'line': s[0] + 1, 'kind': kind, 'nested': False})
    for d in docs:
        lines = None
        for rng, sym, roles, _ in d['occurrences']:
            s = scip.span(rng)
            if roles & scip.DEFINITION or not s or scip.kind_of(sym) != 'callable' or sym not in defs:
                continue
            lines = lines if lines is not None else scip.source_lines(root, d['path']) or []
            if s[0] < len(lines) and scip.DECLARES.search(lines[s[0]][:s[1]]):
                scopes[d['path']].append(((s[0], 0, indent_end(lines, s[0]), 0), sym, s[0] + 1))
    for rel, items in scopes.items():
        for outer, sym, _ in items:
            if any(o != outer and contains(o, outer) and defs[p]['kind'] == 'callable' for o, p, _ in items):
                defs[sym]['nested'] = True
    files, calls, dispatch = {}, {}, {}
    for d in docs:
        rel, lines = d['path'], None
        own = sorted(scopes.get(rel, ()), key=lambda x: (x[0][0], x[0][1]))
        for rng, sym, roles, _ in d['occurrences']:
            target, s = defs.get(sym), scip.span(rng)
            if roles & scip.DEFINITION or not target or not s or target['kind'] == 'namespace':
                continue
            if target['file'] != rel:
                files.setdefault((rel, target['file']), (s[0] + 1, sym))
            iface = target['kind'] == 'term' and sym in implementers
            if target['kind'] not in ('callable', 'type') and not iface:
                continue
            if lines is None:
                lines = scip.source_lines(root, rel) or []
            if not scip.called(lines, s):
                continue
            caller = None
            for outer, owner, line in own:
                if outer[0] > s[0]:
                    break
                if contains(outer, s):
                    caller = (rel, line, owner)
            where = (rel, s[0] + 1, s[1], lines[s[0]].strip() if s[0] < len(lines) else '')
            (dispatch if iface else calls).setdefault((caller or rel, sym), where)
    return defs, files, calls, dispatch, implementers


def indent_end(lines, start):
    base = len(lines[start]) - len(lines[start].lstrip())
    i, body = start + 1, False
    while i < len(lines):
        t = lines[i]
        if t.strip() and not t.lstrip().startswith((')', ']', '#')):
            if len(t) - len(t.lstrip()) <= base and body:
                break
            body = body or len(t) - len(t.lstrip()) > base
        i += 1
    return i - 1


def ratio(a, b):
    return round(a / b, 4) if b else None


def scores(truth, pred):
    tp = len(truth & pred)
    return {'tp': tp, 'fp': len(pred - truth), 'fn': len(truth - pred),
            'precision': ratio(tp, len(pred)), 'recall': ratio(tp, len(truth))}


def predicted(g, indexed):
    files, calls = set(), set()
    for (a, b, kind) in g.edges:
        ma, mb = g.nodes[a], g.nodes[b]
        fa, fb = ma.get('file'), mb.get('file')
        if fa not in indexed or fb not in indexed:
            continue
        if kind not in SKIP_FILE_EDGES and fa != fb and ma.get('kind') != 'doc' and mb.get('kind') != 'doc':
            files.add((fa, fb))
        if kind in CALL_KINDS and a != b:
            calls.add((a, b))
    return files, calls


def shape(text, name):
    m = re.search(r'([\w.\]\)]*?)\b' + re.escape(name) + r'\s*\(', text)
    prefix = m.group(1) if m else ''
    if text.lstrip().startswith('@'):
        return 'decorador'
    if prefix.startswith('super()'):
        return 'super().x()'
    if prefix in ('self.', 'cls.'):
        return f'{prefix}x()'
    if prefix.count('.') >= 2 or ')' in prefix or ']' in prefix:
        return 'cadena a.b.x() / x().y()'
    if prefix:
        return 'calificado obj.x()'
    return 'nombre suelto x()'


def label_kind(sym):
    k = scip.kind_of(sym)
    if k == 'type':
        return 'constructor/clase'
    return 'método' if '#' in sym.rsplit('/', 1)[-1] else 'función'


def evaluate(name, root, docs, g, top, scope=()):
    loc_files = {m['file'] for m in g.nodes.values() if m.get('kind') == 'module'}
    paths = scip.align([d['path'] for d in docs], loc_files)
    for d in docs:
        d['path'] = paths.get(d['path'], d['path'])
    docs = [d for d in docs if d['path'] in loc_files and (not scope or d['path'].startswith(tuple(scope)))]
    indexed = {d['path'] for d in docs}
    defs, tfiles, tcalls, dispatch, implementers = ground_truth(docs, root)
    loc = scip.Locator(g, indexed)
    def_lines = {(d['file'], d['line']) for d in defs.values()}

    def node_of(sym_or_rel, line=0):
        if isinstance(sym_or_rel, tuple):
            return loc.definition(sym_or_rel[0], sym_or_rel[1], sym_or_rel[2])
        if sym_or_rel in indexed:
            cand = loc.at(sym_or_rel, line)
            if cand and cand != loc.mods.get(sym_or_rel) and (sym_or_rel, g.nodes[cand]['line']) not in def_lines:
                return cand
            return loc.mods.get(sym_or_rel)
        d = defs[sym_or_rel]
        if d['kind'] == 'module':
            return loc.mods.get(d['file'])
        return loc.definition(d['file'], d['line'], sym_or_rel)

    truth_calls, truth_where = set(), {}
    for (caller, sym), where in sorted(tcalls.items(), key=repr):
        a, b = node_of(caller, where[1]), node_of(sym)
        if a and b and a != b:
            truth_calls.add((a, b))
            truth_where.setdefault((a, b), (where, caller, sym))
    soft = set()
    for (caller, sym), where in sorted(dispatch.items(), key=repr):
        a = node_of(caller, where[1])
        for impl in sorted(implementers[sym]):
            b = node_of(impl) if impl in defs else None
            if a and b and a != b:
                soft.add((a, b))
    soft -= truth_calls
    pfiles, pcalls = predicted(g, indexed)
    ignored = len(pcalls & soft)
    pcalls -= soft
    truth_files = set(tfiles)
    result = {
        'files_indexed': len(indexed),
        'file_deps': scores(truth_files, pfiles),
        'calls': scores(truth_calls, pcalls),
        'dispatch_ignored': ignored,
        'definitions': definitions(defs, g, indexed, loc),
    }
    result['patterns'] = patterns(root, docs, defs, g, truth_calls, truth_where, pcalls, truth_files, pfiles, tfiles, loc, top)
    precise = to_graph_copy(g)
    added = scip.merge(precise, scip.collect(docs, precise, root))
    pf, pc = predicted(precise, indexed)
    pc -= soft
    result['precise'] = {'added': added, 'file_deps': scores(truth_files, pf), 'calls': scores(truth_calls, pc)}
    return result


def to_graph_copy(g):
    h = Graph()
    h.nodes = {k: dict(v) for k, v in g.nodes.items()}
    h.edges = Counter(g.edges)
    return h


def definitions(defs, g, indexed, loc):
    wanted = {s: d for s, d in defs.items() if d['kind'] in ('callable', 'type') and d['file'] in indexed}
    nodes = {nid: m for nid, m in g.nodes.items() if m.get('kind') in scip.SYMBOL_KINDS and m.get('file') in indexed}
    by_place = defaultdict(list)
    for nid, m in nodes.items():
        by_place[(m['file'], str(m['name']).rsplit('.', 1)[-1])].append((m['line'], nid))
    matched, hit = {}, set()
    for sym, d in sorted(wanted.items()):
        cands = [(abs(line - d['line']), nid) for line, nid in by_place.get((d['file'], scip.name_of(sym)), ()) if abs(line - d['line']) <= 3]
        if cands:
            nid = min(cands)[1]
            matched[sym] = nid
            hit.add(nid)
    missed = Counter()
    examples = defaultdict(list)
    for sym, d in sorted(wanted.items(), key=lambda x: (x[1]['file'], x[1]['line'])):
        if sym in matched:
            continue
        cat = def_category(sym, d)
        missed[cat] += 1
        if len(examples[cat]) < 3:
            examples[cat].append(f"{d['file']}:{d['line']} {scip.name_of(sym)}")
    extra = Counter()
    extra_examples = defaultdict(list)
    for nid in sorted(set(nodes) - hit, key=lambda n: (nodes[n]['file'], nodes[n]['line'])):
        cat = f"nodo {nodes[nid]['kind']} sin definición SCIP"
        extra[cat] += 1
        if len(extra_examples[cat]) < 3:
            extra_examples[cat].append(f"{nodes[nid]['file']}:{nodes[nid]['line']} {nodes[nid]['name']}")
    return {
        'scip': len(wanted), 'cortex': len(nodes), 'matched': len(matched),
        'recall': ratio(len(matched), len(wanted)), 'precision': ratio(len(hit), len(nodes)),
        'missed': [{'pattern': k, 'count': v, 'examples': examples[k]} for k, v in missed.most_common()],
        'extra': [{'pattern': k, 'count': v, 'examples': extra_examples[k]} for k, v in extra.most_common()],
    }


def def_category(sym, d):
    if d['nested']:
        return 'función anidada (closure)'
    last = sym.rsplit('/', 1)[-1]
    if d['kind'] == 'type':
        return 'tipo/clase anidada' if last.count('#') > 1 else 'tipo/clase'
    if '#' in last:
        return 'método'
    return 'función'


def patterns(root, docs, defs, g, truth_calls, truth_where, pcalls, truth_files, pfiles, tfiles, loc, top):
    out = {}
    fn, fn_ex = Counter(), defaultdict(list)
    for edge in sorted(truth_calls - pcalls):
        (rel, line, _, text), caller, sym = truth_where[edge]
        cat = [label_kind(sym), shape(text, scip.name_of(sym)), 'mismo archivo' if defs[sym]['file'] == rel else 'otro archivo']
        if caller == rel:
            cat.append('desde nivel de módulo')
        elif loc.definition(*caller) != edge[0] or defs[caller[2]]['nested']:
            cat.append('llamador anidado')
        if any(a == edge[0] and str(g.nodes[b]['name']).rsplit('.', 1)[-1] == scip.name_of(sym) for a, b in pcalls):
            cat.append('Córtex eligió otro destino homónimo')
        key = ' · '.join(cat)
        fn[key] += 1
        if len(fn_ex[key]) < 3:
            fn_ex[key].append(f'{rel}:{line} {text[:120]}')
    out['calls_fn'] = [{'pattern': k, 'count': v, 'examples': fn_ex[k]} for k, v in fn.most_common(top)]
    refs = defaultdict(list)
    for d in docs:
        for rng, sym, roles, _ in d['occurrences']:
            s = scip.span(rng)
            if s and not roles & scip.DEFINITION and not sym.startswith('local '):
                refs[d['path']].append((s[0] + 1, sym))
    fp, fp_ex = Counter(), defaultdict(list)
    lines_cache = {}
    for a, b in sorted(pcalls - truth_calls):
        ma, mb = g.nodes[a], g.nodes[b]
        name = str(mb['name']).rsplit('.', 1)[-1]
        lines = lines_cache.setdefault(ma['file'], scip.source_lines(root, ma['file']) or [])
        start = ma['line']
        end = ma.get('end') or next_start(loc, ma['file'], start) or len(lines)
        seen = [(ln, sym) for ln, sym in refs.get(ma['file'], ()) if start <= ln <= end and scip.name_of(sym) == name]
        if ma['kind'] == 'module':
            seen = [(ln, sym) for ln, sym in refs.get(ma['file'], ()) if scip.name_of(sym) == name]
        if not seen:
            cat = 'sin referencia SCIP con ese nombre en el llamador'
            ln = next((i + 1 for i in range(start - 1, min(end, len(lines))) if re.search(r'\b' + re.escape(name) + r'\b', lines[i])), start)
        else:
            ln, sym = seen[0]
            mapped = {s2: (loc.definition(defs[s2]['file'], defs[s2]['line'], s2) if s2 in defs else None) for _, s2 in seen}
            same = [(l2, s2) for l2, s2 in seen if mapped[s2] == b]
            project = [(l2, s2) for l2, s2 in seen if s2 in defs and scip.kind_of(s2) in ('callable', 'type')]
            if same:
                ln, sym = same[0]
                cat = 'SCIP ve una referencia, no una llamada (conversión, valor, tipo)'
            elif project:
                ln, sym = project[0]
                cat = 'SCIP lo resuelve a otro símbolo homónimo del proyecto'
            elif any(s2 not in defs for _, s2 in seen):
                ln, sym = next((l2, s2) for l2, s2 in seen if s2 not in defs)
                cat = 'SCIP lo resuelve fuera del proyecto (stdlib/dependencia)'
            else:
                cat = 'SCIP lo resuelve a un campo/variable, no a función'
        cat += f" · {mb['kind']}"
        fp[cat] += 1
        if len(fp_ex[cat]) < 3:
            text = lines[ln - 1].strip() if 0 < ln <= len(lines) else ''
            fp_ex[cat].append(f"{ma['file']}:{ln} {a} -> {b} | {text[:100]}")
    out['calls_fp'] = [{'pattern': k, 'count': v, 'examples': fp_ex[k]} for k, v in fp.most_common(top)]
    ffn, ffn_ex = Counter(), defaultdict(list)
    for pair in sorted(truth_files - pfiles):
        line, sym = tfiles[pair]
        lines = lines_cache.setdefault(pair[0], scip.source_lines(root, pair[0]) or [])
        text = lines[line - 1].strip() if 0 < line <= len(lines) else ''
        kind = scip.kind_of(sym)
        cat = f"primera referencia a {kind}" + (' en línea de import' if IMPORT_LINE.match(text) else '')
        ffn[cat] += 1
        if len(ffn_ex[cat]) < 3:
            ffn_ex[cat].append(f'{pair[0]}:{line} -> {pair[1]} | {text[:100]}')
    out['files_fn'] = [{'pattern': k, 'count': v, 'examples': ffn_ex[k]} for k, v in ffn.most_common(top)]
    kinds = defaultdict(set)
    for (a, b, kind) in g.edges:
        fa, fb = g.nodes[a].get('file'), g.nodes[b].get('file')
        if (fa, fb) in pfiles:
            kinds[(fa, fb)].add(kind)
    ffp, ffp_ex = Counter(), defaultdict(list)
    for pair in sorted(pfiles - truth_files):
        cat = 'aristas Córtex: ' + '+'.join(sorted(kinds[pair]))
        if pair[1].endswith('__init__.py'):
            cat += ' · destino __init__.py (reexporta)'
        if (pair[1], pair[0]) in truth_files:
            cat += ' · existe la inversa'
        ffp[cat] += 1
        if len(ffp_ex[cat]) < 3:
            lines = lines_cache.setdefault(pair[0], scip.source_lines(root, pair[0]) or [])
            stem = Path(pair[1]).stem if Path(pair[1]).stem != '__init__' else Path(pair[1]).parent.name
            ln = next((i + 1 for i, t in enumerate(lines) if IMPORT_LINE.match(t) and stem in t), 0)
            ffp_ex[cat].append(f"{pair[0]}:{ln} -> {pair[1]}" + (f' | {lines[ln - 1].strip()[:100]}' if ln else ''))
    out['files_fp'] = [{'pattern': k, 'count': v, 'examples': ffp_ex[k]} for k, v in ffp.most_common(top)]
    return out


def next_start(loc, rel, line):
    return next((s - 1 for s in loc.starts.get(rel, ()) if s > line), None)


def pct(x):
    return '—' if x is None else f'{x * 100:.1f} %'


def markdown(results, meta):
    out = ['# Córtex · benchmark de precisión frente a SCIP', '',
           f"Generado: {meta['date']} · Córtex analizado con `analyze()` (sin git) · verdad de referencia: índices SCIP.", '',
           '| repo | lenguaje | archivos | deps archivo P | deps archivo R | llamadas P | llamadas R | definiciones R | definiciones P | llamadas R (modo preciso) |',
           '|---|---|---|---|---|---|---|---|---|---|']
    for name, r in results.items():
        if 'error' in r:
            out.append(f"| {name} | {r.get('language', '')} | error: {r['error']} | | | | | | | |")
            continue
        out.append(f"| {name} | {r['language']} | {r['files_indexed']} | {pct(r['file_deps']['precision'])} | {pct(r['file_deps']['recall'])} | "
                   f"{pct(r['calls']['precision'])} | {pct(r['calls']['recall'])} | {pct(r['definitions']['recall'])} | "
                   f"{pct(r['definitions']['precision'])} | {pct(r['precise']['calls']['recall'])} |")
    out += ['', 'P = precisión, R = exhaustividad (recall). Solo cuentan archivos presentes en el índice SCIP.', '']
    titles = {'calls_fn': 'Llamadas que Córtex no ve (falsos negativos)', 'calls_fp': 'Llamadas que Córtex inventa (falsos positivos)',
              'files_fn': 'Dependencias entre archivos que faltan', 'files_fp': 'Dependencias entre archivos de más'}
    for name, r in results.items():
        if 'error' in r:
            continue
        out += [f'## {name}', '',
                f"Llamadas: TP {r['calls']['tp']} · FP {r['calls']['fp']} · FN {r['calls']['fn']} — "
                f"deps archivo: TP {r['file_deps']['tp']} · FP {r['file_deps']['fp']} · FN {r['file_deps']['fn']} — "
                f"definiciones: {r['definitions']['matched']}/{r['definitions']['scip']} (Córtex {r['definitions']['cortex']})", '']
        for key, title in titles.items():
            out += [f'### {title}', '', '| n | patrón | ejemplos |', '|---|---|---|']
            for p in r['patterns'][key]:
                out.append(f"| {p['count']} | {p['pattern']} | {'<br>'.join(e.replace('|', '¦') for e in p['examples'])} |")
            out.append('')
        out += ['### Definiciones SCIP sin nodo Córtex', '', '| n | patrón | ejemplos |', '|---|---|---|']
        for p in r['definitions']['missed']:
            out.append(f"| {p['count']} | {p['pattern']} | {'<br>'.join(p['examples'])} |")
        for p in r['definitions']['extra']:
            out.append(f"| {p['count']} | {p['pattern']} | {'<br>'.join(p['examples'])} |")
        out.append('')
    return '\n'.join(out) + '\n'


def main(argv=None):
    p = argparse.ArgumentParser(description='Benchmark de Córtex frente a índices SCIP')
    p.add_argument('--repos', default=str(HERE / 'repos.toml'))
    p.add_argument('--only', action='append', default=[])
    p.add_argument('--work', default=os.environ.get('CORTEX_BENCH_WORK') or str(Path.home() / '.cache' / 'cortex-bench'))
    p.add_argument('--tools', default=os.environ.get('CORTEX_BENCH_TOOLS'))
    p.add_argument('--index', action='append', default=[], help='nombre=ruta de un índice SCIP ya generado')
    p.add_argument('--reuse', action='store_true')
    p.add_argument('--top', type=int, default=10)
    p.add_argument('--out', default=str(HERE / 'results'))
    args = p.parse_args(argv)
    work, outdir = Path(args.work), Path(args.out)
    tools = Path(args.tools) if args.tools else None
    given = dict(x.split('=', 1) for x in args.index)
    repos = tomllib.loads(Path(args.repos).read_text())['repo']
    results = {}
    for repo in repos:
        if (args.only and repo['name'] not in args.only) or (repo.get('skip') and repo['name'] not in args.only):
            continue
        t0 = time.time()
        try:
            src = checkout(repo, work)
            index = Path(given[repo['name']]) if repo['name'] in given else build_index(repo, src, work, tools, args.reuse)
            out = analyze(src, project=repo['name'], git=False)
            r = evaluate(repo['name'], src, scip.read_index(index), to_graph(out), args.top, repo.get('scope') or ())
        except Exception as exc:
            r = {'error': f'{type(exc).__name__}: {exc}'}
        r.update({'language': repo['language'], 'url': repo['url'], 'commit': repo['commit'], 'seconds': round(time.time() - t0, 1)})
        results[repo['name']] = r
        print(f"{repo['name']}: " + (r.get('error') or f"llamadas P {pct(r['calls']['precision'])} R {pct(r['calls']['recall'])} · "
                                    f"deps P {pct(r['file_deps']['precision'])} R {pct(r['file_deps']['recall'])} · "
                                    f"defs R {pct(r['definitions']['recall'])}"))
    outdir.mkdir(parents=True, exist_ok=True)
    meta = {'date': time.strftime('%Y-%m-%d')}
    (outdir / 'results.json').write_text(json.dumps({'meta': meta, 'results': results}, ensure_ascii=False, indent=1, sort_keys=True) + '\n')
    (outdir / 'RESULTS.md').write_text(markdown(results, meta))
    return 0


if __name__ == '__main__':
    sys.exit(main())
