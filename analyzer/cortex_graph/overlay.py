import contextlib
import json
import logging
import os
import re
import threading
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone

from . import brain, config as project_config, store
from .common import MAX_FILE_BYTES, digest
from .errors import CortexError, InvalidInput, NotFound

try:
    import fcntl
except ImportError:
    fcntl = None
try:
    import msvcrt
except ImportError:
    msvcrt = None

log = logging.getLogger('cortex.overlay')

LOG = 'agente.jsonl'
LOCK = 'agente.lock'
ORIGINS = ('agent', 'ai')
NEW_KINDS = ('component', 'flow')
NODE_KINDS = ('component', 'flow', 'module', 'class', 'function', 'method', 'doc', 'package', 'variable', 'endpoint', 'topic', 'concept',
              'person', 'event')
KIND_ALIASES = {
    'componente': 'component', 'componentes': 'component', 'components': 'component', 'servicio': 'component', 'service': 'component',
    'flujo': 'flow', 'flujos': 'flow', 'flows': 'flow', 'proceso': 'flow', 'process': 'flow', 'archivo': 'module', 'file': 'module',
    'clase': 'class', 'funcion': 'function', 'función': 'function', 'metodo': 'method', 'método': 'method', 'documento': 'doc',
    'paquete': 'package', 'dependencia': 'package', 'ruta': 'endpoint', 'tópico': 'topic', 'topico': 'topic', 'cola': 'topic',
    'concepto': 'concept', 'tema': 'concept', 'persona': 'person', 'evento': 'event',
}
EDGE_KINDS = ('uses', 'step', 'contains', 'import', 'call', 'inherits', 'ref', 'loads', 'tests', 'http', 'rpc', 'handles', 'env', 'data',
              'event', 'depends', 'mentions', 'links', 'participant', 'about', 'from', 'related', 'attends')
CONTENT_KINDS = {'conversation', 'person', 'concept', 'memory', 'event'}
MAX_BATCH = 500
MAX_ID = 200
MAX_NAME = 120
MAX_SUMMARY = 2000
MAX_LABEL = 200
MAX_TAGS = 20
MAX_TAG = 40
MAX_STEPS = 100
MAX_CONTAINS = 200
MAX_PATH = 500
MAX_SOURCE = 80
MAX_NODES = 20000
MAX_EDGES = 60000
MAX_LINE = 10 ** 7
MAX_PLACEHOLDERS = 5000
MAX_LIST = 1000
GUIDE_LIMIT = 40
SECRET_NAMES = re.compile(r'(^|/)(\.env[\w.-]*|[\w.-]*\.(pem|key|p12|pfx|keystore|jks)|id_rsa[\w.]*|credentials[\w.-]*)$', re.I)
SLUG_RE = re.compile(r'[^a-z0-9]+')

thread_guard = threading.Lock()
thread_locks = {}


def now_stamp():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def plain(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(text or '')) if not unicodedata.combining(c)).casefold()


def slugify(text):
    return SLUG_RE.sub('-', plain(text)).strip('-')[:80] or 'nodo'


def log_path(project):
    return os.path.join(store.data_dir(), store.slug(project), LOG)


def stamp(project):
    if not project:
        return None
    try:
        st = os.stat(log_path(project))
    except OSError:
        return None
    return [st.st_size, st.st_mtime_ns]


@contextlib.contextmanager
def locked(project):
    folder = store.project_dir(project)
    path = os.path.join(folder, LOCK)
    with thread_guard:
        guard = thread_locks.setdefault(path, threading.Lock())
    with guard, open(path, 'a+b') as fh:
        if fcntl:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        elif msvcrt:
            fh.seek(0)
            while True:
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    continue
        try:
            yield folder
        finally:
            if fcntl:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            elif msvcrt:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


def read_ops(path):
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []
    ops = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            op = json.loads(line)
        except ValueError:
            continue
        if isinstance(op, dict) and isinstance(op.get('id'), str) and op.get('op') in ('node', 'edge', 'note', 'remove'):
            ops.append(op)
    return ops


def append(path, ops):
    if not ops:
        return
    data = ''.join(json.dumps(op, ensure_ascii=False, sort_keys=True) + '\n' for op in ops)
    prefix = ''
    try:
        with open(path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            if f.tell():
                f.seek(-1, os.SEEK_END)
                prefix = '' if f.read(1) == b'\n' else '\n'
    except FileNotFoundError:
        pass
    with open(path, 'a', encoding='utf-8', newline='\n') as f:
        f.write(prefix + data)
        f.flush()
        os.fsync(f.fileno())


def fold(ops):
    nodes, edges, notes = {}, {}, {}
    for op in ops:
        oid, kind = op['id'], op['op']
        fields = {k: v for k, v in op.items() if k != 'op'}
        if kind == 'node':
            nodes[oid] = {**nodes.get(oid, {}), **fields}
            nodes[oid].setdefault('created', op.get('at'))
        elif kind == 'edge':
            edges[oid] = {**edges.get(oid, {}), **fields}
        elif kind == 'note':
            notes[oid] = {**notes.get(oid, {}), **fields}
        elif kind == 'remove':
            if oid in nodes:
                nodes.pop(oid)
                for eid in [e for e, meta in edges.items() if oid in (meta.get('a'), meta.get('b'))]:
                    edges.pop(eid)
            edges.pop(oid, None)
            notes.pop(oid, None)
    return {'nodes': nodes, 'edges': edges, 'notes': notes}


def load(project):
    return read_ops(log_path(project)) if project else []


def state_of(project):
    return fold(load(project))


def edge_id(a, kind, b):
    return 'rel:' + digest(f'{a}\0{kind}\0{b}')


def unit_of(nid, meta):
    if meta.get('unit'):
        return meta['unit']
    if not meta.get('file') or meta.get('kind') in CONTENT_KINDS:
        return nid
    return ('d:' if meta.get('kind') in ('doc', 'section') else 'm:') + meta['file']


def skipped_dir(name):
    from .analyze import SKIP_DIR_SUFFIXES, SKIP_DIRS
    return name in SKIP_DIRS or name.endswith(SKIP_DIR_SUFFIXES) or name.startswith('.')


def raw_files(root, exclude=(), limit=MAX_PLACEHOLDERS * 4):
    from .analyze import git_visible
    if not root or not os.path.isdir(root):
        return []
    settings = project_config.load(root)
    exclude = tuple(e.strip('/') for e in tuple(exclude) + tuple(settings.get('exclude') or ()) if e.strip('/'))
    visible = git_visible(root)
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not skipped_dir(d))
        for name in sorted(filenames):
            if name.startswith('.'):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, '/')
            if visible is not None and rel not in visible:
                continue
            if any(rel == e or rel.startswith(e + '/') for e in exclude) or project_config.ignored(settings, rel):
                continue
            out.append(rel)
            if len(out) >= limit:
                return out
    return out


