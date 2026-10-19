import os
import re
from collections import defaultdict
from pathlib import Path

CODE = {
    '.clj', '.cljs', '.cljc', '.edn', '.erl', '.hrl', '.nim', '.cr', '.d', '.pas', '.pp', '.adb', '.ads',
    '.f', '.f90', '.f95', '.f03', '.for', '.cob', '.cbl', '.rkt', '.scm', '.ss', '.lisp', '.lsp', '.el', '.tcl',
    '.awk', '.vb', '.vbs', '.bas', '.asm', '.s', '.sv', '.v', '.vhd', '.vhdl', '.r', '.R', '.gd', '.hx', '.purs',
    '.idr', '.agda', '.lean', '.coffee', '.elm', '.gleam', '.odin', '.mojo', '.cu', '.cuh', '.glsl', '.hlsl',
    '.wgsl', '.frag', '.vert', '.comp', '.move', '.cairo', '.vy', '.ino', '.nix', '.raku', '.rakumod', '.sml',
    '.fish', '.bat', '.cmd', '.applescript', '.ahk', '.prg', '.abap', '.apex', '.cls', '.st', '.pde', '.qml',
}
CONFIG = {
    '.yml', '.yaml', '.toml', '.ini', '.cfg', '.conf', '.properties', '.sql', '.proto', '.graphql', '.gql',
    '.prisma', '.html', '.htm', '.css', '.scss', '.sass', '.less', '.styl', '.cmake', '.mk', '.bzl', '.hbs',
    '.ejs', '.njk', '.jinja', '.jinja2', '.j2', '.twig', '.liquid', '.mustache', '.csproj', '.fsproj', '.vbproj',
    '.sln', '.dockerfile', '.thrift', '.avsc', '.smithy', '.cue', '.rego', '.http', '.rest',
}
CONFIG_NAMES = {
    'Dockerfile', 'Containerfile', 'Makefile', 'GNUmakefile', 'makefile', 'CMakeLists.txt', 'Jenkinsfile',
    'Procfile', 'Justfile', 'justfile', 'BUILD', 'BUILD.bazel', 'WORKSPACE', 'MODULE.bazel', 'Gemfile', 'Rakefile',
    'Vagrantfile', 'Podfile', 'Brewfile', 'Tiltfile', 'Earthfile', 'Caddyfile', 'nginx.conf', 'package.json',
    'composer.json', 'deno.json', 'deno.jsonc', 'angular.json', 'nx.json', 'turbo.json', 'vercel.json',
    'firebase.json', 'app.json', 'manifest.json', 'lerna.json', 'project.json', 'pom.xml', 'AndroidManifest.xml',
    'web.config', 'openapi.json', 'swagger.json', 'pubspec.yaml', 'mix.exs', 'go.mod', 'Cargo.toml',
    'Package.swift', 'build.sbt', 'requirements.txt', 'Pipfile', 'setup.cfg', 'tox.ini', 'serverless.yml',
}
CONFIG_PREFIXES = ('Dockerfile.', 'Containerfile.', 'docker-compose', 'compose.')
LOCKS = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'Cargo.lock', 'poetry.lock', 'composer.lock',
    'Gemfile.lock', 'go.sum', 'Pipfile.lock', 'uv.lock', 'bun.lockb', 'flake.lock', 'pubspec.lock', 'mix.lock',
}
DATA_DIRS = {'locales', 'locale', 'i18n', 'l10n', 'translations', 'lang', 'fixtures', '__snapshots__', 'testdata'}
LANG_CODES = set(
    'af am ar az be bg bn bs ca cs cy da de el en eo es et eu fa fi fr ga gl gu he hi hr hu hy id is it ja ka kk '
    'km kn ko ky lo lt lv mk ml mn mr ms my nb ne nl nn no pa pl ps pt ro ru si sk sl sq sr sv sw ta te th tl tr '
    'uk ur uz vi zh zu'.split())
BUNDLE_RE = re.compile(r'_([a-z]{2,3})(?:[_-][A-Za-z0-9]{2,8})*$')
SAMPLE_DIRS = {'examples', 'example', 'samples', 'sample', 'demo', 'demos', '__tests__', 'bench', 'benchmarks', 'playground'}
SOURCE_DIRS = {'src', 'lib', 'app'}
SOURCE_EXTS = {'.js', '.mjs', '.cjs', '.ts', '.mts', '.cts', '.jsx', '.tsx', '.vue', '.svelte'}
MAX_CONFIG_BYTES = 512 * 1024
NAME = r'[A-Za-z_][\w$]*'

