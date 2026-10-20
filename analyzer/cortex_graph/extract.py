import math
import re
import unicodedata
from collections import Counter
from datetime import date

from .common import digest


def fold_table():
    table = {}
    for code in range(0xC0, 0x250):
        ch = chr(code)
        base = ''.join(c for c in unicodedata.normalize('NFKD', ch) if not unicodedata.combining(c))
        if len(base) == 1 and base != ch:
            table[code] = base
    table.update({ord('’'): "'", ord('‘'): "'"})
    return table


FOLD = fold_table()
MAX_SCAN = 2_000_000
MAX_FACT_CHARS = 2000
TOP_CONCEPTS = 12


def words_set(text):
    return frozenset(text.split())


STOP = words_set('''
a al algo algun alguna algunas alguno algunos ante antes aqui asi aun aunque bajo bien cada casi como con contra cual cuales
cualquier cuando cuanto de del desde donde dos el ella ellas ello ellos en entre era eran eres es esa esas ese eso esos esta
estaba estado estan estar estas este esto estos estoy fue fueron fui ha haber habia han has hasta hay he hemos hoy la las le
les lo los mas me mi mia mias mio mios mis mucho muchos muy nada ni no nos nosotros nuestra nuestras nuestro nuestros o otra
otras otro otros para pero poco por porque pues que quien quienes se sea sean segun ser si sido siempre sin sino sobre sois
somos son soy su sus tal tambien tampoco tan tanto te tenemos tener tengo ti tiene tienen todo todos tu tus un una uno unos
unas usted ustedes va vamos van vosotros y ya yo hacer hago hace hacen hizo puedo puede pueden podria quiero quieres quiere
creo cree dice dijo decir digo voy vas ver veo vez veces cosa cosas gracias hola vale bueno buena buenas buenos claro okay
ok sí parte forma manera tiempo ahora luego entonces despues alli ahi aca mismo misma mismos mismas cierto ciertos tipo tipos
dia dias ano anos mes meses always never usually often normally sometimes estuvo tuvo hubo fue fueron era
eran hizo puso vino pudo quiso supo dio vio esta estan tienen haber sido siendo tener poder deber pidio dijeron hicieron
tenia tenian estaba estaban habia hay seguir sigue llega llego paso pasa queda quedo semana semanas hora horas momento caso casos solo sola cuenta mejor peor gran grande nuevo nueva
favor ejemplo etc puedes podemos debo debe deben necesito necesita estamos estaban seria serian fuera tenia tuve hecho dicho
gusta encanta parece queria usar uso haz dame dime mira oye pues favor siguiente anterior primero primera ultimo ultima
about above after again against all also am an and any are aren as at be because been before being below between both but
by can cannot could did didn do does doesn doing don down during each few for from further had hasn have haven having he her
here hers herself him himself his how i if in into is isn it its itself just let me more most my myself no nor not now of
off on once only or other ought our ours ourselves out over own same she should so some such than that the their theirs them
themselves then there these they this those through to too under until up very was wasn we were weren what when where which
while who whom why will with won would you your yours yourself yourselves yes yeah thanks thank hello hi hey please okay
get got make made know think thing things way want need like really much many one two also well even still back going
good great new use used using see look sure right let lets say said said tell told time times day days year years week weeks
first last next something anything everything nothing someone anyone everyone people example etc maybe kind sort lot lots
can could would should shall may might must ll ve re doesn wasn isn aren didn won wouldn couldn shouldn here there via per
lunes martes miercoles jueves viernes sabado domingo monday tuesday wednesday thursday friday saturday sunday enero febrero
marzo abril mayo junio julio agosto septiembre setiembre octubre noviembre diciembre january february march april june july
august september october november december
''')
MONTHS = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8, 'septiembre': 9,
    'setiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12, 'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
}
EN_ABBR = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12}
FIRST_NAMES = words_set('''
alejandro alejandra alberto alicia ana andres andrea angela angelica antonio beatriz camila carlos carla carmen carolina
catalina cecilia claudia cristina cristian daniel daniela david diana diego eduardo elena elisa emilio enrique esteban eva
fernando fernanda francisco gabriel gabriela gonzalo guillermo gustavo hector hugo ignacio ines isabel isabella jaime javier
jesus jorge jose josefina juan juana julia julian juliana laura leonardo lucia luis luisa manuel manuela marcela marcos maria
mariana mario marta martin mateo miguel monica natalia nicolas oscar pablo patricia paula pedro rafael ramon raul ricardo
roberto rodrigo sara sebastian sergio silvia sofia tomas valentina valeria veronica victor ximena jimena yolanda lorena
liliana sandra adriana johana paola felipe samuel simon alvaro ivan ruben estefania melissa vanessa karen katherine kevin
nathalia natalie lina juliet joaquin agustin emiliano santino thiago renata florencia agustina martina macarena constanza
francisca ignacia benjamin vicente matias facundo lautaro gael emma olivia sophia sophie mia ava chloe ella zoe lucas liam
oliver elijah noah ethan james john robert michael william richard joseph thomas charles christopher matthew anthony donald
steven paul andrew joshua kenneth brian george timothy ronald edward jason jeffrey ryan jacob gary nicholas eric jonathan
stephen larry justin scott brandon gregory alexander patrick dennis jerry tyler aaron adam nathan henry peter zachary kyle
jeremy christian sean arthur lawrence dylan jesse bryan billy bruce albert logan alan wayne roy ralph eugene louis philip
bobby johnny mary jennifer linda elizabeth barbara susan jessica sarah nancy betty margaret ashley kimberly emily donna
michelle carol amanda dorothy deborah stephanie rebecca sharon cynthia kathleen amy shirley anna brenda pamela nicole helen
samantha christine debra rachel carolyn janet catherine heather diane ruth julie joyce kelly christina lauren joan evelyn
judith megan cheryl hannah jacqueline martha gloria teresa ann frances kathryn janice abigail alice judy denise doris marilyn
danielle beverly theresa brittany marie kayla alexis lori sam ben tom tim dan nick alex chris mike jim bob kate jane anne lucy
ellen claire felix leo hugo pierre jean jacques francois marc luc antoine giulia giuseppe marco luca francesco alessandro
matteo lorenzo chiara federica paolo joao pedro thiago gustavo rafaela beatriz ines miguel goncalo hans klaus jurgen anja
katrin stefan andreas markus aisha fatima omar ali hassan yusuf mohammed ahmed priya rahul arjun ananya wei li ming hiroshi
yuki kenji sakura
''')
NOT_NAME = STOP | words_set('''
dios god senor senora sr sra srta dr dra mr mrs ms miss prof don dona hola hello hi hey querido querida dear gracias thanks
buenos buenas feliz happy nota note todo todos nada nadie hoy ayer manana tarde noche today tomorrow yesterday tonight
tambien pero entonces ok okay vale si yes no bueno bien gran nuevo nueva capitulo chapter seccion section parte part paso
step tema topic resumen summary introduccion introduction conclusion conclusiones objetivo objetivos titulo title figura
figure tabla table anexo appendix pregunta respuesta question answer usuario user asistente assistant sistema system cliente
gobierno internet web email correo navidad christmas pascua easter ano year estimado estimada atentamente saludos regards
''')
BLOCK_NAME = words_set('''
asunto fecha subject date from to cc bcc re fw fwd enviado sent adjunto adjuntos attachment attachments general ejecutivo
ejecutiva executive senior junior adjunto adjunta nacional regional tecnico tecnica comercial financiero financiera operaciones
operations sales ventas producto product marketing
equipo team grupo group proyecto project plan empresa company universidad university colegio school escuela banco bank
hospital clinica ministerio instituto institute fundacion foundation club calle avenida carrera street avenue road rio river
lago lake monte mount san santa santo saint st new north south east west norte sur este oeste city ciudad estado state
provincia departamento reino kingdom unidos united republica republic america europa europe asia africa inc ltd llc sa sas
corp corporation compania company servicio service app aplicacion api sdk python java javascript typescript react vue node
docker linux windows macos ios android google apple microsoft amazon facebook meta instagram twitter whatsapp telegram slack
discord github gitlab excel word powerpoint notion obsidian chrome firefox safari django flask rust ruby swift kotlin
postgres postgresql mysql mongodb redis kubernetes aws azure spotify netflix youtube tiktok linkedin zoom teams gmail outlook
iphone ipad markdown html css json yaml sql pdf ceo cto cfo
''')
NOT_NAME = NOT_NAME | BLOCK_NAME
TITLE_WORDS = words_set('''
manager director directora ceo cto cfo coo presidente presidenta president gerente profesor profesora professor doctor
doctora dr dra mr mrs ms miss sr sra srta don dona prof profa ingeniero ingeniera engineer lic ing senator senador senadora
alcalde alcaldesa coach capitan captain agent agente detective inspector inspectora lead
''')
NAME_CONNECT = words_set('de del la las los da das do dos di du van von der den le bin ibn al')
NAME_CHARS_UP = 'A-ZÀ-ÖØ-Þ'
NAME_CHARS_LO = 'a-zß-öø-ÿ'
CAP = rf"[{NAME_CHARS_UP}][{NAME_CHARS_LO}]+(?:['’\-][{NAME_CHARS_UP}{NAME_CHARS_LO}][{NAME_CHARS_LO}]+)?"
NAME_RE = re.compile(rf"(?<![\w@#/.\-]){CAP}(?:[ \t]+(?:(?:de|del|da|das|do|dos|di|du|van|von|der|den|le|la|las|los|bin|al)[ \t]+)?{CAP}){{0,3}}(?![\w@])")
LOWER_RE = re.compile(rf"(?<![\w])[{NAME_CHARS_LO}][{NAME_CHARS_LO}]+(?![\w])")
CUE_BEFORE_RE = re.compile(
    r"(?:\b(?:sr|sra|srta|dr|dra|mr|mrs|ms|miss|prof|profa|don|dona|senor|senora|ing|lic)\.?"
    r"|\b(?:mi|tu|su|mis|nuestro|nuestra|my|your|his|her|our|their)\s+(?:mejor\s+|best\s+)?(?:esposa|esposo|marido|mujer|hermano|hermana|"
    r"amigo|amiga|jefe|jefa|novio|novia|pareja|mama|papa|madre|padre|hijo|hija|primo|prima|tio|tia|abuelo|abuela|companero|"
    r"companera|colega|socio|socia|wife|husband|brother|sister|friend|boss|mom|mum|dad|mother|father|son|daughter|cousin|uncle|"
    r"aunt|grandma|grandpa|colleague|coworker|partner|girlfriend|boyfriend|manager|cofounder|cliente|client|sobrino|sobrina|"
    r"suegra|suegro|nephew|niece|mentor|mentora|terapeuta|therapist)"
    r"|\b(?:profesor|profesora|doctor|doctora|ingeniero|ingeniera|licenciado|licenciada|abogado|abogada|presidente|presidenta|"
    r"gerente|director|directora|senador|senadora|alcalde|alcaldesa|professor|engineer|manager|president|coach|tio|tia|abuela|"
    r"abuelo|uncle|aunt|capitan|captain|agent|agente|detective|inspector|inspectora)"
    r"|\b(?:hable|converse|me reuni|reunion|cita|almorce|cene|sali|hablando|conversando|quede|trabaje|trabajo)\s+con"
    r"|\b(?:talked|spoke|met|meeting|chatted|lunch|dinner|coffee|call|worked)\s+(?:to|with)"
    r"|\b(?:hola|hi|hello|hey|querida|querido|dear|gracias|thanks|thank you|conoci a|visite a|llame a|escribi a|le dije a|"
    r"le escribi a|le pregunte a|called|asked|told|emailed|texted|met|invited|invite|cc|para)"
    r"|^\s*(?:de|from|to|para|cc|con|with|autor|author|by|por)\s*:)[\s,]*$")
