# Cobertura de construcciones por lenguaje

Qué construcciones de llamada, definición e importación resuelve el grafo de Córtex en cada lenguaje, y qué cambió en la
ronda 7 de ajuste. Cada fila marcada como resuelta tiene un caso sintético en
[`analyzer/tests/test_langfeatures.py`](../analyzer/tests/test_langfeatures.py) (tabla `CASES`, identificado por
«lenguaje: construcción») o en el archivo de pruebas que se indica.

Leyenda: ✓ resuelto · ◐ parcial · ✗ no resuelto. «Antes» es el estado al terminar la ronda 6, tal como aparecía en los
falsos negativos y positivos de los 12 repos de la ronda 7 (mkdocs, lobsters, bookstack, eshoponweb, melos,
npm-check-updates…); «después», tras la ronda 7. Las filas sin cambio se comprobaron con el caso sintético actual (los
cambios de las rondas 2 a 6 están en el historial de este archivo y en [`results/CONTROL.md`](results/CONTROL.md)).

## Python (scip-python)

| construcción | antes → después | caso |
|---|---|---|
| llamada desde código de módulo | ✓ → ✓ | llamada a nivel de módulo |
| cadena `A.make().run()` con tipo de retorno | ✓ → ✓ | cadena con tipo de retorno |
| herencia, `super().x()`, `self.x()` heredado | ✓ → ✓ | herencia y super() |
| decoradores y `from pkg import *` con `__all__` | ✓ → ✓ | decorador e import * con __all__ |
| lambdas y comprensiones (se atribuyen a la función que las contiene) | ✓ → ✓ | lambda y comprensión… |
| `async def` / `await` | ✓ → ✓ | async/await |
| propiedad leída como atributo (`c.size`) | ✓ → ✓ | propiedad leída como atributo |
| `with X() as v` (tipo de `__enter__`/`__aenter__`) | ✓ → ✓ | with … as |
| contenedor copiado (`list(reversed(x))`, `sorted`, `tuple`, `set`, `iter`) | ✓ → ✓ | contenedor copiado |
| unión con un solo tipo del proyecto (`URL \| str`) | ✓ → ✓ | unión con un solo tipo del proyecto |
| valor recibido por `yield` en un generador (`response = yield request`) | ✗ → ✗ | — |
| funciones y clases anidadas como nodos propios (`def wrapper` dentro de un decorador, `class Meta` dentro de un modelo) | ✓ → ✓ | funciones y clases anidadas, definiciones condicionales… |
| definiciones condicionales (`if sys.platform…: def f`, `try: … except: def f`) | ✓ → ✓ | funciones y clases anidadas, definiciones condicionales… |
| alias local de una clase (`_Text = Text`), `cls(…)` en un `classmethod` | ✓ → ✓ | funciones y clases anidadas, definiciones condicionales… |
| `a if c else b` y `a or b` como tipo; alias de tipo de módulo (`TextType = Union[str, "Text"]`), también importado | ✓ → ✓ | funciones y clases anidadas, definiciones condicionales… |
| anotaciones evaluadas en el ámbito del módulo aunque un parámetro tape el nombre (`box: Optional[box.Box]`) | ✓ → ✓ | `test_pyast.py` |
| iterar o indexar una clase propia (`__iter__`, `__getitem__` con tipo de retorno) | ✓ → ✓ | funciones y clases anidadas, definiciones condicionales… |
| estrechamiento por `if isinstance(x, T):` (también hacia tipos de fuera del proyecto) | ✓ → ✓ | funciones y clases anidadas, definiciones condicionales… |
| `from .paquete import x` relativo: dependencia del `__init__.py` del paquete que reexporta (no en `from . import modulo`) | ✓ → ✓ | import relativo de un paquete que reexporta |
| base genérica `class Choice(ParamType[str])` (herencia a través de `Base[T]`) | ✓ → ✓ | base genérica `class Choice(ParamType[str])` |
| atributo de clase que es un descriptor (`plugins = c.Plugins(…)`, clase con `__get__`): tipo que devuelve `__get__`, con la variable de tipo fijada por la herencia (`class Plugins(OptionallyRequired[PluginCollection])`) | ✗ → ✓ | descriptor de clase con `__get__` genérico… |
| clase genérica del proyecto con sus argumentos como anotación (`option_type: BaseConfigOption[T]`) | ✗ → ✓ | descriptor de clase con `__get__` genérico… |
| atributo inicializado a `None` y asignado en otro método (`self.cfg = None` … `self.cfg = Config(…)`) | ✗ → ✓ | atributo inicializado a None… |

## Go (scip-go)

