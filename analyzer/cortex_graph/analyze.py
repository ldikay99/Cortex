import math
import os
import random
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import igraph as ig
import leidenalg
import networkx as nx
import numpy as np

from . import brain, bridges, config as project_config, content, deps, generic, gitinfo, importers, langs, overlay
from .common import MAX_FILE_BYTES, MAX_NOTEBOOK_BYTES, Graph, Issues, describe_failure, digest, read_source
from .errors import CortexError
from .pyast import analyze_python, py_module_name
from .tsjs import analyze_ts

SKIP_DIRS = {
    '.git', 'node_modules', '.next', '__pycache__', '.venv', 'venv', 'dist', 'build',
    '.mypy_cache', '.pytest_cache', '.ruff_cache', 'coverage', '.turbo', 'vendor', 'target', 'obj',
    '.gradle', 'Pods', '.build', 'DerivedData', '.dart_tool', '.svelte-kit', '.nuxt', '.output', '.cache',
    '.parcel-cache', 'bower_components', '.tox', '.nox', 'site-packages', '.eggs', 'htmlcov', 'vendored',
    'third_party', 'third-party', 'thirdparty',
}
SKIP_DIR_SUFFIXES = ('.docset', '.xcassets', '.framework', '.bundle', '.egg-info')
MINIFIED_EXTS = {'.js', '.mjs', '.cjs', '.css'}
TEST_DIRS = {'tests', 'test', '__tests__', 'e2e', 'spec', 'specs', 'tst', '__testfixtures__', '__fixtures__', '__mocks__', 'testdata'}
TEST_NAME_RE = re.compile(
    r'(\.(test|spec)\.\w+$)|(_test\.(go|py|rs|lua|c|cc|cpp|rb|ex|exs|dart|ts|js)$)|(_spec\.(rb|lua)$)|(\.(tests?|ts)\.ps1$)'
    r'|((Test|Tests|Spec|(?<=[a-z0-9])IT)\.(java|kt|kts|scala|cs|swift|php|groovy|dart)$)')
CODE_PY = {'.py', '.ipynb'}
CODE_TS = {'.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.mts', '.cts', '.vue', '.svelte'}
DOCS = {'.md', '.mdx', '.rst', '.markdown'}
CONTENT_EXTS = {'.txt', '.jsonl', '.srt', '.vtt', '.pdf', '.docx', '.odt', '.eml', '.mbox', '.ics', '.rtf', '.tsv', '.csv'}
CONTENT_KINDS = {'conversation', 'person', 'concept', 'memory', 'event'}
CODE_EXTS = CODE_PY | CODE_TS | DOCS | langs.EXTS
SKIP_SUFFIXES = ('.d.ts', '.min.js', '.bundle.js', '.min.css', '.map', '.pb.go', '_pb2.py', '.g.dart', '.designer.cs')

EDGE_WEIGHT = {
    'contains': 3.0, 'import': 1.0, 'call': 1.0, 'inherits': 1.5, 'ref': 0.6, 'loads': 1.0, 'tests': 0.4, 'http': 1.2,
    'rpc': 1.2, 'handles': 2.0, 'env': 0.2, 'data': 0.6, 'event': 0.8, 'depends': 0.3, 'cochange': 0.3,
    'mentions': 0.5, 'links': 1.0, 'participant': 1.0, 'about': 1.5, 'from': 1.0, 'supersedes': 0.5, 'related': 0.4, 'attends': 0.8,
    'step': 0.6, 'uses': 1.0,
}
STRUCTURAL_RANK = {'contains': 3, 'handles': 2, 'inherits': 2, 'import': 1}
BRIDGE_KINDS = {'http', 'rpc', 'handles', 'event', 'data', 'env', 'depends', 'step', 'uses'}
NODE_EXTRA = ('route', 'table', 'sig', 'doc', 'end', 'decl', 'vis', 'test', 'version', 'ecosystem', 'scope', 'churn', 'last', 'authors',
              'text', 'category', 'subject', 'attribute', 'value', 'when', 'until', 'valid_from', 'valid_to', 'confidence',
              'origin', 'source', 'msg', 'sensitive', 'aliases', 'email', 'emails', 'tag', 'tags', 'owner', 'count', 'started', 'ended',
              'object', 'negated', 'summary', 'steps', 'rels', 'noted', 'client', 'by')
MAX_COMMUNITIES = 28
MIN_COMMUNITY = 8
MIN_NODES = 40
RESOLUTION = 1.6
MAX_VISIBLE = 70000
NEST = 14.0
LAYOUT_BUDGET = 1.5e9
ORBIT_MIN = 900

KIND_ES = {'module': 'archivo', 'doc': 'documento', 'class': 'clase', 'function': 'función', 'method': 'método',
           'package': 'dependencia', 'variable': 'variable', 'endpoint': 'endpoint', 'topic': 'tema',
           'conversation': 'conversación', 'section': 'sección', 'person': 'persona', 'concept': 'concepto',
           'memory': 'recuerdo', 'event': 'evento', 'component': 'componente', 'flow': 'flujo'}

PALETTE = [
    [1.0, 0.72, 0.5], [0.58, 0.72, 1.0], [0.76, 0.6, 1.0], [1.0, 0.58, 0.66], [0.54, 0.92, 0.84],
    [0.5, 0.84, 1.0], [0.9, 0.62, 0.98], [0.84, 0.96, 0.58], [1.0, 0.7, 0.42], [1.0, 0.52, 0.48],
    [0.62, 1.0, 0.7], [0.98, 0.86, 0.5], [0.7, 0.66, 1.0], [0.56, 0.98, 1.0], [1.0, 0.66, 0.84],
]


def is_test(rel):
    parts = rel.split('/')
    name = parts[-1]
    return (
        bool(TEST_DIRS.intersection(p.lower() for p in parts[:-1]))
        or any(p.endswith(('.Tests', '.Test', '.UnitTests', '.IntegrationTests', 'Tests')) and p[:1].isupper() for p in parts[:-1])
        or name.startswith('test_') or name == 'conftest.py' or TEST_NAME_RE.search(name) is not None
    )


SHEBANG_RE = re.compile(rb'^#![ \t]*(\S+)(?:[ \t]+(?:-\S+[ \t]+)*(\S+))?')
MAX_SCRIPT_BYTES = 256 * 1024


def interpreter(head):
    match = SHEBANG_RE.match(head or b'')
    if not match:
        return None
    prog = match.group(1).decode('utf-8', 'replace').rsplit('/', 1)[-1]
    if prog == 'env' and match.group(2):
        prog = match.group(2).decode('utf-8', 'replace').rsplit('/', 1)[-1]
    return re.sub(r'[\d.]+$', '', prog) or None


