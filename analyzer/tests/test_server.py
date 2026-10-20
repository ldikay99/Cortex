import base64
import http.client
import io
import json
import os
import subprocess
import threading
import time
import zipfile
from pathlib import Path

import pytest

from conftest import FILES, source, write_repo
from cortex_graph import server, store


@pytest.fixture(scope='module')
def api(tmp_path_factory):
    data = tmp_path_factory.mktemp('server-data')
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv('CORTEX_DATA', str(data))
        mp.delenv('DATA_PATH', raising=False)
        httpd = server.make_server('127.0.0.1', 0)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        yield Client(httpd.server_address[1], data)
        httpd.shutdown()
        httpd.server_close()


class Client:
    def __init__(self, port, data):
        self.port = port
        self.data = Path(data)

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=60)
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        conn.request(method, path, body=body, headers=headers or {})
        res = conn.getresponse()
        raw = res.read()
        conn.close()
        return res, raw

    def json(self, method, path, body=None, headers=None):
        res, raw = self.request(method, path, body, headers)
        return res.status, json.loads(raw)

    def get(self, path):
        return self.json('GET', path)

    def post(self, path, body=None):
        return self.json('POST', path, body)

    def wait(self, *states, timeout=90):
        deadline = time.time() + timeout
        while time.time() < deadline:
            _, status = self.get('/api/status')
            if status['state'] in states:
                return status
            time.sleep(0.1)
        raise AssertionError(f'estado final no alcanzado: {status}')

    def stream(self, query=''):
        res, raw = self.request('GET', f'/api/stream{query}')
        assert res.status == 200
        return [json.loads(line) for line in raw.decode().splitlines() if line.strip()]


@pytest.fixture(scope='module')
def saved_demo(api):
    ready_project(api)
    return 'demo'


def ndjson(files):
    return '\n'.join(json.dumps({'path': rel, 'content': source(content)}) for rel, content in files.items()).encode()


def zipped(files, prefix='demo/'):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for rel, content in files.items():
            zf.writestr(prefix + rel, source(content))
    return buffer.getvalue()


def ready_project(api, name='demo'):
    status, body = api.post(f'/api/upload?name={name}', ndjson(FILES))
    assert status == 200, body
    status, body = api.post('/api/analyze', {'exclude': [], 'tests': True})
    assert status == 202
    return api.wait('ready', 'error')


def groups(lines):
    items = [item for line in lines if line['t'] == 'batch' for item in line['items']]
    out, pending = [], []
    for item in items:
        if item['t'] == 'community':
            pending.append(item)
        elif item['t'] == 'node':
            out.append(pending + [item])
            pending = []
        else:
            out[-1].append(item)
    return out


def test_upload_review_tree_and_analyze(api):
    status, body = api.post('/api/upload?name=demo', ndjson(FILES))
    assert status == 200 and body['state'] == 'review' and body['project'] == 'demo' and body['files'] == 14
    assert not (api.data / 'demo' / 'fuente' / 'node_modules').exists()
    status, tree = api.get('/api/tree')
    assert status == 200 and 'app/services.py' in tree['files']
    assert set(tree['tests']) == {'tests/test_services.py', 'web/src/pages/Home.test.ts'}
    status, body = api.post('/api/analyze', {'exclude': ['docs'], 'tests': False})
    assert status == 202 and body == {'state': 'analyzing', 'project': 'demo'}
    final = api.wait('ready', 'error')
    assert final['state'] == 'ready' and final['version'] == 1 and final['error'] is None
    assert final['stats']['excluded'] == ['docs'] and final['stats']['tests'] is False
    status, _ = api.get('/api/tree')
    assert status == 409
    status, projects = api.get('/api/projects')
    entry = next(p for p in projects['projects'] if p['project'] == 'demo')
    assert {k: entry['last']['options'][k] for k in ('exclude', 'tests')} == {'exclude': ['docs'], 'tests': False}
    assert set(entry['last']['changes']) == {'added', 'modified', 'removed'} and entry['origin'] == {'type': 'upload'}


def test_zip_upload_strips_root_folder(api):
    status, body = api.post('/api/upload?name=zipped', zipped(FILES))
    assert status == 200 and body['files'] == 14
    assert (api.data / 'zipped' / 'fuente' / 'app' / 'services.py').is_file()


