import json
import os
import re
import threading
from collections import Counter, defaultdict, deque

from . import search as text_search
from . import store
from .analyze import export_markdown, is_test
from .errors import InvalidInput, NotFound

KINDS = ('module', 'class', 'function', 'method', 'doc', 'package', 'variable', 'endpoint', 'topic')
DEPENDENCY_KINDS = ('import', 'call', 'inherits', 'ref', 'tests', 'http', 'rpc', 'handles', 'env', 'data', 'event', 'depends')
RELATIONS = (
    ('imports', 'import', 'out'), ('imported_by', 'import', 'in'),
    ('calls', 'call', 'out'), ('called_by', 'call', 'in'),
    ('inherits', 'inherits', 'out'), ('inherited_by', 'inherits', 'in'),
    ('refs', 'ref', 'out'), ('referenced_by', 'ref', 'in'),
    ('loads', 'loads', 'out'), ('loaded_by', 'loads', 'in'),
    ('tests', 'tests', 'out'), ('tested_by', 'tests', 'in'),
    ('http_calls', 'http', 'out'), ('http_callers', 'http', 'in'),
    ('rpc_calls', 'rpc', 'out'), ('rpc_callers', 'rpc', 'in'),
    ('handled_by', 'handles', 'out'), ('handles', 'handles', 'in'),
    ('env_vars', 'env', 'out'), ('env_users', 'env', 'in'),
    ('data', 'data', 'out'), ('data_users', 'data', 'in'),
    ('emits', 'event', 'out'), ('receives', 'event', 'in'),
    ('depends_on', 'depends', 'out'), ('dependents', 'depends', 'in'),
)
USAGE_KINDS = tuple(k for k in DEPENDENCY_KINDS if k != 'depends') + ('loads',)
SYMBOL_KINDS = ('function', 'method', 'class')
BRIEF_FIELDS = ('route', 'table', 'status', 'sig', 'end', 'vis', 'version', 'ecosystem')
MAX_BRIEF_DOC = 200
BARRELS = {'__init__.py', 'index.ts', 'index.tsx', 'index.js', 'index.mjs', 'index.cjs', 'mod.rs', 'lib.rs', 'main.rs', 'main.go'}
MANIFESTS = {'package.json', 'pyproject.toml', 'setup.cfg', 'setup.py', 'Cargo.toml'}
CONFIG_RE = re.compile(r'(^|/)(\.env[\w.-]*|Dockerfile[\w.-]*|[\w.-]*\.(ya?ml|toml|json|ini|cfg|conf|properties|tf|tfvars|env))$', re.I)
PROTOCOL_NAMES = {'main', 'init', 'constructor', 'setup', 'teardown', 'setUp', 'tearDown', 'run', 'render', 'toString', 'equals',
                  'hashCode', 'String', 'Error', 'ServeHTTP', 'new', 'default', 'drop', 'fmt', 'from', 'deref', 'clone', 'call'}
SECTIONS = ('entry_points', 'endpoints', 'untested_public', 'cycles', 'dead_code', 'hotspots', 'layers')
SECTION_LIMITS = {'entry_points': 30, 'endpoints': 30, 'untested_public': 30, 'cycles': 20, 'dead_code': 50, 'hotspots': 20, 'layers': 50}
MAX_PAGE = 500
LAYER_KINDS = {'import', 'call', 'inherits', 'handles', 'http', 'rpc', 'data', 'event'}
IDENT_RE = re.compile(r'[A-Za-z_$][\w$]*[?!]?')
BUILD_RE = re.compile(r'(^|/)(Makefile|GNUmakefile|[Jj]ustfile|Taskfile[\w.]*|CMakeLists\.txt|[\w.-]+\.(mk|cmake))$')
MAX_SCAN_BYTES = 64 * 1024 * 1024
BASES_RE = re.compile(r'\(\s*\w|\bextends\b|\bimplements\b|^[^(]*\bclass\s+\w+\s*:\s*\w|\bimpl\b')
MAX_PATH = 12
MAX_LIST = 100
MAX_CHANGES = 200
CACHE_SIZE = 8

cache = {}
cache_lock = threading.Lock()


def clamp_int(value, default, low, high, label):
    if value in (None, ''):
        return default
    if isinstance(value, bool):
        raise InvalidInput(f'«{label}» debe ser un número entero')
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidInput(f'«{label}» debe ser un número entero') from exc
    return max(low, min(high, number))


def resolve_project(project=None):
    if project not in (None, ''):
        if not isinstance(project, str) or len(project) > 200:
            raise InvalidInput('el nombre del proyecto no es válido')
        name = store.slug(project)
        if not store.load_history(name)['versions']:
            raise NotFound(f'no existe el proyecto «{project}» o no tiene versiones guardadas')
        return name
    latest = store.latest_project()
    if not latest:
        raise NotFound('todavía no hay proyectos analizados: usa «cortex analyze <carpeta o URL de GitHub>»')
    return latest


def load_index(project=None, version=None):
    name = resolve_project(project)
    hist = store.load_history(name)
    number = store.parse_version(version) or hist['versions'][-1]['v']
    path = store.version_path(name, number)
    try:
        stamp = os.path.getmtime(path)
    except OSError as exc:
        raise NotFound(f'el proyecto «{name}» no tiene la versión v{number}') from exc
    key = (store.data_dir(), name, number)
    with cache_lock:
        hit = cache.get(key)
        if hit and hit[0] == stamp:
            return hit[1]
    graph = store.load_version(name, number)
    if graph is None:
        raise NotFound(f'el proyecto «{name}» no tiene la versión v{number}')
    index = GraphIndex(graph, hist)
    with cache_lock:
        cache.pop(key, None)
        while len(cache) >= CACHE_SIZE:
            cache.pop(next(iter(cache)))
        cache[key] = (stamp, index)
    return index


