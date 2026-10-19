import ast
import json
import os
import re
import sys
import warnings
from collections import defaultdict, deque

from .common import describe_failure, digest, read_source

LINE_RE = re.compile(r'[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$')
PROJECT_MARKERS = ('pyproject.toml', 'setup.py', 'setup.cfg')
STDLIB = frozenset(getattr(sys, 'stdlib_module_names', ()))
MAX_BASE_DEPTH = 8
ROUTE_VERBS = {'get', 'post', 'put', 'patch', 'delete', 'route', 'api_route', 'websocket'}
MAX_SIG = 300
MAX_DOC = 500
MAX_DEFAULT = 24
MAX_DECORATOR = 48
PARAGRAPH_RE = re.compile(r'\n\s*\n')
ROLE_RE = re.compile(r':[\w-]+(?::[\w-]+)?:`~?([^`]*)`')
WRAPPERS = {'Optional', 'Union', 'Final', 'ClassVar', 'Annotated'}
PROPERTIES = {'property', 'cached_property'}
ITEM_METHODS = {'get', 'pop', 'popleft', 'setdefault'}
SEQUENCES = {'ContextVar', 'list', 'List', 'Sequence', 'MutableSequence', 'Iterable', 'Iterator', 'Collection', 'set', 'Set', 'frozenset',
             'FrozenSet', 'AbstractSet', 'MutableSet', 'deque', 'Deque', 'AsyncIterable', 'AsyncIterator', 'Generator',
             'AsyncGenerator', 'ValuesView', 'KeysView', 'Reversible'}
BINDERS = (ast.AnnAssign, ast.Assign, ast.NamedExpr, ast.For, ast.AsyncFor, ast.comprehension, ast.withitem, ast.ExceptHandler,
           ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
MAPPINGS = {'dict', 'Dict', 'Mapping', 'MutableMapping', 'defaultdict', 'DefaultDict', 'OrderedDict', 'ChainMap'}
MAX_INFER = 8


def notebook_source(raw):
    cells = json.loads(raw).get('cells', [])
    lines = []
    for cell in cells:
        if cell.get('cell_type') != 'code':
            continue
        source = cell.get('source', '')
        source = ''.join(source) if isinstance(source, list) else str(source)
        cell_lines = ['' if line.lstrip().startswith(('%', '!', '?')) else line for line in source.splitlines()]
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', SyntaxWarning)
                ast.parse('\n'.join(cell_lines))
        except (SyntaxError, ValueError, RecursionError):
            cell_lines = [''] * len(cell_lines)
        lines += cell_lines + ['']
    return '\n'.join(lines)


def py_module_name(rel):
    mod = os.path.splitext(rel)[0].replace('/', '.')
    return mod[: -len('.__init__')] if mod.endswith('.__init__') else mod


def dotted_dir(rel):
    return os.path.dirname(rel).replace('/', '.')


def is_function(node):
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))


def collapse(text):
    return ' '.join(text.split())


def clip(text, limit):
    return text if len(text) <= limit else text[: limit - 1].rstrip() + '…'


def first_paragraph(text):
    if not text:
        return None
    para = collapse(PARAGRAPH_RE.split(text.strip(), 1)[0])
    para = ROLE_RE.sub(r'\1', para).replace('``', '')
    return clip(para, MAX_DOC) if para else None


def docstring(node):
    try:
        return first_paragraph(ast.get_docstring(node))
    except (TypeError, ValueError):
        return None


def visibility(name):
    if name.startswith('__') and name.endswith('__') and len(name) > 4:
        return 'public'
    return 'private' if name.startswith('_') else 'public'


def line_count(src):
    return max(1, src.count('\n') + (0 if src.endswith('\n') else 1))


def exported(tree):
    names = set()
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, (ast.AugAssign, ast.AnnAssign)) else []
        if any(isinstance(t, ast.Name) and t.id == '__all__' for t in targets) and isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
            names.update(e.value for e in node.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str))
    return names


def tail(node):
    node = node.func if isinstance(node, ast.Call) else node
    return node.attr if isinstance(node, ast.Attribute) else node.id if isinstance(node, ast.Name) else ''