CLASS_RE = re.compile(
    r'^[ \t]*\(?(?:(?:export|public|private|protected|abstract|final|sealed|data|pub|static|partial|open)[ \t]+)*'
    r'(class|struct|interface|trait|module|defmodule|record|enum|protocol|object|contract|library|union|type)'
    r'[ \t]+([A-Za-z_][\w.$:]*)', re.M)
FUNC_RE = re.compile(
    r'^[ \t]*\(?(?:(?:export|public|private|protected|static|async|pub|local|inline|extern|override|virtual)[ \t]+)*'
    r'(def|defn|defn-|defp|defun|defmacro|define|fn|func|function|fun|proc|procedure|sub|method|let|val|task)'
    r'[ \t]+\(?([A-Za-z_][\w.$!?*<>=-]*)', re.M)
IMPORT_RE = re.compile(
    r'^[ \t]*\(?(?:import|require|use|include|using|load|source|from|open|:require|#include|@import|@use)\b(.*)$', re.M)
CALL_RE = re.compile(r'(?:\(|\b)([A-Za-z_][\w.$!?-]*)[ \t]*\(')
LISP_CALL_RE = re.compile(r'\(([A-Za-z_][\w.$!?*<>=/-]*)[\s)]')
QUOTED_RE = re.compile(r'["\']([^"\'\s]+)["\']')
BARE_RE = re.compile(r'[A-Za-z_][\w]*(?:(?:\.|::|/)[A-Za-z_][\w]*)+|[A-Za-z_][\w]*')
LISP = {'.clj', '.cljs', '.cljc', '.edn', '.rkt', '.scm', '.ss', '.lisp', '.lsp', '.el'}
ERLANG = {'.erl', '.hrl'}
CLOJURE = {'.clj', '.cljs', '.cljc'}

ERL_MASK_RE = re.compile(r'%[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\$\\?.', re.S)
ERL_ATTRIBUTE_RE = re.compile(r'^-.*?\.(?=\s|\Z)', re.M | re.S)
ERL_END_RE = re.compile(r'\.(?=\s|\Z)')
ERL_DEF_RE = re.compile(r'^([a-z][\w@]*)[ \t]*\(', re.M)
ERL_ATTR_RE = re.compile(
    r'^-[ \t]*(module|behaviour|behavior|include|include_lib)[ \t]*\([ \t]*(?:"([^"\n]+)"|\'?([\w@.]+)\'?)[ \t]*\)',
    re.M)
ERL_REMOTE_RE = re.compile(r'(?<![\w@?#:\'.])([a-z][\w@]*|\?MODULE)[ \t]*:[ \t]*([a-z][\w@]*)[ \t]*\(')
ERL_FUN_RE = re.compile(r'\bfun[ \t]+(?:([a-z][\w@]*|\?MODULE)[ \t]*:[ \t]*)?([a-z][\w@]*)[ \t]*/[ \t]*\d')
ERL_ATOM_RE = re.compile(r'(?<![\w@?#:\'.$])([a-z][\w@]*)(?![\w@]|[ \t]*[(:/])')
ERL_LOCAL_RE = re.compile(r'(?<![\w@?#:\'.])([a-z][\w@]*)[ \t]*\(')

CLJ_MASK_RE = re.compile(r';[^\n]*|"(?:\\.|[^"\\])*"|\\(?:newline|space|tab|return|formfeed|backspace|u[0-9a-fA-F]{4}|\S)', re.S)
CLJ_TOKEN_RE = re.compile(r'[()\[\]{}]|[^\s,()\[\]{}\'`~@^#"]+')
CLJ_NS_RE = re.compile(r'\(\s*ns\s+[^\s()\[\]{}]+')
CLJ_LOAD_RE = re.compile(r'\(\s*(?:require|use)[\s)]')
CLJ_DEF_RE = re.compile(
    r'^[ \t]*\((def[\w-]*)\s+(?:\^(?:\{[^}]*\}|\S+)\s+)*([^\s()\[\]{}"^@~`]+)', re.M)
CLJ_DEFS = {'def', 'defn', 'defn-', 'defmacro', 'defmulti', 'defmethod', 'defonce', 'deftest', 'defprotocol',
            'defrecord', 'deftype', 'definterface', 'defstruct'}
