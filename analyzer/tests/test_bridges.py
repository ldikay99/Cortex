from conftest import write_repo
from cortex_graph.analyze import analyze
from cortex_graph.bridges import client_path, norm_path


def run(tmp_path, files):
    out = analyze(write_repo(tmp_path / 'repo', files), git=False)
    keys = {n['id']: n['key'] for n in out['nodes']}
    nodes = {n['key']: n for n in out['nodes']}
    return nodes, {(keys[e['a']], keys[e['b']], e['kind']) for e in out['edges']}


def kinds(edges, kind):
    return {(a, b) for a, b, k in edges if k == kind}


def test_paths_are_normalized():
    assert norm_path('/users/{id}/posts/<int:pk>/') == '/users/:id/posts/:pk'
    assert norm_path('api//items/:item_id?') == '/api/items/:item_id'
    assert client_path('\0/api/users/\0?x=1') == '/api/users/:param'
    assert client_path('https://example.com/v1/items') == '/v1/items'
    assert client_path('user_id') is None
    assert client_path('/') == '/'


EXPRESS = {
    'server/app.js': """
        const express = require('express');
        const users = require('./routes/users');
        const app = express();
        app.use('/api/users', users);
        app.get('/health', (req, res) => res.send('ok'));
        module.exports = app;
    """,
    'server/routes/users.js': """
        const express = require('express');
        const router = express.Router();
        function listUsers(req, res) { res.json([]); }
        function getUser(req, res) { res.json({}); }
        router.get('/', listUsers);
        router.get('/:id', getUser);
        module.exports = router;
    """,
    'web/src/api.ts': """
        export async function loadUser(id: string) {
          const res = await fetch(`${API_URL}/api/users/${id}`);
          return res.json();
        }

        export function loadUsers() {
          return axios.get('/api/users');
        }
    """,
}


def test_express_routes_and_react_fetch(tmp_path):
    nodes, edges = run(tmp_path, EXPRESS)
    one = 'e:server/routes/users.js:GET /api/users/:id'
    many = 'e:server/routes/users.js:GET /api/users'
    assert nodes[one]['kind'] == 'endpoint' and nodes[one]['route'] == 'GET /api/users/:id'
    assert (one, 'f:server/routes/users.js:getUser') in kinds(edges, 'handles')
    assert (many, 'f:server/routes/users.js:listUsers') in kinds(edges, 'handles')
    assert ('m:server/routes/users.js', one) in kinds(edges, 'contains')
    assert ('e:server/app.js:GET /health', 'm:server/app.js') in kinds(edges, 'handles')
    assert ('f:web/src/api.ts:loadUser', one) in kinds(edges, 'http')
    assert ('f:web/src/api.ts:loadUsers', many) in kinds(edges, 'http')


FASTAPI = {
    'api/__init__.py': '',
    'api/routers/__init__.py': '',
    'api/main.py': """
        from fastapi import FastAPI

        from .routers import items

        app = FastAPI()
        app.include_router(items.router, prefix='/v1')
    """,
    'api/routers/items.py': """
        from fastapi import APIRouter

        router = APIRouter(prefix='/items')


        @router.get('/{item_id}')
        def read_item(item_id: int):
            '''Example: @router.get('/docs-only') must not count.'''
            return {}


        @router.post('')
        async def create_item():
            return {}
    """,
    'ui/client.ts': """
        export const getItem = (id: number) => fetch(`/v1/items/${id}`).then((r) => r.json());

        export async function createItem(data: object) {
          return fetch('/v1/items', { method: 'POST', body: JSON.stringify(data) });
        }
    """,
    'tests/test_items.py': """
        from fastapi import FastAPI

        app = FastAPI()


        @app.get('/only-in-tests')
        def fake():
            return {}
    """,
}


