# Module 6.6 Fusion-Aware Reranking Report

**Status:** COMPLETE — implemented, unit validated, repository validated, and
real pinned-model acceptance validated on 2026-08-13.

Module 6.6 implements accepted ADR-0042 without changing frozen Phase 1 or
Module 6.5 contracts. It consumes the explicit normalized original query and
the complete bounded `RetrievalFusionResult`, then returns an immutable
`RetrievalRerankResult`. It performs no retrieval, refill, candidate expansion,
RRF recomputation, context construction, or later Phase 6 work.

## Implementation

- `FusionRerankingInterfaceV1` is the additive async `fusion_reranker/v1`
  protocol. `FusionRerankerCapabilities` declares the bounded model identity.
- `RerankingModule` owns optional capability resolution. Empty input returns
  `UNCHANGED_EMPTY`; absence of `fusion_reranker/primary` returns typed
  `RRF_FALLBACK / PROVIDER_UNAVAILABLE`; registered provider failures
  propagate.
- `CrossEncoderReranker` scores every `(normalized original query, chunk.text)`
  pair with the pinned CPU model. It retains the raw logit and computes the
  explicit stable sigmoid relevance value separately from all RRF/raw
  retrieval evidence.
- Cross-encoder order is
  `(-relevance_score, fused_result.global_rank, fused_result.chunk.id)` with
  contiguous one-based reranked ranks. Original global ranks are immutable.
- The provider uses a 512-token pair limit, preserves the query with
  `only_second` truncation, processes batches of 16, permits one active request,
  and supports at most the existing 100 bounded fusion candidates.
- Registry startup loads and validates the exact pinned artifact before engine
  capability resolution. Reverse-order shutdown attempts every cleanup hook and
  surfaces the first deterministic failure.

## Contract and provenance safety

`Chunk`, `ScoredChunk`, `RetrieverInterfaceV1`, `RerankerInterfaceV1`,
`StorageInterfaceV1`, `EmbeddingProviderV1`, `LLMInterfaceV1`,
`ParentPromotionInterfaceV1`, `MultiSourceRetrievalInterfaceV1`,
`RetrievalPlan`, `FusedChunkResult`, and `RetrievalFusionResult` were not
modified for Module 6.6. Every reranked record retains its exact original
`FusedChunkResult`, and the top-level output retains its exact original
`RetrievalFusionResult`; no evidence is flattened or reconstructed.

## Focused and repository validation

| Gate | Result |
|---|---|
| Focused Module 6.6 tests | PASS — 34 tests |
| Phase 6.1–6.6 retrieval tests | PASS — 224 tests |
| Full `uv run pytest` | PASS — 1,004 passed, 1 skipped |
| Coverage | PASS — 90.06% |
| `uv run ruff format --check .` | PASS — 159 files formatted |
| `uv run ruff check .` | PASS |
| Production `mypy --strict` | PASS — 85 source files |
| `uv run pre-commit run --all-files` | PASS |
| Package builds | PASS — core, server, email-ingestion |

The skipped test is the existing opt-in live Phase 4/5 acceptance test. Local
pytest emitted a Windows temp/cache cleanup permission warning after successful
execution; it did not change the test exit status or validation results.

## Real pinned-model acceptance

Command:

```text
uv run --package mnemo-core --extra reranking python scripts/verify_module_6_6_reranking.py
```

Evidence: `docs/milestone-evidence/module-6.6-reranking.json`

| Measurement | Actual result |
|---|---|
| Corpus | `goldenDataset/Bhagavad-gita-As-It-Is.pdf` |
| SHA-256 | `ff112b0b056d303b792f6f2e68cbd73a89adf612fa9113f932446cdea7741583` |
| Module 6.5 collection | `mnemo_m6_5_gita_20260813t113208280320z` |
| Indexed points | 1,275 |
| Query | `What does the Bhagavad Gita teach about duty?` |
| Model | `cross-encoder/ms-marco-MiniLM-L6-v2` |
| Revision | `233902d25c440f23af6f7d6e94d2946bac0bee0a` |
| Device | CPU |
| Candidates before / after | 10 / 10 |
| Relevance range | 0.00009156862380676444–0.0939947070901 |
| Below 0.4 | 10 |
| Startup (cached artifact load) | 19.654 s |
| First rerank | 0.638 s |
| Second rerank | 0.544 s |
| Total acceptance | 27.647 s |
| Deterministic repeat | PASS |
| Fusion/RRF/global-rank provenance | PASS — unchanged |
| Typed unavailable fallback | PASS |
| Registered-provider failure propagation | PASS |

The acceptance regenerated a real Module 6.5 fusion result through the
existing Ollama, Qdrant, SQLite, dense/sparse retrieval, parent-promotion, and
RRF path. It reused the dedicated Module 6.5 acceptance collection without
mutating historical M4/M5 data. The identical second result establishes local
same-runtime determinism, not bitwise cross-platform determinism.

## Scope and limitations

- Modules 6.1–6.6 are complete.
- Module 6.7 and later modules are not started by this work.
- Milestone M6 is not verified.
- This is unreleased work: version 0.20.1 remains unchanged and no commit,
  push, tag, or release was created.