CUE_AFTER_RE = re.compile(
    r"^\s*(?:me |le |nos |te |les )?(?:dijo|dice|comento|escribio|pregunto|llamo|respondio|contesto|opina|piensa|cree|"
    r"said|says|told|asked|wrote|replied|called|thinks|texted|emailed|mentioned|suggested|sugirio|propuso)\b")
LOCATION_BEFORE_RE = re.compile(r"\b(?:en|in|at|from|desde|hacia|to|into|near|cerca de|de|del|of|la|el|the)\s*$")
PLACE_BEFORE_RE = re.compile(r"\b(?:en|in|at|from|desde|hacia|into|near|cerca de|a vivir a|viajar a|viaje a|fui a|vamos a|ir a|travel to|go to|went to|moved to)\s*$")
INITIAL_CHARS = set('.!?\n:;•*-–—>#"“«(¿¡|')
CODE_RE = re.compile(r'```.*?(?:```|\Z)|~~~.*?(?:~~~|\Z)', re.S)
INLINE_CODE_RE = re.compile(r'`[^`\n]{1,200}`')
URL_RE = re.compile(r"\b(?:https?://|www\.)[^\s<>\"'`\]\)]+", re.I)
EMAIL_RE = re.compile(r'(?<![\w.+\-])[\w.+\-]{1,64}@[\w\-]{1,63}(?:\.[\w\-]{1,63})+')
WIKI_RE = re.compile(r'!?\[\[([^\[\]\n|#]*)(?:#([^\[\]\n|]*))?(?:\|([^\[\]\n]*))?\]\]')
TAG_RE = re.compile(r"(?<![\w#&/=\"'])#(?:\[\[([^\]\n]{1,80})\]\]|([^\W\d_][\w/\-]{0,49}))")
HEX_RE = re.compile(r'[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8}')
NORM_PUNCT_RE = re.compile(r'[^\w\s]')
DIGIT_RE = re.compile(r'\d{4}')
TAG_STRIP_RE = re.compile(r'[#@]\S+')
MENTION_RE = re.compile(r'(?<![\w@./])@([A-Za-z0-9_](?:[\w.\-]{0,37}[\w])?)')
ISO_DATE_RE = re.compile(r'(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)')
DMY_RE = re.compile(r'(?<![\d/.\-])(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})(?![\d/.\-])')
MONTH_ALT = '|'.join(sorted(MONTHS, key=len, reverse=True))
ABBR_ALT = '|'.join(sorted(EN_ABBR, key=len, reverse=True))
ES_DATE_RE = re.compile(rf'\b(\d{{1,2}})(?:º|°|o)?\s+de\s+({MONTH_ALT})(?:\s+(?:de|del)\s+|\s*,\s*|\s+)(\d{{4}})\b', re.I)
EN_DATE_RE = re.compile(rf'\b({MONTH_ALT}|{ABBR_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b', re.I)
EN_DATE2_RE = re.compile(rf'\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({MONTH_ALT}|{ABBR_ALT})\.?,?\s+(\d{{4}})\b', re.I)
MONTH_YEAR_RE = re.compile(rf'\b({MONTH_ALT})\s+(?:de\s+|del\s+|of\s+)?(\d{{4}})\b', re.I)
CONNECTORS = {'de', 'del', 'of'}
VERB_ENDINGS = ('iendo', 'aron', 'ieron', 'aban', 'abamos')
SPLIT_RE = re.compile(r"[^\w\s]+|\n")
WORD_EDGE = "'-’"


def fold(text):
    return (text or '').lower().translate(FOLD)


def key(text):
    return re.sub(r'[\W_]+', '-', fold(text)).strip('-')


def singular(word):
    if len(word) > 4 and word.endswith('es') and word[-3] in 'lrndzj':
        return word[:-2]
    if len(word) > 3 and word.endswith('s') and not word.endswith(('ss', 'us', 'is')):
        return word[:-1]
    return word


def concept_key(text):
    return '-'.join(singular(w) for w in re.split(r'[\W_]+', fold(text)) if w)


def slug(text):
    return key(text)[:60].strip('-') or 'seccion'


def normalize(text):
    return ' '.join(NORM_PUNCT_RE.sub(' ', fold(text)).split())


def memory_id(text, extra=''):
    return digest(normalize(text) + (f'|{extra}' if extra else ''))


def blank(text, pattern, keep=None):
    def repl(m):
        if keep is not None:
            keep.append(m.group())
        return re.sub(r'[^\n]', ' ', m.group())
    return pattern.sub(repl, text)


def valid_date(y, m, d=None):
    y, m = int(y), int(m)
    if not 1900 <= y <= 2100 or not 1 <= m <= 12:
        return None
    if d is None:
        return f'{y:04d}-{m:02d}'
    try:
        return date(y, m, int(d)).isoformat()
    except ValueError:
        return None


def find_dates(text):
    found = []
    if not DIGIT_RE.search(text):
        return found

    def take(pattern, build):
        nonlocal text
        def repl(m):
            value = build(m)
            if value:
                found.append(value)
            return ' ' * len(m.group())
        text = pattern.sub(repl, text)

    take(ISO_DATE_RE, lambda m: valid_date(m.group(1), m.group(2), m.group(3)))

    def dmy(m):
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        if mo > 12 >= d:
            d, mo = mo, d
        return valid_date(y, mo, d)

    take(DMY_RE, dmy)
    take(ES_DATE_RE, lambda m: valid_date(m.group(3), MONTHS[m.group(2).lower()], m.group(1)))
    take(EN_DATE_RE, lambda m: valid_date(m.group(3), MONTHS.get(m.group(1).lower()) or EN_ABBR[m.group(1).lower()], m.group(2)))
    take(EN_DATE2_RE, lambda m: valid_date(m.group(3), MONTHS.get(m.group(2).lower()) or EN_ABBR[m.group(2).lower()], m.group(1)))
    take(MONTH_YEAR_RE, lambda m: valid_date(m.group(2), MONTHS[m.group(1).lower()]))
    return found


def is_initial(text, pos):
    i = pos - 1
    while i >= 0 and text[i] in ' \t"\'“‘«*_[(':
        i -= 1
    return i < 0 or text[i] in INITIAL_CHARS


def word_key(word, cache):
    k = cache.get(word)
    if k is None:
        w = word.strip(WORD_EDGE)
        f = w.translate(FOLD)
        if (len(f) < 3 or f in STOP or '_' in f or not f.isalpha() and not f.replace('-', '').replace("'", '').isalpha()
                or w.endswith('ó') or len(f) > 5 and f.endswith(VERB_ENDINGS)):
            k = ''
        else:
            k = singular(f)
        cache[word] = k
    return k


def subsumed(ck, freq):
    parts = tuple(ck.split('-'))
    n = freq[parts]
    content = [i for i, p in enumerate(parts) if p not in CONNECTORS]
    if len(content) < 3:
        return False
    head = parts[:content[-1]]
    while head and head[-1] in CONNECTORS:
        head = head[:-1]
    tail = parts[content[1]:]
    return freq.get(head, 0) >= 2 * n or freq.get(tail, 0) >= 2 * n


