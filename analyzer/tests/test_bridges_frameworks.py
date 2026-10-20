"""Matriz de frameworks (bench/flows/FRAMEWORKS.md): un caso sintético mínimo por framework/librería soportado.

Cada caso declara un repo diminuto y los flujos que Córtex debe unir (ruta -> handler, cliente -> handler,
productor -> consumidor, código -> modelo/tabla, lectura -> definición de env, cableado de servicios).
"""
import pytest

from conftest import write_repo
from cortex_graph.analyze import analyze

VIA = ('endpoint', 'topic', 'variable')
KINDS = {'route': {'handles'}, 'http': {'http', 'handles'}, 'rpc': {'rpc', 'handles'}, 'event': {'event'},
         'data': {'data'}, 'env': {'env'}, 'service': {'depends'}}


def graph(tmp_path, files):
    out = analyze(write_repo(tmp_path / 'repo', files), git=False)
    keys = {n['id']: n['key'] for n in out['nodes']}
    nodes = {n['key']: n for n in out['nodes']}
    edges = {(keys[e['a']], keys[e['b']], e['kind']) for e in out['edges']}
    return nodes, edges


def linked(nodes, edges, kind, a, b):
    adj = {}
    for x, y, k in edges:
        if k in KINDS[kind]:
            adj.setdefault(x, set()).add(y)
            adj.setdefault(y, set()).add(x)
    if b in adj.get(a, ()):
        return True
    via = lambda n: nodes.get(n, {}).get('kind') in VIA or bool(nodes.get(n, {}).get('table'))
    return any(b in adj.get(n, ()) for n in adj.get(a, ()) if via(n))


def check(nodes, edges, exp):
    kind = exp[0]
    if kind == 'route':
        _, route, handler = exp
        eps = [k for k, n in nodes.items() if n.get('kind') == 'endpoint' and n.get('name') == route]
        return any((e, handler, 'handles') in edges for e in eps)
    if kind == 'env':
        _, reader, var, where = exp
        vid = f'v:{var}'
        return (reader, vid, 'env') in edges and any(b == vid and k == 'env' and nodes[a].get('file') == where for a, b, k in edges)
    _, a, b = exp
    return linked(nodes, edges, kind, a, b)


CASES = []


def case(name, group, files, *expect):
    CASES.append(pytest.param(files, expect, id=f'{group}:{name}'))


# ---------------------------------------------------------------- servidores HTTP / rutas

case('Flask', 'route', {
    'app.py': '''
        from flask import Flask
        app = Flask(__name__)

        @app.route('/users/<int:uid>', methods=['GET'])
        def get_user(uid):
            return {}
    ''',
}, ('route', 'GET /users/:uid', 'f:app.py:get_user'))

case('FastAPI', 'route', {
    'api/main.py': '''
        from fastapi import FastAPI
        from api import items
        app = FastAPI()
        app.include_router(items.router, prefix='/api')
    ''',
    'api/items.py': '''
        from fastapi import APIRouter
        router = APIRouter(prefix='/items')

        @router.get('/{item_id}')
        async def read_item(item_id: int):
            return {}
    ''',
}, ('route', 'GET /api/items/:item_id', 'f:api/items.py:read_item'))

case('Django', 'route', {
    'proj/urls.py': '''
        from django.urls import path, include
        urlpatterns = [path('blog/', include('blog.urls'))]
    ''',
    'blog/urls.py': '''
        from django.urls import path
        from . import views
        urlpatterns = [path('posts/<int:pk>/', views.post_detail)]
    ''',
    'blog/views.py': '''
        def post_detail(request, pk):
            return None
    ''',
}, ('route', 'ANY /blog/posts/:pk', 'f:blog/views.py:post_detail'))

case('Django REST Framework', 'route', {
    'api/urls.py': '''
        from rest_framework.routers import DefaultRouter
        from .views import ArticleViewSet
        router = DefaultRouter()
        router.register(r'articles', ArticleViewSet)
        urlpatterns = router.urls
    ''',
    'api/views.py': '''
        from rest_framework import viewsets
        class ArticleViewSet(viewsets.ModelViewSet):
            queryset = None
    ''',
}, ('route', 'GET /articles', 'c:api/views.py:ArticleViewSet'), ('route', 'DELETE /articles/:pk', 'c:api/views.py:ArticleViewSet'))

case('Starlette', 'route', {
    'app.py': '''
        from starlette.applications import Starlette
        from starlette.routing import Route

        async def homepage(request):
            return None

        app = Starlette(routes=[Route('/health', homepage, methods=['GET'])])
    ''',
}, ('route', 'GET /health', 'f:app.py:homepage'))

case('Litestar', 'route', {
    'app.py': '''
        from litestar import Litestar, get

        @get('/books/{book_id:int}')
        async def get_book(book_id: int) -> dict:
            return {}

        app = Litestar(route_handlers=[get_book])
    ''',
}, ('route', 'GET /books/:book_id', 'f:app.py:get_book'))

case('aiohttp', 'route', {
    'server.py': '''
        from aiohttp import web

        async def handle_list(request):
            return web.json_response([])

        app = web.Application()
        app.router.add_get('/orders', handle_list)
    ''',
}, ('route', 'GET /orders', 'f:server.py:handle_list'))

case('Express', 'route', {
    'server.js': '''
        const express = require('express');
        const users = require('./routes/users');
        const app = express();
        app.use('/api/users', users);
    ''',
    'routes/users.js': '''
        const express = require('express');
        const router = express.Router();
        function listUsers(req, res) { res.json([]); }
        router.get('/:id', listUsers);
        module.exports = router;
    ''',
}, ('route', 'GET /api/users/:id', 'f:routes/users.js:listUsers'))

case('Fastify', 'route', {
    'server.ts': '''
        import Fastify from 'fastify';
        const fastify = Fastify();
        async function getPet(request, reply) { return {}; }
        fastify.get('/pets/:id', getPet);
    ''',
}, ('route', 'GET /pets/:id', 'f:server.ts:getPet'))

case('Koa', 'route', {
    'app.js': '''
        const Router = require('@koa/router');
        const router = new Router();
        async function showCart(ctx) { ctx.body = {}; }
        router.get('/cart', showCart);
    ''',
}, ('route', 'GET /cart', 'f:app.js:showCart'))

case('Hapi', 'route', {
    'server.js': '''
        const Hapi = require('@hapi/hapi');
        const server = Hapi.server({ port: 3000 });
        function listTodos(request, h) { return []; }
        server.route({ method: 'GET', path: '/todos', handler: listTodos });
    ''',
}, ('route', 'GET /todos', 'f:server.js:listTodos'))

case('NestJS', 'route', {
    'src/cats.controller.ts': '''
        import { Controller, Get, Param } from '@nestjs/common';

        @Controller('cats')
        export class CatsController {
          @Get(':id')
          findOne(@Param('id') id: string) {
            return id;
          }
        }
    ''',
}, ('route', 'GET /cats/:id', 'f:src/cats.controller.ts:CatsController.findOne'))

case('Next.js app router', 'route', {
    'app/api/projects/[id]/route.ts': '''
        export async function GET(request: Request) {
          return Response.json({});
        }
    ''',
}, ('route', 'GET /api/projects/:id', 'f:app/api/projects/[id]/route.ts:GET'))

case('Next.js pages API', 'route', {
    'pages/api/hello.ts': '''
        export default function handler(req, res) {
          res.status(200).json({});
        }
    ''',
}, ('route', 'ANY /api/hello', 'f:pages/api/hello.ts:handler'))

case('Nuxt server routes', 'route', {
    'nuxt.config.ts': '''
        export default defineNuxtConfig({});
    ''',
    'server/api/todos.get.ts': '''
        export default defineEventHandler(() => []);
    ''',
}, ('route', 'GET /api/todos', 'm:server/api/todos.get.ts'))

case('SvelteKit endpoints', 'route', {
    'src/routes/api/items/+server.ts': '''
        export async function POST({ request }) {
          return new Response('ok');
        }
    ''',
}, ('route', 'POST /api/items', 'f:src/routes/api/items/+server.ts:POST'))

case('Remix', 'route', {
    'app/routes/notes.$noteId.tsx': '''
        export async function loader({ params }) {
          return null;
        }
        export async function action({ request }) {
          return null;
        }
    ''',
}, ('route', 'GET /notes/:noteId', 'f:app/routes/notes.$noteId.tsx:loader'),
    ('route', 'POST /notes/:noteId', 'f:app/routes/notes.$noteId.tsx:action'))

case('Astro endpoints', 'route', {
    'src/pages/api/feed.json.ts': '''
        export async function GET({ params }) {
          return new Response('[]');
        }
    ''',
}, ('route', 'GET /api/feed.json', 'f:src/pages/api/feed.json.ts:GET'))

case('gin', 'route', {
    'main.go': '''
        package main

        import "github.com/gin-gonic/gin"

        func listAlbums(c *gin.Context) {}

        func main() {
            r := gin.Default()
            v1 := r.Group("/v1")
            v1.GET("/albums", listAlbums)
        }
    ''',
}, ('route', 'GET /v1/albums', 'f:main.go:listAlbums'))

case('echo', 'route', {
    'main.go': '''
        package main

        import "github.com/labstack/echo/v4"

        func getUser(c echo.Context) error { return nil }

        func main() {
            e := echo.New()
            e.GET("/users/:id", getUser)
        }
    ''',
}, ('route', 'GET /users/:id', 'f:main.go:getUser'))

case('fiber', 'route', {
    'main.go': '''
        package main

        import "github.com/gofiber/fiber/v2"

        func createBook(c *fiber.Ctx) error { return nil }

        func main() {
            app := fiber.New()
            api := app.Group("/api")
            api.Post("/books", createBook)
        }
    ''',
}, ('route', 'POST /api/books', 'f:main.go:createBook'))

case('chi', 'route', {
    'main.go': '''
        package main

        import "github.com/go-chi/chi/v5"

        func listArticles(w http.ResponseWriter, r *http.Request) {}

        func main() {
            r := chi.NewRouter()
            r.Route("/articles", func(r chi.Router) {
                r.Get("/", listArticles)
            })
        }
    ''',
}, ('route', 'GET /articles', 'f:main.go:listArticles'))

case('gorilla/mux', 'route', {
    'main.go': '''
        package main

        import "github.com/gorilla/mux"

        func getProduct(w http.ResponseWriter, r *http.Request) {}

        func main() {
            r := mux.NewRouter()
            r.HandleFunc("/products/{id}", getProduct).Methods("GET")
        }
    ''',
}, ('route', 'GET /products/:id', 'f:main.go:getProduct'))

