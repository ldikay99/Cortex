import re

import pytest

from conftest import by_key, edge_set, write_repo
from cortex_graph.analyze import analyze, cap_visible, export_json, export_markdown, is_test, list_files
from cortex_graph.errors import CortexError


@pytest.fixture
def graph(repo):
    return analyze(repo, 'demo')


def test_nodes_have_expected_kinds_and_metadata(graph):
    nodes = by_key(graph)
    expected = {
        'm:app/services.py': 'module', 'c:app/models.py:User': 'class', 'f:app/models.py:User.greet': 'method',
        'f:app/services.py:create_user': 'function', 'd:docs/README.md': 'doc', 'm:web/src/pages/Home.tsx': 'module',
        'f:web/src/components/Button.tsx:Button': 'function', 'f:web/src/lib/format.ts:upper': 'function',
    }
    for key, kind in expected.items():
        assert nodes[key]['kind'] == kind
    assert nodes['f:app/api.py:list_users']['route'] == 'GET /users'
    assert nodes['c:app/models.py:User']['table'] == 'users'
    assert nodes['f:app/models.py:User.greet']['parent'] == nodes['c:app/models.py:User']['id']
    assert not any(n['file'].startswith('node_modules/') for n in graph['nodes'])
    assert [n['id'] for n in graph['nodes']] == list(range(len(graph['nodes'])))
    for n in graph['nodes']:
        assert re.fullmatch(r'[0-9a-f]{12}', n['hash'])
        assert len(n['pos']) == 3
    assert graph['stats']['kinds'] == {'doc': 2, 'module': 12, 'function': 9, 'class': 3, 'method': 6}
    assert graph['stats']['warnings'] == [] and graph['stats']['warnings_total'] == 0


def test_edges_cover_imports_calls_inheritance_and_docs(graph):
    edges = edge_set(graph)
    expected = {
        ('m:app/services.py', 'm:app/models.py', 'import'),
        ('m:app/services.py', 'm:app/utils.py', 'import'),
        ('m:app/api.py', 'm:app/services.py', 'import'),
        ('m:app/models.py', 'm:app/base.py', 'import'),
        ('f:app/services.py:create_user', 'f:app/utils.py:slugify', 'call'),
        ('f:app/services.py:create_user', 'c:app/models.py:User', 'call'),
        ('f:app/services.py:UserService.run', 'f:app/services.py:UserService.helper', 'call'),
        ('f:app/api.py:list_users', 'f:app/services.py:create_user', 'call'),
        ('c:app/models.py:User', 'c:app/base.py:Base', 'inherits'),
        ('m:web/src/pages/Home.tsx', 'm:web/src/components/Button.tsx', 'import'),
        ('m:web/src/pages/Home.tsx', 'm:web/src/lib/format.ts', 'import'),
        ('f:web/src/pages/Home.tsx:Home', 'f:web/src/components/Button.tsx:Button', 'call'),
        ('f:web/src/pages/Home.tsx:Home', 'f:web/src/lib/format.ts:formatName', 'call'),
        ('f:web/src/pages/Home.test.ts:testHome', 'f:web/src/pages/Home.tsx:Home', 'tests'),
        ('d:docs/README.md', 'm:app/services.py', 'ref'),
        ('d:docs/README.md', 'm:web/src/pages/Home.tsx', 'ref'),
        ('d:docs/README.md', 'd:docs/guide.md', 'ref'),
        ('d:docs/guide.md', 'm:app/utils.py', 'ref'),
        ('m:app/services.py', 'd:docs/guide.md', 'loads'),
        ('m:app/models.py', 'c:app/models.py:User', 'contains'),
    }
    assert expected <= edges
    assert graph['stats']['edge_kinds'] == {'contains': 18, 'import': 9, 'call': 8, 'tests': 2, 'inherits': 1, 'loads': 1, 'ref': 4}


