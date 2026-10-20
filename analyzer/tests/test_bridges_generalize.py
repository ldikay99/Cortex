from conftest import write_repo
from cortex_graph.analyze import analyze
from cortex_graph.bridges import client_path, env_key


def run(tmp_path, files):
    out = analyze(write_repo(tmp_path / 'repo', files), git=False)
    keys = {n['id']: n['key'] for n in out['nodes']}
    nodes = {n['key']: n for n in out['nodes']}
    return nodes, {(keys[e['a']], keys[e['b']], e['kind']) for e in out['edges']}


def kinds(edges, kind):
    return {(a, b) for a, b, k in edges if k == kind}


def linked(edges, kind, a, b):
    """Directly or through one endpoint/topic/variable/table node."""
    pairs = kinds(edges, kind)
    if (a, b) in pairs or (b, a) in pairs:
        return True
    near = {y for x, y in pairs if x == a} | {x for x, y in pairs if y == a}
    far = {y for x, y in pairs if x == b} | {x for x, y in pairs if y == b}
    return bool(near & far)


def test_trailing_interpolation_and_env_keys():
    assert client_path('api/v1/items/all\0') == '/api/v1/items/all'
    assert client_path('/items/\0') == '/items/:param'
    assert env_key('spring.kafka.bootstrap-servers') == env_key('SPRING_KAFKA_BOOTSTRAP-SERVERS')
    assert env_key('ConnectionStrings:db') == env_key('ConnectionStrings__db')


DECORATED = {
    'api/main.ts': """
        import { NestFactory } from '@nestjs/core';
        async function bootstrap() {
          const app = await NestFactory.create(AppModule);
          app.enableVersioning({ defaultVersion: '1', type: VersioningType.URI });
          app.setGlobalPrefix('api');
        }
    """,
    'api/items.controller.ts': """
        import { Controller, Get, Post, Version, VERSION_NEUTRAL, UseGuards } from '@nestjs/common';

        @Controller('items')
        export class ItemsController {
          @Get(':id')
          @UseGuards(AuthGuard('jwt'))
          public async getItem(@Param('id') id: string) {
            return id;
          }

          @Post()
          @Version('2')
          public async create() {}

          @Get('health')
          @Version(VERSION_NEUTRAL)
          public health() {}
        }
    """,
    'web/items.service.ts': """
        export class ItemsService {
          constructor(private http: HttpClient) {}
          public fetchItem(id: string) {
            return this.http.get<Item>(`/api/v1/items/${id}`);
          }
          public create(body) {
            return this.http.post('/api/v2/items', body);
          }
          public health() {
            return this.http.get('/api/items/health');
          }
        }
    """,
}


def test_decorator_routes_versioning_and_annotation_line(tmp_path):
    nodes, edges = run(tmp_path, DECORATED)
    http, handles = kinds(edges, 'http'), kinds(edges, 'handles')
    get = 'e:api/items.controller.ts:GET /api/v1/items/:id'
    assert nodes[get]['line'] == 5
    assert (get, 'f:api/items.controller.ts:ItemsController.getItem') in handles
    assert ('f:web/items.service.ts:ItemsService.fetchItem', get) in http
    assert ('f:web/items.service.ts:ItemsService.create', 'e:api/items.controller.ts:POST /api/v2/items') in http
    assert ('f:web/items.service.ts:ItemsService.health', 'e:api/items.controller.ts:GET /api/items/health') in http


PRISMA = {
    'prisma/schema.prisma': 'model Order {\n  id String @id\n}\n\nmodel SymbolProfile {\n  id String @id\n}\n',
    'prisma/migrations/1_init/migration.sql': 'CREATE TABLE "Order" (\n  "id" TEXT NOT NULL\n);\n\nCREATE TABLE "SymbolProfile" ("id" TEXT);\n',
    'api/order.service.ts': """
        export class OrderService {
          constructor(private readonly prismaService: PrismaService) {}
          public async orders() {
            return this.prismaService.order.findMany({ include: { symbolProfile: true } });
          }
          public async profiles(tx) {
            return tx.symbolProfile.deleteMany({});
          }
        }
    """,
}


