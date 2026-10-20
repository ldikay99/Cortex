from conftest import write_repo
from cortex_graph.analyze import analyze


def short_edges(graph, kinds=('call',)):
    nodes = graph['nodes']

    def name(n):
        return n['name'] if n['kind'] != 'module' else n['file'].rsplit('/', 1)[-1]
    return {(name(nodes[e['a']]), name(nodes[e['b']])) for e in graph['edges'] if e['kind'] in kinds}


def graph_of(tmp_path, files):
    return analyze(write_repo(tmp_path / 'repo', files), git=False)


JAVA = {
    'src/p/Node.java': """
        package p;
        public class Node {
          public String attr(String key) { return key; }
          public Node parent() { return this; }
        }
    """,
    'src/p/Element.java': """
        package p;
        import java.util.List;
        public class Element extends Node {
          private final Node owner = new Node();
          List<Element> kids;
          public Element attr(String key, String value) { return this; }
          public void text() { }
          public Element self() { return this; }
        }
    """,
    'src/p/Store.java': """
        package p;
        public class Store {
          public void text() { }
          static void helper() { }
        }
    """,
    'src/q/Use.java': """
        package q;
        import java.util.List;
        import p.Element;
        import p.Node;
        import static p.Util.trim;
        public class Use {
          Element field;
          void run(Element param, String s) {
            Element local = new Element();
            local.text();
            param.self().text();
            field.attr("k");
            field.attr("k", "v");
            for (Element kid : field.kids) { kid.text(); }
            var guess = new Element();
            guess.parent();
            s.trim();
            if (param instanceof Element e) { e.text(); }
            trim("x");
          }
        }
    """,
    'src/p/Util.java': """
        package p;
        public class Util { public static String trim(String s) { return s; } }
    """,
}


def test_java_receivers_resolve_through_declared_types(tmp_path):
    edges = short_edges(graph_of(tmp_path, JAVA))
    assert ('Use.run', 'Element.text') in edges
    assert ('Use.run', 'Element.self') in edges
    assert ('Use.run', 'Node.attr') in edges
    assert ('Use.run', 'Element.attr') in edges
    assert ('Use.run', 'Node.parent') in edges
    assert ('Use.run', 'Element') in edges
    assert ('Use.run', 'Util.trim') in edges
    assert ('Use.run', 'Store.text') not in edges


def test_java_calls_on_external_types_do_not_guess_project_methods(tmp_path):
    files = {
        'src/p/Text.java': """
            package p;
            public class Text { public boolean canEncode(char c) { return true; } }
        """,
        'src/p/Use.java': """
            package p;
            import java.nio.charset.CharsetEncoder;
            class Use { boolean ok(CharsetEncoder enc) { return enc.canEncode('x'); } }
        """,
    }
    assert ('Use.ok', 'Text.canEncode') not in short_edges(graph_of(tmp_path, files))


def test_java_nested_classes_bases_and_enum_constant_bodies(tmp_path):
    files = {
        'src/p/Http.java': """
            package p;
            public class Http {
              static abstract class Base { void header(String n) { } }
              static class Request extends Base {
                Request() { super(); header("a"); }
                void send() { new Token.Tag(); }
              }
            }
        """,
        'src/p/Token.java': """
            package p;
            class Token { static class Tag { } }
        """,
        'src/p/State.java': """
            package p;
            enum State {
              Start {
                void process(Token t) { Validate.check(); }
              };
              abstract void process(Token t);
            }
        """,
        'src/p/Validate.java': """
            package p;
            class Validate { static void check() { } }
        """,
    }
    graph = graph_of(tmp_path, files)
    edges = short_edges(graph)
    inherits = short_edges(graph, ('inherits',))
    assert ('Request', 'Base') in inherits
    assert ('Request', 'Base.header') in edges
    assert ('Request', 'Base') in edges
    assert ('Request.send', 'Tag') in edges
    assert ('State', 'Validate.check') in edges
    methods = {n['name'] for n in graph['nodes'] if n['kind'] == 'method'}
    assert 'State.process' in methods
    assert sum(1 for n in graph['nodes'] if n['name'] == 'State.process') == 1


