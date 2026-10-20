import asyncio
import http.client
import json
import threading
from types import SimpleNamespace as NS

import pytest

from conftest import by_key, edge_set, write_repo
from cortex_graph import cli, llm, mcp_server, overlay, pipeline, query, server, store
from cortex_graph.analyze import analyze
from cortex_graph.errors import CortexError, InvalidInput, NotFound


@pytest.fixture
def demo(repo, data_dir):
    pipeline.analyze_source(str(repo), 'demo')
    return 'demo'


def op(action, oid, **fields):
    return {'op': action, 'id': oid, 'at': '2026-01-01T00:00:00Z', 'origin': 'agent', **fields}


def test_fold_updates_removes_and_cascades():
    ops = [
        op('node', 'a:pagos', kind='component', name='Pagos', summary='v1'),
        op('node', 'a:pagos', summary='v2', tags=['core']),
        op('node', 'a:web', kind='component', name='Web'),
        op('edge', 'rel:1', a='a:web', b='a:pagos', kind='uses'),
        op('edge', 'rel:2', a='a:web', b='m:x.py', kind='uses'),
        op('note', 'm:x.py', summary='entrada'),
        op('remove', 'a:pagos'),
        op('remove', 'm:x.py'),
    ]
    state = overlay.fold(ops)
    assert set(state['nodes']) == {'a:web'} and set(state['edges']) == {'rel:2'} and state['notes'] == {}
    state = overlay.fold(ops[:2])
    assert state['nodes']['a:pagos']['summary'] == 'v2' and state['nodes']['a:pagos']['name'] == 'Pagos'
    assert state['nodes']['a:pagos']['created'] == '2026-01-01T00:00:00Z'


def test_add_validates_and_reports_rejections(demo):
    r = overlay.add('demo', nodes=[
        {'name': 'Pagos', 'kind': 'componente', 'summary': 'Cobra pedidos. api_key = "sk_live_abcdefghijklmnop1234"',
         'contains': ['app/services.py'], 'tags': ['servicio']},
        {'name': 'Pagos', 'kind': 'flow'},
        {'kind': 'component'},
        {'name': 'X', 'kind': 'planeta'},
        {'name': 'Y', 'kind': 'component', 'file': '../fuera.py'},
        {'name': 'Z', 'kind': 'component', 'tags': ['x' * 50]},
        {'id': 'f:app/utils.py:slugify', 'summary': 'Normaliza nombres'},
        {'id': 'f:app/utils.py:slugify'},
    ], edges=[
        {'a': 'Pagos', 'b': 'create_user', 'kind': 'call', 'label': 'cobra al crear'},
        {'a': 'Pagos', 'b': 'no-existe', 'kind': 'uses'},
        {'a': 'create_user', 'b': 'slugify', 'kind': 'contains'},
        {'a': 'Pagos', 'b': 'Pagos'},
    ], annotations=[{'id': 'app/api.py', 'summary': 'API HTTP', 'tags': ['api']}, {'id': 'app/api.py'}], rebuild=False)
    assert r['created'] == ['a:pagos', 'a:flow-pagos'] and r['annotated'] == ['f:app/utils.py:slugify', 'm:app/api.py']
    assert r['graph'] == 'pendiente' and r['refresh'] is False
    reasons = {(x['section'], x['index']): x['reason'] for x in r['rejected']}
    assert 'falta «name»' in reasons[('nodes', 2)] and 'no permitido' in reasons[('nodes', 3)]
    assert 'ruta relativa' in reasons[('nodes', 4)] and 'etiqueta' in reasons[('nodes', 5)] and 'para anotarlo' in reasons[('nodes', 7)]
    assert 'no-existe' in reasons[('edges', 1)] and 'contener' in reasons[('edges', 2)] and 'distintos' in reasons[('edges', 3)]
    assert 'summary' in reasons[('annotations', 1)]
    state = overlay.state_of('demo')
    assert 'sk_live' not in json.dumps(state) and '«redactado»' in state['nodes']['a:pagos']['summary']
    kinds = sorted(e['kind'] for e in state['edges'].values())
    assert kinds == ['call', 'contains']
    with pytest.raises(InvalidInput, match='nada que añadir'):
        overlay.add('demo')
    with pytest.raises(InvalidInput, match='como mucho'):
        overlay.add('demo', nodes=[{'name': f'n{i}', 'kind': 'concept'} for i in range(overlay.MAX_BATCH + 1)])
    again = overlay.add('demo', nodes=[{'name': 'pagos', 'kind': 'component', 'summary': 'Cobra'}], rebuild=False)
    assert again['updated'] == ['a:pagos'] and again['created'] == []


