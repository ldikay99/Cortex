import json
import os
import shutil
import subprocess

import pytest

from conftest import by_key, edge_set, write_repo
from cortex_graph import gitinfo
from cortex_graph.analyze import analyze

pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='git no está instalado')


def git_env(date, who):
    return {**os.environ, 'GIT_AUTHOR_DATE': date, 'GIT_COMMITTER_DATE': date, 'GIT_AUTHOR_NAME': who,
            'GIT_AUTHOR_EMAIL': f'{who}@example.org', 'GIT_COMMITTER_NAME': who, 'GIT_COMMITTER_EMAIL': f'{who}@example.org',
            'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1'}


def run(root, *args, date='2024-01-01T10:00:00', who='ana'):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True, env=git_env(date, who)).stdout


def touch(root, rel, line):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((path.read_text() if path.exists() else '') + line + '\n', encoding='utf-8')


@pytest.fixture
def history(repo):
    run(repo, 'init', '-q', '-b', 'main')
    run(repo, 'add', '-A')
    run(repo, 'commit', '-q', '-m', 'init')
    for i, who in enumerate(('bob', 'ana', 'eva')):
        touch(repo, 'app/services.py', f'# {i}')
        touch(repo, 'app/utils.py', f'# {i}')
        run(repo, 'commit', '-qam', f'c{i}', date=f'2024-02-0{i + 1}T10:00:00', who=who)
    touch(repo, 'app/models.py', '# m')
    touch(repo, 'app/base.py', '# b')
    run(repo, 'commit', '-qam', 'pair once', date='2024-03-01T10:00:00')
    for i in range(31):
        touch(repo, f'gen/f{i:02}.py', 'X = 1')
    touch(repo, 'app/services.py', '# big')
    touch(repo, 'app/utils.py', '# big')
    run(repo, 'add', '-A')
    run(repo, 'commit', '-qm', 'big', date='2024-04-01T10:00:00', who='bob')
    return repo


def test_collect_outside_git(tmp_path):
    root = write_repo(tmp_path / 'plain', {'a.py': 'x = 1\n'})
    assert gitinfo.collect(root, ['a.py']) is None
    assert gitinfo.collect(root, []) is None


def test_collect_churn_last_authors_and_cochange(history):
    files = ['app/services.py', 'app/utils.py', 'app/models.py', 'app/base.py', 'app/api.py', 'missing.py']
    info = gitinfo.collect(history, files)
    stats = info['files']
    assert stats['app/services.py'] == {'churn': 5, 'last': '2024-04-01', 'authors': 3}
    assert stats['app/utils.py'] == {'churn': 5, 'last': '2024-04-01', 'authors': 3}
    assert stats['app/models.py'] == {'churn': 2, 'last': '2024-03-01', 'authors': 1}
    assert stats['app/api.py'] == {'churn': 1, 'last': '2024-01-01', 'authors': 1}
    assert 'missing.py' not in stats and 'gen/f00.py' not in stats
    assert info['cochange'] == [('app/services.py', 'app/utils.py', 4)]
    assert info['commits'] == 6 and info['shallow'] is False
    assert '@' not in json.dumps(info) and 'bob' not in json.dumps(info)
    assert gitinfo.collect(history, files) == info


def test_collect_from_subfolder(history):
    info = gitinfo.collect(history / 'app', ['services.py', 'utils.py', 'models.py'])
    assert info['files']['services.py']['churn'] == 5
    assert info['cochange'] == [('services.py', 'utils.py', 4)]
    assert info['commits'] == 6


def test_analyze_applies_git_metadata(history):
    graph = analyze(history, 'demo')
    nodes = by_key(graph)
    assert nodes['m:app/services.py']['churn'] == 5
    assert nodes['m:app/services.py']['last'] == '2024-04-01'
    assert nodes['m:app/services.py']['authors'] == 3
    assert ('m:app/services.py', 'm:app/utils.py', 'cochange') in edge_set(graph)
    weights = {e['w'] for e in graph['edges'] if e['kind'] == 'cochange'}
    assert weights == {4}
    assert 'churn' not in by_key(analyze(history, 'demo', git=False))['m:app/services.py']


def test_parse_log_handles_quoted_paths_prefix_and_shallow_boundary():
    text = ('\0aaa\x1f2024-01-02\x1fAna@X.org\x1fbbb\n\nsrc/a.py\n"src/\\303\\261.py"\nother/b.py\n'
            '\0bbb\x1f2024-01-01\x1fana@x.org\x1f\n\nsrc/a.py\n')
    assert gitinfo.parse_log(text, 'src/') == [('2024-01-02', 'ana@x.org', ['a.py', 'ñ.py'], 3), ('2024-01-01', 'ana@x.org', ['a.py'], 1)]
    assert gitinfo.parse_log(text, 'src/', shallow=True) == [('2024-01-02', 'ana@x.org', ['a.py', 'ñ.py'], 3)]


def test_summarize_caps_pairs_deterministically(monkeypatch):
    monkeypatch.setattr(gitinfo, 'MAX_PAIRS', 2)
    commits = [('2024-01-01', 'a', ['x', 'y', 'z'], 3)] * 3 + [('2024-01-02', 'b', ['x', 'y'], 2), ('2024-01-03', 'c', ['x', 'y'], 40)]
    info = gitinfo.summarize(commits, ['x', 'y', 'z'])
    assert info['cochange'] == [('x', 'y', 4), ('x', 'z', 3)]
    assert info['files']['x'] == {'churn': 5, 'last': '2024-01-03', 'authors': 3}
