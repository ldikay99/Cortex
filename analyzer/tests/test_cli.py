import json
import os
import subprocess
import sys


def run(args, data, cwd, extra_env=None):
    env = {**os.environ, 'CORTEX_DATA': str(data), **(extra_env or {})}
    return subprocess.run([sys.executable, '-m', 'cortex_graph', *args], capture_output=True, text=True, cwd=cwd, env=env, timeout=180)


def test_cli_end_to_end(repo, tmp_path):
    data = tmp_path / 'store'
    res = run(['analyze', str(repo), '--name', 'demo', '--exclude', 'docs/guide.md', '--json'], data, tmp_path)
    assert res.returncode == 0, res.stderr
    summary = json.loads(res.stdout)
    assert summary['project'] == 'demo' and summary['version'] == 1 and summary['stats']['files'] == 10

    res = run(['analyze', str(repo), '--name', 'demo', '--tests'], data, tmp_path)
    assert res.returncode == 0 and 'demo v2:' in res.stdout and 'cambios:' in res.stdout

    res = run(['projects'], data, tmp_path)
    assert res.returncode == 0 and res.stdout.startswith('demo · 2 versiones')
    projects = json.loads(run(['projects', '--json'], data, tmp_path).stdout)['projects']
    assert projects[0]['last']['options'] == {'exclude': [], 'tests': True}

    res = run(['overview', 'demo'], data, tmp_path)
    assert res.returncode == 0 and 'comunidades:' in res.stdout and 'GET /users' in res.stdout

    found = json.loads(run(['search', 'slugify', '--project', 'demo', '--kind', 'function', '--limit', '5', '--json'], data, tmp_path).stdout)
    assert found['results'][0]['key'] == 'f:app/utils.py:slugify'
    res = run(['search', 'create_user'], data, tmp_path)
    assert 'función create_user · app/services.py:' in res.stdout

    assert 'lo llaman' in run(['node', 'create_user'], data, tmp_path).stdout
    assert 'símbolos' in run(['file', 'app/services.py'], data, tmp_path).stdout
    assert 'comunidad 0' in run(['community', '0'], data, tmp_path).stdout
    assert 'camino de 2 pasos' in run(['path', 'list_users', 'slugify'], data, tmp_path).stdout
    impact = json.loads(run(['impact', 'slugify', '--depth', '2', '--json'], data, tmp_path).stdout)
    assert impact['depth'] == 2 and impact['levels'][0]['distance'] == 1
    changes = json.loads(run(['changes', '--project', 'demo', '--since', '1', '--json'], data, tmp_path).stdout)
    assert changes['from_version'] == 1 and changes['to_version'] == 2
    assert 'guide.md' in [n['name'] for n in changes['added']]

    res = run(['export', '--format', 'md'], data, tmp_path)
    assert res.stdout.startswith('# Grafo de conocimiento · demo')
    out = tmp_path / 'demo.cortex.json'
    res = run(['export', '--project', 'demo', '--format', 'cortex', '-o', str(out)], data, tmp_path)
    assert res.returncode == 0 and json.loads(out.read_text())['format'] == 'cortex-grafo/1'
    assert json.loads(run(['export', '-f', 'json'], data, tmp_path).stdout)['project'] == 'demo'


def test_cli_errors_are_clear(tmp_path, repo):
    data = tmp_path / 'store'
    res = run(['overview'], data, tmp_path)
    assert res.returncode != 0 and 'error: todavía no hay proyectos' in res.stderr and 'Traceback' not in res.stderr
    res = run(['analyze', str(tmp_path / 'nope')], data, tmp_path)
    assert res.returncode != 0 and 'no existe la carpeta' in res.stderr and 'Traceback' not in res.stderr
    res = run(['analyze', 'https://gitlab.com/a/b'], data, tmp_path)
    assert res.returncode != 0 and 'github.com' in res.stderr
    run(['analyze', str(repo), '--name', 'demo'], data, tmp_path)
    res = run(['node', 'zzz-nothing'], data, tmp_path)
    assert res.returncode != 0 and 'no encontré' in res.stderr and 'Traceback' not in res.stderr
    res = run(['changes', '--since', 'abc'], data, tmp_path)
    assert res.returncode != 0 and 'entero' in res.stderr
    res = run(['search', 'x', '--kind', 'planet'], data, tmp_path)
    assert res.returncode == 2
    res = run(['export', '--format', 'md', '-o', str(tmp_path / 'missing-dir' / 'x.md')], data, tmp_path)
    assert res.returncode != 0 and 'no se pudo escribir' in res.stderr


def test_default_data_dir_is_cwd_datos(repo, tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ('CORTEX_DATA', 'DATA_PATH')}
    work = tmp_path / 'work'
    work.mkdir()
    res = subprocess.run([sys.executable, '-m', 'cortex_graph', 'analyze', str(repo), '--json'], capture_output=True, text=True,
                         cwd=work, env=env, timeout=180)
    assert res.returncode == 0, res.stderr
    assert (work / 'datos' / 'demo' / 'historial.json').is_file()
