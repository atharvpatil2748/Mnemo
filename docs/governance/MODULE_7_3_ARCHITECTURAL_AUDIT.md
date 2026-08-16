# Module 7.3 — Sources & Ingestion REST Endpoints: Pre-Implementation Architectural Audit

- **Target Module:** Phase 7, Module 7.3 (Sources and Ingestion Endpoints)
- **Status:** GREEN WITH CONDITIONS
- **Audit Date:** 2026-08-16
- **Baseline Commit:** `79bef22b91c31ae985468d96c02fb732807488eb` (Module 7.2 closed, `origin/main` synchronized)
- **Governing Architecture:** `docs/mnemo_architecture_v2.md` (§5.1, §9) & `docs/mnemo_engineering_roadmap.md` (§Phase 7)
- **New ADR Required:** YES — ADR-0051 (*Sources and Document Ingestion REST API Specification*)

---

## 1. Executive Summary

This pre-implementation architectural audit evaluates the feasibility, contract integrity, async safety, and frozen-boundary compatibility of implementing **Module 7.3: Sources & Ingestion REST Endpoints** in `mnemo-server`.

### Key Findings
1. **Core Capabilities Fully Implemented:** Frozen Phases 0–6 contain all necessary domain primitives:
   - Parsing: `ParserRouter` (Phase 3) routing 7 built-in formats (`PDF`, `DOCX`, `Markdown`, `HTML`, `Plain Text`, `JSON`, `CSV/TSV`).
   - Normalization & Classification: `DocumentCleaner` and `DocumentClassifier`.
   - Intermediate Representation: `DocumentCanonicalizer` and `ParsedDocument`.
   - Asset Storage: `StorageInterfaceV1.put_asset` (content-addressed filesystem blobs).
   - Chunking: `ChunkerDispatcher` (Phase 4) with 9 semantic strategies selecting by `DocType`.
   - Embedding: `EmbedderModule` (Phase 5) batching vectors via `EmbeddingProviderV1` (`OllamaEmbedder`).
   - Indexing: `StorageInterfaceV1.upsert_chunks` (atomic write to SQLite FTS5 + Qdrant vector index).
   - Source Linking: `StorageInterfaceV1.upsert_source` (atomic write to SQLite `sources` + Qdrant `notebook_ids` projection).
2. **Zero Core Modifications Required:** Ingestion coordination can be assembled in `mnemo-server` using the public interfaces and composition roots already provided by `KnowledgeEngine` (`engine.storage`, `engine.registry`, `engine.embedding_provider`, and `app.state.token_counter`).
3. **Identity & Deduplication Invariants:**
   - Content deduplication is already built into `ParserRouter` and SQLite schema (`uq_sources_notebook_document`).
   - If a file with matching `sha256` content hash is ingested into a new notebook, the existing `Document` and `Chunk` vectors are reused, and a new `Source` association is linked.
   - If the exact same document is uploaded to the same notebook a second time, SQLite raises a unique constraint violation translated to `ConflictError` (`409 Conflict`).
4. **Execution Model:**
   - For desktop/local-first scale, request-scoped async execution with CPU-bound parsing offloaded to `asyncio.to_thread` guarantees that the FastAPI asyncio event loop never blocks.
   - Status polling endpoint `GET /v1/notebooks/{id}/sources/{sid}/status` queries the persisted `Document.status` (`pending`, `indexing`, `indexed`, `failed`).
5. **Architectural Verdict:** **GREEN WITH CONDITIONS** (Conditions: ADR-0051 must specify multipart limits, content-type resolution, deduplication response format, threadpool offloading, and error translations).

---

## 2. Phase 1 — Module 7.3 Requirement Matrix

