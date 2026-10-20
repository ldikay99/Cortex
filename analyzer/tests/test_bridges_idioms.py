"""Idiomas transversales de la ronda 5 (bench/flows): cada caso declara la forma canónica documentada de un idioma y una o dos
variantes habituales (alias, otros ficheros, anotaciones con argumentos, configuración en plantillas/compose). Repos sintéticos, sin
nombres ni rutas del benchmark."""
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


def table_node(nodes, rel, name):
    return next(k for k, n in nodes.items() if n.get('file') == rel and str(n.get('table', '')).lower() == name.lower())


# ------------------------------------------------------------------------------------------------------------------- datos

def test_query_builder_table_literals(tmp_path):
    nodes, edges = run(tmp_path, {
        'server/package.json': '{"name": "server"}',
        'server/src/migrations/001-comments.ts': '''
            import { Kysely } from 'kysely';

            export async function up(db: Kysely<any>): Promise<void> {
              await db.schema
                .createTable('comments')
                .addColumn('id', 'uuid')
                .execute();
            }
        ''',
        'server/src/repos/comment.repo.ts': '''
            export class CommentRepo {
              constructor(private db: any) {}

              async findById(id: string) {
                return this.db
                  .selectFrom('comments')
                  .selectAll('comments')
                  .where('id', '=', id)
                  .executeTakeFirst();
              }

              async insert(values: any) {
                return this.db.insertInto('comments').values(values).execute();
              }

              async remove(id: string) {
                await this.db.deleteFrom("comments").where('id', '=', id).execute();
              }

              async split(text: string) {
                return Array.from('comments');
              }
            }
        ''',
        'server/db/schema.sql': 'CREATE TABLE orders (id int primary key);\n',
        'server/src/orders.js': '''
            export async function listOrders(supabase) {
              const { data } = await supabase.from('orders').select('*');
              return data;
            }

            export async function joinOrders(qb) {
              return qb.table('users').innerJoin('orders', 'orders.user_id', 'users.id');
            }
        ''',
    })
    table = table_node(nodes, 'server/src/migrations/001-comments.ts', 'comments')
    for fn in ('findById', 'insert', 'remove'):
        assert linked(nodes, edges, 'data', f'f:server/src/repos/comment.repo.ts:CommentRepo.{fn}', table)
    assert not linked(nodes, edges, 'data', 'f:server/src/repos/comment.repo.ts:CommentRepo.split', table)
    orders = table_node(nodes, 'server/db/schema.sql', 'orders')
    assert linked(nodes, edges, 'data', 'f:server/src/orders.js:listOrders', orders)
    assert linked(nodes, edges, 'data', 'f:server/src/orders.js:joinOrders', orders)


def test_rust_table_macro_and_attribute(tmp_path):
    nodes, edges = run(tmp_path, {
        'Cargo.toml': '[package]\nname = "app"\n',
        'src/db/schema.rs': '''
            table! {
                folders (uuid) {
                    uuid -> Text,
                    name -> Text,
                }
            }

            diesel::table! {
                sends (uuid) {
                    uuid -> Text,
                }
            }
        ''',
        'src/db/models/folder.rs': '''
            use crate::db::schema::folders;

            #[derive(Identifiable, Queryable, Insertable)]
            #[diesel(table_name = folders)]
            #[diesel(primary_key(uuid))]
            pub struct Folder {
                pub uuid: String,
            }

            impl Folder {
                pub fn delete(&self, conn: &mut Conn) {
                    diesel::delete(folders::table.filter(folders::uuid.eq(&self.uuid))).execute(conn);
                }
            }
        ''',
        'src/db/models/send.rs': '''
            #[derive(Queryable)]
            #[table_name = "sends"]
            pub struct Send {
                pub uuid: String,
            }
        ''',
        'migrations/sqlite/2018-01-01_create/up.sql': 'CREATE TABLE folders (uuid TEXT PRIMARY KEY, name TEXT);\nCREATE TABLE sends (uuid TEXT);\n',
    })
    folders = table_node(nodes, 'src/db/schema.rs', 'folders')
    sends = table_node(nodes, 'src/db/schema.rs', 'sends')
    sql = table_node(nodes, 'migrations/sqlite/2018-01-01_create/up.sql', 'folders')
    assert linked(nodes, edges, 'data', 'c:src/db/models/folder.rs:Folder', folders)
    assert linked(nodes, edges, 'data', 'c:src/db/models/send.rs:Send', sends)
    assert linked(nodes, edges, 'data', 'f:src/db/models/folder.rs:Folder.delete', folders)
    assert linked(nodes, edges, 'data', folders, sql)


def test_annotated_table_models(tmp_path):
    nodes, edges = run(tmp_path, {
        'pom.xml': '<project/>',
        'src/main/java/app/model/Project.java': '''
            package app.model;

            @PersistenceCapable(table = "PROJECT")
            @FetchGroups({
                @FetchGroup(name = "ALL", members = {})
            })
            public class Project implements Serializable {
                private long id;
            }
        ''',
        'src/main/java/app/model/Component.java': '''
            package app.model;

            /**
             * A component.
             */
            @PersistenceCapable
            @Index(name = "COMPONENT_IDX", members = {"name"})
            public class Component implements Serializable {
                private String name;
            }
        ''',
        'src/main/java/app/model/Account.java': '''
            package app.model;

            @DatabaseTable(tableName = "accounts")
            public class Account {
                private String name;
            }
        ''',
        'src/main/resources/migration/V1__init.sql': '''
            CREATE TABLE "PROJECT" ("ID" bigint NOT NULL);
            CREATE TABLE "COMPONENT" ("ID" bigint NOT NULL);
            CREATE TABLE accounts (id bigint);
        ''',
    })
    sql = 'src/main/resources/migration/V1__init.sql'
    assert linked(nodes, edges, 'data', 'c:src/main/java/app/model/Project.java:Project', table_node(nodes, sql, 'PROJECT'))
    assert linked(nodes, edges, 'data', 'c:src/main/java/app/model/Component.java:Component', table_node(nodes, sql, 'COMPONENT'))
    assert linked(nodes, edges, 'data', 'c:src/main/java/app/model/Account.java:Account', table_node(nodes, sql, 'accounts'))


def test_python_model_inheritance(tmp_path):
    nodes, edges = run(tmp_path, {
        'src/core/models.py': '''
            from django.db import models


            class OwnedModel(models.Model):
                owner = models.ForeignKey("auth.User", null=True, on_delete=models.SET_NULL)

                class Meta:
                    abstract = True
        ''',
        'src/mail/models.py': '''
            from django.db import models

            import core.models as core_models


            class MailAccount(core_models.OwnedModel):
                name = models.CharField(max_length=256)


            class MailRule(MailAccount):
                order = models.IntegerField(default=0)
        ''',
        'src/mail/migrations/0001_initial.py': '''
            from django.db import migrations


            class Migration(migrations.Migration):
                operations = [
                    migrations.CreateModel(
                        name="MailAccount",
                        fields=[],
                    ),
                    migrations.CreateModel(
                        name="MailRule",
                        fields=[],
                    ),
                ]
        ''',
        'src/mail/tasks.py': '''
            from mail.models import MailAccount


            def process_accounts():
                for account in MailAccount.objects.all():
                    print(account)
        ''',
    })
    mig = 'src/mail/migrations/0001_initial.py'
    assert linked(nodes, edges, 'data', 'c:src/mail/models.py:MailAccount', table_node(nodes, mig, 'mail_account'))
    assert linked(nodes, edges, 'data', 'c:src/mail/models.py:MailRule', table_node(nodes, mig, 'mail_rule'))
    assert linked(nodes, edges, 'data', 'f:src/mail/tasks.py:process_accounts', 'c:src/mail/models.py:MailAccount')


