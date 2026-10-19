import json
import os
import re
import threading
import time
from collections import Counter

import numpy as np

from .errors import CortexError, InvalidInput

FORMAT = 'cortex-grafo/1'
NODE_KINDS = {'module', 'class', 'function', 'method', 'doc'}
save_lock = threading.Lock()


def data_dir():
    configured = os.environ.get('CORTEX_DATA') or os.environ.get('DATA_PATH')
    return os.path.abspath(configured or os.path.join(os.getcwd(), 'datos'))


def slug(name):
    return re.sub(r'[^\w.-]+', '-', str(name)).strip('-.')[:60] or 'proyecto'


def project_dir(project):
    path = os.path.join(data_dir(), slug(project))
    os.makedirs(path, exist_ok=True)
    return path


def source_dir(project):
    return os.path.join(project_dir(project), 'fuente')


def version_path(project, version):
    return os.path.join(data_dir(), slug(project), f'v{version}.cortex.json')


def write_atomic(path, text):
    tmp = f'{path}.{os.getpid()}-{threading.get_ident()}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, path)


def read_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_history(project):
    path = os.path.join(data_dir(), slug(project), 'historial.json')
    if not os.path.exists(path):
        return {'project': project, 'origin': None, 'versions': []}
    try:
        hist = read_json(path)
    except (OSError, ValueError) as exc:
        raise CortexError(f'el historial de «{project}» está dañado o no se puede leer') from exc
    if not isinstance(hist, dict) or not isinstance(hist.get('versions'), list):
        raise CortexError(f'el historial de «{project}» está dañado')
    return hist


def parse_version(version):
    if version in (None, ''):
        return None
    if isinstance(version, bool):
        raise InvalidInput('la versión debe ser un número entero')
    if isinstance(version, str):
        version = version.strip().lstrip('vV')
    try:
        number = int(version)
    except (TypeError, ValueError) as exc:
        raise InvalidInput('la versión debe ser un número entero') from exc
    if number < 1:
        raise InvalidInput('la versión debe ser 1 o mayor')
    return number


def load_version(project, version=None):
    hist = load_history(project)
    if not hist['versions']:
        return None
    number = parse_version(version) or hist['versions'][-1]['v']
    if not any(entry.get('v') == number for entry in hist['versions']):
        return None
    try:
        return read_json(version_path(project, number))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise CortexError(f'la versión v{number} de «{project}» está dañada o no se puede leer') from exc


def list_projects():
    root = data_dir()
    if not os.path.isdir(root):
        return []
    out = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name, 'historial.json')
        if not os.path.isfile(path):
            continue
        try:
            hist = read_json(path)
            last = hist['versions'][-1]
            out.append({'project': hist['project'], 'versions': len(hist['versions']), 'last': last, 'origin': hist.get('origin')})
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            continue
    return sorted(out, key=lambda p: p['last'].get('date', ''), reverse=True)


def latest_project():
    projects = list_projects()
    return slug(projects[0]['project']) if projects else None


def stabilize(graph, prev):
    prev_nodes = {n['key']: n for n in prev['nodes']}
    prev_comms = {c['id']: c for c in prev['communities']}
    overlap = Counter((n['c'], prev_nodes[n['key']]['c']) for n in graph['nodes'] if n['key'] in prev_nodes)
    mapping, used = {}, set()
    for (now, before), _ in overlap.most_common():
        if now not in mapping and before not in used:
            mapping[now] = before
            used.add(before)
    rng = np.random.default_rng(11)
    centers = {}
    for c in graph['communities']:
        old = prev_comms.get(mapping.get(c['id']))
        if old:
            c['center'], c['radius'], c['color'] = old['center'], old['radius'], old['color']
        centers[c['id']] = np.array(c['center'], dtype=float)

    fixed = [c for c in graph['communities'] if c['id'] in mapping]
    for c in graph['communities']:
        if c['id'] in mapping:
            continue
        p = np.array(c['center'], dtype=float)
        for _ in range(200):
            if not any(np.linalg.norm(p - np.array(o['center'])) < (o['radius'] + c['radius']) * 1.12 + 3 for o in fixed):
                break
            p = p * 1.05 + rng.normal(scale=1.0, size=3)
        c['center'] = [round(float(x), 3) for x in p]
        centers[c['id']] = p
        fixed.append(c)

    by_id = {n['id']: n for n in graph['nodes']}
    by_comm = {c['id']: c for c in graph['communities']}
    for n in graph['nodes']:
        old = prev_nodes.get(n['key'])
        if old:
            n['pos'] = old['pos']
    for n in graph['nodes']:
        if n['key'] in prev_nodes:
            continue
        anchor = by_id.get(n.get('parent'))
        if anchor is not None and anchor['key'] in prev_nodes:
            base, spread = np.array(anchor['pos'], dtype=float), 0.9
        else:
            base, spread = centers[n['c']], by_comm[n['c']]['radius'] * 0.6
        n['pos'] = [round(float(x), 3) for x in base + rng.normal(scale=spread, size=3)]


