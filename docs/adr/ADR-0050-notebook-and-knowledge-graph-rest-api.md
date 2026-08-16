# ADR-0050: Notebook and Knowledge Graph REST API Specification

- **Status:** Accepted
- **Date:** 2026-08-16
- **Decision Owners:** Mnemo Architecture & Server Maintainers
- **Scope:** Phase 7, Module 7.2 (Notebook CRUD & Graph Endpoints)
- **Supersedes:** None
- **Related Documents:**
  - `docs/mnemo_architecture_v2.md` (§5.1 REST API Surface, §5.2 MCP Server)
  - `docs/mnemo_engineering_roadmap.md` (§7 mnemo-server, §10 Notebook Features, §12 Plugins)
  - `docs/adr/ADR-0001-domain-model-specification.md`
  - `docs/adr/ADR-0002-core-interface-contracts.md`
  - `docs/adr/ADR-0003-hierarchical-configuration.md`
  - `docs/adr/ADR-0004-knowledge-engine-lifecycle.md`
  - `docs/adr/ADR-0005-graph-identity-resolution.md`
  - `docs/adr/ADR-0049-phase-7-server-application-architecture.md`
  - `docs/governance/MODULE_7_2_ARCHITECTURAL_AUDIT.md`
  - `docs/governance/MODULE_7_2_ADVERSARIAL_FORENSIC_REVIEW.md`

---

## 1. Context and Problem Statement

Phase 7 Module 7.1 established the FastAPI application foundation (`mnemo-server`), ASGI lifespan lifecycle, typed `KnowledgeEngine` dependency injection (`get_engine`), `ServerConfig` separation, and uniform JSON error translation ([ADR-0049](ADR-0049-phase-7-server-application-architecture.md)).

Module 7.2 implements the first functional REST endpoints on `mnemo-server` for notebook management, activity timelines, summary views, and knowledge graph visualization. 

Before implementation begins, the HTTP REST contract must be formally frozen. A comprehensive adversarial forensic audit (`docs/governance/MODULE_7_2_ADVERSARIAL_FORENSIC_REVIEW.md`) identified several critical architectural boundaries and two roadmap scope corrections that must be explicitly codified:
1. **Summary Generation vs. Retrieval:** The roadmap wording _"Trigger summary generation if stale"_ represents an aspirational capability whose dependencies (background job worker, multi-source LLM summarization pipeline, staleness detection) reside in Module 10.x. Module 7.2 must define a deterministic, read-only contract over existing persisted insights.
2. **Graph Nodes vs. Edge Availability:** While entity nodes are queryable from frozen storage, `StorageInterfaceV1` does not expose complete `GraphEdge` records (with relation labels and weights). Module 7.2 must provide an honest, nodes-only graph representation without fabricating relationship data.
3. **Concurrency Semantics:** SQLite storage uses unconditional UPSERT for notebooks without version preconditions. The API contract must explicitly declare Last-Write-Wins semantics rather than pretending to offer optimistic concurrency.
4. **Pagination Uniformity:** Keyset pagination must be formalized into a consistent REST DTO envelope with clear parameter bounds and cursor validation.

---

## 2. Architectural Decisions

### Decision 1: REST DTO Boundary & Layering

All HTTP request and response models are transport-layer Data Transfer Objects (DTOs) declared in `mnemo_server.schemas` using Pydantic V2.

- **Isolation:** Frozen `mnemo-core` dataclasses (`Notebook`, `Source`, `Note`, `Session`, `Entity`, `Page[T]`) MUST NOT be directly returned as FastAPI route responses or used as request models.
- **Conversion:** Route handlers in `mnemo-server` explicitly convert between incoming Pydantic request bodies, frozen `mnemo-core` domain objects, and outgoing Pydantic response DTOs.
- **Serialization Standard:**
  - UUID fields are serialized as standard 36-character hyphenated RFC 4122 strings (`"550e8400-e29b-41d4-a716-446655440000"`).
  - Datetime fields are serialized as ISO-8601 strings with explicit UTC indicators (`"2026-08-16T02:30:00Z"`).
  - Metadata is represented as JSON-serializable key-value dictionaries.

