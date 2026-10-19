import os
import threading
from collections import Counter, defaultdict

from . import store
from .analyze import export_markdown
from .errors import InvalidInput, NotFound

KINDS = ('module', 'class', 'function', 'method', 'doc')
DEPENDENCY_KINDS = ('import', 'call', 'inherits', 'ref')
RELATIONS = (
    ('imports', 'import', 'out'), ('imported_by', 'import', 'in'),
    ('calls', 'call', 'out'), ('called_by', 'call', 'in'),
    ('inherits', 'inherits', 'out'), ('inherited_by', 'inherits', 'in'),
    ('refs', 'ref', 'out'), ('referenced_by', 'ref', 'in'),
    ('loads', 'loads', 'out'), ('loaded_by', 'loads', 'in'),
)
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
        for field in ('route', 'table', 'status'):
            if n.get(field):
                item[field] = n[field]
        item.update(extra)
        return item

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
        return {
            **self.context(),
            'date': entry.get('date'),
            'origin': entry.get('origin'),
            'commit': entry.get('commit'),
            'versions': len(self.history),
            'stats': {k: self.graph['stats'].get(k) for k in ('files', 'nodes', 'edges', 'communities', 'kinds', 'edge_kinds', 'tests', 'excluded', 'warnings_total')},
            'communities': communities,
            'top_nodes': [self.brief(n) for n in sorted(self.nodes, key=lambda n: (-n['deg'], n['id']))[:20]],
            'routes': [self.brief(n) for n in sorted((n for n in self.nodes if n.get('route')), key=lambda n: n['route'].split(' ', 1)[-1])],
            'tables': [self.brief(n) for n in sorted((n for n in self.nodes if n.get('table')), key=lambda n: n['table'])],
        }

    def search(self, text, kind=None, limit=20):
        if not isinstance(text, str) or not text.strip():
            raise InvalidInput('la búsqueda está vacía')
        if len(text) > 300:
            raise InvalidInput('la búsqueda es demasiado larga')
        if kind not in (None, '') and kind not in KINDS:
            raise InvalidInput(f'tipo inválido «{kind}»: usa {", ".join(KINDS)}')
        limit = clamp_int(limit, 20, 1, 200, 'limit')
        phrase = ' '.join(text.lower().split())
        terms = phrase.split()
        scored = []
        for n in self.nodes:
            if kind and n['kind'] != kind:
                continue
            name = n['name'].lower()
            haystack = ' '.join((name, n['file'].lower(), n['key'].lower(), (n.get('route') or '').lower(), (n.get('table') or '').lower()))
            if not all(t in haystack for t in terms):
                continue
            if name == phrase:
                score = 100
            elif name.rsplit('.', 1)[-1] == phrase:
                score = 90
            elif name.startswith(phrase):
                score = 70
            elif phrase in name:
                score = 50
            else:
                score = 10 + 10 * sum(t in name for t in terms)
            scored.append((score, n['deg'], -n['id'], n))
        scored.sort(key=lambda s: s[:3], reverse=True)
        return {**self.context(), 'query': text, 'kind': kind or None, 'total': len(scored),
                'results': [self.brief(s[3]) for s in scored[:limit]]}

    def node(self, ref):
        n = self.resolve(ref)
        parent = self.nodes[n['parent']] if 'parent' in n else None
        result = {
            **self.context(),
            'node': self.brief(n, hash=n.get('hash')),
            'status': n.get('status') or 'unchanged',
            'community': {'id': n['c'], 'name': self.community_name(n['c'])},
            'parent': self.brief(parent) if parent else None,
            'children': [self.brief(c) for c in sorted(self.children[n['id']], key=lambda c: c['line'])][:MAX_LIST],
        }
        for label, kind, direction in RELATIONS:
            result[label] = self.related(n, kind, direction)
        return result

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


def search(text, project=None, kind=None, limit=20):
    return load_index(project).search(text, kind, limit)


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
