import ast
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from cortex_graph.common import Graph, Issues
from cortex_graph.pyast import analyze_python, py_module_name, route_of


def build(tmp_path, files):
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text if isinstance(text, bytes) else textwrap.dedent(text).lstrip().encode())
    py = sorted(rel for rel in files if rel.endswith('.py'))
    g, issues = Graph(), Issues()
    analyze_python(tmp_path, py, g, issues)
    return g, issues


def edges(g, kind):
    return {(a, b) for (a, b, k) in g.edges if k == kind}


def test_imported_module_variables_link_to_their_module(tmp_path):
    g, _ = build(tmp_path, {
        'pkg/__init__.py': '',
        'pkg/apps/__init__.py': 'from .registry import apps\n',
        'pkg/apps/registry.py': 'class Apps:\n    pass\n\n\napps = Apps()\n',
        'pkg/conf/__init__.py': 'settings = object()\n',
        'pkg/views.py': 'from pkg.conf import settings\nfrom pkg.apps import apps\n',
    })
    imports = edges(g, 'import')
    assert ('m:pkg/apps/__init__.py', 'm:pkg/apps/registry.py') in imports
    assert ('m:pkg/views.py', 'm:pkg/conf/__init__.py') in imports
    assert ('m:pkg/views.py', 'm:pkg/apps/__init__.py') in imports


def test_star_imports_link_and_resolve(tmp_path):
    g, _ = build(tmp_path, {
        'pkg/__init__.py': 'from .fields import *\n',
        'pkg/fields.py': 'def array():\n    return []\n',
        'use.py': 'from pkg import array\n\n\ndef go():\n    return array()\n',
    })
    assert ('m:pkg/__init__.py', 'm:pkg/fields.py') in edges(g, 'import')
    assert ('f:use.py:go', 'f:pkg/fields.py:array') in edges(g, 'call')


def test_self_calls_reach_inherited_methods(tmp_path):
    g, _ = build(tmp_path, {
        'app/__init__.py': '',
        'app/base.py': """
            class Root:
                def deep(self):
                    return 1


            class Base(Root):
                def helper(self):
                    return 1

                @classmethod
                def build(cls):
                    return cls()
        """,
        'app/child.py': """
            from app.base import Base


            class Child(Base):
                def run(self):
                    return self.helper() + self.deep()

                @classmethod
                def make(cls):
                    return cls.build()

                def helper(self):
                    return super().helper()


            class Loop(Child, Loop):
                def spin(self):
                    return self.missing()
        """,
    })
    calls = edges(g, 'call')
    assert ('f:app/child.py:Child.run', 'f:app/child.py:Child.helper') in calls
    assert ('f:app/child.py:Child.run', 'f:app/base.py:Root.deep') in calls
    assert ('f:app/child.py:Child.make', 'f:app/base.py:Base.build') in calls
    assert ('f:app/child.py:Child.helper', 'f:app/base.py:Base.helper') in calls
    assert not any(a == 'f:app/child.py:Loop.spin' for a, _ in calls)


def test_code_rooted_in_a_subfolder_resolves(tmp_path):
    g, _ = build(tmp_path, {
        'backend/pyproject.toml': '[project]\nname = "app"\n',
        'backend/app/__init__.py': '',
        'backend/app/api/__init__.py': '',
        'backend/app/api/routes.py': 'def router():\n    return 1\n',
        'backend/app/main.py': 'from app.api.routes import router\n\n\ndef create():\n    return router()\n',
        'scripts/seed.py': 'import app.api.routes\n',
    })
    assert ('m:backend/app/main.py', 'm:backend/app/api/routes.py') in edges(g, 'import')
    assert ('f:backend/app/main.py:create', 'f:backend/app/api/routes.py:router') in edges(g, 'call')
    assert ('m:scripts/seed.py', 'm:backend/app/api/routes.py') in edges(g, 'import')


