import math
import os
import re
import time
from collections import defaultdict, deque
from datetime import datetime

from . import query as graph_query
from .analyze import KIND_ES
from .errors import InvalidInput, NotFound

REDACTED = '«redactado»'
MAX_LINES = 400
MAX_CONTEXT = 50
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_QUERY = 500
MIN_BUDGET = 500
MAX_BUDGET = 60000
MAX_ITEMS = 25
MIN_SNIPPETS = 6
SNIPPET_TOKENS = 500
CONTAINER_LINES = 40
MAX_SNIPPET_LINES = 150
SEEDS = 12
ALPHA = 0.2
EPSILON = 1e-5
MAX_PUSHES = 300000
REVERSE = 0.6
RELATIVE_FLOOR = 0.02
KIND_WEIGHT = {
    'call': 1.0, 'inherits': 0.9, 'handles': 1.0, 'http': 0.9, 'rpc': 0.9, 'data': 0.6, 'event': 0.6, 'contains': 0.7,
    'import': 0.35, 'ref': 0.25, 'tests': 0.3, 'loads': 0.3, 'env': 0.2, 'cochange': 0.15, 'depends': 0.05,
}
CODE_KINDS = ('function', 'method', 'class', 'endpoint', 'variable', 'topic', 'package')
FENCES = {
    '.py': 'python', '.ts': 'ts', '.tsx': 'tsx', '.js': 'js', '.jsx': 'jsx', '.mjs': 'js', '.cjs': 'js', '.go': 'go', '.rs': 'rust',
    '.java': 'java', '.kt': 'kotlin', '.cs': 'csharp', '.rb': 'ruby', '.php': 'php', '.swift': 'swift', '.c': 'c', '.h': 'c',
    '.cc': 'cpp', '.cpp': 'cpp', '.hpp': 'cpp', '.scala': 'scala', '.lua': 'lua', '.ex': 'elixir', '.exs': 'elixir',
    '.dart': 'dart', '.sh': 'bash', '.md': 'markdown', '.yml': 'yaml', '.yaml': 'yaml', '.json': 'json', '.toml': 'toml',
    '.sql': 'sql', '.vue': 'vue', '.svelte': 'svelte', '.proto': 'protobuf', '.tf': 'hcl', '.clj': 'clojure', '.erl': 'erlang',
}
SECRET_PATTERNS = [
    re.compile(r'\b(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA|ANVA|AIPA)[0-9A-Z]{16}\b'),
    re.compile(r'\bgh[oprsu]_[A-Za-z0-9]{30,255}\b'),
    re.compile(r'\bgithub_pat_[A-Za-z0-9_]{22,255}\b'),
    re.compile(r'\bxox[abposr]-[A-Za-z0-9-]{10,}'),
    re.compile(r'\b[sr]k_live_[A-Za-z0-9]{16,}\b'),
    re.compile(r'\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'),
]
KEY_BLOCK_RE = re.compile(r'(-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----)([\s\S]*?)(-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----)')
ASSIGN_RE = re.compile(
    r'''(?i)((?:[\w.-]*?)(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key|credentials?)[\w.-]*'''
    r'''["']?(?:\s*:\s*[A-Za-z_][\w\[\]., |]*?(?=\s*=))?\s*(?::=|=>|=|:)\s*)(["'`])([^"'`\n]{4,})\2''')
URL_PASSWORD_RE = re.compile(r'(\b[a-z][a-z0-9+.-]*://[^:/\s@"\']+:)([^@\s/"\']{3,})@', re.I)
REF_RE = re.compile(r'[\w$./:#-]{3,}')


def redact(text):
    count = 0

    def block(match):
        nonlocal count
        count += 1
        inner = re.sub(r'[^\n]+', REDACTED, match.group(2))
        return match.group(1) + inner + match.group(3)

    text = KEY_BLOCK_RE.sub(block, text)
    for pattern in SECRET_PATTERNS:
        text, found = pattern.subn(REDACTED, text)
        count += found

    def assign(match):
        nonlocal count
        value = match.group(3)
        if REDACTED in value or value.startswith(('$', '<', '%', '{')) or '{' in value or value.strip() == '':
            return match.group(0)
        count += 1
        return f'{match.group(1)}{match.group(2)}{REDACTED}{match.group(2)}'

    text = ASSIGN_RE.sub(assign, text)
    text, found = URL_PASSWORD_RE.subn(lambda m: m.group(1) + REDACTED + '@', text)
    return text, count + found


