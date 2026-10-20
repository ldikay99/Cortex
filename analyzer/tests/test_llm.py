import json
from types import SimpleNamespace as NS

import pytest

from cortex_graph import llm


def message(memories, stop='end_turn'):
    body = json.dumps({'memories': memories})
    return NS(stop_reason=stop, content=[NS(type='text', text=body)], usage=NS(input_tokens=1, output_tokens=1))


def mem(text, msg=0, **kw):
    base = {'text': text, 'category': 'identity', 'subject': 'user', 'attribute': 'location', 'value': 'Medellin',
            'when': '', 'confidence': 0.9, 'msg': msg, 'sensitive': False}
    base.update(kw)
    return base


class Messages:
    def __init__(self, owner, beta):
        self.owner = owner
        self.beta = beta

    def create(self, **kw):
        self.owner.calls.append(('beta' if self.beta else 'plain', kw))
        return self.owner.reply(kw)


class Batches:
    def __init__(self, owner):
        self.owner = owner
        self.polls = 0

    def create(self, requests):
        self.owner.batch_requests = requests
        return NS(id='b1')

    def retrieve(self, bid):
        self.polls += 1
        return NS(id=bid, processing_status='ended' if self.polls >= 2 else 'in_progress')

    def results(self, bid):
        out = []
        for r in self.owner.batch_requests:
            out.append(NS(custom_id=r['custom_id'], result=NS(type='succeeded', message=self.owner.reply(r['params']))))
        return list(reversed(out))


class Fake:
    def __init__(self, reply=None):
        self.calls = []
        self.batch_requests = None
        self.reply_fn = reply
        self.messages = Messages(self, False)
        self.messages.batches = Batches(self)
        self.beta = NS(messages=Messages(self, True))

    def reply(self, kw):
        if self.reply_fn:
            return self.reply_fn(kw)
        return message([mem('Vive en Medellin', 0)])


def conv(n=2, rel='chat.json', cid='c1', text='Vivo en Medellin'):
    msgs = [{'i': i, 'role': 'user' if i % 2 == 0 else 'assistant', 'author': 'Ana' if i % 2 == 0 else 'Bot',
             'time': f'2025-03-1{i % 9}T10:00:00Z', 'text': text if i % 2 == 0 else 'ok', 'line': 0} for i in range(n)]
    c = {'id': cid, 'source': 'chatgpt', 'title': 'Mudanza', 'started': None, 'ended': None, 'participants': ['Ana', 'Bot'], 'messages': msgs}
    if rel:
        c['rel'] = rel
    return c


@pytest.fixture(autouse=True)
def nosleep(monkeypatch):
    monkeypatch.setattr(llm.time, 'sleep', lambda s: None)


def test_available_without_credentials(monkeypatch, tmp_path):
    for k in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN'):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv('ANTHROPIC_CONFIG_DIR', str(tmp_path / 'none'))
    monkeypatch.setenv('HOME', str(tmp_path))
    ok, reason = llm.available()
    assert not ok and reason
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'x')
    assert llm.available()[0] == (llm.sdk() is not None)


def test_available_profile_dir(monkeypatch, tmp_path):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.delenv('ANTHROPIC_AUTH_TOKEN', raising=False)
    monkeypatch.setenv('ANTHROPIC_CONFIG_DIR', str(tmp_path))
    assert llm.available()[0] == (llm.sdk() is not None)


def test_request_shape_non_batch(monkeypatch):
    monkeypatch.delenv('CORTEX_AI_MODEL', raising=False)
    fake = Fake()
    out = llm.extract_memories([conv()], owner_names={'Ana'}, client=fake)
    kind, kw = fake.calls[0]
    assert kind == 'beta'
    assert kw['model'] == 'claude-opus-5-5'
    assert 'thinking' not in kw
    assert kw['output_config']['effort'] == 'low'
    fmt = kw['output_config']['format']
    assert fmt['type'] == 'json_schema' and fmt['schema'] is llm.SCHEMA
    assert kw['cache_control'] == {'type': 'ephemeral'}
    assert kw['system'] == llm.SYSTEM_PROMPT
    assert out[0]['origin'] == 'ai' and out[0]['source'] == 'k:chat.json#c1' and out[0]['msg'] == 0
    assert out[0]['when'] == '2025-03-10'


def test_betas_and_fallbacks_only_non_batch():
    seen = {}

    class Beta(Messages):
        def create(self, **kw):
            seen.update(kw)
            return super().create(**kw)

    fake = Fake()
    fake.beta = NS(messages=Beta(fake, True))
    llm.extract_memories([conv()], client=fake)
    assert seen['betas'] == ['server-side-fallback-2026-07-01'] and seen['fallbacks'] == 'default'
    fake2 = Fake()
    llm.extract_memories([conv()], client=fake2, batch=True)
    for r in fake2.batch_requests:
        assert 'fallbacks' not in r['params'] and 'betas' not in r['params']


def test_model_override_env(monkeypatch):
    monkeypatch.setenv('CORTEX_AI_MODEL', 'custom-model')
    fake = Fake()
    llm.extract_memories([conv()], client=fake)
    assert fake.calls[0][1]['model'] == 'custom-model'
    fake = Fake()
    llm.extract_memories([conv()], client=fake, model='explicit')
    assert fake.calls[0][1]['model'] == 'explicit'


def test_redaction_and_code_dropped():
    secret = 'sk-' + 'a1B2c3D4' * 4
    text = f'mi clave es {secret}\n```python\nprint("hola")\n```\ntarjeta 4111 1111 1111 1111 y vivo en Cali'
    fake = Fake()
    llm.extract_memories([conv(text=text)], client=fake)
    sent = fake.calls[0][1]['messages'][0]['content']
    assert secret not in sent and '4111 1111' not in sent and 'print(' not in sent
    assert 'vivo en Cali' in sent and '[0]' in sent and '2025-03-10' in sent
    assert 'Conversation: Mudanza' in sent and 'Owner:' in sent


