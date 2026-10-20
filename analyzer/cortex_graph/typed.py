"""Tipos estáticos declarados para resolver receptores en Java y Kotlin.

Ambos lenguajes declaran (o dejan inferir de forma local) el tipo de cada
variable, parámetro, campo/propiedad y retorno. Con esas anotaciones, `var x =
new T()` / `val x = T()` y el tipo esperado de las lambdas se sabe a qué clase
pertenece `obj.m()`: si la clase es del proyecto se busca `m` en ella, en sus
bases y en sus funciones de extensión; si es externa (JDK, stdlib o una
dependencia) la llamada no apunta al proyecto.
"""
import re
from collections import defaultdict

from .langs import add, decl_line, parser_for, text

UNKNOWN = None
MAX_DEPTH = 12

JAVA_CLASSES = {'class_declaration', 'interface_declaration', 'enum_declaration', 'record_declaration',
                'annotation_type_declaration'}
JAVA_BODIES = {'class_body', 'interface_body', 'enum_body', 'enum_body_declarations', 'annotation_type_body'}
JAVA_FIELDS = {'field_declaration', 'constant_declaration'}
JAVA_CALLABLES = {'method_declaration', 'constructor_declaration', 'compact_constructor_declaration', 'lambda_expression'}
JAVA_BLOCKS = {'block', 'constructor_body', 'switch_block_statement_group', 'switch_rule'}
JAVA_PRIMITIVES = {'integral_type', 'floating_point_type', 'boolean_type', 'void_type'}
JAVA_LITERALS = {'string_literal': 'String', 'text_block': 'String', 'character_literal': 'char',
                 'decimal_integer_literal': 'int', 'true': 'boolean', 'false': 'boolean'}

KT_CLASSES = {'class_declaration', 'object_declaration', 'companion_object'}
KT_TYPES = {'user_type', 'nullable_type', 'function_type', 'parenthesized_type', 'non_nullable_type',
            'definitely_non_nullable_type'}
KT_STATEMENTS = {'block', 'statements', 'source_file', 'lambda_literal', 'control_structure_body', 'function_body'}
KT_LITERALS = {'string_literal': 'String', 'number_literal': 'Int', 'boolean_literal': 'Boolean',
               'character_literal': 'Char', 'float_literal': 'Double'}
KT_SAME = {'let': 'it', 'also': 'it', 'takeIf': 'it', 'takeUnless': 'it', 'apply': 'this', 'run': 'this'}
KT_RETURNS_RECEIVER = {'apply', 'also', 'takeIf', 'takeUnless'}
KT_NOT_VALUES = {'variable_declaration', 'parameter', 'class_parameter', 'function_declaration', 'property_declaration',
                 'import_header', 'package_header', 'user_type', 'type_identifier', 'value_argument_label', 'lambda_parameters',
                 'call_expression'}
KT_BUILDERS = {'buildString': 'StringBuilder', 'buildList': 'MutableList', 'buildSet': 'MutableSet', 'buildMap': 'MutableMap'}
KT_TEXT = {'String', 'Regex', 'StringBuilder', 'CharSequence'}
# importados por defecto en Kotlin (`kotlin.*`, `kotlin.collections.*`): una clase homónima del proyecto que no está en el
# mismo paquete ni importada no los tapa
KT_DEFAULT_TYPES = {'Any', 'Unit', 'Nothing', 'String', 'CharSequence', 'Int', 'Long', 'Short', 'Byte', 'Double', 'Float',
                    'Boolean', 'Char', 'Number', 'Pair', 'Triple', 'Result', 'Regex', 'Array', 'List', 'MutableList', 'Set',
                    'MutableSet', 'Map', 'MutableMap', 'Collection', 'Iterable', 'Sequence', 'Comparable', 'Throwable',
                    'Exception'}
KT_ITERATING = {'forEach', 'map', 'mapNotNull', 'filter', 'filterNot', 'any', 'all', 'none', 'first', 'firstOrNull',
                'find', 'onEach', 'flatMap', 'associateBy', 'associateWith', 'associate', 'groupBy', 'sortedBy',
                'sortedByDescending', 'count', 'sumOf', 'maxByOrNull', 'minByOrNull', 'single', 'singleOrNull',
                'takeWhile', 'dropWhile', 'partition', 'last', 'lastOrNull', 'indexOfFirst', 'forEachIndexed',
                'mapIndexed', 'filterIsInstance', 'distinctBy', 'maxOf', 'minOf', 'fold', 'reduce'}
KT_ITERATING |= {'joinToString', 'mapTo', 'mapNotNullTo', 'filterTo', 'filterIndexed', 'sumBy', 'flatMapTo', 'groupingBy',
                 'associateByTo', 'maxBy', 'minBy', 'sortedWith', 'zip', 'chunked', 'windowed', 'toSortedMap'}
KT_FACTORIES = {'listOf': 'List', 'mutableListOf': 'MutableList', 'arrayListOf': 'ArrayList', 'setOf': 'Set',
                'mutableSetOf': 'MutableSet', 'hashSetOf': 'HashSet', 'linkedSetOf': 'LinkedHashSet', 'mapOf': 'Map',
                'mutableMapOf': 'MutableMap', 'hashMapOf': 'HashMap', 'linkedMapOf': 'LinkedHashMap', 'arrayOf': 'Array',
                'emptyList': 'List', 'emptySet': 'Set', 'emptyMap': 'Map', 'sequenceOf': 'Sequence', 'listOfNotNull': 'List'}
KEEP_ELEMENT = {'toList', 'toMutableList', 'toSet', 'toMutableSet', 'sorted', 'sortedBy', 'sortedByDescending', 'sortedWith',
                'filter', 'filterNot', 'filterNotNull', 'reversed', 'distinct', 'distinctBy', 'take', 'drop', 'takeLast',
                'dropLast', 'asSequence', 'asIterable', 'toTypedArray', 'shuffled', 'plus', 'minus', 'orEmpty', 'takeWhile',
                'dropWhile', 'toHashSet', 'toSortedSet', 'onEach', 'asReversed', 'subList', 'copyOf', 'filterIsInstance',
                'iterator', 'listIterator', 'stream', 'toArray'}
KT_INDEXED = {'forEachIndexed': 1, 'mapIndexed': 1, 'fold': 1, 'reduce': 1}

ELEMENT_OF = {'get', 'remove', 'next', 'previous', 'poll', 'pop', 'peek', 'element', 'first', 'last', 'getFirst',
              'getLast', 'removeFirst', 'removeLast', 'pollFirst', 'pollLast', 'peekFirst', 'peekLast', 'orElse',
              'orElseThrow', 'orElseGet', 'take', 'join', 'firstOrNull', 'lastOrNull', 'single', 'singleOrNull',
              'getOrNull', 'elementAt', 'find', 'random', 'getValue', 'removeAt', 'removeLastOrNull',
              'removeFirstOrNull', 'requireNotNull', 'checkNotNull'}
CONTAINERS = {'List', 'ArrayList', 'LinkedList', 'Set', 'HashSet', 'LinkedHashSet', 'TreeSet', 'SortedSet', 'Collection',
              'Iterable', 'Iterator', 'ListIterator', 'Optional', 'Stack', 'Deque', 'ArrayDeque', 'Queue', 'Vector',
              'CopyOnWriteArrayList', 'BlockingQueue', 'LinkedBlockingQueue', 'ThreadLocal', 'WeakReference',
              'SoftReference', 'Reference', 'AtomicReference', 'Supplier', 'Future', 'CompletableFuture',
              'MutableList', 'MutableSet', 'MutableCollection', 'MutableIterable', 'Sequence', 'Array', 'Lazy',
              'Stream', 'Provider', 'ConcurrentLinkedQueue', 'MutableIterator', 'Enumeration'}
MAPS = {'Map', 'HashMap', 'LinkedHashMap', 'TreeMap', 'SortedMap', 'ConcurrentHashMap', 'WeakHashMap', 'IdentityHashMap',
        'MutableMap', 'ConcurrentMap', 'NavigableMap'}
NOT_ITERABLE = {'Optional', 'ThreadLocal', 'WeakReference', 'SoftReference', 'Reference', 'AtomicReference', 'Supplier',
                'Future', 'CompletableFuture', 'Lazy', 'Provider'}
ITERATED = CONTAINERS - NOT_ITERABLE


class Type:
    __slots__ = ('cid', 'name', 'args', 'static', 'elem', 'recv')

    def __init__(self, cid=None, name=None, args=(), static=False, elem=None, recv=None):
        self.cid, self.name, self.args, self.static, self.elem, self.recv = cid, name, tuple(args), static, elem, recv


def ext(name, args=()):
    return Type(name=name, args=args)


class Elem(Type):
    __slots__ = ()

    def __init__(self, inner):
        super().__init__(inner.cid, inner.name, inner.args, inner.static, inner.elem, inner.recv)


def anonymous_body(node):
    """Cuerpo de una clase anónima (`new T() { … }`): sus métodos ven las variables del método que la crea."""
    return node is not None and node.type == 'class_body' and node.parent is not None and node.parent.type == 'object_creation_expression'


class Pseudo:
    """Valor de una declaración que no es un nodo de expresión (iterado, vararg, parámetro de lambda)."""

    def __init__(self, kind, node, index=0):
        self.kind, self.node, self.index = kind, node, index


