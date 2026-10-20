import time

from cortex_graph import extract

NOTE = """# Reunión de planificación

El lunes hablé con Laura Gómez sobre el grafo de conocimiento. Laura dijo que el grafo de conocimiento es clave.
Hoy Bogotá amaneció fría. Python es genial y Machine Learning también. Santa Marta es bonita.
Mi jefe Carlos Ruiz pidió el informe. Enero fue duro. Gracias Sofía por todo.
Escríbeme a Laura@Example.com o visita https://example.com/page#frag, ver #proyecto/cortex #ideas #fff #123 @dikay.
Ver [[Notas de IA|notas]], [[Plan#Fechas]] y ![[diagrama.png]].
```
Pedro Infante = "no es persona aquí"
```
"""


def msg(i, text, role='user', author='user', time='2024-01-05T10:00:00Z'):
    return {'i': i, 'role': role, 'author': author, 'time': time, 'text': text, 'line': i + 1}


def conv(*texts, **kw):
    return {'node': 'k:chat.json#1', 'messages': [msg(i, t, **kw) for i, t in enumerate(texts)]}


def by_attr(records):
    return {r['attribute']: r for r in records}


def test_keys_are_accent_and_case_insensitive():
    assert extract.key('María José  Pérez') == 'maria-jose-perez'
    assert extract.key('ÁNGEL') == extract.key('angel')
    assert extract.concept_key('Grafos de Conocimiento') == 'grafo-de-conocimiento'
    assert extract.concept_key('ciudades') == 'ciudad'
    assert extract.slug('¿Qué es Córtex?') == 'que-es-cortex'
    assert extract.slug('!!!') == 'seccion'
    assert extract.normalize('  Vivo en  BOGOTÁ! ') == 'vivo en bogota'
    rid = extract.memory_id('Vivo en Bogotá.')
    assert rid == extract.memory_id('vivo en bogota') and len(rid) == 12 and int(rid, 16) >= 0


def test_people_are_precise():
    people = extract.entities(NOTE)['people']
    assert 'Laura Gómez' in people and 'Carlos Ruiz' in people and 'Sofía' in people
    for wrong in ('Laura', 'Bogotá', 'Python', 'Machine Learning', 'Santa Marta', 'Marta', 'Enero', 'Hoy', 'El', 'Gracias',
                  'Pedro Infante', 'Reunión'):
        assert wrong not in people
    assert people[0] == 'Laura Gómez'


def test_people_need_evidence_for_unknown_names():
    text = 'Ayer conversé con Wilfrido. Kwame Nkrumah lideró el país. Luego Kwame Nkrumah habló. Nuevo Plan Estratégico.'
    people = extract.entities(text)['people']
    assert 'Wilfrido' in people and 'Kwame Nkrumah' in people
    assert not any('Plan' in p for p in people)
    assert extract.entities('Nos vemos en Florencia para hablar de Valencia.')['people'] == []
    assert extract.entities('Lunes. Martes y Miércoles con Mayo de 2024.')['people'] == []
    english = extract.entities('Yesterday I met with Jennifer Smith and told Robert about the Project Plan.')['people']
    assert 'Jennifer Smith' in english and 'Robert' in english and 'Project Plan' not in english


def test_titles_and_surnames():
    text = ('Project Manager Sarah Connor aprobó. Director General habló. La profesora Martínez explicó. '
            'Según García Márquez, todo cambia. Fui a la Universidad Nacional y al Banco de Bogotá.')
    people = extract.entities(text)['people']
    assert {'Sarah Connor', 'Martínez', 'García Márquez'} <= set(people)
    assert not any(w in p for p in people for w in ('General', 'Universidad', 'Nacional', 'Banco', 'Project'))


def test_speaker_labels_and_greetings():
    text = 'Marcela: hola, ¿cómo vas?\nHola Wendolyn, todo bien.\nAsunto: informe\nFecha: hoy'
    people = extract.entities(text)['people']
    assert 'Marcela' in people and 'Wendolyn' in people
    assert 'Asunto' not in people and 'Fecha' not in people


