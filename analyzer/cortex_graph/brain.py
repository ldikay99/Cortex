import contextlib
import difflib
import json
import logging
import math
import os
import re
import threading
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from . import chatsearch
from . import semantic
from . import search as text_search
from . import store
from .common import digest
from .errors import CortexError, InvalidInput, NotFound

try:
    import fcntl
except ImportError:
    fcntl = None
try:
    import msvcrt
except ImportError:
    msvcrt = None

log = logging.getLogger('cortex.brain')

LOG = 'memorias.jsonl'
LOCK = 'memorias.lock'
DEFAULT_PROJECT = 'memoria'
CATEGORIES = ('identity', 'preference', 'goal', 'decision', 'event', 'relationship', 'skill', 'habit', 'project', 'fact', 'instruction')
CATEGORY_ALIASES = {
    'identidad': 'identity', 'preferencia': 'preference', 'gusto': 'preference', 'meta': 'goal', 'objetivo': 'goal',
    'decision': 'decision', 'evento': 'event', 'relacion': 'relationship', 'persona': 'relationship', 'habilidad': 'skill',
    'habito': 'habit', 'costumbre': 'habit', 'proyecto': 'project', 'dato': 'fact', 'hecho': 'fact', 'instruccion': 'instruction',
    'regla': 'instruction',
}
CATEGORY_WORDS = {
    'identity': 'identidad quien soy identity who', 'preference': 'preferencia preferencias gusto gustos preference preferences likes',
    'goal': 'meta metas objetivo objetivos goal goals plan', 'decision': 'decision decisiones decidi decided',
    'event': 'evento eventos event events', 'relationship': 'relacion persona familia relationship people family',
    'skill': 'habilidad habilidades skill skills', 'habit': 'habito habitos rutina habit habits routine',
    'project': 'proyecto proyectos project projects', 'fact': 'dato datos fact', 'instruction': 'instruccion instrucciones regla instruction rules',
}
ATTRIBUTE_WORDS = {
    'name': 'nombre llamo name called', 'lives_in': 'vivo vive ciudad donde live lives city where',
    'works_at': 'trabajo empresa work job company employer', 'job_title': 'trabajo puesto cargo profesion work job role',
    'age': 'edad anos age years', 'from': 'naci nacimiento origen born from', 'birthday': 'cumpleanos birthday',
    'reply_language': 'idioma responde language reply', 'likes': 'gusta like likes', 'dislikes': 'odio disgusta hate dislike',
}
ORIGINS = ('manual', 'rule', 'ai', 'import')
USER_SUBJECTS = {'user', 'usuario', 'yo', 'me', 'i', 'owner'}
ROLES = {
    'esposa': 'wife', 'esposo': 'husband', 'marido': 'husband', 'mujer': 'wife', 'pareja': 'partner', 'novia': 'girlfriend',
    'novio': 'boyfriend', 'hermana': 'sister', 'hermano': 'brother', 'madre': 'mother', 'mama': 'mother', 'padre': 'father',
    'papa': 'father', 'hijo': 'son', 'hija': 'daughter', 'jefe': 'boss', 'jefa': 'boss', 'socio': 'cofounder', 'socia': 'cofounder',
    'amigo': 'friend', 'amiga': 'friend', 'perro': 'dog', 'perra': 'dog', 'gato': 'cat', 'gata': 'cat', 'mom': 'mother',
    'dad': 'father', 'manager': 'boss',
}
UNIQUE_ROLES = {'wife', 'husband', 'partner', 'girlfriend', 'boyfriend', 'fiancee', 'fiance', 'mother', 'father', 'boss', 'best_friend',
                'therapist'}
MULTI = {'likes', 'dislikes', 'prefers', 'goal', 'habit', 'skill', 'decision', 'event', 'fact', 'instruction', 'note', 'project',
         'plan', 'interest'}
MAX_TEXT = 1000
MAX_DOC = 500
MAX_INPUT = 5000
MAX_NAME = 80
MAX_QUERY = 500
MAX_HINTS = 30
MAX_HINT = 120
HINT_WEIGHT = 0.5
MAX_ABOUT = 20
MIN_BUDGET = 200
MAX_BUDGET = 20000
MAX_ITEMS = 25
MAX_EXCERPTS = 6
EXCERPT_CHARS = 400
SEEDS = 12
PROBABLE = 0.7
SIMILAR = 0.9
RECENCY_DAYS = 365.0
CACHE_SIZE = 4
TEXT_EXTS = ('.md', '.markdown', '.txt', '.rst', '.org', '.mdx')
RECALL_KINDS = ('conversation', 'section', 'doc', 'person', 'concept', 'event')
KIND_PRIOR = {'memory': 1.0, 'event': 0.8, 'conversation': 0.6, 'section': 0.6, 'doc': 0.55, 'person': 0.5, 'concept': 0.4}
KIND_ORDER = {'memory': 0, 'event': 1, 'conversation': 2, 'section': 3, 'doc': 4, 'person': 5, 'concept': 6}
BRAIN_WEIGHTS = {
    'about': 1.0, 'from': 0.8, 'mentions': 0.7, 'participant': 0.6, 'attends': 0.6, 'supersedes': 0.5, 'related': 0.4,
    'links': 0.5, 'contains': 0.6, 'ref': 0.3,
}
KIND_LABEL = {'memory': 'recuerdo', 'conversation': 'conversación', 'section': 'sección', 'doc': 'documento', 'person': 'persona',
              'concept': 'tema', 'event': 'evento'}
CATEGORY_ES = {'identity': 'identidad', 'preference': 'preferencia', 'goal': 'objetivo', 'decision': 'decisión', 'event': 'evento',
               'relationship': 'relación', 'skill': 'habilidad', 'habit': 'hábito', 'project': 'proyecto', 'fact': 'dato',
               'instruction': 'instrucción'}
ROLE_ES = {'user': 'usuario', 'assistant': 'asistente', 'other': 'otro'}
REL_ES = {
    'wife': 'Su esposa', 'husband': 'Su esposo', 'partner': 'Su pareja', 'girlfriend': 'Su novia', 'boyfriend': 'Su novio',
    'fiancee': 'Su prometida', 'fiance': 'Su prometido', 'mother': 'Su madre', 'father': 'Su padre', 'sister': 'Su hermana',
    'brother': 'Su hermano', 'son': 'Su hijo', 'daughter': 'Su hija', 'boss': 'Su jefe', 'friend': 'Su amigo',
    'best_friend': 'Su mejor amigo', 'cofounder': 'Su socio', 'colleague': 'Su colega', 'coworker': 'Su compañero de trabajo',
    'dog': 'Su perro', 'cat': 'Su gato', 'pet': 'Su mascota', 'therapist': 'Su terapeuta', 'doctor': 'Su médico',
    'grandmother': 'Su abuela', 'grandfather': 'Su abuelo', 'uncle': 'Su tío', 'aunt': 'Su tía', 'cousin': 'Su primo',
    'client': 'Su cliente', 'teacher': 'Su profesor',
}
PREF_ES = {'like': 'Le gusta', 'likes': 'Le gusta', 'love': 'Le encanta', 'dislike': 'No le gusta', 'dislikes': 'No le gusta',
           'hate': 'Odia', 'prefer': 'Prefiere', 'prefers': 'Prefiere'}
STATEMENTS = {
    'name': ('Se llama {}', None), 'lives_in': ('Vive en {}', 'Ya no vive en {}'), 'from': ('Es de {}', None),
    'works_at': ('Trabaja en {}', 'Ya no trabaja en {}'), 'job_title': ('Trabaja como {}', 'Ya no trabaja como {}'),
    'age': ('Tiene {} años', None), 'birthday': ('Su cumpleaños es el {}', None), 'goal': ('Quiere {}', 'Ya no quiere {}'),
    'decided': ('Decidió {}', None), 'decision': ('Decidió {}', None), 'speaks': ('Habla {}', None),
    'learning': ('Está aprendiendo {}', None), 'skill': ('Sabe {}', None), 'project': ('Trabaja en el proyecto {}', None),
    'habit': ('Hábito: {}', None), 'reply_language': ('Quiere que le respondan en {}', None),
}
NEIGHBOUR_HOURS = 6
MONTHS_EN = ('january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december')
MONTHS_ES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')
MONTH_NUMBER = {name: k + 1 for names in (MONTHS_EN, MONTHS_ES) for k, name in enumerate(names)}
MONTH_NUMBER.update({'setiembre': 9, 'sept': 9})
MONTH_RE = '(' + '|'.join(sorted(MONTH_NUMBER, key=len, reverse=True)) + ')'
MEMORY_SHARE = 0.1
MEMORY_MIN = 80
MEMORY_FLOOR = 0.5
MESSAGE_FLOOR = 0.0
MESSAGE_CANDIDATES = 3000
MAX_NODES = 4
NODE_FACTOR = 0.8
DATE_COST = 3
PROFILE_RE = re.compile(r'\b(quien soy|que sabes de mi|mi perfil|hablame de mi|sobre mi|who am i|what do you know about me|my profile|'
                        r'tell me about (?:me|myself)|about me)\b')
