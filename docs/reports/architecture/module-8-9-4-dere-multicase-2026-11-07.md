# Module 8.9.4 — DERE-2 multi-case ranking baseline

**Internal engineering evidence; module PARTIAL.** No ranking policy, weights, application code, public API, cursor format, or generation changed. This extends the [frozen-case investigation](module-8-9-4-fusion-investigation-2026-11-06.md). It does not establish semantic relevance for human users.

## What was frozen and verified

The [version 2 manifest](../../../evaluation/module_894_dere/manifest.v2.json) was written **before** these retrievals. It binds its predecessor, the source manifest, proposed inventory, and disposable alias by digest. Version 1 and both historical case-ID records remain unchanged. The original English→Marathi query and chunk were carried forward literally. Additional queries and target IDs come from the pre-existing inventory; no provisional grade or reviewer status was transferred. One separately labelled compound control concatenates two predeclared questions with different expected chunks. It is not an independent single-target query.

The six cases have seven declared chunk targets in four documents. The run verified exact notebook/source/document/version/chunk joins, document-version SHA-256, source file bytes against the original manifest, and UTF-8 chunk-content SHA-256. The [portable summary](../../../evaluation/module_894_dere/benchmark-summary.v2.json) independently checks each query/target against its recorded inventory origin. The source universe used to verify trace rows comprised 2,698 identities in the authorized notebook, including typed derived evidence joined to the occurrence and derivation records. Every serialized stage row and final item had to pass the notebook/source/document/version/evidence identity check; this is not authorization to export text.

**English→Hindi was investigated and excluded, not scored as a miss.** The proposed record's document and version exist in the disposable notebook, but the declared OCR region has no occurrence/derivation join there and the active text projection contains no occurrence row for that document. A language tag on an unrelated Vision description is not a substitute. Standalone OCR, Vision and CLIP lack governed active-provider/target pairs for this benchmark. BGE text representations of some derived items do not certify those providers.

## How to reproduce and interpret the traces

Use the project interpreter, the existing local BGE revision and CUDA environment. Set `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`. From the repository root:

1. Run `.venv/Scripts/python.exe scripts/run_module_894_rank_benchmark.py dere-trace-<fresh-id>`. The [offline runner](../../../scripts/run_module_894_rank_benchmark.py) refuses existing destinations, copies only the checkpointed evaluation database, ACL and activation receipt from `eval-20261106-04`, verifies the copies, and reuses the existing Full V2 runtime composition. It neither regenerates embeddings nor activates aliases.
2. Run `.venv/Scripts/python.exe scripts/summarize_module_894_rank_benchmark.py scratch/module_894_disposable/dere-trace-<fresh-id>` for the JSON summary. It rechecks provenance, case origins, RRF contribution sums, stage metrics, and one-notebook final delivery. The [recorded experiment](../../../scratch/module_894_disposable/dere-trace-20261107-02/result.json) and six compressed traces are local artifacts. Their filenames and SHA-256 hashes are in the portable summary. A fresh run has fresh authorization receipts and latency; compressed-file hashes are receipts for that run, not a promise of byte-identical timestamps.

The [observer](../../../scripts/module_894_rank_trace.py) is **offline-only**, for a single principal, notebook and serial ranked request in an isolated Python process. It temporarily wraps real method calls, forwards arguments/results without scoring or fetching extra candidates, and restores the methods on exit. It has no transport switch, logging sink, streaming/cursor hook, or server import. Do not install its process-local wrappers in a concurrent serving process. Pre-limit references are held in memory during the diagnostic request. Only allowlisted IDs, paths/ranks, scores, counts, bounds, omissions and reasons are serialized after service success, ancestry checks and fresh scope revalidation. Denied requests are not exported. The receipt-bound manifest contains predeclared **queries**, but detailed candidate traces contain no query, snippet, source text, embedding vector, or credentials.

