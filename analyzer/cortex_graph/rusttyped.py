"""Tipos declarados para resolver receptores en Rust.

Rust anota el tipo de cada parámetro, campo y retorno; `let x = T::new()` toma
el tipo del retorno de `new`. Con eso se sabe a qué `impl` pertenece
`x.metodo()`: si el tipo es del proyecto se busca el método en sus `impl` (y en
los rasgos que implementa); si es de la biblioteca estándar o de una
dependencia, la llamada no apunta al proyecto. También se leen las llamadas
dentro de macros (`assert_eq!(a.len(), f(b))`), que el árbol sintáctico deja
como fichas sueltas.
"""
from collections import defaultdict

from .langs import in_macro, parser_for, rust_imports, text
from .typed import UNKNOWN, Pseudo, Type, ext

MAX_DEPTH = 12
TYPE_ITEMS = {'struct_item', 'enum_item', 'union_item', 'trait_item', 'type_item'}
DEREF = {'Box', 'Arc', 'Rc', 'Cow', 'RefCell', 'Mutex', 'RwLock', 'Pin', 'ManuallyDrop', 'MutexGuard', 'Ref', 'RefMut'}
WRAPPERS = {'Option', 'Result', 'Poll'}
SEQUENCES = {'Vec', 'VecDeque', '[]', 'HashSet', 'BTreeSet', 'BinaryHeap', 'LinkedList', 'Iter', 'IntoIter', 'IterMut',
             'Drain', 'Peekable', 'Rev', 'Skip', 'Take', 'Cloned', 'Copied', 'SmallVec', 'IndexSet'}
MAPS = {'HashMap', 'BTreeMap', 'IndexMap'}
UNWRAP = {'unwrap', 'expect', 'unwrap_or', 'unwrap_or_else', 'unwrap_or_default', 'unwrap_unchecked', 'into_inner'}
SAME = {'clone', 'to_owned', 'as_ref', 'as_mut', 'borrow', 'borrow_mut', 'lock', 'read', 'write', 'take', 'cloned',
        'copied', 'by_ref', 'deref', 'deref_mut', 'as_deref', 'as_deref_mut', 'get_ref', 'get_mut_ref'}
ELEMENT_OPTION = {'get', 'get_mut', 'first', 'last', 'first_mut', 'last_mut', 'pop', 'pop_front', 'pop_back', 'next',
                  'next_back', 'peek', 'find', 'max_by_key', 'min_by_key', 'max', 'min', 'nth', 'last_mut'}
ITERATE = {'iter', 'iter_mut', 'into_iter', 'drain', 'values', 'values_mut', 'rev', 'skip', 'take', 'peekable',
           'cloned', 'copied', 'filter', 'chain', 'step_by', 'skip_while', 'take_while', 'inspect', 'by_ref'}
CLOSURE_ELEMENT = {'map', 'for_each', 'filter', 'filter_map', 'flat_map', 'any', 'all', 'find', 'position', 'inspect',
                   'take_while', 'skip_while', 'max_by_key', 'min_by_key', 'sort_by_key', 'sort_unstable_by_key',
                   'retain', 'and_then', 'is_some_and', 'map_or', 'map_or_else', 'find_map', 'partition', 'fold',
                   'sort_by', 'sort_unstable_by', 'max_by', 'min_by', 'dedup_by_key', 'group_by', 'is_ok_and'}
CLOSURE_ERROR = {'map_err', 'or_else', 'unwrap_or_else', 'inspect_err', 'is_err_and'}
LOCAL_SCOPES = {'block', 'source_file', 'declaration_list'}


