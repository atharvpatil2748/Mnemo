FROM python:3.12-slim

RUN python -m pip install --no-cache-dir uv==0.12.2
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY mnemo-core/pyproject.toml mnemo-core/pyproject.toml
COPY mnemo-server/pyproject.toml mnemo-server/pyproject.toml
COPY mnemo-core/mnemo mnemo-core/mnemo
COPY mnemo-server/mnemo_server mnemo-server/mnemo_server

RUN uv sync --frozen --no-dev --package mnemo-core

CMD [".venv/bin/python", "-c", "import mnemo; print(mnemo.__version__)"]
