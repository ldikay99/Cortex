# Benchmark de memoria (LoCoMo)

Mide cuánta evidencia encuentra `cortex_graph.brain.recall` al preguntar por conversaciones largas, con el conjunto público [LoCoMo](https://github.com/snap-research/locomo) (`data/locomo10.json`, 10 diálogos de varias sesiones con preguntas que citan los mensajes de evidencia, p. ej. `D1:3`).

## Qué hace

1. Descarga `locomo10.json` (commit fijado en `run.py`) a la caché; el dataset nunca se guarda en el repo.
2. Convierte cada diálogo en una carpeta de JSONL genéricos (un archivo por sesión; el hablante A es `user`, el B conserva su nombre; la hora de cada mensaje es la de la sesión más un minuto por turno, y las fotos se añaden como texto con su descripción).
3. Analiza cada carpeta como un proyecto propio, en modo local (sin IA), con `CORTEX_DATA` apuntando a un directorio temporal que se borra al terminar.
4. Para cada pregunta (sin la categoría 5, adversarial) llama a `brain.recall` con presupuestos de 1000, 2000 y 4000 tokens.
5. Lo repite en los dos modos locales: léxico (por defecto, `CORTEX_EMBED_MODEL=off`) y léxico + embeddings (extra `semantic`, modelo de `CORTEX_EMBED_MODEL` o el predeterminado). Ninguno usa IA ni tokens de API; las pistas (`hints`) que añadiría la IA cliente no se miden porque necesitarían un LLM.

## Métricas

- **recall evidencia**: fracción de mensajes de evidencia presentes en el texto devuelto por `recall`.
- **todas halladas**: fracción de preguntas con toda la evidencia recuperada.
- **acierto sesión**: fracción de sesiones de evidencia con al menos un mensaje recuperado.
- Latencia media de `recall` y tokens medios devueltos.

La correspondencia con `dia_id` se hace con las referencias de `items[].messages` (`{file, line}` de cada mensaje devuelto); como respaldo se busca en `markdown` la línea `AAAA-MM-DD HH:MM: <primeros 48 caracteres>` del formato antiguo.

## Cómo recupera `recall` los mensajes

En el modo por defecto todo es local y determinista (numpy/scipy, sin modelos ni red); el índice se construye la primera vez que se consulta un proyecto y queda en caché (`cortex_graph/chatsearch.py`, léxico en `cortex_graph/lexicon.py`):

- **Puntuación por mensaje**: BM25 con un lematizador ligero inglés/español (plurales, tiempos verbales, irregulares frecuentes), palabras con guion unidas (`de-stress` → `destress`), compuestos partidos y corrección de erratas por similitud para términos que no están en el corpus.
- **Hablantes**: los nombres de la pregunta que coinciden con un autor (o con el nombre con que los demás lo llaman, deducido de vocativos como «Hey Mel!» o «gracias, Ana») priorizan los mensajes de esa persona; «yo/mi/I/my» priorizan los del usuario.
- **Expansión semántica** con un léxico genérico de categorías de la vida personal en ambos idiomas (familia, deportes, aficiones, lugares, comida, trabajo, salud, emociones…), sinónimos y traducciones frecuentes, nombres propios y títulos entre comillas como respuesta a «qué ciudad/qué libros», y tipos de respuesta según la pregunta (quién/dónde/cuándo/cuántos).
- **Contexto**: la puntuación se propaga a los mensajes vecinos (sobre todo a la respuesta que sigue a una pregunta) y un poco a toda la sesión; retroalimentación de pseudo-relevancia con los mejores mensajes.
- **Tiempo**: fechas explícitas de la pregunta («en mayo de 2023», «el 7 de mayo») amplían y refuerzan esa ventana.
- **Embeddings locales (opcional)**: con el extra `semantic` (`pip install "cortex-graph[semantic]"`, instala `model2vec==0.10.0`) cada mensaje se convierte en un vector estático (solo numpy, sin GPU). La similitud con la pregunta (sin los nombres de los hablantes) se normaliza, se propaga a los vecinos igual que la léxica y se suma con peso 0,3 a la puntuación BM25 antes de aplicar hablantes, fechas y cobertura. Los vectores se guardan en `<CORTEX_DATA>/<proyecto>/embeddings/` y se invalidan cuando cambia la huella del análisis, el modelo o el texto. El modelo se descarga una vez en la caché de Hugging Face (`HF_HOME`) la primera vez que se usa; si falta el extra, el modelo o la red, `recall` sigue en modo léxico sin avisar.
- **Pistas de la IA (`hints`)**: palabras extra que la IA cliente sabe por su cuenta (sinónimos, traducciones, posibles respuestas) se buscan con la mitad de peso que la pregunta y se suman también a la consulta semántica.
- **Empaquetado**: se eligen mensajes sueltos por puntuación hasta llenar el presupuesto, agrupados por conversación en orden cronológico; cada línea lleva fecha y hora (la fecha solo cuando cambia el día), autor y texto.

### Modelos probados

| modelo (`CORTEX_EMBED_MODEL`) | descarga | licencia | global 1000 / 2000 / 4000 | paráfrasis en español (8 pares, top-1) |
|---|---|---|---|---|
| ninguno (`off`) | 0 | — | 0,826 / 0,888 / 0,938 | — |
| `minishlab/potion-base-8M` (predeterminado, rev. `bf8b0566`) | 30 MB | MIT | 0,840 / 0,905 / 0,949 | 1/8 |
| `minishlab/potion-multilingual-128M` (rev. `73908c34`) | 530 MB | MIT | 0,829 / 0,895 / 0,947 | 6/8 |

En la simulación de afinado, `potion-base-32M` y `potion-retrieval-32M` (130 MB) no mejoraron a `potion-base-8M`. El modelo multilingüe entiende mucho mejor las paráfrasis en español, pero pesa más de 500 MB. Por eso no es el predeterminado: si conversas sobre todo en español, actívalo con `CORTEX_EMBED_MODEL=minishlab/potion-multilingual-128M`. También acepta `repo@revisión` o la ruta de un modelo local.

Los parámetros se afinaron solo con las muestras 0-4 (`--split ajuste`); las 5-9 (`--split control`) sirven de validación y `RESULTS.md` las muestra por separado.

## Uso

```sh
cd analyzer
nice -n 19 .venv/bin/python ../bench/memory/run.py --samples 2
nice -n 19 .venv/bin/python ../bench/memory/run.py
```

- `--samples N`: número de diálogos (por defecto 10).
- `--split ajuste|control|todas`: muestras 0-4, 5-9 o todas (por defecto).
- `--mode lexico|semantico|ambos`: modo léxico, con embeddings o los dos (por defecto). El modo con embeddings necesita el extra `semantic`; el modelo se descarga en `HF_HOME` (pon esa variable en un disco con espacio si hace falta).
- `--cache`: carpeta de descarga (por defecto `CORTEX_BENCH_WORK` o `~/.cache/cortex-bench`).
- `--out`: archivo de resultados (por defecto `bench/memory/results/RESULTS.md`).
