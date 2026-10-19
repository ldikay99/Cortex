import os
import re
from bisect import bisect_left
from collections import defaultdict

from .common import Issues, digest

EXT_LANG = {
    '.py': 'py', '.js': 'js', '.jsx': 'js', '.mjs': 'js', '.cjs': 'js', '.ts': 'js', '.tsx': 'js', '.mts': 'js',
    '.cts': 'js', '.vue': 'js', '.svelte': 'js', '.go': 'go', '.java': 'java', '.kt': 'kt', '.kts': 'kt',
    '.scala': 'c', '.groovy': 'c', '.cs': 'cs', '.rb': 'rb', '.php': 'php', '.rs': 'rs', '.ex': 'ex', '.exs': 'ex',
    '.swift': 'c', '.dart': 'c', '.c': 'c', '.cc': 'c', '.cpp': 'c', '.h': 'c', '.hpp': 'c',
}
ENV_FILES = ('.env.example', '.env.sample', '.env.template', '.env.dist', '.env.defaults', 'env.example', 'example.env')
VERBS = ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS')
MAX_SCAN = 400000

DQ = r'"(?:\\.|[^"\\\n])*"'
SQ = r"'(?:\\.|[^'\\\n])*'"
DQM = r'"(?:\\.|[^"\\])*"'
SQM = r"'(?:\\.|[^'\\])*'"
SLASH = r'//[^\n]*|/\*[\s\S]*?\*/'
TOKENS = {
    'py': re.compile(r'#[^\n]*|[rRbBuUfF]{0,2}(?:"""[\s\S]*?"""|' + r"'''[\s\S]*?'''|" + DQ + '|' + SQ + ')'),
    'js': re.compile(SLASH + '|' + DQ + '|' + SQ + r'|`(?:\\.|[^`\\])*`'),
    'go': re.compile(SLASH + '|' + DQ + '|' + SQ + r'|`[^`]*`'),
    'java': re.compile(SLASH + r'|"""[\s\S]*?"""|' + DQ + '|' + SQ),
    'cs': re.compile(SLASH + r'|(?:\$@|@\$|@)"(?:""|[^"])*"|\$?"(?:\\.|[^"\\\n])*"|' + SQ),
    'rs': re.compile(SLASH + r'|b?r(#*)"[\s\S]*?"\1|b?"(?:\\.|[^"\\])*"|' + r"b?'(?:\\.|[^'\\\n])'"),
    'php': re.compile(SLASH + r'|#(?!\[)[^\n]*|' + DQM + '|' + SQM),
    'rb': re.compile(r'#(?!\{)[^\n]*|' + DQM + '|' + SQM),
    'ex': re.compile(r'#[^\n]*|"""[\s\S]*?"""|' + DQM + '|' + SQ),
}
TOKENS['kt'] = TOKENS['c'] = TOKENS['java']
NOT_NL = re.compile(r'[^\n]')
WS = re.compile(r'\s*')
BRACKETS = re.compile(r'[()\[\]{}]')
ARGS_SPLIT = re.compile(r'[()\[\]{},]')
EXPR = re.compile(r'(?:new\s+)?[A-Za-z_$@][\w$]*(?:(?:\.|::|->|\?\.)[A-Za-z_$][\w$]*)*!?')
DYNAMIC = re.compile(r'\$\{[^}]*\}|#\{[^}]*\}|%[sdvq]|%\(\w+\)s')
BRACED = re.compile(r'\{[^{}]*\}')
PHP_VAR = re.compile(r'\{?\$\w+(?:->\w+)*\}?')
WRAPPERS = {'URI.create', 'URI', 'new URI', 'URI.parse', 'Uri.parse', 'URL', 'new URL', 'new Uri', 'fmt.Sprintf',
            'format!', 'String.format', 'url.format', 'urljoin', 'sprintf', 'Url', 'uri', 'Sprintf', 'format'}
PARAM = re.compile(r'\{\*?(\w*)[^}]*\}|<(?:[^<>:]+:)?(\w+)(?:\.\.)?>|:(\w+)\??|\*(\w+)|\x00')
SCHEME = re.compile(r'^(?:[a-zA-Z][\w+.-]*:)?//[^/\x00]*')
PATHLIKE = re.compile(r'[\w\-./:\x00~%@+=,;!$\'{}<>*]+')
INLINE = re.compile(r'^(?:async\s+)?(?:static\s+)?(?:async\s+)?(?:function\b|\(|\w+\s*=>|func\b|fn\b|\[\s*&|lambda\b|'
                    r'proc\b|->|\{|delegate\b|new\s|do\b)')
KEYWORDS = {'if', 'for', 'while', 'switch', 'catch', 'return', 'new', 'typeof', 'nameof', 'sizeof', 'function', 'fun',
            'def', 'fn', 'func', 'await', 'async', 'throw', 'super', 'this', 'base', 'using', 'lock', 'foreach'}

CLASS_DECL = re.compile(
    r'(?:(?:public|private|protected|internal|abstract|final|sealed|static|partial|open|data|export|default|declare|'
    r'readonly|inner|enum|annotation)\s+)*(?:class|interface|object|record|struct|trait)\s+(\w+)')
CLASS_ANY = re.compile(r'\b(?:class|interface|object|record|struct|trait)\s+(\w+)')
FUN_DECL = re.compile(r'[^{;=]*?\bfun\s+(?:<[^>]*>\s*)?(?:[\w.]+\.)?(\w+)\s*\(')
CALL_NAME = re.compile(r'(\w+)\s*(?:<[^<>()]*(?:<[^<>()]*>[^<>()]*)*>)?\s*\(')
STR_LIT = re.compile(r'''(?:\b(\w+)\s*[=:]\s*)?[\[{(]?\s*(?:"((?:\\.|[^"\\])*)"|'((?:\\.|[^'\\])*)')''')
QUOTED = re.compile(r'''["'`]([^"'`]*)["'`]''')
ARG_NAME = re.compile(r'[A-Za-z_$][\w$]*(?:(?:\.|::|->)[A-Za-z_$][\w$]*)*')
SNAKE = re.compile(r'(?<=[a-z0-9])(?=[A-Z])')

SQL_HEAD = re.compile(r'\s*(SELECT|INSERT|UPDATE|DELETE|WITH|MERGE|REPLACE|UPSERT|select|insert|update|delete|with|merge|'
                      r'replace|upsert)\s')
SQL_TABLE = {upper: re.compile(r'\b(?:%s)\s+[`"\[]?(?:\w+[`"\]]?\.)?[`"\[]?(\w+)' % (
    'FROM|JOIN|INTO|UPDATE|TABLE' if upper else 'from|join|into|update|table')) for upper in (True, False)}
ORM = {
    'js': [re.compile(r'\bprisma\.(\w+)\.(?:find\w*|create\w*|update\w*|delete\w*|upsert|count|aggregate|groupBy)\('),
           re.compile(r'\b(?:getRepository|InjectRepository|getCustomRepository)\(\s*(\w+)'),
           re.compile(r'\bRepository<\s*(\w+)\s*>')],
    'py': [re.compile(r'\.query\(\s*(\w+)\s*[,)]'), re.compile(r'\bselect\(\s*(\w+)\s*[,)]'),
           re.compile(r'\b(\w+)\.objects\.')],
    'php': [re.compile(r'\b(\w+)::(?:query|where\w*|find\w*|create|all|first\w*|updateOrCreate|with|orderBy|latest|'
                       r'paginate|destroy|insert|count)\('),
            re.compile(r'''\bDB::table\(\s*['"](\w+)''')],
    'cs': [re.compile(r'\bDbSet<\s*(\w+)\s*>'), re.compile(r'\bSet<\s*(\w+)\s*>\s*\(')],
    'java': [re.compile(r'\b(?:Jpa|Crud|PagingAndSorting|Mongo|Reactive\w*)Repository<\s*(\w+)')],
    'go': [re.compile(r'\.Model\(\s*&?(?:\w+\.)?(\w+)\{'), re.compile(r'\.Table\(\s*"(\w+)"')],
}
ORM['kt'] = ORM['java']

ENV_USES = {
    'js': [r'\bprocess\.env\.([A-Za-z_]\w*)', r'''\bprocess\.env\[\s*['"`]([A-Za-z_]\w*)''',
           r'\bimport\.meta\.env\.([A-Za-z_]\w*)', r'''\bDeno\.env\.get\(\s*['"]([A-Za-z_]\w*)''',
           r'\bBun\.env\.([A-Za-z_]\w*)'],
    'py': [r'''\bos\.environ(?:\.get\(|\.setdefault\(|\.pop\(|\[)\s*[rbuf]?['"]([A-Za-z_]\w*)''',
           r'''\b(?:os\.)?getenv\(\s*['"]([A-Za-z_]\w*)'''],
    'go': [r'\bos\.(?:Getenv|LookupEnv)\(\s*"([A-Za-z_]\w*)"'],
    'java': [r'\bSystem\.getenv\(\s*"([A-Za-z_]\w*)"'],
    'cs': [r'\bEnvironment\.GetEnvironmentVariable\(\s*"([A-Za-z_]\w*)"'],
    'rb': [r'''\bENV\[\s*['"]([A-Za-z_]\w*)''', r'''\bENV\.fetch\(\s*['"]([A-Za-z_]\w*)'''],
    'php': [r'''\b(?:getenv|env)\(\s*['"]([A-Za-z_]\w*)['"]''', r'''\$_ENV\[\s*['"]([A-Za-z_]\w*)'''],
    'rs': [r'\benv::var(?:_os)?\(\s*"([A-Za-z_]\w*)"', r'\b(?:option_)?env!\(\s*"([A-Za-z_]\w*)"'],
    'ex': [r'\bSystem\.(?:get_env|fetch_env!?)\(\s*"([A-Za-z_]\w*)"'],
    'c': [r'\bgetenv\(\s*"([A-Za-z_]\w*)"', r'\bSystem\.getenv\(\s*"([A-Za-z_]\w*)"',
          r'''\b(?:environment|Platform\.environment)\[\s*['"]([A-Za-z_]\w*)'''],
}
ENV_USES['kt'] = ENV_USES['java']
ENV_USES = {k: re.compile('|'.join(v)) for k, v in ENV_USES.items()}
ENV_DESTRUCT = re.compile(r'\b(?:const|let|var)\s*\{([^}]*)\}\s*=\s*(?:process\.env|import\.meta\.env)\b')
ENV_HINT = re.compile(r'env|ENV|Env')

TOPIC_NAME = r'''['"`]([\w.\-:/]+)['"`]'''
TOPICS = [
    ('js', 'topic', re.compile(r'\.send\(\s*\{\s*topic\s*:\s*' + TOPIC_NAME), 'pub'),
    ('js', 'subscribe', re.compile(r'\.subscribe\(\s*\{\s*topics?\s*:\s*\[?\s*' + TOPIC_NAME), 'sub'),
    ('js py rb', 'sendToQueue', re.compile(r'\.sendToQueue\(\s*' + TOPIC_NAME), 'pub'),
    ('js', 'consume', re.compile(r'\.consume\(\s*' + TOPIC_NAME), 'sub'),
    ('py', 'basic_publish', re.compile(r'\bbasic_publish\([^)]*?routing_key\s*=\s*' + TOPIC_NAME), 'pub'),
    ('py', 'basic_consume', re.compile(r'\bbasic_consume\(\s*(?:[^)]*?queue\s*=\s*)?' + TOPIC_NAME), 'sub'),
    ('py', 'roducer', re.compile(r'\b\w*producer\.(?:send|produce)\(\s*(?:topic\s*=\s*)?' + TOPIC_NAME, re.I), 'pub'),
    ('py', 'KafkaConsumer', re.compile(r'\bKafkaConsumer\(\s*' + TOPIC_NAME), 'sub'),
    ('py js rb go', 'subscribe', re.compile(r'\.subscribe\(\s*\[\s*' + TOPIC_NAME), 'sub'),
    ('java kt', '.send(', re.compile(r'\b\w*(?:[Tt]emplate|[Pp]roducer)\.send\(\s*"([\w.\-:/]+)"'), 'pub'),
    ('java kt', 'ProducerRecord', re.compile(r'\bnew\s+ProducerRecord(?:<[^>]*>)?\(\s*"([\w.\-:/]+)"'), 'pub'),
    ('java kt', 'convertAndSend', re.compile(r'\b\w*[Tt]emplate\.convertAndSend\(\s*"([\w.\-:/]+)"'), 'pub'),
    ('go', 'Topic:', re.compile(r'\bTopic:\s*"([\w.\-:/]+)"'), 'kafka'),
    ('py js rb go java kt cs php ex rs', 'ublish', re.compile(
        r'\.(?:publish|Publish|PublishAsync)\(\s*(?:ctx\s*,\s*)?' + TOPIC_NAME + r'\s*,'), 'pub'),
    ('py js rb go java kt cs php ex rs', 'ubscribe', re.compile(
        r'\.(?:subscribe|psubscribe|Subscribe|PSubscribe|QueueSubscribe|SubscribeAsync)\(\s*(?:ctx\s*,\s*)?' + TOPIC_NAME), 'sub'),
    ('py', 'send_task', re.compile(r'\bsend_task\(\s*' + TOPIC_NAME), 'pub'),
]
TOPICS = [(set(langs.split()), guard, rx, role) for langs, guard, rx, role in TOPICS]
EMIT = re.compile(r'''\.\s*emit\(\s*['"]([\w:.\-/]+)['"]''')
LISTEN = re.compile(r'''\.\s*(?:on|once|addListener|prependListener)\(\s*['"]([\w:.\-/]+)['"]''')
COMMON_EVENTS = set('''click change input submit error data end close open message connect connection disconnect ready
    load exit finish resize scroll keydown keyup keypress mousedown mouseup mousemove mouseenter mouseleave focus blur drain
    readable response request timeout abort progress success start stop update destroy init drop dragstart dragend
    dragover wheel touchstart touchend touchmove pointerdown pointerup pointermove paste copy cut select reset beforeunload
    unload hashchange popstate storage visibilitychange online offline listening upgrade pipe unpipe spawn disconnecting
    warning uncaughtException unhandledRejection SIGINT SIGTERM line keypress'''.split())
