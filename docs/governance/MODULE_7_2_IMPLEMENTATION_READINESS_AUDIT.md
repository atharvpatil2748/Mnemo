# Module 7.2 — Final Implementation Readiness Audit & Contract-to-Code Planning

- **Milestone:** Phase 7 Module 7.2 (Notebook CRUD & Graph Endpoints)
- **Audit Date:** 2026-08-16
- **Baseline Release:** v0.21.2 (M6 frozen, Module 7.1 closed at `3ec5c33`)
- **Authoritative Contract:** [ADR-0050: Notebook and Knowledge Graph REST API Specification](../adr/ADR-0050-notebook-and-knowledge-graph-rest-api.md)
- **Status:** READY FOR IMPLEMENTATION

---

## 1. Executive Verdict

```
MODULE_7_2_STATUS:                    GREEN WITH CONDITIONS
ADR_0050_STATUS:                      ACCEPTED
IMPLEMENTATION_READY:                 YES WITH CONDITIONS
FROZEN_CORE_MODIFICATIONS_REQUIRED:   NO
BLOCKING_ISSUES:                      0
HIGH_RISKS:                           0
MEDIUM_RISKS:                         1 (Timeline multi-stream keyset merge at scale)
LOW_RISKS:                            2 (String cursor transparency; exact-match find_entities in SurrealDB)
```

---

## 2. Endpoint Readiness Matrix

| Endpoint | HTTP Method | Core Method Called | DTO Compatibility | Algorithm Correctness | Frozen Changes Required | Status |
|---|---|---|---|---|---|---|
| `/v1/notebooks` | `POST` | `storage.upsert_notebook` | 100% Compatible | Deterministic | None (0) | **READY** |
| `/v1/notebooks` | `GET` | `storage.list_notebooks` | 100% Compatible | Keyset pagination | None (0) | **READY** |
| `/v1/notebooks/{id}` | `GET` | `storage.get_notebook` | 100% Compatible | ID lookup | None (0) | **READY** |
| `/v1/notebooks/{id}` | `PATCH` | `storage.get_notebook` + `upsert_notebook` | 100% Compatible | Last-Write-Wins | None (0) | **READY** |
| `/v1/notebooks/{id}` | `DELETE` | `storage.delete_notebook` | 100% Compatible | Cascade delete | None (0) | **READY** |
| `/v1/notebooks/{id}` | `GET` (summary) | `storage.get_notebook` + `list_insights` | 100% Compatible | Read-only filtering | None (0) | **READY** |
| `/v1/notebooks/{id}` | `GET` (timeline) | `storage.list_sources/notes/sessions` | 100% Compatible | In-memory merge | None (0) | **READY (Cond. 1)** |
| `/v1/notebooks/{id}` | `GET` (graph) | `storage.capabilities` + `find_entities` | 100% Compatible | Nodes-only guard | None (0) | **READY (Cond. 2)** |

---

## 3. Critical Forensic Findings

### 3.1 Notebook CRUD & Domain Invariants
- **Constructor:** `Notebook(notebook_id=uuid4(), title=..., description=..., created_at=now, updated_at=now, metadata=FrozenMetadata(...))`
- **Invariants:**
  - `title`: Must be non-empty, non-whitespace string (`require_non_empty`).
  - `description`: Optional non-empty, non-whitespace string (`require_optional_non_empty`).
  - `created_at` / `updated_at`: Strict UTC datetime objects (`require_utc`), `created_at <= updated_at`.
  - `metadata`: `FrozenMetadata` instance.
- **DTO Mapping:** `CreateNotebookRequest` and `UpdateNotebookRequest` strip whitespace via Pydantic validators and reject invalid titles with `422 Unprocessable Entity` before constructing domain objects.

### 3.2 Last-Write-Wins (LWW) Concurrency Verification
- `SQLiteStore.upsert_notebook` executes:
  `INSERT INTO notebooks (...) VALUES (...) ON CONFLICT(notebook_id) DO UPDATE SET title=excluded.title, description=excluded.description, updated_at=excluded.updated_at, metadata=excluded.metadata`