def test_merge_into_analyze(repo, tmp_path):
    ops = [
        op('node', 'a:usuarios', kind='component', name='Usuarios', summary='Alta y consulta', community_hint='usuarios'),
        op('node', 'a:alta', kind='flow', name='Alta', community_hint='usuarios'),
        op('node', 'f:app/utils.py:slugify', kind='component', name='ignorado', summary='Normaliza', tags=['texto']),
        op('node', 'a:helper', kind='function', name='helper2', file='app/base.py', line=4, parent='m:app/base.py'),
        op('edge', 'rel:a', a='a:usuarios', b='m:app/services.py', kind='contains'),
        op('edge', 'rel:b', a='a:usuarios', b='c:app/models.py:User', kind='contains'),
        op('edge', 'rel:c', a='a:alta', b='f:app/services.py:create_user', kind='step', order=2),
        op('edge', 'rel:d', a='a:alta', b='f:app/api.py:list_users', kind='step', order=1),
        op('edge', 'rel:e', a='a:alta', b='m:desaparecido.py', kind='step', order=3),
        op('edge', 'rel:f', a='a:usuarios', b='f:app/utils.py:slugify', kind='uses', label='normaliza nombres'),
        op('note', 'm:app/api.py', summary='Rutas HTTP', tags=['api']),
        op('note', 'm:ya-no-existe.py', summary='x'),
    ]
    graph = analyze(repo, 'demo', overlay_ops=ops)
    nodes = by_key(graph)
    comp, flow = nodes['a:usuarios'], nodes['a:alta']
    assert comp['kind'] == 'component' and comp['by'] == 'agent' and comp['summary'] == 'Alta y consulta' and comp['file'] == ''
    assert flow['steps'] == ['f:app/api.py:list_users', 'f:app/services.py:create_user'] and comp['c'] == flow['c']
    assert comp['rels'] == [{'to': 'f:app/utils.py:slugify', 'name': 'slugify', 'kind': 'uses', 'label': 'normaliza nombres'}]
    slug = nodes['f:app/utils.py:slugify']
    assert slug['kind'] == 'function' and slug['summary'] == 'Normaliza' and slug['tags'] == ['texto'] and slug['noted'] == 'agent'
    assert nodes['m:app/api.py']['summary'] == 'Rutas HTTP' and nodes['m:app/api.py']['tags'] == ['api']
    assert graph['nodes'][nodes['m:app/services.py']['parent']]['key'] == 'a:usuarios'
    assert graph['nodes'][nodes['a:helper']['parent']]['key'] == 'm:app/base.py' and nodes['a:helper']['line'] == 4
    assert nodes['c:app/models.py:User']['parent'] == nodes['m:app/models.py']['id']
    edges = edge_set(graph)
    assert ('a:alta', 'f:app/api.py:list_users', 'step') in edges and ('a:usuarios', 'f:app/utils.py:slugify', 'uses') in edges
    assert ('a:alta', 'f:app/api.py:list_users', 'step') in edge_set(graph, 'visible')
    warnings = [w['error'] for w in graph['stats']['warnings'] if w['file'] == overlay.LOG]
    assert any('desaparecido.py' in w for w in warnings) and any('ya tiene padre' in w for w in warnings)
    assert any('ya-no-existe' in w for w in warnings)
    assert graph['stats']['kinds']['component'] == 1 and graph['stats']['kinds']['flow'] == 1
    plain = analyze(repo, 'demo')
    assert nodes['f:app/utils.py:slugify']['hash'] == by_key(plain)['f:app/utils.py:slugify']['hash']
    changed = analyze(repo, 'demo', overlay_ops=ops + [op('node', 'a:usuarios', summary='Otra cosa')])
    assert by_key(changed)['a:usuarios']['hash'] != comp['hash']
    diff = store.compare(changed['nodes'], graph['nodes'])
    assert diff['modified'] == ['a:usuarios'] and 'annotated' not in diff
    diff = store.compare(graph['nodes'], plain['nodes'])
    assert set(diff['added']) == {'a:usuarios', 'a:alta', 'a:helper'} and set(diff['annotated']) == {'f:app/utils.py:slugify', 'm:app/api.py'}


