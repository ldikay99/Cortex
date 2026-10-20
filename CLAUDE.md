# Córtex

Convierte un repositorio en cualquier lenguaje en un grafo de conocimiento versionado que los agentes consultan (MCP, CLI, HTTP) y lo muestra como un universo 3D que una araña teje archivo por archivo.

## Dónde está cada cosa

- `src/`: web Three.js, empaquetada con esbuild en `app.js`. `index.html` y `style.css` en la raíz.
- `analyzer/cortex_graph/`: analizador (`analyze` orquesta, comunidades y layout; `pyast` Python; `tsjs` TS/JS; `langs` otros 26 lenguajes; `generic` configuración y respaldo; `importers` historiales de chat (ChatGPT, Claude, WhatsApp, Telegram, Slack, Discord, JSON/JSONL); `documents` PDF, DOCX, ODT, HTML, correo, calendario y CSV; `extract` extracción determinista de personas, temas y fechas; `content` notas Markdown/Obsidian/Logseq; `brain` memoria personal (remember, recall, forget, profile, timeline); `overlay` grafo escrito por agentes (`graph_guide`, `graph_add`, `graph_remove`, `graph_overlay`, `--ai`); `llm` cliente opcional de la API de Claude para `--ai`; `common`, `store`, `pipeline`, `query`, `server`, `mcp_server`, `cli`). Tests en `analyzer/tests/`.
- Nuevo lenguaje: una entrada en `LANGS` de `langs.py`, su gramática fijada en `analyzer/pyproject.toml` y un test en `tests/test_langs_extra.py`.
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

## Memoria personal

Si el usuario tiene memoria (proyecto `memoria` por defecto, o `CORTEX_MEMORY_PROJECT`):

- Antes de responder preguntas personales o que dependan de quién es el usuario (preferencias, personas, proyectos, decisiones pasadas), llama `recall`; al empezar una conversación, lee `profile` o `cortex://profile/<proyecto>`.
- Guarda con `remember` los datos duraderos: preferencias, instrucciones, decisiones, metas y datos de personas cercanas. No guardes lo efímero ni lo que el usuario acaba de pedir en la tarea.
- Nunca guardes secretos (contraseñas, tokens, claves, números de cuenta) aunque el usuario los mencione.
- Cuando pida olvidar algo, usa `forget` y confirma solo después de borrarlo.

## Skills y agentes

- `.claude/skills/cortex-dev`: arquitectura, comandos, convenciones, checklist de versión.
- `.claude/skills/cortex-knowledge-graph`: cómo consultar el grafo de cualquier repo.
- `.claude/skills/cortex-reel`: grabar demos y reels.
- `.claude/agents/`: `cortex-analyst`, `cortex-maintainer`, `cortex-graph-auditor`.

— Creado por Jonathan C (ldikay99) · Colombia