# ------------------------------------------------------------------------------------------------------------------- entorno

def test_env_templates_and_compose_passthrough(tmp_path):
    nodes, edges = run(tmp_path, {
        'app.conf.example': '''
            # Required services

            #APP_REDIS=redis://localhost:6379
            #APP_DBHOST=localhost
            APP_SECRET_KEY=change-me
        ''',
        '.env.template': '''
            ## Main data folder
            # DATA_FOLDER=data
            # TMP_FOLDER=data/tmp
            ## A sentence, not a variable
        ''',
        'docker-compose.yml': '''
            services:
              app:
                image: app
                environment:
                  - SMTP_HOST
                  - LOG_LEVEL=info
        ''',
        'src/settings.py': '''
            import os


            def database():
                return {"HOST": os.getenv("APP_DBHOST"), "SECRET": os.environ["APP_SECRET_KEY"]}


            def data_dir():
                return os.environ.get("DATA_FOLDER", "data")
        ''',
        'src/Mail.java': '''
            public class Mail {
                String host() {
                    return System.getenv("SMTP_HOST");
                }
            }
        ''',
    })
    assert linked(nodes, edges, 'env', 'f:src/settings.py:database', 'm:app.conf.example')
    assert linked(nodes, edges, 'env', 'f:src/settings.py:data_dir', 'm:.env.template')
    assert linked(nodes, edges, 'env', 'f:src/Mail.java:Mail.host', 'm:docker-compose.yml')
    assert 'v:A_SENTENCE' not in nodes


def test_env_wrapper_functions_and_constant_names(tmp_path):
    nodes, edges = run(tmp_path, {
        'go.mod': 'module example.com/app\n',
        'config/keys.go': '''
            package config

            const (
            	EnvPort     = "APP_PORT"
            	EnvLogLevel = "APP_LOGLEVEL"
            )
        ''',
        'config/parse.go': '''
            package config

            import "os"

            func lookupEnv(env string) (string, bool) {
            	if raw, ok := os.LookupEnv(env); ok {
            		return raw, true
            	}
            	return "", false
            }

            func parseInt(target *int, env string) error {
            	raw, ok := lookupEnv(env)
            	_ = raw
            	_ = ok
            	return nil
            }
        ''',
        'config/config.go': '''
            package config

            type Configuration struct {
            	Port int
            }

            func Get() *Configuration {
            	c := &Configuration{}
            	parseInt(&c.Port, EnvPort)
            	return c
            }
        ''',
        'src/settings/base.py': '''
            import os


            def __get_boolean(key: str, default: str = "NO") -> bool:
                return os.getenv(key, default).lower() in ("yes", "true", "1")


            DEBUG = __get_boolean("APP_DEBUG")
        ''',
        '.env.example': 'APP_DEBUG=no\n',
    })
    assert linked(nodes, edges, 'env', 'f:config/config.go:Get', 'v:APP_PORT')
    assert linked(nodes, edges, 'env', 'f:config/config.go:Get', 'm:config/keys.go')
    assert linked(nodes, edges, 'env', 'm:src/settings/base.py', 'm:.env.example')
    assert 'v:APP_LOGLEVEL' not in nodes  # constante sin ninguna lectura


def test_config_key_constants(tmp_path):
    nodes, edges = run(tmp_path, {
        'pom.xml': '<project/>',
        'src/main/java/app/ConfigKeys.java': '''
            package app;

            public final class ConfigKeys {
                public static final String MANAGEMENT_HOST = "app.management.host";
                public static final String UNUSED_KEY = "app.not.defined";
            }
        ''',
        'src/main/java/app/Application.java': '''
            package app;

            public class Application {
                void start(Config config) {
                    String host = config.getOptionalValue(ConfigKeys.MANAGEMENT_HOST, String.class).orElse("0.0.0.0");
                }
            }
        ''',
        'src/main/kotlin/app/Jobs.kt': '''
            package app

            const val JOB_CRON = "app.jobs.cron"

            class Jobs(private val config: Config) {
                fun schedule() = config.getValue(JOB_CRON, String::class.java)
            }
        ''',
        'src/main/resources/application.properties': 'app.management.host=0.0.0.0\napp.jobs.cron=0 * * * *\n',
    })
    props = 'm:src/main/resources/application.properties'
    assert linked(nodes, edges, 'env', 'f:src/main/java/app/Application.java:Application.start', props)
    assert linked(nodes, edges, 'env', 'f:src/main/kotlin/app/Jobs.kt:Jobs.schedule', props)


def test_config_block_fields_bound_to_env(tmp_path):
    nodes, edges = run(tmp_path, {
        'Cargo.toml': '[package]\nname = "app"\n',
        '.env.template': '# DATA_FOLDER=data\n# ICON_CACHE_FOLDER=data/icon_cache\n',
        'src/config.rs': '''
            make_config! {
                folders {
                    /// Data folder
                    data_folder:        String, false, def, "data".to_owned();
                    /// Icon cache folder
                    icon_cache_folder:  String, false, auto, |c| format!("{}/icon_cache", c.data_folder);
                    /// Not an env var
                    some_other_value:   String, false, def, "x".to_owned();
                },
            }
        ''',
        'app/settings.py': '''
            from dataclasses import dataclass


            @dataclass
            class Settings:
                database_url: str = "sqlite://"
                worker_count: int = 4
        ''',
        '.env.example': 'DATABASE_URL=postgres://localhost/app\n',
    })
    assert linked(nodes, edges, 'env', 'm:src/config.rs', 'm:.env.template')
    assert 'v:SOME_OTHER_VALUE' not in nodes
    assert any(linked(nodes, edges, 'env', n, 'm:.env.example') for n in nodes if nodes[n].get('file') == 'app/settings.py')


# ------------------------------------------------------------------------------------------------------------------- eventos

def test_signals_connect_send_and_receiver(tmp_path):
    nodes, edges = run(tmp_path, {
        'src/documents/signals/__init__.py': '''
            from django.dispatch import Signal

            document_done = Signal()
        ''',
        'src/documents/signals/handlers.py': '''
            def add_tags(sender, document=None, **kwargs):
                return document


            def set_owner(sender, document=None, **kwargs):
                return document
        ''',
        'src/documents/apps.py': '''
            from django.apps import AppConfig


            class DocumentsConfig(AppConfig):
                def ready(self):
                    from documents.signals import document_done
                    from documents.signals import handlers

                    document_done.connect(handlers.add_tags)
                    document_done.connect(handlers.set_owner, dispatch_uid="owner")
        ''',
        'src/documents/consumer.py': '''
            from documents.signals import document_done


            class Consumer:
                def finish(self, document):
                    document_done.send(sender=self.__class__, document=document)
        ''',
        'src/documents/audit.py': '''
            from django.dispatch import receiver

            from documents.signals import document_done


            @receiver(document_done)
            def audit_document(sender, document=None, **kwargs):
                return document
        ''',
        'src/accounts/apps.py': '''
            from django.contrib.auth.signals import user_login_failed

            from accounts.signals import handle_failed_login


            def ready():
                user_login_failed.connect(handle_failed_login)
        ''',
        'src/accounts/signals.py': '''
            def handle_failed_login(sender, credentials, request, **kwargs):
                return None
        ''',
    })
    send = 'f:src/documents/consumer.py:Consumer.finish'
    assert linked(nodes, edges, 'event', send, 'f:src/documents/signals/handlers.py:add_tags')
    assert linked(nodes, edges, 'event', send, 'f:src/documents/signals/handlers.py:set_owner')
    assert linked(nodes, edges, 'event', send, 'f:src/documents/audit.py:audit_document')
    assert linked(nodes, edges, 'event', 'f:src/documents/apps.py:DocumentsConfig.ready', 'f:src/documents/signals/handlers.py:add_tags')
    assert linked(nodes, edges, 'event', 'f:src/accounts/apps.py:ready', 'f:src/accounts/signals.py:handle_failed_login')