| Trace stage (arrays are in rank order unless noted) | What is measured |
|---|---|
| `dense`, `sparse` | Actual Full V2 provider pages, ranks, evidence identity digests; L2 cosine and negative SQLite BM25 respectively. Score scales are separate. The canonical sparse source page is available independently in advanced input. |
| `full_v2_rrf_before_limits` | Real digest-keyed merge scores before slicing, ordered using the implementation's score/digest tie-break; per-path contributions reconstructed from measured ranks using `1/(60+rank)`. Not an alternate policy. |
| `rerank_before_result_limit`, `full_v2_selected` | Actual rerank inputs/ordinals and returned scores, then Full V2 result order. This runtime uses the pass-through reranker. Budget fields distinguish fusion/rerank/output limits. |
| `advanced_before_dedup`, `advanced_after_dedup`, `combined_before_fusion_limit` | Membership-qualified identities and paths before/after candidate-ID merges and actual source-rank-strata ordering. Same-chunk views from different representations remain visible. |
| `advanced_before_output_bounds`, `advanced_selected`, `partitions`, `final` | Pre-output ordering after rerank/diversification, actual cut reason, per-notebook return and final output. The one-notebook child and final identity lists agreed in all six cases. |

The paired control compares the ordered result dictionaries, omissions and completeness with observation off/on. It validates and excludes **only** the fresh per-request authorization-decision fingerprint from equality; issue time/ID vary even across two uninstrumented calls. Source IDs, versions, generation, alias, other locator fields, content, scores and ranks remain in the equality check. An initial import mismatch was fixed; an initial strict byte-equality probe correctly detected the volatile receipt (`dere-trace-20261107-01` retained, not counted). The successful run used a fresh `-02` copy. The ungranted principal, nonexistent notebook and a real version belonging to the wrong document were all denied both ways with no released trace.

## Results with the existing policy

Ranks below refer to *declared evidence identities*. Multiple positions may be different representations of one identity. Credit is once per distinct target; precision denominator is 10; nDCG is binary, not a transferred semantic grade. All metrics, including canonical source-page results and rank positions at intermediate stages, are in the portable summary.

| Case (direction) | Full V2 sparse / BGE dense target ranks | Full V2 RRF rank(s) | Advanced combined rank(s) | Final top-ten rank(s) | Final Recall / Precision / RR / nDCG @10 |
|---|---|---|---|---|---|
| Frozen sixth-grade query (en→mr) | — / 1 | 7 | **13** | — | 0 / 0 / 0 / 0 |
| MRMR-002 (mr→mr) | 3 / 1 | 2 | 3,4 | 3,4 | 1 / .1 / .333 / .500 |
| ENEN-001 (en→en) | 301 / 2 | 33 | 8 | 8 | 1 / .1 / .125 / .315 |
| ENEN-004 (en→en) | 1 / 1 | 1 | 1,2 | 1,2 | 1 / .1 / 1 / 1 |
| ENEN-008 (en→en) | 1 / 40 | 3 | 2,5 | 2,5 | 1 / .1 / .500 / .631 |
| ENEN-005+006 (compound, en→en) | 12,32 / 3,34 | 1,6 | 1,10,11,125 | 1,10 (one distinct target) | .5 / .1 / 1 / .613 |

Descriptive macro across **only the five single-target queries** (four documents):

| Stage | Recall@10 | Precision@10 | MRR@10 | nDCG@10 |
|---|---:|---:|---:|---:|
| Canonical source page | .800 | .080 | .550 | .612 |
| Full V2 sparse | .600 | .060 | .467 | .500 |
| BGE dense | .800 | .080 | .700 | .726 |
| Full V2 RRF | .800 | .080 | .395 | .493 |
| Final scoped | .800 | .080 | .392 | .489 |

These are stage observations from the same requests, **not** a randomized or held-out policy comparison. For the frozen case, 1,000 dense and 1,000 sparse matches yielded 1,688 merged identities; the target was seventh in the 50-item rerank pool and seventh in the ten-item Full V2 output. It became **13/510** before advanced truncation, remained in the 50-item advanced rerank pool, then failed the child `result_limit=10`. This directly measures the position previously unavailable. In ENEN-001 the canonical view instead rescued a target that was outside the Full V2 top ten.