---

### Decision 2: Notebook CRUD REST Contract

The following endpoints are frozen for notebook CRUD operations under `/v1/notebooks`:

```
POST   /v1/notebooks               → Create a new notebook
GET    /v1/notebooks               → List notebooks (keyset cursor paginated)
GET    /v1/notebooks/{notebook_id} → Retrieve a notebook by UUID
PATCH  /v1/notebooks/{notebook_id} → Partially update notebook metadata
DELETE /v1/notebooks/{notebook_id} → Delete notebook and cascade-clean associations
```

#### Detailed Endpoint Specifications

1. **`POST /v1/notebooks` (Create)**
   - **Request Body:** `CreateNotebookRequest`
     - `title: str` (required, `1 <= len <= 255`, leading/trailing whitespace stripped)
     - `description: str | None = None` (optional, `1 <= len <= 4096`)
     - `metadata: dict[str, Any] = Field(default_factory=dict)`
   - **Behavior:** Server generates a fresh `uuid4()`, sets `created_at` and `updated_at` to `datetime.now(UTC)`, freezes metadata, and calls `engine.storage.upsert_notebook()`.
   - **Response:** `201 Created` with `NotebookResponse`.

2. **`GET /v1/notebooks` (List)**
   - **Query Parameters:**
     - `limit: int = 50` (integer, `1 <= limit <= 100`)
     - `cursor: str | None = None` (UUID string representing the last seen `notebook_id`)
   - **Response:** `200 OK` with `PageResponse[NotebookResponse]`.

3. **`GET /v1/notebooks/{notebook_id}` (Get)**
   - **Path Parameter:** `notebook_id: UUID` (valid UUID string, rejected with 422 if malformed).
   - **Behavior:** Calls `engine.storage.get_notebook(notebook_id)`.
   - **Response:** `200 OK` with `NotebookResponse`. If `None`, raises `NotFoundError` (translated to `404 Not Found` via ADR-0049).

4. **`PATCH /v1/notebooks/{notebook_id}` (Update)**
   - **Path Parameter:** `notebook_id: UUID`
   - **Request Body:** `UpdateNotebookRequest`
     - `title: str | None = None` (optional, `1 <= len <= 255`)
     - `description: str | None = None` (optional, `1 <= len <= 4096`)
     - `metadata: dict[str, Any] | None = None` (optional, shallow-merged with existing metadata)
   - **Behavior:**
     - Validates that at least one field is provided for update (rejects empty PATCH with 422).
     - Reads current snapshot via `engine.storage.get_notebook(notebook_id)`. If missing, raises `NotFoundError` (404).
     - Constructs updated `Notebook` with `updated_at = datetime.now(UTC)` and calls `engine.storage.upsert_notebook()`.
   - **Concurrency Semantics: LAST-WRITE-WINS (LWW).**
     - SQLite UPSERT in `mnemo-core` performs unconditional overwrite.
     - No `version` field, ETag, `If-Match`, or `expected_version` condition exists on `Notebook`.
     - Simultaneous PATCH requests are serialized by SQLite; the last commit wins silently.
     - Module 7.2 MUST NOT promise optimistic concurrency. Any future optimistic locking requires a dedicated ADR, schema migration, and core update.
   - **Response:** `200 OK` with updated `NotebookResponse`.

5. **`DELETE /v1/notebooks/{notebook_id}` (Delete)**
   - **Path Parameter:** `notebook_id: UUID`
   - **Behavior:** Calls `deleted = await engine.storage.delete_notebook(notebook_id)`.
   - **Response:** `204 No Content` if `deleted is True`. If `False`, raises `NotFoundError` (404).
   - **Cascade Cleanup:** In SQLite, `ON DELETE CASCADE` removes foreign-key child records (`sources`, `notes`, `sessions`, `turns`, `citations`, `insights`). In `CompositeStorage`, pre-projection locks refresh vector index memberships.

