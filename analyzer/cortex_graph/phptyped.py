"""Tipos declarados para resolver receptores en PHP.

PHP 7.4+ declara tipos en propiedades, parámetros (también los promovidos en el
constructor) y retornos; sin ellos valen los de PHPDoc (`@var`, `@param`,
`@return`). Con ellos, `$this->formatter->format()` se resuelve al método de la
clase o interfaz declarada (o de sus bases y traits); si el tipo es de PHP o de
una dependencia, la llamada no apunta al proyecto.
"""
import re

from .langs import parser_for, php_magic_methods, text
from .typed import UNKNOWN, Type, ext

MAX_DEPTH = 12
CLASSES = {'class_declaration', 'interface_declaration', 'trait_declaration', 'enum_declaration'}
FUNCTIONS = {'method_declaration', 'function_definition', 'anonymous_function', 'arrow_function'}
BUILTIN = {'string', 'int', 'float', 'bool', 'array', 'iterable', 'callable', 'mixed', 'void', 'null', 'false', 'true',
           'object', 'never', 'resource'}
MEMBER_CALLS = {'member_call_expression', 'nullsafe_member_call_expression'}
MEMBER_READS = {'member_access_expression', 'nullsafe_member_access_expression'}
DOC_PROPERTY = re.compile(r'@property(?:-read|-write)?\s+([^\s*]+)\s+\$(\w+)')
DOC_TAG = re.compile(r'@(var|param|return)\s+([^\s*]+)(?:\s+(\$\w+))?')


class DocType(str):
    """Tipo escrito en un comentario PHPDoc (`UriInterface|string`)."""


def docblock(node, src, tag, var=None):
    """Tipo de `@tag` (de `@param T $var` si se da `var`) en el comentario `/** … */` que precede a `node`."""
    prev = node.prev_named_sibling if node is not None else None
    while prev is not None and prev.type == 'attribute_list':
        prev = prev.prev_named_sibling
    if prev is None or prev.type != 'comment':
        return None
    body = text(prev, src)
    if not body.startswith('/**'):
        return None
    for kind, typ, name in DOC_TAG.findall(body):
        if kind == tag and (var is None or name.lstrip('$') == var):
            return DocType(typ)
    return None