@pytest.mark.parametrize('payload', [
    ndjson({'../evil.py': 'x = 1'}),
    ndjson({'/etc/evil.py': 'x = 1'}),
    ndjson({'C:/evil.py': 'x = 1'}),
    zipped({'../../evil.py': 'x = 1'}, prefix=''),
    zipped({'ok.py': 'x = 1', 'a/../../evil.py': 'x = 1'}, prefix=''),
])
def test_upload_rejects_path_traversal(api, payload):
    status, body = api.post('/api/upload?name=evil', payload)
    assert status == 400 and 'ruta no permitida' in body['error']
    assert not (api.data / 'evil.py').exists() and not (api.data.parent / 'evil.py').exists()


@pytest.mark.parametrize('payload, code', [
    (b'', 413),
    (b'not json\n', 400),
    (b'[1, 2]\n', 400),
    (ndjson({'blob.bin': 'nothing to analyze'}), 400),
    (b'PK\x03\x04garbage', 400),
    (zipped({'image.png': 'x'}), 400),
])
def test_upload_rejects_malformed(api, payload, code):
    status, body = api.post('/api/upload?name=bad', payload)
    assert status == code and body['error']


def test_upload_limits(api, monkeypatch):
    big = zipped({'big.py': 'x' * (3 * 1024 * 1024), 'small.py': 'y = 1'})
    status, body = api.post('/api/upload?name=limits', big)
    assert status == 200 and body['files'] == 1
    monkeypatch.setattr(server, 'MAX_EXTRACTED', 1000)
    status, body = api.post('/api/upload?name=limits', zipped({f'f{i}.py': 'z' * 600 for i in range(3)}))
    assert status == 413 and '200 MB' in body['error']
    monkeypatch.setattr(server, 'MAX_EXTRACTED', 200 * 1024 * 1024)
    monkeypatch.setattr(server, 'MAX_FILES', 2)
    status, body = api.post('/api/upload?name=limits', ndjson({f'f{i}.py': 'a = 1' for i in range(3)}))
    assert status == 413 and 'archivos' in body['error']
    assert (api.data / 'limits' / 'fuente' / 'small.py').is_file()


def test_stream_full_and_resume(api):
    status = ready_project(api)
    assert status['state'] == 'ready'
    full = api.stream('?rate=200')
    assert full[0]['t'] == 'meta' and full[0]['project'] == 'demo' and set(full[0]['changes']) == {'added', 'modified', 'removed'}
    assert full[-1]['t'] == 'done'
    batches = [line for line in full if line['t'] == 'batch']
    assert len(batches) > 1 and batches[-1]['done'] == batches[-1]['total'] == status['stats']['nodes']
    full_groups = groups(full)
    assert len(full_groups) == status['stats']['nodes']
    seen_nodes = set()
    for group in full_groups:
        node = next(i for i in group if i['t'] == 'node')
        assert node['key'].split(':', 1)[0] in {'m', 'd', 'c', 'f', 'p', 'v', 'e', 't'}
        seen_nodes.add(node['id'])
        for edge in (i for i in group if i['t'] == 'edge'):
            assert {edge['a'], edge['b']} <= seen_nodes
    communities = [i for g in full_groups for i in g if i['t'] == 'community']
    assert len(communities) == len({c['id'] for c in communities}) == status['stats']['communities']
    _, graph = api.get('/api/graph')
    assert sum(1 for g in full_groups for i in g if i['t'] == 'edge') == len(graph['visible'])

    for start in (0, 1, 7, len(full_groups) - 1):
        resumed = api.stream(f'?rate=5000&from={start}')
        assert resumed[0]['t'] == 'meta' and resumed[-1]['t'] == 'done'
        assert [i for g in groups(resumed) for i in g] == [i for g in full_groups[start:] for i in g]
        assert [line for line in resumed if line['t'] == 'batch'][-1]['done'] == len(full_groups)
    tail = api.stream(f'?from={len(full_groups) + 50}')
    assert [line['t'] for line in tail] == ['meta', 'done']


def test_stream_rejects_bad_params(api):
    assert api.request('GET', '/api/stream?rate=abc')[0].status == 400
    assert api.request('GET', '/api/stream?rate=nan')[0].status == 400
    assert api.request('GET', '/api/stream?from=x')[0].status == 400


def test_exports_import_and_open(api):
    ready_project(api)
    for path, kind, suffix in (('/api/export.md', 'text/markdown', '-grafo.md'), ('/api/export.json', 'application/json', '-grafo.json'),
                               ('/api/export.cortex', 'application/json', '.cortex.json')):
        res, raw = api.request('GET', path)
        assert res.status == 200 and res.getheader('Content-Type').startswith(kind)
        assert res.getheader('Content-Disposition').startswith('attachment; filename="demo-v') and suffix in res.getheader('Content-Disposition')
    _, cortex = api.request('GET', '/api/export.cortex')
    graph = json.loads(cortex)
    graph['project'] = 'importado-demo'
    status, body = api.post('/api/import', json.dumps(graph).encode())
    assert status == 200 and body == {'state': 'ready', 'project': 'importado-demo', 'version': 1}
    assert api.get('/api/status')[1]['project'] == 'importado-demo'
    assert (api.data / 'importado-demo' / 'grafo.md').is_file()
    status, body = api.post('/api/open', {'project': 'demo', 'version': 1})
    assert status == 200 and body == {'state': 'ready', 'project': 'demo', 'version': 1}
    status, body = api.post('/api/update', {'project': 'demo'})
    assert status == 409 and 'a mano' in body['error']