PROFILE_SECTIONS = (
    ('identity', 'Quién es', 'identity', 8), ('instructions', 'Instrucciones para asistentes', 'instruction', 10),
    ('preferences', 'Preferencias', 'preference', 12), ('goals', 'Objetivos', 'goal', 8), ('projects', 'Proyectos activos', 'project', 8),
    ('people', 'Personas clave', 'relationship', 10), ('habits', 'Hábitos', 'habit', 6), ('skills', 'Habilidades', 'skill', 8),
    ('decisions', 'Decisiones recientes', 'decision', 8), ('events', 'Eventos recientes', 'event', 6), ('facts', 'Otros datos', 'fact', 8),
)
NAME_RE = r'([A-ZÁÉÍÓÚÑÜ][\wáéíóúñü]+(?:\s+[A-ZÁÉÍÓÚÑÜ][\wáéíóúñü]+){0,2})'
CUT_RE = re.compile(r'[.;!?\n]|\s(?:desde|since|porque|because|pero|but|aunque|although)\s', re.I)
RULES = [
    (re.compile(r'\b(?:resp[oó]ndeme|cont[eé]stame|h[aá]blame|escr[ií]beme|answer|reply|respond|talk to me|write to me)\b.*?\b(?:en|in)\s+'
                r'(espa[nñ]ol|ingl[eé]s|english|spanish|franc[eé]s|french|portugu[eé]s|portuguese|alem[aá]n|german|italiano|italian|catal[aá]n)',
                re.I), 'instruction', 'reply_language', None),
    (re.compile(r'\b(?:resp[oó]ndeme|cont[eé]stame|h[aá]blame|escr[ií]beme|no uses|no utilices|no me hables|evita|always answer|always reply|'
                r"respond in|answer in|reply in|don'?t use|do not use|never use|please always|please never|(?:siempre|nunca)\s+(?:me\s+)?"
                r'(?:respondas|contestes|escribas|uses|hables|expliques))\b', re.I), 'instruction', 'instruction', None),
    (re.compile(r'(?i:\b(?:mi|my)\s+(esposa|esposo|marido|mujer|pareja|novia|novio|hermana|hermano|madre|mam[aá]|padre|pap[aá]|hijo|hija|jefe|'
                r'jefa|socio|socia|amigo|amiga|perro|perra|gato|gata|wife|husband|partner|girlfriend|boyfriend|sister|brother|mother|'
                r'mom|father|dad|son|daughter|boss|manager|cofounder|friend|dog|cat)\s+(?:se llama\s+|es\s+|is\s+|is called\s+|named\s+|'
                r'called\s+)?)' + NAME_RE), 'relationship', 'relationship', None),
    (re.compile(r'\b(?:me llamo|mi nombre es|my name is|i am called|call me|ll[aá]mame)\s+(.+)', re.I), 'identity', 'name', None),
    (re.compile(r'\b(?:vivo en|resido en|me mud[eé] a|ahora vivo en|i live in|i moved to|i\'m living in|i am living in|i reside in)\s+(.+)',
                re.I), 'identity', 'lives_in', None),
    (re.compile(r'\b(?:trabajo como|mi trabajo es|soy de profesi[oó]n|i work as|my job is)\s+(.+)', re.I), 'identity', 'job_title', None),
    (re.compile(r'\b(?:trabajo en|trabajo para|i work at|i work for)\s+(.+)', re.I), 'identity', 'works_at', None),
    (re.compile(r'\b(?:tengo|i am|i\'m)\s+(\d{1,3})\s+(?:a[nñ]os|years old)\b', re.I), 'identity', 'age', None),
    (re.compile(r'\b(?:nac[ií] en|i was born in)\s+(.+)', re.I), 'identity', 'from', None),
    (re.compile(r'\b(?:mi cumplea[nñ]os es(?: el)?|my birthday is(?: on)?)\s+(.+)', re.I), 'identity', 'birthday', None),
    (re.compile(r'^' + NAME_RE + r'\s+(?:vive en|lives in)\s+(.+)'), 'identity', 'lives_in', 1),
    (re.compile(r'^' + NAME_RE + r'\s+(?:trabaja en|works at|works for)\s+(.+)'), 'identity', 'works_at', 1),
    (re.compile(r'\b(?:no me gustan?|odio|detesto|i hate|i dislike|i don\'t like|i do not like|i can\'t stand)\s+(.+)', re.I),
     'preference', 'dislikes', None),
    (re.compile(r'\b(?:mi\s+(\w+)\s+favorit[oa] es|my favou?rite\s+(\w+)\s+is)\s+(.+)', re.I), 'preference', 'favorite', None),
    (re.compile(r'\b(?:quiero|me gustar[ií]a|mi meta es|mi objetivo es|mi sue[nñ]o es|planeo|i want to|i\'d like to|i would like to|'
                r'my goal is|i plan to|i hope to)\s+(.+)', re.I), 'goal', 'goal', None),
    (re.compile(r'\b(?:me gustan?|me encantan?|adoro|i like|i love|i enjoy|i adore)\b\s*(.+)', re.I), 'preference', 'likes', None),
    (re.compile(r'\b(?:prefiero|i prefer)\s+(.+)', re.I), 'preference', 'prefers', None),
    (re.compile(r'\b(?:decid[ií]|he decidido|hemos decidido|decidimos|vamos a usar|usaremos|eleg[ií]|i decided|we decided|we\'ll use|'
                r'we will use|i chose|we chose|i\'ve decided|i have decided)\s+(.+)', re.I), 'decision', 'decision', None),
    (re.compile(r'\b(?:estoy trabajando en|estoy construyendo|estoy desarrollando|mi proyecto|i\'m working on|i am working on|'
                r'i\'m building|i am building|my project)\s+(.+)', re.I), 'project', 'project', None),
    (re.compile(r'\b(?:voy a|i\'m going to|i am going to)\s+(.+)', re.I), 'goal', 'goal', None),
    (re.compile(r'\b(?:domino|hablo|s[eé] (?:programar|hablar|usar|tocar|cocinar)|soy (?:experto|experta|bueno|buena) en|i know how to|'
                r'i speak|i\'m good at|i am good at|i\'m fluent in|i am fluent in)\s*(.+)', re.I), 'skill', 'skill', None),
    (re.compile(r'\b(?:siempre|nunca|todos los d[ií]as|cada d[ií]a|cada ma[nñ]ana|cada semana|suelo|i always|i never|every day|'
                r'every morning|every week|i usually|i tend to)\b\s*(.*)', re.I), 'habit', 'habit', None),
]
TEMPORAL_RE = re.compile(
    r'\b(antes|anterior|anteriores|anteriormente|previamente|solia|solias|vivia|vivias|trabajaba|trabajabas|estaba|tenia|pasado|pasada|'
    r'pasados|hace|cuando|historial|historia|cambio|cambie|cambiaron|evolucion|ya no|before|previous|previously|used to|formerly|earlier|'
    r'ago|last|history|changed|anymore|no longer|lived|worked|did|was|were|(?:19|20)\d{2})\b')
INTENTS = [
    (re.compile(r'\b(vivo|vivia|vives|vivias|vive|vivi|resido|mude|ciudad|pais|donde|live|lived|living|moved|reside|city|country|where)\b'),
     set(), {'lives_in', 'from'}),
    (re.compile(r'\b(llamo|llamas|nombre|name|called|quien soy|who am i)\b'), {'identity'}, {'name'}),
    (re.compile(r'\b(trabajo|trabajaba|trabajas|trabaja|empresa|empleo|puesto|cargo|profesion|work|worked|job|employer|company|role)\b'),
     set(), {'works_at', 'job_title'}),
    (re.compile(r'\b(edad|anos tengo|cuantos anos|age|how old)\b'), set(), {'age'}),
    (re.compile(r'\b(gusta|gustan|gusto|gustos|encanta|prefiero|prefieres|preferencia|preferencias|favorit\w*|odio|like|likes|love|'
                r'prefer|preference|preferences|favou?rite|hate|dislike)\b'), {'preference'}, set()),
    (re.compile(r'\b(meta|metas|objetivo|objetivos|quiero|planes|goal|goals|aim|plan|plans)\b'), {'goal'}, set()),
    (re.compile(r'\b(decidi|decidimos|decidiste|decision|decisiones|elegi|decide|decided|decisions|chose)\b'), {'decision'}, set()),
    (re.compile(r'\b(esposa|esposo|marido|pareja|novia|novio|hermana|hermano|madre|padre|mama|papa|hijo|hija|hijos|jefe|jefa|amigo|amiga|'
                r'amigos|familia|wife|husband|partner|brother|sister|mother|father|son|daughter|boss|friend|friends|family)\b'),
     {'relationship'}, set()),
    (re.compile(r'\b(habito|habitos|rutina|costumbre|suelo|habit|habits|routine|usually)\b'), {'habit'}, set()),
    (re.compile(r'\b(proyecto|proyectos|construyendo|project|projects|building)\b'), {'project'}, set()),
    (re.compile(r'\b(habilidad|habilidades|domino|hablo|idiomas|skill|skills|speak|languages)\b'), {'skill'}, set()),
    (re.compile(r'\b(responde|respondas|respuesta|respuestas|instruccion|instrucciones|emojis|formato|tono|answer|reply|respond|'
                r'instruction|instructions|format|tone)\b'), {'instruction'}, {'reply_language'}),
    (re.compile(r'\b(evento|eventos|reunion|cita|cumpleanos|viaje|event|events|meeting|appointment|birthday|trip)\b'), {'event'}, set()),
]
ENDINGS = ('aciones', 'acion', 'amientos', 'amiento', 'ieron', 'aron', 'abamos', 'iamos', 'aban', 'ando', 'iendo', 'ados', 'adas', 'idos',
           'idas', 'ias', 'aba', 'ado', 'ada', 'ido', 'ida', 'ing', 'ian', 'amos', 'emos', 'imos', 'ed', 'ia', 'ar', 'er', 'ir', 'as', 'es',
           'os', 'a', 'e', 'o', 's')

guard = threading.Lock()
thread_locks = {}
cache = {}
conversation_cache = {}
cache_lock = threading.Lock()
background = threading.Lock()
running = set()
dirty = set()


def plain(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(text or '')) if not unicodedata.combining(c)).casefold()


def normalize(text):
    return ' '.join(re.findall(r'\w+', plain(text)))


def memory_id(text):
    return digest(normalize(text))


def entity_key(name):
    return re.sub(r'\s+', '-', plain(name).strip().lstrip('@'))


def clip(text, limit):
    text = str(text or '')
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def tokens(text):
    return (len(text) + 3) // 4


def redact(text):
    from .context import redact as redact_text
    return redact_text(text)


def roots(text):
    out = []
    for w in text_search.words(text):
        p = plain(w)
        if len(p) < 4 or not p.isalpha():
            continue
        for ending in ENDINGS:
            if p.endswith(ending) and len(p) - len(ending) >= 3:
                out.append(p[:-len(ending)])
                break
    return out


def project_name(project=None):
    if project in (None, ''):
        return store.slug(os.environ.get('CORTEX_MEMORY_PROJECT') or DEFAULT_PROJECT)
    if not isinstance(project, str) or len(project) > 200:
        raise InvalidInput('el nombre del proyecto no es válido')
    return store.slug(project)


def log_path(project):
    return os.path.join(store.data_dir(), store.slug(project), LOG)


def to_moment(value=None, label='now'):
    if value is None:
        dt = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        dt = value
    else:
        dt = parse_time(value)
        if dt is None:
            raise InvalidInput(f'«{label}» debe ser una fecha ISO (AAAA-MM-DD o AAAA-MM-DDTHH:MM:SS)')
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.replace(microsecond=0)


def parse_time(value):
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip() or len(value) > 40:
        return None
    text = value.strip()
    try:
        dt = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        match = re.match(r'^(\d{4})-(\d{2})(?:-(\d{2}))?$', text)
        if not match:
            return None
        try:
            dt = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3) or 1))
        except ValueError:
            return None
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def stamp(dt):
    return dt.isoformat(timespec='seconds')


