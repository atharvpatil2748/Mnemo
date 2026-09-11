# Phase 8.5 WP-07 Gate Evidence

**Status:** COMPLETE  
**Date:** 2026-08-27  
**Scope:** Production exposure of ranked and bounded exhaustive canonical evidence retrieval

## Implemented contract

WP-07 operationalizes ADR-0058 without modifying frozen V1 retrieval. The
`KnowledgeEngine` composition root now builds one `AdvancedRetrievalService`
from the authorized advanced canonical store, frozen V1 sparse retriever, a
provenance-preserving V1 reranker adapter, and the WP-04 `CursorCodecV2`-backed
`RetrievalCursorCodec`. `Phase85RuntimeV1` marks `exhaustive_retrieval` active
and exposed only when that complete composition is present.

The shared `EvidenceRetrievalApplicationService` accepts a strict public DTO
containing query, explicit ranked/exhaustive mode, notebook/source/document/
version scope, requested representations, optional positional scope, bounded
expansion/deduplication policy, cursor, and candidate/evidence/byte/character
budgets. Server policy applies hard candidate, evidence, response, content, and
elapsed-time ceilings.

## Retrieval and completeness semantics

| Mode | Match/order semantics | Completeness |
|---|---|---|
| `ranked` | Frozen V1 sparse discovery, title-aware provenance, optional bounded expansion, RRF, V1 reranking, deterministic ties | `unknown`/`partial`/`empty`; never upgraded to exhaustive and never emits a cursor |
| `exhaustive` | Authorized canonical SQLite FTS term-disjunction enumeration in deterministic chunk-ID order | `complete` only at stable terminal exhaustion; `truncated` carries `next_cursor`; unavailable requested representations yield terminal `partial` |

Every item retains notebook, source, document, version, chunk/occurrence/
derivation identity where applicable, locator, document title, exact retrieval
paths, title/parent-promotion flags, scores, and final rank. Coverage reports
each requested representation as searched, unavailable, omitted, or failed.
Backend failure and unavailable projection are never converted to no-match or
complete.

The currently production-composed source is `canonical_text`. OCR, Vision,
visual-vector, positional-derived, and title-only representation activation is
truthfully unavailable until the owning later work packages compose them.

## Cursor, bounds, and security

Exhaustive continuation uses the shared versioned, HMAC-protected,
key-rotatable, expiring `CursorCodecV2` path. It binds the plan fingerprint,
notebook scope, requested representations, positional constraints, budgets,
representation offset, and source snapshots. Changed query/scope/version/
representation/bounds, tampering, expiry, unavailable signing key, or snapshot
mutation fails closed. Each continued enumeration re-applies notebook/source/
document/version filters before evidence is returned.

The implementation enforces recall (1–1000), expansion (0–500), fusion (1–500),
rerank/result (1–200), serialized-byte, content-character, and application
deadline ceilings. It logs no query text or evidence content.

## HTTP and MCP

- HTTP: additive `POST /v2/retrieval/evidence` with strict Pydantic input and
  typed response schema.
- MCP: additive `search_evidence`, increasing the advertised ready surface from
  ten to eleven tools. Its machine-facing description distinguishes ranked from
  exhaustive retrieval, lexical enumeration from exact traversal/structured
  arithmetic/semantic image discovery, and instructs clients to pass an
  exhaustive cursor unchanged until null.
- Both adapters invoke the same application service and return the same
  provenance, coverage, completeness, limits, omissions, diagnostics, and next
  action semantics. JSON text remains the compatibility representation and MCP
  `structuredContent` is derived from it.

## Validation

Focused tests cover ranked bounded behavior, exhaustive terminal traversal,
cursor continuation and request/scope binding, unavailable representations,
source failure, snapshot change, tamper/expiry, byte and candidate explosion
bounds, authorization filtering, exact title provenance, parent/reranker
provenance, deterministic multi-document enumeration, timeout, strict DTO and
OpenAPI schemas, MCP schema/description/structured JSON, and the retained V1/MCP
surface.

Final command results and exact counts are recorded in the completion report.

- Focused advanced core plus WP-07 transport suite: **47 passed** (38 core,
  9 server).
- Affected retrieval/runtime/HTTP/MCP/config/governance regression matrix:
  **193 passed**.
- Final directly affected transport/governance matrix after scope hardening:
  **31 passed**.
- Ruff format and check: passed for all 22 affected Python files.
- Targeted strict mypy: passed for all 12 affected production modules.
- Both governance JSON contracts parsed successfully; the WP-00 governance
  contract suite was included in the 193-pass matrix.
- `git diff --check`: passed.

Pytest emitted only pre-existing/non-test Windows cache-cleanup and Starlette
deprecation warnings; no validation failed.

## Compatibility and boundaries

No database migration, source/corpus read or mutation, projection generation,
model/provider call, ingestion, benchmark, or external-agent evaluation was
performed. V1 retrieval, V1 citations, Final-QA V1, `Chunk.text`, canonical
identities, existing ten MCP tool semantics, existing HTTP routes, SQLite/FTS
semantics, and Qdrant optionality remain unchanged.

WP-08 owns structured numeric/filter/aggregate retrieval. WP-09 owns OCR,
Vision, visual-vector, and semantic image sources. WP-10 owns multilingual
activation. WP-11 owns deterministic multi-document comparison primitives.
WP-12 owns Final-QA V2 orchestration, WP-13 capability discovery, WP-14 final
security centralization/certification, WP-16 blind-agent behavioral validation,
and WP-17 final Phase 8.5 certification. No Phase 11 planning or replanning was
introduced.

No new ADR was required; ADR-0058 and ADR-0073 already govern this work. No
contradiction with WP-00 through WP-06 was found.

## Gate

The WP-07 implementation criteria are satisfied by the focused validation
above. This evidence does not certify Phase 8.5.

**WP-07 COMPLETE**
