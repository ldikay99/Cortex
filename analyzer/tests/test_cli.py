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
    assert summary['project'] == 'demo' and summary['version'] == 1 and summary['stats']['files'] == 11

    res = run(['analyze', str(repo), '--name', 'demo', '--tests'], data, tmp_path)
    assert res.returncode == 0 and 'demo v2:' in res.stdout and 'cambios:' in res.stdout

    res = run(['projects'], data, tmp_path)
    assert res.returncode == 0 and res.stdout.startswith('demo · 2 versiones')
    projects = json.loads(run(['projects', '--json'], data, tmp_path).stdout)['projects']
    assert {k: projects[0]['last']['options'][k] for k in ('exclude', 'tests')} == {'exclude': [], 'tests': True}

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
    res = run(['analyze', str(repo), '--scip', str(tmp_path / 'missing.scip')], data, tmp_path)
    assert res.returncode == 3 and 'SCIP' in res.stderr
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


def test_default_data_dir(repo, tmp_path):
    home = tmp_path / 'home'
    env = {k: v for k, v in os.environ.items() if k not in ('CORTEX_DATA', 'DATA_PATH')}
    env.update(HOME=str(home), USERPROFILE=str(home), XDG_DATA_HOME=str(home / 'share'), LOCALAPPDATA=str(home / 'local'))
    work = tmp_path / 'work'
    (work / 'datos').mkdir(parents=True)
    res = subprocess.run([sys.executable, '-m', 'cortex_graph', 'analyze', str(repo), '--json'], capture_output=True, text=True,
                         cwd=work, env=env, timeout=180)
    assert res.returncode == 0, res.stderr
    assert (work / 'datos' / 'demo' / 'historial.json').is_file()
    other = tmp_path / 'other'
    other.mkdir()
    res = subprocess.run([sys.executable, '-m', 'cortex_graph', 'analyze', str(repo), '--quiet'], capture_output=True, text=True,
                         cwd=other, env=env, timeout=180)
    assert res.returncode == 0 and res.stdout == '', res.stderr
    assert not (other / 'datos').exists()
    assert [p.parent.name for p in home.rglob('historial.json')] == ['demo']


def test_cli_new_commands(repo, tmp_path):
    data = tmp_path / 'store'
    assert run(['analyze', str(repo), '--name', 'demo', '--tests', '--quiet'], data, tmp_path).stdout == ''
    again = run(['analyze', str(repo), '--name', 'demo', '--tests'], data, tmp_path)
    assert again.returncode == 0 and 'demo v' in again.stdout

    res = run(['read', 'create_user', '-C', '1'], data, tmp_path)
    assert res.returncode == 0 and 'función create_user · app/services.py:' in res.stdout and '│ def create_user(name):' in res.stdout
    code = json.loads(run(['read', 'slugify', '--json'], data, tmp_path).stdout)
    assert code['code'].startswith('def slugify(text):')

    res = run(['context', 'how is a user created', '--budget', '1500'], data, tmp_path)
    assert res.returncode == 0 and res.stdout.startswith('# Contexto · demo') and 'def create_user' in res.stdout
    assert 'tokens' in res.stderr
    ctx = json.loads(run(['context', 'create user', '--json', '-b', '800'], data, tmp_path).stdout)
    assert ctx['tokens_used'] <= 800 and ctx['items'][0]['name'] == 'create_user'

    res = run(['architecture'], data, tmp_path)
    assert res.returncode == 0 and 'arquitectura' in res.stdout and 'GET /users' in res.stdout
    arch = json.loads(run(['architecture', '--section', 'hotspots', '--limit', '2', '--json'], data, tmp_path).stdout)
    assert arch['hotspots']['limit'] == 2 and 'cycles' not in arch
    assert run(['architecture', '--section', 'planets'], data, tmp_path).returncode == 2

    assert 'packages' in json.loads(run(['deps', '--json'], data, tmp_path).stdout)
    assert run(['deps', 'nothing-like-this'], data, tmp_path).returncode == 3
    res = run(['endpoints'], data, tmp_path)
    assert res.returncode == 0 and 'GET /users → función list_users' in res.stdout
    assert json.loads(run(['endpoints', '--method', 'POST', '--json'], data, tmp_path).stdout)['endpoints']['total'] == 0
    assert run(['vars'], data, tmp_path).returncode == 0
    page = json.loads(run(['search', 'user', '--limit', '1', '--offset', '1', '--json'], data, tmp_path).stdout)
    assert page['offset'] == 1 and len(page['results']) == 1 and 'score' in page['results'][0]


