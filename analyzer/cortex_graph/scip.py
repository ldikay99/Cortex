import bisect
import re
from collections import Counter
from pathlib import Path

from .common import MAX_FILE_BYTES
from .errors import CortexError

DEFINITION = 1
SYMBOL_KINDS = ('class', 'function', 'method')
TARGETS = ('callable', 'type', 'module')
LINKED = ('call', 'tests', 'ref', 'inherits', 'contains')
DECLARES = re.compile(r'(\b(def|func|fun|fn|function|operator)\s+|\bfunc\s*\([^)]*\)\s*)$')
TS_SCHEME = 'scip-typescript '
JVM_SCHEME = 'semanticdb '
RUST_SCHEME = 'rust-analyzer '
DART_SCHEME = 'scip-dart '
DOTNET_SCHEME = 'scip-dotnet '
DOTNET_CONSTRUCTOR = re.compile(r'#`\.c?ctor`\((?:\+\d+)?\)\.$')
RUST_IMPL = re.compile(r'impl#\[(`[^`]*`|[^\]]*)\](?:\[(?:`[^`]*`|[^\]]*)\])?')
JVM_CONSTRUCTOR = re.compile(r'#`<init>`\((?:\+\d+)?\)\.$')
SIGNATURE_HEAD = re.compile(r'^(?:\([a-z ]+\)\s+)?(?:var|let|const)?\s*[^:\n(]*:\s*')
OPTIONAL_TAIL = re.compile(r'\s*(?:\|\s*(?:undefined|null)\s*)*')
COMPONENT_TYPE = re.compile(r'^[^:\n]*:.*\b(?:\w*ExoticComponent|ComponentType|FunctionComponent|FC)<', re.S)
TS_EXTS = ('.ts', '.tsx', '.mts', '.cts')
KOTLIN_EXTS = ('.kt', '.kts')
GENERIC_EXTS = ('.dart', '.java', '.cs', '.scala')
MAX_GENERIC_LINES = 30
JSX_BEFORE = re.compile(r'(?:^|[^\w$.)\]\s]|\b(?:return|yield|await|default|case|else|do)\b)\s*$')


def varint(buf, i):
    out = shift = 0
    while True:
        b = buf[i]
        i += 1
        out |= (b & 0x7f) << shift
        if b < 0x80:
            return out, i
        shift += 7
        if shift > 63:
            raise ValueError('varint demasiado largo')


def fields(buf):
    i, n = 0, len(buf)
    while i < n:
        key, i = varint(buf, i)
        num, wt = key >> 3, key & 7
        if wt == 0:
            val, i = varint(buf, i)
        elif wt == 2:
            size, i = varint(buf, i)
            if i + size > n:
                raise ValueError('mensaje truncado')
            val, i = buf[i:i + size], i + size
        elif wt in (1, 5):
            val, i = None, i + (8 if wt == 1 else 4)
        else:
            raise ValueError('tipo de campo desconocido')
        yield num, wt, val


def signed(v):
    v &= 0xffffffff
    return v - (1 << 32) if v >= 1 << 31 else v


def ints(wt, val):
    if wt == 0:
        return [signed(val)]
    out, i = [], 0
    while i < len(val):
        v, i = varint(val, i)
        out.append(signed(v))
    return out


def text(val):
    return bytes(val).decode('utf-8', errors='replace')


def occurrence(buf):
    rng, sym, roles, enclosing = [], '', 0, []
    for num, wt, val in fields(buf):
        if num == 1 and wt in (0, 2):
            rng += ints(wt, val)
        elif num == 2 and wt == 2:
            sym = text(val)
        elif num == 3 and wt == 0:
            roles = signed(val)
        elif num == 7 and wt in (0, 2):
            enclosing += ints(wt, val)
    return rng, sym, roles, enclosing


def relationship(buf):
    sym, impl = '', False
    for num, wt, val in fields(buf):
        if num == 1 and wt == 2:
            sym = text(val)
        elif num == 3 and wt == 0:
            impl = bool(val)
    return sym, impl


def information(buf):
    sym, impls, sig = '', [], ''
    for num, wt, val in fields(buf):
        if num == 1 and wt == 2:
            sym = text(val)
        elif num == 3 and wt == 2 and not sig:
            sig = text(val)
        elif num == 4 and wt == 2:
            other, impl = relationship(val)
            if impl and other:
                impls.append(other)
    return sym, impls, sig