def test_chunking_keeps_whole_messages_with_indexes():
    c = conv(n=40, text='palabra ' * 100)
    chunks = llm.make_chunks([c], {'Ana'}, 3000)
    assert len(chunks) > 1
    seen = [i for ch in chunks for i, _, _ in ch['lines']]
    assert seen == list(range(40))
    for ch in chunks:
        assert len(llm.chunk_text(ch)) <= 3200
        for _, line, _ in ch['lines']:
            assert line.startswith('[')


def test_refusal_skips_chunk_and_reports():
    fake = Fake(lambda kw: message([], 'refusal'))
    issues = []
    assert llm.extract_memories([conv()], client=fake, issues=issues) == []
    assert len(fake.calls) == 1 and 'rechaz' in issues[0]


def test_max_tokens_splits_once():
    state = {'n': 0}

    def reply(kw):
        state['n'] += 1
        if state['n'] == 1:
            return message([], 'max_tokens')
        return message([mem(f'Hecho {state["n"]} distinto', 0)])

    fake = Fake(reply)
    issues = []
    out = llm.extract_memories([conv(n=6)], client=fake, issues=issues)
    assert len(fake.calls) == 3 and len(out) == 2 and not issues


def test_max_tokens_single_message_gives_issue():
    fake = Fake(lambda kw: message([], 'max_tokens'))
    issues = []
    out = llm.extract_memories([conv(n=1)], client=fake, issues=issues)
    assert out == [] and issues


def test_batch_flow_any_order_and_dedup():
    def reply(kw):
        text = kw['messages'][0]['content']
        return message([mem('Vive en Medellin', 0, confidence=0.6 if 'Dos' in text else 0.95)])

    fake = Fake(reply)
    convs = [conv(cid='a', rel='a.json'), conv(cid='b', rel='b.json')]
    progress = []
    out = llm.extract_memories(convs, client=fake, batch=True, on_progress=progress.append)
    assert [r['custom_id'] for r in fake.batch_requests] == ['c0', 'c1']
    assert fake.messages.batches.polls >= 2
    assert len(out) == 1 and out[0]['confidence'] == 0.95
    assert any(p.get('phase') == 'batch' for p in progress)


def test_batch_errored_results_reported():
    class B(Batches):
        def results(self, bid):
            return [NS(custom_id='c0', result=NS(type='errored'))]

    fake = Fake()
    fake.messages.batches = B(fake)
    issues = []
    assert llm.extract_memories([conv()], client=fake, batch=True, issues=issues) == []
    assert issues


def test_parse_records_fields_and_sanitizing():
    fake = Fake(lambda kw: message([
        mem('Es alérgica a las nueces', 0, category='nonsense', when='basura', confidence=7, sensitive=True),
        mem('Tiene un perro llamado Lola', 99),
        mem('', 0),
    ]))
    out = llm.extract_memories([conv(rel=None)], client=fake)
    assert len(out) == 2
    by = {r['text']: r for r in out}
    a = by['Es alérgica a las nueces']
    assert a['category'] == 'fact' and a['confidence'] == 1.0 and a['sensitive'] is True and a['when'] == '2025-03-10'
    assert a['source'] is None and len(a['id']) == 12 and a['doc'] == a['text']
    assert by['Tiene un perro llamado Lola']['msg'] is None


def test_memory_id_normalization():
    assert llm.memory_id('Vive en Medellín.') == llm.memory_id('  vive EN medellin ')
    assert len(llm.memory_id('x')) == 12


def test_invalid_json_reported():
    fake = Fake(lambda kw: NS(stop_reason='end_turn', content=[NS(type='text', text='nope')]))
    issues = []
    assert llm.extract_memories([conv()], client=fake, issues=issues) == []
    assert issues


def test_rate_limit_retry_then_success():
    anthropic = pytest.importorskip('anthropic')
    import httpx
    req = httpx.Request('POST', 'https://x')
    resp = httpx.Response(429, headers={'retry-after': '1'}, request=req)
    state = {'n': 0}

    def reply(kw):
        state['n'] += 1
        if state['n'] == 1:
            raise anthropic.RateLimitError('slow', response=resp, body=None)
        return message([mem('Vive en Medellin', 0)])

    fake = Fake(reply)
    assert len(llm.extract_memories([conv()], client=fake)) == 1 and state['n'] == 2


def test_client_error_fails_chunk_without_retry():
    anthropic = pytest.importorskip('anthropic')
    import httpx
    resp = httpx.Response(400, request=httpx.Request('POST', 'https://x'))
    state = {'n': 0}

    def reply(kw):
        state['n'] += 1
        raise anthropic.BadRequestError('bad', response=resp, body=None)

    issues = []
    assert llm.extract_memories([conv()], client=Fake(reply), issues=issues) == [] and state['n'] == 1 and issues


def test_server_error_retries_then_gives_up():
    anthropic = pytest.importorskip('anthropic')
    import httpx
    resp = httpx.Response(503, request=httpx.Request('POST', 'https://x'))
    state = {'n': 0}

    def reply(kw):
        state['n'] += 1
        raise anthropic.InternalServerError('down', response=resp, body=None)

    issues = []
    assert llm.extract_memories([conv()], client=Fake(reply), issues=issues) == [] and state['n'] == 3 and issues


def test_empty_input_no_calls():
    fake = Fake()
    assert llm.extract_memories([], client=fake) == [] and not fake.calls
