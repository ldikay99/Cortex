import os
import re
from bisect import bisect_right
from collections import defaultdict, namedtuple
from pathlib import Path

CODE = {
    '.clj', '.cljs', '.cljc', '.edn', '.erl', '.hrl', '.nim', '.cr', '.d', '.pas', '.pp', '.adb', '.ads',
    '.f', '.f90', '.f95', '.f03', '.for', '.cob', '.cbl', '.rkt', '.scm', '.ss', '.lisp', '.lsp', '.el', '.tcl',
    '.awk', '.vb', '.vbs', '.bas', '.asm', '.s', '.sv', '.v', '.vhd', '.vhdl', '.r', '.R', '.gd', '.hx', '.purs',
    '.idr', '.agda', '.lean', '.coffee', '.elm', '.gleam', '.odin', '.mojo', '.cu', '.cuh', '.glsl', '.hlsl',
    '.wgsl', '.frag', '.vert', '.comp', '.move', '.cairo', '.vy', '.ino', '.nix', '.raku', '.rakumod', '.sml',
    '.fish', '.bat', '.cmd', '.applescript', '.ahk', '.prg', '.abap', '.apex', '.cls', '.st', '.pde', '.qml',
    '.trigger', '.cpy', '.CBL', '.COB', '.CPY', '.F', '.F90', '.F95', '.F03', '.F08', '.f08', '.f77',
}
CONFIG = {
    '.yml', '.yaml', '.toml', '.ini', '.cfg', '.conf', '.properties', '.sql', '.proto', '.graphql', '.gql',
    '.prisma', '.html', '.htm', '.css', '.scss', '.sass', '.less', '.styl', '.cmake', '.mk', '.bzl', '.hbs',
    '.ejs', '.njk', '.jinja', '.jinja2', '.j2', '.twig', '.liquid', '.mustache', '.csproj', '.fsproj', '.vbproj',
    '.sln', '.dockerfile', '.thrift', '.avsc', '.smithy', '.cue', '.rego', '.http', '.rest', '.tpl', '.tmpl',
    '.gotmpl', '.cshtml', '.razor', '.erb', '.haml', '.slim', '.handlebars', '.bicep', '.bicepparam', '.storyboard',
    '.xib', '.pks', '.pkb', '.pck', '.pls', '.plsql', '.prc', '.fnc',
}
CONFIG_NAMES = {
    'Dockerfile', 'Containerfile', 'Makefile', 'GNUmakefile', 'makefile', 'CMakeLists.txt', 'Jenkinsfile',
    'Procfile', 'Justfile', 'justfile', 'BUILD', 'BUILD.bazel', 'WORKSPACE', 'MODULE.bazel', 'Gemfile', 'Rakefile',
    'Vagrantfile', 'Podfile', 'Brewfile', 'Tiltfile', 'Earthfile', 'Caddyfile', 'nginx.conf', 'package.json',
    'composer.json', 'deno.json', 'deno.jsonc', 'angular.json', 'nx.json', 'turbo.json', 'vercel.json',
    'firebase.json', 'app.json', 'manifest.json', 'lerna.json', 'project.json', 'pom.xml', 'AndroidManifest.xml',
    'web.config', 'openapi.json', 'swagger.json', 'pubspec.yaml', 'mix.exs', 'go.mod', 'Cargo.toml',
    'Package.swift', 'build.sbt', 'requirements.txt', 'Pipfile', 'setup.cfg', 'tox.ini', 'serverless.yml',
    'serverless.yaml', 'Directory.Packages.props', 'Directory.Build.props', 'packages.config',
}
REQUIREMENTS_RE = re.compile(r'requirements[\w.-]*\.(?:txt|in)$')
CLAIMS = ('.blade.php',)
ANDROID_RES_DIRS = ('layout', 'navigation', 'menu')
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


def claims(rel):
    return rel.rsplit('/', 1)[-1].endswith(CLAIMS)


def path_config(rel):
    parts = rel.split('/')
    name = parts[-1]
    if name.endswith('.object-meta.xml') or name.endswith('.object') and 'objects' in parts[:-1]:
        return True
    if REQUIREMENTS_RE.match(name) or 'requirements' in parts[-2:-1] and name.endswith(('.txt', '.in')):
        return True
    return (name.endswith('.xml') and len(parts) >= 3 and parts[-3] == 'res'
            and parts[-2].split('-')[0] in ANDROID_RES_DIRS)