---

### Decision 3: Standard REST Pagination Contract

All paginated list endpoints in `mnemo-server` must adhere to a uniform envelope:

```json
{
  "items": [...],
  "next_cursor": "550e8400-e29b-41d4-a716-446655440000",
  "limit": 50
}
```

- **Query Parameters:**
  - `limit: int = Query(default=50, ge=1, le=100)`
  - `cursor: str | None = Query(default=None)`
- **Cursor Semantics:**
  - Cursors are transparent string UUIDs matching the frozen core keyset behavior (`WHERE notebook_id > ? ORDER BY notebook_id ASC LIMIT ? + 1`).
  - `next_cursor` is `null` on the terminal page.
  - If a client supplies a non-null `cursor`, it must be validated as a syntactically valid UUID; malformed cursors MUST return `422 Unprocessable Entity`.
- **Response Schema:** Generic `PageResponse[T]` containing:
  - `items: list[T]`
  - `next_cursor: str | None`
  - `limit: int`

---

### Decision 4: Notebook Summary Contract (Scope Correction)

`GET /v1/notebooks/{notebook_id}/summary`

- **Roadmap Scope Correction:** The earlier roadmap text _"Trigger summary generation if stale"_ is formally deferred. `mnemo-core` contains no background job infrastructure, no multi-source LLM summarization pipeline, and no freshness metadata field on `Notebook`. These capabilities are explicitly scheduled for Module 10.x (dependent on Module 10.1 background workers).
- **Module 7.2 Behavior:** The endpoint is **strictly READ-ONLY**.
  1. Verifies that the notebook exists via `engine.storage.get_notebook(notebook_id)` (returns 404 if not found).
  2. Queries already-persisted summary insights via `engine.storage.list_insights(notebook_id, limit=50, cursor=None)`.
  3. Filters for insights with `type == InsightType.SUMMARY`.
  4. Returns:
     ```json
     {
       "notebook_id": "550e8400-e29b-41d4-a716-446655440000",
       "summaries": [
         {
           "insight_id": "...",
           "source_id": "...",
           "content": "...",
           "confidence": 0.95,
           "created_at": "2026-08-16T02:30:00Z"
         }
       ],
       "status": "ready" | "empty"
     }
     ```
  5. If no summary insights exist, returns `"summaries": []` with `"status": "empty"`.
- **Prohibitions:** The endpoint MUST NOT call the synthesizer LLM, start background processes, fabricate unpersisted summaries, or modify storage.

---

### Decision 5: Notebook Activity Timeline Contract

`GET /v1/notebooks/{notebook_id}/timeline`

- **Distinction:**
  - **Module 7.2 Timeline:** A **notebook activity timeline** synthesizing chronological user and system actions.
  - **Module 12.4 `timeline-gen` Plugin:** An **AI-extracted document historical timeline** (date:event pairs extracted from document prose and persisted in SurrealDB).
- **Module 7.2 Implementation:**
  1. Verifies notebook existence (404 if not found).
  2. Queries existing frozen core storage methods:
     - `engine.storage.list_sources(notebook_id, limit=limit, cursor=None)`
     - `engine.storage.list_notes(notebook_id, limit=limit, cursor=None)`
     - `engine.storage.list_sessions(notebook_id, limit=limit, cursor=None)`
  3. Maps domain records to unified `TimelineEventResponse` objects:
     - `Source` → `event_type = "source_added"`, `event_id = source.source_id`, `timestamp = source.created_at`, `title = "Source Added"`
     - `Note` → `event_type = "note_created"`, `event_id = note.note_id`, `timestamp = note.created_at`, `title = note.title or "Untitled Note"`
     - `Session` → `event_type = "session_started"`, `event_id = session.session_id`, `timestamp = session.created_at`, `title = session.title or "New Conversation"`
  4. Merges all events, sorts by `timestamp` descending (most recent first), and slices to requested `limit` (default 50, max 100).
