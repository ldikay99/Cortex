import json
import os
import subprocess
import sys

import pytest

from conftest import edge_set, write_repo
from cortex_graph.analyze import analyze, is_test, list_files
from cortex_graph.errors import CortexError

GO = {
    'go.mod': """
        module example.com/app
    """,
    'models/user.go': """
        package models

        type User struct{ Name string }

        func Persist(u *User) error { return validate(u) }

        func validate(u *User) error { return nil }

        func (u *User) Save() error { return Persist(u) }
    """,
    'svc/helper.go': """
        package svc

        func helper() {}
    """,
    'svc/service.go': """
        package svc

        import (
          "fmt"
          m "example.com/app/models"
        )

        func Run() {
          fmt.Println(1)
          u := &m.User{}
          m.Persist(u)
          helper()
          validate(u)
          u.Save()
        }
    """,
}

RUST = {
    'Cargo.toml': """
        [package]
        name = "demo-app"
    """,
    'src/main.rs': """
        mod models;
        mod util;
        use crate::models::user::{User, Role};

        fn main() {
            let u = User::new();
            util::greet();
            helper();
        }

        fn helper() {}
    """,
    'src/models/mod.rs': """
        pub mod user;
    """,
    'src/models/user.rs': """
        pub struct User { pub name: String }
        pub enum Role { Admin }
        pub trait Named { fn name(&self) -> String; }

        impl User {
            pub fn new() -> Self { Self::blank() }
            fn blank() -> Self { User { name: String::new() } }
        }

        impl Named for User {
            fn name(&self) -> String { self.name.clone() }
        }
    """,
    'src/util.rs': """
        pub fn greet() { println!("hi"); }
    """,
}

JAVA_USER = {
    'java/com/acme/models/Entity.java': """
        package com.acme.models;
        public abstract class Entity { }
    """,
    'java/com/acme/models/User.java': """
        package com.acme.models;
        public class User extends Entity {
          public static User load(int id) { return new User(); }
        }
    """,
}

JAVA = {
    **JAVA_USER,
    'java/com/acme/svc/Api.java': """
        package com.acme.svc;
        public interface Api { User find(int id); }
    """,
    'java/com/acme/svc/Helpers.java': """
        package com.acme.svc;
        class Helpers { static void log(String s) {} }
    """,
    'java/com/acme/svc/UserService.java': """
        package com.acme.svc;
        import com.acme.models.User;
        public class UserService implements Api {
          public User find(int id) { audit(); return User.load(id); }
          private void audit() { Helpers.log("x"); }
        }
    """,
}

KOTLIN = {
    **JAVA_USER,
    'kt/Repo.kt': """
        package com.acme.kt
        import com.acme.models.User

        class Repo(val db: Db) : BaseRepo(), Store {
          fun get(id: Int): User = User.load(id)
          fun save() { validate(); db.write() }
        }

        fun validate() {}
        open class BaseRepo
        interface Store
        class Db { fun write() {} }
    """,
}

SCALA = {
    'Main.scala': """
        package acme
        import acme.models.User

        class Service extends Base with Api { def run(): Unit = { User.make() } }
        object Main { def main(a: Array[String]): Unit = new Service().run() }
        trait Api
        class Base
    """,
    'models/User.scala': """
        package acme.models
        object User { def make(): User = new User() }
        class User
    """,
}

CSHARP = {
    'Order.cs': """
        namespace Acme.Models;
        public class Order { public static Order Find(int id) { return new Order(); } }
    """,
    'Service.cs': """
        using Acme.Models;
        namespace Acme.Svc {
          public class OrderService : BaseService, IOrders {
            public Order Get(int id) { Log(); return Order.Find(id); }
            void Log() { }
          }
          public interface IOrders {}
          public class BaseService {}
        }
    """,
}

PHP = {
    'app/Http/helpers.php': """
        <?php
        function helper_fn() { return 1; }
    """,
    'app/Http/UserController.php': """
        <?php
        namespace App\\Http;
        use App\\Models\\User;
        require_once __DIR__ . "/helpers.php";
        class UserController {
          public function show($id) { $this->render(); helper_fn(); return User::find($id); }
          private function render() {}
        }
    """,
    'app/Models/User.php': """
        <?php
        namespace App\\Models;
        class User extends Model { public static function find($id) { return new User(); } }
        class Model {}
    """,
}