def is_overload(node):
    return is_function(node) and any(tail(d) == 'overload' for d in node.decorator_list)


def real_defs(body):
    impl = {n.name for n in body if is_function(n) and not is_overload(n)}
    return [n for n in body if not (is_overload(n) and n.name in impl)]


def is_none(node):
    return isinstance(node, ast.Constant) and node.value is None or isinstance(node, ast.Name) and node.id == 'None'


def end_of(node):
    return (getattr(node, 'end_lineno', None) or node.lineno, getattr(node, 'end_col_offset', None) or 0)


def bind(names, target, value, at):
    if isinstance(target, ast.Name):
        names[target.id].append((at, value))
    elif isinstance(target, (ast.Tuple, ast.List)):
        for e in target.elts:
            bind(names, e, None, at)
    elif isinstance(target, ast.Starred):
        bind(names, target.value, None, at)


def single(found):
    return found.pop() if len(found) == 1 else None


class Scope:
    def __init__(self, m, cls=None, fn=False):
        self.m, self.cls, self.fn = m, cls, fn
        self.imports = {}
        self.declared = defaultdict(list)
        self.assigned = defaultdict(list)
        self.cache = {}
        self.this = None
        self.nodes = ()
        self.ready = True

    def binds(self, name):
        return name in self.declared or name in self.assigned


def is_super(node):
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'super'


class PyModule:
    def __init__(self, rel, src, parse=True):
        self.rel = rel
        self.src = src
        self.name = py_module_name(rel)
        self.is_pkg = rel.endswith('__init__.py')
        self.tree = ast.Module(body=[], type_ignores=[])
        if parse:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', SyntaxWarning)
                self.tree = ast.parse(src)
        self.defs = {}
        self.imports = {}
        self.stars = []
        self.classes = {}
        self.lines = None
        self.specs = []
        self.local_targets = set()
        self.md_refs = []

    def resolve_relative(self, level, module):
        parts = self.name.split('.')
        if not self.is_pkg:
            parts = parts[:-1]
        if level > 1:
            parts = parts[: len(parts) - (level - 1)]
        return '.'.join(parts + ([module] if module else []))

    def segment(self, node):
        if self.lines is None:
            self.lines = LINE_RE.findall(self.src)
        end, end_col = getattr(node, 'end_lineno', None), getattr(node, 'end_col_offset', None)
        if end is None or end_col is None:
            return ''
        start, col, end = node.lineno - 1, node.col_offset, end - 1
        if start >= len(self.lines) or end >= len(self.lines):
            return ast.get_source_segment(self.src, node) or ''
        if start == end:
            return self.lines[start].encode()[col:end_col].decode()
        first = self.lines[start].encode()[col:].decode()
        last = self.lines[end].encode()[:end_col].decode()
        return ''.join([first, *self.lines[start + 1:end], last])

    def segment_hash(self, node):
        return digest(self.segment(node))

    def text(self, node):
        return collapse(self.segment(node) or ast.unparse(node))

    def decorators(self, node):
        out = []
        for d in node.decorator_list:
            text = self.text(d)
            if len(text) > MAX_DECORATOR and isinstance(d, ast.Call):
                text = self.text(d.func) + '(...)'
            out.append('@' + clip(text, MAX_DECORATOR))
        return out

    def param(self, arg, default=None, prefix=''):
        out = prefix + arg.arg
        if arg.annotation is not None:
            out += ': ' + self.text(arg.annotation)
        if default is not None:
            value = self.text(default)
            value = value if len(value) <= MAX_DEFAULT else '...'
            out += (' = ' if arg.annotation is not None else '=') + value
        return out

    def params(self, a):
        positional = a.posonlyargs + a.args
        defaults = [None] * (len(positional) - len(a.defaults)) + a.defaults
        out = [self.param(arg, d) for arg, d in zip(positional, defaults)]
        if a.posonlyargs:
            out.insert(len(a.posonlyargs), '/')
        if a.vararg:
            out.append(self.param(a.vararg, prefix='*'))
        elif a.kwonlyargs:
            out.append('*')
        out += [self.param(arg, d) for arg, d in zip(a.kwonlyargs, a.kw_defaults)]
        if a.kwarg:
            out.append(self.param(a.kwarg, prefix='**'))
        return ', '.join(out)

    def signature(self, node):
        if isinstance(node, ast.ClassDef):
            bases = [self.text(b) for b in node.bases] + [self.text(k) if k.arg is None else f'{k.arg}={self.text(k.value)}' for k in node.keywords]
            head = f'class {node.name}' + (f'({", ".join(bases)})' if bases else '')
        else:
            head = ('async def ' if isinstance(node, ast.AsyncFunctionDef) else 'def ') + f'{node.name}({self.params(node.args)})'
            if node.returns is not None:
                head += ' -> ' + self.text(node.returns)
        return clip(' '.join(self.decorators(node) + [head]), MAX_SIG)

    def symbol_meta(self, node, vis):
        return {'sig': self.signature(node), 'doc': docstring(node), 'end': getattr(node, 'end_lineno', None) or node.lineno, 'vis': vis}


