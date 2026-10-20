"""Construcciones de cada lenguaje que el grafo resuelve (matriz en bench/LANGFEATURES.md).

Cada caso es un repo mínimo: las aristas de `present` deben estar y las de `absent` no. Las claves siguen la forma de
los nodos: `m:archivo`, `c:archivo:Clase`, `f:archivo:funcion`, `f:archivo:Clase.metodo`.
"""
import pytest

from conftest import edge_set, write_repo
from cortex_graph.analyze import analyze

CASES = [
    # --- Python ---
    ('python', 'llamada a nivel de módulo', {
        'app/core.py': """
            def helper():
                return 1

            helper()
        """,
    }, {('m:app/core.py', 'f:app/core.py:helper', 'call')}, ()),
    ('python', 'cadena con tipo de retorno', {
        'app/core.py': """
            class Engine:
                @staticmethod
                def make() -> 'Engine':
                    return Engine()

                def run(self):
                    return 1


            def chain():
                return Engine.make().run()
        """,
    }, {('f:app/core.py:chain', 'f:app/core.py:Engine.make', 'call'), ('f:app/core.py:chain', 'f:app/core.py:Engine.run', 'call')}, ()),
    ('python', 'with … as (tipo de __enter__)', {
        'app/core.py': """
            class Client:
                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

                def request(self):
                    return 1


            def fetch():
                with Client() as client:
                    return client.request()
        """,
    }, {('f:app/core.py:fetch', 'f:app/core.py:Client.request', 'call')}, ()),
    ('python', 'contenedor copiado (list(reversed(x)))', {
        'app/core.py': """
            import typing


            class Decoder:
                def decode(self, data):
                    return data


            class Multi:
                def __init__(self, children: typing.Sequence[Decoder]):
                    self.children = list(reversed(children))

                def decode(self, data):
                    for child in self.children:
                        data = child.decode(data)
                    return data
        """,
    }, {('f:app/core.py:Multi.decode', 'f:app/core.py:Decoder.decode', 'call')}, ()),
    ('python', 'unión con un solo tipo del proyecto', {
        'app/core.py': """
            class URL:
                def join(self, other):
                    return self


            class Request:
                def __init__(self, url: 'URL | str'):
                    self.url: URL | str = url


            def redirect(request: Request):
                return request.url.join('x')
        """,
    }, {('f:app/core.py:redirect', 'f:app/core.py:URL.join', 'call')}, ()),
    ('python', 'decorador e import * con __all__', {
        'pkg/__init__.py': """
            from .core import *
        """,
        'pkg/core.py': """
            __all__ = ['helper', 'deco']


            def helper():
                return 1


            def deco(fn):
                return fn
        """,
        'pkg/use.py': """
            from pkg import helper, deco


            @deco
            def decorated():
                return helper()
        """,
    }, {('f:pkg/use.py:decorated', 'f:pkg/core.py:helper', 'call'), ('m:pkg/__init__.py', 'm:pkg/core.py', 'import')}, ()),
    ('python', 'funciones y clases anidadas, definiciones condicionales y tipos estrechados', {
        'app/core.py': """
            import sys
            from typing import Iterator, Union


            class Text:
                def copy(self):
                    return self

                def stylize(self):
                    return 1


            class Lines:
                def __iter__(self) -> Iterator[Text]:
                    return iter([])


            TextType = Union[str, "Text"]

            if sys.platform == "win32":
                def features():
                    return 1
            else:
                def features():
                    return 2


            class Model:
                class Meta:
                    ordering = 1


            def decorate(f):
                def wrapper(value: TextType, lines: Lines):
                    _Text = Text
                    _Text.stylize(value)
                    for line in lines:
                        line.copy()
                    if isinstance(value, str):
                        return value.upper()
                    other = value if value else None
                    return other.copy()
                return wrapper
        """,
    }, {('f:app/core.py:decorate', 'f:app/core.py:decorate.wrapper', 'contains'),
        ('f:app/core.py:decorate.wrapper', 'f:app/core.py:Text.stylize', 'call'),
        ('f:app/core.py:decorate.wrapper', 'f:app/core.py:Text.copy', 'call'),
        ('m:app/core.py', 'f:app/core.py:features', 'contains'),
        ('c:app/core.py:Model', 'c:app/core.py:Model.Meta', 'contains')},
     {('f:app/core.py:decorate', 'f:app/core.py:Text.copy', 'call')}),
    ('python', 'lambda y comprensión dentro de una función', {
        'app/core.py': """
            def helper():
                return 1


            def run():
                f = lambda: helper()
                return [helper() for _ in range(2)] + [f()]
        """,
    }, {('f:app/core.py:run', 'f:app/core.py:helper', 'call')}, ()),

    # --- Go ---
    ('go', 'constante y función como valor de otro archivo del paquete', {
        'go.mod': 'module example.com/app\n',
        'cmd/consts.go': """
            package cmd

            const Marker = "x"

            func emptyRun() {}
        """,
        'cmd/use.go': """
            package cmd

            type Command struct{ Run func() }

            func build() string {
              c := &Command{Run: emptyRun}
              _ = c
              return Marker
            }
        """,
    }, {('f:cmd/use.go:build', 'f:cmd/consts.go:emptyRun', 'ref'), ('f:cmd/use.go:build', 'm:cmd/consts.go', 'ref')}, ()),
    ('go', 'parámetro de un literal de función no es un valor del paquete', {
        'go.mod': 'module example.com/app\n',
        'p/tree.go': """
            package p

            const param = 1
        """,
        'p/log.go': """
            package p

            var format = func(param string) string { return param }
        """,
    }, set(), {('m:p/log.go', 'm:p/tree.go', 'ref')}),
    ('go', 'métodos y receptores tipados', {
        'go.mod': 'module example.com/app\n',
        'm/user.go': """
            package m

            type User struct{}

            func (u *User) Save() error { return nil }

            func New() *User { return &User{} }

            func Use() error { return New().Save() }
        """,
    }, {('f:m/user.go:Use', 'f:m/user.go:User.Save', 'call')}, ()),

    # --- TypeScript ---
    ('typescript', 'namespace con miembros', {
        'src/util.ts': """
            export namespace util {
              export function assertNever(x: never): never { throw new Error(); }
              export const objectKeys = typeof Object.keys === 'function'
                ? (obj: any) => Object.keys(obj)
                : (obj: any) => [];
              export const objectValues = (obj: any) => objectKeys(obj).map((k) => obj[k]);
            }
            export namespace other {
              export function assertNever(x: never): void {}
            }
        """,
        'src/use.ts': """
            import { util } from './util';

            export function run(x: any) {
              util.assertNever(x);
              return util.objectValues(x);
            }
        """,
    }, {('f:src/use.ts:run', 'f:src/util.ts:util.assertNever', 'call'), ('f:src/use.ts:run', 'f:src/util.ts:util.objectValues', 'call'),
        ('f:src/util.ts:util.objectValues', 'f:src/util.ts:util.objectKeys', 'call')}, ()),
    ('typescript', 'alias de función y cadena a nivel de módulo', {
        'src/types.ts': """
            export class ZodType {
              optional(): ZodType { return this; }
              parse(x: unknown) { return x; }
            }
            export class ZodString extends ZodType {
              static create = (): ZodString => new ZodString();
            }
            const stringType = ZodString.create;
            export { stringType as string };
        """,
        'src/index.ts': """
            export * from './types';
        """,
        'src/use.ts': """
            import * as z from './index';

            const schema = z.string().optional();
            schema.parse('a');
        """,
    }, {('m:src/use.ts', 'f:src/types.ts:stringType', 'call'), ('m:src/use.ts', 'f:src/types.ts:ZodType.optional', 'call'),
        ('m:src/use.ts', 'f:src/types.ts:ZodType.parse', 'call'), ('f:src/types.ts:stringType', 'f:src/types.ts:ZodString.create', 'ref')},
        {('m:src/use.ts', 'm:src/index.ts', 'call')}),
    ('typescript', 'campo alias de un método (`min = this.gte`)', {
        'src/num.ts': """
            export class ZodNumber {
              gte(n: number): ZodNumber { return this; }
              min = this.gte;
            }
            export function use(z: ZodNumber) {
              return z.min(1);
            }
        """,
    }, {('f:src/num.ts:use', 'f:src/num.ts:ZodNumber.min', 'call'), ('f:src/num.ts:ZodNumber.min', 'f:src/num.ts:ZodNumber.gte', 'ref')}, ()),

    # --- JavaScript (CommonJS) ---
    ('typescript', 'objeto literal tipado por contexto, lectura de propiedad, genérico T y elemento de colección', {
        'src/args.ts': """
            export interface ValidationArguments {
              constraints: any[];
            }
        """,
        'src/meta.ts': """
            import { ValidationArguments } from './args';

            export interface Constraint {
              validate(value: any, args?: ValidationArguments): boolean;
            }

            export interface Options {
              name: string;
              validator: Constraint | Function;
            }

            export class Metadata {
              validateIf?: (value: any) => boolean;
              each: boolean = false;
            }

            export class Validator {
              validate(x: any): boolean { return true; }
            }

            export function validateBy(options: Options): void {}

            export function getFromContainer<T>(someClass: { new (...args: any[]): T }): T {
              return new someClass();
            }
        """,
        'src/use.ts': """
            import { validateBy, getFromContainer, Validator, Metadata } from './meta';

            export function contains(values: any[]) {
              return validateBy({
                name: 'x',
                validator: {
                  validate: (value, args): boolean => args?.constraints[0] === value,
                },
              });
            }

            export function check(items: Metadata[]) {
              items.forEach(m => m.validateIf(1));
              return getFromContainer(Validator).validate(1);
            }
        """,
    }, {('f:src/use.ts:contains', 'c:src/args.ts:ValidationArguments', 'ref'),
        ('f:src/use.ts:check', 'f:src/meta.ts:Metadata.validateIf', 'call'),
        ('f:src/use.ts:check', 'f:src/meta.ts:Validator.validate', 'call')}, ()),
    ('javascript', 'mixin con Object.assign(Clase.prototype, { … }) y this en sus métodos', {
        'lib/emitter.js': """
            function Emitter() {}
            Object.assign(Emitter.prototype, {
              emit(name) { return this.listeners(name); },
              listeners: function (name) { return []; },
            });
            function use() {
              var e = new Emitter();
              return e.emit('x');
            }
            module.exports = Emitter;
        """,
    }, {('f:lib/emitter.js:Emitter.emit', 'f:lib/emitter.js:Emitter.listeners', 'call'),
        ('f:lib/emitter.js:use', 'f:lib/emitter.js:Emitter.emit', 'call')}, ()),
    ('javascript', 'llamada a un valor importado que no es una función', {
        'test/qunit.js': """
            export var test = QUnit.test;
        """,
        'test/a.js': """
            import { test } from './qunit';

            export function suite() {
              test('x', function () {});
            }
        """,
    }, {('f:test/a.js:suite', 'm:test/qunit.js', 'ref')}, {('f:test/a.js:suite', 'm:test/qunit.js', 'call')}),
    ('javascript', 'exports.f, Clase.prototype.m y obj.m = function', {
        'lib/utils.js': """
            exports.compileETag = function (val) { return val; };
        """,
        'lib/view.js': """
            function View(name) { this.name = name; }
            View.prototype.lookup = function lookup(p) { return p; };
            View.prototype.render = function render() { return this.lookup('x'); };
            module.exports = View;
        """,
        'lib/app.js': """
            var compileETag = require('./utils').compileETag;
            var View = require('./view');
            var app = exports = module.exports = {};
            app.set = function set(v) { return compileETag(v); };
            app.render = function render() {
              var view = new View('x');
              return view.render();
            };
        """,
    }, {('f:lib/app.js:app.set', 'f:lib/utils.js:compileETag', 'call'), ('f:lib/app.js:compileETag', 'f:lib/utils.js:compileETag', 'ref'),
        ('f:lib/view.js:View.render', 'f:lib/view.js:View.lookup', 'call'), ('f:lib/app.js:app.render', 'f:lib/view.js:View.render', 'call'),
        ('m:lib/app.js', 'm:lib/utils.js', 'import')}, ()),

    # --- Ruby ---
    ('ruby', 'mixin (include), alias_method y attr_accessor', {
        'lib/helpers.rb': """
            module Helpers
              def status(code)
                code
              end
            end
        """,
        'lib/base.rb': """
            require_relative 'helpers'

            class Base
              include Helpers
              attr_accessor :env

              def call_with_check(env)
                env
              end
              alias_method :call, :call_with_check

              def handle(boom)
                status(500)
                env['x'] = 1
                call(boom)
              end
            end
        """,
    }, {('f:lib/base.rb:Base.handle', 'f:lib/helpers.rb:Helpers.status', 'call'), ('f:lib/base.rb:Base.handle', 'f:lib/base.rb:Base.env', 'call'),
        ('f:lib/base.rb:Base.handle', 'f:lib/base.rb:Base.call_with_check', 'call'), ('c:lib/base.rb:Base', 'c:lib/helpers.rb:Helpers', 'inherits')}, ()),
    ('ruby', 'def self.x junto a def x, operadores y escrituras', {
        'lib/app.rb': """
            class App
              def self.settings
                self
              end

              def settings
                self.class.settings
              end

              def body=(value)
                @body = value
              end

              def <=>(other)
                0
              end

              def run(force = settings)
                force
              end
            end
        """,
    }, {('f:lib/app.rb:App.settings', 'f:lib/app.rb:App.self.settings', 'call'), ('f:lib/app.rb:App.run', 'f:lib/app.rb:App.settings', 'call')}, ()),
    ('ruby', 'autoload y ::Constante raíz', {
        'lib/rack.rb': """
            module Rack
              autoload :Builder, 'rack/builder'
            end
        """,
        'lib/rack/builder.rb': """
            module Rack
              class Builder
              end
            end
        """,
        'lib/rack/logger.rb': """
            module Rack
              class Logger
                def call(env)
                  ::Logger.new(env)
                end
              end
            end
        """,
    }, {('m:lib/rack.rb', 'm:lib/rack/builder.rb', 'import')}, {('f:lib/rack/logger.rb:Logger.call', 'c:lib/rack/logger.rb:Logger', 'call')}),

    ('ruby', 'superclase anidada, receptor tipado (x = X.new), self[k] = v y valor de un hash', {
        'lib/thor/argument.rb': """
            class Thor
              class Argument
                attr_reader :name

                def self.split(args)
                  args
                end

                def required?
                  true
                end
              end
            end
        """,
        'lib/thor/option.rb': """
            class Thor
              class Option < Argument
                def usage
                  required? ? name : nil
                end
              end
            end
        """,
        'lib/thor/table.rb': """
            class Thor
              class Table < Hash
                def []=(key, value)
                  super
                end

                def store(key, value)
                  self[key] = value
                  { label: value_name }
                end

                def value_name
                  1
                end
              end

              class Printer
                def print(rows)
                  rows
                end
              end

              class Runner
                def run(rows)
                  printer = Printer.new
                  printer.print(rows)
                  Thor::Option.split(rows)
                end
              end
            end
        """,
    }, {('f:lib/thor/option.rb:Option.usage', 'f:lib/thor/argument.rb:Argument.required?', 'call'),
        ('f:lib/thor/option.rb:Option.usage', 'f:lib/thor/argument.rb:Argument.name', 'call'),
        ('c:lib/thor/option.rb:Option', 'c:lib/thor/argument.rb:Argument', 'inherits'),
        ('f:lib/thor/table.rb:Table.store', 'f:lib/thor/table.rb:Table.[]=', 'call'),
        ('f:lib/thor/table.rb:Table.store', 'f:lib/thor/table.rb:Table.value_name', 'call'),
        ('f:lib/thor/table.rb:Runner.run', 'f:lib/thor/table.rb:Printer.print', 'call'),
        ('f:lib/thor/table.rb:Runner.run', 'f:lib/thor/argument.rb:Argument.split', 'call')}, ()),
    ('ruby', 'gancho self.included (base.extend), Struct.new y clases homónimas anidadas', {
        'lib/base.rb': """
            module Base
              def self.included(base)
                base.extend ClassMethods
              end

              module ClassMethods
                def commands
                  {}
                end
              end
            end

            class Command < Struct.new(:description)
              def run(other)
                other.description
              end
            end

            class Argument
              def description
                1
              end
            end

            class First
              class Checker
                def go
                  1
                end
              end
            end

            class Second
              class Checker
                def go
                  2
                end
              end
            end
        """,
        'lib/app.rb': """
            class App
              include Base

              def self.listing
                commands
              end
            end
        """,
    }, {('f:lib/app.rb:App.listing', 'f:lib/base.rb:ClassMethods.commands', 'call'),
        ('c:lib/base.rb:Second', 'c:lib/base.rb:Second.Checker', 'contains')},
     {('f:lib/base.rb:Command.run', 'f:lib/base.rb:Argument.description', 'call')}),

    # --- Java / Kotlin ---
    ('java', 'llamada encadenada con tipo de retorno', {
        'src/main/java/app/Engine.java': """
            package app;

            public class Engine {
              public static Engine make() { return new Engine(); }
              public int run() { return 1; }
              public int chain() { return Engine.make().run(); }
            }
        """,
    }, {('f:src/main/java/app/Engine.java:Engine.chain', 'f:src/main/java/app/Engine.java:Engine.run', 'call')}, ()),
    ('kotlin', 'lambda final y función de extensión', {
        'src/main/kotlin/app/Util.kt': """
            package app

            fun String.shout(): String = this.uppercase()

            fun runIt(block: () -> Unit) = block()

            fun main() {
              runIt { "x".shout() }
            }
        """,
    }, {('f:src/main/kotlin/app/Util.kt:main', 'f:src/main/kotlin/app/Util.kt:runIt', 'call')}, ()),

    ('kotlin', 'invoke de companion, constructor SAM, typealias, lambda que devuelve lambda y propiedad invocable', {
        'src/main/kotlin/app/Http.kt': """
            package app

            interface HttpMessage {
                fun header(name: String): String? = null
                fun header(name: String, value: String?): HttpMessage
            }

            interface Request : HttpMessage {
                override fun header(name: String, value: String?): Request
                companion object {
                    operator fun invoke(method: String): Request = TODO()
                }
            }

            class Response(val code: Int)

            typealias HttpHandler = (request: Request) -> Response

            fun interface Filter : (HttpHandler) -> HttpHandler {
                companion object
            }

            fun gunzip() = Filter { next ->
                { request ->
                    request.header("content-encoding")
                    next(request)
                }
            }

            fun build() = Request("GET")

            fun fold(rs: List<Request>, base: Request) = rs.fold(base) { acc, r -> acc.header("x", r.header("y")) }
        """,
        'src/main/kotlin/app/Lens.kt': """
            package app

            class LensGet<IN, OUT> private constructor(private val fn: (String, IN) -> List<OUT>) {
                operator fun invoke(name: String) = { t: IN -> fn(name, t) }
                companion object {
                    operator fun <IN, OUT> invoke(fn: (String, IN) -> List<OUT>): LensGet<IN, OUT> = LensGet(fn)
                }
            }

            open class Spec<IN, OUT>(internal val get: LensGet<IN, OUT>) {
                fun required(name: String) = get(name)
            }

            fun make() = LensGet<String, String> { _, _ -> listOf() }

            fun String.quoted() = replace("a", "b")

            class Template {
                private fun String.replace(x: Int): String = this
            }
        """,
    }, {('f:src/main/kotlin/app/Http.kt:build', 'f:src/main/kotlin/app/Http.kt:Request.invoke', 'call'),
        ('f:src/main/kotlin/app/Http.kt:gunzip', 'c:src/main/kotlin/app/Http.kt:Filter', 'call'),
        ('f:src/main/kotlin/app/Http.kt:gunzip', 'f:src/main/kotlin/app/Http.kt:HttpMessage.header', 'call'),
        ('f:src/main/kotlin/app/Http.kt:fold', 'f:src/main/kotlin/app/Http.kt:Request.header', 'call'),
        ('m:src/main/kotlin/app/Http.kt', 'c:src/main/kotlin/app/Http.kt:HttpHandler', 'contains'),
        ('f:src/main/kotlin/app/Lens.kt:Spec.required', 'f:src/main/kotlin/app/Lens.kt:LensGet.invoke', 'call'),
        ('f:src/main/kotlin/app/Lens.kt:make', 'f:src/main/kotlin/app/Lens.kt:LensGet.invoke', 'call'),
        ('f:src/main/kotlin/app/Lens.kt:LensGet.invoke', 'c:src/main/kotlin/app/Lens.kt:LensGet', 'call')},
        {('f:src/main/kotlin/app/Http.kt:build', 'c:src/main/kotlin/app/Http.kt:Request', 'call'),
         ('f:src/main/kotlin/app/Lens.kt:quoted', 'f:src/main/kotlin/app/Lens.kt:Template.replace', 'call')}),

    ('kotlin', 'objeto anidado invocable, override con valores por defecto, constante del companion importada y visibilidad de funciones', {
        'src/main/kotlin/app/core/Status.kt': """
            package app.core

            class Status internal constructor(val code: Int, val description: String) {
                fun description(d: String) = Status(code, d)

                companion object {
                    @JvmField val BAD_REQUEST = Status(400, "Bad Request")
                }
            }

            interface Builder {
                fun optional(name: String, description: String? = null): Lens
            }

            class Lens(val name: String) {
                operator fun invoke(x: Int) = 1
            }

            open class Spec : Builder {
                override fun optional(name: String, description: String?): Lens = Lens(name)
            }

            object Header : Spec() {
                val CONTENT_TYPE = optional("content-type")
            }

            class Mode(val compress: (String) -> Result) {
                fun use() = compress("x").apply()
            }

            class Result {
                fun apply() = 1
            }

            object Filters {
                object GunZip {
                    operator fun invoke(level: Int) = level
                }
            }
        """,
        'src/main/kotlin/app/web/Use.kt': """
            package app.web

            import app.core.Filters
            import app.core.Header.CONTENT_TYPE
            import app.core.Status
            import app.core.Status.Companion.BAD_REQUEST

            fun bad() = BAD_REQUEST.description("x")

            fun ct() = CONTENT_TYPE(1)

            fun gz() = Filters.GunZip(1)

            fun make() = Status(200, "OK")
        """,
        'src/main/kotlin/app/other/Factory.kt': """
            package app.other

            fun Status(x: Int, y: String) = 1
        """,
    }, {('f:src/main/kotlin/app/web/Use.kt:bad', 'f:src/main/kotlin/app/core/Status.kt:Status.description', 'call'),
        ('f:src/main/kotlin/app/web/Use.kt:ct', 'f:src/main/kotlin/app/core/Status.kt:Lens.invoke', 'call'),
        ('f:src/main/kotlin/app/web/Use.kt:gz', 'f:src/main/kotlin/app/core/Status.kt:GunZip.invoke', 'call'),
        ('f:src/main/kotlin/app/web/Use.kt:make', 'c:src/main/kotlin/app/core/Status.kt:Status', 'call'),
        ('f:src/main/kotlin/app/core/Status.kt:Mode.use', 'f:src/main/kotlin/app/core/Status.kt:Result.apply', 'call'),
        ('c:src/main/kotlin/app/core/Status.kt:Header', 'f:src/main/kotlin/app/core/Status.kt:Spec.optional', 'call')},
        {('f:src/main/kotlin/app/web/Use.kt:make', 'f:src/main/kotlin/app/other/Factory.kt:Status', 'call'),
         ('c:src/main/kotlin/app/core/Status.kt:Header', 'f:src/main/kotlin/app/core/Status.kt:Builder.optional', 'call')}),

    # --- Rust ---
    ('rust', 'método de rasgo sobre un genérico acotado y campo genérico', {
        'Cargo.toml': '[package]\nname = "demo"\n',
        'src/lib.rs': """
            pub trait Pred<T> {
                fn pair(&mut self, a: T, b: T) -> bool;
            }

            pub struct Coalesce<I, F> {
                iter: I,
                f: F,
            }

            impl<I: Iterator, F> Coalesce<I, F>
            where
                F: Pred<I::Item>,
            {
                fn step(&mut self, a: I::Item, b: I::Item) -> bool {
                    self.f.pair(a, b)
                }

                fn fold(self, a: I::Item, b: I::Item) -> bool {
                    let Self { iter, mut f } = self;
                    f.pair(a, b)
                }
            }
        """,
    }, {('f:src/lib.rs:Coalesce.step', 'f:src/lib.rs:Pred.pair', 'call'), ('f:src/lib.rs:Coalesce.fold', 'f:src/lib.rs:Pred.pair', 'call')}, ()),
    ('rust', 'alias de tipo, Self { … } y función anidada', {
        'Cargo.toml': '[package]\nname = "demo"\n',
        'src/lib.rs': """
            pub struct CombinationsGeneric<I> {
                it: I,
            }

            pub type Combinations<I> = CombinationsGeneric<I>;

            impl<I> CombinationsGeneric<I> {
                pub fn new(it: I) -> Self {
                    Self { it }
                }

                pub fn k(&self) -> usize {
                    0
                }
            }

            pub fn combinations<I>(it: I) -> Combinations<I> {
                fn helper() -> usize {
                    1
                }
                let c = Combinations::new(it);
                c.k() + helper();
                c
            }
        """,
    }, {('f:src/lib.rs:combinations', 'f:src/lib.rs:CombinationsGeneric.new', 'call'), ('f:src/lib.rs:combinations', 'f:src/lib.rs:CombinationsGeneric.k', 'call'),
        ('f:src/lib.rs:combinations', 'f:src/lib.rs:helper', 'call')}, ()),

    ('rust', 'parámetro de clausura por la cota Fn, argumento genérico del impl, tupla y #[cfg] activo', {
        'Cargo.toml': '[package]\nname = "demo"\n',
        'src/lib.rs': """
            pub struct DirEntry;

            impl DirEntry {
                pub fn file_name(&self) -> u8 { 0 }
                pub fn depth(&self) -> usize { 0 }

                #[cfg(windows)]
                fn metadata_internal(&self) -> u8 { 1 }

                #[cfg(not(windows))]
                fn metadata_internal(&self) -> u8 { 2 }
            }

            pub struct Walk;

            impl Walk {
                pub fn sort_by<F>(self, cmp: F) -> Self
                where
                    F: FnMut(&DirEntry, &DirEntry) -> u8,
                {
                    self
                }
                pub fn skip(&mut self) {}
            }

            pub struct Filter<I, P> {
                it: I,
                predicate: P,
            }

            impl<P> Filter<Walk, P> {
                pub fn skip(&mut self) {
                    self.it.skip();
                }
            }

            pub fn sorted(w: Walk, ents: Vec<DirEntry>) -> usize {
                let w = w.sort_by(|a, b| a.file_name());
                let (first, _second) = (&ents[0], &ents[1]);
                first.depth()
            }
        """,
    }, {('f:src/lib.rs:sorted', 'f:src/lib.rs:DirEntry.file_name', 'call'),
        ('f:src/lib.rs:sorted', 'f:src/lib.rs:DirEntry.depth', 'call'),
        ('f:src/lib.rs:Filter.skip', 'f:src/lib.rs:Walk.skip', 'call')}, ()),
    ('rust', 'supertrait y métodos de la biblioteca estándar sin adivinar', {
        'Cargo.toml': '[package]\nname = "demo"\n',
        'src/lib.rs': """
            pub trait TupleCollect {
                fn num_items() -> usize;
            }

            pub trait HomogeneousTuple: TupleCollect {}

            pub struct GroupingMap;

            impl GroupingMap {
                pub fn max_by(&self) -> usize { 0 }
            }

            pub fn count<T: HomogeneousTuple>(xs: Vec<u8>) -> usize {
                xs.iter().max_by(|a, b| a.cmp(b));
                T::num_items()
            }
        """,
    }, {('f:src/lib.rs:count', 'f:src/lib.rs:TupleCollect.num_items', 'call'), ('c:src/lib.rs:HomogeneousTuple', 'c:src/lib.rs:TupleCollect', 'inherits')},
        {('f:src/lib.rs:count', 'f:src/lib.rs:GroupingMap.max_by', 'call')}),

    # --- Dart ---
    ('dart', 'lista de inicialización, función local, operador y typedef', {
        'pubspec.yaml': 'name: demo\n',
        'lib/scanner.dart': """
            class Scanner {
              Scanner(String source);
              Object? advance() => null;
            }
        """,
        'lib/parser.dart': """
            import 'scanner.dart';

            typedef Callback = void Function(String message);

            class Parser {
              final Scanner _scanner;

              Parser(String source) : _scanner = Scanner(source);

              bool operator ==(Object other) => false;

              int deep(Object? v) {
                int inner(Object? x) {
                  return 1;
                }

                return inner(v);
              }
            }
        """,
    }, {('f:lib/parser.dart:Parser.Parser', 'c:lib/scanner.dart:Scanner', 'call'), ('f:lib/parser.dart:Parser.deep', 'f:lib/parser.dart:inner', 'call')}, ()),

    ('dart', 'super._(…) y this._(…) en la inicialización', {
        'pubspec.yaml': 'name: demo\n',
        'lib/node.dart': """
            class Node {
              Node._(Object? span);
            }

            class Scalar extends Node {
              Scalar.internal(Object? span) : super._(span);
              Scalar(Object? span) : this.internal(span);
            }
        """,
    }, {('f:lib/node.dart:Scalar.internal', 'f:lib/node.dart:Node._', 'call'), ('f:lib/node.dart:Scalar.Scalar', 'f:lib/node.dart:Scalar.internal', 'call')}, ()),

    ('dart', 'variable de nivel superior tipada y tipo con prefijo de import reexportado', {
        'pubspec.yaml': 'name: demo\n',
        'lib/src/context.dart': """
            Context createInternal() => Context();

            class Context {
              String basename(String path) => path;
              bool equals(String a, String b) => a == b;
            }
        """,
        'lib/src/parsed.dart': """
            class Parsed {
              String get basename => '';
            }
        """,
        'lib/path.dart': """
            import 'src/context.dart';
            export 'src/context.dart';

            final Context context = createInternal();

            String basename(String path) => context.basename(path);
        """,
        'lib/src/path_set.dart': """
            import '../path.dart' as p;

            class PathSet {
              static bool create(p.Context? context) {
                return context!.equals('a', 'b');
              }
            }
        """,
    }, {('f:lib/path.dart:basename', 'f:lib/src/context.dart:Context.basename', 'call'),
        ('f:lib/src/path_set.dart:PathSet.create', 'f:lib/src/context.dart:Context.equals', 'call'),
        ('m:lib/src/path_set.dart', 'm:lib/src/context.dart', 'import')}, ()),

    # --- PHP ---
    ('php', 'tipo de una propiedad en PHPDoc', {
        'src/UriInterface.php': """
            <?php
            namespace App;

            interface UriInterface
            {
                public function getPath(): string;
            }
        """,
        'src/Uri.php': """
            <?php
            namespace App;

            class Uri implements UriInterface
            {
                public function getPath(): string { return ''; }
            }
        """,
        'src/Request.php': """
            <?php
            namespace App;

            class Request
            {
                /** @var UriInterface */
                private $uri;

                public function __construct($uri)
                {
                    $this->uri = new Uri();
                }

                public function target(): string
                {
                    return $this->uri->getPath();
                }
            }
        """,
    }, {('f:src/Request.php:Request.target', 'f:src/UriInterface.php:UriInterface.getPath', 'call')},
        {('f:src/Request.php:Request.target', 'f:src/Uri.php:Uri.getPath', 'call')}),

    ('php', '@method del PHPDoc, atributo #[X(…)], unión con una clase del proyecto, use global y $f()', {
        'src/Stream.php': """
            <?php
            namespace App;

            final class Stream
            {
                public function getPathname(): string { return ''; }
            }
        """,
        'src/Exception.php': """
            <?php
            namespace App;

            class Exception extends \\Exception {}
        """,
        'src/MapCell.php': """
            <?php
            namespace App;

            #[\\Attribute]
            final class MapCell
            {
                public function __construct(public int $column = 0) {}
            }
        """,
        'src/Reader.php': """
            <?php
            namespace App;

            use Exception;

            /**
             * @method Stream first() devuelve el primer registro
             * @method iterable<int, Reader> matching(string $e) fragmentos
             */
            class Reader
            {
                public function __construct(private \\SplFileObject|Stream $document, private ?\\Closure $where = null) {}

                public function path(): string { return $this->document->getPathname(); }

                public function firstPath(): string { return $this->first()->getPathname(); }

                #[MapCell(column: 2)]
                public function run(): void { ($this->where)(); $where = $this->where; $where(); }

                public function where(): void {}
            }

            final class Failure extends Exception {}
        """,
    }, {('f:src/Reader.php:Reader.path', 'f:src/Stream.php:Stream.getPathname', 'call'),
        ('f:src/Reader.php:Reader.firstPath', 'f:src/Reader.php:Reader.first', 'call'),
        ('f:src/Reader.php:Reader.firstPath', 'f:src/Stream.php:Stream.getPathname', 'call'),
        ('f:src/Reader.php:Reader.run', 'c:src/MapCell.php:MapCell', 'call')},
        {('f:src/Reader.php:Reader.run', 'f:src/Reader.php:Reader.where', 'call'),
         ('c:src/Reader.php:Failure', 'c:src/Exception.php:Exception', 'inherits')}),

    # --- C# ---
    ('csharp', 'cabecera partida por #if/#else', {
        'src/Binder.cs': """
            namespace App
            {
                class Binder
                {
            #if FEATURE_SPAN
                    public int Construct(System.ReadOnlySpan<object> values)
            #else
                    public int Construct(object[] values)
            #endif
                    {
                        return Helper();
                    }

                    int Helper() { return 1; }
                }
            }
        """,
    }, {('f:src/Binder.cs:Binder.Construct', 'f:src/Binder.cs:Binder.Helper', 'call')}, ()),

    ('csharp', '#if del marco de destino, delegado, ref partial struct, T de la base genérica y char de un string', {
        'src/Text.cs': """
            namespace App
            {
            #if !NET
                public static class Polyfill { public static int Clamp(int x) { return x; } }
            #endif
                public delegate bool Matcher(char c);

                internal ref partial struct Builder
                {
                    public void Append(char c) { }
                }

                public static class CharHelper
                {
                    public static bool IsDigitX(this char c) { return true; }
                }

                public abstract class RendererBase<T> where T : RendererBase<T>
                {
                    public T Write(string s) { return (T)this; }
                }

                public class Html : RendererBase<Html>
                {
                    public Html Attributes() { return this; }

                    public void Render(string text, Html renderer)
                    {
                        renderer.Write("x").Attributes();
                        var c = text[0];
                        c.IsDigitX();
            #if NETFRAMEWORK
                        Polyfill.Clamp(1);
            #else
                        new Builder().Append(c);
            #endif
                    }
                }
            }
        """,
    }, {('f:src/Text.cs:Html.Render', 'f:src/Text.cs:Html.Attributes', 'call'),
        ('f:src/Text.cs:Html.Render', 'f:src/Text.cs:CharHelper.IsDigitX', 'call'),
        ('f:src/Text.cs:Html.Render', 'f:src/Text.cs:Builder.Append', 'call'),
        ('m:src/Text.cs', 'c:src/Text.cs:Matcher', 'contains')},
        {('f:src/Text.cs:Html.Render', 'f:src/Text.cs:Polyfill.Clamp', 'call'),
         ('m:src/Text.cs', 'c:src/Text.cs:Polyfill', 'contains')}),

    # --- Más construcciones por lenguaje ---
    ('python', 'herencia y super()', {'app/a.py': """
        class Base:
            def save(self):
                return 1


        class Child(Base):
            def save(self):
                return super().save()

            def run(self):
                return self.save()
    """}, {('f:app/a.py:Child.save', 'f:app/a.py:Base.save', 'call'), ('f:app/a.py:Child.run', 'f:app/a.py:Child.save', 'call'), ('c:app/a.py:Child', 'c:app/a.py:Base', 'inherits')}, ()),
    ('python', 'propiedad leída como atributo (referencia entre archivos)', {'app/cfg.py': """
        class Cfg:
            @property
            def size(self) -> int:
                return 1
    """, 'app/use.py': """
        from app.cfg import Cfg


        def use(c: Cfg):
            return c.size
    """}, {('f:app/use.py:use', 'f:app/cfg.py:Cfg.size', 'ref')}, ()),
    ('python', 'async/await', {'app/a.py': """
        class Client:
            async def get(self):
                return 1


        async def run(c: Client):
            return await c.get()
    """}, {('f:app/a.py:run', 'f:app/a.py:Client.get', 'call')}, ()),
    ('typescript', 'decorador, async y desestructuración', {'src/a.ts': """
        function log(target: any, key: string) {}
        export class Repo {
          async find(id: string): Promise<Repo> { return this; }
          save() { return 1; }
        }
        export class Service {
          constructor(private repo: Repo) {}
          @log
          async run() {
            const found = await this.repo.find('x');
            return found.save();
          }
        }
        export function pick({ repo }: { repo: Repo }) { return repo.save(); }
    """}, {('f:src/a.ts:Service.run', 'f:src/a.ts:Repo.find', 'call'), ('f:src/a.ts:Service.run', 'f:src/a.ts:Repo.save', 'call')}, ()),
    ('typescript', 'componente JSX y re-export', {'src/Button.tsx': """
        export function Button() { return <button />; }
    """, 'src/index.ts': """
        export { Button } from './Button';
    """, 'src/App.tsx': """
        import { Button } from './index';
        export function App() { return <Button />; }
    """}, {('f:src/App.tsx:App', 'f:src/Button.tsx:Button', 'call'), ('m:src/App.tsx', 'm:src/Button.tsx', 'import')}, ()),
    ('typescript', 'herencia e interfaz (this.método heredado)', {'src/a.ts': """
        interface Shape { area(): number }
        class Base implements Shape {
          area() { return 1; }
        }
        class Square extends Base {
          twice() { return this.area() * 2; }
        }
    """}, {('f:src/a.ts:Square.twice', 'f:src/a.ts:Base.area', 'call'), ('c:src/a.ts:Square', 'c:src/a.ts:Base', 'inherits')}, ()),
    ('go', 'genéricos e interfaz', {'go.mod': 'module example.com/app\n', 'p/a.go': """
        package p

        type Saver interface{ Save() error }

        type Store struct{}

        func (s Store) Save() error { return nil }

        func Map[T any](xs []T, f func(T) T) []T { return xs }

        func Use(s Saver) []int {
          _ = s.Save()
          return Map([]int{1}, func(x int) int { return x })
        }
    """}, {('f:p/a.go:Use', 'f:p/a.go:Map', 'call')}, ()),
    ('java', 'lambda, referencia a método e import estático', {'src/main/java/app/Util.java': """
        package app;

        public class Util {
          public static int twice(int x) { return 2 * x; }
        }
    """, 'src/main/java/app/Use.java': """
        package app;

        import static app.Util.twice;
        import java.util.function.Function;

        public class Use {
          int run() {
            Function<Integer, Integer> f = x -> twice(x);
            Function<Integer, Integer> g = Util::twice;
            return f.apply(1) + g.apply(2);
          }
        }
    """}, {('f:src/main/java/app/Use.java:Use.run', 'f:src/main/java/app/Util.java:Util.twice', 'call')}, ()),
    ('java', 'clase anónima y genérico new X<>()', {'src/main/java/app/A.java': """
        package app;

        public class A {
          static abstract class Adapter<T> { abstract T read(); }
          static class Box<T> { T get() { return null; } }

          static Adapter<String> make(Box<String> box) {
            return new Adapter<String>() {
              String read() { return box.get(); }
            };
          }

          static Box<String> box() { return new Box<>(); }
        }
    """}, {('f:src/main/java/app/A.java:A.make', 'f:src/main/java/app/A.java:Box.get', 'call'), ('f:src/main/java/app/A.java:A.box', 'c:src/main/java/app/A.java:Box', 'call')}, ()),
    ('kotlin', 'data class, companion y object', {'src/main/kotlin/app/A.kt': """
        package app

        data class User(val name: String) {
          companion object {
            fun create(): User = User("x")
          }
          fun greet(): String = name
        }

        object Registry {
          fun find(): User = User.create()
        }

        fun use(): String = Registry.find().greet()
    """}, {('f:src/main/kotlin/app/A.kt:use', 'f:src/main/kotlin/app/A.kt:Registry.find', 'call'), ('f:src/main/kotlin/app/A.kt:use', 'f:src/main/kotlin/app/A.kt:User.greet', 'call')}, ()),
    ('rust', 'impl Trait for X, método por defecto y macros', {'Cargo.toml': '[package]\nname = "demo"\n', 'src/lib.rs': """
        pub trait Greet {
            fn name(&self) -> String;
            fn greet(&self) -> String { self.name() }
        }

        pub struct User;

        impl Greet for User {
            fn name(&self) -> String { String::new() }
        }

        pub fn run(u: &User) -> usize {
            assert_eq!(u.greet().len(), helper());
            helper()
        }

        fn helper() -> usize { 0 }
    """}, {('f:src/lib.rs:run', 'f:src/lib.rs:Greet.greet', 'call'), ('f:src/lib.rs:run', 'f:src/lib.rs:helper', 'call'), ('f:src/lib.rs:Greet.greet', 'f:src/lib.rs:Greet.name', 'call')}, ()),
    ('dart', 'mixin, extensión y cascada', {'pubspec.yaml': 'name: demo\n', 'lib/a.dart': """
        mixin Logger {
          void log(String m) {}
        }

        class Service with Logger {
          void run() {
            log('x');
          }
          Service config() => this;
        }

        extension Shout on String {
          String shout() => toUpperCase();
        }

        void use() {
          Service()
            ..run()
            ..config();
        }
    """}, {('f:lib/a.dart:Service.run', 'f:lib/a.dart:Logger.log', 'call'), ('f:lib/a.dart:use', 'f:lib/a.dart:Service.run', 'call')}, ()),
    ('php', 'trait, llamada estática y new', {'src/A.php': """
        <?php
        namespace App;

        trait Greets {
            public function greet(): string { return 'hi'; }
        }

        class Util {
            public static function twice(int $x): int { return 2 * $x; }
        }

        class User {
            use Greets;

            public function run(): string {
                Util::twice(1);
                $u = new User();
                return $this->greet();
            }
        }
    """}, {('f:src/A.php:User.run', 'f:src/A.php:Util.twice', 'call'), ('f:src/A.php:User.run', 'f:src/A.php:Greets.greet', 'call'), ('f:src/A.php:User.run', 'c:src/A.php:User', 'call')}, ()),
    ('csharp', 'clase parcial, método de extensión y atributo', {'src/A.cs': """
        namespace App
        {
            public class FormatAttribute : System.Attribute
            {
                public FormatAttribute(string name) {}
            }

            public static class StringExt
            {
                public static string Shout(this string s) { return s; }
            }

            public partial class Service
            {
                [Format("x")]
                public string Run() { return Helper().Shout(); }
            }
        }
    """, 'src/B.cs': """
        namespace App
        {
            public partial class Service
            {
                string Helper() { return ""; }
            }
        }
    """}, {('f:src/A.cs:Service.Run', 'f:src/B.cs:Service.Helper', 'call'), ('f:src/A.cs:Service.Run', 'f:src/A.cs:StringExt.Shout', 'call'),
           ('f:src/A.cs:Service.Run', 'c:src/A.cs:FormatAttribute', 'call')}, ()),
    ('ruby', 'bloque y X.new de clase anidada', {'lib/a.rb': """
        class Request
          class Entry
            def initialize(e); end
          end

          def accept(list)
            list.map { |e| Entry.new(e) }
          end
        end
    """}, {('f:lib/a.rb:Request.accept', 'c:lib/a.rb:Entry', 'call')}, ()),

    # --- Lenguajes sin referencia SCIP ---

    ('swift', 'clase, método y llamada entre archivos', {
        'Sources/App/Engine.swift': """
            class Engine {
                func run() -> Int { return helper() }
            }
            func helper() -> Int { return 1 }
        """,
        'Sources/App/Main.swift': """
            func start() {
                let e = Engine()
                _ = e.run()
                _ = helper()
            }
        """,
    }, {('f:Sources/App/Main.swift:start', 'f:Sources/App/Engine.swift:helper', 'call'), ('f:Sources/App/Main.swift:start', 'c:Sources/App/Engine.swift:Engine', 'call'),
        ('f:Sources/App/Engine.swift:Engine.run', 'f:Sources/App/Engine.swift:helper', 'call')}, ()),
    ('swift', 'extensión y protocolo', {
        'Sources/App/Ext.swift': """
            protocol Named { func name() -> String }
            struct User: Named { func name() -> String { return "u" } }
            extension User {
                func greet() -> String { return name() }
            }
        """,
    }, {('f:Sources/App/Ext.swift:User.greet', 'f:Sources/App/Ext.swift:User.name', 'call'), ('c:Sources/App/Ext.swift:User', 'c:Sources/App/Ext.swift:Named', 'inherits')}, ()),
    ('c', 'función y #include', {
        'src/util.h': "int helper(void);\n",
        'src/util.c': '#include "util.h"\nint helper(void) { return 1; }\n',
        'src/main.c': '#include "util.h"\nint main(void) { return helper(); }\n',
    }, {('f:src/main.c:main', 'f:src/util.c:helper', 'call'), ('m:src/main.c', 'm:src/util.h', 'import')}, ()),
    ('cpp', 'clase, método y espacio de nombres', {
        'src/engine.hpp': "namespace app { class Engine { public: int run(); }; }\n",
        'src/engine.cpp': '#include "engine.hpp"\nnamespace app { int Engine::run() { return helper(); } int helper() { return 1; } }\n',
        'src/main.cpp': '#include "engine.hpp"\nint main() { app::Engine e; return e.run(); }\n',
    }, {('m:src/main.cpp', 'm:src/engine.hpp', 'import')}, ()),
    ('scala', 'objeto, clase y llamada', {
        'src/main/scala/app/Engine.scala': """
            package app

            class Engine {
              def run(): Int = Helper.help()
            }

            object Helper {
              def help(): Int = 1
            }
        """,
    }, {('f:src/main/scala/app/Engine.scala:Engine.run', 'f:src/main/scala/app/Engine.scala:Helper.help', 'call')}, ()),
    ('elixir', 'módulos, alias y llamada calificada', {
        'lib/app/helper.ex': """
            defmodule App.Helper do
              def help(x), do: x
            end
        """,
        'lib/app/engine.ex': """
            defmodule App.Engine do
              alias App.Helper

              def run(x) do
                Helper.help(x) |> local()
              end

              defp local(x), do: x
            end
        """,
    }, {('f:lib/app/engine.ex:App.Engine.run', 'f:lib/app/helper.ex:App.Helper.help', 'call'), ('f:lib/app/engine.ex:App.Engine.run', 'f:lib/app/engine.ex:App.Engine.local', 'call')}, ()),
    ('lua', 'require y función de tabla', {
        'src/util.lua': """
            local M = {}
            function M.helper() return 1 end
            return M
        """,
        'src/main.lua': """
            local util = require('util')
            local function start() return util.helper() end
            return start
        """,
    }, {('m:src/main.lua', 'm:src/util.lua', 'import')}, ()),
    # --- Ronda 4 ---
    ('typescript', 'export = X, export { default as X }, parámetro this, propiedad typeof f y tipo objeto en línea', {
        'lib/render.ts': """
            class Render {
              render(path: string) { return path; }
            }
            export = Render;
        """,
        'lib/extend/console.ts': """
            class Console {
              register(name: string) { return name; }
            }
            export = Console;
        """,
        'lib/extend/index.ts': """
            export { default as Console } from './console';
        """,
        'lib/index.ts': """
            import Render from './render';
            import { Console } from './extend';
            import Index from './models/index';

            interface Extend { console: Console }

            class Hexo {
              public render: Render;
              public extend: Extend;
              public _index: { post_tag: Index };
              constructor() {
                this.render = new Render();
                this.extend = { console: new Console() };
              }
              load() { return this._index.post_tag.load(); }
            }
            export = Hexo;
        """,
        'lib/models/index.ts': """
            export default class Index {
              load() { return 1; }
            }
        """,
        'lib/plugins/clean.ts': """
            import type Hexo from '../index';

            function cleanConsole(this: Hexo) {
              const { console } = this.extend;
              console.register('clean');
              return this.render.render('x');
            }
            export = cleanConsole;
        """,
        'lib/helpers.ts': """
            export function dateHelper(d: string) { return d; }
        """,
        'lib/types.ts': """
            import { dateHelper } from './helpers';
            export interface LocalsType { date: typeof dateHelper; }
        """,
        'lib/plugins/full.ts': """
            import type { LocalsType } from '../types';
            export function fullDate(this: LocalsType, d: string) { return this.date(d); }
        """,
    }, {('f:lib/index.ts:Hexo.constructor', 'c:lib/render.ts:Render', 'call'),
        ('f:lib/index.ts:Hexo.constructor', 'c:lib/extend/console.ts:Console', 'call'),
        ('f:lib/index.ts:Hexo.load', 'f:lib/models/index.ts:Index.load', 'call'),
        ('f:lib/plugins/clean.ts:cleanConsole', 'f:lib/render.ts:Render.render', 'call'),
        ('f:lib/plugins/clean.ts:cleanConsole', 'f:lib/extend/console.ts:Console.register', 'call'),
        ('f:lib/plugins/full.ts:fullDate', 'f:lib/types.ts:LocalsType.date', 'call')}, ()),
    ('typescript', 'claves de un objeto literal tipado y desestructuración como dependencia', {
        'src/opts.ts': """
            export interface Options { path: string; }
            export class Theme { i18n = 1; }
        """,
        'src/render.ts': """
            import { Options } from './opts';
            export function render(o: Options) { return o; }
        """,
        'src/use.ts': """
            import { render } from './render';
            import { Theme } from './opts';
            export function go(p: string, t: Theme) {
              const { i18n } = t;
              return render({ path: p });
            }
        """,
    }, {('f:src/use.ts:go', 'c:src/opts.ts:Options', 'ref'), ('f:src/use.ts:go', 'c:src/opts.ts:Theme', 'ref')}, ()),
    ('javascript', 'cadena exports, alias de require, función de la biblioteca estándar y retorno inferido', {
        'lib/base.js': """
            function Base() {}
            var color = (exports.color = function (type, str) { return str; });
            exports = module.exports = Base;
        """,
        'lib/errors.js': """
            function createError(msg) { return new Error(msg); }
            module.exports = { createError: createError };
        """,
        'lib/lookup.js': """
            module.exports = function lookupFiles(p) { return [p]; };
        """,
        'lib/pool.js': """
            class Pool {
              run() { return 1; }
              static create() { return new Pool(); }
            }
            module.exports = Pool;
        """,
        'lib/list.js': """
            var Base = require('./base');
            var color = Base.color;
            var createError = require('./errors').createError;
            const lookupFiles = require('./lookup');
            const Pool = require('./pool');
            var abs = Math.abs;
            function List() {
              let pool;
              pool = Pool.create();
              pool.run();
              lookupFiles('x');
              abs(-1);
              throw createError(color('pass', 'x'));
            }
            module.exports = List;
        """,
    }, {('f:lib/list.js:List', 'f:lib/list.js:color', 'call'), ('f:lib/list.js:List', 'f:lib/errors.js:createError', 'call'),
        ('f:lib/list.js:List', 'f:lib/pool.js:Pool.run', 'call'), ('f:lib/list.js:List', 'f:lib/list.js:abs', 'call'),
        ('f:lib/list.js:lookupFiles', 'f:lib/lookup.js:module.exports', 'ref'), ('f:lib/list.js:color', 'f:lib/base.js:color', 'ref')},
     {('f:lib/list.js:List', 'f:lib/list.js:createError', 'call')}),
    ('ruby', 'variable de rescue y constantes del núcleo de Ruby', {
        'lib/jekyll/log_adapter.rb': """
            module Jekyll
              class LogAdapter
                def message(topic)
                  topic
                end
              end
            end
        """,
        'lib/jekyll/liquid_renderer/file.rb': """
            module Jekyll
              class LiquidRenderer
                class File
                  def self.join(a, b)
                    a
                  end
                end
              end
            end
        """,
        'lib/jekyll/command.rb': """
            module Jekyll
              class Command
                def process(site)
                  site.process
                rescue StandardError => e
                  e.message
                end

                def path
                  File.join("a", "b")
                end
              end
            end
        """,
    }, set(), {('f:lib/jekyll/command.rb:Command.process', 'f:lib/jekyll/log_adapter.rb:LogAdapter.message', 'call'),
               ('m:lib/jekyll/command.rb', 'm:lib/jekyll/liquid_renderer/file.rb', 'import'),
               ('f:lib/jekyll/command.rb:Command.path', 'f:lib/jekyll/liquid_renderer/file.rb:LiquidRenderer.File.self.join', 'call')}),
    ('kotlin', 'propiedad de extensión, extensión importada sobre receptor desconocido y propiedad importada', {
        'src/main/kotlin/core/Ext.kt': """
            package core

            import org.ext.Node

            val Node.prevLeaf: Node?
                get() = null

            fun Node.remove() {}

            fun Node.upsertAfter(text: String) {}

            val INDENT_PROPERTY: String = "indent"
        """,
        'src/main/kotlin/core/Pattern.kt': """
            package core

            class Pattern {
                fun matches(s: String): Boolean = true
            }
        """,
        'src/main/kotlin/rules/Rule.kt': """
            package rules

            import core.INDENT_PROPERTY
            import core.prevLeaf
            import core.remove
            import core.upsertAfter
            import org.ext.Node
            import org.ext.findChild

            class Rule {
                fun visit(node: Node) {
                    node.prevLeaf?.let { ws -> ws.remove() }
                    node.findChild(1).upsertAfter(INDENT_PROPERTY)
                }

                private fun Node.isValid() = text.matches(Regex("x"))
            }
        """,
    }, {('f:src/main/kotlin/rules/Rule.kt:Rule.visit', 'f:src/main/kotlin/core/Ext.kt:remove', 'call'),
        ('f:src/main/kotlin/rules/Rule.kt:Rule.visit', 'f:src/main/kotlin/core/Ext.kt:upsertAfter', 'call')},
     {('f:src/main/kotlin/rules/Rule.kt:Rule.isValid', 'f:src/main/kotlin/core/Pattern.kt:Pattern.matches', 'call')}),
    ('csharp', 'polyfill bajo #if !NET5_0_OR_GREATER con marca BOM al inicio', {
        'src/NRT.cs': '﻿' + """#if !NET5_0_OR_GREATER
            namespace System.Diagnostics.CodeAnalysis
            {
                internal sealed class NotNullWhenAttribute : System.Attribute
                {
                    public NotNullWhenAttribute(bool v) { }
                }
            }
            #endif
        """,
        'src/Link.cs': """
            using System.Diagnostics.CodeAnalysis;
            namespace App
            {
                class Link
                {
                    public bool TryGet([NotNullWhen(true)] out string value) { value = ""; return true; }
                }
            }
        """,
    }, set(), {('f:src/Link.cs:Link.TryGet', 'c:src/NRT.cs:NotNullWhenAttribute', 'call')}),
    ('python', 'import relativo de un paquete que reexporta', {
        'app/__init__.py': '',
        'app/nested/__init__.py': """
            from .core import interpret
        """,
        'app/nested/core.py': """
            def interpret(x):
                return x
        """,
        'app/client.py': """
            from .nested import interpret
            from . import util


            def go():
                return interpret(1)
        """,
        'app/util.py': '',
    }, {('m:app/client.py', 'm:app/nested/__init__.py', 'import'), ('f:app/client.py:go', 'f:app/nested/core.py:interpret', 'call')},
     {('m:app/client.py', 'm:app/__init__.py', 'import')}),
    # --- ronda 5 ---
    ('kotlin', '`where` como variable, anotación de un accesor, extensión que admite los argumentos y propiedad importada con *', {
        'src/main/kotlin/v/Dialect.kt': """
            package v

            interface Dialect {
                fun reset()
            }

            val current: Dialect get() = TODO()
        """,
        'src/main/kotlin/q/Builder.kt': """
            package q

            class Builder {
                fun append(value: String): Builder = this
            }

            fun Builder.append(vararg expr: Any): Builder = this
        """,
        'src/main/kotlin/q/Query.kt': """
            package q

            import v.*

            class Query(val where: String?) {
                var flag: Int?
                    @Synchronized get() = 1
                    @Synchronized set(value) { }

                fun build(b: Builder) {
                    b.append("x")
                    where?.let { b.append("a", it, "b") }
                    current.reset()
                }

                fun later() = 2
            }
        """,
    }, {('f:src/main/kotlin/q/Query.kt:Query.build', 'f:src/main/kotlin/q/Builder.kt:Builder.append', 'call'),
        ('f:src/main/kotlin/q/Query.kt:Query.build', 'f:src/main/kotlin/q/Builder.kt:append', 'call'),
        ('f:src/main/kotlin/q/Query.kt:Query.build', 'f:src/main/kotlin/v/Dialect.kt:Dialect.reset', 'call'),
        ('c:src/main/kotlin/q/Query.kt:Query', 'f:src/main/kotlin/q/Query.kt:Query.later', 'contains')}, ()),
    ('typescript', 'unión de tipos del proyecto, constante importada a través de un barril y alias de Object', {
        'src/scope.ts': """
            export interface Scope {
                strict_(): boolean
            }
        """,
        'src/types.ts': """
            import {Scope} from "./scope"
            export interface BaseState {
                scope_: Scope
                modified_: boolean
            }
            export interface ObjState extends BaseState {
                base_: any
                revoke_(): void
            }
            export interface MapState extends BaseState {
                base_: Map<any, any>
                revoke_(): void
            }
            export type State = ObjState | MapState
        """,
        'src/env.ts': """
            export const DRAFT = Symbol("draft")
        """,
        'src/common.ts': """
            const O = Object
            export const getProto = O.getPrototypeOf
        """,
        'src/internal.ts': """
            export * from "./env"
            export * from "./types"
            export * from "./common"
        """,
        'src/use.ts': """
            import {State, DRAFT, getProto} from "./internal"
            export function current(value: any) {
                const state: State | undefined = value[DRAFT]
                if (state) {
                    state.revoke_()
                    getProto(state.base_)
                    return state.scope_.strict_()
                }
            }
        """,
    }, {('f:src/use.ts:current', 'f:src/types.ts:ObjState.revoke_', 'call'), ('f:src/use.ts:current', 'f:src/types.ts:MapState.revoke_', 'call'),
        ('f:src/use.ts:current', 'f:src/scope.ts:Scope.strict_', 'call'), ('f:src/use.ts:current', 'f:src/common.ts:getProto', 'call'),
        ('m:src/use.ts', 'm:src/env.ts', 'import')}, ()),
    ('csharp', 'clase parcial como tipo, miembro heredado o de otra parte, clave de inicializador y grupo de métodos', {
        'src/Base.cs': """
            namespace App;

            public class StrategyOptions
            {
                public string Name { get; set; }
                public double InjectionRate { get; set; }
            }
        """,
        'src/Opts.cs': """
            namespace App;

            public class ChaosOptions : StrategyOptions
            {
                public ChaosOptions() => Name = "x";
            }
        """,
        'src/Pipe.cs': """
            namespace App;

            public partial class Pipeline
            {
                internal Component Component { get; }
            }
        """,
        'src/Pipe.Async.cs': """
            namespace App;

            public partial class Pipeline
            {
                public int Run() => Component.Execute();
            }
        """,
        'src/Component.cs': """
            namespace App;

            public class Component
            {
                public int Execute() => 1;
            }

            public static class RandomUtil
            {
                public static double NextDouble() => 0.5;
            }
        """,
        'src/Use.cs': """
            namespace App;

            public class Provider
            {
                public virtual Pipeline GetPipeline(string key) => null;
                public Func<double> Randomizer { get; set; } = RandomUtil.NextDouble;
                public object Make(double r) => new ChaosOptions { InjectionRate = r };
            }
        """,
    }, {('m:src/Use.cs', 'm:src/Pipe.Async.cs', 'import'), ('m:src/Pipe.Async.cs', 'm:src/Pipe.cs', 'import'),
        ('m:src/Use.cs', 'm:src/Base.cs', 'import'), ('m:src/Use.cs', 'm:src/Component.cs', 'import')},
     {('m:src/Use.cs', 'm:src/Pipe.cs', 'import')}),
    ('dart', 'instancia de una clase genérica `Caja<T>(x)`', {
        'lib/a.dart': """
            class Box<T> {
              Box(this.v);
              final T v;
            }

            class User<T> {
              Iterator<T> get iterator => _It<T>(1);
              Box<T> make(T x) => Box<T>(x);
            }

            class _It<T> {
              _It(int x);
            }
        """,
    }, {('f:lib/a.dart:User.iterator', 'c:lib/a.dart:_It', 'call'), ('f:lib/a.dart:User.make', 'c:lib/a.dart:Box', 'call')}, ()),
    ('rust', '`use super::x` dentro de un `mod tests` en línea es el propio archivo', {
        'Cargo.toml': '[package]\nname = "app"\nversion = "0.1.0"\n',
        'src/lib.rs': """
            mod filter;
        """,
        'src/filter/mod.rs': """
            pub mod size;

            pub struct Filter;
        """,
        'src/filter/size.rs': """
            pub fn parse() -> u32 {
                1
            }

            #[cfg(test)]
            mod tests {
                use super::parse;

                #[test]
                fn t() {
                    parse();
                }
            }
        """,
    }, set(), {('m:src/filter/size.rs', 'm:src/filter/mod.rs', 'import')}),
    ('python', 'base genérica `class Choice(ParamType[str])`', {
        'app/types.py': """
            import typing as t

            T = t.TypeVar('T')


            class ParamType(t.Generic[T]):
                def fail(self):
                    raise ValueError()


            class Choice(ParamType[str]):
                def convert(self):
                    self.fail()
        """,
    }, {('f:app/types.py:Choice.convert', 'f:app/types.py:ParamType.fail', 'call'),
        ('c:app/types.py:Choice', 'c:app/types.py:ParamType', 'inherits')}, ()),
    ('kotlin', '`buildString { append() }`, extensión miembro desde una lambda con receptor, `by lazy` y propiedad de nivel superior leída', {
        'src/main/kotlin/q/Builder.kt': """
            package q

            class Builder {
                fun <T> Iterable<T>.appendTo(b: Builder) {}
                operator fun invoke(body: Builder.() -> Unit) { body() }
            }

            fun Builder.append(vararg expr: Any): Builder = this
        """,
        'src/main/kotlin/q/Log.kt': """
            package q

            val logger: Logger = Logger()

            class Logger {
                fun error(msg: String) {}
            }
        """,
        'src/main/kotlin/q/Dialect.kt': """
            package q

            class Provider {
                fun explain(): String = ""
            }

            class Dialect {
                val provider: Provider = Provider()
            }

            class Db {
                val dialect by lazy {
                    Dialect()
                }
            }
        """,
        'src/main/kotlin/q/Use.kt': """
            package q

            class Use {
                fun sqlType(): String = buildString {
                    append("x")
                }

                fun build(qb: Builder, cols: List<String>, db: Db) {
                    qb {
                        cols.appendTo(this)
                    }
                    logger.error("x")
                    db.dialect.provider.explain()
                }
            }
        """,
    }, {('f:src/main/kotlin/q/Use.kt:Use.build', 'f:src/main/kotlin/q/Builder.kt:Builder.appendTo', 'call'),
        ('f:src/main/kotlin/q/Use.kt:Use.build', 'f:src/main/kotlin/q/Dialect.kt:Provider.explain', 'call'),
        ('f:src/main/kotlin/q/Use.kt:Use.build', 'f:src/main/kotlin/q/Log.kt:Logger.error', 'call')},
     {('f:src/main/kotlin/q/Use.kt:Use.sqlType', 'f:src/main/kotlin/q/Builder.kt:append', 'call')}),
    ('javascript', 'miembros de un objeto exportado por defecto (`export default { isArray, own: hasOwn }`)', {
        'lib/utils.js': """
            function isArray(x) {
              return Array.isArray(x)
            }

            const hasOwn = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key)

            export default {
              isArray,
              own: hasOwn
            }
        """,
        'lib/use.js': """
            import utils from './utils.js'

            export function check(x) {
              return utils.isArray(x) && utils.own(x, 'a')
            }
        """,
    }, {('f:lib/use.js:check', 'f:lib/utils.js:isArray', 'call'), ('f:lib/use.js:check', 'f:lib/utils.js:hasOwn', 'call')}, ()),
    ('kotlin', 'llamada infija heredada (`CONTENT_TYPE of x`) como dependencia', {
        'src/main/kotlin/lens/Inject.kt': """
            package lens

            interface LensInjector<in IN> {
                infix fun of(value: IN): String = value.toString()
            }
        """,
        'src/main/kotlin/lens/BiDi.kt': """
            package lens

            class BiDiLens<T> : LensInjector<T>
        """,
        'src/main/kotlin/web/Header.kt': """
            package web

            import lens.BiDiLens

            val CONTENT_TYPE: BiDiLens<String> = BiDiLens()

            fun contentType(x: String) = CONTENT_TYPE of x
        """,
    }, {('m:src/main/kotlin/web/Header.kt', 'm:src/main/kotlin/lens/Inject.kt', 'import')}, ()),
    ('javascript', 'clave renombrada de `module.exports = { exist: checkExistence }` y llamada sobre `require(…)` en línea', {
        'lib/decorate.js': """
            function checkExistence(obj, name) {
              return name in obj
            }

            const deprecate = msg => msg

            module.exports = {
              exist: checkExistence,
              deprecate
            }
        """,
        'lib/reply.js': """
            const decorators = require('./decorate')

            function getDecorator(obj, name) {
              require('./decorate').deprecate('x')
              return decorators.exist(obj, name)
            }

            module.exports = getDecorator
        """,
    }, {('f:lib/reply.js:getDecorator', 'f:lib/decorate.js:checkExistence', 'call'),
        ('f:lib/reply.js:getDecorator', 'f:lib/decorate.js:deprecate', 'call')}, ()),
    # --- ronda 6 ---
    ('kotlin', 'extensión con receptor parámetro de tipo y constructor calificado con el paquete', {
        'src/main/kotlin/app/fp/Validated.kt': """
            package app.fp

            sealed class Validated<out E, out A> {
              data class Valid<A>(val value: A) : Validated<Nothing, A>()
              data class Invalid<E>(val error: E) : Validated<E, Nothing>()
            }

            fun <A> A.valid(): Validated<Nothing, A> = Validated.Valid(this)
            fun <E : Failure> E.invalid(): Validated<E, Nothing> = Validated.Invalid(this)

            open class Failure
        """,
        'src/main/kotlin/app/core/Use.kt': """
            package app.core

            import app.fp.Failure
            import app.fp.valid
            import app.fp.invalid

            class Unknown(val s: String) : Failure()
            class Source(val s: String)

            fun open(s: String): Any = if (s.isEmpty()) Unknown(s).invalid() else Source(s).valid()
            fun wrong(s: String): Any = Source(s).invalid()
            val all = listOf(app.core.Source("x"), app.fp.Validated.Valid(1))
        """,
    }, {('f:src/main/kotlin/app/core/Use.kt:open', 'f:src/main/kotlin/app/fp/Validated.kt:invalid', 'call'),
        ('f:src/main/kotlin/app/core/Use.kt:open', 'f:src/main/kotlin/app/fp/Validated.kt:valid', 'call'),
        ('m:src/main/kotlin/app/core/Use.kt', 'c:src/main/kotlin/app/core/Use.kt:Source', 'call'),
        ('m:src/main/kotlin/app/core/Use.kt', 'c:src/main/kotlin/app/fp/Validated.kt:Valid', 'call')},
        {('f:src/main/kotlin/app/core/Use.kt:wrong', 'f:src/main/kotlin/app/fp/Validated.kt:invalid', 'call')}),
    ('dart', 'llamada genérica encadenada `Caja<T>(a: x).m()`, constructor con nombre genérico y extensión sobre Iterable', {
        'pubspec.yaml': 'name: rx\n',
        'lib/src/t.dart': """
            class DoStreamTransformer<T> {
              DoStreamTransformer({Object? onCancel});
              Stream<T> bind(Stream<T> s) => s;
            }
            class Wrapper<T> {
              Wrapper.seeded(T x);
              void go() {}
            }
            class CombineLatestStream<T> {
              static CombineLatestStream<T> list<T>(Iterable<Stream<T>> s) => CombineLatestStream<T>();
              void run() {}
            }
        """,
        'lib/src/s.dart': """
            import 'dart:async';

            extension SubsExt on Iterable<StreamSubscription<void>> {
              void pauseAll() {}
            }
            extension IntsExt on Iterable<int> {
              void sumAll() {}
            }
        """,
        'lib/src/u.dart': """
            import 'dart:async';
            import 'package:rx/src/t.dart';
            import 'package:rx/src/s.dart';

            extension DoExtensions<T> on Stream<T> {
              Stream<T> doOnCancel(Object onCancel) => DoStreamTransformer<T>(onCancel: onCancel).bind(this);
              void f(T x, List<Stream<T>> streams, List<StreamSubscription<T>> subs, List<String> names) {
                final w = Wrapper<T>.seeded(x);
                w.go();
                CombineLatestStream.list<T>(streams).run();
                subs.pauseAll();
                names.sumAll();
              }
            }
        """,
    }, {('f:lib/src/u.dart:DoExtensions.doOnCancel', 'c:lib/src/t.dart:DoStreamTransformer', 'call'),
        ('f:lib/src/u.dart:DoExtensions.doOnCancel', 'f:lib/src/t.dart:DoStreamTransformer.bind', 'call'),
        ('f:lib/src/u.dart:DoExtensions.f', 'f:lib/src/t.dart:Wrapper.seeded', 'call'),
        ('f:lib/src/u.dart:DoExtensions.f', 'f:lib/src/t.dart:Wrapper.go', 'call'),
        ('f:lib/src/u.dart:DoExtensions.f', 'f:lib/src/t.dart:CombineLatestStream.list', 'call'),
        ('f:lib/src/u.dart:DoExtensions.f', 'f:lib/src/t.dart:CombineLatestStream.run', 'call'),
        ('f:lib/src/u.dart:DoExtensions.f', 'f:lib/src/s.dart:SubsExt.pauseAll', 'call')},
        {('f:lib/src/u.dart:DoExtensions.f', 'f:lib/src/s.dart:IntsExt.sumAll', 'call')}),
    ('ruby', 'delegadores de Forwardable y clase `Struct.new(…) do … end`', {
        'lib/t.rb': """
            require 'forwardable'

            module Fa
              class Builder
                def use(x); end
              end

              class Test
                extend Forwardable
                def_delegators :builder, :use, :[]
                def_delegator :builder, :use, :use_it

                def builder
                  Builder.new
                end

                Stub = Struct.new(:host, :path) do
                  def matches?(env)
                    host == env && path_ok?
                  end

                  def path_ok?
                    path.nil?
                  end
                end

                def run
                  stub = Stub.new(1, 2)
                  stub.matches?(3)
                  use_it
                end
              end

              Options = Class.new do
                def_delegators :@x, :inner
              end
            end
        """,
    }, {('c:lib/t.rb:Test', 'f:lib/t.rb:Test.use', 'contains'), ('c:lib/t.rb:Test', 'f:lib/t.rb:Test.[]', 'contains'),
        ('c:lib/t.rb:Test', 'f:lib/t.rb:Test.use_it', 'contains'), ('c:lib/t.rb:Test', 'c:lib/t.rb:Stub', 'contains'),
        ('c:lib/t.rb:Stub', 'f:lib/t.rb:Stub.host', 'contains'), ('c:lib/t.rb:Stub', 'f:lib/t.rb:Stub.path=', 'contains'),
        ('c:lib/t.rb:Stub', 'f:lib/t.rb:Stub.matches?', 'contains'),
        ('f:lib/t.rb:Stub.matches?', 'f:lib/t.rb:Stub.host', 'call'), ('f:lib/t.rb:Stub.matches?', 'f:lib/t.rb:Stub.path_ok?', 'call'),
        ('f:lib/t.rb:Stub.path_ok?', 'f:lib/t.rb:Stub.path', 'call'), ('f:lib/t.rb:Test.run', 'c:lib/t.rb:Stub', 'call'),
        ('f:lib/t.rb:Test.run', 'f:lib/t.rb:Stub.matches?', 'call'), ('f:lib/t.rb:Test.run', 'f:lib/t.rb:Test.use_it', 'call')},
        {('c:lib/t.rb:Fa', 'f:lib/t.rb:Fa.inner', 'contains')}),
    ('typescript', 'constante fabricada por una función que devuelve una función (`const debug = Debug("x")`)', {
        'tsconfig.json': '{}',
        'lib/utils/debug.ts': """
            export default function genDebugFunction(namespace: string): (...args: any[]) => void {
              function wrapped(...args: any[]): void {}
              return wrapped;
            }
            export function plain(x: string): number { return 1; }
        """,
        'lib/utils/index.ts': """
            export { default as Debug } from "./debug";
            export { plain } from "./debug";
        """,
        'lib/Data.ts': """
            import { Debug, plain } from "./utils";
            const debug = Debug("dataHandler");
            const n = plain("x");
            export default class Data {
              run() { debug("hi"); }
            }
        """,
    }, {('f:lib/Data.ts:Data.run', 'f:lib/Data.ts:debug', 'call'), ('m:lib/Data.ts', 'f:lib/Data.ts:debug', 'contains'),
        ('f:lib/Data.ts:debug', 'f:lib/utils/debug.ts:genDebugFunction', 'call')},
        {('m:lib/Data.ts', 'f:lib/Data.ts:n', 'contains'), ('m:lib/Data.ts', 'f:lib/utils/debug.ts:genDebugFunction', 'call')}),
    # --- ronda 7 ---
    ('ruby', 'ancestro de fuera del proyecto: `scope`, cadenas de ActiveRecord y receptores sin tipo no se enlazan por nombre', {
        'app/models/tag.rb': """
            class Tag < ApplicationRecord
              scope :active, -> { where(active: true) }

              def self.listed
                Tag.active.order(:tag)
              end

              def label
                tags = Tag.where(x: 1).first
                tags.mark
              end

              def mark; end
            end
        """,
        'app/models/search.rb': """
            class Search
              def order; end
            end
        """,
        'app/controllers/home_controller.rb': """
            class HomeController < ApplicationController
              def active; end

              def show
                u = User.find_by(id: 1)
                u.fetched_avatar(10)
                File.mtime("x")
                Search.new.order
              end
            end
        """,
        'app/models/user.rb': """
            class User < ApplicationRecord
              def fetched_avatar(size); end
            end
        """,
        'app/models/static_file.rb': """
            class StaticFile
              def mtime; end
            end
        """,
    }, {('f:app/controllers/home_controller.rb:HomeController.show', 'f:app/models/search.rb:Search.order', 'call')},
        {('f:app/models/tag.rb:Tag.self.listed', 'f:app/controllers/home_controller.rb:HomeController.active', 'call'),
         ('f:app/models/tag.rb:Tag.listed', 'f:app/controllers/home_controller.rb:HomeController.active', 'call'),
         ('f:app/models/tag.rb:Tag.self.listed', 'f:app/models/search.rb:Search.order', 'call'),
         ('f:app/models/tag.rb:Tag.listed', 'f:app/models/search.rb:Search.order', 'call'),
         ('f:app/models/tag.rb:Tag.label', 'f:app/models/tag.rb:Tag.mark', 'call'),
         ('f:app/controllers/home_controller.rb:HomeController.show', 'f:app/models/user.rb:User.fetched_avatar', 'call'),
         ('f:app/controllers/home_controller.rb:HomeController.show', 'f:app/models/static_file.rb:StaticFile.mtime', 'call')}),
    ('ruby', '`X = Class.new(Base)`, estrechamiento por `is_a?` y variable fijada antes de un bloque', {
        'lib/liq/errors.rb': """
            module Liq
              class Error < ::StandardError
                attr_accessor :markup_context
              end

              SyntaxError = Class.new(Error)
            end
        """,
        'lib/liq/parser.rb': """
            module Liq
              class Parser
                def parse(markup)
                  run(markup)
                rescue SyntaxError => e
                  e.markup_context = markup
                end

                def run(m); end
                def handlers; end

                def ==(other)
                  other.is_a?(self.class) && other.handlers
                end

                def merged(files)
                  conf = dup
                  files.each do |f|
                    conf = Util.merge(conf, f)
                  end
                  conf.handlers
                end
              end
            end
        """,
    }, {('f:lib/liq/parser.rb:Parser.parse', 'f:lib/liq/errors.rb:Error.markup_context=', 'call'),
        ('f:lib/liq/parser.rb:Parser.==', 'f:lib/liq/parser.rb:Parser.handlers', 'call'),
        ('f:lib/liq/parser.rb:Parser.merged', 'f:lib/liq/parser.rb:Parser.handlers', 'call')}, ()),
    ('php', '`use` de fuera tapa la clase homónima, valores de funciones y ancestros de fuera, @property y funciones del proyecto', {
        'composer.json': '{"autoload": {"psr-4": {"App\\\\": "app/"}, "files": ["app/helpers.php"]}}',
        'app/helpers.php': """
            <?php
            use App\\Models\\User;

            function user(): User
            {
                return new User();
            }
        """,
        'app/Http/Request.php': """
            <?php
            namespace App\\Http;

            class Request
            {
            }
        """,
        'app/Models/User.php': """
            <?php
            namespace App\\Models;

            class User
            {
                public function can(string $p): bool { return true; }
                public function logDescriptor(): string { return ''; }
            }
        """,
        'app/Models/Account.php': """
            <?php
            namespace App\\Models;

            use Illuminate\\Database\\Eloquent\\Model;

            /**
             * @property User $owner
             */
            class Account extends Model
            {
                public function describe(): string
                {
                    return $this->owner->logDescriptor();
                }

                public function tags(): bool
                {
                    return $this->labels->pluck('id')->contains(1);
                }
            }
        """,
        'app/Models/Shelf.php': """
            <?php
            namespace App\\Models;

            class Shelf
            {
                public function contains(int $x): bool { return true; }
            }
        """,
        'app/Api/DocsController.php': """
            <?php
            namespace App\\Api;

            use GuzzleHttp\\Psr7\\Request;

            class DocsController
            {
                public function json(): string { return ''; }

                public function show()
                {
                    $r = new Request('GET', '/');
                    user()->can('x');
                    return response()->json([]);
                }
            }
        """,
    }, {('f:app/Models/Account.php:Account.describe', 'f:app/Models/User.php:User.logDescriptor', 'call'),
        ('f:app/Api/DocsController.php:DocsController.show', 'f:app/helpers.php:user', 'call'),
        ('f:app/Api/DocsController.php:DocsController.show', 'f:app/Models/User.php:User.can', 'call')},
        {('f:app/Api/DocsController.php:DocsController.show', 'c:app/Http/Request.php:Request', 'call'),
         ('f:app/Api/DocsController.php:DocsController.show', 'f:app/Api/DocsController.php:DocsController.json', 'call'),
         ('f:app/Models/Account.php:Account.tags', 'f:app/Models/Shelf.php:Shelf.contains', 'call')}),
    ('dart', 'una parte (`part of`) ve los imports de su biblioteca, reexportaciones en cadena y nombres de `show`', {
        'pubspec.yaml': 'name: mel\n',
        'lib/mel.dart': """
            export 'src/configs/configs.dart' show AnalyzeConfig;
        """,
        'lib/src/configs/configs.dart': """
            export 'analyze.dart';
        """,
        'lib/src/configs/analyze.dart': """
            class AnalyzeConfig {
              bool get fatal => true;
            }
        """,
        'lib/src/options.dart': """
            class GlobalOptions {
              void verbose() {}
            }
        """,
        'lib/src/commands/runner.dart': """
            import '../options.dart';
            import '../configs/configs.dart';

            part 'analyze.dart';

            class Runner with _AnalyzeMixin {}
        """,
        'lib/src/commands/analyze.dart': """
            part of 'runner.dart';

            mixin _AnalyzeMixin {
              void analyze(GlobalOptions? global, AnalyzeConfig config) {
                global?.verbose();
              }
            }
        """,
    }, {('m:lib/mel.dart', 'm:lib/src/configs/analyze.dart', 'import'),
        ('f:lib/src/commands/analyze.dart:_AnalyzeMixin.analyze', 'f:lib/src/options.dart:GlobalOptions.verbose', 'call'),
        ('m:lib/src/commands/analyze.dart', 'm:lib/src/configs/analyze.dart', 'import')}, ()),
    ('python', 'descriptor de clase con `__get__` genérico y clase genérica del proyecto como anotación', {
        'app/base.py': """
            from typing import Generic, TypeVar, overload

            T = TypeVar('T')


            class Option(Generic[T]):
                @overload
                def __get__(self, obj: 'Config', type=None) -> T: ...

                @overload
                def __get__(self, obj, type=None) -> 'Option': ...

                def __get__(self, obj, type=None):
                    return self

                def validate(self, value):
                    return value


            class Required(Generic[T], Option[T]):
                pass


            class Config:
                pass


            class Wrapper:
                def __init__(self, option_type: Option[T]):
                    self.option_type = option_type

                def run(self, v):
                    return self.option_type.validate(v)
        """,
        'app/plugins.py': """
            class PluginCollection:
                def on_build(self):
                    return 1
        """,
        'app/defaults.py': """
            from app import base
            from app.plugins import PluginCollection


            class Plugins(base.Required[PluginCollection]):
                pass


            class MkConfig(base.Config):
                plugins = Plugins()


            def build(config: MkConfig):
                return config.plugins.on_build()
        """,
    }, {('f:app/defaults.py:build', 'f:app/plugins.py:PluginCollection.on_build', 'call'),
        ('f:app/base.py:Wrapper.run', 'f:app/base.py:Option.validate', 'call')}, ()),
    ('python', 'atributo inicializado a None y asignado después en otro método', {
        'app/config.py': """
            class Config:
                def validate(self):
                    return True
        """,
        'app/base.py': """
            from app.config import Config


            class Application:
                def __init__(self):
                    self.cfg = None

                def load(self):
                    self.cfg = Config()

                def run(self):
                    return self.cfg.validate()
        """,
    }, {('f:app/base.py:Application.run', 'f:app/config.py:Config.validate', 'call')}, ()),
    ('typescript', 'constante con un callback como argumento de una función del proyecto que devuelve un valor', {
        'lib/keyValueBy.ts': """
            export type Index<T> = Record<string, T>
            export function keyValueBy<T>(xs: T[], f: (x: T) => Index<T>): Index<T> { return {} }
            export function wrap(f: () => void): () => void { return f }
        """,
        'lib/opts.ts': """
            import { keyValueBy, wrap } from './keyValueBy'
            function label(x: string) { return x }
            export const optionsMap = keyValueBy(['a'], o => ({ [label(o)]: o }))
            export const handler = wrap(() => label('b'))
        """,
    }, {('m:lib/opts.ts', 'f:lib/keyValueBy.ts:keyValueBy', 'call'), ('m:lib/opts.ts', 'f:lib/opts.ts:label', 'call'),
        ('m:lib/opts.ts', 'f:lib/opts.ts:handler', 'contains')},
        {('m:lib/opts.ts', 'f:lib/opts.ts:optionsMap', 'contains')}),
    ('javascript', 'campo asignado en un método (`this.data = new Data()` en `init()`), salvo con un JSDoc `@type` de otro tipo', {
        'lib/data.js': """
            export class Data {
              getDir() { return 1; }
            }
        """,
        'lib/serve.js': """
            export class Serve {
              reload() { return 2; }
            }
        """,
        'lib/core.js': """
            import { Data } from './data.js';
            import { Serve } from './serve.js';

            export class Base {
              init() {
                if (!this.data) {
                  this.data = new Data();
                }
                /** @type {object} */
                this.serve = new Serve();
              }
            }

            export class Core extends Base {
              run() {
                this.data.getDir();
                this.serve.reload();
              }
            }
        """,
    }, {('f:lib/core.js:Core.run', 'f:lib/data.js:Data.getDir', 'call')}, {('f:lib/core.js:Core.run', 'f:lib/serve.js:Serve.reload', 'call')}),
    ('csharp', 'lambda de un método de un tipo genérico de fuera recibe su argumento de tipo', {
        'src/BaseEntity.cs': """
            namespace App
            {
                public abstract class BaseEntity
                {
                    public int Id { get; set; }
                }
            }
        """,
        'src/CatalogItem.cs': """
            namespace App
            {
                public class CatalogItem : BaseEntity
                {
                    public string Name { get; set; }
                }
            }
        """,
        'src/Config.cs': """
            using Microsoft.EntityFrameworkCore.Metadata.Builders;

            namespace App
            {
                public class CatalogItemConfiguration
                {
                    public void Configure(EntityTypeBuilder<CatalogItem> builder)
                    {
                        builder.Property(ci => ci.Id);
                    }
                }
            }
        """,
    }, {('m:src/Config.cs', 'm:src/BaseEntity.cs', 'import')}, ()),
]


