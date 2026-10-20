"""Constantes y receptores de Ruby resueltos por el árbol sintáctico.

Ruby no declara tipos, pero muchas llamadas tienen un receptor que se sabe a qué
clase pertenece sin ejecutar nada: una constante (`Thor::Options.split`), un
`X.new(…)`, una variable local o de instancia asignada con `X.new` (`printer =
ColumnPrinter.new; printer.print`), `self.class.new` o `dup`. Las constantes se
buscan como lo hace Ruby: primero en el anidamiento léxico (`class Thor; class
Option < Argument` es `Thor::Argument`), después en la raíz y, si no, por nombre
único en el proyecto. Los métodos se buscan en la clase, sus módulos
(`include`/`extend`/`prepend`, también el `base.extend(ClassMethods)` de un
`self.included`) y sus superclases.
"""
from collections import defaultdict

from .langs import RUBY_DELEGATORS, parser_for, ruby_accessors, ruby_bare, ruby_singleton, ruby_struct_class, text

CLASSES = ('class', 'module')
BOUNDARIES = ('method', 'singleton_method', 'class', 'module', 'singleton_class', 'program')
BLOCKS = ('block', 'do_block', 'lambda')
SAME_OBJECT = {'dup', 'clone', 'tap', 'freeze', 'itself'}
MIXINS = ('include', 'extend', 'prepend')
ACCESSORS = {'attr_reader': ('',), 'attr_writer': ('=',), 'attr_accessor': ('', '=')}
DYNAMIC = {'define_method', 'method_missing', 'class_eval', 'instance_eval', 'module_eval', 'class_exec', 'delegate',
           'def_delegator', 'def_delegators', 'def_instance_delegator', 'def_instance_delegators', 'forwardable'}
MAX_DEPTH = 8
RUBY_TOPLEVEL = frozenset((
    'Object', 'BasicObject', 'Module', 'Class', 'Kernel', 'Comparable', 'Enumerable', 'Enumerator', 'NilClass', 'TrueClass',
    'FalseClass', 'Integer', 'Float', 'Numeric', 'Rational', 'Complex', 'String', 'Symbol', 'Array', 'Hash', 'Range', 'Regexp',
    'MatchData', 'Struct', 'Data', 'Proc', 'Method', 'UnboundMethod', 'Binding', 'Time', 'File', 'Dir', 'IO', 'ENV', 'ARGV',
    'ARGF', 'STDIN', 'STDOUT', 'STDERR', 'Encoding', 'Exception', 'StandardError', 'RuntimeError', 'ArgumentError', 'TypeError',
    'NameError', 'NoMethodError', 'KeyError', 'IndexError', 'RangeError', 'StopIteration', 'IOError', 'EOFError', 'Errno',
    'SystemExit', 'Interrupt', 'SignalException', 'ScriptError', 'LoadError', 'NotImplementedError', 'FrozenError',
    'ZeroDivisionError', 'FloatDomainError', 'SecurityError', 'SystemCallError', 'ThreadError', 'FiberError', 'Marshal', 'Math',
    'Process', 'Signal', 'GC', 'ObjectSpace', 'Thread', 'Mutex', 'Queue', 'ConditionVariable', 'Fiber', 'Random', 'Warning',
    'Set', 'Date', 'DateTime', 'Pathname', 'URI', 'JSON', 'YAML', 'Psych', 'ERB', 'CGI', 'Logger', 'Forwardable', 'Singleton',
    'OpenStruct', 'StringIO', 'Tempfile', 'FileUtils', 'Shellwords', 'Open3', 'Benchmark', 'Digest', 'SecureRandom', 'Base64',
    'Zlib', 'Socket', 'Net', 'OptionParser', 'Timeout', 'Etc', 'PP', 'Ripper', 'Coverage', 'RbConfig', 'Gem', 'Bundler'))


class Info:
    __slots__ = ('qual', 'sites', 'methods', 'ivars', 'bases', 'mixins', 'extended', 'module', 'dynamic')

    def __init__(self, qual):
        self.qual = qual
        self.sites = []
        self.methods = defaultdict(list)
        self.ivars = defaultdict(list)
        self.bases = []
        self.mixins = []
        self.extended = []
        self.module = True
        self.dynamic = False


