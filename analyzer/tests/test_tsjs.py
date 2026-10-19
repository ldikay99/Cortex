import pytest

from conftest import edge_set, write_repo
from cortex_graph.analyze import analyze, list_files
from cortex_graph.common import Graph, Issues
from cortex_graph.tsjs import analyze_ts


def ts_graph(root, files):
    root = write_repo(root, files)
    g, issues = Graph(), Issues()
    analyze_ts(root, sorted(rel for rel in files if not rel.endswith('.json')), g, issues)
    assert issues.items == []
    return g


def edges_of(g, kind=None):
    return {(a, b, k) for (a, b, k) in g.edges if kind is None or k == kind}


BARREL = {
    'packages/math/package.json': """
        { "name": "@pkg/math", "main": "dist/index.js" }
    """,
    'packages/math/src/index.ts': """
        export * from "./angle";
        export { scale as resize, clamp } from "./ops";
        export * as vec from "./vector";
        export * from "./geometry";
        import { lerp } from "./ops";
        export { lerp as mix };
        export { useAtom } from "jotai";
        import { atom } from "jotai";
        export { atom };
        export * from "./loop-a";
    """,
    'packages/math/src/angle.ts': """
        export function degrees(r: number) { return r; }
    """,
    'packages/math/src/ops.ts': """
        export function scale(x: number) { return x; }
        export const clamp = (x: number) => x;
        export function lerp(a: number) { return a; }
    """,
    'packages/math/src/vector.ts': """
        export function add(a: number) { return a; }
    """,
    'packages/math/src/geometry/index.ts': """
        export * from "./shapes";
    """,
    'packages/math/src/geometry/shapes.ts': """
        export class Circle {}
    """,
    'packages/math/src/loop-a.ts': """
        export * from "./loop-b";
    """,
    'packages/math/src/loop-b.ts': """
        export * from "./loop-a";
    """,
    'apps/web/src/use.ts': """
        import { degrees, resize, clamp, vec, Circle, mix, useAtom, atom, missing } from "@pkg/math";

        export function run() {
          degrees(1);
          resize(2);
          clamp(3);
          vec.add(4);
          mix(5);
          useAtom();
          atom();
          missing();
          return new Circle();
        }
    """,
}


def test_barrel_reexports_lead_to_the_definition(tmp_path):
    g = ts_graph(tmp_path / 'barrel', BARREL)
    calls = edges_of(g, 'call')
    run = 'f:apps/web/src/use.ts:run'
    assert {
        (run, 'f:packages/math/src/angle.ts:degrees', 'call'),
        (run, 'f:packages/math/src/ops.ts:scale', 'call'),
        (run, 'f:packages/math/src/ops.ts:clamp', 'call'),
        (run, 'f:packages/math/src/vector.ts:add', 'call'),
        (run, 'f:packages/math/src/ops.ts:lerp', 'call'),
        (run, 'c:packages/math/src/geometry/shapes.ts:Circle', 'call'),
    } <= calls
    assert ('m:apps/web/src/use.ts', 'm:packages/math/src/index.ts', 'import') in edges_of(g)
    assert ('m:packages/math/src/index.ts', 'm:packages/math/src/angle.ts', 'import') in edges_of(g)
    to_barrel = {b for a, b, _ in calls if a == run and b.startswith('m:')}
    assert to_barrel == {'m:packages/math/src/index.ts'}
    assert sum(1 for a, b, _ in calls if a == run) == 7


def chain(depth):
    files = {f'src/b{i}.ts': f'export * from "./b{i + 1}";\n' for i in range(depth)}
    files[f'src/b{depth}.ts'] = 'export function leaf() { return 1; }\n'
    files['src/use.ts'] = 'import { leaf } from "./b0";\n\nexport function use() { return leaf(); }\n'
    return files


@pytest.mark.parametrize('depth, target', [(5, 'f:src/b5.ts:leaf'), (6, 'm:src/b0.ts')])
def test_reexports_follow_at_most_five_hops(tmp_path, depth, target):
    g = ts_graph(tmp_path / f'chain{depth}', chain(depth))
    assert ('f:src/use.ts:use', target, 'call') in edges_of(g, 'call')


