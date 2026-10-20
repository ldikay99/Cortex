import json

from cortex_graph import importers


def write(tmp_path, rel, content):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content if isinstance(content, str) else json.dumps(content), encoding='utf-8')
    return rel


def head(tmp_path, rel):
    return (tmp_path / rel).read_bytes()[:65536]


def chatgpt_export():
    mapping = {
        'root': {'id': 'root', 'parent': None, 'children': ['a'], 'message': None},
        'a': {'id': 'a', 'parent': 'root', 'children': ['b'], 'message': {'author': {'role': 'system'}, 'create_time': 1, 'content': {'content_type': 'text', 'parts': ['sys']}}},
        'b': {'id': 'b', 'parent': 'a', 'children': ['c', 'd'], 'message': {'author': {'role': 'user'}, 'create_time': 1700000000, 'content': {'content_type': 'text', 'parts': ['Hola, me llamo Ana']}}},
        'c': {'id': 'c', 'parent': 'b', 'children': [], 'message': {'author': {'role': 'assistant'}, 'create_time': 1700000010, 'content': {'content_type': 'text', 'parts': ['rama vieja']}}},
        'd': {'id': 'd', 'parent': 'b', 'children': ['e'], 'message': {'author': {'role': 'assistant'}, 'create_time': 1700000020, 'content': {'content_type': 'multimodal_text', 'parts': [{'content_type': 'image_asset_pointer'}, {'text': 'Mucho gusto'}, '']}}},
        'e': {'id': 'e', 'parent': 'd', 'children': [], 'message': {'author': {'role': 'tool'}, 'create_time': 1700000030, 'content': {'content_type': 'text', 'parts': ['tool out']}}},
    }
    return [{'id': 'conv1', 'title': 'Saludo', 'create_time': 1700000000, 'update_time': 1700000030, 'current_node': 'e', 'mapping': mapping}]


def test_chatgpt(tmp_path):
    rel = write(tmp_path, 'conversations.json', chatgpt_export())
    assert importers.detect(rel, head(tmp_path, rel)) == 'chatgpt'
    convs = importers.load(str(tmp_path), rel)
    assert len(convs) == 1
    c = convs[0]
    assert c['id'] == 'conv1' and c['title'] == 'Saludo' and c['source'] == 'chatgpt'
    assert [m['text'] for m in c['messages']] == ['Hola, me llamo Ana', 'Mucho gusto']
    assert [m['role'] for m in c['messages']] == ['user', 'assistant']
    assert c['messages'][0]['time'] == '2023-11-14T22:13:20Z'
    assert c['started'] == '2023-11-14T22:13:20Z'
    assert importers.user_names(convs) == {'user'}


def test_claude(tmp_path):
    data = [{'uuid': 'u1', 'name': 'Plan', 'created_at': '2024-01-02T03:04:05.000000Z', 'updated_at': '2024-01-02T03:10:00Z', 'chat_messages': [
        {'sender': 'human', 'text': 'hola', 'created_at': '2024-01-02T03:04:05Z', 'content': [{'type': 'text', 'text': 'hola mundo'}]},
        {'sender': 'assistant', 'text': 'respuesta', 'created_at': '2024-01-02T03:05:00Z', 'content': []},
    ]}]
    rel = write(tmp_path, 'claude/conversations.json', data)
    assert importers.detect(rel, head(tmp_path, rel)) == 'claude'
    c = importers.load(str(tmp_path), rel)[0]
    assert c['title'] == 'Plan' and c['started'] == '2024-01-02T03:04:05Z'
    assert [(m['role'], m['text']) for m in c['messages']] == [('user', 'hola mundo'), ('assistant', 'respuesta')]


def test_claude_code(tmp_path):
    lines = [
        {'type': 'summary', 'summary': 'x'},
        {'type': 'user', 'sessionId': 's1', 'cwd': '/p', 'timestamp': '2025-05-01T10:00:00.000Z', 'message': {'role': 'user', 'content': 'arregla el bug'}},
        {'type': 'assistant', 'sessionId': 's1', 'timestamp': '2025-05-01T10:00:05.000Z', 'message': {'role': 'assistant', 'content': [{'type': 'thinking', 'thinking': 'hm'}, {'type': 'text', 'text': 'Listo'}, {'type': 'tool_use', 'name': 'x'}]}},
        {'type': 'user', 'sessionId': 's1', 'isMeta': True, 'message': {'role': 'user', 'content': 'meta'}},
        {'type': 'user', 'sessionId': 's1', 'message': {'role': 'user', 'content': [{'type': 'tool_result', 'content': 'out'}]}},
        {'type': 'assistant', 'sessionId': 's1', 'isSidechain': True, 'message': {'role': 'assistant', 'content': 'side'}},
    ]
    rel = write(tmp_path, 'proj/s1.jsonl', '\n'.join(json.dumps(x) for x in lines) + '\n')
    assert importers.detect(rel, head(tmp_path, rel)) == 'claude-code'
    c = importers.load(str(tmp_path), rel)[0]
    assert c['id'] == 's1' and len(c['messages']) == 2
    assert [m['line'] for m in c['messages']] == [2, 3]
    assert c['messages'][1]['text'] == 'Listo'
    assert c['title'] == 'arregla el bug'


