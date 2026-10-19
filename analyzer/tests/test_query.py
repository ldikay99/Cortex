import pytest

from cortex_graph import pipeline, query
from cortex_graph.errors import InvalidInput, NotFound


@pytest.fixture
def project(repo, data_dir):
    pipeline.analyze_source(str(repo), 'demo', include_tests=True)
    return repo


def names(items):
    return [i['name'] for i in items]


def test_overview(project):
    o = query.overview()
    assert o['project'] == 'demo' and o['version'] == 1 and o['versions'] == 1
    assert sum(o['stats']['kinds'].get(k, 0) for k in ('module', 'doc', 'class', 'function', 'method')) == 32 and o['communities'][0]['files'] == 14
    assert len(o['top_nodes']) == 20
    assert o['top_nodes'][0]['deg'] >= o['top_nodes'][-1]['deg']
    assert [r['route'] for r in o['routes']] == ['GET /users']
    assert [t['table'] for t in o['tables']] == ['users']
    assert o['origin']['type'] == 'local'


def test_search(project):
    r = query.search('create_user')
    assert r['results'][0]['key'] == 'f:app/services.py:create_user'
    assert query.search('greet')['results'][0]['name'] == 'User.greet'
    assert all(n['kind'] == 'class' for n in query.search('user', kind='class')['results'])
    assert len(query.search('a', limit=3)['results']) == 3
    assert query.search('services create')['results'][0]['name'] == 'create_user'
    assert query.search('/users')['results'][0]['name'] == 'list_users'
    assert query.search('zzz')['total'] == 0
    with pytest.raises(InvalidInput):
        query.search('  ')
    with pytest.raises(InvalidInput):
        query.search('x', kind='planet')
    with pytest.raises(InvalidInput):
        query.search('x', limit='many')


def test_node_resolution_and_context(project):
    n = query.node('create_user')
    assert n['node']['key'] == 'f:app/services.py:create_user'
    assert n['parent']['key'] == 'm:app/services.py'
    assert {'slugify', 'User'} <= set(names(n['calls']))
    assert set(names(n['called_by'])) == {'UserService.helper', 'list_users'}
    assert set(names(n['tested_by'])) == {'test_create_user'}
    assert n['status'] == 'unchanged' and n['community']['name']
    user = query.node('c:app/models.py:User')
    assert names(user['inherits']) == ['Base']
    assert names(user['children']) == ['User.__init__', 'User.greet', 'User.describe']
    module = query.node('app/services.py')
    assert module['node']['kind'] == 'module'
    assert set(names(module['imports'])) == {'models.py', 'utils.py'}
    assert 'README.md' in names(module['referenced_by'])
    assert names(module['loads']) == ['guide.md']
    assert query.node('SLUGIFY')['node']['name'] == 'slugify'
    assert query.node('services.py')['node']['key'] == 'm:app/services.py'
    assert query.node('formatna')['node']['name'] == 'formatName'
    with pytest.raises(NotFound):
        query.node('does-not-exist-anywhere')
    with pytest.raises(InvalidInput):
        query.node('')


def test_file_context(project):
    f = query.file('app/services.py')
    assert [s['name'] for s in f['symbols']] == ['create_user', 'UserService', 'UserService.run', 'UserService.helper']
    assert f['imports'] == ['app/models.py', 'app/utils.py']
    assert set(f['imported_by']) == {'app/api.py', 'tests/test_services.py'}
    assert f['docs'] == ['docs/README.md']
    assert {c['file'] for c in f['called_from']} == {'app/api.py'}
    assert query.file('./pages/Home.tsx')['file'] == 'web/src/pages/Home.tsx'
    assert query.file('Button')['file'] == 'web/src/components/Button.tsx'
    doc = query.file('docs/guide.md')
    assert doc['node']['kind'] == 'doc' and doc['mentions'] == ['app/utils.py']


def test_community(project):
    c = query.community(0)
    assert c['community']['id'] == 0 and c['files'][0]['deg'] >= c['files'][-1]['deg']
    assert len(c['files']) == 14 and c['hubs']
    assert query.community(c['community']['name'])['community']['id'] == 0
    with pytest.raises(NotFound):
        query.community('99')