def test_prisma_models_join_sql_migrations_and_client_uses(tmp_path):
    nodes, edges = run(tmp_path, PRISMA)
    data = kinds(edges, 'data')
    order = 'c:prisma/schema.prisma:Order'
    assert (order, 'c:prisma/migrations/1_init/migration.sql:Order') in data
    assert ('f:api/order.service.ts:OrderService.orders', order) in data
    assert ('f:api/order.service.ts:OrderService.profiles', 'c:prisma/schema.prisma:SymbolProfile') in data


JOBS = {
    'libs/config.ts': "export const GATHER_JOB_NAME = 'GATHER';\nexport const UNUSED_JOB = 'NOPE';\n",
    'api/events/changed.event.ts': """
        export class ChangedEvent {
          public static getName() { return 'thing.changed'; }
        }
    """,
    'api/queue/gather.processor.ts': """
        import { Process, Processor } from '@nestjs/bull';
        import { GATHER_JOB_NAME } from '../../libs/config';

        @Processor('gathering')
        export class GatherProcessor {
          @Process({ concurrency: 2, name: GATHER_JOB_NAME })
          public async gather(job) {
            return job;
          }
        }
    """,
    'api/events/changed.listener.ts': """
        import { OnEvent } from '@nestjs/event-emitter';
        export class ChangedListener {
          @OnEvent(ChangedEvent.getName())
          handleChanged(event) {}
        }
    """,
    'api/things.service.ts': """
        import { GATHER_JOB_NAME } from '../libs/config';
        export class ThingsService {
          public schedule() {
            this.gatheringService.addJob({ name: GATHER_JOB_NAME, data: {} });
          }
          public change() {
            this.eventEmitter.emit(ChangedEvent.getName(), new ChangedEvent());
          }
          public direct() {
            return this.gatherQueue.add(GATHER_JOB_NAME, {});
          }
        }
    """,
}


def test_decorator_consumers_pair_with_producers_by_key(tmp_path):
    nodes, edges = run(tmp_path, JOBS)
    gather = 'f:api/queue/gather.processor.ts:GatherProcessor.gather'
    assert linked(edges, 'event', 'f:api/things.service.ts:ThingsService.schedule', gather)
    assert linked(edges, 'event', 'f:api/things.service.ts:ThingsService.direct', gather)
    assert linked(edges, 'event', 'f:api/things.service.ts:ThingsService.change',
                  'f:api/events/changed.listener.ts:ChangedListener.handleChanged')
    assert 't:NOPE' not in nodes and 't:GATHER' in nodes
    assert nodes['t:GATHER']['file'] == 'api/queue/gather.processor.ts'


BROKER = {
    'api/index.js': """
        const TASKS_QUEUE = 'tasks';
        const RESULTS_QUEUE = 'results';
        async function consumeResults() {
          await channel.consume(RESULTS_QUEUE, (msg) => { console.log(msg); });
        }
        app.post('/tasks', (req, res) => {
          channel.sendToQueue(TASKS_QUEUE, Buffer.from('x'));
        });
    """,
    'worker/main.py': """
        TASKS_QUEUE = 'tasks'
        RESULTS_QUEUE = 'results'


        async def on_message(message):
            await channel.default_exchange.publish(Message(body=b'x'), routing_key=RESULTS_QUEUE)


        async def main():
            queue = await channel.declare_queue(TASKS_QUEUE, durable=True)
            await queue.consume(lambda msg: on_message(msg))
    """,
    'worker2/Program.cs': """
        public class Worker {
            private const string TasksQueue = "tasks";
            private const string ResultsQueue = "results";
            public async Task Run() {
                await channel.BasicConsumeAsync(queue: TasksQueue, autoAck: false, consumer: consumer);
                await channel.BasicPublishAsync(exchange: "", routingKey: ResultsQueue, body: body);
            }
        }
    """,
}


def test_broker_calls_pair_queues_across_languages(tmp_path):
    nodes, edges = run(tmp_path, BROKER)
    assert linked(edges, 'event', 'm:api/index.js', 'f:worker/main.py:on_message')
    assert linked(edges, 'event', 'm:api/index.js', 'f:worker2/Program.cs:Worker.Run')
    assert linked(edges, 'event', 'f:worker/main.py:on_message', 'f:api/index.js:consumeResults')
    assert linked(edges, 'event', 'f:worker2/Program.cs:Worker.Run', 'f:api/index.js:consumeResults')


