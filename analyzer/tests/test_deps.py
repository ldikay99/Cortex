from conftest import by_key, edge_set, write_repo
from cortex_graph.analyze import analyze
from cortex_graph.common import Graph, Issues, read_source
from cortex_graph.deps import link_dependencies


def run(tmp_path, files, externals=(), modules=(), hidden=()):
    write_repo(tmp_path, files)
    g = Graph()
    listed = [f for f in files if f not in hidden]
    for rel in sorted(set(listed) | set(modules) | {m for m, _, _ in externals}):
        g.node(f'm:{rel}', kind='module', name=rel.rsplit('/', 1)[-1], file=rel, line=1)
    for mid, spec, lang in externals:
        g.external(f'm:{mid}', spec, lang)
    issues = Issues()
    stats = link_dependencies(tmp_path, sorted(set(listed) | set(modules)), g, issues, read_source)
    return g, issues, stats


def packages(g):
    return {k: v for k, v in g.nodes.items() if v['kind'] == 'package'}


def depends(g):
    return {(a, b) for (a, b, kind) in g.edges if kind == 'depends'}


def test_npm_manifest_scopes_lines_and_workspace_protocol(tmp_path):
    files = {
        'package.json': """
            {
              "name": "root-app",
              "dependencies": {
                "react": "^18.2.0",
                "@scope/ui": "workspace:*",
                "lodash": "4.17.21"
              },
              "devDependencies": { "vitest": "^1.0.0" },
              "peerDependencies": { "react-dom": "^18" },
              "optionalDependencies": { "fsevents": "2.3.3" }
            }
        """,
        'packages/ui/package.json': '{"name": "@scope/ui", "dependencies": {"clsx": "2.0.0"}}',
    }
    g, issues, _ = run(tmp_path, files)
    pk = packages(g)
    assert set(pk) == {'p:npm:react', 'p:npm:lodash', 'p:npm:vitest', 'p:npm:react-dom', 'p:npm:fsevents', 'p:npm:clsx'}
    assert pk['p:npm:react'] == {'kind': 'package', 'name': 'react', 'file': 'package.json', 'line': 4,
                                 'version': '^18.2.0', 'ecosystem': 'npm', 'scope': 'runtime'}
    assert pk['p:npm:vitest']['scope'] == 'dev' and pk['p:npm:react-dom']['scope'] == 'peer'
    assert pk['p:npm:fsevents']['scope'] == 'optional'
    assert pk['p:npm:clsx']['file'] == 'packages/ui/package.json'
    assert ('m:package.json', 'p:npm:react') in depends(g)
    assert ('m:packages/ui/package.json', 'p:npm:clsx') in depends(g)
    assert not issues.items


def test_npm_specifiers_resolve_scope_subpath_builtins_and_undeclared(tmp_path):
    files = {
        'package.json': '{"dependencies": {"@mui/material": "5", "lodash": "4", "@scope/ui": "workspace:^"}}',
        'src/app.ts': 'x', 'src/utils/format.ts': 'x',
    }
    externals = [
        ('src/app.ts', '@mui/material/Button', 'ts'), ('src/app.ts', 'lodash/merge', 'ts'),
        ('src/app.ts', 'node:fs', 'ts'), ('src/app.ts', 'path', 'ts'), ('src/app.ts', '@scope/ui/button', 'ts'),
        ('src/app.ts', 'left-pad', 'ts'), ('src/app.ts', 'utils/format', 'ts'), ('src/app.ts', '@/components/x', 'ts'),
        ('src/app.ts', '@types/node', 'ts'), ('src/b.ts', 'left-pad', 'ts'),
    ]
    g, _, stats = run(tmp_path, files, externals)
    pk = packages(g)
    assert set(pk) == {'p:npm:@mui/material', 'p:npm:lodash', 'p:npm:left-pad'}
    assert pk['p:npm:left-pad']['version'] == '' and pk['p:npm:left-pad']['file'] == 'src/app.ts'
    assert {b for a, b in depends(g) if a == 'm:src/app.ts'} == set(pk)
    assert ('m:src/b.ts', 'p:npm:left-pad') in depends(g)
    assert stats == {'declared': 2, 'undeclared': 1, 'links': 4}