class GraphIndex:
    def __init__(self, graph, history=None):
        self.graph = graph
        self.project = graph['project']
        self.version = graph.get('version')
        self.history = (history or {}).get('versions') or graph.get('history') or []
        self.origin = (history or {}).get('origin')
        self.lock = threading.Lock()
        self.searcher = None
        self.spans = None
        self.identifiers = False
        self.nodes = graph['nodes']
        self.communities = {c['id']: c for c in graph['communities']}
        self.by_key = {n['key']: n for n in self.nodes}
        self.by_name = defaultdict(list)
        self.by_name_lower = defaultdict(list)
        self.by_file = defaultdict(list)
        self.file_node = {}
        self.children = defaultdict(list)
        for n in self.nodes:
            self.by_name[n['name']].append(n)
            self.by_name_lower[n['name'].lower()].append(n)
            self.by_file[n['file']].append(n)
            if n['kind'] in ('module', 'doc'):
                self.file_node[n['file']] = n
            if 'parent' in n:
                self.children[n['parent']].append(n)
        self.out = defaultdict(lambda: defaultdict(list))
        self.inc = defaultdict(lambda: defaultdict(list))
        self.undirected = defaultdict(list)
        for e in graph['edges']:
            a, b, kind, w = e['a'], e['b'], e['kind'], e['w']
            self.out[kind][a].append((b, w))
            self.inc[kind][b].append((a, w))
            self.undirected[a].append((b, kind, 'forward'))
            self.undirected[b].append((a, kind, 'backward'))
        for neighbours in self.undirected.values():
            neighbours.sort(key=lambda item: (item[1] == 'contains', item[0]))

    def community_name(self, cid):
        c = self.communities.get(cid)
        return c['name'] if c else None

    def brief(self, n, **extra):
        item = {'id': n['id'], 'key': n['key'], 'kind': n['kind'], 'name': n['name'], 'file': n['file'], 'line': n['line'],
                'deg': n['deg'], 'community': self.community_name(n['c'])}
        for field in BRIEF_FIELDS:
            if n.get(field):
                item[field] = n[field]
        if n.get('doc'):
            item['doc'] = n['doc'] if len(n['doc']) <= MAX_BRIEF_DOC else n['doc'][:MAX_BRIEF_DOC - 1].rstrip() + '…'
        if n.get('test'):
            item['test'] = True
        item.update(extra)
        return item

    @staticmethod
    def mini(n, **extra):
        item = {'key': n['key'], 'kind': n['kind'], 'name': n['name'], 'file': n['file'], 'line': n['line']}
        item.update(extra)
        return item

    def text_index(self):
        with self.lock:
            if self.searcher is None:
                self.searcher = text_search.Index(self.nodes)
            return self.searcher

    def is_test_node(self, n):
        return bool(n.get('test')) or is_test(n['file'])

    def span(self, n):
        if n.get('end'):
            return n['line'], max(n['line'], int(n['end']))
        if n['kind'] in ('module', 'doc'):
            return 1, None
        with self.lock:
            if self.spans is None:
                spans = {}
                for members in self.by_file.values():
                    symbols = sorted((m for m in members if m['kind'] not in ('module', 'doc')), key=lambda m: (m['line'], m['id']))
                    for k, m in enumerate(symbols):
                        inside = {m['id']}
                        following = None
                        for other in symbols[k + 1:]:
                            if other.get('parent') in inside:
                                inside.add(other['id'])
                                continue
                            if other['line'] > m['line']:
                                following = other['line'] - 1
                                break
                        spans[m['id']] = following
                self.spans = spans
        end = self.spans.get(n['id'])
        return n['line'], (max(n['line'], end) if end else None)

    def source_root(self):
        candidate = os.path.join(store.data_dir(), store.slug(self.project), 'fuente')
        if os.path.isdir(candidate):
            return candidate
        entries = [h for h in self.history if h.get('v') == self.version] + list(reversed(self.history))
        for origin in [h.get('origin') for h in entries] + [self.origin]:
            if isinstance(origin, dict) and origin.get('type') == 'local' and isinstance(origin.get('path'), str):
                if os.path.isdir(origin['path']):
                    return origin['path']
        return None

    def analyzed_at(self):
        entry = next((h for h in self.history if h.get('v') == self.version), {})
        return entry.get('date')

    def context(self):
        return {'project': self.project, 'version': self.version}

    @staticmethod
    def best(candidates):
        return max(candidates, key=lambda n: (n['deg'], -n['id']))

    def resolve(self, ref):
        if isinstance(ref, int) and not isinstance(ref, bool):
            ref = str(ref)
        if not isinstance(ref, str) or not ref.strip():
            raise InvalidInput('falta la referencia: usa una clave, un nombre de símbolo o una ruta de archivo')
        ref = ref.strip()
        if len(ref) > 500:
            raise InvalidInput('la referencia es demasiado larga')
        if ref in self.by_key:
            return self.by_key[ref]
        if ref in self.by_name:
            return self.best(self.by_name[ref])
        path = ref.replace('\\', '/').removeprefix('./')
        if path in self.file_node:
            return self.file_node[path]
        lower = ref.lower()
        if lower in self.by_name_lower:
            return self.best(self.by_name_lower[lower])
        suffix = [n for f, n in self.file_node.items() if f.endswith('/' + path)]
        if len(suffix) == 1:
            return suffix[0]
        contains = [n for n in self.nodes if lower in n['name'].lower() or lower in n['key'].lower()]
        if contains:
            return max(contains, key=lambda n: (lower in n['name'].lower(), n['deg'], -n['id']))
        raise NotFound(f'no encontré «{ref}» en el proyecto {self.project}')

    def related(self, n, kind, direction, limit=MAX_LIST):
        table = self.out if direction == 'out' else self.inc
        pairs = sorted(table[kind].get(n['id'], []), key=lambda p: (-p[1], -self.nodes[p[0]]['deg']))
        return [self.brief(self.nodes[i], weight=w) for i, w in pairs[:limit]]

    def overview(self):
        cross = defaultdict(Counter)
        for e in self.graph['edges']:
            ca, cb = self.nodes[e['a']]['c'], self.nodes[e['b']]['c']
            if ca != cb:
                cross[ca][cb] += e['w']
                cross[cb][ca] += e['w']
        files_per_comm = Counter(n['c'] for n in self.file_node.values())
        communities = [{
            'id': c['id'], 'name': c['name'], 'size': c['size'], 'files': files_per_comm[c['id']], 'hub': c['hub'],
            'connected_to': [{'id': o, 'name': self.community_name(o), 'weight': w} for o, w in cross[c['id']].most_common(3)],
        } for c in self.graph['communities']]
        entry = next((h for h in self.history if h.get('v') == self.version), {})
        handled = {n['route'] for n in self.nodes if n.get('route') and n['kind'] != 'endpoint'}
        routes = sorted((n for n in self.nodes if n.get('route') and (n['kind'] != 'endpoint' or n['route'] not in handled)),
                        key=lambda n: (n['route'].split(' ', 1)[-1], n['id']))
        tables = sorted((n for n in self.nodes if n.get('table')), key=lambda n: (n['table'], n['id']))
        return {
            **self.context(),
            'date': entry.get('date'),
            'origin': entry.get('origin'),
            'commit': entry.get('commit'),
            'versions': len(self.history),
            'stats': {k: self.graph['stats'].get(k) for k in ('files', 'nodes', 'edges', 'communities', 'languages', 'kinds', 'edge_kinds', 'tests', 'excluded', 'warnings_total')},
            'communities': communities,
            'top_nodes': [self.brief(n) for n in sorted(self.nodes, key=lambda n: (-n['deg'], n['id']))[:20]],
            'routes': [self.brief(n) for n in routes[:MAX_LIST]],
            'routes_total': len(routes),
            'tables': [self.brief(n) for n in tables[:MAX_LIST]],
            'tables_total': len(tables),
        }

    def search(self, text, kind=None, limit=20, offset=0):
        if not isinstance(text, str) or not text.strip():
            raise InvalidInput('la búsqueda está vacía')
        if len(text) > 300:
            raise InvalidInput('la búsqueda es demasiado larga')
        if kind not in (None, '') and kind not in KINDS:
            raise InvalidInput(f'tipo inválido «{kind}»: usa {", ".join(KINDS)}')
        limit = clamp_int(limit, 20, 1, 200, 'limit')
        offset = clamp_int(offset, 0, 0, 10 ** 6, 'offset')
        ranked, total = self.text_index().search(text, kind or None)
        return {**self.context(), 'query': text, 'kind': kind or None, 'total': total, 'offset': offset,
                'terms': text_search.query_terms(text),
                'results': [self.brief(r[3], score=round(r[0], 3)) for r in ranked[offset:offset + limit]]}

    def ranked(self, text, kind=None):
        return self.text_index().search(text, kind or None)[0]

    def node(self, ref):
        n = self.resolve(ref)
        parent = self.nodes[n['parent']] if 'parent' in n else None
        main = self.brief(n, hash=n.get('hash'))
        for field in ('doc', 'churn', 'last', 'authors'):
            if n.get(field):
                main[field] = n[field]
        result = {
            **self.context(),
            'node': main,
            'status': n.get('status') or 'unchanged',
            'community': {'id': n['c'], 'name': self.community_name(n['c'])},
            'parent': self.brief(parent) if parent else None,
            'children': [self.brief(c) for c in sorted(self.children[n['id']], key=lambda c: c['line'])][:MAX_LIST],
        }
        for label, kind, direction in RELATIONS:
            result[label] = self.related(n, kind, direction)
        pairs = Counter()
        for table in (self.out, self.inc):
            for other, w in table['cochange'].get(n['id'], []):
                pairs[other] += w
        result['co_changes'] = [{'file': self.nodes[i]['file'], 'weight': w}
                                for i, w in sorted(pairs.items(), key=lambda p: (-p[1], p[0]))[:20]]
        if n['kind'] == 'topic':
            result['producers'], result['consumers'] = result['receives'], result['emits']
        elif n['kind'] == 'variable':
            users = self.inc['env'].get(n['id'], [])
            result['defined_in'] = sorted({self.nodes[i]['file'] for i, _ in users if self.defines(self.nodes[i])} | {n['file']})
            result['used_by'] = [self.brief(self.nodes[i]) for i, _ in users if not self.defines(self.nodes[i])][:MAX_LIST]
        elif n['kind'] == 'package':
            result['used_by'] = sorted({self.nodes[i]['file'] for i, _ in self.inc['depends'].get(n['id'], [])})[:MAX_LIST * 2]
        return result

    def defines(self, n):
        return n['kind'] == 'module' and CONFIG_RE.search(n['file']) is not None

    def find_file(self, path):
        if not isinstance(path, str) or not path.strip():
            raise InvalidInput('falta la ruta del archivo')
        clean = path.strip().replace('\\', '/').removeprefix('./')
        if clean in self.file_node:
            return self.file_node[clean]
        suffix = [n for f, n in self.file_node.items() if f.endswith('/' + clean)]
        if len(suffix) == 1:
            return suffix[0]
        if len(suffix) > 1:
            options = ', '.join(sorted(n['file'] for n in suffix)[:8])
            raise NotFound(f'«{path}» es ambiguo: {options}')
        n = self.resolve(path)
        return self.file_node.get(n['file'], n)

    def file(self, path):
        f = self.find_file(path)
        symbols = sorted((n for n in self.by_file[f['file']] if n is not f), key=lambda n: (n['line'], n['id']))
        ids = {n['id'] for n in self.by_file[f['file']]}
        called_from = Counter()
        calls_into = Counter()
        for n in self.by_file[f['file']]:
            for other, w in self.inc['call'].get(n['id'], []):
                if other not in ids:
                    called_from[self.nodes[other]['file']] += w
            for other, w in self.out['call'].get(n['id'], []):
                if other not in ids:
                    calls_into[self.nodes[other]['file']] += w
        return {
            **self.context(),
            'file': f['file'],
            'node': self.brief(f),
            'community': {'id': f['c'], 'name': self.community_name(f['c'])},
            'symbols': [{'kind': s['kind'], 'name': s['name'], 'line': s['line'], 'deg': s['deg'], 'key': s['key'],
                         **({'route': s['route']} if s.get('route') else {}), **({'table': s['table']} if s.get('table') else {})}
                        for s in symbols],
            'imports': sorted({self.nodes[i]['file'] for i, _ in self.out['import'].get(f['id'], [])}),
            'imported_by': sorted({self.nodes[i]['file'] for i, _ in self.inc['import'].get(f['id'], [])}),
            'calls_into': [{'file': k, 'weight': w} for k, w in calls_into.most_common(MAX_LIST)],
            'called_from': [{'file': k, 'weight': w} for k, w in called_from.most_common(MAX_LIST)],
            'docs': sorted({self.nodes[i]['file'] for i, _ in self.inc['ref'].get(f['id'], []) if self.nodes[i]['kind'] == 'doc'}),
            'mentions': sorted({self.nodes[i]['file'] for i, _ in self.out['ref'].get(f['id'], [])}),
        }

    def find_community(self, ref):
        if isinstance(ref, int) and not isinstance(ref, bool):
            ref = str(ref)
        if not isinstance(ref, str) or not ref.strip():
            raise InvalidInput('falta la comunidad: usa su número o su nombre')
        ref = ref.strip()
        if ref.isdigit() and int(ref) in self.communities:
            return self.communities[int(ref)]
        lower = ref.lower()
        for c in self.graph['communities']:
            if c['name'].lower() == lower:
                return c
        partial = [c for c in self.graph['communities'] if lower in c['name'].lower() or lower == c['hub'].lower()]
        if partial:
            return max(partial, key=lambda c: c['size'])
        raise NotFound(f'no encontré la comunidad «{ref}» en el proyecto {self.project}')

    def community(self, ref):
        c = self.find_community(ref)
        cid = c['id']
        members = [n for n in self.nodes if n['c'] == cid]
        symbols_per_file = Counter(n['file'] for n in members if n['kind'] not in ('module', 'doc'))
        depends_on, used_by, external_files = Counter(), Counter(), Counter()
        for e in self.graph['edges']:
            a, b = self.nodes[e['a']], self.nodes[e['b']]
            if a['c'] == cid and b['c'] != cid:
                depends_on[b['c']] += e['w']
                if e['kind'] in DEPENDENCY_KINDS:
                    external_files[b['file']] += e['w']
            elif b['c'] == cid and a['c'] != cid:
                used_by[a['c']] += e['w']
        files = sorted((n for n in members if n['kind'] in ('module', 'doc')), key=lambda n: (-n['deg'], n['file']))
        return {
            **self.context(),
            'community': {'id': cid, 'name': c['name'], 'hub': c['hub'], 'size': c['size'], 'files': len(files)},
            'files': [{'file': n['file'], 'kind': n['kind'], 'deg': n['deg'], 'symbols': symbols_per_file[n['file']]} for n in files][:MAX_LIST * 2],
            'hubs': [self.brief(n) for n in sorted(members, key=lambda n: (-n['deg'], n['id']))[:10]],
            'depends_on': [{'id': o, 'name': self.community_name(o), 'weight': w} for o, w in depends_on.most_common()],
            'used_by': [{'id': o, 'name': self.community_name(o), 'weight': w} for o, w in used_by.most_common()],
            'external_files': [{'file': f, 'weight': w} for f, w in external_files.most_common(20)],
        }

    def path(self, source, target):
        a, b = self.resolve(source), self.resolve(target)
        base = {**self.context(), 'from': self.brief(a), 'to': self.brief(b)}
        if a['id'] == b['id']:
            return {**base, 'found': True, 'length': 0, 'steps': [{'node': self.brief(a), 'via': None}]}
        previous = {a['id']: None}
        frontier = [a['id']]
        for _ in range(MAX_PATH):
            following = []
            for current in frontier:
                for other, kind, direction in self.undirected.get(current, []):
                    if other not in previous:
                        previous[other] = (current, kind, direction)
                        following.append(other)
            if b['id'] in previous:
                break
            frontier = following
            if not frontier:
                break
        if b['id'] not in previous:
            return {**base, 'found': False, 'length': None, 'steps': [],
                    'message': f'no hay un camino de {MAX_PATH} pasos o menos entre los dos nodos'}
        chain = []
        current = b['id']
        while previous[current] is not None:
            before, kind, direction = previous[current]
            chain.append({'node': self.brief(self.nodes[current]), 'via': {'kind': kind, 'direction': direction}})
            current = before
        chain.append({'node': self.brief(a), 'via': None})
        chain.reverse()
        return {**base, 'found': True, 'length': len(chain) - 1, 'steps': chain}

    def descendants(self, n):
        found, stack = [], [n['id']]
        while stack:
            for child in self.children[stack.pop()]:
                found.append(child['id'])
                stack.append(child['id'])
        return found

    def impact(self, ref, depth=3):
        n = self.resolve(ref)
        depth = clamp_int(depth, 3, 1, 10, 'depth')
        seeds = [n['id']] + self.descendants(n)
        distance = {s: 0 for s in seeds}
        reason = {}
        frontier = seeds
        for level in range(1, depth + 1):
            following = []
            for current in frontier:
                for kind in DEPENDENCY_KINDS:
                    for other, _ in self.inc[kind].get(current, []):
                        if other not in distance:
                            distance[other] = level
                            reason[other] = (kind, current)
                            following.append(other)
            frontier = following
            if not frontier:
                break
        levels = []
        files = {}
        for level in range(1, depth + 1):
            members = sorted((i for i, d in distance.items() if d == level), key=lambda i: (-self.nodes[i]['deg'], i))
            if not members:
                continue
            for i in members:
                files.setdefault(self.nodes[i]['file'], level)
            levels.append({
                'distance': level, 'count': len(members),
                'nodes': [self.brief(self.nodes[i], via=reason[i][0], depends_on=self.nodes[reason[i][1]]['name']) for i in members[:MAX_LIST]],
            })
        return {
            **self.context(), 'target': self.brief(n), 'depth': depth, 'total': len(distance) - len(seeds),
            'levels': levels, 'files': [{'file': f, 'distance': d} for f, d in sorted(files.items(), key=lambda x: (x[1], x[0]))],
        }

    def module_of(self, i):
        n = self.nodes[i]
        return self.file_node.get(n['file'], n)

    def used(self, i):
        return any(self.inc[k].get(i) for k in USAGE_KINDS)

    def tested(self, n):
        return any(self.inc['tests'].get(i) for i in [n['id']] + self.descendants(n))

    def public(self, n, has_vis):
        if has_vis:
            return n.get('vis') == 'public'
        return not n['name'].rsplit('.', 1)[-1].startswith('_')

    def outside_fan_in(self, n):
        sources = set()
        for kind in USAGE_KINDS:
            if kind == 'tests':
                continue
            for other, _ in self.inc[kind].get(n['id'], []):
                if self.nodes[other]['file'] != n['file']:
                    sources.add(self.nodes[other]['file'])
        return len(sources)

    def find_module(self, rel):
        rel = rel.replace('\\', '/').removeprefix('./')
        rel = os.path.normpath(rel).replace(os.sep, '/') if rel else rel
        if rel in self.file_node:
            return self.file_node[rel]
        stem, ext = os.path.splitext(rel)
        candidates = [stem + e for e in ('.ts', '.tsx', '.js', '.mjs', '.cjs', '.py')] + [rel + '/index.ts', rel + '/index.js']
        for prefix in ('dist/', 'lib/', 'build/', 'out/'):
            if stem.startswith(prefix) or ('/' + prefix) in stem:
                swapped = stem.replace(prefix, 'src/', 1)
                candidates += [swapped + e for e in ('.ts', '.tsx', '.js', '.mjs')]
        for c in candidates:
            if c in self.file_node:
                return self.file_node[c]
        return None

    def python_target(self, base, spec):
        module, _, attr = spec.strip().partition(':')
        path = module.strip().replace('.', '/')
        options = [f'{path}.py', f'{path}/__init__.py', f'src/{path}.py', f'src/{path}/__init__.py']
        for option in options:
            rel = f'{base}/{option}' if base else option
            m = self.file_node.get(rel) or next((n for f, n in sorted(self.file_node.items()) if f.endswith('/' + option)), None)
            if m:
                attr = attr.strip().split('[')[0].strip()
                target = self.by_key.get(f"f:{m['file']}:{attr}") or self.by_key.get(f"c:{m['file']}:{attr}")
                return target or m
        return None

    def manifest_entries(self):
        root = self.source_root()
        if not root:
            return []
        files = {f for f in self.file_node if f.rsplit('/', 1)[-1] in MANIFESTS}
        files |= {n['file'] for n in self.nodes if n['kind'] == 'package' and n['file'].rsplit('/', 1)[-1] in MANIFESTS}
        out = []
        for rel in sorted(f for f in files if not is_test(f))[:60]:
            text = read_text(root, rel, 1024 * 1024)
            if text is None:
                continue
            base = rel.rsplit('/', 1)[0] if '/' in rel else ''
            name = rel.rsplit('/', 1)[-1]
            try:
                out.extend(self.parse_manifest(name, base, rel, text))
            except (ValueError, TypeError, AttributeError, KeyError):
                continue
        return out

    def parse_manifest(self, name, base, rel, text):
        found = []

        def js(kind, label, target):
            if isinstance(target, str) and target:
                path = f'{base}/{target}' if base else target
                found.append((kind, label, target, rel, self.find_module(path)))

        if name == 'package.json':
            data = json.loads(text)
            if not isinstance(data, dict):
                return []
            pkg = data.get('name') or base or 'package'
            bins = data.get('bin')
            if isinstance(bins, str):
                js('bin', pkg, bins)
            elif isinstance(bins, dict):
                for label, target in sorted(bins.items()):
                    js('bin', label, target)
            for field in ('main', 'module'):
                js('library', pkg, data.get(field))
            if isinstance(data.get('exports'), str):
                js('library', pkg, data['exports'])
        elif name == 'pyproject.toml':
            import tomllib
            data = tomllib.loads(text)
            project = data.get('project') or {}
            groups = [project.get('scripts'), project.get('gui-scripts'), ((data.get('tool') or {}).get('poetry') or {}).get('scripts')]
            for group in groups:
                for label, spec in sorted((group or {}).items()):
                    spec = spec.get('callable') if isinstance(spec, dict) else spec
                    if isinstance(spec, str) and ':' in spec:
                        found.append(('script', label, spec, rel, self.python_target(base, spec)))
        elif name in ('setup.cfg', 'setup.py'):
            if 'console_scripts' in text or 'gui_scripts' in text:
                for label, spec in re.findall(r'''["']?([\w.-]+)\s*=\s*([\w.]+:[\w.]+)''', text):
                    found.append(('script', label, spec, rel, self.python_target(base, spec)))
        elif name == 'Cargo.toml':
            import tomllib
            data = tomllib.loads(text)
            for item in data.get('bin') or []:
                if isinstance(item, dict) and isinstance(item.get('path'), str):
                    js('bin', item.get('name') or item['path'], item['path'])
        return found

    def entry_points(self):
        items, seen = [], set()
        for kind, label, target, manifest, n in self.manifest_entries():
            if n is not None and n['key'] in seen:
                continue
            item = {'kind': kind, 'name': label, 'target': target, 'manifest': manifest}
            if n is not None:
                seen.add(n['key'])
                item['node'] = self.mini(n)
            items.append(item)
        for n in self.nodes:
            if n['key'] in seen or self.is_test_node(n):
                continue
            short = n['name'].rsplit('.', 1)[-1]
            if CONFIG_RE.search(n['file']) or BUILD_RE.search(n['file']):
                continue
            if (n['kind'] in ('function', 'method') and short == 'main') or (n['kind'] == 'module' and n['name'] in ('__main__.py', 'manage.py')):
                seen.add(n['key'])
                items.append({'kind': 'main', 'name': n['name'], 'target': f"{n['file']}:{n['line']}", 'node': self.mini(n)})
        order = {'bin': 0, 'script': 1, 'main': 2, 'library': 3}
        items.sort(key=lambda x: (order.get(x['kind'], 9), (x.get('node') or {}).get('file', ''), x['name']))
        return items

    def endpoint_items(self):
        items, covered = [], set()
        for n in self.nodes:
            if n['kind'] != 'endpoint':
                continue
            route = n.get('route') or n['name']
            handlers = [self.nodes[i] for i, _ in sorted(self.out['handles'].get(n['id'], []))]
            callers = sorted({i for k in ('http', 'rpc') for i, _ in self.inc[k].get(n['id'], [])},
                             key=lambda i: (-self.nodes[i]['deg'], i))
            covered.update(h['id'] for h in handlers)
            items.append(self.endpoint_item(n, route, handlers, callers))
        for n in self.nodes:
            if n.get('route') and n['kind'] != 'endpoint' and n['id'] not in covered:
                items.append(self.endpoint_item(None, n['route'], [n], []))
        items.sort(key=lambda x: (x['path'], x['method'], x['handlers'][0]['file'] if x['handlers'] else ''))
        return items

    def endpoint_item(self, n, route, handlers, callers):
        method, _, path = route.partition(' ') if ' ' in route else ('', '', route)
        item = {'route': route, 'method': method.upper(), 'path': path or route}
        if n is not None:
            item.update(key=n['key'], file=n['file'], line=n['line'])
        else:
            item.update(file=handlers[0]['file'], line=handlers[0]['line'])
        item['handlers'] = [self.mini(h, **({'sig': h['sig']} if h.get('sig') else {})) for h in handlers[:5]]
        item['callers_total'] = len(callers)
        item['callers'] = [self.mini(self.nodes[i]) for i in callers[:10]]
        return item

    def untested_public(self):
        if not self.inc['tests'] and not any(n.get('test') for n in self.nodes):
            return [], 'no tests in this analysis (re-analyze including tests to measure coverage)'
        has_vis = any(n.get('vis') for n in self.nodes)
        items = []
        for n in self.nodes:
            if n['kind'] not in SYMBOL_KINDS or self.is_test_node(n) or not self.public(n, has_vis):
                continue
            if CONFIG_RE.search(n['file']) or BUILD_RE.search(n['file']):
                continue
            if n['kind'] == 'method' and n['name'].rsplit('.', 1)[-1].startswith('__'):
                continue
            if self.tested(n):
                continue
            items.append((self.outside_fan_in(n), n))
        items.sort(key=lambda x: (-x[0], -x[1]['deg'], x[1]['id']))
        note = None if has_vis else 'visibility unknown in this graph: public = name without leading underscore'
        return [self.mini(n, fan_in=f, **({'vis': n['vis']} if n.get('vis') else {})) for f, n in items], note

    def import_cycles(self):
        adj = defaultdict(set)
        for a, pairs in self.out['import'].items():
            fa = self.nodes[a]['file']
            if fa not in self.file_node:
                continue
            for b, _ in pairs:
                fb = self.nodes[b]['file']
                if fb != fa and fb in self.file_node:
                    adj[fa].add(fb)
        graph = {k: sorted(v) for k, v in adj.items()}
        cycles = []
        for comp in strongly_connected(graph):
            if len(comp) < 2:
                continue
            members = set(comp)
            start = min(comp)
            cycles.append({'size': len(comp), 'files': sorted(comp)[:15], 'more': max(0, len(comp) - 15),
                           'example': cycle_path(graph, start, members)})
        cycles.sort(key=lambda c: (-c['size'], c['files'][0]))
        return cycles

    def identifier_counts(self):
        with self.lock:
            if self.identifiers is not False:
                return self.identifiers
        root = self.source_root()
        counts = None
        if root:
            counts, total = Counter(), 0
            for rel, n in sorted(self.file_node.items()):
                if n['kind'] != 'module':
                    continue
                text = read_text(root, rel, 4 * 1024 * 1024)
                if text is None:
                    continue
                total += len(text)
                if total > MAX_SCAN_BYTES:
                    counts = None
                    break
                counts.update(IDENT_RE.findall(text))
        with self.lock:
            self.identifiers = counts
        return counts

    def dead_code(self):
        has_vis = any(n.get('vis') for n in self.nodes)
        mentions = self.identifier_counts()
        definitions = Counter(n['name'].rsplit('.', 1)[-1] for n in self.nodes if n['kind'] in SYMBOL_KINDS)
        called_names = set()
        functions_by_ext, with_callers = Counter(), Counter()
        for n in self.nodes:
            if n['kind'] in ('function', 'method'):
                ext = os.path.splitext(n['file'])[1].lower()
                functions_by_ext[ext] += 1
                if self.inc['call'].get(n['id']) or self.inc['tests'].get(n['id']):
                    with_callers[ext] += 1
                    called_names.add(n['name'].rsplit('.', 1)[-1])
        unsupported = {e for e, c in functions_by_ext.items() if c >= 20 and with_callers[e] < 0.03 * c}
        points = self.entry_points()
        entries = {x['node']['key'] for x in points if x.get('node')}
        library = any(x['kind'] == 'library' for x in points) or any(n['kind'] == 'package' for n in self.nodes)
        barrels = {f for f in self.file_node if f.rsplit('/', 1)[-1] in BARRELS}
        exported = set()
        for f in barrels:
            for b, _ in self.out['import'].get(self.file_node[f]['id'], []):
                exported.add(self.nodes[b]['file'])
        items = []
        for n in self.nodes:
            if n['kind'] not in SYMBOL_KINDS or self.is_test_node(n) or n['key'] in entries or n.get('route') or n.get('table'):
                continue
            short = n['name'].rsplit('.', 1)[-1]
            ext = os.path.splitext(n['file'])[1].lower()
            if CONFIG_RE.search(n['file']) or BUILD_RE.search(n['file']):
                continue
            if ext in unsupported or short in PROTOCOL_NAMES or (short.startswith('__') and short.endswith('__')) or short.lower().startswith('test'):
                continue
            if self.used(n['id']) or any(self.used(i) for i in self.descendants(n)):
                continue
            if n['kind'] == 'method' and short in called_names:
                continue
            if mentions is not None and mentions[short] > definitions[short]:
                continue
            parent = self.nodes[n['parent']] if 'parent' in n else None
            if parent is not None and parent['kind'] == 'class' and (self.out['inherits'].get(parent['id']) or self.inc['inherits'].get(parent['id'])
                                                                     or BASES_RE.search(parent.get('sig') or '')):
                continue
            private = n.get('vis') in ('private', 'internal') if has_vis else short.startswith('_')
            public = not private and (n.get('vis') in (None, 'public', 'protected'))
            if public and (n['file'] in barrels or n['file'] in exported or (library and ext == '.go')):
                continue
            if private:
                confidence, reason = 'high', 'private and never referenced'
            elif public and library:
                confidence, reason = 'low', 'public in a library: may be external API'
            else:
                confidence, reason = 'medium', 'no references found in the project'
            start, end = self.span(n)
            items.append((confidence, (end or start) - start + 1, n, reason))
        rank = {'high': 0, 'medium': 1, 'low': 2}
        items.sort(key=lambda x: (rank[x[0]], -x[1], x[2]['id']))
        note = 'static analysis cannot see reflection, dynamic dispatch, decorators or external callers; verify before deleting'
        if mentions is None:
            note += '; source not available, so names mentioned only in text were not checked'
        if unsupported:
            note += f"; skipped {', '.join(sorted(unsupported))} (call graph not extracted)"
        return [self.mini(n, confidence=c, reason=r, lines=size) for c, size, n, r in items], note

    def hotspots(self):
        sources = defaultdict(set)
        for e in self.graph['edges']:
            if e['kind'] not in USAGE_KINDS or e['kind'] == 'tests':
                continue
            a, b = self.nodes[e['a']], self.nodes[e['b']]
            if a['file'] != b['file'] and a['kind'] != 'doc' and not self.is_test_node(a) and b['file'] in self.file_node:
                sources[b['file']].add(a['file'])
        has_churn = any(n.get('churn') for n in self.file_node.values())
        items = []
        for f, users in sources.items():
            m = self.file_node[f]
            if m['kind'] != 'module' or self.is_test_node(m):
                continue
            churn = m.get('churn') or 0
            score = len(users) * churn if has_churn else len(users)
            if score <= 0:
                continue
            item = {'file': f, 'fan_in': len(users), 'score': score, 'community': self.community_name(m['c'])}
            for field in ('churn', 'last', 'authors'):
                if m.get(field):
                    item[field] = m[field]
            items.append(item)
        items.sort(key=lambda x: (-x['score'], -x['fan_in'], x['file']))
        return items, ('fan_in x churn (commits)' if has_churn else 'fan_in only (no git history in this analysis)')

    def layers(self):
        weights = Counter()
        for e in self.graph['edges']:
            if e['kind'] not in LAYER_KINDS:
                continue
            a, b = self.nodes[e['a']], self.nodes[e['b']]
            if a['c'] != b['c'] and a['kind'] != 'doc' and not self.is_test_node(a) and not self.is_test_node(b):
                weights[(a['c'], b['c'])] += e['w']
        graph = defaultdict(list)
        for (a, b), w in sorted(weights.items()):
            if w >= 2 and w >= 2 * weights.get((b, a), 0):
                graph[a].append(b)
        for c in self.communities:
            graph.setdefault(c, [])
        comps = strongly_connected(dict(graph))
        owner = {c: k for k, comp in enumerate(comps) for c in comp}
        deps = {k: sorted({owner[b] for c in comp for b in graph[c] if owner[b] != k}) for k, comp in enumerate(comps)}
        level = {}
        for k in range(len(comps)):
            level[k] = max((level[d] for d in deps[k]), default=-1) + 1
        rows = defaultdict(list)
        for k, comp in enumerate(comps):
            for c in sorted(comp):
                rows[level[k]].append({'id': c, 'name': self.community_name(c), 'size': self.communities[c]['size'],
                                       'depends_on': sorted({self.community_name(b) for b in graph[c] if owner[b] != k}),
                                       **({'cycle_with': sorted(self.community_name(o) for o in comp if o != c)} if len(comp) > 1 else {})})
        return [{'level': lv, 'communities': rows[lv]} for lv in sorted(rows)]

    def architecture(self, section=None, limit=None, offset=0):
        if section not in (None, '') and section not in SECTIONS:
            raise InvalidInput(f'sección inválida «{section}»: usa {", ".join(SECTIONS)}')
        builders = {
            'entry_points': lambda: (self.entry_points(), None),
            'endpoints': lambda: (self.endpoint_items(), None),
            'untested_public': self.untested_public,
            'cycles': lambda: (self.import_cycles(), 'import cycles between files (strongly connected components)'),
            'dead_code': self.dead_code,
            'hotspots': self.hotspots,
            'layers': lambda: (self.layers(), 'level 0 = foundation: depends on no other community; higher levels build on lower ones'),
        }
        result = {**self.context()}
        for name in ([section] if section else SECTIONS):
            items, note = builders[name]()
            if section:
                part = page(items, limit, offset, SECTION_LIMITS[name])
            else:
                part = {'total': len(items), 'items': items[:SECTION_LIMITS[name]]}
            if note:
                part['note'] = note
            result[name] = part
        return result

    def dependencies(self, name=None, limit=50, offset=0):
        packages = [n for n in self.nodes if n['kind'] == 'package']
        users = {n['id']: sorted({self.nodes[i]['file'] for i, _ in self.inc['depends'].get(n['id'], [])}) for n in packages}

        def item(n):
            files = users[n['id']]
            comms = Counter(self.file_node[f]['c'] for f in files if f in self.file_node)
            return {'key': n['key'], 'name': n['name'], 'ecosystem': n.get('ecosystem'), 'version': n.get('version') or '',
                    'declared': bool(n.get('version')) or n['file'].rsplit('/', 1)[-1] in MANIFESTS or not files,
                    'file': n['file'], 'line': n['line'], 'users': len(files),
                    'communities': [self.community_name(c) for c, _ in comms.most_common(3)]}

        base = {**self.context()}
        if not packages:
            base['note'] = 'this graph has no dependency nodes (manifests not found or analyzed with an older version)'
        if name not in (None, ''):
            if not isinstance(name, str) or len(name) > 300:
                raise InvalidInput('el nombre de la dependencia no es válido')
            wanted_name = name.strip().lower()
            matches = [n for n in packages if wanted_name in (n['key'].lower(), n['name'].lower(), f"{n.get('ecosystem')}:{n['name']}".lower())]
            if not matches:
                matches = [n for n in packages if wanted_name in n['name'].lower()]
            if not matches:
                raise NotFound(f'no encontré la dependencia «{name}» en el proyecto {self.project}')
            n = max(matches, key=lambda m: (len(users[m['id']]), -m['id']))
            files = users[n['id']]
            rows = [{'file': f, 'community': self.community_name(self.file_node[f]['c']) if f in self.file_node else None} for f in files]
            return {**base, 'package': item(n), 'used_by': page(rows, limit, offset, 50),
                    'others': [m['key'] for m in matches if m is not n][:10]}
        items = sorted((item(n) for n in packages), key=lambda x: (-x['users'], x['name'], x['key']))
        return {**base, 'ecosystems': dict(sorted(Counter(n.get('ecosystem') or '?' for n in packages).items())),
                'undeclared': sum(1 for x in items if not x['declared']), 'packages': page(items, limit, offset, 50)}

    def endpoints(self, limit=50, offset=0, method=None):
        items = self.endpoint_items()
        if method not in (None, ''):
            items = [x for x in items if x['method'] == str(method).upper()]
        return {**self.context(), 'endpoints': page(items, limit, offset, 50)}

    def variables(self, name=None, limit=50, offset=0):
        items = []
        for n in self.nodes:
            if n['kind'] != 'variable':
                continue
            if name not in (None, '') and str(name).lower() not in n['name'].lower():
                continue
            sources = [self.nodes[i] for i, _ in sorted(self.inc['env'].get(n['id'], []))]
            defined = sorted({(m['file'], m['line']) for m in sources if self.defines(m)} | {(n['file'], n['line'])})
            used = sorted((m for m in sources if not self.defines(m)), key=lambda m: (-m['deg'], m['id']))
            items.append({'key': n['key'], 'name': n['name'], 'file': n['file'], 'line': n['line'],
                          'defined_in': [{'file': f, 'line': ln} for f, ln in defined[:10]],
                          'used_by_total': len(used), 'used_by': [self.mini(m) for m in used[:10]]})
        items.sort(key=lambda x: (-x['used_by_total'], x['name']))
        result = {**self.context(), 'variables': page(items, limit, offset, 50)}
        if not any(n['kind'] == 'variable' for n in self.nodes):
            result['note'] = 'this graph has no environment/config variable nodes'
        return result


