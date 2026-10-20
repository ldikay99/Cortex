import importlib.util
import sys
from pathlib import Path

from cortex_graph.common import Graph

BENCH = Path(__file__).resolve().parents[2] / 'bench' / 'run.py'
spec = importlib.util.spec_from_file_location('bench_run', BENCH)
run = importlib.util.module_from_spec(spec)
sys.modules.setdefault('bench_run', run)
spec.loader.exec_module(run)

JVM = 'semanticdb maven . . '


def test_compiler_generated_jvm_members_are_not_definitions():
    lines = ['data class P(val name: String)', 'fun real() = 1', 'enum class E { A, B }']
    assert run.synthetic(lines, (0, 17, 0, 21), f'{JVM}p/P#getName().')
    assert run.synthetic(lines, (0, 17, 0, 21), f'{JVM}p/P#component1().')
    assert not run.synthetic(lines, (1, 4, 1, 8), f'{JVM}p/real().')
    assert run.synthetic(lines, (2, 11, 2, 12), f'{JVM}p/E#`<anonymous object at 9>`#')
    assert not run.synthetic(lines, (0, 11, 0, 12), f'{JVM}p/P#`<init>`().')
    assert not run.synthetic(lines, (0, 17, 0, 21), 'scip-python python x 1 `p`/P#getName().')


def test_kotlin_scopes_come_from_the_syntax_tree():
    src = b'class A(val x: Int) {\n    fun go() {\n        run()\n    }\n    constructor() : this(1) {\n    }\n}\n'
    tree = run.Parser(run.KOTLIN_LANG).parse(src)
    assert run.syntax_scope(tree, (1, 8, 1, 10), run.KOTLIN_HOLDERS) == (1, 4, 3, 5)
    assert run.syntax_scope(tree, (0, 6, 0, 7), run.KOTLIN_HOLDERS) == (0, 0, 6, 1)
    assert run.syntax_scope(tree, (0, 6, 0, 7), run.KOTLIN_HOLDERS, constructor=True) is None
    assert run.syntax_scope(tree, (4, 4, 4, 15), run.KOTLIN_HOLDERS, constructor=True) == (4, 4, 5, 5)


def test_overloads_count_as_one_definition():
    g = Graph()
    g.node('m:A.java', kind='module', name='A.java', file='A.java', line=1)
    g.node('c:A.java:A', kind='class', name='A', file='A.java', line=1, end=20)
    g.node('f:A.java:A.get', kind='method', name='A.get', file='A.java', line=2, end=4)
    defs = {
        f'{JVM}A#': {'file': 'A.java', 'line': 1, 'kind': 'type', 'nested': False},
        f'{JVM}A#get().': {'file': 'A.java', 'line': 2, 'kind': 'callable', 'nested': False},
        f'{JVM}A#get(+1).': {'file': 'A.java', 'line': 12, 'kind': 'callable', 'nested': False},
        f'{JVM}A#`<init>`().': {'file': 'A.java', 'line': 15, 'kind': 'callable', 'nested': False},
    }
    from cortex_graph import scip
    out = run.definitions(defs, g, {'A.java'}, scip.Locator(g, {'A.java'}))
    assert (out['scip'], out['matched'], out['recall']) == (2, 2, 1.0)


def test_rust_places_decided_from_syntax():
    src = (b'macro_rules! m { () => { helper() } }\n'
           b'pub(crate) fn f() -> Foo {\n'
           b'    assert!(g());\n'
           b'    Foo { a: 1 }\n'
           b'}\n')
    tree = run.Parser(run.RUST_LANG).parse(src)
    assert run.rust_place(tree, (0, 25, 0, 31)) == 'macro_rules'
    assert run.rust_place(tree, (1, 4, 1, 9)) == 'visibility'
    assert run.rust_place(tree, (2, 12, 2, 13)) == 'macro'
    assert run.rust_place(tree, (3, 4, 3, 7)) == 'struct'
    assert run.rust_place(tree, (1, 21, 1, 24)) is None
    lines = src.decode().split('\n')
    assert run.is_call(lines, (3, 4, 3, 7), 'rust-analyzer cargo x 1 Foo#', 'a.rs', 'struct')
    assert run.inner_segment(['use crate::flags::Thing;'], (0, 4, 0, 9))
    assert not run.inner_segment(['mod flags;'], (0, 4, 0, 9))


