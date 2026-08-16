# Module 7.3 — Sources & Ingestion REST Endpoints: Targeted Contradiction Resolution & Reconciliation

- **Target Module:** Phase 7, Module 7.3 (Sources & Ingestion REST Endpoints)
- **Status:** PASS WITH CORRECTIONS
- **Audit Date:** 2026-08-16
- **Baseline Commit:** `79bef22b91c31ae985468d96c02fb732807488eb` (Module 7.2 closed, `origin/main` synchronized)
- **Preceding Document:** `docs/governance/MODULE_7_3_ARCHITECTURAL_AUDIT.md`

---

## Executive Summary

This targeted reconciliation pass forensically verifies every architectural claim, call signature, concurrency assumption, and error contract made in `MODULE_7_3_ARCHITECTURAL_AUDIT.md` against the actual implementation in `mnemo-core`, `mnemo-server`, and `plugins`.

### Overall Verdict
```
MODULE_7_3_RECONCILIATION:          PASS_WITH_CORRECTIONS
ADR_0051_STILL_REQUIRED:             YES
FROZEN_CORE_MODIFICATIONS_REQUIRED: NO
IMPLEMENTATION_READY:               NO — ADR-0051 must be accepted first
```

---

## 1. Item-by-Item Forensic Investigation

### 1.1 SQLite Busy Timeout
- **Claim:** SQLite database is configured with `PRAGMA busy_timeout = 30.0` in `SQLiteStore`.
- **Audit's Assertion:** Audit stated: *"SQLite runs with WAL mode and `busy_timeout=30.0` (ADR-0008)."*
- **Actual Repository Evidence:**
  - In `mnemo-core/mnemo/storage/sqlite.py` lines 310–313:
    ```python
    self._db = await aiosqlite.connect(self._db_path)
    # Enable WAL mode and foreign keys per connection
    await self._db.execute("PRAGMA foreign_keys = ON;")
    await self._db.execute("PRAGMA journal_mode = WAL;")
    ```
  - Notice `PRAGMA busy_timeout` is **NOT** present in `SQLiteStore.open()`.
  - `PRAGMA busy_timeout = 30000;` was added exclusively to `SQLiteEmbeddingCache` in `mnemo-core/mnemo/storage/cache.py` (line 18).
- **Verdict:** **CORRECTED**
- **Architectural Consequence:** `SQLiteStore` relies on `aiosqlite` default timeout (5.0s) and WAL mode concurrency. Since `SQLiteStore` is frozen in Phase 1, `mnemo-server` must handle `sqlite3.OperationalError: database is locked` via the existing `_interface_error_handler` / `StorageError` translation, returning HTTP 503 (`contract.storage`, `retryable: true`).

---

### 1.2 Content-Hash Deduplication Responsibility
- **Claim:** Content-hash deduplication is handled automatically by `ParserRouter`.
- **Audit's Assertion:** Audit stated: *"Deduplication is already built into `ParserRouter`... Skips parsing, chunking, and embedding entirely."*
- **Actual Repository Evidence:**
  - In `mnemo-core/mnemo/parsers/router.py` lines 95–100:
    ```python
    sha256_hash = hashlib.sha256(data).hexdigest()
    existing_doc = await self.storage.get_document_by_content_hash(sha256_hash)
    if existing_doc is not None:
        return existing_doc
    ```
  - `ParserRouter.route()` returns the existing `Document` if `content_hash` matches.
  - In `mnemo-core/mnemo/ingestion/pipeline.py` lines 40–43:
    ```python
    routed = await self._router.route(data, filename)
    if isinstance(routed, Document):
        return await self._load_deduplicated(routed)
    ```
  - **Crucial Boundary Finding:** `ParserRouter` and `IngestionPipeline` operate at the *document* level. Neither creates the `Source` model or associates it with a `Notebook`.
  - Associating the existing `Document` with the target `Notebook` via `Source(source_id=uuid4(), notebook_id=notebook_id, document_id=existing_doc.document_id)` and calling `await storage.upsert_source(source)` is the explicit responsibility of the Module 7.3 service layer in `mnemo-server`.