def test_qualified_key_dispatch(tmp_path):
    nodes, edges = run(tmp_path, {
        'package.json': '{"name": "srv"}',
        'src/queue/constants.ts': '''
            export enum QueueJob {
              SEND_EMAIL = 'send-email',
              ADD_WATCHERS = 'add-watchers',
            }
            export enum JobName {
              Cleanup = 'cleanup',
            }
        ''',
        'src/mail/mail.service.ts': '''
            import { QueueJob } from '../queue/constants';

            export class MailService {
              constructor(private queue: any) {}

              async sendMail(message: any) {
                await this.queue.add(QueueJob.SEND_EMAIL, { message });
              }

              async watch(pageId: string) {
                this.queue
                  .add(QueueJob.ADD_WATCHERS, { pageId })
                  .catch(() => null);
              }
            }
        ''',
        'src/queue/general.processor.ts': '''
            import { QueueJob } from './constants';

            export class GeneralProcessor {
              async process(job: any): Promise<void> {
                switch (job.name) {
                  case QueueJob.SEND_EMAIL: {
                    return this.send(job.data);
                  }
                  case QueueJob.ADD_WATCHERS:
                    return;
                }
              }

              async send(data: any) {}
            }
        ''',
        'src/services/session.service.ts': '''
            import { JobName } from '../queue/constants';

            export class SessionService {
              @OnJob({ name: JobName.Cleanup, queue: QueueName.Background })
              async handleCleanup() {
                return true;
              }

              async onBoot() {
                await this.jobRepository.queue({ name: JobName.Cleanup });
              }
            }
        ''',
        'src/services/manual.ts': '''
            import { JobName } from '../queue/constants';

            export function asJob(name: string) {
              switch (name) {
                case 'session-cleanup': {
                  return { name: JobName.Cleanup };
                }
              }
            }
        ''',
        'src/mail/email.processor.ts': '''
            import { Processor, WorkerHost } from '@nestjs/bullmq';
            import { QueueName } from '../queue/constants';

            @Processor(QueueName.EMAIL_QUEUE)
            export class EmailProcessor extends WorkerHost {
              async process(job: any): Promise<void> {
                return;
              }
            }
        ''',
        'src/mail/mailer.ts': '''
            import { InjectQueue } from '@nestjs/bullmq';
            import { QueueName } from '../queue/constants';

            export class Mailer {
              constructor(@InjectQueue(QueueName.EMAIL_QUEUE) private readonly emailQueue: Queue) {}

              async deliver(message: any) {
                await this.emailQueue.add('send-email', message);
              }
            }
        ''',
        'src/history/history.processor.ts': '''
            export class HistoryProcessor {
              async process(job: any): Promise<void> {
                if (job.name !== QueueJob.PAGE_HISTORY) return;
              }
            }
        ''',
        'src/history/persistence.ts': '''
            export class Persistence {
              async store(page: any) {
                await this.historyQueue.add(
                  QueueJob.PAGE_HISTORY,
                  { pageId: page.id },
                  { jobId: page.id },
                );
              }
            }
        ''',
        'src/ui/reducer.ts': '''
            export function reducer(state: any, action: any) {
              switch (action.type) {
                case Actions.ADD:
                  return state;
              }
            }

            export function add() {
              return dispatch({ type: Actions.ADD });
            }
        ''',
    })
    proc = 'f:src/queue/general.processor.ts:GeneralProcessor.process'
    assert linked(nodes, edges, 'event', 'f:src/mail/mail.service.ts:MailService.sendMail', proc)
    assert linked(nodes, edges, 'event', 'f:src/mail/mail.service.ts:MailService.watch', proc)
    cleanup = 'f:src/services/session.service.ts:SessionService.handleCleanup'
    assert linked(nodes, edges, 'event', 'f:src/services/session.service.ts:SessionService.onBoot', cleanup)
    assert linked(nodes, edges, 'event', 'f:src/services/manual.ts:asJob', cleanup)
    assert not any(k == 'event' and 'reducer.ts' in a + b for a, b, k in edges)
    assert linked(nodes, edges, 'event', 'f:src/mail/mailer.ts:Mailer.deliver', 'f:src/mail/email.processor.ts:EmailProcessor.process')
    assert linked(nodes, edges, 'event', 'f:src/history/persistence.ts:Persistence.store', 'f:src/history/history.processor.ts:HistoryProcessor.process')


def test_job_classes_passed_by_reference(tmp_path):
    nodes, edges = run(tmp_path, {
        'pom.xml': '<project/>',
        'src/main/java/app/tasks/CleanupTask.java': '''
            package app.tasks;

            public class CleanupTask implements Runnable {
                @Override
                public void run() {
                }
            }
        ''',
        'src/main/java/app/flow/ImportWorkflow.java': '''
            package app.flow;

            public final class ImportWorkflow implements Workflow<ImportArg, Void> {
                @Override
                public Void execute(WorkflowContext ctx, ImportArg arg) {
                    ctx.activity(ImportActivity.class).call(arg);
                    return null;
                }
            }
        ''',
        'src/main/java/app/flow/ImportActivity.java': '''
            package app.flow;

            public final class ImportActivity implements Activity<ImportArg, Void> {
                @Override
                public Void execute(ActivityContext ctx, ImportArg arg) {
                    return null;
                }
            }
        ''',
        'src/main/java/app/Scheduler.java': '''
            package app;

            public class Scheduler {
                List<Task> tasks(Config config) {
                    return List.of(
                            recurringTask("Cleanup", cron(config), new CleanupTask()),
                            plain(new UserDto()));
                }

                void start(Engine engine) {
                    engine.createRun(new CreateWorkflowRunRequest<>(ImportWorkflow.class).withArgument(arg));
                }
            }
        ''',
        'src/main/java/app/UserDto.java': '''
            package app;

            public class UserDto {
                public void run() {}
            }
        ''',
        'src/Jobs/ReportJob.cs': '''
            public class ReportJob
            {
                public void Execute() {}
            }
        ''',
        'src/Startup.cs': '''
            public class Startup
            {
                public void Configure(IScheduler scheduler)
                {
                    scheduler.Schedule(typeof(ReportJob), "0 * * * *");
                }
            }
        ''',
    })
    sched = 'src/main/java/app/Scheduler.java'
    assert linked(nodes, edges, 'event', f'f:{sched}:Scheduler.tasks', 'f:src/main/java/app/tasks/CleanupTask.java:CleanupTask.run')
    assert linked(nodes, edges, 'event', f'f:{sched}:Scheduler.start', 'f:src/main/java/app/flow/ImportWorkflow.java:ImportWorkflow.execute')
    assert linked(nodes, edges, 'event', 'f:src/main/java/app/flow/ImportWorkflow.java:ImportWorkflow.execute',
                  'f:src/main/java/app/flow/ImportActivity.java:ImportActivity.execute')
    assert linked(nodes, edges, 'event', 'f:src/Startup.cs:Startup.Configure', 'f:src/Jobs/ReportJob.cs:ReportJob.Execute')
    assert not linked(nodes, edges, 'event', f'f:{sched}:Scheduler.tasks', 'f:src/main/java/app/UserDto.java:UserDto.run')