def fence(rel):
    name = rel.rsplit('/', 1)[-1]
    if name.startswith('Dockerfile'):
        return 'dockerfile'
    return FENCES.get(os.path.splitext(name)[1].lower(), '')


def tokens(text):
    return (len(text) + 3) // 4


class Sources:
    def __init__(self, index):
        self.index = index
        self.root = index.source_root()
        self.cache = {}

    def lines(self, rel):
        if rel in self.cache:
            return self.cache[rel]
        text = graph_query.read_text(self.root, rel, MAX_SOURCE_BYTES) if self.root else None
        lines = text.splitlines() if text is not None else None
        self.cache[rel] = lines
        return lines

    def stale(self, rel):
        stamp = self.index.analyzed_at()
        if not self.root or not stamp:
            return False
        try:
            when = datetime.strptime(stamp, '%Y-%m-%dT%H:%M:%S%z').timestamp()
            return os.path.getmtime(os.path.join(self.root, rel)) > when + 2
        except (OSError, ValueError):
            return False


def unavailable(index):
    return NotFound(f'el código fuente de «{index.project}» no está disponible en este servidor: '
                    'vuelve a analizarlo desde una carpeta local o desde GitHub')


def symbol_range(index, n, lines, context=0):
    total = len(lines)
    start, end = index.span(n)
    if n['kind'] in ('package', 'variable', 'endpoint', 'topic') and not n.get('end'):
        end = start
        context = max(context, 2)
    end = min(end or total, total)
    start = max(1, min(start, total))
    end = max(end, start)
    if not n.get('end'):
        while end > start and not lines[end - 1].strip():
            end -= 1
    return max(1, start - context), min(total, end + context)


def read_symbol(ref, project=None, context=0):
    context = graph_query.clamp_int(context, 0, 0, MAX_CONTEXT, 'context')
    index = graph_query.load_index(project)
    n = index.resolve(ref)
    sources = Sources(index)
    if not sources.root:
        raise unavailable(index)
    lines = sources.lines(n['file'])
    if lines is None:
        raise NotFound(f'no se pudo leer «{n["file"]}» en la fuente de «{index.project}» (¿se movió o se borró?)')
    total = len(lines)
    if not total:
        start = end = 0
    else:
        start, end = symbol_range(index, n, lines, context)
    shown_end = min(end, start + MAX_LINES - 1) if total else 0
    code, redacted = redact('\n'.join(lines[start - 1:shown_end]) if total else '')
    truncated = end - shown_end
    if truncated > 0:
        code += f'\n… (truncado: {truncated} líneas más hasta la {end}; lee sus símbolos internos con read_symbol)'
    result = {
        **index.context(), 'node': index.brief(n), 'file': n['file'], 'start': start, 'end': shown_end, 'symbol_end': end,
        'file_lines': total, 'language': fence(n['file']), 'truncated': truncated > 0, 'redacted': redacted, 'code': code,
    }
    if sources.stale(n['file']):
        result['stale'] = True
        result['note'] = 'el archivo cambió después del análisis: las líneas pueden no coincidir (vuelve a analizar)'
    return result


class Walker:
    def __init__(self, index):
        self.index = index
        self.cache = {}

    def neighbours(self, u):
        found = self.cache.get(u)
        if found is not None:
            return found
        weights = defaultdict(float)
        for kind, w in KIND_WEIGHT.items():
            for v, count in self.index.out[kind].get(u, ()):
                weights[v] += w * (1 + math.log(count))
            back = w * (0.5 if kind == 'contains' else REVERSE)
            for v, count in self.index.inc[kind].get(u, ()):
                weights[v] += back * (1 + math.log(count))
        total = sum(weights.values())
        found = [(v, w / total) for v, w in sorted(weights.items())] if total else []
        self.cache[u] = found
        return found

    def rank(self, seeds):
        total = sum(seeds.values())
        residual = {u: w / total for u, w in seeds.items()}
        score = defaultdict(float)
        queue = deque(sorted(residual))
        queued = set(queue)
        pushes = 0
        while queue and pushes < MAX_PUSHES:
            u = queue.popleft()
            queued.discard(u)
            mass = residual.get(u, 0.0)
            near = self.neighbours(u)
            if mass < EPSILON * max(1, len(near)):
                continue
            pushes += 1
            residual[u] = 0.0
            score[u] += ALPHA * mass
            if not near:
                score[u] += (1 - ALPHA) * mass
                continue
            spread = (1 - ALPHA) * mass
            for v, w in near:
                residual[v] = residual.get(v, 0.0) + spread * w
                if v not in queued and residual[v] >= EPSILON * max(1, len(self.cache.get(v) or ())):
                    queued.add(v)
                    queue.append(v)
        return score