| construcción | antes → después | caso |
|---|---|---|
| métodos y receptores tipados (`New().Save()`) | ✓ → ✓ | métodos y receptores tipados |
| funciones genéricas (`Map[T any]`) y literales de función | ✓ → ✓ | genéricos e interfaz |
| constante, variable o función de otro archivo del paquete usada como valor (`Run: emptyRun`, `x := Marker`) | ✓ → ✓ | constante y función como valor… |
| parámetro de un literal de función que tapa un nombre del paquete | ✓ → ✓ | parámetro de un literal de función… |
| restricciones de compilación (`//go:build`, sufijos `_linux`) | ✓ → ✓ | `test_langs_extra.py` |
| llamada a método de interfaz (despacho a implementaciones) | ◐ → ◐ | se enlaza al método de interfaz; el benchmark no cuenta como fallo la implementación |

## TypeScript (scip-typescript)

| construcción | antes → después | caso |
|---|---|---|
| `namespace X { … }` (miembros `X.f`, también importado y anidado) | ✓ → ✓ | namespace con miembros |
| función definida con un ternario (`cond ? (a) => … : (b) => …`) | ✓ → ✓ | namespace con miembros |
| alias de función (`const s = ZodString.create`, `export { s as string }`) | ✓ → ✓ | alias de función y cadena… |
| cadena a nivel de módulo (`z.string().optional()`, `schema.parse()`) | ✓ → ✓ | alias de función y cadena… |
| campo alias de un método (`min = this.gte`, `static create = crear`) | ✓ → ✓ | campo alias de un método |
| decoradores, `async`/`await`, desestructuración de parámetros | ✓ → ✓ | decorador, async y desestructuración |
| componentes JSX y re-exportaciones (`export { X } from`, `export *`) | ✓ → ✓ | componente JSX y re-export |
| herencia e interfaces (`this.m()` heredado) | ✓ → ✓ | herencia e interfaz |
| tipos genéricos de las clases propias (`this._def.getter()` con `Def` genérico) | ✗ → ✗ | — |
| desestructurar un retorno con tipo objeto literal (`const { status } = f()`) | ✗ → ✗ | — |
| función o método de un objeto literal tipado por contexto (parámetro, propiedad de otro literal, variable anotada) | ✓ → ✓ | objeto literal tipado por contexto, lectura de propiedad… |
| lectura de una propiedad de un receptor tipado (`args.constraints`) como dependencia | ✓ → ✓ | objeto literal tipado por contexto, lectura de propiedad… |
| retorno genérico fijado por el argumento (`get<T>(c: { new (…): T }): T`, `id<T>(x: T): T`) | ✓ → ✓ | objeto literal tipado por contexto, lectura de propiedad… |
| clausura de `forEach`/`map`/`filter`/… sobre `T[]`, `Array<T>`, `Set<T>` | ✓ → ✓ | objeto literal tipado por contexto, lectura de propiedad… |
| campo con tipo función sin valor (`validateIf?: (o) => boolean`) como método; unión con `string` no es función | ✓ → ✓ | objeto literal tipado por contexto, lectura de propiedad… |
| `export = X` (por defecto y `import X = require`) y `export { default as X } from './x'` | ✓ → ✓ | export = X, export { default as X }, parámetro this… |
| parámetro `this: T` de una función (`function f(this: Hexo) { this.call() }`) | ✓ → ✓ | export = X, export { default as X }, parámetro this… |
| propiedad `p: typeof f` de una interfaz como método (`this.date(x)` con `date: typeof dateHelper`) | ✓ → ✓ | export = X, export { default as X }, parámetro this… |
| tipo objeto en línea en un campo (`_index: { post_tag: Index }`) | ✓ → ✓ | export = X, export { default as X }, parámetro this… |
| claves de un objeto literal tipado por contexto (`render({ path })`) y desestructuración (`const { i18n } = theme`) como dependencia; no con uniones ni tipos mapeados (`Partial<T>`) | ✓ → ✓ | claves de un objeto literal tipado y desestructuración… |
| `require('./m')` en un archivo `.ts` como dependencia | ✓ → ✓ | `test_bench.py` (la regla de medida) |
| unión de tipos del proyecto (`type State = ObjState \| MapState`): el miembro se busca en cada uno (llamadas y dependencias) | ✓ → ✓ | unión de tipos del proyecto, constante importada… |
| constante importada a través de un barril (`export * from './env'`): dependencia del módulo que la declara | ✓ → ✓ | unión de tipos del proyecto, constante importada… |
| alias de un espacio de nombres de la biblioteca estándar (`const O = Object; export const getProto = O.getPrototypeOf`) | ✓ → ✓ | unión de tipos del proyecto, constante importada… |
| constante fabricada por una función del proyecto que devuelve una función (`const debug = Debug("x")`, con retorno `(...a) => void` o un `return` de una función): nodo propio, y la llamada que la fabrica es suya | ✓ → ✓ | constante fabricada por una función que devuelve una función… |
| constante con un callback como argumento de una función del proyecto que declara un retorno que no es una función (`const m = keyValueBy(xs, x => …)` con `: Index<R>`): es un valor y sus llamadas son del módulo (antes, nodo función, como `memo(…)`) | ✗ → ✓ | constante con un callback como argumento… |
| campo o variable anotados con un alias de un tipo función (`errorHandler: ErrorHandler`, con `type ErrorHandler = (…) => …`) como función | ✗ → ✗ | — |

