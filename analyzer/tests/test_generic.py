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


def node(g, nid):
    assert nid in g.nodes, sorted(n for n in g.nodes if nid.split(':')[1] in n)
    return g.nodes[nid]


DBT = {
    'dbt_project.yml': """
        name: shop
        version: '1.0'
    """,
    'models/staging/stg_orders.sql': """
        {{ config(materialized='view') }}
        select * from {{ source('raw', 'orders') }}
        where {{ not_deleted('o') }}
    """,
    'models/marts/orders.sql': """
        select o.*, {{ cents_to_dollars('amount') }} as dollars
        from {{ ref('stg_orders') }} o
        join {{ ref('shop', 'customers') }} c using (id)
    """,
    'models/marts/customers.sql': "select 1 as id",
    'models/schema.yml': """
        version: 2
        sources:
          - name: raw
            tables:
              - name: orders
                description: Raw orders.
        models:
          - name: orders
            description: One row per order.
            columns:
              - name: id
                description: Primary key.
                tests:
                  - relationships:
                      to: ref('customers')
                      field: id
    """,
    'macros/money.sql': """
        {# Converts cents to dollars. #}
        {% macro cents_to_dollars(col, scale=2) %}
          ({{ col }} / 100)::numeric(16, {{ scale }})
        {% endmacro %}

        {% macro not_deleted(alias) -%}
          {{ alias }}.deleted_at is null and {{ cents_to_dollars('x') }} > 0
        {%- endmacro %}
    """,
}


def test_dbt_refs_sources_macros_and_schema(tmp_path):
    g = build(tmp_path, DBT)
    macro = node(g, 'f:macros/money.sql:cents_to_dollars')
    assert macro['sig'] == 'macro cents_to_dollars(col, scale=2)'
    assert macro['doc'] == 'Converts cents to dollars.'
    assert (macro['line'], macro['end']) == (2, 4)
    assert node(g, 'm:models/marts/orders.sql')['end'] == 3
    assert node(g, 'm:models/schema.yml')['end'] == 16
    assert node(g, 'f:models/schema.yml:orders.id')['doc'] == 'Primary key.'
    assert {
        ('m:models/marts/orders.sql', 'm:models/staging/stg_orders.sql', 'import'),
        ('m:models/marts/orders.sql', 'm:models/marts/customers.sql', 'import'),
        ('m:models/marts/orders.sql', 'f:macros/money.sql:cents_to_dollars', 'call'),
        ('m:models/staging/stg_orders.sql', 'c:models/schema.yml:raw.orders', 'ref'),
        ('m:models/staging/stg_orders.sql', 'f:macros/money.sql:not_deleted', 'call'),
        ('f:macros/money.sql:not_deleted', 'f:macros/money.sql:cents_to_dollars', 'call'),
        ('c:models/schema.yml:orders', 'm:models/marts/orders.sql', 'ref'),
        ('f:models/schema.yml:orders.id', 'm:models/marts/customers.sql', 'ref'),
        ('c:models/schema.yml:orders', 'f:models/schema.yml:orders.id', 'contains'),
    } <= edges(g)
    assert not any(b.startswith('f:') and 'config' in b for _, b, _ in edges(g, 'call'))


ANSIBLE = {
    'site.yml': """
        # Web tier.
        - name: Configure web
          hosts: web
          become: true
          vars_files:
            - vars/common.yml
          roles:
            - common
            - role: nginx
              tags: [web]
          tasks:
          - name: Extra setup
            import_tasks: tasks/extra.yml
          handlers:
            - name: reload all
              command: /bin/true
        - import_playbook: db.yml
    """,
    'db.yml': """
        - hosts: db
          tasks:
            - include_role:
                name: common
    """,
    'vars/common.yml': 'x: 1',
    'tasks/extra.yml': """
        - name: Touch marker
          file:
            path: /tmp/m
            state: touch
    """,
    'roles/common/tasks/main.yml': """
        - name: Install packages
          apt:
            name: [git, curl]
          notify: restart ntp
        - block:
            - name: Configure ntp
              template: src=ntp.conf.j2 dest=/etc/ntp.conf
              notify:
                - restart ntp
                - reload all
        - include_tasks: users.yml
    """,
    'roles/common/tasks/users.yml': """
        - name: Create users
          user: name=deploy
    """,
    'roles/common/handlers/main.yml': """
        - name: restart ntp
          service: name=ntp state=restarted
    """,
    'roles/common/templates/ntp.conf.j2': 'server {{ ntp_server }}',
    'roles/nginx/tasks/main.yml': """
        - name: Install nginx
          apt: name=nginx
    """,
    'roles/nginx/meta/main.yml': """
        dependencies:
          - role: common
    """,
}