def test_dotted_task_references_in_schedules(tmp_path):
    nodes, edges = run(tmp_path, {
        'src/documents/tasks.py': '''
            from celery import shared_task


            @shared_task
            def train_classifier():
                return None
        ''',
        'src/project/settings.py': '''
            def beat_schedule():
                return {
                    "Train the classifier": {
                        "task": "documents.tasks.train_classifier",
                        "schedule": 3600,
                    },
                }
        ''',
    })
    assert linked(nodes, edges, 'event', 'f:src/project/settings.py:beat_schedule', 'f:src/documents/tasks.py:train_classifier')


# ------------------------------------------------------------------------------------------------------------------- rutas

def handled(nodes, edges, route, handler):
    return any((e, handler, 'handles') in edges for e, n in nodes.items() if n.get('kind') == 'endpoint' and n.get('name') == route)


def test_typed_receivers_chained_groups_and_verb_lists(tmp_path):
    nodes, edges = run(tmp_path, {
        'go.mod': 'module example.com/app\n',
        'api/user.go': '''
            package api

            type UserAPI struct{}

            func (a *UserAPI) GetUsers(ctx *gin.Context) {}
            func (a *UserAPI) CreateUser(ctx *gin.Context) {}
        ''',
        'api/health.go': '''
            package api

            type HealthAPI struct{}

            func (a *HealthAPI) Health(ctx *gin.Context) {}
        ''',
        'api/stream/stream.go': '''
            package stream

            type API struct{}

            func New() *API {
            	return &API{}
            }

            func (a *API) Handle(ctx *gin.Context) {}
        ''',
        'database/user.go': '''
            package database

            type GormDatabase struct{}

            func (d *GormDatabase) GetUsers() []string { return nil }
            func (d *GormDatabase) CreateUser(name string) error { return nil }
        ''',
        'plugin/mock.go': '''
            package plugin

            type Instance struct{}

            func (c *Instance) Health() string { return "" }
        ''',
        'router/router.go': '''
            package router

            func Create(g *gin.Engine) {
            	userHandler := api.UserAPI{}
            	healthHandler := &api.HealthAPI{}
            	streamHandler := stream.New()

            	g.Match([]string{"GET", "HEAD"}, "/health", healthHandler.Health)
            	g.Group("/user").Use(authentication.OptionalAdmin).POST("", userHandler.CreateUser)
            	admin := g.Group("/user")
            	{
            		admin.GET("", userHandler.GetUsers)
            	}
            	g.GET("/stream", streamHandler.Handle)
            }
        ''',
    })
    assert handled(nodes, edges, 'GET /health', 'f:api/health.go:HealthAPI.Health')
    assert handled(nodes, edges, 'HEAD /health', 'f:api/health.go:HealthAPI.Health')
    assert handled(nodes, edges, 'POST /user', 'f:api/user.go:UserAPI.CreateUser')
    assert handled(nodes, edges, 'GET /user', 'f:api/user.go:UserAPI.GetUsers')
    assert handled(nodes, edges, 'GET /stream', 'f:api/stream/stream.go:API.Handle')


# ------------------------------------------------------------------------------------------------------------------- http

def test_generated_sdk_functions_and_their_importers(tmp_path):
    nodes, edges = run(tmp_path, {
        'server/package.json': '{"name": "server"}',
        'server/src/keys.controller.ts': '''
            import { Controller, Delete, Get, Post } from '@nestjs/common';

            @Controller('api-keys')
            export class KeysController {
              @Get()
              getKeys() {}

              @Post()
              createKey() {}

              @Delete(':id')
              deleteKey() {}
            }
        ''',
        'server/src/main.ts': '''
            async function bootstrap() {
              const app = await NestFactory.create(AppModule);
              app.setGlobalPrefix('api');
            }
        ''',
        'packages/sdk/package.json': '{"name": "@org/sdk", "main": "./build/index.js"}',
        'packages/sdk/src/index.ts': '''
            export * from './fetch-client.js';
        ''',
        'packages/sdk/src/fetch-client.ts': '''
            /**
             * DO NOT MODIFY - This file has been generated using oazapfts.
             */
            export const defaults: Oazapfts.Defaults<Oazapfts.CustomHeaders> = {
                headers: {},
                baseUrl: "/api"
            };
            const oazapfts = Oazapfts.runtime(defaults);

            export function getKeys(opts?: Oazapfts.RequestOpts) {
                return oazapfts.ok(oazapfts.fetchJson<{
                    status: 200;
                    data: KeyDto[];
                }>("/api-keys", {
                    ...opts
                }));
            }

            export function createKey({ dto }: { dto: KeyDto }, opts?: Oazapfts.RequestOpts) {
                return oazapfts.ok(oazapfts.fetchJson<{
                    status: 201;
                    data: KeyDto;
                }>("/api-keys", oazapfts.json({
                    ...opts,
                    method: "POST",
                    body: dto
                })));
            }

            export function deleteKey({ id }: { id: string }, opts?: Oazapfts.RequestOpts) {
                return oazapfts.ok(oazapfts.fetchText(`/api-keys/${encodeURIComponent(id)}`, {
                    ...opts,
                    method: "DELETE"
                }));
            }
        ''',
        'web/src/lib/keys.ts': '''
            import { getKeys, deleteKey as removeKey } from '@org/sdk';

            export async function loadKeys() {
              return await getKeys();
            }

            export async function dropKey(id: string) {
              await removeKey({ id });
            }
        ''',
        'web/src/lib/legacy.js': '''
            import api from './api';

            export function fetchKeys() {
              return (dispatch) => {
                api().get('/api/api-keys').then((r) => dispatch(r.data));
              };
            }
        ''',
    })
    sdk = 'packages/sdk/src/fetch-client.ts'
    assert linked(nodes, edges, ('http', 'handles'), f'f:{sdk}:getKeys', 'f:server/src/keys.controller.ts:KeysController.getKeys')
    assert linked(nodes, edges, ('http', 'handles'), f'f:{sdk}:createKey', 'f:server/src/keys.controller.ts:KeysController.createKey')
    assert linked(nodes, edges, ('http', 'handles'), f'f:{sdk}:deleteKey', 'f:server/src/keys.controller.ts:KeysController.deleteKey')
    assert linked(nodes, edges, ('http', 'handles'), 'f:web/src/lib/keys.ts:loadKeys', 'f:server/src/keys.controller.ts:KeysController.getKeys')
    assert linked(nodes, edges, ('http', 'handles'), 'f:web/src/lib/keys.ts:dropKey', 'f:server/src/keys.controller.ts:KeysController.deleteKey')
    assert any(k == 'http' and a.startswith('f:web/src/lib/legacy.js') for a, b, k in edges)


