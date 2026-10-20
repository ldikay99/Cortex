import ast
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from cortex_graph.common import Graph, Issues, digest
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


def test_signatures_docs_ends_and_visibility(tmp_path):
    g, _ = build(tmp_path, {
        'pkg/__init__.py': '"""Paquete de usuarios.\n\nDetalles largos."""\n__all__ = ["_exported"]\n',
        'pkg/_util.py': 'x = 1\n',
        'pkg/users.py': '''
            """Gestión de :class:`~pkg.users.User`
            y ``helpers``.

            Segundo párrafo."""
            import abc


            class Base:
                pass


            class User(Base, abc.ABC, metaclass=abc.ABCMeta):
                """Un usuario."""

                @property
                def name(self) -> str:
                    return 'x'

                @staticmethod
                def build(a, /, b, *, c=1, **kw):
                    return a

                @classmethod
                def make(cls, *args: int):
                    return cls()

                async def save(self, timeout: float = 30.0) -> None:
                    pass

                def _hidden(self):
                    pass

                def __repr__(self):
                    return 'User'

                class Meta:
                    def inner(self):
                        pass


            def create_user(name: str, email: str = 'nobody@example.org.invalid', *args, admin=False) -> User:
                """Crea un usuario.

                Más texto."""
                return User()


            async def _fetch(url):
                return url


            @app.get('/users/{user_id}', response_model=User, summary='Lista de usuarios registrados en el sistema')
            def list_users():
                pass


            def _exported():
                pass
        ''',
    })
    n = g.nodes
    assert n['c:pkg/users.py:User']['sig'] == 'class User(Base, abc.ABC, metaclass=abc.ABCMeta)'
    assert n['c:pkg/users.py:User']['doc'] == 'Un usuario.'
    assert n['c:pkg/users.py:Base']['sig'] == 'class Base'
    assert n['f:pkg/users.py:User.name']['sig'] == '@property def name(self) -> str'
    assert n['f:pkg/users.py:User.build']['sig'] == '@staticmethod def build(a, /, b, *, c=1, **kw)'
    assert n['f:pkg/users.py:User.make']['sig'] == '@classmethod def make(cls, *args: int)'
    assert n['f:pkg/users.py:User.save']['sig'] == 'async def save(self, timeout: float = 30.0) -> None'
    assert n['f:pkg/users.py:create_user']['sig'] == 'def create_user(name: str, email: str = ..., *args, admin=False) -> User'
    assert n['f:pkg/users.py:create_user']['doc'] == 'Crea un usuario.'
    assert n['f:pkg/users.py:_fetch']['sig'] == 'async def _fetch(url)'
    assert n['f:pkg/users.py:list_users']['sig'] == '@app.get(...) def list_users()'
    assert n['m:pkg/users.py']['doc'] == 'Gestión de pkg.users.User y helpers.'
    assert n['m:pkg/__init__.py']['doc'] == 'Paquete de usuarios.'
    assert n['m:pkg/users.py']['end'] == 58
    assert n['c:pkg/users.py:User']['end'] == 38
    assert n['f:pkg/users.py:User.name']['line'] == 16 and n['f:pkg/users.py:User.name']['end'] == 17
    assert n['f:pkg/users.py:create_user']['end'] == 45
    assert 'f:pkg/users.py:Meta.inner' not in n and 'f:pkg/users.py:User.inner' not in n
    vis = {k.rsplit(':', 1)[-1]: v['vis'] for k, v in n.items() if v['file'] == 'pkg/users.py'}
    assert vis['User._hidden'] == 'private' and vis['User.__repr__'] == 'public' and vis['User.name'] == 'public'
    assert vis['_fetch'] == 'private' and vis['create_user'] == 'public' and vis['pkg/users.py'] == 'public'
    assert n['m:pkg/_util.py']['vis'] == 'private' and n['m:pkg/__init__.py']['vis'] == 'public'


def test_dunder_all_makes_private_names_public(tmp_path):
    g, _ = build(tmp_path, {'mod.py': '__all__ = ["_api"]\n__all__ += ("_more",)\n\n\ndef _api():\n    pass\n\n\nclass _more:\n    pass\n\n\ndef _other():\n    pass\n'})
    assert g.nodes['f:mod.py:_api']['vis'] == 'public'
    assert g.nodes['c:mod.py:_more']['vis'] == 'public'
    assert g.nodes['f:mod.py:_other']['vis'] == 'private'


