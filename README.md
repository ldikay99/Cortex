<p align="center">
  <img src="docs/media/cover.png" alt="Córtex: teje el grafo de conocimiento de tu código" width="100%" />
</p>

<h3 align="center">Tu código, tus notas y tus chats, convertidos en una memoria viva que cualquier IA puede consultar.</h3>

<p align="center">
  <em><b>TL;DR</b>: Córtex turns any repository, in any language, and your notes, chats and documents into a living, versioned knowledge graph that AI agents query through MCP, a CLI or HTTP,<br />
  and renders it as a 3D universe woven file by file by a wireframe spider. Deterministic, local, one <code>docker compose up</code> away.</em>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/licencia-MIT-8cdcf5?style=flat-square" alt="Licencia MIT" /></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-8cdcf5?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/Three.js-r170-8cdcf5?style=flat-square&logo=threedotjs&logoColor=white" alt="Three.js" />
  <img src="https://img.shields.io/badge/lenguajes-26%2B-8cdcf5?style=flat-square" alt="26+ lenguajes" />
  <img src="https://img.shields.io/badge/MCP-28%20herramientas-8cdcf5?style=flat-square" alt="MCP" />
  <img src="https://img.shields.io/badge/Docker-compose-8cdcf5?style=flat-square&logo=docker&logoColor=white" alt="Docker" />
</p>

<p align="center">
  <img src="docs/media/preview.gif" alt="La araña teje el grafo de un repositorio" width="720" />
</p>

<p align="center">
  <a href="docs/media/demo.mp4"><b>▶ Ver el video</b></a> &nbsp;·&nbsp;
  <a href="#empieza-en-1-minuto">Empieza en 1 minuto</a> &nbsp;·&nbsp;
  <a href="#para-tu-ia">Para tu IA</a> &nbsp;·&nbsp;
  <a href="#tu-segundo-cerebro">Tu segundo cerebro</a>
</p>

---

## Por qué

Toda IA que entra a un repositorio llega sin memoria. Abre archivos, adivina, vuelve a empezar.

**Córtex le entrega el mapa antes de la primera pregunta**, y te deja verlo nacer.

- **Memoria, no búsqueda.** Cada archivo, clase y función con su lugar exacto y sus vínculos. Tu IA deja de adivinar.
- **Recuerda lo que cambió.** Cada análisis es una versión; lo nuevo, lo modificado y lo que desapareció quedan registrados.
- **Cualquier stack.** Go, Rust, Java, C#, PHP, Ruby, Swift, Kotlin, C/C++, Python, TypeScript y quince más, junto con su Docker, su CI, su SQL y su Terraform.
- **Siempre lo mismo.** Por defecto, sin modelos ni tokens: el mismo código, el mismo mapa.
- **Un espectáculo.** Tu arquitectura convertida en universo, lista para grabar.

## Galería

<table>
  <tr>
    <td width="50%"><img src="docs/media/tejiendo.jpg" alt="La araña tejiendo" /><p align="center"><sub>La araña teje archivo por archivo</sub></p></td>
    <td width="50%"><img src="docs/media/universo.jpg" alt="El universo completo" /><p align="center"><sub>Cada comunidad, una nebulosa</sub></p></td>
  </tr>
  <tr>
    <td><img src="docs/media/nido.jpg" alt="El nido" /><p align="center"><sub>El nido late en el centro</sub></p></td>
    <td><img src="docs/media/ficha.jpg" alt="Ficha de un nodo" /><p align="center"><sub>Cada nodo, con su contexto</sub></p></td>
  </tr>
  <tr>
    <td><img src="docs/media/revision.jpg" alt="Revisión antes de tejer" /><p align="center"><sub>Eliges qué se teje</sub></p></td>
    <td><img src="docs/media/fondo.jpg" alt="Fondo de pantalla" /><p align="center"><sub>Tu código como fondo</sub></p></td>
  </tr>
</table>

## Para tu IA

Tu agente no abre archivos a ciegas: le pide a Córtex **el contexto justo para su tarea**, dentro de su presupuesto de tokens, y lee solo el código que importa.

