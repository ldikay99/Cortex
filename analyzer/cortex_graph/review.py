import math
import os
import re
import subprocess
from collections import defaultdict

from . import query, store
from .analyze import CODE_EXTS, DOCS, is_test
from .common import digest
from .errors import CortexError, InvalidInput
from .gitinfo import git, unquote

REF_RE = re.compile(r'^[\w./~^@{}-]{1,200}$')
HUNK_RE = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')
WORKTREE = 'WORKTREE'
CODE_KINDS = ('class', 'function', 'method')
DEPTH = 3
TEST_DEPTH = 2
MAX_LEVEL = 50
MAX_FILES = 300
MAX_SYMBOLS = 200
MAX_TESTS = 60
MAX_HASHED = 300
MAX_GREP_FILES = 200
MAX_BYTES = 2 * 1024 * 1024
MAX_DIFF_BYTES = 50 * 1024 * 1024
FAR = 10 ** 9
MIN_COCHANGE = 3
COCHANGE_RATIO = 0.4


def check_ref(ref, label):
    if not isinstance(ref, str) or not REF_RE.match(ref) or ref.startswith('-') or '..' in ref:
        raise InvalidInput(f'«{label}» no es una referencia de git válida')
    return ref


def clean_path(path):
    path = unquote(path.split('\t', 1)[0].strip())
    if path == '/dev/null':
        return None
    if path[:2] in ('a/', 'b/'):
        path = path[2:]
    return path or None


def header_paths(line):
    rest = line[len('diff --git '):].strip()
    if rest.startswith('"'):
        parts = re.findall(r'"(?:[^"\\]|\\.)*"|\S+', rest)
        if len(parts) == 2:
            return clean_path(parts[0]), clean_path(parts[1])
    cut = rest.rfind(' b/')
    if cut < 0:
        return None, None
    return clean_path(rest[:cut]), clean_path(rest[cut + 1:])


def parse_diff(text):
    entries, cur, pending = [], None, [0, 0]

    def start(old=None, new=None):
        entry = {'old': old, 'new': new, 'hunks': [], 'added': 0, 'removed': 0, 'binary': False, 'kind': None}
        entries.append(entry)
        return entry

    for line in text.split('\n'):
        if cur is not None and (pending[0] > 0 or pending[1] > 0):
            if line.startswith('+') and pending[1] > 0:
                cur['added'] += 1
                pending[1] -= 1
                continue
            if line.startswith('-') and pending[0] > 0:
                cur['removed'] += 1
                pending[0] -= 1
                continue
            if line.startswith(' '):
                pending[0], pending[1] = max(0, pending[0] - 1), max(0, pending[1] - 1)
                continue
            if line.startswith('\\'):
                continue
            pending = [0, 0]
        if line.startswith('diff --git '):
            cur = start(*header_paths(line))
        elif line.startswith('--- ') and (cur is None or cur['hunks'] or cur.get('seen_old')):
            cur = start(clean_path(line[4:]))
            cur['seen_old'] = True
        elif line.startswith('--- ') and cur is not None:
            cur['old'] = clean_path(line[4:])
            cur['seen_old'] = True
        elif line.startswith('+++ ') and cur is not None:
            cur['new'] = clean_path(line[4:])
        elif cur is None:
            continue
        elif line.startswith('new file mode'):
            cur['kind'] = 'added'
        elif line.startswith('deleted file mode'):
            cur['kind'] = 'deleted'
        elif line.startswith('rename from '):
            cur['old'] = unquote(line[len('rename from '):].strip()) or None
            cur['kind'] = 'renamed'
        elif line.startswith('rename to '):
            cur['new'] = unquote(line[len('rename to '):].strip()) or None
            cur['kind'] = 'renamed'
        elif line.startswith('Binary files') or line.startswith('GIT binary patch'):
            cur['binary'] = True
        else:
            match = HUNK_RE.match(line)
            if match:
                os_, oc, ns, nc = (int(g) if g is not None else 1 for g in match.groups())
                cur['hunks'].append((os_, oc, ns, nc))
                pending = [oc, nc]
    files = []
    for e in entries:
        old, new = e['old'], e['new']
        if e['kind'] == 'added' or (old is None and new):
            old = None
        if e['kind'] == 'deleted' or (new is None and old):
            new = None
        if old is None and new is None:
            continue
        base = {'added': e['added'], 'removed': e['removed'], 'binary': e['binary'], 'hunks': e['hunks']}
        if old and new and old != new:
            files.append({**base, 'path': old, 'status': 'deleted', 'added': 0, 'renamed_to': new,
                          'hunks': [(1, FAR, 0, 0)]})
            files.append({**base, 'path': new, 'status': 'added', 'removed': 0, 'renamed_from': old,
                          'hunks': [(0, 0, 1, FAR)]})
        elif old is None:
            files.append({**base, 'path': new, 'status': 'added', 'hunks': e['hunks'] or [(0, 0, 1, FAR)]})
        elif new is None:
            files.append({**base, 'path': old, 'status': 'deleted', 'hunks': e['hunks'] or [(1, FAR, 0, 0)]})
        else:
            files.append({**base, 'path': new, 'status': 'modified'})
    merged = {}
    for f in files:
        key = (f['path'], f['status'])
        if key in merged:
            m = merged[key]
            m['added'] += f['added']
            m['removed'] += f['removed']
            m['hunks'] = m['hunks'] + f['hunks']
        else:
            merged[key] = f
    return sorted(merged.values(), key=lambda f: (f['path'], f['status']))


