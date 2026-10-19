import os
import re
import subprocess
import time
from pathlib import Path

from . import config as project_config, pipeline, store
from .analyze import SKIP_DIR_SUFFIXES, SKIP_DIRS, maybe_script, wanted
from .errors import CortexError, InvalidInput, NotFound

POLL = 1.0
HOOKS = ('post-commit', 'post-merge', 'post-checkout')
BEGIN = '# >>> cortex'
END = '# <<< cortex'
BLOCK_RE = re.compile(r'\n?' + re.escape(BEGIN) + r'\n.*?' + re.escape(END) + r'\n?', re.S)
CONFIG_FILES = (project_config.CONFIG_FILE, project_config.IGNORE_FILE)


def local_root(source):
    if not isinstance(source, str) or not source.strip():
        raise InvalidInput('indica la carpeta local que quieres vigilar')
    if re.match(r'^[a-z]+://', source.strip(), re.I):
        raise InvalidInput('solo se pueden vigilar carpetas locales')
    root = os.path.abspath(os.path.expanduser(source.strip()))
    if not os.path.isdir(root):
        raise NotFound(f'no existe la carpeta «{source}»')
    return root


def git(root, *args):
    try:
        res = subprocess.run(['git', '-C', root, *args], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return res.stdout if res.returncode == 0 else None


def git_files(root):
    out = git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard')
    if out is None:
        return None
    return sorted({p for p in out.decode('utf-8', 'surrogateescape').split('\0') if p})


def walk_files(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.endswith(SKIP_DIR_SUFFIXES))
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, '/')
        out.extend(name if rel_dir == '.' else f'{rel_dir}/{name}' for name in filenames)
    return sorted(out)


def relevant(rel, settings):
    parts = rel.split('/')
    if any(p in SKIP_DIRS or p.endswith(SKIP_DIR_SUFFIXES) for p in parts[:-1]):
        return False
    if rel in CONFIG_FILES:
        return True
    return (wanted(rel) or maybe_script(rel)) and not project_config.ignored(settings, rel)


def snapshot(root):
    try:
        settings = project_config.load(root)
    except CortexError:
        settings = project_config.defaults()
    files = git_files(root)
    if files is None:
        files = walk_files(root)
    state = {}
    for rel in files:
        if not relevant(rel, settings):
            continue
        try:
            st = os.stat(os.path.join(root, rel))
        except OSError:
            continue
        state[rel] = (st.st_size, st.st_mtime_ns)
    for rel in CONFIG_FILES:
        try:
            st = os.stat(os.path.join(root, rel))
            state[rel] = (st.st_size, st.st_mtime_ns)
        except OSError:
            pass
    return state


def status_line(result=None, error=None):
    stamp = time.strftime('%H:%M:%S')
    if error:
        return f'{stamp} error: {error}'
    st, ch = result['stats'], result['changes']
    if result.get('unchanged'):
        return f"{stamp} {result['project']} v{result['version']} · sin cambios · {st.get('seconds')} s"
    return (f"{stamp} {result['project']} v{result['version']} · {st.get('files')} archivos · {st.get('nodes')} nodos · "
            f"{ch.get('added', 0)} nuevos · {ch.get('modified', 0)} modificados · {ch.get('removed', 0)} eliminados · {st.get('seconds')} s")


def analyze_once(root, name, include_tests):
    try:
        result = pipeline.summary(pipeline.analyze_source(root, name, [], include_tests))
    except CortexError as exc:
        print(status_line(error=exc.message), flush=True)
        return None
    print(status_line(result), flush=True)
    return result


def pause(seconds):
    time.sleep(seconds)


def settle(root, state, debounce):
    quiet_since = time.monotonic()
    while time.monotonic() - quiet_since < debounce:
        pause(min(POLL, debounce))
        now = snapshot(root)
        if now != state:
            state, quiet_since = now, time.monotonic()
    return state


def run(source, name=None, debounce=1.5, include_tests=None, once=False):
    root = local_root(source)
    if once:
        return analyze_once(root, name, include_tests)
    print(f'vigilando {root} (Ctrl+C para salir)', flush=True)
    state = snapshot(root)
    last = analyze_once(root, name, include_tests)
    try:
        while True:
            pause(POLL)
            now = snapshot(root)
            if now == state:
                continue
            state = settle(root, now, debounce)
            last = analyze_once(root, name, include_tests)
    except KeyboardInterrupt:
        print('vigilancia detenida', flush=True)
    return last


def hooks_dir(repo):
    root = local_root(repo)
    out = git(root, 'rev-parse', '--git-path', 'hooks')
    if out is None:
        raise CortexError(f'«{repo}» no es un repositorio git')
    path = Path(out.decode('utf-8', 'surrogateescape').strip())
    return root, path if path.is_absolute() else Path(root) / path


def sh_quote(text):
    return '"' + re.sub(r'(["\\$`])', r'\\\1', text) + '"'


def hook_block(root, name):
    repo = Path(root).resolve().as_posix()
    return f'{BEGIN}\ncortex analyze {sh_quote(repo)} --name {sh_quote(name)} --quiet >/dev/null 2>&1 &\n{END}\n'


def insert_block(text, block):
    if BLOCK_RE.search(text):
        return BLOCK_RE.sub(lambda m: ('\n' if m.group(0).startswith('\n') else '') + block, text, count=1)
    lines = text.rstrip('\n').split('\n')
    if len(lines) > 1 and re.match(r'^\s*exit(\s+0)?\s*$', lines[-1]):
        return '\n'.join(lines[:-1]) + '\n' + block + lines[-1] + '\n'
    return text.rstrip('\n') + '\n' + block


def install_hook(repo, name=None):
    root, folder = hooks_dir(repo)
    if not name:
        try:
            name = project_config.load(root).get('name')
        except CortexError:
            name = None
    name = store.slug(name or os.path.basename(root))
    block = hook_block(root, name)
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for hook in HOOKS:
        path = folder / hook
        text = path.read_text(encoding='utf-8', errors='surrogateescape') if path.exists() else ''
        updated = insert_block(text, block) if text.strip() else f'#!/bin/sh\n{block}'
        if updated != text:
            path.write_text(updated, encoding='utf-8', errors='surrogateescape', newline='\n')
        path.chmod(path.stat().st_mode | 0o111)
        paths.append(str(path))
    return paths[0]


def uninstall_hook(repo):
    _, folder = hooks_dir(repo)
    removed = []
    for hook in HOOKS:
        path = folder / hook
        if not path.is_file():
            continue
        text = path.read_text(encoding='utf-8', errors='surrogateescape')
        if not BLOCK_RE.search(text):
            continue
        rest = BLOCK_RE.sub('\n', text).strip('\n')
        if rest.strip() in ('', '#!/bin/sh'):
            path.unlink()
        else:
            path.write_text(rest + '\n', encoding='utf-8', errors='surrogateescape', newline='\n')
        removed.append(str(path))
    return removed