KOTLIN = {
    'src/web/Context.kt': """
        package web

        interface Context {
            fun path(): String
            fun json(obj: Any): Context
            fun contentType(): String?
            fun contentType(type: String): Context
            fun result(body: String): Context
        }

        fun interface Handler {
            fun handle(ctx: Context)
        }

        fun Context.html(body: String): Context = contentType("text/html").result(body)
    """,
    'src/web/Router.kt': """
        package web

        class Route(val path: String, val handler: Handler)

        class Router {
            private val routes = mutableListOf<Route>()
            val byPath = mutableMapOf<String, Route>()

            fun get(path: String, handler: Handler): Router {
                routes.add(Route(path, handler))
                return this
            }

            fun handle(ctx: Context) {
                routes.forEach { it.handler.handle(ctx) }
                byPath[ctx.path()]?.let { route -> route.handler.handle(ctx) }
                ctx.html("x")
            }

            companion object {
                fun create(): Router = Router().get("/") { ctx -> ctx.json(1) }
            }
        }
    """,
    'src/web/App.kt': """
        package web

        class App(private val router: Router) {
            fun start() {
                router.handle(Fake())
                Router.create().handle(Fake())
                val r = Router()
                r.apply { get("/a") { it.path() } }
            }
        }

        class Fake : Context {
            override fun path() = "/"
            override fun json(obj: Any): Context = this
            override fun contentType(): String? = null
            override fun contentType(type: String): Context = this
            override fun result(body: String): Context = this
        }
    """,
}


def test_kotlin_receivers_lambdas_and_extensions(tmp_path):
    edges = short_edges(graph_of(tmp_path, KOTLIN))
    assert ('Router.get', 'Route') in edges
    assert ('Router.handle', 'Handler.handle') in edges
    assert ('Router.handle', 'Context.path') in edges
    assert ('Router.handle', 'html') in edges
    assert ('html', 'Context.contentType') in edges
    assert ('html', 'Context.result') in edges
    assert ('Router.create', 'Router.get') in edges
    assert ('Router.create', 'Context.json') in edges
    assert ('App.start', 'Router.handle') in edges
    assert ('App.start', 'Router.create') in edges
    assert ('App.start', 'Router.get') in edges
    assert ('App.start', 'Context.path') in edges
    assert ('App.start', 'Fake') in edges


def test_kotlin_property_reads_become_file_dependencies(tmp_path):
    files = {
        'src/a/Config.kt': """
            package a

            class Config {
                var host: String = "localhost"
            }
        """,
        'src/a/Server.kt': """
            package a

            class Server(val cfg: Config)
        """,
        'src/a/Main.kt': """
            package a

            fun host(server: Server) = server.cfg.host
        """,
    }
    assert ('Main.kt', 'Config.kt') in short_edges(graph_of(tmp_path, files), ('import',))


def test_kotlin_imports_of_companion_members_link_the_declaring_file(tmp_path):
    files = {
        'src/a/Keys.kt': """
            package a

            class Keys {
                companion object {
                    val Main = "main"
                }
            }
        """,
        'src/b/Use.kt': """
            package b

            import a.Keys.Companion.Main

            fun use() = Main
        """,
    }
    assert ('Use.kt', 'Keys.kt') in short_edges(graph_of(tmp_path, files), ('import',))


RUST = {
    'Cargo.toml': """
        [package]
        name = "demo"
    """,
    'src/lib.rs': """
        pub mod matcher;
        pub mod flags;
        pub use crate::matcher::Matcher as Engine;
    """,
    'src/matcher.rs': """
        pub trait Sink {
            fn emit(&self, line: &str);
        }

        pub struct Matcher {
            pats: Vec<String>,
        }

        pub struct Builder {
            crlf: bool,
        }

        impl Builder {
            pub fn new() -> Builder {
                Builder { crlf: false }
            }

            pub fn crlf(&mut self, yes: bool) -> &mut Self {
                self.crlf = yes;
                self
            }

            pub fn build(&self) -> Result<Matcher, String> {
                Ok(Matcher { pats: vec![] })
            }
        }

        impl Matcher {
            pub fn is_match(&self, s: &str) -> bool {
                self.pats.iter().any(|p| p == s)
            }
        }

        pub enum Mode {
            Fixed(Matcher),
            Off,
        }
    """,
    'src/flags.rs': """
        use crate::matcher::{Builder, Mode, Sink};

        pub(crate) static SINKS: &[&dyn Sink] = &[];

        pub fn run(mode: Mode) -> bool {
            let mut b = Builder::new();
            let m = b.crlf(true).build().unwrap();
            for s in SINKS.iter() {
                s.emit("x");
            }
            assert!(m.is_match("a"));
            match mode {
                Mode::Fixed(ref inner) => inner.is_match("b"),
                Mode::Off => false,
            }
        }

        pub fn other(s: String) -> usize {
            s.len()
        }
    """,
}