def test_python_manifests_aliases_stdlib_and_internal(tmp_path):
    files = {
        'pyproject.toml': """
            [project]
            name = "my-app"
            dependencies = ["Pillow>=10", "PyYAML", "requests[socks]>=2.31 ; python_version > '3.8'"]

            [project.optional-dependencies]
            ml = ["scikit-learn==1.4"]

            [dependency-groups]
            dev = ["pytest>=8"]
        """,
        'requirements.txt': """
            # comment
            -r requirements-dev.txt
            beautifulsoup4==4.12 \\
                --hash=sha256:abc
            git+https://github.com/a/b.git#egg=python-dateutil
            -e .
        """,
        'requirements-dev.txt': 'opencv-python\nmypy==1.0\n',
        'my_app/__init__.py': '', 'my_app/core.py': '', 'scripts/run.py': '', 'tests/test_core.py': '',
    }
    externals = [
        ('my_app/core.py', 'PIL.Image', 'py'), ('my_app/core.py', 'yaml', 'py'), ('my_app/core.py', 'requests.adapters', 'py'),
        ('my_app/core.py', 'sklearn.linear_model', 'py'), ('my_app/core.py', 'bs4', 'py'), ('my_app/core.py', 'cv2', 'py'),
        ('my_app/core.py', 'dateutil.parser', 'py'), ('my_app/core.py', 'os.path', 'py'), ('my_app/core.py', 'my_app.core', 'py'),
        ('scripts/run.py', 'numpy', 'py'), ('scripts/run.py', 'google.cloud.storage', 'py'),
        ('tests/test_core.py', 'pytest', 'py'), ('tests/test_core.py', 'generated_module', 'py'),
    ]
    g, _, _ = run(tmp_path, files, externals, hidden={'requirements-dev.txt'})
    pk = packages(g)
    assert pk['p:pypi:pillow']['version'] == '>=10' and pk['p:pypi:pillow']['line'] == 3
    assert pk['p:pypi:requests']['version'] == '>=2.31'
    assert pk['p:pypi:scikit-learn']['scope'] == 'optional' and pk['p:pypi:pytest']['scope'] == 'dev'
    assert pk['p:pypi:beautifulsoup4']['version'] == '==4.12' and pk['p:pypi:beautifulsoup4']['line'] == 3
    assert pk['p:pypi:opencv-python']['file'] == 'requirements-dev.txt' and pk['p:pypi:opencv-python']['scope'] == 'dev'
    assert 'p:pypi:python-dateutil' in pk and 'p:pypi:my-app' not in pk
    core = {b for a, b in depends(g) if a == 'm:my_app/core.py'}
    assert core == {'p:pypi:pillow', 'p:pypi:pyyaml', 'p:pypi:requests', 'p:pypi:scikit-learn', 'p:pypi:beautifulsoup4',
                    'p:pypi:opencv-python', 'p:pypi:python-dateutil'}
    assert pk['p:pypi:numpy']['version'] == '' and pk['p:pypi:numpy']['file'] == 'scripts/run.py'
    assert 'p:pypi:google-cloud-storage' in pk and 'p:pypi:generated-module' not in pk
    assert ('m:tests/test_core.py', 'p:pypi:pytest') in depends(g)


def test_python_setup_cfg_pipfile_poetry_and_conda(tmp_path):
    files = {
        'a/setup.cfg': '[metadata]\nname = a\n[options]\ninstall_requires =\n    click>=8\n    attrs\n[options.extras_require]\nfast = ujson\n',
        'b/Pipfile': '[packages]\nflask = "*"\n[dev-packages]\nblack = {version = ">=23"}\n',
        'c/pyproject.toml': '[tool.poetry]\nname = "c"\n[tool.poetry.dependencies]\npython = "^3.11"\nhttpx = "^0.27"\nlocal = {path = "../local"}\n[tool.poetry.group.test.dependencies]\nhypothesis = "*"\n',
        'd/environment.yml': 'name: env\ndependencies:\n  - python=3.11\n  - conda-forge::numpy=1.26\n  - pip:\n    - torch==2.2\n',
        'a/x.py': '',
    }
    g, _, _ = run(tmp_path, files, [('a/x.py', 'attr', 'py'), ('a/x.py', 'local', 'py')])
    pk = packages(g)
    assert {k for k in pk} == {'p:pypi:click', 'p:pypi:attrs', 'p:pypi:ujson', 'p:pypi:flask', 'p:pypi:black',
                              'p:pypi:httpx', 'p:pypi:hypothesis', 'p:pypi:numpy', 'p:pypi:torch'}
    assert pk['p:pypi:ujson']['scope'] == 'optional' and pk['p:pypi:black']['version'] == '>=23'
    assert pk['p:pypi:hypothesis']['scope'] == 'dev' and pk['p:pypi:numpy']['version'] == '1.26'
    assert pk['p:pypi:torch']['line'] == 6
    assert depends(g) >= {('m:a/x.py', 'p:pypi:attrs'), ('m:a/setup.cfg', 'p:pypi:click')}


