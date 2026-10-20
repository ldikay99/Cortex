"""Heurísticas estructurales de la ronda 4 (bench/flows): registro de rutas por forma de la llamada, wrappers cuyo parámetro
fluye a la URL, jobs por referencia y por clave compartida, modelos declarados, variables de entorno definidas por el repo y
cableado de manifiestos. Repos sintéticos, sin nombres ni rutas del benchmark."""
from conftest import write_repo
from cortex_graph.analyze import analyze

VIA = ('endpoint', 'topic', 'variable')


def run(tmp_path, files):
    out = analyze(write_repo(tmp_path / 'repo', files), git=False)
    keys = {n['id']: n['key'] for n in out['nodes']}
    nodes = {n['key']: n for n in out['nodes']}
    return nodes, {(keys[e['a']], keys[e['b']], e['kind']) for e in out['edges']}


def linked(nodes, edges, kinds, a, b):
    adj = {}
    for x, y, k in edges:
        if k in kinds:
            adj.setdefault(x, set()).add(y)
            adj.setdefault(y, set()).add(x)
    if b in adj.get(a, ()):
        return True
    via = lambda n: nodes.get(n, {}).get('kind') in VIA or bool(nodes.get(n, {}).get('table'))
    return any(b in adj.get(n, ()) for n in adj.get(a, ()) if via(n))


def handled(nodes, edges, route, handler):
    return any((e, handler, 'handles') in edges for e, n in nodes.items() if n.get('kind') == 'endpoint' and n.get('name') == route)


def test_wrapper_registration_expands_class_handler(tmp_path):
    nodes, edges = run(tmp_path, {
        'app/api.py': '''
            from app.items import ItemResource, ItemListResource


            class ApiExt(object):
                def add_org_resource(self, resource, *urls, **kwargs):
                    return self.add_resource(resource, *urls, **kwargs)


            api = ApiExt()
            api.add_org_resource(ItemResource, "/api/items/<item_id>", endpoint="item")
            api.add_org_resource(
                ItemListResource,
                "/api/items",
                endpoint="items",
            )
        ''',
        'app/items.py': '''
            class ItemResource(object):
                def get(self, item_id):
                    return {}

                def delete(self, item_id):
                    return {}


            class ItemListResource(object):
                def get(self):
                    return []

                def post(self):
                    return {}
        ''',
    })
    assert handled(nodes, edges, 'GET /api/items/:item_id', 'f:app/items.py:ItemResource.get')
    assert handled(nodes, edges, 'DELETE /api/items/:item_id', 'f:app/items.py:ItemResource.delete')
    assert handled(nodes, edges, 'POST /api/items', 'f:app/items.py:ItemListResource.post')


def test_rpc_names_mounts_and_suffix_client(tmp_path):
    nodes, edges = run(tmp_path, {
        'server/routes/things/index.ts': '''
            export { default } from "./things";
        ''',
        'server/routes/things/things.ts': '''
            import Router from "@koa/router";

            const router = new Router();

            router.post(
              "things.list",
              async (ctx) => {
                ctx.body = [];
              }
            );

            export default router;
        ''',
        'server/routes/index.ts': '''
            import Router from "@koa/router";
            import things from "./things";

            const router = new Router();
            router.use("/", things.routes());
            export default router;
        ''',
        'server/web.ts': '''
            import mount from "koa-mount";
            import api from "./routes";

            export function init(app) {
              app.use(mount("/api", api));
            }
        ''',
        'app/stores/ThingsStore.ts': '''
            import { client } from "../client";

            export default class ThingsStore {
              async fetchAll() {
                return client.post("/things.list", {});
              }
            }
        ''',
    })
    eps = [n for n, m in nodes.items() if m.get('kind') == 'endpoint' and m.get('name') == 'POST /api/things.list']
    assert eps
    assert linked(nodes, edges, {'http'}, 'f:app/stores/ThingsStore.ts:ThingsStore.fetchAll', eps[0])


