import os
import re
from bisect import bisect_right
from collections import defaultdict

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
JS_EXTS = ('.js', '.jsx', '.mjs', '.cjs')
JSDOC_TYPE = re.compile(r'@type\s*\{([^}]*)\}')
FUNCTION_VALUES = {'arrow_function', 'function_expression', 'function', 'generator_function'}
WRAPPERS = {'parenthesized_expression', 'as_expression', 'satisfies_expression', 'non_null_expression'}
COMPONENT_FACTORIES = {'memo', 'forwardRef', 'lazy', 'observer', 'styled', 'connect', 'withRouter',
                       'defineComponent', 'defineAsyncComponent'}
VALUE_TYPES = {'Promise', 'Array', 'ReadonlyArray', 'Record', 'Map', 'Set', 'ReadonlyMap', 'ReadonlySet', 'WeakMap', 'WeakSet', 'Partial',
               'Required', 'Readonly', 'Pick', 'Omit', 'Date', 'RegExp', 'Error', 'String', 'Number', 'Boolean', 'Iterable',
               'Iterator', 'AsyncIterable', 'Generator', 'AsyncGenerator'}
COLLECTION_CALLS = {'map', 'filter', 'reduce', 'reduceRight', 'find', 'findIndex', 'findLast', 'some', 'every',
                    'flatMap', 'forEach', 'sort', 'then', 'catch', 'finally'}
SAME_SHAPE_WRAPPERS = {'useCallback', 'useEvent', 'useEffectEvent', 'useMemoizedFn', 'debounce', 'throttle', 'memoize',
                       'memoizeOne', 'once', 'curry', 'action', 'flow', 'cache'}
HOOK_NAME_RE = re.compile(r'^use[A-Z0-9]')
HOC_NAME_RE = re.compile(r'^with[A-Z]')
FIELD_MEMBERS = ('public_field_definition', 'field_definition')
SIGNATURES = ('abstract_method_signature', 'method_signature')
MAX_HOPS = 5
MAX_WALK = 4000
BUILTIN_NAMESPACES = {'console', 'Math', 'Object', 'Array', 'String', 'Number', 'Function', 'JSON', 'Reflect', 'Promise', 'Date',
                      'Symbol', 'Boolean', 'RegExp'}
BUILTIN_VALUES = {'prototype', 'length', 'name', 'constructor'}
GENERIC_LINE_RE = re.compile(rb'\n[ \t]+<')
SIGNATURE_ENDS = {b')', b']', b'}', b'>'} | {bytes([c]) for c in b'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$'}
MAX_INFER = 20
DEF = 'def'
FUNCTION_SCOPES = {'arrow_function', 'function_expression', 'function', 'function_declaration', 'generator_function',
                   'generator_function_declaration', 'method_definition'}
THIS_HOLDERS = (FUNCTION_SCOPES - {'arrow_function'}) | {'class_body'}
SCOPE_NODES = FUNCTION_SCOPES | {'statement_block', 'program', 'switch_case', 'switch_default', 'for_in_statement',
                                 'catch_clause', 'class_static_block'}
DECLARED = {'function_declaration', 'generator_function_declaration', 'class_declaration', 'abstract_class_declaration'}
TRANSPARENT = {'Promise', 'PromiseLike', 'Readonly', 'Required', 'Partial', 'NonNullable', 'Awaited', 'RefObject',
               'MutableRefObject'}
MAX_BASES = 10
MAPPED_TYPES = {'Partial', 'Required', 'Readonly', 'Pick', 'Omit', 'Record'}
ELEM = 'elem'
NULLISH = {b'undefined', b'null', b'void'}
ITERATING = {'forEach', 'map', 'filter', 'find', 'findIndex', 'findLast', 'findLastIndex', 'some', 'every', 'flatMap',
             'reduce', 'reduceRight'}
COLLECTIONS = {'Array', 'ReadonlyArray', 'Set', 'ReadonlySet'}
MAX_SIG = 300
MAX_DOC = 500
LOCAL_PREFIXES = ('.', '/', '#', '~', '@/')
FILE_TAGS = ('@file', '@fileoverview', '@overview')
SKIPPED_TAGS = ('@module', '@packagedocumentation')
LINK_RE = re.compile(r'\{@(?:link|linkcode|linkplain)\s+([^}|\s]+)(?:[\s|]+([^}]*))?\}')
VIS_MODIFIERS = {'private': 'private', 'protected': 'protected', 'public': 'public'}


IDENT_RE = re.compile(r'[A-Za-z_$][\w$]*')
BLANK = bytes(10 if b == 10 else 32 for b in range(256))
TS_LANG = Language(tsts.language_typescript())
TSX_LANG = Language(tsts.language_tsx())
CALL_SITES = '(call_expression) @site (new_expression) @site'
TS_SITES = Query(TS_LANG, CALL_SITES)
TSX_SITES = Query(TSX_LANG, CALL_SITES + ' (jsx_opening_element) @site (jsx_self_closing_element) @site')
READS = '(member_expression) @read (object) @obj (variable_declarator name: (object_pattern) value: (_)) @pattern'
TS_READS = Query(TS_LANG, READS)
TSX_READS = Query(TSX_LANG, READS)


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
    body = callee.child_by_field_name('body') if callee is not None and (callee.type in FUNCTION_VALUES or callee.type == 'function_declaration') else None
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
    if value.type == 'ternary_expression':
        return any(unwrap(value.child_by_field_name(f)) is not None and unwrap(value.child_by_field_name(f)).type in FUNCTION_VALUES
                   for f in ('consequence', 'alternative'))
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


def jsdoc_hides(t, assign):
    """`/** @type {object} */ this.serve = new Serve()`: TypeScript toma el tipo del JSDoc, no el del valor; si no es la
    clase que se crea, el campo no se tipa por su valor."""
    stmt = assign.parent if assign.parent is not None and assign.parent.type == 'expression_statement' else None
    prev = stmt.prev_named_sibling if stmt is not None else None
    if prev is None or prev.type != 'comment' or prev.end_point[0] + 1 < stmt.start_point[0]:
        return False
    found = JSDOC_TYPE.search(t.text(prev))
    if not found:
        return False
    right = unwrap(assign.child_by_field_name('right'))
    ctor = right.child_by_field_name('constructor') if right is not None and right.type == 'new_expression' else None
    return ctor is None or t.text(ctor) != found.group(1).strip()


def is_hook_factory(name, value):
    value = unwrap(value)
    return bool(HOOK_NAME_RE.match(name)) and value is not None and value.type == 'call_expression'


def function_typed(member):
    annotation = member.child_by_field_name('type')
    value = annotation.named_children[0] if annotation is not None and annotation.named_children else None
    return is_function_type(value)


def type_query(member):
    """`date: typeof date`: el nombre cuyo tipo copia la propiedad (se confirma al enlazar que es una función)."""
    annotation = member.child_by_field_name('type')
    value = annotation.named_children[0] if annotation is not None and annotation.named_children else None
    inner = value.named_children[0] if value is not None and value.type == 'type_query' and value.named_children else None
    return inner if inner is not None and inner.type in ('identifier', 'member_expression') else None


def is_function_type(value):
    while value is not None and value.type == 'parenthesized_type' and value.named_children:
        value = value.named_children[0]
    if value is not None and value.type == 'union_type':
        parts = [p for p in value.named_children if not (p.type in ('predefined_type', 'literal_type') and p.text in NULLISH)]
        return len(parts) == 1 and is_function_type(parts[0])
    return value is not None and value.type == 'function_type'


def function_params(node):
    if node.type in FIELD_MEMBERS:
        node = unwrap(node.child_by_field_name('value'))
    return node.child_by_field_name('parameters') if node is not None else None


def context_param(home, params, index):
    items = [p for p in params.named_children if p.type in ('required_parameter', 'optional_parameter')]
    annotation = items[index].child_by_field_name('type') if index < len(items) else None
    return (home, annotation) if annotation is not None else None


def separate_signatures(src):
    if b'\n' not in src or not GENERIC_LINE_RE.search(src):
        return src
    out, last = bytearray(src), b''
    start = 0
    for line in src.split(b'\n'):
        code = line.strip()
        if code.startswith(b'<') and line[:1] in (b' ', b'\t') and last[-1:] in SIGNATURE_ENDS and not last.endswith(b'=>'):
            out[start + len(line) - len(line.lstrip()) - 1] = ord(';')
        if code and not code.startswith((b'//', b'*', b'/*')):
            last = code
        start += len(line) + 1
    return bytes(out)


def declaration_of(node):
    if node.type != 'export_statement':
        return node
    return next((c for c in node.named_children if c.type not in ('comment', 'decorator')), node)


