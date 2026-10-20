import json
import os
import re
import stat
import sys
import threading
import tomllib

from .errors import CortexError, InvalidInput

NAME = 'cortex'
REPO = 'git+https://github.com/ldikay99/Cortex#subdirectory=analyzer'
MODES = {
    'docker': ('docker', ['exec', '-i', 'cortex-analyzer', 'cortex', 'mcp']),
    'uvx': ('uvx', ['--from', REPO, 'cortex', 'mcp']),
    'local': ('cortex', ['mcp']),
}
HOME = '~'
APPDATA = '%APPDATA%'
SUPPORT = '~/Library/Application Support'
XDG = '~/.config'

CLIENTS = {
    'claude-code': {
        'label': 'Claude Code', 'format': 'json', 'key': 'mcpServers',
        'project': '.mcp.json', 'user': {'any': '~/.claude.json'},
    },
    'claude-desktop': {
        'label': 'Claude Desktop', 'format': 'json', 'key': 'mcpServers',
        'user': {'linux': f'{XDG}/Claude/claude_desktop_config.json', 'darwin': f'{SUPPORT}/Claude/claude_desktop_config.json',
                 'windows': f'{APPDATA}\\Claude\\claude_desktop_config.json'},
    },
    'cursor': {
        'label': 'Cursor', 'format': 'json', 'key': 'mcpServers', 'type': True,
        'project': '.cursor/mcp.json', 'user': {'any': '~/.cursor/mcp.json'},
    },
    'vscode': {
        'label': 'VS Code (GitHub Copilot)', 'format': 'json', 'key': 'servers', 'type': True,
        'project': '.vscode/mcp.json',
        'user': {'linux': f'{XDG}/Code/User/mcp.json', 'darwin': f'{SUPPORT}/Code/User/mcp.json', 'windows': f'{APPDATA}\\Code\\User\\mcp.json'},
    },
    'windsurf': {
        'label': 'Windsurf', 'format': 'json', 'key': 'mcpServers',
        'user': {'any': '~/.codeium/windsurf/mcp_config.json'},
    },
    'devin': {
        'label': 'Devin Desktop / Devin CLI', 'format': 'json', 'key': 'mcpServers',
        'project': '.devin/mcp_config.json',
        'user': {'linux': f'{XDG}/devin/mcp_config.json', 'darwin': f'{XDG}/devin/mcp_config.json', 'windows': f'{APPDATA}\\devin\\mcp_config.json'},
    },
    'zed': {
        'label': 'Zed', 'format': 'json', 'key': 'context_servers', 'env': True,
        'project': '.zed/settings.json',
        'user': {'linux': f'{XDG}/zed/settings.json', 'darwin': f'{XDG}/zed/settings.json', 'windows': f'{APPDATA}\\Zed\\settings.json'},
    },
    'codex': {
        'label': 'Codex CLI', 'format': 'toml', 'key': 'mcp_servers',
        'project': '.codex/config.toml', 'user': {'any': '~/.codex/config.toml'},
    },
    'gemini-cli': {
        'label': 'Gemini CLI', 'format': 'json', 'key': 'mcpServers',
        'project': '.gemini/settings.json', 'user': {'any': '~/.gemini/settings.json'},
    },
    'continue': {
        'label': 'Continue', 'format': 'yaml', 'key': 'mcpServers',
        'project': '.continue/mcpServers/cortex.yaml', 'user': {'any': '~/.continue/mcpServers/cortex.yaml'},
    },
    'cline': {
        'label': 'Cline', 'format': 'json', 'key': 'mcpServers', 'cline': True,
        'user': {'linux': f'{XDG}/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json',
                 'darwin': f'{SUPPORT}/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json',
                 'windows': f'{APPDATA}\\Code\\User\\globalStorage\\saoudrizwan.claude-dev\\settings\\cline_mcp_settings.json'},
    },
}
ALIASES = {'claude': 'claude-code', 'copilot': 'vscode', 'vs-code': 'vscode', 'gemini': 'gemini-cli', 'codex-cli': 'codex'}
TOML_HEADER = re.compile(r'^\s*\[\[?\s*([^\]]+?)\s*\]\]?\s*(?:#.*)?$')


