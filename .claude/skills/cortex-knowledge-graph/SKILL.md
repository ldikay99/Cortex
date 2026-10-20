---
name: cortex-knowledge-graph
description: Build and query a deterministic knowledge graph of any code repository with Córtex (MCP tools, `cortex` CLI or HTTP API), and use its personal memory (remember, recall, forget, profile, timeline) for durable facts about the user. Use when an agent needs to orient in an unfamiliar codebase, locate where logic lives, trace how two parts connect, estimate the impact of a change before editing, see what changed between analyses, or answer questions that depend on who the user is.
---

# Córtex: grafo de conocimiento para agentes

Córtex analiza cualquier repositorio sin IA (26 lenguajes con árboles de sintaxis, configuración e infraestructura como Docker, CI, SQL o Terraform, y un respaldo heurístico para el resto) y guarda un grafo de módulos, clases, funciones, métodos y documentos unidos por `contains`, `import`, `call`, `inherits`, `ref` y `loads`, agrupados en comunidades (Leiden). Cada análisis es una versión con diff por hash de contenido. Todo resultado cita `archivo:línea`.

Córtex también puede importar notas, documentos y chats (`cortex import`) y los convierte en nodos de conversación, sección, persona, concepto, evento y recuerdo, unidos por `mentions`, `links`, `participant`, `about`, `from`, `supersedes`, `related` y `attends`. Todo se procesa en local salvo que se use `--ai`.

## Cuándo analizar

- El proyecto no aparece en `list_projects` / `cortex projects`.
- La última versión es anterior a cambios relevantes (commits, ramas, archivos editados por ti). Compara la fecha de `list_projects` con `git log -1`.
- Antes de un refactor grande y después de terminarlo, para revisar con `changes` lo que realmente se movió.

Reanalizar es barato (segundos a pocos minutos) y no pierde historia: crea `v<n+1>` y conserva las posiciones del mapa.

## Tres formas de acceso

| Vía | Cuándo | Ejemplo |
| --- | --- | --- |
| MCP (`cortex mcp`) | Agente con cliente MCP. Preferida. | `impact_analysis(node="create_user")` |
| CLI | Terminal o scripts; añade `--json` para parsear | `cortex impact create_user --json` |
| HTTP | Otro servicio, con la web levantada | `curl 'localhost:8090/api/query/impact?ref=create_user'` |

Con Docker la CLI va dentro del contenedor: `docker exec cortex-analyzer cortex …`. El MCP se registra en `.mcp.json` con `docker exec -i cortex-analyzer cortex mcp`. En el contenedor las carpetas locales deben estar bajo `/data`; para repos de GitHub basta la URL (usa `GITHUB_TOKEN` si es privado).

Herramientas MCP y equivalentes (`project` es opcional en todas; por defecto, el proyecto analizado más recientemente):

| MCP | CLI | HTTP `/api/query/…` |
| --- | --- | --- |
| `context_for(query, budget)` | `context "<tarea>" [--budget]` | `context?q=&budget=` |
| `read_symbol(node, context)` | `read <ref> [--context]` | `symbol?ref=` |
| `search_code(query, kind, limit, offset)` | `search <texto>` | `search?q=` |
| `node_context(node)` | `node <ref>` | `node?ref=` |
| `file_context(path)` | `file <ruta>` | `file?path=` |
| `community_context(community)` | `community <id\|nombre>` | `community?ref=` |
| `find_path(source, target)` | `path <a> <b>` | `path?a=&b=` |
| `impact_analysis(node, depth)` | `impact <ref>` | `impact?ref=` |
| `review_changes(base, head)` | `review [--base] [--head\|--worktree]` | `review?base=&head=` |
| `architecture(section)` | `architecture` | `architecture` |
| `dependencies(name)` | `deps [nombre]` | `dependencies` |
| `endpoints(method)` | `endpoints` | `endpoints` |
| `variables(name)` | `vars [nombre]` | `variables` |
| `project_overview` | `overview` | `overview` |
| `changes(since_version)` | `changes [--since]` | `changes?since=` |
| `list_projects` · `analyze_project` · `get_report` | `projects` · `analyze` · `export -f md` | `/api/projects` · web · `/api/export.md` |
| `graph_guide` · `graph_add` · `graph_overlay` · `graph_remove` | `graph guide` · `graph add <json>` · `graph list` · `graph remove <id>` | `GET/POST /api/overlay` · `POST /api/overlay/remove` |

Memoria personal (proyecto `memoria` por defecto, o `CORTEX_MEMORY_PROJECT`):

| MCP | CLI | HTTP |
| --- | --- | --- |
| `remember(text, category, about, when)` | `remember "<dato>" [--categoria] [--sobre] [--cuando]` | `POST /api/memory` |
| `recall(query, budget, at)` | `recall "<pregunta>" [--budget] [--en AAAA-MM-DD]` | `/api/query/recall?q=&budget=&at=` |
| `forget(ref)` | `forget <id\|texto>` | `POST /api/memory/forget` |
| `profile(budget)` | `profile [--budget]` | `/api/query/profile?budget=` |
| `timeline(start, end, about, limit)` | `timeline [--desde] [--hasta] [--sobre]` | `/api/query/timeline?start=&end=` |
| `import_history(source, ai, batch, model)` | `import <ruta> [--ai] [--batch]` | — |