def test_chained_server_routes_and_base_path(tmp_path):
    nodes, edges = run(tmp_path, {
        'packages/api/routes/things.ts': '''
            import { Server } from "tiny-server";

            const app = new Server()
              .use(auth)
              .get("/", async (c) => {
                return c.json([]);
              })
              .delete("/:thingId", async (c) => {
                return c.json({});
              });

            export default app;
        ''',
        'packages/api/index.ts': '''
            import { Server } from "tiny-server";
            import things from "./routes/things";

            const v1 = new Server().route("/things", things);
            const app = new Server().basePath("/api").route("/v1", v1);
            export default app;
        ''',
    })
    names = {m['name'] for m in nodes.values() if m.get('kind') == 'endpoint'}
    assert 'GET /api/v1/things' in names
    assert 'DELETE /api/v1/things/:thingId' in names


def test_url_wrappers_across_files(tmp_path):
    nodes, edges = run(tmp_path, {
        'server/router.go': '''
            package router

            import "example.com/app/server/api"

            func Routes(e *gin.RouterGroup) {
                base := e.Group("/api")
                {
                    base.GET("/agents/:agent_id", api.GetAgent)
                }
            }
        ''',
        'server/api/agent.go': '''
            package api

            func GetAgent(c *gin.Context) {
            }
        ''',
        'web/lib/client.ts': '''
            export default class ApiClient {
              server = "";

              private async _request(method: string, path: string, data?: unknown) {
                const res = await fetch(`${this.server}${path}`, {
                  method,
                  body: JSON.stringify(data),
                });
                return res.json();
              }

              async _get(path: string) {
                return this._request('GET', path);
              }
            }
        ''',
        'web/lib/index.ts': '''
            import ApiClient from "./client";

            export default class AppClient extends ApiClient {
              async getAgent(agentId: number) {
                return this._get(`/api/agents/${agentId}`);
              }
            }
        ''',
    })
    assert linked(nodes, edges, {'http'}, 'f:web/lib/index.ts:AppClient.getAgent', 'e:server/router.go:GET /api/agents/:agent_id')
    assert handled(nodes, edges, 'GET /api/agents/:agent_id', 'f:server/api/agent.go:GetAgent')


def test_jobs_by_reference_and_shared_key(tmp_path):
    nodes, edges = run(tmp_path, {
        'tasks/general.py': '''
            from app.worker import job


            @job("emails")
            def send_mail(to, subject):
                return to
        ''',
        'tasks/schedule.py': '''
            from tasks.maintenance import refresh_all


            def periodic_job_definitions():
                return [
                    {"func": refresh_all, "interval": 30},
                ]
        ''',
        'tasks/maintenance.py': '''
            def refresh_all():
                return 1
        ''',
        'auth/account.py': '''
            from tasks.general import send_mail


            def invite(user):
                send_mail.delay([user], "hello")
        ''',
        'server/tasks/UploadTask.ts': '''
            export default class UploadTask extends BaseTask {
              public async perform(props) {
                return props;
              }
            }
        ''',
        'server/processors/Avatar.ts': '''
            import UploadTask from "../tasks/UploadTask";

            export default class AvatarProcessor {
              async perform(event) {
                await new UploadTask().schedule({ id: event.id });
              }
            }
        ''',
        'shared/queues.ts': '''
            export const CleanupQueue = createQueue("cleanup_queue");
        ''',
        'workers/cleanup.ts': '''
            import { CleanupQueue } from "../shared/queues";

            export class CleanupWorker {
              static async build() {
                return client.createRunner(CleanupQueue, {
                  run: withTracing("cleanup.run", runCleanup),
                });
              }
            }

            async function runCleanup(job) {
              return job;
            }
        ''',
        'api/admin.ts': '''
            import { CleanupQueue } from "../shared/queues";

            export async function trigger() {
              await CleanupQueue.enqueue({ all: true });
            }
        ''',
    })
    ev = {'event'}
    assert linked(nodes, edges, ev, 'f:auth/account.py:invite', 'f:tasks/general.py:send_mail')
    assert linked(nodes, edges, ev, 'f:tasks/schedule.py:periodic_job_definitions', 'f:tasks/maintenance.py:refresh_all')
    assert linked(nodes, edges, ev, 'f:server/processors/Avatar.ts:AvatarProcessor.perform', 'f:server/tasks/UploadTask.ts:UploadTask.perform')
    assert linked(nodes, edges, ev, 'f:api/admin.ts:trigger', 'f:workers/cleanup.ts:runCleanup')


