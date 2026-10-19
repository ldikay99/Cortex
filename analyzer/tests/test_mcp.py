import asyncio
import json
import os
import queue
import subprocess
import sys
import threading

import pytest

import cortex_graph
from cortex_graph import __version__, mcp_server, pipeline
from cortex_graph.errors import CortexError, InvalidInput, NotFound

TOOL_NAMES = {'list_projects', 'analyze_project', 'project_overview', 'search_code', 'node_context', 'file_context',
              'community_context', 'find_path', 'impact_analysis', 'changes', 'get_report', 'read_symbol', 'context_for',
              'architecture', 'dependencies', 'endpoints', 'variables', 'review_changes'}


@pytest.fixture
def analyzed(repo, data_dir):
    return mcp_server.analyze_project(str(repo), name='demo', exclude=['docs/guide.md'])


def test_tool_functions(repo, analyzed):
    assert analyzed['project'] == 'demo' and analyzed['version'] == 1 and analyzed['stats']['files'] == 11
    assert analyzed['changes'] == {'added': 0, 'modified': 0, 'removed': 0} and analyzed['report'].endswith('grafo.md')
    again = mcp_server.analyze_project(str(repo), name='demo', include_tests=True)
    assert again['version'] == 2 and again['changes']['added'] >= 1
    projects = mcp_server.list_projects()['projects']
    assert projects[0]['project'] == 'demo' and projects[0]['versions'] == 2
    assert mcp_server.project_overview()['stats']['nodes'] == again['stats']['nodes']
    assert mcp_server.search_code('slugify', kind='function')['results'][0]['name'] == 'slugify'
    assert mcp_server.node_context('create_user', project='demo')['parent']['name'] == 'services.py'
    assert mcp_server.file_context('app/models.py')['symbols'][0]['name'] == 'User'
    assert mcp_server.community_context('0')['community']['id'] == 0
    assert mcp_server.find_path('list_users', 'slugify')['length'] == 2
    assert mcp_server.impact_analysis('slugify', depth=1)['levels'][0]['nodes'][0]['name'] == 'create_user'
    assert mcp_server.changes(since_version=1)['counts']['added'] >= 1
    assert mcp_server.get_report().startswith('# Grafo de conocimiento · demo')
    with pytest.raises(NotFound):
        mcp_server.node_context('zzz-nothing')
    with pytest.raises(InvalidInput):
        mcp_server.analyze_project('ftp://example.com/repo')
    with pytest.raises(NotFound, match='SCIP'):
        mcp_server.analyze_project(str(repo), name='demo', scip=str(repo / 'missing.scip'))
    code = mcp_server.read_symbol('slugify', context=0)
    assert code['code'].startswith('def slugify(text):') and code['file'] == 'app/utils.py'
    ctx = mcp_server.context_for('create a user', budget=1500)
    assert set(ctx) == {'project', 'version', 'query', 'budget', 'tokens_used', 'source', 'markdown', 'items', 'tests'}
    assert ctx['items'][0]['name'] == 'create_user' and ctx['tokens_used'] <= 1500
    arch = mcp_server.architecture()
    assert arch['endpoints']['items'][0]['route'] == 'GET /users'
    assert mcp_server.architecture(section='layers', limit=5)['layers']['limit'] == 5
    assert mcp_server.endpoints()['endpoints']['items'][0]['handlers'][0]['name'] == 'list_users'
    assert 'packages' in mcp_server.dependencies() and 'variables' in mcp_server.variables()
    assert mcp_server.search_code('user', limit=2, offset=1)['offset'] == 1


def test_registered_tools_have_descriptions(analyzed):
    server = mcp_server.build_server()
    tools = asyncio.run(server.list_tools())
    assert {t.name for t in tools} == TOOL_NAMES
    for tool in tools:
        assert tool.description and len(tool.description) > 40
    search = next(t for t in tools if t.name == 'search_code')
    assert set(search.inputSchema['properties']) == {'query', 'project', 'kind', 'limit', 'offset'}
    assert search.inputSchema['required'] == ['query']
    assert search.annotations.readOnlyHint is True
    result = asyncio.run(server.call_tool('search_code', {'query': 'create_user'}))
    blocks, structured = result
    assert structured['results'][0]['key'] == 'f:app/services.py:create_user'


