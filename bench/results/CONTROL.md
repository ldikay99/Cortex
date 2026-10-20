# Ronda 7 de ajuste · antes / después

Generado: 2026-10-20. Los 12 repos de `split = "control6"` se midieron primero a ciegas (código y reglas de la ronda 6)
y después se usaron para ajustar el analizador y las reglas del benchmark (ahora `split = "ajuste7"`). **Antes** =
medida a ciegas, salvo moquette: `analyze()` fallaba en los puentes (`UnboundLocalError` en `bridges.py`, que corrige en
paralelo el trabajo de flujos), y su «antes» es el código de la ronda 6 con los puentes ya corregidos; **después** =
código y reglas actuales, con los índices SCIP reutilizados salvo el de eShopOnWeb, regenerado con el marco de ASP.NET
Core y los paquetes del proyecto (ver abajo). «No medibles»: aristas de llamada apartadas por un límite del indexador.
El detalle de cada repo está en [RESULTS.md](RESULTS.md).

| repo | lenguaje | llamadas P | llamadas R | deps P | deps R | defs R | defs P | no medibles |
|---|---|---|---|---|---|---|---|---|
| gunicorn | python | 99,8 → **99,5** | 93,5 → **95,7** | 100,0 → **100,0** | 96,5 → **97,0** | 100,0 → **100,0** | 99,9 → **99,9** | 0 → 0 |
| mkdocs | python | 99,1 → **99,2** | 87,1 → **95,3** | 100,0 → **98,9** | 90,4 → **96,8** | 100,0 → **100,0** | 99,6 → **99,6** | 0 → 0 |
| npm-check-updates | typescript | 90,6 → **91,3** | 95,2 → **96,0** | 100,0 → **100,0** | 91,7 → **91,7** | 100,0 → **100,0** | 93,9 → **94,8** | 1 → 1 |
| eleventy | javascript | 98,8 → **98,8** | 92,7 → **97,0** | 99,3 → **99,4** | 97,4 → **99,0** | 97,9 → **97,9** | 100,0 → **100,0** | 9 → 9 |
| dive | go | 100,0 → **100,0** | 99,6 → **99,6** | 99,7 → **99,7** | 99,4 → **99,4** | 100,0 → **100,0** | 100,0 → **100,0** | 0 → 0 |
| moquette | java | 98,0 → **98,0** | 99,5 → **99,5** | 97,7 → **97,7** | 100,0 → **100,0** | 100,0 → **100,0** | 100,0 → **100,0** | 0 → 0 |
| ktorm | kotlin | 96,2 → **96,2** | 97,9 → **97,9** | 95,6 → **95,6** | 98,5 → **98,5** | 98,8 → **98,8** | 99,8 → **99,8** | 5 → 5 |
| lobsters | ruby | 87,1 → **98,9** | 99,1 → **99,6** | 90,3 → **100,0** | 100,0 → **100,0** | 99,4 → **99,4** | 100,0 → **100,0** | 91 → 6 |
| bookstack | php | 90,1 → **99,9** | 99,9 → **100,0** | 91,2 → **100,0** | 99,9 → **99,9** | 100,0 → **100,0** | 99,8 → **100,0** | 721 → 867 |
| eshoponweb | csharp | 76,1 → **98,5** | 99,0 → **96,4** | 97,2 → **99,2** | 98,0 → **91,2** | 100,0 → **100,0** | 95,9 → **95,9** | 0 → 0 |
| xh | rust | 97,8 → **97,8** | 97,4 → **97,4** | 98,4 → **98,4** | 96,8 → **96,8** | 100,0 → **100,0** | 99,3 → **99,3** | 0 → 0 |
| melos | dart | 98,0 → **98,1** | 95,2 → **96,2** | 94,8 → **95,5** | 82,1 → **94,1** | 99,9 → **99,9** | 97,2 → **97,2** | 8 → 8 |

Objetivo: llamadas, dependencias y definiciones ≥ 90 % en los 12 repos (llamadas P/R, deps P/R y defs R: 60 métricas),
sin empeorar los 71 de las rondas 1 a 6. Se cumple: 56 → **60** de 60 métricas ≥ 90, media 96,7 → **98,2** (la más
justa, eShopOnWeb deps R 91,2, por el índice nuevo; ver «Patrones restantes»). En los 71 anteriores ninguna métrica baja
(comparación con el `results.json` oficial de la ronda 6, a 0,001 puntos) y suben, por el analizador, liquid llamadas P
96,7 → 99,0 y R 99,0 → 99,6, deps P 97,7 → 100; jekyll llamadas P 98,1 → 99,4 y deps P 94,6 → 98,9; faraday llamadas
P 96,0 → 97,2 y R 97,8 → 98,1; rack llamadas P 95,7 → 96,0 y deps P 99,3 → 100; sinatra llamadas P 99,1 → 99,5 (Ruby);
psr7 llamadas P 98,9 → 100 (PHP); click llamadas R 95,4 → 96,8 y deps R 98,4 → 100, marshmallow llamadas R 94,8 → 95,7,
starlette 97,3 → 97,5 y rich 97,85 → 97,92 (Python); shelf deps R 90,9 → 93,9 (Dart); y por las reglas, twig llamadas P
97,7 → 98,4 y defs P 96,9 → 100. mongoose defs P 90,5 → 99,3 (y llamadas P 96,6 → 96,7) sale de los puentes, que se
editan en paralelo (con el analizador de la ronda 6 y los puentes actuales da lo mismo).

Reparto de la mejora (código de la ronda 6 medido con las reglas y el índice nuevos, mismos puentes): las reglas y el
índice explican bookstack llamadas P 90,1 → 99,5 y deps P 91,2 → 98,8 (funciones de PHP sin símbolo y sus cadenas,
abajo) y eShopOnWeb llamadas P 76,1 → 98,5, deps P 97,2 → 99,6, y también sus bajadas, llamadas R 99,0 → 96,4 y deps R
98,0 → 90,5: con los paquetes, scip-dotnet da 38 referencias más a métodos del proyecto (85 frente a 47) y muchas lecturas más (`item.Id` dentro de lambdas de
LINQ y de Ardalis) que antes no eran verdad de referencia. Ninguna otra métrica de los 12 cambia con las reglas: 57 de
60 métricas ≥ 90 y media 97,2 solo con ellas. Todo lo demás sale del analizador: lobsters llamadas P 87,1 → 98,9 y deps
P 90,3 → 100 (ancestros de fuera del proyecto y sin nombre único con receptor sin tipo en Ruby); mkdocs llamadas R
87,1 → 95,3 y deps R 90,4 → 96,8 (descriptores y clases genéricas de Python); melos deps R 82,1 → 94,1 (partes y
reexportaciones de Dart); bookstack llamadas P 99,5 → 99,9 y deps P 98,8 → 100 (valores de fuera del proyecto en PHP,
`use` que tapa una clase homónima, `@property`); eleventy llamadas R 92,7 → 97,0 y deps R 97,4 → 99,0 (campos asignados
en métodos de JavaScript); gunicorn llamadas R 93,5 → 95,7 (atributos inicializados a `None`); npm-check-updates
llamadas P 90,6 → 91,3 (constantes con un callback que no son funciones); eShopOnWeb deps R 90,5 → 91,2 (lambdas de
tipos genéricos de fuera).

En los 12 bajan cuatro métricas, que siguen ≥ 90: gunicorn llamadas P 99,8 → 99,5 (con los atributos tipados aparecen 4
`self.cfg.set(…)` que scip-python resuelve a `builtins/set#`), mkdocs deps P 100 → 98,9 (una dependencia hacia el
`Locale` de reserva, ver abajo) y las de eShopOnWeb que trae el índice nuevo. «No medibles»: lobsters 91 → 6 porque
Córtex ya no pone aristas por nombre desde receptores sin tipo (Sorbet tampoco los tipa, así que no se puntuaban);
bookstack 721 → 867 por las funciones de PHP sin símbolo.

TIEMPO_CONTROL

## Qué era artefacto del indexador y qué era fallo de Córtex

