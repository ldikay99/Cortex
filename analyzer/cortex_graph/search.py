import bisect
import math
import re
import unicodedata
from collections import defaultdict

CHUNK_RE = re.compile(r'[\W_]+')
WORD_RE = re.compile(r'[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+')
NORM_RE = re.compile(r'[\W_]+')
METHOD_RE = re.compile(r'^(get|post|put|patch|delete|head|options|any|ws|rpc)\s+/', re.I)
FIELDS = (('name', 3.0, 0.6), ('tags', 2.5, 0.3), ('sig', 1.5, 0.5), ('doc', 1.0, 0.75), ('path', 0.8, 0.4))
K1 = 1.2
PREFIX_WEIGHT = 0.5
MAX_PREFIX = 40
TEST_FACTOR = 0.5
STOPWORDS = frozenset('''
a an and are as at be by can do does for from has have how i in into is it its me my of on or our so than that the their
them then there these this those to us was we what when where which who why will with without you your about after all
any been before being both but could each if just more most much not only other over should some such use
used uses using very via want works
el la los las un una unos unas de del al y o u en con por para que como cómo donde dónde cuando cuál cual qué quien es son
se su sus lo le les mi me nos este esta esto estos estas ese esa eso hay muy más sin sobre entre hace hacer funciona
'''.split())
SUFFIXES = ('ation', 'ing', 'ion', 'ment', 'ed', 'er', 'or', 'ly')
SPANISH_WORDS = dict(line.split(':') for line in '''
carrito:cart producto:product pedido:order orden:order usuario:user cliente:client,customer pago:payment,pay envio:shipping,ship
moneda:currency correo:email,mail sesion:session contrasena:password clave:key,password ruta:route,path tabla:table datos:data
configuracion:config,settings ajuste:settings prueba:test archivo:file precio:price cantidad:quantity inventario:inventory,stock
permiso:permission rol:role cuenta:account factura:invoice mensaje:message cola:queue evento:event servicio:service
servidor:server solicitud:request peticion:request respuesta:response registro:log,register plantilla:template vista:view
pagina:page componente:component boton:button formulario:form imagen:image enlace:link busqueda:search
recomendacion:recommendation anuncio:ad catalogo:catalog articulo:item,article elemento:element,item lista:list grafo:graph
nodo:node arista:edge tarea:task,job trabajo:job,worker notificacion:notification idioma:language,locale traduccion:translation
fecha:date hora:time tiempo:time dinero:money descuento:discount cupon:coupon direccion:address telefono:phone nombre:name
perfil:profile inicio:home,start cabecera:header pie:footer tema:theme,topic estilo:style almacenamiento:storage memoria:memory
red:network conexion:connection consulta:query migracion:migration esquema:schema modelo:model controlador:controller
enrutador:router autenticacion:auth,authentication autorizacion:authorization,permission firma:signature,sign cifrado:encrypt
seguridad:security limite:limit reintento:retry salud:health metrica:metric traza:trace depuracion:debug despliegue:deploy
contenedor:container entorno:env,environment secreto:secret cache:cache error:error excepcion:exception fallo:error,failure
dependencia:dependency paquete:package modulo:module clase:class funcion:function metodo:method interfaz:interface tipo:type
evento:event manejador:handler escucha:listener suscripcion:subscription tema:topic canal:channel socket:socket archivo:file
carpeta:folder,directory directorio:directory ventana:window pantalla:screen menu:menu editor:editor texto:text dibujo:drawing
lienzo:canvas forma:shape linea:line punto:point flecha:arrow zoom:zoom capa:layer grupo:group seleccion:selection
historial:history version:version cambio:change estado:state almacen:store tienda:shop,store compra:purchase,checkout
venta:sale suscriptor:subscriber plan:plan factura:invoice reporte:report informe:report grafica:chart tablero:dashboard
'''.split())
SPANISH_ROOTS = dict(line.split(':') for line in '''
agreg:add anad:add elimin:delete,remove borr:delete,remove actualiz:update guard:save,store busc:search,find obten:get,fetch
envi:send valid:validate verific:verify,check list:list carg:load inici:start,init,login cerr:close,logout pag:pay compr:buy,checkout
registr:register,log autentic:authenticate,auth autoriz:authorize calcul:calculate,compute convert:convert renderiz:render
dibuj:draw mostr:show,display,render manej:handle proces:process ejecut:run,execute llam:call conect:connect export:export
import:import filtr:filter orden:sort,order agrup:group analiz:parse,analyze notific:notify program:schedule reintent:retry
sincroniz:sync descarg:download sub:upload compart:share copi:copy peg:paste mov:move redimension:resize escal:scale rot:rotate
selec:select edit:edit abr:open escrib:write le:read consult:query migr:migrate despleg:deploy configur:configure prob:test
traduc:translate cifr:encrypt descifr:decrypt firm:sign recomend:recommend convi:convert
'''.split())
SPANISH_ENDINGS = ('iendo', 'ando', 'ados', 'adas', 'idos', 'idas', 'ado', 'ada', 'ido', 'ida', 'aron', 'ieron', 'amos', 'emos',
                   'imos', 'ar', 'er', 'ir', 'an', 'en', 'as', 'es', 'a', 'e', 'o', 'i')