def document(buf):
    doc = {'path': '', 'language': '', 'occurrences': [], 'implements': {}, 'signatures': {}}
    for num, wt, val in fields(buf):
        if wt != 2:
            continue
        if num == 1:
            doc['path'] = text(val).replace('\\', '/').removeprefix('./')
        elif num == 4:
            doc['language'] = text(val)
        elif num == 2:
            try:
                doc['occurrences'].append(occurrence(val))
            except (IndexError, ValueError):
                continue
        elif num == 3:
            try:
                sym, impls, sig = information(val)
            except (IndexError, ValueError):
                continue
            if sym and impls:
                doc['implements'][sym] = impls
            if sym.startswith(TS_SCHEME) and sig and not sym.endswith(')'):
                doc['signatures'][sym] = sig.strip('`').removeprefix('ts\n').strip()
    return doc


def read_index(path):
    try:
        data = memoryview(Path(path).read_bytes())
    except OSError:
        raise CortexError(f'no se pudo leer el índice SCIP «{path}»')
    docs = []
    try:
        for num, wt, val in fields(data):
            if num == 2 and wt == 2:
                try:
                    doc = document(val)
                except (IndexError, ValueError):
                    continue
                if doc['path']:
                    docs.append(doc)
    except (IndexError, ValueError):
        pass
    return docs


def span(rng):
    if len(rng) == 3:
        return rng[0], rng[1], rng[0], rng[2]
    if len(rng) == 4:
        return tuple(rng)
    return None


def kind_of(sym):
    if not sym or sym.startswith('local '):
        return None
    if sym.endswith(').'):
        return 'callable'
    if sym.startswith(DART_SCHEME) and re.search(r'#`<[gs]et>[^`]*`\.$', sym):
        return 'callable'
    if sym.startswith(RUST_SCHEME) and sym.endswith('#') and rust_member_type(sym):
        return 'term'
    if sym.startswith((TS_SCHEME, DART_SCHEME)) and sym.endswith('`/'):
        return 'module'
    return {'#': 'type', ':': 'module', '/': 'namespace', '.': 'term'}.get(sym[-1])


def canonical(sym):
    if sym.startswith((TS_SCHEME, DART_SCHEME)) and sym.endswith('#`<constructor>`().'):
        return sym[:-len('`<constructor>`().')]
    if sym.startswith(JVM_SCHEME) and JVM_CONSTRUCTOR.search(sym):
        return JVM_CONSTRUCTOR.sub('#', sym)
    if sym.startswith(DOTNET_SCHEME) and DOTNET_CONSTRUCTOR.search(sym):
        return DOTNET_CONSTRUCTOR.sub('#', sym)
    return sym


def constructor(sym):
    return canonical(sym) != sym


def function_term(sym, sig):
    if not sig or not sym.startswith(TS_SCHEME) or kind_of(sym) != 'term':
        return False
    head = SIGNATURE_HEAD.match(sig)
    return bool(head and function_type(sig, head.end()) or COMPONENT_TYPE.search(sig))


def balanced(text, i, pairs='()<>{}[]'):
    opens, closes = pairs[0::2], pairs[1::2]
    depth = 0
    while i < len(text):
        c = text[i]
        if c in opens:
            depth += 1
        elif c in closes and not (c == '>' and text[i - 1] == '='):
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def function_type(text, i):
    if text.startswith('{', i):
        i += 1
        while i < len(text) and text[i] in ' \t\n':
            i += 1
    if text.startswith('<', i):
        i = balanced(text, i)
        while 0 <= i < len(text) and text[i] in ' \t\n':
            i += 1
    if i < 0 or not text.startswith('(', i):
        return False
    end = balanced(text, i)
    if end < 0:
        return False
    if text[end:].lstrip().startswith(('=>', ':')):
        return True
    return bool(OPTIONAL_TAIL.fullmatch(text[end:])) and function_type(text[:end - 1], i + 1)


def rust_member_type(sym):
    """Variante de enum o tipo asociado: rust-analyzer los anida bajo otro tipo o bloque impl."""
    tail = sym.split(' ', 4)[-1]
    if RUST_IMPL.search(tail):
        return True
    return tail[tail.rfind('/') + 1:].count('#') > 1


