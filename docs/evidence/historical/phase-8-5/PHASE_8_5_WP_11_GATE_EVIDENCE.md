# Phase 8.5 WP-11 Gate Evidence

Status: **WP-11 COMPLETE / FOCUSED-TESTED** (not Phase 8.5 certified)

WP-11 adds a thin deterministic multi-document composition primitive over the
existing `AdvancedRetrievalInterfaceV1`. Explicit document partitions are
executed in stable UUID order, each retains its own exact retrieval result,
snapshot, provenance, completeness, and existing `CursorCodecV2` continuation
cursor. No new cursor encoding, query engine, SQL surface, or autonomous
planning was introduced.

## Changed files

- `mnemo-core/mnemo/retrieval/partitioned.py`
- `mnemo-core/mnemo/retrieval/__init__.py`
- `mnemo-core/mnemo/engine.py`
- `mnemo-server/mnemo_server/schemas/retrieval_v2.py`
- `mnemo-server/mnemo_server/services/retrieval_v2.py`
- `mnemo-server/mnemo_server/mcp/contracts.py`
- `mnemo-core/tests/unit/test_partitioned_retrieval.py`

## Contract

`search_evidence` accepts additive `partition_document_ids` and
`all_authorized_documents`, and returns a bounded, canonical document set after
notebook-membership authorization. The response exposes a `partitions` array;
partition results are never flattened without their document identity. A single
aggregate continuation cursor (encoded with the existing CursorCodecV2) binds
the query, scope, document set, limits, and all child continuation positions.
Unauthorized or out-of-scope identities fail closed through the existing
retrieval scope path.

`DeterministicComparisonServiceV1` provides typed compare/delta semantics over
WP-08 `StructuredValue` operands, preserving both operands and their evidence;
missing, invalid, unavailable, and incompatible values are rejected rather
than coerced or delegated to an LLM.

## Validation

- Focused WP-11 tests: 6 passed (partitioning, aggregate cursor binding, typed comparison, missing-value handling).
- Affected retrieval/structured/MCP regression matrix: 95 passed.
- Ruff check (affected modules): passed.
- Strict mypy (affected core/server modules): passed.
- `git diff --check`: passed.
- No corpus, database, model, ingestion, or benchmark state was modified.

Structured numeric predicates, aggregates, unions, and typed equality joins
remain owned by WP-08 and were reused rather than duplicated. Semantic image,
multilingual, Final-QA, capability discovery, security certification, and
external-agent certification remain deferred to their assigned work packages.
