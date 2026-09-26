# Module 8.8.8 — V1/V2 routing contract, local implementation

**2026-09-26 follow-up:** The later [combined independent audit](mnemo-stage-6-combined-forensic-audit.md) found that the principal-aware V2 evidence entry point described below applied only to nonpartitioned requests; partitioned ranked retrieval called the unauthenticated entry point. No historical V1 store/model fallback was observed. The historical local verdict and counts remain intact. See the [remediation acceptance](mnemo-stage-6-forensic-remediation-and-acceptance.md) for the principal-propagation fix and independent route reassessment.

**Verdict: `MODULE_8_8_8_LOCALLY_VERIFIED` (2026-09-26).** This is fixture-backed local route and startup verification, not an independent forensic audit, production deployment, external ChatGPT verification, Stage 6 closure, or the four-transport certification assigned to 8.8.9.

## Authority and baseline

`docs/README.md` establishes the documentation hierarchy. The current architecture §§21.3–21.8 and engineering-roadmap Module 8.8.8 require retained V1 routes to stay retained, V2 evidence/structured/delivery/FinalQA to use their declared contracts, certified V2 never to fall back to a historical V1 store/model, and retained V1 behavior to change only for accepted authorization and certified read compatibility. ADR-0076 fixes certified immutable corpus authority, ADR-0077 separates mutable/operational stores, and ADR-0078 keeps production credentials and generation server-owned. The Stage 5 acceptance report and local 8.8.2f, 8.8.5, 8.8.7 and final 8.8.4 reports were used as prior acceptance boundaries.

Initial Git state was `main...origin/main`, HEAD `069ec468a675c37544a5a2591eac1204c3cb6888`, no staged files, 33 modified tracked and 13 untracked files. Those changes include accepted 8.8.5/8.8.7 work and locally verified 8.8.2f/8.8.4 work. No prior source or test change was reset, stashed or discarded. The separately identified certified production and WP16 databases matched the protected identities below before any edit.

## 8.8.8a — frozen public inventory

`mnemo_server.mcp.tools._TOOL_ROUTES` remains the **single** authoritative MCP route/handler/scope registry. `get_mcp_tools()` and `create_mcp_server()` validate registration against it before exposure, and `execute_mcp_tool()` invokes its handler directly. No competing registry or public tool was added. `test_mcp_route_contracts.py` asserts exact names, families, scopes, handler identity and missing/nonexecutable-route rejection. The new `test_http_v1_v2_public_routes_remain_distinct` asserts the corresponding HTTP OpenAPI route families and separate V1/V2 FinalQA operation IDs.

| MCP tool | Frozen backend family | Handler/service path | HTTP counterpart where applicable |
|---|---|---|---|
| `list_notebooks` | retained V1 | `_handle_list_notebooks` / authorized storage | `GET /v1/notebooks` |
| `get_notebook_summary` | retained storage | `_handle_get_notebook_summary` / persisted insight/source storage | `GET /v1/notebooks/{notebook_id}/summary` |
| `get_timeline` | retained storage | `_handle_get_timeline` / event storage | `GET /v1/notebooks/{notebook_id}/timeline` |
| `get_source_insights` | retained storage | `_handle_get_source_insights` / insight storage | No exact source-insight HTTP counterpart; V1 notebook insights is separate |
| `search_all_notebooks` | retained V1 | `_handle_search_all_notebooks` / `SearchService` | `POST /v1/search` |
| `query_notebook` | retained V1 | `_handle_query_notebook` / `QueryService` | `POST /v1/query`; V1 `/v1/query/stream` and `/v1/ws/query` retain streaming contract |
| `search_evidence` | V2 representations | `_handle_search_evidence` / `EvidenceRetrievalApplicationService` | `POST /v2/retrieval/evidence` |
| `get_capabilities` | runtime V2 | `_handle_get_capabilities` / capability service | `GET /v2/capabilities` |
| `query_structured` | typed V2 | `_handle_query_structured` / `StructuredRetrievalApplicationService` | `POST /v2/retrieval/structured` |
| `get_document` | shared V2 delivery | `_execute_delivery_tool` / bounded delivery | V2 exact-version, expand and original routes |
| `get_document_chunk` | shared V2 delivery | `_execute_delivery_tool` / exact chunk | V2 exact-version `/chunks/{chunk_id}` |
| `get_asset` | shared V2 delivery | `_execute_delivery_tool` / occurrence/original | V2 `/assets` and occurrence `/content` |
| `get_image_analysis` | shared V2 delivery | `_execute_delivery_tool` / persisted derivation | V2 occurrence `/analysis` |
| `run_final_qa_v2` | certified V2 FinalQA | `_handle_final_qa_v2` / `FinalQAV2ApplicationService` | `POST /v2/notebooks/{notebook_id}/final-qa` |

The HTTP V1 `POST /v1/notebooks/{notebook_id}/final-qa` is a separate retained route, **not** the MCP V2 FinalQA handler. The root `/ws/query` alias and V1 WebSocket/SSE query events remain retained streaming, not certified V2 chat. The V2 FinalQA evidence-delivery HTTP route is additive and not a new MCP tool. Other V1 CRUD/ingestion/session/management routes are outside this 14-tool routing contract; no HTTP counterpart was invented for tools without one.

