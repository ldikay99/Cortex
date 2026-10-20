import copy
import json
import textwrap
import time
import types
from pathlib import Path

import pytest

from cortex_graph import analyze, content
from cortex_graph.common import Graph, Issues, read_source


def write(root, rel, text):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip('\n'), encoding='utf-8')


def message(i, role, author, text, time=None, line=0):
    return {'i': i, 'role': role, 'author': author, 'time': time, 'text': text, 'line': line}


def chat(cid, title, msgs, source='chatgpt'):
    times = sorted(m['time'] for m in msgs if m['time'])
    return {'id': cid, 'source': source, 'title': title, 'started': times[0] if times else None,
            'ended': times[-1] if times else None, 'participants': sorted({m['author'] for m in msgs if m['author']}),
            'messages': msgs}


def fake_importers(data):
    def user_names(convs):
        names = set()
        for c in convs:
            for m in c['messages']:
                if m['role'] == 'user' and m['author']:
                    names.add(m['author'])
        return names
    return types.SimpleNamespace(
        MAX_CONVERSATIONS=5000, MAX_MESSAGES=20000,
        detect=lambda rel, head: data[rel][0] if rel in data else None,
        load=lambda root, rel, fmt=None: copy.deepcopy(data[rel][1]),
        user_names=user_names)


def fake_documents(docs):
    def extract(root, rel):
        item = docs.get(rel)
        if item is None:
            return None
        base = {'title': '', 'text': '', 'meta': {}, 'links': [], 'tags': [], 'sections': [], 'messages': [], 'events': []}
        base.update(copy.deepcopy(item))
        return base
    return types.SimpleNamespace(supports=lambda rel: rel in docs or rel.endswith('.pdf'), extract=extract)


def build(root, files=None, now='2026-01-01T00:00:00'):
    root = Path(root)
    files = sorted(files if files is not None else (str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()))
    g, issues = Graph(), Issues()
    analyze.declare_docs(root, [f for f in files if f.endswith(('.md', '.mdx'))], g, issues)
    records = content.link_content(root, files, g, issues, read_source, now=now)
    return g, issues, records


def edges(g, kind=None):
    return {(a, b, k) for (a, b, k) in g.edges if kind is None or k == kind}


@pytest.fixture
def chats(tmp_path, monkeypatch):
    data = {
        'chat/export.json': ('chatgpt', [
            chat('c1', 'Plan de viaje', [
                message(0, 'user', 'user', 'Me llamo Ana y vivo en Bogotá. Hablé con Laura Gómez del grafo de conocimiento.',
                        '2024-01-01T10:00:00Z'),
                message(1, 'assistant', 'assistant', 'Pregúntale a Roberto Díaz sobre el grafo de conocimiento.',
                        '2024-01-01T10:01:00Z'),
                message(2, 'user', 'user', 'Siempre respóndeme en español.', '2024-01-01T10:02:00Z')]),
            chat('c2', '', [
                message(0, 'user', 'user', 'Necesito ideas para la memoria personal y el grafo de conocimiento. Vivo en Bogotá.',
                        '2024-02-01T09:00:00Z'),
                message(1, 'assistant', 'assistant', 'La memoria personal y el grafo de conocimiento se complementan.',
                        '2024-02-01T09:01:00Z')]),
        ]),
        'chat/wa.txt': ('whatsapp', [
            chat('0', 'Pedro Pérez', [
                message(0, 'user', 'Ana', 'Hola Pedro, mañana vemos la memoria personal con Laura Gómez.', '2024-03-01T08:00:00', 1),
                message(1, 'other', 'Pedro Pérez', 'Listo, el grafo de conocimiento queda para después.', '2024-03-01T08:05:00', 2),
                message(2, 'user', 'Ana', 'Me mudé a Medellín la semana pasada.', '2024-03-02T08:00:00', 3)], 'whatsapp'),
        ]),
    }
    for rel in data:
        write(tmp_path, rel, 'x')
    monkeypatch.setattr(content, 'importers', fake_importers(data))
    monkeypatch.setattr(content, 'documents', fake_documents({}))
    return tmp_path


