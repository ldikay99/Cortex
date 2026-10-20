import pytest

from conftest import write_repo
from cortex_graph.analyze import analyze

BASH = {
    'bin/run.sh': """
        #!/usr/bin/env bash
        DIR="$(cd "$(dirname "$0")" && pwd)"
        source "$DIR/../lib/util.sh"

        main() {
          slugify "$1"
          helper
        }

        function helper {
          echo listo
        }

        main "$@"
    """,
    'lib/util.sh': """
        slugify() {
          echo "$1" | tr ' ' '-'
        }
    """,
}

DART = {
    'pubspec.yaml': """
        name: shop
    """,
    'lib/src/base.dart': """
        abstract class Base {
          void save() {}
        }

        mixin Audit on Base {
          void audit() {}
        }
    """,
    'lib/util.dart': """
        String slug(String s) => s.toLowerCase();
    """,
    'lib/user.dart': """
        import 'package:shop/src/base.dart';
        import 'package:flutter/material.dart';
        import 'util.dart' as u;

        class User extends Base with Audit {
          User(this.name);
          final String name;

          String greet() {
            save();
            this.audit();
            return u.slug(name);
          }
        }

        User build() {
          final user = User('ana');
          user.greet();
          return user;
        }
    """,
}

ELIXIR = {
    'lib/shop/repo.ex': """
        defmodule Shop.Repo do
          def insert(attrs), do: {:ok, attrs}
        end
    """,
    'lib/shop/store.ex': """
        defmodule Shop.Store do
          @callback put(term) :: :ok
        end
    """,
    'lib/shop/accounts/user.ex': """
        defmodule Shop.Accounts.User do
          alias Shop.Repo
          @behaviour Shop.Store

          def create(attrs) do
            attrs
            |> normalize()
            |> Repo.insert()
          end

          def put(x), do: Shop.Util.slug(x)

          defp normalize(attrs) when is_map(attrs), do: attrs

          defmodule Profile do
            def new, do: %{}
          end
        end
    """,
    'lib/shop/util.ex': """
        defmodule Shop.Util do
          def slug(x), do: String.downcase(x)
          def map(x), do: x
        end
    """,
    'lib/shop/other.ex': """
        defmodule Shop.Other do
          def run(xs), do: Enum.map(xs, & &1)
        end
    """,
    'lib/shop/report.ex': """
        defmodule Shop.Report do
          import Shop.Util

          def title(x), do: slug(x)
        end
    """,
}

HASKELL = {
    'src/App/Util.hs': """
        module App.Util (slug) where

        slug :: String -> String
        slug s = s
    """,
    'src/App/Models.hs': """
        module App.Models where

        import qualified App.Util as U
        import App.Shape

        data User = User { name :: String }

        instance Shape User where
          area _ = 1

        greet :: User -> String
        greet u = U.slug (name u) ++ helper u

        helper :: User -> String
        helper = name
    """,
    'src/App/Shape.hs': """
        module App.Shape where

        class Shape a where
          area :: a -> Double
    """,
}

ZIG = {
    'src/util.zig': """
        pub fn slug(x: []const u8) []const u8 {
            return x;
        }
    """,
    'src/main.zig': """
        const std = @import("std");
        const util = @import("util.zig");

        pub const User = struct {
            name: []const u8,

            pub fn init(name: []const u8) User {
                return .{ .name = util.slug(name) };
            }

            pub fn greet(self: User) void {
                self.log();
            }

            fn log(self: User) void {
                _ = self;
            }
        };

        pub fn main() void {
            const u = User.init("ana");
            u.greet();
        }
    """,
}

OCAML = {
    'lib/util.ml': """
        let slug s = String.lowercase_ascii s
        let twice f x = f (f x)
    """,
    'lib/util.mli': """
        val slug : string -> string
    """,
    'lib/shapes.ml': """
        class shape = object
          method area = 0
        end
    """,
    'lib/models.ml': """
        open Shapes

        type user = { name : string }

        let greet u = Util.slug u.name ^ helper u
        and helper u = u.name

        module Store = struct
          let save u = greet u
        end

        class square = object
          inherit shape
          method side = 1
        end
    """,
}

JULIA = {
    'src/Shop.jl': """
        module Shop

        include("util.jl")
        include("models.jl")

        end
    """,
    'src/util.jl': """
        slug(s) = lowercase(s)
    """,
    'src/models.jl': """
        abstract type Shape end

        struct User <: Shape
            name::String
        end

        function greet(u::User)
            slug(u.name)
        end
    """,
    'src/app.jl': """
        using Shop

        run(u) = Shop.greet(u)
        Base.length(u::Shop.User) = 1
        size(u) = length(u)
    """,
}

OBJC = {
    'Sources/Base.m': """
        @implementation Base
        - (void)save {
        }
        @end
    """,
    'Sources/User.m': """
        #import "Base.h"
        #import <Foundation/Foundation.h>

        @interface User : Base <NSCoding>
        - (void)greet;
        @end

        @implementation User
        - (void)greet {
            [self save];
            [self helper];
            log_line(1);
        }
        - (void)helper {
        }
        @end

        void log_line(int x) {
        }
    """,
}

HCL = {
    'infra/main.tf': """
        resource "aws_s3_bucket" "logs" {
          bucket = "logs-${var.env}"
        }

        module "vpc" {
          source = "./modules/vpc"
          name   = aws_s3_bucket.logs.id
        }
    """,
    'infra/variables.tf': """
        variable "env" {
          default = "prod"
        }
    """,
    'infra/outputs.tf': """
        output "bucket" {
          value = aws_s3_bucket.logs.arn
        }
    """,
    'infra/modules/vpc/main.tf': """
        variable "name" {}

        resource "aws_vpc" "this" {
          tags = { Name = var.name }
        }
    """,
    'other/main.tf': """
        variable "env" {}
    """,
}

GROOVY = {
    'src/main/groovy/com/shop/Base.groovy': """
        package com.shop

        class Base {
          def save() { true }
        }
    """,
    'src/main/groovy/com/shop/util/Text.groovy': """
        package com.shop.util

        class Text {
          static String slug(String s) { s.toLowerCase() }
        }
    """,
    'src/main/groovy/com/shop/User.groovy': """
        package com.shop

        import com.shop.util.Text

        class User extends Base {
          String name
          def greet() {
            save()
            Text.slug(name)
          }
        }
    """,
    'build.gradle': """
        apply from: 'gradle/extra.gradle'
    """,
    'gradle/extra.gradle': """
        def extra() { 1 }
    """,
}

