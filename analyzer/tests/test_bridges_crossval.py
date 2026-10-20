"""Mecanismos generales de la ronda 6 (bench/flows): cada caso describe un idioma en abstracto con su forma canónica y variantes en
otros lenguajes, más un caso negativo de precisión. Repos sintéticos, sin nombres ni rutas del benchmark; la evidencia en el corpus
está en `bench/flows/README.md` («Ronda 6»)."""
from conftest import write_repo
from cortex_graph.analyze import analyze

VIA = ('endpoint', 'topic', 'variable')


def run(tmp_path, files):
    out = analyze(write_repo(tmp_path / 'repo', files), git=False)
    keys = {n['id']: n['key'] for n in out['nodes']}
    nodes = {n['key']: n for n in out['nodes']}
    return nodes, {(keys[e['a']], keys[e['b']], e['kind']) for e in out['edges']}


def linked(nodes, edges, kinds, a, b):
    kinds = {kinds} if isinstance(kinds, str) else set(kinds)
    adj = {}
    for x, y, k in edges:
        if k in kinds:
            adj.setdefault(x, set()).add(y)
            adj.setdefault(y, set()).add(x)
    if b in adj.get(a, ()):
        return True
    via = lambda n: nodes.get(n, {}).get('kind') in VIA or bool(nodes.get(n, {}).get('table'))
    return any(b in adj.get(n, ()) for n in adj.get(a, ()) if via(n))


def node_at(nodes, rel, name):
    return next(k for k, n in nodes.items() if n.get('file') == rel and (n.get('name') == name or n.get('name', '').endswith('.' + name))
                and n.get('kind') in ('function', 'method', 'class'))


# ------------------------------------------------------------------------------------------------------------- eventos

def test_typed_message_bus(tmp_path):
    nodes, edges = run(tmp_path, {
        'src/Core/Messaging/IHandle.cs': '''
            namespace App.Core.Messaging
            {
                public interface IHandle<TEvent> where TEvent : IEvent
                {
                    void Handle(TEvent message);
                }
                public interface IExecute<TCommand> where TCommand : Command
                {
                    void Execute(TCommand message);
                }
            }
        ''',
        'src/Core/Messaging/Bus.cs': '''
            namespace App.Core.Messaging
            {
                public class Bus : IBus
                {
                    public void PublishEvent<TEvent>(TEvent @event) where TEvent : class, IEvent
                    {
                        Dispatch(@event);
                    }
                    public void Push<TCommand>(TCommand command, int priority = 0) where TCommand : Command
                    {
                        Queue(command);
                    }
                }
            }
        ''',
        'src/Core/Tags/TagsUpdatedEvent.cs': 'namespace App.Core.Tags { public class TagsUpdatedEvent : IEvent { } }\n',
        'src/Core/Tags/RefreshTagsCommand.cs': 'namespace App.Core.Tags { public class RefreshTagsCommand : Command { } }\n',
        'src/Core/Tags/TagService.cs': '''
            namespace App.Core.Tags
            {
                public class TagService
                {
                    private readonly IBus _bus;
                    public void Add(Tag tag)
                    {
                        _repo.Insert(tag);
                        _bus.PublishEvent(new TagsUpdatedEvent());
                    }
                    public void Refresh()
                    {
                        _bus.Push(new RefreshTagsCommand { All = true });
                    }
                    private void Changed(Tag tag)
                    {
                        var changed = new TagsUpdatedEvent
                        {
                            Id = tag.Id,
                        };
                        Log(tag);
                        _bus.PublishEvent(changed);
                    }
                }
            }
        ''',
        'src/Core/Jobs/Scheduler.cs': '''
            namespace App.Core.Jobs
            {
                public class Scheduler
                {
                    public List<Task> Defaults()
                    {
                        return new List<Task>
                        {
                            new Task { Interval = 5, TypeName = typeof(RefreshTagsCommand).FullName },
                        };
                    }
                }
            }
        ''',
        'src/Api/Tags/TagController.cs': '''
            namespace App.Api.Tags
            {
                public class TagController : RestController<Tag>,
                                             IHandle<TagsUpdatedEvent>
                {
                    public void Handle(TagsUpdatedEvent message)
                    {
                        Broadcast();
                    }
                }
            }
        ''',
        'src/Core/Tags/TagRefresher.cs': '''
            namespace App.Core.Tags
            {
                public class TagRefresher : IExecute<RefreshTagsCommand>, IExecute<CleanupTagsCommand>
                {
                    public void Execute(RefreshTagsCommand message) { }
                    public void Execute(CleanupTagsCommand message) { }
                }
            }
        ''',
        # negativo: repositorio genérico con un método que recibe la entidad; `Add(new Order())` no es un despacho
        'src/Core/Orders/OrderRepository.cs': '''
            namespace App.Core.Orders
            {
                public class OrderRepository : IRepository<Order>
                {
                    public Order Insert(Order order) { return order; }
                }
                public class OrderService
                {
                    public void Create() { _repo.Insert(new Order()); }
                }
            }
        ''',
        # variante Java: interfaz genérica del repo + publicador genérico
        'svc/src/main/java/app/events/Listener.java': '''
            package app.events;
            public interface Listener<E> { void onEvent(E event); }
        ''',
        'svc/src/main/java/app/events/EventBus.java': '''
            package app.events;
            public class EventBus {
                public <E> void post(E event) { }
            }
        ''',
        'svc/src/main/java/app/users/UserCreated.java': 'package app.users;\npublic class UserCreated { }\n',
        'svc/src/main/java/app/users/UserService.java': '''
            package app.users;
            public class UserService {
                private EventBus bus;
                public void create() {
                    bus.post(new UserCreated());
                }
            }
        ''',
        'svc/src/main/java/app/mail/WelcomeMailer.java': '''
            package app.mail;
            public class WelcomeMailer implements Listener<UserCreated> {
                @Override
                public void onEvent(UserCreated event) { }
            }
        ''',
    })
    publish = node_at(nodes, 'src/Core/Tags/TagService.cs', 'Add')
    handle = node_at(nodes, 'src/Api/Tags/TagController.cs', 'Handle')
    assert linked(nodes, edges, 'event', publish, handle)
    assert linked(nodes, edges, 'event', node_at(nodes, 'src/Core/Tags/TagService.cs', 'Changed'), handle)
    controller = node_at(nodes, 'src/Api/Tags/TagController.cs', 'TagController')
    assert linked(nodes, edges, 'event', controller, handle)  # registro `IHandle<T>` en la cabecera de la clase
    push = node_at(nodes, 'src/Core/Tags/TagService.cs', 'Refresh')
    execute = node_at(nodes, 'src/Core/Tags/TagRefresher.cs', 'Execute')
    assert linked(nodes, edges, 'event', push, execute)
    defaults = node_at(nodes, 'src/Core/Jobs/Scheduler.cs', 'Defaults')
    assert linked(nodes, edges, 'event', defaults, execute)  # `typeof(T)` en un planificador
    create = node_at(nodes, 'svc/src/main/java/app/users/UserService.java', 'create')
    on_event = node_at(nodes, 'svc/src/main/java/app/mail/WelcomeMailer.java', 'onEvent')
    assert linked(nodes, edges, 'event', create, on_event)
    assert not any(n.get('kind') == 'topic' and n.get('name') == 'Order' for n in nodes.values())


