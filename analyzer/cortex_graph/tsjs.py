import os
import re
from bisect import bisect_right

import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser, Query, QueryCursor

from .common import describe_failure, digest, read_source

TS_SUFFIXES = ['', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.mts', '.cts', '.cjs', '.vue', '.svelte',
               '/index.ts', '/index.tsx', '/index.js', '/index.jsx', '/index.mjs', '/index.vue', '/index.svelte']
TS_PACKAGE_FILES = ('tsconfig.json', 'jsconfig.json', 'package.json')
TS_PATHS_RE = re.compile(r'"([^"]+)"\s*:\s*\[([^\]]*)\]')
TS_BASE_URL_RE = re.compile(r'"baseUrl"\s*:\s*"([^"]*)"')
PKG_NAME_RE = re.compile(r'"name"\s*:\s*"([^"]+)"')
BUILD_DIR_RE = re.compile(r'(^|/)(?:dist|build|lib|out)/')
PKG_ENTRY_RE = re.compile(r'"(?:source|module|main|types|typings)"\s*:\s*"([^"]+)"')
SCRIPT_RE = re.compile(rb'(<script\b[^>]*>)(.*?)</script>', re.S | re.I)
LOAD_RE = re.compile(rb'\b(?:import|require)\s*\(')
FUNCTION_VALUES = {'arrow_function', 'function_expression', 'function', 'generator_function'}
WRAPPERS = {'parenthesized_expression', 'as_expression', 'satisfies_expression', 'non_null_expression'}
COMPONENT_FACTORIES = {'memo', 'forwardRef', 'lazy', 'observer', 'styled', 'connect', 'withRouter',
                       'defineComponent', 'defineAsyncComponent'}
COLLECTION_CALLS = {'map', 'filter', 'reduce', 'reduceRight', 'find', 'findIndex', 'findLast', 'some', 'every',
                    'flatMap', 'forEach', 'sort', 'then', 'catch', 'finally'}
SAME_SHAPE_WRAPPERS = {'useCallback', 'useEvent', 'useEffectEvent', 'useMemoizedFn', 'debounce', 'throttle', 'memoize',
                       'memoizeOne', 'once', 'curry', 'action', 'flow', 'cache'}
HOOK_NAME_RE = re.compile(r'^use[A-Z0-9]')
HOC_NAME_RE = re.compile(r'^with[A-Z]')
FIELD_MEMBERS = ('public_field_definition', 'field_definition')
MAX_HOPS = 5
MAX_BASES = 10
MAX_SIG = 300
MAX_DOC = 500
LOCAL_PREFIXES = ('.', '/', '#', '~', '@/')
FILE_TAGS = ('@file', '@fileoverview', '@overview')
SKIPPED_TAGS = ('@module', '@packagedocumentation')
LINK_RE = re.compile(r'\{@(?:link|linkcode|linkplain)\s+([^}|\s]+)(?:[\s|]+([^}]*))?\}')
VIS_MODIFIERS = {'private': 'private', 'protected': 'protected', 'public': 'public'}


BLANK = bytes(10 if b == 10 else 32 for b in range(256))
TS_LANG = Language(tsts.language_typescript())
TSX_LANG = Language(tsts.language_tsx())
CALL_SITES = '(call_expression) @site (new_expression) @site'
TS_SITES = Query(TS_LANG, CALL_SITES)
TSX_SITES = Query(TSX_LANG, CALL_SITES + ' (jsx_opening_element) @site (jsx_self_closing_element) @site')


def ts_text(node, src):
    return src[node.start_byte:node.end_byte].decode('utf-8', errors='replace')


def json_block(raw, key):
    at = raw.find(f'"{key}"')
    start = raw.find('{', at) if at >= 0 else -1
    if start < 0:
        return ''
    depth = 0
    for i in range(start, len(raw)):
        depth += raw[i] == '{'
        depth -= raw[i] == '}'
        if depth == 0:
            return raw[start:i + 1]
    return raw[start:]


def clean_dir(path):
    path = os.path.normpath(path).replace(os.sep, '/')
    return '' if path in ('.', '') else path