CLJ_TYPES = {'defprotocol', 'defrecord', 'deftype', 'definterface', 'defstruct'}
CLJ_PROTO_METHOD_RE = re.compile(r'\(\s*([^\s()\[\]{}"^@~`/]+)\s*\[')
CLJ_QUALIFIED_RE = re.compile(r'(?<![\w.*+!?<>=/:\'-])([A-Za-z_][\w.*+!?<>=-]*)/([A-Za-z_*+!?<>=-][\w*+!?<>=-]*)')
CLJ_HEAD_RE = re.compile(r'\(([A-Za-z_*+!?<>=-][\w.*+!?<>=-]*)(?=[\s)])')

GENERATED_HTML_RE = re.compile(
    r'<meta[^>]+name=["\']?generator\b|<!--\s*generated by\b|documentation_options\.js'
    r'|[\w/.-]*\b(?:jazzy|doxygen|javadoc|typedoc|rustdoc)[\w.-]*\.(?:css|js)\b', re.I)

SQL_RE = re.compile(
    r'\bcreate[ \t]+(?:or[ \t]+replace[ \t]+)?(?:(?:temporary|temp|unlogged|materialized|virtual|unique)[ \t]+)*'
    r'(table|view|function|procedure|trigger|type)[ \t]+(?:if[ \t]+not[ \t]+exists[ \t]+)?([`"\[]?[\w.$]+[`"\]]?)',
    re.I)
SQL_REF_RE = re.compile(r'\breferences[ \t]+([`"\[]?[\w.$]+[`"\]]?)', re.I)
SQL_ALTER_RE = re.compile(r'\balter[ \t]+table[ \t]+(?:only[ \t]+)?(?:if[ \t]+exists[ \t]+)?([`"\[]?[\w.$]+[`"\]]?)', re.I)
PROTO_RE = re.compile(r'^[ \t]*(message|service|enum)[ \t]+(\w+)', re.M)
RPC_RE = re.compile(r'^[ \t]*rpc[ \t]+(\w+)', re.M)
GRAPHQL_RE = re.compile(r'^[ \t]*(?:extend[ \t]+)?(type|input|interface|enum|union|scalar)[ \t]+(\w+)', re.M)
PRISMA_RE = re.compile(r'^[ \t]*(model|enum|type|view)[ \t]+(\w+)[ \t]*\{', re.M)
PRISMA_MAP_RE = re.compile(r'@@map\(\s*"([^"]+)"')
THRIFT_RE = re.compile(r'^[ \t]*(struct|service|enum|exception|union)[ \t]+(\w+)', re.M)
MAKE_RE = re.compile(r'^([A-Za-z_][\w./-]*)[ \t]*:(?![=:])', re.M)
DOCKER_STAGE_RE = re.compile(r'^[ \t]*FROM[ \t]+\S+[ \t]+AS[ \t]+([\w.-]+)', re.M | re.I)
CMAKE_RE = re.compile(r'\badd_(?:executable|library)[ \t]*\([ \t]*([\w.-]+)', re.I)
BAZEL_RE = re.compile(r'^(\w+)\(\s*name[ \t]*=[ \t]*"([^"]+)"', re.M)
PACKAGE_SCRIPTS_RE = re.compile(r'"scripts"\s*:\s*\{')
WORKSPACES_RE = re.compile(r'"workspaces"\s*:')
PACKAGE_KEY_RE = re.compile(r'"((?:\\.|[^"\\])+)"\s*:')
STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"?')
K8S_KIND_RE = re.compile(r'^kind:[ \t]*["\']?(\w+)', re.M)
K8S_META_RE = re.compile(r'^metadata:[ \t]*(?:#.*)?$', re.M)
K8S_NAME_RE = re.compile(
    r'^([ \t]+)name:[ \t]*(?:"([^"\n]+)"|\'([^\'\n]+)\'|([\w.:@/-]+))[ \t]*(?:#.*)?$')
YAML_DOC_RE = re.compile(r'^---(?:[ \t].*)?$', re.M)
YAML_KEY_RE = re.compile(r'^([ \t]*)([\w.-]+)[ \t]*:', re.M)
GITLAB_RESERVED = {'stages', 'variables', 'include', 'default', 'workflow', 'image', 'services', 'before_script',
                   'after_script', 'cache', 'pages'}


def is_bundle(name):
    stem = os.path.splitext(name)[0]
    if 'messages' in stem.lower():
        return True
    match = BUNDLE_RE.search(stem)
    return bool(match) and match.group(1) in LANG_CODES


