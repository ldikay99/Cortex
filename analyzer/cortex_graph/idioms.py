"""Idiomas transversales de flujos (ronda 5 del benchmark de flujos, `bench/flows`).

Mixins de `bridges.Bridges`, como `structural.Structural`. Cada regla describe una forma de código o de configuración común a muchos
frameworks, no una librería concreta (la matriz y los casos de prueba están en `bench/flows/FRAMEWORKS.md`, sección «Ronda 5», y en
`analyzer/tests/test_bridges_idioms.py`):

- Datos: constructores de consultas con el nombre literal de una tabla declarada (`selectFrom('t')`, `insertInto`, `.from('t')`,
  `collection('t')`...); tablas por macro (`table! { t (id) {..} }`) y modelos que nombran su tabla en un atributo o anotación
  (`#[diesel(table_name = t)]`, `@PersistenceCapable(table = "T")`, cualquier anotación con `table=`); herencia de modelos; registro
  en el ORM (`AutoMigrate(new(pkg.T))`); mapas de esquema tipados (`interface DB { comments: Comments }`, también en `.d.ts`); DDL en
  migraciones escritas en código y renombrados por lista de pares.
- Entorno: plantillas (`*.conf.example`, `.env.template`, con líneas comentadas), `- CLAVE` en `environment:` de compose, envoltorios
  cuyo parámetro llega a una lectura de entorno, constantes cuyo valor es una variable o una clave de configuración, y campos de bloques
  de configuración cuyo nombre en mayúsculas define el repo.
- Eventos: señales y observadores (`sig.connect(h)`, `@receiver`, `notifier.OnX(h)` + `sig.send()`), claves cualificadas compartidas
  entre un despacho (`case Q.X:` en la entrada de un consumidor, `@OnJob({name: Q.X})`, `@Processor(Q.X)`) y sus productores, clases de
  trabajo pasadas por referencia (`new XTask()`, `X.class`), tareas por ruta punteada y hubs de notificación en proceso.
- Rutas y clientes: receptores tipados (`var.Metodo` por el tipo de la variable), grupos encadenados y listas de verbos, viewsets e
  `include([...])` anidados, OpenAPI repartido en ficheros, clientes tipo fetch y SDK generados, clientes OpenAPI generados fuera del
  repo, clientes obtenidos de una llamada, navegación, ternarios en plantillas y URLs construidas en una clase base.
- RPC: contratos declarados en un lenguaje (IDL) e implementados en otro (canales de plataforma).
"""
import re
from collections import defaultdict

from .structural import FLOW_GENERIC


class _Lazy:
    def __getattr__(self, name):
        from . import bridges
        value = getattr(bridges, name)
        setattr(self, name, value)
        return value


B = _Lazy()

# ---------------------------------------------------------------- datos
QB_TABLE = re.compile(r'''(?<![\w$])(?:\.\s*|::\s*)?(selectFrom|insertInto|updateTable|deleteFrom|replaceInto|mergeInto|upsertInto|'''
                      r'''from|into|table|withSchema|innerJoin|leftJoin|rightJoin|fullJoin|crossJoin|leftOuterJoin|rightOuterJoin|'''
                      r'''fullOuterJoin|joinRelated|collection|getCollection|Table|From|Into|Collection|InnerJoin|LeftJoin|Joins)'''
                      r'''\s*\(\s*['"`](\w+)['"`]\s*[,)]''')
QB_NOT_RECV = re.compile(r'(?:\b(?:Array|Buffer|Object|Promise|Set|Map|String|Uint8Array|path|os|fs|Path|Stream|Observable|Rx|of|'
                         r'_|lodash|R|Flux|Mono|Stream|Arrays|List|Collections|Optional|Instant|LocalDate|Duration)\s*\.\s*)$')
DIESEL_TABLE = re.compile(r'(?:\bdiesel::)?\btable!\s*\{')
DIESEL_ENTRY = re.compile(r'(?:^|\n)[ \t]*(?:#\[[^\]]*\]\s*)*(?:[\w.]+\s*\.\s*)?(\w+)\s*(?:\([^)]*\))?\s*\{')
RS_TABLE_ATTR = re.compile(r'#\[\s*(?:diesel\s*\(\s*)?table_name\s*=\s*"?([\w.]+)"?\s*\)?\s*\]')
ANN_TABLE = re.compile(r'''@(\w+)\s*\(([^)]*\b(?:table|tableName|table_name)\s*=\s*"(\w+)"[^)]*)\)''')
ANN_BARE_TABLE = re.compile(r'@(?:javax\.jdo\.annotations\.)?PersistenceCapable\b(?!\s*\([^)]*\btable\s*=)')
PY_CLASS = re.compile(r'^[ \t]*class\s+(\w+)\s*\(([^)]*)\)\s*:', re.M)

# ---------------------------------------------------------------- entorno
TEMPLATE_NAME = re.compile(r'(?i)(?:^|[.\-_])(?:example|sample|template|tmpl|dist|defaults?)(?:\.[\w-]+)?$')
TEMPLATE_FILE = re.compile(r'(?i)^[\w.\-]+\.(?:conf|cfg|env|ini|vars|properties)\.(?:example|sample|template|tmpl|dist|defaults?)$')
COMMENTED_DEF = re.compile(r'^\s*#+\s*(?:export\s+)?([A-Z][A-Z0-9_]{2,})\s*=')
ENV_ARG_READ = {
    'go': r'\bos\.(?:Getenv|LookupEnv)\(\s*(\w+)\b',
    'py': r'\bos\.(?:getenv|environ\.get|environ\.setdefault)\(\s*(\w+)\b|\bos\.environ\[\s*(\w+)\s*\]|\bgetenv\(\s*(\w+)\b',
    'js': r'\bprocess\.env\[\s*(\w+)\s*\]|\bDeno\.env\.get\(\s*(\w+)\b',
    'java': r'\bSystem\.getenv\(\s*(\w+)\s*\)',
    'kt': r'\bSystem\.getenv\(\s*(\w+)\s*\)',
    'rb': r'\bENV\[\s*(\w+)\s*\]|\bENV\.fetch\(\s*(\w+)\b',
    'rs': r'\benv::var(?:_os)?\(\s*&?(\w+)\b',
    'cs': r'\bEnvironment\.GetEnvironmentVariable\(\s*(\w+)\b',
    'php': r'\bgetenv\(\s*\$(\w+)\b|\$_ENV\[\s*\$(\w+)\b',
    'ex': r'\bSystem\.(?:get_env|fetch_env!?)\(\s*(\w+)\b',
}
ENV_ARG_READ = {k: re.compile(v) for k, v in ENV_ARG_READ.items()}
ENV_NAME_VALUE = re.compile(r'[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+')
CONFIG_KEY_VALUE = re.compile(r'[a-z][\w\-]*(?:\.[a-z0-9][\w\-]*)+')
CONFIG_FILE = re.compile(r'(?i)(?:config|settings|conf|env|environment|options)[\w.-]*$')
CONFIG_FIELD = re.compile(r'^[ \t]*(?:(?:pub(?:\([^)]*\))?|public|private|readonly|val|var|let|const|final)\s+)*([a-z][a-z0-9]*(?:_[a-z0-9]+)+)'
                          r'\s*(?:[:=]|,\s*\w)', re.M)

# ---------------------------------------------------------------- eventos
SIGNAL_CONNECT = re.compile(r'(?<![\w$.])([A-Za-z_]\w*)\s*\.\s*(connect|connect_via|On[A-Z]\w*)\s*\(')
SIGNAL_FIRE = re.compile(r'(?<![\w$.])([A-Za-z_]\w*)\s*\.\s*(send|send_robust|send_async|emit|fire|dispatch|trigger)\s*\(')
SIGNAL_DECL = re.compile(r'^[ \t]*([A-Za-z_]\w*)\s*(?::\s*[\w.\[\]]+\s*)?=\s*(?:[\w.]+\.)?(?:Signal|signal|ModelSignal|AsyncSignal)\s*\(', re.M)
RECEIVER_DECOR = re.compile(r'^[ \t]*@(?:[\w.]+\.)?receiver\(\s*\[?\s*((?:[\w.]+\s*,\s*)*[\w.]+)', re.M)
NOTIFIER_NAME = re.compile(r'(?i)notif|observ|emitter|events?$|bus$|hub$|signal|publisher|dispatcher|broker|listeners?$|watcher')
QKEY = r'([A-Z]\w*)\s*\.\s*([A-Za-z_]\w*)'
QKEY_CASE = re.compile(r'\bcase\s+' + QKEY + r'\s*(?::|=>|\{)|\b\w+\s*\.\s*(?:name|type|kind|event|job|topic|jobName|eventName)\s*[!=]==?\s*'
                       + QKEY + r'|^[ \t]*' + QKEY + r'\s*->', re.M)
QKEY_OBJ = re.compile(r'(?<![\w$])(?:name|event|job|topic|queue|channel|jobName|eventName|task)\s*:\s*' + QKEY + r'\b(?!\s*[.(])')
QKEY_ARG = re.compile(r'(?<![\w$])(add|addBulk|queue|queueAll|enqueue|send|emit|emitAsync|publish|dispatch|push|trigger|schedule|fire|'
                      r'notify|post|put|produce|submit|runJob|addJob)\s*(?:<[^<>()]*>)?\s*\(\s*' + QKEY + r'\s*[,)]')
JOB_CLASS_REF = re.compile(r'(?<![\w$.])(?:new\s+([A-Z]\w*)\s*(?:<[^<>()]*>)?\s*\(|([A-Z]\w*)\s*(?:\.class|::class(?:\.java)?)\b|'
                           r'typeof\s*\(\s*([A-Z]\w*)\s*\))')
JOB_CLASS_NAME = re.compile(r'(?:Task|Job|Workflow|Activity|Worker)$')
CHAINED_GROUP = re.compile(r'\b(\w+)\s*\.\s*Group\(\s*"([^"]*)"[^()]*\)(?:\s*\.\s*Use\((?:[^()]|\([^()]*\))*\))*\s*\.\s*'
                           r'(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD|Any|Get|Post|Put|Patch|Delete)\s*\(')
FETCH_LIKE = re.compile(r'(?<![\w$])(?:[A-Za-z_$][\w$]*\s*\.\s*)?((?:fetch|request|http)[A-Z_]\w*|fetch|request)\s*'
                        r'(?:<(?:[^<>]|<(?:[^<>]|<[^<>]*>)*>)*>)?\s*\(')