def test_conversations_people_and_owner(chats):
    g, issues, records = build(chats)
    conv = g.nodes['k:chat/export.json#c1']
    assert conv['kind'] == 'conversation' and conv['name'] == 'Plan de viaje' and conv['source'] == 'chatgpt'
    assert conv['started'] == '2024-01-01T10:00:00Z' and conv['ended'] == '2024-01-01T10:02:00Z' and conv['count'] == 3
    assert conv['doc'].startswith('Me llamo Ana') and conv['file'] == 'chat/export.json' and conv['line'] == 1
    assert g.nodes['k:chat/export.json#c2']['name'].startswith('Necesito ideas para la memoria')
    assert g.nodes['d:chat/export.json']['kind'] == 'doc'
    assert ('d:chat/export.json', 'k:chat/export.json#c1', 'contains') in g.edges
    assert ('d:chat/wa.txt', 'k:chat/wa.txt#0', 'contains') in g.edges
    owner = g.nodes['u:ana']
    assert owner['owner'] is True and owner['kind'] == 'person' and 'user' in owner['aliases'] and owner['name'] == 'Ana'
    assert ('k:chat/export.json#c1', 'u:ana', 'participant') in g.edges
    assert ('k:chat/wa.txt#0', 'u:ana', 'participant') in g.edges
    assert ('k:chat/wa.txt#0', 'u:pedro-perez', 'participant') in g.edges
    assert ('k:chat/export.json#c1', 'u:laura-gomez', 'mentions') in g.edges
    assert 'u:roberto-diaz' not in g.nodes and 'u:assistant' not in g.nodes and 'u:user' not in g.nodes
    assert 'u:pedro' not in g.nodes and 'Pedro' in g.nodes['u:pedro-perez']['aliases']
    for nid, meta in g.nodes.items():
        assert meta.get('file') is not None and isinstance(meta.get('line'), int), nid


def test_concepts_need_two_sources_and_relate(chats):
    g, _, _ = build(chats)
    assert g.nodes['x:grafo-de-conocimiento']['kind'] == 'concept'
    assert 'x:memoria-personal' in g.nodes
    assert ('x:grafo-de-conocimiento', 'x:memoria-personal', 'related') in g.edges
    assert ('k:chat/export.json#c2', 'x:memoria-personal', 'mentions') in g.edges
    assert not any(n.startswith('x:') and 'viaje' in n for n in g.nodes)


def test_rule_memories_are_returned(chats):
    _, _, records = build(chats)
    by = {}
    for r in records:
        by.setdefault(r['attribute'], []).append(r)
    bogota = [r for r in by['lives_in'] if r['value'] == 'Bogotá']
    assert len(bogota) == 2 and {r['source'] for r in bogota} == {'k:chat/export.json#c1', 'k:chat/export.json#c2'}
    medellin = next(r for r in by['lives_in'] if r['value'] == 'Medellín')
    assert medellin['source'] == 'k:chat/wa.txt#0' and medellin['msg'] == 2
    assert sorted(medellin['supersedes']) == sorted(r['id'] for r in bogota)
    assert all(r['valid_to'] == medellin['valid_from'] for r in bogota)
    assert by['instruction:espanol'][0]['category'] == 'instruction'
    assert all(r['origin'] == 'rule' and len(r['id']) == 12 for r in records)
    assert records == sorted(records, key=lambda r: (r['valid_from'] or '', r['id']))


def test_repeated_fact_raises_confidence(tmp_path, monkeypatch):
    data = {'a.json': ('generic', [
        chat('1', 't', [message(0, 'user', 'user', 'Me gusta el jazz.', '2024-01-01T00:00:00Z')]),
        chat('2', 't', [message(0, 'user', 'user', 'Me gusta el jazz.', '2023-01-01T00:00:00Z')]),
    ])}
    write(tmp_path, 'a.json', 'x')
    monkeypatch.setattr(content, 'importers', fake_importers(data))
    monkeypatch.setattr(content, 'documents', fake_documents({}))
    _, _, records = build(tmp_path)
    assert len(records) == 1
    assert records[0]['seen'] == 2 and records[0]['confidence'] == 0.75 and records[0]['source'] == 'k:a.json#2'