case('net/http ServeMux', 'route', {
    'main.go': '''
        package main

        import "net/http"

        func getTask(w http.ResponseWriter, r *http.Request) {}

        func main() {
            mux := http.NewServeMux()
            mux.HandleFunc("GET /tasks/{id}", getTask)
        }
    ''',
}, ('route', 'GET /tasks/:id', 'f:main.go:getTask'))

case('Spring MVC', 'route', {
    'src/main/java/demo/OwnerController.java': '''
        package demo;

        @RestController
        @RequestMapping("/owners")
        public class OwnerController {
            @GetMapping("/{ownerId}")
            public Owner findOwner(@PathVariable int ownerId) {
                return null;
            }
        }
    ''',
}, ('route', 'GET /owners/:ownerId', 'f:src/main/java/demo/OwnerController.java:OwnerController.findOwner'))

case('Spring WebFlux functional', 'route', {
    'src/main/java/demo/Routes.java': '''
        package demo;

        @Configuration
        public class Routes {
            @Bean
            public RouterFunction<ServerResponse> routes(PetHandler handler) {
                return route().GET("/pets", handler::listPets).build();
            }
        }
    ''',
    'src/main/java/demo/PetHandler.java': '''
        package demo;

        @Component
        public class PetHandler {
            public Mono<ServerResponse> listPets(ServerRequest request) {
                return null;
            }
        }
    ''',
}, ('route', 'GET /pets', 'f:src/main/java/demo/PetHandler.java:PetHandler.listPets'))

case('Micronaut', 'route', {
    'src/main/java/demo/HelloController.java': '''
        package demo;

        @Controller("/hello")
        public class HelloController {
            @Get("/{name}")
            public String greet(String name) {
                return name;
            }
        }
    ''',
}, ('route', 'GET /hello/:name', 'f:src/main/java/demo/HelloController.java:HelloController.greet'))

case('JAX-RS / Quarkus', 'route', {
    'src/main/java/demo/FruitResource.java': '''
        package demo;

        @Path("/fruits")
        public class FruitResource {
            @GET
            @Path("/{id}")
            public Fruit get(Long id) {
                return null;
            }
        }
    ''',
}, ('route', 'GET /fruits/:id', 'f:src/main/java/demo/FruitResource.java:FruitResource.get'))

case('OpenAPI spec (generated server interfaces)', 'route', {
    'svc/src/main/resources/openapi.yml': '''
        openapi: 3.0.3
        info:
          title: Pets
          version: "1"
        paths:
          /api/pets:
            get:
              tags:
              - pets
              operationId: listPets
            post:
              tags:
              - pets
              operationId: createPet
    ''',
    'svc/src/main/java/demo/PetResource.java': '''
        package demo;

        public class PetResource implements PetsApi {
            @Override
            public List<Pet> listPets() {
                return null;
            }

            @Override
            public Pet createPet(Pet pet) {
                return pet;
            }
        }
    ''',
    'svc/pom.xml': '<project/>',
}, ('route', 'GET /api/pets', 'f:svc/src/main/java/demo/PetResource.java:PetResource.listPets'))

case('Ktor', 'route', {
    'src/main/kotlin/Routing.kt': '''
        import io.ktor.server.routing.*

        fun Application.configureRouting() {
            routing {
                route("/customers") {
                    get("{id}") {
                        call.respondText("ok")
                    }
                }
            }
        }
    ''',
}, ('route', 'GET /customers/:id', 'f:src/main/kotlin/Routing.kt:configureRouting'))

case('Javalin', 'route', {
    'src/main/java/demo/App.java': '''
        package demo;

        public class App {
            public static void main(String[] args) {
                var app = Javalin.create();
                app.get("/users/{id}", UserController::getOne);
            }
        }
    ''',
    'src/main/java/demo/UserController.java': '''
        package demo;

        public class UserController {
            public static void getOne(Context ctx) {}
        }
    ''',
}, ('route', 'GET /users/:id', 'f:src/main/java/demo/UserController.java:UserController.getOne'))

case('Vert.x Web', 'route', {
    'src/main/java/demo/MainVerticle.java': '''
        package demo;

        public class MainVerticle extends AbstractVerticle {
            @Override
            public void start() {
                Router router = Router.router(vertx);
                router.get("/products/:id").handler(this::handleGetProduct);
            }

            private void handleGetProduct(RoutingContext ctx) {}
        }
    ''',
}, ('route', 'GET /products/:id', 'f:src/main/java/demo/MainVerticle.java:MainVerticle.handleGetProduct'))

case('ASP.NET Core controllers', 'route', {
    'Api/Controllers/OrdersController.cs': '''
        [ApiController]
        [Route("api/[controller]")]
        public class OrdersController : ControllerBase
        {
            [HttpGet("{id}")]
            public IActionResult Get(int id) => Ok();
        }
    ''',
}, ('route', 'GET /api/Orders/:id', 'f:Api/Controllers/OrdersController.cs:OrdersController.Get'))

case('ASP.NET Core minimal APIs', 'route', {
    'Api/Program.cs': '''
        var app = WebApplication.Create(args);
        var todos = app.MapGroup("/todos");
        todos.MapGet("/{id}", TodoEndpoints.GetTodo);
    ''',
    'Api/TodoEndpoints.cs': '''
        public static class TodoEndpoints
        {
            public static IResult GetTodo(int id) => TypedResults.Ok();
        }
    ''',
}, ('route', 'GET /todos/:id', 'f:Api/TodoEndpoints.cs:TodoEndpoints.GetTodo'))

case('Laravel', 'route', {
    'routes/api.php': '''
        <?php
        use App\\Http\\Controllers\\PostController;
        Route::get('/posts/{post}', [PostController::class, 'show']);
    ''',
    'app/Http/Controllers/PostController.php': '''
        <?php
        namespace App\\Http\\Controllers;
        class PostController extends Controller
        {
            public function show($post) { return $post; }
        }
    ''',
}, ('route', 'GET /api/posts/:post', 'f:app/Http/Controllers/PostController.php:PostController.show'))

case('Symfony', 'route', {
    'src/Controller/BlogController.php': '''
        <?php
        namespace App\\Controller;

        class BlogController extends AbstractController
        {
            #[Route('/blog/{slug}', methods: ['GET'])]
            public function show(string $slug): Response
            {
                return new Response();
            }
        }
    ''',
}, ('route', 'GET /blog/:slug', 'f:src/Controller/BlogController.php:BlogController.show'))

case('Slim', 'route', {
    'public/index.php': '''
        <?php
        $app = AppFactory::create();
        $app->get('/hello/{name}', [HelloAction::class, 'greet']);
    ''',
    'src/HelloAction.php': '''
        <?php
        class HelloAction
        {
            public function greet($request, $response, $args) { return $response; }
        }
    ''',
}, ('route', 'GET /hello/:name', 'f:src/HelloAction.php:HelloAction.greet'))

case('Rails', 'route', {
    'config/routes.rb': '''
        Rails.application.routes.draw do
          resources :articles, only: [:show]
        end
    ''',
    'app/controllers/articles_controller.rb': '''
        class ArticlesController < ApplicationController
          def show
          end
        end
    ''',
}, ('route', 'GET /articles/:id', 'f:app/controllers/articles_controller.rb:ArticlesController.show'))

case('Sinatra', 'route', {
    'app.rb': '''
        require 'sinatra'

        get '/status' do
          'ok'
        end
    ''',
}, ('route', 'GET /status', 'm:app.rb'))

case('Hanami 2', 'route', {
    'config/routes.rb': '''
        module Shop
          class Routes < Hanami::Routes
            scope "api" do
              get "/books/:id", to: "books.show"
            end
          end
        end
    ''',
    'app/actions/books/show.rb': '''
        module Shop
          module Actions
            module Books
              class Show < Shop::Action
                def handle(request, response)
                end
              end
            end
          end
        end
    ''',
}, ('route', 'GET /api/books/:id', 'c:app/actions/books/show.rb:Show'))

case('Grape', 'route', {
    'app/api/twitter.rb': '''
        module Twitter
          class API < Grape::API
            prefix :api
            resource :statuses do
              get :public_timeline do
                Status.limit(20)
              end
            end
          end
        end
    ''',
}, ('route', 'GET /api/statuses/public_timeline', 'c:app/api/twitter.rb:API'))

case('axum', 'route', {
    'src/main.rs': '''
        use axum::{routing::get, Router};

        async fn list_users() -> &'static str { "[]" }

        fn app() -> Router {
            Router::new().route("/users", get(list_users))
        }
    ''',
}, ('route', 'GET /users', 'f:src/main.rs:list_users'))

case('actix-web', 'route', {
    'src/main.rs': '''
        use actix_web::{get, web, App};

        #[get("/items/{id}")]
        async fn get_item(path: web::Path<u32>) -> String { String::new() }
    ''',
}, ('route', 'GET /items/:id', 'f:src/main.rs:get_item'))

case('Rocket', 'route', {
    'src/main.rs': '''
        #[macro_use] extern crate rocket;

        #[get("/hello/<name>")]
        fn hello(name: &str) -> String { name.to_string() }

        #[launch]
        fn rocket() -> _ {
            rocket::build().mount("/api", routes![hello])
        }
    ''',
}, ('route', 'GET /api/hello/:name', 'f:src/main.rs:hello'))

case('warp', 'route', {
    'src/main.rs': '''
        use warp::Filter;

        async fn list_todos() -> Result<impl warp::Reply, warp::Rejection> { Ok("[]") }

        fn routes() {
            let todos = warp::path!("todos").and(warp::get()).and_then(list_todos);
        }
    ''',
}, ('route', 'GET /todos', 'f:src/main.rs:list_todos'))

case('Phoenix', 'route', {
    'lib/app_web/router.ex': '''
        defmodule AppWeb.Router do
          use Phoenix.Router

          scope "/api", AppWeb do
            get "/users/:id", UserController, :show
          end
        end
    ''',
    'lib/app_web/controllers/user_controller.ex': '''
        defmodule AppWeb.UserController do
          def show(conn, %{"id" => id}) do
            conn
          end
        end
    ''',
}, ('route', 'GET /api/users/:id', 'f:lib/app_web/controllers/user_controller.ex:AppWeb.UserController.show'))

case('Plug.Router', 'route', {
    'lib/my_router.ex': '''
        defmodule MyRouter do
          use Plug.Router

          get "/ping" do
            send_resp(conn, 200, "pong")
          end
        end
    ''',
}, ('route', 'GET /ping', 'c:lib/my_router.ex:MyRouter'))

