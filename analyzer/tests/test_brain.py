import json
import os
import sys
import threading
import types

import pytest

import cortex_graph
from cortex_graph import brain, store
from cortex_graph.common import Graph
from cortex_graph.errors import CortexError, InvalidInput, NotFound

TOKEN = 'gh' + 'p_' + 'Z9y8X7w6' * 5
REAL_FACTS = brain.external_facts


@pytest.fixture(autouse=True)
def isolated(data_dir, monkeypatch):
    monkeypatch.setattr(brain, 'external_facts', lambda text, now: {})
    from cortex_graph import pipeline
    calls = []
    monkeypatch.setattr(pipeline, 'rebuild', lambda project, include_tests=None: calls.append(project), raising=False)
    return calls


def read_log(project='memoria'):
    with open(brain.log_path(project), encoding='utf-8') as f:
        return f.read()


def test_remember_dedup_supersede_and_history(isolated, data_dir):
    first = brain.remember('Vivo en Sevilla', now='2023-01-05')
    assert first['status'] == 'new' and first['project'] == 'memoria' and first['graph'] == 'actualizado'
    assert first['id'] == brain.memory_id('vivo en  SEVILLA!') and len(first['id']) == 12
    m = first['memory']
    assert (m['category'], m['subject'], m['attribute'], m['value']) == ('identity', 'user', 'lives_in', 'Sevilla')
    second = brain.remember('Ahora vivo en Madrid', now='2025-03-01T10:00:00')
    assert second['status'] == 'updated' and second['superseded'] == [first['id']]
    again = brain.remember('ahora vivo en madrid.', now='2025-03-02')
    assert again['status'] == 'duplicate' and again['id'] == second['id'] and again['graph'] == 'sin cambios'
    current = brain.memories()
    assert [r['text'] for r in current] == ['Ahora vivo en Madrid']
    history = brain.memories(include_inactive=True)
    old = next(r for r in history if r['id'] == first['id'])
    assert old['valid_to'] == '2025-03-01T10:00:00' and old['superseded_by'] == second['id']
    assert history[0]['supersedes'] == [first['id']]
    assert isolated == ['memoria', 'memoria']
    assert (data_dir / 'memoria' / brain.LOG).is_file()
    assert json.loads((data_dir / 'memoria' / 'historial.json').read_text())['origin'] == {'type': 'brain'}
    ops = [json.loads(line) for line in read_log().splitlines()]
    assert [op['op'] for op in ops] == ['add', 'update', 'add']


def test_out_of_order_facts_become_history():
    madrid = brain.remember('Vivo en Madrid', now='2025-06-01', when='2025-01-10')
    seville = brain.remember('Vivo en Sevilla', now='2025-06-02', when='2022-04-01')
    assert seville['status'] == 'new' and seville['memory']['valid_to'] == '2025-01-10'
    assert [r['id'] for r in brain.memories()] == [madrid['id']]
    stored = {r['id']: r for r in brain.memories(include_inactive=True)}
    assert stored[madrid['id']]['supersedes'] == [seville['id']] and stored[madrid['id']]['valid_to'] is None


def test_restating_an_old_fact_reactivates_it():
    a = brain.remember('Vivo en Madrid', now='2020-01-01')
    brain.remember('Vivo en Lisboa', now='2022-01-01')
    back = brain.remember('Vivo en Madrid', now='2024-01-01')
    assert back['status'] == 'updated' and back['id'] != a['id']
    assert [r['text'] for r in brain.memories()] == ['Vivo en Madrid']
    assert len(brain.memories(include_inactive=True)) == 3


def test_multi_valued_facts_coexist_and_explicit_fields_win():
    brain.remember('Me gusta el café', now='2025-01-01')
    tea = brain.remember('Me gusta el té', now='2025-01-02')
    assert tea['status'] == 'new' and tea['superseded'] == []
    assert len(brain.memories()) == 2
    custom = brain.remember('El editor que uso es Helix', category='preferencia', subject='user', attribute='editor', value='Helix',
                            about=['Helix'], now='2025-02-01')
    assert custom['memory']['category'] == 'preference' and custom['memory']['about'] == ['Helix']
    swap = brain.remember('El editor que uso es Zed', category='preference', attribute='editor', value='Zed', now='2025-03-01')
    assert swap['superseded'] == [custom['id']]
    with pytest.raises(InvalidInput, match='categoría'):
        brain.remember('algo', category='planeta')
    with pytest.raises(InvalidInput, match='vacío'):
        brain.remember('   ')
    with pytest.raises(InvalidInput, match='fecha'):
        brain.remember('Fui a Roma', when='ayer')


def test_secrets_are_never_stored_in_clear():
    r = brain.remember(f'Mi token de GitHub es {TOKEN}', now='2025-01-01')
    assert r['memory']['sensitive'] is True and TOKEN not in r['memory']['text'] and '«redactado»' in r['memory']['text']
    assert TOKEN not in read_log()
    flagged = brain.remember('Tengo una cita médica el lunes', sensitive=True, now='2025-01-01')
    assert flagged['memory']['sensitive'] is True