def keyphrases(text, exclude=(), limit=TOP_CONCEPTS, exclude_words=()):
    low = text.lower()
    freq, first, wfreq, wdeg = Counter(), {}, Counter(), Counter()
    cache = {}
    total = 0
    def emit(part):
        while part and not part[-1][0]:
            part.pop()
        if not part:
            return
        pk = tuple(p[0] or p[1] for p in part)
        freq[pk] += 1
        if pk not in first:
            first[pk] = ' '.join(p[1] for p in part)
        size = sum(1 for p in part if p[0])
        for p in part:
            if p[0]:
                wfreq[p[0]] += 1
                wdeg[p[0]] += size
        if size == 3:
            idx = [i for i, p in enumerate(part) if p[0]]
            for sub in (part[:idx[1] + 1], part[idx[1]:]):
                sk = tuple(p[0] or p[1] for p in sub)
                freq[sk] += 1
                if sk not in first:
                    first[sk] = ' '.join(p[1] for p in sub)

    for chunk in SPLIT_RE.split(low):
        part, size = [], 0
        for w in chunk.split():
            k = cache.get(w)
            if k is None:
                k = word_key(w, cache)
            if k:
                part.append((k, w.strip(WORD_EDGE)))
                size += 1
                total += 1
                if size == 3:
                    emit(part)
                    part, size = [], 0
            elif part and part[-1][0] and w in CONNECTORS:
                part.append(('', w))
            elif part:
                emit(part)
                part, size = [], 0
        emit(part)
    min_freq = 2 if total > 300 else 1
    scored = []
    for pk, n in freq.items():
        if n < min_freq:
            continue
        ck = '-'.join(pk)
        if ck in exclude or len(pk) == 1 and (len(pk[0]) < 4 or n < 2) or exclude_words and any(k in exclude_words for k in pk):
            continue
        score = sum(wdeg[k] / wfreq[k] for k in pk if k not in CONNECTORS) * (1 + math.log(n))
        scored.append((-score, ck, first[pk], n))
    scored = [x for x in scored if not subsumed(x[1], freq)]
    scored.sort()
    out, seen = [], set()
    for neg, ck, display, n in scored:
        if ck in seen:
            continue
        seen.add(ck)
        out.append((ck, display, round(-neg, 3), n))
        if len(out) >= limit:
            break
    return out


def person_candidates(text):
    lower_seen = {w.translate(FOLD) for w in set(LOWER_RE.findall(text))}
    stats = {}
    for m in NAME_RE.finditer(text):
        raw = m.group()
        tokens = raw.split()
        start = m.start()
        offset = 0
        titled = blocked = False
        while tokens:
            f0 = tokens[0].lower().translate(FOLD)
            if f0 in TITLE_WORDS:
                titled, blocked = True, False
            elif f0 in BLOCK_NAME:
                blocked = True
            elif f0 not in NOT_NAME and f0 not in NAME_CONNECT:
                break
            offset += len(tokens[0]) + 1
            tokens = tokens[1:]
        while tokens and (tokens[-1].lower().translate(FOLD) in NOT_NAME or tokens[-1].lower().translate(FOLD) in NAME_CONNECT):
            tokens = tokens[:-1]
        if not tokens or blocked:
            continue
        tokens = [t[:-2] if t.endswith(("'s", '’s')) else t for t in tokens]
        folded = [t.lower().translate(FOLD) for t in tokens]
        caps = [f for f, t in zip(folded, tokens) if t[0].isupper()]
        if any(f in NOT_NAME for f in caps) or len(caps) > 4:
            continue
        pos = start + offset
        before = text[max(0, pos - 40):pos].lower().translate(FOLD)
        if '\n' in before:
            before = before.rsplit('\n', 1)[1]
        after = text[m.end():m.end() + 30].lower().translate(FOLD)
        line_start = text.rfind('\n', 0, pos) + 1
        speaker = not text[line_start:pos].strip(' \t-*>[]0123456789:/,.') and after.startswith(':') and len(caps) <= 3
        strong = bool(titled or CUE_BEFORE_RE.search(before) or CUE_AFTER_RE.match(after) or speaker)
        initial = is_initial(text, pos) and not strong
        location = bool(LOCATION_BEFORE_RE.search(before)) and not strong
        place = bool(PLACE_BEFORE_RE.search(before)) and not strong
        name = ' '.join(tokens)
        k = '-'.join(f for f in folded)
        st = stats.get(k)
        if st is None:
            st = stats[k] = {'count': 0, 'surfaces': Counter(), 'strong': False, 'free': False, 'located': True, 'placed': True,
                             'pos': pos, 'caps': caps}
        st['count'] += 1
        st['surfaces'][name] += 1
        st['strong'] |= strong
        st['free'] |= not initial
        st['located'] &= location
        st['placed'] &= place
    people = {}
    for k, st in stats.items():
        caps = st['caps']
        fn = caps[0] in FIRST_NAMES or len(caps) > 1 and any(len(c) >= 4 and c.endswith('ez') for c in caps)
        namelike = all(c in FIRST_NAMES or c not in lower_seen for c in caps)
        if st['located'] and not fn or st['placed'] and len(caps) == 1:
            continue
        if len(caps) == 1:
            ok = (st['strong'] and namelike) or (fn and namelike)
        else:
            ok = (fn and namelike) or (st['strong'] and namelike) or (namelike and st['free'] and st['count'] >= 2)
        if ok:
            people[k] = st
    singles = {k: st for k, st in people.items() if '-' not in k}
    fulls = {}
    for k in people:
        if '-' in k:
            fulls.setdefault(k.split('-', 1)[0], []).append(k)
    for k, st in singles.items():
        owners = fulls.get(k, [])
        if len(owners) == 1:
            target = people[owners[0]]
            target['count'] += st['count']
            target['pos'] = min(target['pos'], st['pos'])
            del people[k]
    return {k: (min(st['surfaces'].items(), key=lambda kv: (-kv[1], kv[0]))[0], st['count'], st['pos'])
            for k, st in people.items()}


def clean(text, urls=None, emails=None):
    text = (text or '')[:MAX_SCAN]
    if '```' in text or '~~~' in text:
        text = blank(text, CODE_RE)
    if '`' in text:
        text = blank(text, INLINE_CODE_RE)
    if '://' in text or 'www.' in text:
        text = blank(text, URL_RE, urls)
    if '@' in text:
        text = blank(text, EMAIL_RE, emails)
    return text


def scan(text, limit=TOP_CONCEPTS, people_text=None):
    urls, emails = [], []
    text = clean(text, urls, emails)
    wikis = []
    for m in WIKI_RE.finditer(text) if '[[' in text else ():
        target = m.group(1).strip()
        heading = (m.group(2) or '').strip()
        alias = (m.group(3) or '').strip()
        if target or heading:
            wikis.append((target, heading, alias, m.start()))
    tags = Counter()
    tag_names = {}
    tag_pos = {}
    for m in TAG_RE.finditer(text) if '#' in text else ():
        raw = (m.group(1) or m.group(2) or '').strip().strip('/-')
        if not raw or HEX_RE.fullmatch(raw):
            continue
        k = concept_key(raw)
        if not k:
            continue
        tags[k] += 1
        tag_names.setdefault(k, raw)
        tag_pos.setdefault(k, m.start())
    mentions = Counter(m.group(1) for m in MENTION_RE.finditer(text)) if '@' in text else Counter()
    dates = find_dates(text)
    if people_text is None:
        people = person_candidates(text)
    else:
        people = person_candidates(clean(people_text))
    person_words = {singular(fold(w)) for name, _, _ in people.values() for w in re.split(r'[\W_]+', name) if w}
    if wikis:
        text = blank(text, WIKI_RE)
    if '#' in text or '@' in text:
        text = TAG_STRIP_RE.sub(' ', text)
    concepts = keyphrases(text, set(tags), limit, person_words)
    return {
        'people': people,
        'concepts': concepts,
        'tags': {k: (tag_names[k], n, tag_pos[k]) for k, n in tags.items()},
        'wikilinks': wikis,
        'mentions': mentions,
        'emails': Counter(e.lower().rstrip('.') for e in emails),
        'urls': sorted({u.rstrip('.,;:!?)') for u in urls}),
        'dates': sorted(set(dates)),
    }


def entities(text):
    found = scan(text)
    people = sorted(found['people'].values(), key=lambda p: (-p[1], key(p[0])))
    tags = sorted(found['tags'].values(), key=lambda t: (-t[1], concept_key(t[0])))
    wikis, seen = [], set()
    for target, heading, _, _ in found['wikilinks']:
        if target and target.lower() not in seen:
            seen.add(target.lower())
            wikis.append(target)
    return {
        'people': [p[0] for p in people],
        'concepts': [c[1] for c in found['concepts']],
        'tags': [t[0] for t in tags],
        'wikilinks': wikis,
        'mentions': sorted(found['mentions'], key=lambda m: (-found['mentions'][m], m.lower())),
        'emails': sorted(found['emails']),
        'urls': found['urls'],
        'dates': found['dates'],
    }