def test_whatsapp_android_es(tmp_path):
    txt = (
        '12/03/24, 14:05 - Los mensajes y llamadas están cifrados de extremo a extremo.\n'
        '12/03/24, 14:06 - Ana: Hola\n'
        'cómo estás?\n'
        '13/03/24, 09:00 - Luis: <Multimedia omitido>\n'
        '13/03/24, 09:01 - Luis: Bien, gracias\n'
        '13/03/24, 21:30 - Ana: Nos vemos mañana\n'
    )
    rel = write(tmp_path, 'Chat de WhatsApp con Luis.txt', txt)
    assert importers.detect(rel, head(tmp_path, rel)) == 'whatsapp'
    c = importers.load(str(tmp_path), rel)[0]
    assert [m['author'] for m in c['messages']] == ['Ana', 'Luis', 'Ana']
    assert c['messages'][0]['text'] == 'Hola\ncómo estás?'
    assert c['messages'][0]['line'] == 2
    assert c['messages'][0]['time'] == '2024-03-12T14:06:00'
    assert c['participants'] == ['Ana', 'Luis']
    assert importers.user_names([c]) == {'Ana'}


def test_whatsapp_ios_en_12h(tmp_path):
    txt = (
        '[3/25/24, 1:05:09 PM] Bob: Hi there\n'
        '[3/25/24, 1:06:00 PM] Bob: ‎<Media omitted>\n'
        '[3/25/24, 11:59:00 PM] Eve: See you\n'
    )
    rel = write(tmp_path, 'chat.txt', txt)
    assert importers.detect(rel, head(tmp_path, rel)) == 'whatsapp'
    c = importers.load(str(tmp_path), rel)[0]
    assert len(c['messages']) == 2
    assert c['messages'][0]['time'] == '2024-03-25T13:05:09'
    assert c['messages'][1]['time'] == '2024-03-25T23:59:00'


def test_telegram(tmp_path):
    data = {'name': 'Grupo', 'type': 'private_group', 'id': 7, 'messages': [
        {'id': 1, 'type': 'service', 'date': '2024-01-01T10:00:00', 'actor': 'Ana', 'text': ''},
        {'id': 2, 'type': 'message', 'date': '2024-01-01T10:01:00', 'from': 'Ana', 'from_id': 'user1', 'text': 'hola'},
        {'id': 3, 'type': 'message', 'date': '2024-01-01T10:02:00', 'from': 'Pepe', 'from_id': 'user2', 'text': ['ver ', {'type': 'link', 'text': 'http://x.y'}]},
    ]}
    rel = write(tmp_path, 'result.json', data)
    assert importers.detect(rel, head(tmp_path, rel)) == 'telegram'
    c = importers.load(str(tmp_path), rel)[0]
    assert c['title'] == 'Grupo' and [m['text'] for m in c['messages']] == ['hola', 'ver http://x.y']


def test_discord(tmp_path):
    data = {'guild': {'name': 'G'}, 'channel': {'id': '5', 'name': 'general'}, 'messages': [
        {'id': '1', 'type': 'Default', 'timestamp': '2024-02-02T10:00:00.000+01:00', 'content': 'hey', 'author': {'name': 'neo', 'nickname': 'Neo'}},
        {'id': '2', 'type': 'Default', 'timestamp': '2024-02-02T10:01:00.000+01:00', 'content': '', 'author': {'name': 'trin'}},
    ]}
    rel = write(tmp_path, 'general.json', data)
    assert importers.detect(rel, head(tmp_path, rel)) == 'discord'
    c = importers.load(str(tmp_path), rel)[0]
    assert c['title'] == 'G / general' and len(c['messages']) == 1
    assert c['messages'][0]['author'] == 'Neo' and c['messages'][0]['time'] == '2024-02-02T09:00:00Z'


