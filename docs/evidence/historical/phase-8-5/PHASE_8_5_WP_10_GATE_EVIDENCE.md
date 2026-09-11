# Phase 8.5 WP-10 Gate Evidence

## Status

**WP-10 Stage 1: BUILDABLE (2026-08-29); activation remains blocked by
post-implementation governed evaluation.**

The implementation is additive and generation-gated. Concrete, offline-only
frozen-profile BGE-M3 and BGE reranker adapters, a conservative EN/HI/MR
detector, typed source references, and bounded SQLite dense retrieval are now
available for controlled construction. This does **not** mean the capability is
READY, ACTIVE, EXPOSED, VERIFIED, or CERTIFIED: no complete multilingual
generation has been activated and Decision 7 numeric quality floors remain open.

## Implemented

- Added `multilingual_text` as an explicit advanced-evidence representation.
- Added authorized language projection generation discovery and retrieval over
  schema-v14 `language_text_fts`.
- Preserved source/document/version, derivation, source-evidence, source and
  target language provenance in advanced candidates.
- Reused `AdvancedRetrievalService`, rank fusion, completeness, snapshots,
  authorization, and `CursorCodecV2` continuation semantics.
- Composed the multilingual source through `KnowledgeEngine` only when an
  active complete generation is available.
- Updated MCP/capability governance to describe truthful multilingual coverage.
- Added `LanguageEvidenceReferenceV2`, which distinguishes canonical chunk,
  OCR region, Vision derivation, and language-derivation sources without fake
  occurrence identifiers.
- Added offline-only exact-revision BGE-M3 (1024-dimensional L2-normalized)
  query/document batch embedding and BGE reranking adapters. Both fail closed
  on profile, revision, dimension, or local-artifact mismatch.
- Added the governed `unicode-en-hi-mr-conservative-v1` detector. It never
  infers Hindi or Marathi from Devanagari alone and returns `und` on ambiguity.
- Added authorization-before-enumeration bounded SQLite cosine retrieval,
  deterministic RRF/rerank limiting, and a typed advanced-retrieval adapter.
- Added deterministic, restart-safe language-observation/derivation and
  multilingual embedding generation builders. They operate only against an
  explicitly supplied isolated target and cannot activate a partial generation.

## Validation

- Focused multilingual-source and Unicode provenance tests: 1 passed.
- Combined WP-09 multimodal-source regression: 3 passed.
- Existing advanced retrieval/runtime/MCP/HTTP focused regressions remain
  green from the affected validation run (66 passed).
- Ruff: passed on modified modules.
- Strict mypy: passed on modified core modules.
- Governance JSON validation: passed.
- `git diff --check`: passed.

Stage-1 focused validation (2026-08-29):

- Multilingual Stage-1, existing multilingual, runtime, projection, and engine
  tests: **68 passed**.
- Affected HTTP/MCP retrieval and capability tests: **27 passed**.
- Strict mypy on the eight affected production modules: passed.
- The exact D:-rooted frozen BGE-M3 and reranker snapshots were resolved and
  minimally initialized offline; no download, model pull, benchmark, corpus
  ingestion, or protected database write occurred.

No corpus, frozen multimodal database/manifest, Golden Dataset, model artifact,
migration, ingestion, benchmark, or V1 contract was modified. No multilingual
model or capability was certified; directional behavioral benchmarking remains
evaluation/certification scope.

## Deferred

Provider readiness in an operator-composed runtime, isolated language and
vector generation builds, activation, broad EN/HI/MR directional evaluation,
numeric Decision 7 quality floors, multilingual OCR/Vision live activation,
blind-agent verification, and certification remain deferred. Those later
evidence gates must not be inferred from Stage-1 source code or unit tests.
