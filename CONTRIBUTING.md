# Contributing to Mnemo

Welcome! Mnemo is a local-first, open-source knowledge engine designed to be a permanent, searchable, citation-grounded memory layer.

Mnemo is in staged engineering development and is an architecture-heavy systems project. Because the repository enforces strict boundaries between its layers (Core, Server, UI, and Plugins), all contributions must respect the accepted architecture, roadmap phase boundaries, and Architecture Decision Records (ADRs).

This guide will help you understand how to contribute effectively while maintaining the project's design philosophy.

## 1. What Kind of Contributions Are Useful?

We welcome contributions across the entire stack, provided they align with the current roadmap phase. Useful contributions include:
- Implementing parsers or chunkers as plugins.
- Improving test coverage or writing unit tests for existing modules.
- Fixing bugs in the currently implemented phases (e.g., storage layer, parsers).
- Improving documentation and type annotations.

**Note:** If you want to build a feature that belongs to a future roadmap phase, please open a discussion first so we can coordinate the implementation order.

## 2. Repository Structure

Mnemo follows a strict four-layer model. **No layer may call upward.**

* `mnemo-core/` (Layer 1): Transport-independent Python domain, interface contracts, plugin registry, and composition. **No HTTP or external APIs allowed here.**
* `mnemo-server/` (Layer 2): REST, WebSocket, and MCP adapters. Contains **no business logic**.
* `mnemo-ui/` (Layer 3): Standalone browser interface.
* `plugins/` (Layer 4): Opt-in implementations that fulfill `mnemo-core` interfaces.
* `docs/`: Architecture specifications, roadmaps, and ADRs.

## 3. First Contribution Path

Making your first contribution is straightforward:

**Clone** the repository
↓
**Install** dependencies using `uv`
↓
**Run Validation** to ensure a clean baseline (`validate.bat` on Windows)
↓
**Understand Architecture:** Read the [Architecture Specification](docs/mnemo_architecture_v2.md) and [Roadmap](docs/mnemo_engineering_roadmap.md)
↓
**Pick a Task** relevant to the current phase
↓
**Implement & Test:** Write code with appropriate unit and integration tests covering the relevant behavior and failure modes
↓
**Document:** Add docstrings and update any relevant documentation
↓
**Open a PR**

## 4. Development Setup

Mnemo relies on strict, modern Python and frontend tooling.

**Requirements:**
- Python 3.12
- `uv` (0.12.2+)
- Node.js 22 + pnpm 11.16 (for UI)
- Docker (for database integration testing)

**Setup:**
```shell
uv sync --locked --all-packages
pnpm --dir mnemo-ui install --frozen-lockfile
```

## 5. Running Tests and Validation

Before opening a pull request, you must ensure that your changes pass all checks.

Run the validation script on Windows:
```shell
validate.bat
```

Or manually run the test and validation steps:
```shell
uv run ruff format --check .
uv run ruff check .
uv run mypy mnemo-core/mnemo mnemo-server/mnemo_server
uv run pytest
uv run pre-commit run --all-files
uv build --package mnemo-core
uv build --package mnemo-server
```

## 6. Code Quality Expectations

- **Formatting & Linting:** We use `ruff`. Code must be cleanly formatted and pass all ruff checks.
- **Type Checking:** We use `mypy` in strict mode (`disallow_untyped_defs = true`). Every function signature must be fully typed.
- **Test Coverage:** Our project target is a minimum of **90% coverage** for all Python code. Every new module or plugin should include appropriate unit and integration tests covering the relevant behavior and failure modes in the `tests/` directory.
- **Documentation:** Public classes, methods, and interface contracts must have descriptive docstrings explaining their parameters and return types.

## 7. Architectural Rules

Mnemo's architecture is deterministic and rigorously enforced.

1. **Consult the Docs:** Always read the [Architecture Specification](docs/mnemo_architecture_v2.md) and relevant [ADRs](docs/adr/) before proposing a change.
2. **Core Isolation:** `mnemo-core` must never make an HTTP request (unless it's an isolated plugin), depend on web frameworks like FastAPI, or execute arbitrary code. It is a pure Python library.
3. **Interface-Driven:** Components must depend on `Protocol` interfaces (e.g., `ParserInterface`, `StorageInterface`), not concrete implementations.
4. **No Silent Failures:** If an invariant is broken, raise a typed exception. Do not silently swallow errors.

## 8. The ADR Process

Significant architectural decisions are recorded as Architecture Decision Records (ADRs) in `docs/adr/`.

You must open an **Architecture Proposal (ADR)** if your PR involves:
- Changing a public interface contract or domain schema.
- Crossing or modifying a layer boundary.
- Introducing a new database or core dependency.
- Altering the application lifecycle.

## 9. Adding New Modules or Modifying Interfaces

- **New Modules:** Must follow the existing directory structure and implement their functionality behind a clean `Protocol`.
- **Modifying Interfaces:** Since interfaces define the boundaries between core and plugins, any change to a file in `mnemo-core/mnemo/interfaces/` requires an ADR and careful review.

## 10. Commit and Pull Request Expectations

- **Commit Messages:** Use conventional commit subjects (e.g., `feat: add markdown parser`, `fix: handle missing PDF metadata`, `docs: update roadmap`).
- **PR Descriptions:** Your pull request must explain:
  - The roadmap scope of the change.
  - How it was tested.
  - The impact on any public APIs.
  - Any ADR implications (if applicable).
- **Scope:** Keep PRs focused. Do not mix refactoring with new feature implementation.

## 11. How to Report Bugs

When opening a bug report, please include:
- A clear, concise description of the bug.
- Steps to reproduce the behavior.
- Expected vs. actual behavior.
- Relevant logs, error traces, and your environment setup (OS, Python version, `uv` version).

## 12. Proposing Architectural Changes

If you believe a fundamental architectural assumption should be changed:
1. Open an Issue outlining the problem and proposed solution.
2. Tag it as an architectural discussion.
3. If the maintainers agree in principle, you will be invited to write an ADR and submit it as a PR to the `docs/adr/` directory before writing code.

By participating in this project, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md). We look forward to building a powerful, local-first knowledge engine with you!
