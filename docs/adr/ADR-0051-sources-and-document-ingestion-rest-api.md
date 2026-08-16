# ADR-0051: Sources and Document Ingestion REST API Specification

- **Status:** Accepted
- **Date:** 2026-08-16
- **Decision Owners:** Mnemo Architecture & Server Maintainers
- **Scope:** Phase 7, Module 7.3 (Sources & Ingestion REST Endpoints)
- **Supersedes:** None
- **Related Documents:**
  - `docs/mnemo_architecture_v2.md` (§5.1 REST API Surface, §9 Document Ingestion Pipeline)
  - `docs/mnemo_engineering_roadmap.md` (§Phase 7 REST API)
  - `docs/adr/ADR-0001-domain-model-specification.md`
  - `docs/adr/ADR-0002-core-interface-contracts.md`
  - `docs/adr/ADR-0008-sqlite-metadata-and-storage.md`
  - `docs/adr/ADR-0010-composite-storage-and-atomic-rollback.md`
  - `docs/adr/ADR-0011-raw-parse-result-boundary.md`
  - `docs/adr/ADR-0013-classifier-boundary.md`
  - `docs/adr/ADR-0014-canonical-document-boundary.md`
  - `docs/adr/ADR-0015-chunk-identity-and-provenance.md`
  - `docs/adr/ADR-0018-embedding-pipeline-orchestration.md`
  - `docs/adr/ADR-0039-multi-source-metadata-projection.md`
  - `docs/adr/ADR-0040-version-aware-sparse-retrieval.md`
  - `docs/adr/ADR-0049-phase-7-server-application-architecture.md`
  - `docs/adr/ADR-0050-notebook-and-knowledge-graph-rest-api.md`
  - `docs/governance/MODULE_7_3_ARCHITECTURAL_AUDIT.md`
  - `docs/governance/MODULE_7_3_TARGETED_RECONCILIATION.md`

---

## 1. Context and Problem Statement

Phase 7 Modules 7.1 and 7.2 established the FastAPI application runtime, error taxonomy ([ADR-0049](ADR-0049-phase-7-server-application-architecture.md)), and notebook REST API ([ADR-0050](ADR-0050-notebook-and-knowledge-graph-rest-api.md)).

Module 7.3 implements the sources and document ingestion REST endpoints under `/v1/notebooks/{notebook_id}/sources`. This encompasses file uploads, content-type detection, parsing, cleaning, classification, asset persistence, canonicalization, semantic chunking, vector embedding, SQLite and Qdrant indexing, source association, source lifecycle status reporting, and source deletion.

Before implementation begins, this ADR freezes the architectural decisions, REST API contracts, deduplication rules, upload memory safety bounds, concurrency guarantees, and error translations governing Module 7.3.

---

## 2. Architectural Decisions

### Decision 1: REST DTO Boundary & Layering

All request and response models for sources and ingestion are transport-layer Data Transfer Objects (DTOs) declared in `mnemo_server.schemas.sources` using Pydantic V2.

- **Isolation:** Frozen `mnemo-core` dataclasses (`Source`, `Document`, `DocumentVersion`, `DocumentMetadata`, `Chunk`, `Page[T]`) MUST NOT be directly returned as FastAPI route responses or used as request models.
- **Conversion:** Route handlers and server-side services in `mnemo-server` explicitly transform incoming multipart data and core domain objects into Pydantic response DTOs.
- **Standard Formatting:**
  - UUID fields are serialized as standard 36-character RFC 4122 strings.
  - Datetime fields are serialized as ISO-8601 UTC strings (`"2026-08-16T12:00:00Z"`).
  - Metadata dictionaries are cleanly unpacked from `FrozenMetadata`.

---

### Decision 2: Sources REST Endpoints Contract

The following 5 endpoints are frozen under `/v1/notebooks/{notebook_id}/sources`:

```
POST   /v1/notebooks/{notebook_id}/sources             → Ingest new source (multipart upload)
GET    /v1/notebooks/{notebook_id}/sources             → List sources (keyset cursor paginated)
GET    /v1/notebooks/{notebook_id}/sources/{source_id} → Retrieve source and document metadata
DELETE /v1/notebooks/{notebook_id}/sources/{source_id} → Delete source association and update memberships
GET    /v1/notebooks/{notebook_id}/sources/{source_id}/status → Retrieve persisted ingestion lifecycle status
```

#### Endpoint Summary Table