def placeholder_files(root, g, exclude=()):
    added = []
    for rel in raw_files(root, exclude, MAX_PLACEHOLDERS):
        path = os.path.join(root, rel)
        try:
            size = os.path.getsize(path)
            if size <= MAX_FILE_BYTES:
                with open(path, 'rb') as fh:
                    raw = fh.read()
                mark, lines = digest(raw), raw.count(b'\n') + 1
            else:
                mark, lines = digest(f'{rel}|{size}'), None
        except OSError:
            continue
        g.node(f'm:{rel}', kind='module', name=rel.rsplit('/', 1)[-1], file=rel, line=1, hash=mark, end=lines)
        added.append(rel)
    return added


def link_overlay(g, ops, issues, root=None, exclude=()):
    if ops is None:
        return []
    extra = placeholder_files(root, g, exclude) if not g.nodes and root is not None else []
    if not ops:
        return extra
    state = fold(ops)

    def report(message):
        issues.add(LOG, message)

    created = []
    for nid in sorted(state['nodes']):
        op = state['nodes'][nid]
        if nid in g.nodes:
            annotate(g.nodes[nid], op)
            continue
        if op.get('kind') not in NODE_KINDS or not op.get('name'):
            report(f'nodo «{nid}» descartado: falta el tipo o el nombre')
            continue
        file = op.get('file') or ''
        meta = {'kind': op['kind'], 'name': op['name'], 'file': file, 'line': int(op.get('line') or (1 if file else 0)),
                'by': op.get('origin') or 'agent'}
        for field in ('summary', 'tags', 'end'):
            if op.get(field):
                meta[field] = op[field]
        if op.get('source'):
            meta['client'] = op['source']
        g.nodes[nid] = meta
        created.append(nid)
    for nid in created:
        op = state['nodes'][nid]
        hint = op.get('community_hint')
        anchor = op.get('anchor')
        if anchor in g.nodes and anchor != nid:
            g.nodes[nid]['unit'] = unit_of(anchor, g.nodes[anchor])
        elif hint:
            g.nodes[nid]['unit'] = 'g:' + slugify(hint)
    has_parent = {b for (_, b, kind) in g.edges if kind == 'contains'}
    for nid in created:
        parent = state['nodes'][nid].get('parent')
        if not parent:
            continue
        if parent not in g.nodes:
            report(f'«{nid}»: el padre «{parent}» no existe en el grafo; se omitió')
            continue
        g.edge(parent, nid, 'contains')
        has_parent.add(nid)
    made = set(created)
    steps = defaultdict(list)
    for eid in sorted(state['edges']):
        e = state['edges'][eid]
        a, b, kind = e.get('a'), e.get('b'), e.get('kind')
        if kind not in EDGE_KINDS or a == b:
            continue
        missing = [x for x in (a, b) if x not in g.nodes]
        if missing:
            report(f'relación {kind} {a} → {b} descartada: no existe «{missing[0]}»')
            continue
        if kind == 'contains':
            if a not in made:
                report(f'relación contains {a} → {b} descartada: solo un nodo creado por el agente puede contener a otros')
                continue
            if b in has_parent:
                report(f'relación contains {a} → {b} descartada: «{b}» ya tiene padre')
                continue
            has_parent.add(b)
        g.edge(a, b, kind)
        if kind == 'step':
            steps[a].append((int(e.get('order') or 0), b))
        if e.get('label'):
            g.nodes[a].setdefault('rels', []).append({'to': b, 'name': g.nodes[b]['name'], 'kind': kind, 'label': e['label']})
    for nid, items in steps.items():
        g.nodes[nid]['steps'] = [b for _, b in sorted(items)]
    for nid in sorted(state['notes']):
        if nid in g.nodes:
            annotate(g.nodes[nid], state['notes'][nid], nid in made)
        else:
            report(f'nota sobre «{nid}» descartada: el nodo ya no existe')
    for nid in created:
        meta = g.nodes[nid]
        meta['hash'] = digest(json.dumps([meta.get(k) for k in ('kind', 'name', 'summary', 'tags', 'file', 'line', 'end', 'steps', 'rels')],
                                         ensure_ascii=False, sort_keys=True))
    return extra


def annotate(meta, op, own=False):
    if op.get('summary'):
        meta['summary'] = op['summary']
    if op.get('tags'):
        meta['tags'] = list(dict.fromkeys(list(meta['tags']) + list(op['tags']))) if isinstance(meta.get('tags'), list) else list(op['tags'])
    if not own and (op.get('summary') or op.get('tags')):
        meta['noted'] = op.get('origin') or 'agent'


def label(members, g, degree):
    made = [n for n in members if g.nodes[n].get('by')]
    if not made or len(made) * 2 < len(members):
        return None
    hints = Counter(g.nodes[n]['unit'][2:] for n in made if str(g.nodes[n].get('unit', '')).startswith('g:'))
    best = max(made, key=lambda n: (g.nodes[n]['kind'] == 'component', degree[n], n))
    if hints and not any(g.nodes[n]['kind'] == 'component' for n in made):
        return hints.most_common(1)[0][0].replace('-', ' ')[:60]
    return g.nodes[best]['name'][:60]


