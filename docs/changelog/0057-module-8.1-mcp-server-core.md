# 0057 — Phase 8, Module 8.1: MCP Server Core

- **Date:** 2026-08-16
- **Status:** COMPLETED
- **Module:** Phase 8, Module 8.1 (MCP Server Core)

---

## 1. Overview & Objectives

Module 8.1 initiates **Phase 8 (MCP Server)** by implementing the foundational Model Context Protocol (MCP) server core inside `mnemo-server` (Layer 2) using the official Python `mcp` SDK (`mcp>=1.9.4,<2`).

It provides stdio and SSE transport adapters, the `mnemo-mcp` CLI executable, clean capability negotiation, strict stdout framing purity (with all diagnostic logging routed exclusively to `sys.stderr`), and validation with **Antigravity** as the designated external MCP client consumer.

---

## 2. Key Deliverables

### MCP Server Core (`mnemo_server.mcp.server`):
- **Server Identity & Capabilities:** Canonical `Server(name="mnemo-mcp", version=__version__)` instance advertising tools capability (`ToolsCapability(listChanged=False)`), prompts capability, and resources capability.
- **Handler Initialization:** Minimal baseline handlers (`list_tools`, `call_tool`, `list_prompts`, `list_resources`) returning empty inventories in Module 8.1, ready for Module 8.2 knowledge retrieval tools.
- **Engine Lifecycle Management:** Clean asynchronous lifespan hooks initializing and shutting down `KnowledgeEngine` without polluting Layer 1 domain logic.

### Stdio Transport (`mnemo_server.mcp.server.run_stdio_server`):
- Non-blocking asynchronous standard I/O communication using `mcp.server.stdio.stdio_server`.
- Guaranteed JSON-RPC framing purity on standard output:
  - Custom stream handler redirecting all Python and Mnemo logging to `sys.stderr`.
  - PyMuPDF alias initialization in `mnemo_server/__init__.py` and `mcp/cli.py` preventing C-extension deprecation warnings from corrupting standard output.

### SSE Transport (`mnemo_server.mcp.server.create_sse_app` / `run_sse_server`):
- Starlette ASGI application hosting `SseServerTransport` mounted on `/sse` (GET stream) and `/messages` (POST endpoint).
- Health check route at `GET /health` reporting service status, version, and engine state.
- Seamless integration with `AuthMiddleware` supporting `none`, `api-key`, and `jwt` authentication modes.

### Console CLI (`mnemo-mcp` / `mnemo_server.mcp.cli`):
- Console script registered in `pyproject.toml` as `mnemo-mcp`.
- Subcommands & flags: `stdio` (default), `sse`, `--host`, `--port`, `--transport`, `--log-level`, `--auth-mode`, `--api-key`, `--jwt-secret`, `-v` / `--version`, `-h` / `--help`.

---

## 3. Live Antigravity Validation

- **Target Consumer:** Antigravity (configured in `~/.gemini/config/mcp_config.json` with ONLY Mnemo MCP server).
- **Subprocess Handshake Verification:**
  - Standard input/output JSON-RPC protocol initialization: `ServerInfo(name='mnemo-mcp', version='0.22.0')`.
  - Protocol version negotiated: `2025-11-25`.
  - Capabilities enumerated: `tools`, `prompts`, `resources`.
  - Tool listing query (`tools/list`): returned `[]` with 0 framing errors.

---

## 4. Verification & Quality Gates

- **Test Suite:** 1,324 passed, 1 skipped, 0 failures.
- **Workspace Coverage:** 90.23% ($\ge 90.00\%$ requirement).
- **Linter & Formatter:** Ruff 100% clean across 242 files.
- **Type Checker:** Mypy `--strict` clean across 138 source files.
- **Package Build:** `uv build --all` succeeds across all workspace packages.
- **Frozen Core Boundary:** 0 modifications to `mnemo-core/`, `plugins/`, or `docs/adr/ADR-0001*`.
