# Córtex · guía para agentes

Córtex convierte un repositorio en un grafo de conocimiento determinista y versionado (26 lenguajes con árboles de sintaxis tree-sitter (Python con `ast`), más configuración e infraestructura y un respaldo heurístico para el resto; comunidades Leiden) y lo muestra como un universo 3D. Los agentes lo consultan por MCP, CLI o HTTP.

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

- MCP: `docker exec -i cortex-analyzer cortex mcp` o `uvx --from git+https://github.com/ldikay99/Cortex#subdirectory=analyzer cortex mcp` (18 herramientas, recursos `cortex://` y prompts).
- CLI: `cortex analyze|context|read|search|node|file|community|path|impact|review|architecture|deps|endpoints|vars|changes|watch|hook|context-files|mcp-config|export … [--json]`.
- HTTP: `/api/query/*` con los mismos nombres.
- Sin servidor: lee `datos/<proyecto>/grafo.md`.

Flujo: `context_for` con la tarea → `read_symbol` en vez de abrir archivos → `node_context`/`find_path` → `impact_analysis` antes de editar → `review_changes` después. Cita siempre `archivo:línea`.

## Reglas

- Sin comentarios en el código. UI en español, brillo suave, líneas finas.
- Contrato público estable (`/api/*`, `cortex-grafo/1`, MCP, `--json`); si cambia, actualiza tests y documentación.
- Build, pytest y e2e en verde antes de terminar.
- Nunca commitear ni borrar `datos/`; no tocar `_original/`.

Detalle ampliado en `.claude/skills/*/SKILL.md`.

— Creado por Jonathan C (ldikay99) · Colombia
