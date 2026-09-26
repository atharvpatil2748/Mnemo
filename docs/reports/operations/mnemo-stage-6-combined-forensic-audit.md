# Phase 8.8 Stage 6 batch — independent combined forensic audit

**Audit date:** 2026-09-26. **Combined verdict:** `COMPLETED_BATCH_FORENSICALLY_BLOCKED`. **Stage verdict:** `STAGE_6_CLOSURE_PENDING`. This is an independent audit of the edited local checkout, not a product-code correction, production deployment, external ChatGPT test, or Module 8.8.9 certification.

## Authority, scope, and baseline

The checked-out `docs/README.md` (SHA-256 `526871adcb3f26c331e4bd42a28e55ae537c126ae4af024c8c0ff4fa1fd294a4`) points to current architecture §§21.2–21.8 (SHA-256 `4838d21f2e1e52dcad3ec4d52376838cb87777edc5aa63d785f183b3e92a6d6f`) and engineering roadmap Module 8.8.2–8.8.11 (SHA-256 `b549a59badd5d36bd0021460746d2186cd2a90599ec603a235607f70c02423cd`). Accepted ADR-0076/0077/0078 constrain the certified corpus, storage-role separation, and server-owned generation and credentials. The Stage 5 local acceptance report, 8.8.1 certification and forensic audit, 8.8.5/8.8.7 forensic reports, and 8.8.2f/8.8.4/8.8.8 implementation reports were read as *claims*, not substituted for current code/tests. The Phase 8.5 MCP contract/failure audit, CI workflow, `pyproject.toml`, and current tool schemas were checked.

Initial Git: `main...origin/main`, HEAD `069ec468a675c37544a5a2591eac1204c3cb6888`, no staged files, 37 modified tracked files and 15 untracked files. `git log` identifies Stage 5 implementation `7e214b7` and documentation `069ec46` on `main`; no separate Stage 5 GitHub-closure report was located. Cumulative tracked diff: 2,871 insertions and 401 deletions across 37 files, plus untracked implementation/tests/reports. It comprises the prior Stage 6 metadata, typed-error, reader-error, all-tool, and route-composition edits; this audit added only `mnemo-server/tests/test_stage6_forensic_audit.py` and this report. No existing change was reset, staged, or overwritten.

## Requirement → implementation → independent evidence ledger

