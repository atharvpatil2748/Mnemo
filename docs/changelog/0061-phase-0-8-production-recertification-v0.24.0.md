# 0061 — Phase 0–8 Production Re-certification (v0.24.0)

- **Date:** 2026-08-20
- **Version:** v0.24.0
- **Scope:** Golden Corpus ingestion integrity, title-aware retrieval, persisted
  Final QA, immutable replay, and live transport re-certification.

## Added

- Transactional SQLite schema v6 title projections for generic exact-version
  sparse title retrieval (ADR-0053).
- Strict provider-neutral citation compliance with one bounded corrective
  regeneration (ADRs 0052 and 0054).
- `POST /v1/notebooks/{notebook_id}/final-qa`, a thin persisted Final-QA
  transport adapter distinct from transient `/v1/query` (ADR-0055).
- Immutable Final-QA execution snapshots, canonical request fingerprints,
  conditional lifecycle transitions, crash-safe resume, and zero-generation
  idempotent replay (ADR-0056).
- Title-aware cross-encoder pair construction and deterministic title-evidence
  ordering without changing canonical chunk text (ADR-0057).

## Fixed

- Source-code parser routing and oversized code declaration preservation.
- Oversized table partitioning and short slide preservation.
- Parent-promotion retrieval-provenance loss and final title attribution.
- Ollama reasoning-only empty content by sending `think: false`.
- ASGI configuration loading from repository `mnemo.toml`.
- MCP SSE double-response ownership in Starlette.
- Corpus-specific reranker and prompt-router signatures; routing and ranking
  are now generic across document types.

## Validation

- Seven-document corpus: 7 documents, 7 versions, 1,512 chunks, 1,512 FTS
  rows, and 1,512 title rows with zero structural orphans/duplicates.
- Python: 1,397 passed, 1 skipped, 90.14% coverage before version bump.
- Ruff, strict mypy, all three packages, frontend, Docker images/Compose, MCP
  stdio/SSE, HTTP streaming, retrieval, persisted Final-QA, citation
  resolution, replay, conflict, crash, and concurrency gates passed locally.
- Qdrant remains intentionally disabled in the certified local profile; no
  local vector-backed hybrid claim is made.

The authoritative evidence is `docs/audit_report_phase0-8-final.md`. GitHub
Actions and release pointers are recorded there after the release commit.
