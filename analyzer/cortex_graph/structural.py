"""Heurísticas estructurales de flujos, independientes de la librería (ronda 4 del benchmark de flujos, `bench/flows`).

En lugar de reconocer cada framework por su nombre, se apoyan en la forma del código y en lo que el propio repo declara. Es un
mixin de `bridges.Bridges` (usa su `Src`, sus índices de símbolos y sus colas `pending`/`clients`/`topic_uses`/`env_*`):

- Rutas: una llamada cuyos argumentos incluyen un literal con forma de ruta (`"/x"`, o un nombre RPC `"a.b"` pasado a un receptor
  tipo router) y una función inline o una referencia a una función/método/clase del repo (`scan_registrations`); montajes (literal +
  router importado o variable local con rutas) y `basePath` componen prefijos; las clases handler se expanden a sus métodos con
  nombre de verbo HTTP (`expand_handler`); prefijos de ruta heredados de la clase base; contratos (interfaces con rutas anotadas)
  servidos por sus implementaciones y consumidos por interfaces cliente que los extienden (`finish_contracts`).
- Clientes: funciones cuyo parámetro fluye a la URL de una llamada cliente, en cadena y entre ficheros (`scan_url_flow` /
  `finish_url_flow`); URLs alternativas de ternarios, reasignaciones y funciones locales (`url_alternatives`); procedimientos RPC
  declarados en routers y llamados por su nombre cualificado (`finish_rpc_chains`).
- Eventos y jobs: productores por referencia (`X.delay()`, `new XTask().schedule()`, `enqueue(f)`, `Enqueue(() => svc.M())` con la
  implementación de la interfaz), por clave compartida entre una llamada productora y un registro con handler (`finish_job_keys`), por
  expresión cron junto a una referencia, `case "x":` de un switch que emite con nombre dinámico, y llamantes de interfaces productoras
  o de funciones `enqueue_*` (`finish_event_wrappers`).
- Datos: clases que declaran su tabla (`__tablename__`, `tableName`, `@Table`/`[Table]`, `@Entity`, `TableName()`), usos cualificados
  `modulo.Modelo` y, en Go, `new(pkg.M)` dentro de funciones con operaciones de base de datos; tablas del DSL <-> `CREATE TABLE`;
  relaciones entre modelos (campos tipados y herencia).
- Entorno: cualquier NOMBRE_EN_MAYÚSCULAS leído en código que el repo define (.env*, bloques `env` de YAML/JSON, Dockerfile, shell),
  opciones declaradas con nombre + variable (`{Name: "x", EnvVars("X")}`), módulos `environment.*` y `${clave}` de propiedades.
- Servicios: `build:`/`command:` de compose -> Dockerfile/entrypoint, ids de servicio en anotaciones cliente <-> `application.name`,
  y referencias entre manifiestos (kustomize `resources`, selectores de etiquetas, `claimName`, `service: name`).
"""
import re
from bisect import bisect_right
from collections import defaultdict


def word_start(text, pos):
    return pos == 0 or not (text[pos - 1].isalnum() or text[pos - 1] in '_$')


def stem_calls(code, stems, rx):
    """Llamadas cuyo nombre contiene alguno de `stems`: búsqueda literal (rápida) y `rx.match` desde el inicio del identificador."""
    starts = set()
    for stem in stems:
        i = code.find(stem)
        while i >= 0:
            j = i
            while j > 0 and (code[j - 1].isalnum() or code[j - 1] in '_$'):
                j -= 1
            starts.add(j)
            k = j
            while k > 0 and code[k - 1] in ' \t':
                k -= 1
            if k < j and code[k - 3:k] == 'new' and word_start(code, k - 3):
                starts.add(k - 3)
            i = code.find(stem, i + len(stem))
    out = []
    for j in sorted(starts):
        if word_start(code, j):
            m = rx.match(code, j)
            if m:
                out.append(m)
    return out


class _Lazy:
    """Acceso diferido a los helpers de `bridges` (que importa este módulo), sin import circular."""

    def __getattr__(self, name):
        from . import bridges
        value = getattr(bridges, name)
        setattr(self, name, value)
        return value


B = _Lazy()

PATH_LIT = re.compile(r'/(?:[\w\-.~%@+=,;!$:*/]|\{[^{}/]+\}|<[^<>/]+>|\[[^\[\]/]+\])*')
RPC_LIT = re.compile(r'[a-z][A-Za-z0-9_]*(?:\.[a-z][A-Za-z0-9_]*)+')
FILE_LIKE = re.compile(r'\.(?:js|mjs|cjs|ts|tsx|jsx|json|html?|css|scss|less|png|jpe?g|gif|svg|ico|webp|woff2?|ttf|map|txt|md|xml|'
                       r'ya?ml|toml|ini|sh|py|rb|go|rs|java|kt|php|ex|exs|cs|lock|log|pdf|zip|gz|sql|db|sqlite|pem|key|crt)$', re.I)
VERB_NAME = {'get': 'GET', 'post': 'POST', 'put': 'PUT', 'patch': 'PATCH', 'delete': 'DELETE', 'del': 'DELETE',
             'head': 'HEAD', 'options': 'OPTIONS', 'all': 'ANY', 'any': 'ANY'}
VERB_IN_NAME = re.compile(r'(?:map|add|on|handle|register|route|r)?_?(get|post|put|patch|delete|head|options)'
                          r'(?:_?(?:route|handler|endpoint|mapping|async|request))?', re.I)
CLASS_VERB = {'get': 'GET', 'post': 'POST', 'put': 'PUT', 'patch': 'PATCH', 'delete': 'DELETE', 'head': 'HEAD', 'options': 'OPTIONS'}
CLASS_REST = {'index': 'GET', 'list': 'GET', 'show': 'GET', 'retrieve': 'GET', 'create': 'POST', 'store': 'POST', 'update': 'PUT',
              'partial_update': 'PATCH', 'destroy': 'DELETE'}
NOT_ROUTE_NAMES = {
    'describe', 'it', 'test', 'expect', 'mock', 'spyOn', 'intercept', 'visit', 'on', 'once', 'off', 'emit', 'addEventListener',
    'removeEventListener', 'subscribe', 'listen', 'push', 'replace', 'navigate', 'redirect', 'open', 'join', 'resolve', 'require',
    'import', 'readFile', 'writeFile', 'readFileSync', 'writeFileSync', 'existsSync', 'fetch', 'log', 'info', 'warn', 'error', 'debug',
    'print', 'printf', 'println', 'format', 'sprintf', 'Sprintf', 'Printf', 'Errorf', 'startsWith', 'endsWith', 'includes', 'match',
    'test', 'split', 'indexOf', 'concat', 'then', 'catch', 'setTimeout', 'setInterval', 'watch', 'computed', 'useEffect', 'useCallback',
    'useMemo', 'sendFile', 'render', 'template', 'static', 'Static', 'File', 'Dir', 'ServeFile', 'StaticFile', 'StaticFS',
    'set', 'setHeader', 'header', 'cookie', 'assert', 'assertEquals', 'when', 'given', 'step', 'exec', 'spawn', 'command', 'task',
    'Group', 'group',  # `Group("/x", mw)`: grupo con middleware, no una ruta con handler
}
NOT_ROUTE_RECV = {'mock', 'jest', 'sinon', 'vi', 'unittest', 'mocker', 'monkeypatch', 'nock', 'fs', 'path', 'os', 'console', 'logger', 'log',
                  'window', 'document', 'location', 'history', 'navigation', 'Linking', 'shutil', 'subprocess', 'self.client', 'client'}
CLIENT_RECV = re.compile(r'^(?:\$|jQuery|axios|http|https|request|superagent|got|ky|fetch|\$http|xhr|cy|page|browser|wrapper)$')
ROUTERISH = re.compile(r'(?i)(?:router|routes?|app|api|server|endpoints?|^r|^v\d+|group|grp|mux|controller)$')
PREFIX_NAME = re.compile(r'(?i)^(?:base_?path|prefix|set_?prefix|mount_?path|context_?path|root_?path|url_?prefix|set_?global_?prefix)$')
MOUNT_TAIL = re.compile(r'(?:\.(?:routes|router|middleware|allowedMethods|handler|callback)\s*\(\s*\)|\.(?:router|routes|app))$')
REF = re.compile(r'(?:new\s+)?([A-Za-z_$][\w$]*(?:\s*(?:\.|::|->)\s*[A-Za-z_$][\w$]*)*)\s*(?:\(\s*\)|::class|\.class)?')
IDENT_BACK = re.compile(r'([A-Za-z_$][\w$]*)\s*(?:<[^<>()]*(?:<[^<>()]*>[^<>()]*)*>)?\s*$')
ASSIGNED = re.compile(r'(?:\b(?:const|let|var|val|final|auto)\s+)?([A-Za-z_$][\w$]*)\s*(?::\s*[^=;\n]+)?(?<![=!<>])=\s*(?:await\s+)?(?:new\s+)?$')
FLOW_CALL = re.compile(r'(fetch|request|get|post|put|patch|delete|head|GET|POST|PUT|'
                       r'PATCH|DELETE|Get|Post|Put|Patch|Delete|getForObject|postForObject|exchange|urlopen|new\s+EventSource|'
                       r'new\s+WebSocket)\s*(?:<[^<>()]*(?:<[^<>()]*>[^<>()]*)*>)?\s*\(')
RECV_BACK = re.compile(r'(?:(?<![\w$])(this|self|super|static|\$this)|([\w$\])]))\s*\??(?:\.|->|::)\s*$')
PATH_PARAM = re.compile(r'(?i)(?:path|url|uri|endpoint|route|href)s?$|^(?:p|u)$')
FLOW_STEMS = ('fetch', 'request', 'get', 'post', 'put', 'patch', 'delete', 'head', 'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'Get', 'Post',
              'Put', 'Patch', 'Delete', 'exchange', 'urlopen', 'EventSource', 'WebSocket')
PRODUCER_STEMS = ('nqueue', 'ush_bulk', 'chedule', 'efer', 'rigger', 'erform', 'ubmit', 'equeue', 'elay', 'apply_async', 'ddOrUpdate', 'dd_or_update',
                  'dd_job', 'ddJob', 'un_later', 'unLater', 'ontinueJobWith', 'ispatch', 'send_task')
CONSUMER_STEMS = ('Worker', 'Runner', 'Consumer', 'Processor', 'Handler', 'Subscriber', 'Listener', 'ddOrUpdate', 'dd_or_update', 'egister',
                  'ubscribe', 'onsume', 'rocess', 'isten', 'andle', 'on(', 'on<', 'on (')
MARK = tuple(chr(0x10 + i) for i in range(8))
WRAP = '\x01'
FLOW_GENERIC = {'get', 'post', 'put', 'patch', 'delete', 'head', 'request', 'fetch', 'send', 'call', 'query', 'GET', 'POST', 'PUT',
                'PATCH', 'DELETE', 'Get', 'Post', 'Put', 'Delete', 'Patch', 'run', 'execute', 'handle', 'open'}
E2E_DIR = re.compile(r'(?i)(?:^|/)(?:cypress|playwright|e2e|e2e-tests|integration-tests)/')
OPTIONS_CLIENT = re.compile(r'(?<![\w$])(?:(?:\$|jQuery)\s*\.\s*ajax|axios(?:\s*\.\s*request)?|\$http|request)\s*\(')
FLOW_SKIP = {'constructor', '__init__', 'init', 'initialize'}
PRODUCER_CALL = re.compile(r'((?:[Ee]nqueue|[Ss]chedule|[Dd]efer|[Tt]rigger|[Pp]erform|[Ss]ubmit|[Rr]equeue)\w*|delay|Delay|'
                           r'apply_async|AddOrUpdate|add_or_update|add_job|addJob|run_later|runLater|ContinueJobWith|dispatch|Dispatch|'
                           r'send_task|enqueue_call|enqueue_at|enqueue_in|push_bulk|perform_bulk)\s*(?:<[^<>()]*>)?\s*\(')
CONSUMER_CALL = re.compile(r'(?:create\w*(?:Worker|Runner|Consumer|Processor|Handler|Subscriber|Listener)|new\s+\w*(?:Worker|Runner|'
                           r'Consumer|Processor|Subscriber|Listener)|(?:AddOrUpdate|add_or_update|register\w*|subscribe\w*|consume\w*|'
                           r'process\w*|listen\w*|handle\w*|on))\s*(?:<[^<>()]*(?:<[^<>()]*>[^<>()]*)*>)?\s*\(')
LAMBDA_CALL = re.compile(r'\s*(?:async\s+)?(?:\(\s*(?:(\w+)(?:\s*:\s*[\w<>.?]+)?)?\s*\)|(\w+))\s*=>\s*(?:\{\s*(?:return\s+)?)?(?:await\s+)?'
                         r'(?:(\w+)\s*\??\.\s*)?([A-Za-z_]\w*)\s*(?:<[^<>()]*>)?\s*\(|\s*lambda\s*(?:(\w+))?\s*:\s*(?:(\w+)\.)?(\w+)\s*\(')
DEFAULT_EXPORT = re.compile(r'\bexport\s+default\s+(?:abstract\s+)?(?:class|(?:async\s+)?function\s*\*?)\s+([A-Za-z_$][\w$]*)')
EMIT_DYNAMIC = re.compile(r'\.\s*(?:emit|publish|broadcast|send|trigger|notify|produce)\s*\(')
PRODUCER_NAME = re.compile(r'(?i)^(?:enqueue|schedule|dispatch|publish|emit|trigger|delay|notify|broadcast|produce)(?:_|[A-Z]|$)')
CRON = re.compile(r'(?:[\d*/,\-?LW#]+\s+){4,5}[\d*/,\-?LW#A-Za-z]+|@(?:yearly|annually|monthly|weekly|daily|midnight|hourly|reboot)')
JOB_DICT = re.compile(r'''(?:func|job|task|callable|perform)['"]?\s*[:=]\s*(?=[A-Za-z_$][\w$.]*\s*[,}\n)])''')
HANDLER_KEY = re.compile(r'''(?<![\w$])['"]?(?:run|handler|handle|process|perform|execute|callback|onMessage|consume|worker|job|fn|func|'''
                         r'''task|processor)['"]?\s*:\s*''')