EXTENSION_RE = re.compile(r'\.[A-Za-z0-9]{1,6}$')


def stem(token):
    if len(token) < 4 or not token.isalpha():
        return token
    if token.endswith('ies') and len(token) > 4:
        token = token[:-3] + 'y'
    elif token.endswith('s') and not token.endswith(('ss', 'us', 'is')):
        token = token[:-1]
    for suffix in SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            token = token[:-len(suffix)] + ('at' if suffix == 'ation' else '')
            break
    if token.endswith('e') and len(token) > 3:
        token = token[:-1]
    return token


def words(text):
    out = []
    for chunk in CHUNK_RE.split(text or ''):
        if not chunk:
            continue
        parts = WORD_RE.findall(chunk) if chunk.isascii() else [chunk]
        for part in parts:
            part = part.lower()
            if len(part) > 1 or part.isdigit():
                out.append(part)
    return out


def tokens(text):
    return [stem(w) for w in words(text)]


def plain(word):
    return ''.join(c for c in unicodedata.normalize('NFKD', word) if not unicodedata.combining(c))


def translations(word):
    w = plain(word)
    for form in (w, w[:-2] if w.endswith('es') else w, w[:-1] if w.endswith('s') else w):
        if form in SPANISH_WORDS:
            return SPANISH_WORDS[form].split(',')
    for ending in SPANISH_ENDINGS:
        if w.endswith(ending) and len(w) - len(ending) >= 2 and w[:-len(ending)] in SPANISH_ROOTS:
            return SPANISH_ROOTS[w[:-len(ending)]].split(',')
    return SPANISH_ROOTS[w].split(',') if w in SPANISH_ROOTS and len(w) > 3 else []


def query_terms(text):
    raw = words(text)
    kept = [w for w in raw if w not in STOPWORDS] or raw
    seen, out = set(), []
    for w in kept:
        for t in [stem(w)] + [stem(x) for x in translations(w)]:
            if t not in seen:
                seen.add(t)
                out.append(t)
    return out


def norm(text):
    return NORM_RE.sub('', (text or '').lower())


def name_forms(n):
    name = n['name']
    forms = {norm(name), norm(EXTENSION_RE.sub('', name))}
    for sep in ('.', '::', '#', '/'):
        if sep in name:
            forms.add(norm(name.rsplit(sep, 1)[-1]))
    forms.discard('')
    return forms


def node_fields(n):
    path = n['file']
    tags = ' '.join(x for x in (n.get('route'), n.get('table')) if x)
    return {'name': n['name'], 'tags': tags, 'sig': n.get('sig') or '', 'doc': n.get('doc') or '', 'path': path}


