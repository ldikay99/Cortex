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
    assert o['stats']['nodes'] == 32 and o['communities'][0]['files'] == 14
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
    assert set(names(n['calls'])) == {'slugify', 'User'}
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