- **Result:** Pure Last-Write-Wins. No `WHERE version = ...` predicate exists.
- **Database Serialization:** In SQLite WAL mode, write transactions are serialized at the database lock layer (and thread-serialized by `aiosqlite`). Concurrent requests to `PATCH /v1/notebooks/{id}` succeed atomically without corrupting SQLite state; the last write committed overwrites previous updates. ADR-0050's declaration of LWW semantics is 100% accurate.

### 3.3 Pagination Forensics
- All 5 list methods (`list_notebooks`, `list_sources`, `list_notes`, `list_sessions`, `list_insights`) use identical keyset seek logic:
  `WHERE id > ? ORDER BY id ASC LIMIT ? + 1`
- `PageResponse[T]` cleanly wraps `Page[T]` (`items`, `next_cursor`, `limit`).
- Cursors are transparent UUID strings. Malformed non-UUID cursors will be rejected with `422 Unprocessable Entity` by Pydantic / FastAPI validators.

### 3.4 Timeline Multi-Stream Merging (Deep Audit)
- **Observation:** In SQLite, `list_sources`, `list_notes`, and `list_sessions` order records by `id ASC` (keyset order on random UUIDv4), NOT by `created_at DESC`.
- **Merge Strategy:** When `GET /v1/notebooks/{id}/timeline` is called with query `limit=N` (default 50, max 100):
  1. The server fetches up to `1000` records across each of the three collections (or iterates until exhausted / capped).
  2. Synthesizes `TimelineEventResponse` objects.
  3. Sorts the combined pool by `timestamp` descending (most recent first).
  4. Slices to the requested `limit`.
- **Scale Condition (Condition 1):** For notebooks within typical desktop/single-user scale (<= 1,000 sources/notes/sessions), this algorithm is deterministic and exact. For massive historical databases (> 100,000 items), true server-side date indexing will be introduced by Module 12.4 (`timeline-gen` SurrealDB plugin). This is documented as a known scale boundary.

### 3.5 Summary Read-Only Insight Filtering
- `Insight` domain model contains: `insight_id: UUID`, `notebook_id: UUID`, `source_id: UUID`, `type: InsightType`, `content: str`, `confidence: float | None`, `created_at: datetime`, `metadata: FrozenMetadata`.
- `InsightType.SUMMARY` equals `"summary"`.
- `GET /v1/notebooks/{id}/summary` calls `list_insights(notebook_id)` and filters by `type == InsightType.SUMMARY`.
- Returns `{ "notebook_id": "...", "summaries": [...], "status": "ready" | "empty" }`. Zero LLM calls or background queues are touched.

### 3.6 Knowledge Graph Nodes-Only & Disabled Mode (Deep Audit)
- **SurrealDB Disabled:** `engine.storage.capabilities().supports_graph` returns `False`. The route handler returns `{ "notebook_id": "...", "nodes": [], "edges": [], "status": "disabled" }` immediately, preventing `NotImplementedError`.
- **SurrealDB Enabled:** `find_entities(canonical_name="", entity_type=None, document_ids=doc_ids, limit=limit)` searches for entities matching `canonical_name`. If no entities exist or are found, returns `{ "nodes": [], "edges": [], "status": "empty" }`.
- **Edges:** `edges: []` is always returned as specified in ADR-0050 Decision 6.

---

## 4. DTO Serialization Forensics

| DTO Field | Domain Field | Type Match | Serialization Behavior |
|---|---|---|---|
| `NotebookResponse.notebook_id` | `Notebook.notebook_id: UUID` | Exact | String UUID (36 chars) |
| `NotebookResponse.created_at` | `Notebook.created_at: datetime` | Exact | ISO-8601 UTC string |
| `NotebookResponse.updated_at` | `Notebook.updated_at: datetime` | Exact | ISO-8601 UTC string |
| `NotebookResponse.metadata` | `Notebook.metadata: FrozenMetadata` | Unpacked | Standard JSON dict |
| `SummaryItemResponse.insight_id` | `Insight.insight_id: UUID` | Exact | String UUID |
| `TimelineEventResponse.event_id` | `Source/Note/Session.id: UUID` | Exact | String UUID |
| `GraphNodeResponse.aliases` | `Entity.aliases: tuple[str, ...]` | Converted | `list[str]` |

