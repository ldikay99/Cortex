<p align="center">
  <img src="docs/media/cover.png" alt="Córtex: teje el grafo de conocimiento de tu código" width="100%" />
</p>

<h3 align="center">Tu código, convertido en una memoria viva que cualquier IA puede consultar.</h3>

<p align="center">
  <em><b>TL;DR</b>: Córtex turns any repository, in any language, into a living, versioned knowledge graph that AI agents query through MCP, a CLI or HTTP,<br />
  and renders it as a 3D universe woven file by file by a wireframe spider. Deterministic, local, one <code>docker compose up</code> away.</em>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/licencia-MIT-8cdcf5?style=flat-square" alt="Licencia MIT" /></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-8cdcf5?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/Three.js-r170-8cdcf5?style=flat-square&logo=threedotjs&logoColor=white" alt="Three.js" />
  <img src="https://img.shields.io/badge/lenguajes-26%2B-8cdcf5?style=flat-square" alt="26+ lenguajes" />
  <img src="https://img.shields.io/badge/MCP-18%20herramientas-8cdcf5?style=flat-square" alt="MCP" />
  <img src="https://img.shields.io/badge/Docker-compose-8cdcf5?style=flat-square&logo=docker&logoColor=white" alt="Docker" />
</p>

<p align="center">
  <img src="docs/media/preview.gif" alt="La araña teje el grafo de un repositorio" width="720" />
</p>

<p align="center">
  <a href="docs/media/demo.mp4"><b>▶ Ver el video</b></a> &nbsp;·&nbsp;
  <a href="#empieza-en-1-minuto">Empieza en 1 minuto</a> &nbsp;·&nbsp;
  <a href="#para-tu-ia">Para tu IA</a>
</p>

---

## Por qué

Toda IA que entra a un repositorio llega sin memoria. Abre archivos, adivina, vuelve a empezar.

**Córtex le entrega el mapa antes de la primera pregunta**, y te deja verlo nacer.

- **Memoria, no búsqueda.** Cada archivo, clase y función con su lugar exacto y sus vínculos. Tu IA deja de adivinar.
- **Recuerda lo que cambió.** Cada análisis es una versión; lo nuevo, lo modificado y lo que desapareció quedan registrados.
- **Cualquier stack.** Go, Rust, Java, C#, PHP, Ruby, Swift, Kotlin, C/C++, Python, TypeScript y quince más, junto con su Docker, su CI, su SQL y su Terraform.
- **Siempre lo mismo.** Sin modelos ni tokens en el análisis: el mismo código, el mismo mapa.
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

18 herramientas MCP, más recursos (`cortex://<proyecto>/overview`) y prompts listos (`orient`, `plan_change`, `review`, `explain`). Lo mismo está en la **CLI** (`cortex … --json`) y en la **API HTTP** (`/api/query/*`).

**Conéctalo a tu cliente** con un comando: Claude Code, Claude Desktop, Cursor, VS Code/Copilot, Windsurf/Devin, Zed, Codex, Gemini CLI, Continue o Cline.

```bash
cortex mcp-config cursor --mode uvx --install
```

**Y que el repo se explique solo**: `cortex context-files` escribe `AGENTS.md`, `CLAUDE.md`, `llms.txt`, reglas de Cursor y de Copilot a partir del grafo, sin tocar lo que ya escribiste.

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
