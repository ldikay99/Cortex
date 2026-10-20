from conftest import write_repo
from cortex_graph.analyze import analyze
from cortex_graph.bridges import client_path, interpolated, norm_path


def run(tmp_path, files):
    out = analyze(write_repo(tmp_path / 'repo', files), git=False)
    keys = {n['id']: n['key'] for n in out['nodes']}
    nodes = {n['key']: n for n in out['nodes']}
    return nodes, {(keys[e['a']], keys[e['b']], e['kind']) for e in out['edges']}


def kinds(edges, kind):
    return {(a, b) for a, b, k in edges if k == kind}


def test_interpolation_and_optional_params():
    assert interpolated('songs/${id}/x${q ? `?a=${q}` : ""}') == 'songs/\0/x?'
    assert interpolated('browse/folders${id ? ') == 'browse/folders'
    assert norm_path('genres/{genre?}/songs') == '/genres/:genre/songs'
    assert client_path('podcasts/\0/episodes?') == '/podcasts/:param/episodes'


LARAVEL_ALIASES = {
    'routes/api.base.php': """
        <?php
        use App\\Http\\Controllers\\API\\Auth\\Passkey\\LoginController as PasskeyLoginController;
        use App\\Http\\Controllers\\API\\LoginController;
        use App\\Http\\Controllers\\API\\FolderController;
        use Illuminate\\Support\\Facades\\Route;

        Route::prefix('api')->group(static function (): void {
            Route::middleware('throttle')->group(static function (): void {
                Route::post('me', LoginController::class);
                Route::post('me/passkey-login', PasskeyLoginController::class);
                Route::group(['prefix' => 'radio'], static function (): void {
                    Route::get('stations', LoginController::class);
                });
            });
            Route::apiResource('me/passkeys', FolderController::class)->only(['destroy']);
            Route::delete('folders/{folder}/items', [
                FolderController::class,
                'destroy',
            ]);
        });
    """,
    'app/Http/Controllers/API/LoginController.php': """
        <?php
        namespace App\\Http\\Controllers\\API;
        class LoginController { public function __invoke() {} }
    """,
    'app/Http/Controllers/API/Auth/Passkey/LoginController.php': """
        <?php
        namespace App\\Http\\Controllers\\API\\Auth\\Passkey;
        class LoginController { public function __invoke() {} }
    """,
    'app/Http/Controllers/API/FolderController.php': """
        <?php
        namespace App\\Http\\Controllers\\API;
        class FolderController { public function destroy() {} }
    """,
}


def test_laravel_use_aliases_groups_and_multiline_actions(tmp_path):
    nodes, edges = run(tmp_path, LARAVEL_ALIASES)
    handles = kinds(edges, 'handles')
    plain = 'f:app/Http/Controllers/API/LoginController.php:LoginController.__invoke'
    passkey = 'f:app/Http/Controllers/API/Auth/Passkey/LoginController.php:LoginController.__invoke'
    folder = 'f:app/Http/Controllers/API/FolderController.php:FolderController.destroy'
    assert ('e:routes/api.base.php:POST /api/me', plain) in handles
    assert ('e:routes/api.base.php:POST /api/me/passkey-login', passkey) in handles
    assert ('e:routes/api.base.php:GET /api/radio/stations', plain) in handles
    assert ('e:routes/api.base.php:DELETE /api/me/passkeys/:passkey', folder) in handles
    assert ('e:routes/api.base.php:DELETE /api/folders/:folder/items', folder) in handles


JS_WRAPPER = {
    'src/services/http.ts': """
        import ky from 'ky'
        class Http {
          client = ky.create({ prefix: `${window.BASE_URL}api` })
          get silently () { return this }
          get withRetries () { return this }
          get (url: string) { return this.client.get(url) }
          post (url: string, data: any) { return this.client.post(url, { json: data }) }
        }
        export const http = new Http()
    """,
    'src/stores/userStore.ts': """
        import { http } from '@/services/http'

        export async function login (email: string) {
          return http.post('me', { email })
        }

        export async function sync (ids: string[]) {
          return http.silently.withRetries.post('songs/by-ids', { ids })
        }

        export async function folders (id?: string) {
          return http.get(`browse/folders${id ? `?folder=${id}` : ''}`)
        }
    """,
    'server/app.js': """
        const express = require('express')
        const app = express()
        function login (req, res) {}
        function byIds (req, res) {}
        function browse (req, res) {}
        app.post('/api/me', login)
        app.post('/api/songs/by-ids', byIds)
        app.get('/api/browse/folders', browse)
    """,
}


def test_js_wrapper_base_url_and_chained_receivers(tmp_path):
    nodes, edges = run(tmp_path, JS_WRAPPER)
    http = kinds(edges, 'http')
    assert ('f:src/stores/userStore.ts:login', 'e:server/app.js:POST /api/me') in http
    assert ('f:src/stores/userStore.ts:sync', 'e:server/app.js:POST /api/songs/by-ids') in http
    assert ('f:src/stores/userStore.ts:folders', 'e:server/app.js:GET /api/browse/folders') in http


