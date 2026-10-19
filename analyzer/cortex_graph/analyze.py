import ast
import hashlib
import math
import os
import re
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import igraph as ig
import leidenalg
import networkx as nx
import numpy as np
import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser

from .errors import CortexError

SKIP_DIRS = {
    '.git', 'node_modules', '.next', '__pycache__', '.venv', 'venv', 'dist', 'build',
    '.mypy_cache', '.pytest_cache', '.ruff_cache', 'coverage', '.turbo',
}
TEST_DIRS = {'tests', 'test', '__tests__', 'e2e', 'spec'}
CODE_PY = {'.py'}
CODE_TS = {'.ts', '.tsx', '.js', '.jsx', '.mjs'}
DOCS = {'.md'}
TS_SUFFIXES = ['', '.ts', '.tsx', '.js', '.jsx', '.mjs', '/index.ts', '/index.tsx', '/index.js']
TS_PACKAGE_FILES = ('tsconfig.json', 'jsconfig.json', 'package.json')
TS_ALIAS_RE = re.compile(r'"@/\*"\s*:\s*\[\s*"([^"]*)"')

EDGE_WEIGHT = {'contains': 3.0, 'import': 1.0, 'call': 1.0, 'inherits': 1.5, 'ref': 0.6, 'loads': 1.0}
STRUCTURAL_RANK = {'contains': 3, 'inherits': 2, 'import': 1}
MAX_COMMUNITIES = 28
MIN_COMMUNITY = 8
MIN_NODES = 40
RESOLUTION = 1.6
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_VISIBLE = 70000
MAX_WARNINGS = 50
NEST = 14.0

KIND_ES = {'module': 'archivo', 'doc': 'documento', 'class': 'clase', 'function': 'función', 'method': 'método'}

PALETTE = [
    [1.0, 0.72, 0.5], [0.58, 0.72, 1.0], [0.76, 0.6, 1.0], [1.0, 0.58, 0.66], [0.54, 0.92, 0.84],
    [0.5, 0.84, 1.0], [0.9, 0.62, 0.98], [0.84, 0.96, 0.58], [1.0, 0.7, 0.42], [1.0, 0.52, 0.48],
    [0.62, 1.0, 0.7], [0.98, 0.86, 0.5], [0.7, 0.66, 1.0], [0.56, 0.98, 1.0], [1.0, 0.66, 0.84],
]


def digest(text):
    if isinstance(text, str):
        text = text.encode('utf-8', errors='replace')
    return hashlib.sha1(text).hexdigest()[:12]


def is_test(rel):
    parts = rel.split('/')
    name = parts[-1]
    return (
        bool(TEST_DIRS.intersection(parts[:-1]))
        or name.startswith('test_') or name == 'conftest.py' or name.endswith('_test.py')
        or re.search(r'\.(test|spec)\.[jt]sx?$', name) is not None
    )


def list_files(root, exclude=(), skip_tests=False):
    exclude = tuple(e.strip('/') for e in exclude if e.strip('/'))
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            rel = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, '/')
            if os.path.splitext(name)[1] not in CODE_PY | CODE_TS | DOCS or name.endswith('.d.ts'):
                continue
            if any(rel == e or rel.startswith(e + '/') for e in exclude):
                continue
            if skip_tests and is_test(rel):
                continue
            out.append(rel)
    return out


class Issues:
    def __init__(self):
        self.items = []
        self.total = 0

    def add(self, rel, message):
        self.total += 1
        if len(self.items) < MAX_WARNINGS:
            self.items.append({'file': rel, 'error': message})


def describe_failure(exc):
    if isinstance(exc, SyntaxError):
        return f'sintaxis inválida en la línea {exc.lineno}' if exc.lineno else 'sintaxis inválida'
    if isinstance(exc, RecursionError):
        return 'el código está anidado demasiado profundo para analizarlo'
    if isinstance(exc, OSError):
        return 'no se pudo leer el archivo'
    if isinstance(exc, ValueError):
        return 'el archivo contiene bytes que no son texto'
    return f'no se pudo analizar ({type(exc).__name__})'


def read_source(root, rel, issues):
    path = root / rel
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            issues.add(rel, 'archivo de más de 2 MB: se omitió')
            return None
        return path.read_bytes()
    except OSError as exc:
        issues.add(rel, describe_failure(exc))
        return None


class Graph:
    def __init__(self):
        self.nodes = {}
        self.edges = Counter()

    def node(self, nid, **meta):
        if nid not in self.nodes:
            self.nodes[nid] = meta
        return nid

    def edge(self, a, b, kind):
        if a != b and a in self.nodes and b in self.nodes:
            self.edges[(a, b, kind)] += 1


def py_module_name(rel):
    mod = rel[:-3].replace('/', '.')
    return mod[: -len('.__init__')] if mod.endswith('.__init__') else mod


def is_function(node):
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))