def test_markdown_notes_links_sections_and_tags(tmp_path, monkeypatch):
    monkeypatch.setattr(content, 'importers', fake_importers({}))
    monkeypatch.setattr(content, 'documents', fake_documents({}))
    long_body = '\n'.join(f'Línea {i} sobre la memoria personal.' for i in range(45))
    write(tmp_path, 'vault/Proyecto Cortex.md', """
        ---
        title: Proyecto Cortex
        tags: [grafo, memoria]
        aliases:
          - Cortex
          - Córtex
        date: 2025-03-12
        ---
        # Proyecto Cortex

        Intro con [[ideas]] y [[Machine Learning|ML]] y [[Laura Gómez]]. #segundo-cerebro

        ## Diseño

        El diseño usa el grafo de conocimiento.

        ### Detalles

        Más detalles con Carlos Ruiz.

        ## Fechas

        LONG
        """)
    path = tmp_path / 'vault/Proyecto Cortex.md'
    path.write_text(path.read_text(encoding='utf-8').replace('LONG', long_body), encoding='utf-8')
    write(tmp_path, 'vault/sub/Ideas.md', """
        tags:: grafo, [[lluvia de ideas]]
        alias:: Lluvia

        Ver [[Cortex]], [[proyecto cortex#Diseño]], [[Proyecto Cortex#No existe]] y [otro](../Proyecto%20Cortex.md).
        Laura Gómez revisó el grafo de conocimiento. #segundo-cerebro
        """)
    write(tmp_path, 'vault/Diario.md', 'Hoy hablé de [[Lluvia]] y [[ML]] con Laura Gómez.\n')
    g, _, _ = build(tmp_path)
    doc = g.nodes['d:vault/Proyecto Cortex.md']
    assert doc['tags'] == ['grafo', 'memoria'] and doc['aliases'] == ['Cortex', 'Córtex'] and doc['when'] == '2025-03-12'
    assert doc['doc'] == 'Proyecto Cortex'
    assert 'd:vault/sub/Ideas.md' in g.nodes and g.nodes['d:vault/sub/Ideas.md']['tags'] == ['grafo', 'lluvia de ideas']
    links = edges(g, 'links')
    assert ('d:vault/Proyecto Cortex.md', 'd:vault/sub/Ideas.md', 'links') in links
    assert ('d:vault/sub/Ideas.md', 'd:vault/Proyecto Cortex.md', 'links') in links
    assert ('d:vault/sub/Ideas.md', 's:vault/Proyecto Cortex.md#diseno', 'links') in links
    assert ('d:vault/Diario.md', 'd:vault/sub/Ideas.md', 'links') in links
    assert g.nodes['s:vault/Proyecto Cortex.md#diseno']['kind'] == 'section'
    assert g.nodes['s:vault/Proyecto Cortex.md#diseno']['doc'] == 'El diseño usa el grafo de conocimiento.'
    assert 's:vault/Proyecto Cortex.md#proyecto-cortex' not in g.nodes
    contains = edges(g, 'contains')
    assert ('d:vault/Proyecto Cortex.md', 's:vault/Proyecto Cortex.md#diseno', 'contains') in contains
    assert ('s:vault/Proyecto Cortex.md#diseno', 's:vault/Proyecto Cortex.md#detalles', 'contains') in contains
    fechas = g.nodes['s:vault/Proyecto Cortex.md#fechas']
    assert fechas['line'] < fechas['end'] and g.nodes['s:vault/Proyecto Cortex.md#detalles']['end'] == fechas['line'] - 1
    assert ('s:vault/Proyecto Cortex.md#detalles', 'u:carlos-ruiz', 'mentions') in g.edges
    ml = g.nodes['x:machine-learning']
    assert ml['kind'] == 'concept' and 'ML' in ml['aliases']
    assert g.nodes['x:segundo-cerebro']['tag'] is True and g.nodes['x:grafo']['tag'] is True
    assert ('d:vault/Proyecto Cortex.md', 'u:laura-gomez', 'mentions') in g.edges
    assert 'x:laura-gomez' not in g.nodes
    assert ('d:vault/Diario.md', 'x:ml', 'mentions') in g.edges


