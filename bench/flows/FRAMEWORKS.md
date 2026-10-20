# Matriz de frameworks y librerías (flujos entre componentes)

Cobertura de Córtex para los frameworks web/móvil/backend y las librerías de mensajería, ORM y configuración más usados, en
Python, JS/TS, Go, Java, Kotlin, C#, PHP, Ruby, Rust, Elixir, Dart/Flutter, Swift y Scala. Cada fila soportada tiene un caso
sintético mínimo en `analyzer/tests/test_bridges_frameworks.py` (parametrizado por `grupo:nombre`, el mismo nombre que la fila)
que declara un repo diminuto y los flujos que Córtex debe unir; el test recorre el grafo igual que el arnés (`bench/flows/run.py`):
arista directa o un salto por un nodo endpoint/topic/variable/tabla, sólo con las aristas del tipo.

- **antes**: el mismo caso ejecutado con `analyzer/cortex_graph/bridges.py` tal como estaba al cerrar la ronda 2.
- **después**: con el código actual (ronda 3). `parcial` = el caso pasa pero hay variantes habituales que no se reconocen (columna
  notas); `no` = no se reconoce.
- Las filas no son una lista cerrada de sintaxis: cada mecanismo es una regla genérica (verbo + ruta en decorador/anotación, rutas
  por ficheros, clientes que casan con endpoints declarados, nombres de tablas/temas/variables declarados) y suele cubrir
  variantes y frameworks hermanos no listados.
- Orden aproximado por popularidad dentro de cada grupo.

```bash
cd analyzer
.venv/bin/python -m pytest tests/test_bridges_frameworks.py -q
.venv/bin/python -m pytest tests/test_bridges_frameworks.py -q -k "Hanami or Rocket"   # filas concretas
```

## Resumen

Total 184 filas · antes: soportado 95, parcial 1, no 88 · después: soportado 160, parcial 16, no 8

Ronda 5: 27 mecanismos transversales nuevos (sección «Ronda 5» al final), uno o más casos por mecanismo en
`analyzer/tests/test_bridges_idioms.py`; Django REST Framework pasa a expandir por verbo.

Ronda 4: dos filas del bloque «No cubierto» pasan a soportadas (cadenas `new Elysia().get()` sin variable y Kubernetes Ingress →
Service, con caso en `test_bridges_frameworks.py`) y se añaden los mecanismos estructurales de la sección «Ronda 4» (186 filas:
soportado 162, parcial 16, no 8). Tornado, Falcon y Flask-RESTful apuntan ahora al método del verbo en vez de a la clase.

## Matriz

### Servidores HTTP (ruta → handler)