def run_git(root, *args):
    out = git(root, *args)
    if out is None:
        raise CortexError('no se pudo obtener el diff: comprueba que la carpeta es un repositorio git y que existen las referencias')
    return out


def commit_sha(root, ref):
    out = git(root, 'rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}', timeout=15)
    return out.strip() if out else None


def read_disk(root, rel):
    path = os.path.join(root, rel)
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return None
        with open(path, 'rb') as f:
            return f.read()
    except OSError:
        return None


def untracked(root):
    out = git(root, 'ls-files', '--others', '--exclude-standard', '-z', timeout=30) or ''
    found = []
    for rel in sorted(p for p in out.split('\0') if p):
        raw = read_disk(root, rel)
        if raw is None or b'\0' in raw[:8000]:
            found.append({'path': rel, 'status': 'added', 'added': 0, 'removed': 0, 'binary': raw is not None, 'hunks': [(0, 0, 1, FAR)]})
            continue
        lines = raw.count(b'\n') + (1 if raw and not raw.endswith(b'\n') else 0)
        found.append({'path': rel, 'status': 'added', 'added': lines, 'removed': 0, 'binary': False, 'hunks': [(0, 0, 1, max(1, lines))]})
    return found


def blobs(root, specs):
    if not specs:
        return {}
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0'}
    try:
        res = subprocess.run(['git', '-C', str(root), 'cat-file', '--batch'], input=''.join(s + '\n' for s in specs).encode('utf-8'),
                             capture_output=True, timeout=60, env=env)
    except (OSError, subprocess.SubprocessError):
        return {}
    if res.returncode != 0:
        return {}
    out, pos, found = res.stdout, 0, {}
    for spec in specs:
        end = out.find(b'\n', pos)
        if end < 0:
            break
        header = out[pos:end].split()
        pos = end + 1
        if len(header) == 3 and header[1] == b'blob':
            size = int(header[2])
            if size <= MAX_BYTES:
                found[spec] = out[pos:pos + size]
            pos += size + 1
    return found


def project_for(root, project):
    if project not in (None, '') or not root:
        return project
    target = os.path.abspath(root)
    for p in store.list_projects():
        origin = p.get('origin') or {}
        if origin.get('type') == 'local' and origin.get('path') and os.path.abspath(origin['path']) == target:
            return p['project']
    name = store.slug(os.path.basename(target))
    return name if store.load_history(name)['versions'] else None