| Endpoint | Method | Path | Request Format | Response Format | Status Codes | Description / Constraints |
|---|---|---|---|---|---|---|
| Ingest Source | `POST` | `/v1/notebooks/{id}/sources` | `multipart/form-data` (`file: UploadFile`) | `SourceResponse` | `201 Created`, `400`, `404`, `409`, `413`, `415`, `422`, `503` | Ingests file bytes, parses, canonicalizes, chunks, embeds, indexes, and links source to notebook. |
| List Sources | `GET` | `/v1/notebooks/{id}/sources` | Query: `limit`, `cursor` | `PageResponse[SourceResponse]` | `200 OK`, `404`, `422`, `503` | Keyset-paginated list of sources in the notebook. |
| Get Source | `GET` | `/v1/notebooks/{id}/sources/{sid}` | — | `SourceResponse` | `200 OK`, `404`, `422`, `503` | Retrieves source metadata, linked document metadata, chunk count, and status. |
| Delete Source | `DELETE` | `/v1/notebooks/{id}/sources/{sid}` | — | `None` (empty body) | `204 No Content`, `404`, `422`, `503` | Deletes source association and updates Qdrant membership projection. |
| Ingestion Status | `GET` | `/v1/notebooks/{id}/sources/{sid}/status` | — | `SourceStatusResponse` | `200 OK`, `404`, `422`, `503` | Polling endpoint returning the current document lifecycle status (`indexing`, `indexed`, `failed`). |

---

## 3. Phase 2 — Endpoint-to-Core Call Chain Mapping

### 3.1 `POST /v1/notebooks/{notebook_id}/sources` (Ingest Source)
```
HTTP POST (multipart/form-data)
  → FastAPI router: validate notebook_id (UUID), read UploadFile bytes, check size limit
  → engine.storage.get_notebook(notebook_id) [404 if None]
  → Compute content_hash = sha256(raw_bytes).hexdigest()
  → engine.storage.get_document_by_content_hash(content_hash)
      ├─ [Hit]: Existing document found (Deduplication)
      │    → Check existing source in notebook [409 Conflict if duplicate]
      │    → Create Source(source_id=uuid4(), notebook_id=notebook_id, document_id=existing.document_id)
      │    → engine.storage.upsert_source(source) [triggers Qdrant membership refresh]
      │    → Return SourceResponse(status="indexed", deduplicated=True) [201 Created]
      │
      └─ [Miss]: New document ingestion
           → asyncio.to_thread(ParserRouter.route, raw_bytes, filename) → ParseResult
           → DocumentCleaner.clean(routed)
           → DocumentClassifier.classify(cleaned, filename)
           → engine.storage.put_asset(...) for transient assets
           → DocumentCanonicalizer.canonicalize(...) → ParsedDocument
           → engine.storage.put_parsed_document(version_id, parsed_doc)
           → engine.storage.upsert_document(Document(status=INDEXING))
           → ChunkerDispatcher.dispatch(parsed_doc, context) → tuple[Chunk, ...]
           → EmbedderModule.embed_chunks(chunks) → tuple[Chunk(embedding=...), ...]
           → engine.storage.upsert_chunks(embedded_chunks)
           → engine.storage.upsert_document(Document(status=INDEXED))
           → engine.storage.upsert_source(Source(...))
           → Return SourceResponse(status="indexed", deduplicated=False) [201 Created]
```

### 3.2 `GET /v1/notebooks/{notebook_id}/sources` (List Sources)
```
HTTP GET ?limit=50&cursor=...
  → FastAPI router: validate notebook_id (UUID), cursor (UUID | None), limit (1..100)
  → engine.storage.get_notebook(notebook_id) [404 if None]
  → engine.storage.list_sources(notebook_id=notebook_id, limit=limit, cursor=cursor_str) → Page[Source]
  → For each source:
      → engine.storage.get_document(source.document_id)
  → Map to PageResponse[SourceResponse] [200 OK]
```

### 3.3 `GET /v1/notebooks/{notebook_id}/sources/{source_id}` (Get Source Metadata)
```
HTTP GET /v1/notebooks/{id}/sources/{sid}
  → FastAPI router: validate notebook_id (UUID), source_id (UUID)
  → engine.storage.get_notebook(notebook_id) [404 if None]
  → engine.storage.get_source(source_id) [404 if None or source.notebook_id != notebook_id]
  → engine.storage.get_document(source.document_id)
  → Return SourceResponse [200 OK]
```

