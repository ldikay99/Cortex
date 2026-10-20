"""Mecanismos generales validados en el corpus (ronda 6 del benchmark de flujos, `bench/flows`).

Mixin de `bridges.Bridges`, como `structural.Structural` e `idioms.Idioms`. Cada mecanismo describe un idioma en abstracto (no una
librería) y se aceptó sólo tras encontrarlo, como texto, en el repo de ajuste y en al menos otros dos repos/instancias del corpus local,
revisando a mano la precisión en esas otras instancias (evidencia en `bench/flows/README.md`, «Ronda 6»; casos sintéticos en
`analyzer/tests/test_bridges_crossval.py`):

- Bus de mensajes tipado: una clase del repo que implementa/hereda un tipo genérico `G<T>` y tiene un método cuyo primer parámetro es
  de tipo `T` es un consumidor de `T`; una instancia `new T(..)` pasada directamente a una llamada de despacho (verbo de despacho o
  método genérico del repo `M<X>(X x)`), o una referencia de tipo `typeof(T)`/`T.class`/`T::class`, es un productor de `T`
  (`typed_bus_*`). También los registros tipados: una llamada con una referencia de tipo y una referencia a un handler cuyo
  parámetro es de ese tipo (`listen(T::class, [C::class, 'm'])`) y los mapas `T::class => [C::class]`.
- Registros de oyentes: una colección de referencias a clases del repo (`X.instance`, `X::class`, `X(..)`) definida en un miembro
  cuyo nombre denota oyentes (`listeners`, `subscribers`, `observers`, `subscribe`, `handlers`) o pasada a `observe/subscribe(X)`;
  cada clase es suscriptora del registro. Despacho por clave hacia métodos con el nombre de la clave (`dispatch('message.created')`
  -> `def message_created` de las clases registradas) y reparto en bucle (`for l in self.listeners(): l.publish(..)` -> `publish`
  de cada clase registrada, desde quien llama al método público que hace el reparto) (`registry_*`).
- Tipos del framework por herencia en el repo: una clase/atributo/anotación declarada en el repo que hereda (en cadena) de un tipo que
  Córtex reconoce (`class RestPostByIdAttribute : HttpPostAttribute`, `class UserAPIRouter(APIRouter)`, `@GetMapping @interface X`)
  se trata como ese tipo; un atributo de ruta propio cuya plantilla se construye con los parámetros del constructor
  (`Template = $"api/v{version}/{resource}"` + `: base(3, resource)`) aporta el prefijo con los valores de cada uso (`framework_alias`).
- SQL en ficheros de recursos: sentencias en elementos de un XML (`<select id="x">.. from t ..</select>`, `<sql>`, mappers) son nodos
  con aristas `data` a las tablas declaradas (como las consultas de un `.sql`), y las clases de entidad sin anotación (en carpetas
  `domain/entity/model`, o que heredan de una base `*Entity`/`*Model`) cuyo nombre en snake_case es una tabla del DDL del repo son
  sus modelos (`entity_tables`, `scan_xml_sql`).
- Consultas con nombre ligadas por etiqueta: un campo cuya etiqueta nombra una consulta de un `.sql` (`GetLists *sqlx.Stmt` con la
  etiqueta `query:"get-lists"`) es esa consulta; sus usos (`c.q.GetLists.Select(..)`) leen la consulta (`finish_query_fields`).
- Registro por referencia de función: una llamada de registro/planificación (`register_*`, `add_task`, `add_job`, `schedule*`,
  `every*`, `submit`, `on_startup`...) cuyos argumentos son referencias (no llamadas) a funciones del repo: cada función es un consumidor
  y el registro su productor (`funcref_*`).
- Mensajes que se manejan a sí mismos: una clase instanciada y pasada a una llamada de despacho (`notify(new X)`, `dispatch(new X)`,
  `X::dispatch()`) sin consumidor externo; su entrada son los métodos que comparte con las demás clases de su misma base (la plantilla
  que invoca el framework: `handle`, `toMail`...).
"""
import re
from collections import defaultdict

from .structural import IDENT_BACK, JOB_METHODS


class _Lazy:
    def __getattr__(self, name):
        from . import bridges
        value = getattr(bridges, name)
        setattr(self, name, value)
        return value


B = _Lazy()

# ---------------------------------------------------------------- bus de mensajes tipado
TB_LANGS = ('cs', 'java', 'kt', 'js', 'php', 'c')
TB_HEAD = re.compile(r'\b(?:class|record|struct|object)\s+(\w+)\s*(?:<[^>{]*>)?\s*(?:\([^)]*\))?\s*((?::|\bextends\b|\bimplements\b)[^{;]*)\{')
TB_GENERIC = re.compile(r'([A-Za-z_][\w.]*)\s*<\s*([A-Za-z_][\w.]*(?:\s*,\s*[A-Za-z_][\w.]*)?)\s*>')
TB_NEW = re.compile(r'(?<![\w$.])new\s+\\?(?:[\w.\\]+[.\\])?([A-Z]\w*|self|static)\s*(?:<[^<>()]*>)?\s*[({]')
TB_ASSIGNED = re.compile(r'(?:(?:\b(?:var|val|let|const|final|auto)\s+|\b[A-Z]\w*(?:<[^<>;=]*>)?\s+)([a-z_]\w*)|\$(\w+))\s*=\s*$')
TB_LOG_BACK = re.compile(r'(?i)(?:\blog\w*|logger|console|print\w*|debug|info|warn\w*|error|trace)\s*\.?\s*\w*\s*\([^()]*$')
TB_TYPEREF = re.compile(r'(?<![\w$.])(?:typeof\s*\(\s*(?:[\w.]+\.)?([A-Z]\w*)\s*\)|nameof\s*\(\s*(?:[\w.]+\.)?([A-Z]\w*)\s*\)|'
                        r'([A-Z]\w*)\s*(?:::class(?:\.java)?|\.class)\b)')
TB_DISPATCH = re.compile(r'(?i)^(?:publish|dispatch|push|send|emit|raise|fire|notify|post|enqueue|execute|trigger|broadcast|schedule|submit|'
                         r'queue|produce|handle|process)\w*$|(?:event|message|command|notification)s?(?:async)?$', re.I)
TB_GENERIC_METHOD = (
    re.compile(r'\b(\w+)\s*<\s*(\w+)\s*>\s*\(\s*(?:this\s+)?(?:in\s+)?(\w+)\s+@?\w+'),          # C#: Push<T>(T command)
    re.compile(r'<\s*(\w+)\b[^<>]*>\s*[\w<>\[\],.? ]+?\s+(\w+)\s*\(\s*(?:final\s+)?(\w+)\s+\w+'),  # Java: <T> void publish(T e)
    re.compile(r'\b(\w+)\s*<\s*(\w+)\b[^<>]*>\s*\(\s*\w+\s*:\s*(\w+)\b'),                      # TS/Kotlin: publish<T>(e: T)
)
TB_NOT_TYPE = {'String', 'Object', 'Integer', 'Long', 'Boolean', 'Void', 'Unit', 'Any', 'Exception', 'Task', 'List', 'Map', 'Set', 'Guid',
               'DateTime', 'Int32', 'Int64', 'Double', 'Decimal', 'JsonElement', 'HttpContext'}
TB_NOT_METHOD = {'if', 'for', 'foreach', 'while', 'switch', 'catch', 'return', 'new', 'using', 'lock', 'nameof', 'typeof', 'sizeof',
                 'when', 'fun', 'function', 'base', 'super', 'this', 'throw', 'await', 'yield', 'get', 'set'}


def tb_param_rx(lang, typ):
    t = re.escape(typ)
    if lang == 'php':
        return re.compile(rf'\bfunction\s+(\w+)\s*\(\s*(?:[\w\\]+\s*\|\s*)*\\?(?:\w+\\)*{t}\b(?:\s*\|\s*[\w\\]+)*\s+\$\w+')
    if lang in ('js', 'kt', 'c'):
        return re.compile(rf'\b(\w+)\s*\(\s*(?:(?:private|public|readonly|override|vararg)\s+)*\w+\s*:\s*(?:[\w.]+\.)?{t}\b(?!\s*[<.])')
    return re.compile(rf'\b(\w+)\s*\(\s*(?:@\w+(?:\([^)]*\))?\s+|\[[^\]]*\]\s*|final\s+|in\s+)*(?:[\w.]+\.)?{t}\??\s+@?\w+\s*[,)=]')


# ---------------------------------------------------------------- tipos del framework por herencia
ALIAS_PY_CLASS = re.compile(r'^[ \t]*class\s+(\w+)\s*\(([^)]*)\)\s*:', re.M)
ALIAS_CLASS = re.compile(r'\bclass\s+(\w+)\s*(?:<[^>{]*>)?\s*(?::|\bextends\b)\s*([\w.]+)')
ALIAS_JAVA_ANN = re.compile(r'((?:@\w+(?:\([^)]*\))?\s*)+)(?:public\s+)?@interface\s+(\w+)')
CS_TEMPLATE = re.compile(r'\bTemplate\s*=\s*\$"([^"]*)"')
CS_CTOR = r'\b{name}\s*\(([^)]*)\)\s*(?::\s*base\s*\(([^)]*)\))?'

# ---------------------------------------------------------------- SQL en recursos y entidades por nombre
XML_STMT = re.compile(r'<(select|insert|update|delete|sql)\b([^>]*)>([\s\S]*?)</\1\s*>', re.I)
MIG_TABLE = re.compile(r'''\b(?:[Cc]reate)(?:\s*\.\s*|_)?[Tt]able(?:ForModel|IfNotExists|_if_not_exists)?\s*\(\s*(?:name\s*:\s*)?["'](\w+)["']''')
MIG_RENAME = re.compile(r'''\bRename\s*\.\s*Table\s*\(\s*["'](\w+)["']\s*\)\s*\.\s*To\s*\(\s*["'](\w+)["']''')
TYPED_MAP = re.compile(r'''\b\w+\s*<\s*([A-Z]\w*)\s*>\s*\(\s*["'](\w+)["']\s*\)''')
XML_SQL_NAME = re.compile(r'(?i)mapper|mapping|sqlmap|quer(?:y|ies)|dao|/sql/|statements')
XML_TAG = re.compile(r'<[^>]*>|&lt;|&gt;|<!\[CDATA\[|\]\]>')
ENTITY_DIR = re.compile(r'(?i)(?:^|/)(?:domain|entity|entities|model|models|po|pojo|do|dataobject|bean|beans|record|records)/')
ENTITY_BASE = re.compile(r'(?:Entity|Model|Record|Do|DO|Po|PO)\b')

# ---------------------------------------------------------------- registros de oyentes
REG_NAMES = r'(?:_?get_?)?(?:all_?)?(listeners|subscribers|observers|subscribe|subscriptions|event_?handlers|handlers|observers_?list|listen)'
REG_DEF = re.compile(r'(?im)^[ \t]*(?:(?:protected|private|public|static|readonly|async|override)\s+)*(?:def\s+(?:self\.)?|function\s+|fn\s+|'
                     r'func\s+(?:\([^)]*\)\s*)?|get\s+)' + REG_NAMES + r'\b')
REG_ASSIGN = re.compile(r'(?im)^[ \t]*(?:(?:protected|private|public|static|readonly|const|let|var|val|final)\s+)*(?:self\.|this\.|@|\$)?'
                        + REG_NAMES + r'\s*(?::\s*[\w\[\]<>., |]+)?\s*(?:=|:)\s*(?:array\s*\(|\[|%[iw]?\[|\{|\(|listOf\(|List\.of\(|new\b)')
REG_CLASS_REF = re.compile(r'(?<![\w$.\\])\\?((?:[A-Z]\w*(?:::|\\|\.))*[A-Z]\w*)\s*(?:\.instance\b|::class\b|\.class\b|\.new\b|\(|(?=\s*[,\])}\n]))')
REG_OBSERVE = re.compile(r'(?<![\w$])(?:([A-Z]\w*)\s*(?:::|\.)\s*)?(observe|subscribe|addObserver|addListener|addSubscriber|register_?(?:listener|observer|subscriber))\s*\(\s*'
                         r'(?:new\s+)?\\?((?:[A-Z]\w*(?:::|\\|\.))*[A-Z]\w*)\s*(?:::class|\.class|\.instance|\(\s*\))?\s*\)')
TYPED_LISTEN = re.compile(r'(?:->|::|\.)\s*(?:listen|on|subscribe|addListener)\s*\(\s*\\?((?:\w+\\)*[A-Z]\w*)::class\s*,\s*([^;]+?)\)\s*;')
KEY_DISPATCH = re.compile(r'(?<![\w$])\w*(?:dispatch|publish|broadcast|emit|trigger|notify|fire|instrument)\w*\s*\(\s*', re.I)
FUNCREF_CALL = re.compile(r'(?<![\w$])(register_\w+|add_task|add_job|add_cron\w*|schedule_\w+|every_\w+|on_startup|on_shutdown|'
                          r'run_in_executor|start_soon|submit|add_periodic_task|AddFunc|AddJob)\s*\(')
SCHED_CALL = re.compile(r'(?i)(?:schedul\w*|cron\w*|\$schedule)\s*(?:->|\.|::)\s*(?:command|job|call|exec|add\w*|register\w*|run)\s*\(\s*')
CMD_NAME = re.compile(r'(?m)^[ \t]*(?:(?:protected|public|private|static)\s+)*(?:\$|self\.)?(?:signature|command_name|commandName|defaultName)'
                      r'\s*[:=]\s*[\'"]([\w:.\-]+)')
SELF_DISPATCH = re.compile(r'(?i)^(?:notify\w*|dispatch\w*|schedule|enqueue\w*|push)$')
URL_BUILDER_DEF = re.compile(r'(?:\bfunction\s+(\w+)\s*(?:<[^>]*>)?\s*\(\s*(\w+)[^)]*\)\s*(?::[^{]+)?|\b(?:const|let)\s+(\w+)\s*=\s*'
                             r'(?:<[^>]*>)?\s*\(\s*(\w+)[^)]*\)\s*(?::[^=]+)?=>)')
TB_STATIC = re.compile(r'(?<![\w$.\\])([A-Z]\w*)\s*(?:::|\.)\s*(dispatch|publish|emit|fire|broadcast|raise)\w*\s*\(')
REG_LOOP = (
    re.compile(r'\bfor\s+(\w+)\s+in\s+(?:self\.|this\.)?' + REG_NAMES + r'\b'),                       # Python
    re.compile(r'(?:self\.|@|this\.)?' + REG_NAMES + r'\b(?:\([^)]*\))?\s*\.\s*(?:each|forEach|map|for_each)\s*(?:\{\s*\|(\w+)\||\(\s*\(?(\w+))'),
    re.compile(r'\bforeach\s*\(\s*\$this->' + REG_NAMES + r'\s+as\s+\$(\w+)'),                       # PHP
    re.compile(r'\bfor\s*\(\s*(?:const|let|var|final|val)?\s*\w*\s*(\w+)\s*(?:of|in|:)\s*(?:this\.|self\.)?' + REG_NAMES + r'\b'),
)


def key_methods(key):
    """Nombres de método que derivan de una clave de evento (`message.created` -> `message_created`, `messageCreated`,
    `onMessageCreated`, `handleMessageCreated`, `on_message_created`)."""
    parts = [p for p in re.split(r'[.:/\-_ ]+', key) if p]
    if len(parts) < 2 or not all(re.fullmatch(r'[A-Za-z]\w*', p) for p in parts):
        return set()
    snake = '_'.join(p.lower() for p in parts)
    camel = parts[0].lower() + ''.join(p[:1].upper() + p[1:].lower() for p in parts[1:])
    pascal = camel[:1].upper() + camel[1:]
    return {snake, camel, f'on_{snake}', f'on{pascal}', f'handle{pascal}', f'handle_{snake}'}


