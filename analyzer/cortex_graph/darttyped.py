"""Tipos declarados para resolver receptores en Dart.

La gramática de Dart deja las expresiones como secuencias planas
(`p`, `.peek`, `(1)`): aquí se reconstruye la cadena receptor + selectores y se
le da tipo con las anotaciones de campos, parámetros, variables y retornos (o con
el constructor que las inicializa). Si el receptor es una clase del proyecto,
`p.peek(1)` apunta a `BlockParser.peek`; si es de la SDK, a nada del proyecto.
"""
from collections import defaultdict

from .langs import dart_generic_parts, parser_for, text
from .typed import UNKNOWN, Type, ext

MAX_DEPTH = 12
CLASSES = {'class_definition', 'mixin_declaration', 'enum_declaration', 'extension_type_declaration'}
BODIES = {'class_body', 'enum_body', 'extension_body', 'mixin_body'}
FUNC_SIGS = {'function_signature', 'getter_signature', 'setter_signature', 'method_signature', 'constructor_signature',
             'factory_constructor_signature', 'operator_signature'}
CONTAINERS = {'List', 'Iterable', 'Set', 'Queue', 'Future', 'FutureOr', 'Stream', 'Iterator', 'LinkedList'}
MAPS = {'Map', 'HashMap', 'LinkedHashMap', 'SplayTreeMap'}
# supertipos de la SDK de Dart sobre los que se declaran extensiones (`extension … on Iterable<T>`)
SUPERS = {'List': ('List', 'Iterable', 'Object'), 'Set': ('Set', 'Iterable', 'Object'), 'Queue': ('Queue', 'Iterable', 'Object'),
          'Iterable': ('Iterable', 'Object'), 'LinkedList': ('LinkedList', 'Iterable', 'Object'),
          'HashMap': ('HashMap', 'Map', 'Object'), 'LinkedHashMap': ('LinkedHashMap', 'Map', 'Object'),
          'SplayTreeMap': ('SplayTreeMap', 'Map', 'Object'), 'Future': ('Future', 'FutureOr', 'Object'),
          'int': ('int', 'num', 'Comparable', 'Object'), 'double': ('double', 'num', 'Comparable', 'Object'),
          'String': ('String', 'Comparable', 'Pattern', 'Object')}
ELEMENT = {'first', 'last', 'single', 'firstOrNull', 'lastOrNull', 'current', 'removeLast', 'removeAt', 'elementAt',
           'firstWhere', 'lastWhere', 'singleWhere', 'reduce', 'removeFirst'}
KEEP = {'toList', 'toSet', 'where', 'skip', 'take', 'reversed', 'whereType', 'sublist', 'getRange', 'skipWhile',
        'takeWhile', 'followedBy'}
ITERATING = {'forEach', 'map', 'where', 'any', 'every', 'firstWhere', 'lastWhere', 'singleWhere', 'expand',
             'skipWhile', 'takeWhile', 'removeWhere', 'retainWhere', 'sort', 'fold', 'reduce', 'indexWhere'}


