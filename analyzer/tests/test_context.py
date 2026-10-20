import os
import shutil
import time

import pytest

from conftest import FILES, write_repo
from cortex_graph import context, pipeline, query, store
from cortex_graph.errors import InvalidInput, NotFound

AWS = 'AKIA' + 'ABCDEFGHIJKLMNOP'
GITHUB = 'gh' + 'p_' + 'A1b2C3d4' * 5
GITHUB_PAT = 'github' + '_pat_' + 'x' * 30
SLACK = 'xo' + 'xb-' + '1234567890-abcdefghijkl'
STRIPE = 'sk' + '_live_' + '9' * 24
JWT = 'ey' + 'JhbGciOiJIUzI1NiJ9.' + 'ey' + 'JzdWIiOiIxMjM0NTYifQ.' + 'abcdefghijklmnopqrstuv'
KEY_LINE = 'MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQ'
SECRETS = (AWS, GITHUB, GITHUB_PAT, SLACK, STRIPE, JWT, KEY_LINE, 'hunter22', 'abcd1234efgh', 's3cr3tpw')


def secrets_module():
    begin, end = '-----BEGIN ' + 'PRIVATE KEY-----', '-----END ' + 'PRIVATE KEY-----'
    return '\n'.join([
        'def load_config():',
        f'    aws = "{AWS}"',
        f'    gh = "{GITHUB}"',
        f'    pat = "{GITHUB_PAT}"',
        f'    slack = "{SLACK}"',
        f'    stripe = "{STRIPE}"',
        f'    jwt = "{JWT}"',
        f'    key = """{begin}',
        f'{KEY_LINE}',
        f'{end}"""',
        '    password = "hunter22"',
        "    API_KEY: str = 'abcd1234efgh'",
        '    url = "postgres://admin:s3cr3tpw@db:5432/app"',
        '    token_url = "{base}/token"',
        '    return locals()',
        '',
    ])


def big_module():
    body = ''.join(f'    total += {i}\n' for i in range(450))
    return f'def huge():\n    total = 0\n{body}    return total\n'


@pytest.fixture
def project(tmp_path, data_dir):
    root = write_repo(tmp_path / 'demo')
    (root / 'app/secrets.py').write_text(secrets_module(), encoding='utf-8')
    (root / 'app/big.py').write_text(big_module(), encoding='utf-8')
    pipeline.analyze_source(str(root), 'demo', include_tests=True)
    return root


def test_redact_patterns():
    text, count = context.redact(secrets_module())
    for secret in SECRETS:
        assert secret not in text
    assert count >= 10
    assert '"{base}/token"' in text and 'def load_config():' in text
    assert text.count('\n') == secrets_module().count('\n')
    assert context.redact('x = compute_token(user)\npassword = os.environ["PW"]\n') == (
        'x = compute_token(user)\npassword = os.environ["PW"]\n', 0)


def test_read_symbol_exact_range(project):
    r = query.node('create_user')
    line = r['node']['line']
    s = context.read_symbol('create_user')
    lines = s['code'].split('\n')
    assert lines[0] == 'def create_user(name):' and lines[-1].strip() == 'return user'
    assert s['start'] == line and s['file'] == 'app/services.py' and s['language'] == 'python'
    assert 'UserService' not in s['code'] and s['redacted'] == 0 and not s['truncated']
    wider = context.read_symbol('f:app/services.py:create_user', context=2)
    assert wider['start'] == line - 2 and wider['end'] >= s['end'] + 1
    method = context.read_symbol('UserService.helper')
    assert method['code'].strip().startswith('def helper(self):') and 'create_user' in method['code']
    module = context.read_symbol('app/utils.py')
    assert module['start'] == 1 and 'def slugify' in module['code']
    with pytest.raises(InvalidInput):
        context.read_symbol('create_user', context='lots')
    with pytest.raises(NotFound):
        context.read_symbol('zzz-nothing-here')


