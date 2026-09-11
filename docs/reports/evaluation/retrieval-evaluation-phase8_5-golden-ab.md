# Corrected Identity-Bound Phase 8.5 Golden GPU A/B

**Status:** VALID EXPERIMENT  
**Promotion decision:** **PROMOTE_BGE**

## Executive summary

The protected 18-query Golden A/B completed with exact document/version relevance and one frozen K50 candidate pool per query. BGE ranked 17/18 targets first; ms-marco ranked 7/18 first. BGE improved ten query ranks, regressed none, and tied eight. The only miss for both models, MBSEL-03, was absent from K50 and is a candidate-retrieval failure, not a reranker failure.

## Exact command

```powershell
.\scratch\.venv-gpu-preflight\Scripts\python.exe scratch/execute_identity_bound_evaluation.py --mode benchmark --candidate-protocol forensic-v1 --candidate-pool-k 50 --reranker both --reranker-batch-size 2 --device cuda --query-set scratch/phase8_5_identity_bound_queries.json --manifest data/canonical_production/phase8_5_integrity_manifest.json --query-vectors scratch/evaluation_recovery/phase85_identity_bound_query_embeddings.npy --query-vectors-digest scratch/evaluation_recovery/phase85_identity_bound_query_embeddings_input.sha256 --mapping-output scratch/identity_bound_phase8_5_mapping_validation.json --validation-output scratch/identity_bound_phase8_5_harness_validation.json --model-cache D:/Mnemo/phase8.5.11-models/huggingface/hub --output scratch/identity_bound_phase8_5_golden_ab_gpu_results.json --checkpoint scratch/identity_bound_phase8_5_golden_ab_gpu_checkpoint.json --failure-output scratch/identity_bound_phase8_5_golden_ab_gpu_failure.json
```

## Experiment identity

- Database SHA-256: `dc9e7fa2d1cb77f0e42ec3220377f74b1e2f98842acbfe487d1c7e6502fb2ada`
- Query-set SHA-256: `8b64f62d520ca3d442370c8aff59de76e993bb1ffea7f76382662cda0e7335f8`
- Governed query-manifest SHA-256: `20077f3f4d41d35347ddb2204321c3e9d0ccd533fc44a4fe2c4b0be769a2de48`
- Integrity-manifest SHA-256: `dd6a194c00675be253f580ecdeec8cb8930d7efc92ebd6d333aa8c57ab8fa62c`
- Corpus vectors SHA-256: `ff0b64210a6a2f3aa513879cc76e8fd7aaf426333678b83969eb3918daeb4693`
- Query vectors SHA-256: `5a4469afa36e4ecf39dd01b691fdd9a779a9c48b6f3bbf6eba207aa3416c7db1`
- Candidate protocol/K/RRF-k: `forensic-v1` / 50 / 60
- ms-marco revision: `233902d25c440f23af6f7d6e94d2946bac0bee0a`
- BGE revision: `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`
- BGE-M3 query-embedding revision: `5617a9f61b028005a4858fdac845db406aefb181`
- Python/PyTorch/CUDA: `3.12.10 (tags/v3.12.10:0cc8128, Apr  8 2025, 12:21:36) [MSC v.1943 64 bit (AMD64)]` / `2.13.0+cu130` / `13.0`
- GPU: `NVIDIA GeForce RTX 4060 Laptop GPU`; reranker batch size: 2

The 18 query vectors were generated once from the unchanged governed queries and frozen for candidate construction. Production corpus embeddings were not regenerated or modified.

## Validation

- Target mapping: 18 resolved, 0 ambiguous, 0 unresolved.
- Candidate-pool and contextual semantic-input equality: PASS for all 18 queries.
- Checkpoint: COMPLETE, 18/18 records per arm.
- CUDA-only execution; no CPU fallback; zero OOM retries.
- Protected-state hashes: unchanged.
- ME361's governed extensionless label resolved to exactly one manifest stem, then content SHA-256 and notebook membership established canonical document/version identity.

## Overall metrics

| Reranker | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 18 | 0.389 | 0.611 | 0.722 | 0.501 | 0.546 |
| bge | 18 | 0.944 | 0.944 | 0.944 | 0.944 | 0.944 |

## Paired analysis

| Cutoff | BGE gains | BGE losses | Ties | Exact two-sided binomial p |
|---|---:|---:|---:|---:|
| R@1 | 10 | 0 | 8 | 0.0020 |
| R@5 | 6 | 0 | 12 | 0.0312 |
| R@10 | 4 | 0 | 14 | 0.1250 |

N=18 is small; exact paired p-values are reported without asymptotic overclaiming. The R@1 result (10 gains, 0 losses) is decisive within this fixed Golden set; R@10 has only four discordant improvements.

## Metrics by language direction

### en->en

| Reranker | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 5 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| bge | 5 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

### en->mr

| Reranker | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 1 | 0.000 | 1.000 | 1.000 | 0.500 | 0.631 |
| bge | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

### hi->en

| Reranker | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 5 | 0.000 | 0.000 | 0.400 | 0.078 | 0.126 |
| bge | 5 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

### hi->mr

| Reranker | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| bge | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

### mr->en

| Reranker | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 5 | 0.000 | 0.600 | 0.600 | 0.227 | 0.312 |
| bge | 5 | 0.800 | 0.800 | 0.800 | 0.800 | 0.800 |

