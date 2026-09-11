# ADR-0058: Advanced Retrieval Completeness and Result Sets

- **Status:** Accepted
- **Implementation:** Core complete (Phase 8.5.6); production canonical composition and HTTP/MCP exposure complete (WP-07, 2026-08-27)
- **Date:** 2026-08-24
- **Extends:** ADR-0038 through ADR-0043, ADR-0053, ADR-0057
- **Supersedes:** Nothing

## Context

Phase 0–8 retrieval is deliberately bounded and ranked. A large `top_k` is not
proof that every matching record was examined. Phase 8.5 needs exact,
positional, structured, and exhaustive retrieval without changing the frozen
ranked path or its provenance.

## Problem

Counts, “all rows,” page/slide ranges, and deterministic exports need a stable
result universe, continuation, and an honest completeness statement. Existing
`ScoredChunk` and ranked fusion contracts cannot express those guarantees.

## Decision

Add `RetrievalPlanV2`, `RetrievalResultSetV1`, and opaque signed cursor
contracts. Plans select one or more typed operations: ranked, exact,
positional, structured, exhaustive, cross-document, or multimodal. Every
result set records a query fingerprint, stable snapshot identity, ordering
policy, examined and returned counts, limits, and one of `COMPLETE`, `PARTIAL`,
`TRUNCATED`, `UNKNOWN`, or `EMPTY`.

Ranked retrieval remains bounded and normally reports `PARTIAL` or `UNKNOWN`.
Exhaustive retrieval uses deterministic storage ordering and cursor traversal;
it reports `COMPLETE` only after stable termination. Parent promotion,
reranking, and diversity may refine ranked results but cannot turn a partial
set into a complete one. Completeness propagates into V2 context and Final QA.

## Alternatives

- Treat a large `top_k` as complete: rejected because it is unverifiable.
- Replace V1 retrieval: rejected because Phase 0–8 is frozen.
- Expose storage offsets: rejected because they are unstable and leak backend
  details.

## Consequences

Callers can distinguish relevance ranking from enumeration. Stable snapshots
may require temporary state and impose retention limits. Cursor expiry is a
typed outcome, not silent restart.

## Compatibility

V1 ranked retrieval, `MetadataFilter`, `ScoredChunk`, RRF, reranking, and title
provenance are unchanged. V2 adapters may wrap V1 ranked results but must not
upgrade their completeness.

## Migration

Add result-set metadata and cursor storage independently of canonical chunks.
Existing indexes remain valid; optional positional projections rebuild from
canonical versions without identity changes.

## Security implications

Cursors are opaque, integrity-protected, notebook-scoped, short-lived, and
limit-bearing. Enumeration requires the same authorization on every page.

## Testing requirements

Test deterministic pagination, stable termination, cursor tampering/expiry,
forced truncation, concurrent mutation, exact/version filters, and truthful
completeness propagation.

## Observability

Record plan type, examined/returned counts, completeness, page count, latency,
and truncation reason without logging query text or document content.

## Rollback/recovery

Disable V2 routes/plans and expire cursors. V1 retrieval remains operational.

## Future-phase impact

Phase 9 may render completeness and continuation. Phase 11 may compose result
sets but may not erase their completeness boundaries.

## Explicit non-goals

This ADR does not choose embedding models, implement aggregation, or promise
unbounded exports.