SDK_AND_MOUNTS = {
    'backend/app/api/main.py': """
        from fastapi import APIRouter
        from app.api.routes import items

        api_router = APIRouter()
        api_router.include_router(items.router)
    """,
    'backend/app/api/routes/items.py': """
        from fastapi import APIRouter

        router = APIRouter(prefix="/items")


        @router.put("/{id}")
        def update_item(id: int):
            return id
    """,
    'frontend/src/client/sdk.gen.ts': """
        // This file is auto-generated by @hey-api/openapi-ts
        export class ItemsService {
            public static updateItem(options: any) {
                return (options.client ?? client).put({
                    responseType: 'json',
                    url: '/api/v1/items/{id}',
                    ...options
                });
            }
        }
    """,
    'frontend/src/components/EditItem.tsx': """
        import { ItemsService } from '../client/sdk.gen'

        export function EditItem({ item }: any) {
            return ItemsService.updateItem({ path: { id: item.id } })
        }
    """,
}


def test_generated_sdk_clients_and_router_mounts(tmp_path):
    nodes, edges = run(tmp_path, SDK_AND_MOUNTS)
    http, handles = kinds(edges, 'http'), kinds(edges, 'handles')
    ep = 'e:backend/app/api/routes/items.py:PUT /items/:id'
    assert ('f:frontend/src/client/sdk.gen.ts:ItemsService.updateItem', ep) in http
    assert ('f:frontend/src/components/EditItem.tsx:EditItem', ep) in http
    assert ('m:backend/app/api/main.py', 'm:backend/app/api/routes/items.py') in handles


RUST_AXUM = {
    'src/http/mod.rs': """
        mod users;
        fn api_router() -> Router {
            users::router()
                .merge(profiles::router())
        }
    """,
    'src/http/users.rs': """
        pub fn router() -> Router {
            Router::new().route("/api/users", post(create_user))
        }

        async fn create_user(ctx: Extension<ApiContext>) -> Result<()> {
            let id = sqlx::query_scalar!(
                r#"insert into "user" (username) values ($1) returning user_id"#,
                name
            );
            sqlx::query!(
                "delete from follow where a = $1 \\
                 and b = $2",
                x
            );
            Ok(())
        }
    """,
    'src/http/profiles.rs': """
        pub fn router() -> Router {
            Router::new()
        }
    """,
    'migrations/1_user.sql': """
        create table "user" (user_id uuid primary key, username text);
        create table follow (a uuid, b uuid);
    """,
}


def test_axum_merges_and_sqlx_raw_strings(tmp_path):
    nodes, edges = run(tmp_path, RUST_AXUM)
    handles, data = kinds(edges, 'handles'), kinds(edges, 'data')
    assert ('f:src/http/mod.rs:api_router', 'f:src/http/users.rs:router') in handles
    assert ('f:src/http/mod.rs:api_router', 'f:src/http/profiles.rs:router') in handles
    assert ('f:src/http/users.rs:create_user', 'c:migrations/1_user.sql:user') in data
    assert ('f:src/http/users.rs:create_user', 'c:migrations/1_user.sql:follow') in data


ORMS = {
    'backend/models.py': """
        from sqlmodel import SQLModel, Field


        class User(SQLModel, table=True):
            id: int = Field(primary_key=True)
    """,
    'backend/routes.py': """
        from backend.models import User


        def read_user(session, user_id):
            return session.get(User, user_id)


        def annotate(user: User) -> User:
            return user
    """,
    'backend/alembic/versions/001_init.py': """
        from alembic import op


        def upgrade():
            op.create_table('user')
    """,
    'app/models/article.rb': """
        class Article < ApplicationRecord
          has_many :comments
        end
    """,
    'app/models/comment.rb': """
        class Comment < ApplicationRecord
        end
    """,
    'app/controllers/articles_controller.rb': """
        class ArticlesController < ApplicationController
          def index
            @articles = Article.all
          end

          def comments
            @article.comments.order(:id)
          end
        end
    """,
    'db/schema.rb': """
        ActiveRecord::Schema.define(version: 1) do
          create_table "articles", force: :cascade do |t|
          end
        end
    """,
    'lib/blog/article.ex': """
        defmodule Blog.Article do
          use Ecto.Schema
          schema "articles" do
            field :title, :string
          end
        end
    """,
    'lib/blog/blog.ex': """
        defmodule Blog do
          alias Blog.Article

          def list_articles do
            Article |> Repo.all()
          end

          def delete_article(article) do
            Repo.delete(article)
          end
        end
    """,
    'priv/repo/migrations/1_create_articles.exs': """
        defmodule Repo.Migrations.CreateArticles do
          def change do
            create table(:articles) do
            end
          end
        end
    """,
    'server/models/productModel.js': """
        import mongoose from 'mongoose'
        const productSchema = mongoose.Schema({ name: String })
        const Product = mongoose.model('Product', productSchema)
        export default Product
    """,
    'server/controllers/productController.js': """
        import Product from '../models/productModel.js'
        export async function getProducts(req, res) {
          res.json(await Product.find({}))
        }
    """,
    'web/src/Product.js': """
        import Product from './ProductCard'
        export function show() { return Product.render() }
    """,
}