### 3.4 `DELETE /v1/notebooks/{notebook_id}/sources/{source_id}` (Delete Source)
```
HTTP DELETE /v1/notebooks/{id}/sources/{sid}
  → FastAPI router: validate notebook_id (UUID), source_id (UUID)
  → engine.storage.get_notebook(notebook_id) [404 if None]
  → engine.storage.get_source(source_id) [404 if None or source.notebook_id != notebook_id]
  → engine.storage.delete_source(source_id) [CompositeStorage removes notebook_id from Qdrant vectors]
  → Return Response(status_code=204) [204 No Content]
```

### 3.5 `GET /v1/notebooks/{notebook_id}/sources/{source_id}/status` (Ingestion Status)
```
HTTP GET /v1/notebooks/{id}/sources/{sid}/status
  → FastAPI router: validate notebook_id (UUID), source_id (UUID)
  → engine.storage.get_notebook(notebook_id) [404 if None]
  → engine.storage.get_source(source_id) [404 if None or source.notebook_id != notebook_id]
  → engine.storage.get_document(source.document_id)
  → Return SourceStatusResponse(source_id, document_id, status=doc.status, ...) [200 OK]
```

---

## 4. Phase 3 — Deep Ingestion Pipeline Investigation

1. **How a source/document enters Mnemo:** User submits a file upload via `POST /v1/notebooks/{id}/sources` as `multipart/form-data`.
2. **How raw content is represented:** Raw content is received as in-memory `bytes` from `UploadFile.read()`.
3. **How a document is persisted:**
   - Raw binary assets are persisted via `storage.put_asset` in content-addressed filesystem storage.
   - Intermediate parsed representation is saved via `storage.put_parsed_document` in filesystem storage.
   - Document registry record and its versions are saved via `storage.upsert_document` in SQLite `documents` and `document_versions` tables.
4. **How parsing is selected:** `ParserRouter` resolves MIME type (via `python-magic` or file extension) and delegates to the appropriate `ParserInterface` registered in `PluginRegistry` (`.pdf`, `.docx`, `.md`, `.html`, `.txt`, `.json`, `.csv`).
5. **How chunks are generated:** `ChunkerDispatcher` matches `document.doc_type` to a registered `ChunkerInterfaceV2` strategy (e.g. `BookChunker`, `PaperChunker`, `GenericChunker`) and materializes deterministic `Chunk` models with `BlockSpan` ordinal tracking.
6. **How embeddings are generated:** `EmbedderModule` batches chunks and queries `EmbeddingProviderV1.embed_batch` (`OllamaEmbedder`), attaching dense float vectors to `Chunk.embedding`.
7. **How vectors are persisted:** `CompositeStorage.upsert_chunks` writes chunks to SQLite `chunks` (with FTS5 trigger) and inserts point vectors with `notebook_ids` payloads into Qdrant collection.
8. **How source/document identity is established:**
   - `content_hash`: SHA-256 digest of input bytes.
   - `document_id`: Deterministic UUID derived from `content_hash` via `uuid5(NAMESPACE_URL, f"mnemo-document:{content_hash}")`.
   - `version_id`: UUID derived from version metadata.
   - `source_id`: Unique UUID representing the association between a specific `notebook_id` and `document_id`.
9. **How ingestion failures are represented:**
   - If parsing/embedding fails, document record transitions to `DocumentStatus.FAILED` in SQLite, or raises a structured exception mapping to ADR-0049.
10. **Synchronous vs Asynchronous:**
    - The core interfaces are 100% async (`async def put_asset`, `async def upsert_chunks`, `async def embed_batch`).
    - CPU-bound parsing (`PyMuPDF`) is synchronous and must be executed in a worker thread (`asyncio.to_thread`).
11. **FastAPI Request Safety:** Safe to invoke directly from FastAPI request handler when bounded by upload size limits (e.g. 50 MB) and executed with `asyncio.to_thread` for CPU parsers.
12. **Event Loop Blocking:** PyMuPDF C-level PDF parsing and python-docx XML parsing are CPU-intensive. Running them inside `asyncio.to_thread` prevents event loop blocking.
13. **Background Job Requirement:** A heavyweight background job broker (Celery/Redis) is NOT required for Phase 7 single-user/desktop deployment; request-level async execution meets all requirements.
14. **Dependencies on Future Modules:** Module 7.3 relies strictly on completed Phases 0–6 and Module 7.1/7.2. Zero dependency on future modules.

