import configparser
import json
import os
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ECOSYSTEMS = ('npm', 'jsr', 'pypi', 'go', 'cargo', 'maven', 'nuget', 'composer', 'rubygems', 'hex', 'pub',
              'swiftpm', 'cocoapods')
SCOPE_RANK = {'runtime': 0, 'peer': 1, 'optional': 2, 'dev': 3}
SKIP_PARTS = {'node_modules', 'vendor', 'fixtures', 'fixture', '__fixtures__', 'testdata', 'bower_components'}
MAX_HEADS = 20000
HEAD_BYTES = 8192
LANG_ECO = {
    'py': 'pypi', 'python': 'pypi', 'ts': 'npm', 'tsx': 'npm', 'js': 'npm', 'jsx': 'npm', 'javascript': 'npm',
    'typescript': 'npm', 'vue': 'npm', 'svelte': 'npm', 'go': 'go', 'rust': 'cargo', 'java': 'jvm', 'kotlin': 'jvm',
    'scala': 'jvm', 'groovy': 'jvm', 'csharp': 'nuget', 'cs': 'nuget', 'fsharp': 'nuget', 'vb': 'nuget',
    'php': 'composer', 'ruby': 'rubygems', 'elixir': 'hex', 'dart': 'pub', 'swift': 'swift', 'objc': 'swift',
}
JS_EXTS = ('.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.mts', '.cts', '.vue', '.svelte')
JVM_EXTS = ('.java', '.kt', '.kts', '.scala', '.groovy')
NODE_BUILTINS = frozenset((
    'assert async_hooks buffer child_process cluster console constants crypto dgram diagnostics_channel dns domain '
    'events fs http http2 https inspector module net os path perf_hooks process punycode querystring readline repl '
    'stream string_decoder sys timers tls trace_events tty url util v8 vm wasi worker_threads zlib test sqlite sea'
).split())
NPM_NAME_RE = re.compile(r'^(?:@[a-z0-9~][a-z0-9._~-]*/)?[a-z0-9~][a-z0-9._~-]*$')
PY_ALIASES = {
    'PIL': 'pillow', 'Image': 'pillow', 'yaml': 'pyyaml', 'sklearn': 'scikit-learn', 'skimage': 'scikit-image',
    'cv2': 'opencv-python', 'bs4': 'beautifulsoup4', 'dateutil': 'python-dateutil', 'jwt': 'pyjwt',
    'google.protobuf': 'protobuf', 'google.auth': 'google-auth', 'google.oauth2': 'google-auth',
    'google.api_core': 'google-api-core', 'googleapiclient': 'google-api-python-client', 'attr': 'attrs',
    'dotenv': 'python-dotenv', 'OpenSSL': 'pyopenssl', 'Crypto': 'pycryptodome', 'Cryptodome': 'pycryptodomex',
    'magic': 'python-magic', 'serial': 'pyserial', 'usb': 'pyusb', 'docx': 'python-docx', 'pptx': 'python-pptx',
    'multipart': 'python-multipart', 'jose': 'python-jose', 'git': 'gitpython', 'MySQLdb': 'mysqlclient',
    'zmq': 'pyzmq', 'win32api': 'pywin32', 'win32con': 'pywin32', 'win32com': 'pywin32', 'pythoncom': 'pywin32',
    'pywintypes': 'pywin32', 'wx': 'wxpython', 'gi': 'pygobject', 'Levenshtein': 'python-levenshtein',
    'slugify': 'python-slugify', 'telegram': 'python-telegram-bot', 'discord': 'discord.py', 'fitz': 'pymupdf',
    'Bio': 'biopython', 'rest_framework': 'djangorestframework', 'corsheaders': 'django-cors-headers',
    'debug_toolbar': 'django-debug-toolbar', 'environ': 'django-environ', 'mpl_toolkits': 'matplotlib',
    'pkg_resources': 'setuptools', 'grpc': 'grpcio', 'nacl': 'pynacl', 'socks': 'pysocks', 'ldap': 'python-ldap',
    'Xlib': 'python-xlib', 'websocket': 'websocket-client', 'kafka': 'kafka-python', 'memcache': 'python-memcached',
    'snappy': 'python-snappy', 'osgeo': 'gdal', 'dns': 'dnspython', '_pytest': 'pytest', 'faiss': 'faiss-cpu',
    'fontTools': 'fonttools', 'speech_recognition': 'speechrecognition', 'paho': 'paho-mqtt', 'ruamel.yaml': 'ruamel.yaml',
    'freetype': 'freetype-py', 'markdown_it': 'markdown-it-py', 'pydispatch': 'pydispatcher', 'sentry_sdk': 'sentry-sdk',
}
PY_NAMESPACES = ('google', 'azure', 'zope', 'jaraco', 'sphinxcontrib', 'backports', 'opentelemetry', 'oslo')
RUBY_STDLIB = frozenset((
    'json set yaml psych uri net/http net/https net/smtp openssl securerandom time date fileutils pathname erb logger '
    'digest digest/md5 digest/sha1 digest/sha2 base64 cgi cgi/util stringio tempfile tmpdir socket optparse ostruct '
    'benchmark open3 shellwords English forwardable singleton delegate monitor thread timeout zlib csv pp prettyprint '
    'rbconfig rubygems bundler bundler/setup io/console io/wait etc find abbrev observer open-uri resolv ripper '
    'coverage objspace weakref fiber continuation pstore racc strscan syslog tsort un mkmf irb readline expect '
    'bigdecimal matrix prime rational complex fcntl pty win32ole webrick ipaddr uri/common net/protocol drb drb/drb '
    'getoptlong mutex_m minitest/autorun'
).split())
RUBY_ALIASES = {
    'active_support': 'activesupport', 'active_record': 'activerecord', 'active_model': 'activemodel',
    'action_controller': 'actionpack', 'action_dispatch': 'actionpack', 'abstract_controller': 'actionpack',
    'action_view': 'actionview', 'action_mailer': 'actionmailer', 'active_job': 'activejob',
    'action_cable': 'actioncable', 'active_storage': 'activestorage', 'action_mailbox': 'actionmailbox',
    'action_text': 'actiontext', 'rails': 'railties',
}
JVM_SKIP = ('java.', 'javax.', 'jdk.', 'kotlin.', 'scala.', 'sun.', 'com.sun.', 'groovy.', 'android.', 'dalvik.')
JVM_ALIASES = {
    'com.google.common': 'com.google.guava:guava', 'com.google.gson': 'com.google.code.gson:gson',
    'org.apache.commons.lang3': 'org.apache.commons:commons-lang3', 'org.slf4j': 'org.slf4j:slf4j-api',
    'org.junit.jupiter': 'org.junit.jupiter:junit-jupiter', 'org.junit': 'junit:junit',
    'org.hamcrest': 'org.hamcrest:hamcrest', 'org.assertj': 'org.assertj:assertj-core',
    'org.mockito': 'org.mockito:mockito-core', 'okhttp3': 'com.squareup.okhttp3:okhttp',
    'okio': 'com.squareup.okio:okio', 'retrofit2': 'com.squareup.retrofit2:retrofit',
    'kotlinx.coroutines': 'org.jetbrains.kotlinx:kotlinx-coroutines-core',
}
JVM_TLDS = {'com', 'org', 'net', 'io', 'dev', 'de', 'me', 'co', 'uk', 'fr', 'nl', 'ch', 'be', 'at', 'info', 'edu', 'gov', 'app', 'ai', 'cn', 'jp', 'ru', 'br', 'it', 'es', 'se', 'no', 'pl', 'cz', 'tech', 'xyz', 'eu', 'us', 'ca', 'au'}
NUGET_SKIP = ('System', 'Microsoft', 'Windows', 'Mono')
PHP_ALIASES = {'illuminate': 'laravel/framework'}
PHP_GROUPS = {'component', 'bridge', 'bundle', 'contracts'}
SWIFT_SYSTEM = frozenset((
    'Foundation UIKit SwiftUI Combine XCTest Darwin Glibc Dispatch os CoreData CoreGraphics CoreFoundation AppKit '
    'CoreLocation MapKit AVFoundation Security CoreImage QuartzCore Metal MetalKit WebKit SafariServices StoreKit '
    'UserNotifications Photos PhotosUI CoreML Vision ARKit SceneKit SpriteKit GameKit CloudKit HealthKit WatchKit '
    'Network CryptoKit Accelerate CoreText ImageIO MobileCoreServices UniformTypeIdentifiers Swift _Concurrency '
    'Observation Charts WidgetKit AuthenticationServices LocalAuthentication CoreBluetooth CoreMotion OSLog Testing '
    'ObjectiveC MessageUI Contacts EventKit AudioToolbox CoreAudio CoreMedia CoreVideo SystemConfiguration zlib'
).split())
GO_HOSTS = {'github.com': 3, 'gitlab.com': 3, 'bitbucket.org': 3, 'golang.org': 3, 'gopkg.in': 2, 'k8s.io': 2,
            'sigs.k8s.io': 2, 'go.uber.org': 2, 'google.golang.org': 2, 'cloud.google.com': 3, 'go.opentelemetry.io': 2}