class JvmTypes:
    def __init__(self, linker):
        self.l, self.g, self.f = linker, linker.g, linker.f
        self.classes = {}
        self.in_file = {}
        self.nested = defaultdict(dict)
        self.imported = defaultdict(dict)
        self.statics = defaultdict(list)
        self.top_props = {}
        self.kt_aliases = {}
        self.member_ext = {}
        self.prop_names = None
        self.extensions = defaultdict(list)
        self.ext_props = defaultdict(list)
        self.prop_homes = None
        self.memo = {}
        self.by_owner = None
        self.roots = {}
        units = [self.f.units[rel] for rel in sorted(self.f.units) if self.f.units[rel].lang in ('java', 'kotlin')]
        for u in units:
            root = parser_for(u.lang).parse(u.src).root_node
            self.roots[u.rel] = root
            (self.scan_java if u.lang == 'java' else self.scan_kotlin)(u, root)
        for u in units:
            self.link_imports(u)
        self.link_bases()

    # --- registro ---

    def register(self, u, n, name, outer):
        cid = f'c:{u.rel}:{name}'
        if cid not in self.g.nodes or cid in self.classes:
            return None
        self.classes[cid] = {'unit': u, 'node': n, 'outer': outer, 'fields': {}, 'arity': {}, 'tparams': tparams(n, u.src),
                             'companion': None}
        add(self.in_file.setdefault((u.rel, name), []), cid)
        if outer:
            self.nested[outer][name] = cid
        return cid

    def scan_java(self, u, root):
        stack = [(root, None)]
        while stack:
            n, outer = stack.pop()
            cid = outer
            if n.type in JAVA_CLASSES:
                named = n.child_by_field_name('name')
                found = self.register(u, n, text(named, u.src), outer) if named is not None else None
                if found:
                    cid = found
                    self.java_members(u, n, cid)
            for c in n.named_children:
                if c.type in JAVA_CLASSES or c.type in JAVA_BODIES or c.type == 'program':
                    stack.append((c, cid))

    def java_members(self, u, n, cid):
        info = self.classes[cid]
        params = n.child_by_field_name('parameters') if n.type == 'record_declaration' else None
        for p in (params.named_children if params is not None else ()):
            name = p.child_by_field_name('name')
            if name is not None:
                info['fields'][text(name, u.src)] = ('decl', u, p.child_by_field_name('type'), None)
        for c in walk_body(n.child_by_field_name('body')):
            if c.type in JAVA_FIELDS:
                for d in c.children_by_field_name('declarator'):
                    name = d.child_by_field_name('name')
                    if name is not None:
                        typ = c.child_by_field_name('type')
                        info['fields'][text(name, u.src)] = ('decl', u, None if is_var(typ, u.src) else typ,
                                                             d.child_by_field_name('value'))
            elif c.type == 'method_declaration':
                name = c.child_by_field_name('name')
                if name is not None:
                    info['arity'].setdefault(text(name, u.src), []).append(java_arity(c.child_by_field_name('parameters')) + (c,))
            elif c.type == 'enum_constant':
                name = c.child_by_field_name('name')
                if name is not None:
                    info['fields'][text(name, u.src)] = ('self', cid)

    def scan_kotlin(self, u, root):
        stack = [(root, None)]
        while stack:
            n, outer = stack.pop()
            cid = outer
            if n.type in KT_CLASSES:
                name = kt_name(n, u.src)
                found = self.register(u, n, name, outer) if name else None
                if found:
                    cid = found
                    if n.type == 'companion_object' and outer:
                        self.classes[outer]['companion'] = cid
                    self.kt_members(u, n, cid, cid)
                elif n.type == 'companion_object' and outer:
                    self.kt_members(u, n, outer, None)
            elif n.type == 'source_file':
                self.kt_top(u, n)
            for c in n.named_children:
                if c.type in KT_CLASSES or c.type in ('class_body', 'enum_class_body', 'source_file'):
                    stack.append((c, cid))

    def kt_members(self, u, n, cid, own):
        info = self.classes[cid]
        if own:
            ctor = next((c for c in n.named_children if c.type == 'primary_constructor'), None)
            params = next((c for c in ctor.named_children if c.type == 'class_parameters'), None) if ctor is not None else None
            for p in (params.named_children if params is not None else ()):
                if p.type == 'class_parameter':
                    name = next((c for c in p.named_children if c.type == 'identifier'), None)
                    typ = next((c for c in p.named_children if c.type in KT_TYPES), None)
                    if name is not None:
                        info['fields'][text(name, u.src)] = ('decl', u, typ, None)
        body = next((c for c in n.named_children if c.type in ('class_body', 'enum_class_body')), None)
        for c in (body.named_children if body is not None else ()):
            if c.type == 'property_declaration':
                for name, typ, value in kt_property(c, u.src):
                    info['fields'][name] = ('decl', u, typ, value)
            elif c.type == 'function_declaration':
                name = c.child_by_field_name('name')
                if name is not None:
                    info['arity'].setdefault(text(name, u.src), []).append(kt_arity(c) + (c,))
                    recv = kt_receiver(c)
                    fid = f"f:{u.rel}:{self.g.nodes[cid]['name']}.{text(name, u.src)}"
                    if recv is not None and fid in self.g.nodes:
                        self.extensions[text(name, u.src)].append((fid, u, recv, c))
                        home = self.classes[cid]['node']
                        self.member_ext[fid] = (u.rel, home.start_byte, home.end_byte, cid)
            elif c.type == 'enum_entry':
                name = next((x for x in c.named_children if x.type == 'identifier'), None)
                if name is not None:
                    info['fields'][text(name, u.src)] = ('self', cid)
            elif c.type == 'companion_object' and not kt_name(c, u.src):
                self.kt_members(u, c, cid, None)

    def kt_top(self, u, root):
        for c in root.named_children:
            if c.type == 'property_declaration':
                recv = kt_prop_receiver(c)
                for name, typ, value in kt_property(c, u.src):
                    if recv is not None:
                        self.ext_props[name].append((u, recv, ('decl', u, typ, value)))
                    else:
                        self.top_props[(u.rel, name)] = ('decl', u, typ, value)
            elif c.type == 'type_alias':
                name = next((x for x in c.named_children if x.type == 'identifier'), None)
                target = next((x for x in c.named_children if x.type in KT_TYPES), None)
                if name is not None and target is not None:
                    self.kt_aliases.setdefault(text(name, u.src), (u, c, target))
            elif c.type == 'function_declaration':
                recv = kt_receiver(c)
                name = c.child_by_field_name('name')
                fid = f'f:{u.rel}:{text(name, u.src)}' if name is not None else None
                if recv is not None and fid in self.g.nodes:
                    self.extensions[text(name, u.src)].append((fid, u, recv, c))

    def link_imports(self, u):
        for kind, value, alias in u.imports:
            parts = value.split('.')
            if kind == 'fqn' and len(parts) > 1:
                owner = self.fqn_class('.'.join(parts[:-1]))
                if owner:
                    self.statics[u.rel].append((parts[-1], owner))
                    inner = self.nested[owner].get(parts[-1])
                    if inner:
                        self.imported[u.rel][alias or parts[-1]] = inner
            elif kind == 'pkg':
                owner = self.fqn_class(value)
                if owner:
                    self.statics[u.rel].append(('*', owner))

    def fqn_class(self, value, depth=0):
        target = self.f.fqn.get(value)
        if target in self.g.nodes and self.g.nodes[target]['kind'] == 'class':
            return target
        head, _, tail = value.rpartition('.')
        owner = self.fqn_class(head, depth + 1) if head and depth < MAX_DEPTH else None
        if owner and tail == 'Companion':
            return owner  # los miembros del companion sin nombre se registran en la clase
        return self.nested[owner].get(tail) if owner else None

    def link_bases(self):
        for cid, info in self.classes.items():
            u, n = info['unit'], info['node']
            for k in base_types(n):
                found = self.resolve_type(u, n, k)
                if found is not None and found.cid and found.cid != cid and found.cid not in self.l.parents.get(cid, ()):
                    self.l.parents[cid].append(found.cid)
                    self.g.edge(cid, found.cid, 'inherits')

    # --- tipos ---

    def resolve_type(self, u, at, node, depth=0):
        if node is None or depth > MAX_DEPTH:
            return UNKNOWN
        if isinstance(node, Pseudo):
            return self.pseudo(u, node, depth)
        if u.lang == 'kotlin':
            return self.kt_type(u, at, node, depth)
        t = node.type
        if t in JAVA_PRIMITIVES:
            return ext(text(node, u.src))
        if t == 'array_type':
            return Type(name='[]', elem=self.resolve_type(u, at, node.child_by_field_name('element'), depth + 1))
        if t == 'generic_type':
            base = node.named_children[0] if node.named_children else None
            found = self.resolve_type(u, at, base, depth + 1)
            args = next((c for c in node.named_children if c.type == 'type_arguments'), None)
            if found is not None and args is not None:
                found = Type(found.cid, found.name, [(u, at, a) for a in args.named_children])
            return found
        if t == 'type_identifier':
            return self.named_type(u, at, text(node, u.src))
        if t == 'scoped_type_identifier':
            parts = [c for c in node.named_children if c.type in ('type_identifier', 'scoped_type_identifier', 'generic_type')]
            if len(parts) < 2:
                return UNKNOWN
            return self.dotted(u, at, parts[0], text(parts[-1], u.src), text(node, u.src), depth)
        if t == 'annotated_type' and node.named_children:
            return self.resolve_type(u, at, node.named_children[-1], depth + 1)
        return UNKNOWN

    def dotted(self, u, at, head, name, whole, depth):
        outer = self.resolve_type(u, at, head, depth + 1)
        if outer is not None and outer.cid:
            return self.member_class(outer.cid, name)
        target = self.fqn_class(''.join(whole.split()))
        return Type(target) if target else (UNKNOWN if outer is None else ext(name))

    def kt_type(self, u, at, node, depth):
        t = node.type
        if t in ('nullable_type', 'parenthesized_type', 'non_nullable_type', 'definitely_non_nullable_type'):
            inner = next((c for c in node.named_children if c.type in KT_TYPES), None)
            return self.resolve_type(u, at, inner, depth + 1)
        if t == 'function_type':
            kids = node.named_children
            params = next((c for c in kids if c.type == 'function_type_parameters'), None)
            recv = kids[0] if kids and kids[0].type in KT_TYPES and params is not None and kids[0].end_byte <= params.start_byte else None
            ret = kids[-1] if kids and kids[-1].type in KT_TYPES and kids[-1] != recv else None
            plist = [(u, at, p) for p in (params.named_children if params is not None else ()) if p.type in KT_TYPES or p.type == 'parameter']
            return Type(name='->', args=plist, elem=(u, at, ret), recv=(u, at, recv) if recv is not None else None)
        if t == 'user_type':
            idents = [c for c in node.named_children if c.type == 'identifier']
            args = next((c for c in node.named_children if c.type == 'type_arguments'), None)
            if not idents:
                return UNKNOWN
            if len(idents) == 1:
                found = self.named_type(u, at, text(idents[0], u.src))
            else:
                found = self.named_type(u, at, text(idents[0], u.src))
                for ident in idents[1:]:
                    if found is not None and found.cid:
                        found = self.member_class(found.cid, text(ident, u.src))
                    else:
                        target = self.fqn_class('.'.join(text(i, u.src) for i in idents))
                        found = Type(target) if target else (ext(text(idents[-1], u.src)) if found is not None else UNKNOWN)
                        break
            if found is not None and args is not None:
                kids = [next((k for k in p.named_children if k.type in KT_TYPES), None) for p in args.named_children]
                found = Type(found.cid, found.name, [(u, at, k) for k in kids])
            return found
        if t == 'parameter':
            return self.resolve_type(u, at, next((c for c in node.named_children if c.type in KT_TYPES), None), depth + 1)
        return UNKNOWN

    def named_type(self, u, at, name):
        key = ('type', u.rel, at.id if at is not None else None, name)
        if key not in self.memo:
            self.memo[key] = UNKNOWN
            self.memo[key] = self._named_type(u, at, name)
        return self.memo[key]

    def _named_type(self, u, at, name):
        if name == 'var':
            return UNKNOWN
        cur = at
        while cur is not None:
            if name in tparams(cur, u.src):
                bound = tparam_bound(cur, u.src, name)
                return self.resolve_type(u, cur, bound) if bound is not None else UNKNOWN
            cur = cur.parent
        for cid in self.chain(u, at):
            inner = self.member_class(cid, name)
            if inner is not None:
                return inner
        local = self.in_file.get((u.rel, name))
        if local:
            return Type(local[0])
        if name in self.imported[u.rel]:
            return Type(self.imported[u.rel][name])
        for member, owner in self.statics[u.rel]:
            if member == '*' and name in self.nested[owner]:
                return Type(self.nested[owner][name])
        found = self.l.type_target(u, name)
        alias = self.kt_aliases.get(name) if u.lang == 'kotlin' else None
        if alias and (not found or (self.g.nodes[found]['file'], self.g.nodes[found].get('decl') or self.g.nodes[found]['line']) ==
                      (alias[0].rel, decl_line(alias[1]))):
            return self.resolve_type(alias[0], alias[1], alias[2], 1)
        if found:
            return Type(found)
        if name in self.f.classes_by_name and not (u.lang == 'kotlin' and name in KT_DEFAULT_TYPES):
            return UNKNOWN
        return ext(name)

    def member_class(self, cid, name, seen=None):
        seen = seen or set()
        if cid in seen or len(seen) > MAX_DEPTH:
            return None
        seen.add(cid)
        inner = self.nested[cid].get(name)
        if inner:
            return Type(inner, static=True)
        companion = self.classes.get(cid, {}).get('companion')
        if companion and name == 'Companion':
            return Type(companion, static=True)
        for base in self.l.parents.get(cid, ()):
            found = self.member_class(base, name, seen)
            if found:
                return found
        return None

    def chain(self, u, at):
        out = []
        cur = at
        classes = JAVA_CLASSES if u.lang == 'java' else KT_CLASSES
        while cur is not None:
            if cur.type in classes:
                name = kt_name(cur, u.src) if u.lang == 'kotlin' else text_of(cur.child_by_field_name('name'), u.src)
                cid = f'c:{u.rel}:{name}' if name else None
                if cid in self.classes:
                    out.append(cid)
            cur = cur.parent
        return out

    def pseudo(self, u, p, depth):
        if p.kind == 'array':
            return Type(name='[]', elem=self.resolve_type(u, p.node, p.node, depth + 1))
        if p.kind == 'iter':
            return self.iterated(self.type_of(u, p.node, depth + 1))
        if p.kind == 'lambda':
            return self.lambda_param(u, p.node, p.index, depth + 1)
        return UNKNOWN

    def iterated(self, t, depth=0):
        if t is None:
            return UNKNOWN
        if t.name == '[]':
            return t.elem
        if t.name in ITERATED and t.args:
            return self.arg(t, 0, depth)
        if t.name in MAPS:
            return UNKNOWN
        return UNKNOWN

    def arg(self, t, i, depth=0):
        if i >= len(t.args):
            return UNKNOWN
        if isinstance(t.args[i], Type):
            return t.args[i]
        au, at, node = t.args[i]
        return self.resolve_type(au, at, node, depth + 1)

    def element(self, owner, name):
        if owner is None or owner.cid or not owner.args:
            return UNKNOWN
        if owner.name in MAPS and name in ('get', 'remove', 'getOrDefault', 'put', 'getValue', 'getOrPut', 'getOrElse') and len(owner.args) == 2:
            return self.arg(owner, 1)
        if owner.name in CONTAINERS and name in ELEMENT_OF:
            return self.arg(owner, 0)
        return UNKNOWN

    # --- expresiones ---

    def type_of(self, u, expr, depth=0):
        if expr is None or depth > MAX_DEPTH:
            return UNKNOWN
        if isinstance(expr, Pseudo):
            return self.pseudo(u, expr, depth)
        key = ('expr', u.rel, expr.id)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = UNKNOWN
        found = (self.java_expr if u.lang == 'java' else self.kt_expr)(u, expr, depth)
        self.memo[key] = found
        return found

    def java_expr(self, u, expr, depth):
        t = expr.type
        if t == 'identifier':
            return self.variable(u, expr, text(expr, u.src), depth)
        if t == 'this':
            return self.this_type(u, expr)
        if t == 'super':
            return self.parent_of(self.this_type(u, expr))
        if t == 'parenthesized_expression':
            return self.type_of(u, expr.named_children[0] if expr.named_children else None, depth + 1)
        if t in ('cast_expression', 'object_creation_expression'):
            return self.resolve_type(u, expr, expr.child_by_field_name('type'), depth + 1)
        if t == 'array_creation_expression':
            return Type(name='[]', elem=self.resolve_type(u, expr, expr.child_by_field_name('type'), depth + 1))
        if t == 'array_access':
            arr = self.type_of(u, expr.child_by_field_name('array'), depth + 1)
            return arr.elem if arr is not None else UNKNOWN
        if t in JAVA_LITERALS:
            return ext(JAVA_LITERALS[t])
        if t == 'ternary_expression':
            return self.type_of(u, expr.child_by_field_name('consequence'), depth + 1)
        if t == 'assignment_expression':
            return self.type_of(u, expr.child_by_field_name('left'), depth + 1)
        if t == 'field_access':
            owner = self.type_of(u, expr.child_by_field_name('object'), depth + 1)
            field = expr.child_by_field_name('field')
            if owner is None or field is None:
                return UNKNOWN
            return self.member(owner, text(field, u.src), depth)
        if t == 'method_invocation':
            return self.result(u, expr, depth)
        return UNKNOWN

    def kt_expr(self, u, expr, depth):
        t = expr.type
        if t == 'identifier':
            return self.variable(u, expr, text(expr, u.src), depth)
        if t == 'this_expression':
            label = next((c for c in expr.named_children if c.type == 'identifier'), None)
            return self.this_type(u, expr, text(label, u.src) if label is not None else None)
        if t == 'super_expression':
            return self.parent_of(self.this_type(u, expr))
        if t in ('parenthesized_expression', 'annotated_expression', 'labeled_expression') and expr.named_children:
            return self.type_of(u, expr.named_children[-1], depth + 1)
        if t == 'as_expression':
            return self.resolve_type(u, expr, expr.child_by_field_name('right'), depth + 1)
        if t == 'unary_expression' and text(expr, u.src).endswith('!!'):
            return self.type_of(u, expr.child_by_field_name('argument'), depth + 1)
        if t == 'binary_expression' and any(c.type == '?:' for c in expr.children):
            return self.type_of(u, expr.child_by_field_name('left'), depth + 1)
        if t in KT_LITERALS:
            return ext(KT_LITERALS[t])
        if t == 'object_literal':
            spec = next((c for c in expr.named_children if c.type == 'delegation_specifiers'), None)
            kids = base_types(expr) if spec is not None else []
            return self.resolve_type(u, expr, kids[0], depth + 1) if kids else UNKNOWN
        if t == 'index_expression':
            owner = self.type_of(u, expr.named_children[0] if expr.named_children else None, depth + 1)
            if owner is not None and owner.name in MAPS:
                return self.arg(owner, 1, depth)
            if owner is not None and owner.name == '[]':
                return owner.elem
            return self.arg(owner, 0, depth) if owner is not None and owner.name in CONTAINERS else UNKNOWN
        if t == 'navigation_expression':
            kids = expr.named_children
            if len(kids) < 2 or kids[-1].type != 'identifier' or nav_op(expr) == '::':
                return UNKNOWN
            owner = self.type_of(u, kids[0], depth + 1)
            return self.member(owner, text(kids[-1], u.src), depth) if owner is not None else UNKNOWN
        if t == 'call_expression':
            return self.result(u, expr, depth)
        return UNKNOWN

    def member(self, owner, name, depth):
        if owner.cid:
            found = self.field_type(owner.cid, name, depth + 1)
            if found is not None:
                return found
            companion = self.classes.get(owner.cid, {}).get('companion')
            if owner.static and companion:
                found = self.field_type(companion, name, depth + 1)
                if found is not None:
                    return found
            if owner.static:
                return self.member_class(owner.cid, name)
            return self.ext_prop(owner, name, depth)
        if owner.name == '[]' and name in ('length', 'size'):
            return ext('int')
        return self.ext_prop(owner, name, depth)

    def ext_prop(self, owner, name, depth):
        """Propiedad de extensión `val Tipo.nombre: T` aplicable a `owner` (también a tipos externos)."""
        family = self.ancestors(owner.cid) if owner.cid else []
        for eu, recv, held in self.ext_props.get(name, ()):
            found = self.resolve_type(eu, recv, recv)
            if found is not None and (found.cid and found.cid in family or not found.cid and not owner.cid and
                                      found.name in ext_family(owner.name)):
                return self.source_type(held, depth)
        return UNKNOWN

    def result(self, u, expr, depth):
        callee = expr.named_children[0] if u.lang == 'kotlin' and expr.named_children else None
        if callee is not None and callee.type == 'identifier' and (self.kt_local(u, callee, text(callee, u.src)) is not False or
                                                                  not self.call(u, expr, depth + 1)[0]):
            # llamar a un valor de tipo función (`next(request)`) devuelve el tipo de retorno de esa función
            held = self.variable(u, callee, text(callee, u.src), depth + 1)
            fn = self.as_function(held) if held is not None and (held.name == '->' or held.cid) else None
            ret = fn.elem if fn is not None and fn.elem else None
            if ret and ret[2] is not None:
                return self.resolve_type(ret[0], ret[1], ret[2], depth + 1)
        if callee is not None and callee.type == 'navigation_expression' and len(callee.named_children) == 2 and \
                callee.named_children[-1].type == 'identifier':
            # `modo.compress(x)` con `compress` una propiedad de tipo función
            owner = self.type_of(u, callee.named_children[0], depth + 1)
            name = text(callee.named_children[-1], u.src)
            held = self.member(owner, name, depth) if owner is not None and owner.cid and not self.method(owner.cid, name) else None
            ret = held.elem if held is not None and held.name == '->' and held.elem else None
            if ret and ret[2] is not None:
                return self.resolve_type(ret[0], ret[1], ret[2], depth + 1)
        target, owner = self.call(u, expr, depth + 1)
        if isinstance(owner, Elem):
            return owner
        if target and self.g.nodes[target]['kind'] == 'class':
            return Type(target)
        if target:
            return self.returns(target, owner, depth + 1, argcount(u, expr))
        return UNKNOWN

    def parent_of(self, here):
        bases = self.l.parents.get(here.cid, ()) if here is not None and here.cid else ()
        return Type(bases[0]) if bases else UNKNOWN

    def this_type(self, u, expr, label=None):
        cur = expr.parent
        while cur is not None:
            t = cur.type
            if u.lang == 'java':
                if t == 'class_body' and cur.parent is not None and cur.parent.type == 'object_creation_expression':
                    return self.resolve_type(u, cur.parent, cur.parent.child_by_field_name('type'))
                if t in JAVA_CLASSES:
                    chain = self.chain(u, cur)
                    return Type(chain[0]) if chain else UNKNOWN
            else:
                if t == 'lambda_literal' and label is None:
                    recv = self.lambda_receiver(u, cur)
                    if recv is not None:
                        return recv
                if t == 'function_declaration':
                    recv = kt_receiver(cur)
                    name = text_of(cur.child_by_field_name('name'), u.src)
                    if recv is not None and label in (None, name):
                        return self.resolve_type(u, cur, recv)
                if t == 'object_literal' and label is None:
                    return self.type_of(u, cur)
                if t in KT_CLASSES and label in (None, kt_name(cur, u.src)):
                    chain = self.chain(u, cur)
                    return Type(chain[0]) if chain else UNKNOWN
            cur = cur.parent
        return UNKNOWN

    def variable(self, u, use, name, depth):
        found = (self.java_local if u.lang == 'java' else self.kt_local)(u, use, name)
        if found is not False:
            if found is None:
                return UNKNOWN
            typ, value = found
            if typ is not None:
                return self.resolve_type(u, use, typ, depth + 1)
            return self.type_of(u, value, depth + 1) if value is not None else UNKNOWN
        for t in self.receivers(u, use):
            if t.cid:
                found = self.field_type(t.cid, name, depth + 1)
                info = self.classes.get(t.cid, {})
                if found is None and info.get('outer') and info['node'].type == 'companion_object':
                    found = self.field_type(info['outer'], name, depth + 1)  # dentro del companion: sus propiedades
                if found is not None:
                    return found
                companion = self.classes.get(t.cid, {}).get('companion')
                found = self.field_type(companion, name, depth + 1) if companion else None
                if found is not None:
                    return found
        if u.lang == 'kotlin' and name in self.ext_props:
            for t in self.receivers(u, use):
                found = self.ext_prop(t, name, depth)
                if found is not None:
                    return found
        for member, owner in self.statics[u.rel]:
            if member in (name, '*'):
                found = self.field_type(owner, name, depth + 1)
                if found is not None:
                    return found
        if u.lang == 'kotlin':
            found = self.top_prop(u, name, depth)
            if found is not None:
                return found
        found = self.named_type(u, use, name) if name[:1].isupper() else UNKNOWN
        if found is not None:
            return Type(found.cid, found.name, static=True)
        if u.lang == 'kotlin' and name[:1].islower() and any(t.name and not t.cid for t in self.receivers(u, use)):
            return ext('?')
        return UNKNOWN

    def top_prop_home(self, u, name):
        """Archivo que declara la propiedad de nivel superior `name` visible desde `u`: el propio archivo, el mismo paquete,
        un import por nombre o un `import paquete.*`."""
        if (u.rel, name) in self.top_props:
            return u.rel
        found = next((rel for rel in sorted(u.scope) if (rel, name) in self.top_props), None)
        alias = u.aliases.get(name) if found is None else None
        if alias and alias[0] == 'files':
            found = next((r for r in alias[1] if (r, name) in self.top_props), None)
        if found is None and u.lang == 'kotlin':
            found = next((r for r in self.prop_imports(u) if (r, name) in self.top_props), None)
            for kind, value, _ in u.imports if found is None else ():
                if kind == 'pkg':
                    found = next((r for r in self.prop_homes.get((value, name), ()) if (r, name) in self.top_props), None)
                    if found is not None:
                        break
        return found

    def top_prop(self, u, name, depth):
        home = self.top_prop_home(u, name)
        held = self.top_props[(home, name)] if home is not None else None
        return self.source_type(held, depth) if held is not None else None

    def receivers(self, u, use):
        """Tipos de los receptores implícitos, del más interno al más externo."""
        out = []
        cur = use.parent
        while cur is not None:
            t = cur.type
            if u.lang == 'java':
                if t == 'class_body' and cur.parent is not None and cur.parent.type == 'object_creation_expression':
                    found = self.resolve_type(u, cur.parent, cur.parent.child_by_field_name('type'))
                    if found is not None and found.cid:
                        out.append(found)
                if t in JAVA_CLASSES:
                    out += [Type(c) for c in self.chain(u, cur)]
                    break
            else:
                if t == 'lambda_literal':
                    found = self.lambda_receiver(u, cur)
                    if found is not None:
                        out.append(found)
                elif t == 'function_declaration' and kt_receiver(cur) is not None:
                    found = self.resolve_type(u, cur, kt_receiver(cur))
                    if found is not None:
                        out.append(found)
                elif t == 'object_literal':
                    found = self.type_of(u, cur)
                    if found is not None and found.cid:
                        out.append(found)
                elif t in KT_CLASSES:
                    out += [Type(c) for c in self.chain(u, cur)]
                    break
            cur = cur.parent
        return out

    def java_local(self, u, use, name):
        prev, cur = use, use.parent
        while cur is not None:
            t = cur.type
            if t in JAVA_CLASSES or t == 'class_body' and not anonymous_body(cur):
                return False
            if t in JAVA_BLOCKS or t == 'program':
                best = None
                for c in cur.named_children:
                    if c.start_byte >= use.start_byte:
                        break
                    if c.end_byte > use.start_byte:
                        continue
                    if c.type == 'local_variable_declaration':
                        for d in c.children_by_field_name('declarator'):
                            if text_of(d.child_by_field_name('name'), u.src) == name:
                                typ = c.child_by_field_name('type')
                                best = (None if is_var(typ, u.src) else typ, d.child_by_field_name('value'))
                if best:
                    return best
            elif t == 'enhanced_for_statement' and prev == cur.child_by_field_name('body'):
                if text_of(cur.child_by_field_name('name'), u.src) == name:
                    typ = cur.child_by_field_name('type')
                    return (None, Pseudo('iter', cur.child_by_field_name('value'))) if is_var(typ, u.src) else (typ, None)
            elif t == 'for_statement':
                for init in cur.children_by_field_name('init'):
                    if init.type == 'local_variable_declaration':
                        for d in init.children_by_field_name('declarator'):
                            if text_of(d.child_by_field_name('name'), u.src) == name:
                                typ = init.child_by_field_name('type')
                                return (None if is_var(typ, u.src) else typ, d.child_by_field_name('value'))
            elif t == 'catch_clause':
                for p in cur.named_children:
                    if p.type == 'catch_formal_parameter' and text_of(p.child_by_field_name('name'), u.src) == name:
                        types = [x for x in p.named_children if x.type == 'catch_type']
                        inner = types[0].named_children if types else []
                        return (inner[0] if len(inner) == 1 else None, None)
            elif t == 'try_with_resources_statement':
                spec = cur.child_by_field_name('resources')
                for r in (spec.named_children if spec is not None else ()):
                    if r.type == 'resource' and text_of(r.child_by_field_name('name'), u.src) == name:
                        typ = r.child_by_field_name('type')
                        return (None if is_var(typ, u.src) else typ, r.child_by_field_name('value'))
            if t in JAVA_CALLABLES:
                params = cur.child_by_field_name('parameters')
                if params is not None and params.type == 'identifier':
                    if text(params, u.src) == name:
                        return None
                for p in (params.named_children if params is not None else ()):
                    if p.type == 'identifier' and text(p, u.src) == name:
                        return None
                    if p.type == 'formal_parameter' and text_of(p.child_by_field_name('name'), u.src) == name:
                        return (p.child_by_field_name('type'), None)
                    if p.type == 'spread_parameter':
                        decl = next((x for x in p.named_children if x.type == 'variable_declarator'), None)
                        if decl is not None and text_of(decl.child_by_field_name('name'), u.src) == name:
                            elem = next((x for x in p.named_children if x.type not in ('variable_declarator', 'modifiers')), None)
                            return (Pseudo('array', elem), None)
                found = java_pattern(cur, u.src, name)
                if found is not None:
                    return (found, None)
                if t != 'lambda_expression' and not anonymous_body(cur.parent):
                    return False
            prev, cur = cur, cur.parent
        return False

    def kt_local(self, u, use, name):
        prev, cur = use, use.parent
        while cur is not None:
            t = cur.type
            if t in KT_CLASSES or t in ('class_body', 'object_literal', 'enum_class_body'):
                return False
            if t in KT_STATEMENTS:
                best = False
                for c in cur.named_children:
                    if c.start_byte >= use.start_byte:
                        break
                    if c.end_byte > use.start_byte:
                        continue
                    if c.type == 'property_declaration':
                        for pname, typ, value in kt_property(c, u.src):
                            if pname == name:
                                best = (typ, value)
                        multi = next((x for x in c.named_children if x.type == 'multi_variable_declaration'), None)
                        if multi is not None and name in kt_names(multi, u.src):
                            typ = kt_typed(multi, u.src, name)
                            best = (typ, None) if typ is not None else None
                if best is not False:
                    return best
            if t == 'for_statement' and prev.type in ('block', 'control_structure_body'):
                decls = [c for c in cur.named_children if c.type in ('variable_declaration', 'multi_variable_declaration')]
                for d in decls:
                    if d.type == 'variable_declaration' and kt_names(d, u.src) == [name]:
                        typ = next((x for x in d.named_children if x.type in KT_TYPES), None)
                        rest = [c for c in cur.named_children if c not in decls and c.type not in ('block', 'control_structure_body')]
                        return (typ, None) if typ is not None else (None, Pseudo('iter', rest[0]) if rest else None)
                    if d.type == 'multi_variable_declaration' and name in kt_names(d, u.src):
                        return None
            elif t == 'catch_block':
                ident = next((c for c in cur.named_children if c.type == 'identifier'), None)
                if ident is not None and text(ident, u.src) == name:
                    return (next((c for c in cur.named_children if c.type in KT_TYPES), None), None)
            elif t == 'when_entry':
                found = self.kt_smart(u, cur, name, when=True)
                if found is not None:
                    return (found, None)
            elif t == 'if_expression' and prev != cur.child_by_field_name('condition'):
                found = self.kt_smart(u, cur, name)
                if found is not None:
                    return (found, None)
            elif t == 'lambda_literal':
                params = next((c for c in cur.named_children if c.type == 'lambda_parameters'), None)
                if params is None and name == 'it':
                    return (None, Pseudo('lambda', cur, 0))
                for i, p in enumerate(params.named_children if params is not None else ()):
                    if name in kt_names(p, u.src):
                        typ = next((x for x in p.named_children if x.type in KT_TYPES), None)
                        if p.type == 'multi_variable_declaration':
                            return None
                        return (typ, None) if typ is not None else (None, Pseudo('lambda', cur, i))
            elif t in ('function_declaration', 'secondary_constructor', 'setter', 'getter'):
                params = next((c for c in cur.named_children if c.type in ('function_value_parameters', 'parameter_with_optional_type')), None)
                for p in (params.named_children if params is not None else ()):
                    if p.type == 'parameter':
                        ident = next((x for x in p.named_children if x.type == 'identifier'), None)
                        if ident is not None and text(ident, u.src) == name:
                            return (next((x for x in p.named_children if x.type in KT_TYPES), None), None)
                if t == 'function_declaration':
                    return False
            prev, cur = cur, cur.parent
        return False

    def kt_smart(self, u, node, name, when=False):
        if when:
            when_node = node.parent
            subject = next((c for c in when_node.named_children if c.type == 'when_subject'), None) if when_node is not None else None
            ident = subject.named_children[0] if subject is not None and subject.named_children else None
            cond = node.child_by_field_name('condition')
            if ident is not None and ident.type == 'identifier' and text(ident, u.src) == name and cond is not None and cond.type == 'type_test':
                return next((c for c in cond.named_children if c.type in KT_TYPES), None)
            return None
        cond = node.child_by_field_name('condition')
        if cond is not None and cond.type == 'is_expression' and not text(cond, u.src).replace(' ', '').count('!is'):
            left = cond.child_by_field_name('left')
            if left is not None and left.type == 'identifier' and text(left, u.src) == name:
                return cond.child_by_field_name('right')
        return None

    def source_type(self, held, depth):
        if held[0] == 'self':
            return Type(held[1])
        _, su, typ, value = held
        if typ is not None:
            return self.resolve_type(su, typ, typ, depth + 1)
        return self.type_of(su, value, depth + 1) if value is not None else UNKNOWN

    def field_type(self, cid, name, depth, seen=None):
        seen = seen or set()
        if cid in seen or depth > MAX_DEPTH:
            return None
        seen.add(cid)
        info = self.classes.get(cid)
        if info is None:
            return None
        if name in info['fields']:
            return self.source_type(info['fields'][name], depth)
        for base in self.l.parents.get(cid, ()):
            found = self.field_type(base, name, depth + 1, seen)
            if found is not None:
                return found
        return None

    def declaration(self, fid):
        meta = self.g.nodes.get(fid) or {}
        u = self.f.units.get(meta.get('file'))
        node = u.fnodes.get(fid) if u is not None else None
        return u, node

    def overload(self, fid, argc):
        meta = self.g.nodes[fid]
        owner, _, name = str(meta['name']).rpartition('.')
        found = self.in_file.get((meta['file'], owner)) if owner else None
        info = self.classes.get(found[0]) if found else None
        for entry in (info['arity'].get(name, ()) if info and argc is not None else ()):
            if fits(entry, argc):
                return entry[2]
        u, node = self.declaration(fid)
        if not owner and argc is not None and node is not None and u.lang == 'kotlin' and node.parent is not None:
            # funciones de nivel superior homónimas del mismo archivo (sobrecargas de extensión): la de esa aridad
            for c in node.parent.named_children:
                if c.type == 'function_declaration' and text_of(c.child_by_field_name('name'), u.src) == name and fits(kt_arity(c), argc):
                    return c
        return None

    def returns(self, fid, owner, depth, argc=None):
        u, node = self.declaration(fid)
        node = self.overload(fid, argc) or node
        if node is None:
            return UNKNOWN
        if u.lang == 'java':
            typ = node.child_by_field_name('type')
        else:
            typ = kt_return(node)
            if typ is None:
                body = next((c for c in node.named_children if c.type == 'function_body'), None)
                if body is not None and text(body, u.src).lstrip().startswith('=') and body.named_children:
                    return self.type_of(u, body.named_children[0], depth + 1)
                return UNKNOWN
        if typ is not None and owner is not None and owner.args and owner.cid:
            names = self.classes.get(owner.cid, {}).get('tparams', [])
            name = type_name(typ, u.src)
            if name in names and names.index(name) < len(owner.args):
                return self.arg(owner, names.index(name), depth)
        return self.resolve_type(u, node, typ, depth + 1)

    def params(self, fid):
        u, node = self.declaration(fid)
        if node is None:
            return u, []
        if u.lang == 'java':
            ps = node.child_by_field_name('parameters')
            return u, [p.child_by_field_name('type') if p.type == 'formal_parameter' else None
                       for p in (ps.named_children if ps is not None else ()) if p.type in ('formal_parameter', 'spread_parameter')]
        ps = next((c for c in node.named_children if c.type == 'function_value_parameters'), None)
        return u, [next((x for x in p.named_children if x.type in KT_TYPES), None)
                   for p in (ps.named_children if ps is not None else ()) if p.type == 'parameter']

    def as_function(self, slot):
        """Tipo función de un tipo esperado: el propio `(A) -> B` o el supertipo función de una `fun interface`
        (`fun interface Filter : (HttpHandler) -> HttpHandler`)."""
        if slot is None or slot.name == '->':
            return slot
        info = self.classes.get(slot.cid) if slot.cid else None
        spec = next((c for c in info['node'].named_children if c.type == 'delegation_specifiers'), None) if info else None
        for d in (spec.named_children if spec is not None else ()):
            fn = next((c for c in d.named_children if c.type == 'function_type'), None)
            if fn is not None:
                return self.resolve_type(info['unit'], info['node'], fn, 1)
        return None

    def lambda_slot(self, u, lam, depth):
        """Tipo esperado (función o interfaz funcional) de la lambda `lam` según dónde aparece."""
        parent = lam.parent
        if depth > MAX_DEPTH:
            return None, None
        if parent is not None and parent.type == 'lambda_literal' and parent.named_children and parent.named_children[-1] == lam:
            # lambda que devuelve otra lambda (`Filter { next -> { request -> … } }`): su tipo es el retorno de la de fuera
            outer = self.as_function(self.lambda_slot(u, parent, depth + 1)[0])
            ret = outer.elem if outer is not None and outer.elem else None
            return (self.resolve_type(*ret[:2], ret[2], depth + 1) if ret and ret[2] is not None else None), None
        if parent is not None and parent.type == 'function_body' and parent.parent is not None and \
                parent.parent.type == 'function_declaration' and kt_return(parent.parent) is not None:
            return self.resolve_type(u, parent.parent, kt_return(parent.parent), depth + 1), None
        if parent is not None and parent.type == 'annotated_lambda':
            call = parent.parent
            index = -1
        elif parent is not None and parent.type == 'value_argument':
            args = parent.parent
            call = args.parent if args is not None else None
            index = [c for c in args.named_children if c.type == 'value_argument'].index(parent)
        elif parent is not None and parent.type == 'property_declaration':
            typ = next((t for _, t, v in kt_property(parent, u.src) if v is not None and v.id == lam.id), None)
            return (self.resolve_type(u, parent, typ, depth + 1) if typ is not None else None), None
        else:
            return None, None
        if call is None or call.type != 'call_expression':
            return None, None
        callee = call.named_children[0] if call.named_children else None
        if callee is not None and callee.type == 'call_expression':
            call, callee = callee, callee.named_children[0] if callee.named_children else None
        name = None
        if callee is not None and callee.type == 'navigation_expression' and callee.named_children:
            name = text(callee.named_children[-1], u.src)
            recv = self.type_of(u, callee.named_children[0], depth + 1)
            if name in KT_SAME or name in KT_ITERATING:
                return None, (name, recv)
        elif callee is not None and callee.type == 'identifier':
            name = text(callee, u.src)
            if name in KT_BUILDERS and index == -1 and not self.f.top_by_name.get(name):
                # `buildString { append(x) }`: la lambda tiene como receptor el `StringBuilder` de la biblioteca estándar
                return None, ('run', ext(KT_BUILDERS[name]))
            if name == 'with':
                args = next((c for c in call.named_children if c.type == 'value_arguments'), None)
                first = args.named_children[0] if args is not None and args.named_children else None
                return None, ('run', self.type_of(u, first.named_children[0] if first is not None and first.named_children else None, depth + 1))
        target, _ = self.call(u, call, depth + 1)
        if not target:
            return None, None
        if self.g.nodes[target]['kind'] == 'class' and index >= 0 and u.lang == 'kotlin':
            # lambda como argumento del constructor primario: el tipo del parámetro en esa posición
            info = self.classes.get(target)
            ctor = next((c for c in info['node'].named_children if c.type == 'primary_constructor'), None) if info else None
            params = next((c for c in ctor.named_children if c.type == 'class_parameters'), None) if ctor is not None else None
            kids = [c for c in params.named_children if c.type == 'class_parameter'] if params is not None else []
            typ = next((c for c in kids[index].named_children if c.type in KT_TYPES), None) if index < len(kids) else None
            return (self.resolve_type(info['unit'], info['node'], typ, depth + 1) if typ is not None else None), None
        if self.g.nodes[target]['kind'] == 'class':
            targs = next((c for c in call.named_children if c.type == 'type_arguments'), None)
            kids = [next((k for k in p.named_children if k.type in KT_TYPES), None) for p in (targs.named_children if targs is not None else ())]
            return Type(target, args=[(u, call, k) for k in kids]), None
        pu, ptypes = self.params(target)
        if not ptypes:
            return None, None
        slot = ptypes[index] if -len(ptypes) <= index < len(ptypes) else None
        _, decl = self.declaration(target)
        return (self.resolve_type(pu, decl, slot, depth + 1) if slot is not None else None), None

    def sam(self, cid):
        """Parámetros del único método de una interfaz funcional del proyecto."""
        if self.by_owner is None:
            self.by_owner = defaultdict(list)
            for (owner, _), fids in self.f.methods.items():
                for m in fids:
                    self.by_owner[(self.g.nodes[m]['file'], owner)].append(m)
        methods = self.by_owner.get((self.g.nodes[cid]['file'], self.g.nodes[cid]['name']), [])
        if len(methods) != 1:
            return None
        u, types = self.params(methods[0])
        _, decl = self.declaration(methods[0])
        return [(u, decl, t) for t in types]

    def lambda_param(self, u, lam, index, depth):
        slot, scoped = self.lambda_slot(u, lam, depth)
        if scoped is not None:
            name, recv = scoped
            if recv is None:
                return UNKNOWN
            if name in KT_SAME:
                return recv if KT_SAME[name] == 'it' and index == 0 else UNKNOWN
            if index == KT_INDEXED.get(name, 0):
                return self.iterated(recv)
            if name == 'fold' and index == 0 and lam.parent is not None and lam.parent.parent is not None:
                # el acumulador de `fold(inicial) { acc, x -> … }` tiene el tipo del valor inicial
                args = next((c for c in lam.parent.parent.named_children if c.type == 'value_arguments'), None)
                if args is None:
                    inner = lam.parent.parent.named_children[0]
                    args = next((c for c in inner.named_children if c.type == 'value_arguments'), None)
                first = args.named_children[0] if args is not None and args.named_children else None
                return self.type_of(u, first.named_children[-1], depth + 1) if first is not None and first.named_children else UNKNOWN
            return UNKNOWN
        if slot is None:
            return UNKNOWN
        if slot.name == '->':
            return self.arg(slot, index, depth) if index < len(slot.args) else UNKNOWN
        if slot.cid:
            params = self.sam(slot.cid)
            fn = self.as_function(slot) if not params else None
            if fn is not None:
                return self.arg(fn, index, depth) if index < len(fn.args) else UNKNOWN
            if params and index < len(params):
                pu, at, typ = params[index]
                names = self.classes.get(slot.cid, {}).get('tparams', [])
                name = type_name(typ, pu.src)
                if slot.args and name in names and names.index(name) < len(slot.args):
                    return self.arg(slot, names.index(name), depth)
                return self.resolve_type(pu, at, typ, depth + 1)
        return UNKNOWN

    def lambda_receiver(self, u, lam):
        key = ('recv', u.rel, lam.id)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = None
        slot, scoped = self.lambda_slot(u, lam, 0)
        found = None
        if scoped is not None and KT_SAME.get(scoped[0]) == 'this':
            found = scoped[1]
        elif slot is not None and slot.name == '->' and slot.recv is not None:
            ru, at, node = slot.recv
            found = self.resolve_type(ru, at, node)
        self.memo[key] = found
        return found

    # --- accesos a miembros ---

    def members(self, u):
        """Archivos que declaran los campos/propiedades y clases anidadas que `u` lee a través de un receptor tipado."""
        out = []
        stack = [self.roots[u.rel]] if u.rel in self.roots else []
        while stack:
            n = stack.pop()
            stack.extend(n.named_children)
            if u.lang == 'java' and n.type == 'field_access':
                obj, field = n.child_by_field_name('object'), n.child_by_field_name('field')
            elif u.lang == 'kotlin' and n.type == 'navigation_expression' and nav_op(n) != '::':
                kids = n.named_children
                if len(kids) < 2 or kids[-1].type != 'identifier':
                    continue
                obj, field = kids[0], kids[-1]
            elif u.lang == 'kotlin' and n.type == 'infix_expression' and len(n.named_children) == 3 and \
                    n.named_children[1].type == 'identifier':
                # `CONTENT_TYPE of contentType`: llamada infija (sin paréntesis) a una función del proyecto, dependencia
                owner = self.type_of(u, n.named_children[0])
                target = self.on(u, owner, text(n.named_children[1], u.src), 1, n)[0] if owner is not None else None
                rel = self.g.nodes[target]['file'] if target else None
                if rel and rel != u.rel:
                    add(out, rel)
                continue
            else:
                continue
            owner = self.type_of(u, obj) if obj is not None and field is not None else None
            rel = self.home(owner.cid, text(field, u.src), owner.static) if owner is not None and owner.cid else None
            if not rel and owner is not None and u.lang == 'kotlin' and text(field, u.src) in self.ext_props:
                rel = self.ext_prop_home(owner, text(field, u.src))
            if rel and rel != u.rel:
                add(out, rel)
        if u.lang == 'kotlin':
            for rel in self.prop_imports(u):
                add(out, rel)
            names = self.top_prop_names()
            stack = [self.roots[u.rel]] if u.rel in self.roots and names else []
            while stack:  # lectura de una propiedad de nivel superior de otro archivo (`exposedLogger.error(…)`)
                n = stack.pop()
                stack.extend(n.named_children)
                if n.type != 'identifier' or text(n, u.src) not in names:
                    continue
                parent = n.parent
                if parent is None or parent.type in KT_NOT_VALUES or \
                        parent.type == 'navigation_expression' and parent.named_children and parent.named_children[0] != n:
                    continue
                name = text(n, u.src)
                if self.kt_local(u, n, name) is not False or any(t.cid and self.field_type(t.cid, name, 1) is not None
                                                                  for t in self.receivers(u, n)):
                    continue
                rel = self.top_prop_home(u, name)
                if rel and rel != u.rel:
                    add(out, rel)
        return out

    def top_prop_names(self):
        if self.prop_names is None:
            self.prop_names = {name for _, name in self.top_props}
        return self.prop_names

    def ext_prop_home(self, owner, name):
        family = self.ancestors(owner.cid) if owner.cid else []
        for eu, recv, _ in self.ext_props.get(name, ()):
            found = self.resolve_type(eu, recv, recv)
            if found is not None and (found.cid and found.cid in family or not found.cid and not owner.cid and
                                      found.name in ext_family(owner.name)):
                return eu.rel
        return None

    def prop_imports(self, u):
        """Archivos que declaran las propiedades de nivel superior (o de extensión) que `u` importa por nombre."""
        if self.prop_homes is None:
            self.prop_homes = defaultdict(list)
            pkgs = {rel: (x.packages[0] if x.packages else '') for rel, x in self.f.units.items() if x.lang == 'kotlin'}
            for rel, name in self.top_props:
                if rel in pkgs:
                    self.prop_homes[(pkgs[rel], name)].append(rel)
            for name, entries in self.ext_props.items():
                for eu, _, _ in entries:
                    self.prop_homes[(pkgs.get(eu.rel, ''), name)].append(eu.rel)
        out = []
        for kind, value, _ in u.imports:
            pkg, _, name = value.rpartition('.')
            for rel in self.prop_homes.get((pkg, name), ()) if kind == 'fqn' else ():
                if rel != u.rel and rel not in out:
                    out.append(rel)
        return out

    def home(self, cid, name, static):
        for cur in self.ancestors(cid):
            info = self.classes.get(cur)
            if info is None:
                continue
            if name in info['fields']:
                return info['unit'].rel
            companion = info.get('companion')
            if companion and name in self.classes[companion]['fields']:
                return self.classes[companion]['unit'].rel
            if static and name in self.nested[cur]:
                return self.g.nodes[self.nested[cur][name]]['file']
        return None

    # --- llamadas ---

    def method(self, cid, name, argc=None, strict=False):
        """Método `name` de `cid` o de sus bases; con `strict`, solo si alguna sobrecarga admite `argc` argumentos (si
        ninguna lo admite, Kotlin elige antes una extensión aplicable, `fun QueryBuilder.append(vararg x: Any)`)."""
        queue, seen, fallback, overrides = [cid], set(), None, []
        while queue and len(seen) <= MAX_DEPTH:
            cur = queue.pop(0)
            if cur in seen or cur not in self.g.nodes:
                continue
            seen.add(cur)
            meta = self.g.nodes[cur]
            cands = [m for m in self.f.methods.get((meta['name'], name), ()) if self.g.nodes[m]['file'] == meta['file']]
            if cands:
                arities = self.classes.get(cur, {}).get('arity', {}).get(name, ())
                fit = [a for a in arities if argc is not None and fits(a, argc)]
                if argc is None or not arities or fit:
                    # Kotlin: un `override` hereda los valores por defecto del método que redefine (mismo nº de parámetros)
                    same = next((o for o, a in overrides if fit and a[1] == fit[0][1]), None)
                    return same or cands[0]
                overrides += [(cands[0], a) for a in arities if len(a) > 2 and kt_override(a[2])]
                fallback = fallback or cands[0]
            queue.extend(self.l.parents.get(cur, ()))
            companion = self.classes.get(cur, {}).get('companion')
            if companion:
                queue.append(companion)
        return None if strict else fallback

    def ancestors(self, cid):
        out, queue = [], [cid]
        while queue and len(out) <= MAX_DEPTH:
            cur = queue.pop(0)
            if cur not in out:
                out.append(cur)
                queue.extend(self.l.parents.get(cur, ()))
        return out

    def extension(self, owner, name, u=None, at=None, argc=None):
        """Función de extensión `name` aplicable a `owner`; una extensión declarada dentro de una clase (miembro) solo
        se ve desde el cuerpo de esa clase. Con `argc`, antes la que admite ese número de argumentos."""
        if owner is None or name not in self.extensions:
            return None
        family = self.ancestors(owner.cid) if owner.cid else []
        entries = self.extensions[name]
        if argc is not None and len(entries) > 1 and all(e[1].lang == 'kotlin' for e in entries):
            entries = sorted(entries, key=lambda e: not fits(kt_arity(e[3]), argc))
        dispatch = generic = None
        for fid, eu, recv, node in entries:
            home = self.member_ext.get(fid)
            if home and (u is None or at is None or home[0] != u.rel or not home[1] <= at.start_byte < home[2]):
                # fuera del cuerpo de su clase, una extensión miembro se ve si una instancia de la clase es receptor
                # implícito (`queryBuilder { cols.appendTo { … } }`, el cuerpo de una subclase)
                if dispatch is None:
                    dispatch = {a for t in (self.receivers(u, at) if u is not None and at is not None else ()) if t.cid
                                for a in self.ancestors(t.cid)}
                if home[3] not in dispatch:
                    continue
            if not home and u is not None and not self.kt_visible(u, fid, name):
                continue
            bounds = kt_type_param(node, recv, eu.src)
            if bounds is not None:
                # receptor parámetro de tipo (`fun <A> A.valid()`): vale para cualquier receptor que cumpla las cotas;
                # una extensión de receptor concreto, si la hay, va antes
                if generic is None and all(self.fits_bound(eu, node, b, owner, family) for b in bounds):
                    generic = fid
                continue
            found = self.resolve_type(eu, node, recv)
            if found is None:
                continue
            if found.cid and found.cid in family or not found.cid and not owner.cid and found.name in ext_family(owner.name):
                return fid
        return generic

    def fits_bound(self, u, node, bound, owner, family):
        """`owner` cumple la cota `bound` de un parámetro de tipo (`<T : Base>`); una cota de fuera del proyecto
        (`Any`, `Comparable<T>`) no descarta nada."""
        found = self.resolve_type(u, node, bound)
        if found is None or not found.cid:
            return True
        return found.cid in family

    def call(self, u, node, depth=0):
        """(destino, tipo del receptor); destino False = resuelta sin destino del proyecto, None = no se sabe."""
        key = ('call', u.rel, node.id)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = (None, None)
        found = (self.java_call if u.lang == 'java' else self.kt_call)(u, node, depth)
        self.memo[key] = found
        return found

    def java_call(self, u, node, depth):
        t = node.type
        if t == 'object_creation_expression':
            typ = self.resolve_type(u, node, node.child_by_field_name('type'))
            return ((typ.cid or False) if typ is not None else None), None
        if t == 'explicit_constructor_invocation':
            ctor = node.child_by_field_name('constructor')
            here = self.this_type(u, node)
            if ctor is None or here is None or not here.cid:
                return None, None
            if ctor.type == 'this':
                return here.cid, None
            bases = self.l.parents.get(here.cid, ())
            return (bases[0] if bases else False), None
        name = text_of(node.child_by_field_name('name'), u.src)
        args = node.child_by_field_name('arguments')
        argc = sum(1 for a in args.named_children if 'comment' not in a.type) if args is not None else None
        obj = node.child_by_field_name('object')
        if not name:
            return None, None
        if obj is None:
            return self.implicit(u, node, name, argc), None
        return self.on(u, self.type_of(u, obj, depth), name, argc, node)

    def implicit(self, u, node, name, argc):
        kotlin = u.lang == 'kotlin'
        for t in self.receivers(u, node):
            found = self.method(t.cid, name, argc, strict=kotlin) if t.cid else None
            found = found or self.extension(t, name, u, node, argc) or (self.method(t.cid, name, argc) if t.cid and kotlin else None)
            if found:
                return found
        for member, owner in self.statics[u.rel]:
            if member in (name, '*'):
                found = self.method(owner, name, argc)
                if found:
                    return found
        return None

    def on(self, u, owner, name, argc, at=None):
        if owner is None:
            return None, None
        if owner.cid:
            if owner.static:
                inner = self.nested[owner.cid].get(name)
                if inner:
                    return (self.factory(inner, argc, (u, at) if at is not None else None) if u.lang == 'kotlin' else None) or inner, None
            kotlin = u.lang == 'kotlin'
            return (self.method(owner.cid, name, argc, strict=kotlin) or self.extension(owner, name, u, at, argc) or
                    (self.method(owner.cid, name, argc) if kotlin else None) or False), owner
        elem = self.element(owner, name)
        if elem is not None:
            return (self.extension(owner, name, u, at) or False), Elem(elem)
        if owner.args and name in KEEP_ELEMENT and (owner.name in CONTAINERS or owner.name == '[]'):
            return (self.extension(owner, name, u, at) or False), Elem(owner)
        return (self.extension(owner, name, u, at) or False), owner

    def kt_call(self, u, node, depth):
        t = node.type
        if t == 'constructor_invocation':
            typ = self.resolve_type(u, node, next((c for c in node.named_children if c.type in KT_TYPES), None))
            return ((typ.cid or False) if typ is not None else None), None
        if t == 'constructor_delegation_call':
            here = self.this_type(u, node)
            if here is None or not here.cid:
                return None, None
            if text(node, u.src).lstrip().startswith('this'):
                return here.cid, None
            bases = self.l.parents.get(here.cid, ())
            return (bases[0] if bases else False), None
        kids = node.named_children
        callee = kids[0] if kids else None
        if callee is None:
            return None, None
        if callee.type == 'call_expression':
            if any(c.type == 'value_arguments' for c in kids[1:]):
                # `f(a)(b)`: se invoca el resultado de `f(a)` (su `operator fun invoke`)
                inner = self.result(u, callee, depth + 1)
                return (self.invoker(inner) or False) if inner is not None and inner.cid else None, None
            return self.call(u, callee, depth + 1)
        argc = argcount(u, node)
        outer = node.parent
        if outer is not None and outer.type == 'call_expression' and outer.named_children and outer.named_children[0] == node:
            # `f(a, b) { … }` se lee como `(f(a, b)) { … }`: la lambda final también es un argumento de `f`
            argc += sum(1 for c in outer.named_children if c.type == 'annotated_lambda')
        if callee.type == 'identifier':
            name = text(callee, u.src)
            if self.kt_local(u, callee, name) is not False:
                held = self.variable(u, callee, name, depth)
                return (self.invoker(held) if held is not None and held.cid else None) or False, None
            found = self.implicit(u, node, name, argc)
            if found:
                return found, None
            if name in KT_FACTORIES:
                targs = next((c for c in kids if c.type == 'type_arguments'), None)
                types = [next((k for k in p.named_children if k.type in KT_TYPES), None) for p in (targs.named_children if targs is not None else ())]
                return False, Elem(Type(name=KT_FACTORIES[name], args=[(u, node, k) for k in types]))
            funcs = [x for x in self.f.top_by_name.get(name, ()) if self.g.nodes[x]['kind'] == 'function' and self.kt_visible(u, x, name)]
            inner = self.receivers(u, node)[:1]
            if funcs and inner and not inner[0].cid and inner[0].name and \
                    set(funcs) <= {fid for fid, _, _, _ in self.extensions.get(name, ())}:
                # receptor implícito externo (`buildString { append(x) }`) y solo extensiones de otros tipos con ese
                # nombre: ninguna se aplica, la llamada es al miembro del receptor externo
                return False, None
            if funcs and name[:1].isupper() and any(c.type == 'annotated_lambda' for c in kids):
                funcs = [x for x in funcs if self.takes_lambda(x)]
            if name[:1].islower() or not funcs:
                # una propiedad del receptor implícito con `operator fun invoke` va antes que una función de nivel superior
                held = next((t for t in (self.field_type(r.cid, name, depth + 1) for r in self.receivers(u, node) if r.cid)
                             if t is not None), None) if funcs else self.variable(u, callee, name, depth)
                found = self.invoker(held) if held is not None and held.cid and not held.static else None
                if found:
                    return found, None
            typ = self.named_type(u, node, name) if name[:1].isupper() and not funcs else None
            if typ is not None:
                return (self.factory(typ.cid, argc, (u, node)) or typ.cid or False), None
            if not funcs and any(not t.cid for t in self.receivers(u, node)):
                return False, None
            return None, None
        if callee.type == 'navigation_expression':
            parts = callee.named_children
            if len(parts) < 2 or parts[-1].type != 'identifier' or nav_op(callee) == '::':
                return None, None
            name = text(parts[-1], u.src)
            owner = self.type_of(u, parts[0], depth)
            if owner is None or not owner.cid and owner.name == '?':
                # nombre calificado con el paquete (`com.app.decoder.IntDecoder()`): la clase del proyecto
                spelled = ''.join(text(callee, u.src).split())
                qualified = self.fqn_class(spelled) if name[:1].isupper() and spelled[:1].islower() and \
                    self.kt_local(u, parts[0], spelled.split('.', 1)[0]) is False else None
                if qualified:
                    return (self.factory(qualified, argc, (u, node)) or qualified), None
                return self.blind_extension(u, name, argc) or (False if owner is not None else None), None
            target, recv = self.on(u, owner, name, argc, node)
            if owner is not None and owner.cid and not target:
                held = self.member(owner, name, depth)
                found = self.invoker(held) if held is not None and held.cid and not held.static else None
                if found:
                    return found, None
                if owner.static and self.nested[owner.cid].get(name):
                    inner = self.nested[owner.cid][name]
                    return (self.factory(inner, argc) or inner), None
            if owner is not None and name in KT_RETURNS_RECEIVER and not target:
                return False, Elem(owner)
            if owner is not None and not owner.cid and owner.name in KT_TEXT and not target and name not in KT_SAME and \
                    name not in KT_ITERATING and name not in ('use', 'with', 'fold'):
                return False, Elem(owner)
            return target, recv
        return None, None

    def blind_extension(self, u, name, argc):
        """Receptor de tipo desconocido (el retorno de una API externa): la función de extensión del proyecto visible desde
        `u` (importada o del mismo paquete), única con ese nombre y número de argumentos, si ninguna clase del proyecto
        declara un método homónimo."""
        if u.lang != 'kotlin' or name not in self.extensions or self.f.methods_by_name.get(name):
            return None
        found = {fid for fid, _, _, node in self.extensions[name] if not self.member_ext.get(fid) and self.kt_visible(u, fid, name)
                 and (argc is None or fits(kt_arity(node), argc))}
        return found.pop() if len(found) == 1 else None

    def kt_visible(self, u, fid, name):
        """Una función de nivel superior de Kotlin se ve desde el mismo paquete o si se importa (por nombre o con `*`)."""
        other = self.f.units.get(self.g.nodes[fid]['file'])
        if u.lang != 'kotlin' or other is None or other.lang != 'kotlin':
            return True
        pkg = other.packages[0] if other.packages else ''
        if pkg == (u.packages[0] if u.packages else ''):
            return True
        return any(kind == 'fqn' and value == f'{pkg}.{name}' or kind == 'pkg' and value == pkg for kind, value, _ in u.imports)

    def takes_lambda(self, fid):
        """La función acepta una lambda final: su último parámetro es un tipo función."""
        _, types = self.params(fid)
        last = types[-1] if types else None
        while last is not None and last.type in ('nullable_type', 'parenthesized_type'):
            last = next((c for c in last.named_children if c.type in KT_TYPES), None)
        return last is not None and last.type == 'function_type'

    def invoker(self, typ):
        """`operator fun invoke` del tipo de un valor que se llama como función (`lente(x)`, `get(nombre)`)."""
        for cur in self.ancestors(typ.cid):
            meta = self.g.nodes.get(cur)
            found = [m for m in self.f.methods.get((meta['name'], 'invoke'), ()) if self.g.nodes[m]['file'] == meta['file']] \
                if meta else []
            if found:
                return found[0]
        return None

    def factory(self, cid, argc=None, at=None):
        """`Tipo(…)` llama al `operator fun invoke` del companion (o del `object`) si `Tipo` es una interfaz o un objeto,
        o si ningún constructor admite ese número de argumentos y una `invoke` del companion sí."""
        info = self.classes.get(cid)
        node = info['node'] if info else None
        if node is None or info['unit'].lang != 'kotlin':
            return None
        if node.type == 'object_declaration':
            return self.invoker(Type(cid))
        meta = self.g.nodes.get(cid)
        found = [m for m in self.f.methods.get((meta['name'], 'invoke'), ()) if self.g.nodes[m]['file'] == meta['file']]
        if not found:
            return None
        head = text(node, info['unit'].src)[:node.child_by_field_name('name').start_byte - node.start_byte] \
            if node.child_by_field_name('name') is not None else ''
        if re.search(r'\binterface\b', head):
            return found[0]
        invokes = [a for a in info['arity'].get('invoke', ()) if any(x.type == 'companion_object' for x in walk_up(a[2]))]
        inside = at is not None and info['unit'].rel == at[0].rel and node.start_byte <= at[1].start_byte < node.end_byte
        if argc is None or not invokes or any(fits(a, argc) for a in kt_constructors(node, inside)):
            return None
        return found[0] if any(fits(a, argc) for a in invokes) else None


