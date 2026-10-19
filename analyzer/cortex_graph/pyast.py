import ast
import json
import os
import re
import sys
import warnings

from .common import describe_failure, digest, read_source

LINE_RE = re.compile(r'[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$')
PROJECT_MARKERS = ('pyproject.toml', 'setup.py', 'setup.cfg')
STDLIB = frozenset(getattr(sys, 'stdlib_module_names', ()))
MAX_BASE_DEPTH = 8
ROUTE_VERBS = {'get', 'post', 'put', 'patch', 'delete', 'route', 'api_route', 'websocket'}


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

    def resolve_name(self, m, name):
        if name in m.defs:
            return m.defs[name]
        return self.resolve(m.imports[name]) if name in m.imports else self.from_stars(m, name)

    def callee(self, m, fn, cls):
        if isinstance(fn, ast.Name):
            return self.resolve_name(m, fn.id)
        if not isinstance(fn, ast.Attribute):
            return None
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
        if head in m.classes and len(chain) == 1:
            return self.method(m, head, chain[0])
        if head in m.imports:
            return self.resolve('.'.join([m.imports[head]] + chain))
        return None

    def link_calls(self, m, node, owner, cls):
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                target = self.callee(m, n.func, cls)
                if target and target != owner:
                    self.g.edge(owner, target, 'call')

    def declare(self, m):
        g = self.g
        mid = g.node(f'm:{m.rel}', kind='module', name=m.rel.rsplit('/', 1)[-1], file=m.rel, line=1, lang='py', hash=digest(m.src))
        for node in m.tree.body:
            if is_function(node):
                fid = g.node(f'f:{m.rel}:{node.name}', kind='function', name=node.name, file=m.rel, line=node.lineno, lang='py',
                             route=route_of(node), hash=m.segment_hash(node))
                m.defs[node.name] = fid
                g.edge(mid, fid, 'contains')
            elif isinstance(node, ast.ClassDef):
                cid = g.node(f'c:{m.rel}:{node.name}', kind='class', name=node.name, file=m.rel, line=node.lineno, lang='py',
                             table=table_of(node), hash=m.segment_hash(node))
                m.defs[node.name] = cid
                m.classes[node.name] = {}
                self.class_info[cid] = (m, node.name, node.bases)
                g.edge(mid, cid, 'contains')
                for sub in node.body:
                    if is_function(sub):
                        fid = g.node(f'f:{m.rel}:{node.name}.{sub.name}', kind='method', name=f'{node.name}.{sub.name}',
                                     file=m.rel, line=sub.lineno, lang='py', route=route_of(sub), hash=m.segment_hash(sub))
                        m.classes[node.name][sub.name] = fid
                        g.edge(cid, fid, 'contains')

    def collect_imports(self, m):
        for node in ast.walk(m.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        m.imports[alias.asname] = self.rooted(m, alias.name)
                    else:
                        head = alias.name.split('.')[0]
                        m.imports[head] = self.rooted(m, head)
                        m.imports[alias.name] = self.rooted(m, alias.name)
            elif isinstance(node, ast.ImportFrom):
                base = m.resolve_relative(node.level, node.module) if node.level else self.rooted(m, node.module or '')
                for alias in node.names:
                    if alias.name != '*':
                        m.imports[alias.asname or alias.name] = f'{base}.{alias.name}' if base else alias.name
                    elif base and base not in m.stars:
                        m.stars.append(base)

    def link(self, m, doc_names):
        g = self.g
        mid = f'm:{m.rel}'
        for target in sorted(set(m.imports.values()) | set(m.stars)):
            resolved = self.resolve(target) or self.module_of(target)
            if resolved:
                g.edge(mid, resolved if resolved.startswith('m:') else 'm:' + g.nodes[resolved]['file'], 'import')
        for node in m.tree.body:
            if isinstance(node, ast.ClassDef):
                cid = m.defs[node.name]
                for base in node.bases:
                    target = self.callee(m, base, None)
                    if target:
                        g.edge(cid, target, 'inherits')
                for sub in node.body:
                    if is_function(sub):
                        self.link_calls(m, sub, m.classes[node.name][sub.name], node.name)
            elif is_function(node):
                self.link_calls(m, node, m.defs[node.name], None)
            else:
                self.link_calls(m, node, mid, None)
        for node in ast.walk(m.tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith('.md'):
                doc = doc_names.get(node.value.rsplit('/', 1)[-1])
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