def kind_of(rel):
    name = rel.rsplit('/', 1)[-1]
    if name in LOCKS or name.startswith('.env') or name == 'FUNDING.yml':
        return None
    if '/ISSUE_TEMPLATE/' in f'/{rel}' or '/PULL_REQUEST_TEMPLATE/' in f'/{rel}':
        return None
    ext = os.path.splitext(name)[1]
    if ext in CODE and name not in CONFIG_NAMES and not name.startswith(CONFIG_PREFIXES):
        return 'code'
    config = (name in CONFIG_NAMES or name.startswith(CONFIG_PREFIXES) or ext in CONFIG
              or ext == '.json' and (name.startswith(('tsconfig', 'jsconfig'))
                                     or name.endswith(('.config.json', '.schema.json'))))
    if not config:
        return None
    if DATA_DIRS.intersection(p.lower() for p in rel.split('/')[:-1]):
        return None
    if ext == '.properties' and is_bundle(name):
        return None
    return 'config'


def clean(name):
    return name.strip('`"[]').rsplit('.', 1)[-1]


def line_of(text, pos):
    return text.count('\n', 0, pos) + 1


def blank(text, pattern):
    return pattern.sub(lambda m: re.sub(r'[^\n]', ' ', m.group()), text)


def yaml_children(text, key):
    match = re.search(rf'^{re.escape(key)}:[ \t]*$', text, re.M)
    if not match:
        return []
    out, indent = [], None
    for m in YAML_KEY_RE.finditer(text, match.end()):
        lead = len(m.group(1).expandtabs(2))
        if lead == 0:
            break
        if indent is None:
            indent = lead
        if lead == indent:
            out.append((m.group(2), m.start()))
    return out


def yaml_documents(text):
    starts = [0] + [m.end() for m in YAML_DOC_RE.finditer(text)]
    ends = [m.start() for m in YAML_DOC_RE.finditer(text)] + [len(text)]
    return [(s, text[s:e]) for s, e in zip(starts, ends)]


def k8s_name(doc):
    meta = K8S_META_RE.search(doc)
    if not meta:
        return None
    indent = None
    for line in doc[meta.end():].split('\n'):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        lead = len(line) - len(line.lstrip(' \t'))
        if lead == 0:
            return None
        if indent is None:
            indent = lead
        if lead != indent:
            continue
        match = K8S_NAME_RE.match(line)
        if match:
            value = (match.group(2) or match.group(3) or match.group(4)).strip()
            return None if '{{' in value or not value else value
    return None


def package_scripts(text):
    at = PACKAGE_SCRIPTS_RE.search(text)
    if not at:
        return []
    depth, i, out = 1, at.end(), []
    while i < len(text) and depth:
        c = text[i]
        if c == '"':
            match = PACKAGE_KEY_RE.match(text, i)
            if match and depth == 1:
                out.append(('function', match.group(1), i, None))
            i = (match or STRING_RE.match(text, i)).end()
            continue
        depth += {'{': 1, '}': -1}.get(c, 0)
        i += 1
    return out


def erlang_code(text):
    return blank(blank(text, ERL_MASK_RE), ERL_ATTRIBUTE_RE)


def erlang_entities(text):
    code = erlang_code(text)
    out = []
    for m in ERL_DEF_RE.finditer(code):
        arrow = code.find('->', m.end())
        stop = ERL_END_RE.search(code, m.end())
        if arrow >= 0 and (stop is None or arrow < stop.start()):
            out.append(('function', m.group(1), m.start(), None))
    return out


def clojure_code(text):
    return blank(text, CLJ_MASK_RE)


def form_end(code, start):
    depth = 0
    for i in range(start, len(code)):
        c = code[i]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
            if depth == 0:
                return i + 1
    return len(code)


def clojure_entities(text):
    code = clojure_code(text)
    out = []
    for m in CLJ_DEF_RE.finditer(code):
        form, name = m.group(1), m.group(2)
        at_margin = code.rfind('\n', 0, m.start()) + 1 == code.find('(', m.start())
        if form not in CLJ_DEFS and not at_margin:
            continue
        if form in CLJ_TYPES:
            out.append(('class', name, m.start(), None))
            if form == 'defprotocol':
                body = code[m.end():form_end(code, code.find('(', m.start()))]
                out += [('method', f'{name}.{p.group(1)}', m.end() + p.start(), None)
                        for p in CLJ_PROTO_METHOD_RE.finditer(body)]
        else:
            out.append(('function', name, m.start(), None))
    return out