def test_orm_models_tables_and_uses(tmp_path):
    nodes, edges = run(tmp_path, ORMS)
    data = kinds(edges, 'data')
    user = 'c:backend/models.py:User'
    assert nodes[user]['table'] == 'user'
    assert ('f:backend/routes.py:read_user', user) in data
    assert ('f:backend/routes.py:annotate', user) not in data
    assert (user, 'c:backend/alembic/versions/001_init.py:user') in data
    article = 'c:app/models/article.rb:Article'
    assert ('f:app/controllers/articles_controller.rb:ArticlesController.index', article) in data
    assert ('f:app/controllers/articles_controller.rb:ArticlesController.comments', 'c:app/models/comment.rb:Comment') in data
    assert (article, 'c:db/schema.rb:articles') in data
    ecto = 'c:lib/blog/article.ex:Blog.Article'
    assert ('f:lib/blog/blog.ex:Blog.list_articles', ecto) in data
    assert ('f:lib/blog/blog.ex:Blog.delete_article', ecto) in data
    assert (ecto, 'c:priv/repo/migrations/1_create_articles.exs:articles') in data
    product = 'c:server/models/productModel.js:Product'
    assert nodes[product]['table'] == 'products'
    assert ('f:server/controllers/productController.js:getProducts', product) in data
    assert not any(b == product for a, b in data if a.startswith(('f:web/', 'm:web/')))


JVM_DOTNET_ORMS = {
    'svc/model/Owner.java': """
        @Entity
        @Table(name = "owners")
        public class Owner {
        }
    """,
    'svc/model/PetType.java': """
        @Entity
        @Table(name = "types")
        public class PetType {
        }
    """,
    'svc/model/OwnerRepository.java': """
        public interface OwnerRepository extends JpaRepository<Owner, Integer> {
            @Query("SELECT t FROM PetType t")
            List<PetType> findPetTypes();
        }
    """,
    'svc/web/OwnerResource.java': """
        class OwnerResource {
            private final OwnerRepository ownerRepository;

            public Owner find(int id) {
                return ownerRepository.findById(id);
            }

            public List<PetType> types() {
                return ownerRepository.findPetTypes();
            }
        }
    """,
    'svc/resources/schema.sql': """
        CREATE TABLE owners (id INTEGER);
    """,
    'Catalog/CatalogContext.cs': """
        public class CatalogContext : DbContext
        {
            public DbSet<CatalogItem> CatalogItems { get; set; }
        }
    """,
    'Catalog/CatalogItem.cs': """
        public class CatalogItem
        {
            public int Id { get; set; }
        }
    """,
    'Catalog/CatalogApi.cs': """
        public static class CatalogApi
        {
            public static async Task<CatalogItem> GetItem(CatalogContext context, int id)
            {
                return await context.CatalogItems.FindAsync(id);
            }
        }
    """,
    'backend/schema/Users.kt': """
        object Users : Table() {
            val userId = varchar("uuid", 50)
        }
    """,
    'backend/Repository.kt': """
        class Repository {
            fun count(): Long = Users.selectAll().count()
        }
    """,
    'backend/db/V1__init.sql': """
        CREATE TABLE IF NOT EXISTS Users (uuid VARCHAR(50));
    """,
}


def test_jpa_ef_and_exposed_tables(tmp_path):
    nodes, edges = run(tmp_path, JVM_DOTNET_ORMS)
    data = kinds(edges, 'data')
    owner, pettype = 'c:svc/model/Owner.java:Owner', 'c:svc/model/PetType.java:PetType'
    assert (owner, 'c:svc/resources/schema.sql:owners') in data
    assert ('f:svc/web/OwnerResource.java:OwnerResource.find', owner) in data
    assert ('f:svc/web/OwnerResource.java:OwnerResource.types', pettype) in data
    assert ('f:Catalog/CatalogApi.cs:CatalogApi.GetItem', 'c:Catalog/CatalogItem.cs:CatalogItem') in data
    assert nodes['c:Catalog/CatalogItem.cs:CatalogItem']['table'] == 'CatalogItems'
    users = 'c:backend/schema/Users.kt:Users'
    assert ('f:backend/Repository.kt:Repository.count', users) in data
    assert (users, 'c:backend/db/V1__init.sql:Users') in data