ROLES_ES = {
    'esposa': 'wife', 'esposo': 'husband', 'marido': 'husband', 'mujer': 'wife', 'pareja': 'partner', 'novia': 'girlfriend',
    'novio': 'boyfriend', 'prometida': 'fiancee', 'prometido': 'fiance', 'hermana': 'sister', 'hermano': 'brother',
    'mama': 'mother', 'madre': 'mother', 'papa': 'father', 'padre': 'father', 'hijo': 'son', 'hija': 'daughter',
    'jefe': 'boss', 'jefa': 'boss', 'amigo': 'friend', 'amiga': 'friend', 'mejor amigo': 'best_friend',
    'mejor amiga': 'best_friend', 'socio': 'business_partner', 'socia': 'business_partner', 'primo': 'cousin',
    'prima': 'cousin', 'tio': 'uncle', 'tia': 'aunt', 'abuelo': 'grandfather', 'abuela': 'grandmother', 'sobrino': 'nephew',
    'sobrina': 'niece', 'suegro': 'father_in_law', 'suegra': 'mother_in_law', 'cunado': 'brother_in_law',
    'cunada': 'sister_in_law', 'companero de trabajo': 'colleague', 'companera de trabajo': 'colleague',
    'companero': 'colleague', 'companera': 'colleague', 'colega': 'colleague', 'cliente': 'client', 'perro': 'dog',
    'perra': 'dog', 'gato': 'cat', 'gata': 'cat', 'mascota': 'pet', 'terapeuta': 'therapist', 'mentor': 'mentor',
    'mentora': 'mentor', 'cofundador': 'cofounder', 'cofundadora': 'cofounder',
}
ROLES_EN = {
    'wife': 'wife', 'husband': 'husband', 'partner': 'partner', 'girlfriend': 'girlfriend', 'boyfriend': 'boyfriend',
    'fiancee': 'fiancee', 'fiance': 'fiance', 'sister': 'sister', 'brother': 'brother', 'mom': 'mother', 'mum': 'mother',
    'mother': 'mother', 'dad': 'father', 'father': 'father', 'son': 'son', 'daughter': 'daughter', 'boss': 'boss',
    'manager': 'boss', 'friend': 'friend', 'best friend': 'best_friend', 'cousin': 'cousin', 'uncle': 'uncle',
    'aunt': 'aunt', 'grandma': 'grandmother', 'grandmother': 'grandmother', 'grandpa': 'grandfather',
    'grandfather': 'grandfather', 'nephew': 'nephew', 'niece': 'niece', 'colleague': 'colleague', 'coworker': 'colleague',
    'co-worker': 'colleague', 'cofounder': 'cofounder', 'co-founder': 'cofounder', 'client': 'client', 'dog': 'dog',
    'cat': 'cat', 'pet': 'pet', 'therapist': 'therapist', 'mentor': 'mentor',
}
UNIQUE_ROLES = {'wife', 'husband', 'partner', 'girlfriend', 'boyfriend', 'fiancee', 'fiance', 'mother', 'father', 'boss',
                'best_friend', 'therapist'}
PROFESSIONS = words_set('''
abogado abogada ingeniero ingeniera profesor profesora maestro maestra medico medica doctor doctora enfermero enfermera
estudiante desarrollador desarrolladora programador programadora disenador disenadora arquitecto arquitecta contador contadora
periodista escritor escritora psicologo psicologa emprendedor emprendedora fundador fundadora cofundador cofundadora gerente
director directora consultor consultora analista cientifico cientifica fotografo fotografa musico chef cocinero cocinera
vendedor vendedora freelance freelancer investigador investigadora economista administrador administradora traductor
traductora editor editora productor productora entrenador entrenadora coach tutor tutora piloto mecanico electricista
carpintero agricultor farmaceutico dentista odontologo odontologa veterinario veterinaria artista actor actriz bailarin
bailarina marketer mercadologo publicista ceo cto cfo coo
engineer developer programmer designer teacher professor nurse lawyer attorney student writer journalist manager founder
consultant analyst scientist researcher architect accountant entrepreneur photographer musician artist cook salesperson
psychologist therapist economist administrator officer specialist coordinator intern pharmacist dentist veterinarian pilot
mechanic electrician carpenter plumber farmer translator producer recruiter trainer copywriter dev devops sre physician
surgeon actress dancer singer
''')
LANGUAGES = ('ingles|espanol|castellano|frances|aleman|portugues|italiano|chino|mandarin|japones|ruso|arabe|coreano|catalan|'
             'euskera|gallego|english|spanish|french|german|portuguese|italian|chinese|japanese|russian|arabic|korean')
STYLE_WORDS = re.compile(
    r'\b(?:emoji|emojis|emoticon|emoticones|emoticons|markdown|jerga|slang|tecnicismo|tecnicismos|jargon|mayuscula|mayusculas|'
    r'caps|vinetas|bullet|bullets|tabla|tablas|table|tables|lista|listas|list|lists|formal|informal|' + LANGUAGES +
    r'|sarcasmo|sarcasm|disclaimer|disclaimers|advertencia|advertencias|relleno|filler|saludo|saludos|greeting|greetings|'
    r'despedida|resumen|summary|summaries|negrita|negritas|bold|titulo|titulos|heading|headings|guion largo|em dash|dashes|'
    r'ingles|tu|usted|tutea|tuteame|breve|corto|cortas|corta|concise|concisa|conciso|short|brief|largo|larga|long|verbose)\b')
PERSIST_RE = re.compile(
    r'\b(?:siempre|nunca|jamas|de ahora en adelante|a partir de ahora|desde ahora|en adelante|en el futuro|cada vez que|'
    r'en todas tus respuestas|en tus respuestas|always|never|from now on|going forward|in the future|'
    r'in all (?:your )?(?:answers|responses|replies)|in your (?:answers|responses|replies)|every time)\b')
ASSIST_RE = re.compile(
    r'\b(?:respondeme|respondame|responde|responder|respondas|contestame|contesta|contestes|hablame|hables|escribeme|escribe|'
    r'escribas|usa|uses|utiliza|utilices|evita|evites|incluye|incluyas|agrega|agregues|anade|anadas|pon|pongas|dame|des|explica|'
    r'expliques|tratame|trates|llamame|dirigete|tutea|tuteame|manten|sigue|formatea|seas|se breve|answer|respond|reply|write|use|'
    r'avoid|include|add|talk|speak|address|explain|format|keep|give|be|refer to me|call me|treat me)\b')
NEG_IMPERATIVE_RE = re.compile(
    r"\b(?:no (?:me )?(?:uses|utilices|incluyas|agregues|anadas|pongas|escribas|hables|respondas|digas|trates|llames)|evita|evites|"
    r"deja de (?:usar|poner|incluir|escribir)|don't (?:ever )?(?:use|add|include|write|say|put|call)|do not (?:use|add|include|write|"
    r"say|put|call)|stop (?:using|adding|including|writing|saying)|avoid|never (?:use|add|include|write|say|put))\b")
PREFER_YOU_RE = re.compile(
    r"\b(?:prefiero que|me gusta que|me gustaria que siempre|quiero que (?:siempre|nunca|me respondas|me hables|me escribas|uses|"
    r"escribas|seas|me trates|me llames|me tutees)|no quiero que (?:uses|escribas|me|incluyas|pongas)|i prefer (?:that )?you|"
    r"i(?:'d| would) (?:like|prefer) (?:it if )?you (?:to )?(?:always|never)?|i want you to (?:always|never)|please always|"
    r"please never|por favor siempre|por favor nunca)\b")
LANG_REPLY_RE = re.compile(r'\b(?:respondeme|responde|contestame|hablame|escribeme|answer|respond|reply|talk to me|write)\b.*\b(?:en|in) (?:' + LANGUAGES + r')\b')
HABIT_ADV = (r'(?:siempre|nunca|jamas|todos los dias|todas las mananas|todas las noches|cada dia|cada manana|cada noche|'
             r'cada semana|a diario|normalmente|usualmente|generalmente|casi siempre|los fines de semana)')
HABIT_ES_RE = re.compile(r'\b(?:yo\s+)?' + HABIT_ADV + r'\s+(?:me\s+|lo\s+|la\s+|le\s+|nos\s+)?([a-z]{2,}(?:o|oy|amos|emos|imos))\b')
HABIT_ES2_RE = re.compile(r'^(?:yo\s+)?(?:me\s+|nos\s+)?([a-z]{2,}(?:o|oy|amos|emos|imos))\b.*\b' + HABIT_ADV + r'\b')
HABIT_ES3_RE = re.compile(r'\b(?:suelo|solemos|acostumbro a|acostumbro|tengo la costumbre de|tengo el habito de)\s+')
HABIT_EN_RE = re.compile(r"\b(?:i|we)\s+(?:always|never|usually|often|normally|rarely|generally|tend to|typically)\s+(?!think|know|want|need|forget|have to)[a-z]+")
HABIT_EN2_RE = re.compile(r"\b(?:every|each)\s+(?:day|morning|night|evening|week|weekend|monday|sunday)\s*,?\s+(?:i|we)\s+[a-z]+|"
                          r"\b(?:i|we)\s+[a-z]+(?:\s+[a-z]+){0,4}\s+every\s+(?:day|morning|night|evening|week|weekend)\b")
NOT_VERB_O = words_set('todo mucho poco algo esto eso nuevo mismo solo tiempo dinero trabajo cuando otro primero claro '
                       'cierto bueno malo largo nunca siempre medio rapido lento tanto cada')
HEDGE_RE = re.compile(r"\b(?:creo que|quizas|quiza|tal vez|a lo mejor|probablemente|puede que|supongo|maybe|perhaps|probably|"
                      r"i think|i guess|i suppose|might|possibly)\b")
SKIP_MESSAGE_RE = re.compile(
    r"^\s*(?:por favor,?\s+)?(?:traduce|traducir|traduceme|translate|corrige|corregir|corrigeme|correct|revisa|revisar|proofread|"
    r"resume|resumeme|resumir|summarize|summarise|parafrasea|paraphrase|reescribe|reescribir|rewrite|redacta|redactar|draft|"
    r"escribe (?:un|una|el|la|me)|escribeme (?:un|una)|write (?:a|an|the|me)|genera|generate|crea (?:un|una)|create (?:a|an)|"
    r"act as|actua como|imagina|imagine|pretend|finge|roleplay|juego de rol|haz de cuenta|simula|simulate)\b")
SKIP_SENTENCE_RE = re.compile(r"^\s*(?:¿|si |if |what if|supongamos|suppose|imagina|imagine|en un mundo|in a world|"
                              r"el personaje|the character|mi personaje|my character)")
