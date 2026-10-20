import argparse
import ast
import bisect
import json
import os
import posixpath
import re
import shlex
import subprocess
import sys
import time
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'analyzer'))

import tree_sitter_ruby
from tree_sitter import Language, Parser

from cortex_graph import scip
from cortex_graph.analyze import analyze
from cortex_graph.common import Graph
from cortex_graph.langs import (RUBY_BLOCKS, RUBY_BOUNDARIES, RUST_NESTED_ITEMS as RUST_ITEMS, blank_branches, csharp_fixups,
                                decl_line, kotlin_fixups, parser_for, ruby_bare, ruby_locals, rust_cfg_off)
from cortex_graph.tsjs import FUNCTION_VALUES, TS_LANG, TSX_LANG, unwrap

FILE_KINDS = ('module',)
SPLITS = {'ajuste1': 'ajuste ronda 1', 'ajuste2': 'ajuste ronda 2', 'ajuste3': 'ajuste ronda 3', 'ajuste4': 'ajuste ronda 4',
          'ajuste5': 'ajuste ronda 5', 'ajuste6': 'ajuste ronda 6', 'ajuste7': 'ajuste ronda 7', 'control': 'control',
          'control2': 'control 2', 'control3': 'control 3', 'control4': 'control 4', 'control5': 'control 5', 'control6': 'control 6',
          'control7': 'control 7 (ciego)'}
CALL_KINDS = ('call', 'tests')
SKIP_FILE_EDGES = ('contains', 'cochange', 'http', 'rpc', 'handles', 'env', 'data', 'event', 'depends')
IMPORT_LINE = re.compile(r'\s*(import|from|use|require|include|using)\b')
RUBY_SCHEME = 'scip-ruby '
RUBY_HOLDERS = ('method', 'singleton_method', 'class', 'module', 'singleton_class')
RUBY_LANG = Language(tree_sitter_ruby.language())
RUBY_OBJECT = re.compile(r' Object#[^#]+$')
KOTLIN_HOLDERS = ('function_declaration', 'class_declaration', 'object_declaration', 'companion_object',
                  'secondary_constructor', 'getter', 'setter')
KOTLIN_EXTS = ('.kt', '.kts')
PHP_SCHEME = 'scip-php '
DOTNET_HOLDERS = ('method_declaration', 'constructor_declaration', 'destructor_declaration', 'local_function_statement',
                  'operator_declaration', 'conversion_operator_declaration', 'class_declaration', 'struct_declaration',
                  'interface_declaration', 'record_declaration', 'enum_declaration')
PHP_HOLDERS = ('method_declaration', 'function_definition', 'class_declaration', 'interface_declaration', 'trait_declaration',
               'enum_declaration')
RUST_HOLDERS = ('function_item', 'function_signature_item', 'struct_item', 'enum_item', 'union_item', 'trait_item')
OVERLOAD = re.compile(r'\(\+\d+\)\.$')
KOTLIN_LANG = parser_for('kotlin').language
RUST_LANG = parser_for('rust').language
DART_LANG = parser_for('dart').language
PHP_LANG = parser_for('php').language
CSHARP_LANG = parser_for('csharp').language
DART_CLASSES = ('class_definition', 'mixin_declaration', 'enum_declaration', 'extension_declaration', 'extension_type_declaration')
DART_CONSTRUCTORS = ('constructor_signature', 'factory_constructor_signature', 'constant_constructor_signature',
                     'redirecting_factory_constructor_signature')
DART_FUNCTIONS = ('function_signature', 'getter_signature', 'setter_signature')
PY_SCHEME = 'scip-python '
PY_MODULE = '/__init__:'
PY_RELATIVE = re.compile(r'\s*from\s+(\.+)([\w.]*)\s+import\b')
PY_ABSOLUTE = re.compile(r'\s*(?:from|import)\s+')
ACTIVE = {}
PHP_CALLS = ('member_call_expression', 'nullsafe_member_call_expression')
PHP_CHAIN = PHP_CALLS + ('member_access_expression', 'nullsafe_member_access_expression')
TS_REQUIRE_SUFFIXES = ('.ts', '.tsx', '.d.ts', '.mts', '.cts', '.js', '/index.ts', '/index.tsx', '/index.d.ts', '/index.js')
TS_HOLDERS = ('variable_declarator', 'public_field_definition', 'field_definition', 'pair', 'assignment_expression', 'method_definition')


def sh(cmd, cwd, env=None):
    subprocess.run(cmd, cwd=cwd, env=env, check=True, stdin=subprocess.DEVNULL)


def checkout(repo, work):
    dest = work / 'repos' / repo['name']
    git = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'advice.detachedHead=false']
    if not (dest / '.git').is_dir():
        dest.mkdir(parents=True, exist_ok=True)
        sh(git + ['init', '-q'], dest)
        sh(git + ['remote', 'add', 'origin', repo['url']], dest)
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=dest, capture_output=True, text=True).stdout.strip()
    if head != repo['commit']:
        sh(git + ['fetch', '-q', '--depth', '1', 'origin', repo['commit']], dest)
        sh(git + ['checkout', '-q', '--force', 'FETCH_HEAD'], dest)
    return dest / repo['subdir'] if repo.get('subdir') else dest


def fill(text, values):
    for k, v in values.items():
        text = text.replace('{' + k + '}', str(v))
    return text


def build_index(repo, src, work, tools, reuse):
    index = work / 'indexes' / f"{repo['name']}.scip"
    if reuse and index.is_file():
        return index
    index.parent.mkdir(parents=True, exist_ok=True)
    (work / 'empty-env.json').write_text('[]\n')
    values = {'src': src, 'index': index, 'work': work, 'tools': tools or work / 'tools', 'python': sys.executable, 'bench': HERE}
    env = dict(os.environ)
    extra = [str(p) for p in (tools / 'bin', tools / 'node_modules' / '.bin') if p.is_dir()] if tools else []
    env['PATH'] = os.pathsep.join(extra + [env.get('PATH', '')])
    env.update({k: fill(v, values) for k, v in (repo.get('env') or {}).items()})
    cwd = src if repo.get('cwd') == 'src' else work
    if repo.get('prepare') and not (src / 'node_modules').is_dir():
        sh(shlex.split(fill(repo['prepare'], values)), src, env)
    sh(['nice', '-n', '19'] + shlex.split(fill(repo['indexer'], values)), cwd, env)
    return index


def to_graph(out):
    g = Graph()
    by_id = {}
    for n in out['nodes']:
        g.nodes[n['key']] = {k: v for k, v in n.items() if k not in ('id', 'key', 'pos', 'c', 'deg', 'decl')}
        if n.get('decl'):
            # la definición se mide en la línea de su declaración, no en la de sus anotaciones (`@Deprecated(…)`)
            g.nodes[n['key']]['line'] = n['decl']
        by_id[n['id']] = n['key']
    for e in out['edges']:
        g.edges[(by_id[e['a']], by_id[e['b']], e['kind'])] = e['w']
    return g


def contains(outer, s):
    return (outer[0], outer[1]) <= (s[0], s[1]) and (s[2], s[3]) <= (outer[2], outer[3])


def ts_holder(tree, s):
    node = tree.root_node.named_descendant_for_point_range((s[0], s[1]), (s[2], s[3]))
    while node is not None and node.type not in TS_HOLDERS:
        node = node.parent
    return node


def holds_function(node):
    if node is None:
        return False
    value = node.child_by_field_name('right' if node.type == 'assignment_expression' else 'value')
    value = unwrap(value)
    return value is not None and value.type in FUNCTION_VALUES


def factory_function(node, sig):
    """`var stackFilter = utils.stackTraceFilter()`: una variable con firma `Function` cuyo valor es una llamada (el
    resultado de una fábrica que scip-typescript no tipa mejor) es invocable. Un campo `target: Function` sin valor no."""
    if node is None or node.type != 'variable_declarator' or not sig:
        return False
    head = scip.SIGNATURE_HEAD.match(sig)
    value = unwrap(node.child_by_field_name('value'))
    return bool(head) and sig[head.end():].strip() == 'Function' and value is not None and value.type == 'call_expression'


def alias_of(node):
    """`const f = g`, `campo = this.m`, `static crear = Clase.crear`: el nombre (o la propiedad) al que remite el valor."""
    if node is None or node.type not in ('variable_declarator', 'public_field_definition', 'field_definition'):
        return None
    value = unwrap(node.child_by_field_name('value'))
    if value is not None and value.type == 'member_expression':
        return value.child_by_field_name('property')
    return value if value is not None and value.type == 'identifier' else None


def own_module(sym, rel):
    path = sym.split(' ', 4)[-1].replace('`', '').rstrip('/')
    return path == rel or path.endswith('/' + rel) or rel.endswith('/' + path)


def ts_tree(root, rel, lang=None):
    try:
        src = (Path(root) / rel).read_bytes().replace(b'\0', b' ')
    except OSError:
        return None
    if lang is CSHARP_LANG:
        src = csharp_fixups(ACTIVE.get((str(root), rel), src))
    elif lang is KOTLIN_LANG:
        src = kotlin_fixups(src)
    return Parser(lang or (TSX_LANG if scip.jsx_file(rel) else TS_LANG)).parse(src)


def csharp_branches(docs, root):
    """El índice C# se compila con unos símbolos concretos: de cada `#if … #else … #endif` solo una rama tiene
    ocurrencias SCIP. El árbol sintáctico del benchmark (ámbitos, `: base(…)`) se construye con esa rama."""
    for d in docs:
        if not d['path'].endswith('.cs'):
            continue
        try:
            src = (Path(root) / d['path']).read_bytes()
        except OSError:
            continue
        if b'#if' not in src:
            continue
        rows = {scip.span(o[0])[0] for o in d['occurrences'] if scip.span(o[0])}
        starts = [0] + [i + 1 for i, c in enumerate(src) if c == 10]

        def choose(branches):
            for i, (start, end, _) in enumerate(branches):
                first, last = bisect.bisect_right(starts, start) - 1, bisect.bisect_right(starts, max(start, end - 1)) - 1
                if any(first < r <= last for r in rows):
                    return i
            return 0

        ACTIVE[(str(root), d['path'])] = blank_branches(src, choose)


def syntax_scope(tree, s, holders, constructor=False):
    node = tree.root_node.named_descendant_for_point_range((s[0], s[1]), (s[2], s[3]))
    while node is not None and node.type not in holders:
        node = node.parent
    if node is None or constructor and node.type != 'secondary_constructor':
        return None
    name = node.child_by_field_name('name')
    if name is None and node.start_point[0] != s[0] or name is not None and not (name.start_point <= (s[0], s[1]) and (s[2], s[3]) <= name.end_point):
        return None
    return (node.start_point[0], node.start_point[1], node.end_point[0], node.end_point[1])


def scope_syntax(sym, rel):
    if sym.startswith(RUBY_SCHEME):
        return RUBY_LANG, RUBY_HOLDERS
    if sym.startswith(scip.JVM_SCHEME) and rel.endswith(KOTLIN_EXTS):
        return KOTLIN_LANG, KOTLIN_HOLDERS
    if sym.startswith(scip.RUST_SCHEME):
        return RUST_LANG, RUST_HOLDERS
    if sym.startswith(PHP_SCHEME):
        return PHP_LANG, PHP_HOLDERS
    if sym.startswith(scip.DOTNET_SCHEME) and rel.endswith('.cs'):
        return CSHARP_LANG, DOTNET_HOLDERS
    return None


def synthetic(lines, s, sym):
    if not sym.startswith(scip.JVM_SCHEME) or scip.constructor(sym) or s[0] != s[2] or s[0] >= len(lines):
        return False
    return lines[s[0]][s[1]:s[3]].strip('`') != scip.name_of(sym)


def rust_self_type(sym, defs):
    """rust-analyzer resuelve `Self` (`Self { … }`, `Self(…)`) al bloque `impl#[Tipo]`, no al tipo: se proyecta sobre el
    tipo implementado si está definido en el mismo módulo."""
    if not sym.startswith(scip.RUST_SCHEME) or not sym.endswith(']'):
        return sym
    m = re.search(r'impl#\[(`[^`]*`|[^\]]*)\]$', sym)
    if not m:
        return sym
    owner = re.sub(r'<.*', '', m.group(1).strip('`')).strip()
    typed = sym[:m.start()] + f'{owner}#'
    return typed if re.fullmatch(r'\w+', owner) and typed in defs else sym