class PhpTypes:
    def __init__(self, linker):
        self.l, self.g, self.f = linker, linker.g, linker.f
        self.classes = {}
        self.memo = {}
        self.roots = {}
        for rel in sorted(self.f.units):
            u = self.f.units[rel]
            if u.lang == 'php':
                root = parser_for('php').parse(u.src).root_node
                self.roots[rel] = root
                self.scan(u, root)

    def scan(self, u, root):
        stack = [root]
        while stack:
            n = stack.pop()
            if n.type in CLASSES:
                name = n.child_by_field_name('name')
                cid = f'c:{u.rel}:{text(name, u.src)}' if name is not None else None
                if cid in self.g.nodes and cid not in self.classes:
                    self.classes[cid] = {'unit': u, 'node': n, 'fields': {}, 'arity': {},
                                         'magic': {m: DocType(r) for m, _, r in php_magic_methods(n, u.src) if r}}
                    self.class_members(u, n, cid)
                    # tipan el receptor, pero no son una dependencia hacia la clase (scip-php no les da ocurrencia)
                    self.classes[cid]['magic_fields'] = {var: (DocType(typ), None) for typ, var in doc_properties(n, u.src)}
            stack.extend(n.named_children)

    def class_members(self, u, n, cid):
        info = self.classes[cid]
        body = n.child_by_field_name('body')
        for c in (body.named_children if body is not None else ()):
            if c.type == 'property_declaration':
                typ = c.child_by_field_name('type') or docblock(c, u.src, 'var')
                for el in c.named_children:
                    if el.type == 'property_element':
                        var = el.child_by_field_name('name') or next((x for x in el.named_children if x.type == 'variable_name'), None)
                        if var is not None:
                            info['fields'][var_name(var, u.src)] = (typ, el.child_by_field_name('default_value'))
            elif c.type == 'method_declaration':
                name = text_of(c.child_by_field_name('name'), u.src)
                params = c.child_by_field_name('parameters')
                info['arity'].setdefault(name, []).append(arity(params))
                if name == '__construct':
                    for p in (params.named_children if params is not None else ()):
                        if p.type == 'property_promotion_parameter':
                            var = p.child_by_field_name('name')
                            if var is not None:
                                info['fields'][var_name(var, u.src)] = (p.child_by_field_name('type'), None)
            elif c.type == 'enum_case':
                name = c.child_by_field_name('name')
                if name is not None:
                    info['fields'][text(name, u.src)] = ('self', cid)

    # --- tipos ---

    def here(self, u, node):
        cur = node
        while cur is not None:
            if cur.type in CLASSES:
                name = cur.child_by_field_name('name')
                cid = f'c:{u.rel}:{text(name, u.src)}' if name is not None else None
                return cid if cid in self.classes else None
            cur = cur.parent
        return None

    def resolve(self, u, at, node, depth=0):
        if node is None or depth > MAX_DEPTH:
            return UNKNOWN
        if isinstance(node, DocType):
            parts = [p.lstrip('?') for p in node.split('|') if p.lstrip('?').lower() not in ('null', 'mixed', '')]
            kinds = [self.named(u, at, p) for p in parts if not p.endswith(']') and '<' not in p]
            if len(parts) == 1:
                return kinds[0] if kinds else UNKNOWN
            classes = {k.cid for k in kinds if k is not None and k.cid}
            return Type(classes.pop()) if len(classes) == 1 else UNKNOWN
        t = node.type
        if t in ('optional_type', 'union_type', 'intersection_type', 'disjunctive_normal_form_type'):
            kinds = [self.resolve(u, at, c, depth + 1) for c in node.named_children]
            kinds = [k for k in kinds if k is not None and not (not k.cid and k.name == 'null')]
            classes = {k.cid for k in kinds if k.cid}
            if len(kinds) == 1:
                return kinds[0]
            return Type(classes.pop()) if len(classes) == 1 else UNKNOWN
        if t == 'primitive_type':
            return ext(text(node, u.src))
        if t == 'named_type':
            inner = node.named_children[0] if node.named_children else None
            return self.resolve(u, at, inner, depth + 1)
        if t in ('name', 'qualified_name', 'relative_scope'):
            return self.named(u, at, text(node, u.src))
        return UNKNOWN

    def named(self, u, at, raw):
        name = raw.strip()
        low = name.lower()
        if low in ('self', 'static', '$this'):
            cid = self.here(u, at)
            return Type(cid) if cid else UNKNOWN
        if low == 'parent':
            cur = at
            while cur is not None and cur.type not in CLASSES:
                cur = cur.parent
            base = next((c for c in cur.named_children if c.type == 'base_clause'), None) if cur is not None else None
            head = next((c for c in base.named_children if c.type in ('name', 'qualified_name')), None) if base is not None else None
            return self.resolve(u, cur, head) if head is not None else UNKNOWN
        if low in BUILTIN:
            return ext(low)
        key = ('type', u.rel, name)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = self.lookup(u, name)
        return self.memo[key]

    def lookup(self, u, name):
        if name.startswith('\\'):
            target = self.f.fqn.get(name.strip('\\').replace('\\', '.'))
            return self.as_class(target, name)
        if '\\' in name:
            pkg = u.packages[0] if u.packages else ''
            head, _, rest = name.partition('\\')
            used = [v for kind, v, alias in u.imports if kind == 'fqn' and (alias or v.rsplit('.', 1)[-1]) == head]
            for cand in [f'{v}.{rest}' for v in used] + [f'{pkg}.{name}' if pkg else name, name]:
                target = self.f.fqn.get(cand.replace('\\', '.'))
                if target:
                    return self.as_class(target, name)
            return ext(name.rsplit('\\', 1)[-1])
        if name in u.foreign:
            return ext(name)
        found = self.l.type_target(u, name)
        if found:
            return Type(found)
        alias = u.aliases.get(name)
        if alias and alias[0] == 'def':
            return self.as_class(alias[1], name)
        if name in u.foreign or name not in self.f.classes_by_name:
            return ext(name)
        return UNKNOWN

    def as_class(self, target, name):
        if target and self.g.nodes[target]['kind'] == 'class':
            return Type(target)
        return ext(name.rsplit('\\', 1)[-1]) if not target else UNKNOWN

    # --- expresiones ---

    def type_of(self, u, expr, depth=0):
        if expr is None or depth > MAX_DEPTH:
            return UNKNOWN
        key = ('expr', u.rel, expr.id)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = UNKNOWN
        found = self._type_of(u, expr, depth)
        self.memo[key] = found
        return found

    def _type_of(self, u, expr, depth):
        t = expr.type
        if t == 'variable_name':
            name = var_name(expr, u.src)
            if name == 'this':
                cid = self.here(u, expr)
                return Type(cid) if cid else UNKNOWN
            return self.variable(u, expr, name, depth)
        if t == 'parenthesized_expression' and expr.named_children:
            return self.type_of(u, expr.named_children[0], depth + 1)
        if t == 'object_creation_expression':
            head = next((c for c in expr.named_children if c.type in ('name', 'qualified_name', 'relative_scope')), None)
            return self.resolve(u, expr, head, depth + 1) if head is not None else UNKNOWN
        if t == 'clone_expression' and expr.named_children:
            return self.type_of(u, expr.named_children[0], depth + 1)
        if t in MEMBER_READS:
            owner = self.type_of(u, expr.child_by_field_name('object'), depth + 1)
            name = text_of(expr.child_by_field_name('name'), u.src)
            if owner is None or not owner.cid or not name:
                return UNKNOWN
            return self.field(owner.cid, name, depth + 1)
        if t in ('class_constant_access_expression',):
            kids = expr.named_children
            owner = self.resolve(u, expr, kids[0], depth + 1) if kids else None
            if owner is not None and owner.cid and len(kids) > 1:
                return self.field(owner.cid, text(kids[1], u.src), depth + 1)
            return UNKNOWN
        if t in MEMBER_CALLS or t == 'scoped_call_expression':
            if t in MEMBER_CALLS:
                owner = self.type_of(u, expr.child_by_field_name('object'), depth + 1)
                if owner is not None and not owner.cid:
                    return ext('?')
            target = self.target(u, expr, depth + 1)
            if target is False and t in MEMBER_CALLS and owner is not None and self.foreign_ancestor(owner.cid):
                return ext('?')
            return self.returns(target, depth + 1) if target else UNKNOWN
        if t == 'function_call_expression':
            # `response()->json()`: una función de PHP o de una dependencia devuelve un valor de fuera del proyecto
            fn = expr.child_by_field_name('function')
            if fn is None or fn.type not in ('name', 'qualified_name'):
                return UNKNOWN
            funcs = [x for x in self.f.top_by_name.get(text(fn, u.src).rsplit('\\', 1)[-1], ()) if self.g.nodes[x]['kind'] == 'function']
            if not funcs:
                return ext('?')
            return self.returns(funcs[0], depth + 1) if len(funcs) == 1 else UNKNOWN
        if t in ('string', 'encapsed_string'):
            return ext('string')
        if t in ('integer', 'float', 'boolean'):
            return ext(t)
        return UNKNOWN

    def variable(self, u, use, name, depth):
        found = self.local(u, use, name)
        if found is False or found is None:
            return UNKNOWN
        typ, value = found
        if typ is not None:
            return self.resolve(u, use, typ, depth + 1)
        return self.type_of(u, value, depth + 1) if value is not None else UNKNOWN

    def local(self, u, use, name):
        cur = use.parent
        while cur is not None:
            if cur.type in FUNCTIONS:
                params = cur.child_by_field_name('parameters')
                for p in (params.named_children if params is not None else ()):
                    var = p.child_by_field_name('name')
                    if var is not None and var_name(var, u.src) == name:
                        return (p.child_by_field_name('type') or docblock(cur, u.src, 'param', name), None)
                body = cur.child_by_field_name('body')
                found = assignment(body, u.src, name, use.start_byte) if body is not None else None
                if found is not None:
                    return found
                if cur.type in ('anonymous_function', 'arrow_function'):
                    cur = cur.parent
                    continue
                return False
            if cur.type in CLASSES:
                return False
            cur = cur.parent
        return False

    def field(self, cid, name, depth, seen=None):
        top = seen is None
        seen = seen or set()
        if cid in seen or depth > MAX_DEPTH:
            return UNKNOWN
        seen.add(cid)
        info = self.classes.get(cid)
        if info is None:
            return UNKNOWN
        held = info['fields'].get(name) or info.get('magic_fields', {}).get(name)
        if held is not None:
            if held[0] == 'self':
                return Type(held[1])
            typ, value = held
            if typ is not None:
                return self.resolve(info['unit'], typ, typ, depth + 1)
            return self.type_of(info['unit'], value, depth + 1) if value is not None else UNKNOWN
        for base in self.l.parents.get(cid, ()):
            found = self.field(base, name, depth + 1, seen)
            if found is not None:
                return found
        return ext('?') if top and self.foreign_ancestor(cid) else UNKNOWN

    def foreign_ancestor(self, cid, seen=None):
        """La clase hereda, implementa o usa un tipo de fuera del proyecto (`extends Model` de Eloquent, `implements
        StatefulGuard`) y no reenvía con `__get`/`__call`: un miembro que no está en sus ancestros del proyecto es de él."""
        seen = seen if seen is not None else set()
        info = self.classes.get(cid)
        if info is None or cid in seen:
            return False
        seen.add(cid)
        if 'foreign' not in info:
            u, n = info['unit'], info['node']
            heads = []
            for c in n.named_children:
                if c.type in ('base_clause', 'class_interface_clause'):
                    heads += [k for k in c.named_children if k.type in ('name', 'qualified_name')]
            body = n.child_by_field_name('body')
            for c in (body.named_children if body is not None else ()):
                if c.type == 'use_declaration':
                    heads += [k for k in c.named_children if k.type in ('name', 'qualified_name')]
            magic = {'__get', '__call'} & set(info['arity'])
            kinds = [self.resolve(u, n, h) for h in heads]
            info['foreign'] = (not magic, any(k is not None and not k.cid for k in kinds), [k.cid for k in kinds if k is not None and k.cid])
        closed, foreign, bases = info['foreign']
        return closed and (foreign or any(self.foreign_ancestor(b, seen) for b in bases))

    def returns(self, fid, depth):
        meta = self.g.nodes.get(fid) or {}
        u = self.f.units.get(meta.get('file'))
        node = u.fnodes.get(fid) if u is not None else None
        if node is None:
            owner, _, name = str(meta.get('name', '')).rpartition('.')
            info = self.classes.get(f"c:{meta.get('file')}:{owner}")
            typ = info['magic'].get(name) if info is not None else None
            return self.resolve(u, info['node'], typ, depth + 1) if typ else UNKNOWN
        return self.resolve(u, node, node.child_by_field_name('return_type') or docblock(node, u.src, 'return'), depth + 1)

    # --- llamadas ---

    def method(self, cid, name, argc=None):
        queue, seen, fallback = [cid], set(), None
        while queue and len(seen) <= MAX_DEPTH:
            cur = queue.pop(0)
            if cur in seen or cur not in self.g.nodes:
                continue
            seen.add(cur)
            meta = self.g.nodes[cur]
            cands = [m for m in self.f.methods.get((meta['name'], name), ()) if self.g.nodes[m]['file'] == meta['file']]
            if cands:
                return cands[0]
            queue.extend(self.l.parents.get(cur, ()))
        return fallback

    def call(self, u, node, depth=0):
        return self.target(u, node, depth), None

    def target(self, u, node, depth=0):
        key = ('call', u.rel, node.id)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = None
        found = self._call(u, node, depth)
        self.memo[key] = found
        return found

    def _call(self, u, node, depth):
        t = node.type
        if t == 'object_creation_expression':
            typ = self.type_of(u, node, depth)
            return (typ.cid or False) if typ is not None else None
        if t == 'attribute':
            head = node.named_children[0] if node.named_children else None
            if head is None or head.type not in ('name', 'qualified_name') or \
                    not any(c.type == 'arguments' for c in node.named_children):
                return False
            typ = self.resolve(u, node, head, depth)
            return (typ.cid or False) if typ is not None else None
        if t == 'function_call_expression':
            fn = node.child_by_field_name('function')
            if fn is None:
                return None
            if fn.type not in ('name', 'qualified_name'):
                return False
            name = text(fn, u.src).rsplit('\\', 1)[-1]
            funcs = [x for x in self.f.top_by_name.get(name, ()) if self.g.nodes[x]['kind'] == 'function']
            return None if funcs else False
        name = text_of(node.child_by_field_name('name'), u.src)
        if not name or node.child_by_field_name('name').type not in ('name',):
            return None
        if t in MEMBER_CALLS:
            owner = self.type_of(u, node.child_by_field_name('object'), depth)
        elif t == 'scoped_call_expression':
            owner = self.resolve(u, node, node.child_by_field_name('scope'), depth)
        else:
            return None
        if owner is None:
            return None
        if owner.cid:
            return self.method(owner.cid, name) or False
        return False

    @staticmethod
    def class_refs(n):
        """Nombres de clase que `n` cita sin llamarla: `X::class`/`X::CONST`, `X::m()`, `instanceof X`, tipos declarados."""
        kids = n.named_children
        if n.type in ('class_constant_access_expression', 'scoped_call_expression', 'scoped_property_access_expression'):
            head = n.child_by_field_name('scope') or (kids[0] if kids else None)
            return [head] if head is not None and head.type in ('name', 'qualified_name') else []
        if n.type == 'named_type':
            return [k for k in kids if k.type in ('name', 'qualified_name')]
        if n.type == 'binary_expression' and len(kids) == 2 and kids[1].type in ('name', 'qualified_name') and \
                b'instanceof' in n.text[kids[0].end_byte - n.start_byte:kids[1].start_byte - n.start_byte]:
            return [kids[1]]
        return []

    def members(self, u):
        """Archivos que declaran las propiedades que `u` lee a través de un receptor tipado."""
        out = []
        stack = [self.roots[u.rel]] if u.rel in self.roots else []
        while stack:
            n = stack.pop()
            stack.extend(n.named_children)
            for head in self.class_refs(n):
                found = self.resolve(u, n, head)
                rel = self.g.nodes[found.cid]['file'] if found is not None and found.cid else None
                if rel and rel != u.rel and rel not in out:
                    out.append(rel)
            if n.type not in MEMBER_READS and n.type != 'class_constant_access_expression':
                continue
            if n.type == 'class_constant_access_expression':
                kids = n.named_children
                owner = self.resolve(u, n, kids[0]) if kids else None
                name = text(kids[1], u.src) if len(kids) > 1 else None
            else:
                owner = self.type_of(u, n.child_by_field_name('object'))
                name = text_of(n.child_by_field_name('name'), u.src)
            if owner is None or not owner.cid or not name:
                continue
            queue, seen = [owner.cid], set()
            while queue:
                cur = queue.pop(0)
                if cur in seen:
                    continue
                seen.add(cur)
                info = self.classes.get(cur)
                if info is not None and name in info['fields']:
                    rel = info['unit'].rel
                    if rel != u.rel and rel not in out:
                        out.append(rel)
                    break
                queue.extend(self.l.parents.get(cur, ()))
        return out