def compare(nodes, before_nodes):
    before = {n['key']: n for n in before_nodes}
    now = {n['key'] for n in nodes}
    added, modified = [], []
    for n in nodes:
        old = before.get(n['key'])
        if old is None:
            added.append(n['key'])
        elif old.get('hash') and n.get('hash') and old['hash'] != n['hash']:
            modified.append(n['key'])
    removed = [{k: before[key].get(k) for k in ('key', 'kind', 'name', 'file')} for key in before if key not in now]
    return {'added': added, 'modified': modified, 'removed': removed}


def diff(graph, prev):
    if not prev:
        for n in graph['nodes']:
            n.pop('status', None)
        return {'added': [], 'modified': [], 'removed': []}
    changes = compare(graph['nodes'], prev['nodes'])
    status = {**{k: 'new' for k in changes['added']}, **{k: 'changed' for k in changes['modified']}}
    for n in graph['nodes']:
        if n['key'] in status:
            n['status'] = status[n['key']]
        else:
            n.pop('status', None)
    return changes


def save_version(graph, origin=None, options=None, commit=None):
    project = graph['project']
    with save_lock:
        hist = load_history(project)
        prev = load_version(project) if hist['versions'] else None
        if prev:
            stabilize(graph, prev)
        changes = diff(graph, prev)
        number = (hist['versions'][-1]['v'] + 1) if hist['versions'] else 1
        entry = {
            'v': number,
            'date': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'origin': origin,
            'options': options or {},
            'commit': commit,
            'stats': {k: graph['stats'][k] for k in ('files', 'nodes', 'edges', 'communities')},
            'changes': {k: len(v) for k, v in changes.items()},
        }
        graph['format'] = FORMAT
        graph['version'] = number
        graph['changes'] = changes
        hist['project'] = project
        hist['versions'].append(entry)
        if origin:
            hist['origin'] = origin
        graph['history'] = hist['versions']
        folder = project_dir(project)
        write_atomic(os.path.join(folder, f'v{number}.cortex.json'), json.dumps(graph, ensure_ascii=False))
        write_atomic(os.path.join(folder, 'historial.json'), json.dumps(hist, ensure_ascii=False, indent=1))
    return hist


def write_exports(graph, export_markdown, export_json):
    folder = project_dir(graph['project'])
    write_atomic(os.path.join(folder, 'grafo.md'), export_markdown(graph))
    write_atomic(os.path.join(folder, 'grafo.json'), json.dumps(export_json(graph), ensure_ascii=False))


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_graph(graph):
    invalid = InvalidInput('no es un grafo de Córtex (.cortex.json)')
    if not isinstance(graph, dict) or graph.get('format') != FORMAT:
        raise invalid
    nodes, edges, visible, comms = graph.get('nodes'), graph.get('edges', []), graph.get('visible'), graph.get('communities')
    if not (isinstance(nodes, list) and nodes and isinstance(edges, list) and isinstance(visible, list) and isinstance(comms, list) and comms):
        raise invalid
    for i, c in enumerate(comms):
        if not isinstance(c, dict) or c.get('id') != i or not isinstance(c.get('name'), str):
            raise InvalidInput('el grafo tiene comunidades inválidas')
        if not (isinstance(c.get('center'), list) and len(c['center']) == 3 and all(map(is_number, c['center'])) and is_number(c.get('radius'))):
            raise InvalidInput('el grafo tiene comunidades inválidas')
    for i, n in enumerate(nodes):
        valid = (
            isinstance(n, dict) and n.get('id') == i and isinstance(n.get('key'), str) and n.get('kind') in NODE_KINDS
            and isinstance(n.get('name'), str) and isinstance(n.get('file'), str) and is_int(n.get('c')) and 0 <= n['c'] < len(comms)
            and is_int(n.get('line')) and is_int(n.get('deg'))
            and isinstance(n.get('pos'), list) and len(n['pos']) == 3 and all(map(is_number, n['pos']))
            and ('parent' not in n or (is_int(n['parent']) and 0 <= n['parent'] < len(nodes)))
        )
        if not valid:
            raise InvalidInput(f'el grafo tiene un nodo inválido (#{i})')
    for e in edges + visible:
        valid = (
            isinstance(e, dict) and is_int(e.get('a')) and is_int(e.get('b')) and 0 <= e['a'] < len(nodes)
            and 0 <= e['b'] < len(nodes) and isinstance(e.get('kind'), str) and is_number(e.get('w'))
        )
        if not valid:
            raise InvalidInput('el grafo tiene una relación inválida')
    graph['project'] = slug(graph.get('project') or 'importado')
    stats = graph.get('stats') if isinstance(graph.get('stats'), dict) else {}
    stats.setdefault('files', sum(1 for n in nodes if n['kind'] in ('module', 'doc')))
    stats.setdefault('nodes', len(nodes))
    stats.setdefault('edges', len(edges))
    stats.setdefault('communities', len(comms))
    graph['stats'] = stats
    return graph
