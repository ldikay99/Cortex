import os
import re
import tomllib

from .errors import CortexError

CONFIG_FILE = '.cortex.toml'
IGNORE_FILE = '.cortexignore'
LIST_KEYS = ('exclude', 'ignore', 'roots')
BOOL_KEYS = ('include_tests', 'git')
KNOWN_KEYS = {'name', *LIST_KEYS, *BOOL_KEYS}


def defaults():
    return {'name': None, 'exclude': [], 'ignore': [], 'include_tests': None, 'roots': [], 'git': True, 'ignore_patterns': []}


def char_class(pattern, i):
    j = i + 1
    negate = j < len(pattern) and pattern[j] in '!^'
    if negate:
        j += 1
    body = []
    while j < len(pattern) and (pattern[j] != ']' or not body):
        c = pattern[j]
        if c == '\\' and j + 1 < len(pattern):
            j += 1
            body.append(re.escape(pattern[j]))
        elif c == '-' and body and j + 1 < len(pattern) and pattern[j + 1] != ']':
            body.append('-')
        else:
            body.append(re.escape(c))
        j += 1
    if j >= len(pattern):
        return None, i
    inner = ''.join(body)
    return (f'[^/{inner}]' if negate else f'(?!/)[{inner}]'), j


def translate(pattern):
    out = []
    i, n = 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c == '\\':
            if i + 1 < n:
                out.append(re.escape(pattern[i + 1]))
            i += 2
            continue
        if c == '*':
            j = i
            while j < n and pattern[j] == '*':
                j += 1
            globstar = j - i >= 2 and (i == 0 or pattern[i - 1] == '/') and (j == n or pattern[j] == '/')
            if globstar and j == n:
                out.append('.*')
            elif globstar:
                out.append('(?:.*/)?')
                j += 1
            else:
                out.append('[^/]*')
            i = j
            continue
        if c == '?':
            out.append('[^/]')
        elif c == '[':
            regex, end = char_class(pattern, i)
            if regex is None:
                out.append(re.escape(c))
            else:
                out.append(regex)
                i = end
        else:
            out.append(re.escape(c))
        i += 1
    return ''.join(out)


def escaped_end(text):
    return (len(text) - len(text.rstrip('\\'))) % 2 == 1


def compile_pattern(line):
    line = line.rstrip('\r\n')
    while line.endswith((' ', '\t')) and not escaped_end(line[:-1]):
        line = line[:-1]
    if not line or line.startswith('#'):
        return None
    negate = line.startswith('!')
    if negate:
        line = line[1:]
    dir_only = line.endswith('/')
    line = line.rstrip('/')
    anchored = '/' in line
    line = line.lstrip('/')
    if not line:
        return None
    regex = re.compile(('^' if anchored else '^(?:.*/)?') + translate(line) + '$', re.S)
    return {'pattern': line, 'regex': regex, 'negate': negate, 'dir': dir_only}


def compile_patterns(lines):
    return [p for p in (compile_pattern(line) for line in lines) if p]


def decide(patterns, path, is_dir):
    result = False
    for p in patterns:
        if (is_dir or not p['dir']) and p['regex'].match(path):
            result = not p['negate']
    return result


def ignored(config, rel):
    patterns = (config or {}).get('ignore') or []
    if not patterns:
        return False
    parts = [p for p in str(rel).replace('\\', '/').split('/') if p and p != '.']
    return any(decide(patterns, '/'.join(parts[:i]), i < len(parts)) for i in range(1, len(parts) + 1))


def string_list(data, key):
    value = data.get(key, [])
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise CortexError(f'{CONFIG_FILE}: «{key}» debe ser una lista de textos')
    return value


def read_toml(path):
    try:
        with open(path, 'rb') as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise CortexError(f'{CONFIG_FILE} no es TOML válido ({exc}); corrígelo o bórralo para analizar') from exc
    except UnicodeDecodeError as exc:
        raise CortexError(f'{CONFIG_FILE} debe estar guardado en UTF-8') from exc
    except OSError as exc:
        raise CortexError(f'no se pudo leer {CONFIG_FILE}: {exc.strerror or exc}') from exc
    if isinstance(data.get('cortex'), dict) and not KNOWN_KEYS & set(data):
        data = data['cortex']
    out = defaults()
    for key in LIST_KEYS:
        out[key] = [v.strip() for v in string_list(data, key) if v.strip()]
    out['exclude'] = [e.strip('/') for e in out['exclude'] if e.strip('/')]
    for key in BOOL_KEYS:
        if key in data:
            if not isinstance(data[key], bool):
                raise CortexError(f'{CONFIG_FILE}: «{key}» debe ser true o false')
            out[key] = data[key]
    if 'name' in data:
        if not isinstance(data['name'], str) or not data['name'].strip():
            raise CortexError(f'{CONFIG_FILE}: «name» debe ser un texto no vacío')
        out['name'] = data['name'].strip()
    return out


def read_lines(path):
    try:
        with open(path, encoding='utf-8-sig', errors='replace') as fh:
            return fh.read().splitlines()
    except OSError:
        return []


def load(root):
    root = str(root)
    path = os.path.join(root, CONFIG_FILE)
    config = read_toml(path) if os.path.isfile(path) else defaults()
    lines = read_lines(os.path.join(root, IGNORE_FILE)) + config['ignore']
    config['ignore_patterns'] = lines
    config['ignore'] = compile_patterns(lines)
    return config