def test_documents_mail_calendar_and_issues(tmp_path, monkeypatch):
    docs = {
        'mail/box.mbox': {'title': 'box', 'text': 'x', 'messages': [
            {'subject': 'Grafo', 'from': 'Laura Gomez <LAURA@example.com>', 'to': 'Ana <ana@example.com>', 'date': '2024-03-12T10:00:00',
             'text': 'Hola Ana, hablemos del grafo de conocimiento.', 'line': 1},
            {'subject': '', 'from': 'laura@example.com', 'to': 'pedro@example.com', 'date': '', 'text': 'Nota breve.', 'line': 9}]},
        'cal/agenda.ics': {'title': 'agenda', 'text': 'Reunión', 'events': [
            {'title': 'Reunión de grafo', 'when': '2025-03-12T10:00:00Z', 'until': '2025-03-12T11:00:00Z', 'where': 'Sala 1',
             'attendees': ['Laura Gómez', 'laura@example.com'], 'line': 3},
            {'title': 'Reunión de grafo', 'when': '2025-03-12', 'until': '', 'where': '', 'attendees': [], 'line': 9},
            {'title': 'Sin fecha', 'when': '', 'until': '', 'where': '', 'attendees': [], 'line': 12}]},
        'docs/informe.txt': {'title': 'Informe', 'text': 'Informe para Laura Gómez sobre el grafo de conocimiento.',
                             'tags': ['informe'], 'links': ['../cal/agenda.ics', 'https://example.com']},
    }
    for rel in list(docs) + ['docs/escaneo.pdf', 'requirements.txt']:
        write(tmp_path, rel, 'x')
    monkeypatch.setattr(content, 'importers', fake_importers({}))
    monkeypatch.setattr(content, 'documents', fake_documents(dict(docs, **{'requirements.txt': {'text': 'Laura Gómez'}})))
    monkeypatch.setattr(content.importlib.util, 'find_spec', lambda name: None)
    g, issues, _ = build(tmp_path)
    assert g.nodes['d:mail/box.mbox#1']['name'] == 'Grafo' and g.nodes['d:mail/box.mbox#2']['name'] == '(sin asunto)'
    assert g.nodes['d:mail/box.mbox#1']['end'] == 8 and g.nodes['d:mail/box.mbox#1']['when'] == '2024-03-12'
    assert ('d:mail/box.mbox', 'd:mail/box.mbox#1', 'contains') in g.edges
    laura = g.nodes['u:laura-gomez']
    assert laura['email'] == 'laura@example.com' and 'u:laura@example.com' not in g.nodes
    assert ('d:mail/box.mbox#2', 'u:laura-gomez', 'mentions') in g.edges
    assert ('d:mail/box.mbox#2', 'u:pedro@example.com', 'mentions') in g.edges
    first, second = 'w:2025-03-12:reunion-de-grafo', 'w:2025-03-12:reunion-de-grafo-2'
    assert g.nodes[first]['kind'] == 'event' and g.nodes[first]['until'] == '2025-03-12T11:00:00Z'
    assert g.nodes[first]['when'] == '2025-03-12T10:00:00Z' and second in g.nodes
    assert not any('sin-fecha' in n for n in g.nodes)
    assert ('u:laura-gomez', first, 'attends') in g.edges and ('d:cal/agenda.ics', first, 'contains') in g.edges
    assert ('d:docs/informe.txt', 'd:cal/agenda.ics', 'links') in g.edges
    assert ('d:docs/informe.txt', 'u:laura-gomez', 'mentions') in g.edges
    assert g.nodes['x:informe']['tag'] is True
    assert {'file': 'docs/escaneo.pdf', 'error': 'instala cortex-graph[docs] para leer PDF'} in issues.items


def test_code_modules_are_not_reparsed(tmp_path, monkeypatch):
    write(tmp_path, 'requirements.txt', 'x')
    write(tmp_path, 'page.html', '<p>{{ name }}</p>')
    monkeypatch.setattr(content, 'importers', fake_importers({}))
    monkeypatch.setattr(content, 'documents', fake_documents({'requirements.txt': {'text': 'Laura Gómez dijo hola'},
                                                              'page.html': {'text': 'Laura Gómez dijo hola'}}))
    g, issues = Graph(), Issues()
    g.node('m:requirements.txt', kind='module', name='requirements.txt', file='requirements.txt', line=1)
    g.node('m:page.html', kind='module', name='page.html', file='page.html', line=1)
    content.link_content(tmp_path, ['page.html', 'requirements.txt'], g, issues, read_source)
    assert set(g.nodes) == {'m:requirements.txt', 'm:page.html'}