def test_dart_private_members_and_directives_are_recovered(tmp_path):
    (tmp_path / 'lib/src').mkdir(parents=True)
    (tmp_path / 'pubspec.yaml').write_text('name: md\n')
    (tmp_path / 'lib/md.dart').write_text("export 'src/a.dart';\nimport 'package:md/src/b.dart';\n")
    (tmp_path / 'lib/src/a.dart').write_text('class A {\n  void _go() {}\n  void run() { _go(); }\n}\n')
    (tmp_path / 'lib/src/b.dart').write_text('class B {}\n')
    docs = [
        {'path': 'lib/md.dart', 'occurrences': [([0, 0, 0], 'scip-dart pub md 1 lib/`md.dart`/', 1, [])]},
        {'path': 'lib/src/a.dart', 'occurrences': [
            ([0, 6, 7], 'scip-dart pub md 1 lib/src/`a.dart`/A#', 1, [0, 0, 3, 1]),
            ([1, 7, 10], 'local 0', 1, [1, 2, 1, 15]),
            ([2, 15, 18], 'local 0', 0, [])]},
        {'path': 'lib/src/b.dart', 'occurrences': [([0, 6, 7], 'scip-dart pub md 1 lib/src/`b.dart`/B#', 1, [])]},
    ]
    run.dart_privates(docs, tmp_path)
    syms = [o[1] for o in docs[1]['occurrences']]
    assert syms[1] == syms[2] == 'scip-dart local . . `lib/src/a.dart`/A#_go().'
    assert set(run.dart_directives(docs, tmp_path)) == {('lib/md.dart', 'lib/src/a.dart'), ('lib/md.dart', 'lib/src/b.dart')}


def test_dotnet_base_constructor_calls_come_from_syntax(tmp_path):
    (tmp_path / 'A.cs').write_text('class Base { public Base(int x) {} }\nclass Kid : Base\n{\n    public Kid() : base(1) { }\n}\n')
    sch = 'scip-dotnet nuget . . '
    docs = [{'path': 'A.cs', 'occurrences': [
        ([0, 6, 10], f'{sch}Demo/Base#', 1, []),
        ([1, 6, 9], f'{sch}Demo/Kid#', 1, []),
        ([1, 12, 16], f'{sch}Demo/Base#', 0, []),
        ([3, 11, 14], f'{sch}Demo/Kid#`.ctor`().', 1, []),
    ]}]
    defs = {f'{sch}Demo/Base#': {'file': 'A.cs', 'line': 1, 'kind': 'type', 'nested': False}}
    found = run.dotnet_base_calls(docs, tmp_path, defs)
    assert list(found) == [(('A.cs', 4, f'{sch}Demo/Kid#`.ctor`().'), f'{sch}Demo/Base#')]


PY = 'scip-python python demo 1 '
TS = 'scip-typescript npm demo 1 '
RB = 'scip-ruby gem demo 1 '
PHP = 'scip-php composer demo 1 '


def test_python_relative_module_references_are_qualified(tmp_path):
    (tmp_path / 'pkg').mkdir()
    (tmp_path / 'pkg/__init__.py').write_text('from ._api import *\nfrom . import json as json\n')
    docs = [
        {'path': 'pkg/__init__.py', 'occurrences': [([0, 0, 0], f'{PY}pkg/__init__:', 1, []), ([0, 5, 10], f'{PY}_api/__init__:', 0, []),
                                                     ([1, 14, 26], f'{PY}json/__init__:', 0, [])]},
        {'path': 'pkg/_api.py', 'occurrences': [([0, 0, 0], f'{PY}`pkg._api`/__init__:', 1, [])]},
        {'path': 'pkg/json/__init__.py', 'occurrences': [([0, 0, 0], f'{PY}`pkg.json`/__init__:', 1, [])]},
    ]
    run.python_relative_modules(docs, tmp_path)
    assert [o[1] for o in docs[0]['occurrences'][1:]] == [f'{PY}`pkg._api`/__init__:', f'{PY}`pkg.json`/__init__:']


def test_python_source_root_module_references_are_qualified(tmp_path):
    (tmp_path / 'src/pkg').mkdir(parents=True)
    (tmp_path / 'src/pkg/a.py').write_text('import typing\nfrom pkg import b\nfrom pkg.b import X\n')
    std = 'scip-python python python-stdlib 3.11 '
    docs = [
        {'path': 'src/pkg/a.py', 'occurrences': [([0, 0, 0], f'{PY}`src.pkg.a`/__init__:', 1, []), ([0, 7, 13], f'{std}typing/__init__:', 0, []),
                                                  ([1, 5, 8], f'{PY}pkg/__init__:', 0, []), ([2, 5, 10], f'{PY}`pkg.b`/__init__:', 0, [])]},
        {'path': 'src/pkg/__init__.py', 'occurrences': [([0, 0, 0], f'{PY}`src.pkg`/__init__:', 1, [])]},
        {'path': 'src/pkg/b.py', 'occurrences': [([0, 0, 0], f'{PY}`src.pkg.b`/__init__:', 1, [])]},
        {'path': 'src/pkg/typing.py', 'occurrences': [([0, 0, 0], f'{PY}`src.pkg.typing`/__init__:', 1, [])]},
    ]
    (tmp_path / 'src/pkg/__init__.py').write_text('')
    (tmp_path / 'src/pkg/ext').mkdir()
    (tmp_path / 'src/pkg/ext/__init__.py').write_text('')
    (tmp_path / 'src/pkg/ext/c.py').write_text('import ext\next.go()\n')
    docs += [{'path': 'src/pkg/ext/__init__.py', 'occurrences': [([0, 0, 0], f'{PY}`src.pkg.ext`/__init__:', 1, [])]},
             {'path': 'src/pkg/ext/c.py', 'occurrences': [([0, 0, 0], f'{PY}`src.pkg.ext.c`/__init__:', 1, []),
                                                          ([0, 7, 10], f'{PY}ext/__init__:', 0, []), ([1, 0, 3], f'{PY}ext/__init__:', 0, [])]}]
    run.python_relative_modules(docs, tmp_path)
    assert [o[1] for o in docs[0]['occurrences'][1:]] == [f'{std}typing/__init__:', f'{PY}`src.pkg`/__init__:',
                                                          f'{PY}`src.pkg.b`/__init__:']
    # `import ext` es un paquete externo homónimo del subpaquete `pkg.ext`: ni el import ni sus usos se enlazan
    assert [o[1] for o in docs[-1]['occurrences'][1:]] == [f'{PY}ext/__init__:'] * 2