RUBY = {
    'lib/shop/base.rb': """
        module Shop
          class Base; end
          class Pricing
            def self.compute(o); 0; end
          end
        end
    """,
    'lib/shop/order.rb': """
        require_relative "base"
        module Shop
          class Order < Base
            def total
              Pricing.compute(self)
              tax_for(1)
            end
            def tax_for(x); x; end
          end
        end
    """,
    'lib/shop/cart.rb': """
        require "shop/base"
        class Cart
          def sum; Shop::Pricing.compute(self); end
        end
    """,
}

C = {
    'main.c': """
        #include "util.h"
        #include <stdio.h>
        struct point { int x; };
        static int helper(int a) { return a; }
        int main(void) { helper(1); printf("x"); return util_go(); }
    """,
    'util.c': """
        #include "util.h"
        int util_go(void) { return 1; }
    """,
    'util.h': """
        int util_go(void);
    """,
}

CPP = {
    'main.cpp': """
        #include "models/user.hpp"
        namespace acme {
        int User::id() { return compute(); }
        int compute() { return 1; }
        }
        int main() { acme::User u; u.id(); return acme::compute(); }
    """,
    'models/user.hpp': """
        namespace acme {
        class User : public Entity { public: int id(); };
        class Entity {};
        }
    """,
}

SWIFT = {
    'Repo.swift': """
        struct Repo { func fetchAll() {} }
        extension Repo { func extra() { fetchAll() } }
    """,
    'Service.swift': """
        import Foundation
        class Service: BaseService, Api {
          func run() { helper(); let r = Repo(); r.fetchAll() }
        }
        protocol Api { func run() }
        class BaseService {}
        func helper() {}
    """,
}

LUA = {
    'app/util.lua': """
        local M = {}
        function M.greet() return 1 end
        return M
    """,
    'main.lua': """
        local util = require("app.util")
        local function helper() end
        function run() util.greet() helper() end
    """,
}