## JavaScript (scip-typescript con tsconfig inferido)

| construcción | antes → después | caso |
|---|---|---|
| `exports.f = function`, `Clase.prototype.m = function`, `obj.m = () => …` (nodos con nombre) | ✓ → ✓ | exports.f, Clase.prototype.m… |
| `module.exports = X`: `require('./m')` es `X` | ✓ → ✓ | exports.f, Clase.prototype.m… |
| `const f = require('./m').f` (alias que remite a la función) | ✓ → ✓ | exports.f, Clase.prototype.m… |
| `this.m()` dentro de un método de prototipo | ✓ → ✓ | exports.f, Clase.prototype.m… |
| módulos ES, clases, JSX | ✓ → ✓ | `test_tsjs.py` |
| llamar a un valor importado que no es una función (`export var test = QUnit.test`): referencia al módulo, no llamada | ✓ → ✓ | llamada a un valor importado que no es una función |
| mixin `Object.assign(Clase.prototype, { m() {…}, n: function () {…} })` (métodos con nombre, `this` dentro) | ✓ → ✓ | mixin con Object.assign… |
| funciones declaradas dentro de una fábrica UMD/IIFE (`(function (root, factory) {…})(this, function () { function f… })`) | ✗ → ✗ | scip-typescript las deja como `local` |
| cadena `var color = (exports.color = function…)` y `exports = module.exports = X` | ✓ → ✓ | cadena exports, alias de require… |
| miembro del objeto exportado (`var color = Base.color` con `exports.color` y `module.exports = Base`) | ✓ → ✓ | cadena exports, alias de require… |
| alias de `require` de una función con nombre: la llamada va a la original (`require('./errors').createError`); nodo propio solo si la exportación no tiene nombre (`module.exports = function…`) | ✓ → ✓ | cadena exports, alias de require… |
| alias de una función de la biblioteca estándar (`var abs = Math.abs`, `Object.prototype.toString`) | ✓ → ✓ | cadena exports, alias de require… |
| retorno inferido de los `return` (`static create() { return new Pool(); }`) y `let x; … x = Pool.create()` | ✓ → ✓ | cadena exports, alias de require… |
| parámetros con tipo JSDoc (`@param {Pool} pool`) | ✗ → ✗ | — |
| miembros de un objeto exportado por defecto (`export default { isArray, own: hasOwn }`; `utils.isArray(x)`) | ✓ → ✓ | miembros de un objeto exportado por defecto… |
| clave renombrada de `module.exports = { exist: checkExistence }` y llamada sobre `require('./m')` en línea (`require('./errors').deprecate(…)`) | ✓ → ✓ | clave renombrada de module.exports… |
| campo asignado en cualquier método (`this.data = new Data()` en `init()`, también de una clase base), si todas las asignaciones crean la misma clase y el constructor no lo declara; un JSDoc `@type` de otro tipo (`/** @type {object} */`) manda, como en TypeScript | ✗ → ✓ | campo asignado en un método… |

## Ruby (scip-ruby)

