import json
import os

import pytest

from conftest import by_key
from cortex_graph import pipeline, store
from cortex_graph.analyze import analyze, export_json, export_markdown
from cortex_graph.errors import InvalidInput

UTILS_V2 = """def slugify(text):
    return text.strip().lower().replace(' ', '-')


def titlecase(text):
    return text.title()
"""
UTILS_V3 = """def slugify(text):
    return text.strip().lower().replace(' ', '-')
"""


def test_data_dir_resolution(tmp_path, monkeypatch):
    monkeypatch.delenv('CORTEX_DATA', raising=False)
    monkeypatch.delenv('DATA_PATH', raising=False)
    monkeypatch.chdir(tmp_path)
    assert store.data_dir() == os.path.abspath(store.user_data_dir())
    (tmp_path / 'datos').mkdir()
    assert store.data_dir() == str(tmp_path / 'datos')
    monkeypatch.setenv('DATA_PATH', str(tmp_path / 'legacy'))
    assert store.data_dir() == str(tmp_path / 'legacy')
    monkeypatch.setenv('CORTEX_DATA', str(tmp_path / 'main'))
    assert store.data_dir() == str(tmp_path / 'main')


def save(repo, origin=None):
    graph = analyze(repo, 'demo')
    store.save_version(graph, origin or {'type': 'local', 'path': str(repo)}, {'exclude': [], 'tests': True})
    store.write_exports(graph, export_markdown, export_json)
    return graph


def test_three_versions_track_changes_and_keep_positions(repo, data_dir):
    v1 = save(repo)
    assert v1['version'] == 1 and v1['changes'] == {'added': [], 'modified': [], 'removed': []}
    assert not any('status' in n for n in v1['nodes'])

    (repo / 'app/utils.py').write_text(UTILS_V2)
    v2 = save(repo)
    assert v2['version'] == 2
    assert 'f:app/utils.py:titlecase' in v2['changes']['added']
    assert {'f:app/utils.py:slugify', 'm:app/utils.py'} <= set(v2['changes']['modified'])
    assert v2['changes']['removed'] == []
    nodes2 = by_key(v2)
    assert nodes2['f:app/utils.py:titlecase']['status'] == 'new'
    assert nodes2['f:app/utils.py:slugify']['status'] == 'changed'
    first = by_key(v1)
    for key, node in first.items():
        assert nodes2[key]['pos'] == node['pos']
    assert [c['center'] for c in v2['communities']] == [c['center'] for c in v1['communities']]

    (repo / 'app/utils.py').write_text(UTILS_V3)
    v3 = save(repo)
    assert [r['key'] for r in v3['changes']['removed']] == ['f:app/utils.py:titlecase']
    assert 'm:app/utils.py' in v3['changes']['modified'] and 'f:app/utils.py:slugify' not in v3['changes']['modified']
    unchanged = by_key(v3)['f:app/services.py:create_user']
    assert 'status' not in unchanged and unchanged['pos'] == first['f:app/services.py:create_user']['pos']

    hist = store.load_history('demo')
    assert [h['v'] for h in hist['versions']] == [1, 2, 3]
    assert hist['versions'][1]['changes'] == {'added': 1, 'modified': len(v2['changes']['modified']), 'removed': 0}
    assert store.load_version('demo', 2)['version'] == 2
    assert store.load_version('demo')['version'] == 3
    assert store.load_version('demo', 9) is None
    assert store.load_version('unknown') is None
    with pytest.raises(InvalidInput):
        store.load_version('demo', 'abc')
    folder = data_dir / 'demo'
    assert {'historial.json', 'v1.cortex.json', 'v2.cortex.json', 'v3.cortex.json', 'grafo.md', 'grafo.json'} <= set(os.listdir(folder))
    assert not [f for f in os.listdir(folder) if f.endswith('.tmp')]

    projects = store.list_projects()
    assert projects[0]['project'] == 'demo' and projects[0]['versions'] == 3 and projects[0]['last']['v'] == 3
    assert store.latest_project() == 'demo'


def test_list_projects_skips_corrupt_history(data_dir, repo):
    save(repo)
    broken = data_dir / 'broken'
    broken.mkdir()
    (broken / 'historial.json').write_text('{nope')
    assert [p['project'] for p in store.list_projects()] == ['demo']


def test_import_export_round_trip(repo, data_dir):
    original = pipeline.analyze_source(str(repo), 'demo')
    exported = json.loads(json.dumps(store.load_version('demo')))
    exported['project'] = 'copia'
    imported = store.validate_graph(exported)
    store.save_version(imported, {'type': 'import'})
    loaded = store.load_version('copia')
    assert loaded['version'] == 1 and loaded['project'] == 'copia'
    assert loaded['nodes'] == original['nodes'] and loaded['edges'] == original['edges'] and loaded['visible'] == original['visible']
    assert store.load_history('copia')['origin'] == {'type': 'import'}