@pytest.mark.parametrize('method, path, body, code', [
    ('POST', '/api/github', {'url': 'https://gitlab.com/a/b'}, 400),
    ('POST', '/api/github', {'url': 'https://github.com/../x'}, 400),
    ('POST', '/api/github', b'{bad json', 400),
    ('POST', '/api/github', b'[1]', 400),
    ('POST', '/api/open', {'project': 'demo', 'version': 'abc'}, 400),
    ('POST', '/api/open', {'version': 1}, 400),
    ('POST', '/api/open', {'project': 'nadie'}, 404),
    ('POST', '/api/update', {'project': 'nadie'}, 404),
    ('POST', '/api/update', {'project': 5}, 400),
    ('POST', '/api/import', b'not json', 400),
    ('POST', '/api/import', {'format': 'cortex-grafo/1', 'nodes': [{'id': 0}], 'visible': [], 'communities': []}, 400),
    ('POST', '/api/import', b'', 400),
    ('POST', '/api/nope', {}, 404),
    ('GET', '/api/nope', None, 404),
    ('GET', '/api/query/node', None, 400),
    ('GET', '/api/query/node?ref=zzz-none&project=demo', None, 404),
    ('GET', '/api/query/overview?project=nadie', None, 404),
    ('GET', '/api/query/search?q=x&kind=planet', None, 400),
    ('GET', '/api/query/search?q=x&limit=lots', None, 400),
    ('GET', '/api/query/search', None, 400),
    ('GET', '/api/query/impact?ref=slugify&depth=deep', None, 400),
    ('GET', '/api/query/changes?project=demo&since=99', None, 404),
    ('GET', '/api/query/community?ref=999&project=demo', None, 404),
    ('GET', '/api/query/path?a=slugify', None, 400),
    ('GET', '/api/query/symbol', None, 400),
    ('GET', '/api/query/symbol?ref=zzz-none&project=demo', None, 404),
    ('GET', '/api/query/symbol?ref=slugify&context=wide&project=demo', None, 400),
    ('GET', '/api/query/context', None, 400),
    ('GET', '/api/query/context?q=user&budget=lots&project=demo', None, 400),
    ('GET', '/api/query/architecture?section=planets&project=demo', None, 400),
    ('GET', '/api/query/dependencies?name=zzz-none&project=demo', None, 404),
    ('GET', '/api/query/endpoints?limit=many&project=demo', None, 400),
    ('GET', '/api/query/variables?offset=x&project=demo', None, 400),
    ('POST', '/api/query/review', {'base': 5}, 400),
])
def test_malformed_requests_get_client_errors(api, saved_demo, method, path, body, code):
    status, out = api.json(method, path, body)
    assert status == code and isinstance(out['error'], str) and out['error']


def test_analyze_validates_options(api):
    api.post('/api/upload?name=demo', ndjson(FILES))
    assert api.post('/api/analyze', {'exclude': 'docs'})[0] == 400
    assert api.post('/api/analyze', {'exclude': [1]})[0] == 400
    assert api.post('/api/analyze', {'tests': 'yes'})[0] == 400
    assert api.get('/api/status')[1]['state'] == 'review'


def test_invalid_content_length(api):
    res, raw = api.request('POST', '/api/github', b'{}', headers={'Content-Length': 'abc'})
    assert res.status == 400 and json.loads(raw)['error']
    res, raw = api.request('POST', '/api/import', b'{}', headers={'Content-Length': str(10 ** 12)})
    assert res.status == 413


