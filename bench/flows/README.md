# Benchmark de flujos entre componentes (verdad-terreno)

Este directorio contiene el conjunto de etiquetas que mide cuanto de bien detecta Cortex los flujos
reales entre componentes de un proyecto (llamada de cliente -> handler, ruta -> handler, evento ->
consumidor, codigo -> tabla/modelo, lectura de variable de entorno -> definicion, cableado de servicios).

Las etiquetas se hicieron SIN ejecutar Cortex ni mirar su salida, para mantenerlas independientes.

## Contenido

- `repos.toml`: un bloque `[[repo]]` por proyecto: `name`, `stack`, `url`, `commit` (SHA completo),
  `ref`, `scope` (rutas etiquetadas de forma exhaustiva), `kinds` (tipos exhaustivos dentro del scope)
  y `notes`.
- `labels/<name>.jsonl`: un flujo por linea (JSON).
- `run.py`: arnés que mide recall y precisión de Córtex (ver «Arnés de evaluación»); `review.jsonl`: veredictos de la
  revisión manual de precisión; `results/`: `RESULTS.md`, `results.json` y las líneas base `baseline.json`, `baseline_r2.json`,
  `baseline_r3.json`, `baseline_r4.json` y `baseline_r5.json`.
- `FRAMEWORKS.md`: matriz de cobertura por framework/librería (antes y después de la ronda 3, con los cambios de estado de la ronda 4),
  con un test sintético por fila en `analyzer/tests/test_bridges_frameworks.py`; los mecanismos estructurales de la ronda 4 tienen
  sus casos en `analyzer/tests/test_bridges_structural.py` y los idiomas transversales de la ronda 5 (forma canónica + variantes) en
  `analyzer/tests/test_bridges_idioms.py`.
- Los repos se clonan en `~/.cache/cortex-bench/flows/<name>` (fuera de este repositorio), con
  `git -c core.hooksPath=/dev/null clone --filter=blob:none <url>` y se fijan al `commit` indicado.
  Nunca se ejecutan scripts, builds, instalaciones ni tests de esos repos; solo se leen.

## Formato de una etiqueta

```json
{"kind": "http", "from": {"file": "rel/path", "line": 12, "symbol": "enclosingFn|null"},
 "to": {"file": "rel/path", "line": 40, "symbol": "handler|null"}, "detail": "GET /api/users/{id}", "note": "opcional"}
```

- `file`: ruta relativa a la raiz del repo clonado. `line`: base 1 (`null` si no aplica).
- `from.line`: linea de la llamada / registro / lectura. `to.line`: linea de definicion del handler,
  modelo, tabla o variable. Si el handler es una funcion anonima inline, `to` apunta a esa funcion
  (normalmente la misma linea del registro de la ruta) y `symbol` es `null`.
- `symbol`: funcion/metodo/clase envolvente. En `from` suele ser `null` cuando no se calculo
  (no es obligatorio puntuarlo); en `to` va el nombre del handler cuando existe.
- Tipos (`kind`):
  - `http`: llamada de cliente (fetch/axios/ky/HttpClient/WebClient/RestClient/Ktor client/cliente OpenAPI
    generado) a una ruta servida por el mismo repo -> handler de la ruta.
  - `route`: declaracion de ruta -> handler (Rails routes.rb, Laravel routes/api.base.php, Express router,
    Phoenix router, axum `.route`, Ktor `get("..")`, minimal APIs, anotaciones Spring, decoradores FastAPI,
    montajes de sub-routers).
  - `rpc`: llamada gRPC cliente -> implementacion servidor (tambien registro del servicio).
  - `event`: productor de un evento de integracion -> cada handler consumidor; y registro de suscripcion
    (`AddSubscription`) -> handler (nota `subscription registration`).
  - `data`: codigo que lee/escribe una tabla/coleccion -> modelo/esquema/migracion que la define, y
    modelo ORM -> migracion/schema.
  - `env`: lectura de variable de entorno -> donde se define (.env, docker-compose, manifiesto k8s,
    application.yaml con `$VAR:default`).
  - `service`: cableado de despliegue (depends_on, URL de servicio en env -> Service/servicio compose,
    lista de modulos Ktor -> modulo). Linea de `from` y `to` al nivel de archivo/bloque.

## Como se hicieron

1. Se leyeron los repos con grep/sed/Read para entender el scope de cada uno.
2. Se escribio, por repo, un script de etiquetado (fuera del repo) con una lista de especificaciones
   `(tipo, archivo y patron del origen, archivo y patron del destino, detalle)`. Las lineas se resuelven
   buscando el patron en el archivo real (falla si no hay coincidencia), nunca con numeros a mano.
   Para los repos grandes con tablas regulares (Koel, Express, Rails, Phoenix, axum, Fastapi) se
   parsearon las tablas de rutas y se cruzaron con las llamadas del cliente; los cruces se revisaron.
3. Validacion automatica: todos los archivos existen y todas las lineas apuntan a una linea no vacia.
4. Revision manual de aprox. 10-15 % de las etiquetas (muestreo aleatorio por repo) reabriendo la linea
   de origen y de destino; se corrigieron: lineas de peticion PUT/POST en formularios Vue (Petclinic),
   segunda coincidencia de `session.get(User, ...)` (FastAPI), prefijos de grupo `radio` y rutas que
   absorbia el parser por sentencias sin `;` (Koel), heuristica de tablas en Phoenix (sustituida por tabla
   manual) y `kind: Service` equivocado para redis-cart (microservices-demo).

## Convenciones y ambiguedades

- Prefijos de ruta: `detail` lleva la ruta completa (con prefijos `/api`, `/api/v1`, `/{year}`, etc.) cuando
  se pudo deducir; `from`/`to` apuntan a la declaracion mas especifica (la linea del verbo/ruta).
- Rutas con varios verbos en una misma linea (`.get(a).post(b)`): una etiqueta por verbo, mismo `from.line`.
- `apiResource`/`resources`: se expande a las acciones que existen realmente en el controlador
  (nota `apiResource expansion` / `resourceful route expansion`). Rutas cuyo controlador viene de un gem
  (Devise registrations) se omiten.
- Clientes generados (OpenAPI en FastAPI template y wild-workouts): se etiqueta la linea con la URL dentro del
  cliente generado (`sdk.gen.ts`, `DefaultApi.js`) y, ademas, cada llamada de la app al cliente generado
  (nota `via generated SDK client`). Un analizador solo capaz de lo primero seguira cubriendo el nucleo.
- URLs base construidas por env/proxy (`VITE_API_URL`, `proxy` de CRA, prefijo `StripPrefix=2` del gateway,
  `baseUrl` + `/{year}`): se resuelve al handler final; la nota lo indica.
- Host por nombre de servicio (`http://customers-service/...`, `lb://`): se resuelve al servicio del repo con ese
  `spring.application.name`.
- Eventos: en eShop el productor se marca en la linea donde el evento se crea/encola para publicar
  (`AddAndSaveEventAsync`, `new XIntegrationEvent`, `PublishAsync`); el "topic" es el nombre del tipo del
  evento. Hay una etiqueta por consumidor.
- Config indirecta (Ktor `config.property("service.secret")`, pydantic Settings): `env` va desde el campo/lectura
  a la linea que mapea o define la variable.
- No se etiquetan tests (`*_test.go`, `spec/`, `internal/common/tests`) ni codigo generado de protobuf.
- Dinamico/no resoluble estaticamente: omitido (por ejemplo `http.post(signedPath)` en Koel, `downloadAsset(path)`
  en kotlinconf-app, webhooks con URL de usuario en eShop).
- Alcance exhaustivo = lo declarado en `scope` y `kinds` de `repos.toml`. Para calcular recall solo deben
  usarse flujos de esos kinds/scopes; la precision no se puede medir con este conjunto (las etiquetas no
  son una lista cerrada de todo lo que existe en el repo fuera del scope).

## Recuentos (1099 etiquetas)

| repo | stack | etiquetas |
|---|---|---|
| koel | Laravel + Vue/TS | 301 |
| full-stack-fastapi-template | FastAPI + React/TS | 115 |
| eShop | .NET 8, RabbitMQ, gRPC, Blazor/MAUI | 107 |
| microservices-demo | Go/C#/Node/Python/Java gRPC + k8s | 93 |
| spring-petclinic-microservices | Spring Cloud + JS | 83 |
| proshop_mern | Express + Mongoose + React | 82 |
| realworld-axum-sqlx | Rust axum + sqlx | 73 |
| kotlinconf-app | Kotlin Multiplatform + Ktor | 72 |
| wild-workouts | Go + gRPC + Firestore + Vue | 71 |
| phoenix-realworld | Elixir Phoenix + Ecto | 56 |
| rails-realworld | Rails API | 46 |

Por tipo: route 383, http 288, data 222, env 82, service 51, rpc 37, event 36.

## Debilidades conocidas

- Koel concentra el 27 % de las etiquetas y solo cubre `route` y `http`.
- `symbol` de `from` es mayormente `null` en Koel, FastAPI, proshop y otros; no puntuar simbolos de origen alli.
- Las etiquetas `data` de Rust/Phoenix/Rails/proshop son aproximaciones por sentencia/funcion: en SQL con
  subconsultas puede haber tablas referenciadas que el patron no capte (falsos negativos del etiquetado).