def name_of(sym):
    tail = sym.rstrip('.#:/')
    if tail.endswith(')'):
        tail = tail[:tail.rfind('(')]
    if tail.endswith('`'):
        return tail[tail.rfind('`', 0, -1) + 1:-1]
    return tail[max(tail.rfind(c) for c in '#/. ]') + 1:]


def rust_owner(match):
    owner = match.group(1).strip('`')
    owner = re.sub(r'<.*', '', owner).strip()
    return f'{owner}#' if re.fullmatch(r'\w+', owner) else '?#'


def qualified(sym):
    if sym.startswith(RUST_SCHEME):
        sym = '/' + RUST_IMPL.sub(rust_owner, sym.split(' ', 4)[-1])
    tail = sym[sym.rfind('`/') + 2:] if '`/' in sym else sym[sym.rfind('/') + 1:]
    parts = re.findall(r'(`[^`]+`|[^#.:()/`\s]+)(#|\([^)]*\)\.|\.|:)', tail)
    if not parts or any(k.startswith('(') for _, k in parts[:-1]):
        return None
    if sym.startswith(JVM_SCHEME):
        parts = [p for p in parts[:-1] if p[0] != 'Companion'] + parts[-1:]  # los miembros del companion son de la clase
    return '.'.join(n.strip('`') for n, _ in parts)


def called(lines, s, rel='', block=False):
    if not lines or s[0] != s[2] or s[0] >= len(lines):
        return False
    line = lines[s[0]]
    if DECLARES.search(line[:s[1]]):
        return False
    if jsx_file(rel) and s[1] > 0 and line[s[1] - 1] == '<' and JSX_BEFORE.search(line[:s[1] - 1]):
        return s[3] >= len(line) or line[s[3]] in ' \t/>'
    row, j = s[0], s[3]
    if rel.endswith(TS_EXTS + KOTLIN_EXTS + GENERIC_EXTS) and j < len(line) and line[j] == '<':
        row, j = skip_generic(lines, row, j)
        line = lines[row] if row < len(lines) else ''
    while j < len(line) and line[j] in ' \t':
        j += 1
    return j < len(line) and (line[j] == '(' or block and line[j] == '{' and rel.endswith(KOTLIN_EXTS))


def skip_generic(lines, row, j):
    depth = 0
    for r in range(row, min(row + MAX_GENERIC_LINES, len(lines))):
        line = lines[r]
        while j < len(line):
            c = line[j]
            if c == '<':
                depth += 1
            elif c == '>' and line[j - 1] != '=':
                depth -= 1
                if depth == 0:
                    return r, j + 1
            elif c in ';(' and depth == 1 and r == row:
                return len(lines), 0
            j += 1
        j = 0
    return len(lines), 0


def jsx_file(rel):
    return rel.endswith(('.tsx', '.jsx', '.js', '.mjs', '.cjs'))


def source_lines(root, rel):
    path = Path(root) / rel
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_bytes().decode('utf-8', errors='replace').split('\n')
    except OSError:
        return None


def align(paths, known):
    by_suffix = {}
    for rel in sorted(known):
        parts = rel.split('/')
        for i in range(len(parts)):
            by_suffix.setdefault('/'.join(parts[i:]), []).append(rel)
    out = {}
    for p in paths:
        if p in known:
            out[p] = p
            continue
        parts = p.split('/')
        for i in range(len(parts)):
            hits = by_suffix.get('/'.join(parts[i:]))
            if hits:
                if len(hits) == 1:
                    out[p] = hits[0]
                break
    return out


