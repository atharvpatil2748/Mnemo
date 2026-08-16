# Module 7.2 — Architectural Compatibility, Implementability & Adversarial Audit

- **Target Module:** Phase 7 Module 7.2 (Notebook CRUD & Graph Endpoints)
- **Audit Date:** 2026-08-16
- **Baseline Release:** v0.21.2 (M6 frozen, Module 7.1 closed & committed at `3ec5c33`)
- **Authoritative References:** `docs/mnemo_engineering_roadmap.md`, `docs/mnemo_architecture_v2.md`, ADR-0001 through ADR-0049

---

## 1. Executive Verdict

```
MODULE_7_2_STATUS:                    GREEN WITH CONDITIONS
FROZEN_PHASE_MODIFICATIONS_REQUIRED:  NO
NEW_ADR_REQUIRED:                     YES (ADR-0050 proposed for REST DTO schemas & pagination contract)
IMPLEMENTATION_READY:                 YES (pending ADR-0050 acceptance)
BLOCKING_ISSUES:                      0
HIGH_RISKS:                           0
MEDIUM_RISKS:                         2 (SurrealDB optional graph capability handling, Keyset pagination cursor encoding)
```

**Key Conclusion:**
Module 7.2 is **100% architecturally compatible** with the frozen `mnemo-core` baseline (Phases 0–6) and Module 7.1 (`mnemo-server`). All required notebook CRUD operations (`upsert_notebook`, `get_notebook`, `delete_notebook`, `list_notebooks`), source associations (`list_sources`), note queries (`list_notes`), session queries (`list_sessions`), insight queries (`list_insights`), and graph operations (`get_entity`, `find_entities`, `get_related_entities`) are already fully implemented, tested, and exposed on `KnowledgeEngine.storage` (`StorageInterfaceV1`). Zero modifications to `mnemo-core` or historical ADRs (ADR-0001 through ADR-0048) are required.

---

## 2. Module 7.2 Scope & Purpose

Module 7.2 implements the notebook-level REST API endpoints on `mnemo-server` (Layer 2), providing the transport interface for the user interface (`mnemo-ui`) and programmatic clients to manage notebooks, inspect timeline events, retrieve extracted summaries, and visualize entity knowledge graphs.

### Endpoints in Scope:
1. `GET /v1/notebooks` — List notebooks with cursor-based pagination
2. `POST /v1/notebooks` — Create a new notebook
3. `GET /v1/notebooks/{id}` — Retrieve notebook details by UUID
4. `PATCH /v1/notebooks/{id}` — Update notebook metadata (title, description, metadata)
5. `DELETE /v1/notebooks/{id}` — Delete notebook and cascade-clean associations
6. `GET /v1/notebooks/{id}/summary` — Retrieve extracted/generated notebook summary
7. `GET /v1/notebooks/{id}/timeline` — Retrieve unified timeline of notebook activity
8. `GET /v1/notebooks/{id}/graph` — Retrieve entity knowledge graph (nodes + edges)

---

## 3. Authoritative Roadmap Requirements

From `docs/mnemo_engineering_roadmap.md` §7 (Module 7.2):

| Task | Notes | Difficulty | Dependency | Status |
|---|---|---|---|---|
| `GET/POST /v1/notebooks` | List + create | Low | 7.1 | Planned |
| `GET/PATCH/DELETE /v1/notebooks/{id}` | CRUD | Low | 7.1 | Planned |
| `GET /v1/notebooks/{id}/summary` | Trigger summary generation if stale | Medium | 7.1 | Planned |
| `GET /v1/notebooks/{id}/timeline` | Return timeline events | Low | 7.1 | Planned |
| `GET /v1/notebooks/{id}/graph` | Return entity graph nodes + edges | Medium | 7.1 | Planned |

---

## 4. Architecture Specification Requirements