LANGUAGES = {
    'go': (GO, {
        ('User', 'class'), ('Persist', 'function'), ('validate', 'function'), ('User.Save', 'method'),
        ('Run', 'function'), ('helper', 'function'),
    }, {
        ('Run', 'call', 'Persist'), ('Run', 'call', 'helper'), ('Run', 'call', 'User.Save'),
        ('User.Save', 'call', 'Persist'), ('Persist', 'call', 'validate'), ('service.go', 'import', 'user.go'),
    }),
    'rust': (RUST, {
        ('User', 'class'), ('Role', 'class'), ('Named', 'class'), ('User.new', 'method'), ('User.blank', 'method'),
        ('User.name', 'method'), ('main', 'function'), ('helper', 'function'), ('greet', 'function'),
    }, {
        ('main', 'call', 'User.new'), ('main', 'call', 'greet'), ('main', 'call', 'helper'),
        ('User.new', 'call', 'User.blank'), ('User', 'inherits', 'Named'), ('main.rs', 'import', 'util.rs'),
        ('main.rs', 'import', 'user.rs'), ('main.rs', 'import', 'mod.rs'), ('mod.rs', 'import', 'user.rs'),
    }),
    'java': (JAVA, {
        ('User', 'class'), ('User.load', 'method'), ('Entity', 'class'), ('Api', 'class'), ('UserService', 'class'),
        ('UserService.find', 'method'), ('UserService.audit', 'method'), ('Helpers.log', 'method'),
    }, {
        ('UserService.find', 'call', 'User.load'), ('UserService.find', 'call', 'UserService.audit'),
        ('UserService.audit', 'call', 'Helpers.log'), ('User', 'inherits', 'Entity'),
        ('UserService', 'inherits', 'Api'), ('UserService.java', 'import', 'User.java'),
    }),
    'kotlin': (KOTLIN, {
        ('Repo', 'class'), ('Repo.get', 'method'), ('Repo.save', 'method'), ('validate', 'function'),
        ('BaseRepo', 'class'), ('Store', 'class'), ('Db', 'class'), ('Db.write', 'method'),
    }, {
        ('Repo.get', 'call', 'User.load'), ('Repo.save', 'call', 'validate'), ('Repo.save', 'call', 'Db.write'),
        ('Repo', 'inherits', 'BaseRepo'), ('Repo', 'inherits', 'Store'), ('Repo.kt', 'import', 'User.java'),
    }),
    'scala': (SCALA, {
        ('Service', 'class'), ('Service.run', 'method'), ('Main', 'class'), ('Main.main', 'method'),
        ('User', 'class'), ('User.make', 'method'), ('Api', 'class'), ('Base', 'class'),
    }, {
        ('Service.run', 'call', 'User.make'), ('Main.main', 'call', 'Service.run'), ('Service', 'inherits', 'Base'),
        ('Service', 'inherits', 'Api'), ('Main.scala', 'import', 'User.scala'),
    }),
    'csharp': (CSHARP, {
        ('Order', 'class'), ('Order.Find', 'method'), ('OrderService', 'class'), ('OrderService.Get', 'method'),
        ('OrderService.Log', 'method'), ('IOrders', 'class'), ('BaseService', 'class'),
    }, {
        ('OrderService.Get', 'call', 'Order.Find'), ('OrderService.Get', 'call', 'OrderService.Log'),
        ('OrderService', 'inherits', 'BaseService'), ('OrderService', 'inherits', 'IOrders'),
        ('Service.cs', 'import', 'Order.cs'),
    }),
    'php': (PHP, {
        ('UserController', 'class'), ('UserController.show', 'method'), ('UserController.render', 'method'),
        ('helper_fn', 'function'), ('User', 'class'), ('User.find', 'method'), ('Model', 'class'),
    }, {
        ('UserController.show', 'call', 'UserController.render'), ('UserController.show', 'call', 'helper_fn'),
        ('UserController.show', 'call', 'User.find'), ('User', 'inherits', 'Model'),
        ('UserController.php', 'import', 'User.php'), ('UserController.php', 'import', 'helpers.php'),
    }),
    'ruby': (RUBY, {
        ('Shop', 'class'), ('Base', 'class'), ('Pricing', 'class'), ('Pricing.compute', 'method'), ('Order', 'class'),
        ('Order.total', 'method'), ('Order.tax_for', 'method'), ('Cart.sum', 'method'),
    }, {
        ('Order.total', 'call', 'Pricing.compute'), ('Order.total', 'call', 'Order.tax_for'),
        ('Cart.sum', 'call', 'Pricing.compute'), ('order.rb', 'import', 'base.rb'), ('cart.rb', 'import', 'base.rb'),
    }),
    'c': (C, {
        ('helper', 'function'), ('main', 'function'), ('util_go', 'function'), ('point', 'class'),
    }, {
        ('main', 'call', 'helper'), ('main', 'call', 'util_go'), ('main.c', 'import', 'util.h'),
        ('util.c', 'import', 'util.h'),
    }),
    'cpp': (CPP, {
        ('User', 'class'), ('Entity', 'class'), ('User.id', 'method'), ('compute', 'function'), ('main', 'function'),
    }, {
        ('User', 'inherits', 'Entity'), ('User.id', 'call', 'compute'), ('main', 'call', 'compute'),
        ('main.cpp', 'import', 'user.hpp'),
    }),
    'swift': (SWIFT, {
        ('Repo', 'class'), ('Repo.fetchAll', 'method'), ('Repo.extra', 'method'), ('Service', 'class'),
        ('Service.run', 'method'), ('Api', 'class'), ('BaseService', 'class'), ('helper', 'function'),
    }, {
        ('Service.run', 'call', 'helper'), ('Service.run', 'call', 'Repo'), ('Service.run', 'call', 'Repo.fetchAll'),
        ('Repo.extra', 'call', 'Repo.fetchAll'), ('Service', 'inherits', 'BaseService'),
        ('Service', 'inherits', 'Api'),
    }),
    'lua': (LUA, {
        ('run', 'function'), ('helper', 'function'), ('greet', 'function'),
    }, {
        ('run', 'call', 'greet'), ('run', 'call', 'helper'), ('main.lua', 'import', 'util.lua'),
    }),
}

MIXED = {
    'go.mod': """
        module example.com/mix
    """,
    'cmd/main.go': """
        package main

        import "example.com/mix/internal/store"

        func main() { store.Open() }
    """,
    'internal/store/store.go': """
        package store

        func Open() {}
    """,
    'app/__init__.py': '',
    'app/models.py': """
        class User:
            pass
    """,
    'app/services.py': """
        from app.models import User


        def make():
            return User()
    """,
    'web/src/lib/api.ts': """
        export function fetchUsers() { return []; }
    """,
    'web/src/index.ts': """
        import { fetchUsers } from './lib/api';

        export function boot() { return fetchUsers(); }
    """,
    'README.md': """
        # Mix

        The binary lives in `cmd/main.go`, the web in `web/src/index.ts`.
        Services are in app.services.
    """,
}


def triples(graph):
    nodes = graph['nodes']
    return {(nodes[e['a']]['name'], e['kind'], nodes[e['b']]['name']) for e in graph['edges']}