class TsResolver:
    def __init__(self, root, files):
        self.root = root
        self.files = set(files)
        self.config_cache = {}
        self.resolved = {}
        self.packages = self.find_packages()

    def read(self, rel):
        path = self.root / rel
        if not path.is_file():
            return None
        try:
            return path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            return None

    def find_packages(self):
        found = {}
        dirs = set()
        for rel in self.files:
            d = os.path.dirname(rel)
            while d not in dirs:
                dirs.add(d)
                if not d:
                    break
                d = os.path.dirname(d)
        for d in sorted(dirs):
            raw = self.read(os.path.join(d, 'package.json'))
            name = PKG_NAME_RE.search(raw) if raw else None
            if name and name.group(1) not in found:
                found[name.group(1)] = (d, PKG_ENTRY_RE.findall(raw))
        return found

    def config(self, directory):
        if directory not in self.config_cache:
            entries, found, base_url = [], False, None
            for name in TS_PACKAGE_FILES:
                raw = self.read(os.path.join(directory, name))
                if raw is None:
                    continue
                found = True
                if name == 'package.json':
                    continue
                match = TS_BASE_URL_RE.search(raw)
                base = clean_dir(os.path.join(directory, match.group(1))) if match else directory
                if match and base_url is None:
                    base_url = base
                for key, targets in TS_PATHS_RE.findall(json_block(raw, 'paths')):
                    entries.append((key, base, re.findall(r'"([^"]*)"', targets)))
            self.config_cache[directory] = (found, entries, base_url)
        return self.config_cache[directory]

    def alias_bases(self, rel):
        bases = []
        directory = os.path.dirname(rel)
        while True:
            if self.config(directory)[0]:
                bases += [directory, os.path.join(directory, 'src')]
            if not directory:
                break
            directory = os.path.dirname(directory)
        return bases or ['', 'src']

    def candidates(self, rel, spec):
        if spec.startswith('.'):
            return [clean_dir(os.path.join(os.path.dirname(rel), spec))]
        bases = []
        directory = os.path.dirname(rel)
        while True:
            _, entries, base_url = self.config(directory)
            for key, base, targets in entries:
                if key.endswith('*') and spec.startswith(key[:-1]):
                    rest = spec[len(key) - 1:]
                    bases += [clean_dir(os.path.join(base, t.replace('*', rest))) for t in targets]
                elif key == spec:
                    bases += [clean_dir(os.path.join(base, t)) for t in targets]
            if base_url is not None:
                bases.append(clean_dir(os.path.join(base_url, spec)))
            if not directory:
                break
            directory = os.path.dirname(directory)
        head = '/'.join(spec.split('/')[:2]) if spec.startswith('@') else spec.split('/')[0]
        if head in self.packages:
            pdir, entries = self.packages[head]
            sub = spec[len(head):].strip('/')
            if sub:
                bases += [clean_dir(os.path.join(pdir, sub)), clean_dir(os.path.join(pdir, 'src', sub))]
            else:
                for entry in entries:
                    entry = re.sub(r'^\./', '', entry)
                    bases.append(clean_dir(os.path.join(pdir, entry)))
                    bases.append(clean_dir(os.path.join(pdir, re.sub(r'^(dist|build|lib|out)/', 'src/', entry))))
                bases += [clean_dir(os.path.join(pdir, 'src', 'index')), clean_dir(os.path.join(pdir, 'index'))]
        if spec.startswith(('@/', '~/')):
            bases += [clean_dir(os.path.join(b, spec[2:])) for b in self.alias_bases(rel)]
        return bases

    def resolve(self, rel, spec):
        key = (os.path.dirname(rel), spec)
        if key not in self.resolved:
            bases = self.candidates(rel, spec)
            for base in list(bases):
                stem, ext = os.path.splitext(base)
                if ext in ('.js', '.jsx', '.mjs', '.cjs', '.d'):
                    bases.append(stem)
            built = [BUILD_DIR_RE.sub(r'\1src/', b, count=1) for b in bases if BUILD_DIR_RE.search(b)]
            self.resolved[key] = self.first_file(bases) or self.first_file(built)
        return self.resolved[key]

    def first_file(self, bases):
        for base in bases:
            for suffix in TS_SUFFIXES:
                if base + suffix in self.files:
                    return base + suffix
        return None


def script_only(src):
    out = bytearray(src.translate(BLANK))
    for match in SCRIPT_RE.finditer(src):
        start, end = match.start(2), match.end(2)
        out[start:end] = src[start:end]
    return bytes(out)


def clip(text, limit):
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def is_bare(spec):
    return not spec.startswith(LOCAL_PREFIXES) and '://' not in spec