def test_ansible_plays_roles_tasks_and_handlers(tmp_path):
    g = build(tmp_path, ANSIBLE)
    play = node(g, 'c:site.yml:Configure web')
    assert (play['line'], play['end'], play['sig'], play['doc']) == (2, 16, 'hosts: web', 'Web tier.')
    assert node(g, 'f:roles/common/tasks/main.yml:Configure ntp')['sig'] == 'template: src=ntp.conf.j2 dest=/etc/ntp.conf'
    assert 'f:roles/common/tasks/main.yml:include_tasks users.yml' in g.nodes
    assert {
        ('c:site.yml:Configure web', 'm:roles/common/tasks/main.yml', 'import'),
        ('c:site.yml:Configure web', 'm:roles/nginx/tasks/main.yml', 'import'),
        ('c:site.yml:Configure web', 'm:vars/common.yml', 'ref'),
        ('c:site.yml:Configure web', 'f:site.yml:Extra setup', 'contains'),
        ('f:site.yml:Extra setup', 'm:tasks/extra.yml', 'import'),
        ('m:site.yml', 'm:db.yml', 'import'),
        ('f:db.yml:include_role common', 'm:roles/common/tasks/main.yml', 'import'),
        ('f:roles/common/tasks/main.yml:Install packages', 'f:roles/common/handlers/main.yml:restart ntp', 'call'),
        ('f:roles/common/tasks/main.yml:Configure ntp', 'f:roles/common/handlers/main.yml:restart ntp', 'call'),
        ('f:roles/common/tasks/main.yml:Configure ntp', 'f:site.yml:reload all', 'call'),
        ('f:roles/common/tasks/main.yml:Configure ntp', 'm:roles/common/templates/ntp.conf.j2', 'ref'),
        ('f:roles/common/tasks/main.yml:include_tasks users.yml', 'm:roles/common/tasks/users.yml', 'import'),
        ('m:roles/nginx/meta/main.yml', 'm:roles/common/tasks/main.yml', 'import'),
    } <= edges(g)


HELM = {
    'charts/shop/Chart.yaml': """
        apiVersion: v2
        name: shop
        description: Shop chart.
        version: 1.2.0
        dependencies:
          - name: common
            repository: file://../common
          - name: redis
            repository: https://charts.example.com
    """,
    'charts/shop/values.yaml': """
        image:
          tag: latest
    """,
    'charts/shop/templates/_helpers.tpl': """
        {{/* Full name of the release. */}}
        {{- define "shop.fullname" -}}
        {{- if .Values.fullnameOverride }}{{ .Values.fullnameOverride }}{{- else }}{{ .Release.Name }}{{- end }}
        {{- end }}

        {{- define "shop.labels" -}}
        app: {{ include "shop.fullname" . }}
        {{ include "common.labels" . }}
        {{- end }}
    """,
    'charts/shop/templates/deployment.yaml': """
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: {{ include "shop.fullname" . }}
          labels: {{- include "shop.labels" . | nindent 4 }}
        spec:
          template:
            spec:
              containers:
                - image: "shop:{{ .Values.image.tag }}"
    """,
    'charts/common/Chart.yaml': """
        name: common
        type: library
    """,
    'charts/common/templates/_labels.tpl': """
        {{- define "common.labels" -}}
        managed-by: helm
        {{- end -}}
    """,
}


def test_helm_charts_defines_includes_and_values(tmp_path):
    g = build(tmp_path, HELM)
    define = node(g, 'f:charts/shop/templates/_helpers.tpl:shop.fullname')
    assert (define['line'], define['end'], define['doc']) == (2, 4, 'Full name of the release.')
    assert node(g, 'c:charts/shop/Chart.yaml:shop')['doc'] == 'Shop chart.'
    assert {
        ('m:charts/shop/templates/deployment.yaml', 'f:charts/shop/templates/_helpers.tpl:shop.fullname', 'call'),
        ('m:charts/shop/templates/deployment.yaml', 'f:charts/shop/templates/_helpers.tpl:shop.labels', 'call'),
        ('f:charts/shop/templates/_helpers.tpl:shop.labels', 'f:charts/shop/templates/_helpers.tpl:shop.fullname', 'call'),
        ('f:charts/shop/templates/_helpers.tpl:shop.labels', 'f:charts/common/templates/_labels.tpl:common.labels', 'call'),
        ('m:charts/shop/templates/deployment.yaml', 'm:charts/shop/values.yaml', 'ref'),
        ('f:charts/shop/templates/_helpers.tpl:shop.fullname', 'm:charts/shop/values.yaml', 'ref'),
        ('c:charts/shop/Chart.yaml:shop', 'm:charts/common/Chart.yaml', 'import'),
    } <= edges(g)
    assert not any(a == 'f:charts/shop/templates/_helpers.tpl:shop.labels' and k == 'ref' for a, _, k in edges(g))


SAM = {
    'template.yaml': """
        AWSTemplateFormatVersion: '2010-09-09'
        Transform: AWS::Serverless-2016-10-31
        Globals:
          Function:
            Runtime: python3.12
        Parameters:
          Stage:
            Type: String
            Description: Deployment stage.
        Resources:
          OrdersTable:
            Type: AWS::DynamoDB::Table
            Properties:
              TableName: !Sub 'orders-${Stage}'
          OrdersFunction:
            Type: AWS::Serverless::Function
            DependsOn: [OrdersTable]
            Properties:
              CodeUri: orders/
              Handler: app.handler
              Environment:
                Variables:
                  TABLE: !Ref OrdersTable
                  ARN:
                    Fn::GetAtt: [OrdersTable, Arn]
              Events:
                GetOrder:
                  Type: Api
                  Properties:
                    Path: /orders/{id}
                    Method: get
        Outputs:
          Api:
            Value: !GetAtt OrdersFunction.Arn
    """,
    'orders/app.py': 'def handler(event, context):\n    return event\n',
}