| framework / librería | lenguaje | qué se reconoce | antes | después | notas |
|---|---|---|---|---|---|
| Flask | Python | `@app.route`/`@bp.route` (+ `methods=`), `register_blueprint(url_prefix)`, `add_url_rule` | soportado | **soportado** |  |
| FastAPI | Python | decoradores `@router.<verbo>`, `APIRouter(prefix)`, `include_router(prefix)` | soportado | **soportado** |  |
| Django | Python | `path`/`re_path`/`url` + `include()` anidados | soportado | **soportado** |  |
| Django REST Framework | Python | routers `register()` (lista + detalle) y vistas genéricas | soportado | **soportado** |  |
| Starlette | Python | `Route(path, endpoint, methods)` | soportado | **soportado** |  |
| Litestar | Python | decoradores sueltos `@get("/x")` importados del framework | no | **parcial** | los `Controller` con `path` de clase no componen el prefijo |
| aiohttp | Python | `app.router.add_<verbo>`, `web.<verbo>` | soportado | **soportado** |  |
| Express | JS/TS | `app|router.<verbo>`, `router.route().get()`, montajes `app.use(prefix, router)` | soportado | **soportado** |  |
| Fastify | JS/TS | `fastify.<verbo>`, `route({method,url,handler})`, `register(prefix)` | soportado | **soportado** |  |
| Koa | JS/TS | `@koa/router` `.get/.post` | soportado | **soportado** |  |
| Hapi | JS/TS | `server.route({ method, path, handler })` | soportado | **soportado** |  |
| NestJS | JS/TS | `@Controller` + `@Get/...`, prefijo global y versionado URI | soportado | **soportado** |  |
| Next.js app router | JS/TS | rutas por ficheros `app/**/route.ts` con `export GET/POST` (y `export { h as GET }`) | soportado | **soportado** |  |
| Next.js pages API | JS/TS | `pages/api/**` con export por defecto | soportado | **soportado** |  |
| Nuxt server routes | JS/TS | `server/api|routes/**.<verbo>.ts` | soportado | **soportado** |  |
| SvelteKit endpoints | JS/TS | `src/routes/**/+server.ts` con `export GET/POST` | soportado | **parcial** | las *form actions* de `+page.server.ts` no se modelan |
| Remix | JS/TS | rutas planas `app/routes/a.$b.tsx`: `loader` → GET, `action` → POST | no | **parcial** | `action` sólo como POST; carpetas `route.tsx` dentro de `app/` las toma antes la regla de Next |
| Astro endpoints | JS/TS | `src/pages/**.ts` con `export GET/POST` | no | **soportado** |  |
| gin | Go | `r.GET`, grupos `Group()` | soportado | **soportado** |  |
| echo | Go | `e.GET`, grupos | soportado | **soportado** |  |
| fiber | Go | `app.Get`, `Group()` | soportado | **soportado** |  |
| chi | Go | `r.Get`, `r.Route("/x", func)` | soportado | **soportado** |  |
| gorilla/mux | Go | `HandleFunc(...).Methods()`, `PathPrefix` | soportado | **soportado** |  |
| net/http ServeMux | Go | `mux.HandleFunc("GET /x", h)` (Go 1.22) | soportado | **soportado** |  |
| Spring MVC | Java/Kotlin | `@RequestMapping` + `@GetMapping/...` | soportado | **soportado** |  |
| Spring WebFlux functional | Java/Kotlin | `route().GET("/x", h::m)` | soportado | **soportado** |  |
| Micronaut | Java/Kotlin | `@Controller("/x")` + `@Get` | soportado | **soportado** |  |
| JAX-RS / Quarkus | Java/Kotlin | `@Path` de clase + `@GET/@Path`; endpoint en el `@Path` de clase si el método no tiene ruta; `@WebSocket/@ServerEndpoint` | soportado | **soportado** |  |
| OpenAPI spec (generated server interfaces) | YAML/JSON | `paths` + `operationId` del spec → método homónimo de la clase que implementa el grupo (tag) en el mismo proyecto | no | **parcial** | sin `operationId` no se resuelve el handler |
| Ktor | Kotlin | `routing { route("/x") { get {} } }`, `fun Route.x()` montadas | soportado | **soportado** |  |
| Javalin | Java/Kotlin | `app.get("/x", Ctrl::m)` y lambdas | no | **soportado** |  |
| Vert.x Web | Java | `router.get("/x").handler(this::h)` | no | **soportado** |  |
| ASP.NET Core controllers | C# | `[Route]` + `[HttpGet]`, `[controller]` | soportado | **soportado** |  |
| ASP.NET Core minimal APIs | C# | `MapGet/MapPost`, `MapGroup`, métodos de extensión `Map*` | soportado | **soportado** |  |
| Laravel | PHP | `Route::<verbo>`, `resource/apiResource`, grupos con prefijo | soportado | **soportado** |  |
| Symfony | PHP | atributos `#[Route(path, methods)]` | soportado | **parcial** | las rutas en YAML/XML (`config/routes/*.yaml`) no |
| Slim | PHP | `$app->get(path, [Clase, "m"])` | soportado | **soportado** |  |
| Rails | Ruby | `routes.rb`: `resources`, verbos, `namespace/scope`, Devise | soportado | **soportado** |  |
| Sinatra | Ruby | `get "/x" do` | soportado | **soportado** |  |
| Hanami 2 | Ruby | `get "/x", to: "a.b"` → `actions/a/b.rb`, `resource ..., to:`, `scope` | no | **soportado** |  |
| Grape | Ruby | `prefix`, `version (path)`, `resource/namespace/route_param` + verbos | no | **parcial** | los `mount` de sub-APIs no componen prefijo |
| axum | Rust | `.route(path, get(h))`, `nest`, `merge` | soportado | **soportado** |  |
| actix-web | Rust | atributos `#[get]`, `web::resource/scope` | soportado | **soportado** |  |
| Rocket | Rust | atributos `#[get]` + `mount("/x", routes![..])` | no | **soportado** |  |
| warp | Rust | `warp::path!(..)`/`path("x")` + `warp::get()` + `and_then(h)` en la misma sentencia | no | **parcial** | filtros repartidos en variables y combinados con `.or()` no |
| Phoenix | Elixir | `router.ex`: `scope`, verbos, `resources` | soportado | **soportado** |  |
| Plug.Router | Elixir | `use Plug.Router` + `get "/x" do` | no | **soportado** |  |
| dart_frog | Dart | rutas por ficheros `routes/**` + `case HttpMethod.x` | soportado | **soportado** |  |
| shelf_router | Dart | `router.get("/x", h)` / cascada `..get` | no | **soportado** |  |
| Vapor | Swift | `app.get("a", ":b") { }`, `grouped()`, `use:` | no | **parcial** | colecciones `RouteCollection.boot` registradas con `register(collection:)` no componen prefijo |
| Play Framework | Scala/Java | `conf/routes` (`GET /x controllers.C.m`) | no | **soportado** |  |
| Hono | JS/TS | `app.<verbo>` sobre `new Hono()`; ronda 4: cadenas `new Hono().use().get()`, `.route("/x", sub)`, `basePath()` | soportado | **soportado** |  |
| Elysia (cadenas sin variable) | JS/TS | `new Elysia().get("/x", h)` (registro estructural) | no | **soportado** | ronda 4 |
| Sanic | Python | decoradores `@app.<verbo>` / blueprints | soportado | **soportado** |  |
| Tornado | Python | tuplas `(r"/x", Handler)` de `Application([...])` | no | **soportado** |  |
| Falcon | Python | `app.add_route("/x", Resource())` | no | **soportado** |  |
| SignalR | C# | `MapHub<Hub>("/x")` → clase del hub | no | **parcial** | las invocaciones `connection.invoke("Método")` del cliente no se enlazan |
| AdonisJS | JS/TS | `router.<verbo>(path, [Controller, "acción"])` | no | **soportado** |  |
| serverless.yml http | YAML | eventos `http`/`httpApi` de `serverless.yml` → handler | soportado | **soportado** |  |
| Flask-RESTful / RESTX | Python | `api.add_resource(Res, "/x")` y envoltorios propios (`api.add_org_resource(Res, "/a", "/b")`), `@ns.route` sobre clases; desde la ronda 4 cada verbo apunta al método `get/post/...` de la clase | no | **soportado** | ronda 4: registro estructural (cualquier llamada con literal de ruta + clase) |
| Bottle | Python | decoradores sueltos `@route`/`@get` importados de bottle | no | **soportado** |  |