def norm_when(value, label='when'):
    if value in (None, ''):
        return None
    dt = parse_time(value)
    if dt is None:
        raise InvalidInput(f'«{label}» debe ser una fecha ISO (AAAA-MM-DD)')
    if isinstance(value, str) and re.match(r'^\d{4}-\d{2}(-\d{2})?$', value.strip()):
        return dt.date().isoformat()
    return stamp(dt)


def record_date(r):
    return r.get('when') or r.get('valid_from') or ''


def age_days(value, now):
    dt = parse_time(value) if value else None
    if dt is None:
        return None
    return max(0.0, (now - dt).total_seconds() / 86400)


def recency(value, now):
    days = age_days(value, now)
    return 0.0 if days is None else math.exp(-days / RECENCY_DAYS)


def is_active(r, at):
    moment = stamp(at)
    start, end = r.get('valid_from') or '', r.get('valid_to') or ''
    return start[:19] <= moment and (not end or end[:19] > moment)


def functional(r):
    attribute = r.get('attribute') or ''
    if not attribute or not r.get('value'):
        return False
    if attribute.startswith('relationship:'):
        parts = attribute.split(':')
        return len(parts) > 2 or parts[1] in UNIQUE_ROLES
    if attribute == 'relationship':
        return False
    return attribute not in MULTI and r.get('category') not in ('event', 'decision', 'goal', 'habit', 'instruction')


def probable(r):
    return (r.get('origin') or 'manual') != 'manual' and float(r.get('confidence') or 0) < PROBABLE


def complete(r):
    out = dict(r)
    out.setdefault('text', '')
    out['doc'] = out.get('doc') or clip(out['text'], MAX_DOC)
    out['category'] = out.get('category') or 'fact'
    out['subject'] = out.get('subject') or 'user'
    for key in ('attribute', 'value', 'object', 'when', 'valid_to', 'source', 'msg', 'superseded_by', 'created'):
        out.setdefault(key, None)
    out['valid_from'] = out.get('valid_from') or out.get('when') or ''
    try:
        out['confidence'] = max(0.0, min(1.0, float(out.get('confidence', 1.0))))
    except (TypeError, ValueError):
        out['confidence'] = 0.5
    out['origin'] = out.get('origin') or 'manual'
    out['sensitive'] = bool(out.get('sensitive'))
    out['negated'] = bool(out.get('negated'))
    out['about'] = [a for a in (out.get('about') or []) if isinstance(a, str)]
    out['supersedes'] = sorted({s for s in (out.get('supersedes') or []) if isinstance(s, str)})
    return out


def tidy(value):
    return ' '.join(str(value or '').split()).strip(' .,;:!¡?¿"\'«»')


def statement(r):
    text = r.get('text') or ''
    attribute = r.get('attribute') or ''
    parts = attribute.split(':')
    base = parts[0]
    value, thing = tidy(r.get('value')), tidy(r.get('object'))
    negated = bool(r.get('negated'))
    line = None
    if r.get('category') == 'instruction' or base == 'instruction':
        return text
    if base == 'relationship' and value:
        role = parts[1] if len(parts) > 1 else ''
        line = f"{REL_ES.get(role) or ('Su ' + role.replace('_', ' ') if role else 'Relación')}: {value}"
    elif base in ('pref', 'likes', 'dislikes', 'prefers'):
        polarity = value.lower() if value.lower() in PREF_ES else base
        target = thing or (value if value.lower() not in PREF_ES else '')
        if polarity in PREF_ES and target:
            line = f'{PREF_ES[polarity]} {target}'
    elif base == 'favorite' and value:
        line = f"Su {parts[1] if len(parts) > 1 else 'cosa'} favorito: {value}"
    elif base in STATEMENTS:
        positive, negative = STATEMENTS[base]
        if negated and negative and (thing or value):
            line = negative.format(thing or value)
        elif value and not negated:
            line = positive.format(value)
    if not line:
        return text
    subject = r.get('subject') or 'user'
    if subject != 'user' and not line.startswith('Su '):
        line = f'{subject} {line[0].lower()}{line[1:]}'
    return line


def statement_key(r):
    if r.get('attribute') and (r.get('value') or r.get('object')):
        return (r.get('subject') or 'user', r['attribute'], normalize(r.get('value')), normalize(r.get('object')), bool(r.get('negated')))
    return ('text', normalize(statement(r)))


def first_value(text):
    text = CUT_RE.split(text, 1)[0].strip(' ,:-"\'«»')
    return clip(text, 120) if text else None


def infer(text):
    for pattern, category, attribute, subject_group in RULES:
        match = pattern.search(text)
        if not match:
            continue
        out = {'category': category, 'attribute': attribute, 'about': []}
        groups = [g for g in match.groups() if g]
        if attribute == 'relationship' and len(groups) >= 2:
            role = ROLES.get(plain(groups[0]), plain(groups[0]))
            name = groups[-1].strip()
            out.update(attribute=f'relationship:{role}' if role in UNIQUE_ROLES else f'relationship:{role}:{entity_key(name)}',
                       value=name, about=[name])
        elif attribute == 'favorite' and len(groups) >= 2:
            out.update(attribute=f'favorite:{plain(groups[0])}', value=first_value(groups[-1]))
        elif attribute == 'reply_language':
            out['value'] = plain(groups[0]) if groups else None
        elif subject_group:
            out.update(subject=match.group(subject_group), value=first_value(match.group(2)), about=[match.group(subject_group)])
        else:
            out['value'] = first_value(groups[-1]) if groups else None
        return out
    return {}


def external_facts(text, now):
    try:
        from . import extract
    except ImportError:
        return {}
    facts = getattr(extract, 'facts', None)
    if facts is None:
        return {}
    conversation = {'id': 'manual', 'source': 'manual', 'title': '', 'started': None, 'ended': None, 'participants': ['user'],
                    'messages': [{'i': 0, 'role': 'user', 'author': 'user', 'time': None, 'text': text, 'line': 0}]}
    try:
        found = facts(conversation, owner_names={'user'}, now=now) or []
    except Exception:
        log.exception('extract.facts falló con un recuerdo manual')
        return {}
    for r in found:
        if isinstance(r, dict) and r.get('category') in CATEGORIES:
            return {k: r.get(k) for k in ('category', 'subject', 'attribute', 'value', 'object', 'negated', 'about') if r.get(k)}
    return {}


def category_of(value):
    if value in (None, ''):
        return None
    if not isinstance(value, str):
        raise InvalidInput('«category» debe ser texto')
    key = plain(value).strip()
    if key in CATEGORIES:
        return key
    if key in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[key]
    raise InvalidInput(f'categoría inválida «{value}»: usa {", ".join(CATEGORIES)}')


def text_field(value, label, limit=200):
    if value in (None, ''):
        return None
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise InvalidInput(f'«{label}» debe ser texto')
    value = ' '.join(str(value).split())
    if len(value) > limit:
        raise InvalidInput(f'«{label}» es demasiado largo (máximo {limit} caracteres)')
    return redact(value)[0] or None


def about_list(value):
    if value in (None, ''):
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)) or len(value) > MAX_ABOUT:
        raise InvalidInput(f'«about» debe ser una lista de hasta {MAX_ABOUT} nombres')
    out = []
    for item in value:
        item = text_field(item, 'about', 120)
        if item and item not in out:
            out.append(item)
    return out


def prepare(raw, now):
    text = raw.get('text')
    if not isinstance(text, str) or not text.strip():
        raise InvalidInput('el recuerdo está vacío: escribe el dato que quieres guardar')
    if len(text) > MAX_INPUT:
        raise InvalidInput(f'el recuerdo es demasiado largo (máximo {MAX_INPUT} caracteres)')
    text, found = redact(' '.join(text.split()))
    text = clip(text, MAX_TEXT)
    category = category_of(raw.get('category'))
    given = {k: raw.get(k) for k in ('subject', 'attribute', 'value')}
    guess = {}
    if not (category and all(given.values())):
        guess = external_facts(text, now) or infer(text)
    origin = raw.get('origin') or 'manual'
    if origin not in ORIGINS:
        raise InvalidInput(f'origen inválido «{origin}»: usa {", ".join(ORIGINS)}')
    try:
        confidence = float(1.0 if raw.get('confidence') is None else raw['confidence'])
    except (TypeError, ValueError) as exc:
        raise InvalidInput('«confidence» debe ser un número entre 0 y 1') from exc
    if not math.isfinite(confidence):
        raise InvalidInput('«confidence» debe ser un número entre 0 y 1')
    msg = raw.get('msg')
    if msg is not None and (isinstance(msg, bool) or not isinstance(msg, int)):
        msg = None
    when = norm_when(raw.get('when'))
    rid = raw.get('id')
    if not (isinstance(rid, str) and re.match(r'^[\w-]{1,64}$', rid)):
        rid = memory_id(text)
    record = {
        'id': rid, 'text': text, 'doc': clip(text, MAX_DOC),
        'category': category or category_of(guess.get('category')) or ('event' if when else 'fact'),
        'subject': text_field(given['subject'] or guess.get('subject'), 'subject', 120) or 'user',
        'attribute': text_field(given['attribute'] or guess.get('attribute'), 'attribute', 120),
        'value': text_field(given['value'] or guess.get('value'), 'value', 300),
        'object': text_field(raw.get('object') or (None if given['value'] else guess.get('object')), 'object', 300),
        'negated': bool(raw.get('negated') if raw.get('negated') is not None else (guess.get('negated') and not given['value'])),
        'when': when, 'valid_from': norm_when(raw.get('valid_from'), 'valid_from') or when or stamp(now), 'valid_to': None,
        'confidence': round(max(0.0, min(1.0, confidence)), 3), 'origin': origin,
        'source': text_field(raw.get('source'), 'source', 500), 'msg': msg,
        'sensitive': bool(raw.get('sensitive')) or found > 0,
        'about': about_list((about_list(raw.get('about')) + list(guess.get('about') or []))[:MAX_ABOUT]),
        'supersedes': [], 'superseded_by': None, 'created': stamp(now),
    }
    if plain(record['subject']) in USER_SUBJECTS:
        record['subject'] = 'user'
    return record


def thread_lock(path):
    with guard:
        return thread_locks.setdefault(path, threading.Lock())


@contextlib.contextmanager
def locked(project):
    folder = store.project_dir(project)
    path = os.path.join(folder, LOCK)
    with thread_lock(path):
        with open(path, 'a+b') as fh:
            if fcntl:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            elif msvcrt:
                fh.seek(0)
                while True:
                    try:
                        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                        break
                    except OSError:
                        continue
            try:
                yield folder
            finally:
                if fcntl:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                elif msvcrt:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