def rust_place(tree, s):
    """Dónde cae una ocurrencia de rust-analyzer: plantilla de `macro_rules!`, argumentos de una macro, `pub(crate)`, un ítem con `#[cfg]` inactivo en Linux o nombre de un literal struct."""
    node = tree.root_node.named_descendant_for_point_range((s[0], s[1]), (s[2], s[3])) if tree else None
    first = node
    while node is not None:
        if node.type in ('macro_definition', 'macro_rule'):
            return 'macro_rules'
        if node.type in RUST_ITEMS and rust_cfg_off(node, src_of(node)):
            return 'cfg_off'
        if node.type == 'macro_invocation':
            return 'macro'
        if node.type == 'visibility_modifier':
            return 'visibility'
        node = node.parent
    holder = first.parent if first is not None else None
    if holder is not None and holder.type == 'scoped_type_identifier' and holder.child_by_field_name('name') == first:
        first, holder = holder, holder.parent
    if holder is not None and holder.type == 'struct_expression' and holder.child_by_field_name('name') == first:
        return 'struct'
    return None


def src_of(node):
    while node.parent is not None:
        node = node.parent
    return node.text


def inner_segment(lines, s):
    """La ocurrencia es un tramo intermedio de una ruta (`crate::a::B`): le sigue `::`."""
    return s[0] < len(lines) and lines[s[0]][s[3]:].lstrip().startswith('::')


def dart_docs(docs):
    return [d for d in docs if d['path'].endswith('.dart') and any(o[1].startswith(scip.DART_SCHEME) for o in d['occurrences'])]


def dart_privates(docs, root):
    """scip-dart emite los miembros privados de librería (`_x`) como símbolos `local`; si la definición es el nombre
    de una función, método o clase (según el árbol sintáctico) se recuperan como símbolos del documento."""
    for d in dart_docs(docs):
        tree = ts_tree(root, d['path'], DART_LANG)
        if tree is None:
            continue
        renamed = {}
        own = next((o[1] for o in d['occurrences'] if o[2] & scip.DEFINITION and o[1].endswith(f"`{d['path'].rsplit('/', 1)[-1]}`/")), None)
        # dos pasadas: las clases privadas primero, para que el constructor con nombre de una clase privada
        # (`_GrowableBoolList._withCapacity`) encuentre el símbolo ya recuperado de su clase
        for rng, sym, roles, _ in [o for o in d['occurrences'] if o[2] & scip.DEFINITION] * 2:
            s = scip.span(rng)
            if not sym.startswith('local ') or not roles & scip.DEFINITION or not s or sym in renamed:
                continue
            node = tree.root_node.named_descendant_for_point_range((s[0], s[1]), (s[2], s[3]))
            holder = node.parent if node is not None else None
            if node is None or node.type != 'identifier' or holder is None:
                continue
            name = node.text.decode('utf-8', 'replace')
            owner = next((a for a in ancestors(holder) if a.type in DART_CLASSES), None)
            prefix = own or f"{scip.DART_SCHEME}local . . `{d['path']}`/"
            if owner is not None and owner != holder:
                named = owner.child_by_field_name('name') or next((c for c in owner.named_children if c.type == 'identifier'), None)
                prefix += f"{named.text.decode('utf-8', 'replace')}#" if named is not None else ''
            if holder.type in DART_CONSTRUCTORS and node == [c for c in holder.named_children if c.type == 'identifier'][-1] and owner is not None:
                klass = owner.child_by_field_name('name') or next((c for c in owner.named_children if c.type == 'identifier'), None)
                real = next((renamed.get(o[1], o[1]) for o in d['occurrences'] if o[2] & scip.DEFINITION and klass is not None and
                             tuple(o[0][:2]) == tuple(klass.start_point) and renamed.get(o[1], o[1]).endswith('#')), None)
                if real:
                    renamed[sym] = f'{real}{name}().'
            elif holder.type in DART_FUNCTIONS and holder.child_by_field_name('name') == node:
                renamed[sym] = f'{prefix}{name}().'
            elif holder.type in DART_CLASSES and (holder.child_by_field_name('name') or holder.named_children[0]) == node:
                renamed[sym] = f'{prefix}{name}#'
        if renamed:
            d['occurrences'] = [(rng, renamed.get(sym, sym), roles, enc) for rng, sym, roles, enc in d['occurrences']]


def unnamed_locals(d):
    """Ocurrencias de símbolos `local` sin definición en el documento: nombres que scip-typescript no supo resolver."""
    defined = {o[1] for o in d['occurrences'] if o[2] & scip.DEFINITION and o[1].startswith('local ')}
    return [(scip.span(o[0]), o[1]) for o in d['occurrences']
            if o[1].startswith('local ') and o[1] not in defined and not o[2] & scip.DEFINITION and scip.span(o[0])]


def ts_docs_of(docs):
    return [d for d in docs if any(o[1].startswith(scip.TS_SCHEME) for o in d['occurrences'][:50])]


def member_scopes(docs, root):
    """`exports.f = function…`, `Clase.prototype.m = function…`, `obj.m = () => …`: scip-typescript no da nombre a esos
    miembros (símbolo `local` o ninguna ocurrencia) ni `enclosing_range`; su ámbito sale del árbol sintáctico (la
    asignación) y no cuentan como definición. Devuelve (archivo, línea, nombre, ámbito)."""
    out = []
    for d in ts_docs_of(docs):
        named = {tuple(scip.span(o[0])[:2]) for o in d['occurrences'] if o[2] & scip.DEFINITION and not o[1].startswith('local ') and scip.span(o[0])}
        tree = ts_tree(root, d['path'])
        for n in ancestors_down(tree.root_node) if tree else ():
            if n.type != 'assignment_expression':
                continue
            left, right = n.child_by_field_name('left'), unwrap(n.child_by_field_name('right'))
            prop = left.child_by_field_name('property') if left is not None and left.type == 'member_expression' else None
            if prop is not None and right is not None and right.type in FUNCTION_VALUES and tuple(prop.start_point) not in named:
                out.append((d['path'], n.start_point[0] + 1, prop.text.decode('utf-8', 'replace'),
                            (n.start_point[0], n.start_point[1], n.end_point[0], n.end_point[1])))
    return out


def blind_sites(docs, root):
    """Llamadas que el indexador no resuelve nunca, comprobado en su código y en los índices: ahí no hay verdad de
    referencia y la arista que Córtex saque del mismo llamador hacia ese nombre no se puntúa.

    - scip-ruby (Sorbet) convierte `f(*args)`, `f(&bloque)` y `f(...)` en llamadas «mágicas» sin ocurrencia del método,
      y no emite ocurrencia para la lectura indexada `x[k]` (método `[]`; sí para la escritura `x[k] = v`).
    - scip-php solo tipa `$this` entre las variables: `$x->m()` (o una cadena que empieza en `$x`) nunca tiene ocurrencia.
    - scip-typescript emite un símbolo `local` sin definición en el documento cuando no sabe nombrar el destino
      (`z.string()` a través de `export { stringType as string }`); el nombre exportado se traduce a los símbolos que
      SCIP sí asocia a ese nombre en el `export`.
    - scip-dart (ronda 5): una llamada a un miembro privado (`_bubbleDown()`) cuyo símbolo `local` no es el de ninguna
      definición del documento no enlaza con su definición.

    Devuelve {archivo: [(línea, {nombres})]}."""
    out, aliases = defaultdict(list), defaultdict(set)
    ts_docs = ts_docs_of(docs)
    for d in ts_docs:
        lines = None
        for rng, sym, roles, _ in d['occurrences']:
            s = scip.span(rng)
            if not s or s[0] != s[2] or not sym.startswith(scip.TS_SCHEME) or scip.kind_of(sym) not in ('callable', 'term'):
                continue
            lines = lines if lines is not None else scip.source_lines(root, d['path']) or []
            spelled = lines[s[0]][s[1]:s[3]] if s[0] < len(lines) else ''
            if spelled and spelled != scip.name_of(sym):
                aliases[spelled].add(scip.name_of(sym))
    for d in ts_docs:
        lines = None
        for s, _ in unnamed_locals(d):
            lines = lines if lines is not None else scip.source_lines(root, d['path']) or []
            if s[0] < len(lines) and scip.called(lines, s, d['path']):
                spelled = lines[s[0]][s[1]:s[3]]
                out[d['path']].append((s[0] + 1, {spelled} | aliases.get(spelled, set())))
    for d in dart_docs(docs):
        lines = None
        for s, _ in unnamed_locals(d):
            lines = lines if lines is not None else scip.source_lines(root, d['path']) or []
            spelled = lines[s[0]][s[1]:s[3]] if s[0] < len(lines) and s[0] == s[2] else ''
            if spelled.startswith('_') and scip.called(lines, s, d['path']):
                out[d['path']].append((s[0] + 1, {spelled}))
    chains, hooked, defined, at = None, None, None, {}
    for d in docs:
        out[d['path']].extend((line, {name}) for line, name in d.get('ambiguous', ()))
        first = next((o[1] for o in d['occurrences'] if not o[1].startswith('local ')), '')
        if first.startswith(RUBY_SCHEME):
            tree, kinds = ts_tree(root, d['path'], RUBY_LANG), ('call',)
            src = (Path(root) / d['path']).read_bytes() if tree else b''
            hooked = hooked if hooked is not None else ruby_hooked(docs, root)
            defined = defined if defined is not None else {o[1] for x in docs for o in x['occurrences']
                                                            if o[2] & scip.DEFINITION and o[1].startswith(RUBY_SCHEME) and scip.kind_of(o[1]) == 'callable'}
            at = defaultdict(list)
            for rng, sym, _, _ in d['occurrences']:
                at[tuple(scip.span(rng)[:2])].append(sym)
            for n in ancestors_down(tree.root_node) if tree and hooked[1] else ():
                word = ruby_hook_call(n, src, hooked)
                if word:
                    out[d['path']].append((n.start_point[0] + 1, {word}))
        elif first.startswith(PHP_SCHEME):
            tree, kinds = ts_tree(root, d['path'], PHP_LANG), PHP_CALLS
            chains = chains if chains is not None else PhpChains(docs, root)
        elif first.startswith(scip.JVM_SCHEME) and d['path'].endswith(KOTLIN_EXTS):
            out[d['path']].extend(kotlin_annotations(ts_tree(root, d['path'], KOTLIN_LANG)))
            continue
        elif first.startswith(scip.DOTNET_SCHEME) and d['path'].endswith('.cs'):
            out[d['path']].extend(dotnet_generic_calls(ts_tree(root, d['path'], CSHARP_LANG)))
            continue
        else:
            continue
        for n in ancestors_down(tree.root_node) if tree else ():
            if n.type == 'element_reference' and kinds == ('call',) and not (
                    n.parent is not None and n.parent.type in ('assignment', 'operator_assignment') and n.parent.child_by_field_name('left') == n):
                out[d['path']].append((n.start_point[0] + 1, {'[]'}))
            if n.type not in kinds:
                continue
            name = n.child_by_field_name('method' if n.type == 'call' else 'name')
            if name is not None and n.type == 'call' and name.text == b'new' and (n.child_by_field_name('receiver') or n).text == b'self.class':
                holder = next((a for a in ancestors(n) if a.type in ('class', 'module')), None)
                named = holder.child_by_field_name('name') if holder is not None else None
                if named is not None:
                    out[d['path']].append((name.start_point[0] + 1, {named.text.split(b'::')[-1].decode('utf-8', 'replace')}))
            if name is not None and (ruby_magic(n) or ruby_untyped(n, src) or ruby_chained(n, at, defined) or
                                     ruby_untyped_local(n, src, at, defined) if n.type == 'call' else
                                     php_untyped(n, chains, d['path'])):
                spelled = name.text.decode('utf-8', 'replace')
                setter = n.type == 'call' and n.parent is not None and n.parent.type in ('assignment', 'operator_assignment') and \
                    n.parent.child_by_field_name('left') == n
                names = {spelled + '='} | ({spelled} if n.parent.type == 'operator_assignment' else set()) if setter else {spelled}
                out[d['path']].append((name.start_point[0] + 1, names))
    return out


