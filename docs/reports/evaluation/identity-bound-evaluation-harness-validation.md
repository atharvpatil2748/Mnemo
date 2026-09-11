# Identity-bound evaluation harness validation

Date: 2026-09-04. Final status: **HARNESS_READY_FOR_GPU_AB**.

**Full benchmark: NOT RUN. Production changes: NONE.** This status establishes the requested harness validation gates, not retrieval quality, production promotion, public exposure, or active V2 serving parity. Separate authorization is required to run the 70-query A/B.

## 1. Authoritative relevance identity

The relevance unit is a canonical **document/version pair within the manifest notebook**, evaluated at chunk-ranked positions. Any chunk from that document/version is relevant. The first relevant chunk determines rank; multiple relevant chunks do not create extra credit. There is no chunk-specific qrel or silent deduplication into a document-ranked list. Recall@K is the single-target hit indicator; MRR is reciprocal first-hit rank within the candidate pool; nDCG@10 uses the first-hit, single-document target convention retained from the historical evaluation.

`resolve_target_identity(qid)` follows:

1. One query with that QID.
2. One existing ingestion-manifest record selected by the query's external source label.
3. Actual source-file SHA-256 equals the manifest digest.
4. Exactly one document version with that content hash and notebook source membership.
5. Nonempty relevant chunk set with exact document/version lineage.

The filename is only a manifest lookup key. `candidate_matches_target` never uses candidate title or filename to decide relevance. Its immutable target includes QID, source ID, notebook ID, document ID, version ID, content SHA-256 and manifest SHA-256. Missing/ambiguous targets or scope inconsistencies fail closed. Different queries may legitimately target the same document/version; that is not ambiguity.

## 2. Existing mechanisms and scope

- Comprehensive: `execute_comprehensive_evaluation.py` compares exact parsed metadata titles to query filename labels.
- Canonical: `run_canonical_production_pipeline.py:323` stores source filenames in `doc_titles`; line552 applies bidirectional filename substring matching.
- Forensic: `run_forensic_analysis.py` uses a hardcoded Phase8.6 document-ID map, with legacy title fallbacks elsewhere, and imports historical canonical ranks.

No historical script was modified or executed. The new harness is an evaluation-only canonical NPZ/FTS comparator, not a new production retrieval service. It does **not** claim to exercise FullMultilingualRetrievalApplicationV2 or its active alias resolver. Model identities are read through MnemoConfig, ModelProfileDocument, and the existing production reranker constants. Canonical SQLite/NPZ identity is explicitly recorded; no historical generation UUID is hardcoded or selected.

## 3. Mapping validation

**70/70 resolved; 0 ambiguous; 0 unresolved.** Every row records query text, source/document/version identity, manifest/content hashes, number of relevant chunks, and example chunk IDs/titles. All loaded candidate identities are backed by exact document-version joins and notebook source membership.

Artifact: `scratch/identity_bound_mapping_validation.json`.

## 4. Historical discrepancy, without inference

The saved comprehensive top candidates were resolved by chunk ID against the unchanged DB. Applying the three mechanisms to those same candidates gives:

| Mechanism | ms-marco saved top hits | BGE saved top hits |
|---|---:|---:|
| Exact metadata-title equality | 8/70 | 8/70 |
| Canonical filename-substring rule, with manifest-bound filenames | 19/70 | 19/70 |
| Canonical document/version equality | 19/70 | 19/70 |

The separate historical canonical artifact reports24/70. Thus `24-8 = (19-8)+(24-19)`: eleven demonstrable matching misses plus a five-count residual between distinct experiments. The residual is **not** assigned to pool size, reranker quality or embedding weakness: canonical candidate identities were not saved, and that run used Top-40 and filename-context text. All differing QIDs and saved candidate/target identities are retained in `historical_matching` in the validation JSON.

This diagnostic is not a rerun or a promotion-quality comparison.