class Rejected(Exception):
    pass


def text(value, label_, limit, required=False):
    if value is None or value == '':
        if required:
            raise Rejected(f'falta «{label_}»')
        return None
    if not isinstance(value, str):
        raise Rejected(f'«{label_}» debe ser texto')
    from .context import redact
    value = ' '.join(redact(value)[0].split()) if limit <= MAX_NAME else redact(value.strip())[0]
    if not value:
        if required:
            raise Rejected(f'falta «{label_}»')
        return None
    if len(value) > limit:
        raise Rejected(f'«{label_}» supera {limit} caracteres')
    return value


def tag_list(value):
    if value in (None, ''):
        return None
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)) or len(value) > MAX_TAGS:
        raise Rejected(f'«tags» debe ser una lista de hasta {MAX_TAGS} etiquetas')
    out = []
    for t in value:
        if not isinstance(t, str) or not t.strip() or len(t.strip()) > MAX_TAG:
            raise Rejected(f'cada etiqueta debe ser texto de 1 a {MAX_TAG} caracteres')
        out.append(t.strip())
    return list(dict.fromkeys(out)) or None


def integer(value, label_, low=0, high=MAX_LINE):
    if value in (None, ''):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise Rejected(f'«{label_}» debe ser un número entero')
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise Rejected(f'«{label_}» debe ser un número entero') from exc
    if not low <= number <= high:
        raise Rejected(f'«{label_}» fuera de rango ({low}-{high})')
    return number


def kind_of(value, allowed, label_='kind'):
    if not isinstance(value, str) or not value.strip():
        raise Rejected(f'falta «{label_}»')
    key = value.strip().lower()
    key = KIND_ALIASES.get(key, key)
    if key not in allowed:
        raise Rejected(f'tipo «{value}» no permitido: usa {", ".join(allowed)}')
    return key


def rel_path(value):
    value = text(value, 'file', MAX_PATH)
    if value is None:
        return None
    value = value.replace('\\', '/').removeprefix('./')
    if value.startswith('/') or re.match(r'^[A-Za-z]:', value) or '..' in value.split('/'):
        raise Rejected('«file» debe ser una ruta relativa dentro del proyecto')
    return value


def short(item):
    if isinstance(item, dict):
        for key in ('id', 'name', 'a'):
            if isinstance(item.get(key), str):
                return item[key][:80]
    return str(item)[:80]