- **Verdict:** **CONFIRMED WITH CLARIFICATION**
- **Architectural Consequence:** The Module 7.3 ingestion service will perform a fast hash check or inspect `routed`. On a deduplication hit, it skips chunking and embedding, creates the `Source` junction in SQLite, and triggers `CompositeStorage.upsert_source` (which updates Qdrant point payloads with the new `notebook_id`).

---

### 1.3 Proposed Ingestion Call Chain & Signature Evidence

| Operation / Call | Exists? | Exact Signature in Codebase | Mode | Owner Component |
|---|---|---|---|---|
| `get_notebook` | YES | `async def get_notebook(notebook_id: UUID) -> Notebook \| None` | Async | `StorageInterfaceV1` / `CompositeStorage` / `SQLiteStore` |
| `get_document_by_content_hash` | YES | `async def get_document_by_content_hash(content_hash: str) -> Document \| None` | Async | `StorageInterfaceV1` / `CompositeStorage` / `SQLiteStore` |
| `get_source` | YES | `async def get_source(source_id: UUID) -> Source \| None` | Async | `StorageInterfaceV1` / `CompositeStorage` / `SQLiteStore` |
| `put_asset` | YES | `async def put_asset(data: bytes, mime_type: str, metadata: FrozenMetadata) -> Asset` | Async | `StorageInterfaceV1` / `CompositeStorage` / `FilesystemBlobStore` |
| `put_parsed_document` | YES | `async def put_parsed_document(version_id: UUID, document: ParsedDocument) -> None` | Async | `StorageInterfaceV1` / `CompositeStorage` / `FilesystemBlobStore` |
| `upsert_document` | YES | `async def upsert_document(document: Document) -> None` | Async | `StorageInterfaceV1` / `CompositeStorage` / `SQLiteStore` |
| `upsert_source` | YES | `async def upsert_source(source: Source) -> None` | Async | `StorageInterfaceV1` / `CompositeStorage` / `SQLiteStore` |
| `upsert_chunks` | YES | `async def upsert_chunks(chunks: tuple[Chunk, ...]) -> None` | Async | `StorageInterfaceV1` / `CompositeStorage` (SQLite + Qdrant) |
| `delete_source` | YES | `async def delete_source(source_id: UUID) -> bool` | Async | `StorageInterfaceV1` / `CompositeStorage` / `SQLiteStore` |
| `list_sources` | YES | `async def list_sources(notebook_id: UUID, limit: int, cursor: str \| None) -> Page[Source]` | Async | `StorageInterfaceV1` / `CompositeStorage` / `SQLiteStore` |
| `ParserRouter.route` | YES | `async def route(data: bytes, filename: str) -> Document \| ParseResult` | Async | `mnemo.parsers.ParserRouter` |
| `DocumentCleaner.clean` | YES | `def clean(result: ParseResult) -> ParseResult` | Sync | `mnemo.cleaner.DocumentCleaner` |
| `DocumentClassifier.classify` | YES | `def classify(result: ParseResult, filename: str) -> ParseResult` | Sync | `mnemo.classifier.DocumentClassifier` |
| `DocumentCanonicalizer.canonicalize` | YES | `def canonicalize(result: ParseResult, asset_map: Mapping[str, Asset]) -> ParsedDocument` | Sync | `mnemo.ingestion.DocumentCanonicalizer` |
| `ChunkerDispatcher.dispatch` | YES | `def dispatch(document: ParsedDocument, context: ChunkingContext) -> tuple[Chunk, ...]` | Sync | `mnemo.chunkers.ChunkerDispatcher` |
| `EmbedderModule.embed_chunks` | YES | `async def embed_chunks(chunks: Sequence[Chunk]) -> tuple[Chunk, ...]` | Async | `mnemo.embeddings.EmbedderModule` |

- **Verdict:** **CONFIRMED**
- **Architectural Consequence:** Every required method exists in frozen core with exact matching signatures.

---