### Clientes HTTP (llamada → handler del mismo repo)

| framework / librería | lenguaje | qué se reconoce | antes | después | notas |
|---|---|---|---|---|---|
| fetch | JS/TS | `fetch(url, {method})` con plantillas, constantes y bases | soportado | **soportado** |  |
| axios | JS/TS | `axios.<verbo>`, instancias con `baseURL` | soportado | **soportado** |  |
| ky | JS/TS | `ky`/instancias `prefixUrl` | soportado | **soportado** |  |
| ofetch / $fetch | JS/TS | `$fetch`, `ofetch`, `useFetch` | soportado | **soportado** |  |
| Angular HttpClient | TS | `this.http.get<T>(url)` | soportado | **soportado** |  |
| XMLHttpRequest / EventSource | JS/TS | `xhr.open(verbo, url)`, `new EventSource/WebSocket(url)` | no | **soportado** |  |
| React Query wrapper | JS/TS | cliente dentro de `queryFn`/`useQuery` | soportado | **soportado** |  |
| requests | Python | `requests.<verbo>`, `session.<verbo>` | soportado | **soportado** |  |
| httpx | Python | `httpx`/`AsyncClient(base_url)` | soportado | **soportado** |  |
| aiohttp client | Python | `session.get(url)` | soportado | **soportado** |  |
| OkHttp | Java/Kotlin | `Request.Builder().url(..).post(..)` | no | **soportado** |  |
| Retrofit | Java/Kotlin | interfaces `@GET("/x")` y llamadas `servicio.m()` por tipo declarado | soportado | **soportado** |  |
| OpenFeign | Java | `@FeignClient` + `@GetMapping` | soportado | **soportado** |  |
| Spring WebClient / RestClient | Java/Kotlin | `.get().uri(..)`, `RestTemplate`, `@HttpExchange` | soportado | **soportado** |  |
| MicroProfile REST Client | Java | `@RegisterRestClient` + `@Path/@GET` | no | **soportado** |  |
| JAX-RS client (WebTarget) | Java | `ClientBuilder.target(..).path(..)` en campos/variables + `.request().get()` | no | **soportado** |  |
| .NET HttpClient | C# | `GetFromJsonAsync/PostAsJsonAsync`, `HttpRequestMessage` | soportado | **soportado** |  |
| Refit | C# | interfaces `[Get("/x")]` | no | **soportado** |  |
| Guzzle / Laravel Http | PHP | `Http::post`, `$client->request` | soportado | **soportado** |  |
| Faraday / HTTParty | Ruby | `HTTParty.get`, `Faraday`, `Net::HTTP` | soportado | **soportado** |  |
| reqwest | Rust | `client.get(format!(..))` | soportado | **soportado** |  |
| gloo-net / Yew | Rust | `Request::get(&format!(..))` y envoltorios `Tipo::get("/x")` | no | **soportado** |  |
| dio (Dart) | Dart | `dio.<verbo>(path)` | soportado | **soportado** |  |
| package:http (Dart) | Dart | `http.get(Uri.parse(..))` | soportado | **soportado** |  |
| Alamofire | Swift | `AF.request(url, method:)` | no | **soportado** |  |
| URLSession | Swift | `URLRequest(url: URL(string:))` + `httpMethod` | no | **soportado** |  |
| Ktor client | Kotlin | `client.get(url)`, builders `url {}` | soportado | **soportado** |  |
| Apollo / GraphQL client | JS/TS/Python/Go | operaciones `gql`/`graphql` → campo raíz → resolver | no | **parcial** | documentos `.graphql` sueltos y clientes generados (Apollo Kotlin/Swift) no |
| tRPC | TS | `router({ x: procedure.query() })` anidados → `trpc.x.useQuery()`, y (ronda 4) cualquier llamada por nombre cualificado `caller.x.y()`, `api.x.y.queryOptions()` como arista `rpc` | no | **parcial** | `mergeRouters` y routers creados dinámicamente no |

### GraphQL (operación del cliente → resolver)

| framework / librería | lenguaje | qué se reconoce | antes | después | notas |
|---|---|---|---|---|---|
| graphql-yoga / resolver maps | JS/TS | mapas `Query/Mutation: { campo: resolver }` (Apollo Server, yoga, mercurius) | no | **soportado** |  |
| NestJS GraphQL / TypeGraphQL | TS | `@Query()/@Mutation()` en resolvers | no | **soportado** |  |
| gqlgen | Go | `func (r *queryResolver) Campo(..)` | no | **soportado** |  |
| Strawberry | Python | `@strawberry.type class Query` + `@strawberry.field`; Graphene `resolve_x`; Ariadne `query.field("x")` | no | **soportado** |  |
| Hot Chocolate | C# | clases `Query/Mutation` o `[QueryType]` (`GetX` → `x`) | no | **soportado** |  |
| Spring for GraphQL | Java/Kotlin | `@QueryMapping/@MutationMapping` | no | **soportado** |  |