class Session:
    def __init__(self, project, state, index, origin, source, at):
        self.project, self.state, self.index = project, state, index
        self.origin, self.source, self.at = origin, source, at
        self.ops = []
        self.position = 0
        self.result = {'created': [], 'updated': [], 'annotated': [], 'edges': [], 'flows': [], 'removed': [], 'rejected': []}
        self.names = defaultdict(list)
        for nid in sorted(state['nodes']):
            self.names[plain(state['nodes'][nid].get('name'))].append(nid)

    def stamp_op(self, op):
        op.update(at=self.at, origin=self.origin)
        if self.source:
            op['source'] = self.source
        self.ops.append(op)
        return op

    def reject(self, section, i, item, reason):
        self.result['rejected'].append({'section': section, 'index': i, 'item': short(item), 'reason': reason})

    def known(self, ref):
        return ref in self.state['nodes'] or (self.index is not None and ref in self.index.by_key)

    def resolve(self, ref):
        if isinstance(ref, int) and not isinstance(ref, bool):
            ref = str(ref)
        if not isinstance(ref, str) or not ref.strip() or len(ref) > MAX_PATH:
            return None
        ref = ref.strip()
        if self.known(ref):
            return ref
        hit = self.named(ref)
        if hit:
            return hit
        index = self.index
        if index is None:
            return None
        path = ref.replace('\\', '/').removeprefix('./')
        if path in index.file_node:
            return index.file_node[path]['key']
        found = index.by_name.get(ref) or index.by_name_lower.get(ref.lower())
        if found:
            return index.best(found)['key']
        suffix = [n for f, n in index.file_node.items() if f.endswith('/' + path)]
        if len(suffix) == 1:
            return suffix[0]['key']
        return None

    def named(self, name, kind=None):
        ids = [nid for nid in self.names.get(plain(name), ()) if nid in self.state['nodes']]
        same = [nid for nid in ids if kind is None or self.state['nodes'][nid].get('kind') == kind]
        return same[0] if same else None

    def need(self, ref, label_):
        key = self.resolve(ref)
        if key is None:
            raise Rejected(f'no existe el nodo «{short(ref)}» ({label_}): créalo en «nodes» o usa una clave de search_code')
        return key

    def anchor(self, hint):
        if not hint or self.index is None:
            return None
        key = self.resolve(hint)
        if key and key in self.index.by_key:
            return key
        try:
            c = self.index.find_community(hint)
        except CortexError:
            return None
        members = [n for n in self.index.nodes if n['c'] == c['id'] and n['kind'] in ('module', 'doc') and not n.get('by')]
        return max(members, key=lambda n: (n['deg'], -n['id']))['key'] if members else None

    def node(self, item):
        if not isinstance(item, dict):
            raise Rejected('cada nodo debe ser un objeto')
        nid = text(item.get('id'), 'id', MAX_ID)
        name = text(item.get('name'), 'name', MAX_NAME)
        summary, tags = text(item.get('summary'), 'summary', MAX_SUMMARY), tag_list(item.get('tags'))
        mine = nid in self.state['nodes'] if nid else False
        if nid and not mine and self.index is not None and nid in self.index.by_key and not self.index.by_key[nid].get('by'):
            if not (summary or tags):
                raise Rejected(f'«{nid}» ya existe en el grafo: para anotarlo da «summary» o «tags»')
            self.note(nid, summary, tags)
            return nid
        wanted = KIND_ALIASES.get(str(item.get('kind') or '').strip().lower(), str(item.get('kind') or '').strip().lower()) or None
        if not nid and name:
            nid = self.named(name, wanted)
            mine = nid is not None
        if not mine:
            kind = kind_of(item.get('kind'), NODE_KINDS)
            if not name:
                raise Rejected('falta «name»')
            if not nid:
                nid = f'a:{slugify(name)}'
                same = self.state['nodes'].get(nid)
                if same and same.get('kind') != kind:
                    nid = f'a:{kind}-{slugify(name)}'
                mine = nid in self.state['nodes']
        op = {'op': 'node', 'id': nid}
        if item.get('kind') not in (None, ''):
            op['kind'] = kind_of(item.get('kind'), NODE_KINDS)
        for field, value in (('name', name), ('summary', summary), ('tags', tags), ('file', rel_path(item.get('file'))),
                             ('line', integer(item.get('line'), 'line')), ('end', integer(item.get('end'), 'end'))):
            if value is not None:
                op[field] = value
        if item.get('parent') not in (None, ''):
            op['parent'] = self.need(item['parent'], 'parent')
            if op['parent'] == nid:
                raise Rejected('un nodo no puede ser su propio padre')
        hint = text(item.get('community_hint'), 'community_hint', MAX_NAME)
        if hint:
            op['community_hint'] = hint
            anchor = self.anchor(hint)
            if anchor:
                op['anchor'] = anchor
        contains = item.get('contains') or []
        if not isinstance(contains, (list, tuple)) or len(contains) > MAX_CONTAINS:
            raise Rejected(f'«contains» debe ser una lista de hasta {MAX_CONTAINS} referencias')
        targets = [self.need(ref, 'contains') for ref in contains]
        if not mine and len(self.state['nodes']) >= MAX_NODES:
            raise Rejected(f'el grafo del agente ya tiene {MAX_NODES} nodos')
        self.stamp_op(op)
        self.state['nodes'][nid] = {**self.state['nodes'].get(nid, {}), **op}
        if nid not in self.names[plain(self.state['nodes'][nid].get('name'))]:
            self.names[plain(self.state['nodes'][nid].get('name'))].append(nid)
        self.result['updated' if mine else 'created'].append(nid)
        for target in targets:
            if target != nid:
                self.edge_op(nid, target, 'contains')
        return nid

    def note(self, nid, summary, tags):
        if nid in self.state['nodes']:
            op = {'op': 'node', 'id': nid, **({'summary': summary} if summary else {}), **({'tags': tags} if tags else {})}
            self.stamp_op(op)
            self.state['nodes'][nid].update(op)
            self.result['updated'].append(nid)
            return
        op = self.stamp_op({'op': 'note', 'id': nid, **({'summary': summary} if summary else {}), **({'tags': tags} if tags else {})})
        self.state['notes'][nid] = {**self.state['notes'].get(nid, {}), **op}
        self.result['annotated'].append(nid)

    def edge_op(self, a, b, kind, label_=None, order=None):
        eid = edge_id(a, kind, b)
        if eid not in self.state['edges'] and len(self.state['edges']) >= MAX_EDGES:
            raise Rejected(f'el grafo del agente ya tiene {MAX_EDGES} relaciones')
        op = {'op': 'edge', 'id': eid, 'a': a, 'b': b, 'kind': kind}
        if label_:
            op['label'] = label_
        if order is not None:
            op['order'] = order
        self.stamp_op(op)
        self.state['edges'][eid] = {**self.state['edges'].get(eid, {}), **op}
        self.result['edges'].append({'id': eid, 'a': a, 'b': b, 'kind': kind})
        return eid

    def edge(self, item):
        if not isinstance(item, dict):
            raise Rejected('cada relación debe ser un objeto')
        kind = kind_of(item.get('kind') or 'uses', EDGE_KINDS)
        a, b = self.need(item.get('a'), 'a'), self.need(item.get('b'), 'b')
        if a == b:
            raise Rejected('una relación necesita dos nodos distintos')
        if kind == 'contains' and a not in self.state['nodes']:
            raise Rejected('solo un nodo creado por el agente puede contener a otros (usa «uses» o «related»)')
        return self.edge_op(a, b, kind, text(item.get('label'), 'label', MAX_LABEL), integer(item.get('order'), 'order', 0, 100000))

    def annotation(self, item):
        if not isinstance(item, dict):
            raise Rejected('cada anotación debe ser un objeto')
        target = self.need(item.get('id') or item.get('node'), 'id')
        summary, tags = text(item.get('summary'), 'summary', MAX_SUMMARY), tag_list(item.get('tags'))
        if not (summary or tags):
            raise Rejected('la anotación necesita «summary» o «tags»')
        self.note(target, summary, tags)
        return target

    def flow(self, item):
        if not isinstance(item, dict):
            raise Rejected('cada flujo debe ser un objeto')
        steps = item.get('steps') or []
        if not isinstance(steps, (list, tuple)) or not steps or len(steps) > MAX_STEPS:
            raise Rejected(f'«steps» debe ser una lista de 1 a {MAX_STEPS} nodos')
        keys = []
        for k, ref in enumerate(steps):
            key = self.resolve(ref)
            if key is None:
                self.reject('flows', self.position, ref, f'paso {k + 1} omitido: no existe el nodo «{short(ref)}»')
            else:
                keys.append(key)
        if not keys:
            raise Rejected('ningún paso del flujo existe en el grafo')
        nid = self.node({**{k: v for k, v in item.items() if k not in ('steps', 'kind')}, 'kind': 'flow'})
        if self.state['nodes'][nid].get('kind') != 'flow':
            raise Rejected(f'«{nid}» existe y no es un flujo')
        wanted = set()
        for k, key in enumerate(keys, 1):
            if key == nid:
                continue
            wanted.add(self.edge_op(nid, key, 'step', order=k))
        for eid, e in list(self.state['edges'].items()):
            if e.get('a') == nid and e.get('kind') == 'step' and eid not in wanted:
                self.remove(eid)
        self.result['flows'].append({'id': nid, 'steps': len(wanted)})
        return nid

    def remove(self, ref):
        if not isinstance(ref, str) or not ref.strip():
            raise Rejected('id vacío')
        ref = ref.strip()
        if ref not in self.state['nodes'] and ref not in self.state['edges'] and ref not in self.state['notes']:
            raise Rejected(f'«{short(ref)}» no es una aportación del agente (los nodos del analizador no se borran)')
        self.ops.append({'op': 'remove', 'id': ref, 'at': self.at, 'origin': self.origin})
        if ref in self.state['nodes']:
            self.state['nodes'].pop(ref)
            for eid in [e for e, meta in self.state['edges'].items() if ref in (meta.get('a'), meta.get('b'))]:
                self.state['edges'].pop(eid)
        self.state['edges'].pop(ref, None)
        self.state['notes'].pop(ref, None)
        self.result['removed'].append(ref)


