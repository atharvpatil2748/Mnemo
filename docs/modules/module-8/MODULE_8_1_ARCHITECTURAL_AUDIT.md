# Module 8.1 — Architectural Audit: MCP Server Core

- **Module:** Phase 8, Module 8.1 (MCP Server Core)
- **Status:** APPROVED / GREEN
- **Date:** 2026-08-16

---

## 1. Scope Analysis & Authoritative Basis

### Authoritative Requirements:
1. **Engineering Roadmap §Phase 8, Module 8.1:**
   - Implement MCP server using official Python `mcp` SDK (`mcp>=1.9.4,<2`).
   - Implement stdio transport for local subprocess communication.
   - Implement SSE (Server-Sent Events) transport for HTTP-based MCP clients.
   - Create `mnemo-mcp` CLI entrypoint supporting `--host`, `--port`, `--transport`, `--version`, and `--help`.
2. **Architecture Specification v2.0 §5.2 (MCP Server):**
   - Layer 2 thin adapter architecture with zero domain logic inside `mnemo-server`.
   - MCP protocol routes through `KnowledgeEngine` without bypassing Layer 1 boundaries.
   - Restrict MCP capabilities strictly to knowledge retrieval (no agentic action tools, no code execution, no web browsing, no file mutation).
3. **M8 Validation Target:**
   - External validation consumer: **Antigravity** (replacing Claude Desktop for this milestone, with historical traceability preserved).

---

## 2. Frozen Core Boundary Audit

| Capability | Module / Layer | Core Status |
|---|---|---|
| Domain Logic | `mnemo-core/` | **Frozen / Untouched (0 changes)** |
| Plugins | `plugins/` | **Frozen / Untouched (0 changes)** |
| Historical ADRs | `docs/adr/ADR-0001` through `ADR-0051` | **Frozen / Untouched (0 changes)** |
| MCP Adapter | `mnemo-server/mnemo_server/mcp/` | **Server Layer Implementation (Layer 2)** |
| CLI Entrypoint | `mnemo-server/mnemo_server/mcp/cli.py` | **Server Layer Implementation (Layer 2)** |

**FROZEN_CORE_MODIFICATIONS_REQUIRED:** `NO` (0 modifications to `mnemo-core/` or `plugins/`).

---

## 3. Server Layer Architecture & Transport Design

### MCP Architecture:
```
External MCP Client (Antigravity)
               │ (JSON-RPC 2.0 / MCP Protocol)
               ▼
┌─────────────────────────────────────────────────────────────┐
│ mnemo-server (Layer 2)                                      │
│                                                             │
│  ├── stdio transport (stdin/stdout framing, stderr logging) │
│  ├── SSE transport (GET /sse + POST /messages)             │
│  └── MCP Server Core (Capabilities & Lifespan Management)   │
└──────────────────────────────┬──────────────────────────────┘
                               │ (Internal Python API)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ mnemo-core (Layer 1)                                        │
│  └── KnowledgeEngine                                        │
└─────────────────────────────────────────────────────────────┘
```

### Stdio Transport Specifications:
- Subprocess communication over standard input / output.
- All application, engine, and server logging redirected to `sys.stderr` to prevent JSON-RPC framing corruption.
- Deterministic signal and stream teardown.

### SSE Transport Specifications:
- Built with Starlette / FastAPI and `SseServerTransport`.
- Exposes `GET /sse` (connection endpoint yielding session ID and event stream) and `POST /messages` (client message receiver).
- Integrates with `ServerConfig` and `AuthMiddleware` for authenticated deployments.

---

## 4. Verification & Quality Gate Plan

- **Automated Tests:** Comprehensive unit and protocol handshake tests for server initialization, stdio stream execution, SSE HTTP endpoints, and `mnemo-mcp` CLI.
- **Antigravity Live Validation:** Real MCP client handshake and capability discovery with Mnemo as the sole configured MCP server.
- **Code Quality:** Ruff format/lint clean, Mypy `--strict` clean across all files, full package build validation.
