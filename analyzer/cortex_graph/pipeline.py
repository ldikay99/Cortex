import base64
import os
import re
import shutil
import subprocess
import time

from . import store
from .analyze import analyze, export_json, export_markdown
from .errors import CortexError, InvalidInput, NotFound

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


def analyze_and_save(root, project, origin, exclude=(), include_tests=False, still_wanted=None):
    started = time.time()
    graph = analyze(root, project, exclude, skip_tests=not include_tests)
    graph['stats']['seconds'] = round(time.time() - started, 1)
    if still_wanted is not None and not still_wanted():
        return None
    store.save_version(graph, origin, {'exclude': list(exclude), 'tests': include_tests}, git_commit(str(root)))
    store.write_exports(graph, export_markdown, export_json)
    return graph


def analyze_source(source, name=None, exclude=(), include_tests=False):
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
        if not os.path.isdir(root):
            raise NotFound(f'no existe la carpeta «{source}»')
        project = store.slug(name or os.path.basename(root))
        origin = {'type': 'local', 'path': root}
    return analyze_and_save(root, project, origin, exclude, include_tests)


def summary(graph):
    stats = graph['stats']
    return {
        'project': graph['project'],
        'version': graph.get('version'),
        'stats': {k: stats.get(k) for k in ('files', 'nodes', 'edges', 'communities', 'languages', 'kinds', 'edge_kinds', 'seconds', 'warnings_total')},
        'changes': {k: len(v) for k, v in (graph.get('changes') or {}).items()},
        'communities': [{'id': c['id'], 'name': c['name'], 'size': c['size']} for c in graph['communities']],
        'warnings': (stats.get('warnings') or [])[:10],
        'report': os.path.join(store.project_dir(graph['project']), 'grafo.md'),
    }