CONFIG_ENV = {
    'backend/app/core/config.py': """
        from pydantic_settings import BaseSettings


        class Settings(BaseSettings):
            SECRET_KEY: str
            SMTP_PORT: int = 587
    """,
    '.env': """
        SECRET_KEY=changethis
        SMTP_PORT=1025
    """,
    'compose.yml': """
        services:
          backend:
            image: api
            environment:
              - SECRET_KEY=${SECRET_KEY}
    """,
    'src/config.rs': """
        #[derive(clap::Parser)]
        pub struct Config {
            #[clap(long, env)]
            pub database_url: String,
        }
    """,
    'src/main.rs': """
        fn main() {
            env_logger::init();
        }
    """,
    '.env.sample': """
        DATABASE_URL=postgres://localhost/app
        RUST_LOG=debug
    """,
    'backend/src/main/resources/application.yaml': """
        service:
            secret: "$ADMIN_SECRET:test"
        database:
            host: "$DB_HOST:"
    """,
    'backend/src/main/kotlin/Config.kt': """
        class Config(config: ApplicationConfig) {
            val secret: String = config.property("service.secret").getString()
            val host = dbConfig.getOrNull("host")
        }
    """,
    'svc/src/main/resources/application.yml': """
        spring:
          ai:
            api-key: ${OPENAI_API_KEY:demo}
    """,
    'docker-compose.yml': """
        services:
          svc:
            environment:
              - OPENAI_API_KEY=${OPENAI_API_KEY}
              - ADMIN_SECRET=s
              - DB_HOST=db
    """,
    'cart/Startup.cs': """
        public class Startup
        {
            public void ConfigureServices(IServiceCollection services)
            {
                string redis = Configuration["REDIS_ADDR"];
            }
        }
    """,
    'ads/AdService.java': """
        class AdService {
            void start() {
                int port = Integer.parseInt(System.getenv().getOrDefault("PORT", "9555"));
            }
        }
    """,
}


def test_env_reads_from_settings_clap_config_keys_and_yaml(tmp_path):
    import subprocess
    root = tmp_path / 'repo'
    root.mkdir()
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    nodes, edges = run(tmp_path, CONFIG_ENV)
    env = kinds(edges, 'env')
    assert ('c:backend/app/core/config.py:Settings', 'v:SECRET_KEY') in env
    assert ('c:backend/app/core/config.py:Settings', 'v:SMTP_PORT') in env
    assert ('m:.env', 'v:SECRET_KEY') in env
    assert ('c:compose.yml:backend', 'v:SECRET_KEY') in env
    assert ('c:src/config.rs:Config', 'v:DATABASE_URL') in env
    assert ('f:src/main.rs:main', 'v:RUST_LOG') in env
    assert ('c:backend/src/main/kotlin/Config.kt:Config', 'v:ADMIN_SECRET') in env
    assert ('c:backend/src/main/kotlin/Config.kt:Config', 'v:DB_HOST') in env
    assert ('m:backend/src/main/resources/application.yaml', 'v:ADMIN_SECRET') in env
    assert ('m:svc/src/main/resources/application.yml', 'v:OPENAI_API_KEY') in env
    assert ('f:cart/Startup.cs:Startup.ConfigureServices', 'v:REDIS_ADDR') in env
    assert ('f:ads/AdService.java:AdService.start', 'v:PORT') in env


def test_untracked_private_env_is_ignored(tmp_path):
    nodes, edges = run(tmp_path, {'.env': 'TOKEN=x\n', 'app.py': "import os\nTOKEN = os.getenv('TOKEN')\n"})
    assert 'm:.env' not in nodes and nodes['v:TOKEN']['file'] == 'app.py'


SERVICES = {
    'compose.yml': """
        services:
          db:
            image: postgres:12
          backend:
            image: api
            depends_on:
              db:
                condition: service_healthy
          adminer:
            image: adminer
            depends_on: [db]
    """,
    'compose.override.yml': """
        services:
          frontend:
            environment:
              - VITE_API_URL=http://backend:8000
          playwright:
            depends_on:
              - backend
    """,
    'k8s/frontend.yaml': """
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: frontend
        spec:
          template:
            spec:
              containers:
                - name: server
                  env:
                    - name: CATALOG_ADDR
                      value: "catalog:3550"
    """,
    'k8s/catalog.yaml': """
        apiVersion: v1
        kind: Service
        metadata:
          name: catalog
        spec:
          ports:
            - port: 3550
    """,
    'gateway/src/main/resources/application.yml': """
        spring:
          application:
            name: api-gateway
          cloud:
            gateway:
              routes:
                - id: vets
                  uri: lb://vets-service
                  predicates:
                    - Path=/api/vet/**
    """,
    'vets/src/main/resources/application.yml': """
        spring:
          application:
            name: vets-service
    """,
    'backend/src/main/resources/application.yaml': """
        ktor:
            application:
                modules:
                    - org.example.RoutesModuleKt.routesModule
    """,
    'backend/src/main/kotlin/org/example/RoutesModule.kt': """
        fun Application.routesModule() {
        }
    """,
}