DART = {
    'server/routes/api/v1/users/[id]/index.dart': """
        import 'package:dart_frog/dart_frog.dart';

        Future<Response> onRequest(RequestContext context, String id) async {
          switch (context.request.method) {
            case HttpMethod.get:
              return _get(context, id);
            case HttpMethod.put:
              return _update(context, id);
            case HttpMethod.delete:
            case HttpMethod.post:
              return Response(statusCode: HttpStatus.methodNotAllowed);
          }
        }

        Future<Response> _get(RequestContext context, String id) async {
          final database = context.read<Database>();
          final user = await database.users.queryUser(int.parse(id));
          return Response.json(body: user);
        }

        Future<Response> _update(RequestContext context, String id) async {
          return Response();
        }
    """,
    'server/db/user.dart': "part 'user.schema.dart';\n\n@Model()\nabstract class User {\n  int get id;\n}\n",
    'server/db/user.schema.dart': """
        part of 'user.dart';

        class _UserRepository extends BaseRepository {
          _UserRepository(super.db) : super(tableName: 'users', keyName: 'id');
        }
    """,
    'client/lib/users.dart': """
        class UsersProvider {
          static Future<User> fetch(Map<String, dynamic> body) async {
            final resp = await Api.ins.get('/v1/users/${body['id']}');
            return User.fromJson(resp.data);
          }
          static Future<void> update(Map<String, dynamic> body) async {
            await Api.ins.put('/v1/users/${body['id']}', data: body);
          }
        }
    """,
}


def test_file_routes_dart_clients_and_annotated_models(tmp_path):
    nodes, edges = run(tmp_path, DART)
    handles, http, data = kinds(edges, 'handles'), kinds(edges, 'http'), kinds(edges, 'data')
    route = 'server/routes/api/v1/users/[id]/index.dart'
    get, put = f'e:{route}:GET /api/v1/users/:id', f'e:{route}:PUT /api/v1/users/:id'
    assert (get, f'f:{route}:_get') in handles and (put, f'f:{route}:_update') in handles
    assert f'e:{route}:DELETE /api/v1/users/:id' not in nodes
    provider = 'f:client/lib/users.dart:UsersProvider'
    assert (f'{provider}.fetch', get) in http and (f'{provider}.update', put) in http
    model = 'c:server/db/user.dart:User'
    assert (model, 'c:server/db/user.schema.dart:users') in data
    assert any(a.split(':', 2)[1] == route and b == model for a, b in data)


SQLC = {
    'db/migrations/1_init.up.sql': 'CREATE SCHEMA "shop";\nCREATE TABLE\n    "shop".orders (\n        id uuid NOT NULL\n    );\n',
    'internal/infras/postgresql/query/query.sql': '-- name: GetAll :many\nSELECT o.id\nFROM "shop".orders o;\n\n-- name: CreateOrder :one\nINSERT INTO\n  "shop".orders (id)\nVALUES ($1);\n',
    'internal/infras/postgresql/models.go': '// Code generated by sqlc. DO NOT EDIT.\n\npackage postgresql\n\ntype ShopOrder struct {\n\tID string `json:"id"`\n}\n',
    'internal/infras/repo/orders.go': """
        package repo

        import "example.com/shop/internal/infras/postgresql"

        func (r *orderRepo) GetAll(ctx context.Context) error {
            querier := postgresql.New(r.db)
            _, err := querier.GetAll(ctx)
            return err
        }
    """,
    'seed/V2__seed.sql': "INSERT INTO shop.orders (id) VALUES ('a');\n",
}


def test_sqlc_queries_generated_structs_and_seed_migrations(tmp_path):
    nodes, edges = run(tmp_path, SQLC)
    data = kinds(edges, 'data')
    table = 'c:db/migrations/1_init.up.sql:orders'
    assert table in nodes
    assert ('f:internal/infras/postgresql/query/query.sql:GetAll', table) in data
    assert ('f:internal/infras/postgresql/query/query.sql:CreateOrder', table) in data
    assert ('c:internal/infras/postgresql/models.go:ShopOrder', table) in data
    assert ('f:internal/infras/repo/orders.go:orderRepo.GetAll', table) in data
    assert ('m:seed/V2__seed.sql', table) in data