def read_ops(path):
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []
    ops = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            op = json.loads(line)
        except ValueError:
            continue
        if isinstance(op, dict) and isinstance(op.get('id'), str):
            ops.append(op)
    return ops


def fold(ops):
    state, tomb = {}, {}
    for op in ops:
        rid, kind = op['id'], op.get('op')
        fields = {k: v for k, v in op.items() if k not in ('op', 'at')}
        if kind == 'add':
            state[rid] = complete(fields)
            tomb.pop(rid, None)
        elif kind == 'update' and rid in state:
            state[rid].update({k: v for k, v in fields.items() if k != 'id'})
        elif kind == 'forget':
            state.pop(rid, None)
            tomb[rid] = op.get('at')
    return state, tomb


def load_state(project):
    return fold(read_ops(log_path(project)))


def append(path, ops):
    if not ops:
        return
    data = ''.join(json.dumps(op, ensure_ascii=False, sort_keys=True) + '\n' for op in ops)
    prefix = ''
    try:
        with open(path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            if f.tell():
                f.seek(-1, os.SEEK_END)
                prefix = '' if f.read(1) == b'\n' else '\n'
    except FileNotFoundError:
        pass
    with open(path, 'a', encoding='utf-8', newline='\n') as f:
        f.write(prefix + data)
        f.flush()
        os.fsync(f.fileno())


def compact(record):
    return {k: v for k, v in record.items() if not (v is None or v is False or (isinstance(v, (str, list)) and not v))}


def ensure_project(project):
    folder = store.project_dir(project)
    path = os.path.join(folder, 'historial.json')
    with store.save_lock:
        if not os.path.exists(path):
            store.write_atomic(path, json.dumps({'project': project, 'origin': {'type': 'brain'}, 'versions': []}, ensure_ascii=False, indent=1))


def chain_of(state, r):
    return sorted((o for o in state.values() if o['id'] != r['id'] and o.get('subject') == r['subject']
                   and o.get('attribute') == r['attribute'] and functional(o)), key=lambda o: (o['valid_from'], o['id']))


def apply(state, tomb, rec, at, ops):
    def update(target, **fields):
        target.update(fields)
        ops.append({'op': 'update', 'id': target['id'], 'at': at, **fields})

    def result(status, record, superseded=()):
        return {'id': record['id'], 'status': status, 'superseded': list(superseded), 'memory': record}

    if rec['id'] in tomb and rec['origin'] != 'manual':
        return result('forgotten', rec)
    key = normalize(rec['text'])
    fact = rec.get('attribute') or ''

    def alike(r):
        return normalize(r['text']) == key and (r.get('attribute') or '') == fact

    if rec['id'] in state and not alike(state[rec['id']]):
        rec['id'] = memory_id(rec['text'])
        if rec['id'] in state and not alike(state[rec['id']]):
            rec['id'] = digest(f'{key}|{fact}')
    same = state.get(rec['id'])
    if same is None or not alike(same):
        same = next((r for r in state.values() if alike(r) and not r.get('valid_to')), None)
    if same and not same.get('valid_to'):
        changes = {}
        if rec['confidence'] > same['confidence']:
            changes['confidence'] = rec['confidence']
        about = list(same['about']) + [a for a in rec['about'] if a not in same['about']]
        if about != same['about']:
            changes['about'] = about
        if changes:
            update(same, **changes)
        return result('duplicate', same)
    if same:
        rec['id'] = digest(f"{key}|{fact}|{rec['valid_from']}")
        if rec['id'] in state:
            return result('duplicate', state[rec['id']])
    superseded = []
    if functional(rec):
        chain = chain_of(state, rec)
        current = next((o for o in reversed(chain) if not o.get('valid_to')), None)
        if current and normalize(current['value']) == normalize(rec['value']) and current['valid_from'] <= rec['valid_from']:
            return result('duplicate', current)
        later = [o for o in chain if o['valid_from'] > rec['valid_from']]
        earlier = [o for o in chain if o['valid_from'] <= rec['valid_from']]
        before = next((o for o in reversed(earlier) if not o.get('valid_to') or o['valid_to'] > rec['valid_from']), None)
        if before and normalize(before['value']) != normalize(rec['value']):
            update(before, valid_to=rec['valid_from'], superseded_by=rec['id'])
            rec['supersedes'] = sorted(set(rec['supersedes']) | {before['id']})
            superseded.append(before['id'])
        if later:
            following = later[0]
            rec['valid_to'], rec['superseded_by'] = following['valid_from'], following['id']
            update(following, supersedes=sorted(set(following['supersedes']) | {rec['id']}))
    record = complete(rec)
    state[record['id']] = record
    ops.append({'op': 'add', 'at': at, **compact(record)})
    return result('updated' if superseded else 'new', record, superseded)


def absorb(project, raws, now=None):
    now = to_moment(now)
    prepared = [prepare(r, now) for r in raws]
    prepared.sort(key=lambda r: (r['valid_from'], r['id']))
    ensure_project(project)
    at = stamp(now)
    with locked(project) as folder:
        state, tomb = load_state(project)
        ops = []
        results = [apply(state, tomb, rec, at, ops) for rec in prepared]
        append(os.path.join(folder, LOG), ops)
    return results, bool(ops)


def rebuild(project):
    from . import pipeline
    run = getattr(pipeline, 'rebuild', None)
    if run is None:
        return None
    return run(project)


def refresh(project):
    try:
        rebuild(project)
        return 'actualizado'
    except CortexError as exc:
        log.warning('no se pudo actualizar el grafo de %s: %s', project, exc.message)
        return f'error: {exc.message}'
    except Exception as exc:
        log.exception('falló la actualización del grafo de %s', project)
        return f'error: {type(exc).__name__}'


def rebuild_worker(project):
    while True:
        refresh(project)
        with background:
            if project in dirty:
                dirty.discard(project)
                continue
            running.discard(project)
            return


def rebuild_later(project):
    with background:
        if project in running:
            dirty.add(project)
            return 'en cola'
        running.add(project)
    threading.Thread(target=rebuild_worker, args=(project,), daemon=True).start()
    return 'actualizando'


def rebuilding(project=None):
    with background:
        return bool(running) if project is None else project in running


def after_change(project, changed, mode):
    if not changed:
        return 'sin cambios'
    if mode == 'background':
        return rebuild_later(project)
    if mode:
        return refresh(project)
    return 'pendiente'


def remember(text, project=None, category=None, about=(), source=None, when=None, confidence=1.0, origin='manual', subject=None,
             attribute=None, value=None, sensitive=None, now=None, rebuild=True):
    project = project_name(project)
    raw = {'text': text, 'category': category, 'about': about, 'source': source, 'when': when, 'confidence': confidence,
           'origin': origin, 'subject': subject, 'attribute': attribute, 'value': value, 'sensitive': sensitive}
    results, changed = absorb(project, [raw], now)
    out = dict(results[0])
    out.update(project=project, graph=after_change(project, changed, rebuild))
    return out


def remember_many(records, project=None, now=None, rebuild=True):
    project = project_name(project)
    if not isinstance(records, (list, tuple)):
        raise InvalidInput('se esperaba una lista de recuerdos')
    results, changed = absorb(project, [r for r in records if isinstance(r, dict) and isinstance(r.get('text'), str) and r['text'].strip()], now)
    counts = defaultdict(int)
    for r in results:
        counts[r['status']] += 1
    return {'project': project, 'counts': dict(sorted(counts.items())), 'results': results, 'graph': after_change(project, changed, rebuild)}


def memories(project=None, include_inactive=False):
    state, _ = load_state(project_name(project))
    records = sorted((r for r in state.values() if include_inactive or not r.get('valid_to')), key=lambda r: r['id'])
    records.sort(key=lambda r: r['valid_from'], reverse=True)
    return records


def forgotten(project=None):
    return set(load_state(project_name(project))[1])


def graph_index(project):
    from . import query
    try:
        return query.load_index(project)
    except CortexError:
        return None


def node_record(index, n):
    record = {k: n.get(k) for k in ('text', 'doc', 'category', 'subject', 'attribute', 'value', 'object', 'negated', 'when',
                                     'valid_from', 'valid_to', 'confidence', 'origin', 'source', 'msg', 'sensitive')}
    record['id'] = n['key'][2:]
    record['text'] = record['text'] or n.get('doc') or n['name']
    record['about'] = sorted(index.nodes[i]['name'] for i, _ in index.out['about'].get(n['id'], ()))
    record['supersedes'] = sorted(index.nodes[i]['key'][2:] for i, _ in index.out['supersedes'].get(n['id'], ()))
    if record.get('confidence') is None:
        record['confidence'] = 0.5
    return complete(record)


def settle(records):
    out = {r['id']: complete(r) for r in records}
    chains = defaultdict(list)
    for r in out.values():
        if functional(r):
            chains[(r['subject'], r['attribute'])].append(r)
    for chain in chains.values():
        chain.sort(key=lambda r: (r['valid_from'], r['id']))
        pending = []
        for r in chain:
            if r.get('valid_to'):
                continue
            if pending and normalize(pending[-1]['value']) != normalize(r['value']):
                for older in pending:
                    older['valid_to'], older['superseded_by'] = r['valid_from'], r['id']
                    r['supersedes'] = sorted(set(r['supersedes']) | {older['id']})
                pending = []
            pending.append(r)
    return [out[k] for k in sorted(out)]


def all_records(project, index=None):
    state, tomb = load_state(project)
    records = dict(state)
    if index is not None:
        for n in index.nodes:
            if n['kind'] == 'memory':
                rid = n['key'][2:]
                if rid not in records and rid not in tomb:
                    records[rid] = node_record(index, n)
    return settle(records.values())


def entity_table(g):
    table = {}
    for kind in ('concept', 'person'):
        for nid in sorted(g.nodes):
            meta = g.nodes[nid]
            if meta.get('kind') != kind:
                continue
            forms = [nid[2:], entity_key(meta.get('name') or '')] + [entity_key(a) for a in meta.get('aliases') or () if isinstance(a, str)]
            if isinstance(meta.get('email'), str):
                forms.append(entity_key(meta['email']))
            for form in forms:
                if form:
                    table[form] = nid
    return table


def entity_for(g, table, name, person):
    key = entity_key(name)
    if not key:
        return None
    if key in table:
        return table[key]
    nid = f"{'u' if person else 'x'}:{key}"
    meta = {'kind': 'person' if person else 'concept', 'name': name.strip(), 'file': '', 'line': 0, 'aliases': [],
            'hash': digest(nid)}
    if not person:
        meta['tag'] = False
    g.node(nid, **meta)
    table[key] = nid
    return nid


def link_memories(g, records):
    records = settle([r for r in records if isinstance(r, dict) and isinstance(r.get('id'), str) and r.get('text')])
    owner = next((nid for nid in sorted(g.nodes) if g.nodes[nid].get('kind') == 'person' and g.nodes[nid].get('owner')), None)
    table = entity_table(g)
    for r in records:
        source = r.get('source') if r.get('source') in g.nodes else None
        file, line = (g.nodes[source]['file'], g.nodes[source]['line']) if source else ('', 0)
        signature = json.dumps([r['text'], r['category'], r['valid_to'], r['confidence'], r['value']], ensure_ascii=False)
        g.node(f"r:{r['id']}", kind='memory', name=clip(r['text'], MAX_NAME), file=file, line=line, text=r['text'],
               doc=clip(r['text'], MAX_DOC), category=r['category'], subject=r['subject'], attribute=r['attribute'], value=r['value'],
               object=r.get('object'), negated=r.get('negated') or None,
               when=r['when'], valid_from=r['valid_from'] or None, valid_to=r['valid_to'], confidence=r['confidence'],
               origin=r['origin'], source=r.get('source'), msg=r.get('msg'), sensitive=r['sensitive'], hash=digest(signature))
    for r in records:
        nid = f"r:{r['id']}"
        if r.get('source') in g.nodes:
            g.edge(nid, r['source'], 'from')
        names = [(name, r['category'] == 'relationship' or name == r['subject']) for name in r['about']]
        if r['subject'] != 'user' and r['subject'] not in r['about']:
            names.append((r['subject'], True))
        if r['subject'] == 'user' and owner:
            g.edge(nid, owner, 'about')
        for name, person in names:
            target = entity_for(g, table, name, person)
            if target:
                g.edge(nid, target, 'about')
        for old in r['supersedes']:
            g.edge(nid, f'r:{old}', 'supersedes')
    return records


def inside(root, path):
    root = os.path.abspath(root)
    return os.path.abspath(path).startswith(root + os.sep)


def load_conversations_file(root, rel):
    try:
        from . import importers
    except ImportError:
        return None
    path = os.path.join(root, rel) if root else ''
    if not root or not inside(root, path):
        return None
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (os.path.abspath(path), st.st_mtime_ns, st.st_size)
    with cache_lock:
        if key in conversation_cache:
            return conversation_cache[key]
    try:
        loaded = importers.load(root, rel) or []
    except Exception:
        log.exception('no se pudo releer %s', rel)
        return None
    with cache_lock:
        while len(conversation_cache) >= 2:
            conversation_cache.pop(next(iter(conversation_cache)))
        conversation_cache[key] = loaded
    return loaded


def find_conversation(root, key, files):
    if not root or not isinstance(key, str) or not key.startswith('k:'):
        return None
    body = key[2:]
    for cut in sorted({body.find('#'), body.rfind('#')} - {-1}):
        rel, cid = body[:cut], body[cut + 1:]
        if rel not in files:
            files[rel] = load_conversations_file(root, rel)
        for c in files[rel] or ():
            if str(c.get('id')) == cid:
                return c
    return None


def render_messages(messages, chars=EXCERPT_CHARS):
    out = []
    for m in messages:
        text = clip(redact(' '.join(str(m.get('text') or '').split()))[0], chars)
        who = m.get('author') or ROLE_ES.get(m.get('role'), m.get('role') or '?')
        when = (m.get('time') or '')[:16].replace('T', ' ')
        out.append(f"> **{who}**{' · ' + when if when else ''}: {text}")
    return '\n'.join(out)


def best_message(messages, query):
    wanted = set(text_search.tokens(query)) | set(roots(query))
    best, top = 0, -1
    for k, m in enumerate(messages):
        text = str(m.get('text') or '')
        score = len(wanted & (set(text_search.tokens(text)) | set(roots(text))))
        if score > top:
            best, top = k, score
    return best


def excerpt_messages(conversation, msg=None, query='', span=1):
    messages = conversation.get('messages') or []
    if not messages:
        return []
    if isinstance(msg, int):
        k = next((pos for pos, m in enumerate(messages) if m.get('i') == msg), min(max(msg, 0), len(messages) - 1))
    else:
        k = best_message(messages, query)
    target = parse_time(messages[k].get('time'))
    near = []
    for pos in range(max(0, k - span), min(len(messages), k + span + 1)):
        when = parse_time(messages[pos].get('time'))
        if pos == k or target is None or when is None or abs((when - target).total_seconds()) <= NEIGHBOUR_HOURS * 3600:
            near.append(messages[pos])
    return near


def conversation_excerpt(conversation, msg=None, query='', span=1):
    return render_messages(excerpt_messages(conversation, msg, query, span))


def message_ref(rel, key, m, k=0):
    ref = {'file': rel, 'conversation': key, 'i': m.get('i', k)}
    if isinstance(m.get('line'), int) and m['line'] > 0:
        ref['line'] = m['line']
    return ref


def message_refs(rel, key, messages):
    return [message_ref(rel, key, m, k) for k, m in enumerate(messages)]


def message_index(index):
    root = index.source_root()
    convs = sorted((n for n in index.nodes if n['kind'] == 'conversation'), key=lambda n: n['key'])
    if not root or not convs:
        return None
    rels = sorted({n['file'] for n in convs})
    stamps = []
    for rel in rels:
        try:
            st = os.stat(os.path.join(root, rel))
            stamps.append((rel, st.st_mtime_ns, st.st_size))
        except OSError:
            stamps.append((rel, 0, 0))
    key = ('messages', store.data_dir(), index.project, index.version, id(index), root, tuple(stamps), semantic.configured())
    with cache_lock:
        if key in cache:
            return cache[key]
    by_file = defaultdict(list)
    for n in convs:
        by_file[n['file']].append(n)
    msgs, by_conv = [], {}
    for rel in rels:
        loaded = {str(c.get('id')): c for c in load_conversations_file(root, rel) or ()}
        prefix = f'k:{rel}#'
        for n in by_file[rel]:
            conversation = loaded.get(n['key'][len(prefix):]) if n['key'].startswith(prefix) else None
            if conversation is None:
                continue
            positions = []
            for k, m in enumerate(conversation.get('messages') or ()):
                text = ' '.join(str(m.get('text') or '').split())
                if not text:
                    continue
                positions.append(len(msgs))
                msgs.append({'conv': n['key'], 'node': n, 'rel': rel, 'i': m.get('i', k), 'pos': len(positions) - 1,
                             'time': parse_time(m.get('time')), 'message': m, 'text': text})
            by_conv[n['key']] = positions
    model = chatsearch.Model([{'text': m['text'], 'author': m['message'].get('author') or '', 'role': m['message'].get('role'),
                               'conv': m['conv'], 'time': m['time']} for m in msgs])
    entry = next((e for e in index.history if e.get('v') == index.version), None) or {}
    semantic.attach(model, [m['text'] for m in msgs], store.project_dir(index.project), (entry.get('options') or {}).get('fingerprint'))
    built = {'msgs': msgs, 'convs': by_conv, 'model': model, 'root': root}
    with cache_lock:
        while len(cache) >= CACHE_SIZE:
            cache.pop(next(iter(cache)))
        cache[key] = built
    return built


def within_hours(mi, ids):
    times = [mi['msgs'][x]['time'] for x in ids]
    for a, b in zip(times, times[1:]):
        if a is not None and b is not None and abs((b - a).total_seconds()) > NEIGHBOUR_HOURS * 3600:
            return False
    return True


def informative(mi, query, text):
    if mi is None:
        return bool(set(text_search.query_terms(query)) & set(text_search.tokens(text)))
    return mi['model'].informative(query, text)


def conversation_text(root, key, limit=60):
    conversation = find_conversation(root, key, {})
    if conversation is None:
        return None
    messages = conversation.get('messages') or []
    text = render_messages(messages[:limit], 2000)
    if len(messages) > limit:
        text += f'\n… ({len(messages) - limit} mensajes más)'
    return text


def node_excerpt(index, n, root, files, query, refs=None):
    if n['kind'] == 'conversation':
        conversation = find_conversation(root, n['key'], files)
        if conversation:
            picked = excerpt_messages(conversation, None, query)
            if refs is not None:
                refs.extend(message_refs(n['file'], n['key'], picked))
            return render_messages(picked)
    if n['kind'] in ('section', 'doc') and root and n['file'].lower().endswith(TEXT_EXTS):
        from . import query as graph_query
        text = graph_query.read_text(root, n['file'], 4 * 1024 * 1024)
        if text is not None:
            lines = text.splitlines()
            start, end = index.span(n)
            body = '\n'.join(lines[max(0, start - 1):min(len(lines), (end or start + 15))]).strip()
            if body:
                return '\n'.join('> ' + line for line in clip(redact(body)[0], EXCERPT_CHARS * 2).splitlines() if line.strip())
    if n.get('doc'):
        return '> ' + clip(redact(' '.join(n['doc'].split()))[0], EXCERPT_CHARS)
    return ''


def is_temporal(query):
    return bool(TEMPORAL_RE.search(plain(query)))


def month_start(dt, back=0):
    year, month = dt.year, dt.month - back
    while month < 1:
        month += 12
        year -= 1
    return datetime(year, month, 1)


def time_window(query, now):
    q = plain(query)
    day = datetime(now.year, now.month, now.day)
    if re.search(r'\b(ayer|yesterday)\b', q):
        return day - timedelta(days=1), day
    if re.search(r'\b(hoy|today)\b', q):
        return day, day + timedelta(days=1)
    if re.search(r'\b(semana pasada|ultima semana|last week)\b', q):
        return day - timedelta(days=14), day
    if re.search(r'\b(esta semana|this week)\b', q):
        return day - timedelta(days=7), now + timedelta(seconds=1)
    if re.search(r'\b(mes pasado|ultimo mes|last month)\b', q):
        return month_start(now, 1), month_start(now)
    if re.search(r'\b(este mes|this month)\b', q):
        return month_start(now), now + timedelta(seconds=1)
    if re.search(r'\b(ano pasado|ultimo ano|last year)\b', q):
        return datetime(now.year - 1, 1, 1), datetime(now.year, 1, 1)
    if re.search(r'\b(este ano|this year)\b', q):
        return datetime(now.year, 1, 1), now + timedelta(seconds=1)
    units = {'dia': 1, 'dias': 1, 'day': 1, 'days': 1, 'semana': 7, 'semanas': 7, 'week': 7, 'weeks': 7, 'mes': 30, 'meses': 30,
             'month': 30, 'months': 30, 'ano': 365, 'anos': 365, 'year': 365, 'years': 365}
    explicit = explicit_window(q, now)
    if explicit:
        return explicit
    match = re.search(r'\bhace\s+(\d+|un|una|unos|unas)\s+(dias?|semanas?|mes|meses|anos?)\b', q) or \
        re.search(r'\b(\d+|a|an|one)\s+(days?|weeks?|months?|years?)\s+ago\b', q)
    if match:
        count = int(match.group(1)) if match.group(1).isdigit() else 1
        unit = units[match.group(2)]
        center = now - timedelta(days=count * unit)
        return center - timedelta(days=unit), center + timedelta(days=unit)
    match = re.search(r'\b(?:en|in|de|del|during|durante)\s+((?:19|20)\d{2})\b', q)
    if match:
        year = int(match.group(1))
        return datetime(year, 1, 1), datetime(year + 1, 1, 1)
    return None


def guess_year(month, now):
    return now.year if month <= now.month else now.year - 1


def month_window(year, month):
    return datetime(year, month, 1), datetime(year + (month == 12), month % 12 + 1, 1)


def day_window(year, month, day):
    try:
        start = datetime(year, month, day)
    except ValueError:
        return None
    return start - timedelta(days=1), start + timedelta(days=2)


def explicit_window(q, now):
    match = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:de\s+|of\s+)?' + MONTH_RE + r'(?:,?\s+(?:de\s+|del\s+)?((?:19|20)\d{2}))?\b', q)
    if match:
        month = MONTH_NUMBER[match.group(2)]
        year = int(match.group(3)) if match.group(3) else guess_year(month, now)
        return day_window(year, month, int(match.group(1)))
    match = re.search(r'\b' + MONTH_RE + r'\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+((?:19|20)\d{2})\b', q)
    if match:
        return day_window(int(match.group(3)), MONTH_NUMBER[match.group(1)], int(match.group(2)))
    match = re.search(r'\b' + MONTH_RE + r',?\s+(?:de\s+|del\s+|of\s+)?((?:19|20)\d{2})\b', q)
    if match:
        return month_window(int(match.group(2)), MONTH_NUMBER[match.group(1)])
    match = re.search(r'\b(?:in|en|during|durante|since|desde)\s+(?:el mes de\s+)?' + MONTH_RE + r'\b', q)
    if match:
        month = MONTH_NUMBER[match.group(1)]
        return month_window(guess_year(month, now), month)
    return None