class PyProject:
    def __init__(self, g, modules, roots=()):
        self.g = g
        self.mods = modules
        self.roots = sorted(set(roots), key=lambda r: (-r.count('.'), r))
        self.prefixes = set()
        for name in modules:
            parts = name.split('.')
            self.prefixes.update('.'.join(parts[:i]) for i in range(1, len(parts) + 1))
        self.class_info = {}
        self.base_cache = {}
        self.root_cache = {}
        self.class_nodes = {}
        self.fn_info = {}
        self.scopes = {}
        self.class_scopes = {}
        self.attr_tables = {}
        self.attr_cache = {}
        self.return_cache = {}
        self.lineages = {}

    def root_for(self, m, head):
        key = (dotted_dir(m.rel), head)
        if key not in self.root_cache:
            self.root_cache[key] = self.find_root(*key)
        return self.root_cache[key]

    def find_root(self, here, head):
        if head in STDLIB:
            return None
        if here and here not in self.mods and f'{here}.{head}' in self.prefixes:
            return here
        matches = [r for r in self.roots if f'{r}.{head}' in self.prefixes]
        near = [r for r in matches if f'{here}.'.startswith(r + '.')]
        if near:
            return near[0]
        return matches[0] if len(matches) == 1 else None

    def rooted(self, m, fq):
        head = fq.split('.', 1)[0]
        if not head or head in self.prefixes:
            return fq
        root = self.root_for(m, head)
        return f'{root}.{fq}' if root else fq

    def resolve(self, fq, depth=0):
        if depth > 4 or not fq:
            return None
        if fq in self.mods:
            return f'm:{self.mods[fq].rel}'
        if '.' not in fq:
            return None
        mod, name = fq.rsplit('.', 1)
        if mod in self.mods:
            m = self.mods[mod]
            if name in m.defs:
                return m.defs[name]
            if name in m.imports:
                return self.resolve(m.imports[name], depth + 1)
            return self.from_stars(m, name, depth + 1)
        if '.' in mod:
            parent, cls = mod.rsplit('.', 1)
            if parent in self.mods and cls in self.mods[parent].classes:
                return self.mods[parent].classes[cls].get(name)
        return None

    def internal(self, fq):
        return fq in self.prefixes or self.module_of(fq) is not None

    def module_of(self, fq):
        while '.' in fq:
            fq = fq.rsplit('.', 1)[0]
            if fq in self.mods:
                return f'm:{self.mods[fq].rel}'
        return None

    def bases_of(self, cid):
        if cid not in self.base_cache:
            self.base_cache[cid] = []
            m, _, bases = self.class_info[cid]
            found = (self.callee(m, base, None) for base in bases)
            self.base_cache[cid] = list(dict.fromkeys(t for t in found if t in self.class_info))
        return self.base_cache[cid]

    def inherited(self, cid, name, depth=0, seen=None):
        if cid not in self.class_info or depth >= MAX_BASE_DEPTH:
            return None
        seen = seen if seen is not None else {cid}
        for base in self.bases_of(cid):
            if base in seen:
                continue
            seen.add(base)
            m, cls, _ = self.class_info[base]
            hit = m.classes[cls].get(name) or self.inherited(base, name, depth + 1, seen)
            if hit:
                return hit
        return None

    def method(self, m, cls, name):
        return m.classes.get(cls, {}).get(name) or self.inherited(f'c:{m.rel}:{cls}', name)

    def from_stars(self, m, name, depth=0):
        return next((hit for hit in (self.resolve(f'{star}.{name}', depth) for star in m.stars) if hit), None)

    def resolve_name(self, m, name, s=None):
        if s is not None and name in s.imports:
            return self.resolve(s.imports[name])
        if name in m.defs:
            return m.defs[name]
        return self.resolve(m.imports[name]) if name in m.imports else self.from_stars(m, name)

    def callee(self, m, fn, cls, s=None):
        if isinstance(fn, ast.Name):
            return self.resolve_name(m, fn.id, s)
        if not isinstance(fn, ast.Attribute):
            return None
        hit = self.static_callee(m, fn, cls, s)
        if hit or s is None:
            return hit
        return self.member(self.expr_type(s, fn.value), fn.attr)

    def static_callee(self, m, fn, cls, s):
        chain = []
        cur = fn
        while isinstance(cur, ast.Attribute):
            chain.append(cur.attr)
            cur = cur.value
        chain.reverse()
        if is_super(cur) and cls and len(chain) == 1:
            return self.inherited(f'c:{m.rel}:{cls}', chain[0])
        if not isinstance(cur, ast.Name):
            return None
        head = cur.id
        if head in ('self', 'cls') and cls and len(chain) == 1:
            return self.method(m, cls, chain[0])
        if s is not None and s.fn and head not in s.imports and s.binds(head):
            return None
        if head in m.classes and len(chain) == 1:
            return self.method(m, head, chain[0])
        imports = s.imports if s is not None and head in s.imports else m.imports
        if head in imports:
            return self.resolve('.'.join([imports[head]] + chain))
        return None

    def member(self, cid, name):
        if cid not in self.class_info:
            return None
        m, cls, _ = self.class_info[cid]
        return self.method(m, cls, name)

    def lineage(self, cid):
        if cid in self.lineages:
            return self.lineages[cid]
        out, todo = [cid], [cid]
        while todo and len(out) <= MAX_BASE_DEPTH * 4:
            nxt = []
            for c in todo:
                for base in self.bases_of(c):
                    if base not in out:
                        out.append(base)
                        nxt.append(base)
            todo = nxt
        self.lineages[cid] = out
        return out

    def class_scope(self, m, cls):
        key = (m.rel, cls)
        if key not in self.class_scopes:
            s = self.class_scopes[key] = Scope(m, cls)
            s.ready = cls is not None
        return self.class_scopes[key]

    def bind_module(self, m, s):
        stack = list(m.tree.body)
        while stack:
            n = stack.pop()
            if is_function(n) or isinstance(n, (ast.ClassDef, ast.Lambda)):
                continue
            self.bind_node(s, n)
            stack.extend(ast.iter_child_nodes(n))

    def bind_node(self, s, n):
        if not isinstance(n, BINDERS):
            return
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            s.declared[n.target.id].append(n.annotation)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                bind(s.assigned, t, n.value if len(n.targets) == 1 else None, end_of(n))
        elif isinstance(n, ast.NamedExpr):
            bind(s.assigned, n.target, n.value, end_of(n))
        elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
            bind(s.assigned, n.target, n, end_of(n.target))
        elif isinstance(n, ast.withitem) and n.optional_vars is not None:
            bind(s.assigned, n.optional_vars, None, end_of(n.optional_vars))
        elif isinstance(n, ast.ExceptHandler) and n.name:
            s.assigned[n.name].append(((n.lineno, n.col_offset), None))
        elif isinstance(n, (ast.Import, ast.ImportFrom)) and s.fn:
            self.bind_import(s.m, n, s.imports)
        elif is_function(n) or isinstance(n, ast.Lambda):
            a = n.args
            for arg in a.posonlyargs + a.args + a.kwonlyargs:
                if arg.annotation is not None:
                    s.declared[arg.arg].append(arg.annotation)
                else:
                    s.assigned[arg.arg].append(((arg.lineno, arg.col_offset), None))
            for arg in (a.vararg, a.kwarg):
                if arg is not None:
                    s.assigned[arg.arg].append(((arg.lineno, arg.col_offset), None))

    def scope(self, m, node, cls):
        if node not in self.scopes:
            s = self.scopes[node] = Scope(m, cls, fn=True)
            s.nodes = list(ast.walk(node))
            for n in s.nodes:
                self.bind_node(s, n)
            for entries in s.assigned.values():
                entries.sort(key=lambda e: e[0])
            first = (node.args.posonlyargs + node.args.args)[:1]
            if cls and first and 'staticmethod' not in {tail(d) for d in node.decorator_list}:
                s.this = first[0].arg
                if first[0].annotation is None:
                    s.declared[s.this] = [f'c:{m.rel}:{cls}']
        return self.scopes[node]

    def annotation_type(self, s, a, depth=0):
        if isinstance(a, str) or a is None or depth > MAX_INFER:
            return a if isinstance(a, str) else None
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            try:
                return self.annotation_type(s, ast.parse(a.value.strip(), mode='eval').body, depth + 1)
            except (SyntaxError, ValueError, RecursionError):
                return None
        if isinstance(a, ast.BinOp) and isinstance(a.op, ast.BitOr):
            parts = [a.left, a.right]
        elif isinstance(a, ast.Subscript) and tail(a.value) in WRAPPERS:
            parts = a.slice.elts if isinstance(a.slice, ast.Tuple) else [a.slice]
            parts = parts[:1] if tail(a.value) == 'Annotated' else parts
        elif isinstance(a, ast.Subscript):
            return self.container(s, a, depth)
        elif isinstance(a, (ast.Name, ast.Attribute)):
            if tail(a) == 'Self':
                return f'c:{s.m.rel}:{s.cls}' if s.cls else None
            target = self.callee(s.m, a, None, s)
            return target if target in self.class_info else None
        else:
            return None
        return single({self.annotation_type(s, p, depth + 1) for p in parts if not is_none(p)})

    def container(self, s, a, depth):
        name = tail(a.value)
        args = list(a.slice.elts) if isinstance(a.slice, ast.Tuple) else [a.slice]
        if name in MAPPINGS and len(args) == 2:
            pair = tuple(self.annotation_type(s, x, depth + 1) for x in args)
        elif name in SEQUENCES or name in ('tuple', 'Tuple') and len(args) == 2 and isinstance(args[1], ast.Constant) and args[1].value is Ellipsis:
            pair = (self.annotation_type(s, args[0], depth + 1),) * 2
        else:
            return None
        return pair if any(pair) else None

    def local_type(self, s, name, at=None):
        entries = s.assigned.get(name, ())
        prior = [i for i, (pos, _) in enumerate(entries) if pos < at] if at and name not in s.declared else ()
        key = (name, prior[-1]) if prior else name
        if key not in s.cache:
            s.cache[key] = None
            if prior:
                value = entries[prior[-1]][1]
                found = {None if value is None else self.expr_type(s, value)}
            elif name in s.declared:
                found = {self.annotation_type(s, a) for a in s.declared[name]}
            else:
                found = {None if v is None else self.expr_type(s, v) for _, v in entries}
            s.cache[key] = single(found)
        return s.cache[key]

    def global_type(self, m, name, depth=0):
        s = self.class_scope(m, None)
        if not s.ready:
            s.ready = True
            self.bind_module(m, s)
        if s.binds(name):
            return self.local_type(s, name)
        fq = m.imports.get(name)
        if fq and '.' in fq and depth < MAX_INFER:
            mod, attr = fq.rsplit('.', 1)
            if mod in self.mods:
                return self.global_type(self.mods[mod], attr, depth + 1)
        return None

    def expr_type(self, s, e, depth=0):
        if depth > MAX_INFER:
            return None
        if isinstance(e, ast.Name):
            return self.local_type(s, e.id, (e.lineno, e.col_offset)) if s.fn and s.binds(e.id) else self.global_type(s.m, e.id)
        if isinstance(e, ast.Attribute):
            return self.attr_type(self.expr_type(s, e.value, depth + 1), e.attr)
        if isinstance(e, ast.Await):
            return self.expr_type(s, e.value, depth + 1)
        if isinstance(e, (ast.Subscript, ast.For, ast.AsyncFor, ast.comprehension)):
            t = self.expr_type(s, e.value if isinstance(e, ast.Subscript) else e.iter, depth + 1)
            return t[isinstance(e, ast.Subscript)] if isinstance(t, tuple) else None
        if isinstance(e, ast.Call):
            target = self.callee(s.m, e.func, s.cls, s)
            if target is None and isinstance(e.func, ast.Attribute) and e.func.attr in ITEM_METHODS:
                t = self.expr_type(s, e.func.value, depth + 1)
                return t[1] if isinstance(t, tuple) else None
            return target if target in self.class_info else self.returns(target)
        return None

    def returns(self, fid):
        if fid not in self.fn_info:
            return None
        if fid not in self.return_cache:
            self.return_cache[fid] = None
            m, node, cls = self.fn_info[fid]
            self.return_cache[fid] = self.annotation_type(self.class_scope(m, cls), node.returns)
        return self.return_cache[fid]

    def attr_table(self, cid):
        if cid not in self.attr_tables:
            m, cls, _ = self.class_info[cid]
            table = tuple(defaultdict(list) for _ in range(4))
            here = self.class_scope(m, cls)
            for sub in self.class_nodes[cid].body:
                if isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name):
                    table[0][sub.target.id].append((here, sub.annotation))
                elif isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        if isinstance(t, ast.Name):
                            table[1][t.id].append((here, sub.value))
                elif is_function(sub):
                    self.self_attrs(self.scope(m, sub, cls), sub, *table[2:])
            self.attr_tables[cid] = table
        return self.attr_tables[cid]

    def self_attrs(self, s, node, declared, assigned):
        if not s.this:
            return
        for n in s.nodes:
            if isinstance(n, ast.AnnAssign):
                targets, value = [n.target], n.annotation
            elif isinstance(n, ast.Assign):
                targets, value = n.targets, n.value if len(n.targets) == 1 else None
            else:
                continue
            for t in targets:
                for e in (t.elts if isinstance(t, (ast.Tuple, ast.List)) else [t]):
                    if isinstance(e, ast.Attribute) and isinstance(e.value, ast.Name) and e.value.id == s.this:
                        if isinstance(n, ast.AnnAssign):
                            declared[e.attr].append((s, value))
                        else:
                            assigned[e.attr].append((s, value if e is t else None))

    def own_attr(self, cid, name, inst):
        declared, assigned = self.attr_table(cid)[2 * inst: 2 * inst + 2]
        if name in declared:
            return cid, single({self.annotation_type(s, a) for s, a in declared[name]})
        if name in assigned:
            return cid, single({None if v is None else self.expr_type(s, v) for s, v in assigned[name]})
        m, cls, _ = self.class_info[cid]
        fid = None if inst else m.classes[cls].get(name)
        if fid is None:
            return None, None
        return fid, self.returns(fid) if PROPERTIES & {tail(d) for d in self.fn_info[fid][1].decorator_list} else None

    def lookup(self, cid, name):
        if cid not in self.class_info:
            return None, None
        key = (cid, name)
        if key not in self.attr_cache:
            self.attr_cache[key] = None, None
            found = ((self.own_attr(c, name, inst) for inst in (0, 1) for c in self.lineage(cid)))
            self.attr_cache[key] = next((hit for hit in found if hit[0]), (None, None))
        return self.attr_cache[key]

    def attr_type(self, cid, name):
        return self.lookup(cid, name)[1]

    def link_calls(self, m, owner, cls, s, nodes=None):
        called = set()
        family = set(self.lineage(f'c:{m.rel}:{cls}')) if cls else ()
        for n in s.nodes if nodes is None else nodes:
            if isinstance(n, ast.Call):
                called.add(n.func)
                target = self.callee(m, n.func, cls, s)
                if target and target != owner:
                    self.g.edge(owner, target, 'call')
            elif isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load) and n not in called:
                target = self.lookup(self.expr_type(s, n.value), n.attr)[0]
                if target and self.g.nodes[target]['file'] != m.rel and self.owner_class(target) not in family:
                    self.g.edge(owner, target, 'ref')

    def owner_class(self, nid):
        if nid in self.class_info:
            return nid
        m, _, cls = self.fn_info.get(nid, (None, None, None))
        return f'c:{m.rel}:{cls}' if cls else None

    def declare(self, m):
        g = self.g
        stem = m.name.rsplit('.', 1)[-1]
        mid = g.node(f'm:{m.rel}', kind='module', name=m.rel.rsplit('/', 1)[-1], file=m.rel, line=1, lang='py', hash=digest(m.src),
                     doc=docstring(m.tree), end=line_count(m.src), vis=visibility(stem))
        public = exported(m.tree)
        for node in real_defs(m.tree.body):
            if is_function(node):
                fid = g.node(f'f:{m.rel}:{node.name}', kind='function', name=node.name, file=m.rel, line=node.lineno, lang='py',
                             route=route_of(node), hash=m.segment_hash(node),
                             **m.symbol_meta(node, 'public' if node.name in public else visibility(node.name)))
                m.defs[node.name] = fid
                self.fn_info.setdefault(fid, (m, node, None))
                g.edge(mid, fid, 'contains')
            elif isinstance(node, ast.ClassDef):
                cid = g.node(f'c:{m.rel}:{node.name}', kind='class', name=node.name, file=m.rel, line=node.lineno, lang='py',
                             table=table_of(node), hash=m.segment_hash(node),
                             **m.symbol_meta(node, 'public' if node.name in public else visibility(node.name)))
                m.defs[node.name] = cid
                methods = m.classes.setdefault(node.name, {})
                self.class_info[cid] = (m, node.name, node.bases)
                self.class_nodes.setdefault(cid, node)
                g.edge(mid, cid, 'contains')
                for sub in real_defs(node.body):
                    if is_function(sub):
                        fid = g.node(f'f:{m.rel}:{node.name}.{sub.name}', kind='method', name=f'{node.name}.{sub.name}',
                                     file=m.rel, line=sub.lineno, lang='py', route=route_of(sub), hash=m.segment_hash(sub),
                                     **m.symbol_meta(sub, visibility(sub.name)))
                        methods[sub.name] = fid
                        self.fn_info.setdefault(fid, (m, sub, node.name))
                        g.edge(cid, fid, 'contains')

    def import_base(self, m, node):
        return m.resolve_relative(node.level, node.module) if node.level else self.rooted(m, node.module or '')

    def bind_import(self, m, node, dest):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    dest[alias.asname] = self.rooted(m, alias.name)
                else:
                    head = alias.name.split('.')[0]
                    dest[head] = self.rooted(m, head)
                    dest[alias.name] = self.rooted(m, alias.name)
            return
        base = self.import_base(m, node)
        for alias in node.names:
            if alias.name != '*':
                dest[alias.asname or alias.name] = f'{base}.{alias.name}' if base else alias.name
            elif base and dest is m.imports and base not in m.stars:
                m.stars.append(base)

    def collect_imports(self, m):
        todo = deque([(m.tree, False)])
        while todo:
            node, nested = todo.popleft()
            inner = nested or is_function(node) or isinstance(node, ast.Lambda)
            todo.extend((c, inner) for c in ast.iter_child_nodes(node))
            if isinstance(node, ast.Constant):
                if isinstance(node.value, str) and node.value.endswith('.md'):
                    m.md_refs.append(node.value)
                continue
            if isinstance(node, ast.Import):
                m.specs += [(a.name, (self.rooted(m, a.name),)) for a in node.names if a.name != '__future__']
            elif isinstance(node, ast.ImportFrom):
                base = self.import_base(m, node)
                if not node.level and node.module and node.module != '__future__':
                    m.specs.append((node.module, tuple(f'{base}.{a.name}' for a in node.names if a.name != '*') + (base,)))
            else:
                continue
            if nested:
                local = {}
                self.bind_import(m, node, local)
                m.local_targets.update(local.values())
            else:
                self.bind_import(m, node, m.imports)

    def link(self, m, doc_names):
        g = self.g
        mid = f'm:{m.rel}'
        for target in sorted(set(m.imports.values()) | set(m.stars) | m.local_targets):
            resolved = self.resolve(target) or self.module_of(target)
            if resolved:
                g.edge(mid, resolved if resolved.startswith('m:') else 'm:' + g.nodes[resolved]['file'], 'import')
        for spec in sorted({spec for spec, targets in m.specs if not any(self.internal(t) for t in targets)}):
            g.external(mid, spec, 'py')
        top = self.class_scope(m, None)
        for node in real_defs(m.tree.body):
            if isinstance(node, ast.ClassDef):
                cid = m.defs[node.name]
                for base in node.bases:
                    target = self.callee(m, base, None)
                    if target:
                        g.edge(cid, target, 'inherits')
                for sub in real_defs(node.body):
                    if is_function(sub):
                        self.link_calls(m, m.classes[node.name][sub.name], node.name, self.scope(m, sub, node.name))
                    else:
                        self.link_calls(m, cid, node.name, self.class_scope(m, node.name), ast.walk(sub))
            elif is_function(node):
                self.link_calls(m, m.defs[node.name], None, self.scope(m, node, None))
            else:
                self.link_calls(m, mid, None, top, ast.walk(node))
        for value in m.md_refs:
            doc = doc_names.get(value.rsplit('/', 1)[-1])
            if doc:
                g.edge(mid, doc, 'loads')