def jsdoc(text, module=False):
    if not text.startswith('/**') or text.startswith('/**/'):
        return ''
    lines, tagged = [], False
    for line in text[3:-2].split('\n'):
        line = line.strip()
        line = line[1:].strip() if line.startswith('*') else line
        low = line.lower()
        if module and low.startswith(FILE_TAGS):
            line, tagged = line.split(None, 1)[1] if ' ' in line else '', True
        elif module and low.startswith(SKIPPED_TAGS):
            tagged = True
            continue
        elif line.startswith('@'):
            break
        if not line and any(lines):
            break
        lines.append(line)
    if module and not tagged:
        return None
    return clip(LINK_RE.sub(lambda m: m.group(2) or m.group(1), ' '.join(lines)), MAX_DOC)


def member_vis(member, src):
    name = member.child_by_field_name('name') or member.child_by_field_name('property')
    if name is not None and name.type == 'private_property_identifier':
        return 'private'
    for c in member.children:
        if c.type == 'accessibility_modifier':
            return VIS_MODIFIERS.get(ts_text(c, src), 'public')
    return 'public'


def inner_function(call, depth=0):
    args = call.child_by_field_name('arguments')
    for arg in args.named_children if args is not None and args.type == 'arguments' else ():
        arg = unwrap(arg)
        if arg.type in FUNCTION_VALUES:
            return arg
        if arg.type == 'call_expression' and depth < 3:
            found = inner_function(arg, depth + 1)
            if found is not None:
                return found
    return None


def unwrap(node):
    while node is not None and node.type in WRAPPERS and node.named_children:
        node = node.named_children[0]
    return node


def literal(node, src):
    if node is None or node.type not in ('string', 'template_string'):
        return None
    if any(c.type == 'template_substitution' for c in node.named_children):
        return None
    return ts_text(node, src).strip('\'"`')


def load_spec(node, src):
    node = unwrap(node)
    if node is not None and node.type == 'await_expression' and node.named_children:
        node = unwrap(node.named_children[0])
    if node is None or node.type != 'call_expression':
        return None
    fn, args = node.child_by_field_name('function'), node.child_by_field_name('arguments')
    if fn is None or args is None or args.type != 'arguments' or not args.named_children:
        return None
    if fn.type == 'import' or (fn.type == 'identifier' and ts_text(fn, src) == 'require'):
        return literal(args.named_children[0], src)
    return None


def callee_names(fn, src):
    last = None
    while fn is not None:
        if fn.type == 'member_expression':
            prop = fn.child_by_field_name('property')
            last = last or (ts_text(prop, src) if prop is not None else None)
            fn = fn.child_by_field_name('object')
        elif fn.type == 'call_expression':
            fn = fn.child_by_field_name('function')
        elif fn.type == 'identifier':
            return ts_text(fn, src), last or ts_text(fn, src)
        else:
            break
    return None, last


def iife_returns_function(callee, src):
    callee = unwrap(callee)
    body = callee.child_by_field_name('body') if callee is not None and callee.type in FUNCTION_VALUES else None
    if body is None:
        return False
    if body.type != 'statement_block':
        return unwrap(body).type in FUNCTION_VALUES
    local = set()
    for statement in body.named_children:
        name = statement.child_by_field_name('name')
        if statement.type == 'function_declaration' and name is not None:
            local.add(ts_text(name, src))
        elif statement.type in ('lexical_declaration', 'variable_declaration'):
            for d in statement.named_children:
                name, value = d.child_by_field_name('name'), unwrap(d.child_by_field_name('value'))
                if name is not None and value is not None and value.type in FUNCTION_VALUES:
                    local.add(ts_text(name, src))
        elif statement.type == 'return_statement':
            value = unwrap(statement.named_children[0]) if statement.named_children else None
            if value is not None and value.type == 'identifier':
                return ts_text(value, src) in local
            return value is not None and value.type in FUNCTION_VALUES
    return False


def is_function_value(value, src):
    value = unwrap(value)
    if value is None:
        return False
    if value.type in FUNCTION_VALUES:
        return True
    if value.type != 'call_expression':
        return False
    callee = value.child_by_field_name('function')
    if iife_returns_function(callee, src):
        return True
    root, last = callee_names(callee, src)
    if root in COMPONENT_FACTORIES or last in COMPONENT_FACTORIES or HOC_NAME_RE.match(root or ''):
        return True
    if last in COLLECTION_CALLS:
        return False
    args = value.child_by_field_name('arguments')
    if args is None or args.type != 'arguments':
        return False
    return any(unwrap(a).type in FUNCTION_VALUES for a in args.named_children)