def exact_refs(index, text):
    found = {}
    for token in REF_RE.findall(text):
        token = token.strip('.:,')
        if token in index.by_key:
            found[index.by_key[token]['id']] = 1.5
        elif token in index.file_node:
            found[index.file_node[token]['id']] = 1.2
        elif token in index.by_name and len(index.by_name[token]) <= 3:
            for n in index.by_name[token]:
                found[n['id']] = 1.2
    return found


def relation_names(index, n, kind, direction, limit=4):
    table = index.out if direction == 'out' else index.inc
    pairs = sorted(table[kind].get(n['id'], []), key=lambda p: (-p[1], -index.nodes[p[0]]['deg'], p[0]))
    return [index.nodes[i]['name'] for i, _ in pairs[:limit]]


def header(index, k, n, start, end):
    where = f"{n['file']}:{n['line']}" + (f'-{end}' if end and end > n['line'] else '')
    out = [f"### {k}. {KIND_ES.get(n['kind'], n['kind'])} `{n['name']}` · `{where}` · comunidad {index.community_name(n['c'])}"]
    if n.get('route') and n['kind'] != 'endpoint':
        out.append(f"ruta: `{n['route']}`")
    if n.get('sig'):
        out.append(f"`{n['sig']}`")
    if n.get('doc'):
        doc = n['doc'] if len(n['doc']) <= 300 else n['doc'][:299].rstrip() + '…'
        out.append(f'> {doc}')
    links = []
    for label, kind, direction in (('lo llaman', 'call', 'in'), ('llama a', 'call', 'out'), ('hereda de', 'inherits', 'out'),
                                   ('lo atiende', 'handles', 'out'), ('atiende', 'handles', 'in')):
        names = relation_names(index, n, kind, direction)
        if names:
            links.append(f"{label}: {', '.join(names)}")
    if links:
        out.append(' · '.join(links))
    return '\n'.join(out) + '\n'


def free_range(ranges, rel, start, end):
    taken = [(a, b) for a, b in ranges.get(rel, ()) if start <= b and a <= end]
    if not taken:
        return start, end, None
    for a, b in taken:
        if a <= start:
            return None, None, (a, b)
    return start, min(a for a, _ in taken) - 1, None