def test_links_tags_and_contacts():
    found = extract.entities(NOTE)
    assert found['tags'] == ['ideas', 'proyecto/cortex'] or sorted(found['tags']) == ['ideas', 'proyecto/cortex']
    assert found['wikilinks'] == ['Notas de IA', 'Plan', 'diagrama.png']
    assert found['mentions'] == ['dikay']
    assert found['emails'] == ['laura@example.com']
    assert found['urls'] == ['https://example.com/page#frag']
    raw = extract.scan('[[Nota|Alias]] y [[#Encabezado]] y [[Otra#Sección|ver]]')['wikilinks']
    assert [(t, h, a) for t, h, a, _ in raw] == [('Nota', '', 'Alias'), ('', 'Encabezado', ''), ('Otra', 'Sección', 'ver')]
    assert extract.entities('color #fff y #a1b2c3 y #[[Tema Largo]] y url.com/a#b')['tags'] == ['Tema Largo']


def test_dates_in_many_formats():
    text = ('Fechas: 12 de marzo de 2025, 2025-04-01T10:00, 03/05/2024, 05/23/2024, March 12, 2025, 7th of June 2023, '
            'el 1º de enero del 2024, marzo 2025, setiembre de 2022, 31/02/2024, 2024-13-01, mañana y el próximo lunes.')
    assert extract.entities(text)['dates'] == [
        '2022-09', '2023-06-07', '2024-01-01', '2024-05-03', '2024-05-23', '2025-03', '2025-03-12', '2025-04-01']
    assert extract.entities('sin fechas, solo 1234 y 12/12')['dates'] == []


def test_keyphrases_rank_multiword_topics():
    text = ('El grafo de conocimiento une notas. La memoria personal guarda hechos. El grafo de conocimiento crece '
            'con la memoria personal. Las notas del grafo de conocimiento. ') * 40
    concepts = extract.entities(text)['concepts']
    assert concepts[0] == 'grafo de conocimiento'
    assert 'memoria personal' in concepts and len(concepts) <= 12
    assert all(c.split()[0] not in extract.STOP for c in concepts)
    assert extract.entities(text) == extract.entities(text)


def test_concepts_exclude_people_and_code():
    text = ('Laura Gómez revisó la arquitectura hexagonal. La arquitectura hexagonal funciona. '
            '```\nfunction_name variable_name arquitectura_mala\n```\n') * 5
    concepts = extract.entities(text)['concepts']
    assert 'arquitectura hexagonal' in concepts
    assert not any('laura' in c or 'gómez' in c or '_' in c for c in concepts)


def test_spanish_identity_facts():
    found = extract.facts(conv('Hola! Me llamo Ana María y vivo en Bogotá, Colombia. Trabajo en Acme Corp como ingeniera de datos.',
                               'Tengo 34 años y soy de Cali.'))
    attrs = by_attr(found)
    assert attrs['name']['value'] == 'Ana María' and attrs['name']['category'] == 'identity'
    assert attrs['lives_in']['value'] == 'Bogotá'
    assert attrs['works_at']['value'] == 'Acme Corp'
    assert attrs['job_title']['value'] == 'ingeniera de datos'
    assert attrs['age']['value'] == '34' and attrs['from']['value'] == 'Cali'
    rec = attrs['lives_in']
    assert rec['origin'] == 'rule' and rec['subject'] == 'user' and rec['source'] == 'k:chat.json#1' and rec['msg'] == 0
    assert rec['when'] == '2024-01-05' and rec['valid_from'] == '2024-01-05T10:00:00Z' and rec['valid_to'] is None
    assert 0.5 <= rec['confidence'] <= 0.8 and rec['sensitive'] is False and len(rec['id']) == 12
    assert rec['text'] == 'Me llamo Ana María y vivo en Bogotá, Colombia.' and rec['doc'] == rec['text']