def source_root(index):
    entry = next((h for h in index.history if h.get('v') == index.version), {})
    origin = entry.get('origin') or {}
    if origin.get('type') == 'local' and origin.get('path') and os.path.isdir(origin['path']):
        return origin['path']
    folder = os.path.join(store.data_dir(), store.slug(index.project), 'fuente')
    return folder if os.path.isdir(folder) else None


def graph_path(index, files, path):
    if path in files:
        return path
    parts = path.split('/')
    for i in range(1, len(parts)):
        tail = '/'.join(parts[i:])
        if tail in files:
            return tail
    return None


def spans(index, rel):
    module = index.file_node.get(rel)
    total = (module or {}).get('end') or FAR
    nodes = sorted((n for n in index.by_file.get(rel, []) if n is not module and n['kind'] not in ('module', 'doc')),
                   key=lambda n: (n['line'], n['id']))
    siblings = defaultdict(list)
    for n in nodes:
        if n['kind'] in CODE_KINDS:
            siblings[n.get('parent')].append(n)
    ends = {}
    for n in nodes:
        if n.get('end'):
            ends[n['id']] = max(n['line'], n['end'])
        elif n['kind'] in CODE_KINDS:
            limit = ends.get(n.get('parent'), total)
            following = [s['line'] for s in siblings[n.get('parent')] if s['line'] > n['line']]
            ends[n['id']] = max(n['line'], min([limit] + [x - 1 for x in following]))
        else:
            ends[n['id']] = n['line']
    return [(n, n['line'], ends[n['id']]) for n in nodes]


def ranges_for(hunks, side):
    out = []
    for os_, oc, ns, nc in hunks:
        start, count, other = (ns, nc, oc) if side == 'new' else (os_, oc, nc)
        if count > 0:
            out.append((start, start + count - 1, other == 0))
        else:
            out.append((max(start, 1), max(start, 1), False))
    return out


def covered(lo, hi, intervals):
    point = lo
    for a, b in sorted(intervals):
        if a > point:
            return False
        point = max(point, b + 1)
        if point > hi:
            return True
    return point > hi


def touched(index, rel, ranges):
    items = spans(index, rel)
    child_spans = defaultdict(list)
    for n, a, b in items:
        if 'parent' in n:
            child_spans[n['parent']].append((a, b))
    hit = {}
    for s, e, pure in ranges:
        for n, a, b in items:
            lo, hi = max(s, a), min(e, b)
            if lo > hi:
                continue
            inner = [(x, y) for x, y in child_spans[n['id']] if x <= hi and y >= lo]
            if covered(lo, hi, inner):
                continue
            record = hit.setdefault(n['id'], {'node': n, 'end': b, 'lines': 0, 'whole': False, 'header': False})
            record['lines'] += hi - lo + 1
            record['header'] = record['header'] or s <= a <= e
            record['whole'] = record['whole'] or (pure and s <= a and e >= b)
    return [hit[k] for k in sorted(hit, key=lambda k: (hit[k]['node']['line'], k))]


def is_code(n):
    return n['kind'] in CODE_KINDS and os.path.splitext(n['file'])[1].lower() in CODE_EXTS - DOCS


def is_test_node(n):
    return bool(n.get('test')) or is_test(n['file'])


def dependents(index, nid):
    found = set()
    for kind in query.DEPENDENCY_KINDS:
        for other, _ in index.inc[kind].get(nid, []):
            found.add(other)
    return found


def traverse(index, seeds, depth):
    distance = {s: 0 for s in seeds}
    reason = {}
    frontier = sorted(seeds)
    for level in range(1, depth + 1):
        following = []
        for current in frontier:
            for kind in query.DEPENDENCY_KINDS:
                for other, _ in index.inc[kind].get(current, []):
                    if other not in distance:
                        distance[other] = level
                        reason[other] = (kind, current)
                        following.append(other)
        frontier = following
        if not frontier:
            break
    return distance, reason