def test_go_server_idioms_orm_observers_and_notifiers(tmp_path):
    nodes, edges = run(tmp_path, {
        'go.mod': 'module example.com/app\n',
        'model/user.go': '''
            package model

            type User struct {
            	ID   uint
            	Name string
            }
        ''',
        'model/message.go': '''
            package model

            type Message struct {
            	ID uint
            }
        ''',
        'database/database.go': '''
            package database

            import (
            	"example.com/app/model"
            	"gorm.io/gorm"
            )

            func New(db *gorm.DB) error {
            	if err := db.AutoMigrate(new(model.User), &model.Message{}); err != nil {
            		return err
            	}
            	return nil
            }
        ''',
        'plugin/manager.go': '''
            package plugin

            type Manager struct{}

            func NewManager(dir string, mux *gin.RouterGroup) (*Manager, error) {
            	return &Manager{}, nil
            }

            func (m *Manager) RemoveUser(id uint) error { return nil }
        ''',
        'api/stream/stream.go': '''
            package stream

            type API struct{}

            func (a *API) Notify(userID uint, msg string) {}
        ''',
        'api/message.go': '''
            package api

            type MessageAPI struct {
            	Notifier Notifier
            }

            func (a *MessageAPI) CreateMessage(ctx *gin.Context) {
            	a.Notifier.Notify(1, "x")
            }
        ''',
        'api/user.go': '''
            package api

            type UserAPI struct{}

            func (a *UserAPI) GetCurrentUser(ctx *gin.Context) {}
        ''',
        'router/router.go': '''
            package router

            func Create(g *gin.Engine) {
            	pluginManager, err := plugin.NewManager("x", g.Group("/plugin"))
            	if err != nil {
            		panic(err)
            	}
            	userChangeNotifier := new(api.UserChangeNotifier)
            	userChangeNotifier.OnUserDeleted(pluginManager.RemoveUser)
            	userHandler := api.UserAPI{}
            	clientAuth := g.Group("")
            	{
            		clientAuth.GET("current/user", userHandler.GetCurrentUser)
            	}
            }
        ''',
    })
    assert linked(nodes, edges, 'data', 'f:database/database.go:New', 'c:model/user.go:User')
    assert linked(nodes, edges, 'data', 'f:database/database.go:New', 'c:model/message.go:Message')
    assert linked(nodes, edges, 'event', 'f:router/router.go:Create', 'f:plugin/manager.go:Manager.RemoveUser')
    assert linked(nodes, edges, 'event', 'f:api/message.go:MessageAPI.CreateMessage', 'f:api/stream/stream.go:API.Notify')
    assert handled(nodes, edges, 'GET /current/user', 'f:api/user.go:UserAPI.GetCurrentUser')


def test_rust_notification_hub_calls(tmp_path):
    nodes, edges = run(tmp_path, {
        'Cargo.toml': '[package]\nname = "app"\n',
        'src/api/notifications.rs': '''
            use crate::api::push::push_folder_update;

            pub struct WebSocketUsers {}

            impl WebSocketUsers {
                pub async fn send_folder_update(&self, folder: &Folder) {
                    self.send_update(&folder.user_uuid).await;
                    push_folder_update(folder).await;
                }

                async fn send_update(&self, user: &str) {}
            }
        ''',
        'src/api/push.rs': '''
            pub async fn push_folder_update(folder: &Folder) {
            }
        ''',
        'src/api/core/folders.rs': '''
            use crate::api::Notify;

            #[post("/folders", data = "<data>")]
            async fn post_folders(data: Json<FolderData>, nt: Notify<'_>) -> JsonResult {
                nt.send_folder_update(&folder).await;
                Ok(())
            }
        ''',
        'src/util.rs': '''
            pub fn send_mail(to: &str) {}

            pub fn caller() {
                send_mail("x");
            }
        ''',
    })
    assert linked(nodes, edges, 'event', 'f:src/api/core/folders.rs:post_folders',
                  'f:src/api/notifications.rs:WebSocketUsers.send_folder_update')
    assert linked(nodes, edges, 'event', 'f:src/api/notifications.rs:WebSocketUsers.send_folder_update',
                  'f:src/api/push.rs:push_folder_update')
    assert not any(k == 'event' and 'util.rs' in a + b for a, b, k in edges)


def test_browser_clients_navigation_ternaries_and_created_instances(tmp_path):
    nodes, edges = run(tmp_path, {
        'go.mod': 'module example.com/app\n',
        'router/router.go': '''
            package router

            func Create(g *gin.Engine) {
            	g.POST("/user", api.CreateUser)
            	g.POST("/plugin/:id/enable", api.EnablePlugin)
            	g.POST("/plugin/:id/disable", api.DisablePlugin)
            	g.GET("/auth/oidc/login", api.Login)
            }
        ''',
        'api/api.go': '''
            package api

            func CreateUser(ctx *gin.Context) {}
            func EnablePlugin(ctx *gin.Context) {}
            func DisablePlugin(ctx *gin.Context) {}
            func Login(ctx *gin.Context) {}
        ''',
        'ui/src/stores.ts': '''
            import axios from 'axios';
            import * as config from './config';

            export class Stores {
              register = async (name: string) =>
                axios
                  .create()
                  .post(config.get('url') + 'user', {name});

              toggle = async (id: number, enabled: boolean) => {
                await axios.post(`${config.get('url')}plugin/${id}/${enabled ? 'enable' : 'disable'}`);
              };
            }

            export function login(name: string) {
              const url = config.get('url') + 'auth/oidc/login?name=' + encodeURIComponent(name);
              window.location.href = url;
            }
        ''',
    })
    http = ('http', 'handles')
    assert linked(nodes, edges, http, 'f:ui/src/stores.ts:Stores.register', 'f:api/api.go:CreateUser')
    assert linked(nodes, edges, http, 'f:ui/src/stores.ts:Stores.toggle', 'f:api/api.go:EnablePlugin')
    assert linked(nodes, edges, http, 'f:ui/src/stores.ts:Stores.toggle', 'f:api/api.go:DisablePlugin')
    assert linked(nodes, edges, http, 'f:ui/src/stores.ts:login', 'f:api/api.go:Login')