def script_route(head):
    prog = interpreter(head)
    if prog in ('python', 'pypy', 'ipython'):
        return 'py'
    if prog in ('node', 'nodejs', 'deno', 'bun', 'ts-node', 'tsx'):
        return 'ts'
    return langs.SHEBANG_LANG.get(prog)


def maybe_script(rel):
    name = rel.rsplit('/', 1)[-1]
    return name not in WRAPPERS and '.' not in name and not name.isupper() and name not in generic.CONFIG_NAMES


def read_head(path):
    try:
        if path.stat().st_size > MAX_SCRIPT_BYTES:
            return b''
        with open(path, 'rb') as fh:
            return fh.read(160)
    except OSError:
        return b''


def minified(path):
    try:
        with open(path, 'rb') as fh:
            head = fh.read(4096)
    except OSError:
        return False
    return any(len(line) > 1000 for line in head.split(b'\n')[:-1]) or (len(head) == 4096 and b'\n' not in head)


WRAPPERS = {'gradlew', 'gradlew.bat', 'mvnw', 'mvnw.cmd', 'sbt', 'sbtw'}


def wanted(rel):
    name = rel.rsplit('/', 1)[-1]
    if name.endswith(SKIP_SUFFIXES) or name in WRAPPERS:
        return False
    ext = os.path.splitext(name)[1]
    return ext in CODE_EXTS or ext.lower() in CONTENT_EXTS or name in langs.NAME_LANG or generic.kind_of(rel) is not None


LANGUAGE_NAMES = {
    '.py': 'Python', '.ipynb': 'Jupyter', '.ts': 'TypeScript', '.tsx': 'TypeScript', '.mts': 'TypeScript',
    '.cts': 'TypeScript', '.js': 'JavaScript', '.jsx': 'JavaScript', '.mjs': 'JavaScript', '.cjs': 'JavaScript',
    '.vue': 'Vue', '.svelte': 'Svelte', '.md': 'Markdown', '.mdx': 'MDX', '.rst': 'reStructuredText', '.go': 'Go',
    '.rs': 'Rust', '.java': 'Java', '.kt': 'Kotlin', '.kts': 'Kotlin', '.scala': 'Scala', '.sc': 'Scala', '.cs': 'C#',
    '.php': 'PHP', '.rb': 'Ruby', '.c': 'C', '.h': 'C/C++', '.cc': 'C++', '.cpp': 'C++', '.cxx': 'C++', '.c++': 'C++',
    '.hh': 'C++', '.hpp': 'C++', '.hxx': 'C++', '.ipp': 'C++', '.swift': 'Swift', '.lua': 'Lua', '.sh': 'Shell',
    '.bash': 'Shell', '.zsh': 'Shell', '.fish': 'Shell', '.dart': 'Dart', '.ex': 'Elixir', '.exs': 'Elixir',
    '.hs': 'Haskell', '.zig': 'Zig', '.ml': 'OCaml', '.mli': 'OCaml', '.jl': 'Julia', '.m': 'Objective-C',
    '.mm': 'Objective-C', '.tf': 'Terraform', '.hcl': 'HCL', '.groovy': 'Groovy', '.gradle': 'Gradle', '.pl': 'Perl',
    '.pm': 'Perl', '.fs': 'F#', '.fsx': 'F#', '.sol': 'Solidity', '.ps1': 'PowerShell', '.psm1': 'PowerShell',
    '.clj': 'Clojure', '.cljs': 'Clojure', '.cljc': 'Clojure', '.erl': 'Erlang', '.hrl': 'Erlang', '.nim': 'Nim',
    '.cr': 'Crystal', '.r': 'R', '.R': 'R', '.elm': 'Elm', '.gleam': 'Gleam', '.cu': 'CUDA', '.cuh': 'CUDA',
    '.yml': 'YAML', '.yaml': 'YAML', '.toml': 'TOML', '.json': 'JSON', '.sql': 'SQL', '.proto': 'Protobuf',
    '.graphql': 'GraphQL', '.gql': 'GraphQL', '.prisma': 'Prisma', '.html': 'HTML', '.htm': 'HTML', '.css': 'CSS',
    '.scss': 'CSS', '.sass': 'CSS', '.less': 'CSS', '.styl': 'CSS', '.xml': 'XML', '.csproj': 'MSBuild',
    '.fsproj': 'MSBuild', '.vbproj': 'MSBuild', '.sln': 'MSBuild', '.ini': 'INI', '.cfg': 'INI', '.conf': 'Config',
    '.properties': 'Properties', '.cmake': 'CMake', '.mk': 'Make', '.bzl': 'Bazel', '.nix': 'Nix',
    '.cshtml': 'Razor', '.razor': 'Razor', '.erb': 'ERB', '.haml': 'Haml', '.slim': 'Slim', '.twig': 'Twig',
    '.liquid': 'Liquid', '.hbs': 'Handlebars', '.handlebars': 'Handlebars', '.j2': 'Jinja', '.jinja': 'Jinja',
    '.jinja2': 'Jinja', '.njk': 'Nunjucks', '.ejs': 'EJS', '.tpl': 'Go template', '.tmpl': 'Go template',
    '.gotmpl': 'Go template', '.bicep': 'Bicep', '.bicepparam': 'Bicep', '.storyboard': 'Interface Builder',
    '.xib': 'Interface Builder', '.cbl': 'COBOL', '.cob': 'COBOL', '.cpy': 'COBOL', '.vb': 'Visual Basic',
    '.bas': 'Visual Basic', '.vbs': 'Visual Basic', '.f': 'Fortran', '.for': 'Fortran', '.f77': 'Fortran',
    '.f90': 'Fortran', '.f95': 'Fortran', '.f03': 'Fortran', '.f08': 'Fortran', '.cls': 'Apex', '.trigger': 'Apex',
    '.apex': 'Apex', '.abap': 'ABAP', '.pks': 'PL/SQL', '.pkb': 'PL/SQL', '.pck': 'PL/SQL', '.pls': 'PL/SQL',
    '.plsql': 'PL/SQL', '.prc': 'PL/SQL', '.fnc': 'PL/SQL', '.dbml': 'DBML',
}
FILE_LANGUAGES = {
    'Dockerfile': 'Docker', 'Containerfile': 'Docker', 'Makefile': 'Make', 'GNUmakefile': 'Make', 'makefile': 'Make',
    'CMakeLists.txt': 'CMake', 'Jenkinsfile': 'Groovy', 'BUILD': 'Bazel', 'BUILD.bazel': 'Bazel', 'WORKSPACE': 'Bazel',
    'Gemfile': 'Ruby', 'Rakefile': 'Ruby', 'Vagrantfile': 'Ruby', 'Podfile': 'Ruby', 'Brewfile': 'Ruby',
    'go.mod': 'Go', 'Cargo.toml': 'TOML', 'requirements.txt': 'Python', 'Pipfile': 'TOML', 'Justfile': 'Make',
}