- **Extensibility:** The `event_type: str` field is open so that Module 12.4 can later introduce `"extracted_event"` without changing the schema envelope.
- **Response Schema (`TimelineResponse`):**
  ```json
  {
    "notebook_id": "550e8400-e29b-41d4-a716-446655440000",
    "events": [
      {
        "event_type": "source_added",
        "event_id": "...",
        "timestamp": "2026-08-16T02:30:00Z",
        "title": "Source Added",
        "details": { "document_id": "..." }
      }
    ],
    "total": 1
  }
  ```

---

### Decision 6: Knowledge Graph Contract (Nodes-Only)

`GET /v1/notebooks/{notebook_id}/graph`

- **Core Limitation:** `StorageInterfaceV1` defines `find_entities()` and `get_related_entities()`. However, `get_related_entities()` returns neighbor `Entity` nodes only; it does NOT return `GraphEdge` records with `relation` and `weight`. Furthermore, no `list_edges_for_document()` or `list_edges_for_notebook()` method exists on the frozen interface.
- **Module 7.2 Decision: NODES ONLY.**
  - The endpoint returns all entity nodes derived from documents associated with the notebook.
  - The `edges` array is explicitly returned as `[]`.
  - The server MUST NOT fabricate mock relations (e.g. `"related_to"`), guess weights, or access private SurrealDB internals.
- **Algorithm:**
  1. Verify notebook existence (404 if not found).
  2. Check graph capability: `engine.storage.capabilities().supports_graph`.
  3. If graph is enabled:
     - Query notebook sources via `engine.storage.list_sources(notebook_id, limit=1000)`.
     - Extract `document_ids = tuple(s.document_id for s in sources.items)`.
     - If `document_ids` is non-empty, query entities via `engine.storage.find_entities(canonical_name="", entity_type=None, document_ids=document_ids, limit=limit)`.
     - Map returned `Entity` records to `GraphNodeResponse`.
- **Response Schema (`EntityGraphResponse`):**
  ```json
  {
    "notebook_id": "550e8400-e29b-41d4-a716-446655440000",
    "nodes": [
      {
        "entity_id": "...",
        "canonical_name": "Antigravity Engine",
        "type": "technology",
        "confidence": 0.98,
        "document_id": "...",
        "aliases": ["AG Engine"]
      }
    ],
    "edges": [],
    "status": "active" | "disabled" | "empty"
  }
  ```
- **Deferred Edge Retrieval:** Full edge retrieval is deferred. Adding `list_edges_for_document()` to `StorageInterfaceV1` in a future phase will require a dedicated ADR and frozen core update.

---

### Decision 7: Graph Disabled Mode Handling

In local-first SQLite deployments where SurrealDB is disabled (`config.storage.surrealdb.enabled = False`), `CompositeStorage` has no built-in fallback guard and delegating graph calls raises `NotImplementedError`.

- **Server-Layer Guard:** `mnemo-server` MUST inspect `engine.storage.capabilities().supports_graph` before calling any graph methods.
- **Deterministic HTTP Behavior:** When `supports_graph is False`:
  - `GET /v1/notebooks/{notebook_id}/graph` returns `200 OK` with:
    ```json
    {
      "notebook_id": "550e8400-e29b-41d4-a716-446655440000",
      "nodes": [],
      "edges": [],
      "status": "disabled"
    }
    ```
  - It MUST NOT raise an unhandled `NotImplementedError` or return `500 Internal Server Error`.

---

### Decision 8: Error Translation Alignment

All Module 7.2 endpoints strictly utilize the error translation boundary established in ADR-0049:

```json
{
  "error": {
    "code": "contract.not_found",
    "message": "Notebook 550e8400-e29b-41d4-a716-446655440000 was not found",
    "details": {},
    "retryable": false
  }
}
```

