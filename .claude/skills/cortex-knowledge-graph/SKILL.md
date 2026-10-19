---
name: cortex-knowledge-graph
description: Build and query a deterministic knowledge graph of any code repository with Córtex (MCP tools, `cortex` CLI or HTTP API). Use when an agent needs to orient in an unfamiliar codebase, locate where logic lives, trace how two parts connect, estimate the impact of a change before editing, or see what changed between analyses.
---

# Córtex: grafo de conocimiento para agentes

Córtex analiza un repositorio sin IA (Python con `ast`, TS/TSX/JS con tree-sitter, Markdown) y guarda un grafo de módulos, clases, funciones, métodos y documentos unidos por `contains`, `import`, `call`, `inherits`, `ref` y `loads`, agrupados en comunidades (Leiden). Cada análisis es una versión con diff por hash de contenido. Todo resultado cita `archivo:línea`.

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

Herramientas MCP y equivalentes:

| MCP | CLI | HTTP `/api/query/…` |
| --- | --- | --- |
| `list_projects` | `projects` | `/api/projects` |
| `analyze_project(source, name, exclude, include_tests)` | `analyze <carpeta\|url> [--name] [--exclude …] [--tests]` | — (web) |
| `project_overview` | `overview [proyecto]` | `overview?project=` |
| `search_code(query, kind, limit)` | `search <texto> [--kind] [--limit]` | `search?q=&kind=&limit=` |
| `node_context(node)` | `node <ref>` | `node?ref=` |
| `file_context(path)` | `file <ruta>` | `file?path=` |
| `community_context(community)` | `community <id\|nombre>` | `community?ref=` |
| `find_path(source, target)` | `path <a> <b>` | `path?a=&b=` |
| `impact_analysis(node, depth)` | `impact <ref> [--depth]` | `impact?ref=&depth=` |
| `changes(since_version)` | `changes [--since]` | `changes?since=` |
| `get_report` | `export -f md` | `/api/export.md` |

`project` es opcional en todas: por defecto, el proyecto analizado más recientemente. Una referencia de nodo acepta clave (`f:app/services.py:create_user`), nombre, ruta o subcadena.

## Flujo recomendado

1. **Orientarse**: `project_overview`. Lee comunidades (subsistemas), sus hubs, los 20 nodos más conectados, rutas de API y tablas.
2. **Localizar**: `search_code` con 1–3 palabras. Filtra con `kind` (`module|class|function|method|doc`) si hay ruido.
3. **Entender**: `node_context` para un símbolo (quién lo llama, qué importa, qué hereda, qué docs lo mencionan); `file_context` para un archivo; `community_context` para un subsistema completo.
4. **Antes de editar**: `impact_analysis` sobre lo que vas a tocar. Revisa el nivel 1 completo y los archivos afectados; súbele `depth` en cambios de API pública.
5. **Conectar**: `find_path` cuando la pregunta es «cómo llega A a B» (ruta → servicio → modelo).
6. **Después de editar**: reanaliza y usa `changes` para confirmar que solo cambió lo previsto.

Usa `get_report` solo si necesitas el panorama entero: es grande.

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