### RPC

| framework / librería | lenguaje | qué se reconoce | antes | después | notas |
|---|---|---|---|---|---|
| gRPC Go | Go | `Register*Server`, `Unimplemented*Server`, `New*Client` | soportado | **soportado** |  |
| gRPC Python | Python | `*Servicer`, `*Stub` | soportado | **soportado** |  |
| gRPC Java / Kotlin | Java/Kotlin | `*ImplBase` (también importado sin `Grpc.`), `@GrpcService`, `@GrpcClient`, stubs Mutiny | no | **soportado** |  |
| gRPC .NET | C# | `X.XBase`, `X.XClient`, `MapGrpcService` | soportado | **soportado** |  |
| gRPC Node | JS/TS | `addService(x.service, {..})` | soportado | **soportado** |  |
| tonic (Rust) | Rust | `impl Servicio for Tipo` | soportado | **soportado** |  |

### Mensajería, colas, jobs y eventos

| framework / librería | lenguaje | qué se reconoce | antes | después | notas |
|---|---|---|---|---|---|
| Kafka (Spring) | Java/Kotlin | `KafkaTemplate.send` → `@KafkaListener` | soportado | **soportado** |  |
| Kafka (kafkajs) | JS/TS | `producer.send({topic})` → `consumer.subscribe` | soportado | **soportado** |  |
| Kafka (SmallRye / MicroProfile) | Java/Kotlin | `@Incoming/@Outgoing`, `@Channel` + `Emitter.send`, `mp.messaging.*.topic` | no | **soportado** |  |
| RabbitMQ (amqplib / pika) | JS/Python/C#/Go | `sendToQueue/basic_publish/BasicPublish` ↔ `consume/basic_consume` | soportado | **soportado** |  |
| AWS SQS | Python/JS | `send_message/receive_message(QueueUrl)`, `SendMessageCommand` (cola = último segmento de la URL/ARN) | no | **parcial** | SNS sólo como productor; suscripciones SNS→SQS de infraestructura no |
| NATS | Go/JS/Python | `Publish/Subscribe(subject)` | soportado | **soportado** |  |
| Redis pub/sub | cualquiera | `publish/subscribe`, canales con plantilla (`progress:{id}` → `progress:*`) | no | **soportado** |  |
| Redis streams | cualquiera | `xadd` ↔ `xread/xreadgroup` (`STREAMS`, dict, `Streams:`) | no | **soportado** |  |
| Celery | Python | `@task(name)`, `.delay/.apply_async`, `send_task/signature("nombre")` | soportado | **soportado** |  |
| RQ | Python | `q.enqueue(func)` → función | no | **soportado** |  |
| Dramatiq | Python | `@dramatiq.actor` + `.send()` | soportado | **soportado** |  |
| BullMQ / Bull | JS/TS | `new Queue(n).add()` ↔ `new Worker(n, h)`, `@Process` | no | **soportado** |  |
| Sidekiq / ActiveJob | Ruby | clases con `Sidekiq::Job`/`ApplicationJob` (también heredado) + `perform_async/perform_later`, inyección `job: Clase`, `sidekiq_scheduler.yml` | no | **soportado** |  |
| Oban | Elixir | `use Oban.Worker` + `Worker.new(args)` | no | **soportado** |  |
| MassTransit / integration events (.NET) | C# | `IConsumer<T>`/`I*EventHandler<T>` ↔ `new T(..)` publicado | no | **soportado** |  |
| NServiceBus | C# | `IHandleMessages<T>` ↔ `Send/Publish(new T)` | soportado | **soportado** |  |
| Hangfire | C# | `BackgroundJob.Enqueue<T>(x => x.M())`, `RecurringJob.AddOrUpdate<T>` | no | **soportado** |  |
| Spring application events | Java/Kotlin | `publishEvent(new T)` → `@EventListener(T)`/`ApplicationListener<T>` | no | **soportado** |  |
| Laravel queues / events | PHP | `Job::dispatch()`/`dispatch(new Job)` → `ShouldQueue::handle` | no | **soportado** |  |
| Symfony Messenger | PHP | `$bus->dispatch(new M)` → `#[AsMessageHandler] __invoke(M $m)` | no | **soportado** |  |
| NestJS microservices / EventEmitter | TS | `emit("x")` ↔ `@OnEvent/@EventPattern/@MessagePattern` | soportado | **soportado** |  |
| Trigger.dev | TS | `task({id})` ↔ `x.trigger/triggerAndWait/batchTrigger`, `tasks.trigger("id")` | no | **soportado** |  |
| Inngest | TS | `createFunction({id}, {event})` ↔ `inngest.send({name})` | no | **soportado** |  |
| Enum-dispatched queues (Rust) | Rust | `Enum::Variante(..).spawn()` + `match cola { Enum::V => h() }` + mapeos `A::X => B::Y` + `queue:` en YAML | no | **parcial** | sólo Rust (`match`); `when`/`switch` sobre enums en otros lenguajes no |
| Laravel events / listeners | PHP | `event(new E)` → `Listeners/*::handle(E $e)` | no | **soportado** |  |
| Spring Cloud Stream | Java/Kotlin | `spring.cloud.stream.bindings.<fn>-in-0.destination` + `StreamBridge.send` | no | **soportado** |  |
| Micronaut Kafka | Java/Kotlin | `@KafkaClient` + `@Topic` → `@KafkaListener` + `@Topic` | no | **soportado** |  |
| Socket.IO | JS/TS | `socket.emit("x")` ↔ `socket.on("x")` | soportado | **soportado** |  |