class Generalized:
    def generalized_init(self):
        self.tb_handlers = defaultdict(list)   # tipo -> [(rel, línea de la clase, línea del G<T>, clase, método)]
        self.tb_sites = []                     # (tipo, rel, línea, llamada, propietario, es referencia de tipo)
        self.tb_generic = set()                # métodos genéricos del repo cuyo primer parámetro es su tipo genérico
        self.reg_members = []                  # (rel, línea, símbolo del registro, nombre del registro, clase registrada)
        self.reg_keys = []                     # (clave, rel, línea) de despachos por clave
        self.reg_loops = []                    # (clase propietaria, nombre del registro, método llamado sobre cada oyente, método del bucle)
        self.alias_bases, self.alias_cache, self.alias_texts = {}, {}, {}
        self.query_tags = []                   # (campo, nombre de consulta) de etiquetas de struct
        self.url_builders = set()              # funciones JS que devuelven su primer parámetro como prefijo (`buildUrl`)
        self.typed_tables = []                 # (rel, línea, tipo, tabla) de `Mapper.Entity<T>("Tabla")`
        self.cmd_names, self.cmd_sites = {}, []  # nombre de comando declarado en la clase -> clase; usos por nombre en planificadores

    # ------------------------------------------------------------ recogida

    def collect_generalized(self, rel, lang, text):
        if lang == 'js' and ('return' in text or '=>' in text):
            for m in URL_BUILDER_DEF.finditer(text):
                p = m.group(2) or m.group(4)
                body = text[m.end():m.end() + 400]
                if re.match(rf'''\s*(?:\{{[^{{}}]{{0,300}}?\breturn\s+)?(?:`\$\{{\s*{re.escape(p)}\s*\}}|{re.escape(p)}\s*\+|new\s+URL\(\s*{re.escape(p)}\b)''', body):
                    self.url_builders.add(m.group(1) or m.group(3))
        if 'igrat' in rel and ('able' in text):
            # tablas creadas por el DSL de una migración (`Create.TableForModel("Tags")`, `createTable('x')`) y renombradas
            for m in MIG_TABLE.finditer(text):
                self.table_decl(rel, text.count('\n', 0, m.start()) + 1, m.group(1), lang)
            for m in MIG_RENAME.finditer(text):
                self.renames[m.group(2).lower()].add(m.group(1).lower())
        if lang in ('cs', 'java', 'kt', 'js') and '>(' in text.replace(' ', ''):
            for m in TYPED_MAP.finditer(text):
                self.typed_tables.append((rel, text.count('\n', 0, m.start()) + 1, m.group(1), m.group(2), lang))
        if 'class' in text or '@interface' in text:
            if lang == 'py':
                for m in ALIAS_PY_CLASS.finditer(text):
                    bases = [b.strip().rsplit('.', 1)[-1] for b in m.group(2).split(',') if b.strip() and '=' not in b]
                    self.alias_bases.setdefault(m.group(1), bases)
            elif lang in ('cs', 'java', 'kt', 'js', 'php', 'c'):
                for m in ALIAS_CLASS.finditer(text):
                    self.alias_bases.setdefault(m.group(1), [m.group(2).rsplit('.', 1)[-1]])
                    if lang == 'cs' and m.group(1).endswith('Attribute'):
                        self.alias_texts[m.group(1)] = rel
                if lang in ('java', 'kt') and '@interface' in text:
                    for m in ALIAS_JAVA_ANN.finditer(text):
                        self.alias_bases.setdefault(m.group(2), re.findall(r'@(\w+)', m.group(1)))
        if lang in TB_LANGS and '<' in text:
            for rx in TB_GENERIC_METHOD:
                for m in rx.finditer(text):
                    g = m.groups()
                    name, tparam, ptype = (g[0], g[1], g[2]) if rx is not TB_GENERIC_METHOD[1] else (g[1], g[0], g[2])
                    if tparam == ptype and name not in TB_NOT_METHOD:
                        self.tb_generic.add(name)

    def scan_xml_sql(self, rel, text):
        """Sentencias SQL en elementos de un XML (mappers): un nodo por sentencia y aristas `data` a las tablas que nombra."""
        if self.is_test(rel) or len(text) > 2 * 1024 * 1024 or not re.search(r'<(?:select|insert|update|delete)\b', text, re.I):
            return
        mid = self.module(rel)
        ns = re.search(r'<mapper\b[^>]*\bnamespace\s*=\s*"([\w.]+)"', text)
        owner = ns.group(1).rsplit('.', 1)[-1] if ns else B.os.path.splitext(rel.rsplit('/', 1)[-1])[0]
        found = False
        for m in XML_STMT.finditer(text):
            idm = re.search(r'\bid\s*=\s*"([\w.\-]+)"', m.group(2))
            if not idm:
                continue
            body = XML_TAG.sub(lambda t: ' ' * len(t.group()) if '\n' not in t.group() else B.blanked(t.group()), m.group(3))
            if not (B.SQL_HEAD.match(body) or re.search(r'(?i)\b(?:select|from|insert\s+into|update|delete\s+from)\b', body)):
                continue
            if not mid:
                mid = self.g.node(f'm:{rel}', kind='module', name=rel.rsplit('/', 1)[-1], file=rel, line=1, lang='xml',
                                  end=text.count('\n') + 1, hash=B.digest(rel))
            line = text.count('\n', 0, m.start()) + 1
            end = text.count('\n', 0, m.end()) + 1
            nid = self.add_function(rel, f'{owner}.{idm.group(1)}', line, end)
            found = True
            for upper in (True, False):
                for t in B.SQL_TABLE[upper].finditer(body):
                    for target in self.sql_targets(t.group(1), rel):
                        if target != nid and self.g.nodes[target]['file'] != rel:
                            self.g.edge(nid, target, 'data')
        return found

    def load_xml_sql(self):
        """Ficheros XML de sentencias (mappers) que el análisis no incluye como código: versionados (o en el árbol si no hay git),
        con nombre o carpeta de consultas y elementos `<select|insert|update|delete>`."""
        for rel in self.all_files():
            if not rel.endswith('.xml') or rel in self.fileset or self.is_test(rel) or not XML_SQL_NAME.search(rel):
                continue
            try:
                path = self.root / rel
                if path.stat().st_size > 2 * 1024 * 1024:
                    continue
                text = path.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            self.scan_xml_sql(rel, text)

    def all_files(self):
        """Todos los ficheros del repo (versionados; sin git, el árbol sin carpetas ocultas ni de dependencias)."""
        cached = getattr(self, '_all_files', None)
        if cached is not None:
            return cached
        self.is_tracked('')
        pool = sorted(self.tracked) if self.tracked else []
        if not pool:
            for d, dirs, names in B.os.walk(self.root):
                dirs[:] = [x for x in dirs if not x.startswith('.') and x not in ('node_modules', 'target', 'build', 'dist', 'vendor')]
                rel = B.os.path.relpath(d, self.root).replace(B.os.sep, '/')
                pool += [(n if rel == '.' else f'{rel}/{n}') for n in names]
                if len(pool) > 50000:
                    break
        self._all_files = pool
        return pool

    def entity_tables(self):
        """Clases de entidad sin anotación de tabla cuyo nombre en snake_case (o su plural) es una tabla del DDL (`.sql`) del repo."""
        ddl = defaultdict(list)
        for key, nids in self.tables.items():
            for nid in nids:
                if (self.g.nodes[nid].get('file') or '').endswith('.sql') and not self.is_test(self.g.nodes[nid]['file']):
                    ddl[key].append(nid)
        declared = {k for k, nids in self.tables.items() if any(n in self.table_decls or (self.g.nodes[n].get('file') or '').endswith('.sql')
                                                              for n in nids)}
        declared |= set(self.renames)
        for rel, line, typ, table, lang in self.typed_tables:
            # `Mapper.Entity<Tag>("Tags")`: tipo del repo + literal que es una tabla declarada (migración o DDL)
            if table.lower() not in declared or self.is_test(rel):
                continue
            # la tabla con el mismo nombre exacto, declarada en DDL o en una migración del mismo lenguaje que la llamada
            fam = B.LANG_FAMILY.get(lang, lang)
            if table.lower() not in self.renames and not any(str(self.g.nodes[t].get('table')) == table and ((self.g.nodes[t].get('file') or '').endswith('.sql') or
                       B.LANG_FAMILY.get(B.EXT_LANG.get(B.os.path.splitext(self.g.nodes[t]['file'])[1]), '') == fam or
                       B.EXT_LANG.get(B.os.path.splitext(self.g.nodes[t]['file'])[1]) == lang) for t in self.tables.get(table.lower(), [])):
                continue
            cands = [n for n in self.short.get(typ, []) if self.g.nodes[n]['kind'] == 'class' and not self.is_test(self.g.nodes[n]['file'])
                     and B.EXT_LANG.get(B.os.path.splitext(self.g.nodes[n]['file'])[1]) == lang]
            cls = cands[0] if len(cands) == 1 else self.pick(rel, cands)
            if not cls:
                continue
            meta = self.g.nodes[cls]
            self.model_at(meta['file'], meta.get('line') or 1, typ, table, lang)
            own = self.owner(rel, line)
            if own and own != cls:
                self.g.edge(own, cls, 'data')
        if not ddl:
            return
        known = {k for (fam, k) in self.models}
        for rel, items in self.by_file.items():
            # clases de entidad de lenguajes de servidor (en JS/TS una clase homónima de una tabla suele ser otra cosa: un DTO, una regla)
            if self.is_test(rel) or not rel.endswith(('.java', '.kt', '.cs', '.py', '.php', '.go', '.rb', '.scala')):
                continue
            in_dir = bool(ENTITY_DIR.search(rel))
            for line, end, nid in items:
                meta = self.g.nodes[nid]
                if meta['kind'] != 'class' or meta.get('table') or '.' in meta['name']:
                    continue
                name = meta['name']
                if name in known or len([n for n in self.short.get(name, []) if self.g.nodes[n]['kind'] == 'class']) > 1:
                    continue  # ya es un modelo, o el nombre no identifica una única clase del repo
                if not in_dir and not any(ENTITY_BASE.search(b) for b in self.alias_bases.get(name, ())):
                    continue
                snake = B.snake(name).lower()
                cands = [t for key in (snake, B.plural_word(snake)) for t in ddl.get(key, []) if self.same_project(rel, self.g.nodes[t]['file'])]
                if not cands:
                    continue
                lang = B.EXT_LANG.get(B.os.path.splitext(rel)[1])
                self.model_at(rel, line, name, self.g.nodes[cands[0]].get('table') or snake, lang)

    def finish_query_fields(self):
        """Usos `x.Campo.` / `x.Campo(` de un campo ligado por etiqueta a una consulta con nombre -> nodo de la consulta."""
        if not self.query_tags:
            return
        fields = defaultdict(set)
        for field, name in self.query_tags:
            fields[field].update(e[0] for e in self.sqlc.get(name, ()))
        rx = re.compile(r'\.\s*(%s)\s*[.(]' % '|'.join(map(re.escape, sorted(fields, key=len, reverse=True))))
        for rel in self.files:
            if not rel.endswith('.go') or self.is_test(rel):
                continue
            text = self.text(rel)
            if not text or not rx.search(text):
                continue
            for m in rx.finditer(text):
                line = text.count('\n', 0, m.start()) + 1
                own = self.owner(rel, line)
                for nid in fields[m.group(1)]:
                    if own and own != nid:
                        self.g.edge(own, nid, 'data')

    def framework_alias(self, name, known, depth=0):
        """Nombre reconocido (`known`) al que llega `name` por la cadena de herencia del repo (`X` o `XAttribute` en C#)."""
        key = (name, id(known))
        if key in self.alias_cache:
            return self.alias_cache[key]
        found = None
        if depth < 5:
            for cand in (name, name + 'Attribute'):
                for base in self.alias_bases.get(cand, ()):
                    short = base[:-9] if base.endswith('Attribute') and base != 'Attribute' else base
                    if short in known or base in known:
                        found = short if short in known else base
                    else:
                        found = self.framework_alias(short, known, depth + 1)
                    if found:
                        break
                if found:
                    break
        self.alias_cache[key] = found
        return found

    def attribute_template(self, name, args):
        """Prefijo de ruta de un atributo propio cuya plantilla (`Template = $"api/v{version}/{resource}"`) se construye con los
        parámetros de su constructor, siguiendo `: base(..)` hasta la clase que la fija; `[controller]` queda para quien lo use."""
        cls, env = name + 'Attribute', {}
        values = [a.strip().strip('"') for a in args.split(',') if a.strip()] if args.strip() else []
        for _ in range(4):
            rel = self.alias_texts.get(cls)
            text = self.text(rel) if rel else None
            if not text:
                return None
            ctor = re.search(CS_CTOR.format(name=re.escape(cls)), text)
            params = []
            if ctor:
                for i, p in enumerate(x for x in ctor.group(1).split(',') if x.strip()):
                    pm = re.match(r'\s*[\w<>?\[\]]+\s+(\w+)\s*(?:=\s*(.+))?$', p)
                    if not pm:
                        continue
                    default = pm.group(2).strip().strip('"') if pm.group(2) else None
                    value = values[i] if i < len(values) else default
                    if value in env:
                        value = env[value]
                    params.append((pm.group(1), value))
            env = dict(params)
            tpl = CS_TEMPLATE.search(text[text.find(f'class {cls}'):])
            if tpl:
                return re.sub(r'\{(\w+)\}', lambda m: str(env.get(m.group(1)) or '{' + m.group(1) + '}'), tpl.group(1))
            if not ctor or not ctor.group(2):
                return None
            values = [env.get(a.strip(), a.strip().strip('"')) for a in ctor.group(2).split(',')]
            env = {}
            bases = self.alias_bases.get(cls) or []
            if not bases:
                return None
            cls = bases[0] if bases[0].endswith('Attribute') else bases[0] + 'Attribute'
        return None

    # ------------------------------------------------------------ recorrido

    def scan_generalized(self, src):
        if self.is_test(src.rel) or self.generated(src.rel):
            return
        if src.lang in TB_LANGS:
            self.typed_bus_handlers(src)
            self.typed_bus_sites(src)
        if src.lang in TB_LANGS + ('py', 'rb', 'go', 'ex', 'rs'):
            self.registry_scan(src)
            self.funcref_scan(src)
        if src.lang == 'js':
            self.jsc_scan(src)
        self.cfg_scan(src)
        self.go_scan(src)
        self.sqlid_scan(src)
        if src.lang == 'go' and self.sqlc and '`' in src.code:
            for m in re.finditer(r'(?m)^[ \t]*([A-Z]\w*)\s+[\w.*\[\]]+\s+`[^`\n]*\b\w+:"([\w\-]+)"', src.code):
                if m.group(2) in self.sqlc:
                    self.query_tags.append((m.group(1), m.group(2)))

    def typed_bus_handlers(self, src):
        """`class C : G<T>` (o `extends/implements G<T>`) con un método cuyo primer parámetro es `T`: consumidor de `T`."""
        s, rel = src.struct, src.rel
        if '<' not in s or 'class' not in s and 'record' not in s and 'object' not in s:
            return
        for m in TB_HEAD.finditer(s):
            bases = m.group(2)
            if '<' not in bases:
                continue
            own_params = set(re.findall(r'\w+', m.group(0)[:m.start(2) - m.start()].split(m.group(1), 1)[-1].split('(')[0]))
            types = []
            for g in TB_GENERIC.finditer(bases):
                for arg in g.group(2).split(','):
                    arg = arg.strip().rsplit('.', 1)[-1]
                    if arg[:1].isupper() and arg not in TB_NOT_TYPE and arg not in own_params and not re.fullmatch(r'T[A-Z]?\w{0,12}', arg):
                        types.append((arg, m.start(2) + g.start(), g.group(1).rsplit('.', 1)[-1]))
            if not types:
                continue
            brace = m.end() - 1
            end = src.close(brace)
            if end < 0:
                continue
            body = s[brace:end]
            cls_line = src.line(m.start(1))
            for typ, at, iface in types:
                for pm in tb_param_rx(src.lang, typ).finditer(body):
                    name = pm.group(1)
                    if name in TB_NOT_METHOD or name == m.group(1):
                        continue
                    line = src.line(brace + pm.start(1))
                    fn = f'f:{rel}:{m.group(1)}.{name}'
                    fn = fn if fn in self.g.nodes else self.decl_after(src, brace + pm.start(1), name)
                    if fn and self.g.nodes[fn]['kind'] in ('method', 'function'):
                        cls = self.owner(rel, cls_line)
                        self.tb_handlers[typ].append((rel, cls_line, src.line(at), cls, fn, line, iface))

    def typed_bus_sites(self, src):
        """Instancias `new T(..)` pasadas como argumento directo de una llamada y referencias de tipo (`typeof(T)`, `T.class`)."""
        s, code, rel = src.struct, src.code, src.rel
        if 'new' in s:
            for m in TB_NEW.finditer(code):
                enc = self.enclosing(src, m.start())
                assigned = TB_ASSIGNED.search(s, max(0, m.start() - 160), m.start())
                if assigned and (not enc or enc[2] == '{'):
                    # `var e = new T {..}; ...; bus.Publish(e)`: la variable se pasa después a una llamada en la misma función
                    own = self.owner(rel, src.line(m.start()))
                    meta = self.g.nodes.get(own) or {}
                    if meta.get('kind') in ('function', 'method') and meta.get('end'):
                        stop = src.nl[meta['end'] - 1] if meta['end'] - 1 < len(src.nl) else len(s)
                        var = re.escape(assigned.group(1) or assigned.group(2))
                        typ = self.tb_type(src, m)
                        rx_arg = rf'\b(\w+)\s*(?:<[^<>()]*>)?\s*\(\s*(?:[^();]*,\s*)?\$?{var}\b(?!\s*[=.(\[])'
                        rx_chain = rf'\b(\w+)\s*\(\s*\$?{var}\s*(?:->|\.)\s*\w+\s*\('  # `dispatch($job->delay(..))`
                        for c in list(re.finditer(rx_arg, s[m.end():stop])) + list(re.finditer(rx_chain, s[m.end():stop])):
                            if TB_DISPATCH.search(c.group(1)) or c.group(1) in self.tb_generic:
                                # la creación y la llamada de despacho (pueden estar en bloques distintos de la función)
                                self.tb_sites.append((typ, rel, src.line(m.start()), c.group(1), None, False))
                                self.tb_sites.append((typ, rel, src.line(m.end() + c.start()), c.group(1), None, False))
                    continue
                if not enc or enc[2] != '(':
                    continue
                if s[src.skip(enc[0] + 1):m.start()].strip(' \t\n,'):
                    # sólo el primer argumento o uno tras una coma: `Push(new X(..))`, `Publish(ctx, new X())`
                    prev = s[:m.start()].rstrip()
                    if not prev.endswith(','):
                        continue
                callee = IDENT_BACK.search(s, max(0, enc[0] - 120), enc[0])
                if not callee and s[:enc[0]].rstrip().endswith('('):  # `dispatch((new X(..))->delay(..))`
                    k = len(s[:enc[0]].rstrip()) - 1
                    callee = IDENT_BACK.search(s, max(0, k - 120), k)
                if not callee:
                    continue
                self.tb_sites.append((self.tb_type(src, m), rel, src.line(m.start()), callee.group(1), None, False))
        if 'chedul' in s or 'cron' in s.lower():
            for m in SCHED_CALL.finditer(code):
                line = src.line(m.start())
                ref = re.match(r'\\?(?:\w+\\)*([A-Z]\w*)\s*(?:::class|\.class)\b|typeof\s*\(\s*([A-Z]\w*)\s*\)', code[m.end():m.end() + 160])
                lit = src.literal(m.end())
                if ref:
                    self.tb_sites.append((self.php_alias(src, ref.group(1) or ref.group(2)), rel, line, 'schedule', None, False))
                elif lit and lit[0]:
                    self.cmd_sites.append((lit[0].split()[0], rel, line))
        if src.lang in ('php', 'py', 'js', 'rb') and ('signature' in s or 'ommand' in s or 'defaultName' in s):
            for m in CMD_NAME.finditer(code):
                own = self.g.nodes.get(self.owner(rel, src.line(m.start()))) or {}
                if own.get('kind') == 'class':
                    self.cmd_names.setdefault(m.group(1), own['name'].rsplit('.', 1)[-1])
        for m in TB_STATIC.finditer(s):
            self.tb_sites.append((self.php_alias(src, m.group(1)), rel, src.line(m.start()), m.group(2), None, False))
        if 'typeof' in s or 'nameof' in s or '.class' in s or '::class' in s:
            for m in TB_TYPEREF.finditer(code):
                typ = m.group(1) or m.group(2) or m.group(3)
                line = src.line(m.start())
                lead = s[s.rfind('\n', 0, m.start()) + 1:m.start()].lstrip()
                if lead.startswith(('[', '@', '#[')) or TB_LOG_BACK.search(s, max(0, m.start() - 80), m.start()):
                    continue  # atributos/anotaciones (`[JsonSerializable(typeof(X))]`) y mensajes de log
                self.tb_sites.append((typ, rel, line, '', self.owner(rel, line), True))

    def class_ref(self, src, name):
        """Clase del repo nombrada por `name` (`A::B`, `A\\B`, `a.B`): por el último segmento, desempatando por la ruta."""
        parts = [p for p in re.split(r'::|\\|\.', name) if p]
        if not parts:
            return None
        if src.lang == 'php' and len(parts) == 1 and parts[0] in self.php_uses(src):
            parts = [p for p in self.php_uses(src)[parts[0]].split('\\') if p]
        cands = [n for n in self.short.get(parts[-1], []) if self.g.nodes[n]['kind'] == 'class' and not self.is_test(self.g.nodes[n]['file'])]
        if len(cands) > 1 and len(parts) > 1:
            path = [B.snake(p).lower().replace('_', '') for p in parts[:-1]]
            score = lambda n: sum(1 for p in path if p in self.g.nodes[n]['file'].lower().replace('_', '').replace('-', ''))
            best = max(score(n) for n in cands)
            narrowed = [n for n in cands if score(n) == best and best > 0]
            cands = narrowed or cands
        return cands[0] if len(cands) == 1 else self.pick(src.rel, cands)

    def registry_scan(self, src):
        s, code, rel = src.struct, src.code, src.rel
        if re.search(REG_NAMES, s, re.I):
            for rx in (REG_DEF, REG_ASSIGN):
                for m in rx.finditer(s):
                    name = m.group(1)
                    line = src.line(m.start(1))
                    own = self.owner(rel, line)
                    meta = self.g.nodes.get(own) or {}
                    if rx is REG_DEF:
                        if meta.get('kind') not in ('method', 'function') or not meta.get('end'):
                            continue
                        start, stop = m.end(), src.nl[meta['end'] - 1] if meta['end'] - 1 < len(src.nl) else len(s)
                        holder = meta['name'].rsplit('.', 1)[0] if '.' in meta['name'] else meta['name']
                    else:
                        open_pos = m.end() - 1
                        while open_pos < len(s) and s[open_pos] not in '([{':
                            open_pos += 1
                        close = src.close(open_pos) if open_pos < len(s) else -1
                        if close < 0:
                            continue
                        start, stop = open_pos, close
                        holder = (meta.get('name') or rel).rsplit('.', 1)[0] if meta.get('kind') == 'method' else (meta.get('name') or rel)
                    body = code[start:stop]
                    if '=>' in body and '::class' in body and name in ('listen', 'listeners', 'handlers', 'event_handlers'):
                        self.typed_map(src, start, stop)
                        continue
                    if name == 'listen':
                        continue
                    for c in REG_CLASS_REF.finditer(body):
                        enc = self.enclosing(src, start + c.start())
                        if not enc or enc[2] != '[' and not re.search(r'(?:array|listOf|setOf|List\.of|Set\.of|arrayOf|list|tuple)\s*$',
                                                                        s[max(0, enc[0] - 12):enc[0]]):
                            continue  # sólo elementos de la lista del registro, no argumentos de otra llamada (`belongsToMany(User::class)`)
                        cls = self.class_ref(src, c.group(1))
                        if not cls or cls == own or self.g.nodes[cls]['file'] == rel and self.g.nodes[cls]['line'] == line:
                            continue
                        at = src.line(start + c.start())
                        self.reg_members.append((rel, at, self.owner(rel, at) or own, f'{holder}.{name}', cls, name))
            for rx in REG_LOOP:
                for m in rx.finditer(s):
                    var = next((g for g in m.groups()[1:] if g), None) if rx is not REG_LOOP[0] else m.group(1)
                    reg = m.group(2) if rx is REG_LOOP[0] else m.group(1)
                    if rx is REG_LOOP[2] or rx is REG_LOOP[3]:
                        var, reg = (m.group(2), m.group(1)) if rx is REG_LOOP[2] else (m.group(1), m.group(2))
                    if not var or not reg:
                        continue
                    own = self.owner(rel, src.line(m.start()))
                    meta = self.g.nodes.get(own) or {}
                    if meta.get('kind') != 'method':
                        continue
                    seg = s[m.end():m.end() + 600]
                    for call in re.finditer(rf'(?<![\w$]){re.escape(var)}\s*(?:\.|->)\s*(\w+)\s*\(', seg):
                        self.reg_loops.append((meta['name'].rsplit('.', 1)[0], reg, call.group(1), own))
        if 'bserv' in s or 'ubscri' in s or 'isten' in s or 'ttach' in s or 'egister' in s:
            for m in REG_OBSERVE.finditer(code):
                cls = self.class_ref(src, m.group(3))
                line = src.line(m.start())
                own = self.owner(rel, line)
                if cls and own and cls != own:
                    self.reg_members.append((rel, line, own, f'{m.group(1) or rel}.{m.group(2)}', cls, m.group(2)))
        if '::class' in s and src.lang == 'php':
            for m in TYPED_LISTEN.finditer(code):
                typ = self.php_alias(src, m.group(1).rsplit('\\', 1)[-1])
                line = src.line(m.start())
                h = m.group(2).strip()
                pair = re.fullmatch(r'\[\s*\\?((?:\w+\\)*\w+)::class\s*,\s*[\'"](\w+)[\'"]\s*\]', h)
                ref = re.fullmatch(r'\\?((?:\w+\\)*\w+)::class', h)
                at = re.fullmatch(r'[\'"]\\?((?:\w+\\)*\w+)@(\w+)[\'"]', h)
                name, method = (pair.group(1), pair.group(2)) if pair else (ref.group(1), None) if ref else (at.group(1), at.group(2)) if at else (None, None)
                if not name:
                    continue
                own = self.owner(rel, line)
                cls = (self.g.nodes.get(own) or {}).get('name', '').split('.')[0] if name in ('self', 'static') else None
                cls = self.class_ref(src, cls or name)
                if cls:
                    self.typed_handler_of(typ, cls, rel, line, method)
        if KEY_DISPATCH.search(s):
            for m in KEY_DISPATCH.finditer(s):
                key = src.expr(m.end())
                if key and '\0' not in key and re.fullmatch(r'[A-Za-z][\w]*(?:[.:/][A-Za-z]\w*)+', key):
                    self.reg_keys.append((key, rel, src.line(m.start())))

    def funcref_scan(self, src):
        """`SchedulerRegistry.register_daily(tasks.a, tasks.b)`, `bg.add_task(f, x)`, `c.AddFunc("@every 1m", f)`: cada argumento
        que es una referencia a una función/método del repo (no una llamada ni una clase)."""
        rel = src.rel
        for m in FUNCREF_CALL.finditer(src.struct):
            args, close = src.args(m.end() - 1)
            if close < 0:
                continue
            for a, b in args:
                text = src.code[a:b].strip()
                if not re.fullmatch(r'(?:self\.|this\.)?[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*', text) or text in ('self', 'this', 'None', 'null'):
                    continue
                line = src.line(a + len(src.code[a:b]) - len(src.code[a:b].lstrip()))
                node = self.ref_node(src, a, b, line)
                if not node or self.g.nodes[node]['kind'] not in ('function', 'method'):
                    continue
                own = self.owner(rel, line)
                if own == node:
                    continue
                topic, sym = self.job_topic(node)
                self.topic_uses.append((topic, rel, line, 'pub', own or '', 'mq'))
                meta = self.g.nodes[sym]
                self.topic_uses.append((topic, meta['file'], meta.get('line') or 1, 'sub', sym, 'mq'))

    def typed_map(self, src, start, stop):
        """`[T::class => [C::class, ..]]`: cada clase de la lista consume `T` (por su método con parámetro `T`, o `handle`)."""
        code = src.code
        for m in re.finditer(r'\\?((?:\w+\\)*[A-Z]\w*)::class\s*=>\s*\[([^\]]*)\]', code[start:stop]):
            typ = self.php_alias(src, m.group(1).rsplit('\\', 1)[-1])
            line = src.line(start + m.start())
            for c in re.finditer(r'\\?((?:\w+\\)*[A-Z]\w*)::class', m.group(2)):
                cls = self.class_ref(src, c.group(1))
                if cls:
                    self.typed_handler_of(typ, cls, src.rel, line)

    def php_uses(self, src):
        uses = getattr(src, 'php_uses', None)
        if uses is None:
            uses = src.php_uses = {}
            if src.lang == 'php':
                for m in re.finditer(r'^\s*use\s+([\w\\]+)(?:\s+as\s+(\w+))?\s*;', src.code, re.M):
                    uses[m.group(2) or m.group(1).rsplit('\\', 1)[-1]] = m.group(1)
        return uses

    def php_alias(self, src, name):
        """Nombre original de un alias PHP (`use A\\B\\Installed as ServerInstalledEvent;` -> `Installed`)."""
        return self.php_uses(src).get(name, name).rsplit('\\', 1)[-1]

    def typed_handler_of(self, typ, cls, rel, line, method=None):
        """Registro tipado: la clase `cls` (o su método `method`) consume `typ`; el registro en `rel:line` también."""
        meta = self.g.nodes[cls]
        methods = [n for n in self.owners.get(meta['name'], []) if self.g.nodes[n]['file'] == meta['file']]
        if method:
            pick = [n for n in methods if self.g.nodes[n]['name'].rsplit('.', 1)[-1] == method]
        else:
            text = self.text(meta['file']) or ''
            pick = [n for n in methods if tb_param_rx('php' if meta['file'].endswith('.php') else 'cs', typ).search(
                '\n'.join(text.split('\n')[(self.g.nodes[n].get('line') or 1) - 1:(self.g.nodes[n].get('line') or 1) + 3]))]
            pick = pick or [n for n in methods if self.g.nodes[n]['name'].rsplit('.', 1)[-1] in ('handle', '__invoke', 'Handle', 'handleEvent')]
        if not pick:
            return
        fn = pick[0]
        own = self.owner(rel, line)
        self.tb_handlers[typ].append((rel, line, line, own, fn, self.g.nodes[fn].get('line') or 1, 'registration'))

    def tb_type(self, src, m):
        """Tipo instanciado; `new self`/`new static` es la clase que contiene la llamada."""
        if m.group(1) not in ('self', 'static'):
            return self.php_alias(src, m.group(1))
        own = self.g.nodes.get(self.owner(src.rel, src.line(m.start()))) or {}
        return own.get('name', '').split('.')[0] if own.get('kind') == 'method' else ''

    # ------------------------------------------------------------ cierre

    def self_handling(self, pubs):
        """Clases despachadas sin consumidor externo: su entrada son los métodos que comparten con sus hermanas (misma base)."""
        for typ in [t for t in pubs if t not in self.tb_handlers]:
            cands = [n for n in self.short.get(typ, []) if self.g.nodes[n]['kind'] == 'class' and not self.is_test(self.g.nodes[n]['file'])]
            if len(cands) != 1:
                continue
            cls = cands[0]
            mine = {self.g.nodes[n]['name'].rsplit('.', 1)[-1]: n for n in self.owners.get(self.g.nodes[cls]['name'], [])}
            mine = {k: n for k, n in mine.items() if k not in ('__construct', '__init__', 'constructor', 'initialize', typ) and not k.startswith('_')}
            shared = {}
            for base in sorted(b for b in self.bases_of(typ) if b not in ('Object', 'object')):
                sib = [c for c in self.impls.get(base, ()) if c != typ]
                if not sib:
                    continue
                names = {k: sum(1 for c in sib if any(self.g.nodes[x]['name'].rsplit('.', 1)[-1] == k for x in self.owners.get(c, [])))
                         for k in mine}
                entry = {k: mine[k] for k, c in names.items() if c and k in JOB_METHODS}
                found = entry or {k: mine[k] for k, c in names.items() if c >= max(1, (len(sib) + 1) // 2)}
                if 0 < len(found) <= 2 and (not shared or len(found) < len(shared)):
                    shared = found
            if not shared:
                continue
            meta = self.g.nodes[cls]
            for n in shared.values():
                self.tb_handlers[typ].append((meta['file'], meta.get('line') or 1, meta.get('line') or 1, None, n,
                                              self.g.nodes[n].get('line') or 1, 'self'))

    def finish_registries(self):
        """Antes de `finish_topics`: registros de oyentes, despachos por clave y repartos en bucle."""
        members = defaultdict(set)
        for rel, line, sym, reg, cls, name in self.reg_members:
            members[reg].add(cls)
            self.topic_uses.append((reg, rel, line, 'pub', sym, 'mq'))
            meta = self.g.nodes[cls]
            self.topic_uses.append((reg, meta['file'], meta.get('line') or 1, 'sub', cls, 'mq'))
            same = [n for n in self.owners.get(meta['name'], []) if self.g.nodes[n]['name'].rsplit('.', 1)[-1] == name]
            if same:
                self.topic_uses.append((reg, meta['file'], self.g.nodes[same[0]].get('line') or 1, 'sub', same[0], 'mq'))
        registered = {c for cs in members.values() for c in cs}
        if not registered:
            return
        methods = defaultdict(list)
        for cls in registered:
            for n in self.owners.get(self.g.nodes[cls]['name'], []):
                methods[self.g.nodes[n]['name'].rsplit('.', 1)[-1]].append(n)
        for key, rel, line in self.reg_keys:
            subs = sorted({n for name in key_methods(key) for n in methods.get(name, [])})
            if not subs:
                continue
            self.topic_uses.append((key, rel, line, 'pub', '', 'mq'))
            for n in subs:
                self.topic_uses.append((key, self.g.nodes[n]['file'], self.g.nodes[n].get('line') or 1, 'sub', n, 'mq'))
        for holder, reg, called, loop_fn in self.reg_loops:
            regs = [r for r in members if r.rsplit('.', 1)[-1] == reg and r.rsplit('.', 1)[0].rsplit('.', 1)[-1] == holder.rsplit('.', 1)[-1]]
            targets = sorted({n for r in regs for c in members[r] for n in self.owners.get(self.g.nodes[c]['name'], [])
                              if self.g.nodes[n]['name'].rsplit('.', 1)[-1] == called})
            if not targets:
                continue
            topic = f'{holder}.{called}'
            for n in targets:
                self.topic_uses.append((topic, self.g.nodes[n]['file'], self.g.nodes[n].get('line') or 1, 'sub', n, 'mq'))
            for rel, line, sym in self.fanout_entries(holder, loop_fn):
                self.topic_uses.append((topic, rel, line, 'pub', sym, 'mq'))

    def fanout_entries(self, holder, loop_fn):
        """Métodos públicos de la clase que llegan (por `self.m`) al método del bucle, y sus llamadas desde otras clases cuando el
        nombre del método es único en el repo."""
        cls_methods = {self.g.nodes[n]['name'].rsplit('.', 1)[-1]: n for n in self.owners.get(holder, [])}
        reach, frontier = {loop_fn}, [loop_fn]
        while frontier:
            target = self.g.nodes[frontier.pop()]['name'].rsplit('.', 1)[-1]
            for name, n in cls_methods.items():
                if n in reach:
                    continue
                meta = self.g.nodes[n]
                body = '\n'.join((self.text(meta['file']) or '').split('\n')[(meta.get('line') or 1):meta.get('end') or 0])
                if re.search(rf'(?:self|this|@)\s*(?:\.|->)\s*{re.escape(target)}\b', body):
                    reach.add(n)
                    frontier.append(n)
        out = []
        hsnake = B.snake(holder.rsplit('.', 1)[-1]).lower()
        for n in reach:
            name = self.g.nodes[n]['name'].rsplit('.', 1)[-1]
            if name.startswith('_'):
                continue
            unique = len([x for x in self.short.get(name, []) if self.g.nodes[x]['kind'] == 'method']) == 1
            for rel, line, sym, recv in self.call_sites(name, self.g.nodes[n]['file']):
                recv = B.snake(recv).lower().strip('_')
                # nombre único en el repo, o receptor nombrado como la clase (`self.event_bus.dispatch` -> `EventBusService`)
                if unique or len(recv) >= 4 and (hsnake.startswith(recv) or recv == hsnake):
                    out.append((rel, line, sym))
        return out

    def call_sites(self, name, home):
        """Llamadas `x.name(` fuera del fichero `home` (búsqueda de texto en los ficheros de código del repo)."""
        rx = re.compile(rf'(\w*)\s*(?:\.|->)\s*{re.escape(name)}\s*\(')
        out = []
        for rel in self.files:
            if rel == home or self.is_test(rel) or not rel.endswith(B.CODE_EXTS):
                continue
            text = self.text(rel)
            if not text or name not in text:
                continue
            for m in rx.finditer(text):
                line = text.count('\n', 0, m.start()) + 1
                sym = self.owner(rel, line)
                if sym:
                    out.append((rel, line, sym, m.group(1)))
        return out


    def finish_generalized_events(self):
        """Antes de `finish_topics`: une productores y consumidores del bus tipado (sólo tipos con ambos lados)."""
        pubs, refs = defaultdict(list), []
        self.tb_sites += [(self.cmd_names[k], rel, line, 'schedule', None, False) for k, rel, line in self.cmd_sites if k in self.cmd_names]
        for typ, rel, line, callee, own, is_ref in self.tb_sites:
            handlers = self.tb_handlers.get(typ)
            if not handlers:
                if not is_ref and SELF_DISPATCH.match(callee):
                    pubs[typ].append((rel, line))  # candidato a mensaje que se maneja a sí mismo
                continue
            if is_ref:
                refs.append((typ, rel, line, own, handlers))
                continue
            if not (TB_DISPATCH.search(callee) or callee in self.tb_generic):
                continue
            pubs[typ].append((rel, line))
        # una interfaz genérica es un bus si consume varios tipos y alguno se despacha con una instancia; sólo entonces cuentan las
        # referencias de tipo (`typeof(T)` en un planificador) a los demás tipos que consume
        by_iface = defaultdict(set)
        for typ, items in self.tb_handlers.items():
            for h in items:
                by_iface[h[6]].add(typ)
        buses = {i for i, ts in by_iface.items() if len(ts) > 1 and ts & set(pubs)}
        for typ, rel, line, own, handlers in refs:
            if not any(h[6] in buses for h in handlers):
                continue
            if True:
                # referencia de tipo fuera de las clases que lo consumen (registro de un planificador, `TypeName = typeof(X)`)
                if own and any(own in (h[3], h[4]) or (self.g.nodes.get(own) or {}).get('name', '').split('.')[0] ==
                               (self.g.nodes.get(h[3]) or {}).get('name', '').split('.')[-1] for h in handlers):
                    continue
                if any(rel == h[0] for h in handlers):
                    continue
            pubs[typ].append((rel, line))
        self.self_handling(pubs)
        for typ, sites in pubs.items():
            if typ not in self.tb_handlers:
                continue
            for rel, line in sites:
                self.topic_uses.append((typ, rel, line, 'pub', '', 'mq'))
            for hrel, cls_line, at_line, cls, fn, fn_line, _ in self.tb_handlers[typ]:
                self.topic_uses.append((typ, hrel, fn_line, 'sub', fn, 'mq'))
                if cls and cls != fn:
                    self.topic_uses.append((typ, hrel, at_line, 'sub', cls, 'mq'))


# ---------------------------------------------------------------- clientes con URL construida por la instancia (JS/TS)
JSC_CLASS = re.compile(r'\bclass\s+([A-Za-z_$][\w$]*)\s*(?:<[^{]*?>)?\s*(?:extends\s+([A-Za-z_$][\w$.]*)\s*(?:<[^{]*?>)?)?\s*(?:implements\s+[^{]+)?\{')
JSC_MEMBER = re.compile(r'(?:^|[;}\n])[ \t]*(?:(?:public|private|protected|readonly|static|async|override|declare|abstract)\s+)*'
                        r'(get\s+|set\s+)?([A-Za-z_$][\w$]*)\s*(?:[!?])?\s*(\(|:|=)')
JSC_CALL = re.compile(r'(?<![\w$])((?:this\s*\.\s*)?[\w$]+(?:\s*\.\s*[\w$]+)*)\s*\.\s*(get|post|put|patch|delete|head)\s*(?:<(?:[^<>]|<[^<>]*>)*>)?\s*\(')
JSC_CLIENTISH = re.compile(r'(?i)http|axios|api|client|request|fetch|ajax|^\$')
JSC_CONST = re.compile(r'(?m)^[ \t]*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=\n]+)?=\s*')
JSC_DEFAULT_NEW = re.compile(r'\bexport\s+default\s+new\s+([A-Za-z_$][\w$]*)\s*\(')
JSC_LOCAL_NEW = re.compile(r'(?:\b(?:const|let|var)\s+|this\.)([A-Za-z_$][\w$]*)\s*(?::[^=;\n]+)?=\s*new\s+([A-Z][\w$]*)\s*\(')
JSC_MAX_ALTS = 4


def js_split(text, sep):
    """Divide `text` por el operador `sep` (`+`, `||`, `??`, `,`) sólo en el nivel superior (fuera de cadenas y paréntesis)."""
    out, depth, start, i, quote = [], 0, 0, 0, None
    n = len(text)
    while i < n:
        ch = text[i]
        if quote:
            if ch == '\\':
                i += 2
                continue
            if ch == quote:
                quote = None
            elif quote == '`' and text.startswith('${', i):
                j, d = i + 2, 1
                while j < n and d:
                    d += {'{': 1, '}': -1}.get(text[j], 0)
                    j += 1
                i = j
                continue
            i += 1
            continue
        if ch in '\'"`':
            quote = ch
        elif ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        elif depth == 0 and text.startswith(sep, i) and not (sep == '+' and (text.startswith('++', i) or i and text[i - 1] == '+')) \
                and not (sep == '?' and (text[i + 1:i + 2] in ('.', '?') or i and text[i - 1] == '?')) \
                and not (sep == ':' and (text[i + 1:i + 2] == ':' or i and text[i - 1] == ':')) \
                and not (sep == '=' and (text[i + 1:i + 2] in ('=', '>') or i and text[i - 1] in '=!<>')):
            out.append(text[start:i])
            start = i + len(sep)
            i += len(sep)
            continue
        i += 1
    out.append(text[start:])
    return out


def js_close(text, pos):
    """Índice del cierre que empareja la apertura en `pos` (respetando cadenas)."""
    depth, i, quote, n = 0, pos, None, len(text)
    while i < n:
        ch = text[i]
        if quote:
            if ch == '\\':
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in '\'"`':
            quote = ch
        elif ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def js_template_parts(body):
    """Partes de una plantilla: [('lit', texto) | ('expr', expresión)]."""
    out, i, last = [], 0, 0
    while True:
        j = body.find('${', i)
        if j < 0:
            out.append(('lit', body[last:]))
            return out
        k = js_close(body, j + 1)
        if k < 0:
            out.append(('lit', body[last:]))
            return out
        out.append(('lit', body[last:j]))
        out.append(('expr', body[j + 2:k]))
        i = last = k + 1


def js_arrow(text):
    """`(a, b) => expr` / `a => expr` / `function (a) { return expr }`: (parámetros, expresión de retorno) o None."""
    m = re.match(r'\s*(?:async\s+)?(?:\(([^()]*)\)|([A-Za-z_$][\w$]*))\s*(?::\s*[^=]+?)?\s*=>\s*', text)
    if not m:
        m2 = re.match(r'\s*(?:async\s+)?function\s*\w*\s*\(([^()]*)\)\s*(?::\s*[^{]+)?\{', text)
        if not m2:
            return None
        params, body = m2.group(1), text[m2.end() - 1:]
    else:
        params, body = m.group(1) if m.group(1) is not None else m.group(2), text[m.end():]
    names = [re.split(r'[\s:=?]', p.strip(), 1)[0] for p in (params or '').split(',') if p.strip()]
    body = body.strip()
    if body.startswith('{'):
        close = js_close(body, 0)
        return names, ('block', body[1:close] if close > 0 else body[1:])
    return names, ('expr', body)


class JsClassClients:
    """URLs construidas por la instancia de una clase cliente: campos (`baseRoute = routes.x`), parámetros del constructor fijados por
    la subclase (`super('agents', {..})` -> `this.resource`), getters (`get url()`), métodos auxiliares (`baseUrl()` con reasignaciones
    condicionales) y objetos de rutas del módulo (`routes.x(id)`). Las llamadas cliente de los métodos propios de una clase se resuelven
    en su contexto; las de métodos heredados, en cada llamada sobre una instancia de la subclase (`AgentAPI.get()` con
    `export default new Agents()`)."""

    def jsc_init(self):
        self.jsc_classes, self.jsc_consts, self.jsc_calls, self.jsc_instances, self.jsc_texts = {}, {}, [], [], {}

    def jsc_scan(self, src):
        code, rel = src.code, src.rel
        if self.is_test(rel) or self.generated(rel):
            return
        consts = {}
        for m in JSC_CONST.finditer(code):
            start = m.end()
            end = self.jsc_expr_end(code, start)
            consts[m.group(1)] = code[start:end].strip()
        if consts:
            self.jsc_consts[rel] = consts
        has_class = 'class' in code
        if has_class:
            for m in JSC_CLASS.finditer(src.struct):
                brace = m.end() - 1
                close = src.close(brace)
                if close < 0:
                    continue
                info = self.jsc_class(src, m.group(1), m.group(2), brace, close)
                self.jsc_classes.setdefault(m.group(1), []).append(info)
        for m in JSC_DEFAULT_NEW.finditer(code):
            self.jsc_instances.append(('default', rel, m.group(1)))
        if ('.get' in code or '.post' in code or '.put' in code or '.patch' in code or '.delete' in code):
            for m in JSC_CALL.finditer(src.struct):
                recv = re.sub(r'\s+', '', m.group(1))
                args, close = src.args(m.end() - 1)
                line = src.line(m.start())
                first = code[args[0][0]:args[0][1]].strip() if args else ''
                self.jsc_calls.append((rel, line, recv, m.group(2).upper(), first, src.struct[:m.start()].count('\n')))
        if 'new ' in code:
            for m in JSC_LOCAL_NEW.finditer(code):
                self.jsc_instances.append(('local', rel, m.group(2), m.group(1)))

    def jsc_expr_end(self, code, start):
        depth, i, quote, n = 0, start, None, len(code)
        while i < n:
            ch = code[i]
            if quote:
                if ch == '\\':
                    i += 2
                    continue
                if ch == quote:
                    quote = None
                i += 1
                continue
            if ch in '\'"`':
                quote = ch
            elif ch in '([{':
                depth += 1
            elif ch in ')]}':
                if depth == 0:
                    return i
                depth -= 1
            elif depth == 0 and (ch == ';' or ch == '\n' and not code[i + 1:i + 40].lstrip().startswith(('.', '?', ':', '+', '|', '&'))
                                 and not code[start:i].rstrip().endswith(('=>', '=', '+', '?', ':', '(', ',', '||', '&&'))):
                return i
            i += 1
        return n

    def jsc_class(self, src, name, base, brace, close):
        code, s = src.code, src.struct
        info = {'rel': src.rel, 'name': name, 'base': (base or '').rsplit('.', 1)[-1] or None, 'fields': {}, 'getters': {},
                'methods': {}, 'ctor': None, 'super': None, 'line': src.line(brace), 'end': src.line(close)}
        pos = brace + 1
        while pos < close:
            m = JSC_MEMBER.search(s, pos, close)
            if not m:
                break
            enc = self.enclosing(src, m.start(2))
            if not enc or enc[0] != brace:
                pos = m.end()
                continue
            getter, mname, kind = m.group(1), m.group(2), m.group(3)
            if kind == '(':
                pclose = src.close(m.end() - 1)
                if pclose < 0:
                    break
                bopen = s.find('{', pclose)
                if bopen < 0 or bopen > close or s[pclose + 1:bopen].strip() and not s[pclose + 1:bopen].strip().startswith(':'):
                    pos = pclose + 1
                    continue
                bclose = src.close(bopen)
                params = [re.split(r'[\s:=?]', p.strip(), 1)[0].lstrip('.') for p in code[m.end():pclose].split(',') if p.strip()]
                params = [p for p in params if p not in ('private', 'public', 'protected', 'readonly')] or params
                params = [re.sub(r'^(?:private|public|protected|readonly)\s+', '', p) for p in params]
                body = code[bopen + 1:bclose]
                if mname == 'constructor':
                    info['ctor'] = (params, body)
                    sm = re.search(r'\bsuper\s*\(', body)
                    if sm:
                        sclose = js_close(body, sm.end() - 1)
                        info['super'] = [a.strip() for a in js_split(body[sm.end():sclose], ',')] if sclose > 0 else None
                elif getter and getter.strip() == 'get':
                    info['getters'][mname] = body
                elif not getter:
                    info['methods'][mname] = (params, body, src.line(m.start(2)))
                pos = bclose + 1 if bclose > 0 else close
            elif kind in (':', '='):
                eq = m.end() - 1 if kind == '=' else None
                if kind == ':':
                    # `name: Tipo = valor` o declaración sin valor
                    seg_end = self.jsc_expr_end(code, m.end())
                    seg = code[m.end():seg_end]
                    k = js_split(seg, '=')
                    if len(k) > 1 and not seg.lstrip().startswith(('>', '=')):
                        info['fields'][mname] = '='.join(k[1:]).strip()
                    pos = seg_end + 1
                    continue
                end = self.jsc_expr_end(code, eq + 1)
                info['fields'][mname] = code[eq + 1:end].strip()
                pos = end + 1
            else:
                pos = m.end()
        return info

    # ------------------------------------------------------------ evaluación

    def jsc_find(self, cid):
        """Clase por identidad `(nombre, fichero)` (o sólo nombre si es único en el repo)."""
        name, rel = cid if isinstance(cid, tuple) else (cid, None)
        items = self.jsc_classes.get(name) or []
        if rel is not None:
            same = [c for c in items if c['rel'] == rel]
            if same:
                return same[0]
        return items[0] if len(items) == 1 else None

    def jsc_base(self, info):
        """Clase base declarada en el repo: la importada por el fichero de la subclase, la del mismo fichero o la única homónima."""
        base = info['base']
        items = self.jsc_classes.get(base) or [] if base else []
        if len(items) <= 1:
            return items[0] if items else None
        same = [c for c in items if c['rel'] == info['rel']]
        if same:
            return same[0]
        text = self.text(info['rel']) or ''
        spec = self.js_import_map(self.src(info['rel'], 'js', text)).get(base) if text else None
        trel = self.js_resolve_spec(info['rel'], spec[0]) if spec else None
        return next((c for c in items if c['rel'] == trel), None)

    def jsc_chain(self, cid, depth=0):
        """Clase y sus bases (de la más derivada a la base) que el repo declara; `cid` = `(nombre, fichero)`."""
        out, info = [], self.jsc_find(cid)
        while info and len(out) < 6 and info not in out:
            out.append(info)
            info = self.jsc_base(info)
        return out

    def jsc_eval(self, expr, ctx, env, depth=0):
        """Valores posibles (hasta 4) de una expresión de URL; `\\0` marca las partes desconocidas. `ctx` = (clase más derivada,
        fichero donde se evalúa la expresión)."""
        expr = (expr or '').strip().rstrip(';').strip()
        if depth > 16 or not expr:
            return ['\0']
        while expr.startswith('(') and js_close(expr, 0) == len(expr) - 1:
            expr = expr[1:-1].strip()
        parts = js_split(expr, '?')
        if len(parts) > 1 and not expr.startswith('?') and '?.' not in expr[:len(parts[0]) + 2]:
            rest = '?'.join(parts[1:])
            alt = js_split(rest, ':')
            if len(alt) >= 2:
                return (self.jsc_eval(':'.join(alt[:1]), ctx, env, depth + 1) +
                        self.jsc_eval(':'.join(alt[1:]), ctx, env, depth + 1))[:JSC_MAX_ALTS]
        for op in ('||', '??'):
            ors = js_split(expr, op)
            if len(ors) > 1:
                for o in ors:
                    vals = self.jsc_eval(o, ctx, env, depth + 1)
                    if any(v and v != '\0' for v in vals):
                        return vals
                return ['\0']
        plus = js_split(expr, '+')
        if len(plus) > 1:
            out = ['']
            for p in plus:
                vals = self.jsc_eval(p, ctx, env, depth + 1)
                out = [a + b for a in out for b in vals][:JSC_MAX_ALTS]
            return out
        if expr[0] in '\'"' and expr[-1] == expr[0] and len(expr) >= 2:
            return [expr[1:-1]]
        if expr[0] == '`' and expr[-1] == '`':
            out = ['']
            for kind, text in js_template_parts(expr[1:-1]):
                vals = [text] if kind == 'lit' else self.jsc_eval(text, ctx, env, depth + 1)
                out = [a + b for a in out for b in vals][:JSC_MAX_ALTS]
            return out
        return self.jsc_ref(expr, ctx, env, depth)

    def jsc_ref(self, expr, ctx, env, depth):
        m = re.match(r'(this|[A-Za-z_$][\w$]*)', expr)
        if not m:
            return ['\0']
        head, rest = m.group(1), expr[m.end():]
        cls, rel = ctx
        if head == 'this':
            seg = re.match(r'\s*\??\.\s*([A-Za-z_$][\w$]*)', rest)
            if not seg:
                return ['\0']
            name, rest = seg.group(1), rest[seg.end():]
            call = re.match(r'\s*\(', rest)
            if call:
                close = js_close(rest, call.end() - 1)
                args = [a for a in js_split(rest[call.end():close], ',') if a.strip()] if close > 0 else []
                vals = [self.jsc_eval(a, ctx, env, depth + 1) for a in args]
                found = self.jsc_member_call(cls, name, [v[0] for v in vals], depth)
                return self.jsc_tail(found, rest[close + 1:] if close > 0 else '', ctx, env, depth)
            found = self.jsc_member(cls, name, depth)
            return self.jsc_tail(found, rest, ctx, env, depth)
        if head in env:
            if rest.strip() and env.get(head + '\x01'):
                return self.jsc_tail(('expr', env[head + '\x01'], ctx, env), rest, ctx, env, depth)
            val = env[head]
            return [val if val is not None else '\0'] if not rest.strip() else ['\0']
        if env.get('\x02body') and not rest.strip():
            local = self.jsc_local(env['\x02body'], head, ctx, {k: v for k, v in env.items() if k != '\x02body'}, depth)
            if local is not None:
                return self.jsc_eval(local, ctx, {k: v for k, v in env.items() if k != '\x02body'}, depth + 1)
        value, vrel = self.jsc_const(rel, head)
        if value is None:
            return ['\0']
        return self.jsc_tail(('expr', value, (cls, vrel), {}), rest, ctx, env, depth)

    def jsc_tail(self, found, rest, ctx, env, depth):
        """Aplica `.prop` y `(args)` a un valor encontrado (expresión, objeto literal o función flecha)."""
        if not found:
            return ['\0']
        kind, value, vctx, venv = found
        rest = rest.strip()
        while rest:
            seg = re.match(r'\??\.\s*([A-Za-z_$][\w$]*)', rest)
            call = re.match(r'\(', rest)
            if seg:
                obj = value.strip()
                if not obj.startswith('{'):
                    ref = self.jsc_deref(obj, vctx, venv, depth)
                    if not ref:
                        return ['\0']
                    obj, vctx, venv = ref
                    if not obj.startswith('{'):
                        return ['\0']
                prop = self.jsc_prop(obj, seg.group(1))
                if prop is None:
                    return ['\0']
                value, rest = prop, rest[seg.end():].strip()
            elif call:
                close = js_close(rest, 0)
                args = [a for a in js_split(rest[1:close], ',') if a.strip()] if close > 0 else []
                vals = [self.jsc_eval(a, ctx, env, depth + 1)[0] for a in args]
                fn = js_arrow(value)
                if not fn:
                    ref = self.jsc_deref(value.strip(), vctx, venv, depth)
                    fn = js_arrow(ref[0]) if ref else None
                    if ref:
                        vctx, venv = ref[1], ref[2]
                if not fn:
                    return ['\0']
                params, (bkind, body) = fn
                venv = {**venv, **{p: (vals[i] if i < len(vals) else None) for i, p in enumerate(params)}}
                value = body if bkind == 'expr' else self.jsc_returned(body, vctx, venv, depth)
                if value is None:
                    return ['\0']
                rest = rest[close + 1:].strip() if close > 0 else ''
            else:
                return ['\0']
        return self.jsc_eval(value, vctx, venv, depth + 1)

    def jsc_deref(self, expr, ctx, env, depth):
        """Una referencia (`routes`, `routes.x`, `this.f`) a la expresión que la define."""
        m = re.fullmatch(r'(this\s*\.\s*)?([A-Za-z_$][\w$]*)((?:\s*\.\s*[A-Za-z_$][\w$]*)*)', expr.strip())
        if not m or depth > 8:
            return None
        if m.group(1):
            found = self.jsc_member(ctx[0], m.group(2), depth)
            if not found or found[0] != 'expr':
                return None
            value, vctx, venv = found[1], found[2], found[3]
        else:
            value, vrel = self.jsc_const(ctx[1], m.group(2))
            if value is None:
                return None
            vctx, venv = (ctx[0], vrel), {}
        for p in re.findall(r'[A-Za-z_$][\w$]*', m.group(3) or ''):
            obj = value.strip()
            if not obj.startswith('{'):
                ref = self.jsc_deref(obj, vctx, venv, depth + 1)
                if not ref:
                    return None
                obj, vctx, venv = ref
            value = self.jsc_prop(obj, p)
            if value is None:
                return None
        return value.strip(), vctx, venv

    def jsc_prop(self, obj, prop):
        obj = obj.strip()
        if not obj.startswith('{'):
            return None
        close = js_close(obj, 0)
        for item in js_split(obj[1:close if close > 0 else len(obj)], ','):
            km = re.match(r'\s*["\']?([A-Za-z_$][\w$]*)["\']?\s*(:|\()', item)
            if km and km.group(1) == prop:
                if km.group(2) == '(':  # método abreviado `x(id) { return .. }`
                    return 'function ' + item.strip()
                return item[km.end():].strip()
            if item.strip() == prop:
                return prop
        return None

    def jsc_const(self, rel, name):
        """Constante del módulo (o importada de otro fichero del repo): (expresión, fichero)."""
        consts = self.jsc_consts.get(rel) or {}
        if name in consts:
            return consts[name], rel
        imports = self.js_imports.get(rel)
        if imports is None:
            text = self.text(rel) or ''
            imports = self.js_import_map(self.src(rel, 'js', text)) if text else {}
        spec = imports.get(name)
        if spec:
            trel = self.js_resolve_spec(rel, spec[0])
            if trel:
                orig = spec[1] or name
                value = (self.jsc_consts.get(trel) or {}).get(orig)
                if value is not None:
                    return value, trel
        return None, rel

    def jsc_member(self, cls, name, depth):
        """`this.name` en una instancia de `cls`: campo, asignación del constructor (con los argumentos de `super(..)` de la subclase)
        o getter, buscando de la clase más derivada a la base."""
        chain = self.jsc_chain(cls)
        envs = self.jsc_ctor_envs(chain, depth)
        for i, k in enumerate(chain):
            if name in k['fields']:
                return ('expr', k['fields'][name], (cls, k['rel']), {})
            if k['ctor']:
                params, body = k['ctor']
                am = None
                for am in re.finditer(rf'\bthis\s*\.\s*{re.escape(name)}\s*=(?!=)\s*', body):
                    pass
                if am:
                    end = self.jsc_expr_end(body, am.end())
                    return ('expr', body[am.end():end].strip(), (cls, k['rel']), envs[i])
            if name in k['getters']:
                value = self.jsc_returned(k['getters'][name], (cls, k['rel']), envs[i], depth)
                if value is not None:
                    return ('expr', value, (cls, k['rel']), envs[i])
            if name in k['methods']:
                return ('method', k['methods'][name], (cls, k['rel']), envs[i])
        return None

    def jsc_member_call(self, cls, name, args, depth):
        found = self.jsc_member(cls, name, depth)
        if not found:
            return None
        kind, value, vctx, venv = found
        if kind == 'method':
            params, body, _ = value
            venv = {**venv, **{p: (args[i] if i < len(args) else None) for i, p in enumerate(params)}}
            ret = self.jsc_returned(body, vctx, venv, depth)
            return ('expr', ret, vctx, venv) if ret is not None else None
        fn = js_arrow(value)
        if not fn:
            ref = self.jsc_deref(value, vctx, venv, depth)
            if not ref:
                return None
            value, vctx, venv = ref
            fn = js_arrow(value)
            if not fn:
                return None
        params, (bkind, body) = fn
        venv = {**venv, **{p: (args[i] if i < len(args) else None) for i, p in enumerate(params)}}
        ret = body if bkind == 'expr' else self.jsc_returned(body, vctx, venv, depth)
        return ('expr', ret, vctx, venv) if ret is not None else None

    def jsc_ctor_envs(self, chain, depth):
        """Entorno de los parámetros del constructor de cada clase de la cadena, a partir de los `super(..)` de la subclase."""
        envs = [{} for _ in chain]
        for i in range(1, len(chain)):
            sub, k = chain[i - 1], chain[i]
            if not k['ctor'] or not sub['super']:
                continue
            params = k['ctor'][0]
            env = {}
            for j, p in enumerate(params):
                if j < len(sub['super']):
                    arg = sub['super'][j]
                    if arg.strip().startswith('{'):
                        env[p] = None
                        env[p + '\x01'] = arg.strip()
                    else:
                        vals = self.jsc_eval(arg, ((chain[0]['name'], chain[0]['rel']), sub['rel']), envs[i - 1], depth + 1)
                        env[p] = vals[0] if vals and vals[0] != '\0' else None
            envs[i] = env
        return envs

    def jsc_returned(self, body, ctx, env, depth):
        """Expresión devuelta por un cuerpo; una variable local devuelta se sustituye por su valor (`jsc_local`)."""
        rets = list(re.finditer(r'\breturn\s+', body))
        if not rets:
            return None
        exprs = []
        for r in rets:
            expr = body[r.end():self.jsc_expr_end(body, r.end())].strip()
            if re.fullmatch(r'[A-Za-z_$][\w$]*', expr):
                local = self.jsc_local(body[:r.start()], expr, ctx, env, depth)
                expr = local if local is not None else expr
            if expr not in exprs:
                exprs.append(expr)
        if len(exprs) > 1:
            # varios `return`: alternativas, sin la cadena vacía de un caso por defecto (`return ''`)
            exprs = [e for e in exprs if e not in ("''", '""', '``', 'null', 'undefined')] or exprs
            out = exprs[-1]
            for e in reversed(exprs[:-1]):
                out = f'__alt__ ? ({e}) : ({out})'
            return out
        return exprs[0]

    def jsc_local(self, body, name, ctx, env, depth):
        """Valor de una variable local en `body`: su declaración y las reasignaciones posteriores (`v = ..`, `v += ..`); una
        reasignación dentro de un `if (cond)` se aplica si la condición es cierta, se omite si es falsa (parámetro nulo o ausente,
        opción que el objeto no define) y si no se sabe da dos alternativas."""
        decl = None
        for decl in re.finditer(rf'\b(?:let|var|const)\s+{re.escape(name)}\s*(?::[^=;]+)?=(?!=)\s*', body):
            pass
        if not decl:
            return None
        value = body[decl.end():self.jsc_expr_end(body, decl.end())].strip()
        for am in re.finditer(rf'(?<![\w$.]){re.escape(name)}\s*(\+?)=(?![=>])\s*', body[decl.end():]):
            at = decl.end() + am.end()
            new = body[at:self.jsc_expr_end(body, at)].strip()
            new = f'({value}) + ({new})' if am.group(1) else re.sub(rf'(?<![\w$.]){re.escape(name)}(?![\w$])', lambda _: f'({value})', new)
            truth = self.jsc_condition(body, decl.end() + am.start(), ctx, env, depth)
            if truth is True:
                value = new
            elif truth is None:
                value = f'__alt__ ? ({value}) : ({new})'
        return value

    def jsc_condition(self, body, pos, ctx, env, depth):
        """Verdad de la condición del `if` que encierra `pos` (True/False/None si no se sabe o no hay `if`)."""
        head = body[:pos]
        for m in reversed(list(re.finditer(r'\bif\s*\(', head))):
            close = js_close(body, m.end() - 1)
            if close < 0 or close > pos:
                continue
            after = body[close + 1:pos]
            if after.strip().startswith('{'):
                block = js_close(body, close + 1 + after.index('{'))
                if block > 0 and block < pos:
                    continue
            elif ';' in after or '\n' in after.strip():
                continue
            return self.jsc_truth(body[m.end():close], ctx, env, depth)
        return True

    def jsc_truth(self, cond, ctx, env, depth):
        parts = js_split(cond, '&&')
        if len(parts) > 1:
            vals = [self.jsc_truth(p, ctx, env, depth) for p in parts]
            return False if False in vals else (True if all(v is True for v in vals) else None)
        c = cond.strip()
        m = re.fullmatch(r'(!?)\s*((?:this\.)?[A-Za-z_$][\w$]*(?:\??\.[A-Za-z_$][\w$]*)*)(?:\s*(!==?|===?)\s*(null|undefined))?', c)
        if not m:
            return None
        ref = m.group(2).replace('?.', '.')
        head = ref.split('.')[0]
        if head in env and '.' not in ref:
            val = env[head]
            present = val is not None and val != ''
        else:
            vals = self.jsc_eval(ref, ctx, env, depth + 1)
            if vals == ['\0'] and self.jsc_absent(ref, ctx, env, depth):
                present = False
            elif vals and vals[0] not in ('\0', ''):
                present = True
            else:
                return None
        if m.group(3):
            present = present if m.group(3).startswith('!') else not present
        return not present if m.group(1) else present

    def jsc_absent(self, ref, ctx, env, depth):
        """`this.options.flag` u `opts.flag` sobre un objeto literal conocido que no define `flag`."""
        bits = ref.split('.')
        if len(bits) < 2:
            return False
        obj = None
        if bits[0] in env and env.get(bits[0] + '\x01'):
            obj = env[bits[0] + '\x01']
        elif bits[0] == 'this' and len(bits) == 3:
            member = self.jsc_member(ctx[0], bits[1], depth)
            if member and member[0] == 'expr':
                value = member[1].strip()
                obj = value if value.startswith('{') else member[3].get(value + '\x01')
        else:
            found = self.jsc_deref('.'.join(bits[:-1]), ctx, env, depth)
            obj = found[0] if found else None
        return bool(obj) and obj.strip().startswith('{') and self.jsc_prop(obj, bits[-1]) is None

    # ------------------------------------------------------------ cierre

    def finish_class_clients(self):
        if not self.jsc_classes or not self.jsc_calls:
            return
        by_file = defaultdict(list)
        for items in self.jsc_classes.values():
            for info in items:
                by_file[info['rel']].append(info)
        subclasses = defaultdict(set)
        for items in self.jsc_classes.values():
            for info in items:
                cid = (info['name'], info['rel'])
                for c in self.jsc_chain(cid)[1:]:
                    subclasses[(c['rel'], c['name'])].add(cid)
        # métodos de clase con llamadas cliente: (fichero, clase, método) -> [(verbo, expresión, línea)]
        client_methods = defaultdict(list)
        for rel, line, recv, verb, first, _ in self.jsc_calls:
            if not JSC_CLIENTISH.search(recv.rsplit('.', 1)[-1]) or not first:
                continue
            info = next((c for c in by_file.get(rel, []) if c['line'] <= line <= c['end']), None)
            if not info:
                if re.match(r'[A-Za-z_$][\w$]*\s*\.\s*[A-Za-z_$]', first) and not first.startswith('this'):
                    # objeto de rutas del módulo (`routes.x`, `routes.x(id)`) fuera de una clase
                    for v in self.jsc_eval(first, ('', rel), {}, 0):
                        self.jsc_emit(rel, line, verb, v)
                continue
            meth = max(((l, n) for n, (p, b, l) in info['methods'].items() if l <= line), default=(0, None))[1]
            if not meth or 'this' not in first and not re.match(r'[A-Za-z_$][\w$]*\s*\.\s*[A-Za-z_$]', first):
                continue
            client_methods[(rel, info['name'], meth)].append((verb, first, line))
        # un método que delega en otro método cliente de la misma clase (`get(cache) { return this.getFromNetwork() }`)
        for _ in range(2):
            for items in self.jsc_classes.values():
                for info in items:
                    for meth, (params, body, _) in info['methods'].items():
                        if (info['rel'], info['name'], meth) in client_methods:
                            continue
                        for c in re.finditer(r'\bthis\s*\.\s*([A-Za-z_$][\w$]*)\s*\(', body):
                            calls = client_methods.get((info['rel'], info['name'], c.group(1)))
                            if calls and c.group(1) != meth:
                                client_methods[(info['rel'], info['name'], meth)] = list(calls)
                                break
        for (rel, cls, meth), calls in client_methods.items():
            if subclasses.get((rel, cls)):
                continue  # clase base: sus llamadas se resuelven en cada instancia de una subclase
            info = next(c for c in by_file[rel] if c['name'] == cls)
            params, body, _ = info['methods'][meth]
            env = {**{p: '\0' for p in params}, '\x02body': body}
            for verb, first, line in calls:
                for v in self.jsc_eval(first, ((cls, rel), rel), env, 0):
                    self.jsc_emit(rel, line, verb, v)
        # llamadas a métodos heredados sobre instancias de una subclase
        inherited = defaultdict(dict)
        for (rel, cls, meth), calls in client_methods.items():
            info = next(c for c in by_file[rel] if c['name'] == cls)
            for sub in subclasses.get((rel, cls), ()):
                if not any(meth in c['methods'] for c in self.jsc_chain(sub) if c is not info and self.jsc_chain(sub).index(c) <
                           self.jsc_chain(sub).index(info)):
                    inherited[sub][meth] = (info, calls)
        if not inherited:
            return
        instances = defaultdict(dict)
        for item in self.jsc_instances:
            # identidad de la clase instanciada: la del mismo fichero, la importada o la única homónima
            info = self.jsc_find((item[2], item[1])) if any(c['rel'] == item[1] for c in self.jsc_classes.get(item[2], [])) else None
            if info is None:
                text = self.text(item[1]) or ''
                spec = self.js_import_map(self.src(item[1], 'js', text)).get(item[2]) if text else None
                trel = self.js_resolve_spec(item[1], spec[0]) if spec else None
                info = self.jsc_find((item[2], trel)) if trel else self.jsc_find(item[2])
            if info is None:
                continue
            cid = (info['name'], info['rel'])
            if item[0] == 'default':
                instances[item[1]]['default'] = cid
            else:
                instances[item[1]][item[3]] = cid
        for rel in self.files:
            if self.is_test(rel) or not rel.endswith(('.js', '.ts', '.jsx', '.tsx', '.vue', '.mjs', '.svelte')):
                continue
            text = self.text(rel)
            if not text:
                continue
            names = {var: cls for var, cls in instances.get(rel, {}).items() if var != 'default' and cls in inherited}
            if 'import' in text or 'require' in text:
                for alias, (spec, orig) in self.js_import_map(self.src(rel, 'js', text)).items():
                    trel = self.js_resolve_spec(rel, spec)
                    if trel and orig is None and instances.get(trel, {}).get('default') in inherited:
                        names[alias] = instances[trel]['default']
            for var, cls in names.items():
                for m in re.finditer(rf'(?<![\w$.]){re.escape(var)}\s*\.\s*([A-Za-z_$][\w$]*)\s*\(', text):
                    if m.group(1) not in inherited[cls]:
                        continue
                    base, calls = inherited[cls][m.group(1)]
                    line = text.count('\n', 0, m.start()) + 1
                    params, body, _ = base['methods'][m.group(1)]
                    env = {**{p: '\0' for p in params}, '\x02body': body}
                    for verb, first, _ in calls:
                        for v in self.jsc_eval(first, (cls, base['rel']), env, 0):
                            self.jsc_emit(rel, line, verb, v)

    def jsc_emit(self, rel, line, verb, value):
        if not value or '/' not in value or '__alt__' in value:
            return
        tail = re.sub(r'[/\x00]+$', '', value) if value.rstrip('/').endswith('\0') else None
        if tail is not None and len([x for x in re.sub(r'^[^/]*\x00', '', tail).split('/') if x and '\0' not in x]) < 2:
            return  # sólo un prefijo conocido seguido de una parte desconocida (`${this.baseUrl}${method}`): no es una ruta
        path = B.client_path(value)
        if path is None or not any(s != ':' for s in B.segments(path)):
            return
        sym = self.owner(rel, line)
        if sym:
            item = (rel, line, verb if verb in B.VERBS else 'ANY', path, sym)
            self.clients.append(item)
            if value.startswith('\0'):
                self.based.add(item)


# ---------------------------------------------------------------- claves de configuración y tipos ligados a una sección
CFG_FILE = re.compile(r'(?i)(?:^|/)(?:[\w.-]*(?:config|settings|application|appsettings|bootstrap|generator)[\w.-]*\.(?:ya?ml|toml|properties|json)|'
                      r'(?:config|conf|configs|resources|settings)/[\w.-]+\.(?:ya?ml|toml|properties)|[\w.-]+\.(?:toml|properties))'
                      r'(?:\.(?:sample|example|dist|template|default|tmpl))?$')
CFG_SKIP = re.compile(r'(?i)(?:^|/)(?:docker-compose|compose\.|package(?:-lock)?\.json|tsconfig|jsconfig|composer\.|\.eslintrc|\.prettierrc|'
                      r'renovate|tslint|nx\.json|project\.json|angular\.json|turbo\.json|vercel\.json|lerna\.json|babel|\.github/|'
                      r'cargo\.toml|pyproject\.toml|pubspec|pnpm-|yarn|launchsettings|manifest\.json|openapi|swagger|\.vscode/|locale|i18n|lang/)')
CFG_KEY_LIT = re.compile(r'''(["'])((?:[A-Za-z][\w\-]*)(?:[.:][A-Za-z_][\w\-]*)+)\1''')
CFG_VALUE_ANN = re.compile(r'''\$\{([A-Za-z][\w.\-]*)(?::[^}]*)?\}''')
CFG_PREFIX_ANN = re.compile(r'''@(?:ConfigurationProperties|ConfigMapping|ConfigurationProperties)\s*\(\s*(?:(?:prefix|value)\s*=\s*)?"([\w.\-]+)"''')
CFG_COND_ANN = re.compile(r'''@ConditionalOnProperty\s*\(([^)]*)\)''')
CFG_READ_CALL = re.compile(r'''(?i)(?:get\w*|string\w*|int\w*|bool\w*|float\w*|duration\w*|strings|value|property|exists|isset|lookup|'''
                           r'''must\w*|require\w*|config|setting\w*|env|param\w*|option\w*)\s*(?:<[^<>()]*>)?\s*\(\s*$''')
CS_BIND = re.compile(r'''\bConfigure\s*<\s*([A-Z]\w*)\s*>\s*\(\s*[\w.]*GetSection\s*\(\s*"([\w:.]+)"\s*\)|'''
                     r'''\bGetSection\s*\(\s*"([\w:.]+)"\s*\)\s*\.\s*(?:Get|Bind)\s*<\s*([A-Z]\w*)\s*>|'''
                     r'''\bAddOptions\s*<\s*([A-Z]\w*)\s*>\s*\(\s*\)\s*\.\s*(?:Bind|BindConfiguration)\s*\(\s*(?:\w+\.GetSection\s*\(\s*)?"([\w:.]+)"''')
GO_BIND = re.compile(r'''\b\w+\s*\.\s*Unmarshal(?:Key|WithConf)?\s*\(\s*"([\w.\-]+)"\s*,\s*&\s*([\w.]+)''')
ENV_PREFIX = re.compile(r'''\b(?:\w+\.)?(?:Provider\w*|AddEnvironmentVariables|SetEnvPrefix|EnvPrefix|env_prefix|envPrefix)\s*(?:\(|=|:)\s*'''
                        r'''(?:prefix\s*:\s*)?["']([A-Z][A-Z0-9]*_?)["']''')


def cfg_norm(key):
    return re.sub(r'[^A-Z0-9]+', '_', key.replace('-', '').upper()).strip('_')


class ConfigKeys:
    """Claves de configuración: un literal con forma de clave (`"db.host"`, `${xss.enabled}`, `"Radarr:Server"`) en un contexto de
    lectura, o un tipo ligado a una sección (`Configure<T>(GetSection("A:B"))`, `@ConfigurationProperties(prefix = "a")`,
    `ko.Unmarshal("db", &c)`, cuyos campos/propiedades son las claves `sección.campo`), frente a la clave escrita en un fichero de
    configuración del repo (YAML/TOML/properties/JSON, también `.sample`/`.example`) o, si ninguno la define, frente al propio campo.
    Las variables de entorno con el prefijo de un proveedor (`env.Provider("APP_", "__")`) y la convención `SECCION__CLAVE` son la
    misma clave."""

    def cfg_init(self):
        self.cfg_reads, self.cfg_binds, self.cfg_fields, self.cfg_prefixes, self.cfg_type_reads = [], [], {}, [], []
        self.cfg_index = None

    def cfg_files(self):
        pool = set(self.files) | set(self.all_files())
        out = []
        for rel in sorted(pool):
            if CFG_FILE.search(rel) and not CFG_SKIP.search(rel) and not self.is_test(rel) and '/node_modules/' not in '/' + rel:
                out.append(rel)
        return out

    def cfg_build_index(self):
        index = defaultdict(list)
        for rel in self.cfg_files():
            try:
                path = self.root / rel
                if not path.is_file() or path.stat().st_size > 256 * 1024:
                    continue
                text = path.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            base = rel.rsplit('/', 1)[-1].lower()
            kind = 'toml' if '.toml' in base else 'properties' if '.properties' in base else 'json' if '.json' in base else 'yaml'
            if kind == 'yaml' and re.search(r'(?m)^(?:apiVersion|kind|services|version)\s*:', text) and re.search(r'(?m)^(?:apiVersion|services)\s*:', text):
                continue  # manifiestos k8s / compose: no son ficheros de claves de la aplicación
            for line, key in cfg_keys(text, kind):
                index[cfg_norm(key)].append((rel, line, key))
        self.cfg_index = index
        return index

    def cfg_scan(self, src):
        code, rel, lang = src.code, src.rel, src.lang
        if self.is_test(rel):
            return
        if lang in ('java', 'kt', 'cs', 'js', 'py', 'go', 'rb', 'php', 'c'):
            if '${' in code:
                for m in CFG_VALUE_ANN.finditer(code):
                    lead = code[code.rfind('\n', 0, m.start()) + 1:m.start()]
                    if '@' in lead or 'Value' in lead or 'property' in lead.lower():
                        line = src.line(m.start())
                        if lead.lstrip().startswith('@'):
                            # anotación: la lectura es del miembro anotado (la primera línea que no es otra anotación)
                            rest = code.split('\n', line + 6)[line:line + 6]
                            step = next((i for i, x in enumerate(rest) if x.strip() and not x.strip().startswith('@')), None)
                            line = line + 1 + step if step is not None else line
                        self.cfg_reads.append((rel, line, m.group(1), 'value'))
            for m in CFG_PREFIX_ANN.finditer(code):
                line = src.line(m.start())
                self.cfg_reads.append((rel, line, m.group(1), 'prefix'))
                tail = code[m.end():m.end() + 800]
                for _ in range(4):
                    tail = re.sub(r'\([^()]*\)', '', tail)  # argumentos de otras anotaciones (`@PropertySource(value = {..})`)
                after = re.search(r'\b(?:class|record|interface)\s+(\w+)|[{;]', tail)
                if after and after.group(1):
                    self.cfg_binds.append((after.group(1), m.group(1), rel, line))
            for m in CFG_COND_ANN.finditer(code):
                args = m.group(1)
                prefix = re.search(r'''\bprefix\s*=\s*"([\w.\-]+)"''', args)
                for name in re.findall(r'''"([\w.\-]+)"''', re.sub(r'''\b(?:prefix|havingValue|matchIfMissing)\s*=\s*"[^"]*"''', '', args)):
                    self.cfg_reads.append((rel, src.line(m.start()), f'{prefix.group(1)}.{name}' if prefix else name, 'cond'))
            for m in CFG_KEY_LIT.finditer(code):
                if src.ends.get(m.start()) is None:
                    continue
                before = src.struct[max(0, m.start() - 60):m.start()]
                if CFG_READ_CALL.search(before) or re.search(r'\[\s*$', before):
                    self.cfg_reads.append((rel, src.line(m.start()), m.group(2), 'lit'))
            if lang == 'cs' and ('Configure' in code or 'GetSection' in code or 'AddOptions' in code):
                for m in CS_BIND.finditer(code):
                    typ, section = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3)) if m.group(4) else (m.group(5), m.group(6))
                    self.cfg_binds.append((typ, section, rel, src.line(m.start())))
            if lang == 'go' and 'Unmarshal' in code:
                for m in GO_BIND.finditer(code):
                    self.go_bind(src, m)
            for m in ENV_PREFIX.finditer(code):
                self.cfg_prefixes.append((rel, src.line(m.start()), m.group(1)))

    def go_bind(self, src, m):
        """`ko.Unmarshal("db", &c)`: campos (con su etiqueta `koanf/mapstructure/yaml/json/toml`) del struct de `c`."""
        var = m.group(2).split('.')[-1]
        code = src.code
        decl = None
        for decl in re.finditer(rf'\bvar\s+{re.escape(var)}\s+struct\s*\{{|\b{re.escape(var)}\s+struct\s*\{{', code[:m.start()]):
            pass
        body_at = None
        if decl:
            body_at = decl.end() - 1
        else:
            typ = re.search(rf'\bvar\s+{re.escape(var)}\s+\*?(\w+)\b|\b{re.escape(var)}\s*:?=\s*&?(\w+)\s*\{{', code[:m.start()])
            name = typ and (typ.group(1) or typ.group(2))
            st = re.search(rf'\btype\s+{re.escape(name)}\s+struct\s*\{{', code) if name else None
            body_at = st.end() - 1 if st else None
        if body_at is None:
            self.cfg_reads.append((src.rel, src.line(m.start()), m.group(1), 'prefix'))
            return
        close = src.close(body_at)
        for f in re.finditer(r'(?m)^[ \t]*([A-Z]\w*)\s+[\w.*\[\]]+(?:\s+`([^`]*)`)?', code[body_at + 1:close]):
            tag = re.search(r'''(?:koanf|mapstructure|yaml|toml|json|env)\s*:\s*"([\w.\-]+)''', f.group(2) or '')
            key = tag.group(1) if tag else f.group(1)
            self.cfg_reads.append((src.rel, src.line(body_at + 1 + f.start(1)), f'{m.group(1)}.{key}', 'field'))

    def finish_config_keys(self):
        """Antes de `finish_env`: lecturas de claves definidas en ficheros de configuración, campos de tipos ligados y sus lecturas."""
        if not (self.cfg_reads or self.cfg_binds):
            return
        index = self.cfg_index if self.cfg_index is not None else self.cfg_build_index()
        prefixes = defaultdict(set)  # clase -> prefijos de sección
        for typ, section, rel, line in self.cfg_binds:
            prefixes[typ].add(section)
        used = set()
        for rel, line, key, kind in self.cfg_reads:
            norm = cfg_norm(key)
            hits = index.get(norm)
            if not hits and kind == 'value':
                own = self.g.nodes.get(self.owner(rel, line)) or {}
                cls = own.get('name', '').split('.')[0]
                for p in prefixes.get(cls, ()):
                    if index.get(cfg_norm(f'{p}.{key}')):
                        norm, hits = cfg_norm(f'{p}.{key}'), index[cfg_norm(f'{p}.{key}')]
                        break
            if not hits:
                continue
            self.env_uses.append((rel, line, hits[0][2]))
            used.add(norm)
        for norm in used:
            for rel, line, key in index[norm]:
                mid = self.module(rel) or self.g.node(f'm:{rel}', kind='module', name=rel.rsplit('/', 1)[-1], file=rel, line=1,
                                                       lang='config', hash=B.digest(rel))
                self.env_defs.append((rel, line, key, mid))
        self.finish_bound_types(index, prefixes)
        self.finish_env_prefixes()

    def finish_bound_types(self, index, prefixes):
        """Propiedades de un tipo ligado a una sección: cada propiedad es la clave `sección.propiedad`; las lecturas `x.Prop` de una
        variable de ese tipo (también `IOptions<T>` y su `.Value`) son lecturas de la clave; el registro (`Configure<T>`) cablea el tipo."""
        for typ, sections in prefixes.items():
            cands = [n for n in self.short.get(typ, []) if self.g.nodes[n]['kind'] == 'class' and not self.is_test(self.g.nodes[n]['file'])]
            if len(cands) != 1:
                continue
            cls = cands[0]
            meta = self.g.nodes[cls]
            text = self.text(meta['file']) or ''
            lines = text.split('\n')
            body = '\n'.join(lines[(meta.get('line') or 1) - 1:meta.get('end') or len(lines)])
            props = {}
            for p in re.finditer(r'(?m)^[ \t]*(?:public|private|protected)?\s*(?:static\s+)?[\w<>?\[\],. ]+?\s+(\w+)\s*(?:\{\s*get|;|=)', body):
                if p.group(1)[:1].isalpha() and p.group(1) not in ('class', 'return', 'new'):
                    props[p.group(1)] = (meta.get('line') or 1) + body.count('\n', 0, p.start(1))
            section = sorted(sections)[0]
            for prop, pline in props.items():
                key = f'{section}.{prop}'.replace(':', '.')
                self.env_uses.append((meta['file'], pline, key))
                for rel, line, k in index.get(cfg_norm(key), []):
                    mid = self.module(rel)
                    if mid:
                        self.env_defs.append((rel, line, k, mid))
            self.cfg_fields[typ] = (section, props)
            for typ2, section2, rel, line in self.cfg_binds:
                if typ2 == typ and rel.endswith('.cs'):
                    own = self.owner(rel, line)
                    if own and own != cls:
                        self.g.edge(own, cls, 'depends')
        if self.cfg_fields:
            self.cfg_type_uses()

    def cfg_type_uses(self):
        """`_serverOptions.Port` con `IOptions<ServerOptions> serverOptions` y `_serverOptions = serverOptions.Value`."""
        names = '|'.join(map(re.escape, sorted(self.cfg_fields)))
        decl = re.compile(rf'\b(?:I?Options(?:Monitor|Snapshot)?\s*<\s*)?({names})\s*>?\s+@?(\w+)\s*[,;)=]')
        for rel in self.files:
            if not rel.endswith(('.cs', '.java', '.kt', '.ts', '.go')) or self.is_test(rel):
                continue
            text = self.text(rel)
            if not text or not re.search(names, text):
                continue
            vars_ = {}
            for m in decl.finditer(text):
                vars_[m.group(2)] = m.group(1)
            for m in re.finditer(r'\b(\w+)\s*=\s*(\w+)\s*\.\s*(?:Value|CurrentValue)\b', text):
                if m.group(2) in vars_:
                    vars_[m.group(1)] = vars_[m.group(2)]
            for var, typ in vars_.items():
                section, props = self.cfg_fields[typ]
                for m in re.finditer(rf'(?<![\w.]){re.escape(var)}\s*\??\.\s*(\w+)\b', text):
                    if m.group(1) in props:
                        self.env_uses.append((rel, text.count('\n', 0, m.start()) + 1, f'{section}.{m.group(1)}'.replace(':', '.')))

    def finish_env_prefixes(self):
        """`env.Provider("APP_", "__", ..)`: las variables `APP_seccion__clave` definidas en el repo son la clave `seccion.clave`."""
        for prel, pline, prefix in self.cfg_prefixes:
            for rel, line, name, mid in list(self.env_defs):
                if name.startswith(prefix) and name != prefix and len(name) > len(prefix) + 1:
                    rest = name[len(prefix):].lstrip('_')
                    key = rest.replace('__', '.')
                    self.env_defs.append((rel, line, key, mid))
                    self.env_uses.append((prel, pline, name))