def test_deployment_service_wiring(tmp_path):
    nodes, edges = run(tmp_path, SERVICES)
    depends, handles = kinds(edges, 'depends'), kinds(edges, 'handles')
    assert ('c:compose.yml:backend', 'c:compose.yml:db') in depends
    assert ('c:compose.yml:adminer', 'c:compose.yml:db') in depends
    assert ('c:compose.override.yml:frontend', 'c:compose.yml:backend') in depends
    assert ('c:compose.override.yml:playwright', 'c:compose.yml:backend') in depends
    assert ('c:k8s/frontend.yaml:Deployment/frontend', 'c:k8s/catalog.yaml:Service/catalog') in depends
    gw, vets = 'm:gateway/src/main/resources/application.yml', 'm:vets/src/main/resources/application.yml'
    assert (gw, vets) in depends
    assert ('e:gateway/src/main/resources/application.yml:ANY /api/vet/**', vets) in handles
    assert ('m:backend/src/main/resources/application.yaml',
            'f:backend/src/main/kotlin/org/example/RoutesModule.kt:routesModule') in depends
    assert not any('postgres' in b for a, b in depends)


KTOR = {
    'backend/src/main/kotlin/RoutesModule.kt': """
        import io.ktor.server.routing.*

        fun Application.routesModule() {
            routing {
                get("/healthz") {
                    call.respond(HttpStatusCode.OK)
                }
                route("/{year}") {
                    yearRoutes()
                }
            }
        }
    """,
    'backend/src/main/kotlin/routes/UserRoutes.kt': """
        import io.ktor.server.routing.*

        fun Route.yearRoutes() {
            val config: ConferenceConfig by inject()
            post("sign") {
                call.respond(1)
            }
        }
    """,
    'app/src/YearlyApi.kt': """
        class YearlyApi(private val year: Int, private val client: HttpClient) {
            suspend fun sign(): Boolean = client.post {
                apiUrl("sign")
            }.status.isSuccess()

            private fun HttpRequestBuilder.apiUrl(path: String) {
                url {
                    encodedPath = "$year/$path"
                }
            }
        }
    """,
    'admin/src/AdminApi.kt': """
        class AdminApi(private val token: String) {
            private val origin: String = window.location.origin
            private val client = HttpClient(Js)

            suspend fun health(): String = get("$origin/healthz")

            private suspend inline fun <reified T> get(url: String): T =
                client.get(url) { header("Authorization", token) }.body()
        }
    """,
}


def test_ktor_routes_mounts_and_clients(tmp_path):
    nodes, edges = run(tmp_path, KTOR)
    handles, http = kinds(edges, 'handles'), kinds(edges, 'http')
    sign = 'e:backend/src/main/kotlin/routes/UserRoutes.kt:POST /:year/sign'
    assert (sign, 'f:backend/src/main/kotlin/routes/UserRoutes.kt:yearRoutes') in handles
    assert ('f:backend/src/main/kotlin/RoutesModule.kt:routesModule',
            'f:backend/src/main/kotlin/routes/UserRoutes.kt:yearRoutes') in handles
    assert ('f:app/src/YearlyApi.kt:YearlyApi.sign', sign) in http
    assert ('f:admin/src/AdminApi.kt:AdminApi.health', 'e:backend/src/main/kotlin/RoutesModule.kt:GET /healthz') in http