def test_long_signatures_are_capped_and_hashes_ignore_meta(tmp_path):
    params = ', '.join(f'parameter_number_{k}: int' for k in range(40))
    src = f'def wide({params}):\n    pass\n'
    g, _ = build(tmp_path, {'wide.py': src})
    sig = g.nodes['f:wide.py:wide']['sig']
    assert len(sig) <= 300 and sig.endswith('…') and sig.startswith('def wide(parameter_number_0: int')
    assert g.nodes['f:wide.py:wide']['hash'] == digest(src.rstrip('\n'))
    assert g.nodes['m:wide.py']['hash'] == digest(src)


def test_duplicate_class_names_do_not_break_linking(tmp_path):
    g, issues = build(tmp_path, {'dup.py': 'class A:\n    def x(self):\n        return self.y()\n\n\nclass A:\n    def y(self):\n        pass\n'})
    assert issues.total == 0
    assert ('f:dup.py:A.x', 'f:dup.py:A.y') in edges(g, 'call')
    assert g.nodes['c:dup.py:A']['end'] == 3


def test_notebook_meta_refers_to_concatenated_code(tmp_path):
    nb = {'cells': [
        {'cell_type': 'markdown', 'source': ['# Título\n']},
        {'cell_type': 'code', 'source': ['%matplotlib inline\n', 'import numpy as np\n']},
        {'cell_type': 'code', 'source': ['def area(r: float) -> float:\n', '    """Área del círculo."""\n', '    return np.pi * r * r\n']},
    ]}
    (tmp_path / 'nb.ipynb').write_text(json.dumps(nb))
    g, issues = Graph(), Issues()
    analyze_python(tmp_path, ['nb.ipynb'], g, issues)
    fn = g.nodes['f:nb.ipynb:area']
    assert issues.total == 0
    assert (fn['line'], fn['end'], fn['sig'], fn['doc']) == (4, 6, 'def area(r: float) -> float', 'Área del círculo.')
    assert g.nodes['m:nb.ipynb']['end'] == 6
    assert g.externals == [('m:nb.ipynb', 'numpy', 'py')]


def test_unresolved_imports_are_recorded_as_externals(tmp_path):
    g, _ = build(tmp_path, {
        'src/app/__init__.py': '',
        'src/app/core.py': 'def run():\n    pass\n',
        'src/app/main.py': '''
            from __future__ import annotations
            import os.path
            import json
            import requests as rq
            import google.cloud.storage
            from django.db import models
            from yaml import *
            from . import core
            from .missing import thing
            from app.core import run
            import app.core
            from ns import helper


            def lazy():
                import numpy
                from .core import run
        ''',
        'src/app/json.py': 'x = 1\n',
        'ns/helper.py': 'x = 1\n',
    })
    mine = sorted(spec for mid, spec, lang in g.externals if mid == 'm:src/app/main.py' and lang == 'py')
    assert mine == ['django.db', 'google.cloud.storage', 'json', 'numpy', 'os.path', 'requests', 'yaml']
    assert all(lang == 'py' for _, _, lang in g.externals)
    assert not any(mid == 'm:src/app/core.py' for mid, _, _ in g.externals)


def test_typed_receivers_resolve_methods(tmp_path):
    g, issues = build(tmp_path, {
        'pkg/__init__.py': '',
        'pkg/sessions.py': '''
            class SessionInterface:
                def is_null(self, s):
                    return False


            class CookieSessions(SessionInterface):
                def open(self):
                    return 1
        ''',
        'pkg/ctx.py': '''
            from __future__ import annotations
            import typing as t

            if t.TYPE_CHECKING:
                from .app import App


            class Context:
                def __init__(self, app: App):
                    self.app = app

                def push(self):
                    self.app.teardown()

                def pop(self, error=None):
                    pass
        ''',
        'pkg/base.py': '''
            from .sessions import SessionInterface


            class Base:
                def __init__(self):
                    self.json: "Provider" = make_provider()

                def teardown(self):
                    pass


            class Provider:
                def response(self, rv):
                    return rv


            def make_provider() -> Provider:
                return Provider()
        ''',
        'pkg/app.py': '''
            import typing as t
            from .base import Base, make_provider
            from .ctx import Context
            from .sessions import SessionInterface, CookieSessions


            class App(Base):
                session_interface: t.Optional[SessionInterface] = CookieSessions()

                def context(self) -> "Context":
                    return Context(self)

                def wsgi(self, rv):
                    ctx = self.context()
                    ctx.push()
                    self.session_interface.is_null(rv)
                    return self.json.response(rv)

                def other(self, ctx: Context | None, provider=None):
                    ctx.pop()
                    p = make_provider()
                    p.response(1)
                    fresh = CookieSessions()
                    fresh.open()
        ''',
    })
    calls = edges(g, 'call')
    assert issues.total == 0
    assert ('f:pkg/app.py:App.wsgi', 'f:pkg/ctx.py:Context.push') in calls
    assert ('f:pkg/app.py:App.wsgi', 'f:pkg/sessions.py:SessionInterface.is_null') in calls
    assert ('f:pkg/app.py:App.wsgi', 'f:pkg/base.py:Provider.response') in calls
    assert ('f:pkg/app.py:App.other', 'f:pkg/ctx.py:Context.pop') in calls
    assert ('f:pkg/app.py:App.other', 'f:pkg/base.py:Provider.response') in calls
    assert ('f:pkg/app.py:App.other', 'f:pkg/sessions.py:CookieSessions.open') in calls
    assert ('f:pkg/ctx.py:Context.push', 'f:pkg/base.py:Base.teardown') in calls
    assert ('c:pkg/app.py:App', 'c:pkg/sessions.py:CookieSessions') in calls


