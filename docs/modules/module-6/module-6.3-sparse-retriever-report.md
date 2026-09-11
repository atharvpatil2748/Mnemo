# Module 6.3 SparseRetriever Verification Report

## Verdict

**Module 6.3: COMPLETE.** Module 6.4 and Module 6.5 remain not started; M6 is
not verified. This work is uncommitted and unreleased at version 0.20.1.

## Architecture

ADR-0039 extends ADR-0038's version-aware derived-index rule to SQLite FTS5.
The frozen `RetrieverInterfaceV1`, `StorageInterfaceV1`, `MetadataFilter`,
`ScoredChunk`, and `Chunk` contracts were not modified.

`SparseRetriever` is a stateless delegate to
`StorageInterfaceV1.search_sparse()`. SQLite migration 4 adds
`retrieval_version_metadata`, keyed by `(document_id, version_id)`. Its type and
date values derive from exact-version `ParsedDocument` and `DocumentVersion`
state coordinated by `CompositeStorage`. Notebook/source predicates query the
canonical relational `Source` rows and execute before ranking.

SQLite returns a negative BM25 cost with smaller values ranked first. The
adapter exposes unnormalized `-bm25()` values so results satisfy ADR-0002's
descending-score convention. Sparse values are not calibrated against dense
scores; cross-mode fusion remains Module 6.5.

FTS rows remain derived state synchronized by existing SQLite triggers.
Projection and chunk writes share one transaction. Composite compensation now
restores both chunk rows and prior sparse projection if the vector write fails.
Historical rows without migration-4 projection fail closed for type/date
filters until rebuilt; unfiltered and relational membership queries remain
available.

## Test evidence

Focused SparseRetriever, SQLite filter/projection, and CompositeStorage tests:
**58 passed**. The matrix covers normal/empty/invalid queries, top-k, empty
results, storage failures, invalid backend results, registry discovery,
storage-agnostic imports, exact-version type/date behavior, inclusive date
bounds, null dates, fail-closed unprojected rows, source-ID OR semantics,
same-row notebook/source intersection, score ordering, identity, and
projection compensation. Migration 4 is tested from a version-3 database,
including a second idempotent open.

Deterministic fixtures—not the one-version golden book—prove superseded/current
version separation, differing version type/date, inclusive boundaries, and
missing-date behavior.

## Real golden SQLite acceptance

Executed at `2026-08-13T09:44:37.681344+00:00` with
`scripts/verify_module_6_3_sparse.py`:

- Corpus: `goldenDataset/Bhagavad-gita-As-It-Is.pdf`
- SHA-256: `ff112b0b056d303b792f6f2e68cbd73a89adf612fa9113f932446cdea7741583`
- Classification: `book`
- Real chunks indexed: 1,275
- Dedicated database:
  `data/module-6.3-acceptance/20260813T094352302462Z/mnemo.db`
- Query: `What does the Bhagavad Gita teach about duty?`
- `top_k`: 5; unfiltered results: 5; filtered results: 5
- Filter: acceptance notebook AND acceptance source AND `doc_types=[book]`
- Filtered/unfiltered eligible identities: identical
- Descending scores: `9.351617995457696`, `9.269531160380218`,
  `8.004111685954335`, `7.201607814854517`, `7.109710240700759`
- Returned chunk IDs, in order:
  - `70a5a0adeada1ba3ad5d17e10a1f6f61b323d3f3db62fa1eb32303a8b13c12a8`
  - `7484e4b9f63c238455f2cd254fa9aee448a55b018ff40a1ebe15611b6fc07427`
  - `cc3c1a957112dce0acac04380adaa95bc5728f0289de70755774e297c0c50f82`
  - `8d9ebdc51fd8529b24cbb2fd83b4644a303987f7e822ef56226390d0f483378f`
  - `01f748728d6807afa9a1529fe50e40bfa94554461e537f14b27102a3e1a31be4`
- Canonical document identity: PASS
- Relevance spot-check: the top result discusses prescribed duties and
  exemplary action; this is plausible keyword evidence, not a semantic-quality
  claim
- FTS deletion followed by empty search: PASS
- Reindex followed by successful search: PASS
- Total parse/chunk/index/query/delete/reindex time: 45.3535 seconds

The acceptance database was newly created. No historical M4/M5 database or
Qdrant collection was modified. The golden corpus does not naturally prove
multi-version/date variation; those claims come only from deterministic SQLite
fixtures.

## Validation gates

- Focused tests: 58 passed
- Full pytest: 851 passed, 1 skipped
- Coverage: 90.23%
- Ruff format: PASS (`146 files already formatted`)
- Ruff check: PASS
- Production strict mypy: PASS (`76 source files`)
- Pre-commit: PASS
- `git diff --check`: PASS

## Files and scope

Implementation touches `mnemo/retrieval/sparse.py`, retrieval exports,
`SQLiteStore`, and the internal CompositeStorage projection write. Tests,
ADR-0039, the acceptance runner, roadmap/architecture reconciliation, this
report, and changelog 0042 are included.

Module 6.1 and Module 6.2 changes remain preserved. Sparse retrieval does not
implement parents, parallel execution, deduplication, RRF, reranking, context
assembly, or answer synthesis.