EVENTS_AND_GRPC = {
    'Basket.API/IntegrationEvents/Events/OrderStartedIntegrationEvent.cs': """
        public record OrderStartedIntegrationEvent(string UserId) : IntegrationEvent;
    """,
    'Basket.API/IntegrationEvents/OrderStartedIntegrationEventHandler.cs': """
        public class OrderStartedIntegrationEventHandler(
            IBasketRepository repository) : IIntegrationEventHandler<OrderStartedIntegrationEvent>
        {
            public async Task Handle(OrderStartedIntegrationEvent @event)
            {
                await repository.DeleteBasketAsync(@event.UserId);
            }
        }
    """,
    'Basket.API/Extensions.cs': """
        public static class Extensions
        {
            public static void AddServices(this IHostApplicationBuilder builder)
            {
                builder.AddRabbitMqEventBus("eventbus")
                       .AddSubscription<OrderStartedIntegrationEvent, OrderStartedIntegrationEventHandler>();
            }
        }
    """,
    'Ordering.API/CreateOrderCommandHandler.cs': """
        public class CreateOrderCommandHandler
        {
            public async Task<bool> Handle(CreateOrderCommand message)
            {
                var evt = new OrderStartedIntegrationEvent(message.UserId);
                await _events.AddAndSaveEventAsync(evt);
                return true;
            }
        }
    """,
    'Basket.API/Proto/basket.proto': """
        syntax = "proto3";
        package BasketApi;
        service Basket {
          rpc GetBasket(GetBasketRequest) returns (CustomerBasketResponse) {}
        }
    """,
    'Basket.API/Grpc/BasketService.cs': """
        public class BasketService(
            IBasketRepository repository) : Basket.BasketBase
        {
            public override async Task<CustomerBasketResponse> GetBasket(GetBasketRequest request, ServerCallContext context)
            {
                return new();
            }
        }
    """,
    'Basket.API/Program.cs': """
        var app = builder.Build();
        app.MapGrpcService<BasketService>();
    """,
    'WebApp/Services/BasketClientService.cs': """
        using GrpcBasketClient = eShop.Basket.API.Grpc.Basket.BasketClient;

        public class BasketClientService(GrpcBasketClient basketClient)
        {
            public async Task Load()
            {
                var result = await basketClient.GetBasketAsync(new ());
            }
        }
    """,
    'api/protobuf/users.proto': """
        syntax = "proto3";
        package users;
        service UsersService {
          rpc GetTrainingBalance(GetTrainingBalanceRequest) returns (GetTrainingBalanceResponse) {}
        }
    """,
    'internal/users/main.go': """
        package main

        func main() {
            server.RunGRPCServer(func(server *grpc.Server) {
                svc := NewGrpcServer(app)
                users.RegisterUsersServiceServer(server, svc)
            })
        }
    """,
    'internal/users/ports/grpc.go': """
        package ports

        type GrpcServer struct {
            app Application
        }

        func NewGrpcServer(application Application) GrpcServer {
            return GrpcServer{app: application}
        }

        func (g GrpcServer) GetTrainingBalance(ctx context.Context, r *users.GetTrainingBalanceRequest) (*users.GetTrainingBalanceResponse, error) {
            return nil, nil
        }
    """,
    'internal/common/client/grpc.go': """
        package client

        func NewUsersClient() (client users.UsersServiceClient, close func() error, err error) {
            return users.NewUsersServiceClient(conn), conn.Close, nil
        }
    """,
    'internal/trainings/adapters/users_grpc.go': """
        package adapters

        type UsersGrpc struct {
            client users.UsersServiceClient
        }

        func (s UsersGrpc) Balance(ctx context.Context) error {
            _, err := s.client.GetTrainingBalance(ctx, &users.GetTrainingBalanceRequest{})
            return err
        }
    """,
    'internal/users/fixtures.go': """
        package main

        func setAmount() error {
            usersClient, usersClose, err := client.NewUsersClient()
            resp, err := usersClient.GetTrainingBalance(context.Background(), nil)
            return err
        }
    """,
}


def test_integration_events_and_grpc_wiring(tmp_path):
    nodes, edges = run(tmp_path, EVENTS_AND_GRPC)
    event, rpc, handles = kinds(edges, 'event'), kinds(edges, 'rpc'), kinds(edges, 'handles')
    topic = 't:OrderStartedIntegrationEvent'
    assert ('f:Ordering.API/CreateOrderCommandHandler.cs:CreateOrderCommandHandler.Handle', topic) in event
    assert (topic, 'f:Basket.API/IntegrationEvents/OrderStartedIntegrationEventHandler.cs:OrderStartedIntegrationEventHandler.Handle') in event
    assert (topic, 'm:Basket.API/Extensions.cs') in event or (topic, 'f:Basket.API/Extensions.cs:Extensions.AddServices') in event
    basket = 'e:Basket.API/Proto/basket.proto:RPC BasketApi.Basket/GetBasket'
    assert (basket, 'f:Basket.API/Grpc/BasketService.cs:BasketService.GetBasket') in handles
    assert ('m:Basket.API/Program.cs', 'c:Basket.API/Grpc/BasketService.cs:BasketService') in handles
    assert ('f:WebApp/Services/BasketClientService.cs:BasketClientService.Load', basket) in rpc
    balance = 'e:api/protobuf/users.proto:RPC users.UsersService/GetTrainingBalance'
    assert (balance, 'f:internal/users/ports/grpc.go:GrpcServer.GetTrainingBalance') in handles
    assert ('f:internal/trainings/adapters/users_grpc.go:UsersGrpc.Balance', balance) in rpc
    assert ('f:internal/users/fixtures.go:setAmount', balance) in rpc


ROUTERS = {
    'lib/app_web/router.ex': """
        defmodule AppWeb.Router do
          use AppWeb, :router

          scope "/", AppWeb do
            resources "/comments", CommentController, except: [:new, :edit]
            get("/tags", TagController, :index)
          end
        end
    """,
    'lib/app_web/controllers/comment_controller.ex': """
        defmodule AppWeb.CommentController do
          def index(conn, _params), do: conn
          def delete(conn, _params), do: conn
        end
    """,
    'lib/app_web/controllers/tag_controller.ex': """
        defmodule AppWeb.TagController do
          def index(conn, _params), do: conn
        end
    """,
    'config/routes.rb': """
        Rails.application.routes.draw do
          scope :api do
            devise_for :users, controllers: { sessions: :sessions },
                               path_names: { sign_in: :login }
          end
        end
    """,
    'app/controllers/sessions_controller.rb': """
        class SessionsController < Devise::SessionsController
          def create
          end
        end
    """,
}