- `env` no se etiqueto donde el repo no define las variables (proshop, Rails, Phoenix, Koel).
- No hay `event` fuera de eShop (ni colas Celery/Kafka/Redis pubsub): cobertura de eventos de un solo repo.
- Algunos `service` son de grano grueso (linea del bloque compose / Service k8s).
- Los `http` que pasan por un gateway/proxy se etiquetan contra el handler final.

## Arnés de evaluación (`run.py`)

```bash
cd analyzer
nice -n 19 .venv/bin/python ../bench/flows/run.py                 # analiza todos los repos de repos.toml y escribe results/
nice -n 19 .venv/bin/python ../bench/flows/run.py --only koel     # un repo (fusiona con results.json previo)
nice -n 19 .venv/bin/python ../bench/flows/run.py --reuse         # reutiliza los grafos ya analizados
```

- Clona (si falta) y fija cada repo en `~/.cache/cortex-bench/flows/<name>` (`--clones`), analiza con
  `analyze(root, git=False)` y guarda un grafo compacto (solo aristas de flujo) en `<clones>/../work/flow-graphs`
  (`--cache`). Nunca ejecuta nada de los repos.
- Salida: `results/RESULTS.md` (tablas en español) y `results/results.json`. `results/baseline.json` es la primera
  ejecución, sobre el Córtex de partida, y se usa para la tabla de línea base; `results/baseline_r2.json` es la ejecución
  al empezar la ronda 2 (tabla «antes → después»).
- Cada repo lleva su conjunto (`split` en `results.json`): sin `split` = «ajuste ronda 1», `control` = «ajuste ronda 2»
  (el antiguo control, usado para afinar en la ronda 2), `control2` = «ajuste ronda 3» (el examen final de la ronda 2, usado
  para afinar en la ronda 3), `control3` = «ajuste ronda 4» (el examen ciego de la ronda 3, usado para afinar en la ronda 4) y
  `control4` = «ajuste ronda 5» (el examen ciego de la ronda 4, usado para afinar en la ronda 5). El valor de `split` en `repos.toml`
  no cambia: la correspondencia con la etiqueta del informe está en `SPLITS` de `run.py`. Los conjuntos sin entrada en `SPLITS` o
  marcados en `BLIND` (`control5` = «control 5 (ciego)», el examen ciego siguiente) no se clonan, ni se analizan, ni se leen sus
  etiquetas salvo que se pidan con `--only`. `RESULTS.md` añade un resumen de recall y de precisión por conjunto, y `results/baseline_r3.json`
  / `results/baseline_r4.json` (ejecuciones al empezar cada ronda) alimentan las tablas «Ronda 3/4 (antes → después)» con tiempos.

### Cómo se puntúa una etiqueta

- Solo cuentan las etiquetas cuyos `kind` estén en `kinds` del repo y cuyo origen o destino caiga en `scope`
  (los `*` del scope casan un segmento de ruta).
- Origen: el nodo más interno de `from.file` que cubre `from.line` (función/método/clase; si no hay, el módulo). Si la
  línea es una anotación/decorador (`@`, `[`, `#[`) se toma el nodo que empieza en las 3 líneas siguientes. Para `route`,
  `rpc`, `event`, `env` y `service` se añaden los nodos endpoint/topic/variable declarados a ±2 líneas. `from.symbol`
  no se usa.
- Destino: igual con `to.file`/`to.line`, más los nodos del mismo archivo cuyo nombre corto coincide con `to.symbol`
  a ±10 líneas (sobrecargas). En `data` vale cualquier nodo que cubra la línea (modelo, tabla o migración); en `env`, el
  módulo del archivo que define la variable o el nodo `v:NOMBRE` declarado en ese archivo.
- Encontrada = existe un camino de 1 o 2 aristas (sin dirección) cuyo nodo intermedio es endpoint, topic, variable o
  tabla, usando solo las aristas del tipo: `route` → `handles`; `http` → `http`+`handles`; `rpc` → `rpc`+`handles`;
  `event` → `event`; `data` → `data`; `env` → `env`; `service` → `depends`. No cuentan `contains`, `import`, `call`,
  `ref` ni `cochange`.
- (Ronda 4) Registro sobre el propio handler: en `event`, si el origen (la línea del decorador/anotación de suscripción, que se
  resuelve al nodo que empieza justo debajo) y el destino son el mismo nodo, cuenta como encontrada si ese nodo está unido a un
  topic por una arista `event`. Antes sólo se encontraba cuando el nodo topic estaba declarado en esa misma línea, lo que con varios
  consumidores de un mismo topic (cada uno con su `@Topic`/`@job`) sólo podía cumplirse para uno.
- (Ronda 5) Línea de anotación/decorador: si la línea es una anotación, el origen/destino es el nodo decorado (el que empieza en la
  primera línea de código tras el bloque de anotaciones, aunque el bloque sea largo), con preferencia sobre la clase que la cubre; si
  lo decorado no es un nodo (un campo), se mantiene la regla anterior. Los analizadores de lenguaje pasaron a situar la declaración en
  su palabra clave (`public Response getCwes()`, `async onConfigUpdate()`) y no en la primera anotación, y la regla anterior («el nodo
  que empieza en las 3 líneas siguientes») dejaba de encontrar el método decorado cuando la clase cubría la línea.
- (Ronda 5) Ruta declarada sobre el propio handler: en `route`, si el origen (la anotación de verbo) y el destino son el mismo nodo,
  cuenta como encontrada si ese handler sirve un endpoint con el mismo verbo y una ruta que es sufijo de la etiquetada (JAX-RS con
  `@Path` sólo en la clase: Córtex sitúa el endpoint en el `@Path` de clase y la etiqueta en el `@GET` del método).
- (Ronda 5) Destino de `service` en la línea 1 de un fichero (un Dockerfile, un script de entrada): también vale el módulo, aunque la
  línea 1 abra un bloque (la primera etapa `FROM .. AS x`).

### Precisión

Las unidades son las aristas de flujo de Córtex cuyo origen está en el `scope`/`kinds` del repo (sin tests; para `env`,
solo lecturas desde código, no las definiciones: desde la ronda 2 una arista `env` cuenta solo si su origen está en un
fichero de código, porque los servicios compose y los recursos k8s también enlazan las variables que definen). Las que forman parte del camino de una etiqueta encontrada cuentan
como acierto. De las demás se toma una muestra determinista (10 por repo, ordenadas por hash) y se revisan leyendo el
código; los veredictos viven en `review.jsonl` (`{"repo","kind","a","b","edge","verdict":"ok|fp","note"}`, `ok` =
flujo real que el etiquetado no recoge). La precisión estimada aplica la tasa de `fp` de la muestra al resto; también
se da una cota conservadora con la regla del tres. Si el muestreo cambia, las aristas nuevas salen como `pendiente`
en `RESULTS.md` hasta revisarlas.

## Correcciones del etiquetado

Ninguna etiqueta resultó incorrecta al revisar los falsos negativos restantes. En la revisión de precisión aparecieron
flujos reales que el etiquetado no recoge (no se han añadido para no sesgar el conjunto): `playwright depends_on
mailpit` (full-stack-fastapi-template, `compose.override.yml`), la ruta `GET /` de `backend/server.js` (proshop_mern),
`POST /logout` y `OPTIONS /check` de `src/WebhookClient` y los accesos a `CatalogItems` de `GetItemPictureById`
(eShop), y `loginUser` → `GET /api/users/current` vía el SDK generado (wild-workouts).

Ronda 2 (revisando los falsos negativos del antiguo control):

- ghostfolio, `POST /api/v1/ai/activities` (2 etiquetas: `route` desde `ai.controller.ts:78` y `http` desde
  `data.service.ts:893`): el parser de decoradores del etiquetado tomó como handler `FileInterceptor` (línea 90, un
  argumento de `@UseInterceptors`); el handler real es `AiController.getActivitiesFromFile` (línea 95). Se corrigió
  `to.line`/`to.symbol`.
- Flujos reales vistos en la revisión de precisión y no etiquetados (no se añaden): montajes `app.MapDefaultEndpoints()` y
  demás métodos de extensión `Map*` de ASP.NET (eShop, aspire-samples), seeds `data.sql` y migraciones posteriores que
  escriben en tablas creadas antes (spring-petclinic, kotlinconf-app, ghostfolio), cableado k8s por URLs `*.svc` y
  `configMapKeyRef` hacia Services de infraestructura (sb3-course), y lecturas `cleanEnv(process.env, {...})` de variables
  que el repo no define (ghostfolio).

## Falsos negativos residuales conocidos

- Inferencia de tipos: `session.delete(current_user)` (FastAPI), `current_user.favorite(@article)` y
  `current_user.update_attributes(...)` (Rails, a través de métodos del modelo).
- Colecciones de Firestore → struct de Go (wild-workouts): no hay convención que una `Collection("x")` con su modelo.
- Rutas con versión duplicada (`/api/catalog/items` v1 y v2 en eShop) se funden en un único endpoint.
- `GET /` llamado desde locust es ambiguo entre varios servicios con raíz `GET /` (microservices-demo).
- Ternario en la URL (`petId ? ... : ''`): solo se sigue la primera rama (spring-petclinic, el `POST`).