def test_read_symbol_truncates_and_redacts(project):
    big = context.read_symbol('huge')
    assert big['truncated'] and big['end'] - big['start'] + 1 == context.MAX_LINES
    assert big['code'].split('\n')[-1].startswith('… (truncado')
    assert big['symbol_end'] > big['end']
    secret = context.read_symbol('load_config')
    assert secret['redacted'] >= 10 and context.REDACTED in secret['code']
    for value in SECRETS:
        assert value not in secret['code']


def test_read_symbol_source_location(project, data_dir, tmp_path):
    stamp = time.time() + 3600
    os.utime(project / 'app/utils.py', (stamp, stamp))
    assert context.read_symbol('slugify').get('stale') is True
    fuente = data_dir / 'demo' / 'fuente'
    write_repo(fuente, {'app/utils.py': "def slugify(text):\n    return 'from-store'\n"})
    assert 'from-store' in context.read_symbol('slugify')['code']
    shutil.rmtree(fuente)
    shutil.move(str(project), str(tmp_path / 'moved'))
    with pytest.raises(NotFound, match='no está disponible'):
        context.read_symbol('slugify')
    plain = context.context_for('slugify text')
    assert plain['source'] is False and plain['items'] and '```' not in plain['markdown']


def test_read_text_stays_inside_root(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    (tmp_path / 'outside.py').write_text('secret = 1\n')
    (root / 'inside.py').write_text('x = 1\n')
    assert query.read_text(str(root), 'inside.py', 1000) == 'x = 1\n'
    assert query.read_text(str(root), '../outside.py', 1000) is None
    assert query.read_text(str(root), 'inside.py', 2) is None
    try:
        os.symlink(tmp_path / 'outside.py', root / 'link.py')
    except (OSError, NotImplementedError):
        return
    assert query.read_text(str(root), 'link.py', 1000) is None


def test_context_for_ranks_and_fits_budget(project):
    r = context.context_for('how is a user created', budget=2000)
    assert r['items'][0]['name'] == 'create_user' and r['items'][0]['seed']
    assert r['tokens_used'] <= 2000 and r['source'] is True
    assert '```python\ndef create_user(name):' in r['markdown']
    assert r['markdown'].startswith('# Contexto · demo v1')
    assert {'User', 'slugify'} <= {i['name'] for i in r['items']}
    assert 'test_create_user' in {t['name'] for t in r['tests']}
    assert not any(i.get('test') for i in r['items'])
    assert context.tokens(r['markdown']) == r['tokens_used']
    small = context.context_for('how is a user created', budget=500)
    assert small['tokens_used'] <= 500 and small['items']
    exact = context.context_for('rename f:app/utils.py:slugify everywhere', budget=1500)
    assert 'f:app/utils.py:slugify' in exact['seeds'][:2]
    secret = context.context_for('load_config', budget=3000)
    assert secret['items'][0]['name'] == 'load_config'
    for value in SECRETS:
        assert value not in secret['markdown']


def test_context_for_edge_cases(project):
    none = context.context_for('zzzqqq')
    assert none['items'] == [] and 'Nada en el grafo' in none['markdown']
    with pytest.raises(InvalidInput):
        context.context_for('   ')
    with pytest.raises(InvalidInput):
        context.context_for('x' * 600)
    with pytest.raises(InvalidInput):
        context.context_for('user', budget='big')
    tests = context.context_for('test create user')
    assert any(i.get('test') for i in tests['items'])
    first = context.context_for('user service helper')
    second = context.context_for('user service helper')
    assert first['markdown'] == second['markdown']


def test_brief_includes_new_meta(data_dir, tmp_path):
    root = write_repo(tmp_path / 'meta', {'app/a.py': FILES['app/utils.py']})
    pipeline.analyze_source(str(root), 'meta')
    index = query.load_index('meta')
    n = dict(index.by_key['f:app/a.py:slugify'], sig='def slugify(text)', doc='Make a slug. ' * 40, end=2, vis='public')
    b = index.brief(n)
    assert b['sig'] == 'def slugify(text)' and b['end'] == 2 and b['vis'] == 'public'
    assert len(b['doc']) == query.MAX_BRIEF_DOC and b['doc'].endswith('…')
    assert store.slug('meta') == index.project


def save_knowledge(root):
    specs = [
        ('k:chats/c.json#a1', 'conversation', 'Planes de viaje', 'chats/c.json', 1, {'started': '2025-05-01', 'doc': 'viaje a Japón'}),
        ('u:ana-lopez', 'person', 'Ana López', '', 0, {}),
        ('r:abc123def456', 'memory', 'Quiero viajar a Japón con Ana', '', 0, {'text': 'Quiero viajar a Japón con Ana', 'category': 'goal'}),
        ('s:notas/v.md#japon', 'section', 'Japón', 'notas/v.md', 1, {'end': 3, 'doc': 'Kioto en otoño'}),
    ]
    nodes = [{'id': i, 'key': k, 'kind': kind, 'name': name, 'file': f, 'line': line, 'c': 0, 'deg': 1, 'pos': [0.0, 0.0, 0.0], 'hash': k, **extra}
             for i, (k, kind, name, f, line, extra) in enumerate(specs)]
    ids = {n['key']: n['id'] for n in nodes}
    pairs = [('r:abc123def456', 'k:chats/c.json#a1', 'from'), ('r:abc123def456', 'u:ana-lopez', 'about'),
             ('k:chats/c.json#a1', 'u:ana-lopez', 'participant'), ('s:notas/v.md#japon', 'u:ana-lopez', 'mentions')]
    graph = {'project': 'notas', 'nodes': nodes, 'edges': [{'a': ids[a], 'b': ids[b], 'kind': k, 'w': 1} for a, b, k in pairs], 'visible': [],
             'communities': [{'id': 0, 'name': 'memoria', 'hub': 'c.json', 'size': 4, 'center': [0, 0, 0], 'radius': 1.0, 'color': [1, 1, 1]}],
             'stats': {'files': 2, 'nodes': 4, 'edges': len(pairs), 'communities': 1}}
    store.save_version(graph, {'type': 'local', 'path': str(root)})


def test_knowledge_projects_read_and_context(data_dir, tmp_path, monkeypatch):
    import sys
    import types
    import cortex_graph
    root = tmp_path / 'notas'
    (root / 'chats').mkdir(parents=True)
    (root / 'chats' / 'c.json').write_text('[{"x": 1}]', encoding='utf-8')
    (root / 'notas').mkdir()
    (root / 'notas' / 'v.md').write_text('# Japón\n\nKioto en otoño con Ana.\n', encoding='utf-8')
    conversation = {'id': 'a1', 'messages': [{'i': 0, 'role': 'user', 'author': 'Marina', 'time': '2025-05-01T10:00:00',
                                              'text': f'Quiero ir a Japón, mi clave es {AWS}'},
                                             {'i': 1, 'role': 'assistant', 'author': '', 'time': None, 'text': '¡Qué buen plan!'}]}
    fake = types.SimpleNamespace(load=lambda r, rel, fmt=None: [conversation] if rel == 'chats/c.json' else [])
    monkeypatch.setitem(sys.modules, 'cortex_graph.importers', fake)
    monkeypatch.setattr(cortex_graph, 'importers', fake, raising=False)
    save_knowledge(root)
    memory = context.read_symbol('r:abc123def456', 'notas')
    assert memory['code'] == 'Quiero viajar a Japón con Ana' and memory['language'] == 'markdown' and memory['file'] == ''
    chat = context.read_symbol('k:chats/c.json#a1', 'notas')
    assert '**Marina** · 2025-05-01 10:00: Quiero ir a Japón' in chat['code'] and AWS not in chat['code']
    assert '**asistente**: ¡Qué buen plan!' in chat['code'] and chat['redacted'] >= 1
    section = context.read_symbol('s:notas/v.md#japon', 'notas')
    assert section['code'].startswith('# Japón')
    ctx = context.context_for('viaje a Japón con Ana', 'notas', budget=1500)
    keys = [i['key'] for i in ctx['items']]
    assert 'r:abc123def456' in keys and 'u:ana-lopez' in keys
    assert '> Quiero viajar a Japón con Ana' in ctx['markdown'] and ctx['tokens_used'] <= 1500