def seeds_of(index, record):
    n = record['node']
    if n['kind'] in ('module', 'doc'):
        return [n['id']] + (index.descendants(n) if record['change'] == 'deleted' else [])
    if n['kind'] == 'class' and record['change'] == 'modified' and not record.get('header', True):
        return [n['id']]
    return [n['id']] + index.descendants(n)


def short(n):
    return n['name'].rsplit('.', 1)[-1]


def grep_tests(root, names):
    words = sorted({w for w in names if len(w) >= 4 and re.match(r'^\w+$', w) and not w.startswith('__')})[:60]
    if not root or not words:
        return None
    args = ['grep', '-l', '-I', '-w', '-F']
    for w in words:
        args += ['-e', w]
    out = git(root, *args, timeout=30)
    if out is None:
        return None if git(root, 'rev-parse', '--git-dir', timeout=15) is None else {}
    hits = {}
    for rel in sorted(p for p in out.split('\n') if p.strip())[:MAX_GREP_FILES * 5]:
        rel = unquote(rel.strip())
        if not is_test(rel) or len(hits) >= MAX_GREP_FILES:
            continue
        raw = read_disk(root, rel)
        if raw is None:
            continue
        text = raw.decode('utf-8', errors='replace')
        found = sorted(w for w in words if re.search(r'\b' + re.escape(w) + r'\b', text))
        if found:
            hits[rel] = found
    return hits


def brief(index, n, **extra):
    item = index.brief(n, **extra)
    for key in ('end', 'vis', 'sig'):
        if n.get(key) and key not in item:
            item[key] = n[key]
    return item


def collect_diff(root, base, head, diff_text):
    if diff_text is not None:
        if not isinstance(diff_text, str):
            raise InvalidInput('«diff_text» debe ser texto')
        if len(diff_text) > MAX_DIFF_BYTES:
            raise InvalidInput('el diff es demasiado grande')
        return parse_diff(diff_text)
    if not root or not os.path.isdir(root):
        raise InvalidInput('indica la carpeta del repositorio (root) o pasa el diff como texto')
    check_ref(base, 'base')
    common = ['diff', '--no-color', '--no-ext-diff', '--no-renames', '--unified=0', '--relative']
    if head == WORKTREE:
        files = parse_diff(run_git(root, *common, base, '--'))
        known = {f['path'] for f in files}
        return sorted(files + [f for f in untracked(root) if f['path'] not in known], key=lambda f: (f['path'], f['status']))
    check_ref(head, 'head')
    return parse_diff(run_git(root, *common, base, head, '--'))