def kinds(graph):
    return {(n['name'], n['kind']) for n in graph['nodes']}


def everything():
    files = {f'{lang}/{rel}': content for lang, (repo, _, _) in LANGUAGES.items() for rel, content in repo.items()}
    files.update({f'mixed/{rel}': content for rel, content in MIXED.items()})
    return files


@pytest.mark.parametrize('lang', sorted(LANGUAGES))
def test_language_defs_and_edges(tmp_path, lang):
    files, defs, edges = LANGUAGES[lang]
    graph = analyze(write_repo(tmp_path / lang, files), lang)
    assert defs <= kinds(graph)
    assert edges <= triples(graph)
    assert graph['stats']['warnings'] == []


def test_go_does_not_guess_across_packages(tmp_path):
    graph = analyze(write_repo(tmp_path / 'go', GO), 'go')
    found = triples(graph)
    assert ('Run', 'call', 'validate') not in found
    assert not any(target == 'Println' for _, _, target in found)


def test_mixed_repo_every_language_contributes(tmp_path):
    graph = analyze(write_repo(tmp_path / 'mix', MIXED), 'mix')
    assert graph['stats']['warnings'] == []
    by_ext = {}
    for n in graph['nodes']:
        by_ext.setdefault(os.path.splitext(n['file'])[1], set()).add(n['kind'])
    assert {'module', 'function'} <= by_ext['.go']
    assert {'module', 'function', 'class'} <= by_ext['.py']
    assert {'module', 'function'} <= by_ext['.ts']
    assert by_ext['.md'] == {'doc'}
    edges = edge_set(graph)
    assert {
        ('f:cmd/main.go:main', 'f:internal/store/store.go:Open', 'call'),
        ('m:cmd/main.go', 'm:internal/store/store.go', 'import'),
        ('f:app/services.py:make', 'c:app/models.py:User', 'call'),
        ('f:web/src/index.ts:boot', 'f:web/src/lib/api.ts:fetchUsers', 'call'),
        ('d:README.md', 'm:cmd/main.go', 'ref'),
        ('d:README.md', 'm:web/src/index.ts', 'ref'),
        ('d:README.md', 'm:app/services.py', 'ref'),
    } <= edges


def test_ts_paths_wildcard_and_exact_alias(tmp_path):
    root = write_repo(tmp_path / 'paths', {
        'tsconfig.json': """
            {
              "compilerOptions": {
                "paths": {
                  "~/*": ["src/*"],
                  "settings": ["src/config/index.ts"]
                }
              }
            }
        """,
        'src/lib/text.ts': """
            export function slug(s: string) { return s; }
        """,
        'src/config/index.ts': """
            export const settings = () => 1;
        """,
        'src/pages/home.ts': """
            import { slug } from '~/lib/text';
            import { settings } from 'settings';

            export function home() { return slug('x') + settings(); }
        """,
    })
    edges = edge_set(analyze(root, 'paths'))
    assert {
        ('m:src/pages/home.ts', 'm:src/lib/text.ts', 'import'),
        ('m:src/pages/home.ts', 'm:src/config/index.ts', 'import'),
        ('f:src/pages/home.ts:home', 'f:src/lib/text.ts:slug', 'call'),
        ('f:src/pages/home.ts:home', 'f:src/config/index.ts:settings', 'call'),
    } <= edges


def test_ts_base_url(tmp_path):
    root = write_repo(tmp_path / 'base', {
        'web/tsconfig.json': """
            { "compilerOptions": { "baseUrl": "./src" } }
        """,
        'web/src/lib/format.ts': """
            export function fmt() { return 1; }
        """,
        'web/src/pages/page.ts': """
            import { fmt } from 'lib/format';

            export function page() { return fmt(); }
        """,
    })
    edges = edge_set(analyze(root, 'base'))
    assert ('m:web/src/pages/page.ts', 'm:web/src/lib/format.ts', 'import') in edges
    assert ('f:web/src/pages/page.ts:page', 'f:web/src/lib/format.ts:fmt', 'call') in edges