PERL = {
    'lib/Shop/Base.pm': """
        package Shop::Base;
        use strict;

        sub new { my ($class) = @_; return bless {}, $class }
        sub save { 1 }

        1;
    """,
    'lib/Shop/Util.pm': """
        package Shop::Util;

        sub slug { lc shift }

        1;
    """,
    'lib/Shop/User.pm': """
        package Shop::User;
        use strict;
        use parent -norequire, 'Shop::Base';
        use Shop::Util;

        sub greet {
            my $self = shift;
            $self->save();
            return Shop::Util::slug($self->{name});
        }

        1;
    """,
    'lib/Shop/Admin.pm': """
        package Shop::Admin;
        use Mojo::Base 'Shop::User';

        sub ban { my $self = shift; $self->greet }

        1;
    """,
    'bin/run.pl': """
        require "lib/Shop/User.pm";
        Shop::User->greet();
    """,
}

FSHARP = {
    'src/Text.fs': """
        namespace Shop

        module Text =
            let shout (s: string) = s.ToUpper()
    """,
    'src/Util.fs': """
        module Shop.Util

        let slug (s: string) = s.ToLower()
    """,
    'src/Models.fs': """
        namespace Shop.Models

        open Shop.Util
        open Shop.Text

        type Base() =
            member this.Save() = true

        type User(name: string) =
            inherit Base()
            member this.Greet() = slug name
            member this.Run() = this.Greet()
            member this.Loud() = shout name

        module Store =
            let save (u: User) = u.Save()
    """,
}

SOLIDITY = {
    'contracts/Base.sol': """
        pragma solidity ^0.8.0;

        contract Base {
            function _check() internal pure returns (bool) { return true; }
        }
    """,
    'contracts/lib/SafeMath.sol': """
        pragma solidity ^0.8.0;

        library SafeMath {
            function add(uint a, uint b) internal pure returns (uint) { return a + b; }
        }
    """,
    'contracts/Token.sol': """
        pragma solidity ^0.8.0;

        import "./Base.sol";
        import {SafeMath} from "./lib/SafeMath.sol";

        interface IToken {
            function transfer(address to) external returns (bool);
        }

        contract Token is Base, IToken {
            modifier onlyOwner() { _; }

            function transfer(address to) external override onlyOwner returns (bool) {
                SafeMath.add(1, 2);
                return _check();
            }
        }
    """,
}

POWERSHELL = {
    'scripts/run.ps1': """
        . "$PSScriptRoot\\lib\\util.ps1"
        using module ./Models.psm1

        function Invoke-Main {
            $slug = ConvertTo-Slug "Hola Mundo"
            $u = [User]::new()
            $u.Greet()
        }

        Invoke-Main
    """,
    'scripts/lib/util.ps1': """
        function ConvertTo-Slug($text) {
            return $text.ToLower()
        }
    """,
    'scripts/Models.psm1': """
        class Base {
            [string] Describe() { return "base" }
        }

        class User : Base {
            [string] Greet() { return $this.Describe() }
        }
    """,
}

LANGUAGES = {
    'bash': (BASH, {
        ('main', 'function'), ('helper', 'function'), ('slugify', 'function'),
    }, {
        ('run.sh', 'import', 'util.sh'), ('main', 'call', 'slugify'), ('main', 'call', 'helper'),
    }),
    'dart': (DART, {
        ('Base', 'class'), ('Audit', 'class'), ('User', 'class'), ('User.greet', 'method'), ('User.User', 'method'),
        ('build', 'function'), ('slug', 'function'),
    }, {
        ('user.dart', 'import', 'base.dart'), ('user.dart', 'import', 'util.dart'), ('User', 'inherits', 'Base'),
        ('User', 'inherits', 'Audit'), ('User.greet', 'call', 'Base.save'), ('User.greet', 'call', 'Audit.audit'),
        ('User.greet', 'call', 'slug'), ('build', 'call', 'User'), ('build', 'call', 'User.greet'),
    }),
    'elixir': (ELIXIR, {
        ('Shop.Accounts.User', 'class'), ('Shop.Accounts.User.Profile', 'class'), ('Shop.Repo', 'class'),
        ('Shop.Accounts.User.create', 'method'), ('Shop.Accounts.User.normalize', 'method'),
        ('Shop.Accounts.User.Profile.new', 'method'),
    }, {
        ('user.ex', 'import', 'repo.ex'), ('Shop.Accounts.User', 'inherits', 'Shop.Store'),
        ('Shop.Accounts.User.create', 'call', 'Shop.Accounts.User.normalize'),
        ('Shop.Accounts.User.create', 'call', 'Shop.Repo.insert'), ('Shop.Accounts.User.put', 'call', 'Shop.Util.slug'),
        ('report.ex', 'import', 'util.ex'), ('Shop.Report.title', 'call', 'Shop.Util.slug'),
    }),
    'haskell': (HASKELL, {
        ('User', 'class'), ('Shape', 'class'), ('greet', 'function'), ('User.area', 'method'), ('slug', 'function'),
    }, {
        ('Models.hs', 'import', 'Util.hs'), ('Models.hs', 'import', 'Shape.hs'), ('User', 'inherits', 'Shape'),
        ('greet', 'call', 'slug'), ('greet', 'call', 'helper'),
    }),
    'zig': (ZIG, {
        ('User', 'class'), ('User.init', 'method'), ('User.greet', 'method'), ('main', 'function'), ('slug', 'function'),
    }, {
        ('main.zig', 'import', 'util.zig'), ('User.init', 'call', 'slug'), ('User.greet', 'call', 'User.log'),
        ('main', 'call', 'User.init'),
    }),
    'ocaml': (OCAML, {
        ('greet', 'function'), ('helper', 'function'), ('Store', 'class'), ('Store.save', 'method'), ('user', 'class'),
        ('square', 'class'), ('slug', 'function'),
    }, {
        ('models.ml', 'import', 'util.ml'), ('models.ml', 'import', 'shapes.ml'), ('greet', 'call', 'slug'),
        ('greet', 'call', 'helper'), ('Store.save', 'call', 'greet'), ('square', 'inherits', 'shape'),
    }),
    'julia': (JULIA, {
        ('User', 'class'), ('Shape', 'class'), ('greet', 'function'), ('slug', 'function'), ('run', 'function'),
    }, {
        ('Shop.jl', 'import', 'util.jl'), ('Shop.jl', 'import', 'models.jl'), ('app.jl', 'import', 'Shop.jl'),
        ('User', 'inherits', 'Shape'), ('greet', 'call', 'slug'),
    }),
    'objc': (OBJC, {
        ('User', 'class'), ('Base', 'class'), ('User.greet', 'method'), ('User.helper', 'method'), ('log_line', 'function'),
    }, {
        ('User.m', 'import', 'Base.m'), ('User', 'inherits', 'Base'), ('User.greet', 'call', 'User.helper'),
        ('User.greet', 'call', 'log_line'), ('User.greet', 'call', 'Base.save'),
    }),
    'hcl': (HCL, {
        ('aws_s3_bucket.logs', 'class'), ('module.vpc', 'class'), ('var.env', 'class'), ('output.bucket', 'class'),
        ('aws_vpc.this', 'class'),
    }, {
        ('main.tf', 'import', 'main.tf'), ('aws_s3_bucket.logs', 'call', 'var.env'),
        ('module.vpc', 'call', 'aws_s3_bucket.logs'), ('output.bucket', 'call', 'aws_s3_bucket.logs'),
        ('aws_vpc.this', 'call', 'var.name'),
    }),
    'groovy': (GROOVY, {
        ('User', 'class'), ('Base', 'class'), ('User.greet', 'method'), ('Text.slug', 'method'),
    }, {
        ('User.groovy', 'import', 'Text.groovy'), ('User', 'inherits', 'Base'), ('User.greet', 'call', 'Base.save'),
        ('User.greet', 'call', 'Text.slug'), ('build.gradle', 'import', 'extra.gradle'),
    }),
    'perl': (PERL, {
        ('Shop::User', 'class'), ('Shop::Base', 'class'), ('greet', 'function'), ('slug', 'function'),
    }, {
        ('User.pm', 'import', 'Util.pm'), ('User.pm', 'import', 'Base.pm'), ('Shop::User', 'inherits', 'Shop::Base'),
        ('greet', 'call', 'slug'), ('run.pl', 'import', 'User.pm'), ('run.pl', 'call', 'greet'),
        ('Shop::Admin', 'inherits', 'Shop::User'), ('ban', 'call', 'greet'), ('Admin.pm', 'import', 'User.pm'),
    }),
    'fsharp': (FSHARP, {
        ('User', 'class'), ('Base', 'class'), ('Store', 'class'), ('User.Greet', 'method'), ('Store.save', 'method'),
        ('slug', 'function'),
    }, {
        ('Models.fs', 'import', 'Util.fs'), ('User', 'inherits', 'Base'), ('User.Greet', 'call', 'slug'),
        ('User.Run', 'call', 'User.Greet'), ('Store.save', 'call', 'Base.Save'), ('Models.fs', 'import', 'Text.fs'),
        ('User.Loud', 'call', 'Text.shout'),
    }),
    'solidity': (SOLIDITY, {
        ('Token', 'class'), ('IToken', 'class'), ('SafeMath', 'class'), ('Token.transfer', 'method'),
        ('Token.onlyOwner', 'method'),
    }, {
        ('Token.sol', 'import', 'Base.sol'), ('Token.sol', 'import', 'SafeMath.sol'), ('Token', 'inherits', 'Base'),
        ('Token', 'inherits', 'IToken'), ('Token.transfer', 'call', 'SafeMath.add'),
        ('Token.transfer', 'call', 'Base._check'), ('Token.transfer', 'call', 'Token.onlyOwner'),
    }),
    'powershell': (POWERSHELL, {
        ('Invoke-Main', 'function'), ('ConvertTo-Slug', 'function'), ('User', 'class'), ('User.Greet', 'method'),
    }, {
        ('run.ps1', 'import', 'util.ps1'), ('run.ps1', 'import', 'Models.psm1'), ('User', 'inherits', 'Base'),
        ('Invoke-Main', 'call', 'ConvertTo-Slug'), ('Invoke-Main', 'call', 'User.Greet'),
        ('User.Greet', 'call', 'Base.Describe'),
    }),
}