def source_roots(root, modules):
    dirs = set()
    for m in modules.values():
        parts = m.rel.split('/')[:-1]
        dirs.update('/'.join(parts[:i]) for i in range(1, len(parts) + 1))
    roots = set()
    for d in sorted(dirs):
        if d.rsplit('/', 1)[-1] == 'src' or any((root / d / marker).is_file() for marker in PROJECT_MARKERS):
            roots.add(d.replace('/', '.'))
    for m in modules.values():
        if m.is_pkg and '/' in m.rel.rsplit('/', 1)[0]:
            parent = dotted_dir(m.rel).rsplit('.', 1)[0]
            if parent not in modules:
                roots.add(parent)
    return roots


def load_module(rel, raw, issues):
    try:
        src = notebook_source(raw) if rel.endswith('.ipynb') else raw.decode('utf-8-sig', errors='replace')
    except (ValueError, RecursionError, MemoryError, AttributeError) as exc:
        issues.add(rel, describe_failure(exc))
        return None
    try:
        return PyModule(rel, src)
    except (SyntaxError, RecursionError) as exc:
        issues.add(rel, describe_failure(exc))
        return PyModule(rel, src, parse=False)
    except (ValueError, MemoryError, AttributeError) as exc:
        issues.add(rel, describe_failure(exc))
        return None