RUST_SKIP = {'std', 'core', 'alloc', 'crate', 'self', 'super', 'proc_macro', 'test', 'Self'}
GRADLE_CONF = (r'(?:implementation|api|compileOnly|runtimeOnly|annotationProcessor|kapt|ksp|classpath|compile|runtime'
               r'|testCompile|testRuntime|lintChecks|detektPlugins|[a-z]\w*(?:Implementation|Api|CompileOnly|RuntimeOnly))')
GRADLE_PLATFORM = r'''\s*\(?\s*(?:(?:enforced)?[pP]latform\s*\(\s*)?'''
GRADLE_COORD_RE = re.compile(r'\b(' + GRADLE_CONF + r')' + GRADLE_PLATFORM + r'''["']([\w.\-]+):([\w.\-]+)(?::([^"'@\s]+))?[^"']*["']''')
GRADLE_MAP_RE = re.compile(r'\b(' + GRADLE_CONF + r''')\s*\(?\s*group\s*[:=]\s*["']([\w.\-]+)["']\s*,\s*name\s*[:=]\s*["']([\w.\-]+)["'](?:\s*,\s*version\s*[:=]\s*["']([^"']+)["'])?''')
GRADLE_LIBS_RE = re.compile(r'\b(' + GRADLE_CONF + r')' + GRADLE_PLATFORM + r'libs\.([\w.]+)')
GEM_RE = re.compile(r'''^\s*gem\s*\(?\s*["']([^"']+)["']((?:\s*,\s*["'][^"']*["'])*)(.*)$''')
GEMSPEC_RE = re.compile(r'''\.add_(runtime_|development_)?dependency\s*\(?\s*["']([^"']+)["']((?:\s*,\s*["'][^"']*["'])*)''')
POD_RE = re.compile(r'''^\s*pod\s+["']([^"']+)["']((?:\s*,\s*["'][^"']*["'])*)(.*)$''')
SWIFT_PKG_RE = re.compile(r'\.package\s*\(((?:[^()]|\((?:[^()]|\([^()]*\))*\))*)\)')
SWIFT_TARGET_RE = re.compile(r'\.(?:executable|test|binary|macro|system|plugin)?[tT]arget\s*\(\s*name\s*:\s*"([^"]+)"')
MIX_DEP_RE = re.compile(r'\{\s*:(\w+)\s*,\s*(?:"([^"]*)"\s*)?([^{}]*)\}')
REQ_RE = re.compile(r'^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(.*)$')
NAMESPACE_RE = re.compile(r'^\s*namespace\s+([\w.\\]+)', re.M)
PACKAGE_RE = re.compile(r'^\s*package\s+([\w.`]+)', re.M)
SETUP_REQ_RE = re.compile(r'(install_requires|tests_require)\s*=\s*\[(.*?)\]', re.S)
SETUP_NAME_RE = re.compile(r'''\bname\s*=\s*["']([^"']+)["']''')
QUOTED_RE = re.compile(r'''["']([^"']+)["']''')
DEV_FILE_RE = re.compile(r'dev|test|lint|doc|ci\b|typing|check|format|style|bench|mypy')
MANIFEST_NAMES = {
    'pyproject.toml': 'pyproject', 'setup.cfg': 'setupcfg', 'setup.py': 'setuppy', 'Pipfile': 'pipfile',
    'go.mod': 'gomod', 'Cargo.toml': 'cargo', 'pom.xml': 'pom', 'packages.config': 'nugetconfig',
    'composer.json': 'composer', 'Gemfile': 'gemfile', 'mix.exs': 'mix', 'pubspec.yaml': 'pubspec',
    'Package.swift': 'swiftpm', 'Podfile': 'podfile', 'package.json': 'npm', 'deno.json': 'deno', 'deno.jsonc': 'deno',
    'environment.yml': 'conda', 'environment.yaml': 'conda', 'build.gradle': 'gradle', 'build.gradle.kts': 'gradle',
    'Directory.Packages.props': 'msbuild', 'Directory.Build.props': 'msbuild',
}


