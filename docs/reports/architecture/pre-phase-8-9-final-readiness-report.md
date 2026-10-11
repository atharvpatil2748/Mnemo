# Pre-Phase-8.9 final readiness report

Date: 2026-10-11. **Decision: NOT READY for an unqualified pre-Phase-8.9 readiness certification.** The current offline/unindexed safety baseline and source preservation are verified, but the CI-equivalent repository formatter gate fails on 38 pre-existing dirty source/test/script files. The separate Phase 8.9 authorization decision must not be inferred from this report. Phase 8.9 implementation, production indexing, tunnel restart, and credential reactivation did not occur in this task.

## Current implementation boundary

Production selection is explicit `UNINDEXED` in `config/production/runtime-selection.json`. `mnemo_server/services/production_runtime_selection.py:49` raises `PRODUCTION_CORPUS_UNINDEXED`; HTTP and MCP startup/request/dispatch paths call the guard before historical binding use. The old exact-identity V2 production/evaluation indexes were retired, not silently republished. `mnemo/corpus_identity.py` supplies path-independent logical corpus/deployment/index identity; `portable_corpus_runtime.py` is a read-only signed/publication/storage/generation inspector, **not** the current production indexed-serving path. `SQLiteNotebookScopeAuthority` persists explicit grants and `CentralAuthorizationServiceV1` checks them where installed. Future indexed multi-user onboarding and all-route enforcement remain unimplemented/uncertified; no actor gains access from a notebook ID or source-hash match alone.

The governed two-corpus rebuild and integrity modules are separate **isolated evaluation tooling**. They validate exact source manifests, runtime ownership, representation coverage, and activation for disposable targets. They do not activate or promote a production index. V1 canonical retrieval remains frozen; current automatic V2 remains bounded to one unambiguous notebook in suitable isolated data. The proposed shared, authorized cross-document/cross-notebook/multimodal/structured Phase 8.9 design in ADR-0080 has **not** started. Phase 9 remains blocked pending a later exact-identity Phase 8.9 GO.

## Historical decommission and protected state

The machine-readable receipts at `scratch/phase8_9_decommission/2026-10-10/full-store-execution.json` and `partial-rebuild-execution.json` record five exact allowlisted COMPLETE retirements: historical Full V2, shared canonical evaluation, registry Phase 8.5, registry Phase 8.6, and one owned partial rebuild. Their row deltas are 59,937, 35,067, 27,791, 29,285, and 29,322 respectively: **181,402 aggregate indexed-table rows**, not unique logical objects. The [execution record](phase-8-9-runtime-cutover-execution.md) provides notebook IDs, family counts, snapshots, alias retirement, FK/integrity/FTS verification and retained evidence. On this date, the base-file SHA-256 of all five databases matched their exact `after_sha256` receipt value; no live SQLite connection was opened merely to repeat counts. The evaluation registry has an empty `notebooks` object. No `data/notebook_runtime/mnemo.db` was present.

The exact 44-document and 24-document manifests were re-evaluated against **current original bytes** by `verify_source_manifest`: 44/44 and 24/24 matched, with identities `a915a7e4746841c6cd9c92b9b2a98abb46778928cd40387bbe4f9dac190abe85` and `67feeac521afa836646de6b727c23413ddf2216fb77ed25b0024b3be09539eee`. The 15 pre-existing deleted tracked files at the top level of `goldenDataset/` remain untouched and are distinct from these nested verified corpora. The non-secret credential registry still reports the historical generation `REVOKED` and no active generation. A process scan found zero matching `certified-tunnel-stdio` processes. These are point-in-time local checks; they do not certify external transport or every possible external launcher.

The former `scratch/.venv-gpu-preflight` (pre-deletion inventory: 3,428,879,387 bytes) is absent after the user's manual deletion. `scratch/audit_relevance_mapping.py` now validates/selects the main `.venv/Scripts/python.exe`, failing closed if it is missing. The main interpreter remains present and previously executed the optional tool's exact bounded CUDA probe on `cuda:0`. The earlier **bare** `pytest` attempt with unrecognized `--cov` options did not run tests: `Get-Command pytest` currently resolves to a global Python Scripts executable, while `.venv/Scripts/python.exe -m pytest --version` reports pytest 8.4.2 and its `pytest_cov` import reports 6.3.0. Focused post-deletion tests have passed through that intended interpreter. This does **not** establish equivalence to historical GPU reranker benchmark outputs.

## Verification commands and actual results