@pytest.mark.parametrize('mutate', [
    lambda g: g.update(format='otro'),
    lambda g: g.update(nodes=[]),
    lambda g: g['nodes'][0].update(id=99),
    lambda g: g['nodes'][0].update(c=50),
    lambda g: g['nodes'][1].update(kind='planet'),
    lambda g: g['edges'].append({'a': 0, 'b': 10 ** 6, 'kind': 'call', 'w': 1}),
    lambda g: g['visible'].append({'a': 'x', 'b': 0, 'kind': 'call', 'w': 1}),
    lambda g: g['communities'][0].update(center=[0, 0]),
])
def test_validate_graph_rejects_malformed(repo, data_dir, mutate):
    pipeline.analyze_source(str(repo), 'demo')
    graph = store.load_version('demo')
    mutate(graph)
    with pytest.raises(InvalidInput):
        store.validate_graph(graph)


def test_slug_and_parse_version():
    assert store.slug('../../etc') == 'etc'
    assert store.slug('..') == 'proyecto'
    assert store.slug('Mi Proyecto!') == 'Mi-Proyecto'
    assert store.parse_version('v3') == 3 and store.parse_version(None) is None
    for bad in ('0', 'x', True, -2):
        with pytest.raises(InvalidInput):
            store.parse_version(bad)


def test_unchanged_source_skips_analysis(repo, data_dir, monkeypatch):
    real = pipeline.analyze
    first = pipeline.analyze_source(str(repo), 'demo')
    assert first['version'] == 1 and first['unchanged'] is False
    assert {'fingerprint', 'analyze', 'save', 'total'} <= set(first['stats']['timings'])
    fingerprint = store.load_history('demo')['versions'][0]['options']['fingerprint']
    assert len(fingerprint) == 64

    def boom(*args, **kwargs):
        raise AssertionError('no debería analizar')

    monkeypatch.setattr(pipeline, 'analyze', boom)
    again = pipeline.analyze_source(str(repo), 'demo')
    assert again['unchanged'] is True and again['version'] == 1 and again['nodes'] == first['nodes']
    assert isinstance(again['stats']['seconds'], float)
    result = pipeline.summary(again)
    assert result['unchanged'] and result['changes'] == {'added': 0, 'modified': 0, 'removed': 0}
    assert len(store.load_history('demo')['versions']) == 1
    assert sorted(os.listdir(data_dir / 'demo')) == sorted(['.lock', 'historial.json', 'v1.cortex.json', 'grafo.md', 'grafo.json'])

    before = os.stat(repo / 'app/utils.py').st_mtime_ns
    (repo / 'app/utils.py').write_text(UTILS_V2)
    os.utime(repo / 'app/utils.py', ns=(before + 10 ** 9, before + 10 ** 9))
    seen = {}

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(pipeline, 'analyze', spy)
    third = pipeline.analyze_source(str(repo), 'demo')
    assert third['version'] == 2 and not third['unchanged'] and seen['previous']['version'] == 1
    assert 'f:app/utils.py:titlecase' in third['changes']['added']


def test_fingerprint_tracks_options_and_files(repo):
    base = pipeline.fingerprint(repo)
    assert pipeline.fingerprint(repo) == base
    assert pipeline.fingerprint(repo, include_tests=True) != base
    assert pipeline.fingerprint(repo, exclude=['docs']) != base
    (repo / 'notes.unknownext').write_text('x')
    assert pipeline.fingerprint(repo) == base
    (repo / 'app/new.py').write_text('x = 1\n')
    added = pipeline.fingerprint(repo)
    assert added != base
    (repo / '.cortexignore').write_text('app/new.py\n')
    assert pipeline.fingerprint(repo) not in (base, added)
    (repo / 'app/new.py').unlink()
    (repo / '.cortexignore').unlink()
    assert pipeline.fingerprint(repo) == base
    assert pipeline.fingerprint(repo, commit={'sha': 'abc'}) != base


def test_config_defaults_for_name_tests_and_git(repo, data_dir, monkeypatch):
    (repo / '.cortex.toml').write_text('name = "desde-config"\ninclude_tests = true\ngit = false\n', encoding='utf-8')
    seen = {}
    real = pipeline.analyze

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(pipeline, 'analyze', spy)
    graph = pipeline.analyze_source(str(repo))
    assert graph['project'] == 'desde-config' and seen['git'] is False and seen['skip_tests'] is False
    assert store.load_history('desde-config')['versions'][0]['options']['tests'] is True
    pipeline.analyze_source(str(repo), 'otro', include_tests=False)
    assert seen['skip_tests'] is True


def test_imported_folder_is_copied_and_survives_its_origin(tmp_path, data_dir):
    import shutil
    from cortex_graph.errors import NotFound
    notes = tmp_path / 'notas'
    notes.mkdir()
    (notes / 'viaje.md').write_text('# Viaje\n\nQuiero ir a Kioto con [[Ana]].\n', encoding='utf-8')
    graph = pipeline.analyze_source(str(notes), 'cerebro', copy=True)
    assert store.load_history('cerebro')['origin'] == {'type': 'import', 'path': str(notes)}
    assert os.path.isfile(os.path.join(store.source_dir('cerebro'), 'viaje.md'))
    shutil.rmtree(notes)
    again = pipeline.rebuild('cerebro')
    assert {n['key'] for n in again['nodes']} == {n['key'] for n in graph['nodes']}
    local = tmp_path / 'local'
    local.mkdir()
    (local / 'a.md').write_text('# A\n', encoding='utf-8')
    pipeline.analyze_source(str(local), 'suelto')
    shutil.rmtree(local)
    with pytest.raises(NotFound):
        pipeline.rebuild('suelto')