def test_query_endpoints(api, saved_demo):
    status, o = api.get('/api/query/overview?project=demo')
    assert status == 200 and o['project'] == 'demo' and o['routes'][0]['route'] == 'GET /users'
    status, s = api.get('/api/query/search?q=slugify&kind=function&limit=3&project=demo')
    assert status == 200 and s['results'][0]['key'] == 'f:app/utils.py:slugify'
    status, n = api.get('/api/query/node?ref=create_user&project=demo')
    assert status == 200 and {'slugify', 'User'} <= {c['name'] for c in n['calls']}
    status, f = api.get('/api/query/file?path=app/services.py&project=demo')
    assert status == 200 and f['imports'] == ['app/models.py', 'app/utils.py']
    status, c = api.get('/api/query/community?ref=0&project=demo')
    assert status == 200 and c['community']['id'] == 0
    status, p = api.get('/api/query/path?a=list_users&b=slugify&project=demo')
    assert status == 200 and p['length'] == 2
    status, i = api.get('/api/query/impact?ref=slugify&depth=2&project=demo')
    assert status == 200 and i['depth'] == 2 and i['levels'][0]['nodes'][0]['name'] == 'create_user'
    status, ch = api.get('/api/query/changes?project=demo&since=1')
    assert status == 200 and ch['from_version'] == 1
    status, default = api.get('/api/query/overview')
    assert status == 200 and default['project'] == store.latest_project()


def test_new_query_endpoints(api, saved_demo):
    status, sym = api.get('/api/query/symbol?ref=create_user&context=1&project=demo')
    assert status == 200 and 'def create_user(name):' in sym['code'] and sym['file'] == 'app/services.py'
    status, ctx = api.get('/api/query/context?q=how+is+a+user+created&budget=1200&project=demo')
    assert status == 200 and ctx['items'][0]['name'] == 'create_user' and ctx['tokens_used'] <= 1200 and ctx['source'] is True
    status, arch = api.get('/api/query/architecture?project=demo')
    assert status == 200 and arch['endpoints']['items'][0]['route'] == 'GET /users' and 'layers' in arch
    status, part = api.get('/api/query/architecture?section=dead_code&limit=3&project=demo')
    assert status == 200 and set(part) == {'project', 'version', 'dead_code'}
    status, deps = api.get('/api/query/dependencies?project=demo')
    assert status == 200 and 'packages' in deps
    status, eps = api.get('/api/query/endpoints?method=GET&project=demo')
    assert status == 200 and eps['endpoints']['items'][0]['handlers'][0]['name'] == 'list_users'
    status, vs = api.get('/api/query/variables?project=demo')
    assert status == 200 and 'variables' in vs
    status, found = api.get('/api/query/search?q=user&limit=1&offset=1&project=demo')
    assert status == 200 and found['offset'] == 1 and 'score' in found['results'][0]


def test_review_endpoint(api, saved_demo, monkeypatch):
    from cortex_graph import review
    calls = []
    monkeypatch.setattr(review, 'review', lambda root, base, head, project, diff_text: calls.append((root, base, head, project, diff_text)) or {'ok': 1})
    assert api.get('/api/query/review?project=demo') == (200, {'ok': 1})
    assert api.get('/api/query/review?project=demo&worktree=1')[0] == 200
    assert api.post('/api/query/review', {'project': 'demo', 'diff': 'diff --git a/x b/x', 'base': 'main'}) == (200, {'ok': 1})
    assert calls == [(None, 'HEAD~1', 'HEAD', 'demo', None), (None, 'HEAD', 'WORKTREE', 'demo', None),
                     (None, 'main', 'HEAD', 'demo', 'diff --git a/x b/x')]