def test_fastapi_prefixes_and_ts_client(tmp_path):
    nodes, edges = run(tmp_path, FASTAPI)
    get = 'e:api/routers/items.py:GET /v1/items/:item_id'
    post = 'e:api/routers/items.py:POST /v1/items'
    assert (get, 'f:api/routers/items.py:read_item') in kinds(edges, 'handles')
    assert (post, 'f:api/routers/items.py:create_item') in kinds(edges, 'handles')
    assert ('f:ui/client.ts:getItem', get) in kinds(edges, 'http')
    assert ('f:ui/client.ts:createItem', post) in kinds(edges, 'http')
    routes = {n['route'] for n in nodes.values() if n['kind'] == 'endpoint'}
    assert not any('only-in-tests' in r or 'docs-only' in r for r in routes)


SPRING = {
    'svc/src/main/java/com/x/OwnerController.java': """
        package com.x;

        @RestController
        @RequestMapping("/owners")
        public class OwnerController {
            @GetMapping("/{ownerId}")
            public Owner find(@PathVariable int ownerId) {
                return null;
            }

            @PostMapping
            public Owner create(@RequestBody Owner owner) {
                return owner;
            }
        }
    """,
    'android/src/main/kotlin/com/y/OwnerApi.kt': """
        package com.y

        interface OwnerApi {
            @GET("owners/{id}")
            fun owner(@Path("id") id: Int): Call<Owner>
        }
    """,
    'gateway/src/main/java/com/z/Gateway.java': """
        package com.z;

        public class Gateway {
            private RestTemplate restTemplate;

            public Owner load(int id) {
                return restTemplate.getForObject("http://owners-service/owners/{id}", Owner.class, id);
            }

            public Owner save(Owner owner) {
                return restTemplate.postForObject("http://owners-service/owners", owner, Owner.class);
            }
        }
    """,
}


def test_spring_endpoints_with_retrofit_and_resttemplate(tmp_path):
    nodes, edges = run(tmp_path, SPRING)
    get = 'e:svc/src/main/java/com/x/OwnerController.java:GET /owners/:ownerId'
    post = 'e:svc/src/main/java/com/x/OwnerController.java:POST /owners'
    assert (get, 'f:svc/src/main/java/com/x/OwnerController.java:OwnerController.find') in kinds(edges, 'handles')
    assert (post, 'f:svc/src/main/java/com/x/OwnerController.java:OwnerController.create') in kinds(edges, 'handles')
    http = kinds(edges, 'http')
    assert ('f:gateway/src/main/java/com/z/Gateway.java:Gateway.load', get) in http
    assert ('f:gateway/src/main/java/com/z/Gateway.java:Gateway.save', post) in http
    assert any(a.startswith(('f:android/', 'c:android/', 'm:android/')) and b == get for a, b in http)


GIN = {
    'backend/main.go': """
        package main

        import "github.com/gin-gonic/gin"

        func listOrders(c *gin.Context) {}

        func main() {
        	r := gin.Default()
        	v1 := r.Group("/api/v1")
        	v1.GET("/orders", listOrders)
        	v1.POST("/orders", func(c *gin.Context) {})
        	r.Run()
        }
    """,
    'scripts/sync.py': """
        import requests

        BASE = 'http://localhost:8080'


        def fetch_orders():
            return requests.get(f'{BASE}/api/v1/orders').json()


        def push_order(order):
            return requests.post(BASE + '/api/v1/orders', json=order)
    """,
}


def test_gin_groups_and_python_requests(tmp_path):
    nodes, edges = run(tmp_path, GIN)
    get, post = 'e:backend/main.go:GET /api/v1/orders', 'e:backend/main.go:POST /api/v1/orders'
    assert (get, 'f:backend/main.go:listOrders') in kinds(edges, 'handles')
    assert (post, 'f:backend/main.go:main') in kinds(edges, 'handles')
    assert ('f:scripts/sync.py:fetch_orders', get) in kinds(edges, 'http')
    assert ('f:scripts/sync.py:push_order', post) in kinds(edges, 'http')