def detect_sides(index, root, base, head, diff, diff_text, graph_files, warnings):
    entry = next((h for h in index.history if h.get('v') == index.version), {})
    graph_sha = (entry.get('commit') or {}).get('sha') or None
    base_sha = commit_sha(root, base) if root and diff_text is None else None
    head_sha = commit_sha(root, head) if root and diff_text is None and head != WORKTREE else None
    default = 'new'
    if graph_sha and head_sha and graph_sha == head_sha:
        default = 'new'
    elif graph_sha and base_sha and graph_sha == base_sha and head != WORKTREE:
        default = 'old'
        warnings.append(f'el grafo (v{index.version}) corresponde a la base del diff: los símbolos nuevos no están en el grafo')
    elif graph_sha and (base_sha or head_sha) and graph_sha not in (base_sha, head_sha):
        warnings.append(f'el grafo (v{index.version}) se generó en el commit {graph_sha[:8]}, que no es la base ni el final del diff: '
                        'las líneas pueden no coincidir; vuelve a analizar el proyecto')
    sides, specs = {}, {}
    for f in diff:
        rel = graph_path(index, graph_files, f['path'])
        if f['status'] != 'modified' or rel is None:
            continue
        module = index.file_node.get(rel)
        if not module or not module.get('hash') or len(specs) >= MAX_HASHED:
            continue
        specs[f['path']] = (rel, module['hash'])
    contents = {}
    if root and specs:
        if diff_text is not None:
            contents = {(p, 'new'): read_disk(root, p) for p in specs}
        else:
            wanted = [f'{base}:{p}' for p in specs] + ([f'{head}:{p}' for p in specs] if head != WORKTREE else [])
            found = blobs(root, wanted)
            for p in specs:
                contents[(p, 'old')] = found.get(f'{base}:{p}')
                contents[(p, 'new')] = read_disk(root, p) if head == WORKTREE else found.get(f'{head}:{p}')
    stale = []
    for p, (rel, h) in sorted(specs.items()):
        new, old = contents.get((p, 'new')), contents.get((p, 'old'))
        if new is not None and digest(new.replace(b'\r\n', b'\n')) == h:
            sides[p] = 'new'
        elif old is not None and digest(old.replace(b'\r\n', b'\n')) == h:
            sides[p] = 'old'
        elif new is not None or old is not None:
            stale.append(rel)
    if stale:
        warnings.append(f'{len(stale)} archivo(s) cambiaron desde el último análisis y sus líneas pueden estar desplazadas: '
                        + ', '.join(stale[:5]) + (' …' if len(stale) > 5 else ''))
    return default, sides, set(stale), graph_sha


def risk_of(index, records, impact_nodes, coverage, test_info, entries, cochange_missing, endpoints, total_lines):
    reasons = []
    impact_nodes = [n for n in impact_nodes if n['kind'] != 'doc']

    def add(factor, points, detail):
        if points > 0:
            reasons.append({'factor': factor, 'points': int(points), 'detail': detail})

    code = [r for r in records if not is_test_node(r['node'])]
    fan = [(len({d for s in seeds_of(index, r) for d in dependents(index, s) if not is_test_node(index.nodes[d])}), r) for r in code]
    if fan:
        top, rec = max(fan, key=lambda x: (x[0], -x[1]['node']['id']))
        add('fan_in', min(20, round(5 * math.log2(1 + top))), f'«{rec["node"]["name"]}» tiene {top} dependiente(s) directo(s)')
    total = len(impact_nodes)
    add('dependents', min(20, round(4 * math.log2(1 + total))), f'{total} símbolo(s) dependen del cambio de forma directa o transitiva')
    churns = sorted(n.get('churn') or 0 for n in index.file_node.values())
    hot = []
    if churns and churns[-1]:
        p90 = churns[int(0.9 * (len(churns) - 1))]
        p75 = churns[int(0.75 * (len(churns) - 1))]
        for e in entries:
            c = e.get('churn') or 0
            if c >= max(5, p90):
                hot.append((12, e['file'], c))
            elif c >= max(3, p75):
                hot.append((6, e['file'], c))
    if hot:
        points, path, c = max(hot, key=lambda x: (x[0], x[2], x[1]))
        add('hotspot', points, f'«{path}» es un punto caliente: {c} commits recientes'
            + (f' (y {len(hot) - 1} archivo(s) más)' if len(hot) > 1 else ''))
    symbols = [r for r in code if is_code(r['node']) and r['change'] != 'deleted']
    if test_info == 'none':
        add('tests', 8, 'no hay información de tests (el análisis los excluyó y no se pudo buscar en el repositorio)')
    elif symbols:
        missing = [r for r in symbols if not coverage.get(r['node']['id'])]
        add('tests', round(20 * len(missing) / len(symbols)), f'{len(missing)} de {len(symbols)} símbolo(s) cambiados no tienen tests que los ejerciten')
    public = [r for r in code if r['node'].get('vis') == 'public' and r['change'] != 'added'
              and any(index.nodes[d]['file'] != r['node']['file'] for d in dependents(index, r['node']['id']))]
    add('public_api', min(10, 4 * len(public)), f'{len(public)} símbolo(s) públicos usados desde otros archivos')
    own = {r['node']['c'] for r in records}
    reach = sorted({n['c'] for n in impact_nodes} - own)
    add('communities', min(10, 3 * len(reach)), f'el impacto alcanza {len(reach)} comunidad(es) más: '
        + ', '.join(index.community_name(c) or str(c) for c in reach[:4]))
    add('endpoints', min(10, 4 * len(endpoints)), f'{len(endpoints)} endpoint(s) afectados: ' + ', '.join(endpoints[:4]))
    gone = [r for r in records if r['change'] == 'deleted' and any(not is_test_node(index.nodes[d]) and d not in r['seeds']
                                                                    for s in r['seeds'] for d in dependents(index, s))]
    add('deleted', min(15, 5 * len(gone)), f'{len(gone)} símbolo(s) eliminados todavía tienen dependientes en el grafo')
    add('cochange', min(10, 2 * len(cochange_missing)), f'{len(cochange_missing)} archivo(s) suelen cambiar junto a estos y no están en el diff')
    add('size', min(8, round(2 * math.log2(1 + total_lines / 50))), f'{total_lines} línea(s) cambiadas')
    reasons.sort(key=lambda r: (-r['points'], r['factor']))
    score = min(100, sum(r['points'] for r in reasons))
    return {'score': score, 'level': 'alto' if score >= 60 else 'medio' if score >= 30 else 'bajo', 'reasons': reasons}


