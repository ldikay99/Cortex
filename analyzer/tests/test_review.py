import os
import shutil
import subprocess

import pytest

from cortex_graph import pipeline, review
from cortex_graph.errors import InvalidInput

pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='git no está instalado')


def run(root, *args, date='2024-01-01T10:00:00', who='ana'):
    env = {**os.environ, 'GIT_AUTHOR_DATE': date, 'GIT_COMMITTER_DATE': date, 'GIT_AUTHOR_NAME': who,
           'GIT_AUTHOR_EMAIL': f'{who}@example.org', 'GIT_COMMITTER_NAME': who, 'GIT_COMMITTER_EMAIL': f'{who}@example.org',
           'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1'}
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True, env=env).stdout


def edit(root, rel, old, new):
    path = root / rel
    text = path.read_text(encoding='utf-8')
    assert old in text
    path.write_text(text.replace(old, new), encoding='utf-8')


def commit(root, message, date):
    run(root, 'add', '-A')
    run(root, 'commit', '-qm', message, date=date)
    return run(root, 'rev-parse', 'HEAD').strip()


@pytest.fixture
def git_repo(repo, data_dir):
    run(repo, 'init', '-q', '-b', 'main')
    commit(repo, 'init', '2024-01-01T10:00:00')
    for i in range(3):
        edit(repo, 'app/utils.py', "return text", f"# {i}\n    return text")
        edit(repo, 'app/services.py', "PROMPT", f"# {i}\nPROMPT")
        commit(repo, f'c{i}', f'2024-02-0{i + 1}T10:00:00')
    return repo


def analyzed(repo, include_tests=True):
    pipeline.analyze_source(str(repo), 'demo', include_tests=include_tests)
    return repo


def names(items):
    return [i['name'] for i in items]


def test_review_maps_changed_lines_to_symbols_impact_and_tests(git_repo):
    edit(git_repo, 'app/utils.py', "text.lower()", "text.strip().lower()")
    sha = commit(git_repo, 'strip', '2024-03-01T10:00:00')
    analyzed(git_repo)
    r = review.review(str(git_repo))
    assert (r['project'], r['base'], r['head'], r['graph_commit']) == ('demo', 'HEAD~1', 'HEAD', sha)
    assert r['warnings'] == []
    assert r['files'] == [{'file': 'app/utils.py', 'status': 'modified', 'added': 1, 'removed': 1, 'churn': 5,
                           'last': '2024-03-01', 'authors': 1, 'in_graph': True, 'symbols': 1}]
    [symbol] = r['symbols']
    assert (symbol['key'], symbol['kind'], symbol['change'], symbol['line']) == ('f:app/utils.py:slugify', 'function', 'modified', 1)
    levels = {lv['distance']: names(lv['nodes']) for lv in r['impact']['levels']}
    assert levels[1] == ['create_user']
    assert set(levels[2]) == {'UserService.helper', 'list_users'}
    assert r['impact']['total'] == sum(lv['count'] for lv in r['impact']['levels'])
    assert r['impact']['endpoints'] == ['GET /users']
    assert names(r['tests']['covering']) == ['test_create_user']
    assert r['tests']['covering'][0]['targets'] == ['slugify'] and r['tests']['source'] == 'graph'
    assert r['tests']['missing'] == []
    assert r['cochange'] == [{'file': 'app/services.py', 'with': 'app/utils.py', 'count': 4}]
    risk = r['risk']
    assert 0 < risk['score'] <= 100 and risk['level'] in ('bajo', 'medio', 'alto')
    factors = {x['factor'] for x in risk['reasons']}
    assert {'dependents', 'fan_in', 'endpoints', 'cochange'} <= factors and 'tests' not in factors
    assert risk['score'] == min(100, sum(x['points'] for x in risk['reasons']))
    assert review.review(str(git_repo)) == r


def test_review_innermost_symbol_and_missing_tests(git_repo):
    edit(git_repo, 'app/models.py', "return f'user {self.name}'", "return f'usuario {self.name}'")
    edit(git_repo, 'app/services.py', "class UserService:", "class UserService:\n    kind = 'svc'\n")
    commit(git_repo, 'texts', '2024-03-01T10:00:00')
    analyzed(git_repo)
    r = review.review(str(git_repo), project='demo')
    assert names(r['symbols']) == ['User.describe', 'UserService']
    assert [s['change'] for s in r['symbols']] == ['modified', 'modified']
    assert 'User.greet' in names(r['impact']['levels'][0]['nodes'])
    assert 'UserService.run' not in [n['name'] for lv in r['impact']['levels'] for n in lv['nodes']]
    assert r['tests']['missing'] == ['User.describe']
    assert names(r['tests']['covering']) == ['test_services.py'] and r['tests']['covering'][0]['via'] == 'import'
    tests = next(x for x in r['risk']['reasons'] if x['factor'] == 'tests')
    assert tests['points'] == 10


