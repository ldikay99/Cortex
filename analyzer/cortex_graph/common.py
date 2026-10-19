import hashlib
import json
from collections import Counter

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_NOTEBOOK_BYTES = 40 * 1024 * 1024
MAX_WARNINGS = 50


def digest(text):
    if isinstance(text, str):
        text = text.encode('utf-8', errors='replace')
    return hashlib.sha1(text).hexdigest()[:12]


class Issues:
    def __init__(self):
        self.items = []
        self.total = 0

    def add(self, rel, message):
        self.total += 1
        if len(self.items) < MAX_WARNINGS:
            self.items.append({'file': rel, 'error': message})


def describe_failure(exc):
    if isinstance(exc, SyntaxError):
        return f'sintaxis inválida en la línea {exc.lineno}' if exc.lineno else 'sintaxis inválida'
    if isinstance(exc, RecursionError):
        return 'el código está anidado demasiado profundo para analizarlo'
    if isinstance(exc, OSError):
        return 'no se pudo leer el archivo'
    if isinstance(exc, json.JSONDecodeError):
        return 'el notebook no es un JSON válido'
    if isinstance(exc, ValueError):
        return 'el archivo contiene bytes que no son texto'
    return f'no se pudo analizar ({type(exc).__name__})'


def read_source(root, rel, issues):
    path = root / rel
    limit = MAX_NOTEBOOK_BYTES if rel.endswith('.ipynb') else MAX_FILE_BYTES
    try:
        if path.stat().st_size > limit:
            issues.add(rel, f'archivo de más de {limit // (1024 * 1024)} MB: se omitió')
            return None
        return path.read_bytes().replace(b'\r\n', b'\n')
    except OSError as exc:
        issues.add(rel, describe_failure(exc))
        return None


class Graph:
    def __init__(self):
        self.nodes = {}
        self.edges = Counter()
        self.externals = []
        self.seen_externals = set()

    def external(self, mid, spec, lang):
        key = (mid, spec, lang)
        if spec and key not in self.seen_externals:
            self.seen_externals.add(key)
            self.externals.append(key)

    def node(self, nid, **meta):
        if nid not in self.nodes:
            self.nodes[nid] = meta
        elif meta.get('hash') and meta['hash'] != self.nodes[nid].get('hash'):
            self.nodes[nid]['hash'] = digest(self.nodes[nid].get('hash', '') + meta['hash'])
        return nid

    def edge(self, a, b, kind):
        if a != b and a in self.nodes and b in self.nodes:
            self.edges[(a, b, kind)] += 1