def file_hits(index, f, rel, module, side):
    if f['status'] == 'modified':
        hits = touched(index, rel, ranges_for(f['hunks'], side))
        for h in hits:
            h['change'] = ('added' if side == 'new' else 'deleted') if h['whole'] else 'modified'
    else:
        top = [(n, a, b) for n, a, b in spans(index, rel) if 'parent' not in n or index.nodes[n['parent']] is module]
        hits = [{'node': n, 'end': b, 'lines': b - a + 1 if b < FAR else 1, 'change': f['status']} for n, a, b in top]
        if module:
            hits.insert(0, {'node': module, 'end': module.get('end'), 'lines': f['added'] + f['removed'], 'change': f['status']})
    if not hits and module:
        hits = [{'node': module, 'end': module.get('end'), 'lines': f['added'] + f['removed'], 'change': 'modified'}]
    return hits


def map_files(index, diff, default, sides, stale, warnings):
    graph_files = set(index.file_node) | set(index.by_file)
    records, entries, missing = {}, [], []
    for f in diff:
        rel = graph_path(index, graph_files, f['path'])
        module = index.file_node.get(rel) if rel else None
        entry = {'file': rel or f['path'], 'status': f['status'], 'added': f['added'], 'removed': f['removed']}
        entry.update({k: f[k] for k in ('renamed_from', 'renamed_to', 'binary') if f.get(k)})
        entry.update({k: module[k] for k in ('churn', 'last', 'authors') if module and module.get(k)})
        entry['in_graph'] = rel is not None
        entries.append(entry)
        if rel is None:
            if f['status'] != 'deleted':
                missing.append(f['path'])
            continue
        if rel in stale:
            entry['stale'] = True
        side = 'old' if f['status'] == 'deleted' else 'new' if f['status'] == 'added' else sides.get(f['path'], default)
        hits = file_hits(index, f, rel, module, side)
        entry['symbols'] = len(hits)
        for h in hits:
            rec = records.setdefault(h['node']['id'], {'node': h['node'], 'end': h['end'], 'lines': 0, 'change': h['change'], 'header': False})
            rec['lines'] += h['lines']
            rec['header'] = rec['header'] or h.get('header', True)
    if missing:
        warnings.append(f'{len(missing)} archivo(s) del diff no están en el grafo: ' + ', '.join(missing[:5]) + (' …' if len(missing) > 5 else ''))
    ordered = [records[k] for k in sorted(records, key=lambda k: (records[k]['node']['file'], records[k]['node']['line'], k))]
    for r in ordered:
        r['seeds'] = set(seeds_of(index, r))
    return entries, ordered