def cfg_keys(text, kind):
    """(línea, clave) de un fichero de configuración; las secciones también son claves."""
    out = []
    if kind == 'properties':
        for i, line in enumerate(text.split('\n')):
            m = re.match(r'^\s*([A-Za-z][\w.\-\[\]]*)\s*[=:]', line)
            if m and not line.lstrip().startswith(('#', '!')):
                key = m.group(1)
                parts = key.split('.')
                for j in range(1, len(parts)):
                    out.append((i + 1, '.'.join(parts[:j])))
                out.append((i + 1, key))
        return out
    if kind == 'toml':
        section = ''
        for i, line in enumerate(text.split('\n')):
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            head = re.match(r'^\[\[?([^\]]+)\]\]?', s)
            if head:
                section = head.group(1).strip().strip('"')
                out.append((i + 1, section))
                continue
            m = re.match(r'''^["']?([A-Za-z_][\w.\-]*)["']?\s*=''', s)
            if m:
                out.append((i + 1, f'{section}.{m.group(1)}' if section else m.group(1)))
        return out
    if kind == 'json':
        stack = []
        for i, line in enumerate(text.split('\n')):
            for m in re.finditer(r'"([A-Za-z_][\w\-]*)"\s*:\s*(\{)?|(\})', line):
                if m.group(3):
                    if stack:
                        stack.pop()
                    continue
                key = '.'.join(stack + [m.group(1)])
                out.append((i + 1, key))
                if m.group(2):
                    stack.append(m.group(1))
        return out
    keys = []
    for i, line in enumerate(text.split('\n')):
        body = line.strip()
        if not body or body.startswith(('#', '-', '---')):
            continue
        m = re.match(r'^([ \t]*)["\']?([A-Za-z_][\w.\-]*)["\']?\s*:(?:\s|$)', line)
        if not m:
            continue
        ind = len(m.group(1).expandtabs(2))
        keys = [(n, k) for n, k in keys if n < ind] + [(ind, m.group(2))]
        out.append((i + 1, '.'.join(k for _, k in keys)))
    return out


