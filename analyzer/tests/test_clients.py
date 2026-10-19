import json
import os
import tomllib

import pytest

from cortex_graph import clients
from cortex_graph.errors import CortexError, InvalidInput

DOCKER = ['exec', '-i', 'cortex-analyzer', 'cortex', 'mcp']
JSON_CLIENTS = [name for name, spec in clients.CLIENTS.items() if spec['format'] == 'json']


@pytest.fixture
def home(tmp_path, monkeypatch):
    path = tmp_path / 'home'
    path.mkdir()
    monkeypatch.setenv('HOME', str(path))
    monkeypatch.setenv('USERPROFILE', str(path))
    monkeypatch.setenv('APPDATA', str(path / 'AppData' / 'Roaming'))
    monkeypatch.delenv('XDG_CONFIG_HOME', raising=False)
    return path


def target(name, scope, root, system):
    spec = clients.CLIENTS[name]
    scope = clients.pick_scope(spec, scope)
    shown = clients.config_path(spec, scope, system)
    return os.path.abspath(os.path.join(root, shown) if scope == 'project' else clients.expand(shown, system))


def test_snippets_cover_every_client():
    assert set(clients.CLIENTS) >= {'claude-code', 'claude-desktop', 'cursor', 'vscode', 'windsurf', 'zed', 'codex',
                                    'gemini-cli', 'continue', 'cline'}
    for item in clients.snippets('docker', 'linux'):
        assert item['entry']['args'] == DOCKER and item['entry']['command'] == 'docker'
        assert item['format'] in ('json', 'toml', 'yaml') and item['content'].endswith('\n')
        if item['format'] == 'json':
            data = json.loads(item['content'])
            assert data[clients.CLIENTS[item['client']]['key']]['cortex'] == item['entry']
        elif item['format'] == 'toml':
            assert tomllib.loads(item['content'])['mcp_servers']['cortex'] == item['entry']


def test_snippet_shapes_and_paths():
    assert clients.snippet('claude-code')['path'] == '.mcp.json'
    assert clients.snippet('claude-code', scope='user')['path'] == '~/.claude.json'
    assert clients.snippet('claude')['client'] == 'claude-code' and clients.snippet('copilot')['client'] == 'vscode'
    desktop = {s: clients.snippet('claude-desktop', system=s)['path'] for s in ('linux', 'darwin', 'windows')}
    assert desktop == {'linux': '~/.config/Claude/claude_desktop_config.json',
                       'darwin': '~/Library/Application Support/Claude/claude_desktop_config.json',
                       'windows': '%APPDATA%\\Claude\\claude_desktop_config.json'}
    assert clients.snippet('claude-desktop', scope='project')['scope'] == 'user'
    vscode = json.loads(clients.snippet('vscode')['content'])
    assert vscode == {'servers': {'cortex': {'type': 'stdio', 'command': 'docker', 'args': DOCKER}}}
    assert json.loads(clients.snippet('cursor')['content'])['mcpServers']['cortex']['type'] == 'stdio'
    zed = json.loads(clients.snippet('zed')['content'])
    assert zed == {'context_servers': {'cortex': {'command': 'docker', 'args': DOCKER, 'env': {}}}}
    cline = json.loads(clients.snippet('cline', system='darwin')['content'])['mcpServers']['cortex']
    assert cline['disabled'] is False and cline['autoApprove'] == []
    assert clients.snippet('windsurf')['path'] == '~/.codeium/windsurf/mcp_config.json'
    assert clients.snippet('gemini-cli')['path'] == '.gemini/settings.json'
    codex = clients.snippet('codex', 'uvx')
    assert codex['path'] == '.codex/config.toml' and codex['content'].startswith('[mcp_servers.cortex]\ncommand = "uvx"\n')
    assert codex['entry']['args'] == ['--from', clients.REPO, 'cortex', 'mcp']
    cont = clients.snippet('continue', 'local')
    assert cont['path'] == '.continue/mcpServers/cortex.yaml' and 'schema: v1' in cont['content']
    assert 'command: cortex\n    args: ["mcp"]' in cont['content']
    assert clients.snippet('claude-code')['cli'] == 'claude mcp add --transport stdio --scope project cortex -- docker exec -i cortex-analyzer cortex mcp'
    assert "'git+https://github.com/ldikay99/Cortex#subdirectory=analyzer'" in clients.snippet('claude-code', 'uvx')['cli']


def test_invalid_arguments(tmp_path):
    for call in (lambda: clients.snippet('emacs'), lambda: clients.snippet('cursor', 'podman'),
                 lambda: clients.snippet(''), lambda: clients.install('cursor', scope='team', root=str(tmp_path))):
        with pytest.raises(InvalidInput):
            call()