CELERY_TASK = re.compile(r'^[ \t]*@(?:shared_task|(?:\w+\.)*task|(?:\w+\.)*actor)\b(\([^\n]*\))?', re.M)
CELERY_CALL = re.compile(r'\b(\w+)\.(?:delay|apply_async|s|si|signature|send)\(')

JS_SERVER_IMPORT = re.compile(
    r'''(?:require\(\s*|from\s+|import\s+)['"](?:express|koa|@koa/router|koa-router|fastify|hono|hono/[\w-]+|restify|'''
    r'''polka|elysia|h3|itty-router|@hapi/hapi|hyper-express|ultimate-express|express-promise-router)['"]''')
JS_SERVER_VAR = re.compile(
    r'\b(?:const|let|var)\s+(\w+)\s*(?::\s*[\w<>.]+\s*)?=\s*(?:await\s+)?(?:new\s+)?(?:express(?:\.Router)?|Router|'
    r'KoaRouter|Koa|Hono|Elysia|fastify|Fastify|polka|restify\.createServer|createRouter|PromiseRouter)\s*\(')
JS_SERVER_NAMES = {'app', 'router', 'server', 'api', 'routes', 'fastify', 'instance', 'r', 'route', 'v1', 'v2'}
JS_ROUTE = re.compile(r'\b(\w+)\s*\.\s*(get|post|put|patch|delete|del|all|options|head)\s*\(')
JS_CHAIN_ROUTE = re.compile(r'\b(\w+)\s*\.\s*route\s*\(')
JS_CHAIN_VERB = re.compile(r'\s*\.\s*(get|post|put|patch|delete|all|options|head)\s*\(')
JS_MOUNT = re.compile(r'\b(\w+)\s*\.\s*(use|register)\s*\(')
JS_IMPORT = re.compile(
    r'''import\s+(?:(\w+)|\*\s+as\s+(\w+)|\{([^}]*)\})(?:\s*,\s*\{([^}]*)\})?\s+from\s+['"]([^'"]+)['"]'''
    r'''|\b(?:const|let|var)\s+(\w+)\s*=\s*require\(\s*['"]([^'"]+)['"]\s*\)''')
JS_CLIENT = re.compile(r'(?<![\w$])(fetch|\$fetch|ofetch|useFetch|useSWR|ky|got|axios|superagent|request)\s*\(')
JS_CLIENT_METHOD = re.compile(
    r'\b([\w$]+)\s*\.\s*(get|post|put|patch|delete|head|request)\s*(?:<[^<>()]*(?:<[^<>()]*>[^<>()]*)*>)?\s*\(')
JS_CLIENT_NAMES = re.compile(r'^(?:\$?http\w*|axios|api|client|request|instance|ky|got|superagent|agent|fetcher|'
                             r'service|\w*(?:Api|API|Client|Http|Service|Request|Fetcher))$')
JS_NEXT_EXPORT = re.compile(r'\bexport\s+(?:async\s+)?(?:function\s+|const\s+|let\s+)(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b'
                            r'|\bexport\s*\{([^}]*)\}')
JS_DEFAULT_FN = re.compile(r'\bexport\s+default\s+(?:async\s+)?function\s*\*?\s*(\w+)')
NEST_PREFIX = re.compile(r'''\.setGlobalPrefix\(\s*['"`]([^'"`]*)''')
METHOD_KW = re.compile(r'''\bmethod\s*:\s*['"`](\w+)''', re.I)
URL_KW = re.compile(r'''\b(?:url|path)\s*:\s*''')

PY_DECOR = re.compile(r'^[ \t]*@([\w.]+)\.(get|post|put|patch|delete|head|options|route|api_route|websocket)\(', re.M)
PY_DEF = re.compile(r'\s*(?:@[^\n]*\n\s*)*(?:async\s+)?(def|class)\s+(\w+)')
PY_ROUTER = re.compile(r'\b(\w+)\s*=\s*(?:[\w.]+\.)?(?:APIRouter|Blueprint|FastAPI|Flask|Quart|Sanic|APIBlueprint)\(')
PY_MOUNT = re.compile(r'\b(\w+)\.(include_router|register_blueprint|mount)\(')
PY_IMPORT = re.compile(r'^[ \t]*from\s+(\.*[\w.]*)\s+import\s+\(?([^\n)]*)', re.M)
PY_IMPORT_AS = re.compile(r'^[ \t]*import\s+([\w.]+)(?:\s+as\s+(\w+))?', re.M)
PY_METHODS = re.compile(r'''\bmethods\s*=\s*[\[\(\{]([^\]\)\}]*)''')
PY_PREFIX = re.compile(r'''\b(?:prefix|url_prefix)\s*=\s*[rf]?['"]([^'"]*)['"]''')
PY_CLIENT = re.compile(r'\b((?:\w+\.)*\w+)\.(get|post|put|patch|delete|head|options|request|urlopen)\s*\(')
PY_CLIENT_NAMES = {'requests', 'httpx', 'session', 'client', 'sess', 'http', 'async_client', 'http_client',
                   'api_client', 'aiohttp', 'request', 'grequests', 'treq', 'test_client', 'c', 's'}
PY_URLPATH = re.compile(r'\b(path|re_path|url)\(')
PY_ROUTER_REG = re.compile(r'\b(\w+)\.register\(')
PY_AIOHTTP = re.compile(r'\b(?:web|\w+\.router)\.(?:add_)?(get|post|put|patch|delete|head|route|view)\(')
PY_STARLETTE = re.compile(r'\b(?:Route|WebSocketRoute)\(')
PY_URL_RULE = re.compile(r'\.add_url_rule\(')

ANN_START = re.compile(r'(?m)^[ \t]*(?:@(?=[A-Za-z])|\[(?=[A-Za-z])|#\[(?=[A-Za-z]))')
ANN_NAME = re.compile(r'[A-Za-z_][\w.]*')
SPRING_VERB = {'GetMapping': 'GET', 'PostMapping': 'POST', 'PutMapping': 'PUT', 'DeleteMapping': 'DELETE',
               'PatchMapping': 'PATCH', 'RequestMapping': 'ANY', 'GetExchange': 'GET', 'PostExchange': 'POST',
               'PutExchange': 'PUT', 'DeleteExchange': 'DELETE', 'PatchExchange': 'PATCH', 'HttpExchange': 'ANY'}
CAP_VERB = {'Get': 'GET', 'Post': 'POST', 'Put': 'PUT', 'Delete': 'DELETE', 'Patch': 'PATCH', 'All': 'ANY',
            'Head': 'HEAD', 'Options': 'OPTIONS'}
NET_VERB = {'HttpGet': 'GET', 'HttpPost': 'POST', 'HttpPut': 'PUT', 'HttpDelete': 'DELETE', 'HttpPatch': 'PATCH',
            'HttpHead': 'HEAD', 'HttpOptions': 'OPTIONS'}
LISTENERS = {'KafkaListener': ('topics', 'topicPattern', 'value'), 'RabbitListener': ('queues', 'value'),
             'JmsListener': ('destination', 'value'), 'SqsListener': ('value', 'queueNames'),
             'StreamListener': ('value', 'target')}
JAVA_CLIENT = re.compile(r'\.(getForObject|getForEntity|postForObject|postForEntity|postForLocation|patchForObject|'
                         r'exchange|put|delete)\s*\(')
JAVA_WEBCLIENT = re.compile(r'\.(get|post|put|delete|patch)\(\)\s*\.\s*uri\(')
CS_CLIENT = re.compile(r'\.(Get|Post|Put|Delete|Patch|GetString|GetStream|GetByteArray|GetFromJson|PostAsJson|PutAsJson|'
                       r'PatchAsJson|DeleteFromJson)Async\s*(?:<[^<>()]*(?:<[^<>()]*>[^<>()]*)*>)?\s*\(')
CS_REQUEST = re.compile(r'\bnew\s+HttpRequestMessage\(\s*HttpMethod\.(\w+)\s*,')
CS_MAP = re.compile(r'\b(\w+)\s*\.\s*Map(Get|Post|Put|Patch|Delete|Methods)\s*\(')
CS_GROUP = re.compile(r'\b(\w+)\s*=\s*(\w+)\s*\.\s*MapGroup\(')
GO_ROUTE = re.compile(r'\b(\w+)\s*\.\s*(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD|Any|Get|Post|Put|Patch|Delete|Options|Head|'
                      r'Handle|HandleFunc)\s*\(')
GO_GROUP = re.compile(r'\b(\w+)\s*:?=\s*(\w+)\s*\.\s*(?:Group|PathPrefix|Prefix)\(')
GO_ROUTE_BLOCK = re.compile(r'\b\w+\s*\.\s*(?:Route|Group)\(\s*"([^"]*)"\s*,\s*func\s*\(')
GO_METHODS = re.compile(r'\s*\.\s*Methods\(([^)]*)\)')
GO_CLIENT = re.compile(r'\b(http|\w*[Cc]lient)\.(Get|Post|Head|PostForm)\(')
GO_NEWREQ = re.compile(r'\bhttp\.NewRequest(?:WithContext)?\(\s*(?:[\w.()]+\s*,\s*)?(?:"(\w+)"|http\.Method(\w+))\s*,')
GO_RESTY = re.compile(r'\.R\(\)(?:\s*\.\s*\w+\([^()]*\))*\s*\.\s*(Get|Post|Put|Delete|Patch)\(')
RB_CLIENT = re.compile(r'\b(Net::HTTP|HTTParty|Faraday|RestClient|HTTP|conn|connection|client|http)\.(get|post|put|patch|delete)'
                       r'\b[ \t]*\(?')
RB_SINATRA = re.compile(r'''^[ \t]*(get|post|put|patch|delete|options|head|link|unlink)\s*\(?\s*(['"])(/[^'"]*)\2''', re.M)
PHP_ROUTE = re.compile(r'\bRoute::(get|post|put|patch|delete|options|any|match)\s*\(')
PHP_RESOURCE = re.compile(r'\bRoute::(resource|apiResource)\s*\(')
PHP_VAR_ROUTE = re.compile(r'\$(\w+)\s*->\s*(get|post|put|patch|delete|options|any|map)\s*\(')
PHP_GROUP = re.compile(r'(?:->|::)\s*group\s*\(')
PHP_SERVER_VARS = {'app', 'group', 'router', 'route', 'r', 'routes', 'api', 'proxy', 'collector', 'routeCollector'}
PHP_CLIENT = re.compile(r'(?:\bHttp::(?:\w+\([^()]*\)\s*->\s*)*|\$(?:this->)?(?:\w*[Cc]lient|http|guzzle)\s*->\s*)'
                        r'(get|post|put|patch|delete|request)\s*\(')
RS_ATTR = re.compile(r'#\[\s*(?:\w+::)?(get|post|put|delete|patch|head|options)\(\s*"([^"]*)"')
RS_FN = re.compile(r'(?:\s*#\[[^\]]*\])*\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(\w+)')
RS_ROUTE = re.compile(r'\.route\(\s*"([^"]*)"\s*,')
RS_RESOURCE = re.compile(r'\bweb::resource\(\s*"([^"]*)"\s*\)')
RS_SCOPE = re.compile(r'\bweb::scope\(\s*"([^"]*)"\s*\)')
RS_NEST = re.compile(r'\.nest\(\s*"([^"]*)"\s*,\s*([\w:]+)\s*\(')
RS_AXUM_VERB = re.compile(r'\b(get|post|put|delete|patch|head|options|any)\(\s*([\w:]+)\s*\)')
RS_ACTIX_VERB = re.compile(r'\bweb::(get|post|put|delete|patch|head)\(\)\s*\.\s*to\(\s*([\w:]+)')
RS_CLIENT = re.compile(r'(?:\breqwest::(?:blocking::)?|\b(?:client|http|self\.client)\.)(get|post|put|delete|patch)\(')
EX_CLIENT = re.compile(r'\b(?:HTTPoison|Req|Tesla|Finch|HTTPotion)\.(get|post|put|patch|delete)!?\(')

GRPC_GO_REG = re.compile(r'\bRegister(\w+)Server\(\s*[^,()]+(?:\([^()]*\))?\s*,\s*([^)]+)\)')
GRPC_GO_EMBED = re.compile(r'\btype\s+(\w+)\s+struct\s*\{[^}]*?\bUnimplemented(\w+)Server\b')
GRPC_GO_CHAIN = re.compile(r'\bNew(\w+)Client\(')
GRPC_GO_BIND = re.compile(r'\b(\w+)\s*(?::=|=|:)\s*(?:\w+\.)?New(\w+)Client\(')
GRPC_PY_SERVER = re.compile(r'^[ \t]*class\s+(\w+)\(\s*(?:[\w.]+\.)?(\w+)Servicer\s*\)', re.M)
GRPC_PY_SUB = re.compile(r'^[ \t]*class\s+(\w+)\(\s*([\w.]+)\s*\)', re.M)
GRPC_PY_BIND = re.compile(r'\b(\w+)\s*=\s*(?:[\w.]+\.)?(\w+)Stub\(')
GRPC_PY_CHAIN = re.compile(r'\b(\w+)Stub\(')
GRPC_JAVA_SERVER = re.compile(r'\bclass\s+(\w+)[^{]*?(?:extends|:)\s*(?:[\w.]+\.)?(\w+)Grpc(?:Kt)?\.\w*ImplBase\b')
GRPC_JAVA_BIND = re.compile(r'\b(\w+)\s*=\s*(?:[\w.]+\.)?(\w+)Grpc(?:Kt)?\.new\w*Stub\(')
GRPC_JAVA_DECL = re.compile(r'\b(\w+)Grpc(?:Kt)?\.\w*Stub\s+(\w+)')
GRPC_CS_SERVER = re.compile(r'\bclass\s+(\w+)\s*:\s*(?:[\w.]+\.)?(\w+)\.\2Base\b')
GRPC_CS_BIND = re.compile(r'\b(\w+)\s*=\s*new\s+(?:[\w.]+\.)?(\w+)\.\2Client\(')
GRPC_CS_DECL = re.compile(r'\b(?:[\w.]+\.)?(\w+)\.\1Client\s+(\w+)')
GRPC_JS_SERVER = re.compile(r'\.addService\(\s*([\w$.]+?)\.service\s*,')
GRPC_JS_BIND = re.compile(r'\b(\w+)\s*=\s*new\s+(?:[\w$]+\.)*(\w+?)(?:Client)?\(')
GRPC_RS_SERVER = re.compile(r'\bimpl\s+(?:[\w:]+::)?(\w+)\s+for\s+(\w+)')
GRPC_RS_BIND = re.compile(r'\b(\w+)\s*=\s*(?:[\w:]+::)?(\w+)Client::(?:connect|new)\(')
GRPC_CALL = re.compile(r'\s*\.\s*(\w+)\s*\(')
PROTO_PACKAGE = re.compile(r'^\s*package\s+([\w.]+)\s*;', re.M)