DYNAMIC = {
    'src/views/Home.ts': """
        export default function Home() { return 1; }
    """,
    'src/util.ts': """
        export function helper() { return 1; }
    """,
    'src/mod.ts': """
        export function start() { return 1; }
    """,
    'src/fsx.ts': """
        export function read() { return 1; }
    """,
    'src/ghost.ts': """
        export const ghost = 1;
    """,
    'src/pages/a.ts': """
        export const a = 1;
    """,
    'src/router.ts': """
        import fs = require("./fsx");

        export const routes = [{ component: () => import("./views/Home") }];

        export function load() {
          const { helper } = require("./util");
          return helper();
        }

        export async function lazy() {
          const mod = await import("./mod");
          return mod.start();
        }

        export function page(name: string) {
          // require("./ghost")
          return import(`./pages/${name}`);
        }

        export function file() { return fs.read(); }
    """,
}


def test_dynamic_imports_and_nested_requires(tmp_path):
    g = ts_graph(tmp_path / 'dyn', DYNAMIC)
    edges = edges_of(g)
    router = 'm:src/router.ts'
    assert {
        (router, 'm:src/views/Home.ts', 'import'),
        (router, 'm:src/util.ts', 'import'),
        (router, 'm:src/mod.ts', 'import'),
        (router, 'm:src/fsx.ts', 'import'),
        ('f:src/router.ts:load', 'f:src/util.ts:helper', 'call'),
        ('f:src/router.ts:lazy', 'f:src/mod.ts:start', 'call'),
        ('f:src/router.ts:file', 'f:src/fsx.ts:read', 'call'),
    } <= edges
    assert (router, 'm:src/ghost.ts', 'import') not in edges
    assert (router, 'm:src/pages/a.ts', 'import') not in edges


def test_commonjs_passthrough_to_built_sources(tmp_path):
    g = ts_graph(tmp_path / 'cjs', {
        'packages/next/package.json': """
            { "name": "next" }
        """,
        'packages/next/link.js': """
            module.exports = require('./dist/client/link')
        """,
        'packages/next/src/client/link.tsx': """
            export default function Link() { return <a />; }
        """,
        'apps/site/page.tsx': """
            import Link from 'next/link';

            export function Page() { return <Link />; }
        """,
    })
    edges = edges_of(g)
    assert ('m:packages/next/link.js', 'm:packages/next/src/client/link.tsx', 'import') in edges
    assert ('f:apps/site/page.tsx:Page', 'f:packages/next/src/client/link.tsx:Link', 'call') in edges


def test_vue_and_svelte_imports_without_extension(tmp_path):
    root = write_repo(tmp_path / 'vue', {
        'src/components/VArticlePreview.vue': """
            <template><div /></template>
            <script setup>
            const props = defineProps({});
            </script>
        """,
        'src/components/VTag.vue': """
            <script>
            export default { name: 'VTag' };
            </script>
        """,
        'src/components/Menu/index.vue': """
            <script setup>
            </script>
        """,
        'src/components/Badge.svelte': """
            <script>
              export let label = '';
            </script>
        """,
        'src/views/Home.vue': """
            <script setup>
            import VArticlePreview from './../components/VArticlePreview';
            import VTag from '@/components/VTag';
            import Menu from '@/components/Menu';
            import Badge from '../components/Badge';
            </script>
        """,
    })
    graph = analyze(root, 'vue')
    edges = edge_set(graph)
    home = 'm:src/views/Home.vue'
    assert {
        (home, 'm:src/components/VArticlePreview.vue', 'import'),
        (home, 'm:src/components/VTag.vue', 'import'),
        (home, 'm:src/components/Menu/index.vue', 'import'),
        (home, 'm:src/components/Badge.svelte', 'import'),
    } <= edges
    assert 'f:src/components/VArticlePreview.vue:props' not in {n['key'] for n in graph['nodes']}


CLASSES = {
    'src/base.ts': """
        export interface Persist { save(): void }

        export interface Durable extends Persist { flush(): void }

        export class Store {
          save() { return this.flush(); }
          flush() { return 1; }
        }
    """,
    'src/history.ts': """
        import { Store, Durable } from './base';

        function helper() { return 1; }

        export class History extends Store implements Durable {
          count = 0;
          state = helper();

          record() {
            this.save();
            this.local();
            super.flush();
            return [1].map(() => this.size());
          }

          local = () => helper();
          size = function () { return 1; };

          static make() { return new History(); }

          #secret() { return 1; }

          get total() { return this.count; }
        }

        export const Mixin = class extends Store {
          run() { return this.save(); }
        };
    """,
    'src/app.ts': """
        import { History } from './history';

        export function boot() { return History.make(); }
    """,
}