def triples(graph):
    nodes = graph['nodes']
    return {(nodes[e['a']]['name'], e['kind'], nodes[e['b']]['name']) for e in graph['edges']}


def kinds(graph):
    return {(n['name'], n['kind']) for n in graph['nodes']}


def build(tmp_path, lang):
    return analyze(str(write_repo(tmp_path / lang, LANGUAGES[lang][0])))


@pytest.mark.parametrize('lang', sorted(LANGUAGES))
def test_language_defs_and_edges(tmp_path, lang):
    _, defs, edges = LANGUAGES[lang]
    graph = build(tmp_path, lang)
    assert defs - kinds(graph) == set()
    assert edges - triples(graph) == set()
    assert graph['stats']['warnings'] == []


def test_dart_skips_foreign_packages(tmp_path):
    files = dict(DART, **{'lib/material.dart': 'void unrelated() {}\n'})
    found = triples(analyze(str(write_repo(tmp_path / 'dart', files))))
    assert ('user.dart', 'import', 'material.dart') not in found


def test_elixir_external_module_call_is_not_guessed(tmp_path):
    found = triples(build(tmp_path, 'elixir'))
    assert ('Shop.Other.run', 'call', 'Shop.Util.map') not in found


def test_hcl_variables_stay_in_their_module(tmp_path):
    graph = build(tmp_path, 'hcl')
    nodes = graph['nodes']
    refs = {(nodes[e['a']]['file'], nodes[e['b']]['file']) for e in graph['edges'] if e['kind'] == 'call'}
    assert ('infra/main.tf', 'infra/variables.tf') in refs
    assert ('infra/main.tf', 'other/main.tf') not in refs
    imports = {(nodes[e['a']]['file'], nodes[e['b']]['file']) for e in graph['edges'] if e['kind'] == 'import'}
    assert ('infra/main.tf', 'infra/modules/vpc/main.tf') in imports


def test_julia_base_extension_keeps_its_qualifier(tmp_path):
    graph = build(tmp_path, 'julia')
    assert ('Base.length', 'function') in kinds(graph)
    assert not any(b == 'Base.length' for _, kind, b in triples(graph) if kind == 'call')


def test_ocaml_interface_is_its_own_unit(tmp_path):
    graph = build(tmp_path, 'ocaml')
    slugs = {n['file'] for n in graph['nodes'] if n['name'] == 'slug'}
    assert slugs == {'lib/util.ml', 'lib/util.mli'}
    assert ('greet', 'call', 'slug') in triples(graph)


def test_new_languages_are_deterministic(tmp_path):
    files = {f'{lang}/{rel}': content for lang, (repo, _, _) in LANGUAGES.items() for rel, content in repo.items()}
    first = analyze(str(write_repo(tmp_path / 'a', files)))
    second = analyze(str(write_repo(tmp_path / 'b', files)))
    assert [(n['key'], n['kind']) for n in first['nodes']] == [(n['key'], n['kind']) for n in second['nodes']]
    assert [(e['a'], e['b'], e['kind']) for e in first['edges']] == [(e['a'], e['b'], e['kind']) for e in second['edges']]


def imports(graph):
    nodes = graph['nodes']
    return {(nodes[e['a']]['file'], nodes[e['b']]['file']) for e in graph['edges'] if e['kind'] == 'import'}