def test_blind_sites_follow_each_indexer_limit(tmp_path):
    (tmp_path / 'a.rb').write_text('class A\n  def go(*args, &blk)\n    run(*args)\n    each(&:x)\n    request.path\n    @io.read\n    x = 1\n    x.succ\n  end\nend\n')
    (tmp_path / 'A.php').write_text('<?php\nclass A {\n  function go($r) {\n    $r->send();\n    $this->uri->getPath();\n  }\n}\n')
    (tmp_path / 'a.ts').write_text('import * as z from "./z";\nz.string().optional();\nhelper();\n')
    docs = [
        {'path': 'a.rb', 'occurrences': [([0, 6, 7], f'{RB}A#', 1, [])]},
        {'path': 'A.php', 'occurrences': [([1, 6, 7], f'{PHP}A#', 1, [])]},
        {'path': 'a.ts', 'occurrences': [([1, 2, 8], 'local 3', 0, []), ([1, 11, 19], f'{TS}`types.ts`/ZodType#optional().', 0, []),
                                         ([2, 0, 6], 'local 4', 1, []), ([2, 0, 6], 'local 4', 0, [])]},
        {'path': 'types.ts', 'occurrences': [([9, 16, 22], f'{TS}`types.ts`/stringType.', 0, [])]},
    ]
    (tmp_path / 'types.ts').write_text('\n' * 9 + '  stringType as string,\n')
    sites = run.blind_sites(docs, tmp_path)
    assert sites['a.rb'] == [(3, {'run'}), (5, {'path'}), (6, {'read'})]
    assert sites['A.php'] == [(4, {'send'})]
    assert sites['a.ts'] == [(2, {'string', 'stringType'})]


def test_ruby_requires_and_autoload_are_dependencies(tmp_path):
    (tmp_path / 'rack').mkdir()
    (tmp_path / 'rack.rb').write_text("require 'rack/version'\nmodule Rack\n  autoload :Builder, 'rack/builder'\nend\n")
    (tmp_path / 'rack/builder.rb').write_text("require_relative 'version'\n")
    docs = [{'path': p, 'occurrences': [([0, 0, 1], f'{RB}Rack#', 1, [])]} for p in ('rack.rb', 'rack/builder.rb', 'rack/version.rb')]
    assert set(run.ruby_requires(docs, tmp_path)) == {('rack.rb', 'rack/version.rb'), ('rack.rb', 'rack/builder.rb'),
                                                      ('rack/builder.rb', 'rack/version.rb')}


def test_rust_self_resolves_to_the_implemented_type():
    sym = 'rust-analyzer cargo demo 1 lazy/impl#[`LazyBuffer<I>`]'
    defs = {'rust-analyzer cargo demo 1 lazy/LazyBuffer#': {}}
    assert run.rust_self_type(sym, defs) == 'rust-analyzer cargo demo 1 lazy/LazyBuffer#'
    assert run.rust_self_type(sym, {}) == sym
    assert run.rust_self_type('rust-analyzer cargo demo 1 lazy/impl#[`LazyBuffer<I>`]new().', defs).endswith('new().')


def test_csharp_tree_keeps_the_branch_with_occurrences(tmp_path):
    src = '#if NET\nint A() => 1;\n#else\nint B() => 2;\n#endif\n'
    (tmp_path / 'A.cs').write_text(src)
    run.csharp_branches([{'path': 'A.cs', 'occurrences': [([3, 4, 5], 'scip-dotnet nuget . . B().', 1, [])]}], tmp_path)
    kept = run.ACTIVE[(str(tmp_path), 'A.cs')].decode()
    assert 'B()' in kept and 'A()' not in kept and len(kept) == len(src)