# ---------------------------------------------------------------- módulos de construcción del repo
class BuildModules:
    """Dependencias entre módulos de construcción del propio repo: `<dependency><artifactId>x</artifactId>` de un `pom.xml` hacia el
    módulo cuyo `artifactId` es `x`, `<ProjectReference Include="..">` de un `.csproj`, `project(':x')` de Gradle, dependencias de
    `package.json` con el nombre de un paquete del monorepo y `path = ".."` de Cargo; y literales en código que nombran un ensamblado
    del repo (`"App.Core"` en una lista de ensamblados). Aristas `depends` entre los manifiestos (o desde el código al manifiesto)."""

    def finish_build_modules(self):
        manifests = [rel for rel in self.all_files() if rel.rsplit('/', 1)[-1] in ('pom.xml', 'package.json', 'Cargo.toml', 'build.gradle',
                                                                                 'build.gradle.kts') or rel.endswith(('.csproj', '.fsproj'))]
        manifests = [rel for rel in manifests if not self.is_test(rel) and '/node_modules/' not in '/' + rel]
        if len(manifests) < 2:
            return
        texts, ids = {}, {}
        for rel in manifests:
            text = self.text(rel) if rel in self.fileset else None
            if text is None:
                try:
                    path = self.root / rel
                    text = path.read_text(encoding='utf-8', errors='replace') if path.stat().st_size < 512 * 1024 else ''
                except OSError:
                    text = ''
            texts[rel] = text
            name = rel.rsplit('/', 1)[-1]
            if name == 'pom.xml':
                body = re.sub(r'<parent>[\s\S]*?</parent>|<dependencies>[\s\S]*|<build>[\s\S]*', '', text)
                m = re.search(r'<artifactId>\s*([\w.\-]+)\s*</artifactId>', body)
                if m:
                    ids[('maven', m.group(1))] = rel
            elif name == 'package.json':
                m = re.search(r'"name"\s*:\s*"([^"]+)"', text)
                if m:
                    ids[('npm', m.group(1))] = rel
            elif name == 'Cargo.toml':
                m = re.search(r'(?m)^\[package\][^\[]*?^name\s*=\s*"([\w\-]+)"', text)
                if m:
                    ids[('cargo', m.group(1))] = rel
            elif name.startswith('build.gradle'):
                ids[('gradle', ':' + rel.rsplit('/', 1)[0].replace('/', ':') if '/' in rel else ':')] = rel
            else:
                ids[('net', B.os.path.splitext(name)[0])] = rel
                asm = re.search(r'<AssemblyName>\s*([\w.]+)\s*</AssemblyName>', text)
                if asm:
                    ids[('net', asm.group(1))] = rel
        for rel, text in texts.items():
            name = rel.rsplit('/', 1)[-1]
            refs = []
            if name == 'pom.xml':
                deps = re.search(r'<dependencies>([\s\S]*?)</dependencies>', re.sub(r'<dependencyManagement>[\s\S]*?</dependencyManagement>', lambda x: ' ' * len(x.group()), text))
                if deps:
                    for d in re.finditer(r'<dependency>([\s\S]*?)</dependency>', deps.group(1)):
                        a = re.search(r'<artifactId>\s*([\w.\-]+)\s*</artifactId>', d.group(1))
                        if a:
                            refs.append((deps.start(1) + d.start(1) + a.start(), ('maven', a.group(1))))
            elif name == 'package.json':
                for block in re.finditer(r'"(?:dependencies|devDependencies|peerDependencies)"\s*:\s*\{([^}]*)\}', text):
                    for d in re.finditer(r'"([^"]+)"\s*:\s*"[^"]*"', block.group(1)):
                        refs.append((block.start(1) + d.start(), ('npm', d.group(1))))
            elif name == 'Cargo.toml':
                for d in re.finditer(r'(?m)^([\w\-]+)\s*=\s*\{[^}\n]*\bpath\s*=\s*"([^"]+)"', text):
                    refs.append((d.start(), ('cargo', d.group(1))))
            elif name.startswith('build.gradle'):
                for d in re.finditer(r'''project\s*\(\s*["'](:[\w:\-]+)["']\s*\)''', text):
                    refs.append((d.start(), ('gradle', d.group(1))))
            else:
                for d in re.finditer(r'<ProjectReference\s+Include\s*=\s*"([^"]+)"', text):
                    target = B.os.path.normpath(B.os.path.join(B.os.path.dirname(rel), d.group(1).replace('\\', '/'))).replace(B.os.sep, '/')
                    refs.append((d.start(), ('path', target)))
            src_mid = self.module(rel)
            if not src_mid:
                continue
            for pos, key in refs:
                target = key[1] if key[0] == 'path' else ids.get(key)
                if not target or target == rel:
                    continue
                tmid = self.module(target)
                if not tmid:
                    continue
                self.g.edge(src_mid, tmid, 'depends')
        self.assembly_literals({k[1]: v for k, v in ids.items() if k[0] == 'net' and '.' in k[1]})

    def assembly_literals(self, names):
        """`"App.Core"` en código C# (listas de ensamblados para autodescubrimiento) -> el `.csproj` de ese ensamblado."""
        if not names:
            return
        rx = re.compile(r'"(%s)"' % '|'.join(map(re.escape, sorted(names, key=len, reverse=True))))
        for rel in self.files:
            if not rel.endswith('.cs') or self.is_test(rel):
                continue
            text = self.text(rel)
            if not text or not rx.search(text):
                continue
            for m in rx.finditer(text):
                line = text.count('\n', 0, m.start()) + 1
                own = self.owner(rel, line)
                tmid = self.module(names[m.group(1)])
                if own and tmid:
                    self.g.edge(own, tmid, 'depends')