def is_hook_factory(name, value):
    value = unwrap(value)
    return bool(HOOK_NAME_RE.match(name)) and value is not None and value.type == 'call_expression'


def heritage_of(node):
    refs = []
    for part in node.children:
        if part.type == 'class_heritage':
            for clause in part.named_children:
                if clause.type == 'extends_clause':
                    refs += [('extends', v) for v in clause.children_by_field_name('value')]
                elif clause.type == 'implements_clause':
                    refs += [('implements', v) for v in clause.named_children]
        elif part.type == 'extends_type_clause':
            refs += [('extends', v) for v in part.named_children]
    return refs


class TsModule:
    def __init__(self, g, rel, src, resolver):
        self.g = g
        self.rel = rel
        self.src = src
        self.resolver = resolver
        self.mid = g.node(f'm:{rel}', kind='module', name=rel.rsplit('/', 1)[-1], file=rel, line=1, lang='ts', hash=digest(src),
                          end=src.count(b'\n') + (not src.endswith(b'\n')))
        self.defs = {}
        self.classes = {}
        self.default = None
        self.imports = {}
        self.exports = {}
        self.reexports = {}
        self.wildcards = []
        self.foreign = set()
        self.foreign_star = False
        self.bodies = []
        self.heritage = []
        self.public = set()
        self.outer = None
        self.doc = ''
        tsx = rel.endswith(('.tsx', '.jsx', '.js', '.mjs', '.cjs'))
        self.sites = TSX_SITES if tsx else TS_SITES
        self.tree_root = Parser(TSX_LANG if tsx else TS_LANG).parse(src).root_node
        self.read_top_level(self.tree_root)
        self.read_module_doc(self.tree_root)
        if LOAD_RE.search(src):
            self.read_loads(self.tree_root)
        self.resolver = None

    def text(self, node):
        return ts_text(node, self.src)

    def resolve(self, spec):
        if not spec:
            return None
        target = self.resolver.resolve(self.rel, spec)
        if not target and is_bare(spec):
            self.g.external(self.mid, spec, 'ts')
        return target

    def leading_doc(self, comment, node):
        if comment is None or comment.end_point[0] < node.start_point[0] - 1:
            return ''
        return jsdoc(self.text(comment))

    def read_module_doc(self, tree_root):
        first = tree_root.children[0] if tree_root.children else None
        if first is None or first.type != 'comment':
            return
        doc = jsdoc(self.text(first), module=True)
        after = first.next_sibling
        if doc is None and (after is None or after.start_point[0] > first.end_point[0] + 1):
            doc = jsdoc(self.text(first))
        if doc:
            self.g.nodes[self.mid]['doc'] = doc

    def prefix(self):
        if self.outer is None or self.outer.type != 'export_statement':
            return ''
        return 'export default ' if any(c.type == 'default' for c in self.outer.children) else 'export '

    def top_vis(self):
        return 'public' if self.outer is not None and self.outer.type == 'export_statement' else 'internal'

    def head(self, node, stop):
        start = next((c.start_byte for c in node.children if c.type not in ('decorator', 'comment')), node.start_byte)
        return self.src[start:stop].decode('utf-8', errors='replace')

    def body_start(self, node):
        body = node.child_by_field_name('body')
        return body.start_byte if body is not None else node.end_byte

    def value_sig(self, holder, value, label, before):
        value = unwrap(value)
        if value is None:
            return before + label
        if value.type in FUNCTION_VALUES:
            return before + self.head(holder, self.body_start(value))
        if value.type != 'call_expression':
            return before + label
        callee = value.child_by_field_name('function')
        root, last = callee_names(callee, self.src)
        wraps = root in COMPONENT_FACTORIES or last in COMPONENT_FACTORIES or last in SAME_SHAPE_WRAPPERS or \
            HOC_NAME_RE.match(root or '')
        fn = inner_function(value) if wraps else None
        if fn is not None:
            params = fn.child_by_field_name('parameters') or fn.child_by_field_name('parameter')
            text = self.text(params) if params is not None else ''
            text = text[1:-1] if params is not None and params.type == 'formal_parameters' else text
            ret = fn.child_by_field_name('return_type')
            return f'{label}({text}){self.text(ret) if ret is not None else ""}'
        if callee is not None and callee.type in ('identifier', 'member_expression', 'call_expression') and \
                callee.end_byte - callee.start_byte <= 80:
            return before + self.head(holder, callee.start_byte) + self.text(callee) + '(…)'
        return before + label

    def side(self, target):
        self.imports.setdefault(f'__side__{target}', (target, '*'))

    def symbol(self, key, kind, name, node, line, sig='', end=None, vis=None, doc=''):
        meta = {'sig': clip(sig, MAX_SIG), 'doc': doc, 'end': end or node.end_point[0] + 1, 'vis': vis or self.top_vis()}
        return self.g.node(key, kind=kind, name=name, file=self.rel, line=line, lang='ts',
                           hash=digest(self.src[node.start_byte:node.end_byte]), **{k: v for k, v in meta.items() if v})

    def declare_function(self, name_node, body, line, sig, end):
        name = self.text(name_node)
        sid = self.symbol(f'f:{self.rel}:{name}', 'function', name, body, line, sig, end, doc=self.doc)
        self.defs[name] = sid
        self.g.edge(self.mid, sid, 'contains')
        self.bodies.append((sid, body, None))
        return sid

    def declare_class(self, node, name_node, before):
        name = self.text(name_node)
        cid = self.symbol(f'c:{self.rel}:{name}', 'class', name, node, node.start_point[0] + 1,
                          before + self.head(node, self.body_start(node)), doc=self.doc)
        self.defs[name] = cid
        self.g.edge(self.mid, cid, 'contains')
        self.heritage.append((cid, heritage_of(node)))
        methods = self.classes.setdefault(cid, {})
        body = node.child_by_field_name('body')
        comment, reach = None, -1
        for member in body.named_children if body is not None else []:
            if member.type == 'comment':
                comment, reach = member, member.end_point[0] + 1
                continue
            if member.type == 'decorator' and member.start_point[0] <= reach:
                reach = member.end_point[0] + 1
            method = self.member_method(member)
            if method is None:
                self.bodies.append((cid, member, cid))
                comment = comment if member.type == 'decorator' else None
                continue
            if method not in methods:
                doc = jsdoc(self.text(comment)) if comment is not None and member.start_point[0] <= reach else ''
                methods[method] = self.symbol(f'f:{self.rel}:{name}.{method}', 'method', f'{name}.{method}', member,
                                              member.start_point[0] + 1, self.member_sig(member, method),
                                              vis=member_vis(member, self.src), doc=doc)
                self.g.edge(cid, methods[method], 'contains')
            comment = None
            self.bodies.append((methods[method], member, cid))
        return cid

    def member_sig(self, member, name):
        if member.type == 'method_definition':
            return self.head(member, self.body_start(member))
        return self.value_sig(member, member.child_by_field_name('value'), name, '')

    def declare_interface(self, node, name_node):
        name = self.text(name_node)
        iid = self.symbol(f'c:{self.rel}:{name}', 'class', name, node, node.start_point[0] + 1,
                          self.prefix() + self.head(node, self.body_start(node)), doc=self.doc)
        self.defs.setdefault(name, iid)
        self.g.edge(self.mid, iid, 'contains')
        self.heritage.append((iid, heritage_of(node)))
        return iid

    def member_method(self, member):
        if member.type in FIELD_MEMBERS:
            if not is_function_value(member.child_by_field_name('value'), self.src):
                return None
        elif member.type != 'method_definition':
            return None
        name = member.child_by_field_name('name') or member.child_by_field_name('property')
        if name is None or name.type not in ('property_identifier', 'private_property_identifier', 'string'):
            return None
        return self.text(name).strip('\'"') or None

    def bind(self, pattern, target, replace):
        found = []
        if pattern is not None and pattern.type == 'identifier':
            found.append((self.text(pattern), '*'))
        elif pattern is not None and pattern.type == 'object_pattern':
            for part in pattern.named_children:
                key = part.child_by_field_name('key') if part.type == 'pair_pattern' else part
                alias = part.child_by_field_name('value') if part.type == 'pair_pattern' else part
                if key is not None and alias is not None and alias.type in ('identifier', 'shorthand_property_identifier_pattern'):
                    found.append((self.text(alias), self.text(key).strip('\'"')))
        for alias, name in found:
            if replace:
                self.imports[alias] = (target, name)
            else:
                self.imports.setdefault(alias, (target, name))
        self.side(target)

    def read_top_level(self, tree_root):
        comment = None
        for top in tree_root.children:
            if top.type == 'comment':
                comment = top
                continue
            self.outer, self.doc = top, self.leading_doc(comment, top)
            comment = None
            node, exported_default = top, False
            if top.type == 'export_statement':
                if self.read_export(top):
                    continue
                exported_default = any(c.type == 'default' for c in top.children)
                inner = [c for c in top.children if c.is_named and c.type not in ('comment', 'decorator')]
                node = inner[0] if inner else top
                if exported_default and node.type == 'identifier':
                    self.default = ('name', self.text(node))
                    continue
            sid = self.read_statement(node)
            if exported_default and sid:
                self.default = ('id', sid)
        self.outer, self.doc = None, ''
        self.public.update(self.exports.values())
        if self.default and self.default[0] == 'name':
            self.public.add(self.default[1])
        for name in sorted(self.public):
            meta = self.g.nodes.get(self.defs.get(name))
            if meta is not None and meta.get('file') == self.rel:
                meta['vis'] = 'public'

    def read_export(self, node):
        source = node.child_by_field_name('source')
        clause = next((c for c in node.named_children if c.type == 'export_clause'), None)
        if source is None:
            if clause is None:
                return False
            for spec in clause.named_children:
                name, alias = spec.child_by_field_name('name'), spec.child_by_field_name('alias')
                if name is not None:
                    exported = self.text(alias or name)
                    self.exports[exported] = self.text(name)
                    if exported == 'default' and self.default is None:
                        self.default = ('name', self.text(name))
            return True
        target = self.resolve(literal(source, self.src))
        namespace = next((c for c in node.named_children if c.type == 'namespace_export'), None)
        names = []
        if namespace is not None:
            ids = [c for c in namespace.named_children if c.type in ('identifier', 'string')]
            names = [(self.text(ids[0]).strip('\'"'), '*')] if ids else []
        elif clause is not None:
            for spec in clause.named_children:
                name, alias = spec.child_by_field_name('name'), spec.child_by_field_name('alias')
                if name is not None:
                    names.append((self.text(alias or name), self.text(name)))
        if not target:
            self.foreign.update(exported for exported, _ in names)
            self.foreign_star = self.foreign_star or (namespace is None and clause is None)
            return True
        self.side(target)
        for exported, name in names:
            self.reexports[exported] = (target, name)
        if namespace is None and clause is None and target not in self.wildcards:
            self.wildcards.append(target)
        return True

    def read_statement(self, node):
        kind, name = node.type, node.child_by_field_name('name')
        if kind in ('function_declaration', 'generator_function_declaration') and name is not None:
            return self.declare_function(name, node, node.start_point[0] + 1,
                                         self.prefix() + self.head(node, self.body_start(node)), None)
        if kind in ('class_declaration', 'abstract_class_declaration') and name is not None:
            return self.declare_class(node, name, self.prefix())
        if kind == 'interface_declaration' and name is not None:
            return self.declare_interface(node, name)
        if kind in ('lexical_declaration', 'variable_declaration'):
            self.read_variables(node)
        elif kind == 'import_statement':
            self.read_import(node)
        elif kind == 'expression_statement' and self.read_commonjs(node):
            return None
        elif kind not in ('type_alias_declaration', 'ambient_declaration', 'comment'):
            self.bodies.append((self.mid, node, None))
        return None

    def read_variables(self, node):
        keyword = node.children[0].type + ' ' if node.children and not node.children[0].is_named else ''
        for d in node.children:
            if d.type != 'variable_declarator':
                continue
            value, name = d.child_by_field_name('value'), d.child_by_field_name('name')
            target = self.resolve(load_spec(value, self.src))
            if target:
                self.bind(name, target, True)
            elif name is not None and name.type == 'identifier' and value is not None and value.type == 'class':
                self.declare_class(value, name, self.prefix() + keyword + self.head(d, value.start_byte))
            elif name is not None and name.type == 'identifier' and (
                    is_function_value(value, self.src) or is_hook_factory(self.text(name), value)):
                self.declare_function(name, value, d.start_point[0] + 1,
                                      self.value_sig(d, value, self.text(name), self.prefix() + keyword),
                                      d.end_point[0] + 1)
            elif value is not None:
                self.bodies.append((self.mid, value, None))

    def read_commonjs(self, node):
        expr = node.named_children[0] if node.named_children else None
        target = self.resolve(load_spec(expr, self.src))
        if target:
            self.side(target)
            return True
        if expr is None or expr.type != 'assignment_expression':
            return False
        left, right = expr.child_by_field_name('left'), expr.child_by_field_name('right')
        self.read_cjs_exports(left, right)
        target = self.resolve(load_spec(right, self.src))
        if target and left is not None and self.text(left) == 'module.exports':
            self.side(target)
            if target not in self.wildcards:
                self.wildcards.append(target)
            self.default = self.default or ('module', target)
            return True
        return False

    def read_cjs_exports(self, left, right):
        head = self.text(left) if left is not None and left.type == 'member_expression' else ''
        if right is None or not (head == 'module.exports' or head.startswith(('exports.', 'module.exports.'))):
            return
        if right.type == 'identifier':
            self.public.add(self.text(right))
        elif right.type == 'object' and head == 'module.exports':
            for part in right.named_children:
                value = part.child_by_field_name('value') if part.type == 'pair' else part
                if value is not None and value.type in ('identifier', 'shorthand_property_identifier'):
                    self.public.add(self.text(value))

    def read_loads(self, tree_root):
        for match in LOAD_RE.finditer(self.src):
            word = match.group().split(b'(')[0].rstrip()
            head = tree_root.named_descendant_for_byte_range(match.start(), match.start() + len(word))
            call = head.parent if head is not None else None
            if call is None or call.type != 'call_expression' or call.child_by_field_name('function') != head:
                continue
            target = self.resolve(load_spec(call, self.src))
            if not target:
                continue
            self.side(target)
            holder = call.parent
            while holder is not None and (holder.type in WRAPPERS or holder.type == 'await_expression'):
                holder = holder.parent
            if holder is not None and holder.type == 'variable_declarator':
                self.bind(holder.child_by_field_name('name'), target, False)

    def read_import(self, node):
        source = node.child_by_field_name('source')
        required = next((c for c in node.named_children if c.type == 'import_require_clause'), None)
        if source is None and required is not None:
            target = self.resolve(literal(required.child_by_field_name('source'), self.src))
            names = [c for c in required.named_children if c.type == 'identifier']
            if target and names:
                self.bind(names[0], target, True)
            return
        target = self.resolve(literal(source, self.src)) if source is not None else None
        for alias, name in self.imported_names(node):
            if target:
                self.imports[alias] = (target, name)
            else:
                self.foreign.add(alias)
        if target:
            self.side(target)

    def imported_names(self, node):
        found = []
        for clause in node.children:
            if clause.type != 'import_clause':
                continue
            for part in clause.children:
                if part.type == 'identifier':
                    found.append((self.text(part), 'default'))
                elif part.type == 'namespace_import':
                    ids = [x for x in part.children if x.type == 'identifier']
                    found += [(self.text(ids[0]), '*')] if ids else []
                elif part.type == 'named_imports':
                    for spec in part.children:
                        if spec.type == 'import_specifier':
                            name = spec.child_by_field_name('name')
                            alias = spec.child_by_field_name('alias') or name
                            found.append((self.text(alias), self.text(name).strip('\'"')))
        return found