def intents(query):
    q = plain(query)
    categories, attributes = set(), set()
    for pattern, cats, attrs in INTENTS:
        if pattern.search(q):
            categories |= cats
            attributes |= attrs
    return categories, attributes


def intent_match(r, categories, attributes):
    base = (r.get('attribute') or '').split(':', 1)[0]
    return r.get('category') in categories or (base and base in attributes) or (r.get('attribute') or '') in attributes


def memory_fields(r):
    tags = [CATEGORY_ES.get(r['category'], ''), CATEGORY_WORDS.get(r['category'], ''), r.get('attribute') or '', r.get('value') or '',
            '' if r['subject'] == 'user' else r['subject'], ' '.join(r['about']),
            ATTRIBUTE_WORDS.get((r.get('attribute') or '').split(':', 1)[0], ''), ' '.join(roots(r['text']))]
    return {'name': r['text'], 'doc': '', 'tags': ' '.join(t for t in tags if t)}


def node_fields(n):
    extra = [n.get('source') or '', n.get('email') or '', ' '.join(a for a in n.get('aliases') or () if isinstance(a, str)),
             ' '.join(roots(f"{n['name']} {n.get('doc') or ''}"))]
    return {'name': n['name'], 'doc': n.get('doc') or '', 'tags': ' '.join(t for t in extra if t)}


