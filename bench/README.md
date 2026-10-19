# Benchmark de precisión (SCIP)

Mide la calidad real del grafo de Córtex comparándolo con índices [SCIP](https://github.com/sourcegraph/scip) generados por indexadores con resolución de tipos (scip-python, scip-go, scip-typescript).

## Qué mide

Solo cuentan los archivos presentes en el índice SCIP (y dentro de `scope`, si el repo lo define).

| métrica | verdad de referencia (SCIP) | lado Córtex |
|---|---|---|
| dependencias entre archivos | A → B si A referencia un símbolo definido en B | cualquier arista entre nodos de A y B (salvo `contains`/`cochange`) |
| llamadas | ocurrencia de función/método/clase seguida de `(`, atribuida al ámbito (`enclosing_range`) más interno | aristas `call` y `tests` |
| definiciones | funciones, métodos y tipos definidos | nodos `function`/`method`/`class` del mismo archivo y nombre (±3 líneas) |

Los símbolos SCIP se proyectan sobre claves de Córtex por archivo + línea (`line`..`end`, o el símbolo anterior más cercano si no hay `end`). Las llamadas a métodos de interfaz que Córtex resuelve a una implementación (relación `is_implementation`) no cuentan como falso positivo. La fila «modo preciso» repite la medida tras `scip.apply_scip`.

## Uso

```sh
cd analyzer
.venv/bin/python ../bench/run.py --tools ~/scip-tools          # todos los repos de repos.toml (salvo skip = true)
.venv/bin/python ../bench/run.py --only flask --reuse           # reutiliza el índice ya generado
.venv/bin/python ../bench/run.py --index gin=/ruta/gin.scip     # índice propio, sin ejecutar el indexador
```

- `--work` (o `CORTEX_BENCH_WORK`, por defecto `~/.cache/cortex-bench`): clones e índices. Nunca dentro del repo.
- `--tools` (o `CORTEX_BENCH_TOOLS`): carpeta con `bin/` (scip-go, scip) y `node_modules/.bin` (scip-python, scip-typescript); se antepone al `PATH`.
- Salida: `bench/results/results.json` y `bench/results/RESULTS.md` (tabla + 10 patrones principales de falsos positivos/negativos por repo, con `archivo:línea`).

## Instalar los indexadores (fuera del repo)

```sh
mkdir -p ~/scip-tools/bin && cd ~/scip-tools
npm install --ignore-scripts @sourcegraph/scip-python@0.6.6 @sourcegraph/scip-typescript@0.4.0
gh release download v0.2.7 -R sourcegraph/scip-go -p 'scip-go-linux-amd64.tar.gz*'
sha256sum -c scip-go-linux-amd64.tar.gz.sha256 && tar xzf scip-go-linux-amd64.tar.gz -C bin
```

## Seguridad

Los repos de `repos.toml` son datos no confiables: se clonan con hooks desactivados, se fija el commit exacto y los indexadores solo los leen. scip-python recibe un entorno vacío (`--environment`) para no invocar `pip` dentro del repo; scip-go usa `GOTOOLCHAIN=local` y `CGO_ENABLED=0`. Si un repo necesita dependencias para resolver tipos (TypeScript), `prepare` usa siempre `npm install --ignore-scripts`; nunca se ejecutan scripts del repo.

## Añadir un repo

Una entrada `[[repo]]` en `repos.toml` con `name`, `language`, `url`, `commit` y `indexer` (marcadores `{src}`, `{index}`, `{work}`). Opcionales: `cwd = "src"`, `env`, `subdir`, `scope`, `prepare`, `skip`.
