FROM python:3.12-slim
LABEL org.opencontainers.image.title="cortex-analyzer" \
      org.opencontainers.image.description="Córtex: analizador determinista que convierte código, notas, documentos y conversaciones en un grafo de conocimiento y memoria, con CLI, API HTTP y servidor MCP." \
      org.opencontainers.image.source="https://github.com/ldikay99/Cortex" \
      org.opencontainers.image.url="https://github.com/ldikay99/Cortex" \
      org.opencontainers.image.licenses="MIT"
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
RUN python -c "import tomllib; p = tomllib.load(open('pyproject.toml', 'rb'))['project']; print('\n'.join(p['dependencies'] + p['optional-dependencies']['all']))" > /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
COPY cortex_graph ./cortex_graph
RUN pip install --no-cache-dir . && rm -rf /app/build
ENV PORT=8000 PYTHONUNBUFFERED=1 HOME=/tmp CORTEX_DATA=/data HF_HOME=/data/.modelos
EXPOSE 8000
USER nobody
CMD ["cortex", "serve"]
