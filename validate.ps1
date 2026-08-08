$ErrorActionPreference = "Stop"
uv run ruff format .
uv run ruff check .
uv run mypy --strict mnemo-core/mnemo mnemo-core/tests mnemo-server/mnemo_server
uv run pytest --cov=mnemo --cov-report=term-missing
uv run pre-commit run --all-files
uv build --package mnemo-core --package mnemo-server