def test_cloudformation_sam_resources_refs_and_handlers(tmp_path):
    g2 = build(tmp_path, SAM)
    assert 'c:template.yaml:AWS::DynamoDB::Table/OrdersTable' in g2.nodes
    fn = 'c:template.yaml:AWS::Serverless::Function/OrdersFunction'
    table = 'c:template.yaml:AWS::DynamoDB::Table/OrdersTable'
    assert node(g2, 'c:template.yaml:Parameter/Stage')['doc'] == 'Deployment stage.'
    assert node(g2, 'e:template.yaml:GET /orders/:id')['route'] == 'GET /orders/:id'
    assert {
        (fn, table, 'ref'), (table, 'c:template.yaml:Parameter/Stage', 'ref'),
        ('c:template.yaml:Output/Api', fn, 'ref'), ('e:template.yaml:GET /orders/:id', fn, 'handles'),
    } <= edges(g2)


def test_sam_handler_resolves_to_code_function(tmp_path):
    root = write_repo(tmp_path / 'repo', SAM)
    g = Graph()
    g.node('m:orders/app.py', kind='module', name='app.py', file='orders/app.py', line=1)
    g.node('f:orders/app.py:handler', kind='function', name='handler', file='orders/app.py', line=1)
    generic.analyze_generic(root, ['template.yaml'], g, Issues(), read_source, digest)
    fn = 'c:template.yaml:AWS::Serverless::Function/OrdersFunction'
    assert {(fn, 'f:orders/app.py:handler', 'ref'),
            ('e:template.yaml:GET /orders/:id', 'f:orders/app.py:handler', 'handles')} <= edges(g)


SERVERLESS = {
    'serverless.yml': """
        service: users
        provider:
          name: aws
          runtime: nodejs20.x
        functions:
          create:
            handler: src/handlers/users.create
            description: Creates a user.
            events:
              - http:
                  path: users/{id}
                  method: post
              - httpApi: 'GET /users'
        resources:
          Resources:
            UsersBucket:
              Type: AWS::S3::Bucket
    """,
}


def test_serverless_functions_endpoints_and_resources(tmp_path):
    g = build(tmp_path, SERVERLESS)
    fn = node(g, 'f:serverless.yml:create')
    assert (fn['sig'], fn['doc']) == ('create: src/handlers/users.create', 'Creates a user.')
    assert {('e:serverless.yml:POST /users/:id', 'f:serverless.yml:create', 'handles'),
            ('e:serverless.yml:GET /users', 'f:serverless.yml:create', 'handles')} <= edges(g)
    assert 'c:serverless.yml:AWS::S3::Bucket/UsersBucket' in g.nodes


BICEP = {
    'infra/main.bicep': """
        @description('Azure region.')
        param location string = resourceGroup().location
        var prefix = 'shop-${location}'

        resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
          name: '${prefix}sa'
          location: location
          kind: 'StorageV2'
        }

        module network './network.bicep' = {
          name: 'net'
          params: {
            storageId: storage.id
          }
        }

        output storageId string = storage.id
    """,
    'infra/network.bicep': "param storageId string\n",
    'Pulumi.yaml': """
        name: shop-infra
        runtime: nodejs
        description: Infra for the shop.
    """,
    'Pulumi.dev.yaml': """
        config:
          aws:region: us-east-1
    """,
}


def test_bicep_declarations_refs_modules_and_pulumi(tmp_path):
    g = build(tmp_path, BICEP)
    param = node(g, 'f:infra/main.bicep:location')
    assert (param['doc'], param['sig']) == ('Azure region.', 'param location string = resourceGroup().location')
    storage = node(g, 'c:infra/main.bicep:storage')
    assert (storage['line'], storage['end']) == (5, 9)
    assert {
        ('c:infra/main.bicep:storage', 'f:infra/main.bicep:prefix', 'ref'),
        ('c:infra/main.bicep:storage', 'f:infra/main.bicep:location', 'ref'),
        ('f:infra/main.bicep:prefix', 'f:infra/main.bicep:location', 'ref'),
        ('c:infra/main.bicep:network', 'c:infra/main.bicep:storage', 'ref'),
        ('c:infra/main.bicep:network', 'm:infra/network.bicep', 'import'),
        ('f:infra/main.bicep:storageId', 'c:infra/main.bicep:storage', 'ref'),
        ('m:Pulumi.dev.yaml', 'c:Pulumi.yaml:shop-infra', 'ref'),
    } <= edges(g)
    assert ('c:infra/main.bicep:storage', 'f:infra/main.bicep:storageId', 'ref') not in edges(g)


def with_code_nodes(tmp_path, files, code):
    root = write_repo(tmp_path / 'repo', files)
    g = Graph()
    for nid in code:
        rel = nid.split(':')[1]
        g.node(f'm:{rel}', kind='module', name=rel.rsplit('/', 1)[-1], file=rel, line=1)
        if not nid.startswith('m:'):
            g.node(nid, kind='class', name=nid.rsplit(':', 1)[-1], file=rel, line=1)
    rels = sorted(rel for rel in files if generic.kind_of(rel))
    generic.analyze_generic(root, rels, g, Issues(), read_source, digest)
    return g


