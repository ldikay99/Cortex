"""Tipos declarados para resolver receptores en C#.

Reutiliza el registro de clases, campos y métodos del tipador de Java/Kotlin y
añade la sintaxis de C#: clases parciales repartidas en varios archivos, tipos
anidados, propiedades, métodos de extensión (`this T x`), `var`, patrones
`x is T y`, `foreach`, `await` y lambdas de LINQ.
"""
from collections import defaultdict

from .langs import parser_for, text
from .typed import UNKNOWN, Elem, JvmTypes, Pseudo, Type, ext, fits

CS_CLASSES = {'class_declaration', 'struct_declaration', 'interface_declaration', 'record_declaration', 'enum_declaration',
              'record_struct_declaration'}
CS_TYPES = {'identifier', 'generic_name', 'qualified_name', 'predefined_type', 'nullable_type', 'array_type', 'pointer_type',
            'ref_type', 'tuple_type', 'implicit_type', 'alias_qualified_name', 'function_pointer_type'}
CS_CALLABLES = {'method_declaration', 'constructor_declaration', 'local_function_statement', 'operator_declaration',
                'conversion_operator_declaration', 'destructor_declaration', 'accessor_declaration', 'lambda_expression',
                'anonymous_method_expression'}
CS_SCOPES = {'block', 'switch_section'}
CS_VALUE_PARENTS = {'member_access_expression', 'assignment_expression', 'argument', 'binary_expression', 'return_statement',
                    'arrow_expression_clause', 'equals_value_clause', 'prefix_unary_expression', 'postfix_unary_expression',
                    'parenthesized_expression', 'interpolation', 'conditional_expression', 'await_expression',
                    'element_access_expression', 'conditional_access_expression', 'is_pattern_expression', 'expression_statement'}
TASKS = {'Task', 'ValueTask', 'IAsyncEnumerable'}
CS_ELEMENT = {'First', 'FirstOrDefault', 'Last', 'LastOrDefault', 'Single', 'SingleOrDefault', 'ElementAt',
              'ElementAtOrDefault', 'Min', 'Max', 'Dequeue', 'Peek', 'Pop', 'Find', 'MinBy', 'MaxBy', 'Current'}
CS_KEEP = {'Where', 'OrderBy', 'OrderByDescending', 'ThenBy', 'ThenByDescending', 'ToList', 'ToArray', 'AsEnumerable',
           'Distinct', 'Skip', 'Take', 'Reverse', 'Concat', 'Union', 'Except', 'Intersect', 'ToHashSet', 'DistinctBy',
           'SkipWhile', 'TakeWhile', 'AsReadOnly', 'GetRange', 'FindAll', 'Append', 'Prepend', 'ToImmutableList'}
CS_LAMBDA = {'Select', 'Where', 'Any', 'All', 'First', 'FirstOrDefault', 'Last', 'LastOrDefault', 'Single',
             'SingleOrDefault', 'Count', 'Sum', 'Min', 'Max', 'OrderBy', 'OrderByDescending', 'ThenBy', 'ThenByDescending',
             'GroupBy', 'ToDictionary', 'ToLookup', 'SelectMany', 'ForEach', 'Exists', 'Find', 'FindAll', 'RemoveAll',
             'TrueForAll', 'Aggregate', 'DistinctBy', 'MinBy', 'MaxBy', 'SkipWhile', 'TakeWhile', 'Average', 'FindIndex'}
CS_CONTAINERS = {'List', 'IList', 'IEnumerable', 'ICollection', 'IReadOnlyList', 'IReadOnlyCollection', 'HashSet', 'ISet',
                 'Queue', 'Stack', 'LinkedList', 'IEnumerator', 'Lazy', 'Nullable', 'ImmutableList', 'ImmutableArray',
                 'ConcurrentQueue', 'ConcurrentBag', 'SortedSet', 'IQueryable', 'IOrderedEnumerable', 'ObservableCollection',
                 'Collection', 'ReadOnlyCollection', 'BlockingCollection', 'IAsyncEnumerable'}
CS_MAPS = {'Dictionary', 'IDictionary', 'IReadOnlyDictionary', 'ConcurrentDictionary', 'SortedDictionary',
           'ImmutableDictionary', 'SortedList', 'ReadOnlyDictionary'}
DELEGATES = {'Func', 'Action', 'Predicate', 'Comparison', 'Converter', 'EventHandler'}


