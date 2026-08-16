FROM python:3.12-slim

RUN python -m pip install --no-cache-dir uv==0.12.2
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY mnemo-core/pyproject.toml mnemo-core/pyproject.toml
COPY mnemo-core/README.md mnemo-core/README.md
COPY mnemo-server/pyproject.toml mnemo-server/pyproject.toml
COPY mnemo-server/README.md mnemo-server/README.md
COPY mnemo-core/mnemo mnemo-core/mnemo
COPY mnemo-server/mnemo_server mnemo-server/mnemo_server

RUN uv sync --frozen --no-dev --package mnemo-server

# Start the production Mnemo FastAPI ASGI server
CMD [".venv/bin/mnemo", "serve", "--host", "0.0.0.0", "--port", "8000"]

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD .venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1