GRPC = {
    'proto/shop.proto': """
        syntax = "proto3";
        package shop;

        service CartService {
          rpc AddItem (AddItemRequest) returns (Empty) {}
          rpc GetCart (GetCartRequest) returns (Cart) {}
        }

        message AddItemRequest { string user_id = 1; }
    """,
    'cart/server.go': """
        package main

        type cartServer struct {
        	pb.UnimplementedCartServiceServer
        }

        func (s *cartServer) AddItem(ctx context.Context, req *pb.AddItemRequest) (*pb.Empty, error) {
        	return nil, nil
        }

        func main() {
        	srv := grpc.NewServer()
        	pb.RegisterCartServiceServer(srv, &cartServer{})
        }
    """,
    'web/cart_client.py': """
        import shop_pb2_grpc


        def add(channel):
            stub = shop_pb2_grpc.CartServiceStub(channel)
            return stub.AddItem(None)
    """,
    'frontend/rpc.go': """
        package main

        func getCart(conn *grpc.ClientConn) {
        	pb.NewCartServiceClient(conn).
        		GetCart(ctx, nil)
        }
    """,
}


def test_grpc_server_and_clients(tmp_path):
    nodes, edges = run(tmp_path, GRPC)
    add, get = 'e:proto/shop.proto:RPC shop.CartService/AddItem', 'e:proto/shop.proto:RPC shop.CartService/GetCart'
    assert nodes[add]['kind'] == 'endpoint'
    assert (add, 'f:cart/server.go:cartServer.AddItem') in kinds(edges, 'handles')
    assert ('f:web/cart_client.py:add', add) in kinds(edges, 'rpc')
    assert ('f:frontend/rpc.go:getCart', get) in kinds(edges, 'rpc')


RAILS = {
    'config/routes.rb': """
        Rails.application.routes.draw do
          root 'pages#home'
          resources :photos, only: [:index, :show] do
            member do
              get :preview
            end
          end
          namespace :admin do
            resources :users, only: [:destroy]
          end
          get 'about', to: 'pages#about'
        end
    """,
    'app/controllers/photos_controller.rb': """
        class PhotosController < ApplicationController
          def index; end
          def show; end
          def preview; end
        end
    """,
    'app/controllers/pages_controller.rb': """
        class PagesController < ApplicationController
          def home; end
          def about; end
        end
    """,
    'app/controllers/admin/users_controller.rb': """
        module Admin
          class UsersController < ApplicationController
            def destroy; end
          end
        end
    """,
}


def test_rails_routes(tmp_path):
    nodes, edges = run(tmp_path, RAILS)
    handles = kinds(edges, 'handles')
    photos, pages = 'app/controllers/photos_controller.rb', 'app/controllers/pages_controller.rb'
    assert ('e:config/routes.rb:GET /', f'f:{pages}:PagesController.home') in handles
    assert ('e:config/routes.rb:GET /photos', f'f:{photos}:PhotosController.index') in handles
    assert ('e:config/routes.rb:GET /photos/:id', f'f:{photos}:PhotosController.show') in handles
    assert ('e:config/routes.rb:GET /photos/:id/preview', f'f:{photos}:PhotosController.preview') in handles
    assert ('e:config/routes.rb:DELETE /admin/users/:id',
            'f:app/controllers/admin/users_controller.rb:UsersController.destroy') in handles
    assert ('e:config/routes.rb:GET /about', f'f:{pages}:PagesController.about') in handles
    assert 'e:config/routes.rb:POST /photos' not in nodes


LARAVEL = {
    'routes/api.php': """
        <?php
        use App\\Http\\Controllers\\UserController;
        use Illuminate\\Support\\Facades\\Route;

        Route::get('/users/{id}', [UserController::class, 'show']);
        Route::prefix('admin')->group(function () {
            Route::post('/users', [UserController::class, 'store']);
        });
        Route::apiResource('posts', PostController::class)->only(['index']);
    """,
    'app/Http/Controllers/UserController.php': """
        <?php
        namespace App\\Http\\Controllers;

        class UserController
        {
            public function show($id) {}
            public function store() {}
        }
    """,
    'app/Http/Controllers/PostController.php': """
        <?php
        namespace App\\Http\\Controllers;

        class PostController
        {
            public function index() {}
        }
    """,
}