def test_path(project):
    p = query.path('list_users', 'slugify')
    assert p['found'] and p['length'] == 2
    assert [s['node']['name'] for s in p['steps']] == ['list_users', 'create_user', 'slugify']
    assert [s['via']['kind'] for s in p['steps'][1:]] == ['call', 'call']
    assert p['steps'][1]['via']['direction'] == 'forward'
    back = query.path('slugify', 'list_users')
    assert [s['via']['direction'] for s in back['steps'][1:]] == ['backward', 'backward']
    assert query.path('slugify', 'slugify')['length'] == 0


def test_impact(project):
    r = query.impact('slugify', depth=3)
    by_distance = {level['distance']: set(names(level['nodes'])) for level in r['levels']}
    assert by_distance[1] == {'create_user'}
    assert {'UserService.helper', 'list_users', 'test_create_user'} <= by_distance[2]
    assert 'UserService.run' in by_distance[3]
    assert r['total'] == sum(level['count'] for level in r['levels'])
    shallow = query.impact('slugify', depth=1)
    assert [level['distance'] for level in shallow['levels']] == [1]
    module = query.impact('app/models.py', depth=1)
    assert {'create_user', 'services.py', '__init__.py'} <= set(names(module['levels'][0]['nodes']))
    doc_impact = query.impact('app/utils.py', depth=1)
    assert {'guide.md', 'create_user', 'services.py'} <= set(names(doc_impact['levels'][0]['nodes']))


def test_changes_and_project_selection(project, data_dir):
    first = query.changes()
    assert first['from_version'] is None and first['counts'] == {'added': 0, 'modified': 0, 'removed': 0}
    (project / 'app/utils.py').write_text('def slugify(text):\n    return text\n\n\ndef extra():\n    return 1\n')
    pipeline.analyze_source(str(project), 'demo', include_tests=True)
    r = query.changes('demo')
    assert r['from_version'] == 1 and r['to_version'] == 2
    assert names(r['added']) == ['extra']
    assert 'slugify' in names(r['modified'])
    assert query.changes(since=2)['counts'] == {'added': 0, 'modified': 0, 'removed': 0}
    with pytest.raises(NotFound):
        query.changes(since=7)
    with pytest.raises(NotFound):
        query.overview('nadie')
    assert query.node('extra')['status'] == 'new'
    assert '# Grafo de conocimiento · demo' in query.report()


def test_no_projects(data_dir):
    with pytest.raises(NotFound, match='todavía no hay proyectos'):
        query.overview()


ARCH_FILES = {
    'pkg/__init__.py': '',
    'pkg/a.py': """
        from pkg import b


        def fa():
            return b.fb()


        def _unused_helper():
            return 1
    """,
    'pkg/b.py': """
        from pkg import a


        def fb():
            return 2


        def late():
            return a.fa()
    """,
    'pkg/cli.py': """
        def main():
            return 0
    """,
    'pyproject.toml': """
        [project]
        name = "pkg"

        [project.scripts]
        pkgcli = "pkg.cli:main"
    """,
    'web/package.json': """
        {"name": "webtool", "bin": {"webtool": "./bin/run.js"}, "main": "src/index.js"}
    """,
    'web/bin/run.js': """
        export function run() { return 1; }
    """,
    'web/src/index.js': """
        export function start() { return 2; }
    """,
}