def ruby_symbol_def(d, lines, s, sym):
    """`module_function :m` (y `private_class_method :m`): scip-ruby sitúa la definición de la copia de clase
    (`<Class:M>#m`) en el símbolo `:m`. Es el mismo método: se proyecta sobre su `def m`."""
    if not (s[0] < len(lines) and ':' in lines[s[0]][max(0, s[1] - 1):s[1] + 1] and
            re.search(r'\b(module_function|private_class_method|public_class_method)\b', lines[s[0]][:s[1]])):
        return s
    name = scip.name_of(sym)
    for rng, other, roles, _ in d['occurrences']:
        o = scip.span(rng)
        if roles & scip.DEFINITION and o and other != sym and scip.name_of(other) == name and o[0] < len(lines) and \
                re.search(r'\bdef\s+(self\.)?$', lines[o[0]][:o[1]]):
            return o
    return s


def ruby_hooked(docs, root):
    """Módulos que un `self.included`/`self.extended`/`self.inherited` añade a otra clase en tiempo de ejecución
    (`base.extend(ClassMethods)`, `base.send(:include, Shell)`) y los nombres de sus métodos. Sorbet no ejecuta esos
    ganchos: ninguna referencia de fuera del módulo apunta a sus métodos (0 en thor; 66 desde dentro)."""
    trees = [ts_tree(root, d['path'], RUBY_LANG) for d in docs if d['path'].endswith('.rb')]
    modules, names = set(), {}
    for tree in trees:
        for n in ancestors_down(tree.root_node) if tree else ():
            name = n.child_by_field_name('name') if n.type in ('method', 'singleton_method') else None
            if name is None or name.text not in (b'included', b'extended', b'inherited'):
                continue
            for c in ancestors_down(n):
                args = c.child_by_field_name('arguments') if c.type == 'call' and c.child_by_field_name('receiver') is not None else None
                modules.update(a.text.split(b'::')[-1] for a in (args.named_children if args else ()) if a.type in ('constant', 'scope_resolution'))
    for tree in trees:
        for n in ancestors_down(tree.root_node) if tree and modules else ():
            module = n.child_by_field_name('name').text.split(b'::')[-1] if n.type == 'module' else None
            for m in ancestors_down(n) if module in modules else ():
                if m.type == 'method':
                    names.setdefault(m.child_by_field_name('name').text, set()).add(module)
    return modules, names


def ruby_hook_call(n, src, hooked):
    """Nombre de una llamada a un método de un módulo de `ruby_hooked` hecha fuera de ese módulo."""
    if n.type == 'call':
        name = n.child_by_field_name('method')
    elif n.type == 'identifier' and ruby_bare(n, src):
        name = n
    else:
        return None
    homes = hooked[1].get(name.text) if name is not None else None
    if not homes or any(a.type == 'module' and a.child_by_field_name('name').text.split(b'::')[-1] in homes for a in ancestors(n)):
        return None
    return name.text.decode('utf-8', 'replace')


def kotlin_annotations(tree):
    """semanticdb-kotlinc no emite ocurrencia para el nombre de una anotación (`@SinceKtlint("0.39", EXPERIMENTAL)`): 0 de 155
    usos de anotaciones del proyecto en ktlint (0 de ~660 anotaciones en ktlint, http4k, javalin y moshi apuntan a una
    clase del proyecto). La instanciación que Córtex ve ahí no se mide."""
    out = []
    for n in ancestors_down(tree.root_node) if tree else ():
        ut = next((c for c in n.named_children if c.type in ('user_type', 'constructor_invocation')), None) if n.type == 'annotation' else None
        while ut is not None and ut.type == 'constructor_invocation':
            ut = next((c for c in ut.named_children if c.type == 'user_type'), None)
        names = [c for c in ut.named_children if c.type in ('identifier', 'type_identifier')] if ut is not None else []
        if names:
            word = {names[-1].text.decode('utf-8', 'replace')}
            out.append((names[-1].start_point[0] + 1, word))
            # el nodo de Córtex empieza en la declaración anotada, no en la anotación (ronda 5)
            holder = n.parent.parent if n.parent is not None and n.parent.type == 'modifiers' else None
            if holder is not None and decl_line(holder) != names[-1].start_point[0] + 1:
                out.append((decl_line(holder), word))
    return out


def dotnet_generic_calls(tree):
    """scip-dotnet no emite ocurrencias para un nombre con argumentos de tipo (`generic_name`): ni el método de
    `lista.Find<T>()` ni la clase de `new Caja<T>()` o de `: base(…)` cuando la base es `Base<T>` (0 de 620 nombres
    genéricos en markdig, 0 de 240 en serilog y 0 de 860 en stateless)."""
    out = []
    for n in ancestors_down(tree.root_node) if tree else ():
        name = None
        if n.type == 'invocation_expression':
            fn = n.child_by_field_name('function')
            name = fn.child_by_field_name('name') if fn is not None and fn.type == 'member_access_expression' else fn
        elif n.type == 'object_creation_expression':
            name = n.child_by_field_name('type')
        elif n.type == 'constructor_initializer' and n.text.lstrip(b': \t\n').startswith(b'base') and n.parent is not None and \
                n.parent.parent is not None:
            bases = next((c for c in n.parent.parent.parent.named_children if c.type == 'base_list'), None) \
                if n.parent.parent.parent is not None else None
            name = bases.named_children[0] if bases is not None and bases.named_children else None
        if name is not None and name.type == 'qualified_name':
            name = name.child_by_field_name('name')
        if name is not None and name.type == 'generic_name' and name.named_children:
            out.append((n.start_point[0] + 1 if n.type == 'constructor_initializer' else name.start_point[0] + 1,
                        {name.named_children[0].text.decode('utf-8', 'replace')}))
    return out


def dotnet_events(docs, root):
    """scip-dotnet da a los eventos (`public event Delegado? Cerrado;`) el sufijo de tipo (`Clase#Cerrado#`): son
    miembros, no tipos; se renombran como términos."""
    events = set()
    for d in docs:
        if not d['path'].endswith('.cs'):
            continue
        lines = None
        for rng, sym, roles, _ in d['occurrences']:
            s = scip.span(rng)
            if roles & scip.DEFINITION and sym.startswith(scip.DOTNET_SCHEME) and sym.endswith('#') and s and s[0] == s[2]:
                lines = lines if lines is not None else scip.source_lines(root, d['path']) or []
                if s[0] < len(lines) and re.search(r'\bevent\b', lines[s[0]][:s[1]]):
                    events.add(sym)
    for d in docs if events else ():
        d['occurrences'] = [(rng, sym[:-1] + '.' if sym in events else sym, roles, enc) for rng, sym, roles, enc in d['occurrences']]


def shared_symbols(docs, root):
    """Un mismo símbolo SCIP para definiciones distintas en varios archivos:

    - scip-dotnet nombra los tipos solo con el último tramo del espacio de nombres (`Inlines/LinkInlineRenderer#`):
      clases homónimas de `Markdig.Renderers.Html.Inlines` y `…Normalize.Inlines` comparten símbolo, y sus miembros
      también (salvo las partes de una clase `partial`, que sí son el mismo tipo).
    - semanticdb-kotlinc numera las sobrecargas (`f(+1).`) dentro de cada archivo: funciones de nivel superior homónimas
      del mismo paquete en archivos distintos (extensiones `map` sobre receptores distintos) comparten `paquete/map().`.

    Cada definición recibe un símbolo propio (con su ruta) y las referencias, que no se sabe a cuál apuntan, dejan de
    ser verdad de referencia: se anotan en `d['ambiguous']` como (línea, nombre) para no puntuar la arista de Córtex
    del mismo sitio."""
    homes = defaultdict(dict)
    for d in docs:
        dotnet, kotlin = d['path'].endswith('.cs'), d['path'].endswith(KOTLIN_EXTS)
        if not dotnet and not kotlin:
            continue
        lines = None
        for rng, sym, roles, _ in d['occurrences']:
            s = scip.span(rng)
            if not roles & scip.DEFINITION or not s:
                continue
            if dotnet and sym.startswith(scip.DOTNET_SCHEME) and sym.endswith('#'):
                lines = lines if lines is not None else scip.source_lines(root, d['path']) or []
                homes[sym][d['path']] = s[0] < len(lines) and re.search(r'\bpartial\b', lines[s[0]]) is not None
            elif kotlin and sym.startswith(scip.JVM_SCHEME) and scip.kind_of(sym) == 'callable' and \
                    '#' not in sym.rsplit(' ', 1)[-1]:
                homes[sym][d['path']] = False
    shared = {sym for sym, where in homes.items() if len(where) > 1 and not all(where.values())}
    if not shared:
        return
    for d in docs:
        if not d['path'].endswith(('.cs',) + KOTLIN_EXTS):
            continue
        tag = re.sub(r'\W', '_', d['path'])
        fixed, lines = [], None
        for rng, sym, roles, enc in d['occurrences']:
            owner = next((sym[:i + 1] for i, c in enumerate(sym) if c in '#.' and sym[:i + 1] in shared), None) \
                if sym.startswith((scip.DOTNET_SCHEME, scip.JVM_SCHEME)) else None
            if owner is not None:
                s = scip.span(rng)
                if roles & scip.DEFINITION and d['path'] in homes[owner]:
                    head, _, tail = owner.rpartition(' ')
                    sym = f'{head} {tag}/{tail}' + sym[len(owner):]
                elif s:
                    lines = lines if lines is not None else scip.source_lines(root, d['path']) or []
                    spelled = lines[s[0]][s[1]:s[3]] if s[0] < len(lines) and s[0] == s[2] else ''
                    d.setdefault('ambiguous', []).append((s[0] + 1, spelled or scip.name_of(sym)))
                    sym = f'local ambiguous {sym}'
            fixed.append((rng, sym, roles, enc))
        d['occurrences'] = fixed


def dotnet_generic_names(docs, root):
    """Nombres que un archivo C# solo usa con argumentos de tipo (`Base<T>`, `Caja<T>`, `M<T>()`): scip-dotnet no
    emite ocurrencia para ellos, así que una dependencia de Córtex apoyada solo en esos nombres no se puntúa."""
    out = {}
    for d in docs:
        if not d['path'].endswith('.cs') or not any(o[1].startswith(scip.DOTNET_SCHEME) for o in d['occurrences'][:50]):
            continue
        tree = ts_tree(root, d['path'], CSHARP_LANG)
        names = {n.named_children[0].text.decode('utf-8', 'replace') for n in ancestors_down(tree.root_node)
                 if n.type == 'generic_name' and n.named_children} if tree else set()
        names |= {name for _, name in d.get('ambiguous', ())}
        if names:
            out[d['path']] = names
    return out


def dotnet_unnamed(docs):
    """Métodos que scip-dotnet define bajo `<invalid-global-code>` (no supo nombrar su tipo): sus llamadas no llevan ese
    símbolo (ronda 5: 0 de 48 sitios en polly, 1 de 76 en markdig, 0 de 9 en serilog), así que la arista de Córtex hacia
    ellos no se puntúa. {(archivo, línea, nombre)}"""
    out = set()
    for d in docs:
        for rng, sym, roles, _ in d['occurrences']:
            s = scip.span(rng)
            if roles & scip.DEFINITION and s and sym.startswith(scip.DOTNET_SCHEME) and '`<invalid-global-code>`#' in sym and \
                    scip.kind_of(sym) == 'callable':
                out.add((d['path'], s[0] + 1, plain(sym)))
    return out


def php_unnamed_functions(docs, root):
    """Funciones de PHP sin definición SCIP. scip-php nombra una función solo si está cargada (`function_exists`) o en
    los stubs de PhpStorm, y `index_php.py` vacía las listas `autoload.files` para no ejecutar código del repo
    (`app/App/helpers.php` de bookstack): ni la definición ni sus llamadas tienen símbolo, así que la arista de Córtex
    hacia ellas no se puntúa ni el nodo cuenta como definición de más. {(archivo, línea, nombre)}"""
    out = set()
    # los homónimos de una función de PHP (`function error_log` que una prueba define para sustituirla) sí se enlazan
    builtin = {sym.split(' ')[-1][:-3] for d in docs for _, sym, _, _ in d['occurrences']
               if sym.startswith(PHP_SCHEME + 'composer php ') and sym.endswith('().')}
    for d in docs:
        if not any(o[1].startswith(PHP_SCHEME) for o in d['occurrences'][:50]):
            continue
        tree = ts_tree(root, d['path'], PHP_LANG)
        if tree is None:
            continue
        defined = {tuple(scip.span(rng)[:2]) for rng, sym, roles, _ in d['occurrences'] if roles & scip.DEFINITION and scip.span(rng)}
        for n in ancestors_down(tree.root_node):
            name = n.child_by_field_name('name') if n.type == 'function_definition' else None
            if name is not None and tuple(name.start_point) not in defined and name.text.decode('utf-8', 'replace') not in builtin:
                out.add((d['path'], name.start_point[0] + 1, name.text.decode('utf-8', 'replace')))
    return out