def test_laravel_routes(tmp_path):
    nodes, edges = run(tmp_path, LARAVEL)
    handles = kinds(edges, 'handles')
    users = 'app/Http/Controllers/UserController.php'
    assert ('e:routes/api.php:GET /api/users/:id', f'f:{users}:UserController.show') in handles
    assert ('e:routes/api.php:POST /api/admin/users', f'f:{users}:UserController.store') in handles
    assert ('e:routes/api.php:GET /api/posts', 'f:app/Http/Controllers/PostController.php:PostController.index') in handles
    assert 'e:routes/api.php:POST /api/posts' not in nodes


ENV = {
    'docker-compose.yml': """
        services:
          api:
            image: demo
            environment:
              - DATABASE_URL=postgres://db
              - DEBUG
          worker:
            image: demo
            environment:
              REDIS_URL: redis://cache
    """,
    '.env.example': """
        SECRET_KEY=changeme
    """,
    '.env': """
        SECRET_KEY=real
        LEAK_ONLY=1
    """,
    'Dockerfile': """
        FROM python:3.12
        ENV PORT=8000 MODE=prod
        ARG BUILD_ID
    """,
    'app/settings.py': """
        import os

        DATABASE_URL = os.environ['DATABASE_URL']


        def secret():
            return os.getenv('SECRET_KEY')
    """,
    'web/src/config.ts': """
        export const redis = () => process.env.REDIS_URL;
    """,
}


def test_env_variables_from_config_and_code(tmp_path):
    nodes, edges = run(tmp_path, ENV)
    env = kinds(edges, 'env')
    assert nodes['v:DATABASE_URL']['file'] == 'docker-compose.yml' and nodes['v:DATABASE_URL']['kind'] == 'variable'
    assert nodes['v:SECRET_KEY']['file'] == '.env.example'
    assert ('m:docker-compose.yml', 'v:DATABASE_URL') in env
    assert ('m:docker-compose.yml', 'v:DEBUG') in env
    assert ('m:docker-compose.yml', 'v:REDIS_URL') in env
    assert ('m:app/settings.py', 'v:DATABASE_URL') in env
    assert ('f:app/settings.py:secret', 'v:SECRET_KEY') in env
    assert ('f:web/src/config.ts:redis', 'v:REDIS_URL') in env
    assert {('m:Dockerfile', 'v:PORT'), ('m:Dockerfile', 'v:MODE'), ('m:Dockerfile', 'v:BUILD_ID')} <= env
    assert ('m:docker-compose.yml', 'v:DATABASE_URL') in kinds(edges, 'contains')
    assert 'v:LEAK_ONLY' not in nodes and 'm:.env' not in nodes


KAFKA = {
    'orders/producer.ts': """
        export async function publishOrder(producer: any, order: object) {
          await producer.send({ topic: 'orders.created', messages: [{ value: JSON.stringify(order) }] });
        }
    """,
    'billing/Listener.java': """
        public class Listener {
            @KafkaListener(topics = "orders.created", groupId = "billing")
            public void onOrder(String message) {
            }
        }
    """,
    'shipping/consumer.py': """
        from kafka import KafkaConsumer


        def consume():
            consumer = KafkaConsumer('orders.created')
            for msg in consumer:
                print(msg)
    """,
}


def test_kafka_topic_links_producer_and_consumers(tmp_path):
    nodes, edges = run(tmp_path, KAFKA)
    topic = 't:orders.created'
    assert nodes[topic]['kind'] == 'topic'
    event = kinds(edges, 'event')
    assert ('f:orders/producer.ts:publishOrder', topic) in event
    assert (topic, 'f:billing/Listener.java:Listener.onOrder') in event
    assert (topic, 'f:shipping/consumer.py:consume') in event


SQL = {
    'db/schema.sql': """
        CREATE TABLE users (id int);
        CREATE TABLE orders (id int);
    """,
    'app/repo.py': '''
        def find_user(conn, uid):
            return conn.execute("SELECT * FROM users WHERE id = %s", (uid,))


        def count_orders(conn):
            sql = """
                SELECT count(*) FROM orders
            """
            return conn.execute(sql)


        def label():
            return "Select one from users list"
    ''',
}