| construcción | antes → después | caso |
|---|---|---|
| `include`/`extend`/`prepend` (métodos del módulo como base) | ✓ → ✓ | mixin (include), alias_method… |
| `alias nuevo viejo` / `alias_method :nuevo, :viejo` | ✓ → ✓ | mixin (include), alias_method… |
| `a[k] = v` y `a.b = v` no declaran `a` como variable local | ✓ → ✓ | mixin (include), alias_method… |
| `attr_accessor`/`attr_reader`/`attr_writer` | ✓ → ✓ | mixin (include), alias_method… |
| `def self.x` junto a `def x` (nodos distintos; llamada al del mismo nivel, también `self.class.x`) | ✓ → ✓ | def self.x junto a def x… |
| métodos de operador y de escritura (`<=>`, `[]`, `body=`) | ✓ → ✓ | def self.x junto a def x… |
| llamadas en valores por defecto (`def f(base = settings)`) | ✓ → ✓ | def self.x junto a def x… |
| `autoload :X, 'ruta'` como dependencia | ✓ → ✓ | autoload y ::Constante raíz |
| `::Constante` (raíz) no se confunde con una clase anidada homónima | ✓ → ✓ | autoload y ::Constante raíz |
| `X.new` de una clase anidada, dentro de bloques | ✓ → ✓ | bloque y X.new de clase anidada |
| constantes resueltas como Ruby: anidamiento léxico (`class Thor; class Option < Argument`), raíz y nombre único | ✓ → ✓ | superclase anidada, receptor tipado… |
| receptor tipado por sintaxis: `X.new`, `x = X.new; x.m`, `@x = X.new`, `self.class.new`, `dup`, constante (`Thor::Options.split`, heredado) | ✓ → ✓ | superclase anidada, receptor tipado… |
| búsqueda por nivel (instancia / clase) en la clase, sus módulos y superclases | ✓ → ✓ | superclase anidada, receptor tipado… |
| `self[k]` / `self[k] = v` (métodos `[]` y `[]=`), llamadas como valor de un hash (`{a: metodo}`) | ✓ → ✓ | superclase anidada, receptor tipado… |
| módulos que añade un gancho `self.included` (`base.extend(ClassMethods)`, `base.send(:include, M)`) | ✓ → ✓ | gancho self.included (base.extend), Struct.new… |
| accesores de `Struct.new(:a)` / `Data.define(:a)`: el método homónimo del proyecto deja de ser único | ✓ → ✓ | gancho self.included (base.extend), Struct.new… |
| clases homónimas anidadas en el mismo archivo (`First::Checker`, `Second::Checker`) | ✓ → ✓ | gancho self.included (base.extend), Struct.new… |
| constantes nombradas (clases, módulos, `NOMBRE = …`) como dependencia entre archivos | ✓ → ✓ | superclase anidada, receptor tipado… |
| variable de `rescue X => e` con el tipo `X` (externo: sin enlace por nombre único) | ✓ → ✓ | variable de rescue y constantes del núcleo de Ruby |
| constantes del núcleo y la biblioteca estándar (`File`, `Hash`, `Logger`…) no se resuelven por nombre único a una clase anidada del proyecto | ✓ → ✓ | variable de rescue y constantes del núcleo de Ruby |
| delegadores de `Forwardable` en el cuerpo de la clase (`def_delegators :obj, :a, :b`, `def_delegator :obj, :m, :alias`) como métodos | ✓ → ✓ | delegadores de Forwardable y clase `Struct.new(…) do … end` |
| `Stub = Struct.new(:a, :b) do … end`: clase con un accesor por miembro y los métodos del bloque (`self` dentro de ellos es la clase; el bloque no abre ámbito de constantes) | ✓ → ✓ | delegadores de Forwardable y clase `Struct.new(…) do … end` |
| clase con un ancestro de fuera del proyecto (`class Tag < ApplicationRecord`): un método que no está en sus ancestros del proyecto (`Tag.active` de un `scope`, `Category.where(…)`, `comments` de un `has_many`) no se enlaza por nombre a otra clase, y lo que devuelve no tiene tipo del proyecto | ✗ → ✓ | ancestro de fuera del proyecto: `scope`, cadenas de ActiveRecord… |
| receptor sin tipo (`u = User.find_by(…)`, `File.mtime(x)`): ya no se enlaza por el nombre único del método (en los 7 repos de Ruby, 12 aciertos frente a 47 errores) | ◐ → ✗ (a propósito) | ancestro de fuera del proyecto: `scope`, cadenas de ActiveRecord… |

## Java (scip-java)

| construcción | antes → después | caso |
|---|---|---|
| llamadas encadenadas con tipo de retorno | ✓ → ✓ | llamada encadenada con tipo de retorno |
| lambdas, referencias a método (`Util::twice`), `import static` | ✓ → ✓ | lambda, referencia a método e import estático |
| clase anónima: sus métodos ven las variables del método que la crea | ✓ → ✓ | clase anónima y genérico new X<>() |
| `new X<>()` / `new X<T>() { … }` como instanciación | ✓ → ✓ | clase anónima y genérico new X<>() |

## Kotlin (scip-java + semanticdb-kotlinc)