| Failure Case | Raised Core / Server Exception | HTTP Status | Error Code | Retryable |
|---|---|---|---|---|
| Invalid UUID in path / query | FastAPI `RequestValidationError` | `422 Unprocessable Entity` | `http.validation` | `false` |
| Empty PATCH body | FastAPI `RequestValidationError` | `422 Unprocessable Entity` | `http.validation` | `false` |
| Title empty string (`""`) | Pydantic `ValidationError` | `422 Unprocessable Entity` | `http.validation` | `false` |
| Limit out of bounds (`<1` or `>100`) | FastAPI `RequestValidationError` | `422 Unprocessable Entity` | `http.validation` | `false` |
| Notebook not found | `NotFoundError` | `404 Not Found` | `contract.not_found` | `false` |
| Storage unavailable / lock timeout | `StorageError` | `503 Service Unavailable` | `contract.storage` | `true` |
| Engine not in `READY` state | `DependencyUnavailableError` | `503 Service Unavailable` | `contract.dependency_unavailable` | `true` |
| Request cancelled by client | `asyncio.CancelledError` | `499 Client Closed Request` | `contract.cancelled` | `false` |
| Unexpected internal exception | `Exception` | `500 Internal Server Error` | `internal.error` | `false` (Sanitized) |

---

### Decision 9: Frozen Boundary Commitments

Module 7.2 implementation is strictly constrained to the transport adapter layer (`mnemo-server`).
The following components are **FROZEN** and MUST NOT be modified:

- `mnemo-core/mnemo/engine.py` (KnowledgeEngine composition root)
- `mnemo-core/mnemo/interfaces/*` (All interface protocols and error types)
- `mnemo-core/mnemo/models/*` (All frozen domain models)
- `mnemo-core/mnemo/storage/*` (All storage backend implementations)
- `mnemo-core/mnemo/retrieval/*` (All retrieval, reranking, and fusion logic)
- `plugins/*` (All plugin packages)
- `docs/adr/ADR-0001` through `ADR-0049`

---

### Decision 10: Inventory of Intentional Future Deferrals

To maintain architectural integrity, the following features are explicitly identified as deferred to future modules:

1. **LLM-Driven Notebook Summary Generation:** Deferred to Module 10.2 (depends on Module 10.1 background worker).
2. **Summary Staleness Detection:** Deferred to Module 10.2.
3. **Background Ingestion & Job Queueing:** Deferred to Module 7.3 and Module 10.1.
4. **Complete Knowledge Graph Edge Retrieval:** Deferred to a future phase requiring an explicit `StorageInterfaceV1` update.
5. **Optimistic Concurrency for Notebook Updates:** Deferred to a future ADR requiring a schema migration on `notebooks`.
6. **Semantic Date:Event Timeline Extraction:** Deferred to Module 12.4 (`timeline-gen` plugin).

---

## 3. Endpoint Inventory & DTO Specifications

### Endpoint Summary Table

| Method | Path | Summary | Request DTO | Response DTO | Success Code |
|---|---|---|---|---|---|
| `POST` | `/v1/notebooks` | Create notebook | `CreateNotebookRequest` | `NotebookResponse` | `201 Created` |
| `GET` | `/v1/notebooks` | List notebooks | — | `PageResponse[NotebookResponse]` | `200 OK` |
| `GET` | `/v1/notebooks/{notebook_id}` | Get notebook | — | `NotebookResponse` | `200 OK` |
| `PATCH` | `/v1/notebooks/{notebook_id}` | Update notebook | `UpdateNotebookRequest` | `NotebookResponse` | `200 OK` |
| `DELETE` | `/v1/notebooks/{notebook_id}` | Delete notebook | — | `None` | `204 No Content` |
| `GET` | `/v1/notebooks/{notebook_id}/summary` | Get summaries | — | `NotebookSummaryResponse` | `200 OK` |
| `GET` | `/v1/notebooks/{notebook_id}/timeline` | Get activity timeline | — | `TimelineResponse` | `200 OK` |
| `GET` | `/v1/notebooks/{notebook_id}/graph` | Get entity graph | — | `EntityGraphResponse` | `200 OK` |

---

