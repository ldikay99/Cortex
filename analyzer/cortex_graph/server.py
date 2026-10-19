import io
import json
import logging
import math
import os
import re
import shutil
import socket
import threading
import time
import zipfile
import zlib
from collections import Counter, defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import context, pipeline, query, store
from .analyze import (MAX_NOTEBOOK_BYTES, MAX_SCRIPT_BYTES, SKIP_DIRS, export_json, export_markdown, formats, is_test,
                      list_files, maybe_script, script_route, wanted)
from .errors import Conflict, CortexError, InvalidInput, NotFound, TooLarge

log = logging.getLogger('cortex.server')

MAX_UPLOAD = 80 * 1024 * 1024
MAX_EXTRACTED = 200 * 1024 * 1024
MAX_FILE = 2 * 1024 * 1024
MAX_FILES = 20000
MAX_ZIP_ENTRIES = 200000
MAX_JSON = 1_000_000
MAX_PARAM = 1000
SKIP_PARTS = SKIP_DIRS
TICK = 0.05
DISCONNECTS = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, socket.timeout)


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.data = {'state': 'idle', 'graph': None, 'plan': None, 'error': None, 'source': None,
                     'project': None, 'origin': None, 'gen': 0}

    def snapshot(self):
        with self.lock:
            return dict(self.data)

    def begin(self, **changes):
        with self.lock:
            self.data['gen'] += 1
            self.data.update(graph=None, plan=None, error=None, **changes)
            return self.data['gen']

    def update(self, gen, **changes):
        with self.lock:
            if gen != self.data['gen']:
                return False
            self.data.update(**changes)
            return True

    def is_current(self, gen):
        with self.lock:
            return gen == self.data['gen']


state = State()


def build_order(graph):
    nodes, edges = graph['nodes'], graph['visible']
    children = defaultdict(list)
    for n in nodes:
        if 'parent' in n:
            children[n['parent']].append(n['id'])
    link = defaultdict(Counter)
    for e in edges:
        ca, cb = nodes[e['a']]['c'], nodes[e['b']]['c']
        if ca != cb:
            link[ca][cb] += e['w']
            link[cb][ca] += e['w']
    sizes = Counter(n['c'] for n in nodes)
    seen, comm_order = set(), []
    for start in sorted(sizes, key=lambda c: -sizes[c]):
        if start in seen:
            continue
        queue = deque([start])
        seen.add(start)
        while queue:
            c = queue.popleft()
            comm_order.append(c)
            for following, _ in link[c].most_common():
                if following not in seen:
                    seen.add(following)
                    queue.append(following)
    by_comm = defaultdict(list)
    for n in nodes:
        if n['kind'] in ('module', 'doc'):
            by_comm[n['c']].append(n)
    order, placed = [], set()
    for c in comm_order:
        for top in sorted(by_comm[c], key=lambda n: -n['deg']):
            stack = [top['id']]
            while stack:
                i = stack.pop()
                if i in placed:
                    continue
                placed.add(i)
                order.append(i)
                stack.extend(reversed(sorted(children[i], key=lambda j: nodes[j]['line'])))
    order += [n['id'] for n in nodes if n['id'] not in placed]
    return order


def stream_plan(graph):
    order = build_order(graph)
    rank = {nid: k for k, nid in enumerate(order)}
    waiting = defaultdict(list)
    for e in graph['visible']:
        waiting[max(e['a'], e['b'], key=rank.__getitem__)].append(e)
    first = {}
    for k, nid in enumerate(order):
        first.setdefault(graph['nodes'][nid]['c'], k)
    return {'order': order, 'waiting': waiting, 'first': first}


def set_ready(graph, gen):
    plan = stream_plan(graph)
    return state.update(gen, graph=graph, plan=plan, state='ready', project=graph['project'])


def human_error(exc):
    if isinstance(exc, CortexError):
        return exc.message
    if isinstance(exc, MemoryError):
        return 'el proyecto es demasiado grande para la memoria disponible'
    return f'no se pudo analizar el proyecto: error interno ({type(exc).__name__}); los detalles quedaron en el registro del analizador'


def fail_job(gen, exc):
    if isinstance(exc, CortexError):
        log.warning('trabajo cancelado: %s', exc.message)
    else:
        log.exception('falló un trabajo en segundo plano')
    state.update(gen, state='error', error=human_error(exc))