case('dart_frog', 'route', {
    'routes/api/todos/index.dart': '''
        Future<Response> onRequest(RequestContext context) async {
          switch (context.request.method) {
            case HttpMethod.get:
              return _list(context);
            default:
              return Response(statusCode: 405);
          }
        }

        Future<Response> _list(RequestContext context) async => Response.json(body: []);
    ''',
}, ('route', 'GET /api/todos', 'f:routes/api/todos/index.dart:_list'))

case('shelf_router', 'route', {
    'bin/server.dart': '''
        import 'package:shelf_router/shelf_router.dart';

        Response _echo(Request request) => Response.ok('');

        void main() {
          final router = Router()..get('/echo/<message>', _echo);
        }
    ''',
}, ('route', 'GET /echo/:message', 'f:bin/server.dart:_echo'))

case('Vapor', 'route', {
    'Sources/App/routes.swift': '''
        import Vapor

        func routes(_ app: Application) throws {
            app.get("hello", ":name") { req async -> String in
                "Hello"
            }
        }
    ''',
}, ('route', 'GET /hello/:name', 'f:Sources/App/routes.swift:routes'))

case('Play Framework', 'route', {
    'conf/routes': '''
        GET     /clients/:id          controllers.Clients.show(id: Long)
    ''',
    'app/controllers/Clients.scala': '''
        package controllers

        class Clients @Inject()(cc: ControllerComponents) extends AbstractController(cc) {
          def show(id: Long) = Action { Ok("") }
        }
    ''',
}, ('route', 'GET /clients/:id', 'f:app/controllers/Clients.scala:Clients.show'))

# ---------------------------------------------------------------- clientes HTTP (contra una ruta del mismo repo)

SERVER = {
    'server/app.py': '''
        from fastapi import FastAPI
        app = FastAPI()

        @app.get('/api/orders/{order_id}')
        def get_order(order_id: int):
            return {}

        @app.post('/api/orders')
        def create_order():
            return {}
    ''',
}
GET_ORDER, CREATE_ORDER = 'f:server/app.py:get_order', 'f:server/app.py:create_order'


def client(name, files, *expect):
    case(name, 'http', {**SERVER, **files}, *expect)


client('fetch', {
    'web/api.ts': '''
        export async function loadOrder(id: string) {
          const res = await fetch(`/api/orders/${id}`);
          return res.json();
        }
    ''',
}, ('http', 'f:web/api.ts:loadOrder', GET_ORDER))

client('axios', {
    'web/api.js': '''
        import axios from 'axios';
        export function saveOrder(body) {
          return axios.post('/api/orders', body);
        }
    ''',
}, ('http', 'f:web/api.js:saveOrder', CREATE_ORDER))

client('ky', {
    'web/api.ts': '''
        import ky from 'ky';
        export const api = ky.create({ prefixUrl: '/api' });
        export function getOrder(id) {
          return api.get(`orders/${id}`).json();
        }
    ''',
}, ('http', 'f:web/api.ts:getOrder', GET_ORDER))

client('ofetch / $fetch', {
    'web/composables/orders.ts': '''
        export async function orderById(id: string) {
          return await $fetch(`/api/orders/${id}`);
        }
    ''',
}, ('http', 'f:web/composables/orders.ts:orderById', GET_ORDER))

client('Angular HttpClient', {
    'web/src/app/order.service.ts': '''
        @Injectable({ providedIn: 'root' })
        export class OrderService {
          constructor(private http: HttpClient) {}
          getOrder(id: string) {
            return this.http.get<Order>(`/api/orders/${id}`);
          }
        }
    ''',
}, ('http', 'f:web/src/app/order.service.ts:OrderService.getOrder', GET_ORDER))

client('XMLHttpRequest / EventSource', {
    'web/upload.ts': '''
        export function upload(body) {
          const xhr = new XMLHttpRequest();
          xhr.open('POST', '/api/orders');
          xhr.send(body);
        }
        export function follow(id) {
          return new EventSource(`/api/orders/${id}`);
        }
    ''',
}, ('http', 'f:web/upload.ts:upload', CREATE_ORDER), ('http', 'f:web/upload.ts:follow', GET_ORDER))

client('React Query wrapper', {
    'web/hooks.ts': '''
        import { useQuery } from '@tanstack/react-query';
        import axios from 'axios';
        export function useOrder(id: string) {
          return useQuery({ queryKey: ['order', id], queryFn: () => axios.get(`/api/orders/${id}`) });
        }
    ''',
}, ('http', 'f:web/hooks.ts:useOrder', GET_ORDER))

client('requests', {
    'worker/sync.py': '''
        import requests
        BASE = 'http://server:8000'

        def pull(order_id):
            return requests.get(f'{BASE}/api/orders/{order_id}').json()
    ''',
}, ('http', 'f:worker/sync.py:pull', GET_ORDER))

client('httpx', {
    'worker/client.py': '''
        import httpx

        async def push(payload):
            async with httpx.AsyncClient(base_url='http://server:8000') as client:
                return await client.post('/api/orders', json=payload)
    ''',
}, ('http', 'f:worker/client.py:push', CREATE_ORDER))

client('aiohttp client', {
    'worker/fetcher.py': '''
        import aiohttp

        async def fetch_order(session, order_id):
            async with session.get(f'http://server/api/orders/{order_id}') as resp:
                return await resp.json()
    ''',
}, ('http', 'f:worker/fetcher.py:fetch_order', GET_ORDER))

client('OkHttp', {
    'android/src/main/java/demo/Api.java': '''
        package demo;

        public class Api {
            private final OkHttpClient client = new OkHttpClient();

            public String order(String id) throws IOException {
                Request request = new Request.Builder().url(BASE_URL + "/api/orders/" + id).build();
                return client.newCall(request).execute().body().string();
            }
        }
    ''',
}, ('http', 'f:android/src/main/java/demo/Api.java:Api.order', GET_ORDER))

client('Retrofit', {
    'android/src/main/java/demo/OrderService.kt': '''
        interface OrderService {
            @GET("/api/orders/{id}")
            suspend fun getOrder(@Path("id") id: String): Order
        }
    ''',
    'android/src/main/java/demo/OrderRepository.kt': '''
        class OrderRepository(private val service: OrderService) {
            suspend fun load(id: String) = service.getOrder(id)
        }
    ''',
}, ('http', 'f:android/src/main/java/demo/OrderService.kt:OrderService.getOrder', GET_ORDER),
    ('http', 'f:android/src/main/java/demo/OrderRepository.kt:OrderRepository.load', GET_ORDER))

client('OpenFeign', {
    'svc/src/main/java/demo/OrderClient.java': '''
        package demo;

        @FeignClient(name = "orders")
        public interface OrderClient {
            @GetMapping("/api/orders/{id}")
            Order find(@PathVariable("id") String id);
        }
    ''',
}, ('http', 'f:svc/src/main/java/demo/OrderClient.java:OrderClient.find', GET_ORDER))

client('Spring WebClient / RestClient', {
    'svc/src/main/java/demo/Gateway.java': '''
        package demo;

        public class Gateway {
            public Mono<Order> order(String id) {
                return webClient.get().uri("/api/orders/{id}", id).retrieve().bodyToMono(Order.class);
            }
            public Order create(Order o) {
                return restClient.post().uri("/api/orders").body(o).retrieve().body(Order.class);
            }
        }
    ''',
}, ('http', 'f:svc/src/main/java/demo/Gateway.java:Gateway.order', GET_ORDER),
    ('http', 'f:svc/src/main/java/demo/Gateway.java:Gateway.create', CREATE_ORDER))

client('MicroProfile REST Client', {
    'svc/src/main/java/demo/OrderRestClient.java': '''
        package demo;

        @Path("/api/orders")
        @RegisterRestClient(configKey = "orders")
        public interface OrderRestClient {
            @GET
            @Path("/{id}")
            Order get(@PathParam("id") String id);
        }
    ''',
}, ('http', 'f:svc/src/main/java/demo/OrderRestClient.java:OrderRestClient.get', GET_ORDER))

client('JAX-RS client (WebTarget)', {
    'svc/src/main/java/demo/OrderTarget.java': '''
        package demo;

        public class OrderTarget {
            private final WebTarget target;

            public OrderTarget() {
                this.target = ClientBuilder.newClient().target(baseUrl).path("api/orders");
            }

            public Order find(String id) {
                return this.target.path(id).request().get(Order.class);
            }
        }
    ''',
}, ('http', 'f:svc/src/main/java/demo/OrderTarget.java:OrderTarget.find', GET_ORDER))

client('.NET HttpClient', {
    'Web/OrdersApi.cs': '''
        public class OrdersApi(HttpClient http)
        {
            public Task<Order?> Get(int id) => http.GetFromJsonAsync<Order>($"/api/orders/{id}");
        }
    ''',
}, ('http', 'f:Web/OrdersApi.cs:OrdersApi.Get', GET_ORDER))

client('Refit', {
    'Web/IOrdersApi.cs': '''
        public interface IOrdersApi
        {
            [Get("/api/orders/{id}")]
            Task<Order> GetOrder(int id);
        }
    ''',
}, ('http', 'f:Web/IOrdersApi.cs:IOrdersApi.GetOrder', GET_ORDER))

client('Guzzle / Laravel Http', {
    'app/Services/Orders.php': '''
        <?php
        class Orders
        {
            public function create($data)
            {
                return Http::post('http://server/api/orders', $data);
            }
        }
    ''',
}, ('http', 'f:app/Services/Orders.php:Orders.create', CREATE_ORDER))

client('Faraday / HTTParty', {
    'lib/orders_client.rb': '''
        class OrdersClient
          def fetch(id)
            HTTParty.get("http://server/api/orders/#{id}")
          end
        end
    ''',
}, ('http', 'f:lib/orders_client.rb:OrdersClient.fetch', GET_ORDER))

client('reqwest', {
    'cli/src/main.rs': '''
        async fn fetch_order(client: &reqwest::Client, id: u32) -> reqwest::Result<String> {
            client.get(format!("http://server/api/orders/{}", id)).send().await?.text().await
        }
    ''',
}, ('http', 'f:cli/src/main.rs:fetch_order', GET_ORDER))

client('gloo-net / Yew', {
    'front/src/api.rs': '''
        use gloo_net::http::Request;

        pub async fn load_order(id: u32) -> String {
            Request::get(&format!("/api/orders/{}", id)).send().await.unwrap().text().await.unwrap()
        }
    ''',
}, ('http', 'f:front/src/api.rs:load_order', GET_ORDER))