| repo | hallazgo | tipo | tratamiento |
|---|---|---|---|
| eShopOnWeb | 30 de las 32 llamadas «inventadas» (quedan 2 con el índice nuevo): `basket.AddItem(…)` con `basket` de `IRepository<Basket>` (Ardalis), `await _basketService.TransferBasketAsync(anonymousId, …)` con un argumento de `Request.Cookies`, `AddErrors(result)` con `IdentityResult`, `builder.Services.AddCoreServices(…)` en `Program.cs` | artefacto (configuración del índice: compilado sin el marco de ASP.NET Core ni los paquetes NuGet del proyecto; 0 ocurrencias de `PageModel`, `Controller` o `IServiceCollection` frente a 12, 2 y 7, y 47 referencias a métodos del proyecto frente a 85) | `index_dotnet.py --framework-ref` y `--package` (solo ensamblados de referencia, comprobado tras `restore`); índice regenerado |
| bookstack | `setting('app-public')`, `user()->mfaValues()…`: funciones de `app/App/helpers.php` (en `autoload.files`) y lo que se llama sobre su resultado | artefacto (scip-php nombra una función solo si está cargada, e `index_php.py` no carga `autoload.files`: 0 de 83 funciones con definición en los 7 índices PHP; en bookstack, 388 llamadas a sus 6 funciones y 793 sobre su resultado, ninguna con ocurrencia; en twig, 19 llamadas a sus 65 funciones, ninguna) | no medibles (`run.php_unnamed_functions`, `PhpChains.unnamed`); las homónimas de una función de PHP (`error_log` sustituida en una prueba de monolog) sí se miden |
| bookstack | `response()->json([…])` → `ApiDocsController#json` (59 llamadas), `session()->forget(…)`, `$this->roles->pluck('id')->contains(…)` → `Bookshelf#contains`, `$this->provider->retrieveById(…)` (propiedad heredada de un `StatefulGuard` de Laravel) | fallo de Córtex | `phptyped`: el valor de una función de PHP o de una dependencia, y un miembro que no está en los ancestros del proyecto de una clase con un ancestro de fuera (`foreign_ancestor`), son de fuera |
| bookstack | `new Request('GET', $uri)` con `use GuzzleHttp\Psr7\Request;` → `app/Http/Request.php` (4) | fallo de Córtex | `langs.link_imports`: un `use` de fuera tapa la clase homónima del proyecto |
| bookstack | `$this->user->logDescriptor()` con `@property User $user` (3 FN); las lecturas de esas propiedades no tienen ocurrencia SCIP | fallo de Córtex | `phptyped.doc_properties`: tipan el receptor, sin dependencia por la lectura |
| lobsters | `Tag.active` (un `scope :active`) → `HomeController#active` (10 de las 80 llamadas «inventadas»), `.order(…)` de ActiveRecord → `Search#order` (20), `replaced_hat.save` → `StoriesController#save`, `File.mtime(path)` → `StaticFile#mtime` (jekyll) | fallo de Córtex | `rubytyped.closed` y `foreign_value` (un ancestro de fuera del proyecto cierra la búsqueda y lo que devuelve no tiene tipo); `langs.qualified` sin nombre único con receptor sin tipo en Ruby (12 aciertos frente a 47 errores en los 7 repos de Ruby) |
| liquid, faraday, jekyll | los aciertos que daba el nombre único: `rescue SyntaxError => e; e.markup_context = …` con `SyntaxError = Class.new(Error)`, `other.is_a?(self.class) && other.handlers`, `registers.is_a?(Registers) ? registers.static : …`, `configuration = clone` reasignada dentro de un bloque | fallo de Córtex | `rubytyped`: `Class.new(Base)`, estrechamiento por `is_a?`/`kind_of?`/`instance_of?` y la variable fijada por la asignación anterior al bloque (como Sorbet) |
| mkdocs | `config.plugins.on_page_context(…)` con `plugins = c.Plugins(…)` (`__get__` → `T`, `class Plugins(OptionallyRequired[PluginCollection])`), `self.option_type.run_validation(…)` con `option_type: BaseConfigOption[T]` | fallo de Córtex | `pyast.descriptor`, `generic_env`, `type_params`; `container` (clase genérica del proyecto) |
| gunicorn | `self.cfg.validate()` con `self.cfg = None` en `__init__` y `self.cfg = Config(…)` en otro método | fallo de Córtex | `pyast.own_attr`: las asignaciones de `None` no cuentan |
| melos | 42 dependencias de tipo y 33 de lectura que faltaban desde las partes `part of 'runner.dart'`; 14 desde `lib/melos.dart` (`export 'src/…' show X`) | fallo de Córtex | `langs.dart_scopes`: parte ↔ biblioteca, reexportaciones en cadena con `show`, nombres de `show` como dependencia |
| npm-check-updates | `export const cliOptionsMap = keyValueBy(cliOptions, option => …)`: 26 nodos función sin definición SCIP y 51 llamadas del módulo atribuidas a ellos | fallo de Córtex | `tsjs.demote_wrapped`: con una función del proyecto que declara un retorno que no es una función (`: Index<R>`), la constante es un valor |
| eleventy | `this.templateData.getDataDir()` con `this.templateData = new TemplateData(…)` en un método de `CoreMinimal` | fallo de Córtex | `tsjs.method_fields` (JavaScript); un `/** @type {object} */` encima manda, como en TypeScript (`jsdoc_hides`) |
| eShopOnWeb | `builder.Property(ci => ci.Id)` con `EntityTypeBuilder<CatalogItem> builder` | fallo de Córtex | `cstyped.lambda_param`: la lambda de un método de un tipo genérico de fuera recibe su argumento de tipo del proyecto |
| (bridges) moquette | `analyze()` fallaba (`UnboundLocalError` en `bridges.py`) | fallo de Córtex (fuera de esta ronda) | corregido por el trabajo de flujos; medido con ese código |

## Patrones restantes (después)

- **eShopOnWeb**: deps R 91,2. Con los paquetes, scip-dotnet ve lecturas que Córtex no tipa: `item.Id` sobre elementos de
  métodos de Ardalis o de EF Core (`catalogItems.First(…)`, `Query.Where(b => b.BuyerId …)` con `Query` heredado de
  `Specification<T>`), 18 dependencias; y nombres calificados con el espacio de nombres
  (`BlazorShared.Authorization.Constants.Roles.ADMINISTRATORS`), 4.
- **npm-check-updates**: llamadas P 91,3: 47 llamadas a constantes que scip-typescript no firma como función, porque la
  fábrica es de un paquete sin tipos instalados (`const parseNpmrc = memoize((p) => …)`, firma `any`) o porque firma con el
  nombre de un alias (`var distTag: GetVersion` con `type GetVersion = (…) => …`; contarlas expondría, además, campos
  tipados así que Córtex no trata como métodos: hono, excalidraw, ioredis); deps R 91,7: 44 lecturas de propiedades de
  interfaces (`options.cacheFile` con `options: RunOptions`).
- **melos**: deps R 94,1: lecturas encadenadas de propiedades (`workspace.config.commands.analyze`) en las partes y
  llamadas a métodos de un `mixin` aplicado (`melos.run(…)` con `_RunMixin`).
- **mkdocs**: elementos de `for key, config_option in self._schema` (`PlainConfigSchema = Sequence[Tuple[str,
  BaseConfigOption]]`, 6 FN) y retornos sin anotación (`server.serve()`); deps P 98,9 por `Locale` de un
  `try: from babel.core import Locale except ImportError: from mkdocs.utils.babel_stub import Locale`.
- **gunicorn**: llamadas P 99,5: `self.cfg.set(…)` que scip-python resuelve a `builtins/set#` (4 FP); llamadas R 95,7:
  receptores que son parámetros sin anotar y retornos de funciones sin anotación (`_get_client().delete(…)`).
- **ktorm**: deps P 95,6 sin cambio: extensiones de la biblioteca estándar de Kotlin (`use`, `runCatching`) que Córtex
  enlaza a homónimas del proyecto.


# Ronda 6 de ajuste · antes / después (histórico)

Generado: 2026-10-20. Los 12 repos de `split = "control5"` se midieron primero a ciegas (código y reglas de la ronda 5)
y después se usaron para ajustar el analizador y las reglas del benchmark (ahora `split = "ajuste6"`). **Antes** =
medida a ciegas; **después** = código y reglas actuales, con los índices SCIP reutilizados (ninguno se regeneró).
«No medibles»: aristas de llamada apartadas por un límite del indexador. El detalle de cada repo está en
[RESULTS.md](RESULTS.md).

| repo | lenguaje | llamadas P | llamadas R | deps P | deps R | defs R | defs P | no medibles |
|---|---|---|---|---|---|---|---|---|
| marshmallow | python | 100,0 → **100,0** | 94,8 → **94,8** | 87,1 → **100,0** | 100,0 → **100,0** | 100,0 → **100,0** | 99,7 → **99,7** | 0 → 0 |
| rq | python | 99,8 → **99,8** | 97,2 → **97,2** | 100,0 → **100,0** | 100,0 → **100,0** | 100,0 → **100,0** | 99,9 → **99,9** | 0 → 0 |
| ioredis | typescript | 97,1 → **97,3** | 91,0 → **98,1** | 99,5 → **99,5** | 97,0 → **97,0** | 98,4 → **99,8** | 100,0 → **100,0** | 3 → 3 |
| mongoose | javascript | 96,6 → **96,6** | 99,4 → **99,3** | 97,4 → **97,4** | 100,0 → **100,0** | 95,5 → **95,4** | 90,5 → **90,5** | 462 → 462 |
| afero | go | 100,0 → **100,0** | 100,0 → **100,0** | 100,0 → **100,0** | 96,4 → **96,4** | 100,0 → **100,0** | 100,0 → **100,0** | 0 → 0 |
| commons-codec | java | 99,4 → **99,4** | 98,7 → **98,7** | 99,0 → **99,0** | 99,5 → **99,5** | 100,0 → **100,0** | 100,0 → **100,0** | 0 → 0 |
| hoplite | kotlin | 97,5 → **97,9** | 77,4 → **95,7** | 97,4 → **97,5** | 94,7 → **99,0** | 99,3 → **99,3** | 100,0 → **100,0** | 0 → 0 |
| faraday | ruby | 94,1 → **96,0** | 90,4 → **97,8** | 98,1 → **98,2** | 95,4 → **100,0** | 89,6 → **100,0** | 99,3 → **99,4** | 63 → 57 |
| flysystem | php | 99,8 → **99,8** | 98,8 → **98,8** | 100,0 → **100,0** | 99,3 → **99,3** | 99,0 → **99,0** | 100,0 → **100,0** | 738 → 738 |
| flurl | csharp | 99,1 → **99,1** | 98,4 → **98,4** | 100,0 → **100,0** | 97,5 → **97,5** | 100,0 → **100,0** | 100,0 → **100,0** | 10 → 10 |
| indexmap | rust | 97,8 → **97,8** | 98,1 → **98,1** | 97,1 → **97,1** | 99,0 → **99,0** | 98,5 → **98,5** | 99,2 → **99,2** | 0 → 0 |
| rxdart | dart | 99,7 → **99,8** | 77,0 → **98,0** | 99,5 → **99,5** | 99,0 → **100,0** | 99,5 → **99,5** | 100,0 → **100,0** | 8 → 12 |

Objetivo: llamadas, dependencias y definiciones ≥ 90 % en los 12 repos (llamadas P/R, deps P/R y defs R: 60 métricas),
sin empeorar los 59 de las rondas 1 a 5. Se cumple: 56 → **60** de 60 métricas ≥ 90, media 97,2 → **98,8** (la más
justa, hoplite llamadas R 95,7; defs P de mongoose, 90,5, no cambia: ver «Patrones restantes»). En los 59 anteriores
ninguna métrica baja (comparación con el `results.json` oficial de la ronda 5, a 0,001 puntos) y suben jekyll defs R
96,2 → 98,8 y defs P 98,9 → 100, rack defs R 96,7 → 99,7 y llamadas R 99,5 → 100, liquid defs R 97,6 → 97,9 y defs P
99,8 → 100 (línea del símbolo en los accesores de Ruby y delegadores de `Forwardable`), y moment defs R 98,7 → 100
(`export var getSetHour = makeGetSet('Hours', true)`: constante fabricada por una función que devuelve una función).