class PyModule:
    def __init__(self, rel, src):
        self.rel = rel
        self.src = src
        self.name = py_module_name(rel)
        self.is_pkg = rel.endswith('__init__.py')
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', SyntaxWarning)
            self.tree = ast.parse(src)
        self.defs = {}
        self.imports = {}
        self.classes = {}

    def resolve_relative(self, level, module):
        parts = self.name.split('.')
        if not self.is_pkg:
            parts = parts[:-1]
        if level > 1:
            parts = parts[: len(parts) - (level - 1)]
        return '.'.join(parts + ([module] if module else []))

    def segment_hash(self, node):
        return digest(ast.get_source_segment(self.src, node) or '')


class PyProject:
    def __init__(self, g, modules):
        self.g = g
        self.mods = modules

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
            return None
        if '.' in mod:
            parent, cls = mod.rsplit('.', 1)
            if parent in self.mods and cls in self.mods[parent].classes:
                return self.mods[parent].classes[cls].get(name)
        return None

    def resolve_name(self, m, name):
        return m.defs.get(name) or (self.resolve(m.imports[name]) if name in m.imports else None)

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
        if not isinstance(cur, ast.Name):
            return None
        chain.reverse()
        head = cur.id
        if head in ('self', 'cls') and cls and len(chain) == 1:
            return m.classes.get(cls, {}).get(chain[0])
        if head in m.classes and len(chain) == 1:
            return m.classes[head].get(chain[0])
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
                g.edge(mid, cid, 'contains')
                for sub in node.body:
                    if is_function(sub):
                        fid = g.node(f'f:{m.rel}:{node.name}.{sub.name}', kind='method', name=f'{node.name}.{sub.name}',
                                     file=m.rel, line=sub.lineno, lang='py', route=route_of(sub), hash=m.segment_hash(sub))
                        m.classes[node.name][sub.name] = fid
                        g.edge(cid, fid, 'contains')

    @staticmethod
    def collect_imports(m):
        for node in ast.walk(m.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        m.imports[alias.asname] = alias.name
                    else:
                        head = alias.name.split('.')[0]
                        m.imports[head] = head
                        m.imports[alias.name] = alias.name
            elif isinstance(node, ast.ImportFrom):
                base = m.resolve_relative(node.level, node.module) if node.level else (node.module or '')
                for alias in node.names:
                    if alias.name != '*':
                        m.imports[alias.asname or alias.name] = f'{base}.{alias.name}' if base else alias.name

    def link(self, m, doc_names):
        g = self.g
        mid = f'm:{m.rel}'
        for target in set(m.imports.values()):
            resolved = self.resolve(target)
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


def analyze_python(root, files, g, issues):
    modules = {}
    for rel in files:
        raw = read_source(root, rel, issues)
        if raw is None:
            continue
        try:
            modules[py_module_name(rel)] = PyModule(rel, raw.decode('utf-8', errors='replace'))
        except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
            issues.add(rel, describe_failure(exc))
    doc_names = {}
    for nid, meta in g.nodes.items():
        if meta['kind'] == 'doc':
            doc_names.setdefault(meta['file'].rsplit('/', 1)[-1], nid)
    project = PyProject(g, modules)
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


def route_of(fn):
    for d in fn.decorator_list:
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in {'get', 'post', 'put', 'patch', 'delete'}:
            if d.args and isinstance(d.args[0], ast.Constant) and isinstance(d.args[0].value, str):
                return f'{d.func.attr.upper()} {d.args[0].value}'
    return None


def table_of(cls):
    for n in cls.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__tablename__' for t in n.targets):
            if isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
                return n.value.value
    return None


TS_LANG = Language(tsts.language_typescript())
TSX_LANG = Language(tsts.language_tsx())


def ts_text(node, src):
    return src[node.start_byte:node.end_byte].decode('utf-8', errors='replace')


class TsResolver:
    def __init__(self, root, files):
        self.root = root
        self.files = set(files)
        self.alias_cache = {}

    def package_alias(self, directory):
        if directory not in self.alias_cache:
            found = None
            for name in TS_PACKAGE_FILES:
                path = self.root / directory / name
                if path.is_file():
                    found = found or []
                    try:
                        match = TS_ALIAS_RE.search(path.read_text(encoding='utf-8', errors='replace'))
                    except OSError:
                        match = None
                    if match:
                        target = match.group(1).rstrip('*').strip('/')
                        found.insert(0, os.path.normpath(os.path.join(directory, target)).replace(os.sep, '/'))
            self.alias_cache[directory] = found
        return self.alias_cache[directory]

    def alias_bases(self, rel):
        bases = []
        directory = os.path.dirname(rel)
        while True:
            aliases = self.package_alias(directory)
            if aliases is not None:
                bases += aliases + [directory, os.path.join(directory, 'src')]
            if not directory:
                break
            directory = os.path.dirname(directory)
        if not bases:
            bases = ['', 'src']
        seen = []
        for b in bases:
            b = '' if b in ('', '.') else b.strip('/') + '/'
            if b not in seen:
                seen.append(b)
        return seen

    def resolve(self, rel, spec):
        if spec.startswith('@/'):
            bases = [b + spec[2:] for b in self.alias_bases(rel)]
        elif spec.startswith('.'):
            bases = [os.path.normpath(os.path.join(os.path.dirname(rel), spec)).replace(os.sep, '/')]
        else:
            return None
        for base in list(bases):
            stem, ext = os.path.splitext(base)
            if ext in ('.js', '.jsx', '.mjs'):
                bases.append(stem)
        for base in bases:
            for suffix in TS_SUFFIXES:
                if base + suffix in self.files:
                    return base + suffix
        return None


class TsModule:
    def __init__(self, g, rel, src, resolver):
        self.g = g
        self.rel = rel
        self.src = src
        self.mid = g.node(f'm:{rel}', kind='module', name=rel.rsplit('/', 1)[-1], file=rel, line=1, lang='ts', hash=digest(src))
        self.defs = {}
        self.default = None
        self.imports = {}
        self.bodies = []
        parser = Parser(TSX_LANG if rel.endswith(('.tsx', '.jsx', '.js', '.mjs')) else TS_LANG)
        self.read_top_level(parser.parse(src).root_node, resolver)

    def declare(self, name_node, kind, body, line):
        name = ts_text(name_node, self.src)
        sid = self.g.node(f'f:{self.rel}:{name}', kind=kind, name=name, file=self.rel, line=line, lang='ts',
                          hash=digest(self.src[body.start_byte:body.end_byte]))
        self.defs[name] = sid
        self.g.edge(self.mid, sid, 'contains')
        self.bodies.append((sid, body))
        return sid

    def read_top_level(self, tree_root, resolver):
        src = self.src
        for top in tree_root.children:
            node, exported_default = top, False
            if top.type == 'export_statement':
                exported_default = any(c.type == 'default' for c in top.children)
                inner = [c for c in top.children if c.is_named and c.type not in ('comment', 'decorator')]
                node = inner[0] if inner else top
                if exported_default and node.type == 'identifier':
                    self.default = ('name', ts_text(node, src))
                    continue
            if node.type in ('function_declaration', 'generator_function_declaration') and node.child_by_field_name('name'):
                sid = self.declare(node.child_by_field_name('name'), 'function', node, node.start_point[0] + 1)
                if exported_default:
                    self.default = ('id', sid)
            elif node.type in ('class_declaration', 'abstract_class_declaration') and node.child_by_field_name('name'):
                sid = self.declare(node.child_by_field_name('name'), 'class', node, node.start_point[0] + 1)
                if exported_default:
                    self.default = ('id', sid)
            elif node.type in ('lexical_declaration', 'variable_declaration'):
                for d in node.children:
                    if d.type == 'variable_declarator':
                        value, name = d.child_by_field_name('value'), d.child_by_field_name('name')
                        if (name is not None and name.type == 'identifier' and value is not None
                                and value.type in ('arrow_function', 'function_expression', 'function', 'call_expression')):
                            self.declare(name, 'function', value, d.start_point[0] + 1)
            elif node.type == 'import_statement':
                self.read_import(node, resolver)

    def read_import(self, node, resolver):
        src = self.src
        source = node.child_by_field_name('source')
        if source is None:
            return
        target = resolver.resolve(self.rel, ts_text(source, src).strip('\'"'))
        if not target:
            return
        for clause in node.children:
            if clause.type != 'import_clause':
                continue
            for part in clause.children:
                if part.type == 'identifier':
                    self.imports[ts_text(part, src)] = (target, 'default')
                elif part.type == 'namespace_import':
                    ids = [x for x in part.children if x.type == 'identifier']
                    if ids:
                        self.imports[ts_text(ids[0], src)] = (target, '*')
                elif part.type == 'named_imports':
                    for spec in part.children:
                        if spec.type == 'import_specifier':
                            name = spec.child_by_field_name('name')
                            alias = spec.child_by_field_name('alias') or name
                            self.imports[ts_text(alias, src)] = (target, ts_text(name, src))
        self.imports.setdefault(f'__side__{target}', (target, '*'))


def analyze_ts(root, files, g, issues):
    resolver = TsResolver(root, files)
    modules = {}
    for rel in files:
        src = read_source(root, rel, issues)
        if src is None:
            continue
        try:
            modules[rel] = TsModule(g, rel, src, resolver)
        except (RecursionError, ValueError, MemoryError) as exc:
            issues.add(rel, describe_failure(exc))

    def resolve_import(target, name):
        t = modules.get(target)
        if not t:
            return None
        if name == 'default':
            if t.default is None:
                return t.mid
            kind, value = t.default
            return value if kind == 'id' else t.defs.get(value, t.mid)
        if name == '*':
            return t.mid
        return t.defs.get(name, t.mid)

    for t in modules.values():
        for target, _ in t.imports.values():
            g.edge(t.mid, f'm:{target}', 'import')
        src = t.src
        for sid, body in t.bodies:
            stack = [body]
            while stack:
                n = stack.pop()
                stack.extend(n.children)
                name = None
                if n.type == 'call_expression':
                    fn = n.child_by_field_name('function')
                    if fn is not None and fn.type == 'identifier':
                        name = ts_text(fn, src)
                    elif fn is not None and fn.type == 'member_expression':
                        obj, prop = fn.child_by_field_name('object'), fn.child_by_field_name('property')
                        if obj is not None and prop is not None and obj.type == 'identifier':
                            alias = ts_text(obj, src)
                            if alias in t.imports and t.imports[alias][1] == '*':
                                target = resolve_import(t.imports[alias][0], ts_text(prop, src))
                                if target:
                                    g.edge(sid, target, 'call')
                elif n.type in ('jsx_opening_element', 'jsx_self_closing_element'):
                    tag = n.child_by_field_name('name')
                    if tag is not None and tag.type == 'identifier':
                        name = ts_text(tag, src)
                if name:
                    target = t.defs.get(name)
                    if not target and name in t.imports:
                        target = resolve_import(*t.imports[name])
                    if target and target != sid:
                        g.edge(sid, target, 'call')


PATH_RE = re.compile(r'[\w@.\-/]+\.(?:py|tsx?|jsx?|mjs|md|ya?ml|sh|sql|toml)\b')
DOTTED_RE = re.compile(r'\bsrc(?:\.\w+)+\b')


def declare_docs(root, files, g, issues):
    texts = {}
    for rel in files:
        raw = read_source(root, rel, issues)
        if raw is None:
            continue
        g.node(f'd:{rel}', kind='doc', name=rel.rsplit('/', 1)[-1], file=rel, line=1, lang='md', hash=digest(raw))
        texts[rel] = raw.decode('utf-8', errors='replace')
    return texts


def link_docs(texts, g, all_files):
    by_base = defaultdict(list)
    for f in all_files:
        by_base[f.rsplit('/', 1)[-1]].append(f)
    known = {meta['file'] for meta in g.nodes.values()}
    for rel, text in texts.items():
        did = f'd:{rel}'
        mentions = set(PATH_RE.findall(text)) | {h.replace('.', '/') + '.py' for h in DOTTED_RE.findall(text)}
        for hit in mentions:
            hit = hit.lstrip('./')
            nearby = os.path.normpath(os.path.join(os.path.dirname(rel), hit)).replace(os.sep, '/')
            if hit in known:
                targets = [hit]
            elif nearby in known:
                targets = [nearby]
            else:
                same_name = by_base.get(hit.rsplit('/', 1)[-1], [])
                targets = same_name if len(same_name) == 1 else []
            for target in targets:
                g.edge(did, f'd:{target}' if target.endswith('.md') else f'm:{target}', 'ref')


def community_name(members_files):
    tops = Counter(f.split('/', 1)[0] for f in members_files if '/' in f)
    if tops:
        top, n = tops.most_common(1)[0]
        if top.startswith('.') and n * 2 >= len(members_files):
            return top.lstrip('.')
    dirs = Counter()
    for f in members_files:
        parts = f.split('/')[:-1]
        dirs['/'.join(parts[:3]) if parts else '(raíz)'] += 1
    top = dirs.most_common(1)[0][0]
    label = top.split('/')[-1] or top
    return label.lstrip('.').replace('_', ' ') or top


def neighbour_weights(w, comm, c):
    links = Counter()
    for (a, b), wt in w.items():
        if comm[a] == c and comm[b] != c:
            links[comm[b]] += wt
        elif comm[b] == c and comm[a] != c:
            links[comm[a]] += wt
    return links


def detect_communities(g):
    file_of = {nid: ('d:' if m['kind'] == 'doc' else 'm:') + m['file'] for nid, m in g.nodes.items()}
    files = sorted(set(file_of.values()))
    index = {f: i for i, f in enumerate(files)}
    w = Counter()
    for (a, b, kind), n in g.edges.items():
        fa, fb = file_of[a], file_of[b]
        if fa != fb:
            w[(min(index[fa], index[fb]), max(index[fa], index[fb]))] += EDGE_WEIGHT[kind] * n
    graph = ig.Graph(n=len(files), edges=list(w.keys()))
    graph.es['weight'] = list(w.values())
    partition = leidenalg.find_partition(graph, leidenalg.RBConfigurationVertexPartition, weights='weight',
                                         resolution_parameter=RESOLUTION, seed=7)
    comm = list(partition.membership)

    sizes = Counter(comm)
    folder = defaultdict(Counter)
    for f, c in zip(files, comm):
        if sizes[c] > 1:
            folder[os.path.dirname(f[2:])][c] += 1
    for i, f in enumerate(files):
        if sizes[comm[i]] == 1:
            d = os.path.dirname(f[2:])
            while d and not folder.get(d):
                d = os.path.dirname(d)
            if folder.get(d):
                comm[i] = folder[d].most_common(1)[0][0]

    def merge_small():
        initial = Counter(comm)
        for c in sorted(initial, key=lambda x: initial[x]):
            sizes = Counter(comm)
            if sizes[c] >= MIN_COMMUNITY and len(sizes) <= MAX_COMMUNITIES:
                continue
            links = neighbour_weights(w, comm, c)
            if links:
                target = links.most_common(1)[0][0]
            elif sizes[c] >= MIN_COMMUNITY or len(sizes) <= MAX_COMMUNITIES:
                continue
            else:
                target = max((x for x in sizes if x != c), key=lambda x: sizes[x])
            comm[:] = [target if x == c else x for x in comm]

    def folder_key(f):
        parts = f[2:].split('/')[:-1]
        return '/'.join(parts[:2]) if parts else '(raíz)'

    sizes = Counter(comm)
    linked = set()
    for (a, b) in w:
        if comm[a] != comm[b]:
            linked.update((comm[a], comm[b]))
    home = {}
    for c in sorted(sizes, key=lambda x: -sizes[x]):
        if sizes[c] >= MIN_COMMUNITY or c in linked:
            continue
        key = Counter(folder_key(f) for f, x in zip(files, comm) if x == c).most_common(1)[0][0]
        if key in home:
            comm[:] = [home[key] if x == c else x for x in comm]
        else:
            home[key] = c
    for _ in range(3):
        merge_small()

    hidden = defaultdict(set)
    for f, c in zip(files, comm):
        top = f[2:].split('/', 1)[0]
        if top.startswith('.') and '/' in f[2:]:
            hidden[top].add(c)
    for top, cs in hidden.items():
        owned = [c for c in cs
                 if sum(1 for f, x in zip(files, comm) if x == c and f[2:].startswith(top + '/')) * 2 >= Counter(comm)[c]]
        for c in owned[1:]:
            comm[:] = [owned[0] if x == c else x for x in comm]

    file_nodes = Counter(file_of[nid] for nid in g.nodes)
    for _ in range(3):
        weight = Counter()
        for f, c in zip(files, comm):
            weight[c] += file_nodes[f]
        for c in sorted(weight, key=lambda x: weight[x]):
            if weight[c] >= MIN_NODES:
                continue
            links = neighbour_weights(w, comm, c)
            if not links:
                top = Counter(f[2:].split('/', 1)[0] for f, x in zip(files, comm) if x == c).most_common(1)[0][0]
                for f, x in zip(files, comm):
                    if x != c and f[2:].split('/', 1)[0] == top:
                        links[x] += 1
            if links:
                target = links.most_common(1)[0][0]
                comm[:] = [target if x == c else x for x in comm]

    remap = {c: k for k, (c, _) in enumerate(Counter(comm).most_common())}
    file_comm = {f: remap[c] for f, c in zip(files, comm)}
    return {nid: file_comm[file_of[nid]] for nid in g.nodes}


def spread_directions(ncomm, radius, community_graph, rng):
    dirs = rng.normal(size=(ncomm, 3))
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    wmax = max((d['weight'] for _, _, d in community_graph.edges(data=True)), default=1)
    size = np.array([radius[j] for j in range(ncomm)])
    for _ in range(300):
        force = np.zeros_like(dirs)
        for i in range(ncomm):
            diff = dirs[i] - dirs
            dist2 = (diff ** 2).sum(axis=1) + 1e-3
            force[i] = (diff * (size * radius[i] / dist2 ** 1.5)[:, None]).sum(axis=0)
        for a, b, d in community_graph.edges(data=True):
            pull = (dirs[b] - dirs[a]) * 0.4 * d['weight'] / wmax
            force[a] += pull
            force[b] -= pull
        dirs += force * 0.002
        dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    return dirs


def pack_centers(dirs, radius, rng):
    ncomm = len(dirs)
    centers = np.array([dirs[c] * (NEST + radius[c] * 2.5) for c in range(ncomm)])
    for it in range(600):
        moved = False
        if it < 500:
            centers *= 0.985
        for i in range(ncomm):
            d = np.linalg.norm(centers[i])
            need = NEST + radius[i]
            if d < need:
                centers[i] = centers[i] / d * need if d else rng.normal(size=3) * need
                moved = True
            for j in range(i + 1, ncomm):
                v = centers[j] - centers[i]
                dist = np.linalg.norm(v) or 1e-3
                need = (radius[i] + radius[j]) * 1.12 + 3
                if dist < need:
                    push = (need - dist) / 2 * v / dist
                    centers[i] -= push
                    centers[j] += push
                    moved = True
        if not moved and it >= 500:
            break
    return centers


def layout(g, community, seed=7):
    rng = np.random.default_rng(seed)
    members = defaultdict(list)
    for nid, c in community.items():
        members[c].append(nid)
    ncomm = len(members)
    community_graph = nx.Graph()
    community_graph.add_nodes_from(range(ncomm))
    for (a, b, kind), n in g.edges.items():
        ca, cb = community[a], community[b]
        if ca != cb:
            prev = community_graph.get_edge_data(ca, cb, {}).get('weight', 0)
            community_graph.add_edge(ca, cb, weight=prev + EDGE_WEIGHT[kind] * n)
    radius = {c: max(4.5, 1.05 * len(m) ** (1 / 3) * 1.25) for c, m in members.items()}
    centers = pack_centers(spread_directions(ncomm, radius, community_graph, rng), radius, rng)

    adj = defaultdict(Counter)
    for (a, b, kind), n in g.edges.items():
        if community[a] == community[b]:
            adj[a][b] += EDGE_WEIGHT[kind] * n
    node_pos = {}
    for c, nodes in members.items():
        sub = nx.Graph()
        sub.add_nodes_from(nodes)
        for a in nodes:
            for b, wt in adj[a].items():
                sub.add_edge(a, b, weight=wt)
        if len(nodes) == 1:
            local = {nodes[0]: np.zeros(3)}
        else:
            local = nx.spring_layout(sub, dim=3, seed=seed + c, iterations=80, k=1.4 / math.sqrt(len(nodes)))
        arr = np.array([local[n] for n in nodes], dtype=float)
        arr -= arr.mean(axis=0)
        r90 = np.percentile(np.linalg.norm(arr, axis=1), 90) or 1
        arr = arr / r90 * radius[c] + rng.normal(scale=0.15, size=arr.shape)
        for n, p in zip(nodes, arr):
            node_pos[n] = centers[c] + p
    return centers, radius, node_pos, members


def rounded(vector):
    return [round(float(x), 3) for x in vector]


def analyze(root, project=None, exclude=(), skip_tests=False):
    root = Path(root)
    if not root.is_dir():
        raise CortexError(f'no existe la carpeta «{root}»')
    files = list_files(root, exclude, skip_tests)
    py = [f for f in files if os.path.splitext(f)[1] in CODE_PY]
    ts = [f for f in files if os.path.splitext(f)[1] in CODE_TS]
    md = [f for f in files if os.path.splitext(f)[1] in DOCS]
    issues = Issues()
    g = Graph()
    texts = declare_docs(root, md, g, issues)
    analyze_python(root, py, g, issues)
    analyze_ts(root, ts, g, issues)
    link_docs(texts, g, files)
    if not g.nodes:
        raise CortexError('no hay archivos de código ni documentos para analizar (.py, .ts, .tsx, .js, .jsx, .mjs, .md)')

    community = detect_communities(g)
    centers, radius, node_pos, members = layout(g, community)

    degree = Counter()
    for (a, b, _), n in g.edges.items():
        degree[a] += n
        degree[b] += n

    ids = {nid: i for i, nid in enumerate(g.nodes)}
    communities = []
    for c in range(len(centers)):
        hub = max((n for n in members[c] if g.nodes[n]['kind'] in ('module', 'doc')), key=lambda n: degree[n], default=members[c][0])
        communities.append({
            'id': c, 'name': community_name([g.nodes[n]['file'] for n in members[c]]), 'hub': g.nodes[hub]['name'],
            'size': len(members[c]), 'center': rounded(centers[c]), 'radius': round(float(radius[c]), 3),
            'color': PALETTE[c % len(PALETTE)],
        })
    repeated = Counter(c['name'] for c in communities)
    for c in communities:
        if repeated[c['name']] > 1:
            c['name'] = f"{c['name']} · {c['hub'].rsplit('.', 1)[0]}"

    nodes = []
    for nid, meta in g.nodes.items():
        nodes.append({
            'id': ids[nid], 'key': nid, 'c': community[nid], 'kind': meta['kind'], 'name': meta['name'],
            'file': meta['file'], 'line': meta['line'], 'deg': degree[nid], 'pos': rounded(node_pos[nid]),
            **({'route': meta['route']} if meta.get('route') else {}),
            **({'table': meta['table']} if meta.get('table') else {}),
            'hash': meta.get('hash', ''),
        })
    for (a, b, kind) in g.edges:
        if kind == 'contains':
            nodes[ids[b]]['parent'] = ids[a]
    edges = [{'a': ids[a], 'b': ids[b], 'kind': kind, 'w': n} for (a, b, kind), n in g.edges.items()]
    visible = cap_visible(visible_edges(g, community, ids))
    return {
        'project': project or root.resolve().name,
        'stats': {
            'files': len(files), 'nodes': len(nodes), 'edges': len(edges), 'communities': len(communities),
            'kinds': dict(Counter(n['kind'] for n in nodes)), 'edge_kinds': dict(Counter(e['kind'] for e in edges)),
            'tests': not skip_tests, 'excluded': list(exclude), 'warnings': issues.items, 'warnings_total': issues.total,
        },
        'communities': communities, 'nodes': nodes, 'edges': edges, 'visible': visible,
    }


def visible_edges(g, community, ids):
    file_node = {m['file']: nid for nid, m in g.nodes.items() if m['kind'] in ('module', 'doc')}
    keep = {}
    cross = defaultdict(Counter)
    for (a, b, kind), n in g.edges.items():
        fa, fb = g.nodes[a]['file'], g.nodes[b]['file']
        if kind == 'call':
            if fa == fb:
                continue
            a, b, kind = file_node.get(fa, a), file_node.get(fb, b), 'import'
        if community[a] != community[b]:
            pair = tuple(sorted((community[a], community[b])))
            cross[pair][(file_node.get(fa, a), file_node.get(fb, b))] += n
            continue
        key = (min(a, b), max(a, b))
        if key not in keep or kind != 'import':
            keep[key] = (a, b, kind, keep.get(key, (0, 0, 0, 0))[3] + n)
    out = [{'a': ids[a], 'b': ids[b], 'kind': kind, 'w': n} for a, b, kind, n in keep.values()]
    for links in cross.values():
        for (a, b), n in links.most_common(2):
            out.append({'a': ids[a], 'b': ids[b], 'kind': 'import', 'w': n})
    return out


def cap_visible(edges, limit=MAX_VISIBLE):
    if len(edges) <= limit:
        return edges
    ranked = sorted(range(len(edges)), key=lambda i: (STRUCTURAL_RANK.get(edges[i]['kind'], 0), edges[i]['w']), reverse=True)
    chosen = set(ranked[:limit])
    return [e for i, e in enumerate(edges) if i in chosen]


def export_json(out):
    comm_files = defaultdict(list)
    for n in out['nodes']:
        if n['kind'] in ('module', 'doc'):
            comm_files[n['c']].append(n['file'])
    return {
        'project': out['project'],
        'generator': 'Córtex · análisis estático determinista (AST + Leiden), sin IA',
        'stats': out['stats'],
        'communities': [{'id': c['id'], 'name': c['name'], 'hub': c['hub'], 'size': c['size'], 'files': sorted(comm_files[c['id']])}
                        for c in out['communities']],
        'version': out.get('version'),
        'history': out.get('history', []),
        'changes': out.get('changes'),
        'nodes': [{k: n[k] for k in ('id', 'key', 'kind', 'name', 'file', 'line', 'c', 'deg', 'parent', 'route', 'table', 'hash', 'status') if k in n}
                  for n in out['nodes']],
        'edges': [{'source': e['a'], 'target': e['b'], 'kind': e['kind'], 'weight': e['w']} for e in out['edges']],
    }


def export_markdown(out):
    nodes, edges, comms = out['nodes'], out['edges'], out['communities']
    st = out['stats']
    cname = {c['id']: c['name'] for c in comms}
    children = defaultdict(list)
    for n in nodes:
        if 'parent' in n:
            children[n['parent']].append(n)
    imports = defaultdict(set)
    imported_by = Counter()
    cross = Counter()
    for e in edges:
        a, b = nodes[e['a']], nodes[e['b']]
        if a['c'] != b['c']:
            cross[(a['c'], b['c'])] += e['w']
        if e['kind'] == 'import' and a['kind'] == 'module' and b['kind'] == 'module':
            imports[a['file']].add(b['file'])
            imported_by[b['file']] += 1

    def all_symbols(n):
        found = []
        for child in children[n['id']]:
            found.append(child)
            found.extend(all_symbols(child))
        return found

    lines = []
    add = lines.append
    add(f"# Grafo de conocimiento · {out['project']}\n")
    add(f"> Generado por Córtex: análisis estático determinista (AST de Python y TypeScript, comunidades con Leiden), sin IA. "
        f"{st['files']} archivos · {st['nodes']} nodos · {st['edges']} relaciones · {st['communities']} comunidades."
        f"{' Tests excluidos.' if not st.get('tests', True) else ''}"
        f"{' Carpetas omitidas: ' + ', '.join(f'`{e}`' for e in st['excluded']) + '.' if st.get('excluded') else ''}\n")
    add('## Cómo usar este archivo\n')
    add('Es un mapa del código para un asistente. Las **comunidades** son subsistemas detectados por cómo se conectan los archivos '
        '(imports, llamadas, herencia). Antes de leer código, ubica aquí dónde vive cada cosa: cada símbolo trae `archivo:línea`. '
        'Los «nodos más conectados» son los puntos de los que más depende el resto: cambiarlos tiene más impacto.\n')

    hist = out.get('history') or []
    if hist:
        add('## Versiones\n')
        add('| versión | fecha | origen | commit | archivos | nodos | nuevos | modificados | eliminados |')
        add('|---|---|---|---|---|---|---|---|---|')
        for h in hist:
            origin = h.get('origin') or {}
            source = origin.get('url') or origin.get('type') or '—'
            commit = ((h.get('commit') or {}).get('sha') or '')[:8] or '—'
            ch = h.get('changes', {})
            add(f"| v{h['v']} | {h['date'][:16].replace('T', ' ')} | {source} | {commit} | {h['stats']['files']} | {h['stats']['nodes']} | "
                f"{ch.get('added', 0)} | {ch.get('modified', 0)} | {ch.get('removed', 0)} |")
        add('')
    changes = out.get('changes') or {}
    if len(hist) > 1 and any(changes.get(k) for k in ('added', 'modified', 'removed')):
        by_key = {n['key']: n for n in nodes}
        add(f"## Cambios desde la versión anterior (v{hist[-2]['v']} → v{hist[-1]['v']})\n")
        for title, keys in (('Nuevos', changes.get('added', [])), ('Modificados', changes.get('modified', []))):
            if keys:
                add(f'**{title}** ({len(keys)}):')
                for k in keys[:80]:
                    n = by_key[k]
                    add(f"- {KIND_ES.get(n['kind'], n['kind'])} **{n['name']}** · `{n['file']}:{n['line']}`")
                if len(keys) > 80:
                    add(f'- … y {len(keys) - 80} más')
                add('')
        if changes.get('removed'):
            add(f"**Eliminados** ({len(changes['removed'])}):")
            for n in changes['removed'][:80]:
                add(f"- {KIND_ES.get(n['kind'], n['kind'])} **{n['name']}** · `{n['file']}`")
            add('')

    add('## Comunidades\n')
    add('| # | comunidad | nodos | archivos | archivo central | se conecta sobre todo con |')
    add('|---|---|---|---|---|---|')
    for c in comms:
        files = [n for n in nodes if n['c'] == c['id'] and n['kind'] in ('module', 'doc')]
        links = Counter()
        for (a, b), w in cross.items():
            if a == c['id']:
                links[b] += w
            elif b == c['id']:
                links[a] += w
        top = ', '.join(cname[x] for x, _ in links.most_common(3)) or '—'
        add(f"| {c['id']} | **{c['name']}** | {c['size']} | {len(files)} | `{c['hub']}` | {top} |")
    add('')

    add('## Nodos más conectados\n')
    for n in sorted(nodes, key=lambda n: -n['deg'])[:30]:
        add(f"- **{n['name']}** · {KIND_ES.get(n['kind'], n['kind'])} · `{n['file']}:{n['line']}` · {n['deg']} conexiones · {cname[n['c']]}")
    add('')

    add('## Dependencias entre comunidades\n')
    for (a, b), w in cross.most_common(30):
        add(f'- {cname[a]} → {cname[b]} ({w})')
    add('')

    routes = [n for n in nodes if n.get('route')]
    if routes:
        add('## Rutas de la API\n')
        for n in sorted(routes, key=lambda n: n['route'].split(' ', 1)[-1]):
            add(f"- `{n['route']}` → {n['name']} · `{n['file']}:{n['line']}`")
        add('')
    tables = [n for n in nodes if n.get('table')]
    if tables:
        add('## Tablas de base de datos\n')
        for n in sorted(tables, key=lambda n: n['table']):
            add(f"- `{n['table']}` → {n['name']} · `{n['file']}:{n['line']}`")
        add('')

    docs = [n for n in nodes if n['kind'] == 'doc']
    doc_refs = defaultdict(list)
    for e in edges:
        if e['kind'] == 'ref':
            doc_refs[nodes[e['a']]['file']].append(nodes[e['b']]['file'])
    if docs:
        add('## Documentos\n')
        for n in sorted(docs, key=lambda n: -n['deg'])[:60]:
            refs = sorted(set(doc_refs[n['file']]))
            tail = f" · menciona: {', '.join(f'`{r}`' for r in refs[:8])}{' …' if len(refs) > 8 else ''}" if refs else ''
            add(f"- `{n['file']}`{tail}")
        add('')

    add('## Detalle por comunidad\n')
    for c in comms:
        add(f"### {c['name']} · {c['size']} nodos\n")
        files = sorted((n for n in nodes if n['c'] == c['id'] and n['kind'] == 'module'), key=lambda n: -n['deg'])
        for f in files:
            syms = all_symbols(f)
            classes = [s['name'] for s in syms if s['kind'] == 'class']
            funcs = [s['name'] for s in syms if s['kind'] in ('function', 'method')]
            parts = [f"`{f['file']}` · {f['deg']} conexiones"]
            if imported_by[f['file']]:
                parts.append(f"lo importan {imported_by[f['file']]}")
            add('- ' + ' · '.join(parts))
            if classes:
                add(f"  - clases: {', '.join(classes[:15])}{' …' if len(classes) > 15 else ''}")
            if funcs:
                add(f"  - funciones: {', '.join(funcs[:20])}{f' … (+{len(funcs) - 20})' if len(funcs) > 20 else ''}")
            deps = sorted(imports[f['file']])
            if deps:
                add(f"  - importa: {', '.join(f'`{d}`' for d in deps[:10])}{' …' if len(deps) > 10 else ''}")
        add('')
    return '\n'.join(lines)