CALLED_CLIENT = re.compile(r'(?<![\w$.])([A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)*)\s*\([^()]*\)\s*\.\s*(get|post|put|patch|delete|head)\s*'
                           r'(?:<(?:[^<>]|<[^<>]*>)*>)?\s*\(')
NAVIGATION = re.compile(r'\b(?:window\.)?location(?:\.href)?\s*=(?!=)\s*|\b(?:window\.open|location\.assign|location\.replace)\s*\(')
ORM_REGISTER = re.compile(r'\.\s*(?:AutoMigrate|Sync2?|RegisterModel|CreateTable|CreateTables)\s*\(')
ORM_REGISTERED = re.compile(r'\bnew\(\s*(?:(\w+)\.)?([A-Z]\w*)\s*\)|&(?:(\w+)\.)?([A-Z]\w*)\s*\{\s*\}')
TERNARY_SLOT = re.compile(r'''\$\{\s*[^{}?]+\?\s*(['"])([\w\-./]*)\1\s*:\s*\1([\w\-./]*)\1\s*\}''')
NOTIFY_NAME = re.compile(r'^(?:(?:[Ss]end|[Pp]ush|[Ee]mit)(?:_[a-z]\w*|[A-Z]\w*)|(?:[Nn]otify|[Bb]roadcast|[Pp]ublish)(?:_[a-z]\w*|[A-Z]\w*)?)$')
MESSAGING_PLACE = re.compile(r'(?i)push|websocket|socket|broadcast|pubsub|stream|hub$|realtime|bus$')
DEF_HEAD = re.compile(r'\b(?:def|fn|func|function|fun|sub)\s+$|\bfunc\s*\([^)]*\)\s*$|'
                      r'\b(?:public|private|protected|internal|static|async|void|override|virtual|abstract)\s+(?:[\w<>\[\],.?]+\s+)?$')
VIEWSET_ACTIONS = {'list': ('GET', False), 'create': ('POST', False), 'retrieve': ('GET', True), 'update': ('PUT', True),
                   'partial_update': ('PATCH', True), 'destroy': ('DELETE', True)}
VIEWSET_BASES = {'ModelViewSet': set(VIEWSET_ACTIONS), 'ReadOnlyModelViewSet': {'list', 'retrieve'}, 'ListModelMixin': {'list'},
                 'CreateModelMixin': {'create'}, 'RetrieveModelMixin': {'retrieve'}, 'UpdateModelMixin': {'update', 'partial_update'},
                 'DestroyModelMixin': {'destroy'}, 'ListAPIView': {'list'}}
VIEWSET_EXTRA = re.compile(r'^[ \t]*@(?:\w+\.)?action\(((?:[^()]|\([^()]*\))*)\)\s*\n(?:[ \t]*@[^\n]*\n)*[ \t]*(?:async\s+)?def\s+(\w+)', re.M)
CALL_ON_VAR = re.compile(r'(?<![\w$.])([A-Za-z_]\w*)\s*\??\.\s*([a-zA-Z_]\w*)\s*\(')
GLOBAL_INSTANCE = re.compile(r'^(?:final|var|const|val|let|export\s+const)\s+([a-z_]\w*)\s*=\s*(?:new\s+)?([A-Z]\w*)\s*\(', re.M)
KEYED_CLASS = re.compile(r'@\w+\(\s*(?:' + QKEY + r'|[\'"]([\w.:\-]{3,})[\'"])\s*[,)][^\n]*\n(?:\s*@[^\n]*\n)*\s*(?:export\s+)?'
                         r'(?:default\s+)?(?:abstract\s+)?class\s+(\w+)')
KEYED_FIELD = re.compile(r'@\w+\(\s*(?:' + QKEY + r'|[\'"]([\w.:\-]{3,})[\'"])\s*\)\s*(?:(?:private|public|protected|readonly)\s+)*(\w+)\s*[:!?]')
BUILDER_CALL = re.compile(r'\b([\w$]+)\s*\.\s*(get|post|put|patch|delete|head)\s*(?:<(?:[^<>]|<[^<>]*>)*>)?\s*\(\s*(?=this\s*\.\s*\w+\s*\()')
SCHEMA_BLOCK = re.compile(r'^(?:export\s+)?(?:interface\s+\w+(?:\s+extends\s+[\w<>, ]+)?|type\s+\w+\s*=)\s*\{', re.M)
SCHEMA_MEMBER = re.compile(r'^[ \t]+["\']?([A-Za-z_]\w*)["\']?\s*:\s*([A-Z]\w*)\s*;?[ \t]*$', re.M)
RENAME_PAIR = re.compile(r'''\{\s*['"]?old_?[Nn]ame['"]?\s*:\s*['"](\w+)['"]\s*,\s*['"]?new_?[Nn]ame['"]?\s*:\s*['"](\w+)['"]''')
GENERATED_CLIENT_TYPE = re.compile(r'[A-Z]\w*(?:Api|API|Client)$')
OPENAPI_JSON = re.compile(r'(?i)(?:openapi|swagger)[\w.\-]*\.json$')
EXT_FAMILY = {'.kt': 'jvm', '.kts': 'jvm', '.java': 'jvm', '.scala': 'jvm', '.groovy': 'jvm', '.ts': 'js', '.tsx': 'js', '.js': 'js',
              '.jsx': 'js', '.mjs': 'js', '.cjs': 'js', '.mts': 'js', '.vue': 'js', '.svelte': 'js', '.m': 'apple', '.mm': 'apple',
              '.swift': 'apple'}
JOB_ENTRY = {'process', 'handle', 'perform', 'run', 'execute', 'consume', 'onMessage', 'handleMessage', 'handleJob', 'onJob', 'onEvent',
             'processJob', 'work', 'call', 'receive', 'on_message', 'handle_message', '__call__', 'Process', 'Handle', 'Execute', 'Consume'}
PRODUCER_VERB = re.compile(r'^(?:add|queue|enqueue|send|emit|publish|dispatch|push|trigger|schedule|fire|notify|produce|submit|upsert|run|post|'
                           r'put)(?:[A-Z_]\w*)?$', re.I)
ENV_LIKE_NAME = re.compile(r'[A-Z][A-Z0-9_]*[A-Z0-9]')
LOG_CALL = re.compile(r'(?i)^(?:log\w*|print\w*|\w*printf|format|msgf?|warn\w*|error\w*|debug|info|trace|fatal\w*|panic\w*|errorf|'
                      r'sprintf|str|f|t|i18n|translate)$')
QKEY_OBJ_HINT = re.compile(r'\b(?:name|event|job|topic|queue|channel|jobName|eventName|task)\s*:\s*[A-Z]')
FETCH_HINT = re.compile(r'''(?:fetch|request|http)\w*\s*(?:<[\s\S]{0,400}?>)?\s*\(\s*(?:[`'"]/|\{)''')
CALLED_HINT = re.compile(r'\)\s*\.\s*(?:get|post|put|patch|delete|head)\s*[<(]')
QB_HINT = re.compile(r'''(?:From|Into|Table|table|from|into|Join|join|ollection|withSchema)\s*\(\s*['"`]''')
MIGRATION_PATH = re.compile(r'(?i)igration|alteration|/upgrades?/|/changesets?/')
DOTTED_TASK = re.compile(r'''['"]((?:[a-z_][a-z0-9_]*\.){1,6}[a-z_][a-z0-9_]*)['"]''')