| construcción | antes → después | caso |
|---|---|---|
| lambda final (`run { … }`) y funciones de extensión | ✓ → ✓ | lambda final y función de extensión |
| `data class`, `companion object`, `object` | ✓ → ✓ | data class, companion y object |
| `Tipo(…)` sobre una interfaz u `object`, o sin constructor que encaje: `operator fun invoke` del companion | ✓ → ✓ | invoke de companion, constructor SAM… |
| valor invocado con `operator fun invoke` (local, propiedad del receptor, `f(a)(b)`) | ✓ → ✓ | invoke de companion, constructor SAM… |
| `fun interface X : (A) -> B` y lambdas que devuelven lambdas (`Filter { next -> { request -> … } }`): tipo de sus parámetros | ✓ → ✓ | invoke de companion, constructor SAM… |
| `typealias` (nodo propio y resolución a su tipo) | ✓ → ✓ | invoke de companion, constructor SAM… |
| acumulador de `fold(inicial) { acc, x -> … }` y retorno de un valor de tipo función | ✓ → ✓ | invoke de companion, constructor SAM… |
| extensión miembro visible solo dentro de su clase | ✓ → ✓ | invoke de companion, constructor SAM… |
| `object` anidado invocado como `Dueño.Anidado(…)`: su `operator fun invoke` | ✓ → ✓ | objeto anidado invocable, override… |
| `override` sin valores por defecto acepta llamadas con menos argumentos (hereda los del método redefinido) | ✓ → ✓ | objeto anidado invocable, override… |
| constante importada del companion (`import …Status.Companion.BAD_REQUEST`) y propiedad en mayúsculas invocada | ✓ → ✓ | objeto anidado invocable, override… |
| función de nivel superior de otro paquete sin importar no tapa una clase | ✓ → ✓ | objeto anidado invocable, override… |
| propiedad de tipo función (`compress(x).apply()`) y lambda pasada a un constructor primario | ✓ → ✓ | objeto anidado invocable, override… |
| parámetros de lambda inferidos de un genérico del contexto (`LensSet { …, target -> }`) | ✗ → ✗ | — |
| propiedad de extensión (`val ASTNode.prevLeaf: ASTNode?`), también sobre tipos externos y como dependencia | ✓ → ✓ | propiedad de extensión, extensión importada… |
| una extensión solo se aplica si es visible (importada o del mismo paquete): un `import` externo homónimo la tapa | ✓ → ✓ | propiedad de extensión, extensión importada… |
| receptor de tipo desconocido (retorno de una API externa): la extensión del proyecto visible, única con ese nombre y aridad | ✓ → ✓ | propiedad de extensión, extensión importada… |
| propiedad del receptor implícito externo (`text.matches(…)` dentro de `fun ASTNode.f()`) no se enlaza por nombre | ✓ → ✓ | propiedad de extensión, extensión importada… |
| propiedad de nivel superior importada (`import …INDENT_SIZE_PROPERTY`) como dependencia | ✓ → ✓ | propiedad de extensión, extensión importada… |
| `where` (palabra clave suave) usado como variable al principio de una sentencia y anotaciones de un accesor (`@Synchronized set(v)`): la gramática rompía el resto del archivo | ✓ → ✓ | `where` como variable, anotación de un accesor… y `test_kotlin_grammar_fixups_keep_positions` |
| la extensión que admite los argumentos antes que un miembro que no (`append("a", x, "b")` con `fun QueryBuilder.append(vararg)`) | ✓ → ✓ | `where` como variable, anotación de un accesor… |
| propiedad de nivel superior importada con `*` o de otro paquete (`currentDialect.dataTypeProvider`) como receptor tipado | ✓ → ✓ | `where` como variable, anotación de un accesor… |
| lectura de una propiedad de nivel superior de otro archivo (`exposedLogger.error(…)`) como dependencia | ✓ → ✓ | `buildString { append() }`, extensión miembro… |
| `buildString { append(x) }` (receptor `StringBuilder` externo): no se enlaza a una extensión homónima de otro tipo | ✓ → ✓ | `buildString { append() }`, extensión miembro… |
| extensión miembro usada donde su clase es receptor implícito (`queryBuilder { cols.appendTo(…) }`, subclases) | ✓ → ✓ | `buildString { append() }`, extensión miembro… |
| `val dialect by lazy { … }`: tipo de la última expresión de la lambda | ✓ → ✓ | `buildString { append() }`, extensión miembro… |
| línea de una definición: la de su declaración, no la de un bloque de anotaciones (`@Deprecated(…)` en varias líneas) | ✓ → ✓ | `test_definition_lines_skip_annotations_and_dart_bodies_are_in_range` |
| llamada infija (`CONTENT_TYPE of x`, también heredada de una interfaz) como dependencia | ✓ → ✓ | llamada infija heredada… |
| extensión con receptor parámetro de tipo (`fun <A> A.valid()`, `fun <E : Base> E.invalid()`, cotas en `where`): se aplica a cualquier receptor que cumpla las cotas, detrás de una extensión de receptor concreto | ✓ → ✓ | extensión con receptor parámetro de tipo y constructor calificado… |
| constructor calificado con el paquete (`com.app.decoder.IntDecoder()`) | ✓ → ✓ | extensión con receptor parámetro de tipo y constructor calificado… |
| extensión declarada en un `companion object` e importada (`import …Loader.Companion.toLoader`) | ✗ → ✗ | — |
| propiedad genérica sustituida por el argumento del tipo (`errors.list` con `errors: NonEmptyList<ConfigFailure>` y `val list: List<A>`) | ✗ → ✗ | — |