def test_forget_by_id_and_text_erases_and_blocks_reimport(isolated):
    keep = brain.remember('Me gusta el jazz', now='2025-01-01')
    gone = brain.remember('Mi película favorita es Alien', now='2025-01-01')
    assert brain.forget(f"r:{gone['id']}")['forgotten'] == [gone['id']]
    assert 'Alien' not in read_log() and gone['id'] in brain.forgotten()
    again = brain.remember_many([{'text': 'Mi película favorita es Alien', 'origin': 'rule', 'confidence': 0.6}], rebuild=False)
    assert again['counts'] == {'forgotten': 1} and again['graph'] == 'sin cambios'
    assert brain.forget('me gusta el jazz.')['forgotten'] == [keep['id']]
    assert brain.memories() == []
    with pytest.raises(NotFound):
        brain.forget('algo que nunca dije')
    manual = brain.remember('Mi película favorita es Alien', now='2025-02-01')
    assert manual['status'] == 'new' and brain.memories()[0]['id'] == gone['id']
    result = brain.forget_and_refresh(gone['id'], rebuild=True)
    assert result['graph'] == 'actualizado' and isolated[-1] == 'memoria'


def test_background_rebuild_is_coalesced(monkeypatch):
    from cortex_graph import pipeline
    started, release = threading.Event(), threading.Event()
    calls = []

    def slow(project, include_tests=None):
        calls.append(project)
        started.set()
        release.wait(5)

    monkeypatch.setattr(pipeline, 'rebuild', slow, raising=False)
    assert brain.remember('Vivo en Quito', rebuild='background')['graph'] == 'actualizando'
    started.wait(5)
    assert brain.remember('Me gusta el mar', rebuild='background')['graph'] == 'en cola'
    assert brain.remember('Me gusta la montaña', rebuild='background')['graph'] == 'en cola'
    release.set()
    for _ in range(200):
        if not brain.rebuilding('memoria'):
            break
        threading.Event().wait(0.02)
    assert calls == ['memoria', 'memoria']


def test_rebuild_errors_do_not_lose_memories(monkeypatch):
    from cortex_graph import pipeline

    def broken(project, include_tests=None):
        raise CortexError('sin espacio')

    monkeypatch.setattr(pipeline, 'rebuild', broken, raising=False)
    r = brain.remember('Vivo en Lima')
    assert r['graph'] == 'error: sin espacio' and brain.memories()[0]['text'] == 'Vivo en Lima'
    monkeypatch.delattr(pipeline, 'rebuild', raising=False)
    assert brain.remember('Vivo en Cusco')['graph'] == 'actualizado'


def test_concurrent_remember_keeps_every_record():
    errors = []

    def worker(k):
        try:
            brain.remember_many([{'text': f'Dato número {k}-{j}'} for j in range(5)], 'hilos', now='2025-01-01', rebuild=False)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and len(brain.memories('hilos')) == 30


def test_rule_inference_spanish_and_english():
    cases = {
        'Me llamo Marina': ('identity', 'name', 'Marina'),
        'My name is Ana': ('identity', 'name', 'Ana'),
        'I live in Berlin': ('identity', 'lives_in', 'Berlin'),
        'Trabajo en Acme desde 2021': ('identity', 'works_at', 'Acme'),
        'Mi esposa se llama Ana López': ('relationship', 'relationship:wife', 'Ana López'),
        'my boss is John Smith': ('relationship', 'relationship:boss', 'John Smith'),
        'No me gusta el frío': ('preference', 'dislikes', 'el frío'),
        'Mi color favorito es el azul': ('preference', 'favorite:color', 'el azul'),
        'Quiero aprender japonés': ('goal', 'goal', 'aprender japonés'),
        'I decided to use Postgres': ('decision', 'decision', 'to use Postgres'),
        'Mi hermano Pedro vive lejos': ('relationship', 'relationship:brother:pedro', 'Pedro'),
        'Todos los días corro 5 km': ('habit', 'habit', 'corro 5 km'),
        'Siempre respóndeme en español': ('instruction', 'reply_language', 'espanol'),
        'no uses emojis': ('instruction', 'instruction', None),
    }
    for text, expected in cases.items():
        found = brain.infer(text)
        assert (found.get('category'), found.get('attribute'), found.get('value')) == expected, text
    assert brain.infer('Ana vive en Sevilla')['subject'] == 'Ana'
    assert brain.infer('El cielo es azul') == {}


def test_external_rule_facts_are_used_when_available(monkeypatch):
    monkeypatch.setattr(brain, 'external_facts', lambda text, now: {'category': 'skill', 'attribute': 'language', 'value': 'Rust'})
    r = brain.remember('Programo en Rust')
    assert (r['memory']['category'], r['memory']['attribute'], r['memory']['value']) == ('skill', 'language', 'Rust')


def test_real_rule_extractor_supersedes_preferences(monkeypatch):
    pytest.importorskip('cortex_graph.extract')
    monkeypatch.setattr(brain, 'external_facts', REAL_FACTS)
    first = brain.remember('Me gusta el café', now='2025-01-01')
    second = brain.remember('No me gusta el café', now='2025-06-01')
    assert first['memory']['attribute'] == second['memory']['attribute'] and second['superseded'] == [first['id']]
    assert brain.remember('Vivo en Sevilla', now='2025-01-01')['memory']['attribute'] == 'lives_in'