class Idioms:
    def idioms_init(self):
        self.py_classes, self.const_sites, self.env_wrappers, self.env_calls = [], defaultdict(list), {}, []
        self.const_refs, self.config_fields = [], []
        self.signal_regs, self.signal_decls, self.signal_fires, self.qkey_subs, self.qkey_pubs = [], set(), [], [], []
        self.dotted_refs, self.job_classes, self.class_bases = [], {}, None
        self.orm_registered, self.qkey_declared, self._const_ref_rx = [], set(), None

    # ------------------------------------------------------------ fase de recogida (antes de `finish_models`)

    def collect_idioms(self, rel, lang, text):
        if self.is_test(rel):
            return
        if lang == 'rs' and 'table' in text:
            self.collect_rust_tables(rel, text)
        if lang in ('java', 'kt', 'cs', 'php', 'js', 'c') and '@' in text and ('table' in text or 'PersistenceCapable' in text):
            self.collect_annotated_tables(rel, lang, text)
        if lang == 'go' and ('AutoMigrate' in text or 'Sync' in text or 'RegisterModel' in text or 'CreateTable' in text):
            self.collect_orm_registrations(rel, lang, text)
        if MIGRATION_PATH.search(rel) and re.search(r'(?i)create\s+table', text):
            # DDL en cadenas de una migración escrita en código (`sql\`CREATE TABLE "partners" (...)\``, `op.execute("CREATE TABLE")`)
            for m in B.SQL_CREATE_TABLE.finditer(text):
                head = text[text.rfind('\n', 0, m.start()) + 1:m.start()].lstrip()
                if not head.startswith(('//', '#', '--', '*', '/*')):
                    self.table_decl(rel, text.count('\n', 0, m.start()) + 1, m.group(2), lang)
        if 'igration' in rel and ('oldName' in text or 'old_name' in text):
            # tablas renombradas en una migración mediante una lista de pares (`{ oldName: 'partners', newName: 'partner' }`)
            for m in RENAME_PAIR.finditer(text):
                self.renames[m.group(2).lower()].add(m.group(1).lower())
        if lang == 'py' and 'class' in text:
            self.py_classes += [(rel, text.count('\n', 0, m.start()) + 1, m.group(1), m.group(2)) for m in PY_CLASS.finditer(text)]
        rx = B.CONST_DECL.get(lang)
        if rx and ('const' in text or 'final' in text or 'static' in text or lang in ('py', 'rb', 'go')):
            for m in rx.finditer(text):
                value = m.group(3)
                if ENV_NAME_VALUE.fullmatch(value) or CONFIG_KEY_VALUE.fullmatch(value):
                    self.const_sites[m.group(1)].append((rel, text.count('\n', 0, m.start(1)) + 1, value))

    def collect_rust_tables(self, rel, text):
        """`table! { t (id) { col -> Type, } }` declara la tabla `t`; `#[diesel(table_name = t)] struct X` es su modelo."""
        for m in DIESEL_TABLE.finditer(text):
            open_pos = m.end() - 1
            depth, i = 0, open_pos
            end = len(text)
            while i < len(text):
                ch = text[i]
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
                i += 1
            body, pos, inner = text[open_pos + 1:end], 0, 0
            while pos < len(body):
                e = DIESEL_ENTRY.match(body, pos)
                if not e:
                    nxt = body.find('\n', pos + 1)
                    if nxt < 0:
                        break
                    pos = nxt
                    continue
                brace = e.end() - 1
                close, d = brace, 0
                for j in range(brace, len(body)):
                    if body[j] == '{':
                        d += 1
                    elif body[j] == '}':
                        d -= 1
                        if d == 0:
                            close = j
                            break
                at = open_pos + 1 + e.start(1)
                line = text.count('\n', 0, at) + 1
                self.table_decl(rel, line, e.group(1), 'rs', end=text.count('\n', 0, open_pos + 1 + close) + 1)
                pos = close + 1
                inner += 1
        for m in RS_TABLE_ATTR.finditer(text):
            st = re.match(r'(?:\s*#\[[^\]]*\])*\s*(?:pub(?:\([^)]*\))?\s+)?struct\s+(\w+)', text[m.end():m.end() + 600])
            if st:
                self.model_at(rel, text.count('\n', 0, m.end() + st.start(1)) + 1, st.group(1), m.group(1).rsplit('.', 1)[-1], 'rs')

    def collect_annotated_tables(self, rel, lang, text):
        """Anotaciones/atributos de clase que nombran la tabla (`table = "X"`, `tableName = "x"`) o la marcan como persistente
        (`@PersistenceCapable`, tabla = nombre de la clase)."""
        for rx, named in ((ANN_TABLE, True), (ANN_BARE_TABLE, False)):
            for m in rx.finditer(text):
                cls = re.search(r'\b(?:class|record|struct)\s+(\w+)', text[m.end():m.end() + 1500])
                if not cls:
                    continue
                between = text[m.end():m.end() + cls.start()]
                for _ in range(6):
                    flat = re.sub(r'\([^()]*\)', '', between)
                    if flat == between:
                        break
                    between = flat
                if '{' in between or ';' in between:
                    continue
                name = cls.group(1)
                table = m.group(3) if named else name
                self.model_at(rel, text.count('\n', 0, m.end() + cls.start(1)) + 1, name, table, lang)

    def prepare_models(self):
        """Herencia de modelos en Python: una clase cuya base es un modelo ya reconocido también lo es (bases abstractas propias)."""
        self.finish_orm_registrations()
        self.schema_maps()
        known = {short for (fam, short) in self.models if fam == 'py'}
        if not known:
            return
        pending = list(self.py_classes)
        for _ in range(4):
            added = False
            rest = []
            for rel, line, name, bases in pending:
                names = {b.strip().split('[')[0].rsplit('.', 1)[-1] for b in bases.split(',') if b.strip() and '=' not in b}
                if name not in known and names & known and name not in ('Meta', 'Config'):
                    self.model_at(rel, line, name, B.snake(name), 'py')
                    known.add(name)
                    added = True
                elif name not in known:
                    rest.append((rel, line, name, bases))
            pending = rest
            if not added:
                break

    # ------------------------------------------------------------ fase de recorrido

    def scan_idioms(self, src):
        if self.is_test(src.rel):
            return
        if src.lang in ('js', 'py', 'java', 'kt', 'c', 'php', 'rb'):
            self.scan_fetch_like(src)
        if src.lang == 'js':
            self.scan_navigation(src)
            self.scan_url_builders(src)
        self.scan_env_wrappers(src)
        self.scan_signals(src)
        self.scan_keyed_dispatch(src)
        self.scan_job_classes(src)
        if src.lang == 'py' and ('task' in src.code or 'job' in src.code):
            for m in DOTTED_TASK.finditer(src.code):
                # sólo como valor de una clave/argumento `task`/`job` (planificadores), no como clave de un diccionario de consulta
                if re.search(r'''(?:['"](?:task|job)['"]\s*:|\b(?:task|job)\s*=)\s*$''', src.code[max(0, m.start() - 30):m.start()]):
                    self.dotted_refs.append((src.rel, src.line(m.start()), m.group(1)))
        if CONFIG_FILE.search(B.os.path.splitext(src.rel.rsplit('/', 1)[-1])[0]):
            for m in CONFIG_FIELD.finditer(src.code):
                enc = self.enclosing(src, m.start(1))
                if enc and enc[2] in '([':
                    continue  # argumento con nombre de una llamada (`update(auth_user=..)`), no un campo declarado
                own = self.g.nodes.get(self.owner(src.rel, src.line(m.start(1)))) or {}
                if own.get('name', '').rsplit('.', 1)[-1] in ('Config', 'Meta', 'model_config'):
                    continue  # opciones del propio modelo de ajustes (`class Config: env_file = ".env"`), no variables
                self.config_fields.append((src.rel, src.line(m.start(1)), m.group(1).upper()))

    def query_builder_uses(self, src):
        """`selectFrom('t')`, `insertInto('t')`, `.from('t')`, `collection('t')`...: literal igual a una tabla declarada."""
        out = []
        if not self.tables:
            return out
        code = src.code
        if not QB_HINT.search(code):
            return out
        for m in QB_TABLE.finditer(code):
            if QB_NOT_RECV.search(code[max(0, m.start(1) - 40):m.start(1)]):
                continue
            for t in self.table_targets(m.group(2), src.rel):
                out.append((src.line(m.start()), t))
        return out

    def scan_env_wrappers(self, src):
        """Funciones cuyo parámetro llega a una lectura de entorno (también en cadena, `parseX(env) => lookup(env)`)."""
        rx = ENV_ARG_READ.get(src.lang)
        if rx is None or not B.ENV_HINT.search(src.text):
            return
        for m in rx.finditer(src.code):
            ident = next((g for g in m.groups() if g), None)
            fn = self.function_at(src, m.start())
            if not ident or not fn:
                continue
            params = self.fn_params(src, fn)
            if ident in params:
                short = self.g.nodes[fn]['name'].rsplit('.', 1)[-1]
                self.env_wrappers.setdefault(short, set()).add((fn, params.index(ident)))

    def scan_const_refs(self, src):
        """Referencias (no declaraciones) a constantes cuyo valor es un nombre de variable o una clave de configuración."""
        sites = self.const_sites
        if not sites:
            return
        rx = self._const_ref_rx
        if rx is None:
            names = sorted(sites, key=len, reverse=True)
            rx = self._const_ref_rx = re.compile(r'(?<![\w$])(?:[A-Za-z_]\w*\s*\.\s*)?(' + '|'.join(map(re.escape, names)) + r')\b(?!\s*[(=:])')
        for m in rx.finditer(src.code):
            line = src.line(m.start())
            name = m.group(1)
            if any(rel == src.rel and ln == line for rel, ln, _ in sites[name]):
                continue
            enc = self.enclosing(src, m.start())
            call = re.search(r'([A-Za-z_]\w*)\s*$', src.struct[max(0, enc[0] - 60):enc[0]]) if enc and enc[2] == '(' else None
            if call and LOG_CALL.search(call.group(1)):
                continue  # el nombre de la variable en un mensaje de log no es una lectura
            values = {v for _, _, v in sites[name]}
            if len(values) == 1:
                self.const_refs.append((src.rel, line, name, values.pop()))

    # ------------------------------------------------------------ cierre

    def finish_const_refs(self):
        """Referencias a constantes cuyo valor es una clave de configuración del repo o una variable de entorno definida."""
        props = {key for _, _, key, _ in self.spring_props}
        defined = {name for _, _, name, _ in self.env_defs}
        wanted = {name for name, sites in self.const_sites.items()
                  if len({v for _, _, v in sites}) == 1 and (sites[0][2] in props or sites[0][2] in defined)}
        if not wanted:
            return
        self.const_sites = {k: v for k, v in self.const_sites.items() if k in wanted}
        self._const_ref_rx = None
        quick = re.compile(r'\b(?:%s)\b' % '|'.join(sorted(map(re.escape, wanted), key=len, reverse=True)))
        for rel in self.files:
            lang = B.EXT_LANG.get(B.os.path.splitext(rel)[1])
            if not lang or self.is_test(rel):
                continue
            text = self.text(rel)
            if text and len(text) < 600 * 1024 and quick.search(text):
                src = self.src(rel, lang, text)
                self.scan_const_refs(src)

    def finish_env_idioms(self):
        """Antes de `finish_env`: llamadas a envoltorios de lectura de entorno, constantes con nombres de variable/clave y campos de
        bloques de configuración."""
        self.propagate_env_wrappers()
        self.finish_const_refs()
        props = {key for _, _, key, _ in self.spring_props}
        for rel, line, name, value in self.const_refs:
            if CONFIG_KEY_VALUE.fullmatch(value) and value in props:
                self.config_reads.append((rel, line, value))
            elif ENV_NAME_VALUE.fullmatch(value):
                self.soft_env_uses.append((rel, line, value))
        env_files = {name for rel, line, name, mid in self.env_defs if not rel.endswith(B.CODE_EXTS)}
        for rel, line, name in self.config_fields:
            if name in env_files:
                self.soft_env_uses.append((rel, line, name))

    def propagate_env_wrappers(self):
        if not self.env_wrappers:
            return
        book = {k: v for k, v in self.env_wrappers.items() if k not in FLOW_GENERIC}
        fresh = set(book)
        for _ in range(4):
            if not fresh:
                break
            names = sorted(fresh)
            fresh = set()
            rx = re.compile(r'(?<![\w$.])(?:[A-Za-z_]\w*\s*\.\s*)?(%s)\s*\(' % '|'.join(map(re.escape, names)))
            for rel in self.files:
                lang = B.EXT_LANG.get(B.os.path.splitext(rel)[1])
                if lang not in ENV_ARG_READ or self.is_test(rel):
                    continue
                text = self.text(rel)
                if not text or len(text) > 600 * 1024 or not rx.search(text):
                    continue
                src = self.src(rel, lang, text)
                src.scope = lambda pos, src=src: self.function_at(src, pos)
                for m in rx.finditer(src.code):
                    head = src.code[max(0, m.start() - 40):m.start()]
                    if re.search(r'\b(?:func|def|fn|function|fun)\s*(?:\([^)]*\)\s*)?$', head):
                        continue
                    wrappers = book.get(m.group(1), set())
                    idx = {i for _, i in wrappers}
                    if len(idx) != 1:
                        continue
                    i = idx.pop()
                    args, _ = src.args(m.end() - 1)
                    if len(args) <= i:
                        continue
                    a, b = args[i]
                    text_arg = src.code[a:b].strip()
                    fn = self.function_at(src, m.start())
                    params = self.fn_params(src, fn) if fn else []
                    if text_arg in params and fn not in {w for w, _ in wrappers}:
                        short = self.g.nodes[fn]['name'].rsplit('.', 1)[-1]
                        if short not in book and short not in FLOW_GENERIC:
                            book.setdefault(short, set()).add((fn, params.index(text_arg)))
                            fresh.add(short)
                        continue
                    value = self.env_name_value(src, a, b)
                    if value:
                        line = src.line(m.start())
                        self.env_uses.append((rel, line, value))
                        ref = re.fullmatch(r'(?:\w+\s*\.\s*)?(\w+)', text_arg)
                        for srel, sline, v in self.const_sites.get(ref.group(1), []) if ref else ():
                            if v == value:
                                self.env_uses.append((srel, sline, value))

    def env_name_value(self, src, a, b):
        lit = src.literal(src.skip(a))
        if lit:
            return lit[0] if ENV_LIKE_NAME.fullmatch(lit[0]) else None
        ref = re.fullmatch(r'(?:\w+\s*\.\s*)?(\w+)', src.code[a:b].strip())
        values = {v for _, _, v in self.const_sites.get(ref.group(1), [])} if ref else set()
        if not values and ref:
            values = set(self.consts.get(ref.group(1), ()))
        if len(values) == 1:
            value = values.pop()
            return value if ENV_LIKE_NAME.fullmatch(value) else None
        return None

    # ------------------------------------------------------------ eventos: señales/observadores, claves cualificadas, jobs por clase

    def scan_signals(self, src):
        """Señales y observadores: `sig.connect(handler)` / `notifier.OnUserDeleted(handler)` registran el handler en el tema `sig` /
        `UserDeleted`; `@receiver(sig)` también; `sig.send(...)`/`emit`/`fire` publican en las señales declaradas o conectadas."""
        code, rel = src.code, src.rel
        if src.lang == 'py' and ('Signal' in code or 'signal' in code):
            self.signal_decls.update(m.group(1) for m in SIGNAL_DECL.finditer(code))
        if src.lang == 'py' and 'receiver' in code:
            for m in RECEIVER_DECOR.finditer(code):
                close = src.close(code.index('(', m.start()))
                d = B.PY_DEF.match(code, close + 1) if close > 0 else None
                fn = self.decl_after(src, d.start(2), d.group(2)) if d else None
                if fn:
                    for sig in m.group(1).split(','):
                        self.signal_regs.append((sig.strip().rsplit('.', 1)[-1], rel, src.line(m.start()), fn, fn))
        for m in (SIGNAL_CONNECT.finditer(code) if '.connect' in code or '.On' in code else ()):
            recv, verb = m.group(1), m.group(2)
            if recv in ('self', 'this', 'super', 'cls') or recv in B.KEYWORDS:
                continue
            if verb.startswith('On') and not NOTIFIER_NAME.search(recv):
                continue
            args, close = src.args(m.end() - 1)
            if not args:
                continue
            line = src.line(m.start())
            node = self.ref_node(src, args[0][0], args[0][1], line)
            if not node or self.g.nodes[node]['kind'] not in ('function', 'method'):
                continue
            topic = verb[2:] if verb.startswith('On') else recv
            self.signal_regs.append((topic, rel, line, self.owner(rel, line), node))
        for m in SIGNAL_FIRE.finditer(code):
            if m.group(1) not in ('self', 'this', 'super', 'cls'):
                self.signal_fires.append((m.group(1), rel, src.line(m.start())))

    def scan_keyed_dispatch(self, src):
        """Claves cualificadas (`Enum.MIEMBRO`) compartidas entre un despacho (`case Q.X:`, `job.name === Q.X`, decorador con
        `{name: Q.X}`) y sus productores (`queue.add(Q.X, ..)`, `{name: Q.X}` en el mensaje encolado)."""
        code, rel = src.code, src.rel
        if '.' not in code:
            return
        for m in (QKEY_CASE.finditer(code) if 'case' in code or '==' in code or '->' in code else ()):
            q, k = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4)) if m.group(3) else (m.group(5), m.group(6))
            line = src.line(m.start())
            sym = self.owner(rel, line)
            if sym and not sym.startswith('m:') and self.dispatch_entry(sym):
                self.qkey_subs.append((f'{q}.{k}', rel, line, sym))
        for m in (QKEY_OBJ.finditer(code) if QKEY_OBJ_HINT.search(code) else ()):
            line = src.line(m.start())
            key = f'{m.group(1)}.{m.group(2)}'
            if self.in_decorator(src, m.start()):
                sym = self.decl_node(rel, self.decorator_line(src, m.start()))
                if sym and not sym.startswith('m:'):
                    self.qkey_subs.append((key, rel, line, sym))
                    self.qkey_declared.add(key)  # consumidor declarado por decorador: el tema existe aunque el productor sea dinámico
            elif self.message_object(src, m.start()):
                self.qkey_pubs.append((key, rel, line))
        for m in QKEY_ARG.finditer(code):
            if not self.in_decorator(src, m.start()):
                self.qkey_pubs.append((f'{m.group(2)}.{m.group(3)}', rel, src.line(m.start())))
        if '@' in code and src.lang in ('js', 'java', 'kt', 'cs', 'py'):
            # misma clave en el decorador de la clase consumidora (`@Processor(Q.X) class P { process() }`) y en la inyección del
            # productor (`@InjectQueue(Q.X) private q: Queue` + `this.q.add(..)`)
            for m in KEYED_CLASS.finditer(code):
                key = f'{m.group(1)}.{m.group(2)}' if m.group(1) else m.group(3)
                cls = next((n for n in self.short.get(m.group(4), []) if self.g.nodes[n]['kind'] == 'class' and self.g.nodes[n]['file'] == rel), None)
                if cls:
                    topic, sym = self.job_topic(cls)
                    if sym != cls:
                        self.qkey_subs.append((key, rel, src.line(m.start()), sym))
            for m in KEYED_FIELD.finditer(code):
                key = f'{m.group(1)}.{m.group(2)}' if m.group(1) else m.group(3)
                for c in re.finditer(rf'\bthis\s*\.\s*{re.escape(m.group(4))}\s*\.\s*(?:add|addBulk|send|emit|publish|push|enqueue)\s*\(', code):
                    self.qkey_pubs.append((key, rel, src.line(c.start())))

    def dispatch_entry(self, sym):
        """Despacho de mensajes: el `switch` está en la entrada de un consumidor (`process`/`handle`/`perform`... o una clase
        `*Processor`/`*Consumer`/`*Handler`/`*Worker`/`*Listener`), no en cualquier `switch` sobre un enum."""
        name = self.g.nodes[sym]['name']
        short = name.rsplit('.', 1)[-1]
        cls = name.rsplit('.', 1)[0].rsplit('.', 1)[-1] if '.' in name else ''
        return short in JOB_ENTRY or bool(re.search(r'(?:Processor|Consumer|Handler|Worker|Listener|Subscriber|Job)$', cls))

    def message_object(self, src, pos):
        """`{name: Q.X}` es un mensaje encolado si es argumento de una llamada productora (`queue({..})`, `add([{..}])`) o lo
        devuelve una función (`return { name: Q.X }`), no la configuración de un registro (`registerQueue({ name: Q.X })`)."""
        enc = self.enclosing(src, pos)
        while enc and enc[2] in '{[':
            before = src.struct[max(0, enc[0] - 30):enc[0]]
            if re.search(r'\breturn\s*$', before):
                return True
            outer = self.enclosing(src, enc[0])
            if outer and outer[2] == '(':
                name = re.search(r'([A-Za-z_$][\w$]*)\s*(?:<[^<>()]*>)?\s*$', src.struct[max(0, outer[0] - 80):outer[0]])
                word = re.match(r'[a-z]+|[A-Z][a-z]*', name.group(1)) if name else None
                return bool(word and PRODUCER_VERB.fullmatch(word.group()))
            enc = outer
        return False

    def decorator_line(self, src, pos):
        start = src.code.rfind('\n', 0, pos) + 1
        for _ in range(20):
            if src.code[start:start + 200].lstrip().startswith(('@', '[')) or start == 0:
                break
            start = src.code.rfind('\n', 0, start - 1) + 1
        return src.line(start)

    def scan_job_classes(self, src):
        """Clases de trabajo (`XTask`, `XJob`, `XWorkflow`, `XActivity`, `XWorker`, o que heredan de una) pasadas por referencia
        (`new XTask()`, `X.class`, `X::class`, `typeof(X)`) como argumento de una llamada: la llamada encola/registra el job."""
        if src.lang not in ('java', 'kt', 'cs', 'php', 'js', 'py', 'rb', 'c', 'go'):
            return
        code, rel = src.code, src.rel
        for m in JOB_CLASS_REF.finditer(code):
            name = m.group(1) or m.group(2) or m.group(3)
            target = self.job_class(name)
            if not target or EXT_FAMILY.get(B.os.path.splitext(self.g.nodes[target]['file'])[1], B.os.path.splitext(self.g.nodes[target]['file'])[1]) \
                    != EXT_FAMILY.get(B.os.path.splitext(rel)[1], B.os.path.splitext(rel)[1]):
                continue
            enc = self.enclosing(src, m.start())
            if not enc or enc[2] != '(':
                continue
            head = src.struct[max(0, enc[0] - 80):enc[0]]
            if re.search(r'(?<![.\w])(?:class|interface)\s+\w+[^;{]*$|\b(?:extends|implements)\s+[^;{()]*$', head):
                continue
            line = src.line(m.start())
            own = self.owner(rel, line)
            if not own or own == target or (self.g.nodes.get(own) or {}).get('name', '').split('.')[0] == name:
                continue
            topic, sym = self.job_topic(target)
            if sym == target:
                continue
            self.topic_uses.append((topic, rel, line, 'pub', '', 'mq'))
            meta = self.g.nodes[sym]
            self.topic_uses.append((topic, meta['file'], meta.get('line') or 1, 'sub', sym, 'mq'))

    def job_class(self, name):
        cache = self.job_classes
        if name in cache:
            return cache[name]
        found = None
        suffix = JOB_CLASS_NAME.search(name)
        if suffix and suffix.start() == 0:
            suffix = None  # `new Worker(...)`, `new Task()`: tipos genéricos, no una clase de trabajo concreta
        if suffix or any(JOB_CLASS_NAME.search(b) for b in self.bases_of(name)):
            cands = [n for n in self.short.get(name, []) if self.g.nodes[n]['kind'] == 'class' and not self.is_test(self.g.nodes[n]['file'])]
            found = cands[0] if len(cands) == 1 else None
        cache[name] = found
        return found

    def bases_of(self, name):
        rev = self.class_bases
        if rev is None:
            rev = self.class_bases = defaultdict(set)
            for base, classes in self.impls.items():
                for c in classes:
                    rev[c].add(base)
        return rev.get(name, ())

    def finish_event_idioms(self):
        """Antes de `finish_topics`: señales (registro + handler, y emisores de señales conocidas), claves cualificadas con despacho
        y productor, y rutas punteadas `"paquete.modulo.tarea"` hacia tareas conocidas."""
        known = {topic for topic, *_ in self.signal_regs} | self.signal_decls
        for topic, rel, line, own, handler in self.signal_regs:
            meta = self.g.nodes[handler]
            if own and own != handler:
                self.topic_uses.append((topic, rel, line, 'sub', own, 'mq'))
            self.topic_uses.append((topic, meta['file'], meta.get('line') or 1, 'sub', handler, 'mq'))
        for sig, rel, line in self.signal_fires:
            if sig in known and len(sig) > 3:
                self.topic_uses.append((sig, rel, line, 'pub', '', 'mq'))
        subs = defaultdict(list)
        for key, rel, line, sym in self.qkey_subs:
            subs[key].append((rel, line, sym))
        pubs = {key for key, _, _ in self.qkey_pubs}
        for key, items in subs.items():
            if key not in pubs and key not in self.qkey_declared:
                continue
            topic = key.rsplit('.', 1)[-1]
            for rel, line, sym in items:
                self.topic_uses.append((topic, rel, line, 'sub', sym, 'mq'))
        for key, rel, line in self.qkey_pubs:
            if key in subs:
                self.topic_uses.append((key.rsplit('.', 1)[-1], rel, line, 'pub', '', 'mq'))
        self.finish_notifier_calls()
        if self.dotted_refs and self.tasks:
            for rel, line, value in self.dotted_refs:
                mod, _, fn = value.rpartition('.')
                if fn not in self.tasks:
                    continue
                defs = [n for n in self.short.get(fn, []) if self.g.nodes[n]['kind'] == 'function'
                        and B.os.path.splitext(self.g.nodes[n]['file'])[0].endswith(mod.replace('.', '/'))]
                if len(defs) == 1:
                    self.topic_uses.append((self.tasks[fn], rel, line, 'pub', '', 'mq'))

    # ------------------------------------------------------------ receptores tipados: `variable.Metodo` -> método del tipo

    def var_type(self, src, var, pos=None):
        """Tipo de una variable local o campo: literal compuesto (`x := pkg.T{..}`, `&T{}`), constructor (`x = T(..)`,
        `final x = T()`, `new T()`), fábrica cuyo tipo de retorno se declara (`x := pkg.NewT(..)` con `func NewT(..) *T`),
        declaración tipada (`var x T`, `T x`, `x: T`)."""
        if not var or var in ('this', 'self', 'super'):
            return None
        cache = getattr(src, 'var_types', None)
        if cache is None:
            cache = src.var_types = {}
        code = src.code
        key = re.escape(var)
        if var not in cache:
            cache[var] = [(m.start(), m.group(1).replace(' ', ''), m.group(2)) for m in re.finditer(
                rf'(?<![\w$.]){key}\s*(?:,\s*[\w$]+\s*)*(?::\s*[\w<>?, .]+?\s*)?:?=\s*(?:await\s+)?&?(?:new\s+)?((?:[A-Za-z_]\w*\s*\.\s*)?[A-Za-z_]\w*)\s*'
                rf'(?:<[^<>()]*>\s*)?([({{])', code)]
        cands = cache[var]
        if pos is not None:
            before = [c for c in cands if c[0] < pos]
            cands = before[-1:] or cands[:1]
        for _, name, kind in cands[-1:]:
            short = name.rsplit('.', 1)[-1]
            if short[:1].isupper() and self.owners.get(short):
                return short
            if kind == '(':
                ret = self.return_type(name)
                if ret:
                    return ret
        if ('#', var) not in cache:
            m = re.search(rf'\bvar\s+{key}\s+\*?(?:\w+\.)?([A-Z]\w*)\b', code)
            if not m and src.lang == 'go':  # parámetro Go `func f(e *echo.Echo, a *App)`
                m = re.search(rf'[(,]\s*{key}\s+\*?(?:\w+\.)?([A-Z]\w*)\s*[,)]', code)
            typ = m.group(1) if m else self.recv_type(src, var)
            if not typ:
                m = re.search(rf'\bfinal\s+([A-Z]\w*)(?:<[^<>]*>)?\??\s+_?{key}\s*[;=]', code)
                typ = m.group(1) if m else None
            cache[('#', var)] = typ
        return cache[('#', var)]

    def return_type(self, name):
        """Tipo de retorno declarado de una fábrica (`func NewX(..) *X`, `function newX(): X`, `fun newX(): X`)."""
        qual, _, short = name.rpartition('.')
        funcs = [n for n in self.short.get(short, []) if self.g.nodes[n]['kind'] == 'function']
        if qual and len(funcs) > 1:
            funcs = [n for n in funcs if B.os.path.basename(B.os.path.dirname(self.g.nodes[n]['file'])) == qual] or funcs
        if len(funcs) != 1:
            return None
        meta = self.g.nodes[funcs[0]]
        lines = (self.text(meta['file']) or '').split('\n')[(meta.get('line') or 1) - 1:(meta.get('line') or 1) + 3]
        head = ' '.join(lines)
        m = re.search(rf'\b{re.escape(short)}\s*\([^)]*\)\s*(?::\s*)?\(?\s*\*?(?:\w+\.)?([A-Z]\w*)', head)
        return m.group(1) if m and self.owners.get(m.group(1)) else None

    def typed_method(self, src, text, pos=None):
        """`variable.Metodo` (o `variable.Metodo()` que devuelve el handler) resuelto por el tipo de la variable."""
        m = re.fullmatch(r'\s*(?:this\.|self\.)?([a-z_]\w*)\s*\.\s*([A-Za-z_]\w*)\s*(?:\(\s*\))?\s*', text)
        if not m or m.group(1) in ('this', 'self', 'super', 'cls') or m.group(1) in B.KEYWORDS:
            return None
        typ = self.var_type(src, m.group(1), pos)
        if not typ:
            return None
        found = [n for n in self.owners.get(typ, []) if self.g.nodes[n]['name'].rsplit('.', 1)[-1] == m.group(2)
                 and not self.is_test(self.g.nodes[n]['file'])]
        return found[0] if len(found) == 1 else None

    def scan_chained_groups(self, src):
        """Rutas sobre un grupo creado en la misma cadena: `r.Group("/user").Use(mw).POST("", h)` -> `POST /user`."""
        code = src.code
        if 'Group(' not in code:
            return
        for m in CHAINED_GROUP.finditer(code):
            verb = m.group(3).upper()
            args, close = src.args(m.end() - 1)
            if len(args) < 2:
                continue
            tpl = src.expr(args[0][0])
            if tpl is None:
                continue
            path = '/'.join(x.strip('/') for x in (m.group(2), tpl) if x.strip('/'))
            handler = self.handler(src, *args[-1], src.line(m.start(3)))
            self.route(src, m.start(3), m.group(1), ['ANY' if verb == 'ANY' else verb], '/' + path, handler,
                       self.scopes_at([], m.start()), strict=True)

    # ------------------------------------------------------------ clientes HTTP: llamadas tipo fetch, receptores llamados, SDK generados

    def scan_fetch_like(self, src):
        """Llamadas cuyo nombre empieza por `fetch`/`request`/`http` (`fetchJson("/x", {method: "POST"})`, `requestJson`, `httpGet`)
        con una ruta literal, y clientes obtenidos de una llamada (`api().get("/x")`, `getClient().post(..)`). Son clientes débiles:
        sólo enlazan si casan con un endpoint declarado. Una base literal del fichero (`baseUrl: "/api"`) se antepone."""
        code = src.code
        base = None
        bases = {lit for lit in re.findall(r'''\b(?:baseURL|baseUrl|basePath|BASE_URL)\s*[:=]\s*["'`](/[\w\-./]*)["'`]''', code)}
        if len(bases) == 1:
            base = bases.pop().rstrip('/')
        for m in (FETCH_LIKE.finditer(code) if FETCH_HINT.search(code) else ()):
            name = m.group(1)
            if name in ('fetch', 'request', 'http') or name.endswith(('Wrapper', 'Mock')):
                continue
            args, close = src.args(m.end() - 1)
            if not args:
                continue
            first = src.skip(args[0][0])
            if src.struct[first:first + 1] == '{':
                uu = B.URL_KW.search(code, first, args[0][1])
                first = src.skip(uu.end()) if uu else None
            lit = src.literal(first) if first is not None else None
            if not lit or not lit[0].startswith('/'):
                continue
            tpl = src.expr(first)
            if tpl is None:
                continue
            rest = code[args[0][1]:close]
            mm = B.METHOD_KW.search(rest)
            verb = mm.group(1).upper() if mm else next((v for v in B.VERBS if name.upper().endswith(v)), 'GET')
            if base and not tpl.startswith(base + '/'):
                tpl = base + tpl
            self.weak_client(src, src.line(m.start()), verb, tpl)
        if src.lang == 'js' and CALLED_HINT.search(code):
            for m in CALLED_CLIENT.finditer(code):
                if not any(B.JS_CLIENT_NAMES.match(x) for x in re.split(r'\s*\.\s*', m.group(1))):
                    continue
                args, close = src.args(m.end() - 1)
                if not args:
                    continue
                tpl = self.js_url_arg(src, args[0])
                if tpl is not None:
                    self.weak_client(src, src.line(m.start()), m.group(2).upper(), tpl)

    def finish_sdk_callers(self):
        """Funciones exportadas de un cliente generado (una sola llamada HTTP) llamadas desde otros ficheros que las importan del
        fichero o de un índice/paquete que lo reexporta (`import { getKeys } from '@org/sdk'`): la llamada es un cliente del endpoint."""
        wrappers = defaultdict(dict)
        found = defaultdict(set)
        for a, b, kind in self.g.edges:
            if kind == 'http' and b.startswith('e:'):
                found[a].add(b)
        for sym, targets in found.items():
            meta = self.g.nodes.get(sym) or {}
            if len(targets) == 1 and meta.get('kind') == 'function' and B.EXT_LANG.get(B.os.path.splitext(meta['file'])[1]) == 'js' \
                    and self.generated(meta['file']):
                wrappers[meta['name']][meta['file']] = (sym, next(iter(targets)))
        if not wrappers:
            return
        rx = re.compile(r'(?<![\w$.])(%s)\s*(?:<[^<>()]*>)?\s*\(' % '|'.join(sorted(map(re.escape, wrappers), key=len, reverse=True)))
        for rel in self.files:
            if B.EXT_LANG.get(B.os.path.splitext(rel)[1]) != 'js' or self.is_test(rel) or self.generated(rel):
                continue
            text = self.text(rel)
            if not text or len(text) > 600 * 1024 or not rx.search(text):
                continue
            src = self.src(rel, 'js', text)
            imports = self.js_import_map(src)
            resolved = {}
            for m in rx.finditer(src.code):
                name = m.group(1)
                if name not in imports or B.IMPORT_LINE.match(src.code[src.code.rfind('\n', 0, m.start()) + 1:m.start()]):
                    continue
                if name not in resolved:
                    trel = self.js_import_target(src, name)
                    resolved[name] = next(((sym, ep) for frel, (sym, ep) in wrappers[name].items()
                                           if trel and (trel == frel or self.reexports(trel, imports[name][1] or name, frel))), None)
                hit = resolved[name]
                sym = self.owner(rel, src.line(m.start())) if hit else None
                if sym and sym != hit[0]:
                    self.g.edge(sym, hit[1], 'http')

    def scan_navigation(self, src):
        """Navegación del navegador a una URL del backend (`window.location.href = url`, `window.open(url)`, `location.assign(url)`):
        cliente débil GET (sólo enlaza si casa con un endpoint declarado)."""
        code = src.code
        if 'location' not in code and 'open' not in code:
            return
        for m in NAVIGATION.finditer(code):
            if not m.group().endswith('('):
                start = m.end()
            else:
                args, close = src.args(m.end() - 1)
                if not args:
                    continue
                start = args[0][0]
            tpl = src.expr(start)
            if tpl is None or '\0' not in tpl and not tpl.startswith('/'):
                continue
            self.weak_client(src, src.line(m.start()), 'GET', tpl)

    def collect_orm_registrations(self, rel, lang, text):
        """Registro de modelos en el ORM (`db.AutoMigrate(new(model.User), &model.App{})`, `Sync2`, `RegisterModel`, `CreateTable`):
        los tipos registrados son modelos (tabla = nombre en plural)."""
        for m in ORM_REGISTER.finditer(text):
            depth, i = 0, m.end() - 1
            while i < len(text):
                if text[i] == '(':
                    depth += 1
                elif text[i] == ')':
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            for t in ORM_REGISTERED.finditer(text, m.end(), i):
                self.orm_registered.append((rel, t.group(1) or t.group(3) or '', t.group(2) or t.group(4)))

    def finish_orm_registrations(self):
        for rel, pkg, name in sorted(set(self.orm_registered)):
            cands = [n for n in self.short.get(name, []) if self.g.nodes[n]['kind'] == 'class' and self.g.nodes[n]['file'].endswith('.go')
                     and not self.is_test(self.g.nodes[n]['file']) and not self.g.nodes[n].get('table')]
            if pkg and len(cands) > 1:
                cands = [n for n in cands if B.os.path.basename(B.os.path.dirname(self.g.nodes[n]['file'])) == pkg] or cands
            nid = cands[0] if len(cands) == 1 else self.pick(rel, cands)
            if nid:
                meta = self.g.nodes[nid]
                self.model_at(meta['file'], meta.get('line') or 1, name, B.plural_word(B.snake(name)), 'go')

    def template_ternaries(self, src, start, end, env=None):
        """Plantilla con una interpolación ternaria de literales (`${base}x/${on ? 'enable' : 'disable'}`): una URL por rama."""
        lit = src.literal(start)
        if not lit:
            return []
        content, _, prefix, quote = lit
        m = TERNARY_SLOT.search(content)
        if not m:
            return []
        out = []
        for branch in (m.group(2), m.group(3)):
            variant = content[:m.start()] + branch + content[m.end():]
            value = src.template(variant, prefix, quote, start, 0, env)
            if value:
                out.append(value)
        return out

    def finish_notifier_calls(self):
        """Notificadores en proceso: funciones/métodos con nombre productor (`send_folder_update`, `push_logout`, `Notify`,
        `broadcastX`) definidos en un módulo o tipo de mensajería (`notifications`, `push`, `stream`, `hub`, `websocket`, `events`...)
        y llamados desde otro fichero: la llamada publica en el tema del método, que es su consumidor."""
        by_lang = defaultdict(dict)
        names = defaultdict(list)
        for nid, meta in self.g.nodes.items():
            if meta.get('kind') not in ('function', 'method') or not meta.get('file') or self.is_test(meta['file']):
                continue
            short = meta['name'].rsplit('.', 1)[-1]
            if NOTIFY_NAME.match(short):
                names[short].append(nid)
        for short, nids in names.items():
            if len(nids) != 1:
                continue
            meta = self.g.nodes[nids[0]]
            rel = meta['file']
            place = [B.os.path.splitext(rel.rsplit('/', 1)[-1])[0], rel.rsplit('/', 2)[-2] if rel.count('/') else '']
            if '.' in meta['name']:
                place.append(meta['name'].rsplit('.', 2)[-2])
            lang = B.EXT_LANG.get(B.os.path.splitext(rel)[1])
            if lang and any(MESSAGING_PLACE.search(p) for p in place if p):
                by_lang[lang][short] = nids[0]
        for lang, book in by_lang.items():
            rx = re.compile(r'(?<![\w$])(%s)\s*(?:::<[^<>]*>)?\s*\(' % '|'.join(sorted(map(re.escape, book), key=len, reverse=True)))
            for rel in self.files:
                if B.EXT_LANG.get(B.os.path.splitext(rel)[1]) != lang or self.is_test(rel):
                    continue
                text = self.text(rel)
                if not text or len(text) > 800 * 1024 or not rx.search(text):
                    continue
                aliases = None
                for m in rx.finditer(text):
                    target = book[m.group(1)]
                    meta = self.g.nodes[target]
                    if meta['file'] == rel:
                        continue
                    recv = re.search(r'([A-Za-z_]\w*)\s*(?:\.|::)\s*$', text[max(0, m.start() - 60):m.start()])
                    if recv:
                        if aliases is None:
                            aliases = self.module_aliases(self.src(rel, lang, text)) if lang in ('go', 'py', 'js') else set()
                        pkg = B.os.path.basename(B.os.path.dirname(meta['file']))
                        if recv.group(1) in aliases and recv.group(1) != pkg and recv.group(1) != B.os.path.splitext(B.os.path.basename(meta['file']))[0]:
                            continue  # `signal.Notify(..)`: función de un paquete importado, no el notificador del repo
                    head = text[max(0, m.start() - 80):m.start()].split('\n')[-1]
                    if DEF_HEAD.search(head):
                        continue
                    line = text.count('\n', 0, m.start()) + 1
                    if B.IMPORT_LINE.match(text[text.rfind('\n', 0, m.start()) + 1:m.start()]):
                        continue
                    own = self.owner(rel, line)
                    if not own or self.g.nodes[own]['kind'] not in ('function', 'method'):
                        continue  # firma de una interfaz (`Notify(userID uint, ..)` en `type Notifier interface`), no una llamada
                    self.topic_uses.append((m.group(1), rel, line, 'pub', own, 'mq'))
                    self.topic_uses.append((m.group(1), meta['file'], meta.get('line') or 1, 'sub', target, 'mq'))

    # ------------------------------------------------------------ routers de viewsets (DRF y similares)

    def viewset_routes(self, base, cls):
        """Registro de un viewset en un router (`router.register("x", XViewSet)`): acciones estándar según las bases (`ModelViewSet`,
        `ReadOnlyModelViewSet`, mixins `List/Create/Retrieve/Update/DestroyModelMixin`) o los métodos definidos, cada una a su método
        si la clase lo define y si no a la clase; y acciones extra `@action(methods=[..], detail=.., url_path=..)`."""
        meta = self.g.nodes.get(cls) if cls else None
        if not meta or meta.get('kind') != 'class':
            return None
        text = self.text(meta['file']) or ''
        lines = text.split('\n')
        head = ' '.join(lines[(meta.get('line') or 1) - 1:(meta.get('line') or 1) + 2])
        bases = self.viewset_bases(head, meta['file'], 0)
        methods = {}
        for n in self.owners.get(meta['name'], []):
            if self.g.nodes[n]['file'] == meta['file']:
                methods[self.g.nodes[n]['name'].rsplit('.', 1)[-1]] = n
        actions = set(a for a in VIEWSET_ACTIONS if a in methods)
        for b in bases:
            actions |= VIEWSET_BASES.get(b, set())
        if not actions and not bases & set(VIEWSET_BASES) and not any(b.endswith(('ViewSet', 'ViewSetMixin')) for b in bases):
            return None
        base = base.strip('/')
        out = []
        for action, (verb, detail) in VIEWSET_ACTIONS.items():
            if action in actions:
                out.append(([verb], base + ('/<pk>' if detail else ''), methods.get(action, cls)))
        body = '\n'.join(lines[(meta.get('line') or 1) - 1:meta.get('end') or len(lines)])
        for m in VIEWSET_EXTRA.finditer(body):
            args = m.group(1)
            name = m.group(2)
            fn = methods.get(name)
            if not fn:
                continue
            verbs = [v.upper() for v in re.findall(r'''["'](\w+)["']''', (re.search(r'\bmethods\s*=\s*\[([^\]]*)\]', args) or [None, '"get"'])[1])]
            url = re.search(r'''\burl_path\s*=\s*r?["']([^"']+)["']''', args)
            detail = re.search(r'\bdetail\s*=\s*True\b', args)
            out.append(([v for v in verbs if v in B.VERBS] or ['GET'], base + ('/<pk>' if detail else '') + '/' + (url.group(1) if url else name), fn))
        return out

    def viewset_bases(self, head, rel, depth):
        m = re.search(r'\bclass\s+\w+\s*\(([^)]*)\)', head)
        names = {re.sub(r'\[.*$', '', b.strip()).rsplit('.', 1)[-1] for b in (m.group(1).split(',') if m else []) if b.strip()}
        out = set(names)
        if depth < 3:
            for name in names - set(VIEWSET_BASES):
                cands = [n for n in self.short.get(name, []) if self.g.nodes[n]['kind'] == 'class' and self.g.nodes[n]['file'].endswith('.py')]
                if len(cands) == 1:
                    cm = self.g.nodes[cands[0]]
                    ctext = (self.text(cm['file']) or '').split('\n')
                    out |= self.viewset_bases(' '.join(ctext[(cm.get('line') or 1) - 1:(cm.get('line') or 1) + 2]), cm['file'], depth + 1)
        return out

    def spec_implementors(self, cands, tags):
        """Desempate entre métodos homónimos del `operationId`: la clase que implementa la interfaz generada desde el spec (`{Tag}Api`,
        `{Tag}Resource`...) o, si no, una interfaz que el repo no declara (generada en la compilación)."""
        def bases(n):
            cls = self.g.nodes[n]['name'].rsplit('.', 1)[0].rsplit('.', 1)[-1] if '.' in self.g.nodes[n]['name'] else ''
            return self.bases_of(cls) if cls else set()
        want = {re.sub(r'\W', '', t).lower() for t in tags or ()}
        named = [n for n in cands if any(re.sub(r'(?:Api|Resource|Controller|Service|Delegate|Endpoint)$', '', b).lower() in want for b in bases(n))]
        if named:
            return named
        return [n for n in cands if any(not any(self.g.nodes[x]['kind'] == 'class' for x in self.short.get(b, [])) and b[:1].isupper()
                                        and b.endswith(('Api', 'Resource', 'Controller', 'Delegate')) for b in bases(n))]

    # ------------------------------------------------------------ OpenAPI repartido en ficheros (`$ref` de path items)

    def openapi_refs(self, rel, text):
        """`paths: /x: $ref: "./resources/x.yaml"`: las operaciones del path item están en el fichero referenciado; el endpoint se
        sitúa en la línea del verbo de ese fichero."""
        lines = text.split('\n')
        start = next((i for i, x in enumerate(lines) if re.match(r'paths:\s*(?:#.*)?$', x)), None)
        if start is None or '$ref' not in text:
            return
        base = re.search(r'''^basePath:\s*['"]?(/[^'"\s#]*)''', text, re.M)
        base = base.group(1).rstrip('/') if base else ''
        servers = re.search(r'^servers:\s*\n\s*-\s*url:\s*(\S+)', text, re.M)
        base = base or (B.spec_base(servers.group(1)) if servers else '')
        path = None
        for i in range(start + 1, len(lines)):
            raw = lines[i]
            body = raw.strip()
            if not body or body.startswith('#'):
                continue
            if B.indent_of(raw) == 0:
                break
            m = re.match(r'''['"]?(/[^'"]*?)['"]?\s*:\s*(?:#.*)?$''', body)
            if m:
                path = m.group(1)
                continue
            ref = re.match(r'''\$ref:\s*['"]?([^'"#\s]+\.ya?ml)['"]?\s*$''', body)
            if ref and path:
                target = B.os.path.normpath(B.os.path.join(B.os.path.dirname(rel), ref.group(1))).replace(B.os.sep, '/')
                sub = self.text(target) if target in self.fileset else None
                if sub:
                    self.openapi += [(target,) + op for op in path_item_ops(sub, base + path)]
                path = None


