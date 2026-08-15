# Module 6.5 Multi-Source Retrieval Orchestration and Fusion Report

## Verdict

**COMPLETE and locally validated** under accepted ADR-0041. This verdict is
limited to Module 6.5. Modules 6.6–6.10 are not started and milestone M6 is not
verified.

## Scope and architecture

Module 6.5 implements the additive `MultiSourceRetrievalInterfaceV1` through
`MultiSourceRetriever`. It consumes the canonical Module 6.1 `RetrievalPlan`,
resolves existing dense, sparse, and parent-promotion capabilities through a
frozen `PluginRegistry`, and returns an immutable `RetrievalFusionResult`.

The implementation preserves every frozen Phase 1 contract. It does not modify
`RetrieverInterfaceV1`, `StorageInterfaceV1`, `EmbeddingProviderV1`, `Chunk`,
`ScoredChunk`, `MetadataFilter`, or `ParentPromotionInterfaceV1`, and it has no
direct Qdrant, SQLite, SurrealDB, reranking, context, citation, synthesis, or
multi-hop dependency.

## Execution semantics

- Effective invocations have deterministic identities such as
  `sq-1:dense`; `HYBRID` expands in dense-then-sparse order.
- Each dense invocation embeds its exact query text through the configured
  `EmbeddingProviderV1`. One vector is never reused for unrelated subqueries.
- A shared configured semaphore bounds embedding, retrieval, and one mandatory
  source-local parent-promotion call per stream. Default concurrency is four;
  accepted bounds are 1 through 32.
- `GRAPH` and compatibility-only `PARENT` fail explicitly before task creation.
- Any invocation, promotion, registry, or validation failure fails the complete
  operation; peers are cancelled and no partial success is returned.
- Deduplication uses canonical `Chunk.id`. Conflicting immutable snapshots for
  one ID raise an integrity error.
- Each invocation contributes at most once per chunk. RRF is
  `math.fsum(1 / (60 + local_rank))` over one-based ranks. Raw dense and sparse
  scores remain unchanged in immutable `FusionEvidence` records.
- Global ordering is `(-rrf_score, chunk.id)`. The caller's required
  `global_limit` (1 through 100) is applied after fusion, then contiguous
  one-based global ranks are assigned.
- `requires_multi_hop` is retained as first-stage state for Module 6.10.
  `requires_multi_doc` never strips immutable planner filters.

## Automated validation

Executed on 2026-08-13 from the repository root:

```text
uv run pytest mnemo-core/tests/unit/test_multi_source_retriever.py
83 passed

uv run pytest <Module 6.1-6.5 focused test set>
147 passed

uv run pytest
970 passed, 1 skipped
coverage: 90.68% (branch-aware)

uv run ruff format --check .
PASS (155 files already formatted after generated test-temp cleanup)

uv run ruff check .
PASS

uv run mypy mnemo-core/mnemo mnemo-server/mnemo_server
PASS (80 source files)

uv run pre-commit run --all-files
PASS

git diff --check
PASS
```

The full run emitted one expected warning from the local Qdrant integration
about a payload index; it did not fail a test. The first formatting/pre-commit
attempt exposed pytest-generated files under `.tmp`; those disposable files
were formatted only to complete the gate and then removed from the working
tree. Production files were already compliant.

## Real acceptance

Command:

```text
uv run python scripts/verify_module_6_5_fusion.py
```

Evidence: `docs/milestone-evidence/module-6.5-fusion.json`

| Measurement | Result |
|---|---:|
| Timestamp (UTC) | 2026-08-13T11:33:53.628544+00:00 |
| Corpus | `goldenDataset/Bhagavad-gita-As-It-Is.pdf` |
| SHA-256 | `ff112b0b056d303b792f6f2e68cbd73a89adf612fa9113f932446cdea7741583` |
| Physical pages | 952 |
| Canonical chunks | 1,275 |
| Ollama model / dimension | `nomic-embed-text` / 768 |
| Qdrant collection | `mnemo_m6_5_gita_20260813t113208280320z` |
| Qdrant points | 1,275 |
| SQLite database | `data/module-6.5-acceptance/20260813T113208280320Z/mnemo.db` |
| Planner subqueries | 3 (hybrid, dense, sparse) |
| Effective source streams | 4 |
| Raw/promoted counts | 8/8 for every stream |
| Source-local occurrences | 32 |
| Deduplicated candidates | 24 |
| Global limit / final results | 10 / 10 |
| Configured concurrency | 4 |
| Embedding / indexing | 35.920 s / 3.941 s |
| First orchestration | 0.324 s |
| Cached repeat | 0.075 s |
| Total acceptance | 105.142 s |
| Deterministic repeat | PASS |

The real path exercised canonical parsing/chunking, Ollama embeddings, Qdrant
dense retrieval, SQLite FTS5 sparse retrieval, exact metadata filters,
registry resolution, ParentRetriever once per stream, cross-source
deduplication, RRF, and global ranking. The final identities, ranks, RRF scores,
and all raw evidence are recorded in the JSON artifact.

The golden BookChunker corpus contains 1,275 root chunks and no stored parent
families. Consequently, the live ParentRetriever calls were genuine but
non-promoting. This is a dataset limitation, not fabricated promotion
evidence. Threshold, replacement, provenance, and fusion behavior with
canonical families are validated by controlled Module 6.4 real-storage
fixtures and Module 6.5 unit tests.

## Files introduced for Module 6.5

- `mnemo-core/mnemo/interfaces/multi_source_retrieval.py`
- `mnemo-core/mnemo/retrieval/fusion.py`
- additive retrieval evidence/result models and exports
- `mnemo-core/tests/unit/test_multi_source_retriever.py`
- `scripts/verify_module_6_5_fusion.py`
- `docs/adr/ADR-0041-deterministic-multi-source-retrieval-fusion.md`
- this report, changelog 0044, and the JSON evidence artifact

## Status boundary

- Modules 6.1–6.5: COMPLETE
- Modules 6.6–6.10: NOT STARTED
- M6: NOT VERIFIED
- Version: 0.20.1
- Commit, push, tag, release: not performed