client('dio (Dart)', {
    'app/lib/orders_repo.dart': '''
        class OrdersRepo {
          final Dio dio;
          OrdersRepo(this.dio);

          Future<Response> create(Map body) => dio.post('/api/orders', data: body);
        }
    ''',
}, ('http', 'f:app/lib/orders_repo.dart:OrdersRepo.create', CREATE_ORDER))

client('package:http (Dart)', {
    'app/lib/orders_http.dart': '''
        import 'package:http/http.dart' as http;

        Future<http.Response> fetchOrder(String id) => http.get(Uri.parse('$baseUrl/api/orders/$id'));
    ''',
}, ('http', 'f:app/lib/orders_http.dart:fetchOrder', GET_ORDER))

client('Alamofire', {
    'ios/Orders.swift': '''
        import Alamofire

        func loadOrder(id: String) {
            AF.request("\\(baseURL)/api/orders/\\(id)").responseDecodable(of: Order.self) { _ in }
        }
    ''',
}, ('http', 'f:ios/Orders.swift:loadOrder', GET_ORDER))

client('URLSession', {
    'ios/OrderService.swift': '''
        func createOrder() async throws {
            var request = URLRequest(url: URL(string: "https://server/api/orders")!)
            request.httpMethod = "POST"
            let (_, _) = try await URLSession.shared.data(for: request)
        }
    ''',
}, ('http', 'f:ios/OrderService.swift:createOrder', CREATE_ORDER))

client('Ktor client', {
    'shared/src/commonMain/kotlin/OrderApi.kt': '''
        class OrderApi(private val client: HttpClient) {
            suspend fun order(id: String): Order = client.get("$base/api/orders/$id").body()
        }
    ''',
}, ('http', 'f:shared/src/commonMain/kotlin/OrderApi.kt:OrderApi.order', GET_ORDER))

client('Apollo / GraphQL client', {
    'server/schema.graphql': '''
        type Query {
          order(id: ID!): Order
        }
    ''',
    'server/resolvers.js': '''
        const resolvers = {
          Query: {
            order: (_, { id }) => findOrder(id),
          },
        };
        module.exports = resolvers;
    ''',
    'web/queries.js': '''
        import { gql, useQuery } from '@apollo/client';
        const ORDER = gql`
          query Order($id: ID!) {
            order(id: $id) { id }
          }
        `;
        export function useOrderQuery(id) {
          return useQuery(ORDER, { variables: { id } });
        }
    ''',
}, ('http', 'f:web/queries.js:useOrderQuery', 'm:server/resolvers.js'))

case('tRPC', 'http', {
    'server/router.ts': '''
        import { initTRPC } from '@trpc/server';
        const t = initTRPC.create();
        export const appRouter = t.router({
          greeting: t.procedure.query(() => 'hi'),
        });
    ''',
    'web/hello.tsx': '''
        import { trpc } from './trpc';
        export function Hello() {
          const q = trpc.greeting.useQuery();
          return q.data;
        }
    ''',
}, ('http', 'f:web/hello.tsx:Hello', 'm:server/router.ts'))

# ---------------------------------------------------------------- RPC

PROTO = {
    'proto/orders.proto': '''
        syntax = "proto3";
        package shop;
        service Orders {
          rpc GetOrder (GetOrderRequest) returns (Order) {}
        }
    ''',
}


def rpc(name, files, *expect):
    case(name, 'rpc', {**PROTO, **files}, *expect)


rpc('gRPC Go', {
    'svc/server.go': '''
        package svc

        type server struct {
            pb.UnimplementedOrdersServer
        }

        func (s *server) GetOrder(ctx context.Context, in *pb.GetOrderRequest) (*pb.Order, error) { return nil, nil }
    ''',
    'web/client.go': '''
        package web

        func load(conn *grpc.ClientConn) {
            c := pb.NewOrdersClient(conn)
            c.GetOrder(ctx, &pb.GetOrderRequest{})
        }
    ''',
}, ('rpc', 'f:web/client.go:load', 'f:svc/server.go:server.GetOrder'))

rpc('gRPC Python', {
    'svc/server.py': '''
        class OrdersServicer(orders_pb2_grpc.OrdersServicer):
            def GetOrder(self, request, context):
                return None
    ''',
    'web/client.py': '''
        def load(channel):
            stub = orders_pb2_grpc.OrdersStub(channel)
            return stub.GetOrder(req)
    ''',
}, ('rpc', 'f:web/client.py:load', 'f:svc/server.py:OrdersServicer.GetOrder'))

rpc('gRPC Java / Kotlin', {
    'svc/src/main/kotlin/OrdersService.kt': '''
        @GrpcService
        class OrdersService : OrdersImplBase() {
            override fun getOrder(request: GetOrderRequest, observer: StreamObserver<Order>) {}
        }
    ''',
    'web/src/main/java/demo/OrderGateway.java': '''
        package demo;

        public class OrderGateway {
            @GrpcClient("orders")
            OrdersGrpc.OrdersBlockingStub stub;

            public Order get() {
                return stub.getOrder(GetOrderRequest.newBuilder().build());
            }
        }
    ''',
}, ('rpc', 'f:web/src/main/java/demo/OrderGateway.java:OrderGateway.get', 'f:svc/src/main/kotlin/OrdersService.kt:OrdersService.getOrder'))

rpc('gRPC .NET', {
    'Svc/OrdersService.cs': '''
        public class OrdersService : Orders.OrdersBase
        {
            public override Task<Order> GetOrder(GetOrderRequest request, ServerCallContext context) => null;
        }
    ''',
    'Web/OrderClient.cs': '''
        public class OrderClient(Orders.OrdersClient client)
        {
            public Task<Order> Load() => client.GetOrderAsync(new GetOrderRequest()).ResponseAsync;
        }
    ''',
}, ('rpc', 'f:Web/OrderClient.cs:OrderClient.Load', 'f:Svc/OrdersService.cs:OrdersService.GetOrder'))

rpc('gRPC Node', {
    'svc/server.js': '''
        function getOrder(call, callback) { callback(null, {}); }
        server.addService(shop.Orders.service, { getOrder: getOrder });
    ''',
}, ('rpc', 'e:proto/orders.proto:RPC shop.Orders/GetOrder', 'f:svc/server.js:getOrder'))

rpc('tonic (Rust)', {
    'svc/src/main.rs': '''
        use tonic::{Request, Response, Status};

        pub struct MyOrders;

        #[tonic::async_trait]
        impl Orders for MyOrders {
            async fn get_order(&self, request: Request<GetOrderRequest>) -> Result<Response<Order>, Status> { todo!() }
        }
    ''',
}, ('rpc', 'e:proto/orders.proto:RPC shop.Orders/GetOrder', 'f:svc/src/main.rs:MyOrders.get_order'))

# ---------------------------------------------------------------- mensajería / colas / eventos

case('Kafka (Spring)', 'event', {
    'orders/src/main/java/demo/OrderService.java': '''
        package demo;

        public class OrderService {
            public void place(Order o) {
                kafkaTemplate.send("order-placed", o);
            }
        }
    ''',
    'notify/src/main/java/demo/Listener.java': '''
        package demo;

        public class Listener {
            @KafkaListener(topics = "order-placed")
            public void onOrder(Order o) {}
        }
    ''',
}, ('event', 'f:orders/src/main/java/demo/OrderService.java:OrderService.place', 'f:notify/src/main/java/demo/Listener.java:Listener.onOrder'))

case('Kafka (kafkajs)', 'event', {
    'producer.js': '''
        async function publish(producer, order) {
          await producer.send({ topic: 'orders', messages: [{ value: JSON.stringify(order) }] });
        }
    ''',
    'consumer.js': '''
        async function start(consumer) {
          await consumer.subscribe({ topic: 'orders' });
        }
    ''',
}, ('event', 'f:producer.js:publish', 'f:consumer.js:start'))

case('Kafka (SmallRye / MicroProfile)', 'event', {
    'a/src/main/java/demo/Emitters.java': '''
        package demo;

        public class Emitters {
            @Inject
            @Channel("prices-out")
            Emitter<Double> emitter;

            public void send(double p) {
                emitter.send(p);
            }
        }
    ''',
    'a/src/main/resources/application.properties': '''
        mp.messaging.outgoing.prices-out.topic=prices
    ''',
    'b/src/main/java/demo/PriceConsumer.java': '''
        package demo;

        public class PriceConsumer {
            @Incoming("prices-in")
            public void consume(double price) {}
        }
    ''',
    'b/src/main/resources/application.properties': '''
        mp.messaging.incoming.prices-in.topic=prices
    ''',
}, ('event', 'f:a/src/main/java/demo/Emitters.java:Emitters.send', 'f:b/src/main/java/demo/PriceConsumer.java:PriceConsumer.consume'))

case('RabbitMQ (amqplib / pika)', 'event', {
    'api/publisher.js': '''
        async function enqueue(channel, task) {
          channel.sendToQueue('tasks', Buffer.from(JSON.stringify(task)));
        }
    ''',
    'worker/consumer.py': '''
        def on_message(ch, method, properties, body):
            pass

        def main(channel):
            channel.basic_consume(queue='tasks', on_message_callback=on_message)
    ''',
}, ('event', 'f:api/publisher.js:enqueue', 'f:worker/consumer.py:main'))

case('AWS SQS', 'event', {
    'api/jobs.py': '''
        def submit(sqs, body):
            sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=body)
    ''',
    'api/config.py': '''
        QUEUE_URL = 'https://sqs.us-east-1.amazonaws.com/123/thumbnails'
    ''',
    'worker/handler.py': '''
        def poll(sqs):
            sqs.receive_message(QueueUrl='https://sqs.us-east-1.amazonaws.com/123/thumbnails')
    ''',
}, ('event', 'f:api/jobs.py:submit', 'f:worker/handler.py:poll'))

case('NATS', 'event', {
    'pub/main.go': '''
        package main

        func announce(nc *nats.Conn) {
            nc.Publish("orders.created", []byte("x"))
        }
    ''',
    'sub/main.go': '''
        package main

        func listen(nc *nats.Conn) {
            nc.Subscribe("orders.created", func(m *nats.Msg) {})
        }
    ''',
}, ('event', 'f:pub/main.go:announce', 'f:sub/main.go:listen'))

case('Redis pub/sub', 'event', {
    'worker/progress.py': '''
        def report(r, task_id, data):
            r.publish(f"progress:{task_id}", data)
    ''',
    'api/stream.py': '''
        async def follow(redis, task_id):
            channel = f"progress:{task_id}"
            pubsub = redis.pubsub()
            await pubsub.subscribe(channel)
    ''',
}, ('event', 'f:worker/progress.py:report', 'f:api/stream.py:follow'))