| Requirement and authority | Code boundary inspected | Existing evidence inspected; fresh result | Verdict |
|---|---|---|---|
| 8.8.5a authorized nullable envelope; architecture §21.7, roadmap 8.8.5 | `services/source_metadata.py`, `services/delivery.py`, schemas, MCP/HTTP adapters | `test_source_metadata.py`, old/new public matrix and fresh focused run: canonical IDs/version hash, nullable display fields and path suppression pass | Pass |
| 8.8.5b one bounded resolver used for every source-oriented response | `AuthorizedSourceMetadataResolverV1.resolve_many`, search/query/evidence/structured/delivery/FinalQA/MCP consumers | 0/200/201, deduplication and public route tests pass; independent partitioned public request shows nested items omit the envelope on both schemas | **Fail** |
| 8.8.5c canonical identity, duplicate names, versions, nondisclosure | resolver scope check, metadata tests, public old/new matrix | Same filename across distinct sources, exact chunk ancestry, mismatched reference and unknown scope tests pass | Pass in tested paths; partition view incomplete |
| 8.8.7a ten safe categories; architecture §21.8, roadmap 8.8.7 | `typed_errors.py`, `errors.py`, MCP dispatch, auth middleware | `test_typed_errors.py`, public HTTP/MCP regressions, fresh focused/full runs | Pass |
| 8.8.7b allowlisted safe origin and correlation | classifier cause walk, HTTP request state and MCP call boundary | Forged code, nested storage/schema/timeout/cursor and distinct UUID tests; fresh runs | Pass |
| 8.8.7c no public SQL/path/token disclosure | classifier allowlists, sanitized HTTP/MCP/streaming responses and logs | Malicious message and unknown/unauthorized shape tests, public transport matrix; fresh runs | Pass locally |
| 8.8.2f originating reader error, roadmap 8.8.2 | `ChunkReadModel`, SQLite reader, `advanced.py::_safe_source_failure_reason`, typed classifier | Old/new SQL, page-filter, nested `sq-2:sparse`, public MCP/HTTP reader tests rerun | Pass locally; independently evaluated here, not in an earlier separate audit |
| 8.8.4a registration, route, handler, auth scope | `mcp/tools.py::_TOOL_ROUTES`, `get_mcp_tools`, `execute_mcp_tool`, startup validation | Route-registry tests and 14-tool discovery pass | Pass |
| 8.8.4b/c authorized valid/empty/invalid/unavailable | 14 handlers, V1/V2 services, old/new readers | 14-tool and persisted OCR/Vision matrix pass for tested inputs; partitioned ranked multilingual returns failed representation while equivalent nonpartitioned request reaches source | **Fail** |
| 8.8.4d provenance/transport parity | same logical disposable corpus through direct MCP, real stdio, loopback SSE, applicable HTTP | `test_mcp_transport_contract_matrix.py` rerun; partition child items differ from top-level metadata | **Fail** |
| 8.8.8a/b/c frozen V1/V2 route and no historical fallback | one route map, `ProductionStorageComposition.validate_injected_engine`, V2 service selection, retained V1 | Route/startup and distinct-store/model negative tests rerun; no historical fallback demonstrated; principal-aware V2 partition route is not preserved and 8.8.4 prerequisite remains failed | **Acceptance blocked** |

## Complete 14-tool and backend evidence inventory

`_TOOL_ROUTES` in `mcp/tools.py` is the dispatch authority, not a detached table. Public input definitions and route-registration tests enforce the 14 names. The same-fixture transport matrix calls all 14 through direct MCP, real local stdio and disposable loopback SSE; its HTTP comparison covers only existing counterparts. The old/new public matrix separately exercises typed errors, persisted OCR/Vision, cursor traversal, metadata, assets and binary delivery. These are local fixture outcomes, not live tunnel parity.

| Tool | Declared backend and handler | Freshly rerun evidence; limitation |
|---|---|---|
| `list_notebooks` | retained V1, `_handle_list_notebooks` | nonempty inventory, invalid limit; V1 HTTP exists |
| `get_notebook_summary` | retained storage, `_handle_get_notebook_summary` | nonempty/empty and unknown scope; V1 HTTP exists |
| `get_timeline` | retained storage, `_handle_get_timeline` | persisted event/empty and invalid; V1 HTTP exists |
| `get_source_insights` | retained storage, `_handle_get_source_insights` | persisted insight/empty and invalid; no exact HTTP counterpart |
| `search_all_notebooks` | retained V1, `_handle_search_all_notebooks` | scoped/global FTS, empty and unknown; V1 HTTP exists |
| `query_notebook` | retained V1, `_handle_query_notebook` | evidence and deterministic synthesis, invalid/unknown; V1 HTTP and retained streaming are not FinalQA V2 |
| `search_evidence` | representation-specific V2, `_handle_search_evidence` | ranked/exhaustive, cursor, partial schema failure, invalid; **partitioned ranked governed source fails**; V2 HTTP exists |
| `get_capabilities` | runtime V2, `_handle_get_capabilities` | lifecycle and invalid capability; V2 HTTP exists; registration alone is not readiness |
| `query_structured` | typed V2, `_handle_query_structured` | authorized projection, invalid and unavailable; V2 HTTP exists |
| `get_document` | shared V2 delivery, `_execute_delivery_tool` | fixture blocks/original, unknown/unavailable; V2 HTTP exists; production parsed representation remains unavailable |
| `get_document_chunk` | shared V2 delivery, `_execute_delivery_tool` | exact chunk/ancestry, mismatch/unknown; V2 HTTP exists |
| `get_asset` | shared V2 delivery, `_execute_delivery_tool` | occurrence and original bytes, unknown; V2 HTTP exists |
| `get_image_analysis` | shared V2 delivery, `_execute_delivery_tool` | reopened persisted OCR/Vision, explicit/latest/all and unavailable; V2 HTTP exists; not image discovery |
| `run_final_qa_v2` | certified V2, `_handle_final_qa_v2` | deterministic fixture execution/citation and invalid/unavailable; V2 HTTP exists; no live provider/tunnel claim |