From `docs/mnemo_architecture_v2.md` §5.1 (REST API Surface):
- Versioned at `/v1`.
- All requests and responses use JSON.
- `Notebook` is the primary organizational aggregate in Mnemo.
- Documents are logical, content-addressed items; their presence in a notebook is mediated exclusively through `Source` associations.
- `DELETE /v1/notebooks/{id}` deletes the notebook record; SQLite `ON DELETE CASCADE` cleans up owned notes, sessions, turns, citations, and sources, while `CompositeStorage` updates vector index retrieval projections atomically.

---

## 5. Relevant ADR Dependency Matrix

| ADR | Decision | Frozen Implementation | Module 7.2 Compatibility |
|---|---|---|---|
| **ADR-0001** | Immutable domain models (`Notebook`, `Source`, `Note`, `Session`, `Turn`, `Citation`, `Entity`, `GraphEdge`) | `mnemo-core/mnemo/models/notebook.py`, `graph.py` | ✅ **Compatible.** Domain models are immutable dataclasses with strict validation. |
| **ADR-0002** | `StorageInterfaceV1` contract defining atomic storage façade methods | `mnemo-core/mnemo/interfaces/storage.py` | ✅ **Compatible.** All CRUD and query methods exist on `StorageInterfaceV1`. |
| **ADR-0003** | Configuration system with separate storage/plugin settings | `mnemo-core/mnemo/config.py` | ✅ **Compatible.** Storage capabilities dynamically report enabled backends. |
| **ADR-0004** | `KnowledgeEngine` composition root and lifecycle | `mnemo-core/mnemo/engine.py` | ✅ **Compatible.** `engine.storage` provides ready access to storage methods. |
| **ADR-0005** | Stable UUIDs for `Entity` and `GraphEdge` | `mnemo-core/mnemo/models/graph.py` | ✅ **Compatible.** Entities and edges have deterministic UUID identities. |
| **ADR-0049** | FastAPI server lifecycle, `ServerConfig`, typed `get_engine`, JSON error envelope | `mnemo-server/mnemo_server/app.py`, `errors.py`, `dependencies.py` | ✅ **Compatible.** Module 7.2 mounts routers directly on this foundation. |

---

## 6. Frozen Implementation Audit (What Can Be Called Today)

`KnowledgeEngine.storage` exposes the complete set of required methods:

```python
# Notebook CRUD
await engine.storage.list_notebooks(limit: int, cursor: str | None) -> Page[Notebook]
await engine.storage.upsert_notebook(notebook: Notebook) -> None
await engine.storage.get_notebook(notebook_id: UUID) -> Notebook | None
await engine.storage.delete_notebook(notebook_id: UUID) -> bool

# Notebook Associations & Children
await engine.storage.list_sources(notebook_id: UUID, limit: int, cursor: str | None) -> Page[Source]
await engine.storage.list_notes(notebook_id: UUID, limit: int, cursor: str | None) -> Page[Note]
await engine.storage.list_sessions(notebook_id: UUID, limit: int, cursor: str | None) -> Page[Session]
await engine.storage.list_insights(notebook_id: UUID, limit: int, cursor: str | None) -> Page[Insight]

# Graph Operations
await engine.storage.get_entity(entity_id: UUID) -> Entity | None
await engine.storage.find_entities(canonical_name: str, entity_type: str | None, document_ids: tuple[UUID, ...], limit: int) -> tuple[Entity, ...]
await engine.storage.get_related_entities(entity_id: UUID, hops: int, relations: tuple[str, ...], limit: int) -> tuple[Entity, ...]
engine.storage.capabilities().supports_graph -> bool
```

---

## 7. Endpoint & API Compatibility Matrix