def text_of(node, src):
    return text(node, src) if node is not None else None


def is_var(node, src):
    return node is not None and node.type == 'type_identifier' and text(node, src) == 'var'


def type_name(node, src):
    if node is None:
        return None
    if node.type == 'type_identifier':
        return text(node, src)
    if node.type in ('user_type', 'nullable_type'):
        idents = [c for c in node.named_children if c.type == 'identifier']
        if len(idents) == 1:
            return text(idents[0], src)
        inner = next((c for c in node.named_children if c.type == 'user_type'), None)
        return type_name(inner, src) if inner is not None else None
    return None


def ext_family(name):
    out = {name, name.removeprefix('Mutable')}
    if name in MAPS:
        out |= {'Map', 'MutableMap'}
    elif name in ITERATED:
        out |= {'Iterable', 'Collection', 'MutableIterable', 'MutableCollection'}
        if 'List' in name:
            out |= {'List', 'MutableList'}
        if 'Set' in name:
            out |= {'Set', 'MutableSet'}
    return out


def tparam_bound(node, src, name):
    for clause in node.named_children:
        if clause.type == 'type_parameter_constraints_clause':
            kids = clause.named_children
            if kids and text(kids[0], src) == name:
                bound = next((k.child_by_field_name('type') for k in kids[1:] if k.type == 'type_parameter_constraint'
                              and k.child_by_field_name('type') is not None), None)
                if bound is not None:
                    return bound
    params = node.child_by_field_name('type_parameters')
    if params is None:
        params = next((c for c in node.named_children if c.type == 'type_parameters'), None)
    for p in (params.named_children if params is not None else ()):
        kids = p.named_children
        if kids and kids[0].type in ('type_identifier', 'identifier') and text(kids[0], src) == name:
            for k in kids[1:]:
                if k.type in KT_TYPES:
                    return k
                if k.type == 'type_bound' and k.named_children:
                    return k.named_children[0]
    return None