class RustTypes:
    def __init__(self, linker):
        self.l, self.g, self.f = linker, linker.g, linker.f
        self.classes = {}
        self.methods = defaultdict(list)
        self.memo = {}
        self.roots = {}
        self.impl_of = {}
        self.statics = {}
        for rel in sorted(self.f.units):
            u = self.f.units[rel]
            if u.lang == 'rust':
                root = parser_for('rust').parse(u.src).root_node
                self.roots[rel] = root
                self.scan(u, root)

    # --- registro ---

    def scan(self, u, root):
        stack = [root]
        while stack:
            n = stack.pop()
            if n.type in TYPE_ITEMS:
                name = n.child_by_field_name('name')
                cid = f'c:{u.rel}:{text(name, u.src)}' if name is not None else None
                if cid in self.g.nodes and cid not in self.classes:
                    self.classes[cid] = {'unit': u, 'node': n, 'fields': self.fields(u, n), 'variants': self.variants(u, n),
                                         'alias': n.child_by_field_name('type') if n.type == 'type_item' else None}
            elif n.type in ('const_item', 'static_item'):
                name = n.child_by_field_name('name')
                if name is not None:
                    self.statics.setdefault((u.rel, text(name, u.src)), n.child_by_field_name('type'))
            elif n.type == 'impl_item':
                owner = last_ident(n.child_by_field_name('type'), u.src)
                body = n.child_by_field_name('body')
                for c in (body.named_children if body is not None else ()):
                    if c.type in ('function_item', 'function_signature_item'):
                        name = c.child_by_field_name('name')
                        fid = f'f:{u.rel}:{owner}.{text(name, u.src)}' if name is not None and owner else None
                        if fid in self.g.nodes:
                            self.methods[(owner, text(name, u.src))].append((fid, u, c, n))
                            self.impl_of.setdefault(fid, (u, n))
            elif n.type in ('function_item', 'function_signature_item') and n.parent is not None and n.parent.type == 'declaration_list' and \
                    n.parent.parent is not None and n.parent.parent.type == 'trait_item':
                trait = n.parent.parent.child_by_field_name('name')
                name = n.child_by_field_name('name')
                if trait is not None and name is not None:
                    fid = f'f:{u.rel}:{text(trait, u.src)}.{text(name, u.src)}'
                    if fid in self.g.nodes:
                        self.methods[(text(trait, u.src), text(name, u.src))].append((fid, u, n, n.parent.parent))
            stack.extend(n.named_children)

    def fields(self, u, n):
        out = {}
        body = n.child_by_field_name('body')
        if body is None:
            return out
        if body.type == 'field_declaration_list':
            for c in body.named_children:
                name = c.child_by_field_name('name')
                if c.type == 'field_declaration' and name is not None:
                    out[text(name, u.src)] = c.child_by_field_name('type')
        elif body.type == 'ordered_field_declaration_list':
            for i, c in enumerate(x for x in body.named_children if x.type not in ('visibility_modifier', 'attribute_item')):
                out[str(i)] = c
        return out

    def variants(self, u, n):
        if n.type != 'enum_item':
            return {}
        out = {}
        body = n.child_by_field_name('body')
        for c in (body.named_children if body is not None else ()):
            name = c.child_by_field_name('name')
            if c.type == 'enum_variant' and name is not None:
                fields = c.child_by_field_name('body')
                out[text(name, u.src)] = [x for x in fields.named_children if x.type not in ('visibility_modifier', 'attribute_item')] \
                    if fields is not None and fields.type == 'ordered_field_declaration_list' else []
        return out

    # --- tipos ---

    def resolve_type(self, u, at, node, depth=0):
        if node is None or depth > MAX_DEPTH:
            return UNKNOWN
        if isinstance(node, Pseudo):
            return self.pseudo(u, node, depth)
        t = node.type
        if t in ('reference_type', 'pointer_type'):
            return self.resolve_type(u, at, node.child_by_field_name('type'), depth + 1)
        if t in ('abstract_type', 'dynamic_type'):
            inner = node.child_by_field_name('trait')
            return self.resolve_type(u, at, inner, depth + 1)
        if t == 'primitive_type':
            return ext(text(node, u.src))
        if t == 'array_type':
            return Type(name='[]', args=[(u, at, node.child_by_field_name('element'))])
        if t == 'tuple_type':
            return Type(name='()', args=[(u, at, c) for c in node.named_children])
        if t == 'generic_type':
            base = self.resolve_type(u, at, node.child_by_field_name('type'), depth + 1)
            args = node.child_by_field_name('type_arguments')
            kids = [c for c in (args.named_children if args is not None else ()) if c.type not in ('lifetime', 'type_binding')]
            if base is not None and not base.cid and base.name in DEREF and kids:
                return self.resolve_type(u, at, kids[0], depth + 1)
            if base is not None:
                base = Type(base.cid, base.name, [(u, at, k) for k in kids])
            return base
        if t == 'type_identifier':
            return self.named_type(u, at, text(node, u.src))
        if t == 'scoped_type_identifier':
            return self.path_type(u, at, node, depth)
        return UNKNOWN

    def path_type(self, u, at, node, depth):
        segs = path_segments(node, u.src)
        if not segs:
            return UNKNOWN
        if len(segs) == 1:
            return self.named_type(u, at, segs[0])
        if segs[0] == 'Self':
            return UNKNOWN
        found, rest = self.l.rust_follow(u, segs)
        if found and len(rest) == 1:
            unit = self.f.units.get(found)
            cid = unit.top.get(rest[0]) if unit is not None else None
            if cid and self.g.nodes[cid]['kind'] == 'class':
                return self.dealias(Type(cid))
            return UNKNOWN
        head = segs[0]
        alias = u.aliases.get(head)
        if head in ('crate', 'self', 'super') or alias or self.l.defined(segs[-1]) and not self.l.foreign(u, (head,)):
            return UNKNOWN
        return ext(segs[-1])

    def named_type(self, u, at, name):
        key = ('type', u.rel, at.id if at is not None else None, name)
        if key not in self.memo:
            self.memo[key] = UNKNOWN
            self.memo[key] = self.dealias(self._named_type(u, at, name))
        return self.memo[key]

    def dealias(self, t, depth=0):
        """`type Combinations<I> = CombinationsGeneric<I, Vec<usize>>`: el tipo nombrado es el de la derecha."""
        info = self.classes.get(t.cid) if t is not None and t.cid else None
        if info is None or info.get('alias') is None or depth > MAX_DEPTH:
            return t
        return self.dealias(self.resolve_type(info['unit'], info['alias'], info['alias'], depth + 1), depth + 1)

    def _named_type(self, u, at, name):
        cur = at
        while cur is not None:
            if name == 'Self' and cur.type in ('impl_item', 'trait_item'):
                if cur.type == 'trait_item':
                    named = cur.child_by_field_name('name')
                    return self.named_type(u, cur.parent, text(named, u.src)) if named is not None else UNKNOWN
                return self.resolve_type(u, cur, cur.child_by_field_name('type'))
            bound = generic_bound(cur, u.src, name)
            if bound is not False:
                found = [self.resolve_type(u, cur, b) for b in bound]
                return next((t for t in found if t is not None and t.cid), found[0] if found else UNKNOWN)
            item = self.scoped_use(u, cur, name)
            if item is not None:
                cid = item[0].top.get(item[1])
                return Type(cid) if cid and self.g.nodes[cid]['kind'] == 'class' else UNKNOWN
            cur = cur.parent
        found = self.l.type_target(u, name)
        if found:
            return Type(found)
        local = [c for c in self.f.classes_by_name.get(name, ()) if self.g.nodes[c]['file'] == u.rel]
        if local:
            return Type(local[0])
        if name in self.f.classes_by_name and not self.l.foreign(u, (name,)):
            return UNKNOWN
        return ext(name)

    def scoped_use(self, u, block, name):
        """(unidad, nombre) importado con `use` dentro de un bloque o de un `mod { … }` (no a nivel de archivo)."""
        if block.type not in ('block', 'declaration_list'):
            return None
        for c in block.named_children:
            if c.type != 'use_declaration':
                continue
            for kind, segs, alias in rust_imports(c, u.src):
                if kind == 'rust' and segs and (alias or segs[-1]) == name:
                    found, rest = self.l.rust_follow(u, segs)
                    unit = self.f.units.get(found) if found else None
                    if unit is not None and len(rest) == 1:
                        return unit, rest[0]
                elif kind == 'rustglob' and segs:
                    found, rest = self.l.rust_follow(u, segs)
                    unit = self.f.units.get(found) if found else None
                    if unit is not None and not rest and (name in unit.top or (found, name) in self.statics):
                        return unit, name
        return None

    def static(self, u, use, name, depth):
        cur = use
        while cur is not None:
            item = self.scoped_use(u, cur, name)
            if item is not None:
                typ = self.statics.get((item[0].rel, item[1]))
                return self.resolve_type(item[0], typ, typ, depth + 1) if typ is not None else UNKNOWN
            cur = cur.parent
        typ = self.statics.get((u.rel, name))
        if typ is not None:
            return self.resolve_type(u, typ, typ, depth + 1)
        alias = u.aliases.get(name)
        if alias and alias[0] == 'item':
            typ = self.statics.get((alias[1], alias[2]))
            unit = self.f.units.get(alias[1])
            if typ is not None and unit is not None:
                return self.resolve_type(unit, typ, typ, depth + 1)
        for rel in sorted(u.wide):
            typ = self.statics.get((rel, name))
            if typ is not None:
                return self.resolve_type(self.f.units[rel], typ, typ, depth + 1)
        return UNKNOWN

    def function(self, u, at, name):
        cur = at
        while cur is not None:
            item = self.scoped_use(u, cur, name)
            if item is not None:
                target = item[0].top.get(item[1])
                return target if target and self.g.nodes[target]['kind'] == 'function' else None
            cur = cur.parent
        target, _ = self.l.unqualified(u, None, name)
        return target if target and self.g.nodes[target]['kind'] == 'function' else None

    def arg(self, t, i, depth=0):
        if t is None or i >= len(t.args):
            return UNKNOWN
        if isinstance(t.args[i], Type):
            return t.args[i]
        au, at, node = t.args[i]
        return self.resolve_type(au, at, node, depth + 1)

    def unwrapped(self, t, depth=0):
        if t is not None and not t.cid and t.name in WRAPPERS:
            return self.arg(t, 0, depth)
        return UNKNOWN

    def element(self, t, depth=0):
        if t is None or t.cid:
            return UNKNOWN
        if t.name in SEQUENCES or t.name == 'Option':
            return self.arg(t, 0, depth)
        if t.name in MAPS:
            return Type(name='()', args=list(t.args[:2]))
        return UNKNOWN

    def pseudo(self, u, p, depth):
        if p.kind == 'iter':
            return self.element(self.type_of(u, p.node, depth + 1), depth)
        if p.kind == 'unwrap':
            return self.unwrapped(self.type_of(u, p.node, depth + 1), depth)
        if p.kind == 'closure':
            return self.closure_param(u, p.node, p.index, depth + 1)
        if p.kind == 'tuple':
            return self.arg(self.resolve_type(u, p.node, p.node, depth + 1), p.index, depth)
        if p.kind == 'err':
            t = self.type_of(u, p.node, depth + 1)
            return self.arg(t, 1, depth) if t is not None and t.name == 'Result' else UNKNOWN
        if p.kind == 'variant':
            return self.variant_field(u, p.node, p.index, depth)
        if p.kind == 'field':
            head = p.node.child_by_field_name('type')
            owner = self.resolve_type(u, p.node, head, depth + 1) if head is not None else UNKNOWN
            return self.field_type(u, p.node, owner.cid, p.index, depth) if owner is not None and owner.cid else UNKNOWN
        return UNKNOWN

    def variant_field(self, u, pattern, index, depth):
        head = pattern.child_by_field_name('type')
        if head is None:
            return UNKNOWN
        if head.type == 'scoped_identifier':
            owner = self.path_value(u, head.child_by_field_name('path'), depth)
            cids = [owner.cid] if owner is not None and owner.cid else []
            name = text_of(head.child_by_field_name('name'), u.src)
        else:
            name = text(head, u.src)
            cids = [c for c, info in self.classes.items() if name in info['variants'] and info['unit'].rel == u.rel]
            if not cids:
                cids = [c for c, info in self.classes.items() if name in info['variants'] and self.l.reachable(u, info['unit'].rel)]
        if len(cids) != 1:
            return UNKNOWN
        info = self.classes[cids[0]]
        fields = info['variants'].get(name, [])
        return self.resolve_type(info['unit'], fields[index], fields[index], depth + 1) if index < len(fields) else UNKNOWN

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
        found = self._type_of(u, expr, depth)
        self.memo[key] = found
        return found

    def _type_of(self, u, expr, depth):
        t = expr.type
        if t == 'identifier':
            return self.variable(u, expr, text(expr, u.src), depth)
        if t == 'self':
            return self.named_type(u, expr, 'Self')
        if t in ('reference_expression', 'unary_expression', 'parenthesized_expression'):
            inner = expr.child_by_field_name('value') or (expr.named_children[-1] if expr.named_children else None)
            if t == 'unary_expression' and text(expr, u.src).lstrip().startswith('!'):
                return ext('bool')
            return self.type_of(u, inner, depth + 1)
        if t == 'try_expression':
            return self.unwrapped(self.type_of(u, expr.named_children[0] if expr.named_children else None, depth + 1), depth)
        if t == 'type_cast_expression':
            return self.resolve_type(u, expr, expr.child_by_field_name('type'), depth + 1)
        if t == 'struct_expression':
            return self.struct_type(u, expr, depth)
        if t in ('string_literal', 'raw_string_literal'):
            return ext('str')
        if t in ('integer_literal', 'float_literal', 'boolean_literal', 'char_literal'):
            return ext(t)
        if t == 'field_expression':
            owner = self.type_of(u, expr.child_by_field_name('value'), depth + 1)
            field = expr.child_by_field_name('field')
            if owner is None or field is None:
                return UNKNOWN
            name = text(field, u.src)
            if owner.cid:
                return self.field_type(u, expr, owner.cid, name, depth)
            if owner.name == '()' and name.isdigit():
                return self.arg(owner, int(name), depth)
            return UNKNOWN
        if t == 'index_expression':
            owner = self.type_of(u, expr.named_children[0] if expr.named_children else None, depth + 1)
            if owner is not None and not owner.cid and owner.name in MAPS:
                return self.arg(owner, 1, depth)
            return self.element(owner, depth)
        if t == 'call_expression':
            target, owner = self.call(u, expr, depth + 1)
            if isinstance(owner, Result):
                return owner.type
            if target and self.g.nodes[target]['kind'] == 'class':
                return Type(target)
            if target:
                return self.returns(target, depth + 1)
            return UNKNOWN
        if t == 'macro_invocation':
            name = text_of(expr.child_by_field_name('macro'), u.src)
            return ext('String') if name in ('format', 'concat') else (ext('Vec') if name == 'vec' else UNKNOWN)
        if t == 'scoped_identifier':
            path = expr.child_by_field_name('path')
            owner = self.path_value(u, path, depth) if path is not None else None
            name = text_of(expr.child_by_field_name('name'), u.src)
            if owner is not None and owner.cid and name in self.classes.get(owner.cid, {}).get('variants', ()):
                return Type(owner.cid)
            return UNKNOWN
        return UNKNOWN

    def field_type(self, u, at, cid, name, depth):
        """Tipo del campo `name`; si es un parámetro genérico del struct (`f: F`), sus cotas salen del `impl` o la
        función donde se usa, que por convención repite los nombres (`impl<I, F: Pred> … for Coalesce<I, F>`)."""
        info = self.classes.get(cid)
        node = info.get('fields', {}).get(name) if info is not None else None
        if node is None:
            return UNKNOWN
        concrete = self.impl_argument(u, at, info, node) if node.type == 'type_identifier' else None
        if concrete is not None:
            return self.resolve_type(u, concrete, concrete, depth + 1)
        if node.type == 'type_identifier' and generic_bound(info['node'], info['unit'].src, text(node, info['unit'].src)) is not False:
            found = self.named_type(u, at, text(node, info['unit'].src))
            if found is not None:
                return found
        return self.resolve_type(info['unit'], node, node, depth + 1)

    def impl_argument(self, u, at, info, node):
        """Argumento concreto del parámetro genérico `node` del struct en el `impl` que rodea `at`
        (`impl<P> Iterator for FilterEntry<IntoIter, P>`: `I` es `IntoIter`)."""
        params = info['node'].child_by_field_name('type_parameters')
        names = [text(p.child_by_field_name('name') or p, info['unit'].src) for p in (params.named_children if params else ())
                 if p.type in ('type_parameter', 'constrained_type_parameter', 'type_identifier')]
        word = text(node, info['unit'].src)
        impl = at
        while impl is not None and impl.type != 'impl_item':
            impl = impl.parent
        kind = impl.child_by_field_name('type') if impl is not None else None
        args = kind.child_by_field_name('type_arguments') if kind is not None and kind.type == 'generic_type' else None
        own = impl.child_by_field_name('type_parameters') if impl is not None else None
        local = {text(p.child_by_field_name('name') or p, u.src) for p in (own.named_children if own else ())}
        kids = [c for c in (args.named_children if args else ()) if c.type not in ('lifetime',)]
        if word not in names or len(kids) != len(names):
            return None
        hit = kids[names.index(word)]
        return hit if text(hit, u.src) not in local else None

    def literal_target(self, u, expr, depth):
        """Tipo que instancia `Tipo { … }` tal como se nombra (un alias es su propio destino); construir una variante de
        enum (`Estado::Inicio { … }`) no es instanciar el enum."""
        name = expr.child_by_field_name('name')
        if name is not None and name.type == 'type_identifier' and text(name, u.src) != 'Self':
            typ = self._named_type(u, expr, text(name, u.src))
            return (typ.cid or False) if typ is not None else None
        if name is not None and name.type == 'scoped_type_identifier':
            owner = self.path_value(u, name.child_by_field_name('path'), depth)
            if owner is not None and owner.cid and text_of(name.child_by_field_name('name'), u.src) in self.classes.get(owner.cid, {}).get('variants', ()):
                return False
        typ = self.struct_type(u, expr, depth)
        return (typ.cid or False) if typ is not None else None

    def struct_type(self, u, expr, depth):
        name = expr.child_by_field_name('name')
        if name is None:
            return UNKNOWN
        if name.type == 'scoped_type_identifier':
            path = name.child_by_field_name('path')
            owner = self.path_value(u, path, depth) if path is not None else None
            last = text_of(name.child_by_field_name('name'), u.src)
            if owner is not None and owner.cid and last in self.classes.get(owner.cid, {}).get('variants', ()):
                return Type(owner.cid)
        return self.resolve_type(u, expr, name, depth + 1)

    def path_value(self, u, path, depth):
        """Tipo nombrado por el prefijo de una ruta `A::b` (solo si `A` es un tipo)."""
        if path is None:
            return None
        if path.type == 'identifier':
            name = text(path, u.src)
            if name == 'Self' or name[:1].isupper():
                return self.named_type(u, path, name)
            return None
        if path.type == 'generic_type':
            return self.resolve_type(u, path, path, depth + 1)
        if path.type == 'scoped_identifier':
            segs = path_segments(path, u.src)
            if segs and segs[-1][:1].isupper():
                found, rest = self.l.rust_follow(u, segs)
                if found and len(rest) == 1:
                    unit = self.f.units.get(found)
                    cid = unit.top.get(rest[0]) if unit is not None else None
                    return self.dealias(Type(cid)) if cid and self.g.nodes[cid]['kind'] == 'class' else None
                if segs[0] not in ('crate', 'self', 'super') and segs[0] not in u.aliases and not self.l.defined(segs[-1]):
                    return ext(segs[-1])
        return None

    def variable(self, u, use, name, depth):
        found = self.local(u, use, name)
        if found is False:
            typ = self.static(u, use, name, depth)
            if typ is not None:
                return typ
            if name[:1].isupper():
                typ = self.named_type(u, use, name)
                return Type(typ.cid, typ.name, static=True) if typ is not None else UNKNOWN
            return UNKNOWN
        if found is None:
            return UNKNOWN
        typ, value = found
        if typ is not None:
            return self.resolve_type(u, use, typ, depth + 1)
        return self.type_of(u, value, depth + 1) if value is not None else UNKNOWN

    def local(self, u, use, name):
        prev, cur = use, use.parent
        while cur is not None:
            t = cur.type
            if t in LOCAL_SCOPES:
                best = False
                for c in cur.named_children:
                    if c.start_byte >= use.start_byte:
                        break
                    if c.end_byte > use.start_byte:
                        continue
                    if c.type == 'let_declaration':
                        found = bind(c.child_by_field_name('pattern'), u.src, name, c.child_by_field_name('type'),
                                     c.child_by_field_name('value'))
                        if found is not False:
                            best = found
                if best is not False:
                    return best
            elif t == 'for_expression' and prev == cur.child_by_field_name('body'):
                found = bind(cur.child_by_field_name('pattern'), u.src, name, None, Pseudo('iter', cur.child_by_field_name('value')))
                if found is not False:
                    return found
            elif t in ('if_expression', 'while_expression') and prev != cur.child_by_field_name('condition'):
                cond = cur.child_by_field_name('condition')
                found = self.let_condition(u, cond, name)
                if found is not False:
                    return found
            elif t == 'let_chain':
                for c in cur.named_children:
                    if c.type == 'let_condition' and c.end_byte <= use.start_byte:
                        found = self.let_condition(u, c, name)
                        if found is not False:
                            return found
            elif t == 'match_arm':
                pattern = cur.child_by_field_name('pattern')
                block = cur.parent.parent if cur.parent is not None else None
                value = block.child_by_field_name('value') if block is not None and block.type == 'match_expression' else None
                found = bind(pattern, u.src, name, None, value, match=True)
                if found is not False:
                    return found
            elif t == 'closure_expression':
                params = cur.child_by_field_name('parameters')
                for i, p in enumerate(params.named_children if params is not None else ()):
                    if p.type == 'identifier' and text(p, u.src) == name:
                        return (None, Pseudo('closure', cur, i))
                    if p.type == 'parameter':
                        found = bind(p.child_by_field_name('pattern'), u.src, name, p.child_by_field_name('type'),
                                     Pseudo('closure', cur, i))
                        if found is not False:
                            return found
                    elif bind(p, u.src, name, None, None) is not False:
                        return None
            elif t == 'function_item':
                params = cur.child_by_field_name('parameters')
                for p in (params.named_children if params is not None else ()):
                    if p.type == 'parameter':
                        found = bind(p.child_by_field_name('pattern'), u.src, name, p.child_by_field_name('type'), None)
                        if found is not False:
                            return found
                return False
            prev, cur = cur, cur.parent
        return False

    def let_condition(self, u, cond, name):
        if cond is None:
            return False
        if cond.type == 'let_chain':
            for c in cond.named_children:
                found = self.let_condition(u, c, name)
                if found is not False:
                    return found
            return False
        if cond.type != 'let_condition':
            return False
        return bind(cond.child_by_field_name('pattern'), u.src, name, None, cond.child_by_field_name('value'), match=True)

    def returns(self, fid, depth):
        held = self.declaration(fid)
        if held is None:
            return UNKNOWN
        u, node = held
        return self.resolve_type(u, node, node.child_by_field_name('return_type'), depth + 1)

    def declaration(self, fid):
        meta = self.g.nodes.get(fid) or {}
        u = self.f.units.get(meta.get('file'))
        node = u.fnodes.get(fid) if u is not None else None
        return (u, node) if node is not None else None

    def closure_param(self, u, closure, index, depth):
        args = closure.parent
        call = args.parent if args is not None and args.type == 'arguments' else None
        if call is None or call.type != 'call_expression':
            return UNKNOWN
        fn = call.child_by_field_name('function')
        if fn is not None and fn.type == 'generic_function':
            fn = fn.child_by_field_name('function')
        if fn is None or fn.type != 'field_expression':
            return UNKNOWN
        name = text_of(fn.child_by_field_name('field'), u.src)
        recv = self.type_of(u, fn.child_by_field_name('value'), depth + 1)
        if recv is not None and recv.cid:
            found, _ = self.on(recv, name, depth + 1)
            return self.fn_bound_param(found, list(args.named_children).index(closure), index, depth) if found else UNKNOWN
        if recv is None:
            return UNKNOWN
        if name in CLOSURE_ERROR and recv.name == 'Result':
            return self.arg(recv, 1, depth) if index == 0 else UNKNOWN
        if name in CLOSURE_ELEMENT:
            if name == 'fold':
                return self.element(recv, depth) if index == 1 else UNKNOWN
            if name in ('sort_by', 'sort_unstable_by', 'max_by', 'min_by'):
                return self.element(recv, depth)
            return self.element(recv, depth) if index == 0 else UNKNOWN
        return UNKNOWN

    def fn_bound_param(self, fid, arg, index, depth):
        """Tipo del parámetro `index` de la clausura que recibe el argumento `arg` de un método del proyecto, por la cota
        del genérico (`F: FnMut(&DirEntry) -> bool`, también en `where`) o por `impl Fn(&T)`."""
        held = self.declaration(fid)
        if held is None:
            return UNKNOWN
        u, node = held
        params = [p for p in (node.child_by_field_name('parameters').named_children if node.child_by_field_name('parameters') else ())
                  if p.type == 'parameter']
        kind = params[arg].child_by_field_name('type') if arg < len(params) else None
        if kind is not None and kind.type == 'abstract_type':
            kind = next((c for c in kind.named_children if c.type == 'function_type'), kind)
        if kind is not None and kind.type == 'type_identifier':
            word = text(kind, u.src)
            preds = [c for c in node.named_children if c.type == 'where_clause'] + \
                [c for c in (node.child_by_field_name('type_parameters').named_children if node.child_by_field_name('type_parameters') else ())]
            for pred in (x for c in preds for x in ([c] if c.type != 'where_clause' else c.named_children)):
                left = pred.child_by_field_name('left') or pred.child_by_field_name('name')
                bounds = pred.child_by_field_name('bounds')
                if left is not None and text(left, u.src) == word and bounds is not None:
                    kind = next((c for c in bounds.named_children if c.type == 'function_type'), None)
                    break
        if kind is None or kind.type != 'function_type':
            return UNKNOWN
        inner = kind.child_by_field_name('parameters') or next((c for c in kind.named_children if c.type == 'parameters'), None)
        types = [c for c in (inner.named_children if inner is not None else ())]
        if index >= len(types):
            return UNKNOWN
        typ = types[index]
        while typ.type == 'reference_type' and typ.named_children:
            typ = next((c for c in typ.named_children if c.type not in ('lifetime', 'mutable_specifier')), typ)
            if typ.type != 'reference_type':
                break
        return self.resolve_type(u, node, typ, depth + 1)

    # --- llamadas ---

    def owner_cid(self, fid):
        held = self.impl_of.get(fid)
        if held is None:
            return None
        key = ('impl', fid)
        if key not in self.memo:
            u, impl = held
            found = self.resolve_type(u, impl, impl.child_by_field_name('type'))
            self.memo[key] = found.cid if found is not None else None
        return self.memo[key]

    def method(self, cid, name, seen=None):
        seen = seen or set()
        if cid in seen or len(seen) > MAX_DEPTH or cid not in self.g.nodes:
            return None
        seen.add(cid)
        cands = self.methods.get((self.g.nodes[cid]['name'], name), ())
        exact = [fid for fid, _, _, _ in cands if fid in self.impl_of and self.owner_cid(fid) == cid]
        exact = exact or [fid for fid, cu, _, holder in cands if holder.type == 'trait_item' and f'c:{cu.rel}:{self.g.nodes[cid]["name"]}' == cid]
        if exact:
            return exact[0]
        for base in self.l.parents.get(cid, ()):
            found = self.method(base, name, seen)
            if found:
                return found
        return None

    def call(self, u, node, depth=0):
        """(destino, extra); destino False = resuelta sin destino del proyecto, None = no se sabe."""
        key = ('call', u.rel, node.id)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = (None, None)
        found = self._call(u, node, depth)
        self.memo[key] = found
        return found

    def _call(self, u, node, depth):
        t = node.type
        if t == 'struct_expression':
            return self.literal_target(u, node, depth), None
        if t == 'token_tree':
            return self.macro_call(u, node, depth)
        fn = node.child_by_field_name('function')
        if fn is not None and fn.type == 'generic_function':
            fn = fn.child_by_field_name('function')
        if fn is None:
            return None, None
        if fn.type == 'identifier':
            if self.local(u, fn, text(fn, u.src)) is not False:
                return False, None
            return self.function(u, fn, text(fn, u.src)), None
        if fn.type == 'scoped_identifier':
            owner = self.path_value(u, fn.child_by_field_name('path'), depth)
            name = text_of(fn.child_by_field_name('name'), u.src)
            if owner is None:
                return self.module_fn(u, fn), None
            return self.on(owner, name, depth, static=True)
        if fn.type == 'field_expression':
            field = fn.child_by_field_name('field')
            if field is None or field.type != 'field_identifier':
                return None, None
            owner = self.type_of(u, fn.child_by_field_name('value'), depth)
            return self.on(owner, text(field, u.src), depth)
        return None, None

    def module_fn(self, u, path):
        segs = path_segments(path, u.src)
        if len(segs) < 2 or segs[0] == 'Self':
            return None
        found, rest = self.l.rust_follow(u, segs)
        unit = self.f.units.get(found) if found else None
        target = unit.top.get(rest[0]) if unit is not None and len(rest) == 1 else None
        return target if target and self.g.nodes[target]['kind'] == 'function' else None

    def on(self, owner, name, depth, static=False):
        if owner is None or not name:
            return None, None
        if owner.cid:
            if static and name in self.classes.get(owner.cid, {}).get('variants', ()):
                return False, Result(Type(owner.cid))
            found = self.method(owner.cid, name)
            if found:
                return found, None
            if name in SAME:
                return False, Result(Type(owner.cid))
            return False, None
        if name in UNWRAP and owner.name in WRAPPERS:
            return False, Result(self.unwrapped(owner, depth))
        if name in SAME:
            return False, Result(owner)
        if name in ('ok', 'err') and owner.name == 'Result':
            return False, Result(Type(name='Option', args=[owner.args[0 if name == 'ok' else 1]] if len(owner.args) > 1 else ()))
        if name in ELEMENT_OPTION and (owner.name in SEQUENCES or owner.name in MAPS):
            inner = self.arg(owner, 1, depth) if owner.name in MAPS else self.element(owner, depth)
            return False, Result(Type(name='Option', args=[inner] if inner is not None else ()))
        if name in ITERATE and (owner.name in SEQUENCES or owner.name in MAPS or owner.name == 'Option'):
            if owner.name in MAPS:
                return False, Result(Type(name='Iter', args=[owner.args[1]] if name.startswith('values') and len(owner.args) > 1 else []))
            inner = self.element(owner, depth)
            return False, Result(Type(name='Iter', args=[inner] if inner is not None else ()))
        if name == 'iter' and owner.name in MAPS:
            return False, None
        return False, None

    def macro_call(self, u, node, depth):
        """Llamada `f(…)`, `A::f(…)` o `x.f(…)` escrita como fichas dentro de una macro."""
        prev = node.prev_sibling
        if prev is None or prev.type != 'identifier' or not in_macro(node):
            return None, None
        name = text(prev, u.src)
        dot = prev.prev_sibling
        if dot is not None and dot.type == '.':
            owner = self.token_chain(u, dot.prev_sibling, depth)
            return self.on(owner, name, depth) if owner is not None else (None, None)
        if dot is not None and dot.type == '::':
            head = dot.prev_sibling
            if head is not None and head.type == 'identifier' and (text(head, u.src)[:1].isupper() or text(head, u.src) == 'Self'):
                owner = self.named_type(u, node, text(head, u.src))
                return self.on(owner, name, depth, static=True)
            return None, None
        if self.local(u, node, name) is not False:
            return False, None
        return None, None

    def token_chain(self, u, tok, depth):
        """Tipo de la expresión `a.b.c` o `a.b()` que termina en la ficha `tok`."""
        if tok is None or depth > MAX_DEPTH:
            return UNKNOWN
        if tok.type == 'self':
            return self.named_type(u, tok, 'Self')
        if tok.type == 'token_tree':
            call_name = tok.prev_sibling
            if call_name is None or call_name.type != 'identifier':
                return UNKNOWN
            target, extra = self.macro_call(u, tok, depth + 1)
            if isinstance(extra, Result):
                return extra.type
            return self.returns(target, depth + 1) if target else UNKNOWN
        if tok.type == 'identifier':
            dot = tok.prev_sibling
            if dot is not None and dot.type == '.':
                owner = self.token_chain(u, dot.prev_sibling, depth + 1)
                if owner is None or not owner.cid:
                    return UNKNOWN
                info = self.classes.get(owner.cid, {})
                node = info.get('fields', {}).get(text(tok, u.src))
                return self.resolve_type(info['unit'], node, node, depth + 1) if node is not None else UNKNOWN
            if dot is not None and dot.type == '::':
                return UNKNOWN
            return self.variable(u, tok, text(tok, u.src), depth + 1)
        return UNKNOWN

    # --- accesos a campos ---

    def members(self, u):
        """Archivos que declaran los structs cuyos campos lee `u` a través de un receptor tipado."""
        out = []
        stack = [self.roots[u.rel]] if u.rel in self.roots else []
        while stack:
            n = stack.pop()
            stack.extend(n.named_children)
            if n.type != 'field_expression':
                continue
            field = n.child_by_field_name('field')
            parent = n.parent
            if field is None or field.type != 'field_identifier' or parent is not None and parent.type == 'call_expression' \
                    and parent.child_by_field_name('function') == n:
                continue
            owner = self.type_of(u, n.child_by_field_name('value'))
            if owner is not None and owner.cid and text(field, u.src) in self.classes.get(owner.cid, {}).get('fields', {}):
                rel = self.g.nodes[owner.cid]['file']
                if rel != u.rel and rel not in out:
                    out.append(rel)
        return out


