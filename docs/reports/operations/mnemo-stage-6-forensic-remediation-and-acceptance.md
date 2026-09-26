# Phase 8.8 Stage 6 batch — forensic remediation and fresh local acceptance

**Date:** 2026-09-26. **Scope:** F-1/F-2 remediation and independent local reassessment of 8.8.5, 8.8.7, 8.8.2f, 8.8.4 and 8.8.8. This does not certify the running tunnel or close Stage 6.

## Authority and baseline

The current architecture §§21.2–21.8, engineering roadmap Module 8.8.2–8.8.11, and accepted ADR-0076/0077/0078 govern this pass. The prior [combined independent audit](mnemo-stage-6-combined-forensic-audit.md), its strict regressions, Stage 5 acceptance, and prior local/forensic module reports were inspected as point-in-time claims. Initial Git: `main...origin/main`, HEAD `069ec468a675c37544a5a2591eac1204c3cb6888`, 37 modified tracked and 17 untracked files, none staged. The accepted 8.8.5/8.8.7 and pending 8.8.2f/8.8.4/8.8.8 work was preserved.

Before product edits, `CI=true MNEMO_CI=1 uv run pytest -q -p no:cacheprovider --no-cov mnemo-server/tests/test_stage6_forensic_audit.py --runxfail --tb=short` yielded **four failures and two passes** on disposable old/new SQLite schemas. Two failures were `'failed' != 'searched'` for partitioned governed ranked retrieval; two were `KeyError: 'source_metadata'` on nested partition items. The two passing cases established only absence of cross-notebook content, not full partition authorization. No product fix was assumed from the earlier reports.

## Root causes and corrections

| Finding | Independent call-chain evidence | Correction | Regression closure |
|---|---|---|---|
| F-1, high | `EvidenceRetrievalApplicationService.execute` called `PartitionedRetrievalServiceV1.execute`; the latter called ordinary `AdvancedRetrievalService.execute`, which invokes the governed multilingual source without a principal. The nonpartitioned path called `execute_authorized`. | Added `PartitionedRetrievalServiceV1.execute_authorized` and shared traversal; production application dispatch passes only the server-authenticated principal. Explicit document partitions are checked against exact notebook/document/version ancestry before retrieval; unknown and inaccessible identities produce the same static `NotFoundError`. The old `execute` remains for nonproduction compatibility. | Both former old/new xfails became ordinary passes. The principal-only governed fixture now returns a nonempty multilingual canonical candidate on both nonpartitioned and partitioned requests; its unauthenticated method is never called. Mixed, foreign, unknown and version-mismatched partitions fail before source invocation; duplicates are invalid. |
| F-2, medium | `_partitioned_response` copied child results into both `items` and `partitions[].items`; `_with_authorized_metadata` enriched only `items`. | One authorized bounded `resolve_many` call uses the canonical top-level references. Its envelopes are projected by canonical reference into both views. The existing 200-reference resolver limit and serialized byte ceiling remain. | Both former old/new xfails became ordinary passes. Exact top-level/nested envelope parity, canonical source/document/version/chunk attribution, and nonempty same-fixture direct MCP/stdio/SSE/HTTP results pass. |

The earlier cross-notebook tests expected an empty success. The safer fail-closed behavior now raises `authorized resource was not found` before retrieval; those two tests were strengthened to assert that exact sanitized message and absence of foreign text/chunk identity. This is a justified security correction, not a weakened test. The four strict xfail markers were removed only after the product fixes passed with `--runxfail`; subsequent normal and `--runxfail` executions had no xfail/XPASS masking.

## Authorization, metadata and schema matrix

| Disposable variant and case | Observed local public result |
|---|---|
| Older schema, ranked governed source, explicit authorized document | `searched`, nonempty `multilingual_text` candidate with exact canonical IDs; principal-aware source called; top/nested metadata agree |
| Newer schema, same | Same contract |
| Older/newer canonical-text partition | Nonempty top/nested source envelope parity, exact document/version/chunk/source IDs; nullable legacy page metadata retained |
| Older/newer foreign or unknown partition | Static `NotFoundError`; no foreign text/ID; governed source not invoked |
| Older/newer mixed authorized/foreign, wrong version | Static `NotFoundError` before retrieval; no partial foreign hit/count |
| Older/newer duplicate partition | Bounded input failure before retrieval |