class CSharpTypes(JvmTypes):
    def __init__(self, linker):
        self.l, self.g, self.f = linker, linker.g, linker.f
        self.classes = {}
        self.in_file = {}
        self.nested = defaultdict(dict)
        self.imported = defaultdict(dict)
        self.statics = defaultdict(list)
        self.top_props = {}
        self.extensions = defaultdict(list)
        self.memo = {}
        self.by_owner = None
        self.roots = {}
        self.parts = defaultdict(list)
        self.part_key = {}
        units = [self.f.units[rel] for rel in sorted(self.f.units) if self.f.units[rel].lang == 'csharp']
        for u in units:
            root = parser_for('csharp').parse(u.src).root_node
            self.roots[u.rel] = root
            self.scan_cs(u, root)
        self.link_bases()

    # --- registro ---

    def scan_cs(self, u, root):
        stack = [(root, None, '')]
        while stack:
            n, outer, space = stack.pop()
            cid = outer
            if n.type in ('namespace_declaration', 'file_scoped_namespace_declaration'):
                name = n.child_by_field_name('name')
                space = '.'.join(x for x in (space, text(name, u.src) if name is not None else '') if x)
            if n.type in CS_CLASSES:
                named = n.child_by_field_name('name')
                found = self.register(u, n, text(named, u.src), outer) if named is not None else None
                if found:
                    cid = found
                    key = (space, self.qual_name(outer) if outer else '', text(named, u.src))
                    self.part_key[cid] = key
                    self.parts[key].append(cid)
                    self.cs_members(u, n, cid)
            for c in n.named_children:
                if c.type in CS_CLASSES or c.type in ('declaration_list', 'compilation_unit', 'namespace_declaration',
                                                      'file_scoped_namespace_declaration'):
                    stack.append((c, cid, space))
                elif c.type == 'enum_member_declaration_list':
                    stack.append((c, cid, space))

    def qual_name(self, cid):
        key = self.part_key.get(cid)
        return '.'.join(x for x in (key[1], key[2]) if x) if key else ''

    def cs_members(self, u, n, cid):
        info = self.classes[cid]
        params = n.child_by_field_name('parameters') or next((c for c in n.named_children if c.type == 'parameter_list'), None)
        if n.type in ('record_declaration', 'record_struct_declaration') and params is not None:
            for p in params.named_children:
                name = p.child_by_field_name('name')
                if name is not None:
                    info['fields'][text(name, u.src)] = ('decl', u, p.child_by_field_name('type'), None)
        body = n.child_by_field_name('body')
        static = any(text(m, u.src) == 'static' for m in n.named_children if m.type == 'modifier')
        for c in (body.named_children if body is not None else ()):
            if c.type in ('field_declaration', 'event_field_declaration'):
                decl = next((x for x in c.named_children if x.type == 'variable_declaration'), None)
                typ = decl.child_by_field_name('type') if decl is not None else None
                for d in (decl.named_children if decl is not None else ()):
                    if d.type == 'variable_declarator':
                        name = d.child_by_field_name('name') or next((x for x in d.named_children if x.type == 'identifier'), None)
                        value = next((x for x in d.named_children if x != name and x.type not in ('bracketed_argument_list',)), None)
                        if name is not None:
                            info['fields'][text(name, u.src)] = ('decl', u, None if is_implicit(typ) else typ, value)
            elif c.type == 'indexer_declaration':
                info['fields'].setdefault('this[]', ('decl', u, c.child_by_field_name('type'), None))
            elif c.type in ('property_declaration', 'event_declaration'):
                name = c.child_by_field_name('name')
                if name is not None:
                    info['fields'][text(name, u.src)] = ('decl', u, c.child_by_field_name('type'), c.child_by_field_name('value'))
            elif c.type == 'method_declaration':
                name = c.child_by_field_name('name')
                if name is None:
                    continue
                ps = c.child_by_field_name('parameters')
                info['arity'].setdefault(text(name, u.src), []).append(cs_arity(ps) + (c,))
                first = next((p for p in (ps.named_children if ps is not None else ()) if p.type == 'parameter'), None)
                if static and first is not None and any(text(m, u.src) == 'this' for m in first.named_children if m.type == 'modifier'):
                    fid = f"f:{u.rel}:{self.g.nodes[cid]['name']}.{text(name, u.src)}"
                    if fid in self.g.nodes:
                        self.extensions[text(name, u.src)].append((fid, u, first.child_by_field_name('type'), c))
            elif c.type == 'enum_member_declaration':
                name = c.child_by_field_name('name')
                if name is not None:
                    info['fields'][text(name, u.src)] = ('self', cid)
        if n.type == 'enum_declaration':
            members = n.child_by_field_name('body')
            for c in (members.named_children if members is not None else ()):
                name = c.child_by_field_name('name')
                if c.type == 'enum_member_declaration' and name is not None:
                    info['fields'][text(name, u.src)] = ('self', cid)

    def partners(self, cid):
        key = self.part_key.get(cid)
        return self.parts[key] if key else [cid]

    def link_bases(self):
        for cid, info in self.classes.items():
            u, n = info['unit'], info['node']
            bases = next((c for c in n.named_children if c.type == 'base_list'), None)
            for k in (bases.named_children if bases is not None else ()):
                if k.type == 'primary_constructor_base_type':
                    k = k.named_children[0] if k.named_children else None
                found = self.resolve_type(u, n, k)
                if found is not None and found.cid and found.cid not in self.partners(cid) and found.cid not in self.l.parents.get(cid, ()):
                    self.l.parents[cid].append(found.cid)
                    self.g.edge(cid, found.cid, 'inherits')

    # --- tipos ---

    def resolve_type(self, u, at, node, depth=0):
        if node is None or depth > 12:
            return UNKNOWN
        if isinstance(node, Pseudo):
            return self.pseudo(u, node, depth)
        t = node.type
        if t in ('nullable_type', 'pointer_type', 'ref_type', 'scoped_type'):
            return self.resolve_type(u, at, node.child_by_field_name('type') or (node.named_children[0] if node.named_children else None), depth + 1)
        if t == 'predefined_type':
            return ext(text(node, u.src))
        if t == 'implicit_type':
            return UNKNOWN
        if t == 'array_type':
            return Type(name='[]', elem=self.resolve_type(u, at, node.child_by_field_name('type'), depth + 1))
        if t == 'identifier':
            return self.named_type(u, at, text(node, u.src))
        if t == 'generic_name':
            ident = next((c for c in node.named_children if c.type == 'identifier'), None)
            base = self.named_type(u, at, text(ident, u.src)) if ident is not None else None
            args = next((c for c in node.named_children if c.type == 'type_argument_list'), None)
            if base is not None and args is not None:
                base = Type(base.cid, base.name, [(u, at, a) for a in args.named_children])
            return base
        if t == 'qualified_name':
            qual, name = node.child_by_field_name('qualifier'), node.child_by_field_name('name')
            if qual is None or name is None:
                return UNKNOWN
            outer = self.resolve_type(u, at, qual, depth + 1)
            last = self.resolve_type(u, at, name, depth + 1) if name.type == 'generic_name' else None
            label = text(next((c for c in name.named_children if c.type == 'identifier'), name), u.src)
            if outer is not None and outer.cid:
                found = self.member_class(outer.cid, label)
                if found is not None and last is not None:
                    found = Type(found.cid, found.name, last.args)
                return found
            target = self.l.f.fqn.get(text(node, u.src).replace(' ', ''))
            return Type(target) if target else (UNKNOWN if outer is None else ext(label))
        return UNKNOWN

    def named_type(self, u, at, name):
        found = super().named_type(u, at, name)
        if found is not None or name not in self.f.classes_by_name:
            return found
        space = '.'.join(u.packages[:1])
        keys = {self.part_key[c] for c in self.f.classes_by_name[name] if c in self.part_key and not self.part_key[c][1]}
        visible = [k for k in keys if space == k[0] or space.startswith(k[0] + '.') or not k[0]]
        if len(visible) == 1:
            return Type(self.parts[visible[0]][0])
        return found

    def member_class(self, cid, name, seen=None):
        seen = seen or set()
        if cid in seen or len(seen) > 12:
            return None
        for part in self.partners(cid):
            seen.add(part)
            inner = self.nested[part].get(name)
            if inner:
                return Type(inner, static=True)
        for part in self.partners(cid):
            for base in self.l.parents.get(part, ()):
                found = self.member_class(base, name, seen)
                if found:
                    return found
        return None

    def chain(self, u, at):
        out = []
        cur = at
        while cur is not None:
            if cur.type in CS_CLASSES:
                named = cur.child_by_field_name('name')
                cid = f'c:{u.rel}:{text(named, u.src)}' if named is not None else None
                if cid in self.classes:
                    out.append(cid)
            cur = cur.parent
        return out

    def field_type(self, cid, name, depth, seen=None):
        seen = seen or set()
        if cid in seen or depth > 12:
            return None
        for part in self.partners(cid):
            seen.add(part)
            info = self.classes.get(part)
            if info is not None and name in info['fields']:
                return self.source_type(info['fields'][name], depth)
        for part in self.partners(cid):
            for base in self.l.parents.get(part, ()):
                found = self.field_type(base, name, depth + 1, seen)
                if found is not None:
                    return found
        return None

    def ancestors(self, cid):
        out, queue = [], [cid]
        while queue and len(out) <= 24:
            cur = queue.pop(0)
            if cur not in out:
                out.append(cur)
                for part in self.partners(cur):
                    if part not in out:
                        out.append(part)
                    queue.extend(self.l.parents.get(part, ()))
        return out

    def method(self, cid, name, argc=None, strict=False):
        fallback = None
        for cur in self.ancestors(cid):
            if cur not in self.g.nodes:
                continue
            meta = self.g.nodes[cur]
            cands = [m for m in self.f.methods.get((meta['name'], name), ()) if self.g.nodes[m]['file'] == meta['file']]
            if not cands:
                continue
            arities = self.classes.get(cur, {}).get('arity', {}).get(name, ())
            if argc is None or not arities or any(fits(a, argc) for a in arities):
                return cands[0]
            fallback = fallback or cands[0]
        return None if strict else fallback

    def overload(self, fid, argc):
        meta = self.g.nodes[fid]
        owner, _, name = str(meta['name']).rpartition('.')
        found = self.in_file.get((meta['file'], owner)) if owner else None
        info = self.classes.get(found[0]) if found else None
        for entry in (info['arity'].get(name, ()) if info and argc is not None else ()):
            if fits(entry, argc):
                return entry[2]
        return None

    def returns(self, fid, owner, depth, argc=None):
        u, node = self.declaration(fid)
        node = self.overload(fid, argc) or node
        if node is None:
            return UNKNOWN
        typ = node.child_by_field_name('returns') or node.child_by_field_name('type')
        if typ is not None and owner is not None and owner.cid:
            from .typed import tparams, type_name
            holder = next((a for a in ancestors(node.parent) if a.type in CS_CLASSES), None)
            names = tparams(holder, u.src) if holder is not None else []
            name = text(typ, u.src) if typ.type == 'identifier' else type_name(typ, u.src)
            if name in names:
                bound = owner if self.classes.get(owner.cid, {}).get('node') == holder else self.as_base(owner, holder, u)
                if bound is not None and names.index(name) < len(bound.args):
                    return self.arg(bound, names.index(name), depth)
        return self.resolve_type(u, node, typ, depth + 1)

    def as_base(self, owner, holder, hu):
        """El tipo base genérico `holder` visto desde `owner`, con sus argumentos (`class Html : Base<Html>`: en los
        métodos de `Base<T>`, `T` es `Html`)."""
        label = text(holder.child_by_field_name('name'), hu.src) if holder.child_by_field_name('name') is not None else None
        queue, seen = [owner.cid], set()
        while queue and len(seen) < 12:
            cid = queue.pop(0)
            if cid in seen or cid not in self.classes:
                continue
            seen.add(cid)
            for part in self.partners(cid):
                info = self.classes.get(part)
                bases = next((c for c in info['node'].named_children if c.type == 'base_list'), None) if info else None
                for k in (bases.named_children if bases is not None else ()):
                    found = self.resolve_type(info['unit'], info['node'], k)
                    if found is None or not found.cid:
                        continue
                    ident = k.named_children[0] if k.type == 'generic_name' and k.named_children else None
                    if ident is not None and text(ident, info['unit'].src) == label and found.args:
                        return found
                    queue.append(found.cid)
        return None

    def params(self, fid):
        u, node = self.declaration(fid)
        if node is None:
            return u, []
        ps = node.child_by_field_name('parameters')
        return u, [p.child_by_field_name('type') for p in (ps.named_children if ps is not None else ()) if p.type == 'parameter']

    def parent_of(self, here):
        if here is None or not here.cid:
            return UNKNOWN
        bases = [b for p in self.partners(here.cid) for b in self.l.parents.get(p, ())]
        return Type(bases[0]) if bases else UNKNOWN

    def iterated(self, t, depth=0):
        if t is None or t.cid:
            return UNKNOWN
        if t.name == '[]':
            return t.elem
        if t.name in CS_CONTAINERS and t.args:
            return self.arg(t, 0, depth)
        return UNKNOWN

    # --- expresiones ---

    def type_of(self, u, expr, depth=0):
        if expr is None or depth > 12:
            return UNKNOWN
        if isinstance(expr, Pseudo):
            return self.pseudo(u, expr, depth)
        key = ('expr', u.rel, expr.id)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = UNKNOWN
        found = self.cs_expr(u, expr, depth)
        self.memo[key] = found
        return found

    def cs_expr(self, u, expr, depth):
        t = expr.type
        if t == 'identifier':
            return self.variable(u, expr, text(expr, u.src), depth)
        if t in ('this', 'this_expression'):
            return self.this_type(u, expr)
        if t in ('base', 'base_expression'):
            return self.parent_of(self.this_type(u, expr))
        if t == 'parenthesized_expression' and expr.named_children:
            return self.type_of(u, expr.named_children[0], depth + 1)
        if t in ('generic_name', 'predefined_type', 'qualified_name'):
            typ = self.resolve_type(u, expr, expr, depth + 1)
            return Type(typ.cid, typ.name, typ.args, static=True) if typ is not None else UNKNOWN
        if t == 'cast_expression':
            return self.resolve_type(u, expr, expr.child_by_field_name('type'), depth + 1)
        if t == 'as_expression':
            return self.resolve_type(u, expr, expr.child_by_field_name('right') or expr.named_children[-1], depth + 1)
        if t == 'object_creation_expression':
            return self.resolve_type(u, expr, expr.child_by_field_name('type'), depth + 1)
        if t in ('string_literal', 'interpolated_string_expression', 'verbatim_string_literal', 'raw_string_literal'):
            return ext('string')
        if t == 'character_literal':
            return ext('char')
        if t == 'await_expression' and expr.named_children:
            inner = self.type_of(u, expr.named_children[0], depth + 1)
            if inner is not None and not inner.cid and inner.name in TASKS:
                return self.arg(inner, 0, depth) if inner.args else ext('void')
            return UNKNOWN
        if t == 'element_access_expression':
            owner = self.type_of(u, expr.child_by_field_name('expression'), depth + 1)
            if owner is not None and owner.cid:
                return self.field_type(owner.cid, 'this[]', depth + 1)
            if owner is None:
                return UNKNOWN
            if owner.name in ('string', 'String'):
                return ext('char')
            if owner.name == '[]':
                return owner.elem
            if owner.name in CS_MAPS:
                return self.arg(owner, 1, depth)
            return self.arg(owner, 0, depth) if owner.name in CS_CONTAINERS else UNKNOWN
        if t == 'member_access_expression':
            owner = self.type_of(u, expr.child_by_field_name('expression'), depth + 1)
            name = member_name(expr.child_by_field_name('name'), u.src)
            if owner is None or not name:
                return UNKNOWN
            return self.cs_member(owner, name, depth)
        if t == 'conditional_access_expression':
            owner = self.type_of(u, expr.child_by_field_name('condition'), depth + 1)
            binding = next((c for c in expr.named_children if c.type == 'member_binding_expression'), None)
            name = member_name(binding.child_by_field_name('name'), u.src) if binding is not None else None
            return self.cs_member(owner, name, depth) if owner is not None and name else UNKNOWN
        if t == 'invocation_expression':
            return self.result(u, expr, depth)
        return UNKNOWN

    def cs_member(self, owner, name, depth):
        if owner.cid:
            found = self.field_type(owner.cid, name, depth + 1)
            if found is not None:
                return found
            return self.member_class(owner.cid, name) if owner.static else UNKNOWN
        if owner.name in CS_MAPS and name in ('Values', 'Keys') and len(owner.args) == 2:
            return Type(name='IEnumerable', args=[owner.args[1 if name == 'Values' else 0]])
        if owner.name in ('Lazy', 'Nullable') and name == 'Value' and owner.args:
            return self.arg(owner, 0, depth)
        if owner.name == '[]' and name == 'Length' or name == 'Count':
            return ext('int')
        return UNKNOWN

    def result(self, u, expr, depth):
        target, owner = self.call(u, expr, depth + 1)
        if isinstance(owner, Elem):
            return owner
        if target and self.g.nodes[target]['kind'] == 'class':
            return Type(target)
        if target:
            return self.returns(target, owner, depth + 1, self.argc(expr))
        return UNKNOWN

    def argc(self, node):
        args = node.child_by_field_name('arguments')
        return sum(1 for a in args.named_children if a.type == 'argument') if args is not None else None

    def this_type(self, u, expr, label=None):
        chain = self.chain(u, expr)
        return Type(chain[0]) if chain else UNKNOWN

    def receivers(self, u, use):
        return [Type(c) for c in self.chain(u, use)]

    def variable(self, u, use, name, depth):
        found = self.cs_local(u, use, name)
        if found is not False:
            if found is None:
                return UNKNOWN
            typ, value = found
            if typ is not None and not is_implicit(typ):
                return self.resolve_type(u, use, typ, depth + 1)
            return self.type_of(u, value, depth + 1) if value is not None else UNKNOWN
        for t in self.receivers(u, use):
            found = self.field_type(t.cid, name, depth + 1)
            if found is not None:
                return found
        typ = self.named_type(u, use, name) if name[:1].isupper() else UNKNOWN
        if typ is not None:
            return Type(typ.cid, typ.name, static=True)
        return UNKNOWN

    def cs_local(self, u, use, name):
        prev, cur = use, use.parent
        while cur is not None:
            t = cur.type
            if t in CS_CLASSES or t == 'declaration_list':
                return False
            if t in CS_SCOPES:
                best = False
                for c in cur.named_children:
                    if c.start_byte >= use.start_byte:
                        break
                    if c.end_byte > use.start_byte:
                        continue
                    if c.type in ('local_declaration_statement', 'using_statement'):
                        found = declared(c, u.src, name)
                        if found is not False:
                            best = found
                if best is not False:
                    return best
            elif t == 'foreach_statement' and prev == cur.child_by_field_name('body'):
                left = cur.child_by_field_name('left')
                if left is not None and left.type == 'identifier' and text(left, u.src) == name:
                    typ = cur.child_by_field_name('type')
                    if typ is None or is_implicit(typ):
                        return (None, Pseudo('iter', cur.child_by_field_name('right')))
                    return (typ, None)
            elif t in ('for_statement', 'using_statement', 'fixed_statement'):
                found = declared(cur, u.src, name)
                if found is not False:
                    return found
            elif t == 'catch_clause':
                decl = next((c for c in cur.named_children if c.type == 'catch_declaration'), None)
                if decl is not None and text_of(decl.child_by_field_name('name'), u.src) == name:
                    return (decl.child_by_field_name('type'), None)
            if t in CS_CALLABLES:
                params = cur.child_by_field_name('parameters')
                if params is not None and params.type in ('identifier', 'implicit_parameter'):
                    if text(params, u.src) == name:
                        return (None, Pseudo('lambda', cur, 0))
                for i, p in enumerate(params.named_children if params is not None and params.type not in ('identifier', 'implicit_parameter') else ()):
                    if p.type in ('identifier', 'implicit_parameter') and text(p, u.src) == name:
                        return (None, Pseudo('lambda', cur, i))
                    if p.type == 'parameter' and text_of(p.child_by_field_name('name'), u.src) == name:
                        typ = p.child_by_field_name('type')
                        return (typ, None) if typ is not None else (None, Pseudo('lambda', cur, i))
                found = pattern(cur, u.src, name)
                if found is not None:
                    return found
                if t not in ('lambda_expression', 'anonymous_method_expression', 'local_function_statement'):
                    return False
            prev, cur = cur, cur.parent
        return False

    def lambda_param(self, u, lam, index, depth):
        args = lam.parent
        if args is not None and args.type == 'argument':
            args = args.parent
        call = args.parent if args is not None and args.type == 'argument_list' else None
        if call is None or call.type != 'invocation_expression':
            return UNKNOWN
        fn = call.child_by_field_name('function')
        position = [a for a in args.named_children if a.type == 'argument'].index(lam.parent) if lam.parent.type == 'argument' else 0
        if fn is not None and fn.type == 'member_access_expression':
            name = member_name(fn.child_by_field_name('name'), u.src)
            recv = self.type_of(u, fn.child_by_field_name('expression'), depth + 1)
            if recv is not None and not recv.cid and name in CS_LAMBDA:
                if recv.name == '[]':
                    return recv.elem if index == 0 else UNKNOWN
                if recv.name in CS_MAPS and index == 0:
                    return UNKNOWN
                return self.arg(recv, 0, depth) if index == 0 and recv.name in CS_CONTAINERS else UNKNOWN
            if recv is not None and not recv.cid and index == 0 and position == 0 and len(recv.args) == 1 and \
                    recv.name not in CS_CONTAINERS and recv.name not in CS_MAPS and recv.name not in TASKS:
                # `builder.Property(ci => ci.Id)` con `EntityTypeBuilder<CatalogItem> builder`: la lambda de un método de un
                # tipo genérico de fuera del proyecto recibe su argumento de tipo, si es una clase del proyecto
                elem = self.arg(recv, 0, depth)
                if elem is not None and elem.cid:
                    return elem
        target, _ = self.call(u, call, depth + 1)
        if not target or self.g.nodes[target]['kind'] == 'class':
            return UNKNOWN
        pu, types = self.params(target)
        if position >= len(types) or types[position] is None:
            return UNKNOWN
        _, decl = self.declaration(target)
        slot = self.resolve_type(pu, decl, types[position], depth + 1)
        if slot is not None and not slot.cid and slot.name in DELEGATES and index < len(slot.args):
            return self.arg(slot, index, depth)
        if slot is not None and slot.cid:
            params = self.sam(slot.cid)
            if params and index < len(params):
                su, at, typ = params[index]
                return self.resolve_type(su, at, typ, depth + 1)
        return UNKNOWN

    def sam(self, cid):
        return None

    # --- llamadas ---

    def call(self, u, node, depth=0):
        key = ('call', u.rel, node.id)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = (None, None)
        found = self.cs_call(u, node, depth)
        self.memo[key] = found
        return found

    def cs_call(self, u, node, depth):
        t = node.type
        if t == 'object_creation_expression':
            typ = self.resolve_type(u, node, node.child_by_field_name('type'))
            return ((typ.cid or False) if typ is not None else None), None
        if t == 'constructor_initializer':
            here = self.this_type(u, node)
            if here is None or not here.cid:
                return None, None
            if text(node, u.src).lstrip(': \t').startswith('this'):
                return here.cid, None
            bases = [b for p in self.partners(here.cid) for b in self.l.parents.get(p, ())]
            return (bases[0] if bases else False), None
        if t == 'attribute':
            return self.attribute_class(u, node), None
        if t != 'invocation_expression':
            return None, None
        fn = node.child_by_field_name('function')
        argc = self.argc(node)
        if fn is None:
            return None, None
        if fn.type in ('identifier', 'generic_name'):
            name = member_name(fn, u.src)
            if self.cs_local(u, fn, name) is not False:
                return False, None
            return self.implicit(u, node, name, argc), None
        if fn.type == 'member_access_expression':
            name = member_name(fn.child_by_field_name('name'), u.src)
            owner = self.type_of(u, fn.child_by_field_name('expression'), depth)
            return self.cs_on(owner, name, argc, depth)
        if fn.type == 'conditional_access_expression':
            binding = next((c for c in fn.named_children if c.type == 'member_binding_expression'), None)
            name = member_name(binding.child_by_field_name('name'), u.src) if binding is not None else None
            owner = self.type_of(u, fn.child_by_field_name('condition'), depth)
            return self.cs_on(owner, name, argc, depth)
        return None, None

    def attribute_class(self, u, node):
        """`[Formato("x")]` crea una instancia del atributo: `FormatoAttribute` (o `Formato`) del proyecto."""
        name = node.child_by_field_name('name')
        if name is None or not any(c.type == 'attribute_argument_list' for c in node.named_children):
            return None
        word = member_name(name, u.src) if name.type != 'qualified_name' else text(name, u.src).rsplit('.', 1)[-1]
        for cand in (f'{word}Attribute', word) if not word.endswith('Attribute') else (word,):
            typ = self.named_type(u, node, cand)
            if typ is not None and typ.cid:
                return typ.cid
        return False

    def cs_on(self, owner, name, argc, depth):
        if owner is None or not name:
            return None, None
        if owner.cid:
            if owner.static:
                inner = self.nested[owner.cid].get(name)
                if inner:
                    return inner, None
            return (self.method(owner.cid, name, argc) or self.extension(owner, name) or False), owner
        found = self.extension(owner, name)
        if found:
            return found, None
        if name in CS_ELEMENT and (owner.name in CS_CONTAINERS or owner.name == '[]'):
            inner = owner.elem if owner.name == '[]' else self.arg(owner, 0, depth)
            return False, Elem(inner) if inner is not None else None
        if name in CS_KEEP and (owner.name in CS_CONTAINERS or owner.name == '[]'):
            return False, Elem(owner)
        if name in ('TryGetValue', 'GetValueOrDefault') and owner.name in CS_MAPS and len(owner.args) == 2:
            inner = self.arg(owner, 1, depth)
            return False, Elem(inner) if inner is not None else None
        return False, None

    def extension(self, owner, name, u=None, at=None, argc=None):
        if owner is None or name not in self.extensions:
            return None
        family = self.ancestors(owner.cid) if owner.cid else []
        for fid, eu, recv, node in self.extensions[name]:
            found = self.resolve_type(eu, node, recv)
            if found is None:
                continue
            if found.cid and found.cid in family or not found.cid and not owner.cid and found.name == owner.name:
                return fid
        return None

    # --- accesos a miembros ---

    def field_home(self, cid, name, static=False):
        """Archivo que declara el campo o la propiedad `name` de `cid` (o de una de sus partes o bases)."""
        for cur in self.ancestors(cid):
            info = self.classes.get(cur)
            if info is not None and (name in info['fields'] or static and name in self.nested[cur]):
                return info['unit'].rel if name in info['fields'] else self.g.nodes[self.nested[cur][name]]['file']
        return None

    def implicit_member(self, u, n):
        """`Name = …` o `Component.Run()` dentro de una clase: un campo o una propiedad heredados, o declarados en otra
        parte de la clase parcial (no una variable local ni un parámetro); y la clave de un inicializador `new X { Clave = … }`."""
        parent = n.parent
        if parent is None or parent.type not in CS_VALUE_PARENTS:
            return None
        name = text(n, u.src)
        if parent.type == 'assignment_expression' and parent.child_by_field_name('left') == n and parent.parent is not None and \
                parent.parent.type == 'initializer_expression':
            created = parent.parent.parent
            if created is None or created.type != 'object_creation_expression':
                return None
            owner = self.resolve_type(u, created, created.child_by_field_name('type'))
            return self.field_home(owner.cid, name) if owner is not None and owner.cid else None
        if parent.type == 'member_access_expression' and parent.child_by_field_name('expression') != n or \
                parent.type == 'assignment_expression' and parent.parent is not None and parent.parent.type == 'initializer_expression':
            return None
        if self.cs_local(u, n, name) is not False:
            return None
        for cid in self.chain(u, n):
            found = self.field_home(cid, name)
            if found:
                return found
        return None

    def members(self, u):
        out = []
        stack = [self.roots[u.rel]] if u.rel in self.roots else []
        while stack:
            n = stack.pop()
            stack.extend(n.named_children)
            if n.type == 'identifier':
                rel = self.implicit_member(u, n)
                if rel and rel != u.rel and rel not in out:
                    out.append(rel)
                continue
            if n.type != 'member_access_expression':
                continue
            parent = n.parent
            if parent is not None and parent.type == 'invocation_expression' and parent.child_by_field_name('function') == n:
                continue
            owner = self.type_of(u, n.child_by_field_name('expression'))
            name = member_name(n.child_by_field_name('name'), u.src)
            if owner is None or not owner.cid or not name:
                continue
            rel = self.field_home(owner.cid, name, owner.static)
            if rel is None:  # grupo de métodos pasado como delegado: `Func<double> f = RandomUtil.NextDouble`
                fid = self.method(owner.cid, name)
                rel = self.g.nodes[fid]['file'] if fid else None
            if rel and rel != u.rel and rel not in out:
                out.append(rel)
        return out