def fits(arity, argc):
    lo, hi = arity[0], arity[1]
    return lo <= argc and (hi is None or argc <= hi)


def argcount(u, node):
    if u.lang == 'java':
        args = node.child_by_field_name('arguments')
        return sum(1 for a in args.named_children if 'comment' not in a.type) if args is not None else None
    kids = node.named_children
    inner = argcount(u, kids[0]) if kids and kids[0].type == 'call_expression' else 0
    args = next((c for c in kids if c.type == 'value_arguments'), None)
    return (inner or 0) + sum(1 for a in (args.named_children if args is not None else ()) if a.type == 'value_argument') + \
        sum(1 for c in kids if c.type == 'annotated_lambda')


def java_arity(params):
    lo, hi = 0, 0
    for p in (params.named_children if params is not None else ()):
        if p.type == 'formal_parameter':
            lo += 1
            hi = hi if hi is None else hi + 1
        elif p.type == 'spread_parameter':
            hi = None
    return lo, hi


def kt_arity(fn):
    params = next((c for c in fn.named_children if c.type == 'function_value_parameters'), None)
    kids = params.named_children if params is not None else []
    total = sum(1 for c in kids if c.type == 'parameter')
    plain = sum(1 for i, c in enumerate(kids) if c.type == 'parameter' and (i + 1 == len(kids) or kids[i + 1].type in ('parameter', 'parameter_modifiers')))
    vararg = any(c.type == 'parameter_modifiers' and 'vararg' in c.text.decode('utf-8', 'replace') for c in kids)
    return (0 if vararg else plain), (None if vararg else total)