TEMPLATES = {
    'Views/Orders/Index.cshtml': """
        @model IEnumerable<Shop.Models.Order>
        @inject IOrderService Orders
        @{ Layout = "_Layout"; }
        <partial name="_OrderRow" />
        @await Html.PartialAsync("_Summary")
        @await Component.InvokeAsync("Cart")
    """,
    'Views/Orders/_OrderRow.cshtml': '<tr></tr>',
    'Views/Shared/_Layout.cshtml': '<html>@RenderBody()</html>',
    'Views/Shared/_Summary.cshtml': '<p></p>',
    'Pages/Counter.razor': """
        @page "/counter"
        @inherits ComponentBase
        <OrderCard Order="@current" />
        <PageTitle>Counter</PageTitle>
        @code {
            private int count;
            private List<OrderCard> cards = new();
            private void IncrementCount()
            {
                count++;
            }
        }
    """,
    'Shared/OrderCard.razor': '<div>@Order</div>',
    'resources/views/layouts/app.blade.php': '<html>@yield("content")</html>',
    'resources/views/orders/index.blade.php': """
        @extends('layouts.app')
        @section('content')
          @include('orders.partials.row', ['order' => $o])
          @includeWhen($admin, 'orders.partials.admin', ['x' => 'y'])
          <x-alert type="error" />
          <livewire:order-table />
        @endsection
    """,
    'resources/views/orders/partials/row.blade.php': '<tr></tr>',
    'resources/views/orders/partials/admin.blade.php': '<b></b>',
    'resources/views/components/alert.blade.php': '<div></div>',
    'app/views/users/show.html.erb': """
        <%= render 'form' %>
        <%= render partial: 'shared/avatar', locals: { user: @user } %>
        <%= render 'missing/thing' %>
    """,
    'app/views/users/_form.html.erb': '<form></form>',
    'app/views/shared/_avatar.html.haml': '%img',
    'templates/base.html': """
        {% block body %}{% endblock %}
    """,
    'shop/templates/shop/list.html': """
        {% extends "base.html" %}
        {% import "macros/forms.html" as forms %}
        {% from "macros/forms.html" import label as lbl %}
        {% block body %}{% include "shop/_row.html" %}{{ forms.input('q') }}{{ lbl('x') }}{% endblock %}
    """,
    'shop/templates/shop/_row.html': '<tr></tr>',
    'templates/macros/forms.html': """
        {% macro input(name) %}<input name="{{ name }}">{% endmacro %}
        {% macro label(text) %}<label>{{ text }}</label>{% endmacro %}
    """,
    'templates/page.html.twig': """
        {% extends '@App/layout.html.twig' %}
        {% block body %}{{ include('parts/nav.html.twig') }}{% endblock %}
    """,
    'templates/layout.html.twig': '<html></html>',
    'templates/parts/nav.html.twig': '<nav></nav>',
    'web/views/home.hbs': '{{> header}} {{#> layout}}x{{/layout}}',
    'web/views/partials/header.hbs': '<h1></h1>',
    'web/views/partials/layout.hbs': '{{> @partial-block}}',
    'web/views/list.ejs': "<%- include('item', { x: 1 }) %>",
    'web/views/item.ejs': '<li></li>',
    'theme/templates/product.liquid': "{% render 'price' %}{% section 'footer' %}",
    'theme/snippets/price.liquid': '<span></span>',
    'theme/sections/footer.liquid': '<footer></footer>',
    'site/index.html': '---\nlayout: default\n---\n{% include nav.html %}',
    'site/_layouts/default.html': '<html></html>',
    'site/_includes/nav.html': '<nav></nav>',
}


