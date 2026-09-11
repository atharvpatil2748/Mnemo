# ADR-0063: Structured Retrieval and Safe Aggregation

- **Status:** Accepted
- **Implementation:** Operational exposure complete (Phase 8.5 WP-08 gate; behavioral and final certification pending)
- **Date:** 2026-08-24
- **Extends:** ADR-0011, ADR-0039, ADR-0058
- **Supersedes:** Nothing

## Context

CSV, XLSX, and document tables contain typed rows that embedding retrieval
cannot aggregate exactly.

## Problem

Questions involving filters, counts, averages, grouping, sorting, and “all
rows” require deterministic semantics, row-level evidence, and injection-safe
execution.

## Decision

Add a versioned `StructuredQueryV1` IR with an allowlisted dataset/version,
selected columns, typed predicates, grouping, aggregate functions, ordering,
limit, and cursor. Schema discovery produces typed column observations and
confidence without mutating canonical parser data.

A compiler validates identifiers and types, binds all values as parameters,
and executes only supported operations against version-scoped derived table
projections. No user SQL or provider-generated SQL is executed. Results include
schema generation, row universe, matched/returned counts, completeness from
ADR-0058, deterministic ordering, and row/cell provenance back to source
blocks/chunks.

## Alternatives

- Ask an LLM over sampled chunks: rejected for exact aggregates.
- Expose SQL: rejected for security and portability.
- Treat tables as plain text only: retained as fallback, not structured truth.

## Consequences

Correctness improves at the cost of schema inference and projection lifecycle.
Ambiguous columns return a typed clarification/failure instead of guessing.

## Compatibility

Existing table blocks, chunks, FTS, and ranked retrieval remain unchanged.
Structured projections and plans are additive.

## Migration

Build versioned projections from canonical IR where available. Missing IR is
reported; reparse requires exact original bytes under ADR-0059.

## Security implications

Strict allowlists, parameter binding, row/column authorization, resource
ceilings, and denial of arbitrary functions are mandatory.

## Testing requirements

Test schema discovery, all predicate types, nulls, Unicode, grouping,
aggregates, stable pagination, provenance, ambiguous columns, injection,
overflow, resource limits, and migration rollback.

## Observability

Record operation kinds, rows examined/returned, completeness, latency, and
typed rejection reasons without values.

## Rollback/recovery

Disable structured planning and drop/rebuild derived projections. Text
retrieval remains available without false exactness claims.

## Future-phase impact

Phase 9 may provide a typed query builder/table viewer; Phase 11 may combine
aggregates only when universes and completeness are compatible.

## Explicit non-goals

This ADR does not provide arbitrary analytics code, joins across unauthorized
notebooks, or editable spreadsheets.