Reparto de la mejora (código de la ronda 5 medido con las reglas nuevas): las reglas del benchmark explican marshmallow
deps P 87,1 → 100 (módulos de scip-python sin la raíz `src/`); la regla de `Function` de scip-typescript hace medible una
definición y una llamada más en mongoose (llamadas R 99,4 → 99,3, defs R 95,5 → 95,4) y ninguna otra métrica de los 12
cambia con las reglas. Todo lo demás sale del analizador: hoplite llamadas R 77,4 → 95,7 y deps R 94,7 → 99,0 (extensiones
con receptor parámetro de tipo, constructores calificados con el paquete); rxdart llamadas R 77,0 → 98,0 (llamadas
genéricas de Dart encadenadas o con argumentos con nombre, constructores con nombre de clases genéricas, extensiones sobre
`Iterable`); faraday defs R 89,6 → 100, llamadas R 90,4 → 97,8 y P 94,1 → 96,0, deps R 95,4 → 100 (delegadores de
`Forwardable`, `Struct.new(…) do … end`); ioredis llamadas R 91,0 → 98,1 y defs R 98,4 → 99,8 (constantes fabricadas
por una función que devuelve una función).

Tiempo de análisis (CPU, `analyze()` completo, mismos puentes, código de la ronda 5 frente al actual, una pasada
alterna por repo): 71 repos 615,8 → 590,4 s, 59 repos 566,0 → 540,4 s, los 12 nuevos 49,8 → 50,0 s; la parte de los
analizadores de lenguaje (`langs`), 235,1 → 219,2 s. La bajada es ruido de la máquina: repetidas dos veces más, las
mayores diferencias (http4k −6,0 s, exposed −4,9 s, markdig −3,7 s, zod +0,9 s) quedan iguales (http4k 73,9/72,5 →
72,1/74,4 s; exposed 51,3/46,0 → 44,8/45,7 s; markdig 17,1/17,1 → 17,2/20,0 s). Sin coste medible.

## Qué era artefacto del indexador y qué era fallo de Córtex

| repo | hallazgo | tipo | tratamiento |
|---|---|---|---|
| marshmallow, click, rich, httpx, rq, flask | `from marshmallow.exceptions import X` → `` `marshmallow.exceptions`/__init__: `` con la definición en `` `src.marshmallow.exceptions`/__init__: `` (raíz de fuentes); `from marshmallow import fields as ma_fields` → `fields/__init__:` en el import y en cada uso | artefacto (scip-python: referencias del proyecto a módulos sin definición, regla de la ronda 2 → actual: marshmallow 174 → 11, click 119 → 43, rich 54 → 27, httpx 26 → 11, rq 74 → 59, flask 90 → 78, httpie 68 → 67; healthchecks 966 y starlette 45 sin cambio, son paquetes externos no instalados) | `run.python_relative_modules`: el único módulo definido cuyo nombre termina en el referenciado; en la ruta de un import absoluto solo quitando carpetas que no son paquete, y un `import apprise` externo homónimo de un subpaquete no se enlaza ni en sus usos |
| mocha, mongoose | `var stackFilter = utils.stackTraceFilter()` con firma `var stackFilter: Function` | artefacto (scip-typescript no tipa mejor el resultado de una fábrica CommonJS: 2 variables con firma `Function` y valor de llamada, 2 referencias, en los 13 índices TS/JS) | `run.factory_function`: invocable; un campo `target: Function` sin valor no (en class-validator contaría 3 campos que nunca se llaman) |
| hoplite | `ConfigFailure.UnknownSource(r).invalid()` con `fun <E> E.invalid()` (89 llamadas), `x.valid()` con `fun <A> A.valid()` (34) | fallo de Córtex | `typed.extension` + `kt_type_param`: receptor parámetro de tipo con sus cotas (`<T : Base>`, `where`), detrás de una extensión de receptor concreto |
| hoplite | `com.sksamuel.hoplite.decoder.BigDecimalDecoder()` (49 llamadas desde una lista de nivel de módulo) | fallo de Córtex | `typed.kt_call`: nombre calificado con el paquete |
| rxdart | `DoStreamTransformer<T>(onCancel: x).bind(this)` (la gramática lo lee como comparaciones, con `record_literal` y selectores detrás), `CombineLatestStream.list<T>(xs)`, `_Wrapper<T>.seeded(x)` (`constructor_invocation`) | fallo de Córtex | `langs.dart_generic_parts`, `dart_constructor_call`; `darttyped.generic_target` (receptor de la cadena) |
| rxdart | `subscriptions.cancelAll()` con `extension … on Iterable<StreamSubscription<void>>` y `subscriptions: List<StreamSubscription<T>>` (39 llamadas) | fallo de Córtex | `darttyped.extension`: supertipos de la SDK (`SUPERS`) y argumentos de tipo compatibles (`same_args`) |
| faraday | `def_delegators :builder, :use, :request…` (22 definiciones), `Stub = Struct.new(:host, …) do … end` (clase y 24 accesores; `host` dentro de sus métodos) | fallo de Córtex | `langs.ruby_accessor_sites` (solo en el cuerpo de la clase), `ruby_struct_class`; `rubytyped`: el bloque es la clase para `self`, no para las constantes |
| jekyll, rack, liquid | `def_delegators`/`attr_accessor` partidos en varias líneas: SCIP define cada método en su símbolo, Córtex en la línea de la llamada (a más de 3 líneas) | fallo de Córtex | la línea del nodo es la del símbolo |
| ioredis, moment | `const debug = Debug("redis")` con `genDebugFunction(): (...args) => void` (45 llamadas a `debug`), `export var getSetHour = makeGetSet('Hours', true)` (5 definiciones) | fallo de Córtex | `tsjs`: pendiente `factory` y `makes_function` (retorno declarado como función o `return` de una función); la llamada que la fabrica es de la constante |
| (pruebas de puentes) | `data:Room (Android)`: `@Query("SELECT …")` quedaba fuera del rango del método desde que la ronda 5 movió `line` a la declaración | fallo de Córtex (ronda 5) | `langs.placed`: `line` es la primera línea (con anotaciones) y `decl` la de la declaración; el benchmark y `scip.Locator` usan `decl` |

## Patrones restantes (después)

- **mongoose**: defs P 90,5 sin cambio desde la medida a ciegas: 71 nodos `class` con `table` que el código de flujos
  (`bridges.py`, fuera de esta ronda) crea a partir de ejemplos en comentarios JSDoc (`conn.model('Test', …)` en
  `connection.js:239`).
- **hoplite**: extensión miembro de un `companion object` importada (`import …ClasspathResourceLoader.Companion.toClasspathResourceLoader`
  sobre `X::class.java`, 8 FN) y propiedades genéricas sustituidas por el argumento (`errors.list` con
  `NonEmptyList<ConfigFailure>`, 5 FN).
- **rxdart**: parámetros tipados por un genérico (`sink.onListen()`, 6 FN); `_WhereTypeStreamSink<S, T>(…)` con dos
  argumentos de tipo.
- **marshmallow**: atributos asignados en `__init__` desde parámetros (`self.inner.deserialize(…)`), 11 FN.
- **faraday**: `self.class::Handler.new` (3 FP, Sorbet no tipa `self.class::X`) y escrituras `self.headers =` en un
  `Struct` con un `def headers=` explícito (2 FP: SCIP sitúa el símbolo en el miembro del `Struct`).
- **test_bridges_generalize.py::test_file_routes_dart_clients_and_annotated_models**: espera la arista `http` desde la
  clase `UsersProvider`; desde la ronda 5 el rango de un método de Dart incluye su cuerpo y la arista sale, bien, de
  `UsersProvider.fetch`/`update`. Es la expectativa de la prueba (fuera de esta ronda), no el análisis.


# Ronda 5 de ajuste · antes / después (histórico)

Generado: 2026-10-20. Los 12 repos de `split = "control4"` se midieron primero a ciegas (código y reglas de la ronda 4)
y después se usaron para ajustar el analizador y las reglas del benchmark (ahora `split = "ajuste5"`). **Antes** =
medida a ciegas; **después** = código y reglas actuales, con los índices SCIP reutilizados salvo el de polly, regenerado
con la configuración de compilación del repo (ver abajo). «No medibles»: aristas de llamada apartadas por un límite del
indexador. El detalle de cada repo está en [RESULTS.md](RESULTS.md).

| repo | lenguaje | llamadas P | llamadas R | deps P | deps R | defs R | defs P | no medibles |
|---|---|---|---|---|---|---|---|---|
| click | python | 97,9 → **98,0** | 92,0 → **95,3** | 100,0 → **100,0** | 98,4 → **98,4** | 100,0 → **100,0** | 99,5 → **99,5** | 0 → 0 |
| starlette | python | 99,7 → **99,8** | 94,6 → **97,3** | 100,0 → **100,0** | 100,0 → **100,0** | 100,0 → **100,0** | 100,0 → **100,0** | 0 → 0 |
| immer | typescript | 100,0 → **100,0** | 96,1 → **100,0** | 100,0 → **100,0** | 83,9 → **100,0** | 99,2 → **100,0** | 100,0 → **100,0** | 0 → 0 |
| fastify | javascript | 93,7 → **99,0** | 99,4 → **99,0** | 100,0 → **100,0** | 100,0 → **100,0** | 99,5 → **99,5** | 100,0 → **100,0** | 14 → 14 |
| echo | go | 98,9 → **98,9** | 99,8 → **99,8** | 99,2 → **99,2** | 99,2 → **99,2** | 100,0 → **100,0** | 100,0 → **100,0** | 0 → 0 |
| commons-io | java | 98,7 → **98,7** | 97,6 → **97,6** | 97,7 → **97,7** | 99,0 → **99,0** | 100,0 → **100,0** | 100,0 → **100,0** | 0 → 0 |
| exposed | kotlin | 90,0 → **98,0** | 74,8 → **94,7** | 92,2 → **95,2** | 79,1 → **96,9** | 92,6 → **98,2** | 99,0 → **100,0** | 4 → 6 |
| liquid | ruby | 90,6 → **96,7** | 99,0 → **99,0** | 93,2 → **97,7** | 100,0 → **100,0** | 97,6 → **97,6** | 99,8 → **99,8** | 78 → 112 |
| twig | php | 97,7 → **97,7** | 99,9 → **99,9** | 100,0 → **100,0** | 100,0 → **100,0** | 99,8 → **99,9** | 96,8 → **96,9** | 983 → 983 |
| polly | csharp | 57,1 → **96,2** | 99,5 → **97,7** | 72,4 → **98,7** | 93,8 → **95,8** | 98,4 → **99,8** | 98,6 → **100,0** | 90 → 109 |
| fd | rust | 98,5 → **98,5** | 98,5 → **98,5** | 90,8 → **98,6** | 100,0 → **100,0** | 98,3 → **98,3** | 99,2 → **99,2** | 0 → 0 |
| collection | dart | 90,0 → **99,2** | 94,2 → **99,2** | 100,0 → **100,0** | 98,2 → **100,0** | 96,8 → **96,8** | 97,0 → **97,3** | 0 → 17 |

