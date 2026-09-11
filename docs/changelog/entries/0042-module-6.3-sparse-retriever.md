# Changelog 0042: Module 6.3 SparseRetriever

## Status

Module 6.3 is implemented and locally validated. This is unreleased Phase 6
work; version 0.20.1 and all existing tags remain unchanged.

## Changes

- Added the thin, storage-agnostic `SparseRetriever`.
- Added SQLite schema migration 4 for exact-version derived retrieval metadata.
- Replaced the stale nonexistent `documents.type` filter with the ADR-0039
  `(document_id, version_id)` projection.
- Enforced notebook/source/type/date filters in SQL before BM25 ordering and
  `top_k`, including same-Source-row notebook/source intersection.
- Replaced the historic `abs(bm25)` mapping with unnormalized `-bm25()` so the
  adapter satisfies ADR-0002's descending-score convention.
- Preserved FTS trigger synchronization and added projection compensation for
  failed multi-store writes.

The original Module 2.2 changelog remains historical evidence of that release;
this entry records the Phase 6 correction. Modules 6.4 and 6.5 are not started,
and milestone M6 is not verified.