def dotnet_type_homes(docs):
    """Tipos que define cada archivo C#. Una dependencia de tipo de Córtex (`import`) hacia un archivo cuyo tipo el
    origen solo escribe con argumentos (`Func<FallbackActionArguments<T>, …>`) no tiene ocurrencia SCIP (ronda 5: 0 de
    415 nombres genéricos de tipos del proyecto en polly, frente a 1151 de 1165 sin argumentos) y no se puntúa."""
    out = defaultdict(set)
    for d in docs:
        for rng, sym, roles, _ in d['occurrences']:
            if roles & scip.DEFINITION and sym.startswith(scip.DOTNET_SCHEME) and scip.kind_of(sym) == 'type':
                out[d['path']].add(scip.name_of(sym))
    return out


def ruby_magic(call):
    args = call.child_by_field_name('arguments')
    return any(a.type in ('splat_argument', 'forward_argument') or
               a.type == 'block_argument' and not any(x.type == 'simple_symbol' for x in a.named_children)
               for a in (args.named_children if args is not None else ()))


def ruby_untyped(call, src):
    """Receptor sin tipo para Sorbet sin firmas: una variable de instancia (o de clase/global) o un método sin `sig`
    llamado sin receptor (`request.path`), también al principio de una cadena (`request.env.fetch`); un parámetro del
    método o del bloque que no se reasigna antes (`klass.namespace`, `|command| command.usage`), y `self.class` dentro
    de un método de un módulo (la clase que lo incluye no se conoce)."""
    node = call.child_by_field_name('receiver')
    while node is not None and node.type == 'call' and node.child_by_field_name('receiver') is not None:
        node = node.child_by_field_name('receiver')
    if node is not None and node.type == 'self' and node.parent.type == 'call' and node.parent.child_by_field_name('method') is not None \
            and node.parent.child_by_field_name('method').text == b'class':
        holder = next((a for a in ancestors(node) if a.type in ('class', 'module', 'singleton_class')), None)
        return holder is not None and holder.type == 'module'
    if node is not None and node.type == 'call':
        node = node.child_by_field_name('method')
        return node is not None and node.type == 'identifier'
    if node is None or node.type not in ('identifier', 'instance_variable', 'class_variable', 'global_variable'):
        return False
    return node.type != 'identifier' or not ruby_local(node, src) or ruby_param(node)


def ruby_chained(call, at, defined):
    """Receptor que es el resultado de un método del proyecto (`Jekyll.logger.info`) o de una lectura indexada
    (`registers[:site].filter_cache`): sin `sig`, Sorbet lo devuelve `T.untyped` (0 de 233 y 0 de 186 llamadas así en
    jekyll, thor, rack y sinatra se resuelven a un método del proyecto). `X.new` sí tiene tipo."""
    recv = call.child_by_field_name('receiver')
    if recv is not None and recv.type == 'element_reference':
        return True
    inner = recv.child_by_field_name('method') if recv is not None and recv.type == 'call' else None
    return inner is not None and inner.text != b'new' and any(s in defined for s in at.get(tuple(inner.start_point), ()))


def ruby_untyped_value(value, src, at, defined):
    """Valor que Sorbet sin firmas deja `T.untyped`: la llamada a un método del proyecto (sin `sig`), con o sin receptor,
    o una llamada sobre un receptor sin tipo (`@parse_context.new_parser(x)`, `registers[:site]`). `X.new` sí tiene tipo."""
    if value is None:
        return False
    if value.type in ('instance_variable', 'class_variable', 'global_variable', 'element_reference'):
        return True
    if value.type == 'identifier':
        return not ruby_local(value, src) and any(s in defined for s in at.get(tuple(value.start_point), ()))
    if value.type != 'call':
        return False
    method = value.child_by_field_name('method')
    if method is None or method.text == b'new':
        return False
    return any(s in defined for s in at.get(tuple(method.start_point), ())) or ruby_untyped(value, src) or \
        ruby_chained(value, at, defined)


def ruby_untyped_local(call, src, at, defined):
    """Receptor que es una variable local asignada (antes, en el mismo método) solo con valores sin tipo para Sorbet
    (`p = @parse_context.new_parser(lhs); p.consume(:id)`): la variable también es `T.untyped`."""
    recv = call.child_by_field_name('receiver')
    if recv is None or recv.type != 'identifier' or not ruby_local(recv, src) or ruby_param(recv):
        return False
    scope = recv.parent
    while scope is not None and scope.type not in RUBY_BOUNDARIES:
        scope = scope.parent
    if scope is None:
        return False
    values = [n.child_by_field_name('right') for n in ancestors_down(scope) if n.type == 'assignment' and n.end_byte <= call.start_byte
              and n.child_by_field_name('left') is not None and n.child_by_field_name('left').text == recv.text]
    return bool(values) and all(ruby_untyped_value(v, src, at, defined) for v in values)


def ruby_param(ident):
    """Parámetro (de método o de bloque) que no se reasigna antes de `ident`: Sorbet lo tipa `T.untyped` sin firma."""
    name, scope = ident.text, ident.parent
    while scope is not None:
        if scope.type in RUBY_BLOCKS or scope.type in RUBY_BOUNDARIES:
            params = scope.child_by_field_name('parameters')
            names = [(p if p.type == 'identifier' else p.child_by_field_name('name') or
                      next((c for c in p.named_children if c.type == 'identifier'), p)).text for p in (params.named_children if params else ())]
            if name in names:
                return not any(n.type in ('assignment', 'operator_assignment') and n.end_byte <= ident.start_byte and
                               n.child_by_field_name('left') is not None and n.child_by_field_name('left').text == name
                               for n in ancestors_down(scope))
            if scope.type in RUBY_BOUNDARIES:
                return False
        scope = scope.parent
    return False


def ruby_local(ident, src):
    name, scope = ident.text.decode('utf-8', 'replace'), ident.parent
    while scope is not None:
        if (scope.type in RUBY_BLOCKS or scope.type in RUBY_BOUNDARIES) and name in ruby_locals(scope, src):
            return True
        if scope.type in RUBY_BOUNDARIES:
            return False
        scope = scope.parent
    return False


def php_untyped(call, chains=None, rel=None):
    """Receptor que scip-php no tipa: una variable que no es `$this` (también indexada, `$x[0]->m()`), una constante o
    caso de enum (`Bom::Utf8->m()`: `Types::type()` no trata `ClassConstFetch`) o una llamada de la cadena cuyo
    resultado no tiene tipo (ver `PhpChains`)."""
    node = call.child_by_field_name('object')
    while node is not None and node.type in PHP_CHAIN + ('parenthesized_expression', 'subscript_expression'):
        if chains is not None and node.type in PHP_CALLS + ('scoped_call_expression',) and chains.untyped(rel, node):
            return True
        node = node.named_children[0] if node.type in ('parenthesized_expression', 'subscript_expression') else \
            node.child_by_field_name('object')
    if chains is not None and node is not None and node.type == 'scoped_call_expression' and chains.untyped(rel, node):
        return True
    if chains is not None and node is not None and node.type == 'function_call_expression' and chains.unnamed(rel, node):
        return True
    if node is not None and node.type == 'class_constant_access_expression':
        return True
    return node is not None and node.type == 'variable_name' and node.text != b'$this'


class PhpChains:
    """scip-php da tipo al resultado de una llamada con el tipo de retorno de su definición (`Types::type()`):
    `TypeParser::parse` solo convierte nombres de clase completos, así que un retorno nativo `self`/`static` sin
    `@return` en el PHPDoc queda sin tipo, y una llamada sin ocurrencia SCIP tampoco tiene tipo. Lo que se llame
    sobre ese resultado (`Reader::fromString($s)->setDelimiter(';')`) nunca tiene ocurrencia."""

    def __init__(self, docs, root):
        self.root, self.at, self.defs, self.trees = root, {}, {}, {}
        for d in docs:
            for rng, sym, roles, _ in d['occurrences']:
                s = scip.span(rng)
                if s and sym.startswith(PHP_SCHEME):
                    self.at.setdefault((d['path'], s[0], s[1]), sym)
                    if roles & scip.DEFINITION:
                        self.defs.setdefault(sym, (d['path'], s[0], s[1]))

    def tree(self, rel):
        if rel not in self.trees:
            self.trees[rel] = ts_tree(self.root, rel, PHP_LANG)
        return self.trees[rel]

    def unnamed(self, rel, call):
        """`user()->can(…)`: una función sin ocurrencia SCIP (ver `php_unnamed_functions`) no da tipo a la cadena."""
        fn = call.child_by_field_name('function')
        return fn is not None and fn.type in ('name', 'qualified_name') and (rel, *fn.start_point) not in self.at

    def untyped(self, rel, call):
        name = call.child_by_field_name('name')
        sym = self.at.get((rel, *name.start_point)) if name is not None else None
        if sym is None:
            return True
        where = self.defs.get(sym)
        tree = self.tree(where[0]) if where else None
        node = tree.root_node.named_descendant_for_point_range(where[1:], where[1:]) if tree else None
        while node is not None and node.type != 'method_declaration':
            node = node.parent
        ret = node.child_by_field_name('return_type') if node is not None else None
        if ret is None or ret.text.decode('utf-8', 'replace').lstrip('?') not in ('self', 'static'):
            return False
        prev = node.prev_named_sibling
        while prev is not None and prev.type == 'attribute_list':
            prev = prev.prev_named_sibling
        return not (prev is not None and prev.type == 'comment' and b'@return' in prev.text)


def python_relative_modules(docs, root):
    """scip-python nombra los módulos de un import relativo (`from ._api import *`, `from . import json`) solo con su
    último tramo (`_api/__init__:`), sin el paquete, así que la referencia no coincide con la definición del módulo
    (`` `httpx._api`/__init__: ``). Se resuelve con la sintaxis del import y el nombre del módulo que importa.

    Ronda 6: lo mismo ocurre con un submódulo importado como miembro (`from marshmallow import fields as ma_fields`: el
    import y cada uso `ma_fields.Field` llevan `fields/__init__:`), y con una raíz de fuentes (`src/marshmallow/`) la
    definición lleva la ruta desde la raíz del proyecto (`` `src.marshmallow.exceptions`/__init__: ``) y la referencia el
    nombre importado (`` `marshmallow.exceptions`/__init__: ``). Una referencia del propio proyecto sin definición se enlaza
    con el único módulo definido cuyo nombre termina en ella; si es la ruta de un import absoluto (`from X import`,
    `import X`), solo quitando carpetas que no son paquete (`src`), para no confundir un paquete externo con un submódulo
    homónimo."""
    modules, own = {}, {}
    for d in docs:
        for rng, sym, roles, _ in d['occurrences']:
            if roles & scip.DEFINITION and sym.startswith(PY_SCHEME) and sym.endswith(PY_MODULE):
                name = sym.split(' ', 4)[-1][:-len(PY_MODULE)].strip('`')
                modules.setdefault(name, sym)
                own.setdefault(d['path'], name)
    defined = set(modules.values())
    tails = defaultdict(set)
    for name, sym in modules.items():
        parts, rooted = name.split('.'), True
        for i in range(1, len(parts)):
            rooted = rooted and not (Path(root) / '/'.join(parts[:i]) / '__init__.py').is_file()
            tails[(sym.rsplit(' ', 1)[0], '.'.join(parts[i:]))].add((name, rooted))
    for d in docs:
        here, lines = own.get(d['path']), None
        if here is None:
            continue
        package = here if d['path'].endswith('__init__.py') else here.rpartition('.')[0]
        fixed, external = [], set()
        for rng, sym, roles, enc in d['occurrences']:
            s = scip.span(rng)
            if not roles & scip.DEFINITION and sym.startswith(PY_SCHEME) and sym.endswith(PY_MODULE) and sym not in defined and s:
                lines = lines if lines is not None else scip.source_lines(root, d['path']) or []
                m = PY_RELATIVE.match(lines[s[0]]) if s[0] < len(lines) else None
                if m:
                    base = package.split('.') if package else []
                    base = base[:len(base) - (len(m.group(1)) - 1)] if len(m.group(1)) > 1 else base
                    spelled = lines[s[0]][s[1]:s[3]]
                    rest = spelled.lstrip('.') if spelled.startswith('.') else '.'.join(filter(None, [m.group(2), spelled.split()[0]]))
                    target = modules.get('.'.join(base + ([rest] if rest else [])))
                    sym = target or sym
                elif s[0] < len(lines):
                    name = sym.split(' ', 4)[-1][:-len(PY_MODULE)].strip('`')
                    head = PY_ABSOLUTE.match(lines[s[0]])
                    absolute = head is not None and head.end() == s[1]
                    homes = {home for home, rooted in tails.get((sym.rsplit(' ', 1)[0], name), ()) if rooted or not absolute}
                    if absolute and len(homes) != 1:
                        external.add(sym)  # `import apprise` externo: sus usos (`apprise.Apprise()`) tampoco se enlazan
                    elif len(homes) == 1:
                        sym = (sym, modules[homes.pop()])
            fixed.append((rng, sym, roles, enc))
        d['occurrences'] = [(rng, sym if isinstance(sym, str) else sym[0] if sym[0] in external else sym[1], roles, enc)
                            for rng, sym, roles, enc in fixed]