def kind_of(rel):
    name = rel.rsplit('/', 1)[-1]
    if name in LOCKS or name.startswith('.env') or name == 'FUNDING.yml':
        return None
    if '/ISSUE_TEMPLATE/' in f'/{rel}' or '/PULL_REQUEST_TEMPLATE/' in f'/{rel}':
        return None
    ext = os.path.splitext(name)[1]
    if ext in CODE and name not in CONFIG_NAMES and not name.startswith(CONFIG_PREFIXES):
        return 'code'
    config = (claims(rel) or path_config(rel) or name in CONFIG_NAMES or name.startswith(CONFIG_PREFIXES) or ext in CONFIG
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
        self.fmt = 'legacy'
        self.tree = None
        self.links = []
        self.facts = defaultdict(list)
        self.symbols = []


def line_index(text):
    starts = [0] + [m.end() for m in re.finditer('\n', text)]
    return lambda pos: bisect_right(starts, pos)


def last_pos(text, start, end):
    return start + max(len(text[start:end].rstrip()) - 1, 0)


def squash(value, limit):
    return ' '.join(str(value).split())[:limit] or None if value else None


def lang_key(rel):
    name = rel.rsplit('/', 1)[-1]
    if claims(rel):
        return 'blade'
    return os.path.splitext(rel)[1].lstrip('.') or name.lower()


def analyze_generic(root, files, g, issues, read_source, digest):
    units = {}
    tables = defaultdict(list)
    names = defaultdict(list)
    ctx = Context(files)
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
        lang = lang_key(rel)
        lines = line_index(text)
        mid = g.node(f'm:{rel}', kind='module', name=rel.rsplit('/', 1)[-1], file=rel, line=1, lang=lang,
                     hash=digest(raw), end=max(1, len(text.splitlines())))
        u = GenericFile(rel, text, mid)
        units[rel] = u
        scripts = rel.rsplit('/', 1)[-1] != 'package.json' or emits_scripts(root, rel, text)
        u.fmt = format_of(u, ctx)
        try:
            found = sorted((Ent(*e) for e in extract(u, ctx, scripts)), key=lambda e: e.pos)
        except (IndexError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
            issues.add(rel, 'no se pudo extraer su estructura: queda solo como archivo')
            found = []
        groups = {}
        for i, e in enumerate(found):
            end = e.end if e.end is not None else found[i + 1].pos if i + 1 < len(found) else len(text)
            groups.setdefault((PREFIX.get(e.kind, 'f'), e.name), []).append((e, end))
        for (prefix, name), parts in groups.items():
            e = parts[0][0]
            extra = {k: v for k, v in (('table', e.table), ('sig', squash(e.sig, 300)), ('doc', squash(e.doc, 500)),
                                       ('route', name if e.kind == 'endpoint' else None)) if v}
            extra['end'] = max(lines(last_pos(text, p.pos, stop)) for p, stop in parts)
            sid = g.node(f'{prefix}:{rel}:{name}', kind=e.kind, name=name, file=rel, line=lines(e.pos), lang=lang,
                         hash=digest(''.join(text[p.pos:stop] for p, stop in parts)), **extra)
            u.symbols.append((e.kind, name, sid))
            u.defs.setdefault(name.rsplit('.', 1)[-1], sid)
            u.spans += [(p.pos, stop, sid) for p, stop in parts]
            if e.table:
                tables[e.table.lower()].append(sid)
            if kind_of(rel) == 'code':
                names[(family(rel), name.rsplit('.', 1)[-1])].append(sid)
        for (prefix, name), parts in groups.items():
            parent = parts[0][0].parent
            owner = next((f'{p}:{rel}:{parent}' for p in ('c', 'f') if parent and (p, parent) in groups), mid)
            g.edge(owner, f'{prefix}:{rel}:{name}', 'contains')
        u.spans.sort()
    link_sql(units, g, tables)
    link_code(units, g, names)
    Linker(units, g, tables).run()
    return {u.mid: (u.rel, u.text) for u in units.values()}, tables


def nearest_tables(g, tables, name, rel):
    found = tables.get(clean(name).lower(), [])
    same = [t for t in found if g.nodes[t]['file'] == rel]
    if same or len(found) <= 1:
        return same or found
    best = closest(rel, [g.nodes[t]['file'] for t in found])
    return [t for t in found if g.nodes[t]['file'] == best]


def link_sql(units, g, tables):
    for rel in sorted(units):
        u = units[rel]
        if u.fmt != 'sql':
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
        if family(rel) in ('erlang', 'clojure') or u.fmt in OWN_CODE:
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


Ent = namedtuple('Ent', 'kind name pos table end sig doc parent', defaults=(None,) * 5)
PREFIX = {'class': 'c', 'endpoint': 'e'}
OWN_CODE = {'cobol', 'fortran', 'vb', 'apex', 'abap', 'cls'}
SQL_EXTS = {'.sql', '.pks', '.pkb', '.pck', '.pls', '.plsql', '.prc', '.fnc'}
PLSQL_EXTS = SQL_EXTS - {'.sql'}
COBOL_EXTS = {'.cbl', '.cob', '.cpy'}
FORTRAN_EXTS = {'.f', '.for', '.f77', '.f90', '.f95', '.f03', '.f08'}
TEMPLATE_EXTS = {'.html', '.htm', '.j2', '.jinja', '.jinja2', '.njk', '.twig', '.liquid'}
DBT_KEYS = {'models', 'sources', 'seeds', 'snapshots', 'exposures', 'metrics', 'semantic_models', 'analyses'}
DBT_HINT_RE = re.compile(r'\{\{-?\s*(?:ref|source|config)\s*\(|\{%-?\s*(?:macro|materialization|snapshot|test)\b')
CFN_TYPE_RE = re.compile(r'^[ \t]+Type:[ \t]*["\']?(?:AWS|Custom|Alexa)::', re.M)
VB6_RE = re.compile(r'^(?:VERSION\s+\d|Attribute\s+VB_)', re.M)
APEX_HINT_RE = re.compile(r'\b(?:class|interface|enum)\s+\w+[^;{]*\{', re.I)


class Context:
    def __init__(self, files):
        self.dbt = sorted({dir_of(f) for f in files if f.rsplit('/', 1)[-1] == 'dbt_project.yml'}, key=len, reverse=True)
        self.charts = sorted({dir_of(f) for f in files if f.rsplit('/', 1)[-1] == 'Chart.yaml'}, key=len, reverse=True)

    def dbt_root(self, rel):
        return next((d for d in self.dbt if rel.startswith(d)), None)

    def chart_root(self, rel):
        return next((d for d in self.charts if rel.startswith(d)), None)


def dir_of(rel):
    return rel.rsplit('/', 1)[0] + '/' if '/' in rel else ''


def join_path(base, spec):
    path = os.path.normpath(os.path.join(base.rstrip('/'), spec.strip())).replace(os.sep, '/')
    return path[2:] if path.startswith('./') else path


def format_of(u, ctx):
    rel, text = u.rel, u.text
    name = rel.rsplit('/', 1)[-1]
    ext = os.path.splitext(name)[1].lower()
    if claims(rel):
        return 'blade'
    if ext in SQL_EXTS:
        return 'dbt' if ctx.dbt_root(rel) is not None or DBT_HINT_RE.search(text) else 'sql'
    if ext in ('.yml', '.yaml'):
        return yaml_format(u, ctx)
    simple = {'.tpl': 'helm', '.tmpl': 'helm', '.gotmpl': 'helm', '.cshtml': 'razor', '.razor': 'razor', '.erb': 'erb',
              '.haml': 'erb', '.slim': 'erb', '.hbs': 'hbs', '.handlebars': 'hbs', '.mustache': 'hbs', '.ejs': 'ejs',
              '.bicep': 'bicep', '.bicepparam': 'bicep', '.storyboard': 'ios', '.xib': 'ios', '.trigger': 'apex',
              '.apex': 'apex', '.abap': 'abap', '.vb': 'vb', '.vbs': 'vb', '.bas': 'vb'}
    if ext in simple:
        return simple[ext]
    if ext in TEMPLATE_EXTS:
        return 'tpl'
    if name == 'AndroidManifest.xml':
        return 'manifest'
    if name.endswith('.object-meta.xml') or ext == '.object':
        return 'sobject'
    if ext == '.xml' and path_config(rel):
        return 'android'
    if ext in COBOL_EXTS:
        return 'cobol'
    if ext in FORTRAN_EXTS:
        return 'fortran'
    if ext == '.cls':
        return 'vb' if VB6_RE.search(text[:4000]) else 'apex' if APEX_HINT_RE.search(text) else 'cls'
    return 'legacy'


def yaml_format(u, ctx):
    rel, name = u.rel, u.rel.rsplit('/', 1)[-1]
    if (name.startswith(('docker-compose', 'compose.', 'action.', 'azure-pipelines', 'bitbucket-pipelines'))
            or '.github/workflows/' in rel or name == '.gitlab-ci.yml'):
        return 'legacy'
    chart = ctx.chart_root(rel)
    if name == 'Chart.yaml':
        u.tree = yaml_tree(u.text)
        return 'chart'
    if chart is not None and rel[len(chart):].startswith('templates/'):
        return 'helm'
    u.tree = yaml_tree(u.text)
    top = {c.key for c in u.tree.children if c.key}
    if name in ('serverless.yml', 'serverless.yaml'):
        return 'serverless'
    if name in ('Pulumi.yaml', 'Pulumi.yml'):
        return 'pulumi'
    if name.startswith('Pulumi.'):
        return 'pulumistack'
    if name == 'dbt_project.yml':
        return 'dbtproject'
    if ctx.dbt_root(rel) is not None and top & DBT_KEYS:
        return 'dbtyml'
    if 'Resources' in top and (top & {'AWSTemplateFormatVersion', 'Transform'} or CFN_TYPE_RE.search(u.text)):
        return 'cfn'
    if is_ansible(rel, u.tree):
        return 'ansible'
    return 'legacy'


def extract(u, ctx, scripts=True):
    fn = EXTRACTORS.get(u.fmt)
    return fn(u, ctx) if fn else entities(u.rel, u.text, scripts)


class Spans:
    def __init__(self, ents):
        self.spans = sorted(((e.pos, e.end, e) for e in ents if e.end is not None), key=lambda s: (s[0], -s[1]))
        self.starts = [s[0] for s in self.spans]

    def at(self, pos):
        i = bisect_right(self.starts, pos) - 1
        while i >= 0:
            start, end, e = self.spans[i]
            if end > pos:
                return key_of(e)
            i -= 1
        return None


def key_of(e):
    return (PREFIX.get(e.kind, 'f'), e.name)


def match_close(code, i, pairs='{}'):
    depth = 0
    for j in range(i, len(code)):
        c = code[j]
        if c == pairs[0]:
            depth += 1
        elif c == pairs[1]:
            depth -= 1
            if depth == 0:
                return j + 1
    return len(code)


def split_args(text, i):
    out, depth, start, quote = [], 0, i + 1, None
    for j in range(i, min(len(text), i + 4000)):
        c = text[j]
        if quote:
            if c == quote and text[j - 1] != '\\':
                quote = None
            continue
        if c in '\'"':
            quote = c
        elif c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
            if depth == 0:
                out.append(text[start:j])
                return out
        elif c == ',' and depth == 1:
            out.append(text[start:j])
            start = j + 1
    return out


def line_text(text, pos):
    end = text.find('\n', pos)
    return text[pos:end if end >= 0 else len(text)]


def comment_doc(text, pos, prefixes):
    out = []
    for line in reversed(text[:pos].split('\n')[:-1]):
        s = line.strip()
        prefix = next((p for p in prefixes if s.startswith(p)), None)
        if prefix is None or not s:
            break
        out.append(s[len(prefix):].strip())
    return ' '.join(reversed(out)).strip() or None


def block_doc(text, pos):
    head = text[:pos].rstrip()
    if not head.endswith('*/'):
        return None
    start = head.rfind('/**')
    if start < 0:
        return None
    body = re.sub(r'^\s*\*+ ?', '', head[start + 3:-2], flags=re.M)
    return body.strip().split('\n\n')[0].split('@')[0].strip() or None


def strings_in(text):
    return [a or b for a, b in re.findall(r'"([^"\n]*)"|\'([^\'\n]*)\'', text)]


def mask_keep(text, pattern):
    return pattern.sub(lambda m: re.sub(r'[^\n]', ' ', m.group()), text)


class YNode:
    __slots__ = ('key', 'value', 'line', 'pos', 'col', 'end', 'stop', 'item', 'children', 'vpos')

    def __init__(self, key, value, line, pos, col, item):
        self.key, self.value, self.line, self.pos, self.col, self.item = key, value, line, pos, col, item
        self.end, self.stop, self.children, self.vpos = line, pos, [], pos

    def get(self, key):
        return next((c for c in self.children if c.key == key), None)

    def scalar(self, key=None):
        node = self.get(key) if key is not None else self
        if node is None or not node.value or BLOCK_RE.fullmatch(node.value):
            return None
        return unquote(node.value)

    def items(self):
        return [c for c in self.children if c.item]

    def values(self):
        if self.value and self.value.startswith('['):
            return [unquote(v.strip()) for v in self.value.strip('[]').split(',') if v.strip()]
        if self.value:
            return [self.scalar()]
        return [i.scalar() for i in self.items() if i.scalar()]


YKEY_RE = re.compile(r'''("(?:\\.|[^"\\\n])*"|'(?:[^'\n]|'')*'|[^\s#'"{}\[\],&*!|>%@`][^#\n]*?)[ \t]*:(?=[ \t]|$)''')
BLOCK_RE = re.compile(r'[|>][-+0-9]*')


def unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
        return value[1:-1].replace("''", "'") if value[0] == "'" else value[1:-1]
    return value


def yaml_value(value):
    value = value.strip()
    if value[:1] in ('"', "'"):
        q, i = value[0], 1
        while i < len(value):
            if value[i] == q and (q == '"' and value[i - 1] != '\\' or q == "'" and value[i + 1:i + 2] != "'"):
                break
            i += 2 if q == "'" and value[i] == "'" else 1
        head, rest = value[:i + 1], value[i + 1:]
        m = re.search(r'(?:^|[ \t])#', rest)
        return (head + (rest[:m.start()] if m else rest)).strip()
    m = re.search(r'(?:^|[ \t])#', value)
    return (value[:m.start()] if m else value).strip()


def balanced(value):
    return sum(value.count(c) for c in '[{') <= sum(value.count(c) for c in ']}')


def yaml_tree(text):
    root = YNode(None, None, 0, 0, -1, False)
    stack, block, flow, offset = [root], None, None, 0
    for n, raw in enumerate(text.split('\n'), 1):
        start, offset = offset, offset + len(raw) + 1
        body = raw.rstrip()
        stripped = body.lstrip(' ')
        col = len(body) - len(stripped)
        if block is not None:
            if not stripped or col > block:
                if stripped:
                    yaml_touch(stack, n, start + len(body))
                continue
            block = None
        if flow is not None:
            flow.value += ' ' + stripped
            if balanced(flow.value):
                flow = None
            yaml_touch(stack, n, start + len(body))
            continue
        if not stripped or stripped[0] == '#' or col == 0 and stripped[0] == '%':
            continue
        if col == 0 and (stripped in ('---', '...') or stripped.startswith('--- ')):
            del stack[1:]
            continue
        while True:
            if stripped == '-' or stripped[:2] in ('- ', '-\t'):
                while yaml_pops(stack[-1], col):
                    stack.pop()
                node = YNode(None, None, n, start + col, col, True)
                stack[-1].children.append(node)
                stack.append(node)
                rest = stripped[1:]
                stripped = rest.lstrip(' \t')
                col += 1 + len(rest) - len(stripped)
                if stripped and stripped[0] != '#':
                    continue
                break
            m = YKEY_RE.match(stripped)
            if m:
                while stack[-1].col >= col:
                    stack.pop()
                tail = stripped[m.end():]
                value = yaml_value(tail)
                node = YNode(unquote(m.group(1)), value or None, n, start + col, col, False)
                node.vpos = start + col + m.end() + len(tail) - len(tail.lstrip())
                stack[-1].children.append(node)
                stack.append(node)
                if value and BLOCK_RE.fullmatch(value):
                    block = col
                elif value and value[0] in '[{' and not balanced(value):
                    flow = node
            elif stack[-1].item and stack[-1].value is None and not stack[-1].children:
                stack[-1].value = yaml_value(stripped)
                stack[-1].vpos = start + col
                if BLOCK_RE.fullmatch(stack[-1].value):
                    block = col - 2
                elif stack[-1].value[:1] in '[{' and not balanced(stack[-1].value):
                    flow = stack[-1]
            break
        yaml_touch(stack, n, start + len(body))
    return root


def yaml_pops(top, col):
    if top.col < col or top.col < 0:
        return False
    if top.col > col or top.item or top.value is not None:
        return True
    return any(not c.item for c in top.children)


def yaml_touch(stack, line, stop):
    for node in stack[1:]:
        node.end, node.stop = line, stop


def yaml_comment(text, pos):
    lines = text[:pos].split('\n')[:-1]
    out = []
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped.startswith('#'):
            break
        out.append(stripped.lstrip('#').strip())
    return ' '.join(reversed(out)) or None


def flow_get(value, key):
    m = re.search(rf'[{{,][ \t]*{re.escape(key)}[ \t]*:[ \t]*([^,}}]+)', value or '')
    return unquote(m.group(1)) if m else None


JMACRO_RE = re.compile(r'\{%-?\s*(macro|test|materialization)\s+(\w+)\s*(\([^%]*?\))?[^%]*?-?%\}', re.S)
JENDMACRO_RE = re.compile(r'\{%-?\s*end(?:macro|test|materialization)\b[^%]*%\}')
JSNAPSHOT_RE = re.compile(r'\{%-?\s*snapshot\s+(\w+)')
JREGION_RE = re.compile(r'\{\{.*?\}\}|\{%.*?%\}', re.S)
JCALL_RE = re.compile(r'(?<![\w.])([A-Za-z_]\w*)(?:\.([A-Za-z_]\w*))?\s*\(')
JDISPATCH_RE = re.compile(r'adapter\.dispatch\(\s*[\'"](\w+)[\'"]')
JCOMMENT_RE = re.compile(r'\{#.*?#\}', re.S)
DBT_REF_RE = re.compile(r'''\bref\(\s*(['"])([^'"]+)\1(?:\s*,\s*(['"])([^'"]+)\3)?''')
DBT_SOURCE_RE = re.compile(r'''\bsource\(\s*(['"])([^'"]+)\1\s*,\s*(['"])([^'"]+)\3''')
TPL_TAG_RE = re.compile(
    r'\{%-?\s*(extends|include|import|from|embed|use|layout|render|section|include_relative|sameas)\b(.*?)-?%\}', re.S)
TPL_FN_RE = re.compile(r'''\{\{.*?\b(include|source)\(\s*['"]([^'"]+)['"]''')
TPL_ALIAS_RE = re.compile(r'\bas\s+(\w+)')
FRONT_LAYOUT_RE = re.compile(r'\A---[ \t]*\n(?:.*\n)*?layout:[ \t]*["\']?([\w./-]+)', re.M)
JINJA_SKIP = {'macro', 'test', 'materialization', 'if', 'elif', 'for', 'set', 'call', 'filter', 'with', 'block'}


def jinja_doc(text, pos):
    head = text[:pos].rstrip()
    if head.endswith('#}'):
        start = head.rfind('{#')
        return head[start + 2:-2].strip('-# \n') if start >= 0 else None
    return None


def jinja_macros(u):
    out = []
    for m in JMACRO_RE.finditer(u.text):
        stop = JENDMACRO_RE.search(u.text, m.end())
        end = stop.end() if stop else len(u.text)
        kind, name = m.group(1), m.group(2)
        name = name if kind == 'macro' else f'{kind}_{name}'
        out.append(Ent('function', name, m.start(), end=end, sig=f'{m.group(1)} {m.group(2)}{m.group(3) or "()"}',
                       doc=jinja_doc(u.text, m.start())))
    return out


def jinja_calls(u, spans):
    code = mask_keep(u.text, JCOMMENT_RE)
    for region in JREGION_RE.finditer(code):
        body = region.group()
        tag = re.match(r'\{%-?\s*(\w+)', body)
        if tag and tag.group(1) in ('macro', 'test', 'materialization'):
            continue
        owner = spans.at(region.start())
        for m in JCALL_RE.finditer(body):
            if m.group(1) in JINJA_SKIP and not m.group(2):
                continue
            u.links.append((owner, 'call', 'macro', (m.group(1), m.group(2)) if m.group(2) else (None, m.group(1))))
        for m in JDISPATCH_RE.finditer(body):
            u.links.append((owner, 'call', 'macro', (None, f'default__{m.group(1)}')))


def dbt_refs(u, spans, kind):
    for m in DBT_REF_RE.finditer(u.text):
        u.links.append((spans.at(m.start()) if kind == 'ref' else None, kind, 'model', m.group(4) or m.group(2)))
    for m in DBT_SOURCE_RE.finditer(u.text):
        u.links.append((spans.at(m.start()), 'ref', 'source', f'{m.group(2)}.{m.group(4)}'))


def dbt_extract(u, ctx):
    ents = jinja_macros(u)
    spans = Spans(ents)
    u.facts['models'] += [m.group(1) for m in JSNAPSHOT_RE.finditer(u.text)]
    dbt_refs(u, spans, 'import')
    jinja_calls(u, spans)
    return ents


def tpl_extract(u, ctx):
    ents = jinja_macros(u)
    spans = Spans(ents)
    code = mask_keep(u.text, JCOMMENT_RE)
    for m in TPL_TAG_RE.finditer(code):
        tag, args = m.group(1), m.group(2)
        found = strings_in(args.split(' import ')[0] if tag == 'from' else args)
        if not found and tag in ('include', 'render', 'section', 'layout', 'include_relative'):
            bare = re.match(r'\s*([\w./-]+)', args)
            found = [bare.group(1)] if bare and bare.group(1) not in ('with', 'for') else []
        if not found:
            continue
        specs = found if args.lstrip().startswith('[') else found[:1]
        for spec in specs:
            u.links.append((None, 'ref', 'template', (tag, spec)))
        if tag == 'import':
            alias = TPL_ALIAS_RE.search(args)
            if alias:
                u.facts['aliases'].append((alias.group(1), specs[0]))
        elif tag == 'from':
            names = args.split(' import ', 1)[1] if ' import ' in args else ''
            for item in names.split(','):
                bits = item.split()
                if bits and re.fullmatch(r'\w+', bits[0]):
                    u.facts['imported'].append((bits[-1] if 'as' in bits else bits[0], bits[0], specs[0]))
    for m in TPL_FN_RE.finditer(code):
        u.links.append((None, 'ref', 'template', (m.group(1), m.group(2))))
    front = FRONT_LAYOUT_RE.match(u.text)
    if front:
        u.links.append((None, 'ref', 'template', ('layout', front.group(1))))
    jinja_calls(u, spans)
    return ents


HELM_DEFINE_RE = re.compile(r'\{\{-?\s*(define|block)\s+"([^"]+)"[^}]*\}\}')
HELM_ACTION_RE = re.compile(r'\{\{-?\s*(if|range|with|define|block|end)\b')
HELM_INCLUDE_RE = re.compile(r'\b(?:include|template)\s+"([^"]+)"')
HELM_VALUES_RE = re.compile(r'\.Values\.\w')
HELM_COMMENT_RE = re.compile(r'\{\{-?\s*/\*.*?\*/\s*-?\}\}', re.S)


def helm_end(text, start):
    depth = 0
    for m in HELM_ACTION_RE.finditer(text, start):
        depth += -1 if m.group(1) == 'end' else 1
        if depth == 0:
            close = text.find('}}', m.end())
            return close + 2 if close >= 0 else len(text)
    return len(text)


def helm_doc(text, pos):
    head = text[:pos].rstrip()
    if head.endswith('*/}}') or head.endswith('*/ -}}'):
        start = head.rfind('{{')
        return re.sub(r'^\{\{-?\s*/\*|\*/\s*-?\}\}$', '', head[start:]).strip() if start >= 0 else None
    return None


def helm_extract(u, ctx):
    ents = []
    code = mask_keep(u.text, HELM_COMMENT_RE)
    for m in HELM_DEFINE_RE.finditer(code):
        ents.append(Ent('function', m.group(2), m.start(), end=helm_end(code, m.start()),
                        sig=f'{m.group(1)} "{m.group(2)}"', doc=helm_doc(u.text, m.start())))
    spans = Spans(ents)
    root = ctx.chart_root(u.rel)
    for m in HELM_INCLUDE_RE.finditer(code):
        u.links.append((spans.at(m.start()), 'call', 'define', (root, m.group(1))))
    if root is not None:
        seen = set()
        for m in HELM_VALUES_RE.finditer(code):
            owner = spans.at(m.start())
            if owner not in seen:
                seen.add(owner)
                u.links.append((owner, 'ref', 'values', root))
    if os.path.splitext(u.rel)[1].lower() in ('.yml', '.yaml'):
        ents += [Ent(*e) for e in entities(u.rel, u.text)]
    return ents


def chart_extract(u, ctx):
    tree, ents = u.tree, []
    name = tree.scalar('name')
    if not name:
        return ents
    node = tree.get('name')
    ents.append(Ent('class', name, node.pos, end=len(u.text), sig=f'chart {name} {tree.scalar("version") or ""}',
                    doc=tree.scalar('description')))
    u.facts['chart'].append(name)
    deps = tree.get('dependencies')
    for item in deps.items() if deps else []:
        dep, repo = item.scalar('name'), item.scalar('repository') or ''
        if dep:
            u.links.append((('c', name), 'import', 'chart', (dir_of(u.rel), dep, repo)))
    return ents


BLADE_DIRECTIVE_RE = re.compile(
    r'@(extends|include|includeIf|includeWhen|includeUnless|includeFirst|each|component|livewire|extendsFirst)\s*\(')
BLADE_TAG_RE = re.compile(r'<(x-|livewire:)([\w.:-]+)')


def blade_extract(u, ctx):
    code = mask_keep(u.text, re.compile(r'\{\{--.*?--\}\}', re.S))
    for m in BLADE_DIRECTIVE_RE.finditer(code):
        args = split_args(code, m.end() - 1)
        kind = m.group(1)
        pick = args[1:2] if kind in ('includeWhen', 'includeUnless') else args[:1]
        for arg in pick:
            for spec in strings_in(arg) if arg.strip().startswith('[') else strings_in(arg)[:1]:
                u.links.append((None, 'ref', 'blade', ('livewire' if kind == 'livewire' else 'view', spec)))
    for m in BLADE_TAG_RE.finditer(code):
        name = m.group(2)
        if m.group(1) == 'x-' and name.split(':')[0] in ('slot', 'dynamic-component'):
            continue
        u.links.append((None, 'ref', 'blade', ('livewire' if m.group(1) == 'livewire:' else 'comp', name)))
    return []


ERB_RENDER_RE = re.compile(
    r'''\brender\b\s*\(?\s*(?:(partial|template|layout)\s*:\s*|:(partial|template|layout)\s*=>\s*)?(['"])([^'"#{}\s]+)\3''')


def erb_extract(u, ctx):
    for m in ERB_RENDER_RE.finditer(u.text):
        u.links.append((None, 'ref', 'partial', (m.group(1) or m.group(2) or 'partial', m.group(4))))
    return []


HBS_PARTIAL_RE = re.compile(r'''\{\{~?#?>\s*(?:"([^"]+)"|'([^']+)'|([\w./-]+))''')
EJS_INCLUDE_RE = re.compile(r'''\binclude\(\s*['"]([^'"]+)['"]|<%[-=_]?\s*include\s+([\w./-]+)''')


def hbs_extract(u, ctx):
    for m in HBS_PARTIAL_RE.finditer(u.text):
        u.links.append((None, 'ref', 'hbs', m.group(1) or m.group(2) or m.group(3)))
    return []


def ejs_extract(u, ctx):
    for m in EJS_INCLUDE_RE.finditer(u.text):
        u.links.append((None, 'ref', 'ejs', m.group(1) or m.group(2)))
    return []


RAZOR_DIRECTIVE_RE = re.compile(r'^[ \t]*@(model|inherits|inject|using|layout|implements)[ \t]+([^\r\n;]+)', re.M)
RAZOR_CODE_RE = re.compile(r'@(?:code|functions)\s*\{')
RAZOR_TAG_RE = re.compile(r'<([A-Z]\w*)(?=[\s/>])')
RAZOR_PARTIAL_RE = re.compile(
    r'(?:Html\.(?:Render)?Partial(?:Async)?|\bPartialAsync)\(\s*"([^"]+)"|<partial\s+name="([^"]+)"|\bLayout\s*=\s*"([^"]+)"')
RAZOR_VC_RE = re.compile(r'Component\.InvokeAsync\(\s*(?:"(\w+)"|nameof\((\w+)\))|<vc:([\w-]+)')
RAZOR_TYPEOF_RE = re.compile(r'<component\s+type="typeof\((\w+)\)')
CS_METHOD_RE = re.compile(
    r'^[ \t]*(?:\[[^\]\n]*\][ \t]*)*'
    r'(?:(?:public|private|protected|internal|static|async|override|virtual|sealed|new|unsafe|extern|partial)[ \t]+)*'
    r'([\w<>\[\],.? ]+?)[ \t]+(\w+)[ \t]*(?:<[^>\n]*>)?\(([^)]*)\)\s*(?:\{|=>)', re.M)
C_KEYWORDS = {'if', 'for', 'foreach', 'while', 'switch', 'catch', 'using', 'lock', 'return', 'new', 'else', 'when', 'do',
              'try', 'fixed', 'checked', 'sizeof', 'typeof', 'nameof', 'await', 'throw', 'in', 'is', 'as'}


def razor_extract(u, ctx):
    ents, text = [], u.text
    code = mask_keep(text, re.compile(r'@\*.*?\*@', re.S))
    blocks = []
    for m in RAZOR_CODE_RE.finditer(code):
        brace = m.end() - 1
        end = match_close(code, brace)
        blocks.append((m.start(), end))
        for f in CS_METHOD_RE.finditer(code, brace + 1, end):
            if f.group(2) in C_KEYWORDS or (f.group(1).split() or [''])[-1] in C_KEYWORDS:
                continue
            stop = match_close(code, f.end() - 1) if code[f.end() - 1] == '{' else code.find('\n', f.end())
            ents.append(Ent('function', f.group(2), f.start(), end=stop if stop > 0 else end,
                            sig=f.group().strip().rstrip('{=>').strip()))
    for m in RAZOR_DIRECTIVE_RE.finditer(code):
        kind, rest = m.group(1), m.group(2).strip()
        if kind == 'inject':
            rest = rest.rsplit(None, 1)[0] if len(rest.split()) > 1 else rest
        if kind == 'using' and not rest.startswith('static ') and '=' not in rest:
            continue
        names = [rest.split()[-1]] if kind == 'using' else re.findall(r'[A-Za-z_][\w.]*', rest)
        edge = 'inherits' if kind in ('inherits', 'implements') else 'ref'
        for name in names:
            if kind != 'using' and name in ('static', 'global'):
                continue
            u.links.append((None, edge, 'class', (name.rsplit('.', 1)[-1], ('.cs',), name)))
    markup = code
    for start, end in blocks:
        markup = markup[:start] + re.sub(r'[^\n]', ' ', markup[start:end]) + markup[end:]
    if u.rel.endswith('.razor'):
        for m in RAZOR_TAG_RE.finditer(markup):
            u.links.append((None, 'ref', 'component', m.group(1)))
    for m in RAZOR_TYPEOF_RE.finditer(markup):
        u.links.append((None, 'ref', 'component', m.group(1)))
    for m in RAZOR_PARTIAL_RE.finditer(code):
        spec = m.group(1) or m.group(2) or m.group(3)
        typed = re.match(r'@typeof\((\w+)\)', spec)
        u.links.append((None, 'ref', 'component', typed.group(1)) if typed else (None, 'ref', 'view', spec))
    for m in RAZOR_VC_RE.finditer(code):
        name = m.group(1) or m.group(2) or ''.join(p.title() for p in m.group(3).split('-'))
        u.links.append((None, 'ref', 'viewcomponent', name))
    return ents


ROLE_DIRS = {'tasks', 'handlers', 'vars', 'defaults', 'meta'}
PLAY_KEYS = {'hosts', 'import_playbook', 'ansible.builtin.import_playbook'}
TASK_KEYS = {
    'name', 'when', 'tags', 'register', 'notify', 'become', 'become_user', 'become_method', 'vars', 'loop',
    'loop_control', 'ignore_errors', 'ignore_unreachable', 'changed_when', 'failed_when', 'delegate_to',
    'delegate_facts', 'environment', 'listen', 'no_log', 'args', 'retries', 'until', 'delay', 'run_once', 'block',
    'rescue', 'always', 'check_mode', 'diff', 'any_errors_fatal', 'throttle', 'timeout', 'async', 'poll', 'collections',
    'module_defaults', 'connection', 'debugger', 'local_action', 'action', 'remote_user', 'port', 'tasks_from',
}


def ansible_role(rel):
    parts = rel.split('/')
    for i in range(len(parts) - 3, -1, -1):
        if parts[i] == 'roles' and parts[i + 2] in ROLE_DIRS:
            return '/'.join(parts[:i + 2]), parts[i + 2]
    if len(parts) >= 2 and parts[-2] in ROLE_DIRS:
        return '/'.join(parts[:-2]), parts[-2]
    return None, None


def is_ansible(rel, tree):
    role, part = ansible_role(rel)
    items = tree.items()
    if role is not None and 'roles' in rel.split('/'):
        return True
    if items and any(any(c.key in PLAY_KEYS for c in i.children) for i in items):
        return True
    return part in ('tasks', 'handlers') and bool(items) and all(i.children for i in items)


def short_module(key):
    return key.rsplit('.', 1)[-1] if key.startswith(('ansible.builtin.', 'ansible.legacy.')) else key


def ansible_extract(u, ctx):
    ents = []
    role, part = ansible_role(u.rel)
    base = dir_of(u.rel)
    tree = u.tree

    def task(t, handler, parent):
        mods = [c for c in t.children if c.key and c.key not in TASK_KEYS and not c.key.startswith('with_')]
        if t.get('block') is not None and not mods:
            for key in ('block', 'rescue', 'always'):
                node = t.get(key)
                for x in node.items() if node else []:
                    task(x, handler, parent)
            return
        mod = mods[0] if mods else None
        arg = (mod.scalar() or '') if mod else ''
        target = mod and (arg or mod.scalar('file') or mod.scalar('name') or flow_get(mod.value, 'file')
                          or flow_get(mod.value, 'name'))
        name = t.scalar('name') or (f'{mod.key} {target or ""}'.strip()[:80] if mod else None)
        if not name:
            return
        key = ('f', name)
        ents.append(Ent('function', name, t.pos, end=t.stop, sig=f'{mod.key}: {arg}' if mod else name,
                        doc=yaml_comment(u.text, t.pos), parent=parent))
        if handler:
            u.facts['handlers'].append((name, key))
            listen = t.get('listen')
            u.facts['handlers'] += [(v, key) for v in (listen.values() if listen else []) if v]
        notify = t.get('notify')
        for target in notify.values() if notify else []:
            if target and '{{' not in target:
                u.links.append((key, 'call', 'handler', (role, target)))
        if mod is None:
            return
        kind = short_module(mod.key)
        if kind == 'include' and arg:
            target = arg.split()[0]
        if kind in ('include_tasks', 'import_tasks', 'include', 'import_playbook') and target and '{{' not in target:
            spots = [f'{role}/tasks' if role else None, base.rstrip('/')]
            u.links.append((key, 'import', 'path', ([s for s in spots if s is not None], target)))
        elif kind in ('include_role', 'import_role') and target and '{{' not in target:
            u.links.append((key, 'import', 'role', target))
        elif kind in ('include_vars',) and target and '{{' not in target:
            u.links.append((key, 'ref', 'path', ([f'{role}/vars' if role else base.rstrip('/'), base.rstrip('/')], target)))
        elif kind in ('template', 'copy', 'script', 'unarchive'):
            src = mod.scalar('src') or flow_get(mod.value, 'src') or (re.search(r'\bsrc=(\S+)', arg) or [None, None])[1]
            if src and '{{' not in src:
                sub = 'templates' if kind == 'template' else 'files'
                spots = [f'{role}/{sub}' if role else None, f'{base}{sub}', base.rstrip('/')]
                u.links.append((key, 'ref', 'path', ([s for s in spots if s is not None], src)))

    def play(item):
        hosts = item.scalar('hosts')
        target = item.scalar('import_playbook') or item.scalar('ansible.builtin.import_playbook')
        if target:
            u.links.append((None, 'import', 'path', ([base.rstrip('/')], target)))
            return
        name = item.scalar('name') or f'hosts {hosts}'
        key = ('c', name)
        ents.append(Ent('class', name, item.pos, end=item.stop, sig=f'hosts: {hosts}', doc=yaml_comment(u.text, item.pos)))
        roles = item.get('roles')
        for r in roles.items() if roles else []:
            rname = r.scalar() if r.value and not r.value.startswith('{') else (
                r.scalar('role') or r.scalar('name') or flow_get(r.value, 'role') or flow_get(r.value, 'name'))
            if rname and '{{' not in rname:
                u.links.append((key, 'import', 'role', rname))
        files = item.get('vars_files')
        for f in files.values() if files else []:
            if f and '{{' not in f:
                u.links.append((key, 'ref', 'path', ([base.rstrip('/')], f)))
        for section in ('pre_tasks', 'tasks', 'post_tasks', 'handlers'):
            node = item.get(section)
            for t in node.items() if node else []:
                task(t, section == 'handlers', name)

    if part == 'meta':
        deps = tree.get('dependencies')
        for d in deps.items() if deps else []:
            rname = d.scalar() if d.value and not d.value.startswith('{') else (
                d.scalar('role') or d.scalar('name') or flow_get(d.value, 'role'))
            if rname and '{{' not in rname:
                u.links.append((None, 'import', 'role', rname))
        return ents
    if part in ('vars', 'defaults'):
        return ents
    for item in tree.items():
        if any(c.key in PLAY_KEYS for c in item.children):
            play(item)
        elif part in ('tasks', 'handlers') or role is None:
            task(item, part == 'handlers', None)
    u.facts['role'].append(role)
    return ents


CFN_REF_RE = re.compile(
    r'''!Ref[ \t]+["']?([\w-]+)|\bRef["']?[ \t]*:[ \t]*["']?([\w-]+)|!GetAtt[ \t]+["']?([\w-]+)|!GetAtt[ \t]*\[[ \t]*["']?([\w-]+)'''
    r'''|Fn::GetAtt["']?[ \t]*:\s*(?:\[\s*|-\s+)?["']?([\w-]+)|\$\{([\w-]+)[.}]''')
CFN_DEPENDS_RE = re.compile(r'''\bDependsOn["']?[ \t]*:[ \t]*(\[[^\]]*\]|["']?[\w-]+["']?|(?:\s*-[ \t]+["']?[\w-]+["']?)+)''')


def route_name(method, path):
    path = '/' + str(path).strip().strip('/')
    path = re.sub(r'\{(\w+)\+?\}', r':\1', path)
    method = str(method or 'ANY').upper()
    return f'{"ANY" if method == "*" else method} {path}'


def cfn_extract(u, ctx, base=None):
    tree, ents = base or u.tree, []
    ids, spans = {}, []
    transform, globs = u.tree.get('Transform'), u.tree.get('Globals')
    sam = bool(transform) and any('Serverless' in (v or '') for v in transform.values())
    glob = globs.get('Function') if globs else None
    for section, label in (('Parameters', 'Parameter'), ('Resources', None), ('Outputs', 'Output')):
        node = tree.get(section)
        for c in node.children if node else []:
            if not c.key:
                continue
            kind = c.scalar('Type')
            if label:
                name, sig = f'{label}/{c.key}', f'{label} {c.key}' + (f': {kind}' if kind else '')
            elif kind:
                name, sig = f'{kind}/{c.key}', f'{c.key}: {kind}'
            else:
                continue
            ents.append(Ent('class', name, c.pos, end=c.stop, sig=sig,
                            doc=c.scalar('Description') or yaml_comment(u.text, c.pos)))
            if section != 'Outputs':
                ids[c.key] = name
            spans.append((c, name))
            if kind in ('AWS::Serverless::Function', 'AWS::Lambda::Function'):
                cfn_function(u, c, name, glob, sam, ents)
    for c, name in spans:
        body = u.text[c.pos:c.stop]
        found = [next(g for g in m.groups() if g) for m in CFN_REF_RE.finditer(body)]
        for m in CFN_DEPENDS_RE.finditer(body):
            found += re.findall(r'[\w-]+', m.group(1))
        for ref in sorted(set(found)):
            if ref in ids and ids[ref] != name:
                u.links.append((('c', name), 'ref', 'local', ('c', ids[ref])))
    return ents


def cfn_function(u, c, name, glob, sam, ents):
    props = c.get('Properties') or YNode(None, None, 0, 0, 0, False)

    def pick(key):
        return props.scalar(key) or (glob.scalar(key) if glob else None)

    handler, code = pick('Handler'), pick('CodeUri')
    spec = (dir_of(u.rel), code if code and '://' not in code else None, handler, pick('Runtime'))
    if handler:
        u.links.append((('c', name), 'ref', 'handler_code', spec))
    events = props.get('Events')
    for ev in events.children if events and sam else []:
        if ev.scalar('Type') not in ('Api', 'HttpApi'):
            continue
        p = ev.get('Properties')
        path = p.scalar('Path') if p else None
        if path:
            route = route_name(p.scalar('Method'), path)
            ents.append(Ent('endpoint', route, ev.pos, end=ev.stop, sig=f'{route} -> {c.key}'))
            u.links.append((('e', route), 'handles', 'handles', (spec, ('c', name))))


def serverless_extract(u, ctx):
    tree, ents = u.tree, []
    provider = tree.get('provider')
    runtime = provider.scalar('runtime') if provider else None
    functions = tree.get('functions')
    for c in functions.children if functions else []:
        if not c.key:
            continue
        handler = c.scalar('handler')
        ents.append(Ent('function', c.key, c.pos, end=c.stop, sig=f'{c.key}: {handler or c.scalar("image") or ""}',
                        doc=c.scalar('description') or yaml_comment(u.text, c.pos)))
        spec = (dir_of(u.rel), None, handler, c.scalar('runtime') or runtime)
        if handler:
            u.links.append((('f', c.key), 'ref', 'handler_code', spec))
        events = c.get('events')
        for ev in events.items() if events else []:
            http = ev.get('http') or ev.get('httpApi')
            if http is None:
                continue
            if http.value and not http.value.startswith('{'):
                bits = http.scalar().split(None, 1)
                method, path = (bits[0], bits[1]) if len(bits) == 2 else ('ANY', bits[0] if bits[0] != '*' else '/')
            else:
                method = http.scalar('method') or flow_get(http.value, 'method') or 'ANY'
                path = http.scalar('path') or flow_get(http.value, 'path')
            if not path:
                continue
            route = route_name(method, path)
            ents.append(Ent('endpoint', route, ev.pos, end=ev.stop, sig=f'{route} -> {c.key}'))
            u.links.append((('e', route), 'handles', 'handles', (spec, ('f', c.key))))
    resources = tree.get('resources')
    if resources is not None and resources.get('Resources') is not None:
        ents += cfn_extract(u, ctx, resources)
    return ents


def pulumi_extract(u, ctx):
    name = u.tree.scalar('name')
    if not name:
        return []
    runtime = u.tree.scalar('runtime') or (u.tree.get('runtime').scalar('name') if u.tree.get('runtime') else '')
    u.facts['project'].append(name)
    return [Ent('class', name, u.tree.get('name').pos, end=len(u.text), sig=f'pulumi project {name} ({runtime})',
                doc=u.tree.scalar('description'))]


def pulumistack_extract(u, ctx):
    u.links.append((None, 'ref', 'pulumi', dir_of(u.rel)))
    return []


def dbtproject_extract(u, ctx):
    name = u.tree.scalar('name')
    return [Ent('class', name, u.tree.get('name').pos, end=len(u.text), sig=f'dbt project {name}')] if name else []


def dbtyml_extract(u, ctx):
    ents = []

    def columns(node, owner):
        cols = node.get('columns')
        for col in cols.items() if cols else []:
            cname = col.scalar('name')
            if cname:
                ents.append(Ent('method', f'{owner}.{cname}', col.pos, end=col.stop, sig=f'column {cname}',
                                doc=col.scalar('description'), parent=owner))

    for section in sorted(DBT_KEYS):
        node = u.tree.get(section)
        for item in node.items() if node else []:
            name = item.scalar('name')
            if not name:
                continue
            if section == 'sources':
                tables = item.get('tables')
                for t in tables.items() if tables else []:
                    tname = t.scalar('name')
                    if tname:
                        full = f'{name}.{tname}'
                        ents.append(Ent('class', full, t.pos, end=t.stop, sig=f'source {full}',
                                        doc=t.scalar('description') or item.scalar('description')))
                        u.facts['sources'].append(full)
                        columns(t, full)
                continue
            ents.append(Ent('class', name, item.pos, end=item.stop, sig=f'{section[:-1]} {name}', doc=item.scalar('description')))
            columns(item, name)
            if section in ('models', 'seeds', 'snapshots', 'analyses'):
                u.links.append((('c', name), 'ref', 'model', name))
    dbt_refs(u, Spans(ents), 'ref')
    return ents


BICEP_DECL_RE = re.compile(r"^[ \t]*(resource|module|param|var|output|type|func)[ \t]+(\w+)(?:[ \t]+'([^'\n]*)')?", re.M)
BICEP_IMPORT_RE = re.compile(r"^[ \t]*(?:import|using)\b[^'\n]*'([^'\n]+\.bicep)'", re.M)
BICEP_MASK_RE = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
BICEP_STR_RE = re.compile(r"'(?:\\.|[^'\\])*'")
BICEP_IDENT_RE = re.compile(r'(?<![\w.$])([A-Za-z_]\w*)\b(?![ \t]*:(?!:))')


def bicep_end(code, start):
    depth, i, seen = 0, start, False
    while i < len(code):
        c = code[i]
        if c == "'":
            m = BICEP_STR_RE.match(code, i)
            i = m.end() if m else i + 1
            continue
        if c in '{[(':
            depth += 1
            seen = True
        elif c in '}])':
            depth -= 1
            if depth <= 0 and seen:
                return i + 1
        elif c == '\n' and depth == 0:
            return i
        i += 1
    return len(code)


def bicep_doc(text, pos):
    lines = text[:pos].split('\n')[:-1]
    out = []
    for line in reversed(lines):
        s = line.strip()
        m = re.match(r"@(?:sys\.)?description\(\s*'((?:\\.|[^'])*)'", s)
        if m:
            out.append(m.group(1))
        elif s.startswith('//'):
            out.append(s.lstrip('/ '))
        elif not s.startswith('@'):
            break
    return ' '.join(reversed(out)) or None


def bicep_extract(u, ctx):
    code = mask_keep(u.text, BICEP_MASK_RE)
    ents, decls = [], []
    for m in BICEP_DECL_RE.finditer(code):
        kind, name = m.group(1), m.group(2)
        end = bicep_end(code, m.end())
        ent_kind = 'class' if kind in ('resource', 'module') else 'function'
        ents.append(Ent(ent_kind, name, m.start(), end=end, sig=line_text(code, m.start()).strip().rstrip('{= '),
                        doc=bicep_doc(u.text, m.start())))
        decls.append((m, end, (PREFIX.get(ent_kind, 'f'), name)))
        if kind == 'module' and m.group(3) and not re.match(r'(?:br|ts)[:/]', m.group(3)):
            u.links.append(((PREFIX.get(ent_kind, 'f'), name), 'import', 'path', ([dir_of(u.rel).rstrip('/')], m.group(3))))
    for m in BICEP_IMPORT_RE.finditer(code):
        u.links.append((None, 'import', 'path', ([dir_of(u.rel).rstrip('/')], m.group(1))))
    keys = {key[1]: key for _, _, key in decls}
    for m, end, key in decls:
        body = BICEP_STR_RE.sub(lambda s: ' '.join(re.findall(r'\$\{([^}]*)\}', s.group())), code[m.end():end])
        for ref in sorted({x for x in BICEP_IDENT_RE.findall(body) if x in keys and keys[x] != key}):
            u.links.append((key, 'ref', 'local', keys[ref]))
    return ents


QNAME = r'(?:[`"\[][^`"\]\n]+[`"\]]|[\w$#@]+)(?:[ \t]*\.[ \t]*(?:[`"\[][^`"\]\n]+[`"\]]|[\w$#@]+))*'
SQL_CREATE_RE = re.compile(
    r'\bcreate[ \t]+(?:or[ \t]+(?:replace|alter)[ \t]+)?(?:definer[ \t]*=[ \t]*\S+[ \t]+)?'
    r'(?:(?:temporary|temp|unlogged|materialized|virtual|unique|editionable|noneditionable|global|local|external|recursive'
    r'|secure|transient)[ \t]+)*'
    r'(table|view|function|procedure|proc|trigger|type[ \t]+body|type|package[ \t]+body|package)[ \t]+'
    r'(?:if[ \t]+not[ \t]+exists[ \t]+)?(' + QNAME + ')', re.I)
SQL_INNER_RE = re.compile(
    r'^[ \t]*(?:(?:overriding|final|instantiable|not|member|static|constructor|map|order)[ \t]+)*(procedure|function)[ \t]+(' + QNAME + ')',
    re.I | re.M)
SQL_MASK_RE = re.compile(r"--[^\n]*|/\*.*?\*/|'(?:[^'\n]|'')*'", re.S)
SQL_USE_RE = re.compile(
    r'\b(?:from|join|into|update|truncate(?:[ \t]+table)?|using)\s+(?!select\b|values\b|set\b)((?>' + QNAME + r'))(?![(.])',
    re.I)
SQL_ON_RE = re.compile(r'\bon\s+((?>' + QNAME + r'))(?![(.])', re.I)
SQL_CALL_RE = re.compile(r'\b(?:exec|execute|call|perform)\s+(?:@\w+\s*=\s*)?((?>' + QNAME + r'))|((?>' + QNAME + r'))[ \t]*\(', re.I)
SQL_STMT_CALL_RE = re.compile(r'^[ \t]*((?>' + QNAME + r'))[ \t]*;', re.M)
SQL_GO_RE = re.compile(r'^[ \t]*GO[ \t]*;?[ \t]*$', re.M | re.I)
SQL_DOLLAR_RE = re.compile(r'\$(\w*)\$')
SQL_PART_RE = re.compile(r'[`"\[]([^`"\]]+)[`"\]]|([\w$#@]+)')


def sql_parts(raw):
    return [a or b for a, b in SQL_PART_RE.findall(raw)]


def stmt_end(code, start, limit):
    depth = 0
    go = SQL_GO_RE.search(code, start, limit)
    limit = go.start() if go else limit
    for i in range(start, limit):
        c = code[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif c == ';' and depth <= 0:
            return i + 1
    return limit


def routine_end(code, start, limit):
    dollar = SQL_DOLLAR_RE.search(code, start, limit)
    if dollar:
        close = code.find(dollar.group(), dollar.end(), limit)
        if close > 0:
            semi = code.find(';', close, limit)
            return semi + 1 if semi > 0 else close + len(dollar.group())
    go = SQL_GO_RE.search(code, start, limit)
    return go.start() if go else limit


def sql_links(u, code, key, start, end, trigger=False):
    body = code[start:end]
    for m in SQL_USE_RE.finditer(body):
        u.links.append((key, 'data', 'table', sql_parts(m.group(1))))
    if trigger:
        head = re.split(r'\b(?:begin|as|for[ \t]+each|execute|declare)\b', body, maxsplit=1, flags=re.I)[0]
        for m in SQL_ON_RE.finditer(head):
            u.links.append((key, 'data', 'table', sql_parts(m.group(1))))
    for m in SQL_CALL_RE.finditer(body):
        u.links.append((key, 'call', 'sqlcall', sql_parts(m.group(1) or m.group(2))))
    for m in SQL_STMT_CALL_RE.finditer(body):
        u.links.append((key, 'call', 'sqlcall', sql_parts(m.group(1))))


def sql_extract(u, ctx):
    code = mask_keep(u.text, SQL_MASK_RE)
    creates = list(SQL_CREATE_RE.finditer(code))
    bounds = [m.start() for m in creates] + [len(code)]
    ents, routines = [], []
    for i, m in enumerate(creates):
        kind = ' '.join(m.group(1).lower().split())
        parts = sql_parts(m.group(2))
        if not parts:
            continue
        name, limit = parts[-1], bounds[i + 1]
        sig = ' '.join(line_text(code, m.start()).split())
        if kind in ('table', 'view', 'type'):
            end = stmt_end(code, m.end(), limit)
            ents.append(Ent('class', name, m.start(), table=name if kind != 'type' else None, end=end, sig=sig))
            if kind == 'view':
                routines.append((('c', name), m.start(), end, False))
        elif kind in ('package', 'package body', 'type body'):
            ents.append(Ent('class', name, m.start(), end=limit, sig=sig))
            ents += sql_inner(u, code, m.end(), limit, name, routines)
        else:
            end = routine_end(code, m.end(), limit)
            ents.append(Ent('function', name, m.start(), end=end, sig=sig))
            routines.append((('f', name), m.start(), end, kind == 'trigger'))
    if not creates and os.path.splitext(u.rel)[1].lower() in PLSQL_EXTS:
        ents += sql_inner(u, code, 0, len(code), None, routines)
    for key, start, end, trigger in routines:
        sql_links(u, code, key, start, end, trigger)
    return ents


def sql_inner(u, code, start, limit, owner, routines):
    found = list(SQL_INNER_RE.finditer(code, start, limit))
    out = []
    for i, m in enumerate(found):
        parts = sql_parts(m.group(2))
        if not parts:
            continue
        end = found[i + 1].start() if i + 1 < len(found) else limit
        close = re.search(rf'\bend[ \t]+{re.escape(parts[-1])}[ \t]*;', code[m.end():end], re.I)
        end = m.end() + close.end() if close else end
        name = f'{owner}.{parts[-1]}' if owner else parts[-1]
        out.append(Ent('method' if owner else 'function', name, m.start(), end=end, parent=owner,
                       sig=' '.join(line_text(code, m.start()).split())))
        routines.append(((PREFIX.get(out[-1].kind, 'f'), name), m.start(), end, False))
    return out


COBOL_RESERVED = {'EXIT', 'GOBACK', 'CONTINUE', 'ELSE', 'DECLARATIVES', 'STOP', 'END', 'NEXT', 'SKIP', 'EJECT', 'TRUE',
                  'FALSE', 'OTHER', 'RETURN', 'THEN', 'END-EXEC'}
COBOL_PROGRAM_RE = re.compile(r'\b(?:PROGRAM|FUNCTION)-ID\.?\s+["\']?([\w-]+)', re.I)
COBOL_END_PROGRAM_RE = re.compile(r'\bEND[ \t]+PROGRAM\b[^.\n]*\.?', re.I)
COBOL_PROCEDURE_RE = re.compile(r'\bPROCEDURE[ \t]+DIVISION\b[^.]*\.', re.I)
COBOL_PARA_RE = re.compile(r'^([ \t]*)([A-Za-z0-9][\w-]*)(?:[ \t]+(SECTION))?(?:[ \t]+\d+)?[ \t]*\.[ \t]*$', re.M)
COBOL_PERFORM_RE = re.compile(r'\b(?:PERFORM|GO\s+TO)\s+([A-Za-z0-9][\w-]*)(?:\s+(?:THRU|THROUGH)\s+([\w-]+))?', re.I)
COBOL_CALL_RE = re.compile(r'\bCALL[ \t]+["\']([\w-]+)["\']', re.I)
COBOL_COPY_RE = re.compile(r'\bCOPY[ \t]+["\']?([\w-]+)|\+\+INCLUDE[ \t]+([\w-]+)|\bEXEC[ \t]+SQL[ \t]+INCLUDE[ \t]+([\w-]+)', re.I)
COBOL_SQL_RE = re.compile(r'\bEXEC[ \t]+SQL\b(.*?)\bEND-EXEC', re.I | re.S)
COBOL_STR_RE = re.compile(r'"[^"\n]*"|\'[^\'\n]*\'')


def cobol_code(text):
    fixed = not re.search(r'>>[ \t]*SOURCE[ \t]+(?:FORMAT[ \t]+)?(?:IS[ \t]+)?FREE', text, re.I)
    if fixed:
        m = re.search(r'^([^\n]*?)(?:IDENTIFICATION|ID|PROCEDURE)[ \t]+DIVISION', text, re.I | re.M)
        fixed = m is None or len(m.group(1)) >= 7
    out = []
    for line in text.split('\n'):
        if fixed:
            if len(line) > 6 and line[6] in '*/':
                line = ' ' * len(line)
            else:
                line = ' ' * min(len(line), 7) + line[7:72] + ' ' * max(len(line) - 72, 0)
        cut = line.find('*>')
        if cut >= 0:
            line = line[:cut] + ' ' * (len(line) - cut)
        out.append(line)
    return '\n'.join(out), fixed


def cobol_extract(u, ctx):
    code, fixed = cobol_code(u.text)
    plain = mask_keep(code, COBOL_STR_RE)
    ents = []
    programs = [(m.start(), m.end(), m.group(1)) for m in COBOL_PROGRAM_RE.finditer(code)] or [(0, 0, None)]
    for i, (start, head, name) in enumerate(programs):
        limit = programs[i + 1][0] if i + 1 < len(programs) else len(code)
        stop = COBOL_END_PROGRAM_RE.search(code, head, limit)
        end = stop.end() if stop else limit
        if name:
            ents.append(Ent('class', name, start, end=end, sig=f'PROGRAM-ID. {name}'))
        proc = COBOL_PROCEDURE_RE.search(plain, head, end)
        if not proc:
            continue
        paras = []
        for p in COBOL_PARA_RE.finditer(plain, proc.end(), end):
            if fixed and len(p.group(1).expandtabs(4)) > 10:
                continue
            word = p.group(2).upper()
            if word in COBOL_RESERVED or word.startswith('END-'):
                continue
            paras.append(p)
        for j, p in enumerate(paras):
            stop_at = paras[j + 1].start() if j + 1 < len(paras) else end
            ents.append(Ent('function', p.group(2), p.start(2), end=stop_at, parent=name,
                            sig=' '.join(p.group().split())))
    spans = Spans(ents)
    for m in COBOL_PERFORM_RE.finditer(plain):
        owner = spans.at(m.start())
        for target in filter(None, (m.group(1), m.group(2))):
            u.links.append((owner, 'call', 'cobpara', target.upper()))
    for m in COBOL_CALL_RE.finditer(code):
        u.links.append((spans.at(m.start()), 'call', 'cobprog', m.group(1).upper()))
    for m in COBOL_COPY_RE.finditer(code):
        name = next(g for g in m.groups() if g)
        if name.upper() not in ('SQLCA', 'SQLDA'):
            u.links.append((None, 'import', 'copybook', name.upper()))
    for m in COBOL_SQL_RE.finditer(plain):
        for t in SQL_USE_RE.finditer(m.group(1)):
            u.links.append((spans.at(m.start()), 'data', 'table', sql_parts(t.group(1))))
    return ents


VB_MASK_RE = re.compile(r'"(?:[^"\n]|"")*"|\'[^\n]*|^[ \t]*rem\b[^\n]*', re.I | re.M)
VB_MODS = (r'(?:(?:public|private|friend|protected|partial|mustinherit|notinheritable|shadows|shared|static|global|'
           r'overrides|overridable|overloads|mustoverride|notoverridable|async|iterator|default|readonly|writeonly|'
           r'widening|narrowing|custom)[ \t]+)*')
VB_TYPE_RE = re.compile(r'^[ \t]*' + VB_MODS + r'(class|module|structure|interface|enum|namespace)[ \t]+(\w+)', re.I)
VB_PROC_RE = re.compile(r'^[ \t]*(' + VB_MODS + r')(declare[ \t]+(?:(?:ansi|unicode|auto)[ \t]+)?)?'
                        r'(sub|function|property|operator|event)[ \t]+(?:(?:get|let|set)[ \t]+)?(\w+)', re.I)
VB_END_RE = re.compile(r'^[ \t]*end[ \t]+(class|module|structure|interface|enum|namespace|sub|function|property|operator|event)\b', re.I)
VB_LAMBDA_RE = re.compile(r'\b(sub|function)[ \t]*\([^)]*\)[ \t]*(?:as[ \t]+[\w.]+[ \t]*)?$', re.I)
VB_NAME_RE = re.compile(r'^Attribute[ \t]+VB_Name[ \t]*=[ \t]*"(\w+)"', re.M)
VB_INHERITS_RE = re.compile(r'^[ \t]*(inherits|implements)[ \t]+([\w.]+)', re.I | re.M)
VB_CALL_RE = re.compile(r'\bcall[ \t]+(\w+)(?:\.(\w+))?|(?<![\w.])(\w+)\.(\w+)\b|(?<![\w.])(\w+)[ \t]*\('
                        r'|^[ \t]*(\w+)(?=[ \t]*$|[ \t]+[^=\s])', re.I | re.M)
VB_TYPES = {'class', 'module', 'structure', 'interface', 'enum'}
VB_PROCS = {'sub', 'function', 'property', 'operator', 'event'}


def vb_doc(text, pos):
    out = []
    for line in reversed(text[:pos].split('\n')[:-1]):
        s = line.strip()
        if not s.startswith("'''"):
            break
        out.append(re.sub(r'<[^>]+>', ' ', s[3:]))
    return ' '.join(reversed(out)).strip() or None


def vb_extract(u, ctx):
    code = mask_keep(u.text, VB_MASK_RE)
    ents, stack, offset = [], [], 0
    vbname = VB_NAME_RE.search(u.text)
    types = (VB_TYPE_RE.match(x) for x in code.split('\n'))
    file_owner = vbname.group(1) if vbname and not any(t and t.group(1).lower() not in ('enum', 'namespace') for t in types) else None
    if file_owner:
        ents.append(Ent('class', file_owner, vbname.start(), end=len(code), sig=f'Module {file_owner}'))

    def close(item, stop):
        if item[1] is not None:
            ents[item[1]] = ents[item[1]]._replace(end=stop)

    def owner():
        return next((ents[i].name for k, i in reversed(stack) if k in VB_TYPES and i is not None), file_owner)

    def owner_kind():
        return next((k for k, i in reversed(stack) if k in VB_TYPES), None)

    for line in code.split('\n'):
        start, offset = offset, offset + len(line) + 1
        stop = start + len(line)
        m = VB_END_RE.match(line)
        if m:
            kind = m.group(1).lower()
            while stack:
                item = stack.pop()
                close(item, stop)
                if item[0] == kind:
                    break
            continue
        t, p = VB_TYPE_RE.match(line), VB_PROC_RE.match(line)
        if (t or p) and stack and stack[-1][0] in VB_PROCS and stack[-1][1] is not None:
            item = stack.pop()
            close(item, start - 1)
        if t:
            kind = t.group(1).lower()
            if kind == 'namespace':
                stack.append(('namespace', None))
                continue
            ents.append(Ent('class', t.group(2), start, sig=line.strip(), doc=vb_doc(u.text, start), parent=owner()))
            stack.append((kind, len(ents) - 1))
            continue
        if p:
            kind, name, mods = p.group(3).lower(), p.group(4), p.group(1).lower()
            cls = owner()
            single = bool(p.group(2)) or 'mustoverride' in mods or owner_kind() == 'interface' or kind == 'event' and 'custom' not in mods
            ents.append(Ent('method' if cls else 'function', f'{cls}.{name}' if cls else name, start, end=stop if single else None,
                            sig=line.strip(), doc=vb_doc(u.text, start), parent=cls))
            if not single:
                stack.append((kind, len(ents) - 1))
            continue
        lam = VB_LAMBDA_RE.search(line)
        if lam:
            stack.append((lam.group(1).lower(), None))
    while stack:
        close(stack.pop(), len(code))
    ents = [e if e.end is not None else e._replace(end=len(code)) for e in ents]
    spans = Spans(ents)
    for m in VB_CALL_RE.finditer(code):
        key = spans.at(m.start())
        if key is None or key[0] != 'f':
            continue
        cls = key[1].rsplit('.', 1)[0] if '.' in key[1] else None
        if m.group(1):
            spec = (cls, m.group(1), m.group(2)) if m.group(2) else (cls, None, m.group(1))
        elif m.group(3):
            spec = (cls, m.group(3), m.group(4))
        else:
            spec = (cls, None, m.group(5) or m.group(6))
        u.links.append((key, 'call', 'vbcall', spec))
    for m in VB_INHERITS_RE.finditer(code):
        key = spans.at(m.start())
        if key and key[0] == 'c':
            u.links.append((key, 'inherits', 'class', (m.group(2), ('.vb', '.cs', '.bas', '.cls'), m.group(2))))
    return ents


F_UNIT_RE = re.compile(
    r'^[ \t]*(?:(?:pure|elemental|recursive|impure|non_recursive|module|integer|real|logical|complex|character'
    r'|double[ \t]+precision|double[ \t]+complex|type[ \t]*\([^)]*\)|class[ \t]*\([^)]*\))'
    r'(?:[ \t]*\([^)]*\)|[ \t]*\*[ \t]*\d+)?[ \t]+)*'
    r'(program|module|submodule|subroutine|function|block[ \t]*data)\b[ \t]*(\([^)]*\)[ \t]*)?(\w+)?', re.I)
F_TYPE_RE = re.compile(r'^[ \t]*type[ \t]*(?:,[ \t]*([^:\n]*?))?[ \t]*::[ \t]*(\w+)|^[ \t]*type[ \t]+(\w+)[ \t]*$', re.I)
F_END_RE = re.compile(r'^[ \t]*end[ \t]*(program|module|submodule|subroutine|function|type|interface|procedure'
                      r'|block[ \t]*data)\b|^[ \t]*end[ \t]*$', re.I)
F_INTERFACE_RE = re.compile(r'^[ \t]*(?:abstract[ \t]+)?interface\b', re.I)
F_USE_RE = re.compile(r'^[ \t]*use\b[ \t]*(?:,[ \t]*(?:intrinsic|non_intrinsic)[ \t]*)?(?:::)?[ \t]*(\w+)', re.I | re.M)
F_CALL_RE = re.compile(r'\bcall[ \t]+(\w+)\b|(?<![\w%])(\w+)[ \t]*\(', re.I)
F_MASK_RE = re.compile(r"'(?:[^'\n]|'')*'|\"(?:[^\"\n]|\"\")*\"|![^\n]*")
F_KEYWORDS = {'if', 'call', 'allocate', 'deallocate', 'write', 'read', 'print', 'open', 'close', 'format', 'select',
              'case', 'where', 'forall', 'do', 'while', 'return', 'stop', 'intent', 'dimension', 'size', 'real', 'int',
              'character', 'integer', 'logical', 'complex', 'type', 'class', 'len', 'kind', 'present', 'allocated',
              'associated', 'trim', 'adjustl', 'abs', 'max', 'min', 'mod', 'sqrt', 'exp', 'log', 'sum', 'shape'}


def fortran_code(rel, text):
    lines = text.split('\n')
    if os.path.splitext(rel)[1].lower() in ('.f', '.for', '.f77'):
        body = [x for x in lines if x.strip() and x[:1] not in 'cC*!dD']
        if body and sum(1 for x in body if re.match(r'[ 0-9]{5}', x)) >= 0.8 * len(body):
            lines = [' ' * len(x) if x[:1] in 'cC*!dD' else x[:72] + ' ' * max(len(x) - 72, 0) for x in lines]
    return mask_keep('\n'.join(lines), F_MASK_RE)


def fortran_extract(u, ctx):
    code = fortran_code(u.rel, u.text)
    ents, stack, offset = [], [], 0
    for line in code.split('\n'):
        start, offset = offset, offset + len(line) + 1
        stop = start + len(line)
        if F_END_RE.match(line):
            if stack:
                kind, idx = stack.pop()
                if idx is not None:
                    ents[idx] = ents[idx]._replace(end=stop)
            continue
        if F_INTERFACE_RE.match(line):
            stack.append(('interface', None))
            continue
        if any(k == 'interface' for k, _ in stack):
            continue
        t = F_TYPE_RE.match(line)
        if t:
            name = t.group(2) or t.group(3)
            parent = next((ents[i].name for k, i in reversed(stack) if k in ('module', 'program') and i is not None), None)
            ents.append(Ent('class', name, start, sig=line.strip(), parent=parent))
            stack.append(('type', len(ents) - 1))
            base = re.search(r'extends[ \t]*\([ \t]*(\w+)', t.group(1) or '', re.I)
            if base:
                u.links.append((('c', name), 'inherits', 'ftype', base.group(1).lower()))
            continue
        m = F_UNIT_RE.match(line)
        if not m or not m.group(3) or m.group(3).lower() == 'procedure':
            continue
        kind = ' '.join(m.group(1).lower().split())
        name = m.group(3)
        parent = next((ents[i].name for k, i in reversed(stack) if k in ('module', 'program', 'submodule') and i is not None), None)
        is_class = kind in ('program', 'module', 'submodule', 'block data', 'blockdata')
        ents.append(Ent('class' if is_class else 'function', name, start, sig=' '.join(line.split()), parent=parent,
                        doc=comment_doc(u.text, start, ('!',))))
        stack.append((kind.split()[0] if is_class else kind, len(ents) - 1))
        if kind == 'module':
            u.facts['modules'].append(name.lower())
        elif kind == 'submodule' and m.group(2):
            u.links.append((None, 'import', 'fmod', m.group(2).strip('() \t').split(':')[0].lower()))
        elif not is_class:
            u.facts['procs'].append((name.lower(), 'sub' if kind == 'subroutine' else 'fn'))
    ents = [e if e.end is not None else e._replace(end=len(code)) for e in ents]
    spans = Spans(ents)
    for m in F_USE_RE.finditer(code):
        u.links.append((None, 'import', 'fmod', m.group(1).lower()))
        u.facts['uses'].append(m.group(1).lower())
    for m in F_CALL_RE.finditer(code):
        owner = spans.at(m.start())
        if owner is None or F_UNIT_RE.match(line_text(code, code.rfind('\n', 0, m.start()) + 1)):
            continue
        name = (m.group(1) or m.group(2)).lower()
        if name not in F_KEYWORDS:
            u.links.append((owner, 'call', 'fcall', (name, 'sub' if m.group(1) else 'fn')))
    return ents


APEX_MASK_RE = re.compile(r"//[^\n]*|/\*.*?\*/|'(?:\\.|[^'\\\n])*'", re.S)
APEX_CLASS_RE = re.compile(
    r'\b(?:(?:public|private|protected|global|abstract|virtual|with|without|inherited|sharing|static|override|final)\s+)*'
    r'(class|interface|enum)\s+(\w+)((?:\s+extends\s+[\w.<>]+)?(?:\s+implements\s+[\w.<>,\s]+?)?)\s*\{', re.I)
APEX_METHOD_RE = re.compile(
    r'^[ \t]*(?:@\w+(?:\([^)]*\))?\s*)*(?:(?:public|private|protected|global|static|override|virtual|abstract|webservice'
    r'|testmethod|final|transient)\s+)*([\w.<>,\[\] ]+?)\s+(\w+)\s*\(([^;{}]*?)\)\s*\{', re.I | re.M)
APEX_TRIGGER_RE = re.compile(r'\btrigger\s+(\w+)\s+on\s+(\w+)\s*\(', re.I)
APEX_CALL_RE = re.compile(r'\b(\w+)\s*\.\s*(\w+)\s*\(|(?<![\w.])(\w+)\s*\(|\bnew\s+(\w+)\s*[(<\[]', re.I)
APEX_KEYWORDS = {'if', 'for', 'while', 'switch', 'catch', 'when', 'return', 'else', 'do', 'try', 'new', 'super', 'this',
                 'system', 'database', 'string', 'math', 'json', 'test', 'schema', 'limits', 'userinfo'}


def apex_extract(u, ctx):
    code = mask_keep(u.text, APEX_MASK_RE)
    ents, classes = [], []
    for m in APEX_CLASS_RE.finditer(code):
        end = match_close(code, m.end() - 1)
        parent = next((c.name for c in reversed(classes) if c.pos < m.start() < c.end), None)
        ent = Ent('class', m.group(2), m.start(), end=end, sig=' '.join(m.group().rstrip('{').split()), parent=parent,
                  doc=block_doc(u.text, m.start()))
        ents.append(ent)
        classes.append(ent)
        for base in re.findall(r'\b(?:extends|implements)\s+([\w.<>,\s]+)', m.group(3) or '', re.I):
            for b in re.findall(r'(\w+)(?:<[^>]*>)?', base):
                if b.lower() not in ('extends', 'implements'):
                    u.links.append((('c', m.group(2)), 'inherits', 'apexclass', b))
    for m in APEX_TRIGGER_RE.finditer(code):
        brace = code.find('{', m.end())
        end = match_close(code, brace) if brace >= 0 else len(code)
        ents.append(Ent('class', m.group(1), m.start(), end=end, sig=' '.join(line_text(code, m.start()).split())))
        u.links.append((('c', m.group(1)), 'data', 'table', [m.group(2)]))
        u.facts['triggers'].append(m.group(1))
    for m in APEX_METHOD_RE.finditer(code):
        if m.group(2).lower() in C_KEYWORDS or (m.group(1).split() or [""])[-1].lower() in C_KEYWORDS:
            continue
        owner = next((c.name for c in reversed(classes) if c.pos < m.start() < c.end), None)
        if owner is None or any(e.kind == 'method' and e.pos < m.start() < e.end for e in ents):
            continue
        end = match_close(code, m.end() - 1)
        ents.append(Ent('method', f'{owner}.{m.group(2)}', m.start(), end=end, parent=owner,
                        sig=' '.join(m.group().rstrip('{').split()), doc=block_doc(u.text, m.start())))
    spans = Spans(ents)
    for start in [m.start() for m in re.finditer(r'\[\s*select\b', code, re.I)]:
        body = code[start + 1:match_close(code, start, '[]') - 1]
        while True:
            reduced = re.sub(r'\([^()]*\)', ' ', body)
            if reduced == body:
                break
            body = reduced
        found = re.search(r'\bfrom\s+(\w+)', body, re.I)
        if found:
            u.links.append((spans.at(start), 'data', 'table', [found.group(1)]))
    for m in APEX_CALL_RE.finditer(code):
        key = spans.at(m.start())
        if key is None or key[0] != 'f' and key[1] not in u.facts['triggers']:
            continue
        cls = key[1].rsplit('.', 1)[0]
        if m.group(1):
            u.links.append((key, 'call', 'apexmeth', (m.group(1), m.group(2))))
        elif m.group(3) and m.group(3).lower() not in APEX_KEYWORDS and code[max(0, m.start() - 4):m.start()].strip().lower() != 'new':
            u.links.append((key, 'call', 'apexmeth', (cls, m.group(3))))
        elif m.group(4):
            u.links.append((key, 'ref', 'apexclass', m.group(4)))
    return ents


ABAP_BLOCKS = [
    (re.compile(r'^[ \t]*class[ \t]+([\w/]+)[ \t]+definition\b(?![^.\n]*\b(?:deferred|load)\b)', re.I), 'class', 'endclass'),
    (re.compile(r'^[ \t]*class[ \t]+([\w/]+)[ \t]+implementation\b', re.I), 'class', 'endclass'),
    (re.compile(r'^[ \t]*interface[ \t]+([\w/]+)(?![ \t]+(?:deferred|load))[ \t]*(?:public)?[ \t]*\.', re.I), 'class', 'endinterface'),
    (re.compile(r'^[ \t]*method[ \t]+([\w/~]+)[^.\n]*\.', re.I), 'method', 'endmethod'),
    (re.compile(r'^[ \t]*form[ \t]+([\w/-]+)', re.I), 'function', 'endform'),
    (re.compile(r'^[ \t]*function[ \t]+([\w/]+)[ \t]*\.', re.I), 'function', 'endfunction'),
    (re.compile(r'^[ \t]*module[ \t]+([\w/]+)[ \t]+(?:input|output)\b', re.I), 'function', 'endmodule'),
]
ABAP_REPORT_RE = re.compile(r'^[ \t]*(?:report|program|function-pool)[ \t]+([\w/]+)', re.I | re.M)
ABAP_MASK_RE = re.compile(r"^\*[^\n]*|'(?:[^'\n]|'')*'|`[^`\n]*`|\|[^|\n]*\||\"[^\n]*", re.M)
ABAP_CALL_RE = re.compile(
    r"\bperform[ \t]+([\w/-]+)|\bcall[ \t]+function[ \t]+'([\w/]+)'|([\w/]+)=>([\w/~]+)|\bme->([\w/~]+)", re.I)
ABAP_REF_RE = re.compile(r'\b(?:new[ \t]+([\w/]+)[ \t]*\(|type[ \t]+ref[ \t]+to[ \t]+([\w/]+))', re.I)
ABAP_INHERIT_RE = re.compile(r'\b(?:inheriting[ \t]+from|interfaces)[ \t]+([\w/]+)', re.I)
ABAP_INCLUDE_RE = re.compile(r'^[ \t]*include[ \t]+([\w/]+)[ \t]*\.', re.I | re.M)


def abap_extract(u, ctx):
    calls = mask_keep(u.text, re.compile(r"^\*[^\n]*|\"[^\n]*", re.M))
    code = mask_keep(u.text, ABAP_MASK_RE)
    ents, stack, offset, current = [], [], 0, None
    report = ABAP_REPORT_RE.search(code)
    if report:
        ents.append(Ent('class', report.group(1).lower(), report.start(), end=len(code),
                        sig=' '.join(line_text(code, report.start()).split())))
    for line in code.split('\n'):
        start, offset = offset, offset + len(line) + 1
        low = line.strip().lower()
        if stack and re.match(rf'{stack[-1][0]}\b', low):
            closer, idx = stack.pop()
            ents[idx] = ents[idx]._replace(end=start + len(line))
            continue
        for pattern, kind, closer in ABAP_BLOCKS:
            m = pattern.match(line)
            if not m:
                continue
            name = m.group(1).lower()
            if kind == 'class':
                current = name
            full = f'{current}.{name}' if kind == 'method' and current else name
            ents.append(Ent('method' if kind == 'method' and current else 'class' if kind == 'class' else 'function', full, start,
                            sig=' '.join(line.split()), parent=current if kind == 'method' else None))
            stack.append((closer, len(ents) - 1))
            break
    ents = [e if e.end is not None else e._replace(end=len(code)) for e in ents]
    spans = Spans(ents)
    for m in ABAP_CALL_RE.finditer(calls):
        key = spans.at(m.start())
        if m.group(1):
            u.links.append((key, 'call', 'abapform', m.group(1).lower()))
        elif m.group(2):
            u.links.append((key, 'call', 'abapfunc', m.group(2).lower()))
        elif m.group(3):
            u.links.append((key, 'call', 'abapmeth', (m.group(3).lower(), m.group(4).lower())))
        elif m.group(5) and key and '.' in key[1]:
            u.links.append((key, 'call', 'abapmeth', (key[1].rsplit('.', 1)[0].lower(), m.group(5).lower())))
    for m in ABAP_REF_RE.finditer(code):
        u.links.append((spans.at(m.start()), 'ref', 'abapclass', (m.group(1) or m.group(2)).lower()))
    for m in ABAP_INHERIT_RE.finditer(code):
        key = spans.at(m.start())
        if key and key[0] == 'c':
            u.links.append((key, 'inherits', 'abapclass', m.group(1).lower()))
    for m in ABAP_INCLUDE_RE.finditer(code):
        u.links.append((None, 'import', 'abapinclude', m.group(1).lower()))
    for m in SQL_USE_RE.finditer(code):
        if re.search(r'\b(?:select|update|modify|delete|insert)\b', line_text(code, code.rfind('\n', 0, m.start()) + 1), re.I):
            u.links.append((spans.at(m.start()), 'data', 'table', sql_parts(m.group(1))))
    return ents


JVM_EXTS = ('.kt', '.java', '.scala', '.groovy')
APPLE_EXTS = ('.swift', '.m', '.mm', '.h')
ANDROID_CLASS_RE = re.compile(
    r'''(?:tools:context|android:name|app:layout_behavior|class|android:targetActivity)\s*=\s*"(\.?[A-Za-z_][\w.$]*)"''')
ANDROID_TAG_RE = re.compile(r'<([a-z][\w]*(?:\.[\w$]+)+)(?=[\s/>])')
ANDROID_RES_RE = re.compile(r'@(layout|navigation|menu)/(\w+)')
MANIFEST_RE = re.compile(r'<(activity|activity-alias|service|receiver|provider|application)\b[^>]*?'
                         r'\bandroid:(?:name|targetActivity)\s*=\s*"([^"]+)"', re.S)
IOS_CLASS_RE = re.compile(r'\bcustomClass="(\w+)"')


def android_extract(u, ctx):
    found = [m.group(1) for m in ANDROID_CLASS_RE.finditer(u.text)] + [m.group(1) for m in ANDROID_TAG_RE.finditer(u.text)]
    for name in sorted(set(found)):
        if ('.' in name or name[0].isupper()) and not name.startswith(('android.', 'androidx.', 'com.google.android.material.')):
            u.links.append((None, 'ref', 'class', (name, JVM_EXTS, name)))
    for kind, name in sorted(set(ANDROID_RES_RE.findall(u.text))):
        u.links.append((None, 'ref', 'res', (kind, name)))
    return []


def manifest_extract(u, ctx):
    package = re.search(r'\bpackage\s*=\s*"([\w.]+)"', u.text)
    for kind, name in MANIFEST_RE.findall(u.text):
        fqn = (package.group(1) if package else '') + name if name.startswith('.') else name
        u.links.append((None, 'ref', 'class', (fqn, JVM_EXTS, fqn)))
    return []


def ios_extract(u, ctx):
    for name in sorted(set(IOS_CLASS_RE.findall(u.text))):
        u.links.append((None, 'ref', 'class', (name, APPLE_EXTS, name)))
    return []


def sobject_extract(u, ctx):
    name = u.rel.rsplit('/', 1)[-1].split('.')[0]
    label = re.search(r'<label>([^<]+)</label>', u.text)
    return [Ent('class', name, 0, table=name, end=len(u.text), sig=f'SObject {name}', doc=label.group(1) if label else None)]


HANDLER_EXTS = ('.py', '.js', '.mjs', '.cjs', '.ts', '.mts', '.rb', '.go', '.java', '.kt', '.cs', '.php', '.ps1', '.sh')


def strip_exts(rel):
    head, _, name = rel.rpartition('/')
    stem = name.split('.')[0] if not name.startswith('.') else name
    return f'{head}/{stem}' if head else stem


class Linker:
    def __init__(self, units, g, tables):
        self.units, self.g, self.tables = units, g, tables
        self.files = sorted(set(units) | {n[2:] for n, m in g.nodes.items() if n.startswith('m:') and m.get('kind') == 'module'})
        self.fileset = set(self.files)
        self.by_base = defaultdict(list)
        for f in self.files:
            self.by_base[f.rsplit('/', 1)[-1]].append(f)
        self.cache = {}

    def run(self):
        for rel in sorted(self.units):
            u = self.units[rel]
            for src, kind, how, spec in u.links:
                sid = f'{src[0]}:{rel}:{src[1]}' if src else u.mid
                for target in getattr(self, f'r_{how}')(u, spec):
                    if target != sid:
                        self.g.edge(sid, target, kind)

    def cached(self, key, build):
        if key not in self.cache:
            self.cache[key] = build()
        return self.cache[key]

    def tail(self, spec):
        spec = spec.lstrip('/')
        return [f for f in self.by_base.get(spec.rsplit('/', 1)[-1], ()) if f == spec or f.endswith('/' + spec)]

    def module(self, rel):
        return [f'm:{rel}'] if rel in self.fileset and f'm:{rel}' in self.g.nodes else []

    def pick(self, rel, found):
        found = sorted(set(found))
        if len({t for t, _ in found}) <= 1:
            return [found[0][0]] if found else []
        same = [t for t, f in found if f == rel]
        if same:
            return same[:1]
        best = closest(rel, [f for _, f in found])
        return [t for t, f in found if f == best][:1] if best else []

    def pick_file(self, rel, files):
        return self.pick(rel, [(f'm:{f}', f) for f in files if f'm:{f}' in self.g.nodes])

    def symbols(self, fmts, lower=True):
        def build():
            out = defaultdict(list)
            for rel in sorted(self.units):
                u = self.units[rel]
                if u.fmt in fmts:
                    for kind, name, sid in u.symbols:
                        if kind == 'endpoint':
                            continue
                        for key in {name, name.rsplit('.', 1)[-1]}:
                            out[key.lower() if lower else key].append((sid, rel))
            return out
        return self.cached(('symbols', tuple(sorted(fmts)), lower), build)

    def local(self, u, name, kinds=None):
        name = name.lower()
        hits = [sid for kind, n, sid in u.symbols if (kinds is None or kind in kinds) and n.lower() == name]
        hits = hits or [sid for kind, n, sid in u.symbols if (kinds is None or kind in kinds) and n.rsplit('.', 1)[-1].lower() == name]
        return hits[:1]

    def classes(self):
        def build():
            out = defaultdict(list)
            for nid, meta in self.g.nodes.items():
                if meta.get('kind') == 'class':
                    out[meta['name'].rsplit('.', 1)[-1]].append((nid, meta['file']))
            return out
        return self.cached('classes', build)

    def r_local(self, u, key):
        return [f'{key[0]}:{u.rel}:{key[1]}']

    def r_path(self, u, spec):
        bases, path = spec
        for base in list(bases) + ['']:
            hit = join_path(base, path)
            if hit in self.fileset:
                return self.module(hit)
        return []

    def r_role(self, u, name):
        role = ansible_role(u.rel)[0]
        bases = [dir_of(u.rel) + 'roles/'] + ([dir_of(role)] if role else [])
        for candidate in [name] + ([name.rsplit('.', 1)[-1]] if '.' in name else []):
            for main in ('tasks/main.yml', 'tasks/main.yaml', 'meta/main.yml', 'meta/main.yaml'):
                near = [f'{b}{candidate}/{main}' for b in bases if f'{b}{candidate}/{main}' in self.fileset]
                hits = near[:1] or self.tail(f'roles/{candidate}/{main}') or self.tail(f'{candidate}/{main}')
                if hits:
                    return self.pick_file(u.rel, hits)
        return []

    def r_handler(self, u, spec):
        role, name = spec

        def build():
            out = defaultdict(list)
            for rel in sorted(self.units):
                for hname, key in self.units[rel].facts.get('handlers', ()):
                    out[hname].append((f'{key[0]}:{rel}:{key[1]}', rel, ansible_role(rel)[0]))
            return out
        found = self.cached('handlers', build).get(name, [])
        same = [(s, f) for s, f, r in found if r == role and role is not None] or [(s, f) for s, f, r in found if f == u.rel]
        return self.pick(u.rel, same or [(s, f) for s, f, _ in found])

    def r_model(self, u, name):
        def build():
            out = defaultdict(list)
            for rel in sorted(self.units):
                unit = self.units[rel]
                if unit.fmt == 'dbt' and not JMACRO_RE.search(unit.text):
                    out[os.path.splitext(rel.rsplit('/', 1)[-1])[0]].append(rel)
                for model in unit.facts.get('models', ()):
                    out[model].append(rel)
            return out
        return self.pick_file(u.rel, self.cached('models', build).get(name, []))

    def r_source(self, u, name):
        def build():
            out = defaultdict(list)
            for rel in sorted(self.units):
                for full in self.units[rel].facts.get('sources', ()):
                    out[full].append((f'c:{rel}:{full}', rel))
            return out
        return self.pick(u.rel, self.cached('sources', build).get(name, []))

    def macro_in(self, u, spec, name):
        files = self.r_template(u, ('import', spec))
        return [f'f:{f[2:]}:{name}' for f in files if f'f:{f[2:]}:{name}' in self.g.nodes]

    def r_macro(self, u, spec):
        alias, name = spec
        if alias:
            target = next((s for a, s in u.facts.get('aliases', ()) if a == alias), None)
            return self.macro_in(u, target, name) if target else []
        hit = [sid for kind, n, sid in u.symbols if kind == 'function' and n == name]
        if hit:
            return hit
        imported = next(((orig, s) for local, orig, s in u.facts.get('imported', ()) if local == name), None)
        if imported:
            return self.macro_in(u, imported[1], imported[0])
        if u.fmt in ('dbt', 'dbtyml'):
            return self.pick(u.rel, self.symbols({'dbt'}, lower=False).get(name, []))
        return []

    def r_template(self, u, spec):
        tag, path = spec
        path = re.sub(r'^@[\w-]+/', '', path.split('::')[-1]).strip()
        if not path or '{' in path or '$' in path:
            return []
        name = u.rel.rsplit('/', 1)[-1]
        compound = name[name.find('.'):] if '.' in name else ''
        variants = [path] + [path + e for e in dict.fromkeys((compound, '.liquid', '.html', '.njk', '.j2')) if e and not path.endswith(e)]
        here = dir_of(u.rel)
        for v in variants:
            hit = join_path(here, v)
            if hit in self.fileset and hit != u.rel:
                return self.module(hit)
        prefer = {'layout': ('layout', '_layouts', 'layouts'), 'render': ('snippets', '_includes'), 'include': ('_includes', 'snippets'),
                  'section': ('sections',)}.get(tag, ())
        for v in variants:
            hits = [h for h in self.tail(v) if h != u.rel]
            if not hits:
                continue
            for d in prefer:
                pref = [h for h in hits if h.endswith(f'{d}/{v}')]
                if pref:
                    return self.pick_file(u.rel, pref)
            tpl = [h for h in hits if h.endswith(f'templates/{v}')]
            return self.pick_file(u.rel, tpl or hits)
        return []

    def r_define(self, u, spec):
        root, name = spec
        found = self.symbols({'helm'}, lower=False).get(name, [])
        found = [(s, f) for s, f in found if s.endswith(f':{name}')]
        same = [(s, f) for s, f in found if root is not None and f.startswith(root)]
        return self.pick(u.rel, same or found)

    def r_values(self, u, root):
        return self.module(f'{root}values.yaml') or self.module(f'{root}values.yml')

    def r_chart(self, u, spec):
        here, dep, repo = spec
        if repo.startswith('file://'):
            return self.module(join_path(here, repo[7:].rstrip('/') + '/Chart.yaml'))
        local = self.module(f'{here}charts/{dep}/Chart.yaml')
        if local:
            return local
        charts = [rel for rel in sorted(self.units) if dep in self.units[rel].facts.get('chart', ())]
        return self.pick_file(u.rel, charts)

    def r_pulumi(self, u, here):
        for name in ('Pulumi.yaml', 'Pulumi.yml'):
            unit = self.units.get(f'{here}{name}')
            if unit and unit.facts.get('project'):
                return [f'c:{unit.rel}:{unit.facts["project"][0]}']
        return []

    def r_handler_code(self, u, spec):
        here, code, handler, runtime = spec
        if not handler:
            return []
        base = join_path(here, code) if code else here.rstrip('/')
        base = '' if base == '.' else base
        if '::' in handler:
            left, method = handler.split('::', 1)
            cls = left.rsplit('.', 1)[-1]
            found = self.pick(u.rel, self.classes().get(cls, []))
            meth = [f'f:{c.split(":", 2)[1]}:{cls}.{method}' for c in found]
            return [m for m in meth if m in self.g.nodes] or found
        if '.' not in handler:
            return []
        path, fn = handler.rsplit('.', 1)
        for stem in dict.fromkeys((path, path.replace('.', '/'))):
            for ext in HANDLER_EXTS:
                rel = join_path(base, stem + ext) if base else join_path('', stem + ext)
                if rel in self.fileset:
                    fid = f'f:{rel}:{fn}'
                    return [fid] if fid in self.g.nodes else self.module(rel)
        return []

    def r_handles(self, u, spec):
        target, fallback = spec
        return self.r_handler_code(u, target) or self.r_local(u, fallback)

    def r_class(self, u, spec):
        name, exts, hint = spec
        simple = name.rsplit('.', 1)[-1].split('$')[0]
        found = [(n, f) for n, f in self.classes().get(simple, []) if f.endswith(exts)]
        if '.' in hint.strip('.'):
            pkg = '/' + '/'.join(hint.strip('.').split('.')[:-1]) + '/'
            narrowed = [(n, f) for n, f in found if pkg in '/' + f]
            found = narrowed or found
        return self.pick(u.rel, found)

    def r_component(self, u, name):
        files = [f for f in self.by_base.get(f'{name}.razor', [])]
        return self.pick_file(u.rel, files) or self.r_class(u, (name, ('.cs',), name))

    def r_view(self, u, name):
        path = name.lstrip('~').lstrip('/')
        if not path.endswith('.cshtml'):
            path += '.cshtml'
        here = dir_of(u.rel)
        while True:
            for hit in (join_path(here, path), join_path(here, 'Shared/' + path)):
                if hit in self.fileset and hit != u.rel:
                    return self.module(hit)
            if not here:
                break
            here = dir_of(here.rstrip('/'))
        hits = self.tail(path)
        shared = [h for h in hits if '/Shared/' in f'/{h}']
        return self.pick_file(u.rel, shared or hits)

    def r_viewcomponent(self, u, name):
        return self.r_class(u, (f'{name}ViewComponent', ('.cs',), name)) or self.r_class(u, (name, ('.cs',), name))

    def r_blade(self, u, spec):
        kind, name = spec
        name = name.split('::')[-1]
        parts = name.replace(':', '.').split('.')
        if kind == 'view':
            hits = self.tail('/'.join(parts) + '.blade.php')
            return self.pick_file(u.rel, [h for h in hits if '/views/' in f'/{h}'] or hits)
        pascal = ''.join(p.title() for p in re.split(r'[-_]', parts[-1]))
        if kind == 'comp':
            path = '/'.join(parts)
            views = self.tail(f'components/{path}.blade.php') or self.tail(f'components/{path}/index.blade.php')
            classes = [(n, f) for n, f in self.classes().get(pascal, []) if f.endswith('.php') and 'Component' in f]
            return self.pick_file(u.rel, views) + self.pick(u.rel, classes)
        views = self.tail('livewire/' + '/'.join(parts) + '.blade.php')
        classes = [(n, f) for n, f in self.classes().get(pascal, []) if f.endswith('.php') and 'Livewire' in f]
        return self.pick(u.rel, classes) + self.pick_file(u.rel, views)

    def views(self):
        def build():
            out = defaultdict(list)
            for rel in sorted(self.units):
                if self.units[rel].fmt == 'erb':
                    out[strip_exts(rel)].append(rel)
            return out
        return self.cached('erb', build)

    def r_partial(self, u, spec):
        kind, path = spec
        path = path.lstrip('/')
        index = self.views()
        head, _, leaf = path.rpartition('/')
        leaf = leaf if kind in ('template',) else f'_{leaf}' if not leaf.startswith('_') else leaf
        if kind == 'layout' and not head:
            head = 'layouts'
        want = f'{head}/{leaf}' if head else leaf
        here = dir_of(u.rel).rstrip('/')
        if not head:
            local = index.get(f'{here}/{leaf}' if here else leaf, [])
            if local:
                return self.pick_file(u.rel, local)
            want = f'application/{leaf}'
        hits = [f for key, files in index.items() if key == want or key.endswith('/' + want) for f in files]
        views = [h for h in hits if f'/views/{want}' in f'/{strip_exts(h)}']
        return self.pick_file(u.rel, views or hits)

    def r_hbs(self, u, name):
        hits = [f for f in self.files if f.endswith(('.hbs', '.handlebars', '.mustache')) and
                (strip_exts(f) == name or strip_exts(f).endswith('/' + name))]
        partials = [h for h in hits if 'partial' in h.lower()]
        return self.pick_file(u.rel, partials or hits)

    def r_ejs(self, u, path):
        for v in (path, path + '.ejs'):
            hit = join_path(dir_of(u.rel), v)
            if hit in self.fileset:
                return self.module(hit)
        return self.pick_file(u.rel, self.tail(path if path.endswith('.ejs') else path + '.ejs'))

    def r_res(self, u, spec):
        kind, name = spec
        root = u.rel[:u.rel.rfind('/res/') + 5] if '/res/' in f'/{u.rel}' else ''
        hits = [f for f in self.by_base.get(f'{name}.xml', []) if f.split('/')[-2].split('-')[0] == kind]
        near = [h for h in hits if root and h.startswith(root)]
        return self.pick_file(u.rel, near or hits)

    def table_nodes(self):
        def build():
            out = defaultdict(list)
            for nid, meta in self.g.nodes.items():
                if meta.get('table'):
                    out[meta['table'].lower()].append((nid, meta['file'], meta.get('lang')))
            return out
        return self.cached('tables', build)

    def r_table(self, u, parts):
        if not parts:
            return []
        found = self.table_nodes().get(parts[-1].lower(), [])
        same = [(n, f) for n, f, _ in found if f == u.rel]
        if same:
            return same[:1]
        sql = [(n, f) for n, f, lang in found if lang in ('sql', 'object') or f.endswith('.object-meta.xml')]
        return self.pick(u.rel, sql or [(n, f) for n, f, _ in found])

    def r_sqlcall(self, u, parts):
        if not parts:
            return []
        index = self.symbols({'sql'})
        if len(parts) >= 2:
            full = f'{parts[-2]}.{parts[-1]}'.lower()
            hits = [(s, f) for s, f in index.get(full, []) if s.lower().endswith(full)]
            if hits:
                return self.pick(u.rel, hits)
        name = parts[-1].lower()
        hits = [(s, f) for s, f in index.get(name, []) if s.split(':', 2)[2].lower().rsplit('.', 1)[-1] == name
                and self.g.nodes[s]['kind'] in ('function', 'method')]
        return self.pick(u.rel, hits)

    def r_cobpara(self, u, name):
        return self.local(u, name, ('function',))

    def r_cobprog(self, u, name):
        found = [(s, f) for s, f in self.symbols({'cobol'}).get(name.lower(), []) if self.g.nodes[s]['kind'] == 'class']
        if found:
            return self.pick(u.rel, found)
        return self.pick_file(u.rel, [f for f in self.files if f.rsplit('/', 1)[-1].split('.')[0].upper() == name
                                      and self.units.get(f) and self.units[f].fmt == 'cobol'])

    def r_copybook(self, u, name):
        def build():
            out = defaultdict(list)
            for f in self.files:
                base = f.rsplit('/', 1)[-1]
                stem, ext = os.path.splitext(base)
                if ext.lower() in COBOL_EXTS or not ext:
                    out[stem.upper()].append(f)
            return out
        hits = [f for f in self.cached('copybooks', build).get(name, []) if f != u.rel]
        cpy = [f for f in hits if f.lower().endswith('.cpy')]
        return self.pick_file(u.rel, cpy or hits)

    def r_vbcall(self, u, spec):
        cls, qual, name = spec
        index = self.symbols({'vb'})
        if qual:
            hits = [(s, f) for s, f in index.get(name.lower(), []) if s.lower().endswith(f':{qual}.{name}'.lower())]
            return self.pick(u.rel, hits)
        if cls:
            own = f'f:{u.rel}:{cls}.{name}'.lower()
            hit = [sid for kind, n, sid in u.symbols if sid.lower() == own]
            if hit:
                return hit
        hits = [(s, f) for s, f in index.get(name.lower(), []) if self.g.nodes[s]['kind'] in ('function', 'method')]
        same = [(s, f) for s, f in hits if f == u.rel]
        if same:
            return [same[0][0]]
        return self.pick(u.rel, hits) if len({s for s, _ in hits}) == 1 and len(name) > 2 else []

    def fortran(self):
        def build():
            mods, procs = defaultdict(list), defaultdict(list)
            for rel in sorted(self.units):
                unit = self.units[rel]
                for name in unit.facts.get('modules', ()):
                    mods[name].append(rel)
                for name, kind in unit.facts.get('procs', ()):
                    procs[name].append((rel, kind))
            return mods, procs
        return self.cached('fortran', build)

    def r_fmod(self, u, name):
        return self.pick_file(u.rel, [f for f in self.fortran()[0].get(name, []) if f != u.rel])

    def r_fcall(self, u, spec):
        name, kind = spec
        mods, procs = self.fortran()
        local = [k for n, k in u.facts.get('procs', ()) if n == name]
        if local and (kind == 'fn') <= (local[0] == 'fn'):
            return self.local(u, name, ('function',))
        used = {f for m in u.facts.get('uses', ()) for f in mods.get(m, [])}
        hits = [(rel, k) for rel, k in procs.get(name, []) if rel != u.rel and (kind == 'sub' or k == 'fn')]
        scoped = [rel for rel, _ in hits if rel in used]
        rels = scoped or ([rel for rel, _ in hits] if kind == 'sub' and len(hits) == 1 else [])
        found = [(sid, rel) for rel in rels for k, n, sid in self.units[rel].symbols if n.lower() == name and k == 'function']
        return self.pick(u.rel, found)

    def r_ftype(self, u, name):
        found = [(s, f) for s, f in self.symbols({'fortran'}).get(name, []) if self.g.nodes[s]['kind'] == 'class']
        return self.pick(u.rel, found)

    def r_apexclass(self, u, name):
        found = [(s, f) for s, f in self.symbols({'apex'}).get(name.lower(), []) if self.g.nodes[s]['kind'] == 'class']
        return self.pick(u.rel, found)

    def r_apexmeth(self, u, spec):
        cls, name = spec
        full = f'{cls}.{name}'.lower()
        found = [(s, f) for s, f in self.symbols({'apex'}).get(full, [])]
        return self.pick(u.rel, found)

    def r_abapform(self, u, name):
        local = self.local(u, name, ('function',))
        if local:
            return local
        return self.pick(u.rel, [(s, f) for s, f in self.symbols({'abap'}).get(name, []) if self.g.nodes[s]['kind'] == 'function'])

    def r_abapfunc(self, u, name):
        return self.r_abapform(u, name)

    def r_abapmeth(self, u, spec):
        cls, name = spec
        return self.pick(u.rel, self.symbols({'abap'}).get(f'{cls}.{name}', []))

    def r_abapclass(self, u, name):
        return self.pick(u.rel, [(s, f) for s, f in self.symbols({'abap'}).get(name, []) if self.g.nodes[s]['kind'] == 'class'])

    def r_abapinclude(self, u, name):
        name = name.replace('/', '#')
        return self.pick_file(u.rel, [f for f in self.files if f.endswith('.abap') and f != u.rel and
                                      name in f.rsplit('/', 1)[-1].lower().split('.')[:-1]])


EXTRACTORS = {
    'sql': sql_extract, 'dbt': dbt_extract, 'tpl': tpl_extract, 'helm': helm_extract, 'chart': chart_extract,
    'blade': blade_extract, 'erb': erb_extract, 'hbs': hbs_extract, 'ejs': ejs_extract, 'razor': razor_extract,
    'ansible': ansible_extract, 'cfn': cfn_extract, 'serverless': serverless_extract, 'pulumi': pulumi_extract,
    'pulumistack': pulumistack_extract, 'dbtproject': dbtproject_extract, 'dbtyml': dbtyml_extract,
    'bicep': bicep_extract, 'cobol': cobol_extract, 'vb': vb_extract, 'fortran': fortran_extract, 'apex': apex_extract,
    'abap': abap_extract, 'android': android_extract, 'manifest': manifest_extract, 'ios': ios_extract,
    'sobject': sobject_extract, 'cls': lambda u, ctx: [],
}
