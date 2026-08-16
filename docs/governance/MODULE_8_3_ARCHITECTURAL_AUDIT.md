# Module 8.3 — Architectural Audit: MCP Testing & Client Integration

- **MODULE:** Phase 8, Module 8.3 (MCP Testing & Client Integration)
- **STATUS:** AUDIT COMPLETE / READY FOR INTEGRATION VALIDATION
- **GOVERNING DOCUMENTS:**
  - `docs/mnemo_architecture_v2.md` §5.2 (MCP Server Integration)
  - `docs/mnemo_engineering_roadmap.md` §Phase 8, Module 8.3 & Milestone M8
  - `docs/adr/ADR-0049-phase-7-server-application-architecture.md`
  - `docs/governance/MODULE_8_1_CLOSURE_REPORT.md`
  - `docs/governance/MODULE_8_2_CLOSURE_REPORT.md`

---

## 1. Architectural Scope & Invariants

### 1.1 Context & Authority
Module 8.3 is the final testing and certification module of Phase 8.
- **Module 8.1** established the MCP server runtime (`Server`, `stdio_server`, `SseServerTransport`, `mnemo-mcp` CLI).
- **Module 8.2** implemented the six authoritative knowledge retrieval tools:
  1. `query_notebook`
  2. `search_all_notebooks`
  3. `list_notebooks`
  4. `get_notebook_summary`
  5. `get_source_insights`
  6. `get_timeline`

### 1.2 Module 8.3 Core Objectives
Module 8.3 must formally prove and certify the complete end-to-end integration stack:
```
Golden Corpus Data (Bhagavad Gita PDF + SQLite + Blobs)
      ↓
Mnemo Storage / Composite Backend
      ↓
KnowledgeEngine & Layer 2 Services (QueryService, SearchService)
      ↓
Mnemo MCP Server Core (`mnemo-server/mnemo_server/mcp`)
      ↓
MCP Stdio Transport (`uv run mnemo-mcp stdio`)
      ↓
Antigravity MCP Client (`mcp_config.json`)
      ↓
Tool Discovery (`tools/list`)
      ↓
Real Tool Invocations (`tools/call`)
      ↓
Grounded Evidence / Accurate Answers / Deterministic Error Handling
```

---

## 2. Frozen Boundaries & Anti-Regression Rules

1. **Frozen Core Boundary (Layer 1):**
   - Zero modifications to `mnemo-core/`.
   - Zero modifications to `plugins/`.
   - Zero modifications to historical ADRs (`ADR-0001` through `ADR-0051`).
2. **Read-Only MCP Capability Surface:**
   - The MCP server exposes **only** the 6 knowledge retrieval tools.
   - Absolutely **no** mutation tools (no document ingestion triggers, no notebook creation/deletion, no note modification).
   - Absolutely **no** arbitrary code execution, shell execution, web browsing, or filesystem manipulation tools.
3. **No Synthetic / Duplicate Data Substitution:**
   - Testing must evaluate against the **real Golden Corpus** stored in `data/manual-gita-qa/` (`goldenDataset/Bhagavad-gita-As-It-Is.pdf`, SHA-256: `ff112b0b056d303b792f6f2e68cbd73a89adf612fa9113f932446cdea7741583`).
   - No mock data or fake citations may be substituted for real Golden Corpus verification.

---

## 3. Tool Matrix & Validation Criteria

| Tool Name | Subsystem Target | Expected Payload / Response Structure |
|---|---|---|
| `list_notebooks` | `StorageInterfaceV1.list_notebooks` | Returns notebook array with `notebook_id`, `title`, `source_count`, `metadata`, `next_cursor`. |
| `get_notebook_summary` | `StorageInterfaceV1.list_insights` + `list_sources` | Returns `summary`, `summaries` list, `sources` inventory with titles, and status string (`ready` / `empty`). |
| `get_source_insights` | `StorageInterfaceV1.list_insights` (scoped to source) | Returns `insights` list matching `source_id` with optional `insight_type` filtering (`key_fact`, `claim`, `entity`, `summary`). |
| `get_timeline` | `StorageInterfaceV1.list_sources`, `list_notes`, `list_sessions` | Returns chronological events sorted descending by timestamp across source additions, notes, and sessions. |
| `search_all_notebooks` | `SearchService` (MultiSourceRetriever) | Returns ranked search results with chunk text, scores, heading paths, page numbers, and total hit count. |
| `query_notebook` | `QueryService` (Retrieval + Synthesis) | Returns grounded `answer`, structured `citations` (with document titles, page numbers, heading paths, exact quotes), and `retrieval_metadata`. |

---

## 4. ADR Assessment

- **NEW_ADR_REQUIRED:** NO.
- **Rationale:** Module 8.3 implements the testing, certification, and integration verification already specified in Architecture Specification v2.0 §5.2 and Engineering Roadmap §Phase 8, Module 8.3 without introducing new architectural abstractions or modifying existing interface contracts.