def impact_of(index, ordered):
    seeds = set().union(*(r['seeds'] for r in ordered)) if ordered else set()
    distance, reason = traverse(index, seeds, DEPTH)
    impacted = sorted((i for i, d in distance.items() if d > 0), key=lambda i: (distance[i], -index.nodes[i]['deg'], i))
    nodes = [index.nodes[i] for i in impacted if not is_test_node(index.nodes[i])]
    levels, files_at = [], {}
    for level in range(1, DEPTH + 1):
        members = [n for n in nodes if distance[n['id']] == level]
        if not members:
            continue
        for n in members:
            files_at.setdefault(n['file'], level)
        levels.append({'distance': level, 'count': len(members),
                       'nodes': [brief(index, n, via=reason[n['id']][0], depends_on=index.nodes[reason[n['id']][1]]['name'])
                                 for n in members[:MAX_LEVEL]]})
    reached = [index.nodes[i] for i in seeds] + nodes + [index.nodes[a] for i in seeds for a, _ in index.inc['handles'].get(i, [])]
    endpoints = sorted({n.get('route') or n['name'] for n in reached if n['kind'] == 'endpoint' or n.get('route')})
    result = {'total': len(nodes), 'depth': DEPTH, 'levels': levels,
              'files': [{'file': f, 'distance': d} for f, d in sorted(files_at.items(), key=lambda x: (x[1], x[0]))][:MAX_FILES],
              'communities': sorted({index.community_name(n['c']) for n in nodes} - {None}), 'endpoints': endpoints[:MAX_LEVEL]}
    return result, nodes, endpoints


def graph_tests(index, ordered, coverage):
    found = {}
    for r in ordered:
        if is_test_node(r['node']):
            continue
        local, _ = traverse(index, r['seeds'], TEST_DEPTH)
        module = index.file_node.get(r['node']['file'])
        if module and module['id'] not in r['seeds']:
            for other, _ in index.inc['import'].get(module['id'], []):
                local.setdefault(other, 1)
        direct = {a for s in r['seeds'] for a, _ in index.inc['tests'].get(s, [])}
        for i, d in sorted(local.items()):
            n = index.nodes[i]
            if d == 0 or not is_test_node(n):
                continue
            via = 'tests' if i in direct else 'import' if n['kind'] == 'module' else 'calls'
            item = found.setdefault(i, {'node': n, 'distance': d, 'via': via, 'targets': set()})
            item['distance'] = min(item['distance'], d)
            item['via'] = 'tests' if 'tests' in (via, item['via']) else item['via']
            item['targets'].add(r['node']['name'])
            coverage[r['node']['id']].add(i)
    return sorted(found.values(), key=lambda t: (t['distance'], t['via'] != 'tests', t['node']['file'], t['node']['line'], t['node']['id']))


def stem(n):
    return os.path.splitext(os.path.basename(n['file']))[0] if n['kind'] in ('module', 'doc') else short(n)


def grep_coverage(index, root, ordered, coverage):
    code = [r for r in ordered if not is_test_node(r['node'])]
    near = {r['node']['id']: {stem(r['node'])} | {short(index.nodes[d]) for s in r['seeds'] for d in dependents(index, s)
                                                  if index.nodes[d]['kind'] in CODE_KINDS} for r in code}
    mentions = grep_tests(root, sorted(set().union(*near.values())) if near else [])
    if mentions is None:
        return None
    seen = set().union(*mentions.values()) if mentions else set()
    for r in code:
        if near[r['node']['id']] & seen:
            coverage[r['node']['id']].add(-1)
    return mentions