def test_preferences_with_negation():
    found = extract.facts(conv('Me encanta el café y el chocolate, pero no me gusta el té.', 'Odio madrugar.',
                               'Prefiero el té verde al café.', 'Ya no me gusta el reguetón.'))
    prefs = {r['object']: r['value'] for r in found if r['category'] == 'preference'}
    assert prefs == {'café': 'love', 'chocolate': 'love', 'té': 'dislike', 'madrugar': 'hate', 'té verde': 'prefer',
                     'reguetón': 'dislike'}
    attrs = {r['attribute'] for r in found}
    assert 'pref:cafe' in attrs and 'pref:te' in attrs


def test_instructions_for_assistants():
    found = extract.facts(conv('Siempre respóndeme en español.', 'No uses emojis.', 'De ahora en adelante sé breve.',
                               'Prefiero que me hables de tú.', 'Always answer briefly.', "Don't use markdown tables.",
                               'No uses esa función en este archivo.'))
    inst = [r for r in found if r['category'] == 'instruction']
    assert [r['text'] for r in inst] == ['Siempre respóndeme en español.', 'No uses emojis.', 'De ahora en adelante sé breve.',
                                         'Prefiero que me hables de tú.', 'Always answer briefly.', "Don't use markdown tables."]
    assert inst[1]['attribute'] == 'instruction:emojis'


def test_habits_goals_decisions_relationships():
    found = extract.facts(conv('Todos los días corro 5 km.', 'Nunca como carne.', 'Mi meta es aprender japonés este año.',
                               'Quiero mudarme a Lisboa.', 'Decidimos usar PostgreSQL para el backend.',
                               'Mi esposa se llama Laura y mi hermano Pedro vive en Cali.', 'Juan es mi jefe.',
                               'Estoy aprendiendo Rust.', 'Hablo inglés y francés.', 'Estoy trabajando en Cortex, un grafo.'))
    cats = [(r['category'], r['attribute'], r['value']) for r in found]
    assert ('habit', 'habit:corro-km', 'Todos los días corro 5 km') in cats
    assert any(c == 'habit' and 'carne' in v for c, _, v in cats)
    assert ('goal', 'goal:aprender-japon', 'aprender japonés') in [(c, a, v) for c, a, v in cats if c == 'goal'] or \
        any(a.startswith('goal:aprender') for c, a, v in cats)
    assert any(c == 'goal' and 'Lisboa' in v for c, _, v in cats)
    assert any(c == 'decision' and 'PostgreSQL' in v for c, _, v in cats)
    rel = {a: v for c, a, v in cats if c == 'relationship'}
    assert rel == {'relationship:wife': 'Laura', 'relationship:brother:pedro': 'Pedro', 'relationship:boss': 'Juan'}
    assert any(c == 'skill' and a.startswith('learning:') and v == 'Rust' for c, a, v in cats)
    assert any(c == 'skill' and a.startswith('speaks:') for c, a, v in cats)
    project = next(r for r in found if r['category'] == 'project')
    assert project['about'] == ['Cortex']
    wife = next(r for r in found if r['attribute'] == 'relationship:wife')
    assert wife['about'] == ['Laura']


def test_english_facts():
    found = extract.facts(conv("I'm a software engineer and I live in Berlin.", 'I love hiking and reading.', "I don't like spam.",
                               'My wife is Sarah.', 'I always wake up at 6.', 'We decided to use React.',
                               'My goal is to run a marathon.', 'My name is John Smith.', 'I work at Initech.'))
    attrs = by_attr(found)
    assert attrs['lives_in']['value'] == 'Berlin' and attrs['job_title']['value'] == 'software engineer'
    assert attrs['pref:hiking']['value'] == 'love' and attrs['pref:spam']['value'] == 'dislike'
    assert attrs['relationship:wife']['value'] == 'Sarah'
    assert attrs['name']['value'] == 'John Smith' and attrs['works_at']['value'] == 'Initech'
    assert any(r['category'] == 'habit' for r in found) and any(r['category'] == 'decision' for r in found)
    assert any(r['category'] == 'goal' and r['value'] == 'run a marathon' for r in found)


