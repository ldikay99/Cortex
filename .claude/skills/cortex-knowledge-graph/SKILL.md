---
name: cortex-knowledge-graph
description: Build and query a deterministic knowledge graph of any code repository with Córtex (MCP tools, `cortex` CLI or HTTP API). Use when an agent needs to orient in an unfamiliar codebase, locate where logic lives, trace how two parts connect, estimate the impact of a change before editing, or see what changed between analyses.
---

# Córtex: grafo de conocimiento para agentes

Córtex analiza cualquier repositorio sin IA (26 lenguajes con árboles de sintaxis, configuración e infraestructura como Docker, CI, SQL o Terraform, y un respaldo heurístico para el resto) y guarda un grafo de módulos, clases, funciones, métodos y documentos unidos por `contains`, `import`, `call`, `inherits`, `ref` y `loads`, agrupados en comunidades (Leiden). Cada análisis es una versión con diff por hash de contenido. Todo resultado cita `archivo:línea`.

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

Una referencia de nodo acepta clave (`f:app/services.py:create_user`), nombre, ruta o subcadena. Tipos de nodo: `module`, `class`, `function`, `method`, `doc`, `endpoint`, `package`, `variable`, `topic`. Relaciones: `contains`, `import`, `call`, `inherits`, `ref`, `loads`, `tests`, `http`, `rpc`, `handles`, `env`, `data`, `event`, `depends`, `cochange`.

## Flujo recomendado

1. **Contexto para la tarea**: `context_for("<lo que vas a hacer>")`. Devuelve los símbolos relevantes con firma, doc, rango de líneas y el código clave dentro del presupuesto. Empieza siempre aquí.
2. **Leer código**: `read_symbol` con la clave; no abras archivos completos.
3. **Seguir vínculos**: `node_context` (llamadas, herencia, tests, rutas, variables, dependencias), `find_path` para «cómo llega A a B», `endpoints` para conexiones entre servicios.
4. **Antes de editar**: `impact_analysis` sobre lo que vas a tocar.
5. **Después de editar**: `review_changes` (`--worktree` para cambios sin commitear): símbolos tocados, impacto, tests a correr y riesgo.
6. **Panorama**: `project_overview` y `architecture` (entradas, capas, ciclos, código muerto, puntos calientes).

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
