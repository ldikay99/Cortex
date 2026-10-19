# Córtex · benchmark de precisión frente a SCIP

Generado: 2026-10-19 · Córtex analizado con `analyze()` (sin git) · verdad de referencia: índices SCIP.

| repo | lenguaje | archivos | deps archivo P | deps archivo R | llamadas P | llamadas R | definiciones R | definiciones P | llamadas R (modo preciso) |
|---|---|---|---|---|---|---|---|---|---|
| flask | python | 24 | 98.2 % | 100.0 % | 99.1 % | 96.6 % | 94.6 % | 99.2 % | 100.0 % |
| gin | go | 84 | 99.6 % | 93.2 % | 100.0 % | 100.0 % | 100.0 % | 99.5 % | 100.0 % |

P = precisión, R = exhaustividad (recall). Solo cuentan archivos presentes en el índice SCIP.

## flask

Llamadas: TP 228 · FP 2 · FN 8 — deps archivo: TP 112 · FP 2 · FN 0 — definiciones: 371/392 (Córtex 374)

### Llamadas que Córtex no ve (falsos negativos)

| n | patrón | ejemplos |
|---|---|---|
| 4 | método · calificado obj.x() · mismo archivo | src/flask/cli.py:631 app = info.load_app()<br>src/flask/cli.py:653 rv.update(info.load_app().cli.list_commands(ctx))<br>src/flask/ctx.py:426 app_ctx.pop(exc) |
| 1 | método · cadena a.b.x() / x().y() · mismo archivo | src/flask/app.py:278 view_func=lambda **kw: self_ref().send_static_file(**kw),  # type: ignore # noqa: B950 |
| 1 | método · calificado obj.x() · otro archivo | src/flask/cli.py:640 ctx.with_resource(app.app_context()) |
| 1 | método · calificado obj.x() · otro archivo · llamador anidado | src/flask/cli.py:398 ctx.with_resource(app.app_context()) |
| 1 | método · cadena a.b.x() / x().y() · mismo archivo · llamador anidado | src/flask/cli.py:397 app = ctx.ensure_object(ScriptInfo).load_app() |

### Llamadas que Córtex inventa (falsos positivos)

| n | patrón | ejemplos |
|---|---|---|
| 2 | SCIP ve una referencia, no una llamada (conversión, valor, tipo) · class | src/flask/app.py:727 f:src/flask/app.py:Flask.test_cli_runner -> c:src/flask/testing.py:FlaskCliRunner ¦ def test_cli_runner(self, **kwargs: t.Any) -> FlaskCliRunner:<br>src/flask/app.py:669 f:src/flask/app.py:Flask.test_client -> c:src/flask/testing.py:FlaskClient ¦ def test_client(self, use_cookies: bool = True, **kwargs: t.Any) -> FlaskClient: |

### Dependencias entre archivos que faltan

| n | patrón | ejemplos |
|---|---|---|

### Dependencias entre archivos de más

| n | patrón | ejemplos |
|---|---|---|
| 1 | aristas Córtex: env · existe la inversa | src/flask/helpers.py:0 -> src/flask/cli.py |
| 1 | aristas Córtex: import · destino __init__.py (reexporta) · existe la inversa | src/flask/wrappers.py:10 -> src/flask/json/__init__.py ¦ from . import json |

### Definiciones SCIP sin nodo Córtex

| n | patrón | ejemplos |
|---|---|---|
| 19 | función anidada (closure) | src/flask/cli.py:395 decorator<br>src/flask/cli.py:422 decorator<br>src/flask/config.py:30 __get__ |
| 2 | función | src/flask/cli.py:230 locate_app<br>src/flask/helpers.py:51 stream_with_context |
| 2 | nodo function sin definición SCIP | src/flask/cli.py:241 locate_app<br>src/flask/helpers.py:62 stream_with_context |
| 1 | nodo method sin definición SCIP | src/flask/config.py:35 ConfigAttribute.__get__ |

## gin

Llamadas: TP 1841 · FP 0 · FN 0 — deps archivo: TP 235 · FP 1 · FN 17 — definiciones: 1140/1140 (Córtex 1146)

### Llamadas que Córtex no ve (falsos negativos)

| n | patrón | ejemplos |
|---|---|---|

### Llamadas que Córtex inventa (falsos positivos)

| n | patrón | ejemplos |
|---|---|---|

### Dependencias entre archivos que faltan

| n | patrón | ejemplos |
|---|---|---|
| 15 | primera referencia a term | benchmarks_test.go:44 -> mode.go ¦ DefaultWriter = os.Stdout<br>binding/binding_test.go:189 -> binding/json.go ¦ EnableDecoderDisallowUnknownFields = true<br>binding/multipart_form_mapping_test.go:29 -> binding/binding.go ¦ err := FormMultipart.Bind(req, &s) |
| 2 | primera referencia a callable | debug_test.go:62 -> context_test.go ¦ debugPrintRoute("GET", "/path/to/route/:param", HandlersChain{func(c *Context) {}, handlerNameTest})<br>routes_test.go:778 -> gin_test.go ¦ base.GET("/metrics", handlerTest1) |

### Dependencias entre archivos de más

| n | patrón | ejemplos |
|---|---|---|
| 1 | aristas Córtex: import | gin.go:0 -> render/render.go |

### Definiciones SCIP sin nodo Córtex

| n | patrón | ejemplos |
|---|---|---|
| 6 | nodo function sin definición SCIP | gin_test.go:209 init<br>logger_test.go:18 init<br>mode_test.go:16 init |

