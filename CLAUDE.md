# Córtex

Convierte un repositorio en un grafo de conocimiento versionado que los agentes consultan (MCP, CLI, HTTP) y lo muestra como un universo 3D que una araña teje archivo por archivo.

## Dónde está cada cosa

- `src/`: web Three.js, empaquetada con esbuild en `app.js`. `index.html` y `style.css` en la raíz.
- `analyzer/cortex_graph/`: analizador Python (`analyze`, `store`, `pipeline`, `query`, `server`, `mcp_server`, `cli`). Tests en `analyzer/tests/`.
- `tests/e2e/smoke.mjs`: prueba de humo con Playwright contra la app levantada.
- `datos/<proyecto>/`: versiones, `historial.json`, `grafo.md`, `grafo.json`. Generado, no se versiona.
- `.mcp.json`: servidor MCP `cortex` vía `docker exec -i cortex-analyzer cortex mcp`.

## Comandos

```bash
npm ci && npm run build
cd analyzer && .venv/bin/pytest -q
docker compose up -d --build        # http://localhost:8090
npm run test:e2e
```

## Reglas

- Sin comentarios en el código.
- UI en español; brillo suave y líneas finas.
- Contrato público estable: `/api/*`, formato `cortex-grafo/1`, herramientas MCP, `--json` de la CLI.
- Build, pytest y e2e en verde antes de terminar; verificar en el navegador si el cambio es visible.
- Nunca commitear ni borrar `datos/`; no tocar `_original/`.

## Skills y agentes

- `.claude/skills/cortex-dev`: arquitectura, comandos, convenciones, checklist de versión.
- `.claude/skills/cortex-knowledge-graph`: cómo consultar el grafo de cualquier repo.
- `.claude/skills/cortex-reel`: grabar demos y reels.
- `.claude/agents/`: `cortex-analyst`, `cortex-maintainer`, `cortex-graph-auditor`.

— Creado por Jonathan C (ldikay99) · Colombia