def test_community_hint_groups_agent_nodes(tmp_path):
    files = {f'svc{i}/main.py': f'def run{i}():\n    return {i}\n' for i in range(3)}
    root = write_repo(tmp_path / 'hint', files)
    ops = [op('node', f'a:c{i}', kind='component', name=f'Parte {i}', community_hint='Facturación') for i in range(3)]
    graph = analyze(root, 'hint', overlay_ops=ops)
    nodes = by_key(graph)
    assert len({nodes[f'a:c{i}']['c'] for i in range(3)}) == 1


def test_empty_folder_becomes_fillable_project(tmp_path, data_dir):
    root = write_repo(tmp_path / 'blobs', {'flujo.zzflow': '<definitions/>', 'reglas/precio.qqdsl': 'regla precio = base * 2\n', '.oculto': 'x'})
    with pytest.raises(CortexError, match='no hay código'):
        analyze(root, 'blobs', overlay_ops=None)
    (tmp_path / 'vacio').mkdir()
    with pytest.raises(CortexError, match='no hay código'):
        analyze(tmp_path / 'vacio', 'vacio', overlay_ops=[])
    summary = mcp_server.analyze_project(str(root), name='blobs')
    assert summary['stats']['files'] == 2 and summary['stats']['kinds'] == {'module': 2}
    guide = mcp_server.graph_guide('blobs')
    assert guide['worklist']['files_without_symbols']['total'] == 2 and guide['steps']
    assert {x['file'] for x in guide['worklist']['files_without_symbols']['items']} == {'flujo.zzflow', 'reglas/precio.qqdsl'}
    r = mcp_server.graph_add('blobs', nodes=[{'name': 'Motor de precios', 'kind': 'component', 'contains': ['reglas/precio.qqdsl']}],
                             flows=[{'name': 'Cotizar', 'steps': ['flujo.zzflow', 'Motor de precios']}],
                             annotations=[{'id': 'flujo.zzflow', 'summary': 'Proceso BPMN de cotización'}])
    assert r['created'] == ['a:motor-de-precios', 'a:cotizar'] and r['refresh'] is True and not r['rejected']
    assert overlay.wait('blobs')
    node = mcp_server.node_context('a:cotizar', project='blobs')
    assert [s['key'] for s in node['steps']] == ['m:flujo.zzflow', 'a:motor-de-precios']
    assert mcp_server.file_context('flujo.zzflow', project='blobs')['summary'] == 'Proceso BPMN de cotización'
    assert mcp_server.search_code('cotización', project='blobs')['results'][0]['key'] == 'm:flujo.zzflow'
    ctx = mcp_server.context_for('motor de precios', project='blobs', budget=1000)
    assert 'a:motor-de-precios' in [i['key'] for i in ctx['items']]
    assert mcp_server.read_symbol('a:motor-de-precios', project='blobs')['code'].startswith('# componente Motor de precios')