def analyze_python(root, files, g, issues):
    modules = {}
    for rel in files:
        raw = read_source(root, rel, issues)
        if raw is None:
            continue
        m = load_module(rel, raw, issues)
        if m is not None:
            modules[m.name] = m
    doc_names = {}
    for nid, meta in g.nodes.items():
        if meta['kind'] == 'doc':
            doc_names.setdefault(meta['file'].rsplit('/', 1)[-1], nid)
    project = PyProject(g, modules, source_roots(root, modules))
    for m in list(modules.values()):
        try:
            project.declare(m)
            project.collect_imports(m)
        except RecursionError as exc:
            issues.add(m.rel, describe_failure(exc))
            del modules[m.name]
    for m in modules.values():
        try:
            project.link(m, doc_names)
        except RecursionError as exc:
            issues.add(m.rel, describe_failure(exc))


def route_methods(call):
    for kw in call.keywords:
        if kw.arg == 'methods' and isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
            names = [e.value.upper() for e in kw.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            if names:
                return ','.join(names)
    return None


def route_of(fn):
    for d in fn.decorator_list:
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ROUTE_VERBS:
            if d.args and isinstance(d.args[0], ast.Constant) and isinstance(d.args[0].value, str):
                verb = route_methods(d) if d.func.attr in ('route', 'api_route') else None
                return f'{verb or d.func.attr.upper()} {d.args[0].value}'
    return None


def table_of(cls):
    for n in cls.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__tablename__' for t in n.targets):
            if isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
                return n.value.value
    return None