def test_typescript_member_functions_and_aliases(tmp_path):
    (tmp_path / 'app.js').write_text('exports.f = function (v) { return v; };\nconst g = h;\nfunction h() {}\n')
    docs = [{'path': 'app.js', 'occurrences': [([0, 8, 9], 'local 1', 0, []), ([1, 6, 7], f'{TS}`app.js`/g.', 1, []),
                                               ([1, 10, 11], f'{TS}`app.js`/h().', 0, []), ([2, 9, 10], f'{TS}`app.js`/h().', 1, [2, 0, 2, 15])],
             'implements': {}}]
    assert [s[:3] for s in run.member_scopes(docs, tmp_path)] == [('app.js', 1, 'f')]
    defs = run.ground_truth(docs, tmp_path)[0]
    assert defs[f'{TS}`app.js`/g.']['kind'] == 'callable' and defs['scope app.js:1']['kind'] == 'scope'


def test_dart_unnamed_constructors_are_their_class(tmp_path):
    (tmp_path / 'lib').mkdir()
    (tmp_path / 'lib/a.dart').write_text('class A {\n  A(this.x);\n  A.named();\n  final int x;\n}\n')
    docs = [{'path': 'lib/a.dart', 'occurrences': [([0, 6, 7], 'scip-dart pub demo 1 lib/`a.dart`/A#', 1, [])]}]
    assert run.dart_constructors(docs, tmp_path) == [('lib/a.dart', 2, 'A', 'A')]


def test_ruby_untyped_receivers_index_reads_and_runtime_mixins(tmp_path):
    (tmp_path / 'b.rb').write_text(
        'module Hooks\n  def self.included(base)\n    base.extend ClassMethods\n  end\n  module ClassMethods\n    def commands; end\n'
        '  end\n  def helper(k)\n    self.class.commands\n    k.name\n    @h[k]\n    @h[k] = 1\n  end\nend\n'
        'class B\n  include Hooks\n  def make\n    self.class.new\n    commands\n  end\nend\n')
    docs = [{'path': 'b.rb', 'occurrences': [([0, 7, 12], f'{RB}Hooks#', 1, [])]}]
    sites = run.blind_sites(docs, tmp_path)['b.rb']
    assert {(9, 'commands'), (10, 'name'), (11, '[]'), (18, 'B'), (19, 'commands')} <= {(line, n) for line, names in sites for n in names}
    assert not any(line == 12 for line, _ in sites)


def test_ruby_symbol_definitions_and_object_fallback(tmp_path):
    lines = ['module Mime', '  def mime_type(ext)', '  end', '  module_function :mime_type', 'end']
    d = {'occurrences': [([1, 6, 15], f'{RB}Mime#mime_type().', 1, []), ([3, 18, 28], f'{RB}`<Class:Mime>`#mime_type().', 1, [])]}
    assert run.ruby_symbol_def(d, lines, (3, 18, 3, 28), f'{RB}`<Class:Mime>`#mime_type().') == (1, 6, 1, 15)
    assert run.RUBY_OBJECT.search(f'{RB}Object#namespace().') and not run.RUBY_OBJECT.search(f'{RB}Thor#Object#x().')


def test_python_overloads_and_every_definition_site_count(tmp_path):
    (tmp_path / 'm.py').write_text('from typing import overload\n\n@overload\ndef f(x: int) -> int: ...\n\n@overload\n'
                                   'def f(x: str) -> str: ...\n\ndef f(x):\n    return x\n')
    cache = {}
    run.python_overloads(tmp_path, 'm.py', cache)
    assert cache[('m.py', 4)] == [4, 7, 9]
    g = Graph()
    g.node('m:m.py', kind='module', name='m.py', file='m.py', line=1)
    g.node('f:m.py:f', kind='function', name='f', file='m.py', line=9, end=10)
    g.node('f:m.py:A.g.decorator', kind='function', name='A.g.decorator', file='m.py', line=30, end=31)
    g.node('f:m.py:A.h.decorator', kind='function', name='A.h.decorator', file='m.py', line=40, end=41)
    defs = {'scip-python python x 1 `m`/f().': {'file': 'm.py', 'line': 4, 'kind': 'callable', 'nested': False,
                                                 'sites': [('m.py', 4), ('m.py', 9)]},
            'scip-python python x 1 `m`/A#decorator().': {'file': 'm.py', 'line': 30, 'kind': 'callable', 'nested': False,
                                                           'sites': [('m.py', 30), ('m.py', 40)]}}
    from cortex_graph import scip
    out = run.definitions(defs, g, {'m.py'}, scip.Locator(g, {'m.py'}))
    assert (out['recall'], out['precision']) == (1.0, 1.0)


def test_rust_inactive_cfg_items_are_not_measured():
    src = b'#[cfg(windows)]\nfn win() { helper() }\n\n#[cfg(not(windows))]\nfn unix() { helper() }\n'
    tree = run.Parser(run.RUST_LANG).parse(src)
    assert run.rust_place(tree, (1, 11, 1, 17)) == 'cfg_off'
    assert run.rust_place(tree, (4, 12, 4, 18)) is None