def recall_index(project, index, records):
    try:
        st = os.stat(log_path(project))
        log_stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        log_stamp = None
    key = (store.data_dir(), project, id(index) if index is not None else None, getattr(index, 'version', None), log_stamp)
    with cache_lock:
        hit = cache.get(key)
        if hit:
            return hit
    entries, pseudo = [], []
    for r in records:
        entries.append(('memory', r))
        pseudo.append({'id': len(pseudo), 'key': f"r:{r['id']}", 'kind': 'memory', 'file': '', 'deg': 0, **memory_fields(r)})
    if index is not None:
        for n in index.nodes:
            if n['kind'] in RECALL_KINDS:
                entries.append(('node', n))
                pseudo.append({'id': len(pseudo), 'key': n['key'], 'kind': n['kind'], 'file': n['file'], 'deg': n['deg'], **node_fields(n)})
    built = (entries, text_search.Index(pseudo))
    with cache_lock:
        while len(cache) >= CACHE_SIZE:
            cache.pop(next(iter(cache)))
        cache[key] = built
    return built


def clamp_budget(budget, default):
    from . import query as graph_query
    return graph_query.clamp_int(budget, default, MIN_BUDGET, MAX_BUDGET, 'budget')


def memory_line(r, now):
    start = (record_date(r) or '')[:10]
    parts = [CATEGORY_ES.get(r['category'], r['category'])]
    if r.get('valid_to'):
        parts.append(f"{start or '?'} → {r['valid_to'][:10]} (ya no vigente)")
    elif start:
        parts.append(f'desde {start}')
    if probable(r):
        parts.append('probable')
    if r['sensitive']:
        parts.append('sensible')
    head = statement(r)
    line = f"- {head} · {' · '.join(parts)} · `r:{r['id']}`"
    if normalize(head) != normalize(r['text']):
        line += f"\n  > «{r['text']}»"
    return line


def memory_item(r, score, now):
    item = {'kind': 'memory', 'key': f"r:{r['id']}", 'score': round(score, 6), 'active': not r.get('valid_to'), 'statement': statement(r)}
    for k in ('id', 'text', 'category', 'subject', 'attribute', 'value', 'when', 'valid_from', 'valid_to', 'confidence', 'origin',
              'source', 'msg', 'sensitive', 'about'):
        item[k] = r.get(k)
    item['probable'] = probable(r)
    return item


def node_item(index, n, score):
    item = index.brief(n, score=round(score, 6))
    return item


def message_line(m, when):
    text = clip(redact(' '.join(str(m.get('text') or '').split()))[0], EXCERPT_CHARS)
    who = m.get('author') or ROLE_ES.get(m.get('role'), m.get('role') or '?')
    return f"- {when + ' ' if when else ''}{who}: {text}"


def message_cost(msg):
    if 'cost' not in msg:
        msg['cost'] = tokens(message_line(msg['message'], '00:00')) + 2
    return msg['cost']


def render_group(mi, ids):
    lines, previous = [], None
    for x in ids:
        msg = mi['msgs'][x]
        when = msg['time']
        same_day = previous is not None and when is not None and previous['time'] is not None and previous['time'].date() == when.date()
        if same_day and msg['pos'] > previous['pos'] + 1:
            lines.append('- …')
        label = (when.strftime('%H:%M') if same_day else when.strftime('%Y-%m-%d %H:%M')) if when else ''
        lines.append(message_line(msg['message'], label))
        previous = msg
    return '\n'.join(lines)


def conversation_header(n):
    name = n.get('name') or ''
    title = f" «{name}»" if name and normalize(name) not in normalize(n['key']) else ''
    return f"\n###{title} `{n['key']}`\n"


def node_header(n):
    when = (n.get('started') or n.get('when') or '')[:10]
    return (f"\n### {KIND_LABEL.get(n['kind'], n['kind'])} «{n['name']}»" + (f' · {when}' if when else '')
            + (f" · `{n['file']}:{n['line']}`" if n['file'] else '') + f" · `{n['key']}`\n")


def clean_hints(hints):
    if hints in (None, '', ()):
        return []
    if isinstance(hints, str):
        hints = [h for h in re.split(r'[,;\n]', hints)]
    if not isinstance(hints, (list, tuple)) or not all(isinstance(h, str) for h in hints):
        raise InvalidInput('hints debe ser una lista de textos')
    out = []
    for h in hints:
        h = ' '.join(h.split())
        if not h:
            continue
        if len(h) > MAX_HINT:
            raise InvalidInput(f'cada pista de hints admite como máximo {MAX_HINT} caracteres')
        if h.casefold() not in {x.casefold() for x in out}:
            out.append(h)
    if len(out) > MAX_HINTS:
        raise InvalidInput(f'hints admite como máximo {MAX_HINTS} pistas')
    return out