def test_listener_registries_key_dispatch_and_fanout(tmp_path):
    nodes, edges = run(tmp_path, {
        # Ruby: registro `listeners` + despacho por clave -> método con el nombre de la clave
        'lib/events/types.rb': "module Events::Types\n  ORDER_PLACED = 'order.placed'\n  ORDER_PAID = 'order.paid'\nend\n",
        'app/dispatchers/async_dispatcher.rb': '''
            class AsyncDispatcher < BaseDispatcher
              def listeners
                [
                  MailerListener.instance,
                  StatsListener.instance
                ]
              end
            end
        ''',
        'app/listeners/mailer_listener.rb': '''
            class MailerListener < BaseListener
              def order_placed(event)
                deliver(event)
              end
            end
        ''',
        'app/listeners/stats_listener.rb': '''
            class StatsListener < BaseListener
              def order_paid(event)
                count(event)
              end
            end
        ''',
        'app/models/order.rb': '''
            class Order < ApplicationRecord
              include Events::Types
              def notify_created
                Rails.configuration.dispatcher.dispatch(ORDER_PLACED, Time.zone.now, order: self)
              end
            end
        ''',
        # Python: el bus construye sus oyentes y reparte en un bucle; quien llama a `dispatch` llega a `publish` de cada uno
        'app/services/bus/listeners.py': '''
            class MailListener:
                def publish(self, event):
                    send(event)

            class HookListener:
                def publish(self, event):
                    post(event)
        ''',
        'app/services/bus/service.py': '''
            from app.services.bus.listeners import HookListener, MailListener

            class BusService:
                def _get_listeners(self, group):
                    return [
                        MailListener(group),
                        HookListener(group),
                    ]

                def _publish(self, event, group):
                    for listener in self._get_listeners(group):
                        listener.publish(event)

                def dispatch_event(self, group, kind):
                    self._publish(make(kind), group)
        ''',
        'app/routes/signup.py': '''
            def signup(bus, group):
                save()
                bus.dispatch_event(group, "signup")
        ''',
        # PHP: registro tipado, mapa tipo -> handlers, lista de suscriptores y observadores
        'app/Events/Paid.php': '<?php\nnamespace App\\Events;\nclass Paid { }\n',
        'app/Listeners/AuditListener.php': '''<?php
            namespace App\\Listeners;
            use App\\Events\\Paid;
            class AuditListener
            {
                public function record(Paid $event): void { }

                public function subscribe($events): void
                {
                    $events->listen(Paid::class, [self::class, 'record']);
                }
            }
        ''',
        'app/Notifications/Receipt.php': '''<?php
            namespace App\\Notifications;
            use App\\Events\\Paid as PaidEvent;
            class Receipt
            {
                public function handle(PaidEvent $event): void { }
            }
        ''',
        'app/Observers/UserObserver.php': '<?php\nnamespace App\\Observers;\nclass UserObserver\n{\n    public function created($u) { }\n}\n',
        'app/Providers/EventServiceProvider.php': '''<?php
            namespace App\\Providers;
            use App\\Events\\Paid as PaidEvent;
            use App\\Notifications\\Receipt;
            class EventServiceProvider extends ServiceProvider
            {
                protected $listen = [
                    PaidEvent::class => [Receipt::class],
                ];

                protected $subscribe = [
                    AuditListener::class,
                ];

                public function boot(): void
                {
                    User::observe(UserObserver::class);
                }
            }
        ''',
        'app/Http/Controllers/PayController.php': '''<?php
            namespace App\\Http\\Controllers;
            use App\\Events\\Paid;
            class PayController
            {
                public function store()
                {
                    Event::dispatch(new Paid($order));
                }
            }
        ''',
    })
    disp = node_at(nodes, 'app/dispatchers/async_dispatcher.rb', 'listeners')
    assert linked(nodes, edges, 'event', disp, node_at(nodes, 'app/listeners/mailer_listener.rb', 'MailerListener'))
    created = node_at(nodes, 'app/models/order.rb', 'notify_created')
    assert linked(nodes, edges, 'event', created, node_at(nodes, 'app/listeners/mailer_listener.rb', 'order_placed'))
    assert not linked(nodes, edges, 'event', created, node_at(nodes, 'app/listeners/stats_listener.rb', 'order_paid'))
    signup = node_at(nodes, 'app/routes/signup.py', 'signup')
    assert linked(nodes, edges, 'event', signup, node_at(nodes, 'app/services/bus/listeners.py', 'HookListener.publish'))
    assert linked(nodes, edges, 'event', node_at(nodes, 'app/services/bus/service.py', '_get_listeners'),
                  node_at(nodes, 'app/services/bus/listeners.py', 'MailListener'))
    store = node_at(nodes, 'app/Http/Controllers/PayController.php', 'store')
    record = node_at(nodes, 'app/Listeners/AuditListener.php', 'record')
    assert linked(nodes, edges, 'event', store, record)
    assert linked(nodes, edges, 'event', node_at(nodes, 'app/Listeners/AuditListener.php', 'subscribe'), record)
    assert linked(nodes, edges, 'event', store, node_at(nodes, 'app/Notifications/Receipt.php', 'handle'))
    provider = node_at(nodes, 'app/Providers/EventServiceProvider.php', 'EventServiceProvider')
    assert linked(nodes, edges, 'event', provider, node_at(nodes, 'app/Listeners/AuditListener.php', 'subscribe'))
    boot = node_at(nodes, 'app/Providers/EventServiceProvider.php', 'boot')
    assert linked(nodes, edges, 'event', boot, node_at(nodes, 'app/Observers/UserObserver.php', 'UserObserver'))