# ---------------------------------------------------------------- canales y tareas en proceso (Go)
GO_CHAN_FIELD = re.compile(r'(?m)^[ \t]*(\w+(?:\s*,\s*\w+)*)\s+(?:<-\s*)?chan\b')
GO_SEND = re.compile(r'(?<![\w.])\w+\s*\.\s*(\w+)\s*<-(?!-)')
GO_RECV = re.compile(r'<-\s*\w+\s*\.\s*(\w+)\b|\brange\s+\w+\s*\.\s*(\w+)\s*\{')
GO_SPAWN = re.compile(r'(?m)^[ \t]*go\s+((?:\w+\s*\.\s*)?\w+)\s*\(')
GO_PRODUCER = re.compile(r'^(?:Push|Publish|Send|Enqueue|Emit|Queue|Notify|Broadcast|Dispatch|Submit|Schedule|Add|Record)\w*$')


class GoChannels:
    """Colas en proceso de Go: un campo `chan` de un struct en el que una función escribe (`m.queue <- x`, `case m.q <- x:`) y otra lee
    (`for x := range m.queue`, `<-m.queue`, `case x := <-m.q:`) es un topic entre ambas; quien llama a la función productora (con
    nombre de verbo de envío y única en el repo) también produce. `go f(..)` lanza `f` en otra goroutine (`go_*`)."""

    def go_init(self):
        self.go_chans, self.go_sends, self.go_recvs, self.go_spawns = defaultdict(set), [], [], []

    def go_scan(self, src):
        if src.lang != 'go' or self.is_test(src.rel):
            return
        code, rel = src.code, src.rel
        pkg = rel.rsplit('/', 1)[0] if '/' in rel else ''
        if 'chan' in code:
            for m in GO_CHAN_FIELD.finditer(code):
                enc = self.enclosing(src, m.start(1))
                if enc and enc[2] == '{' and re.search(r'\bstruct\s*$', src.struct[max(0, enc[0] - 40):enc[0]]):
                    for name in re.split(r'\s*,\s*', m.group(1)):
                        self.go_chans[pkg].add(name)
        if '<-' in code:
            for m in GO_SEND.finditer(code):
                self.go_sends.append((pkg, m.group(1), rel, src.line(m.start())))
            for m in GO_RECV.finditer(code):
                self.go_recvs.append((pkg, m.group(1) or m.group(2), rel, src.line(m.start())))
        if 'go ' in code:
            for m in GO_SPAWN.finditer(code):
                self.go_spawns.append((rel, src.line(m.start()), re.sub(r'\s+', '', m.group(1))))

    def finish_go(self):
        if not (self.go_sends or self.go_spawns):
            return
        recvs = defaultdict(list)
        for pkg, field, rel, line in self.go_recvs:
            if field in self.go_chans.get(pkg, ()):
                recvs[(pkg, field)].append((rel, line))
        producers = defaultdict(set)
        for pkg, field, rel, line in self.go_sends:
            key = (pkg, field)
            if field not in self.go_chans.get(pkg, ()) or key not in recvs:
                continue
            topic = f'{pkg}.{field}' if pkg else field
            own = self.owner(rel, line)
            self.topic_uses.append((topic, rel, line, 'pub', own or '', 'mq'))
            meta = self.g.nodes.get(own) or {}
            name = meta.get('name', '').rsplit('.', 1)[-1]
            if meta.get('kind') in ('function', 'method') and GO_PRODUCER.match(name):
                producers[name].add(topic)
            for r_rel, r_line in recvs[key]:
                self.topic_uses.append((topic, r_rel, r_line, 'sub', self.owner(r_rel, r_line) or '', 'mq'))
        for name, topics in producers.items():
            if len([n for n in self.short.get(name, []) if self.g.nodes[n]['kind'] in ('function', 'method')]) != 1:
                continue
            for rel, line, sym, _ in self.call_sites(name, ''):
                if rel.endswith('.go'):
                    for topic in topics:
                        self.topic_uses.append((topic, rel, line, 'pub', sym, 'mq'))
        for rel, line, ref in self.go_spawns:
            own = self.owner(rel, line)
            parts = ref.split('.')
            name = parts[-1]
            cands = [n for n in self.short.get(name, []) if self.g.nodes[n]['kind'] in ('function', 'method')
                     and self.g.nodes[n]['file'].endswith('.go') and not self.is_test(self.g.nodes[n]['file'])]
            if len(cands) > 1:  # varias funciones homónimas: la del mismo paquete
                cands = [n for n in cands if self.g.nodes[n]['file'].rsplit('/', 1)[0] == rel.rsplit('/', 1)[0]] or cands
            target = cands[0] if len(cands) == 1 else None
            if not target or target == own or not own:
                continue
            topic, sym = self.job_topic(target)
            self.topic_uses.append((f'go {topic}', rel, line, 'pub', own, 'mq'))
            meta = self.g.nodes[sym]
            self.topic_uses.append((f'go {topic}', meta['file'], meta.get('line') or 1, 'sub', sym, 'mq'))