def path_item_ops(text, path):
    """Operaciones de un path item YAML en su propio fichero: verbos en la raíz con `operationId` y `tags`."""
    ops, op = [], None
    lines = text.split('\n')
    for i, raw in enumerate(lines):
        body = raw.strip()
        if not body or body.startswith('#'):
            continue
        ind = len(raw) - len(raw.lstrip())
        if ind == 0:
            m = re.match(r'(get|put|post|delete|patch|head|options)\s*:\s*$', body)
            op = [i + 1, m.group(1).upper(), path, None, []] if m else None
            if op:
                ops.append(op)
            continue
        if op is None:
            continue
        m = re.match(r'''operationId:\s*['"]?([\w.\-]+)''', body)
        if m:
            op[3] = m.group(1)
        m = re.match(r'tags:\s*(\[[^\]]*\])?\s*$', body)
        if m and m.group(1):
            op[4] = [t.strip().strip('\'"') for t in m.group(1)[1:-1].split(',') if t.strip()]
        elif m:
            for nxt in lines[i + 1:i + 12]:
                item = re.match(r'''\s*-\s*['"]?([^'"#]+?)['"]?\s*$''', nxt)
                if not item:
                    break
                op[4].append(item.group(1))
    return [tuple(o[:4]) + (tuple(o[4]),) for o in ops if o[3]]