def test_class_members_this_super_and_heritage(tmp_path):
    g = ts_graph(tmp_path / 'cls', CLASSES)
    nodes = g.nodes
    history = 'c:src/history.ts:History'
    assert nodes[history]['kind'] == 'class' and nodes[history]['line'] == 5
    for name in ('record', 'local', 'size', 'make', '#secret', 'total'):
        key = f'f:src/history.ts:History.{name}'
        assert nodes[key]['kind'] == 'method' and nodes[key]['name'] == f'History.{name}'
        assert (history, key, 'contains') in g.edges
    assert 'f:src/history.ts:History.count' not in nodes and 'f:src/history.ts:History.state' not in nodes
    assert nodes['c:src/base.ts:Persist']['kind'] == 'class'
    edges = edges_of(g)
    record = 'f:src/history.ts:History.record'
    assert {
        (history, 'c:src/base.ts:Store', 'inherits'),
        (history, 'c:src/base.ts:Durable', 'inherits'),
        ('c:src/base.ts:Durable', 'c:src/base.ts:Persist', 'inherits'),
        ('c:src/history.ts:Mixin', 'c:src/base.ts:Store', 'inherits'),
        (record, 'f:src/base.ts:Store.save', 'call'),
        (record, 'f:src/history.ts:History.local', 'call'),
        (record, 'f:src/base.ts:Store.flush', 'call'),
        (record, 'f:src/history.ts:History.size', 'call'),
        ('f:src/base.ts:Store.save', 'f:src/base.ts:Store.flush', 'call'),
        ('f:src/history.ts:History.local', 'f:src/history.ts:helper', 'call'),
        ('f:src/history.ts:History.make', history, 'call'),
        ('f:src/history.ts:Mixin.run', 'f:src/base.ts:Store.save', 'call'),
        (history, 'f:src/history.ts:helper', 'call'),
        ('f:src/app.ts:boot', 'f:src/history.ts:History.make', 'call'),
    } <= edges
    assert not any(a == history and b.startswith('f:src/history.ts:History.') for a, b, k in edges if k == 'call')


DECLARATIONS = {
    'arrow': ('export const arrow = () => 1;', True),
    'expression': ('export const expression = function () { return 1; };', True),
    'Memo': ('export const Memo = memo(() => null);', True),
    'Forward': ('export const Forward = React.forwardRef((p, r) => null);', True),
    'Styled': ('export const Styled = styled.div`color: red`;', True),
    'Wrapped': ('export const Wrapped = styled(Button)`margin: 0`;', True),
    'Lazy': ('export const Lazy = lazy(() => import("./other"));', True),
    'Routed': ('export const Routed = withRouter(Page);', True),
    'useCounter': ('export const useCounter = create((set) => ({ n: 0 }));', True),
    'useAuth': ('export const useAuth = defineStore("auth", {});', True),
    'handler': ('export const handler = debounce(() => save(), 300);', True),
    'memoized': ('export const memoized = (function () { const inner = () => 1; return inner; })();', True),
    'config': ('export const config = makeConfig({ a: 1 });', False),
    'Ctx': ('export const Ctx = createContext(null);', False),
    'doubled': ('export const doubled = values.map((v) => v * 2);', False),
    'settings': ('export const settings = (() => ({ a: 1 }))();', False),
    'count': ('export const count = ref(0);', False),
    'store': ('export const store = useStore();', False),
}


def test_const_call_initializers_are_functions_only_when_they_wrap_one(tmp_path):
    body = '\n'.join(line for line, _ in DECLARATIONS.values())
    g = ts_graph(tmp_path / 'noise', {
        'src/other.ts': 'export const other = 1;\n',
        'src/decls.tsx': 'import { makeConfig } from "./make";\n' + body + '\n',
        'src/make.ts': 'export function makeConfig(x: object) { return x; }\n',
    })
    for name, (_, is_function) in DECLARATIONS.items():
        assert (f'f:src/decls.tsx:{name}' in g.nodes) is is_function, name
    assert ('m:src/decls.tsx', 'f:src/make.ts:makeConfig', 'call') in g.edges
    assert ('m:src/decls.tsx', 'm:src/other.ts', 'import') in g.edges


def test_ts_graph_is_deterministic(tmp_path):
    files = {**BARREL, **{f'cls/{k}': v for k, v in CLASSES.items()}, **{f'dyn/{k}': v for k, v in DYNAMIC.items()}}
    root = write_repo(tmp_path / 'det', files)
    rels = [rel for rel in list_files(root) if not rel.endswith('.json')]
    runs = []
    for _ in range(2):
        g = Graph()
        analyze_ts(root, rels, g, Issues())
        runs.append((list(g.nodes.items()), list(g.edges.items())))
    assert runs[0] == runs[1]