SECRET_RE = re.compile(r"(?:contrasena|password|passwd|clave|api[ _-]?key|token|secret|secreto|pin)\s*(?:es|is|:|=)")
SECRET_TOKEN_RE = re.compile(r"\b(?:sk|pk|rk|ghp|gho|xox[abp])[-_][A-Za-z0-9_\-]{12,}|\bAKIA[0-9A-Z]{12,}|\b[A-Fa-f0-9]{32,}\b")
SENSITIVE_RE = re.compile(
    r'\b(?:diabetes|cancer|depresion|depression|ansiedad|anxiety|terapia|therapy|medicamento|medicamentos|medication|diagnostico|'
    r'diagnosis|diagnosed|enfermedad|illness|embarazada|pregnant|vih|hiv|bipolar|tdah|adhd|autismo|autism|religion|catolico|'
    r'catolica|cristiano|cristiana|musulman|judio|judia|ateo|atea|christian|muslim|jewish|atheist|gay|lesbiana|lesbian|'
    r'bisexual|transgenero|transgender|orientacion sexual|sexual orientation|salario|sueldo|salary|deuda|deudas|debt|'
    r'cuenta bancaria|bank account|tarjeta de credito|credit card|cedula|pasaporte|passport|ssn|dni|voto por|i vote for|'
    r'partido politico|political party)\b')
FIRST_PERSON_RE = re.compile(r"\b(?:yo|me|mi|mis|tengo|tuve|fui|voy|iremos|nos|nuestro|nuestra|nuestros|i|my|we|our|i'm|i'll|i've|we're|we'll)\b")
SENT_SPLIT_RE = re.compile(r'(?<=[.!?…])\s+|\n+|;\s*')
QUOTED_RE = re.compile(r'"[^"\n]{0,300}"|“[^”\n]{0,300}”|«[^»\n]{0,300}»')
STRICT_STOP = re.compile(
    r"[,.;:!?()\[\]\"“”«»]|\s+(?:y|e|o|pero|porque|aunque|desde|hace|con|cuando|donde|mientras|ya que|pues|asi que|and|or|but|"
    r"because|since|for|with|when|where|while|although|so|as|que|who|which|that|hasta|until|durante|during|cerca|near|now|ahora|"
    r"hoy|today|actualmente|currently|right now|todavia|still|tambien|too|also|at|in|on|en|para|como|as a|as an|la semana|"
    r"el mes|el ano|la proxima|el proximo|el pasado|la pasada|este|esta|last|next|this|ayer|yesterday|manana|tomorrow)\b")
LOOSE_STOP = re.compile(r"[.;!?()\[\]\"“”«»]|\s+(?:pero|porque|aunque|but|because|although|ya que|so that)\b")
PREF_STOP = re.compile(
    r"[.;:!?()\[\]\"“”«»]|\s+(?:pero|porque|aunque|cuando|si|but|because|although|when|if|since|desde|hace|mas que|more than|"
    r"than|que|that|especialmente|especially|sobre todo)\b")
PREFER_STOP = re.compile(PREF_STOP.pattern + r"|\s+(?:a|al|over|en vez de|instead of|antes que|rather than)\s+")
THIRD_PERSON_RE = re.compile(r"[^\W\d_](?:ó|ió)\b")
DESCRIBE_RE = re.compile(r"^(?:you|tu|usted|eres|you're|you are|el|ella|he|she|they|ellos|it|esto|this)\b")
LIST_SEP_RE = re.compile(r",\s*|\s+(?:y|e|o|ni|and|or|nor)\s+")
CLAUSE_START = words_set('no nunca ya tampoco pero aunque manana hoy ayer luego despues entonces ahora voy vamos tengo quiero '
                         'not never but tomorrow today yesterday then now will')
SHORT_HORIZON_RE = re.compile(r"(?<!la )(?<!cada )(?<!las )\b(?:manana|hoy|esta tarde|esta noche|ahorita|ahora mismo|en un rato|"
                              r"luego|tomorrow|today|tonight|later today|this afternoon|this evening|right now)\b")
LEADING = words_set('el la los las lo un una unos unas the a an mucho muchisimo muchisima bastante demasiado really so very '
                    'to de del al')
PRONOUN_VALUES = words_set("it this that you them him her eso esto lo la que cuando como how when what why where which who "
                           "the idea tu te ustedes usted everything todo nada anything something algo")
NAME_TOKEN_RE = re.compile(r"[ \t]*([^\W\d_][\w'’\-]*)")
def strip_leading(words):
    while words and fold(words[0]) in LEADING:
        words = words[1:]
    return words


def cut(s, f, start, stop, max_words):
    m = stop.search(f, start)
    end = m.start() if m else len(s)
    words = s[start:end].split()
    words = strip_leading(words)[:max_words]
    while words and fold(words[-1]) in STOP:
        words = words[:-1]
    value = ' '.join(words).strip(' ,:-–—\'"')
    return value if re.search(r'[^\W\d_]', value) else ''


def name_value(s, start, require_cap=True, limit=3):
    out, pos = [], start
    while len(out) < limit:
        m = NAME_TOKEN_RE.match(s, pos)
        if not m:
            break
        tok = m.group(1)
        f = fold(tok)
        if f in NAME_CONNECT and out:
            nxt = NAME_TOKEN_RE.match(s, m.end())
            if nxt and nxt.group(1)[:1].isupper():
                out.append(tok)
                pos = m.end()
                continue
            break
        if f in NOT_NAME or f in STOP or f in PROFESSIONS:
            break
        if require_cap and not tok[:1].isupper():
            break
        out.append(tok)
        pos = m.end()
    while out and fold(out[-1]) in NAME_CONNECT:
        out.pop()
    if not out:
        return ''
    return ' '.join(t if t[:1].isupper() else t[:1].upper() + t[1:] for t in out)


def last_word_key(value):
    words = [w for w in re.split(r'[\W_]+', fold(value)) if w and w not in STOP and len(w) > 2]
    return singular(words[-1])[:12] if words else key(value)[:24]


def short_key(value, n=3):
    words = [w for w in re.split(r'[\W_]+', fold(value)) if w and w not in STOP and not w.isdigit()]
    return '-'.join(singular(w) for w in words[:n]) or key(value)[:24]


def fact(category, attribute, value, confidence, about=(), when=None, **extra):
    out = {'category': category, 'attribute': attribute, 'value': value, 'confidence': confidence, 'about': list(about)}
    if when:
        out['when'] = when
    out.update(extra)
    return out


def rx(pattern):
    return re.compile(pattern)


ROLE_ES_ALT = '|'.join(sorted(ROLES_ES, key=len, reverse=True))
ROLE_EN_ALT = '|'.join(sorted(ROLES_EN, key=len, reverse=True))
NAME_RULES = [
    (rx(r"\b(?:me llamo|mi nombre es|my name is|my name's)\s+"), 'name', 0.8, 'free'),
    (rx(r"\b(?:llamame|puedes llamarme|call me|you can call me|mis amigos me dicen|my friends call me)\s+"), 'nickname', 0.7, 'cap'),
    (rx(r"^(?:hola,?\s+|hi,?\s+|hello,?\s+)?(?:soy|i'm|i am)\s+(?=[a-z])"), 'name', 0.6, 'first'),
]
LIVE_RULES = [
    (rx(r"\b(?P<neg>ya no |no |tampoco )?(?:vivo|resido|estoy viviendo|vivimos)\s+en\s+"), 'lives_in'),
    (rx(r"\bi\s+(?P<neg>don't |do not |dont |no longer )?(?:live|reside)\s+in\s+"), 'lives_in'),
    (rx(r"\b(?:i|we)(?:'m| am|'re| are)\s+(?P<neg>no longer |not )?living\s+in\s+"), 'lives_in'),
    (rx(r"\b(?:me mude|me he mudado|me voy a mudar|nos mudamos|nos hemos mudado|me vine a vivir|me fui a vivir|nos fuimos a vivir|"
        r"nos vinimos a vivir|ahora vivo|ahora vivimos)\s+(?:a|en)\s+"), 'lives_in'),
    (rx(r"\b(?:i|we)(?:'ve| have)?\s+(?:just\s+|recently\s+)?moved\s+to\s+"), 'lives_in'),
    (rx(r"\b(?:now|currently)\s+(?:i|we)\s+live\s+in\s+"), 'lives_in'),
    (rx(r"\bsoy\s+(?:de|originari[oa] de|oriund[oa] de)\s+"), 'from'),
    (rx(r"\bi(?:'m| am)\s+(?:originally\s+)?from\s+"), 'from'),
    (rx(r"\b(?:naci|i was born)\s+(?:en|in)\s+"), 'born_in'),
]
WORK_RULES = [
    (rx(r"\b(?P<neg>ya no |no )?trabajo\s+(?:en|para)\s+(?!(?:el |un |mi )?proyecto\b)"), 'works_at', 0.75),
    (rx(r"\bi\s+(?P<neg>don't |do not |no longer )?(?:still\s+)?work\s+(?:at|for)\s+"), 'works_at', 0.75),
    (rx(r"\b(?:sigo|continuo|seguimos|sigo estando)\s+trabajando\s+(?:en|para)\s+(?!(?:el |un |mi )?proyecto\b)"), 'works_at', 0.75),
    (rx(r"\b(?:estoy|estamos)\s+trabajando\s+(?:para\s+|en\s+(?=[^.,;]{2,50}?\b(?:como|de)\s))(?!(?:el |un |una |mi )?proyecto\b)"), 'works_at', 0.7),
    (rx(r"\bi(?:'m| am)\s+(?P<neg>no longer )?(?:still\s+)?(?:working|employed)\s+(?:at|for|by)\s+"), 'works_at', 0.75),
    (rx(r"\b(?:me contrataron en|empece a trabajar en|entre a trabajar en|i joined|i started working at|i got a job at|i was hired by)\s+"), 'works_at', 0.7),
    (rx(r"\b(?P<neg>renuncie a mi trabajo en|deje de trabajar en|deje mi trabajo en|i quit my job at|i left my job at|i resigned from|i stopped working at)\s+"), 'works_at', 0.7),
]
JOB_RULES = [
    (rx(r"\btrabaj(?:o|ando)\s+como\s+(?:un |una )?"), 0.75, False),
    (rx(r"\btrabaj(?:o|ando)\s+de\s+"), 0.7, True),
    (rx(r"\btrabaj(?:o|ando)\b[^.,;]{2,50}?\b(?:como|de)\s+(?:un |una )?(?=[a-z]+\b)"), 0.7, True),
    (rx(r"\b(?:i\s+(?:still\s+)?work|i(?:'m| am)\s+(?:still\s+)?working)\b[^.,;]{2,50}?\bas\s+(?:an?\s+)?"), 0.7, False),
    (rx(r"\bme dedico a\s+(?:la |el )?"), 0.7, False),
    (rx(r"\bmi (?:trabajo|profesion|cargo|puesto|rol|ocupacion) es\s+(?:de\s+)?"), 0.75, False),
    (rx(r"\bi\s+work\s+as\s+(?:an?\s+)?"), 0.75, False),
    (rx(r"\bmy (?:job|role|title|position|profession|occupation) is\s+(?:an?\s+)?"), 0.75, False),
    (rx(r"\b(?:soy|i'm|i am)\s+(?:un |una |an? )?(?=[a-z])"), 0.6, True),
]
AGE_RULES = [rx(r"\btengo\s+(\d{1,3})\s+anos\b"), rx(r"\bi(?:'m| am)\s+(\d{1,3})\s+years?\s+old\b")]
BIRTHDAY_RULES = [rx(r"\b(?:naci el|mi cumpleanos es el|mi cumpleanos es|my birthday is|i was born on)\s+")]
PREF_ES = rx(r"\b(?P<neg>no |nunca |ya no |tampoco )?me\s+(?:(?:gusta|gustan)\s+mucho|gusta|gustan|encanta|encantan|fascina|"
             r"fascinan|interesa|interesan|apasiona|apasionan)\s+")