### ORM y acceso a datos

| framework / librería | lenguaje | qué se reconoce | antes | después | notas |
|---|---|---|---|---|---|
| SQLAlchemy | Python | `__tablename__`, `session.query(M)`, `select(M)`, `op.create_table` | soportado | **soportado** |  |
| SQLModel | Python | `table=True`, `select(M)` | soportado | **soportado** |  |
| Django ORM | Python | `models.Model`, `M.objects`, `CreateModel`, `Meta.model` | soportado | **soportado** |  |
| Prisma | TS | `model` ↔ `prisma.m.findMany()` ↔ `CREATE TABLE` de migraciones | soportado | **soportado** |  |
| TypeORM | TS | `@Entity`, `getRepository(M)`, `Repository<M>` | soportado | **soportado** |  |
| Sequelize | JS/TS | `sequelize.define`, `M.findOne` | soportado | **soportado** |  |
| Drizzle | TS | `pgTable/mysqlTable/sqliteTable` ↔ `from(t)/insert(t)/db.query.t` | no | **soportado** |  |
| Mongoose | JS/TS | `mongoose.model(..)`, `M.find` | soportado | **soportado** |  |
| Knex | JS/TS | `createTable` ↔ `knex("t")`, `.from("t")` (también Supabase `.from`) | no | **soportado** |  |
| GORM | Go | `TableName()`, `db.Model(&M{})`, `.Table("t")` | no | **soportado** |  |
| ent | Go | `ent.Schema` ↔ `client.M.Query()/Create()` | no | **soportado** |  |
| sqlc | Go/SQL | `-- name:` ↔ `CREATE TABLE`, structs y llamadas generadas | soportado | **soportado** |  |
| Raw SQL in code | cualquiera | cadenas `SELECT/INSERT/UPDATE/DELETE/ALTER` ↔ `CREATE TABLE` (incl. renombrados) | no | **soportado** |  |
| JPA / Hibernate / Spring Data | Java/Kotlin | `@Entity/@Table`, `*Repository<E>` (extends/implements), métodos de repositorio | soportado | **soportado** |  |
| Panache (Quarkus) | Java/Kotlin | `PanacheEntity` (`E.listAll()`), `PanacheRepository<E>`, `@MongoEntity` | no | **soportado** |  |
| Exposed (Kotlin) | Kotlin | `object T : Table()`, `class E : Entity` + `EntityClass<E>(T)`, `SchemaUtils` | no | **soportado** |  |
| Room (Android) | Kotlin/Java | `@Entity(tableName)`, `@Query` SQL, `@Insert/@Update/@Delete(E)`, `@Database(entities)` | parcial | **soportado** |  |
| EF Core | C# | `DbSet<E>`, `ToTable`, `CreateTable` | soportado | **soportado** |  |
| Dapper | C# | SQL en `Query<T>("...")` | soportado | **soportado** |  |
| Eloquent (Laravel) | PHP | `extends Model`, `M::where`, `Schema::create` | soportado | **soportado** |  |
| Doctrine | PHP | `#[ORM\Entity]/#[ORM\Table]`, `getRepository(E::class)` | no | **parcial** | mapeos XML/YAML no |
| ActiveRecord | Ruby | `ApplicationRecord`, `M.all`, `create_table`, asociaciones | soportado | **soportado** |  |
| ROM (Ruby Object Mapper) | Ruby | `schema :t` en relaciones, `Repository[:t]`, `rename_table` | no | **soportado** |  |
| Ecto | Elixir | `schema "t"`, `Repo.*(M)`, `create table` | soportado | **soportado** |  |
| Diesel | Rust | `schema::t::dsl`, `t.filter()/insert_into(t)` ↔ `CREATE TABLE` | no | **parcial** | el DSL se reconoce por heurística de nombres de tabla |
| SeaORM | Rust | `#[sea_orm(table_name)]` ↔ `modulo::Entity::find()` | no | **soportado** |  |
| sqlx (Rust) | Rust | `sqlx::query!` SQL ↔ migraciones | soportado | **soportado** |  |
| Core Data / SwiftData | Swift | `@Model`, `NSManagedObject`, `FetchDescriptor<T>`, `@Query` | no | **parcial** | modelos `.xcdatamodeld` no |
| Drift / Floor (Dart) | Dart | `extends Table`, `@Entity`, `select(db.t)` | no | **soportado** |  |

### Configuración y variables de entorno