def py_canon(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def canon(eco, name):
    if eco == 'pypi':
        return py_canon(name)
    if eco in ('nuget', 'composer', 'cocoapods', 'swiftpm'):
        return name.lower()
    if eco == 'cargo':
        return name.replace('-', '_')
    return name


def manifest_kind(rel):
    parts = rel.split('/')
    name, low = parts[-1], parts[-1].lower()
    if SKIP_PARTS.intersection(parts[:-1]):
        return None
    if name in MANIFEST_NAMES:
        return MANIFEST_NAMES[name]
    if low.endswith(('.txt', '.in')) and (low.startswith('requirements') or 'requirements' in parts[:-1]):
        return 'requirements'
    if low.endswith(('.csproj', '.fsproj', '.vbproj')):
        return 'msbuild'
    if low.endswith('.versions.toml'):
        return 'catalog'
    if name.endswith('.gemspec'):
        return 'gemspec'
    return None


def extra_manifests(root, files):
    dirs = {''}
    for rel in files:
        d = os.path.dirname(rel)
        while d not in dirs:
            dirs.add(d)
            d = os.path.dirname(d)
    listed = set(files)
    found = []
    for d in sorted(dirs):
        for sub in (d, f'{d}/requirements' if d else 'requirements'):
            try:
                names = sorted(e.name for e in os.scandir(root / sub) if e.is_file())
            except OSError:
                continue
            for name in names:
                rel = f'{sub}/{name}' if sub else name
                if rel not in listed and manifest_kind(rel):
                    listed.add(rel)
                    found.append(rel)
    return found


class Lines:
    def __init__(self, text):
        self.lines = text.splitlines()

    def find(self, token, start=0):
        pat = re.compile(r'(?<![\w.\-/@])' + re.escape(token) + r'(?![\w\-/])', re.I)
        for i in list(range(start, len(self.lines))) + list(range(0, min(start, len(self.lines)))):
            if pat.search(self.lines[i]):
                return i
        return start if start < len(self.lines) else 0

    def header(self, regex, start=0):
        pat = re.compile(regex)
        return next((i for i in range(start, len(self.lines)) if pat.search(self.lines[i])), 0)


def strip_jsonc(text):
    out, i, n, quoted = [], 0, len(text), False
    while i < n:
        c = text[i]
        if quoted:
            out.append(c)
            if c == '\\' and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif c == '"':
                quoted = False
        elif text.startswith('//', i):
            while i < n and text[i] != '\n':
                i += 1
            continue
        elif text.startswith('/*', i):
            end = text.find('*/', i + 2)
            i = n if end < 0 else end + 2
            continue
        else:
            quoted = c == '"'
            out.append(c)
        i += 1
    return re.sub(r',(\s*[}\]])', r'\1', ''.join(out))


def requirement(text):
    text = re.split(r'\s+--|\s+#', text, 1)[0].split(';', 1)[0].strip()
    if not text or text.startswith(('-', '#')):
        return None
    if '://' in text or text.startswith('git+'):
        egg = re.search(r'[#&]egg=([A-Za-z0-9._-]+)', text)
        return (egg.group(1), '') if egg else None
    m = REQ_RE.match(text)
    if not m:
        return None
    version = m.group(2).strip()
    return m.group(1), '' if version.startswith('@') else version.strip('() ')


def local_tag(tag):
    return tag.rsplit('}', 1)[-1]


def prefixes(names, sep):
    out = set()
    for n in names:
        segs = n.split(sep)
        out.update(sep.join(segs[:k]) for k in range(1, len(segs) + 1))
    return out


def inside(spec, sep, names, all_prefixes):
    segs = spec.split(sep)
    return spec in all_prefixes or any(sep.join(segs[:k]) in names for k in range(1, len(segs) + 1))


def kebab(name):
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '-', name).lower()


def underscore(name):
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '_', name).lower()


def gem_group(text):
    names = set(re.findall(r'''[:"'](\w+)''', text))
    if names & {'development', 'test', 'doc', 'docs', 'lint', 'rubocop', 'ci', 'tools'}:
        return 'dev'
    return 'runtime' if not names or names <= {'default', 'production'} else 'optional'


def line_at(text, pos):
    return text.count('\n', 0, pos)


