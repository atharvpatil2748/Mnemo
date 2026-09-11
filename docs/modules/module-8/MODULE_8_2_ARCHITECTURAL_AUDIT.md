# Module 8.2 — Architectural Audit: MCP Tool Implementations

- **Module:** Phase 8, Module 8.2 (MCP Tool Implementations)
- **Status:** APPROVED / GREEN
- **Date:** 2026-08-16

---

## 1. Scope Analysis & Authoritative Basis

### Authoritative Requirements:
1. **Architecture Specification v2.0 §5.2 (MCP Server):**
   - Exposes knowledge-retrieval tools only:
     - `query_notebook`: Grounded evidence retrieval and synthesis with citations.
     - `search_all_notebooks`: Full-text and semantic multi-mode search.
     - `list_notebooks`: Read-only notebook inventory with source counts.
     - `get_notebook_summary`: Pre-generated and freshly-generated notebook summaries.
     - `get_source_insights`: Extracted key facts and entities from a source.
     - `get_timeline`: Chronological events across sources, notes, and sessions.
   - Strictly forbids: ingestion triggers, notebook mutation, code execution, web browsing, email sending, shell commands, or arbitrary file access.
2. **Engineering Roadmap §Phase 8, Module 8.2:**
   - Implements the 6 knowledge tools on top of the Module 8.1 MCP server core.
   - Integrates with `KnowledgeEngine` and existing Layer 2 service orchestration without domain logic duplication.
3. **ADR Status:**
   - ADR-0049 (§Phase 7 Server Architecture), ADR-0050 (§Notebooks), ADR-0051 (§Sources/Ingestion), ADR-0044/ADR-0045 (§Citations/QA) fully govern the underlying services and schemas.
   - **NEW_ADR_REQUIRED:** `NO` (Architecture §5.2 and existing ADRs define the complete contractual surface).

---

## 2. Frozen Core Boundary Audit

| Capability | Module / Layer | Core Status |
|---|---|---|
| Domain Logic & Storage | `mnemo-core/` | **Frozen / Untouched (0 changes)** |
| Plugins | `plugins/` | **Frozen / Untouched (0 changes)** |
| Historical ADRs | `docs/adr/ADR-0001` through `ADR-0051` | **Frozen / Untouched (0 changes)** |
| MCP Tool Schemas & Handlers | `mnemo-server/mnemo_server/mcp/` | **Server Layer Implementation (Layer 2)** |
| Service Orchestration | `mnemo-server/mnemo_server/services/` | **Server Layer Implementation (Layer 2)** |

**FROZEN_CORE_MODIFICATIONS_REQUIRED:** `NO` (0 modifications to `mnemo-core/` or `plugins/`).

---

## 3. Tool Contract Specifications & Architecture Mapping

```
Antigravity / MCP Client
             │ (JSON-RPC 2.0 / tools/call)
             ▼
┌─────────────────────────────────────────────────────────────┐
│ mnemo-server (Layer 2)                                      │
│                                                             │
│  ├── MCP Server Core (mnemo_server.mcp.server)              │
│  └── Tool Dispatcher & Schemas (mnemo_server.mcp.tools)     │
│       ├── query_notebook        ──► QueryService            │
│       ├── search_all_notebooks  ──► SearchService           │
│       ├── list_notebooks        ──► Storage.list_notebooks  │
│       ├── get_notebook_summary  ──► Storage.list_insights   │
│       ├── get_source_insights   ──► InsightService / Storage│
│       └── get_timeline          ──► Storage (timeline)      │
└──────────────────────────────┬──────────────────────────────┘
                               │ (Internal Python API)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ mnemo-core (Layer 1)                                        │
│  └── KnowledgeEngine                                        │
└─────────────────────────────────────────────────────────────┘
```

### Tool Inventory & Signatures:

1. **`query_notebook`**:
   - Inputs: `notebook_id: str (UUID)`, `question: str`, `top_k: int = 10`, `synthesize: bool = True`
   - Output: `answer: str | None`, `citations: list[Citation]`, `retrieval_metadata: dict`
   - Security: Scoped to requested notebook; verifies existence.

2. **`search_all_notebooks`**:
   - Inputs: `query: str`, `top_k: int = 10`, `notebook_id: str | None = None`
   - Output: `results: list[SearchResult]`, `total: int`, `latency_ms: int`
   - Security: Multi-mode dense/sparse search without LLM synthesis or side-effects.

3. **`list_notebooks`**:
   - Inputs: `limit: int = 50`, `cursor: str | None = None`
   - Output: `notebooks: list[NotebookSummary]`, `next_cursor: str | None`, `total: int`
   - Security: Read-only listing with source counts.

4. **`get_notebook_summary`**:
   - Inputs: `notebook_id: str (UUID)`
   - Output: `notebook_id: str`, `summary: str | None`, `summaries: list`, `sources: list`, `status: str`
   - Security: Read-only summary retrieval.

5. **`get_source_insights`**:
   - Inputs: `source_id: str (UUID)`, `insight_type: str | None = None`, `limit: int = 50`
   - Output: `source_id: str`, `notebook_id: str`, `insights: list[Insight]`, `total: int`
   - Security: Validates source identity and returns structured insights.

6. **`get_timeline`**:
   - Inputs: `notebook_id: str (UUID)`, `limit: int = 50`
   - Output: `notebook_id: str`, `events: list[TimelineEvent]`, `total: int`
   - Security: Validates notebook identity; returns chronological events.

---

## 4. Verification & Quality Gates

- **Unit & Integration Testing:** Full test suite for every tool, covering parameter validation, missing resources, malformed inputs, happy paths, evidence formatting, and error mapping.
- **Antigravity Live Validation:** Real MCP client tool discovery and execution via stdio transport against Mnemo as sole MCP server.
- **Quality Standards:** Ruff clean, Mypy `--strict` clean, $\ge 90.00\%$ coverage, `uv build --all` clean.