def test_link_memories_builds_nodes_and_edges():
    g = Graph()
    g.node('u:marina', kind='person', name='Marina', file='chats/a.json', line=1, owner=True)
    g.node('u:ana-lopez', kind='person', name='Ana López', file='chats/a.json', line=1, aliases=['Anita'])
    g.node('k:chats/a.json#c1', kind='conversation', name='Charla', file='chats/a.json', line=3)
    records = [
        {'id': 'aaaaaaaaaaaa', 'text': 'Vivo en Sevilla', 'category': 'identity', 'attribute': 'lives_in', 'value': 'Sevilla',
         'valid_from': '2022-01-01', 'origin': 'rule', 'confidence': 0.6, 'source': 'k:chats/a.json#c1', 'msg': 2},
        {'id': 'bbbbbbbbbbbb', 'text': 'Vivo en Madrid', 'category': 'identity', 'attribute': 'lives_in', 'value': 'Madrid',
         'valid_from': '2024-01-01', 'origin': 'manual'},
        {'id': 'cccccccccccc', 'text': 'Anita y yo vamos a Roma', 'category': 'event', 'about': ['Anita', 'Roma'], 'valid_from': '2024-05-01'},
        {'id': 'dddddddddddd', 'text': 'Pedro trabaja en Acme', 'subject': 'Pedro', 'attribute': 'works_at', 'value': 'Acme'},
    ]
    out = brain.link_memories(g, records)
    by_id = {r['id']: r for r in out}
    assert by_id['aaaaaaaaaaaa']['valid_to'] == '2024-01-01' and by_id['bbbbbbbbbbbb']['supersedes'] == ['aaaaaaaaaaaa']
    seville = g.nodes['r:aaaaaaaaaaaa']
    assert seville['kind'] == 'memory' and seville['file'] == 'chats/a.json' and seville['line'] == 3 and seville['valid_to'] == '2024-01-01'
    assert g.nodes['r:bbbbbbbbbbbb']['file'] == '' and g.nodes['r:bbbbbbbbbbbb']['line'] == 0
    edges = set(g.edges)
    assert ('r:aaaaaaaaaaaa', 'k:chats/a.json#c1', 'from') in edges
    assert ('r:bbbbbbbbbbbb', 'r:aaaaaaaaaaaa', 'supersedes') in edges
    assert ('r:bbbbbbbbbbbb', 'u:marina', 'about') in edges
    assert ('r:cccccccccccc', 'u:ana-lopez', 'about') in edges and ('r:cccccccccccc', 'x:roma', 'about') in edges
    assert g.nodes['u:pedro']['kind'] == 'person' and ('r:dddddddddddd', 'u:pedro', 'about') in edges
    again = Graph()
    for nid, meta in g.nodes.items():
        if meta['kind'] != 'memory' and not nid.startswith(('x:roma', 'u:pedro')):
            again.node(nid, **meta)
    brain.link_memories(again, list(reversed(records)))
    assert sorted(again.nodes) == sorted(g.nodes) and again.edges == g.edges


def test_recall_ranks_memories_and_handles_time():
    brain.remember('Vivo en Sevilla', now='2023-01-05')
    brain.remember('Vivo en Madrid', now='2025-03-01')
    brain.remember('Me gusta el café de especialidad', now='2025-01-01')
    brain.remember('Decidí usar Postgres para el proyecto Córtex', now='2025-09-10')
    brain.remember('Decidí aprender piano', now='2024-02-10')
    brain.remember('Siempre respóndeme en español', now='2025-02-01')
    now = '2025-10-15'
    where = brain.recall('¿dónde vivo?', now=now)
    assert [i['text'] for i in where['items']][0] == 'Vivo en Madrid'
    assert all(i['active'] for i in where['items'] if i['kind'] == 'memory')
    assert where['markdown'].startswith('# Memoria · memoria') and '## Recuerdos' in where['markdown']
    english = brain.recall('where do I live', now=now)
    assert english['items'][0]['text'] == 'Vivo en Madrid'
    before = brain.recall('¿dónde vivía antes?', now=now)
    texts = [i['text'] for i in before['items'] if i['kind'] == 'memory']
    assert before['temporal'] and texts[:2] == ['Vivo en Sevilla', 'Vivo en Madrid'] and 'ya no vigente' in before['markdown']
    then = brain.recall('¿dónde vivo?', at='2024-06-01', now=now)
    assert then['items'][0]['text'] == 'Vivo en Sevilla' and then['at'] == '2024-06-01T00:00:00'
    decided = brain.recall('what did I decide last month', now=now)
    assert decided['items'][0]['text'] == 'Decidí usar Postgres para el proyecto Córtex'
    answer = brain.recall('how should you answer me', now=now)
    assert answer['items'][0]['text'] == 'Siempre respóndeme en español'
    small = brain.recall('qué me gusta', budget=200, now=now)
    assert small['tokens'] <= 200 and small['items']
    nothing = brain.recall('xilófono cuántico', now=now)
    assert nothing['items'] == [] and 'Nada en la memoria' in nothing['markdown']
    with pytest.raises(InvalidInput):
        brain.recall('')
    with pytest.raises(InvalidInput):
        brain.recall('x', at='no-es-fecha')


def test_recall_on_empty_memory_is_friendly():
    r = brain.recall('¿quién soy?')
    assert r['items'] == [] and 'Todavía no hay recuerdos' in r['markdown']