Objetivo: llamadas, dependencias y definiciones ≥ 90 % (P y R) en los 12 repos, sin empeorar los 47 de las rondas 1 a 4.
Se cumple en los 12 (el más justo, exposed llamadas R 94,7). En los 47 anteriores, ninguna métrica baja más de 0,4
puntos: http4k deps R 98,4 → 98,0 (dos dependencias que faltan y que antes no se medían: miembros heredados que
semanticdb-kotlinc nombra con el subtipo, como `LensExtractor#get()`), axios deps R 100 → 99,4 (una dependencia que hace
visible la regla de propiedades exportadas, `platform.generateString`) y llamadas P 99,6 → 99,5 (2 FP de 431 llamadas,
antes 1 de 280), y ktlint llamadas R 98,25 → 98,20 (una llamada). miniflux defs P 100 → 99,5 sale de 16 nodos de tablas
SQL (`internal/database/migrations.go`) que añade el código de flujos que se edita en paralelo a esta ronda; con los
puentes de la ronda 4 miniflux no cambia. Suben, entre otros, ktlint deps R 95,3 → 99,2 y defs R 97,4 → 99,7, dapper
deps R 92,0 → 96,0, markdig deps R 94,0 → 97,3, zod deps R 93,9 → 97,8, http4k llamadas P 96,1 → 97,2 y deps P 93,2 →
95,0, thor deps P 97,9 → 100, ripgrep deps P 96,2 → 98,6, itertools llamadas R 93,0 → 94,3 y shelf defs R 97,6 → 98,4.

Reparto de la mejora (código de la ronda 4 medido con las reglas y el índice nuevos): las reglas del benchmark y el
índice de polly explican polly llamadas P 57,1 → 96,2 y deps P 72,4 → 99,3 (casi todo por el índice, compilado sin los
`global using` del repo y con 790 errores; deps R baja entonces a 90,3 porque hay más dependencias de referencia);
fastify llamadas P 93,7 → 99,0 (propiedades abreviadas exportadas; con la regla, R baja a 97,9 y el analizador la
devuelve a 99,0); liquid llamadas P 90,6 → 96,7 y deps P 93,2 → 97,7 (variables locales de Ruby sin tipo); collection
llamadas P 90,0 → 93,6 y R → 95,8 (privados de Dart); exposed llamadas P 90,0 → 92,5 y deps P → 93,3 (miembros heredados
de Kotlin y el árbol del benchmark corregido). El resto sale del analizador: exposed llamadas P 92,5 → 98,0 y R 74,7 →
94,7, deps R 78,5 → 96,9 y defs R 92,6 → 98,2 (gramática de Kotlin, extensiones, propiedades de nivel superior, línea de
la declaración); immer llamadas R 96,1 → 100 y deps R 83,9 → 100 (uniones, constantes a través de un barril); click
llamadas R 92,0 → 95,3 y starlette 94,6 → 97,3 (bases genéricas de Python); polly deps R 90,3 → 95,8 y defs R 98,4 →
99,8; fd deps P 90,8 → 98,6 (`super` en un `mod tests`); collection llamadas → 99,2 / 99,2 (rango de los métodos de
Dart, `Caja<T>(x)`).

Tiempo de análisis (CPU, `analyze()` completo, mismos puentes): 59 repos 542,6 → 543,9 s (+0,2 %), 47 repos 413,4 →
412,0 s; la parte de los analizadores de lenguaje (`langs`), 206,2 → 216,9 s (+5,2 %), sobre todo C# (polly +3,8 s,
markdig +2,2 s, dapper +1,8 s: los miembros implícitos como dependencia).

## Qué era artefacto del indexador y qué era fallo de Córtex

| repo | hallazgo | tipo | tratamiento |
|---|---|---|---|
| polly | 154 de las 157 llamadas «inventadas» y 127 dependencias de más: el índice se compiló sin los `global using` del repo (`<Using Include="Polly.Utils" />` del `.csproj`, `ImplicitUsings` de `eng/Common.props`, `System.Collections`… de `Directory.Build.targets`): 790 errores de compilación en 122 archivos (`TimeSpan`, `ValueTask`, `CancellationToken` sin resolver) y 0 de 171 usos de tipos de `Polly.Utils` con ocurrencia en los 141 archivos que dependen de ese `using` | artefacto (configuración del índice, como serilog en la ronda 2) | `index_dotnet.py --using`; índice regenerado: 0 errores, 133 de 171 usos con ocurrencia |
| polly, markdig, stateless | `Func<FallbackActionArguments<T>, …>`: un tipo del proyecto escrito solo con argumentos de tipo | artefacto (scip-dotnet: 0 de 415 nombres genéricos de tipos del proyecto con ocurrencia en polly, 0/127 markdig, 0/144 stateless, 0/34 dapper; 1151 de 1165 de los mismos tipos sin argumentos) | la dependencia de tipo hacia su archivo no se puntúa (`run.dotnet_type_homes`) |
| polly, markdig, serilog | métodos de `PredicateBuilder<TResult>`, `GeneratorHelper`… que scip-dotnet define bajo `` `<invalid-global-code>` `` | artefacto (0 de 48 llamadas escritas en polly, 1 de 76 en markdig, 0 de 9 en serilog llevan ese símbolo) | no medibles (`run.dotnet_unnamed`) |
| polly | referencia a `ResiliencePipeline` (clase parcial en seis archivos), `Name = …` heredado en un constructor, `Component` declarado en otra parte de la clase, `new X { InjectionRate = r }`, `Func<double> f = RandomUtil.NextDouble` | fallos de Córtex | `langs.partial_parts`, `cstyped.implicit_member`, `cstyped.members` (grupos de métodos) |
| polly, exposed | `[UnconditionalSuppressMessage(…)]` / `@Deprecated(…)` en varias líneas: el nodo empezaba en el atributo, a más de 3 líneas del nombre | fallo de Córtex | `langs.decl_line`: la línea de una definición es la de su declaración (como el `def` de Python tras sus decoradores) |
| exposed | `where?.let { … }` (`where` es palabra clave suave) y `@Synchronized set(v)` rompían el árbol de 11 de los 79 archivos medidos (`TransactionManager`, `FunctionProvider`, `Query`, cinco dialectos): sus miembros se leían como funciones de nivel superior | fallo de Córtex (gramática de tree-sitter-kotlin) | `langs.kotlin_fixups` (sin mover posiciones), también en el árbol del benchmark; los bytes NUL de un comentario (ktlint) se vuelven espacios |
| exposed | `append("CAST(", e, ")")` dentro de `queryBuilder { }`: el miembro `append(String)` no admite tres argumentos y la extensión `fun QueryBuilder.append(vararg)` sí | fallo de Córtex | `typed.method(strict)` y `extension(argc)` (Kotlin) |
| exposed | `currentDialect` (propiedad de nivel superior importada con `vendors.*`), `exposedLogger`, `val dialect by lazy { … }`, `buildString { append(…) }`, extensiones miembro (`cols.appendTo { }`) en lambdas con receptor, `CONTENT_TYPE of x` | fallos de Córtex | `typed.top_prop_home`, `kt_property`, `KT_BUILDERS`, `extension` (receptores de despacho), llamadas infijas |
| exposed, http4k, javalin | `delete.execute(…)` → `DeleteStatement#execute().` sin definición: `execute` solo se define en `Statement` | artefacto (semanticdb-kotlinc: 291 referencias así en exposed, 114 en http4k, 32 en javalin; 0 en los índices de Java) | `run.jvm_inherited`, con los supertipos que nombra la declaración (en un tipo, semanticdb-kotlinc a veces lista sus subtipos: `Filter#` → `CacheFilter#`) |
| immer | `state.base_` y `state.scope_.immer_` con `state: ImmerState` (unión de cuatro interfaces): scip-typescript emite una ocurrencia por declaración | fallo de Córtex | `tsjs.union`, `member_owners`, `key_owners` |
| immer | `import {DRAFT_STATE} from "../internal"` (barril con `export *`) y `const O = Object; export const getPrototypeOf = O.getPrototypeOf` | fallos de Córtex | `tsjs.value_home`, `builtin_function` |
| fastify, mocha, axios | `module.exports = { getSchemaSerializer }` / `export default { isArray, hasOwnProp: hasOwnProperty }`: scip-typescript define la propiedad como símbolo «meta» (`getSchemaSerializer0:`) y las llamadas lo usan | artefacto (53 propiedades y 37 referencias en fastify, 20 y 33 en mocha, 9 y 39 en axios) | la llamada a la propiedad es la llamada a la función (`run.ground_truth`, `forward`) |
| axios, fastify, mocha | `utils.isArray(x)` sobre `export default { … }`, `decorators.exist(…)` con `exist: checkExistence`, `require('./errors').deprecate(…)` | fallos de Córtex (visibles con la regla anterior) | `tsjs.default_members`, `read_cjs_exports`, `loads_at` |
| collection | `_bubbleDown(…)` con un símbolo `local` distinto del de su definición | artefacto (scip-dart: 34 de 216 llamadas a privados en collection; 0 en shelf, path, yaml y markdown) | no medibles (`blind_sites`) |
| collection | el nodo de un método de Dart acababa en la firma (el cuerpo es hermano en el árbol): las llamadas del cuerpo no caían en su rango | fallo de Córtex | `langs`: rango y hash del nodo con el cuerpo |
| collection | `_IteratorZip<T>(…)`: la gramática lo lee como `_IteratorZip < T > (…)` | fallo de Córtex (gramática) | `langs.dart_generic_call` |
| collection | `_GrowableBoolList._withCapacity(…) : super._(…)`: constructor con nombre de una clase privada | regla (fallo del benchmark) | `run.dart_privates` en dos pasadas |
| liquid | `p = @parse_context.new_parser(lhs); p.consume(:id)` | artefacto (Sorbet: 0 de 613 llamadas sobre variables así en liquid, jekyll, thor, rack y sinatra se resuelven a un método del proyecto) | no medibles (`run.ruby_untyped_local`) |
| fd | `mod tests { use super::x; }` dependía del módulo padre del archivo | fallo de Córtex | `langs.rust_imports` (`super` dentro de un módulo en línea) |
| click, starlette | `class Choice(ParamType[str])`: la base genérica no se resolvía (`self.fail()` heredado) | fallo de Córtex | `pyast.generic_base` |
| ktlint (efecto) | las anotaciones no medibles se apartaban en su línea, y el nodo ahora empieza en la declaración | regla (adaptación del benchmark) | `run.kotlin_annotations` también en la línea de la declaración anotada |