def test_sql_strings_link_to_tables(tmp_path):
    nodes, edges = run(tmp_path, SQL)
    data = kinds(edges, 'data')
    assert ('f:app/repo.py:find_user', 'c:db/schema.sql:users') in data
    assert ('f:app/repo.py:count_orders', 'c:db/schema.sql:orders') in data
    assert not any(a == 'f:app/repo.py:label' for a, b in data)


MIXED = {
    'web/app/api/users/[id]/route.ts': """
        export async function GET(request: Request) {
          return Response.json({});
        }
    """,
    'web/components/Profile.tsx': """
        export function Profile({ id }: { id: string }) {
          fetch(`/api/users/${id}`);
          return null;
        }
    """,
    'site/urls.py': """
        from django.urls import include, path

        urlpatterns = [
            path('blog/', include('blog.urls')),
        ]
    """,
    'blog/__init__.py': '',
    'blog/urls.py': """
        from django.urls import path

        from . import views

        urlpatterns = [
            path('<int:pk>/', views.detail, name='detail'),
        ]
    """,
    'blog/views.py': """
        def detail(request, pk):
            return None
    """,
    'Catalog/CatalogApi.cs': """
        public static class CatalogApi
        {
            public static void Map(WebApplication app)
            {
                var api = app.MapGroup("api/catalog");
                api.MapGet("/items/{id:int}", GetItem);
            }

            public static Item GetItem(int id) { return null; }
        }
    """,
    'Ordering/OrdersController.cs': """
        [ApiController]
        [Route("api/[controller]")]
        public class OrdersController : ControllerBase
        {
            [HttpGet("{id}")]
            public Order Get(int id) { return null; }
        }
    """,
    'client/CatalogClient.cs': """
        public class CatalogClient
        {
            private HttpClient http;

            public Task<Item> Load(int id) => http.GetFromJsonAsync<Item>($"api/catalog/items/{id}");
        }
    """,
    'nest/cats.controller.ts': """
        import { Controller, Get } from '@nestjs/common';

        @Controller('cats')
        export class CatsController {
          @Get(':id')
          findOne(id: string) {
            return id;
          }
        }
    """,
}


def test_nextjs_django_aspnet_and_nest(tmp_path):
    nodes, edges = run(tmp_path, MIXED)
    handles, http = kinds(edges, 'handles'), kinds(edges, 'http')
    nxt = 'e:web/app/api/users/[id]/route.ts:GET /api/users/:id'
    assert (nxt, 'f:web/app/api/users/[id]/route.ts:GET') in handles
    assert ('f:web/components/Profile.tsx:Profile', nxt) in http
    assert ('e:blog/urls.py:ANY /blog/:pk', 'f:blog/views.py:detail') in handles
    item = 'e:Catalog/CatalogApi.cs:GET /api/catalog/items/:id'
    assert (item, 'f:Catalog/CatalogApi.cs:CatalogApi.GetItem') in handles
    assert ('f:client/CatalogClient.cs:CatalogClient.Load', item) in http
    assert ('e:Ordering/OrdersController.cs:GET /api/Orders/:id', 'f:Ordering/OrdersController.cs:OrdersController.Get') in handles
    assert ('e:nest/cats.controller.ts:GET /cats/:id', 'f:nest/cats.controller.ts:CatsController.findOne') in handles


def test_ambiguous_clients_are_skipped(tmp_path):
    files = {
        'a/server.js': "const app = require('express')();\napp.get('/ping', function a() {});\n",
        'b/server.js': "const app = require('express')();\napp.get('/ping', function b() {});\n",
        'c/client.js': "export function ping() { return fetch('/ping'); }\n",
    }
    nodes, edges = run(tmp_path, files)
    assert 'e:a/server.js:GET /ping' in nodes and 'e:b/server.js:GET /ping' in nodes
    assert not kinds(edges, 'http')
