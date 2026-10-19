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
