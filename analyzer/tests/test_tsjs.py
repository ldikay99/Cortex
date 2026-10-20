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
    assert not {b for a, b, _ in calls if a == run and b.startswith('m:')}
    assert (run, 'm:packages/math/src/index.ts', 'ref') in edges_of(g)
    assert sum(1 for a, b, _ in calls if a == run) == 6


def chain(depth):
    files = {f'src/b{i}.ts': f'export * from "./b{i + 1}";\n' for i in range(depth)}
    files[f'src/b{depth}.ts'] = 'export function leaf() { return 1; }\n'
    files['src/use.ts'] = 'import { leaf } from "./b0";\n\nexport function use() { return leaf(); }\n'
    return files


@pytest.mark.parametrize('depth, target, kind', [(5, 'f:src/b5.ts:leaf', 'call'), (6, 'm:src/b0.ts', 'ref')])
def test_reexports_follow_at_most_five_hops(tmp_path, depth, target, kind):
    g = ts_graph(tmp_path / f'chain{depth}', chain(depth))
    assert ('f:src/use.ts:use', target, kind) in edges_of(g)


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


ENRICHED = {
    'src/api.tsx': """
        /**
         * @file Shared helpers for the app.
         */

        import React, { memo } from 'react';
        import { ReactQueryDevtools } from '@tanstack/react-query/devtools';
        import fs from 'node:fs';
        import { local } from './local';
        import missing from './nope';
        import aliased from '@/nowhere';
        export { atom } from 'jotai';
        const lazy = () => import('lodash/debounce');
        const env = require('dotenv');

        /**
         * Fetches a user by id.
         * Uses the {@link Client | shared client}.
         *
         * Second paragraph is ignored.
         * @param id the id
         * @returns the user
         */
        export async function fetchUser(id: string): Promise<User> {
          return fetch(id);
        }

        /** Renders a button. */
        export const Button = memo((props: Props) => <div>{props.x}</div>);

        const clamp = (x: number, lo = 0): number => Math.max(lo, x);

        export const useStore = create<State>()((set) => ({}));

        /** Main app. */
        @Component({})
        export class App extends React.Component<Props, State> implements Disposable {
          /** Loads it. */
          @Input()
          async load(id: number): Promise<void> {
            await this.save();
          }

          private save() {}
          protected handle = (e: Event): void => {};
          #secret() {}
          static create() {}
        }

        /** Button props. */
        interface Props<T> extends Base {
          x: number;
        }

        // plain comment
        function helper() {}

        export { helper };
    """,
    'src/local.js': """
        function local() {}
        function hidden() {}
        module.exports = { local };
    """,
    'src/Counter.vue': """
        <template>
          <div>hi</div>
        </template>

        <script setup lang="ts">
        import { ref } from 'vue';
        /** Counter state. */
        function useCounter(start: number) {
          return ref(start);
        }
        </script>
    """,
}


def meta_of(g, nid):
    return {k: g.nodes[nid].get(k) for k in ('line', 'end', 'vis', 'sig', 'doc')}


def test_functions_and_arrow_consts_carry_signature_doc_end_and_visibility(tmp_path):
    g = ts_graph(tmp_path / 'enriched', ENRICHED)
    assert meta_of(g, 'f:src/api.tsx:fetchUser') == {
        'line': 23, 'end': 25, 'vis': 'public', 'sig': 'export async function fetchUser(id: string): Promise<User>',
        'doc': 'Fetches a user by id. Uses the shared client.'}
    assert meta_of(g, 'f:src/api.tsx:Button') == {
        'line': 28, 'end': 28, 'vis': 'public', 'sig': 'Button(props: Props)', 'doc': 'Renders a button.'}
    assert meta_of(g, 'f:src/api.tsx:clamp') == {
        'line': 30, 'end': 30, 'vis': 'internal', 'sig': 'const clamp = (x: number, lo = 0): number =>', 'doc': None}
    assert g.nodes['f:src/api.tsx:useStore']['sig'] == 'export const useStore = create<State>()(…)'
    assert meta_of(g, 'f:src/api.tsx:helper') == {
        'line': 55, 'end': 55, 'vis': 'public', 'sig': 'function helper()', 'doc': None}
    assert g.nodes['f:src/local.js:local']['vis'] == 'public'
    assert g.nodes['f:src/local.js:hidden']['vis'] == 'internal'
    module = g.nodes['m:src/api.tsx']
    assert (module['end'], module['doc']) == (57, 'Shared helpers for the app.')
    assert 'sig' not in module and 'vis' not in module