def const_path(node, src):
    """(raíz, [tramos]) de `A::B::C` o `::A`; None si no es una constante literal."""
    parts = []
    while node is not None and node.type == 'scope_resolution':
        name = node.child_by_field_name('name')
        if name is None or name.type != 'constant':
            return None
        parts.append(text(name, src))
        node = node.child_by_field_name('scope')
        if node is None:
            return True, parts[::-1]
    if node is None or node.type != 'constant':
        return None
    parts.append(text(node, src))
    return False, parts[::-1]


class RubyTypes:
    def __init__(self, linker):
        self.l, self.g, self.f = linker, linker.g, linker.f
        self.classes = {}
        self.by_last = defaultdict(set)
        self.quals = {}
        self.class_nodes = {}
        self.struct_blocks = {}
        self.consts = defaultdict(set)
        self.memo = {}
        self.mro_memo = {}
        self.roots = {}
        for rel in sorted(self.f.units):
            u = self.f.units[rel]
            if u.lang == 'ruby':
                tree = getattr(u, 'tree', None) or parser_for('ruby').parse(u.src)
                root = tree.root_node
                self.roots[rel] = root
                self.scan(u, root)

    # --- índice de clases y módulos ---

    def scan(self, u, root):
        stack = [(root, ())]
        while stack:
            n, nesting = stack.pop()
            t = n.type
            if t in CLASSES:
                path = const_path(n.child_by_field_name('name'), u.src)
                if path is None:
                    continue
                rooted, parts = path
                qual = '::'.join(parts if rooted or not nesting else [nesting[0]] + parts)
                info = self.classes.get(qual)
                if info is None:
                    info = self.classes[qual] = Info(qual)
                    self.by_last[parts[-1]].add(qual)
                info.module = info.module and t == 'module'
                key = u.class_keys.get(n.start_byte, parts[-1])
                cid = f'c:{u.rel}:{key}'
                info.sites.append((u, cid if cid in self.g.nodes else None))
                self.quals[(u.rel, n.start_byte)] = qual
                self.class_nodes.setdefault(u.rel, []).append(n)
                sup = n.child_by_field_name('superclass')
                if sup is not None and sup.named_children:
                    info.bases.append((u, sup.named_children[0], nesting))
                inner = (qual,) + nesting
                body = n.child_by_field_name('body')
                if body is not None:
                    self.members_of(u, info, body, key, inner)
                    stack.extend((c, inner) for c in body.named_children)
                continue
            struct = ruby_struct_class(n, u.src) if t == 'assignment' else None
            if struct:
                # `Stub = Struct.new(:a) do … end`: clase con accesores; el bloque no abre ámbito léxico de constantes
                qual = '::'.join(nesting[:1] + (struct[0],))
                info = self.classes.get(qual)
                if info is None:
                    info = self.classes[qual] = Info(qual)
                    self.by_last[struct[0]].add(qual)
                info.module = False
                key = u.class_keys.get(n.start_byte, struct[0])
                cid = f'c:{u.rel}:{key}'
                info.sites.append((u, cid if cid in self.g.nodes else None))
                self.quals[(u.rel, n.start_byte)] = qual
                for word in struct[1]:
                    if f'f:{u.rel}:{key}.{word}' in self.g.nodes:
                        info.methods[word].append((f'f:{u.rel}:{key}.{word}', False))
                if struct[2] is not None:
                    self.struct_blocks[struct[2].id] = qual
                    self.members_of(u, info, struct[2], key, nesting)
            if t == 'assignment' and n.parent is not None and n.parent.type in ('body_statement', 'program'):
                left = n.child_by_field_name('left')
                if left is not None and left.type == 'constant':
                    self.consts['::'.join(nesting[:1] + (text(left, u.src),))].add(u.rel)
                    base = class_new_base(n.child_by_field_name('right'), u.src)
                    if base is not None:
                        # `SyntaxError = Class.new(Error)`: una clase sin cuerpo cuyos métodos son los de su base
                        qual = '::'.join(nesting[:1] + (text(left, u.src),))
                        info = self.classes.get(qual)
                        if info is None:
                            info = self.classes[qual] = Info(qual)
                            self.by_last[text(left, u.src)].add(qual)
                        info.module = False
                        info.bases.append((u, base, nesting))
            if t in ('method', 'singleton_method'):
                continue
            stack.extend((c, nesting) for c in n.named_children)

    def members_of(self, u, info, body, owner, nesting):
        """Métodos, accesores, alias, mixins y variables de instancia de un cuerpo de clase o módulo."""
        stack = list(body.named_children)
        while stack:
            n = stack.pop()
            t = n.type
            if t in CLASSES:
                continue
            if t in ('method', 'singleton_method'):
                name = n.child_by_field_name('name')
                if name is None:
                    continue
                word = text(name, u.src)
                single = ruby_singleton(n)
                keys = (f'f:{u.rel}:{owner}.self.{word}',) * single + (f'f:{u.rel}:{owner}.{word}',)
                fid = next((x for x in keys if x in self.g.nodes), None)
                if fid:
                    info.methods[word].append((fid, single))
                if single and word in ('included', 'extended', 'inherited'):
                    self.included_hook(u, info, n, nesting)
                self.ivars_of(u, info, n, nesting)
                continue
            if t == 'call' and n.child_by_field_name('receiver') is None:
                self.declaration(u, info, n, owner, nesting)
            if t in ('call', 'identifier') and text(n.child_by_field_name('method') if t == 'call' else n, u.src) in DYNAMIC:
                info.dynamic = True
            elif t == 'alias':
                names = [text(c, u.src).lstrip(':') for c in n.named_children]
                if len(names) == 2:
                    info.methods.setdefault(('alias', names[0]), names[1])
            stack.extend(n.named_children)

    def declaration(self, u, info, n, owner, nesting):
        method, args = n.child_by_field_name('method'), n.child_by_field_name('arguments')
        word = text(method, u.src) if method is not None else ''
        kids = args.named_children if args is not None else []
        if word in MIXINS:
            info.mixins.extend((u, a, nesting, word) for a in kids if a.type in ('constant', 'scope_resolution'))
        elif word in ACCESSORS or word in RUBY_DELEGATORS:
            for name in ruby_accessors(n, u.src):
                fid = f'f:{u.rel}:{owner}.{name}'
                if fid in self.g.nodes:
                    info.methods[name].append((fid, ruby_singleton(n)))
        elif word == 'alias_method':
            names = [text(a, u.src).lstrip(':').strip('\'"') for a in kids if a.type in ('simple_symbol', 'string')]
            if len(names) == 2:
                info.methods.setdefault(('alias', names[0]), names[1])

    def included_hook(self, u, info, node, nesting):
        """`def self.included(base)` con `base.extend(M)`, `base.include(M)` o `base.send(:include, M)`: quien incluye el
        módulo gana esos métodos (de clase con `extend`, de instancia con `include`)."""
        stack = [node]
        while stack:
            n = stack.pop()
            stack.extend(n.named_children)
            if n.type != 'call' or n.child_by_field_name('receiver') is None:
                continue
            method, args = n.child_by_field_name('method'), n.child_by_field_name('arguments')
            word, kids = text(method, u.src) if method is not None else '', args.named_children if args is not None else []
            if word in ('send', '__send__', 'public_send') and kids and kids[0].type == 'simple_symbol':
                word, kids = text(kids[0], u.src).lstrip(':'), kids[1:]
            if word in MIXINS:
                info.extended.extend((u, a, nesting, word) for a in kids if a.type in ('constant', 'scope_resolution'))

    def ivars_of(self, u, info, method, nesting):
        stack = [method]
        while stack:
            n = stack.pop()
            stack.extend(n.named_children)
            if n.type in ('assignment', 'operator_assignment'):
                left = n.child_by_field_name('left')
                if left is not None and left.type == 'instance_variable':
                    info.ivars[text(left, u.src)].append((u, n.child_by_field_name('right'), nesting))

    # --- constantes ---

    def nesting_at(self, u, node):
        out = []
        cur = node.parent
        while cur is not None:
            if cur.type in CLASSES:
                qual = self.quals.get((u.rel, cur.start_byte))
                if qual:
                    out.append(qual)
            cur = cur.parent
        return tuple(out)

    def constant(self, u, node, nesting):
        path = const_path(node, u.src)
        if path is None:
            return None
        rooted, parts = path
        tail = '::'.join(parts)
        if rooted:
            return tail if tail in self.classes else None
        for prefix in nesting:
            cand = f'{prefix}::{tail}'
            if cand in self.classes:
                return cand
        if tail in self.classes:
            return tail
        if parts[0] in RUBY_TOPLEVEL:
            return None
        hits = [q for q in self.by_last.get(parts[-1], ()) if q == tail or q.endswith('::' + tail)]
        return hits[0] if len(hits) == 1 else None

    def value_file(self, u, node, nesting):
        """Archivo que define la constante de valor `NOMBRE` (`TEMPLATE_EXTNAME = ".tt"`) vista desde `nesting`."""
        path = const_path(node, u.src)
        if path is None:
            return None
        rooted, parts = path
        tail = '::'.join(parts)
        for cand in ([] if rooted else [f'{p}::{tail}' for p in nesting]) + [tail]:
            files = self.consts.get(cand)
            if files:
                return sorted(files)[0] if len(files) == 1 else None
        return None

    # --- herencia ---

    def resolved(self, entries):
        """Mixins o bases (`(unidad, nodo, anidamiento, …)`) resueltos a clases del proyecto."""
        out = []
        for entry in entries:
            found = self.constant(entry[0], entry[1], entry[2])
            if found:
                out.append((found, entry[3] if len(entry) > 3 else 'base'))
        return out

    def links(self, qual):
        if qual not in self.mro_memo:
            info = self.classes.get(qual)
            self.mro_memo[qual] = (self.resolved(info.mixins[::-1]), self.resolved(info.bases)) if info else ([], [])
        return self.mro_memo[qual]

    def bases(self, u):
        """(clase, base) por cada `class X < Base`, `include M` o `base.extend(M)` de `u`, con las constantes resueltas
        como Ruby."""
        out = []
        for n in self.class_nodes.get(u.rel, ()):
            qual = self.quals.get((u.rel, n.start_byte))
            info = self.classes.get(qual)
            name = const_path(n.child_by_field_name('name'), u.src)
            if info is None or name is None:
                continue
            source = f'c:{u.rel}:{u.class_keys.get(n.start_byte, name[1][-1])}'
            for entry in info.bases + info.mixins:
                if entry[0] is not u or not (n.start_byte <= entry[1].start_byte < n.end_byte):
                    continue
                found = self.constant(entry[0], entry[1], entry[2])
                target = self.site(found, u.rel) if found else None
                if target and target != source:
                    out.append((source, target))
        return out

    def site(self, qual, rel):
        """Nodo de la clase `qual`; si se reabre en varios archivos, el del archivo que se llama como ella."""
        info = self.classes.get(qual)
        cids = sorted(cid for _, cid in (info.sites if info is not None else ()) if cid)
        if not cids:
            return None
        found = self.l.pick(cids, rel)
        if found:
            return found
        stem = snake(qual.rsplit('::', 1)[-1])
        return next((c for c in cids if self.g.nodes[c]['file'].rsplit('/', 1)[-1] == f'{stem}.rb'), cids[0])

    def method(self, qual, name, rel, level='i'):
        """Método `name` de una instancia (`level` 'i') o de la propia clase ('c') de `qual`: la clase, sus módulos
        (`include`/`prepend` para instancias, `extend` para la clase) y sus superclases. Si no hay ninguno del nivel
        pedido, uno del otro nivel (`module_function`, `extend self`)."""
        found = self.lookup(qual, name, level, set())
        if found is None and self.classes[qual].module:
            found = self.lookup(qual, name, 'c' if level == 'i' else 'i', set())
        if found is None:
            return False if self.complete(qual) or self.closed(qual) else None
        return self.l.pick(found, rel)

    def complete(self, qual, seen=None):
        """Todos los ancestros de `qual` son del proyecto y ninguno define métodos en tiempo de ejecución
        (`define_method`, `method_missing`, `delegate`…): un método que no está en ellos es de Ruby."""
        seen = seen if seen is not None else set()
        if qual in seen:
            return True
        seen.add(qual)
        info = self.classes.get(qual)
        if info is None or info.dynamic or 'method_missing' in info.methods:
            return False
        mixins, bases = self.links(qual)
        if len(mixins) != len(info.mixins) or len(bases) != len(info.bases):
            return False
        return all(self.complete(q, seen) for q, _ in mixins + bases)

    def closed(self, qual, seen=None):
        """Como `complete`, pero un ancestro de fuera del proyecto (`ActiveRecord::Base`, ningún tipo del proyecto se
        llama así) también cierra la búsqueda: un método que no está en los ancestros del proyecto es de él, no de otra
        clase del proyecto que se llame igual (`Tag.active` con `scope :active` no es `HomeController#active`)."""
        seen = seen if seen is not None else set()
        if qual in seen:
            return True
        seen.add(qual)
        info = self.classes.get(qual)
        if info is None or info.dynamic or 'method_missing' in info.methods or info.extended:
            return False
        for entry in info.mixins + info.bases:
            found = self.constant(entry[0], entry[1], entry[2])
            if found:
                if not self.closed(found, seen):
                    return False
                continue
            path = const_path(entry[1], entry[0].src)
            if path is None or path[1][-1] in self.by_last:
                return False
        return True

    def lookup(self, qual, name, level, seen):
        if qual in seen or len(seen) > 40:
            return None
        seen.add(qual)
        info = self.classes.get(qual)
        if info is None:
            return None
        word = name
        for _ in range(3):
            entries = info.methods.get(word) if word in info.methods else None
            if entries:
                same = [fid for fid, single in entries if single == (level == 'c')]
                if same:
                    return same
            target = info.methods.get(('alias', word))
            if not target:
                break
            word = target
        mixins, bases = self.links(qual)
        for mod, kind in mixins:
            if (kind == 'extend') == (level == 'c'):
                found = self.lookup(mod, name, 'i', seen)
                if found:
                    return found
        for mod, kind in mixins:
            extra = self.classes.get(mod) if kind == 'include' else None
            for ext, how in self.resolved(extra.extended) if extra is not None else ():
                if (how == 'extend') == (level == 'c'):
                    found = self.lookup(ext, name, 'i', seen)
                    if found:
                        return found
        for base, _ in bases:
            found = self.lookup(base, name, level, seen)
            if found:
                return found
        return None

    # --- receptores ---

    def type_of(self, u, node, nesting, depth=0):
        """('i', clase) para una instancia, ('c', clase) para la propia clase; None si no se sabe."""
        if node is None or depth > MAX_DEPTH:
            return None
        key = (u.rel, node.start_byte, node.end_byte, node.type)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = None
        found = self.infer(u, node, nesting, depth)
        self.memo[key] = found
        return found

    def infer(self, u, node, nesting, depth):
        t = node.type
        if t in ('constant', 'scope_resolution'):
            found = self.constant(u, node, nesting)
            if found:
                return 'c', found
            path = const_path(node, u.src)
            known = path is None or path[1][0] in self.by_last or self.value_file(u, node, nesting)
            return None if known else ('x', None)
        if t == 'rescue':
            caught = node.child_by_field_name('exceptions')
            kinds = {self.type_of(u, c, nesting, depth + 1) for c in caught.named_children} if caught is not None else {None}
            kind = kinds.pop() if len(kinds) == 1 else None
            return ('i', kind[1]) if kind and kind[0] == 'c' else kind if kind and kind[0] == 'x' else None
        if t == 'parenthesized_statements' and len(node.named_children) == 1:
            return self.type_of(u, node.named_children[0], nesting, depth + 1)
        if t == 'self':
            return self.self_type(node, nesting)
        if t == 'instance_variable':
            info = self.classes.get(nesting[0]) if nesting else None
            kinds = {self.type_of(o, rhs, n, depth + 1) for o, rhs, n in (info.ivars.get(text(node, u.src), ()) if info else ())}
            return kinds.pop() if len(kinds) == 1 else None
        if t == 'identifier':
            kind = self.narrowed(u, node)
            if kind is not None:
                found = self.type_of(u, kind, nesting, depth + 1)
                if found is not None and found[0] == 'c':
                    return 'i', found[1]
            rhs = self.local(u, node)
            if rhs is not None:
                return self.type_of(u, rhs, nesting, depth + 1) if rhs is not False else None
            word = text(node, u.src)
            if word in SAME_OBJECT:
                return self.self_type(node, nesting)
            return self.foreign_value(self.self_type(node, nesting), word) if ruby_bare(node, u.src) else None
        if t == 'call':
            method = node.child_by_field_name('method')
            word = text(method, u.src) if method is not None else ''
            receiver = node.child_by_field_name('receiver')
            if receiver is None:
                here = self.self_type(node, nesting)
                if word == 'new' and here is not None and here[0] == 'c':
                    return 'i', here[1]
                return here if word in SAME_OBJECT else self.foreign_value(here, word)
            inner = self.type_of(u, receiver, nesting, depth + 1)
            if inner is None:
                return None
            if inner[0] == 'x':
                return inner
            if word == 'new' and inner[0] == 'c':
                return 'i', inner[1]
            if word == 'class' and inner[0] == 'i':
                return 'c', inner[1]
            if word in SAME_OBJECT:
                return inner
            return self.foreign_value(inner, word)
        return None

    def foreign_value(self, typ, word):
        """Valor de `x.m` cuando `m` no está en los ancestros del proyecto de una clase cerrada por uno de fuera
        (`Category.where(…)`, `comments` de un `has_many`): es de esa biblioteca, sin tipo del proyecto ('x')."""
        if typ is None or typ[0] not in ('c', 'i') or typ[1] not in self.classes or word in ('new', 'class') or \
                self.classes[typ[1]].module:
            return None
        if self.lookup(typ[1], word, typ[0], set()) or self.lookup(typ[1], word, 'c' if typ[0] == 'i' else 'i', set()):
            return None
        return ('x', None) if self.closed(typ[1]) else None

    def narrowed(self, u, ident):
        """`x.is_a?(K) && x.m`, `x.is_a?(K) ? x.m : …`, `if x.kind_of?(K) … x.m`: la clase `K` que estrecha `x` donde se
        usa (como hace Sorbet con el flujo), o None."""
        name, cur = text(ident, u.src), ident
        while cur.parent is not None and cur.parent.type not in BOUNDARIES:
            parent = cur.parent
            guard = None
            if parent.type == 'binary' and parent.child_by_field_name('right') == cur and \
                    parent.child_by_field_name('operator') is not None and text(parent.child_by_field_name('operator'), u.src) in ('&&', 'and'):
                guard = parent.child_by_field_name('left')
            elif parent.type in ('conditional', 'if', 'elsif') and parent.child_by_field_name('consequence') == cur:
                guard = parent.child_by_field_name('condition')
            elif parent.type == 'then' and parent.parent is not None and parent.parent.type in ('if', 'elsif'):
                guard = parent.parent.child_by_field_name('condition')
            kind = type_guard(guard, name, u.src) if guard is not None else None
            if kind is not None:
                return kind
            cur = parent
        return None

    def self_type(self, node, nesting):
        if not nesting:
            return None
        cur = node.parent
        while cur is not None and cur.type not in ('method', 'singleton_method', 'class', 'module', 'singleton_class'):
            cur = cur.parent
        if cur is None:
            return None
        if cur.type == 'method':
            owner = cur.parent
            while owner is not None and owner.type not in ('class', 'module', 'singleton_class'):
                if owner.id in self.struct_blocks:
                    return 'i', self.struct_blocks[owner.id]
                owner = owner.parent
            return ('c' if owner is not None and owner.type == 'singleton_class' else 'i'), nesting[0]
        return 'c', nesting[0]

    def local(self, u, ident):
        """Valor de la última asignación `x = …` (o `x ||= …`) antes de `ident` en su método; False si `x` es un
        parámetro o una variable de bloque sin asignar; None si no es una variable local."""
        name = text(ident, u.src)
        scope, blocks = ident.parent, []
        while scope is not None and scope.type not in BOUNDARIES:
            if scope.type in BLOCKS:
                blocks.append(scope)
            scope = scope.parent
        if scope is None:
            return None
        for b in blocks:
            params = b.child_by_field_name('parameters')
            if params is not None and any(param_name(p, u.src) == name for p in params.named_children):
                return False
        best = outer = None
        for start, end, right in self.assignments(u, scope).get(name, ()):
            if start >= ident.start_byte:
                break
            if end <= ident.start_byte:
                best = right
                if not self.in_other_block(right, ident, scope):
                    outer = right
        # una reasignación dentro de un bloque (`files.each do … x = f(x) end`) no cambia el tipo de la variable fuera
        # de él: Sorbet lo fija con la asignación anterior al bloque
        best = outer if outer is not None else best
        if best is not None:
            return best
        params = scope.child_by_field_name('parameters')
        if params is not None and any(param_name(p, u.src) == name for p in params.named_children):
            return False
        return None

    @staticmethod
    def in_other_block(value, ident, scope):
        cur = value.parent if value is not None else None
        while cur is not None and cur != scope:
            if cur.type in BLOCKS and not (cur.start_byte <= ident.start_byte < cur.end_byte):
                return True
            cur = cur.parent
        return False

    def assignments(self, u, scope):
        """{nombre: [(inicio, fin, valor)]} de las asignaciones a variables locales de un método (sin entrar en otros)."""
        key = ('assign', u.rel, scope.start_byte, scope.end_byte)
        if key not in self.memo:
            found, stack = {}, [scope]
            while stack:
                n = stack.pop()
                if n is not scope and n.type in BOUNDARIES:
                    continue
                var = n.child_by_field_name('variable') if n.type == 'rescue' else None
                ident = next((c for c in var.named_children if c.type == 'identifier'), None) if var is not None else None
                if ident is not None:
                    found.setdefault(text(ident, u.src), []).append((n.start_byte, var.end_byte, n))
                if n.type in ('assignment', 'operator_assignment'):
                    left = n.child_by_field_name('left')
                    if left is not None and left.type == 'identifier':
                        found.setdefault(text(left, u.src), []).append((n.start_byte, n.end_byte, n.child_by_field_name('right')))
                stack.extend(n.named_children)
            for entries in found.values():
                entries.sort(key=lambda e: e[0])
            self.memo[key] = found
        return self.memo[key]

    # --- interfaz del tipador ---

    def call(self, u, node, depth=0):
        if node.type == 'element_reference':
            return self.index(u, node), None
        if node.type == 'identifier':
            return (self.own(u, node, text(node, u.src)) if ruby_bare(node, u.src) else None), None
        if node.type != 'call':
            return None, None
        receiver, method = node.child_by_field_name('receiver'), node.child_by_field_name('method')
        if method is None or receiver is not None and receiver.type == 'super':
            return None, None
        name = text(method, u.src)
        if node.parent is not None and node.parent.type == 'assignment' and node.parent.child_by_field_name('left') == node:
            name += '='
        if receiver is None:
            return self.own(u, node, name), None
        if receiver.type == 'self':
            return None, None
        typ = self.type_of(u, receiver, self.nesting_at(u, node))
        if typ is None:
            return None, None
        if typ[0] == 'x':
            return False, None
        if typ[0] == 'c' and name == 'new':
            return self.site(typ[1], u.rel), None
        return self.method(typ[1], name, u.rel, typ[0]), None

    def own(self, u, node, name):
        """Llamada sin receptor: método del nivel del llamador (instancia o clase) en la clase y sus ancestros."""
        nesting = self.nesting_at(u, node)
        typ = self.self_type(node, nesting)
        if typ is None:
            return None
        found = self.lookup(typ[1], name, typ[0], set())
        if not found:
            return False if self.lookup(typ[1], name, 'c' if typ[0] == 'i' else 'i', set()) else None
        return self.l.pick(found, u.rel)

    def index(self, u, node):
        """`x[k]` y `x[k] = v` llaman a `[]` y `[]=` del tipo de `x`."""
        obj = node.child_by_field_name('object')
        if obj is None:
            return None
        nesting = self.nesting_at(u, node)
        typ = self.type_of(u, obj, nesting)
        if typ is None or typ[0] == 'x':
            return None
        write = node.parent is not None and node.parent.type in ('assignment', 'operator_assignment') and \
            node.parent.child_by_field_name('left') == node
        return self.method(typ[1], '[]=' if write else '[]', u.rel, typ[0])

    def members(self, u):
        """Archivos que definen las constantes (clases, módulos o valores) que `u` nombra."""
        out = []
        root = self.roots.get(u.rel)
        stack = [root] if root is not None else []
        while stack:
            n = stack.pop()
            if n.type == 'scope_resolution' or n.type == 'constant' and not (n.parent is not None and n.parent.type == 'scope_resolution'):
                if n.parent is not None and n.parent.type in CLASSES and n.parent.child_by_field_name('name') == n:
                    n = n.child_by_field_name('scope') if n.type == 'scope_resolution' else None
                    if n is None:
                        continue
                nesting = self.nesting_at(u, n)
                qual = self.constant(u, n, nesting)
                info = self.classes.get(qual) if qual else None
                files = {o.rel for o, _ in info.sites} if info is not None else set()
                home = self.site(qual, u.rel) if len(files) > 1 and u.rel not in files else None
                rel = self.g.nodes[home]['file'] if home else next(iter(files)) if len(files) == 1 else None if files else \
                    self.value_file(u, n, nesting)
                if rel and rel != u.rel and rel not in out:
                    out.append(rel)
                if n.type == 'scope_resolution':
                    continue
            stack.extend(n.named_children)
        return out