### 1.4 DocumentStatus Model & Persisted Transitions
- **Claim:** `DocumentStatus` represents real persisted database states in SQLite.
- **Audit's Assertion:** Audit stated: *"document.status gives the exact ingestion state (`pending`, `indexing`, `indexed`, `failed`)"*.
- **Actual Repository Evidence:**
  - In `mnemo-core/mnemo/models/documents.py` lines 39–46:
    ```python
    class DocumentStatus(StrEnum):
        PENDING = "pending"
        INDEXING = "indexing"
        INDEXED = "indexed"
        ENRICHED = "enriched"
        FAILED = "failed"
    ```
  - In SQLite `documents` table: `status TEXT NOT NULL`.
  - `Document` model enforces `require_enum(status, DocumentStatus, "status")`.
  - Ingestion starts with `DocumentStatus.INDEXING` and updates to `DocumentStatus.INDEXED` once `upsert_chunks` completes.
- **Verdict:** **CONFIRMED**
- **Architectural Consequence:** The status values are first-class persisted domain values, not synthetic REST-layer mockups.

---

### 1.5 Ingestion Failure Atomicity Across Stores
- **Claim:** Storage writes have rollback compensation on failure.
- **Audit's Assertion:** Audit analyzed failure atomicity across stages.
- **Actual Repository Evidence:**
  - In `CompositeStorage.upsert_chunks` (lines 397–417):
    - `_Compensator` creates a snapshot of SQLite chunks and Qdrant projected points.
    - If writing to Qdrant fails, `_Compensator.rollback()` restores the SQLite chunk snapshot and projection.
  - In `CompositeStorage.upsert_source` (lines 223–232):
    - If updating Qdrant memberships fails, `_restore_source` rolls back the SQLite write.
  - **Early Failures (Before `upsert_chunks`):**
    - If parsing or embedding fails before `upsert_chunks`:
      - Blobs written via `put_asset` / `put_parsed_document` remain in filesystem storage (content-addressed, harmless).
      - No records exist in `chunks` or `sources`.
      - If `Document(status=INDEXING)` was written, it can be transitioned to `Document(status=FAILED)` or rolled back via `delete_document`.
- **Verdict:** **CONFIRMED**
- **Architectural Consequence:** Multi-store writes (`upsert_chunks`, `upsert_source`) have robust snapshot-and-rollback compensation in `CompositeStorage`.

---

### 1.6 Source Deletion & Membership Projections
- **Claim:** `delete_source` deletes the junction row and refreshes Qdrant memberships without destroying underlying document chunks.
- **Audit's Assertion:** Audit asserted: *"CompositeStorage only removes the `notebook_id` from the Qdrant point vector's payload and deletes the `sources` association row."*
- **Actual Repository Evidence:**
  - In `mnemo-core/mnemo/storage/composite.py` lines 237–254:
    ```python
    async def delete_source(self, source_id: UUID) -> bool:
        async with self._projection_lock:
            previous = await self._sql.get_source(source_id)
            if previous is None:
                return False
            deleted = await self._sql.delete_source(source_id)
            await self._refresh_memberships((previous.document_id,))
            return deleted
    ```
  - In `CompositeStorage._refresh_memberships`:
    - Reads all remaining `sources` for `document_id`.
    - If another notebook still references the document, its `notebook_id` remains in the Qdrant vector payload.
    - If zero notebooks reference the document, `notebook_ids` becomes `()` in Qdrant (chunks remain stored in SQLite & Qdrant, but are excluded from notebook-scoped vector searches).
- **Verdict:** **CONFIRMED**
- **Architectural Consequence:** Multi-notebook source sharing works correctly out-of-the-box without modifying frozen core.

---

### 1.7 HTTP 413 Payload Too Large Contract
- **Claim:** 413 error contract can be handled cleanly under ADR-0049.
- **Audit's Assertion:** Audit noted 413 as part of the error mapping.
- **Actual Repository Evidence:**
  - ADR-0049 specifies the error envelope:
    ```json
    {
      "error": {
        "code": "<string>",
        "message": "<string>",
        "details": {},
        "retryable": false
      }
    }
    ```
  - In `mnemo-server/mnemo_server/errors.py` lines 132–144:
    ```python
    def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = str(exc.detail) if exc.detail else "HTTP request failed"
        retryable = exc.status_code in (502, 503, 504)
        code = f"http.{exc.status_code}"
        return error_response(
            exc.status_code,
            code,
            message,
            details={},
            retryable=retryable,
            headers=exc.headers,
        )
    ```
  - Raising `HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="...")` produces status `413` with code `"http.413"` and `retryable: false`.
  - No core exception changes or modifications to ADR-0049 are needed.