def test_django_nested_includes_and_viewset_routers(tmp_path):
    nodes, edges = run(tmp_path, {
        'src/mail/views.py': '''
            from rest_framework.decorators import action
            from rest_framework.viewsets import ModelViewSet, ViewSet


            class OwnerMixin:
                pass


            class MailAccountViewSet(OwnerMixin, ModelViewSet[object]):
                @action(methods=["post"], detail=False)
                def test(self, request):
                    return None

                @action(methods=["post"], detail=True, url_path="run-now")
                def process(self, request, pk=None):
                    return None


            class LogViewSet(ViewSet):
                def list(self, request):
                    return []

                def retrieve(self, request, pk=None):
                    return None
        ''',
        'src/core/views.py': '''
            class ProfileView:
                def get(self, request):
                    return None

                def patch(self, request):
                    return None
        ''',
        'src/core/urls.py': '''
            from django.urls import include, path, re_path
            from rest_framework.routers import DefaultRouter

            from core.views import ProfileView
            from mail.views import LogViewSet, MailAccountViewSet

            api_router = DefaultRouter()
            api_router.register(r"mail_accounts", MailAccountViewSet)
            api_router.register(r"logs", LogViewSet, basename="logs")

            urlpatterns = [
                re_path(
                    r"^api/",
                    include(
                        [
                            re_path(
                                "^profile/",
                                include(
                                    [
                                        re_path("^$", ProfileView.as_view(), name="profile"),
                                    ],
                                ),
                            ),
                            re_path("^", include(api_router.urls)),
                        ],
                    ),
                ),
            ]
        ''',
    })
    cls = 'c:src/mail/views.py:MailAccountViewSet'
    assert handled(nodes, edges, 'GET /api/mail_accounts', cls)
    assert handled(nodes, edges, 'PATCH /api/mail_accounts/:pk', cls)
    assert handled(nodes, edges, 'DELETE /api/mail_accounts/:pk', cls)
    assert handled(nodes, edges, 'POST /api/mail_accounts/test', 'f:src/mail/views.py:MailAccountViewSet.test')
    assert handled(nodes, edges, 'POST /api/mail_accounts/:pk/run-now', 'f:src/mail/views.py:MailAccountViewSet.process')
    assert handled(nodes, edges, 'GET /api/logs/:pk', 'f:src/mail/views.py:LogViewSet.retrieve')
    assert handled(nodes, edges, 'GET /api/logs', 'f:src/mail/views.py:LogViewSet.list')
    assert not any(n.get('name') == 'DELETE /api/logs/:pk' for n in nodes.values())
    assert handled(nodes, edges, 'GET /api/profile', 'f:src/core/views.py:ProfileView.get')
    assert handled(nodes, edges, 'PATCH /api/profile', 'f:src/core/views.py:ProfileView.patch')


def test_rails_resource_modules_and_ruby_job_variants(tmp_path):
    nodes, edges = run(tmp_path, {
        'config/routes.rb': '''
            Rails.application.routes.draw do
              namespace :api do
                namespace :v1 do
                  resources :lists, only: [:index] do
                    resource :accounts, only: [:show, :create], module: :lists
                  end
                  resources :polls, only: [:show] do
                    resources :votes, only: :create, module: :polls
                  end
                end
              end
            end
        ''',
        'app/controllers/api/v1/lists_controller.rb': '''
            class Api::V1::ListsController < Api::BaseController
              def index
              end
            end
        ''',
        'app/controllers/api/v1/lists/accounts_controller.rb': '''
            class Api::V1::Lists::AccountsController < Api::BaseController
              def show
              end

              def create
              end
            end
        ''',
        'app/controllers/api/v1/accounts_controller.rb': '''
            class Api::V1::AccountsController < Api::BaseController
              def show
              end
            end
        ''',
        'app/controllers/api/v1/polls/votes_controller.rb': '''
            class Api::V1::Polls::VotesController < Api::BaseController
              def create
              end
            end
        ''',
        'app/workers/feed_insert_worker.rb': '''
            class FeedInsertWorker
              include Sidekiq::Worker

              def perform(status_id, follower_id)
              end
            end
        ''',
        'app/workers/purge_emoji_worker.rb': '''
            class PurgeEmojiWorker
              include Sidekiq::IterableJob

              def build_enumerator(domain, cursor:)
              end

              def each_iteration(emojis, _domain)
              end
            end
        ''',
        'app/services/fan_out_service.rb': '''
            class FanOutService
              def call(status, followers)
                FeedInsertWorker.push_bulk(followers) do |follower|
                  [status.id, follower.id]
                end
                PurgeEmojiWorker.perform_async(status.domain)
              end
            end
        ''',
    })
    show = [h for h in nodes if h.startswith('f:app/controllers/api/v1/lists/accounts_controller.rb') and h.endswith('show')]
    vote = [h for h in nodes if h.startswith('f:app/controllers/api/v1/polls/votes_controller.rb') and h.endswith('create')]
    assert show and handled(nodes, edges, 'GET /api/v1/lists/:list_id/accounts', show[0])
    assert vote and handled(nodes, edges, 'POST /api/v1/polls/:poll_id/votes', vote[0])
    call = [n for n in nodes if n.startswith('f:app/services/fan_out_service.rb') and n.endswith('call')][0]
    perform = [n for n in nodes if n.startswith('f:app/workers/feed_insert_worker.rb') and n.endswith('perform')][0]
    iteration = [n for n in nodes if n.startswith('f:app/workers/purge_emoji_worker.rb') and n.endswith('each_iteration')][0]
    assert linked(nodes, edges, 'event', call, perform)
    assert linked(nodes, edges, 'event', call, iteration)


def test_request_helpers_with_long_signatures(tmp_path):
    nodes, edges = run(tmp_path, {
        'config/routes.rb': '''
            Rails.application.routes.draw do
              namespace :api do
                namespace :v1 do
                  resources :lists, only: [:index, :create]
                  resources :custom_emojis, only: [:index]
                end
              end
            end
        ''',
        'app/controllers/api/v1/lists_controller.rb': '''
            class Api::V1::ListsController < Api::BaseController
              def index
              end

              def create
              end
            end
        ''',
        'app/controllers/api/v1/custom_emojis_controller.rb': '''
            class Api::V1::CustomEmojisController < Api::BaseController
              def index
              end
            end
        ''',
        'app/javascript/app/api.ts': '''
            import axios from 'axios';

            export default function api() {
              return axios.create({});
            }

            export async function apiRequest<
              ApiResponse = unknown,
              ApiParamsOrData = unknown,
            >(
              method: Method,
              url: string,
              args: {
                signal?: AbortSignal;
                params?: Record<string, unknown>;
                data?: Record<string, unknown>;
                timeout?: number;
              } = {},
            ) {
              const { data } = await api().request<ApiResponse>({
                method,
                url: '/api/' + url,
                ...args,
              });
              return data;
            }

            export async function apiRequestGet<ApiResponse = unknown>(url: string) {
              return apiRequest<ApiResponse>('GET', url);
            }

            export async function apiRequestPost<ApiResponse = unknown>(url: string, data?: unknown) {
              return apiRequest<ApiResponse>('POST', url, { data });
            }
        ''',
        'app/javascript/app/lists.ts': '''
            import { apiRequestGet, apiRequestPost } from './api';

            export const apiGetLists = () => apiRequestGet('v1/lists');

            export const apiCreate = (list: unknown) => apiRequestPost('v1/lists', list);
        ''',
        'app/javascript/app/emoji.ts': '''
            export async function importEmojis() {
              const response = await fetchAndCheckEtag({
                oldEtag: 'x',
                path: '/api/v1/custom_emojis',
              });
              return response;
            }
        ''',
    })
    http = ('http', 'handles')
    idx = [h for h in nodes if h.startswith('f:app/controllers/api/v1/lists_controller.rb') and h.endswith('index')][0]
    create = [h for h in nodes if h.startswith('f:app/controllers/api/v1/lists_controller.rb') and h.endswith('create')][0]
    emoji = [h for h in nodes if h.startswith('f:app/controllers/api/v1/custom_emojis_controller.rb') and h.endswith('index')][0]
    assert linked(nodes, edges, http, 'f:app/javascript/app/lists.ts:apiGetLists', idx)
    assert linked(nodes, edges, http, 'f:app/javascript/app/lists.ts:apiCreate', create)
    assert linked(nodes, edges, http, 'f:app/javascript/app/emoji.ts:importEmojis', emoji)