def kt_override(fn):
    mods = next((c for c in fn.named_children if c.type == 'modifiers'), None) if fn is not None else None
    return mods is not None and b'override' in mods.text


def walk_up(node):
    while node is not None:
        yield node
        node = node.parent


def kt_constructors(node, inside=False):
    """Aridades (mínima, máxima) del constructor primario y de los secundarios de una clase Kotlin."""
    out = []
    ctor = next((c for c in node.named_children if c.type == 'primary_constructor'), None)
    params = next((c for c in ctor.named_children if c.type == 'class_parameters'), None) if ctor is not None else None
    kids = [c for c in params.named_children if c.type == 'class_parameter'] if params is not None else []
    private = not inside and ctor is not None and b'private' in ctor.text.split(b'(')[0]
    if not private and (ctor is not None or not any(c.type == 'class_body' and any(x.type == 'secondary_constructor' for x in c.named_children)
                                   for c in node.named_children)):
        vararg = any(b'vararg' in c.text.split(b':')[0] for c in kids)
        plain = sum(1 for c in kids if b'=' not in c.text.split(b':', 1)[-1].split(b'->')[-1])
        out.append((0 if vararg else plain, None if vararg else len(kids)))
    body = next((c for c in node.named_children if c.type == 'class_body'), None)
    out += [kt_arity(c) for c in (body.named_children if body is not None else ()) if c.type == 'secondary_constructor']
    return out