def ancestors(node):
    while node is not None:
        yield node
        node = node.parent


def dart_constructors(docs, root):
    """Constructores sin nombre de Dart por sintaxis: (archivo, línea, nombre, clase). Como en el resto de lenguajes, no
    son una definición aparte y llamarlos es instanciar su clase. scip-dart trata los constructores con nombre
    (`Element.text(…)`) como miembros con ese nombre, y así se cuentan."""
    out = []
    for d in dart_docs(docs):
        tree = ts_tree(root, d['path'], DART_LANG)
        for n in ancestors_down(tree.root_node) if tree else ():
            if n.type not in DART_CONSTRUCTORS:
                continue
            idents = [c for c in n.named_children if c.type == 'identifier']
            owner = next((a for a in ancestors(n) if a.type in DART_CLASSES), None)
            klass = (owner.child_by_field_name('name') or next((c for c in owner.named_children if c.type == 'identifier'), None)) \
                if owner is not None else None
            if idents and klass is not None and idents[-1].text == klass.text:
                out.append((d['path'], n.start_point[0] + 1, idents[-1].text.decode(), klass.text.decode()))
    return out


def dart_directives(docs, root):
    """scip-dart no emite ocurrencias para `import`/`export`; la dependencia que declaran sale de la URI."""
    package = re.search(r'^name:\s*([\w-]+)', (Path(root) / 'pubspec.yaml').read_text(errors='replace'), re.M) \
        if (Path(root) / 'pubspec.yaml').is_file() else None
    paths = {d['path'] for d in docs}
    out = {}
    for d in dart_docs(docs):
        tree = ts_tree(root, d['path'], DART_LANG)
        for node in (tree.root_node.named_children if tree is not None else ()):
            if node.type != 'import_or_export':
                continue
            lit = next((n for n in ancestors_down(node) if n.type == 'string_literal'), None)
            uri = lit.text.decode('utf-8', 'replace').strip('\'"') if lit is not None else ''
            if package and uri.startswith(f'package:{package.group(1)}/'):
                target = 'lib/' + uri.split('/', 1)[1]
            elif ':' in uri or not uri:
                continue
            else:
                target = posixpath.normpath(posixpath.join(posixpath.dirname(d['path']), uri))
            if target in paths and target != d['path']:
                out.setdefault((d['path'], target), (node.start_point[0] + 1, f'{scip.DART_SCHEME}pub . . `{target}`/'))
    return out


def ruby_requires(docs, root):
    """scip-ruby no emite ocurrencias para `require`/`require_relative`/`load`/`autoload`: la dependencia que declaran sale
    de la ruta (relativa al archivo con `require_relative`; relativa a la raíz medida, que es la del `$LOAD_PATH`, en el
    resto)."""
    paths, out = {d['path'] for d in docs}, {}
    for d in docs:
        if not d['path'].endswith('.rb') or not any(o[1].startswith(RUBY_SCHEME) for o in d['occurrences'][:50]):
            continue
        tree = ts_tree(root, d['path'], RUBY_LANG)
        for n in ancestors_down(tree.root_node) if tree else ():
            method, args = n.child_by_field_name('method'), n.child_by_field_name('arguments')
            if n.type != 'call' or method is None or args is None or n.child_by_field_name('receiver') is not None:
                continue
            word = method.text.decode()
            lits = [a for a in args.named_children if a.type == 'string']
            if word not in ('require', 'require_relative', 'load', 'autoload') or not lits or \
                    any(c.type == 'interpolation' for c in lits[-1].named_children):
                continue
            spec = lits[-1].text.decode('utf-8', 'replace').strip('\'"')
            base = posixpath.dirname(d['path']) if word == 'require_relative' else ''
            target = posixpath.normpath(posixpath.join(base, spec))
            target += '' if target.endswith('.rb') else '.rb'
            if target in paths and target != d['path']:
                out.setdefault((d['path'], target), (n.start_point[0] + 1, f'{RUBY_SCHEME}file . . `{target}`/'))
    return out


def ts_requires(docs, root):
    """En archivos TypeScript, `require('./m')` es la función `require` de Node (devuelve `any`): scip-typescript no emite
    ocurrencia del módulo (0 de 91 en hexo; en JavaScript sí, 180 de 186 en mocha y express). La dependencia que declara
    sale de la ruta, resuelta como la resuelve TypeScript."""
    paths, out = {d['path'] for d in docs}, {}
    for d in ts_docs_of(docs):
        if not d['path'].endswith(scip.TS_EXTS):
            continue
        tree = ts_tree(root, d['path'])
        for n in ancestors_down(tree.root_node) if tree else ():
            fn, args = n.child_by_field_name('function'), n.child_by_field_name('arguments')
            if n.type != 'call_expression' or fn is None or fn.type != 'identifier' or fn.text != b'require' or args is None:
                continue
            lits = [a for a in args.named_children if a.type != 'comment']
            if len(lits) != 1 or lits[0].type != 'string':
                continue
            spec = lits[0].text.decode('utf-8', 'replace')[1:-1]
            if not spec.startswith('.'):
                continue
            base = posixpath.normpath(posixpath.join(posixpath.dirname(d['path']), spec))
            target = next((c for c in [base] + [base + e for e in TS_REQUIRE_SUFFIXES] if c in paths), None)
            if target and target != d['path']:
                out.setdefault((d['path'], target), (n.start_point[0] + 1, f'{scip.TS_SCHEME}npm . . `{target}`/'))
    return out


def ancestors_down(node):
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.named_children))


def is_call(lines, s, sym, rel, place=None):
    if place == 'struct' and scip.kind_of(sym) == 'type':
        return True
    if sym.startswith(PHP_SCHEME) and scip.kind_of(sym) == 'type' and s[0] < len(lines) and \
            re.search(r'\bnew\s+\\?$', lines[s[0]][:s[1]]):
        return True
    if sym.startswith(scip.DOTNET_SCHEME) and scip.kind_of(sym) == 'type' and s[0] < len(lines) and \
            re.search(r'\bnew\s+$', lines[s[0]][:s[1]]) and lines[s[0]][s[3]:].lstrip()[:1] in ('', '{'):
        return True  # `new X { … }`: instanciación con inicializador y sin paréntesis
    if sym.startswith(RUBY_SCHEME):
        if scip.kind_of(sym) == 'type':
            line = lines[s[0]] if s[0] < len(lines) else ''
            return line[s[3]:].startswith('.new')
        return True
    if sym.startswith(scip.JVM_SCHEME) and rel.endswith(KOTLIN_EXTS) and scip.kind_of(sym) == 'type' and s[0] < len(lines) and \
            not re.search(r'(:|,|->|<|\bis|\bas\??|\bclass|\binterface|\bobject|@)\s*$', kotlin_before(lines, s)):
        return scip.called(lines, s, rel, True)  # `Filter { … }`: constructor SAM de una `fun interface`
    return scip.called(lines, s, rel, scip.kind_of(sym) == 'callable')


def kotlin_before(lines, s):
    """Código antes del nombre de un tipo de Kotlin, sin su calificación (`Rule.`) y desde la línea anterior si el nombre
    abre la línea (`StandardRule(…),⏎ Rule.OfficialCodeStyle {` es la lista de supertipos, no un constructor SAM)."""
    before, row = re.sub(r'(?:[\w`]+\s*\.\s*)+$', '', lines[s[0]][:s[1]]), s[0]
    while not before.strip() and row > 0:
        row -= 1
        before = lines[row].split('//')[0]
    return before


def python_overloads(root, rel, cache):
    """`@overload def f` seguidas de su implementación: scip-python solo emite la definición de la primera; las demás
    líneas del grupo son la misma definición (como las sobrecargas del resto de lenguajes). {(archivo, línea): [líneas]}."""
    if (rel, None) in cache:
        return
    cache[(rel, None)] = True
    try:
        tree = ast.parse((Path(root) / rel).read_bytes())
    except (OSError, SyntaxError, ValueError, RecursionError):
        return
    for node in ast.walk(tree):
        groups = defaultdict(list)
        for sub in node.body if isinstance(getattr(node, 'body', None), list) else ():
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                groups[sub.name].append(sub)
        for defs in groups.values():
            if len(defs) > 1 and any(any((d.attr if isinstance(d, ast.Attribute) else getattr(d, 'id', '')) == 'overload'
                                         for d in f.decorator_list) for f in defs):
                lines = [f.lineno for f in defs]
                for line in lines:
                    cache[(rel, line)] = lines