def test_function_reference_registrations_and_self_handling_messages(tmp_path):
    nodes, edges = run(tmp_path, {
        'app/tasks/purge.py': 'def purge_tokens():\n    delete_old()\n',
        'app/tasks/report.py': 'def weekly_report():\n    build()\n',
        'app/main.py': '''
            from app.tasks.purge import purge_tokens
            from app.tasks import report

            async def start_scheduler(registry, bg):
                registry.register_daily(
                    purge_tokens,
                    report.weekly_report,
                )
                bg.add_task(report.weekly_report, "now")
        ''',
        # PHP: notificaciones/jobs/comandos con la plantilla de su base y despachados sin consumidor externo
        'app/Notifications/Welcome.php': '<?php\nnamespace App\\Notifications;\nclass Welcome extends Notification\n{\n'
                                         '    public function via($n) { return ["mail"]; }\n    public function toMail($n) { }\n}\n',
        'app/Notifications/Goodbye.php': '<?php\nnamespace App\\Notifications;\nclass Goodbye extends Notification\n{\n'
                                         '    public function via($n) { return ["mail"]; }\n    public function toMail($n) { }\n}\n',
        'app/Services/Signup.php': '''<?php
            namespace App\\Services;
            use App\\Notifications\\Welcome;
            class Signup
            {
                public function run($user)
                {
                    $user->notify(new Welcome($user));
                }
            }
        ''',
        'app/Console/Commands/PruneCommand.php': '''<?php
            namespace App\\Console\\Commands;
            class PruneCommand extends Command
            {
                protected $signature = 'app:prune {--days=}';
                public function handle(): int { return 0; }
            }
        ''',
        'app/Console/Commands/StatsCommand.php': '<?php\nnamespace App\\Console\\Commands;\nclass StatsCommand extends Command\n{\n'
                                                 '    public function handle(): int { return 0; }\n}\n',
        'app/Console/Kernel.php': '''<?php
            namespace App\\Console;
            use App\\Console\\Commands\\StatsCommand;
            class Kernel
            {
                protected function schedule(Schedule $schedule): void
                {
                    $schedule->command('app:prune --days=3')->daily();
                    $schedule->command(StatsCommand::class)->hourly();
                }
            }
        ''',
    })
    start = node_at(nodes, 'app/main.py', 'start_scheduler')
    assert linked(nodes, edges, 'event', start, node_at(nodes, 'app/tasks/purge.py', 'purge_tokens'))
    assert linked(nodes, edges, 'event', start, node_at(nodes, 'app/tasks/report.py', 'weekly_report'))
    run_ = node_at(nodes, 'app/Services/Signup.php', 'run')
    assert linked(nodes, edges, 'event', run_, node_at(nodes, 'app/Notifications/Welcome.php', 'toMail'))
    sched = node_at(nodes, 'app/Console/Kernel.php', 'schedule')
    assert linked(nodes, edges, 'event', sched, node_at(nodes, 'app/Console/Commands/PruneCommand.php', 'handle'))
    assert linked(nodes, edges, 'event', sched, node_at(nodes, 'app/Console/Commands/StatsCommand.php', 'handle'))


# ------------------------------------------------------------------------------------------------------------- http

SERVER = '''
    const express = require('express');
    const router = express.Router();
    router.get('/api/v1/accounts/:accountId/agents', listAgents);
    router.post('/api/v1/accounts/:accountId/agents', createAgent);
    router.delete('/api/v1/accounts/:accountId/agents/:id', deleteAgent);
    router.post('/api/v1/accounts/:accountId/agents/bulk_create', bulkCreate);
    router.post('/api/households/webhooks/:id/test', testWebhook);
    router.get('/api/households/webhooks', listWebhooks);
    function listAgents(req, res) {}
    function createAgent(req, res) {}
    function deleteAgent(req, res) {}
    function bulkCreate(req, res) {}
    function testWebhook(req, res) {}
    function listWebhooks(req, res) {}
    module.exports = router;
'''


def test_instance_built_client_urls(tmp_path):
    nodes, edges = run(tmp_path, {
        'server/routes.js': SERVER,
        'web/api/ApiClient.js': '''
            const DEFAULT_API_VERSION = 'v1';

            class ApiClient {
              constructor(resource, options = {}) {
                this.apiVersion = `/api/${options.apiVersion || DEFAULT_API_VERSION}`;
                this.options = options;
                this.resource = resource;
              }

              get url() {
                return `${this.baseUrl()}/${this.resource}`;
              }

              baseUrl() {
                let url = this.apiVersion;
                if (this.options.enterprise) {
                  url = `/enterprise${url}`;
                }
                if (this.options.accountScoped) {
                  url = `${url}/accounts/${this.accountId}`;
                }
                return url;
              }

              get() {
                return axios.get(this.url);
              }

              create(data) {
                return axios.post(this.url, data);
              }

              delete(id) {
                return axios.delete(`${this.url}/${id}`);
              }
            }

            export default ApiClient;
        ''',
        'web/api/agents.js': '''
            import ApiClient from './ApiClient';

            class Agents extends ApiClient {
              constructor() {
                super('agents', { accountScoped: true });
              }

              bulkInvite({ emails }) {
                return axios.post(`${this.url}/bulk_create`, { emails });
              }
            }

            export default new Agents();
        ''',
        'web/store/agents.js': '''
            import AgentAPI from '../api/agents';

            export const actions = {
              get: async ({ commit }) => {
                const response = await AgentAPI.get();
                commit('SET', response.data);
              },
              remove: async ({ commit }, id) => {
                await AgentAPI.delete(id);
              },
            };
        ''',
        # campos inicializados con un objeto de rutas del módulo (cadenas y funciones flecha)
        'web/lib/base.ts': '''
            export abstract class BaseCRUDAPI<T> {
              public baseRoute: string;
              constructor(public requests: Requests) {}
              async getAll() {
                return await this.requests.get<T[]>(this.baseRoute);
              }
            }
        ''',
        'web/lib/webhooks.ts': '''
            import { BaseCRUDAPI } from "./base";

            const prefix = "/api";

            const routes = {
              webhooks: `${prefix}/households/webhooks`,
              webhooksIdTest: (id: string | number) => `${prefix}/households/webhooks/${id}/test`,
            };

            export class WebhooksAPI extends BaseCRUDAPI<Webhook> {
              baseRoute = routes.webhooks;
              itemTestRoute = routes.webhooksIdTest;

              async testOne(itemId: string | number) {
                return await this.requests.post<null>(`${this.itemTestRoute(itemId)}`, {});
              }
            }
        ''',
    })
    bulk = node_at(nodes, 'web/api/agents.js', 'bulkInvite')
    assert linked(nodes, edges, ('http', 'handles'), bulk, node_at(nodes, 'server/routes.js', 'bulkCreate'))
    get = node_at(nodes, 'web/store/agents.js', 'get') if any(n.get('name', '').endswith('get') and n.get('file') == 'web/store/agents.js'
                                                                for n in nodes.values()) else 'm:web/store/agents.js'
    assert linked(nodes, edges, ('http', 'handles'), get, node_at(nodes, 'server/routes.js', 'listAgents'))
    test = node_at(nodes, 'web/lib/webhooks.ts', 'testOne')
    assert linked(nodes, edges, ('http', 'handles'), test, node_at(nodes, 'server/routes.js', 'testWebhook'))


def test_instance_urls_prune_conditions_and_locals(tmp_path):
    nodes, edges = run(tmp_path, {
        'server/routes.js': '''
            router.get('/api/documents/', listDocs);
            router.post('/api/documents/bulk_edit/', bulkEdit);
            router.get('/api/documents/:id/notes/', notes);
            router.get('/api/metadata/age-ratings', ageRatings);
            router.get('/api/metadata/people', people);
            function listDocs() {}
            function bulkEdit() {}
            function notes() {}
            function ageRatings() {}
            function people() {}
        ''',
        'web/abstract.service.ts': '''
            export abstract class AbstractService<T> {
              protected baseUrl: string = '/api/'
              protected resourceName: string
              protected getResourceUrl(id: number = null, action: string = null): string {
                let url = `${this.baseUrl}${this.resourceName}/`
                if (id !== null) {
                  url += `${id}/`
                }
                if (action) {
                  url += `${action}/`
                }
                return url
              }
              list() {
                return this.http.get(this.getResourceUrl())
              }
            }
        ''',
        'web/document.service.ts': '''
            import { AbstractService } from './abstract.service'
            export class DocumentService extends AbstractService<Doc> {
              constructor() {
                super()
                this.resourceName = 'documents'
              }
              bulkEdit(ids) {
                return this.http.post(this.getResourceUrl(null, 'bulk_edit'), { ids })
              }
              getNotes(documentId: number) {
                return this.http.get(this.getResourceUrl(documentId, 'notes'))
              }
            }
        ''',
        'web/metadata.service.ts': '''
            export class MetadataService {
              baseUrl = environment.apiUrl;
              getAllAgeRatings(libraries?: Array<number>) {
                let method = 'metadata/age-ratings'
                if (libraries != undefined && libraries.length > 0) {
                  method += '?libraryIds=' + libraries.join(',');
                }
                return this.httpClient.get(this.baseUrl + method);
              }
            }
        ''',
    })
    bulk = node_at(nodes, 'web/document.service.ts', 'bulkEdit')
    assert linked(nodes, edges, ('http', 'handles'), bulk, node_at(nodes, 'server/routes.js', 'bulkEdit'))
    get_notes = node_at(nodes, 'web/document.service.ts', 'getNotes')
    assert linked(nodes, edges, ('http', 'handles'), get_notes, node_at(nodes, 'server/routes.js', 'notes'))
    assert not linked(nodes, edges, ('http', 'handles'), get_notes, node_at(nodes, 'server/routes.js', 'listDocs'))
    ages = node_at(nodes, 'web/metadata.service.ts', 'getAllAgeRatings')
    assert not linked(nodes, edges, ('http', 'handles'), ages, node_at(nodes, 'server/routes.js', 'people'))