def recall(query, project=None, budget=2000, at=None, now=None, hints=None):
    if not isinstance(query, str) or not query.strip():
        raise InvalidInput('la consulta está vacía: pregunta qué quieres recordar')
    if len(query) > MAX_QUERY:
        raise InvalidInput(f'la consulta es demasiado larga (máximo {MAX_QUERY} caracteres)')
    hints = clean_hints(hints)
    budget = clamp_budget(budget, 2000)
    now = to_moment(now)
    moment = to_moment(at, 'at') if at not in (None, '') else None
    project = project_name(project)
    index = graph_index(project)
    records = all_records(project, index)
    temporal = is_temporal(query)
    window = time_window(query, now)
    categories, attributes = intents(query)
    base = {'project': project, 'query': query, 'budget': budget, 'temporal': temporal, 'at': stamp(moment) if moment else None}
    if hints:
        base['hints'] = hints
    if not records and index is None:
        markdown = f'# Memoria · {project}\n\nTodavía no hay recuerdos en «{project}»: guárdalos con remember o importa un historial.\n'
        return {**base, 'markdown': markdown, 'items': [], 'tokens': tokens(markdown)}
    entries, searcher = recall_index(project, index, records)
    words = [ATTRIBUTE_WORDS.get(a, a) for a in sorted(attributes)] + [CATEGORY_WORDS.get(c, c) for c in sorted(categories)]
    augmented = ' '.join([query] + roots(query) + words)
    ranked, _ = searcher.search(augmented)
    top = ranked[0][0] if ranked else 0
    text_score = {r[3]['id']: r[0] / top for r in ranked} if top > 0 else {}
    if hints:
        extra, _ = searcher.search(' '.join(hints + roots(' '.join(hints))))
        peak = extra[0][0] if extra else 0
        for r in extra if peak > 0 else ():
            text_score[r[3]['id']] = text_score.get(r[3]['id'], 0) + HINT_WEIGHT * r[0] / peak
    graph_ids = {}
    back = {}
    if index is not None:
        for pid, (kind, obj) in enumerate(entries):
            gnode = index.by_key.get(f"r:{obj['id']}") if kind == 'memory' else obj
            if gnode is not None:
                graph_ids[pid] = gnode['id']
                back[gnode['id']] = pid
    ppr = {}
    if index is not None and text_score:
        from .context import Walker
        seeds = {}
        for pid, t in sorted(text_score.items(), key=lambda x: (-x[1], x[0])):
            if len(seeds) >= SEEDS:
                break
            if pid in graph_ids:
                seeds[graph_ids[pid]] = t * t
        if seeds:
            raw = Walker(index, BRAIN_WEIGHTS).rank(seeds)
            peak = max(raw.values()) if raw else 0
            ppr = {back[g]: v / peak for g, v in raw.items() if g in back and peak > 0}
    candidates = set(text_score) | {pid for pid, v in ppr.items() if v >= 0.05}
    about_me = bool(PROFILE_RE.search(plain(query)))
    if categories or attributes or about_me:
        candidates |= {pid for pid, (kind, obj) in enumerate(entries)
                       if kind == 'memory' and (about_me or intent_match(obj, categories, attributes))}
    scored = []
    for pid in candidates:
        kind, obj = entries[pid]
        t, g = text_score.get(pid, 0.0), ppr.get(pid, 0.0)
        relevance = 0.75 * t + 0.25 * g
        if kind == 'memory':
            r = obj
            if moment is not None:
                if r['valid_from'] and r['valid_from'][:19] > stamp(moment):
                    continue
                current = is_active(r, moment)
            else:
                current = not r.get('valid_to')
            if not current and not temporal:
                continue
            score = relevance * KIND_PRIOR['memory'] * (0.5 + 0.5 * r['confidence'])
            if about_me:
                score += 0.2 * r['confidence']
            if intent_match(r, categories, attributes):
                score += 0.35
            score += 0.1 * recency(record_date(r), now)
            if not current:
                score += 0.2
            date = parse_time(record_date(r))
        else:
            n = obj
            score = relevance * KIND_PRIOR.get(n['kind'], 0.4)
            stamp_value = n.get('started') or n.get('when') or n.get('ended')
            score += 0.05 * recency(stamp_value, now) if stamp_value else 0
            date = parse_time(stamp_value) if stamp_value else None
        if window:
            if date is not None and window[0] <= date < window[1]:
                score += 0.4
            elif date is not None:
                score *= 0.6
        if score > 0:
            scored.append((score, pid))
    scored.sort(key=lambda s: (-s[0], KIND_ORDER.get(entries[s[1]][1]['kind'] if entries[s[1]][0] == 'node' else 'memory', 9), s[1]))
    floor = scored[0][0] * 0.1 if scored else 0
    mi = message_index(index) if index is not None else None
    loaded = set(mi['convs']) if mi else set()
    mems = [(sc, entries[pid][1]) for sc, pid in scored if entries[pid][0] == 'memory' and sc >= floor][:MAX_ITEMS]
    if mems and not about_me:
        mems = [(sc, r) for sc, r in mems if sc >= mems[0][0] * MEMORY_FLOOR]
    nodes = [(sc, entries[pid][1]) for sc, pid in scored if entries[pid][0] == 'node' and sc >= floor
             and entries[pid][1]['key'] not in loaded][:MAX_ITEMS]
    seen, unique = set(), []
    for sc, r in mems:
        stamp_key = r.get('valid_from') if temporal else None
        keys = ((statement_key(r), stamp_key), (normalize(statement(r)), stamp_key))
        if not any(k in seen for k in keys):
            seen.update(keys)
            unique.append((sc, r))
    mems = unique
    if temporal and not window:
        mems.sort(key=lambda x: (record_date(x[1]), x[1]['id']))
    scores = mi['model'].score(query, window, hints) if mi else None
    hits = chatsearch.top(scores, MESSAGE_FLOOR, MESSAGE_CANDIDATES) if scores is not None else []
    root = index.source_root() if index is not None else None
    files = {}
    intro = (f'# Memoria · {project}\n\nConsulta: «{query}». Recuerdos primero (datos sobre el usuario), luego fragmentos de '
             f'conversaciones y documentos.' + (' Incluye recuerdos que ya no están vigentes, en orden cronológico.' if temporal and not window else '')
             + (f' Periodo: {stamp(window[0])[:10]} a {stamp(window[1])[:10]}.' if window else '')
             + (f' Vigentes a {stamp(moment)[:10]}.' if moment else '') + '\n')
    parts, used, items = [intro], tokens(intro), []
    if not mems and not nodes and not hits:
        parts.append(f'\nNada en la memoria coincide con «{query}».\n')
    taken = set()
    if mems:
        share = budget if about_me or not (nodes or hits) else max(int(budget * MEMORY_SHARE), MEMORY_MIN)
        limit = min(budget, used + share)
        heading = '\n## Recuerdos\n'
        parts.append(heading)
        used += tokens(heading)
        excerpts = 0
        for sc, r in mems:
            line = memory_line(r, now) + '\n'
            if used + tokens(line) > limit and items:
                break
            parts.append(line)
            used += tokens(line)
            item = memory_item(r, sc, now)
            if excerpts < MAX_EXCERPTS and r.get('source'):
                picked, rel = [], None
                if mi and r['source'] in mi['convs']:
                    positions = mi['convs'][r['source']]
                    target = next((x for x in positions if mi['msgs'][x]['i'] == r.get('msg')), None)
                    if target is not None:
                        p = mi['msgs'][target]['pos']
                        ids = [x for x in positions[max(0, p - 1):p + 2] if x == target or within_hours(mi, sorted({x, target}))]
                        picked = [(x, mi['msgs'][x]['message']) for x in ids]
                        rel = mi['msgs'][target]['rel']
                elif root:
                    conversation = find_conversation(root, r['source'], files)
                    if conversation:
                        picked = [(None, m) for m in excerpt_messages(conversation, r.get('msg'), query)]
                        rel = (index.by_key.get(r['source']) or {}).get('file') if index is not None else None
                if picked and informative(mi, query, ' '.join(str(m.get('text') or '') for _, m in picked)):
                    quote = '\n'.join('  ' + line for line in render_messages([m for _, m in picked]).splitlines()) + '\n'
                    if used + tokens(quote) <= limit:
                        parts.append(quote)
                        used += tokens(quote)
                        item['excerpt'] = quote.strip()
                        item['messages'] = message_refs(rel, r['source'], [m for _, m in picked])
                        taken.update(x for x, _ in picked if x is not None)
                        excerpts += 1
            items.append(item)
    fragments = [(sc, k, 'message', x) for k, (sc, x) in enumerate(hits) if x not in taken]
    if nodes:
        top = nodes[0][0]
        limit_nodes = MAX_NODES if fragments else MAX_ITEMS
        fragments += [(sc / top * NODE_FACTOR, len(hits) + k, 'node', n) for k, (sc, n) in enumerate(nodes[:limit_nodes])]
    fragments.sort(key=lambda f: (-f[0], f[1]))
    heading = '\n## Fragmentos\n'
    if fragments and used + tokens(heading) < budget:
        used += tokens(heading)
        groups, days, chosen_nodes, misses = {}, set(), [], 0
        for sc, _, kind, payload in fragments:
            if misses >= 40 or used >= budget:
                break
            if kind == 'message':
                msg = mi['msgs'][payload]
                conv = msg['conv']
                day = (conv, msg['time'].date() if msg['time'] else None)
                cost = message_cost(msg) + (DATE_COST if day not in days else 0) + (0 if conv in groups else tokens(conversation_header(msg['node'])))
                if used + cost > budget:
                    misses += 1
                    continue
                used += cost
                days.add(day)
                group = groups.setdefault(conv, {'ids': [], 'score': sc})
                group['ids'].append(payload)
            else:
                n = payload
                refs = []
                quote = node_excerpt(index, n, root, files, query, refs)
                cost = tokens(node_header(n)) + (tokens(quote) + 1 if quote else 0)
                if used + cost > budget:
                    misses += 1
                    continue
                used += cost
                chosen_nodes.append((sc, n, quote, refs))
        if groups or chosen_nodes:
            parts.append(heading)
        for conv in sorted(groups, key=lambda c: (min((mi['msgs'][x]['time'] or datetime.min) for x in groups[c]['ids']), c)):
            ids = sorted(groups[conv]['ids'], key=lambda x: mi['msgs'][x]['pos'])
            node = mi['msgs'][ids[0]]['node']
            quote = render_group(mi, ids)
            parts.append(conversation_header(node) + quote + '\n')
            item = node_item(index, node, groups[conv]['score'])
            item['excerpt'] = quote
            item['messages'] = [message_ref(mi['msgs'][x]['rel'], conv, mi['msgs'][x]['message'], mi['msgs'][x]['i']) for x in ids]
            items.append(item)
        for sc, n, quote, refs in chosen_nodes:
            parts.append(node_header(n) + (quote + '\n' if quote else ''))
            item = node_item(index, n, sc)
            if quote:
                item['excerpt'] = quote
            if refs:
                item['messages'] = refs
            items.append(item)
    markdown = ''.join(parts)
    return {**base, 'markdown': markdown, 'items': items, 'tokens': tokens(markdown)}


def profile_line(r):
    notes = []
    date = record_date(r)[:10]
    if date:
        notes.append(f'desde {date}' if r['category'] not in ('event', 'decision') else date)
    if probable(r):
        notes.append('probable')
    return f"- {statement(r)}" + (f" ({'; '.join(notes)})" if notes else '') + f" [r:{r['id']}]"


def profile_item(r):
    return {'id': r['id'], 'key': f"r:{r['id']}", 'statement': statement(r), 'text': r['text'], 'category': r['category'],
            'attribute': r['attribute'], 'merged': r.get('merged') or [r['id']],
            'value': r['value'], 'when': r['when'], 'valid_from': r['valid_from'], 'confidence': r['confidence'], 'origin': r['origin'],
            'probable': probable(r), 'source': r.get('source')}


