# Córtex · guía para agentes

Córtex convierte un repositorio en un grafo de conocimiento determinista y versionado (Python `ast`, TS/TSX/JS con tree-sitter, Markdown, comunidades Leiden) y lo muestra como un universo 3D. Los agentes lo consultan por MCP, CLI o HTTP.

## Estructura

- `src/`: web Three.js → `app.js` con esbuild. `index.html`, `style.css` en la raíz.
- `analyzer/cortex_graph/`: analizador, almacenamiento, consultas, API HTTP, servidor MCP y CLI `cortex`. Tests en `analyzer/tests/`.
- `tests/e2e/smoke.mjs`: humo con Playwright (`CORTEX_URL`, `CHROME_PATH`, `CORTEX_SAVED`).
- `datos/<proyecto>/`: salida generada (`v<n>.cortex.json`, `historial.json`, `grafo.md`, `grafo.json`). No se versiona.

## Comandos

```bash
npm ci && npm run build
cd analyzer && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]' && .venv/bin/pytest -q
docker compose up -d --build        # web en http://localhost:8090, analizador en el contenedor cortex-analyzer
npm run test:e2e
```

## Usar el grafo

- MCP: `docker exec -i cortex-analyzer cortex mcp` (11 herramientas: `list_projects`, `analyze_project`, `project_overview`, `search_code`, `node_context`, `file_context`, `community_context`, `find_path`, `impact_analysis`, `changes`, `get_report`).
- CLI: `cortex analyze|projects|overview|search|node|file|community|path|impact|changes|export … [--json]`.
- HTTP: `/api/query/overview|search|node|file|community|path|impact|changes`.
- Sin servidor: lee `datos/<proyecto>/grafo.md`.

Flujo: overview → search → node/file/community → impact antes de editar → changes después de reanalizar. Cita siempre `archivo:línea`.

## Reglas

- Sin comentarios en el código. UI en español, brillo suave, líneas finas.
- Contrato público estable (`/api/*`, `cortex-grafo/1`, MCP, `--json`); si cambia, actualiza tests y documentación.
- Build, pytest y e2e en verde antes de terminar.
- Nunca commitear ni borrar `datos/`; no tocar `_original/`.

Detalle ampliado en `.claude/skills/*/SKILL.md`.

— Creado por Jonathan C (ldikay99) · Colombia