| Method | Path | Request Body / Params | Response DTO | Success Code | Description |
|---|---|---|---|---|---|
| `POST` | `/v1/notebooks/{notebook_id}/sources` | `multipart/form-data` (`file: UploadFile`) | `SourceResponse` | `201 Created` | Ingests file, runs parsing/chunking/embedding/indexing, links source. |
| `GET` | `/v1/notebooks/{notebook_id}/sources` | Query: `limit: int = 50`, `cursor: UUID \| None = None` | `PageResponse[SourceResponse]` | `200 OK` | Lists sources in notebook with keyset pagination. |
| `GET` | `/v1/notebooks/{notebook_id}/sources/{source_id}` | Path: `notebook_id: UUID`, `source_id: UUID` | `SourceResponse` | `200 OK` | Retrieves source details and linked document summary. |
| `DELETE` | `/v1/notebooks/{notebook_id}/sources/{source_id}` | Path: `notebook_id: UUID`, `source_id: UUID` | `None` (empty body) | `204 No Content` | Removes source association and updates Qdrant membership projection. |
| `GET` | `/v1/notebooks/{notebook_id}/sources/{source_id}/status` | Path: `notebook_id: UUID`, `source_id: UUID` | `SourceStatusResponse` | `200 OK` | Returns current persisted `DocumentStatus` (`indexing`, `indexed`, `failed`). |

---

### Decision 3: Document-Level vs. Source-Level Deduplication

A strict architectural separation is enforced between **document-level** and **source-level** deduplication:

1. **Document-Level Deduplication (Core Responsibility):**
   - Handled by `ParserRouter.route()` and `StorageInterfaceV1.get_document_by_content_hash()`.
   - Compares the SHA-256 digest (`content_hash`) of incoming file bytes.
   - If a matching document already exists in the system, parsing, canonicalization, chunking, and embedding are skipped entirely.
2. **Source-Level Deduplication (Server Responsibility):**
   - Handled by `mnemo-server` via SQLite's `uq_sources_notebook_document` unique constraint (`UNIQUE(notebook_id, document_id)`).
   - **Same Content + Same Notebook:** Re-uploading an identical file to the same notebook is rejected with `ConflictError` (`409 Conflict`).
   - **Same Content + Different Notebook:** Uploading an existing file to a different notebook reuses the canonical `Document` and `Chunk` vectors, creates a new `Source` row (`source_id = uuid4()`), and updates Qdrant point vector `notebook_ids` payloads via `CompositeStorage.upsert_source()`. Returns `201 Created` with `deduplicated: true`.

---

### Decision 4: Server-Side Ingestion Pipeline Architecture

Because `KnowledgeEngine` is an architectural composition root and does not expose a monolithic `engine.ingest()` method, `mnemo-server` implements a lightweight `IngestionService` coordinating frozen core primitives:

```
[HTTP Request: UploadFile]
         │
         ▼
[1. Bounded Chunk Streaming Reader (max 50 MB limit)]
         │
         ▼
[2. Notebook Existence Check (storage.get_notebook)]
         │
         ▼
[3. Content-Hash Calculation (sha256)]
         │
         ├───────────────────────────────────────────────┐
         │                                               │
   [Hash Match: Deduplication Hit]             [Hash Miss: New Document]
         │                                               │
         ▼                                               ▼
[Check Existing Source in Notebook]         [4. Offloaded Parsing (asyncio.to_thread)]
   └─ Found: 409 Conflict                   [5. Cleaner & Classifier (in-memory)]
   └─ Not Found: Link Existing Doc           [6. Asset Persistence (storage.put_asset)]
         │                                  [7. Canonicalizer (in-memory)]
         ▼                                  [8. IR Persistence (storage.put_parsed_document)]
[Create Source Association]                 [9. Document Record (DocumentStatus.INDEXING)]
         │                                  [10. ChunkerDispatcher (in-memory)]
         ▼                                  [11. EmbedderModule (Ollama embedding)]
[storage.upsert_source]                     [12. Vector & FTS Indexing (storage.upsert_chunks)]
(Refreshes Qdrant Memberships)              [13. Document Update (DocumentStatus.INDEXED)]
         │                                  [14. Create Source & storage.upsert_source]
         │                                               │
         └───────────────────────┬───────────────────────┘
                                 │
                                 ▼
                    [Return SourceResponse DTO]
```

- **Token Counter Resolution:** `IngestionService` resolves the canonical `O200KBaseTokenCounter` from `request.app.state.token_counter` (provisioned during server lifespan).
- **Chunker Dispatcher:** Dispatches chunks via `ChunkerDispatcher(engine.registry, token_counter)` selecting the strategy by `document.doc_type`.
- **Embedder Module:** Executes batch embeddings via `EmbedderModule(engine.embedding_provider)`.

---

### Decision 5: Async and Event-Loop Safety

Synchronous CPU-bound parsing operations MUST NOT block the FastAPI asyncio event loop:

- **Threadpool Delegation:** `ParserRouter.route()` and `IngestionPipeline.ingest()` (which invoke PyMuPDF C-level PDF parsing, python-docx XML parsing, BeautifulSoup DOM traversal, and markdown tokenization) are executed inside worker threads using `asyncio.to_thread()`.
- **Async I/O:** All storage operations (`put_asset`, `put_parsed_document`, `upsert_document`, `upsert_chunks`, `upsert_source`) and embedding calls (`embed_chunks`) remain purely asynchronous.

---

### Decision 6: Upload Size & Memory Safety

To prevent memory exhaustion attacks from unbounded multipart uploads:

1. **Configurable Limit:** `ServerConfig.max_upload_bytes` defines the maximum permitted payload size (default: `52_428_800` bytes / 50 MB).
2. **Bounded Chunked Reading:** `mnemo-server` reads incoming `UploadFile` streams in bounded 1 MB chunks (`await file.read(1024 * 1024)`), tracking cumulative byte count.
3. **Immediate 413 Rejection:** If the cumulative size exceeds `max_upload_bytes`, reading aborts immediately and raises a Starlette `HTTPException(status_code=413, detail=...)`.
4. **Transport-Layer Error Envelope:** Under ADR-0049, Starlette 413 exceptions are translated to:
   ```json
   {
     "error": {
       "code": "http.413",
       "message": "File upload exceeds maximum permitted size of 52428800 bytes",
       "details": {},
       "retryable": false
     }
   }
   ```
   No modifications to frozen core error classes or ADR-0049 are made.

---

### Decision 7: SQLite Concurrency Reality

`SQLiteStore` in frozen core executes `PRAGMA foreign_keys = ON;` and `PRAGMA journal_mode = WAL;`. `SQLiteStore` does NOT configure `PRAGMA busy_timeout` (the 30s timeout exists only in `SQLiteEmbeddingCache`).

- `SQLiteStore` relies on `aiosqlite` default timeouts and SQLite WAL concurrency.
- When write contention occurs, SQLite operational errors propagate as `StorageError`.
- Under ADR-0049, `StorageError` is translated to HTTP `503 Service Unavailable` with `code = "contract.storage"` and `retryable = true`.

---

### Decision 8: Failure & Partial State Semantics

1. **Compensated Multi-Store Writes:** `CompositeStorage.upsert_chunks` and `CompositeStorage.upsert_source` include snapshot-and-rollback compensators (`_Compensator`). If a write to Qdrant fails, SQLite chunk tables and membership projections are rolled back automatically.
2. **Orphaned Content-Addressed Blobs:** If ingestion fails prior to `upsert_chunks` (e.g. during embedding), binary assets written via `put_asset` and intermediate documents written via `put_parsed_document` remain in filesystem blob storage as unreferenced, content-addressed files. These are harmless and do not corrupt database integrity.
3. **Document Failure State:** If document creation begins and subsequent chunking/embedding fails, the document record transitions to `DocumentStatus.FAILED`.

---

### Decision 9: Document Status Lifecycle

The API uses the frozen domain `DocumentStatus` enum without introducing synthetic states:

```python
class DocumentStatus(StrEnum):
    PENDING = "pending"
    INDEXING = "indexing"
    INDEXED = "indexed"
    ENRICHED = "enriched"
    FAILED = "failed"
```

- Ingestion begins in `INDEXING` state.
- Ingestion completes in `INDEXED` state.
- Unhandled ingestion errors record `FAILED` state.
- `GET /v1/notebooks/{id}/sources/{sid}/status` returns the persisted `DocumentStatus` value.

---

### Decision 10: Source CRUD & Deletion Semantics

1. **Listing Sources (`GET /v1/notebooks/{id}/sources`):**
   - Returns keyset-paginated `PageResponse[SourceResponse]` using UUID cursor.
   - Enforces `1 <= limit <= 100` (default: 50).
2. **Retrieving Single Source (`GET /v1/notebooks/{id}/sources/{source_id}`):**
   - Validates that `source.notebook_id == notebook_id`. Returns `404 Not Found` if mismatched or nonexistent.
3. **Deleting Source (`DELETE /v1/notebooks/{id}/sources/{source_id}`):**
   - Validates notebook association and calls `storage.delete_source(source_id)`.
   - `CompositeStorage.delete_source` deletes the junction row in `sources` and triggers `_refresh_memberships`.
   - If other notebooks reference the same document, their notebook IDs are preserved in Qdrant point vector payloads.
   - If no other notebooks reference the document, `notebook_ids` in Qdrant is updated to empty `()`, excluding it from notebook queries.
   - Underlying chunks and document records in SQLite and Qdrant are preserved.
   - Returns `204 No Content`.

---

### Decision 11: Ingestion Status Polling Endpoint