def test_php_chains_without_types_are_not_measured(tmp_path):
    (tmp_path / 'R.php').write_text('<?php\nclass R {\n  public static function from(): static { return new static(); }\n'
                                    '  public function a(): self { return $this; }\n  /** @return $this */\n'
                                    '  public function b(): self { return $this; }\n  function go() {\n'
                                    '    R::from()->a();\n    $this->b()->a();\n    $this->a()->b()->a();\n    E::One->label();\n'
                                    '    $x[0]->run();\n  }\n}\n')
    sym = lambda m: f'{PHP}R#{m}().'
    occ = [([2, 25, 29], sym('from'), 1, []), ([3, 18, 19], sym('a'), 1, []), ([5, 18, 19], sym('b'), 1, []),
           ([7, 7, 11], sym('from'), 0, []), ([8, 11, 12], sym('b'), 0, []), ([8, 15, 16], sym('a'), 0, []),
           ([9, 11, 12], sym('a'), 0, [])]
    sites = run.blind_sites([{'path': 'R.php', 'occurrences': occ}], tmp_path)['R.php']
    assert (8, {'a'}) in sites and (10, {'b'}) in sites and (10, {'a'}) in sites
    assert (11, {'label'}) in sites and (12, {'run'}) in sites
    assert (9, {'a'}) not in sites


def test_dotnet_generic_names_events_and_shared_symbols(tmp_path):
    cs = 'scip-dotnet nuget . . '
    (tmp_path / 'A.cs').write_text('class A : Base<A> {\n  public event D? Closed;\n  A() : base(1) { list.Find<int>(); new Box<int>(); }\n}\n')
    (tmp_path / 'Html').mkdir()
    (tmp_path / 'Text').mkdir()
    (tmp_path / 'Html/R.cs').write_text('class R { void W() {} }\n')
    (tmp_path / 'Text/R.cs').write_text('class R { void W() {} }\n')
    (tmp_path / 'U.cs').write_text('class U { void G() { new R().W(); } }\n')
    docs = [{'path': 'A.cs', 'occurrences': [([0, 6, 7], f'{cs}N/A#', 1, []), ([1, 18, 24], f'{cs}N/A#Closed#', 1, [])]},
            {'path': 'Html/R.cs', 'occurrences': [([0, 6, 7], f'{cs}Inlines/R#', 1, []), ([0, 15, 16], f'{cs}Inlines/R#W().', 1, [])]},
            {'path': 'Text/R.cs', 'occurrences': [([0, 6, 7], f'{cs}Inlines/R#', 1, []), ([0, 15, 16], f'{cs}Inlines/R#W().', 1, [])]},
            {'path': 'U.cs', 'occurrences': [([0, 25, 26], f'{cs}Inlines/R#', 0, []), ([0, 29, 30], f'{cs}Inlines/R#W().', 0, [])]}]
    run.dotnet_events(docs, tmp_path)
    assert docs[0]['occurrences'][1][1] == f'{cs}N/A#Closed.'
    run.shared_symbols(docs, tmp_path)
    assert docs[1]['occurrences'][0][1] != docs[2]['occurrences'][0][1]
    assert all(o[1].startswith('local ') for o in docs[3]['occurrences']) and docs[3]['ambiguous'] == [(1, 'R'), (1, 'W')]
    sites = run.blind_sites(docs, tmp_path)
    assert (3, {'Find'}) in sites['A.cs'] and (3, {'Box'}) in sites['A.cs'] and (3, {'Base'}) in sites['A.cs']
    assert run.dotnet_generic_names(docs, tmp_path)['A.cs'] >= {'Base', 'Find', 'Box'}


def test_kotlin_top_level_overloads_in_several_files_are_ambiguous(tmp_path):
    (tmp_path / 'a.kt').write_text('fun A.map(x: Int) = 1\n')
    (tmp_path / 'b.kt').write_text('fun B.map(x: Int) = 2\nfun go(b: B) = b.map(1)\n')
    docs = [{'path': 'a.kt', 'occurrences': [([0, 6, 9], f'{JVM}p/map().', 1, [])]},
            {'path': 'b.kt', 'occurrences': [([0, 6, 9], f'{JVM}p/map().', 1, []), ([1, 17, 20], f'{JVM}p/map().', 0, [])]}]
    run.shared_symbols(docs, tmp_path)
    assert docs[0]['occurrences'][0][1] != docs[1]['occurrences'][0][1]
    assert docs[1]['ambiguous'] == [(2, 'map')]


def test_call_shapes_of_kotlin_csharp_and_operators():
    assert run.is_call(['val f = Filter { it }'], (0, 8, 0, 14), f'{JVM}p/Filter#', 'a.kt')
    assert not run.is_call(['fun f(): Filter {'], (0, 9, 0, 15), f'{JVM}p/Filter#', 'a.kt')
    assert not run.is_call(['object : Filter {'], (0, 9, 0, 15), f'{JVM}p/Filter#', 'a.kt')
    cs = 'scip-dotnet nuget . . '
    assert run.is_call(['var x = new Line { A = 1 };'], (0, 12, 0, 16), f'{cs}N/Line#', 'a.cs')
    assert not run.is_call(['var x = new Line[3];'], (0, 12, 0, 16), f'{cs}N/Line#', 'a.cs')
    assert not run.is_call(['var x = new Line.Sync(1);'], (0, 12, 0, 16), f'{cs}N/Line#', 'a.cs')
    assert not run.is_call(['public static implicit operator Block(W w) => w.B;'], (0, 32, 0, 37), f'{cs}N/Block#', 'a.cs')
    assert run.plain(f'{cs}N/P#`Markdig.Parsers.IPost.PostProcess`().') == 'PostProcess'
    assert run.scip.qualified(f'{JVM}p/Body#Companion#invoke(+1).') == 'Body.invoke'