GRPC = {
    'proto/shop.proto': """
        syntax = "proto3";
        package shop;
        import "google/api/annotations.proto";
        service ShopService {
          rpc ListItems(ListRequest) returns (ListReply) {
            option (google.api.http) = {
              get: "/v1/items"
            };
          }
        }
    """,
    'internal/server.go': """
        package internal

        type shopServer struct {
            gen.UnimplementedShopServiceServer
        }

        func NewShopServer(grpcServer *grpc.Server) gen.ShopServiceServer {
            svc := shopServer{}
            gen.RegisterShopServiceServer(grpcServer, &svc)
            return &svc
        }

        func (s *shopServer) ListItems(ctx context.Context, r *gen.ListRequest) (*gen.ListReply, error) {
            return nil, nil
        }
    """,
    'cmd/proxy/main.go': """
        package main

        func newGateway(ctx context.Context, cfg Config) error {
            mux := runtime.NewServeMux()
            return gen.RegisterShopServiceHandlerFromEndpoint(ctx, mux, cfg.Endpoint, nil)
        }
    """,
    'web/app.js': """
        async function load(base) {
          const response = await fetch(`${base}/v1/items`);
          return response.json();
        }
    """,
    'cmd/server/config.go': 'package main\n\ntype Config struct {\n\tEndpoint string `env-required:"true" env:"SHOP_ENDPOINT"`\n}\n',
    'docker-compose.yml': 'services:\n  proxy:\n    image: x\n    environment:\n      SHOP_ENDPOINT: shop:5000\n  shop:\n    image: y\n',
}


def test_grpc_registration_gateway_http_annotations_and_env_tags(tmp_path):
    nodes, edges = run(tmp_path, GRPC)
    rpc, handles, http, env = kinds(edges, 'rpc'), kinds(edges, 'handles'), kinds(edges, 'http'), kinds(edges, 'env')
    impl = 'f:internal/server.go:shopServer.ListItems'
    endpoint = 'e:proto/shop.proto:RPC shop.ShopService/ListItems'
    assert ('f:internal/server.go:NewShopServer', endpoint) in rpc
    assert ('f:cmd/proxy/main.go:newGateway', endpoint) in rpc
    route = 'e:proto/shop.proto:GET /v1/items'
    assert (route, impl) in handles
    assert ('f:web/app.js:load', route) in http
    assert ('c:cmd/server/config.go:Config', 'v:SHOP_ENDPOINT') in env and ('m:docker-compose.yml', 'v:SHOP_ENDPOINT') in env


SPRING = {
    'gateway/src/main/resources/application.properties': 'spring.application.name=gateway\nserver.port=9000\nitems.service.url=http://localhost:8082\nloki.url=http://localhost:3100\n',
    'gateway/src/main/resources/logback-spring.xml': '<configuration>\n  <springProperty scope="context" name="lokiUrl" source="loki.url"/>\n</configuration>\n',
    'gateway/src/main/java/gw/Routes.java': """
        package gw;
        @Configuration
        public class Routes {
            @Value("${items.service.url}")
            private String itemsServiceUrl;

            @Bean
            public RouterFunction<ServerResponse> itemsRoute() {
                return GatewayRouterFunctions.route("items")
                        .route(RequestPredicates.path("/api/items"), HandlerFunctions.http(itemsServiceUrl))
                        .build();
            }

            @Bean
            public RouterFunction<ServerResponse> fallbackRoute() {
                return route("fallback").GET("/fallbackRoute", request -> ServerResponse.ok().build()).build();
            }
        }
    """,
    'items/src/main/resources/application.properties': 'spring.application.name=items\nserver.port=8082\nspring.datasource.url=jdbc:mysql://localhost:3306/items\n',
    'items/src/main/java/items/ItemController.java': """
        package items;
        @RestController
        @RequestMapping("/api/items")
        public class ItemController {
            @GetMapping
            public List<Item> all() { return null; }
        }
    """,
    'orders/src/main/resources/application.properties': 'spring.application.name=orders\nserver.port=8081\n',
    'orders/src/main/java/orders/ItemsClient.java': """
        package orders;
        public interface ItemsClient {
            @GetExchange("/api/items")
            List<Item> all();
        }
    """,
    'docker-compose.yml': 'services:\n  mysql:\n    image: mysql\n    ports:\n      - "3306:3306"\n',
    'k8s/items.yml': """
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: items
        spec:
          template:
            spec:
              containers:
                - name: items
                  env:
                    - name: SPRING_DATASOURCE_URL
                      valueFrom:
                        configMapKeyRef:
                          key: SPRING_DATASOURCE_URL
                          name: items-config
        ---
        apiVersion: v1
        kind: ConfigMap
        metadata:
          name: items-config
        data:
          SPRING_DATASOURCE_URL: "jdbc:mysql://mysql.default.svc.cluster.local:3306/items"
        ---
        apiVersion: v1
        kind: Service
        metadata:
          name: mysql
    """,
}