def project_for(project, create=False):
    from . import query
    if project not in (None, ''):
        if not isinstance(project, str) or len(project) > 200:
            raise InvalidInput('el nombre del proyecto no es válido')
        name = store.slug(project)
        if not create and not store.load_history(name)['versions'] and not os.path.exists(log_path(name)):
            raise NotFound(f'no existe el proyecto «{project}»: analízalo con analyze_project o crea su grafo con graph_add')
        return name
    try:
        return query.resolve_project(None)
    except NotFound as exc:
        raise InvalidInput('indica «project»: todavía no hay proyectos (se crea uno nuevo con ese nombre)') from exc


def latest_index(project):
    from . import query
    if not store.load_history(project)['versions']:
        return None
    try:
        return query.load_index(project)
    except CortexError:
        return None


def ensure_project(project):
    folder = store.project_dir(project)
    path = os.path.join(folder, 'historial.json')
    with store.save_lock:
        if not os.path.exists(path):
            store.write_atomic(path, json.dumps({'project': project, 'origin': {'type': 'agent'}, 'versions': []}, ensure_ascii=False, indent=1))


def as_list(value, label_):
    if value in (None, ''):
        return []
    if isinstance(value, dict):
        return [value]
    if not isinstance(value, (list, tuple)):
        raise InvalidInput(f'«{label_}» debe ser una lista')
    return list(value)


def client_name(source):
    if not isinstance(source, str) or not source.strip():
        return None
    return re.sub(r'[^\w .@/+-]+', '', source.strip())[:MAX_SOURCE] or None


def add(project=None, nodes=None, edges=None, annotations=None, flows=None, origin='agent', source=None, rebuild='background', now=None):
    sections = {'nodes': as_list(nodes, 'nodes'), 'flows': as_list(flows, 'flows'), 'edges': as_list(edges, 'edges'),
                'annotations': as_list(annotations, 'annotations')}
    total = sum(len(v) for v in sections.values())
    if not total:
        raise InvalidInput('no hay nada que añadir: pasa nodes, edges, annotations o flows')
    if total > MAX_BATCH:
        raise InvalidInput(f'como mucho {MAX_BATCH} elementos por llamada; divide el lote')
    if origin not in ORIGINS:
        raise InvalidInput('origen inválido')
    name = project_for(project, create=True)
    ensure_project(name)
    index = latest_index(name)
    with locked(name) as folder:
        session = Session(name, state_of(name), index, origin, client_name(source), now or now_stamp())
        handlers = (('nodes', session.node), ('flows', session.flow), ('edges', session.edge), ('annotations', session.annotation))
        for section, handler in handlers:
            for i, item in enumerate(sections[section]):
                session.position = i
                mark, rejected = len(session.ops), len(session.result['rejected'])
                try:
                    handler(item)
                except Rejected as exc:
                    del session.ops[mark:]
                    del session.result['rejected'][rejected:]
                    session.reject(section, i, item, str(exc))
        append(os.path.join(folder, LOG), session.ops)
    result = session.result
    result['created'] = list(dict.fromkeys(result['created']))
    result['updated'] = [x for x in dict.fromkeys(result['updated']) if x not in result['created']]
    result['annotated'] = list(dict.fromkeys(result['annotated']))
    changed = bool(session.ops)
    return {'project': name, **{k: v for k, v in result.items() if k != 'removed'},
            'graph': brain.after_change(name, changed, rebuild), 'refresh': changed and rebuild == 'background'}


def remove(project=None, ids=None, origin='agent', rebuild='background'):
    ids = as_list(ids, 'ids')
    if not ids:
        raise InvalidInput('indica los ids a quitar (nodos, relaciones e:… o anotaciones del agente)')
    if len(ids) > MAX_BATCH:
        raise InvalidInput(f'como mucho {MAX_BATCH} ids por llamada')
    name = project_for(project)
    with locked(name) as folder:
        session = Session(name, state_of(name), None, origin, None, now_stamp())
        for i, ref in enumerate(ids):
            mark = len(session.ops)
            try:
                session.remove(ref)
            except Rejected as exc:
                del session.ops[mark:]
                session.reject('ids', i, ref, str(exc))
        append(os.path.join(folder, LOG), session.ops)
    changed = bool(session.ops)
    return {'project': name, 'removed': session.result['removed'], 'rejected': session.result['rejected'],
            'graph': brain.after_change(name, changed, rebuild), 'refresh': changed and rebuild == 'background'}