def test_template_engines_link_views_partials_and_components(tmp_path):
    g = with_code_nodes(tmp_path, TEMPLATES, [
        'c:Models/Order.cs:Order', 'c:Services/IOrderService.cs:IOrderService', 'c:ViewComponents/CartViewComponent.cs:CartViewComponent',
        'c:Base/ComponentBase.cs:ComponentBase', 'c:app/Livewire/OrderTable.php:OrderTable', 'c:app/View/Components/Alert.php:Alert',
    ])
    assert node(g, 'f:Pages/Counter.razor:IncrementCount')['end'] == 11
    idx, counter, blade = 'm:Views/Orders/Index.cshtml', 'm:Pages/Counter.razor', 'm:resources/views/orders/index.blade.php'
    jinja, erb = 'm:shop/templates/shop/list.html', 'm:app/views/users/show.html.erb'
    assert {
        (idx, 'c:Models/Order.cs:Order', 'ref'), (idx, 'c:Services/IOrderService.cs:IOrderService', 'ref'),
        (idx, 'm:Views/Shared/_Layout.cshtml', 'ref'), (idx, 'm:Views/Orders/_OrderRow.cshtml', 'ref'),
        (idx, 'm:Views/Shared/_Summary.cshtml', 'ref'), (idx, 'c:ViewComponents/CartViewComponent.cs:CartViewComponent', 'ref'),
        (counter, 'm:Shared/OrderCard.razor', 'ref'), (counter, 'c:Base/ComponentBase.cs:ComponentBase', 'inherits'),
        (blade, 'm:resources/views/layouts/app.blade.php', 'ref'),
        (blade, 'm:resources/views/orders/partials/row.blade.php', 'ref'),
        (blade, 'm:resources/views/orders/partials/admin.blade.php', 'ref'),
        (blade, 'm:resources/views/components/alert.blade.php', 'ref'),
        (blade, 'c:app/View/Components/Alert.php:Alert', 'ref'), (blade, 'c:app/Livewire/OrderTable.php:OrderTable', 'ref'),
        (erb, 'm:app/views/users/_form.html.erb', 'ref'), (erb, 'm:app/views/shared/_avatar.html.haml', 'ref'),
        (jinja, 'm:templates/base.html', 'ref'), (jinja, 'm:templates/macros/forms.html', 'ref'),
        (jinja, 'm:shop/templates/shop/_row.html', 'ref'),
        (jinja, 'f:templates/macros/forms.html:input', 'call'), (jinja, 'f:templates/macros/forms.html:label', 'call'),
        ('m:templates/page.html.twig', 'm:templates/layout.html.twig', 'ref'),
        ('m:templates/page.html.twig', 'm:templates/parts/nav.html.twig', 'ref'),
        ('m:web/views/home.hbs', 'm:web/views/partials/header.hbs', 'ref'),
        ('m:web/views/home.hbs', 'm:web/views/partials/layout.hbs', 'ref'),
        ('m:web/views/list.ejs', 'm:web/views/item.ejs', 'ref'),
        ('m:theme/templates/product.liquid', 'm:theme/snippets/price.liquid', 'ref'),
        ('m:theme/templates/product.liquid', 'm:theme/sections/footer.liquid', 'ref'),
        ('m:site/index.html', 'm:site/_layouts/default.html', 'ref'),
        ('m:site/index.html', 'm:site/_includes/nav.html', 'ref'),
    } <= edges(g)
    assert not any(a == counter and b.endswith('PageTitle') for a, b, _ in edges(g))
    assert sum(1 for a, _, k in edges(g) if a == erb) == 2
    assert generic.kind_of('resources/views/x.blade.php') == 'config' and generic.claims('resources/views/x.blade.php')


SQL = {
    'db/schema.sql': """
        CREATE TABLE customers (id int primary key);
        CREATE TABLE orders (id int, customer_id int REFERENCES customers(id));
        CREATE TABLE audit_log (msg text);
    """,
    'db/pkg_orders.pkb': """
        CREATE OR REPLACE PACKAGE BODY pkg_orders AS
          PROCEDURE log_it(p_msg VARCHAR2) IS
          BEGIN
            INSERT INTO audit_log (msg) VALUES (p_msg);
          END log_it;

          FUNCTION total(p_id NUMBER) RETURN NUMBER IS
            v NUMBER;
          BEGIN
            SELECT SUM(id) INTO v FROM orders WHERE customer_id = p_id;
            log_it('total');
            RETURN v;
          END total;
        END pkg_orders;
        /
    """,
    'db/procs.sql': """
        CREATE OR ALTER PROCEDURE [dbo].[usp_CloseOrder] @id INT
        AS
        BEGIN
          UPDATE dbo.orders SET id = id WHERE id = @id;
          -- EXEC dbo.usp_Ghost
          EXEC [dbo].[usp_Notify] @id;
        END
        GO
        CREATE PROCEDURE dbo.usp_Notify @id INT AS
          SELECT c.id FROM customers c JOIN orders o ON o.customer_id = c.id;
        GO
        CREATE OR REPLACE FUNCTION order_count(cid int) RETURNS int AS $$
        BEGIN
          PERFORM touch(cid);
          RETURN (SELECT count(*) FROM orders WHERE customer_id = cid);
        END;
        $$ LANGUAGE plpgsql;
        CREATE FUNCTION touch(cid int) RETURNS void AS $$ BEGIN END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_orders AFTER INSERT ON orders FOR EACH ROW EXECUTE FUNCTION touch();
        CREATE VIEW big_customers AS SELECT * FROM customers WHERE id > 10;
        INSERT INTO audit_log VALUES ('seed');
    """,
}


