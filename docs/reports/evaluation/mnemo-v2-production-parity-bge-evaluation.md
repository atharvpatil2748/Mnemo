# Mnemo V2 Production-Parity BGE Evaluation

**Date:** 2026-09-06  
**Status:** `PRODUCTION_PARITY_EVALUATION_PASS`  
**Scope:** Evaluation only; no BGE activation or production alias change

## Executive result

The governed BGE reranker completed the protected 18-query Phase 8.5 evaluation against the actual 44-document production V2 store and actual server-owned V2 candidate path. The evaluation ran on CUDA with batch size 2, no CPU fallback, the governed 256-token contextual pair policy, and identity-bound document/version relevance.

The evaluation passed the production-parity execution and safety gates. It does **not** activate BGE and does not by itself certify Mnemo.

| Metric | Result |
|---|---:|
| Recall@1 | 83.3% (15/18) |
| Recall@5 | 88.9% (16/18) |
| Recall@10 | 88.9% (16/18) |
| MRR | 0.8474 |
| nDCG@10 | 0.8548 |
| Target in fused Top-50 | 94.4% (17/18) |

`MBSEL-03` was absent from the fused candidate pool and therefore could not be recovered by the reranker. `MBSEL-02` entered the pool but was ranked 19. `MBSEL-01` was ranked 5. The other 15 targets were ranked first.

## Production identity and immutability

The evaluator resolved the store through the same governed server configuration and registration used by production V2 serving.

- Path: `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db`
- Governed identity: `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d`
- Physical SHA-256 before: `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`
- Physical SHA-256 after: `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`
- Size before/after: 189,804,544 bytes
- Documents: 44
- Versions: 44
- Source memberships: 44
- Chunks: 2,658
- `PRAGMA integrity_check`: `ok`
- Foreign-key violations: 0
- WAL before/after: 0 bytes

The corpus database was byte-identical after evaluation. The separate 67-document Phase 8.6 database did not participate.

## Query identity mapping

The frozen Phase 8.5 query set contains 18 queries. Each external target was resolved by exact corpus-manifest source hash, then bound to its canonical source, document, and version identities in the production store. Relevance is document/version-level: every candidate chunk belonging to the target document/version is relevant.

- Resolved: 18/18
- Ambiguous: 0
- Unresolved: 0
- Query-set SHA-256: `8b64f62d520ca3d442370c8aff59de76e993bb1ffea7f76382662cda0e7335f8`
- Corpus census SHA-256: `8210d54998292c619e320fbe1995f845e9152f95545f12a9f74b79ad0dd4aba9`

No filename equality, title equality, substring matching, synthetic identity, or Phase 8.6 hardcoded document mapping was used as relevance truth.

## Candidate and reranker contract

Candidate generation used `mnemo.full-multilingual-retrieval-application/2` and `mnemo.v2-typed-candidate-builder/1`, with the real authorization, evidence-resolution, dense BGE-M3, FTS5, and RRF path.

- Retrieval candidate K: 50
- Reranker candidate K: 50 fused candidates
- RRF K: 60
- Candidate parity: PASS
- Candidate identities and their input ordering were recorded per query
- Semantic and contextual input hashes were recorded per candidate

The reranker configuration was:

- Model: `BAAI/bge-reranker-v2-m3`
- Revision: `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`
- Pair policy: `bge-reranker-v2-m3-pair-256-contextual-v1`
- Candidate representation: `[title | heading_path] + authorized semantic text`
- Query representation: NFKC plus bounded whitespace
- Truncation: deterministic retain-head; unused query budget assigned to the document
- Audited pairs: 900
- Maximum retained pair length: 256 tokens
- Deterministically truncated pairs: 646
- Pair-policy violations: 0

## CUDA execution

- Device: `cuda`
- GPU: NVIDIA GeForce RTX 4060 Laptop GPU
- Python: 3.12.10
- PyTorch: 2.13.0+cu130
- CUDA: 13.0
- Batch size: 2
- CPU fallback: disabled and not observed
- Peak allocated GPU memory: 2,302,887,936 bytes
- Peak reserved GPU memory: 2,336,227,328 bytes
- OOM retries: 0
- Total evaluator time: 280.24 seconds

The production router remained in `PASS_THROUGH` throughout. The evaluator used a server-owned, non-activating BGE lease and a separate read-only store connection. BGE was not installed into or selected by the active production router.

## Dynamic public requested-k

Public requested-k and the internal fused reranker pool remained separate. Real application-service probes produced:

| requested_k | returned | internal reranker K |
|---:|---:|---:|
| 1 | 1 | 50 |
| 5 | 5 | 50 |
| 10 | 10 | 50 |
| 25 | 25 | 50 |
| 50 | 50 | 50 |

The public API was not hardcoded to 50. MCP/tool input cannot alter the governed internal candidate pool.

## Historical baseline comparison

The historical corrected Golden result reported BGE R@1/R@5/R@10 of 94.4% and MRR/nDCG@10 of 0.944. It is **not identity-equivalent** to this run: that evaluation used the 67-document canonical/evaluation database and a different candidate protocol/model-native input behavior. The historical ms-marco result is likewise not an equivalent paired control for this production-store run.

Accordingly, this report does not manufacture gains, regressions, ties, or statistical significance against those numbers. The difference between 94.4% historical R@1 and 83.3% here is a real observed cross-protocol difference, but cannot be attributed solely to the reranker. A same-corpus, same-candidate, same-256-token ms-marco control would be required for a paired model-effect claim.

## Validation

- Mapping: 18 resolved, 0 ambiguous, 0 unresolved
- Candidate identity resolution: PASS
- Production candidate path: PASS
- Candidate/input audit: PASS
- Dynamic requested-k: PASS for 1, 5, 10, 25, 50
- CUDA/batch-2/no-fallback: PASS
- Checkpoint: `COMPLETE`, 18/18
- Focused tests: 63 passed
- Ruff: PASS
- Strict mypy: PASS (3 touched production modules)
- Compileall: PASS
- JSON parsing: PASS
- Production DB byte identity and integrity: PASS

Repository-wide `git diff --check` retains the previously documented unrelated whitespace issue in `mnemo-core/mnemo/models/chunks.py:65`; this evaluation did not modify that file.

## Lifecycle and next gate

The lifecycle remains:

- DECLARED: PASS
- IMPLEMENTED: PASS
- CONFIGURED: PASS
- BUILDABLE: PASS
- READY: PASS
- ACTIVE: PASS
- EXPOSED: PASS
- EVALUATED: FALSE
- VERIFIED: FALSE
- CERTIFIED: FALSE

Serving remains `PASS_THROUGH`; `BGE_ACTIVE = FALSE`. The next single governed gate is the separate, controlled BGE activation authority. Activation must consume this evaluation evidence, capture rollback state, and be followed by post-activation HTTP/MCP verification and rollback verification.

