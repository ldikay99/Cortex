---
name: cortex-dev
description: Develop Córtex itself (the 3D web in src/ and the Python analyzer in analyzer/cortex_graph/). Use when changing the visualization, the analyzer, the CLI, the MCP server or the HTTP API, when running builds and tests, or when preparing a release.
---

# Desarrollar Córtex

## Mapa

**Web** (`src/`, empaquetada con esbuild en `app.js`, servida por nginx):

| Archivo | Rol |
| --- | --- |
| `main.js` | Arranque, detección de WebGL2, errores globales |
| `cortex.js` | Orquestador: escena, cámara, UI, atajos, búsqueda, cine, grabación, flujo de proyectos |
| `project.js` | Cliente de la API (`api/…`) y streaming NDJSON con reintentos y reanudación |
| `weaver.js` | Ordena el tejido nodo a nodo según la velocidad |
| `spider.js` | Tarántula de líneas cian, su andar y sus saltos |
| `graph.js` | Nodos y relaciones en buffers (`EDGE` define los tipos) |
| `cosmos.js` | Nebulosas por comunidad, galaxias, tormentas |
| `nest.js` | Nido geodésico de seda y núcleo que late |
| `sky.js`, `lightning.js` | Fondo estelar y relámpagos |
| `materials.js` | Shaders de puntos y líneas |
| `communities.js` | Panel de comunidades y nodos más conectados |
| `recorder.js` | Grabación WebM del canvas |
| `storage.js`, `toast.js`, `rand.js` | Utilidades |

`index.html` y `style.css` contienen el marcado y estilo de la UI.

**Analizador** (`analyzer/cortex_graph/`, paquete `cortex-graph`, comando `cortex`):

| Archivo | Rol |
| --- | --- |
| `analyze.py` | Análisis Python/TS/Markdown, comunidades Leiden, layout, exportaciones `grafo.md` / `grafo.json` |
| `store.py` | Persistencia en `datos/`, versiones, diff por hash, estabilización del layout, validación de `.cortex.json` |
| `pipeline.py` | Fuente local o GitHub (clon superficial), análisis y guardado |
| `query.py` | Índice y consultas: overview, search, node, file, community, path, impact, changes, report |
| `server.py` | API HTTP: subida, clon, revisión, análisis, stream, export, `/api/query/*` |
| `mcp_server.py` | Servidor MCP (FastMCP) con 11 herramientas |
| `cli.py` | CLI `cortex` |
| `errors.py` | `CortexError`, `NotFound`, `InvalidInput`, `Conflict` |

Tests: `analyzer/tests/` (pytest) y `tests/e2e/smoke.mjs` (Playwright contra la app levantada).

## Comandos

```bash
npm ci
npm run build                      # src/ → app.js
npm run dev                        # build en watch

cd analyzer && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
cd analyzer && .venv/bin/pytest -q

docker compose up -d --build       # web en http://localhost:8090
docker compose logs -f analyzer
docker compose down

npm run test:e2e                   # requiere la app arriba; CORTEX_URL, CHROME_PATH, CORTEX_SAVED
```

`CORTEX_SAVED` debe nombrar un grafo ya guardado en `datos/` (analiza uno antes, p. ej. `docker exec cortex-analyzer cortex analyze https://github.com/fastapi/full-stack-fastapi-template`).

## Convenciones

- **Sin comentarios** en el código. Nombres claros en su lugar.
- **UI en español**, en minúsculas y con tono sereno (`despertando`, `tejido a 2×`). Mensajes de error del analizador también en español; descripciones de herramientas MCP en inglés.
- **Estética**: brillo suave, líneas finas, nada de deslumbramientos. Fondo `#020309`, cian `rgb(140 220 245)`, núcleo `#ffe6c2`. Cualquier efecto nuevo debe verse bien en modo cine y en una grabación.
- **Contrato de la API**: rutas `/api/*`, formato `cortex-grafo/1`, firmas de herramientas MCP y salida `--json` de la CLI son públicos. Si cambian, actualiza tests, README y la skill `cortex-knowledge-graph`.
- **Determinismo**: el mismo código da el mismo grafo y el mismo layout (semillas fijas, orden estable).
- No se versiona `datos/` ni `app.js`.

## Antes de terminar

1. `npm run build` sin errores.
2. `pytest -q` en `analyzer/` en verde.
3. `docker compose up -d --build` y `npm run test:e2e` en verde.
4. Verificación en el navegador: tejer un repo, panel de comunidades, búsqueda, modo cine, grabar 5 s, consola sin errores.

## Checklist de versión

- Versión en `package.json` y `analyzer/pyproject.toml` (y `__version__` en `cortex_graph/__init__.py`).
- CI de GitHub Actions en verde (pytest, build, `docker compose build`).
- README: capturas y GIF en `docs/media/` al día con la UI.
- Probar el MCP: `docker exec -i cortex-analyzer cortex mcp` desde un cliente y llamar `project_overview`.
- Probar un `.cortex.json` exportado reimportándolo.

— Creado por Jonathan C (ldikay99) · Colombia