def test_lambda_job_resolves_interface_implementation(tmp_path):
    nodes, edges = run(tmp_path, {
        'Services/IReportService.cs': '''
            namespace App.Services;
            public interface IReportService
            {
                Task Rebuild(int id);
            }
        ''',
        'Services/ReportService.cs': '''
            namespace App.Services;
            public class ReportService : IReportService
            {
                public async Task Rebuild(int id)
                {
                    await Task.CompletedTask;
                }
            }
        ''',
        'Controllers/ReportController.cs': '''
            namespace App.Controllers;
            public class ReportController(IReportService reportService) : ControllerBase
            {
                public ActionResult Refresh(int id)
                {
                    BackgroundJob.Enqueue(() => reportService.Rebuild(id));
                    return Ok();
                }
            }
        ''',
    })
    assert linked(nodes, edges, {'event'}, 'f:Controllers/ReportController.cs:ReportController.Refresh',
                  'f:Services/ReportService.cs:ReportService.Rebuild')


def test_declared_models_and_qualified_uses(tmp_path):
    nodes, edges = run(tmp_path, {
        'server/models/Pin.ts': '''
            import { Table, Model } from "sequelize-typescript";

            @Table({ tableName: "pins", modelName: "pin" })
            class Pin extends Model {
            }

            export default Pin;
        ''',
        'server/models/index.ts': '''
            export { default as Pin } from "./Pin";
        ''',
        'server/routes/pins.ts': '''
            import { Pin } from "../models";

            export async function list() {
              return Pin.findAll({ where: {} });
            }
        ''',
        'server/schema.sql': '''
            CREATE TABLE pins (
                id uuid NOT NULL
            );
        ''',
        'app/models.py': '''
            class Destination(db.Model):
                __tablename__ = "destinations"
        ''',
        'app/handlers.py': '''
            from app import models


            def get_destination(destination_id):
                return models.Destination.get_by_id(destination_id)
        ''',
    })
    assert linked(nodes, edges, {'data'}, 'f:server/routes/pins.ts:list', 'c:server/models/Pin.ts:Pin')
    assert linked(nodes, edges, {'data'}, 'c:server/models/Pin.ts:Pin', 'c:server/schema.sql:pins')
    assert linked(nodes, edges, {'data'}, 'f:app/handlers.py:get_destination', 'c:app/models.py:Destination')


def test_env_names_defined_by_the_repo(tmp_path):
    nodes, edges = run(tmp_path, {
        '.env.sample': 'DATA_DIR=/data\nAPP_OPEN=true\n',
        'compose.yaml': '''
            x-app-environment: &app-environment
              APP_REDIS_URL: "redis://redis:6379/0"
            services:
              server:
                image: app
                environment:
                  <<: *app-environment
              redis:
                image: redis
        ''',
        'packages/config.ts': '''
            const allEnv = z.object({
              DATA_DIR: z.string().default(""),
            });
        ''',
        'app/settings.py': '''
            import os

            REDIS_URL = os.environ.get("APP_REDIS_URL", "redis://localhost")
        ''',
        'cmd/flags.go': '''
            package main

            var flags = []cli.Flag{
                &cli.BoolFlag{
                    Sources: cli.EnvVars("APP_OPEN"),
                    Name:    "open",
                },
            }
        ''',
        'cmd/setup.go': '''
            package main

            func setup(c *cli.Command) {
                open := c.Bool("open")
                _ = open
            }
        ''',
    })
    def reads(var, where):
        return any(b == f'v:{var}' and k == 'env' and nodes[a].get('file') == where for a, b, k in edges)
    assert reads('DATA_DIR', 'packages/config.ts')
    assert reads('APP_REDIS_URL', 'app/settings.py') and reads('APP_REDIS_URL', 'compose.yaml')
    assert reads('APP_OPEN', 'cmd/setup.go')


