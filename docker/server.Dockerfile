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

# Phase 7 handoff: replace this scaffold process with the FastAPI ASGI entrypoint.
CMD [".venv/bin/python", "-c", "import time; print('Mnemo server Phase 0 scaffold ready', flush=True); time.sleep(2147483647)"]

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD .venv/bin/python -c "import mnemo_server" || exit 1