class CrossLanguage:
    """Interfaces implementadas sólo en otro lenguaje (canales de plataforma generados: la app Dart llama a `NativeApi.m()` y la
    implementación es una clase Kotlin/Swift que declara `: NativeApi`): la llamada tipada es un RPC hacia el método implementado
    (o heredado de una base del repo)."""

    def finish_cross_language(self):
        lang_of = lambda rel: EXT_FAMILY.get(B.os.path.splitext(rel)[1], B.os.path.splitext(rel)[1])
        impls, callers = {}, set()
        for base, classes in self.impls.items():
            if len(base) < 4 or base[:1].islower():
                continue
            nodes = [n for c in sorted(classes) for n in self.short.get(c, []) if self.g.nodes[n]['kind'] == 'class'
                     and not self.is_test(self.g.nodes[n]['file'])]
            impl_langs = {lang_of(self.g.nodes[n]['file']) for n in nodes}
            decls = [n for n in self.short.get(base, []) if self.g.nodes[n]['kind'] == 'class']
            defined = {lang_of(self.g.nodes[n]['file']) for n in decls}
            if not nodes or not defined or impl_langs & defined:
                continue
            if not any(re.search(rf'\b(?:abstract\s+(?:base\s+|interface\s+)?class|interface|protocol|trait)\s+{re.escape(base)}\b',
                                 self.text(self.g.nodes[n]['file']) or '') for n in decls):
                continue  # el contrato es una interfaz/clase abstracta (IDL), no una clase concreta homónima
            impls[base] = nodes  # contrato declarado en otro lenguaje (IDL), generado para el que lo implementa
            callers.update(defined)
        if not impls:
            return
        globals_ = self.global_instances(callers)
        rx = re.compile(r'\b(%s)\b' % '|'.join(sorted(map(re.escape, impls), key=len, reverse=True)))
        for rel in self.files:
            ext = lang_of(rel)
            lang = B.EXT_LANG.get(B.os.path.splitext(rel)[1])
            if not lang or ext not in callers or self.is_test(rel) or self.generated(rel):
                continue  # el contrato se usa desde el lenguaje que lo declara
            text = self.text(rel)
            if not text or len(text) > 600 * 1024:
                continue
            mentioned = set(rx.findall(text))
            gl = {var: t for var, t in globals_.items() if t in impls and re.search(rf'\b{re.escape(var)}\s*\.', text)}
            if not mentioned and not gl:
                continue
            src = None
            for m in CALL_ON_VAR.finditer(text):
                var, meth = m.group(1), m.group(2)
                if var in ('this', 'self', 'super', 'super', 'widget') or meth[:1].isupper():
                    continue
                src = src or self.src(rel, lang, text)
                typ = self.var_type(src, var) if mentioned else None
                typ = typ if typ in impls else gl.get(var)
                if not typ:
                    continue
                classes = [n for n in impls[typ] if lang_of(self.g.nodes[n]['file']) != ext]
                if not classes or len(classes) != len(impls[typ]):
                    continue
                targets = set()
                for cls in classes:
                    hit = self.inherited_method(self.g.nodes[cls]['name'], meth, 0, lang_of(self.g.nodes[cls]['file']))
                    if hit:
                        targets.add(hit)
                sym = self.owner(rel, text.count('\n', 0, m.start()) + 1) if targets else None
                for t in sorted(targets)[:3]:
                    if sym and sym != t:
                        self.g.edge(sym, t, 'rpc')

    def inherited_method(self, cls, meth, depth, ext=None):
        family = lambda rel: EXT_FAMILY.get(B.os.path.splitext(rel)[1], B.os.path.splitext(rel)[1])
        found = [n for n in self.owners.get(cls, []) if self.g.nodes[n]['name'].rsplit('.', 1)[-1] == meth
                 and (ext is None or family(self.g.nodes[n]['file']) == ext)]
        if found:
            return found[0]
        if depth < 3:
            for base in sorted(self.bases_of(cls)):
                hit = self.inherited_method(base, meth, depth + 1, ext)
                if hit:
                    return hit
        return None

    def global_instances(self, families):
        """Instancias de nivel superior (`final networkApi = NetworkApi();`, `val api = Api()`) declaradas una sola vez en el repo."""
        found = defaultdict(set)
        for rel in self.files:
            ext = B.os.path.splitext(rel)[1]
            if ext not in ('.dart', '.kt', '.ts', '.js', '.swift') or EXT_FAMILY.get(ext, ext) not in families or self.is_test(rel):
                continue
            text = self.text(rel)
            if not text or len(text) > 600 * 1024 or '= ' not in text:
                continue
            for m in GLOBAL_INSTANCE.finditer(text):
                found[m.group(1)].add(m.group(2))
        return {var: next(iter(ts)) for var, ts in found.items() if len(ts) == 1}