def current_system():
    if sys.platform.startswith('win'):
        return 'windows'
    return 'darwin' if sys.platform == 'darwin' else 'linux'


def spec_for(client):
    if not isinstance(client, str) or not client.strip():
        raise InvalidInput(f'falta el cliente: usa {", ".join(CLIENTS)}')
    name = ALIASES.get(client.strip().lower(), client.strip().lower())
    if name not in CLIENTS:
        raise InvalidInput(f'cliente desconocido «{client}»: usa {", ".join(CLIENTS)}')
    return name, CLIENTS[name]


def command_for(mode):
    if mode not in MODES:
        raise InvalidInput(f'modo desconocido «{mode}»: usa {", ".join(MODES)}')
    command, args = MODES[mode]
    return command, list(args)


def pick_scope(spec, scope):
    if scope in (None, ''):
        return 'project' if 'project' in spec else 'user'
    if scope not in ('project', 'user'):
        raise InvalidInput(f'alcance desconocido «{scope}»: usa project o user')
    return scope if scope in spec else 'user'


def config_path(spec, scope, system):
    if scope == 'project':
        return spec['project']
    paths = spec['user']
    return paths.get(system) or paths['any']


def entry(spec, mode):
    command, args = command_for(mode)
    item = {'type': 'stdio'} if spec.get('type') else {}
    item.update(command=command, args=args)
    if spec.get('env'):
        item['env'] = {}
    if spec.get('cline'):
        item.update(env={}, disabled=False, autoApprove=[])
    return item


def toml_value(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, list):
        return '[' + ', '.join(toml_value(v) for v in value) + ']'
    return json.dumps(value, ensure_ascii=False)


def toml_block(item):
    return f'[mcp_servers.{NAME}]\n' + ''.join(f'{k} = {toml_value(v)}\n' for k, v in item.items())


def yaml_document(item):
    args = ', '.join(json.dumps(a, ensure_ascii=False) for a in item['args'])
    return ('name: Cortex\nversion: 1.2.0\nschema: v1\nmcpServers:\n'
            f'  - name: {NAME}\n    type: stdio\n    command: {item["command"]}\n    args: [{args}]\n')


def render(spec, item):
    if spec['format'] == 'toml':
        return toml_block(item)
    if spec['format'] == 'yaml':
        return yaml_document(item)
    return json.dumps({spec['key']: {NAME: item}}, ensure_ascii=False, indent=2) + '\n'


def shell_join(command, args):
    return ' '.join([command] + [a if re.fullmatch(r'[\w@%+=:,./-]+', a) else "'" + a.replace("'", "'\\''") + "'" for a in args])


def cli_for(name, mode, scope):
    command, args = command_for(mode)
    line = shell_join(command, args)
    if name == 'claude-code':
        return f'claude mcp add --transport stdio --scope {"project" if scope == "project" else "user"} {NAME} -- {line}'
    if name == 'codex':
        return f'codex mcp add {NAME} -- {line}'
    if name == 'gemini-cli':
        return f'gemini mcp add --scope {scope} {NAME} {line}'
    if name == 'devin':
        return f'devin mcp add --scope {scope} {NAME} -- {line}'
    return None


def snippet(client, mode='docker', scope=None, system=None):
    name, spec = spec_for(client)
    scope = pick_scope(spec, scope)
    item = entry(spec, mode)
    result = {'client': name, 'label': spec['label'], 'mode': mode, 'scope': scope,
              'path': config_path(spec, scope, system or current_system()), 'format': spec['format'],
              'content': render(spec, item), 'entry': item}
    cli = cli_for(name, mode, scope)
    if cli:
        result['cli'] = cli
    return result


def snippets(mode='docker', system=None):
    return [snippet(name, mode, None, system) for name in CLIENTS]