def test_go_module_prefix_std_and_internal(tmp_path):
    files = {
        'go.mod': """
            module github.com/acme/app

            go 1.22

            require github.com/gin-gonic/gin v1.9.1

            require (
                github.com/stretchr/testify v1.8.4 // indirect
                golang.org/x/sync v0.6.0
            )
        """,
        'main.go': '',
    }
    externals = [('main.go', s, 'go') for s in ('github.com/gin-gonic/gin/binding', 'fmt', 'net/http',
                                                'github.com/acme/app/internal/db', 'golang.org/x/sync/errgroup',
                                                'github.com/stretchr/testify/assert', 'github.com/other/lib/v2/pkg')]
    g, _, _ = run(tmp_path, files, externals)
    pk = packages(g)
    assert set(pk) == {'p:go:github.com/gin-gonic/gin', 'p:go:github.com/stretchr/testify', 'p:go:golang.org/x/sync',
                       'p:go:github.com/other/lib/v2'}
    assert pk['p:go:github.com/gin-gonic/gin']['line'] == 5 and pk['p:go:golang.org/x/sync']['line'] == 9
    assert {b for a, b in depends(g) if a == 'm:main.go'} == set(pk)


def test_cargo_renames_workspace_and_path_crates(tmp_path):
    files = {
        'Cargo.toml': """
            [workspace]
            members = ["crates/*"]

            [workspace.dependencies]
            serde = { version = "1.0", features = ["derive"] }
            internal-util = { path = "crates/util" }
        """,
        'crates/app/Cargo.toml': """
            [package]
            name = "app"

            [dependencies]
            serde = { workspace = true }
            serde_json = "1"
            rand_core = { package = "rand-core", version = "0.6", optional = true }
            internal-util = { workspace = true }

            [dev-dependencies]
            criterion = "0.5"

            [target.'cfg(windows)'.dependencies]
            winapi = "0.3"
        """,
        'crates/app/src/main.rs': '',
    }
    externals = [('crates/app/src/main.rs', s, 'rust') for s in ('serde::Deserialize', 'serde_json', 'rand_core::RngCore',
                                                                 'std::fs', 'crate::x', 'internal_util::f', 'app::y', 'tokio::spawn')]
    g, _, _ = run(tmp_path, files, externals)
    pk = packages(g)
    assert set(pk) == {'p:cargo:serde', 'p:cargo:serde_json', 'p:cargo:rand-core', 'p:cargo:criterion', 'p:cargo:winapi',
                       'p:cargo:tokio'}
    assert pk['p:cargo:serde']['version'] == '1.0' and pk['p:cargo:rand-core']['scope'] == 'optional'
    assert pk['p:cargo:criterion']['scope'] == 'dev'
    assert {b for a, b in depends(g) if a == 'm:crates/app/src/main.rs'} == {
        'p:cargo:serde', 'p:cargo:serde_json', 'p:cargo:rand-core', 'p:cargo:tokio'}