| Check | Command/evidence | Result |
|---|---|---|
| Manifest bytes | `.venv/Scripts/python.exe -B -c` invoking `verify_source_manifest` for both configured manifests/corpora | PASS, 44/44 and 24/24; exit 0 |
| Retired store protection | `Get-FileHash -Algorithm SHA256` on five exact DB files, compared with receipt `after_sha256` | PASS, 5/5 exact matches |
| Operational state | Selector JSON, non-secret credential lifecycle fields, tunnel process scan, evaluation registry inspection | PASS: `UNINDEXED`, revoked/no active generation, zero observed tunnel processes, empty registry |
| Main GPU replacement | Exact preflight CUDA code through `.venv` (recorded in `scratch/gpu_preflight_environment_removal_result.md`) | PASS, `cuda:0`, finite bounded tensor; no benchmark claim |
| Focused safety/identity/rebuild/interpreter tests | `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -o addopts=''` on seven focused test files | PASS, 91 passed, exit 0. Coverage intentionally disabled for this diagnostic run; it does not satisfy the normal coverage gate. |
| Full ordinary test suite and coverage | `.venv/Scripts/python.exe -m pytest -q --junitxml=scratch/pre_phase89_closure_junit.xml` with unmodified `pytest.ini` | PASS, exit 0: 3,058 passed, 5 skipped, 0 failed; combined statement/branch coverage 90.04% versus 90% gate; JUnit at the named path and `coverage.xml`. Nine warnings include an inability to write `.pytest_cache`; test execution and coverage still completed. |
| Repository Ruff lint | `.venv/Scripts/python.exe -m ruff check .` | PASS, exit 0 |
| Strict source typing | `.venv/Scripts/python.exe -m mypy --strict mnemo-core/mnemo mnemo-server/mnemo_server plugins/email-ingestion/email_ingestion` | PASS, 313 source files, exit 0 |
| Python compile | `.venv/Scripts/python.exe -m compileall -q` on the three source packages | PASS, exit 0 |
| CI-equivalent formatter | `.venv/Scripts/python.exe -m ruff format --check .` | **FAIL**, exit 1: 38 source/test/script files would be reformatted; 547 already formatted. No formatter was run. |
| Whitespace/diff and documentation links | `git diff --check`; targeted PowerShell relative-link verification across 11 changed/created docs; ADR filename-number uniqueness check | PASS, exit 0; 227 relative links checked, 0 broken; 0 duplicate ADR numbers. ADR-0080 remains Proposed, ADR-0081 Accepted. |

The 38 formatter failures are in pre-existing working-tree files outside this task's documentation edits, including `mnemo-core/mnemo/ocr_paddle.py`, `mnemo-core/mnemo/retrieval/advanced.py`, `mnemo-server/mnemo_server/services/portable_corpus_runtime.py`, `mnemo-server/mnemo_server/tools/legacy_decommission.py`, and related tests/scripts. They are a **real CI-equivalent gate failure**, not evidence that runtime tests failed. Bulk formatting would modify unrelated user work, so it was not performed. The full list was captured in the tool output of `ruff format --check`; a later owner-approved scoped formatting pass must preserve those changes and rerun the gate.

## Readiness matrix

| Requirement | Evidence/check | Actual result | Status | Next action |
|---|---|---|---|---|
| Explicit offline/unindexed production | Selector, HTTP/MCP guard paths, focused tests | `UNINDEXED`; no historical fallback in tested paths | PASS | Keep gate until separately authorized indexed publication. |
| Legacy five-store retirement | Exact receipts and five current hashes | All five match recorded post-reset state | PASS | Preserve snapshots/receipts; no rerun of executor. |
| Source preservation | Full source-manifest byte/SHA-256 verification | 44/44 and 24/24 | PASS | Recheck before any future build. |
| Credential and tunnel retirement | Non-secret lifecycle state and process scan | Revoked/no active; no matching tunnel process | PASS | Do not reactivate for this baseline. |
| Path-independent logical identity and isolated rebuild safeguards | `corpus_identity`, governed rebuild/integrity modules and focused tests | Implemented/tested in disposable scope | PASS | Do not infer production publication from fixture evidence. |
| Main environment after GPU venv removal | Target absent, main interpreter/CUDA, focused tests | Main replacement works; historical benchmark equivalence untested | PASS | Adapt only intentionally rerun historical commands. |
| Full ordinary test/coverage gate | Current full-suite run, `scratch/pre_phase89_closure_junit.xml`, `coverage.xml` | Exit 0; 3,058 passed, 5 skipped; 90.04% meets 90% | PASS | Preserve the explicit `.venv` invocation. |
| Ruff lint, strict mypy, compile | Current commands above | All passed | PASS | Retain normal CI checks. |
| CI formatter gate | `ruff format --check .` | 38 files unformatted | FAIL | Authorize a scoped formatting remediation without losing existing edits, then rerun. |
| Documentation/ADR coherence | [Consistency audit](pre-phase-8-9-documentation-consistency-audit.md), link/diff check | 227 relative links valid; 0 duplicate ADR numbers; `git diff --check` passes | PASS | Preserve historical evidence as historical, not current authority. |
| Future indexed multi-user serving and external MCP/HTTP certification | ADR-0080 proposal and current unindexed selector | Intentionally not implemented/certified | NOT VERIFIED | Phase 8.9 work only after separate authorization; not a claim about this offline baseline. |