def run_analysis(gen, source, project, origin, exclude=(), include_tests=False):
    try:
        graph = pipeline.analyze_and_save(source, project, origin, exclude, include_tests, still_wanted=lambda: state.is_current(gen))
        if graph is not None and set_ready(graph, gen):
            counts = {k: len(v) for k, v in graph['changes'].items()}
            log.info('%s v%s: %s nodos, cambios %s', project, graph['version'], graph['stats']['nodes'], counts)
    except Exception as exc:
        fail_job(gen, exc)


def start_analysis(source, project, origin, exclude=(), include_tests=False):
    gen = state.begin(state='analyzing', source=source, project=project, origin=origin)
    threading.Thread(target=run_analysis, args=(gen, source, project, origin, exclude, include_tests), daemon=True).start()
    return gen


def start_clone(owner, repo, then, project=None):
    name = store.slug(project or repo)
    origin = {'type': 'github', 'url': pipeline.github_url(owner, repo)}
    gen = state.begin(state='cloning', project=name, origin=origin, source=None)

    def job():
        try:
            dest = pipeline.clone_github(owner, repo, store.source_dir(name))
            if state.update(gen, source=dest):
                then(gen, dest, name, origin)
        except Exception as exc:
            fail_job(gen, exc)

    threading.Thread(target=job, daemon=True).start()
    return name


def to_review(gen, dest, name, origin):
    state.update(gen, state='review', source=dest)


def clean_parts(raw):
    if not isinstance(raw, str) or not raw or len(raw) > 1000 or '\x00' in raw:
        raise InvalidInput('hay un archivo con una ruta inválida')
    path = raw.replace('\\', '/')
    parts = [p for p in path.split('/') if p not in ('', '.')]
    if path.startswith('/') or re.match(r'^[A-Za-z]:', path) or '..' in parts:
        raise InvalidInput(f'ruta no permitida (fuera del proyecto): {raw[:200]}')
    return parts


def file_limit(rel):
    if rel.endswith('.ipynb'):
        return MAX_NOTEBOOK_BYTES
    return MAX_FILE if wanted(rel) else MAX_SCRIPT_BYTES


def kept(parts):
    if not parts or SKIP_PARTS.intersection(parts) or not (wanted('/'.join(parts)) or maybe_script('/'.join(parts))):
        return None
    return '/'.join(parts)


class Extraction:
    def __init__(self, dest):
        self.dest = dest
        self.files = 0
        self.bytes = 0

    def add(self, rel, data):
        if len(data) > file_limit(rel):
            return
        if not wanted(rel) and not script_route(data[:160]):
            return
        self.files += 1
        self.bytes += len(data)
        if self.files > MAX_FILES:
            raise TooLarge(f'el proyecto tiene más de {MAX_FILES} archivos para analizar')
        if self.bytes > MAX_EXTRACTED:
            raise TooLarge('el proyecto supera 200 MB de archivos para analizar')
        path = os.path.join(self.dest, rel)
        if not os.path.abspath(path).startswith(os.path.abspath(self.dest) + os.sep):
            raise InvalidInput(f'ruta no permitida (fuera del proyecto): {rel[:200]}')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)


def extract_zip(body, out):
    try:
        archive = zipfile.ZipFile(io.BytesIO(body))
        entries = [i for i in archive.infolist() if not i.is_dir()]
    except (zipfile.BadZipFile, zipfile.LargeZipFile, ValueError, OSError) as exc:
        raise InvalidInput('el .zip está dañado o no es un .zip válido') from exc
    if len(entries) > MAX_ZIP_ENTRIES:
        raise TooLarge(f'el .zip tiene más de {MAX_ZIP_ENTRIES} entradas')
    names = [clean_parts(i.filename) for i in entries]
    tops = {parts[0] for parts in names if parts}
    strip = len(tops) == 1 and all(len(parts) > 1 for parts in names)
    with archive:
        for info, parts in zip(entries, names):
            rel = kept(parts[1:] if strip else parts)
            if not rel or info.file_size > file_limit(rel):
                continue
            try:
                with archive.open(info) as f:
                    data = f.read(file_limit(rel) + 1)
            except RuntimeError as exc:
                raise InvalidInput('el .zip está protegido con contraseña') from exc
            except NotImplementedError as exc:
                raise InvalidInput('el .zip usa una compresión no soportada') from exc
            except (zipfile.BadZipFile, zlib.error, EOFError, OSError) as exc:
                raise InvalidInput('el .zip está dañado') from exc
            out.add(rel, data)