def test_noise_is_ignored():
    found = extract.facts({'node': 'k:x#1', 'messages': [
        msg(0, 'Vivo en Marte y me llamo Robot.', role='assistant', author='assistant'),
        msg(1, '¿Vivo en Bogotá?'),
        msg(2, 'Si vivo en Bogotá, ¿qué pasa?'),
        msg(3, 'Traduce: vivo en París y me gusta el vino.'),
        msg(4, 'Escribe un cuento donde el héroe dice que vive en Roma.'),
        msg(5, 'Me llamó la atención eso. Laura trabajó en Google.'),
        msg(6, 'Vivo en una casa pequeña. Trabajo en casa. Mi hermano es ingeniero. I left the meeting early.'),
        msg(7, 'Mi contraseña es hunter2 y me gusta el sushi.'),
        msg(8, '```\nme llamo Variable\n```\n> vivo en Quito\nEl texto "vivo en Lima" es una cita.'),
        msg(9, 'I like it. I love you. I like how you write.'),
    ]})
    assert found == []


def test_negation_and_supersession():
    found = extract.facts({'node': 'k:x#1', 'messages': [
        msg(0, 'Vivo en Bogotá.', time='2023-01-01T00:00:00Z'),
        msg(1, 'Ya no vivo en Bogotá.', time='2024-01-01T00:00:00Z'),
        msg(2, 'Ahora vivo en Medellín.', time='2024-06-01T00:00:00Z'),
        msg(3, 'Vivo en Medellín.', time='2025-01-01T00:00:00Z'),
    ]})
    records = extract.supersede(found)
    first, gone, now, again = records
    assert gone['value'] == '' and gone.get('negated') and gone['object'] == 'Bogotá'
    assert first['valid_to'] == '2024-01-01T00:00:00Z' and gone['supersedes'] == [first['id']]
    assert gone['valid_to'] == '2024-06-01T00:00:00Z' and now['supersedes'] == [gone['id']]
    assert now['valid_to'] is None and again['valid_to'] is None and 'supersedes' not in again


def test_owner_names_select_messages():
    chat = {'node': 'k:wa#0', 'messages': [
        msg(0, 'Vivo en Quito.', role='other', author='Ana'),
        msg(1, 'Vivo en Lima.', role='other', author='Pedro Pérez'),
    ]}
    assert [r['value'] for r in extract.facts(chat, owner_names={'Ana'})] == ['Quito']
    assert extract.facts(chat) == []


def test_remember_events_sensitive_and_hedges():
    found = extract.facts(conv('Recuerda que mi perro se llama Max.', 'Recuérdame llamar al dentista.',
                               'Me casé el 12 de marzo de 2020 con Laura.', 'Creo que me gusta el jazz.',
                               'Tengo diabetes y me gusta el pan integral.'))
    attrs = by_attr(found)
    assert attrs['relationship:dog:max']['value'] == 'Max' and attrs['relationship:dog:max']['confidence'] == 0.8
    note = next(r for r in found if r['category'] == 'fact')
    assert note['value'] == 'llamar al dentista'
    event = next(r for r in found if r['category'] == 'event')
    assert event['when'] == '2020-03-12'
    assert attrs['pref:jazz']['confidence'] == 0.55
    assert attrs['pref:pan-integral']['sensitive'] is True


def test_facts_are_deterministic_and_unique():
    chat = conv('Vivo en Bogotá.', 'Vivo en Bogotá.', 'Me gusta el café y el té.')
    a, b = extract.facts(chat), extract.facts(chat)
    assert a == b
    ids = [r['id'] for r in a]
    assert len(ids) == len(set(ids)) == 3
    assert extract.facts({'messages': [{'role': 'user', 'text': 'Vivo en Lima.'}]}, now='2026-01-01T00:00:00')[0]['valid_from'] == '2026-01-01T00:00:00'