def test_mentions_are_capped(tmp_path, monkeypatch):
    names = ['Laura Gómez', 'Pedro Pérez', 'Carlos Ruiz', 'Sofía Herrera', 'Andrés Mejía']
    text = ' '.join(f'Hablé con {n}.' * (i + 1) for i, n in enumerate(names))
    write(tmp_path, 'a.txt', 'x')
    monkeypatch.setattr(content, 'importers', fake_importers({}))
    monkeypatch.setattr(content, 'documents', fake_documents({'a.txt': {'title': 'a', 'text': text}}))
    monkeypatch.setattr(content, 'MAX_MENTIONS', 2)
    g, _, _ = build(tmp_path)
    assert {b for (a, b, k) in g.edges if k == 'mentions'} == {'u:andres-mejia', 'u:sofia-herrera'}
    assert all(f'u:{n}' in g.nodes for n in ('laura-gomez', 'pedro-perez', 'carlos-ruiz'))


def test_output_is_deterministic(chats):
    g1, _, r1 = build(chats)
    g2, _, r2 = build(chats)
    assert list(g1.nodes.items()) == list(g2.nodes.items())
    assert sorted(g1.edges.items()) == sorted(g2.edges.items())
    assert r1 == r2


def test_large_export_is_fast(tmp_path, monkeypatch):
    words = 'grafo memoria proyecto viaje cocina servidor datos cliente informe campaña diseño equipo'.split()
    convs = []
    for c in range(300):
        msgs = []
        for i in range(20):
            if i % 2 == 0:
                text = f'Hablé con Laura Gómez sobre el {words[(c + i) % 12]} del {words[(c * 3 + i) % 12]}. Vivo en Bogotá.'
                msgs.append(message(i, 'user', 'user', text, f'2024-01-{1 + c % 28:02d}T10:{i:02d}:00Z'))
            else:
                msgs.append(message(i, 'assistant', 'assistant', ('El ' + ' y el '.join(words) + '. ') * 30))
        convs.append(chat(str(c), f'Conversación {c}', msgs))
    write(tmp_path, 'big.json', 'x')
    monkeypatch.setattr(content, 'importers', fake_importers({'big.json': ('chatgpt', convs)}))
    monkeypatch.setattr(content, 'documents', fake_documents({}))
    t = time.perf_counter()
    g, _, records = build(tmp_path, ['big.json'])
    assert time.perf_counter() - t < 8
    assert sum(1 for m in g.nodes.values() if m['kind'] == 'conversation') == 300
    assert sum(1 for m in g.nodes.values() if m['kind'] == 'concept') <= content.MAX_CONCEPTS
    related = [e for e in g.edges if e[2] == 'related']
    degree = {}
    for a, b, _ in related:
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1
    assert all(d <= content.MAX_RELATED for d in degree.values())
    assert all(a < b for a, b, _ in related)
    assert records