# ---------------------------------------------------------------- tablas nombradas por identificadores en SQL
SQL_TPL_SLOT = re.compile(r'\b(from|join|into|update|table)\s+(?:only\s+)?$', re.I)


class SqlIdentifiers:
    """SQL en plantillas de código (`sql\\`select .. from ${table}\\``) cuya tabla es un identificador: un objeto de esquema importado
    (`Roles`, `UsersRoles`) o la tabla que se extrae de él (`const { table } = convertToIdentifiers(Roles)`, `${Roles.table}`); su nombre
    en snake_case es una tabla del DDL del repo. Y las claves foráneas del DDL (`references roles (id)`) como aristas `data` entre tablas."""

    def sqlid_scan(self, src):
        if src.lang != 'js' or self.is_test(src.rel) or '${' not in src.code or 'sql`' not in src.code.replace(' ', ''):
            return
        code, rel = src.code, src.rel
        aliases = {}
        for m in re.finditer(r'\b(?:const|let|var)\s+\{([^}]*)\}\s*=\s*\w+\s*\(\s*([A-Z]\w*)\s*(?:,[^()]*)?\)', code):
            for part in m.group(1).split(','):
                bits = [b.strip() for b in part.split(':')]
                if bits[0] == 'table':
                    aliases[bits[-1]] = m.group(2)
        for m in re.finditer(r'\b(?:const|let|var)\s+(\w+)\s*=\s*(?:([A-Z]\w*)\s*\.\s*table\b|\w+\s*\(\s*([A-Z]\w*)\s*(?:,[^()]*)?\))', code):
            aliases[m.group(1)] = m.group(2) or m.group(3)  # `const t = Roles.table`, `const roles = convertToIdentifiers(Roles)`
        for start, end in src.strings:
            if code[start] != '`' or not code[max(0, start - 4):start].endswith('sql'):
                continue
            body = code[start:end]
            for m in re.finditer(r'\$\{\s*([A-Za-z_$][\w$]*)(?:\s*\.\s*table)?\s*\}', body):
                if not SQL_TPL_SLOT.search(body[max(0, m.start() - 30):m.start()]):
                    continue
                ident = m.group(1)
                schema = aliases.get(ident) or (ident if ident[:1].isupper() else None)
                if not schema:
                    continue
                spec = self.js_import_map(src).get(schema)
                home = (self.js_resolve_spec(rel, spec[0]) or self.npm_package_dir(spec[0])) if spec else None
                for target in self.sqlid_tables(schema, rel, home):
                    own = self.owner(rel, src.line(start + m.start()))
                    if own and own != target:
                        self.g.edge(own, target, 'data')

    def npm_package_dir(self, spec):
        """Fichero `package.json` del paquete del monorepo llamado `spec` (`@acme/schemas`, `@acme/schemas/lib/x`)."""
        names = getattr(self, '_npm_names', None)
        if names is None:
            names = self._npm_names = {}
            for rel in self.all_files():
                if rel.rsplit('/', 1)[-1] == 'package.json' and '/node_modules/' not in '/' + rel:
                    try:
                        text = (self.root / rel).read_text(encoding='utf-8', errors='replace')[:4096]
                    except OSError:
                        continue
                    m = re.search(r'"name"\s*:\s*"([^"]+)"', text)
                    if m:
                        names.setdefault(m.group(1), rel)
        parts = (spec or '').split('/')
        return names.get('/'.join(parts[:2]) if spec.startswith('@') else parts[0])

    def sqlid_tables(self, schema, rel, home=None):
        snake = B.snake(schema).lower()
        root = self.project_root(home) if home else None
        out = []
        for key in dict.fromkeys((snake, B.singularize(snake), B.plural_word(snake))):
            out += [n for n in self.tables.get(key, []) if (self.g.nodes[n].get('file') or '').endswith('.sql') and (
                self.same_project(rel, self.g.nodes[n]['file']) or root is not None and self.project_root(self.g.nodes[n]['file']) == root)]
        return sorted(set(out))[:2]

    def finish_foreign_keys(self):
        """`references x (id)` del DDL (aristas `ref` entre tablas) también como `data`: la tabla depende de la referida."""
        for (a, b, kind) in list(self.g.edges):
            if kind != 'ref':
                continue
            ma, mb = self.g.nodes.get(a) or {}, self.g.nodes.get(b) or {}
            if ma.get('table') and mb.get('table') and (ma.get('file') or '').endswith('.sql') and (mb.get('file') or '').endswith('.sql') \
                    and a != b:
                self.g.edge(a, b, 'data')