# ------------------------------------------------------------------------------------------------------------------- rpc

def test_cross_language_platform_interfaces(tmp_path):
    nodes, edges = run(tmp_path, {
        'mobile/pigeon/native_api.dart': '''
            @HostApi()
            abstract class NativeSyncApi {
              void cancelSync();
              List<String> getAlbums();
            }
        ''',
        'mobile/pigeon/network_api.dart': '''
            @HostApi()
            abstract class NetworkApi {
              bool hasCertificate();
            }
        ''',
        'mobile/lib/services/sync.service.dart': '''
            import 'package:app/platform/native_api.g.dart';

            class SyncService {
              final NativeSyncApi _nativeSyncApi;

              SyncService(this._nativeSyncApi);

              Future<void> cancel() async {
                await _nativeSyncApi.cancelSync();
              }

              Future<List<String>> albums() => _nativeSyncApi.getAlbums();
            }
        ''',
        'mobile/lib/providers/platform.dart': '''
            final networkApi = NetworkApi();
        ''',
        'mobile/lib/widgets/cert.dart': '''
            import 'package:app/providers/platform.dart';

            class CertSettings {
              Future<bool> check() async {
                return await networkApi.hasCertificate();
              }
            }
        ''',
        'mobile/android/app/src/main/kotlin/app/sync/SyncBase.kt': '''
            package app.sync

            open class NativeSyncApiImplBase(context: Context) {
                fun cancelSync() {}
            }
        ''',
        'mobile/android/app/src/main/kotlin/app/sync/SyncImpl.kt': '''
            package app.sync

            class NativeSyncApiImpl30(context: Context) : NativeSyncApiImplBase(context), NativeSyncApi {
                override fun getAlbums(): List<String> = listOf()
            }
        ''',
        'mobile/android/app/src/main/kotlin/app/net/NetworkPlugin.kt': '''
            package app.net

            private class NetworkApiImpl(private val context: Context) : NetworkApi {
                override fun hasCertificate(): Boolean = false
            }
        ''',
    })
    rpc = lambda rel, target: any(k == 'rpc' and a.split(':')[1] == rel and b == target for a, b, k in edges)
    kt = 'f:mobile/android/app/src/main/kotlin/app'
    assert rpc('mobile/lib/services/sync.service.dart', f'{kt}/sync/SyncBase.kt:NativeSyncApiImplBase.cancelSync')
    assert rpc('mobile/lib/services/sync.service.dart', f'{kt}/sync/SyncImpl.kt:NativeSyncApiImpl30.getAlbums')
    assert rpc('mobile/lib/widgets/cert.dart', f'{kt}/net/NetworkPlugin.kt:NetworkApiImpl.hasCertificate')


def test_inherited_url_builders(tmp_path):
    nodes, edges = run(tmp_path, {
        'src/docs/views.py': '''
            class BulkEditView:
                def post(self, request):
                    return None


            class TestAccountView:
                def post(self, request):
                    return None
        ''',
        'src/docs/urls.py': '''
            from django.urls import path, re_path, include
            from docs.views import BulkEditView, TestAccountView

            urlpatterns = [
                re_path(r"^api/", include([
                    path("documents/bulk_edit/", BulkEditView.as_view()),
                    path("mail_accounts/test/", TestAccountView.as_view()),
                ])),
            ]
        ''',
        'ui/src/app/services/rest/abstract-service.ts': '''
            export abstract class AbstractService<T> {
              protected baseUrl: string = environment.apiBaseUrl
              protected http: HttpClient
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
            }
        ''',
        'ui/src/app/services/rest/document.service.ts': '''
            import { AbstractService } from './abstract-service'

            export class DocumentService extends AbstractService<Document> {
              constructor() {
                super()
                this.resourceName = 'documents'
              }

              bulkEdit(selection: any) {
                return this.http.post(this.getResourceUrl(null, 'bulk_edit'), { ...selection })
              }
            }
        ''',
        'ui/src/app/services/rest/mail-account.service.ts': '''
            import { AbstractService } from './abstract-service'

            export class MailAccountService extends AbstractService<MailAccount> {
              constructor() {
                super()
                this.resourceName = 'mail_accounts'
              }

              test(o: any) {
                return this.http.post(this.getResourceUrl() + 'test/', o)
              }
            }
        ''',
    })
    http = ('http', 'handles')
    assert linked(nodes, edges, http, 'f:ui/src/app/services/rest/document.service.ts:DocumentService.bulkEdit', 'f:src/docs/views.py:BulkEditView.post')
    assert linked(nodes, edges, http, 'f:ui/src/app/services/rest/mail-account.service.ts:MailAccountService.test', 'f:src/docs/views.py:TestAccountView.post')


def test_typed_schema_map_models(tmp_path):
    nodes, edges = run(tmp_path, {
        'package.json': '{"name": "srv"}',
        'src/migrations/001-init.ts': '''
            export async function up(db: Kysely<any>): Promise<void> {
              await db.schema.createTable('comments').addColumn('id', 'uuid').execute();
              await db.schema.createTable('page_labels').addColumn('id', 'uuid').execute();
              await db.schema
                .createTable('users')
                .addColumn('id', 'uuid')
                .execute();
            }
        ''',
        'src/database/types/db.ts': '''
            export interface Comments {
              content: string | null;
              id: string;
            }

            export interface PageLabels {
              id: string;
            }

            export interface Users {
              id: string;
            }

            export interface DB {
              comments: Comments;
              pageLabels: PageLabels;
              users: Users;
            }
        ''',
    })
    mig = 'src/migrations/001-init.ts'
    assert linked(nodes, edges, 'data', 'c:src/database/types/db.ts:Comments', table_node(nodes, mig, 'comments'))
    assert linked(nodes, edges, 'data', 'c:src/database/types/db.ts:PageLabels', table_node(nodes, mig, 'page_labels'))