case('Redis streams', 'event', {
    'api/events.js': '''
        async function emitSignup(redis, user) {
          await redis.xadd('signups', '*', 'id', user.id);
        }
    ''',
    'worker/consume.js': '''
        async function loop(redis) {
          await redis.xreadgroup('GROUP', 'g', 'c', 'STREAMS', 'signups', '>');
        }
    ''',
}, ('event', 'f:api/events.js:emitSignup', 'f:worker/consume.js:loop'))

case('Celery', 'event', {
    'worker/tasks.py': '''
        from celery import shared_task

        @shared_task(name='reports.build')
        def build_report(report_id):
            pass
    ''',
    'api/views.py': '''
        from worker.tasks import build_report

        def request_report(rid):
            build_report.delay(rid)
    ''',
}, ('event', 'f:api/views.py:request_report', 'f:worker/tasks.py:build_report'))

case('RQ', 'event', {
    'jobs.py': '''
        def resize_image(path):
            pass
    ''',
    'web.py': '''
        from rq import Queue
        from jobs import resize_image

        def upload(q, path):
            q.enqueue(resize_image, path)
    ''',
}, ('event', 'f:web.py:upload', 'f:jobs.py:resize_image'))

case('Dramatiq', 'event', {
    'tasks.py': '''
        import dramatiq

        @dramatiq.actor
        def send_welcome(user_id):
            pass
    ''',
    'signup.py': '''
        from tasks import send_welcome

        def register(uid):
            send_welcome.send(uid)
    ''',
}, ('event', 'f:signup.py:register', 'f:tasks.py:send_welcome'))

case('BullMQ / Bull', 'event', {
    'queue.ts': '''
        import { Queue } from 'bullmq';
        export const emailQueue = new Queue('emails');
        export async function queueWelcome(to: string) {
          await emailQueue.add('welcome', { to });
        }
    ''',
    'worker.ts': '''
        import { Worker } from 'bullmq';
        async function processEmail(job) {}
        export const worker = new Worker('emails', processEmail);
    ''',
}, ('event', 'f:queue.ts:queueWelcome', 'f:worker.ts:processEmail'))

case('Sidekiq / ActiveJob', 'event', {
    'app/jobs/hard_job.rb': '''
        class HardJob
          include Sidekiq::Job

          def perform(name)
          end
        end
    ''',
    'app/controllers/jobs_controller.rb': '''
        class JobsController < ApplicationController
          def create
            HardJob.perform_async('bob')
          end
        end
    ''',
}, ('event', 'f:app/controllers/jobs_controller.rb:JobsController.create', 'f:app/jobs/hard_job.rb:HardJob.perform'))

case('Oban', 'event', {
    'lib/app/workers/mailer.ex': '''
        defmodule App.Workers.Mailer do
          use Oban.Worker, queue: :mailers

          @impl Oban.Worker
          def perform(%Oban.Job{args: args}) do
            :ok
          end
        end
    ''',
    'lib/app/accounts.ex': '''
        defmodule App.Accounts do
          def register(user) do
            %{id: user.id} |> App.Workers.Mailer.new() |> Oban.insert()
          end
        end
    ''',
}, ('event', 'f:lib/app/accounts.ex:App.Accounts.register', 'f:lib/app/workers/mailer.ex:App.Workers.Mailer.perform'))

case('MassTransit / integration events (.NET)', 'event', {
    'Orders/OrderPlaced.cs': '''
        public record OrderPlaced(int Id) : IntegrationEvent;
    ''',
    'Orders/OrdersApi.cs': '''
        public class OrdersApi
        {
            public async Task Place(IPublishEndpoint bus) => await bus.Publish(new OrderPlaced(1));
        }
    ''',
    'Billing/OrderPlacedConsumer.cs': '''
        public class OrderPlacedConsumer : IConsumer<OrderPlaced>
        {
            public Task Consume(ConsumeContext<OrderPlaced> context) => Task.CompletedTask;
        }
    ''',
}, ('event', 'f:Orders/OrdersApi.cs:OrdersApi.Place', 'f:Billing/OrderPlacedConsumer.cs:OrderPlacedConsumer.Consume'))

case('NServiceBus', 'event', {
    'Sales/PlaceOrder.cs': '''
        public class PlaceOrder : ICommand { }
    ''',
    'Web/OrdersController.cs': '''
        public class OrdersController
        {
            public async Task Post(IMessageSession session) => await session.Send(new PlaceOrder());
        }
    ''',
    'Sales/PlaceOrderHandler.cs': '''
        public class PlaceOrderHandler : IHandleMessages<PlaceOrder>
        {
            public Task Handle(PlaceOrder message, IMessageHandlerContext context) => Task.CompletedTask;
        }
    ''',
}, ('event', 'f:Web/OrdersController.cs:OrdersController.Post', 'f:Sales/PlaceOrderHandler.cs:PlaceOrderHandler.Handle'))

case('Hangfire', 'event', {
    'Jobs/ReportJob.cs': '''
        public class ReportJob
        {
            public void Run(int id) { }
        }
    ''',
    'Web/ReportsController.cs': '''
        public class ReportsController
        {
            public void Queue(int id) => BackgroundJob.Enqueue<ReportJob>(j => j.Run(id));
        }
    ''',
}, ('event', 'f:Web/ReportsController.cs:ReportsController.Queue', 'f:Jobs/ReportJob.cs:ReportJob.Run'))

case('Spring application events', 'event', {
    'src/main/java/demo/UserService.java': '''
        package demo;

        public class UserService {
            public void register(User u) {
                publisher.publishEvent(new UserRegistered(u.id()));
            }
        }
    ''',
    'src/main/java/demo/WelcomeMailer.java': '''
        package demo;

        public class WelcomeMailer {
            @EventListener
            public void on(UserRegistered event) {}
        }
    ''',
}, ('event', 'f:src/main/java/demo/UserService.java:UserService.register', 'f:src/main/java/demo/WelcomeMailer.java:WelcomeMailer.on'))

case('Laravel queues / events', 'event', {
    'app/Jobs/ProcessPodcast.php': '''
        <?php
        namespace App\\Jobs;
        class ProcessPodcast implements ShouldQueue
        {
            public function handle(): void {}
        }
    ''',
    'app/Http/Controllers/PodcastController.php': '''
        <?php
        namespace App\\Http\\Controllers;
        use App\\Jobs\\ProcessPodcast;
        class PodcastController extends Controller
        {
            public function store() { ProcessPodcast::dispatch($podcast); }
        }
    ''',
}, ('event', 'f:app/Http/Controllers/PodcastController.php:PodcastController.store', 'f:app/Jobs/ProcessPodcast.php:ProcessPodcast.handle'))

case('Symfony Messenger', 'event', {
    'src/Message/SmsNotification.php': '''
        <?php
        namespace App\\Message;
        class SmsNotification { }
    ''',
    'src/MessageHandler/SmsNotificationHandler.php': '''
        <?php
        namespace App\\MessageHandler;
        #[AsMessageHandler]
        class SmsNotificationHandler
        {
            public function __invoke(SmsNotification $message) {}
        }
    ''',
    'src/Controller/SmsController.php': '''
        <?php
        namespace App\\Controller;
        class SmsController
        {
            public function send(MessageBusInterface $bus) { $bus->dispatch(new SmsNotification('hi')); }
        }
    ''',
}, ('event', 'f:src/Controller/SmsController.php:SmsController.send', 'f:src/MessageHandler/SmsNotificationHandler.php:SmsNotificationHandler.__invoke'))

case('NestJS microservices / EventEmitter', 'event', {
    'src/orders.service.ts': '''
        import { EventEmitter2 } from '@nestjs/event-emitter';
        export class OrdersService {
          create() {
            this.eventEmitter.emit('order.created', {});
          }
        }
    ''',
    'src/listeners.ts': '''
        import { OnEvent } from '@nestjs/event-emitter';
        export class OrderListener {
          @OnEvent('order.created')
          handle(payload) {}
        }
    ''',
}, ('event', 'f:src/orders.service.ts:OrdersService.create', 'f:src/listeners.ts:OrderListener.handle'))

case('Trigger.dev', 'event', {
    'trigger/thumbnail.ts': '''
        import { task } from '@trigger.dev/sdk/v3';
        export const makeThumbnail = task({
          id: 'make-thumbnail',
          run: async (payload) => {},
        });
    ''',
    'app/api/upload.ts': '''
        import { makeThumbnail } from '../../trigger/thumbnail';
        export async function upload() {
          await makeThumbnail.trigger({ key: 'x' });
        }
    ''',
}, ('event', 'f:app/api/upload.ts:upload', 'f:trigger/thumbnail.ts:makeThumbnail'))

case('Inngest', 'event', {
    'inngest/functions.ts': '''
        export const syncUser = inngest.createFunction({ id: 'sync-user' }, { event: 'app/user.created' }, async ({ event }) => {});
    ''',
    'app/signup.ts': '''
        export async function signup() {
          await inngest.send({ name: 'app/user.created', data: {} });
        }
    ''',
}, ('event', 'f:app/signup.ts:signup', 'f:inngest/functions.ts:syncUser'))

case('Enum-dispatched queues (Rust)', 'event', {
    'core/src/queue.rs': '''
        pub enum JobQueue { SendMail, Cleanup }

        async fn send_mail(p: &str) {}

        fn processor(queue: JobQueue, p: &str) {
            match queue {
                JobQueue::SendMail => Box::pin(send_mail(p)),
                JobQueue::Cleanup => Box::pin(send_mail(p)),
            }
        }
    ''',
    'api/src/user.rs': '''
        async fn signup(conn: &mut Conn) {
            JobQueue::SendMail.spawn(conn).await;
        }
    ''',
}, ('event', 'f:api/src/user.rs:signup', 'f:core/src/queue.rs:send_mail'))

# ---------------------------------------------------------------- ORM / acceso a datos

case('SQLAlchemy', 'data', {
    'app/models.py': '''
        class User(Base):
            __tablename__ = 'users'
    ''',
    'app/repo.py': '''
        from app.models import User

        def find(session, uid):
            return session.query(User).get(uid)
    ''',
    'migrations/versions/001_init.py': '''
        def upgrade():
            op.create_table('users', sa.Column('id'))
    ''',
}, ('data', 'f:app/repo.py:find', 'c:app/models.py:User'))