def test_architecture_on_real_analysis(tmp_path, data_dir):
    from conftest import write_repo
    root = write_repo(tmp_path / 'arch', ARCH_FILES)
    pipeline.analyze_source(str(root), 'arch')
    a = query.architecture('arch')
    assert set(query.SECTIONS) <= set(a)
    entries = {(e['kind'], e['name']): e for e in a['entry_points']['items']}
    assert entries[('script', 'pkgcli')]['node']['key'] == 'f:pkg/cli.py:main'
    assert entries[('bin', 'webtool')]['node']['file'] == 'web/bin/run.js'
    assert entries[('library', 'webtool')]['node']['file'] == 'web/src/index.js'
    cycles = a['cycles']['items']
    assert cycles and set(cycles[0]['files']) == {'pkg/a.py', 'pkg/b.py'}
    assert cycles[0]['example'][0] == cycles[0]['example'][-1]
    dead = a['dead_code']['items']
    assert dead[0]['name'] == '_unused_helper' and dead[0]['confidence'] == 'high'
    assert 'fa' not in {d['name'] for d in dead} and 'main' not in {d['name'] for d in dead}
    assert a['hotspots']['items'][0]['fan_in'] >= 1
    assert a['layers']['items'][0]['level'] == 0
    page = query.architecture('arch', section='dead_code', limit=1, offset=0)
    assert set(page) == {'project', 'version', 'dead_code'} and page['dead_code']['limit'] == 1
    assert len(page['dead_code']['items']) == 1 and page['dead_code']['total'] == a['dead_code']['total']
    with pytest.raises(InvalidInput):
        query.architecture('arch', section='planets')


def synthetic():
    rows = [
        ('m:app/server.py', 'module', 'server.py', 'app/server.py', 1, 0, {'churn': 10, 'last': '2026-01-01'}),
        ('f:app/server.py:get_user', 'function', 'get_user', 'app/server.py', 3, 0, {'sig': 'def get_user(id)', 'end': 6, 'vis': 'public'}),
        ('e:app/server.py:GET /users/:id', 'endpoint', 'GET /users/:id', 'app/server.py', 2, 0, {'route': 'GET /users/:id'}),
        ('m:web/client.ts', 'module', 'client.ts', 'web/client.ts', 1, 1, {'churn': 2}),
        ('f:web/client.ts:fetchUser', 'function', 'fetchUser', 'web/client.ts', 1, 1, {}),
        ('v:DATABASE_URL', 'variable', 'DATABASE_URL', '.env.example', 1, 0, {}),
        ('m:.env.example', 'module', '.env.example', '.env.example', 1, 0, {}),
        ('p:pypi:flask', 'package', 'flask', 'pyproject.toml', 4, 0, {'version': '3.0', 'ecosystem': 'pypi'}),
        ('t:user.created', 'topic', 'user.created', 'app/server.py', 5, 0, {}),
        ('f:app/worker.py:on_created', 'function', 'on_created', 'app/worker.py', 2, 0, {}),
        ('m:app/worker.py', 'module', 'worker.py', 'app/worker.py', 1, 0, {}),
        ('p:npm:left-pad', 'package', 'left-pad', 'web/client.ts', 1, 1, {'ecosystem': 'npm'}),
    ]
    ids = {key: i for i, (key, *_rest) in enumerate(rows)}
    nodes = [{'id': i, 'key': key, 'kind': kind, 'name': name, 'file': f, 'line': line, 'c': c, 'deg': 1, 'pos': [0, 0, 0], **meta}
             for i, (key, kind, name, f, line, c, meta) in enumerate(rows)]
    pairs = [
        ('m:app/server.py', 'f:app/server.py:get_user', 'contains', 1), ('m:web/client.ts', 'f:web/client.ts:fetchUser', 'contains', 1),
        ('m:app/worker.py', 'f:app/worker.py:on_created', 'contains', 1),
        ('e:app/server.py:GET /users/:id', 'f:app/server.py:get_user', 'handles', 1),
        ('f:web/client.ts:fetchUser', 'e:app/server.py:GET /users/:id', 'http', 2),
        ('f:app/server.py:get_user', 'v:DATABASE_URL', 'env', 1), ('m:.env.example', 'v:DATABASE_URL', 'env', 1),
        ('m:app/server.py', 'p:pypi:flask', 'depends', 1), ('m:web/client.ts', 'p:npm:left-pad', 'depends', 1),
        ('f:app/server.py:get_user', 't:user.created', 'event', 1), ('t:user.created', 'f:app/worker.py:on_created', 'event', 1),
        ('m:app/server.py', 'm:app/worker.py', 'cochange', 4),
    ]
    edges = [{'a': ids[a], 'b': ids[b], 'kind': k, 'w': w} for a, b, k, w in pairs]
    for n in nodes:
        if n['key'].startswith('f:') or n['key'].startswith('e:'):
            n['parent'] = ids['m:' + n['file']]
    graph = {'project': 'synth', 'version': 1, 'stats': {}, 'nodes': nodes, 'edges': edges,
             'communities': [{'id': 0, 'name': 'app', 'hub': 'server.py', 'size': 9}, {'id': 1, 'name': 'web', 'hub': 'client.ts', 'size': 3}]}
    return query.GraphIndex(graph, {'versions': [{'v': 1, 'date': '2026-01-01T00:00:00+0000'}]})