def is_getter(node):
    return node.type == 'method_definition' and any(c.type == 'get' for c in node.children)


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
        self.shapes = {}
        self.aliases = {}
        self.vars = {}
        self.funcs = {}
        self.ns = ''
        self.cjs_export = None
        self.default_members = {}
        self.loads_at = {}
        self.namespaces = {}
        self.ns_bodies = {}
        self.pending = []
        self.wrapped = []
        self.member_fns = set()
        tsx = rel.endswith(('.tsx', '.jsx', '.js', '.mjs', '.cjs'))
        self.sites = TSX_SITES if tsx else TS_SITES
        self.reads = TSX_READS if tsx else TS_READS
        self.tree_root = Parser(TSX_LANG if tsx else TS_LANG).parse(src if tsx else separate_signatures(src)).root_node
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

    def table(self):
        """Nombres declarados en el ámbito actual: el módulo o el `namespace` que se está leyendo."""
        return self.namespaces[self.ns[:-1]] if self.ns else self.defs

    def declare_function(self, name_node, body, line, sig, end):
        name = self.text(name_node)
        sid = self.symbol(f'f:{self.rel}:{self.ns}{name}', 'function', self.ns + name, body, line, sig, end, doc=self.doc)
        self.table()[name] = sid
        self.g.edge(self.mid, sid, 'contains')
        self.bodies.append((sid, body, None))
        self.funcs[sid] = (unwrap(body), None)
        return sid

    def declare_class(self, node, name_node, before):
        bare = self.text(name_node)
        name = self.ns + bare
        cid = self.symbol(f'c:{self.rel}:{name}', 'class', name, node, node.start_point[0] + 1,
                          before + self.head(node, self.body_start(node)), doc=self.doc)
        self.table()[bare] = cid
        self.g.edge(self.mid, cid, 'contains')
        self.heritage.append((cid, heritage_of(node)))
        methods = self.classes.setdefault(cid, {})
        body = node.child_by_field_name('body')
        self.shapes[cid] = body
        comment, reach = None, -1
        for member in body.named_children if body is not None else []:
            if member.type == 'comment':
                comment, reach = member, member.end_point[0] + 1
                continue
            if member.type == 'decorator' and member.start_point[0] <= reach:
                reach = member.end_point[0] + 1
            method = self.member_method(member)
            if method is None:
                alias = self.member_alias(member)
                if alias is not None:
                    self.pending.append(('member', cid, name, alias, member, unwrap(member.child_by_field_name('value')), None))
                self.bodies.append((cid, member, cid))
                comment = comment if member.type == 'decorator' else None
                continue
            if method not in methods:
                doc = jsdoc(self.text(comment)) if comment is not None and member.start_point[0] <= reach else ''
                methods[method] = self.symbol(f'f:{self.rel}:{name}.{method}', 'method', f'{name}.{method}', member,
                                              member.start_point[0] + 1, self.member_sig(member, method),
                                              vis=member_vis(member, self.src), doc=doc)
                self.g.edge(cid, methods[method], 'contains')
                self.funcs[methods[method]] = (member, cid)
            else:
                self.stretch(methods[method], member)
            comment = None
            self.bodies.append((methods[method], member, cid))
        return cid

    def stretch(self, sid, node):
        meta = self.g.nodes[sid]
        meta['end'] = max(meta.get('end') or 0, node.end_point[0] + 1)

    def member_sig(self, member, name):
        if member.type == 'method_definition':
            return self.head(member, self.body_start(member))
        if member.type in SIGNATURES or member.child_by_field_name('value') is None:
            return self.head(member, member.end_byte).rstrip(';,')
        return self.value_sig(member, member.child_by_field_name('value'), name, '')

    def declare_interface(self, node, name_node):
        bare = self.text(name_node)
        name = self.ns + bare
        iid = self.symbol(f'c:{self.rel}:{name}', 'class', name, node, node.start_point[0] + 1,
                          self.prefix() + self.head(node, self.body_start(node)), doc=self.doc)
        self.table().setdefault(bare, iid)
        self.g.edge(self.mid, iid, 'contains')
        self.heritage.append((iid, heritage_of(node)))
        body = node.child_by_field_name('body')
        self.shapes.setdefault(iid, body)
        self.declare_signatures(iid, name, body)
        return iid

    def declare_signatures(self, iid, name, body):
        methods = self.classes.setdefault(iid, {})
        comment = None
        for member in body.named_children if body is not None else ():
            if member.type == 'comment':
                comment = member
                continue
            key = member.child_by_field_name('name')
            kind = member.type == 'method_signature' or member.type == 'property_signature' and function_typed(member)
            query = type_query(member) if not kind and member.type == 'property_signature' else None
            if query is not None and key is not None and key.type == 'property_identifier':
                self.pending.append(('member', iid, name, self.text(key), member, query, None))
            if not kind or key is None or key.type not in ('property_identifier', 'string') or self.text(key).strip('\'"') in methods:
                comment = None
                continue
            method = self.text(key).strip('\'"')
            doc = jsdoc(self.text(comment)) if comment is not None and comment.end_point[0] >= member.start_point[0] - 1 else ''
            methods[method] = self.symbol(f'f:{self.rel}:{name}.{method}', 'method', f'{name}.{method}', member,
                                          member.start_point[0] + 1, self.head(member, member.end_byte).rstrip(';,'),
                                          vis='public', doc=doc)
            self.g.edge(iid, methods[method], 'contains')
            self.funcs[methods[method]] = (member, iid)
            comment = None

    def declare_type(self, node, name_node):
        bare = self.text(name_node)
        name = self.ns + bare
        tid = self.symbol(f'c:{self.rel}:{name}', 'class', name, node, node.start_point[0] + 1,
                          self.prefix() + clip(self.text(node), MAX_SIG), doc=self.doc)
        self.table().setdefault(bare, tid)
        self.g.edge(self.mid, tid, 'contains')
        if node.type == 'type_alias_declaration':
            value = node.child_by_field_name('value')
            self.aliases[tid] = value
            if value is not None and value.type == 'object_type':
                self.shapes.setdefault(tid, value)
        return tid

    def member_method(self, member):
        if member.type in FIELD_MEMBERS:
            value = member.child_by_field_name('value')
            if not is_function_value(value, self.src) and not (value is None and function_typed(member)):
                return None
        elif member.type != 'method_definition' and member.type not in SIGNATURES:
            return None
        name = member.child_by_field_name('name') or member.child_by_field_name('property')
        if name is None or name.type not in ('property_identifier', 'private_property_identifier', 'string'):
            return None
        return self.text(name).strip('\'"') or None

    def member_alias(self, member):
        """`min = this.gte;` o `static create = crear;`: campo cuyo valor es otra función (se confirma al enlazar)."""
        value = unwrap(member.child_by_field_name('value')) if member.type in FIELD_MEMBERS else None
        name = member.child_by_field_name('name') or member.child_by_field_name('property')
        if value is None or value.type not in ('member_expression', 'identifier') or name is None or \
                name.type not in ('property_identifier', 'private_property_identifier'):
            return None
        return self.text(name)

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
                assigned = any(c.type == '=' for c in top.children)
                exported_default = assigned or any(c.type == 'default' for c in top.children)
                inner = [c for c in top.children if c.is_named and c.type not in ('comment', 'decorator')]
                node = inner[0] if inner else top
                if assigned and node.type == 'identifier':
                    self.cjs_export = self.cjs_export or self.text(node)
                if exported_default and node.type == 'identifier':
                    self.default = ('name', self.text(node))
                    continue
                if exported_default and node.type == 'object':
                    # `export default { isArray, isString: check }`: `utils.isArray()` sobre la importación por defecto
                    for part in node.named_children:
                        value = part.child_by_field_name('value') if part.type == 'pair' else part
                        key = part.child_by_field_name('key') if part.type == 'pair' else part
                        if part.type in ('pair', 'shorthand_property_identifier') and value is not None and \
                                value.type in ('identifier', 'shorthand_property_identifier') and key is not None:
                            self.default_members[self.text(key).strip('\'"')] = self.text(value)
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
        if kind in ('function_declaration', 'generator_function_declaration', 'function_signature') and name is not None:
            sid = self.table().get(self.text(name))
            if sid and sid.startswith('f:') and self.g.nodes[sid]['file'] == self.rel:
                self.stretch(sid, node)
                self.bodies.append((sid, node, None))
                return sid
            return self.declare_function(name, node, node.start_point[0] + 1,
                                         self.prefix() + self.head(node, self.body_start(node)).rstrip(';'), None)
        if kind == 'expression_statement' and node.named_children and node.named_children[0].type == 'internal_module':
            node, kind = node.named_children[0], 'internal_module'
        if kind in ('internal_module', 'module'):
            body = node.child_by_field_name('body')
            label = self.text(name) if name is not None and name.type in ('identifier', 'nested_identifier') else ''
            outer = self.ns
            if label and body is not None:
                self.ns = f'{outer}{label}.'
                self.namespaces.setdefault(self.ns[:-1], {})
                self.ns_bodies[body.id] = self.ns[:-1]
            self.read_block(body)
            self.ns = outer
            return None
        if kind == 'ambient_declaration':
            for inner in node.named_children:
                if inner.type == 'statement_block':
                    self.read_block(inner)
                else:
                    self.read_statement(inner)
            return None
        if kind in ('class_declaration', 'abstract_class_declaration') and name is not None:
            return self.declare_class(node, name, self.prefix())
        if kind == 'interface_declaration' and name is not None:
            return self.declare_interface(node, name)
        if kind in ('type_alias_declaration', 'enum_declaration') and name is not None:
            return self.declare_type(node, name)
        if kind in ('lexical_declaration', 'variable_declaration'):
            self.read_variables(node)
        elif kind == 'import_statement':
            self.read_import(node)
        elif kind == 'expression_statement' and self.read_commonjs(node):
            return None
        elif kind not in ('type_alias_declaration', 'ambient_declaration', 'comment'):
            self.bodies.append((self.mid, node, None))
        return None

    def read_block(self, body):
        for statement in body.named_children if body is not None else ():
            self.read_statement(declaration_of(statement))

    def read_variables(self, node):
        keyword = node.children[0].type + ' ' if node.children and not node.children[0].is_named else ''
        for d in node.children:
            if d.type != 'variable_declarator':
                continue
            value, name = d.child_by_field_name('value'), d.child_by_field_name('name')
            value = self.export_chain(value, name)
            target = self.resolve(load_spec(value, self.src))
            if target:
                self.bind(name, target, True)
                if name is not None and name.type == 'identifier':
                    self.pending.append(('require', self.text(name), self.prefix() + keyword + self.text(d), d, target, self.top_vis()))
            elif name is not None and name.type == 'identifier' and value is not None and value.type == 'class':
                self.declare_class(value, name, self.prefix() + keyword + self.head(d, value.start_byte))
            elif name is not None and name.type == 'identifier' and (
                    is_function_value(value, self.src) or is_hook_factory(self.text(name), value) or function_typed(d) or
                    self.made_by_factory(value)):
                typed = not is_function_value(value, self.src) and function_typed(d)
                sid = self.declare_function(name, d if typed or value is None else value, d.start_point[0] + 1,
                                            self.prefix() + keyword + self.head(d, d.end_byte if value is None else value.start_byte).rstrip(' =')
                                            if typed else self.value_sig(d, value, self.text(name), self.prefix() + keyword),
                                            d.end_point[0] + 1)
                call = unwrap(value)
                if not typed and call is not None and call.type == 'call_expression' and not is_hook_factory(self.text(name), value) \
                        and not self.made_by_factory(value) and not iife_returns_function(call.child_by_field_name('function'), self.src):
                    # `const m = keyValueBy(xs, x => …)`: función solo por el argumento; se confirma al enlazar
                    self.wrapped.append((sid, self.text(name), d, value, self.ns))
            else:
                if name is not None and name.type == 'identifier':
                    if not self.ns:
                        self.vars.setdefault(self.text(name), d)
                    alias = unwrap(value)
                    if alias is not None and alias.type in ('member_expression', 'identifier'):
                        obj = alias.child_by_field_name('object')
                        source = self.resolve(load_spec(obj, self.src)) if obj is not None else None
                        if source:
                            self.side(source)
                        self.pending.append(('var', self.ns, self.text(name), self.prefix() + keyword + self.text(d), d, alias,
                                             (source, self.top_vis())))
                    elif alias is not None and alias.type == 'call_expression' and \
                            alias.child_by_field_name('function') is not None and \
                            alias.child_by_field_name('function').type in ('identifier', 'member_expression'):
                        # `const debug = Debug("x")`: si la función llamada devuelve una función, la constante lo es
                        self.pending.append(('factory', self.ns, self.text(name), self.prefix() + keyword + self.text(d), d,
                                             alias, self.top_vis()))
                if value is not None:
                    self.bodies.append((self.mid, value, None))

    def export_chain(self, value, name):
        """`var color = (exports.color = function…)`: los `exports.x` / `module.exports` de la cadena exportan el nombre
        declarado, y si la cadena termina en una función, esa es su valor."""
        inner = unwrap(value)
        if inner is None or inner.type != 'assignment_expression' or name is None or name.type != 'identifier':
            return value
        while inner is not None and inner.type == 'assignment_expression':
            head = self.text(inner.child_by_field_name('left'))
            if head == 'module.exports':
                self.cjs_export = self.cjs_export or self.text(name)
                self.public.add(self.text(name))
            elif head.startswith(('exports.', 'module.exports.')) and head.count('.') == 1 + head.startswith('module.'):
                self.exports.setdefault(head.rsplit('.', 1)[1], self.text(name))
            inner = unwrap(inner.child_by_field_name('right'))
        return inner if is_function_value(inner, self.src) else value

    def made_by_factory(self, value):
        value = unwrap(value)
        fn = value.child_by_field_name('function') if value is not None and value.type == 'call_expression' else None
        sid = self.defs.get(self.text(fn)) if fn is not None and fn.type == 'identifier' else None
        return sid in self.funcs and iife_returns_function(self.funcs[sid][0], self.src)

    def read_commonjs(self, node):
        expr = node.named_children[0] if node.named_children else None
        target = self.resolve(load_spec(expr, self.src))
        if target:
            self.side(target)
            return True
        if expr is not None and expr.type == 'call_expression' and self.read_assign(expr):
            return True
        if expr is None or expr.type != 'assignment_expression':
            return False
        left, right = expr.child_by_field_name('left'), expr.child_by_field_name('right')
        while left is not None and left.type == 'identifier' and self.text(left) == 'exports' and \
                right is not None and right.type == 'assignment_expression':
            left, right = right.child_by_field_name('left'), right.child_by_field_name('right')
        self.read_cjs_exports(left, right)
        if self.read_member_function(expr, left, right):
            return True
        target = self.resolve(load_spec(right, self.src))
        if target and left is not None and self.text(left) == 'module.exports':
            self.side(target)
            if target not in self.wildcards:
                self.wildcards.append(target)
            self.default = self.default or ('module', target)
            return True
        return False

    def read_assign(self, call):
        """`Object.assign(Clase.prototype, { m() {…}, n: function () {…} })` en el nivel superior: métodos de la clase
        (mixin), igual que `Clase.prototype.m = function…`."""
        fn, args = call.child_by_field_name('function'), call.child_by_field_name('arguments')
        kids = [a for a in (args.named_children if args is not None else ()) if a.type != 'comment']
        if fn is None or self.text(fn) != 'Object.assign' or len(kids) < 2:
            return False
        found = False
        for obj in kids[1:]:
            for part in obj.named_children if obj.type == 'object' else ():
                key = part.child_by_field_name('name' if part.type == 'method_definition' else 'key')
                value = part if part.type == 'method_definition' else unwrap(part.child_by_field_name('value')) if part.type == 'pair' else None
                if key is not None and key.type == 'property_identifier' and value is not None and \
                        (value.type in FUNCTION_VALUES or value.type == 'method_definition'):
                    found = self.declare_member(part, kids[0], key, value) or found
        return found

    def read_member_function(self, expr, left, right):
        """`exports.f = function…`, `Clase.prototype.m = function…` u `obj.m = () => …` en el nivel superior: una función
        con nombre (de módulo, método del constructor o miembro de `obj`), no código suelto del módulo."""
        fn = unwrap(right)
        prop = left.child_by_field_name('property') if left is not None and left.type == 'member_expression' else None
        if prop is None or prop.type != 'property_identifier' or fn is None or fn.type not in FUNCTION_VALUES:
            return False
        return self.declare_member(expr, left.child_by_field_name('object'), prop, fn)

    def declare_member(self, expr, holder, prop, fn):
        owner, name = self.text(holder), self.text(prop)
        base = owner[:-len('.prototype')] if owner.endswith('.prototype') else owner
        cls = self.defs.get(base) if base != owner else None
        if owner in ('exports', 'module.exports') or self.ns:
            qual = None if self.ns else name
        elif IDENT_RE.fullmatch(base) and (cls or base == owner):
            qual = f'{base}.{name}'
        else:
            qual = None
        if not qual or f'f:{self.rel}:{qual}' in self.g.nodes:
            return False
        sid = self.symbol(f'f:{self.rel}:{qual}', 'method' if cls else 'function', qual, expr, expr.start_point[0] + 1,
                          self.value_sig(expr, fn, qual, ''), vis='public' if qual == name else None, doc=self.doc)
        self.g.edge(cls or self.mid, sid, 'contains')
        if qual in (name, 'module.exports'):
            self.member_fns.add(sid)
        if qual == name:
            self.defs.setdefault(name, sid)
        elif cls:
            self.classes.setdefault(cls, {}).setdefault(name, sid)
        else:
            self.namespaces.setdefault(base, {}).setdefault(name, sid)
        self.bodies.append((sid, fn, cls))
        self.funcs[sid] = (fn, cls)
        return True

    def read_cjs_exports(self, left, right):
        head = self.text(left) if left is not None and left.type == 'member_expression' else ''
        if right is None or not (head == 'module.exports' or head.startswith(('exports.', 'module.exports.'))):
            return
        if right.type == 'identifier':
            self.public.add(self.text(right))
            if head == 'module.exports':
                self.cjs_export = self.text(right)
            elif head.count('.') == 1 + head.startswith('module.'):
                self.exports.setdefault(head.rsplit('.', 1)[1], self.text(right))
        elif right.type == 'object' and head == 'module.exports':
            for part in right.named_children:
                value = part.child_by_field_name('value') if part.type == 'pair' else part
                if value is not None and value.type in ('identifier', 'shorthand_property_identifier'):
                    self.public.add(self.text(value))
                    key = part.child_by_field_name('key') if part.type == 'pair' else None
                    if key is not None and key.type in ('property_identifier', 'string'):
                        # `module.exports = { exist: checkExistence }`: `require('./m').exist` es `checkExistence`
                        self.exports.setdefault(self.text(key).strip('\'"'), self.text(value))

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
            self.loads_at[call.start_byte] = target
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
        self.funcs = {sid: (t,) + spec for t in modules.values() for sid, spec in t.funcs.items()}
        self.getters = {sid: True for t in modules.values() for sid, (node, _) in t.funcs.items() if is_getter(node)}
        self.scopes = {}
        self.return_cache = {}
        self.field_cache = {}
        self.alias_of = {}
        self.this_cache = {}
        self.assigned_cache = {}
        self.member_fns = {sid for t in modules.values() for sid in t.member_fns}
        self.cjs_owners = {t.defs[t.cjs_export]: t.rel for t in modules.values() if t.cjs_export in t.defs}
        self.anon = {}
        self.unions = {}
        self.also = {}

    def union(self, found):
        """Tipo de una unión de varios tipos del proyecto (`ProxyState | MapState`): TypeScript resuelve un miembro en cada
        uno de ellos (scip-typescript emite una ocurrencia por declaración), así que se buscan en todos."""
        found = sorted(found)
        if len(found) == 1:
            return found[0]
        key = '|' + '|'.join(found)
        self.unions[key] = tuple(found)
        return key

    def find(self, target, name, depth, seen):
        t = self.modules.get(target)
        if t is None or depth > MAX_HOPS or (target, name) in seen:
            return None
        seen.add((target, name))
        if name == '*':
            return (self.local(t, t.cjs_export, depth, seen) or t.mid) if t.cjs_export else t.mid
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

    def value_home(self, target, name, depth=0, seen=None):
        """Módulo que declara la constante o variable exportada `name` (`export const DRAFT_STATE = …`), siguiendo las
        reexportaciones (`export * from './env'`) como hace el compilador."""
        t, seen = self.modules.get(target), seen if seen is not None else set()
        if t is None or depth > MAX_HOPS or (target, name) in seen:
            return None
        seen.add((target, name))
        local = t.exports.get(name, name)
        if local in t.vars:
            return target
        if local in t.imports:
            return self.value_home(*t.imports[local], depth + 1, seen)
        if name in t.reexports:
            return self.value_home(*t.reexports[name], depth + 1, seen)
        if name in t.defs or name in t.foreign:
            return None
        for wildcard in t.wildcards:
            found = self.value_home(wildcard, name, depth + 1, seen)
            if found:
                return found
        return None

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

    def lineage(self, cid):
        if cid in self.unions:
            return list(dict.fromkeys(c for part in self.unions[cid] for c in self.lineage(part)))
        out, todo = [], [cid]
        while todo and len(out) <= MAX_BASES:
            c = todo.pop(0)
            if c and c not in out:
                out.append(c)
                todo += self.parents.get(c, [])
        return out

    def scope_names(self, t, node):
        key = (t.rel, node.id)
        if key in self.scopes:
            return self.scopes[key]
        out = self.scopes[key] = {}
        if node.type in FUNCTION_SCOPES:
            single = node.child_by_field_name('parameter')
            params = node.child_by_field_name('parameters')
            context = None
            for i, p in enumerate(([single] if single is not None else []) + (params.named_children if params is not None else [])):
                typed = p.type in ('required_parameter', 'optional_parameter')
                pattern = p.child_by_field_name('pattern') if typed else p
                annotation = p.child_by_field_name('type') if typed else None
                if annotation is None:
                    context = self.contextual(t, node) if context is None else context
                    if context and context[0] == ELEM:
                        annotation = context[1:3] if i == context[3] else None
                    else:
                        annotation = context_param(*context, i) if context else None
                self.add_pattern(t, out, pattern, annotation, None)
                if pattern is not None and pattern.type == 'this':
                    out.pop('this', None)
        elif node.type == 'for_in_statement':
            self.add_pattern(t, out, node.child_by_field_name('left'), None, None)
        elif node.type == 'catch_clause':
            self.add_pattern(t, out, node.child_by_field_name('parameter'), None, None)
        else:
            for c in node.named_children:
                if c.type == 'export_statement':
                    c = next((x for x in c.named_children if x.type not in ('comment', 'decorator')), c)
                if c.type in ('lexical_declaration', 'variable_declaration'):
                    for d in c.named_children:
                        if d.type == 'variable_declarator' and not load_spec(d.child_by_field_name('value'), t.src):
                            self.add_pattern(t, out, d.child_by_field_name('name'), d.child_by_field_name('type'),
                                             d.child_by_field_name('value'))
                elif c.type in DECLARED and c.child_by_field_name('name') is not None:
                    out.setdefault(t.text(c.child_by_field_name('name')), []).append((c.start_byte, None, None, DEF))
        return out

    def add_pattern(self, t, out, pattern, annotation, value, prop=None):
        if pattern is None:
            return
        if pattern.type in ('identifier', 'shorthand_property_identifier_pattern'):
            out.setdefault(t.text(pattern), []).append((pattern.start_byte, annotation, value, prop))
        elif prop == DEF:
            for part in pattern.named_children:
                self.add_pattern(t, out, part, None, None, DEF)
        elif pattern.type == 'assignment_pattern':
            self.add_pattern(t, out, pattern.child_by_field_name('left'), annotation, value, prop)
        elif pattern.type == 'object_pattern':
            for part in pattern.named_children:
                if part.type == 'shorthand_property_identifier_pattern':
                    self.add_pattern(t, out, part, annotation, value, (prop or ()) + (t.text(part),))
                elif part.type == 'object_assignment_pattern':
                    left = part.child_by_field_name('left')
                    self.add_pattern(t, out, left, annotation, value, (prop or ()) + (t.text(left),) if left is not None else None)
                elif part.type == 'pair_pattern':
                    key = part.child_by_field_name('key')
                    self.add_pattern(t, out, part.child_by_field_name('value'), annotation, value,
                                     (prop or ()) + (t.text(key).strip('\'"'),) if key is not None else None)
                else:
                    self.add_pattern(t, out, part, None, None, DEF)
        else:
            for part in pattern.named_children:
                self.add_pattern(t, out, part, None, None, DEF)

    def this_param(self, t, node):
        """Tipo anotado del parámetro `this` de la función que rodea a `node` (`function f(this: Hexo)`), o None."""
        fn = node.parent
        while fn is not None and fn.type not in THIS_HOLDERS:
            fn = fn.parent
        if fn is None or fn.type in ('method_definition', 'class_body'):
            return None
        key = (t.rel, fn.id)
        if key not in self.this_cache:
            params = fn.child_by_field_name('parameters')
            first = next((p for p in params.named_children if p.type != 'comment'), None) if params is not None else None
            pattern = first.child_by_field_name('pattern') if first is not None and first.type == 'required_parameter' else None
            self.this_cache[key] = self.annotation_type(t, first.child_by_field_name('type'), None) \
                if pattern is not None and pattern.type == 'this' else None
        return self.this_cache[key]

    def binding(self, t, ident):
        name, pos, node = t.text(ident), ident.start_byte, ident.parent
        while node is not None:
            if node.type in SCOPE_NODES:
                entries = self.scope_names(t, node).get(name)
                if entries:
                    prior = [e for e in entries if e[0] <= pos]
                    return node, prior[-1] if prior else entries[0]
            node = node.parent
        return None, None

    def local_value(self, t, ident):
        scope, entry = self.binding(t, ident)
        if scope is None or scope.type == 'program' or scope.id in t.ns_bodies:
            return False
        return True

    def ident_target(self, t, ident):
        """Destino de un nombre suelto: lo declarado en el `namespace` que lo rodea, o en el módulo y sus imports."""
        scope, _ = self.binding(t, ident)
        if scope is not None and scope.id in t.ns_bodies:
            return t.namespaces[t.ns_bodies[scope.id]].get(t.text(ident))
        if scope is not None and scope.type != 'program':
            return None
        return self.name_target(t, t.text(ident))

    def namespace_ref(self, t, ident):
        """Miembros del `namespace` que nombra `ident` (propio, anidado o importado), o None."""
        name = t.text(ident)
        scope, _ = self.binding(t, ident)
        if scope is not None and scope.id in t.ns_bodies:
            return t.namespaces.get(f'{t.ns_bodies[scope.id]}.{name}')
        if scope is not None and scope.type != 'program':
            return None
        if name in t.namespaces:
            return t.namespaces[name]
        return self.ns_export(*t.imports[name], 0) if name in t.imports else None

    def ns_export(self, target, name, depth):
        m = self.modules.get(target)
        if m is None or name == '*' or depth > MAX_HOPS:
            return None
        local = m.exports.get(name, name)
        if local in m.namespaces:
            return m.namespaces[local]
        for origin in (m.imports.get(local), m.reexports.get(name)):
            found = self.ns_export(*origin, depth + 1) if origin else None
            if found is not None:
                return found
        for wildcard in m.wildcards:
            found = self.ns_export(wildcard, name, depth + 1)
            if found is not None:
                return found
        return None

    def contextual(self, t, fn):
        parent, child = fn.parent, fn
        while parent is not None and parent.type in WRAPPERS:
            parent, child = parent.parent, parent
        if parent is None:
            return ()
        if parent.type == 'variable_declarator' or parent.type in FIELD_MEMBERS:
            return self.function_shape(t, parent.child_by_field_name('type'), 0)
        if parent.type == 'pair' and parent.child_by_field_name('value') == child or fn.type == 'method_definition' and parent.type == 'object':
            holder = parent if parent.type == 'pair' else fn
            key = holder.child_by_field_name('key' if holder.type == 'pair' else 'name')
            cid = self.object_type(t, holder.parent, 0) if key is not None else None
            return self.member_shape(cid, t.text(key).strip('\'"')) if cid else ()
        if parent.type == 'arguments' and parent.parent is not None and parent.parent.type == 'call_expression':
            index = next((i for i, a in enumerate(parent.named_children) if a == child), None)
            fn = parent.parent.child_by_field_name('function')
            spec = self.funcs.get(self.call_target(t, parent.parent, None))
            if index is None:
                return ()
            if spec:
                return self.callable_shape(spec[0], function_params(spec[1]), index)
            if fn is not None and fn.type == 'member_expression':
                method = t.text(fn.child_by_field_name('property'))
                elem = self.element_annotation(t, fn.child_by_field_name('object')) if method in ITERATING and index == 0 else None
                if elem:
                    return (ELEM,) + elem + (1 if method in ('reduce', 'reduceRight') else 0,)
                hit = self.field_of(self.expr_type(t, fn.child_by_field_name('object'), None), method)
                return self.callable_shape(hit[0], hit[1], index) if hit else ()
            return ()
        if parent.type == 'return_statement' or parent.type in FUNCTION_VALUES and parent.child_by_field_name('body') == child:
            holder = parent if parent.type in FUNCTION_VALUES else parent.parent
            while holder is not None and holder.type not in FUNCTION_SCOPES:
                holder = holder.parent
            return self.function_shape(t, holder.child_by_field_name('return_type'), 0) if holder is not None else ()
        return ()

    def element_annotation(self, t, obj):
        """(módulo, tipo del elemento) de una colección anotada (`xs: T[]`, `Array<T>`, `Set<T>`, `this.xs`)."""
        if obj is None:
            return None
        if obj.type == 'identifier':
            scope, entry = self.binding(t, obj)
            annotation = entry[1] if scope is not None and entry[3] is None else None
            home, node = annotation if isinstance(annotation, tuple) else (t, annotation)
        elif obj.type == 'member_expression' and obj.child_by_field_name('object').type == 'this':
            cls = next((c for _, body, c in t.bodies if c and body.start_byte <= obj.start_byte < body.end_byte), None)
            hit = self.field_of(cls, t.text(obj.child_by_field_name('property'))) if cls else None
            home, node = hit if hit else (t, None)
        else:
            return None
        while node is not None and node.type in ('type_annotation', 'parenthesized_type', 'readonly_type') and node.named_children:
            node = node.named_children[-1]
        if node is not None and node.type == 'array_type' and node.named_children:
            return home, node.named_children[0]
        if node is not None and node.type == 'generic_type' and home.text(node.child_by_field_name('name')) in COLLECTIONS:
            args = node.child_by_field_name('type_arguments')
            return (home, args.named_children[0]) if args is not None and args.named_children else None
        return None

    def object_type(self, t, obj, depth, strict=False):
        """Tipo esperado de un objeto literal: el del parámetro al que se pasa, el de la propiedad de otro objeto literal
        tipado o la anotación de la variable que lo recibe."""
        parent, child = obj.parent, obj
        while parent is not None and parent.type in WRAPPERS:
            parent, child = parent.parent, parent
        if parent is None or depth > MAX_INFER:
            return None
        if parent.type == 'arguments' and parent.parent is not None and parent.parent.type == 'call_expression':
            index = next((i for i, a in enumerate(parent.named_children) if a == child), None)
            spec = self.funcs.get(self.call_target(t, parent.parent, None))
            params = function_params(spec[1]) if spec and index is not None else None
            found = context_param(spec[0], params, index) if params is not None else None
            return self.annotation_type(found[0], found[1], None, strict=strict) if found else None
        if parent.type == 'pair' and parent.child_by_field_name('value') == child:
            outer = self.object_type(t, parent.parent, depth + 1, strict)
            key = parent.child_by_field_name('key')
            return self.member_type(outer, t.text(key).strip('\'"'), depth + 1, strict) if outer and key is not None else None
        if parent.type == 'variable_declarator':
            return self.annotation_type(t, parent.child_by_field_name('type'), None, strict=strict)
        return None

    def member_shape(self, cid, name):
        """Parámetros de la función que espera la propiedad o el método `name` de `cid`."""
        for c in self.lineage(cid):
            hit = self.fields(c).get(name)
            if hit and hit[1] is not None:
                return self.function_shape(hit[0], hit[1], 0)
            spec = self.funcs.get(self.methods.get(c, {}).get(name))
            params = function_params(spec[1]) if spec else None
            if params is not None:
                return spec[0], params
        return ()

    def field_of(self, cid, name):
        for c in self.lineage(cid) if cid else ():
            hit = self.fields(c).get(name)
            if hit and hit[1] is not None:
                return hit[0], hit[1]
        return None

    def callable_shape(self, t, node, index, depth=0):
        if node is None or depth > MAX_INFER:
            return ()
        if node.type in ('type_annotation', 'parenthesized_type') and node.named_children:
            return self.callable_shape(t, node.named_children[-1], index, depth + 1)
        if node.type in ('formal_parameters', 'function_type', 'call_signature'):
            params = node if node.type == 'formal_parameters' else node.child_by_field_name('parameters')
            found = context_param(t, params, index) if params is not None else None
            return self.function_shape(found[0], found[1], depth + 1) if found else ()
        if node.type == 'generic_type':
            node = node.child_by_field_name('name')
        cid = self.ref_target(t, node) if node is not None and node.type in ('type_identifier', 'nested_type_identifier') else None
        home = self.modules.get(self.g.nodes[cid]['file']) if cid else None
        if home is None:
            return ()
        if cid in home.aliases:
            return self.callable_shape(home, home.aliases[cid], index, depth + 1)
        body = home.shapes.get(cid)
        for member in body.named_children if body is not None else ():
            if member.type == 'call_signature':
                found = self.callable_shape(home, member, index, depth + 1)
                if found:
                    return found
        return ()

    def function_shape(self, t, node, depth):
        if node is None or depth > MAX_INFER:
            return ()
        if node.type in ('type_annotation', 'parenthesized_type') and node.named_children:
            return self.function_shape(t, node.named_children[-1], depth + 1)
        if node.type == 'union_type':
            return next((s for s in (self.function_shape(t, part, depth + 1) for part in node.named_children) if s), ())
        if node.type == 'function_type':
            params = node.child_by_field_name('parameters')
            return (t, params) if params is not None else ()
        if node.type == 'generic_type':
            node = node.child_by_field_name('name')
        if node is None or node.type not in ('type_identifier', 'nested_type_identifier'):
            return ()
        cid = self.ref_target(t, node)
        home = self.modules.get(self.g.nodes[cid]['file']) if cid else None
        if home is None or cid not in home.aliases:
            return ()
        return self.function_shape(home, home.aliases[cid], depth + 1)

    def entry_type(self, t, entry, cls, depth):
        _, annotation, value, prop = entry
        if prop == DEF:
            return None
        if isinstance(annotation, tuple):
            found = self.annotation_type(annotation[0], annotation[1], None, depth + 1)
        elif annotation is not None:
            found = self.annotation_type(t, annotation, cls, depth + 1)
        else:
            found = self.expr_type(t, value, cls, depth + 1) if value is not None else None
        for name in prop or ():
            found = self.member_type(found, name, depth + 1)
        return found

    def ident_type(self, t, ident, cls, depth):
        scope, entry = self.binding(t, ident)
        name = t.text(ident)
        if scope is not None and scope.id in t.ns_bodies and entry[3] == DEF:
            target = t.namespaces[t.ns_bodies[scope.id]].get(name)
            return target if target and self.g.nodes[target]['kind'] == 'class' else None
        if scope is not None and entry[3] != DEF and (scope.type != 'program' or name not in t.defs):
            if entry[1] is None and entry[2] is None and entry[3] is None and scope.type not in FUNCTION_SCOPES:
                return self.assigned_type(t, scope, name, cls if scope.type != 'program' else None, depth)
            return self.entry_type(t, entry, cls if scope.type != 'program' else None, depth)
        if scope is None and name in t.imports:
            origin = self.var_origin(*t.imports[name], depth)
            if origin:
                return origin
        target = self.strict_target(t, name)
        return target if target and self.g.nodes[target]['kind'] == 'class' else None

    def var_origin(self, target, name, depth):
        m = self.modules.get(target)
        if m is None or depth > MAX_INFER:
            return None
        if name == 'default' and m.default and m.default[0] == 'name':
            name = m.default[1]
        name = m.exports.get(name, name)
        if name in m.vars:
            d = m.vars[name]
            return self.entry_type(m, (d.start_byte, d.child_by_field_name('type'), d.child_by_field_name('value'), None), None, depth + 1)
        if name in m.imports:
            return self.var_origin(*m.imports[name], depth + 1)
        if name in m.reexports:
            return self.var_origin(*m.reexports[name], depth + 1)
        return None

    def annotation_type(self, t, node, cls, depth=0, strict=False):
        if node is None or depth > MAX_INFER:
            return None
        if node.type in ('type_annotation', 'parenthesized_type', 'readonly_type') and node.named_children:
            return self.annotation_type(t, node.named_children[-1], cls, depth + 1, strict)
        if node.type == 'this_type':
            return cls
        if node.type == 'generic_type':
            name, args = node.child_by_field_name('name'), node.child_by_field_name('type_arguments')
            if strict and name is not None and t.text(name) in MAPPED_TYPES:
                return None
            if name is not None and t.text(name) in TRANSPARENT and args is not None and args.named_children:
                return self.annotation_type(t, args.named_children[0], cls, depth + 1)
            return self.annotation_type(t, name, cls, depth + 1)
        if node.type in ('union_type', 'intersection_type'):
            if strict and node.type == 'union_type' and \
                    sum(1 for p in node.named_children if not (p.type in ('predefined_type', 'literal_type') and p.text in NULLISH)) > 1:
                return None
            found = {self.annotation_type(t, part, cls, depth + 1) for part in node.named_children}
            found.discard(None)
            if node.type == 'union_type' and len(found) > 1:
                return self.union({p for f in found for p in self.unions.get(f, (f,))})
            return found.pop() if len(found) == 1 else None
        if node.type in ('type_identifier', 'identifier', 'nested_type_identifier'):
            return self.shape(self.ref_target(t, node), depth + 1)
        if node.type == 'object_type':
            key = f'{{}}{t.rel}:{node.start_byte}'
            self.anon.setdefault(key, (t, node))
            return key
        return None

    def shape(self, cid, depth):
        if not cid or depth > MAX_INFER or self.g.nodes[cid]['kind'] != 'class':
            return None
        t = self.modules.get(self.g.nodes[cid]['file'])
        if t is not None and cid in t.aliases and cid not in t.shapes:
            return self.annotation_type(t, t.aliases[cid], None, depth + 1)
        return cid

    def expr_type(self, t, node, cls, depth=0):
        if node is None or depth > MAX_INFER:
            return None
        kind = node.type
        if kind in ('as_expression', 'satisfies_expression') and len(node.named_children) > 1:
            if kind == 'as_expression':
                return self.annotation_type(t, node.named_children[-1], cls, depth + 1)
            return self.expr_type(t, node.named_children[0], cls, depth + 1)
        if kind in ('parenthesized_expression', 'non_null_expression', 'await_expression') and node.named_children:
            return self.expr_type(t, node.named_children[0], cls, depth + 1)
        if kind == 'this':
            return self.this_param(t, node) or cls
        if kind == 'identifier':
            return self.ident_type(t, node, cls, depth + 1)
        if kind == 'new_expression':
            target = self.call_target(t, node, cls, depth + 1)
            return target if target and (self.g.nodes[target]['kind'] == 'class' or target in self.methods) else None
        if kind == 'call_expression':
            target = self.call_target(t, node, cls, depth + 1)
            return self.returns(target, depth + 1) or self.generic_return(t, node, target, cls, depth + 1)
        if kind == 'member_expression':
            prop = node.child_by_field_name('property')
            base = self.expr_type(t, node.child_by_field_name('object'), cls, depth + 1)
            return self.member_type(base, t.text(prop), depth + 1) if prop is not None else None
        if kind == 'ternary_expression':
            found = {self.expr_type(t, node.child_by_field_name(f), cls, depth + 1) for f in ('consequence', 'alternative')}
            found.discard(None)
            return found.pop() if len(found) == 1 else None
        return None

    def generic_return(self, t, call, sid, cls, depth):
        """`f<T>(x: T): T` o `get<T>(c: { new (...): T }): T`: el tipo de retorno es el parámetro de tipo que fija el
        argumento (el valor pasado o la clase que se instancia)."""
        spec = self.funcs.get(sid) if sid else None
        node = unwrap(spec[1].child_by_field_name('value')) if spec and spec[1].type in FIELD_MEMBERS else spec[1] if spec else None
        names = node.child_by_field_name('type_parameters') if node is not None else None
        ret = node.child_by_field_name('return_type') if names is not None else None
        word = spec[0].text(ret.named_children[-1]) if ret is not None and ret.named_children else ''
        if not word or word not in {spec[0].text(p.child_by_field_name('name')) for p in names.named_children if p.child_by_field_name('name')}:
            return None
        params = [p for p in function_params(node).named_children if p.type in ('required_parameter', 'optional_parameter')] \
            if function_params(node) is not None else []
        args = call.child_by_field_name('arguments')
        args = [a for a in args.named_children if a.type != 'comment'] if args is not None else []
        for p, arg in zip(params, args):
            annotation = p.child_by_field_name('type')
            spelled = spec[0].text(annotation.named_children[-1]) if annotation is not None and annotation.named_children else ''
            if spelled == word:
                return self.expr_type(t, arg, cls, depth + 1)
            if re.search(r'\bnew\s*\([^)]*\)\s*(=>|:)\s*' + re.escape(word) + r'\b', spelled) and arg.type == 'identifier':
                found = self.strict_target(t, t.text(arg))
                return found if found and self.g.nodes[found]['kind'] == 'class' else None
        return None

    def returns(self, sid, depth):
        if not sid or sid not in self.funcs or depth > MAX_INFER:
            return None
        if sid in self.alias_of:
            return self.returns(self.alias_of[sid], depth + 1)
        if sid not in self.return_cache:
            self.return_cache[sid] = None
            t, node, cls = self.funcs[sid]
            if node.type in FIELD_MEMBERS or node.type == 'property_signature':
                annotation = node.child_by_field_name('type')
                inner = annotation.named_children[-1] if annotation is not None and annotation.named_children else None
                node = unwrap(node.child_by_field_name('value')) if inner is None else inner
            if node is not None:
                ret = node.child_by_field_name('return_type')
                body = node.child_by_field_name('body')
                if ret is not None:
                    found = self.annotation_type(t, ret, cls, depth + 1)
                elif body is not None and body.type != 'statement_block' and node.type in FUNCTION_VALUES:
                    found = self.expr_type(t, body, cls, depth + 1)
                elif body is not None and body.type == 'statement_block' and not any(c.type in ('*', 'async') for c in node.children) \
                        and node.type not in ('generator_function', 'generator_function_declaration'):
                    found = self.body_returns(t, body, cls, depth)
                else:
                    found = None
                self.return_cache[sid] = found
        return self.return_cache[sid]

    def body_returns(self, t, body, cls, depth):
        """Retorno que infiere TypeScript sin anotación: el tipo de los `return` de la función, si todos coinciden."""
        found, stack, budget = set(), list(body.named_children), MAX_WALK
        while stack and budget:
            n, budget = stack.pop(), budget - 1
            if n.type in FUNCTION_SCOPES or n.type in ('class', 'class_declaration'):
                continue
            if n.type == 'return_statement':
                arg = next((c for c in n.named_children if c.type != 'comment'), None)
                if arg is not None and arg.type not in ('null', 'undefined'):
                    found.add(self.expr_type(t, arg, cls, depth + 1))
                if len(found) > 1 or None in found:
                    return None
                continue
            stack.extend(n.named_children)
        return found.pop() if found and not stack else None

    def assigned_type(self, t, scope, name, cls, depth):
        """`let pool; … pool = Pool.create()`: tipo de las asignaciones a una variable declarada sin valor, si coinciden."""
        key = (t.rel, scope.id, name)
        if key not in self.assigned_cache:
            self.assigned_cache[key] = None
            found, stack, budget = set(), [scope], MAX_WALK
            while stack and budget:
                n, budget = stack.pop(), budget - 1
                left = n.child_by_field_name('left') if n.type == 'assignment_expression' else None
                if left is not None and left.type == 'identifier' and t.text(left) == name:
                    found.add(self.expr_type(t, n.child_by_field_name('right'), cls, depth + 1))
                stack.extend(n.named_children)
            self.assigned_cache[key] = found.pop() if len(found) == 1 and not stack else None
        return self.assigned_cache[key]

    def fields(self, cid):
        if cid in self.field_cache:
            return self.field_cache[cid]
        out = self.field_cache[cid] = {}
        t, body = self.anon[cid] if cid in self.anon else (self.modules.get(self.g.nodes[cid]['file']), None)
        body = t.shapes.get(cid) if t is not None and body is None else body
        for member in body.named_children if body is not None else ():
            name = member.child_by_field_name('name') or member.child_by_field_name('property')
            if member.type in FIELD_MEMBERS + ('property_signature',) and name is not None:
                out.setdefault(t.text(name), (t, member.child_by_field_name('type'), member.child_by_field_name('value')))
            elif member.type == 'method_definition' and name is not None and t.text(name) == 'constructor':
                self.constructor_fields(t, cid, member, out)
        if t is not None and t.rel.endswith(JS_EXTS) and body is not None:
            self.method_fields(t, body, out)
        return out

    def method_fields(self, t, body, out):
        """JavaScript: TypeScript infiere los campos de una clase de las asignaciones `this.x = …` de cualquier método
        (`this.templateData = new TemplateData(…)` en un `init()`); se toman si todas crean la misma clase."""
        found = defaultdict(set)
        for member in body.named_children:
            name = member.child_by_field_name('name')
            if member.type != 'method_definition' or name is None or t.text(name) == 'constructor':
                continue
            stack, budget = [member.child_by_field_name('body')], MAX_WALK
            while stack and budget:
                n, budget = stack.pop(), budget - 1
                if n is None or n.type in FUNCTION_SCOPES or n.type in ('class', 'class_declaration'):
                    continue
                if n.type == 'assignment_expression':
                    left, right = n.child_by_field_name('left'), unwrap(n.child_by_field_name('right'))
                    if left is not None and left.type == 'member_expression' and left.child_by_field_name('object').type == 'this' \
                            and right is not None and right.type not in ('null', 'undefined') and not jsdoc_hides(t, n):
                        ctor = right.child_by_field_name('constructor') if right.type == 'new_expression' else None
                        found[t.text(left.child_by_field_name('property'))].add((t.text(ctor) if ctor is not None else None, right))
                stack.extend(n.named_children)
        for field, values in found.items():
            ctors = {c for c, _ in values}
            if len(ctors) == 1 and None not in ctors:
                out.setdefault(field, (t, None, next(iter(values))[1]))

    def constructor_fields(self, t, cid, member, out):
        params = member.child_by_field_name('parameters')
        for p in params.named_children if params is not None else ():
            pattern = p.child_by_field_name('pattern')
            if any(c.type in ('accessibility_modifier', 'readonly') for c in p.children) and pattern is not None:
                out.setdefault(t.text(pattern), (t, p.child_by_field_name('type'), None))
        body = member.child_by_field_name('body')
        for stmt in body.named_children if body is not None else ():
            expr = stmt.named_children[0] if stmt.type == 'expression_statement' and stmt.named_children else None
            left = expr.child_by_field_name('left') if expr is not None and expr.type == 'assignment_expression' else None
            if left is not None and left.type == 'member_expression' and left.child_by_field_name('object').type == 'this':
                # el constructor declara el campo (TypeScript no lo vuelve a inferir de otros métodos)
                field = t.text(left.child_by_field_name('property'))
                out.setdefault(field, (t, None, None if jsdoc_hides(t, expr) else expr.child_by_field_name('right')))

    def member_type(self, cid, name, depth, strict=False):
        if not cid or depth > MAX_INFER:
            return None
        if cid in self.unions:
            found = {self.member_type(part, name, depth + 1, strict) for part in self.unions[cid]}
            found.discard(None)
            return self.union({p for f in found for p in self.unions.get(f, (f,))}) if found else None
        for c in self.lineage(cid):
            hit = self.fields(c).get(name)
            if hit:
                t, annotation, value = hit
                if annotation is not None:
                    return self.annotation_type(t, annotation, c, depth + 1, strict)
                return self.expr_type(t, value, c, depth + 1) if value is not None else None
            method = self.methods.get(c, {}).get(name)
            if method:
                return self.returns(method, depth + 1) if self.getters.get(method) else None
        return None

    def member_target(self, t, fn, cls, depth=0):
        obj, prop = fn.child_by_field_name('object'), fn.child_by_field_name('property')
        if obj is None or prop is None:
            return None
        name = t.text(prop)
        if obj.type == 'this':
            return self.method_of(self.this_param(t, obj) or cls, name)
        if obj.type == 'super':
            return self.inherited(cls, name) if cls else None
        if obj.type == 'identifier' and not self.local_value(t, obj):
            members = self.namespace_ref(t, obj)
            if members is not None and members.get(name):
                return members[name]
            source = t.imports.get(t.text(obj))
            home = self.modules.get(source[0]) if source and source[1] == 'default' else None
            if home is not None and name in home.default_members:
                return self.name_target(home, home.default_members[name])
            owner = self.strict_target(t, t.text(obj))
            if owner and owner.startswith('m:'):
                return self.resolve_import(owner[2:], name)
            if owner in self.methods and self.method_of(owner, name):
                return self.method_of(owner, name)
            home = self.cjs_owners.get(owner)
            if home and (name in self.modules[home].exports or f'f:{home}:{name}' in self.member_fns):
                return self.exported(home, name) or None
            if owner in self.methods:
                return None
        source = t.loads_at.get(obj.start_byte) if obj.type == 'call_expression' else None
        if source:  # `require('./errors').deprecate(…)`: la función exportada
            return self.exported(source, name) or None
        base = self.expr_type(t, obj, cls, depth + 1)
        if base in self.unions:
            found = list(dict.fromkeys(m for m in (self.method_of(part, name) for part in self.unions[base]) if m))
            if len(found) > 1:
                self.also[(t.rel, fn.start_byte)] = found[1:]
            return found[0] if found else None
        return self.method_of(base, name)

    def call_target(self, t, n, cls, depth=0):
        if n.type == 'call_expression':
            fn = n.child_by_field_name('function')
            if fn is not None and fn.type == 'identifier':
                return self.ident_target(t, fn)
            if fn is not None and fn.type == 'member_expression':
                return self.member_target(t, fn, cls, depth)
            if fn is not None and fn.type == 'super':
                return next(iter(self.parents.get(cls, ())), None) if cls else None
            return None
        if n.type == 'new_expression':
            ctor = n.child_by_field_name('constructor')
            if ctor is not None and ctor.type == 'identifier':
                return self.ident_target(t, ctor)
            if ctor is not None and ctor.type == 'member_expression':
                return self.member_target(t, ctor, cls, depth)
            return None
        if n.type in ('jsx_opening_element', 'jsx_self_closing_element'):
            tag = n.child_by_field_name('name')
            if tag is not None and tag.type == 'identifier':
                return self.ident_target(t, tag)
            return None
        return None

    def declare_aliases(self, t):
        """`const f = Clase.crear`, `const g = require('./m').g`, `min = this.gte`: otro nombre para una función del
        proyecto. Se declaran como función (o método) que remite a la original, igual que hace el compilador."""
        for kind, *rest in t.pending:
            if kind == 'require':
                name, sig, d, source, vis = rest
                target, value = f'f:{source}:module.exports', d.child_by_field_name('value')
                if name in t.defs or not self.is_function(target) or target not in self.member_fns:
                    continue
                sid = t.symbol(f'f:{t.rel}:{name}', 'function', name, d, d.start_point[0] + 1, sig, d.end_point[0] + 1, vis=vis)
                self.g.edge(t.mid, sid, 'contains')
            elif kind == 'factory':
                ns, name, sig, d, value, vis = rest
                table = t.namespaces[ns[:-1]] if ns else t.defs
                target = self.alias_target(t, value.child_by_field_name('function'), None)
                if name in table or not self.is_function(target) or not self.makes_function(target):
                    continue
                sid = table[name] = t.symbol(f'f:{t.rel}:{ns}{name}', 'function', ns + name, d, d.start_point[0] + 1, sig,
                                             d.end_point[0] + 1, vis=vis)
                self.g.edge(t.mid, sid, 'contains')
                self.funcs[sid] = (t, d, None)
                # la llamada que la fabrica pertenece a la constante, como el cuerpo de `const f = () => …`
                held = d.child_by_field_name('value')
                t.bodies = [(sid, body, cls) if body == held and owner == t.mid else (owner, body, cls) for owner, body, cls in t.bodies]
                continue
            elif kind == 'var':
                ns, name, sig, d, value, (source, vis) = rest
                prop = t.text(value.child_by_field_name('property')) if source else ''
                target = self.exported(source, prop) if source else self.alias_target(t, value, None)
                builtin = not target and not source and self.builtin_function(t, value)
                if not self.is_function(target) and not builtin:
                    continue
                table = t.namespaces[ns[:-1]] if ns else t.defs
                if name in table:
                    continue
                if source:
                    t.imports[name] = (source, prop)
                    if target not in self.member_fns:
                        continue
                sid = t.symbol(f'f:{t.rel}:{ns}{name}', 'function', ns + name, d, d.start_point[0] + 1, sig, d.end_point[0] + 1, vis=vis)
                if not source:
                    table[name] = sid
                self.g.edge(t.mid, sid, 'contains')
                if builtin:
                    continue
            else:
                cid, owner, name, member, value, _ = rest
                target = self.alias_target(t, value, cid)
                methods = t.classes.setdefault(cid, {})
                if not self.is_function(target) or name in methods:
                    continue
                sid = methods[name] = t.symbol(f'f:{t.rel}:{owner}.{name}', 'method', f'{owner}.{name}', member,
                                               member.start_point[0] + 1, t.text(member).rstrip(';'),
                                               vis=member_vis(member, t.src))
                self.g.edge(cid, sid, 'contains')
            self.funcs[sid] = (t, value, None)
            self.alias_of[sid] = target
            self.g.edge(sid, target, 'ref')
        self.cache.clear()

    def demote_wrapped(self, t):
        """`const m = keyValueBy(xs, x => …)`: una llamada con una función como argumento parece un envoltorio
        (`memo(…)`, `debounce(…)`), pero si la función llamada es del proyecto y declara un retorno que no es una función,
        la constante es un valor y sus llamadas son del módulo."""
        for sid, name, d, value, ns in t.wrapped:
            call = unwrap(value)
            target = self.alias_target(t, call.child_by_field_name('function'), None)
            if not self.is_function(target) or self.makes_function(target) or not self.returns_value(target):
                continue
            table = t.namespaces[ns[:-1]] if ns else t.defs
            if table.get(name) != sid:
                continue
            del table[name]
            for key in [k for k in self.g.edges if sid in k[:2]]:
                del self.g.edges[key]
            del self.g.nodes[sid]
            t.funcs.pop(sid, None)
            self.funcs.pop(sid, None)
            self.getters.pop(sid, None)
            t.bodies = [(t.mid if owner == sid else owner, body, cls) for owner, body, cls in t.bodies]
            if not ns:
                t.vars.setdefault(name, d)

    def returns_value(self, sid):
        """La función `sid` declara un tipo de retorno que seguro no es invocable (`Index<R>`, `T[]`, `Promise<X>`)."""
        spec = self.funcs.get(sid)
        node = spec[1] if spec else None
        while node is not None and node.type == 'variable_declarator':
            node = unwrap(node.child_by_field_name('value'))
        ret = node.child_by_field_name('return_type') if node is not None else None
        return ret is not None and self.value_type(spec[0], ret, 0)

    def value_type(self, t, node, depth):
        if node is None or depth > MAX_INFER:
            return False
        if node.type in ('type_annotation', 'parenthesized_type', 'readonly_type'):
            return bool(node.named_children) and self.value_type(t, node.named_children[-1], depth + 1)
        if node.type in ('union_type', 'intersection_type'):
            return all(self.value_type(t, p, depth + 1) for p in node.named_children)
        if node.type in ('array_type', 'tuple_type', 'literal_type', 'object_type', 'template_literal_type'):
            return True
        if node.type == 'predefined_type':
            return t.text(node) not in ('any', 'unknown', 'never')
        if node.type in ('generic_type', 'type_identifier', 'nested_type_identifier'):
            name = node.child_by_field_name('name') if node.type == 'generic_type' else node
            if name is not None and t.text(name) in VALUE_TYPES:
                return True
            cid = self.ref_target(t, node)
            if not cid or self.g.nodes[cid]['kind'] != 'class':
                return False
            home = self.modules.get(self.g.nodes[cid]['file'])
            if home is not None and cid in home.aliases:
                return self.value_type(home, home.aliases[cid], depth + 1)
            body = home.shapes.get(cid) if home is not None else None
            return body is not None and not any(c.type in ('call_signature', 'construct_signature') for c in body.named_children)
        return False

    def makes_function(self, sid):
        """La función `sid` devuelve una función: tipo de retorno declarado como función (`(): (...a) => void`) o un
        `return` de una función."""
        spec = self.funcs.get(sid)
        node = spec[1] if spec else None
        while node is not None and node.type == 'variable_declarator':
            node = unwrap(node.child_by_field_name('value'))
        if node is None:
            return False
        ret = node.child_by_field_name('return_type')
        inner = ret.named_children[0] if ret is not None and ret.named_children else None
        while inner is not None and inner.type == 'parenthesized_type' and inner.named_children:
            inner = inner.named_children[0]
        if inner is not None:
            return inner.type == 'function_type'
        return iife_returns_function(node, spec[0].src)

    def builtin_function(self, t, value):
        """`var abs = Math.abs`, `var toString = Object.prototype.toString`: alias de una función de la biblioteca estándar."""
        if value.type != 'member_expression':
            return False
        root = value
        while root.type == 'member_expression':
            root = root.child_by_field_name('object')
        prop = t.text(value.child_by_field_name('property'))
        name = t.text(root) if root.type == 'identifier' else ''
        held = t.vars.get(name) if root.type == 'identifier' and not self.local_value(t, root) else None
        alias = unwrap(held.child_by_field_name('value')) if held is not None else None
        if alias is not None and alias.type == 'identifier' and t.text(alias) in BUILTIN_NAMESPACES and \
                t.text(alias) not in t.vars:  # `const O = Object; export const getPrototypeOf = O.getPrototypeOf`
            name, root = t.text(alias), alias
        return name in BUILTIN_NAMESPACES and prop[:1].islower() and prop not in BUILTIN_VALUES and \
            name not in t.defs and name not in t.imports and name not in t.vars and not self.local_value(t, root)

    def alias_target(self, t, value, cls):
        if value.type == 'identifier':
            return self.ident_target(t, value)
        return self.member_target(t, value, cls)

    def is_function(self, sid):
        return bool(sid) and self.g.nodes.get(sid, {}).get('kind') in ('function', 'method')

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
                self.g.edge(sid, target, 'ref' if self.g.nodes[target].get('kind') == 'module' else 'call')
                fn = n.child_by_field_name('function') if n.type == 'call_expression' else None
                for other in self.also.get((t.rel, fn.start_byte), ()) if fn is not None else ():
                    if other != sid:
                        self.g.edge(sid, other, 'call')
            elif not target and n.type == 'call_expression':
                owner = self.field_owner(t, n.child_by_field_name('function'), cls)
                if owner and self.g.nodes[owner]['file'] != t.rel:
                    self.g.edge(sid, owner, 'ref')
        found = QueryCursor(t.reads).captures(t.tree_root)
        for n in found.get('obj', []) + found.get('pattern', []):
            at = bisect_right(starts, n.start_byte) - 1
            if at < 0 or n.end_byte > bodies[at][1].end_byte:
                continue
            sid, _, cls = bodies[at]
            for owner in self.key_owners(t, n, cls):
                if self.g.nodes[owner]['file'] != t.rel:
                    self.g.edge(sid, owner, 'ref')
        for n in found.get('read', []):
            parent = n.parent
            if parent is not None and parent.type == 'call_expression' and parent.child_by_field_name('function') == n:
                continue
            at = bisect_right(starts, n.start_byte) - 1
            if at < 0 or n.end_byte > bodies[at][1].end_byte or \
                    n.child_by_field_name('object').type == 'this' and not self.this_param(t, n):
                continue
            sid, _, cls = bodies[at]
            for owner in self.member_owners(t, n, cls):
                if self.g.nodes[owner]['file'] != t.rel:
                    self.g.edge(sid, owner, 'ref')

    def key_owners(self, t, node, cls):
        """Clases o interfaces del proyecto que declaran las claves de un objeto literal tipado por contexto
        (`render({ path })` con `path` de `StoreFunctionData`) o las propiedades que desestructura `const { a } = x`."""
        if node.type == 'object':
            parent = node.parent
            while parent is not None and parent.type in WRAPPERS:
                parent = parent.parent
            if parent is None or parent.type not in ('arguments', 'pair', 'variable_declarator'):
                return ()
            base = self.object_type(t, node, 0, strict=True)
            keys = [part.child_by_field_name('key' if part.type == 'pair' else 'name') if part.type != 'shorthand_property_identifier'
                    else part for part in node.named_children if part.type in ('pair', 'method_definition', 'shorthand_property_identifier')]
        else:
            base = self.expr_type(t, node.child_by_field_name('value'), cls)
            keys = [part.child_by_field_name('key') if part.type == 'pair_pattern' else part.child_by_field_name('left')
                    if part.type == 'object_assignment_pattern' else part for part in node.child_by_field_name('name').named_children]
        if not base:
            return ()
        out = set()
        for key in keys:
            name = t.text(key).strip('\'"') if key is not None else ''
            for part in self.unions.get(base, (base,)) if name else ():
                owner = next((c for c in self.lineage(part) if c not in self.anon and (name in self.fields(c) or name in self.methods.get(c, {}))),
                             None)
                if owner:
                    out.add(owner)
        return out

    def member_owners(self, t, node, cls):
        """Clases o interfaces del proyecto que declaran la propiedad que lee `obj.prop` (una por tipo de una unión)."""
        obj, prop = node.child_by_field_name('object'), node.child_by_field_name('property')
        if obj is None or prop is None or obj.type not in ('identifier', 'member_expression', 'call_expression', 'non_null_expression',
                                                              'parenthesized_expression', 'as_expression'):
            return ()
        base = self.expr_type(t, obj, cls)
        name = t.text(prop)
        out = set()
        for part in self.unions.get(base, (base,)) if base else ():
            owner = next((c for c in self.lineage(part) if c not in self.anon and (name in self.fields(c) or name in self.methods.get(c, {}))),
                         None)
            if owner:
                out.add(owner)
        return out

    def field_owner(self, t, fn, cls):
        if fn is None or fn.type != 'member_expression':
            return None
        obj, prop = fn.child_by_field_name('object'), fn.child_by_field_name('property')
        base = (self.this_param(t, obj) or cls) if obj.type == 'this' else self.expr_type(t, obj, cls)
        name = t.text(prop) if prop is not None else ''
        return next((c for c in self.lineage(base) if c not in self.anon and name in self.fields(c)), None) if base else None


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
        project.demote_wrapped(t)
    for t in modules.values():
        project.declare_aliases(t)
    for t in modules.values():
        for target, name in list(t.imports.values()) + list(t.reexports.values()):
            g.edge(t.mid, f'm:{target}', 'import')
            found = project.exported(target, name) if name != '*' else None
            origin = g.nodes[found]['file'] if found else project.value_home(target, name) if name not in ('*', 'default') else None
            if origin and origin not in (t.rel, target):
                g.edge(t.mid, f'm:{origin}', 'import')
        project.link_calls(t)