class Deps:
    def __init__(self, root, files, g, issues, read_source):
        self.root, self.files, self.g, self.issues, self.read_source = Path(root), files, g, issues, read_source
        self.decls, self.order, self.manifest_edges = {}, 0, set()
        self.internal = {e: set() for e in ECOSYSTEMS}
        self.alias, self.central, self.parsed = {}, {}, set()
        self.catalog, self.catalog_refs, self.php_ns, self.memo = {}, [], set(), {}

    def add(self, eco, name, version, scope, rel, line, key=None):
        name = name.strip()
        if not name:
            return
        k = (eco, canon(eco, name))
        version = (version or '').strip()
        prev = self.decls.get(k)
        if prev is None:
            self.order += 1
            self.decls[k] = {'name': k[1] if eco == 'pypi' else name, 'version': version, 'scope': scope, 'file': rel,
                             'line': line + 1, 'order': self.order}
        else:
            if SCOPE_RANK[scope] < SCOPE_RANK[prev['scope']]:
                prev['scope'] = scope
            if not prev['version'] and version:
                prev['version'] = version
        self.manifest_edges.add((rel, k))
        if key and canon(eco, key) != k[1]:
            self.alias.setdefault(eco, {})[canon(eco, key)] = k

    def text(self, rel):
        raw = self.read_source(self.root, rel, self.issues)
        return None if raw is None else raw.decode('utf-8', errors='replace')

    def run_manifest(self, rel, kind=None):
        if rel in self.parsed:
            return
        self.parsed.add(rel)
        kind = kind or manifest_kind(rel)
        text = self.text(rel)
        if text is None:
            return
        try:
            getattr(self, f'parse_{kind}')(rel, text, Lines(text))
        except (ValueError, TypeError, KeyError, AttributeError, IndexError, ET.ParseError, configparser.Error,
                RecursionError):
            self.issues.add(rel, 'no se pudieron leer las dependencias del manifiesto')

    def parse_npm(self, rel, text, L):
        data = json.loads(text)
        if not isinstance(data, dict):
            return
        if isinstance(data.get('name'), str):
            self.internal['npm'].add(data['name'])
        for section, scope in (('dependencies', 'runtime'), ('devDependencies', 'dev'),
                               ('peerDependencies', 'peer'), ('optionalDependencies', 'optional')):
            deps = data.get(section)
            if not isinstance(deps, dict):
                continue
            start = L.header(r'"' + section + r'"\s*:')
            for dep, ver in deps.items():
                ver = ver if isinstance(ver, str) else ''
                if ver.startswith(('workspace:', 'file:', 'link:', 'portal:')):
                    self.internal['npm'].add(dep)
                    continue
                self.add('npm', dep, ver, scope, rel, L.find(f'"{dep}"', start))

    def parse_deno(self, rel, text, L):
        data = json.loads(strip_jsonc(text))
        if not isinstance(data, dict):
            return
        if isinstance(data.get('name'), str):
            self.internal['jsr'].add(data['name'])
        imports = data.get('imports')
        start = L.header(r'"imports"\s*:')
        for key, target in (imports.items() if isinstance(imports, dict) else ()):
            m = re.match(r'^(npm|jsr):/?(@?[^@/]+(?:/[^@/]+)?)(?:@([^/]+))?', target) if isinstance(target, str) else None
            if m:
                name = m.group(2)
                if m.group(1) == 'npm' and not name.startswith('@'):
                    name = name.split('/')[0]
                self.add(m.group(1), name, m.group(3) or '', 'runtime', rel, L.find(f'"{key}"', start), key=key.rstrip('/'))

    def parse_requirements(self, rel, text, L):
        scope = 'dev' if DEV_FILE_RE.search(rel.rsplit('/', 1)[-1].lower()) else 'runtime'
        logical, first = '', None
        for i, line in enumerate(L.lines):
            first = i if first is None else first
            if line.rstrip().endswith('\\'):
                logical += line.rstrip()[:-1] + ' '
                continue
            item, at = (logical + line).strip(), first
            logical, first = '', None
            inc = re.match(r'^(?:-r|--requirement)\s*=?\s*(\S+)', item)
            if inc:
                target = os.path.normpath(os.path.join(os.path.dirname(rel), inc.group(1))).replace(os.sep, '/')
                if not target.startswith('..') and (self.root / target).is_file():
                    self.run_manifest(target, 'requirements')
                continue
            if item.startswith('-e '):
                item = item[3:].strip()
                if not ('://' in item or item.startswith('git+')):
                    continue
            req = requirement(item)
            if req:
                self.add('pypi', req[0], req[1], scope, rel, at)

    def pep508_list(self, items, scope, rel, L, start):
        for item in items if isinstance(items, list) else ():
            req = requirement(item) if isinstance(item, str) else None
            if req:
                self.add('pypi', req[0], req[1], scope, rel, L.find(req[0], start))

    def poetry_table(self, deps, scope, rel, L, start):
        for dep, spec in (deps.items() if isinstance(deps, dict) else ()):
            if dep.lower() == 'python':
                continue
            if isinstance(spec, dict) and ('path' in spec or 'develop' in spec) and 'version' not in spec:
                self.internal['pypi'].add(dep)
                continue
            version = spec if isinstance(spec, str) else spec.get('version', '') if isinstance(spec, dict) else ''
            self.add('pypi', dep, version if isinstance(version, str) else '', scope, rel, L.find(dep, start))

    def parse_pyproject(self, rel, text, L):
        data = tomllib.loads(text)
        project = data.get('project') or {}
        if isinstance(project.get('name'), str):
            self.internal['pypi'].add(project['name'])
        start = L.header(r'^\s*\[project\]')
        self.pep508_list(project.get('dependencies'), 'runtime', rel, L, start)
        opt_start = L.header(r'^\s*\[project\.optional-dependencies\]') or start
        for _, items in sorted((project.get('optional-dependencies') or {}).items()):
            self.pep508_list(items, 'optional', rel, L, opt_start)
        groups_start = L.header(r'^\s*\[dependency-groups\]')
        for _, items in sorted((data.get('dependency-groups') or {}).items()):
            self.pep508_list(items, 'dev', rel, L, groups_start)
        tool = data.get('tool') or {}
        poetry = tool.get('poetry') or {}
        if isinstance(poetry.get('name'), str):
            self.internal['pypi'].add(poetry['name'])
        self.poetry_table(poetry.get('dependencies'), 'runtime', rel, L, L.header(r'^\s*\[tool\.poetry\.dependencies\]'))
        self.poetry_table(poetry.get('dev-dependencies'), 'dev', rel, L, L.header(r'^\s*\[tool\.poetry\.dev-dependencies\]'))
        for group, body in sorted((poetry.get('group') or {}).items()):
            start = L.header(r'^\s*\[tool\.poetry\.group\.' + re.escape(group) + r'\.dependencies\]')
            self.poetry_table((body or {}).get('dependencies'), 'runtime' if group == 'main' else 'dev', rel, L, start)
        uv = tool.get('uv') or {}
        self.pep508_list(uv.get('dev-dependencies'), 'dev', rel, L, L.header(r'^\s*\[tool\.uv\]'))
        for name, src in sorted((uv.get('sources') or {}).items()):
            if isinstance(src, dict) and (src.get('workspace') or 'path' in src):
                self.internal['pypi'].add(name)
        for _, items in sorted(((tool.get('pdm') or {}).get('dev-dependencies') or {}).items()):
            self.pep508_list(items, 'dev', rel, L, 0)

    def parse_setupcfg(self, rel, text, L):
        cfg = configparser.ConfigParser(interpolation=None, strict=False)
        cfg.read_string(text)
        if cfg.has_option('metadata', 'name'):
            self.internal['pypi'].add(cfg.get('metadata', 'name'))
        for option, scope in (('install_requires', 'runtime'), ('tests_require', 'dev')):
            if cfg.has_option('options', option):
                self.pep508_list(cfg.get('options', option).splitlines(), scope, rel, L, L.header(option))
        if cfg.has_section('options.extras_require'):
            start = L.header(r'^\s*\[options\.extras_require\]')
            for _, value in cfg.items('options.extras_require'):
                self.pep508_list(value.splitlines(), 'optional', rel, L, start)

    def parse_setuppy(self, rel, text, L):
        m = SETUP_NAME_RE.search(text)
        if m:
            self.internal['pypi'].add(m.group(1))
        for m in SETUP_REQ_RE.finditer(text):
            scope = 'runtime' if m.group(1) == 'install_requires' else 'dev'
            self.pep508_list(QUOTED_RE.findall(m.group(2)), scope, rel, L, line_at(text, m.start()))

    def parse_pipfile(self, rel, text, L):
        data = tomllib.loads(text)
        for section, scope in (('packages', 'runtime'), ('dev-packages', 'dev')):
            start = L.header(r'^\s*\[' + section + r'\]')
            for dep, spec in (data.get(section) or {}).items():
                if isinstance(spec, dict) and 'path' in spec:
                    continue
                version = spec if isinstance(spec, str) else spec.get('version', '') if isinstance(spec, dict) else ''
                self.add('pypi', dep, '' if version == '*' else version, scope, rel, L.find(dep, start))

    def parse_conda(self, rel, text, L):
        inside_deps, pip_indent = False, None
        for i, line in enumerate(L.lines):
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            indent = len(line) - len(line.lstrip())
            if indent == 0 and not stripped.startswith('-'):
                inside_deps = stripped.startswith('dependencies:')
                continue
            if not inside_deps or not stripped.startswith('- '):
                continue
            item = stripped[2:].split(' #', 1)[0].strip().strip('"\'')
            if pip_indent is not None and indent <= pip_indent:
                pip_indent = None
            if item == 'pip:':
                pip_indent = indent
                continue
            if pip_indent is not None:
                req = requirement(item)
            else:
                m = re.match(r'^(?:[\w.-]+::)?([A-Za-z0-9][\w.-]*)\s*(.*)$', item)
                req = (m.group(1), m.group(2).lstrip('=').strip()) if m else None
            if req and req[0].lower() not in ('python', 'pip'):
                self.add('pypi', req[0], req[1], 'runtime', rel, i)

    def parse_gomod(self, rel, text, L):
        block = None
        for i, line in enumerate(L.lines):
            code = line.split('//', 1)[0].strip()
            if not code:
                continue
            if block:
                if code == ')':
                    block = None
                else:
                    self.go_entry(block, code.split(), rel, i)
                continue
            m = re.match(r'^(module|require|replace|exclude|retract|tool|go|toolchain|godebug)\b\s*(.*)$', code)
            if not m:
                continue
            if m.group(2) == '(':
                block = m.group(1)
            else:
                self.go_entry(m.group(1), m.group(2).split(), rel, i)

    def go_entry(self, kind, parts, rel, i):
        if kind == 'module' and parts:
            self.internal['go'].add(parts[0].strip('"'))
        elif kind == 'require' and len(parts) >= 2:
            self.add('go', parts[0].strip('"'), parts[1], 'runtime', rel, i)
        elif kind == 'replace' and '=>' in parts:
            target = parts[parts.index('=>') + 1:]
            if target and target[0].startswith(('.', '/')):
                self.internal['go'].add(parts[0])

    def cargo_table(self, deps, scope, rel, L, start, workspace):
        for key, spec in (deps.items() if isinstance(deps, dict) else ()):
            name, version, sc = key, '', scope
            if isinstance(spec, str):
                version = spec
            elif isinstance(spec, dict):
                if spec.get('workspace') is True:
                    ws = workspace.get(key)
                    spec = {**(ws if isinstance(ws, dict) else {'version': ws or ''}), **spec}
                name = spec.get('package', key)
                if 'path' in spec:
                    self.internal['cargo'].update((name, key))
                    continue
                version = spec.get('version', '') if isinstance(spec.get('version', ''), str) else ''
                if spec.get('optional') and scope == 'runtime':
                    sc = 'optional'
            else:
                continue
            self.add('cargo', name, version, sc, rel, L.find(key, start), key=key)

    def parse_cargo(self, rel, text, L):
        data = tomllib.loads(text)
        for table in ('package', 'lib'):
            name = (data.get(table) or {}).get('name')
            if isinstance(name, str):
                self.internal['cargo'].add(name)
        ws = (data.get('workspace') or {}).get('dependencies') or {}
        for section, scope in (('dependencies', 'runtime'), ('dev-dependencies', 'dev'), ('build-dependencies', 'dev')):
            self.cargo_table(data.get(section), scope, rel, L, L.header(r'^\s*\[' + section + r'\]'), ws)
            for _, body in sorted((data.get('target') or {}).items()):
                self.cargo_table((body or {}).get(section), scope, rel, L, L.header(re.escape(section) + r'\]'), ws)
        self.cargo_table(ws, 'runtime', rel, L, L.header(r'^\s*\[workspace\.dependencies\]'), {})

    def parse_pom(self, rel, text, L):
        root = ET.fromstring(text.encode('utf-8'))
        for el in root.iter():
            if isinstance(el.tag, str):
                el.tag = local_tag(el.tag)
        group = root.findtext('groupId') or root.findtext('parent/groupId') or ''
        version = root.findtext('version') or root.findtext('parent/version') or ''
        artifact = root.findtext('artifactId') or ''
        props = {'project.groupId': group, 'pom.groupId': group, 'project.version': version, 'pom.version': version,
                 'project.artifactId': artifact, 'project.parent.version': root.findtext('parent/version') or ''}
        props.update({p.tag: (p.text or '').strip() for p in root.findall('properties/*') if isinstance(p.tag, str)})
        if group and artifact:
            self.internal['maven'].add(f'{group}:{artifact}')
        for m in root.findall('modules/module'):
            name = (m.text or '').strip().rsplit('/', 1)[-1]
            if group and name:
                self.internal['maven'].add(f'{group}:{name}')

        def resolve(value):
            for _ in range(5):
                new = re.sub(r'\$\{([^}]+)\}', lambda m: props.get(m.group(1), m.group(0)), value)
                if new == value:
                    break
                value = new
            return value.strip()

        managed = {}
        for dep in root.findall('.//dependencyManagement/dependencies/dependency'):
            key = f"{resolve(dep.findtext('groupId') or '')}:{resolve(dep.findtext('artifactId') or '')}"
            managed[key] = resolve(dep.findtext('version') or '')
        cursor = 0
        for container in [root] + root.findall('profiles/profile'):
            for dep in container.findall('dependencies/dependency'):
                g, a = resolve(dep.findtext('groupId') or ''), resolve(dep.findtext('artifactId') or '')
                if not g or not a:
                    continue
                v = resolve(dep.findtext('version') or '') or managed.get(f'{g}:{a}', '')
                scope = (dep.findtext('scope') or '').strip()
                optional = (dep.findtext('optional') or '').strip() == 'true'
                sc = 'dev' if scope == 'test' else 'optional' if optional else 'runtime'
                line = L.find(f'<artifactId>{dep.findtext("artifactId").strip()}</artifactId>', cursor)
                cursor = line + 1
                self.add('maven', f'{g}:{a}', '' if '${' in v else v, sc, rel, line)

    def parse_gradle(self, rel, text, L):
        hits = sorted((m.start(), m.group(1), m.group(2), m.group(3), m.group(4) or '')
                      for regex in (GRADLE_COORD_RE, GRADLE_MAP_RE) for m in regex.finditer(text))
        for pos, conf, g, a, v in hits:
            sc = 'dev' if conf.lower().startswith(('test', 'androidtest')) else 'runtime'
            self.add('maven', f'{g}:{a}', '' if '$' in v else v, sc, rel, line_at(text, pos))
        for m in GRADLE_LIBS_RE.finditer(text):
            ref = re.sub(r'\.(get|asprovider)$', '', m.group(2).lower().replace('_', '.').replace('-', '.'))
            self.catalog_refs.append((rel, ref))

    def parse_catalog(self, rel, text, L):
        data = tomllib.loads(text)
        versions = data.get('versions') or {}
        start = L.header(r'^\s*\[libraries\]')
        for alias, spec in (data.get('libraries') or {}).items():
            if isinstance(spec, str):
                parts = spec.split(':')
                if len(parts) < 2:
                    continue
                coord, v = f'{parts[0]}:{parts[1]}', parts[2] if len(parts) > 2 else ''
            elif isinstance(spec, dict):
                coord = spec.get('module') or (f"{spec['group']}:{spec['name']}" if 'group' in spec and 'name' in spec else '')
                ver = spec.get('version', '')
                if isinstance(ver, dict):
                    ver = versions.get(ver['ref'], '') if 'ref' in ver else ver.get('strictly', ver.get('require', ''))
                v = ver if isinstance(ver, str) else ''
                if not coord:
                    continue
            else:
                continue
            self.add('maven', coord, v, 'runtime', rel, L.find(alias, start))
            self.catalog[alias.lower().replace('_', '.').replace('-', '.')] = ('maven', coord)

    def parse_msbuild(self, rel, text, L):
        root = ET.fromstring(text.encode('utf-8'))
        name = rel.rsplit('/', 1)[-1]
        if not name.endswith('.props'):
            self.internal['nuget'].add(os.path.splitext(name)[0])
        cursor = 0
        for el in root.iter():
            if not isinstance(el.tag, str):
                continue
            tag = local_tag(el.tag)
            if tag in ('AssemblyName', 'RootNamespace') and (el.text or '').strip() and '$' not in el.text:
                self.internal['nuget'].add(el.text.strip())
            include = el.get('Include') or ''
            if not include or '$' in include:
                continue
            version = el.get('Version') or el.get('VersionOverride') or ''
            for child in el:
                if isinstance(child.tag, str) and local_tag(child.tag) in ('Version', 'VersionOverride'):
                    version = (child.text or '').strip()
            if tag == 'PackageVersion':
                self.central.setdefault(include.lower(), version)
            elif tag in ('PackageReference', 'GlobalPackageReference'):
                line = L.find(include, cursor)
                cursor = line + 1
                dev = (el.get('PrivateAssets') or '').lower() == 'all'
                self.add('nuget', include, '' if '$' in version else version, 'dev' if dev else 'runtime', rel, line)

    def parse_nugetconfig(self, rel, text, L):
        for el in ET.fromstring(text.encode('utf-8')).iter('package'):
            pid = el.get('id') or ''
            if pid:
                dev = (el.get('developmentDependency') or '').lower() == 'true'
                self.add('nuget', pid, el.get('version') or '', 'dev' if dev else 'runtime', rel, L.find(pid))

    def parse_composer(self, rel, text, L):
        data = json.loads(text)
        if not isinstance(data, dict):
            return
        if isinstance(data.get('name'), str):
            self.internal['composer'].add(data['name'])
        self.internal['composer'].update(k for k in (data.get('replace') or {}) if isinstance(k, str))
        for section in ('autoload', 'autoload-dev'):
            auto = data.get(section)
            for kind in ('psr-4', 'psr-0'):
                block = auto.get(kind) if isinstance(auto, dict) else None
                self.php_ns.update(ns.strip('\\').lower() for ns in (block or {}) if ns.strip('\\'))
        for section, scope in (('require', 'runtime'), ('require-dev', 'dev')):
            deps = data.get(section)
            if not isinstance(deps, dict):
                continue
            start = L.header(r'"' + section + r'"\s*:')
            for dep, ver in deps.items():
                if '/' in dep:
                    self.add('composer', dep, ver if isinstance(ver, str) else '', scope, rel, L.find(f'"{dep}"', start))

    def parse_gemfile(self, rel, text, L):
        stack = []
        for i, line in enumerate(L.lines):
            code = line.split('#', 1)[0].rstrip()
            s = code.strip()
            if not s:
                continue
            first = s.split()[0]
            if first == 'group' and re.search(r'\bdo\b', s):
                stack.append(gem_group(s))
                continue
            if first in ('if', 'unless', 'case', 'begin', 'while', 'until') or re.search(r'\bdo\b(\s*\|[^|]*\|)?\s*$', s):
                stack.append(stack[-1] if stack else 'runtime')
                continue
            if first == 'end' or s == 'end':
                if stack:
                    stack.pop()
                continue
            m = GEM_RE.match(code)
            if not m:
                continue
            name, rest = m.group(1), m.group(3) or ''
            if re.search(r'\bpath\s*:|:path\s*=>', rest):
                self.internal['rubygems'].add(name)
                continue
            inline = re.search(r'\bgroups?\s*:\s*(\[[^\]]*\]|:\w+)', rest)
            scopes = [x for x in stack if x != 'runtime'] + ([gem_group(inline.group(1))] if inline else [])
            scope = max(scopes, key=SCOPE_RANK.get) if scopes else 'runtime'
            self.add('rubygems', name, ', '.join(QUOTED_RE.findall(m.group(2) or '')), scope, rel, i)

    def parse_gemspec(self, rel, text, L):
        m = re.search(r'''\.name\s*=\s*["']([^"']+)["']''', text)
        if m:
            self.internal['rubygems'].add(m.group(1))
        for m in GEMSPEC_RE.finditer(text):
            versions = ', '.join(QUOTED_RE.findall(m.group(3) or ''))
            scope = 'dev' if m.group(1) == 'development_' else 'runtime'
            self.add('rubygems', m.group(2), versions, scope, rel, line_at(text, m.start()))

    def parse_mix(self, rel, text, L):
        m = re.search(r'\bapp:\s*:(\w+)', text)
        if m:
            self.internal['hex'].add(m.group(1))
        start = max(text.find('defp deps'), 0)
        for m in MIX_DEP_RE.finditer(text, start):
            name, version, rest = m.group(1), m.group(2) or '', m.group(3) or ''
            if 'in_umbrella' in rest or re.search(r'\bpath:', rest):
                self.internal['hex'].add(name)
                continue
            only = re.search(r'only:\s*(\[[^\]]*\]|:\w+)', rest)
            scope = 'dev' if only and 'prod' not in only.group(1) else 'optional' if 'optional: true' in rest else 'runtime'
            self.add('hex', name, version, scope, rel, line_at(text, m.start()))

    def parse_pubspec(self, rel, text, L):
        section, entries = None, []
        for i, line in enumerate(L.lines):
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            indent = len(line) - len(line.lstrip())
            key, _, value = line.strip().partition(':')
            value = value.split(' #', 1)[0].strip().strip('"\'')
            if indent == 0:
                section = key if key in ('dependencies', 'dev_dependencies') else None
                if key == 'name' and value:
                    self.internal['pub'].add(value)
            elif section and (not entries or entries[-1][0] != section or indent <= entries[-1][3]):
                entries.append((section, key, i, indent, value, {}))
            elif section:
                entries[-1][5][key] = value
        for section, name, i, _, value, nested in entries:
            if 'path' in nested:
                self.internal['pub'].add(name)
            elif 'sdk' not in nested:
                scope = 'dev' if section == 'dev_dependencies' else 'runtime'
                self.add('pub', name, nested.get('version', value), scope, rel, i)

    def parse_swiftpm(self, rel, text, L):
        m = re.search(r'Package\s*\(\s*name\s*:\s*"([^"]+)"', text)
        if m:
            self.internal['swiftpm'].add(m.group(1))
        self.internal['swiftpm'].update(SWIFT_TARGET_RE.findall(text))
        for m in SWIFT_PKG_RE.finditer(text):
            args = m.group(1)
            if re.search(r'\bpath\s*:', args):
                continue
            url = re.search(r'url\s*:\s*"([^"]+)"', args)
            ident = re.search(r'\bid\s*:\s*"([^"]+)"', args)
            if url:
                pkg = url.group(1).rstrip('/').rsplit('/', 1)[-1]
                pkg = pkg[:-4] if pkg.endswith('.git') else pkg
            elif ident:
                pkg = ident.group(1).rsplit('.', 1)[-1]
            else:
                continue
            version = re.search(r'(?:from|exact|branch|revision)\s*:\s*"([^"]+)"|"([\d.]+)"\s*\.\.', args)
            v = (version.group(1) or version.group(2)) if version else ''
            self.add('swiftpm', pkg, v, 'runtime', rel, line_at(text, m.start()))

    def parse_podfile(self, rel, text, L):
        for i, line in enumerate(L.lines):
            m = POD_RE.match(line.split('#', 1)[0])
            if not m:
                continue
            name = m.group(1).split('/', 1)[0]
            if re.search(r':path\s*=>|\bpath\s*:', m.group(3) or ''):
                self.internal['cocoapods'].add(name)
                continue
            self.add('cocoapods', name, ', '.join(QUOTED_RE.findall(m.group(2) or '')), 'runtime', rel, i)

    def collect(self):
        listed = {f for f in self.files if manifest_kind(f)}
        for rel in sorted(listed | set(extra_manifests(self.root, self.files)), key=lambda r: (r.count('/'), r)):
            self.run_manifest(rel)
        for rel, ref in self.catalog_refs:
            key = self.catalog.get(ref)
            if key in self.decls:
                self.manifest_edges.add((rel, key))
        for key, d in self.decls.items():
            if key[0] == 'nuget' and not d['version']:
                d['version'] = self.central.get(key[1], '')
        for eco, names in self.internal.items():
            for name in names:
                self.decls.pop((eco, canon(eco, name)), None)
        self.manifest_edges = {(rel, k) for rel, k in self.manifest_edges if k in self.decls}

    def scan_internal(self):
        self.py_top, self.npm_suffixes, self.lib_paths = set(), set(), set()
        self.py_names = {py_canon(n).replace('-', '_') for n in self.internal['pypi']}
        self.cs_ns, self.jvm_prefixes = set(self.internal['nuget']), set()
        self.swift_mods = {n.lower() for n in self.internal['swiftpm']}
        listed, heads = set(self.files), 0
        for rel in self.files:
            stem, ext = os.path.splitext(rel)
            parts = rel.split('/')
            if ext in ('.py', '.pyi'):
                d, top = os.path.dirname(rel), parts[-1][:-len(ext)]
                while d and f'{d}/__init__.py' in listed:
                    top, d = d.rsplit('/', 1)[-1], os.path.dirname(d)
                self.py_top.add(top)
            elif ext in JS_EXTS:
                segs = stem.split('/')
                segs = segs[:-1] if segs[-1] == 'index' and len(segs) > 1 else segs
                self.npm_suffixes.update('/'.join(segs[i:]) for i in range(len(segs)))
            elif ext == '.rb' and '/lib/' in f'/{stem}':
                self.lib_paths.add(f'/{stem}'.rsplit('/lib/', 1)[1])
            elif ext == '.swift' and 'Sources' in parts[:-2]:
                self.swift_mods.add(parts[parts.index('Sources') + 1].lower())
            if (ext in JVM_EXTS or ext in ('.cs', '.php')) and heads < MAX_HEADS:
                heads += 1
                try:
                    with open(self.root / rel, 'rb') as fh:
                        head = fh.read(HEAD_BYTES).decode('utf-8', errors='replace')
                except OSError:
                    continue
                if ext == '.cs':
                    self.cs_ns.update(NAMESPACE_RE.findall(head))
                elif ext == '.php':
                    self.php_ns.update(n.strip('\\').lower() for n in NAMESPACE_RE.findall(head))
                else:
                    m = PACKAGE_RE.search(head)
                    if m:
                        segs = m.group(1).replace('`', '').split('.')
                        self.jvm_prefixes.add('.'.join(segs[:3]))
        self.cs_all = prefixes(self.cs_ns, '.')
        self.php_all = prefixes(self.php_ns, '\\')
        self.by_eco = {}
        for eco, c in self.decls:
            self.by_eco.setdefault(eco, {})[c] = (eco, c)

    def declared(self, eco, name):
        c = canon(eco, name)
        k = self.by_eco.get(eco, {}).get(c) or self.alias.get(eco, {}).get(c)
        return k if k in self.decls else None

    def resolve(self, spec, lang):
        eco = LANG_ECO.get(lang)
        if not eco or not isinstance(spec, str):
            return None
        spec = spec.strip().strip('"\'<>;').strip()
        if not spec:
            return None
        key = (eco, spec)
        if key not in self.memo:
            self.memo[key] = getattr(self, f'resolve_{eco}')(spec)
        return self.memo[key]

    def resolve_npm(self, spec):
        if spec.startswith(('.', '/', '#', '~', '@/', '$')) or '!' in spec or '://' in spec:
            return None
        if spec.startswith(('npm:', 'jsr:')):
            eco = spec[:3]
            m = re.match(r'^(@?[^@/]+(?:/[^@/]+)?)', spec[4:].lstrip('/'))
            if not m:
                return None
            name = m.group(1) if m.group(1).startswith('@') or eco == 'jsr' else m.group(1).split('/')[0]
            return self.declared(eco, name) or ('new', eco, name)
        if ':' in spec:
            return None
        segs = spec.split('/')
        for k in range(len(segs), 0, -1):
            for eco in ('npm', 'jsr'):
                key = self.alias.get(eco, {}).get('/'.join(segs[:k]))
                if key in self.decls:
                    return key
        name = '/'.join(segs[:2]) if spec.startswith('@') else segs[0]
        key = self.declared('npm', name) or self.declared('jsr', name)
        if key:
            return key
        if name in NODE_BUILTINS or name in self.internal['npm'] or name.startswith('@types/'):
            return None
        if not NPM_NAME_RE.match(name) or spec in self.npm_suffixes or name in self.npm_suffixes:
            return None
        return ('new', 'npm', name)

    def resolve_pypi(self, spec):
        segs = spec.split('.')
        top = segs[0]
        if not top or top in sys.stdlib_module_names or top == '__future__':
            return None
        candidates = [PY_ALIASES[p] for p in ('.'.join(segs[:k]) for k in range(len(segs), 0, -1)) if p in PY_ALIASES]
        if top in PY_NAMESPACES and len(segs) > 1:
            candidates += ['-'.join(segs[:k]) for k in range(min(len(segs), 4), 1, -1)]
        candidates += [top, f'python-{top}', f'{top}-python', f'py{top}', f'{top}-binary', f'{top}-py',
                       f'django-{top}', f'flask-{top}'] + ([top[2:]] if top.lower().startswith('py') and len(top) > 3 else [])
        for c in candidates:
            key = self.declared('pypi', c)
            if key:
                return key
        if top in self.py_top or top.lower() in self.py_names or top.startswith('_') or not top.isidentifier():
            return None
        return ('new', 'pypi', candidates[0])

    def resolve_go(self, spec):
        segs = spec.split('/')
        if '.' not in segs[0]:
            return None
        for k in range(len(segs), 0, -1):
            prefix = '/'.join(segs[:k])
            if prefix in self.internal['go']:
                return None
            key = self.declared('go', prefix)
            if key:
                return key
        n = GO_HOSTS.get(segs[0], 3 if len(segs) >= 3 else len(segs))
        if segs[0] == 'gopkg.in' and len(segs) > 2 and not re.search(r'\.v\d+$', segs[1]):
            n = 3
        name = '/'.join(segs[:n])
        if len(segs) > n and re.match(r'^v\d+$', segs[n]):
            name = f'{name}/{segs[n]}'
        return ('new', 'go', name)

    def resolve_cargo(self, spec):
        m = re.match(r'^(?:extern\s+crate\s+)?:*\s*([A-Za-z_][\w-]*)', spec)
        top = m.group(1) if m else ''
        if not top or top in RUST_SKIP:
            return None
        key = self.declared('cargo', top)
        if key:
            return key
        if canon('cargo', top) in {canon('cargo', n) for n in self.internal['cargo']} or top[0].isupper():
            return None
        return ('new', 'cargo', top)

    def resolve_jvm(self, spec):
        spec = re.sub(r'\.\*$', '', re.sub(r'^static\s+', '', spec.replace('`', '')))
        if spec.startswith(JVM_SKIP) or '.' not in spec:
            return None
        pkg = []
        for s in spec.split('.'):
            if not (s[:1].islower() or s[:1] == '_'):
                break
            pkg.append(s)
        if not pkg or any(spec == p or spec.startswith(p + '.') for p in self.jvm_prefixes):
            return None
        f = [s.lower() for s in pkg]
        ranks = []
        for c, key in sorted(self.by_eco.get('maven', {}).items()):
            group, _, artifact = c.partition(':')
            gs, tokens = group.lower().split('.'), re.split(r'[-.]', artifact.lower())
            p = 0
            while p < len(gs) and p < len(f) and gs[p] == f[p]:
                p += 1
            if p >= 2 and p >= len(gs) - 1:
                score = 10 * p
            elif gs[-1] in f[:3]:
                score = 5
            elif len(f) >= 2 and f[0] in tokens and f[1] in tokens:
                score = 4
            else:
                continue
            score += 3 * len(set(tokens) & set(f[2:]))
            d = self.decls[key]
            ranks.append(((score, -SCOPE_RANK[d['scope']], -len(tokens), -d['order']), key, p))
        ranks.sort(reverse=True)
        if ranks and (len(ranks) == 1 or ranks[0][0][0] > ranks[1][0][0]):
            return ranks[0][1]
        alias = next((JVM_ALIASES[p] for p in ('.'.join(pkg[:k]) for k in range(len(pkg), 0, -1)) if p in JVM_ALIASES), None)
        shared = '.'.join(pkg[:ranks[0][2]]) if ranks and ranks[0][2] >= 2 else ''
        return ('new', 'maven', alias or shared or '.'.join(pkg[:3 if pkg[0] in JVM_TLDS else 2]))

    def resolve_nuget(self, spec):
        spec = re.sub(r'^(global\s+)?(using\s+)?(static\s+)?', '', spec).split('=')[-1].strip().replace('global::', '')
        if not spec:
            return None
        segs, low = spec.split('.'), spec.lower()
        ids = self.by_eco.get('nuget', {})
        for k in range(len(segs), 0, -1):
            key = ids.get('.'.join(segs[:k]).lower())
            if key:
                return key
        longer = [] if segs[0] == 'System' else sorted((c for c in ids if c.startswith(low + '.')), key=lambda c: (len(c), c))
        if longer:
            return ids[longer[0]]
        if inside(spec, '.', self.cs_ns, self.cs_all) or segs[0] in NUGET_SKIP:
            return None
        if not re.match(r'^[A-Za-z_][\w.]*$', spec):
            return None
        return ('new', 'nuget', '.'.join(segs[:2]))

    def resolve_composer(self, spec):
        spec = re.sub(r'^(function|const)\s+', '', spec).lstrip('\\')
        segs = [s for s in spec.split('\\') if s]
        if len(segs) < 2:
            return None
        s = [x.lower().replace('-', '').replace('_', '') for x in segs]
        own = inside('\\'.join(segs).lower(), '\\', self.php_ns, self.php_all)
        declared = self.by_eco.get('composer', {})
        vendors = Counter(c.partition('/')[0].replace('-', '') for c in declared)
        best = None
        for c, key in sorted(declared.items()):
            vendor, _, pkg = c.partition('/')
            v, p = vendor.replace('-', ''), pkg.replace('-', '')
            score = 0
            if s[0] == v:
                if p == s[1]:
                    score = 30
                elif len(s) > 2 and p == s[1] + s[2]:
                    score = 35
                elif len(s) > 2 and s[1] in PHP_GROUPS and p.startswith(s[2]):
                    score = 30
                elif p.startswith(s[1]):
                    score = 15
                elif s[1].startswith(p):
                    score = 12
                elif p == v:
                    score = 10
                elif len(s[1]) >= 3 and s[1] in p:
                    score = 8
                elif v.startswith(p) or p.startswith(v):
                    score = 6
                elif vendors[v] == 1:
                    score = 2
            elif PHP_ALIASES.get(s[0]) == c:
                score = 25
            elif p == s[0]:
                score = 20
            if score >= (30 if own else 1):
                rank = (score, -self.decls[key]['order'])
                if best is None or rank > best[0]:
                    best = (rank, key)
        if best:
            return best[1]
        if own:
            return None
        if s[0] in PHP_ALIASES:
            name = PHP_ALIASES[s[0]]
        elif s[1] in PHP_GROUPS and len(segs) > 2:
            name = f'{segs[0].lower()}/{kebab(segs[2])}'
        else:
            name = f'{segs[0].lower()}/{kebab(segs[1])}'
        return None if name in self.internal['composer'] else ('new', 'composer', name)

    def resolve_rubygems(self, spec):
        if spec.startswith(('.', '/')) or spec in RUBY_STDLIB or spec in self.lib_paths:
            return None
        parts = spec.split('/')
        for k in range(len(parts), 0, -1):
            for sep in ('-', '_'):
                key = self.declared('rubygems', sep.join(parts[:k]))
                if key:
                    return key
        alias = RUBY_ALIASES.get(parts[0])
        if alias and self.declared('rubygems', alias):
            return self.declared('rubygems', alias)
        name = alias or parts[0]
        if parts[0] in RUBY_STDLIB or name in self.internal['rubygems'] or not re.match(r'^[a-z][\w.-]*$', name):
            return None
        return ('new', 'rubygems', name)

    def resolve_hex(self, spec):
        segs = spec.lstrip(':').split('.')
        names = ([f'{underscore(segs[0])}_{underscore(segs[1])}'] if len(segs) > 1 else []) + [underscore(segs[0])]
        return next((k for k in (self.declared('hex', n) for n in names) if k), None)

    def resolve_pub(self, spec):
        if not spec.startswith('package:'):
            return None
        name = spec[8:].split('/', 1)[0]
        key = self.declared('pub', name)
        if key:
            return key
        if not name or name in self.internal['pub'] or name in ('flutter', 'flutter_test', 'flutter_driver'):
            return None
        return ('new', 'pub', name)

    def resolve_swift(self, spec):
        mod = re.split(r'[/.\s]', re.sub(r'^@?import\s+', '', spec).strip())[0]
        if not mod or mod in SWIFT_SYSTEM or mod.lower() in self.swift_mods:
            return None
        low, best = mod.lower(), None
        for eco in ('swiftpm', 'cocoapods'):
            for c, key in sorted(self.by_eco.get(eco, {}).items()):
                bare = re.sub(r'^swift-', '', c).replace('-', '').replace('_', '')
                score = 3 if low in (c, bare) else 1 if len(bare) >= 3 and low.startswith(bare) else 0
                if score and (best is None or score > best[0]):
                    best = (score, key)
        return best[1] if best else None

    def link(self):
        from .analyze import is_test
        g, new, hits, real = self.g, {}, set(), set()
        for mid, spec, lang in g.externals:
            if mid not in g.nodes:
                continue
            r = self.resolve(spec, lang)
            if r is None:
                continue
            if r[0] == 'new':
                key = (r[1], canon(r[1], r[2]))
                if key not in self.decls:
                    rel = g.nodes[mid].get('file', '')
                    if key not in new or rel < new[key][1]:
                        new[key] = (key[1] if r[1] == 'pypi' else r[2], rel)
                    if not is_test(rel):
                        real.add(key)
                r = key
            hits.add((mid, r))
        managed = {eco for eco, _ in self.decls}
        new = {k: v for k, v in new.items() if k in real or k[0] not in managed}
        ids = {}
        for key in sorted(self.decls, key=lambda k: (k[0], self.decls[k]['name'])):
            d = self.decls[key]
            ids[key] = g.node(f"p:{key[0]}:{d['name']}", kind='package', name=d['name'], file=d['file'], line=d['line'],
                              version=d['version'], ecosystem=key[0], scope=d['scope'])
        for key in sorted(new):
            name, rel = new[key]
            ids[key] = g.node(f'p:{key[0]}:{name}', kind='package', name=name, file=rel, line=1, version='',
                              ecosystem=key[0], scope='runtime')
        for rel, key in sorted(self.manifest_edges):
            g.edge(f'm:{rel}', ids[key], 'depends')
        for mid, key in sorted(hits):
            if key in ids:
                g.edge(mid, ids[key], 'depends')
        return {'declared': len(self.decls), 'undeclared': len(new), 'links': len(hits)}


def link_dependencies(root, files, g, issues, read_source):
    deps = Deps(root, files, g, issues, read_source)
    deps.collect()
    deps.scan_internal()
    return deps.link()
