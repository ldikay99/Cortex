import base64
import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import time

from . import __version__, brain, config as project_config, overlay, store
from .analyze import analyze, export_json, export_markdown, list_files
from .errors import CortexError, InvalidInput, NotFound

try:
    import fcntl
except ImportError:
    fcntl = None
try:
    import msvcrt
except ImportError:
    msvcrt = None

GITHUB_RE = re.compile(r'^https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$')
CLONE_TIMEOUT = 300
MAX_EXCLUDES = 2000


def parse_github(url):
    match = GITHUB_RE.match(str(url).strip()) if isinstance(url, str) and len(url) <= 300 else None
    if not match or match.group(1) in ('.', '..') or match.group(2) in ('.', '..'):
        return None
    return match.group(1), match.group(2)


def github_url(owner, repo):
    return f'https://github.com/{owner}/{repo}'


def normalize_excludes(exclude):
    if exclude is None:
        return []
    if not isinstance(exclude, (list, tuple)):
        raise InvalidInput('«exclude» debe ser una lista de rutas')
    if len(exclude) > MAX_EXCLUDES:
        raise InvalidInput(f'«exclude» admite como mucho {MAX_EXCLUDES} rutas')
    cleaned = []
    for item in exclude:
        if not isinstance(item, str) or len(item) > 500:
            raise InvalidInput('cada ruta de «exclude» debe ser texto de menos de 500 caracteres')
        item = item.strip().strip('/')
        if item:
            cleaned.append(item)
    return cleaned


def git_commit(path):
    if not os.path.isdir(os.path.join(path, '.git')):
        return None
    try:
        res = subprocess.run(['git', '-C', path, 'log', '-1', '--format=%H%n%s%n%cI'], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    sha, subject, date = (res.stdout.split('\n') + ['', '', ''])[:3]
    return {'sha': sha, 'subject': subject, 'date': date}


def clone_github(owner, repo, dest):
    token = os.environ.get('GITHUB_TOKEN', '')
    staging = dest + '.clonando'
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    cmd = ['git', 'clone', '--depth', '1', '--quiet', f'{github_url(owner, repo)}.git', staging]
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0'}
    if token:
        basic = base64.b64encode(f'x-access-token:{token}'.encode()).decode()
        env.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='http.https://github.com/.extraheader',
                   GIT_CONFIG_VALUE_0=f'AUTHORIZATION: basic {basic}')
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=CLONE_TIMEOUT, env=env)
    except FileNotFoundError as exc:
        raise CortexError('git no está instalado: no se puede clonar') from exc
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise CortexError('la clonación tardó más de 5 minutos y se canceló') from exc
    if res.returncode != 0:
        shutil.rmtree(staging, ignore_errors=True)
        raise CortexError('no se pudo clonar: ¿el repo existe y es público? (para privados, define GITHUB_TOKEN)')
    shutil.rmtree(dest, ignore_errors=True)
    os.replace(staging, dest)
    return dest


def code_signature():
    folder = os.path.dirname(os.path.abspath(__file__))
    out = [__version__]
    for name in sorted(os.listdir(folder)):
        if name.endswith('.py'):
            st = os.stat(os.path.join(folder, name))
            out.append(f'{name}:{st.st_size}:{st.st_mtime_ns}')
    return out


def source_files(root, exclude, include_tests, settings):
    exclude = tuple(exclude) + tuple(settings.get('exclude') or ())
    return [f for f in list_files(root, exclude, not include_tests) if not project_config.ignored(settings, f)]


def memory_stamp(project):
    if not project:
        return None
    try:
        st = os.stat(os.path.join(store.project_dir(project), brain.LOG))
    except OSError:
        return None
    return [st.st_size, st.st_mtime_ns]


def fingerprint(root, exclude=(), include_tests=False, settings=None, commit=None, mtimes=True, project=None):
    settings = settings if settings is not None else project_config.load(root)
    head = {
        'analyzer': code_signature(), 'exclude': sorted(exclude), 'tests': bool(include_tests), 'git': settings.get('git', True),
        'ignore': settings.get('ignore_patterns') or [], 'config_exclude': settings.get('exclude') or [], 'roots': settings.get('roots') or [],
        'commit': (commit or {}).get('sha') if settings.get('git', True) else None, 'memories': memory_stamp(project),
        'overlay': overlay.stamp(project),
    }
    h = hashlib.sha256(json.dumps(head, sort_keys=True).encode())
    for rel in sorted(source_files(root, exclude, include_tests, settings)):
        try:
            st = os.stat(os.path.join(root, rel))
        except OSError:
            continue
        h.update(f'{rel}\0{st.st_size}\0{st.st_mtime_ns if mtimes else 0}\n'.encode('utf-8', 'surrogateescape'))
    return h.hexdigest()


@contextlib.contextmanager
def project_lock(project):
    path = os.path.join(store.project_dir(project), '.lock')
    with open(path, 'a+b') as fh:
        if fcntl:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        elif msvcrt:
            while True:
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    continue
        try:
            yield
        finally:
            if fcntl:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            elif msvcrt:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


def previous_graph(project):
    try:
        return store.load_version(project)
    except CortexError:
        return None