## Rust (rust-analyzer)

| construcción | antes → después | caso |
|---|---|---|
| método de rasgo sobre un genérico acotado (`F: Pred`, cotas en `where`, varias cotas) | ✓ → ✓ | método de rasgo sobre un genérico acotado… |
| campo de tipo genérico del struct (`self.f.pair()`, `self.0.x()`), cotas del `impl` que lo usa | ✓ → ✓ | método de rasgo sobre un genérico acotado… |
| desestructurar un struct (`let Self { iter, f } = self`) | ✓ → ✓ | método de rasgo sobre un genérico acotado… |
| alias de tipo `type X<I> = Y<I>` (nodo propio y resolución al tipo de la derecha) | ✓ → ✓ | alias de tipo, Self { … } y función anidada |
| ítems dentro de una función (`fn`, `struct`, `impl` locales) | ✓ → ✓ | alias de tipo, Self { … } y función anidada |
| `Self { … }` y `Tipo { … }` como instanciación; una variante de enum no instancia el enum | ✓ → ✓ | alias de tipo, Self { … } y función anidada |
| supertraits (`trait A: B`) | ✓ → ✓ | supertrait y métodos de la biblioteca estándar… |
| `impl Trait for X`, métodos por defecto, llamadas dentro de macros | ✓ → ✓ | impl Trait for X, método por defecto y macros |
| métodos de la biblioteca estándar (`max_by`, `count`…) no se adivinan por nombre | ✓ → ✓ | supertrait y métodos de la biblioteca estándar… |
| rasgos con implementación general (`impl<T: Iterator> Itertools for T`) | ✗ → ✗ | — |
| parámetro de una clausura tipado por la cota `Fn` del método del proyecto (`F: FnMut(&DirEntry) -> bool`, `impl Fn(&T)`) | ✓ → ✓ | parámetro de clausura por la cota Fn… |
| campo genérico con argumento concreto en el `impl` (`impl<P> … for Filter<IntoIter, P>`: `self.it` es `IntoIter`) | ✓ → ✓ | parámetro de clausura por la cota Fn… |
| desestructurar una tupla literal (`let (a, b) = (&xs[0], &xs[1])`) | ✓ → ✓ | parámetro de clausura por la cota Fn… |
| ítems gemelos bajo `#[cfg]`: el nodo es el activo en Linux (`#[cfg(not(windows))]`) | ✓ → ✓ | parámetro de clausura por la cota Fn… |
| `use super::x` dentro de un `mod tests { }` en línea: `super` es el módulo del archivo | ✓ → ✓ | `use super::x` dentro de un `mod tests` en línea… |

## Dart (scip-dart)

| construcción | antes → después | caso |
|---|---|---|
| lista de inicialización del constructor (`: _x = Scanner(s)`) | ✓ → ✓ | lista de inicialización, función local… |
| delegación `: super._(…)` / `: this._(…)` a otro constructor con nombre | ✓ → ✓ | super._(…) y this._(…) en la inicialización |
| funciones locales (`int inner(x) {…}` dentro de un método) | ✓ → ✓ | lista de inicialización, función local… |
| operadores (`operator ==`, `[]`, `[]=`) | ✓ → ✓ | lista de inicialización, función local… |
| `typedef` | ✓ → ✓ | lista de inicialización, función local… |
| `mixin`, `extension`, cascadas `..m()` | ✓ → ✓ | mixin, extensión y cascada |
| variable de nivel superior con tipo (`final Context context = …;`) | ✓ → ✓ | variable de nivel superior tipada… |
| tipo con prefijo de import (`p.Context`), también reexportado (`export 'src/context.dart'`), y su dependencia | ✓ → ✓ | variable de nivel superior tipada… |
| parámetros de una función anónima pasada a un parámetro con tipo función (`responseHandler: (response) {…}`) | ✗ → ✗ | — |
| instancia de una clase genérica `Caja<T>(x)` (la gramática la lee como comparaciones) | ✓ → ✓ | instancia de una clase genérica `Caja<T>(x)` |
| rango (y hash) de un método o función: incluye su cuerpo, hermano de la firma en el árbol | ✓ → ✓ | `test_definition_lines_skip_annotations_and_dart_bodies_are_in_range` |
| llamada genérica con argumentos con nombre o encadenada (`Caja<T>(a: x).bind(this)`) y miembro estático genérico (`Clase.list<T>(xs)`) | ✓ → ✓ | llamada genérica encadenada `Caja<T>(a: x).m()`… |
| constructor con nombre de una clase genérica (`_Wrapper<T>.seeded(x)`), también como valor de una variable | ✓ → ✓ | llamada genérica encadenada `Caja<T>(a: x).m()`… |
| extensión sobre un supertipo de la SDK (`extension … on Iterable<StreamSubscription<void>>` sobre un `List<StreamSubscription<T>>`), con argumentos de tipo compatibles | ✓ → ✓ | llamada genérica encadenada `Caja<T>(a: x).m()`… |
| una parte (`part of 'runner.dart'`) ve los imports y prefijos de su biblioteca y las otras partes | ✗ → ✓ | una parte (`part of`) ve los imports de su biblioteca… |
| reexportaciones en cadena de una biblioteca importada (`export 'analyze.dart'` dentro del barril), con sus filtros `show` | ✗ → ✓ | una parte (`part of`) ve los imports de su biblioteca… |
| nombres de `show` de un `import`/`export` como dependencia del archivo que los define, aunque llegue por un barril | ✗ → ✓ | una parte (`part of`) ve los imports de su biblioteca… |