def test_typescript_require_is_a_dependency(tmp_path):
    (tmp_path / 'lib/plugins').mkdir(parents=True)
    (tmp_path / 'lib/index.ts').write_text("require('./plugins')(this);\nconst x = require(`./${name}`);\nrequire('fs');\n")
    (tmp_path / 'lib/plugins/index.ts').write_text("export = function (ctx) {};\n")
    (tmp_path / 'lib/a.js').write_text("var Base = require('./b');\n")
    docs = [{'path': p, 'occurrences': [([0, 0, 1], f'{TS}`{p}`/', 1, [])]} for p in ('lib/index.ts', 'lib/plugins/index.ts', 'lib/a.js')]
    found = run.ts_requires(docs, tmp_path)
    assert set(found) == {('lib/index.ts', 'lib/plugins/index.ts')}
    assert found[('lib/index.ts', 'lib/plugins/index.ts')][0] == 1


def test_ruby_receivers_from_unsigned_methods_and_index_reads_are_untyped(tmp_path):
    (tmp_path / 'a.rb').write_text('module J\n  def self.logger\n    @l\n  end\n  def go(r)\n    J.logger.info\n    r[:site].cache\n'
                                   '    J.new.info\n  end\nend\n')
    docs = [{'path': 'a.rb', 'occurrences': [([0, 7, 8], f'{RB}J#', 1, []), ([1, 11, 17], f'{RB}<Class:J>#logger().', 1, []),
                                              ([5, 6, 12], f'{RB}<Class:J>#logger().', 0, [])]}]
    names = {(line, n) for line, ns in run.blind_sites(docs, tmp_path)['a.rb'] for n in ns}
    assert (6, 'info') in names and (7, 'cache') in names and (8, 'info') not in names


def test_kotlin_annotations_and_supertype_lists_are_not_calls(tmp_path):
    src = b'@SinceKtlint("0.39", EXPERIMENTAL)\n@Deprecated\nclass A :\n    B(),\n    Rule.Official {\n}\n'
    tree = run.Parser(run.KOTLIN_LANG).parse(src)
    assert run.kotlin_annotations(tree) == [(1, {'SinceKtlint'}), (3, {'SinceKtlint'}), (2, {'Deprecated'}), (3, {'Deprecated'})]
    lines = src.decode().split('\n')
    assert not run.is_call(lines, (4, 9, 4, 17), f'{JVM}p/Rule#Official#', 'a.kt')
    assert run.is_call(['val f =', '    Filter { it }'], (1, 4, 1, 10), f'{JVM}p/Filter#', 'a.kt')


def test_types_defined_in_several_files_depend_on_any_of_them():
    sch = 'scip-dotnet nuget . . '
    defs = {f'{sch}D/SqlMapper#': {'file': 'SqlMapper.Async.cs', 'line': 1, 'kind': 'type',
                                   'sites': [('SqlMapper.Async.cs', 1), ('SqlMapper.ITypeMap.cs', 1)]},
            f'{sch}D/Other#': {'file': 'Other.cs', 'line': 1, 'kind': 'type', 'sites': [('Other.cs', 1)]}}
    tfiles = {('Map.cs', 'SqlMapper.Async.cs'): (3, f'{sch}D/SqlMapper#'), ('Map.cs', 'Other.cs'): (4, f'{sch}D/Other#')}
    via = {('Map.cs', 'SqlMapper.Async.cs'): {f'{sch}D/SqlMapper#'}, ('Map.cs', 'Other.cs'): {f'{sch}D/Other#'}}
    run.spread_homes(tfiles, via, defs, {('Map.cs', 'SqlMapper.ITypeMap.cs')})
    assert set(tfiles) == {('Map.cs', 'SqlMapper.ITypeMap.cs'), ('Map.cs', 'Other.cs')}


def test_dart_private_classes_keep_the_document_prefix(tmp_path):
    (tmp_path / 'lib').mkdir()
    (tmp_path / 'lib/p.dart').write_text('class _P {\n  _P();\n}\nvoid f() { _P(); }\n')
    own = 'scip-dart pub md 1 lib/`p.dart`/'
    docs = [{'path': 'lib/p.dart', 'occurrences': [([0, 0, 0], own, 1, []), ([0, 6, 8], 'local 0', 1, []),
                                                    ([3, 11, 13], f'{own}_P#`<constructor>`().', 0, [])]}]
    run.dart_privates(docs, tmp_path)
    assert docs[0]['occurrences'][1][1] == f'{own}_P#' == run.scip.canonical(docs[0]['occurrences'][2][1])


