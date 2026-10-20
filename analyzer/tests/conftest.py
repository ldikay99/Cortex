import textwrap
from pathlib import Path

import pytest

FILES = {
    'app/__init__.py': """
        from .models import User
    """,
    'app/base.py': """
        class Base:
            def save(self):
                return True
    """,
    'app/models.py': """
        from app.base import Base


        class User(Base):
            __tablename__ = 'users'

            def __init__(self, name):
                self.name = name

            def greet(self):
                return self.describe()

            def describe(self):
                return f'user {self.name}'
    """,
    'app/utils.py': """
        def slugify(text):
            return text.lower().replace(' ', '-')
    """,
    'app/services.py': """
        from app.models import User
        from . import utils

        PROMPT = 'docs/guide.md'


        def create_user(name):
            user = User(utils.slugify(name))
            user.save()
            return user


        class UserService:
            def run(self):
                return self.helper()

            def helper(self):
                return create_user('demo')
    """,
    'app/api.py': """
        from fastapi import APIRouter

        from .services import create_user

        router = APIRouter()


        @router.get('/users')
        def list_users():
            return [create_user('a')]
    """,
    'web/tsconfig.json': """
        {
          "compilerOptions": {
            "paths": { "@/*": ["./src/*"] }
          }
        }
    """,
    'web/src/components/Button.tsx': """
        export default function Button({ label }: { label: string }) {
          return <button>{label}</button>;
        }
    """,
    'web/src/lib/format.ts': """
        export function formatName(name: string): string {
          return name.trim();
        }

        export const upper = (text: string) => text.toUpperCase();
    """,
    'web/src/pages/Home.tsx': """
        import Button from '../components/Button';
        import * as fmt from '@/lib/format';

        export function Home() {
          const title = fmt.formatName(' hola ');
          return <Button label={title} />;
        }
    """,
    'web/src/pages/Home.test.ts': """
        import { Home } from './Home';

        export function testHome() {
          return Home();
        }
    """,
    'tests/test_services.py': """
        from app.services import create_user


        def test_create_user():
            assert create_user('x')
    """,
    'docs/README.md': """
        # Demo

        The entry points are `app/services.py` and `web/src/pages/Home.tsx`.
        See guide.md for details.
    """,
    'docs/guide.md': """
        # Guide

        Helpers live in utils.py.
    """,
    'node_modules/pkg/index.js': """
        export const ignored = 1;
    """,
}


def source(content):
    return textwrap.dedent(content).lstrip('\n')


def write_repo(root, files=FILES):
    root = Path(root)
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source(content), encoding='utf-8')
    return root


@pytest.fixture
def repo(tmp_path):
    return write_repo(tmp_path / 'demo')


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / 'datos'
    monkeypatch.setenv('CORTEX_DATA', str(path))
    monkeypatch.delenv('DATA_PATH', raising=False)
    return path


def by_key(graph):
    return {n['key']: n for n in graph['nodes']}


def edge_set(graph, edges='edges'):
    nodes = graph['nodes']
    return {(nodes[e['a']]['key'], nodes[e['b']]['key'], e['kind']) for e in graph[edges]}


@pytest.fixture(autouse=True)
def lexical_recall(monkeypatch):
    monkeypatch.setenv('CORTEX_EMBED_MODEL', 'off')