class TsProject:
    def __init__(self, g, modules):
        self.g = g
        self.modules = modules
        self.cache = {}
        self.methods = {cid: methods for t in modules.values() for cid, methods in t.classes.items()}
        self.parents = {}

    def find(self, target, name, depth, seen):
        t = self.modules.get(target)
        if t is None or depth > MAX_HOPS or (target, name) in seen:
            return None
        seen.add((target, name))
        if name == '*':
            return t.mid
        if name == 'default' and t.default is not None:
            kind, value = t.default
            if kind == 'module':
                return self.find(value, 'default', depth + 1, seen)
            return value if kind == 'id' else self.local(t, value, depth, seen)
        if name in t.defs:
            return t.defs[name]
        if name in t.exports:
            return self.local(t, t.exports[name], depth, seen)
        if name in t.reexports:
            return self.find(*t.reexports[name], depth + 1, seen)
        if name in t.foreign:
            return ''
        if name == 'default':
            return None
        outcome = '' if t.foreign_star else None
        for wildcard in t.wildcards:
            found = self.find(wildcard, name, depth + 1, seen)
            if found:
                return found
            outcome = '' if found == '' else outcome
        return outcome

    def local(self, t, name, depth, seen):
        if name in t.defs:
            return t.defs[name]
        if name in t.imports:
            return self.find(*t.imports[name], depth + 1, seen)
        return '' if name in t.foreign else None

    def exported(self, target, name):
        if (target, name) not in self.cache:
            self.cache[(target, name)] = self.find(target, name, 0, set())
        return self.cache[(target, name)]

    def resolve_import(self, target, name):
        found = self.exported(target, name)
        if found is not None:
            return found or None
        t = self.modules.get(target)
        return t.mid if t else None

    def name_target(self, t, name):
        if name in t.defs:
            return t.defs[name]
        return self.resolve_import(*t.imports[name]) if name in t.imports else None

    def strict_target(self, t, name):
        if name in t.defs:
            return t.defs[name]
        return self.exported(*t.imports[name]) or None if name in t.imports else None

    def ref_target(self, t, node):
        if node is not None and node.type == 'generic_type':
            node = node.child_by_field_name('name')
        if node is None:
            return None
        if node.type in ('identifier', 'type_identifier'):
            return self.strict_target(t, t.text(node))
        if node.type not in ('member_expression', 'nested_type_identifier'):
            return None
        head = node.child_by_field_name('object') or node.child_by_field_name('module')
        tail = node.child_by_field_name('property') or node.child_by_field_name('name')
        if head is None or tail is None or head.type != 'identifier':
            return None
        alias = t.imports.get(t.text(head))
        return self.exported(alias[0], t.text(tail)) if alias and alias[1] == '*' else None

    def link_heritage(self, t):
        for cid, refs in t.heritage:
            for kind, ref in refs:
                target = self.ref_target(t, ref)
                if not target or target == cid or self.g.nodes[target]['kind'] != 'class':
                    continue
                self.g.edge(cid, target, 'inherits')
                parents = self.parents.setdefault(cid, [])
                if kind == 'extends' and target not in parents:
                    parents.append(target)

    def method_of(self, cid, name, depth=0):
        if not cid or depth > MAX_BASES:
            return None
        found = self.methods.get(cid, {}).get(name)
        if found:
            return found
        for parent in self.parents.get(cid, ()):
            found = self.method_of(parent, name, depth + 1)
            if found:
                return found
        return None

    def inherited(self, cid, name):
        for parent in self.parents.get(cid, ()):
            found = self.method_of(parent, name, 1)
            if found:
                return found
        return None

    def member_target(self, t, fn, cls):
        obj, prop = fn.child_by_field_name('object'), fn.child_by_field_name('property')
        if obj is None or prop is None:
            return None
        name = t.text(prop)
        if obj.type == 'this':
            return self.method_of(cls, name)
        if obj.type == 'super':
            return self.inherited(cls, name) if cls else None
        if obj.type != 'identifier':
            return None
        owner = self.strict_target(t, t.text(obj))
        if owner and owner.startswith('m:'):
            return self.resolve_import(owner[2:], name)
        return self.method_of(owner, name) if owner in self.methods else None

    def call_target(self, t, n, cls):
        if n.type == 'call_expression':
            fn = n.child_by_field_name('function')
            if fn is not None and fn.type == 'identifier':
                return self.name_target(t, t.text(fn))
            if fn is not None and fn.type == 'member_expression':
                return self.member_target(t, fn, cls)
            return None
        if n.type == 'new_expression':
            ctor = n.child_by_field_name('constructor')
            return self.name_target(t, t.text(ctor)) if ctor is not None and ctor.type == 'identifier' else None
        if n.type in ('jsx_opening_element', 'jsx_self_closing_element'):
            tag = n.child_by_field_name('name')
            return self.name_target(t, t.text(tag)) if tag is not None and tag.type == 'identifier' else None
        return None

    def link_calls(self, t):
        bodies = sorted(t.bodies, key=lambda b: b[1].start_byte)
        starts = [body.start_byte for _, body, _ in bodies]
        sites = QueryCursor(t.sites).captures(t.tree_root).get('site', [])
        for n in sorted(sites, key=lambda n: (n.start_byte, n.end_byte)):
            at = bisect_right(starts, n.start_byte) - 1
            if at < 0 or n.end_byte > bodies[at][1].end_byte:
                continue
            sid, _, cls = bodies[at]
            target = self.call_target(t, n, cls)
            if target and target != sid:
                self.g.edge(sid, target, 'call')


def analyze_ts(root, files, g, issues):
    resolver = TsResolver(root, files)
    modules = {}
    for rel in files:
        src = read_source(root, rel, issues)
        if src is None:
            continue
        if rel.endswith(('.vue', '.svelte')):
            src = script_only(src)
        try:
            modules[rel] = TsModule(g, rel, src, resolver)
        except (RecursionError, ValueError, MemoryError) as exc:
            issues.add(rel, describe_failure(exc))
    project = TsProject(g, modules)
    for t in modules.values():
        project.link_heritage(t)
    for t in modules.values():
        for target, _ in t.imports.values():
            g.edge(t.mid, f'm:{target}', 'import')
        project.link_calls(t)
