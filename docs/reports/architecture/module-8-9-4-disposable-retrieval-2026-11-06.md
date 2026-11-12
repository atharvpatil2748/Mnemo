# Module 8.9.4 — real disposable retrieval milestone

Date: 2026-11-06. **Module status: PARTIAL.** This report follows the [DERE preflight](module-8-9-4-dere-evidence-2026-11-06.md), without revising either conflicting historical `P85-EVAL-ENMR-001` record. The run is a one-case deterministic engineering measurement, **not** human-adjudicated semantic relevance or production/provider certification.

## Provider availability and admission

The [machine-readable availability matrix](../../../evaluation/module_894_dere/provider_availability_2026-11-06.json) separates real local query probes from notebook-bound admission. The existing offline probe `scratch/phase8_5_full_multilingual_v2/configuration_package/provider_probe.py` exited **1** after its BGE stage because its reranker call passes an obsolete `actor_id` argument to `RerankerCandidateBuilderV1.build`; this is harness/API drift, not evidence that BGE failed. The task-specific [read-only provider probe](../../../scripts/probe_module_894_local_providers.py) then independently completed:

| Provider / revision | Representation; query / asset | Language; dimensions; metric / norm / space | Observed readiness | Disposable admission |
|---|---|---|---|---|
| SQLite FTS5 canonical source, current code | Canonical text; real query executed / N/A | Token-based; no dense dimension or semantic cross-language guarantee | Composed on cloned SQLite store; ten ranked results | **Admitted** with explicit ACL; target missed. |
| BGE-M3 `5617a9f61b028005a4858fdac845db406aefb181` | Multilingual text; real offline query encoded / N/A | Declared en/hi/mr; 1024; cosine / L2; space `7dcba654e1c947145253ff65ef93e2b4ef1105cdf680b79218a446c79cc1a0d7` | **Loaded and queried**, exit 0, norm 1.0000000423 | **Not admitted**: frozen snapshot has no active `language_text_v2` generation or governed alias. Query readiness alone is not source/version admission. |
| CLIP `32bd64288804d66eefd0ccbe215aa642df71cc41` | Visual vector; real local text-tower query / asset tower not probed | 768; configured cosine, query L2 norm 0.9999999404; asset shared space unverified | Query side loaded and encoded, exit 0 | **Not admitted**: no active matching visual alias, verified asset vector space, or image DERE target in this fixture. |
| PaddleOCR package 3.4.1 | OCR derivation; no inference executed | Detection and Devanagari recognition directories exist; exact tree hashes and output language unverified | **Not proven ready** by model load/inference | No active OCR generation or validated OCR DERE case. |
| `qwen2.5vl:latest`, local Ollama ID `616d67811505` | Vision; listed by already-running local service / no inference executed | Governed revision and language behavior unverified | **Present, not operationally proven** | No active Vision generation or validated Vision DERE case. |

No Ollama service, tunnel, production provider, or production alias was started or activated. The older `scratch/phase8_5_wp10_remediation/eval-20260829-02` store has a ready/active *legacy* `multilingual_embedding` generation with complete receipt, but a different `source_id` and no `language_text_v2` generation. It was inspected read-only and was **not** substituted for the frozen DERE store or activated. The separate Vision/visual canary has ready but inactive generations; ready is not active.

## Disposable environment and exact query

The source is the frozen isolated `scratch/phase8_5_11/eval-20260825-02` snapshot. Its source-manifest digest and source→notebook/document→version→chunk/text joins passed the prior [read-only preflight](../../../evaluation/module_894_dere/preflight_result.v1.json). This task additionally read-hashed, without modifying, the declared `goldenDataset/Phase 8.5 Evaluation Corpus/manuscript.pdf`: SHA-256 `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085`, matching the frozen DERE case and persisted document version.

An immutable read-only SQLite backup created `scratch/module_894_disposable/eval-20261106-01/mnemo.db`; the protected snapshot was not opened for writing. A separate disposable `acl.db` explicitly granted owner role to test actor `7ee69849-d87e-57d1-b2ef-29128d668a5e` for notebook `df9c20cf-85fe-529c-902e-2e9e68193fbe`. No legacy owner was inferred. The [runner](../../../scripts/run_module_894_disposable_canonical.py) uses real `SQLiteStore`, `SparseRetriever`, `CanonicalTextAdvancedSource`, `AdvancedRetrievalService`, `SharedSearchApplicationService`, and `ScopedSearchApplicationService`, with the existing SQLite membership authority. Its thin engine-shaped test harness is **not** a deployed `KnowledgeEngine` or transport adapter. It opens/migrates **only the disposable copy**. It passes `representations=None` (no hints) and the exact frozen query:

> How did the author spend their sixth grade year according to the personal reflection?

The final [machine-readable ranked result](../../../scratch/module_894_disposable/eval-20261106-01/dere-canonical-result-v4.json) contains all ten candidate/source/document/version/chunk identities, retrieval paths and RRF fused scores; it contains no source text. The target chunk `523c5c88b522ce818212ffc42241706b731a767bb4dc5045ffa1a99e3392a0ca` is **absent** from top ten. All **10/10** returned items independently rejoined to the authorized notebook, source, document, version, and chunk in the disposable store. The result's nested `source_snapshot_preflight` records the *original* unmodified snapshot's lack of ACL/aliases; it is not the status of this later disposable run.