def keyed(graph):
    return {n['key']: n for n in graph['nodes']}


RUST_CRATES = {
    'Cargo.toml': """
        [workspace]
        members = ["a", "b"]
    """,
    'a/Cargo.toml': """
        [package]
        name = "alpha"
    """,
    'a/src/lib.rs': """
        pub fn run(x: Option<u8>) -> u8 {
            let v = x.unwrap();
            v.frobnicate();
            std::thread::spin_all();
            local_helper()
        }

        fn local_helper() -> u8 { 1 }
    """,
    'b/Cargo.toml': """
        [package]
        name = "beta"
    """,
    'b/src/lib.rs': """
        pub struct Query;

        impl Query {
            pub fn unwrap(self) -> u8 { 0 }
            pub fn frobnicate(&self) {}
        }

        pub fn spin_all() {}
    """,
    'b/src/util.rs': """
        pub fn go<T>(q: T) {
            q.frobnicate();
        }
    """,
}


def test_rust_receiver_calls_stay_in_their_crate(tmp_path):
    found = triples(analyze(str(write_repo(tmp_path / 'rust', RUST_CRATES))))
    assert ('run', 'call', 'local_helper') in found
    assert ('run', 'call', 'Query.unwrap') not in found
    assert ('run', 'call', 'Query.frobnicate') not in found
    assert ('run', 'call', 'spin_all') not in found
    assert ('go', 'call', 'Query.frobnicate') in found


RUST_TESTS = {
    'Cargo.toml': """
        [package]
        name = "solo"
    """,
    'src/lib.rs': """
        pub fn add(a: u8, b: u8) -> u8 { a + b }

        #[cfg(test)]
        mod tests {
            use super::*;

            #[test]
            fn adds() { assert_eq!(add(1, 2), 3); }
        }

        #[test]
        fn loose() { add(0, 0); }

        #[cfg(not(test))]
        fn shipped() { add(1, 1); }
    """,
}


def lang_nodes(root, files, skip_tests):
    from cortex_graph import langs
    from cortex_graph.common import Graph, Issues, describe_failure, digest, read_source
    g = Graph()
    langs.analyze_languages(root, files, g, Issues(), read_source, describe_failure, digest, skip_tests=skip_tests)
    return g


def test_rust_tests_inside_sources_are_skipped(tmp_path):
    root = write_repo(tmp_path / 'rust', RUST_TESTS)
    kept = lang_nodes(root, ['src/lib.rs'], False)
    skipped = lang_nodes(root, ['src/lib.rs'], True)
    assert {'f:src/lib.rs:adds', 'f:src/lib.rs:loose'} <= set(kept.nodes)
    assert {'f:src/lib.rs:adds', 'f:src/lib.rs:loose'} & set(skipped.nodes) == set()
    assert {'f:src/lib.rs:add', 'f:src/lib.rs:shipped'} <= set(skipped.nodes)
    assert ('f:src/lib.rs:shipped', 'f:src/lib.rs:add', 'call') in skipped.edges


GO_PACKAGES = {
    'go.mod': """
        module example.com/web
    """,
    'render/render.go': """
        package render

        type Render interface{ Render() error }
    """,
    'render/json.go': """
        package render

        type JSON struct{ Data any }
    """,
    'binding/binding.go': """
        package binding

        type Binding interface{ Name() string }
    """,
    'binding/form.go': """
        package binding

        type formBinding struct{}
    """,
    'config/config.go': """
        package config

        type Options struct{}
    """,
    'config/opts.go': """
        package config

        var Opts = 1

        const (
          Mode = "debug"
        )
    """,
    'context.go': """
        package web

        import (
          "net/http"

          "example.com/web/binding"
          "example.com/web/config"
          "example.com/web/render"
        )

        var mode = config.Mode

        type Context struct {
          b binding.Binding
          w http.ResponseWriter
        }

        func (c *Context) JSON() any {
          return render.JSON{}
        }
    """,
}


def test_go_package_imports_and_type_uses(tmp_path):
    found = imports(analyze(str(write_repo(tmp_path / 'go', GO_PACKAGES))))
    assert ('context.go', 'binding/binding.go') in found
    assert ('context.go', 'render/json.go') in found
    assert ('context.go', 'render/render.go') not in found
    assert ('context.go', 'binding/form.go') not in found
    assert ('context.go', 'config/opts.go') in found
    assert ('context.go', 'config/config.go') not in found


CSHARP_TYPES = {
    'Domain/ShipOrderCommand.cs': """
        namespace Shop.Domain;
        public record ShipOrderCommand(int Id);
    """,
    'Domain/IAppDbContext.cs': """
        namespace Shop.Domain;
        public interface IAppDbContext { }
    """,
    'Api/Handlers.cs': """
        using MediatR;
        using Shop.Domain;

        namespace Shop.Api;

        public class ShipOrderHandler : IRequestHandler<ShipOrderCommand, bool>
        {
            private readonly IAppDbContext _context;
            public ShipOrderHandler(IAppDbContext context) { _context = context; }
        }
    """,
    'Api/Other.cs': """
        namespace Shop.Api;
        public class Other { public Task<int> Run() { return null; } }
    """,
    'Shared/Task.cs': """
        namespace Shop.Shared;
        public class Task { }
    """,
}


def test_csharp_type_references_link_files(tmp_path):
    found = imports(analyze(str(write_repo(tmp_path / 'cs', CSHARP_TYPES))))
    assert ('Api/Handlers.cs', 'Domain/ShipOrderCommand.cs') in found
    assert ('Api/Handlers.cs', 'Domain/IAppDbContext.cs') in found
    assert ('Api/Other.cs', 'Shared/Task.cs') not in found


C_ANGLE = {
    'include/acme/core.h': """
        struct acme_core { int x; };
    """,
    'include/acme/util.h': """
        #include <acme/core.h>
        #include <stdio.h>
        #include <vector>
        int util(void);
    """,
    'src/main.cpp': """
        #include <acme/util.h>
        #include <util.h>
        int main() { return util(); }
    """,
    'other/util.h': """
        int other_util(void);
    """,
    'compat/stdio.h': """
        int compat_printf(void);
    """,
    'src/vector.h': """
        struct vec { int n; };
    """,
}


def test_c_angle_includes_need_a_full_suffix(tmp_path):
    found = imports(analyze(str(write_repo(tmp_path / 'c', C_ANGLE))))
    assert ('include/acme/util.h', 'include/acme/core.h') in found
    assert ('src/main.cpp', 'include/acme/util.h') in found
    assert ('src/main.cpp', 'other/util.h') not in found
    assert ('include/acme/util.h', 'compat/stdio.h') not in found
    assert ('include/acme/util.h', 'src/vector.h') not in found