def language_of(rel):
    name = rel.rsplit('/', 1)[-1]
    if generic.claims(rel) and name.endswith('.blade.php'):
        return 'Blade'
    if name in FILE_LANGUAGES:
        return FILE_LANGUAGES[name]
    if name.startswith(('Dockerfile', 'Containerfile')) or name.endswith('.dockerfile'):
        return 'Docker'
    ext = os.path.splitext(name)[1]
    lang = langs.lang_of(rel)
    family = LANGUAGE_NAMES.get(langs.LANGS[lang]['exts'][0]) if lang else None
    return LANGUAGE_NAMES.get(ext) or LANGUAGE_NAMES.get(ext.lower()) or family or (ext.lstrip('.').upper() if ext else name)


def formats():
    return {
        'exts': sorted(CODE_EXTS | CONTENT_EXTS | generic.CODE | generic.CONFIG | {'.json', '.xml'}),
        'names': sorted(generic.CONFIG_NAMES | set(langs.NAME_LANG)), 'max_script_bytes': MAX_SCRIPT_BYTES,
        'prefixes': list(generic.CONFIG_PREFIXES) + ['requirements'], 'skip_dirs': sorted(SKIP_DIRS), 'skip_suffixes': list(SKIP_SUFFIXES),
        'locks': sorted(generic.LOCKS), 'max_bytes': MAX_FILE_BYTES, 'max_notebook_bytes': MAX_NOTEBOOK_BYTES,
    }


def git_visible(root):
    if not (Path(root) / '.git').exists():
        return None
    try:
        res = subprocess.run(['git', '-C', str(root), 'ls-files', '-co', '--exclude-standard', '-z'], capture_output=True,
                             timeout=60, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
    except (OSError, subprocess.TimeoutExpired):
        return None
    if res.returncode != 0:
        return None
    return {p.decode('utf-8', 'replace') for p in res.stdout.split(b'\0') if p}


def chat_only(rel):
    return rel.lower().endswith('.json') and generic.kind_of(rel) is None


def chat_export(rel, path):
    if not chat_only(rel):
        return False
    try:
        with open(path, 'rb') as fh:
            head = fh.read(64 * 1024)
    except OSError:
        return False
    try:
        return bool(importers.detect(rel, head))
    except Exception:
        return False


def tracked_source_dir(root, dirpath, name, visible):
    """`build/` anidado en el código (p. ej. `app/actions/build/`) que git no ignora: es fuente, no salida de compilación."""
    if name != 'build' or visible is None or os.path.abspath(dirpath) == os.path.abspath(root):
        return False
    prefix = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, '/') + '/'
    return any(p.startswith(prefix) for p in visible)


def list_files(root, exclude=(), skip_tests=False):
    exclude = tuple(e.strip('/') for e in exclude if e.strip('/'))
    visible = git_visible(root)
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if (d not in SKIP_DIRS or tracked_source_dir(root, dirpath, d, visible))
                             and not d.endswith(SKIP_DIR_SUFFIXES))
        for name in sorted(filenames):
            rel = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, '/')
            if visible is not None and rel not in visible:
                continue
            if not wanted(rel) and not (maybe_script(rel) and script_route(read_head(Path(dirpath) / name))) and not chat_export(rel, Path(dirpath) / name):
                continue
            if os.path.splitext(name)[1] in MINIFIED_EXTS and minified(Path(dirpath) / name):
                continue
            if any(rel == e or rel.startswith(e + '/') for e in exclude):
                continue
            if skip_tests and is_test(rel):
                continue
            out.append(rel)
    return out


PATH_RE = re.compile(r'[\w@.\-/+]+\.(?:' + '|'.join(sorted({re.escape(e[1:]) for e in CODE_EXTS | generic.CODE | generic.CONFIG | {'.json', '.sh'}},
                                                         key=len, reverse=True)) + r')\b')
DOTTED_RE = re.compile(r'\b[A-Za-z_]\w*(?:\.\w+)+\b')
KNOWN_EXTS = {e.lower() for e in CODE_EXTS | generic.CODE | generic.CONFIG} | {'.json', '.sh', '.txt', '.lock', '.xml', '.csv'}

FRONTMATTER_RE = re.compile(r'\A(?:\ufeff)?---[ \t]*\r?\n.*?\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)', re.S)


def declare_docs(root, files, g, issues):
    texts = {}
    for rel in files:
        raw = read_source(root, rel, issues)
        if raw is None:
            continue
        text = raw.decode('utf-8', errors='replace')
        body = FRONTMATTER_RE.sub('', text, count=1)
        title = next((line.strip().lstrip('#=*- ').strip() for line in body.splitlines() if line.strip().lstrip('#=*- ').strip()), '')
        g.node(f'd:{rel}', kind='doc', name=rel.rsplit('/', 1)[-1], file=rel, line=1, lang='md', hash=digest(raw),
               end=text.count('\n') + 1, doc=title[:200])
        texts[rel] = text
    return texts


def link_docs(sources, g, all_files):
    by_base = defaultdict(list)
    for f in all_files:
        by_base[f.rsplit('/', 1)[-1]].append(f)
    known = {meta['file'] for meta in g.nodes.values()}
    py_modules = {py_module_name(f): f for f in all_files if f.endswith(('.py', '.ipynb'))}
    for did, (rel, text) in sources.items():
        mentions = set(PATH_RE.findall(text))
        for hit in set(DOTTED_RE.findall(text)):
            if '.' + hit.rsplit('.', 1)[-1] in KNOWN_EXTS:
                continue
            while '.' in hit and hit not in py_modules:
                hit = hit.rsplit('.', 1)[0]
            if hit in py_modules:
                mentions.add(py_modules[hit])
        for hit in mentions:
            hit = hit.lstrip('./')
            nearby = os.path.normpath(os.path.join(os.path.dirname(rel), hit)).replace(os.sep, '/')
            if hit in known:
                targets = [hit]
            elif nearby in known:
                targets = [nearby]
            elif os.path.splitext(hit)[1] in CODE_EXTS and os.path.splitext(hit)[1] not in DOCS:
                same_name = by_base.get(hit.rsplit('/', 1)[-1], [])
                targets = same_name if len(same_name) == 1 else []
            else:
                targets = []
            for target in targets:
                if target != rel:
                    g.edge(did, f'd:{target}' if os.path.splitext(target)[1] in DOCS else f'm:{target}', 'ref')


GENERIC_SEGMENTS = {
    'src', 'lib', 'libs', 'main', 'java', 'kotlin', 'scala', 'groovy', 'app', 'apps', 'internal', 'pkg', 'source',
    'sources', 'crates', 'packages', 'modules', 'code', 'js', 'ts', 'python', 'go', 'csharp', 'dotnet', 'php', 'ruby',
}
DOMAIN_ROOTS = {'com', 'org', 'net', 'io', 'dev', 'me', 'co', 'edu', 'gov'}
CAP_SHARE = 0.25