def test_spring_relaxed_binding_gateway_ports_and_declarative_clients(tmp_path):
    nodes, edges = run(tmp_path, SPRING)
    depends, handles, http = kinds(edges, 'depends'), kinds(edges, 'handles'), kinds(edges, 'http')
    gw_props = 'm:gateway/src/main/resources/application.properties'
    items_props = 'm:items/src/main/resources/application.properties'
    assert linked(edges, 'env', 'c:gateway/src/main/java/gw/Routes.java:Routes', gw_props)
    assert linked(edges, 'env', 'm:gateway/src/main/resources/logback-spring.xml', gw_props)
    assert linked(edges, 'env', items_props, 'c:k8s/items.yml:Deployment/items')
    assert linked(edges, 'env', 'c:k8s/items.yml:Deployment/items', 'c:k8s/items.yml:ConfigMap/items-config')
    assert ('f:gateway/src/main/java/gw/Routes.java:Routes.itemsRoute', items_props) in depends
    assert (gw_props, items_props) in depends
    assert (items_props, 'c:docker-compose.yml:mysql') in depends
    assert ('c:k8s/items.yml:Deployment/items', 'c:k8s/items.yml:Service/mysql') in depends
    proxy = next(n for n in nodes if n.startswith('e:gateway/src/main/java/gw/Routes.java:ANY /api/items'))
    assert (proxy, 'c:items/src/main/java/items/ItemController.java:ItemController') in handles
    assert ('e:gateway/src/main/java/gw/Routes.java:GET /fallbackRoute', 'f:gateway/src/main/java/gw/Routes.java:Routes.fallbackRoute') in handles
    assert ('f:orders/src/main/java/orders/ItemsClient.java:ItemsClient.all', 'e:items/src/main/java/items/ItemController.java:GET /api/items') in http


ASPIRE = {
    'AppHost/AppHost.cs': """
        var builder = DistributedApplication.CreateBuilder(args);

        var postgres = builder.AddPostgres("postgres");
        var db = postgres.AddDatabase("catalogdb");

        var api = builder.AddProject<Projects.Api>("catalogapi")
            .WithReference(db)
            .WaitFor(db);

        builder.AddJavaScriptApp("web", "../Web")
            .WithReference(api)
            .WithHttpEndpoint(env: "PORT");

        builder.Build().Run();
    """,
    'Api/Program.cs': """
        var builder = WebApplication.CreateBuilder(args);
        builder.AddNpgsqlDbContext<CatalogDbContext>("catalogdb");
        var app = builder.Build();
        app.MapCatalogApi();
        app.Run();
    """,
    'Api/CatalogApi.cs': """
        public static class CatalogApi
        {
            public static RouteGroupBuilder MapCatalogApi(this IEndpointRouteBuilder routes)
            {
                var group = routes.MapGroup("/api/v1/catalog");
                group.MapGet("items", () => Results.Ok());
                return group;
            }
        }
    """,
    'Web/proxy.conf.js': """
        module.exports = {
          "/api": { target: process.env["services__catalogapi__https__0"] },
        };
        const port = process.env.PORT;
    """,
    'Front/Program.cs': """
        var builder = WebApplication.CreateBuilder(args);
        builder.Services.AddHttpServiceReference<CatalogClient>("https+http://catalogapi");
    """,
    'Front/CatalogClient.cs': """
        public class CatalogClient(HttpClient client)
        {
            public Task<Page?> GetItemsAsync(int? before)
            {
                var query = before is null ? "" : $"?before={before}";
                return client.GetFromJsonAsync<Page>($"api/v1/catalog/items{query}");
            }
        }
    """,
}