def test_dart_unlinked_private_calls_and_private_named_constructors(tmp_path):
    (tmp_path / 'lib').mkdir()
    (tmp_path / 'lib/q.dart').write_text('class Q<E> {\n  void _down() {}\n  void add() {\n    _down();\n  }\n}\n'
                                         'class _G {\n  _G._withCapacity();\n}\n')
    own = 'scip-dart pub c 1 lib/`q.dart`/'
    docs = [{'path': 'lib/q.dart', 'occurrences': [
        ([0, 0, 0], own, 1, []), ([0, 6, 7], f'{own}Q#', 1, []), ([1, 7, 12], 'local 3', 1, []),
        ([3, 4, 9], 'local 7', 0, []),  # scip-dart: la llamada lleva otro `local` que su definición
        ([6, 6, 8], 'local 9', 1, []), ([7, 5, 18], 'local 10', 1, [])]}]
    run.dart_privates(docs, tmp_path)
    syms = [o[1] for o in docs[0]['occurrences']]
    assert syms[2] == f'{own}Q#_down().' and syms[3] == 'local 7'
    assert syms[4] == f'{own}_G#' and syms[5] == f'{own}_G#_withCapacity().'
    assert (4, {'_down'}) in run.blind_sites(docs, tmp_path)['lib/q.dart']


def test_ruby_locals_assigned_from_untyped_values_are_not_measured(tmp_path):
    (tmp_path / 'a.rb').write_text('class T\n  def go\n    p = @ctx.new_parser(1)\n    p.consume(:id)\n    q = Parser.new\n'
                                   '    q.look\n  end\nend\n')
    docs = [{'path': 'a.rb', 'occurrences': [([0, 6, 7], f'{RB}T#', 1, [])]}]
    names = {(line, n) for line, ns in run.blind_sites(docs, tmp_path)['a.rb'] for n in ns}
    assert (4, 'consume') in names and (6, 'look') not in names


def test_dotnet_type_homes_and_kotlin_trees_with_grammar_fixups(tmp_path):
    cs = 'scip-dotnet nuget . . '
    docs = [{'path': 'Args.cs', 'occurrences': [([0, 14, 18], f'{cs}Polly/Args#', 1, []), ([1, 8, 9], f'{cs}Polly/Args#X.', 1, [])]}]
    assert run.dotnet_type_homes(docs) == {'Args.cs': {'Args'}}
    (tmp_path / 'Q.kt').write_text('class Q {\n    fun f() {\n        a()\n        where?.let { b() }\n    }\n'
                                   '    var d: Int?\n        @Synchronized get() = 1\n        @Synchronized set(v) { }\n}\n')
    (tmp_path / 'N.kt').write_bytes(b'// a\x00b\nclass N {\n    fun g() = 1\n}\n')
    assert not run.ts_tree(tmp_path, 'Q.kt', run.KOTLIN_LANG).root_node.has_error
    assert not run.ts_tree(tmp_path, 'N.kt', run.KOTLIN_LANG).root_node.has_error


def test_kotlin_inherited_members_ts_shorthand_exports_and_unnamed_dotnet_types(tmp_path):
    defs = {f'{JVM}p/Statement#execute().': {'file': 'S.kt', 'line': 3, 'kind': 'callable'}}
    supers = {f'{JVM}p/Delete#': [f'{JVM}p/Base#'], f'{JVM}p/Base#': [f'{JVM}p/Statement#']}
    assert run.jvm_inherited(f'{JVM}p/Delete#execute().', defs, supers) == f'{JVM}p/Statement#execute().'
    assert run.jvm_inherited(f'{JVM}p/Delete#other().', defs, supers) is None
    (tmp_path / 's.js').write_text('function get (a) { return a }\nmodule.exports = {\n  get\n}\n')
    (tmp_path / 'u.js').write_text("const { get } = require('./s')\nfunction use () { return get(1) }\n")
    ts = 'scip-typescript npm . . '
    docs = [{'path': 's.js', 'implements': {}, 'occurrences': [
                ([0, 9, 12], f'{ts}`s.js`/get().', 1, [0, 0, 0, 30]), ([2, 2, 5], f'{ts}`s.js`/get0:', 1, []),
                ([2, 2, 5], f'{ts}`s.js`/get().', 0, [])]},
            {'path': 'u.js', 'implements': {}, 'occurrences': [
                ([1, 9, 12], f'{ts}`u.js`/use().', 1, [1, 0, 1, 34]), ([1, 25, 28], f'{ts}`s.js`/get0:', 0, [])]}]
    _, files, calls, *_ = run.ground_truth(docs, tmp_path)
    assert any(sym == f'{ts}`s.js`/get().' for _, sym in calls) and ('u.js', 's.js') in files
    cs = 'scip-dotnet nuget . . '
    docs = [{'path': 'P.cs', 'occurrences': [([3, 20, 23], f'{cs}Polly/`<invalid-global-code>`#Add().', 1, []),
                                             ([5, 20, 23], f'{cs}Polly/P#Run().', 1, [])]}]
    assert run.dotnet_unnamed(docs) == {('P.cs', 4, 'Add')}


