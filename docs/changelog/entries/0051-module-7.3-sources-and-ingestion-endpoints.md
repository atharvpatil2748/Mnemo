# Module 7.3 Sources & Document Ingestion REST Endpoints

- Implemented transport-layer Pydantic V2 DTOs (`SourceResponse`, `SourceStatusResponse`, `PageResponse[SourceResponse]`) isolating HTTP concerns from frozen domain models.
- Implemented `IngestionService` coordinating frozen pipeline components:
  - `ServerParserRouter` with `PluginRegistry` providing format-specific extension precedence over generic `text/plain` libmagic MIME detection (Markdown, PlainText, CSV, PDF, DOCX, HTML, JSON).
  - `DocumentCleaner` for Unicode normalization and language detection.
  - `DocumentClassifier` for deterministic file-extension and heuristic document categorization.
  - `DocumentCanonicalizer` and `IngestionPipeline` for block normalization and asset extraction.
  - `ChunkerDispatcher` for token-aware chunk generation.
  - `EmbedderModule` with anyio task groups and concurrency limiting for vector embeddings.
  - SQLite metadata/source persistence and Qdrant vector storage.
- Implemented cross-notebook and intra-notebook deduplication semantics via SHA-256 content hashes:
  - **Case A (Fresh Ingestion):** Parses, canonicalizes, chunks, embeds, persists to storage, links new `Source` to notebook.
  - **Case B (Cross-Notebook Ingestion):** Reuses existing `Document`, `DocumentVersion`, and embeddings; creates and links a new `Source` with `deduplicated=True`.
  - **Case C (Intra-Notebook Re-upload):** Detects existing source association in target notebook and raises `409 Conflict` (`contract.conflict`).
- Implemented 5 source REST endpoints under `/v1/notebooks/{id}/sources`:
  - `POST /v1/notebooks/{id}/sources`: Multipart file upload with 50MB file size limit (`413 Content Too Large`), empty file check (`422 Unprocessable Content`), and unsupported extension check (`400 Bad Request`).
  - `GET /v1/notebooks/{id}/sources`: Keyset pagination (`1 <= limit <= 100`, default 50).
  - `GET /v1/notebooks/{id}/sources/{source_id}`: Source retrieval with cross-notebook ownership validation (`404 Not Found`).
  - `DELETE /v1/notebooks/{id}/sources/{source_id}`: Source disassociation (`204 No Content`) with cross-notebook ownership validation.
  - `GET /v1/notebooks/{id}/sources/{source_id}/status`: Ingestion status polling returning `processing`, `indexed`, `failed`, or `active`.
- Implemented transactional rollback and failure tracking:
  - Failed pipeline runs clean up transient stored assets and transition document status to `FAILED` with retryable `503 Service Unavailable` on embedding/storage outages.
- Implemented configurable upload limits via `MNEMO_MAX_UPLOAD_BYTES` (default 50MB).
- Added `python-multipart` dependency for FastAPI multipart file upload support.
- Added comprehensive unit and integration test suite (`test_server_sources.py`) covering all endpoints, deduplication cases, error mapping, pagination, cross-platform libmagic handling, and failure modes.

Module 7.3 is complete and verified. Frozen phases 0–6 and ADRs 0001–0051 remain untouched.