def test_orchestrator_resources_wiring_env_injection_and_mounts(tmp_path):
    nodes, edges = run(tmp_path, ASPIRE)
    depends, handles, http = kinds(edges, 'depends'), kinds(edges, 'handles'), kinds(edges, 'http')
    host = 'AppHost/AppHost.cs'
    api, db, web = f'c:{host}:catalogapi', f'c:{host}:catalogdb', f'c:{host}:web'
    assert (api, db) in depends and (web, api) in depends
    assert linked(edges, 'env', 'm:Web/proxy.conf.js', f'm:{host}')
    assert linked(edges, 'env', 'm:Api/Program.cs', f'm:{host}')
    assert ('m:Front/Program.cs', api) in depends
    assert ('m:Api/Program.cs', 'f:Api/CatalogApi.cs:CatalogApi.MapCatalogApi') in handles
    assert ('f:Front/CatalogClient.cs:CatalogClient.GetItemsAsync', 'e:Api/CatalogApi.cs:GET /api/v1/catalog/items') in http


DJANGO = {
    'backend/backend/urls.py': """
        from django.conf.urls import url, include

        urlpatterns = [
            url(r'^api/v1/', include('posts.urls', namespace='posts')),
        ]
    """,
    'backend/posts/urls.py': """
        from django.conf.urls import url
        from .views import PostList, TagDetail
        from .feeds import MainFeed

        urlpatterns = [
            url(r'^tag/(?P<tag>[^\\.]+)/$', PostList.as_view()),
            url(r'tag/(?P<slug>[^\\.]+)/$', TagDetail.as_view()),
            url(r'^feed/rss$', MainFeed()),
        ]
    """,
    'backend/posts/views.py': 'class PostList(ListAPIView):\n    pass\n\n\nclass TagDetail(RetrieveAPIView):\n    pass\n',
    'backend/posts/feeds.py': 'class MainFeed(Feed):\n    pass\n',
    'backend/posts/models.py': 'from django.db import models\n\n\nclass Post(models.Model):\n    title = models.CharField()\n',
    'backend/posts/serializers.py': 'from .models import Post\n\n\nclass PostSerializer(ModelSerializer):\n    class Meta:\n        model = Post\n',
    'backend/posts/migrations/0001_initial.py': """
        class Migration(migrations.Migration):
            operations = [
                migrations.CreateModel(
                    name='Post',
                    fields=[],
                ),
            ]
    """,
    'backend/backend/settings.py': "DATABASES = {\n    'default': {\n        'HOST': 'postgres',\n    }\n}\n",
    'backend/config/env': 'SECRET_KEY=x\n',
    'docker-compose.yml': 'services:\n  postgres:\n    image: postgres\n    env_file: backend/config/env\n  web:\n    image: x\n    links:\n      - postgres\n',
    'docker-compose-dev.yml': 'services:\n  postgres:\n    image: postgres\n',
    'frontend/src/actions.js': """
        import axios from 'axios';
        export const ROOT_URL = 'http://api.' + host + '/api/v1';
        export function fetchByTag(tag) {
          const url = `${ROOT_URL}/tag/${tag}/`;
          return axios.get(url);
        }
    """,
}


def test_django_mounts_migrations_serializers_and_compose_wiring(tmp_path):
    nodes, edges = run(tmp_path, DJANGO)
    handles, data, depends, http = kinds(edges, 'handles'), kinds(edges, 'data'), kinds(edges, 'depends'), kinds(edges, 'http')
    assert ('m:backend/backend/urls.py', 'm:backend/posts/urls.py') in handles
    assert ('e:backend/posts/urls.py:ANY /api/v1/feed/rss', 'c:backend/posts/feeds.py:MainFeed') in handles
    model = 'c:backend/posts/models.py:Post'
    assert (model, 'c:backend/posts/migrations/0001_initial.py:Post') in data
    assert {('c:backend/posts/serializers.py:PostSerializer', model), ('c:backend/posts/serializers.py:PostSerializer.Meta', model)} & data
    assert ('m:backend/backend/settings.py', 'c:docker-compose.yml:postgres') in depends
    assert ('c:docker-compose.yml:postgres', 'm:backend/config/env') in depends
    assert ('c:docker-compose.yml:web', 'c:docker-compose.yml:postgres') in depends
    assert ('f:frontend/src/actions.js:fetchByTag', 'e:backend/posts/urls.py:ANY /api/v1/tag/:tag') in http