RAILS_VERB = re.compile(r'''^(get|post|put|patch|delete|match|root)\b\s*\(?\s*(?:(['"])([^'"]*)\2|:(\w+))?(.*)$''')
RAILS_RES = re.compile(r'^(resources|resource)\s*\(?\s*((?::\w+\s*,\s*)*:\w+)(.*)$')
RAILS_SCOPE = re.compile(r'''^(namespace|scope|member|collection|concern|constraints|controller|defaults|devise_scope|'''
                         r'''with_options|direct)\b\s*\(?\s*(?::(\w+)|(['"])([^'"]*)\3)?(.*)$''')
RAILS_TO = re.compile(r'''(?:\bto:\s*|=>\s*)['"]([\w/]+)#(\w+)['"]''')
RAILS_OPT = re.compile(r'''\b(controller|action|on|path|module|only|except|via)\s*:\s*(\[[^\]]*\]|:\w+|['"][^'"]*['"])''')
RAILS_ACTIONS = [('index', 'GET', ''), ('create', 'POST', ''), ('new', 'GET', '/new'), ('edit', 'GET', '/:id/edit'),
                 ('show', 'GET', '/:id'), ('update', 'PATCH', '/:id'), ('update', 'PUT', '/:id'), ('destroy', 'DELETE', '/:id')]
LARAVEL_ACTIONS = [('index', 'GET', ''), ('create', 'GET', '/create'), ('store', 'POST', ''), ('show', 'GET', '/:p'),
                   ('edit', 'GET', '/:p/edit'), ('update', 'PUT', '/:p'), ('update', 'PATCH', '/:p'), ('destroy', 'DELETE', '/:p')]
RB_OPENER = re.compile(r'\bdo\b(?:\s*\|[^|]*\|)?\s*$|^(?:if|unless|while|until|case|begin|def|class|module)\b')
RB_END = re.compile(r'^end\b')
EX_VERB = re.compile(r'''^(get|post|put|patch|delete|options|head|forward|live)\s*\(?\s*"([^"]*)"\s*,\s*([\w.]+)(?:\s*,\s*:(\w+))?''')
EX_RES = re.compile(r'''^resources\s*\(?\s*"([^"]*)"\s*,\s*([\w.]+)(.*)$''')
EX_SCOPE = re.compile(r'''^scope\s*\(?\s*"([^"]*)"''')


def blanked(text):
    return ' ' * len(text) if '\n' not in text else NOT_NL.sub(' ', text)


def docstring(text, start, tok):
    t = tok.lstrip('rRbBuUfF')
    if not t.startswith(('"""', "'''")):
        return False
    i = start - 1
    while i >= 0 and text[i] in ' \t\r\n':
        i -= 1
    return i < 0 or text[i] == ':' or (text[i] not in '=([{,+%' and '\n' in text[i:start])


def paren(m):
    return m.start() + m.group().rfind('(')


class Src:
    def __init__(self, rel, lang, text):
        self.rel, self.lang, self.text = rel, lang, text
        code, struct, self.strings = [], [], []
        last = 0
        for m in TOKENS[lang].finditer(text):
            s, e = m.span()
            tok = m.group()
            gap = text[last:s]
            code.append(gap)
            struct.append(gap)
            if tok[0] in '/#' or (lang == 'py' and docstring(text, s, tok)):
                b = blanked(tok)
                code.append(b)
                struct.append(b)
            else:
                code.append(tok)
                struct.append(tok[0] + blanked(tok[1:-1]) + tok[-1] if len(tok) > 1 else tok)
                self.strings.append((s, e))
            last = e
        code.append(text[last:])
        struct.append(text[last:])
        self.code, self.struct = ''.join(code), ''.join(struct)
        self.ends = dict(self.strings)
        self.nl = [m.start() for m in re.finditer('\n', text)]

    def line(self, pos):
        return bisect_left(self.nl, pos) + 1

    def skip(self, pos):
        return WS.match(self.struct, pos).end()

    def literal(self, pos):
        end = self.ends.get(pos)
        if end is None:
            return None
        tok = self.text[pos:end]
        i = next((k for k, ch in enumerate(tok) if ch in '"\'`'), None)
        if i is None:
            return None
        q = tok[i]
        body = tok[i:].rstrip('#')
        content = body[3:-3] if body.startswith(q * 3) and len(body) >= 6 else body[1:-1]
        return content, end, tok[:i], q

    def template(self, content, prefix, quote):
        content = DYNAMIC.sub('\0', content)
        if 'f' in prefix.lower() or '$' in prefix:
            content = BRACED.sub('\0', content)
        if self.lang == 'php' and quote == '"':
            content = PHP_VAR.sub('\0', content)
        return content

    def close(self, pos):
        depth = 0
        for m in BRACKETS.finditer(self.struct, pos, min(len(self.struct), pos + MAX_SCAN)):
            depth += 1 if m.group() in '([{' else -1
            if depth == 0:
                return m.start()
        return -1

    def args(self, open_pos):
        end = self.close(open_pos)
        if end < 0:
            return [], -1
        out, depth, start = [], 0, open_pos + 1
        for m in ARGS_SPLIT.finditer(self.struct, open_pos + 1, end):
            ch = m.group()
            if ch in '([{':
                depth += 1
            elif ch in ')]}':
                depth -= 1
            elif depth == 0:
                out.append((start, m.start()))
                start = m.end()
        if self.struct[start:end].strip() or out:
            out.append((start, end))
        return out, end

    def expr(self, pos, depth=0):
        parts, p, seen = [], self.skip(pos), False
        for _ in range(10):
            lit = self.literal(p)
            if lit:
                content, end, prefix, quote = lit
                parts.append(self.template(content, prefix, quote))
                p, seen = end, True
            else:
                m = EXPR.match(self.struct, p)
                if not m:
                    break
                q = self.skip(m.end())
                if q < len(self.struct) and self.struct[q] == '(':
                    end = self.close(q)
                    if end < 0:
                        break
                    name = m.group().replace('?.', '.')
                    inner = None
                    if depth < 3 and (name in WRAPPERS or name.rsplit('.', 1)[-1] in WRAPPERS):
                        inner = self.expr(q + 1, depth + 1)
                    parts.append(inner if inner is not None else '\0')
                    seen = seen or inner is not None
                    p = end + 1
                else:
                    parts.append('\0')
                    p = m.end()
            q = self.skip(p)
            if self.struct.startswith('+', q) and not self.struct.startswith('++', q) or (
                    self.lang == 'php' and self.struct.startswith('.', q) and not self.struct.startswith('..', q)):
                p = self.skip(q + 1)
                continue
            break
        return ''.join(parts) if seen else None


def drop_base(tpl):
    tpl = SCHEME.sub('', tpl.strip())
    if tpl.startswith('\0'):
        cut = tpl.find('/')
        tpl = tpl[cut:] if cut >= 0 else ''
    return tpl


def norm_path(path):
    path = path.split('?', 1)[0].split('#', 1)[0]
    segs = []
    for s in path.split('/'):
        if not s or s == '.':
            continue
        m = PARAM.search(s)
        if m:
            s = ':' + next((x for x in m.groups() if x), 'param')
        segs.append(s)
    return '/' + '/'.join(segs)


def client_path(tpl):
    if not tpl:
        return None
    tpl = drop_base(tpl).split('?', 1)[0].split('#', 1)[0]
    if tpl == '/':
        return '/'
    if not tpl or not PATHLIKE.fullmatch(tpl) or not re.search('[A-Za-z]', tpl):
        return None
    if not tpl.startswith('/'):
        if '/' not in tpl.strip('/') and not tpl.endswith('/') or re.match(r'[\w-]+\.[a-z]{2,4}(?:/|$)', tpl):
            return None
    return norm_path(tpl)


def segments(path):
    return [s.lower() if not s.startswith(':') else ':' for s in path.strip('/').split('/') if s]


def snake(name):
    return SNAKE.sub('_', name).lower()


def plural_forms(word):
    out = {word, word + 's', word + 'es'}
    if word.endswith('y'):
        out.add(word[:-1] + 'ies')
    if word.endswith('s'):
        out.add(word[:-1])
    return out


def singularize(word):
    if word.endswith('ies'):
        return word[:-3] + 'y'
    if word.endswith(('ses', 'xes', 'ches', 'shes')):
        return word[:-2]
    if word.endswith('s') and not word.endswith('ss'):
        return word[:-1]
    return word


def rpc_key(name):
    return name.replace('_', '').lower()


def shared(a, b):
    n = 0
    for x, y in zip(a.split('/')[:-1], b.split('/')[:-1]):
        if x != y:
            break
        n += 1
    return n


def quoted_all(text):
    return [m.group(1) for m in QUOTED.finditer(text or '')]


def first_string(text):
    m = QUOTED.search(text or '')
    return m.group(1) if m else None


def main_verbs(found):
    found = [v for v in dict.fromkeys(v.upper() for v in found) if v in VERBS or v == 'ANY']
    trimmed = [v for v in found if v not in ('HEAD', 'OPTIONS')]
    return trimmed or found or ['ANY']


def ann_path(args):
    for m in STR_LIT.finditer(args or ''):
        if m.group(1) in (None, 'value', 'path', 'template', 'url', 'uri'):
            return m.group(2) if m.group(2) is not None else m.group(3)
    return ''


def next_seg(part):
    if part.startswith('(') and part.endswith(')') or part.startswith('@'):
        return ''
    m = re.fullmatch(r'\[\[?(?:\.\.\.)?(\w+)\]?\]', part)
    return ':' + m.group(1) if m else part


def django_regex(path):
    path = path.lstrip('^').rstrip('$')
    path = re.sub(r'\(\?P<(\w+)>[^)]*\)', r'<\1>', path)
    path = re.sub(r'\(\?:[^)]*\)\??', '', path)
    path = re.sub(r'\([^)]*\)', '<param>', path)
    return path.replace('\\', '').replace('?', '').replace('$', '')


def unq(value):
    return (value or '').strip().strip('\'":[]')


def option_map(text):
    return {k: v for k, v in RAILS_OPT.findall(text or '')}