class UrlBuilders:
    """Métodos que construyen la URL a partir de campos de la instancia y de sus parámetros, definidos en una clase base de otro
    fichero (`getResourceUrl(id = null, action = null) { let url = `${this.baseUrl}${this.resourceName}/`; if (id) url += `${id}/` ...`)
    y llamados desde subclases que fijan esos campos (`this.resourceName = 'documents'`): `this.http.post(this.getResourceUrl(null,
    'bulk_edit'))` es un cliente de `.../documents/bulk_edit/`."""

    def scan_url_builders(self, src):
        code = src.code
        if 'this.' not in code:
            return
        for m in BUILDER_CALL.finditer(code):
            chain = B.js_chain(code, m.start(1)) + [m.group(1)]
            if not any(B.JS_CLIENT_NAMES.match(x) for x in chain if x not in ('this', 'self')):
                continue
            args, close = src.args(m.end() - 1)
            if not args:
                continue
            a, b = args[0]
            bm = re.match(r'\s*this\s*\.\s*(\w+)\s*\(', code[a:b])
            if not bm:
                continue
            open_pos = a + bm.end() - 1
            bargs, bclose = src.args(open_pos)
            if bclose < 0 or bclose > b:
                continue
            value = self.builder_value(src, m.start(), bm.group(1), [code[x:y].strip() for x, y in bargs])
            if value is None:
                continue
            rest = code[bclose + 1:b].strip()
            if rest.startswith('+'):
                tail = src.expr(src.skip(bclose + 1 + code[bclose + 1:b].index('+') + 1))
                value += tail if tail is not None else '\0'
            elif rest:
                continue
            self.weak_client(src, src.line(m.start()), m.group(2).upper(), value)

    def builder_value(self, src, pos, name, args):
        own = self.owner(src.rel, src.line(pos))
        meta = self.g.nodes.get(own) or {}
        if '.' not in meta.get('name', ''):
            return None
        cls = meta['name'].rsplit('.', 1)[0]
        method = self.class_method(cls, name, 0)
        if not method:
            return None
        mmeta = self.g.nodes[method]
        text = self.text(mmeta['file']) or ''
        lines = text.split('\n')
        body = '\n'.join(lines[(mmeta.get('line') or 1) - 1:mmeta.get('end') or (mmeta.get('line') or 1)])
        sig = re.search(rf'\b{re.escape(name)}\s*\(([^)]*)\)', body)
        params = [re.split(r'[\s:=?]', p.strip(), 1)[0] for p in sig.group(1).split(',')] if sig else []
        env = {}
        for i, p in enumerate(params):
            arg = args[i] if i < len(args) else None
            if arg is None or arg in ('null', 'undefined', 'None', ''):
                env[p] = None
            else:
                lit = re.fullmatch(r'''(['"`])([^'"`$]*)\1''', arg)
                env[p] = lit.group(2) if lit else '\0'
        field = lambda f: self.field_value(src, f) if self.field_value(src, f) is not None else self.field_value_in(text, f)
        first = re.search(r'\b(?:let|var|const)\s+(\w+)\s*(?::\s*\w+)?\s*=\s*([^;\n]+)', body)
        if not first:
            ret = re.search(r'\breturn\s+([^;\n]+)', body)
            return self.eval_url(ret.group(1), env, field) if ret else None
        var, value = first.group(1), self.eval_url(first.group(2), env, field)
        if value is None:
            return None
        for am in re.finditer(rf'\b{re.escape(var)}\s*\+=\s*([^;\n]+)', body[first.end():]):
            before = body[:first.end() + am.start()].split('\n')
            cond = re.search(r'\bif\s*\(\s*(\w+)', '\n'.join(before[-3:]))
            if cond and cond.group(1) in env and env[cond.group(1)] is None:
                continue
            part = self.eval_url(am.group(1), env, field)
            value += part if part is not None else '\0'
        return value

    def class_method(self, cls, name, depth):
        found = [n for n in self.owners.get(cls, []) if self.g.nodes[n]['name'].rsplit('.', 1)[-1] == name]
        if found:
            return found[0]
        short = cls.rsplit('.', 1)[-1]
        for base in sorted(self.bases_of(short)) if depth < 3 else ():
            hit = self.class_method(base, name, depth + 1)
            if hit:
                return hit
        return None

    def field_value(self, src, f):
        return self.field_value_in(src.code, f, strict=True)

    def field_value_in(self, text, f, strict=False):
        m = re.search(rf'''(?:\bthis\s*\.\s*|^[ \t]*(?:(?:private|protected|public|readonly|static)\s+)*){re.escape(f)}\s*(?::\s*[\w<>\[\]|]+\s*)?=\s*(['"`])([^'"`$\n]*)\1''',
                      text, re.M)
        if m:
            return m.group(2)
        return None if strict else ('\0' if re.search(rf'\b{re.escape(f)}\b', text) else None)

    def eval_url(self, expr, env, field):
        expr = expr.strip().rstrip(';').strip()
        out = []
        for part in re.split(r'\s*\+\s*', expr):
            lit = re.fullmatch(r'''(['"])([^'"]*)\1''', part)
            tpl = re.fullmatch(r'`([^`]*)`', part)
            if lit:
                out.append(lit.group(2))
            elif tpl:
                def sub(mm):
                    inner = mm.group(1).strip()
                    fm = re.fullmatch(r'this\.(\w+)', inner)
                    if fm:
                        v = field(fm.group(1))
                        return v if v is not None else '\0'
                    v = env.get(inner, '\0')
                    return v if v is not None else ''
                out.append(re.sub(r'\$\{([^{}]*)\}', sub, tpl.group(1)))
            elif re.fullmatch(r'this\.(\w+)', part):
                v = field(part[5:])
                out.append(v if v is not None else '\0')
            elif part in env:
                out.append(env[part] or '')
            else:
                out.append('\0')
        return ''.join(out)