`GET /v1/notebooks/{notebook_id}/sources/{source_id}/status` provides a lightweight polling endpoint returning:

```json
{
  "source_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "notebook_id": "123e4567-e89b-12d3-a456-426614174000",
  "document_id": "e4eaaaf2-d142-11e1-b3e4-080027620cdd",
  "status": "indexed",
  "created_at": "2026-08-16T12:00:00Z",
  "updated_at": "2026-08-16T12:00:05Z",
  "error_message": null
}
```

This endpoint reports real persisted `DocumentStatus` rather than simulating a distributed job queue.

---

### Decision 12: Keyset Pagination Envelope

Reuses the `PageResponse[T]` schema established in ADR-0050:

```json
{
  "items": [...],
  "next_cursor": "550e8400-e29b-41d4-a716-446655440000",
  "limit": 50
}
```

- Invalid cursor strings return HTTP `422 Unprocessable Entity` (`code: "http.validation"`).
- `limit < 1` or `limit > 100` returns HTTP `422 Unprocessable Entity`.

---

### Decision 13: Error Translation Mapping

Conforms strictly to [ADR-0049](ADR-0049-phase-7-server-application-architecture.md):

| Condition | Exception | HTTP Status | Code | Retryable |
|---|---|---|---|---|
| Malformed UUID in path/query | `RequestValidationError` | `422` | `http.validation` | `false` |
| Empty file / invalid form | `RequestValidationError` | `422` | `http.validation` | `false` |
| Notebook or source not found | `NotFoundError` | `404` | `contract.not_found` | `false` |
| Duplicate source in notebook | `ConflictError` | `409` | `contract.conflict` | `false` |
| Unsupported file extension/MIME | `UnsupportedError` | `400` | `contract.unsupported` | `false` |
| File exceeds max size | `HTTPException(413)` | `413` | `http.413` | `false` |
| Embedding provider unavailable | `DependencyUnavailableError` | `503` | `contract.dependency_unavailable` | `true` |
| SQLite/Qdrant storage lock/error | `StorageError` | `503` | `contract.storage` | `true` |
| Unhandled server exception | `Exception` | `500` | `internal.unhandled` | `false` |

---

### Decision 14: Frozen Boundary Integrity

Module 7.3 MUST NOT modify any files in:
- `mnemo-core/`
- `plugins/`
- `docs/adr/ADR-0001` through `ADR-0050`

All ingestion orchestration, file validation, DTO conversion, and endpoint routing belong exclusively to `mnemo-server`.

---

### Decision 15: Explicitly Deferred Capabilities

The following capabilities are deliberately excluded from Module 7.3 and deferred to their designated roadmap modules:
1. **Background Ingestion Job Workers / Celery / Redis:** Deferred to cloud/cluster deployment phases.
2. **Optical Character Recognition (OCR) / Scanned PDF Parsing:** Deferred to Phase 12 plugin modules (`deepdoc-parser`, `mineru-parser`).
3. **Automatic LLM Summary Generation on Upload:** Deferred to Module 10.x.
4. **Knowledge Graph Entity/Edge Extraction on Ingestion:** Handled by Phase 12 `graph-retrieval` plugin.
5. **Document-Level Permanent Purge (`delete_document_cascade`):** Maintained as internal storage API, not exposed as public source CRUD.

---

## 3. Consequences

### Positive
- Delivers complete, working document ingestion for 7 standard formats without modifying frozen core.
- Enforces strict memory and upload bounds, protecting against memory exhaustion attacks.
- Guarantees event-loop responsiveness by offloading C-level PDF and DOCX parsing to threadpools.
- Leverages existing content-addressable deduplication and multi-backend compensation in `CompositeStorage`.
- Full alignment with ADR-0049 and ADR-0050 schemas and error contracts.

### Negative / Trade-offs
- Ingestion runs within the HTTP request lifecycle; extremely large files (e.g. 1,000-page PDFs) may take 5–15 seconds to parse and embed before HTTP response returns.
- Filesystem blobs created prior to early failure are not actively garbage-collected in Module 7.3.

---

## 4. Quality Gates & Acceptance Criteria

1. **Unit & Integration Tests:** Comprehensive test suite in `mnemo-server/tests/test_server_sources.py` covering all 5 endpoints, duplicate rejections, deduplication reuse, 413 limits, 404 missing handling, 400 unsupported formats, and pagination.
2. **Workspace Test Gate:** All 1,190+ workspace tests pass with 0 failures.
3. **Coverage Gate:** Total workspace line and branch coverage `>= 90.00%`.
4. **Code Quality:** `ruff check .` and `ruff format --check .` 100% clean.
5. **Type Safety:** `mypy --strict` passes across all packages with 0 errors.
6. **Packaging:** `uv build --package mnemo-server` succeeds.