def test_classes_methods_and_interfaces_carry_signature_doc_and_visibility(tmp_path):
    g = ts_graph(tmp_path / 'enriched', ENRICHED)
    assert meta_of(g, 'c:src/api.tsx:App') == {
        'line': 36, 'end': 47, 'vis': 'public', 'doc': 'Main app.',
        'sig': 'export class App extends React.Component<Props, State> implements Disposable'}
    assert meta_of(g, 'f:src/api.tsx:App.load') == {
        'line': 39, 'end': 41, 'vis': 'public', 'sig': 'async load(id: number): Promise<void>', 'doc': 'Loads it.'}
    assert meta_of(g, 'f:src/api.tsx:App.save')['vis'] == 'private'
    assert meta_of(g, 'f:src/api.tsx:App.save')['doc'] is None
    assert meta_of(g, 'f:src/api.tsx:App.handle') == {
        'line': 44, 'end': 44, 'vis': 'protected', 'sig': 'protected handle = (e: Event): void =>', 'doc': None}
    assert meta_of(g, 'f:src/api.tsx:App.#secret')['vis'] == 'private'
    assert meta_of(g, 'f:src/api.tsx:App.create')['sig'] == 'static create()'
    assert meta_of(g, 'c:src/api.tsx:Props') == {
        'line': 50, 'end': 52, 'vis': 'internal', 'sig': 'interface Props<T> extends Base', 'doc': 'Button props.'}


def test_vue_sfc_symbols_keep_original_line_numbers(tmp_path):
    g = ts_graph(tmp_path / 'enriched', ENRICHED)
    assert meta_of(g, 'f:src/Counter.vue:useCounter') == {
        'line': 8, 'end': 10, 'vis': 'internal', 'sig': 'function useCounter(start: number)', 'doc': 'Counter state.'}
    assert g.nodes['m:src/Counter.vue']['end'] == 11


def test_unresolved_bare_imports_are_recorded_as_externals(tmp_path):
    g = ts_graph(tmp_path / 'enriched', ENRICHED)
    assert g.externals == [
        ('m:src/Counter.vue', 'vue', 'ts'),
        ('m:src/api.tsx', 'react', 'ts'),
        ('m:src/api.tsx', '@tanstack/react-query/devtools', 'ts'),
        ('m:src/api.tsx', 'node:fs', 'ts'),
        ('m:src/api.tsx', 'jotai', 'ts'),
        ('m:src/api.tsx', 'dotenv', 'ts'),
        ('m:src/api.tsx', 'lodash/debounce', 'ts'),
    ]


def test_workspace_packages_are_not_externals(tmp_path):
    g = ts_graph(tmp_path / 'barrel', BARREL)
    assert ('m:apps/web/src/use.ts', '@pkg/math', 'ts') not in g.externals
    assert ('m:packages/math/src/index.ts', 'jotai', 'ts') in g.externals


def test_long_signatures_are_clipped_and_doc_tags_dropped(tmp_path):
    params = ', '.join(f'argument{i}: number' for i in range(40))
    g = ts_graph(tmp_path / 'long', {'src/long.ts': f"""
        /** @deprecated use other */
        export function wide({params}) {{ return 1; }}
    """})
    meta = g.nodes['f:src/long.ts:wide']
    assert len(meta['sig']) == 300 and meta['sig'].endswith('…')
    assert 'doc' not in meta


TYPED = {
    'src/store.ts': """
        export class Store {
          load(id: string): Item { return new Item(); }
          async fetch(): Promise<Item> { return new Item(); }
        }
        export class Item {
          save() {}
        }
        export interface Repo {
          find(id: string): Item;
          onChange: (id: string) => void;
          name: string;
        }
        export type Handler = (store: Store, next: () => void) => void;
        export type Maybe = Store | undefined;
        export enum Mode { A, B }
        export function run(handler: Handler) {}
        export const shared = new Store();
    """,
    'src/index.ts': """
        export { Store, Item } from "./store";
        export type { Repo, Handler } from "./store";
    """,
    'src/app.ts': """
        import { Store, Repo, Handler } from "./index";
        import { Maybe, run, shared } from "./store";

        class Service {
          constructor(private store: Store, public repo: Repo) {}
          other = new Store();
          get current(): Store { return this.store; }
          go(maybe: Maybe) {
            this.store.load('a').save();
            this.repo.find('x');
            this.repo.onChange('x');
            this.other.load('b');
            this.current.load('c');
            maybe!.load('d');
          }
          async later() {
            const item = await this.store.fetch();
            item.save();
            const { store } = this;
            store.load('e');
          }
        }

        export const handle: Handler = (s, next) => {
          s.load('f');
          next();
        };

        export function main() {
          run((s) => s.load('g'));
          shared.load('h');
          const load = () => 1;
          load();
        }
    """,
}


