import os
import shutil
import stat
import subprocess

import pytest

from cortex_graph import store, watch
from cortex_graph.errors import CortexError, InvalidInput

needs_git = pytest.mark.skipif(shutil.which('git') is None, reason='git no está instalado')


def git(root, *args):
    subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)


def init_repo(root):
    git(root, 'init', '-q')
    git(root, 'config', 'user.email', 't@example.com')
    git(root, 'config', 'user.name', 't')
    git(root, 'config', 'commit.gpgsign', 'false')


def bump(path, text):
    before = os.stat(path).st_mtime_ns
    path.write_text(text, encoding='utf-8')
    os.utime(path, ns=(before + 10 ** 9, before + 10 ** 9))


def test_once_detects_changes(repo, data_dir, capsys):
    first = watch.run(str(repo), 'demo', once=True)
    assert first['version'] == 1 and not first['unchanged']
    again = watch.run(str(repo), 'demo', once=True)
    assert again['unchanged'] and again['version'] == 1
    bump(repo / 'app/utils.py', 'def slugify(text):\n    return text\n\n\ndef other():\n    return 1\n')
    third = watch.run(str(repo), 'demo', once=True)
    assert third['version'] == 2 and not third['unchanged'] and third['changes']['added'] == 1
    lines = capsys.readouterr().out.strip().split('\n')
    assert len(lines) == 3 and 'sin cambios' in lines[1] and '1 nuevos' in lines[2]
    assert [v['v'] for v in store.load_history('demo')['versions']] == [1, 2]


def test_once_reports_errors_and_rejects_urls(tmp_path, data_dir, capsys):
    (tmp_path / 'x').mkdir()
    (tmp_path / 'x' / '.cortex.toml').write_text('name = [', encoding='utf-8')
    assert watch.run(str(tmp_path / 'x'), once=True) is None
    assert 'error: .cortex.toml no es TOML válido' in capsys.readouterr().out
    with pytest.raises(InvalidInput):
        watch.run('https://github.com/a/b', once=True)


def test_snapshot_skips_noise(repo):
    (repo / '.cortexignore').write_text('app/utils.py\n', encoding='utf-8')
    (repo / 'notes.bin').write_bytes(b'\0')
    state = watch.snapshot(str(repo))
    assert 'app/services.py' in state and '.cortexignore' in state
    assert 'app/utils.py' not in state and 'notes.bin' not in state
    assert not any(k.startswith('node_modules/') for k in state)


@needs_git
def test_snapshot_respects_gitignore(repo):
    init_repo(repo)
    (repo / '.gitignore').write_text('generated/\n', encoding='utf-8')
    (repo / 'generated').mkdir()
    (repo / 'generated' / 'out.py').write_text('x = 1\n', encoding='utf-8')
    state = watch.snapshot(str(repo))
    assert 'app/services.py' in state and 'generated/out.py' not in state


def test_loop_reanalyzes_after_change(repo, data_dir, monkeypatch, capsys):
    calls = []

    def fake_sleep(seconds):
        calls.append(seconds)
        if len(calls) == 1:
            bump(repo / 'app/utils.py', 'def slugify(text):\n    return text.upper()\n')
        elif len(calls) > 3:
            raise KeyboardInterrupt

    monkeypatch.setattr(watch, 'pause', fake_sleep)
    last = watch.run(str(repo), 'demo', debounce=0)
    assert last['version'] == 2
    out = capsys.readouterr().out
    assert 'vigilando' in out and 'vigilancia detenida' in out
    assert [v['v'] for v in store.load_history('demo')['versions']] == [1, 2]


@needs_git
def test_hook_install_is_idempotent_and_preserves_content(tmp_path):
    repo = tmp_path / 'mi repo'
    repo.mkdir()
    init_repo(repo)
    hooks = repo / '.git' / 'hooks'
    hooks.mkdir(exist_ok=True)
    existing = '#!/bin/sh\necho previo\nexit 0\n'
    (hooks / 'post-merge').write_text(existing, encoding='utf-8')

    path = watch.install_hook(str(repo), 'Mi App')
    assert path == str(hooks / 'post-commit')
    commit = (hooks / 'post-commit').read_text(encoding='utf-8')
    assert commit.startswith('#!/bin/sh\n')
    assert f'cortex analyze "{repo.resolve().as_posix()}" --name "Mi-App" --quiet >/dev/null 2>&1 &' in commit
    merge = (hooks / 'post-merge').read_text(encoding='utf-8')
    assert merge.startswith('#!/bin/sh\necho previo\n# >>> cortex\n') and merge.endswith('# <<< cortex\nexit 0\n')
    for hook in watch.HOOKS:
        assert os.stat(hooks / hook).st_mode & stat.S_IXUSR

    watch.install_hook(str(repo), 'Mi App')
    assert (hooks / 'post-commit').read_text(encoding='utf-8') == commit
    assert (hooks / 'post-merge').read_text(encoding='utf-8') == merge
    watch.install_hook(str(repo), 'otro')
    assert (hooks / 'post-merge').read_text(encoding='utf-8').count('# >>> cortex') == 1
    assert '--name "otro"' in (hooks / 'post-merge').read_text(encoding='utf-8')

    removed = watch.uninstall_hook(str(repo))
    assert sorted(removed) == sorted(str(hooks / h) for h in watch.HOOKS)
    assert not (hooks / 'post-commit').exists() and not (hooks / 'post-checkout').exists()
    assert (hooks / 'post-merge').read_text(encoding='utf-8') == existing
    assert watch.uninstall_hook(str(repo)) == []


@needs_git
def test_hook_uses_hooks_path_and_default_name(tmp_path):
    repo = tmp_path / 'proyecto'
    repo.mkdir()
    init_repo(repo)
    git(repo, 'config', 'core.hooksPath', 'custom-hooks')
    (repo / '.cortex.toml').write_text('name = "desde-toml"\n', encoding='utf-8')
    path = watch.install_hook(str(repo))
    assert path == str(repo / 'custom-hooks' / 'post-commit')
    assert '--name "desde-toml"' in open(path, encoding='utf-8').read()


def test_hook_requires_git_repo(tmp_path):
    with pytest.raises(CortexError):
        watch.install_hook(str(tmp_path))


def test_shell_quoting():
    assert watch.sh_quote('a"b$c`d\\e') == '"a\\"b\\$c\\`d\\\\e"'