PREF_ES_VERB = {'gusta': 'like', 'gustan': 'like', 'encanta': 'love', 'encantan': 'love', 'fascina': 'love', 'fascinan': 'love',
                'interesa': 'interest', 'interesan': 'interest', 'apasiona': 'love', 'apasionan': 'love'}
PREF_RULES = [
    (rx(r"\b(?:odio|detesto|aborrezco|no soporto|no aguanto)\s+"), 'hate'),
    (rx(r"\bprefiero\s+(?!que\b)"), 'prefer'),
    (rx(r"\b(?:adoro|amo)\s+(?!a\b)"), 'love'),
    (rx(r"\bsoy\s+(?:muy\s+)?(?:fan|fanatic[oa]|amante|aficionad[oa])\s+(?:de|del|a|al)\s+"), 'love'),
    (rx(r"\bi\s+(?P<neg>don't |do not |dont |no longer |never )?(?:really\s+)?(?P<verb>like|love|enjoy|adore|hate|dislike|detest|prefer)\s+(?!you\b|it\b|this\b|that\b|how\b|when\b|what\b|the way\b)"), None),
    (rx(r"\bi\s+(?:can't|cannot|cant)\s+stand\s+"), 'hate'),
    (rx(r"\bi(?:'m| am)\s+(?:a\s+)?(?:big\s+|huge\s+)?fan\s+of\s+"), 'love'),
    (rx(r"\bi(?:'m| am)\s+not\s+(?:a\s+)?(?:big\s+)?fan\s+of\s+"), 'dislike'),
    (rx(r"\bi(?:'m| am)\s+(?:really\s+)?into\s+"), 'like'),
]
EN_POLARITY = {'like': 'like', 'love': 'love', 'enjoy': 'like', 'adore': 'love', 'hate': 'hate', 'dislike': 'dislike',
               'detest': 'hate', 'prefer': 'prefer'}
GOAL_VERBS_ES = (r'(?:aprender|ser|convertirme|llegar|lograr|conseguir|vivir|viajar|mudarme|tener|empezar|comenzar|dejar|bajar|'
                 r'perder|ahorrar|comprar|construir|lanzar|terminar|estudiar|correr|casarme|emprender|montar|abrir|jubilarme|'
                 r'retirarme|cambiar de trabajo|conocer|visitar|publicar|escribir un libro|graduarme|independizarme|crecer)')
GOAL_VERBS_EN = (r'(?:learn|become|start|quit|move|travel|buy|save|launch|lose|run|finish|study|write a book|open|retire|marry|'
                 r'get married|visit|live|grow|graduate|publish|found|become)')
GOAL_RULES = [
    (rx(r"\bmi (?:meta|objetivo|sueno|proposito|plan)(?: principal| para [\w ]{1,25})? es\s+"), 0.75, False),
    (rx(r"\bmy (?:main |biggest )?(?:goal|dream|plan|objective|aim)(?: for [\w ]{1,25})? is\s+(?:to\s+)?"), 0.75, False),
    (rx(r"\b(?P<neg>ya no |no )?(?:quiero|deseo|espero|sueno con|me gustaria)\s+(?=" + GOAL_VERBS_ES + r"\b)"), 0.6, True),
    (rx(r"\b(?:voy a|planeo|pienso|tengo planeado|estoy planeando|tengo pensado)\s+(?=" + GOAL_VERBS_ES + r"\b)"), 0.6, True),
    (rx(r"\bi\s+(?P<neg>don't |do not |no longer )?(?:really\s+)?(?:want|wanna|hope|plan|intend|aim|dream)\s+(?:to|of)\s+(?=" + GOAL_VERBS_EN + r"\b)"), 0.6, True),
    (rx(r"\bi(?:'m| am)\s+(?:going|planning|hoping)\s+to\s+(?=" + GOAL_VERBS_EN + r"\b)"), 0.6, True),
]
LEARN_RULES = [rx(r"\b(?:estoy aprendiendo|estoy estudiando|aprendo|i(?:'m| am) (?:learning|studying))\s+(?:a\s+)?")]
DECISION_RULES = [
    (rx(r"\b(?:decidi|he decidido|hemos decidido|decidimos|tome la decision de|tomamos la decision de|ya decidi)\s+(?:que\s+)?"), 0.65),
    (rx(r"\b(?:vamos a usar|voy a usar|usaremos|vamos a utilizar|utilizaremos|elegimos|escogimos|nos quedamos con|me quedo con|opte por|"
        r"optamos por|nos decidimos por|me decidi por)\s+"), 0.65),
    (rx(r"\b(?:i|we)(?:'ve| have)?\s+decided\s+(?:to\s+|that\s+|on\s+)?"), 0.65),
    (rx(r"\bwe(?:'ll| will| are going to|'re going to)\s+(?:use|go with|adopt|switch to)\s+"), 0.65),
    (rx(r"\b(?:i|we)(?:'m| am|'re| are)\s+going\s+with\s+"), 0.6),
    (rx(r"\b(?:i|we)\s+(?:chose|picked|opted for|settled on|switched to)\s+"), 0.6),
    (rx(r"^(?:ok,?\s+|okay,?\s+|bien,?\s+|vale,?\s+)?(?:let's|lets)\s+(?:use|go with)\s+"), 0.55),
    (rx(r"^(?:ok,?\s+|okay,?\s+|bien,?\s+|vale,?\s+)?usemos\s+"), 0.55),
]
PROJECT_RULES = [rx(r"\b(?:estoy trabajando en|estoy construyendo|estoy desarrollando|estoy creando|trabajo en el proyecto|"
                    r"mi proyecto(?: actual)?(?: se llama| es)?|i(?:'m| am) (?:currently )?(?:working on|building|developing|creating)|"
                    r"my (?:current |side )?project(?: is called| is| called)?)\s+")]
PROJECT_SKIP = re.compile(r"^(?:esto|este|esta|eso|this|that|it|una? funcion|el codigo|the code|a function|un script|a script|"
                          r"tu|your|lo que|what|how|como)\b")
SKILL_RULES = [
    (rx(r"\b(?:hablo|domino|i speak|i'm fluent in|i am fluent in)\s+(?:(?:un poco de|algo de|a bit of|some)\s+)?(?=(?:" + LANGUAGES + r")\b)"), 'speaks'),
    (rx(r"\b(?:soy expert[oa] en|tengo experiencia en|tengo experiencia con|tengo \d+ anos de experiencia (?:en|con)|se programar en|"
        r"programo en|i(?:'m| am) (?:an expert|experienced|proficient|good) (?:in|at|with)|i have (?:\d+ years of )?experience "
        r"(?:in|with)|i know how to|i can (?:code|program) in)\s+"), 'skill'),
]
REMEMBER_RE = rx(r"^(?:por favor,?\s+|please,?\s+)?(?:recuerda que|recuerdame que|recuerdame|no olvides que|no te olvides de que|"
                 r"ten en cuenta que|toma nota(?: de)? que|anota que|remember that|don't forget that|do not forget that|"
                 r"keep in mind that|note that|for (?:the|your) record,?)\s+")


