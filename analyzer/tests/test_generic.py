from conftest import write_repo
from cortex_graph import generic
from cortex_graph.common import Graph, Issues, digest, read_source


def build(tmp_path, files):
    root = write_repo(tmp_path / 'repo', files)
    rels = sorted(rel for rel in files if generic.kind_of(rel))
    g = Graph()
    generic.analyze_generic(root, rels, g, Issues(), read_source, digest)
    return g


def edges(g, kind=None):
    return {(a, b, k) for (a, b, k) in g.edges if kind is None or k == kind}


ERLANG = {
    'src/shop_handler.erl': """
        -module(shop_handler).
        -callback handle(term()) -> ok.
        -export([run/1]).

        run(X) ->
            ok.
    """,
    'include/shop.hrl': """
        -record(order, {id, total = 1.5}).
        -define(TAX, 0.19).
    """,
    'src/shop_cart.erl': """
        %% cart_total(X) -> not_a_def.
        -module(shop_cart).
        -behaviour(shop_handler).
        -include("../include/shop.hrl").
        -include_lib("kernel/include/file.hrl").
        -spec add(list(), term()) -> list().
        -export([add/2, total/1]).

        add(Items, Item) when is_list(Items) ->
            Mapper = fun normalize/1,
            [Mapper(Item) | Items];
        add(_, Item) ->
            shop_handler:run(Item),
            "total(1) ->",
            [Item].

        total(Items) ->
            lists:sum(Items).

        normalize(Item) ->
            ?MODULE:total([Item]),
            handler_for(shop_handler).

        handler_for(M) -> M.
    """,
}


def test_erlang_definitions_merge_clauses_and_ignore_fun_references(tmp_path):
    g = build(tmp_path, ERLANG)
    cart = sorted(n for n, m in g.nodes.items() if m['file'] == 'src/shop_cart.erl' and m['kind'] == 'function')
    assert cart == ['f:src/shop_cart.erl:add', 'f:src/shop_cart.erl:handler_for',
                    'f:src/shop_cart.erl:normalize', 'f:src/shop_cart.erl:total']
    assert g.edges[('m:src/shop_cart.erl', 'f:src/shop_cart.erl:add', 'contains')] == 1
    assert g.nodes['f:src/shop_cart.erl:add']['line'] == 9


def test_erlang_behaviour_include_and_calls(tmp_path):
    g = build(tmp_path, ERLANG)
    assert {
        ('m:src/shop_cart.erl', 'm:src/shop_handler.erl', 'inherits'),
        ('m:src/shop_cart.erl', 'm:include/shop.hrl', 'import'),
        ('f:src/shop_cart.erl:add', 'f:src/shop_handler.erl:run', 'call'),
        ('f:src/shop_cart.erl:add', 'f:src/shop_cart.erl:normalize', 'call'),
        ('f:src/shop_cart.erl:normalize', 'f:src/shop_cart.erl:total', 'call'),
        ('f:src/shop_cart.erl:normalize', 'f:src/shop_cart.erl:handler_for', 'call'),
        ('f:src/shop_cart.erl:normalize', 'm:src/shop_handler.erl', 'ref'),
    } <= edges(g)
    assert ('f:src/shop_cart.erl:add', 'f:src/shop_cart.erl:total', 'call') not in edges(g)


CLOJURE = {
    'src/shop/core.clj': """
        (ns shop.core
          "Entry point. Uses shop.util/never-called in a docstring."
          (:require [clojure.string :as str]
                    [shop.price-rules :as rules]
                    [shop.util :refer [slug]]
                    shop.db)
          (:import (java.util Date)))

        (defn total [items]
          (rules/apply-discount (reduce + items)))

        (defn label [x]
          (str/upper-case (slug x)))

        (defn save! [x]
          (shop.db/insert x))
    """,
    'src/shop/price_rules.clj': """
        (ns shop.price-rules)

        (defn apply-discount [n] (* n 0.9))
    """,
    'src/shop/util.clj': """
        (ns shop.util)

        (defn slug [s] s)

        (defn never-called [] nil)
    """,
    'src/shop/db.clj': """
        (ns shop.db)

        (defprotocol Store
          (insert [this x]))

        (defn insert-all [xs] (map insert xs))
    """,
}


def test_clojure_multiline_ns_requires_and_alias_calls(tmp_path):
    g = build(tmp_path, CLOJURE)
    assert {
        ('m:src/shop/core.clj', 'm:src/shop/price_rules.clj', 'import'),
        ('m:src/shop/core.clj', 'm:src/shop/util.clj', 'import'),
        ('m:src/shop/core.clj', 'm:src/shop/db.clj', 'import'),
        ('f:src/shop/core.clj:total', 'f:src/shop/price_rules.clj:apply-discount', 'call'),
        ('f:src/shop/core.clj:label', 'f:src/shop/util.clj:slug', 'call'),
        ('f:src/shop/core.clj:save!', 'f:src/shop/db.clj:Store.insert', 'call'),
    } <= edges(g)
    assert 'c:src/shop/db.clj:Store' in g.nodes
    assert not any(b == 'f:src/shop/util.clj:never-called' for _, b, _ in edges(g, 'call'))