def test_new_project_from_overlay_only(data_dir):
    with pytest.raises(InvalidInput, match='indica «project»'):
        overlay.add(nodes=[{'name': 'A', 'kind': 'component'}])
    r = overlay.add('procesos', nodes=[{'name': 'Ventas', 'kind': 'component', 'summary': 'Área comercial'}],
                    flows=[{'name': 'Venta', 'steps': ['Ventas']}], rebuild=True)
    assert r['graph'] == 'actualizado'
    hist = store.load_history('procesos')
    assert hist['origin'] == {'type': 'agent'} and hist['versions'][0]['v'] == 1
    assert mcp_server.node_context('Venta', project='procesos')['node']['kind'] == 'flow'
    assert mcp_server.project_overview('procesos')['communities'][0]['name'] == 'Ventas'
    with pytest.raises(NotFound):
        overlay.listing('otro-que-no-existe')


def test_fingerprint_and_refresh(demo, repo):
    first = pipeline.fingerprint(str(repo), project='demo')
    assert pipeline.analyze_source(str(repo), 'demo')['unchanged']
    overlay.add('demo', nodes=[{'name': 'Núcleo', 'kind': 'component'}], rebuild=False)
    assert pipeline.fingerprint(str(repo), project='demo') != first
    graph = pipeline.analyze_source(str(repo), 'demo')
    assert not graph['unchanged'] and graph['version'] == 2 and graph['changes']['added'] == ['a:nucleo']
    assert '## Aportado por agentes' in open(f"{store.project_dir('demo')}/grafo.md", encoding='utf-8').read()
    r = overlay.add('demo', annotations=[{'id': 'slugify', 'summary': 'Normaliza'}], rebuild=True)
    assert r['annotated'] == ['f:app/utils.py:slugify'] and r['graph'] == 'actualizado'
    latest = query.load_index('demo')
    assert latest.version == 3 and latest.graph['changes']['annotated'] == ['f:app/utils.py:slugify']
    assert latest.by_key['f:app/utils.py:slugify']['status'] == 'noted'
    assert query.changes('demo')['counts'] == {'added': 0, 'modified': 0, 'removed': 0, 'annotated': 1}
    gone = overlay.remove('demo', ['a:nucleo', 'm:app/utils.py', 'rel:nada'], rebuild=True)
    assert gone['removed'] == ['a:nucleo'] and len(gone['rejected']) == 2
    assert 'a:nucleo' not in query.load_index('demo').by_key


def test_flow_redefinition_replaces_steps(demo):
    overlay.add('demo', flows=[{'name': 'Alta', 'steps': ['list_users', 'create_user', 'slugify']}], rebuild=False)
    r = overlay.add('demo', flows=[{'name': 'Alta', 'steps': ['create_user', 'list_users'], 'summary': 'Crear usuarios'}], rebuild=True)
    assert r['updated'] == ['a:alta'] and r['flows'] == [{'id': 'a:alta', 'steps': 2}]
    steps = mcp_server.node_context('a:alta')['steps']
    assert [(s['name'], s['order']) for s in steps] == [('create_user', 1), ('list_users', 2)]
    listed = overlay.listing('demo')
    assert listed['counts']['edges'] == {'step': 2} and listed['nodes'][0]['status'] == 'en el grafo'


def test_mcp_tools_and_prompt(demo):
    server_ = mcp_server.build_server()
    tools = {t.name: t for t in asyncio.run(server_.list_tools())}
    assert {'graph_guide', 'graph_add', 'graph_remove', 'graph_overlay'} <= set(tools) and len(tools) == 28
    assert set(tools['graph_add'].inputSchema['properties']) == {'project', 'nodes', 'edges', 'annotations', 'flows'}
    assert 'component' in tools['graph_add'].description and 'worklist' in tools['graph_guide'].description
    assert tools['graph_remove'].annotations.destructiveHint is True and tools['graph_overlay'].annotations.readOnlyHint is True
    _, added = asyncio.run(server_.call_tool('graph_add', {'project': 'demo', 'nodes': [{'name': 'API', 'kind': 'component',
                                                                                        'contains': ['app/api.py']}]}))
    assert added['created'] == ['a:api'] and added['refresh'] is True
    assert overlay.wait('demo')
    _, listed = asyncio.run(server_.call_tool('graph_overlay', {'project': 'demo'}))
    assert listed['nodes'][0]['id'] == 'a:api' and listed['nodes'][0]['status'] == 'en el grafo' and listed['version'] == 2
    _, guide = asyncio.run(server_.call_tool('graph_guide', {'project': 'demo', 'limit': 5}))
    assert guide['overlay']['in_graph']['nodes'] == 1 and len(guide['worklist']['modules_without_summary']['items']) <= 5
    assert guide['worklist']['endpoints_without_counterpart']['total'] >= 1
    _, removed = asyncio.run(server_.call_tool('graph_remove', {'project': 'demo', 'ids': ['a:api']}))
    assert removed['removed'] == ['a:api']
    assert overlay.wait('demo')
    prompts = {p.name for p in asyncio.run(server_.list_prompts())}
    assert 'build_graph' in prompts
    text = asyncio.run(server_.get_prompt('build_graph', {'project': 'demo'})).messages[0].content.text
    assert 'graph_guide' in text and 'graph_add' in text and 'graph_overlay' in text