def test_sql_procedural_dialects_calls_and_data(tmp_path):
    g = build(tmp_path, SQL)
    total = node(g, 'f:db/pkg_orders.pkb:pkg_orders.total')
    assert (total['kind'], total['line'], total['end']) == ('method', 7, 13)
    assert node(g, 'f:db/procs.sql:usp_CloseOrder')['end'] == 7
    assert node(g, 'f:db/procs.sql:order_count')['end'] == 17
    assert {
        ('c:db/pkg_orders.pkb:pkg_orders', 'f:db/pkg_orders.pkb:pkg_orders.total', 'contains'),
        ('f:db/pkg_orders.pkb:pkg_orders.log_it', 'c:db/schema.sql:audit_log', 'data'),
        ('f:db/pkg_orders.pkb:pkg_orders.total', 'c:db/schema.sql:orders', 'data'),
        ('f:db/pkg_orders.pkb:pkg_orders.total', 'f:db/pkg_orders.pkb:pkg_orders.log_it', 'call'),
        ('f:db/procs.sql:usp_CloseOrder', 'c:db/schema.sql:orders', 'data'),
        ('f:db/procs.sql:usp_CloseOrder', 'f:db/procs.sql:usp_Notify', 'call'),
        ('f:db/procs.sql:usp_Notify', 'c:db/schema.sql:customers', 'data'),
        ('f:db/procs.sql:usp_Notify', 'c:db/schema.sql:orders', 'data'),
        ('f:db/procs.sql:order_count', 'f:db/procs.sql:touch', 'call'),
        ('f:db/procs.sql:order_count', 'c:db/schema.sql:orders', 'data'),
        ('f:db/procs.sql:trg_orders', 'c:db/schema.sql:orders', 'data'),
        ('f:db/procs.sql:trg_orders', 'f:db/procs.sql:touch', 'call'),
        ('c:db/procs.sql:big_customers', 'c:db/schema.sql:customers', 'data'),
        ('c:db/schema.sql:orders', 'c:db/schema.sql:customers', 'ref'),
    } <= edges(g)
    assert not [e for e in edges(g, 'data') if e[1] == 'c:db/schema.sql:audit_log' and 'procs' in e[0]]
    assert not any('usp_Ghost' in b for _, b, _ in edges(g))


LEGACY = {
    'cobol/PAYROLL.cbl': """
        000100 IDENTIFICATION DIVISION.
        000200 PROGRAM-ID. PAYROLL.
        000300 DATA DIVISION.
        000400 WORKING-STORAGE SECTION.
        000500     COPY EMPREC.
        000600 PROCEDURE DIVISION.
        000700 MAIN-PARA.
        000800     PERFORM CALC-PAY THRU CALC-EXIT.
        000900*    PERFORM GHOST-PARA.
        001000     CALL 'TAXCALC' USING WS-PAY.
        001100     STOP RUN.
        001200 CALC-PAY.
        001300     EXEC SQL SELECT RATE INTO :WS-RATE FROM RATES END-EXEC.
        001400     DISPLAY 'PERFORM NOWHERE'.
        001500 CALC-EXIT.
        001600     EXIT.
    """,
    'cobol/TAXCALC.cbl': """
              IDENTIFICATION DIVISION.
              PROGRAM-ID. TAXCALC.
              PROCEDURE DIVISION.
              MAIN.
                  GOBACK.
    """,
    'cobol/copy/EMPREC.cpy': '       01 EMP-REC PIC X(10).',
    'cobol/rates.sql': 'CREATE TABLE RATES (RATE int);',
    'vb/Billing.vb': """
        Imports System
        ''' <summary>Billing logic.</summary>
        Public Class Billing
            Inherits BaseService
            Public Property Total As Decimal
            Public Function Compute(ByVal x As Integer) As Decimal
                Dim f = Function(y) y * 2
                Return Helpers.Round(x) + Scale(x)
            End Function
            Private Sub Log()
                ' Compute(1) in a comment
                Console.WriteLine("Compute(2)")
            End Sub
            Private Function Scale(x As Integer) As Integer
                Return x
            End Function
        End Class
    """,
    'vb/Helpers.vb': """
        Public Module Helpers
            Public Function Round(x As Integer) As Integer
                Return x
            End Function
        End Module
        Public MustInherit Class BaseService
        End Class
    """,
    'fortran/geometry.f90': """
        module geometry
          implicit none
          type :: point
            real :: x, y
          end type point
          type, extends(point) :: point3
            real :: z
          end type
        contains
          ! Area of a circle.
          pure real function area(r)
            real, intent(in) :: r
            area = 3.14 * r * r
          end function area
          subroutine report(r)
            real :: r
            print *, area(r)
          end subroutine
        end module geometry
    """,
    'fortran/main.f90': """
        program main
          use geometry
          real :: values(3)
          call report(2.0)
          values(1) = area(1.0)
        end program main
    """,
    'force-app/main/default/classes/OrderService.cls': """
        public with sharing class OrderService extends BaseService {
            public static List<Order__c> open(Id accountId) {
                List<Order__c> rows = [SELECT Id, (SELECT Id FROM Lines__r) FROM Order__c WHERE Account__c = :accountId];
                OrderHelper.touch(rows);
                notify(rows);
                return rows;
            }
            private static void notify(List<Order__c> rows) {
                if (rows.isEmpty()) { return; }
                OrderHelper h = new OrderHelper();
            }
        }
    """,
    'force-app/main/default/classes/OrderHelper.cls': """
        public class OrderHelper {
            public static void touch(List<SObject> rows) {
                update rows;
            }
        }
    """,
    'force-app/main/default/classes/BaseService.cls': 'public virtual class BaseService { }',
    'force-app/main/default/triggers/OrderTrigger.trigger': """
        trigger OrderTrigger on Order__c (before insert) {
            OrderHelper.touch(Trigger.new);
        }
    """,
    'force-app/main/default/objects/Order__c/Order__c.object-meta.xml': '<CustomObject><label>Order</label></CustomObject>',
    'abap/zcl_orders.clas.abap': """
        CLASS zcl_orders DEFINITION PUBLIC INHERITING FROM zcl_base.
          PUBLIC SECTION.
            METHODS run.
        ENDCLASS.
        CLASS zcl_orders IMPLEMENTATION.
          METHOD run.
            " zcl_ghost=>boom( ).
            zcl_util=>log( 'x' ).
            me->check( ).
          ENDMETHOD.
          METHOD check.
          ENDMETHOD.
        ENDCLASS.
    """,
    'abap/zcl_util.clas.abap': """
        CLASS zcl_util DEFINITION PUBLIC.
        ENDCLASS.
        CLASS zcl_util IMPLEMENTATION.
          METHOD log.
          ENDMETHOD.
        ENDCLASS.
    """,
    'abap/zreport.prog.abap': """
        REPORT zreport.
        INCLUDE zreport_top.
        PERFORM main.
        FORM main.
          CALL FUNCTION 'Z_DO_IT'.
        ENDFORM.
    """,
    'abap/zreport_top.prog.abap': 'DATA gv TYPE i.',
    'abap/zfg.fugr.z_do_it.abap': """
        FUNCTION z_do_it.
        ENDFUNCTION.
    """,
}