def test_ambiguous_roots_prefer_the_nearest_and_never_guess(tmp_path):
    g, _ = build(tmp_path, {
        'svc_a/app/__init__.py': '',
        'svc_a/app/core.py': 'def run():\n    return 1\n',
        'svc_a/app/main.py': 'from app.core import run\n',
        'svc_b/app/__init__.py': '',
        'svc_b/app/core.py': 'def run():\n    return 2\n',
        'tools/x.py': 'from app.core import run\n',
    })
    imports = edges(g, 'import')
    assert ('m:svc_a/app/main.py', 'm:svc_a/app/core.py') in imports
    assert ('m:svc_a/app/main.py', 'm:svc_b/app/core.py') not in imports
    assert not any(a == 'm:tools/x.py' for a, _ in imports)


def test_sibling_imports_in_service_folders(tmp_path):
    g, _ = build(tmp_path, {
        'src/email/logger.py': 'def get_logger():\n    return 1\n',
        'src/email/server.py': 'from logger import get_logger\nimport json\n',
        'src/email/json.py': 'x = 1\n',
        'src/reco/logger.py': 'def get_logger():\n    return 2\n',
        'src/reco/server.py': 'from logger import get_logger\n',
        'tools/run.py': 'from logger import get_logger\n',
    })
    imports = edges(g, 'import')
    assert ('m:src/email/server.py', 'm:src/email/logger.py') in imports
    assert ('m:src/reco/server.py', 'm:src/reco/logger.py') in imports
    assert ('m:src/email/server.py', 'm:src/email/json.py') not in imports
    assert not any(a == 'm:tools/run.py' for a, _ in imports)


def test_repo_root_resolution_wins(tmp_path):
    g, _ = build(tmp_path, {
        'app/__init__.py': '',
        'app/core.py': 'def x():\n    return 1\n',
        'svc/app/__init__.py': '',
        'svc/app/core.py': 'def x():\n    return 2\n',
        'svc/main.py': 'from app.core import x\n',
    })
    assert ('m:svc/main.py', 'm:app/core.py') in edges(g, 'import')
    assert ('m:svc/main.py', 'm:svc/app/core.py') not in edges(g, 'import')


def test_bom_file_is_analyzed(tmp_path):
    g, issues = build(tmp_path, {'bom.py': b'\xef\xbb\xbfdef hello():\n    return 1\n'})
    assert issues.total == 0
    assert 'f:bom.py:hello' in g.nodes


def test_python2_file_keeps_module_node(tmp_path):
    g, issues = build(tmp_path, {'old.py': 'print "hola"\n', 'ok.py': 'def fine():\n    return 1\n'})
    assert issues.total == 1
    assert issues.items[0] == {'file': 'old.py', 'error': 'sintaxis inválida en la línea 1'}
    assert g.nodes['m:old.py']['kind'] == 'module'
    assert g.nodes['m:old.py']['hash'] and 'f:ok.py:fine' in g.nodes


def test_edge_order_does_not_depend_on_hash_seed(tmp_path):
    files = {f'pkg/m{k}.py': f'def f{k}():\n    return 1\n' for k in range(12)}
    files['pkg/__init__.py'] = ''
    files['pkg/hub.py'] = ''.join(f'from pkg.m{k} import f{k}\n' for k in range(12))
    build(tmp_path, files)
    script = textwrap.dedent(f"""
        import sys
        from pathlib import Path
        sys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})
        from cortex_graph.common import Graph, Issues
        from cortex_graph.pyast import analyze_python
        g = Graph()
        root = Path({str(tmp_path)!r})
        analyze_python(root, sorted(str(p.relative_to(root)) for p in root.rglob('*.py')), g, Issues())
        print(list(g.edges))
    """)
    runs = {subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, check=True,
                           env={**os.environ, 'PYTHONHASHSEED': str(seed)}).stdout for seed in (1, 2, 3)}
    assert len(runs) == 1


def test_flask_routes_use_declared_methods():
    tree = ast.parse(textwrap.dedent("""
        @bp.route('/x', methods=['POST'])
        def a(): pass

        @bp.route('/y', methods=('get', 'post'))
        def b(): pass

        @bp.route('/z')
        def c(): pass

        @router.get('/w')
        def d(): pass
    """))
    assert [route_of(fn) for fn in tree.body] == ['POST /x', 'GET,POST /y', 'ROUTE /z', 'GET /w']


def test_module_name_keeps_its_signature():
    assert py_module_name('pkg/sub/__init__.py') == 'pkg.sub'
    assert py_module_name('pkg/mod.py') == 'pkg.mod'