def test_cli_graph_commands(demo, tmp_path, capsys):
    batch = tmp_path / 'lote.json'
    batch.write_text(json.dumps({'nodes': [{'name': 'Servicios', 'kind': 'component', 'contains': ['app/services.py']}],
                                 'edges': [{'a': 'Servicios', 'b': 'slugify', 'kind': 'uses'}]}), encoding='utf-8')
    assert cli.main(['graph', 'add', str(batch), '--project', 'demo']) == 0
    out = capsys.readouterr().out
    assert 'a:servicios' in out and 'grafo: actualizado' in out
    assert cli.main(['graph', 'list', '--project', 'demo', '--json']) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed['total'] == {'nodes': 1, 'edges': 2, 'annotations': 0}
    assert cli.main(['graph', 'guide', '--project', 'demo']) == 0
    assert 'cómo completar el grafo' in capsys.readouterr().out
    assert cli.main(['graph', 'remove', 'a:servicios', '--project', 'demo']) == 0
    assert 'quitados' in capsys.readouterr().out
    assert cli.main(['graph', 'add', str(tmp_path / 'falta.json')]) == 1
    assert 'no se pudo leer' in capsys.readouterr().err
    assert cli.main(['analyze', 'x', '--yes']) == 1
    assert '--ai' in capsys.readouterr().err


def ai_message(payload, stop='end_turn'):
    return NS(stop_reason=stop, content=[NS(type='text', text=json.dumps(payload))])