def test_infer_single_text():
    rec = extract.infer('Mi jefa se llama Marta Ruiz')
    assert rec['category'] == 'relationship' and rec['attribute'] == 'relationship:boss' and rec['value'] == 'Marta Ruiz'
    assert extract.infer('hola') is None


def test_scan_is_linear_on_large_text():
    block = ('Hablé con Laura Gómez sobre el grafo de conocimiento y la memoria personal el 12 de marzo de 2025. '
             'Visita https://example.com o escribe a ana@example.com. #ideas [[Plan]] @ana\n')
    small, large = block * 500, block * 4000
    t = time.perf_counter()
    extract.scan(small)
    t_small = time.perf_counter() - t
    t = time.perf_counter()
    found = extract.scan(large)
    t_large = time.perf_counter() - t
    assert 'Laura Gómez' in [p[0] for p in found['people'].values()]
    assert t_large < 5 and t_large < max(t_small, 0.01) * 20
    messages = [msg(i, 'Hola. Necesito ayuda con el informe del proyecto de marketing para el cliente. Vivo en Quito.')
                for i in range(4000)]
    t = time.perf_counter()
    extract.facts({'messages': messages})
    assert time.perf_counter() - t < 5


def test_moves_and_negation_in_one_sentence():
    cases = {
        'Laura, ya no vivo en Medellín, me fui a vivir a Bogotá': 'Bogotá',
        'Me mudé a Cali.': 'Cali', 'Me fui a vivir en Pasto.': 'Pasto', 'Ahora vivo en Quito.': 'Quito',
        'I moved to Lisbon.': 'Lisbon', 'Now I live in Porto.': 'Porto',
    }
    for text, place in cases.items():
        found = [r for r in extract.facts(conv(text)) if r['attribute'] == 'lives_in']
        assert [r['value'] for r in found] == [place], text


def test_continuing_work_forms():
    cases = {
        'Sigo trabajando en Lumen como desarrollador': ('Lumen', 'desarrollador'),
        'Estoy trabajando en Acme como diseñadora.': ('Acme', 'diseñadora'),
        'Trabajo en Lumen como desarrolladora.': ('Lumen', 'desarrolladora'),
        "I'm working at Initech as a developer.": ('Initech', 'developer'),
        'I still work at Initech.': ('Initech', None),
    }
    for text, (org, job) in cases.items():
        attrs = by_attr(extract.facts(conv(text)))
        assert attrs['works_at']['value'] == org, text
        assert (attrs['job_title']['value'] if 'job_title' in attrs else None) == job, text
        assert not any(a.startswith('project:') for a in attrs), text
    assert extract.facts(conv('Trabajo de noche.')) == []


def test_preference_clauses_do_not_leak():
    def prefs(text):
        return sorted((r['attribute'], r['value']) for r in extract.facts(conv(text)))
    assert prefs('Prefiero hoteles pequeños y no me gusta madrugar.') == [('pref:hotel-pequeno', 'prefer'), ('pref:madrugar', 'dislike')]
    assert prefs('Me encanta el café de especialidad, mañana voy a probar uno nuevo') == [('pref:cafe-de-especialidad', 'love')]
    assert prefs('Me gusta el café, el té y la música clásica.') == [
        ('pref:cafe', 'like'), ('pref:musica-clasica', 'like'), ('pref:te', 'like')]


def test_transient_plans_are_not_goals():
    assert extract.facts(conv('Mañana voy a viajar a Lima.')) == []
    assert extract.facts(conv('Hoy quiero aprender a cocinar arroz.')) == []
    goal = extract.facts(conv('Voy a aprender alemán este año.'))
    assert [r['attribute'] for r in goal] == ['goal:aprender-aleman']
    assert any(r['category'] == 'goal' for r in extract.facts(conv('Quiero aprender a nadar por la mañana.')))