def listing(project=None, limit=200, offset=0):
    from .query import clamp_int
    name = project_for(project)
    limit = clamp_int(limit, 200, 1, MAX_LIST, 'limit')
    offset = clamp_int(offset, 0, 0, 10 ** 6, 'offset')
    state = state_of(name)
    index = latest_index(name)
    keys = index.by_key if index else {}

    def status(nid):
        n = keys.get(nid)
        return 'en el grafo' if n is not None and n.get('by') else 'pendiente'

    nodes = [{'id': nid, **{k: meta[k] for k in ('kind', 'name', 'summary', 'tags', 'file', 'line', 'parent', 'community_hint', 'origin',
                                                  'source', 'at') if meta.get(k) not in (None, '', [])},
              'status': status(nid), **({'community': index.community_name(keys[nid]['c'])} if nid in keys else {})}
             for nid, meta in sorted(state['nodes'].items())]
    edges = [{'id': eid, **{k: e[k] for k in ('a', 'b', 'kind', 'label', 'order', 'origin', 'at') if e.get(k) not in (None, '')},
              'status': 'en el grafo' if not keys or (e.get('a') in keys and e.get('b') in keys) else 'descartada'}
             for eid, e in sorted(state['edges'].items(), key=lambda kv: (kv[1].get('a', ''), kv[1].get('kind', ''), kv[1].get('order') or 0, kv[0]))]
    notes = [{'id': nid, **{k: meta[k] for k in ('summary', 'tags', 'origin', 'source', 'at') if meta.get(k) not in (None, '', [])},
              'status': 'en el grafo' if nid in keys else 'pendiente'}
             for nid, meta in sorted(state['notes'].items())]
    warnings = [w['error'] for w in ((index.graph.get('stats') or {}).get('warnings') or []) if w.get('file') == LOG] if index else []
    return {
        'project': name, 'version': index.version if index else None, 'refreshing': brain.rebuilding(name),
        'counts': {'nodes': dict(Counter(n.get('kind') for n in state['nodes'].values())), 'edges': dict(Counter(e.get('kind') for e in state['edges'].values())),
                   'annotations': len(state['notes'])},
        'total': {'nodes': len(nodes), 'edges': len(edges), 'annotations': len(notes)}, 'limit': limit, 'offset': offset,
        'nodes': nodes[offset:offset + limit], 'edges': edges[offset:offset + limit], 'annotations': notes[offset:offset + limit],
        'issues': warnings,
    }


GUIDE_STEPS = [
    'Read the worklist below. Priorities: files the analyzer could not parse, communities without a component, modules without a summary, '
    'and endpoints, topics or variables with no detected counterpart.',
    'Read the code with read_symbol (any node key, including module keys m:<path>) or file_context; never guess.',
    'Call graph_add in batches (up to 500 items): nodes of kind "component" for logical parts (service, screen, layer, subsystem, datastore, '
    'external system) with a one-paragraph summary and "contains" listing the files or symbols that implement them; "flows" for named '
    'business or technical processes with ordered "steps"; "edges" of kind "uses" between components (or any analyzer edge kind such as '
    'call, http, data, event); "annotations" to attach a summary and tags to existing nodes (modules, classes, endpoints...).',
    'Reference nodes by key (preferred), by exact name or by file path. New node ids are a:<slug-of-name> unless you pass "id"; '
    'reusing a name updates that node. Use community_hint (a community name, file or node key) to place a node next to related code.',
    'For files the analyzer does not understand, describe them with annotations on their m:<path> node, or create nodes of an analyzer kind '
    '(function, endpoint, variable...) with "file", "line" and "parent": "m:<path>".',
    'Verify with graph_overlay (status of each contribution and dropped items) and node_context on the new nodes. The graph is refreshed '
    'in the background after every graph_add, creating a new version; graph_remove undoes contributions.',
]


def guide(project=None, limit=GUIDE_LIMIT):
    from .analyze import is_test, wanted
    from .query import clamp_int, load_index
    name = project_for(project)
    limit = clamp_int(limit, GUIDE_LIMIT, 5, 500, 'limit')
    state = state_of(name)
    counts = {'nodes': dict(Counter(n.get('kind') for n in state['nodes'].values())),
              'edges': dict(Counter(e.get('kind') for e in state['edges'].values())), 'annotations': len(state['notes'])}
    if not store.load_history(name)['versions']:
        return {'project': name, 'version': None, 'steps': GUIDE_STEPS, 'overlay': counts, 'refreshing': brain.rebuilding(name),
                'message': 'el proyecto todavía no tiene versión: espera a que termine la actualización o analízalo con analyze_project'}
    index = load_index(name)
    root = index.source_root()
    warned = {}
    for w in (index.graph.get('stats') or {}).get('warnings') or []:
        if w.get('file') and w['file'] != LOG:
            warned.setdefault(w['file'], w.get('error'))
    stats = index.graph.get('stats') or {}
    raw = [f for f in (raw_files(root, stats.get('excluded') or ()) if root else []) if stats.get('tests', True) or not is_test(f)]
    has_symbols = {index.nodes[n['parent']]['file'] for n in index.nodes if 'parent' in n and not n.get('by')}
    unparsed = []
    for rel in raw:
        if rel in index.file_node and rel not in warned:
            continue
        reason = warned.get(rel) or ('formato que el analizador no reconoce' if not wanted(rel) else 'omitido: minificado, generado o ilegible')
        unparsed.append({'file': rel, 'reason': reason})
    for rel in sorted(warned):
        if rel not in raw and rel not in index.file_node:
            unparsed.append({'file': rel, 'reason': warned[rel]})
    empty = [{'file': n['file'], 'key': n['key'], 'reason': 'sin símbolos detectados'}
             for n in sorted(index.file_node.values(), key=lambda n: (-n['deg'], n['file']))
             if n['kind'] == 'module' and n['file'] not in has_symbols and not n.get('summary') and n['file'] not in warned
             and not SECRET_NAMES.search(n['file'])]
    unparsed = [u for u in unparsed if not SECRET_NAMES.search(u['file'])]
    modules = [index.brief(n) for n in sorted(index.file_node.values(), key=lambda n: (-n['deg'], n['file']))
               if n['kind'] == 'module' and not n.get('summary')]
    members = defaultdict(list)
    for n in index.nodes:
        members[n['c']].append(n)
    communities = []
    for c in index.graph['communities']:
        group = members[c['id']]
        if any(n['kind'] == 'component' for n in group):
            continue
        files = sorted((n for n in group if n['kind'] in ('module', 'doc')), key=lambda n: (-n['deg'], n['file']))
        communities.append({'id': c['id'], 'name': c['name'], 'size': c['size'], 'hub': c['hub'], 'files': [n['file'] for n in files[:8]],
                            'files_total': len(files)})
    endpoints, topics, variables = [], [], []
    for n in index.nodes:
        i = n['id']
        if n['kind'] == 'endpoint':
            gaps = [label_ for label_, missing in (('sin manejador', not index.out['handles'].get(i)),
                                                   ('sin clientes detectados', not (index.inc['http'].get(i) or index.inc['rpc'].get(i))))
                    if missing]
            if gaps:
                endpoints.append(index.brief(n, gaps=gaps))
        elif n['kind'] == 'topic':
            producers, consumers = index.inc['event'].get(i), index.out['event'].get(i)
            if not producers or not consumers:
                topics.append(index.brief(n, gaps=['sin productores' if not producers else 'sin consumidores']))
        elif n['kind'] == 'variable':
            users = index.inc['env'].get(i) or []
            defined = any(index.defines(index.nodes[u]) for u, _ in users) or index.defines(index.file_node.get(n['file'], n))
            used = any(not index.defines(index.nodes[u]) for u, _ in users)
            if not (defined and used):
                variables.append(index.brief(n, gaps=['sin uso detectado' if defined else 'sin definición detectada']))

    def page(items):
        return {'total': len(items), 'items': items[:limit]}

    made = sum(1 for n in index.nodes if n.get('by'))
    noted = sum(1 for n in index.nodes if n.get('noted'))
    return {
        'project': name, 'version': index.version, 'source': bool(root), 'steps': GUIDE_STEPS,
        'stats': {k: index.graph['stats'].get(k) for k in ('files', 'nodes', 'edges', 'communities', 'languages')},
        'overlay': {**counts, 'in_graph': {'nodes': made, 'annotated': noted}}, 'refreshing': brain.rebuilding(name),
        'worklist': {
            'unparsed_files': page(unparsed), 'files_without_symbols': page(empty), 'communities_without_component': page(communities),
            'modules_without_summary': page(modules), 'endpoints_without_counterpart': page(endpoints),
            'topics_without_counterpart': page(topics), 'variables_without_counterpart': page(variables),
        },
    }