OBJC_HEADERS = {
    'Lib/AFManager.h': """
        #import <Foundation/Foundation.h>
        #import "AFSerializer.h"

        @interface AFManager : NSObject
        - (void)start;
        @end
    """,
    'Lib/AFSerializer.h': """
        @interface AFSerializer : NSObject
        @end
    """,
    'Lib/AFManager.m': """
        #import "AFManager.h"

        @implementation AFManager
        - (void)start { }
        @end
    """,
    'Lib/Bridge.m': """
        #import "plain.h"

        @implementation Bridge
        - (int)run { return plain(); }
        @end
    """,
    'Plain/plain.h': """
        int plain(void);
    """,
}


def test_objc_headers_use_the_objc_grammar(tmp_path):
    graph = analyze(str(write_repo(tmp_path / 'objc', OBJC_HEADERS)))
    nodes = keyed(graph)
    assert nodes['c:Lib/AFManager.h:AFManager']['kind'] == 'class'
    assert nodes['c:Lib/AFSerializer.h:AFSerializer']['kind'] == 'class'
    found = imports(graph)
    assert ('Lib/AFManager.h', 'Lib/AFSerializer.h') in found
    assert ('Lib/AFManager.m', 'Lib/AFManager.h') in found
    assert ('Lib/Bridge.m', 'Plain/plain.h') in found


STDLIB_CALLS = {
    'kt/Rules.kt': """
        package acme.rules
        fun check(value: Boolean) {}
    """,
    'kt/App.kt': """
        package acme.app
        fun start() { check(true) }
    """,
    'cpp/clamp.h': """
        namespace detail { int clampify(int x) { return x; } }
    """,
    'cpp/main.cpp': """
        int run() { return std::clampify(1) + detail::clampify(2); }
    """,
    'java/Util.java': """
        package acme.util;
        public class Util { public static void shuffleAll(int n) {} }
    """,
    'java/Main.java': """
        package acme.main;
        public class Main { void go() { Collections.shuffleAll(3); } }
    """,
}


def test_stdlib_names_and_roots_never_resolve_globally(tmp_path):
    graph = analyze(str(write_repo(tmp_path / 'std', STDLIB_CALLS)))
    nodes = graph['nodes']
    calls = [(nodes[e['a']]['name'], nodes[e['b']]['name']) for e in graph['edges'] if e['kind'] == 'call']
    assert ('start', 'check') not in calls
    assert calls.count(('run', 'clampify')) == 1
    assert ('Main.go', 'Util.shuffleAll') not in calls


OVERLOADS = """
    class Calc {
      int add(int a) { return a; }
      int add(int a, int b) { return a + b; }
    }
"""


def test_editing_a_later_overload_changes_the_hash(tmp_path):
    first = keyed(analyze(str(write_repo(tmp_path / 'a', {'Calc.java': OVERLOADS}))))
    edited = OVERLOADS.replace('return a + b;', 'return b + a;')
    second = keyed(analyze(str(write_repo(tmp_path / 'b', {'Calc.java': edited}))))
    assert first['f:Calc.java:Calc.add']['hash'] != second['f:Calc.java:Calc.add']['hash']