def test_slack_folder(tmp_path):
    write(tmp_path, 'slack/channels.json', [{'id': 'C1', 'name': 'general'}, {'id': 'C2', 'name': 'vacio'}])
    write(tmp_path, 'slack/users.json', [{'id': 'U1', 'name': 'ana', 'real_name': 'Ana Gómez'}])
    write(tmp_path, 'slack/general/2024-01-01.json', [{'type': 'message', 'user': 'U1', 'text': 'hola <@U1>', 'ts': '1704103200.000100'}, {'type': 'message', 'subtype': 'channel_join', 'user': 'U1', 'text': 'joined', 'ts': '1704103201.000100'}])
    write(tmp_path, 'slack/general/2024-01-02.json', [{'type': 'message', 'user': 'U9', 'text': 'otro', 'ts': '1704189600.000100'}])
    assert importers.detect('slack/channels.json', head(tmp_path, 'slack/channels.json')) == 'slack'
    assert importers.detect('slack/general/2024-01-01.json', head(tmp_path, 'slack/general/2024-01-01.json')) == 'slack'
    convs = importers.load(str(tmp_path), 'slack/channels.json')
    assert len(convs) == 1
    c = convs[0]
    assert c['title'] == '#general' and [m['author'] for m in c['messages']] == ['Ana Gómez', 'U9']
    assert c['messages'][0]['text'] == 'hola @Ana Gómez'
    assert importers.load(str(tmp_path), 'slack/general/2024-01-01.json') == []


def test_srt_and_vtt(tmp_path):
    srt = '1\n00:00:01,000 --> 00:00:03,000\nAna: Buenos días\n\n2\n00:00:04,000 --> 00:00:06,000\nBienvenidos\na todos\n'
    rel = write(tmp_path, 'reunion.srt', srt)
    assert importers.detect(rel, head(tmp_path, rel)) == 'srt'
    c = importers.load(str(tmp_path), rel)[0]
    assert [(m['author'], m['text'], m['line']) for m in c['messages']] == [('Ana', 'Buenos días', 1), ('', 'Bienvenidos a todos', 5)]
    vtt = 'WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n<v Luis>Hola equipo</v>\n'
    rel = write(tmp_path, 'm.vtt', vtt)
    assert importers.detect(rel, head(tmp_path, rel)) == 'vtt'
    c = importers.load(str(tmp_path), rel)[0]
    assert c['messages'][0]['author'] == 'Luis' and c['messages'][0]['text'] == 'Hola equipo'


def test_generic_json_jsonl_markdown(tmp_path):
    rel = write(tmp_path, 'chat.json', [{'role': 'user', 'content': 'hola'}, {'role': 'assistant', 'content': [{'type': 'text', 'text': 'qué tal'}]}])
    assert importers.detect(rel, head(tmp_path, rel)) == 'generic'
    c = importers.load(str(tmp_path), rel)[0]
    assert [m['role'] for m in c['messages']] == ['user', 'assistant'] and c['messages'][1]['text'] == 'qué tal'
    rel = write(tmp_path, 'chat.jsonl', json.dumps({'role': 'user', 'content': 'uno'}) + '\n\nnot json\n' + json.dumps({'role': 'assistant', 'content': 'dos'}) + '\n')
    assert importers.detect(rel, head(tmp_path, rel)) == 'generic'
    c = importers.load(str(tmp_path), rel)[0]
    assert [m['line'] for m in c['messages']] == [1, 4]
    md = '**User:** Hola\ncómo vas\n\n**Assistant:** Bien\n\n## User\nUna pregunta\n'
    rel = write(tmp_path, 'log.md', md)
    assert importers.detect(rel, head(tmp_path, rel)) == 'generic'
    c = importers.load(str(tmp_path), rel)[0]
    assert [(m['role'], m['line']) for m in c['messages']] == [('user', 1), ('assistant', 4), ('user', 6)]
    assert c['messages'][0]['text'] == 'Hola\ncómo vas'


def test_detect_negative(tmp_path):
    assert importers.detect('notes.txt', b'solo una nota\nsin formato\n') is None
    assert importers.detect('data.json', b'{"a": 1}') is None
    assert importers.detect('README.md', b'# Titulo\n\nUser is a word here\n') is None
    assert importers.load(str(tmp_path), 'missing.json', 'chatgpt') == []


def test_caps(tmp_path, monkeypatch):
    monkeypatch.setattr(importers, 'MAX_MESSAGES', 3)
    rel = write(tmp_path, 'big.jsonl', '\n'.join(json.dumps({'role': 'user', 'content': 'm%d' % i}) for i in range(10)))
    assert len(importers.load(str(tmp_path), rel)[0]['messages']) == 3