JOB_METHODS = ('perform', 'run', 'execute', 'handle', 'process', 'call', '__call__', 'work', 'Execute', 'Run', 'Handle', 'Process',
               'Perform', 'perform_now', 'invoke', 'Invoke', 'each_iteration')
CLASS_HEAD = re.compile(r'\b(?:class|record|struct)\s+(\w+)\s*(?:<[^>{]*>)?\s*(?:\([^)]*\))?\s*((?::|\bextends\b|\bimplements\b)[^{;]*)')
MODEL_FIELD = re.compile(r'^\s*(?:@\w+(?:\([^)]*\))?\s*)*(?:(?:private|protected|public|internal|final|lateinit|open|override|readonly|'
                         r'virtual)\s+)*(?:(?:val|var)\s+\w+\s*:\s*)?[\w.]+(?:\s*<[^<>;=]*>)?\??\s*\w*\s*(?:[;=,)]|\{\s*get|$)')
MODEL_HINT = re.compile(r'__tablename__|tableName|table_name|db_table|\$table\b|TableName\(|@(?:Table|Entity|MappedEntity|Document|MongoEntity)\b|'
                        r'\[Table\(')
MODEL_CLASS = re.compile(r'(?:class|record)\s+([A-Z]\w*)')
MODEL_CLASS_LEAD = re.compile(r'[ \t]*(?:export\s+)?(?:default\s+)?(?:(?:public|private|internal|abstract|final|sealed|partial|open|data)\s+)*')
MODEL_ANN = re.compile(r'(?:@|\[)(Table|Entity|MappedEntity|Document|MongoEntity|Model)\b(\([^)]*\))?')
MODEL_TABLE_KEY = re.compile(r'''(?:\b__tablename__|\btableName|\btable_name|\bdb_table|\$table)\s*(?::\s*\w+\s*)?[:=]\s*['"](\w+)['"]''')
DB_OP = re.compile(r'\.\s*(?:AutoMigrate|Migrator|CreateTable|RegisterModel|Find|Get|Insert|Update|Delete|Where|Table|Exec|Query|Count|Sync\w*|Save|Create|First|Select|Model|Iterate|Exist|'
                   r'Join|Cols|Omit|AllCols|NoAutoCondition|SumInt|Scan|Limit|OrderBy|Desc|Asc|ID|Begin|Commit)\s*\(')
FLAG_DECL = re.compile(r'\{[^{}]{0,600}\}')
FLAG_READ = re.compile(r'''\.\s*(?:String|Bool|Int|Int64|Uint|Uint64|Float64|Duration|StringSlice|IntSlice|Path|Generic|Timestamp|IsSet|'''
                       r'''Value)\s*\(\s*["']([\w.\-]+)["']\s*\)''')
JSON_ENV_NAME = re.compile(r'(?i)(?:^|/)(?:launch[\w.-]*|[\w.-]*env[\w.-]*|[\w.-]*settings)\.json$')
ENV_MODULE = re.compile(r'(?i)^(?:env|environment|environments)(?:[.\-_][\w-]+)?$')
SHELLISH = ('.sh', '.bash', '.zsh', '.ini', '.cfg', '.tpl', '.template', '.tmpl')
ENV_BLOCK = re.compile(r'(?i)env')
ENV_TOKEN = re.compile(r'[A-Z][A-Z0-9]*_[A-Z0-9_]*')
ENV_QUOTED = re.compile(r'''(["'`])([A-Z][A-Z0-9]*_[A-Z0-9_]*)\1''')
RPC_INVOKE = {'query', 'mutate', 'fetch', 'prefetch', 'subscribe', 'useQuery', 'useMutation', 'useSuspenseQuery', 'useInfiniteQuery',
              'useSuspenseInfiniteQuery', 'useSubscription', 'queryOptions', 'mutationOptions', 'infiniteQueryOptions',
              'subscriptionOptions', 'ensureData', 'fetchInfinite', 'prefetchInfinite'}
RPC_CHAIN_BACK = re.compile(r'(?:(?<=\.\.\.)|(?<![\w$.]))([A-Za-z_$][\w$]*(?:\s*\??\.\s*[A-Za-z_$][\w$]*)+)\s*$')
MANIFEST_REF = re.compile(r'''^\s*-?\s*(claimName|serviceName|secretName|name)\s*:\s*["']?([\w.-]+)["']?\s*$''')
MANIFEST_KINDS = {'claimName': ('PersistentVolumeClaim',), 'serviceName': ('Service',), 'secretName': ('Secret',),
                  'service': ('Service',), 'secretRef': ('Secret',), 'configMapRef': ('ConfigMap',), 'configMap': ('ConfigMap',),
                  'persistentVolumeClaim': ('PersistentVolumeClaim',), 'secretKeyRef': ('Secret',)}
REG_LANGS = ('py', 'js', 'go', 'java', 'kt', 'cs', 'rb', 'php', 'rs', 'ex', 'c')


def bracket_pairs(struct):
    stack, pairs, back = [], [], {}
    for m in B.BRACKETS.finditer(struct):
        ch, pos = m.group(), m.start()
        if ch in '([{':
            stack.append((pos, ch))
        elif stack:
            start, opener = stack.pop()
            pairs.append((start, pos, opener))
            back[pos] = start
    pairs.sort()
    return pairs, back


CLASS_ROUTE = re.compile(r'''(?:@|\[)(?:Route|RoutePrefix|RequestMapping|Controller|Path)\s*\(\s*(?:(?:value|path|template)\s*[=:]\s*)?\{?\s*["']([^"']*)["']'''
                         r'''[^\n]*\n(?:\s*(?:@|\[)[^\n]*\n)*[^\n]*?\b(?:class|interface)\s+(\w+)''')
CLASS_BASES = re.compile(r'\b(?:class|interface)\s+\w+\s*(?:<[^>{]*>)?\s*(?:\([^)]*\))?\s*(?::|\bextends\b|\bimplements\b)\s*([^{]*)')


CLIENT_IFACE = re.compile(r'@(Client|FeignClient|RegisterRestClient|HttpExchange)\b(\([^)]*\))?[\s\S]{0,400}?\binterface\s+(\w+)\s*'
                          r'(?:<[^>{]*>)?\s*(?:extends|:)\s*([\w\s,<>.]+?)\s*\{')
SERVICE_ID = re.compile(r'''@(?:Client|FeignClient|RegisterRestClient)\s*\(\s*(?:(?:id|name|value|serviceId|configKey)\s*=\s*)?"([\w.\-]+)"''')