case('SQLModel', 'data', {
    'app/models.py': '''
        class Hero(SQLModel, table=True):
            id: int
    ''',
    'app/crud.py': '''
        from sqlmodel import select
        from app.models import Hero

        def heroes(session):
            return session.exec(select(Hero)).all()
    ''',
}, ('data', 'f:app/crud.py:heroes', 'c:app/models.py:Hero'))

case('Django ORM', 'data', {
    'shop/models.py': '''
        from django.db import models

        class Product(models.Model):
            name = models.CharField(max_length=10)
    ''',
    'shop/views.py': '''
        from .models import Product

        def catalog(request):
            return Product.objects.filter(active=True)
    ''',
}, ('data', 'f:shop/views.py:catalog', 'c:shop/models.py:Product'))

case('Prisma', 'data', {
    'prisma/schema.prisma': '''
        model Post {
          id    Int    @id
          title String
        }
    ''',
    'src/posts.ts': '''
        export async function listPosts() {
          return prisma.post.findMany();
        }
    ''',
}, ('data', 'f:src/posts.ts:listPosts', 'c:prisma/schema.prisma:Post'))

case('TypeORM', 'data', {
    'src/entity/Photo.ts': '''
        @Entity('photos')
        export class Photo {
          @PrimaryGeneratedColumn() id: number;
        }
    ''',
    'src/photos.ts': '''
        import { Photo } from './entity/Photo';
        export async function allPhotos(ds) {
          return ds.getRepository(Photo).find();
        }
    ''',
}, ('data', 'f:src/photos.ts:allPhotos', 'c:src/entity/Photo.ts:Photo'))

case('Sequelize', 'data', {
    'models/user.js': '''
        const User = sequelize.define('User', { name: DataTypes.STRING });
        module.exports = User;
    ''',
    'services/users.js': '''
        const User = require('../models/user');
        async function byName(name) {
          return User.findOne({ where: { name } });
        }
    ''',
}, ('data', 'f:services/users.js:byName', 'c:models/user.js:User'))

case('Drizzle', 'data', {
    'db/schema.ts': '''
        import { pgTable, serial, text } from 'drizzle-orm/pg-core';
        export const users = pgTable('users', { id: serial('id'), name: text('name') });
    ''',
    'db/queries.ts': '''
        import { users } from './schema';
        export async function allUsers(db) {
          return db.select().from(users);
        }
    ''',
}, ('data', 'f:db/queries.ts:allUsers', 'c:db/schema.ts:users'))

case('Mongoose', 'data', {
    'models/Product.js': '''
        const mongoose = require('mongoose');
        const Product = mongoose.model('Product', productSchema);
        module.exports = Product;
    ''',
    'controllers/products.js': '''
        const Product = require('../models/Product');
        async function list(req, res) {
          res.json(await Product.find({}));
        }
    ''',
}, ('data', 'f:controllers/products.js:list', 'c:models/Product.js:Product'))

case('Knex', 'data', {
    'migrations/001.js': '''
        exports.up = (knex) => knex.schema.createTable('accounts', (t) => { t.increments(); });
    ''',
    'src/accounts.js': '''
        async function open(knex) {
          return knex('accounts').insert({ balance: 0 });
        }
    ''',
}, ('data', 'f:src/accounts.js:open', 'c:migrations/001.js:accounts'))

case('GORM', 'data', {
    'models/user.go': '''
        package models

        type User struct {
            ID   uint
            Name string
        }

        func (User) TableName() string { return "users" }
    ''',
    'repo/users.go': '''
        package repo

        func Find(db *gorm.DB) {
            db.Model(&models.User{}).Where("name = ?", "x")
        }
    ''',
}, ('data', 'f:repo/users.go:Find', 'c:models/user.go:User'))

case('ent', 'data', {
    'ent/schema/pet.go': '''
        package schema

        type Pet struct {
            ent.Schema
        }

        func (Pet) Fields() []ent.Field { return nil }
    ''',
    'svc/pets.go': '''
        package svc

        func List(ctx context.Context, client *ent.Client) {
            client.Pet.Query().All(ctx)
        }
    ''',
}, ('data', 'f:svc/pets.go:List', 'c:ent/schema/pet.go:Pet'))

case('sqlc', 'data', {
    'db/schema.sql': '''
        CREATE TABLE authors (
          id BIGSERIAL PRIMARY KEY,
          name text NOT NULL
        );
    ''',
    'db/query.sql': '''
        -- name: GetAuthor :one
        SELECT * FROM authors WHERE id = $1 LIMIT 1;
    ''',
}, ('data', 'f:db/query.sql:GetAuthor', 'c:db/schema.sql:authors'))

case('Raw SQL in code', 'data', {
    'db/001_init.sql': '''
        CREATE TABLE invoices (id int);
    ''',
    'src/invoices.py': '''
        def unpaid(cur):
            cur.execute("UPDATE invoices SET paid = false WHERE due < now()")
    ''',
}, ('data', 'f:src/invoices.py:unpaid', 'c:db/001_init.sql:invoices'))

case('JPA / Hibernate / Spring Data', 'data', {
    'src/main/java/demo/Owner.java': '''
        package demo;

        @Entity
        @Table(name = "owners")
        public class Owner {
            @Id Long id;
        }
    ''',
    'src/main/java/demo/OwnerRepository.java': '''
        package demo;

        public interface OwnerRepository extends JpaRepository<Owner, Long> {
            List<Owner> findByLastName(String name);
        }
    ''',
    'src/main/java/demo/OwnerService.java': '''
        package demo;

        public class OwnerService {
            private final OwnerRepository owners;

            public List<Owner> byName(String n) {
                return owners.findByLastName(n);
            }
        }
    ''',
}, ('data', 'f:src/main/java/demo/OwnerService.java:OwnerService.byName', 'c:src/main/java/demo/Owner.java:Owner'))

case('Panache (Quarkus)', 'data', {
    'src/main/java/demo/Villain.java': '''
        package demo;

        @Entity
        public class Villain extends PanacheEntity {
            public String name;
        }
    ''',
    'src/main/java/demo/VillainService.java': '''
        package demo;

        public class VillainService {
            public List<Villain> all() {
                return Villain.listAll();
            }
        }
    ''',
}, ('data', 'f:src/main/java/demo/VillainService.java:VillainService.all', 'c:src/main/java/demo/Villain.java:Villain'))

case('Exposed (Kotlin)', 'data', {
    'src/main/kotlin/Tables.kt': '''
        object Cities : IntIdTable("cities") {
            val name = varchar("name", 50)
        }

        class City(id: EntityID<Int>) : IntEntity(id) {
            companion object : IntEntityClass<City>(Cities)
            var name by Cities.name
        }
    ''',
    'src/main/kotlin/CityDao.kt': '''
        class CityDao {
            fun create(n: String) = transaction { City.new { name = n } }
        }
    ''',
}, ('data', 'f:src/main/kotlin/CityDao.kt:CityDao.create', 'c:src/main/kotlin/Tables.kt:Cities'))

case('Room (Android)', 'data', {
    'app/src/main/java/demo/Note.kt': '''
        @Entity(tableName = "notes")
        data class Note(@PrimaryKey val id: String, val text: String)
    ''',
    'app/src/main/java/demo/NoteDao.kt': '''
        @Dao
        interface NoteDao {
            @Query("SELECT * FROM notes")
            fun all(): List<Note>

            @Insert
            suspend fun add(note: Note)
        }
    ''',
}, ('data', 'f:app/src/main/java/demo/NoteDao.kt:NoteDao.all', 'c:app/src/main/java/demo/Note.kt:Note'),
    ('data', 'f:app/src/main/java/demo/NoteDao.kt:NoteDao.add', 'c:app/src/main/java/demo/Note.kt:Note'))

case('EF Core', 'data', {
    'Data/ShopContext.cs': '''
        public class ShopContext : DbContext
        {
            public DbSet<Product> Products { get; set; }
        }
    ''',
    'Data/Product.cs': '''
        public class Product
        {
            public int Id { get; set; }
        }
    ''',
    'Api/ProductsApi.cs': '''
        public class ProductsApi(ShopContext db)
        {
            public List<Product> All() => db.Products.ToList();
        }
    ''',
}, ('data', 'f:Api/ProductsApi.cs:ProductsApi.All', 'c:Data/Product.cs:Product'))

case('Dapper', 'data', {
    'Db/schema.sql': '''
        CREATE TABLE Customers (Id int);
    ''',
    'Api/CustomerRepo.cs': '''
        public class CustomerRepo(IDbConnection conn)
        {
            public IEnumerable<Customer> All() => conn.Query<Customer>("SELECT * FROM Customers");
        }
    ''',
}, ('data', 'f:Api/CustomerRepo.cs:CustomerRepo.All', 'c:Db/schema.sql:Customers'))

case('Eloquent (Laravel)', 'data', {
    'app/Models/Flight.php': '''
        <?php
        namespace App\\Models;
        class Flight extends Model { }
    ''',
    'app/Http/Controllers/FlightController.php': '''
        <?php
        use App\\Models\\Flight;
        class FlightController
        {
            public function index() { return Flight::where('active', 1)->get(); }
        }
    ''',
    'database/migrations/2024_create_flights.php': '''
        <?php
        Schema::create('flights', function (Blueprint $table) { $table->id(); });
    ''',
}, ('data', 'f:app/Http/Controllers/FlightController.php:FlightController.index', 'c:app/Models/Flight.php:Flight'))

case('Doctrine', 'data', {
    'src/Entity/Product.php': '''
        <?php
        namespace App\\Entity;
        #[ORM\\Entity(repositoryClass: ProductRepository::class)]
        #[ORM\\Table(name: 'product')]
        class Product { }
    ''',
    'src/Controller/ProductController.php': '''
        <?php
        class ProductController
        {
            public function show(EntityManagerInterface $em, int $id) { return $em->getRepository(Product::class)->find($id); }
        }
    ''',
}, ('data', 'f:src/Controller/ProductController.php:ProductController.show', 'c:src/Entity/Product.php:Product'))

case('ActiveRecord', 'data', {
    'app/models/article.rb': '''
        class Article < ApplicationRecord
        end
    ''',
    'app/controllers/articles_controller.rb': '''
        class ArticlesController < ApplicationController
          def index
            @articles = Article.all
          end
        end
    ''',
    'db/schema.rb': '''
        ActiveRecord::Schema.define do
          create_table "articles" do |t|
          end
        end
    ''',
}, ('data', 'f:app/controllers/articles_controller.rb:ArticlesController.index', 'c:app/models/article.rb:Article'))