class Index:
    def __init__(self, nodes):
        self.nodes = nodes
        self.postings = defaultdict(list)
        lengths = {f: [] for f, _, _ in FIELDS}
        per_doc = []
        for n in nodes:
            fields = node_fields(n)
            counted = {}
            for field, _, _ in FIELDS:
                toks = tokens(fields[field])
                lengths[field].append(len(toks))
                tf = defaultdict(int)
                for t in toks:
                    tf[t] += 1
                counted[field] = tf
            per_doc.append(counted)
        average = {f: (sum(v) / len(v) if v else 0) or 1.0 for f, v in lengths.items()}
        for i, counted in enumerate(per_doc):
            combined = defaultdict(float)
            for field, weight, b in FIELDS:
                size = lengths[field][i]
                if not size:
                    continue
                scale = weight / (1 - b + b * size / average[field])
                for t, count in counted[field].items():
                    combined[t] += count * scale
            for t, value in combined.items():
                self.postings[t].append((i, value))
        total = len(nodes)
        self.idf = {t: math.log(1 + (total - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.postings.items()}
        self.vocabulary = sorted(self.postings)

    def expand(self, term):
        if len(term) < 3:
            return []
        start = bisect.bisect_left(self.vocabulary, term)
        found = []
        for t in self.vocabulary[start:]:
            if not t.startswith(term):
                break
            if t != term:
                found.append(t)
        found.sort(key=lambda t: (-len(self.postings[t]), t))
        return found[:MAX_PREFIX]

    def bm25(self, terms):
        scores = defaultdict(float)
        matched = defaultdict(set)
        for q, term in enumerate(terms):
            variants = [(term, 1.0)] if term in self.postings else []
            variants += [(t, PREFIX_WEIGHT) for t in self.expand(term)]
            best = {}
            for t, factor in variants:
                idf = self.idf[t] * factor
                for i, tf in self.postings[t]:
                    value = idf * tf * (K1 + 1) / (tf + K1)
                    if value > best.get(i, 0):
                        best[i] = value
            for i, value in best.items():
                scores[i] += value
                matched[i].add(q)
        return scores, matched

    def tier(self, n, phrase, raw):
        if not phrase:
            return 0
        forms = name_forms(n)
        route = n.get('route') or ''
        if raw.strip().lower() in (n['key'].lower(), n['file'].lower()):
            return 3
        if route and (raw.startswith('/') or METHOD_RE.match(raw.strip())):
            if phrase in (norm(route), norm(route.split(' ', 1)[-1])):
                return 3
        if phrase == norm(n['name']):
            return 3
        if phrase in forms:
            return 2
        if n.get('table') and phrase == norm(n['table']):
            return 2
        if len(phrase) >= 3 and any(f.startswith(phrase) for f in forms):
            return 1
        return 0

    def search(self, text, kind=None, wants_tests=None):
        terms = query_terms(text)
        phrase = norm(text)
        if wants_tests is None:
            wants_tests = 'test' in terms or 'spec' in terms
        scores, matched = self.bm25(terms) if terms else ({}, {})
        ranked = []
        if scores:
            top = max(scores.values())
            for i, raw_score in scores.items():
                n = self.nodes[i]
                if kind and n['kind'] != kind:
                    continue
                coverage = len(matched[i]) / len(terms)
                score = raw_score * (0.2 + 0.8 * coverage * coverage) * (1 + 0.05 * math.log1p(n['deg']))
                if n.get('test') and not wants_tests:
                    score *= TEST_FACTOR
                level = self.tier(n, phrase, text)
                ranked.append((score + level * (top + 1), n['deg'], -n['id'], n, coverage))
        if not ranked:
            ranked = self.substring(text, kind)
        ranked.sort(key=lambda r: r[:3], reverse=True)
        return ranked, len(ranked)

    def substring(self, text, kind):
        phrase = ' '.join(text.lower().split())
        parts = phrase.split()
        found = []
        for n in self.nodes:
            if kind and n['kind'] != kind:
                continue
            name = n['name'].lower()
            haystack = ' '.join((name, n['file'].lower(), n['key'].lower(), (n.get('route') or '').lower(), (n.get('table') or '').lower()))
            if not all(p in haystack for p in parts):
                continue
            if name == phrase:
                score = 4.0
            elif name.startswith(phrase):
                score = 3.0
            elif phrase in name:
                score = 2.0
            else:
                score = 1.0
            found.append((score, n['deg'], -n['id'], n, 1.0))
        return found