## 5. Candidate generation and fairness

The configurable `candidate_protocol` makes a previously hidden discrepancy explicit. Validation used **forensic-v1**, reusing the exact existing forensic `clean_fts_query` helper through AST extraction without importing/executing its runner. The forensic helper quotes up to15 lexical tokens; comprehensive-v1 has different normalization/token handling and is an explicitly different experimental protocol. No FTS5 schema, index or production query implementation was modified.

Both protocols retain RRF k=60. For K=25/50/100, the historical stage truncates dense and lexical source lists to K, fuses them, then retains K hybrid candidates. Therefore K is the common retrieval-source and pre-rerank depth—not merely slicing a fixed, larger RRF pool. Ties retain deterministic source order as in the historical implementation.

Saved query embeddings were reused with their ordered query-text digest checked. Corpus embeddings were not recomputed. Shapes, finiteness, normalization, complete corpus chunk-ID membership, and notebook scope were validated. The artifact records the query-cache and corpus-vector SHA-256 values; query-cache provenance is the prior recovery producer, not a fresh provider claim.

For every query and K the JSON stores dense, FTS, hybrid and pre-rerank IDs, complete candidate identity/text records, exact provider texts, and a pool digest. It includes complete Top-50 candidate lists.

The benchmark function constructs pools once, then sequentially passes the same query/candidate/text/target serialization to both rerankers. `identical_pools` raises `INVALID_EXPERIMENT` on any difference; a hard equality assertion is also present. The shared Mnemo `render_contextual_provider_text` is reused unchanged. Canonical chunk text is never rewritten. Only ordering/scores can differ between models.

## 6. K25/K50/K100 coverage

| K | Target entries | Coverage |
|---|---:|---:|
| 25 | 54/70 | 77.14% |
| 50 | 60/70 | 85.71% |
| 100 | 62/70 | 88.57% |

All210 per-query/per-depth target ranks match the saved forensic traces; there are no differing QIDs. The independently manifest-bound identity matches the historical Phase8.6 target IDs.

Previous16 Stage-A cases: DQ02, DQ03, DQ04, DQ05, DQ06, DQ10, DQ11, DQ12, DQ28, DQ31, DQ54, DQ55, DQ59, DQ60, DQ61, DQ62.

- Newly in pool at50: DQ11, DQ28, DQ31, DQ54, DQ61, DQ62.
- Two additional at100: DQ10, DQ55.
- Eight remain absent at100.

These are pool-entry results only. Top-50 was supported and validated, **not promoted**.

## 7. Unit/synthetic validation

**16 tests passed**, with no GPU/model dependency:

- Target at1,5,10 and11; target absent.
- Multiple relevant chunks count by first hit.
- Identical titles across different documents do not establish relevance.
- Same document/different version is not relevant.
- Missing identity, missing typed target, wrong notebook and duplicate chunk fail closed.
- Immutable target identity.
- Candidate equality rejects text/order changes.
- K25/50/100 behavior and deterministic RRF.
- Metric aggregation and rejection of zero denominators.

Commands executed:

```powershell
.\scratch\.venv-gpu-preflight\Scripts\python.exe -m unittest discover -s scratch -p test_identity_bound_evaluation.py
.\.venv\Scripts\ruff.exe check --select F,E9 scratch/execute_identity_bound_evaluation.py scratch/test_identity_bound_evaluation.py
.\.venv\Scripts\python.exe -m compileall -q scratch/execute_identity_bound_evaluation.py scratch/test_identity_bound_evaluation.py
```

All passed. JSON parses,70 unique pool QIDs, smoke pair count1, protected-state equality, and full_benchmark_run=false were independently asserted. No production regression suite or full retrieval-quality benchmark was claimed.

## 8. CUDA smoke test

The same loader used by the new benchmark was exercised after complete mapping/pool validation. Exactly one synthetic, non-corpus pair was passed to BGE-reranker:

- Query: `What color is the test square?`
- Evidence: `The test square is blue.`
- Model: BAAI/bge-reranker-v2-m3.
- Revision: `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`.
- Explicit device: `cuda:0`.
- Finite score: `0.9974802136421204`.
- Load/score measurement:10.0931 seconds.

Result: **PASS**. This score is only a wiring/finite-output check, not accuracy evidence. Model references were released, garbage collected and CUDA cache emptied; the process ended. No70-query reranking, Phase8.5 run or A/B comparison occurred. ms-marco was not separately smoke-inferred; its configured snapshot identity was validated and remains a future A/B participant.

## 9. Environment and reproducibility

- Isolated Python3.12.10 at `scratch/.venv-gpu-preflight`.
- PyTorch2.13.0+cu130; CUDA13.0; RTX4060 Laptop GPU.
- sentence-transformers5.7.0; transformers5.15.0 from uv.lock.
- BGE-M3 revision `5617a9f61b028005a4858fdac845db406aefb181`.
- ms-marco revision `233902d25c440f23af6f7d6e94d2946bac0bee0a`.
- DB SHA-256 `dc9e7fa2d1cb77f0e42ec3220377f74b1e2f98842acbfe487d1c7e6502fb2ada`.

Timestamp, Git commit, DB path/digest, query-set hash, manifest hash, vector hashes, K, protocol, model revisions, device/runtime and complete protected hashes are in JSON. Existing workspace changes predate this task and were not reverted.

Initial model discovery correctly rejected duplicate BGE cache roots. The successful run explicitly selected the existing `D:/Mnemo/phase8.5.11-models/huggingface/hub` cache containing all three exact revisions; no arbitrary 'latest' snapshot was selected. No model was downloaded or replaced.

## 10. Production safety

**399 protected files compared before/after with identical SHA-256 values**, covering source-corpus/Golden files, application source, configuration, selected model snapshots, DB/WAL/SHM, corpus embeddings and lockfile. The SQLite connection uses mode=ro, query_only=ON and a consistent read transaction. Integrity/FK checks pass; data_version and DB hash checks detect intervening writes. No writes were observed.

No active reranker/alias change; no BGE-M3, embeddings, FTS5, corpus, Golden Dataset, ContextBuilder, parser/chunking or production pool configuration change. No engine initialization, indexing, corpus embedding or model download. The one authorized synthetic reranker smoke pair is the only model inference in this task.

## 11. Files

- `scratch/execute_identity_bound_evaluation.py`
- `scratch/test_identity_bound_evaluation.py`
- `scratch/identity_bound_mapping_validation.json`
- `scratch/identity_bound_harness_validation.json`
- `docs/reports/evaluation/identity-bound-evaluation-harness-validation.md`

The harness-validation JSON is large because full candidate evidence/text is retained for all three pool depths rather than saving only ranks.

## 12. Authorization boundary and exact next task

**HARNESS_READY_FOR_GPU_AB. Full benchmark execution is NOT authorized by this implementation task and was NOT RUN.** Production-serving parity and promotion are not established by harness readiness.

Next task: explicitly authorize the corrected70-query paired GPU experiment using the frozen forensic-v1 candidate protocol, same shared Top-50 pools and both rerankers. The command below is provided for that later authorization; it was not executed:

```powershell
.\scratch\.venv-gpu-preflight\Scripts\python.exe scratch/execute_identity_bound_evaluation.py --mode benchmark --candidate-protocol forensic-v1 --candidate-pool-k 50 --reranker both --device cuda --model-cache D:/Mnemo/phase8.5.11-models/huggingface/hub
```

That future mode writes `scratch/identity_bound_benchmark_results.json`, separately from historical evaluation evidence. Do not describe a future comparison against the old comprehensive protocol as a pool-depth-only causal experiment: its lexical query preparation differs. No contextual representation experiment or production promotion should start automatically.