class Locator:
    def __init__(self, g, files):
        self.mods, spans, self.quals, self.names, self.decls = {}, {}, {}, {}, {}
        for nid, m in g.nodes.items():
            rel = m.get('file')
            if rel not in files:
                continue
            if m.get('kind') == 'module':
                self.mods.setdefault(rel, nid)
            elif m.get('kind') in SYMBOL_KINDS and m.get('line'):
                if m.get('decl'):
                    self.decls.setdefault((rel, m['decl']), nid)
                spans.setdefault(rel, []).append((m['line'], m.get('end') or 0, nid))
                self.names[nid] = str(m.get('name')).rsplit('.', 1)[-1]
                if nid.startswith(f'{nid[0]}:{rel}:'):
                    self.quals.setdefault((rel, nid[len(rel) + 3:]), []).append(nid)
        self.spans = {rel: sorted(v) for rel, v in spans.items()}
        self.starts = {rel: [s[0] for s in v] for rel, v in self.spans.items()}

    def at(self, rel, line):
        spans = self.spans.get(rel, ())
        i = bisect.bisect_right(self.starts.get(rel, ()), line) - 1
        while i >= 0:
            start, end, nid = spans[i]
            if not end or end >= line:
                return nid
            i -= 1
        return self.mods.get(rel)

    def definition(self, rel, line, sym=None):
        if (rel, line) in self.decls:
            # la línea de la declaración de un nodo que empieza en sus anotaciones
            return self.decls[(rel, line)]
        spans = self.spans.get(rel, ())
        i = bisect.bisect_right(self.starts.get(rel, ()), line) - 1
        if i >= 0 and spans[i][0] == line:
            same = [nid for start, _, nid in spans[:i + 1] if start == line]
            name = name_of(sym) if sym and len(same) > 1 else None
            return next((nid for nid in same if name and self.names.get(nid) == name), spans[i][2])
        parts = (qualified(sym) or '').split('.') if sym else []
        for i in range(len(parts) - 1):
            named = self.quals.get((rel, '.'.join(parts[i:])))
            if named:
                if len(named) == 1:
                    return named[0]
                break
        if len(parts) == 1 and len(self.quals.get((rel, parts[0]), ())) == 1:
            return self.quals[(rel, parts[0])][0]
        return self.at(rel, line)


def collect(docs, g, root):
    paths = align([d['path'] for d in docs], {m['file'] for m in g.nodes.values() if m.get('kind') == 'module'})
    loc = Locator(g, set(paths.values()))
    targets = {}
    for d in docs:
        rel = paths.get(d['path'])
        if rel not in loc.mods:
            continue
        for rng, sym, roles, _ in d['occurrences']:
            kind = kind_of(sym)
            s = span(rng)
            if not roles & DEFINITION or not s or sym in targets:
                continue
            if kind == 'term' and sym.startswith(TS_SCHEME):
                nid = loc.definition(rel, s[0] + 1, sym)
                meta = g.nodes.get(nid) or {}
                if (meta.get('decl') or meta.get('line')) == s[0] + 1 and meta.get('kind') in ('function', 'method') and str(meta.get('name')).rsplit('.', 1)[-1] == name_of(sym):
                    targets[sym] = nid
            elif kind in TARGETS:
                targets[sym] = loc.mods[rel] if kind == 'module' else loc.definition(rel, s[0] + 1, sym)
    found = Counter()
    for d in docs:
        rel = paths.get(d['path'])
        if rel not in loc.mods:
            continue
        lines = None
        for rng, sym, roles, _ in d['occurrences']:
            target = targets.get(canonical(sym))
            s = span(rng)
            if roles & DEFINITION or not target or not s:
                continue
            source = loc.at(rel, s[0] + 1)
            trel = g.nodes[target]['file']
            if trel != rel:
                found[(loc.mods[rel], loc.mods[trel], 'import')] += 1
            if target == source or g.nodes[target].get('kind') == 'module':
                continue
            if lines is None:
                lines = source_lines(root, rel) or []
            call = called(lines, s, rel, kind_of(sym) == 'callable')
            if source == loc.mods[rel] and not call:
                continue
            found[(source, target, 'call' if call else 'ref')] += 1
    return found


def merge(g, found):
    linked = {(a, b) for (a, b, k) in g.edges if k in LINKED} | {(b, a) for (a, b, k) in g.edges if k == 'contains'}
    calls = {(a, b) for (a, b, k) in found if k == 'call'}
    added = Counter()
    for (a, b, kind), n in sorted(found.items()):
        if a == b or a not in g.nodes or b not in g.nodes or (a, b, kind) in g.edges:
            continue
        if kind != 'import' and (a, b) in linked:
            continue
        if kind == 'ref' and (a, b) in calls:
            continue
        g.edges[(a, b, kind)] = n
        added[kind] += 1
    return dict(sorted(added.items()))


def apply_scip(g, root, index_path):
    return merge(g, collect(read_index(index_path), g, root))