def meaningful(directory):
    parts = [p for p in directory.split('/') if p]
    out, skip = [], False
    for i, p in enumerate(parts):
        if skip:
            skip = False
            continue
        if p.lower() in DOMAIN_ROOTS and i < len(parts) - 1:
            skip = True
            continue
        if p.lower() not in GENERIC_SEGMENTS:
            out.append(p)
    return out


def covering_dir(files):
    dirs = Counter()
    for f in files:
        parts = f.split('/')[:-1]
        for k in range(1, len(parts) + 1):
            dirs['/'.join(parts[:k])] += 1
    need = len(files) / 2
    found = [d for d, n in dirs.items() if n >= need]
    return max(found, key=lambda d: (d.count('/'), dirs[d], d)) if found else ''


def units(g):
    return {nid: m.get('unit') or nid if m.get('unit') or not m['file'] or m['kind'] in CONTENT_KINDS else ('d:' if m['kind'] in ('doc', 'section') else 'm:') + m['file']
            for nid, m in g.nodes.items()}


def content_name(members, g, degree):
    kinds = Counter(g.nodes[n]['kind'] for n in members)
    if sum(kinds[k] for k in CONTENT_KINDS) * 2 < len(members):
        return None
    named = [n for n in members if g.nodes[n]['kind'] in ('person', 'concept') and not g.nodes[n].get('owner')]
    named = named or [n for n in members if g.nodes[n]['kind'] in ('conversation', 'event')]
    return g.nodes[max(named, key=lambda n: (degree[n], n))]['name'][:60] if named else None


def community_name(members_files, project='(raíz)'):
    files = sorted(set(members_files))
    tops = Counter(f.split('/', 1)[0] for f in files if '/' in f)
    if tops:
        top, n = tops.most_common(1)[0]
        if top.startswith('.') and n * 2 >= len(files):
            return top.lstrip('.')
    code = [f for f in files if os.path.splitext(f)[1] not in DOCS and not generic.kind_of(f)] or files
    directory = covering_dir(code)
    words = meaningful(directory)
    if not words:
        below = Counter()
        for f in code:
            inner = meaningful(os.path.dirname(f[len(directory):].strip('/')))
            if inner:
                below[inner[0]] += 1
        if below and below.most_common(1)[0][1] * 3 >= len(code):
            words = [min(below, key=lambda k: (-below[k], k))]
    label = words[-1] if words else project
    return label.strip('._-').replace('_', ' ').strip() or project


def distinguish(communities, members, g, degree):
    groups = defaultdict(list)
    for c in communities:
        groups[c['name']].append(c)
    for name, same in groups.items():
        if len(same) < 2:
            continue
        dirs = {c['id']: covering_dir(sorted({g.nodes[n]['file'] for n in members[c['id']]})) for c in same}
        shared = os.path.commonpath(list(dirs.values())) if all(dirs.values()) else ''
        taken = set()
        for c in same:
            words = [w for w in meaningful(dirs[c['id']][len(shared):]) if w != name]
            if not words or words[0] in taken:
                hubs = sorted((n for n in members[c['id']] if g.nodes[n]['kind'] == 'module'), key=lambda n: (-degree[n], n))
                stems = [os.path.splitext(g.nodes[n]['name'])[0] for n in hubs]
                words = [x for x in stems if x != name and x not in taken and x.lower() not in ('index', 'mod', 'main', '__init__')]
            extra = words[0] if words else c['hub'].rsplit('.', 1)[0]
            taken.add(extra)
            c['name'] = f'{name} · {extra}'


def common_prefix_len(a, b):
    n = 0
    for x, y in zip(a.split('/'), b.split('/')):
        if x != y or not x:
            break
        n += 1
    return n


def detect_communities(g):
    file_of = units(g)
    files = sorted(set(file_of.values()))
    index = {f: i for i, f in enumerate(files)}
    w = Counter()
    for (a, b, kind), n in sorted(g.edges.items()):
        fa, fb = file_of[a], file_of[b]
        if fa != fb:
            w[(min(index[fa], index[fb]), max(index[fa], index[fb]))] += EDGE_WEIGHT[kind] * n
    graph = ig.Graph(n=len(files), edges=list(w.keys()))
    graph.es['weight'] = list(w.values())
    partition = leidenalg.find_partition(graph, leidenalg.RBConfigurationVertexPartition, weights='weight',
                                         resolution_parameter=RESOLUTION, seed=7)
    comm = list(partition.membership)

    sizes = Counter(comm)
    folder = defaultdict(Counter)
    for f, c in zip(files, comm):
        if sizes[c] > 1:
            folder[os.path.dirname(f[2:])][c] += 1
    for i, f in enumerate(files):
        if sizes[comm[i]] == 1:
            d = os.path.dirname(f[2:])
            while d and not folder.get(d):
                d = os.path.dirname(d)
            if folder.get(d):
                comm[i] = min(folder[d], key=lambda c: (-folder[d][c], c))

    file_nodes = Counter(file_of[nid] for nid in g.nodes)
    groups = defaultdict(list)
    for i, c in enumerate(comm):
        groups[c].append(i)
    nb = defaultdict(Counter)
    for (a, b), wt in w.items():
        ca, cb = comm[a], comm[b]
        if ca != cb:
            nb[ca][cb] += wt
            nb[cb][ca] += wt
    nodes_of = {c: sum(file_nodes[files[i]] for i in idx) for c, idx in groups.items()}
    home = {}

    def home_dir(c):
        if c not in home:
            home[c] = covering_dir([files[i][2:] for i in groups[c]])
        return home[c]

    cap = max(MIN_COMMUNITY * 2, int(len(files) * CAP_SHARE))

    def merge(keep, gone):
        groups[keep].extend(groups.pop(gone))
        nodes_of[keep] += nodes_of.pop(gone)
        for other, wt in nb.pop(gone, Counter()).items():
            nb[other].pop(gone, None)
            if other != keep:
                nb[keep][other] += wt
                nb[other][keep] += wt
        nb[keep].pop(gone, None)
        home.pop(keep, None)
        home.pop(gone, None)

    def nearest_folder(c):
        mine = home_dir(c)
        others = [x for x in groups if x != c]
        return min(others, key=lambda x: (-common_prefix_len(mine, home_dir(x)), len(groups[x]) + len(groups[c]) > cap,
                                          nodes_of[x], x)) if others else None

    def best_neighbour(c):
        links = nb.get(c)
        if not links:
            return None
        fits = [x for x in links if len(groups[x]) + len(groups[c]) <= cap] or list(links)
        return max(fits, key=lambda x: (links[x] / max(1, nodes_of[x]), -x))

    def small(c):
        return len(groups[c]) < MIN_COMMUNITY or nodes_of[c] < MIN_NODES

    lonely = defaultdict(list)
    for c in sorted(groups):
        if not nb.get(c):
            lonely[home_dir(c)].append(c)
    for same in lonely.values():
        for c in same[1:]:
            merge(same[0], c)

    changed = True
    while changed and len(groups) > 1:
        changed = False
        for c in sorted(groups, key=lambda x: (nodes_of[x], x)):
            if c not in groups or not small(c) or len(groups) == 1:
                continue
            target = best_neighbour(c)
            if target is None:
                target = nearest_folder(c)
                if target is not None and len(groups[c]) >= MIN_COMMUNITY:
                    shared = '/'.join(home_dir(c).split('/')[:common_prefix_len(home_dir(c), home_dir(target))])
                    if not meaningful(shared):
                        continue
            if target is None:
                continue
            merge(target, c)
            changed = True
    while len(groups) > MAX_COMMUNITIES:
        best = None
        for a in sorted(nb):
            for b, wt in nb[a].items():
                if a < b and len(groups[a]) + len(groups[b]) <= cap:
                    score = wt / (nodes_of[a] * nodes_of[b])
                    if best is None or score > best[0]:
                        best = (score, a, b)
        if best is None:
            c = min(groups, key=lambda x: (nodes_of[x], x))
            target = nearest_folder(c)
            merge(target, c)
        else:
            merge(best[1], best[2])
    for c, idx in groups.items():
        for i in idx:
            comm[i] = c

    hidden = defaultdict(set)
    for f, c in zip(files, comm):
        top = f[2:].split('/', 1)[0]
        if top.startswith('.') and '/' in f[2:]:
            hidden[top].add(c)
    for top, cs in sorted(hidden.items()):
        owned = sorted(c for c in cs
                       if sum(1 for f, x in zip(files, comm) if x == c and f[2:].startswith(top + '/')) * 2 >= Counter(comm)[c])
        for c in owned[1:]:
            comm[:] = [owned[0] if x == c else x for x in comm]

    order = sorted(Counter(comm).items(), key=lambda kv: (-kv[1], kv[0]))
    remap = {c: k for k, (c, _) in enumerate(order)}
    file_comm = {f: remap[c] for f, c in zip(files, comm)}
    return {nid: file_comm[file_of[nid]] for nid in g.nodes}