def test_local_types_resolve_member_calls(tmp_path):
    g = ts_graph(tmp_path / 'typed', TYPED)
    calls = edges_of(g, 'call')
    store, item, repo = 'f:src/store.ts:Store', 'f:src/store.ts:Item', 'f:src/store.ts:Repo'
    assert {
        ('f:src/app.ts:Service.go', f'{store}.load', 'call'),
        ('f:src/app.ts:Service.go', f'{item}.save', 'call'),
        ('f:src/app.ts:Service.go', f'{repo}.find', 'call'),
        ('f:src/app.ts:Service.go', f'{repo}.onChange', 'call'),
        ('f:src/app.ts:Service.later', f'{store}.fetch', 'call'),
        ('f:src/app.ts:Service.later', f'{item}.save', 'call'),
        ('f:src/app.ts:Service.later', f'{store}.load', 'call'),
        ('f:src/app.ts:handle', f'{store}.load', 'call'),
        ('f:src/app.ts:main', f'{store}.load', 'call'),
        ('f:src/app.ts:main', 'f:src/store.ts:run', 'call'),
    } <= calls
    assert not any(b == 'f:src/app.ts:load' for _, b, _ in calls)


def test_types_interfaces_and_signatures_are_symbols(tmp_path):
    g = ts_graph(tmp_path / 'typed', TYPED)
    kinds = {nid: m['kind'] for nid, m in g.nodes.items()}
    assert kinds['c:src/store.ts:Handler'] == 'class'
    assert kinds['c:src/store.ts:Mode'] == 'class'
    assert kinds['f:src/store.ts:Repo.find'] == 'method'
    assert kinds['f:src/store.ts:Repo.onChange'] == 'method'
    assert 'f:src/store.ts:Repo.name' not in g.nodes
    assert ('c:src/store.ts:Repo', 'f:src/store.ts:Repo.find', 'contains') in g.edges


def test_imports_through_barrels_reach_the_defining_module(tmp_path):
    g = ts_graph(tmp_path / 'typed', TYPED)
    imports = edges_of(g, 'import')
    assert ('m:src/app.ts', 'm:src/index.ts', 'import') in imports
    assert ('m:src/app.ts', 'm:src/store.ts', 'import') in imports
    assert ('m:src/index.ts', 'm:src/store.ts', 'import') in imports


AMBIENT = {
    'src/api.ts': """
        export abstract class Base {
          abstract run(x: number): void;
          start() { this.run(1); }
        }
        export function over(a: string): string;
        export function over(a: number): number;
        export function over(a: any) { return a; }
        export namespace Shapes {
          export interface Circle { r: number }
          export function area() { return 1; }
        }
        declare global {
          interface Window { app: Base }
        }
        declare abstract class Fetcher {
          fetch(input: string): void
        }
        export const pick: (a: number) => number = Math.abs;
        export interface Overloads {
          (a: string): Base
          // second
          <T>(a: T, b: T): Base
        }
        export function after() {}
    """,
}


def test_ambient_namespaces_overloads_and_abstract_members(tmp_path):
    g = ts_graph(tmp_path / 'ambient', AMBIENT)
    nodes = g.nodes
    assert nodes['f:src/api.ts:Base.run']['kind'] == 'method'
    assert ('f:src/api.ts:Base.start', 'f:src/api.ts:Base.run', 'call') in g.edges
    assert nodes['f:src/api.ts:over']['line'] == 5 and nodes['f:src/api.ts:over']['end'] == 7
    assert {'f:src/api.ts:Shapes.area', 'c:src/api.ts:Shapes.Circle', 'c:src/api.ts:Window', 'c:src/api.ts:Fetcher',
            'f:src/api.ts:Fetcher.fetch', 'f:src/api.ts:pick', 'f:src/api.ts:after'} <= set(nodes)


def test_consts_built_by_local_function_factories_are_functions(tmp_path):
    g = ts_graph(tmp_path / 'factory', {'src/utils.js': """
        const typeOfTest = (type) => (thing) => typeof thing === type;
        function kindOf(name) { return function (thing) { return thing.kind === name; }; }
        const isFunction = typeOfTest('function');
        const isCart = kindOf('cart');
        const answer = Number('42');
        export function check(x) { return isFunction(x) && isCart(x); }
    """})
    assert g.nodes['f:src/utils.js:isFunction']['kind'] == 'function'
    assert g.nodes['f:src/utils.js:isCart']['kind'] == 'function'
    assert 'f:src/utils.js:answer' not in g.nodes
    assert ('f:src/utils.js:check', 'f:src/utils.js:isFunction', 'call') in g.edges