| Endpoint | HTTP Method | Core Storage Method | Parameters / Body | Return Type | Status Code | Error Mapping |
|---|---|---|---|---|---|---|
| `/v1/notebooks` | `GET` | `list_notebooks(limit, cursor)` | `limit: int = 50`, `cursor: str \| None = None` | `PageResponse[NotebookResponse]` | `200 OK` | `422` (param validation), `503` (storage error) |
| `/v1/notebooks` | `POST` | `upsert_notebook(notebook)` | `CreateNotebookRequest(title, description, metadata)` | `NotebookResponse` | `201 Created` | `422` (validation), `503` (storage error) |
| `/v1/notebooks/{id}` | `GET` | `get_notebook(notebook_id)` | `id: UUID` | `NotebookResponse` | `200 OK` | `404` (not found), `422` (invalid UUID), `503` (engine not ready) |
| `/v1/notebooks/{id}` | `PATCH` | `get_notebook` + `upsert_notebook` | `id: UUID`, `UpdateNotebookRequest(title, description, metadata)` | `NotebookResponse` | `200 OK` | `404` (not found), `422` (validation), `503` (storage error) |
| `/v1/notebooks/{id}` | `DELETE` | `delete_notebook(notebook_id)` | `id: UUID` | `DeleteNotebookResponse` or `204` | `200 OK` / `204` | `404` (not found), `422` (invalid UUID), `503` (storage error) |
| `/v1/notebooks/{id}/summary` | `GET` | `get_notebook` + `list_insights` | `id: UUID` | `NotebookSummaryResponse` | `200 OK` | `404` (not found), `503` (storage error) |
| `/v1/notebooks/{id}/timeline` | `GET` | `get_notebook` + `list_sources` + `list_notes` + `list_sessions` | `id: UUID`, `limit: int = 50` | `TimelineResponse` | `200 OK` | `404` (not found), `503` (storage error) |
| `/v1/notebooks/{id}/graph` | `GET` | `get_notebook` + `list_sources` + `find_entities` | `id: UUID`, `limit: int = 100` | `EntityGraphResponse` | `200 OK` | `404` (not found), `503` (storage error) |

---

## 8. Notebook Identity & Versioning Forensics

- **Identifier Format:** All notebook IDs are RFC 4122 standard UUIDs (`uuid.UUID`).
- **ID Generation:**
  - On `POST /v1/notebooks`, `mnemo-server` generates a fresh `uuid4()` for `notebook_id`.
  - Clients cannot inject duplicate or arbitrary IDs; server owns creation identity.
- **Timestamps:**
  - `created_at`: Set to `datetime.now(UTC)` on creation.
  - `updated_at`: Set to `datetime.now(UTC)` on creation and updated on `PATCH`.
- **Validation:**
  - `title`: Must be non-empty string (`1 <= len <= 255`).
  - `description`: Optional non-empty string (`len <= 4096`).
  - `metadata`: Arbitrary JSON object, frozen to `FrozenMetadata` in core.
- **Optimistic Concurrency:**
  - Core model uses `updated_at` timestamps. SQLite serializes updates under WAL mode.
  - No explicit ETag/version header is required for Module 7.2 baseline, but `updated_at` is returned in all responses.

---

## 9. Graph Architecture Audit

- **Graph Backend:** Implemented via `SurrealDBStore` (when enabled in configuration).
- **Capability Check:** `engine.storage.capabilities().supports_graph` indicates whether graph storage is active.
- **Offline / Local-First Behavior:** When SurrealDB is disabled (e.g. SQLite-only local configuration), `GET /v1/notebooks/{id}/graph` must gracefully return `{ "nodes": [], "edges": [] }` with a status indicating graph indexing is inactive, rather than raising an unhandled exception.
- **Entity Scope:** Entities are extracted per `document_id`. Notebook graph queries resolve the notebook's documents via `list_sources(notebook_id)` and aggregate entities and edges across those documents.
- **Cascade Deletion:** When a notebook is deleted, `Source` associations are deleted in SQLite. Deleting a document directly invokes `delete_graph_for_document(document_id)`.

---

## 10. Error Contract Audit (ADR-0049 Alignment)

Module 7.2 relies entirely on the existing ADR-0049 error translation boundary:
- **Notebook Not Found:** Handler raises `NotFoundError(f"Notebook {id} was not found")` → Translated by `_interface_error_handler` to `404 Not Found` with `code: "contract.not_found"`.
- **Validation Errors:** Pydantic body validation or invalid UUID path params → Translated by `_validation_error_handler` to `422 Unprocessable Entity` with `code: "http.validation"`.
- **Storage / Lock Failure:** `StorageError` → Translated to `503 Service Unavailable` with `code: "contract.storage"`, `retryable: true`.
- **Engine Not Ready:** `get_engine` raises `DependencyUnavailableError` → Translated to `503 Service Unavailable` with `code: "contract.dependency_unavailable"`.

