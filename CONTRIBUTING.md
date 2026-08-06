# Contributing to Mnemo

Mnemo is in staged engineering development. Contributions must respect the
accepted architecture, roadmap phase boundaries, and ADRs.

## Before opening a change

1. Read the architecture specification, engineering roadmap, and accepted ADRs.
2. Keep work within the active roadmap module.
3. Open an architecture proposal before changing a public contract, layer
   boundary, storage choice, or lifecycle rule.
4. Do not add business logic to `mnemo-server` or transport dependencies to
   `mnemo-core`.

## Local verification

Run these checks before submitting a pull request:

```shell
uv sync --locked --all-packages
uv run ruff format --check .
uv run ruff check .
uv run mypy mnemo-core/mnemo mnemo-server/mnemo_server
uv run pytest
uv run pre-commit run --all-files
uv build --package mnemo-core
uv build --package mnemo-server
```

Changes to `mnemo-ui` must also pass its format, lint, typecheck, test, and build
scripts.

Use conventional commit subjects. Pull requests should explain their roadmap
scope, tests, public API impact, and any ADR implications.