# ------------------------------------------------------------------------------------------------------------- precisión

def test_nothing_from_comments_or_docstrings(tmp_path):
    nodes, edges = run(tmp_path, {
        'lib/connection.js': '''
            const mongoose = require('mongoose');
            /**
             * Defines a model on this connection.
             *
             * @example
             *     const Test = conn.model('Test', schema);
             *     const Ticket = mongoose.model('Ticket', schema, 'tickets');
             *     router.get('/examples/:id', showExample);
             *     process.env.EXAMPLE_SECRET
             */
            Connection.prototype.model = function(name, schema) {
              return this.models[name];
            };
        ''',
        'app/helpers.py': '''
            def describe():
                """Usage::

                    class Invoice(models.Model):
                        __tablename__ = "invoices"

                    @app.route("/docs/example")
                    def example(): ...
                """
                return None
        ''',
        'src/main/java/app/Docs.java': '''
            package app;
            /**
             * Example:
             * <pre>
             * @Entity
             * @Table(name = "widgets")
             * public class Widget { }
             * </pre>
             */
            public class Docs { }
        ''',
        '.env.example': 'EXAMPLE_SECRET=x\n',
    })
    assert not any(n.get('table') for n in nodes.values()), [n for n in nodes.values() if n.get('table')]
    assert not any(n.get('kind') == 'endpoint' for n in nodes.values())
    assert not any(k == 'env' and a.startswith(('f:lib/', 'm:lib/')) for a, b, k in edges)


def test_socket_annotation_without_path_does_not_crash(tmp_path):
    nodes, edges = run(tmp_path, {
        'src/main/java/app/Broker.java': '''
            package app;
            @WebSocket
            public class Broker {
                public void onMessage(String m) { }
            }
        ''',
        'src/main/java/app/Chat.java': '''
            package app;
            @ServerEndpoint(value = "/chat")
            public class Chat { }
        ''',
    })
    assert any(n.get('kind') == 'endpoint' and n.get('name', '').endswith('/chat') for n in nodes.values())


def test_scanner_failure_is_recorded_and_analysis_continues(tmp_path, monkeypatch):
    from cortex_graph import bridges

    def boom(self, src):
        if src.rel.endswith('broken.py'):
            raise RuntimeError('scanner exploded')
        return original(self, src)

    original = bridges.Bridges.scan_registrations
    monkeypatch.setattr(bridges.Bridges, 'scan_registrations', boom)
    monkeypatch.setattr(bridges.Bridges, 'finish_jobs', lambda self: 1 / 0)
    out = analyze(write_repo(tmp_path / 'repo', {
        'app/broken.py': 'def f():\n    return 1\n',
        'app/routes.py': '@app.route("/ok")\ndef ok():\n    return 1\n',
    }), git=False)
    warnings = out['meta']['warnings'] if 'meta' in out else out['stats']['warnings']
    assert any('scanner exploded' in w['error'] and w['file'] == 'app/broken.py' for w in warnings)
    assert any('finish_jobs' in w['error'] for w in warnings)
    assert any(n.get('kind') == 'endpoint' for n in out['nodes'])


# ------------------------------------------------------------------------------------------------------------- rutas

def test_framework_types_by_repo_inheritance(tmp_path):
    nodes, edges = run(tmp_path, {
        'src/Http/VersionedApiControllerAttribute.cs': '''
            namespace App.Http
            {
                public class VersionedApiControllerAttribute : Attribute, IRouteTemplateProvider
                {
                    public const string CONTROLLER_RESOURCE = "[controller]";
                    public VersionedApiControllerAttribute(int version, string resource = CONTROLLER_RESOURCE)
                    {
                        Template = $"api/v{version}/{resource}";
                    }
                    public string Template { get; }
                }

                public class V2ApiControllerAttribute : VersionedApiControllerAttribute
                {
                    public V2ApiControllerAttribute(string resource = "[controller]")
                        : base(2, resource)
                    {
                    }
                }
            }
        ''',
        'src/Http/RestPostByIdAttribute.cs': '''
            namespace App.Http
            {
                [AttributeUsage(AttributeTargets.Method)]
                public class RestPostByIdAttribute : HttpPostAttribute
                {
                }

                public class RestDeleteByIdAttribute : HttpDeleteAttribute
                {
                    public RestDeleteByIdAttribute()
                        : base("{id:int}")
                    {
                    }
                }
            }
        ''',
        'src/Api/TagController.cs': '''
            namespace App.Api
            {
                [V2ApiController]
                public class TagController : RestController<Tag>
                {
                    [HttpGet]
                    public List<Tag> GetAll() { return null; }

                    [RestPostById]
                    public Tag Create([FromBody] Tag tag) { return tag; }

                    [RestDeleteById]
                    public void DeleteTag(int id) { }
                }

                [V2ApiController("exclusions")]
                public class ExclusionController : RestController<Exclusion>
                {
                    [HttpGet("paged")]
                    public List<Exclusion> Paged() { return null; }
                }
            }
        ''',
        'app/routers.py': 'from fastapi import APIRouter\n\nclass UserAPIRouter(APIRouter):\n    pass\n',
        'app/routes/items.py': '''
            from app.routers import UserAPIRouter

            router = UserAPIRouter(prefix="/items", tags=["Items"])

            @router.get("/self")
            def read_self():
                return {}
        ''',
    })
    names = {n['name'] for n in nodes.values() if n.get('kind') == 'endpoint'}
    assert any(x.lower() == 'get /api/v2/tag' for x in names), names
    assert any(x.lower() == 'post /api/v2/tag' for x in names), names
    assert any(x.lower() == 'get /api/v2/exclusions/paged' for x in names), names
    assert any(x.lower().startswith('delete /api/v2/tag/:') for x in names), names
    assert 'GET /items/self' in names, names