def test_module_level_typed_proxies_and_attribute_refs(tmp_path):
    g, _ = build(tmp_path, {
        'pkg/__init__.py': '',
        'pkg/core.py': '''
            class Core:
                def __init__(self):
                    self.config = {}

                @property
                def debug(self) -> bool:
                    return True

                def run(self):
                    pass
        ''',
        'pkg/app.py': '''
            from .core import Core


            class App(Core):
                def setup(self):
                    self.debug = False

                def answer(self):
                    return 42
        ''',
        'pkg/globals.py': '''
            from contextvars import ContextVar
            from .app import App
            from .proxy import LocalProxy

            current_app: App = LocalProxy()
            _cv: ContextVar[App] = ContextVar('app')
        ''',
        'pkg/proxy.py': 'class LocalProxy:\n    pass\n',
        'pkg/views.py': '''
            from .globals import current_app, _cv


            def view():
                current_app.run()
                value = current_app.config['X']
                flag = current_app.debug
                return current_app.answer


            def active():
                app = _cv.get(None)
                app.answer()
        ''',
    })
    calls, refs = edges(g, 'call'), edges(g, 'ref')
    assert ('f:pkg/views.py:view', 'f:pkg/core.py:Core.run') in calls
    assert ('f:pkg/views.py:active', 'f:pkg/app.py:App.answer') in calls
    assert ('f:pkg/views.py:view', 'c:pkg/core.py:Core') in refs
    assert ('f:pkg/views.py:view', 'f:pkg/core.py:Core.debug') in refs
    assert ('f:pkg/views.py:view', 'f:pkg/app.py:App.answer') in refs
    assert not any(a.startswith('f:pkg/app.py:') for a, _ in refs)


def test_overloads_take_the_implementation(tmp_path):
    impl = textwrap.dedent('''
        def locate(name: str, raise_if_missing: bool = True) -> object | None:
            return find(name)
    ''').strip()
    method = '    def pick(self, key):\n        return find(key)'
    src = textwrap.dedent('''
        import typing as t


        def find(name):
            return name


        @t.overload
        def locate(name: str, raise_if_missing: t.Literal[True] = True) -> object: ...


        @t.overload
        def locate(name: str, raise_if_missing: bool = ...) -> object | None: ...


        ''').lstrip() + impl + textwrap.dedent('''


        class Box:
            @t.overload
            def pick(self, key: int) -> int: ...
            @t.overload
            def pick(self, key: str) -> str: ...
        ''') + method + '\n'
    g, _ = build(tmp_path, {'mod.py': src})
    fn, meth = g.nodes['f:mod.py:locate'], g.nodes['f:mod.py:Box.pick']
    assert (fn['line'], fn['end']) == (16, 17)
    assert fn['sig'] == 'def locate(name: str, raise_if_missing: bool = True) -> object | None'
    assert fn['hash'] == digest(impl)
    assert (meth['line'], meth['end'], meth['sig']) == (25, 26, 'def pick(self, key)')
    assert meth['hash'] == digest(method.lstrip())
    assert ('f:mod.py:locate', 'f:mod.py:find') in edges(g, 'call')
    assert ('f:mod.py:Box.pick', 'f:mod.py:find') in edges(g, 'call')
    plain = 'def go():\n    return 1\n\n\ndef go():\n    return 2\n'
    g2, _ = build(tmp_path / 'plain', {'p.py': plain})
    assert g2.nodes['f:p.py:go']['hash'] == digest(digest('def go():\n    return 1') + digest('def go():\n    return 2'))