def analyze_and_save(root, project, origin, exclude=(), include_tests=None, still_wanted=None, scip=None):
    started = time.perf_counter()
    settings = project_config.load(root)
    if include_tests is None:
        include_tests = bool(settings.get('include_tests'))
    git = settings.get('git', True)
    commit = git_commit(str(root))
    timings = {}
    with project_lock(project):
        hist = store.load_history(project)
        last = hist['versions'][-1] if hist['versions'] else None
        print_ = fingerprint(root, exclude, include_tests, settings, commit, mtimes=(origin or {}).get('type') != 'github', project=project)
        timings['fingerprint'] = round(time.perf_counter() - started, 3)
        previous = previous_graph(project) if last else None
        if previous is not None and not scip and (last.get('options') or {}).get('fingerprint') == print_:
            previous['unchanged'] = True
            timings['total'] = round(time.perf_counter() - started, 3)
            previous.setdefault('stats', {}).update(seconds=round(timings['total'], 2), timings=timings)
            return previous
        mark = time.perf_counter()
        graph = analyze(root, project, exclude, skip_tests=not include_tests, git=git, previous=previous, scip=scip,
                        memories=brain.memories(project, include_inactive=True), overlay_ops=overlay.load(project))
        timings['analyze'] = round(time.perf_counter() - mark, 3)
        if still_wanted is not None and not still_wanted():
            return None
        mark = time.perf_counter()
        graph['stats']['seconds'] = round(time.perf_counter() - started, 1)
        options = {'exclude': list(exclude), 'tests': include_tests, 'fingerprint': print_}
        store.save_version(graph, origin, options, commit, previous=previous)
        store.write_exports(graph, lambda g: export_markdown(g) + overlay.markdown(g), export_json)
        timings['save'] = round(time.perf_counter() - mark, 3)
    timings['total'] = round(time.perf_counter() - started, 3)
    graph['unchanged'] = False
    graph['stats'].update(seconds=round(timings['total'], 1), timings=timings)
    return graph


def analyze_source(source, name=None, exclude=(), include_tests=None, scip=None, copy=False):
    if not isinstance(source, str) or not source.strip():
        raise InvalidInput('indica una carpeta local o una URL https://github.com/usuario/repo')
    source = source.strip()
    exclude = normalize_excludes(exclude)
    github = parse_github(source)
    if github:
        project = store.slug(name or github[1])
        root = clone_github(*github, store.source_dir(project))
        origin = {'type': 'github', 'url': github_url(*github)}
    elif re.match(r'^[a-z]+://', source, re.I):
        raise InvalidInput('solo se aceptan URLs como https://github.com/usuario/repo')
    else:
        root = os.path.abspath(os.path.expanduser(source))
        if os.path.isfile(root):
            project = store.slug(name or os.path.splitext(os.path.basename(root))[0])
            origin = {'type': 'file', 'path': root}
            root = stage_file(root, project)
        elif not os.path.isdir(root):
            raise NotFound(f'no existe la carpeta o el archivo «{source}»')
        else:
            project = store.slug(name or project_config.load(root).get('name') or os.path.basename(root))
            origin = {'type': 'local', 'path': root}
            if copy:
                origin = {'type': 'import', 'path': root}
                root = stage_folder(root, project)
    if scip and not os.path.isfile(scip):
        raise NotFound(f'no existe el índice SCIP «{scip}»')
    return analyze_and_save(root, project, origin, exclude, include_tests, scip=os.path.abspath(scip) if scip else None)


def stage_file(path, project):
    folder = store.source_dir(project)
    os.makedirs(folder, exist_ok=True)
    shutil.copy2(path, os.path.join(folder, os.path.basename(path)))
    return folder


def stage_folder(path, project):
    folder = store.source_dir(project)
    os.makedirs(folder, exist_ok=True)
    for rel in list_files(path):
        target = os.path.join(folder, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(path, rel), target)
    return folder


def rebuild(project, include_tests=None):
    hist = store.load_history(project)
    origin = hist.get('origin') or {'type': 'brain'}
    last = hist['versions'][-1] if hist['versions'] else {}
    options = last.get('options') or {}
    kind = origin.get('type')
    if kind == 'local' and os.path.isdir(origin.get('path') or ''):
        root = origin['path']
    elif kind == 'file' and os.path.isfile(origin.get('path') or ''):
        root = stage_file(origin['path'], project)
    elif kind == 'local':
        raise NotFound(f'la carpeta de origen «{origin.get("path")}» ya no existe: vuelve a analizarla desde su nueva ubicación')
    else:
        root = store.source_dir(project)
        os.makedirs(root, exist_ok=True)
    tests = options.get('tests') if include_tests is None else include_tests
    return analyze_and_save(root, project, origin, options.get('exclude') or (), tests)


def summary(graph):
    stats = graph['stats']
    return {
        'project': graph['project'],
        'version': graph.get('version'),
        'unchanged': bool(graph.get('unchanged')),
        'stats': {k: stats.get(k) for k in ('files', 'nodes', 'edges', 'communities', 'languages', 'kinds', 'edge_kinds', 'seconds', 'timings', 'warnings_total')},
        'changes': ({'added': 0, 'modified': 0, 'removed': 0} if graph.get('unchanged')
                    else {k: len(v) for k, v in (graph.get('changes') or {}).items()}),
        'communities': [{'id': c['id'], 'name': c['name'], 'size': c['size']} for c in graph['communities']],
        'warnings': (stats.get('warnings') or [])[:10],
        'report': os.path.join(store.project_dir(graph['project']), 'grafo.md'),
    }