def test_kubernetes_names_with_colons_and_quotes(tmp_path):
    g = build(tmp_path, {
        'deploy/rbac.yaml': """
            apiVersion: rbac.authorization.k8s.io/v1
            kind: ClusterRole
            metadata:
              labels:
                name: not-this-one
              name: system:kube-apiserver-to-kubelet
            ---
            kind: ClusterRoleBinding
            metadata:
              name: "system:kube-apiserver"
            ---
            kind: Service
            metadata:
              name: {{ include "chart.fullname" . }}
        """,
    })
    classes = sorted(m['name'] for m in g.nodes.values() if m['kind'] == 'class')
    assert classes == ['ClusterRole/system:kube-apiserver-to-kubelet', 'ClusterRoleBinding/system:kube-apiserver']


def test_data_dirs_and_translation_bundles_are_skipped():
    assert generic.kind_of('src/main/resources/application.properties') == 'config'
    assert generic.kind_of('src/main/resources/application-mysql.properties') == 'config'
    assert generic.kind_of('src/main/resources/messages/messages.properties') is None
    assert generic.kind_of('src/main/resources/messages/messages_es.properties') is None
    assert generic.kind_of('src/main/resources/i18n/labels_pt_BR.properties') is None
    assert generic.kind_of('config/labels_pt_BR.properties') is None
    assert generic.kind_of('config/app.config.json') == 'config'
    assert generic.kind_of('test/fixtures/app.config.json') is None
    assert generic.kind_of('locales/package.json') is None
    assert generic.kind_of('i18n/settings.properties') is None
    assert generic.kind_of('testdata/protoexample/test.proto') is None
    assert generic.kind_of('lang/erl/src/x.erl') == 'code'


def test_generated_documentation_html_is_skipped(tmp_path):
    g = build(tmp_path, {
        'docs/api/index.html': """
            <!DOCTYPE html>
            <html><head><meta name="generator" content="Doxygen 1.9.8"></head><body></body></html>
        """,
        'docs/swift/Classes.html': """
            <html><head><link rel="stylesheet" href="css/jazzy.css" /></head></html>
        """,
        'docs/java/index.html': """
            <!-- Generated by javadoc (17) -->
            <html></html>
        """,
        'web/templates/home.html': """
            <html><head><meta name="viewport" content="width=device-width"></head></html>
        """,
    })
    assert sorted(n for n in g.nodes if n.startswith('m:')) == ['m:web/templates/home.html']


def test_package_scripts_only_for_real_packages(tmp_path):
    scripts = '{ "name": "x", "scripts": { "dev": "next dev", "build": "tsc -p ${DIR}" }, "x": {} }'
    g = build(tmp_path, {
        'package.json': scripts,
        'packages/ui/package.json': scripts,
        'packages/ui/src/index.ts': 'export const a = 1;',
        'packages/meta/package.json': '{ "name": "m", "workspaces": ["a"], "scripts": { "lint": "eslint" } }',
        'tools/empty/package.json': scripts,
        'tools/empty/next.config.js': 'module.exports = {};',
        'examples/blog/package.json': scripts,
        'examples/blog/src/page.ts': 'export const p = 1;',
        'test/e2e/app/package.json': scripts,
        'test/e2e/app/index.js': 'module.exports = 1;',
        'packages/codemod/__testfixtures__/a/package.json': scripts,
    })
    found = sorted(n for n, m in g.nodes.items() if m['kind'] == 'function')
    assert found == [
        'f:package.json:build', 'f:package.json:dev', 'f:packages/meta/package.json:lint',
        'f:packages/ui/package.json:build', 'f:packages/ui/package.json:dev',
    ]
    assert 'm:examples/blog/package.json' in g.nodes


def test_compose_ci_sql_and_proto_entities(tmp_path):
    g = build(tmp_path, {
        'docker-compose.yml': """
            services:
              api:
                image: api
                depends_on:
                  - db
              db:
                image: postgres
        """,
        '.github/workflows/ci.yml': """
            on: push
            jobs:
              test:
                runs-on: ubuntu-latest
              deploy:
                needs: test
        """,
        'db/schema.sql': """
            CREATE TABLE users (id int primary key);
            CREATE TABLE orders (
              id int primary key,
              user_id int REFERENCES users(id)
            );
        """,
        'api/shop.proto': """
            syntax = "proto3";
            message Order { string id = 1; }
            service Shop {
              rpc Place (Order) returns (Order);
            }
        """,
    })
    assert {'c:docker-compose.yml:api', 'c:docker-compose.yml:db', 'f:.github/workflows/ci.yml:test',
            'f:.github/workflows/ci.yml:deploy', 'c:api/shop.proto:Order', 'c:api/shop.proto:Shop',
            'f:api/shop.proto:Shop.Place'} <= set(g.nodes)
    assert ('c:db/schema.sql:orders', 'c:db/schema.sql:users', 'ref') in edges(g)


def test_generic_analysis_is_deterministic(tmp_path):
    files = {**ERLANG, **CLOJURE}
    first = build(tmp_path / 'a', files)
    second = build(tmp_path / 'b', files)
    assert list(first.nodes) == list(second.nodes)
    assert list(first.edges.items()) == list(second.edges.items())
