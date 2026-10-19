import pytest

from cortex_graph import contextfiles, pipeline
from cortex_graph.contextfiles import END, START
from cortex_graph.errors import InvalidInput, NotFound


@pytest.fixture
def project(repo, data_dir):
    pipeline.analyze_source(str(repo), 'demo', include_tests=True)
    return repo


def paths(result):
    return {f['target']: f['path'] for f in result['files']}


def test_generates_every_target_in_repo_root(project):
    result = contextfiles.generate()
    assert result['project'] == 'demo' and result['root'] == str(project)
    assert [f['target'] for f in result['files']] == ['agents', 'claude', 'llms', 'cursor', 'copilot']
    expected = {'agents': 'AGENTS.md', 'claude': 'CLAUDE.md', 'llms': 'llms.txt', 'cursor': '.cursor/rules/cortex.mdc',
                'copilot': '.github/copilot-instructions.md'}
    for target, rel in expected.items():
        path = project / rel
        assert str(path) == paths(result)[target] and path.is_file()
        text = path.read_text(encoding='utf-8')
        assert text.count('\n') <= 150
        assert 'Cómo consultar este repo con Córtex' in text
        assert '`impact_analysis`' in text and '`cortex impact <ref>`' in text
        assert '`app/services.py`' in text and '`GET /users` → `list_users` · app/api.py:8' in text
    for f in result['files']:
        assert f['changed'] and f['bytes'] > 0 and f['lines'] > 10


def test_content_is_well_formed(project):
    contextfiles.generate()
    agents = (project / 'AGENTS.md').read_text(encoding='utf-8')
    assert agents.startswith(START + '\n## Córtex: mapa de «demo»') and agents.endswith(END + '\n')
    assert '**Lenguajes:** Python' in agents and '### Subsistemas (comunidades)' in agents
    critical = agents.split('### Archivos ')[1].split('###')[0]
    assert '`app/models.py`' in critical and '`web/tsconfig.json`' not in critical
    assert '… y -' not in agents and '1 subsistemas' not in agents and '`cortex community <número o nombre>`' in agents
    for line in agents.splitlines():
        if line.startswith('| '):
            assert line.count('|') == 4, line
    cursor = (project / '.cursor/rules/cortex.mdc').read_text(encoding='utf-8')
    assert cursor.startswith('---\ndescription: ') and 'alwaysApply: true\n---\n\n# Córtex' in cursor and START not in cursor
    llms = (project / 'llms.txt').read_text(encoding='utf-8')
    assert llms.startswith(START + '\n# demo\n\n> Repositorio de 14 archivos')


def test_preserves_user_content_and_is_idempotent(project):
    agents = project / 'AGENTS.md'
    agents.write_text('# Guía del equipo\n\nNo toques la carpeta legacy.\n', encoding='utf-8')
    copilot = project / '.github' / 'copilot-instructions.md'
    copilot.parent.mkdir()
    copilot.write_text(f'Intro propia.\n\n{START}\nviejo contenido\n{END}\n\n## Al final\n\nNotas finales.\n', encoding='utf-8')
    contextfiles.generate(targets=['agents', 'copilot'])
    text = agents.read_text(encoding='utf-8')
    assert text.startswith('# Guía del equipo\n\nNo toques la carpeta legacy.\n\n' + START)
    assert text.count(START) == 1 and text.count(END) == 1
    other = copilot.read_text(encoding='utf-8')
    assert other.startswith('Intro propia.\n\n' + START) and 'viejo contenido' not in other
    assert other.endswith(END + '\n\n## Al final\n\nNotas finales.\n') and other.count(START) == 1
    before = {p: open(p, encoding='utf-8').read() for p in (agents, copilot)}
    again = contextfiles.generate(targets='agents,copilot')
    assert [f['changed'] for f in again['files']] == [False, False]
    assert before == {p: open(p, encoding='utf-8').read() for p in (agents, copilot)}


def test_dry_run_and_out_dir(project, tmp_path):
    result = contextfiles.generate('demo', ['claude'], write=False)
    assert not (project / 'CLAUDE.md').exists() and result['written'] is False
    assert result['files'][0]['content'].startswith(START)
    out = tmp_path / 'salida'
    out.mkdir()
    written = contextfiles.generate(targets=('llms',), out_dir=str(out))
    assert written['root'] == str(out) and (out / 'llms.txt').is_file() and not (project / 'llms.txt').exists()


def test_errors(project, tmp_path):
    with pytest.raises(InvalidInput):
        contextfiles.generate(targets=['readme'])
    with pytest.raises(NotFound):
        contextfiles.generate(out_dir=str(tmp_path / 'no-existe'))
    with pytest.raises(NotFound):
        contextfiles.generate('otro')