def test_request_options_object_wrappers(tmp_path):
    nodes, edges = run(tmp_path, {
        'src/Api/TagController.cs': '''
            namespace App.Api
            {
                [Route("api/v3/tag")]
                public class TagController : Controller
                {
                    [HttpGet]
                    public List<Tag> GetAll() { return null; }
                    [HttpGet("{id}")]
                    public Tag Get(int id) { return null; }
                    [HttpPost]
                    public Tag Create(Tag t) { return t; }
                    [HttpDelete("{id}")]
                    public void Delete(int id) { }
                }

                [Route("api/v3/filter")]
                public class FilterController : Controller
                {
                    [HttpPost]
                    public Filter Add(Filter f) { return f; }
                    [HttpPut("{id}")]
                    public Filter Update(Filter f) { return f; }
                }
            }
        ''',
        'frontend/src/Utilities/createAjaxRequest.js': '''
            import $ from 'jquery';
            const apiRoot = window.App.apiRoot;
            function addRootUrl(ajaxOptions) {
              ajaxOptions.url = apiRoot + ajaxOptions.url;
            }
            export default function createAjaxRequest(originalAjaxOptions) {
              const ajaxOptions = { ...originalAjaxOptions };
              addRootUrl(ajaxOptions);
              const request = $.ajax({
                xhr: () => new XMLHttpRequest(),
                ...ajaxOptions
              });
              return { request };
            }
        ''',
        'frontend/src/Store/Creators/createFetchHandler.js': '''
            import createAjaxRequest from 'Utilities/createAjaxRequest';
            export default function createFetchHandler(section, url) {
              return function(getState, payload, dispatch) {
                const { id, ...other } = payload;
                const { request } = createAjaxRequest({
                  url: id == null ? url : `${url}/${id}`,
                  data: other
                });
                return request;
              };
            }
        ''',
        'frontend/src/Store/Creators/createRemoveItemHandler.js': '''
            import createAjaxRequest from 'Utilities/createAjaxRequest';
            function createRemoveItemHandler(section, url) {
              return function(getState, payload, dispatch) {
                const { id } = payload;
                const ajaxOptions = {
                  url: `${url}/${id}`,
                  method: 'DELETE'
                };
                return createAjaxRequest(ajaxOptions).request;
              };
            }
            export default createRemoveItemHandler;
        ''',
        'frontend/src/Store/Creators/createSaveProviderHandler.js': '''
            import createAjaxRequest from 'Utilities/createAjaxRequest';
            function createSaveProviderHandler(section, url, options = {}) {
              return function(getState, payload, dispatch) {
                const { id, ...other } = payload;
                const requestUrl = id ? `${url}/${id}` : url;
                const ajaxOptions = {
                  url: `${requestUrl}?${$.param(params, true)}`,
                  method: id ? 'PUT' : 'POST',
                  dataType: 'json'
                };
                const { request } = createAjaxRequest(ajaxOptions);
                return request;
              };
            }
            export default createSaveProviderHandler;
        ''',
        'frontend/src/Store/filterActions.js': '''
            import createSaveProviderHandler from './Creators/createSaveProviderHandler';
            export const actionHandlers = handleThunks({
              [SAVE_FILTER]: createSaveProviderHandler('filters', '/filter'),
            });
        ''',
        'frontend/src/Store/tagActions.js': '''
            import createAjaxRequest from 'Utilities/createAjaxRequest';
            import createFetchHandler from './Creators/createFetchHandler';
            import createRemoveItemHandler from './Creators/createRemoveItemHandler';
            export const actionHandlers = handleThunks({
              [FETCH_TAGS]: createFetchHandler('tags', '/tag'),
              [ADD_TAG]: function(getState, payload, dispatch) {
                const promise = createAjaxRequest({
                  url: '/tag',
                  method: 'POST',
                  data: JSON.stringify(payload.tag)
                }).request;
              },
              [DELETE_TAG]: createRemoveItemHandler('tags', '/tag'),
            });
        ''',
    })
    actions = 'm:frontend/src/Store/tagActions.js'
    ctrl = lambda name: node_at(nodes, 'src/Api/TagController.cs', name)
    assert linked(nodes, edges, ('http', 'handles'), actions, ctrl('GetAll'))
    assert linked(nodes, edges, ('http', 'handles'), actions, ctrl('Create'))
    assert linked(nodes, edges, ('http', 'handles'), actions, ctrl('Delete'))
    filters = 'm:frontend/src/Store/filterActions.js'
    assert linked(nodes, edges, ('http', 'handles'), filters, node_at(nodes, 'src/Api/TagController.cs', 'Add'))
    assert linked(nodes, edges, ('http', 'handles'), filters, node_at(nodes, 'src/Api/TagController.cs', 'Update'))


# ------------------------------------------------------------------------------------------------------------- datos

def test_sql_in_resource_files_and_named_entities(tmp_path):
    nodes, edges = run(tmp_path, {
        'pom.xml': '<project><modules><module>core</module></modules></project>\n',
        'sql/schema.sql': 'create table sys_user (\n  user_id bigint not null\n);\ncreate table sys_role (\n  role_id bigint\n);\n',
        'core/pom.xml': '<project><artifactId>core</artifactId></project>\n',
        'core/src/main/java/app/domain/SysUser.java': 'package app.domain;\npublic class SysUser extends BaseEntity {\n  private Long userId;\n}\n',
        'core/src/main/java/app/service/UserService.java': 'package app.service;\npublic class UserService {\n  void run() {}\n}\n',
        'core/src/main/resources/mapper/SysUserMapper.xml': '''<?xml version="1.0" encoding="UTF-8" ?>
<mapper namespace="app.mapper.SysUserMapper">
    <sql id="selectUserVo">
        select u.user_id from sys_user u
    </sql>
    <select id="selectUserList" resultMap="SysUserResult">
        <include refid="selectUserVo"/>
        where u.del_flag = '0'
        <if test="roleId != null"> and exists (select 1 from sys_role r where r.role_id = #{roleId})</if>
    </select>
</mapper>
''',
    })
    user = next(k for k, n in nodes.items() if n.get('table') == 'sys_user' and n.get('file') == 'sql/schema.sql')
    role = next(k for k, n in nodes.items() if n.get('table') == 'sys_role' and n.get('file') == 'sql/schema.sql')
    entity = node_at(nodes, 'core/src/main/java/app/domain/SysUser.java', 'SysUser')
    assert linked(nodes, edges, 'data', entity, user)
    stmt = node_at(nodes, 'core/src/main/resources/mapper/SysUserMapper.xml', 'selectUserList')
    assert linked(nodes, edges, 'data', stmt, role)
    assert linked(nodes, edges, 'data', node_at(nodes, 'core/src/main/resources/mapper/SysUserMapper.xml', 'selectUserVo'), user)
    assert not any(k == 'data' and a.startswith('c:core/src/main/java/app/service') for a, b, k in edges)