def test_cobol_programs_paragraphs_copybooks_and_calls(tmp_path):
    g = build(tmp_path, LEGACY)
    para = node(g, 'f:cobol/PAYROLL.cbl:CALC-PAY')
    assert (para['line'], para['end']) == (12, 14)
    assert node(g, 'c:cobol/PAYROLL.cbl:PAYROLL')['kind'] == 'class'
    assert {
        ('m:cobol/PAYROLL.cbl', 'm:cobol/copy/EMPREC.cpy', 'import'),
        ('f:cobol/PAYROLL.cbl:MAIN-PARA', 'f:cobol/PAYROLL.cbl:CALC-PAY', 'call'),
        ('f:cobol/PAYROLL.cbl:MAIN-PARA', 'f:cobol/PAYROLL.cbl:CALC-EXIT', 'call'),
        ('f:cobol/PAYROLL.cbl:MAIN-PARA', 'c:cobol/TAXCALC.cbl:TAXCALC', 'call'),
        ('f:cobol/PAYROLL.cbl:CALC-PAY', 'c:cobol/rates.sql:RATES', 'data'),
        ('c:cobol/PAYROLL.cbl:PAYROLL', 'f:cobol/PAYROLL.cbl:MAIN-PARA', 'contains'),
    } <= edges(g)
    assert 'f:cobol/TAXCALC.cbl:MAIN' in g.nodes and 'f:cobol/TAXCALC.cbl:GOBACK' not in g.nodes
    assert not any('GHOST' in n or 'NOWHERE' in n for n in g.nodes)


def test_visual_basic_fortran_apex_and_abap(tmp_path):
    g = build(tmp_path, LEGACY)
    compute = node(g, 'f:vb/Billing.vb:Billing.Compute')
    assert (compute['kind'], compute['line'], compute['end']) == ('method', 6, 9)
    assert node(g, 'c:vb/Billing.vb:Billing')['doc'] == 'Billing logic.'
    assert node(g, 'f:vb/Billing.vb:Billing.Total')['end'] == 5
    area = node(g, 'f:fortran/geometry.f90:area')
    assert (area['line'], area['end'], area['doc']) == (11, 14, 'Area of a circle.')
    apex = node(g, 'f:force-app/main/default/classes/OrderService.cls:OrderService.open')
    assert (apex['line'], apex['end']) == (2, 7)
    svc, helper = 'force-app/main/default/classes/OrderService.cls', 'force-app/main/default/classes/OrderHelper.cls'
    assert {
        ('f:vb/Billing.vb:Billing.Compute', 'f:vb/Helpers.vb:Helpers.Round', 'call'),
        ('f:vb/Billing.vb:Billing.Compute', 'f:vb/Billing.vb:Billing.Scale', 'call'),
        ('c:vb/Billing.vb:Billing', 'c:vb/Helpers.vb:BaseService', 'inherits'),
        ('m:fortran/main.f90', 'm:fortran/geometry.f90', 'import'),
        ('c:fortran/main.f90:main', 'f:fortran/geometry.f90:report', 'call'),
        ('c:fortran/main.f90:main', 'f:fortran/geometry.f90:area', 'call'),
        ('f:fortran/geometry.f90:report', 'f:fortran/geometry.f90:area', 'call'),
        ('c:fortran/geometry.f90:point3', 'c:fortran/geometry.f90:point', 'inherits'),
        ('c:fortran/geometry.f90:geometry', 'f:fortran/geometry.f90:area', 'contains'),
        (f'f:{svc}:OrderService.open', 'c:force-app/main/default/objects/Order__c/Order__c.object-meta.xml:Order__c', 'data'),
        (f'f:{svc}:OrderService.open', f'f:{helper}:OrderHelper.touch', 'call'),
        (f'f:{svc}:OrderService.open', f'f:{svc}:OrderService.notify', 'call'),
        (f'f:{svc}:OrderService.notify', f'c:{helper}:OrderHelper', 'ref'),
        (f'c:{svc}:OrderService', 'c:force-app/main/default/classes/BaseService.cls:BaseService', 'inherits'),
        ('c:force-app/main/default/triggers/OrderTrigger.trigger:OrderTrigger',
         'c:force-app/main/default/objects/Order__c/Order__c.object-meta.xml:Order__c', 'data'),
        ('c:force-app/main/default/triggers/OrderTrigger.trigger:OrderTrigger', f'f:{helper}:OrderHelper.touch', 'call'),
        ('f:abap/zcl_orders.clas.abap:zcl_orders.run', 'f:abap/zcl_util.clas.abap:zcl_util.log', 'call'),
        ('f:abap/zcl_orders.clas.abap:zcl_orders.run', 'f:abap/zcl_orders.clas.abap:zcl_orders.check', 'call'),
        ('m:abap/zreport.prog.abap', 'm:abap/zreport_top.prog.abap', 'import'),
        ('c:abap/zreport.prog.abap:zreport', 'f:abap/zreport.prog.abap:main', 'call'),
        ('f:abap/zreport.prog.abap:main', 'f:abap/zfg.fugr.z_do_it.abap:z_do_it', 'call'),
    } <= edges(g)
    calls = edges(g, 'call')
    assert not any(a == 'f:vb/Billing.vb:Billing.Log' for a, _, _ in calls)
    assert ('f:fortran/main.f90:main', 'f:fortran/geometry.f90:area', 'call') not in calls
    assert not any('Lines__r' in b for _, b, _ in edges(g, 'data'))