def test_rust_receivers_resolve_through_declared_and_returned_types(tmp_path):
    graph = graph_of(tmp_path, RUST)
    edges = short_edges(graph)
    assert ('run', 'Builder.new') in edges
    assert ('run', 'Builder.crlf') in edges
    assert ('run', 'Builder.build') in edges
    assert ('run', 'Sink.emit') in edges
    assert ('run', 'Matcher.is_match') in edges
    assert ('Builder.new', 'Builder') in edges
    assert not any(a == 'other' for a, _ in edges)


def test_rust_reexports_point_at_the_defining_file(tmp_path):
    files = dict(RUST)
    files['src/main.rs'] = """
        use demo::Engine;

        fn main() {
            let e: Engine = todo!();
            e.is_match("x");
        }
    """
    graph = graph_of(tmp_path, files)
    assert ('main', 'Matcher.is_match') in short_edges(graph)
    assert ('main.rs', 'matcher.rs') in short_edges(graph, ('import',))


def test_rust_calls_inside_macro_arguments_are_read(tmp_path):
    files = {
        'Cargo.toml': '[package]\nname = "m"\n',
        'src/lib.rs': """
            pub struct Set;

            impl Set {
                pub fn matches(&self, s: &str) -> bool { s.is_empty() }
            }

            fn build() -> Set { Set }

            #[derive(Debug)]
            pub struct Unused;

            #[test]
            fn check() {
                let set = build();
                assert!(!set.matches("x"));
                assert_eq!(helper(1), 2);
            }

            fn helper(x: u8) -> u8 { x }
        """,
    }
    edges = short_edges(graph_of(tmp_path, files))
    assert ('check', 'build') in edges
    assert ('check', 'Set.matches') in edges
    assert ('check', 'helper') in edges
    assert not any(b == 'Debug' for _, b in edges)


DART = {
    'pubspec.yaml': """
        name: md
    """,
    'lib/md.dart': """
        export 'src/parser.dart';
    """,
    'lib/src/parser.dart': """
        import 'line.dart';

        class Parser {
          final List<Line> lines;
          int pos = 0;

          Parser(this.lines);
          Parser.empty() : lines = [];

          Line get current => lines[pos];

          Line? peek(int n) => null;

          void advance() { pos++; }
        }
    """,
    'lib/src/line.dart': """
        class Line {
          final String content;
          Line(this.content);
          bool get isBlank => content.isEmpty;
          Line trimmed() => Line(content.trim());
        }
    """,
    'lib/src/block.dart': """
        import 'parser.dart';
        import 'line.dart';

        class Block {
          bool canParse(Parser parser) {
            final next = parser.peek(1);
            parser.current.trimmed();
            parser
              ..advance()
              ..advance();
            for (final l in parser.lines) {
              l.trimmed();
            }
            return _check(parser.current) && next != null;
          }

          bool _check(Line line) => line.content.startsWith('#');

          Parser make() => Parser.empty();
        }
    """,
}


def test_dart_receivers_resolve_through_declared_types(tmp_path):
    edges = short_edges(graph_of(tmp_path, DART))
    assert ('Block.canParse', 'Parser.peek') in edges
    assert ('Block.canParse', 'Line.trimmed') in edges
    assert ('Block.canParse', 'Parser.advance') in edges
    assert ('Block.canParse', 'Block._check') in edges
    assert ('Block.make', 'Parser.empty') in edges
    assert ('Line.trimmed', 'Line') in edges
    assert ('Block.canParse', 'Parser.current') not in edges
    assert not any(b == 'Line.isBlank' for _, b in edges)


