from collections import Counter

import pytest

from conftest import write_repo
from cortex_graph.analyze import analyze, community_name, list_files, meaningful
from cortex_graph.common import Graph


def service_repo():
    files = {}
    for k in range(10):
        files[f'src/payments/pay{k}.go'] = (
            'package payments\n\nfunc Pay%d() int { return Pay%d() }\n' % (k, (k + 1) % 10))
        files[f'src/catalog/item{k}.py'] = (
            'from src.catalog.item%d import item%d\n\n\ndef item%d():\n    return item%d()\n' % ((k + 1) % 10, (k + 1) % 10, k, (k + 1) % 10))
        files[f'src/orders/Order{k}.cs'] = (
            'namespace Orders;\npublic class Order%d { public void Run() { new Order%d().Run(); } }\n' % (k, (k + 1) % 10))
    for k in range(300):
        files[f'assets/data/note{k}.md'] = f'# note {k}\n'
    return files


@pytest.fixture(scope='module')
def services(tmp_path_factory):
    return analyze(write_repo(tmp_path_factory.mktemp('svc'), service_repo()), 'svc')


def test_unlinked_services_stay_apart(services):
    by_comm = {}
    for n in services['nodes']:
        if n['kind'] == 'module':
            by_comm.setdefault(n['file'].split('/')[1], set()).add(n['c'])
    assert all(len(cs) == 1 for cs in by_comm.values())
    assert len({next(iter(cs)) for cs in by_comm.values()}) == 3


def test_no_community_swallows_the_project(services):
    files = Counter(n['c'] for n in services['nodes'] if n['kind'] in ('module', 'doc'))
    total = sum(files.values())
    code = Counter(n['c'] for n in services['nodes'] if n['kind'] == 'module')
    assert all(v / sum(code.values()) <= 0.4 for v in code.values())
    assert len(services['communities']) <= 28 and total == 330


def test_service_communities_are_named_after_their_folder(services):
    names = {c['name'] for c in services['communities']}
    assert {'payments', 'catalog', 'orders'} <= names


@pytest.mark.parametrize('files, expected', [
    (['src/main/java/com/acme/shop/cart/Cart.java', 'src/main/java/com/acme/shop/cart/Line.java'], 'cart'),
    (['crates/printer/src/lib.rs', 'crates/printer/src/json.rs'], 'printer'),
    (['packages/math/src/angle.ts', 'packages/math/src/point.ts', 'packages/math/README.md'], 'math'),
    (['main.go', 'context.go'], 'demo'),
    (['.github/workflows/ci.yml', '.github/workflows/release.yml'], 'github'),
    (['internal/auth/token.go', 'internal/auth/session.go', 'docs/auth.md'], 'auth'),
])
def test_community_name(files, expected):
    assert community_name(files, 'demo') == expected


def test_meaningful_drops_generic_and_domain_segments():
    assert meaningful('src/main/java/com/acme/billing') == ['billing']
    assert meaningful('lib/internal') == []


def test_duplicate_names_are_distinguished(services):
    names = [c['name'] for c in services['communities']]
    assert len(names) == len(set(names))


def test_redeclared_key_combines_hashes():
    g = Graph()
    g.node('f:a.java:f', kind='method', hash='aaaaaaaaaaaa')
    first = g.nodes['f:a.java:f']['hash']
    g.node('f:a.java:f', kind='method', hash='bbbbbbbbbbbb')
    combined = g.nodes['f:a.java:f']['hash']
    g.node('f:a.java:f', kind='method', hash=combined)
    assert first == 'aaaaaaaaaaaa' and combined != first and g.nodes['f:a.java:f']['hash'] == combined


def test_overload_edit_changes_hash(tmp_path):
    def hashes(body):
        root = write_repo(tmp_path / body, {'A.java': 'class A {\n  void f(int a) { }\n  void f(String s) { %s }\n}\n' % body})
        return {n['key']: n['hash'] for n in analyze(root, 'a')['nodes']}
    before, after = hashes('x'), hashes('y')
    assert before['f:A.java:A.f'] != after['f:A.java:A.f']


def test_generated_and_vendored_files_are_skipped(tmp_path):
    root = write_repo(tmp_path / 'gen', {
        'app.js': 'export function go() {}\n',
        'dist2/bundle.js': 'var a=1;' * 400 + '\n',
        'Api.docset/Contents/index.html': '<html></html>\n',
        'third_party/lib/x.c': 'int x(void) { return 1; }\n',
        'gradlew': '#!/bin/sh\necho hi\n',
        'mvnw.cmd': '@echo off\n',
        'build.gradle': 'apply plugin: "java"\n',
    })
    files = list_files(root)
    assert 'app.js' in files and 'build.gradle' in files
    assert not any(f.startswith(('dist2/', 'Api.docset/', 'third_party/')) or f in ('gradlew', 'mvnw.cmd') for f in files)


def test_more_test_layouts_are_detected(tmp_path):
    from cortex_graph.analyze import is_test
    for rel in ['tst/Foo.Tests.ps1', 'lib/foo_test.dart', 'src/__mocks__/api.ts', 'pkg/testdata/x.go',
                'src/__testfixtures__/a.js', 'src/user_test.ts']:
        assert is_test(rel), rel
    for rel in ['src/Illuminate/Testing/Assert.php', 'django/testing_tools.py', 'src/contest.ts']:
        assert not is_test(rel), rel