def ground_truth(docs, root):
    defs, scopes, implementers, homes = {}, defaultdict(list), defaultdict(set), defaultdict(set)
    overloads = {}
    sigs = {k: v for d in docs for k, v in d.get('signatures', {}).items()}
    aliases, forward = [], {}
    for d in docs:
        for sym, ifaces in d['implements'].items():
            for iface in ifaces:
                implementers[iface].add(sym)
        tree, lines = None, None
        for rng, sym, roles, enclosing in d['occurrences']:
            kind, s = scip.kind_of(sym), scip.span(rng)
            if not (roles & scip.DEFINITION) or not kind or not s:
                continue
            outer = scip.span(enclosing)
            ts = sym.startswith(scip.TS_SCHEME)
            if kind in ('callable', 'type') and sym.startswith(scip.JVM_SCHEME):
                lines = lines if lines is not None else scip.source_lines(root, d['path']) or []
                if synthetic(lines, s, sym):
                    continue
            if sym.startswith(RUBY_SCHEME) and kind == 'type' and scip.name_of(sym).startswith('<Class:'):
                continue
            if sym.startswith(RUBY_SCHEME) and kind == 'callable':
                lines = lines if lines is not None else scip.source_lines(root, d['path']) or []
                s = ruby_symbol_def(d, lines, s, sym)
            if sym.startswith(scip.RUST_SCHEME):
                tree = tree or ts_tree(root, d['path'], RUST_LANG)
                if rust_place(tree, s) in ('macro', 'macro_rules'):
                    continue
                if kind == 'namespace' and s[:2] == (0, 0) and s[2] > 0:
                    kind = 'module'
            syntax = scope_syntax(sym, d['path']) if not outer and kind in ('callable', 'type') else None
            if syntax:
                tree = tree or ts_tree(root, d['path'], syntax[0])
                ctor = scip.constructor(sym) and not sym.startswith(scip.DOTNET_SCHEME)
                outer = syntax_scope(tree, s, syntax[1], ctor) if tree else None
            if ts and (kind == 'module' and not own_module(sym, d['path']) or 'typeLiteral' in sym):
                continue
            if ts and kind == 'term' and sym not in defs:
                tree = tree or ts_tree(root, d['path'])
                holder = ts_holder(tree, s) if tree else None
                if holds_function(holder) or scip.function_term(sym, sigs.get(sym)) or factory_function(holder, sigs.get(sym)):
                    kind = 'callable'
                    outer = outer or (holder and (holder.start_point[0], holder.start_point[1], holder.end_point[0], holder.end_point[1]))
                elif alias_of(holder) is not None:
                    aliases.append((sym, d, alias_of(holder).start_point, holder))
            if ts and not outer and kind == 'callable':
                tree = tree or ts_tree(root, d['path'])
                holder = ts_holder(tree, s) if tree else None
                if holder is not None and holder.type == 'method_definition':
                    outer = (holder.start_point[0], holder.start_point[1], holder.end_point[0], holder.end_point[1])
            if outer and kind in ('callable', 'type'):
                scopes[d['path']].append((outer, sym, s[0] + 1))
            defs.setdefault(sym, {'file': d['path'], 'line': s[0] + 1, 'kind': kind, 'nested': False})
            defs[sym].setdefault('sites', []).append((d['path'], s[0] + 1))
            if kind in ('type', 'namespace', 'module'):
                homes[sym].add(d['path'])
    refs_at = {}
    for sym, d, at, holder in aliases:
        if d['path'] not in refs_at:
            refs_at[d['path']] = defaultdict(list)
            for o in d['occurrences']:
                if not o[2] & scip.DEFINITION and len(o[0]) >= 3:
                    refs_at[d['path']][(o[0][0], o[0][1])].append(o[1])
    for _ in range(2):
        for sym, d, at, holder in aliases:
            if defs[sym]['kind'] == 'term' and any(defs.get(o, {}).get('kind') == 'callable' for o in refs_at[d['path']][tuple(at)]):
                defs[sym]['kind'] = 'callable'
                scopes[d['path']].append(((holder.start_point[0], holder.start_point[1], holder.end_point[0], holder.end_point[1]),
                                          sym, defs[sym]['line']))
    for d in docs:
        # `module.exports = { getSchemaSerializer }`: scip-typescript define la propiedad abreviada como un símbolo
        # «meta» (`getSchemaSerializer0:`) y en la misma posición referencia la función; quien llama a la propiedad
        # (`const { getSchemaSerializer } = require('./schemas')`) llama a la función
        # (también `{ hasOwnProp: hasOwnProperty }`: la referencia está en la posición del valor)
        spans, tree = defaultdict(list), None
        for rng, sym, roles, _ in d['occurrences']:
            if sym.startswith(scip.TS_SCHEME):
                spans[tuple(rng)].append((sym, roles))
        for rng, found in list(spans.items()):
            meta = [sym for sym, roles in found if roles & scip.DEFINITION and sym.endswith(':')]
            target = next((sym for sym, roles in found if not roles & scip.DEFINITION and defs.get(sym, {}).get('kind') == 'callable'), None)
            if meta and not target and len(rng) == 3:
                tree = tree or ts_tree(root, d['path'])
                node = tree.root_node.named_descendant_for_point_range((rng[0], rng[1]), (rng[0], rng[2])) if tree else None
                value = node.parent.child_by_field_name('value') if node is not None and node.parent is not None and \
                    node.parent.type == 'pair' and node.parent.child_by_field_name('key') == node else None
                if value is not None and value.type == 'identifier' and value.start_point[0] == value.end_point[0]:
                    at = (value.start_point[0], value.start_point[1], value.end_point[1])
                    target = next((sym for sym, roles in spans.get(at, ()) if not roles & scip.DEFINITION and
                                   defs.get(sym, {}).get('kind') == 'callable'), None)
            for sym in meta if target else ():
                forward[sym] = target
    for rel, line, _, outer in member_scopes(docs, root):
        defs[f'scope {rel}:{line}'] = {'file': rel, 'line': line, 'kind': 'scope', 'nested': False}
        scopes[rel].append((outer, f'scope {rel}:{line}', line))
    for sym, info in defs.items():
        if sym.startswith(PY_SCHEME) and info['kind'] == 'callable':
            python_overloads(root, info['file'], overloads)
            group = overloads.get((info['file'], info['line'])) or ()
            info['sites'] += [(info['file'], line) for line in group if (info['file'], line) not in info['sites']]
    for d in docs:
        lines = None
        for rng, sym, roles, _ in d['occurrences']:
            s = scip.span(rng)
            if roles & scip.DEFINITION or not s or scip.kind_of(sym) != 'callable' or sym not in defs or sym.startswith(scip.TS_SCHEME):
                continue
            lines = lines if lines is not None else scip.source_lines(root, d['path']) or []
            if s[0] < len(lines) and scip.DECLARES.search(lines[s[0]][:s[1]]):
                scopes[d['path']].append(((s[0], 0, indent_end(lines, s[0]), 0), sym, s[0] + 1))
    for rel, items in scopes.items():
        for outer, sym, _ in items:
            if any(o != outer and contains(o, outer) and defs[p]['kind'] == 'callable' for o, p, _ in items):
                defs[sym]['nested'] = True
    files, calls, dispatch, via = {}, {}, {}, defaultdict(set)
    supers = jvm_supertypes(docs, root, defs)
    for d in docs:
        rel, lines, tree = d['path'], None, None
        own = sorted(scopes.get(rel, ()), key=lambda x: (x[0][0], x[0][1]))
        values = {tuple(o[0]) for o in d['occurrences']
                  if o[1].startswith(scip.TS_SCHEME) and scip.kind_of(o[1]) in ('callable', 'term') and not scip.constructor(o[1])}
        for rng, raw, roles, _ in d['occurrences']:
            sym = rust_self_type(scip.canonical(raw), defs)
            if sym not in defs and sym.startswith(scip.JVM_SCHEME):
                sym = jvm_inherited(sym, defs, supers) or sym
            sym = forward.get(sym, sym)
            target, s = defs.get(sym), scip.span(rng)
            if roles & scip.DEFINITION or not target or not s or target['kind'] == 'namespace':
                continue
            if target['kind'] == 'type' and sym.startswith(scip.TS_SCHEME) and tuple(rng) in values and not scip.constructor(raw):
                continue
            place = None
            if sym.startswith(scip.RUST_SCHEME):
                tree = tree or ts_tree(root, rel, RUST_LANG)
                place = rust_place(tree, s)
                if place in ('macro_rules', 'visibility', 'cfg_off'):
                    continue
            if target['kind'] == 'module' and sym.startswith(scip.RUST_SCHEME) and \
                    inner_segment(lines if lines is not None else scip.source_lines(root, rel) or [], s):
                continue
            if sym.startswith(RUBY_SCHEME) and RUBY_OBJECT.search(sym):
                lines = lines if lines is not None else scip.source_lines(root, rel) or []
                if s[0] < len(lines) and lines[s[0]][:s[1]].rstrip().endswith('.'):
                    continue
            if target['file'] != rel and rel not in homes[sym]:
                files.setdefault((rel, target['file']), (s[0] + 1, sym))
                via[(rel, target['file'])].add(sym)
            iface = target['kind'] == 'term' and sym in implementers
            if target['kind'] not in ('callable', 'type') and not iface:
                continue
            if lines is None:
                lines = scip.source_lines(root, rel) or []
            if not is_call(lines, s, sym, rel, place):
                continue
            caller = None
            for outer, owner, line in own:
                if outer[0] > s[0]:
                    break
                if contains(outer, s):
                    caller = (rel, line, owner)
            where = (rel, s[0] + 1, s[1], lines[s[0]].strip() if s[0] < len(lines) else '')
            (dispatch if iface else calls).setdefault((caller or rel, sym), where)
    for key, where in dotnet_base_calls(docs, root, defs).items():
        calls.setdefault(key, where)
    return defs, files, calls, dispatch, implementers, via


def jvm_supertypes(docs, root, defs):
    """Supertipos de cada tipo de Kotlin: sus relaciones en el índice que también nombra la lista de supertipos de la
    declaración (`class DeleteStatement(…) : Statement<Int>(…)`, según el árbol sintáctico). semanticdb-kotlinc a veces
    lista en un tipo sus subtipos (`Filter#` → `CacheFilter#`), así que la relación sola no dice la dirección."""
    out = defaultdict(list)
    for d in docs:
        if not d['path'].endswith(KOTLIN_EXTS):
            continue
        tree, heads = None, None
        for sym, parents in d['implements'].items():
            if not sym.startswith(scip.JVM_SCHEME) or not sym.endswith('#') or sym not in defs or defs[sym]['file'] != d['path']:
                continue
            if heads is None:
                tree, heads = ts_tree(root, d['path'], KOTLIN_LANG), {}
                for n in ancestors_down(tree.root_node) if tree else ():
                    if n.type in ('class_declaration', 'object_declaration', 'companion_object'):
                        name = next((c for c in n.named_children if c.type in ('identifier', 'type_identifier')), None)
                        specs = next((c for c in n.named_children if c.type == 'delegation_specifiers'), None)
                        if name is not None and specs is not None:
                            heads[name.start_point[0] + 1] = set(re.findall(r'\w+', specs.text.decode('utf-8', 'replace')))
            words = heads.get(defs[sym]['line'], set())
            out[sym] += [p for p in parents if scip.name_of(p) in words]
    return out


def jvm_inherited(sym, defs, supers):
    """semanticdb-kotlinc nombra un miembro heredado con el tipo del receptor (`DeleteStatement#execute().` cuando
    `execute` solo se define en `Statement`): sin definición, la referencia se proyecta sobre la del supertipo más cercano
    (relaciones de la clase en el índice). Ronda 5: 291 referencias así en exposed, 114 en http4k, 32 en javalin; 0 en
    los índices de Java."""
    m = re.match(r'(.*#)([^#]+)$', sym)
    todo, seen = list(supers.get(m.group(1), ())) if m else [], set()
    while todo:
        sup = todo.pop(0)
        if sup in seen:
            continue
        seen.add(sup)
        if sup + m.group(2) in defs:
            return sup + m.group(2)
        todo += supers.get(sup, ())
    return None


def spread_homes(tfiles, via, defs, pfiles):
    """Un tipo definido en varios archivos (clase parcial de C#, módulo reabierto de Ruby) se define en todos ellos: la
    referencia `SqlMapper.ITypeMap` depende de cualquiera de los archivos de `SqlMapper`, no solo del primero que lista el
    índice. Si la predicción depende de otro de esos archivos, la dependencia de referencia pasa a ese."""
    for pair in [p for p in tfiles if p not in pfiles]:
        syms = via.get(pair, ())
        spread = [sym for sym in syms if len({f for f, _ in defs[sym].get('sites', ())}) > 1]
        if not spread or len(spread) != len(syms):
            continue
        alt = next((h for sym in spread for h in sorted({f for f, _ in defs[sym]['sites']}) if h != pair[0] and (pair[0], h) in pfiles), None)
        if alt:
            line_sym = tfiles.pop(pair)
            tfiles.setdefault((pair[0], alt), line_sym)


def dotnet_base_calls(docs, root, defs):
    """scip-dotnet no emite ocurrencia para `: base(…)`: la llamada al constructor de la clase base se toma del árbol
    sintáctico; la clase base es el símbolo SCIP del primer tipo de la lista de bases, si se define como `class`."""
    out, trees = {}, {}

    def tree_of(rel):
        if rel not in trees:
            trees[rel] = ts_tree(root, rel, CSHARP_LANG)
        return trees[rel]

    for d in docs:
        if not d['path'].endswith('.cs') or not any(o[1].startswith(scip.DOTNET_SCHEME) for o in d['occurrences'][:50]):
            continue
        tree = tree_of(d['path'])
        at = {}
        for rng, sym, roles, _ in d['occurrences']:
            s = scip.span(rng)
            if s:
                at.setdefault((s, bool(roles & scip.DEFINITION)), sym)
        for init in (n for n in ancestors_down(tree.root_node) if n.type == 'constructor_initializer') if tree else ():
            if not init.text.decode('utf-8', 'replace').lstrip(': \t\n').startswith('base'):
                continue
            ctor, klass = init.parent, init.parent.parent.parent if init.parent.parent is not None else None
            name = ctor.child_by_field_name('name')
            bases = next((c for c in klass.named_children if c.type == 'base_list'), None) if klass is not None else None
            first = bases.named_children[0] if bases is not None and bases.named_children else None
            if name is None or first is None:
                continue
            caller = at.get(((name.start_point[0], name.start_point[1], name.end_point[0], name.end_point[1]), True))
            ident = first if first.type == 'identifier' else next((c for c in ancestors_down(first) if c.type == 'identifier'), None)
            if first.type == 'qualified_name':
                ident = first.child_by_field_name('name')
            target = at.get(((ident.start_point[0], ident.start_point[1], ident.end_point[0], ident.end_point[1]), False)) if ident else None
            target = scip.canonical(target) if target else None
            info = defs.get(target) if target else None
            if not caller or not info or info['kind'] != 'type':
                continue
            home = tree_of(info['file'])
            text_line = (scip.source_lines(root, info['file']) or [''] * info['line'])[info['line'] - 1]
            col = len(text_line) - len(text_line.lstrip())
            node = home.root_node.named_descendant_for_point_range((info['line'] - 1, col), (info['line'] - 1, col)) if home else None
            while node is not None and node.type not in DOTNET_HOLDERS:
                node = node.parent
            if node is None or node.type != 'class_declaration':
                continue
            row = init.start_point[0]
            out.setdefault(((d['path'], name.start_point[0] + 1, caller), target),
                           (d['path'], row + 1, init.start_point[1], init.text.decode('utf-8', 'replace').strip()[:80]))
    return out