## Conjunto de control

Seis repos adicionales marcados con `split = "control"` en `repos.toml`. Se etiquetaron **después** de los últimos
arreglos del analizador, también sin ejecutar Córtex ni mirar su salida, y ningún arreglo se ajustó contra ellos: sirven
para medir si las mejoras generalizan a proyectos y frameworks nunca usados para afinar (los 11 repos de arriba son el
conjunto de ajuste). Misma metodología, formato y reglas de `scope`/`kinds` que el resto (script con patrones resueltos
contra el archivo real, validación automática y revisión manual de ~10 % de las etiquetas por repo, sin correcciones
pendientes tras la revisión).

| repo | stack | etiquetas | tipos |
|---|---|---|---|
| ghostfolio | NestJS + Angular (Nx), colas Bull/Redis, EventEmitter2, Prisma | 452 | route 120, http 108, data 165, event 36, env 19, service 4 |
| aspire-samples | .NET Aspire (4 muestras): minimal APIs, gRPC, EF, Angular/React/Vue/Vite, Node + workers Python/C# por RabbitMQ | 117 | route 18, http 16, rpc 10, event 11, data 21, env 14, service 27 |
| full-stack-flutter-app | Flutter (dio) + dart_frog con rutas por ficheros + stormberry | 95 | route 26, http 17, data 52 |
| sb3-course | Spring Boot 3: Gateway MVC, RestClient/@HttpExchange, Kafka+Avro, Flyway, Angular, k8s | 90 | route 8, http 5, event 2, data 10, env 41, service 24 |
| go-coffeeshop | Go: gRPC + grpc-gateway, RabbitMQ, sqlc/Postgres, echo | 86 | route 7, http 4, rpc 9, event 12, data 21, env 14, service 19 |
| django-react-blog | Django + DRF (vistas genéricas) + React/Redux + nginx | 75 | route 22, http 8, data 29, env 4, service 12 |

Total del control: 915 etiquetas (route 201, http 158, data 298, env 92, service 86, event 61, rpc 19).

Notas específicas del control:

- ghostfolio concentra el 49 % de las etiquetas (rutas y llamadas se extrajeron con un parser de decoradores NestJS y de
  `this.http.*`, cruzadas por verbo y ruta con versionado URI; los casos con URL en variable local se resolvieron a mano).
  Para métricas por repo no hay problema; en el agregado conviene reportar también la media por repo.
- Eventos nuevos respecto al conjunto de ajuste: colas Bull (nombre del job = topic), `EventEmitter2`, RabbitMQ con
  `amqp091`/`amqplib`/`pika`/cliente .NET, Kafka (`KafkaTemplate` -> `@KafkaListener`). Las colas con consumidores
  competidores (tasks en `aspire-samples`) llevan una etiqueta por consumidor.
- Patrones de otros ecosistemas: rutas por ficheros (dart_frog), anotaciones `google.api.http` en `.proto`, `MapGroup` +
  métodos de extensión (`MapCatalogApi`), vistas genéricas DRF, gateways Spring `RequestPredicates.path`, variables
  inyectadas por orquestadores (`WithReference` de Aspire, relaxed binding de Spring -> ConfigMap de k8s).
- `rpc` está poco representado (19) y `service`/`env` casi no existen en ghostfolio y full-stack-flutter-app (ver `notes`
  de cada repo en `repos.toml` para el alcance exacto de `env`).
- Omisiones deliberadas: `POST /v1/users/{id}/follow` del cliente Flutter (el servidor solo implementa `PUT`),
  `api/v1/auth/` y `/signup` en django-react-blog (handler de librería / ruta inexistente), `API_HTTP`/`API_HTTPS` de los
  `vite.config.ts` de aspire-samples (origen de la variable no verificado), `McpController` de ghostfolio (no es HTTP).

## Ronda 2 de ajuste (antiguo control)

Tras la ronda 1 el antiguo control dio 11.7 % (ghostfolio), 54.7 % (django-react-blog), 34.9 % (go-coffeeshop), 25.6 %
(sb3-course), 0 % (full-stack-flutter-app) y 39.3 % (aspire-samples): la ronda 1 había sobreajustado a librerías concretas.
En la ronda 2 esos 6 repos pasaron a ser conjunto de ajuste («ajuste ronda 2») y el objetivo fue generalizar con
mecanismos independientes de la librería (todo en `analyzer/cortex_graph/bridges.py`, con tests sintéticos en
`analyzer/tests/test_bridges_generalize.py`, sin nombres ni rutas de los repos del benchmark):

- Rutas declarativas: el endpoint se sitúa en la línea de la anotación de verbo; versionado URI de NestJS
  (`enableVersioning`, `@Version`, `VERSION_NEUTRAL`); `@*Exchange` siempre es cliente; rutas funcionales Java
  (`.GET("/x", ...)`), rutas por ficheros de dart_frog (`routes/**` + `case HttpMethod.x`), métodos de extensión `Map*` de
  ASP.NET como montajes, `include()` de Django como montaje, handlers que instancian una clase (`MainFeed()`), y rutas
  proxy (`RequestPredicates.path(...)` + `http(...)`, `MapForwarder`) que se resuelven al controlador que sirve ese prefijo.
- Clientes por emparejamiento con endpoints: cualquier llamada `x.get/post/.../request/fetch/send/exchange(url)` en
  cualquier lenguaje cuya URL (constantes locales o globales `UPPER_CASE`/`Clase.CONST`, plantillas, concatenación) case con
  una ruta declarada en otro fichero; interfaces declarativas (`@GetExchange`, Feign, Retrofit) propagan la arista a sus
  llamantes; las URLs con base desconocida (`${base}/x`) casan por sufijo si el candidato es único; los empates se resuelven
  por cercanía de ruta (monorepos) y, dentro de un mismo fichero, por orden de declaración.
- Datos por nombre declarado: modelos Prisma ↔ `CREATE TABLE` de las migraciones y `<cliente>.<modelo>.findMany(...)`;
  `CREATE TABLE` multilínea/con esquema en `.sql`, consultas sqlc (`-- name:`), structs generados por sqlc y llamadas a
  esas consultas (filtradas por import); DML de seeds/migraciones `.sql`; `@Model`/`tableName` de Dart y accesos
  `db.<tabla>.query*()`; `CreateModel` de Django y `Meta.model` de serializers; `CreateTable`/`ToTable` de EF; `@Document`
  de Spring Data. Las uniones por nombre no cruzan proyectos hermanos de un monorepo.
- Eventos por clave: consumidores por decorador (`@Process`, `@OnEvent`, `@EventPattern`, `@MessagePattern`,
  `@RabbitSubscribe`, `@SqsMessageHandler`) con la clave resuelta (literal, constante global o expresión simbólica
  `Clase.metodo()`); productores = llamadas de broker en cualquier lenguaje (`sendToQueue`, `publish`, `BasicPublishAsync`,
  `emit`, `add` sobre colas, `consume`/`subscribe`...) con la cola resuelta por constante o por la variable declarada con
  `declare_queue/assertQueue`, y referencias a la constante de la clave fuera del decorador; configuración de publicadores
  (`publisher.MessageTypeName("x")`) y despacho `switch msg.Type { case "x": ... }` con el handler deducido por el tipo del
  payload. Los usos débiles solo crean topic si hay productor y consumidor.
- Env/config: tags `env:"X"` de Go, `cleanEnv(process.env, {...})`, `config.get('X')` (solo si X está definida), relaxed
  binding de Spring (`a.b-c` ↔ `A_BC`) entre `@Value`/propiedades/`logback-spring.xml` y manifiestos k8s/compose, claves
  jerárquicas de .NET (`Section:Key` ↔ `Section__Key`), `data:` de ConfigMap/Secret y `configMapKeyRef`, `env_file:` de
  compose, y variables que inyecta un AppHost de Aspire (`WithReference` → `services__x__https__0`, `ConnectionStrings__x`,
  `X_URI`...; `WithHttpEndpoint(env:)`, `WithEnvironment`) frente a sus lectores (`AddNpgsqlDbContext("x")`,
  `GetConnectionString`).