## Muestra de las categorías nuevas de «no medibles»

- **variable local de Ruby asignada con un valor sin tipo** — liquid 200, jekyll 111, thor 72, rack 193, sinatra 37
  llamadas; con método del proyecto en SCIP 0. `liquid/tags/assign.rb:59 p.consume(:id)` (con `p =
  @parse_context.new_parser(lhs)`), `liquid/block_body.rb:60 tag.parse(…)`, `rack/directory.rb:144 stat.mtime`,
  `thor.rb:266 command.options`.
- **llamada a un privado de Dart sin enlace** — collection 34 de 216 (shelf 0/184, path 0/47, yaml 0/265, markdown
  0/84). `lib/src/priority_queue.dart:240 _bubbleDown(…)` (`local 15`; la definición de la línea 437 es `local 82`).
- **métodos de C# bajo `<invalid-global-code>`** — polly 9 métodos (26 definiciones), markdig 19, serilog 1.
  `src/Polly.Core/PredicateBuilder.TResult.cs:31 Add(…)`, `:130 CreatePredicate(…)`.

## Patrones restantes (después)

- **exposed**: `Op<Boolean>.toQueryBuilder` que semanticdb-kotlinc resuelve a `Op#TRUE#toQueryBuilder()`, extensiones
  miembro importadas desde un `object` (`import …SqlExpressionBuilder.wrap`), `.inProperCase()` sobre un receptor de
  tipo desconocido con un miembro homónimo en el proyecto, e `import` sin uso real (dependencias de más).
- **polly**: llamadas genéricas dentro de métodos con varias sobrecargas (`GetSyncContext<TResult>(…)`: el nodo de
  Córtex junta las sobrecargas) y `ex.TrySetStackTrace()` (extensión genérica `this T` con `where T : Exception`).
- **http4k**: con los miembros heredados ya medidos, `LensExtractor#get()` y `UriTemplate#toString()` heredados que
  Córtex no ve (deps R 98,4 → 98,0).
- **mocha**: parámetros tipados solo por JSDoc (`@param {BufferedWorkerPool} pool`), 5 FN.

# Ronda 4 de ajuste · antes / después (histórico)

Generado: 2026-10-20. Los 11 repos de `split = "control3"` se midieron primero a ciegas (código y reglas de la ronda 3) y
después se usaron para ajustar el analizador y las reglas del benchmark (ahora `split = "ajuste4"`). **Antes** = medida a
ciegas; **después** = código y reglas actuales, con los índices SCIP reutilizados. «No medibles»: aristas de llamada
apartadas por un límite del indexador. El detalle de cada repo está en [RESULTS.md](RESULTS.md).

| repo | lenguaje | llamadas P | llamadas R | deps P | deps R | defs R | defs P | no medibles |
|---|---|---|---|---|---|---|---|---|
| httpie | python | 100,0 → **100,0** | 96,3 → **96,3** | 99,6 → **99,6** | 93,2 → **97,0** | 100,0 → **100,0** | 99,8 → **99,8** | 0 → 0 |
| gotify-server | go | 99,8 → **99,8** | 100,0 → **100,0** | 96,4 → **96,4** | 98,2 → **98,2** | 100,0 → **100,0** | 100,0 → **100,0** | 0 → 0 |
| hexo | typescript | 98,7 → **99,2** | 56,2 → **98,5** | 75,6 → **100,0** | 77,8 → **99,3** | 92,2 → **98,8** | 99,8 → **99,8** | 2 → 2 |
| mocha | javascript | 98,2 → **99,0** | 86,5 → **97,5** | 100,0 → **100,0** | 100,0 → **100,0** | 91,5 → **100,0** | 99,4 → **100,0** | 162 → 179 |
| jekyll | ruby | 93,1 → **97,8** | 99,4 → **99,4** | 78,1 → **93,9** | 95,2 → **100,0** | 96,2 → **96,2** | 98,9 → **98,9** | 170 → 239 |
| zxing | java | 99,9 → **99,9** | 99,8 → **99,8** | 100,0 → **100,0** | 100,0 → **100,0** | 99,9 → **99,9** | 99,9 → **99,9** | 0 → 0 |
| ktlint | kotlin | 93,4 → **99,2** | 88,4 → **98,2** | 98,5 → **98,9** | 84,8 → **95,3** | 97,4 → **97,4** | 97,7 → **97,7** | 0 → 101 |
| bat | rust | 98,0 → **98,0** | 96,9 → **96,9** | 92,7 → **94,7** | 92,7 → **95,3** | 96,3 → **96,3** | 100,0 → **100,0** | 0 → 0 |
| shelf | dart | 91,8 → **97,7** | 97,5 → **97,7** | 98,4 → **98,4** | 90,9 → **90,9** | 97,6 → **97,6** | 97,6 → **97,6** | 0 → 0 |
| slim | php | 100,0 → **100,0** | 96,9 → **96,9** | 100,0 → **100,0** | 100,0 → **100,0** | 98,4 → **98,4** | 100,0 → **100,0** | 17 → 17 |
| dapper | csharp | 94,2 → **96,5** | 97,7 → **97,7** | 91,1 → **96,3** | 83,1 → **92,0** | 98,0 → **98,0** | 99,4 → **99,8** | 77 → 77 |

Objetivo: llamadas, dependencias y definiciones ≥ 90 % (P y R) en los 11 repos, sin empeorar los 36 de las rondas 1 a
3. Se cumple en los 11 (el más justo, shelf deps R 90,9, sin cambio). En los 36 anteriores ninguna métrica baja salvo
express defs P 100 → 94,7: un nodo nuevo, `var flatten = Array.prototype.flat` (alias de una función de la biblioteca
estándar), que scip-typescript no tipa porque el `tsconfig` inferido usa `lib` ES5 (sin `flat`, de ES2019): el `flat`
de esa línea no tiene ocurrencia, mientras que `Array.prototype.slice` dos líneas antes sí (`lib.es5.d.ts`/`Array#slice`).
Suben, entre otros, zod llamadas R 91,1 → 92,7, http4k llamadas R 90,2 → 93,4 y P 95,8 → 96,1, javalin llamadas R 95,4
→ 96,1, yaml llamadas P 98,5 → 99,7, moment defs R 97,9 → 98,7 y excalidraw llamadas R 95,5 → 96,1.

Reparto de la mejora (código de la ronda 3 medido con las reglas nuevas): las reglas del benchmark explican shelf
llamadas P (prefijo de las clases privadas de Dart), bat deps (tipos de varios archivos) y parte de jekyll (llamadas P
93,1 → 98,0, deps R → 100), ktlint llamadas P (→ 98,4) y dapper deps R (→ 92,0); hexo deps P (→ 100) es la regla de
`require` en TypeScript. El resto sale del analizador: hexo llamadas R 56,2 → 98,5 y deps R 82,2 → 99,3; mocha llamadas R
86,5 → 97,5 y defs R 91,5 → 100; ktlint llamadas R 89,1 → 98,2 y deps R 85,2 → 95,3; jekyll deps P 85,0 → 93,9; dapper
llamadas P 94,2 → 96,5 y deps P 92,0 → 96,3; httpie deps R 93,2 → 97,0.

## Qué era artefacto del indexador y qué era fallo de Córtex