def test_migration_dsl_tables_and_typed_table_mappings(tmp_path):
    nodes, edges = run(tmp_path, {
        'src/Core/Datastore/Migration/001_initial_setup.cs': '''
            namespace App.Core.Datastore.Migration
            {
                public class InitialSetup : AppMigrationBase
                {
                    protected override void MainDbUpgrade()
                    {
                        Create.TableForModel("Tags")
                              .WithColumn("Label").AsString().Unique();
                        Create.TableForModel("Blacklist")
                              .WithColumn("Title").AsString();
                    }
                }
            }
        ''',
        'src/Core/Datastore/Migration/150_rename_blacklist.cs': '''
            namespace App.Core.Datastore.Migration
            {
                public class rename_blacklist : AppMigrationBase
                {
                    protected override void MainDbUpgrade()
                    {
                        Rename.Table("Blacklist").To("Blocklist");
                    }
                }
            }
        ''',
        'src/Core/Datastore/TableMapping.cs': '''
            namespace App.Core.Datastore
            {
                public static class TableMapping
                {
                    public static void Map()
                    {
                        Mapper.Entity<Tag>("Tags").RegisterModel();
                        Mapper.Entity<Blocklist>("Blocklist").RegisterModel();
                        Mapper.Entity<Settings>("Unknown").RegisterModel();
                    }
                }
            }
        ''',
        'src/Core/Tags/Tag.cs': 'namespace App.Core.Tags\n{\n    public class Tag : ModelBase\n    {\n        public string Label { get; set; }\n    }\n}\n',
        'src/Core/Blocklisting/Blocklist.cs': 'namespace App.Core.Blocklisting\n{\n    public class Blocklist : ModelBase { }\n}\n',
        'src/Core/Settings.cs': 'namespace App.Core\n{\n    public class Settings { }\n}\n',
    })
    tags = next(k for k, n in nodes.items() if n.get('table') == 'Tags' and 'Migration' in n.get('file', ''))
    tag = node_at(nodes, 'src/Core/Tags/Tag.cs', 'Tag')
    assert linked(nodes, edges, 'data', tag, tags)
    assert linked(nodes, edges, 'data', node_at(nodes, 'src/Core/Datastore/TableMapping.cs', 'Map'), tag)
    black = next(k for k, n in nodes.items() if n.get('table') == 'Blacklist' and 'Migration' in n.get('file', ''))
    assert linked(nodes, edges, 'data', node_at(nodes, 'src/Core/Blocklisting/Blocklist.cs', 'Blocklist'), black)
    assert not linked(nodes, edges, 'data', node_at(nodes, 'src/Core/Datastore/TableMapping.cs', 'Map'),
                      node_at(nodes, 'src/Core/Settings.cs', 'Settings'))


# ------------------------------------------------------------------------------------------------------------- entorno

def test_config_keys_and_section_bound_types(tmp_path):
    nodes, edges = run(tmp_path, {
        # Spring: @Value, @ConditionalOnProperty, @ConfigurationProperties(prefix) y un YAML que no es application.yml
        'admin/src/main/resources/application.yml': 'app:\n  name: demo\nxss:\n  enabled: true\n  excludes: /system/notice\n',
        'gen/src/main/resources/generator.yml': 'gen:\n  author: someone\n  tablePrefix: sys_\n',
        'core/src/main/java/app/FilterConfig.java': '''
            package app;
            public class FilterConfig {
                @Value("${xss.excludes}")
                private String excludes;

                @Bean
                @ConditionalOnProperty(value = "xss.enabled", havingValue = "true")
                public Filter xss() { return null; }
            }
        ''',
        'core/src/main/java/app/AppConfig.java': '''
            package app;
            @Component
            @ConfigurationProperties(prefix = "app")
            public class AppConfig {
                private String name;
            }
        ''',
        'gen/src/main/java/app/GenConfig.java': '''
            package app;
            @Component
            @ConfigurationProperties(prefix = "gen")
            @PropertySource(value = { "classpath:generator.yml" })
            public class GenConfig {
                @Value("${author}")
                public void setAuthor(String author) { }
            }
        ''',
        # .NET: Configure<T>(GetSection("App:Server")) y lecturas de la propiedad a través de IOptions<T>
        'src/Common/Options/ServerOptions.cs': 'namespace App.Common\n{\n    public class ServerOptions\n    {\n        public int? Port { get; set; }\n'
                                              '        public string UrlBase { get; set; }\n    }\n}\n',
        'src/Host/Bootstrap.cs': '''
            namespace App.Host
            {
                public static class Bootstrap
                {
                    public static void Build(IServiceCollection services, IConfiguration config)
                    {
                        services.Configure<ServerOptions>(config.GetSection("App:Server"));
                    }
                }
            }
        ''',
        'src/Core/ConfigFileProvider.cs': '''
            namespace App.Core
            {
                public class ConfigFileProvider
                {
                    private readonly ServerOptions _serverOptions;
                    public ConfigFileProvider(IOptions<ServerOptions> serverOptions)
                    {
                        _serverOptions = serverOptions.Value;
                    }
                    public int Port => _serverOptions.Port ?? 8080;
                }
            }
        ''',
        # Go: koanf con `Unmarshal("db", &c)`, fichero `.toml.sample` y variables con prefijo del proveedor de entorno
        'config.toml.sample': '[app]\naddress = "localhost:9000"\n\n[db]\nhost = "localhost"\nport = 5432\n',
        'cmd/init.go': '''
            package main

            func initDB() {
            	var c struct {
            		Host string `koanf:"host"`
            		Port int    `koanf:"port"`
            	}
            	if err := ko.Unmarshal("db", &c); err != nil {
            		panic(err)
            	}
            }

            func initConfig() {
            	ko.Load(env.Provider("APP_", ".", func(s string) string { return s }), nil)
            	addr := ko.String("app.address")
            	_ = addr
            }
        ''',
        'docker-compose.yml': 'services:\n  app:\n    image: app\n    environment:\n      APP_db__host: db\n',
    })
    yml = 'm:admin/src/main/resources/application.yml'
    assert linked(nodes, edges, 'env', node_at(nodes, 'core/src/main/java/app/FilterConfig.java', 'xss'), yml)
    assert linked(nodes, edges, 'env', node_at(nodes, 'core/src/main/java/app/AppConfig.java', 'AppConfig'), yml)
    gen = node_at(nodes, 'gen/src/main/java/app/GenConfig.java', 'setAuthor')
    assert linked(nodes, edges, 'env', gen, 'm:gen/src/main/resources/generator.yml')
    port = node_at(nodes, 'src/Core/ConfigFileProvider.cs', 'ConfigFileProvider')
    assert linked(nodes, edges, 'env', port, node_at(nodes, 'src/Common/Options/ServerOptions.cs', 'ServerOptions'))
    assert linked(nodes, edges, 'depends', node_at(nodes, 'src/Host/Bootstrap.cs', 'Build'),
                  node_at(nodes, 'src/Common/Options/ServerOptions.cs', 'ServerOptions'))
    sample = next(k for k, n in nodes.items() if n.get('file') == 'config.toml.sample' and n.get('kind') == 'module')
    assert linked(nodes, edges, 'env', node_at(nodes, 'cmd/init.go', 'initDB'), sample)
    assert linked(nodes, edges, 'env', node_at(nodes, 'cmd/init.go', 'initConfig'), sample)


# ------------------------------------------------------------------------------------------------------------- servicios