def test_kotlin_annotation_sites_include_the_annotated_declaration():
    src = b'class A {\n    @Since(\n        "1"\n    )\n    fun go() = 1\n}\n'
    tree = run.Parser(run.KOTLIN_LANG).parse(src)
    assert run.kotlin_annotations(tree) == [(2, {'Since'}), (5, {'Since'})]



def test_jvm_supertypes_follow_the_class_header_and_pair_exports_forward(tmp_path):
    (tmp_path / 'F.kt').write_text('fun interface Filter {\n    fun invoke(x: Int): Int\n}\n'
                                   'class Cache(val n: Int) :\n    Filter {\n    override fun invoke(x: Int) = x\n}\n')
    docs = [{'path': 'F.kt', 'implements': {f'{JVM}p/Filter#': [f'{JVM}p/Cache#'], f'{JVM}p/Cache#': [f'{JVM}p/Filter#']},
             'occurrences': []}]
    defs = {f'{JVM}p/Filter#': {'file': 'F.kt', 'line': 1, 'kind': 'type'}, f'{JVM}p/Cache#': {'file': 'F.kt', 'line': 4, 'kind': 'type'}}
    assert run.jvm_supertypes(docs, tmp_path, defs) == {f'{JVM}p/Filter#': [], f'{JVM}p/Cache#': [f'{JVM}p/Filter#']}
    (tmp_path / 'u.js').write_text('const hasOwn = (o, k) => true\nexport default {\n  own: hasOwn\n}\n')
    (tmp_path / 'v.js').write_text("import u from './u.js'\nfunction f () { return u.own(1) }\n")
    ts = 'scip-typescript npm . . '
    docs = [{'path': 'u.js', 'implements': {}, 'occurrences': [
                ([0, 6, 12], f'{ts}`u.js`/hasOwn.', 1, []), ([2, 2, 5], f'{ts}`u.js`/own0:', 1, []),
                ([2, 7, 13], f'{ts}`u.js`/hasOwn.', 0, [])]},
            {'path': 'v.js', 'implements': {}, 'occurrences': [
                ([1, 9, 10], f'{ts}`v.js`/f().', 1, [1, 0, 1, 34]), ([1, 25, 28], f'{ts}`u.js`/own0:', 0, [])]}]
    _, files, calls, *_ = run.ground_truth(docs, tmp_path)
    assert any(sym == f'{ts}`u.js`/hasOwn.' for _, sym in calls)


def test_php_functions_without_scip_symbol_and_their_chains_are_not_measured(tmp_path):
    (tmp_path / 'helpers.php').write_text('<?php\nfunction user(): U { return new U(); }\nfunction error_log($m) { }\n')
    (tmp_path / 'C.php').write_text('<?php\nclass C {\n  function go() {\n    user()->can(1);\n    strlen("x")->bad();\n'
                                    '    $this->run();\n  }\n}\n')
    builtin = 'scip-php composer php 8.4.23 '
    docs = [{'path': 'helpers.php', 'occurrences': [([2, 9, 18], f'{builtin}error_log().', 0, [])]},
            {'path': 'C.php', 'occurrences': [([1, 6, 7], f'{PHP}C#', 1, []), ([4, 4, 10], f'{builtin}strlen().', 0, []),
                                              ([5, 11, 14], f'{PHP}C#run().', 0, [])]}]
    # scip-php no nombra `user` (no está cargada): ni definición ni llamadas; `error_log` es homónima de la de PHP
    assert run.php_unnamed_functions(docs, tmp_path) == {('helpers.php', 2, 'user')}
    sites = run.blind_sites(docs, tmp_path)['C.php']
    assert (4, {'can'}) in sites and not any(line in (5, 6) for line, _ in sites)


def test_dotnet_restore_check_rejects_package_build_assets(tmp_path):
    import json
    import pytest
    spec = importlib.util.spec_from_file_location('index_dotnet', BENCH.parent / 'index_dotnet.py')
    dotnet = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dotnet)
    (tmp_path / 'obj').mkdir()
    assets = {'targets': {'net9.0': {'A/1.0': {'build': {'buildTransitive/net8.0/_._': {}}, 'compile': {'lib/a.dll': {}}}}}}
    (tmp_path / 'obj' / 'project.assets.json').write_text(json.dumps(assets))
    dotnet.check_restore(tmp_path)
    assets['targets']['net9.0']['B/2.0'] = {'analyzers': {'analyzers/dotnet/cs/Gen.dll': {}}}
    (tmp_path / 'obj' / 'project.assets.json').write_text(json.dumps(assets))
    with pytest.raises(SystemExit):
        dotnet.check_restore(tmp_path)
