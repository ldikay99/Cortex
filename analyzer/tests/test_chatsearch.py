from datetime import datetime, timedelta

import numpy as np

from cortex_graph import chatsearch, semantic


def model(lines, start=datetime(2024, 1, 1, 10)):
    msgs = []
    for k, (conv, author, text) in enumerate(lines):
        msgs.append({'text': text, 'author': author, 'role': 'user' if author == 'user' else 'other', 'conv': conv,
                     'time': start + timedelta(days=int(conv[1:]) * 30, minutes=k)})
    return chatsearch.Model(msgs)


def best(m, query, window=None):
    scores = m.score(query, window)
    return max(range(len(scores)), key=lambda x: scores[x])


def test_stem_merges_english_and_spanish_forms():
    stem = chatsearch.stem
    assert stem('painting') == stem('painted') == stem('paints') == stem('paint')
    assert stem('swimming') == stem('swim') and stem('families') == stem('family')
    assert stem('children') == 'child' and stem('went') == 'go'
    assert stem('pintando') == stem('pintar') == stem('pinté'.replace('é', 'e'))
    assert stem('experimentation') == stem('experimenting')


def test_vocatives_reveal_the_user_name():
    lines = [('c1', 'Ana', 'Hey Marta! How was the trip?'), ('c1', 'user', 'Great, thanks Ana. We hiked a lot.'),
             ('c1', 'Ana', 'Glad to hear, Marta!'), ('c1', 'user', 'I also bought a new camera.'),
             ('c1', 'Ana', 'Cool, Marta. Send pics!'), ('c1', 'user', 'Sure Ana!')]
    m = model(lines)
    assert m.alias['marta'] == {m.author_ids['user']} and m.alias['ana'] == {m.author_ids['Ana']}
    assert best(m, 'What did Marta buy?') == 3


def test_lexicon_expands_categories_in_both_languages():
    lines = [('c1', 'user', 'I signed up for a pottery class'), ('c1', 'Ana', 'nice weather today'),
             ('c2', 'user', 'me encanta la natación'), ('c2', 'Ana', 'qué calor hace')]
    m = model(lines)
    assert best(m, 'what hobbies do I have?') == 0
    assert best(m, '¿qué deportes practico?') == 2


def test_first_person_queries_prefer_the_user():
    lines = [('c1', 'Ana', 'I love sushi'), ('c1', 'user', 'I love sushi too')]
    m = model(lines)
    assert best(m, 'what food do I love?') == 1


def test_typos_and_hyphens_still_match():
    lines = [('c1', 'user', 'running helps me de-stress'), ('c1', 'Ana', 'my education matters'), ('c1', 'user', 'ok')]
    m = model(lines)
    assert best(m, 'how do I destress?') == 0
    assert best(m, 'educaton plans') == 1


def test_context_and_time_window_lift_answers():
    lines = [('c1', 'Ana', 'How was the concert?'), ('c1', 'user', 'Amazing, the band played for three hours'),
             ('c2', 'Ana', 'Any news?'), ('c2', 'user', 'I adopted a puppy')]
    m = model(lines)
    scores = m.score('concert')
    assert scores[1] > 0 and scores[1] > scores[2]
    window = (datetime(2024, 2, 25), datetime(2024, 3, 5))
    assert best(m, 'what happened?', window) in (2, 3)
    assert chatsearch.top(m.score('xyzzy')) == []


def test_hints_expand_with_lower_weight():
    lines = [('c1', 'user', 'I play the violin every evening'), ('c1', 'Ana', 'nice'),
             ('c2', 'user', 'my favourite instrument is old'), ('c2', 'Ana', 'cool')]
    m = model(lines)
    plain_scores = m.score('what instrument do I play?')
    assert plain_scores[0] > 0
    hinted = m.score('what kind of music?', hints=['violin', 'piano'])
    assert best(m, 'what kind of music?') != 0 and hinted[0] == max(hinted)
    both = m.score('instrument', hints=['violin'])
    assert both[2] > both[0]


class Concepts:
    name = 'test@1'
    table = {'dog': 0, 'puppy': 0, 'pet': 0, 'perro': 0, 'car': 1, 'truck': 1, 'coche': 1, 'rain': 2, 'weather': 2}

    def __init__(self):
        self.calls = 0

    def __call__(self, texts):
        self.calls += 1
        out = np.zeros((len(texts), 4), dtype=np.float32)
        for k, text in enumerate(texts):
            for w in chatsearch.words(text):
                out[k, self.table.get(w, 3)] += 1.0 if w in self.table else 0.05
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(norms > 0, norms, 1)


def test_semantic_fusion_finds_paraphrases():
    lines = [('c1', 'user', 'we adopted a puppy yesterday'), ('c1', 'Ana', 'so cute'),
             ('c2', 'user', 'I sold my truck'), ('c2', 'Ana', 'the weather is awful')]
    m = model(lines)
    assert m.score('tell me about my dog')[0] == 0
    enc = Concepts()
    m.attach(enc([x[2] for x in lines]), enc)
    scores = m.score('tell me about my dog')
    assert best(m, 'tell me about my dog') == 0 and scores[0] > scores[2]
    assert best(m, '¿qué pasó con mi coche?') == 2


def test_embeddings_are_cached_and_invalidated(tmp_path):
    enc = Concepts()
    texts = ['a puppy', 'a truck', 'rain']
    first = semantic.vectors(enc, texts, str(tmp_path), 'fp1')
    again = semantic.vectors(enc, texts, str(tmp_path), 'fp1')
    assert enc.calls == 1 and np.array_equal(first, again) and first.dtype == np.float32
    semantic.vectors(enc, texts, str(tmp_path), 'fp2')
    assert enc.calls == 2 and len(list((tmp_path / semantic.FOLDER).glob('*.npy'))) == 1
    semantic.vectors(enc, texts + ['dog'], str(tmp_path), 'fp2')
    assert enc.calls == 3


def test_semantic_is_optional(monkeypatch):
    monkeypatch.setenv('CORTEX_EMBED_MODEL', 'off')
    assert semantic.configured() is None and semantic.encoder() is None
    monkeypatch.setenv('CORTEX_EMBED_MODEL', 'org/missing-model')
    monkeypatch.setattr(semantic, 'failed', {})
    calls = []

    def broken(spec):
        calls.append(spec)
        raise ImportError('no model2vec')

    monkeypatch.setattr(semantic, 'load', broken)
    assert semantic.encoder() is None and semantic.encoder() is None and calls == ['org/missing-model']
    m = model([('c1', 'user', 'hello there')])
    assert semantic.attach(m, ['hello there'], None) is False and m.vectors is None
    monkeypatch.delenv('CORTEX_EMBED_MODEL')
    assert semantic.configured() == semantic.DEFAULT_MODEL
    assert semantic.parse(semantic.DEFAULT_MODEL)[1] == semantic.REVISIONS[semantic.DEFAULT_MODEL]