## Remaining risks and decision boundary

The unindexed reset is safe to retain offline; it is not a production GO. The formatter failure blocks an unqualified repository-readiness certification under the user's requirement for applicable CI-equivalent checks, despite the passing full suite, coverage, lint, typing, compile, link, and diff checks. The smallest next step is an owner-reviewed, scope-limited formatting pass on the 38 named already-dirty files, followed by the complete CI-equivalent gate and protected-state recheck. Do not format by resetting, mass-restoring, or overwriting user work. No Phase 8.9 work should begin merely because this report exists.

The working tree was not normalized. It had approximately 255 pre-existing Git status entries before this task, including extensive modifications/untracked work and 15 deleted top-level `goldenDataset/` paths. This task's attributed changes are limited to the root README, `mnemo-core/README.md`, `mnemo-server/README.md`, current architecture, roadmap, transition document, ADR index, documentation navigation and the two reports. Existing signed/historical reports and immutable governance contracts were not edited. Complete external conversation history was not accessible through the repository; available conversation context and repository evidence were used without claiming more.

## 2026-10-11 owner-reviewed formatter follow-up (later verification)

**Current decision: PRE-PHASE-8.9 READY FOR EXPLICIT AUTHORIZATION.** The preceding `NOT READY` decision and its 38-file formatter failure remain above as the historical checkpoint. This follow-up closes that specific gate; it does **not** authorize Phase 8.9 implementation, production indexing, credential reactivation, tunnel restart, or indexed multi-user/external transport certification.

Before editing, the current `ruff format --check .` again failed on exactly **38** Python files: 12 tracked files with existing working-tree changes and 26 untracked files. The exact pre-format paths and classifications were saved in `scratch/pre_phase89_formatter_remediation_2026-10-11.md`. The list was checked against Ruff's existing configuration; no generated, vendored, source-corpus, fixture-data, receipt, database, or protected artifact was eligible. The formatter received only these explicit paths:

```text
mnemo-core/mnemo/ocr_paddle.py
mnemo-core/mnemo/retrieval/advanced.py
mnemo-core/tests/unit/test_advanced_retrieval.py
mnemo-core/tests/unit/test_asset_catalog_store.py
mnemo-core/tests/unit/test_corpus_identity.py
mnemo-core/tests/unit/test_isolated_multilingual_items.py
mnemo-core/tests/unit/test_ocr_paddle.py
mnemo-core/tests/unit/test_v2_index_build_operator.py
mnemo-core/tests/unit/test_v2_production_adapters.py
mnemo-server/mnemo_server/services/portable_corpus_runtime.py
mnemo-server/mnemo_server/services/scope_authority.py
mnemo-server/mnemo_server/tools/isolated_activation.py
mnemo-server/mnemo_server/tools/isolated_rebuild.py
mnemo-server/mnemo_server/tools/legacy_decommission.py
mnemo-server/mnemo_server/tools/rebuild_cleanup.py
mnemo-server/mnemo_server/tools/rebuild_integrity.py
mnemo-server/mnemo_server/tools/source_manifest.py
mnemo-server/mnemo_server/tools/windows_open_handles.py
mnemo-server/tests/test_capabilities_v2.py
mnemo-server/tests/test_isolated_rebuild.py
mnemo-server/tests/test_legacy_decommission.py
mnemo-server/tests/test_legacy_reset_preflight.py
mnemo-server/tests/test_mcp_immutable_schema_matrix.py
mnemo-server/tests/test_phase86_exposure_boundary.py
mnemo-server/tests/test_portable_corpus_runtime.py
mnemo-server/tests/test_production_runtime_selection.py
mnemo-server/tests/test_rebuild_integrity.py
mnemo-server/tests/test_scope_authority.py
mnemo-server/tests/test_server_config.py
mnemo-server/tests/test_two_corpus_rebuild.py
mnemo-server/tests/test_v2_production_adapters_registration.py
scripts/classify_pre_phase89_failures.py
scripts/decommission_partial_rebuild.py
scripts/decommission_pre_phase89.py
scripts/phase8_5_11_derived_pipeline.py
scripts/phase8_5_11_ingest.py
scripts/run_two_corpus_rebuild.py
tests/test_phase8_5_11_derived_pipeline.py
```