def save_graph(project, nodes, edges, root):
    full = []
    for i, n in enumerate(nodes):
        full.append({'id': i, 'c': 0, 'deg': 1, 'pos': [0.0, 0.0, 0.0], 'hash': str(i), **n})
    ids = {n['key']: n['id'] for n in full}
    graph = {
        'project': project, 'nodes': full,
        'edges': [{'a': ids[a], 'b': ids[b], 'kind': k, 'w': 1} for a, b, k in edges], 'visible': [],
        'communities': [{'id': 0, 'name': 'memoria', 'hub': 'x', 'size': len(full), 'center': [0, 0, 0], 'radius': 1.0, 'color': [1, 1, 1]}],
        'stats': {'files': 1, 'nodes': len(full), 'edges': len(edges), 'communities': 1},
    }
    store.save_version(graph, {'type': 'local', 'path': str(root)})


@pytest.fixture
def brain_graph(tmp_path, monkeypatch):
    root = tmp_path / 'fuente'
    (root / 'chats').mkdir(parents=True)
    (root / 'chats' / 'a.json').write_text('[]', encoding='utf-8')
    (root / 'notas').mkdir()
    (root / 'notas' / 'viajes.md').write_text('# Viajes\n\nQuiero volver a Kioto en otoño con Ana.\n', encoding='utf-8')
    conversation = {'id': 'c1', 'source': 'chatgpt', 'title': 'Planes', 'started': '2025-05-01T09:00:00', 'ended': None,
                    'participants': ['Marina'], 'messages': [
                        {'i': 0, 'role': 'user', 'author': 'Marina', 'time': '2025-05-01T09:00:00', 'text': 'Hola', 'line': 0},
                        {'i': 1, 'role': 'assistant', 'author': '', 'time': None, 'text': '¿En qué te ayudo?', 'line': 0},
                        {'i': 2, 'role': 'user', 'author': 'Marina', 'time': None, 'text': f'Mi hermana Lucía vive en Oslo, clave {TOKEN}', 'line': 0},
                    ]}
    fake = types.SimpleNamespace(load=lambda r, rel, fmt=None: [conversation] if rel == 'chats/a.json' else [])
    monkeypatch.setitem(sys.modules, 'cortex_graph.importers', fake)
    monkeypatch.setattr(cortex_graph, 'importers', fake, raising=False)
    nodes = [
        {'key': 'k:chats/a.json#c1', 'kind': 'conversation', 'name': 'Planes', 'file': 'chats/a.json', 'line': 0, 'started': '2025-05-01T09:00:00',
         'doc': 'Hola', 'source': 'chatgpt', 'count': 3},
        {'key': 'u:lucia', 'kind': 'person', 'name': 'Lucía', 'file': '', 'line': 0, 'aliases': ['Lu']},
        {'key': 'r:eeeeeeeeeeee', 'kind': 'memory', 'name': 'Mi hermana Lucía vive en Oslo', 'file': 'chats/a.json', 'line': 0,
         'text': 'Mi hermana Lucía vive en Oslo', 'category': 'relationship', 'subject': 'user', 'attribute': 'relationship:sister:lucia',
         'value': 'Lucía', 'valid_from': '2025-05-01', 'confidence': 0.6, 'origin': 'rule', 'source': 'k:chats/a.json#c1', 'msg': 2},
        {'key': 's:notas/viajes.md#viajes', 'kind': 'section', 'name': 'Viajes', 'file': 'notas/viajes.md', 'line': 1, 'end': 3,
         'doc': 'Quiero volver a Kioto en otoño con Ana.'},
        {'key': 'w:2025-11-02:kioto', 'kind': 'event', 'name': 'Vuelo a Kioto', 'file': 'notas/viajes.md', 'line': 3, 'when': '2025-11-02'},
    ]
    edges = [('r:eeeeeeeeeeee', 'k:chats/a.json#c1', 'from'), ('r:eeeeeeeeeeee', 'u:lucia', 'about'),
             ('k:chats/a.json#c1', 'u:lucia', 'mentions')]
    save_graph('memoria', nodes, edges, root)
    return root


def test_recall_uses_graph_memories_excerpts_and_sections(brain_graph):
    r = brain.recall('¿dónde vive mi hermana?', now='2025-10-01')
    first = r['items'][0]
    assert first['key'] == 'r:eeeeeeeeeeee' and first['probable'] is True
    assert 'Mi hermana Lucía vive en Oslo' in first['excerpt'] and TOKEN not in r['markdown'] and '«redactado»' in first['excerpt']
    assert 'probable' in r['markdown']
    trip = brain.recall('viaje a Kioto', now='2025-10-01')
    keys = [i['key'] for i in trip['items']]
    assert 's:notas/viajes.md#viajes' in keys and 'w:2025-11-02:kioto' in keys
    section = next(i for i in trip['items'] if i['key'] == 's:notas/viajes.md#viajes')
    assert 'Kioto' in section['excerpt'] and '## Fragmentos' in trip['markdown']
    assert brain.forget('r:eeeeeeeeeeee')['forgotten'] == ['eeeeeeeeeeee']
    assert all(i['key'] != 'r:eeeeeeeeeeee' for i in brain.recall('¿dónde vive mi hermana?', now='2025-10-01')['items'])