---

## 5. Phase 4 — Source vs Document Semantics & Identity Model

### Conceptual Hierarchy
- **`Notebook`:** A user-facing collection/workspace (1 `Notebook` has N `Sources`).
- **`Document`:** An immutable, content-addressed digital artifact defined by its `content_hash` (SHA-256).
- **`Source`:** A many-to-one junction entity associating a `Document` with a specific `Notebook` (`(notebook_id, document_id)`).
- **`Chunk`:** A discrete, embeddable semantic segment of a `DocumentVersion`.

### Deduplication & Idempotency Rules
1. **Intra-Notebook Duplicate (Same File to Same Notebook):**
   - SQLite enforces `UNIQUE(notebook_id, document_id)` on `sources`.
   - Attempting to upload the exact same file to the same notebook raises `ConflictError` (`409 Conflict`).
2. **Cross-Notebook Deduplication (Same File to Different Notebook):**
   - `ParserRouter` detects matching `content_hash`.
   - Skips parsing, chunking, and embedding entirely.
   - Inserts a new `Source(source_id=uuid4(), notebook_id=new_notebook_id, document_id=existing_doc_id)`.
   - `CompositeStorage.upsert_source` refreshes Qdrant payloads, adding `new_notebook_id` to the existing point vectors.
   - Fast sub-10ms response.

---

## 6. Phase 5 — File Upload / Multipart Forensics

1. **Multipart Handling:** FastAPI `UploadFile` (spooled temporary file in memory/disk).
2. **Filename Sanitization:** Path traversal attacks (`../../etc/passwd`) are neutralized by extracting `Path(file.filename).name` and validating non-empty string.
3. **MIME Type Validation:**
   - Primary: `python-magic` inspection of initial bytes.
   - Fallback: standard `mimetypes` extension matching.
   - Unsupported types raise `UnsupportedError` (`400 Bad Request` or `415 Unsupported Media Type`).
4. **Size Bounds:** Configurable `max_upload_bytes` on `ServerConfig` (default: 50 MB). Files exceeding limit immediately return `413 Payload Too Large`.
5. **Empty Files:** Files with 0 bytes return `422 Unprocessable Entity`.
6. **Cleanup on Error:** Transient assets and temporary buffers are cleaned up if parsing fails before persistence.

---

## 7. Phase 6 — Async / Concurrency / Performance Audit

| Operation | Nature | Potential Event-Loop Impact | Mitigation Strategy |
|---|---|---|---|
| `file.read()` | Async I/O | None | Async streaming read from SpooledTemporaryFile |
| `ParserRouter.route` | CPU-bound | Blocks if large PDF/DOCX | Wrap in `asyncio.to_thread` |
| `DocumentCleaner` / `Classifier` | CPU-bound | Negligible (<5ms) | Pure in-memory transformation |
| `put_asset` / `put_parsed_document` | Disk I/O | None | Uses `aiofiles` / async filesystem storage |
| `ChunkerDispatcher.dispatch` | CPU-bound | Low (<20ms) | Pure in-memory tokenization |
| `EmbedderModule.embed_chunks` | Network I/O | None | Async HTTP call to Ollama with capacity limiter |
| `upsert_chunks` (SQLite + Qdrant) | DB / Network | None | Async transactions with SQLite WAL & Qdrant gRPC/HTTP |

---

## 8. Phase 7 — Error Contract Compatibility Table

| Exception | Core Taxonomy Code | HTTP Status | Retryable | Response Details |
|---|---|---|---|---|
| `ContractValidationError` | `contract.validation` | `422` | `False` | Field-level validation error |
| `NotFoundError` | `contract.not_found` | `404` | `False` | `{"notebook_id": "..."}` or `{"source_id": "..."}` |
| `ConflictError` | `contract.conflict` | `409` | `False` | Duplicate source in notebook |
| `UnsupportedError` | `contract.unsupported` | `400` / `415` | `False` | Unsupported MIME type / file extension |
| `StorageError` | `contract.storage` | `503` | `True` | Database lock / storage failure details |
| `DependencyUnavailableError` | `contract.dependency_unavailable` | `503` | `True` | Embedding model / Qdrant offline |
| `PayloadTooLargeError` | `http.413` | `413` | `False` | File size exceeds configured limit |