The `ruff format --diff` preview spanned 2,076 lines over these paths. After formatting, a per-file before/after comparison of normalized Python ASTs found **0/38 semantic AST changes**, and an ordered comment-token comparison found **0/38 comment changes**. The formatter reported `38 files reformatted`. Existing user modifications and untracked file identities were retained; no source behavior, test assertion, literal value, or comment was changed. These structural comparisons supplement the passing tests; they do not imply a review of every possible runtime behavior outside the test suite.

| Check | Exact command or method | Current result |
|---|---|---|
| Repository format | `.venv/Scripts/python.exe -m ruff format --check .` | PASS, exit 0: 585 files already formatted. |
| Ruff lint | `.venv/Scripts/python.exe -m ruff check .` | PASS, exit 0. |
| Full suite and configured coverage | `.venv/Scripts/python.exe -m pytest -q --junitxml=scratch/pre_phase89_final_verification_junit.xml --cov-report=xml:scratch/pre_phase89_final_verification_coverage.xml` | PASS, exit 0: **3,058 passed, 5 skipped, 0 failed** in 293.58 s; combined statement/branch coverage **90.04%**, above the unchanged **90%** threshold. JUnit has 3,063 tests, 0 failures/errors, 5 skipped. The extra `--cov-report` changes only the XML artifact destination, not coverage measurement or threshold. |
| Focused safety group | `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -o addopts=''` on interpreter-selection, corpus-identity, production-selection, scope-authority, decommission, reset-preflight, isolated-rebuild, two-corpus-rebuild, and source-manifest tests | PASS, exit 0: 109 passed. Coverage options were intentionally disabled only for this diagnostic group; the full run above satisfies the normal gate. |
| Strict source typing | `.venv/Scripts/python.exe -m mypy --strict mnemo-core/mnemo mnemo-server/mnemo_server plugins/email-ingestion/email_ingestion` | PASS, exit 0: 313 source files. |
| Compilation | `.venv/Scripts/python.exe -m compileall -q mnemo-core/mnemo mnemo-server/mnemo_server plugins/email-ingestion/email_ingestion` | PASS, exit 0. |
| Whitespace | `git diff --check` | PASS, exit 0. |
| Documentation and ADRs | Targeted relative-link scan over 11 reconciled documents; ADR filename-number uniqueness and status inspection | PASS: 227 links checked, 0 broken; 0 duplicate ADR numbers. ADR-0080 remains Proposed and ADR-0081 Accepted only for the unindexed baseline. |

The full run emitted nine warnings, including `.pytest_cache` write permission and library deprecation warnings; JUnit and coverage XML were written to their distinct task-specific paths and are readable. These warnings did not change the exit status or test counts. The old bare-`pytest` plugin mismatch is avoided by invoking the main `.venv` interpreter explicitly. Historical GPU benchmark equivalence remains untested.

After the tests, all **five retired database SHA-256 values** still matched their exact `after_sha256` receipts, and all **five recovery snapshot hashes** matched `snapshot_sha256`; both receipts remained present. `verify_source_manifest` checked original bytes again: **44/44** and **24/24**, with the same identities recorded above. The production selector remained `UNINDEXED`; `data/notebook_runtime/mnemo.db` remained absent; the evaluation registry's `notebooks` object remained empty. The non-secret credential lifecycle view still showed no active generation and every recorded generation revoked; a local process scan found zero matching tunnel processes. The main `.venv/Scripts/python.exe` remained present, `scratch/.venv-gpu-preflight` absent, and the same 15 tracked top-level `goldenDataset/` deletions remained. No retired store was opened for live SQLite inspection or decommissioned again. Process and filesystem observations are point-in-time local evidence, not external-launcher or indexed-serving certification.

The Git working tree remains heavily modified and untracked. The only code-file changes attributable to this follow-up are Ruff's layout edits to the 38 inventoried files; their pre-existing semantic edits and all other unrelated status entries were preserved. This report and the scratch formatter inventory are the task evidence changes. Nothing was staged or committed. No Phase 8.9 or Phase 9 implementation, production index, activation, or tunnel restart occurred. The exact next decision is **whether to authorize Phase 8.9 separately** under its proposed ADR and gates; that decision is not made here.