ENTITIES = {
    'Db/CatalogItem.cs': 'public class CatalogItem { public int Id { get; set; } }\n',
    'Db/CatalogDbContext.cs': """
        public class CatalogDbContext : DbContext
        {
            public DbSet<CatalogItem> CatalogItems => Set<CatalogItem>();
            protected override void OnModelCreating(ModelBuilder builder)
            {
                DefineItem(builder.Entity<CatalogItem>());
            }
            private static void DefineItem(EntityTypeBuilder<CatalogItem> builder)
            {
                builder.ToTable("Catalog");
            }
        }
    """,
    'Db/Migrations/1_Initial.cs': """
        public partial class Initial : Migration
        {
            protected override void Up(MigrationBuilder migrationBuilder)
            {
                migrationBuilder.CreateTable(
                    name: "Catalog",
                    columns: table => new { Id = table.Column<int>() });
            }
        }
    """,
    'product/src/main/java/p/Product.java': '@Document(value = "product")\n@Data\npublic class Product {\n    private String id;\n}\n',
    'product/src/main/java/p/ProductRepository.java': 'public interface ProductRepository extends MongoRepository<Product, String> {\n}\n',
    'product/src/main/java/p/ProductService.java': """
        public class ProductService {
            private final ProductRepository productRepository;
            public List<Product> all() {
                return productRepository.findAll();
            }
        }
    """,
}


def test_ef_migrations_table_mapping_and_document_entities(tmp_path):
    nodes, edges = run(tmp_path, ENTITIES)
    data = kinds(edges, 'data')
    table = 'c:Db/Migrations/1_Initial.cs:Catalog'
    assert ('c:Db/CatalogItem.cs:CatalogItem', table) in data
    assert ('f:Db/CatalogDbContext.cs:CatalogDbContext.DefineItem', table) in data
    product = 'c:product/src/main/java/p/Product.java:Product'
    assert ('c:product/src/main/java/p/ProductRepository.java:ProductRepository', product) in data
    assert ('f:product/src/main/java/p/ProductService.java:ProductService.all', product) in data


GENERIC_CLIENTS = {
    'svc-a/server.js': "const express = require('express');\nconst app = express();\napp.get('/api/report', (req, res) => res.send('a'));\n",
    'svc-b/server.js': "const express = require('express');\nconst app = express();\napp.get('/api/report', (req, res) => res.send('b'));\n",
    'svc-a/web/report.js': "export function loadReport() {\n  return fetch('api/report');\n}\n",
    'mobile/lib/report.dart': """
        class ReportRepo {
          Future<void> load() async {
            await gateway.get('/api/report');
          }
        }
    """,
    'tools/cache.ts': "export function read(store) {\n  return store.cache.get('/api/report');\n}\n",
}


def test_generic_clients_and_monorepo_tie_break(tmp_path):
    nodes, edges = run(tmp_path, GENERIC_CLIENTS)
    http = kinds(edges, 'http')
    assert ('f:svc-a/web/report.js:loadReport', 'e:svc-a/server.js:GET /api/report') in http
    assert not any(a.startswith('f:tools/cache.ts') for a, b in http)


BASED = {
    'api/app.py': "from fastapi import FastAPI\napp = FastAPI()\n\n\n@app.get('/api/orders')\ndef orders():\n    return []\n",
    'web/orders.ts': """
        export class OrdersService {
          constructor(private http: HttpClient, private cfg: Config) {}
          list() { return this.http.get(`${this.cfg.apiUrl}/orders`); }
          other() { return this.http.get('/orders'); }
        }
    """,
    'Svc/Startup.cs': """
        public class Startup {
            public void Configure(IConfiguration configuration) {
                var cs = configuration["Database:Main"];
            }
        }
    """,
    'docker-compose.yml': 'services:\n  svc:\n    image: x\n    environment:\n      Database__Main: Host=db\n',
}


def test_unknown_base_urls_and_hierarchical_config_keys(tmp_path):
    nodes, edges = run(tmp_path, BASED)
    http = kinds(edges, 'http')
    assert ('f:web/orders.ts:OrdersService.list', 'e:api/app.py:GET /api/orders') in http
    assert not any(a == 'f:web/orders.ts:OrdersService.other' for a, b in http)
    assert linked(edges, 'env', 'f:Svc/Startup.cs:Startup.Configure', 'm:docker-compose.yml')