def entities(rel, text, scripts=True):
    name = rel.rsplit('/', 1)[-1]
    ext = os.path.splitext(name)[1].lower()
    out = []
    if ext == '.sql':
        for m in SQL_RE.finditer(text):
            kind = m.group(1).lower()
            out.append(('class' if kind in ('table', 'view', 'type') else 'function', clean(m.group(2)), m.start(),
                        clean(m.group(2)) if kind in ('table', 'view') else None))
    elif ext == '.proto':
        out += [('class', m.group(2), m.start(), None) for m in PROTO_RE.finditer(text)]
        services = [(m.start(), m.group(2)) for m in PROTO_RE.finditer(text) if m.group(1) == 'service']
        for m in RPC_RE.finditer(text):
            owner = [s for p, s in services if p < m.start()]
            out.append(('method', f'{owner[-1]}.{m.group(1)}' if owner else m.group(1), m.start(), None))
    elif ext in ('.graphql', '.gql'):
        out += [('class', m.group(2), m.start(), None) for m in GRAPHQL_RE.finditer(text)]
    elif ext == '.prisma':
        for m in PRISMA_RE.finditer(text):
            block = text[m.end():text.find('}', m.end())]
            mapped = PRISMA_MAP_RE.search(block)
            out.append(('class', m.group(2), m.start(), (mapped.group(1) if mapped else m.group(2)) if m.group(1) == 'model' else None))
    elif ext == '.thrift':
        out += [('class', m.group(2), m.start(), None) for m in THRIFT_RE.finditer(text)]
    elif name in ('Makefile', 'GNUmakefile', 'makefile', 'Justfile', 'justfile') or ext == '.mk':
        out += [('function', m.group(1), m.start(), None) for m in MAKE_RE.finditer(text)
                if not m.group(1).startswith('.') and '%' not in m.group(1)]
    elif name.startswith(('Dockerfile', 'Containerfile')) or ext == '.dockerfile':
        out += [('class', m.group(1), m.start(), None) for m in DOCKER_STAGE_RE.finditer(text)]
    elif name == 'CMakeLists.txt' or ext == '.cmake':
        out += [('class', m.group(1), m.start(), None) for m in CMAKE_RE.finditer(text)]
    elif name in ('BUILD', 'BUILD.bazel') or ext == '.bzl':
        out += [('class', m.group(2), m.start(), None) for m in BAZEL_RE.finditer(text)]
    elif name == 'package.json':
        out += package_scripts(text) if scripts else []
    elif ext in ('.yml', '.yaml'):
        if name.startswith(('docker-compose', 'compose.')):
            out += [('class', k, p, None) for k, p in yaml_children(text, 'services')]
        elif '.github/workflows/' in rel or name.startswith(('action.', 'azure-pipelines', 'bitbucket-pipelines')):
            out += [('function', k, p, None) for k, p in yaml_children(text, 'jobs')]
        elif name == '.gitlab-ci.yml':
            out += [('function', m.group(2), m.start(), None) for m in YAML_KEY_RE.finditer(text)
                    if not m.group(1) and m.group(2) not in GITLAB_RESERVED and not m.group(2).startswith('.')]
        else:
            for offset, doc in yaml_documents(text):
                kind, meta = K8S_KIND_RE.search(doc), k8s_name(doc)
                if kind and meta:
                    out.append(('class', f'{kind.group(1)}/{meta}', offset + kind.start(), None))
    elif ext in ERLANG:
        out += erlang_entities(text)
    elif ext in CLOJURE:
        out += clojure_entities(text)
    elif ext in CODE:
        for m in CLASS_RE.finditer(text):
            out.append(('class', m.group(2).rstrip(':.'), m.start(), None))
        for m in FUNC_RE.finditer(text):
            out.append(('function', m.group(2).rstrip(':.'), m.start(), None))
    return out


def generated_html(rel, raw):
    if os.path.splitext(rel)[1].lower() not in ('.html', '.htm'):
        return False
    return bool(GENERATED_HTML_RE.search(raw[:4096].decode('utf-8', errors='replace')))


def emits_scripts(root, rel, text):
    parts = rel.split('/')[:-1]
    if not parts:
        return True
    for part in (p.lower() for p in parts):
        if part in SAMPLE_DIRS or part.startswith('test') or 'fixture' in part:
            return False
    if WORKSPACES_RE.search(text):
        return True
    try:
        entries = sorted(os.scandir(Path(root).joinpath(*parts)), key=lambda e: e.name)
    except OSError:
        return False
    for entry in entries:
        if entry.name.startswith('.'):
            continue
        if entry.name in SOURCE_DIRS and entry.is_dir():
            return True
        if os.path.splitext(entry.name)[1] in SOURCE_EXTS and '.config.' not in entry.name and entry.is_file():
            return True
    return False


def family(rel):
    ext = os.path.splitext(rel)[1].lower()
    if ext in ERLANG:
        return 'erlang'
    if ext in CLOJURE:
        return 'clojure'
    return 'lisp' if ext in LISP else ext