def forgotten(index, entries):
    in_diff = {e['file'] for e in entries}
    best = {}
    for e in entries:
        module = index.file_node.get(e['file'])
        if not module:
            continue
        for table in (index.out, index.inc):
            for other, w in table['cochange'].get(module['id'], []):
                path = index.nodes[other]['file']
                if path not in in_diff and w >= MIN_COCHANGE and w >= COCHANGE_RATIO * (module.get('churn') or 0):
                    item = {'file': path, 'with': e['file'], 'count': w}
                    old = best.get(path)
                    if old is None or (-w, e['file']) < (-old['count'], old['with']):
                        best[path] = item
    return sorted(best.values(), key=lambda c: (-c['count'], c['file']))[:20]


def review(root, base='HEAD~1', head='HEAD', project=None, diff_text=None):
    base, head = base or 'HEAD~1', head or 'HEAD'
    root = os.path.abspath(os.path.expanduser(str(root))) if root not in (None, '') else None
    name = project_for(root, project)
    index = query.load_index(name)
    if root is None:
        root = source_root(index)
        if root and git(root, 'rev-parse', '--git-dir', timeout=15) is None:
            root = None if diff_text is None else root
    diff = collect_diff(root, base, head, diff_text)
    warnings = [f'no hay un proyecto analizado desde «{root}»: se usa el último analizado, «{index.project}»'] if root and not name else []
    graph_files = set(index.file_node) | set(index.by_file)
    default, sides, stale, graph_sha = detect_sides(index, root, base, head, diff, diff_text, graph_files, warnings)
    entries, ordered = map_files(index, diff, default, sides, stale, warnings)
    impact, impact_nodes, endpoints = impact_of(index, ordered)
    coverage = defaultdict(set)
    covering = graph_tests(index, ordered, coverage)
    stats = index.graph.get('stats') or {}
    source, mentions = 'graph', {}
    if stats.get('tests') is False and not any(n.get('test') for n in index.file_node.values()):
        mentions = grep_coverage(index, root, ordered, coverage)
        source = 'none' if mentions is None else 'grep'
        mentions = mentions or {}
        if source == 'none':
            warnings.append('el análisis excluyó los tests y no se pudo buscar en el repositorio: vuelve a analizar con tests')
    test_files = {}
    for t in covering:
        test_files.setdefault(t['node']['file'], t['distance'])
    code = [r for r in ordered if not is_test_node(r['node']) and is_code(r['node']) and r['change'] != 'deleted']
    cochange = forgotten(index, entries)
    total_lines = sum(f['added'] + f['removed'] for f in diff)
    risk = risk_of(index, ordered, impact_nodes, coverage, source, entries, cochange, endpoints, total_lines)
    return {
        **index.context(), 'base': base, 'head': head, 'graph_commit': graph_sha,
        'summary': {'files': len(entries), 'added': sum(f['added'] for f in diff), 'removed': sum(f['removed'] for f in diff),
                    'symbols': len(ordered), 'dependents': len(impact_nodes), 'tests': len(test_files) + len(mentions)},
        'files': entries[:MAX_FILES],
        'symbols': [brief(index, r['node'], **({'end': r['end']} if r['end'] and r['end'] < FAR else {}), change=r['change'], lines=r['lines'])
                    for r in ordered[:MAX_SYMBOLS]],
        'impact': impact,
        'tests': {
            'source': source,
            'covering': [brief(index, t['node'], via=t['via'], distance=t['distance'], targets=sorted(t['targets'])) for t in covering[:MAX_TESTS]],
            'files': [{'file': f, 'distance': d} for f, d in sorted(test_files.items(), key=lambda x: (x[1], x[0]))][:MAX_TESTS],
            'mentions': [{'file': f, 'names': names} for f, names in sorted(mentions.items())][:MAX_TESTS],
            'missing': [r['node']['name'] for r in code if not coverage.get(r['node']['id'])][:MAX_SYMBOLS],
            'changed': sorted({r['node']['file'] for r in ordered if is_test_node(r['node'])})[:MAX_TESTS],
        },
        'cochange': cochange, 'risk': risk, 'warnings': warnings,
    }