def ancestors(node):
    while node is not None:
        yield node
        node = node.parent


def text_of(node, src):
    return text(node, src) if node is not None else None


def is_implicit(node):
    return node is not None and node.type == 'implicit_type'


def member_name(node, src):
    if node is None:
        return None
    if node.type == 'generic_name':
        ident = next((c for c in node.named_children if c.type == 'identifier'), None)
        return text(ident, src) if ident is not None else None
    return text(node, src) if node.type == 'identifier' else None


def cs_arity(params):
    kids = [p for p in (params.named_children if params is not None else ()) if p.type == 'parameter']
    if any('params' in text_mods(p) for p in kids):
        return 0, None
    required = sum(1 for p in kids if p.child_by_field_name('default_value') is None and not any(
        c.type == 'equals_value_clause' for c in p.named_children))
    return required, len(kids)


def text_mods(p):
    return {c.text.decode('utf-8', 'replace') for c in p.named_children if c.type == 'modifier'}


def declared(holder, src, name):
    """(tipo, valor) de `name` en una `variable_declaration` de `holder`; False si no la declara."""
    for decl in holder.named_children:
        if decl.type != 'variable_declaration':
            continue
        typ = decl.child_by_field_name('type')
        for d in decl.named_children:
            if d.type != 'variable_declarator':
                continue
            ident = d.child_by_field_name('name') or next((x for x in d.named_children if x.type == 'identifier'), None)
            if ident is not None and text(ident, src) == name:
                value = next((x for x in d.named_children if x != ident and x.type != 'bracketed_argument_list'), None)
                return (None if is_implicit(typ) else typ, value)
    return False


def pattern(scope, src, name):
    stack = [scope]
    while stack:
        n = stack.pop()
        if n.type == 'declaration_pattern':
            ident = n.child_by_field_name('name')
            if ident is not None and text(ident, src) == name:
                return (n.child_by_field_name('type'), None)
        if n.type == 'declaration_expression':
            ident = n.child_by_field_name('name')
            if ident is not None and text(ident, src) == name:
                typ = n.child_by_field_name('type')
                return (None if is_implicit(typ) else typ, None)
        if n.type in CS_CLASSES or n != scope and n.type in ('lambda_expression', 'local_function_statement'):
            continue
        stack.extend(n.named_children)
    return None