| repo | hallazgo | tipo | tratamiento |
|---|---|---|---|
| hexo | `export = Hexo` (68 módulos) y `export { default as Console } from './console'`: la clase exportada no se encontraba desde `import Hexo from` | fallo de Córtex | `tsjs.read_top_level` (`export =` es la exportación por defecto y la de CommonJS) |
| hexo | `function cleanConsole(this: Hexo)`: el tipo de `this` sale del parámetro `this` | fallo de Córtex | `tsjs.this_param` |
| hexo | `date: typeof date` en `LocalsType` (40 definiciones y las llamadas `this.date(…)`) | fallo de Córtex | `tsjs.type_query` (método que remite a la función) |
| hexo | `_binaryRelationIndex: { post_tag: BinaryRelationIndex<…> }` | fallo de Córtex | tipo objeto en línea (`annotation_type`) |
| hexo | `render({ path })` y `const { i18n } = this.theme` (claves de objetos tipados, desestructuración) | fallo de Córtex | `tsjs.key_owners` (sin uniones ni tipos mapeados, donde scip-typescript define propiedades nuevas: class-validator `validator: ValidatorConstraintInterface \| Function`, zod `Partial<ParseParams>`) |
| hexo | `require('./clean')` en archivos `.ts` (91 sitios): ninguna ocurrencia del módulo | artefacto (es el `require` de Node, `any`) | dependencia por ruta (`run.ts_requires`); en `.js` scip-typescript sí la emite (180 de 186 en mocha y express) |
| mocha | `var color = (exports.color = function…)`, `exports = module.exports = Base`, `var color = Base.color` | fallos de Córtex | `tsjs.export_chain`, `read_commonjs`, `cjs_owners` |
| mocha | `require('../errors').createError`: Córtex enlazaba al alias, scip-typescript a la función original; `const lookupFiles = require('./lookup-files')` de un `module.exports = function…` es una definición | fallo de Córtex | los alias de `require` remiten a la original; nodo propio solo si la exportación no tiene nombre (`declare_aliases`) |
| mocha | `var consoleLog = console.log`, `Object.prototype.toString` (funciones de la biblioteca estándar) | fallo de Córtex | `tsjs.builtin_function` |
| mocha | `static create() { return new Pool(); }` sin anotación y `let pool; … pool = Pool.create()` | fallo de Córtex | `tsjs.body_returns`, `assigned_type` |
| mocha | `progress.update(…)` hacia `Progress.prototype.update`: el miembro no tiene símbolo SCIP (0 de 610 llamadas a nombres que solo existen como miembros CommonJS llevan un símbolo del proyecto) | artefacto | no medible (`run.measure`, nodos de `member_scopes`) |
| jekyll | `File.join` enlazado a `Jekyll::LiquidRenderer::File` por nombre único (77 dependencias falsas) | fallo de Córtex | `rubytyped.RUBY_TOPLEVEL`: una constante del núcleo no se resuelve por nombre único |
| jekyll | `rescue … => e; e.message` enlazado a `LogAdapter#message` | fallo de Córtex | `rubytyped`: la variable de `rescue` tiene el tipo de la excepción |
| jekyll | `Jekyll.logger.info` (`def logger` sin `sig`) y `registers[:site].filter_cache` | artefacto (Sorbet: 0 de 233 y 0 de 186) | no medibles (`run.ruby_chained`) |
| jekyll, dapper, bat | `Utils::Platforms`, `SqlMapper.ITypeMap`: SCIP da como destino el primer archivo de un tipo definido en varios | regla | cualquiera de sus archivos (`run.spread_homes`) |
| jekyll | `Configuration[user_config].stringify_keys` (`Hash.[]` en una subclase devuelve la subclase) | artefacto | se deja (3 FP) |
| ktlint | `val ASTNode.prevLeaf: ASTNode?` (propiedades de extensión), extensiones tapadas por un `import` externo homónimo, `text.matches(…)` en un receptor implícito externo, `import …INDENT_SIZE_PROPERTY` | fallos de Córtex | `typed.ext_prop`, `kt_visible` en `extension`, `ext('?')`, `prop_imports` |
| ktlint | `KotlinLogging.logger {}.initKtLintKLogger()`, `findChildByType(RPAR).upsertWhitespaceBeforeMe(…)`: receptor que devuelve una API externa | fallo de Córtex | `typed.blind_extension` (extensión visible, única por nombre y aridad, sin miembros homónimos en el proyecto) |
| ktlint | `@SinceKtlint("0.39", EXPERIMENTAL)`: 0 de 155 anotaciones del proyecto con ocurrencia | artefacto (semanticdb-kotlinc) | no medibles (`run.kotlin_annotations`) |
| ktlint | `StandardRule(…),⏎ Rule.OfficialCodeStyle {` contado como constructor SAM | regla (fallo del benchmark) | `run.kotlin_before` |
| dapper | `NRT.cs` empieza por la marca BOM antes de `#if !NET5_0_OR_GREATER`: el polyfill no se descartaba | fallo de Córtex | `langs.PREPROC_RE` admite la BOM |
| shelf | `_Pipeline(…)` apunta a `_Pipeline#<constructor>` con el prefijo del paquete y la clase recuperada llevaba `local . .` | regla (fallo del benchmark) | `run.dart_privates` usa el prefijo del documento |
| httpie | `from .cli.nested_json import X` (el paquete reexporta) no creaba dependencia hacia `nested_json/__init__.py` | fallo de Córtex | `pyast`: también en imports relativos con módulo (no en `from . import x`) |

## Muestra de las categorías nuevas de «no medibles»

- **receptor de un método sin `sig` (Ruby)** — jekyll 173, thor 32, rack 21, sinatra 7 sitios; con un método del proyecto
  en SCIP 0 (59 a `Kernel`/`Object`, 174 sin ocurrencia). `command.rb:30 Jekyll.logger.error`, `site.rb:86
  Jekyll.logger.info`, `theme.rb:12 Jekyll.logger.debug`, `theme.rb:77 Jekyll.logger.error`.
- **receptor `x[k]` (Ruby)** — jekyll 95, thor 34, rack 41, sinatra 16; con método del proyecto 0. `filters.rb:422
  @context.registers[:site].filter_cache`, `drops/site_drop.rb:17 @obj.collections[key].docs`.
- **miembros CommonJS sin nombre (JS)** — mocha 365, express 106, moment 95, axios 44 llamadas a esos nombres: 264 con
  símbolo `local`, 289 sin ocurrencia, 57 externas, 0 del proyecto. `reporters/html.js:238 progress.update(percent).draw(ctx)`.
- **anotaciones de Kotlin** — ktlint 155 usos de `@SinceKtlint`/anotaciones del proyecto, 0 con ocurrencia; en
  ktlint, http4k, javalin y moshi ninguna de las ~660 anotaciones apunta a una clase del proyecto.

## Patrones restantes (después)

- **shelf**: parámetros de funciones anónimas pasadas a un parámetro con tipo función (`createMiddleware(responseHandler:
  (response) { … })`, 6 dependencias que faltan) y referencias en comentarios de documentación (`/// [Handler]`).
- **mocha**: parámetros tipados solo por JSDoc (`@param {BufferedWorkerPool} pool`), 5 FN.
- **dapper**: `SqlMapper.IMemberMap` como tipo de retorno de un tipo anidado, 2 dependencias.
- **hexo**: llamadas sobre uniones de dos tipos del proyecto (`renderer.compile` con `StoreFunction \| StoreSyncFunction`).
- **jekyll**: `Hash.[]` en una subclase (3 FP) y 46 definiciones (alias y métodos generados) sin nodo.
- **express**: el alias `var flatten = Array.prototype.flat` (ver arriba).

# Ronda 3 de ajuste · antes / después (histórico)

Generado: 2026-10-20. Los 11 repos de `split = "control2"` se midieron primero a ciegas (código y reglas de la ronda 2) y
después se usaron para ajustar el analizador y las reglas del benchmark (ahora `split = "ajuste3"`). **Antes** = medida a
ciegas; **después** = código y reglas actuales, con los índices SCIP reutilizados. «No medibles»: aristas de llamada
apartadas por un límite del indexador. El detalle de cada repo está en [RESULTS.md](RESULTS.md).

| repo | lenguaje | llamadas P | llamadas R | deps P | deps R | defs R | defs P | no medibles |
|---|---|---|---|---|---|---|---|---|
| rich | python | 99,8 → **99,8** | 93,1 → **97,8** | 100,0 → **100,0** | 99,8 → **99,8** | 92,3 → **100,0** | 99,2 → **99,9** | 0 → 0 |
| chi | go | 100,0 → **100,0** | 100,0 → **100,0** | 98,6 → **98,6** | 97,9 → **97,9** | 100,0 → **100,0** | 99,2 → **100,0** | 0 → 0 |
| class-validator | typescript | 100,0 → **100,0** | 98,5 → **99,8** | 100,0 → **100,0** | 89,8 → **100,0** | 99,7 → **100,0** | 99,7 → **100,0** | 0 → 0 |
| moment | javascript | 81,2 → **99,1** | 99,3 → **99,3** | 100,0 → **100,0** | 99,9 → **99,9** | 97,9 → **97,9** | 99,2 → **99,2** | 0 → 0 |
| thor | ruby | 85,3 → **98,8** | 91,2 → **99,8** | 82,8 → **97,9** | 77,8 → **97,9** | 99,1 → **100,0** | 100,0 → **100,0** | 31 → 145 |
| commons-lang | java | 98,9 → **98,9** | 99,2 → **99,2** | 98,2 → **98,2** | 99,4 → **99,4** | 99,8 → **99,8** | 100,0 → **100,0** | 0 → 0 |
| http4k | kotlin | 78,8 → **95,8** | 70,5 → **90,2** | 93,3 → **92,7** | 91,6 → **98,1** | 92,5 → **95,1** | 96,4 → **99,9** | 0 → 71 |
| walkdir | rust | 99,5 → **99,5** | 96,1 → **99,8** | 100,0 → **100,0** | 100,0 → **100,0** | 95,2 → **100,0** | 95,2 → **100,0** | 0 → 0 |
| path | dart | 99,3 → **99,4** | 91,8 → **99,4** | 97,0 → **97,1** | 94,1 → **100,0** | 100,0 → **100,0** | 98,3 → **98,3** | 0 → 0 |
| csv | php | 88,0 → **98,1** | 94,8 → **100,0** | 97,0 → **99,8** | 79,4 → **100,0** | 90,6 → **95,7** | 100,0 → **100,0** | 332 → 520 |
| markdig | csharp | 80,6 → **95,5** | 94,5 → **98,2** | 88,9 → **99,1** | 92,2 → **94,0** | 96,4 → **99,3** | 89,4 → **99,6** | 0 → 131 |

Objetivo: llamadas, dependencias y definiciones ≥ 90 % (P y R) en los 11 repos, sin empeorar los 25 de las rondas 1 y 2.
Se cumple en los 11; en los 25 anteriores ninguna métrica baja salvo dos décimas: httpx defs P 100 → 99,8 (un `def main`
de reserva en un `except ImportError` que tapa un import y que scip-python no define) y http4k deps P 93,3 → 92,7
(los `typealias` de Kotlin ahora son nodos; deps R sube de 91,6 a 98,1).

## Qué era artefacto del indexador y qué era fallo de Córtex

Cada categoría nueva de «no medibles» se comprobó con todos sus sitios en los índices (y una muestra de 10 a mano); la
muestra de Ruby está en `scip-r3/evidence-ruby.txt` del directorio de trabajo.

