# Phase 8.5.6 Gate Evidence — Advanced Retrieval and Completeness

**Gate:** PASS  
**Date:** 2026-08-25  
**Governing decision:** ADR-0058  
**Schema:** unchanged at v10; no migration required

## Implementation

Phase 8.5.6 adds an independent core V2 retrieval contract without widening
`StorageInterfaceV1` or changing V1 query behavior:

- immutable `RetrievalPlanV2`, `RetrievalResultSetV1`, typed candidates,
  representation reports, positional/identity scopes, and stage budgets;
- distinct `RANKED` and deterministic cursor-paged `EXHAUSTIVE` execution;
- `COMPLETE`, `PARTIAL`, `TRUNCATED`, `UNKNOWN`, and `EMPTY` semantics exactly
  matching ADR-0058;
- provider-neutral representation sources, explicit unavailable/failed paths,
  provenance-preserving RRF, authoritative-identity deduplication, bounded
  parent/adjacent expansion, optional provenance-preserving reranking, and
  safe output byte/content/result bounds;
- an additive canonical-text adapter over V1 sparse retrieval plus SQLite
  deterministic enumeration using existing canonical chunks, FTS, and title
  projections;
- opaque HMAC-SHA256 cursors bound to plan fingerprint, notebook, per-source
  snapshots, offsets, and expiry. Snapshot mutation, tampering, request reuse,
  and expiry fail closed.

Representation identity is retained through recall, expansion, fusion,
reranking, bounds, and final projection: notebook/source/document/version,
chunk or occurrence/derivation, locator, document title, raw retrieval paths,
title evidence, parent promotion, fused score, and final rank.

## Completeness and bounds proof

- Ranked retrieval never upgrades bounded evidence to `COMPLETE`.
- Exhaustive retrieval emits `COMPLETE` only at stable terminal traversal.
- Result, recall, expansion, fusion, rerank, serialized-byte, and content-size
  limits are typed and validated.
- Forced result/byte truncation returns a continuation cursor and never repeats
  the previously consumed candidate.
- Missing/disabled representations report `PARTIAL`; source failures report
  `FAILED` at representation level and overall `UNKNOWN`, never `EMPTY`.
- Canonical positional tests cover page scopes; synthetic locators cover PDF,
  PPTX, DOCX, XLSX, code, OCR, and vision positions without fabricated data.

## Security and failure evidence

Tests cover notebook/source/document/version isolation, cross-notebook
candidate rejection, cursor tampering/expiry/plan mismatch, snapshot mutation,
candidate and expansion explosion, malformed source pages, invalid snapshots,
reranker identity/provenance mutation, query and model bounds, and distinct
OCR/vision/visual evidence sharing similar text. Cursors grant no authority;
each page re-applies the authorized scope. Diagnostics contain counts, status,
reason codes, and timing but no query or evidence content.

One defect was found by the negative identity tests: a provenance-less derived
candidate could previously hash the string `None`. `advanced_candidate_id`
now rejects candidates lacking chunk, occurrence, or derivation identity.

## Tests and quality evidence

Executed from the repository root:

```text
uv run pytest mnemo-core/tests/unit/test_advanced_retrieval.py -q --no-cov
36 passed

uv run pytest -q
1563 passed, 1 skipped
coverage: 90.13% (required: 90%)
```

The focused suite covers ranked/exhaustive state, cursor termination,
concurrent-snapshot mutation, title retention, positional lookup, bounded
expansion, identity-aware deduplication, representation unavailability,
authorization, malformed adapters, and contract validation. Existing retrieval
regression suites (sparse, dense, fusion, parent promotion, projection,
reranker, and diversity) also pass in the full run.

Final static/build commands:

```text
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict mnemo-core/mnemo mnemo-server/mnemo_server plugins/email-ingestion/email_ingestion
uv build --package mnemo-core
uv build --package mnemo-server
uv build --package mnemo-email-ingestion
git diff --check
```

All passed. Focused execution completed in 4.33 seconds; the full suite
completed in 172.94 seconds. No production latency SLO is frozen by this gate.

## Phase 0–8 and Golden Corpus compatibility

The certified database was opened read-only. It remains:

```text
documents=15, document_versions=15, sources=15
chunks=1514, fts_chunks=1514, fts_chunk_titles=1514
orphan_chunks=0, orphan_fts=0, duplicate_chunk_ids=0
sha256(concatenated ordered chunk id + text)=1997852deb381869d1ff72f511fa22b97bdea5287e5f6632ef1292405bbf4e66
```

Phase 8.5.6 did not write, purge, re-ingest, or rebuild the corpus. Canonical
chunks/text, embeddings, V1 FTS/title retrieval, RRF/reranking, Final QA,
HTTP, six MCP tools, and Qdrant optionality are unchanged.

## Limitations and rollback

This gate does not implement structured aggregation (8.5.7), multimodal
context/citations/Final QA V2 (8.5.8), multilingual retrieval (8.5.9), or new
HTTP/MCP delivery. OCR, vision, and visual-vector sources plug into the typed
orchestrator, but deployment-specific query adapters/fusion belong to the
later multimodal workstream. Disable V2 service composition and expire its
cursors to roll back; V1 remains operational and no data migration is needed.

## Verdict

`PHASE 8.5.6 GATE: PASS`