def test_build_module_dependencies(tmp_path):
    nodes, edges = run(tmp_path, {
        'pom.xml': '<project>\n  <artifactId>shop</artifactId>\n  <modules><module>shop-web</module><module>shop-core</module></modules>\n</project>\n',
        'shop-core/pom.xml': '<project>\n  <parent><artifactId>shop</artifactId></parent>\n  <artifactId>shop-core</artifactId>\n</project>\n',
        'shop-web/pom.xml': '<project>\n  <parent><artifactId>shop</artifactId></parent>\n  <artifactId>shop-web</artifactId>\n'
                            '  <dependencies>\n    <dependency>\n      <groupId>x</groupId>\n      <artifactId>shop-core</artifactId>\n'
                            '    </dependency>\n    <dependency><artifactId>spring-web</artifactId></dependency>\n  </dependencies>\n</project>\n',
        'src/App.Core/App.Core.csproj': '<Project Sdk="Microsoft.NET.Sdk">\n</Project>\n',
        'src/App.Host/App.Host.csproj': '<Project Sdk="Microsoft.NET.Sdk">\n  <ItemGroup>\n'
                                        '    <ProjectReference Include="..\\App.Core\\App.Core.csproj" />\n  </ItemGroup>\n</Project>\n',
        'src/App.Host/Bootstrap.cs': 'namespace App.Host\n{\n    public static class Bootstrap\n    {\n'
                                     '        private static readonly List<string> ASSEMBLIES = new List<string>\n        {\n'
                                     '            "App.Core"\n        };\n    }\n}\n',
        'packages/schemas/package.json': '{\n  "name": "@acme/schemas",\n  "version": "1.0.0"\n}\n',
        'packages/core/package.json': '{\n  "name": "@acme/core",\n  "dependencies": {\n    "@acme/schemas": "workspace:^",\n'
                                      '    "koa": "^2.0.0"\n  }\n}\n',
    })
    assert ('m:shop-web/pom.xml', 'm:shop-core/pom.xml', 'depends') in edges
    assert ('m:src/App.Host/App.Host.csproj', 'm:src/App.Core/App.Core.csproj', 'depends') in edges
    assert linked(nodes, edges, 'depends', node_at(nodes, 'src/App.Host/Bootstrap.cs', 'Bootstrap'), 'm:src/App.Core/App.Core.csproj')
    assert ('m:packages/core/package.json', 'm:packages/schemas/package.json', 'depends') in edges


def test_go_channels_and_goroutines(tmp_path):
    nodes, edges = run(tmp_path, {
        'internal/manager/manager.go': '''
            package manager

            type Manager struct {
            	msgQ     chan Message
            	nextPipes chan *pipe
            }

            func (m *Manager) PushMessage(msg Message) error {
            	select {
            	case m.msgQ <- msg:
            	default:
            		return errQueueFull
            	}
            	return nil
            }

            func (m *Manager) Run() {
            	go m.worker()
            	for p := range m.nextPipes {
            		p.next()
            	}
            }

            func (m *Manager) worker() {
            	for {
            		select {
            		case msg, ok := <-m.msgQ:
            			if !ok {
            				return
            			}
            			send(msg)
            		}
            	}
            }
        ''',
        'cmd/tx.go': '''
            package main

            func handleSendTxMessage(app *App) error {
            	if err := app.manager.PushMessage(msg); err != nil {
            		return err
            	}
            	return nil
            }
        ''',
        'cmd/main.go': 'package main\n\nfunc main() {\n\tgo mgr.Run()\n}\n',
    })
    worker = node_at(nodes, 'internal/manager/manager.go', 'worker')
    assert linked(nodes, edges, 'event', node_at(nodes, 'internal/manager/manager.go', 'PushMessage'), worker)
    assert linked(nodes, edges, 'event', node_at(nodes, 'cmd/tx.go', 'handleSendTxMessage'), worker)
    assert linked(nodes, edges, 'event', node_at(nodes, 'internal/manager/manager.go', 'Run'), worker)
    assert linked(nodes, edges, 'event', node_at(nodes, 'cmd/main.go', 'main'), node_at(nodes, 'internal/manager/manager.go', 'Run'))


def test_sql_template_identifiers_foreign_keys_and_alterations(tmp_path):
    nodes, edges = run(tmp_path, {
        'packages/schemas/package.json': '{"name": "@acme/schemas"}',
        'packages/schemas/tables/roles.sql': 'create table roles (\n  id varchar(21) not null,\n  primary key (id)\n);\n',
        'packages/schemas/tables/users_roles.sql': 'create table users_roles (\n  id varchar(21) not null,\n'
                                                   '  role_id varchar(21) not null\n    references roles (id) on delete cascade\n);\n',
        'packages/schemas/alterations/1.0.0-roles.ts': '''
            import { sql } from 'slonik';
            const alteration = {
              up: async (pool) => {
                await pool.query(sql`
                  create table roles (
                    id varchar(21) not null
                  );
                `);
              },
            };
            export default alteration;
        ''',
        'packages/core/package.json': '{"name": "@acme/core"}',
        'packages/core/src/queries/roles.ts': '''
            import { Roles, UsersRoles } from '@acme/schemas';
            import { sql } from 'slonik';
            import { convertToIdentifiers } from '../utils/sql.js';

            const { table, fields } = convertToIdentifiers(Roles);

            export const createRolesQueries = (pool) => {
              const findRoles = async () =>
                pool.any(sql`
                  select ${fields.id}
                  from ${table}
                `);
              const deleteUserRoles = async (id) =>
                pool.query(sql`
                  delete from ${UsersRoles.table} where id = ${id}
                `);
              return { findRoles, deleteUserRoles };
            };
        ''',
    })
    roles = next(k for k, n in nodes.items() if n.get('table') == 'roles' and n.get('file', '').endswith('roles.sql') and 'users' not in n['file'])
    users_roles = next(k for k, n in nodes.items() if n.get('table') == 'users_roles')
    find = node_at(nodes, 'packages/core/src/queries/roles.ts', 'findRoles') if any(
        n.get('name', '').endswith('findRoles') for n in nodes.values()) else 'f:packages/core/src/queries/roles.ts:createRolesQueries'
    queries = [k for k, n in nodes.items() if n.get('file') == 'packages/core/src/queries/roles.ts' and n.get('kind') in ('function', 'method')]
    assert any(linked(nodes, edges, 'data', q, roles) for q in queries), find
    assert any(linked(nodes, edges, 'data', q, users_roles) for q in queries)
    assert linked(nodes, edges, 'data', users_roles, roles)
    alter = next(k for k, n in nodes.items() if n.get('table') == 'roles' and 'alterations' in n.get('file', ''))
    assert linked(nodes, edges, 'data', alter, roles)


def test_route_constants_and_router_passing_mounts(tmp_path):
    nodes, edges = run(tmp_path, {
        'src/routes/domain.ts': '''
            export default function domainRoutes<T extends Router>(...[router, tenant]: RouterInitArgs<T>) {
              const filesPath = '/domains/:id/files';
              router.get(filesPath, async (ctx, next) => { ctx.body = []; return next(); });
              router.put(filesPath, async (ctx, next) => next());
            }
        ''',
        'src/routes/init.ts': '''
            import Router from 'koa-router';
            import domainRoutes from './domain';
            const createRouters = (tenant) => {
              const managementRouter = new Router();
              managementRouter.use(auth());
              domainRoutes(managementRouter, tenant);
              return [managementRouter];
            };
            export default createRouters;
        ''',
    })
    names = {n['name'] for n in nodes.values() if n.get('kind') == 'endpoint'}
    assert 'GET /domains/:id/files' in names and 'PUT /domains/:id/files' in names, names
    assert linked(nodes, edges, 'handles', node_at(nodes, 'src/routes/init.ts', 'createRouters'), node_at(nodes, 'src/routes/domain.ts', 'domainRoutes'))