# ---------------------------------------------------------------- fábricas de repositorios tipados por modelo
DATA_METHODS = {'create', 'get', 'get_one', 'get_all', 'getall', 'find', 'find_one', 'findone', 'findall', 'find_all', 'update', 'delete',
                'remove', 'save', 'insert', 'page_all', 'list', 'count', 'upsert', 'patch', 'multi_query', 'get_by_id', 'getbyid', 'add',
                'createone', 'updateone', 'deleteone', 'getone'}


class RepositoryFactories:
    """Una propiedad/función que devuelve un objeto de acceso a datos (clase del repo con varios métodos CRUD) construido con una clase
    de modelo (`return RepositoryGeneric(self.session, PK_ID, CookBook)`) da acceso a ese modelo; sus usos `repos.cookbooks.x(..)` en
    otros ficheros también (nombre de la propiedad único entre estas fábricas)."""

    def finish_repo_factories(self):
        models = {self.g.nodes[n]['name'].rsplit('.', 1)[-1]: n for ns in self.models.values() for n in ns}
        if not models:
            return
        crud = {}
        for owner, methods in self.owners.items():
            names = {self.g.nodes[m]['name'].rsplit('.', 1)[-1].lower() for m in methods}
            if len(names & DATA_METHODS) >= 3:
                crud[owner.rsplit('.', 1)[-1]] = True
        if not crud:
            return
        rx_ret = re.compile(r'\breturn\s+(?:new\s+)?(%s)\s*(?:<[^<>()]*>|\[[^\]]*\])?\s*\(' % '|'.join(map(re.escape, sorted(crud))))
        props = defaultdict(set)
        for rel, items in self.by_file.items():
            if self.is_test(rel):
                continue
            text = None
            for line, end, nid in items:
                meta = self.g.nodes[nid]
                if meta['kind'] not in ('method', 'function') or not end or end - line > 40:
                    continue
                if text is None:
                    text = self.text(rel) or ''
                    lines = text.split('\n')
                body = '\n'.join(lines[line - 1:end])
                m = rx_ret.search(body)
                if not m:
                    continue
                close = js_close(body, m.end() - 1)
                args = body[m.end():close if close > 0 else len(body)]
                found = [models[a] for a in re.findall(r'\b([A-Z]\w*)\b', args) if a in models]
                if len(found) != 1:
                    continue
                self.g.edge(nid, found[0], 'data')
                props[meta['name'].rsplit('.', 1)[-1]].add(found[0])
        unique = {p: next(iter(ms)) for p, ms in props.items() if len(ms) == 1 and len(p) > 3}
        if not unique:
            return
        rx = re.compile(r'\.\s*(%s)\s*\.\s*\w+\s*\(' % '|'.join(map(re.escape, sorted(unique, key=len, reverse=True))))
        for rel in self.files:
            if self.is_test(rel) or not rel.endswith(B.CODE_EXTS):
                continue
            text = self.text(rel)
            if not text or not rx.search(text):
                continue
            for m in rx.finditer(text):
                own = self.owner(rel, text.count('\n', 0, m.start()) + 1)
                if own and own != unique[m.group(1)]:
                    self.g.edge(own, unique[m.group(1)], 'data')