class DartTypes:
    def __init__(self, linker):
        self.l, self.g, self.f = linker, linker.g, linker.f
        self.classes = {}
        self.extensions = defaultdict(list)
        self.exports = defaultdict(set)
        self.tops = {}
        self.memo = {}
        self.roots = {}
        for rel in sorted(self.f.units):
            u = self.f.units[rel]
            if u.lang == 'dart':
                root = parser_for('dart').parse(u.src).root_node
                self.roots[rel] = root
                self.scan(u, root)

    # --- registro ---

    def scan(self, u, root):
        for c in root.named_children:
            if c.type == 'import_or_export':
                spec = next((x for x in c.named_children if x.type == 'library_export'), None)
                uri = string_of(spec, u.src) if spec is not None else None
                rel = self.uri_file(u, uri) if uri else None
                if rel:
                    self.exports[u.rel].add(rel)
            elif c.type in ('top_level_variable_declaration', 'static_final_declaration_list', 'initialized_identifier_list'):
                for name, decl in variables(c, u.src) if c.type == 'top_level_variable_declaration' else top_variables(c, u.src):
                    self.tops[(u.rel, name)] = (u, decl)
        stack = [root]
        while stack:
            n = stack.pop()
            if n.type in CLASSES or n.type == 'extension_declaration':
                name = n.child_by_field_name('name')
                name = name or next((x for x in n.named_children if x.type == 'identifier'), None)
                cid = f'c:{u.rel}:{text(name, u.src)}' if name is not None else None
                if cid in self.g.nodes and cid not in self.classes:
                    self.classes[cid] = {'unit': u, 'node': n, 'fields': {}, 'methods': defaultdict(list)}
                    self.class_members(u, n, cid)
            stack.extend(c for c in n.named_children if c.type in CLASSES or c.type in BODIES
                         or c.type in ('program', 'extension_declaration'))

    def uri_file(self, u, uri):
        if uri.startswith('package:'):
            pkg, _, path = uri[len('package:'):].partition('/')
            if self.l.pubs is None:
                self.l.pubs = self.l.find_markers('pubspec.yaml', r'^name:\s*([\w-]+)')
            roots = sorted(d for d, name in self.l.pubs.items() if name == pkg)
            return next((c for c in (f'{d}/lib/{path}'.lstrip('/') for d in roots) if c in self.l.files), None)
        if ':' in uri:
            return None
        found = self.l.norm(u.rel, uri)
        return found if found in self.l.files else None

    def class_members(self, u, n, cid):
        info = self.classes[cid]
        body = n.child_by_field_name('body') or next((c for c in n.named_children if c.type in BODIES), None)
        on = n.child_by_field_name('class') if n.type == 'extension_declaration' else None
        for c in (body.named_children if body is not None else ()):
            sig = c.named_children[0] if c.type in ('method_signature', 'declaration') and c.named_children else c
            if c.type == 'enum_constant':
                name = next((x for x in c.named_children if x.type == 'identifier'), None)
                if name is not None:
                    info['fields'][text(name, u.src)] = ('self', cid)
                continue
            if c.type == 'declaration' and sig.type not in FUNC_SIGS:
                for name, decl in variables(c, u.src):
                    info['fields'][name] = (u, decl)
                continue
            if sig.type == 'getter_signature':
                name = sig.child_by_field_name('name')
                if name is not None:
                    info['fields'][text(name, u.src)] = (u, sig)
            elif sig.type == 'function_signature':
                name = sig.child_by_field_name('name')
                if name is None:
                    continue
                info['methods'][text(name, u.src)].append(sig)
                fid = f'f:{u.rel}:{self.g.nodes[cid]["name"]}.{text(name, u.src)}'
                if on is not None and fid in self.g.nodes:
                    self.extensions[text(name, u.src)].append((fid, u, on))

    # --- tipos ---

    def resolve(self, u, tnode, depth=0):
        """Tipo de un `type_identifier` (con sus `type_arguments` hermanos)."""
        if tnode is None or depth > MAX_DEPTH:
            return UNKNOWN
        if tnode.type == 'void_type':
            return ext('void')
        if tnode.type != 'type_identifier':
            return UNKNOWN
        name = text(tnode, u.src)
        nxt = tnode.next_named_sibling
        if nxt is not None and nxt.type == 'type_identifier' and name in u.aliases:
            cid = self.prefixed(u, name, text(nxt, u.src))
            found, tnode, nxt = (Type(cid) if cid else UNKNOWN), nxt, nxt.next_named_sibling
        else:
            found = self.named_type(u, tnode, name)
        if found is not None and nxt is not None and nxt.type == 'type_arguments':
            found = Type(found.cid, found.name, [(u, a) for a in nxt.named_children if a.type == 'type_identifier'])
        return found

    def named_type(self, u, at, name):
        key = ('type', u.rel, at.id if at is not None else None, name)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = UNKNOWN
        cur = at
        while cur is not None:
            params = next((c for c in cur.named_children if c.type == 'type_parameters'), None)
            if params is not None and any(text(p, u.src).split()[0] == name for p in params.named_children):
                return UNKNOWN
            cur = cur.parent
        found = self.class_in(u, name)
        self.memo[key] = Type(found) if found else (UNKNOWN if name in self.f.classes_by_name else ext(name))
        return self.memo[key]

    def prefixed(self, u, prefix, name):
        """Clase `prefijo.Nombre` de un `import '…' as prefijo`, también reexportada (`export 'src/x.dart'`)."""
        alias = u.aliases.get(prefix)
        seen, queue = set(), list(alias[1]) if alias and alias[0] == 'files' else []
        while queue:
            rel = queue.pop(0)
            if rel in seen:
                continue
            seen.add(rel)
            unit = self.f.units.get(rel)
            cid = unit.top.get(name) if unit is not None else None
            if cid and self.g.nodes[cid]['kind'] == 'class':
                return cid
            queue.extend(sorted(self.exports.get(rel, ())))
        return None

    def class_in(self, u, name):
        found = self.l.type_target(u, name)
        if found:
            return found
        seen, queue = set(), list(u.explicit)
        while queue:
            rel = queue.pop()
            if rel in seen:
                continue
            seen.add(rel)
            unit = self.f.units.get(rel)
            cid = unit.top.get(name) if unit is not None else None
            if cid and self.g.nodes[cid]['kind'] == 'class':
                return cid
            queue.extend(self.exports.get(rel, ()))
        return None

    def arg(self, t, i, depth=0):
        if t is None or i >= len(t.args):
            return UNKNOWN
        if isinstance(t.args[i], Type):
            return t.args[i]
        au, node = t.args[i]
        return self.resolve(au, node, depth + 1)

    def element(self, t, depth=0):
        if t is None or t.cid:
            return UNKNOWN
        if t.name in CONTAINERS:
            return self.arg(t, 0, depth)
        if t.name in MAPS:
            return self.arg(t, 1, depth)
        return UNKNOWN

    # --- expresiones ---

    def chain(self, last):
        """Primario y selectores que terminan en `last` (`p` `.peek` `(1)`)."""
        nodes = [last]
        cur = last.prev_named_sibling
        while cur is not None and nodes[0].type in ('selector', 'cascade_section') and cur.type in ('selector',) + PRIMARIES:
            nodes.insert(0, cur)
            if cur.type != 'selector':
                break
            cur = cur.prev_named_sibling
        return nodes

    def eval(self, u, nodes, depth=0):
        if not nodes or depth > MAX_DEPTH:
            return UNKNOWN
        key = ('chain', u.rel, nodes[-1].id, len(nodes))
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = UNKNOWN
        found = self._eval(u, nodes, depth)
        self.memo[key] = found
        return found

    def _eval(self, u, nodes, depth):
        if nodes[0].type == 'selector':
            return UNKNOWN
        if len(nodes) >= 2 and is_call(nodes[1]):
            target = self.invoke(u, nodes[:2], depth)
            t = self.result(target, depth)
            rest = nodes[2:]
        else:
            t = self.primary(u, nodes[0], depth)
            rest = nodes[1:]
        i = 0
        while i < len(rest) and t is not None:
            sel = rest[i]
            name = member_name(sel, u.src)
            if name and i + 1 < len(rest) and is_call(rest[i + 1]):
                target, extra = self.on(t, name, depth)
                t = extra if isinstance(extra, Type) else self.result(target, depth)
                i += 2
                continue
            if name:
                t = self.member(t, name, depth)
            elif index_selector(sel):
                t = self.element(t, depth)
            elif text(sel, u.src).strip() != '!':
                return UNKNOWN
            i += 1
        return t

    def primary(self, u, n, depth):
        t = n.type
        if t == 'identifier':
            return self.variable(u, n, text(n, u.src), depth)
        if t == 'this':
            return self.this_type(n, u)
        if t == 'super':
            here = self.this_type(n, u)
            bases = self.l.parents.get(here.cid, ()) if here is not None and here.cid else ()
            return Type(bases[0]) if bases else UNKNOWN
        if t in ('const_object_expression', 'new_expression', 'constructor_invocation'):
            return self.resolve(u, next((c for c in n.named_children if c.type == 'type_identifier'), None), depth + 1)
        generic = dart_generic_parts(n.parent, u.src) if t in ('parenthesized_expression', 'record_literal') and \
            n.parent is not None and n.parent.type == 'relational_expression' else None
        if generic is not None and generic[1] == n:
            # `Caja<T>(x).m()`: el receptor es lo que devuelve la llamada genérica
            return self.result(self.generic_target(u, n.parent, generic[0], depth), depth)
        if t == 'parenthesized_expression':
            inner = n.named_children[0] if n.named_children else None
            if inner is not None and inner.type == 'type_cast_expression':
                cast = next((c for c in inner.named_children if c.type == 'type_cast'), None)
                tid = next((c for c in cast.named_children if c.type == 'type_identifier'), None) if cast is not None else None
                return self.resolve(u, tid, depth + 1)
            return self.value(u, inner, depth + 1) if inner is not None else UNKNOWN
        if t in ('string_literal',):
            return ext('String')
        if t == 'list_literal':
            return ext('List')
        return UNKNOWN

    def value(self, u, node, depth=0):
        """Tipo de una expresión que acaba en `node` (último hijo de una secuencia)."""
        if node is None:
            return UNKNOWN
        if node.type == 'selector':
            return self.eval(u, self.chain(node), depth + 1)
        if node.type == 'postfix_expression' and len(node.named_children) == 1:
            node = node.named_children[0]
        if node.type in PRIMARIES:
            return self.primary(u, node, depth + 1)
        return UNKNOWN

    def this_type(self, n, u=None):
        cur = n.parent
        while cur is not None:
            if cur.type in CLASSES or cur.type == 'extension_declaration':
                found = self.cid_of(cur, u)
                if cur.type == 'extension_declaration':
                    holder = self.classes.get(found)
                    on = cur.child_by_field_name('class')
                    return self.resolve(holder['unit'], on) if holder else UNKNOWN
                return Type(found) if found else UNKNOWN
            cur = cur.parent
        return UNKNOWN

    def cid_of(self, n, u):
        name = n.child_by_field_name('name') or next((x for x in n.named_children if x.type == 'identifier'), None)
        cid = f'c:{u.rel}:{text(name, u.src)}' if name is not None and u is not None else None
        return cid if cid in self.classes else None

    def variable(self, u, use, name, depth):
        found = self.local(u, use, name)
        if found is not False:
            return self.decl_type(u, found, depth) if found is not None else UNKNOWN
        cur = use.parent
        while cur is not None:
            if cur.type in CLASSES or cur.type == 'extension_declaration':
                here = self.this_type(use, u)
                found = self.field(here.cid, name, depth) if here is not None and here.cid else None
                if found is not None:
                    return found
                break
            cur = cur.parent
        held = self.tops.get((u.rel, name))
        if held is not None:
            return self.decl_type(held[0], held[1], depth)
        if name[:1].isupper():
            typ = self.named_type(u, use, name)
            return Type(typ.cid, typ.name, static=True) if typ is not None else UNKNOWN
        return UNKNOWN

    def decl_type(self, u, decl, depth):
        if isinstance(decl, tuple):
            kind, node = decl
            if kind == 'iter':
                return self.element(self.value(u, node, depth + 1), depth)
            return UNKNOWN
        if isinstance(decl, Decl):
            tnode, values = decl.type_node(), decl.values()
        else:
            tnode, values = declared_type(decl), decl.children_by_field_name('value')
        if tnode is not None:
            return self.resolve(u, tnode, depth + 1)
        return self.value(u, values[-1], depth + 1) if values else UNKNOWN

    def local(self, u, use, name):
        cur = use.parent
        while cur is not None:
            t = cur.type
            if t in BODIES or t in CLASSES:
                return False
            if t == 'block':
                best = False
                for c in cur.named_children:
                    if c.start_byte >= use.start_byte:
                        break
                    if c.end_byte > use.start_byte:
                        continue
                    if c.type == 'local_variable_declaration':
                        for d in c.named_children:
                            if d.type == 'initialized_variable_definition' and text_of(d.child_by_field_name('name'), u.src) == name:
                                best = d
                if best is not False:
                    return best
            elif t == 'for_statement':
                parts = next((c for c in cur.named_children if c.type == 'for_loop_parts'), None)
                if parts is not None and text_of(parts.child_by_field_name('name'), u.src) == name:
                    values = parts.children_by_field_name('value')
                    return ('iter', values[-1]) if values else None
            elif t == 'function_body':
                sig = cur.prev_named_sibling
                found = params_find(sig, u.src, name)
                if found is not False:
                    return found
            elif t == 'function_expression':
                params = next((c for c in cur.named_children if c.type == 'formal_parameter_list'), None)
                found = params_find(params, u.src, name)
                if found is not False:
                    return found
            cur = cur.parent
        return False

    def field(self, cid, name, depth, seen=None):
        seen = seen or set()
        if cid in seen or depth > MAX_DEPTH:
            return None
        seen.add(cid)
        info = self.classes.get(cid)
        if info is None:
            return None
        held = info['fields'].get(name)
        if held is not None:
            if held[0] == 'self':
                return Type(held[1])
            return self.decl_type(held[0], held[1], depth + 1)
        for base in self.l.parents.get(cid, ()):
            found = self.field(base, name, depth + 1, seen)
            if found is not None:
                return found
        return None

    def member(self, t, name, depth):
        if t.cid:
            found = self.field(t.cid, name, depth)
            if found is not None:
                return found
            return UNKNOWN
        if name in ELEMENT:
            return self.element(t, depth)
        if name in KEEP and t.name in CONTAINERS:
            return t
        if name in ('values', 'keys') and t.name in MAPS:
            return Type(name='Iterable', args=[t.args[1 if name == 'values' else 0]] if len(t.args) == 2 else [])
        return UNKNOWN

    def result(self, target, depth):
        if not target:
            return UNKNOWN
        meta = self.g.nodes[target]
        if meta['kind'] == 'class':
            return Type(target)
        u = self.f.units.get(meta['file'])
        sig = u.fnodes.get(target) if u is not None else None
        if sig is None:
            return UNKNOWN
        if sig.type in ('constructor_signature', 'factory_constructor_signature'):
            owner = self.l.pick(self.f.classes_by_name.get(str(meta['name']).split('.')[0], []), meta['file'])
            return Type(owner) if owner else UNKNOWN
        return self.resolve(u, declared_type(sig), depth + 1)

    # --- llamadas ---

    def method(self, cid, name, seen=None):
        seen = seen or set()
        if cid in seen or len(seen) > MAX_DEPTH or cid not in self.g.nodes:
            return None
        seen.add(cid)
        meta = self.g.nodes[cid]
        cands = [m for m in self.f.methods.get((meta['name'], name), ()) if self.g.nodes[m]['file'] == meta['file']]
        if cands:
            return cands[0]
        for base in self.l.parents.get(cid, ()):
            found = self.method(base, name, seen)
            if found:
                return found
        return None

    def extension(self, t, name):
        family = self.ancestors(t.cid) if t.cid else []
        for fid, eu, on in self.extensions.get(name, ()):
            found = self.resolve(eu, on)
            if found is None:
                continue
            if found.cid and found.cid in family:
                return fid
            if not found.cid and not t.cid and found.name in SUPERS.get(t.name, (t.name,)) and self.same_args(found, t):
                # `extension … on Iterable<StreamSubscription<void>>` sobre un `List<StreamSubscription<T>>`
                return fid
        return None

    def same_args(self, want, have):
        """Los argumentos de tipo conocidos de los dos lados son compatibles (uno sin resolver, como un parámetro de tipo
        o `void`, vale para cualquiera)."""
        for i in range(min(len(want.args), len(have.args))):
            a, b = self.arg(want, i), self.arg(have, i)
            if a is None or b is None or a.name in ('void', 'dynamic', 'Object') and not a.cid:
                continue
            if a.cid or b.cid:
                if not (a.cid and b.cid and a.cid in self.ancestors(b.cid)):
                    return False
            elif a.name not in SUPERS.get(b.name, (b.name,)):
                return False
        return True

    def ancestors(self, cid):
        out, queue = [], [cid]
        while queue and len(out) <= MAX_DEPTH:
            cur = queue.pop(0)
            if cur not in out:
                out.append(cur)
                queue.extend(self.l.parents.get(cur, ()))
        return out

    def on(self, t, name, depth):
        if t is None:
            return None, None
        if t.cid:
            if t.static:
                found = self.method(t.cid, name)
                if found:
                    return found, None
                return self.ctor(t.cid, name), None
            return (self.method(t.cid, name) or self.extension(t, name) or False), None
        found = self.extension(t, name)
        if found:
            return found, None
        if name in ELEMENT:
            return False, self.element(t, depth) or None
        if name in KEEP and t.name in CONTAINERS:
            return False, t
        return False, None

    def ctor(self, cid, name):
        meta = self.g.nodes[cid]
        found = self.f.methods.get((meta['name'], name), ())
        return found[0] if found else cid

    def invoke(self, u, nodes, depth):
        """Destino de `primario(…)`: constructor, variable local invocable, método del receptor implícito."""
        head = nodes[0]
        if head.type != 'identifier':
            return None
        name = text(head, u.src)
        if self.local(u, head, name) is not False:
            return False
        cid = self.class_in(u, name) if name[:1].isupper() else None
        if cid:
            return cid
        here = self.this_type(head, u)
        found = self.method(here.cid, name) if here is not None and here.cid else None
        if found:
            return found
        if here is not None and here.cid is None and here.name:
            found = self.extension(here, name)
            if found:
                return found
        if name[:1].isupper():
            return False if name not in self.f.classes_by_name else None
        return None

    def call(self, u, node, depth=0):
        key = ('call', u.rel, node.id)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = (None, None)
        found = self._call(u, node, depth)
        self.memo[key] = (found, None)
        return self.memo[key]

    def _call(self, u, node, depth):
        if node.type in ('initializer_list_entry', 'redirection'):
            return None
        if node.type == 'relational_expression':
            generic = dart_generic_parts(node, u.src)
            return self.generic_target(u, node, generic[0], depth) if generic else None
        if node.type in ('const_object_expression', 'new_expression', 'constructor_invocation'):
            typ = self.primary(u, node, depth)
            if typ is None:
                return None
            if typ.cid:
                named = [c for c in node.named_children if c.type == 'identifier']
                return self.ctor(typ.cid, text(named[-1], u.src)) if named else typ.cid
            return False
        if node.type == 'cascade_section':
            sel = next((c for c in node.named_children if c.type == 'cascade_selector'), None)
            name = text_of(next((c for c in sel.named_children if c.type == 'identifier'), None), u.src) if sel is not None else None
            first = node
            while first.prev_named_sibling is not None and first.prev_named_sibling.type == 'cascade_section':
                first = first.prev_named_sibling
            base = first.prev_named_sibling
            recv = self.value(u, base, depth) if base is not None else None
            target, _ = self.on(recv, name, depth) if name else (None, None)
            return target
        if node.type == 'selector' and not is_call(node):
            return False
        nodes = self.chain(node)
        if len(nodes) == 2:
            return self.invoke(u, nodes, depth)
        if len(nodes) >= 3:
            name = member_name(nodes[-2], u.src)
            if not name:
                return None
            recv = self.eval(u, nodes[:-2], depth)
            target, _ = self.on(recv, name, depth)
            return target
        return None

    def generic_target(self, u, node, parts, depth):
        """Destino de una llamada genérica `Caja<T>(x)` (la clase) o `Clase.crear<T>(x)` (el miembro estático o el
        constructor con nombre)."""
        head = node.named_children[0].named_children[0]
        if len(parts) == 1:
            if self.local(u, head, parts[0]) is not False:
                return False
            cid = self.class_in(u, parts[0])
            return cid or (False if parts[0] not in self.f.classes_by_name else None)
        target, _ = self.on(self.variable(u, head, parts[0], depth), parts[1], depth)
        return target

    def members(self, u):
        """Archivos que declaran los campos que `u` lee a través de un receptor tipado."""
        out = []
        stack = [self.roots[u.rel]] if u.rel in self.roots else []
        while stack:
            n = stack.pop()
            stack.extend(n.named_children)
            nxt = n.next_named_sibling
            if n.type == 'type_identifier' and nxt is not None and nxt.type == 'type_identifier' and text(n, u.src) in u.aliases:
                cid = self.prefixed(u, text(n, u.src), text(nxt, u.src))
                rel = self.g.nodes[cid]['file'] if cid else None
                if rel and rel != u.rel and rel not in out:
                    out.append(rel)
            if n.type != 'selector':
                continue
            name = member_name(n, u.src)
            nxt = n.next_named_sibling
            if not name or nxt is not None and is_call(nxt):
                continue
            nodes = self.chain(n)
            recv = self.eval(u, nodes[:-1]) if len(nodes) > 1 else None
            if recv is None or not recv.cid:
                continue
            for cid in self.ancestors(recv.cid):
                info = self.classes.get(cid)
                if info is not None and name in info['fields']:
                    rel = info['unit'].rel
                    if rel != u.rel and rel not in out:
                        out.append(rel)
                    break
        return out