| repo | hallazgo | tipo | tratamiento |
|---|---|---|---|
| thor | `class Thor; class Option < Argument` (constante léxica), `x = X.new; x.m`, `Thor::Options.split` heredado, `self[k] = v`, `{a: metodo}`, `class << self; def included(base) base.extend(ClassMethods)`, `Struct.new(:a)`, clases homónimas anidadas, constantes como dependencia | fallos de Córtex | tipador de Ruby nuevo (`rubytyped.py`), `langs.ruby_index`, `ruby_struct_members`, claves de clases anidadas |
| thor (y rack, sinatra) | receptores que son parámetros sin firma (0 de 1146 se resuelven a un método del proyecto), `self.class` en un módulo (0 de 36), lectura `x[k]` (0 de 548 ocurrencias de `[]`), `self.class.new` → `Class#new` (0 de 7), métodos añadidos por ganchos `self.included` (0 de 223 desde fuera del módulo) | artefactos (Sorbet sin firmas) | no medibles (`run.ruby_untyped`, `ruby_param`, `ruby_hooked`) |
| thor | `klass.namespace` → `Object#namespace` (el `def` de nivel superior de `rake_compat.rb`, privado en `Object`) | artefacto | una referencia a `Object#m` con receptor explícito no cuenta |
| rack | `module_function :mime_type` define `<Class:Mime>#mime_type` en el símbolo `:mime_type` | artefacto | se proyecta sobre su `def` (`run.ruby_symbol_def`) |
| moment | `test('x', …)` con `export var test = QUnit.test` era una llamada al módulo | fallo de Córtex | referencia (`tsjs.link_calls`) |
| class-validator | `validate: (value, args) => args.constraints[0]` dentro de un objeto literal pasado a `ValidateBy`, `getFromContainer(Validator).validate()`, `metadatas.forEach(m => m.validateIf())`, campo `validateIf?: (…) => boolean` | fallos de Córtex | contexto de objetos literales, lecturas de propiedad, `generic_return`, elemento de colección (`tsjs`) |
| rich | funciones y clases anidadas sin nodo, `def` bajo `if`/`try`, `_Text = Text`, `x if c else y`, `TextType = Union[…]`, `__iter__`, anotación con un parámetro que tapa el módulo | fallos de Córtex | `pyast` (`declare_inner`, `flat_defs`, `type_alias`, `class_object`, `narrowing`) |
| rich, flask | scip-python da el mismo símbolo a funciones anidadas homónimas (`App#decorator().`) y solo define la primera `@overload` | artefactos | cada definición SCIP cuenta; el grupo `@overload` es una definición |
| path | `final Context context = createInternal();` sin tipo; `p.Context` (import con prefijo y reexportación) | fallos de Córtex | `darttyped.top_variables`, `prefixed` |
| walkdir | parámetros de clausura por la cota `F: FnMut(&DirEntry)`, `self.it` con `impl<P> … for Filter<IntoIter, P>`, `let (a, b) = (&x[0], &x[1])`, gemelos `#[cfg(windows)]` | fallos de Córtex | `rusttyped.fn_bound_param`, `impl_argument`, `langs.rust_cfg_off` |
| walkdir | rust-analyzer solo indexa la variante de `#[cfg]` activa en Linux | artefacto | ocurrencias en ítems `cfg` inactivos no se miden |
| csv | retorno `self`/`static` sin `@return`, enum/constante o `$x[0]` como receptor | artefacto (scip-php; 0 de 144, 0 de 34, 0 de 35) | no medibles (`PhpChains`, `php_untyped`) |
| csv | `@method`, `#[MapCell(…)]`, unión `SplFileObject\|Stream`, `use Exception;`, `$f()` | fallos de Córtex | `langs.php_magic_methods`, `phptyped` |
| csv | `SplFileObject\|Stream`: scip-php elige el primer miembro de la unión que declara el método | artefacto | se deja (~28 FP) |
| markdig | nombres genéricos sin ocurrencia (0 de ~1.700 en tres repos), tipos homónimos `Inlines/X#` (277 referencias), eventos con sufijo `#` | artefactos (scip-dotnet) | no medibles / un símbolo por definición / término |
| markdig | polyfills `#if !NET`, `delegate`, `ref partial struct`, `T` de `Base<T>`, `string[i]` | fallos de Córtex | `langs.dotnet_branch`, `csharp_fixups`, `cstyped.as_base` |
| http4k | sobrecargas de nivel superior en varios archivos con el mismo símbolo (148 referencias) | artefacto (semanticdb-kotlinc) | `run.shared_symbols` |
| http4k | `invoke` del companion y de valores invocables, constructor SAM de `fun interface`, `typealias`, lambdas que devuelven lambdas, `fold`, extensiones miembro, `override` que hereda los valores por defecto, objetos anidados invocables, visibilidad por paquete | fallos de Córtex | `typed` (`factory`, `invoker`, `as_function`, `kt_override`, `kt_visible`) |
| http4k | `Filter { … }` es una llamada; `#Companion#` es la clase | regla | `is_call`, `scip.qualified` |

## Muestra de las categorías nuevas de «no medibles» de Ruby

Sitios contados en thor/rack/sinatra; «con SCIP» = cuántos tienen una ocurrencia de un método definido en el proyecto en
el nombre llamado (sin contar el `Object#` de los `def` de nivel superior). 10 sitios de thor revisados a mano por
categoría (símbolo SCIP entre corchetes; vacío = ninguna ocurrencia):