def indent_end(lines, start):
    base = len(lines[start]) - len(lines[start].lstrip())
    i, body = start + 1, False
    while i < len(lines):
        t = lines[i]
        if t.strip() and not t.lstrip().startswith((')', ']', '#')):
            if len(t) - len(t.lstrip()) <= base and body:
                break
            body = body or len(t) - len(t.lstrip()) > base
        i += 1
    return i - 1


def ratio(a, b):
    return round(a / b, 4) if b else None


def scores(truth, pred):
    tp = len(truth & pred)
    return {'tp': tp, 'fp': len(pred - truth), 'fn': len(truth - pred),
            'precision': ratio(tp, len(pred)), 'recall': ratio(tp, len(truth))}


def predicted(g, indexed):
    files, calls = set(), set()
    for (a, b, kind) in g.edges:
        ma, mb = g.nodes[a], g.nodes[b]
        fa, fb = ma.get('file'), mb.get('file')
        if fa not in indexed or fb not in indexed:
            continue
        if kind not in SKIP_FILE_EDGES and fa != fb and ma.get('kind') != 'doc' and mb.get('kind') != 'doc':
            files.add((fa, fb))
        if kind in CALL_KINDS and a != b:
            calls.add((a, b))
    return files, calls


def shape(text, name):
    m = re.search(r'([\w.\]\)]*?)\b' + re.escape(name) + r'\s*\(', text)
    prefix = m.group(1) if m else ''
    if text.lstrip().startswith('@'):
        return 'decorador'
    if prefix.startswith('super()'):
        return 'super().x()'
    if prefix in ('self.', 'cls.'):
        return f'{prefix}x()'
    if prefix.count('.') >= 2 or ')' in prefix or ']' in prefix:
        return 'cadena a.b.x() / x().y()'
    if prefix:
        return 'calificado obj.x()'
    return 'nombre suelto x()'


def plain(sym):
    name = scip.name_of(sym)
    if sym.startswith(scip.DOTNET_SCHEME) and '.' in name[1:]:
        name = name.rsplit('.', 1)[-1]  # implementación explícita de interfaz: `IFoo.Bar` es el método `Bar`
    return 'constructor' if name == '<constructor>' else re.sub(r'^<[gs]et>', '', name)


def label_kind(sym):
    k = scip.kind_of(sym)
    if k == 'type':
        return 'constructor/clase'
    return 'método' if '#' in sym.rsplit('/', 1)[-1] else 'función'


def measure(root, docs, g, scope=()):
    """Verdad de referencia SCIP y predicción de Córtex proyectadas sobre los mismos nodos."""
    loc_files = {m['file'] for m in g.nodes.values() if m.get('kind') == 'module'}
    docs = list({d['path']: d for d in reversed(docs)}.values())[::-1]
    paths = scip.align([d['path'] for d in docs], loc_files)
    for d in docs:
        d['path'] = paths.get(d['path'], d['path'])
    docs = [d for d in docs if d['path'] in loc_files and (not scope or d['path'].startswith(tuple(scope)))]
    indexed = {d['path'] for d in docs}
    dart_privates(docs, root)
    python_relative_modules(docs, root)
    csharp_branches(docs, root)
    dotnet_events(docs, root)
    shared_symbols(docs, root)
    defs, tfiles, tcalls, dispatch, implementers, via = ground_truth(docs, root)
    for pair, where in {**dart_directives(docs, root), **ruby_requires(docs, root), **ts_requires(docs, root)}.items():
        tfiles.setdefault(pair, where)
    loc = scip.Locator(g, indexed)
    def_lines = {(d['file'], d['line']) for d in defs.values()}

    def node_of(sym_or_rel, line=0):
        if isinstance(sym_or_rel, tuple):
            return loc.definition(sym_or_rel[0], sym_or_rel[1], sym_or_rel[2])
        if sym_or_rel in indexed:
            cand = loc.at(sym_or_rel, line)
            if cand and cand != loc.mods.get(sym_or_rel) and (sym_or_rel, g.nodes[cand]['line']) not in def_lines:
                return cand
            return loc.mods.get(sym_or_rel)
        d = defs[sym_or_rel]
        if d['kind'] == 'module':
            return loc.mods.get(d['file'])
        return loc.definition(d['file'], d['line'], sym_or_rel)

    truth_calls, truth_where = set(), {}
    for (caller, sym), where in sorted(tcalls.items(), key=repr):
        a, b = node_of(caller, where[1]), node_of(sym)
        if a and b and a != b:
            truth_calls.add((a, b))
            truth_where.setdefault((a, b), (where, caller, sym))
    soft = set()
    for (caller, sym), where in sorted(dispatch.items(), key=repr):
        a = node_of(caller, where[1])
        for impl in sorted(implementers[sym]):
            b = node_of(impl) if impl in defs else None
            if a and b and a != b:
                soft.add((a, b))
    soft -= truth_calls
    blind = {(loc.at(rel, line), name) for rel, sites in blind_sites(docs, root).items() for line, names in sites for name in names}
    pfiles, pcalls = predicted(g, indexed)
    spread_homes(tfiles, via, defs, pfiles)
    ctors, ctor_class = dart_constructors(docs, root), {}
    for rel, line, name, klass in ctors:
        node = loc.definition(rel, line)
        if node and plain_name(g.nodes[node]) == name and f'c:{rel}:{klass}' in g.nodes:
            ctor_class[node] = f'c:{rel}:{klass}'
    pcalls = {(a, ctor_class.get(b, b)) for a, b in pcalls if a != ctor_class.get(b, b)}
    members = member_scopes(docs, root)
    named = {(d['file'], d['line'], plain(sym)) for sym, d in defs.items() if d['kind'] in ('callable', 'type')}
    anonymous = {(rel, line, name) for rel, line, name, _ in members if (rel, line, name) not in named} | dotnet_unnamed(docs) | \
        php_unnamed_functions(docs, root)
    unmeasured = {(a, b) for a, b in pcalls - truth_calls if (a, str(g.nodes[b]['name']).rsplit('.', 1)[-1]) in blind or
                  (g.nodes[b].get('file'), g.nodes[b].get('line'), plain_name(g.nodes[b])) in anonymous}
    support, generic = defaultdict(set), dotnet_generic_names(docs, root)
    generic_homes = dotnet_type_homes(docs) if generic else {}
    for (a, b, kind) in g.edges:
        pair = (g.nodes[a].get('file'), g.nodes[b].get('file'))
        if pair in pfiles and pair not in tfiles:
            if pair[0] in generic and (kind == 'import' or plain_name(g.nodes[b]) in generic[pair[0]]):
                support[pair].add(('generic', pair[1]) if kind == 'import' and generic_homes.get(pair[1], set()) & generic[pair[0]] else
                                  'import' if kind == 'import' else (a, b))
                continue
            support[pair].add((a, b) if kind in CALL_KINDS and (a, b) in unmeasured else None)
    pfiles = pfiles - {pair for pair, edges in support.items() if None not in edges and edges - {'import'}}
    homes = {(d['path'], scip.name_of(sym), scip.span(rng)[0] + 1) for d in docs for rng, sym, roles, _ in d['occurrences']
             if roles & scip.DEFINITION and scip.kind_of(sym) == 'type' and scip.span(rng)}
    unnamed = anonymous | {c[:3] for c in ctors}
    return {'docs': docs, 'indexed': indexed, 'defs': defs, 'tfiles': tfiles, 'loc': loc, 'truth_calls': truth_calls,
            'truth_where': truth_where, 'soft': soft, 'unmeasured': unmeasured, 'pfiles': pfiles, 'pcalls': pcalls, 'homes': homes,
            'unnamed': unnamed, 'ctor_class': ctor_class}


def evaluate(name, root, docs, g, top, scope=()):
    m = measure(root, docs, g, scope)
    docs, indexed, defs, tfiles, loc = m['docs'], m['indexed'], m['defs'], m['tfiles'], m['loc']
    truth_calls, soft, unmeasured, pfiles = m['truth_calls'], m['soft'], m['unmeasured'], m['pfiles']
    pcalls = m['pcalls'] - soft - unmeasured
    truth_files = set(tfiles)
    result = {
        'files_indexed': len(indexed),
        'file_deps': scores(truth_files, pfiles),
        'calls': scores(truth_calls, pcalls),
        'dispatch_ignored': len(m['pcalls'] & soft),
        'unmeasured_ignored': len(unmeasured),
        'definitions': definitions(defs, g, indexed, loc, m['homes'], m['unnamed']),
    }
    result['patterns'] = patterns(root, docs, defs, g, truth_calls, m['truth_where'], pcalls, truth_files, pfiles, tfiles, loc, top)
    precise = to_graph_copy(g)
    added = scip.merge(precise, scip.collect(docs, precise, root))
    pf, pc = predicted(precise, indexed)
    pc = {(a, m['ctor_class'].get(b, b)) for a, b in pc if a != m['ctor_class'].get(b, b)} - soft - unmeasured
    result['precise'] = {'added': added, 'file_deps': scores(truth_files, pf), 'calls': scores(truth_calls, pc)}
    return result


def to_graph_copy(g):
    h = Graph()
    h.nodes = {k: dict(v) for k, v in g.nodes.items()}
    h.edges = Counter(g.edges)
    return h


def definitions(defs, g, indexed, loc, homes=(), unnamed=()):
    wanted = {s: d for s, d in defs.items() if d['kind'] in ('callable', 'type') and d['file'] in indexed}
    overloads = defaultdict(list)
    for sym in wanted:
        if not scip.constructor(sym):
            # los miembros del `companion object` de Kotlin son de la clase en Córtex: se agrupan con los homónimos de ella
            overloads[(wanted[sym]['file'], OVERLOAD.sub('().', sym).replace('#Companion#', '#'))].append(sym)
    nodes = {nid: m for nid, m in g.nodes.items() if m.get('kind') in scip.SYMBOL_KINDS and m.get('file') in indexed}
    by_place = defaultdict(list)
    for nid, m in nodes.items():
        by_place[(m['file'], str(m['name']).rsplit('.', 1)[-1])].append((m['line'], nid))
    matched, hit = {}, set()
    for sym, d in sorted(wanted.items()):
        for rel, at in d.get('sites') or [(d['file'], d['line'])]:
            cands = [(abs(line - at), nid) for line, nid in by_place.get((rel, plain(sym)), ()) if abs(line - at) <= 3]
            if cands:
                nid = min(cands)[1]
                matched.setdefault(sym, nid)
                hit.add(nid)
    reopened = defaultdict(list)
    for rel, name, line in homes:
        reopened[(rel, name)].append(line)
    for nid, m in nodes.items():
        if nid not in hit and m['kind'] == 'class' and any(abs(m['line'] - line) <= 3 for line in reopened.get((m['file'], plain_name(m)), ())):
            hit.add(nid)
    nodes = {nid: m for nid, m in nodes.items() if nid in hit or (m['file'], m['line'], plain_name(m)) not in unnamed}
    found = sum(any(s in matched for s in group) for group in overloads.values())
    missed = Counter()
    examples = defaultdict(list)
    for group in sorted(overloads.values(), key=lambda v: (wanted[v[0]]['file'], wanted[v[0]]['line'])):
        if any(s in matched for s in group):
            continue
        sym, d = group[0], wanted[group[0]]
        cat = def_category(sym, d)
        missed[cat] += 1
        if len(examples[cat]) < 3:
            examples[cat].append(f"{d['file']}:{d['line']} {plain(sym)}")
    extra = Counter()
    extra_examples = defaultdict(list)
    for nid in sorted(set(nodes) - hit, key=lambda n: (nodes[n]['file'], nodes[n]['line'])):
        cat = f"nodo {nodes[nid]['kind']} sin definición SCIP"
        extra[cat] += 1
        if len(extra_examples[cat]) < 3:
            extra_examples[cat].append(f"{nodes[nid]['file']}:{nodes[nid]['line']} {nodes[nid]['name']}")
    return {
        'scip': len(overloads), 'cortex': len(nodes), 'matched': found,
        'recall': ratio(found, len(overloads)), 'precision': ratio(len(hit), len(nodes)),
        'missed': [{'pattern': k, 'count': v, 'examples': examples[k]} for k, v in missed.most_common()],
        'extra': [{'pattern': k, 'count': v, 'examples': extra_examples[k]} for k, v in extra.most_common()],
    }