All error translations conform 100% to [ADR-0049](../adr/ADR-0049-phase-7-server-application-architecture.md).

---

## 9. Phase 8 — ADR Compatibility Matrix

| Requirement | Governing ADR | Current Implementation | Compatible? | Risk | Resolution |
|---|---|---|---|---|---|
| Thin Adapter API | ADR-0049 | `mnemo-server` contains zero domain logic; orchestrates core components | YES | None | Maintain clean separation |
| Keyset Pagination | ADR-0050 | `PageResponse[SourceResponse]` uses UUID cursor | YES | None | Reuse common DTO |
| Content Deduplication | ADR-0001, ADR-0014 | `content_hash` sha256 lookup in `ParserRouter` | YES | None | Preserved |
| Chunk Provenance | ADR-0015 | `BlockSpan` and sha256 chunk IDs | YES | None | Preserved |
| Qdrant Notebook Filtering | ADR-0039, ADR-0040 | `CompositeStorage._refresh_memberships` | YES | None | Verified in Phase 5/6 |
| Token Counter Injection | ADR-0047 | `app.state.token_counter` provisioned on startup | YES | None | Injected via dependency |

---

## 10. Phase 9 — Adversarial Counter-Analysis (10 Explicit Challenges)

1. **Challenge 1:** *"The ingestion pipeline is already a single method on KnowledgeEngine."*
   - **Counter-evidence:** `KnowledgeEngine` does NOT expose an `engine.ingest()` facade. It provides `storage`, `registry`, and `embedding_provider`. Ingestion coordination must be assembled cleanly in the transport layer without altering frozen core.
2. **Challenge 2:** *"File upload directly into memory will crash the server on 1 GB files."*
   - **Counter-evidence:** `ServerConfig.max_upload_bytes` (50 MB limit) rejects oversized files upfront before buffering.
3. **Challenge 3:** *"Parsing large PDFs will block the asyncio event loop."*
   - **Counter-evidence:** The parsing invocation is wrapped in `asyncio.to_thread`, delegating C-level parsing to the default threadpool.
4. **Challenge 4:** *"Concurrent uploads to the same notebook cause SQLite lock contention."*
   - **Counter-evidence:** SQLite runs with WAL mode and `busy_timeout=30.0` (ADR-0008). Ingestion writes are fast, atomic, and retryable.
5. **Challenge 5:** *"Deleting a source deletes the underlying chunks for all notebooks."*
   - **Counter-evidence:** `CompositeStorage.delete_source` only removes the `notebook_id` from the Qdrant point vector's payload and deletes the `sources` association row. Chunks remain intact if referenced by other sources.
6. **Challenge 6:** *"What if Ollama is down during ingestion?"*
   - **Counter-evidence:** `EmbedderModule` raises `DependencyUnavailableError`, mapped to `503 Service Unavailable` with `retryable=True`.
7. **Challenge 7:** *"Can an attacker perform path traversal via uploaded filename?"*
   - **Counter-evidence:** Filename is sanitized using `Path(filename).name`, and assets are stored exclusively by SHA-256 UUID in filesystem blob store.
8. **Challenge 8:** *"What happens if a user uploads a file with no extension or unknown MIME type?"*
   - **Counter-evidence:** `_detect_mime` runs libmagic on buffer; if unrecognized, `ParserRouter` raises `UnsupportedError`, returning `400 Bad Request`.
9. **Challenge 9:** *"Is a background worker process needed?"*
   - **Counter-evidence:** In single-worker desktop Mnemo, async request execution provides instant feedback with synchronous verification for the client.
10. **Challenge 10:** *"Does Module 7.3 require modifying any Phase 0–6 files?"*
    - **Counter-evidence:** Zero files in `mnemo-core/` or `plugins/` require modification.