### mr->mr

| Reranker | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| bge | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

## Metrics by format

### csv

| Reranker | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 3 | 0.333 | 0.667 | 1.000 | 0.458 | 0.582 |
| bge | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

### js

| Reranker | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 3 | 0.333 | 0.667 | 1.000 | 0.542 | 0.649 |
| bge | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

### pdf

| Reranker | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 9 | 0.444 | 0.556 | 0.556 | 0.511 | 0.515 |
| bge | 9 | 0.889 | 0.889 | 0.889 | 0.889 | 0.889 |

### pptx

| Reranker | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 3 | 0.333 | 0.667 | 0.667 | 0.475 | 0.500 |
| bge | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

## Candidate coverage

| K | Targets present | Coverage |
|---:|---:|---:|
| 25 | 17/18 | 94.4% |
| 50 | 17/18 | 94.4% |
| 100 | 18/18 | 100.0% |

MBSEL-03 (Marathi query → English resume) was absent from K25 and K50 but entered at rank 96 in K100. Neither K50 reranker could recover it.

## Per-query comparison

| QID | Direction | Format | Target | ms rank | BGE rank | Δ (ms−BGE) | Outcome |
|---|---|---|---|---:|---:|---:|---|
| MBSEL-01 | en->en | pdf | Atharv_Patil_RESUME_SDE.pdf | 1 | 1 | 0 | TIE |
| MBSEL-02 | hi->en | pdf | Atharv_Patil_RESUME_SDE.pdf | 34 | 1 | 33 | BGE_GAIN |
| MBSEL-03 | mr->en | pdf | Atharv_Patil_RESUME_SDE.pdf | — | — | 0 | TIE |
| MBSEL-04 | en->mr | pdf | manuscript.pdf | 2 | 1 | 1 | BGE_GAIN |
| MBSEL-05 | hi->mr | pdf | manuscript.pdf | 1 | 1 | 0 | TIE |
| MBSEL-06 | mr->mr | pdf | manuscript.pdf | 1 | 1 | 0 | TIE |
| MBSEL-07 | en->en | csv | Y24_CPI.csv | 1 | 1 | 0 | TIE |
| MBSEL-08 | hi->en | csv | Y24_CPI.csv | 8 | 1 | 7 | BGE_GAIN |
| MBSEL-09 | mr->en | csv | Y24_CPI.csv | 4 | 1 | 3 | BGE_GAIN |
| MBSEL-10 | en->en | pptx | ME361_L1_fbd03201-7db3-4553-a6e5-06f24817f9ea (1).pptx | 1 | 1 | 0 | TIE |
| MBSEL-11 | hi->en | pptx | ME361_L1_fbd03201-7db3-4553-a6e5-06f24817f9ea (1).pptx | 11 | 1 | 10 | BGE_GAIN |
| MBSEL-12 | mr->en | pptx | ME361_L1_fbd03201-7db3-4553-a6e5-06f24817f9ea (1).pptx | 3 | 1 | 2 | BGE_GAIN |
| MBSEL-13 | en->en | pdf | Act 2. panch-parmeshwar-by-munshi-premchand.pdf | 1 | 1 | 0 | TIE |
| MBSEL-14 | hi->en | pdf | Act 2. panch-parmeshwar-by-munshi-premchand.pdf | 47 | 1 | 46 | BGE_GAIN |
| MBSEL-15 | mr->en | pdf | Act 2. panch-parmeshwar-by-munshi-premchand.pdf | 20 | 1 | 19 | BGE_GAIN |
| MBSEL-16 | en->en | js | server.js | 1 | 1 | 0 | TIE |
| MBSEL-17 | hi->en | js | server.js | 8 | 1 | 7 | BGE_GAIN |
| MBSEL-18 | mr->en | js | server.js | 2 | 1 | 1 | BGE_GAIN |

### Major BGE gains

- MBSEL-14: rank 47 → 1.
- MBSEL-02: rank 34 → 1.
- MBSEL-15: rank 20 → 1.
- MBSEL-11: rank 11 → 1.
- MBSEL-08 and MBSEL-17: rank 8 → 1.

### BGE regressions

None in rank, R@1, R@5, or R@10 on this Golden set.

## Runtime

- ms-marco: 900 pairs, 5.47s, peak allocated 117,798,912 bytes.
- BGE: 900 pairs, 168.08s, peak allocated 2,875,100,160 bytes, peak reserved 3,602,907,136 bytes.

## Failure attribution

- Candidate retrieval: MBSEL-03 only at K50.
- Reranker: ms-marco leaves ten K50-present targets below BGE; BGE has no K50-present target below rank 1.
- Relevance/mapping: none; all targets resolve uniquely by manifest hash to canonical document/version.
- Infrastructure: none; complete CUDA execution with zero OOM retries.

## Promotion decision

**PROMOTE_BGE.** This is an evidence-based recommendation, not an automatic production mutation. BGE dominates the protected corrected Golden A/B (10 wins, 0 losses) and also improved all aggregate Phase 8.6 metrics. A controlled production-promotion validation should now verify configuration/alias binding, rollback, and the eight known Phase 8.6 rank-1 regressions before changing the active reranker.

## Production safety

No corpus, Golden Dataset, canonical DB, FTS, corpus embedding, chunking, ContextBuilder, production candidate K, model revision, or active alias was modified. No production promotion was performed.