REL_ES_RE = rx(r"\bmis?\s+(" + ROLE_ES_ALT + r")\s*,?\s+(?:que\s+)?(?:se llama\s+|es\s+|llamad[oa]\s+)?")
REL_EN_RE = rx(r"\bmy\s+(" + ROLE_EN_ALT + r")(?:'s name is|\s+is named|\s+named|\s+called|\s+is|,)?\s+")
REL_REVERSE_RE = rx(r"\b([a-z][a-z'\-]+(?:\s+[a-z][a-z'\-]+)?)\s+(?:es|is)\s+(?:mi|my)\s+(" + ROLE_ES_ALT + '|' + ROLE_EN_ALT + r")\b")


def relationship_facts(s, f):
    out = []
    for pattern, roles in ((REL_ES_RE, ROLES_ES), (REL_EN_RE, ROLES_EN)):
        for m in pattern.finditer(f):
            explicit = bool(re.search(r'(?:se llama|named|called|name is|llamad[oa])\s+$', f[m.start():m.end()]))
            name = name_value(s, m.end(), require_cap=not explicit, limit=3)
            if not name:
                continue
            role = roles[m.group(1)]
            attribute = f'relationship:{role}' if role in UNIQUE_ROLES else f'relationship:{role}:{key(name)}'
            out.append(fact('relationship', attribute, name, 0.75, about=[name], role=role))
    for m in REL_REVERSE_RE.finditer(f) if (' es mi' in f or ' is my' in f) else ():
        start = m.start(1)
        name = name_value(s, start, require_cap=True, limit=2)
        if not name or len(name) < len(m.group(1)) * 0.5:
            continue
        role = ROLES_ES.get(m.group(2)) or ROLES_EN[m.group(2)]
        attribute = f'relationship:{role}' if role in UNIQUE_ROLES else f'relationship:{role}:{key(name)}'
        out.append(fact('relationship', attribute, name, 0.75, about=[name], role=role))
    return out


def instruction_fact(s, f):
    prefer = PREFER_YOU_RE.search(f)
    persist = PERSIST_RE.search(f)
    negative = NEG_IMPERATIVE_RE.search(f)
    lang = LANG_REPLY_RE.search(f) if (' en ' in f or ' in ' in f) else None
    if not (prefer or persist or negative or lang):
        return None
    if DESCRIBE_RE.match(f) and not prefer:
        return None
    habit = HABIT_ES_RE.search(f) or HABIT_EN_RE.search(f)
    if habit and not prefer and not negative:
        verb = habit.group(1) if habit.re is HABIT_ES_RE else ''
        if not verb or verb not in NOT_VERB_O and not ASSIST_RE.fullmatch(verb):
            return None
    ok = prefer or lang or persist and ASSIST_RE.search(f) or negative and (persist or STYLE_WORDS.search(f))
    if not ok:
        return None
    value = s.strip()[:300]
    return fact('instruction', f'instruction:{last_word_key(value)}', value, 0.75)


def habit_fact(s, f):
    m = HABIT_ES_RE.search(f)
    if m and m.group(1) not in NOT_VERB_O:
        return fact('habit', f'habit:{short_key(f[m.start():])}', cut(s, f, m.start(), LOOSE_STOP, 14), 0.6)
    m = HABIT_ES2_RE.search(f)
    if m and m.group(1) not in NOT_VERB_O:
        return fact('habit', f'habit:{short_key(f)}', cut(s, f, 0, LOOSE_STOP, 14), 0.6)
    for pattern in (HABIT_ES3_RE, HABIT_EN_RE, HABIT_EN2_RE):
        m = pattern.search(f)
        if m:
            start = m.end() if pattern is HABIT_ES3_RE else m.start()
            value = cut(s, f, start, LOOSE_STOP, 14)
            if value:
                return fact('habit', f'habit:{short_key(value)}', value, 0.6)
    return None


GATES = {k: words_set(v) for k, v in {
    'name': "llamo nombre name soy i'm am call llamame llamarme dicen",
    'live': 'vivo vivimos viviendo vivir resido mude mudamos mudado vine fui live living moved soy from naci born',
    'age': 'anos years',
    'birthday': 'naci cumpleanos birthday born',
    'work': 'trabajo trabajar trabajando sigo continuo still work working employed contrataron empece entre joined started got hired renuncie deje quit left '
            'resigned stopped',
    'job': "trabajo trabajando dedico mi work working my soy i'm am",
    'pref': 'gusta gustan encanta encantan fascina fascinan interesa interesan apasiona apasionan odio detesto aborrezco soporto '
            'aguanto prefiero adoro amo fan fanatico fanatica amante aficionado aficionada like love enjoy adore hate dislike '
            'detest prefer stand into',
    'goal': 'meta objetivo sueno proposito plan quiero deseo espero gustaria voy planeo pienso planeado planeando pensado goal '
            'dream want wanna hope intend aim going planning hoping',
    'learn': 'aprendiendo estudiando aprendo learning studying',
    'skill': 'hablo domino speak fluent experto experta experiencia expert experienced proficient good experience programar '
             'programo know can',
    'decision': "decidi decidido decidimos decision usar usaremos utilizar utilizaremos elegimos escogimos quedamos quedo opte "
                "optamos decided we'll will going chose picked opted settled switched let's lets usemos",
    'project': 'trabajando construyendo desarrollando creando proyecto working building developing creating project',
    'relationship': 'mi mis my',
    'remember': 'recuerda recuerdame olvides olvides cuenta nota anota remember forget mind note record',
    'instruction': "siempre nunca jamas ahora adelante futuro vez respuestas always never forward future answers responses "
                   "replies time prefiero gusta gustaria quiero prefer like want please favor uses utilices incluyas agregues "
                   "anadas pongas escribas hables respondas digas trates llames evita evites deja don't do stop avoid "
                   "respondeme responde contestame hablame escribeme answer respond reply talk write",
    'habit': 'siempre nunca jamas todos todas cada diario normalmente usualmente generalmente fines suelo solemos acostumbro '
             'costumbre habito always never usually often normally rarely generally tend typically every each',
}.items()}
ALL_TRIGGERS = frozenset().union(*GATES.values())
TOKEN_RE = re.compile(r"[a-z]+(?:'[a-z]+)?")


def gate(toks, name):
    return not toks.isdisjoint(GATES[name])


def hits(pattern, s, f):
    for m in pattern.finditer(f):
        if not THIRD_PERSON_RE.search(s[m.start():m.end()].lower()):
            yield m


def hit(pattern, s, f):
    m = pattern.search(f)
    if m is None or 'ó' not in s[m.start():m.end()]:
        return m
    return next(hits(pattern, s, f), None)


def proper(value, s):
    return bool(value) and (value[:1].isupper() or s == s.lower())