def kt_name(node, src):
    named = node.child_by_field_name('name')
    if named is None and node.type != 'companion_object':
        named = next((c for c in node.named_children if c.type in ('identifier', 'type_identifier', 'simple_identifier')), None)
    return text(named, src) if named is not None else None


def kt_names(node, src):
    if node.type == 'variable_declaration':
        ident = next((c for c in node.named_children if c.type == 'identifier'), None)
        return [text(ident, src)] if ident is not None else []
    return [n for c in node.named_children if c.type == 'variable_declaration' for n in kt_names(c, src)]


def kt_typed(multi, src, name):
    for c in multi.named_children:
        if c.type == 'variable_declaration' and kt_names(c, src) == [name]:
            return next((x for x in c.named_children if x.type in KT_TYPES), None)
    return None


def kt_property(node, src):
    decl = next((c for c in node.named_children if c.type == 'variable_declaration'), None)
    if decl is None:
        return []
    names = kt_names(decl, src)
    typ = next((c for c in decl.named_children if c.type in KT_TYPES), None)
    value = None
    for c in node.named_children:
        if c.start_byte > decl.end_byte and c.type not in ('getter', 'setter', 'modifiers', 'property_delegate', 'type_constraints'):
            value = c
            break
    if value is None:
        getter = next((c for c in node.named_children if c.type == 'getter'), None)
        body = next((c for c in getter.named_children if c.type == 'function_body'), None) if getter is not None else None
        if body is not None and text(body, src).lstrip().startswith('=') and body.named_children:
            value = body.named_children[0]
    if value is None:
        # `val dialect by lazy { … }`: el tipo es el de la última expresión de la lambda
        delegate = next((c for c in node.named_children if c.type == 'property_delegate'), None)
        call = delegate.named_children[0] if delegate is not None and delegate.named_children else None
        callee = call.named_children[0] if call is not None and call.type == 'call_expression' and call.named_children else None
        lam = next((c for c in call.named_children if c.type == 'annotated_lambda'), None) if callee is not None and \
            callee.type == 'identifier' and text(callee, src) == 'lazy' else None
        body = next((c for c in lam.named_children if c.type == 'lambda_literal'), None) if lam is not None else None
        stmts = [c for c in body.named_children if c.type not in ('lambda_parameters', 'line_comment', 'block_comment')] \
            if body is not None else []
        value = stmts[-1] if stmts else None
    return [(n, typ, value) for n in names]


