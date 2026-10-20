import difflib
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import numpy as np
from scipy import sparse

from . import lexicon

WORD_RE = re.compile(r'[^\W_]+')
VOCATIVE_RE = re.compile(r'(?:[,;]\s*|\b(?:[Hh]ey|[Hh]i|[Hh]ello|[Tt]hanks|[Tt]hank you|[Dd]ear|[Hh]ola|[Gg]racias|[Qq]uerid[oa])\s+)'
                         r'([A-ZÁÉÍÓÚÑ][a-záéíóúñü]{1,})\s*[!,.?:]')
STOP = frozenset('''
a about above after again against all also am an and any are as at be because been before being below between both but by can
could did do does doing done down during each else even ever few for from further get gets got had has have having he her here
hers herself him himself his how i if in into is it its itself just let lets me more most much must my myself no nor not now
of off on once only or other our ours ourselves out over own really same she should so some still such than that thats the their
theirs them themselves then there these they this those through to too under until up upon us very was we were what whats when
where which while who whom whose why will with would yeah yes yet you your yours yourself yourselves im ive id youre youve youll
dont didnt doesnt isnt wasnt cant wont oh ok okay hey hi hello thanks thank wow lol
something anything thing things kind sort lot lots one ones way well much many
el la los las lo un una unos unas de del al y e o u ni en con por para que como donde cuando cual cuales quien quienes cuyo es son
era eran fue fueron ser estar esta estan estaba estoy estas este esto estos ese esa eso esos esas aquel aquella se su sus le les mi
mis me te ti tu tus nos nosotros vosotros ellos ellas el ella yo usted ustedes hay muy mas sin sobre entre hace hacer haber
ha han he hemos habia tiene tienen tengo tenia pero porque pues si no ya tambien solo aqui alli asi bien algo nada todo toda todos
todas otro otra otros otras mucho mucha muchos muchas poco ese hola gracias vale bueno claro jaja
'''.split())
IRREGULAR = dict(pair.split(':') for pair in '''
children:child kids:kid men:man women:woman people:person went:go gone:go goes:go ran:run saw:see seen:see bought:buy took:take
taken:take made:make felt:feel thought:think told:tell met:meet left:leave found:find began:begin begun:begin wrote:write
written:write gave:give given:give ate:eat eaten:eat drove:drive driven:drive flew:fly flown:fly swam:swim won:win lost:lose
paid:pay sang:sing sung:sing taught:teach brought:bring caught:catch built:build sent:send spent:spend kept:keep slept:sleep
held:hold fell:fall became:become came:come knew:know known:know grew:grow grown:grow threw:throw chose:choose chosen:choose
spoke:speak broke:break broken:break rode:ride heard:hear sold:sell stood:stand wore:wear worn:wear drew:draw drawn:draw
fought:fight sat:sit led:lead fed:feed shot:shoot hung:hang dug:dig lit:light woke:wake mice:mouse feet:foot teeth:tooth
geese:goose bitten:bite hid:hide hidden:hide forgot:forget forgotten:forget
'''.split())
EN_SUFFIXES = ('ations', 'ation', 'ments', 'ment', 'nesses', 'ness', 'ingly', 'ings', 'ing', 'edly', 'ies', 'ied', 'ed', 'es', 's')
ES_SUFFIXES = ('amientos', 'imientos', 'amiento', 'imiento', 'aciones', 'iciones', 'acion', 'icion', 'ieron', 'aron', 'abamos',
               'iamos', 'ando', 'iendo', 'ados', 'adas', 'idos', 'idas', 'aban', 'ado', 'ada', 'ido', 'ida', 'aba', 'amos', 'emos',
               'imos', 'ar', 'er', 'ir', 'ia', 'ias', 'as', 'os', 'es', 'a', 'o', 'e')