## PHP (scip-php)

| construcción | antes → después | caso |
|---|---|---|
| tipos PHPDoc (`@var` en propiedades, `@param`, `@return`) | ✓ → ✓ | tipo de una propiedad en PHPDoc |
| traits, llamadas estáticas, `new` | ✓ → ✓ | trait, llamada estática y new |
| variables sin tipo declarado: por asignación o por nombre único | ◐ → ◐ | — |
| `@method` en el PHPDoc de la clase (nodo y tipo de retorno) | ✓ → ✓ | @method del PHPDoc, atributo #[X(…)]… |
| `#[Atributo(…)]` instancia la clase | ✓ → ✓ | @method del PHPDoc, atributo #[X(…)]… |
| unión `SplFileObject\|Stream` con una sola clase del proyecto | ✓ → ✓ | @method del PHPDoc, atributo #[X(…)]… |
| `use Exception;` global y `$f()` (nunca una función con nombre) | ✓ → ✓ | @method del PHPDoc, atributo #[X(…)]… |
| `use GuzzleHttp\Psr7\Request;` (de fuera) tapa la clase `Request` del proyecto en ese archivo | ✗ → ✓ | `use` de fuera tapa la clase homónima… |
| valor de una función de PHP o de una dependencia (`response()->json()`, `session()->forget()`), de un miembro que no está en los ancestros del proyecto de una clase con un ancestro de fuera (`$this->provider` de `StatefulGuard`, `$this->roles->pluck()` de Eloquent): no se enlaza por nombre único | ✗ → ✓ | `use` de fuera tapa la clase homónima… |
| `@property User $user` del PHPDoc de la clase (también `-read`/`-write`) | ✗ → ✓ | `use` de fuera tapa la clase homónima… |
| función del proyecto como receptor de una cadena (`user()->can(…)` con `function user(): User`) | ✗ → ✓ | `use` de fuera tapa la clase homónima… |

## C# (scip-dotnet)

| construcción | antes → después | caso |
|---|---|---|
| cabecera partida por `#if … #else … #endif` (se conserva la primera rama) | ✓ → ✓ | cabecera partida por #if/#else |
| atributos con argumentos (`[Formato("x")]` instancia `FormatoAttribute`) | ✓ → ✓ | clase parcial, método de extensión y atributo |
| clases parciales y métodos de extensión | ✓ → ✓ | clase parcial, método de extensión y atributo |
| `#if` sobre símbolos del marco de destino evaluado para el .NET actual (fuera los polyfills de `#if !NET`) | ✓ → ✓ | #if del marco de destino, delegado… |
| `delegate` como tipo; `ref partial struct` | ✓ → ✓ | #if del marco de destino, delegado… |
| `T` de la base genérica en los métodos de la derivada; `string[i]` es `char` (y sus extensiones) | ✓ → ✓ | #if del marco de destino, delegado… |
| `#if` en la primera línea tras la marca BOM (polyfills `#if !NET5_0_OR_GREATER`) | ✓ → ✓ | polyfill bajo #if !NET5_0_OR_GREATER con marca BOM al inicio |
| referencia a una clase parcial (`ResiliencePipeline` en varios archivos): dependencia de una de sus partes | ✓ → ✓ | clase parcial como tipo, miembro heredado… |
| campo o propiedad heredados o de otra parte de la clase parcial, sin receptor (`Name = …`, `Component.Run()`) como dependencia | ✓ → ✓ | clase parcial como tipo, miembro heredado… |
| clave de un inicializador `new X { Clave = … }` y grupo de métodos `Func<double> f = Util.Next` como dependencia | ✓ → ✓ | clase parcial como tipo, miembro heredado… |
| línea de una definición sin sus atributos (`[UnconditionalSuppressMessage(…)]` en varias líneas) | ✓ → ✓ | `test_definition_lines_skip_annotations_and_dart_bodies_are_in_range` |
| parámetro de una lambda pasada a un método de un tipo genérico de fuera con un argumento de tipo del proyecto (`builder.Property(ci => ci.Id)` con `EntityTypeBuilder<CatalogItem>`) | ✗ → ✓ | lambda de un método de un tipo genérico de fuera… |