---

## 11. Phase 10 — New ADR Determination

- **Is a new ADR required?** **YES — ADR-0051**
- **Title:** `ADR-0051: Sources and Document Ingestion REST API Specification`
- **Decisions to freeze in ADR-0051:**
  1. REST Endpoints & DTO schemas for `/v1/notebooks/{id}/sources`.
  2. Multipart file upload limits and filename sanitization.
  3. Deduplication semantics and response structure (`deduplicated: bool`).
  4. Synchronous request-scoped ingestion execution with `asyncio.to_thread` parsing.
  5. Source deletion & Qdrant membership projection cleanup.
  6. Ingestion error translation table.

---

## 12. Phase 11 — Frozen Boundary Verification

```
mnemo-core/                       UNCHANGED (100% frozen)
plugins/                          UNCHANGED (100% frozen)
docs/adr/ADR-0001..ADR-0050       UNCHANGED (100% frozen)
```
Zero frozen-boundary violations detected.

---

## 13. Phase 12 — Implementation Blueprint

### Files to Create:
1. `docs/adr/ADR-0051-sources-and-ingestion-rest-api.md`
2. `mnemo-server/mnemo_server/schemas/sources.py` (`SourceResponse`, `SourceStatusResponse`, `SourceListResponse`)
3. `mnemo-server/mnemo_server/services/ingestion.py` (Ingestion coordination service)
4. `mnemo-server/mnemo_server/routers/sources.py` (FastAPI router for `/v1/notebooks/{id}/sources`)
5. `mnemo-server/tests/test_server_sources.py` (Integration test suite for source endpoints)

### Files to Modify:
1. `mnemo-server/mnemo_server/app.py` (Mount `sources_router` under `/v1`)
2. `mnemo-server/mnemo_server/config.py` (Add `max_upload_bytes: int = 50 * 1024 * 1024` to `ServerConfig`)
3. `mnemo-server/mnemo_server/dependencies.py` (Add `get_token_counter` dependency)
4. `mnemo-server/mnemo_server/schemas/__init__.py` (Export source DTOs)
5. `mnemo-server/mnemo_server/routers/__init__.py` (Export sources router)

---

## 14. Phase 13 — Acceptance Criteria

1. **Functionality:**
   - `POST /v1/notebooks/{id}/sources` successfully ingests PDF, DOCX, Markdown, HTML, TXT, JSON, CSV files and indexes them into SQLite + Qdrant.
   - Ingesting duplicate file to same notebook returns `409 Conflict`.
   - Ingesting existing file to different notebook reuses document and returns `201 Created` with `deduplicated=True`.
   - `GET /v1/notebooks/{id}/sources` returns paginated list of sources.
   - `GET /v1/notebooks/{id}/sources/{sid}` returns source and document details.
   - `DELETE /v1/notebooks/{id}/sources/{sid}` removes source and updates Qdrant memberships.
   - `GET /v1/notebooks/{id}/sources/{sid}/status` returns correct lifecycle status.
2. **Quality Gates:**
   - 100% pytest pass across full test suite.
   - Code coverage `>= 90.00%`.
   - `ruff check` and `ruff format --check` clean.
   - `mypy --strict` clean across all packages.
   - `uv build --package mnemo-server` succeeds.

---

## 15. Final Verdict & Status Declaration

```
MODULE_7_3_STATUS:                  GREEN WITH CONDITIONS
FROZEN_CORE_MODIFICATIONS_REQUIRED: NO
NEW_ADR_REQUIRED:                   YES — ADR-0051
IMPLEMENTATION_READY:               NO — ADR-0051 must be accepted first
BLOCKING_ISSUES:                    0
HIGH_RISKS:                         0
MEDIUM_RISKS:                       1 (Event-loop blocking during large PDF parsing -> resolved via asyncio.to_thread)
LOW_RISKS:                          1 (Upload payload size memory consumption -> resolved via max_upload_bytes limit)
```

### Recommendation
Proceed to the creation and formal acceptance of **ADR-0051: Sources and Document Ingestion REST API Specification**.