def spread_directions(ncomm, radius, community_graph, rng):
    dirs = rng.normal(size=(ncomm, 3))
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    wmax = max((d['weight'] for _, _, d in community_graph.edges(data=True)), default=1)
    size = np.array([radius[j] for j in range(ncomm)])
    for _ in range(300):
        force = np.zeros_like(dirs)
        for i in range(ncomm):
            diff = dirs[i] - dirs
            dist2 = (diff ** 2).sum(axis=1) + 1e-3
            force[i] = (diff * (size * radius[i] / dist2 ** 1.5)[:, None]).sum(axis=0)
        for a, b, d in community_graph.edges(data=True):
            pull = (dirs[b] - dirs[a]) * 0.4 * d['weight'] / wmax
            force[a] += pull
            force[b] -= pull
        dirs += force * 0.002
        dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    return dirs


def pack_centers(dirs, radius, rng):
    ncomm = len(dirs)
    centers = np.array([dirs[c] * (NEST + radius[c] * 2.5) for c in range(ncomm)])
    for it in range(600):
        moved = False
        if it < 500:
            centers *= 0.985
        for i in range(ncomm):
            d = np.linalg.norm(centers[i])
            need = NEST + radius[i]
            if d < need:
                centers[i] = centers[i] / d * need if d else rng.normal(size=3) * need
                moved = True
            for j in range(i + 1, ncomm):
                v = centers[j] - centers[i]
                dist = np.linalg.norm(v) or 1e-3
                need = (radius[i] + radius[j]) * 1.12 + 3
                if dist < need:
                    push = (need - dist) / 2 * v / dist
                    centers[i] -= push
                    centers[j] += push
                    moved = True
        if not moved and it >= 500:
            break
    return centers


def force_layout(count, pairs, rng, niter):
    if count == 1:
        return np.zeros((1, 3))
    graph = ig.Graph(n=count, edges=list(pairs))
    start = rng.uniform(-1, 1, size=(count, 3)) * math.sqrt(count)
    ig.set_random_number_generator(random.Random(int(rng.integers(1 << 30))))
    try:
        coords = graph.layout_fruchterman_reingold_3d(weights=list(pairs.values()) or None, niter=niter, seed=start.tolist())
    finally:
        ig.set_random_number_generator(random)
    return np.array(coords.coords, dtype=float)


def sphere_points(count):
    i = np.arange(count) + 0.5
    phi = np.arccos(1 - 2 * i / count)
    theta = math.pi * (1 + 5 ** 0.5) * i
    return np.stack([np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)], axis=1)


def layout_sizes(nodes, file_of):
    return len(nodes) if len(nodes) <= ORBIT_MIN else len({file_of[n] for n in nodes})


def local_layout(nodes, adj, rng, file_of, niter):
    if len(nodes) <= ORBIT_MIN:
        index = {n: i for i, n in enumerate(nodes)}
        pairs = Counter()
        for a in nodes:
            for b, wt in adj[a].items():
                if b in index and a != b:
                    pairs[(min(index[a], index[b]), max(index[a], index[b]))] += wt
        return force_layout(len(nodes), pairs, rng, niter)
    groups = defaultdict(list)
    for i, n in enumerate(nodes):
        groups[file_of[n]].append(i)
    keys = sorted(groups)
    findex = {f: i for i, f in enumerate(keys)}
    pairs = Counter()
    for a in nodes:
        for b, wt in adj[a].items():
            fa, fb = findex[file_of[a]], findex.get(file_of.get(b))
            if fb is not None and fa != fb:
                pairs[(min(fa, fb), max(fa, fb))] += wt
    centers = force_layout(len(keys), pairs, rng, niter)
    spread = np.linalg.norm(centers - centers.mean(axis=0), axis=1)
    step = (np.percentile(spread, 90) or 1) / max(1.0, len(keys) ** (1 / 3))
    biggest = max(len(v) for v in groups.values())
    out = np.zeros((len(nodes), 3))
    for f, idx in groups.items():
        center = centers[findex[f]]
        heads = [i for i in idx if nodes[i][:2] in ('m:', 'd:')]
        rest = [i for i in idx if i not in heads]
        for i in heads:
            out[i] = center
        if rest:
            radius = step * (0.25 + 0.55 * (len(rest) / biggest) ** (1 / 3))
            shell = sphere_points(len(rest)) * radius * rng.uniform(0.75, 1.0, size=(len(rest), 1))
            out[rest] = center + shell
    return out