**Verdict:** Zero new error translation code needed. ADR-0049 completely covers Module 7.2.

---

## 11. Serialization & DTO Architecture Audit

### Decision: Dedicated Pydantic DTOs in `mnemo-server`
To maintain the strict separation between transport layer (Layer 2) and core domain layer (Layer 1):
- `mnemo-server` must define dedicated Pydantic request and response schemas in `mnemo_server/schemas/`.
- Domain dataclasses (`Notebook`, `Page[Notebook]`, `Source`, `Entity`, etc.) are converted to Pydantic DTOs at the endpoint boundary.
- All datetime fields serialize to ISO-8601 strings with UTC timezone (`2026-08-16T02:30:00Z`).
- All UUID fields serialize to standard 36-character hyphenated strings.
- Metadata dictionaries serialize cleanly to JSON objects.

---

## 12. Async & Blocking I/O Audit

- **Core Storage Methods:** All `StorageInterfaceV1` methods (`upsert_notebook`, `get_notebook`, `delete_notebook`, `list_notebooks`, `list_sources`, `list_notes`, `find_entities`) are native async coroutines (`async def`).
- **Database I/O:** Handled asynchronously via `aiosqlite` and `surrealdb.AsyncSurreal`.
- **No Blocking Calls:** Module 7.2 endpoint execution requires no `asyncio.to_thread` wrappers because no synchronous filesystem or network I/O is performed in notebook CRUD.

---

## 13. Concurrency & SQLite Transaction Audit

- **WAL Mode:** Enabled in `SQLiteStore.open()` (`PRAGMA journal_mode = WAL; PRAGMA busy_timeout = 30000;`).
- **Concurrent Readers:** Multiple FastAPI requests can read notebooks simultaneously without locking.
- **Serialized Writers:** Updates and deletes are protected by SQLite transactions and `busy_timeout`.
- **Multi-Worker Safety:** Compatible with single-worker default and multi-worker deployment per ADR-0049 §8.

---

## 14. Security & Input Validation Audit

- **Path Parameter Validation:** FastAPI + Pydantic automatically validates UUID formatting on `{id}` parameters.
- **Request Body Validation:** Strict length constraints on `title` (1–255 chars) and `description` (max 4096 chars).
- **Metadata Sanitization:** Metadata is restricted to JSON-serializable primitives (strings, numbers, booleans, lists, dicts) without executable code or unbounded payloads.
- **No Information Leakage:** Unexpected exceptions are sanitized by ADR-0049 handlers (stack traces and disk paths omitted).

---

## 15. Future Module Compatibility

- **Module 7.3 (Sources & Ingestion):** `Source` associations reference `notebook_id`. Module 7.2 manages notebook lifecycle; Module 7.3 manages document ingestion into notebooks. Perfectly decoupled.
- **Module 7.4 (Query & Search):** `/v1/query` optionally filters by `notebook_id`. Module 7.2's notebook identity model is 100% compatible.
- **Module 7.5 (Sessions & Notes):** Sessions and Notes belong to notebooks (`notebook_id`). Module 7.2 creates and manages the parent notebook entity.
- **Phase 8 (MCP):** MCP tools `list_notebooks`, `get_notebook_summary`, `get_timeline` map 1:1 to the domain calls established in Module 7.2.
- **Phase 9 (UI):** Notebooks list page, detail tabs (Chat, Sources, Notes), and graph visualization consume the exact endpoints specified in Module 7.2.

---

## 16. Adversarial Review & Edge Case Matrix