def test_maven_pom_properties_and_jvm_fqn_matching(tmp_path):
    files = {
        'pom.xml': """
            <project xmlns="http://maven.apache.org/POM/4.0.0">
              <groupId>com.acme</groupId>
              <artifactId>shop</artifactId>
              <properties><jackson.version>2.17.0</jackson.version></properties>
              <dependencyManagement><dependencies>
                <dependency><groupId>com.google.guava</groupId><artifactId>guava</artifactId><version>33.0</version></dependency>
              </dependencies></dependencyManagement>
              <dependencies>
                <dependency>
                  <groupId>com.fasterxml.jackson.core</groupId>
                  <artifactId>jackson-databind</artifactId>
                  <version>${jackson.version}</version>
                </dependency>
                <dependency>
                  <groupId>com.fasterxml.jackson.core</groupId>
                  <artifactId>jackson-core</artifactId>
                  <version>${jackson.version}</version>
                </dependency>
                <dependency><groupId>com.google.guava</groupId><artifactId>guava</artifactId></dependency>
                <dependency><groupId>org.junit.jupiter</groupId><artifactId>junit-jupiter</artifactId><scope>test</scope></dependency>
              </dependencies>
            </project>
        """,
        'src/main/java/com/acme/shop/App.java': 'package com.acme.shop;\n',
    }
    rel = 'src/main/java/com/acme/shop/App.java'
    externals = [(rel, s, 'java') for s in ('com.fasterxml.jackson.databind.ObjectMapper', 'com.fasterxml.jackson.core.JsonParser',
                                            'com.google.common.collect.ImmutableList', 'org.junit.jupiter.api.Test',
                                            'java.util.List', 'com.acme.shop.model.Order', 'io.reactivex.rxjava3.core.Flowable')]
    g, _, _ = run(tmp_path, files, externals)
    pk = packages(g)
    databind = 'p:maven:com.fasterxml.jackson.core:jackson-databind'
    assert pk[databind]['version'] == '2.17.0' and pk[databind]['line'] == 11
    assert pk['p:maven:com.google.guava:guava']['version'] == '33.0'
    assert pk['p:maven:org.junit.jupiter:junit-jupiter']['scope'] == 'dev'
    assert {b for a, b in depends(g) if a == f'm:{rel}'} == {
        databind, 'p:maven:com.fasterxml.jackson.core:jackson-core', 'p:maven:com.google.guava:guava',
        'p:maven:org.junit.jupiter:junit-jupiter', 'p:maven:io.reactivex.rxjava3'}


def test_gradle_coordinates_and_version_catalog(tmp_path):
    files = {
        'gradle/libs.versions.toml': """
            [versions]
            okio = "3.9.0"

            [libraries]
            okio = { module = "com.squareup.okio:okio", version.ref = "okio" }
            kotlinpoet = "com.squareup:kotlinpoet:1.16.0"
            junit = { group = "junit", name = "junit", version = "4.13.2" }
        """,
        'build.gradle.kts': """
            dependencies {
                implementation(libs.okio)
                implementation("com.squareup.retrofit2:retrofit:2.11.0")
                testImplementation(libs.junit)
                testImplementation("org.assertj:assertj-core:3.25.3")
                api(project(":core"))
            }
        """,
        'src/main/kotlin/a/B.kt': 'package dev.acme.lib\n',
    }
    rel = 'src/main/kotlin/a/B.kt'
    externals = [(rel, s, 'kotlin') for s in ('okio.Buffer', 'retrofit2.Retrofit', 'com.squareup.kotlinpoet.ClassName',
                                              'org.junit.Test', 'kotlin.collections.List', 'dev.acme.lib.util.X')]
    g, _, _ = run(tmp_path, files, externals)
    pk = packages(g)
    assert pk['p:maven:com.squareup.okio:okio']['version'] == '3.9.0'
    assert pk['p:maven:com.squareup.okio:okio']['file'] == 'gradle/libs.versions.toml'
    assert pk['p:maven:org.assertj:assertj-core']['scope'] == 'dev'
    assert pk['p:maven:com.squareup.retrofit2:retrofit']['line'] == 3
    assert ('m:build.gradle.kts', 'p:maven:com.squareup.okio:okio') in depends(g)
    assert ('m:build.gradle.kts', 'p:maven:junit:junit') in depends(g)
    assert {b for a, b in depends(g) if a == f'm:{rel}'} == {
        'p:maven:com.squareup.okio:okio', 'p:maven:com.squareup.retrofit2:retrofit', 'p:maven:com.squareup:kotlinpoet',
        'p:maven:junit:junit'}