META = {
    'go': ({'go.mod': 'module example.com/shop\n', 'shop.go': """
        // Package shop sells things.
        //
        // More text.
        package shop

        import (
            "fmt"
            gin "github.com/gin-gonic/gin"
            "example.com/shop/util"
        )

        // Server serves.
        // Second line.
        type Server struct {
            Name string
        }

        // Handle handles a request.
        //go:noinline
        func (s *Server) Handle(w int, r string) error {
            return nil
        }

        func helper() {}
    """, 'util/util.go': 'package util\n'}, {
        'c:shop.go:Server': ('type Server struct', 'Server serves. Second line.', 'public', 16),
        'f:shop.go:Server.Handle': ('func (s *Server) Handle(w int, r string) error', 'Handle handles a request.', 'public', 22),
        'f:shop.go:helper': ('func helper()', None, 'private', 24),
    }),
    'rust': ({'Cargo.toml': '[package]\nname = "shop"\n', 'src/lib.rs': """
        //! Crate docs here.

        mod util;
        use serde::Deserialize;
        use crate::util::slug;

        /// A user.
        ///
        /// Details.
        #[derive(Debug)]
        pub struct User {
            name: String,
        }

        /** Block doc. */
        pub(crate) enum Kind { A, B }

        trait Greeter {
            fn greet(&self) -> String;
        }

        impl User {
            /// Makes one.
            pub fn new(name: &str) -> Self {
                User { name: name.into() }
            }
            fn hidden(&self) {}
        }

        impl Greeter for User {
            fn greet(&self) -> String { String::new() }
        }
    """, 'src/util.rs': 'pub fn slug() {}\n'}, {
        'c:src/lib.rs:User': ('pub struct User', 'A user.', 'public', 13),
        'c:src/lib.rs:Kind': ('pub(crate) enum Kind', 'Block doc.', 'internal', 16),
        'f:src/lib.rs:Greeter.greet': ('fn greet(&self) -> String', None, 'public', 19),
        'f:src/lib.rs:User.new': ('pub fn new(name: &str) -> Self', 'Makes one.', 'public', 26),
        'f:src/lib.rs:User.hidden': ('fn hidden(&self)', None, 'private', 27),
    }),
    'java': ({'src/com/shop/User.java': """
        package com.shop;

        import org.springframework.web.bind.annotation.GetMapping;
        import org.junit.*;
        import com.shop.model.Base;

        /**
         * A user entity.
         *
         * @author me
         */
        @Entity
        public class User extends Base {
            /** Greets {@link Base} users. @return hi */
            @Override
            public String greet(String name) throws Exception {
                return "hi";
            }
            void pkg() {}
            private int secret() { return 1; }
            protected abstract void prot();
        }

        interface Repo {
            /** Finds. */
            User find(long id);
        }
    """, 'src/com/shop/model/Base.java': 'package com.shop.model;\npublic class Base {}\n'}, {
        'c:src/com/shop/User.java:User': ('public class User extends Base', 'A user entity.', 'public', 22),
        'f:src/com/shop/User.java:User.greet': ('public String greet(String name) throws Exception', 'Greets Base users.',
                                                'public', 18),
        'f:src/com/shop/User.java:User.pkg': ('void pkg()', None, 'internal', 19),
        'f:src/com/shop/User.java:User.secret': ('private int secret()', None, 'private', 20),
        'f:src/com/shop/User.java:User.prot': ('protected abstract void prot()', None, 'protected', 21),
        'c:src/com/shop/User.java:Repo': ('interface Repo', None, 'internal', 27),
        'f:src/com/shop/User.java:Repo.find': ('User find(long id)', 'Finds.', 'public', 26),
    }),
    'csharp': ({'Models/User.cs': """
        using System.Linq;

        namespace Shop.Models
        {
            /// <summary>
            /// A user with <see cref="Base"/> parent.
            /// </summary>
            /// <remarks>Ignored.</remarks>
            [Serializable]
            public class User : Base
            {
                /// <summary>Greets.</summary>
                public async Task<string> Greet(string name)
                {
                    return name;
                }
                void Hidden() {}
                protected internal void Both() {}
                internal int Count() => 1;
            }
            class Plain {}
            interface IRepo { void Save(); }
        }
    """}, {
        'c:Models/User.cs:User': ('public class User : Base', 'A user with Base parent.', 'public', 20),
        'f:Models/User.cs:User.Greet': ('public async Task<string> Greet(string name)', 'Greets.', 'public', 16),
        'f:Models/User.cs:User.Hidden': ('void Hidden()', None, 'private', 17),
        'f:Models/User.cs:User.Both': ('protected internal void Both()', None, 'protected', 18),
        'f:Models/User.cs:User.Count': ('internal int Count()', None, 'internal', 19),
        'c:Models/User.cs:Plain': ('class Plain', None, 'internal', 21),
        'f:Models/User.cs:IRepo.Save': ('void Save()', None, 'public', 22),
    }),
    'kotlin': ({'User.kt': """
        package shop

        /**
         * A user.
         */
        @JvmInline
        data class User(val name: String) : Base() {
            /** Greets. */
            override fun greet(x: Int): String {
                return name
            }
            private fun hide() = 1
            internal fun inner() {}
        }

        fun top(a: Int) = a
    """}, {
        'c:User.kt:User': ('data class User(val name: String) : Base()', 'A user.', 'public', 14),
        'f:User.kt:User.greet': ('override fun greet(x: Int): String', 'Greets.', 'public', 11),
        'f:User.kt:User.hide': ('private fun hide()', None, 'private', 12),
        'f:User.kt:User.inner': ('internal fun inner()', None, 'internal', 13),
        'f:User.kt:top': ('fun top(a: Int)', None, 'public', 16),
    }),
    'swift': ({'User.swift': """
        import Foundation

        /// A user.
        /// More.
        public class User: Base {
            /// Greets.
            @discardableResult
            public func greet(name: String) -> String {
                return name
            }
            private func hide() {}
            func plain() {}
            fileprivate func fp() {}
        }

        protocol Repo {
            func save()
        }
    """}, {
        'c:User.swift:User': ('public class User: Base', 'A user. More.', 'public', 14),
        'f:User.swift:User.greet': ('public func greet(name: String) -> String', 'Greets.', 'public', 10),
        'f:User.swift:User.hide': ('private func hide()', None, 'private', 11),
        'f:User.swift:User.plain': ('func plain()', None, 'internal', 12),
        'f:User.swift:User.fp': ('fileprivate func fp()', None, 'private', 13),
        'f:User.swift:Repo.save': ('func save()', None, 'internal', 17),
    }),
    'php': ({'src/User.php': """
        <?php
        namespace App\\Models;

        use Illuminate\\Support\\Str;
        use App\\Models\\Base;

        /**
         * A user.
         *
         * @property string $name
         */
        final class User extends Base
        {
            /**
             * Greets the user.
             * @param string $x
             */
            public function greet(string $x): string
            {
                return $x;
            }
            private function hide() {}
            protected static function prot() {}
            function plain() {}
        }

        /** Top helper. */
        function helper($a) { return $a; }
    """, 'src/Base.php': '<?php\nnamespace App\\Models;\nclass Base {}\n'}, {
        'c:src/User.php:User': ('final class User extends Base', 'A user.', 'public', 25),
        'f:src/User.php:User.greet': ('public function greet(string $x): string', 'Greets the user.', 'public', 21),
        'f:src/User.php:User.hide': ('private function hide()', None, 'private', 22),
        'f:src/User.php:User.prot': ('protected static function prot()', None, 'protected', 23),
        'f:src/User.php:User.plain': ('function plain()', None, 'public', 24),
        'f:src/User.php:helper': ('function helper($a)', 'Top helper.', 'public', 28),
    }),
    'ruby': ({'lib/user.rb': """
        # frozen_string_literal: true

        require 'json'

        # A user.
        # Second line.
        class User < Base
          # Greets.
          def greet(name)
            name
          end

          def self.build
          end

          private

          # Hidden.
          def hide
          end

          protected def prot
          end

          public

          def again; end
        end
    """}, {
        'c:lib/user.rb:User': ('class User < Base', 'A user. Second line.', 'public', 28),
        'f:lib/user.rb:User.greet': ('def greet(name)', 'Greets.', 'public', 11),
        'f:lib/user.rb:User.build': ('def self.build', None, 'public', 14),
        'f:lib/user.rb:User.hide': ('def hide', 'Hidden.', 'private', 20),
        'f:lib/user.rb:User.prot': ('def prot', None, 'protected', 23),
        'f:lib/user.rb:User.again': ('def again', None, 'public', 27),
    }),
    'cpp': ({'src/widget.cpp': """
        #include <vector>
        #include <fmt/format.h>

        /// A widget.
        class Widget : public Base {
        public:
            int size() { return 1; }
        private:
            void hide() {}
        };

        // Adds numbers.
        static int add(int a, int b) {
            return a + b;
        }

        template <typename T>
        class Box { T v; };

        namespace {
        void anon() {}
        }
    """}, {
        'c:src/widget.cpp:Widget': ('class Widget : public Base', 'A widget.', 'public', 10),
        'f:src/widget.cpp:Widget.size': ('int size()', None, 'public', 7),
        'f:src/widget.cpp:Widget.hide': ('void hide()', None, 'private', 9),
        'f:src/widget.cpp:add': ('static int add(int a, int b)', 'Adds numbers.', 'private', 15),
        'c:src/widget.cpp:Box': ('template <typename T> class Box', None, 'public', 18),
        'f:src/widget.cpp:anon': ('void anon()', None, 'private', 21),
    }),
    'elixir': ({'lib/user.ex': """
        defmodule Shop.User do
          @moduledoc \"\"\"
          A user module.

          More details.
          \"\"\"
          import Ecto.Query

          @doc \"\"\"
          Creates a user.
          \"\"\"
          @spec create(map) :: {:ok, map}
          def create(attrs) do
            attrs
          end

          @doc "Short one."
          def put(x), do: x

          @doc false
          def quiet(x), do: x

          defp hide(x), do: x
        end
    """}, {
        'c:lib/user.ex:Shop.User': ('defmodule Shop.User', 'A user module.', 'public', 24),
        'f:lib/user.ex:Shop.User.create': ('def create(attrs)', 'Creates a user.', 'public', 15),
        'f:lib/user.ex:Shop.User.put': ('def put(x)', 'Short one.', 'public', 18),
        'f:lib/user.ex:Shop.User.quiet': ('def quiet(x)', None, 'public', 21),
        'f:lib/user.ex:Shop.User.hide': ('defp hide(x)', None, 'private', 23),
    }),
    'haskell': ({'src/Shop.hs': """
        -- | Shop module.
        module Shop (greet) where

        -- | Greets.
        greet :: String -> String
        greet u = u
    """}, {
        'f:src/Shop.hs:greet': ('greet :: String -> String', 'Greets.', 'public', 6),
    }),
    'julia': ({'src/Shop.jl': '''
        """
            greet(x)

        Greets x.
        """
        function greet(x::Int)
            x
        end

        _hidden(a) = a
    '''}, {
        'f:src/Shop.jl:greet': ('function greet(x::Int)', 'Greets x.', 'public', 8),
        'f:src/Shop.jl:_hidden': ('_hidden(a)', None, 'private', 10),
    }),
}