class Result:
    """Tipo del valor que devuelve un método externo conocido (`unwrap`, `iter`, `clone`…)."""

    def __init__(self, type_):
        self.type = type_


def text_of(node, src):
    return text(node, src) if node is not None else None


def last_ident(node, src):
    if node is None:
        return None
    if node.type == 'generic_type':
        return last_ident(node.child_by_field_name('type'), src)
    if node.type in ('reference_type', 'pointer_type'):
        return last_ident(node.child_by_field_name('type'), src)
    if node.type == 'scoped_type_identifier':
        return last_ident(node.child_by_field_name('name'), src)
    if node.type == 'type_identifier':
        return text(node, src)
    return None


def path_segments(node, src):
    if node is None:
        return []
    if node.type in ('identifier', 'type_identifier', 'crate', 'self', 'super'):
        return [text(node, src)]
    if node.type in ('scoped_identifier', 'scoped_type_identifier'):
        return path_segments(node.child_by_field_name('path'), src) + path_segments(node.child_by_field_name('name'), src)
    if node.type == 'generic_type':
        return path_segments(node.child_by_field_name('type'), src)
    return []


def generic_bound(node, src, name):
    """Primer rasgo que acota el parámetro genérico `name` declarado en `node` (False si no lo declara)."""
    params = node.child_by_field_name('type_parameters')
    found = False
    for p in (params.named_children if params is not None else ()):
        pname = p.child_by_field_name('name') if p.type in ('type_parameter', 'constrained_type_parameter') else None
        if pname is None and p.type == 'constrained_type_parameter':
            pname = p.child_by_field_name('left')
        if pname is None and p.type == 'type_identifier':
            pname = p
        if pname is not None and text(pname, src) == name:
            found = all_bounds(p.child_by_field_name('bounds'))
            break
    if found is False:
        return False
    where = next((c for c in node.named_children if c.type == 'where_clause'), None)
    for pred in (where.named_children if where is not None else ()):
        left = pred.child_by_field_name('left')
        if left is not None and text(left, src) == name:
            found += all_bounds(pred.child_by_field_name('bounds'))
    return found


