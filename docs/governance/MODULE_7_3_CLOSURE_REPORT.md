# Module 7.3 — Closure and Implementation Verification Report

- **Module:** Phase 7, Module 7.3 (Sources & Document Ingestion REST Endpoints)
- **Status:** COMPLETE (Re-verified & Corrected post-CI)
- **Authoritative Contract:** [ADR-0051: Sources & Document Ingestion REST API Specification](../adr/ADR-0051-sources-and-document-ingestion-rest-api.md)
- **Baseline Commit:** `e6c1ddf2c253818e388d07e5d80ba4c95a2982d6` (Module 7.2 closed)
- **Date:** 2026-08-16

---

## 1. Implementation Summary

Module 7.3 implements synchronous document ingestion, source association, deduplication, listing, single-source retrieval, deletion, and status polling REST endpoints in `mnemo-server`.

All endpoints were implemented strictly within `mnemo-server` using FastAPI, `python-multipart`, and Pydantic V2 DTOs, adhering 100% to [ADR-0051](../adr/ADR-0051-sources-and-document-ingestion-rest-api.md). The `IngestionService` orchestrates the frozen ingestion pipeline (`ServerParserRouter`, `DocumentCleaner`, `DocumentClassifier`, `DocumentCanonicalizer`, `IngestionPipeline`, `ChunkerDispatcher`, `EmbedderModule`, and `StorageInterfaceV1`) with exact content-hash deduplication and rollback semantics. Zero modifications were made to frozen core packages, models, interfaces, or storage engines.

---

## 2. Endpoint Inventory

| # | Method | Path | Request DTO | Response DTO | Success Code | Status |
|---|---|---|---|---|---|---|
| 1 | `POST` | `/v1/notebooks/{notebook_id}/sources` | Multipart `file: UploadFile` | `SourceResponse` | `201 Created` | **VERIFIED** |
| 2 | `GET` | `/v1/notebooks/{notebook_id}/sources` | — | `PageResponse[SourceResponse]` | `200 OK` | **VERIFIED** |
| 3 | `GET` | `/v1/notebooks/{notebook_id}/sources/{source_id}` | — | `SourceResponse` | `200 OK` | **VERIFIED** |
| 4 | `DELETE` | `/v1/notebooks/{notebook_id}/sources/{source_id}` | — | `None` | `204 No Content` | **VERIFIED** |
| 5 | `GET` | `/v1/notebooks/{notebook_id}/sources/{source_id}/status` | — | `SourceStatusResponse` | `200 OK` | **VERIFIED** |

---

## 3. ADR-0051 Contract Alignment

- **Decision 1 (DTO Boundary):** `SourceResponse` and `SourceStatusResponse` encapsulate all transport responses. Domain dataclasses are never exposed directly over HTTP.
- **Decision 2 (Ingestion Orchestration):** Full pipeline coordination inside `IngestionService` utilizing `ServerParserRouter`, `DocumentCleaner`, `DocumentClassifier`, `DocumentCanonicalizer`, `ChunkerDispatcher`, `EmbedderModule`, and storage persistence.
- **Decision 3 (Content-Hash Deduplication):**
  - *Case A (New content):* Complete parsing, chunking, embedding, storage, and Source link.
  - *Case B (Cross-notebook duplicate):* Reuses existing `Document` and embeddings; creates and links new `Source` with `deduplicated=True`.
  - *Case C (Intra-notebook duplicate):* Returns `409 Conflict` (`contract.conflict`).
- **Decision 4 (Upload Limits & Safety):** Enforces 50MB file size limit (`413 Content Too Large`), empty file check (`422 Unprocessable Content`), and file extension parser check (`400 Bad Request`).
- **Decision 5 (Async / Threading Model):** Asynchronous endpoint handlers delegating to async engine APIs; anyio task groups with concurrency limiter for vector batch embeddings.
- **Decision 6 (Document Lifecycle States):** Correct transitions across `STAGED`, `INDEXED`, `ACTIVE`, and `FAILED` states.
- **Decision 7 (Transactional Rollback & Failure Semantics):** On failure during ingestion, cleanup of transient assets, transition of `Document` to `FAILED` status, and mapping of dependency outages to retryable `503 Service Unavailable`.
- **Decision 8 (Pagination):** Keyset seeking via transparent UUID string cursors with `1 <= limit <= 100` (default 50).
- **Decision 9 (Error Mapping):** Standardized error envelope (`contract.not_found`, `contract.conflict`, `contract.dependency_unavailable`, `contract.storage`, `http.validation`) with sanitized detail payloads.
- **Decision 10 (Frozen Core Integrity):** Zero edits to `mnemo-core`, `plugins`, or ADRs 0001–0050.

---

## 4. Post-Closure CI Forensic Investigation & Incident Resolution

### Incident Summary
During initial CI execution on Linux runners (Python 3.12.13), 3 Markdown ingestion tests failed with `400 Bad Request` instead of `201 Created` / `503 Service Unavailable`:
- `test_ingest_markdown_source_success`
- `test_ingest_embedding_failure_returns_503_and_sets_failed_status`
- `test_ingest_storage_failure_returns_503`

### Root Cause
On Linux systems where native `libmagic` is present, `ParserRouter._detect_mime(data, filename)` identifies plain-text Markdown (`.md`) bytes as `"text/plain"`. In the frozen `ParserRouter` implementation, `resolve_parser(mime_type)` was evaluated prior to checking file extensions. Because `PlainTextParser` is registered for `"text/plain"`, `ParserRouter` dispatched `.md` files to `PlainTextParser`. `PlainTextParser` produced generic text blocks lacking `parser.markdown.*` metadata. Subsequent classification marked the document as `DocType.MARKDOWN`, causing `MarkdownChunker` to fail with `UnsupportedError("canonical Markdown block is missing parser.markdown.kind")`, which mapped to HTTP 400.

On Windows development machines without `libmagic`, `_magic_from_buffer` returned `None` and fell back to extension mapping (`"text/markdown"`), masking the issue locally.

### Resolution
Implemented `ServerParserRouter(ParserRouter)` within `mnemo-server/mnemo_server/services/ingestion.py`. `ServerParserRouter` applies format-specific extension precedence over generic text MIME types (`"text/plain"`), ensuring structured text formats (`.md`, `.csv`, `.json`, `.html`) resolve to their dedicated parsers regardless of underlying `libmagic` detection. Added cross-platform unit tests in `test_server_sources.py` that explicitly simulate `_magic_from_buffer` returning `"text/plain"`.

---

## 5. Quality Gates & Verification

```
Test Suite:          1,213 passed, 1 skipped (0 failures)
Workspace Coverage:  90.20% (Gate: >= 90.00%)
Ruff Formatting:     Clean (205 files checked)
Ruff Linting:        Clean (All checks passed)
Mypy Strict:         Clean (Success: 0 issues in 113 source files)
Package Build:       Clean (mnemo_server-0.21.2 wheel + tar.gz built)
```

---

## 6. Frozen Boundary Audit

```
mnemo-core/                       UNCHANGED (0 modified files)
plugins/                          UNCHANGED (0 modified files)
docs/adr/ADR-0001..ADR-0051       UNCHANGED (0 modified files)
```