def kt_receiver(fn):
    name = fn.child_by_field_name('name')
    if name is None:
        return None
    for c in fn.named_children:
        if c.start_byte >= name.start_byte:
            return None
        if c.type in KT_TYPES:
            return c
    return None


def kt_type_param(fn, recv, src):
    """Si el receptor de la extensión `fn` es uno de sus parámetros de tipo (`fun <A> A.valid()`, `T?.x()`), las cotas
    de ese parámetro (`<T : Base>`, `where T : Base`); None si el receptor es un tipo concreto."""
    while recv is not None and recv.type in ('nullable_type', 'parenthesized_type', 'non_nullable_type',
                                             'definitely_non_nullable_type'):
        recv = next((c for c in recv.named_children if c.type in KT_TYPES), None)
    if recv is None or recv.type != 'user_type' or len(recv.named_children) != 1 or recv.named_children[0].type != 'identifier':
        return None
    name = text(recv, src)
    params = next((c for c in fn.named_children if c.type == 'type_parameters'), None)
    if params is None:
        return None
    bounds, found = [], False
    for p in params.named_children:
        ident = next((c for c in p.named_children if c.type in ('identifier', 'type_identifier')), None)
        if p.type == 'type_parameter' and ident is not None and text(ident, src) == name:
            found = True
            bounds += [c for c in p.named_children if c.type in KT_TYPES]
    if not found:
        return None
    for group in (c for c in fn.named_children if c.type == 'type_constraints'):
        for con in group.named_children:
            ident = next((c for c in con.named_children if c.type in ('identifier', 'type_identifier')), None)
            if ident is not None and text(ident, src) == name:
                bounds += [c for c in con.named_children if c.type in KT_TYPES]
    return bounds


