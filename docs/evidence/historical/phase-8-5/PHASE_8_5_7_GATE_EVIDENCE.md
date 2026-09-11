# Phase 8.5.7 Gate Evidence

**Gate:** PASS  
**Scope:** Structured retrieval and safe aggregation (ADR-0063)  
**Evidence date:** 2026-08-25

## Implementation

Phase 8.5.7 adds an internal, provider-neutral `StructuredQueryV1` path that
consumes an immutable `RetrievalResultSetV1`; it does not bypass or modify V1
retrieval. The typed, extra-forbid AST allowlists fields, predicates, ordering,
grouping, distinct, aggregates, pagination, and resource budgets. Conservative
schema discovery reports typed column observations and explicit confidence,
rejecting absent or ambiguous headers.

Deterministic extractors support canonical `TableBlock` IR, exact-version
SQLite projections, and a bounded delimited fallback. Values have explicit
present/missing/uncertain/invalid/unavailable states. Normalization covers
declared strings, integers, decimals, booleans, ISO dates/datetimes, ISO
durations, enums, lists, and objects without locale, currency, timezone, or
unit guessing. Filters, stable typed sorting, grouping, distinct, count,
distinct-count, sum, minimum, maximum, average, and typed comparison run
without an LLM.

Every value and aggregate retains compact notebook/source/document/version/
chunk/occurrence/derivation, locator, retrieval-path, and extraction-method
provenance. Deduplication merges supporting evidence without merging distinct
source positions. Retrieval completeness is never upgraded; missing evidence,
unavailable representations, truncation, and every configured bound remain
explicit in results and diagnostics.

## Storage and migration

SQLite schema v11 additively creates `structured_table_projections` and
`structured_table_cells`, with exact-version foreign keys, deterministic table
identities, checksums, indexes, and the existing atomic `index_generations`
BUILDING-to-READY lifecycle. Projection is idempotent and immutable; failed or
interrupted generations are rebuilt transactionally. Reads use fixed SQL
shapes, allowlisted projected columns, and bound parameters. Migration tests
cover fresh creation, v10 upgrade, repeated migration, and rollback after an
injected statement failure.

## Security, bounds, and correctness

Tests cover notebook/document/version allowlists, hostile extractor candidate
injection, over-limit extractor output, unknown AST nodes/fields/operators,
expression payload rejection, parameterized values containing apostrophes,
type confusion, incompatible comparisons, nesting/group/distinct/aggregation/
record/output bounds, and full-materialization prevention. Production
structured code contains no `eval`, `exec`, user SQL, provider SQL, or dynamic
SQL expression compiler.

The result metadata records schema generation, retrieval snapshot identity,
candidate and extracted-row universes, matched/returned counts, operation
kinds, provenance truncation, stage timings, and truncation reasons. Pagination
is deterministic over the supplied immutable retrieval snapshot.

## Executed evidence

```text
uv run pytest -q --no-cov mnemo-core/tests/unit/test_structured_retrieval.py
37 passed in 1.59s

uv run pytest -q
1600 passed, 1 skipped, 8 warnings in 144.60s
Required test coverage of 90% reached. Total coverage: 90.06%

uv run mypy --strict mnemo-core/mnemo mnemo-server/mnemo_server plugins/email-ingestion/email_ingestion
Success: no issues found in 175 source files

uv run ruff format --check .
PASS

uv run ruff check .
PASS

uv build --package mnemo-core
uv build --package mnemo-server
uv build --package mnemo-email-ingestion
All source distributions and wheels built successfully (0.25.0)

git diff --check
PASS
```

## Compatibility and Golden Corpus

`StorageInterfaceV1`, `RetrievalPlanV2`, `RetrievalResultSetV1`, canonical
documents/versions/sources/chunks/text, V1 FTS/embeddings/retrieval/Final-QA,
HTTP routes, six MCP tools, and Qdrant optionality are unchanged. Structured
interfaces and CompositeStorage delegation are additive.

The certified corpus was queried only through SQLite read-only connections for
the gate audit. Its canonical baseline remains:

```text
documents=15, document_versions=15, sources=15
chunks=1514, fts_chunks=1514, fts_chunk_titles=1514
orphan_chunks=0, orphan_versions=0, duplicate_chunk_ids=0
sha256(concatenated ordered chunk id + text)=1997852deb381869d1ff72f511fa22b97bdea5287e5f6632ef1292405bbf4e66
```

Schema v11 is additive; no structured rows were backfilled into the certified
corpus (`structured_table_projections=0`). Existing versions require a governed
projection build from their exact retained canonical IR before structured
execution. No purge, re-ingestion, re-chunking, embedding regeneration, or
Qdrant enablement occurred.

## Limitations and rollback

This gate does not implement arbitrary joins, arbitrary analytics code,
LLM-based extraction, multimodal Final-QA V2, multilingual retrieval, or new
HTTP/MCP delivery. General associations are expressed through authorized
multi-document records, typed system identity fields, grouping, and comparison;
unauthorized cross-notebook joins are forbidden by ADR-0063.

Rollback disables structured planning/composition while retaining V1 text
retrieval. Derived v11 projections can be rebuilt from exact canonical IR;
failed generations are never served. Canonical Phase 0–8 data requires no
rollback.

## Verdict

`PHASE 8.5.7 GATE: PASS`