HTTP V1 query/search, V1 WebSocket/query streaming, V2 evidence/structured/delivery and authenticated HTTP V2 FinalQA remain distinct. The certified-style canonical sparse adapter uses the authorized effective store; it is not an independently selected historical store. Startup mismatch tests for actual `MnemoConfig`-backed injected engines pass. `validate_injected_engine` deliberately skips full identity comparison for a non-`MnemoConfig` read-only test double (`services/production_storage_composition.py:47–57`); no external route to that internal seam was demonstrated. Keep it a documented residual risk, not a proven production fallback. Module 8.8.9 must still test the external tunnel.

## Independent adversarial findings and reproductions

**F-1 — High, 8.8.4 valid-request and V2 principal-bound routing defect.** `EvidenceRetrievalApplicationService.execute` invokes `engine.partitioned_retrieval.execute` at `services/retrieval_v2.py:97–102` without passing the trusted principal, whereas its nonpartitioned production path calls `execute_authorized` at line 121. `PartitionedRetrievalServiceV1.execute` calls `_retrieval.execute` at `mnemo-core/mnemo/retrieval/partitioned.py:117`. The governed ranked multilingual source's unauthenticated `retrieve` raises at `full_multilingual_advanced_v2.py:94–103`, while `retrieve_authorized` is the actual V2 path. Independent public `execute_mcp_tool` tests use a disposable governed-source analogue and the real service/dispatcher on both schemas. Nonpartitioned ranked requests report `searched`; explicit authorized document partitions report `failed` with `source_failure:provider_failure` and no item. `uv run pytest ... test_stage6_forensic_audit.py --runxfail --tb=short` reproduced two assertion failures (`'failed' != 'searched'`). This is an authenticated valid-request failure and dropped principal context, not evidence that foreign content was disclosed. A distinct cross-notebook partition test returned no foreign canonical text/chunk on both schemas. Minimal correction: pass the principal through partition traversal, use `execute_authorized` for production, and validate every explicit partition against authorized notebook/document ancestry before retrieval. Prove both positive governed ranked output and negative scope behavior without changing V1 ranking or cursor semantics.

**F-2 — Medium, 8.8.5/8.8.4 metadata/provenance defect.** `_partitioned_response` duplicates per-partition `child.items` into `partitions[].items` at `services/retrieval_v2.py:372–382`. `_with_authorized_metadata` at lines 150–184 enriches only the top-level `response.items`; it does not update the nested partition copies. On both old/new disposable SQLite fixtures, a successful partitioned canonical MCP request returned the correct notebook/document/version/chunk/source metadata at top level, while `partitions[0].items[0].source_metadata` raised `KeyError`. The `--runxfail` command reproduced both failures. No unauthorized data was observed; the contract-level source envelope and cross-view parity are incomplete. Minimal correction: enrich each canonical item once after authorization and project the same envelope into both views, enforcing the existing 200-reference and byte ceilings. Preserve canonical IDs and pagination.

The four audit regressions are retained as **strict xfails**, not quietly treated as passing acceptance evidence. The same file has two passing older/newer cross-notebook nondisclosure tests. With `--runxfail` it reports **four failures, two passes**, preserving the actual current-code reproduction; with normal CI execution it reports **two passes, four xfails**. No product source was modified or defect hidden by a relaxed assertion.