class SchemaMaps:
    """Mapas de esquema tipados: una interfaz/tipo cuyos miembros son tablas declaradas (`interface DB { comments: Comments;
    pageLabels: PageLabels }`, el esquema de Kysely o de un cliente generado): cada tipo miembro es el modelo de esa tabla. También en
    ficheros de declaraciones `.d.ts` versionados (que el análisis general no incluye), donde se declara el nodo del tipo."""

    def schema_maps(self):
        if not self.tables:
            return
        cands = [rel for rel in self.files if rel.endswith(('.ts', '.tsx')) and rel in self.cache]
        if (self.root / '.git').exists():
            self.is_tracked('')
            cands += [rel for rel in sorted(self.tracked or ()) if rel.endswith('.d.ts') and '/node_modules/' not in '/' + rel
                      and not self.is_test(rel)]
        for rel in cands:
            text = self.cache.get(rel)
            if text is None:
                try:
                    path = self.root / rel
                    if path.stat().st_size > 512 * 1024:
                        continue
                    text = path.read_text(encoding='utf-8', errors='replace')
                except OSError:
                    continue
            if 'interface' not in text and 'type' not in text:
                continue
            for m in SCHEMA_BLOCK.finditer(text):
                brace = m.end() - 1
                end = text.find('\n}', brace)
                body = text[brace:end if end > 0 else brace + 20000]
                members = SCHEMA_MEMBER.findall(body)
                hits = [(k, t) for k, t in members if B.snake(k) in self.tables or k.lower() in self.tables]
                if len(hits) < 3 or len(hits) * 2 < len(members):
                    continue
                for key, typ in hits:
                    table = B.snake(key) if B.snake(key) in self.tables else key.lower()
                    decl = re.search(rf'^(?:export\s+)?(?:interface\s+{re.escape(typ)}\b|type\s+{re.escape(typ)}\s*=)', text, re.M)
                    if not decl:
                        continue
                    line = text.count('\n', 0, decl.start()) + 1
                    close = text.find('\n}', decl.end())
                    end_line = text.count('\n', 0, close) + 2 if close > 0 else line
                    nid = next((n for _, _, n in self.by_file.get(rel, []) if self.g.nodes[n]['name'] == typ), None)
                    if nid is None:
                        if not self.module(rel):
                            self.g.node(f'm:{rel}', kind='module', name=rel.rsplit('/', 1)[-1], file=rel, line=1, lang='ts',
                                        end=text.count('\n') + 1, hash=B.digest(rel))
                        nid = self.declare(f'c:{rel}:{typ}', 'class', typ, rel, line)
                        self.g.nodes[nid].update(end=end_line, lang='ts')
                        self.add_item(rel, line, end_line, nid)
                    self.model_at(rel, line, typ, table, 'js')