def test_ts_monorepo_workspace_packages(tmp_path):
    root = write_repo(tmp_path / 'mono', {
        'package.json': """
            { "name": "acme", "private": true, "workspaces": ["packages/*", "apps/*"] }
        """,
        'packages/ui/package.json': """
            { "name": "@acme/ui", "main": "dist/index.js" }
        """,
        'packages/ui/src/index.ts': """
            export function Card() { return 1; }
        """,
        'packages/ui/src/button.tsx': """
            export function Button() { return <button />; }
        """,
        'apps/web/package.json': """
            { "name": "web" }
        """,
        'apps/web/src/app.ts': """
            import { Card } from '@acme/ui';
            import { Button } from '@acme/ui/button';

            export function app() { return Card() + Button(); }
        """,
    })
    edges = edge_set(analyze(root, 'mono'))
    assert {
        ('m:apps/web/src/app.ts', 'm:packages/ui/src/index.ts', 'import'),
        ('m:apps/web/src/app.ts', 'm:packages/ui/src/button.tsx', 'import'),
        ('f:apps/web/src/app.ts:app', 'f:packages/ui/src/index.ts:Card', 'call'),
        ('f:apps/web/src/app.ts:app', 'f:packages/ui/src/button.tsx:Button', 'call'),
    } <= edges


def test_vue_and_svelte_parse_only_scripts(tmp_path):
    root = write_repo(tmp_path / 'sfc', {
        'src/lib/text.ts': """
            export function slug(s: string) { return s; }
        """,
        'src/components/Hello.vue': """
            <template>
              <div @click="greet()">{{ slug('hola') }}</div>
            </template>

            <script setup lang="ts">
            import { slug } from '../lib/text';

            function greet() {
              return slug('hola');
            }
            </script>

            <style scoped>
            div { color: red; }
            </style>
        """,
        'src/components/Btn.svelte': """
            <script lang="ts">
              import { slug } from '../lib/text';
              export function act() { return slug('x'); }
            </script>

            <button on:click={act}>x</button>
        """,
    })
    graph = analyze(root, 'sfc')
    nodes = {n['key']: n for n in graph['nodes']}
    edges = edge_set(graph)
    assert nodes['f:src/components/Hello.vue:greet']['line'] == 8
    assert nodes['f:src/components/Btn.svelte:act']['line'] == 3
    assert {
        ('m:src/components/Hello.vue', 'm:src/lib/text.ts', 'import'),
        ('f:src/components/Hello.vue:greet', 'f:src/lib/text.ts:slug', 'call'),
        ('m:src/components/Btn.svelte', 'm:src/lib/text.ts', 'import'),
        ('f:src/components/Btn.svelte:act', 'f:src/lib/text.ts:slug', 'call'),
    } <= edges
    assert graph['stats']['warnings'] == []


@pytest.mark.parametrize('rel', [
    'svc/user_test.go', 'lib/user_spec.rb', 'src/UserTest.java', 'src/UserTests.kt', 'App/OrderTests.cs',
    'Sources/RepoTests.swift', 'src/UserTest.php', 'src/a.test.go', 'src/a.spec.rb', 'web/Home.spec.tsx',
    'src/Tests/Foo.cs', 'src/Test/Foo.java', 'Spec/foo.rb', '__tests__/x.js',
])
def test_is_test_new_patterns(rel):
    assert is_test(rel)


@pytest.mark.parametrize('rel', [
    'src/Contest.java', 'src/Latest.kt', 'src/protest.go', 'src/attestation.py', 'lib/testing_utils/x.rb.txt',
    'src/Testimonial.swift',
])
def test_is_test_negatives(rel):
    assert not is_test(rel)


def test_list_files_skips_vendored_and_built_output(tmp_path):
    root = write_repo(tmp_path / 'skip', {
        'vendor/lib/a.go': 'package lib\n',
        'target/debug/b.rs': 'fn b() {}\n',
        'Pods/Kit/c.swift': 'func c() {}\n',
        'obj/Debug/d.cs': 'class D {}\n',
        '.gradle/e.kt': 'fun e() {}\n',
        'web/app.min.js': 'var a=1;\n',
        'web/types.d.ts': 'export {};\n',
        'web/app.js': 'export const a = 1;\n',
        'src/main.go': 'package main\n',
        'src/lib.rs': 'fn x() {}\n',
        'docs/guide.rst': 'Guide\n',
        'docs/page.mdx': '# Page\n',
        'notes.txt': 'notes\n',
    })
    assert list_files(root) == ['notes.txt', 'docs/guide.rst', 'docs/page.mdx', 'src/lib.rs', 'src/main.go', 'web/app.js']


def test_readme_only_repo(tmp_path):
    root = write_repo(tmp_path / 'readme', {'README.md': '# Solo\n\nNothing else here.\n'})
    graph = analyze(root, 'readme')
    assert [(n['key'], n['kind']) for n in graph['nodes']] == [('d:README.md', 'doc')]
    assert graph['edges'] == []
    assert len(graph['communities']) == 1