FIRST_PERSON = frozenset('i me my mine myself yo mi mis conmigo mio mia'.split())
EPOCH = datetime(1970, 1, 1)
OTHER_SPEAKER = 0.25
SELF_SPEAKER = 0.6
NAME_WEIGHT = 0.3
CONTEXT = (0.4, 0.2, 0.15)
SESSION = 0.05
COVER = 0.2
BM25 = (1.2, 0.75)
FEEDBACK_DOCS = 5
FEEDBACK_TERMS = 8
FEEDBACK_WEIGHT = 0.3
HINT_WEIGHT = 0.5
SEMANTIC = (0.3, 0.3, 1.0)
SEM_STRIP = 1
WINDOW_BOOST = 2.0
WINDOW_BASE = 0.05
WINDOW_DAYS = (2, 8)
WEAK_WORDS = '''
recently recent currently usually often ever likely might would could kind kinds type types sort specific particular mention mentioned
mentions say says said tell tells told talk talked share shared describe described consider considered based besides both also
reciente recientemente actualmente normalmente usualmente seguido probable probablemente tipo tipos clase mencionar menciono dijo
decir contar conto hablar hablo compartir compartio describir considerar ambos tambien
'''
WEAK_WEIGHT = 0.4
QUESTION_WORDS = {
    'who': 'person', 'quien': 'person', 'quienes': 'person', 'where': 'place', 'donde': 'place', 'adonde': 'place',
    'when': 'time', 'cuando': 'time', 'many': 'count', 'cuantos': 'count', 'cuantas': 'count',
}
QUESTION_TERMS = {
    'person': '_ent',
    'count': '''one two three four five six seven eight nine ten twice several couple few dozen first second third both
    uno una dos tres cuatro cinco seis siete ocho nueve diez varios varias pocos ambos primero segundo tercero
    1 2 3 4 5 6 7 8 9 10 11 12 15 20''',
    'place': '_ent place city country town lugar ciudad pais pueblo',
    'time': '''yesterday today tomorrow tonight ago last next week weekend month year morning night ayer hoy manana anoche
    pasado proximo semana fin mes ano noche january february march april may june july august september october november december
    enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre''',
}
QUESTION_WEIGHT = 0.6
HEAD_MEMBER = 0.5
MEMBER_HEAD = 0.35
SYNONYM = 0.8
STEMS = {}
DOUBLE = re.compile(r'([bdfgklmnprtvz])\1$')
CAP_RE = re.compile(r'(?<![.!?¡¿]\s)(?<!^)(?<![.!?¡¿])\b([A-ZÁÉÍÓÚÑ][a-záéíóúñü]{2,})')
HYPHEN_RE = re.compile(r'\b([^\W\d_]{2,})-([^\W\d_]{3,})\b')
QUOTE_RE = re.compile(r'["“«]([^"”»]{2,80})["”»]')


def plain(text):
    text = str(text or '')
    if text.isascii():
        return text.casefold()
    return ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c)).casefold()


def stem(w):
    if w in IRREGULAR:
        return IRREGULAR[w]
    if len(w) <= 3 or not w.isalpha():
        return w
    for suffix in EN_SUFFIXES:
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            base = w[:-len(suffix)]
            if suffix in ('ies', 'ied'):
                base += 'y'
            elif suffix in ('es',) and not base.endswith(('s', 'x', 'z', 'ch', 'sh')):
                base = w[:-1]
            elif suffix == 's' and w.endswith(('ss', 'us', 'is')):
                continue
            if suffix.startswith(('ing', 'ed')) and DOUBLE.search(base):
                base = base[:-1]
            w = base
            break
    for suffix in ES_SUFFIXES:
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            w = w[:-len(suffix)]
            break
    if w.endswith('y') and len(w) > 3:
        w = w[:-1] + 'i'
    return w


def words(text):
    return WORD_RE.findall(plain(text))


def stemmed(w):
    t = STEMS.get(w)
    if t is None:
        t = stem(w)
        if len(STEMS) < 500000:
            STEMS[w] = t
    return t


def terms(text, keep_stop=False, flat=None):
    found = WORD_RE.findall(flat if flat is not None else plain(text))
    return [stemmed(w) for w in found if (keep_stop or w not in STOP) and (len(w) > 1 or w.isdigit())]


def expansions():
    table = defaultdict(dict)

    def forms(phrase):
        return tuple(terms(phrase, keep_stop=True)) if not phrase.startswith('_') else (phrase,)

    def add(src, dst, w):
        for d in dst:
            if d != src and table[src].get(d, 0) < w:
                table[src][d] = w

    for heads, members in lexicon.parse_groups(lexicon.GROUPS):
        h, m = [forms(x) for x in heads], [forms(x) for x in members]
        if any('_ent' in x for x in m):
            m += [forms(x) for x in lexicon.GAZETTEER.split()]
        for x in h:
            add(x, m, HEAD_MEMBER)
            add(x, h, SYNONYM)
        for x in m:
            add(x, h, MEMBER_HEAD)
    for group in lexicon.parse_synonyms(lexicon.SYNONYMS):
        f = [forms(x) for x in group]
        for x in f:
            add(x, f, SYNONYM)
    return table