def all_bounds(bounds):
    """Rasgos de una cota (`T: Clone + Pred<X>`), en orden."""
    return [c for c in (bounds.named_children if bounds is not None else ())
            if c.type in ('type_identifier', 'scoped_type_identifier', 'generic_type')]


def plain_ident(node):
    while node is not None and node.type in ('ref_pattern', 'mut_pattern'):
        node = next((c for c in node.named_children if c.type != 'mutable_specifier'), None)
    return node if node is not None and node.type == 'identifier' else None


def bind(pattern, src, name, typ, value, match=False):
    """(tipo, valor) del nombre `name` ligado por `pattern`; None si se liga sin tipo conocido; False si no lo liga."""
    if pattern is None:
        return False
    t = pattern.type
    if t == 'identifier':
        return (typ, value) if text(pattern, src) == name else False
    if t == 'mut_pattern' or t == 'ref_pattern' or t == 'match_pattern':
        inner = next((c for c in pattern.named_children if c.type != 'mutable_specifier'), None)
        return bind(inner, src, name, typ, value, match)
    if t == 'tuple_struct_pattern':
        head = pattern.child_by_field_name('type')
        kids = [c for c in pattern.named_children if c != head]
        word = text(head, src) if head is not None else ''
        for i, k in enumerate(kids):
            ident = plain_ident(k)
            if ident is None or text(ident, src) != name:
                continue
            if word in ('Some', 'Ok') and len(kids) == 1:
                return (None, Pseudo('unwrap', value)) if value is not None and not isinstance(value, Pseudo) else None
            if word == 'Err' and len(kids) == 1:
                return (None, Pseudo('err', value)) if value is not None and not isinstance(value, Pseudo) else None
            return (None, Pseudo('variant', pattern, i))
        return None if any(bind(k, src, name, None, None) is not False for k in kids) else False
    if t == 'struct_pattern':
        for field in pattern.named_children:
            if field.type != 'field_pattern':
                continue
            key = field.child_by_field_name('name')
            inner = field.child_by_field_name('pattern')
            if inner is None and key is not None and text(key, src) == name:
                return (None, Pseudo('field', pattern, name))
            if inner is not None and plain_ident(inner) is not None and text(plain_ident(inner), src) == name and key is not None:
                return (None, Pseudo('field', pattern, text(key, src)))
            if inner is not None and bind(inner, src, name, None, None) is not False:
                return None
        return False
    if t == 'tuple_pattern' and typ is None and value is not None and not isinstance(value, Pseudo) and value.type == 'tuple_expression':
        kids = value.named_children
        for i, k in enumerate(pattern.named_children):
            if plain_ident(k) is not None and text(plain_ident(k), src) == name:
                return (None, kids[i]) if i < len(kids) else None
    if t == 'tuple_pattern' and typ is not None:
        for i, k in enumerate(pattern.named_children):
            if k.type == 'identifier' and text(k, src) == name:
                return (Pseudo('tuple', typ, i), None)
    for c in pattern.named_children:
        if c.type == 'identifier' and text(c, src) == name and t not in ('scoped_identifier',):
            return None
        if c.type not in ('identifier', 'type_identifier', 'scoped_identifier') and bind(c, src, name, None, None) is not False:
            return None
    return False