def sentence_facts(s, f, allow_remember=True, toks=None):
    out = []
    if toks is None:
        toks = set(TOKEN_RE.findall(f))
    if allow_remember and gate(toks, 'remember'):
        m = REMEMBER_RE.match(f)
        if m:
            inner = sentence_facts(s[m.end():], f[m.end():], False)
            if inner:
                for item in inner:
                    item['confidence'] = min(0.8, item['confidence'] + 0.1)
                return inner
            value = cut(s, f, m.end(), LOOSE_STOP, 20)
            return [fact('fact', f'note:{short_key(value, 4)}', value, 0.7)] if value else []
    inst = instruction_fact(s, f) if gate(toks, 'instruction') else None
    if inst:
        return [inst]
    for pattern, attribute, conf, mode in NAME_RULES if gate(toks, 'name') else ():
        m = hit(pattern, s, f)
        if not m:
            continue
        tok = NAME_TOKEN_RE.match(s, m.end())
        if not tok:
            continue
        if mode == 'first' and fold(tok.group(1)) not in FIRST_NAMES:
            continue
        if mode == 'cap' and not tok.group(1)[:1].isupper() and fold(tok.group(1)) not in FIRST_NAMES:
            continue
        value = name_value(s, m.end(), require_cap=False)
        if value:
            out.append(fact('identity', attribute, value, conf))
            break
    places = {}
    for pattern, attribute in LIVE_RULES if gate(toks, 'live') else ():
        for m in hits(pattern, s, f):
            neg = 'neg' in pattern.groupindex and m.group('neg')
            place = cut(s, f, m.end(), STRICT_STOP, 5)
            if proper(place, s) and (attribute not in places or places[attribute][0] < m.start()):
                places[attribute] = (m.start(), neg, place)
    for attribute, (_, neg, place) in sorted(places.items(), key=lambda kv: kv[1][0]):
        out.append(fact('identity', attribute, '' if neg else place, 0.75, negated=bool(neg), object=place))
    for pattern in AGE_RULES if gate(toks, 'age') else ():
        m = hit(pattern, s, f)
        if m and 0 < int(m.group(1)) < 120:
            out.append(fact('identity', 'age', m.group(1), 0.7))
    for pattern in BIRTHDAY_RULES if gate(toks, 'birthday') else ():
        m = hit(pattern, s, f)
        if m:
            found = find_dates(s[m.end():m.end() + 40])
            if found:
                out.append(fact('identity', 'birthday', found[0], 0.75, when=found[0]))
    for pattern, attribute, conf in WORK_RULES if gate(toks, 'work') else ():
        m = hit(pattern, s, f)
        if m:
            neg = 'neg' in pattern.groupindex and m.group('neg')
            org = cut(s, f, m.end(), STRICT_STOP, 5)
            if proper(org, s) and fold(org.split()[0]) not in PRONOUN_VALUES:
                out.append(fact('identity', attribute, '' if neg else org, conf, negated=bool(neg), object=org))
                break
    for pattern, conf, strict in JOB_RULES if gate(toks, 'job') else ():
        m = hit(pattern, s, f)
        if not m:
            continue
        value = cut(s, f, m.end(), STRICT_STOP, 4)
        if not value:
            continue
        words = [fold(w) for w in value.split()]
        if strict and not (words[0] in PROFESSIONS or words[-1] in PROFESSIONS):
            continue
        out.append(fact('identity', 'job_title', value, conf))
        break
    found_pref = []
    pref = gate(toks, 'pref')
    for m in hits(PREF_ES, s, f) if pref else ():
        if re.match(r'\s*(?:que|cuando|como|si)\b', f[m.end():]):
            continue
        verb = re.search(r'(gustan?|encantan?|fascinan?|interesan?|apasionan?)\s*(?:mucho\s*)?$', f[m.start():m.end()]).group(1)
        polarity = PREF_ES_VERB[verb]
        if m.group('neg'):
            polarity = 'dislike' if polarity in ('like', 'love') else 'no_interest'
        found_pref.append((m.start(), m.end(), polarity))
    for pattern, polarity in PREF_RULES if pref else ():
        for m in hits(pattern, s, f):
            current = polarity
            if current is None:
                current = EN_POLARITY[m.group('verb')]
                if m.group('neg'):
                    if current in ('hate', 'dislike'):
                        continue
                    current = 'dislike'
            found_pref.append((m.start(), m.end(), current))
    found_pref.sort()
    found_pref = [p for i, p in enumerate(found_pref) if not any(q[0] < p[0] < q[1] for q in found_pref[:i])]
    for i, (begin, start, polarity) in enumerate(found_pref[:4]):
        m2 = (PREFER_STOP if polarity == 'prefer' else PREF_STOP).search(f, start)
        end = m2.start() if m2 else len(s)
        if i + 1 < len(found_pref):
            end = min(end, found_pref[i + 1][0])
        bounds, pos = [], start
        for sm in LIST_SEP_RE.finditer(f, start, end):
            bounds.append((pos, sm.start(), f[pos - 2:pos]))
            pos = sm.end()
        bounds.append((pos, end, f[pos - 2:pos]))
        for n, (a, b, sep) in enumerate(bounds):
            words = strip_leading(s[a:b].split())
            if not words or n and (',' in sep and len(words) > 3 or fold(words[0]) in CLAUSE_START):
                break
            words = words[:5]
            value = ' '.join(words).strip(' ,:-')
            if not value or words[0].lower() in PRONOUN_VALUES or not re.search(r'[^\W\d_]', value):
                continue
            out.append(fact('preference', f'pref:{concept_key(value)[:40]}', polarity, 0.7, object=value))
            if n >= 3:
                break
    for pattern, conf, verbish in GOAL_RULES if gate(toks, 'goal') else ():
        m = hit(pattern, s, f)
        if m and verbish and SHORT_HORIZON_RE.search(f):
            continue
        if m:
            neg = 'neg' in pattern.groupindex and m.group('neg')
            value = cut(s, f, m.end(), LOOSE_STOP, 12)
            if value:
                out.append(fact('goal', f'goal:{short_key(value)}', '' if neg else value, conf, negated=bool(neg), object=value))
                break
    for pattern in LEARN_RULES if gate(toks, 'learn') else ():
        m = hit(pattern, s, f)
        if m:
            value = cut(s, f, m.end(), STRICT_STOP, 5)
            if value and fold(value.split()[0]) not in PRONOUN_VALUES:
                out.append(fact('skill', f'learning:{short_key(value)}', value, 0.6))
    for pattern, attribute in SKILL_RULES if gate(toks, 'skill') else ():
        m = hit(pattern, s, f)
        if m:
            value = cut(s, f, m.end(), STRICT_STOP, 5)
            if value:
                out.append(fact('skill', f'{attribute}:{short_key(value)}', value, 0.65))
    for pattern, conf in DECISION_RULES if gate(toks, 'decision') else ():
        m = hit(pattern, s, f)
        if m:
            value = cut(s, f, m.end(), LOOSE_STOP, 12)
            if value and fold(value.split()[0]) not in PRONOUN_VALUES:
                out.append(fact('decision', f'decided:{short_key(value)}', value, conf))
                break
    employer = {fold(o.get('object') or '') for o in out if o['attribute'] == 'works_at'}
    for pattern in PROJECT_RULES if gate(toks, 'project') else ():
        m = hit(pattern, s, f)
        if m and not PROJECT_SKIP.match(f[m.end():]) and fold(cut(s, f, m.end(), STRICT_STOP, 5)) not in employer:
            value = cut(s, f, m.end(), LOOSE_STOP, 8)
            if value:
                name = name_value(s, m.end(), require_cap=True, limit=3)
                out.append(fact('project', f'project:{short_key(value)}', value, 0.55, about=[name] if name else []))
    if gate(toks, 'relationship') or ' es mi' in f or ' is my' in f:
        out.extend(relationship_facts(s, f))
    if not out and gate(toks, 'habit'):
        h = habit_fact(s, f)
        if h and h['value']:
            out.append(h)
    return out


def clean_message(text):
    text = (text or '')[:MAX_FACT_CHARS * 2]
    text = CODE_RE.sub(' ', text)
    text = INLINE_CODE_RE.sub(' ', text)
    text = URL_RE.sub(' ', text)
    text = QUOTED_RE.sub(' ', text)
    text = '\n'.join(line for line in text.split('\n') if not line.lstrip().startswith('>'))
    return text[:MAX_FACT_CHARS]


def iso_now(now):
    if now is None:
        return None
    return now.isoformat() if hasattr(now, 'isoformat') else str(now)


def owner_message(msg, owners):
    author = fold(msg.get('author') or '').strip()
    if owners and author and author in owners:
        return True
    if msg.get('role') != 'user':
        return False
    return not owners or not author or author in ('user', 'usuario', 'human', 'yo', 'me', 'you') or author in owners


def facts(conversation, owner_names=None, now=None):
    owners = {fold(n).strip() for n in owner_names or () if n}
    source = conversation.get('node') or conversation.get('source_id')
    stamp = iso_now(now)
    out, seen = [], set()
    for idx, msg in enumerate(conversation.get('messages') or ()):
        if not owner_message(msg, owners):
            continue
        text = clean_message(msg.get('text'))
        if not text.strip() or SKIP_MESSAGE_RE.match(fold(text[:200])):
            continue
        time = msg.get('time')
        when = time[:10] if time and re.match(r'\d{4}-\d{2}-\d{2}', time) else None
        ftext = fold(text)
        if ALL_TRIGGERS.isdisjoint(TOKEN_RE.findall(ftext)) and not DIGIT_RE.search(ftext):
            continue
        if len(ftext) != len(text):
            text = ftext
        for s, f in zip(SENT_SPLIT_RE.split(text), SENT_SPLIT_RE.split(ftext)):
            if '?' in s or len(s) < 6:
                continue
            s = ' '.join(s.split()).strip(' -*•')
            f = ' '.join(f.split()).strip(' -*•')
            if len(s) < 6 or len(s) > 400 or len(f) != len(s):
                continue
            toks = set(TOKEN_RE.findall(f))
            dated = DIGIT_RE.search(f)
            if toks.isdisjoint(ALL_TRIGGERS) and not dated or SKIP_SENTENCE_RE.match(f) or SECRET_RE.search(f) or SECRET_TOKEN_RE.search(s):
                continue
            found = sentence_facts(s, f, toks=toks)
            if not found and dated:
                dates = find_dates(s)
                if dates and FIRST_PERSON_RE.search(f) and len(s.split()) >= 4:
                    found = [fact('event', f'event:{dates[0]}:{short_key(s)}', s[:200], 0.55, when=dates[0])]
            if not found:
                continue
            hedge = 0.15 if HEDGE_RE.search(f) else 0.0
            sensitive = bool(SENSITIVE_RE.search(f))
            text_s = s[:1000]
            for item in found:
                base = ' '.join(NORM_PUNCT_RE.sub(' ', f[:1000]).split())
                rid = digest(base if len(found) == 1 else f"{base}|{item['attribute']}")
                if rid in seen:
                    continue
                seen.add(rid)
                rec = {
                    'id': rid, 'text': text_s, 'doc': text_s[:500], 'category': item['category'], 'subject': 'user',
                    'attribute': item['attribute'], 'value': item['value'], 'when': item.get('when') or when,
                    'valid_from': time or stamp, 'valid_to': None,
                    'confidence': round(max(0.5, min(0.8, item['confidence'] - hedge)), 2), 'origin': 'rule',
                    'source': source, 'msg': msg.get('i', idx), 'sensitive': sensitive, 'about': item.get('about') or [],
                }
                for extra in ('negated', 'object', 'role'):
                    if item.get(extra):
                        rec[extra] = item[extra]
                out.append(rec)
    return out


def infer(text, now=None):
    found = facts({'messages': [{'i': 0, 'role': 'user', 'author': '', 'time': None, 'text': text}]}, now=now)
    return found[0] if found else None


def value_key(record):
    return normalize(record.get('value') or '')


def supersede(records):
    groups = {}
    for r in records:
        if r.get('attribute') and r.get('valid_from'):
            groups.setdefault((r.get('subject') or 'user', r['attribute']), []).append(r)
    for items in groups.values():
        items.sort(key=lambda r: (r['valid_from'], r.get('msg') or 0, r['id']))
        active = []
        for r in items:
            current = value_key(r)
            keep = []
            for old in active:
                if value_key(old) != current and old['valid_from'] < r['valid_from']:
                    old['valid_to'] = r['valid_from']
                    r.setdefault('supersedes', []).append(old['id'])
                else:
                    keep.append(old)
            keep.append(r)
            active = keep
    for r in records:
        if r.get('supersedes'):
            r['supersedes'] = sorted(set(r['supersedes']))
    return records
