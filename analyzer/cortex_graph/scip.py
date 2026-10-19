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
DECLARES = re.compile(r'(\b(def|func|fun|fn|function)\s+|\bfunc\s*\([^)]*\)\s*)$')


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
    sym, impls = '', []
    for num, wt, val in fields(buf):
        if num == 1 and wt == 2:
            sym = text(val)
        elif num == 4 and wt == 2:
            other, impl = relationship(val)
            if impl and other:
                impls.append(other)
    return sym, impls


def document(buf):
    doc = {'path': '', 'language': '', 'occurrences': [], 'implements': {}}
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
                sym, impls = information(val)
            except (IndexError, ValueError):
                continue
            if sym and impls:
                doc['implements'][sym] = impls
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
    return {'#': 'type', ':': 'module', '/': 'namespace', '.': 'term'}.get(sym[-1])


def name_of(sym):
    tail = sym.rstrip('.#:/')
    if tail.endswith(')'):
        tail = tail[:tail.rfind('(')]
    if tail.endswith('`'):
        return tail[tail.rfind('`', 0, -1) + 1:-1]
    return tail[max(tail.rfind(c) for c in '#/. ') + 1:]


def qualified(sym):
    tail = sym[sym.rfind('`/') + 2:] if '`/' in sym else sym[sym.rfind('/') + 1:]
    parts = re.findall(r'(`[^`]+`|[^#.:()/`\s]+)(#|\([^)]*\)\.|\.|:)', tail)
    if not parts or any(k.startswith('(') for _, k in parts[:-1]):
        return None
    return '.'.join(n.strip('`') for n, _ in parts)


def called(lines, s):
    if not lines or s[0] != s[2] or s[0] >= len(lines):
        return False
    line = lines[s[0]]
    if DECLARES.search(line[:s[1]]):
        return False
    j = s[3]
    while j < len(line) and line[j] in ' \t':
        j += 1
    return j < len(line) and line[j] == '('


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
        self.mods, spans, self.quals = {}, {}, {}
        for nid, m in g.nodes.items():
            rel = m.get('file')
            if rel not in files:
                continue
            if m.get('kind') == 'module':
                self.mods.setdefault(rel, nid)
            elif m.get('kind') in SYMBOL_KINDS and m.get('line'):
                spans.setdefault(rel, []).append((m['line'], m.get('end') or 0, nid))
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
        spans = self.spans.get(rel, ())
        i = bisect.bisect_right(self.starts.get(rel, ()), line) - 1
        if i >= 0 and spans[i][0] == line:
            return spans[i][2]
        named = self.quals.get((rel, qualified(sym))) if sym else None
        if named and len(named) == 1:
            return named[0]
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
            if roles & DEFINITION and kind in TARGETS and s and sym not in targets:
                targets[sym] = loc.mods[rel] if kind == 'module' else loc.definition(rel, s[0] + 1, sym)
    found = Counter()
    for d in docs:
        rel = paths.get(d['path'])
        if rel not in loc.mods:
            continue
        lines = None
        for rng, sym, roles, _ in d['occurrences']:
            target = targets.get(sym)
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
            call = called(lines, s)
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