def class_new_base(node, src):
    """`Class.new(Base)` (también con bloque): el nodo de `Base`, o None."""
    if node is None or node.type != 'call':
        return None
    recv, method = node.child_by_field_name('receiver'), node.child_by_field_name('method')
    if recv is None or method is None or text(recv, src).removeprefix('::') != 'Class' or text(method, src) != 'new':
        return None
    args = node.child_by_field_name('arguments')
    first = args.named_children[0] if args is not None and args.named_children else None
    return first if first is not None and first.type in ('constant', 'scope_resolution') else None


def type_guard(cond, name, src):
    """El `K` de `name.is_a?(K)` / `kind_of?` / `instance_of?` en `cond` (o en uno de sus `&&`)."""
    while cond is not None and cond.type == 'parenthesized_statements' and len(cond.named_children) == 1:
        cond = cond.named_children[0]
    if cond is None:
        return None
    if cond.type == 'binary' and cond.child_by_field_name('operator') is not None and \
            text(cond.child_by_field_name('operator'), src) in ('&&', 'and'):
        return type_guard(cond.child_by_field_name('left'), name, src) or type_guard(cond.child_by_field_name('right'), name, src)
    if cond.type != 'call':
        return None
    recv, method, args = cond.child_by_field_name('receiver'), cond.child_by_field_name('method'), cond.child_by_field_name('arguments')
    if recv is None or recv.type != 'identifier' or text(recv, src) != name or method is None or \
            text(method, src) not in ('is_a?', 'kind_of?', 'instance_of?') or args is None or len(args.named_children) != 1:
        return None
    return args.named_children[0]


def snake(name):
    return ''.join('_' + c.lower() if c.isupper() and i else c.lower() for i, c in enumerate(name))


def param_name(node, src):
    if node.type == 'identifier':
        return text(node, src)
    name = node.child_by_field_name('name')
    if name is not None:
        return text(name, src)
    found = next((c for c in node.named_children if c.type == 'identifier'), None)
    return text(found, src) if found is not None else None