def test_resources_and_prompts(analyzed):
    server = mcp_server.build_server()
    assert [str(r.uri) for r in asyncio.run(server.list_resources())] == ['cortex://projects']
    templates = {t.uriTemplate for t in asyncio.run(server.list_resource_templates())}
    assert templates == {'cortex://{project}/overview', 'cortex://{project}/report', 'cortex://{project}/community/{id}'}
    projects = json.loads(list(asyncio.run(server.read_resource('cortex://projects')))[0].content)
    assert projects['projects'][0]['project'] == 'demo'
    overview = json.loads(list(asyncio.run(server.read_resource('cortex://demo/overview')))[0].content)
    assert overview['project'] == 'demo'
    report = list(asyncio.run(server.read_resource('cortex://demo/report')))[0]
    assert report.content.startswith('# Grafo de conocimiento · demo') and report.mime_type == 'text/markdown'
    community = json.loads(list(asyncio.run(server.read_resource('cortex://demo/community/0')))[0].content)
    assert community['community']['id'] == 0
    prompts = {p.name: p for p in asyncio.run(server.list_prompts())}
    assert set(prompts) == {'orient', 'plan_change', 'review', 'explain'}
    assert [a.name for a in prompts['plan_change'].arguments if a.required] == ['change']
    text = asyncio.run(server.get_prompt('plan_change', {'change': 'rename slugify'})).messages[0].content.text
    assert 'rename slugify' in text and 'impact_analysis' in text and 'context_for' in text
    assert 'review_changes' in asyncio.run(server.get_prompt('review', {'base': 'main'})).messages[0].content.text
    assert 'read_symbol' in asyncio.run(server.get_prompt('explain', {'symbol': 'slugify'})).messages[0].content.text
    assert 'architecture' in asyncio.run(server.get_prompt('orient', {})).messages[0].content.text


def test_review_changes_delegates_and_degrades(analyzed, monkeypatch):
    review = pytest.importorskip('cortex_graph.review')
    calls = []
    monkeypatch.setattr(review, 'review', lambda root, base, head, project, diff_text: calls.append((root, base, head, project, diff_text)) or {'ok': True})
    assert mcp_server.review_changes() == {'ok': True}
    assert mcp_server.review_changes('HEAD', 'WORKTREE', 'demo', '/repo', 'diff --git') == {'ok': True}
    assert calls == [(None, 'HEAD~1', 'HEAD', 'demo', None), ('/repo', 'HEAD', 'WORKTREE', 'demo', 'diff --git')]

    def not_ready(*args):
        raise NotImplementedError

    monkeypatch.setattr(review, 'review', not_ready)
    with pytest.raises(CortexError, match='todavía no'):
        mcp_server.review_changes()
    monkeypatch.delattr(cortex_graph, 'review')
    monkeypatch.setitem(sys.modules, 'cortex_graph.review', None)
    with pytest.raises(CortexError, match='no está disponible'):
        mcp_server.review_changes()


class StdioClient:
    def __init__(self, env):
        self.proc = subprocess.Popen([sys.executable, '-m', 'cortex_graph', 'mcp'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, env=env, text=True, bufsize=1)
        self.lines = queue.Queue()
        threading.Thread(target=self.pump, daemon=True).start()

    def pump(self):
        for line in self.proc.stdout:
            self.lines.put(line)

    def send(self, message):
        self.proc.stdin.write(json.dumps(message) + '\n')
        self.proc.stdin.flush()

    def receive(self, message_id, timeout=60):
        while True:
            message = json.loads(self.lines.get(timeout=timeout))
            if message.get('id') == message_id:
                return message

    def close(self):
        self.proc.stdin.close()
        try:
            return self.proc.wait(timeout=10), self.proc.stderr.read()
        except subprocess.TimeoutExpired:
            self.proc.kill()
            raise


def test_stdio_handshake(repo, data_dir):
    pipeline.analyze_source(str(repo), 'demo')
    client = StdioClient({**os.environ, 'CORTEX_DATA': str(data_dir)})
    try:
        client.send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'pytest', 'version': '1'}}})
        init = client.receive(1)
        assert init['result']['serverInfo']['name'] == 'cortex' and init['result']['serverInfo']['version'] == __version__
        assert {'tools', 'resources', 'prompts'} <= set(init['result']['capabilities'])
        assert 'tools' in init['result']['capabilities'] and 'Córtex' in init['result']['instructions']
        client.send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        client.send({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
        tools = client.receive(2)['result']['tools']
        assert {t['name'] for t in tools} == TOOL_NAMES
        client.send({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'search_code', 'arguments': {'query': 'slugify'}}})
        result = client.receive(3)['result']
        assert result['isError'] is False
        assert result['structuredContent']['results'][0]['key'] == 'f:app/utils.py:slugify'
        assert json.loads(result['content'][0]['text'])['project'] == 'demo'
        client.send({'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'node_context', 'arguments': {'node': 'zzz-nothing'}}})
        failure = client.receive(4)['result']
        assert failure['isError'] is True and 'no encontré' in failure['content'][0]['text']
    finally:
        code, stderr = client.close()
    assert code == 0 and 'Traceback' not in stderr and 'Processing request' not in stderr
