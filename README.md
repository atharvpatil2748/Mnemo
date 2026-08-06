# Mnemo

Mnemo is a local-first, open-source knowledge engine. It is designed to ingest,
structure, index, retrieve, and cite knowledge from local documents while
remaining independent of agents, tool execution, and transport frameworks.

> **Project status:** Phase 0 and Phase 1 are complete. The repository currently
> provides the typed domain model, core interface contracts, plugin registry,
> immutable configuration system, and `KnowledgeEngine` composition root.
> Storage, parsing, retrieval, REST, MCP, and UI product functionality belong to
> later roadmap phases and are not operational yet.

## Architecture

Mnemo is a from-scratch implementation informed by research into RAGFlow,
RAG-Anything, and Open Notebook. It is not a fork of those projects.

- `mnemo-core`: transport-independent Python domain, contracts, registry,
  configuration, and composition.
- `mnemo-server`: future REST, WebSocket, and MCP adapters with no business
  logic.
- `mnemo-ui`: future standalone browser interface.
- `plugins`: opt-in implementations discovered by the core registry.

The authoritative design and execution documents are:

- [Architecture Specification v2.0](docs/mnemo_architecture_v2.md)
- [Engineering Roadmap v1.0](docs/mnemo_engineering_roadmap.md)
- [Accepted ADRs](docs/adr)
- [Engineering changelog](docs/changelog)

## Development baseline

Requirements:

- Python 3.12
- `uv` 0.12.2 or compatible
- Node.js 22 and pnpm 11.16 for the UI scaffold
- Docker with Compose for container checks

Install and verify the Python workspace:

```shell
uv sync --locked --all-packages
uv run ruff format --check .
uv run ruff check .
uv run mypy mnemo-core/mnemo mnemo-server/mnemo_server
uv run pytest
uv run pre-commit run --all-files
```

Verify the frontend scaffold:

```shell
pnpm --dir mnemo-ui install --frozen-lockfile
pnpm --dir mnemo-ui format:check
pnpm --dir mnemo-ui lint
pnpm --dir mnemo-ui typecheck
pnpm --dir mnemo-ui test
pnpm --dir mnemo-ui build
```

Build the Python distributions:

```shell
uv build --package mnemo-core
uv build --package mnemo-server
```

## Current Python API

```python
from mnemo import KnowledgeEngine, MnemoConfig

config = MnemoConfig.from_file("mnemo.toml")
engine = KnowledgeEngine(config)
await engine.initialize()
await engine.shutdown()
```

Initialization requires plugins that provide the Phase 1 `primary` storage,
embedding, and reranker slots plus the four LLM role slots. Mnemo does not yet
ship those implementations; they are assigned to later roadmap phases.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Architecture changes require review and
an ADR. By participating, contributors agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

## License

Licensed under the [Apache License 2.0](LICENSE).
