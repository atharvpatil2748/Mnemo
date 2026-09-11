# Phase 8.5 WP-08 Gate Evidence

**Status:** WP-08 implementation complete; behavioral and final Phase 8.5
certification remain WP-16/WP-17.

## Implemented contract

- Reused schema-v14 `structured_table_projections`, `structured_table_cells`,
  generation coverage, and active-generation aliases; no migration was added.
- Added an exact authorized dataset/schema catalog with dataset, source,
  document, version, generation, schema, row-count, field-type, readiness, and
  canonical evidence provenance. Internal paths/table names are not exposed.
- Composed `StructuredDatasetRuntimeService` through `KnowledgeEngine` and
  `Phase85RuntimeV1`. A deterministic active-generation-set identity is supplied
  to the generation-backed capability registration. Missing/stale/incomplete
  generations remain inactive and unavailable rather than appearing empty.
- Added a strict public DTO compiler to the existing `StructuredQueryV1` IR.
  Supported predicates are `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, inclusive
  `between`, `in`, `is_missing`, and `is_present`; supported deterministic
  operations include selection, sorting/null order, grouping, count,
  distinct-count, sum, min, max, average, and distinct fields.
- Added compatible-schema union and explicit typed equality join. Fuzzy,
  semantic, entity-resolution, graph, generated, and arbitrary SQL joins are
  rejected or absent by contract. Null join keys do not match; duplicate keys
  retain deterministic pair provenance.
- Added the shared application envelope, row/cell provenance, generation and
  schema identities, counts, predicate/order/null-policy summaries, coverage,
  omissions, limits, and recommended continuation actions.
- Added `POST /v2/retrieval/structured` and additive MCP `query_structured`.
  MCP exposes structured content and identical canonical JSON TextContent.

## Bounds, continuation, and completeness

Configured hard ceilings cover rows scanned/returned, groups, fields, evidence
references, response bytes, elapsed time, and page size. `CursorCodecV2` binds
the authorized notebook scope, exact dataset set, request fingerprint,
generation snapshot, ordering, effective limits, format/key version, and
expiry. Query, scope, budget, snapshot, or token tampering fails closed.

`complete` is returned only after the stable declared dataset universe is
evaluated and the result page terminates. More results produce `truncated` plus
`next_cursor`; terminal exhaustion produces a null cursor. Successfully
evaluated no-match is `empty`. Missing requested generations produce
partial/unavailable diagnostics and never a false empty/complete result. A
non-resumable hard scan/output failure is partial, not disguised as complete.

## Security evidence

Public DTOs use `extra=forbid`; there is no raw SQL/expression/function/order
fragment field. Dataset and field identifiers must resolve from the authorized
catalog and declared typed schema. Values are normalized by the existing typed
IR and are never executable SQL. Tests cover SQL-shaped field injection,
unknown/malicious fields and operators, invalid types, oversized page limits,
cross-notebook scope, cursor tampering, changed-query/budget replay, incompatible
types, null/duplicate join keys, extraction/aggregation/output bounds, timeout,
snapshot/fingerprint mismatch, and hostile extractor behavior. Standard HTTP
error mapping sanitizes internal failures.

## Behavioral cases 7–15

Deterministic fixtures prove numeric CPI `>` and inclusive range predicates,
cursor traversal for every matching row, complete-universe count and average,
branch filtering/comparison, descending numeric order with explicit null order,
exact named-row comparison, and branch group/count. None use semantic search,
top-k ranking, or lexical numeric comparison.

## Validation

- Focused WP-08 core/server/governance suite: 68 passed after contract updates.
- Affected MCP, WP-06 delivery, WP-07 retrieval, cursor, engine/runtime, and
  structured regressions: 196 passed after the single expected tool-inventory
  fixture was updated for additive `query_structured`.
- Targeted Ruff: pass.
- Targeted strict mypy: 13 production modules, pass.
- Governance JSON parse/schema and ADR-link tests: pass.
- `git diff --check`: pass for the WP-08 change set.
- Persistent warning: the host denies pytest cache/temp cleanup access; test
  execution itself succeeds.

## Runtime and compatibility statement

The configured evaluation database was inspected read-only and contains zero
structured projection rows and zero complete active structured generations.
Consequently, `Phase85RuntimeV1` truthfully keeps structured execution inactive
for that database. The isolated SQLite fixture creates a complete active
generation and proves the operational catalog/execution path without mutating
the configured database, the 44-file source corpus, or the certified Golden
Corpus.

V1 retrieval/plans/scored chunks/citations/Final-QA/HTTP, canonical `Chunk.text`,
FTS/title rows, Qdrant optionality, WP-06 asset delivery, and WP-07 evidence
retrieval are unchanged. No database migration, corpus ingestion, projection
backfill, model call, benchmark, release, or Phase 11 behavior occurred.

## Deferred boundary

WP-09+ owns semantic image/multimodal retrieval, multilingual activation,
multi-document orchestration, Final-QA V2 exposure, capability discovery,
blind-agent certification, and final certification. WP-08 provides only the
deterministic structured primitive those later work packages may invoke.