def doc_properties(node, src):
    """`@property User $user` (también `-read`/`-write`) del PHPDoc de la clase: propiedades servidas por `__get`."""
    prev = node.prev_named_sibling
    while prev is not None and prev.type == 'attribute_list':
        prev = prev.prev_named_sibling
    if prev is None or prev.type != 'comment':
        return []
    body = text(prev, src)
    return DOC_PROPERTY.findall(body) if body.startswith('/**') else []


def text_of(node, src):
    return text(node, src) if node is not None else None


def var_name(node, src):
    return text(node, src).lstrip('$')


def arity(params):
    kids = [p for p in (params.named_children if params is not None else ()) if p.type.endswith('parameter')]
    return len([p for p in kids if p.child_by_field_name('default_value') is None]), len(kids)


def assignment(body, src, name, before):
    """(tipo, valor) de la última asignación `$name = …` (o `catch (T $name)`, `foreach (… as $name)`) antes de `before`."""
    best = None
    stack = [body]
    while stack:
        n = stack.pop()
        if n.start_byte >= before:
            continue
        if n.type in FUNCTIONS or n.type in CLASSES:
            continue
        if n.type == 'assignment_expression' and n.end_byte <= before:
            left = n.child_by_field_name('left')
            if left is not None and left.type == 'variable_name' and var_name(left, src) == name:
                if best is None or n.start_byte > best[0]:
                    best = (n.start_byte, (None, n.child_by_field_name('right')))
        elif n.type == 'catch_clause':
            var = n.child_by_field_name('name')
            if var is not None and var_name(var, src) == name and n.start_byte < before:
                types = n.child_by_field_name('type')
                best = (n.start_byte, (types, None))
        elif n.type == 'foreach_statement':
            pair = [c for c in n.named_children if c.type in ('variable_name', 'pair')]
            if any(c.type == 'variable_name' and var_name(c, src) == name for c in pair[1:]) and \
                    (best is None or n.start_byte > best[0]):
                best = (n.start_byte, None)
        stack.extend(n.named_children)
    if best is None:
        return None
    return best[1] if best[1] is not None else (None, None)