## Lenguajes sin referencia SCIP

Sin indexador SCIP que se pueda ejecutar con las reglas del benchmark (ver «Lenguajes que no se miden» en el
[README](README.md)); se comprueba con casos sintéticos.

| lenguaje | construcción | estado | caso |
|---|---|---|---|
| Swift | clases, métodos, funciones libres, `Clase()` | ✓ | clase, método y llamada entre archivos |
| Swift | `extension` y conformidad a protocolo | ✓ | extensión y protocolo |
| Swift | receptor tipado por inferencia (`let e = Engine(); e.run()`) | ✗ (solo por nombre único de más de 3 letras) | — |
| C | funciones y `#include` | ✓ | función y #include |
| C++ | `#include`, clases y espacios de nombres | ◐ (receptores sin inferencia) | clase, método y espacio de nombres |
| Scala | `object`, clases, llamada `Objeto.f()` | ✓ | objeto, clase y llamada |
| Elixir | módulos, `alias`, llamadas calificadas y `defp` | ✓ | módulos, alias y llamada calificada |
| Lua | `require` | ✓ | require y función de tabla |

## Reglas del benchmark asociadas

Algunas filas solo se pueden medir con una regla del benchmark, decidida por la sintaxis o por los datos SCIP y
documentada en el [README](README.md#normalización-por-indexador): módulos de imports relativos en scip-python,
`Self` → tipo en rust-analyzer, constructores de Dart, ramas `#if` del índice C#, miembros CommonJS sin nombre en
scip-typescript y las llamadas que cada indexador no resuelve nunca (no medibles). En la ronda 3 se añadieron: cada
ocurrencia de definición SCIP cuenta (sobrecargas `@overload` de Python, funciones anidadas homónimas, `module_function`
de Ruby), los ítems `#[cfg]` inactivos de Rust, el `Object#` de Sorbet con receptor explícito, los receptores sin tipo y
los ganchos `self.included` de Ruby, las cadenas sin tipo de scip-php, los nombres genéricos y los símbolos compartidos
de scip-dotnet y semanticdb-kotlinc. En la ronda 4: `require('./m')` en TypeScript como dependencia por ruta, los
tipos definidos en varios archivos (clases parciales, módulos reabiertos) satisfechos por cualquiera de sus archivos, la
lista de supertipos de Kotlin partida en varias líneas, el prefijo de las clases privadas de Dart, y como no medibles los
receptores de Ruby que salen de un método sin `sig` o de una lectura `x[k]`, las llamadas a miembros CommonJS sin nombre
y las anotaciones de Kotlin. En la ronda 5: el árbol de Kotlin con las mismas correcciones de gramática que Córtex, los
miembros heredados de Kotlin nombrados con el tipo del receptor, las propiedades abreviadas exportadas de
scip-typescript, las dependencias de tipo de C# hacia tipos escritos solo con argumentos genéricos, los constructores
con nombre de clases privadas de Dart, y como no medibles las variables locales de Ruby asignadas con valores sin tipo,
las llamadas a privados de Dart sin enlace con su definición y los métodos de C# bajo `<invalid-global-code>`. En la
ronda 6: las referencias de scip-python a módulos del proyecto nombrados sin la raíz de fuentes (`src/`) o solo con su
último tramo (`from paquete import submodulo`). En la ronda 7: como no medibles, las funciones de PHP que scip-php no
nombra (las de `autoload.files`, que `index_php.py` no carga) y lo que se llama sobre su resultado; y el índice de C#
con el marco `Microsoft.AspNetCore.App` y los paquetes NuGet del proyecto (solo ensamblados de referencia). Sus pruebas están en
[`analyzer/tests/test_bench.py`](../analyzer/tests/test_bench.py).