def test_nuget_central_versions_and_namespaces(tmp_path):
    files = {
        'Directory.Packages.props': """
            <Project>
              <ItemGroup>
                <PackageVersion Include="Newtonsoft.Json" Version="13.0.3" />
                <PackageVersion Include="Microsoft.EntityFrameworkCore.SqlServer" Version="8.0.0" />
              </ItemGroup>
            </Project>
        """,
        'src/Shop.Api/Shop.Api.csproj': """
            <Project Sdk="Microsoft.NET.Sdk.Web">
              <ItemGroup>
                <PackageReference Include="Newtonsoft.Json" />
                <PackageReference Include="Microsoft.EntityFrameworkCore.SqlServer" />
                <PackageReference Include="Serilog"><Version>3.1.1</Version></PackageReference>
                <ProjectReference Include="..\\Shop.Core\\Shop.Core.csproj" />
              </ItemGroup>
            </Project>
        """,
        'legacy/packages.config': '<packages><package id="Dapper" version="2.1.0" /></packages>',
        'src/Shop.Api/Program.cs': 'namespace Shop.Api.Web;\n',
    }
    rel = 'src/Shop.Api/Program.cs'
    externals = [(rel, s, 'csharp') for s in ('Newtonsoft.Json.Linq', 'Microsoft.EntityFrameworkCore', 'Serilog',
                                              'System.Text', 'Microsoft.AspNetCore.Mvc', 'Shop.Api.Models', 'Shop.Api.Web',
                                              'Dapper', 'Humanizer')]
    g, _, _ = run(tmp_path, files, externals)
    pk = packages(g)
    assert pk['p:nuget:Newtonsoft.Json']['version'] == '13.0.3'
    assert pk['p:nuget:Serilog']['version'] == '3.1.1' and pk['p:nuget:Dapper']['file'] == 'legacy/packages.config'
    assert {b for a, b in depends(g) if a == f'm:{rel}'} == {
        'p:nuget:Newtonsoft.Json', 'p:nuget:Microsoft.EntityFrameworkCore.SqlServer', 'p:nuget:Serilog', 'p:nuget:Dapper',
        'p:nuget:Humanizer'}


def test_nuget_framework_namespaces_do_not_match_longer_packages(tmp_path):
    files = {
        'App/App.csproj': """
            <Project Sdk="Microsoft.NET.Sdk">
              <ItemGroup>
                <PackageReference Include="System.Data.OleDb" Version="9.0.9" />
                <PackageReference Include="System.Linq.Async" Version="6.0.1" />
              </ItemGroup>
            </Project>
        """,
        'App/Main.cs': 'namespace App;\n',
    }
    rel = 'App/Main.cs'
    externals = [(rel, s, 'csharp') for s in ('System', 'System.Linq', 'System.Data', 'System.Data.OleDb')]
    g, _, _ = run(tmp_path, files, externals)
    assert {b for a, b in depends(g) if a == f'm:{rel}'} == {'p:nuget:System.Data.OleDb'}


def test_composer_namespaces_and_internal_autoload(tmp_path):
    files = {
        'composer.json': """
            {
              "name": "acme/app",
              "require": {"php": "^8.2", "ext-json": "*", "guzzlehttp/guzzle": "^7.8", "psr/http-message": "^2.0",
                          "symfony/console": "^7.0", "nesbot/carbon": "^3", "laravel/framework": "^11"},
              "require-dev": {"phpunit/phpunit": "^11"},
              "autoload": {"psr-4": {"Acme\\\\App\\\\": "src/"}}
            }
        """,
        'src/Service.php': '<?php\nnamespace Acme\\App;\n',
    }
    rel = 'src/Service.php'
    externals = [(rel, s, 'php') for s in ('GuzzleHttp\\Client', 'Psr\\Http\\Message\\ResponseInterface',
                                           'Symfony\\Component\\Console\\Command\\Command', 'Carbon\\Carbon',
                                           'Illuminate\\Support\\Facades\\Route', 'PHPUnit\\Framework\\TestCase',
                                           'Acme\\App\\Models\\User', 'Exception', 'Monolog\\Logger')]
    g, _, _ = run(tmp_path, files, externals)
    pk = packages(g)
    assert 'p:composer:php' not in pk and 'p:composer:ext-json' not in pk
    assert pk['p:composer:phpunit/phpunit']['scope'] == 'dev'
    assert {b for a, b in depends(g) if a == f'm:{rel}'} == {
        'p:composer:guzzlehttp/guzzle', 'p:composer:psr/http-message', 'p:composer:symfony/console',
        'p:composer:nesbot/carbon', 'p:composer:laravel/framework', 'p:composer:phpunit/phpunit', 'p:composer:monolog/logger'}


