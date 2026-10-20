# Benchmark de precisión (SCIP)

Mide la calidad real del grafo de Córtex comparándolo con índices [SCIP](https://github.com/sourcegraph/scip) generados por indexadores con resolución de tipos (scip-python, scip-go, scip-typescript, scip-ruby, scip-java para Java y Kotlin, rust-analyzer, scip-dart, scip-php y scip-dotnet).

## Repos medidos

| repo | conjunto | lenguaje | estilo | commit fijado |
|---|---|---|---|---|
| flask 3.1.0 | ajuste ronda 1 | Python | biblioteca (`src/flask/`) | `ab81496` |
| healthchecks v5.0 | ajuste ronda 1 | Python | aplicación web Django | `47415f0` |
| gin v1.10.0 | ajuste ronda 1 | Go | biblioteca | `75ccf94` |
| miniflux v2.3.4 | ajuste ronda 1 | Go | servicio web (lector RSS) | `9b8db05` |
| excalidraw v0.18.0 | ajuste ronda 1 | TypeScript/TSX | monorepo React (app + paquetes, alias `@excalidraw/*`) | `817d8c5` |
| hono v4.13.13 | ajuste ronda 1 | TypeScript | framework web, tipos genéricos intensivos | `a0d8499` |
| axios v1.20.0 | ajuste ronda 1 | JavaScript (ESM) | biblioteca, `lib/` con tsconfig inferido | `84a9f3b` |
| rack v3.2.7 | ajuste ronda 1 | Ruby | biblioteca/middleware, `lib/` | `20bbc54` |
| jsoup 1.23.2 | ajuste ronda 1 | Java | biblioteca (parser HTML), `src/main/java/` | `fbc7775` |
| javalin 7.2.3 | ajuste ronda 1 | Kotlin + Java | framework web, `javalin/src/main/` | `8c12b9f` |
| ripgrep 15.2.0 | ajuste ronda 1 | Rust | workspace de 9 crates (CLI + bibliotecas), `crates/` | `e89fff8` |
| markdown 7.2.1 | ajuste ronda 1 | Dart | biblioteca, `lib/` | `a8288ca` |
| monolog 3.12.1 | ajuste ronda 1 | PHP | biblioteca con traits e interfaces, `src/` | `d7059e4` |
| stateless (rama dev, 2026-10-07) | ajuste ronda 1 | C# | biblioteca, clases parciales y anidadas, `src/Stateless/` | `3906001` |
| httpx 0.28.1 | ajuste ronda 2 | Python | cliente HTTP, `httpx/` | `26d48e0` |
| cobra v1.10.2 | ajuste ronda 2 | Go | biblioteca CLI | `88b30ab` |
| zod v3.23.8 | ajuste ronda 2 | TypeScript | validación de esquemas, `src/` (namespaces, alias, cadenas) | `ca42965` |
| express v5.2.1 | ajuste ronda 2 | JavaScript (CommonJS) | framework web, `lib/` | `dbac741` |
| sinatra v4.2.1 | ajuste ronda 2 | Ruby | framework web (DSL), `lib/` | `599a007` |
| gson 2.13.2 | ajuste ronda 2 | Java | biblioteca JSON, `gson/src/main/java/` | `686fad7` |
| moshi 1.15.0 | ajuste ronda 2 | Kotlin + Java | biblioteca JSON, `moshi/src/main/java/` | `491e66b` |
| itertools v0.14.0 | ajuste ronda 2 | Rust | biblioteca de iteradores (rasgos genéricos), `src/` | `a015a68` |
| yaml 3.1.2 | ajuste ronda 2 | Dart | parser YAML, `lib/` | `54e8284` |
| psr7 2.7.1 | ajuste ronda 2 | PHP | mensajes HTTP PSR-7, `src/` | `c2270ca` |
| serilog v4.1.0 | ajuste ronda 2 | C# | logging estructurado, `src/Serilog/` (multi-target con `#if`) | `467cfd8` |
| rich v15.0.0 | ajuste ronda 3 | Python | consola enriquecida, `rich/` | `6ac483c` |
| chi v5.5.0 | ajuste ronda 3 | Go | router HTTP | `3a33ba5` |
| class-validator v0.15.1 | ajuste ronda 3 | TypeScript | validación con decoradores, `src/` | `2e1a5c2` |
| moment 2.30.1 | ajuste ronda 3 | JavaScript (ESM) | fechas, `src/` (prototipo por asignación) | `485d9a7` |
| thor v1.5.0 | ajuste ronda 3 | Ruby | CLI (DSL de clase, ganchos `self.included`), `lib/` | `6a680f2` |
| commons-lang 3.20.0 | ajuste ronda 3 | Java | utilidades, `src/main/java/` | `598dfc1` |
| http4k 6.61.0.0 | ajuste ronda 3 | Kotlin | toolkit HTTP funcional, `core/core/src/main/` | `0c990a9` |
| walkdir 2.5.0 | ajuste ronda 3 | Rust | recorrido de directorios, `src/` (`#[cfg]` por plataforma) | `4f26be4` |
| path v1.9.0 | ajuste ronda 3 | Dart | rutas, `lib/` (import con prefijo y reexportación) | `115ea2a` |
| csv 9.28.0 | ajuste ronda 3 | PHP | lectura/escritura CSV, `src/` (atributos PHP 8) | `6582ace` |
| markdig 1.1.0 | ajuste ronda 3 | C# | parser Markdown, `src/Markdig/` | `bddaa55` |
| httpie 3.2.4 | ajuste ronda 4 | Python | cliente HTTP de línea de órdenes, `httpie/` | `2105caa` |
| gotify-server v3.1.1 | ajuste ronda 4 | Go | servidor de notificaciones | `e6361ca` |
| hexo v8.1.2 | ajuste ronda 4 | TypeScript | generador de sitios, `lib/` (`export =`, `require` y parámetros `this`) | `c3a7bef` |
| mocha v9.2.2 | ajuste ronda 4 | JavaScript (CommonJS) | framework de pruebas, `lib/` | `24b5243` |
| jekyll v4.4.1 | ajuste ronda 4 | Ruby | generador de sitios, `lib/` | `1f319fb` |
| zxing 3.5.4 | ajuste ronda 4 | Java | códigos de barras, `core/src/main/java/` | `f651b0a` |
| ktlint 1.8.0 | ajuste ronda 4 | Kotlin | linter (extensiones sobre `ASTNode`), cinco módulos | `c26a4ff` |
| bat v0.26.1 | ajuste ronda 4 | Rust | `cat` con resaltado, `src/` | `979ba22` |
| shelf (main, 2026-10-20) | ajuste ronda 4 | Dart | middleware HTTP, `pkgs/shelf/lib/` | `b66665b` |
| slim 4.15.3 | ajuste ronda 4 | PHP | microframework, `Slim/` | `3675bf6` |
| dapper 2.1.89 | ajuste ronda 4 | C# | micro-ORM, `Dapper/` (clases parciales) | `eb47546` |
| click 8.5.0 | ajuste ronda 5 | Python | biblioteca de línea de órdenes, `src/click/` (bases genéricas `ParamType[T]`) | `8b19813` |
| starlette 1.9.0 | ajuste ronda 5 | Python | framework ASGI, `starlette/` | `1840c9d` |
| immer v11.2.2 | ajuste ronda 5 | TypeScript | estado inmutable, `src/` (uniones de tipos del proyecto, barril `internal.ts`) | `313f09c` |
| fastify v5.12.7 | ajuste ronda 5 | JavaScript (CommonJS) | framework web, `lib/` | `9f40003` |
| echo v5.4.0 | ajuste ronda 5 | Go | framework web | `fc41009` |
| commons-io 2.22.0 | ajuste ronda 5 | Java | biblioteca de E/S, `src/main/java/` | `c14acc1` |
| exposed 0.61.0 | ajuste ronda 5 | Kotlin | DSL y ORM de SQL, `exposed-core/src/main/` | `1c8b114` |
| liquid v5.13.0 | ajuste ronda 5 | Ruby | lenguaje de plantillas, `lib/` | `7a5e45f` |
| twig v3.30.0 | ajuste ronda 5 | PHP | motor de plantillas, `src/` | `8c73707` |
| polly 8.8.0 | ajuste ronda 5 | C# | resiliencia, `src/Polly.Core/` (clases parciales y genéricas, `global using`) | `9ad5ae9` |
| fd v10.5.0 | ajuste ronda 5 | Rust | búsqueda de archivos, `src/` | `4f81778` |
| collection (main, 2026-10-20) | ajuste ronda 5 | Dart | colecciones, `pkgs/collection/lib/` | `5283f88` |
| marshmallow 4.3.1 | ajuste ronda 6 | Python | serialización, `src/marshmallow/` (raíz de fuentes `src/`) | `c7b559a` |
| rq v2.12 | ajuste ronda 6 | Python | colas de trabajos sobre Redis, `rq/` | `aa76e68` |
| ioredis v6.0.0 | ajuste ronda 6 | TypeScript | cliente de Redis, `lib/` | `8ed2946` |
| mongoose 9.11.2 | ajuste ronda 6 | JavaScript (CommonJS) | ODM de MongoDB, `lib/` | `a477fca` |
| afero v1.15.0 | ajuste ronda 6 | Go | sistemas de archivos | `18d690e` |
| commons-codec 1.23.0 | ajuste ronda 6 | Java | codificadores, `src/main/java/` | `f442c70` |
| hoplite v3.0.4 | ajuste ronda 6 | Kotlin | configuración, `hoplite-core/src/main/` (extensiones genéricas `fun <A> A.valid()`) | `14112f3` |
| faraday v2.15.0 | ajuste ronda 6 | Ruby | cliente HTTP, `lib/` (`Forwardable`, `Struct.new … do`) | `af2db2d` |
| flysystem 3.36.0 | ajuste ronda 6 | PHP | sistemas de archivos, `src/` | `f7fb152` |
| flurl (master, 2025-01-01) | ajuste ronda 6 | C# | cliente HTTP, `src/Flurl/` y `src/Flurl.Http/` | `36a3fa2` |
| indexmap 2.14.2 | ajuste ronda 6 | Rust | tabla hash ordenada, `src/` | `17334ef` |
| rxdart 0.28.0 | ajuste ronda 6 | Dart | extensiones de `Stream`, `packages/rxdart/lib/` | `6852efa` |
| gunicorn 26.2.2 (main, 2026-09-06) | ajuste ronda 7 | Python | servidor WSGI/ASGI, `gunicorn/` | `afc7d2f` |
| mkdocs (master, 2025-10-20) | ajuste ronda 7 | Python | generador de sitios, `mkdocs/` (configuración con descriptores genéricos) | `2862536` |
| npm-check-updates (main, 2026-10-10) | ajuste ronda 7 | TypeScript | aplicación de línea de órdenes, `src/` | `161014e` |
| eleventy (main, 2026-10-16) | ajuste ronda 7 | JavaScript (ESM) | generador de sitios, `src/` | `8ab5037` |
| dive (main, 2025-05-16) | ajuste ronda 7 | Go | aplicación de terminal (imágenes de contenedores) | `d6c6919` |
| moquette (main, 2026-10-10) | ajuste ronda 7 | Java | broker MQTT, `broker/src/main/java/` | `396737b` |
| ktorm (main, 2026-06-20) | ajuste ronda 7 | Kotlin | ORM, `ktorm-core/src/main/` | `1f0fd02` |
| lobsters (master, 2026-10-20) | ajuste ronda 7 | Ruby | aplicación Rails, `app/` | `559e00c` |
| bookstack (development, 2026-10-18) | ajuste ronda 7 | PHP | aplicación Laravel, `app/` | `045c6a9` |
| eShopOnWeb (main, 2025-01-13) | ajuste ronda 7 | C# | aplicación ASP.NET Core, `src/ApplicationCore`, `Infrastructure`, `Web`, `BlazorShared` | `4da8212` |
| xh 0.26.2 (master, 2026-09-05) | ajuste ronda 7 | Rust | cliente HTTP de línea de órdenes, `src/` | `2404ace` |
| melos (main, 2026-10-19) | ajuste ronda 7 | Dart | herramienta de monorepos, `packages/melos/lib/` (partes `part of`) | `696c66e` |

Los repos de «ajuste ronda 2» se midieron primero a ciegas (`split = "control"`) y después se usaron para ajustar el
analizador (`split = "ajuste2"`); los de «ajuste ronda 3», igual (`split = "control2"` → `"ajuste3"`, informe en
`results/CONTROL.md`); los de «ajuste ronda 4», igual (`split = "control3"` → `"ajuste4"`), y los de «ajuste ronda 5»
(`split = "control4"` → `"ajuste5"`), los de «ajuste ronda 6» (`split = "control5"` → `"ajuste6"`) y los de «ajuste
ronda 7» (`split = "control6"` → `"ajuste7"`; moquette no se pudo medir a ciegas: `analyze()` fallaba en los puentes, y
su «antes» es el código de la ronda 6 con ese fallo corregido). Los de `split = "control7"` son un conjunto ciego aparte:
no se miden con los oficiales.

Ningún repo necesitó `npm install`: los índices TS/JS se generan sin `node_modules` (los tipos externos quedan como `any`; SCIP pierde esas referencias y la medida se limita a símbolos del propio repo).

## Qué mide

Solo cuentan los archivos presentes en el índice SCIP (y dentro de `scope`, si el repo lo define).

| métrica | verdad de referencia (SCIP) | lado Córtex |
|---|---|---|
| dependencias entre archivos | A → B si A referencia un símbolo definido en B | cualquier arista entre nodos de A y B salvo `contains`/`cochange` y los flujos semánticos (`http`, `rpc`, `handles`, `env`, `data`, `event`, `depends`), que no son referencias de símbolo |
| llamadas | ocurrencia de función/método/clase seguida de `(`, atribuida al ámbito (`enclosing_range`) más interno | aristas `call` y `tests` |
| definiciones | funciones, métodos y tipos definidos | nodos `function`/`method`/`class` del mismo archivo y nombre (±3 líneas) |

Los símbolos SCIP se proyectan sobre claves de Córtex por archivo + línea (`line`..`end`, o el símbolo anterior más cercano si no hay `end`); si el nombre calificado SCIP (`Externa.Interna.metodo`) termina en el nombre de un nodo de Córtex (`Interna.metodo`), se usa ese nodo. Las llamadas a métodos de interfaz que Córtex resuelve a una implementación (relación `is_implementation`) no cuentan como falso positivo. La fila «modo preciso» repite la medida tras `scip.apply_scip`.

Reglas comunes a todos los indexadores:

- **Sobrecargas**: Córtex representa con un solo nodo los métodos homónimos de una clase; las sobrecargas SCIP de un mismo nombre (`m().`, `m(+1).`, …) cuentan como una sola definición.
- **Constructores** (`<init>`, `.ctor`, `<constructor>`): una llamada al constructor es una llamada a la clase, y los constructores no se cuentan como definiciones aparte.
- **Tipos definidos en varios archivos** (clases parciales de C#, módulos reabiertos de Ruby): no crean dependencia entre esos archivos por su nombre.

### Normalización por indexador

- **scip-typescript**: `new X()` apunta al constructor (`X#<constructor>().`) y se proyecta sobre la clase `X`, igual que `X()` en Python. Las constantes y propiedades cuyo valor es una función (`const f = () => …`, `json = (…) => …`) son términos en SCIP; cuentan como invocables si la firma SCIP es un tipo función (incluidas firmas de llamada `{ (…): T }` y `*ExoticComponent`/`FC`) o si el inicializador es sintácticamente una función; su ámbito se toma del árbol sintáctico porque SCIP no emite `enclosing_range` para ellas. Cuentan como llamada `f<T>(…)` y `<Componente …>` en archivos JSX. El módulo citado en `import … from './x'` es una dependencia de archivo (símbolo de módulo). Se ignoran los miembros de tipos literales anónimos (`typeLiteral`). Getters/setters y `constructor` se comparan por nombre normalizado.
- **scip-ruby** (`--typed true`): toda referencia a un método es una llamada (Ruby no exige paréntesis) y `X.new` es una llamada a la clase `X`. Los ámbitos salen del árbol sintáctico (`def`, `class`, `module`). Un módulo reabierto (`module Rack` en cada archivo) no crea dependencia hacia el archivo que lo abrió primero.
- **scip-java (Java y Kotlin, SemanticDB)**: Kotlin no emite `enclosing_range`; sus ámbitos salen del árbol sintáctico (`fun`, `class`, `object`, `companion object`, constructores secundarios, `get`/`set`). Una definición cuya ocurrencia no deletrea su nombre en el código la genera el compilador (getters/setters de propiedades, `componentN`/`copy` de `data class`, `<anonymous object at N>`, `Companion` implícito) y no cuenta. En Kotlin también es llamada `f { … }` (lambda final) y `f<T>(…)`.
- **rust-analyzer**: sin `enclosing_range`; ámbitos por sintaxis (`fn`, `struct`, `enum`, `union`, `trait`). `impl#[Tipo][Rasgo]metodo().` se proyecta sobre `Tipo.metodo`. Las variantes de enum (`Enum#Variante#`) y los tipos asociados de un `impl` son términos, no tipos. Decidido por el árbol sintáctico: las ocurrencias dentro de `macro_rules!` (plantillas) y de `pub(crate)` se ignoran; las definiciones generadas dentro de una invocación de macro no cuentan; el nombre de un literal struct (`Tipo { … }`) es la instanciación y cuenta como llamada, como `new Tipo()`. Un módulo de archivo (`mod x;`, `use crate::x;`) es dependencia solo cuando es el último tramo de la ruta (`crate::x::Y` depende del archivo de `Y`, no de los intermedios).
- **scip-dart**: el símbolo del archivo (`` `x.dart`/ ``) es un módulo y los constructores `<constructor>` se proyectan sobre la clase. scip-dart exporta los miembros privados de librería (`_x`) como símbolos `local`; si la definición es el nombre de una función, método o clase, se recuperan como símbolos del documento. Tampoco emite ocurrencias para `import`/`export`: la dependencia que declaran se toma de la URI (relativa o `package:` del propio paquete).
- **scip-php**: sin `enclosing_range`; ámbitos por sintaxis (métodos, funciones, clases, interfaces, traits, enums). `new X` sin paréntesis también es instanciación.
- **scip-dotnet**: sin `enclosing_range`; ámbitos por sintaxis (métodos, constructores, funciones locales, operadores y tipos). scip-dotnet no emite ocurrencia para `: base(…)`: la llamada al constructor base sale del árbol sintáctico, con la clase base tomada del símbolo SCIP del primer tipo de la lista de bases (si se define como `class`). El índice se compila con un juego concreto de símbolos, así que de cada `#if … #else … #endif` solo una rama tiene ocurrencias: el árbol sintáctico del benchmark se construye con esa rama (la que tiene ocurrencias SCIP; la primera si ninguna).
- **Genéricos en la instanciación** (Java, C#, Scala, además de TS, Kotlin y Dart): `new Caja<>()`, `new Adaptador<T>() { … }` y `Metodo<T>(…)` son llamadas; los argumentos de tipo se saltan antes de buscar el `(`.
- **scip-python (imports relativos)**: scip-python nombra el módulo de `from ._api import *` o `from . import json` solo con su último tramo (`_api/__init__:`), sin el paquete, y la referencia no coincide con la definición del módulo; se completa con la sintaxis del import y el nombre del módulo que importa.
- **scip-typescript (más)**: los getters/setters no tienen `enclosing_range` y su ámbito sale del árbol sintáctico. Una declaración que es a la vez tipo y valor (`type OK<T>` y `const OK = …`) emite los dos símbolos en la misma posición; en una llamada cuenta el valor, no el tipo. Una constante o propiedad cuyo valor es otro nombre (`const s = Clase.crear`, `min = this.gte`) es invocable si ese nombre es una función según SCIP. Los miembros asignados en CommonJS (`exports.f = function`, `Clase.prototype.m = …`, `obj.m = () => …`) no tienen nombre en scip-typescript (símbolo `local` o ninguno): su ámbito sale de la asignación y no cuentan como definición.
- **scip-ruby (más)**: `require`, `require_relative`, `load` y `autoload` no tienen ocurrencia; la dependencia sale de la ruta (relativa al archivo con `require_relative`, a la raíz medida —la del `$LOAD_PATH`— en el resto). La clase singleton `<Class:X>` que abre `class << self` no es una definición propia.
- **rust-analyzer (más)**: `Self { … }` y `Self(…)` apuntan al bloque `impl#[Tipo]`, no al tipo; se proyectan sobre el tipo implementado.
- **scip-dart (más)**: los constructores sin nombre (`A(…)`, `factory A(…)`) son la clase: no cuentan como definición y llamarlos es llamar a la clase (también en la predicción de Córtex). Los constructores con nombre son miembros con ese nombre (`Element.text(…)` → `Element#text().`); los privados (`A._(…)`), que scip-dart deja como `local`, se recuperan igual.
- **Varias definiciones de un mismo símbolo** (módulos de Ruby reabiertos, clases parciales de C#, funciones anidadas homónimas que scip-python nombra igual —`App#decorator().` en varios métodos de `App`—, definiciones bajo `if`/`else`): cuenta cada ocurrencia de definición SCIP; el símbolo se encuentra si un nodo de Córtex está a ±3 líneas de cualquiera de ellas.
- **scip-python (sobrecargas)**: de un grupo `@overload def f` + implementación, scip-python solo emite la definición de la primera; las líneas del resto del grupo (sacadas del árbol sintáctico) son la misma definición.
- **scip-ruby (ronda 3)**: `module_function :m` (y `private_class_method :m`) sitúa la definición de la copia de clase `<Class:M>#m` en el símbolo `:m`; se proyecta sobre su `def m`. Sorbet resuelve un receptor sin tipo contra `Object` (un `def` de nivel superior es un método privado de `Object`): una referencia a `Object#m` con receptor explícito (`klass.namespace`) no es una llamada posible en Ruby y no se cuenta.
- **scip-dotnet (ronda 3)**: nombra los tipos solo con el último tramo del espacio de nombres (`Inlines/LinkInlineRenderer#` para tres clases de `Html`, `Normalize` y `Roundtrip`), y semanticdb-kotlinc numera las sobrecargas de nivel superior por archivo (`paquete/map().` para extensiones de tres archivos): cuando un símbolo tiene varias definiciones que no son una clase parcial, cada definición recibe su propio símbolo y las referencias ambiguas dejan de ser verdad de referencia (la arista de Córtex en ese sitio no se puntúa; 277 referencias en markdig, 148 en http4k, 13 en javalin). Los `event` de C# llevan sufijo de tipo `#` y se tratan como términos. Un `new X { … }` sin paréntesis es instanciación, y en Kotlin `Tipo { … }` (constructor SAM de una `fun interface`) es una llamada salvo tras `:`, `,`, `->`, `is`, `as`, `class`, `object` o `@`. `operator X(` es una declaración. Los miembros `#Companion#` de Kotlin son de la clase, y en C# una implementación explícita `IFoo.Bar` es el método `Bar`.
- **rust-analyzer (ronda 3)**: solo indexa la variante de `#[cfg]` activa en el entorno del índice (Linux x86-64); las ocurrencias dentro de un ítem con `#[cfg(windows)]` (o cualquier `cfg` falso en Linux) no tienen ámbito y no se miden.
- **scip-typescript (ronda 4)**: en un archivo `.ts`, `require('./m')` es la función `require` de Node y devuelve `any`; scip-typescript no emite la ocurrencia del módulo (0 de 91 en hexo, frente a 180 de 186 en los `.js` de mocha y express): la dependencia sale de la ruta, resuelta como la resuelve TypeScript (`./m.ts`, `./m/index.ts`…).
- **Tipos definidos en varios archivos (ronda 4)**: una referencia a una clase parcial de C# o a un módulo reabierto de Ruby (`SqlMapper.ITypeMap`, `Utils::Platforms`) depende de cualquiera de los archivos que la definen, no solo del primero que lista el índice; si Córtex depende de otro de ellos, la dependencia de referencia pasa a ese.
- **Kotlin y Dart (ronda 4)**: en Kotlin, un tipo al principio de línea tras una lista de supertipos partida (`StandardRule(…),⏎ Rule.OfficialCodeStyle {`) es un supertipo, no un constructor SAM: lo que precede al nombre se mira sin su calificación y desde la línea anterior. En Dart, las clases privadas recuperadas de símbolos `local` reciben el prefijo del propio documento, para que coincidan con el símbolo de su constructor (`` _Pipeline#`<constructor>`(). ``).
- **Kotlin (ronda 5)**: el árbol sintáctico del benchmark se construye con las mismas correcciones de gramática que
  Córtex (`where` como variable al principio de una sentencia, anotaciones de un accesor, bytes NUL), que rompían el
  resto del archivo (11 de 79 archivos medidos en exposed); y como los nodos de Córtex empiezan en la declaración y no en
  sus anotaciones, una anotación no medible también se aparta en la línea de la declaración anotada. semanticdb-kotlinc
  nombra un miembro heredado con el tipo del receptor (`DeleteStatement#execute().` cuando `execute` solo se define en
  `Statement`): esa referencia sin definición se proyecta sobre la del supertipo más cercano (291 referencias en exposed,
  114 en http4k, 32 en javalin; ninguna en los índices de Java). Los supertipos son las relaciones del índice que nombra
  la cabecera de la clase: en un tipo, semanticdb-kotlinc a veces lista sus subtipos (`Filter#` → `CacheFilter#`).
- **scip-typescript (ronda 5)**: `module.exports = { f }` y `export default { f, g: h }` definen la propiedad como un
  símbolo «meta» (`f0:`) y referencian la función en la posición del valor; una llamada a la propiedad es una llamada a
  la función (53 propiedades y 37 referencias en fastify, 20 y 33 en mocha, 9 y 39 en axios).
- **scip-dotnet (ronda 5)**: un tipo del proyecto escrito solo con argumentos de tipo (`Func<FallbackActionArguments<T>,
  …>`) no tiene ocurrencia (0 de 415 nombres genéricos de tipos del proyecto en polly, 0 de 127 en markdig, 0 de 144 en
  stateless, frente a 1151 de 1165 de los mismos tipos sin argumentos en polly): la dependencia de tipo de Córtex hacia
  el archivo que lo define no se puntúa. Los métodos que scip-dotnet define bajo `` `<invalid-global-code>` `` (no supo
  nombrar su tipo) no reciben referencias (0 de 48 llamadas escritas en polly, 1 de 76 en markdig): la arista de Córtex
  hacia ellos no se puntúa.
- **scip-dart (ronda 5)**: un constructor con nombre de una clase privada (`_GrowableBoolList._withCapacity`) se
  recupera con el símbolo ya recuperado de su clase.
- **scip-python (ronda 6)**: con una raíz de fuentes (`src/marshmallow/`), la definición de un módulo lleva la ruta
  desde la raíz del proyecto (`` `src.marshmallow.exceptions`/__init__: ``) y la referencia el nombre importado
  (`` `marshmallow.exceptions`/__init__: ``); un submódulo importado como miembro (`from marshmallow import fields as
  ma_fields`) lleva solo su último tramo en el import y en cada uso (`fields/__init__:`). Una referencia del propio
  proyecto sin definición se enlaza con el único módulo definido cuyo nombre termina en ella; si es la ruta de un import
  absoluto, solo quitando carpetas que no son paquete, y un `import x` externo homónimo de un subpaquete (`import
  apprise` dentro de `hc/integrations/apprise/`) no se enlaza ni en sus usos. Referencias del proyecto a módulos sin
  definición antes → después: marshmallow 174 → 11, click 119 → 43, rich 54 → 27, httpx 26 → 11, rq 74 → 59, flask 90 → 78,
  httpie 68 → 67; healthchecks 966 y starlette 45 sin cambio (los restantes son paquetes externos no instalados).
- **scip-typescript (ronda 6)**: una variable con firma `Function` cuyo valor es una llamada (`var stackFilter =
  utils.stackTraceFilter()`, el resultado de una fábrica CommonJS que scip-typescript no tipa mejor) también es invocable;
  un campo `target: Function` sin valor no. Son 2 variables con 2 referencias en los 13 índices TS/JS (mocha
  `stackFilter`, mongoose `ActiveRoster`).
- **Línea de una definición (ronda 6)**: el nodo de Córtex empieza en sus anotaciones o atributos (los puentes leen
  `@Query("…")` dentro de su rango) y guarda en `decl` la línea de la declaración; el benchmark mide la definición en
  `decl`, como en la ronda 5.

### Llamadas no medibles

Hay llamadas que un indexador no resuelve nunca, comprobado en su código y en los índices; ahí no hay verdad de referencia. La arista de Córtex desde el mismo llamador hacia ese nombre no se puntúa (ni acierto ni fallo) y `results.json` cuenta cuántas se apartan (`unmeasured_ignored`); una dependencia entre archivos que solo se apoya en ellas tampoco cuenta como falso positivo.

- **scip-ruby** (Sorbet sin firmas, `--typed true`): `f(*args)`, `f(&bloque)` y `f(...)` se convierten en llamadas «mágicas» sin ocurrencia del método (0 de 84 en sinatra y 0 de 35 en rack la tienen). Un receptor que es una variable de instancia, de clase o global, o un método sin firma llamado sin receptor (`request.path`, también al principio de una cadena) es `T.untyped`: en sinatra y rack, 1 de 128 y 1 de 41 llamadas con receptor «método sin receptor» y 0 de 238 con receptor `@ivar` se resuelven a un método del proyecto.
- **scip-ruby (ronda 3)**, comprobado en thor, rack y sinatra (`bench/results/CONTROL.md` tiene la muestra de cada categoría):
  un parámetro del método o del bloque que no se reasigna antes también es `T.untyped` sin firma (0 de 1146 llamadas sobre
  un parámetro se resuelven a un método del proyecto; solo a `Kernel`, `Array`, `Hash`… o al `Object#` de un `def` de nivel
  superior); `self.class` dentro de un método de un módulo no tiene tipo (0 de 36); la lectura indexada `x[k]` no emite
  ocurrencia del método `[]` (0 de 548; la escritura `x[k] = v` sí la emite); `self.class.new` se resuelve a `Class#new`,
  nunca a la clase (0 de 7); y los métodos de un módulo que añade un gancho `self.included`/`extended`/`inherited`
  (`base.extend(ClassMethods)`, `base.send(:include, Shell)`), porque Sorbet no ejecuta el gancho: 0 de 223 llamadas desde
  fuera del módulo se resuelven a ellos (66 desde dentro sí).
- **scip-php (ronda 3)**: solo da tipo a nombres de clase escritos completos; un retorno nativo `self`/`static` sin `@return` deja sin tipo la cadena (0 de 144 llamadas encadenadas en csv; las 8 con `@return $this` de monolog sí se resuelven), igual que un caso de enum o constante como receptor (`Bom::Utf8->m()`, 0 de 34) y una variable indexada (`$x[0]->m()`, 0 de 35; `$this->streams[…]` sí, 3 de 3, y no se aparta).
- **scip-dotnet 0.2.14 (ronda 3)**: no emite ocurrencia para ningún nombre con argumentos de tipo (`M<T>()`, `new Caja<T>()`, `: base(…)` hacia `Base<T>`): 0 de ~620 en markdig, 0 de ~240 en serilog, 0 de ~860 en stateless. Esas llamadas no se miden, y en archivos `.cs` una dependencia que solo se apoya en ellas (o en sus `using`) no cuenta como falso positivo.
- **scip-ruby (ronda 4)**: un receptor que es el resultado de un método del proyecto sin `sig` (`Jekyll.logger.info`) o de una lectura indexada (`context.registers[:site].filter_cache`) es `T.untyped`: 0 de 233 y 0 de 186 llamadas así en jekyll, thor, rack y sinatra se resuelven a un método del proyecto (`X.new` sí tiene tipo y se mide).
- **scip-typescript (ronda 4)**: los miembros CommonJS sin nombre en SCIP (`Clase.prototype.m = function…`, `exports.f = …`) no tienen símbolo, así que ninguna llamada puede apuntarles: 0 de 610 llamadas a nombres que solo existen como miembros asignados (mocha, express, moment y axios) llevan un símbolo del proyecto (264 `local`, 289 sin ocurrencia, 57 externos). La arista de Córtex hacia uno de esos nodos no se puntúa.
- **semanticdb-kotlinc (ronda 4)**: no emite ocurrencia para el nombre de una anotación (`@SinceKtlint("0.39", EXPERIMENTAL)`): 0 de 155 usos de anotaciones del proyecto en ktlint (ninguna de las ~660 anotaciones de ktlint, http4k, javalin y moshi apunta a una clase del proyecto). La instanciación que Córtex ve ahí no se mide.
- **scip-ruby (ronda 5)**: una variable local asignada (antes, en el mismo método) solo con valores sin tipo para Sorbet
  —el resultado de un método del proyecto sin `sig` o de una llamada sobre un receptor sin tipo— también es
  `T.untyped`: `p = @parse_context.new_parser(lhs); p.consume(:id)`. 0 de 613 llamadas sobre esas variables se
  resuelven a un método del proyecto (liquid 200, jekyll 111, thor 72, rack 193, sinatra 37).
- **scip-dart (ronda 5)**: una llamada a un miembro privado (`_bubbleDown()`) cuyo símbolo `local` no es el de ninguna
  definición del documento no enlaza con su definición (34 de 216 llamadas a privados en collection; 0 en shelf, path,
  yaml y markdown); la arista de Córtex desde ese llamador hacia ese nombre no se puntúa.
- **scip-php**: su `Types::type()` solo da tipo a `$this` entre las variables, así que `$x->m()` o una cadena que empieza en `$x` no tiene ocurrencia (0 de 214 en psr7, 0 de 173 en monolog).
- **scip-php (ronda 7)**: nombra una función solo si está cargada (`function_exists`) o en los stubs de PhpStorm, y
  `index_php.py` vacía las listas `autoload.files` para no ejecutar código del repo: las funciones del proyecto
  (`app/App/helpers.php` de bookstack) no tienen definición ni ocurrencias, y tampoco lo que se llama sobre su resultado
  (`user()->can(…)`). En los 7 índices PHP: 0 de 83 funciones con definición SCIP; bookstack, 388 llamadas a sus 6
  funciones y 793 llamadas sobre su resultado, ninguna con ocurrencia; twig, 19 llamadas a sus 65 funciones, ninguna. Las
  homónimas de una función de PHP (`function error_log` que una prueba de monolog define para sustituirla) sí se miden:
  sus llamadas llevan el símbolo de PHP. La arista de Córtex hacia una función así no se puntúa y su nodo no cuenta como
  definición de más.
- **scip-typescript**: cuando no sabe nombrar el destino emite un símbolo `local` sin definición en el documento (`z.string()` a través de `export { stringType as string }`, `require('./m').f` de CommonJS). El nombre escrito se traduce a los símbolos que SCIP sí asocia a ese nombre en un `export`.
- Documentos duplicados en el índice (proyectos TS con `references`) se cuentan una vez.

## Uso

```sh
cd analyzer
W=/ruta/grande/cortex-bench
.venv/bin/python ../bench/run.py --work $W --tools $W/tools          # todos los repos de repos.toml (salvo skip = true)
.venv/bin/python ../bench/run.py --work $W --only jsoup --reuse      # reutiliza el índice ya generado
.venv/bin/python ../bench/run.py --index gin=/ruta/gin.scip          # índice propio, sin ejecutar el indexador
```

- `--work` (o `CORTEX_BENCH_WORK`, por defecto `~/.cache/cortex-bench`): clones, índices, cachés (Go, coursier, NuGet, Composer) y carpetas de compilación (~1,5 GB con todos los repos, sin contar `--tools`). Nunca dentro del repo; si el disco del sistema va justo, apúntalo a otro volumen.
- `--tools` (o `CORTEX_BENCH_TOOLS`, por defecto `<work>/tools`): carpeta con `bin/` (scip-go, scip-ruby) y `node_modules/.bin` (scip-python, scip-typescript), que se anteponen al `PATH`, y las subcarpetas `jvm/`, `rust/`, `dart/`, `php/` y `dotnet/` (≈2,5 GB en total).
- Marcadores de `repos.toml`: `{src}`, `{index}`, `{work}`, `{tools}`, `{python}` (el intérprete que ejecuta `run.py`) y `{bench}` (esta carpeta).
- Salida: `bench/results/results.json` y `bench/results/RESULTS.md` (tabla con el conjunto de cada repo —`split` en `repos.toml`: ajuste ronda 1 a 7, control— + 10 patrones principales de falsos positivos/negativos por repo, con `archivo:línea`, y el número de llamadas no medibles). Con `--only`, los resultados del resto de repos se conservan; para medir un conjunto ciego sin mezclarlo con los oficiales, `--out` a una carpeta fuera de `results/`.

## Instalar los indexadores (fuera del repo)

Todo va bajo `$T` (`--tools`); ningún paso ejecuta código de los repos medidos.

```sh
T=$W/tools && mkdir -p $T/bin && cd $T
# Python, TypeScript/JS, Go, Ruby
npm install --ignore-scripts @sourcegraph/scip-python@0.6.6 @sourcegraph/scip-typescript@0.4.0
gh release download v0.2.7 -R sourcegraph/scip-go -p 'scip-go-linux-amd64.tar.gz*'
sha256sum -c scip-go-linux-amd64.tar.gz.sha256 && tar xzf scip-go-linux-amd64.tar.gz -C bin
gh release download scip-ruby-v0.4.7 -R sourcegraph/scip-ruby -p scip-ruby-x86_64-linux
echo 'a068c7c3b2042b9eac563ce77ce35dcaca666b418530b1db9f932a3dbc7175dd  scip-ruby-x86_64-linux' | sha256sum -c && install -m 755 scip-ruby-x86_64-linux bin/scip-ruby

# Java y Kotlin: JDK ≥ 17 del sistema (javac o el módulo jdk.compiler) + coursier, que descarga de Maven Central
# (verificando las sumas publicadas) scip-java 0.12.3, semanticdb-javac 0.12.3, semanticdb-kotlinc 0.6.0 y kotlinc 2.2.0
mkdir -p jvm && curl -sSfLo jvm/coursier.jar https://github.com/coursier/coursier/releases/download/v2.1.26/coursier.jar
echo 'd3135830850eddfb9998be66ab4c79478ee6cff56012bb5a177532b1df47c7cc  jvm/coursier.jar' | sha256sum -c

# Rust: toolchain 1.91.0 con rust-analyzer y rust-src en una RUSTUP_HOME/CARGO_HOME propias
curl -sSfO https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu/rustup-init
echo 'dda7234360b7f578ca8b0ddcb80145646fa61a67c1720a5abc7051b35c9fcb71  rustup-init' | sha256sum -c   # rustup-init 1.29.1
chmod +x rustup-init && RUSTUP_HOME=$T/rust/rustup CARGO_HOME=$T/rust/cargo ./rustup-init -y --no-modify-path \
  --profile minimal --default-toolchain 1.91.0 -c rust-analyzer -c rust-src

# Dart: SDK 3.13.5 y scip_dart 1.7.0 (pub verifica el sha256 de cada paquete)
B=https://storage.googleapis.com/dart-archive/channels/stable/release/3.13.5/sdk
curl -sSfO $B/dartsdk-linux-x64-release.zip && curl -sSfO $B/dartsdk-linux-x64-release.zip.sha256sum
sed 's/\*//' dartsdk-linux-x64-release.zip.sha256sum | sha256sum -c && mkdir -p dart && unzip -q dartsdk-linux-x64-release.zip -d dart
PUB_CACHE=$T/dart/pub-cache HOME=$T/dart/home dart/dart-sdk/bin/dart pub global activate scip_dart 1.7.0

# PHP: binario estático 8.4.23 de static-php-cli (no publica suma: se fija la calculada), Composer 2.10.3 y scip-php
mkdir -p php/bin && curl -sSfLO https://dl.static-php.dev/static-php-cli/common/php-8.4.23-cli-linux-x86_64.tar.gz
echo '1aeed5bc7967977ca5b1da7163acd91bf9ba3ac56037045d4e91ee2ff2712bb7  php-8.4.23-cli-linux-x86_64.tar.gz' | sha256sum -c
tar xzf php-8.4.23-cli-linux-x86_64.tar.gz -C php/bin
curl -sSfLo php/bin/composer.phar https://getcomposer.org/download/2.10.3/composer.phar
echo '7a2d379d5b8ffdaa028580ef26494c36d2feef4b178d3dd1473a4dbc5e17c8d6  php/bin/composer.phar' | sha256sum -c
git -c core.hooksPath=/dev/null clone https://github.com/davidrjenni/scip-php php/scip-php
git -C php/scip-php checkout 71a5b117ec4c5dd2af302e363410e604e5df309e
(cd php/scip-php && COMPOSER_HOME=$T/php/composer-home ../bin/php ../bin/composer.phar install --no-dev --no-scripts --no-plugins)

# C#: SDK de .NET 9.0.318 (sha512 publicado en releases.json) y scip-dotnet 0.2.14
mkdir -p dotnet/sdk && curl -sSfLO https://builds.dotnet.microsoft.com/dotnet/Sdk/9.0.318/dotnet-sdk-9.0.318-linux-x64.tar.gz
echo 'e8685293a3512178e0de1bb3c1663e31fdf9d761af705094bf833cc1ff6b9a18c543aa4141f0216503c98039c719585a6d32905b0bbb3279e93b7e7616e047c3  dotnet-sdk-9.0.318-linux-x64.tar.gz' | sha512sum -c
tar xzf dotnet-sdk-9.0.318-linux-x64.tar.gz -C dotnet/sdk
DOTNET_CLI_HOME=$T/dotnet/home DOTNET_CLI_TELEMETRY_OPTOUT=1 dotnet/sdk/dotnet tool install scip-dotnet --version 0.2.14 --tool-path dotnet/tools
```

scip-ruby es un binario autónomo (Sorbet): lee los `.rb` sin `bundle install` ni ejecutar código. Conviene apuntar también `TMPDIR` a `--work`; los scripts `index_*.py` ya dirigen allí `COURSIER_CACHE`, `COMPOSER_CACHE_DIR` y `NUGET_PACKAGES`.

## Seguridad

Los repos de `repos.toml` son datos no confiables: se clonan con hooks desactivados, se fija el commit exacto y los indexadores solo los leen. Por lenguaje:

- **Python/Go/TS/Ruby**: scip-python recibe un entorno vacío (`--environment`) para no invocar `pip`; scip-go usa `GOTOOLCHAIN=local` y `CGO_ENABLED=0`; si un repo TS necesitara dependencias, `prepare` usaría siempre `npm install --ignore-scripts`.
- **Java/Kotlin** (`index_jvm.py`): no se usan Maven ni Gradle. Las carpetas de fuentes indicadas se compilan con `javac -proc:none` (sin procesadores de anotaciones) o con `kotlinc` y un único plugin, SemanticDB; las dependencias son coordenadas de Maven Central fijadas en `repos.toml` que descarga coursier. Compilar no ejecuta código del repo.
- **Rust**: `rust-analyzer scip` ejecuta por defecto los `build.rs` en su fase de «build scripts» (comprobado con un `build.rs` que escribe un archivo). `rust-analyzer.json` sustituye esa fase por `true` (`cargo.buildScripts.overrideCommand`) y desactiva las macros procedurales, así que solo corre `cargo metadata`, que descarga crates sin compilarlas. `RUSTC_WRAPPER` vacío y `RUSTUP_TOOLCHAIN` fijado anulan lo que pudieran pedir `.cargo/config.toml` o `rust-toolchain.toml` del repo (ripgrep solo fija `rustflags` para Windows y musl).
- **Dart**: `dart pub get` resuelve y descarga paquetes de pub.dev sin ejecutar su código (los hooks de compilación solo corren en `dart run/build`); scip-dart analiza con el analizador de la SDK. Hay que pasarle la ruta absoluta del paquete (con `./` trata la raíz como paquete anidado y no indexa nada).
- **PHP** (`index_php.py`): `composer install --no-dev --no-scripts --no-plugins --ignore-platform-reqs`. scip-php hace `require vendor/autoload.php` del proyecto, que incluiría los archivos `autoload.files` de cada paquete; antes de indexar se vacían esas listas en el autoloader generado por Composer. Su único `class_exists` (que cargaría un archivo del repo) solo se alcanza si un nombre de clase coincide con una función ya definida, cosa que no ocurre al no cargarse ningún archivo `files`. Si el repo no versiona `composer.lock` (monolog), se escribe a partir de `vendor/composer/installed.json`.
- **C#** (`index_dotnet.py`): no se evalúa ningún `.csproj`, `.sln` ni `Directory.Build.*` del repo. Sus `.cs` se copian a una carpeta fuera del clon con un `.csproj` propio (sin analizadores ni generadores de paquetes) y `Directory.Build.props/targets`, `Directory.Packages.props` y `NuGet.config` propios; `dotnet restore` se lanza solo sobre ese proyecto y scip-dotnet con `--skip-dotnet-restore` (sin esa opción, scip-dotnet restaura los proyectos del directorio de trabajo, es decir, los del repo). Para que el índice sea fiel, el `.csproj` propio reproduce a mano lo que el original declara: `--nullable`, `--implicit-usings` (los `global using` implícitos del SDK) y `--define` con los símbolos de compilación del marco de destino que se mide (serilog: los de `net8.0`). Sin `ImplicitUsings`, serilog no compilaba (`IEnumerable<T>` sin resolver) y scip-dotnet perdía esas llamadas; con la configuración actual el proyecto compila sin errores. Lo mismo con los `global using` del proyecto (`<Using Include="X" />` del `.csproj` y de `Directory.Build.targets`, opción `--using`): sin ellos, polly no compilaba (790 errores en 122 archivos, `TimeSpan`, `ValueTask`… sin resolver) y scip-dotnet perdía esas referencias (0 de 171 usos de tipos de `Polly.Utils` con ocurrencia; 133 de 171 con la configuración del repo, que compila sin errores). Desde la ronda 7 también los marcos y paquetes del proyecto: `--framework-ref Microsoft.AspNetCore.App` (el `<FrameworkReference>` implícito de `Microsoft.NET.Sdk.Web`, que sale de los paquetes de referencia instalados con el SDK) y `--package Id@Versión` con las versiones fijadas del `Directory.Packages.props` original, que entran con `IncludeAssets="compile"`: solo ensamblados de referencia, que el compilador lee como metadatos; ni `build/*.props|targets` (MSBuild no importa nada de los paquetes) ni analizadores o generadores de código, y `index_dotnet.py` lo comprueba en `project.assets.json` tras `restore` (en eShopOnWeb, 101 paquetes con sus dependencias, ninguno aporta más que marcadores vacíos `_._`). Sin ellos, los tipos de ASP.NET Core y de los paquetes no se resolvían en eShopOnWeb (0 ocurrencias de `PageModel`, `Controller` o `IServiceCollection`, frente a 12, 2 y 7) y scip-dotnet perdía las llamadas con un receptor o un argumento de esos tipos: 47 referencias a métodos del proyecto, frente a 85 con los paquetes.

## Lenguajes que no se miden

- **Swift**: no hay un indexador SCIP mantenido para Swift; la alternativa (IndexStoreDB vía `swift build -index-store-path`) compila el paquete con SwiftPM, que ejecuta los manifiestos `Package.swift` y los plugins del repo, y el toolchain de Linux ocupa varios GB.
- **C/C++ (scip-clang)**: necesita una base de compilación (`compile_commands.json`) que genera el sistema de build del repo (CMake, Bazel, Make…), es decir, ejecutar su configuración.
- **excalidraw con dependencias**: `npm install --ignore-scripts` del monorepo ocupa más de 500 MB; se mide sin `node_modules` (ver arriba).

## Brechas conocidas

Matriz por lenguaje de lo que se resuelve y lo que no: [LANGFEATURES.md](LANGFEATURES.md).

- **rack, sinatra y thor (Ruby)**: Sorbet sin firmas (`typed: true` forzado) no resuelve receptores sin tipo (`@ivar`, métodos sin firma, parámetros) ni los módulos que añaden los ganchos `self.included`; esas llamadas no se puntúan (ver «Llamadas no medibles»). Córtex tipa por sintaxis lo que Ruby deja ver (`X.new`, variables asignadas con `X.new`, constantes resueltas por anidamiento léxico) y busca por nivel en clases, módulos y superclases. Quedan como «falsos positivos» los bloques de DSL a nivel de clase (`error do … request … end`), que Ruby evalúa en la instancia y Sorbet en la clase. Desde la ronda 7 un receptor sin tipo ya no se enlaza por el nombre único del método (`option = class_options[name]; option.x`), ni un método que no está en los ancestros del proyecto de una clase con un ancestro de fuera (`Tag.active` de un `scope` de ActiveRecord): en una aplicación Rails casi siempre es de la biblioteca.
- **hono**: los manejadores `app.get(path, (c) => …)` ya se tipan por contexto a través de `HandlerInterface`; desde la ronda 3 también los métodos de objetos literales tipados por contexto y las lecturas de propiedades de un receptor tipado (`c.req.raw`) cuentan como dependencia; quedan sin tipo los callbacks de fábricas genéricas (`defineWebSocketHelper((c, events) => …)`).
- **TypeScript en general**: Córtex infiere tipos locales (anotaciones, `new`, tipos de retorno, campos y propiedades de constructor, `this.x.y()`, desestructuración, `await`, parámetros tipados por contexto, también en objetos literales, elementos de `T[]` en `forEach`/`map`…, retornos `T` fijados por el argumento); no hace inferencia genérica completa ni sigue tipos externos.
- **Java/Kotlin/C#/Rust/Dart/PHP**: Córtex tipa los receptores con las anotaciones del código (variables, parámetros, campos/propiedades, retornos, `var`/`val x = T()`, genéricos de colecciones conocidas, lambdas con tipo esperado, rasgos/traits/extensiones) y elige la sobrecarga por número de argumentos. No distingue sobrecargas que solo difieren en el tipo de los argumentos ni hace inferencia genérica de funciones propias.
- **monolog (PHP)**: la mayoría de los «falsos positivos» son llamadas que Córtex resuelve y scip-php no: receptores tipados por propiedades promovidas del constructor (`$record->level->getName()`) y variables asignadas con `new static(...)`.
- **stateless (C#)**: scip-dotnet no resuelve algunas llamadas genéricas dentro de lambdas (`ParameterConversion.Unpack<TArg0>(args, 0)`), que cuentan como falsos positivos; entre sobrecargas homónimas repartidas en dos partes de una clase parcial (`AddActivateAction` síncrona y asíncrona) Córtex elige la de la primera parte.

## Añadir un repo

Una entrada `[[repo]]` en `repos.toml` con `name`, `language`, `url`, `commit` e `indexer` (marcadores `{src}`, `{index}`, `{work}`, `{tools}`, `{python}`, `{bench}`). Opcionales: `cwd = "src"`, `env`, `subdir`, `scope`, `prepare`, `skip`, `ref` (etiqueta legible del commit). Para Java/Kotlin, PHP y C# el indexador es `{python} -I {bench}/index_jvm.py …`, `index_php.py …` o `index_dotnet.py …` (ver el `--help` de cada uno).

## Ajuste ronda 2

Los 11 repos que se midieron a ciegas tras la ronda 1 (antes `split = "control"`) pasaron a ser el conjunto de ajuste de
la ronda 2 (`split = "ajuste2"`). Antes = medida a ciegas (código y reglas de la ronda 1); después = código y reglas
actuales. «No medibles»: aristas de llamada apartadas por un límite del indexador (ver «Llamadas no medibles»). El
informe con los hallazgos está en [`results/CONTROL.md`](results/CONTROL.md) y la matriz de construcciones en
[`LANGFEATURES.md`](LANGFEATURES.md).

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

Artefactos de indexador encontrados (no eran fallos de Córtex):

- **serilog**: el índice se había compilado sin los `global using` implícitos ni los símbolos `#if` del marco de destino; con `IEnumerable<T>` sin resolver, Roslyn no infería los genéricos (`Guard.AgainstNull(x)`) y scip-dotnet no emitía esas llamadas. Se regeneró con `--implicit-usings enable --nullable enable` y los `FEATURE_*` de `net8.0` (compila sin errores): solo con eso, llamadas P pasa de 69,8 a 93,4.
- **psr7** (y monolog): scip-php no tipa variables salvo `$this`; las llamadas sobre `$x->` quedan fuera de la medida.
- **sinatra** (y rack): Sorbet sin firmas no emite ocurrencias para `f(*a)`, `f(&b)`, `f(...)` ni para receptores sin tipo; `require`/`autoload` no tienen símbolo.
- **httpx**: scip-python nombra mal el módulo de los imports relativos (`from ._api import *`): las 16 «dependencias de más» eran reales.
- **zod / express**: scip-typescript deja como `local` sin nombre las llamadas a través de `export { a as b }` y los miembros CommonJS; los getters no tienen ámbito; los tipos y valores homónimos (`type OK` / `const OK`) emiten dos símbolos.
- **itertools**: `Self { … }` apunta al bloque `impl`, no al tipo.
- **yaml**: scip-dart trata los constructores con nombre como miembros y los privados como `local`.
- **gson / moshi**: el benchmark no contaba `new X<>()` como llamada (en Java y C# no se saltaban los argumentos de tipo).

Notas: `regex` 1.11.1 se descartó porque rust-analyzer entra en pánico al renderizar la documentación (`DocsRangeMap::map`) sin proc-macros; se sustituyó por itertools. gson necesita `src/main/java-templates` (contiene `GsonBuildConfig`, con marcadores sin sustituir) y moshi `jsr305`.

## Ajuste ronda 3

Los 11 repos que se midieron a ciegas tras la ronda 2 (`split = "control2"`) pasaron a ser el conjunto de ajuste de la
ronda 3 (`split = "ajuste3"`). Antes = medida a ciegas (código y reglas de la ronda 2); después = código y reglas
actuales. Hallazgos y muestras de cada categoría nueva de «no medibles» en [`results/CONTROL.md`](results/CONTROL.md);
construcciones nuevas en [`LANGFEATURES.md`](LANGFEATURES.md).

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

Los 25 repos de las rondas 1 y 2 no empeoran salvo dos décimas (httpx defs P 100 → 99,8; http4k deps P 93,3 → 92,7, a
cambio de deps R 91,6 → 98,1) y suben en muchos casos: rack llamadas P 91,8 → 94,7 y R 94,9 → 99,3, sinatra P 91,8 →
98,2, flask/healthchecks/httpx defs R → 100, hono y zod deps R 92,8 → 95,7 y 91,3 → 93,9, stateless llamadas P 93,3 →
96,3. Tiempo de análisis (CPU, 36 repos, `analyze()` completo): 305,8 → 326,5 s (+6,8 %); la parte de los analizadores
de lenguaje, 141,7 → 154,1 s (+8,7 %).

Reglas generales añadidas a Córtex (no por repo):

- **Ruby**: tipador por sintaxis (`analyzer/cortex_graph/rubytyped.py`): constantes resueltas como Ruby (anidamiento
  léxico, raíz, nombre único), receptores `X.new` / locales y `@ivar` asignados con `X.new` / `self.class.new` / `dup`,
  búsqueda por nivel en la clase, sus `include`/`extend`/`prepend`, los módulos de los ganchos `self.included` y las
  superclases; `self[k]`, valores de hash, `Struct.new`, clases homónimas anidadas y constantes como dependencia.
- **Python**: funciones y clases anidadas como nodos, definiciones condicionales, alias locales de clases, `cls(…)`,
  `if`/`or` en expresiones, alias de tipo de módulo, `__iter__`/`__getitem__`, estrechamiento por `isinstance` y
  anotaciones resueltas en el ámbito del módulo.
- **TypeScript/JavaScript**: objetos literales tipados por contexto, lecturas de propiedad como dependencia, retornos
  `T` fijados por el argumento, elementos de colecciones en `forEach`/`map`…, campos de tipo función,
  `Object.assign(Clase.prototype, {…})` y llamadas a valores importados que no son funciones como referencias.
- **Rust / Dart**: parámetros de clausura por la cota `Fn`, argumentos genéricos concretos del `impl`, tuplas literales,
  gemelos `#[cfg]`; variables de nivel superior tipadas y tipos con prefijo de import reexportados.
- **Kotlin / C# / PHP**: `operator fun invoke` (companion, objetos anidados, valores invocables), constructores SAM,
  `typealias`, `override` con valores por defecto heredados, visibilidad por paquete; `#if` de marco de destino,
  delegados, `T` de la base genérica, `string[i]`; `@method`, atributos `#[X(…)]`, uniones con una clase del proyecto.

Artefactos de indexador encontrados (no eran fallos de Córtex): Sorbet sin firmas no tipa parámetros, `self.class` en
módulos, lecturas `x[k]` ni los módulos de los ganchos `self.included`, y resuelve receptores sin tipo contra `Object`;
scip-ruby sitúa la copia de `module_function` en el símbolo; scip-python da el mismo símbolo a funciones anidadas
homónimas y solo define la primera `@overload`; rust-analyzer solo indexa el `#[cfg]` activo; scip-php no tipa retornos
`self`/`static`, enums ni variables indexadas; scip-dotnet no emite nombres genéricos y nombra los tipos con el último
tramo del espacio de nombres; semanticdb-kotlinc comparte símbolo entre sobrecargas de nivel superior de distintos
archivos.

## Ajuste ronda 4

Los 11 repos que se midieron a ciegas tras la ronda 3 (`split = "control3"`) pasaron a ser el conjunto de ajuste de la
ronda 4 (`split = "ajuste4"`). Antes = medida a ciegas (código y reglas de la ronda 3); después = código y reglas
actuales. Hallazgos, reparto entre reglas y analizador y muestras de cada categoría nueva de «no medibles» en
[`results/CONTROL.md`](results/CONTROL.md); construcciones nuevas en [`LANGFEATURES.md`](LANGFEATURES.md).

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

Los 36 repos de las rondas 1 a 3 no empeoran salvo express defs P 100 → 94,7 (un nodo: `var flatten =
Array.prototype.flat`, que scip-typescript no tipa con la `lib` ES5 del `tsconfig` inferido) y suben en varios: zod
llamadas R 91,1 → 92,7, http4k llamadas R 90,2 → 93,4, javalin 95,4 → 96,1, yaml llamadas P 98,5 → 99,7. Tiempo de
análisis (CPU, `analyze()` completo): 36 repos 333,4 → 342,5 s (+2,7 %), 47 repos 408,1 → 411,4 s (+0,8 %); la parte
TypeScript/JavaScript, 15,8 → 18,1 s (+14 %, sobre todo excalidraw +0,9 s).

Reglas generales añadidas a Córtex (no por repo):

- **TypeScript/JavaScript**: `export = X` y `export { default as X }`, parámetro `this: T`, propiedades `typeof f`, tipos
  objeto en línea, claves de objetos literales tipados y desestructuración como dependencia, cadenas CommonJS
  (`var a = (exports.a = function…)`, `exports = module.exports = X`), miembros del objeto exportado, alias de `require`
  hacia la función original, alias de funciones de la biblioteca estándar, retornos inferidos de los `return` y
  variables `let` asignadas después.
- **Ruby**: la variable de `rescue X => e` tiene el tipo `X`; las constantes del núcleo (`File`, `Hash`…) no se
  resuelven por nombre único a una clase anidada del proyecto.
- **Kotlin**: propiedades de extensión, visibilidad de las extensiones por `import`, propiedades de un receptor implícito
  externo, extensión importada sobre un receptor de tipo desconocido y propiedades de nivel superior importadas.
- **C# / Python**: `#if` tras la marca BOM; `from .paquete import x` depende del `__init__.py` del paquete.

Artefactos de indexador encontrados (no eran fallos de Córtex): `require` en archivos `.ts` sin ocurrencia del módulo;
miembros CommonJS sin símbolo; Sorbet sin firmas no tipa el resultado de un método del proyecto ni de `x[k]`;
semanticdb-kotlinc no emite las anotaciones; SCIP elige el primer archivo de un tipo definido en varios. Dos fallos del
propio benchmark: la lista de supertipos de Kotlin partida en líneas y el prefijo de las clases privadas de Dart.

## Ajuste ronda 5

Los 12 repos que se midieron a ciegas tras la ronda 4 (`split = "control4"`) pasaron a ser el conjunto de ajuste de la
ronda 5 (`split = "ajuste5"`). Antes = medida a ciegas (código y reglas de la ronda 4); después = código y reglas
actuales; el índice de polly se regeneró con los `global using` del repo (ver «Seguridad», C#). Hallazgos, reparto entre
reglas y analizador y muestras de cada categoría nueva de «no medibles» en [`results/CONTROL.md`](results/CONTROL.md);
construcciones nuevas en [`LANGFEATURES.md`](LANGFEATURES.md).

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

Los 47 repos de las rondas 1 a 4 no bajan más de 0,4 puntos (http4k deps R 98,4 → 98,0 y axios deps R 100 → 99,4, por
dependencias que las reglas nuevas hacen medibles; ktlint llamadas R −0,05) y suben en muchos: ktlint deps R 95,3 → 99,2
y defs R 97,4 → 99,7, dapper deps R 92,0 → 96,0, markdig deps R 94,0 → 97,3, zod deps R 93,9 → 97,8, thor deps P 97,9 →
100. miniflux defs P 100 → 99,5 viene del código de flujos que se edita en paralelo (16 nodos de tablas SQL), no de esta
ronda. Tiempo de análisis (CPU, `analyze()` completo, mismos puentes): 59 repos 542,6 → 543,9 s (+0,2 %), 47 repos 413,4
→ 412,0 s; la parte de los analizadores de lenguaje (`langs`), 206,2 → 216,9 s (+5,2 %), sobre todo C# (polly +3,8 s,
markdig +2,2 s, dapper +1,8 s: los miembros implícitos como dependencia).

Reglas generales añadidas a Córtex (no por repo):

- **Todos**: la línea de una definición es la de su declaración, sin las anotaciones o atributos que la preceden; un
  byte NUL no corta el árbol sintáctico.
- **Kotlin**: correcciones de gramática (`where` como variable, anotaciones de un accesor), la extensión que admite los
  argumentos antes que un miembro que no, la lambda final cuenta como argumento, propiedades de nivel superior importadas
  con `*` o leídas desde otro archivo, `by lazy`, `buildString { }`, extensiones miembro con su clase como receptor
  implícito y llamadas infijas como dependencia.
- **TypeScript/JavaScript**: uniones de tipos del proyecto, constantes a través de un barril, alias de `Object`, miembros
  de `export default { … }` y claves renombradas de `module.exports = { … }`, llamadas sobre `require('./m')` en línea.
- **C#**: referencias a clases parciales, miembros heredados o de otra parte sin receptor, claves de inicializadores y
  grupos de métodos como dependencia.
- **Python / Rust / Dart**: bases genéricas `Base[T]`; `use super::x` en un `mod tests` en línea; `Caja<T>(x)` y el
  cuerpo dentro del rango de cada método.

Artefactos de indexador encontrados (no eran fallos de Córtex): el índice de polly compilado sin los `global using` del
repo (790 errores); scip-dotnet sin ocurrencias para tipos escritos con argumentos genéricos ni referencias a los métodos
bajo `<invalid-global-code>`; semanticdb-kotlinc nombra los miembros heredados con el subtipo y a veces lista subtipos en
las relaciones de un tipo; scip-typescript define las propiedades abreviadas exportadas como símbolos «meta»; scip-dart
no enlaza algunas llamadas a privados con su definición; Sorbet sin firmas no tipa las variables locales asignadas con
valores sin tipo. Dos fallos del propio benchmark: el árbol de Kotlin sin las correcciones de gramática y los
constructores con nombre de clases privadas de Dart.

## Ajuste ronda 6

Los 12 repos que se midieron a ciegas tras la ronda 5 (`split = "control5"`) pasaron a ser el conjunto de ajuste de la
ronda 6 (`split = "ajuste6"`). Antes = medida a ciegas (código y reglas de la ronda 5); después = código y reglas
actuales, con los mismos índices. Hallazgos, reparto entre reglas y analizador y muestras en
[`results/CONTROL.md`](results/CONTROL.md); construcciones nuevas en [`LANGFEATURES.md`](LANGFEATURES.md).

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

Las 60 métricas (llamadas P/R, deps P/R, defs R) de los 12 repos quedan ≥ 90 (antes 56); media 97,2 → 98,8. Los 59
repos de las rondas 1 a 5 no bajan en ninguna métrica y suben jekyll (defs R 96,2 → 98,8, defs P → 100), rack (defs R
96,7 → 99,7, llamadas R → 100), liquid (defs P → 100) y moment (defs R 98,7 → 100). Tiempo de análisis (CPU, `analyze()` completo, mismos puentes):
71 repos 615,8 → 590,4 s en una pasada, diferencia que es ruido (los repos con más diferencia, medidos dos veces más,
quedan iguales); sin coste medible.

Reglas generales añadidas a Córtex (no por repo):

- **Kotlin**: extensiones con receptor parámetro de tipo (`fun <A> A.valid()`, con sus cotas) y constructores
  calificados con el paquete (`com.app.decoder.IntDecoder()`).
- **Dart**: llamadas genéricas encadenadas o con argumentos con nombre (`Caja<T>(a: x).bind(this)`), miembros estáticos
  genéricos (`Clase.list<T>(xs)`), constructores con nombre de clases genéricas (`_Wrapper<T>.seeded(x)`) y extensiones
  sobre supertipos de la SDK (`on Iterable<StreamSubscription<void>>` sobre un `List<…>`).
- **Ruby**: delegadores de `Forwardable` (`def_delegators`, `def_delegator`) como métodos, `X = Struct.new(:a) do … end`
  como clase con accesores, y la línea de cada accesor o delegador es la de su símbolo.
- **TypeScript/JavaScript**: una constante fabricada por una función del proyecto que devuelve una función (`const debug
  = Debug("x")`) es una función, y la llamada que la fabrica es suya.
- **Todos**: el nodo empieza en sus anotaciones (`line`) y guarda la línea de la declaración en `decl` (la ronda 5 había
  movido `line`, y los puentes dejaban de ver `@Query("…")` dentro del método).

Artefactos de indexador encontrados (no eran fallos de Córtex): scip-python nombra los módulos de un proyecto con raíz
de fuentes sin esa raíz y los submódulos importados como miembro solo con su último tramo; scip-typescript tipa como
`Function` el resultado de una fábrica CommonJS.

## Ajuste ronda 7

Los 12 repos que se midieron a ciegas tras la ronda 6 (`split = "control6"`) pasaron a ser el conjunto de ajuste de la
ronda 7 (`split = "ajuste7"`), elegidos sobre todo entre aplicaciones (Rails, Laravel, ASP.NET Core, herramientas de
línea de órdenes). Antes = medida a ciegas (código y reglas de la ronda 6; moquette, cuyo `analyze()` fallaba en los
puentes, con ese fallo corregido); después = código y reglas actuales, con los mismos índices salvo el de eShopOnWeb.
Hallazgos, reparto entre reglas y analizador y muestras en [`results/CONTROL.md`](results/CONTROL.md); construcciones
nuevas en [`LANGFEATURES.md`](LANGFEATURES.md).

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

Las 60 métricas (llamadas P/R, deps P/R, defs R) de los 12 repos quedan ≥ 90 (antes 56); media 96,7 → 98,2. Los 71
repos de las rondas 1 a 6 no bajan en ninguna métrica y suben, entre otros, liquid (llamadas P 96,7 → 99,0, deps P →
100), jekyll (llamadas P 98,1 → 99,4, deps P 94,6 → 98,9), faraday, rack y sinatra (Ruby), psr7 (llamadas P → 100),
click (llamadas R 95,4 → 96,8), shelf (deps R 90,9 → 93,9) y, por las reglas, twig (defs P 96,9 → 100). TIEMPO

En las aplicaciones, la precisión caía sobre todo por enlazar por nombre receptores sin tipo: métodos de la biblioteca
del framework (`Tag.active` de un `scope`, `.order(…)` de ActiveRecord, `response()->json()` de Laravel) acababan en el
único método homónimo del proyecto, a menudo de un controlador. Ahora se prefiere no poner la arista.

Reglas generales añadidas a Córtex (no por repo):

- **Ruby**: un ancestro de fuera del proyecto (`class Tag < ApplicationRecord`) cierra la búsqueda de métodos, y lo que
  devuelve un método que no está en los ancestros del proyecto no tiene tipo; un receptor sin tipo no se enlaza por el
  nombre único del método; `X = Class.new(Base)` es una clase; estrechamiento por `x.is_a?(K)` en `&&`, ternarios e `if`;
  una variable reasignada dentro de un bloque conserva el tipo de su asignación anterior (como Sorbet).
- **PHP**: un `use` de fuera tapa la clase homónima del proyecto; el valor de una función de PHP o de una dependencia, y
  un miembro ausente de los ancestros del proyecto de una clase con un ancestro de fuera, son de fuera; `@property` del
  PHPDoc; una función del proyecto con tipo de retorno tipa la cadena (`user()->can()`).
- **Python**: descriptores de clase (`__get__`, con la variable de tipo fijada por la herencia), clases genéricas del
  proyecto como anotación (`BaseConfigOption[T]`) y atributos inicializados a `None`.
- **Dart**: las partes (`part of`) comparten los imports de su biblioteca; reexportaciones en cadena con `show`; los
  nombres de `show` son dependencias.
- **TypeScript/JavaScript**: una constante con un callback como argumento de una función del proyecto que devuelve un
  valor no es una función; en JavaScript, los campos asignados en cualquier método (`this.x = new X()`), salvo un JSDoc
  `@type` de otro tipo.
- **C#**: la lambda de un método de un tipo genérico de fuera (`EntityTypeBuilder<CatalogItem>`) recibe su argumento de
  tipo.

Artefactos de indexador y de configuración encontrados (no eran fallos de Córtex): el índice de eShopOnWeb se compilaba
sin el marco de ASP.NET Core ni los paquetes NuGet del proyecto (ahora `index_dotnet.py --framework-ref` y `--package`,
solo con ensamblados de referencia); scip-php no nombra las funciones que no están cargadas, y las de `autoload.files`
no se cargan para no ejecutar código del repo (sus llamadas y las cadenas que empiezan en ellas no se miden).