- Cableado de servicios: recursos de AppHost (C# y TS) como nodos con `WithReference`/`WaitFor` → `depends`; hosts en URLs
  de código y config (`https+http://x`, `user@host:port`, `name.ns.svc.cluster.local`), valores sueltos en claves `*_HOST`,
  `localhost:PUERTO` → servicio que publica ese puerto (compose `ports`, `server.port` de Spring), `links`/`env_file` de
  compose; se prefiere el compose principal y no se cruza compose ↔ k8s.
- gRPC: registro (`RegisterXServer(s, &svc)`, `MapGrpcService<T>`) y gateway (`RegisterXHandlerFromEndpoint`) como aristas
  `rpc` a los métodos del servicio; anotaciones `google.api.http` del `.proto` como endpoints HTTP servidos por la
  implementación.

Resultado (ver `results/RESULTS.md`): el antiguo control pasa de 21.1 % (193/915) a 99.1 % de recall (907/915) sin bajar la ronda 1
(98.8 %), con precisión estimada del 99.8 % sobre la muestra revisada.

Falsos negativos residuales de la ronda 2:

- go-coffeeshop: los 4 productores reales (`baristaEventPub.Publish(...)`) solo se conectan con su `MessageTypeName` por la
  inyección de dependencias (wire), que no se sigue.
- aspire-samples: en `queue.consume(lambda msg: on_message(...))` el topic se une al handler `on_message`, pero no a la
  función que registra el consumo (`main`), así que la etiqueta de registro `main → on_message` no se encuentra;
  `MigrateAsync` → migración inicial no se modela.
- full-stack-flutter-app: la ruta websocket (`ws.dart`) apunta a una clausura que el extractor de Dart no delimita.
- django-react-blog: `ROOT_URL = 'http://api.' + host` → bloque `server_name api.*` de nginx (no se modelan server
  blocks).

## Examen final (control2; desde la ronda 3, «ajuste ronda 3»)

Seis repos adicionales marcados con `split = "control2"` en `repos.toml`. Son el examen final: se etiquetaron **a ciegas**
(sin ejecutar Córtex, sin `run.py` y sin mirar ninguna salida del analizador), después de cerrar el ajuste, y se mantienen
**fuera del ajuste y del conjunto de control**: ningún arreglo del analizador debe afinarse contra ellos y se miden una sola
vez al final. Misma metodología, formato y reglas de `scope`/`kinds` que el resto (script con patrones resueltos contra el
archivo real, validación automática de que todas las líneas existen y no están en blanco, y revisión manual de ~10 % de las
etiquetas reabriendo origen y destino). Son proyectos y frameworks distintos de los 17 anteriores.

| repo | stack | etiquetas | tipos |
|---|---|---|---|
| papermark | Next.js (app router + pages) + Prisma + tareas Trigger.dev | 206 | route 69, event 38, data 66, env 33 |
| 8mb.local | FastAPI + Celery/Redis (+ pub/sub) + SvelteKit | 154 | route 46, http 54, event 13, env 41 |
| quarkus-super-heroes | Quarkus multi-servicio: OpenAPI -> JAX-RS, REST client, gRPC Kotlin, Kafka, Panache, UI React | 139 | route 40, http 13, rpc 11, event 6, data 29, env 13, service 27 |
| terminus | Ruby Hanami 2 + ROM + Sidekiq/scheduler + compose/render | 122 | route 40, event 11, data 40, env 21, service 10 |
| tchatchers | Rust Axum + Yew/WASM + sqlx + Redis streams | 105 | route 14, http 16, event 17, data 31, env 11, service 16 |
| NotyKT | Android Kotlin (Retrofit + Room) + backend Ktor/Exposed en el mismo repo | 87 | route 10, http 16, data 26, env 34, service 1 |

Total control2: 813 etiquetas (route 219, data 192, env 153, http 99, event 85, service 54, rpc 11). Ningún repo supera el
26 % del total (papermark 25 %).

Notas específicas de control2:

- Patrones nuevos respecto a tuning y control: rutas de Next.js por ficheros (`route.ts` con `export GET/POST`), tareas
  Trigger.dev como eventos (`task.trigger` -> `task({id})`), tareas Celery por nombre de cadena y canal Redis pub/sub,
  interfaces JAX-RS generadas desde OpenAPI (el origen es el `openapi.yml`), clientes MicroProfile REST, canales
  SmallRye/Kafka y WebSocket de Quarkus, Retrofit/Room frente a Ktor/Exposed, colas Redis streams en Rust, jobs Sidekiq y
  repositorios ROM de Hanami, y wiring `links`/`depends_on`/`fromService` de compose y render.yaml.
- Ver `notes` de cada repo en `repos.toml` para el alcance exacto. Omisiones deliberadas: tareas Trigger.dev importadas
  pero no definidas en papermark, `Object.const_get(job).perform_in` (dinámico) en terminus, `LOCAL_RUNTIME` y demás
  variables no definidas en 8mb.local, rutas HTML de terminus y fetch de componentes en papermark.

Debilidades conocidas de control2:

- `rpc` (11) y `service` (54, de los que 27 son de quarkus-super-heroes) están poco representados; `rpc` solo existe en
  quarkus-super-heroes y `service` casi no existe en NotyKT, 8mb.local ni papermark.
- `data` de papermark es solo `app/api/` (66 de ~200 usos de Prisma); `event` de quarkus-super-heroes tiene solo 6 etiquetas.
- 8mb.local y papermark concentran `env` por lecturas repetidas de unas pocas variables (muchas etiquetas apuntan a la
  misma línea de `.env.example`).
- Los clientes de 8mb.local se etiquetaron por patrón de código (verbo deducido de `method:`); las rutas de terminus
  se deducen del nombre `api.x.y` de `routes.rb` hacia el fichero de la acción.

## Examen ciego (control3; desde la ronda 4, «ajuste ronda 4»)

Siete repos adicionales marcados con `split = "control3"` en `repos.toml`. Se etiquetaron **a ciegas** (sin ejecutar Córtex,
sin `run.py` y sin mirar ninguna salida del analizador) y se mantienen **fuera del ajuste, del control y del control2**:
ningún arreglo del analizador debe afinarse contra ellos. Misma metodología, formato y reglas de `scope`/`kinds` que el resto
(script con patrones resueltos contra el archivo real, validación automática de que todas las líneas existen y no están en
blanco, y revisión manual de ~10 % de las etiquetas reabriendo origen y destino). Los frameworks no aparecen en ningún repo
anterior (Micronaut, Flask-RESTful + RQ, gin + gRPC de agentes, Phoenix + Oban, Koa + BullMQ + socket.io, Hono + tRPC + Expo,
ASP.NET con controladores + Hangfire + Angular).

| repo | stack | etiquetas | tipos |
|---|---|---|---|
| micronaut-microservices-poc | Micronaut multi-servicio (@Client, Kafka, Micronaut Data/Mongo/Elastic, WebSocket) + Vue y Angular | 123 | route 29, http 25, event 10, data 27, env 13, service 19 |
| redash | Flask-RESTful + SQLAlchemy + RQ (rq-scheduler) + React/JS en el mismo repo | 140 | route 28, http 28, event 38, data 23, env 13, service 10 |
| woodpecker | Go gin + gRPC servidor/agente + xorm + pubsub/SSE + Vue 3 | 149 | route 45, http 35, rpc 14, event 12, data 25, env 15, service 3 |
| plausible-analytics | Phoenix (router con scopes) + Ecto + Oban (cron y workers) + runtime.exs | 139 | route 51, event 29, data 28, env 31 |
| outline | Koa (@koa/router) + Sequelize + BullMQ + socket.io + React | 140 | route 29, http 5, event 51, data 31, env 22, service 2 |
| karakeep | Hono + tRPC + Drizzle + colas liteque + app Expo/React Native + MCP/SDK + compose y k8s | 146 | route 13, http 11, rpc 25, event 32, data 24, env 12, service 29 |
| Kavita | ASP.NET Core (controladores) + EF Core + Hangfire + Angular HttpClient | 148 | route 32, http 34, event 52, data 24, env 6 |

Total control3: 985 etiquetas (route 227, event 224, data 182, http 138, env 112, service 63, rpc 39). Ningún repo supera el
16 % del total (el mayor es woodpecker con 15,1 %).

Notas específicas de control3:

- Patrones nuevos: interfaces `*Operations` de Micronaut implementadas por controladores y clientes `@Client` declarativos
  (la llamada se etiqueta en el sitio de uso del gateway), topics Kafka con `@KafkaClient`/`@KafkaListener`; `add_org_resource`
  de Flask-RESTful con varias URLs por recurso y trabajos RQ (`.delay`, `@job`, `periodic_job_definitions`); grupos anidados de
  gin resueltos a rutas completas y gRPC de agente con `c.client.<Metodo>`; scopes de Phoenix con alias de módulo y workers Oban
  (crontab de `runtime.exs`); rutas Koa con el nombre `recurso.accion` en la línea siguiente, handlers inline y eventos
  socket.io emisor -> `socket.on`; tRPC (procedimientos `tagsProcedure`) llamado desde Hono, desde la app Expo con TanStack
  Query y desde el SDK openapi-fetch del servidor MCP; Hangfire (`BackgroundJob.Enqueue(() => servicio.Metodo())`,
  `RecurringJob.AddOrUpdate`, `TriggerJob`) y Angular `httpClient.get(baseUrl + '..')`.
- tRPC se etiquetó como `rpc` (llamada cliente -> procedimiento); la llamada REST al SDK del servidor MCP como `http`.
- Omisiones deliberadas: login de Micronaut Security (sin handler en el repo), llamadas dinámicas de los stores de Outline
  (`/${apiEndpoint}.create`), cliente React de Plausible (URLs por helper), `/api/v1/sites` (solo ee) y `ScoreTrialProspects`
  (ee) de Plausible, `weekly_reports` (sin migración create table), productores implícitos de eventos de Outline, ruta
  `/bookmarks/{id}/highlights` de karakeep (fuera de scope) y `ColorScapeController`/SignalR de Kavita.
- Scopes parciales a propósito para acotar el esfuerzo: Redash (solo recursos alerts, destinations, query_snippets,
  visualizations y widgets), Woodpecker (rutas globales sin orgs/repos), Plausible (sin LiveView/HTML), Outline (cinco
  recursos), karakeep (routers tags y highlights) y Kavita (cinco controladores). Fuera de esos scopes no hay exhaustividad.

Debilidades conocidas de control3:

- `service` (63) está concentrado en micronaut (19) y karakeep (29); plausible-analytics y Kavita no tienen `service` (sin
  compose en el repo / no aplica) y woodpecker y outline solo tienen 3 y 2.
- `rpc` (39) solo existe en woodpecker (gRPC real) y karakeep (tRPC): un analizador sin soporte tRPC fallará en 25 etiquetas.
- `http` de outline es mínimo (5) y plausible-analytics no tiene `http`; `event` de outline (51) y Kavita (52) son
  mayoritariamente tareas con receptor resuelto por nombre (en Kavita se elige la sobrecarga por receptor y número de
  argumentos, que puede ser ambigua) y `env` de plausible-analytics y outline son lecturas de una sola línea hacia un fichero de
  ejemplo (`.env.dev` / `.env.sample`).
- Varias etiquetas `env` de micronaut y `service` de karakeep/micronaut son wiring de grano fino (línea del bloque), y los
  `data` de redash/outline/karakeep se apoyan en patrones de línea (`models.X`, `Model.find*`, `db.query.tabla`).
- Los SHA fijados en `repos.toml` son el HEAD en el momento del etiquetado (octubre de 2026 salvo micronaut-microservices-poc,
  de 2021).

## Ronda 3 de ajuste (antiguo examen final)

El examen final de la ronda 2 (control2) dio 56.5 % (459/813): 8mb.local 92.2 %, papermark 80.1 % (tareas Trigger.dev 0/38),
NotyKT 71.3 % (Retrofit 8/16, Room 10/26), tchatchers 62.9 % (cliente Yew 0/16, Redis streams 0/17), quarkus-super-heroes 13.7 %
(rutas JAX-RS generadas desde OpenAPI 0/40, REST client 0/13, gRPC Kotlin 0/11, Kafka 0/6, service 0/27) y terminus 4.1 % (rutas
Hanami 0/40, ROM 0/40, Sidekiq 0/11, env 1/21). La detección seguía yendo librería a librería. En la ronda 3 esos 6 repos pasan a
ser conjunto de ajuste («ajuste ronda 3»; `split` sigue siendo `control2`) y, como en la ronda 2, todo son mecanismos genéricos en
`analyzer/cortex_graph/bridges.py` (sin nombres ni rutas de repos del benchmark), con un caso sintético por framework en
`analyzer/tests/test_bridges_frameworks.py` y la matriz de cobertura en [`FRAMEWORKS.md`](FRAMEWORKS.md).

Mecanismos nuevos:

- Contratos declarados: specs OpenAPI/Swagger (YAML y JSON; `servers`/`basePath`) → endpoint en la línea del verbo y handler =
  método homónimo del `operationId` en una clase/fichero del mismo proyecto que implementa el grupo (tag); sólo rellena huecos (no
  duplica rutas ya declaradas en código). Clases `@Path` sin ruta de método sitúan el endpoint en el `@Path` de clase; WebSockets
  `@WebSocket/@ServerEndpoint`.
- Clientes: `@RegisterRestClient`/`@Client` (MicroProfile, Micronaut) e interfaces C# con `[Get]` (Refit) como clientes
  declarativos; constructores de rutas encadenadas (`target(..).path(..)` en campos y variables + `.request().get()`); OkHttp
  `Request.Builder().url()`; Swift `URLRequest`/`AF.request` (interpolación `\(..)`); `xhr.open(verbo, url)`, `EventSource`,
  `WebSocket`; llamadas `Tipo::get("/x")` (Rust); llamadas por tipo declarado a interfaces cliente (`val s: Servicio` →
  `s.metodo()`), que es lo que conecta los repositorios de Android con Retrofit; GraphQL (operaciones `gql`/`graphql` → resolvers
  en mapas `Query/Mutation`, `@Query/@QueryMapping`, gqlgen, Strawberry/Graphene/Ariadne, Hot Chocolate) y tRPC (routers anidados
  → `trpc.a.b.useQuery()`).
- Rutas: Hanami 2 (`to: "a.b"` → `actions/a/b.rb`, `resource ..., to:`) y continuación de líneas en `routes.rb`; Remix, Astro,
  Litestar/Bottle (decoradores sueltos importados), Tornado, Falcon, Flask-RESTful, Javalin/Vert.x/Spark (`x.get("/p", h)` y
  `.handler()`), Grape, Rocket `mount`, warp, Plug.Router, shelf_router, Vapor, Play (`conf/routes`), SignalR `MapHub`, AdonisJS,
  y `export { h as GET }` de Next.js con la ruta en la línea de cada verbo.
- Eventos y jobs: canales SmallRye (`@Incoming/@Outgoing`, `@Channel` + `Emitter.send`) y Spring Cloud Stream/`StreamBridge` con
  el `topic/destination` de `mp.messaging.*`/`spring.cloud.stream.bindings.*`; Micronaut `@KafkaClient/@Topic`; clases-job de Ruby
  (`Sidekiq::Job`, `ApplicationJob`, Resque/Shoryuken..., también heredado) con nombres cualificados por módulo, inyección
  `job: Clase` y planificadores YAML (`class:`); mensajes tipados (`publishEvent(new T)` → `@EventListener(T)`, `T::dispatch` /
  `event(new T)` → `ShouldQueue`/listeners, Symfony Messenger, Hangfire `Enqueue<T>(x => x.M())`, Oban); tareas por fábrica
  (`task({id})`/`createFunction` ↔ `.trigger()`/`inngest.send`); colas por variante de enum (`E::V(..).spawn()` + `match cola { E::V
  => h() }` + mapeos `A::X => B::Y` + `queue:` en YAML); claves con plantilla (`progress:{id}` → `progress:*`); Celery
  `signature/send_task("nombre")`; Redis streams, SQS/SNS (cola = último segmento de URL/ARN), RQ `enqueue(func)`, BullMQ `Worker`.
- Datos: corregido el recorte de prefijos de cadena que se comía la `U` de `UPDATE` (afectaba a todos los lenguajes); `ALTER` y
  `TRUNCATE`; renombrados de tabla (`rename_table`, `Schema::rename`, `ALTER TABLE .. RENAME TO`); ROM (`schema :t`,
  `Repository[:t]`), Sequel; Panache (llamadas estáticas de entidad en Java, `implements PanacheRepository<E>`, `@MongoEntity`) y
  repositorio → entidad; Exposed (`EntityClass<E>(Tabla)`, `SchemaUtils`), Room (`@Insert/@Update/@Delete(E)`, `entities = [..]`);
  Drizzle, Knex/Supabase `.from()`, ent, Doctrine, Diesel, SeaORM, SwiftData/Core Data, Drift; el SQL en cadenas ya no cruza a tablas
  de un proyecto hermano cuando hay una candidata en el propio (Room ↔ Exposed en el mismo repo); `TableName()` de GORM con receptor
  sin nombre.
- Configuración: ficheros `.env.*` versionados en cualquier carpeta (`.env.tt`, `.env.production`...), clases de settings
  (Hanami/dry-configurable, pydantic) y sus lecturas `settings.campo`, `@ConfigProperty`, perfiles `%prod.` y claves con comillas de
  Quarkus, `*.env.vars.X`, HOCON con bloques `clave { }`, `$env/*` de SvelteKit y `env.X` importado de módulos `env`, `[env]` de
  `fly.toml`.
- Cableado: compose detectado por contenido (ficheros con otro nombre y fragmentos sin `services:`), alias de red/`container_name`/
  `hostname` como nombres de host, desempate por estructura de ruta paralela entre fragmentos, `render.yaml` (servicios, bases de
  datos, `envVars` con `fromService/fromDatabase/fromGroup`) y `Procfile` → módulo de entrada.
- gRPC: `*ImplBase` importado sin `Grpc.` (Kotlin), `@GrpcService` + interfaz Mutiny, `@GrpcClient` (campos/parámetros, también
  asignados a `this.x`) y enlace de inyección cliente → implementación; las copias del `.proto` en otros servicios enlazan con el
  endpoint RPC único.

Resultado (ver `results/RESULTS.md`): el antiguo examen final pasa de 56.5 % (459/813) a 99.5 % (809/813): 8mb.local 100 %,
papermark 100 %, NotyKT 100 %, terminus 99.2 %, quarkus-super-heroes 99.3 %, tchatchers 98.1 %; por tipo route 100 %, http 98.0 %,
rpc 100 %, event 98.8 %, data 99.5 %, env 100 %, service 100 %. Rondas anteriores sin cambios: ajuste ronda 1 98.8 % (1086/1099),
ajuste ronda 2 99.1 % (907/915). Precisión estimada 99.7 % (conservadora 99.1 %) sobre 173 aristas revisadas, 2 falsos positivos;
68 veredictos nuevos en `review.jsonl`. Tiempo de `analyze()` medido intercalando el `bridges.py` de partida y el actual (mínimo de dos pasadas): 17 repos previos 87.0 s → 85.8 s (−1.4 %), ajuste ronda 3 52.3 s → 51.1 s (−2.3 %), ningún repo por encima de +6 % (la búsqueda de ficheros `.env*` pasó a listar cada carpeta una vez en lugar de probar cada nombre).

Falsos negativos residuales de la ronda 3:

- tchatchers: el `WebSocket::open(&address)` recibe la URL por un mensaje del reactor (`get_ws_room_address`), no por un literal.
- terminus: `app/actions/extensions/build/create.rb` no se analiza porque `build/` está en las carpetas excluidas por defecto.
- quarkus-super-heroes: `Fight` → `initialize-database.js` (la etiqueta une la colección Mongo con el usuario `readWrite` del
  script de inicialización; no hay mención de la colección).

Falsos positivos vistos en la revisión: `dbConfig.property("port")` (NotyKT) se enlaza por nombre relajado con `PORT` aunque lee
`database.port` (falta seguir el prefijo de `config.config("database")`); al revisar también se corrigieron dos fuentes de ruido
antes de cerrar: cadenas de `Deps["a.extensions.b"]` tomadas como acceso a la asociación `extensions` (ahora se ignoran las
cadenas) y SQL de Room unido a la tabla Exposed del backend hermano.

## Examen ciego (control4)

Cuarto conjunto de verdad-terreno ciego (`split = "control4"` en `repos.toml`), etiquetado sin ejecutar Córtex ni mirar su
salida. Son 7 repos de producción con envoltorios propios (rutas registradas por utilidades del proyecto, URLs construidas por
helpers, trabajos como clases propias, configuración por objetos de ajustes), distintos de los 30 anteriores. Los repos se
clonaron en `cortex-bench-cache/flows/<name>` con `git clone --filter=blob:none` y se fijaron al SHA indicado; nunca se ejecutó
nada de ellos. Las etiquetas se generaron con un script por repo (patrones resueltos contra el archivo real, nunca líneas a
mano), se validó que cada `from`/`to` apunta a una línea existente no vacía y se reabrió al azar ~10 % (≈125 etiquetas, con
sesgo a http/event/data); se corrigieron el mapeo de URL del SDK de immich (cogía la URL de la función siguiente), una lectura
`import static` de Dependency-Track y los destinos `Dockerfile:1` de vaultwarden.

| repo | stack | etiquetas |
|---|---|---|
| immich | NestJS + Kysely + SDK oazapfts + web Svelte + app Flutter (cliente OpenAPI generado y canales Pigeon a Kotlin) | 254 (route 29, http 57, rpc 37, event 72, data 15, env 25, service 19) |
| paperless-ngx | Django/DRF + Celery + signals + Angular | 193 (route 56, http 35, event 44, data 22, env 18, service 18) |
| mastodon | Rails + Sidekiq + schema.rb + React/Redux | 190 (route 47, http 28, event 62, data 31, env 16, service 6) |
| vaultwarden | Rust Rocket (macros) + Diesel + make_config! | 174 (route 50, event 28, data 51, env 39, service 6) |
| dependency-track | JAX-RS v1/v2 (OpenAPI) + Dex (workflows/activities) + db-scheduler + JDO + SmallRye Config | 168 (route 30, event 62, data 24, env 47, service 5) |
| docmost | NestJS + Kysely + BullMQ + EventEmitter2 + React | 140 (route 27, http 27, event 35, data 32, env 15, service 4) |
| gotify | Go gin + GORM + UI React/axios | 120 (route 44, http 37, env 30, data 5, event 4) |

Total control4: 1239 etiquetas (event 307, route 283, env 190, http 184, data 180, service 58, rpc 37). Ningún repo supera el
21 % del total (el mayor es immich con 20,5 %).

Notas específicas de control4:

- Patrones nuevos: atributos de macro de Rocket (`#[get("..")]`, `routes![]`) y `make_config!`; rutas de Django con `re_path`
  anidados con `include` y `api_router.register` (viewsets con acciones heredadas; `update` = PUT y PATCH); Rails
  `resources`/`member`/`scope module` con helpers de API del frontend (`apiRequestGet('v1/..')`); controladores JAX-RS v1 por
  anotaciones y v2 por `operationId` de OpenAPI -> método de la implementación; workflows/activities de Dex
  (`createRun(new CreateWorkflowRunRequest<>(X.class))`, `ctx.activity(X.class)`), `recurringTask` de db-scheduler y
  constantes `ConfigKeys` -> `application.properties`; Celery (`apply_async`/`delay`/`s`, beat) y signals de Django; Sidekiq
  (`perform_async`/`perform_at`/`push_bulk`) y `sidekiq.yml`; BullMQ (`queue.add(QueueJob.X)` -> `case QueueJob.X`) y
  `@OnEvent`/`@OnJob`; SDK TypeScript (oazapfts) y cliente OpenAPI de Dart (no incluido en el repo; el `operationId` es el nombre
  del método del controlador) y Pigeon (`HostApi` Dart -> implementación Kotlin).
- tRPC no aparece; `rpc` son los canales Pigeon de immich (llamada Dart -> `override fun` de Kotlin; el cliente Dart generado
  `.g.dart` no está en el repo).
- Convenciones: `resources` de Rails y `ModelViewSet` de DRF se etiquetan una vez por verbo apuntando a la acción (Rails) o a la
  clase del viewset (DRF, nota `viewset expansion`); los atributos Rocket y los decoradores Nest apuntan del decorador a la
  función; el SDK de immich se etiqueta en la línea de la URL de oazapfts.
- Omisiones deliberadas: variables OIDC y LetsEncrypt de gotify; colas ee (search, ai, billing) de docmost; `/comments/resolve`
  y `/pages/labels*` de docmost (sin handler en el repo); llamadas `consume_task.apply_async`/grupos de Celery y
  `documents/bulk_edit.py`; `ModerationListSynchronizationScheduler` de mastodon (no existe); constantes `ConfigKeys` importadas
  con `import static` y `DexEngineInitializer` en el env de Dependency-Track; implementaciones Swift de Pigeon; `ciphers` y
  `organizations` de vaultwarden (rutas).
- Scopes parciales a propósito: gotify (completo salvo OIDC/LetsEncrypt en env), docmost (comment, label, favorite, watcher,
  share), paperless-ngx (vistas explícitas de `urls.py` + viewsets de correo/config/logs y 18 variables), mastodon (lists, polls,
  filters, scheduled_statuses, conversations, markers, bookmarks, favourites, announcements, preferences, custom_emojis y 18
  workers), vaultwarden (folders, sends, emergency_access, events, public, core/mod.rs; 30 variables), Dependency-Track (4
  recursos v1 y 6 grupos v2) e immich (partner, memory, session y api-key). Fuera de esos scopes no hay exhaustividad.

Debilidades conocidas de control4:

- `rpc` (37) solo existe en immich (Pigeon) y depende de receptores Dart con nombres de variable fijos
  (`_nativeSyncApi`, `networkApi`, ...); no hay tRPC ni gRPC en este conjunto.
- `service` (58) es el tipo más pobre: gotify no tiene (sin compose), vaultwarden/mastodon/dependency-track/docmost tienen 4-6
  y casi todo es `depends_on` de grano fino; paperless-ngx e immich suman 37 por repetir `depends_on` en varios compose.
- `http` falta en vaultwarden y dependency-track (el frontend está en otro repo) y en immich 27 de las 57 etiquetas son llamadas
  de web/ a funciones importadas del SDK y 4 de la app Flutter a un cliente generado ausente (se etiquetan por nombre de método).
- `env` de vaultwarden y paperless-ngx son lecturas de un campo/línea hacia un fichero de ejemplo (a menudo comentado) y
  `data` de gotify (5) es mínimo; `data` de immich se limita a partner/api_key y a las clases de tabla (los nombres de tabla
  cambiaron en una migración posterior).
- Los `event` de dependency-track (62) son en su mayoría llamadas de workflow a activity resueltas por clase, y los de immich
  (72) por nombre de evento/trabajo; ambos pueden ser ambiguos para un analizador sin soporte de esos buses.
- Los SHA fijados son el HEAD de la rama por defecto en octubre de 2026. `SPLITS` de `run.py` todavía no incluye `control4`
  (no se tocó el arnés).

## Ronda 4 de ajuste (antiguo examen ciego)

El examen ciego de la ronda 3 (control3) dio 28.3 % (279/985): plausible-analytics 81.3 %, Kavita 41.9 % (Hangfire 0/52),
woodpecker 36.9 % (http 0/35, xorm 0/25, env 0/15), micronaut-microservices-poc 26.0 %, redash 5.7 % (rutas registradas con un
envoltorio propio `api.add_org_resource(...)`), karakeep 4.1 % (Hono + tRPC + Drizzle + colas) y outline 2.1 % (Koa con nombres RPC
`router.post("documents.list")`, Sequelize, BullMQ). La lección: las reglas por librería (la matriz de FRAMEWORKS.md tenía 160
filas «soportadas») no sobreviven a proyectos reales, que envuelven los frameworks en sus propios helpers. En la ronda 4 esos 7 repos
pasan a ser conjunto de ajuste («ajuste ronda 4»; `split` sigue siendo `control3`) y los cambios son mecanismos estructurales,
independientes de la librería, en `analyzer/cortex_graph/structural.py` (mixin de `Bridges`), con casos sintéticos en
`analyzer/tests/test_bridges_structural.py` (sin nombres ni rutas del benchmark):

- Rutas por forma de la llamada: cualquier llamada (no test) con un literal con forma de ruta (`"/x"`, o un nombre RPC `"a.b"` pasado
  a un receptor tipo router) y una función inline o una referencia a una función/método/clase del repo (resuelta por import, por el
  propio fichero, por reexportación de un `index`, por paquete del monorepo según su `package.json` o por clase única). Las clases
  handler se expanden a sus métodos con nombre de verbo (`get/post/...`, `on_get`, y si no hay ninguno `index/show/create/...`; no en
  Ruby/Elixir, donde la clase es un controlador de acciones). Montajes: literal + router importado o variable local con rutas
  (también cadenas `new X().use().route("/v1", v1)` y `basePath("/api")`), componiendo prefijos. Prefijos de ruta heredados de la clase
  base (`[Route("api/[controller]")]` en `BaseApiController`), contratos (interfaz con `@Get` servida por la clase que la implementa,
  con su `@Controller`), variables de grupo redefinidas en bloques anidados (se elige la definición previa a la ruta) y scopes de
  Phoenix con alias de módulo y sentencias en varias líneas.
- Clientes: funciones cuyo parámetro fluye a la URL de una llamada cliente (`_request(method, path) => fetch(base + path)`,
  `fetchPaginated(endpoint) => client.post(endpoint)`) se propagan en cadena y entre ficheros (`this._get("/api/x")`); valores
  alternativos de ternarios, reasignaciones y funciones locales (`saveOrCreateUrl(d)`); base del cliente leída del inicializador de la
  variable (`createClient({baseUrl})`, `axios.create({baseURL: env ? env : "/api/"})`); URLs con base desconocida (`this.baseUrl +
  'device'`) casan por segmentos literales y menor prefijo extra; nombres RPC con punto por sufijo único; interfaces cliente que
  extienden un contrato anotado; procedimientos tRPC llamados por su nombre cualificado (`c.var.api.tags.list()`,
  `api.tags.list.queryOptions()`) como aristas `rpc`.
- Eventos y jobs: productores por referencia (`f.delay()`, `new XTask().schedule()`, `queue.enqueue(f)`, `{"func": f}`, cron
  `{"0 * * * *", Mod}`, `BackgroundJob.Enqueue(() => svc.M())` resuelto a la implementación de la interfaz del receptor, con
  sobrecarga por número de argumentos); claves compartidas entre una llamada productora y un registro con handler
  (`Queue.enqueue()` ↔ `createRunner(Queue, {run: wrap("x", fn)})`, `TriggerJob(K)` ↔ `AddOrUpdate(K, ...)`); `emit(event.name)`
  dentro de `case "x":` de un switch; llamantes de métodos de interfaces productoras (`@KafkaClient`) y de funciones `enqueue_*`.
- Datos: clases que declaran su tabla (`__tablename__`, `tableName`, `@Table({tableName})`, `[Table]`, `@Entity`/`@MappedEntity`
  también en `record`, `TableName()`), usos cualificados (`models.X`, imports reexportados) y en Go `new(pkg.M)`/`[]*pkg.M` dentro de
  funciones con operaciones de base de datos; tablas del DSL (Drizzle) ↔ `CREATE TABLE`; relaciones entre modelos (campos tipados y
  herencia); HQL `from Entidad`; las instantáneas generadas de EF (`BuildTargetModel`) ya no generan aristas.
- Entorno: cualquier NOMBRE_EN_MAYÚSCULAS leído en código (literal exacto, `.X`, clave `X:`) que el repo define (`.env*` incluidos
  `.env-example`, bloques YAML cuyo nombre contiene `env` incluidas anclas `x-...-environment`, bloques `env` de JSON como
  `launchSettings.json`, `ENV` multilínea de Dockerfile, `export X=` de shell); lecturas `$X`/`%(ENV_X)s` en scripts y `.conf`;
  opciones declaradas con nombre y variable en el mismo literal (`{Name: "open", Sources: EnvVars("X_OPEN")}` + `c.Bool("open")`);
  módulos `environment.*` que exportan un objeto; `${clave}` de propiedades en cualquier anotación.
- Servicios: `build:` y `command:` de compose → Dockerfile y función/`case` del `ENTRYPOINT`; ids de servicio en anotaciones cliente
  (`@Client(id = "x")`) ↔ `*.application.name`; manifiestos: kustomize `resources`, selector de Service ↔ etiquetas del workload,
  `claimName`, `backend.service.name`, `secretRef/configMapRef` (en la misma carpeta); `depends_on` y URLs prefieren el servicio del
  mismo fichero compose salvo en los `*.override.*`.

Código por librería sustituido: `api.add_resource(...)` (Flask-RESTful) y las cascadas `..get("/x", h)` (shelf_router) los cubre el
registro estructural. Arreglos generales hechos al revisar: imports Python multilínea entre paréntesis y reexportaciones de
`__init__.py`, alias `@scope/...` resueltos por las aristas de import, resolución `paquete.Función` en Go por carpeta del paquete,
constructores Go de servicios gRPC que devuelven la interfaz (se toma el `return &T{}`),
nodos de tabla que colisionaban con una clase homónima (migraciones de EF), lecturas de texto cacheadas tras el escaneo.

Arnés: `control4` (siguiente examen ciego) no se clona, analiza ni lee (`SPLITS`); nueva regla de registro sobre el propio handler
(ver «Cómo se puntúa»). Carpetas `build/` anidadas en el código y no ignoradas por git ya no se excluyen
(`analyze.tracked_source_dir`; era el falso negativo residual de terminus `app/actions/extensions/build/create.rb`).

Resultado (ver `results/RESULTS.md`): el antiguo examen ciego pasa de 28.3 % (279/985) a 97.3 % (958/985): plausible-analytics,
outline y karakeep 100 %, redash 99.3 %, Kavita 96.6 %, micronaut-microservices-poc 93.5 %, woodpecker 91.3 %; por tipo route
99.6 %, http 97.1 %, rpc 100 %, event 94.2 %, data 96.2 %, env 100 %, service 96.8 %. Rondas anteriores: ajuste ronda 1 98.8 %
(1086/1099, igual), ajuste ronda 2 99.1 % (907/915, igual), ajuste ronda 3 99.6 % (810/813, antes 809). Precisión estimada
98.9 % (conservadora 98.3 %) sobre 251 aristas revisadas, 5 falsos positivos; en el ajuste ronda 4, 96.8 % (conservadora 93.5 %).
Se revisaron 116 aristas nuevas (`review.jsonl`): 14 falsos positivos, de los que se corrigieron 11 antes de cerrar (mocks
generados tomados como acceso a datos, el `Fallback` de un cliente declarativo sirviendo el contrato, cliente débil duplicado sin la
base en la misma línea, `pathFilter()` de tRPC, `Task.Delay` resuelto a una interfaz TS, cron en un campo de clase, `using` de C#
tomado como acceso a un `DbSet`, clase controladora de Phoenix expandida por verbo); quedan los modelos/servicios homónimos entre
microservicios de micronaut (3).

Tiempo de `analyze()` intercalando el `bridges.py` de la ronda 3 y el actual (mínimo de dos pasadas, `results/baseline_r4.json`):
30 repos 428.1 s → 457.3 s (+6.8 %); ajuste ronda 1 53.6 → 56.8 s, ronda 2 37.6 → 38.6 s, ronda 3 59.1 → 67.4 s, ronda 4
277.8 → 294.5 s. El coste propio de los mecanismos nuevos es pequeño (p. ej. terminus 1.3 → 1.5 s de `link_bridges`); las
mayores subidas por repo (quarkus-super-heroes +27 %, terminus +26 %, outline +17 %) vienen sobre todo del *layout* de
`analyze.py`, que con unas pocas aristas nuevas forma más comunidades (terminus: 18 → 20 comunidades, `force_layout` 3.2 → 5.5 s).

Falsos negativos residuales de la ronda 4:

- woodpecker: los 12 eventos son un pubsub en memoria detrás de una interfaz (`Scheduler.PublishPipelineEvent` ↔ `Subscribe`,
  `PushAtOnce` ↔ `Poll`, `logger.Write` ↔ `Tail`) con temas dinámicos; no hay clave ni referencia compartida que los empareje.
- micronaut-microservices-poc: datos a través de repositorios propios (`PolicyDocumentDb` con `entityManager`), la colección Mongo
  `product` y el índice Elasticsearch `policy_stats` (7); `ZK_HOSTS localhost:2181` casa con el kafkaserver de otro compose.
- Kavita: el handler de `upload-theme` comparte id de nodo con una sobrecarga (2), `httpResource(() => url)` y `url(...)` de
  `FontFace` no se reconocen como clientes, y un `Sync` de Hangfire ambiguo entre dos servicios.
- redash: `widget.save` construye la URL con `${url}/${this.id}` tras reasignar `url` en una rama (1).

## Ronda 5 de ajuste (antiguo examen ciego control4)

El examen ciego de la ronda 4 (control4) dio 46,6 % (577/1239): mastodon 84,7 %, docmost 64,3 %, paperless-ngx 50,3 %, immich 45,7 %,
gotify 36,7 %, vaultwarden 31,6 % y dependency-track 8,3 %; por tipo route 80 %, service 79 %, event 46 %, http 40 %, env 32 %, data
17 % y rpc 0 %. Los fallos no eran exóticos: modelos de Django que heredan de una base abstracta propia, señales `connect`/`send`, beat de
Celery, `@action` de DRF, `include([...])` en línea, variables leídas por envoltorios (`parseInt(&c.Port, EnvPort)`,
`__get_boolean("PAPERLESS_X")`, `ConfigKeys.X`, campos de `make_config!`) y definidas en plantillas con líneas comentadas
(`paperless.conf.example`, `.env.template`), Diesel (`table!`), JDO (`@PersistenceCapable`), Kysely (`selectFrom('t')`, `interface DB`),
gin con receptores tipados y grupos encadenados, BullMQ con `case QueueJob.X`, Sidekiq `push_bulk`, workflows por `X.class`, SDK
generados (oazapfts y cliente Dart de OpenAPI fuera del repo), servicios Angular que heredan `getResourceUrl()` y canales Pigeon
Dart → Kotlin. La matriz de FRAMEWORKS.md era menos profunda de lo que decía: casi todo era la forma más común de idiomas cubiertos sólo
en su variante canónica.

En la ronda 5 esos 7 repos pasan a ser conjunto de ajuste («ajuste ronda 5»; `split` sigue siendo `control4`; `control5` queda como
examen ciego en `SPLITS`/`BLIND` sin clonar, analizar ni leer). Cada arreglo se escribió primero como caso sintético en su forma
canónica y una o dos variantes (alias, otro fichero, anotaciones con argumentos, configuración en YAML/properties/.env/compose) en
`analyzer/tests/test_bridges_idioms.py` (27 casos), sin nombres ni rutas del benchmark, y se implementó en
`analyzer/cortex_graph/idioms.py` (mixins `Idioms`, `CrossLanguage`, `UrlBuilders`, `SchemaMaps`, `GeneratedClients`) más ajustes en
`bridges.py`/`structural.py`. La lista de mecanismos está en [`FRAMEWORKS.md`](FRAMEWORKS.md), sección «Ronda 5»; en resumen: datos por
nombre literal en constructores de consultas, tablas por macro y modelos por atributo/anotación, herencia de modelos, registro en el
ORM, mapas de esquema tipados (también `.d.ts`), DDL en migraciones de código y renombrados por lista; entorno por plantillas,
envoltorios, constantes y campos de configuración; señales/observadores, claves cualificadas de despacho, jobs por referencia de clase,
tareas por ruta punteada y hubs de notificación; receptores tipados, grupos encadenados, viewsets, OpenAPI repartido y clientes
generados; y contratos entre lenguajes.

Revisión de precisión durante la ronda (además de la muestra del arnés): dos muestras dirigidas de aristas nuevas (164 y 72 aristas,
estratificadas por repo y tipo) encontraron 12 patrones de falso positivo que se corrigieron antes de cerrar, cada uno con su caso en
`test_precision_guards`: `switch` sobre enums fuera de un consumidor (reductores, `Notification.path`), objetos `{name: Q.X}` de
configuración de colas (`registerQueue`), `new Worker()` de Node unido a un worker de Elixir, `signal.Notify` de Go tomado como el
notificador del repo, firmas de interfaz Go tomadas como llamadas o como accesos a datos, `Group("/x", middleware)` como ruta, claves de
un diccionario `{"app.tasks.f": ...}` como tareas encoladas, argumentos con nombre (`update(auth_user=...)`) y opciones de `class
Config` como campos de configuración, nombres en minúscula leídos por un envoltorio (`_tool("ffprobe")`), listas YAML sin valor fuera
de `environment:`, ficheros de dominio (`*notification*`, `*subscription*`) tomados como hubs, SQL unido a esquemas de fixtures de test y
constantes de entorno citadas en mensajes de log. De las 86 aristas nuevas de la muestra del arnés, 2 eran falsos positivos (los dos
últimos patrones), ya corregidos.

### Etiquetas y puntuación

- Etiquetas corregidas (dependency-track, 2): `apiserver depends_on postgres` y `jdbc host postgres` apuntaban a `dev/compose.yaml:54`, que
  es la clave `postgres:` dentro de `depends_on` del propio apiserver (el patrón del etiquetado casó la primera aparición); el destino
  es el servicio `postgres` (línea 75). Nota `label fix r5` en la etiqueta.
- Puntuación (ver «Cómo se puntúa»): decorado sobre anotaciones (necesario porque los analizadores de lenguaje, modificados en paralelo
  en esta ronda, sitúan ahora las declaraciones en su palabra clave y no en la primera anotación), ruta declarada sobre el propio handler
  con verbo y sufijo de ruta comprobados, y destino de `service` en la línea 1 de un fichero. Con las etiquetas y reglas finales, el
  punto de partida de control4 es 588/1239 (47,5 %: +1 vaultwarden, +8 dependency-track, +2 immich); las rondas 1-4 no cambian con la
  puntuación nueva sobre los grafos de partida.
- Sin cambiar (se documentan como residuales): las dos reglas traefik de dependency-track (`traefik.http.routers.x.rule` en las
  etiquetas del propio servicio: origen y destino caen en el mismo bloque, la etiqueta no es puntuable como camino) y los 4
  `depends_on` de `e2e/docker-compose.dev.yml` de immich (Córtex trata `e2e/` como carpeta de tests y no la analiza como despliegue).

### Resultado (ver `results/RESULTS.md`)

Ajuste ronda 5 (antiguo control4): 46,6 % (577/1239; 47,5 % con las reglas finales) → **99,0 % (1226/1239)**: gotify, docmost,
paperless-ngx y mastodon 100 %, vaultwarden 99,4 %, immich 97,2 %, dependency-track 97,0 %; por tipo route 100 %, http 100 %, rpc 97,3 %,
event 99,7 %, data 100 %, env 98,9 %, service 84,5 %. Rondas anteriores: ajuste ronda 1 98,8 % (1086/1099, igual), ronda 2 99,2 % (908/915,
antes 907: la ruta websocket de full-stack-flutter-app, cuya clausura delimita ahora el analizador de Dart modificado en paralelo), ronda 3 99,6 % (810/813, igual), ronda 4 97,3 % (958/985, igual). Precisión
estimada 99,0 % (conservadora 98,4 %) sobre 330 aristas revisadas, 5 falsos positivos (los 3 de micronaut de la ronda 4 y uno en cada una
de las rondas 2 y 3); en el ajuste ronda 5, 70 revisadas y 0 falsos positivos en la muestra final (conservadora 96,5 %).

Tiempo de `analyze()` intercalando `bridges.py`/`structural.py` de partida y los actuales (mínimo de dos pasadas, `CORTEX_EMBED_MODEL=off`,
`results/baseline_r5.json`) en los cinco repos más grandes: 212,0 s → 227,0 s (+7,1 %): mastodon 53,5 → 55,3, immich 48,1 → 53,8 (es el que
más aristas nuevas tiene: +2000 de datos de Kysely y migraciones), dependency-track 57,8 → 61,8, paperless-ngx 31,7 → 34,6 y ghostfolio
20,9 → 21,5. Una primera versión costaba +16 %; se recortó con resolución tipada sólo como último recurso, constantes de configuración
resueltas al final y sólo para valores definidos por el repo, contratos entre lenguajes sólo para interfaces/clases abstractas y llamantes
del lenguaje que las declara, y filtros rápidos antes de cada expresión regular. El resto de segundos de `RESULTS.md` son de una única
ejecución en una máquina con carga variable (otros procesos en paralelo) y no son comparables.

Falsos negativos residuales de la ronda 5 (13):

- immich (7): los 4 `depends_on` de `e2e/` (arriba), los hosts por defecto `dto.REDIS_HOSTNAME || 'redis'` y `|| 'database'`, que ya se
  resuelven al servicio pero quedan ambiguos entre las variantes del compose de `docker/` con el mismo servicio, y `cancelHashing`
  (el analizador de Dart no delimita el método que hace la llamada, así que el origen no tiene aristas).
- dependency-track (5): las 2 reglas traefik, `API_BASE_URL: http://localhost:8080` (el puerto 8080 lo publica traefik pero también es el
  puerto por defecto de las aplicaciones Spring del repo) y las 2 lecturas de `dt.outbound.allowed-destinations` en `HttpClient`.
- vaultwarden (1): `send_auth_response` existe en dos hubs (WebSocket y suscripciones anónimas) y la llamada no se desambigua por tipo.

Tests: `analyzer/tests/test_bridges_idioms.py` (27 casos). El caso «Django REST Framework» de `test_bridges_frameworks.py` se actualizó
a la expansión por verbo. Dos casos previos (`data:Room (Android)` y `test_file_routes_dart_clients_and_annotated_models`) fallan también
con el `bridges.py`/`structural.py` de partida: se deben a los cambios paralelos en los analizadores de Kotlin/Dart, no a esta ronda.