PRIMARIES = ('identifier', 'this', 'super', 'const_object_expression', 'new_expression', 'parenthesized_expression',
             'string_literal', 'list_literal', 'record_literal', 'constructor_invocation')


def text_of(node, src):
    return text(node, src) if node is not None else None


def string_of(node, src):
    lit = node
    while lit is not None and lit.type != 'string_literal':
        lit = lit.named_children[0] if lit.named_children else None
    return text(lit, src).strip('\'"') if lit is not None else None


def is_call(node):
    return node is not None and node.type == 'selector' and bool(node.named_children) and node.named_children[0].type == 'argument_part'


def member_name(sel, src):
    if sel.type != 'selector' or not sel.named_children:
        return None
    inner = sel.named_children[0]
    if inner.type in ('unconditional_assignable_selector', 'conditional_assignable_selector'):
        ident = next((c for c in inner.named_children if c.type == 'identifier'), None)
        return text(ident, src) if ident is not None else None
    return None


def index_selector(sel):
    inner = sel.named_children[0] if sel.named_children else None
    return inner is not None and any(c.type == 'index_selector' for c in inner.named_children)


def declared_type(node):
    """`type_identifier` que precede al nombre en una declaración, parámetro o firma."""
    if node is None:
        return None
    name = node.child_by_field_name('name')
    for c in node.named_children:
        if name is not None and c.start_byte >= name.start_byte:
            break
        if c.type in ('type_identifier', 'void_type'):
            return c
    return None