def context_for(query, project=None, budget=8000):
    if not isinstance(query, str) or not query.strip():
        raise InvalidInput('la consulta está vacía: describe la tarea o el símbolo que te interesa')
    if len(query) > MAX_QUERY:
        raise InvalidInput(f'la consulta es demasiado larga (máximo {MAX_QUERY} caracteres)')
    budget = graph_query.clamp_int(budget, 8000, MIN_BUDGET, MAX_BUDGET, 'budget')
    started = time.perf_counter()
    index = graph_query.load_index(project)
    terms = graph_query.text_search.query_terms(query)
    wants_tests = 'test' in terms or 'spec' in terms
    ranked = index.ranked(query)
    seeds = {}
    top = ranked[0][0] if ranked else 0
    for score, _, _, n, _ in ranked:
        if len(seeds) >= SEEDS:
            break
        if index.is_test_node(n) and not wants_tests:
            continue
        seeds[n['id']] = (score / top) ** 2 if top else 1.0
    for i, w in exact_refs(index, query).items():
        seeds[i] = max(seeds.get(i, 0), w)
    base = {**index.context(), 'query': query, 'budget': budget}
    if not seeds:
        markdown = f'# Contexto · {index.project}\n\nNada en el grafo coincide con «{query}». Prueba con nombres de símbolos, archivos o rutas.\n'
        return {**base, 'tokens_used': tokens(markdown), 'markdown': markdown, 'items': [], 'tests': [], 'source': False,
                'seconds': round(time.perf_counter() - started, 3)}
    scores = Walker(index).rank(seeds)
    candidates = []
    for i, value in scores.items():
        n = index.nodes[i]
        if index.is_test_node(n) and not wants_tests:
            continue
        if n['kind'] not in CODE_KINDS and i not in seeds:
            continue
        candidates.append((value + (seeds.get(i, 0) * 0.05), i))
    candidates.sort(key=lambda c: (-c[0], c[1]))
    floor = candidates[0][0] * RELATIVE_FLOOR if candidates else 0
    candidates = [c for c in candidates if c[0] >= floor or c[1] in seeds]
    chosen = [index.nodes[i] for _, i in candidates[:MAX_ITEMS]]
    sources = Sources(index)
    available = bool(sources.root)
    intro = (f"# Contexto · {index.project} v{index.version}\n\n"
             f"Consulta: «{query}». {len(chosen)} símbolos ordenados por relevancia (búsqueda + cercanía en el grafo). "
             f"Lee más con read_symbol(clave) o node_context(clave).\n")
    if not available:
        intro += '\nEl código fuente no está disponible en este servidor: solo se muestran cabeceras.\n'
    used = tokens(intro)
    heads = []
    for k, n in enumerate(chosen, 1):
        start, end = index.span(n)
        lines = sources.lines(n['file']) if available and n['kind'] not in ('module', 'doc') else None
        if lines:
            start, end = symbol_range(index, n, lines)
        text = header(index, k, n, start, end)
        cost = tokens(text) + 1
        if used + cost > budget and heads:
            break
        heads.append((n, start, end, text))
        used += cost
    ranges = defaultdict(list)
    blocks = {}
    snippets = 0
    max_snippets = min(MAX_ITEMS, max(MIN_SNIPPETS, budget // SNIPPET_TOKENS))
    for n, start, end, _ in heads:
        if not available or snippets >= max_snippets or n['kind'] in ('module', 'doc', 'package'):
            continue
        lines = sources.lines(n['file'])
        if not lines:
            continue
        first, last, hit = free_range(ranges, n['file'], *symbol_range(index, n, lines))
        if hit:
            note = f'(su código está en el bloque de `{n["file"]}:{hit[0]}-{hit[1]}`)\n'
            if used + tokens(note) <= budget:
                blocks[n['id']] = note
                used += tokens(note)
            continue
        kids = [c['line'] for c in index.children[n['id']] if c['line'] > first]
        if kids and last - first + 1 > CONTAINER_LINES:
            last = max(first, min(min(kids) - 1, first + CONTAINER_LINES - 1))
            while last > first and not lines[last - 1].strip():
                last -= 1
        lang = fence(n['file'])
        shown = min(last, first + MAX_SNIPPET_LINES - 1)
        while shown >= first:
            body, _ = redact('\n'.join(lines[first - 1:shown]))
            tail = f'\n… ({last - shown} líneas más: read_symbol("{n["key"]}"))' if shown < last else ''
            block = f'```{lang}\n{body}{tail}\n```\n'
            if used + tokens(block) <= budget:
                break
            if shown - first < 6:
                block = None
                break
            shown = first + (shown - first) // 2
        else:
            block = None
        if not block:
            continue
        blocks[n['id']] = block
        ranges[n['file']].append((first, shown))
        used += tokens(block)
        snippets += 1
    parts = [intro]
    items = []
    for n, start, end, text in heads:
        parts.append(text + blocks.get(n['id'], ''))
        item = index.brief(n, score=round(scores.get(n['id'], 0.0), 6), seed=n['id'] in seeds)
        item['code'] = n['id'] in blocks and blocks[n['id']].startswith('```')
        items.append(item)
    tests = []
    chosen_ids = {n['id'] for n, _, _, _ in heads}
    for i in sorted(chosen_ids):
        for t, _ in index.inc['tests'].get(i, []):
            tests.append(t)
    tests = sorted(set(tests), key=lambda t: (-index.nodes[t]['deg'], t))[:10]
    if tests:
        listing = '## Tests relacionados\n' + ''.join(f"- `{index.nodes[t]['name']}` · `{index.nodes[t]['file']}:{index.nodes[t]['line']}`\n" for t in tests)
        if used + tokens(listing) <= budget:
            parts.append(listing)
            used += tokens(listing)
    markdown = '\n'.join(parts)
    return {**base, 'tokens_used': tokens(markdown), 'markdown': markdown, 'items': items,
            'tests': [index.mini(index.nodes[t]) for t in tests], 'source': available,
            'seeds': [index.nodes[i]['key'] for i in sorted(seeds, key=lambda i: (-seeds[i], i))][:SEEDS],
            'seconds': round(time.perf_counter() - started, 3)}