## Documentation and claim audit

- `docs/README.md:27`, `docs/architecture/current/mnemo_architecture_v2.md:2551,2621,2729,2831`, and `docs/architecture/current/mnemo_engineering_roadmap.md:270,377,1306` still describe 8.8.2f as pending/awaiting 8.8.7. That is stale relative to the locally implemented and now independently tested reader-error contract; it must say *locally implemented/forensically evaluated here*, without implying deployment or Phase 8.8 completion. The canonical dependency-order sentences should remain historical/planning order, not be removed.
- `docs/reports/operations/mnemo-module-8-8-8-local-implementation.md:40` says production evidence retrieval invokes the principal-aware entry point. It is accurate for nonpartitioned requests but overbroad for partitioned requests (F-1). The report's local-verification verdict is historical evidence, not a current independent acceptance verdict. Add an erratum/reference to this audit; do not rewrite the earlier test counts.
- `docs/reports/operations/mnemo-module-8-8-4-local-implementation.md:139–160,182` claims complete applicable 14-tool local success/transport parity; its tested corpus did not cover principal-aware ranked multilingual partitions or nested partition metadata (F-1/F-2). It correctly disclaims a governed multilingual positive fixture at line 160; the limitation must carry forward to any broader assertion. The historical 2,679-pass count is not false, but it did not prove these options.
- The 8.8.5 and 8.8.7 forensic reports distinguish local acceptance from deployment, disclose their executed gates, and cite tests that exist. 8.8.5's broad resolver-reuse claim omitted partition child items (F-2); this audit supersedes that acceptance for the combined current tree. The 8.8.2f report correctly says its previous result was only local verification; **this audit** supplies the later independent assessment, not a fictional earlier separate audit.
- Architecture/ADR status and the Stage 5 historical acceptance report need no decision rewrite. A future documentation reconciliation should update current status lines; this audit is already indexed in `docs/reports/README.md`. No new ADR is required for these narrow contract corrections. Phase 8.8 is still in progress; production parsed-document availability, search_images, and live four-transport behavior are not claimed.

## Executed validation and environment limits

Fresh focused command: `CI=true MNEMO_CI=1 uv run pytest -q -p no:cacheprovider --no-cov` with `test_stage6_forensic_audit.py`, `test_mcp_v1_v2_routing.py`, `test_mcp_route_contracts.py`, `test_mcp_immutable_schema_matrix.py`, `test_mcp_transport_contract_matrix.py`, `test_source_metadata.py`, `test_typed_errors.py`, `test_mcp_principal.py`, `test_production_storage_composition.py`, and `mnemo-core/tests/unit/test_sqlite_store.py`: **217 passed, two xfailed, one warning** before the second audit test was added. Final independent test file: **two passed, four xfailed**; deliberate `--runxfail`: **four failed, two passed**. The first full run, collected before the second audit test was added, recorded **2,688 passed, 18 skipped, two xfailed, eight warnings, 90.31%** and was superseded by the final run.

Final full command `CI=true MNEMO_CI=1 uv run pytest -q -p no:cacheprovider --tb=short --cov-report=term:skip-covered`: **2,688 passed, 18 skipped, four xfailed, eight warnings, 90.31% repository-wide coverage** (90% floor), exit 0. Xfails are the two confirmed defects above, not acceptance. Warnings were existing Starlette/httpx deprecations, malformed openpyxl fixture dependencies, Qdrant local-index advice, FastAPI/MCP deprecations. `uv` emitted a nonfatal dangling `~nemo_server-0.22.0.dist-info` warning; no dependency cleanup was performed.