@pytest.mark.parametrize('name', JSON_CLIENTS)
@pytest.mark.parametrize('scope', ['project', 'user'])
def test_json_merge_keeps_everything_else(name, scope, tmp_path, home):
    root = tmp_path / 'repo'
    root.mkdir()
    spec = clients.CLIENTS[name]
    path = target(name, scope, str(root), 'linux')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    original = {'theme': 'dark', 'nested': {'a': [1, 2]},
                spec['key']: {'other': {'command': 'node', 'args': ['x.js']}, 'cortex': {'command': 'viejo'}}}
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(original, f, indent=4)
    os.chmod(path, 0o600)
    written = clients.install(name, 'docker', scope, str(root), 'linux')
    assert written == path
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    assert data['theme'] == 'dark' and data['nested'] == {'a': [1, 2]}
    assert data[spec['key']]['other'] == {'command': 'node', 'args': ['x.js']}
    assert data[spec['key']]['cortex'] == clients.entry(spec, 'docker')
    assert list(data) == ['theme', 'nested', spec['key']]
    if os.name == 'posix':
        assert os.stat(path).st_mode & 0o777 == 0o600
    text = open(path, encoding='utf-8').read()
    assert text.startswith('{\n    "theme"')
    stamp = os.stat(path).st_mtime_ns
    assert clients.install(name, 'docker', scope, str(root), 'linux') == path
    assert open(path, encoding='utf-8').read() == text and os.stat(path).st_mtime_ns == stamp
    assert not [p for p in os.listdir(os.path.dirname(path)) if p.endswith('.tmp')]


@pytest.mark.parametrize('name', list(clients.CLIENTS))
def test_install_creates_missing_config(name, tmp_path, home):
    root = tmp_path / 'repo'
    root.mkdir()
    path = clients.install(name, 'local', 'project', str(root), 'linux')
    assert os.path.isfile(path)
    spec = clients.CLIENTS[name]
    text = open(path, encoding='utf-8').read()
    assert text == clients.snippet(name, 'local', 'project', 'linux')['content']
    if 'project' in spec:
        assert path.startswith(str(root))
    else:
        assert path.startswith(str(home))


def test_json_with_comments_is_merged_with_backup(tmp_path, home):
    root = tmp_path / 'repo'
    path = root / '.zed' / 'settings.json'
    path.parent.mkdir(parents=True)
    original = ('// Zed settings\n{\n  /* tema */\n  "theme": "One Dark", // oscuro\n  "url": "http://x//y",\n'
                '  "context_servers": {\n    "other": {"command": "a", "args": [],},\n  },\n}\n')
    path.write_text(original, encoding='utf-8')
    clients.install('zed', 'docker', 'project', str(root))
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['theme'] == 'One Dark' and data['url'] == 'http://x//y'
    assert data['context_servers']['other'] == {'command': 'a', 'args': []}
    assert data['context_servers']['cortex']['args'] == DOCKER
    assert (root / '.zed' / 'settings.json.bak').read_text(encoding='utf-8') == original


def test_broken_json_is_never_overwritten(tmp_path):
    path = tmp_path / '.cursor' / 'mcp.json'
    path.parent.mkdir()
    path.write_text('{"mcpServers": {"other": ', encoding='utf-8')
    with pytest.raises(CortexError):
        clients.install('cursor', root=str(tmp_path))
    assert path.read_text(encoding='utf-8') == '{"mcpServers": {"other": '
    path.write_text('{"mcpServers": []}', encoding='utf-8')
    with pytest.raises(CortexError):
        clients.install('cursor', root=str(tmp_path))
    path.write_text('[1]', encoding='utf-8')
    with pytest.raises(CortexError):
        clients.install('cursor', root=str(tmp_path))


def test_toml_merge_replaces_only_cortex(tmp_path, home):
    path = home / '.codex' / 'config.toml'
    path.parent.mkdir()
    original = ('# mi config\nmodel = "o4"\n\n[mcp_servers.other]\ncommand = "node"\nargs = ["x.js"]\n\n'
                '[mcp_servers.cortex]\ncommand = "viejo"\n\n[mcp_servers.cortex.env]\nTOKEN_NAME = "x"\n\n'
                '[mcp_servers.cortex-extra]\ncommand = "otro"\n\n[profiles.fast]\nmodel = "mini"  # rapido\n')
    path.write_text(original, encoding='utf-8')
    clients.install('codex', 'uvx', 'user')
    text = path.read_text(encoding='utf-8')
    data = tomllib.loads(text)
    assert data['model'] == 'o4' and data['profiles'] == {'fast': {'model': 'mini'}}
    assert data['mcp_servers']['other'] == {'command': 'node', 'args': ['x.js']}
    assert data['mcp_servers']['cortex-extra'] == {'command': 'otro'}
    assert data['mcp_servers']['cortex'] == {'command': 'uvx', 'args': ['--from', clients.REPO, 'cortex', 'mcp']}
    assert '# mi config' in text and '# rapido' in text and 'TOKEN_NAME' not in text
    assert clients.install('codex', 'uvx', 'user') == str(path)
    assert path.read_text(encoding='utf-8') == text


def test_toml_refuses_unsafe_merges(tmp_path, home):
    path = tmp_path / '.codex' / 'config.toml'
    path.parent.mkdir()
    for original in ('[mcp_servers]\ncortex = { command = "viejo" }\n', 'mcp_servers.cortex.command = "viejo"\n', 'model = \n'):
        path.write_text(original, encoding='utf-8')
        with pytest.raises(CortexError):
            clients.install('codex', root=str(tmp_path))
        assert path.read_text(encoding='utf-8') == original


def test_user_paths_follow_system(tmp_path, home, monkeypatch):
    assert clients.install('claude-desktop', system='windows') == str(home / 'AppData' / 'Roaming' / 'Claude' / 'claude_desktop_config.json')
    assert clients.install('claude-desktop', system='darwin') == str(home / 'Library' / 'Application Support' / 'Claude' / 'claude_desktop_config.json')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    assert clients.install('zed', scope='user', system='linux') == str(tmp_path / 'xdg' / 'zed' / 'settings.json')
    assert clients.install('claude-code', scope='user') == str(home / '.claude.json')