def layout(g, community, seed=7):
    rng = np.random.default_rng(seed)
    members = defaultdict(list)
    for nid, c in community.items():
        members[c].append(nid)
    ncomm = len(members)
    community_graph = nx.Graph()
    community_graph.add_nodes_from(range(ncomm))
    for (a, b, kind), n in g.edges.items():
        ca, cb = community[a], community[b]
        if ca != cb:
            prev = community_graph.get_edge_data(ca, cb, {}).get('weight', 0)
            community_graph.add_edge(ca, cb, weight=prev + EDGE_WEIGHT[kind] * n)
    radius = {c: max(4.5, 1.05 * len(m) ** (1 / 3) * 1.25) for c, m in members.items()}
    centers = pack_centers(spread_directions(ncomm, radius, community_graph, rng), radius, rng)

    adj = defaultdict(Counter)
    for (a, b, kind), n in g.edges.items():
        if community[a] == community[b]:
            adj[a][b] += EDGE_WEIGHT[kind] * n
    file_of = units(g)
    work = sum(layout_sizes(nodes, file_of) ** 2 for nodes in members.values())
    niter = int(min(600, max(40, LAYOUT_BUDGET / max(1, work))))
    node_pos = {}
    for c, nodes in members.items():
        arr = local_layout(nodes, adj, np.random.default_rng(seed + c), file_of, niter)
        arr -= arr.mean(axis=0)
        r90 = np.percentile(np.linalg.norm(arr, axis=1), 90) or 1
        arr = arr / r90 * radius[c] + rng.normal(scale=0.15, size=arr.shape)
        for n, p in zip(nodes, arr):
            node_pos[n] = centers[c] + p
    return centers, radius, node_pos, members


def rounded(vector):
    return [round(float(x), 3) for x in vector]


def mark_tests(g):
    tested = {nid for nid, m in g.nodes.items() if is_test(m['file'])}
    for nid in tested:
        g.nodes[nid]['test'] = True
    for (a, b, kind), n in list(g.edges.items()):
        if kind == 'call' and a in tested and b not in tested:
            del g.edges[(a, b, kind)]
            g.edges[(a, b, 'tests')] += n


def apply_git(g, info):
    if not info:
        return
    by_file = {}
    for nid, m in g.nodes.items():
        if m['kind'] in ('module', 'doc'):
            by_file[m['file']] = nid
    for rel, meta in (info.get('files') or {}).items():
        nid = by_file.get(rel)
        if nid:
            g.nodes[nid].update({k: v for k, v in meta.items() if k in ('churn', 'last', 'authors')})
    for a, b, w in info.get('cochange') or []:
        if a in by_file and b in by_file:
            g.edges[(by_file[a], by_file[b], 'cochange')] += int(w)


def reuse_layout(g, community, previous):
    known = {n['key']: n for n in previous.get('nodes', [])}
    if not g.nodes or sum(1 for nid in g.nodes if nid in known) < 0.9 * len(g.nodes):
        return None
    members = defaultdict(list)
    for nid, c in community.items():
        members[c].append(nid)
    node_pos = {}
    for nid in g.nodes:
        if nid in known:
            node_pos[nid] = np.array(known[nid]['pos'], dtype=float)
    centers, radius = {}, {}
    for c, nodes in members.items():
        pts = np.array([node_pos[n] for n in nodes if n in node_pos]) if any(n in node_pos for n in nodes) else None
        if pts is None:
            return None
        centers[c] = pts.mean(axis=0)
        radius[c] = max(4.5, float(np.percentile(np.linalg.norm(pts - centers[c], axis=1), 90)) if len(pts) > 1 else 4.5)
    rng = np.random.default_rng(13)
    file_pos = {g.nodes[n]['file']: node_pos[n] for n in node_pos if g.nodes[n]['kind'] in ('module', 'doc')}
    for nid in sorted(g.nodes):
        if nid not in node_pos:
            anchor = file_pos.get(g.nodes[nid]['file'])
            base = anchor if anchor is not None else centers[community[nid]]
            node_pos[nid] = base + rng.normal(scale=0.6, size=3)
    order = sorted(members)
    return ([centers[c] for c in order], np.array([radius[c] for c in order]), node_pos,
            {i: members[c] for i, c in enumerate(order)}) if order == list(range(len(order))) else None