class Bridges:
    def __init__(self, root, files, g, read_source, is_test):
        self.root, self.g, self.read_source, self.is_test = root, g, read_source, is_test
        self.files = sorted(files)
        self.fileset = set(files)
        self.issues = Issues()
        self.by_file = defaultdict(list)
        self.short = defaultdict(list)
        self.full = defaultdict(list)
        self.owners = defaultdict(list)
        self.tables = defaultdict(list)
        self.table_classes = defaultdict(list)
        for nid, m in sorted(g.nodes.items()):
            if m.get('kind') in ('function', 'method', 'class') and m.get('file'):
                self.by_file[m['file']].append((m.get('line') or 1, m.get('end') or 0, nid))
                self.short[m['name'].rsplit('.', 1)[-1]].append(nid)
                self.full[m['name']].append(nid)
                if m['kind'] == 'method' and '.' in m['name']:
                    self.owners[m['name'].rsplit('.', 1)[0]].append(nid)
            if m.get('table'):
                self.tables[str(m['table']).lower()].append(nid)
                if m.get('kind') == 'class':
                    self.table_classes[m['name'].lower()].append(nid)
        for rel in self.by_file:
            self.by_file[rel].sort()
        self.starts = {rel: [x[0] for x in items] for rel, items in self.by_file.items()}
        self.pending, self.clients, self.mounts = [], [], defaultdict(list)
        self.local = defaultdict(dict)
        self.ep_index = defaultdict(list)
        self.env_defs, self.env_uses = [], []
        self.topic_uses, self.tasks, self.task_calls = [], {}, []
        self.services, self.rpc_pending = {}, []
        self.nest, self.nest_prefix = [], []
        self.js_imports, self.django, self.test_routes = {}, {}, set()
        self.nuxt = any(f.rsplit('/', 1)[-1].startswith('nuxt.config.') for f in files)

    def module(self, rel):
        mid = f'm:{rel}'
        return mid if mid in self.g.nodes else None

    def owner(self, rel, line):
        items = self.by_file.get(rel)
        if items:
            i = bisect_left(self.starts[rel], line + 1) - 1
            steps = 0
            while i >= 0 and steps < 400:
                start, end, nid = items[i]
                if not end or end >= line:
                    return nid
                i -= 1
                steps += 1
        return self.module(rel)

    def pick(self, rel, cands):
        cands = sorted(set(cands))
        if len(cands) <= 1:
            return cands[0] if cands else None
        same = [c for c in cands if self.g.nodes[c]['file'] == rel]
        if len(same) == 1:
            return same[0]
        pool = same or cands
        ranked = sorted(((shared(rel, self.g.nodes[c]['file']), c) for c in pool), key=lambda x: (-x[0], x[1]))
        return ranked[0][1] if ranked[0][0] > ranked[1][0] else None

    def in_file(self, rel, name):
        cands = [n for _, _, n in self.by_file.get(rel, []) if self.g.nodes[n]['name'].rsplit('.', 1)[-1] == name]
        cands.sort(key=lambda n: (self.g.nodes[n]['kind'] == 'class', n))
        return cands[0] if cands else None

    def resolve(self, expr, rel, line=None, owner=None):
        expr = re.sub(r'\.(?:bind|as_view)\([^)]*\)$', '', (expr or '').strip())
        if not expr:
            return None
        m = re.match(r'''^\[\s*\\?([\w\\]+)::class\s*,\s*['"](\w+)['"]\s*\]$''', expr) or \
            re.match(r'''^['"]\\?([\w\\]+)[@:](\w+)['"]$''', expr) or \
            re.match(r'''^\\?([\w\\]+)::class\s*\.\s*['"]:(\w+)['"]$''', expr)
        if m:
            owner, name = m.group(1).rsplit('\\', 1)[-1], m.group(2)
        else:
            m = re.match(r'^\\?([\w\\]+)::class$', expr)
            if m:
                cls = m.group(1).rsplit('\\', 1)[-1]
                return self.pick(rel, self.full.get(f'{cls}.__invoke', [])) or self.pick(rel, [
                    n for n in self.short.get(cls, []) if self.g.nodes[n]['kind'] == 'class'])
            if not re.fullmatch(r'[\w$.:>\-&*]+', expr):
                return None
            parts = [p.lstrip('$&*') for p in re.split(r'\.|::|->', expr)]
            parts = [p for p in parts if p and p not in ('this', 'self', 'static', 'cls')]
            if not parts:
                return None
            name = parts[-1]
            if len(parts) > 1 and not owner:
                owner = parts[-2]
        if owner:
            found = self.pick(rel, self.full.get(f'{owner}.{name}', [])) or self.pick(rel, [
                n for n in self.short.get(name, []) if self.g.nodes[n]['name'].endswith(f'.{owner}.{name}')])
            if found:
                return found
        cands = self.short.get(name, [])
        local = [n for n in cands if self.g.nodes[n]['file'] == rel]
        if local:
            if line is not None and len(local) > 1:
                return min(local, key=lambda n: (abs(self.g.nodes[n]['line'] - line), n))
            return sorted(local)[0]
        return self.pick(rel, cands)

    def decl_after(self, src, pos, name):
        line = src.line(pos)
        cands = [n for s, e, n in self.by_file.get(src.rel, []) if self.g.nodes[n]['name'].rsplit('.', 1)[-1] == name
                 and line - 30 <= s <= line + 30]
        return min(cands, key=lambda n: (abs(self.g.nodes[n]['line'] - line), n)) if cands else None

    def imported(self, src, text):
        head, _, rest = text.partition('.')
        if src.lang == 'js':
            trel = self.js_import_target(src, head)
        elif src.lang == 'py' and rest:
            key = self.py_target(src, text)
            trel = key[0] if key and key[0] != src.rel else None
        else:
            trel = None
        if not trel:
            return None
        name = rest.rsplit('.', 1)[-1] if rest else self.js_imported_name(src, head)
        return (self.in_file(trel, name) if name else None) or self.default_export(trel) or self.module(trel)

    def default_export(self, rel):
        items = self.by_file.get(rel)
        text = self.text(rel) if items and rel.endswith(tuple(k for k, v in EXT_LANG.items() if v == 'js')) else None
        m = JS_DEFAULT_FN.search(text or '')
        return self.in_file(rel, m.group(1)) if m else None

    def handler(self, src, start, end, line):
        text = src.code[start:end].strip()
        flat = src.struct[start:end].strip()
        if not flat:
            return None
        if INLINE.match(flat):
            return self.owner(src.rel, line)
        if re.fullmatch(r'[\w$.:>\-]+', text):
            found = self.imported(src, text)
            if found:
                return found
        found = self.resolve(text, src.rel, line)
        if found or '(' not in flat:
            return found
        if '=>' in flat or re.search(r'\b(?:function|func|fn|lambda|delegate)\b', flat):
            return self.owner(src.rel, line)
        names = [m for m in ARG_NAME.finditer(src.code, start, end)
                 if not src.struct[m.end():m.end() + 1].strip().startswith('(')]
        for m in reversed(names):
            found = self.imported(src, m.group()) or self.resolve(m.group(), src.rel, line)
            if found:
                return found
        return None

    def route(self, src, pos, recv, verbs, tpl, handler, scope='', strict=False):
        if tpl is None:
            return
        if self.is_test(src.rel):
            self.test_routes.add(src.rel)
            return
        dynamic, tpl = '\0' in tpl, drop_base(tpl)
        if '://' in tpl or ' ' in tpl.strip() or (strict and tpl and not tpl.startswith('/')):
            return
        segs = segments(norm_path(tpl))
        if dynamic and segs and all(x == ':' for x in segs):
            return
        line = src.line(pos)
        self.pending.append((src.rel, line, recv or '', tuple(verbs), tpl, handler or '', scope,
                             self.owner(src.rel, line) or ''))

    def client(self, src, pos, method, tpl, sym=None):
        path = client_path(tpl)
        if path is None or src.rel in self.test_routes:
            return
        line = src.line(pos)
        sym = sym or self.owner(src.rel, line)
        if sym:
            self.clients.append((src.rel, line, (method or 'ANY').upper(), path, sym))

    def scopes_at(self, scopes, pos):
        return '/'.join(p.strip('/') for s, e, p in scopes if s <= pos <= e and p.strip('/'))

    def text(self, rel):
        raw = self.read_source(self.root, rel, self.issues)
        if raw is None or b'\0' in raw[:8192]:
            return None
        return raw.decode('utf-8', errors='replace')

    def run(self):
        self.load_protos()
        self.load_env_files()
        for rel in self.files:
            lang = EXT_LANG.get(os.path.splitext(rel)[1])
            name = rel.rsplit('/', 1)[-1]
            if lang:
                text = self.text(rel)
                if text is not None:
                    self.scan(Src(rel, lang, text))
            elif name.startswith(('docker-compose', 'compose.')) or name.endswith(('.yml', '.yaml')):
                self.scan_yaml(rel)
            elif name.startswith(('Dockerfile', 'Containerfile')) or name.endswith('.dockerfile'):
                self.scan_dockerfile(rel)
        self.finish_endpoints()
        self.finish_clients()
        self.finish_rpc()
        self.finish_env()
        self.finish_topics()

    def scan(self, src):
        lang = src.lang
        if lang == 'py':
            self.scan_py(src)
        elif lang == 'js':
            self.scan_js(src)
        elif lang == 'go':
            self.scan_go(src)
        elif lang in ('java', 'kt'):
            self.scan_annotations(src)
            self.scan_java_clients(src)
        elif lang == 'cs':
            self.scan_annotations(src)
            self.scan_cs(src)
        elif lang == 'rb':
            self.scan_rb(src)
        elif lang == 'php':
            self.scan_annotations(src)
            self.scan_php(src)
        elif lang == 'rs':
            self.scan_rs(src)
        elif lang == 'ex':
            self.scan_ex(src)
        self.scan_grpc(src)
        self.scan_env(src)
        self.scan_topics(src)
        self.scan_data(src)

    def scan_env(self, src):
        rx = ENV_USES.get(src.lang)
        if rx is None or not ENV_HINT.search(src.text):
            return
        for m in rx.finditer(src.code):
            self.env_uses.append((src.rel, src.line(m.start()), next(x for x in m.groups() if x)))
        if src.lang == 'js':
            for m in ENV_DESTRUCT.finditer(src.code):
                line = src.line(m.start())
                for part in m.group(1).split(','):
                    name = part.split(':')[0].split('=')[0].strip().lstrip('.')
                    if re.fullmatch(r'[A-Za-z_]\w*', name):
                        self.env_uses.append((src.rel, line, name))

    def scan_topics(self, src):
        lang, code = src.lang, src.code
        for langs, guard, rx, role in TOPICS:
            if lang not in langs or guard not in code:
                continue
            for m in rx.finditer(code):
                role_here = role
                if role == 'kafka':
                    before = code[max(0, m.start() - 300):m.start()]
                    role_here = 'sub' if re.search(r'Reader|Consumer|Subscri', before) else 'pub'
                self.topic_uses.append((m.group(1), src.rel, src.line(m.start()), role_here, '', 'mq'))
        if lang == 'js':
            for rx, role, guard in ((EMIT, 'pub', 'emit('), (LISTEN, 'sub', '(')):
                if guard not in code:
                    continue
                for m in rx.finditer(code):
                    name = m.group(1)
                    if name not in COMMON_EVENTS and len(name) > 2:
                        self.topic_uses.append((name, src.rel, src.line(m.start()), role, '', 'emitter'))
        if lang == 'py' and '@' in code:
            for m in CELERY_TASK.finditer(code):
                d = PY_DEF.match(code, m.end())
                if not d or d.group(1) != 'def':
                    continue
                kw = re.search(r'''\bname\s*=\s*['"]([\w.\-:]+)''', m.group(1) or '')
                fn = self.decl_after(src, d.start(2), d.group(2))
                name = kw.group(1) if kw else d.group(2)
                if fn:
                    self.tasks.setdefault(d.group(2), name)
                    self.topic_uses.append((name, src.rel, src.line(m.start()), 'sub', fn, 'mq'))
        if lang == 'py':
            for m in CELERY_CALL.finditer(code):
                self.task_calls.append((m.group(1), src.rel, src.line(m.start())))

    def scan_data(self, src):
        if not self.tables:
            return
        hits = set()
        for s, e in src.strings:
            if e - s > 20000:
                continue
            content = src.text[s:e]
            head = SQL_HEAD.match(content.lstrip('rRbBuUfF$@`\'"'))
            if not head:
                continue
            for m in SQL_TABLE[head.group(1).isupper()].finditer(content):
                for t in self.tables.get(m.group(1).lower(), []):
                    hits.add((src.line(s), t))
        for rx in ORM.get(src.lang, []):
            for m in rx.finditer(src.code):
                for t in self.table_targets(m.group(1), src.rel):
                    hits.add((src.line(m.start()), t))
        for line, t in sorted(hits):
            sym = self.owner(src.rel, line)
            if sym and sym != t:
                self.g.edge(sym, t, 'data')

    def table_targets(self, name, rel):
        found = list(self.table_classes.get(name.lower(), []))
        if not found:
            for form in sorted(plural_forms(snake(name)) | plural_forms(name.lower())):
                found += self.tables.get(form, [])
        found = sorted(set(found))
        if len(found) <= 1:
            return found
        best = self.pick(rel, found)
        return [best] if best else found[:2]

    def scan_py(self, src):
        code, rel = src.code, src.rel
        for m in PY_ROUTER.finditer(code):
            end = src.close(paren(m))
            pre = PY_PREFIX.search(code, paren(m), end) if end > 0 else None
            if pre:
                self.local[rel][m.group(1)] = (None, pre.group(1))
        for m in PY_DECOR.finditer(code):
            recv, verb = m.group(1), m.group(2)
            args, end = src.args(paren(m))
            if not args:
                continue
            path = None
            for a, b in args:
                kw = re.match(r'\s*(\w+)\s*=(?!=)', src.struct[a:b])
                if kw and kw.group(1) not in ('path', 'rule'):
                    continue
                path = src.expr(a + (kw.end() if kw else 0))
                break
            if path is None:
                continue
            d = PY_DEF.match(code, end + 1)
            argtext = code[m.end():end]
            if verb in ('route', 'api_route'):
                mm = PY_METHODS.search(argtext)
                verbs = main_verbs(quoted_all(mm.group(1))) if mm else ['ANY' if d and d.group(1) == 'class' else 'GET']
            else:
                verbs = ['GET' if verb == 'websocket' else verb.upper()]
            fn = self.decl_after(src, d.start(2), d.group(2)) if d else None
            self.route(src, m.start(), recv.rsplit('.', 1)[-1], verbs, path, fn)
        if 'web.' in code or 'router.add_' in code:
            self.scan_aiohttp(src)
        if 'Route(' in code:
            for m in PY_STARLETTE.finditer(code):
                args, end = src.args(paren(m))
                if len(args) < 2:
                    continue
                mm = PY_METHODS.search(code, m.end(), end)
                verbs = main_verbs(quoted_all(mm.group(1))) if mm else ['ANY']
                a, b = args[1]
                kw = re.match(r'\s*endpoint\s*=\s*', code[a:b])
                self.route(src, m.start(), '', verbs, src.expr(args[0][0]),
                           self.handler(src, a + (kw.end() if kw else 0), b, src.line(m.start())))
        if 'add_url_rule' in code:
            for m in PY_URL_RULE.finditer(code):
                args, end = src.args(paren(m))
                if not args:
                    continue
                argtext = code[m.end():end]
                mm = PY_METHODS.search(argtext)
                verbs = main_verbs(quoted_all(mm.group(1))) if mm else ['GET']
                vf = re.search(r'\bview_func\s*=\s*', argtext)
                if vf:
                    a = m.end() + vf.end()
                    b = next((y for x, y in args if x <= a <= y), end)
                    fn = self.handler(src, a, b, src.line(m.start()))
                else:
                    fn = self.handler(src, *args[2], src.line(m.start())) if len(args) > 2 else None
                self.route(src, m.start(), '', verbs, src.expr(args[0][0]), fn)
        for m in PY_MOUNT.finditer(code):
            args, end = src.args(paren(m))
            if not args:
                continue
            if m.group(2) == 'mount':
                if len(args) < 2:
                    continue
                pre, target = first_string(code[args[0][0]:args[0][1]]), code[args[1][0]:args[1][1]].strip()
            else:
                kw = PY_PREFIX.search(code, m.end(), end)
                pre, target = (kw.group(1) if kw else ''), code[args[0][0]:args[0][1]].strip()
            if pre is None or not re.fullmatch(r'[\w.]+', target):
                continue
            key = self.py_target(src, target)
            if key:
                self.mounts[key].append((rel, m.group(1), pre, ''))
        if 'urlpatterns' in code or 'Router(' in code:
            self.scan_django(src)
        self.scan_py_clients(src)

    def scan_aiohttp(self, src):
        code = src.code
        for m in PY_AIOHTTP.finditer(code):
            args, end = src.args(paren(m))
            verb = m.group(1)
            if verb == 'route':
                if len(args) < 3:
                    continue
                verbs, args = [(first_string(code[args[0][0]:args[0][1]]) or 'ANY').upper()], args[1:]
            elif len(args) < 2:
                continue
            else:
                verbs = ['ANY' if verb == 'view' else verb.upper()]
            self.route(src, m.start(), '', verbs, src.expr(args[0][0]), self.handler(src, *args[1], src.line(m.start())))

    def py_target(self, src, target):
        parts = target.split('.')
        var = parts[-1]
        modname = parts[-2] if len(parts) > 1 else None
        for m in PY_IMPORT.finditer(src.code):
            base = m.group(1)
            for n in m.group(2).split(','):
                bits = [b.strip() for b in n.split(' as ')]
                if not bits[0]:
                    continue
                alias = bits[-1]
                full = (base + bits[0]) if base.endswith('.') else f'{base}.{bits[0]}'
                if modname is None and alias == var:
                    rel = self.py_module(src.rel, base)
                    if rel:
                        return (rel, bits[0])
                    rel = self.py_module(src.rel, full)
                    return (rel, None) if rel else None
                if modname is not None and alias == modname:
                    rel = self.py_module(src.rel, full)
                    if rel:
                        return (rel, var)
        if modname is not None:
            for m in PY_IMPORT_AS.finditer(src.code):
                if (m.group(2) or m.group(1).rsplit('.', 1)[-1]) == modname:
                    rel = self.py_module(src.rel, m.group(1))
                    if rel:
                        return (rel, var)
            return None
        if var in self.local[src.rel] or re.search(rf'^\s*{re.escape(var)}\s*=', src.code, re.M):
            return (src.rel, var)
        return None

    def py_module(self, rel, spec):
        dots = len(spec) - len(spec.lstrip('.'))
        path = spec.lstrip('.').replace('.', '/')
        if dots:
            base = rel.split('/')[:-1]
            base = base[:len(base) - (dots - 1)] if dots > 1 else base
            path = '/'.join(base + ([path] if path else []))
        if not path:
            return None
        for cand in (f'{path}.py', f'{path}/__init__.py'):
            if cand in self.fileset:
                return cand
        if dots:
            return None
        tails = sorted(f for f in self.fileset if f.endswith(('/' + path + '.py', '/' + path + '/__init__.py')))
        if len(tails) == 1:
            return tails[0]
        if tails:
            ranked = sorted(tails, key=lambda f: (-shared(rel, f), f))
            return ranked[0] if shared(rel, ranked[0]) > shared(rel, ranked[1]) else None
        return None

    def django_routers(self, src):
        return set(re.findall(r'\b(\w+)\s*=\s*(?:\w+\.)?(?:Default|Simple|Nested\w*|Extended\w*)Router\(', src.code))

    def scan_django(self, src):
        code, rel = src.code, src.rel
        units = self.django
        routers = self.django_routers(src)
        entries = units.setdefault((rel, None), [])
        if 'urlpatterns' in code:
            for m in PY_URLPATH.finditer(code):
                args, end = src.args(paren(m))
                if len(args) < 2:
                    continue
                lit = src.literal(src.skip(args[0][0]))
                if not lit:
                    continue
                path = lit[0] if m.group(1) == 'path' else django_regex(lit[0])
                target = code[args[1][0]:args[1][1]].strip()
                line = src.line(m.start())
                inc = re.match(r'''include\(\s*(?:\(\s*)?(?:['"]([\w.]+)['"]|([\w.]+))''', target)
                if inc:
                    spec = inc.group(1) or inc.group(2)
                    if inc.group(2) and spec.split('.')[0] in routers:
                        key = (rel, spec.split('.')[0])
                    elif inc.group(1):
                        trel = self.py_module(rel, spec)
                        key = (trel, None) if trel else None
                    else:
                        found = self.py_target(src, spec)
                        key = (found[0], None) if found and found[0] != rel else None
                    if key:
                        entries.append(('include', path, key, line))
                    continue
                entries.append(('route', path, self.handler(src, args[1][0], args[1][1], line), line))
        for var in sorted(routers):
            if re.search(rf'urlpatterns\s*\+?=\s*(?:\[[^\]]*)?\b{var}\.urls', code):
                entries.append(('include', '', (rel, var), 0))
        for m in PY_ROUTER_REG.finditer(code):
            if m.group(1) not in routers:
                continue
            args, end = src.args(paren(m))
            if len(args) < 2:
                continue
            lit = src.literal(src.skip(args[0][0]))
            if not lit:
                continue
            line = src.line(m.start())
            target = self.handler(src, args[1][0], args[1][1], line)
            base = django_regex(lit[0])
            bucket = units.setdefault((rel, m.group(1)), [])
            bucket.append(('route', base, target, line))
            bucket.append(('route', base + '/<pk>', target, line))

    def finish_django(self):
        units = self.django
        included = {key for entries in units.values() for kind, _, key, _ in entries if kind == 'include'}
        seen = set()

        def walk(key, prefix, depth):
            if depth > 6 or (key, prefix) in seen:
                return
            seen.add((key, prefix))
            for kind, path, target, line in units.get(key, []):
                if kind == 'include':
                    walk(target, prefix + '/' + path, depth + 1)
                elif not self.is_test(key[0]):
                    self.pending.append((key[0], line, '', ('ANY',), prefix + '/' + path, target or '', '', ''))

        for key in sorted(k for k in units if k not in included and units[k]):
            walk(key, '', 0)

    def scan_py_clients(self, src):
        code = src.code
        for m in PY_CLIENT.finditer(code):
            recv, verb = m.group(1), m.group(2)
            last = recv.rsplit('.', 1)[-1]
            if last not in PY_CLIENT_NAMES and not last.endswith(('client', 'session')):
                continue
            args, end = src.args(paren(m))
            if not args:
                continue
            if verb == 'request':
                if len(args) < 2:
                    continue
                method = first_string(code[args[0][0]:args[0][1]]) or 'ANY'
                tpl = src.expr(args[1][0])
            else:
                kw = re.match(r'\s*(\w+)\s*=(?!=)', src.struct[args[0][0]:args[0][1]])
                if kw and kw.group(1) != 'url':
                    continue
                method = 'GET' if verb == 'urlopen' else verb
                tpl = src.expr(args[0][0] + (kw.end() if kw else 0))
            self.client(src, m.start(), method, tpl)

    def js_server_vars(self, src):
        names = set(JS_SERVER_VAR.findall(src.code))
        if JS_SERVER_IMPORT.search(src.code):
            names |= JS_SERVER_NAMES
        return names

    def js_import_map(self, src):
        imports = self.js_imports.get(src.rel)
        if imports is None:
            imports = {}
            for m in JS_IMPORT.finditer(src.code):
                spec = m.group(5) or m.group(7)
                for name in (m.group(1), m.group(2), m.group(6)):
                    if name:
                        imports[name] = (spec, None)
                for group in (m.group(3), m.group(4)):
                    for part in (group or '').split(','):
                        bits = [b.strip() for b in part.strip().split(' as ')]
                        if bits[0]:
                            imports[bits[-1]] = (spec, bits[0])
            self.js_imports[src.rel] = imports
        return imports

    def js_resolve_spec(self, rel, spec):
        if not spec or not spec.startswith('.'):
            return None
        base = os.path.normpath(os.path.join(os.path.dirname(rel), spec)).replace(os.sep, '/')
        for suffix in ('', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '/index.ts', '/index.js', '/index.tsx', '/index.mjs'):
            if base + suffix in self.fileset:
                return base + suffix
        stem = os.path.splitext(base)[0]
        for suffix in ('.ts', '.tsx'):
            if stem + suffix in self.fileset:
                return stem + suffix
        return None

    def js_import_target(self, src, ident):
        found = self.js_import_map(src).get(ident)
        return self.js_resolve_spec(src.rel, found[0]) if found else None

    def js_imported_name(self, src, ident):
        found = self.js_import_map(src).get(ident)
        return found[1] if found and found[1] else None

    def scan_js(self, src):
        code = src.code
        self.scan_js_files(src)
        servers = self.js_server_vars(src)
        if servers:
            self.scan_js_server(src, servers)
        if '@nestjs' in code or 'setGlobalPrefix' in code:
            self.nest_prefix += NEST_PREFIX.findall(code)
            if '@nestjs' in code:
                self.scan_annotations(src)
        self.scan_js_clients(src, servers)

    def scan_js_server(self, src, servers):
        code, rel = src.code, src.rel
        for m in JS_ROUTE.finditer(code):
            recv, verb = m.group(1), m.group(2)
            if recv not in servers:
                continue
            args, end = src.args(paren(m))
            if len(args) < 2:
                continue
            verb = {'del': 'DELETE', 'all': 'ANY'}.get(verb, verb.upper())
            self.route(src, m.start(), recv, [verb], src.expr(args[0][0]),
                       self.handler(src, *args[-1], src.line(m.start())), strict=True)
        for m in JS_CHAIN_ROUTE.finditer(code):
            if m.group(1) not in servers:
                continue
            args, end = src.args(paren(m))
            if not args:
                continue
            first = code[args[0][0]:args[0][1]]
            if first.strip().startswith('{'):
                mm, uu = METHOD_KW.search(first), URL_KW.search(first)
                hh = re.search(r'\bhandler\s*:\s*([\w.]+)', first)
                if uu:
                    fn = self.resolve(hh.group(1), rel) if hh else self.owner(rel, src.line(m.start()))
                    self.route(src, m.start(), m.group(1), [(mm.group(1) if mm else 'ANY').upper()],
                               src.expr(args[0][0] + uu.end()), fn, strict=True)
                continue
            if len(args) == 2:
                self.js_mount(src, m.group(1), src.expr(args[0][0]), code[args[1][0]:args[1][1]].strip())
                continue
            tpl, p = src.expr(args[0][0]), end + 1
            while True:
                c = JS_CHAIN_VERB.match(code, p)
                if not c:
                    break
                cargs, cend = src.args(c.end() - 1)
                if cend < 0:
                    break
                fn = self.handler(src, *cargs[-1], src.line(m.start())) if cargs else None
                self.route(src, c.start(), m.group(1), ['ANY' if c.group(1) == 'all' else c.group(1).upper()], tpl, fn,
                           strict=True)
                p = cend + 1
        for m in JS_MOUNT.finditer(code):
            if m.group(1) not in servers:
                continue
            args, end = src.args(paren(m))
            if m.group(2) == 'register':
                if len(args) >= 2:
                    pre = re.search(r'''\bprefix\s*:\s*['"`]([^'"`]*)''', code[args[1][0]:args[1][1]])
                    if pre:
                        self.js_mount(src, m.group(1), pre.group(1), code[args[0][0]:args[0][1]].strip())
                continue
            if len(args) < 2 or not src.literal(src.skip(args[0][0])):
                continue
            self.js_mount(src, m.group(1), src.expr(args[0][0]), code[args[-1][0]:args[-1][1]].strip())

    def js_mount(self, src, recv, prefix, target):
        if prefix is None:
            return
        prefix = drop_base(prefix)
        target = re.sub(r'\.routes\(\)$|\.router$|\(\)$', '', target)
        req = re.match(r'''require\(\s*['"]([^'"]+)['"]\s*\)''', target)
        if req:
            trel = self.js_resolve_spec(src.rel, req.group(1))
        elif re.fullmatch(r'[\w$]+', target):
            trel = self.js_import_target(src, target)
        else:
            return
        if trel:
            self.mounts[(trel, None)].append((src.rel, recv, prefix, ''))
        elif not req and re.search(rf'\b{re.escape(target)}\s*=', src.code):
            self.local[src.rel][target] = (recv, prefix)

    def scan_js_files(self, src):
        rel = src.rel
        parts = rel.split('/')
        dirs, stem = parts[:-1], os.path.splitext(parts[-1])[0]
        if self.is_test(rel):
            return
        if stem == 'route' and 'app' in dirs:
            i = len(dirs) - 1 - dirs[::-1].index('app')
            self.export_routes(src, '/'.join(next_seg(p) for p in dirs[i + 1:]))
        elif stem == '+server' and 'routes' in dirs:
            i = len(dirs) - 1 - dirs[::-1].index('routes')
            self.export_routes(src, '/'.join(next_seg(p) for p in dirs[i + 1:]))
        elif 'pages' in dirs and dirs[dirs.index('pages') + 1:dirs.index('pages') + 2] == ['api']:
            i = dirs.index('pages')
            segs = [next_seg(p) for p in dirs[i + 1:]] + ([] if stem == 'index' else [next_seg(stem)])
            m = JS_DEFAULT_FN.search(src.code)
            if m or 'export default' in src.code:
                fn = self.in_file(rel, m.group(1)) if m else None
                self.route(src, 0, '', ['ANY'], '/'.join(segs), fn or self.module(rel))
        elif self.nuxt and 'server' in dirs and dirs[dirs.index('server') + 1:dirs.index('server') + 2] in (['api'], ['routes']):
            i = dirs.index('server')
            bits = stem.split('.')
            verb = bits[-1].upper() if len(bits) > 1 and bits[-1].upper() in VERBS else 'ANY'
            base = bits[0] if verb != 'ANY' else stem
            prefix = ['api'] if dirs[i + 1] == 'api' else []
            segs = prefix + [next_seg(p) for p in dirs[i + 2:]] + ([] if base == 'index' else [next_seg(base)])
            self.route(src, 0, '', [verb], '/'.join(segs), self.module(rel))

    def export_routes(self, src, path):
        for m in JS_NEXT_EXPORT.finditer(src.code):
            if m.group(1):
                found = [(m.group(1), m.group(1))]
            else:
                found = []
                for part in m.group(2).split(','):
                    bits = [b.strip() for b in part.split(' as ')]
                    if bits[-1] in VERBS:
                        found.append((bits[-1], bits[0]))
            for verb, local in found:
                fn = self.in_file(src.rel, local) or self.module(src.rel)
                self.route(src, m.start(), '', [verb], path, fn)

    def scan_js_clients(self, src, servers):
        code = src.code
        for m in JS_CLIENT.finditer(code):
            args, end = src.args(paren(m))
            if not args:
                continue
            a, b = args[0]
            first = code[a:b]
            opts = code[args[1][0]:args[1][1]] if len(args) > 1 else ''
            if first.strip().startswith('{'):
                uu = URL_KW.search(first)
                if not uu:
                    continue
                tpl, opts = src.expr(a + uu.end()), first
            else:
                tpl = src.expr(a)
            mm = METHOD_KW.search(opts)
            self.client(src, m.start(), mm.group(1) if mm else ('ANY' if m.group(1) == 'request' else 'GET'), tpl)
        for m in JS_CLIENT_METHOD.finditer(code):
            recv, verb = m.group(1), m.group(2)
            if recv in servers or not JS_CLIENT_NAMES.match(recv):
                continue
            args, end = src.args(paren(m))
            if not args:
                continue
            if verb == 'request':
                a, b = args[0]
                obj = code[a:b]
                uu, mm = URL_KW.search(obj), METHOD_KW.search(obj)
                if uu:
                    self.client(src, m.start(), mm.group(1) if mm else 'ANY', src.expr(a + uu.end()))
                continue
            self.client(src, m.start(), verb, src.expr(args[0][0]))

    def scan_annotations(self, src):
        code, s, rel = src.code, src.struct, src.rel
        if not re.search(r'^[ \t]*(?:@\w|\[\w|#\[)', s, re.M):
            return
        classes = []
        for m in CLASS_ANY.finditer(s):
            brace = s.find('{', m.end())
            semi = s.find(';', m.end())
            if brace < 0 or (0 <= semi < brace and src.lang != 'kt'):
                continue
            end = src.close(brace)
            classes.append([m.start(), end if end > 0 else len(s), m.group(1), {}])
        blocks, done = [], -1
        for m in ANN_START.finditer(s):
            if m.start() < done:
                continue
            p, anns = m.start(), []
            while True:
                p = src.skip(p)
                if s.startswith('@', p) and p + 1 < len(s) and s[p + 1].isalpha():
                    nm = ANN_NAME.match(s, p + 1)
                    q = q2 = nm.end()
                    while q2 < len(s) and s[q2] in ' \t':
                        q2 += 1
                    args = ''
                    if s.startswith('(', q2):
                        e = src.close(q2)
                        if e < 0:
                            break
                        args, q = code[q2 + 1:e], e + 1
                    anns.append((nm.group().rsplit('.', 1)[-1], args, p))
                    p = q
                elif src.lang in ('cs', 'php') and (s.startswith('[', p) or s.startswith('#[', p)):
                    o = p + (1 if s[p] == '[' else 2)
                    if o >= len(s) or not s[o].isalpha():
                        break
                    inner, e = src.args(o - 1)
                    if e < 0:
                        break
                    for a, b in inner:
                        nm = re.match(r'\s*(?:\w+:\s*)?([\w.\\]+)\s*(?:\((.*)\))?\s*$', code[a:b], re.S)
                        if nm:
                            anns.append((re.split(r'[.\\]', nm.group(1))[-1], nm.group(2) or '', a))
                    p = e + 1
                else:
                    break
            done = p
            if not anns:
                continue
            window = s[p:p + 600]
            cm = CLASS_DECL.match(window)
            if cm:
                blocks.append(('class', cm.group(1), anns, p))
                continue
            fm = FUN_DECL.match(window) if src.lang == 'kt' else None
            stop = min([i for i in (window.find('{'), window.find(';'), window.find('=>')) if i >= 0] or [len(window)])
            name = fm.group(1) if fm else next((c.group(1) for c in CALL_NAME.finditer(window[:stop + 1])
                                                if c.group(1) not in KEYWORDS), None)
            if name:
                blocks.append(('method', name, anns, p))
        for kind, name, anns, p in blocks:
            if kind == 'class':
                for c in classes:
                    if c[2] == name and p - 5 <= c[0] <= p + 300:
                        c[3] = self.class_meta(anns, name)
                        break
        for kind, name, anns, p in blocks:
            if kind != 'method':
                continue
            owner = None
            for c in classes:
                if c[0] <= p <= c[1] and (owner is None or c[0] >= owner[0]):
                    owner = c
            cname = owner[2] if owner else None
            fid = f'f:{rel}:{cname}.{name}'
            fn = fid if fid in self.g.nodes else self.decl_after(src, p, name)
            self.method_annotations(src, p, anns, owner[3] if owner else {}, cname, name, fn)

    def class_meta(self, anns, name):
        meta = {'prefix': '', 'client': False}
        for ann, args, _ in anns:
            if ann in ('RequestMapping', 'Path', 'Controller', 'RestController', 'Route', 'HttpExchange', 'RoutePrefix'):
                path = ann_path(args)
                if ann == 'Controller' and not path:
                    m = re.search(r'''\bpath\s*:\s*['"`]([^'"`]*)''', args)
                    path = m.group(1) if m else ''
                if path:
                    meta['prefix'] = path.replace('[controller]', re.sub(r'Controller$', '', name))
                meta['client'] = meta['client'] or ann == 'HttpExchange'
            elif ann == 'FeignClient':
                meta['client'] = True
                m = re.search(r'''\bpath\s*=\s*"([^"]*)"''', args)
                if m:
                    meta['prefix'] = m.group(1)
        return meta

    def method_annotations(self, src, p, anns, meta, cname, name, fn):
        verbs, path, kind, jax = [], None, None, None
        for ann, args, at in anns:
            if ann in SPRING_VERB and src.lang in ('java', 'kt'):
                verbs.append(SPRING_VERB[ann])
                path, kind = ann_path(args), 'spring'
                found = re.findall(r'RequestMethod\.(\w+)', args)
                if ann == 'RequestMapping' and found:
                    verbs = found
            elif ann in CAP_VERB and src.lang in ('js', 'java', 'kt'):
                verbs.append(CAP_VERB[ann])
                path, kind = ann_path(args), 'nest'
            elif ann in VERBS and src.lang in ('java', 'kt'):
                verbs.append(ann)
                if args.strip():
                    path, kind = ann_path(args), 'retrofit'
                else:
                    kind = kind or 'jaxrs'
            elif ann == 'Path' and src.lang in ('java', 'kt'):
                jax = ann_path(args)
            elif ann in NET_VERB and src.lang == 'cs':
                verbs.append(NET_VERB[ann])
                path, kind = (ann_path(args) if args.strip() else (path or '')), 'net'
            elif ann == 'Route' and src.lang in ('cs', 'php'):
                path, kind = ann_path(args), kind or ('net' if src.lang == 'cs' else 'symfony')
                mm = re.search(r'methods\s*:\s*\[([^\]]*)\]', args) if src.lang == 'php' else None
                if mm:
                    verbs += quoted_all(mm.group(1))
            elif ann in LISTENERS and src.lang in ('java', 'kt'):
                for key in LISTENERS[ann]:
                    mm = re.search(rf'\b{key}\s*=\s*\{{?([^}})]*)', args)
                    names = quoted_all(mm.group(1)) if mm else ([] if '=' in args.split('"')[0] else quoted_all(args))
                    if names:
                        for t in names:
                            if not t.startswith('$') and '#{' not in t:
                                self.topic_uses.append((t, src.rel, src.line(at), 'sub', fn or '', 'mq'))
                        break
        if kind == 'jaxrs':
            path = jax or ''
        if kind is None or path is None:
            return
        full = path.lstrip('~') if kind == 'net' and path.startswith(('/', '~/')) else (meta.get('prefix') or '') + '/' + path
        full = full.replace('[controller]', re.sub(r'Controller$', '', cname or '')).replace('[action]', name)
        verbs = main_verbs(verbs)
        if kind == 'retrofit' or meta.get('client'):
            for v in verbs:
                self.client(src, p, v, full, fn or self.owner(src.rel, src.line(p)))
        elif kind == 'nest':
            if not self.is_test(src.rel):
                self.nest.append((src.rel, src.line(p), tuple(verbs), full, fn or ''))
        else:
            self.route(src, p, '', verbs, full, fn)

    def scan_java_clients(self, src):
        code = src.code
        for m in JAVA_CLIENT.finditer(code):
            verb = m.group(1)
            if verb in ('put', 'delete', 'exchange') and not re.search(r'(?i)(rest|template|client)\w*\s*$', code[max(0, m.start() - 40):m.start()]):
                continue
            args, end = src.args(paren(m))
            if not args:
                continue
            if verb == 'exchange':
                hm = re.search(r'HttpMethod\.(\w+)', code[m.end():end])
                method = hm.group(1) if hm else 'ANY'
            else:
                method = re.match(r'[a-z]+', verb).group()
            self.client(src, m.start(), method, src.expr(args[0][0]))
        for m in JAVA_WEBCLIENT.finditer(code):
            self.client(src, m.start(), m.group(1), src.expr(m.end()))

    def scan_cs(self, src):
        code, rel = src.code, src.rel
        for m in CS_GROUP.finditer(code):
            lit = src.expr(m.end())
            if lit is not None:
                self.local[rel][m.group(1)] = (m.group(2), drop_base(lit))
        for m in CS_MAP.finditer(code):
            args, end = src.args(paren(m))
            if len(args) < 2:
                continue
            if m.group(2) == 'Methods':
                if len(args) < 3:
                    continue
                verbs = main_verbs(quoted_all(code[args[1][0]:args[1][1]]))
            else:
                verbs = [m.group(2).upper()]
            self.route(src, m.start(), m.group(1), verbs, src.expr(args[0][0]), self.handler(src, *args[-1], src.line(m.start())))
        for m in CS_CLIENT.finditer(code):
            verb = re.match(r'[A-Z][a-z]+', m.group(1)).group()
            self.client(src, m.start(), verb, src.expr(m.end()))
        for m in CS_REQUEST.finditer(code):
            self.client(src, m.start(), m.group(1), src.expr(m.end()))

    def scan_go(self, src):
        code, rel = src.code, src.rel
        scopes = []
        for m in GO_ROUTE_BLOCK.finditer(code):
            brace = src.struct.find('{', m.end())
            if brace > 0:
                scopes.append((brace, src.close(brace), m.group(1)))
        for m in GO_GROUP.finditer(code):
            lit = src.expr(m.end())
            if lit is not None:
                self.local[rel][m.group(1)] = (m.group(2), drop_base(lit))
        for m in GO_ROUTE.finditer(code):
            recv, verb = m.group(1), m.group(2)
            if recv in ('http', 'client', 'httpClient', 'c', 'cli') and verb in ('Get', 'Post', 'Head'):
                continue
            args, end = src.args(paren(m))
            if len(args) < 2:
                continue
            first, verbs = args[0], None
            if verb in ('Handle', 'HandleFunc') and len(args) >= 3:
                lit = src.literal(src.skip(first[0]))
                if lit and lit[0].isupper() and '/' not in lit[0]:
                    verbs, first = [lit[0]], args[1]
            tpl = src.expr(first[0])
            if tpl is None:
                continue
            lead = re.match(r'^([A-Z]+)\s+(.*)$', tpl)
            if lead and lead.group(1) in VERBS:
                verbs, tpl = [lead.group(1)], lead.group(2)
            if verbs is None:
                if verb in ('Handle', 'HandleFunc'):
                    chain = GO_METHODS.match(code, end + 1)
                    verbs = main_verbs([v for pair in re.findall(r'"(\w+)"|Method(\w+)', chain.group(1)) for v in pair if v]) \
                        if chain else ['ANY']
                else:
                    verbs = ['ANY' if verb == 'Any' else verb.upper()]
            self.route(src, m.start(), recv, verbs, tpl, self.handler(src, *args[-1], src.line(m.start())),
                       self.scopes_at(scopes, m.start()), strict=True)
        for m in GO_CLIENT.finditer(code):
            self.client(src, m.start(), m.group(2).replace('PostForm', 'Post'), src.expr(m.end()))
        for m in GO_NEWREQ.finditer(code):
            self.client(src, m.start(), m.group(1) or m.group(2), src.expr(m.end()))
        for m in GO_RESTY.finditer(code):
            self.client(src, m.start(), m.group(1), src.expr(m.end()))

    def scan_rb(self, src):
        rel = src.rel
        if rel.rsplit('/', 1)[-1] == 'routes.rb' or '/config/routes/' in f'/{rel}':
            self.scan_rails(src)
        elif re.search(r'\bSinatra\b|require\s+[\'"]sinatra', src.code):
            for m in RB_SINATRA.finditer(src.code):
                self.route(src, m.start(), '', [m.group(1).upper()], m.group(3), self.owner(rel, src.line(m.start())))
        for m in RB_CLIENT.finditer(src.code):
            self.client(src, m.start(), m.group(2), src.expr(m.end()))

    def scan_rails(self, src):
        if self.is_test(src.rel):
            return
        stack = []
        codes = src.code.split('\n')
        for i, raw in enumerate(src.struct.split('\n')):
            line, text = raw.strip(), codes[i].strip()
            if not line:
                continue
            if RB_END.match(line):
                if stack:
                    stack.pop()
                continue
            opens = bool(RB_OPENER.search(line))
            m = RAILS_RES.match(text)
            if m:
                names = re.findall(r':(\w+)', m.group(2))
                opts = option_map(m.group(3))
                for res in names:
                    self.rails_resources(src, i + 1, stack, m.group(1) == 'resource', res, opts)
                if opens:
                    stack.append(('res', names[-1], m.group(1) == 'resource', opts))
                continue
            m = RAILS_VERB.match(text)
            if m and (m.group(1) != 'match' or m.group(3) or m.group(4)):
                self.rails_verb(src, i + 1, stack, m)
                if opens:
                    stack.append(('none',))
                continue
            m = RAILS_SCOPE.match(text)
            if m and opens:
                kind, arg = m.group(1), m.group(2) or m.group(4) or ''
                opts = option_map(m.group(5))
                if kind == 'namespace':
                    stack.append(('scope', arg, arg))
                elif kind == 'scope':
                    stack.append(('scope', unq(opts.get('path', arg)), unq(opts.get('module', ''))))
                elif kind in ('member', 'collection'):
                    stack.append((kind,))
                elif kind == 'controller':
                    stack.append(('ctrl', arg))
                else:
                    stack.append(('none',))
                continue
            if opens:
                stack.append(('none',))

    def rails_prefix(self, stack, member=False):
        path, modules, ctrl = [], [], None
        for idx, item in enumerate(stack):
            if item[0] == 'scope':
                if item[1].strip('/'):
                    path.append(item[1].strip('/'))
                if item[2]:
                    modules.append(item[2].strip('/'))
            elif item[0] == 'res':
                res, singular, opts = item[1], item[2], item[3]
                path.append(unq(opts.get('path', res)))
                inner = next((x[0] for x in stack[idx + 1:] if x[0] in ('member', 'collection', 'res')), None)
                if not singular and inner != 'collection':
                    path.append(':id' if inner == 'member' or (inner is None and member) else f':{singularize(res)}_id')
                ctrl = unq(opts.get('controller', res if not singular else res + 's'))
            elif item[0] == 'ctrl':
                ctrl = item[1]
        return path, modules, ctrl

    def rails_resources(self, src, line, stack, singular, res, opts):
        path, modules, _ = self.rails_prefix(stack)
        only = set(re.findall(r'\w+', opts['only'])) if 'only' in opts else None
        excluded = set(re.findall(r'\w+', opts.get('except', '')))
        seg = unq(opts.get('path', res))
        ctrl = unq(opts.get('controller', res if not singular else res + 's'))
        for action, verb, suffix in RAILS_ACTIONS:
            if singular and action == 'index' or (only is not None and action not in only) or action in excluded:
                continue
            suffix = suffix.replace('/:id', '') if singular else suffix
            self.rails_route(src, line, verb, '/'.join(path + [seg]) + suffix, modules, ctrl, action)

    def rails_verb(self, src, line, stack, m):
        verb, lit, sym, rest = m.group(1), m.group(3), m.group(4), m.group(5) or ''
        opts = option_map(rest)
        to = RAILS_TO.search(rest)
        in_res = any(x[0] == 'res' for x in stack)
        member = opts.get('on') == ':member' or (in_res and opts.get('on') != ':collection')
        path, modules, ctrl = self.rails_prefix(stack, member=member)
        if verb == 'root':
            target = to or (re.match(r'([\w/]+)#(\w+)', lit) if lit else None)
            if target:
                self.rails_route(src, line, 'GET', '/'.join(path), modules, target.group(1), target.group(2))
            return
        seg = '' if lit and '#' in lit else (lit if lit is not None else (sym or ''))
        if to:
            ctrl, action = to.group(1), to.group(2)
        elif lit and '#' in lit:
            ctrl, action = lit.split('#', 1)
        else:
            action = unq(opts.get('action', '')) or sym or (seg.strip('/').split('/')[-1] if seg else '')
            ctrl = unq(opts.get('controller', '')) or ctrl or (seg.strip('/').split('/')[0] if seg else None)
        verbs = [verb.upper()] if verb != 'match' else main_verbs(re.findall(r'\w+', opts.get('via', 'any')))
        for v in verbs:
            self.rails_route(src, line, v, '/'.join(path + [seg.strip('/')]), modules, ctrl, action)

    def rails_route(self, src, line, verb, path, modules, ctrl, action):
        fn = None
        if ctrl and action:
            sub = '/'.join(p for p in modules + [ctrl] if p)
            files = [f for f in self.by_file if f.endswith(f'controllers/{sub}_controller.rb')]
            if not files and modules:
                files = [f for f in self.by_file if f.endswith(f'controllers/{ctrl}_controller.rb')]
            if len(files) == 1:
                cls = ''.join(w.capitalize() for w in ctrl.split('/')[-1].split('_')) + 'Controller'
                items = [n for _, _, n in self.by_file[files[0]]]
                fn = next((n for n in items if self.g.nodes[n]['name'] == f'{cls}.{action}'), None) or \
                    next((n for n in items if self.g.nodes[n]['name'] == cls), None)
        self.pending.append((src.rel, line, '', (verb,), '/' + path, fn or '', '', ''))

    def scan_php(self, src):
        code, rel = src.code, src.rel
        scopes, defaults = [], []
        if 'group' in code:
            for m in PHP_GROUP.finditer(code):
                open_pos = paren(m)
                args, end = src.args(open_pos)
                if end < 0:
                    continue
                start = max(code.rfind(';', 0, m.start()), code.rfind('{', 0, m.start()), code.rfind('}', 0, m.start())) + 1
                chain = code[start:m.start()]
                pre = re.search(r'''\bprefix\(\s*['"]([^'"]*)['"]''', chain)
                first = code[args[0][0]:args[0][1]] if args else ''
                arr = re.search(r'''['"]prefix['"]\s*=>\s*['"]([^'"]*)['"]''', first)
                lit = src.literal(src.skip(args[0][0])) if args else None
                prefix = pre.group(1) if pre else arr.group(1) if arr else lit[0] if lit else ''
                scopes.append((open_pos, end, prefix))
                ctl = re.search(r'\bcontroller\(\s*\\?([\w\\]+)::class', chain)
                if ctl:
                    defaults.append((open_pos, end, ctl.group(1).rsplit('\\', 1)[-1]))
        base = 'api' if rel.endswith('routes/api.php') else ''

        def scope_of(pos):
            return '/'.join(x for x in (base, self.scopes_at(scopes, pos)) if x)

        for m in PHP_ROUTE.finditer(code):
            args, end = src.args(paren(m))
            verb = m.group(1)
            if verb == 'match':
                if len(args) < 3:
                    continue
                verbs, args = main_verbs(quoted_all(code[args[0][0]:args[0][1]])), args[1:]
            else:
                verbs = ['ANY' if verb == 'any' else verb.upper()]
            if len(args) < 2:
                continue
            target = code[args[1][0]:args[1][1]].strip()
            ctl = next((c for s, e, c in reversed(defaults) if s <= m.start() <= e), None)
            if ctl and re.fullmatch(r'''['"]\w+['"]''', target):
                fn = self.resolve(target[1:-1], rel, owner=ctl)
            else:
                fn = self.handler(src, args[1][0], args[1][1], src.line(m.start()))
            self.route(src, m.start(), '', verbs, src.expr(args[0][0]), fn, scope_of(m.start()))
        for m in PHP_RESOURCE.finditer(code):
            args, end = src.args(paren(m))
            if len(args) < 2:
                continue
            lit = src.literal(src.skip(args[0][0]))
            cls = re.match(r'\s*\\?([\w\\]+)::class', code[args[1][0]:args[1][1]])
            if not lit or not cls:
                continue
            cls = cls.group(1).rsplit('\\', 1)[-1]
            stop = code.find(';', end)
            tail = code[end:stop if stop > 0 else end + 200]
            only = re.search(r'->only\(\s*\[?([^\])]*)', tail)
            exc = re.search(r'->except\(\s*\[?([^\])]*)', tail)
            only = set(quoted_all(only.group(1))) if only else None
            exc = set(quoted_all(exc.group(1))) if exc else set()
            segs = lit[0].strip('/').split('.')
            path = '/'.join([f'{s}/{{{singularize(s)}}}' for s in segs[:-1]] + [segs[-1]])
            param = '{' + singularize(segs[-1]).replace('-', '_') + '}'
            for action, verb, suffix in LARAVEL_ACTIONS:
                if m.group(1) == 'apiResource' and action in ('create', 'edit'):
                    continue
                if (only is not None and action not in only) or action in exc:
                    continue
                self.route(src, m.start(), '', [verb], path + suffix.replace(':p', param),
                           self.resolve(action, rel, owner=cls), scope_of(m.start()))
        for m in PHP_VAR_ROUTE.finditer(code):
            if m.group(1) not in PHP_SERVER_VARS:
                continue
            args, end = src.args(paren(m))
            verb = m.group(2)
            if verb == 'map':
                if len(args) < 3:
                    continue
                verbs, args = main_verbs(quoted_all(code[args[0][0]:args[0][1]])), args[1:]
            else:
                verbs = ['ANY' if verb == 'any' else verb.upper()]
            if len(args) < 2 or not src.literal(src.skip(args[0][0])):
                continue
            self.route(src, m.start(), m.group(1), verbs, src.expr(args[0][0]),
                       self.handler(src, args[1][0], args[1][1], src.line(m.start())), scope_of(m.start()), strict=True)
        for m in PHP_CLIENT.finditer(code):
            if m.group(1) == 'request':
                args, end = src.args(paren(m))
                if len(args) >= 2:
                    self.client(src, m.start(), first_string(code[args[0][0]:args[0][1]]) or 'ANY', src.expr(args[1][0]))
            else:
                self.client(src, m.start(), m.group(1), src.expr(m.end()))

    def scan_rs(self, src):
        code, rel = src.code, src.rel
        scopes = []
        for m in RS_SCOPE.finditer(code):
            end = -1
            depth = 0
            for i in range(m.start() - 1, max(-1, m.start() - 4000), -1):
                ch = src.struct[i]
                if ch in ')]}':
                    depth += 1
                elif ch in '([{':
                    if depth == 0:
                        end = src.close(i)
                        break
                    depth -= 1
            if end < 0:
                stop = code.find(';', m.end())
                end = stop if stop > 0 else len(code)
            scopes.append((m.end(), end, m.group(1)))
        for m in RS_ATTR.finditer(code):
            d = RS_FN.match(code, code.find(']', m.end()) + 1)
            fn = self.decl_after(src, d.start(1), d.group(1)) if d else None
            self.route(src, m.start(), '', [m.group(1).upper()], m.group(2), fn, self.scopes_at(scopes, m.start()))
        for m in RS_ROUTE.finditer(code):
            args, end = src.args(paren(m))
            if len(args) < 2:
                continue
            body = code[args[1][0]:args[1][1]]
            for verb, target in RS_ACTIX_VERB.findall(body) or RS_AXUM_VERB.findall(body):
                self.route(src, m.start(), '', ['ANY' if verb == 'any' else verb.upper()], m.group(1),
                           self.resolve(target.replace('::', '.'), rel, src.line(m.start())), self.scopes_at(scopes, m.start()))
        for m in RS_RESOURCE.finditer(code):
            stop = code.find(';', m.end())
            chain = code[m.end():stop if stop > 0 else m.end() + 400]
            cut = chain.find('web::resource')
            chain = chain[:cut] if cut > 0 else chain
            found = RS_ACTIX_VERB.findall(chain) or [('any', t) for t in re.findall(r'^\s*\.\s*to\(\s*([\w:]+)', chain)]
            for verb, target in found:
                self.route(src, m.start(), '', ['ANY' if verb == 'any' else verb.upper()], m.group(1),
                           self.resolve(target.replace('::', '.'), rel, src.line(m.start())), self.scopes_at(scopes, m.start()))
        for m in RS_NEST.finditer(code):
            fn = self.resolve(m.group(2).replace('::', '.'), rel)
            if fn:
                self.mounts[('sym', fn)].append((rel, '', m.group(1), self.owner(rel, src.line(m.start())) or ''))
        for m in RS_CLIENT.finditer(code):
            self.client(src, m.start(), m.group(1), src.expr(m.end()))

    def scan_ex(self, src):
        if 'Phoenix.Router' in src.code:
            self.scan_phoenix(src)
        for m in EX_CLIENT.finditer(src.code):
            self.client(src, m.start(), m.group(1), src.expr(m.end()))

    def scan_phoenix(self, src):
        if self.is_test(src.rel):
            return
        stack = []
        for i, raw in enumerate(src.code.split('\n')):
            line = raw.strip()
            if not line:
                continue
            if RB_END.match(line):
                if stack:
                    stack.pop()
                continue
            opens = bool(re.search(r'\bdo\s*$', line)) or line.startswith('fn') and line.endswith('->')
            prefix = '/'.join(x[1].strip('/') for x in stack if x[1].strip('/'))
            m = EX_SCOPE.match(line)
            if m:
                if opens:
                    stack.append(('scope', m.group(1)))
                continue
            m = EX_RES.match(line)
            if m:
                ctrl, rest, seg = m.group(2), m.group(3), m.group(1).strip('/')
                only = re.search(r'only:\s*\[([^\]]*)\]', rest)
                exc = re.search(r'except:\s*\[([^\]]*)\]', rest)
                only = set(re.findall(r':(\w+)', only.group(1))) if only else None
                exc = set(re.findall(r':(\w+)', exc.group(1))) if exc else set()
                for action, verb, suffix in RAILS_ACTIONS:
                    if (only is not None and action not in only) or action in exc:
                        continue
                    self.phoenix_route(src, i + 1, verb, f'{prefix}/{seg}{suffix}', ctrl, action)
                if opens:
                    stack.append(('res', f'{seg}/:{singularize(seg.split("/")[-1])}_id'))
                continue
            m = EX_VERB.match(line)
            if m:
                verb = {'live': 'GET', 'forward': 'ANY'}.get(m.group(1), m.group(1).upper())
                self.phoenix_route(src, i + 1, verb, f'{prefix}/{m.group(2)}', m.group(3), m.group(4))
                if opens:
                    stack.append(('none', ''))
                continue
            if opens:
                stack.append(('none', ''))

    def phoenix_route(self, src, line, verb, path, ctrl, action):
        short = ctrl.rsplit('.', 1)[-1]
        fn = self.pick(src.rel, [n for n in self.short.get(action, []) if self.g.nodes[n]['name'].endswith(f'{short}.{action}')]) \
            if action else None
        fn = fn or self.pick(src.rel, [n for n in self.full.get(ctrl, []) + self.short.get(short, [])
                                       if self.g.nodes[n]['kind'] == 'class'])
        self.pending.append((src.rel, line, '', (verb,), path, fn or '', '', ''))

    def load_protos(self):
        groups, pkgs = defaultdict(list), {}
        for nid, m in sorted(self.g.nodes.items()):
            rel = m.get('file') or ''
            if m.get('kind') != 'method' or not rel.endswith('.proto') or '.' not in m['name'] or self.is_test(rel):
                continue
            if rel not in pkgs:
                found = PROTO_PACKAGE.search(self.text(rel) or '')
                pkgs[rel] = found.group(1) if found else ''
            svc, rpc = m['name'].rsplit('.', 1)
            groups[(pkgs[rel], svc, rpc)].append((rel.count('/'), len(rel), rel, m.get('line') or 1))
        for (pkg, svc, rpc), items in sorted(groups.items()):
            _, _, rel, line = min(items)
            name = f'RPC {pkg + "." if pkg else ""}{svc}/{rpc}'
            eid = self.g.node(f'e:{rel}:{name}', kind='endpoint', name=name, file=rel, line=line, lang='proto',
                              route=name, hash=digest(name))
            mid = self.module(rel)
            if mid:
                self.g.edge(mid, eid, 'contains')
            self.services.setdefault(svc, {}).setdefault(rpc_key(rpc), eid)

    def scan_grpc(self, src):
        if not self.services:
            return
        code, rel, lang = src.code, src.rel, src.lang
        servers = []
        if lang == 'go':
            servers += [(m.group(1), m.group(2), 'dir') for m in GRPC_GO_EMBED.finditer(code)]
            for m in GRPC_GO_REG.finditer(code):
                impl = m.group(2).strip()
                t = re.match(r'&?\s*(\w+)\s*\{|new\((\w+)\)', impl)
                if not t and re.fullmatch(r'\w+', impl):
                    t = re.search(rf'\b{impl}\s*:?=\s*(?:&\s*(\w+)\s*\{{|new\((\w+)\)|(\w+)\s*\{{)', code)
                if t:
                    servers.append((next(x for x in t.groups() if x), m.group(1), 'dir'))
        elif lang == 'py':
            impls = {m.group(1): m.group(2) for m in GRPC_PY_SERVER.finditer(code)}
            for m in GRPC_PY_SUB.finditer(code):
                base = m.group(2).rsplit('.', 1)[-1]
                if base in impls and m.group(1) not in impls:
                    impls[m.group(1)] = impls[base]
            servers += [(c, s, 'file') for c, s in sorted(impls.items())]
        elif lang in ('java', 'kt'):
            servers += [(m.group(1), m.group(2), 'file') for m in GRPC_JAVA_SERVER.finditer(code)]
        elif lang == 'cs':
            servers += [(m.group(1), m.group(2), 'file') for m in GRPC_CS_SERVER.finditer(code)]
        elif lang == 'rs' and 'tonic' in code:
            servers += [(m.group(2), m.group(1), 'file') for m in GRPC_RS_SERVER.finditer(code)]
        elif lang == 'js' and not self.is_test(rel):
            for m in GRPC_JS_SERVER.finditer(code):
                svc = m.group(1).rsplit('.', 1)[-1]
                p = src.skip(m.end())
                if svc not in self.services or not code.startswith('{', p):
                    continue
                args, _ = src.args(p)
                for a, b in args:
                    kv = re.match(r'''\s*['"]?(\w+)['"]?\s*(?::\s*(.+))?$''', code[a:b], re.S)
                    if not kv:
                        continue
                    eid = self.services[svc].get(rpc_key(kv.group(1)))
                    fn = self.resolve((kv.group(2) or kv.group(1)).strip(), rel)
                    if eid and fn:
                        self.g.edge(eid, fn, 'handles')
        if not self.is_test(rel):
            for cls, svc, scope in servers:
                for key, eid in sorted(self.services.get(svc, {}).items()):
                    for n in self.class_methods(cls, scope, rel):
                        if rpc_key(self.g.nodes[n]['name'].rsplit('.', 1)[-1]) == key:
                            self.g.edge(eid, n, 'handles')
        binds, chains = defaultdict(set), []
        if lang == 'go':
            chains = [(m, m.group(1)) for m in GRPC_GO_CHAIN.finditer(code)]
            binds_rx = [(GRPC_GO_BIND, 1, 2)]
        elif lang == 'py':
            chains = [(m, m.group(1)) for m in GRPC_PY_CHAIN.finditer(code)]
            binds_rx = [(GRPC_PY_BIND, 1, 2)]
        elif lang in ('java', 'kt'):
            binds_rx = [(GRPC_JAVA_BIND, 1, 2), (GRPC_JAVA_DECL, 2, 1)]
        elif lang == 'cs':
            binds_rx = [(GRPC_CS_BIND, 1, 2), (GRPC_CS_DECL, 2, 1)]
        elif lang == 'js':
            binds_rx = [(GRPC_JS_BIND, 1, 2)]
        elif lang == 'rs':
            binds_rx = [(GRPC_RS_BIND, 1, 2)]
        else:
            binds_rx = []
        for rx, var, svc in binds_rx:
            for m in rx.finditer(code):
                if m.group(svc) in self.services:
                    binds[m.group(var)].add(m.group(svc))
        for m, svc in chains:
            if svc not in self.services:
                continue
            end = src.close(paren(m))
            call = GRPC_CALL.match(code, end + 1) if end > 0 else None
            if call:
                self.rpc_call(src, m.start(), {svc}, call.group(1))
        for var, svcs in sorted(binds.items()):
            for m in re.finditer(rf'\b{re.escape(var)}\s*\.\s*(\w+)\s*\(', code):
                self.rpc_call(src, m.start(), svcs, m.group(1))

    def class_methods(self, cls, scope, rel):
        if scope == 'dir':
            folder = rel.rsplit('/', 1)[0] if '/' in rel else ''
            return sorted(n for n in self.owners.get(cls, [])
                          if (self.g.nodes[n]['file'].rsplit('/', 1)[0] if '/' in self.g.nodes[n]['file'] else '') == folder)
        return sorted(n for _, _, n in self.by_file.get(rel, []) if self.g.nodes[n]['name'].rsplit('.', 1)[0] == cls
                      and self.g.nodes[n]['kind'] == 'method')

    def rpc_call(self, src, pos, svcs, method):
        key = rpc_key(method)
        alt = key[:-5] if key.endswith('async') and len(key) > 5 else None
        found = sorted({self.services[s].get(key) or (self.services[s].get(alt) if alt else None) for s in svcs} - {None})
        if len(found) == 1:
            self.rpc_pending.append((src.rel, src.line(pos), found[0]))

    def load_env_files(self):
        for d in sorted({rel.rsplit('/', 1)[0] if '/' in rel else '' for rel in self.files}):
            for name in ENV_FILES:
                rel = f'{d}/{name}' if d else name
                path = self.root / rel
                try:
                    if not path.is_file() or path.stat().st_size > 256 * 1024:
                        continue
                    text = path.read_text(encoding='utf-8', errors='replace')
                except OSError:
                    continue
                found = [(i + 1, m.group(1)) for i, line in enumerate(text.split('\n'))
                         for m in [re.match(r'^\s*(?:export\s+)?([A-Za-z_]\w*)\s*=', line)] if m]
                if not found:
                    continue
                mid = self.g.node(f'm:{rel}', kind='module', name=name, file=rel, line=1, lang='env',
                                  end=text.count('\n') + 1, hash=digest(rel + ' '.join(n for _, n in found)))
                self.env_defs += [(rel, line, n, mid) for line, n in found]

    def scan_yaml(self, rel):
        mid = self.module(rel)
        text = self.text(rel) if mid else None
        if not text or not re.search(r'^\s*(?:-\s+)?(?:env|environment):', text, re.M):
            return
        lines = text.split('\n')
        for i, line in enumerate(lines):
            m = re.match(r'^(\s*)(-\s+)?(env|environment):\s*(?:#.*)?$', line)
            if not m:
                continue
            ind, child = len(m.group(1)) + len(m.group(2) or ''), None
            for j in range(i + 1, len(lines)):
                raw = lines[j]
                body = raw.strip()
                if not body or body.startswith('#'):
                    continue
                cur = len(raw) - len(raw.lstrip())
                if cur < ind or (cur == ind and not body.startswith('-')):
                    break
                child = cur if child is None else child
                if cur != child:
                    continue
                k = re.match(r'''^-\s*name:\s*["']?([A-Za-z_][\w.-]*)''', body) or \
                    re.match(r'''^-\s*["']?([A-Za-z_]\w*)(?:=|["']?\s*$)''', body) or \
                    re.match(r'''^["']?([A-Z_][A-Z0-9_]*)["']?\s*:''', body)
                if k:
                    self.env_defs.append((rel, j + 1, k.group(1), mid))

    def scan_dockerfile(self, rel):
        mid = self.module(rel)
        text = self.text(rel) if mid else None
        for i, line in enumerate((text or '').split('\n')):
            m = re.match(r'^\s*(ENV|ARG)\s+(.+)$', line, re.I)
            if m:
                for n in re.findall(r'([A-Za-z_]\w*)=', m.group(2)) or re.findall(r'^([A-Za-z_]\w*)', m.group(2)):
                    self.env_defs.append((rel, i + 1, n, mid))

    def declare(self, nid, kind, name, rel, line):
        self.g.node(nid, kind=kind, name=name, file=rel, line=line, hash=digest(name))
        mid = self.module(rel)
        if mid:
            self.g.edge(mid, nid, 'contains')
        return nid

    def finish_env(self):
        nodes = {}
        for rel, line, name, mid in sorted(set(self.env_defs)):
            if self.is_test(rel):
                continue
            if name not in nodes:
                nodes[name] = self.declare(f'v:{name}', 'variable', name, rel, line)
            self.g.edge(mid, nodes[name], 'env')
        for rel, line, name in sorted(set(self.env_uses), key=lambda x: (self.is_test(x[0]), x)):
            if name not in nodes:
                if self.is_test(rel):
                    continue
                nodes[name] = self.declare(f'v:{name}', 'variable', name, rel, line)
            sym = self.owner(rel, line)
            if sym:
                self.g.edge(sym, nodes[name], 'env')

    def finish_topics(self):
        for name, rel, line in sorted(self.task_calls):
            if name in self.tasks:
                self.topic_uses.append((self.tasks[name], rel, line, 'pub', '', 'mq'))
        uses = sorted(set(self.topic_uses), key=lambda x: (self.is_test(x[1]), x))
        roles = defaultdict(lambda: defaultdict(set))
        for name, rel, line, role, sym, kind in uses:
            roles[(name, kind)][role].add(rel)
        nodes = {}
        for name, rel, line, role, sym, kind in uses:
            found = roles[(name, kind)]
            if kind == 'emitter' and (not found['pub'] or not found['sub'] or len(found['pub'] | found['sub']) < 2):
                continue
            if name not in nodes:
                if self.is_test(rel):
                    continue
                nodes[name] = self.declare(f't:{name}', 'topic', name, rel, line)
            sym = sym or self.owner(rel, line)
            if sym:
                self.g.edge(*((sym, nodes[name]) if role == 'pub' else (nodes[name], sym)), 'event')

    def finish_endpoints(self):
        self.finish_django()
        nest = sorted(set(self.nest_prefix))
        for rel, line, verbs, path, fn in self.nest:
            self.pending.append((rel, line, '', verbs, (nest[0] + '/' if len(nest) == 1 else '') + path, fn, '', ''))
        for rel, line, recv, verbs, tpl, handler, scope, sym in sorted(set(self.pending)):
            for pre in self.prefixes(rel, recv, sym):
                path = norm_path('/'.join(x for x in (pre, scope, tpl) if x))
                for verb in verbs:
                    self.endpoint(rel, line, verb, path, handler)

    def prefixes(self, rel, recv, sym, depth=0):
        if depth > 5:
            return ['']
        entry = self.local[rel].get(recv) if recv else None
        if entry and entry[0] and entry[0] != recv:
            return [p + '/' + entry[1] for p in self.prefixes(rel, entry[0], sym, depth + 1)]
        own = entry[1] if entry else ''
        mounts = (self.mounts.get(('sym', sym)) if sym else None) or self.mounts.get((rel, recv)) or self.mounts.get((rel, None)) or []
        base = sorted({p + '/' + lit for r2, v2, lit, s2 in sorted(set(mounts))
                       for p in self.prefixes(r2, v2, s2, depth + 1)})[:3] or ['']
        return [b + '/' + own if own else b for b in base]

    def endpoint(self, rel, line, verb, path, handler):
        name = f'{verb} {path}'
        nid = f'e:{rel}:{name}'
        if nid not in self.g.nodes:
            mid = self.module(rel)
            self.g.node(nid, kind='endpoint', name=name, file=rel, line=line, lang=self.g.nodes[mid].get('lang') if mid else None,
                        route=name, hash=digest(name))
            if mid:
                self.g.edge(mid, nid, 'contains')
            segs = segments(path)
            self.ep_index[segs[-1] if segs else ''].append((verb, segs, nid))
        if handler and handler in self.g.nodes:
            self.g.edge(nid, handler, 'handles')

    def finish_clients(self):
        for rel, line, method, path, sym in sorted(set(self.clients)):
            target = self.match(method, segments(path))
            if target:
                self.g.edge(sym, target, 'http')

    def match(self, method, csegs):
        last = csegs[-1] if csegs else ''
        pool = self.ep_index.get(last, []) + (self.ep_index.get(':', []) if last not in (':', '') else [])
        best, top = [], None
        for verb, esegs, nid in pool:
            if verb != method and 'ANY' not in (verb, method):
                continue
            n = min(len(esegs), len(csegs))
            lits, ok = 0, True
            for a, b in zip(esegs[len(esegs) - n:], csegs[len(csegs) - n:]):
                if a == ':':
                    continue
                if b == ':' or a != b:
                    ok = False
                    break
                lits += 1
            if not ok or (lits == 0 and (esegs or csegs)):
                continue
            if len(esegs) == len(csegs):
                tier = 3
            elif len(csegs) > len(esegs):
                tier = 2
            elif ':' in esegs[:len(esegs) - n] or lits < 2:
                continue
            else:
                tier = 1
            score = (tier, lits, verb == method)
            if top is None or score > top:
                top, best = score, [nid]
            elif score == top:
                best.append(nid)
        best = sorted(set(best))
        return best[0] if len(best) == 1 else None

    def finish_rpc(self):
        for rel, line, eid in sorted(set(self.rpc_pending)):
            sym = self.owner(rel, line)
            if sym:
                self.g.edge(sym, eid, 'rpc')


def link_bridges(root, files, g, issues, read_source):
    from .analyze import is_test
    Bridges(root, files, g, read_source, is_test).run()