def test_manifest_and_compose_wiring(tmp_path):
    nodes, edges = run(tmp_path, {
        'docker-compose.yml': '''
            services:
              api:
                build: ./api
                image: api
        ''',
        'api/Dockerfile': 'FROM python:3.12\n',
        'api/main.py': 'print(1)\n',
        'k8s/kustomization.yaml': '''
            apiVersion: kustomize.config.k8s.io/v1beta1
            kind: Kustomization
            resources:
            - web-deployment.yaml
            - web-service.yaml
        ''',
        'k8s/web-deployment.yaml': '''
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: web
            spec:
              selector:
                matchLabels:
                  app: shop-web
              template:
                metadata:
                  labels:
                    app: shop-web
                spec:
                  containers:
                    - name: web
                      image: shop
        ''',
        'k8s/web-service.yaml': '''
            apiVersion: v1
            kind: Service
            metadata:
              name: web
            spec:
              selector:
                app: shop-web
              ports:
                - port: 80
        ''',
    })
    dep = {'depends'}
    assert linked(nodes, edges, dep, 'c:docker-compose.yml:api', 'm:api/Dockerfile')
    assert linked(nodes, edges, dep, 'c:k8s/web-service.yaml:Service/web', 'c:k8s/web-deployment.yaml:Deployment/web')
    assert linked(nodes, edges, dep, 'm:k8s/kustomization.yaml', 'c:k8s/web-service.yaml:Service/web')


def test_annotated_contract_served_by_implementation(tmp_path):
    nodes, edges = run(tmp_path, {
        'orders-api/src/main/java/OrderOperations.java': '''
            public interface OrderOperations {
                @Get("/{number}")
                OrderResult get(String number);
            }
        ''',
        'orders/src/main/java/OrderController.java': '''
            @Controller("/orders")
            public class OrderController implements OrderOperations {
                @Override
                public OrderResult get(String number) {
                    return null;
                }
            }
        ''',
    })
    assert handled(nodes, edges, 'GET /orders/:number', 'f:orders/src/main/java/OrderController.java:OrderController.get')


def test_rpc_procedures_called_by_name(tmp_path):
    nodes, edges = run(tmp_path, {
        'trpc/routers/things.ts': '''
            import { router, authedProcedure } from "../index";

            export const thingsAppRouter = router({
              list: authedProcedure
                .input(z.object({}))
                .query(async ({ ctx }) => {
                  return [];
                }),
            });
        ''',
        'trpc/routers/_app.ts': '''
            import { router } from "../index";
            import { thingsAppRouter } from "./things";

            export const appRouter = router({
              things: thingsAppRouter,
            });
        ''',
        'web/hooks/things.ts': '''
            export function useThings() {
              const api = useTRPC();
              return useQuery(api.things.list.queryOptions({}));
            }
        ''',
    })
    eps = [n for n, m in nodes.items() if m.get('kind') == 'endpoint' and m.get('name', '').endswith('/trpc/things/list')]
    assert eps and ('f:web/hooks/things.ts:useThings', eps[0], 'rpc') in edges


def test_django_urls_with_unmounted_router_and_patterns(tmp_path):
    nodes, edges = run(tmp_path, {
        'app/views.py': '''
            def ping(request):
                return None


            class DocumentViewSet:
                def list(self, request):
                    return None
        ''',
        'app/urls.py': '''
            from django.urls import path
            from rest_framework.routers import DefaultRouter
            from app import views

            router = DefaultRouter()
            router.register(r"documents", views.DocumentViewSet)

            urlpatterns = [path("ping/", views.ping)]
        ''',
    })
    assert any(n.get('kind') == 'endpoint' for n in nodes.values())