class GeneratedClients:
    """Clientes generados desde un spec OpenAPI del repo que no están versionados (`openapi-generator` en el build): una llamada
    `api.createPartner(..)` sobre un receptor cuyo tipo (`PartnersApi`, `UsersClient`) no declara el repo y cuyo método es un
    `operationId` del spec es un cliente HTTP de esa operación."""

    def finish_generated_clients(self):
        ops = defaultdict(set)
        for rel, line, verb, path, op, tags in self.openapi:
            ops[op].add((verb, path))
        ops = {op: next(iter(v)) for op, v in ops.items() if len(v) == 1}
        if not ops:
            return
        rx = re.compile(r'(?<![\w$.])([A-Za-z_]\w*)\s*\??\.\s*(%s)\s*\(' % '|'.join(sorted(map(re.escape, ops), key=len, reverse=True)))
        declared = lambda t: any(self.g.nodes[n]['kind'] == 'class' for n in self.short.get(t, []))
        for rel in self.files:
            lang = B.EXT_LANG.get(B.os.path.splitext(rel)[1])
            if not lang or self.is_test(rel) or self.generated(rel):
                continue
            text = self.text(rel)
            if not text or len(text) > 600 * 1024 or not rx.search(text):
                continue
            src = None
            for m in rx.finditer(text):
                if m.group(1) in ('this', 'self', 'super'):
                    continue
                src = src or self.src(rel, lang, text)
                typ = self.var_type(src, m.group(1))
                if not typ or not GENERATED_CLIENT_TYPE.match(typ) or declared(typ):
                    continue
                verb, path = ops[m.group(2)]
                line = text.count('\n', 0, m.start()) + 1
                sym = self.owner(rel, line)
                if sym:
                    self.clients.append((rel, line, verb, B.norm_path(path), sym))

    def load_openapi_json(self):
        """Specs OpenAPI/Swagger en JSON versionados con otro nombre (`app-openapi-specs.json`) que el listado general no incluye."""
        if not (self.root / '.git').exists() and not any(OPENAPI_JSON.search(f) for f in self.files):
            names = []
            for dirpath, _, filenames in B.os.walk(self.root):
                if '/node_modules' in dirpath or '/.git' in dirpath:
                    continue
                names += [B.os.path.relpath(B.os.path.join(dirpath, n), self.root).replace(B.os.sep, '/') for n in filenames
                          if OPENAPI_JSON.search(n)]
                if len(names) > 50:
                    break
        else:
            self.is_tracked('')
            names = [rel for rel in sorted(self.tracked or ()) if OPENAPI_JSON.search(rel.rsplit('/', 1)[-1])]
        for rel in names:
            if rel in self.fileset or self.is_test(rel) or '/node_modules/' in '/' + rel:
                continue
            try:
                path = self.root / rel
                if path.stat().st_size > 8 * 1024 * 1024:
                    continue
                text = path.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            if '"paths"' in text[:400000] and re.search(r'"(?:openapi|swagger)"\s*:', text[:4000]):
                self.openapi += [(rel,) + op for op in B.openapi_json(text)]