def kt_prop_receiver(node):
    """Tipo receptor de una propiedad de extensión (`val ASTNode.prevLeaf: ASTNode?`), o None."""
    for c in node.named_children:
        if c.type == 'variable_declaration':
            return None
        if c.type in KT_TYPES:
            return c
    return None


def kt_return(fn):
    params = next((c for c in fn.named_children if c.type == 'function_value_parameters'), None)
    if params is None:
        return None
    for c in fn.named_children:
        if c.start_byte > params.start_byte and c.type in KT_TYPES:
            return c
        if c.type == 'function_body':
            return None
    return None


def nav_op(node):
    return next((c.type for c in node.children if not c.is_named), '.')


def tparams(node, src):
    params = node.child_by_field_name('type_parameters')
    if params is None:
        params = next((c for c in node.named_children if c.type in ('type_parameters', 'type_parameter_list')), None)
    out = []
    for p in (params.named_children if params is not None else ()):
        named = next((c for c in p.named_children if c.type in ('type_identifier', 'identifier')), None)
        if named is not None:
            out.append(text(named, src))
    return out


def base_types(n):
    out = []
    for c in n.named_children:
        if c.type in ('superclass', 'super_interfaces', 'extends_interfaces'):
            out += [k for x in c.named_children for k in (x.named_children if x.type == 'type_list' else [x])]
        elif c.type == 'delegation_specifiers':
            for spec in c.named_children:
                inner = spec.named_children[0] if spec.type == 'delegation_specifier' and spec.named_children else spec
                if inner.type in ('constructor_invocation', 'explicit_delegation'):
                    inner = next((k for k in inner.named_children if k.type in KT_TYPES), None)
                if inner is not None and inner.type in KT_TYPES:
                    out.append(inner)
    return out


def walk_body(body):
    stack = [body] if body is not None else []
    while stack:
        n = stack.pop()
        for c in n.named_children:
            if c.type == 'enum_body_declarations':
                stack.append(c)
            else:
                yield c


def java_pattern(scope, src, name):
    stack = [scope]
    while stack:
        n = stack.pop()
        if n.type == 'instanceof_expression':
            named = n.child_by_field_name('name')
            if named is not None and text(named, src) == name:
                return n.child_by_field_name('right')
        if n.type in ('type_pattern', 'record_pattern_component'):
            kids = n.named_children
            if len(kids) == 2 and kids[1].type == 'identifier' and text(kids[1], src) == name:
                return kids[0]
        if n.type in JAVA_CLASSES or (n.type == 'class_body' and n != scope):
            continue
        stack.extend(n.named_children)
    return None