`test_source_metadata.py` separately exercises the resolver's 0/200/201-reference bounds, deduplication, duplicate filenames, nullable metadata, version changes and path suppression. The unchanged Stage 5 old/new public matrix and the new partitioned fixture exercise the actual MCP dispatch; `test_mcp_transport_contract_matrix.py` now includes both canonical and principal-only governed multilingual ranked evidence, partitioned and nonpartitioned, in nonempty direct MCP versus real local stdio and loopback SSE comparisons, and compares the existing HTTP `/v2/retrieval/evidence` route on the same fixture. No HTTP endpoint was invented. These fixtures prove adapter/principal propagation but do not assert a live multilingual model or external tunnel result.

## Complete 14-tool reassessment

The existing startup-validated `_TOOL_ROUTES` registry remains the actual registration/handler/scope map. No tool, handler family or route declaration changed. The full suite and focused same-fixture matrix re-exercise these applicable success and negative contracts:

| Tool | Route family | Reproduced public-path evidence |
|---|---|---|
| `list_notebooks` | Retained V1 | Nonempty authorized inventory, invalid limit |
| `get_notebook_summary` | Retained storage | Persisted summary, empty/unknown scope |
| `get_timeline` | Retained storage | Persisted event, empty/unknown scope |
| `get_source_insights` | Retained storage | Persisted insight, empty/unknown source |
| `search_all_notebooks` | Retained V1 | Scoped/global FTS, empty/unknown scope |
| `query_notebook` | Retained V1 | Authorized evidence and deterministic synthesis, invalid/unknown scope |
| `search_evidence` | Representation-specific V2 | Ranked/exhaustive and cursor tests; new nonempty governed ranked partition, metadata parity, mixed-scope denial |
| `get_capabilities` | Runtime V2 | Scope-qualified lifecycle and invalid capability |
| `query_structured` | Typed V2 | Authorized projection, unavailable/invalid |
| `get_document` | Shared V2 delivery | Fixture blocks/original, unknown/unavailable; production parsed representation not inferred |
| `get_document_chunk` | Shared V2 delivery | Exact chunk ancestry, mismatch/unknown |
| `get_asset` | Shared V2 delivery | Occurrence/original bytes, unknown |
| `get_image_analysis` | Shared V2 delivery | Persisted OCR/Vision reopened from disk, explicit/latest/all and unavailable |
| `run_final_qa_v2` | Certified V2 service | Deterministic fixture execution/citations and invalid/unavailable, disposable operational store |

The same-fixture transport test invokes all 14 tools through direct MCP, real stdio and isolated SSE; HTTP comparison is limited to actual counterparts. The new partitioned case is present in all applicable retrieval adapters. No live external or certified-model parity is inferred. The retained V1 search/query route and WebSocket semantics remain distinct from certified V2 FinalQA.

## V1/V2 fallback, typed errors and reader-error reassessment

Production partitioned retrieval now calls only the principal-aware V2 advanced retriever. Its unauthenticated method is a test spy that would fail if invoked, including in the disposable real-stdio and loopback-SSE child fixtures; no historical V1 store/model selection was added. Distinct-store/model production-composition mismatch and retained-V1 compatibility regressions remain in `test_production_storage_composition.py`, `test_mcp_v1_v2_routing.py`, HTTP/stdio/SSE startup tests and the full suite. The canonical sparse compatibility adapter remains a same-store authorized representation, not cross-store fallback. `query_notebook` remains retained V1; `run_final_qa_v2` remains certified-style V2 with a separate operational store.

The 8.8.7 typed-error and 8.8.2f nested reader-failure tests were rerun with the focused and full suites. The corrected foreign/unknown partition path uses the existing safe static `NotFoundError`; no raw SQL, path, token or exception detail was added. Earlier independent acceptance reports remain historical. This combined pass is the first independent assessment of 8.8.2f, not a retroactive separate audit.

## Validation, documentation and protected state