def test_review_worktree_with_new_deleted_and_untracked_files(git_repo):
    analyzed(git_repo)
    edit(git_repo, 'app/models.py', "return f'user {self.name}'", "return f'usuario {self.name}'")
    os.remove(git_repo / 'app/api.py')
    (git_repo / 'app/fresh.py').write_text('def fresh():\n    return 1\n', encoding='utf-8')
    r = review.review(str(git_repo), base='HEAD', head='WORKTREE')
    files = {f['file']: f for f in r['files']}
    assert files['app/api.py']['status'] == 'deleted' and files['app/api.py']['removed'] == 10
    assert files['app/fresh.py'] == {'file': 'app/fresh.py', 'status': 'added', 'added': 2, 'removed': 0, 'in_graph': False}
    assert files['app/models.py']['status'] == 'modified'
    changes = {s['key']: s['change'] for s in r['symbols']}
    assert changes == {'m:app/api.py': 'deleted', 'f:app/api.py:list_users': 'deleted', 'f:app/models.py:User.describe': 'modified',
                       'e:app/api.py:GET /users': 'deleted', 'p:pypi:fastapi': 'deleted'}
    assert 'GET /users' in r['impact']['endpoints']
    assert any('app/fresh.py' in w for w in r['warnings'])


def test_review_uses_base_side_when_graph_is_older(git_repo):
    analyzed(git_repo)
    edit(git_repo, 'app/services.py', "from app.models import User", "import os\nimport sys\nimport re\nfrom app.models import User")
    edit(git_repo, 'app/services.py', "user.save()", "user.save()\n    user.save()")
    commit(git_repo, 'shift', '2024-03-01T10:00:00')
    r = review.review(str(git_repo))
    assert names(r['symbols']) == ['create_user']
    assert any('base del diff' in w for w in r['warnings'])
    edit(git_repo, 'app/utils.py', "text.lower()", "text.casefold()")
    commit(git_repo, 'later', '2024-03-02T10:00:00')
    stale = review.review(str(git_repo))
    assert any('no es la base ni el final' in w for w in stale['warnings'])
    assert names(stale['symbols']) == ['slugify']


def test_review_diff_text_without_git_and_renames(git_repo):
    analyzed(git_repo)
    diff = '\n'.join([
        'diff --git a/app/utils.py b/app/text_utils.py', 'similarity index 100%', 'rename from app/utils.py', 'rename to app/text_utils.py',
        'diff --git a/demo/app/base.py b/demo/app/base.py', '--- a/demo/app/base.py', '+++ b/demo/app/base.py',
        '@@ -2,0 +3 @@', '+        print("x")', '',
    ])
    r = review.review(None, project='demo', diff_text=diff)
    files = {(f['file'], f['status']): f for f in r['files']}
    assert files[('app/utils.py', 'deleted')]['renamed_to'] == 'app/text_utils.py'
    assert files[('app/text_utils.py', 'added')]['in_graph'] is False
    assert files[('app/base.py', 'modified')]['added'] == 1
    changes = {s['key']: s['change'] for s in r['symbols']}
    assert changes['f:app/utils.py:slugify'] == 'deleted' and changes['f:app/base.py:Base.save'] == 'modified'
    assert 'deleted' in {x['factor'] for x in r['risk']['reasons']}


def test_review_without_analyzed_tests_searches_repository(git_repo):
    edit(git_repo, 'app/services.py', "user.save()", "user.save()\n    user.save()")
    commit(git_repo, 'save twice', '2024-03-01T10:00:00')
    analyzed(git_repo, include_tests=False)
    r = review.review(str(git_repo))
    assert r['tests']['source'] == 'grep'
    assert r['tests']['mentions'] == [{'file': 'tests/test_services.py', 'names': ['create_user']}]
    assert r['tests']['missing'] == []


def test_review_rejects_bad_refs(git_repo):
    analyzed(git_repo)
    for bad in ('--output=/tmp/x', 'a..b', 'x y', ''):
        with pytest.raises(InvalidInput):
            review.check_ref(bad, 'base')
    with pytest.raises(InvalidInput):
        review.review(str(git_repo), base='--output=x')


def test_parse_diff_statuses_and_counts():
    text = '\n'.join([
        'diff --git a/app/old.py b/app/new_name.py', 'similarity index 90%', 'rename from app/old.py', 'rename to app/new_name.py',
        '--- a/app/old.py', '+++ b/app/new_name.py', '@@ -1,2 +1,2 @@', '-x = 1', '+x = 2', ' y = 3',
        'diff --git a/app/gone.py b/app/gone.py', 'deleted file mode 100644', '--- a/app/gone.py', '+++ /dev/null',
        '@@ -1,2 +0,0 @@', '--- tricky', '-b',
        'diff --git a/img.png b/img.png', 'new file mode 100644', 'Binary files /dev/null and b/img.png differ',
        'diff --git a/m.py b/m.py', '--- a/m.py', '+++ b/m.py', '@@ -5 +5,2 @@', '-a', '+b', '+c', '@@ -9,0 +11 @@', '+d', '',
    ])
    files = review.parse_diff(text)
    summary = [(f['path'], f['status'], f['added'], f['removed'], f['binary']) for f in files]
    assert summary == [
        ('app/gone.py', 'deleted', 0, 2, False), ('app/new_name.py', 'added', 1, 0, False),
        ('app/old.py', 'deleted', 0, 1, False), ('img.png', 'added', 0, 0, True), ('m.py', 'modified', 3, 1, False),
    ]
    assert files[-1]['hunks'] == [(5, 1, 5, 2), (9, 0, 11, 1)]
    assert review.ranges_for(files[-1]['hunks'], 'new') == [(5, 6, False), (11, 11, True)]
    assert review.ranges_for(files[-1]['hunks'], 'old') == [(5, 5, False), (9, 9, False)]