def profile(project=None, budget=1500, now=None):
    budget = clamp_budget(budget, 1500)
    now = to_moment(now)
    project = project_name(project)
    index = graph_index(project)
    records = [r for r in all_records(project, index) if is_active(r, now) and not r['sensitive']]
    merged, lines = {}, {}
    for r in sorted(records, key=lambda r: (-r['confidence'], r['origin'] != 'manual', r['id'])):
        key = (r['category'], statement_key(r))
        same = merged.get(key) or lines.get((r['category'], normalize(statement(r))))
        if same is not None:
            same['merged'].append(r['id'])
            continue
        merged[key] = lines[(r['category'], normalize(statement(r)))] = dict(r, merged=[r['id']])
    grouped = defaultdict(list)
    for r in merged.values():
        grouped[r['category']].append(r)
    for category, items in grouped.items():
        if category in ('decision', 'event'):
            items.sort(key=lambda r: (record_date(r), r['confidence'], r['id']), reverse=True)
        else:
            items.sort(key=lambda r: (-(r['confidence'] * (0.6 + 0.4 * recency(record_date(r), now))), r['id']))
    people = []
    if index is not None:
        named = {plain(a) for r in grouped.get('relationship', ()) for a in r['about']}
        for n in sorted((n for n in index.nodes if n['kind'] == 'person' and not n.get('owner')), key=lambda n: (-n['deg'], n['id'])):
            if plain(n['name']) not in named and n['deg'] > 0:
                people.append(n)
            if len(people) >= 6:
                break
    header = (f'# Perfil · {project}\n\nLo que se sabe del usuario a partir de su memoria (solo datos vigentes; '
              '«probable» = deducido con poca confianza).\n')
    used = tokens(header)
    plan = {key: [] for key, _, _, _ in PROFILE_SECTIONS}
    pools = {key: list(grouped.get(category, ())) + ([('person', n) for n in people] if key == 'people' else [])
             for key, _, category, _ in PROFILE_SECTIONS}
    titles = {key: title for key, title, _, _ in PROFILE_SECTIONS}
    caps = {key: cap for key, _, _, cap in PROFILE_SECTIONS}

    def line_of(entry):
        if isinstance(entry, tuple):
            n = entry[1]
            return f"- {n['name']} ({n['deg']} conexiones) [{n['key']}]"
        return profile_line(entry)

    full = False
    for limit in (3, None):
        for key, _, _, _ in PROFILE_SECTIONS:
            pool, chosen = pools[key], plan[key]
            while pool and len(chosen) < min(caps[key], limit or caps[key]):
                cost = tokens(line_of(pool[0]) + '\n') + (tokens(f'\n## {titles[key]}\n') if not chosen else 0)
                if used + cost > budget:
                    full = True
                    break
                chosen.append(pool.pop(0))
                used += cost
    parts = [header]
    sections = {}
    for key, title, _, _ in PROFILE_SECTIONS:
        if not plan[key]:
            continue
        parts.append(f'\n## {title}\n')
        parts.extend(line_of(e) + '\n' for e in plan[key])
        sections[key] = [({'kind': 'person', 'key': e[1]['key'], 'name': e[1]['name'], 'deg': e[1]['deg']} if isinstance(e, tuple)
                          else profile_item(e)) for e in plan[key]]
    if not records and not people:
        parts.append('\nTodavía no hay recuerdos: guárdalos con remember o importa un historial.\n')
    markdown = ''.join(parts)
    return {'project': project, 'markdown': markdown, 'sections': sections, 'tokens': tokens(markdown), 'count': len(records),
            'truncated': full or any(pools[k] for k in pools)}


def matches_about(term, *values):
    for value in values:
        if isinstance(value, (list, tuple)):
            if matches_about(term, *value):
                return True
        elif value and term in plain(value):
            return True
    return False


def timeline(project=None, start=None, end=None, about=None, limit=100):
    from . import query as graph_query
    project = project_name(project)
    limit = graph_query.clamp_int(limit, 100, 1, 1000, 'limit')
    first = norm_when(start, 'start') if start not in (None, '') else None
    last = norm_when(end, 'end') if end not in (None, '') else None
    if about is not None and (not isinstance(about, str) or len(about) > 200):
        raise InvalidInput('«about» debe ser texto de menos de 200 caracteres')
    term = plain(about).strip() if about else ''
    index = graph_index(project)
    items = []
    for r in all_records(project, index):
        date = record_date(r)
        if not date:
            continue
        if term and not matches_about(term, r['text'], r['subject'], r['about'], r.get('value')):
            continue
        items.append({'date': date, 'kind': 'memory', 'key': f"r:{r['id']}", 'id': r['id'], 'text': r['text'],
                      'statement': statement(r), 'category': r['category'],
                      'until': r.get('valid_to'), 'active': not r.get('valid_to'), 'source': r.get('source'), 'probable': probable(r)})
    if index is not None:
        for n in index.nodes:
            if n['kind'] not in ('event', 'conversation'):
                continue
            date = n.get('when') if n['kind'] == 'event' else n.get('started')
            if not date:
                continue
            if term:
                linked = [index.nodes[i]['name'] for i, _ in index.out['participant'].get(n['id'], ())]
                linked += [index.nodes[i]['name'] for i, _ in index.inc['attends'].get(n['id'], ())]
                linked += [index.nodes[i]['name'] for i, _ in index.out['mentions'].get(n['id'], ())]
                if not matches_about(term, n['name'], n.get('doc'), linked, n['key']):
                    continue
            items.append({'date': date, 'kind': n['kind'], 'key': n['key'], 'text': n['name'],
                          'until': n.get('until') or n.get('ended'), 'file': n['file'], 'line': n['line'],
                          **({'source': n['source']} if n.get('source') else {}), **({'count': n['count']} if n.get('count') else {})})
    if first:
        items = [i for i in items if i['date'][:len(first)] >= first]
    if last:
        items = [i for i in items if i['date'][:len(last)] <= last]
    items.sort(key=lambda i: (i['date'], KIND_ORDER.get(i['kind'], 9), i['key']))
    total = len(items)
    items = items[:limit] if first else items[-limit:]
    return {'project': project, 'start': first, 'end': last, 'about': about or None, 'total': total, 'items': items}


def forget(ref, project=None, now=None):
    if isinstance(ref, int) and not isinstance(ref, bool):
        ref = str(ref)
    if not isinstance(ref, str) or not ref.strip():
        raise InvalidInput('indica qué olvidar: el id del recuerdo (r:…) o su texto')
    if len(ref) > MAX_INPUT:
        raise InvalidInput('la referencia es demasiado larga')
    project = project_name(project)
    at = stamp(to_moment(now))
    ref = ref.strip()
    rid = ref[2:] if ref.startswith('r:') else ref
    index = graph_index(project)
    with locked(project) as folder:
        path = os.path.join(folder, LOG)
        ops = read_ops(path)
        state, tomb = fold(ops)
        records = {r['id']: r for r in all_records(project, index)}
        records.update(state)
        found = rid if rid in records else None
        if found is None:
            wanted = normalize(ref)
            best, top = None, 0.0
            for r in sorted(records.values(), key=lambda r: r['id']):
                ratio = difflib.SequenceMatcher(None, wanted, normalize(r['text'])).ratio()
                if ratio > top:
                    best, top = r['id'], ratio
            found = best if top >= SIMILAR else None
        if found is None:
            raise NotFound(f'no encontré ningún recuerdo como «{clip(ref, 80)}» en «{project}»')
        kept = [op for op in ops if op['id'] != found]
        kept.append({'op': 'forget', 'id': found, 'at': at})
        store.write_atomic(path, ''.join(json.dumps(op, ensure_ascii=False, sort_keys=True) + '\n' for op in kept))
        store.scrub_memory(project, f'r:{found}')
    return {'project': project, 'forgotten': [found]}


def forget_and_refresh(ref, project=None, now=None, rebuild=True):
    result = forget(ref, project, now)
    result['graph'] = after_change(result['project'], True, rebuild)
    return result


def find_sources(root):
    from .analyze import list_files
    try:
        from . import importers
    except ImportError:
        return []
    conversations = []
    for rel in list_files(root):
        try:
            with open(os.path.join(root, rel), 'rb') as f:
                head = f.read(64 * 1024)
        except OSError:
            continue
        try:
            fmt = importers.detect(rel, head)
        except Exception:
            fmt = None
        if not fmt:
            continue
        try:
            loaded = importers.load(root, rel, fmt) or []
        except Exception:
            log.exception('no se pudo leer el historial %s', rel)
            continue
        for c in loaded:
            conversations.append({**c, 'node': f"k:{rel}#{c['id']}"})
    return conversations


def load_llm():
    from . import llm
    return llm


def import_history(source, project=None, ai=False, batch=False, model=None, warn=None, on_progress=None, client=None, now=None):
    from . import pipeline
    project = project_name(project)
    llm = load_llm() if ai else None
    if ai:
        if client is None:
            ok, reason = llm.available()
            if not ok:
                raise CortexError(f'no se puede usar la extracción con IA: {reason}')
    graph = pipeline.analyze_source(source, project, copy=True)
    result = {'project': graph['project'], 'analysis': pipeline.summary(graph), 'ai': None}
    if ai:
        index = graph_index(graph['project'])
        root = index.source_root() if index is not None else None
        if not root and isinstance(source, str) and os.path.isdir(os.path.expanduser(source)):
            root = os.path.abspath(os.path.expanduser(source))
        conversations = find_sources(root) if root else []
        if not conversations:
            result['ai'] = {'conversations': 0, 'extracted': 0, 'counts': {}, 'note': 'no encontré conversaciones que enviar'}
        else:
            try:
                from . import importers
                owners = sorted(importers.user_names(conversations))
            except Exception:
                owners = []
            if warn:
                warn(len(conversations), sum(len(str(m.get('text') or '')) for c in conversations for m in c.get('messages') or ()),
                     model or os.environ.get('CORTEX_AI_MODEL') or getattr(llm, 'DEFAULT_MODEL', 'claude-opus-5-5'))
            nodes = {str(c['id']): c['node'] for c in conversations}
            records = llm.extract_memories(conversations, owner_names=owners or None, model=model, batch=batch, client=client,
                                           on_progress=on_progress) or []
            fixed = []
            for r in records:
                if not isinstance(r, dict):
                    continue
                r = dict(r, origin='ai')
                if r.get('source') in nodes:
                    r['source'] = nodes[r['source']]
                fixed.append(r)
            stored = remember_many(fixed, graph['project'], now=now, rebuild=True)
            result['ai'] = {'conversations': len(conversations), 'extracted': len(records), 'counts': stored['counts'],
                            'graph': stored['graph']}
    try:
        latest = store.load_version(graph['project']) or {}
    except CortexError:
        latest = {}
    saved = {r['id'] for r in memories(graph['project'])}
    found = {n['key'][2:] for n in latest.get('nodes') or () if n.get('kind') == 'memory' and not n.get('valid_to')}
    result['memories'] = len(saved | found)
    return result