### Pydantic DTO Schema Definitions

```python
# mnemo_server/schemas/notebooks.py

class CreateNotebookRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    metadata: dict[str, Any] = Field(default_factory=dict)

class UpdateNotebookRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    metadata: dict[str, Any] | None = Field(default=None)

class NotebookResponse(BaseModel):
    notebook_id: UUID
    title: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any]

# mnemo_server/schemas/common.py

class PageResponse[T](BaseModel):
    items: list[T]
    next_cursor: str | None
    limit: int

# mnemo_server/schemas/summary.py

class SummaryItemResponse(BaseModel):
    insight_id: UUID
    source_id: UUID
    content: str
    confidence: float | None
    created_at: datetime

class NotebookSummaryResponse(BaseModel):
    notebook_id: UUID
    summaries: list[SummaryItemResponse]
    status: Literal["ready", "empty"]

# mnemo_server/schemas/timeline.py

class TimelineEventResponse(BaseModel):
    event_type: str
    event_id: UUID
    timestamp: datetime
    title: str
    details: dict[str, Any] = Field(default_factory=dict)

class TimelineResponse(BaseModel):
    notebook_id: UUID
    events: list[TimelineEventResponse]
    total: int

# mnemo_server/schemas/graph.py

class GraphNodeResponse(BaseModel):
    entity_id: UUID
    canonical_name: str
    type: str
    confidence: float
    document_id: UUID
    aliases: list[str]

class GraphEdgeResponse(BaseModel):
    source_id: UUID
    target_id: UUID
    relation: str
    weight: float

class EntityGraphResponse(BaseModel):
    notebook_id: UUID
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse] = Field(default_factory=list)
    status: Literal["active", "disabled", "empty"]
```

---

## 4. Consequences and Impact

### Positive Consequences
1. **Clean Separation of Concerns:** Transport concerns (Pydantic DTOs, HTTP routing, status codes, query validation) live entirely in `mnemo-server`; `mnemo-core` remains pure and HTTP-independent.
2. **Deterministic Error Handling:** Fully integrates with ADR-0049 error envelopes without introducing a second error subsystem.
3. **No Unimplemented Stubs:** Replaces vague "trigger if stale" and "full graph" roadmap ambitions with clean, executable, read-only contracts that match the actual capabilities of the frozen core.
4. **Forward Compatibility:** Activity timeline and nodes-only graph responses are designed with open types (`event_type: str`, `status: str`) so later phases (Modules 10.x and 12.4) can enrich them without breaking the REST contract.

### Negative Consequences / Trade-offs
1. **Nodes-Only Graph:** The UI graph visualization cannot render directed edge relations until a future core extension exposes `GraphEdge` query methods.
2. **No Optimistic Concurrency:** Concurrent edits to a single notebook resolve via Last-Write-Wins. (Acceptable for local-first single-user mode).

---

## 5. Alternatives Considered and Rejected

1. **Directly Exposing Domain Dataclasses as Response Models:** Rejected. Domain dataclasses use frozen tuples, strict immutability, and internal types (`FrozenMetadata`) that do not serialize cleanly with FastAPI/Pydantic without custom encoders.
2. **Fabricating Graph Edges (e.g. creating `"related_to"` dummy edges):** Rejected. Fabricating data at the transport layer violates architectural integrity and misleads callers.
3. **Calling LLM Synthesizer Synchronously in `GET /summary`:** Rejected. LLM synthesis over multiple sources takes seconds, can exceed HTTP gateway timeouts, and lacks background queue infrastructure in Module 7.2.
4. **Implementing Token-Based Encrypted Cursors:** Rejected. For a local-first SQLite database, transparent UUID string cursors provide standard keyset pagination without unnecessary crypto/HMAC overhead.

---

## 6. Implementation Readiness

With the formal acceptance of ADR-0050, the architectural gate for Module 7.2 is complete:
- **ADR-0050 Status:** Accepted
- **Frozen Core Impact:** 0 modified files
- **Ready for Implementation:** Yes