Focused forensic file with `--runxfail`: **8 passed, 0 xfailed**; focused matrix including metadata, typed errors, authorization, route/startup, old/new public MCP, direct/stdio/SSE/HTTP and partition unit tests: **186 passed, one existing deprecation warning**. A first full run after correction passed **2,694, skipped 18, warned eight, 90.29% coverage**. A second final full run after strengthening the governed-source fixture is recorded below.

Ruff lint, strict mypy (291 source files), compileall, `uv lock --check` (171 packages), three Python source/wheel builds, frontend format/lint/typecheck/test/build, three Docker Compose configuration checks, and `git diff --check` passed in this remediation pass. Ruff formatting initially found two new files and then one strengthened test file; all were formatted and rechecked. Docker image builds were not run because the local Docker Desktop Linux daemon was unavailable. The nonfatal dangling virtualenv `~nemo_server` dist-info warning was not cleaned up.

`docs/README.md`, current architecture and roadmap now distinguish Stage 5's historical 8.8.2f deferral from its subsequent local implementation and independent combined assessment. Dated follow-ups in the 8.8.5, 8.8.4 and 8.8.8 reports identify their missed partition cases without overwriting earlier verdicts/counts. The report index points to both the blocked audit and this correction. No accepted ADR was changed or new decision required.

The certified production DB baseline was SHA-256 `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`, 189,804,544 bytes, UTC mtime `2026-09-01T11:09:20.1047581Z`, no WAL/SHM/journal. WP16 was SHA-256 `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d`, 37,195,776 bytes, UTC mtime `2026-08-29T13:37:31.2308106Z`, no sidecars. Protected manifest, launcher and signed activation/certificate/final/convergence identities matched the combined audit's recorded hashes. Registry metadata named exactly one ACTIVE generation, `fc85192e-f672-4cc0-9539-b4b063bb8f41`. Final checkpoint values and verdict follow below.

## Acceptance and handoff

Final full-suite, protected-state and status results are recorded in the closing checkpoint below. Local acceptance requires the former xfails to pass normally, no new high/critical defect, passing all-tool and route regressions, at least 90% repository coverage and identical protected artifacts. Module 8.8.10a–c evaluation isolation and 8.8.11a–c structured-contract verification remain mandatory under canonical roadmap step 7, so this batch cannot close Stage 6. Module 8.8.9 live four-transport parity, 8.8.12 `search_images`, and final Phase 8.8 gates also remain separate.

The next external ChatGPT verification needs an explicitly authorized notebook with stable source/document/version/chunk identities and, for the fixed path, governed multilingual evidence availability. Before testing, a separately authorized deployment must establish source/build identity and four-transport startup convergence without changing the certified corpus. Fresh external calls should list the 14 tools and capabilities; compare nonpartitioned/partitioned ranked `search_evidence`, top/nested source metadata, exact retrieval/citations and safe negative scopes using designated test resources. Missing/forged credentials require a separate safe interface. Match external request IDs to sanitized server logs where available; do not infer per-request process identity from timestamps. Recheck protected hashes and sidecars. This report performs none of those external or deployment actions.

## Closing checkpoint and verdicts

The final exact-tree `CI=true MNEMO_CI=1 uv run pytest -q -p no:cacheprovider --tb=short --cov-report=term:skip-covered` exited 0: **2,694 passed, 18 skipped, 0 xfailed, 0 xpassed, eight warnings, 90.31% repository-wide coverage**, above the unchanged 90% floor. The four former strict xfails and two strengthened cross-notebook tests pass as ordinary cases on both schemas. The separate final forensic-file normal and `--runxfail` commands each reported **eight passed**. The final real direct MCP/stdio/SSE/HTTP same-fixture transport file, including nonempty principal-only governed multilingual partition responses, reported **six passed**. The broader focused cross-module matrix reported **186 passed, one deprecation warning** before the final governed transport-fixture extension; its subsequently strengthened cases were rerun in focused files and the final full suite. Warnings are existing Starlette/httpx deprecations, malformed openpyxl test dependencies, local Qdrant advice, and MCP/FastAPI deprecations. No test was skipped to avoid the corrected path.