---

## 5. Router & Application Integration Plan

```
mnemo-server/mnemo_server/
├── app.py                     ← Include notebooks router: app.include_router(notebooks.router, prefix="/v1")
├── routers/
│   ├── __init__.py
│   └── notebooks.py           ← FastAPI APIRouter(prefix="/notebooks", tags=["notebooks"])
└── schemas/
    ├── __init__.py
    ├── common.py              ← PageResponse[T]
    ├── notebooks.py           ← Create/Update/NotebookResponse
    ├── summary.py             ← NotebookSummaryResponse
    ├── timeline.py            ← TimelineResponse
    └── graph.py               ← EntityGraphResponse
```

- **Dependencies:** All endpoints consume `engine: KnowledgeEngine = Depends(get_engine)`.
- **Error Propagation:** `NotFoundError`, `ContractValidationError`, and `StorageError` bubble up directly to ADR-0049 handlers.

---

## 6. Adversarial Test Plan

The implementation test suite (`mnemo-server/tests/test_server_notebooks.py`) must cover:

1. **Notebook Lifecycle:**
   - POST valid notebook → 201 Created with generated UUID and UTC timestamps.
   - GET notebook by ID → 200 OK.
   - GET non-existent notebook UUID → 404 Not Found (`contract.not_found`).
   - GET malformed UUID string → 422 Unprocessable Entity (`http.validation`).
   - PATCH update title only → 200 OK with new updated_at.
   - PATCH empty body `{}` → 422 Unprocessable Entity.
   - PATCH with whitespace title `"   "` → 422 Unprocessable Entity.
   - DELETE notebook → 204 No Content.
   - DELETE non-existent notebook → 404 Not Found.
   - GET after DELETE → 404 Not Found.
2. **Pagination:**
   - List empty notebooks repository → 200 OK (`items: []`, `next_cursor: null`).
   - List with pagination across multiple pages with valid `cursor`.
   - List with `limit=0` or `limit=101` → 422 Unprocessable Entity.
   - List with malformed `cursor="not-a-uuid"` → 422 Unprocessable Entity.
3. **Summary Endpoint:**
   - GET summary on notebook with no summary insights → 200 OK (`summaries: []`, `status: "empty"`).
   - GET summary on non-existent notebook → 404 Not Found.
4. **Timeline Endpoint:**
   - GET timeline on empty notebook → 200 OK (`events: []`, `total: 0`).
   - GET timeline on notebook with sources, notes, and sessions → 200 OK with correct chronological sort and event types (`source_added`, `note_created`, `session_started`).
5. **Graph Endpoint:**
   - GET graph when SurrealDB is disabled (`supports_graph=False`) → 200 OK (`nodes: []`, `edges: []`, `status: "disabled"`).
   - GET graph on non-existent notebook → 404 Not Found.
6. **Concurrency / Last-Write-Wins:**
   - Sequential PATCH updates simulate LWW without data corruption.

---

## 7. Frozen Boundary Audit

| Path | Frozen Status | Modifications Required |
|---|---|---|
| `mnemo-core/mnemo/engine.py` | FROZEN | 0 changes |
| `mnemo-core/mnemo/interfaces/*` | FROZEN | 0 changes |
| `mnemo-core/mnemo/models/*` | FROZEN | 0 changes |
| `mnemo-core/mnemo/storage/*` | FROZEN | 0 changes |
| `plugins/*` | FROZEN | 0 changes |
| `docs/adr/ADR-0001` through `ADR-0050` | FROZEN | 0 changes |

---

## 8. Final Readiness Declaration

```
READY_TO_IMPLEMENT: YES
```