def test_communities_and_visible_edges(graph):
    assert graph['communities']
    ids = {c['id'] for c in graph['communities']}
    assert all(n['c'] in ids for n in graph['nodes'])
    assert sum(c['size'] for c in graph['communities']) == len(graph['nodes'])
    nodes = graph['nodes']
    file_pairs = {frozenset((nodes[e['a']]['file'], nodes[e['b']]['file'])) for e in graph['edges']}
    exact = {frozenset((e['a'], e['b'])) for e in graph['edges']}
    for e in graph['visible']:
        assert 0 <= e['a'] < len(nodes) and 0 <= e['b'] < len(nodes)
        if frozenset((e['a'], e['b'])) not in exact:
            assert e['kind'] == 'import'
            assert nodes[e['a']]['kind'] in ('module', 'doc') and nodes[e['b']]['kind'] in ('module', 'doc')
            assert frozenset((nodes[e['a']]['file'], nodes[e['b']]['file'])) in file_pairs
    assert not any(e['kind'] == 'call' for e in graph['visible'])


def test_analysis_is_deterministic(repo, graph):
    again = analyze(repo, 'demo')
    assert again['nodes'] == graph['nodes'] and again['edges'] == graph['edges'] and again['visible'] == graph['visible']


def test_parse_errors_become_warnings(tmp_path):
    root = write_repo(tmp_path / 'broken', {'ok.py': 'def fine():\n    return 1\n', 'bad.py': 'def broken(:\n', 'notes.md': 'see ok.py'})
    graph = analyze(root, 'broken')
    assert graph['stats']['warnings_total'] == 1
    assert graph['stats']['warnings'][0]['file'] == 'bad.py'
    assert 'sintaxis' in graph['stats']['warnings'][0]['error']
    assert 'f:ok.py:fine' in by_key(graph)


def test_empty_project_raises_clear_error(tmp_path):
    (tmp_path / 'empty').mkdir()
    with pytest.raises(CortexError, match='no hay archivos'):
        analyze(tmp_path / 'empty')
    with pytest.raises(CortexError, match='no existe'):
        analyze(tmp_path / 'missing')


def test_visible_cap_keeps_structural_and_heaviest():
    edges = [{'a': i, 'b': i + 1, 'kind': 'import', 'w': i} for i in range(10)] + [{'a': 0, 'b': 5, 'kind': 'contains', 'w': 1}]
    kept = cap_visible(edges, limit=4)
    assert len(kept) == 4
    assert {'a': 0, 'b': 5, 'kind': 'contains', 'w': 1} in kept
    assert sorted(e['w'] for e in kept if e['kind'] == 'import') == [7, 8, 9]


def test_is_test_and_list_files(repo):
    assert is_test('tests/test_services.py') and is_test('web/src/pages/Home.test.ts') and is_test('pkg/conftest.py')
    assert is_test('a/b_test.py') and is_test('spec/x.ts') and not is_test('app/services.py')
    files = list_files(repo)
    assert 'app/services.py' in files and 'docs/README.md' in files and 'web/tsconfig.json' in files
    assert not any(f.startswith('node_modules/') for f in files)
    no_tests = list_files(repo, skip_tests=True)
    assert 'tests/test_services.py' not in no_tests and 'web/src/pages/Home.test.ts' not in no_tests
    excluded = list_files(repo, exclude=['web/', 'docs/guide.md'])
    assert not any(f.startswith('web/') for f in excluded) and 'docs/guide.md' not in excluded and 'docs/README.md' in excluded


def test_exports(graph):
    md = export_markdown(graph)
    for section in ('# Grafo de conocimiento · demo', '## Comunidades', '## Nodos más conectados', '## Rutas de la API', '`GET /users`',
                    '## Tablas de base de datos', '`users`', '## Documentos'):
        assert section in md
    data = export_json(graph)
    assert data['project'] == 'demo' and len(data['nodes']) == len(graph['nodes']) and len(data['edges']) == len(graph['edges'])
    assert {'source', 'target', 'kind', 'weight'} == set(data['edges'][0])
    assert 'pos' not in data['nodes'][0]