def test_profile_sections_probable_and_budget(brain_graph):
    brain.remember('Me llamo Marina', now='2025-01-01')
    brain.remember('Siempre respóndeme en español', now='2025-01-02')
    brain.remember('Me gusta el café', now='2025-01-03')
    brain.remember_many([{'text': 'Quiero correr una maratón', 'origin': 'rule', 'confidence': 0.55, 'when': '2025-04-01'}], rebuild=False)
    brain.remember(f'Mi contraseña del banco es password="{TOKEN}"', now='2025-01-04')
    p = brain.profile(now='2025-10-01')
    md = p['markdown']
    assert md.startswith('# Perfil · memoria') and '## Quién es' in md and '## Instrucciones para asistentes' in md
    assert '## Preferencias' in md and '## Objetivos' in md and '## Personas clave' in md
    assert set(p['sections']) >= {'identity', 'instructions', 'preferences', 'goals', 'people'}
    goal = p['sections']['goals'][0]
    assert goal['probable'] is True and 'Quiero correr una maratón (2025-04-01' not in md and '(desde 2025-04-01; probable)' in md
    assert 'banco' not in md and p['count'] >= 4
    assert any(i.get('key') == 'r:eeeeeeeeeeee' for i in p['sections']['people'])
    brain.remember_many([{'text': f'Me gusta la ciudad número {k} por sus museos y parques'} for k in range(12)], now='2025-05-01', rebuild=False)
    tiny = brain.profile(budget=200, now='2025-10-01')
    assert tiny['tokens'] <= 200 and tiny['truncated']


def test_timeline_orders_and_filters(brain_graph):
    brain.remember('Vivo en Sevilla', now='2023-01-05')
    brain.remember('Vivo en Madrid', now='2025-03-01')
    t = brain.timeline()
    dates = [i['date'] for i in t['items']]
    assert dates == sorted(dates) and t['total'] == len(t['items'])
    kinds = {i['kind'] for i in t['items']}
    assert {'memory', 'conversation', 'event'} <= kinds
    seville = next(i for i in t['items'] if i['text'] == 'Vivo en Sevilla')
    assert seville['active'] is False and seville['until'].startswith('2025-03-01')
    assert [i['text'] for i in brain.timeline(start='2025-01-01', end='2025-04-30')['items']] == ['Vivo en Madrid']
    about = brain.timeline(about='lucia')
    assert {i['key'] for i in about['items']} == {'r:eeeeeeeeeeee', 'k:chats/a.json#c1'}
    assert len(brain.timeline(limit=2)['items']) == 2 and brain.timeline(limit=2)['items'][-1]['date'] == dates[-1]
    with pytest.raises(InvalidInput):
        brain.timeline(start='mañana')


def test_import_history_with_fake_ai(tmp_path, monkeypatch):
    from cortex_graph import pipeline
    folder = tmp_path / 'export'
    folder.mkdir()
    events = []
    monkeypatch.setattr(pipeline, 'analyze_source', lambda source, name=None, *a, **k: events.append(('analyze', name)) or {'project': name},
                        raising=False)
    monkeypatch.setattr(pipeline, 'summary', lambda graph: {'project': graph['project']}, raising=False)
    monkeypatch.setattr(brain, 'graph_index', lambda project: None)
    conversations = [{'id': 'c1', 'messages': [{'i': 0, 'role': 'user', 'text': 'Me mudé a Oslo'}], 'node': 'k:conv.json#c1'}]
    monkeypatch.setattr(brain, 'find_sources', lambda root: events.append(('find', root)) or conversations)

    class FakeLLM:
        DEFAULT_MODEL = 'modelo-de-prueba'

        @staticmethod
        def available():
            return True, ''

        @staticmethod
        def extract_memories(convs, owner_names=None, model=None, batch=False, client=None, on_progress=None, max_chars=60000):
            events.append(('extract', batch, model))
            return [{'text': 'El usuario vive en Oslo', 'category': 'identity', 'subject': 'user', 'attribute': 'lives_in',
                     'value': 'Oslo', 'confidence': 0.9, 'source': 'c1', 'msg': 0, 'when': '2025-02-01', 'sensitive': False}]

    monkeypatch.setattr(brain, 'load_llm', lambda: FakeLLM)
    warned = []
    result = brain.import_history(str(folder), ai=True, batch=True, warn=lambda *a: warned.append(a) or events.append(('warn',)))
    assert [e[0] for e in events] == ['analyze', 'find', 'warn', 'extract'] and events[-1] == ('extract', True, None)
    assert warned == [(1, len('Me mudé a Oslo'), 'modelo-de-prueba')]
    stored = brain.memories()[0]
    assert stored['origin'] == 'ai' and stored['source'] == 'k:conv.json#c1' and stored['msg'] == 0
    assert result['ai']['counts'] == {'new': 1} and result['memories'] == 1
    local = brain.import_history(str(folder))
    assert local['ai'] is None and events[-1] == ('analyze', 'memoria')
    FakeLLM.available = staticmethod(lambda: (False, 'falta ANTHROPIC_API_KEY'))
    with pytest.raises(CortexError, match='ANTHROPIC_API_KEY'):
        brain.import_history(str(folder), ai=True)


