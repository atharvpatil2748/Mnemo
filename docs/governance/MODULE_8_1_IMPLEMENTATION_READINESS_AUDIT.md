# Module 8.1 — Implementation Readiness Audit: MCP Server Core

- **Module:** Phase 8, Module 8.1 (MCP Server Core)
- **Status:** APPROVED / READY FOR IMPLEMENTATION
- **Date:** 2026-08-16

---

## 1. Readiness Assessment Matrix

| Checklist Item | Requirement | Assessment | Verdict |
|---|---|---|---|
| **Roadmap Alignment** | Implements Roadmap §Phase 8, Module 8.1 tasks | Scope limited to MCP server core, stdio, SSE, and `mnemo-mcp` CLI | **READY** |
| **Architectural Boundaries** | Strictly Layer 2 adapter inside `mnemo-server` | Zero domain logic; calls `KnowledgeEngine` | **READY** |
| **Dependency Compatibility** | `mcp>=1.9.4,<2` and `sse-starlette>=2.1.0` in `mnemo-server` | Verified compatible with Python 3.12, AnyIO, Pydantic V2, Starlette | **READY** |
| **Transport Design** | Stdio with stderr logging, SSE with Starlette | Non-blocking async streams, clean shutdown | **READY** |
| **CLI Specification** | `mnemo-mcp` console script with stdio/sse modes | Subcommands and arguments validated | **READY** |
| **M8 Validation Target** | Antigravity configured as sole MCP server | Clear testing procedure defined | **READY** |
| **Frozen Core** | Zero changes to `mnemo-core/` and `plugins/` | 100% frozen layer compliance | **READY** |

---

## 2. Implementation Execution Plan

1. **Dependency Registration:** Register `mcp>=1.9.4,<2` in `mnemo-server/pyproject.toml` and synchronize lockfile.
2. **Core Server & Transports:** Implement `mnemo_server/mcp/server.py` (`create_mcp_server`, `run_stdio_server`, `create_sse_app`, `run_sse_server`).
3. **CLI Entrypoint:** Implement `mnemo_server/mcp/cli.py` and register console script `mnemo-mcp`.
4. **Test Implementation:** Author `test_mcp_server.py`, `test_mcp_sse.py`, `test_mcp_cli.py`.
5. **Quality Gates:** Verify `pytest` (>=90% coverage), `ruff format/check`, `mypy --strict`, `uv build --all`.
6. **Live Antigravity Validation:** Validate MCP server connection via Antigravity.
7. **Documentation & Governance:** Author closure report and update roadmap.