def extract_ndjson(body, out):
    for number, raw in enumerate(body.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise InvalidInput(f'la línea {number} no es JSON válido') from exc
        if not isinstance(item, dict) or not isinstance(item.get('path'), str) or not isinstance(item.get('content', ''), str):
            raise InvalidInput(f'la línea {number} debe ser un objeto {{path, content}} con texto')
        rel = kept(clean_parts(item['path']))
        if rel:
            out.add(rel, item.get('content', '').encode('utf-8', errors='replace'))


def project_param(params):
    return params.get('project') or None


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'cortex-analyzer'
    sys_version = ''
    timeout = 300

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        self.dispatch(GET_ROUTES)

    def do_POST(self):
        self.dispatch(POST_ROUTES)

    def dispatch(self, routes):
        self.responded = False
        try:
            url = urlparse(self.path)
            route = routes.get(url.path)
            if route is None:
                if self.command == 'POST':
                    self.close_connection = True
                raise NotFound('no encontrado')
            route(self, self.params(url.query))
        except CortexError as exc:
            self.fail(exc.status, exc.message)
        except DISCONNECTS:
            self.close_connection = True
        except Exception:
            log.exception('error atendiendo %s %s', self.command, self.path[:300])
            self.fail(500, 'error interno del analizador: el detalle quedó en su registro')

    def params(self, raw):
        try:
            parsed = parse_qs(raw, keep_blank_values=True, max_num_fields=50)
        except ValueError as exc:
            raise InvalidInput('la consulta tiene demasiados parámetros') from exc
        values = {}
        for key, items in parsed.items():
            if len(items[0]) > MAX_PARAM:
                raise InvalidInput(f'el parámetro «{key}» es demasiado largo')
            values[key] = items[0]
        return values

    def fail(self, status, message):
        self.close_connection = True
        if self.responded:
            return
        try:
            self.send_json({'error': message}, status)
        except DISCONNECTS:
            pass

    def begin_response(self, status, headers):
        self.responded = True
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        if self.close_connection:
            self.send_header('Connection', 'close')
        self.end_headers()

    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.begin_response(status, {'Content-Type': 'application/json; charset=utf-8', 'Content-Length': str(len(body)),
                                     'Cache-Control': 'no-store'})
        self.wfile.write(body)

    def send_file(self, body, kind, filename):
        self.begin_response(200, {'Content-Type': f'{kind}; charset=utf-8', 'Content-Length': str(len(body)),
                                  'Content-Disposition': f'attachment; filename="{filename}"', 'Cache-Control': 'no-store'})
        self.wfile.write(body)

    def read_body(self, limit, too_large):
        if 'chunked' in (self.headers.get('Transfer-Encoding') or '').lower():
            return self.read_chunked(limit, too_large)
        raw = self.headers.get('Content-Length') or '0'
        try:
            size = int(raw)
        except ValueError as exc:
            self.close_connection = True
            raise InvalidInput('la cabecera Content-Length no es válida') from exc
        if size < 0:
            self.close_connection = True
            raise InvalidInput('la cabecera Content-Length no es válida')
        if size > limit:
            self.close_connection = True
            raise TooLarge(too_large)
        data = self.rfile.read(size)
        if len(data) < size:
            self.close_connection = True
            raise InvalidInput('el cuerpo de la petición llegó incompleto')
        return data

    def read_chunked(self, limit, too_large):
        self.close_connection = True
        parts, total = [], 0
        while True:
            line = self.rfile.readline(64)
            try:
                size = int(line.split(b';')[0].strip(), 16)
            except ValueError as exc:
                raise InvalidInput('el cuerpo de la petición está mal formado') from exc
            if size == 0:
                self.rfile.readline(64)
                return b''.join(parts)
            total += size
            if total > limit:
                raise TooLarge(too_large)
            parts.append(self.rfile.read(size))
            self.rfile.readline(64)

    def body_json(self, limit=MAX_JSON):
        body = self.read_body(limit, 'la petición es demasiado grande')
        if not body.strip():
            return {}
        try:
            data = json.loads(body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise InvalidInput('el cuerpo de la petición no es JSON válido') from exc
        if not isinstance(data, dict):
            raise InvalidInput('se esperaba un objeto JSON')
        return data

    def get_status(self, params):
        s = state.snapshot()
        g = s['graph']
        self.send_json({'state': s['state'], 'project': s['project'], 'error': s['error'],
                        'stats': g['stats'] if g else None, 'version': g.get('version') if g else None})

    def get_formats(self, params):
        self.send_json(formats())

    def get_projects(self, params):
        self.send_json({'projects': store.list_projects()})

    def get_tree(self, params):
        s = state.snapshot()
        if s['state'] != 'review' or not s['source']:
            raise Conflict('no hay un proyecto esperando revisión')
        files = list_files(s['source'])
        self.send_json({'project': s['project'], 'files': files, 'tests': [f for f in files if is_test(f)]})

    def get_graph(self, params):
        s = state.snapshot()
        if s['graph']:
            self.send_json(s['graph'])
        else:
            self.send_json({'state': s['state']}, 503)

    def current_graph(self):
        g = state.snapshot()['graph']
        if not g:
            raise Conflict('todavía no hay un grafo listo')
        return g, f"{g['project']}-v{g.get('version', 1)}"

    def get_export_md(self, params):
        g, name = self.current_graph()
        self.send_file(export_markdown(g).encode(), 'text/markdown', f'{name}-grafo.md')

    def get_export_json(self, params):
        g, name = self.current_graph()
        self.send_file(json.dumps(export_json(g), ensure_ascii=False).encode(), 'application/json', f'{name}-grafo.json')

    def get_export_cortex(self, params):
        g, name = self.current_graph()
        self.send_file(json.dumps(g, ensure_ascii=False).encode(), 'application/json', f'{name}.cortex.json')

    def line(self, obj):
        data = (json.dumps(obj, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
        self.wfile.write(f'{len(data):x}\r\n'.encode() + data + b'\r\n')
        self.wfile.flush()

    def end_stream(self):
        self.wfile.write(b'0\r\n\r\n')
        self.wfile.flush()

    def get_stream(self, params):
        try:
            rate = float(params.get('rate') or 90)
        except ValueError as exc:
            raise InvalidInput('«rate» debe ser un número') from exc
        if not math.isfinite(rate):
            raise InvalidInput('«rate» debe ser un número')
        rate = max(1.0, min(5000.0, rate))
        start = query.clamp_int(params.get('from'), 0, 0, 10 ** 9, 'from')
        self.begin_response(200, {'Content-Type': 'application/x-ndjson; charset=utf-8', 'Cache-Control': 'no-store',
                                  'X-Accel-Buffering': 'no', 'Transfer-Encoding': 'chunked'})
        s = state.snapshot()
        while s['state'] in ('analyzing', 'cloning'):
            self.line({'t': s['state'], 'project': s['project']})
            time.sleep(1)
            s = state.snapshot()
        if s['state'] == 'error':
            self.line({'t': 'error', 'error': s['error']})
        elif s['state'] != 'ready' or not s['graph']:
            self.line({'t': s['state'] if s['state'] in ('idle', 'review') else 'idle'})
        else:
            self.send_graph(s['graph'], s['plan'], rate, start)
        self.end_stream()

    def send_graph(self, g, plan, rate, start):
        nodes, communities = g['nodes'], g['communities']
        order, waiting, first = plan['order'], plan['waiting'], plan['first']
        self.line({'t': 'meta', 'project': g['project'], 'stats': g['stats'], 'version': g.get('version'),
                   'changes': {k: len(v) for k, v in (g.get('changes') or {}).items()}})
        k = min(start, len(order))
        budget = 0.0
        while k < len(order):
            budget += rate * TICK
            batch = []
            while budget >= 1 and k < len(order):
                n = nodes[order[k]]
                if first[n['c']] == k:
                    batch.append({'t': 'community', **communities[n['c']]})
                batch.append({'t': 'node', **n})
                for e in waiting.get(n['id'], ()):
                    batch.append({'t': 'edge', 'a': e['a'], 'b': e['b'], 'kind': e['kind'], 'w': e['w']})
                budget -= 1
                k += 1
            if batch:
                self.line({'t': 'batch', 'items': batch, 'done': k, 'total': len(order)})
            time.sleep(TICK)
        self.line({'t': 'done', 'stats': g['stats']})

    def get_query_overview(self, params):
        self.send_json(query.overview(project_param(params)))

    def get_query_search(self, params):
        self.send_json(query.search(params.get('q', ''), project_param(params), params.get('kind') or None, params.get('limit'),
                                    params.get('offset')))

    def get_query_node(self, params):
        self.send_json(query.node(params.get('ref', ''), project_param(params)))

    def get_query_file(self, params):
        self.send_json(query.file(params.get('path', ''), project_param(params)))

    def get_query_community(self, params):
        self.send_json(query.community(params.get('ref', ''), project_param(params)))

    def get_query_path(self, params):
        self.send_json(query.path(params.get('a', ''), params.get('b', ''), project_param(params)))

    def get_query_impact(self, params):
        self.send_json(query.impact(params.get('ref', ''), project_param(params), params.get('depth')))

    def get_query_changes(self, params):
        self.send_json(query.changes(project_param(params), params.get('since') or None))

    def get_query_symbol(self, params):
        self.send_json(context.read_symbol(params.get('ref', ''), project_param(params), params.get('context')))

    def get_query_context(self, params):
        self.send_json(context.context_for(params.get('q', ''), project_param(params), params.get('budget')))

    def get_query_architecture(self, params):
        self.send_json(query.architecture(project_param(params), params.get('section') or None, params.get('limit'), params.get('offset')))

    def get_query_dependencies(self, params):
        self.send_json(query.dependencies(project_param(params), params.get('name') or None, params.get('limit'), params.get('offset')))

    def get_query_endpoints(self, params):
        self.send_json(query.endpoints(project_param(params), params.get('limit'), params.get('offset'), params.get('method') or None))

    def get_query_variables(self, params):
        self.send_json(query.variables(project_param(params), params.get('name') or None, params.get('limit'), params.get('offset')))

    def review(self, base, head, project, diff=None):
        from .mcp_server import run_review
        for label, value in (('base', base), ('head', head)):
            if value is not None and not isinstance(value, str):
                raise InvalidInput(f'«{label}» debe ser texto')
        if diff is not None and not isinstance(diff, str):
            raise InvalidInput('«diff» debe ser texto')
        self.send_json(run_review(base or 'HEAD~1', head or 'HEAD', project, None, diff))

    def get_query_review(self, params):
        worktree = params.get('worktree') in ('1', 'true', 'yes')
        base = params.get('base') or ('HEAD' if worktree else None)
        head = 'WORKTREE' if worktree else params.get('head')
        self.review(base, head, project_param(params))

    def post_query_review(self, params):
        req = self.body_json(MAX_UPLOAD // 8)
        project = req.get('project') if isinstance(req.get('project'), str) and req.get('project') else project_param(params)
        self.review(req.get('base'), req.get('head'), project, req.get('diff'))

    def post_analyze(self, params):
        opts = self.body_json()
        s = state.snapshot()
        if not s['source'] or s['state'] == 'cloning':
            raise Conflict('primero sube o clona un proyecto')
        exclude = pipeline.normalize_excludes(opts.get('exclude', []))
        tests = opts.get('tests', False)
        if not isinstance(tests, bool):
            raise InvalidInput('«tests» debe ser true o false')
        start_analysis(s['source'], s['project'], s['origin'], exclude, tests)
        self.send_json({'state': 'analyzing', 'project': s['project']}, 202)

    def post_github(self, params):
        github = pipeline.parse_github(self.body_json(4096).get('url', ''))
        if not github:
            raise InvalidInput('usa una URL como https://github.com/usuario/repo')
        name = start_clone(*github, then=to_review)
        self.send_json({'state': 'cloning', 'project': name}, 202)

    def post_open(self, params):
        req = self.body_json(4096)
        project = req.get('project')
        if not isinstance(project, str) or not project.strip():
            raise InvalidInput('falta el nombre del proyecto')
        g = store.load_version(project, req.get('version'))
        if not g:
            raise NotFound('ese proyecto no tiene versiones guardadas')
        hist = store.load_history(g['project'])
        gen = state.begin(state='analyzing', project=g['project'], origin=hist.get('origin'), source=store.source_dir(g['project']))
        set_ready(g, gen)
        self.send_json({'state': 'ready', 'project': g['project'], 'version': g.get('version')})

    def post_update(self, params):
        project = self.body_json(4096).get('project')
        if not isinstance(project, str) or not project.strip():
            raise InvalidInput('falta el nombre del proyecto')
        hist = store.load_history(project)
        if not hist['versions']:
            raise NotFound('ese proyecto no tiene versiones guardadas')
        origin = hist.get('origin') or {}
        opts = hist['versions'][-1].get('options') or {}
        exclude = pipeline.normalize_excludes(opts.get('exclude', []))
        tests = bool(opts.get('tests', False))
        name = store.slug(hist['project'])
        github = pipeline.parse_github(origin.get('url', '')) if origin.get('type') == 'github' else None
        if github:
            def analyze_again(gen, dest, project_name, project_origin):
                if state.update(gen, state='analyzing'):
                    run_analysis(gen, dest, project_name, project_origin, exclude, tests)

            start_clone(*github, then=analyze_again, project=name)
            return self.send_json({'state': 'cloning', 'project': name}, 202)
        if origin.get('type') == 'local' and isinstance(origin.get('path'), str) and os.path.isdir(origin['path']):
            start_analysis(origin['path'], name, origin, exclude, tests)
            return self.send_json({'state': 'analyzing', 'project': name}, 202)
        raise Conflict('este proyecto se subió a mano: vuelve a subir su carpeta o .zip para actualizarlo')

    def post_import(self, params):
        body = self.read_body(MAX_UPLOAD, 'el archivo debe pesar menos de 80 MB')
        if not body:
            raise InvalidInput('el archivo llegó vacío')
        try:
            g = json.loads(body)
        except (ValueError, UnicodeDecodeError, RecursionError) as exc:
            raise InvalidInput('no es un grafo de Córtex (.cortex.json)') from exc
        g = store.validate_graph(g)
        options = ((g.get('history') or [{}])[-1] or {}).get('options') if isinstance(g.get('history'), list) else None
        gen = state.begin(state='analyzing', project=g['project'], origin={'type': 'import'}, source=None)
        store.save_version(g, {'type': 'import'}, options if isinstance(options, dict) else None)
        store.write_exports(g, export_markdown, export_json)
        set_ready(g, gen)
        self.send_json({'state': 'ready', 'project': g['project'], 'version': g['version']})

    def post_upload(self, params):
        name = store.slug(params.get('name') or 'proyecto')
        body = self.read_body(MAX_UPLOAD, 'el proyecto debe pesar entre 1 byte y 80 MB (solo código, configuración y documentos)')
        if not body:
            raise TooLarge('el proyecto debe pesar entre 1 byte y 80 MB (solo código, configuración y documentos)')
        dest = store.source_dir(name)
        staging = f'{dest}.subiendo-{threading.get_ident()}'
        shutil.rmtree(staging, ignore_errors=True)
        out = Extraction(staging)
        try:
            if body[:2] == b'PK':
                extract_zip(body, out)
            else:
                extract_ndjson(body, out)
            if not out.files:
                raise InvalidInput('no encontré archivos de código, configuración ni documentos en lo que subiste')
            shutil.rmtree(dest, ignore_errors=True)
            os.replace(staging, dest)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        gen = state.begin(state='review', project=name, source=dest, origin={'type': 'upload'})
        self.send_json({'state': 'review', 'project': name, 'files': out.files, 'gen': gen}, 200)


GET_ROUTES = {
    '/api/status': Handler.get_status,
    '/api/projects': Handler.get_projects,
    '/api/formatos': Handler.get_formats,
    '/api/tree': Handler.get_tree,
    '/api/graph': Handler.get_graph,
    '/api/stream': Handler.get_stream,
    '/api/export.md': Handler.get_export_md,
    '/api/export.json': Handler.get_export_json,
    '/api/export.cortex': Handler.get_export_cortex,
    '/api/query/overview': Handler.get_query_overview,
    '/api/query/search': Handler.get_query_search,
    '/api/query/node': Handler.get_query_node,
    '/api/query/file': Handler.get_query_file,
    '/api/query/community': Handler.get_query_community,
    '/api/query/path': Handler.get_query_path,
    '/api/query/impact': Handler.get_query_impact,
    '/api/query/changes': Handler.get_query_changes,
    '/api/query/symbol': Handler.get_query_symbol,
    '/api/query/context': Handler.get_query_context,
    '/api/query/architecture': Handler.get_query_architecture,
    '/api/query/dependencies': Handler.get_query_dependencies,
    '/api/query/endpoints': Handler.get_query_endpoints,
    '/api/query/variables': Handler.get_query_variables,
    '/api/query/review': Handler.get_query_review,
}

POST_ROUTES = {
    '/api/upload': Handler.post_upload,
    '/api/github': Handler.post_github,
    '/api/analyze': Handler.post_analyze,
    '/api/open': Handler.post_open,
    '/api/update': Handler.post_update,
    '/api/import': Handler.post_import,
    '/api/query/review': Handler.post_query_review,
}


def make_server(host='0.0.0.0', port=8000):
    os.makedirs(store.data_dir(), exist_ok=True)
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    return httpd


def serve(port=None, host='0.0.0.0'):
    port = port or int(os.environ.get('PORT', '8000'))
    httpd = make_server(host, port)
    log.info('esperando un proyecto · datos en %s · puerto %s', store.data_dir(), port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info('detenido')
    finally:
        httpd.server_close()