def markdown(graph):
    nodes = graph.get('nodes') or []
    made = [n for n in nodes if n.get('by')]
    noted = [n for n in nodes if n.get('noted')]
    if not made and not noted:
        return ''
    by_key = {n['key']: n for n in nodes}
    lines = ['', '## Aportado por agentes\n', 'Nodos y notas escritos por una IA (MCP, CLI o `--ai`), no por el análisis estático.\n']
    kind_name = {'component': 'componente', 'flow': 'flujo'}
    for n in sorted(made, key=lambda n: (n['kind'] != 'component', n['kind'], n['name'])):
        where = f" · `{n['file']}:{n['line']}`" if n.get('file') else ''
        head = f"- **{n['name']}** · {kind_name.get(n['kind'], n['kind'])}{where}{' · IA' if n.get('by') == 'ai' else ''}"
        if n.get('summary'):
            head += f": {n['summary'][:300]}"
        lines.append(head)
        if n.get('steps'):
            lines.append('  - pasos: ' + ' → '.join(by_key[k]['name'] if k in by_key else k for k in n['steps']))
    for n in sorted(noted, key=lambda n: (n['file'], n['line'], n['name']))[:200]:
        lines.append(f"- `{n['file']}:{n['line']}` {n['name']}: {(n.get('summary') or ', '.join(n.get('tags') or []))[:300]}")
    lines.append('')
    return '\n'.join(lines)


AI_MAX_CHARS = 40000
AI_FILE_LINES = 80
AI_MAX_TOKENS = 16000
AI_FILES = 40
AI_SCHEMA = {
    'type': 'object',
    'properties': {
        'components': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string'}, 'role': {'type': 'string', 'enum': ['service', 'screen', 'layer', 'subsystem', 'datastore', 'external', 'library', 'other']},
                'summary': {'type': 'string'}, 'files': {'type': 'array', 'items': {'type': 'string'}},
                'uses': {'type': 'array', 'items': {'type': 'string'}},
            },
            'required': ['name', 'role', 'summary', 'files', 'uses'], 'additionalProperties': False,
        }},
        'flows': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {'name': {'type': 'string'}, 'summary': {'type': 'string'}, 'steps': {'type': 'array', 'items': {'type': 'string'}}},
            'required': ['name', 'summary', 'steps'], 'additionalProperties': False,
        }},
        'summaries': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {'file': {'type': 'string'}, 'summary': {'type': 'string'}},
            'required': ['file', 'summary'], 'additionalProperties': False,
        }},
    },
    'required': ['components', 'flows', 'summaries'], 'additionalProperties': False,
}
AI_PROMPT = """You document a software project as a knowledge graph. You receive one group of related files (a community detected from imports and calls): for each file its path, the symbols a static analyzer found (kind, name, signature, key) and the first lines of the file. Secrets were replaced with «redactado».

Return:
- components: the logical parts this group implements (a service, a screen, a layer, a subsystem, a datastore, an external system it talks to). name: short and specific, in the language of the code comments or English. summary: 1-3 sentences on what it does and why. files: the paths (exactly as given) that implement it. uses: names of other components it depends on (from this answer). Prefer 1-4 components per group; skip a component that would only restate a single file.
- flows: named business or technical processes that cross several files (for example "checkout", "user signup", "nightly import"). steps: the ordered symbol keys or file paths (exactly as given) involved. Only flows you can see in the code; return an empty list otherwise.
- summaries: one sentence per important file saying what it is for, especially for files with no symbols (configs, scripts, unknown languages).

Never invent files, keys or behavior that the input does not show."""