Final `uv run ruff check .`, `uv run ruff format --check .` (523 files), strict mypy (291 source files), compileall, `uv lock --check` (171 packages), and `git diff --check` passed. The three `uv build --package mnemo-core`, `mnemo-server`, and `mnemo-email-ingestion` source/wheel builds passed. Frontend `pnpm format:check`, `lint`, `typecheck`, `test` (one passing test), and `build` passed. All three Docker Compose `config --quiet` checks passed. Docker image builds remain **unverified** because `docker version` could not reach the local daemon. Relative Markdown links in the eight changed documentation files resolved; current status lines no longer describe 8.8.2f as presently pending.

Post-gate protected identities matched the pre-edit values exactly: production DB SHA-256 `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`, 189,804,544 bytes, UTC mtime `2026-09-01T11:09:20.1047581Z`; WP16 SHA-256 `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d`, 37,195,776 bytes, UTC mtime `2026-08-29T13:37:31.2308106Z`. Neither DB had WAL, SHM or journal sidecars before or after. Manifest `e579727c8867c92d4ca7fe05256a35d74942077f86b86a6fad9938ff3b4fc566`, launcher `007ee235783cb8f673a2f9c135bc38269ba2a355057c5cd119c0125e471fde22`, signed activation `c17a7f5531cc75795fb63c6f53682d30eb6ed831127db95038d3d1741cd25525`, certificate `1a69e95796b98abcc1f4f6484692481058bff776b454a14e3a0b35d86f16312a`, final evidence `0255160992fc1ed2fdc5b5c6bfb55bb442b55018655f511274d698569a06230c`, and signed startup convergence `b5ccccb9787773ef10f5a6364bbc80ed98324640ea5438da604ebfaf2b7c2b23` were unchanged. Registry metadata still showed exactly one ACTIVE generation `fc85192e-f672-4cc0-9539-b4b063bb8f41`. No secret values were read into this report.

| Module | Fresh local forensic verdict | Basis |
|---|---|---|
| 8.8.5 | `MODULE_8_8_5_FORENSICALLY_ACCEPTED` | F-2 repaired; resolver bounds, canonical identity, nullable legacy metadata, old/new schema and top/nested public parity pass |
| 8.8.7 | `MODULE_8_8_7_FORENSICALLY_ACCEPTED` | Existing independent typed-error acceptance preserved by fresh public error, sanitization and correlation regressions |
| 8.8.2f | `MODULE_8_8_2F_FORENSICALLY_ACCEPTED` | First independent combined audit plus fresh older/newer nested reader-origin and public MCP/HTTP tests |
| 8.8.4 | `MODULE_8_8_4_FORENSICALLY_ACCEPTED` | All-14-tool public matrix and corrected governed ranked partition/metadata transport cases pass |
| 8.8.8 | `MODULE_8_8_8_FORENSICALLY_ACCEPTED` | Single route map, distinct backend startup tests, retained V1 compatibility and principal-aware partitioned V2 path pass without observed historical fallback |

**Cross-module integration and documentation:** accepted locally for this batch; no new high/critical defect was found. **Combined verdict:** `COMPLETED_BATCH_FORENSICALLY_ACCEPTED`. **Formal Stage 6 verdict:** `STAGE_6_CLOSURE_PENDING`; canonical roadmap step 7 still requires 8.8.10a–c and 8.8.11a–c. Phase 8.8 and production/external certification remain open. The historical blocked combined audit is not overwritten; this dated report records its remediation. The batch is ready for a separately authorized GitHub closure workflow, subject to actual publication/CI and required review; no GitHub closure occurred here.

Final Git: `main...origin/main` at `069ec468a675c37544a5a2591eac1204c3cb6888`, **41 modified tracked, 18 untracked, zero staged**. All earlier dirty Stage 6 work remains. This pass changed the partitioned core retriever, V2 retrieval application service, disposable immutable-schema fixture and transport matrix, strict forensic test, three current-status documents, three historical-report errata, report index, and this report. No commit, push, PR, deployment, production restart, tunnel restart, credential/configuration/active-generation change, or protected-store mutation occurred. External ChatGPT verification was not performed.