class FakeAI:
    def __init__(self, payload):
        self.calls = []
        self.payload = payload
        self.beta = NS(messages=NS(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        return ai_message(self.payload)


AI_PAYLOAD = {
    'components': [{'name': 'Usuarios', 'role': 'service', 'summary': 'Gestiona usuarios.', 'files': ['app/services.py', 'app/models.py'],
                    'uses': ['Utilidades']},
                   {'name': 'Utilidades', 'role': 'library', 'summary': 'Helpers.', 'files': ['app/utils.py'], 'uses': []}],
    'flows': [{'name': 'Listar usuarios', 'summary': 'GET /users crea un usuario demo.',
               'steps': ['f:app/api.py:list_users', 'f:app/services.py:create_user', 'inventado.py']}],
    'summaries': [{'file': 'app/api.py', 'summary': 'Rutas HTTP.'}, {'file': 'nada.py', 'summary': 'x'}],
}


def test_ai_enrich_with_fake_client(repo, data_dir, monkeypatch):
    (repo / '.env').write_text('API_KEY=supersecreto123\n', encoding='utf-8')
    (repo / 'app' / 'config.py').write_text('password = "hunter2hunter2"\n', encoding='utf-8')
    pipeline.analyze_source(str(repo), 'demo')
    fake = FakeAI(AI_PAYLOAD)
    seen = []
    result = overlay.ai_enrich('demo', client=fake, confirm=lambda n, chars, model: seen.append((n, model)) or True)
    assert seen and seen[0][1] == llm.model_name() and fake.calls
    sent = json.dumps(fake.calls)
    assert 'supersecreto123' not in sent and 'hunter2hunter2' not in sent and 'def slugify' in sent
    assert fake.calls[0]['output_config']['format']['schema'] == overlay.AI_SCHEMA and fake.calls[0]['betas'] == [llm.FALLBACK_BETA]
    assert result['components'] >= 2 and result['flows'] >= 1 and result['summaries'] >= 1 and result['rejected_total'] >= 1
    state = overlay.state_of('demo')
    assert state['nodes']['a:usuarios']['origin'] == 'ai' and state['nodes']['a:usuarios']['source'] == llm.model_name()
    graph = pipeline.rebuild('demo')
    nodes = by_key(graph)
    assert nodes['a:usuarios']['by'] == 'ai' and nodes['m:app/api.py']['noted'] == 'ai'
    assert nodes['a:listar-usuarios']['steps'] == ['f:app/api.py:list_users', 'f:app/services.py:create_user']
    cancelled = overlay.ai_enrich('demo', client=fake, confirm=lambda *a: False)
    assert cancelled['note'].startswith('cancelado')
    monkeypatch.setattr(llm, 'available', lambda: (False, 'sin credenciales: define ANTHROPIC_API_KEY'))
    with pytest.raises(InvalidInput, match='ANTHROPIC_API_KEY'):
        overlay.ai_enrich('demo')


def test_cli_analyze_ai(repo, data_dir, monkeypatch, capsys):
    fake = FakeAI(AI_PAYLOAD)
    monkeypatch.setattr(llm, 'available', lambda: (True, 'prueba'))
    errors = {name: type(name, (Exception,), {}) for name in ('RateLimitError', 'APIStatusError', 'APIConnectionError')}
    monkeypatch.setattr(llm, 'sdk', lambda: NS(Anthropic=lambda: fake, **errors))
    assert cli.main(['analyze', str(repo), '--name', 'demo', '--ai', '--json']) == 0
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert 'enviará' in captured.err and out['version'] == 2 and out['ai']['components'] >= 2 and fake.calls
    monkeypatch.setattr(llm, 'available', lambda: (False, 'sin credenciales'))
    assert cli.main(['analyze', str(repo), '--name', 'demo', '--ai']) == 1
    assert 'sin credenciales' in capsys.readouterr().err


def test_ai_bad_responses_become_issues(demo):
    class Bad(FakeAI):
        def create(self, **kw):
            self.calls.append(kw)
            return ai_message({}, stop='refusal') if len(self.calls) == 1 else NS(stop_reason='end_turn', content=[NS(type='text', text='no json')])

    result = overlay.ai_enrich('demo', client=Bad({}))
    assert result['issues'] and 'rechazó' in result['issues'][0]


@pytest.fixture
def api(data_dir):
    httpd = server.make_server('127.0.0.1', 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def call(port, method, path, body=None):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=60)
    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None)
    res = conn.getresponse()
    data = json.loads(res.read())
    conn.close()
    return res.status, data


def test_http_overlay_endpoints(demo, api):
    status, added = call(api, 'POST', '/api/overlay', {'project': 'demo', 'nodes': [{'name': 'Web', 'kind': 'component'}],
                                                        'edges': [{'a': 'Web', 'b': 'nada'}]})
    assert status == 201 and added['created'] == ['a:web'] and added['rejected'][0]['section'] == 'edges'
    assert overlay.wait('demo')
    status, listed = call(api, 'GET', '/api/overlay?project=demo')
    assert status == 200 and listed['nodes'][0]['id'] == 'a:web' and listed['nodes'][0]['source'] == 'http'
    assert call(api, 'POST', '/api/overlay', {'project': 'demo'})[0] == 400
    assert call(api, 'POST', '/api/overlay', {'project': 'demo', 'nodes': 'x'})[0] == 400
    status, removed = call(api, 'POST', '/api/overlay/remove', {'project': 'demo', 'ids': ['a:web']})
    assert status == 200 and removed['removed'] == ['a:web']
    assert overlay.wait('demo')
    assert call(api, 'GET', '/api/overlay?project=no-existe')[0] == 404