def test_repository_factory_properties(tmp_path):
    nodes, edges = run(tmp_path, {
        'app/db/models/cookbook.py': 'from app.db.base import SqlAlchemyBase\n\nclass CookBook(SqlAlchemyBase):\n    __tablename__ = "cookbooks"\n',
        'app/repos/generic.py': '''
            class RepositoryGeneric:
                def __init__(self, session, pk, model):
                    self.model = model
                def create(self, data): ...
                def get_one(self, value): ...
                def update(self, match, data): ...
                def delete(self, value): ...
        ''',
        'app/repos/factory.py': '''
            from functools import cached_property
            from app.db.models.cookbook import CookBook
            from app.repos.generic import RepositoryGeneric

            class AllRepositories:
                @cached_property
                def cookbooks(self) -> RepositoryGeneric:
                    return RepositoryGeneric(self.session, "id", CookBook)
        ''',
        'app/routes/cookbooks.py': '''
            class CookbookController:
                def get_all(self):
                    return self.repos.cookbooks.page_all(None)
        ''',
    })
    model = node_at(nodes, 'app/db/models/cookbook.py', 'CookBook')
    assert linked(nodes, edges, 'data', node_at(nodes, 'app/repos/factory.py', 'cookbooks'), model)
    assert linked(nodes, edges, 'data', node_at(nodes, 'app/routes/cookbooks.py', 'get_all'), model)


def test_namespace_qualified_handlers(tmp_path):
    nodes, edges = run(tmp_path, {
        'app/Http/Controllers/Api/Client/ActivityLogController.php': '<?php\nnamespace App\\Http\\Controllers\\Api\\Client;\n'
                                                                       'class ActivityLogController\n{\n    public function __invoke() { }\n}\n',
        'app/Http/Controllers/Api/Client/Servers/ActivityLogController.php': '<?php\nnamespace App\\Http\\Controllers\\Api\\Client\\Servers;\n'
                                                                               'class ActivityLogController\n{\n    public function __invoke() { }\n}\n',
        'app/Http/Controllers/Api/Client/Servers/DatabaseController.php': '<?php\nnamespace App\\Http\\Controllers\\Api\\Client\\Servers;\n'
                                                                            'class DatabaseController\n{\n    public function index() { }\n}\n',
        'app/Http/Controllers/Admin/DatabaseController.php': '<?php\nnamespace App\\Http\\Controllers\\Admin;\n'
                                                             'class DatabaseController\n{\n    public function index() { }\n}\n',
        'routes/api-client.php': (
            "<?php\n"
            "use Illuminate\\Support\\Facades\\Route;\n"
            "use App\\Http\\Controllers\\Api\\Client;\n\n"
            "Route::get('/activity', Client\\ActivityLogController::class);\n"
            "Route::group(['prefix' => '/servers/{server}'], function () {\n"
            "    Route::get('/activity', Client\\Servers\\ActivityLogController::class);\n"
            "    Route::get('/databases', [Client\\Servers\\DatabaseController::class, 'index']);\n"
            "});\n"),
    })
    handles = {(nodes[a]['name'], b) for a, b, k in edges if k == 'handles' and nodes[a].get('kind') == 'endpoint'}
    assert ('GET /activity', 'f:app/Http/Controllers/Api/Client/ActivityLogController.php:ActivityLogController.__invoke') in handles, handles
    assert any(e.endswith('/servers/:server/databases') and t.startswith('f:app/Http/Controllers/Api/Client/Servers/') for e, t in handles), handles


def test_dockerfile_and_compose_references(tmp_path):
    nodes, edges = run(tmp_path, {
        'config.toml.sample': '[app]\naddress = "0.0.0.0:9000"\n',
        'docker-entrypoint.sh': '#!/bin/sh\nset -e\nexec "$@"\n',
        'docker/nginx.conf': 'server { listen 80; }\n',
        'Dockerfile': 'FROM alpine:latest AS production\nWORKDIR /app\nCOPY config.toml.sample config.toml\n'
                      'COPY docker/nginx.conf /etc/nginx/nginx.conf\nCOPY docker-entrypoint.sh /usr/local/bin/\n'
                      'VOLUME /app/data\nEXPOSE 9000\nENTRYPOINT ["docker-entrypoint.sh"]\nCMD ["./app"]\n',
        'docker-compose.yml': 'services:\n  app:\n    build:\n      context: .\n      target: production\n    ports:\n'
                              '      - "9091:9000"\n    volumes:\n      - app-data:/app/data\nvolumes:\n  app-data:\n',
    })
    dock = 'm:Dockerfile'
    owners = {k for k, n in nodes.items() if n.get('file') == 'Dockerfile'}
    assert any(linked(nodes, edges, 'depends', o, 'm:config.toml.sample') for o in owners)
    assert any(linked(nodes, edges, 'depends', o, 'm:docker-entrypoint.sh') for o in owners)
    assert any(linked(nodes, edges, 'depends', o, 'm:docker/nginx.conf') for o in owners)
    app = next(k for k, n in nodes.items() if n.get('file') == 'docker-compose.yml' and n.get('name') == 'app')
    assert any(linked(nodes, edges, 'depends', app, o) for o in owners | {dock})


def test_erb_env_reads_in_yaml(tmp_path):
    nodes, edges = run(tmp_path, {
        '.env.example': 'REDIS_URL=redis://redis:6379\nPOSTGRES_HOST=postgres\n',
        'config/cable.yml': "production:\n  adapter: redis\n  url: <%= ENV.fetch('REDIS_URL', 'redis://127.0.0.1:6379') %>\n",
        'config/database.yml': "default: &default\n  host: <%= ENV['POSTGRES_HOST'] %>\n",
    })
    assert linked(nodes, edges, 'env', 'm:config/cable.yml', 'm:.env.example')
    assert linked(nodes, edges, 'env', 'm:config/database.yml', 'm:.env.example')


def test_wrapped_handler_resolved_by_receiver_type(tmp_path):
    nodes, edges = run(tmp_path, {
        'cmd/handlers.go': '''
            package main

            func initHTTPHandlers(e *echo.Echo, a *App) {
            	g := e.Group("")
            	g.GET("/api/campaigns/:id", pm(hasID(a.GetCampaign), auth.PermCampaignsGet))
            }
        ''',
        'cmd/campaigns.go': 'package main\n\nfunc (a *App) GetCampaign(c *echo.Context) error {\n\treturn nil\n}\n',
        'internal/core/campaigns.go': 'package core\n\nfunc (c *Core) GetCampaign(id int) error {\n\treturn nil\n}\n',
    })
    handles = {(nodes[a]['name'], b) for a, b, k in edges if k == 'handles' and nodes[a].get('kind') == 'endpoint'}
    assert ('GET /api/campaigns/:id', 'f:cmd/campaigns.go:App.GetCampaign') in handles, handles