## 8.8.8b — historical fallback prevention

For production HTTP, stdio and SSE startup, the existing certified binding first resolves the server-owned production configuration. ADR-0077 storage preflight supplies the effective engine configuration. Previously, a **read-only injected engine** was accepted solely because `certified_read_only=True`; its store or model configuration could still differ from the admitted composition. `ProductionStorageComposition.validate_injected_engine()` now requires a real `MnemoConfig`-backed injected engine to match the entire effective configuration, not merely the read-only flag. All three startup entry points call this same gate before engine initialization, V2 installation or public transport exposure. A store or embedding-model fork fails with static `INJECTED_PRODUCTION_RUNTIME_MISMATCH`, without opening the historical database. Writable certified injection retains its existing rejection. Test doubles without a `MnemoConfig` retain the legacy synthetic seam; actual `KnowledgeEngine` construction has a typed `MnemoConfig`.

The distinct disposable historical/V2 configuration tests in `test_production_storage_composition.py`, `test_server_app.py`, `test_mcp_server.py` and `test_mcp_sse.py` prove fail-closed store and model selection at the composition and HTTP/stdio/SSE startup boundaries. The HTTP and stdio tests additionally assert no historical file creation or protocol stream exposure. These tests fail on the pre-8.8.8 read-only-flag-only check and pass with the shared gate.

The V2 service-selection audit found no further in-scope implicit cross-database constructor. `EvidenceRetrievalApplicationService` invokes `engine.advanced_retrieval` and, in production, its principal-aware entry point; `StructuredRetrievalApplicationService` invokes `engine.structured_retrieval`; shared delivery uses the engine's authorized storage; FinalQA V2 requires its own execution store and rejects use of production corpus storage as that operational store. Missing V2 services are typed unavailable, not V1 success. `test_mcp_v1_v2_routing.py` removes V2 evidence/structured/FinalQA composition from an older/newer disposable corpus while retaining working V1 search and deterministic V1 synthesis: V1 calls succeed, while all three V2 calls return `capability_unavailable` with correlation IDs and no V1 answer in the error. Existing final-8.8.4 public contract, metadata, reader and typed-error tests cover missing representations, projections, derivations, operational composition, nested sparse-reader errors, unauthorized scope and forbidden client policy overrides.

`CanonicalTextAdvancedSource` legitimately adapts the retained compatible sparse reader on the **same authorized effective store**; it is not an independent historical database. The governed multilingual ranked source is installed by the certified V2 startup and bound to the active V2 identity. Its exhaustive `ProjectedMultilingualAdvancedSource` fallback uses that same engine storage and the multilingual representation, not a separate historical V1 store/model. The name “fallback” there denotes governed exhaustive retrieval strategy, not a V2-to-V1 production-identity switch. No ranking, candidate-pool, cursor, model activation or production configuration was changed.

## 8.8.8c — retained V1 and transport compatibility

The new old/new public MCP regression proves `query_notebook` synthesis and `search_all_notebooks` still work when V2 evidence, structured and FinalQA services are unavailable; none routes into FinalQA V2. Existing `test_mcp_immutable_schema_matrix.py` verifies retained searches, candidate/chunk/document/version identities, authorization, nullable old-schema page ranges and newer persisted ranges. `test_mcp_transport_contract_matrix.py` reuses the final 8.8.4 corpus across direct public MCP, a real local stdio subprocess, isolated loopback SSE and applicable HTTP routes, including all 14 nonempty tool outcomes and safe errors. The same-fixture SSE child now runs the real disposable ADR-0077 preflight rather than a `SimpleNamespace` pretending to be the production storage composition. The direct comparator uses the same read-only workspace decision, preserving truthful capability snapshot equivalence. The child still replaces only certified binding/V2 installer authority for a **disposable local fixture** and never registers a production tunnel. Retained V1 WebSocket/SSE and partial-result semantics remain covered by existing streaming and reader tests; no V2 streaming was introduced.

This is local transport *routing* evidence, not Module 8.8.9's full HTTP/stdio/SSE/external-tunnel behavioral certification. The governed multilingual positive path is not claimed ready on the canonical-only disposable matrix; scope-specific unavailability remains truthful. The certified production corpus's absent parsed-document representation remains unavailable; no evaluation artifact was copied into it.

## Executed validation and defect disposition

Focused final command: `CI=true MNEMO_CI=1 uv run pytest -q -p no:cacheprovider --no-cov` on `test_mcp_v1_v2_routing.py`, `test_mcp_route_contracts.py`, `test_mcp_immutable_schema_matrix.py`, `test_mcp_transport_contract_matrix.py`, `test_mcp_server.py`, `test_mcp_sse.py`, `test_server_app.py`, `test_production_storage_composition.py`, `test_typed_errors.py`, `test_final_qa_v2_transport.py`, `test_structured_v2.py`, and `test_mcp_principal.py`: **226 passed, two warnings**. An intermediate run failed its two SSE cases after the new startup gate exposed an incomplete **test harness** composition. Running real disposable preflight and matching the scope decision corrected the fixture without relaxing production code; the isolated SSE rerun passed both cases. An early new structured test request was missing the schema-required `version_ids`; correcting the request produced two passing old/new tests, not a product change.