Una referencia de nodo acepta clave (`f:app/services.py:create_user`), nombre, ruta o subcadena. Tipos de nodo: `module`, `class`, `function`, `method`, `doc`, `endpoint`, `package`, `variable`, `topic`, `conversation`, `section`, `person`, `concept`, `memory`, `event`, y los que escriben los agentes: `component`, `flow`. Relaciones: `contains`, `import`, `call`, `inherits`, `ref`, `loads`, `tests`, `http`, `rpc`, `handles`, `env`, `data`, `event`, `depends`, `cochange`, `mentions`, `links`, `participant`, `about`, `from`, `supersedes`, `related`, `attends`, `step` (flujo → paso, ordenado), `uses` (dependencia entre componentes).

## Flujo recomendado

1. **Contexto para la tarea**: `context_for("<lo que vas a hacer>")`. Devuelve los símbolos relevantes con firma, doc, rango de líneas y el código clave dentro del presupuesto. Empieza siempre aquí.
2. **Leer código**: `read_symbol` con la clave; no abras archivos completos.
3. **Seguir vínculos**: `node_context` (llamadas, herencia, tests, rutas, variables, dependencias), `find_path` para «cómo llega A a B», `endpoints` para conexiones entre servicios.
4. **Antes de editar**: `impact_analysis` sobre lo que vas a tocar.
5. **Después de editar**: `review_changes` (`--worktree` para cambios sin commitear): símbolos tocados, impacto, tests a correr y riesgo.
6. **Panorama**: `project_overview` y `architecture` (entradas, capas, ciclos, código muerto, puntos calientes).

## Completar el grafo tú mismo

Cuando el análisis cubre mal el proyecto (lenguajes no soportados, flujos en configuración, procesos de negocio) o el usuario quiere componentes, flujos y resúmenes:

1. `graph_guide(project)` (CLI `cortex graph guide`): procedimiento y lista de trabajo: archivos sin analizar o sin símbolos, comunidades sin componente, archivos sin resumen, endpoints/tópicos/variables sin pareja. Si el proyecto no existe, `analyze_project` primero: funciona aunque ningún lenguaje esté soportado (cada archivo queda como nodo `m:<ruta>`).
2. Lee el contenido real con `read_symbol`/`file_context`; nunca inventes archivos ni comportamiento.
3. `graph_add` en lotes de hasta 500: `nodes` (`{name, kind: "component", summary, contains: [refs], community_hint}`), `flows` (`{name, summary, steps: [refs en orden]}`), `edges` (`{a, b, kind: "uses"}` u otro tipo del analizador), `annotations` (`{id, summary, tags}` sobre cualquier nodo). Refs: clave (mejor), nombre exacto o ruta. Ids nuevos `a:<slug>`; repetir un nombre actualiza el nodo; dar la clave de un nodo del analizador lo anota.
4. Revisa `rejected` y reenvía corregido; verifica con `graph_overlay` y `node_context`. `graph_remove` deshace (los nodos del analizador nunca se borran).

Todo queda en `datos/<proyecto>/agente.jsonl`, genera versión nueva en segundo plano y aparece en la web con la marca «agente» (o «IA» si vino de `cortex analyze --ai`). Prompt MCP: `build_graph`.

## Memoria personal: cuándo usarla

- **Antes de responder** preguntas personales o que dependen del usuario (preferencias, personas de su entorno, proyectos, decisiones pasadas): `recall` con la pregunta. Cita la fecha y la fuente de cada recuerdo; si `recall` no encuentra nada, dilo en lugar de adivinar.
- **Al empezar una conversación**: `profile` (o el recurso `cortex://profile/<proyecto>`) como instrucciones de sistema.
- **Al guardar**: `remember` para datos duraderos que el usuario afirma: hechos, preferencias, instrucciones, decisiones, metas, relaciones. Un dato nuevo que contradice uno anterior reemplaza al viejo (`supersedes`); no hace falta borrarlo.
- **Al olvidar**: `forget` con el id (`r:…`) o el texto. Borra también el texto de versiones anteriores.
- **Historia**: `timeline` con `start`/`end` o `about` para «qué pasó en 2024» o «qué sé de Ana».
- **Nunca** guardes secretos (contraseñas, tokens, claves, números de cuenta), ni datos que el usuario no pidió guardar.
- `import_history` solo cuando el usuario indique la carpeta a importar. Con `ai=true` el texto sale a la API de Claude: pide confirmación antes.

## Leer sin servidor

Todo persiste en `datos/<proyecto>/` (o `$CORTEX_DATA`):

- `grafo.md`: reporte para agentes (comunidades, hubs, dependencias, rutas, tablas, documentos, símbolos por archivo). Léelo directamente si no hay MCP.
- `grafo.json`: grafo compacto para herramientas.
- `v<n>.cortex.json`: versión completa, reimportable en la web.
- `historial.json`: versiones con fecha, origen, opciones, commit, stats y conteo de cambios.

## Reglas

- Cita siempre `archivo:línea` tal como lo devuelve Córtex.
- El grafo es estático: llamadas dinámicas, inyección de dependencias o strings no se resuelven. Si algo «no tiene dependientes», confírmalo con una búsqueda de texto antes de borrarlo.
- Si `stats.warnings_total` > 0, hay archivos que no se pudieron analizar; tenlo en cuenta en tus conclusiones.
- Respeta las exclusiones del usuario (`exclude`, tests) al reanalizar: repite las mismas opciones para que el diff sea comparable.

— Creado por Jonathan C (ldikay99) · Colombia