def analyze(root, project=None, exclude=(), skip_tests=False, git=True, previous=None, scip=None, memories=None, overlay_ops=None):
    root = Path(root)
    if not root.is_dir():
        raise CortexError(f'no existe la carpeta «{root}»')
    settings = project_config.load(root)
    exclude = tuple(exclude) + tuple(settings.get('exclude') or ())
    files = [f for f in list_files(root, exclude, skip_tests) if not project_config.ignored(settings, f)]
    scripts = {f: script_route(read_head(root / f)) for f in files if maybe_script(f) and not langs.lang_of(f)}
    scripts = {f: r for f, r in scripts.items() if r}
    py = [f for f in files if os.path.splitext(f)[1] in CODE_PY or scripts.get(f) == 'py']
    ts = [f for f in files if os.path.splitext(f)[1] in CODE_TS or scripts.get(f) == 'ts']
    md = [f for f in files if os.path.splitext(f)[1] in DOCS]
    overrides = {f: r for f, r in scripts.items() if r not in ('py', 'ts')}
    script_names = {f: {'py': 'Python', 'ts': 'JavaScript'}.get(r) or LANGUAGE_NAMES.get(langs.LANGS[r]['exts'][0], r)
                    for f, r in scripts.items()}
    other = [f for f in files if (langs.lang_of(f) or f in overrides) and not generic.claims(f)]
    rest = [f for f in files if generic.claims(f) or (os.path.splitext(f)[1] not in CODE_EXTS and os.path.splitext(f)[1].lower() not in CONTENT_EXTS
                                                      and not langs.lang_of(f) and f not in scripts and not chat_only(f))]
    texts_in = [f for f in files if os.path.splitext(f)[1].lower() in CONTENT_EXTS | DOCS | {'.json'}]
    issues = Issues()
    g = Graph()
    texts = declare_docs(root, md, g, issues)
    analyze_python(root, py, g, issues)
    analyze_ts(root, ts, g, issues)
    langs.analyze_languages(root, other, g, issues, read_source, describe_failure, digest, overrides, skip_tests=skip_tests)
    sources, tables = generic.analyze_generic(root, rest, g, issues, read_source, digest)
    sources.update({f'd:{rel}': (rel, text) for rel, text in texts.items()})
    link_docs(sources, g, files)
    generic.link_tables(g, tables)
    deps.link_dependencies(root, files, g, issues, read_source)
    bridges.link_bridges(root, files, g, issues, read_source)
    gone = brain.forgotten(project) if project else set()
    records = {r['id']: r for r in content.link_content(root, texts_in, g, issues, read_source) or () if r['id'] not in gone}
    records.update({r['id']: r for r in memories or ()})
    if records:
        brain.link_memories(g, [records[k] for k in sorted(records)])
    files += overlay.link_overlay(g, overlay_ops, issues, root, exclude)
    if scip:
        from . import scip as scip_index
        scip_index.apply_scip(g, root, scip)
    if not skip_tests:
        mark_tests(g)
    if git:
        apply_git(g, gitinfo.collect(root, files))
    for nid, meta in g.nodes.items():
        if not meta.get('hash'):
            meta['hash'] = digest(f"{nid}|{meta.get('version', '')}|{meta.get('route', '')}")
    if not g.nodes:
        raise CortexError('no hay código, documentos, notas, conversaciones ni recuerdos para analizar en esa carpeta')

    g.edges = Counter(dict(sorted(g.edges.items())))
    community = detect_communities(g)
    reused = reuse_layout(g, community, previous) if previous else None
    centers, radius, node_pos, members = reused or layout(g, community)

    degree = Counter()
    for (a, b, _), n in g.edges.items():
        degree[a] += n
        degree[b] += n

    ids = {nid: i for i, nid in enumerate(g.nodes)}
    project_name = project or root.resolve().name
    communities = []
    for c in range(len(centers)):
        hub = max((n for n in members[c] if g.nodes[n]['kind'] in ('module', 'doc')), key=lambda n: (degree[n], n), default=None)
        topical = content_name(members[c], g, degree) or overlay.label(members[c], g, degree)
        hub = hub if hub and not topical else max(members[c], key=lambda n: (degree[n], n))
        communities.append({
            'id': c, 'name': topical or community_name([g.nodes[n]['file'] for n in members[c]], project_name), 'hub': g.nodes[hub]['name'],
            'size': len(members[c]), 'center': rounded(centers[c]), 'radius': round(float(radius[c]), 3),
            'color': PALETTE[c % len(PALETTE)],
        })
    distinguish(communities, members, g, degree)

    nodes = []
    for nid, meta in g.nodes.items():
        nodes.append({
            'id': ids[nid], 'key': nid, 'c': community[nid], 'kind': meta['kind'], 'name': meta['name'],
            'file': meta['file'], 'line': meta['line'], 'deg': degree[nid], 'pos': rounded(node_pos[nid]),
            **{k: meta[k] for k in NODE_EXTRA if meta.get(k) not in (None, '', False)},
            'hash': meta.get('hash', ''),
        })
    for (a, b, kind) in g.edges:
        if kind == 'contains':
            nodes[ids[b]]['parent'] = ids[a]
    edges = [{'a': ids[a], 'b': ids[b], 'kind': kind, 'w': n} for (a, b, kind), n in g.edges.items()]
    visible = cap_visible(visible_edges(g, community, ids))
    return {
        'project': project or root.resolve().name,
        'stats': {
            'files': len(files), 'nodes': len(nodes), 'edges': len(edges), 'communities': len(communities),
            'kinds': dict(Counter(n['kind'] for n in nodes)), 'edge_kinds': dict(Counter(e['kind'] for e in edges)),
            'languages': dict(Counter(script_names.get(n['file']) or language_of(n['file'])
                                      for n in nodes if n['kind'] in ('module', 'doc')).most_common()),
            'tests': not skip_tests, 'excluded': list(exclude), 'warnings': issues.items, 'warnings_total': issues.total,
        },
        'communities': communities, 'nodes': nodes, 'edges': edges, 'visible': visible,
    }


def visible_edges(g, community, ids):
    file_node = {m['file']: nid for nid, m in g.nodes.items() if m['kind'] in ('module', 'doc')}
    keep = {}
    cross = defaultdict(Counter)
    bridges_out = []
    for (a, b, kind), n in g.edges.items():
        fa, fb = g.nodes[a]['file'], g.nodes[b]['file']
        if kind in BRIDGE_KINDS:
            if kind not in ('depends', 'env') or community[a] == community[b]:
                bridges_out.append({'a': ids[a], 'b': ids[b], 'kind': kind, 'w': n})
            continue
        if kind == 'cochange':
            continue
        if kind in ('call', 'tests'):
            if fa == fb:
                continue
            a, b, kind = file_node.get(fa, a), file_node.get(fb, b), 'tests' if kind == 'tests' else 'import'
        if community[a] != community[b]:
            pair = tuple(sorted((community[a], community[b])))
            cross[pair][(file_node.get(fa, a), file_node.get(fb, b))] += n
            continue
        key = (min(a, b), max(a, b))
        if key not in keep or kind != 'import':
            keep[key] = (a, b, kind, keep.get(key, (0, 0, 0, 0))[3] + n)
    out = [{'a': ids[a], 'b': ids[b], 'kind': kind, 'w': n} for a, b, kind, n in keep.values()]
    for links in cross.values():
        total = sum(links.values())
        for (a, b), n in links.most_common(1 + (total >= 4) + (total >= 12)):
            out.append({'a': ids[a], 'b': ids[b], 'kind': 'import', 'w': n})
    return bridges_out + out


def cap_visible(edges, limit=MAX_VISIBLE):
    if len(edges) <= limit:
        return edges
    ranked = sorted(range(len(edges)), key=lambda i: (STRUCTURAL_RANK.get(edges[i]['kind'], 0), edges[i]['w']), reverse=True)
    chosen = set(ranked[:limit])
    return [e for i, e in enumerate(edges) if i in chosen]


def export_json(out):
    comm_files = defaultdict(list)
    for n in out['nodes']:
        if n['kind'] in ('module', 'doc'):
            comm_files[n['c']].append(n['file'])
    return {
        'project': out['project'],
        'generator': 'Córtex · análisis estático determinista (AST + Leiden), sin IA',
        'stats': out['stats'],
        'communities': [{'id': c['id'], 'name': c['name'], 'hub': c['hub'], 'size': c['size'], 'files': sorted(comm_files[c['id']])}
                        for c in out['communities']],
        'version': out.get('version'),
        'history': out.get('history', []),
        'changes': out.get('changes'),
        'nodes': [{k: n[k] for k in ('id', 'key', 'kind', 'name', 'file', 'line', 'c', 'deg', 'parent', 'route', 'table', 'hash', 'status') if k in n}
                  for n in out['nodes']],
        'edges': [{'source': e['a'], 'target': e['b'], 'kind': e['kind'], 'weight': e['w']} for e in out['edges']],
    }