case('ROM (Ruby Object Mapper)', 'data', {
    'app/relations/books.rb': '''
        module Shop
          module Relations
            class Books < ROM::Relation[:sql]
              schema :books, infer: true
            end
          end
        end
    ''',
    'app/repositories/book_repo.rb': '''
        module Shop
          class BookRepo < ROM::Repository[:books]
          end
        end
    ''',
    'config/db/migrate/001_create_books.rb': '''
        ROM::SQL.migration do
          change do
            create_table :books do
              primary_key :id
            end
          end
        end
    ''',
}, ('data', 'c:app/relations/books.rb:Books', 'c:config/db/migrate/001_create_books.rb:books'),
    ('data', 'c:app/repositories/book_repo.rb:BookRepo', 'c:app/relations/books.rb:Books'))

case('Ecto', 'data', {
    'lib/app/blog/post.ex': '''
        defmodule App.Blog.Post do
          use Ecto.Schema
          schema "posts" do
            field :title, :string
          end
        end
    ''',
    'lib/app/blog.ex': '''
        defmodule App.Blog do
          def list_posts do
            Repo.all(App.Blog.Post)
          end
        end
    ''',
}, ('data', 'f:lib/app/blog.ex:App.Blog.list_posts', 'c:lib/app/blog/post.ex:App.Blog.Post'))

case('Diesel', 'data', {
    'migrations/2024_create_posts/up.sql': '''
        CREATE TABLE posts (id SERIAL PRIMARY KEY);
    ''',
    'src/schema.rs': '''
        diesel::table! {
            posts (id) {
                id -> Int4,
            }
        }
    ''',
    'src/repo.rs': '''
        use crate::schema::posts::dsl::*;

        pub fn published(conn: &mut PgConnection) {
            posts.filter(published.eq(true)).load::<Post>(conn);
        }
    ''',
}, ('data', 'f:src/repo.rs:published', 'c:migrations/2024_create_posts/up.sql:posts'))

case('SeaORM', 'data', {
    'src/entity/cake.rs': '''
        #[derive(Clone, Debug, PartialEq, DeriveEntityModel)]
        #[sea_orm(table_name = "cake")]
        pub struct Model {
            pub id: i32,
        }
    ''',
    'src/service.rs': '''
        pub async fn cakes(db: &DbConn) {
            cake::Entity::find().all(db).await;
        }
    ''',
}, ('data', 'f:src/service.rs:cakes', 'c:src/entity/cake.rs:Model'))

case('sqlx (Rust)', 'data', {
    'migrations/0001_users.sql': '''
        CREATE TABLE users (id BIGINT);
    ''',
    'src/users.rs': '''
        async fn count(pool: &PgPool) {
            sqlx::query!("SELECT count(*) FROM users").fetch_one(pool).await;
        }
    ''',
}, ('data', 'f:src/users.rs:count', 'c:migrations/0001_users.sql:users'))

case('Core Data / SwiftData', 'data', {
    'App/Models/Trip.swift': '''
        import SwiftData

        @Model
        final class Trip {
            var name: String
            init(name: String) { self.name = name }
        }
    ''',
    'App/TripStore.swift': '''
        func loadTrips(context: ModelContext) throws -> [Trip] {
            try context.fetch(FetchDescriptor<Trip>())
        }
    ''',
}, ('data', 'f:App/TripStore.swift:loadTrips', 'c:App/Models/Trip.swift:Trip'))

case('Drift / Floor (Dart)', 'data', {
    'lib/db/todos.dart': '''
        @DataClassName('Todo')
        class Todos extends Table {
          IntColumn get id => integer().autoIncrement()();
        }
    ''',
    'lib/db/todo_repo.dart': '''
        class TodoRepo {
          Future<List<Todo>> all(AppDatabase db) => db.select(db.todos).get();
        }
    ''',
}, ('data', 'f:lib/db/todo_repo.dart:TodoRepo.all', 'c:lib/db/todos.dart:Todos'))

# ---------------------------------------------------------------- config / env

case('dotenv (.env)', 'env', {
    '.env.example': '''
        DATABASE_URL=postgres://localhost/db
    ''',
    'src/db.js': '''
        export function connect() {
          return new Pool({ connectionString: process.env.DATABASE_URL });
        }
    ''',
}, ('env', 'f:src/db.js:connect', 'DATABASE_URL', '.env.example'))

case('pydantic Settings', 'env', {
    '.env.example': '''
        SECRET_KEY=changeme
    ''',
    'app/config.py': '''
        from pydantic_settings import BaseSettings

        class Settings(BaseSettings):
            SECRET_KEY: str

        settings = Settings()
    ''',
    'app/auth.py': '''
        from app.config import settings

        def sign(data):
            return encode(data, settings.SECRET_KEY)
    ''',
}, ('env', 'f:app/auth.py:sign', 'SECRET_KEY', '.env.example'))

case('Spring relaxed binding', 'env', {
    'src/main/resources/application.properties': '''
        orders.service-url=http://localhost:8081
    ''',
    'docker-compose.yml': '''
        services:
          api:
            image: api
            environment:
              ORDERS_SERVICEURL: http://orders:8081
    ''',
    'src/main/java/demo/Cfg.java': '''
        package demo;

        public class Cfg {
            @Value("${orders.service-url}")
            private String url;
        }
    ''',
}, ('env', 'c:src/main/java/demo/Cfg.java:Cfg', 'ORDERS_SERVICEURL', 'docker-compose.yml'))

case('MicroProfile / Quarkus config', 'env', {
    'src/main/resources/application.properties': '''
        greeting.message=hello
        %prod.greeting.message=hola
    ''',
    'src/main/java/demo/Greeter.java': '''
        package demo;

        public class Greeter {
            @ConfigProperty(name = "greeting.message")
            String message;
        }
    ''',
}, ('env', 'c:src/main/java/demo/Greeter.java:Greeter', 'GREETING_MESSAGE', 'src/main/resources/application.properties'))

case('.NET configuration', 'env', {
    'docker-compose.yml': '''
        services:
          web:
            image: web
            environment:
              ConnectionStrings__Default: Host=db
    ''',
    'Web/Program.cs': '''
        var cs = builder.Configuration.GetConnectionString("Default");
    ''',
}, ('env', 'm:Web/Program.cs', 'ConnectionStrings__Default', 'docker-compose.yml'))

case('Vite / import.meta.env', 'env', {
    'web/.env.example': '''
        VITE_API_URL=http://localhost:8000
    ''',
    'web/src/api.ts': '''
        export function base() {
          return import.meta.env.VITE_API_URL;
        }
    ''',
}, ('env', 'f:web/src/api.ts:base', 'VITE_API_URL', 'web/.env.example'))

case('SvelteKit $env', 'env', {
    'web/.env.example': '''
        PUBLIC_BACKEND_URL=http://localhost:8000
    ''',
    'web/src/lib/api.ts': '''
        import { env } from '$env/dynamic/public';
        export function backend() {
          return env.PUBLIC_BACKEND_URL;
        }
    ''',
}, ('env', 'f:web/src/lib/api.ts:backend', 'PUBLIC_BACKEND_URL', 'web/.env.example'))

case('Go env / envconfig tags', 'env', {
    'docker-compose.yml': '''
        services:
          api:
            image: api
            environment:
              PG_URL: postgres://db
    ''',
    'internal/config/config.go': '''
        package config

        type Config struct {
            PgURL string `env:"PG_URL"`
        }

        func Port() string { return os.Getenv("PORT") }
    ''',
}, ('env', 'c:internal/config/config.go:Config', 'PG_URL', 'docker-compose.yml'))

case('Rails / Ruby ENV + Hanami settings', 'env', {
    '.env.example': '''
        REDIS_URL=redis://localhost
    ''',
    'config/settings.rb': '''
        module App
          class Settings < Hanami::Settings
            setting :redis_url, constructor: Types::String
          end
        end
    ''',
    'app/providers/cache.rb': '''
        class Cache
          def start
            Redis.new(url: settings.redis_url)
          end
        end
    ''',
}, ('env', 'f:app/providers/cache.rb:Cache.start', 'REDIS_URL', '.env.example'))

case('Kubernetes manifests', 'env', {
    'k8s/deployment.yaml': '''
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: api
        spec:
          template:
            spec:
              containers:
                - name: api
                  env:
                    - name: CACHE_TTL
                      value: "60"
    ''',
    'src/cache.py': '''
        import os

        def ttl():
            return int(os.environ.get('CACHE_TTL', '30'))
    ''',
}, ('env', 'f:src/cache.py:ttl', 'CACHE_TTL', 'k8s/deployment.yaml'))

case('Helm values', 'env', {
    'chart/Chart.yaml': '''
        apiVersion: v2
        name: api
    ''',
    'chart/templates/deployment.yaml': '''
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: {{ .Release.Name }}
        spec:
          template:
            spec:
              containers:
                - name: api
                  env:
                    - name: LOG_LEVEL
                      value: {{ .Values.logLevel | quote }}
    ''',
    'src/log.py': '''
        import os
        LEVEL = os.getenv('LOG_LEVEL')
    ''',
}, ('env', 'm:src/log.py', 'LOG_LEVEL', 'chart/templates/deployment.yaml'))

case('render.yaml', 'env', {
    'render.yaml': '''
        services:
          - type: web
            name: api
            envVars:
              - key: WEB_CONCURRENCY
                value: 4
    ''',
    'app/server.py': '''
        import os
        WORKERS = os.environ['WEB_CONCURRENCY']
    ''',
}, ('env', 'm:app/server.py', 'WEB_CONCURRENCY', 'render.yaml'))

case('fly.toml', 'env', {
    'fly.toml': '''
        app = "demo"

        [env]
          PRIMARY_REGION = "mad"
    ''',
    'app/main.py': '''
        import os
        REGION = os.getenv('PRIMARY_REGION')
    ''',
}, ('env', 'm:app/main.py', 'PRIMARY_REGION', 'fly.toml'))

# ---------------------------------------------------------------- cableado de servicios

case('docker compose depends_on / links', 'service', {
    'docker-compose.yml': '''
        services:
          api:
            image: api
            depends_on:
              - db
          db:
            image: postgres
    ''',
}, ('service', 'c:docker-compose.yml:api', 'c:docker-compose.yml:db'))

case('compose fragments + network aliases', 'service', {
    'deploy/compose/app.yml': '''
          app:
            image: app
            environment:
              CACHE_HOST: redis-cache
    ''',
    'deploy/compose/infra.yml': '''
          cache-1:
            image: redis
            networks:
              default:
                aliases:
                  - redis-cache
    ''',
}, ('service', 'c:deploy/compose/app.yml:app', 'c:deploy/compose/infra.yml:cache-1'))