def test_cli_integrations(repo, tmp_path):
    data = tmp_path / 'store'
    run(['analyze', str(repo), '--name', 'demo', '--tests'], data, tmp_path)
    diff = tmp_path / 'change.diff'
    diff.write_text('diff --git a/app/utils.py b/app/utils.py\n--- a/app/utils.py\n+++ b/app/utils.py\n'
                    '@@ -1,2 +1,2 @@\n def slugify(text):\n-    return text.lower().replace(\' \', \'-\')\n+    return text.lower()\n',
                    encoding='utf-8')
    res = run(['review', '--diff-file', str(diff), '--json'], data, tmp_path)
    if 'no está disponible' not in res.stderr:
        assert res.returncode == 0, res.stderr
        review = json.loads(res.stdout)
        assert 'slugify' in [s['name'] for s in review['symbols']]
        assert 'riesgo' in run(['review', '--diff-file', str(diff)], data, tmp_path).stdout
    assert run(['review', '--diff-file', str(tmp_path / 'missing.diff')], data, tmp_path).returncode == 1
    assert run(['review', '--head', 'X', '--worktree'], data, tmp_path).returncode == 2

    snippet = run(['mcp-config', 'claude-code', '--mode', 'local', '--json'], data, tmp_path)
    if snippet.returncode == 0:
        assert json.loads(snippet.stdout)['client'] == 'claude-code'
        assert 'cortex' in run(['mcp-config', '--client', 'cursor'], data, tmp_path).stdout
        assert len(json.loads(run(['mcp-config', '--json'], data, tmp_path).stdout)['clients']) >= 5
        project_root = tmp_path / 'proj'
        project_root.mkdir()
        res = run(['mcp-config', 'claude-code', '--mode', 'local', '--install', '--root', str(project_root)], data, tmp_path)
        assert res.returncode == 0 and (project_root / '.mcp.json').is_file()
        assert run(['mcp-config', 'nope'], data, tmp_path).returncode == 1

    out = tmp_path / 'ctxfiles'
    out.mkdir()
    res = run(['context-files', '--out', str(out), '--targets', 'agents', 'llms', '--json'], data, tmp_path)
    if res.returncode == 0:
        written = json.loads(res.stdout)
        assert {f['target'] for f in written['files']} == {'agents', 'llms'} and (out / 'AGENTS.md').is_file()
        dry = json.loads(run(['context-files', '--out', str(out), '--dry-run', '--json'], data, tmp_path).stdout)
        assert dry['written'] is False

    git_repo = tmp_path / 'gitrepo'
    git_repo.mkdir()
    if subprocess.run(['git', 'init', '-q', str(git_repo)], capture_output=True).returncode == 0:
        res = run(['hook', 'install', str(git_repo), '--name', 'demo', '--json'], data, tmp_path)
        assert res.returncode == 0, res.stderr
        installed = json.loads(res.stdout)['paths']
        assert installed and os.path.isfile(installed[0])
        res = run(['hook', 'uninstall', str(git_repo)], data, tmp_path)
        assert res.returncode == 0 and 'ganchos quitados' in res.stdout
        assert 'no había' in run(['hook', 'uninstall', str(git_repo)], data, tmp_path).stdout

    res = run(['watch', str(repo), '--name', 'demo', '--once', '--tests'], data, tmp_path)
    assert res.returncode == 0, res.stderr


def test_cli_memory_commands(tmp_path):
    data = tmp_path / 'store'
    home = tmp_path / 'home'
    env = {'HOME': str(home), 'USERPROFILE': str(home), 'ANTHROPIC_API_KEY': '', 'ANTHROPIC_AUTH_TOKEN': '',
           'ANTHROPIC_CONFIG_DIR': str(home / 'none')}
    res = run(['remember', 'Vivo en Sevilla', '--cuando', '2023-01-05'], data, tmp_path, env)
    assert res.returncode == 0, res.stderr
    assert res.stdout.startswith('guardado: Vivo en Sevilla')
    saved = json.loads(run(['remember', 'Vivo en Madrid', '--categoria', 'identidad', '--sobre', 'Madrid', '--json'], data, tmp_path, env).stdout)
    assert saved['status'] in ('new', 'updated') and saved['memory']['category'] == 'identity' and saved['project'] == 'memoria'
    assert 'ya lo sabía' in run(['remember', 'vivo en madrid'], data, tmp_path, env).stdout
    res = run(['recall', '¿dónde vivo?'], data, tmp_path, env)
    assert res.returncode == 0 and '# Memoria · memoria' in res.stdout and 'Vivo en Madrid' in res.stdout and 'tokens)' in res.stderr
    recalled = json.loads(run(['recall', 'where do I live', '--budget', '300', '--json'], data, tmp_path, env).stdout)
    assert recalled['items'][0]['id'] == saved['id'] and recalled['tokens'] <= 300
    hinted = json.loads(run(['recall', 'mi ciudad', '--pistas', 'Madrid', 'vivo', '--json'], data, tmp_path, env).stdout)
    assert hinted['hints'] == ['Madrid', 'vivo'] and hinted['items'][0]['id'] == saved['id']
    assert '## Quién es' in run(['profile'], data, tmp_path, env).stdout
    assert 'sections' in json.loads(run(['profile', '--json'], data, tmp_path, env).stdout)
    res = run(['timeline', '--desde', '2023-01-01', '--sobre', 'madrid'], data, tmp_path, env)
    assert res.returncode == 0 and 'Vive en Madrid' in res.stdout and 'Sevilla' not in res.stdout
    res = run(['forget', saved['id']], data, tmp_path, env)
    assert res.returncode == 0 and f"olvidado: r:{saved['id']}" in res.stdout
    res = run(['forget', 'algo que nunca dije'], data, tmp_path, env)
    assert res.returncode == 3 and 'no encontré' in res.stderr
    res = run(['remember', 'x', '--categoria', 'planeta'], data, tmp_path, env)
    assert res.returncode == 2
    notes = tmp_path / 'notas'
    notes.mkdir()
    (notes / 'diario.md').write_text('# Diario\n\nHoy hablé con Ana sobre el viaje a Kioto.\n', encoding='utf-8')
    res = run(['import', str(notes), '--name', 'diario'], data, tmp_path, env)
    assert res.returncode == 0, res.stderr
    assert 'nada sale de tu equipo' in res.stderr and 'diario v1:' in res.stdout and 'recuerdos vigentes' in res.stdout
    res = run(['import', str(notes), '--name', 'diario', '--batch'], data, tmp_path, env)
    assert res.returncode == 1 and '--ai' in res.stderr
    res = run(['import', str(notes), '--name', 'diario', '--ai'], data, tmp_path, env)
    assert res.returncode == 1 and 'envía tus conversaciones a la nube' in res.stderr and 'no se puede usar la extracción con IA' in res.stderr
    assert 'Traceback' not in res.stderr