| framework / librería | lenguaje | qué se reconoce | antes | después | notas |
|---|---|---|---|---|---|
| dotenv (.env) | cualquiera | `.env`, `.env.*` versionados (también `.env.tt`), `process.env`, `os.getenv`... | no | **soportado** |  |
| pydantic Settings | Python | campos de `BaseSettings` y lecturas `settings.CAMPO` | no | **soportado** |  |
| Spring relaxed binding | Java/Kotlin | `@Value("${a.b}")` ↔ `A_B` en compose/k8s | soportado | **soportado** |  |
| MicroProfile / Quarkus config | Java/Kotlin | `@ConfigProperty(name)`, perfiles `%prod.`, `quarkus.*.env.vars.X` | no | **soportado** |  |
| .NET configuration | C# | `GetConnectionString`, `Section:Key` ↔ `Section__Key` | soportado | **soportado** |  |
| Vite / import.meta.env | JS/TS | `import.meta.env.X` ↔ `.env*` del proyecto | no | **soportado** |  |
| SvelteKit $env | JS/TS | `$env/dynamic|static/*` y `env.X` importados de módulos `env` | no | **soportado** |  |
| Go env / envconfig tags | Go | tags `env:"X"`, `os.Getenv` | soportado | **soportado** |  |
| Rails / Ruby ENV + Hanami settings | Ruby | `ENV[...]`, `setting :x` + `settings.x` | no | **soportado** |  |
| Kubernetes manifests | YAML | `env:`, ConfigMap/Secret, `configMapKeyRef` | soportado | **soportado** |  |
| Helm values | YAML | plantillas `templates/**` con `env:` | soportado | **soportado** |  |
| render.yaml | YAML | `envVars: - key:` | no | **soportado** |  |
| fly.toml | TOML | sección `[env]` | no | **soportado** |  |

### Cableado de despliegue

| framework / librería | lenguaje | qué se reconoce | antes | después | notas |
|---|---|---|---|---|---|
| docker compose depends_on / links | YAML | `depends_on`, `links`, URLs a servicios, puertos | soportado | **soportado** |  |
| compose fragments + network aliases | YAML | ficheros compose detectados por contenido (fragmentos sin `services:`), `container_name`, `hostname`, `aliases` | no | **soportado** |  |
| Kubernetes Service URLs | YAML | `host:puerto`, `*.svc` → `Service` | soportado | **soportado** |  |
| Kubernetes Ingress → Service | YAML | `backend: service: name`, selectores Service → workload, `claimName`, kustomize `resources:` | no | **soportado** | ronda 4 |
| render.yaml fromService / fromDatabase | YAML | `fromService/fromDatabase/fromGroup` → recurso | no | **soportado** |  |
| Procfile | Procfile | procesos → módulo/fichero de entrada | no | **soportado** |  |

### No cubierto (conocido)

| patrón | lenguaje | tipo |
|---|---|---|
| Bun.serve `routes: {}` / Deno Fresh | JS/TS | route |
| Symfony / Laravel rutas en YAML/XML | PHP | route |
| SignalR / gRPC-web / WebSocket por tipo de mensaje (cliente → método del hub) | C#/JS | rpc |
| Suscripciones SNS→SQS, EventBridge, colas declaradas sólo en Terraform/CloudFormation | IaC | event |
| Istio VirtualService | YAML | service |
| Terraform / Pulumi (recursos y variables) | IaC | service/env |
| Clientes generados de OpenAPI/gRPC-gateway fuera del repo (sólo `.d.ts`) | cualquiera | http |

## Ronda 4: mecanismos estructurales (independientes de la librería)

Tras la ronda 3 el examen ciego (control3) dio 26 %: los proyectos reales envuelven los frameworks en helpers propios. La ronda 4
sustituye reglas por librería por reglas por forma del código y por lo que el repo declara (`analyzer/cortex_graph/structural.py`,
mixin de `Bridges`). Cada mecanismo tiene un caso sintético en `analyzer/tests/test_bridges_structural.py`:

| mecanismo | qué se reconoce | caso |
|---|---|---|
| registro de rutas por forma | llamada con literal de ruta (`"/x"` o nombre RPC `"a.b"` en receptor tipo router) + función inline o referencia del repo; clases → métodos por verbo | `test_wrapper_registration_expands_class_handler`, `test_rpc_names_mounts_and_suffix_client` |
| montajes y prefijos | literal + router importado (también reexportado por un `index`) o variable local con rutas; `basePath`; paquetes del monorepo por `package.json` | `test_rpc_names_mounts_and_suffix_client`, `test_chained_server_routes_and_base_path` |
| contratos anotados | interfaz con `@Get` servida por su implementación (con su `@Controller`) y consumida por interfaces cliente que la extienden; prefijos heredados de la clase base | `test_annotated_contract_served_by_implementation` |
| wrappers de URL | el parámetro de una función fluye a la URL de una llamada cliente; se propaga en cadena y entre ficheros; ternarios y reasignaciones | `test_url_wrappers_across_files` |
| clientes con base desconocida | `${base}x`, `this.baseUrl + 'x'`: casan por segmentos literales y menor prefijo extra; nombres RPC con punto por sufijo único | `test_rpc_names_mounts_and_suffix_client` |
| jobs por referencia | `f.delay()`, `new XTask().schedule()`, `enqueue(f)`, `{"func": f}`, cron `{"* * * * *", Mod}`, `Enqueue(() => svc.M())` → implementación de la interfaz | `test_jobs_by_reference_and_shared_key`, `test_lambda_job_resolves_interface_implementation` |
| jobs por clave compartida | constante/literal usada en una llamada productora y en un registro con handler (`createRunner(Q, {run: f})`, `AddOrUpdate(K, ...)`↔`TriggerJob(K)`) | `test_jobs_by_reference_and_shared_key` |
| modelos declarados | `__tablename__`, `tableName`, `@Table({tableName})`, `[Table]`, `@Entity`/`@MappedEntity`, `TableName()`; usos `modulo.Modelo`, barrels, Go `new(pkg.M)` en funciones con BD; DSL ↔ `CREATE TABLE` | `test_declared_models_and_qualified_uses` |
| env definido por el repo | NOMBRE_EN_MAYÚSCULAS en código (literal, `.X`, clave `X:`) definido en `.env*`, bloques `env` de YAML/JSON, Dockerfile, shell; `{Name: "x", EnvVars("X")}` + `c.Bool("x")`; módulos `environment.*` | `test_env_names_defined_by_the_repo` |
| cableado | compose `build:`/`command:` → Dockerfile/entrypoint, ids de servicio ↔ `application.name`, manifiestos k8s/kustomize | `test_manifest_and_compose_wiring` |
| RPC por nombre | procedimientos de routers tRPC llamados por su nombre cualificado | `test_rpc_procedures_called_by_name` |