class Structural:
    def structural_init(self):
        self.svc_ids, self.class_routes, self.client_ifaces, self.impls = [], {}, {}, defaultdict(set)
        self.param_cache, self.url_wrappers, self.url_wrappers_new = {}, {}, set()
        self.job_keys, self.qual_rx, self.flag_binds, self.flag_reads = [], {}, defaultdict(set), []
        self.rpc_eps, self.ws_packages = set(), None
        self.router_calls = []

    def collect_class_routes(self, rel, text):
        """Prefijos de ruta declarados en clases base (`[Route("api/[controller]")] class BaseApiController`), heredables."""
        if 'class' not in text and 'interface' not in text or not re.search(r'(?:@|\[)(?:Route|RoutePrefix|RequestMapping|Controller|Path|Client|'
                                                                            r'FeignClient|RegisterRestClient)\b', text):
            return
        for m in SERVICE_ID.finditer(text):
            self.svc_ids.append((rel, text.count('\n', 0, m.start()) + 1, m.group(1)))
        for m in CLASS_ROUTE.finditer(text):
            self.class_routes.setdefault(m.group(2), m.group(1))
        if 'interface' in text:
            for m in CLIENT_IFACE.finditer(text):
                path = re.search(r'''\bpath\s*=\s*"([^"]*)"''', m.group(2) or '')
                bases = re.findall(r'[A-Za-z_]\w*', re.sub(r'<[^<>]*>', '', m.group(4) or ''))
                self.client_ifaces.setdefault(m.group(3), (path.group(1) if path else '', bases))

    def inherited_prefix(self, header, name, depth=0):
        routes = self.class_routes
        m = CLASS_BASES.search(header)
        if not m or depth > 3:
            return None
        for base in re.findall(r'[A-Za-z_]\w*', re.sub(r'<[^<>]*>', '', m.group(1))):
            if base in routes and base != name:
                return routes[base].replace('[controller]', re.sub(r'Controller$', '', name))
        return None

    def reg_index(self, src):
        cached = src.reg_pairs
        if cached is None:
            pairs, back = bracket_pairs(src.struct)
            cached = src.reg_pairs = (pairs, [p[0] for p in pairs], back)
        return cached

    def enclosing(self, src, pos):
        pairs, starts, _ = self.reg_index(src)
        i = bisect_right(starts, pos) - 1
        steps = 0
        while i >= 0 and steps < 2000:
            start, end, opener = pairs[i]
            if start < pos < end:
                return start, end, opener
            i -= 1
            steps += 1
        return None

    def chain_head(self, src, dot):
        """Receptor de una cadena `a.b(...).c(...)` que termina en `dot` (separador previo al método): la variable de la cabeza o,
        si la cabeza es una construcción (`new X()`, `x.Router()`), la variable a la que se asigna la cadena."""
        s, back = src.struct, self.reg_index(src)[2]
        i, head, called = dot, None, False
        for _ in range(400):
            j = i - 1
            while j >= 0 and s[j] in ' \t\r\n':
                j -= 1
            if j < 0:
                break
            if s[j] in ')]':
                if j not in back:
                    break
                i, called = back[j], True
                continue
            m = IDENT_BACK.search(s, max(0, j - 120), j + 1)
            if not m:
                break
            i, head = m.start(1), m.group(1)
            k = i - 1
            while k >= 0 and s[k] in ' \t\r\n':
                k -= 1
            if k >= 0 and s[k] == '.':
                i = k - 1 if k > 0 and s[k - 1] == '?' else k
                continue
            if k >= 1 and s[k - 1:k + 1] in ('::', '->'):
                i = k - 1
                continue
            break
        if head is None:
            return ''
        if called or head[:1].isupper():
            before = re.sub(r'\bnew\s+$', '', s[max(0, i - 160):i])
            a = ASSIGNED.search(before)
            if a:
                return a.group(1)
        return head

    def scan_registrations(self, src):
        rel, lang = src.rel, src.lang
        if lang not in REG_LANGS or self.is_test(rel) or self.generated(rel):
            return
        s = src.struct
        found = []
        for start, end in src.strings:
            if end - start > 240:
                continue
            lit = src.literal(start)
            if not lit:
                continue
            content, _, prefix, _ = lit
            if 'f' in prefix.lower() or not content or len(content) > 200:
                continue
            if content.startswith('/'):
                if not PATH_LIT.fullmatch(content) or content.startswith('//') or FILE_LIKE.search(content):
                    continue
                kind = 'path'
            elif RPC_LIT.fullmatch(content) and not FILE_LIKE.search(content):
                kind = 'rpc'
            else:
                continue
            enc = self.enclosing(src, start)
            if not enc or enc[2] != '(':
                continue
            open_pos = enc[0]
            name_m = IDENT_BACK.search(s, max(0, open_pos - 160), open_pos)
            if not name_m or name_m.group(1) in B.KEYWORDS or name_m.group(1) in NOT_ROUTE_NAMES:
                continue
            name = name_m.group(1)
            k = name_m.start(1) - 1
            while k >= 0 and s[k] in ' \t\r\n':
                k -= 1
            dotted = k >= 0 and (s[k] == '.' or s[max(0, k - 1):k + 1] in ('::', '->'))
            found.append((name_m.start(1), open_pos, name, dotted, k, start, end, content, kind))
        found += self.const_path_args(src)
        if not found:
            self.router_passing(src, set())
            return
        calls = {}
        for item in found:
            calls.setdefault(item[1], []).append(item)
        regs, mounts = [], []
        for open_pos, items in sorted(calls.items()):
            pos, _, name, dotted, k, *_ = items[0]
            line = src.line(pos)
            if (rel, line) in self.route_lines:
                continue
            args, close = src.args(open_pos)
            if close < 0 or not args:
                continue
            lits, others = [], []
            spans = {(st, en): (content, kind) for _, _, _, _, _, st, en, content, kind in items}
            for a, b in args:
                hit = next(((st, en) for st, en in spans if a <= st < b), None)
                if hit:
                    kw = re.fullmatch(r'\s*(?:(\w+)\s*[=:]\s*)?', s[a:hit[0]])
                    if kw and not s[hit[1]:b].strip() and (kw.group(1) in (None, 'path', 'rule', 'url', 'route', 'pattern', 'prefix',
                                                                            'value', 'template')):
                        lits.append(spans[hit])
                        continue
                others.append((a, b))
            if not lits:
                continue
            recv = self.chain_head(src, k) if dotted else ''
            if recv in NOT_ROUTE_RECV:
                continue
            kinds = {kd for _, kd in lits}
            if kinds == {'rpc'} and not (dotted and (ROUTERISH.search(recv or '') or recv in self.js_server_vars_cached(src))
                                         and name.lower() in VERB_NAME):
                continue
            lits = [c for c, kd in lits if kd == 'path' or kinds == {'rpc'}]
            if PREFIX_NAME.match(name) and not others and dotted:
                regs.append(('prefix', line, recv, name, lits[0], None, pos))
                continue
            target = None
            for a, b in reversed(others):
                kw = re.match(r'\s*(\w+)\s*[=:](?![=:])\s*', s[a:b])
                if kw and kw.group(1) not in ('handler', 'view', 'view_func', 'to', 'action', 'controller', 'resource', 'callback',
                                              'component', 'app'):
                    continue
                target = self.reg_target(src, (a + kw.end()) if kw else a, b, line)
                if target:
                    break
            if not target:
                continue
            verbs = self.reg_verbs(src, name, open_pos, close)
            if target[0] == 'inline' and dotted and name.lower() in VERB_NAME and CLIENT_RECV.match(recv or '') \
                    and recv not in self.js_server_vars_cached(src):
                continue
            for tpl in lits:
                if target[0] in ('module', 'local'):
                    mounts.append((line, recv, tpl, target, pos))
                else:
                    regs.append(('route', line, recv, verbs, tpl, target[1], pos))
        local_recvs = {r[2] for r in regs if r[0] == 'route'} | {m[1] for m in mounts}
        self.router_passing(src, local_recvs)
        for line, recv, tpl, target, pos in mounts:
            if target[0] == 'local' and target[1] not in local_recvs:
                continue
            if target[0] == 'local':
                self.local[rel][target[1]] = (recv, tpl)
            else:
                self.mounts[(target[1], None)].append((rel, recv, tpl, ''))
                self.mount_links.append((rel, line, (target[1], self.default_name(target[1]))))
        for reg in regs:
            if reg[0] == 'prefix':
                _, line, recv, _, tpl, _, pos = reg
                if recv and recv not in self.local[rel]:
                    self.local[rel][recv] = (None, tpl)
                continue
            _, line, recv, verbs, tpl, handler, pos = reg
            self.route(src, pos, recv, verbs, tpl, handler)

    def router_passing(self, src, recvs):
        """`resourceRoutes(managementRouter, tenant)`: un router del fichero pasado como primer argumento a una función de otro
        fichero que registra rutas sobre ese parámetro es un montaje (`finish_router_passing`)."""
        s = src.struct
        names = {r for r in recvs if r and re.fullmatch(r'[A-Za-z_$][\w$]*', r)}
        names |= set(re.findall(r'(?<![\w$.])([A-Za-z_$][\w$]*)\s*(?::[^=;\n]+)?=\s*(?:new\s+)?(?:[\w$]+\.)?(?:\w*Router|express|Hono|Koa|'
                                r'Elysia|Fastify|APIRouter|Blueprint|gin\.New|gin\.Default|chi\.NewRouter|mux\.NewRouter)\s*\(', src.code))
        if not names:
            return
        rx = re.compile(r'(?<![\w$.])([A-Za-z_$][\w$]*)\s*\(\s*(%s)\s*[,)]' % '|'.join(map(re.escape, sorted(names))))
        for m in rx.finditer(s):
            if m.group(1) in B.KEYWORDS or m.group(1) in names:
                continue
            line = src.line(m.start())
            target = self.reg_target(src, m.start(1), m.end(1), line)
            if target and target[0] == 'ref' and target[1] and self.g.nodes[target[1]]['file'] != src.rel:
                self.router_calls.append((src.rel, line, target[1]))

    def finish_router_passing(self):
        by_file = defaultdict(set)
        for rel, line, recv, *_ in self.pending:
            by_file[rel].add(recv)
        for rel, line, fn in self.router_calls:
            meta = self.g.nodes[fn]
            text = self.text(meta['file']) or ''
            head = '\n'.join(text.split('\n')[(meta.get('line') or 1) - 1:(meta.get('line') or 1) + 8])
            name = re.escape(meta['name'].rsplit('.', 1)[-1])
            sig = re.search(rf'\b{name}\s*(?:<[^()]*>)?\s*\(\s*(?:\.\.\.\s*\[\s*)?([A-Za-z_$][\w$]*)', head) or \
                re.search(rf'\b{name}\s*=\s*(?:async\s*)?\(\s*(?:\.\.\.\s*\[\s*)?([A-Za-z_$][\w$]*)', head)
            if sig and sig.group(1) in by_file.get(meta['file'], ()):
                self.mount_links.append((rel, line, ('sym', fn)))

    def const_path_args(self, src):
        """Rutas en una constante del fichero (`const filesPath = '/domains/:id/files'; router.get(filesPath, ..)`): el identificador
        cuenta como el literal en llamadas con nombre de verbo sobre un receptor."""
        code, s = src.code, src.struct
        consts = {}
        for m in re.finditer(r'''(?<![\w$.])(?:const|let|var|final|val)\s+([A-Za-z_$][\w$]*)\s*(?::[^=;\n]+)?=\s*(['"])(/[\w\-./:{}<>*]*)\2\s*;?[ \t]*$''',
                             code, re.M):
            if PATH_LIT.fullmatch(m.group(3)) and not FILE_LIKE.search(m.group(3)):
                consts[m.group(1)] = m.group(3)
        if not consts:
            return []
        out = []
        rx = re.compile(r'(?<![\w$])(get|post|put|patch|delete|all|head|options)\s*\(\s*(%s)\s*[,)]' % '|'.join(map(re.escape, consts)))
        for m in rx.finditer(s):
            k = m.start(1) - 1
            while k >= 0 and s[k] in ' \t\r\n':
                k -= 1
            if k < 0 or s[k] != '.':
                continue
            open_pos = s.index('(', m.end(1))
            out.append((m.start(1), open_pos, m.group(1), True, k, m.start(2), m.end(2), consts[m.group(2)], 'path'))
        return out

    def js_server_vars_cached(self, src):
        cached = src.reg_servers
        if cached is None:
            cached = src.reg_servers = self.js_server_vars(src) if src.lang == 'js' else set()
        return cached

    def reg_verbs(self, src, name, open_pos, close):
        low = name.lower()
        if low in VERB_NAME:
            return [VERB_NAME[low]]
        m = VERB_IN_NAME.fullmatch(name)
        if m:
            return [m.group(1).upper()]
        text = src.code[open_pos:close]
        mm = B.PY_METHODS.search(text)
        if mm:
            verbs = B.main_verbs(B.quoted_all(mm.group(1)))
            if verbs:
                return verbs
        mm = B.METHOD_KW.search(text)
        if mm and mm.group(1).upper() in B.VERBS:
            return [mm.group(1).upper()]
        args, _ = src.args(open_pos)
        first = src.code[args[0][0]:args[0][1]] if args else ''
        listed = re.findall(r'''["'](GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)["']|\bMethod(Get|Post|Put|Patch|Delete|Head|Options)\b''', first)
        if listed and '/' not in first:  # lista de verbos como primer argumento: `Match([]string{"GET", "HEAD"}, "/x", h)`
            return list(dict.fromkeys((a or b).upper() for a, b in listed))
        return ['ANY']

    def reg_target(self, src, a, b, line):
        """Destino de un argumento de registro: ('inline'|'ref', nid), ('module', fichero) o ('local', variable); si el nombre no
        se resuelve, `variable.Metodo` por el tipo de la variable."""
        found = self.reg_target_named(src, a, b, line)
        if found is None:
            typed = self.typed_method(src, src.code[a:b].strip(), a)
            if typed:
                return ('ref', typed)
        return found

    def reg_target_named(self, src, a, b, line):
        code, struct, rel = src.code, src.struct, src.rel
        flat = struct[a:b].strip()
        text = code[a:b].strip()
        if not flat:
            return None
        if B.INLINE.match(flat) and not flat.startswith(('{', 'new ', '[')):
            if flat.startswith('(') and '=>' not in flat and '->' not in flat and not re.match(r'\(\s*(?:async\s+)?(?:function|lambda)\b', flat):
                return None
            at = a + (len(code[a:b]) - len(code[a:b].lstrip()))
            return ('inline', self.owner(rel, src.line(at)))
        m = REF.fullmatch(text)
        if not m:
            return None
        ref = re.sub(r'\s+', '', m.group(1))
        ref = MOUNT_TAIL.sub('', ref + ('()' if re.search(r'\(\s*\)$', text) else ''))
        ref = re.sub(r'\(\)$', '', ref)
        if ref in ('this', 'self', 'null', 'None', 'nil', 'true', 'false', 'True', 'False', 'undefined'):
            return None
        head = re.split(r'\.|::|->', ref)[0]
        if src.lang == 'js':
            trel = self.js_import_target(src, head)
            if trel:
                trel = self.barrel_target(trel, self.js_imported_name(src, head))
                rest = ref[len(head) + 1:] if ref != head else ''
                name = rest.rsplit('.', 1)[-1] if rest else self.js_imported_name(src, head)
                node = self.in_file(trel, name) if name and name not in ('default',) else None
                if not node and not rest:
                    dm = DEFAULT_EXPORT.search(self.text(trel) or '')
                    node = self.in_file(trel, dm.group(1)) if dm else None
                    if node and self.g.nodes[node]['kind'] not in ('function', 'method', 'class'):
                        node = None
                if node:
                    return ('ref', node)
                return ('module', trel)
        if '.' not in ref and '::' not in ref and '->' not in ref and re.search(rf'(?<![\w$.]){re.escape(ref)}\s*(?::[^=\n]+)?=(?!=)', struct):
            node = self.in_file(rel, ref)
            if node and self.g.nodes[node]['kind'] in ('function', 'method', 'class'):
                return ('ref', node)
            return ('local', ref)
        node = self.imported(src, ref) if src.lang in ('js', 'py') else None
        if node and self.g.nodes[node]['kind'] in ('function', 'method', 'class'):
            return ('ref', node)
        if src.lang == 'py' and '.' not in ref:
            key = self.py_target(src, ref)
            if key and key[0] and key[0] != rel:
                node = self.in_file(key[0], key[1] or ref) or self.py_reexport(key[0], key[1] or ref)
                if node and self.g.nodes[node]['kind'] in ('function', 'method', 'class'):
                    return ('ref', node)
            alias = re.search(rf'^[ \t]*from\s+([\w.]+)\s+import\s+[^\n]*?\b(\w+)\s+as\s+{re.escape(ref)}\b', src.code, re.M)
            if alias:
                key = self.py_module(rel, alias.group(1))
                node = self.in_file(key, alias.group(2)) if key else None
                if not node and key and key.endswith('__init__.py'):
                    found = [n for n in self.short.get(alias.group(2), []) if self.g.nodes[n]['file'].startswith(key.rsplit('/', 1)[0] + '/')]
                    node = found[0] if len(found) == 1 else None
                if node:
                    return ('ref', node)
        parts = [p for p in re.split(r'\.|::|->', ref) if p]
        short = parts[-1]
        local = self.in_file(rel, short)
        if local and len(parts) == 1:
            return ('ref', local)
        cands = [n for n in self.short.get(short, []) if self.g.nodes[n]['kind'] in ('function', 'method', 'class')
                 and not self.is_test(self.g.nodes[n]['file'])]
        if len(parts) > 1:
            owner = parts[-2]
            owned = [n for n in cands if self.g.nodes[n]['name'].endswith(f'{owner}.{short}')]
            if owned:
                cands = owned
            elif owner[:1].islower() and src.lang == 'py':
                mod = [n for n in cands if self.g.nodes[n]['file'].rsplit('/', 1)[-1].split('.')[0] == owner]
                cands = mod
            else:
                return None
        elif not short[:1].isupper() and not self.mentions_import(src, short):
            return None
        found = self.pick(rel, cands)
        return ('ref', found) if found else None

    def py_reexport(self, rel, name, depth=0):
        """`from .sub import name` en un `__init__.py` (o módulo fachada): sigue la reexportación hasta la definición."""
        if depth > 3 or not rel.endswith('.py'):
            return None
        text = self.text(rel) or ''
        for m in B.PY_IMPORT.finditer(text):
            names = {p.strip().split(' as ')[-1].strip(): p.strip().split(' as ')[0].strip() for p in m.group(2).split(',') if p.strip()}
            if name not in names:
                continue
            target = self.py_module(rel, m.group(1))
            if not target:
                return None
            return self.in_file(target, names[name]) or self.py_reexport(target, names[name], depth + 1)
        return None

    def mentions_import(self, src, name):
        return bool(re.search(rf'^[ \t]*(?:from\s+\S+\s+)?import\b[^\n]*\b{re.escape(name)}\b|^[ \t]*use\s+[^\n]*\b{re.escape(name)}\b',
                              src.code, re.M))

    def barrel_target(self, trel, name):
        """Sigue reexportaciones `export { default } from './x'` / `export * from` de ficheros índice sin rutas propias."""
        for _ in range(3):
            text = self.text(trel) or ''
            if len(text) > 20000:
                return trel
            m = re.search(r'''export\s*\{\s*(?:default|%s)(?:\s+as\s+\w+)?\s*\}\s*from\s*['"]([^'"]+)['"]''' % re.escape(name or 'default'),
                          text) or (re.fullmatch(r'''\s*(?:export\s*\*\s*from\s*['"][^'"]+['"]\s*;?\s*)+''', text) and
                                    re.search(r'''from\s*['"]([^'"]+)['"]''', text))
            if not m:
                return trel
            nxt = self.js_resolve_spec(trel, m.group(1))
            if not nxt or nxt == trel:
                return trel
            trel = nxt
        return trel

    def default_name(self, rel):
        m = re.search(r'^\s*export\s+default\s+([A-Za-z_$][\w$]*)\s*;?\s*$', self.text(rel) or '', re.M)
        return m.group(1) if m and self.in_file(rel, m.group(1)) else None

    def workspace_file(self, spec):
        """Paquetes del propio monorepo (`name` de cada package.json) importados por nombre: `@org/pkg/sub` -> fichero."""
        packages = self.ws_packages
        if packages is None:
            packages = self.ws_packages = {}
            for f in self.files:
                if f.rsplit('/', 1)[-1] != 'package.json' or '/node_modules/' in '/' + f:
                    continue
                try:
                    meta = B.json.loads(self.text(f) or '{}')
                except ValueError:
                    continue
                name = meta.get('name') if isinstance(meta, dict) else None
                if isinstance(name, str) and name and name not in packages:
                    folder = f.rsplit('/', 1)[0] if '/' in f else ''
                    entry = meta.get('exports')
                    if isinstance(entry, dict):
                        entry = entry.get('.')
                        if isinstance(entry, dict):
                            entry = entry.get('import') or entry.get('default') or entry.get('types')
                    entry = entry if isinstance(entry, str) else meta.get('main') if isinstance(meta.get('main'), str) else None
                    packages[name] = (folder, entry)
        name = next((n for n in sorted(packages, key=len, reverse=True) if spec == n or spec.startswith(n + '/')), None)
        if not name:
            return None
        folder, entry = packages[name]
        rest = spec[len(name):].lstrip('/')
        base = '/'.join(x for x in (folder, rest) if x)
        cands = [base + s for s in ('.ts', '.tsx', '.js', '.mjs', '/index.ts', '/index.tsx', '/index.js', '/src/index.ts', '/src/index.js')]
        if not rest and entry:
            cands.insert(0, B.os.path.normpath('/'.join(x for x in (folder, entry) if x)).replace(B.os.sep, '/'))
            cands += [B.os.path.splitext(cands[0])[0] + s for s in ('.ts', '.tsx')]
        if rest:
            cands += [folder + '/src/' + rest + s for s in ('.ts', '.tsx', '.js', '/index.ts')]
        return next((c for c in cands if c in self.fileset), None)

    def expand_handler(self, verbs, handler):
        """Una clase registrada como handler se expande a sus métodos con nombre de verbo HTTP (`get`, `on_post`; si no hay ninguno,
        `index/show/create/update/destroy`); si no tiene ninguno, la clase sigue siendo el handler."""
        meta = self.g.nodes.get(handler) if handler else None
        if not meta or meta.get('kind') != 'class' or B.EXT_LANG.get(B.os.path.splitext(meta['file'])[1]) in ('rb', 'ex'):
            return [(v, handler) for v in verbs]  # en Ruby/Elixir la clase es el controlador de acciones, no un recurso por verbo
        cls = meta['name']
        methods = {}
        for n in self.owners.get(cls, []):
            m = self.g.nodes[n]
            if m['file'] == meta['file']:
                methods[m['name'].rsplit('.', 1)[-1]] = n
        by_verb = {}
        for name, n in sorted(methods.items()):
            low = name.lower()
            low = low[3:] if low.startswith('on_') else low
            if low in CLASS_VERB:
                by_verb.setdefault(CLASS_VERB[low], n)
        if not by_verb:
            for name, n in sorted(methods.items()):
                if name in CLASS_REST:
                    by_verb.setdefault(CLASS_REST[name], n)
        out = []
        for verb in verbs:
            if verb == 'ANY' and by_verb:
                out += sorted(by_verb.items())
            elif verb in by_verb:
                out.append((verb, by_verb[verb]))
            else:
                out.append((verb, handler))
        return out

    # ------------------------------------------------------------------ clientes: el parámetro de un wrapper fluye a la URL

    def fn_params(self, src, nid):
        cache = self.param_cache
        if nid in cache:
            return cache[nid]
        meta = self.g.nodes.get(nid) or {}
        params = []
        if meta.get('line') and meta.get('kind') in ('function', 'method'):
            lines = src.code.split('\n', meta['line'] + 30)[meta['line'] - 1:meta['line'] + 29]  # firmas largas en varias líneas
            head = ' '.join(lines)
            name = re.escape(meta['name'].rsplit('.', 1)[-1])
            sig = re.search(rf'\b{name}\s*(?:<[^()]*>)?\s*\(([^)]*)\)', head) or \
                re.search(rf'\b{name}\s*(?::[^=]+)?=\s*(?:async\s+)?(?:function\s*\w*\s*)?\(([^)]*)\)', head) or \
                re.search(rf'\b{name}\s*(?::[^=]+)?=\s*(?:async\s+)?([A-Za-z_$][\w$]*)\s*=>', head)
            if sig:
                params = [B.param_name(p, src.lang) for p in sig.group(1).split(',')]
                params = [p for p in params if p and p not in ('self', 'cls', 'this')]
        cache[nid] = params
        return params

    def flow_value(self, src, a, b, env):
        first = src.code[a:b].lstrip()
        if first.startswith('{'):
            uu = B.URL_KW.search(src.code, a, b)
            return src.expr(uu.end(), 0, env) if uu else None
        return src.expr(a, 0, env)

    def flow_method(self, src, name, args, env, params):
        low = name.lower()
        if low in VERB_NAME and low not in ('all', 'any'):
            return ('lit', VERB_NAME[low])
        for a, b in args:
            text = src.code[a:b].strip()
            lit = re.fullmatch(r'''['"`](\w+)['"`]''', text)
            if lit and lit.group(1).upper() in B.VERBS:
                return ('lit', lit.group(1).upper())
            if text in params and re.search(r'(?i)method|verb', text):
                return ('param', params.index(text))
            if text.startswith('{'):
                mm = re.search(r'''\bmethod\s*:\s*(?:['"`](\w+)['"`]|([A-Za-z_$][\w$]*))|(?<![\w$.])(method)\s*[,}]''', text)
                if mm and mm.group(1):
                    return ('lit', mm.group(1).upper())
                var = mm and (mm.group(2) or mm.group(3))
                if var in params:
                    return ('param', params.index(var))
        return ('lit', 'ANY')

    def scan_url_flow(self, src):
        """Funciones cuyo parámetro termina en la URL de una llamada de cliente (`_get(path) => fetch(base + path)`)."""
        if src.lang not in ('js', 'py', 'php', 'rb', 'kt', 'java', 'cs', 'c') or self.is_test(src.rel):
            return
        code = src.code
        for m in stem_calls(code, FLOW_STEMS, FLOW_CALL):
            self.flow_site(src, m, m.group(1), None)
        if 'ajax' in code or 'axios' in code or 'request' in code:
            self.options_wrappers(src)

    def options_wrappers(self, src):
        """Funciones cuyo parámetro es el objeto de opciones de una petición (`$.ajax({...opts})`, `axios(opts)`,
        `axios.request(opts)`): la URL y el verbo vienen de las claves `url` y `method`/`type` de quien la llama
        (`createAjaxRequest({ url: '/tag', method: 'POST' })`), también a través de otras funciones (`createFetchHandler(s, '/tag')`)."""
        code, s = src.code, src.struct
        if E2E_DIR.search(src.rel) or src.lang != 'js':
            return
        for m in OPTIONS_CLIENT.finditer(s):
            fn = self.function_at(src, m.start())
            if not fn:
                continue
            params = self.fn_params(src, fn)
            args, close = src.args(m.end() - 1)
            if close < 0 or len(args) != 1 or not params:
                continue
            arg = code[args[0][0]:args[0][1]].strip()
            names = {arg} if re.fullmatch(r'[A-Za-z_$][\w$]*', arg) else set(re.findall(r'\.\.\.\s*([A-Za-z_$][\w$]*)', arg))
            meta = self.g.nodes[fn]
            body = code[src.nl[meta['line'] - 2] if meta['line'] > 1 else 0:m.start()]
            for n in list(names):  # `const opts = { ...original }` / `const opts = original`
                for a in re.finditer(rf'\b(?:const|let|var)\s+{re.escape(n)}\s*=\s*(?:\{{\s*\.\.\.\s*([A-Za-z_$][\w$]*)|([A-Za-z_$][\w$]*)\s*;)', body):
                    names.add(a.group(1) or a.group(2))
            hit = next((p for p in params if p in names), None)
            if hit is None:
                continue
            short = meta['name'].rsplit('.', 1)[-1]
            item = {'index': params.index(hit), 'tpl': '\0' + WRAP, 'method': ('opts',), 'sym': fn, 'rel': src.rel, 'opts': True,
                    'cls': meta['name'].rsplit('.', 1)[0] if meta['kind'] == 'method' and '.' in meta['name'] else None}
            book = self.url_wrappers
            if all(w['sym'] != fn for w in book.get(short, [])):
                book.setdefault(short, []).append(item)
                self.url_wrappers_new.add(short)

    def flow_site(self, src, m, name, wrapper):
        fn = self.function_at(src, m.start())
        if not fn and (wrapper is None or src.lang != 'js' or not (wrapper.get('opts') or wrapper.get('chain'))):
            return None
        params = self.fn_params(src, fn) if fn else []  # una llamada a un envoltorio en el nivel del módulo también es cliente
        open_pos = m.end() - 1
        args, close = src.args(open_pos)
        if close < 0 or (not args and not name.startswith('new ')):
            return None
        env = {p: MARK[i] for i, p in enumerate(params[:len(MARK)])}
        if wrapper is None:
            at = 0
            if name in ('request', 'exchange') and len(args) > 1:
                first = src.code[args[0][0]:args[0][1]].strip()
                if re.fullmatch(r'''['"`]\w+['"`]''', first) or re.search(r'(?i)method|verb', first):
                    at = 1
            if not args:
                return None
            value = self.flow_value(src, args[at][0], args[at][1], env)
            if not value or not any(mk in value for mk in MARK):
                value = next((v for v in self.url_alternatives(src, args[at][0], args[at][1], env=env) if any(mk in v for mk in MARK)), None)
            if not value:
                return None
            rm = RECV_BACK.search(src.code, max(0, m.start() - 80), m.start())
            chain = B.js_chain(src.code, m.start()) if rm else []
            client_like = any(B.JS_CLIENT_NAMES.match(x) for x in chain if x not in ('this', 'self'))
            used = next(i for i, mk in enumerate(MARK) if mk in value)
            if not client_like and not PATH_PARAM.search(params[used] if used < len(params) else '') \
                    and not (B.SCHEME.sub('', value.split(MARK[used], 1)[0]).startswith('\0')):
                return None
            method = ('lit', 'GET') if name.startswith('new ') else self.flow_method(src, name, args, env, params)
            tpl = value
        else:
            if len(args) <= wrapper['index']:
                return None
            a, b = args[wrapper['index']]
            if wrapper.get('opts'):
                return self.options_site(src, m, wrapper, args, env, params, fn)
            value = self.flow_value(src, a, b, env)
            if value is None:
                return None
            tpl = wrapper['tpl'].replace(WRAP, value)
            method = wrapper['method']
            if method[0] == 'param':
                if len(args) <= method[1]:
                    return None
                arg = src.code[args[method[1]][0]:args[method[1]][1]].strip()
                lit = re.fullmatch(r'''['"`](\w+)['"`]''', arg)
                if lit and lit.group(1).upper() in B.VERBS:
                    method = ('lit', lit.group(1).upper())
                elif arg in params:
                    method = ('param', params.index(arg))
                else:
                    method = ('lit', 'ANY')
        marks = [i for i, mk in enumerate(MARK) if mk in tpl]
        wrapping = False
        if marks:
            i = marks[0]
            out = tpl.replace(MARK[i], WRAP)
            for j in marks[1:]:
                out = out.replace(MARK[j], '\0')
            meta = self.g.nodes[fn]
            short = meta['name'].rsplit('.', 1)[-1]
            lead = B.SCHEME.sub('', out.split(WRAP, 1)[0].strip()).strip('\0/')
            wrapping = WRAP in out and short not in FLOW_SKIP and (not lead or PATH_PARAM.search(params[i] if i < len(params) else ''))
        if marks and not wrapping:
            if wrapper is None:
                return None
            for mk in MARK:
                tpl = tpl.replace(mk, '\0')
        elif marks:
            chain = bool(wrapper and (wrapper.get('chain') or wrapper.get('opts')))  # derivado de un envoltorio de opciones (JS)
            item = {'index': i, 'tpl': out, 'method': method, 'sym': fn, 'rel': src.rel, 'chain': chain,
                    'cls': meta['name'].rsplit('.', 1)[0] if meta['kind'] == 'method' and '.' in meta['name'] else None}
            book = self.url_wrappers
            if all(w['sym'] != fn for w in book.get(short, [])):
                book.setdefault(short, []).append(item)
                self.url_wrappers_new.add(short)
            return None
        if wrapper is not None:
            self.client(src, m.start(), method[1] if method[0] == 'lit' else 'ANY', tpl, self.owner(src.rel, src.line(m.start())))
        return None

    def options_site(self, src, m, wrapper, args, env, params, fn):
        """Llamada a un envoltorio de opciones con un objeto literal: cliente con `url`/`method` del objeto, o nuevo envoltorio si
        la URL viene de un parámetro de la función que llama."""
        a, b = args[wrapper['index']]
        if E2E_DIR.search(src.rel):
            return None
        start = src.skip(a)
        ident = re.fullmatch(r'[A-Za-z_$][\w$]*', src.code[start:b].strip())
        if ident:  # `const ajaxOptions = { url: .., method: .. }; createAjaxRequest(ajaxOptions)`
            decl = None
            for decl in re.finditer(rf'\b(?:const|let|var)\s+{ident.group()}\s*(?::[^=]+)?=\s*\{{', src.struct[max(0, start - 3000):start]):
                pass
            if not decl:
                return None
            start = max(0, start - 3000) + decl.end() - 1
            b = src.close(start) + 1
            if b <= 0:
                return None
            a = start
        if src.struct[start:start + 1] != '{':
            return None
        uu = re.compile(r'(?<![\w$.])url\s*(?::\s*|(?=\s*[,}\n]))').search(src.code, start, b)  # `url: x` o abreviado `url,`
        if not uu or self.enclosing(src, uu.start())[0] != start:
            return None
        inner, _ = src.args(start)
        span = next(((x, y) for x, y in inner if x <= uu.start() < y), None)
        if not span:
            return None
        at = uu.end() if ':' in src.code[uu.start():uu.end()] else uu.start()
        values = [v for v in [src.expr(at, 0, env)] + self.url_alternatives(src, at, span[1], env=env) if v]
        lead = re.match(r'\s*(?:`\$\{\s*([A-Za-z_$][\w$]*)\s*\}[^`]*`|([A-Za-z_$][\w$]*)\s*$)', src.code[at:span[1]])
        var = lead and (lead.group(1) or lead.group(2))
        if var and var not in env:
            # variable local con ramas (`const requestUrl = id ? `${url}/${id}` : url`): cada rama es una URL posible
            decl = None
            for decl in re.finditer(rf'\b(?:const|let|var)\s+{re.escape(var)}\s*=\s*', src.struct[max(0, start - 3000):start]):
                pass
            if decl:
                vs = max(0, start - 3000) + decl.end()
                ve = vs + len(re.match(r'[^;\n]*', src.struct[vs:]).group())
                alts = [v for v in self.url_alternatives(src, vs, ve, env=env) if v]
                if len(alts) > 1:
                    values = alts
        method = self.flow_method(src, 'request', [(a, b)], env, params)
        mt = re.search(r'''\bmethod\s*:\s*(\w+)\s*\?\s*['"`](\w+)['"`]\s*:\s*['"`](\w+)['"`]''', src.code[start:b])
        if mt and method == ('lit', 'ANY'):
            # `method: id ? 'PUT' : 'POST'` con `url: id ? `${u}/${id}` : u`: se emparejan las ramas de la misma condición
            values = values[-2:] if len(values) >= 2 else values
            pairs = [(mt.group(2).upper(), values[0]), (mt.group(3).upper(), values[-1])] if len(values) == 2 else \
                [(v, x) for v in (mt.group(2).upper(), mt.group(3).upper()) for x in values]
            for verb, value in pairs:
                self.options_value(src, m, fn, ('lit', verb), value)
            return None
        if method == ('lit', 'ANY'):
            tm = re.search(r'''\btype\s*:\s*['"`](\w+)['"`]''', src.code[start:b])
            method = ('lit', tm.group(1).upper()) if tm and tm.group(1).upper() in B.VERBS else ('lit', 'GET')
        for value in dict.fromkeys(values):
            self.options_value(src, m, fn, method, value)
        return None

    def options_value(self, src, m, fn, method, value):
        meta = self.g.nodes.get(fn) or {'name': '', 'kind': 'module'}
        short = meta['name'].rsplit('.', 1)[-1]
        marks = [i for i, mk in enumerate(MARK) if mk in value]
        if marks:
            out = value.replace(MARK[marks[0]], WRAP)
            for j in marks[1:]:
                out = out.replace(MARK[j], '\0')
            if out.split(WRAP, 1)[0].strip('\0/') or short in FLOW_SKIP:
                return
            item = {'index': marks[0], 'tpl': '\0' + out, 'method': method, 'sym': fn, 'rel': src.rel, 'chain': True,
                    'cls': meta['name'].rsplit('.', 1)[0] if meta['kind'] == 'method' and '.' in meta['name'] else None}
            book = self.url_wrappers
            if all(w['sym'] != fn or w['tpl'] != item['tpl'] or w['method'] != method for w in book.get(short, [])):
                book.setdefault(short, []).append(item)
                self.url_wrappers_new.add(short)
            return
        if method[0] == 'lit':
            self.client(src, m.start(), method[1], '\0' + value, self.owner(src.rel, src.line(m.start())))

    def finish_url_flow(self):
        book, fresh = self.url_wrappers, set(self.url_wrappers_new)
        cache, done = {}, set()
        for _ in range(4):
            names = sorted(n for n in fresh if n not in done)
            if not names:
                break
            done.update(names)
            self.url_wrappers_new = set()
            quick = re.compile(r'(?<![\w$])(?:%s)\b' % '|'.join(map(re.escape, names)))
            rx = re.compile(r'(?<![\w$])(%s)\s*(?:<[^<>()]*(?:<[^<>()]*>[^<>()]*)*>)?\s*\(' % '|'.join(map(re.escape, names)))
            for rel in self.files:
                lang = B.EXT_LANG.get(B.os.path.splitext(rel)[1])
                if lang not in ('js', 'py', 'php', 'rb', 'kt', 'java', 'cs', 'c') or self.is_test(rel):
                    continue
                if rel not in cache:
                    text = self.text(rel)
                    cache[rel] = text if text and len(text) < 600 * 1024 else None
                text = cache[rel]
                if not text or not quick.search(text):
                    continue
                src = cache.get(('src', rel))
                if src is None:
                    src = cache[('src', rel)] = self.src(rel, lang, text)
                    src.scope = lambda pos, src=src: self.function_at(src, pos)
                for m in rx.finditer(src.code):
                    name = m.group(1)
                    rm = RECV_BACK.search(src.code, max(0, m.start() - 80), m.start())
                    recv = (rm.group(1) or rm.group(2)) if rm else None
                    head = src.code[max(0, m.start() - 60):m.start()]
                    if re.search(r'\b(?:function|def|fun|func|fn|sub)\s*\*?\s*$', head):
                        continue
                    close = src.close(m.end() - 1)
                    after = src.struct[close + 1:close + 80].lstrip() if close > 0 else ''
                    if re.match(r'(?::[^;=\n]*?)?(?:\{|=>)', after) and not recv \
                            and re.match(r'\s*(?:(?:public|private|protected|static|async|override|readonly)\s+)*$',
                                         src.code[src.code.rfind('\n', 0, m.start()) + 1:m.start()]):
                        continue
                    cands = book.get(name, [])
                    if name in FLOW_GENERIC and not recv:
                        continue
                    if recv in ('this', 'self', 'super', 'static', '$this'):
                        own = self.owner(rel, src.line(m.start()))
                        cls = (self.g.nodes.get(own) or {}).get('name', '').rsplit('.', 1)[0]
                        cands = [w for w in cands if w['rel'] == rel or w['cls'] != cls] if len(cands) > 1 else cands
                    if len({w['sym'] for w in cands}) > 1:
                        same = [w for w in cands if w['rel'] == rel]
                        cands = same if len({w['sym'] for w in same}) == 1 else []
                    for w in cands:
                        if self.owner(rel, src.line(m.start())) != w['sym']:
                            self.flow_site(src, m, name, w)
            fresh = set(self.url_wrappers_new)

    # ------------------------------------------------------------------ eventos y jobs: identidad compartida

    def collect_class_bases(self, text):
        if 'class' not in text:
            return
        for m in CLASS_HEAD.finditer(text):
            for base in re.findall(r'[A-Za-z_]\w*', re.sub(r'<[^<>]*(?:<[^<>]*>[^<>]*)*>|\([^()]*\)', '', m.group(2))):
                if base not in ('public', 'private', 'protected', 'internal', 'where', 'new', 'class', 'struct') and base != m.group(1):
                    self.impls[base].add(m.group(1))

    def ref_node(self, src, a, b, line):
        target = self.reg_target(src, a, b, line)
        return target[1] if target and target[0] in ('ref', 'inline') and target[1] else None

    def recv_type(self, src, recv):
        if not recv or recv in ('this', 'self'):
            return None
        key = re.escape(recv)
        for rx in (rf'(?<![\w.])([A-Z]\w*)(?:<[^<>()=;]*>)?\??\s+{key}\b(?!\s*\()', rf'(?<![\w$.]){key}\s*[?!]?:\s*([A-Z]\w*)',
                   rf'(?<![\w$.]){key}\s*=\s*new\s+([A-Z]\w*)', rf'\bself\.{key}\s*=\s*([A-Z]\w*)\s*\('):
            m = re.search(rx, src.code)
            if m:
                return m.group(1)
        return None

    def type_method(self, type_name, method, rel, nargs=None):
        impls = self.impls
        classes, frontier = [], [type_name]
        for _ in range(3):
            nxt = []
            for t in frontier:
                for c in sorted(impls.get(t, ())):
                    if c not in classes:
                        classes.append(c)
                        nxt.append(c)
            frontier = nxt
        if not classes:
            classes = [type_name]
        cands = []
        for cls in classes:
            for n in self.owners.get(cls, []):
                if self.g.nodes[n]['name'].rsplit('.', 1)[-1] == method and not self.is_test(self.g.nodes[n]['file']):
                    cands.append(n)
        if not cands and classes != [type_name]:
            cands = [n for n in self.owners.get(type_name, []) if self.g.nodes[n]['name'].rsplit('.', 1)[-1] == method]
        if len(cands) > 1 and nargs is not None:
            fit = [n for n in cands if (lambda r: r and r[0] <= nargs <= r[1])(self.arity(n))]
            cands = fit or cands
        if len(cands) > 1:
            files = {self.g.nodes[n]['file'] for n in cands}
            if len(files) == 1:
                return min(cands, key=lambda n: (self.g.nodes[n].get('line') or 0))
        return cands[0] if len(cands) == 1 else self.pick(rel, cands)

    def arity(self, nid):
        meta = self.g.nodes[nid]
        lines = (self.text(meta['file']) or '').split('\n')[(meta.get('line') or 1) - 1:(meta.get('line') or 1) + 3]
        m = re.search(rf'\b{re.escape(meta["name"].rsplit(".", 1)[-1])}\s*(?:<[^()]*>)?\s*\(([^)]*)\)', ' '.join(lines))
        if not m:
            return None
        parts = [p for p in m.group(1).split(',') if p.strip()]
        return len([p for p in parts if '=' not in p]), len(parts)

    def job_topic(self, nid):
        """Topic de un job: el nombre de la clase (su método perform/run/execute es el consumidor) o de la función."""
        meta = self.g.nodes[nid]
        if meta['kind'] == 'class':
            runs = [n for n in self.owners.get(meta['name'], []) if self.g.nodes[n]['file'] == meta['file']
                    and self.g.nodes[n]['name'].rsplit('.', 1)[-1] in JOB_METHODS]
            if len(runs) > 1:  # un `process()` privado auxiliar no es la entrada del job
                lines = (self.text(meta['file']) or '').split('\n')
                runs = [n for n in runs if not re.match(r'\s*(?:@\w+\s+)*(?:private|protected)\b', lines[(self.g.nodes[n].get('line') or 1) - 1]
                                                       if (self.g.nodes[n].get('line') or 0) <= len(lines) else '')
                        and not self.g.nodes[n]['name'].rsplit('.', 1)[-1].startswith('_')] or runs
            if len(runs) == 1:
                return meta['name'], runs[0]
        return meta['name'], nid

    def scan_jobs(self, src):
        """Productores de jobs por referencia: `X.delay()`, `new XTask().schedule()`, `enqueue(f)`, `Enqueue(() => svc.M())`; y claves
        (literal o constante) compartidas entre una llamada productora y un registro con handler."""
        if src.lang not in REG_LANGS or self.is_test(src.rel):
            return
        code, rel = src.code, src.rel
        keys = self.job_keys
        for m in stem_calls(code, PRODUCER_STEMS, PRODUCER_CALL):
            name = m.group(1)
            open_pos = m.end() - 1
            args, close = src.args(open_pos)
            if close < 0:
                continue
            line = src.line(m.start())
            rm = RECV_BACK.search(code, max(0, m.start() - 80), m.start())
            generic = re.search(r'<\s*([A-Z]\w*)\s*>\s*\($', code[m.start():m.end()])
            hit = None
            for a, b in args:
                lam = LAMBDA_CALL.match(src.struct, a)
                if lam and lam.end() <= b:
                    param, recv, meth = lam.group(1) or lam.group(2) or lam.group(5), lam.group(3) or lam.group(6), \
                        lam.group(4) or lam.group(7)
                    body_args, _ = src.args(lam.end() - 1)
                    nargs = len(body_args)
                    if recv and param and recv == param and generic:
                        target = self.type_method(generic.group(1), meth, rel, nargs)
                    elif recv:
                        typ = self.recv_type(src, recv) or (recv if recv[:1].isupper() else None)
                        target = self.type_method(typ, meth, rel, nargs) if typ else None
                    else:
                        own = self.owner(rel, line)
                        cls = (self.g.nodes.get(own) or {}).get('name', '').rsplit('.', 1)[0] if own else ''
                        target = self.type_method(cls, meth, rel, nargs) if cls else None
                        target = target or self.in_file(rel, meth)
                    if target:
                        hit = target
                        break
            if not hit and rm and name not in ('dispatch', 'Dispatch', 'push', 'add', 'Add', 'send', 'Send', 'publish', 'Publish', 'emit'):
                hit = self.job_receiver(src, rm.start() + (len(rm.group(1)) if rm.group(1) else 1), line)
            if not hit and name.lower() not in ('dispatch', 'trigger', 'push', 'add', 'send', 'publish', 'emit', 'schedule'):
                for a, b in args[:2]:
                    text = code[a:b].strip()
                    if re.fullmatch(r'[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*', text) and text not in ('this', 'self'):
                        node = self.ref_node(src, a, b, line)
                        if node and self.g.nodes[node]['kind'] in ('function', 'method', 'class'):
                            hit = node
                            break
            if hit:
                topic, sym = self.job_topic(hit)
                self.topic_uses.append((topic, rel, line, 'pub', '', 'mq'))
                meta = self.g.nodes[sym]
                self.topic_uses.append((topic, meta['file'], meta.get('line') or 1, 'sub', sym, 'mq'))
            key = self.key_arg(src, args)
            if key:
                keys.append((key, rel, line, 'sub' if hit else 'pub', hit))
            if rm and rm.group(2):
                ident = re.search(r'([A-Za-z_$][\w$]*)\s*\??(?:\.|->|::)\s*$', code[max(0, m.start() - 80):m.start()])
                if ident and ident.group(1)[:1].isupper() and ident.group(1) not in ('Task', 'BackgroundJob', 'RecurringJob', 'Promise'):
                    keys.append((ident.group(1), rel, line, 'pub', None))
        for s, e in src.strings:
            if e - s > 60:
                continue
            lit = src.literal(s)
            if not lit or not CRON.fullmatch(lit[0].strip()):
                continue
            enc = self.enclosing(src, s)
            before = src.struct[max(0, enc[0] - 40):enc[0]].rstrip() if enc else ''
            if not enc or enc[2] == '{' and before[-1:] not in ('=', ':', ',', '(', '[', '{', '') or enc[1] - enc[0] > 400:
                continue  # sólo tuplas/listas/objetos literales y argumentos, no cuerpos de clase o función
            for im in re.finditer(r'(?<![\w$.\'"])([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)', src.struct[enc[0] + 1:enc[1]]):
                a0 = enc[0] + 1 + im.start(1)
                node = self.ref_node(src, a0, a0 + len(im.group(1)), src.line(s))
                if node and self.g.nodes[node]['kind'] in ('function', 'method', 'class') and node != self.owner(rel, src.line(s)):
                    topic, sym = self.job_topic(node)
                    self.topic_uses.append((topic, rel, src.line(s), 'pub', '', 'mq'))
                    meta = self.g.nodes[sym]
                    self.topic_uses.append((topic, meta['file'], meta.get('line') or 1, 'sub', sym, 'mq'))
                    break
        if 'case' in code:
            for m in EMIT_DYNAMIC.finditer(code):
                args, close = src.args(m.end() - 1)
                if not args or src.literal(src.skip(args[0][0])):
                    continue
                for name in self.case_labels(src, m.start()):
                    if name not in B.COMMON_EVENTS:
                        self.topic_uses.append((name, rel, src.line(m.start()), 'pub', '', 'emitter'))
        if 'job' in code or 'Job' in code or 'func' in code:
            for m in JOB_DICT.finditer(code):
                if not word_start(code, m.start()) and code[m.start() - 1] not in '"\'':
                    continue
                a = m.end()
                b = a + len(re.match(r'[A-Za-z_$][\w$.]*', code[a:]).group())
                node = self.ref_node(src, a, b, src.line(a))
                if node and self.g.nodes[node]['kind'] in ('function', 'method', 'class'):
                    topic, sym = self.job_topic(node)
                    self.topic_uses.append((topic, rel, src.line(m.start()), 'pub', '', 'mq'))
                    meta = self.g.nodes[sym]
                    self.topic_uses.append((topic, meta['file'], meta.get('line') or 1, 'sub', sym, 'mq'))
        for m in stem_calls(code, CONSUMER_STEMS, CONSUMER_CALL):
            args, close = src.args(m.end() - 1)
            if close < 0 or len(args) < 2:
                continue
            key = self.key_arg(src, args)
            if not key:
                continue
            for a, b in args:
                for fa, fb, at in self.handler_values(src, a, b):
                    node = self.ref_node(src, fa, fb, src.line(at))
                    if node and self.g.nodes[node]['kind'] in ('function', 'method', 'class'):
                        keys.append((key, rel, src.line(at), 'sub', node))

    def case_labels(self, src, pos):
        """Literales de los `case "x":` consecutivos que abren el bloque del switch que contiene `pos`."""
        window = src.struct[max(0, pos - 4000):pos]
        base = pos - len(window)
        stops = list(re.finditer(r'\b(?:case\b|default\s*:|switch\s*\()', window))
        if not stops or not stops[-1].group().startswith('case'):
            return []
        labels, i = [], len(stops) - 1
        while i >= 0 and stops[i].group().startswith('case'):
            at = base + stops[i].start()
            m = re.match(r'case\s+(?:([\'"`])([\w.:\-/]+)\1|([A-Za-z_][\w.]*))\s*:', src.code[at:at + 200])
            if not m:
                break
            lit = src.literal(src.skip(at + 4)) if m.group(1) else None
            labels.append(lit[0] if lit else m.group(2) or m.group(3))
            if i == 0:
                break
            gap = window[stops[i - 1].end():stops[i].start()]
            if not re.fullmatch(r'\s+[^:]*:\s*', gap):
                break
            i -= 1
        return [x for x in labels if x and re.fullmatch(r'[\w.:\-/]+', x) and not x[:1].isupper()]

    def key_arg(self, src, args):
        for a, b in args[:2]:
            text = src.code[a:b].strip()
            if re.fullmatch(r'''(?:[A-Z]\w*\.)*[A-Z][A-Za-z0-9_]{3,}''', text) and not re.fullmatch(r'[A-Z][a-z]+', text):
                return text.rsplit('.', 1)[-1]
            lit = re.fullmatch(r'''(['"`])([\w.:\-/]{3,80})\1''', text)
            if lit and '/' not in lit.group(2)[:1] and lit.group(2) not in B.COMMON_EVENTS:
                return lit.group(2)
        return None

    def handler_values(self, src, a, b):
        """Referencias a funciones dentro de un argumento: directa, `{run: f}` o envuelta `{run: wrap("x", f)}`."""
        text = src.code[a:b].strip()
        if re.fullmatch(r'[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*', text):
            yield a + src.code[a:b].find(text), a + src.code[a:b].find(text) + len(text), a
            return
        if not text.startswith('{'):
            return
        for km in HANDLER_KEY.finditer(src.code, a, b):
            depth_ok = src.struct.count('{', a, km.start()) - src.struct.count('}', a, km.start()) == 1
            if not depth_ok:
                continue
            val_start = km.end()
            val_end = val_start
            for mm in B.ARGS_SPLIT.finditer(src.struct, val_start, b):
                if mm.group() in ',}' and src.struct.count('(', val_start, mm.start()) == src.struct.count(')', val_start, mm.start()):
                    val_end = mm.start()
                    break
            idents = list(re.finditer(r'(?<![\w$.\'"])([A-Za-z_$][\w$]*)(?![\w$])(?!\s*[(:])', src.struct[val_start:val_end]))
            for im in reversed(idents):
                s0 = val_start + im.start(1)
                if im.group(1) in ('async', 'await', 'function', 'this', 'job', 'req', 'res', 'ctx', 'c', 'e', 'err', 'data'):
                    continue
                yield s0, s0 + len(im.group(1)), km.start()
                break

    def job_receiver(self, src, end, line):
        """Cabeza de `X.delay()` / `new X().schedule()` / `X().perform()`: función o clase del repo."""
        text = src.struct[max(0, end - 160):end]
        m = re.search(r'(?:\bnew\s+)?([A-Za-z_$][\w$]*)\s*(\([^()]*\))?\s*$', text)
        if not m:
            return None
        name = m.group(1)
        if name in ('this', 'self', 'super') or name in B.KEYWORDS:
            return None
        before = text[:m.start()]
        if re.search(r'[\w$)\]]\s*\??\.\s*$', before):
            return None
        a = end - len(text) + m.start(1)
        node = self.ref_node(src, a, a + len(name), line)
        if node and B.EXT_LANG.get(B.os.path.splitext(self.g.nodes[node]['file'])[1]) != src.lang:
            return None
        if node and self.g.nodes[node]['kind'] in ('function', 'method', 'class'):
            if self.g.nodes[node]['kind'] == 'class' or not m.group(2):
                return node
        return None

    def finish_job_keys(self):
        keys = self.job_keys
        roles = {}
        for key, rel, line, role, node in keys:
            roles.setdefault(key, set()).add(role)
        for key, rel, line, role, node in sorted(keys, key=lambda k: (k[3] != 'sub',) + tuple(str(x) for x in k)):
            if roles.get(key) != {'pub', 'sub'}:
                continue
            if role == 'sub':
                topic, sym = self.job_topic(node)
                self.topic_uses.append((key, rel, line, 'sub', '', 'mq'))
                meta = self.g.nodes[sym]
                self.topic_uses.append((key, meta['file'], meta.get('line') or 1, 'sub', sym, 'mq'))
            else:
                self.topic_uses.append((key, rel, line, 'pub', '', 'mq'))

    # ------------------------------------------------------------------ datos: modelos declarados por estructura

    def collect_declared_models(self, rel, lang, text):
        """Clases/structs que declaran su tabla (`__tablename__`, `tableName`, `$table`, `db_table`, `TableName()`), o con un
        decorador/atributo de entidad (`@Table({tableName})`, `[Table("x")]`, `@Entity`, `@MappedEntity`, `@Document`)."""
        if self.is_test(rel) or lang not in ('py', 'js', 'java', 'kt', 'cs', 'php', 'rb', 'c', 'go'):
            return
        if not MODEL_HINT.search(text):
            return
        heads = [(m.start(), m.group(1)) for m in MODEL_CLASS.finditer(text)
                 if word_start(text, m.start()) and MODEL_CLASS_LEAD.fullmatch(text, text.rfind('\n', 0, m.start()) + 1, m.start())]
        for i, (pos, name) in enumerate(heads):
            if name in ('Meta', 'Config', 'Props'):
                continue
            end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
            body = text[pos:min(end, pos + 6000)]
            before = text[max(0, pos - 400):pos]
            ann = None
            for am in MODEL_ANN.finditer(before):
                ann = am
            if ann and re.search(r'\b(?:class|interface|struct)\b|[;}]\s*$', before[ann.end():]) and not re.fullmatch(r'[\s\S]*?\)\s*', before[ann.end():]):
                ann = ann if not re.search(r'\b(?:class|interface|struct)\s+\w', before[ann.end():]) else None
            key = MODEL_TABLE_KEY.search(body[:3000])
            table = None
            if ann:
                args = ann.group(2) or ''
                named = re.search(r'''\b(?:tableName|name|collection|value|table)\s*[:=]\s*['"](\w+)['"]''', args) or \
                    re.match(r'''\s*\(?\s*['"](\w+)['"]''', args)
                table = named.group(1) if named else None
                if not table and ann.group(1).lower() not in ('table', 'entity', 'mappedentity', 'document', 'mongoentity'):
                    continue
                table = table or name
            elif key and not re.search(r'\b(?:class|interface)\s+\w', body[len(name) + 8:key.start()]):
                table = key.group(1)
            if table:
                self.model_at(rel, text.count('\n', 0, pos) + 1, name, table, lang)
        if lang == 'go':
            for m in re.finditer(r'\bfunc\s*\(\s*(?:\w+\s+)?\*?(\w+)\s*\)\s*TableName\(\)\s*string\s*\{\s*return\s+"(\w+)"', text):
                decl = re.search(rf'^type\s+{re.escape(m.group(1))}\s+struct\b', text, re.M)
                if decl:
                    self.model_at(rel, text.count('\n', 0, decl.start()) + 1, m.group(1), m.group(2), lang)

    def migration_class(self, nid, name):
        rel = self.g.nodes[nid]['file']
        if rel.endswith(('.Designer.cs', 'ModelSnapshot.cs')):
            return True
        return bool(re.search(rf'\bclass\s+{re.escape(name)}\s*:\s*(?:[\w.]+\.)?Migration\b', self.text(rel) or ''))

    def load_json_env(self):
        """Ficheros JSON versionados de configuración de arranque (`launchSettings.json`, `.vscode/launch.json`, `*env*.json`) que
        el listado general no incluye: sus bloques `env` definen variables."""
        if not (self.root / '.git').exists():
            return
        self.is_tracked('')
        for rel in sorted(self.tracked or ()):
            if rel in self.fileset or not JSON_ENV_NAME.search(rel) or self.is_test(rel) or '/node_modules/' in '/' + rel:
                continue
            try:
                path = self.root / rel
                if path.stat().st_size > 256 * 1024:
                    continue
                text = path.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            self.scan_json_env(rel, text)

    def scan_json_env(self, rel, text):
        """Objetos JSON bajo una clave con `env` (`environmentVariables`, `env`): sus claves MAYÚSCULAS definen variables."""
        if self.is_test(rel) or not re.search(r'"[\w-]*(?:env|Env|ENV)[\w-]*"\s*:\s*\{', text):
            return
        mid = self.config_module(rel, text, 'json')
        for m in re.finditer(r'"[\w-]*(?:env|Env|ENV)[\w-]*"\s*:\s*\{([^{}]*)\}', text):
            for k in re.finditer(r'"([A-Z][A-Z0-9_]{2,})"\s*:', m.group(1)):
                self.env_defs.append((rel, text.count('\n', 0, m.start(1) + k.start()) + 1, k.group(1), mid))

    def reexports(self, trel, name, rel, depth=0):
        if depth > 3:
            return False
        text = self.text(trel) or ''
        if len(text) > 200000:
            return False
        for m in re.finditer(r'''export\s*(?:\{([^}]*)\}|\*)\s*from\s*['"]([^'"]+)['"]''', text):
            names = [p.split(' as ')[-1].strip() for p in (m.group(1) or '').split(',')]
            if m.group(1) is not None and name not in names and not any(n == 'default' for n in names):
                continue
            nxt = self.js_resolve_spec(trel, m.group(2))
            if nxt == rel or nxt and nxt != trel and self.reexports(nxt, name, rel, depth + 1):
                return True
        m = re.search(rf'''import\s+{re.escape(name)}\s+from\s*['"]([^'"]+)['"]''', text)
        if m and re.search(rf'\bexport\s*\{{[^}}]*\b{re.escape(name)}\b', text):
            return self.js_resolve_spec(trel, m.group(1)) == rel
        return False

    def qualified_model_uses(self, src):
        """`modulo.Modelo` (alias de import de Python/JS/Go) y, en Go, `new(pkg.M)`, `&pkg.M{}`, `[]*pkg.M` dentro de funciones que
        operan sobre la base de datos."""
        fam = B.LANG_FAMILY.get(src.lang, src.lang)
        names = {short for (f, short) in self.models if f == fam}
        if not names or src.lang not in ('py', 'js', 'go', 'rb', 'php', 'java', 'kt', 'cs') or self.generated(src.rel):
            return []
        cache = self.qual_rx
        rx = cache.get(fam)
        if rx is None:
            rx = cache[fam] = re.compile(r'(?<![\w$.])([a-z_$][\w$]*)\s*\.\s*(' + '|'.join(sorted(map(re.escape, names), key=len, reverse=True))
                                         + r')\b(?!\s*[:=](?!=))')
        out, code = [], src.code
        aliases = None
        for m in rx.finditer(code):
            qual, name = m.group(1), m.group(2)
            if qual in ('this', 'self', 'super', 'cls'):
                continue
            if aliases is None:
                aliases = self.module_aliases(src)
            if qual not in aliases:
                continue
            after = code[m.end():m.end() + 3].lstrip()
            before = code[max(0, m.start() - 8):m.start()]
            line_start = code.rfind('\n', 0, m.start()) + 1
            if B.IMPORT_LINE.match(code[line_start:m.start()]):
                continue
            if src.lang == 'go':
                if not (re.search(r'(?:\bnew\(\s*|&|\[\]\*?|\*)$', before) or after[:1] == '{'):
                    continue
                if not self.db_scope(src, m.start()):
                    continue
            elif not (after[:1] in '.(' or after[:1] in ',)' and B.PY_DB_CALL.search(code[max(0, m.start() - 60):m.start()])):
                continue
            out += [(src.line(m.start()), t) for t in self.model_targets(fam, name, src.rel)]
        return out

    def module_aliases(self, src):
        code = src.code
        if src.lang == 'py':
            found = set(re.findall(r'^[ \t]*from\s+[\w.]+\s+import\s+([^\n(]+)', code, re.M))
            names = {p.strip().split(' as ')[-1].strip() for line in found for p in line.split(',')}
            names |= {(m.group(2) or m.group(1).rsplit('.', 1)[-1]) for m in B.PY_IMPORT_AS.finditer(code)}
            return names
        if src.lang == 'js':
            return set(self.js_import_map(src))
        if src.lang == 'go':
            out = set()
            for m in re.finditer(r'(?:^|\n)\s*(?:import\s+)?(\w+\s+)?"([\w.\-/]+)"', code):
                out.add((m.group(1) or '').strip() or m.group(2).rsplit('/', 1)[-1])
            return out
        return set()

    def db_scope(self, src, pos):
        own = self.owner(src.rel, src.line(pos))
        meta = self.g.nodes.get(own) or {}
        if meta.get('kind') in ('function', 'method') and meta.get('line'):
            lines = src.code.split('\n', (meta.get('end') or meta['line']) + 1)
            body = '\n'.join(lines[meta['line'] - 1:meta.get('end') or meta['line']])
        elif meta.get('kind') == 'class':
            return False  # firmas de una interfaz o campos de un struct: no operan sobre la base de datos
        else:
            body = src.code
        return bool(DB_OP.search(body))

    # ------------------------------------------------------------------ env: nombres definidos por el propio repo

    def scan_env_blocks(self, rel, lines, mid):
        """Claves MAYÚSCULAS bajo cualquier bloque YAML cuyo nombre contenga `env` (`environment:`, `env:`, anclas
        `x-app-environment: &env` reutilizadas con `<<: *env`)."""
        if self.is_test(rel) or not mid:
            return
        stack = []
        for i, line in enumerate(lines):
            body = line.strip()
            if not body or body.startswith('#'):
                continue
            ind = len(line) - len(line.lstrip())
            while stack and stack[-1][0] >= ind:
                stack.pop()
            key = re.match(r'''^(?:-\s+)?["']?([\w.\-]+)["']?\s*:(?:\s|$)''', body)
            var = re.match(r'''^(?:-\s+)?["']?([A-Z][A-Z0-9_]{2,})["']?\s*(?::(?:\s|$)|=)|^-\s+["']?([A-Z][A-Z0-9_]{2,})["']?\s*$''', body)
            if var and var.group(2) and not (stack and stack[-1][1] == 'environment'):
                var = None  # `- NOMBRE` sin valor sólo es una variable en la lista `environment:` (paso desde el host en compose)
            if var and any(ENV_BLOCK.search(k) for _, k in stack):
                self.env_defs.append((rel, i + 1, var.group(1) or var.group(2), mid))
            if key:
                stack.append((ind, key.group(1)))

    def config_objects(self, src):
        """Módulos de entorno (`environment.ts`, `config/env.js`...) que exportan un objeto literal: sus claves se definen ahí y
        `alias.clave` en los módulos que lo importan es una lectura."""
        stem = B.os.path.splitext(src.rel.rsplit('/', 1)[-1])[0]
        mid = self.module(src.rel)
        if ENV_MODULE.match(stem) and mid:
            for m in re.finditer(r'\bexport\s+(?:const|let|var)\s+\w+\s*(?::[^=]+)?=\s*\{|\bexport\s+default\s*\{|module\.exports\s*=\s*\{',
                                 src.struct):
                args, _ = src.args(m.end() - 1)
                for a, b in args:
                    k = re.match(r'''\s*['"]?([A-Za-z_][\w]*)['"]?\s*:''', src.code[a:b])
                    if k:
                        self.env_defs.append((src.rel, src.line(a + k.start(1)), k.group(1), mid))
        for alias, (spec, name) in self.js_import_map(src).items():
            tail = (spec or '').rstrip('/').rsplit('/', 1)[-1]
            if not ENV_MODULE.match(B.os.path.splitext(tail)[0]) or not spec.startswith(('.', '@', '~')):
                continue
            for m in re.finditer(rf'(?<![\w$.]){re.escape(alias)}\s*\.\s*([A-Za-z_]\w*)\b(?!\s*\()', src.code):
                self.soft_env_uses.append((src.rel, src.line(m.start()), m.group(1)))

    def finish_flag_env(self):
        """Opciones declaradas con su nombre y su variable de entorno en el mismo literal (`{Name: "open", EnvVars("X_OPEN")}`):
        las lecturas por nombre (`c.Bool("open")`) leen esa variable."""
        for rel, line, key in self.flag_reads:
            for var in sorted(self.flag_binds.get(key, ())):
                self.soft_env_uses.append((rel, line, var))

    def scan_config_env(self, rel):
        """Scripts de shell, `.conf` y plantillas: `$X`/`${X}`/`%(ENV_X)s` son lecturas; `export X=`/`X=` son definiciones."""
        mid = self.module(rel)
        text = self.text(rel) if mid and not self.is_test(rel) else None
        if not text or len(text) > 256 * 1024:
            return
        for i, line in enumerate(text.split('\n')):
            stripped = line.lstrip()
            if stripped.startswith('#') and not stripped.startswith('#!'):
                continue
            d = re.match(r'^\s*(?:export\s+)?([A-Z][A-Z0-9_]{2,})=', line)
            if d and not rel.endswith('.conf'):
                self.env_defs.append((rel, i + 1, d.group(1), mid))
            for m in re.finditer(r'\$\{?([A-Z][A-Z0-9_]{2,})\b|%\(ENV_([A-Z][A-Z0-9_]{2,})\)s', line):
                if d and m.start() < d.end():
                    continue
                self.soft_env_uses.append((rel, i + 1, m.group(1) or m.group(2)))

    def scan_env_names(self, src):
        """Cualquier NOMBRE_EN_MAYÚSCULAS leído en código (literal exacto, `.NOMBRE`, clave `NOMBRE:`) que el repo define como
        variable de entorno (.env*, compose, k8s, Dockerfile...): lectura blanda, se confirma en `finish_env`."""
        if self.is_test(src.rel) or src.lang not in REG_LANGS:
            return
        code, text = src.code, src.text
        if '_' not in code:
            return
        for m in ENV_QUOTED.finditer(text):
            if m.start() in src.ends and len(m.group(2)) >= 3:
                self.soft_env_uses.append((src.rel, src.line(m.start()), m.group(2)))
        if 'Name' in code or 'name' in code:
            for m in FLAG_DECL.finditer(src.struct):
                body = code[m.start():m.end()]
                name = re.search(r'''\b[Nn]ame\s*[:=]\s*["']([\w.\-]+)["']''', body)
                if name:
                    for var in re.findall(r'''["']([A-Z][A-Z0-9_]{2,})["']''', body):
                        self.flag_binds[name.group(1)].add(var)
        if '("' in code or "('" in code:
            for m in FLAG_READ.finditer(code):
                self.flag_reads.append((src.rel, src.line(m.start()), m.group(1)))
        if src.lang == 'js':
            self.config_objects(src)
        for m in ENV_TOKEN.finditer(code):
            s, e = m.span()
            if e - s < 3 or not word_start(code, s) or e < len(code) and (code[e].isalnum() or code[e] in '_$'):
                continue
            i = s - 1
            while i >= 0 and code[i] in ' \t':
                i -= 1
            j = e
            while j < len(code) and code[j] in ' \t':
                j += 1
            member = i >= 0 and code[i] == '.' and not (i > 0 and code[i - 1] == '.') and code[j:j + 1] != '('
            key = code[j:j + 1] == ':' and code[j + 1:j + 2] != ':' and (i < 0 or code[i] in '\n{,(')
            if not (member or key):
                continue
            self.soft_env_uses.append((src.rel, src.line(s), m.group()))

    # ------------------------------------------------------------------ contratos: interfaces con rutas anotadas

    def finish_contracts(self):
        """Rutas anotadas en una interfaz/contrato: las sirven las clases que la implementan (con su prefijo de clase) y las
        consumen las interfaces cliente que la extienden (con el prefijo de su anotación de cliente)."""
        impls, routes, clients = self.impls, self.class_routes, self.client_ifaces
        if not impls and not clients:
            return
        contract = {}

        def split(fn):
            meta = self.g.nodes.get(fn) or {}
            if meta.get('kind') != 'method' or '.' not in meta.get('name', ''):
                return None, None
            cls, name = meta['name'].rsplit('.', 1)
            return cls.rsplit('.', 1)[-1], name

        def servers(cls, name):
            out = []
            for c in sorted(impls.get(cls, ())):
                if c in clients or c not in routes:
                    continue
                m = [n for n in self.owners.get(c, []) if self.g.nodes[n]['name'].rsplit('.', 1)[-1] == name]
                if m:
                    out.append((routes.get(c, ''), m[0]))
            return out

        nest = []
        for rel, line, verbs, full, fn, version in self.nest:
            cls, name = split(fn)
            impl = servers(cls, name) if cls else []
            if cls:
                contract.setdefault(cls, []).append((verbs, full, name))
            if not impl:
                nest.append((rel, line, verbs, full, fn, version))
            for prefix, m in impl:
                nest.append((rel, line, verbs, '/' + '/'.join(x.strip('/') for x in (prefix, full) if x.strip('/')), m, version))
        self.nest = nest
        pending = []
        for item in self.pending:
            rel, line, recv, verbs, tpl, handler, scope, sym = item
            cls, name = split(handler)
            impl = servers(cls, name) if cls else []
            if cls:
                contract.setdefault(cls, []).append((verbs, tpl, name))
            if not impl:
                pending.append(item)
            for prefix, m in impl:
                pending.append((rel, line, recv, verbs, '/'.join(x.strip('/') for x in (prefix, tpl) if x.strip('/')), m, scope, sym))
        self.pending = pending
        wanted = {}
        for ci, (prefix, bases) in clients.items():
            calls = {}
            for base in bases:
                for verbs, path, name in contract.get(base, []):
                    calls.setdefault(name, (verbs, '/' + '/'.join(x.strip('/') for x in (prefix, path) if x.strip('/'))))
            if calls:
                wanted[ci] = calls
        if not wanted:
            return
        names = '|'.join(sorted(map(re.escape, wanted), key=len, reverse=True))
        decl = re.compile(rf'\b({names})\b(?:<[^<>;]*>)?\s+(\w+)\s*[;,)=]|\b(\w+)\s*:\s*({names})\b')
        for rel in self.files:
            if B.EXT_LANG.get(B.os.path.splitext(rel)[1]) not in ('java', 'kt', 'cs', 'js', 'c') or self.is_test(rel):
                continue
            text = self.text(rel)
            if not text or not re.search(rf'\b(?:{names})\b', text):
                continue
            for m in decl.finditer(text):
                ci, var = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
                calls = wanted[ci]
                for call in re.finditer(rf'(?<![\w$])(?:this\.)?{re.escape(var)}\s*\??\.\s*(\w+)\s*\(', text):
                    if call.group(1) not in calls:
                        continue
                    verbs, path = calls[call.group(1)]
                    line = text.count('\n', 0, call.start()) + 1
                    sym = self.owner(rel, line)
                    if sym:
                        for verb in verbs:
                            self.clients.append((rel, line, verb, B.norm_path(path), sym))

    def finish_service_ids(self, hosts):
        """Identificadores de servicio en anotaciones/llamadas cliente (`@Client(id = "x")`, `@FeignClient(name = "x")`) iguales al
        nombre de aplicación que declara otro proyecto del repo."""
        named = {host for host, rel, line in self.svc_names}
        for rel, line, value in sorted(set(self.svc_ids)):
            if value in named:
                sym = self.decl_node(rel, line)
                targets = [nid for k, nid in hosts.get(value, []) if k == 'app' and self.g.nodes[nid]['file'].split('/')[0] != rel.split('/')[0]]
                if sym and len(set(targets)) == 1:
                    self.g.edge(sym, targets[0], 'depends')

    def decl_node(self, rel, line):
        """Nodo de la declaración anotada: si la línea es una anotación (`@X`, `[X]`), el nodo que empieza justo después."""
        text = self.text(rel) or ''
        lines = text.split('\n')
        if 0 < line <= len(lines) and lines[line - 1].lstrip().startswith(('@', '[', '#[')):
            after = [n for s, e, n in self.by_file.get(rel, []) if line <= s <= line + 6]
            if after:
                return min(after, key=lambda n: (self.g.nodes[n].get('line') or 0, n))
        return self.owner(rel, line)

    def scan_compose_builds(self, rel, lines):
        """`build: ./dir` (o `context:`/`dockerfile:`) de un servicio compose -> Dockerfile de esa carpeta."""
        if self.is_test(rel) or not (rel.rsplit('/', 1)[-1].startswith(('docker-compose', 'compose.')) or rel in self.compose_files):
            return
        base = rel.rsplit('/', 1)[0] if '/' in rel else ''
        scripts = set()
        for i, line in enumerate(lines):
            m = re.match(r'^(\s*)build:\s*["\']?([^\s"\'#]*)', line)
            if not m:
                continue
            ctx, dockerfile = m.group(2), None
            if not ctx:
                for j in range(i + 1, min(len(lines), i + 8)):
                    sub = re.match(r'^(\s*)(context|dockerfile):\s*["\']?([^\s"\'#]+)', lines[j])
                    if not sub or len(sub.group(1)) <= len(m.group(1)):
                        if lines[j].strip() and len(lines[j]) - len(lines[j].lstrip()) <= len(m.group(1)):
                            break
                        continue
                    if sub.group(2) == 'context':
                        ctx = sub.group(3)
                    else:
                        dockerfile = sub.group(3)
            folder = B.os.path.normpath(B.os.path.join(base, ctx or '.')).replace(B.os.sep, '/')
            folder = '' if folder in ('.', '') else folder
            target = '/'.join(x for x in (folder, dockerfile or 'Dockerfile') if x)
            mid, sym = self.module(target), self.owner(rel, i + 1)
            if mid and sym and sym != self.module(rel):
                self.g.edge(sym, mid, 'depends')
            entry = re.search(r'''^\s*ENTRYPOINT\s+\[?\s*["']?([^\s"',\]]+)''', self.text(target) or '', re.M) if mid else None
            if entry:
                scripts.add(entry.group(1))
        for i, line in enumerate(lines):
            m = re.match(r'^\s*entrypoint:\s*\[?\s*["\']?([^\s"\',\]]+)', line)
            if m:
                scripts.add(m.group(1))
        found = set()
        for path in scripts:
            tail = path.lstrip('./')
            found.update(f for f in self.fileset if ('/' + tail).endswith('/' + f) or f.endswith('/' + tail.split('/', 1)[-1]) and '/' in tail)
        for script in sorted(found):
            text, mid = self.text(script) or '', self.module(script)
            if not mid or len(text) > 200000:
                continue
            for i, line in enumerate(lines):
                m = re.match(r'''^\s*command:\s*\[?\s*["']?([\w.:-]+)''', line)
                if m and re.search(rf'^\s*(?:{re.escape(m.group(1))}\s*\)|(?:function\s+)?{re.escape(m.group(1))}\s*\(\s*\))', text, re.M):
                    sym = self.owner(rel, i + 1)
                    if sym and sym != self.module(rel):
                        self.g.edge(sym, mid, 'depends')

    def finish_event_wrappers(self):
        """Métodos de una interfaz productora (sin cuerpo) unidos a un topic: sus llamantes tipados también publican."""
        wrappers = {}
        for a, b, kind in sorted(self.g.edges):
            if kind != 'event' or not b.startswith('t:'):
                continue
            meta = self.g.nodes.get(a) or {}
            if meta.get('kind') != 'method' or '.' not in meta.get('name', ''):
                continue
            cls = meta['name'].rsplit('.', 1)[0].rsplit('.', 1)[-1]
            text = self.text(meta['file']) or ''
            if re.search(rf'\binterface\s+{re.escape(cls)}\b', text):
                wrappers.setdefault(a, b)
        if wrappers:
            self.typed_receivers(wrappers, 'event')
        producers = {}
        for a, b, kind in self.g.edges:
            meta = self.g.nodes.get(a) or {}
            if kind == 'event' and b.startswith('t:') and meta.get('kind') in ('function', 'method') \
                    and PRODUCER_NAME.search(meta['name'].rsplit('.', 1)[-1]):
                producers.setdefault(a, set()).add(b)
        if producers:
            for a, b, kind in sorted(self.g.edges):
                if kind == 'call' and b in producers and a != b and not self.is_test(self.g.nodes[a].get('file') or ''):
                    for topic in sorted(producers[b]):
                        self.g.edge(a, topic, 'event')

    # ------------------------------------------------------------------ clientes: URLs alternativas (ternarios, reasignaciones)

    def url_alternatives(self, src, a, b, depth=0, env=None):
        """Valores posibles de una URL además del principal: ramas de un ternario, el cuerpo ternario de una función local
        (`saveOrCreateUrl = (d) => d.id ? "a/" + d.id : "a"`) y las asignaciones previas de la misma variable en la función."""
        s = src.struct
        start = src.skip(a)
        text = s[start:b].rstrip()
        out = []
        if text.startswith('`') and '?' in src.code[start:b]:
            return self.template_ternaries(src, start, b, env)
        if text.startswith('(') and src.close(start) == start + len(text) - 1 and depth < 3:
            return self.url_alternatives(src, start + 1, start + len(text) - 1, depth + 1, env)
        tern = self.ternary(src, start, start + len(text))
        if tern:
            for x, y in tern:
                v = src.expr(x, 0, env)
                if v is not None:
                    out.append(v)
                elif depth < 2:
                    out += self.url_alternatives(src, x, y, depth + 1, env)
            return out
        if depth > 1:
            return out
        call = re.fullmatch(r'([A-Za-z_$][\w$]*)\s*\([^()]*\)', text)
        if call:
            for m in re.finditer(rf'(?<![\w$.]){re.escape(call.group(1))}\s*=\s*(?:async\s*)?\([^()]*\)\s*=>\s*|'
                                 rf'\bfunction\s+{re.escape(call.group(1))}\s*\([^()]*\)\s*\{{\s*return\s+', s):
                body = src.skip(m.end())
                end = src.close(body) if s[body:body + 1] == '(' else -1
                if end > 0:
                    out += self.url_alternatives(src, body + 1, end, depth + 1, env)
                else:
                    stop = re.search(r'[;\n]', s[body:body + 600])
                    out += self.url_alternatives(src, body, body + (stop.start() if stop else 0), depth + 1, env)
            return out
        if re.fullmatch(r'[A-Za-z_$][\w$]*', text):
            fn = self.function_at(src, start)
            meta = self.g.nodes.get(fn) or {}
            lo = src.nl[meta['line'] - 2] if meta.get('line', 0) > 1 and meta['line'] - 2 < len(src.nl) else 0
            for m in re.finditer(rf'(?<![\w$.]){re.escape(text)}\s*(?::[^=;\n]+)?=(?![=>])', s[lo:start]):
                v = src.expr(lo + m.end(), 0, env)
                if v is not None:
                    out.append(v)
                stop = re.search(r'[;\n]', s[lo + m.end():lo + m.end() + 400])
                if stop and depth < 2:
                    out += self.url_alternatives(src, lo + m.end(), lo + m.end() + stop.start(), depth + 1, env)
        return out

    def ternary(self, src, a, b):
        s, depth, q = src.struct, 0, None
        for i in range(a, b):
            ch = s[i]
            if ch in '([{':
                depth += 1
            elif ch in ')]}':
                depth -= 1
            elif depth == 0 and ch == '?' and q is None and s[i + 1:i + 2] not in ('.', '?') and s[i - 1:i] != '?':
                q = i
            elif depth == 0 and ch == ':' and q is not None:
                return [(q + 1, i), (i + 1, b)]
        return None

    # ------------------------------------------------------------------ RPC por nombre: cadenas `x.router.proc(...)`

    def finish_rpc_chains(self):
        """Procedimientos declarados en routers RPC (tRPC: `router({tags: tagsRouter})` + `procedure.query()`) llamados por su
        nombre cualificado: `caller.tags.list()`, `api.tags.list.queryOptions()`, `trpc.tags.list.useQuery()`."""
        named = {name: (rel, entries) for name, rel, entries in self.trpc_routers if name}
        refs = {v for _, _, entries in self.trpc_routers for _, kind, v, _ in entries if kind == 'ref'}
        procs = {}

        def walk(rel, entries, prefix, depth):
            for key, kind, value, line in entries:
                if kind == 'proc':
                    procs[tuple(prefix + [key])] = f'e:{rel}:{value} /trpc/' + '/'.join(prefix + [key])
                elif value in named and depth < 6:
                    walk(*named[value], prefix + [key], depth + 1)

        for name, rel, entries in self.trpc_routers:
            if name not in refs:
                walk(rel, entries, [], 0)
        procs = {k: v for k, v in procs.items() if v in self.g.nodes and len(k) >= 2}
        self.rpc_eps = set(procs.values())
        if not procs:
            return
        chains = []
        quick = re.compile(r'\.\s*(%s)\b' % '|'.join(sorted({re.escape(k[-1]) for k in procs}, key=len, reverse=True)))
        for rel in self.files:
            if B.EXT_LANG.get(B.os.path.splitext(rel)[1]) != 'js' or self.is_test(rel):
                continue
            text = self.text(rel)
            if not text or len(text) > 1024 * 1024 or not quick.search(text):
                continue
            for m in quick.finditer(text):
                tail = re.match(r'\s*(?:\??\.\s*[A-Za-z_$][\w$]*\s*)?(?:<[^<>()]*>)?\s*\(', text[m.end():m.end() + 120])
                head = RPC_CHAIN_BACK.search(text, max(0, m.start() - 200), m.start())
                if not tail or not head:
                    continue
                segs = re.split(r'\s*\??\.\s*', head.group(1)) + [m.group(1)]
                more = re.match(r'\s*\??\.\s*([A-Za-z_$][\w$]*)', text[m.end():m.end() + 120])
                if more and more.group(1) not in RPC_INVOKE:
                    continue  # pathFilter()/queryKey()/getQueryData(): referencia a la caché, no una llamada
                if more:
                    segs.append(more.group(1))
                chains.append((rel, text.count('\n', 0, m.start()) + 1, tuple(segs[-6:])))
        for rel, line, segs in sorted(set(chains)):
            for cut in (0, 1):
                cand = segs[:len(segs) - cut] if cut else segs
                hits = [p for p in procs if len(cand) > len(p) and cand[-len(p):] == p]
                if hits:
                    best = max(hits, key=len)
                    if sum(1 for h in hits if len(h) == len(best)) == 1:
                        sym = self.owner(rel, line)
                        if sym and not self.is_test(rel):
                            self.g.edge(sym, procs[best], 'rpc')
                    break

    def finish_table_links(self):
        """Tablas declaradas en código (DSL de esquema) <-> `CREATE TABLE` homónimo de las migraciones SQL del mismo proyecto."""
        sql = {}
        for key, nids in self.tables.items():
            for n in nids:
                if (self.g.nodes[n].get('file') or '').endswith('.sql'):
                    sql.setdefault(key, []).append(n)
        for nid in sorted(self.table_decls):
            meta = self.g.nodes[nid]
            if meta['file'].endswith('.sql'):
                continue
            found = [t for t in sql.get(str(meta.get('table') or meta['name']).lower(), []) if self.same_project(meta['file'], self.g.nodes[t]['file'])]
            for t in sorted(found)[:3]:
                self.g.edge(nid, t, 'data')

    # ------------------------------------------------------------------ cableado de manifiestos (k8s/kustomize)

    def finish_manifest_refs(self):
        """Referencias entre recursos declarados en manifiestos: lista de ficheros (`resources:`), nombres referenciados
        (`claimName`, `serviceName`, `service: name`, `secretRef/configMapRef: name`) y selectores de etiquetas Service -> workload."""
        docs, by_name = [], {}
        for rel in self.files:
            if not rel.endswith(('.yml', '.yaml')) or self.is_test(rel) or self.world(rel) == 'compose':
                continue
            items = [n for _, _, n in self.by_file.get(rel, []) if self.g.nodes[n]['kind'] == 'class' and '/' in self.g.nodes[n]['name']]
            text = self.text(rel) or ''
            if 'resources:' in text and re.search(r'^kind:\s*Kustomization', text, re.M):
                self.kustomize(rel, text)
            if not items:
                continue
            lines = text.split('\n')
            for nid in items:
                meta = self.g.nodes[nid]
                kind, name = meta['name'].split('/', 1)
                body = lines[(meta.get('line') or 1) - 1:meta.get('end') or len(lines)]
                docs.append((nid, kind, name, meta.get('line') or 1, body))
                by_name.setdefault((B.os.path.dirname(rel), name), []).append((kind, nid))
        by_dir = {}
        for doc in docs:
            by_dir.setdefault(B.os.path.dirname(self.g.nodes[doc[0]]['file']), []).append(doc)
        labels = {}
        for nid, kind, name, start, body in docs:
            if kind not in ('Service', 'Ingress') and 'labels:' in '\n'.join(body):
                labels[nid] = self.yaml_map(body, ('spec', 'template', 'metadata', 'labels')) or self.yaml_map(body, ('metadata', 'labels'))
        for nid, kind, name, start, body in docs:
            folder = B.os.path.dirname(self.g.nodes[nid]['file'])
            sel = self.yaml_map(body, ('spec', 'selector')) if kind == 'Service' else None
            if sel:
                line = start + next((i for i, x in enumerate(body) if re.match(r'^\s*selector:', x)), 0)
                for oid, okind, oname, ostart, obody in by_dir.get(folder, []):
                    found = labels.get(oid)
                    if oid != nid and found and all(found.get(k) == v for k, v in sel.items()):
                        self.g.edge(self.owner(self.g.nodes[nid]['file'], line) or nid, oid, 'depends')
            for i, x in enumerate(body):
                m = MANIFEST_REF.match(x)
                if not m:
                    continue
                key, value = m.group(1), m.group(2)
                want = MANIFEST_KINDS.get(key)
                if key == 'name':
                    parent = next((re.match(r'^\s*-?\s*(\w+):\s*$', body[j]).group(1) for j in range(i - 1, max(-1, i - 3), -1)
                                   if re.match(r'^\s*-?\s*(\w+):\s*$', body[j])), None)
                    want = MANIFEST_KINDS.get(parent)
                if not want:
                    continue
                for okind, oid in by_name.get((folder, value), []):
                    if okind in want and oid != nid:
                        self.g.edge(nid, oid, 'depends')

    def yaml_map(self, body, path):
        depth, ind, out = 0, -1, {}
        for x in body:
            if not x.strip() or x.lstrip().startswith('#'):
                continue
            cur = len(x) - len(x.lstrip())
            if depth == len(path):
                if cur <= ind:
                    break
                m = re.match(r'''^\s*["']?([\w./-]+)["']?:\s*["']?([^"'#\s]+)''', x)
                if m:
                    out[m.group(1)] = m.group(2)
                continue
            if cur <= ind:
                return {}
            if re.match(rf'^\s*{re.escape(path[depth])}:\s*$', x):
                depth, ind = depth + 1, cur
        return out

    def kustomize(self, rel, text):
        mid = self.module(rel)
        base = rel.rsplit('/', 1)[0] if '/' in rel else ''
        block = None
        for i, line in enumerate(text.split('\n')):
            if re.match(r'^(?:resources|bases|components):\s*$', line):
                block = True
                continue
            if block and line.strip() and not line.startswith((' ', '-')):
                block = None
            m = re.match(r'^\s*-\s*["\']?([\w./-]+\.ya?ml)["\']?\s*$', line) if block else None
            if not m or not mid:
                continue
            target = B.os.path.normpath('/'.join(x for x in (base, m.group(1)) if x)).replace(B.os.sep, '/')
            nodes = [n for _, _, n in self.by_file.get(target, []) if self.g.nodes[n]['kind'] == 'class']
            dest = nodes[0] if len(nodes) == 1 else self.module(target)
            sym = self.owner(rel, i + 1)
            if dest and sym:
                self.g.edge(sym, dest, 'depends')

    def finish_model_relations(self):
        """Relaciones entre modelos declarados: campos tipados con otro modelo (`Set<PolicyVersion> versions`) y herencia entre
        modelos (`class InPayment extends AccountingEntry`), en lenguajes con tipos (Java/Kotlin/C#/TS)."""
        fams = {}
        for (fam, short), nids in self.models.items():
            if fam in ('java', 'kt', 'cs', 'js'):
                fams.setdefault(fam, {})[short] = nids
        for fam, names in fams.items():
            if len(names) < 2:
                continue
            rx = re.compile(r'(?<![\w$.])(' + '|'.join(sorted(map(re.escape, names), key=len, reverse=True)) + r')\b')
            for short, nids in sorted(names.items()):
                for nid in nids:
                    meta = self.g.nodes[nid]
                    if self.is_test(meta['file']):
                        continue
                    lines = (self.text(meta['file']) or '').split('\n')[(meta.get('line') or 1) - 1:meta.get('end') or meta.get('line') or 1]
                    head = ' '.join(lines[:6])
                    base = re.search(rf'\b(?:class|record)\s+{re.escape(short)}\b[^{{]*?(?:\bextends\b|:)\s*([\w.]+)', head)
                    found = {base.group(1).rsplit('.', 1)[-1]} if base else set()
                    for line in lines[1:]:
                        if MODEL_FIELD.match(line):
                            found.update(m.group(1) for m in rx.finditer(line))
                    for other in sorted(found - {short}):
                        for target in self.model_targets(fam, other, meta['file']):
                            if target != nid and self.same_project(meta['file'], self.g.nodes[target]['file']):
                                self.g.edge(nid, target, 'data')