Final full command: `CI=true MNEMO_CI=1 uv run pytest -q -p no:cacheprovider --tb=short`: **2,686 passed, 18 skipped, eight test warnings, 90.23% repository-wide coverage**, exit 0, with the unchanged 90% enforcement gate. Test warnings were existing Starlette/httpx deprecations, malformed openpyxl fixture notices and local Qdrant advice. Coverage also warned that one temporary parallel `.coverage.MSI.pid70736.XZen7jUx` shard was malformed; it still produced the coverage report and passed the threshold. That exact shard was created during this run, inspected and removed; no pre-existing file was cleaned. The `uv` environment repeatedly emitted a nonfatal dangling distribution-info warning. Neither warning was hidden or used to lower the gate.

`uv run ruff check .` passed; `uv run ruff format --check .` passed (**522 files**); strict mypy passed on the configured three Python source targets (**291 files**); compileall passed; `uv lock --check` resolved **171 packages**; all three `uv build --package` source+wheel builds passed; `git diff --check` passed. Frontend `pnpm format:check`, `pnpm lint`, `pnpm typecheck`, `pnpm test` (**one passed, frontend-reported 100% coverage**) and `pnpm build` passed. The initial Ruff/import and format findings were corrected in the new tests before these final green gates. No coverage configuration, dependency lock, generated distribution or frontend source was changed.

All three configured `docker compose ... config --quiet` checks passed. Image builds were not run: `docker version` could not connect to the local Docker Desktop Linux daemon (`dockerDesktopLinuxEngine` pipe absent). This is an environment-dependent CI build limitation, not evidence of a route-test pass or a production deployment; GitHub's Docker build job remains a separate check when this work is published.

## Protected-state checkpoint

| Protected artifact | Before and after SHA-256 | Size and UTC mtime | Sidecars |
|---|---|---|---|
| Certified production DB, `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db` | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | 189,804,544 bytes; `2026-09-01T11:09:20.1047581Z` | No WAL/SHM/journal |
| WP16 DB, `scratch/phase8_5_wp16/eval-20260828-01/mnemo.db` | `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d` | 37,195,776 bytes; `2026-08-29T13:37:31.2308106Z` | No WAL/SHM/journal |

Freshly recomputed after the gates, and equal to the recorded baseline: production manifest `e579727c8867c92d4ca7fe05256a35d74942077f86b86a6fad9938ff3b4fc566`, certified launcher `007ee235783cb8f673a2f9c135bc38269ba2a355057c5cd119c0125e471fde22`, signed activation `c17a7f5531cc75795fb63c6f53682d30eb6ed831127db95038d3d1741cd25525`, certificate `1a69e95796b98abcc1f4f6484692481058bff776b454a14e3a0b35d86f16312a`, final evidence `0255160992fc1ed2fdc5b5c6bfb55bb442b55018655f511274d698569a06230c`, and four-transport startup convergence `b5ccccb9787773ef10f5a6364bbc80ed98324640ea5438da604ebfaf2b7c2b23`. Credential-registry metadata still lists exactly one `ACTIVE` generation, `fc85192e-f672-4cc0-9539-b4b063bb8f41`; no credential value was printed. No protected database was opened writable or repaired.

## Change inventory and acceptance

This pass changed `mnemo_server.services.production_storage_composition`, `mnemo_server.app`, `mnemo_server.mcp.server`, the corresponding production/HTTP/stdio/SSE startup tests, the disposable SSE child, and its transport comparator; it added `test_mcp_v1_v2_routing.py` and this report. The existing ToolRouteContract registry, retrieval rankings, readers, metadata, typed-error and FinalQA implementations were preserved. Existing dirty 8.8.5/8.8.7/8.8.2f/8.8.4 changes remain uncommitted. Final Git is still `main...origin/main` at `069ec468a675c37544a5a2591eac1204c3cb6888`, with no staged changes. No commit, push, PR, production deployment, production/tunnel restart, migration, reindex, embedding regeneration, credential/configuration change or signed-evidence mutation occurred.

| Requirement | Evidence | Local result |
|---|---|---|
| 8.8.8a route inventory/freeze | Existing one-registry/startup tests, new HTTP route-family freeze, audited handler/service/transport map above | Verified |
| 8.8.8b no historical V1 fallback | New shared effective-config identity gate on HTTP/stdio/SSE; distinct disposable historical-store/model injections rejected; missing V2 service public MCP tests; existing representation, delivery and FinalQA regressions | Verified locally |
| 8.8.8c retained V1 compatibility | New old/new V1 synthesis/search with V2 absent; existing old/new reader, authorization, typed-error, streaming and direct/stdio/SSE/HTTP contract matrix | Verified locally |

Separate work remains for 8.8.9 live four-transport parity, 8.8.10 evaluation-only selection, 8.8.11 structured availability certification, 8.8.12 `search_images`, and final Phase 8.8 acceptance. This report does not mark Stage 6 complete.