def test_only_unsupported_files_is_a_clean_error(tmp_path):
    root = write_repo(tmp_path / 'blobs', {'photo.png': 'x', 'blob.bin': 'y'})
    with pytest.raises(CortexError, match='no hay código'):
        analyze(root, 'blobs')


def test_plain_text_and_tables_become_documents(tmp_path):
    root = write_repo(tmp_path / 'text', {'notes.txt': 'hola\n', 'data.csv': 'a,b\n1,2\n'})
    graph = analyze(root, 'text')
    assert sorted((n['key'], n['kind']) for n in graph['nodes'] if n['kind'] == 'doc') == [('d:data.csv', 'doc'), ('d:notes.txt', 'doc')]


def test_malformed_sources_do_not_crash(tmp_path):
    root = tmp_path / 'broken'
    root.mkdir()
    (root / 'broken.go').write_text('package x\nfunc (( {\n', encoding='utf-8')
    (root / 'bytes.rs').write_bytes(b'\xff\xfe fn \x00 main( {')
    (root / 'plain.php').write_text('no php tag here\n', encoding='utf-8')
    (root / 'half.java').write_text('class A { void f( {', encoding='utf-8')
    graph = analyze(root, 'broken')
    assert {n['file'] for n in graph['nodes'] if n['kind'] == 'module'} == {'broken.go', 'bytes.rs', 'plain.php', 'half.java'}


def test_multi_language_analysis_is_deterministic(tmp_path):
    root = write_repo(tmp_path / 'all', everything())
    first = analyze(root, 'all')
    second = analyze(root, 'all')
    assert first['nodes'] == second['nodes']
    assert first['edges'] == second['edges']
    assert first['visible'] == second['visible']
    assert first['communities'] == second['communities']
    copy = write_repo(tmp_path / 'copy', everything())
    third = analyze(copy, 'all')
    assert third['nodes'] == first['nodes'] and third['edges'] == first['edges']


def test_multi_language_analysis_ignores_hash_seed(tmp_path):
    root = write_repo(tmp_path / 'all', everything())
    script = (
        'import json, sys\n'
        'from cortex_graph.analyze import analyze\n'
        'g = analyze(sys.argv[1], "all")\n'
        'print(json.dumps([g["nodes"], g["edges"], g["visible"], g["communities"]], sort_keys=True))\n'
    )
    outputs = []
    for seed in ('1', '2'):
        env = {**os.environ, 'PYTHONHASHSEED': seed}
        run = subprocess.run([sys.executable, '-c', script, str(root)], capture_output=True, text=True, env=env,
                             check=True)
        outputs.append(json.loads(run.stdout))
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize('files,child,qualifier', [
    ({
        'base.rb': 'module Shop\nend\nclass Shop::Base\nend\n',
        'order.rb': 'require_relative "base"\nclass Order < Shop::Base\nend\n',
    }, 'Order', 'Shop'),
    ({
        'p/Outer.java': 'package p;\npublic class Outer { public static class Inner {} }\n',
        'p/Kid.java': 'package p;\npublic class Kid extends Outer.Inner {}\n',
    }, 'Kid', 'Outer'),
])
def test_qualified_superclass_does_not_inherit_qualifier(tmp_path, files, child, qualifier):
    found = triples(analyze(write_repo(tmp_path / 'q', files), 'q'))
    assert (child, 'inherits', qualifier) not in found


def test_ruby_superclass_in_same_module_other_file(tmp_path):
    root = write_repo(tmp_path / 'rb', {
        'base.rb': 'module Shop\n  class Base; end\nend\n',
        'order.rb': 'require_relative "base"\nmodule Shop\n  class Order < Base\n  end\nend\n',
    })
    assert ('Order', 'inherits', 'Base') in triples(analyze(root, 'rb'))


def test_doc_file_name_does_not_link_python_module(tmp_path):
    root = write_repo(tmp_path / 'docs', {
        'service.py': 'def handler():\n    return 1\n',
        'cmd/service.go': 'package main\n\nfunc main() {}\n',
        'README.md': '# Docs\n\nThe entry point is service.go.\n',
    })
    edges = edge_set(analyze(root, 'docs'))
    assert ('d:README.md', 'm:cmd/service.go', 'ref') in edges
    assert ('d:README.md', 'm:service.py', 'ref') not in edges