def test_dependencies_endpoints_variables_on_new_kinds():
    index = synthetic()
    deps = index.dependencies()
    assert deps['packages']['total'] == 2 and deps['ecosystems'] == {'npm': 1, 'pypi': 1}
    flask = next(p for p in deps['packages']['items'] if p['name'] == 'flask')
    assert flask['version'] == '3.0' and flask['users'] == 1 and flask['declared'] and flask['communities'] == ['app']
    assert deps['undeclared'] == 1
    one = index.dependencies('FLASK')
    assert one['package']['key'] == 'p:pypi:flask' and one['used_by']['items'] == [{'file': 'app/server.py', 'community': 'app'}]
    with pytest.raises(NotFound):
        index.dependencies('django')
    eps = index.endpoints()['endpoints']
    assert eps['total'] == 1
    ep = eps['items'][0]
    assert ep['method'] == 'GET' and ep['path'] == '/users/:id'
    assert ep['handlers'][0]['name'] == 'get_user' and ep['handlers'][0]['sig'] == 'def get_user(id)'
    assert ep['callers_total'] == 1 and ep['callers'][0]['name'] == 'fetchUser'
    assert index.endpoints(method='post')['endpoints']['total'] == 0
    vs = index.variables()['variables']['items']
    assert vs[0]['name'] == 'DATABASE_URL' and vs[0]['used_by_total'] == 1
    assert [d['file'] for d in vs[0]['defined_in']] == ['.env.example']
    assert index.variables(name='nope')['variables']['total'] == 0
    page = index.dependencies(limit=1, offset=1)['packages']
    assert page['offset'] == 1 and len(page['items']) == 1


def test_node_context_for_new_kinds_and_layers():
    index = synthetic()
    topic = index.node('t:user.created')
    assert [n['name'] for n in topic['producers']] == ['get_user'] and [n['name'] for n in topic['consumers']] == ['on_created']
    var = index.node('v:DATABASE_URL')
    assert var['defined_in'] == ['.env.example'] and [n['name'] for n in var['used_by']] == ['get_user']
    assert index.node('p:pypi:flask')['used_by'] == ['app/server.py']
    handler = index.node('get_user')
    assert [n['name'] for n in handler['handles']] == ['GET /users/:id']
    assert handler['node']['sig'] == 'def get_user(id)' and handler['node']['end'] == 6
    assert [n['name'] for n in handler['env_vars']] == ['DATABASE_URL'] and [n['name'] for n in handler['emits']] == ['user.created']
    endpoint = index.node('GET /users/:id')
    assert [n['name'] for n in endpoint['handled_by']] == ['get_user'] and [n['name'] for n in endpoint['http_callers']] == ['fetchUser']
    server = index.node('app/server.py')
    assert server['co_changes'] == [{'file': 'app/worker.py', 'weight': 4}] and server['node']['churn'] == 10
    layers = index.layers()
    assert [[c['name'] for c in row['communities']] for row in layers] == [['app'], ['web']]
    assert layers[1]['communities'][0]['depends_on'] == ['app']
    hot, basis = index.hotspots()
    assert hot[0]['file'] == 'app/server.py' and hot[0]['score'] == 10 and 'churn' in basis
    assert index.span(index.by_key['f:app/server.py:get_user']) == (3, 6)


def test_strongly_connected_and_cycle_path():
    graph = {'a': ['b'], 'b': ['c'], 'c': ['a', 'd'], 'd': [], 'e': ['e']}
    comps = query.strongly_connected(graph)
    assert ['a', 'b', 'c'] in comps and ['d'] in comps
    assert query.cycle_path(graph, 'a', {'a', 'b', 'c'}) == ['a', 'b', 'c', 'a']