case('Kubernetes Ingress → Service', 'service', {
    'k8s/ingress.yaml': '''
        apiVersion: networking.k8s.io/v1
        kind: Ingress
        metadata:
          name: web-ingress
        spec:
          rules:
          - http:
              paths:
              - path: "/"
                backend:
                  service:
                    name: web
    ''',
    'k8s/web-service.yaml': '''
        apiVersion: v1
        kind: Service
        metadata:
          name: web
        spec:
          selector:
            app: web
    ''',
}, ('service', 'c:k8s/ingress.yaml:Ingress/web-ingress', 'c:k8s/web-service.yaml:Service/web'))

case('Kubernetes Service URLs', 'service', {
    'k8s/web.yaml': '''
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: web
        spec:
          template:
            spec:
              containers:
                - name: web
                  env:
                    - name: API_ADDR
                      value: "api:8080"
    ''',
    'k8s/api.yaml': '''
        apiVersion: v1
        kind: Service
        metadata:
          name: api
        spec:
          ports:
            - port: 8080
    ''',
}, ('service', 'c:k8s/web.yaml:Deployment/web', 'c:k8s/api.yaml:Service/api'))

case('render.yaml fromService / fromDatabase', 'service', {
    'render.yaml': '''
        databases:
          - name: main-db
        services:
          - type: web
            name: api
            envVars:
              - key: DATABASE_URL
                fromDatabase:
                  name: main-db
                  property: connectionString
    ''',
}, ('service', 'c:render.yaml:api.DATABASE_URL', 'c:render.yaml:main-db'))

case('Procfile', 'service', {
    'Procfile': '''
        web: gunicorn app.wsgi
        worker: celery -A app.tasks worker
    ''',
    'app/wsgi.py': '''
        application = None
    ''',
    'app/tasks.py': '''
        app = None
    ''',
}, ('service', 'm:Procfile', 'm:app/tasks.py'))

# ---------------------------------------------------------------- GraphQL (servidor <- operación del cliente)

GQL_CLIENT = {
    'web/orders.ts': '''
        import { gql } from '@apollo/client';
        export const ORDER = gql`
          query Order($id: ID!) {
            order(id: $id) { id }
          }
        `;
        export function useOrder(id) {
          return useQuery(ORDER, { variables: { id } });
        }
    ''',
}

case('graphql-yoga / resolver maps', 'graphql', {**GQL_CLIENT,
    'server/schema.ts': '''
        import { createSchema } from 'graphql-yoga';
        async function orderById(_, { id }) { return null; }
        export const schema = createSchema({
          typeDefs: 'type Query { order(id: ID!): Order }',
          resolvers: { Query: { order: orderById } },
        });
    ''',
}, ('http', 'f:web/orders.ts:useOrder', 'f:server/schema.ts:orderById'))

case('NestJS GraphQL / TypeGraphQL', 'graphql', {**GQL_CLIENT,
    'server/orders.resolver.ts': '''
        import { Resolver, Query, Args } from '@nestjs/graphql';

        @Resolver()
        export class OrdersResolver {
          @Query(() => Order)
          order(@Args('id') id: string) {
            return null;
          }
        }
    ''',
}, ('http', 'f:web/orders.ts:useOrder', 'f:server/orders.resolver.ts:OrdersResolver.order'))

case('gqlgen', 'graphql', {**GQL_CLIENT,
    'graph/schema.resolvers.go': '''
        package graph

        func (r *queryResolver) Order(ctx context.Context, id string) (*model.Order, error) {
            return nil, nil
        }
    ''',
}, ('http', 'f:web/orders.ts:useOrder', 'f:graph/schema.resolvers.go:queryResolver.Order'))

case('Strawberry', 'graphql', {**GQL_CLIENT,
    'api/schema.py': '''
        import strawberry

        @strawberry.type
        class Query:
            @strawberry.field
            def order(self, id: str) -> Order:
                return None
    ''',
}, ('http', 'f:web/orders.ts:useOrder', 'f:api/schema.py:Query.order'))

case('Hot Chocolate', 'graphql', {**GQL_CLIENT,
    'Api/Query.cs': '''
        public class Query
        {
            public Order GetOrder(string id) => null;
        }
    ''',
}, ('http', 'f:web/orders.ts:useOrder', 'f:Api/Query.cs:Query.GetOrder'))

case('Spring for GraphQL', 'graphql', {**GQL_CLIENT,
    'src/main/java/demo/OrderGraph.java': '''
        package demo;

        @Controller
        public class OrderGraph {
            @QueryMapping
            public Order order(@Argument String id) {
                return null;
            }
        }
    ''',
}, ('http', 'f:web/orders.ts:useOrder', 'f:src/main/java/demo/OrderGraph.java:OrderGraph.order'))

case('Laravel events / listeners', 'event', {
    'app/Events/OrderShipped.php': '''
        <?php
        namespace App\\Events;
        class OrderShipped { }
    ''',
    'app/Listeners/SendShipmentNotification.php': '''
        <?php
        namespace App\\Listeners;
        use App\\Events\\OrderShipped;
        class SendShipmentNotification
        {
            public function handle(OrderShipped $event): void {}
        }
    ''',
    'app/Http/Controllers/OrderController.php': '''
        <?php
        class OrderController
        {
            public function ship($order) { event(new OrderShipped($order)); }
        }
    ''',
}, ('event', 'f:app/Http/Controllers/OrderController.php:OrderController.ship',
    'f:app/Listeners/SendShipmentNotification.php:SendShipmentNotification.handle'))

case('Spring Cloud Stream', 'event', {
    'orders/src/main/java/demo/Checkout.java': '''
        package demo;

        public class Checkout {
            public void done(Order o) {
                streamBridge.send("orders-out-0", o);
            }
        }
    ''',
    'orders/src/main/resources/application.yml': '''
        spring:
          cloud:
            stream:
              bindings:
                orders-out-0:
                  destination: orders
    ''',
    'billing/src/main/java/demo/Billing.java': '''
        package demo;

        public class Billing {
            @Bean
            public Consumer<Order> charge() {
                return o -> {};
            }
        }
    ''',
    'billing/src/main/resources/application.yml': '''
        spring:
          cloud:
            stream:
              bindings:
                charge-in-0:
                  destination: orders
    ''',
}, ('event', 'f:orders/src/main/java/demo/Checkout.java:Checkout.done', 'f:billing/src/main/java/demo/Billing.java:Billing.charge'))

case('Micronaut Kafka', 'event', {
    'src/main/java/demo/ProductClient.java': '''
        package demo;

        @KafkaClient
        public interface ProductClient {
            @Topic("products")
            void send(String product);
        }
    ''',
    'src/main/java/demo/ProductListener.java': '''
        package demo;

        @KafkaListener
        public class ProductListener {
            @Topic("products")
            public void receive(String product) {}
        }
    ''',
}, ('event', 'f:src/main/java/demo/ProductClient.java:ProductClient.send', 'f:src/main/java/demo/ProductListener.java:ProductListener.receive'))


# ---------------------------------------------------------------- más servidores / eventos

case('Hono', 'route', {'src/index.ts': '''
import { Hono } from 'hono'
const app = new Hono()
function listBooks(c) { return c.json([]) }
app.get('/books', listBooks)
'''}, ('route', 'GET /books', 'f:src/index.ts:listBooks'))

case('Elysia (cadenas sin variable)', 'route', {'src/index.ts': '''
import { Elysia } from 'elysia'
function listBooks() { return [] }
new Elysia().get('/books', listBooks).listen(3000)
'''}, ('route', 'GET /books', 'f:src/index.ts:listBooks'))

case('Sanic', 'route', {'app.py': '''
from sanic import Sanic
app = Sanic("x")

@app.get("/items")
async def items(request):
    return None
'''}, ('route', 'GET /items', 'f:app.py:items'))

case('Tornado', 'route', {'app.py': '''
import tornado.web
class MainHandler(tornado.web.RequestHandler):
    def get(self):
        pass
app = tornado.web.Application([(r"/main", MainHandler)])
'''}, ('route', 'GET /main', 'f:app.py:MainHandler.get'))

case('Falcon', 'route', {'app.py': '''
import falcon
class Things:
    def on_get(self, req, resp):
        pass
app = falcon.App()
app.add_route('/things', Things())
'''}, ('route', 'GET /things', 'f:app.py:Things.on_get'))

case('Socket.IO', 'event', {'server.js': '''
const io = require('socket.io')(3000);
io.on('connection', (socket) => { socket.on('chat:message', onMessage); });
function onMessage(m) {}
''', 'client.js': '''
export function send(socket, m) { socket.emit('chat:message', m); }
'''}, ('event', 'f:client.js:send', 'm:server.js'))

case('SignalR', 'route', {'Hubs/ChatHub.cs': '''
public class ChatHub : Hub
{
    public async Task SendMessage(string user, string message) { }
}
''', 'Program.cs': '''
app.MapHub<ChatHub>("/chat");
''', 'web/chat.js': '''
export function send(connection) { connection.invoke("SendMessage", "u", "m"); }
'''}, ('route', 'ANY /chat', 'c:Hubs/ChatHub.cs:ChatHub'))

case('AdonisJS', 'route', {'start/routes.ts': '''
import router from '@adonisjs/core/services/router'
const UsersController = () => import('#controllers/users_controller')
router.get('/users', [UsersController, 'index'])
''', 'app/controllers/users_controller.ts': '''
export default class UsersController {
  async index() { return [] }
}
'''}, ('route', 'GET /users', 'f:app/controllers/users_controller.ts:UsersController.index'))

case('serverless.yml http', 'route', {'serverless.yml': '''
service: api
functions:
  hello:
    handler: handler.hello
    events:
      - httpApi:
          path: /hello
          method: get
''', 'handler.py': '''
def hello(event, context):
    return {}
'''}, ('route', 'GET /hello', 'f:handler.py:hello'))

case('Flask-RESTful / RESTX', 'route', {'app.py': '''
from flask_restful import Api, Resource
class TodoList(Resource):
    def get(self):
        return []
api = Api(app)
api.add_resource(TodoList, '/todos')
'''}, ('route', 'GET /todos', 'f:app.py:TodoList.get'))

case('Bottle', 'route', {'app.py': '''
from bottle import route, run

@route('/hello')
def hello():
    return 'x'
'''}, ('route', 'GET /hello', 'f:app.py:hello'))


@pytest.mark.parametrize('files,expect', CASES)
def test_framework(tmp_path, files, expect):
    nodes, edges = graph(tmp_path, files)
    missing = [e for e in expect if not check(nodes, edges, e)]
    assert not missing, missing