def export_markdown(out):
    nodes, edges, comms = out['nodes'], out['edges'], out['communities']
    st = out['stats']
    cname = {c['id']: c['name'] for c in comms}
    children = defaultdict(list)
    for n in nodes:
        if 'parent' in n:
            children[n['parent']].append(n)
    imports = defaultdict(set)
    imported_by = Counter()
    cross = Counter()
    for e in edges:
        a, b = nodes[e['a']], nodes[e['b']]
        if a['c'] != b['c']:
            cross[(a['c'], b['c'])] += e['w']
        if e['kind'] == 'import' and a['kind'] == 'module' and b['kind'] == 'module':
            imports[a['file']].add(b['file'])
            imported_by[b['file']] += 1

    def all_symbols(n):
        found = []
        for child in children[n['id']]:
            found.append(child)
            found.extend(all_symbols(child))
        return found

    lines = []
    add = lines.append
    add(f"# Grafo de conocimiento · {out['project']}\n")
    langs_line = ', '.join(f'{k} ({v})' for k, v in list((st.get('languages') or {}).items())[:12])
    add(f"> Generado por Córtex: análisis estático determinista (árboles de sintaxis de cada lenguaje, comunidades con Leiden), sin IA. "
        f"{st['files']} archivos · {st['nodes']} nodos · {st['edges']} relaciones · {st['communities']} comunidades."
        f"{' Lenguajes: ' + langs_line + '.' if langs_line else ''}"
        f"{' Tests excluidos.' if not st.get('tests', True) else ''}"
        f"{' Carpetas omitidas: ' + ', '.join(f'`{e}`' for e in st['excluded']) + '.' if st.get('excluded') else ''}\n")
    add('## Cómo usar este archivo\n')
    add('Es un mapa del código para un asistente. Las **comunidades** son subsistemas detectados por cómo se conectan los archivos '
        '(imports, llamadas, herencia). Antes de leer código, ubica aquí dónde vive cada cosa: cada símbolo trae `archivo:línea`. '
        'Los «nodos más conectados» son los puntos de los que más depende el resto: cambiarlos tiene más impacto.\n')

    hist = out.get('history') or []
    if hist:
        add('## Versiones\n')
        add('| versión | fecha | origen | commit | archivos | nodos | nuevos | modificados | eliminados |')
        add('|---|---|---|---|---|---|---|---|---|')
        for h in hist:
            origin = h.get('origin') or {}
            source = origin.get('url') or origin.get('type') or '—'
            commit = ((h.get('commit') or {}).get('sha') or '')[:8] or '—'
            ch = h.get('changes', {})
            add(f"| v{h['v']} | {h['date'][:16].replace('T', ' ')} | {source} | {commit} | {h['stats']['files']} | {h['stats']['nodes']} | "
                f"{ch.get('added', 0)} | {ch.get('modified', 0)} | {ch.get('removed', 0)} |")
        add('')
    changes = out.get('changes') or {}
    if len(hist) > 1 and any(changes.get(k) for k in ('added', 'modified', 'removed')):
        by_key = {n['key']: n for n in nodes}
        add(f"## Cambios desde la versión anterior (v{hist[-2]['v']} → v{hist[-1]['v']})\n")
        for title, keys in (('Nuevos', changes.get('added', [])), ('Modificados', changes.get('modified', []))):
            if keys:
                add(f'**{title}** ({len(keys)}):')
                for k in keys[:80]:
                    n = by_key[k]
                    add(f"- {KIND_ES.get(n['kind'], n['kind'])} **{n['name']}** · `{n['file']}:{n['line']}`")
                if len(keys) > 80:
                    add(f'- … y {len(keys) - 80} más')
                add('')
        if changes.get('removed'):
            add(f"**Eliminados** ({len(changes['removed'])}):")
            for n in changes['removed'][:80]:
                add(f"- {KIND_ES.get(n['kind'], n['kind'])} **{n['name']}** · `{n['file']}`")
            add('')

    add('## Comunidades\n')
    add('| # | comunidad | nodos | archivos | archivo central | se conecta sobre todo con |')
    add('|---|---|---|---|---|---|')
    for c in comms:
        files = [n for n in nodes if n['c'] == c['id'] and n['kind'] in ('module', 'doc')]
        links = Counter()
        for (a, b), w in cross.items():
            if a == c['id']:
                links[b] += w
            elif b == c['id']:
                links[a] += w
        top = ', '.join(cname[x] for x, _ in links.most_common(3)) or '—'
        add(f"| {c['id']} | **{c['name']}** | {c['size']} | {len(files)} | `{c['hub']}` | {top} |")
    add('')

    add('## Nodos más conectados\n')
    for n in sorted(nodes, key=lambda n: -n['deg'])[:30]:
        add(f"- **{n['name']}** · {KIND_ES.get(n['kind'], n['kind'])} · `{n['file']}:{n['line']}` · {n['deg']} conexiones · {cname[n['c']]}")
    add('')

    add('## Dependencias entre comunidades\n')
    for (a, b), w in cross.most_common(30):
        add(f'- {cname[a]} → {cname[b]} ({w})')
    add('')

    routes = [n for n in nodes if n.get('route')]
    if routes:
        add('## Rutas de la API\n')
        for n in sorted(routes, key=lambda n: n['route'].split(' ', 1)[-1]):
            add(f"- `{n['route']}` → {n['name']} · `{n['file']}:{n['line']}`")
        add('')
    tables = [n for n in nodes if n.get('table')]
    if tables:
        add('## Tablas de base de datos\n')
        for n in sorted(tables, key=lambda n: n['table']):
            add(f"- `{n['table']}` → {n['name']} · `{n['file']}:{n['line']}`")
        add('')

    docs = [n for n in nodes if n['kind'] == 'doc']
    doc_refs = defaultdict(list)
    for e in edges:
        if e['kind'] == 'ref':
            doc_refs[nodes[e['a']]['file']].append(nodes[e['b']]['file'])
    if docs:
        add('## Documentos\n')
        for n in sorted(docs, key=lambda n: -n['deg'])[:60]:
            refs = sorted(set(doc_refs[n['file']]))
            tail = f" · menciona: {', '.join(f'`{r}`' for r in refs[:8])}{' …' if len(refs) > 8 else ''}" if refs else ''
            add(f"- `{n['file']}`{tail}")
        add('')

    add('## Detalle por comunidad\n')
    for c in comms:
        add(f"### {c['name']} · {c['size']} nodos\n")
        files = sorted((n for n in nodes if n['c'] == c['id'] and n['kind'] == 'module'), key=lambda n: -n['deg'])
        for f in files:
            syms = all_symbols(f)
            classes = [s['name'] for s in syms if s['kind'] == 'class']
            funcs = [s['name'] for s in syms if s['kind'] in ('function', 'method')]
            parts = [f"`{f['file']}` · {f['deg']} conexiones"]
            if imported_by[f['file']]:
                parts.append(f"lo importan {imported_by[f['file']]}")
            add('- ' + ' · '.join(parts))
            if classes:
                add(f"  - clases: {', '.join(classes[:15])}{' …' if len(classes) > 15 else ''}")
            if funcs:
                add(f"  - funciones: {', '.join(funcs[:20])}{f' … (+{len(funcs) - 20})' if len(funcs) > 20 else ''}")
            deps = sorted(imports[f['file']])
            if deps:
                add(f"  - importa: {', '.join(f'`{d}`' for d in deps[:10])}{' …' if len(deps) > 10 else ''}")
        add('')
    return '\n'.join(lines)