def test_with_real_parsers(tmp_path):
    pytest.importorskip('cortex_graph.importers')
    pytest.importorskip('cortex_graph.documents')
    export = [{'title': 'Plan de viaje', 'create_time': 1700000000, 'update_time': 1700000500, 'id': 'c1', 'conversation_id': 'c1',
               'current_node': 'n2', 'mapping': {
                   'n1': {'id': 'n1', 'parent': None, 'children': ['n2'], 'message': {
                       'author': {'role': 'user'}, 'create_time': 1700000000,
                       'content': {'content_type': 'text', 'parts': ['Me llamo Ana y vivo en Bogotá. Hablé con Laura Gómez.']}}},
                   'n2': {'id': 'n2', 'parent': 'n1', 'children': [], 'message': {
                       'author': {'role': 'assistant'}, 'create_time': 1700000100,
                       'content': {'content_type': 'text', 'parts': ['Pregúntale a Roberto Díaz.']}}}}}]
    write(tmp_path, 'chat/conversations.json', json.dumps(export))
    write(tmp_path, 'chat/whatsapp.txt', """
        12/03/2024, 10:15 - Ana: Hola Pedro! me encanta el cine coreano
        12/03/2024, 10:16 - Pedro Pérez: Sí, con Laura Gómez
        12/03/2024, 10:17 - Ana: Perfecto
        """)
    write(tmp_path, 'cal/agenda.ics', """
        BEGIN:VCALENDAR
        BEGIN:VEVENT
        SUMMARY:Reunión de grafo
        DTSTART:20250312T100000Z
        DTEND:20250312T110000Z
        ATTENDEE;CN=Laura Gómez:mailto:laura@example.com
        END:VEVENT
        END:VCALENDAR
        """)
    write(tmp_path, 'mail/hilo.eml', """
        From: Laura Gomez <laura@example.com>
        To: Ana <ana@example.com>
        Subject: Grafo de conocimiento
        Date: Tue, 12 Mar 2024 10:00:00 +0000

        Hola Ana, te comparto notas.
        """)
    write(tmp_path, 'notas/Idea.md', '# Idea\n\nHablar con Laura Gómez del [[Plan]].\n')
    g, issues, records = build(tmp_path)
    assert g.nodes['k:chat/conversations.json#c1']['source'] == 'chatgpt'
    assert g.nodes['k:chat/whatsapp.txt#0']['source'] == 'whatsapp'
    assert g.nodes['u:ana']['owner'] is True and g.nodes['u:ana']['email'] == 'ana@example.com'
    assert g.nodes['u:laura-gomez']['email'] == 'laura@example.com'
    assert 'u:roberto-diaz' not in g.nodes
    assert any(n.startswith('w:2025-03-12:') for n in g.nodes)
    assert ('d:notas/Idea.md', 'u:laura-gomez', 'mentions') in g.edges and 'x:plan' in g.nodes
    attrs = {r['attribute']: r['value'] for r in records}
    assert attrs['name'] == 'Ana' and attrs['lives_in'] == 'Bogotá' and attrs['pref:cine-coreano'] == 'love'
    assert issues.items == []


def test_owner_merges_and_relationship_resolves(tmp_path):
    pytest.importorskip('cortex_graph.importers')
    write(tmp_path, 'wa/Chat con Laura.txt', """
        12/03/2024, 10:15 - Jonathan: Hola Laura
        12/03/2024, 10:16 - Laura: Hola!
        12/03/2024, 10:17 - Jonathan: Laura, ya no vivo en Medellín, me fui a vivir a Bogotá
        12/03/2024, 10:18 - Jonathan: Mi esposa Ana te manda saludos
        """)
    export = [{'title': 'x', 'id': 'c1', 'conversation_id': 'c1', 'create_time': 1700000000, 'current_node': 'n1', 'mapping': {
        'n1': {'id': 'n1', 'parent': None, 'children': [], 'message': {
            'author': {'role': 'user'}, 'create_time': 1700000000,
            'content': {'content_type': 'text', 'parts': ['Vivo en Medellín.']}}}}}]
    write(tmp_path, 'chat/conversations.json', json.dumps(export))
    write(tmp_path, 'notas/Familia.md', '# Familia\n\nCena con Ana Gómez el domingo.\n')
    g, _, records = build(tmp_path)
    owners = [n for n, m in g.nodes.items() if m.get('owner')]
    assert owners == ['u:jonathan'] and 'user' in g.nodes['u:jonathan']['aliases']
    assert ('k:chat/conversations.json#c1', 'u:jonathan', 'participant') in g.edges
    assert 'u:user' not in g.nodes and 'u:ana' not in g.nodes
    wife = next(r for r in records if r['attribute'] == 'relationship:wife')
    assert wife['value'] == 'Ana Gómez' and wife['about'] == ['Ana Gómez'] and 'Ana' in g.nodes['u:ana-gomez']['aliases']
    lives = [r for r in records if r['attribute'] == 'lives_in']
    assert [r['value'] for r in lives] == ['Medellín', 'Bogotá']
    assert lives[1]['supersedes'] == [lives[0]['id']] and lives[0]['valid_to'] == lives[1]['valid_from']