def test_statements_are_normalized_third_person():
    cases = [
        ({'attribute': 'lives_in', 'value': 'Bogotá'}, 'Vive en Bogotá'),
        ({'attribute': 'lives_in', 'value': '', 'object': 'Medellín', 'negated': True}, 'Ya no vive en Medellín'),
        ({'attribute': 'works_at', 'value': 'Lumen'}, 'Trabaja en Lumen'),
        ({'attribute': 'job_title', 'value': 'desarrollador'}, 'Trabaja como desarrollador'),
        ({'attribute': 'name', 'value': 'Laura'}, 'Se llama Laura'),
        ({'attribute': 'relationship:wife', 'value': 'Ana Gómez'}, 'Su esposa: Ana Gómez'),
        ({'attribute': 'relationship:dog:toby', 'value': 'Toby'}, 'Su perro: Toby'),
        ({'attribute': 'pref:jazz', 'value': 'love', 'object': 'jazz'}, 'Le encanta jazz'),
        ({'attribute': 'pref:cafe', 'value': 'like', 'object': 'el café'}, 'Le gusta el café'),
        ({'attribute': 'pref:madrugar', 'value': 'dislike', 'object': 'madrugar'}, 'No le gusta madrugar'),
        ({'attribute': 'pref:trafico', 'value': 'hate', 'object': 'tráfico'}, 'Odia tráfico'),
        ({'attribute': 'pref:hotel', 'value': 'prefer', 'object': 'hoteles pequeños'}, 'Prefiere hoteles pequeños'),
        ({'attribute': 'dislikes', 'value': 'el frío'}, 'No le gusta el frío'),
        ({'attribute': 'goal:japon', 'value': 'aprender japonés'}, 'Quiere aprender japonés'),
        ({'attribute': 'decided:postgres', 'value': 'usar Postgres.'}, 'Decidió usar Postgres'),
        ({'attribute': 'speaks:ingles', 'value': 'inglés'}, 'Habla inglés'),
        ({'attribute': 'learning:piano', 'value': 'piano'}, 'Está aprendiendo piano'),
        ({'attribute': 'works_at', 'value': 'Acme', 'subject': 'Pedro'}, 'Pedro trabaja en Acme'),
        ({'attribute': 'instruction:espanol', 'value': 'x', 'category': 'instruction'}, 'Siempre respóndeme en español'),
        ({'attribute': 'raro:algo', 'value': 'x'}, 'Siempre respóndeme en español'),
        ({}, 'Siempre respóndeme en español'),
    ]
    for fields, expected in cases:
        record = brain.complete({'id': 'x', 'text': 'Siempre respóndeme en español', **fields})
        assert brain.statement(record) == expected, fields


def test_one_sentence_with_many_facts_renders_each_once():
    sentence = 'Prefiero hoteles pequeños y no me gusta madrugar.'
    base = {'text': sentence, 'category': 'preference', 'origin': 'rule', 'confidence': 0.75, 'when': '2025-03-01'}
    brain.remember_many([
        dict(base, id='aaaaaaaaaaa1', attribute='pref:hotel-pequeno', value='prefer', object='hoteles pequeños'),
        dict(base, id='aaaaaaaaaaa2', attribute='pref:madrugar', value='dislike', object='madrugar'),
        dict(base, id='aaaaaaaaaaa3', text='Odio madrugar, no me gusta nada', attribute='pref:madrugar-temprano', value='dislike',
             object='madrugar'),
        {'text': 'Laura, ya no vivo en Medellín, me fui a vivir a Bogotá', 'category': 'identity', 'attribute': 'lives_in',
         'value': 'Bogotá', 'origin': 'rule', 'confidence': 0.75, 'when': '2025-04-01'},
    ], rebuild=False)
    md = brain.profile(now='2025-10-01')['markdown']
    assert md.count('- Prefiere hoteles pequeños') == 1 and md.count('- No le gusta madrugar') == 1
    assert '- Vive en Bogotá' in md and sentence not in md and 'Medellín' not in md
    merged = next(i for i in brain.profile(now='2025-10-01')['sections']['preferences'] if i['statement'] == 'No le gusta madrugar')
    assert len(merged['merged']) == 2
    r = brain.recall('¿dónde vivo?', now='2025-10-01')
    assert r['items'][0]['statement'] == 'Vive en Bogotá' and r['items'][0]['text'].startswith('Laura')
    assert '- Vive en Bogotá · ' in r['markdown'] and '  > «Laura, ya no vivo en Medellín' in r['markdown']
    liked = brain.recall('qué no me gusta', now='2025-10-01')
    assert liked['markdown'].count('No le gusta madrugar') == 1


def test_excerpt_neighbours_stay_within_six_hours():
    conversation = {'messages': [
        {'i': 0, 'role': 'user', 'author': 'Laura', 'time': '2024-02-01T09:00:00', 'text': 'mensaje viejo'},
        {'i': 1, 'role': 'user', 'author': 'Laura', 'time': '2025-03-01T10:00:00', 'text': 'me mudé a Bogotá'},
        {'i': 2, 'role': 'other', 'author': 'Ana', 'time': '2025-03-01T13:30:00', 'text': '¡qué bien!'},
        {'i': 3, 'role': 'other', 'author': 'Ana', 'time': None, 'text': 'sin hora'},
    ]}
    text = brain.conversation_excerpt(conversation, 1)
    assert 'me mudé a Bogotá' in text and '¡qué bien!' in text and 'mensaje viejo' not in text
    assert 'sin hora' in brain.conversation_excerpt(conversation, 2)
    assert brain.conversation_excerpt(conversation, 0) == '> **Laura** · 2024-02-01 09:00: mensaje viejo'