@pytest.mark.parametrize('lang', sorted(META))
def test_symbols_carry_signature_doc_end_and_visibility(tmp_path, lang):
    files, expected = META[lang]
    root = write_repo(tmp_path / lang, files)
    g = lang_nodes(root, sorted(files), False)
    for nid, (sig, doc, vis, end) in expected.items():
        meta = g.nodes[nid]
        assert (meta.get('sig'), meta.get('doc'), meta.get('vis'), meta.get('end')) == (sig, doc, vis, end), nid


def test_module_nodes_get_line_count_and_file_doc(tmp_path):
    files = {**META['go'][0], **META['rust'][0]}
    root = write_repo(tmp_path / 'mods', files)
    g = lang_nodes(root, sorted(files), False)
    assert g.nodes['m:shop.go']['doc'] == 'Package shop sells things.'
    assert g.nodes['m:shop.go']['end'] == 24
    assert g.nodes['m:src/lib.rs']['doc'] == 'Crate docs here.'
    assert g.nodes['m:util/util.go']['end'] == 1


def test_signatures_are_capped_and_collapsed(tmp_path):
    params = ', '.join(f'arg{i} int' for i in range(80))
    root = write_repo(tmp_path / 'long', {'long.go': f'package long\n\n// Big\n//   spaced   doc.\nfunc Big({params}) {{}}\n'})
    meta = lang_nodes(root, ['long.go'], False).nodes['f:long.go:Big']
    assert len(meta['sig']) <= 300 and meta['sig'].startswith('func Big(arg0 int, arg1 int')
    assert meta['doc'] == 'Big spaced doc.'


def externals(lang):
    files = META[lang][0]
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        root = write_repo(Path(tmp) / lang, files)
        return sorted(lang_nodes(root, sorted(files), False).externals)


def test_unresolved_imports_are_recorded_as_externals():
    assert externals('go') == [('m:shop.go', 'fmt', 'go'), ('m:shop.go', 'github.com/gin-gonic/gin', 'go')]
    assert externals('rust') == [('m:src/lib.rs', 'serde::Deserialize', 'rust')]
    assert externals('java') == [('m:src/com/shop/User.java', 'org.junit', 'java'),
                                 ('m:src/com/shop/User.java', 'org.springframework.web.bind.annotation.GetMapping', 'java')]
    assert externals('php') == [('m:src/User.php', 'Illuminate\\Support\\Str', 'php')]
    assert externals('cpp') == [('m:src/widget.cpp', 'fmt/format.h', 'cpp')]
    assert externals('ruby') == [('m:lib/user.rb', 'json', 'ruby')]
    assert externals('csharp') == [('m:Models/User.cs', 'System.Linq', 'csharp')]
    assert externals('elixir') == [('m:lib/user.ex', 'Ecto.Query', 'elixir')]
    assert externals('swift') == []


def test_enriched_meta_reaches_the_output_graph(tmp_path):
    graph = analyze(str(write_repo(tmp_path / 'out', META['go'][0])))
    node = next(n for n in graph['nodes'] if n['name'] == 'Server.Handle')
    assert node['sig'].startswith('func (s *Server) Handle') and node['vis'] == 'public' and node['end'] == 22
    assert node['doc'] == 'Handle handles a request.'


GO_TYPED = {
    'go.mod': 'module "example.com/web"\n',
    'context.go': """
        package web

        import (
          "net/http"
          "os"
        )

        type HandlersChain []func(*Context)

        func (c HandlersChain) Last() func(*Context) { return c[len(c)-1] }

        type Context struct {
          handlers HandlersChain
          Request  *http.Request
          engine   *Engine
        }

        func (c *Context) Header(key string) {}
        func (c *Context) Set(key string) {}
        func (c *Context) Query(key string) string { return key }
        func (c *Context) Open() {}

        func (c *Context) Next() {
          c.Set("x")
          c.handlers.Last()
          c.engine.Use()
        }

        func (c *Context) Load() {
          c.Request.URL.Query()
          os.Open("x")
        }
    """,
    'gin.go': """
        package web

        type RouterGroup struct{}

        func (g *RouterGroup) Use() {}
        func (g *RouterGroup) GET(path string, fn func(*Context)) {}

        type Engine struct {
          RouterGroup
        }

        func New() *Engine { return &Engine{} }

        func stack(n int) []byte { return nil }

        func Run() {
          e := New()
          e.GET("/", func(c *Context) { c.Header("a") })
          other := &Engine{}
          other.Use()
          made := new(Context)
          made.Next()
          stack := stack(3)
          _ = stack
          for _, c := range []*Context{} {
            c.Set("y")
          }
        }
    """,
    'auth.go': """
        package web

        import "example.com/web/internal/bytesconv"

        type Render interface{ Render() error }

        type JSON struct{}

        func (JSON) Render() error { return nil }

        var _ Render = (*JSON)(nil)

        func Auth(c *Context) {
          c.Header(string(bytesconv.StringToBytes("realm")))
          JSON{}.Render()
        }
    """,
    'internal/bytesconv/bytesconv_1.19.go': """
        //go:build !go1.20

        package bytesconv

        func StringToBytes(s string) []byte { return nil }
    """,
    'internal/bytesconv/bytesconv_1.20.go': """
        //go:build go1.20

        package bytesconv

        func StringToBytes(s string) []byte { return nil }
    """,
    'binding/binding.go': """
        //go:build !nomsgpack

        package binding

        func validate(obj any) error { return nil }
    """,
    'binding/binding_nomsgpack.go': """
        //go:build nomsgpack

        package binding

        func validate(obj any) error { return nil }
    """,
    'binding/form.go': """
        package binding

        import (
          "mime/multipart"
          "net/http"
        )

        type formBinding struct{}

        func (formBinding) Name() string { return "form" }

        func (formBinding) Bind(req *http.Request, obj any) error {
          return validate(obj)
        }

        func check(fh *multipart.FileHeader) {
          fh.Open()
        }
    """,
}