def plain_name(meta):
    return str(meta['name']).rsplit('.', 1)[-1]


def def_category(sym, d):
    if d['nested']:
        return 'función anidada (closure)'
    last = sym.rsplit('/', 1)[-1]
    if d['kind'] == 'type':
        return 'tipo/clase anidada' if last.count('#') > 1 else 'tipo/clase'
    if '#' in last:
        return 'método'
    return 'función'


def patterns(root, docs, defs, g, truth_calls, truth_where, pcalls, truth_files, pfiles, tfiles, loc, top):
    out = {}
    fn, fn_ex = Counter(), defaultdict(list)
    for edge in sorted(truth_calls - pcalls):
        (rel, line, _, text), caller, sym = truth_where[edge]
        cat = [label_kind(sym), shape(text, plain(sym)), 'mismo archivo' if defs[sym]['file'] == rel else 'otro archivo']
        if caller == rel:
            cat.append('desde nivel de módulo')
        elif loc.definition(*caller) != edge[0] or defs[caller[2]]['nested']:
            cat.append('llamador anidado')
        if any(a == edge[0] and str(g.nodes[b]['name']).rsplit('.', 1)[-1] == plain(sym) for a, b in pcalls):
            cat.append('Córtex eligió otro destino homónimo')
        key = ' · '.join(cat)
        fn[key] += 1
        if len(fn_ex[key]) < 3:
            fn_ex[key].append(f'{rel}:{line} {text[:120]}')
    out['calls_fn'] = [{'pattern': k, 'count': v, 'examples': fn_ex[k]} for k, v in fn.most_common(top)]
    refs = defaultdict(list)
    for d in docs:
        for rng, sym, roles, _ in d['occurrences']:
            s = scip.span(rng)
            if s and not roles & scip.DEFINITION and not sym.startswith('local '):
                refs[d['path']].append((s[0] + 1, scip.canonical(sym)))
    fp, fp_ex = Counter(), defaultdict(list)
    lines_cache = {}
    for a, b in sorted(pcalls - truth_calls):
        ma, mb = g.nodes[a], g.nodes[b]
        name = str(mb['name']).rsplit('.', 1)[-1]
        lines = lines_cache.setdefault(ma['file'], scip.source_lines(root, ma['file']) or [])
        start = ma['line']
        end = ma.get('end') or next_start(loc, ma['file'], start) or len(lines)
        seen = [(ln, sym) for ln, sym in refs.get(ma['file'], ()) if start <= ln <= end and plain(sym) == name]
        if ma['kind'] == 'module':
            seen = [(ln, sym) for ln, sym in refs.get(ma['file'], ()) if plain(sym) == name]
        if not seen:
            cat = 'sin referencia SCIP con ese nombre en el llamador'
            ln = next((i + 1 for i in range(start - 1, min(end, len(lines))) if re.search(r'\b' + re.escape(name) + r'\b', lines[i])), start)
        else:
            ln, sym = seen[0]
            mapped = {s2: (loc.definition(defs[s2]['file'], defs[s2]['line'], s2) if s2 in defs else None) for _, s2 in seen}
            same = [(l2, s2) for l2, s2 in seen if mapped[s2] == b]
            project = [(l2, s2) for l2, s2 in seen if s2 in defs and defs[s2]['kind'] in ('callable', 'type')]
            if same:
                ln, sym = same[0]
                cat = 'SCIP ve una referencia, no una llamada (conversión, valor, tipo)'
            elif project:
                ln, sym = project[0]
                cat = 'SCIP lo resuelve a otro símbolo homónimo del proyecto'
            elif any(s2 not in defs for _, s2 in seen):
                ln, sym = next((l2, s2) for l2, s2 in seen if s2 not in defs)
                cat = 'SCIP lo resuelve fuera del proyecto (stdlib/dependencia)'
            else:
                cat = 'SCIP lo resuelve a un campo/variable, no a función'
        cat += f" · {mb['kind']}"
        fp[cat] += 1
        if len(fp_ex[cat]) < 3:
            text = lines[ln - 1].strip() if 0 < ln <= len(lines) else ''
            fp_ex[cat].append(f"{ma['file']}:{ln} {a} -> {b} | {text[:100]}")
    out['calls_fp'] = [{'pattern': k, 'count': v, 'examples': fp_ex[k]} for k, v in fp.most_common(top)]
    ffn, ffn_ex = Counter(), defaultdict(list)
    for pair in sorted(truth_files - pfiles):
        line, sym = tfiles[pair]
        lines = lines_cache.setdefault(pair[0], scip.source_lines(root, pair[0]) or [])
        text = lines[line - 1].strip() if 0 < line <= len(lines) else ''
        kind = scip.kind_of(sym)
        cat = f"primera referencia a {kind}" + (' en línea de import' if IMPORT_LINE.match(text) else '')
        ffn[cat] += 1
        if len(ffn_ex[cat]) < 3:
            ffn_ex[cat].append(f'{pair[0]}:{line} -> {pair[1]} | {text[:100]}')
    out['files_fn'] = [{'pattern': k, 'count': v, 'examples': ffn_ex[k]} for k, v in ffn.most_common(top)]
    kinds = defaultdict(set)
    for (a, b, kind) in g.edges:
        fa, fb = g.nodes[a].get('file'), g.nodes[b].get('file')
        if (fa, fb) in pfiles:
            kinds[(fa, fb)].add(kind)
    ffp, ffp_ex = Counter(), defaultdict(list)
    for pair in sorted(pfiles - truth_files):
        cat = 'aristas Córtex: ' + '+'.join(sorted(kinds[pair]))
        if pair[1].endswith('__init__.py'):
            cat += ' · destino __init__.py (reexporta)'
        if (pair[1], pair[0]) in truth_files:
            cat += ' · existe la inversa'
        ffp[cat] += 1
        if len(ffp_ex[cat]) < 3:
            lines = lines_cache.setdefault(pair[0], scip.source_lines(root, pair[0]) or [])
            stem = Path(pair[1]).stem if Path(pair[1]).stem != '__init__' else Path(pair[1]).parent.name
            ln = next((i + 1 for i, t in enumerate(lines) if IMPORT_LINE.match(t) and stem in t), 0)
            ffp_ex[cat].append(f"{pair[0]}:{ln} -> {pair[1]}" + (f' | {lines[ln - 1].strip()[:100]}' if ln else ''))
    out['files_fp'] = [{'pattern': k, 'count': v, 'examples': ffp_ex[k]} for k, v in ffp.most_common(top)]
    return out


def next_start(loc, rel, line):
    return next((s - 1 for s in loc.starts.get(rel, ()) if s > line), None)


def pct(x):
    return '—' if x is None else f'{x * 100:.1f} %'


def markdown(results, meta):
    out = ['# Córtex · benchmark de precisión frente a SCIP', '',
           f"Generado: {meta['date']} · Córtex analizado con `analyze()` (sin git) · verdad de referencia: índices SCIP.", '',
           '| repo | conjunto | lenguaje | archivos | deps archivo P | deps archivo R | llamadas P | llamadas R | definiciones R | definiciones P | llamadas R (modo preciso) |',
           '|---|---|---|---|---|---|---|---|---|---|---|']
    for name, r in results.items():
        split = SPLITS.get(r.get('split'), r.get('split') or '')
        if 'error' in r:
            out.append(f"| {name} | {split} | {r.get('language', '')} | error: {r['error']} | | | | | | | |")
            continue
        out.append(f"| {name} | {split} | {r['language']} | {r['files_indexed']} | {pct(r['file_deps']['precision'])} | {pct(r['file_deps']['recall'])} | "
                   f"{pct(r['calls']['precision'])} | {pct(r['calls']['recall'])} | {pct(r['definitions']['recall'])} | "
                   f"{pct(r['definitions']['precision'])} | {pct(r['precise']['calls']['recall'])} |")
    out += ['', 'P = precisión, R = exhaustividad (recall). Solo cuentan archivos presentes en el índice SCIP.', '']
    titles = {'calls_fn': 'Llamadas que Córtex no ve (falsos negativos)', 'calls_fp': 'Llamadas que Córtex inventa (falsos positivos)',
              'files_fn': 'Dependencias entre archivos que faltan', 'files_fp': 'Dependencias entre archivos de más'}
    for name, r in results.items():
        if 'error' in r:
            continue
        out += [f'## {name}', '',
                f"Llamadas: TP {r['calls']['tp']} · FP {r['calls']['fp']} · FN {r['calls']['fn']} — "
                f"deps archivo: TP {r['file_deps']['tp']} · FP {r['file_deps']['fp']} · FN {r['file_deps']['fn']} — "
                f"definiciones: {r['definitions']['matched']}/{r['definitions']['scip']} (Córtex {r['definitions']['cortex']})"
                + (f" — llamadas no medibles (límite del indexador): {r['unmeasured_ignored']}" if r.get('unmeasured_ignored') else ''), '']
        for key, title in titles.items():
            out += [f'### {title}', '', '| n | patrón | ejemplos |', '|---|---|---|']
            for p in r['patterns'][key]:
                out.append(f"| {p['count']} | {p['pattern']} | {'<br>'.join(e.replace('|', '¦') for e in p['examples'])} |")
            out.append('')
        out += ['### Definiciones SCIP sin nodo Córtex', '', '| n | patrón | ejemplos |', '|---|---|---|']
        for p in r['definitions']['missed']:
            out.append(f"| {p['count']} | {p['pattern']} | {'<br>'.join(p['examples'])} |")
        for p in r['definitions']['extra']:
            out.append(f"| {p['count']} | {p['pattern']} | {'<br>'.join(p['examples'])} |")
        out.append('')
    return '\n'.join(out) + '\n'


def main(argv=None):
    p = argparse.ArgumentParser(description='Benchmark de Córtex frente a índices SCIP')
    p.add_argument('--repos', default=str(HERE / 'repos.toml'))
    p.add_argument('--only', action='append', default=[])
    p.add_argument('--work', default=os.environ.get('CORTEX_BENCH_WORK') or str(Path.home() / '.cache' / 'cortex-bench'))
    p.add_argument('--tools', default=os.environ.get('CORTEX_BENCH_TOOLS'))
    p.add_argument('--index', action='append', default=[], help='nombre=ruta de un índice SCIP ya generado')
    p.add_argument('--reuse', action='store_true')
    p.add_argument('--top', type=int, default=10)
    p.add_argument('--out', default=str(HERE / 'results'))
    args = p.parse_args(argv)
    work, outdir = Path(args.work), Path(args.out)
    tools = Path(args.tools) if args.tools else work / 'tools'
    given = dict(x.split('=', 1) for x in args.index)
    repos = tomllib.loads(Path(args.repos).read_text())['repo']
    results = {}
    for repo in repos:
        if (args.only and repo['name'] not in args.only) or (repo.get('skip') and repo['name'] not in args.only):
            continue
        t0 = time.time()
        try:
            src = checkout(repo, work)
            index = Path(given[repo['name']]) if repo['name'] in given else build_index(repo, src, work, tools, args.reuse)
            out = analyze(src, project=repo['name'], git=False)
            r = evaluate(repo['name'], src, scip.read_index(index), to_graph(out), args.top, repo.get('scope') or ())
        except Exception as exc:
            r = {'error': f'{type(exc).__name__}: {exc}'}
        r.update({'language': repo['language'], 'url': repo['url'], 'commit': repo['commit'], 'seconds': round(time.time() - t0, 1),
                  'split': repo.get('split', 'ajuste1')})
        results[repo['name']] = r
        print(f"{repo['name']}: " + (r.get('error') or f"llamadas P {pct(r['calls']['precision'])} R {pct(r['calls']['recall'])} · "
                                    f"deps P {pct(r['file_deps']['precision'])} R {pct(r['file_deps']['recall'])} · "
                                    f"defs R {pct(r['definitions']['recall'])}"))
    outdir.mkdir(parents=True, exist_ok=True)
    previous = outdir / 'results.json'
    if args.only and previous.is_file():
        order = [r['name'] for r in repos]
        merged = {**json.loads(previous.read_text()).get('results', {}), **results}
        results = {k: merged[k] for k in order if k in merged}
    meta = {'date': time.strftime('%Y-%m-%d')}
    (outdir / 'results.json').write_text(json.dumps({'meta': meta, 'results': results}, ensure_ascii=False, indent=1, sort_keys=True) + '\n')
    (outdir / 'RESULTS.md').write_text(markdown(results, meta))
    return 0


if __name__ == '__main__':
    sys.exit(main())