PHP = {
    'composer.json': '{"autoload": {"psr-4": {"App\\\\": "src/"}}}',
    'src/Level.php': """<?php
        namespace App;

        enum Level: int {
            case Debug = 100;
            public function getName(): string { return 'x'; }
        }
    """,
    'src/Record.php': """<?php
        namespace App;

        class Record {
            public function __construct(public readonly Level $level, public readonly string $message) {}
            public function with(string $m): self { return new self($this->level, $m); }
        }
    """,
    'src/FormatterInterface.php': """<?php
        namespace App;

        interface FormatterInterface { public function format(Record $r): string; }
    """,
    'src/LineFormatter.php': """<?php
        namespace App;

        class LineFormatter implements FormatterInterface {
            public function format(Record $r): string { return $r->message; }
        }
    """,
    'src/FormattableTrait.php': """<?php
        namespace App;

        trait FormattableTrait {
            protected ?FormatterInterface $formatter = null;
            public function getFormatter(): FormatterInterface { return $this->formatter ?? new LineFormatter(); }
        }
    """,
    'src/Base.php': """<?php
        namespace App;

        abstract class Base {
            public function __construct(protected Level $level) {}
            public function reset(): void {}
        }
    """,
    'src/Handler.php': """<?php
        namespace App;

        class Handler extends Base {
            use FormattableTrait;

            public function __construct(Level $level) { parent::__construct($level); }

            public function handle(Record $record): string {
                $copy = $record->with('x');
                $copy->level->getName();
                $first = reset($this->items);
                return $this->getFormatter()->format($copy);
            }
        }
    """,
}


def test_php_receivers_resolve_through_declared_types(tmp_path):
    edges = short_edges(graph_of(tmp_path, PHP))
    assert ('Handler.__construct', 'Base.__construct') in edges
    assert ('Handler.handle', 'Record.with') in edges
    assert ('Handler.handle', 'Level.getName') in edges
    assert ('Handler.handle', 'FormattableTrait.getFormatter') in edges
    assert ('Handler.handle', 'FormatterInterface.format') in edges
    assert ('Handler.handle', 'Base.reset') not in edges
    assert ('Record.with', 'Record') in edges


CSHARP = {
    'src/Machine.cs': """
        namespace Demo
        {
            public partial class Machine<TState>
            {
                private readonly Dictionary<TState, Representation> _states = new();
                internal Events Ev { get; } = new Events();

                public void Fire(TState s)
                {
                    var rep = GetRepresentation(s);
                    rep.Enter();
                    foreach (var r in _states.Values) { r.Exit(); }
                    Ev.Raise(rep);
                    _states.Values.Select(x => x.Name()).ToList();
                }
            }
        }
    """,
    'src/Machine.Representation.cs': """
        namespace Demo
        {
            public partial class Machine<TState>
            {
                internal Representation GetRepresentation(TState s) => new Representation();

                internal class Representation : Base
                {
                    public Representation() : base(1) { }
                    public void Enter() { }
                    public void Exit() { }
                    public string Name() => "x";
                }

                internal class Events
                {
                    public void Raise(Representation r) { r.Twice(); }
                }
            }
        }
    """,
    'src/Base.cs': """
        namespace Demo
        {
            public class Base { public Base(int x) { } }

            public static class Extensions
            {
                public static int Twice<T>(this Machine<T>.Representation r) => 2;
            }
        }
    """,
}


def test_csharp_receivers_partial_classes_and_extensions(tmp_path):
    edges = short_edges(graph_of(tmp_path, CSHARP))
    assert ('Machine.Fire', 'Machine.GetRepresentation') in edges
    assert ('Machine.Fire', 'Representation.Enter') in edges
    assert ('Machine.Fire', 'Representation.Exit') in edges
    assert ('Machine.Fire', 'Events.Raise') in edges
    assert ('Machine.Fire', 'Representation.Name') in edges
    assert ('Representation', 'Base') in edges
    assert ('Events.Raise', 'Extensions.Twice') in edges


def test_dotnet_preprocessor_conditions_follow_the_current_framework():
    from cortex_graph.langs import dotnet_branch, preproc_value
    assert preproc_value(b'NET') is True and preproc_value(b'!NET8_0_OR_GREATER') is False
    assert preproc_value(b'!(NETFRAMEWORK || NETSTANDARD2_0)') is True and preproc_value(b'NET462 || NETSTANDARD2_1') is False
    assert preproc_value(b'FEATURE_SPAN') is None and preproc_value(b'FEATURE_SPAN && NETFRAMEWORK') is False
    assert dotnet_branch([(0, 1, b'!NET'), (1, 2, b'else')]) == 1
    assert dotnet_branch([(0, 1, b'!NET')]) is None
    assert dotnet_branch([(0, 1, b'FEATURE_X'), (1, 2, b'else')]) == 0
