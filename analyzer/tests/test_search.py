import pytest

from cortex_graph import search


def node(i, name, kind='function', file='pkg/mod.py', **meta):
    return {'id': i, 'key': f'f:{file}:{name}', 'kind': kind, 'name': name, 'file': file, 'line': i + 1, 'deg': meta.pop('deg', 1), 'c': 0, **meta}


def names(index, text, **kwargs):
    ranked, _ = index.search(text, **kwargs)
    return [r[3]['name'] for r in ranked]


def test_identifier_splitting_and_stemming():
    assert search.words('parseHTTPRequest2JSON') == ['parse', 'http', 'request', '2', 'json']
    assert search.words('create_user-name.v2') == ['create', 'user', 'name', '2']
    assert search.words('ShouldBindJSON') == ['should', 'bind', 'json']
    assert search.words('a b') == []
    assert search.words('añadirUsuario') == ['añadirusuario']
    assert search.stem('validation') == search.stem('validate') == search.stem('validated')
    assert search.stem('binding') == search.stem('bind')
    assert search.stem('services') == search.stem('service')
    assert search.stem('user') == 'user' and search.stem('status') == 'status'
    assert search.query_terms('How does the binding validate a request?') == ['bind', 'validat', 'request']
    assert search.query_terms('the a') == ['the']


def test_field_boosts_and_ranking():
    nodes = [
        node(0, 'validateStruct', sig='func validateStruct(obj any) error', doc='Validates a struct with tags.'),
        node(1, 'render', doc='Renders a template; validate is not done here.'),
        node(2, 'Bind', kind='method', file='binding/binding.go', sig='func Bind(req *http.Request, obj any) error',
             doc='Bind decodes the request body and validates it.'),
        node(3, 'helpers.go', kind='module', file='validate/helpers.go'),
        node(4, 'unrelated'),
    ]
    index = search.Index(nodes)
    ranked = names(index, 'validate')
    assert ranked[0] == 'validateStruct'
    assert ranked.index('helpers.go') < ranked.index('render')
    assert 'unrelated' not in ranked
    assert names(index, 'how does binding validate a request')[0] == 'Bind'
    assert names(index, 'decodes body')[0] == 'Bind'
    assert names(index, 'validate', kind='module') == ['helpers.go']


def test_exact_and_prefix_bonuses():
    nodes = [
        node(0, 'UserService.create_user', kind='method', doc='create user create user create user'),
        node(1, 'create_user'),
        node(2, 'create_user_profile'),
        node(3, 'Router', kind='class', file='app/router.py'),
        node(4, 'RouterGroup', kind='class', file='app/group.py', deg=50),
        node(5, 'list_users', route='GET /users'),
        node(6, 'User', kind='class', table='users', deg=9),
    ]
    index = search.Index(nodes)
    assert names(index, 'create_user')[:3] == ['create_user', 'UserService.create_user', 'create_user_profile']
    assert names(index, 'router')[0] == 'Router'
    assert names(index, 'routergr')[0] == 'RouterGroup'
    assert names(index, '/users')[0] == 'list_users'
    assert names(index, 'GET /users')[0] == 'list_users'
    assert names(index, 'users')[0] == 'User'
    assert names(index, 'pkg/mod.py')[0] in {n['name'] for n in nodes}


def test_coverage_beats_single_term_and_tests_rank_lower():
    nodes = [
        node(0, 'create_user', file='app/services.py'),
        node(1, 'UserService', kind='class', file='app/services.py'),
        node(2, 'test_create_user', file='tests/test_services.py', test=True),
        node(3, 'create_order', file='app/orders.py'),
    ]
    index = search.Index(nodes)
    assert names(index, 'services create')[0] == 'create_user'
    assert names(index, 'create user')[:2] == ['create_user', 'test_create_user']
    assert names(index, 'test create user')[0] == 'test_create_user'
    ranked, total = index.search('create')
    assert total == 3 and ranked[-1][3]['name'] == 'test_create_user'


def test_prefix_expansion_and_substring_fallback():
    nodes = [node(0, 'serializeResponse'), node(1, 'x1'), node(2, 'q')]
    index = search.Index(nodes)
    assert names(index, 'serial') == ['serializeResponse']
    assert names(index, 'q') == ['q']
    assert names(index, 'zzz') == []
    ranked, total = index.search('x')
    assert total == 1 and ranked[0][3]['name'] == 'x1'


def test_scores_are_deterministic():
    nodes = [node(i, f'handler{i}', file=f'pkg/h{i}.py') for i in range(30)]
    index = search.Index(nodes)
    first = [(r[3]['id'], r[0]) for r in index.search('handler')[0]]
    second = [(r[3]['id'], r[0]) for r in search.Index(nodes).search('handler')[0]]
    assert first == second and len(first) == 30


@pytest.fixture
def project(repo, data_dir):
    from cortex_graph import pipeline
    pipeline.analyze_source(str(repo), 'demo', include_tests=True)
    return repo


def test_query_search_shape(project):
    from cortex_graph import query
    r = query.search('create user')
    assert r['results'][0]['name'] == 'create_user'
    assert all('score' in x for x in r['results'])
    assert [x['score'] for x in r['results']] == sorted((x['score'] for x in r['results']), reverse=True)
    assert r['terms'] == ['creat', 'user']
    page = query.search('user', limit=2, offset=1)
    assert page['offset'] == 1 and len(page['results']) == 2
    assert page['results'][0]['key'] == query.search('user', limit=2)['results'][1]['key']
    index = query.load_index()
    assert index.text_index() is index.text_index()


def test_spanish_questions_expand_to_english_identifiers():
    from cortex_graph.search import query_terms
    assert {'add', 'product', 'cart'} <= set(query_terms('cómo se agrega un producto al carrito'))
    assert {'send', 'email'} <= set(query_terms('enviar correo de confirmación'))
    assert {'delet', 'ord'} <= set(query_terms('eliminar pedidos'))
    assert query_terms('add item to cart') == ['add', 'item', 'cart']