All six final lists exposed five canonical and five multilingual views, with no lineage/membership violations among exported rows. All stopped at the result limit and completed their observed scoped invocation in **6.95–8.26 s** within the configured **30 s** deadline. The configured candidate budget was 1,000 and requested-k was 10. This bounds the observed application result/pools at their respective stages; it is **not** a cap of 1,000 combined physical reads across nested providers (the two Full V2 lanes each use the configured recall limit). The diagnostic did not widen any plan. Only one notebook has real measured data; the existing multi-notebook fairness and signed-cursor fixture regressions were run, not reclassified as measured multi-notebook quality.

**Offline alternatives: insufficient evidence.** The manifest predeclared at least two independent source documents per compared language direction, plus multiple authorized notebooks for cross-notebook fairness. Both Marathi cases come from one document, the Hindi target is unbound, and only one notebook was exercised. The compound control is dependent and excluded from the macro. No alternative was selected, deployed, or evaluated as a winner. The next useful fixture is a second authorized Marathi source and notebook plus a verified Hindi source carrying its actual matching active projection, with independently declared targets. Human semantic adjudication remains outstanding.

## Verification and acceptance

The focused probe, existing DERE preflight and scoped-search regressions passed **54 tests**, exit 0 (one Windows pytest-cache access warning). The paired real-provider run exited 0 for all six cases, including all three on/off denial controls. The portable summary was recomputed from the six trace files and matched as a JSON object.

The configured full command `.venv/Scripts/python.exe -m pytest -q --cov-report=term:skip-covered --cov-report=xml:scratch/module_894_disposable/dere-trace-20261107-02/full-coverage.xml --junitxml=scratch/module_894_disposable/dere-trace-20261107-02/full-junit.xml` exited **0**: **3,360 passed, 6 skipped, 0 failed, 9 warnings**. Combined line/branch coverage was **50,133 / 55,701 = 90.003770%** against the unchanged 90% requirement. See [JUnit](../../../scratch/module_894_disposable/dere-trace-20261107-02/full-junit.xml) and [coverage](../../../scratch/module_894_disposable/dere-trace-20261107-02/full-coverage.xml). Ruff lint and formatting (622 files), strict mypy (three packages and four evaluation scripts, 325 source files), compilation and `git diff --check` each exited 0. Relative links resolved.

All **573 files** inventoried under the four original evaluation directories had identical before/after SHA-256 values. The production selector remained `UNINDEXED`; nothing was staged, committed or pushed. No production migration, alias activation, tunnel action, or Module 8.9.5 work occurred. **8.9.4a and d remain PARTIAL; b and c retain their internal PASS.**

## Separate tunnel finding (local, read-only)

PID 82188 is the unsigned `C:\Tools\tunnel-client.exe`, SHA-256 `7D3C7D492CE84B52835E11865A835A8A5BCD4A669DEE84E169AA11B314DC952A`. The process command names the `codexpro` profile; its parent is `wscript.exe C:\Tools\start-codexpro-hidden.vbs`, started by `svchost.exe` under `services.exe` and `wininit.exe`. The running **CodexPro Tunnel** logon task invokes that exact watchdog, which launches the client hidden and restarts it on exit. The separate **Mnemo Tunnel** task was Ready, not Running. This establishes the **local launch configuration** as CodexPro, not the Mnemo profile; it does not authenticate the binary's publisher.

The profile file is `C:\Users\athar\AppData\Roaming\tunnel-client\codexpro.yaml`; its configured HTTPS control-plane hostname is **api.openai.com**. The actual observed connection was to **172.66.0.243:443**, with a listener on **127.0.0.1:8081**. No local DNS-cache entry joined that IP to the hostname. Configuration is not TLS peer/SNI or downstream-account evidence: the hostname actually served by that socket and its ultimate tenant remain **unverified**. No network probe, process action, configuration edit, or credential operation was performed.