@pytest.mark.parametrize('lang,construct,files,present,absent', CASES, ids=[f'{c[0]}: {c[1]}' for c in CASES])
def test_language_feature(tmp_path, lang, construct, files, present, absent):
    root = write_repo(tmp_path / 'repo', files)
    edges = edge_set(analyze(root, 'langfeatures', git=False))
    assert set(present) <= edges, sorted(set(present) - edges)
    assert not set(absent) & edges, sorted(set(absent) & edges)


def test_definition_lines_skip_annotations_and_dart_bodies_are_in_range(tmp_path):
    """Ronda 5: la línea de una definición es la de su declaración, no la de las anotaciones o atributos que la preceden
    (como el `def` de Python tras sus decoradores), y el rango de un método de Dart incluye su cuerpo. Ronda 6: esa línea
    va en `decl` y el nodo empieza en sus anotaciones (`line`), para que su rango las incluya."""
    root = write_repo(tmp_path / 'repo', {
        'src/main/kotlin/a/Q.kt': """
            package a

            class Q {
                @Deprecated(
                    "x",
                    ReplaceWith("y"),
                    level = DeprecationLevel.ERROR
                )
                fun old(): Int = 1
            }
        """,
        'src/Ext.cs': """
            namespace App;

            public static class Ext
            {
                [System.Obsolete(
                    "x",
                    false)]
                [System.Diagnostics.DebuggerStepThrough]
                public static int Add(this int a) => a;
            }
        """,
        'lib/h.dart': """
            class H {
              void heapify() {
                var c = 1;
                _down(c);
              }

              void _down(int c) {}
            }
        """,
    })
    nodes = {n['key']: n for n in analyze(root, 'langfeatures', git=False)['nodes']}
    # el nodo empieza en sus anotaciones (los puentes leen `@Query(…)` dentro de su rango) y `decl` es la declaración
    assert (nodes['f:src/main/kotlin/a/Q.kt:Q.old']['line'], nodes['f:src/main/kotlin/a/Q.kt:Q.old']['decl']) == (4, 9)
    assert nodes['f:src/Ext.cs:Ext.Add']['decl'] == 9 and nodes['f:src/Ext.cs:Ext.Add']['line'] < 9
    heapify = nodes['f:lib/h.dart:H.heapify']
    assert (heapify['line'], heapify['end']) == (2, 5)


def test_kotlin_grammar_fixups_keep_positions():
    from cortex_graph.langs import kotlin_fixups, parser_for
    src = (b'class A(val where: Int?) {\n    fun f() {\n        a()\n        where?.let { b() }\n    }\n'
           b'    var d: Int?\n        @Synchronized get() = 1\n        @Synchronized set(v) { }\n'
           b'    fun <T> g(x: T): Int\n        where T : Any = 1\n}\n')
    fixed = kotlin_fixups(src)
    assert len(fixed) == len(src) and b'where?.let' in fixed and b'where T : Any' in fixed
    assert parser_for('kotlin').parse(src).root_node.has_error
    assert not parser_for('kotlin').parse(fixed).root_node.has_error