def test_phoenix_app_router_and_devise_sessions(tmp_path):
    nodes, edges = run(tmp_path, ROUTERS)
    handles = kinds(edges, 'handles')
    ctrl = 'lib/app_web/controllers/comment_controller.ex'
    assert ('e:lib/app_web/router.ex:DELETE /comments/:id', f'f:{ctrl}:AppWeb.CommentController.delete') in handles
    assert ('e:lib/app_web/router.ex:GET /tags', 'f:lib/app_web/controllers/tag_controller.ex:AppWeb.TagController.index') in handles
    assert 'e:lib/app_web/router.ex:GET /comments/:id' not in nodes
    assert ('e:config/routes.rb:POST /api/users/login', 'f:app/controllers/sessions_controller.rb:SessionsController.create') in handles
    assert 'e:config/routes.rb:DELETE /api/users/sign_out' not in nodes


GENERATED_SERVERS = {
    'internal/trainer/ports/openapi_api.gen.go': """
        // Code generated by oapi-codegen. DO NOT EDIT.
        package ports

        type ServerInterfaceWrapper struct {
            Handler ServerInterface
        }

        func (siw *ServerInterfaceWrapper) MakeHourAvailable(w http.ResponseWriter, r *http.Request) {
            siw.Handler.MakeHourAvailable(w, r)
        }

        func HandlerWithOptions(si ServerInterface, options ChiServerOptions) http.Handler {
            r := options.BaseRouter
            wrapper := ServerInterfaceWrapper{Handler: si}
            r.Group(func(r chi.Router) {
                r.Put(options.BaseURL+"/trainer/calendar/make-hour-available", wrapper.MakeHourAvailable)
            })
            return r
        }
    """,
    'internal/trainer/ports/http.go': """
        package ports

        type HttpServer struct{}

        func (h HttpServer) MakeHourAvailable(w http.ResponseWriter, r *http.Request) {
        }
    """,
    'internal/trainer/ports/grpc.go': """
        package ports

        type GrpcServer struct{}

        func (g GrpcServer) MakeHourAvailable(ctx context.Context, request *trainer.UpdateHourRequest) (*empty.Empty, error) {
            return nil, nil
        }
    """,
    'web/src/clients/trainer/api/DefaultApi.js': """
        /*
         * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
         */
        export default class DefaultApi {
            makeHourAvailable(hourUpdate, callback) {
              return this.apiClient.callApi(
                '/trainer/calendar/make-hour-available', 'PUT',
                {}, {}, {}, {}, hourUpdate, [], [], [], null, null, callback
              );
            }
        }
    """,
}


def test_generated_handlers_point_to_implementations(tmp_path):
    nodes, edges = run(tmp_path, GENERATED_SERVERS)
    handles, http = kinds(edges, 'handles'), kinds(edges, 'http')
    ep = 'e:internal/trainer/ports/openapi_api.gen.go:PUT /trainer/calendar/make-hour-available'
    assert (ep, 'f:internal/trainer/ports/http.go:HttpServer.MakeHourAvailable') in handles
    assert ('f:web/src/clients/trainer/api/DefaultApi.js:DefaultApi.makeHourAvailable', ep) in http


URL_VALUES = {
    'WebApp/Services/CatalogService.cs': """
        public class CatalogService(HttpClient httpClient)
        {
            private readonly string remoteServiceBaseUrl = "api/catalog/";

            public Task<CatalogItem?> GetCatalogItem(int id)
            {
                var uri = $"{remoteServiceBaseUrl}items/{id}";
                return httpClient.GetFromJsonAsync<CatalogItem>(uri);
            }

            public Task<CatalogResult> GetCatalogItems(int pageIndex)
            {
                var uri = GetAllCatalogItemsUri(remoteServiceBaseUrl, pageIndex);
                return httpClient.GetFromJsonAsync<CatalogResult>(uri);
            }

            private static string GetAllCatalogItemsUri(string baseUri, int pageIndex)
            {
                return $"{baseUri}items?pageIndex={pageIndex}";
            }
        }
    """,
    'Catalog.API/CatalogApi.cs': """
        public static class CatalogApi
        {
            public static IEndpointRouteBuilder MapCatalogApi(this IEndpointRouteBuilder app)
            {
                var api = app.MapGroup("api/catalog");
                api.MapGet("/items", GetAllItems);
                api.MapGet("/items/{id:int}", GetItemById);
                return app;
            }

            public static Task GetAllItems() => null;
            public static Task GetItemById(int id) => null;
        }
    """,
    'web/src/client.js': """
        export function first () { const url = '/api/catalog/items'; return fetch(url) }
        export function load (url) { return fetch(url) }
    """,
}


def test_url_constants_fields_and_helper_returns(tmp_path):
    nodes, edges = run(tmp_path, URL_VALUES)
    http = kinds(edges, 'http')
    svc = 'f:WebApp/Services/CatalogService.cs:CatalogService'
    assert (f'{svc}.GetCatalogItem', 'e:Catalog.API/CatalogApi.cs:GET /api/catalog/items/:id') in http
    assert (f'{svc}.GetCatalogItems', 'e:Catalog.API/CatalogApi.cs:GET /api/catalog/items') in http
    assert ('f:web/src/client.js:first', 'e:Catalog.API/CatalogApi.cs:GET /api/catalog/items') in http
    assert not any(a == 'f:web/src/client.js:load' for a, b in http)