def test_openapi_split_specs_and_generated_clients(tmp_path):
    nodes, edges = run(tmp_path, {
        'pom.xml': '<project/>',
        'api/src/main/openapi/openapi.yaml': '''
            openapi: 3.0.3
            info:
              title: x
            servers:
            - url: /api/v2
            paths:
              /secrets:
                $ref: "./resources/secrets/secrets.yaml"
              /secrets/{name}:
                $ref: "./resources/secrets/secret.yaml"
        ''',
        'api/src/main/openapi/resources/secrets/secrets.yaml': '''
            # License header
            get:
              operationId: listSecrets
              tags:
                - Secrets
            post:
              operationId: createSecret
              tags:
                - Secrets
        ''',
        'api/src/main/openapi/resources/secrets/secret.yaml': '''
            delete:
              operationId: deleteSecret
              tags:
                - Secrets
        ''',
        'server/src/main/java/app/v2/SecretsResource.java': '''
            package app.v2;

            public class SecretsResource implements SecretsApi {
                public Response listSecrets() { return null; }
                public Response createSecret(CreateSecretRequest r) { return null; }
                public Response deleteSecret(String name) { return null; }
            }
        ''',
        'secrets/src/main/java/app/secrets/DatabaseSecretManager.java': '''
            package app.secrets;

            public class DatabaseSecretManager implements SecretManager {
                public void listSecrets() {}
                public void createSecret(String name) {}
                public void deleteSecret(String name) {}
            }
        ''',
        'open-api/app-openapi-specs.json': '{"openapi": "3.0.0", "servers": [{"url": "/api"}], "paths": {"/partners": {"post": {"operationId": "createPartner", "tags": ["Partners"]}}}}',
        'server/src/partner.controller.ts': '''
            import { Controller, Post } from '@nestjs/common';

            @Controller('partners')
            export class PartnerController {
              @Post()
              createPartner() {}
            }
        ''',
        'server/src/main.ts': '''
            async function bootstrap() {
              const app = await NestFactory.create(AppModule);
              app.setGlobalPrefix('api');
            }
        ''',
        'mobile/lib/repositories/partner_api.repository.dart': '''
            import 'package:openapi/api.dart';

            class PartnerApiRepository {
              final PartnersApi _api;

              PartnerApiRepository(this._api);

              Future<void> create(String id) => _api.createPartner(PartnerCreateDto(id: id));
            }
        ''',
    })
    res = 'f:server/src/main/java/app/v2/SecretsResource.java:SecretsResource'
    assert handled(nodes, edges, 'GET /api/v2/secrets', f'{res}.listSecrets')
    assert handled(nodes, edges, 'POST /api/v2/secrets', f'{res}.createSecret')
    assert handled(nodes, edges, 'DELETE /api/v2/secrets/:name', f'{res}.deleteSecret')
    assert any(k == 'http' and a.startswith('f:mobile/lib/repositories/partner_api.repository.dart')
               and nodes[b].get('name') == 'POST /api/partners' for a, b, k in edges)


def test_code_migrations_with_sql_and_rename_maps(tmp_path):
    nodes, edges = run(tmp_path, {
        'package.json': '{"name": "srv"}',
        'src/schema/migrations/1700-Initial.ts': '''
            export async function up(db: Kysely<any>): Promise<void> {
              await sql`CREATE TABLE "partners" ("sharedById" uuid NOT NULL);`.execute(db);
              // CREATE TABLE "ignored" is only a comment
            }
        ''',
        'src/schema/migrations/1800-StandardizeNames.ts': '''
            const renames = [
              { oldName: 'partners', newName: 'partner' },
            ];
        ''',
        'src/schema/tables/partner.table.ts': '''
            @Table('partner')
            export class PartnerTable {
              sharedById!: string;
            }
        ''',
        'migrations/versions/0001_init.py': '''
            from alembic import op


            def upgrade():
                op.execute("CREATE TABLE audit_log (id serial primary key)")
        ''',
    })
    partners = table_node(nodes, 'src/schema/migrations/1700-Initial.ts', 'partners')
    assert linked(nodes, edges, 'data', 'c:src/schema/tables/partner.table.ts:PartnerTable', partners)
    assert not any(n.get('table') == 'ignored' for n in nodes.values())
    assert any(n.get('table') == 'audit_log' for n in nodes.values())


def test_default_hosts_resolve_to_main_compose(tmp_path):
    nodes, edges = run(tmp_path, {
        'docker/docker-compose.yml': '''
            services:
              server:
                image: app
              redis:
                image: valkey
        ''',
        'docker/docker-compose.dev.yml': '''
            services:
              server:
                image: app
              redis:
                image: valkey
        ''',
        'server/src/config.ts': '''
            export function redisConfig(dto: any) {
              return {
                host: dto.REDIS_HOSTNAME || 'redis',
                port: dto.REDIS_PORT || 6379,
              };
            }
        ''',
    })
    assert ('f:server/src/config.ts:redisConfig', 'c:docker/docker-compose.yml:redis', 'depends') in edges


def test_precision_guards(tmp_path):
    nodes, edges = run(tmp_path, {
        'go.mod': 'module example.com/app\n',
        'api/stream/stream.go': '''
            package stream

            type API struct{}

            func (a *API) Notify(userID uint, msg string) {}
        ''',
        'runner/runner.go': '''
            package runner

            import (
            	"os"
            	"os/signal"
            )

            func doShutdownOnSignal() {
            	ch := make(chan os.Signal, 1)
            	signal.Notify(ch, os.Interrupt)
            }
        ''',
        'web/compile.js': '''
            import { Worker } from 'node:worker_threads';

            export function compileAll() {
              return new Worker('./compile-worker.js');
            }
        ''',
        'lib/sso/worker.ex': '''
            defmodule App.SSO.Verification.Worker do
              use Oban.Worker

              def perform(job), do: :ok
            end
        ''',
        'src/models/notification.ts': '''
            export class Notification {
              get path() {
                switch (this.event) {
                  case NotificationEventType.ReactionsCreate:
                    return '/reactions';
                }
              }
            }
        ''',
        'src/tasks/reactions.ts': '''
            export class ReactionTask {
              async perform() {
                await Notification.create({ event: NotificationEventType.ReactionsCreate });
              }
            }
        ''',
        'src/queue/queue.module.ts': '''
            export const QueueModule = BullModule.registerQueue({ name: QueueName.HISTORY_QUEUE });
        ''',
        'src/history/history.processor.ts': '''
            @Processor(QueueName.HISTORY_QUEUE)
            export class HistoryProcessor {
              async process(job: any) {}
            }
        ''',
        'tools/probe.py': '''
            import os


            def _tool(name):
                return os.environ.get(name, name)


            def ffprobe():
                return _tool("ffprobe")
        ''',
        'config/data.yml': '''
            environments:
              families:
                - OVS
                - LIN
        ''',
        'api/message.go': '''
            package api

            type Notifier interface {
            	Notify(userID uint, msg string)
            }
        ''',
        'router/router.go': '''
            package router

            func Create(g *gin.Engine) {
            	authentication := auth.Auth{}
            	pluginRoute := g.Group("/plugin/", authentication.RequireClient)
            	pluginRoute.GET("/:id/config", api.GetConfig)
            }
        ''',
        'auth/auth.go': '''
            package auth

            type Auth struct{}

            func (a *Auth) RequireClient(ctx *gin.Context) {}
        ''',
        'docs/tasks.py': '''
            from celery import shared_task


            @shared_task
            def reindex():
                return None
        ''',
        'docs/handlers.py': '''
            TASK_TYPES = {
                "docs.tasks.reindex": "REINDEX",
            }
        ''',
        'web/settings.py': '''
            def update_auth(manager, body):
                manager.update(
                    auth_user=body.auth_user,
                )
        ''',
        '.env.example': 'AUTH_USER=admin\n',
    })
    assert not any(k == 'event' and 'runner.go' in a + b for a, b, k in edges)
    assert not any(k == 'event' and 'compile.js' in a + b for a, b, k in edges)
    assert not any(k == 'event' and 'notification.ts' in a + b for a, b, k in edges)
    assert not any(k == 'event' and 'queue.module.ts' in a + b for a, b, k in edges)
    assert 'v:ffprobe' not in nodes and 'v:OVS' not in nodes
    assert not any(k == 'event' and 'message.go' in a for a, b, k in edges)
    assert not any(k == 'handles' and b.startswith('f:auth/auth.go') for a, b, k in edges)
    assert not any(k == 'event' and 'handlers.py' in a for a, b, k in edges)
    assert not any(k == 'env' and 'web/settings.py' in a for a, b, k in edges)