class GenericFile:
    def __init__(self, rel, text, mid):
        self.rel = rel
        self.text = text
        self.mid = mid
        self.defs = {}
        self.spans = []


def analyze_generic(root, files, g, issues, read_source, digest):
    units = {}
    tables = defaultdict(list)
    names = defaultdict(list)
    for rel in files:
        raw = read_source(root, rel, issues)
        if raw is None:
            continue
        if b'\0' in raw[:8192]:
            continue
        if kind_of(rel) == 'config' and len(raw) > MAX_CONFIG_BYTES:
            issues.add(rel, 'archivo de configuración de más de 512 KB: se omitió')
            continue
        if generated_html(rel, raw):
            continue
        text = raw.decode('utf-8', errors='replace')
        ext = os.path.splitext(rel)[1]
        mid = g.node(f'm:{rel}', kind='module', name=rel.rsplit('/', 1)[-1], file=rel, line=1,
                     lang=ext.lstrip('.') or rel.rsplit('/', 1)[-1].lower(), hash=digest(raw))
        u = GenericFile(rel, text, mid)
        units[rel] = u
        scripts = rel.rsplit('/', 1)[-1] != 'package.json' or emits_scripts(root, rel, text)
        found = sorted(entities(rel, text, scripts), key=lambda e: e[2])
        groups = {}
        for i, (kind, name, pos, table) in enumerate(found):
            end = found[i + 1][2] if i + 1 < len(found) else len(text)
            prefix = 'c' if kind == 'class' else 'f'
            groups.setdefault((prefix, name), []).append((kind, pos, end, table))
        for (prefix, name), parts in groups.items():
            kind, pos, _, table = parts[0]
            sid = g.node(f'{prefix}:{rel}:{name}', kind=kind, name=name, file=rel, line=line_of(text, pos),
                         lang=ext.lstrip('.'), hash=digest(''.join(text[s:e] for _, s, e, _ in parts)),
                         **({'table': table} if table else {}))
            g.edge(mid, sid, 'contains')
            u.defs.setdefault(name.rsplit('.', 1)[-1], sid)
            u.spans += [(s, e, sid) for _, s, e, _ in parts]
            if table:
                tables[table.lower()].append(sid)
            if kind_of(rel) == 'code':
                names[(family(rel), name.rsplit('.', 1)[-1])].append(sid)
        u.spans.sort()
    link_sql(units, g, tables)
    link_code(units, g, names)
    return {u.mid: (u.rel, u.text) for u in units.values()}, tables


def nearest_tables(g, tables, name, rel):
    found = tables.get(clean(name).lower(), [])
    same = [t for t in found if g.nodes[t]['file'] == rel]
    return same or found


def link_sql(units, g, tables):
    for rel in sorted(units):
        u = units[rel]
        if not u.rel.lower().endswith('.sql'):
            continue
        for start, end, sid in u.spans:
            for m in SQL_REF_RE.finditer(u.text, start, end):
                for target in nearest_tables(g, tables, m.group(1), u.rel):
                    g.edge(sid, target, 'ref')
        for m in SQL_ALTER_RE.finditer(u.text):
            owners = nearest_tables(g, tables, m.group(1), u.rel)
            stop = u.text.find(';', m.end())
            for r in SQL_REF_RE.finditer(u.text, m.end(), stop if stop > 0 else len(u.text)):
                for source in owners:
                    for target in nearest_tables(g, tables, r.group(1), u.rel):
                        g.edge(source, target, 'ref')


def closest(rel, candidates):
    candidates = sorted(set(candidates) - {rel})
    if len(candidates) <= 1:
        return candidates[0] if candidates else None
    parts = rel.split('/')

    def shared(other):
        n = 0
        for a, b in zip(parts, other.split('/')):
            if a != b:
                break
            n += 1
        return n

    ranked = sorted(((shared(c), c) for c in candidates), key=lambda x: (-x[0], x[1]))
    return ranked[0][1] if ranked[0][0] > ranked[1][0] else None