@pytest.fixture
def chats(tmp_path, monkeypatch):
    root = tmp_path / 'chats-src'
    (root / 'chats').mkdir(parents=True)
    convs = {}
    filler = ['qué tal el día', 'bien, mucho trabajo', 'nos vemos luego', 'jaja vale', 'perfecto, gracias']
    for n, (rel, day) in enumerate((('chats/s1.json', '2023-05-07'), ('chats/s2.json', '2023-08-20'), ('chats/s3.json', '2024-02-11'))):
        (root / rel).write_text('[]', encoding='utf-8')
        messages = []
        for k in range(30):
            text = f'Lucía: {filler[k % len(filler)]}'
            messages.append({'i': k, 'role': 'user' if k % 2 else 'other', 'author': 'Lucía' if k % 2 == 0 else 'Marina',
                             'time': f'{day}T10:{k:02d}:00', 'text': text, 'line': k + 1})
        convs[rel] = {'id': 'c', 'title': f'Sesión {n + 1}', 'messages': messages}
    convs['chats/s1.json']['messages'][12]['text'] = 'Lucía: fui a pintar un mural con acuarelas en el parque'
    convs['chats/s1.json']['messages'][13]['text'] = 'Marina: ¡qué bonito ese mural!'
    convs['chats/s2.json']['messages'][5]['text'] = 'Lucía: hoy aprendí cerámica y pinté un jarrón'
    convs['chats/s3.json']['messages'][20]['text'] = 'Lucía: corrí la maratón de Oslo'
    convs['chats/s3.json']['messages'][21]['time'] = '2024-02-12T09:00:00'
    convs['chats/s3.json']['messages'][21]['text'] = 'Marina: ¿y la maratón de Oslo fue dura?'
    fake = types.SimpleNamespace(load=lambda r, rel, fmt=None: [convs[rel]] if rel in convs else [])
    monkeypatch.setitem(sys.modules, 'cortex_graph.importers', fake)
    monkeypatch.setattr(cortex_graph, 'importers', fake, raising=False)
    nodes = [{'key': f'k:{rel}#c', 'kind': 'conversation', 'name': c['title'], 'file': rel, 'line': 0,
              'started': c['messages'][0]['time'], 'count': 30} for rel, c in sorted(convs.items())]
    save_graph('memoria', nodes, [], root)
    return convs


def test_recall_ranks_messages_with_refs(chats):
    r = brain.recall('¿Qué pintó Lucía en el parque?', budget=600, now='2024-06-01')
    convo = [i for i in r['items'] if i['kind'] == 'conversation']
    assert convo and max(convo, key=lambda i: i['score'])['key'] == 'k:chats/s1.json#c'
    refs = next(i for i in convo if i['key'] == 'k:chats/s1.json#c')['messages']
    assert {'file': 'chats/s1.json', 'conversation': 'k:chats/s1.json#c', 'i': 12, 'line': 13} in refs
    group = r['markdown'].split('k:chats/s1.json#c`')[1].split('###')[0]
    assert '- 2023-05-07 ' in group and '10:12 Lucía: Lucía: fui a pintar un mural con acuarelas en el parque' in group
    assert '### `k:chats/s1.json#c`' in r['markdown'] or '### «Sesión 1» `k:chats/s1.json#c`' in r['markdown']
    assert r['tokens'] <= 600
    oslo = brain.recall('maratón de Oslo', budget=600, now='2024-06-01')
    hit = next(i for i in oslo['items'] if i['key'] == 'k:chats/s3.json#c')
    assert {20, 21} <= {m['i'] for m in hit['messages']}
    assert '- 2024-02-12 09:00 Marina:' in oslo['markdown']


def test_group_lines_show_date_once_per_day(chats):
    index = brain.graph_index('memoria')
    mi = brain.message_index(index)
    assert brain.message_index(index) is mi and len(mi['msgs']) == 90
    ids = mi['convs']['k:chats/s3.json#c']
    text = brain.render_group(mi, [ids[3], ids[20], ids[21]])
    lines = text.splitlines()
    assert lines[0].startswith('- 2024-02-11 10:03 ') and lines[1] == '- …' and lines[2].startswith('- 10:20 ')
    assert lines[3].startswith('- 2024-02-12 09:00 Marina: ')


def test_rare_terms_outweigh_common_ones(chats):
    index = brain.graph_index('memoria')
    mi = brain.message_index(index)
    scores = mi['model'].score('trabajo y jarrón')
    top = max(range(len(scores)), key=lambda x: scores[x])
    assert mi['msgs'][top]['conv'] == 'k:chats/s2.json#c' and mi['msgs'][top]['i'] == 5
    named = mi['model'].score('¿qué dijo Lucía?')
    assert all(named[x] >= named[x + 1] for x in range(0, 30, 2))


def test_many_instances_diversify_across_conversations(chats):
    r = brain.recall('¿Cuántas cosas pintó Lucía?', budget=800, now='2024-06-01')
    keys = [i['key'] for i in r['items'] if i['kind'] == 'conversation']
    assert {'k:chats/s1.json#c', 'k:chats/s2.json#c'} <= set(keys)