def test_server_survives_internal_errors(api, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError('boom')

    monkeypatch.setattr(store, 'list_projects', explode)
    status, body = api.get('/api/projects')
    assert status == 500 and 'error interno' in body['error'] and 'boom' not in body['error']
    monkeypatch.undo()
    assert api.get('/api/status')[0] == 200


def test_analysis_failure_sets_error_state(api, tmp_path):
    status, _ = api.post('/api/upload?name=demo', ndjson(FILES))
    assert status == 200
    status, _ = api.post('/api/analyze', {'exclude': ['app', 'web', 'docs', 'tests']})
    assert status == 202
    final = api.wait('ready', 'error')
    assert final['state'] == 'error' and 'para analizar en esa carpeta' in final['error']
    lines = api.stream()
    assert lines == [{'t': 'error', 'error': final['error']}]


def test_idle_like_stream_in_review(api):
    api.post('/api/upload?name=demo', ndjson(FILES))
    assert api.stream() == [{'t': 'review'}]


def test_github_clone_failure_is_reported(api, monkeypatch):
    monkeypatch.setenv('GIT_ALLOW_PROTOCOL', 'none')
    status, body = api.post('/api/github', {'url': 'https://github.com/ldikay99/definitely-not-a-repo-xyz'})
    assert status == 202 and body == {'state': 'cloning', 'project': 'definitely-not-a-repo-xyz'}
    final = api.wait('review', 'error', timeout=120)
    assert final['state'] == 'error' and 'no se pudo clonar' in final['error']


def test_local_origin_update(api, tmp_path):
    from cortex_graph import pipeline
    root = write_repo(tmp_path / 'local-demo')
    pipeline.analyze_source(str(root), 'local-demo')
    (root / 'app' / 'extra.py').write_text('def extra():\n    return 1\n')
    status, body = api.post('/api/update', {'project': 'local-demo'})
    assert status == 202 and body == {'state': 'analyzing', 'project': 'local-demo'}
    final = api.wait('ready', 'error')
    assert final['state'] == 'ready' and final['version'] == 2
    status, ch = api.get('/api/query/changes?project=local-demo')
    assert [n['name'] for n in ch['added']] == ['extra.py', 'extra']


def test_clone_keeps_token_out_of_args_and_repo(tmp_path, monkeypatch):
    from cortex_graph import pipeline
    secret = 'ghp_' + 'x' * 36
    monkeypatch.setenv('GITHUB_TOKEN', secret)
    seen = {}

    def fake_run(cmd, env=None, **kw):
        seen['cmd'], seen['env'] = cmd, env
        staging = cmd[-1]
        os.makedirs(os.path.join(staging, '.git'))
        with open(os.path.join(staging, '.git', 'config'), 'w') as fh:
            fh.write('[remote "origin"]\n\turl = https://github.com/o/r.git\n')
        return subprocess.CompletedProcess(cmd, 0, '', '')

    monkeypatch.setattr(pipeline.subprocess, 'run', fake_run)
    dest = str(tmp_path / 'fuente')
    pipeline.clone_github('o', 'r', dest)
    encoded = base64.b64encode(f'x-access-token:{secret}'.encode()).decode()
    assert not any(secret in a or encoded in a for a in seen['cmd'])
    assert encoded in seen['env']['GIT_CONFIG_VALUE_0']
    config = open(os.path.join(dest, '.git', 'config')).read()
    assert secret not in config and encoded not in config


def test_memory_endpoints(api, monkeypatch):
    from cortex_graph import brain, pipeline
    calls = []
    monkeypatch.setattr(pipeline, 'rebuild', lambda project, include_tests=None: calls.append(project), raising=False)
    status, saved = api.post('/api/memory', {'text': 'Vivo en Bilbao', 'project': 'yo-server', 'category': 'identity', 'about': ['Bilbao']})
    assert status == 201 and saved['status'] == 'new' and saved['memory']['category'] == 'identity'
    status, again = api.post('/api/memory', {'text': 'vivo en bilbao', 'project': 'yo-server'})
    assert status == 200 and again['status'] == 'duplicate'
    status, recalled = api.get('/api/query/recall?q=%C2%BFd%C3%B3nde+vivo%3F&project=yo-server&budget=500')
    assert status == 200 and recalled['items'][0]['id'] == saved['id'] and recalled['tokens'] <= 500
    status, hinted = api.get('/api/query/recall?q=mi+ciudad&project=yo-server&hints=Bilbao,vivo')
    assert status == 200 and hinted['hints'] == ['Bilbao', 'vivo'] and hinted['items'][0]['id'] == saved['id']
    assert api.get('/api/query/recall?q=x&project=yo-server&hints=' + ','.join(f'a{k}' for k in range(40)))[0] == 400
    status, prof = api.get('/api/query/profile?project=yo-server')
    assert status == 200 and '## Quién es' in prof['markdown']
    status, line = api.get('/api/query/timeline?project=yo-server&about=bilbao')
    assert status == 200 and line['items'][0]['key'] == f"r:{saved['id']}"
    status, listed = api.get('/api/query/memories?project=yo-server')
    assert status == 200 and listed['total'] == 1 and listed['memories'][0]['text'] == 'Vivo en Bilbao'
    assert api.post('/api/memory', {'text': '', 'project': 'yo-server'})[0] == 400
    assert api.post('/api/memory', {'text': 'x', 'project': 'yo-server', 'category': 7})[0] == 400
    assert api.post('/api/memory', {'text': 'x', 'project': 'yo-server', 'confidence': 'mucha'})[0] == 400
    assert api.get('/api/query/recall?q=&project=yo-server')[0] == 400
    status, gone = api.post('/api/memory/forget', {'ref': saved['id'], 'project': 'yo-server'})
    assert status == 200 and gone['forgotten'] == [saved['id']]
    assert api.post('/api/memory/forget', {'ref': 'nada parecido', 'project': 'yo-server'})[0] == 404
    for _ in range(200):
        if not brain.rebuilding():
            break
        time.sleep(0.02)
    assert set(calls) == {'yo-server'}