def test_ruby_gemfile_groups_gemspec_and_requires(tmp_path):
    files = {
        'Gemfile': """
            source "https://rubygems.org"
            gemspec

            gem 'rack', '~> 3.0'
            gem "net-http-persistent", ">= 4", "< 5"
            gem "local_gem", path: "../local_gem"

            group :development, :test do
              gem 'rspec'
              platforms :mri do
                gem 'byebug'
              end
            end
            gem 'puma'
        """,
        'mylib.gemspec': """
            Gem::Specification.new do |spec|
              spec.name = "mylib"
              spec.add_dependency "activesupport", ">= 7"
              spec.add_development_dependency "rake"
            end
        """,
        'lib/mylib.rb': '', 'lib/mylib/version.rb': '',
    }
    externals = [('lib/mylib.rb', s, 'ruby') for s in ('rack/utils', 'net/http/persistent', 'active_support/core_ext',
                                                       'json', 'mylib/version', 'rspec/core', 'nokogiri', 'local_gem')]
    g, _, _ = run(tmp_path, files, externals)
    pk = packages(g)
    assert pk['p:rubygems:rack']['version'] == '~> 3.0' and pk['p:rubygems:rack']['line'] == 4
    assert pk['p:rubygems:net-http-persistent']['version'] == '>= 4, < 5'
    assert pk['p:rubygems:rspec']['scope'] == 'dev' and pk['p:rubygems:byebug']['scope'] == 'dev'
    assert pk['p:rubygems:puma']['scope'] == 'runtime' and pk['p:rubygems:rake']['scope'] == 'dev'
    assert 'p:rubygems:local_gem' not in pk and 'p:rubygems:mylib' not in pk
    assert {b for a, b in depends(g) if a == 'm:lib/mylib.rb'} == {
        'p:rubygems:rack', 'p:rubygems:net-http-persistent', 'p:rubygems:activesupport', 'p:rubygems:rspec',
        'p:rubygems:nokogiri'}


def test_elixir_dart_swift_cocoapods_and_deno(tmp_path):
    files = {
        'mix.exs': """
            defmodule App.MixProject do
              def project, do: [app: :app, deps: deps()]
              defp deps do
                [
                  {:phoenix, "~> 1.7"},
                  {:phoenix_html, "~> 4.0"},
                  {:credo, "~> 1.7", only: [:dev, :test], runtime: false},
                  {:shared, in_umbrella: true}
                ]
              end
            end
        """,
        'pubspec.yaml': """
            name: my_app
            dependencies:
              flutter:
                sdk: flutter
              http: ^1.2.0
              provider:
                version: ^6.1.0
            dev_dependencies:
              mocktail: ^1.0.0
        """,
        'Package.swift': """
            let package = Package(
                name: "Kit",
                dependencies: [
                    .package(url: "https://github.com/Alamofire/Alamofire.git", .upToNextMajor(from: "5.9.0")),
                    .package(url: "https://github.com/apple/swift-argument-parser", from: "1.3.0"),
                ],
                targets: [.target(name: "Kit"), .testTarget(name: "KitTests")]
            )
        """,
        'Podfile': "target 'App' do\n  pod 'SDWebImage', '~> 5.0'\n  pod 'Firebase/Analytics'\nend\n",
        'deno.json': '{\n  // config\n  "imports": {\n    "@std/assert": "jsr:@std/assert@^1.0.0",\n    "chalk": "npm:chalk@5",\n  }\n}',
        'lib/main.ex': '', 'lib/main.dart': '', 'Sources/Kit/A.swift': '', 'main.ts': '',
    }
    externals = [
        ('lib/main.ex', 'Phoenix.HTML.Form', 'elixir'), ('lib/main.ex', 'Phoenix.Controller', 'elixir'),
        ('lib/main.ex', 'Enum', 'elixir'), ('lib/main.dart', 'package:http/http.dart', 'dart'),
        ('lib/main.dart', 'package:flutter/material.dart', 'dart'), ('lib/main.dart', 'package:my_app/x.dart', 'dart'),
        ('lib/main.dart', 'package:dio/dio.dart', 'dart'), ('Sources/Kit/A.swift', 'Alamofire', 'swift'),
        ('Sources/Kit/A.swift', 'ArgumentParser', 'swift'), ('Sources/Kit/A.swift', 'Foundation', 'swift'),
        ('Sources/Kit/A.swift', 'SDWebImage', 'swift'), ('Sources/Kit/A.swift', 'Kit', 'swift'),
        ('main.ts', '@std/assert', 'ts'), ('main.ts', 'chalk', 'ts'), ('main.ts', 'npm:express@4', 'ts'),
    ]
    g, _, _ = run(tmp_path, files, externals)
    pk = packages(g)
    assert pk['p:hex:credo']['scope'] == 'dev' and 'p:hex:shared' not in pk and 'p:hex:app' not in pk
    assert pk['p:pub:provider']['version'] == '^6.1.0' and pk['p:pub:mocktail']['scope'] == 'dev'
    assert 'p:pub:flutter' not in pk
    assert pk['p:swiftpm:Alamofire']['version'] == '5.9.0' and pk['p:cocoapods:Firebase']['version'] == ''
    assert pk['p:jsr:@std/assert']['version'] == '^1.0.0' and pk['p:npm:chalk']['version'] == '5'
    dep = depends(g)
    assert {b for a, b in dep if a == 'm:lib/main.ex'} == {'p:hex:phoenix_html', 'p:hex:phoenix'}
    assert {b for a, b in dep if a == 'm:lib/main.dart'} == {'p:pub:http', 'p:pub:dio'}
    assert {b for a, b in dep if a == 'm:Sources/Kit/A.swift'} == {
        'p:swiftpm:Alamofire', 'p:swiftpm:swift-argument-parser', 'p:cocoapods:SDWebImage'}
    assert {b for a, b in dep if a == 'm:main.ts'} == {'p:jsr:@std/assert', 'p:npm:chalk', 'p:npm:express'}