def test_go_typed_receivers_resolve_methods(tmp_path):
    root = write_repo(tmp_path / 'go', GO_TYPED)
    g = lang_nodes(root, sorted(f for f in GO_TYPED if f.endswith('.go')), False)
    calls = {(a, b) for a, b, kind in g.edges if kind == 'call'}
    expected = {
        ('f:auth.go:Auth', 'f:context.go:Context.Header'),
        ('f:context.go:Context.Next', 'f:context.go:Context.Set'),
        ('f:context.go:Context.Next', 'f:context.go:HandlersChain.Last'),
        ('f:context.go:Context.Next', 'f:gin.go:RouterGroup.Use'),
        ('f:gin.go:Run', 'f:gin.go:New'),
        ('f:gin.go:Run', 'f:gin.go:RouterGroup.GET'),
        ('f:gin.go:Run', 'f:context.go:Context.Header'),
        ('f:gin.go:Run', 'f:gin.go:RouterGroup.Use'),
        ('f:gin.go:Run', 'f:context.go:Context.Next'),
        ('f:gin.go:Run', 'f:context.go:Context.Set'),
        ('f:gin.go:Run', 'f:gin.go:stack'),
        ('f:auth.go:Auth', 'f:auth.go:JSON.Render'),
    }
    assert expected <= calls


def test_go_unnamed_receivers_and_build_tagged_twins(tmp_path):
    root = write_repo(tmp_path / 'go', GO_TYPED)
    g = lang_nodes(root, sorted(f for f in GO_TYPED if f.endswith('.go')), False)
    calls = {(a, b) for a, b, kind in g.edges if kind == 'call'}
    assert g.nodes['f:binding/form.go:formBinding.Name']['kind'] == 'method'
    assert g.nodes['f:binding/form.go:formBinding.Bind']['kind'] == 'method'
    assert 'f:binding/form.go:Bind' not in g.nodes and 'f:binding/form.go:Name' not in g.nodes
    assert ('f:binding/form.go:formBinding.Bind', 'f:binding/binding.go:validate') in calls
    assert ('f:auth.go:Auth', 'f:internal/bytesconv/bytesconv_1.20.go:StringToBytes') in calls
    assert not any(b.startswith(('f:binding/binding_nomsgpack.go', 'f:internal/bytesconv/bytesconv_1.19.go')) for _, b in calls)


def test_go_conversions_and_foreign_receivers_are_not_calls(tmp_path):
    root = write_repo(tmp_path / 'go', GO_TYPED)
    g = lang_nodes(root, sorted(f for f in GO_TYPED if f.endswith('.go')), False)
    calls = {(a, b) for a, b, kind in g.edges if kind == 'call'}
    assert ('m:auth.go', 'c:auth.go:JSON', 'ref') in g.edges
    assert not any(b == 'c:auth.go:JSON' for _, b in calls)
    assert not any(b in ('f:context.go:Context.Query', 'f:context.go:Context.Open') for _, b in calls)


def test_go_build_constraints():
    from cortex_graph.langs import go_constraint, go_enabled
    assert go_constraint('go1.20 && !nomsgpack') and go_constraint('linux || windows')
    assert not go_constraint('windows') and not go_constraint('appengine')
    assert go_constraint('!(appengine || go_json)') and go_constraint('')
    assert go_enabled('a/b_test.go', b'//go:build !go1.20\n\npackage a\n') == ('!go1.20', False)
    assert go_enabled('a/file_windows.go', b'package a\n') == ('', False)
    assert go_enabled('a/file_linux_amd64.go', b'package a\n') == ('', True)


RUBY_CALLS = {
    'lib/shop/cart.rb': """
        module Shop
          class Cart
            attr_accessor :total
            attr_reader :items

            def initialize
              @items = []
              self.total = 0
            end

            def add(item, qty = 1)
              price = qty
              refresh
              price
              item.weigh
              @store.persist(item)
              Shop::Receipt.new(self)
            end

            def refresh
              [1].each { |entry| entry }
            end
          end
        end
    """,
    'lib/shop/receipt.rb': """
        module Shop
          class Receipt
            def initialize(cart)
              @cart = cart
            end

            def persist(item)
            end
          end
        end
    """,
}


def test_ruby_bare_calls_accessors_and_constructors(tmp_path):
    graph = analyze(str(write_repo(tmp_path / 'rb', RUBY_CALLS)))
    found = triples(graph)
    assert {('Cart.total', 'method'), ('Cart.total=', 'method'), ('Cart.items', 'method')} <= kinds(graph)
    assert {('Cart.add', 'call', 'Cart.refresh'), ('Cart.add', 'call', 'Receipt'),
            ('Cart.initialize', 'call', 'Cart.total=')} <= found
    assert ('Cart.add', 'call', 'Cart.price') not in found
    assert ('Cart.add', 'call', 'Receipt.persist') not in found
    assert not any(a == 'Cart.refresh' and k == 'call' for a, k, _ in found)


def test_go_package_without_resolved_uses_keeps_its_representative(tmp_path):
    files = {
        'go.mod': 'module example.com/app\n',
        'util/util.go': 'package util\n\nfunc Helper() {}\n',
        'util/extra.go': 'package util\n\nfunc Extra() {}\n',
        'main.go': 'package main\n\nimport "example.com/app/util"\n\nfunc main() {\n\tutil.Generated()\n}\n',
    }
    found = imports(analyze(str(write_repo(tmp_path / 'gorep', files))))
    assert ('main.go', 'util/util.go') in found
    assert ('main.go', 'util/extra.go') not in found


def test_go_method_values_and_field_reads_link_their_files(tmp_path):
    files = {
        'go.mod': 'module example.com/app\n',
        'model/user.go': 'package model\n\ntype User struct {\n\tID   int\n\tName string\n}\n',
        'model/store.go': 'package model\n\ntype Store struct{}\n\nfunc (s *Store) Save(u *User) {}\n',
        'api/api.go': ('package api\n\nimport "example.com/app/model"\n\n'
                       'func Register(s *model.Store, u *model.User, mux map[string]func(*model.User)) int {\n'
                       '\tmux["save"] = s.Save\n\treturn u.ID\n}\n'),
    }
    graph = analyze(str(write_repo(tmp_path / 'gosel', files)))
    found = triples(graph)
    assert ('Register', 'ref', 'Store.Save') in found
    assert ('Register', 'ref', 'User') in found
    assert ('Register', 'call', 'Store.Save') not in found