def link_code(units, g, names):
    code = {rel: units[rel] for rel in sorted(units) if kind_of(rel) == 'code'}
    link_erlang({rel: u for rel, u in code.items() if family(rel) == 'erlang'}, g)
    link_clojure({rel: u for rel, u in code.items() if family(rel) == 'clojure'}, g)
    by_stem = defaultdict(list)
    for rel in code:
        by_stem[os.path.splitext(rel.rsplit('/', 1)[-1])[0].lower()].append(rel)
    for rel, u in code.items():
        if family(rel) in ('erlang', 'clojure'):
            continue
        ext = os.path.splitext(rel)[1]
        for m in IMPORT_RE.finditer(u.text):
            rest = m.group(1)
            specs = QUOTED_RE.findall(rest) or BARE_RE.findall(rest)[:3]
            for spec in specs:
                path = re.sub(r'\.|::', '/', os.path.splitext(spec)[0] if '/' in spec or '.' in os.path.splitext(spec)[1] else spec)
                path = path.strip('/').lower()
                stem = path.rsplit('/', 1)[-1]
                hits = [r for r in by_stem.get(stem, []) if r != rel and os.path.splitext(r)[0].lower().endswith(path)]
                if len(hits) == 1:
                    g.edge(u.mid, f'm:{hits[0]}', 'import')
        pattern = LISP_CALL_RE if ext in LISP else CALL_RE
        scope = family(rel)
        for start, end, sid in u.spans or [(0, len(u.text), u.mid)]:
            body = u.text[start:end]
            for m in pattern.finditer(body, body.find('\n') + 1 if u.spans else 0):
                name = m.group(1).rsplit('.', 1)[-1].rsplit('/', 1)[-1]
                target = u.defs.get(name)
                candidates = names.get((scope, name), ())
                if target is None and len(candidates) == 1 and len(name) > 2:
                    target = candidates[0]
                if target and target != sid:
                    g.edge(sid, target, 'call')


def erlang_include(rel, spec, lib, files):
    spec = spec.replace('\\', '/')
    local = os.path.normpath(os.path.join(os.path.dirname(rel), spec)).replace(os.sep, '/')
    if not lib and local in files:
        return local
    parts = [p for p in spec.split('/') if p not in ('', '.', '..')]
    if lib:
        parts = parts[1:]
    if not parts:
        return None
    suffix = '/'.join(parts)
    hits = [f for f in files if f == suffix or f.endswith('/' + suffix)]
    if not hits and not lib:
        hits = [f for f in files if f.rsplit('/', 1)[-1] == parts[-1]]
    return closest(rel, hits)


def link_erlang(units, g):
    modules = defaultdict(list)
    attrs = {}
    for rel, u in units.items():
        found = [(m.group(1), m.group(2) or m.group(3)) for m in ERL_ATTR_RE.finditer(u.text)]
        attrs[rel] = found
        declared = [v for k, v in found if k == 'module']
        if rel.endswith('.erl'):
            modules[declared[0] if declared else os.path.splitext(rel.rsplit('/', 1)[-1])[0]].append(rel)
    files = set(units)
    for rel, u in units.items():
        included = []
        for key, value in attrs[rel]:
            if key in ('behaviour', 'behavior'):
                target = closest(rel, modules.get(value, []))
                if target:
                    g.edge(u.mid, units[target].mid, 'inherits')
            elif key in ('include', 'include_lib'):
                target = erlang_include(rel, value, key == 'include_lib', files)
                if target:
                    g.edge(u.mid, units[target].mid, 'import')
                    included.append(units[target])
        code = erlang_code(u.text)
        for start, end, sid in u.spans:
            for target in erlang_calls(rel, u, code, start, end, units, modules, included):
                if target != sid:
                    g.edge(sid, target, 'call')
            for target in erlang_module_refs(rel, code, start, end, modules):
                g.edge(sid, units[target].mid, 'ref')


def erlang_calls(rel, u, code, start, end, units, modules, included):
    out = []

    def remote(module, name):
        if module == '?MODULE':
            return local(name)
        candidates = modules.get(module, [])
        target = rel if rel in candidates else closest(rel, candidates)
        return units[target].defs.get(name) if target else None

    def local(name):
        for unit in [u] + included:
            if name in unit.defs:
                return unit.defs[name]
        return None

    for m in ERL_REMOTE_RE.finditer(code, start, end):
        out.append(remote(m.group(1), m.group(2)))
    for m in ERL_FUN_RE.finditer(code, start, end):
        out.append(remote(m.group(1), m.group(2)) if m.group(1) else local(m.group(2)))
    for m in ERL_LOCAL_RE.finditer(code, start, end):
        if m.start() == 0 or code[m.start() - 1] == '\n':
            continue
        out.append(local(m.group(1)))
    return [t for t in out if t]


def erlang_module_refs(rel, code, start, end, modules):
    found = set()
    for m in ERL_ATOM_RE.finditer(code, start, end):
        candidates = modules.get(m.group(1), [])
        target = None if rel in candidates else closest(rel, candidates)
        if target:
            found.add(target)
    return sorted(found)