def variables(node, src):
    """(nombre, declaración) de cada variable de un `declaration` de campo o de nivel superior."""
    out = []
    for c in node.named_children:
        if c.type in ('initialized_identifier_list', 'static_final_declaration_list', 'identifier_list'):
            for item in c.named_children:
                ident = item if item.type == 'identifier' else next((x for x in item.named_children if x.type == 'identifier'), None)
                if ident is not None:
                    out.append((text(ident, src), Decl(node, item)))
    return out


def top_variables(node, src):
    """`final Context context = …;` de nivel superior: la gramática deja `final` y el tipo como hermanos de la lista."""
    prev = node.prev_named_sibling
    kind = prev if prev is not None and prev.type == 'type_identifier' else None
    out = []
    for item in node.named_children:
        ident = item if item.type == 'identifier' else next((x for x in item.named_children if x.type == 'identifier'), None)
        if ident is not None:
            out.append((text(ident, src), Decl(node, item, kind)))
    return out


class Decl:
    """Declaración de campo: tipo en el nodo `declaration`, valor en el `initialized_identifier`."""

    def __init__(self, holder, item, kind=None):
        self.holder, self.item, self.kind = holder, item, kind

    def type_node(self):
        if self.kind is not None or self.holder.type != 'top_level_variable_declaration' and self.holder.parent is not None and \
                self.holder.parent.type == 'program':
            return self.kind
        return next((c for c in self.holder.named_children if c.type in ('type_identifier', 'void_type')), None)

    def values(self):
        kids = self.item.named_children
        return kids[1:] if kids and kids[0].type == 'identifier' else []


def params_find(holder, src, name):
    if holder is None:
        return False
    stack = [holder]
    while stack:
        n = stack.pop()
        if n.type == 'formal_parameter':
            ident = n.child_by_field_name('name')
            ctor = next((c for c in n.named_children if c.type in ('constructor_param', 'super_formal_parameter')), None)
            if ctor is not None:
                ident = next((c for c in ctor.named_children if c.type == 'identifier'), None)
                if ident is not None and text(ident, src) == name:
                    return None
            elif ident is None:
                ident = next((c for c in n.named_children if c.type == 'identifier'), None)
            if ident is not None and text(ident, src) == name:
                return n
            continue
        if n.type in ('function_body', 'block'):
            continue
        stack.extend(n.named_children)
    return False