Código por librería sustituido por el mecanismo general: `api.add_resource(...)` de Flask-RESTful y las cascadas `..get("/x", h)` de
shelf_router (ambos los cubre el registro estructural); el resto de reglas se mantiene donde aporta semántica propia del framework
(verbo por defecto de `add_url_rule`, tuplas de Tornado).

## Ronda 5: idiomas transversales (`analyzer/cortex_graph/idioms.py`)

El examen ciego de la ronda 4 (control4) dio 46,6 %: Django con modelos que heredan de bases propias, señales y beat de Celery,
Diesel con `table!`, JDO, Kysely, configuración leída por envoltorios (`parseX(&c.f, EnvX)`, `__get_boolean("X")`, constantes
`ConfigKeys.X`, campos de `make_config!`), SDK y clientes OpenAPI generados, canales de plataforma Pigeon, hubs de notificación... Ninguna
de esas filas estaba en la matriz, que seguía siendo menos profunda de lo que decía. La ronda 5 añade un mixin (`Idioms` y clases
hermanas) con reglas por forma del código o de la configuración, cada una con su caso canónico y una o dos variantes en
`analyzer/tests/test_bridges_idioms.py`:

| mecanismo | qué se reconoce | caso |
|---|---|---|
| tablas por nombre literal en constructores de consultas | `selectFrom('t')`, `insertInto`, `updateTable`, `deleteFrom`, `innerJoin`, `.from('t')`, `.table('t')`, `collection('t')` con `t` declarada (sustituye a la regla `from/into/table` de JS, que tomaba `Array.from('x')`) | `test_query_builder_table_literals` |
| tablas por macro y modelos por atributo/anotación | `table! { t (id) {..} }` / `diesel::table!`, `#[diesel(table_name = t)]`, `#[table_name = "t"]`, `@PersistenceCapable(table=..)` (o sin tabla: el nombre de la clase), cualquier anotación con `table=`/`tableName=` (`@DatabaseTable`) | `test_rust_table_macro_and_attribute`, `test_annotated_table_models` |
| herencia de modelos | clases Python que derivan (en cadena, con alias de módulo) de un modelo reconocido | `test_python_model_inheritance` |
| registro de modelos en el ORM | `db.AutoMigrate(new(pkg.T), &pkg.U{})`, `Sync2`, `RegisterModel`, `CreateTable` | `test_go_server_idioms_orm_observers_and_notifiers` |
| mapas de esquema tipados | interfaz/tipo cuyos miembros son tablas declaradas (`interface DB { comments: Comments }`), también en `.d.ts` versionados | `test_typed_schema_map_models` |
| DDL en migraciones de código y renombrados por lista | ``sql`CREATE TABLE ..` ``/`op.execute("CREATE TABLE ..")` en ficheros de migración; `{ oldName: 'a', newName: 'b' }` | `test_code_migrations_with_sql_and_rename_maps` |
| plantillas de entorno | `*.conf.example`, `*.env.template`... con `CLAVE=valor` y líneas comentadas `# CLAVE=valor`; `- CLAVE` en `environment:` de compose | `test_env_templates_and_compose_passthrough` |
| envoltorios de lectura de entorno | función cuyo parámetro llega a `os.LookupEnv`/`os.getenv`/`process.env[..]`/`System.getenv`/`ENV[..]`/`env::var` (en cadena) y sus llamadas con literal o constante; la declaración de la constante también | `test_env_wrapper_functions_and_constant_names` |
| constantes con claves de configuración | referencias a `ConfigKeys.X = "a.b"` (o `const val`) cuyo valor es una clave de `application.properties`/YAML | `test_config_key_constants` |
| campos de bloques de configuración | campos `snake_case` de un fichero/macro de configuración cuyo nombre en mayúsculas está definido en un `.env*` o plantilla (`make_config!`, dataclasses/settings) | `test_config_block_fields_bound_to_env` |
| señales y observadores | `sig.connect(handler)`, `@receiver(sig)`, `notifier.OnUserDeleted(handler)` (receptor con nombre de notificador) + `sig.send()/send_robust()/emit()` | `test_signals_connect_send_and_receiver`, `test_go_server_idioms_orm_observers_and_notifiers` |
| claves cualificadas de despacho | `case Q.X:`/`job.name !== Q.X` en la entrada de un consumidor (`process`/`handle`/clase `*Processor`), decoradores `@OnJob({name: Q.X})`, `@Processor(Q.X)` + `@InjectQueue(Q.X) q` y productores `queue.add(Q.X, ..)`, `queue({name: Q.X})`, `return {name: Q.X}` | `test_qualified_key_dispatch`, `test_precision_guards` |
| jobs por referencia de clase | `new XTask()`, `X.class`, `X::class.java`, `typeof(X)` como argumento (`recurringTask(.., new XTask())`, `ctx.activity(X.class)`) con `XTask/Job/Workflow/Activity/Worker` (o base así llamada) | `test_job_classes_passed_by_reference` |
| tareas por ruta punteada | `"task": "app.tasks.f"` (beat y planificadores) hacia la tarea `f` de `app/tasks.py` | `test_dotted_task_references_in_schedules` |
| hubs de notificación en proceso | `send_x/push_x/notify/broadcast/publish/emit_x` definidos en un módulo/tipo de canal (`websocket`, `push`, `stream`, `hub`, `pubsub`...) y llamados desde otro fichero (no a través de un paquete importado) | `test_rust_notification_hub_calls`, `test_precision_guards` |
| jobs Ruby iterables y `push_bulk` | `include X::IterableJob` (o cualquier `include ..Job/..Worker`), `each_iteration`, `Worker.push_bulk(..)` | `test_rails_resource_modules_and_ruby_job_variants` |
| receptores tipados en handlers | `var.Metodo` / `var.Metodo()` resuelto por el tipo de la variable (`x := pkg.T{}`, `x, err := pkg.NewT()` con el tipo de retorno de la fábrica, `var x T`, `T x`, `x: T`) | `test_typed_receivers_chained_groups_and_verb_lists` |
| grupos encadenados y listas de verbos | `r.Group("/x").Use(mw).POST("", h)`, `Match([]string{"GET","HEAD"}, "/p", h)`, rutas relativas dentro de un grupo | `test_typed_receivers_chained_groups_and_verb_lists`, `test_go_server_idioms_orm_observers_and_notifiers` |
| routers de viewsets e `include([...])` anidados | acciones estándar por bases (`ModelViewSet`, `ReadOnlyModelViewSet`, mixins) al método o a la clase, `@action(methods, detail, url_path)`; prefijos de `include([...])` en línea | `test_django_nested_includes_and_viewset_routers` |
| `resources ..., module:` de Rails | el módulo se aplica al controlador y a las rutas anidadas | `test_rails_resource_modules_and_ruby_job_variants` |
| OpenAPI repartido y desempate | `paths: /x: $ref: "./x.yaml"` (verbos del fichero referenciado); entre métodos homónimos del `operationId`, la clase que implementa `{Tag}Api` | `test_openapi_split_specs_and_generated_clients` |
| clientes tipo fetch y SDK generados | `fetchJson("/x", {method})`, `requestX`, `httpGet` con base literal del fichero; funciones exportadas de un cliente generado llamadas desde quien las importa (paquete del monorepo o índice) | `test_generated_sdk_functions_and_their_importers` |
| clientes OpenAPI generados fuera del repo | `api.createX()` con receptor de tipo `*Api/*Client` que el repo no declara y método = `operationId` de un spec del repo (también JSON con otro nombre) | `test_openapi_split_specs_and_generated_clients` |
| clientes obtenidos de una llamada, navegación y ternarios | `api().get('/x')`, `axios.create().post(..)`, `window.location.href = url`, `window.open(url)`, `` `${b}x/${on ? 'a' : 'b'}` `` | `test_browser_clients_navigation_ternaries_and_created_instances`, `test_generated_sdk_functions_and_their_importers` |
| envoltorios con firma larga | el parámetro de una función con genéricos y parámetros en muchas líneas (`apiRequest<..>(method, url, args)`) | `test_request_helpers_with_long_signatures` |
| URLs construidas en una clase base | `this.http.post(this.getResourceUrl(null, 'x'))` con `getResourceUrl` heredado que concatena `this.resourceName` (fijado en la subclase) y sus parámetros | `test_inherited_url_builders` |
| contratos de otro lenguaje (canales de plataforma) | llamada tipada a una interfaz declarada en un lenguaje (IDL Pigeon en Dart) e implementada sólo en otro (`class X : Base(), NativeApi` en Kotlin), con métodos heredados; también instancias globales `final api = Api()` | `test_cross_language_platform_interfaces` |
| hosts por defecto y compose principal | `host: env.X \|\| 'redis'` → servicio `redis`; entre variantes del compose (`.dev`, `.prod`) se elige el principal | `test_default_hosts_resolve_to_main_compose` |

Cambios de estado en la matriz: «Django REST Framework» pasa a expandir por verbo (`GET /x` → `list` o la clase, `DELETE /x/:pk` →
`destroy` o la clase, más `@action`); el caso de `test_bridges_frameworks.py` se actualizó a esa salida. La regla anterior de JS
`.from/.into/.table('x')` queda sustituida por la de constructores de consultas.