def clj_read(code):
    stack = [[]]
    for m in CLJ_TOKEN_RE.finditer(code):
        token = m.group()
        if token in ('(', '[', '{'):
            stack.append([])
        elif token in (')', ']', '}'):
            if len(stack) > 1:
                done = stack.pop()
                stack[-1].append(done)
        else:
            stack[-1].append(token)
    while len(stack) > 1:
        done = stack.pop()
        stack[-1].append(done)
    return stack[0]


def clj_options(rest):
    options, i = {}, 0
    while i < len(rest):
        key = rest[i]
        if isinstance(key, str) and key.startswith(':') and i + 1 < len(rest):
            options[key] = rest[i + 1]
            i += 2
        else:
            i += 1
    return options


def clj_libspecs(items):
    out = []
    for item in items:
        if isinstance(item, str):
            if not item.startswith(':'):
                out.append((item, None, ()))
            continue
        if not item or not isinstance(item[0], str) or item[0].startswith(':'):
            continue
        head, rest = item[0], item[1:]
        if any(isinstance(x, str) and x.startswith(':') for x in rest):
            options = clj_options(rest)
            alias = options.get(':as') or options.get(':as-alias')
            refer = options.get(':refer', options.get(':only', ()))
            refer = 'all' if refer == ':all' else tuple(x for x in refer if isinstance(x, str)) if isinstance(refer, list) else ()
            out.append((head, alias if isinstance(alias, str) else None, refer))
        else:
            for x in rest:
                if isinstance(x, str):
                    out.append((f'{head}.{x}', None, ()))
                elif x and isinstance(x[0], str):
                    out += clj_libspecs([[f'{head}.{x[0]}', *x[1:]]])
    return out


def clojure_requires(code):
    out = []
    ns = CLJ_NS_RE.search(code)
    ns_span = (ns.start(), form_end(code, ns.start())) if ns else (0, 0)
    if ns:
        form = clj_read(code[ns_span[0]:ns_span[1]])
        for clause in (form[0] if form else []):
            if isinstance(clause, list) and clause and clause[0] in (':require', ':use', ':import', ':require-macros', ':use-macros'):
                out += clj_libspecs(clause[1:])
    for m in CLJ_LOAD_RE.finditer(code):
        if ns_span[0] <= m.start() < ns_span[1]:
            continue
        form = clj_read(code[m.start():form_end(code, m.start())])
        if form and isinstance(form[0], list):
            out += clj_libspecs(form[0][1:])
    return out


def clj_path(ns):
    return ns.replace('-', '_').replace('.', '/')


def link_clojure(units, g):
    by_suffix = defaultdict(list)
    for rel in units:
        parts = os.path.splitext(rel)[0].split('/')
        for i in range(len(parts)):
            by_suffix['/'.join(parts[i:])].append(rel)

    def find(rel, ns):
        hits = by_suffix.get(clj_path(ns), [])
        ext = os.path.splitext(rel)[1]
        preferred = [h for h in hits if h.endswith(ext)] or [h for h in hits if h.endswith('.cljc')] or hits
        return closest(rel, preferred)

    for rel, u in units.items():
        code = clojure_code(u.text)
        aliases, referred, refer_all = {}, {}, []
        for ns, alias, refer in clojure_requires(code):
            target = find(rel, ns)
            if not target:
                continue
            g.edge(u.mid, units[target].mid, 'import')
            aliases[ns] = units[target]
            if alias:
                aliases[alias] = units[target]
            if refer == 'all':
                refer_all.append(units[target])
            for name in refer:
                referred[name] = units[target]

        def resolve(name):
            if name in u.defs:
                return u.defs[name]
            if name in referred:
                return referred[name].defs.get(name)
            for unit in refer_all:
                if name in unit.defs:
                    return unit.defs[name]
            return None

        for start, end, sid in u.spans:
            for m in CLJ_QUALIFIED_RE.finditer(code, start, end):
                unit = aliases.get(m.group(1))
                target = unit.defs.get(m.group(2)) if unit else None
                if target and target != sid:
                    g.edge(sid, target, 'call')
            for m in CLJ_HEAD_RE.finditer(code, start, end):
                target = resolve(m.group(1))
                if target and target != sid:
                    g.edge(sid, target, 'call')


def link_tables(g, tables):
    for nid, meta in list(g.nodes.items()):
        table = meta.get('table')
        if not table or meta.get('lang') == 'sql':
            continue
        for target in tables.get(table.lower(), []):
            if target != nid:
                g.edge(nid, target, 'ref')