def page(items, limit, offset, default):
    limit = clamp_int(limit, default, 1, MAX_PAGE, 'limit')
    offset = clamp_int(offset, 0, 0, 10 ** 7, 'offset')
    return {'total': len(items), 'offset': offset, 'limit': limit, 'items': items[offset:offset + limit]}


def read_text(root, rel, limit):
    base = os.path.realpath(root)
    path = os.path.realpath(os.path.join(base, rel))
    if not path.startswith(base + os.sep) or not os.path.isfile(path):
        return None
    try:
        if os.path.getsize(path) > limit:
            return None
        with open(path, 'rb') as f:
            return f.read().replace(b'\r\n', b'\n').decode('utf-8', errors='replace')
    except OSError:
        return None


def strongly_connected(graph):
    index, low, stack, on, out = {}, {}, [], set(), []
    counter = 0
    for start in sorted(graph):
        if start in index:
            continue
        index[start] = low[start] = counter
        counter += 1
        stack.append(start)
        on.add(start)
        work = [(start, iter(graph.get(start, ())))]
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on.add(w)
                    work.append((w, iter(graph.get(w, ()))))
                    advanced = True
                    break
                if w in on:
                    low[v] = min(low[v], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                out.append(sorted(comp))
    return out


def cycle_path(graph, start, members):
    previous = {}
    queue = deque()
    for nxt in graph.get(start, ()):
        if nxt in members and nxt not in previous:
            previous[nxt] = start
            queue.append(nxt)
    while queue:
        current = queue.popleft()
        if current == start:
            break
        for nxt in graph.get(current, ()):
            if nxt in members and nxt not in previous:
                previous[nxt] = current
                queue.append(nxt)
    if start not in previous:
        return []
    chain, current = [start], previous[start]
    while current != start and len(chain) < 30:
        chain.append(current)
        current = previous[current]
    chain.append(start)
    chain.reverse()
    return chain


def changes(project=None, since=None):
    name = resolve_project(project)
    index = load_index(name)
    versions = [h['v'] for h in index.history]
    since = store.parse_version(since)
    if since is None:
        earlier = [v for v in versions if v < index.version]
        since = earlier[-1] if earlier else None
    elif since not in versions:
        raise NotFound(f'el proyecto «{name}» no tiene la versión v{since}')
    empty = {'added': 0, 'modified': 0, 'removed': 0}
    if since is None:
        return {**index.context(), 'from_version': None, 'to_version': index.version, 'counts': empty,
                'added': [], 'modified': [], 'removed': [], 'message': 'solo hay una versión: todavía no hay cambios que comparar'}
    old = store.load_version(name, since)
    if old is None:
        raise NotFound(f'no se pudo leer la versión v{since} de «{name}»')
    diff = store.compare(index.nodes, old['nodes'])
    return {
        **index.context(),
        'from_version': since,
        'to_version': index.version,
        'counts': {k: len(v) for k, v in diff.items()},
        'added': [index.brief(index.by_key[k]) for k in diff['added'][:MAX_CHANGES]],
        'modified': [index.brief(index.by_key[k]) for k in diff['modified'][:MAX_CHANGES]],
        'removed': diff['removed'][:MAX_CHANGES],
    }


def overview(project=None):
    return load_index(project).overview()


def search(text, project=None, kind=None, limit=20, offset=0):
    return load_index(project).search(text, kind, limit, offset)


def node(ref, project=None):
    return load_index(project).node(ref)


def file(path, project=None):
    return load_index(project).file(path)


def community(ref, project=None):
    return load_index(project).community(ref)


def path(source, target, project=None):
    return load_index(project).path(source, target)


def impact(ref, project=None, depth=3):
    return load_index(project).impact(ref, depth)


def report(project=None):
    return export_markdown(load_index(project).graph)



def architecture(project=None, section=None, limit=None, offset=0):
    return load_index(project).architecture(section, limit, offset)


def dependencies(project=None, name=None, limit=50, offset=0):
    return load_index(project).dependencies(name, limit, offset)


def endpoints(project=None, limit=50, offset=0, method=None):
    return load_index(project).endpoints(limit, offset, method)


def variables(project=None, name=None, limit=50, offset=0):
    return load_index(project).variables(name, limit, offset)
