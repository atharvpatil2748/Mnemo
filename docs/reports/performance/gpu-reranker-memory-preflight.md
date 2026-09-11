# GPU Reranker Memory Preflight

**Date:** 2026-09-05 (Asia/Calcutta)  
**Status:** `GPU_BATCHING_READY`  
**Scope:** memory-safe inference and bounded stress testing only; the 70-query benchmark was not run.

## 1. Exact OOM cause

The failed run reached `CrossEncoder.predict` for `BAAI/bge-reranker-v2-m3` and attempted to score 50 unchanged candidates in internal batches of 16. The model is a float32, 24-layer XLM-R sequence classifier with 1,024 hidden dimensions, 16 attention heads, and an 8,192-token configured sequence limit. Real Phase 8.6 contextual candidate pairs are long: the stress sample contained pair lengths through 5,025 tokens.

The proximal failure was therefore the simultaneous GPU activation workload from a fixed batch of 16 long, padded sequences. CUDA reported no free memory while attempting an additional 1,619,001,344-byte allocation. The failure happened inside model inference, after successful model loading; it was not an embedding, candidate-pool, relevance, database, or CUDA-installation failure. The exact internal tensor named by CUDA is not available in the crash artifact, so no narrower tensor-level attribution is claimed.

## 2. GPU and model

- GPU: NVIDIA GeForce RTX 4060 Laptop GPU
- Reported total device memory: 8,585,216,000 bytes (8,188 MiB)
- PyTorch: 2.13.0+cu130
- CUDA runtime reported by PyTorch: 13.0
- Model: `BAAI/bge-reranker-v2-m3`
- Revision: `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`
- Local governed snapshot was reused; there was no download or model change.
- CrossEncoder/tokenizer sequence limit: 8,192 tokens. No new truncation or semantic-text transformation was introduced.

## 3. Batching remediation

`execute_identity_bound_evaluation.py` now accepts `--reranker-batch-size {1,2}`, defaulting to 2. Prediction is split explicitly into ordered micro-batches. If CUDA OOM occurs at 2, the failed batch is retried with the same pairs and order at 1 after guarded synchronization, garbage collection, and `torch.cuda.empty_cache()`. It never falls back to CPU and never raises the batch size. An OOM at 1 terminates with `GPU_BATCH_OOM_UNRECOVERABLE`.

The candidate fingerprint/equality assertion remains before inference for both rerankers. Query text, candidate identities, ordering, semantic text, relevance identities, K=50, model revisions, and scoring order are unchanged.

## 4. Real-data stress test

Six exact K=50 provider-text pairs were selected from the validated Phase 8.6 pools: shortest, median-length, longest-by-character, and long native English, Hindi, and Marathi cases. This included PDF, HTML, and JSON material. It did not perform retrieval or generate a ranking.

Raw tokenizer lengths were: 47, 638, 4,916, 4,911, 4,210, and 5,025 tokens. The longest text by characters was 12,936 characters; the largest tokenized pair was the Marathi HTML case DQ23 at 5,025 tokens.

| Requested batch | Result | Successful batches | OOM retries | Peak allocated | Peak reserved | Time |
|---:|---|---:|---:|---:|---:|---:|
| 1 | PASS | 6 | 0 | 2,507,330,048 bytes (2.34 GiB) | 2,810,183,680 bytes (2.62 GiB) | 3.79 s |
| 2 | PASS | 3 | 0 | 2,940,454,912 bytes (2.74 GiB) | 3,607,101,440 bytes (3.36 GiB) | 4.28 s |

Maximum tested and successful batch size: **2**. Batch 16 was deliberately not retried.

## 5. Score determinism

The same six pairs were scored in the same order at batch sizes 1 and 2. Maximum absolute score difference was `6.556510925292969e-07`, below the declared `1e-5` tolerance. Result: **PASS**.

## 6. OOM fallback

The retry state machine was exercised using controlled fault injection: a fake predictor raised the same CUDA-OOM-shaped exception for a two-pair call and accepted one-pair calls. The helper cleared cached state, retried the exact inputs in order at batch size 1, returned two scores, and recorded one OOM retry. Result: **PASS**.

This was a control-path test; the real BGE batch of 2 did not OOM. The GPU was not intentionally exhausted a second time.

## 7. Checkpoint and failure behavior

The previous harness retained all records in memory and wrote only after both rerankers finished. The revised benchmark creates a separate `INCOMPLETE` checkpoint and atomically updates it after every completed query. It records completed rows and per-reranker timing/memory diagnostics. A complete final artifact is written separately; an interrupted checkpoint cannot be mistaken for a complete benchmark. No previous valid benchmark artifact is overwritten. The production benchmark was not invoked while validating this behavior.

## 8. Validation

- Existing identity harness unit tests: 16 passed.
- Python compilation: PASS.
- Ruff fatal/error checks (`F,E9`): PASS.
- `git diff --check` for changed harness files: PASS.
- Exact candidate-input digest before/after stress scoring: identical (`89f8bb0ec9af761896a08c9e920ca2b15dd7ec1c63634eebaedd99bb96229f37`).
- Candidate protocol remained `forensic-v1`; pool depth remained K=50.
- Full benchmark: **NOT RUN**.

## 9. Production safety

Only evaluation scripts and this report/artifact were changed. There was no production configuration change, reranker promotion, alias change, database write, embedding/index generation, FTS modification, corpus/Golden Dataset change, ContextBuilder change, CPU fallback, or provider inference beyond the expressly authorized small BGE stress set. The canonical DB remains externally open, so Windows `Get-FileHash` could not reacquire it; this task never opened or wrote it. Its last verified governed preflight SHA-256 remains `dc9e7fa2d1cb77f0e42ec3220377f74b1e2f98842acbfe487d1c7e6502fb2ada`.

## 10. Authorization for the subsequent run

The memory preflight supports a later full GPU A/B at batch size 2, with automatic reduction to 1. That full run is **not part of this task** and was not launched. Final status: **`GPU_BATCHING_READY`**.