def expand(path, system):
    if path.startswith(APPDATA):
        base = os.environ.get('APPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming')
        return os.path.join(base, *path[len(APPDATA):].strip('\\').split('\\'))
    if path.startswith(XDG + '/') and system == 'linux' and os.environ.get('XDG_CONFIG_HOME'):
        return os.path.join(os.environ['XDG_CONFIG_HOME'], *path[len(XDG) + 1:].split('/'))
    return os.path.expanduser(path)


def strip_jsonc(text):
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == '\\' else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith('//', i):
            while i < n and text[i] != '\n':
                i += 1
        elif text.startswith('/*', i):
            end = text.find('*/', i + 2)
            i = n if end < 0 else end + 2
        else:
            out.append(ch)
            i += 1
    return re.sub(r',(\s*[}\]])', r'\1', ''.join(out))


def parse_json(text, path):
    if not text.strip():
        return {}, False
    try:
        return json.loads(text), False
    except ValueError:
        pass
    try:
        return json.loads(strip_jsonc(text)), True
    except ValueError as exc:
        raise CortexError(f'«{path}» no es JSON válido: corrígelo o añade «{NAME}» a mano') from exc


def read_text(path):
    try:
        with open(path, encoding='utf-8-sig') as f:
            return f.read()
    except FileNotFoundError:
        return None


def write_atomic(path, text):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = f'{path}.{os.getpid()}-{threading.get_ident()}.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        if os.path.exists(path):
            os.chmod(tmp, stat.S_IMODE(os.stat(path).st_mode))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def indent_of(text):
    match = re.search(r'^\{\s*\n([ \t]+)\S', text or '')
    if not match:
        return 2
    return '\t' if '\t' in match.group(1) else len(match.group(1))


def merge_json(spec, path, text, item):
    data, lossy = parse_json(text or '', path)
    if not isinstance(data, dict):
        raise CortexError(f'«{path}» no contiene un objeto JSON')
    servers = data.get(spec['key'])
    if servers is None:
        servers = data[spec['key']] = {}
    if not isinstance(servers, dict):
        raise CortexError(f'«{spec["key"]}» en «{path}» no es un objeto')
    servers[NAME] = item
    return json.dumps(data, ensure_ascii=False, indent=indent_of(text)) + '\n', lossy


def toml_table(header):
    return [p.strip().strip('"\'') for p in header.split('.')]


def merge_toml(path, text, item):
    text = text or ''
    try:
        before = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise CortexError(f'«{path}» no es TOML válido: corrígelo o añade [mcp_servers.{NAME}] a mano') from exc
    kept, skipping = [], False
    for line in text.splitlines(keepends=True):
        header = TOML_HEADER.match(line)
        if header:
            skipping = toml_table(header.group(1))[:2] == ['mcp_servers', NAME]
        if not skipping:
            kept.append(line)
    body = ''.join(kept).rstrip()
    merged = (body + '\n\n' if body else '') + toml_block(item)
    try:
        after = tomllib.loads(merged)
    except tomllib.TOMLDecodeError as exc:
        raise CortexError(f'no pude fusionar «{path}» sin riesgo: añade [mcp_servers.{NAME}] a mano') from exc
    expected = {**before, 'mcp_servers': {**(before.get('mcp_servers') or {}), NAME: item}}
    if after != expected:
        raise CortexError(f'no pude fusionar «{path}» sin riesgo: añade [mcp_servers.{NAME}] a mano')
    return merged, False


def install(client, mode='docker', scope='project', root='.', system=None):
    name, spec = spec_for(client)
    system = system or current_system()
    scope = pick_scope(spec, scope)
    shown = config_path(spec, scope, system)
    path = os.path.abspath(os.path.join(root, shown) if scope == 'project' else expand(shown, system))
    item = entry(spec, mode)
    text = read_text(path)
    if spec['format'] == 'yaml':
        merged, lossy = render(spec, item), False
    elif spec['format'] == 'toml':
        merged, lossy = merge_toml(path, text, item)
    else:
        merged, lossy = merge_json(spec, path, text, item)
    if merged == text:
        return path
    if lossy:
        write_atomic(path + '.bak', text)
    write_atomic(path, merged)
    return path