`uv run ruff check .`, `uv run ruff format --check .` (523 files), `uv run mypy --strict mnemo-core/mnemo mnemo-server/mnemo_server plugins/email-ingestion/email_ingestion` (291 source files), compileall, `uv lock --check` (171 packages), all three `uv build --package` source/wheel builds, and `git diff --check` passed. Frontend `pnpm format:check`, `pnpm lint`, `pnpm typecheck`, `pnpm test` (one passed, frontend-reported 100% coverage), and `pnpm build` passed. Three configured `docker compose --file ... config --quiet` checks passed. Docker image builds were **not executed**: `docker version` could not connect to the local Docker Desktop Linux daemon. GitHub CI on a published commit remains unverified for this edited tree. No ignored-only evaluator script was required by the executed tests.

## Protected state

The following were independently hashed before audit tests and after the final full suite. Both sides match exactly:

| Artifact | SHA-256 | Bytes; UTC mtime | Sidecars |
|---|---|---|---|
| Certified production DB, `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db` | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | 189,804,544; `2026-09-01T11:09:20.1047581Z` | WAL/SHM/journal absent |
| WP16 DB, `scratch/phase8_5_wp16/eval-20260828-01/mnemo.db` | `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d` | 37,195,776; `2026-08-29T13:37:31.2308106Z` | WAL/SHM/journal absent |

Production manifest `e579727c8867c92d4ca7fe05256a35d74942077f86b86a6fad9938ff3b4fc566`; certified launcher `007ee235783cb8f673a2f9c135bc38269ba2a355057c5cd119c0125e471fde22`; signed activation `c17a7f5531cc75795fb63c6f53682d30eb6ed831127db95038d3d1741cd25525`; certificate `1a69e95796b98abcc1f4f6484692481058bff776b454a14e3a0b35d86f16312a`; final evidence `0255160992fc1ed2fdc5b5c6bfb55bb442b55018655f511274d698569a06230c`; signed convergence `b5ccccb9787773ef10f5a6364bbc80ed98324640ea5438da604ebfaf2b7c2b23`. All matched the accepted recorded baselines at both checkpoints. Credential-registry metadata showed exactly one `ACTIVE` generation `fc85192e-f672-4cc0-9539-b4b063bb8f41`; no secret value was read into the report. No protected database was opened writable, repaired, migrated, or modified.

## Final acceptance and next gate

| Module | Verdict | Reason |
|---|---|---|
| 8.8.5 | `MODULE_8_8_5_BLOCKED` | F-2 violates source-oriented nested partition item envelope/parity |
| 8.8.7 | `MODULE_8_8_7_FORENSICALLY_ACCEPTED` | Ten categories, safe origins/UUIDs, HTTP/MCP/retained stream sanitization and fresh regressions passed |
| 8.8.2f | `MODULE_8_8_2F_FORENSICALLY_ACCEPTED` | Reader-owned schema/retrieval reasons survive tested old/new public boundaries; this is its first independent combined audit |
| 8.8.4 | `MODULE_8_8_4_BLOCKED` | F-1 valid ranked partition, F-2 provenance parity |
| 8.8.8 | `MODULE_8_8_8_BLOCKED` | Route/store/model negative tests pass, but 8.8.4 dependency and governed partition route are not closed; no actual V1 fallback observed |

**Cross-module integration:** blocked by F-1/F-2. **Documentation:** factual status reconciliation pending; accepted ADRs remain intact. **Completed batch:** `COMPLETED_BATCH_FORENSICALLY_BLOCKED`. **GitHub closure:** not ready while the two reproduced defects and report/status discrepancies remain; Docker image build CI for this edited tree is also unverified. **Stage 6:** `STAGE_6_CLOSURE_PENDING` independently of this batch because roadmap step 7 still requires 8.8.10a–c evaluation isolation and 8.8.11a–c structured-contract work. Subsequent 8.8.9, 8.8.12, 8.8.13 and final phase gates remain distinct.

No commit, push, PR, production deployment, production restart, tunnel restart, credential/configuration change or protected-store mutation occurred. Product-code corrections are proposed, **not** applied in this forensic pass.