# ---------------------------------------------------------------- referencias de Dockerfile y compose
DOCKER_NAME = re.compile(r'(?i)(?:^|/)(?:Dockerfile[\w.\-]*|Containerfile[\w.\-]*|[\w.\-]+\.dockerfile)$')


class DockerRefs:
    """Cableado de construcción: `COPY/ADD src dest` de un Dockerfile hacia el fichero del repo copiado, `ENTRYPOINT`/`CMD`/
    `HEALTHCHECK` hacia el script del repo (también por el destino de un `COPY`), y el servicio compose hacia la etapa `target:` de su
    `build`, el `EXPOSE` del puerto que publica (`ports: - "8080:9000"`) y el `VOLUME` que monta."""

    def finish_docker_refs(self):
        files = self.all_files()
        fileset = set(files)
        dockerfiles = [rel for rel in files if DOCKER_NAME.search(rel) and self.module(rel) and not self.is_test(rel)]
        if not dockerfiles:
            return
        exposes, volumes = defaultdict(list), defaultdict(list)
        for rel in dockerfiles:
            text = self.text(rel) or ''
            if len(text) > 200000:
                continue
            base = rel.rsplit('/', 1)[0] if '/' in rel else ''
            dests = {}
            logical = []
            buf, start = '', 0
            for i, line in enumerate(text.split('\n')):
                if not buf:
                    start = i + 1
                buf += line.rstrip('\\') + ' '
                if not line.rstrip().endswith('\\'):
                    logical.append((start, buf.strip()))
                    buf = ''
            for line, stmt in logical:
                m = re.match(r'(?i)^(COPY|ADD|ENTRYPOINT|CMD|HEALTHCHECK|EXPOSE|VOLUME)\s+(.*)$', stmt)
                if not m:
                    continue
                op, rest = m.group(1).upper(), m.group(2)
                own = self.owner(rel, line) or self.module(rel)
                if op in ('COPY', 'ADD'):
                    if '--from' in rest:
                        continue
                    toks = [t for t in self.docker_tokens(rest) if not t.startswith('--')]
                    if len(toks) < 2:
                        continue
                    dest = toks[-1]
                    for src_tok in toks[:-1]:
                        target = self.docker_source(src_tok, base, fileset)
                        if target:
                            self.docker_edge(own, target)
                            name = src_tok.rstrip('/').rsplit('/', 1)[-1]
                            dests[dest.rstrip('/') + '/' + name if dest.endswith('/') else dest] = target
                            dests[name] = dests.get(name, target)
                elif op in ('ENTRYPOINT', 'CMD', 'HEALTHCHECK'):
                    for tok in self.docker_tokens(re.sub(r'(?i)^(?:--\w+=\S+\s+)*CMD\s+', '', rest)):
                        if not re.search(r'\.(?:sh|bash|py|js|rb|php)$|/', tok) or tok.startswith(('-', '/bin/', '/usr/bin/')):
                            continue
                        target = dests.get(tok) or dests.get(tok.rsplit('/', 1)[-1]) or self.docker_source(tok.lstrip('/'), base, fileset)
                        if target:
                            self.docker_edge(own, target)
                elif op == 'EXPOSE':
                    for port in re.findall(r'\b(\d{2,5})\b', rest):
                        exposes[port].append((rel, line, own))
                elif op == 'VOLUME':
                    for path in re.findall(r'(/[\w./\-]+)', rest):
                        volumes[path.rstrip('/')].append((rel, line, own))
        self.compose_docker_links(exposes, volumes)

    def docker_tokens(self, rest):
        rest = rest.strip()
        if rest.startswith('['):
            return re.findall(r'"([^"]*)"', rest)
        return [t for t in re.split(r'\s+', rest) if t]

    def docker_source(self, tok, base, fileset):
        tok = tok.strip().strip('"\'')
        if not tok or '*' in tok or tok in ('.', './') or '$' in tok:
            return None
        tok = tok[2:] if tok.startswith('./') else tok
        for root in (base, '', base.rsplit('/', 1)[0] if '/' in base else ''):
            cand = B.os.path.normpath(B.os.path.join(root, tok)).replace(B.os.sep, '/')
            if cand in fileset:
                return cand
        tail = [f for f in fileset if f.endswith('/' + tok)] if '/' in tok else []
        return tail[0] if len(tail) == 1 else None

    def docker_edge(self, own, target):
        mid = self.module(target)
        if not mid and not self.is_test(target):
            mid = self.g.node(f'm:{target}', kind='module', name=target.rsplit('/', 1)[-1], file=target, line=1,
                              lang='config', hash=B.digest(target))
        if own and mid and own != mid:
            self.g.edge(own, mid, 'depends')

    def compose_docker_links(self, exposes, volumes):
        for rel in self.all_files():
            name = rel.rsplit('/', 1)[-1]
            if not (name.startswith(('docker-compose', 'compose.')) and name.endswith(('.yml', '.yaml'))) or self.is_test(rel):
                continue
            text = self.text(rel) or ''
            lines = text.split('\n')
            for i, line in enumerate(lines):
                own = self.owner(rel, i + 1)
                tm = re.match(r'^\s+target:\s*["\']?([\w.\-]+)', line)
                if tm:
                    stage = [n for n in self.short.get(tm.group(1), []) if DOCKER_NAME.search(self.g.nodes[n].get('file') or '')]
                    if len(stage) == 1 and own:
                        self.g.edge(own, stage[0], 'depends')
                pm = re.match(r'''^\s*-\s*["']?(?:[\d.]+:)?(?:\d{2,5}:)?(\d{2,5})(?:/\w+)?["']?\s*$''', line)
                if pm and own and pm.group(1) in exposes:
                    cands = exposes[pm.group(1)]
                    same = [c for c in cands if self.same_project(rel, c[0])]
                    if len({c[0] for c in same}) == 1:
                        self.g.edge(own, same[0][2], 'depends')
                vm = re.match(r'''^\s*-\s*["']?[\w.\-/~]+:(/[\w./\-]+?)(?::\w+)?["']?\s*$''', line)
                if vm and own and vm.group(1).rstrip('/') in volumes:
                    for vrel, vline, vown in volumes[vm.group(1).rstrip('/')][:1]:
                        self.g.edge(own, vown, 'depends')