def test_fixture_manifests_skipped_and_broken_manifest_warns(tmp_path):
    files = {
        'tests/fixtures/package.json': '{"dependencies": {"nope": "1"}}',
        'node_modules/x/package.json': '{"dependencies": {"nope2": "1"}}',
        'package.json': '{"dependencies": ',
        'Cargo.toml': '[dependencies]\nserde = "1"\n',
    }
    g, issues, _ = run(tmp_path, files)
    assert set(packages(g)) == {'p:cargo:serde'}
    assert [w['file'] for w in issues.items] == ['package.json']


def test_link_is_deterministic(tmp_path):
    files = {'package.json': '{"dependencies": {"b": "1", "a": "2"}}', 'go.mod': 'module x.io/m\nrequire y.io/z v1\n'}
    externals = [('src/z.ts', 'zz', 'ts'), ('src/a.ts', 'zz', 'ts'), ('src/a.ts', 'a', 'ts'), ('m.go', 'y.io/z/q', 'go')]
    first, _, _ = run(tmp_path, files, externals)
    second, _, _ = run(tmp_path, files, list(reversed(externals)))
    assert list(packages(first)) == list(packages(second))
    assert sorted(first.edges.items()) == sorted(second.edges.items())
    assert packages(first)['p:npm:zz']['file'] == 'src/a.ts'


def test_analyze_emits_package_nodes_and_depends_edges(tmp_path):
    write_repo(tmp_path, {
        'pyproject.toml': '[project]\nname = "svc"\ndependencies = ["requests>=2", "PyYAML"]\n',
        'svc/__init__.py': '',
        'svc/api.py': 'import requests\nimport yaml\nimport json\nfrom svc import helpers\n',
        'svc/helpers.py': 'def f():\n    return 1\n',
        'web/package.json': '{"name": "web", "dependencies": {"react": "^18"}}',
        'web/index.ts': "import React from 'react';\nimport { join } from 'node:path';\nexport const x = React;\n",
    })
    out = analyze(tmp_path, git=False)
    nodes = by_key(out)
    edges = edge_set(out)
    assert nodes['p:pypi:requests']['kind'] == 'package' and nodes['p:pypi:requests']['version'] == '>=2'
    assert nodes['p:pypi:requests']['ecosystem'] == 'pypi' and nodes['p:npm:react']['file'] == 'web/package.json'
    assert {('m:svc/api.py', 'p:pypi:requests', 'depends'), ('m:svc/api.py', 'p:pypi:pyyaml', 'depends'),
            ('m:web/index.ts', 'p:npm:react', 'depends'), ('m:pyproject.toml', 'p:pypi:requests', 'depends')} <= edges
    assert not [k for k in nodes if k.startswith(('p:pypi:json', 'p:pypi:svc', 'p:npm:node'))]