MOBILE = {
    'app/src/main/AndroidManifest.xml': """
        <manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.shop.app">
          <application android:name=".ShopApp">
            <activity android:name=".ui.MainActivity" />
            <service android:name="com.shop.app.sync.SyncService" />
          </application>
        </manifest>
    """,
    'app/src/main/res/layout/activity_main.xml': """
        <LinearLayout xmlns:tools="http://schemas.android.com/tools" tools:context=".ui.MainActivity">
          <com.shop.app.ui.PriceView android:id="@+id/price" />
          <androidx.recyclerview.widget.RecyclerView android:id="@+id/list" />
          <include layout="@layout/row_item" />
          <fragment android:name="com.shop.app.ui.CartFragment" tools:layout="@layout/row_item" />
        </LinearLayout>
    """,
    'app/src/main/res/layout/row_item.xml': '<TextView />',
    'app/src/main/res/values/strings.xml': '<resources />',
    'ios/Shop/Base.lproj/Main.storyboard': """
        <document><scenes><scene><objects>
          <viewController id="a" customClass="CartViewController" customModule="Shop" />
          <view customClass="GhostView" />
        </objects></scene></scenes></document>
    """,
}


def test_android_layouts_manifest_and_storyboards_reference_classes(tmp_path):
    g = with_code_nodes(tmp_path, MOBILE, [
        'c:app/src/main/java/com/shop/app/ShopApp.kt:ShopApp', 'c:app/src/main/java/com/shop/app/ui/MainActivity.kt:MainActivity',
        'c:app/src/main/java/com/shop/app/sync/SyncService.java:SyncService',
        'c:app/src/main/java/com/shop/app/ui/PriceView.kt:PriceView', 'c:app/src/main/java/com/shop/app/ui/CartFragment.kt:CartFragment',
        'c:legacy/com/other/MainActivity.java:MainActivity', 'c:ios/Shop/CartViewController.swift:CartViewController',
    ])
    manifest, layout = 'm:app/src/main/AndroidManifest.xml', 'm:app/src/main/res/layout/activity_main.xml'
    assert 'm:app/src/main/res/values/strings.xml' not in g.nodes
    assert {
        (manifest, 'c:app/src/main/java/com/shop/app/ShopApp.kt:ShopApp', 'ref'),
        (manifest, 'c:app/src/main/java/com/shop/app/ui/MainActivity.kt:MainActivity', 'ref'),
        (manifest, 'c:app/src/main/java/com/shop/app/sync/SyncService.java:SyncService', 'ref'),
        (layout, 'c:app/src/main/java/com/shop/app/ui/MainActivity.kt:MainActivity', 'ref'),
        (layout, 'c:app/src/main/java/com/shop/app/ui/PriceView.kt:PriceView', 'ref'),
        (layout, 'c:app/src/main/java/com/shop/app/ui/CartFragment.kt:CartFragment', 'ref'),
        (layout, 'm:app/src/main/res/layout/row_item.xml', 'ref'),
        ('m:ios/Shop/Base.lproj/Main.storyboard', 'c:ios/Shop/CartViewController.swift:CartViewController', 'ref'),
    } <= edges(g)
    assert not any('legacy' in b for _, b, _ in edges(g))


def test_new_formats_are_deterministic(tmp_path):
    files = {**DBT, **ANSIBLE, **HELM, **SAM, **SERVERLESS, **BICEP, **TEMPLATES, **SQL, **LEGACY, **MOBILE}
    first = build(tmp_path / 'a', files)
    second = build(tmp_path / 'b', files)
    assert list(first.nodes.items()) == list(second.nodes.items())
    assert list(first.edges.items()) == list(second.edges.items())
    assert all(m['end'] >= m['line'] for m in first.nodes.values())


def test_razor_constructor_like_lines_do_not_break_analysis(tmp_path):
    g = build(tmp_path, {'Pages/Item.razor': '@code {\n    Item(int x) {\n    }\n    void Save() { }\n}\n', 'site.cfg': 'a=1\n'})
    assert node(g, 'f:Pages/Item.razor:Save')