| Threat / Edge Case | Likelihood | Impact | Severity | Mitigation Strategy |
|---|---|---|---|---|
| Requesting non-existent notebook UUID | High | Low | **LOW** | `get_notebook` returns `None` → raises `NotFoundError` → clean 404 response |
| Deleting notebook while active query runs | Low | Medium | **MEDIUM** | SQLite foreign keys and WAL mode ensure active query reads consistent snapshot before deletion |
| Updating notebook with empty title `""` | Medium | Low | **LOW** | Pydantic `min_length=1` rejects with 422 before touching core |
| Requesting graph when SurrealDB is disabled | Medium | Medium | **MEDIUM** | Check `supports_graph`; if false, return empty graph payload `{ "nodes": [], "edges": [] }` |
| Calling `/v1/notebooks/{id}/timeline` on empty notebook | Medium | Low | **LOW** | Empty lists for sources, notes, sessions → returns `{ "events": [], "total": 0 }` |
| Simultaneous PATCH requests to same notebook | Low | Low | **LOW** | SQLite atomic `UPDATE` applies last write; both return valid updated snapshots |
| Malformed UUID string in path parameter | High | Low | **LOW** | FastAPI path validator returns 422 with structured validation error |
| Extremely large `limit` parameter (`limit=1000000`) | Medium | Medium | **LOW** | Query parameter constrained to `le=100` via `Query(..., le=100)` |

---

## 17. New ADR Determination

### Recommendation: **ADR-0050 PROPOSED**
While ADR-0049 defined the server application foundation, a dedicated ADR is recommended to formalize:
1. **REST DTO Schema Standard:** Pydantic DTO models separating HTTP JSON representations from core frozen dataclasses.
2. **Pagination Contract:** Standard `PageResponse[T]` envelope containing `items: list[T]`, `next_cursor: str | None`, and `limit: int`.
3. **Timeline Event Contract:** Unified event schema (`event_type`, `event_id`, `timestamp`, `title`, `details`) across sources, notes, and sessions.
4. **Graph DTO Representation:** Standard node (`id`, `label`, `type`, `confidence`) and edge (`source_id`, `target_id`, `relation`, `weight`) JSON schema.

**ADR Title:** `ADR-0050: Notebook and Graph REST API Specification`

---

## 18. Proposed Implementation Blueprint

### Files to Create in Module 7.2:
```
mnemo-server/mnemo_server/
├── routers/
│   ├── __init__.py
│   └── notebooks.py               ← /v1/notebooks router
└── schemas/
    ├── __init__.py
    ├── common.py                  ← Pagination and shared DTOs
    ├── notebooks.py               ← Notebook CRUD request/response DTOs
    └── graph.py                   ← Graph node/edge DTOs

mnemo-server/tests/
└── test_server_notebooks.py       ← Comprehensive test suite for notebook endpoints
```

### Files to Modify in Module 7.2:
```
mnemo-server/mnemo_server/app.py   ← Include notebooks router in create_app()
docs/mnemo_engineering_roadmap.md  ← Update Module 7.2 task status upon completion
```

---

## 19. Explicit Frozen-File DO-NOT-TOUCH List

The following frozen components **MUST NOT** be modified during Module 7.2 implementation:
- `mnemo-core/mnemo/engine.py`
- `mnemo-core/mnemo/config.py`
- `mnemo-core/mnemo/registry.py`
- `mnemo-core/mnemo/models/*`
- `mnemo-core/mnemo/interfaces/*`
- `mnemo-core/mnemo/storage/*`
- `mnemo-core/mnemo/retrieval/*`
- `mnemo-core/mnemo/parsers/*`
- `mnemo-core/mnemo/chunkers/*`
- `plugins/email-ingestion/*`
- `docs/adr/ADR-0001` through `ADR-0049`
- `docs/governance/MODULE_7_1_CLOSURE_REPORT.md`

---

## 20. Final Audit Verdict

```
MODULE_7_2_AUDIT_STATUS:   GREEN WITH CONDITIONS
CONDITIONS:                1. Formalize ADR-0050 for REST DTO schemas & pagination contract prior to code implementation.
                           2. Ensure graceful empty-graph return when SurrealDB is disabled.
FROZEN_CODE_IMPACT:        ZERO (0 files to modify in mnemo-core)
READY_FOR_ADR_0050:        YES
```