def test_explicit_dates_build_time_windows():
    now = brain.to_moment('2024-06-15')
    assert brain.time_window('what did she do in May 2023', now) == (brain.datetime(2023, 5, 1), brain.datetime(2023, 6, 1))
    assert brain.time_window('qué pasó el 7 de mayo de 2023', now) == (brain.datetime(2023, 5, 6), brain.datetime(2023, 5, 9))
    assert brain.time_window('on August 20, 2023', now)[0] == brain.datetime(2023, 8, 19)
    assert brain.time_window('qué hice en septiembre', now) == (brain.datetime(2023, 9, 1), brain.datetime(2023, 10, 1))
    assert brain.time_window('qué hice en marzo', now) == (brain.datetime(2024, 3, 1), brain.datetime(2024, 4, 1))
    assert brain.time_window('qué hice', now) is None


def test_temporal_window_boosts_matching_session(chats):
    r = brain.recall('what did Lucía paint in August 2023', budget=400, now='2024-06-01')
    best = max((i for i in r['items'] if i['kind'] == 'conversation'), key=lambda i: i['score'])
    assert best['key'] == 'k:chats/s2.json#c' and 5 in {m['i'] for m in best['messages']}


def test_memories_are_capped_and_excerpts_must_match(chats):
    brain.remember_many([{'text': f'Me gusta pintar cuadro número {k} con acuarelas', 'category': 'preference', 'origin': 'rule',
                          'confidence': 0.6, 'source': 'k:chats/s1.json#c', 'msg': 3} for k in range(40)], rebuild=False)
    r = brain.recall('¿Qué pintó Lucía con acuarelas en el parque?', budget=1000, now='2024-06-01')
    memory_part = r['markdown'].split('## Fragmentos')[0]
    assert brain.tokens(memory_part) <= 0.3 * 1000 + 120
    assert any(i['kind'] == 'conversation' for i in r['items'])
    assert all('excerpt' not in i for i in r['items'] if i['kind'] == 'memory')
    brain.remember_many([{'text': 'Le encantó el mural del parque', 'source': 'k:chats/s1.json#c', 'msg': 12}], now='2024-01-01', rebuild=False)
    good = brain.recall('mural del parque', budget=1000, now='2024-06-01')
    mural = next(i for i in good['items'] if i['kind'] == 'memory' and 'mural' in i['text'])
    assert 'fui a pintar un mural' in mural['excerpt'] and {'file': 'chats/s1.json', 'conversation': 'k:chats/s1.json#c', 'i': 12, 'line': 13} in mural['messages']
    fragments = good['markdown'].split('## Fragmentos')[-1]
    assert 'fui a pintar un mural' not in fragments
    profile_like = brain.recall('¿qué sabes de mí?', budget=1000, now='2024-06-01')
    assert sum(1 for i in profile_like['items'] if i['kind'] == 'memory') > sum(1 for i in r['items'] if i['kind'] == 'memory')


def test_recall_hints_add_lower_weight_terms(chats):
    plain = brain.recall('¿qué hizo Lucía?', budget=300, now='2024-06-01')
    hinted = brain.recall('¿qué hizo Lucía?', budget=300, now='2024-06-01', hints=['acuarelas', 'mural', 'pintura'])
    assert 'hints' not in plain and hinted['hints'] == ['acuarelas', 'mural', 'pintura']
    best = max((i for i in hinted['items'] if i['kind'] == 'conversation'), key=lambda i: i['score'])
    assert best['key'] == 'k:chats/s1.json#c' and 12 in {m['i'] for m in best['messages']}
    direct = brain.recall('maratón', budget=300, now='2024-06-01', hints=['cerámica'])
    top = max((i for i in direct['items'] if i['kind'] == 'conversation'), key=lambda i: i['score'])
    assert top['key'] == 'k:chats/s3.json#c'
    assert brain.clean_hints('a, b;a\nc') == ['a', 'b', 'c'] and brain.clean_hints(None) == []
    for bad in ([1], {'a': 1}, ['x' * 200], [f'w{k}' for k in range(40)]):
        with pytest.raises(InvalidInput):
            brain.recall('hola', budget=300, hints=bad)


def test_recall_uses_optional_embeddings(chats, monkeypatch):
    import numpy as np
    from cortex_graph import semantic

    class Toy:
        name = 'toy@1'
        calls = 0

        def __call__(self, texts):
            Toy.calls += 1
            out = np.full((len(texts), 2), 0.01, dtype=np.float32)
            for k, t in enumerate(texts):
                if any(w in t.lower() for w in ('mural', 'acuarelas', 'zorblat')):
                    out[k, 0] = 1.0
                else:
                    out[k, 1] = 1.0
            return out / np.linalg.norm(out, axis=1, keepdims=True)

    monkeypatch.setattr(semantic, 'encoder', lambda: Toy() if semantic.configured() else None)
    monkeypatch.setenv('CORTEX_EMBED_MODEL', 'toy')
    r = brain.recall('zorblat', budget=300, now='2024-06-01')
    best = max((i for i in r['items'] if i['kind'] == 'conversation'), key=lambda i: i['score'])
    assert best['key'] == 'k:chats/s1.json#c' and 12 in {m['i'] for m in best['messages']}
    files = [f for f in os.listdir(os.path.join(store.project_dir('memoria'), semantic.FOLDER)) if f.endswith('.npy')]
    assert len(files) == 1
    monkeypatch.setenv('CORTEX_EMBED_MODEL', 'off')
    assert not [i for i in brain.recall('zorblat', budget=300, now='2024-06-01')['items'] if i['kind'] == 'conversation']