| Rank | Chunk ID | Fused score |
|---:|---|---:|
| 1 | `4c39520ae9e2cc6e7f658f42cd393d890a7feda1846373c04c5ad9bd6571f5fe` | 0.0163934426 |
| 2 | `8cfbbd9771c42ccc1d430ae5ead3cb91fc11b498a9c64258c68a0c32dcf2579f` | 0.0161290323 |
| 3 | `682a7393456bc9e38c7aa20cdea728d1206ce2cc1213f386d253e28a2897c9f6` | 0.0158730159 |
| 4 | `9c0d67194e2740faac2b179c48dc0f40f91ce921822ac941c319d9b23a5d3940` | 0.0156250000 |
| 5 | `e86cce458258216984b920b3a2904bc3c29498332ace47936fde0412cb208162` | 0.0153846154 |
| 6 | `f8767254d4ddb061ffd6ca32e05a280d49e14d747387fc4fdb018b180cdbda15` | 0.0151515152 |
| 7 | `937817faefa2bf2aa1f5f18a4303f6f15db0f0fada61a0e570fa8d37b6ed7870` | 0.0149253731 |
| 8 | `87844586a0defafd84603221a20ec4b01cab37b4449fd67b103ed5833412c704` | 0.0147058824 |
| 9 | `d4a58bd9f4e9a64e325f85f60d637fa9a7c16d80635cd96d802d495684cebad6` | 0.0144927536 |
| 10 | `254f76f9fe73883a2f70b27115bdeb6dbcc8d08398c9390096e66d1ffdda8716` | 0.0142857143 |

For this **one declared target identity**, Recall@10 = **0**, Precision@10 = **0**, MRR = **0**. These are engineering identity metrics, not a population quality estimate. The run also proved safe denial on an ungranted principal, nonexistent notebook, and wrong version; a disposable reader could retrieve before revocation and was denied afterward. The ACL revision advanced to 5; the disposable grant table retains only the active owner. Already-delivered results cannot be recalled. There is no claim of deployment/client parity.

## Acceptance matrix and next gates

| Roadmap task | Current status | Exact remaining evidence |
|---|---|---|
| 8.9.4a | **PARTIAL** | BGE and CLIP query-side probes are real, but the frozen notebook has no active complete Full V2 `language_text_v2` or visual generation. Build a compatible generation and coverage/alias **only in a new disposable copy**, prove language/model revision/metric/normalization/shared-space admission against source versions, then run positive and incompatible-provider tests. Do not promote the older legacy BGE alias. |
| 8.9.4b | **PASS (existing internal fixture gate)** | Keep bounded fan-out regression tests; this one-notebook run does not replace multi-notebook evidence. |
| 8.9.4c | **PASS (existing internal fixture gate)** | Keep signed aggregate cursor and membership-preserving fusion regression tests. |
| 8.9.4d | **PARTIAL** | The first genuine authorized no-hint canonical run is measured, but the frozen target missed top ten. A real Full V2 cross-language generation/query is needed for the en→mr case; OCR/Vision/CLIP need independent validated targets and active compatible sources. Human semantic adjudication remains absent and is never claimed. |

No admission code was changed: a suitable active Full V2 generation/alias for the frozen case is not present, so a purported real provider compatibility test would be fabricated. The existing focused admission/ACL regressions were rerun; code correction must start with a reproducible failing test once a genuinely active disposable mixed-provider fixture is available. No public contract or existing single-notebook cursor changed. The full configured suite was not rerun for these evaluation-only scripts; the prior 3,354-pass/90.017973% run is historical, not a new result.

## Verification and safety

Commands and outcomes for this task: the original offline provider probe exited **1** due obsolete reranker builder arguments; `.venv/Scripts/python.exe scripts/probe_module_894_local_providers.py bge` and `clip` each exited **0**; the final disposable no-hint runner with `--source-file` and exclusive `--output` exited **0**; `.venv/Scripts/python.exe -m pytest -q -o addopts='' mnemo-server/tests/test_module_894_scoped_search.py mnemo-server/tests/test_module_893_shared_search.py tests/test_module_894_dere_preflight.py` passed **59** with one pytest-cache permission warning (diagnostic override, not coverage gate). `.venv/Scripts/python.exe -m ruff check .` passed, `.venv/Scripts/python.exe -m ruff format --check .` passed (615 files), `.venv/Scripts/python.exe -m mypy --strict mnemo-core/mnemo mnemo-server/mnemo_server plugins/email-ingestion/email_ingestion scripts/verify_module_894_dere.py scripts/probe_module_894_local_providers.py scripts/run_module_894_disposable_canonical.py` passed (324 files), compilation of those three packages and three scripts passed, and `git diff --check` passed. The first exploratory strict-mypy run caught an untyped library call in the new CLIP probe; it was annotated consistently with the existing adapter and the final gate passed. No full coverage suite was rerun for these evaluation-only scripts; the prior 3,354-pass/90.017973% result is historical, not a new result.

Post-run inspection still found **zero active generations in the disposable clone**; no derived provider alias was silently activated. The original evaluation source-file SHA-256 and source-manifest SHA-256 matched their pre-run values. Production remains `UNINDEXED`; its runtime database path remained absent. No production alias/index/migration, credential, tunnel, or `goldenDataset/` mutation occurred. The disposable files remain local under `scratch/module_894_disposable/`; no files were staged, committed or pushed. Module 8.9.5 was not started.