- **Verdict:** **CONFIRMED**
- **Architectural Consequence:** 413 is a pure transport-layer HTTP exception handled by the standard Starlette exception handler in `errors.py`.

---

### 1.8 Upload Memory & Concurrency Analysis
- **Claim:** Streaming upload validation protects against memory exhaustion.
- **Audit's Assertion:** Audit noted 50 MB default max upload bytes.
- **Actual Repository Evidence:**
  - Starlette's `UploadFile` spools files > 1 MB to disk.
  - If a route handler unconditionally executes `await file.read()`, it buffers the entire byte payload into memory.
  - With a 50 MB limit:
    - 1 concurrent request: ~50 MB RAM.
    - 5 concurrent requests: ~250 MB RAM.
    - 10 concurrent requests: ~500 MB RAM.
  - **Mitigation:** The ingestion service must enforce a bounded chunk-streaming reader:
    ```python
    chunk_size = 1024 * 1024  # 1MB chunks
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(chunk_size):
        total += len(chunk)
        if total > max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Upload exceeds maximum permitted size of {max_upload_bytes} bytes",
            )
        chunks.append(chunk)
    payload = b"".join(chunks)
    ```
  - This immediately terminates uploads exceeding 50 MB without allocating unbounded memory.
- **Verdict:** **CONFIRMED WITH CONCRETE IMPLEMENTATION DIRECTIVE**
- **Architectural Consequence:** ADR-0051 will codify the bounded chunked streaming upload check.

---

### 1.9 Thread Offloading Analysis
- **Claim:** Synchronous CPU-bound parsing must be offloaded to `asyncio.to_thread`.
- **Audit's Assertion:** Audit recommended wrapping parsing in `asyncio.to_thread`.
- **Actual Repository Evidence:**
  - `PDFParser.parse()` calls PyMuPDF (`fitz.open`), which runs C-level PDF parsing synchronously.
  - `DOCXParser.parse()` unpacks XML documents synchronously via `python-docx`.
  - `HTMLParser.parse()` parses DOM synchronously via BeautifulSoup.
  - `MarkdownParser.parse()` tokenizes markdown synchronously.
  - In `mnemo-core/mnemo/parsers/router.py` line 125:
    `return parser.parse(data, filename, metadata)`
  - Since `ParserRouter.route()` is called during ingestion, running `await asyncio.to_thread(pipeline.ingest, ...)` ensures that neither file I/O nor C-level parsing blocks the FastAPI asyncio event loop.
- **Verdict:** **CONFIRMED**
- **Architectural Consequence:** The server-side ingestion service will execute synchronous CPU-intensive parsing via `asyncio.to_thread`.

---

## 2. Summary of Corrections to Audit

1. **Correction 1 (SQLite busy_timeout):** `SQLiteStore.open()` does NOT execute `PRAGMA busy_timeout = 30000;` (that was added only to `SQLiteEmbeddingCache`). Server-side error handlers must be prepared for SQLite busy timeouts under high write contention.
2. **Correction 2 (Deduplication Layering):** `ParserRouter` deduplicates at the `Document` level, but `mnemo-server` owns the `Source` association and duplicate prevention (`409 Conflict`) at the `Notebook` level.
3. **Correction 3 (Streaming Upload Bounds):** Server upload handling must stream in chunks to enforce `max_upload_bytes` before loading the entire buffer.

---

## 3. Final Determination

```
MODULE_7_3_RECONCILIATION:          PASS_WITH_CORRECTIONS
ADR_0051_STILL_REQUIRED:             YES
FROZEN_CORE_MODIFICATIONS_REQUIRED: NO
IMPLEMENTATION_READY:               NO — ADR-0051 must be accepted first
```