def ai_batches(index, root, max_chars=AI_MAX_CHARS):
    from . import llm
    from .query import read_text
    members = defaultdict(list)
    for n in index.nodes:
        if n['kind'] in ('module', 'doc') and not n.get('by'):
            members[n['c']].append(n)
    batches = []
    for c in index.graph['communities']:
        files = sorted(members[c['id']], key=lambda n: (-n['deg'], n['file']))
        current, size = [], 0
        for f in files:
            symbols = [s for s in index.by_file[f['file']] if s is not f and not s.get('by')][:30]
            head = [f"### {f['file']} · key {f['key']}"]
            for s in symbols:
                head.append(f"- {s['kind']} {s['name']}{(' ' + s['sig'][:160]) if s.get('sig') else ''} · key {s['key']}")
            body = ''
            if root and not SECRET_NAMES.search(f['file']):
                content = read_text(root, f['file'], MAX_FILE_BYTES)
                if content:
                    body = llm.redact('\n'.join(content.splitlines()[:AI_FILE_LINES]))
            chunk = '\n'.join(head) + (f'\n```\n{body}\n```' if body else '') + '\n'
            chunk = chunk[:max(2000, max_chars // 4)]
            if current and (size + len(chunk) > max_chars or len(current) >= AI_FILES):
                batches.append({'community': c['name'], 'text': ''.join(current)})
                current, size = [], 0
            current.append(chunk)
            size += len(chunk)
        if current:
            batches.append({'community': c['name'], 'text': ''.join(current)})
    return batches


def ai_request(batch, model):
    return {
        'model': model, 'max_tokens': AI_MAX_TOKENS, 'system': AI_PROMPT,
        'messages': [{'role': 'user', 'content': f"Community: {batch['community']}\n\n{batch['text']}"}],
        'output_config': {'effort': 'low', 'format': {'type': 'json_schema', 'schema': AI_SCHEMA}},
    }


def ai_items(data, community):
    nodes, flows, edges, notes = [], [], [], []
    if not isinstance(data, dict):
        return nodes, flows, edges, notes
    for c in data.get('components') or []:
        if not isinstance(c, dict) or not isinstance(c.get('name'), str) or not c['name'].strip():
            continue
        nodes.append({'name': c['name'][:MAX_NAME], 'kind': 'component', 'summary': str(c.get('summary') or '')[:MAX_SUMMARY] or None,
                      'tags': [c['role']] if isinstance(c.get('role'), str) and c['role'] else None, 'community_hint': community,
                      'contains': [f for f in c.get('files') or [] if isinstance(f, str)][:MAX_CONTAINS]})
        for other in c.get('uses') or []:
            if isinstance(other, str) and other.strip() and other.strip() != c['name']:
                edges.append({'a': c['name'][:MAX_NAME], 'b': other.strip()[:MAX_NAME], 'kind': 'uses'})
    for f in data.get('flows') or []:
        if isinstance(f, dict) and isinstance(f.get('name'), str) and f['name'].strip() and f.get('steps'):
            flows.append({'name': f['name'][:MAX_NAME], 'summary': str(f.get('summary') or '')[:MAX_SUMMARY] or None,
                          'steps': [s for s in f['steps'] if isinstance(s, str)][:MAX_STEPS], 'community_hint': community})
    for s in data.get('summaries') or []:
        if isinstance(s, dict) and isinstance(s.get('file'), str) and isinstance(s.get('summary'), str) and s['summary'].strip():
            notes.append({'id': s['file'], 'summary': s['summary'][:MAX_SUMMARY]})
    return nodes, flows, edges, notes


def ai_enrich(project=None, model=None, client=None, confirm=None, progress=None, max_chars=AI_MAX_CHARS):
    from . import llm
    from .query import load_index
    name = project_for(project)
    index = load_index(name)
    model = llm.model_name(model)
    batches = ai_batches(index, index.source_root(), max_chars)
    chars = sum(len(b['text']) for b in batches)
    base = {'project': name, 'model': model, 'requests': len(batches), 'chars': chars}
    if not batches:
        return {**base, 'note': 'no hay archivos que describir'}
    if client is None:
        ok, why = llm.available()
        if not ok:
            raise InvalidInput(f'--ai no está disponible: {why}')
    if confirm is not None and not confirm(len(batches), chars, model):
        return {**base, 'note': 'cancelado: no se envió nada'}
    if client is None:
        client = llm.sdk().Anthropic()
    issues, collected = [], ([], [], [], [])
    for k, batch in enumerate(batches, 1):
        params = ai_request(batch, model)
        label_ = f'grupo {k} ({batch["community"]})'
        message = llm.call_with_retry(lambda: client.beta.messages.create(**params, betas=[llm.FALLBACK_BETA], fallbacks='default'), issues, label_)
        if message is not None:
            stop = getattr(message, 'stop_reason', None)
            try:
                if stop == 'refusal':
                    raise ValueError('el modelo rechazó el grupo')
                if stop == 'max_tokens':
                    raise ValueError('respuesta cortada por límite de tokens')
                found = ai_items(json.loads(llm.first_text(message)), batch['community'])
                for bucket, items in zip(collected, found):
                    bucket.extend(items)
            except ValueError as exc:
                issues.append(f'{label_}: {exc}')
        if progress:
            progress({'phase': 'ai', 'done': k, 'total': len(batches)})
    nodes, flows, edges, notes = collected
    rejected, counts = [], Counter()
    for section, items in (('nodes', nodes), ('flows', flows), ('edges', edges), ('annotations', notes)):
        for start in range(0, len(items), MAX_BATCH):
            part = items[start:start + MAX_BATCH]
            res = add(name, origin='ai', source=model, rebuild=False, **{section: part})
            rejected.extend(res['rejected'])
            counts['components'] += len(res['created']) + len(res['updated']) if section == 'nodes' else 0
            counts['flows'] += len(res['flows'])
            counts['edges'] += sum(1 for e in res['edges'] if e['kind'] == 'uses')
            counts['summaries'] += len(res['annotated']) if section == 'annotations' else 0
    return {**base, **dict(counts), 'rejected': rejected[:100], 'rejected_total': len(rejected), 'issues': issues}


def wait(project=None, timeout=60.0):
    deadline = time.monotonic() + timeout
    while brain.rebuilding(project) and time.monotonic() < deadline:
        time.sleep(0.02)
    return not brain.rebuilding(project)