- **parámetro sin firma** — thor 581, rack 349, sinatra 216 sitios; con SCIP 0. `thor.rb:13 name.nil?` [Kernel#nil?],
  `thor.rb:627 to_s` [Kernel#to_s], `actions/file_manipulation.rb:51 args.last` [Array#last], `base.rb:62 delete` [],
  `base.rb:679 to_s` [Kernel], `command.rb:105 public_methods` [Kernel], `group.rb:150 each` [Array#each],
  `parser/option.rb:69 downcase` [], `runner.rb:215 puts` [IO#puts], `shell/column_printer.rb:19 zero?` [].
- **método de un gancho `self.included`** — thor 223; con SCIP 0. `thor.rb:25 from_superclass`, `thor.rb:301
  print_table`, `thor.rb:538 invoke_command`, `actions.rb:174 say_status`, `actions/empty_directory.rb:36 merge`,
  `base.rb:63 merge`, `command.rb:146 handle_no_command_error`, `group.rb:162 class_options`, `runner.rb:182 group` [],
  `line_editor/basic.rb:16 print` [Kernel#print].
- **lectura `x[k]`** — thor 218, rack 240, sinatra 90; ocurrencias de `[]` en los tres índices: 0 (de `[]=`: 19).
  `thor.rb:55 options[:for]`, `thor.rb:613 map[meth]`, `actions/create_file.rb:64 config[:perm]`, `base.rb:78
  config[:current_command]`, `base.rb:819 options[:for]`, `parser/arguments.rb:16 args[Range.new(…)]`, `runner.rb:85
  options["as"]`, `runner.rb:177 options["substring"]`, `shell.rb:46 config[:shell]`, `rack/static.rb:147 response[1]`.
- **`self.class` en un módulo** — thor 36; con SCIP 0 (en clases, 13 de 15 sí se resuelven). `actions.rb:128
  source_paths_for_search`, `actions.rb:146 name`, `actions.rb:274 exit_on_failure?`, `base.rb:89 map`, `base.rb:92
  disable_required_check?`, `base.rb:111 arguments`, `invocation.rb:134 map`… (ninguna ocurrencia, ni siquiera de `class`).
- **`self.class.new`** — thor 1, rack 6; 6 → [Class#new], 1 sin ocurrencia, 0 → la clase.

## Patrones restantes (después)

- **rich**: llamadas sobre elementos de tuplas desempaquetadas (`for text, style, control in …`) y valores invocables (`_highlighter(…)`).
- **chi**: 3 dependencias por lectura de campo de interfaz (`rctx.Routes.Match`).
- **class-validator**: `customConstraintMetadata.instance.validate(…)` (tipo de un campo `any`).
- **moment**: `export var lang = deprecate(msg, fn)` — Córtex lo toma por función (envoltura con una función como argumento) y scip-typescript por término; 3 alias de funciones externas (`var mathAbs = Math.abs`).
- **thor**: 7 «falsos positivos» de locales asignadas con el resultado de un método sin firma (`option = class_options[name]`), que Córtex enlaza por nombre único.
- **http4k**: ~125 FN de inferencia genérica de Kotlin: parámetros de lambdas SAM genéricas (`LensSet { name, values, target -> … }`), `this@label` en expresiones `object`, operadores (`it + (…)` → `plus`).
- **csv / markdig**: ver CONTROL de cada fila arriba (`SplFileObject|Stream` en csv; `GetData`/`SetData` sobre `MarkdownObject` sin ocurrencia SCIP en markdig, ~20).

# Ronda 2 de ajuste · antes / después (histórico)

Generado: 2026-10-20. Los 11 repos se midieron primero a ciegas (un repo nuevo por lenguaje, elegido tras
la ronda 1, sin tocar `cortex_graph`) y después se usaron para ajustar el analizador y las reglas del benchmark. **Antes**
= medida a ciegas; **después** = código y reglas actuales, índices SCIP reutilizados salvo serilog (regenerado, ver
abajo). El detalle de los patrones restantes de cada repo está en [RESULTS.md](RESULTS.md).

| repo | lenguaje | llamadas P | llamadas R | deps P | deps R | defs R | defs P | no medibles |
|---|---|---|---|---|---|---|---|---|
| httpx | python | 99,5 → **99,5** | 93,9 → **95,4** | 81,6 → **100,0** | 96,0 → **96,7** | 97,9 → **97,9** | 100,0 → **100,0** | 0 |
| cobra | go | 100,0 → **100,0** | 99,9 → **99,9** | 100,0 → **100,0** | 86,7 → **100,0** | 99,7 → **99,7** | 100,0 → **100,0** | 0 |
| zod | typescript | 83,9 → **99,4** | 41,9 → **91,1** | 100,0 → **100,0** | 68,0 → **91,3** | 92,2 → **100,0** | 99,5 → **99,5** | 278 |
| express | javascript | 100,0 → **100,0** | 100,0 → **100,0** | 100,0 → **100,0** | 100,0 → **100,0** | 61,1 → **94,4** | 100,0 → **100,0** | 7 |
| sinatra | ruby | 76,2 → **91,8** | 87,7 → **99,1** | 87,5 → **100,0** | 100,0 → **100,0** | 94,1 → **99,7** | 96,4 → **100,0** | 41 |
| gson | java | 96,3 → **99,3** | 97,9 → **98,7** | 99,3 → **99,3** | 100,0 → **100,0** | 98,7 → **98,7** | 99,9 → **99,9** | 0 |
| moshi | kotlin | 95,8 → **99,7** | 95,5 → **98,1** | 100,0 → **100,0** | 100,0 → **100,0** | 99,0 → **99,0** | 100,0 → **100,0** | 0 |
| itertools | rust | 94,1 → **99,1** | 83,2 → **93,0** | 94,5 → **95,5** | 98,1 → **99,1** | 95,0 → **99,0** | 100,0 → **100,0** | 0 |
| yaml | dart | 93,7 → **98,5** | 97,7 → **100,0** | 97,6 → **97,6** | 100,0 → **100,0** | 93,1 → **96,4** | 86,3 → **96,4** | 0 |
| psr7 | php | 81,2 → **97,2** | 98,9 → **100,0** | 98,2 → **100,0** | 98,2 → **98,2** | 100,0 → **100,0** | 100,0 → **100,0** | 31 |
| serilog | csharp | 69,8 → **97,0** | 91,9 → **98,2** | 97,6 → **99,6** | 96,9 → **98,7** | 97,5 → **98,6** | 92,7 → **98,1** | 0 |

Objetivo de la ronda: llamadas, dependencias y definiciones ≥ 90 % (P y R) en los 11 repos, sin empeorar los 14 de la
ronda 1 (comparados en [RESULTS.md](RESULTS.md)). Se cumple en todos.

## Qué era artefacto del indexador y qué era fallo de Córtex

| repo | hallazgo | tipo | tratamiento |
|---|---|---|---|
| serilog | índice compilado sin `ImplicitUsings`, `Nullable` ni los `#if` de `net8.0`: `IEnumerable<T>` sin resolver, genéricos sin inferir, llamadas `Guard.AgainstNull(x)` ausentes | artefacto (construcción del índice) | `index_dotnet.py --implicit-usings`, `--nullable enable` y `--define FEATURE_*`; compila con 0 errores |
| serilog | `#if FEATURE_SPAN … #else … #endif` partiendo la cabecera de un método rompía el árbol sintáctico de Córtex y del benchmark | fallo de Córtex + regla | Córtex conserva la primera rama (`langs.blank_branches`); el benchmark, la rama con ocurrencias SCIP |
| serilog | atributos con argumentos (`[MessageTemplateFormatMethod("…")]`) | fallo de Córtex | instancian `XAttribute` (`cstyped.attribute_class`) |
| psr7 | `$this->uri->getPath()` con `/** @var UriInterface */` | fallo de Córtex | tipos PHPDoc (`phptyped.docblock`) |
| psr7 | `$request->withRequestTarget()` y demás llamadas sobre variables | artefacto (scip-php solo tipa `$this`; 0 de 214 resueltas) | no medibles |
| sinatra | `f(*args)`, `f(&block)`, receptores `@ivar` / método sin firma | artefacto (Sorbet; 0 de 84) | no medibles |
| sinatra | `include Helpers`, `alias_method`, `def self.x` junto a `def x`, `body=`/`<=>`, valores por defecto, `X.new` anidado, `a[k] = v` tomado como variable | fallos de Córtex | `langs.ruby_*` |
| sinatra | `require 'sinatra/main'` sin símbolo SCIP | artefacto | dependencia por ruta (`run.ruby_requires`) |
| httpx | `from ._api import *` nombrado `_api/__init__:` | artefacto (scip-python) | se completa con la sintaxis del import |
| httpx | `with Client() as c`, `list(reversed(x))`, uniones `URL \| str` | fallos de Córtex | `pyast.Entered`, `SAME_ELEMENTS`, uniones |
| cobra | constantes y funciones usadas como valor desde otro archivo del paquete | fallo de Córtex | `langs.go_ident` |
| zod | `namespace util`, `const s = ZodString.create`, `min = this.gte`, ternario de funciones, cadena `z.string().optional()` en módulo | fallos de Córtex | `tsjs` (namespaces, alias, `declare_aliases`) |
| zod | `z.string()` como `local` sin nombre; getters sin ámbito; `type OK` + `const OK` | artefactos (scip-typescript) | no medibles / ámbito por sintaxis / cuenta el valor |
| express | `exports.f`, `Clase.prototype.m`, `app.m = function`, `module.exports = X`, `require('./m').f` | fallo de Córtex | `tsjs.read_member_function`, `cjs_export`, alias |
| express | esos miembros no tienen nombre en SCIP | artefacto | ámbito por la asignación; no cuentan como definición |
| itertools | métodos de rasgo sobre genéricos acotados, campos genéricos, `let Self { … } = self`, alias `type`, ítems anidados, supertraits, variantes de enum como literal, `max_by` de std adivinado por nombre | fallos de Córtex | `rusttyped` (`field_type`, `dealias`, `literal_target`, `all_bounds`), `langs.nested_item`, `BUILTINS` |
| itertools | `Self { … }` apunta a `impl#[Tipo]` | artefacto | se proyecta sobre el tipo (`run.rust_self_type`) |
| yaml | constructor con lista de inicialización, `super._()`/`this._()`, funciones locales, operadores, `typedef` | fallos de Córtex | `langs.dart_body`, `dart_delegation`, `nested_item`, `dart_function_name` |
| yaml | constructores sin nombre como nodos aparte; privados como `local` | regla/artefacto | constructores sin nombre = su clase; privados recuperados |
| gson / moshi | `new X<>()` y `new X<T>() { … }` no contaban como llamada; variables capturadas por clases anónimas | regla + fallo de Córtex | genéricos saltados en Java/C#; `typed.anonymous_body` |

## Patrones restantes (después)

- **httpx**: FN llamadas: 8 × método · cadena a.b.x() / x().y() · otro archivo (`httpx/_auth.py:206`); 5 × método · calificado obj.x() · otro archivo (`httpx/_client.py:1480`). FP llamadas: 2 × SCIP lo resuelve fuera del proyecto (stdlib/dependencia) · method (`httpx/_models.py:1089`). Deps que faltan: 3 × primera referencia a callable (`httpx/_auth.py:158`). No medibles: 0.
- **cobra**: FN llamadas: 1 × constructor/clase · nombre suelto x() · otro archivo (`completions_test.go:3010`). FP llamadas: —. Deps que faltan: —. No medibles: 0.
- **zod**: FN llamadas: 24 × método · cadena a.b.x() / x().y() · mismo archivo (`src/types.ts:2236`); 21 × método · calificado obj.x() · mismo archivo (`src/types.ts:3146`). FP llamadas: 3 × SCIP ve una referencia, no una llamada (conversión, valor, tipo) · function (`src/benchmarks/realworld.ts:44`); 2 × SCIP ve una referencia, no una llamada (conversión, valor, tipo) · method (`src/__tests__/transformer.test.ts:11`). Deps que faltan: 10 × primera referencia a term (`src/__tests__/array.test.ts:63`). No medibles: 278.
- **express**: FN llamadas: —. FP llamadas: —. Deps que faltan: —. No medibles: 7.
- **sinatra**: FN llamadas: 2 × método · nombre suelto x() · mismo archivo (`sinatra/base.rb:269`). FP llamadas: 15 × sin referencia SCIP con ese nombre en el llamador · method (`sinatra/base.rb:980`); 4 × SCIP ve una referencia, no una llamada (conversión, valor, tipo) · method (`sinatra/base.rb:1150`). Deps que faltan: —. No medibles: 41.
- **gson**: FN llamadas: 6 × método · calificado obj.x() · otro archivo (`gson/src/main/java/com/google/gson/internal/bind/EnumTypeAdapter.java:85`); 4 × método · cadena a.b.x() / x().y() · mismo archivo (`gson/src/main/java/com/google/gson/TypeAdapter.java:314`). FP llamadas: 6 × SCIP lo resuelve fuera del proyecto (stdlib/dependencia) · method (`gson/src/main/java/com/google/gson/FieldAttributes.java:106`); 1 × sin referencia SCIP con ese nombre en el llamador · method (`gson/src/main/java/com/google/gson/stream/JsonWriter.java:527`). Deps que faltan: —. No medibles: 0.
- **moshi**: FN llamadas: 7 × método · calificado obj.x() · otro archivo (`moshi/src/main/java/com/squareup/moshi/ClassJsonAdapter.java:139`); 2 × método · calificado obj.x() · mismo archivo (`moshi/src/main/java/com/squareup/moshi/AdapterMethodsFactory.java:284`). FP llamadas: 1 × SCIP lo resuelve fuera del proyecto (stdlib/dependencia) · method (`moshi/src/main/java/com/squareup/moshi/Types.java:291`); 1 × sin referencia SCIP con ese nombre en el llamador · method (`moshi/src/main/java/com/squareup/moshi/internal/Util.java:114`). Deps que faltan: —. No medibles: 0.
- **itertools**: FN llamadas: 13 × método · calificado obj.x() · mismo archivo (`src/adaptors/map.rs:44`); 11 × método · cadena a.b.x() / x().y() · mismo archivo (`src/adaptors/map.rs:24`). FP llamadas: 2 × SCIP ve una referencia, no una llamada (conversión, valor, tipo) · class (`src/format.rs:160`); 1 × sin referencia SCIP con ese nombre en el llamador · class (`src/adaptors/mod.rs:682`). Deps que faltan: 1 × primera referencia a type (`src/lib.rs:93`). No medibles: 0.
- **yaml**: FN llamadas: —. FP llamadas: 3 × sin referencia SCIP con ese nombre en el llamador · class (`lib/src/scanner.dart:514`); 1 × SCIP lo resuelve fuera del proyecto (stdlib/dependencia) · class (`lib/src/equality.dart:22`). Deps que faltan: —. No medibles: 0.
- **psr7**: FN llamadas: —. FP llamadas: 3 × sin referencia SCIP con ese nombre en el llamador · method (`src/Utils.php:171`); 2 × SCIP lo resuelve fuera del proyecto (stdlib/dependencia) · method (`src/Utils.php:209`). Deps que faltan: 1 × primera referencia a type (`src/Message.php:141`). No medibles: 31.
- **serilog**: FN llamadas: 4 × método · cadena a.b.x() / x().y() · otro archivo (`src/Serilog/Capturing/PropertyBinder.cs:78`); 2 × método · calificado obj.x() · otro archivo (`src/Serilog/Capturing/DepthLimiter.cs:55`). FP llamadas: 6 × sin referencia SCIP con ese nombre en el llamador · method (`src/Serilog/Events/MessageTemplate.cs:53`); 5 × SCIP ve una referencia, no una llamada (conversión, valor, tipo) · class (`src/Serilog/Configuration/LoggerDestructuringConfiguration.cs:79`). Deps que faltan: 4 × primera referencia a type (`src/Serilog/Capturing/MessageTemplateProcessor.cs:21`). No medibles: 0.