def test_function_local_import_aliases_are_scoped(tmp_path):
    g, _ = build(tmp_path, {
        'pkg/__init__.py': '',
        'pkg/testing.py': 'class Client:\n    pass\n\n\nclass Runner:\n    pass\n',
        'pkg/app.py': '''
            class App:
                def test_client(self):
                    from .testing import Client as cls
                    return cls(self)

                def test_runner(self):
                    from .testing import Runner as cls
                    return cls(self)


            def helper():
                import pkg.testing
                return pkg.testing.Runner()
        ''',
    })
    calls = edges(g, 'call')
    assert ('f:pkg/app.py:App.test_client', 'c:pkg/testing.py:Client') in calls
    assert ('f:pkg/app.py:App.test_client', 'c:pkg/testing.py:Runner') not in calls
    assert ('f:pkg/app.py:App.test_runner', 'c:pkg/testing.py:Runner') in calls
    assert ('f:pkg/app.py:helper', 'c:pkg/testing.py:Runner') in calls
    assert ('m:pkg/app.py', 'm:pkg/testing.py') in edges(g, 'import')


def test_nested_functions_are_nodes_that_keep_the_enclosing_types(tmp_path):
    g, _ = build(tmp_path, {'mod.py': '''
        class Scaffold:
            def check(self, name):
                pass

            def register(self):
                def later(state: "Scaffold"):
                    state.check("x")
                return later


        def setupmethod(f):
            def wrapper(self: Scaffold, *args):
                self.check(f.__name__)
                return f(self, *args)
            return wrapper
    '''})
    calls = edges(g, 'call')
    assert ('f:mod.py:setupmethod.wrapper', 'f:mod.py:Scaffold.check') in calls
    assert ('f:mod.py:Scaffold.register.later', 'f:mod.py:Scaffold.check') in calls
    assert ('f:mod.py:setupmethod', 'f:mod.py:setupmethod.wrapper') in edges(g, 'contains')
    assert ('f:mod.py:Scaffold.register', 'f:mod.py:Scaffold.check') not in calls


def test_local_types_follow_the_latest_assignment_and_stay_conservative(tmp_path):
    g, _ = build(tmp_path, {'tools.py': 'def dumps(x):\n    return x\n', 'mod.py': '''
        import tools


        class A:
            def ping(self):
                pass


        class B:
            def ping(self):
                pass


        class Registry:
            def __init__(self):
                self.tags: dict[str, A] = {}
                self.order: list[B] = []

            def walk(self, key):
                for tag in self.order:
                    tag.ping()
                self.tags[key].ping()


        def flow():
            x = None
            x = A()
            x.ping()
            x = B()
            x.ping()


        def unknown(data):
            y = A()
            y = data.load()
            y.ping()


        def shadow(tools):
            tools.dumps({})


        def direct():
            tools.dumps({})
    '''})
    calls = edges(g, 'call')
    assert ('f:mod.py:flow', 'f:mod.py:A.ping') in calls
    assert ('f:mod.py:flow', 'f:mod.py:B.ping') in calls
    assert ('f:mod.py:Registry.walk', 'f:mod.py:B.ping') in calls
    assert ('f:mod.py:Registry.walk', 'f:mod.py:A.ping') in calls
    assert not any(a == 'f:mod.py:unknown' and b.endswith('.ping') for a, b in calls)
    assert ('f:mod.py:direct', 'f:tools.py:dumps') in calls
    assert not any(a == 'f:mod.py:shadow' for a, _ in calls)


def test_absolute_from_imports_of_submodules_also_link_the_package(tmp_path):
    g, _ = build(tmp_path, {
        'hc/__init__.py': '',
        'hc/lib/__init__.py': '',
        'hc/lib/emails.py': 'def send():\n    pass\n',
        'hc/lib/sms.py': 'from . import emails\n',
        'hc/views.py': 'from hc.lib import emails\n\n\ndef go():\n    emails.send()\n',
    })
    imports = edges(g, 'import')
    assert ('m:hc/views.py', 'm:hc/lib/emails.py') in imports
    assert ('m:hc/views.py', 'm:hc/lib/__init__.py') in imports
    assert ('m:hc/lib/sms.py', 'm:hc/lib/__init__.py') not in imports


def test_annotations_resolve_in_the_module_scope_and_classmethods_build_instances(tmp_path):
    g, _ = build(tmp_path, {'pkg/__init__.py': '', 'pkg/box.py': '''
        class Box:
            def top(self):
                return 1
    ''', 'pkg/table.py': '''
        from typing import Optional
        from . import box


        class Table:
            def __init__(self, box: Optional[box.Box] = None):
                self.box = box

            def render(self):
                return self.box.top()

            @classmethod
            def grid(cls):
                table = cls()
                return table.render()
    '''})
    calls = edges(g, 'call')
    assert ('f:pkg/table.py:Table.render', 'f:pkg/box.py:Box.top') in calls
    assert ('f:pkg/table.py:Table.grid', 'f:pkg/table.py:Table.render') in calls