EXPAND = expansions()
WEAK_TERMS = frozenset(terms(WEAK_WORDS, keep_stop=True))


class Model:
    def __init__(self, msgs):
        self.msgs = msgs
        n = len(msgs)
        lower = Counter(w for m in msgs for w in WORD_RE.findall(m['text']) if w.islower())
        self.speakers(msgs, lower)
        upper = Counter(w for m in msgs for w in CAP_RE.findall(m['text']))
        vocab, rows, cols, vals, lengths, words_seen = {}, [], [], [], [], set()
        for i, m in enumerate(msgs):
            flat = plain(m['text'])
            counts = Counter(terms(m['text'], flat=flat))
            words_seen.update(w for w in WORD_RE.findall(flat) if len(w) >= 4 and w.isalpha())
            if '-' in flat:
                counts.update(stemmed(a + b) for a, b in HYPHEN_RE.findall(flat))
            caps = [w for w in CAP_RE.findall(m['text']) if lower[w.lower()] * 3 < upper[w] and plain(w) not in self.alias]
            if caps:
                counts['_ent'] = 1
            if QUOTE_RE.search(m['text']):
                counts['_quote'] = 1
            lengths.append(sum(counts.values()) or 1)
            for t, c in counts.items():
                j = vocab.setdefault(t, len(vocab))
                rows.append(i)
                cols.append(j)
                vals.append(c)
        self.vocab = vocab
        self.tf = sparse.csr_matrix((np.array(vals, dtype=np.float32), (rows, cols)), shape=(n, len(vocab)))
        self.lengths = np.array(lengths, dtype=np.float32)
        self.df = np.asarray((self.tf > 0).sum(axis=0)).ravel().astype(np.float32)
        self.idf = np.log(1 + (n - self.df + 0.5) / (self.df + 0.5)).astype(np.float32)
        self.csc = self.tf.tocsc()
        self.prev = np.array([i - 1 if i > 0 and msgs[i - 1]['conv'] == m['conv'] else -1 for i, m in enumerate(msgs)], dtype=np.int64)
        self.next = np.array([i + 1 if i + 1 < n and msgs[i + 1]['conv'] == m['conv'] else -1 for i, m in enumerate(msgs)], dtype=np.int64)
        convs = {}
        self.conv = np.array([convs.setdefault(m['conv'], len(convs)) for m in msgs], dtype=np.int64)
        self.nconv = len(convs)
        self.times = np.array([(m['time'] - EPOCH).total_seconds() if m.get('time') else np.nan for m in msgs], dtype=np.float64)
        self.terms_of = {j: t for t, j in vocab.items()}
        self.surfaces = None
        self.words = words_seen
        self.vectors = None
        self.encode = None

    def attach(self, vectors, encode):
        if vectors is not None and len(vectors) == len(self.msgs) and encode is not None:
            self.vectors, self.encode = vectors, encode

    def speakers(self, msgs, lower):
        authors = Counter(m['author'] for m in msgs if m['author'])
        self.author_ids = {a: k for k, a in enumerate(sorted(authors))}
        self.author = np.array([self.author_ids.get(m['author'], -1) for m in msgs], dtype=np.int64)
        self.users = {self.author_ids[m['author']] for m in msgs if m['author'] and m.get('role') == 'user'}
        aliases = defaultdict(Counter)
        own = defaultdict(Counter)
        by_conv = defaultdict(set)
        for m in msgs:
            by_conv[m['conv']].add(m['author'])
        for m in msgs:
            others = by_conv[m['conv']] - {m['author']}
            for x in {plain(x) for x in VOCATIVE_RE.findall(m['text'])}:
                own[m['author']][x] += 1
                if len(others) == 1:
                    aliases[next(iter(others))][x] += 1
        alias = defaultdict(set)
        for a in authors:
            for w in words(a):
                if len(w) > 2 and w not in STOP:
                    alias[w].add(self.author_ids[a])
            for x, c in aliases[a].items():
                if c >= 3 and c >= 4 * own[a][x] and lower[x] * 4 < c and x not in STOP:
                    alias[x].add(self.author_ids[a])
        self.alias = dict(alias)

    def query(self, text, expand=1.0):
        found, kept, raw, names, mine, asked = set(), [], {}, set(), False, set()
        for w in words(text):
            if w in self.alias:
                found |= self.alias[w]
                names.add(stem(w))
                kept.append(stem(w))
                continue
            mine = mine or w in FIRST_PERSON
            if w in QUESTION_WORDS and QUESTION_WEIGHT:
                asked.add(QUESTION_WORDS[w])
            if w in STOP or (len(w) < 2 and not w.isdigit()):
                continue
            kept.append(stem(w))
            raw.setdefault(kept[-1], w)
        slots, k = [], 0
        while k < len(kept):
            pair = tuple(kept[k:k + 2])
            key = pair if len(pair) == 2 and (pair in EXPAND or ''.join(pair) in self.vocab) else (kept[k],)
            k += len(key)
            variants = {t: 1.0 for t in key}
            if len(key) == 1 and key[0] not in self.vocab:
                variants.update(self.repairs(key[0], raw.get(key[0], key[0])))
            if len(key) == 2 and ''.join(key) in self.vocab:
                variants[''.join(key)] = 1.0
            if expand:
                for dst, w in EXPAND.get(key, {}).items():
                    for t in dst:
                        variants.setdefault(t, 0.0)
                        variants[t] = max(variants[t], w * expand * (0.7 if len(dst) > 1 else 1.0))
            if key[0] in names and len(key) == 1:
                variants = {key[0]: NAME_WEIGHT}
            elif len(key) == 1 and key[0] in WEAK_TERMS:
                variants = {t: w * WEAK_WEIGHT for t, w in variants.items()}
            if not any(s[0] == key for s in slots):
                slots.append((key, variants))
        for kind in sorted(asked):
            slots.append((('?' + kind,), {t: QUESTION_WEIGHT for t in terms(QUESTION_TERMS[kind], keep_stop=True)}))
        if not found and mine and self.users and len(self.author_ids) > 1:
            return slots, set(self.users), SELF_SPEAKER
        return slots, found, OTHER_SPEAKER

    def repairs(self, t, word):
        if len(word) < 5 or not word.isalpha():
            return {}
        out = {}
        for k in range(3, len(t) - 2):
            if t[:k] in self.vocab and t[k:] in self.vocab:
                out[t[:k]] = out[t[k:]] = 0.6
        if not out:
            if self.surfaces is None:
                self.surfaces = defaultdict(list)
                for v in sorted(self.words):
                    self.surfaces[v[0]].append(v)
            pool = [v for v in self.surfaces.get(word[0], ()) if abs(len(v) - len(word)) <= 2]
            near = difflib.get_close_matches(word, pool, n=3, cutoff=0.85)
            out = {stemmed(x): 0.8 for x in near if stemmed(x) in self.vocab}
        return out

    def slot_weight(self, key, variants):
        if key[0].startswith('?'):
            known = [self.idf[self.vocab[t]] for t in variants if t in self.vocab]
            return QUESTION_WEIGHT * float(np.mean(known)) if known else 0.0
        idf = [self.idf[self.vocab[t]] for t in key if t in self.vocab]
        if idf:
            return max(idf)
        known = [self.idf[self.vocab[t]] for t in variants if t in self.vocab]
        return 0.7 * max(known) if known else 0.0

    def bm25(self, slots):
        k1, b = BM25
        n = len(self.msgs)
        score = np.zeros(n, dtype=np.float32)
        hits = np.zeros(n, dtype=np.float32)
        norm = k1 * (1 - b + b * self.lengths / self.lengths.mean())
        mass = 0.0
        for key, variants in slots:
            weight = self.slot_weight(key, variants)
            if not weight:
                continue
            mass += weight
            best = np.zeros(n, dtype=np.float32)
            cover = np.zeros(n, dtype=np.float32)
            for t, w in variants.items():
                j = self.vocab.get(t)
                if j is None or w <= 0:
                    continue
                lo, hi = self.csc.indptr[j], self.csc.indptr[j + 1]
                idx, tf = self.csc.indices[lo:hi], self.csc.data[lo:hi]
                value = w * self.idf[j] * tf * (k1 + 1) / (tf + norm[idx])
                np.maximum.at(best, idx, value)
                np.maximum.at(cover, idx, w)
            score += best
            hits += cover * weight
        return score, hits / mass if mass else hits

    def informative(self, query, text):
        keys = [t for key, _ in self.query(query, expand=0)[0] for t in key]
        limit = 0.3 * max(1, len(self.msgs))
        rare = [t for t in keys if t in self.vocab and self.df[self.vocab[t]] <= limit] or keys
        return bool(set(rare) & set(terms(text)))

    def spread(self, s):
        before = np.where(self.prev >= 0, s[np.maximum(self.prev, 0)], 0)
        after = np.where(self.next >= 0, s[np.maximum(self.next, 0)], 0)
        out = s + np.maximum(CONTEXT[0] * before, CONTEXT[1] * after)
        far_before = np.where(self.prev >= 0, before[np.maximum(self.prev, 0)], 0)
        far_after = np.where(self.next >= 0, after[np.maximum(self.next, 0)], 0)
        out += CONTEXT[2] * np.maximum(far_before, far_after)
        top = np.zeros(self.nconv, dtype=np.float32)
        np.maximum.at(top, self.conv, s)
        return out + SESSION * top[self.conv]

    def lexical(self, slots):
        s, cover = self.bm25(slots)
        return self.spread(s * (COVER + (1 - COVER) * cover * cover))

    def feedback(self, s, slots):
        top = np.argsort(-s, kind='stable')[:FEEDBACK_DOCS]
        peak = float(s[top[0]]) if len(top) else 0.0
        if peak <= 0:
            return []
        have = {t for _, variants in slots for t in variants}
        acc = defaultdict(float)
        for x in top:
            lo, hi = self.tf.indptr[x], self.tf.indptr[x + 1]
            for j in self.tf.indices[lo:hi]:
                acc[j] += float(self.idf[j]) * float(s[x]) / peak
        picked = [self.terms_of[j] for j, _ in sorted(acc.items(), key=lambda kv: (-kv[1], kv[0]))
                  if self.terms_of[j] not in have and self.df[j] > 1 and not self.terms_of[j].startswith('_')]
        return [((t,), {t: 1.0}) for t in picked[:FEEDBACK_TERMS]]

    def hint_slots(self, hints, slots):
        have = {t for key, _ in slots for t in key}
        out = []
        for hint in hints or ():
            for key, variants in self.query(str(hint), expand=0.7)[0]:
                if key[0].startswith('?') or all(t in have for t in key):
                    continue
                have.update(key)
                out.append((key, variants))
        return out

    def semantic(self, text, hints):
        if self.vectors is None or not SEMANTIC[0]:
            return None
        try:
            if SEM_STRIP:
                text = ' '.join(w for w in WORD_RE.findall(str(text)) if plain(w) not in self.alias and (SEM_STRIP < 2 or plain(w) not in STOP))
            q = np.asarray(self.encode([' '.join([text] + [str(h) for h in hints or ()])]), dtype=np.float32)[0]
        except Exception:
            return None
        norm = float(np.linalg.norm(q))
        if not norm:
            return None
        cos = (self.vectors @ (q / norm)).astype(np.float32)
        floor = float(np.quantile(cos, 1 - SEMANTIC[1])) if 0 < SEMANTIC[1] < 1 else 0.0
        peak = float(cos.max())
        if peak <= floor:
            return None
        sem = np.clip((cos - floor) / (peak - floor), 0, None) ** SEMANTIC[2]
        return self.spread(sem)

    def score(self, text, window=None, hints=None):
        n = len(self.msgs)
        if not n:
            return np.zeros(0, dtype=np.float32)
        slots, speakers, factor = self.query(text)
        prior = np.where(np.isin(self.author, list(speakers)), 1.0, factor) if speakers else 1.0
        s = self.lexical(slots) if slots else np.zeros(n, dtype=np.float32)
        extra = self.hint_slots(hints, slots)
        if extra and HINT_WEIGHT:
            s = s + HINT_WEIGHT * self.lexical(extra)
        sem = self.semantic(text, hints)
        if sem is not None:
            peak = float(s.max())
            s = s + SEMANTIC[0] * (peak if peak > 0 else 1.0) * sem
        extra = self.feedback(s * prior, slots + extra)
        if extra:
            s = s + FEEDBACK_WEIGHT * self.lexical(extra)
        s = s * prior
        if window:
            lo = (window[0] - timedelta(days=WINDOW_DAYS[0]) - EPOCH).total_seconds()
            hi = (window[1] + timedelta(days=WINDOW_DAYS[1]) - EPOCH).total_seconds()
            inside = (self.times >= lo) & (self.times < hi)
            if inside.any():
                peak = float(s.max()) if s.max() > 0 else 1.0
                s = s * np.where(inside, 1 + WINDOW_BOOST, 1.0) + inside * WINDOW_BASE * peak
        return s.astype(np.float32)


def top(scores, floor=0.0, limit=None):
    if scores is None or not len(scores):
        return []
    order = np.argsort(-scores, kind='stable')[:limit]
    peak = float(scores[order[0]])
    if peak <= 0:
        return []
    return [(float(scores[x]) / peak, int(x)) for x in order if scores[x] > 0 and scores[x] >= peak * floor]