| Pregunta | Herramienta |
| --- | --- |
| «Voy a tocar el login: dame contexto» | `context_for` → paquete priorizado con firmas, docs y código en ≤ 8k tokens |
| «Muéstrame `validate`» | `read_symbol` → el código exacto, con secretos redactados |
| «¿Qué se rompe si cambio `mutateElement`?» | `impact_analysis` |
| «Revisa mi diff antes del PR» | `review_changes` → símbolos tocados, impacto, tests que corren y riesgo 0–100 |
| «¿Quién llama a `POST /orders`?» | `endpoints` → rutas HTTP y RPC con su handler y sus clientes, aunque estén en otro servicio u otro lenguaje |
| «¿Quién usa `axios`?» | `dependencies` |
| «¿Dónde se lee `DATABASE_URL`?» | `variables` |
| «¿Hay ciclos, código muerto o puntos calientes?» | `architecture` |
| «¿Qué sabes de mí sobre esto?» | `recall` → recuerdos vigentes con fecha y fuente, dentro de un presupuesto |
| «Recuerda que prefiero respuestas cortas» | `remember` (y `forget` para borrarlo) |

28 herramientas MCP (18 de código, 6 de [memoria](#tu-segundo-cerebro): `remember`, `recall`, `forget`, `profile`, `timeline`, `import_history`, y 4 para [que tu IA escriba el grafo](#grafo-hecho-por-tu-ia)), más recursos (`cortex://<proyecto>/overview`, `cortex://profile/<proyecto>`) y prompts listos (`orient`, `plan_change`, `review`, `explain`, `build_graph`). Lo mismo está en la **CLI** (`cortex … --json`) y en la **API HTTP** (`/api/query/*`).

**Conéctalo a tu cliente** con un comando: Claude Code, Claude Desktop, Cursor, VS Code/Copilot, Windsurf/Devin, Zed, Codex, Gemini CLI, Continue o Cline.

```bash
cortex mcp-config cursor --mode uvx --install
```

**Y que el repo se explique solo**: `cortex context-files` escribe `AGENTS.md`, `CLAUDE.md`, `llms.txt`, reglas de Cursor y de Copilot a partir del grafo, sin tocar lo que ya escribiste.

## Grafo hecho por tu IA

Donde el análisis estático no llega (lenguajes raros, flujos definidos en configuración, procesos de negocio) o cuando quieres más que símbolos, tu IA completa el grafo a su manera: **componentes** (servicios, pantallas, capas, almacenes, sistemas externos), **flujos** con pasos ordenados, relaciones `uses` y resúmenes sobre cualquier nodo. Se guarda en un registro propio (`datos/<proyecto>/agente.jsonl`), crea una versión nueva y se ve en la web igual que lo demás, con su marca «agente» o «IA».

- MCP: `graph_guide` da la lista de trabajo (archivos sin analizar, comunidades sin componente, archivos sin resumen, endpoints o variables sin pareja); `graph_add` añade en lotes validados; `graph_overlay` y `graph_remove` revisan y deshacen. El prompt `build_graph` guía el proceso.
- CLI: `cortex graph guide|add lote.json|list|remove ID…`. HTTP: `GET/POST /api/overlay`, `POST /api/overlay/remove`.
- Sin agente: `cortex analyze <carpeta> --ai` pide a la API de Claude componentes, flujos y resúmenes por comunidad (envía código con los secretos redactados; avisa y pide confirmación; requiere `ANTHROPIC_API_KEY`).

Una carpeta con archivos que Córtex no entiende también sirve: cada archivo queda como nodo y tu IA lo describe.

## Tu segundo cerebro

Córtex también guarda lo que sabes de ti. Tus chats, notas y documentos se convierten en una memoria personal que tu IA consulta antes de responder.

- **Recuerda y olvida.** `remember` guarda un dato con su categoría y su fecha; `forget` lo borra, también del texto de versiones anteriores.
- **Sabe lo vigente.** Un dato nuevo reemplaza al anterior: si te mudas, «vivo en Bogotá» sustituye a «vivo en Madrid». `recall --en AAAA-MM-DD` responde con lo que era cierto en esa fecha.
- **Responde dentro de tu presupuesto.** `recall` devuelve solo la evidencia que cabe en los tokens que le des, con su fecha y su fuente: primero los recuerdos y después los mensajes más relevantes, agrupados por conversación en orden cronológico (`- AAAA-MM-DD HH:MM Autor: texto`).
- **Entiende cómo preguntas.** Busca en inglés y español con raíces, sinónimos, nombres de quien habla y fechas. Tu IA puede pasar `hints` (sinónimos, traducciones, posibles respuestas) que cuentan menos que la pregunta; en la CLI es `--pistas`.
- **Embeddings locales, si quieres.** Con el extra `semantic` (`pip install "cortex-graph[semantic]"`), `recall` suma similitud semántica con un modelo estático pequeño (`minishlab/potion-base-8M`, 30 MB, se descarga una vez). Para conversaciones sobre todo en español, usa `CORTEX_EMBED_MODEL=minishlab/potion-multilingual-128M` (530 MB); `CORTEX_EMBED_MODEL=off` lo desactiva. Sin el extra, todo sigue igual.
- **Perfil listo para tu IA.** `profile` genera un Markdown compacto para las instrucciones de sistema, y `timeline` ordena tu historia por fechas.

```bash
cortex import ~/exports                  # chats, notas, PDFs, correos… (carpeta o archivo)
cortex recall "¿dónde trabajo y con quién?"
cortex remember "prefiero respuestas cortas" --categoria preference
cortex profile --budget 800              # perfil para las instrucciones de tu IA
cortex forget "vivo en Madrid"
cortex mcp-config claude-code --mode uvx --install   # tu IA ya usa tu memoria
```

| Fuente | Formatos |
| --- | --- |
| Chats | Exportaciones de ChatGPT y Claude, transcripciones de Claude Code (`.jsonl`), WhatsApp, Telegram, Slack, Discord, JSON/JSONL y Markdown genéricos |
| Notas | Markdown, Obsidian y Logseq: `[[wikilinks]]`, `#etiquetas` y frontmatter |
| Documentos | PDF (extra `docs`), DOCX, ODT, HTML, RTF, TXT, CSV y TSV |
| Correo y agenda | `.eml`, `.mbox`, `.ics` |
| Subtítulos y transcripciones | `.srt`, `.vtt` |

- **Local por defecto.** `cortex import` extrae personas, temas, eventos y recuerdos sin modelos: nada sale de tu equipo.
- **La nube, solo si la pides.** `cortex import RUTA --ai` envía el texto a la API de Claude para extraer recuerdos. Requiere el extra `ai` (`pip install "cortex-graph[ai]"`) y `ANTHROPIC_API_KEY`; avisa antes de enviar, redacta secretos y usa `claude-opus-5-5` salvo que definas `CORTEX_AI_MODEL`. `--batch` cuesta menos pero tarda más. Con Docker, pasa la clave en el entorno de `docker compose`.
- **Sin secretos.** Tokens, contraseñas y claves se redactan al guardar. Tu memoria vive en `CORTEX_DATA` o en la carpeta de datos de tu sistema.

## Empieza en 1 minuto

```bash
git clone https://github.com/ldikay99/Cortex.git && cd Cortex
docker compose up -d
```

Abre **http://localhost:8090**, elige una carpeta, un `.zip` o una URL de GitHub, revisa qué carpetas entran y pulsa **Tejer**.

> Para repos privados de GitHub: `GITHUB_TOKEN=ghp_… docker compose up -d`.

**Sin Docker**, solo la CLI y el MCP (Python 3.11–3.13):

```bash
uvx --from git+https://github.com/ldikay99/Cortex#subdirectory=analyzer cortex analyze ./mi-repo
uvx --from git+https://github.com/ldikay99/Cortex#subdirectory=analyzer cortex mcp
```

<details>
<summary>Más formas de usarlo</summary>

```bash
cortex analyze https://github.com/excalidraw/excalidraw
cortex context "cómo se valida un request" --project gin
cortex review --worktree                 # tus cambios sin commitear
cortex watch .                           # reanaliza al guardar
cortex hook install                      # reanaliza en cada commit
cortex analyze . --scip index.scip       # modo preciso con un índice SCIP
```

Imágenes publicadas: `ghcr.io/ldikay99/cortex-web` y `ghcr.io/ldikay99/cortex-analyzer`. Los datos viven en `CORTEX_DATA`, en `./datos` si existe, o en la carpeta de datos de tu sistema.

Configura cada repo con `.cortex.toml` (`name`, `exclude`, `include_tests`, `git`) y `.cortexignore` (sintaxis de `.gitignore`).

</details>

## Por dentro

- **Más de 25 lenguajes con su árbol de sintaxis real:** Python (y notebooks), TypeScript, JavaScript, Vue, Svelte, Go, Rust, Java, Kotlin, Scala, Groovy, C#, F#, PHP, Ruby, C, C++, Objective-C, Swift, Dart, Elixir, Haskell, OCaml, Julia, Lua, Perl, Zig, Solidity, Bash, PowerShell y Terraform. Cada símbolo trae firma, documentación, rango de líneas y visibilidad.
- **Puentes entre servicios:** rutas HTTP de una veintena de frameworks unidas a sus clientes, gRPC de punta a punta, tablas SQL usadas desde el código, variables de entorno, colas y eventos.
- **Dependencias externas** de npm, PyPI, Go, Cargo, Maven/Gradle, NuGet, Composer, RubyGems y más, con quién las usa.
- **La infraestructura también es código:** compose, CI, Make, Kubernetes, Helm, Ansible, CloudFormation/SAM, Bicep, dbt, protobuf, GraphQL, Prisma, plantillas (Razor, Blade, ERB, Jinja, Twig) y legado (COBOL, PL/SQL, T-SQL, Fortran, VB, ABAP, Apex).
- **Historia de git:** archivos calientes, quién cambia con quién y riesgo de cada cambio.
- **Siempre al día:** un repo sin cambios se revisa en milisegundos y, en repos medianos, un cambio pequeño se reanaliza en menos de un segundo.
- **Calidad medida** contra índices SCIP de compilador: en Python y Go, 98–100 % de precisión y 93–100 % de cobertura en llamadas y dependencias ([`bench/`](bench)).
- **Memoria medida** en LoCoMo (1 536 preguntas sobre conversaciones largas, todo local y sin IA): `recall` encuentra el 83 %, el 89 % y el 94 % de la evidencia con presupuestos de 1 000, 2 000 y 4 000 tokens, y el 84 %, el 90 % y el 95 % con los embeddings locales opcionales (extra `semantic`). Con 2 000 tokens llega a la sesión correcta en el 97 % de las preguntas, en ~20 ms. Las muestras 5-9, que no se usaron para afinar, dan resultados parecidos ([`bench/memory`](bench/memory)).
- Comunidades descubiertas solas, con nombre propio; versiones con diff por contenido y un mapa que no se reacomoda.

## Atajos

| Tecla | Acción |
| --- | --- |
| <kbd>/</kbd> | Buscar archivo, clase o función |
| <kbd>F</kbd> | Cámara que persigue a la araña |
| <kbd>H</kbd> | Modo cine (sin interfaz) |
| <kbd>?</kbd> | Ayuda y leyenda |
| <kbd>W</kbd> <kbd>A</kbd> <kbd>S</kbd> <kbd>D</kbd> <kbd>Q</kbd> <kbd>E</kbd> | Desplazar la cámara |
| <kbd>Esc</kbd> | Cerrar paneles |
| Clic en una nebulosa | La araña viaja hasta allí |

Velocidad del tejido de 0.5× a 4× desde la barra (o `?velocidad=2` en la URL). El botón ● graba un reel WebM solo de la escena 3D.

## Bajo el capó

**Web** Three.js · shaders propios · esbuild · nginx &nbsp;|&nbsp; **Analizador** Python 3.12 · ast · tree-sitter · igraph + leidenalg · NetworkX · MCP SDK &nbsp;|&nbsp; **Calidad** pytest · Playwright e2e · GitHub Actions &nbsp;|&nbsp; **Entrega** Docker Compose

Para agentes que trabajan en este repo: [`CLAUDE.md`](CLAUDE.md), [`AGENTS.md`](AGENTS.md), skills en [`.claude/skills`](.claude/skills) y subagentes en [`.claude/agents`](.claude/agents).

## Autor

<p>
  <a href="https://github.com/ldikay99"><b>Jonathan C (ldikay99)</b></a> · Colombia<br />
  Ingeniero de Software especializado en IA: ingeniería de prompts, skills y agentes, orquestación multiagente, MCP, entrenamiento y ajuste de modelos, RAG y grafos de conocimiento, plataformas de IA.
</p>

Si Córtex te sirve, una ⭐ ayuda a que más gente lo encuentre.

## Licencia

[MIT](LICENSE) © 2026 Jonathan C (ldikay99)