SPRING_JS = {
    'customers/web/PetResource.java': """
        @RestController
        class PetResource {
            @GetMapping("/petTypes")
            public List<PetType> getPetTypes() { return null; }

            @PutMapping("/owners/*/pets/{petId}")
            public void processUpdateForm(@RequestBody PetRequest petRequest) { }

            @PostMapping("/owners/{ownerId}/pets")
            public Pet processCreationForm(@PathVariable("ownerId") int ownerId) { return null; }
        }
    """,
    'static/scripts/pages/PetFormPage.js': """
        import { request } from '../api/client.js';
        export async function loadTypes () {
            return request('/api/customer/petTypes', { signal });
        }
        export async function save (ownerId, petId, payload) {
            const petPath = petId ? `/${petId}` : '';
            const url = `/api/customer/owners/${ownerId}/pets${petPath}`;
            await request(url, { ...jsonRequest(petId ? 'PUT' : 'POST', payload) });
        }
    """,
}


def test_spring_paths_wildcards_and_request_verbs(tmp_path):
    nodes, edges = run(tmp_path, SPRING_JS)
    http = kinds(edges, 'http')
    page = 'f:static/scripts/pages/PetFormPage.js'
    assert (f'{page}:loadTypes', 'e:customers/web/PetResource.java:GET /petTypes') in http
    assert (f'{page}:save', 'e:customers/web/PetResource.java:PUT /owners/:param/pets/:petId') in http


MISC = {
    'frontend/main.go': """
        package main

        func main() {
            r := mux.NewRouter()
            r.HandleFunc(baseUrl+"/bot", svc.chatBotHandler).Methods(http.MethodPost)
        }

        func (fe *frontendServer) chatBotHandler(w http.ResponseWriter, r *http.Request) {
            url := "http://" + fe.assistantSvcAddr
            req, err := http.NewRequest(http.MethodPost, url, r.Body)
        }
    """,
    'frontend/templates/assistant.html': """
        <div id="chat"></div>
        <script>
          async function send () {
            const response = await fetch("{{ $.baseUrl }}/bot", { method: "POST" });
          }
        </script>
    """,
    'assistant/server.py': """
        from flask import Flask


        def create_app():
            app = Flask(__name__)

            @app.route("/", methods=['POST'])
            def talk():
                return "ok"

            return app
    """,
    'hooks/WebhookEndpoints.cs': """
        public static class WebhookEndpoints
        {
            public static IEndpointRouteBuilder Map(this IEndpointRouteBuilder app)
            {
                app.MapMethods("/check", [HttpMethods.Options], () => Results.Ok());
                return app;
            }
        }
    """,
    'src/articles.rs': """
        async fn delete_article(ctx: Ctx) -> Result<()> {
            sqlx::query!(
                r#"
                    -- delete only if the author matches
                    with deleted as (delete from article where slug = $1 returning 1)
                    select exists(select 1 from deleted) "deleted!"
                "#,
                slug
            );
            Ok(())
        }
    """,
    'migrations/1_article.sql': """
        create table article (slug text primary key);
    """,
}


def test_inline_scripts_root_urls_nested_handlers_and_sql_comments(tmp_path):
    nodes, edges = run(tmp_path, MISC)
    http, handles, data = kinds(edges, 'http'), kinds(edges, 'handles'), kinds(edges, 'data')
    assert ('m:frontend/templates/assistant.html', 'e:frontend/main.go:POST /bot') in http
    assert ('f:frontend/main.go:frontendServer.chatBotHandler', 'e:assistant/server.py:POST /') in http
    assert {('e:assistant/server.py:POST /', 'f:assistant/server.py:create_app'),
            ('e:assistant/server.py:POST /', 'f:assistant/server.py:create_app.talk')} & handles
    assert 'e:hooks/WebhookEndpoints.cs:OPTIONS /check' in nodes
    assert ('f:src/articles.rs:delete_article', 'c:migrations/1_article.sql:article') in data


def test_sqlalchemy_tablename_models_join_migrations_and_uses(tmp_path):
    files = {
        'app/models.py': "class Account(Base):\n    __tablename__ = 'accounts'\n",
        'app/views.py': "from app.models import Account\n\n\ndef show(db, pk):\n    return db.query(Account).get(pk)\n\n\ndef make():\n    return Account(name='x')\n",
        'db/schema.sql': 'CREATE TABLE accounts (id INTEGER);\n',
    }
    nodes, edges = run(tmp_path, files)
    data = kinds(edges, 'data')
    model = 'c:app/models.py:Account'
    assert (model, 'c:db/schema.sql:accounts') in data
    assert ('f:app/views.py:show', model) in data and ('f:app/views.py:make', model) in data
