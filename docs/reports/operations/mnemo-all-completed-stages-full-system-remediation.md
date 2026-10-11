# Completed-stage full-system remediation — 2026-09-28

## Superseding external-defect correction pass

Final exact-tree validation:2775passed/18existing skips/9warnings/90.31%;
162focused passed/1cache-warning; no new skips/xfails. Ruff,strictmypy,
compileall,lock,3Pythonbuilds,frontend gates,3Dockerbuilds,3Compose configs,
412-document/392-relative-link scan and diff-check passed.

The [cursor/FinalQA remediation report](mnemo-cursor-finalqa-external-defect-remediation.md)
preserves failing-first evidence and supersedes the earlier cursor/answer
completion claims below. Requested candidate limits are now signed before
server normalization. Premature generation is rejected before publication;
complete snapshots retain termination metadata, including through replay.
V1 top1 versus document-scoped V2 was reproduced as a ranking/scope difference;
top5 includes both relevant codePrompt chunks. No V1 ranking was changed.

Current deployed291-file manifest:
8141d5090f25a26b742c8417d87dff7a3f1473a1f2b277792ba20f60c0504274.
Forward restart2026-09-28T06:55:01.8796870Z; tunnel96024,
cmd94652, venvPython93940, interpreter96476. All14 passed certified real stdio
and authenticated loopback SSE after the final product change. Approved1024-token
FinalQA terminated stop/complete with two citations and zero-inference replay.
Actual production TCP HTTP also passed changed-budget409, FinalQA/replay200 and
delivery/structured reads. All53 REST operations have accounted-for real TCP
fixture invocations; this is not53 positive production requests or public REST
certification. Protected before/after identities are unchanged. Final exact
validation/Git inventory is in the linked report. Historical counts and verdicts
below are not retroactively rewritten.

**SPECIFIC_EXTERNAL_ACTION_REQUIRED:** owner must run the updated connected-MCP
prompt against this new deployment. No authenticated public application client
is available to this engineering session. Fresh four-transport certification
and external ChatGPT acceptance remain pending, not inferred from health200.

## Verdict, authority and exact boundary

`MNEMO_COMPLETION_REQUIRES_SPECIFIC_EXTERNAL_ACTION`. Product corrections have been implemented, retested and loaded by the existing tunnel. All 14 names were invoked successfully through certified local stdio and authenticated loopback SSE; this is not independent external acceptance or complete fresh four-transport certification.

Initial Git: main and origin/main at `5d2612fef6d26cc1e1b0547bb5bd3da6abf21187`, 24 modified tracked files, 11 untracked, nothing staged. Final: 34 modified tracked, 19 untracked, nothing staged. Existing Stage 6 work was preserved. No commit, push, PR, credential rotation, corpus write, evaluation promotion or signed-artifact rewrite occurred.

Authority: [canonical roadmap](../../architecture/current/mnemo_engineering_roadmap.md) §§1, 2, 6, 12; [architecture](../../architecture/current/mnemo_architecture_v2.md) §§21.3–21.11; accepted ADRs 0064, 0074, 0076–0078; Stage 6 independent forensic closure and historical GitHub closure. ADR-0064 permits canonical-chunk FinalQA; ADR-0074 requires actual runtime-owned services and active compatible generation identities; ADR-0076 freezes the production corpus; ADR-0077 separates mutable operation/workspace state; ADR-0078 owns authentication and generation authority. Historical completion labels and signed convergence were treated as claims with exact identity boundaries, not new-source behavioral certificates.

## Completed-stage reconstruction and current evidence

| Canonical completed phase | Original deliverable / actual implementation | Reproduced evidence and limit |
|---|---|---|
| 0 | uv workspace, lint/types/tests/coverage, React rails, CI, three Compose/Docker builds | All local quality/build gates reproduced; no new GitHub CI because publication prohibited. Original Apache setup is historical, current proprietary policy preserved |
| 1 | Typed models, seven protocols, versioned registry, configuration/composition/lifecycle | models/interfaces/registry/config/engine suites passed; actual certified engine startup exercised |
| 2 | Filesystem + SQLite authority, optional Qdrant vectors, partial Surreal graph, CompositeStorage rollback | storage suites passed; actual immutable SQLite/blob delivery exercised. Adapter-specific NotImplementedError slots are not a mandate to duplicate filesystem/graph data into Qdrant/SQLite |
| 3 through 3.9 | PDF/DOCX/Markdown/HTML/text and extended parsers, cleaner/classifier, canonicalization | parser/ingestion suites passed. Roadmap's unchecked running-header/footer item and optional future LLM orchestration are not represented as implemented |
| 4 | Nine V2 chunkers, canonical block spans/IDs, hierarchy, tokenizer/checksum | all chunker/tokenizer suites passed; persisted production exact-chunk ancestry retrieved. Historical 952-page milestone not rerun as a new live ingestion |
| 5 | Provider-backed batching/cache/dimension validation; configuration-dependent Qdrant | embedding/cache suites passed; production BGE-M3 pinned cache loaded. Historical 1,000-chunk Qdrant milestone not recertified on live production |
| 6 | Planning/HyDE, dense/sparse/hybrid/RRF, parent promotion, reranking, context/citations, persisted QA | suites passed; actual retained synthesis returned a citation; actual V2 typed text QA returned citation_resolved. No V1 fallback introduced |
| 7 | REST CRUD/read adapters, ingestion, sessions/notes/insights, query/search, retained WebSocket, auth | full server suites passed; 53 OpenAPI method/path operations inventoried; real TCP read-only production requests passed. Mutation/streaming fixture suites do not prove all public HTTP endpoints |
| 8 | Original six MCP tools, native stdio/SSE and conformance | final-source disposable direct/stdio/SSE comparisons and actual certified stdio/SSE passed |
| 8.5 | Asset provenance, durable processing/OCR/Vision/vector derivations, advanced/structured/MM/multilingual retrieval, bounded delivery, FinalQA V2 | all suites passed; real original/asset bytes, persisted analyses, exact chunks, structured queries, complete cursors and cited FinalQA exercised. Optional provider generation is not auto-activated |
| 8.6 | Validated isolated multilingual evaluation notebook | old/new isolation tests passed, protected evaluation hashes preserved; no production registry federation |
| 8.7 | Expanded 14-tool capability/client milestone | all 14 successfully invoked locally against certified production; new-source independent external 14-tool acceptance pending |

The roadmap explicitly leaves Phase 8.8 convergence/contract acceptance in progress. Module 8.8.9 fresh external/four-transport behavior, subsequent image discovery/provenance/GO gates, Phase 9 UI and Product Stage 7 ecosystem are not silently claimed complete. No tool 15 was implemented. This record is not an exhaustive fresh live rerun of every historical ingestion/model/evaluation milestone.

## Confirmed defects and applied corrections

1. **Delivery composition:** handlers constructed bounded delivery ad hoc, while lifecycle had no document/exact/asset registration. Failed-first test `test_server_owned_delivery_is_registered_from_actual_service` rejected the missing factory parameter. KnowledgeEngine now validates one server-owned delivery factory; HTTP/MCP reuse its service. Exact registration requires ExactDocumentReaderV1. Incompatible factory fails startup; absent protocol is not advertised.
2. **FinalQA dependency:** the old dependency graph required multimodal retrieval even for canonical-text QA. `test_text_finalqa_requires_typed_retrieval_not_visual_generation` failed at dependency_unavailable:multimodal_retrieval. ADR-0064's typed text route now depends on exhaustive retrieval, authorization and provenance; actual provider/request modality checks remain. No model/profile/certification gate was bypassed.
3. **FinalQA modality truthfulness:** static metadata advertised image when a text-only provider was composed. `test_finalqa_modalities_are_derived_from_the_composed_provider` failed first. Metadata now derives supported evidence kinds from actual provider capabilities. Production reports text/OCR/Vision, not direct image support.
4. **Multimodal generation identity:** active persisted READY/complete OCR and Vision sources were composed, but registration omitted their generation identity, falsely reporting active_generation_unavailable. The composition regression failed on generation_active=False. Readiness now binds a deterministic digest of the exact composed persisted representation/generation identities. Asset inventory alone does not count as a derived generation; absent generations remain unready. No alias/activation/write occurred.
5. **HTTP numeric coercion:** actual authenticated TCP evidence request with candidate_budget=true returned 200. Failed-first schema tests had 10 failures/3 passes, including boolean/float/string coercion and positional boolean acceptance. Strict integer budget/page/section fields now reject these inputs. Thirteen new regressions pass; actual HTTP returns 422 invalid_input with safe correlation ID. Valid integer DTOs, signed cursors and public tool names are unchanged.

Changed product files in this run: core engine.py and phase85/runtime.py; server app.py, mcp/server.py, schemas/retrieval_v2.py, services/capabilities_v2.py and services/delivery.py. Regression files: core test_engine.py/test_phase85_runtime.py, server test_capabilities_v2.py/test_retrieval_v2.py. Added opt-in sanitized runners: scripts/verify_completed_stage_mcp.py and scripts/verify_completed_stage_http.py. Existing unrelated/inherited modifications were not discarded.

The subsequent sixth repair additionally changed core delivery.py, its unit test_delivery.py, and server routers/delivery.py, plus the existing composition files. Architecture and report index/current preparation were reconciled; the five requested reports,53-operation JSON manifest and two runners are intended new files, not ignored-only evaluators.

## Actual persisted production and transport evidence

Read-only immutable census: 44 original-document references, 464 occurrences, 469 asset-catalog rows, 463 succeeded OCR and 463 succeeded Vision derivations; all 469 catalog JSON references exist under the configured blob root. Active generation aliases include one OCR, one Vision, one visual-vector and 44 structured entries, all ready/complete/failed=0. Visual semantic retrieval still requires its configured query provider; an alias alone does not activate that provider.

Final-source certified stdio, 2026-09-28T04:30:29–04:30:42Z: all 14 invoked, none isError; two-page evidence completion; original PDF and asset binaries each 1,024 bytes; two persisted analyses; 31 structured descriptors; one-row query/continuation and valid empty query; retained answer with one citation; V2 answer complete/citation_resolved with one citation. Binary and FinalQA DTOs do not expose request_id; execution identity is not a fabricated request ID. Representative IDs are in the [14-tool record](mnemo-14-tool-external-acceptance-matrix.md).

Actual authenticated loopback SSE, 04:34:25–04:34:31Z, repeated all 14 and structured pagination/empty; FinalQA complete/citation_resolved with one citation. Temporary listener was removed. Real TCP HTTP, 04:25:57–04:25:58Z, passed 20 authenticated requests plus missing-authentication 401: scoped capabilities, notebook/source/summary/timeline/insight/graph reads, two-page evidence, exact chunk, 80-character continuation rejection, boolean rejection, structured positive describe, original PDF/asset bytes and persisted analysis. This is localhost, not public HTTP.

FinalQA publishes to the separately governed operational store; this is an expected authorized operational write, not a protected corpus mutation. Optional OCR generation remains profile_not_configured while persisted OCR search/delivery works. Parsed-document blocks absent from the immutable corpus remain unavailable; successful original delivery is not proof of missing block availability.

## Final validation

- `MNEMO_CI=1 uv run --no-sync --extra dev pytest -q --cov=mnemo --cov=mnemo_server --cov-report=term-missing:skip-covered --cov-report=xml`: **2,747 passed, 18 skipped, nine warnings, 90.31%, 225.58 seconds**; no xfails or XPASS. Coverage also emitted two module-not-measured diagnostics.
- Focused final engine/runtime/capability/retrieval/security/direct/stdio/SSE/HTTP old/new matrix: **112 passed, one pytest-cache warning**, 35.76 seconds.
- Ruff whole tree lint/format pass (525 Python files at that gate); strict mypy **291 source files** pass, compileall and uv lock --check (171 packages) pass.
- All three Python sdist/wheel builds **0.25.0** pass; frontend format/lint/typecheck/test/build pass, **one test, 100% frontend coverage**.
- All three Compose configs and all three Docker image builds pass against corrected product source.
- Diff check passes. Final report-link check is recorded in the completion follow-up below.

The 18 established local_database exclusions remain explicit. The known unrestricted historical protected-manifest lifecycle assertion was not repaired by altering authority and the unrestricted suite is not claimed green. Existing pytest-cache permissions, dependency deprecation/openpyxl/Qdrant warnings and dangling old dist-info warning are disclosed. An earlier focused invocation passed tests but failed the full-repository coverage threshold on a subset; it was rerun with --no-cov, not used as the full coverage gate.

## Deployment identity

Forward restarts used the existing scheduled task `Mnemo Tunnel` and unchanged signed launcher. Final restart: **2026-09-28T04:30:03.959Z**; tunnel **69952**, launcher Python **84316**, interpreter **37160**, parent cmd **18588**. Previous tunnel 69860/Python65024/92580 were stopped; cmd83648 had already exited during child cleanup (benign termination race). No graceful-stop control was exposed by this CLI, so this was controlled process termination/restart, not a fabricated graceful API operation. The unrelated tunnel process was not touched.

The editable .venv resolves mnemo and mnemo_server to this workspace's core/server directories. Full product manifest over **291** Python source files (core/server/email plugin), sorted POSIX relative path + space + SHA256 per file, newline-joined without trailing newline: **dc563a2a5486c235956fabc6e46db577920d5e76277eb67c125c03ffc075560d**. This full-source algorithm differs from older changed-file-only digests. It is operator attestation, not an MCP-exposed source revision. No package reinstall was necessary for editable loading; packages were independently built.

Tunnel health/ready return200 and control-plane polling is current. This is NOT an authenticated public application invocation. No connected Mnemo tool or authorized external application client is available in this task; independent ChatGPT is the required final external client.

## Protected checkpoint (before = after observed tests/restart)

| Resource | SHA256 | Bytes | UTC mtime |
|---|---|---:|---|
| Production | 3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c | 189804544 | 2026-09-01T11:09:20.1047581Z |
| WP16 | 18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d | 37195776 | 2026-08-29T13:37:31.2308106Z |
| Phase8.5 evaluation | bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84 | 45592576 | 2026-09-08T06:41:25.6366051Z |
| Phase8.6 evaluation | 9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2 | 52600832 | 2026-09-08T08:14:51.7220651Z |

Production/WP16 sidecar-free. Both evaluation WAL:0 bytes, e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855; both SHM:32768 bytes, fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb; original mtimes retained. Manifest e579727c8867c92d4ca7fe05256a35d74942077f86b86a6fad9938ff3b4fc566; launcher007ee235783cb8f673a2f9c135bc38269ba2a355057c5cd119c0125e471fde22; activation c17a7f5531cc75795fb63c6f53682d30eb6ed831127db95038d3d1741cd25525; certificate1a69e95796b98abcc1f4f6484692481058bff776b454a14e3a0b35d86f16312a; final evidence0255160992fc1ed2fdc5b5c6bfb55bb442b55018655f511274d698569a06230c; convergence b5ccccb9787773ef10f5a6364bbc80ed98324640ea5438da604ebfaf2b7c2b23. Sole ACTIVE generation remains fc85192e-f672-4cc0-9539-b4b063bb8f41. Credentials were never printed.

## Exact remaining actions, not missing-integration excuses

1. Owner must execute the [complete connected-tool prompt](mnemo-final-external-chatgpt-acceptance-prompt.md) against the existing tunnel. It must prove new-source public application behavior, particularly new delivery registrations and cited FinalQA. No external acceptance is awarded here.
2. Fresh authenticated external results must join the new-source direct/stdio/SSE/HTTP evidence before Module8.8.9 four-transport behavioral certification. Existing signed startup convergence remains immutable configuration evidence, not a new behavioral certificate.
3. Public HTTP coverage requires an owner-authorized authenticated HTTP endpoint/runner; the existing tunnel forwards MCP stdio and does not establish public exposure of all 53 REST operations. Local write/stream tests use disposable fixtures. A governed writable workspace and any optional external adapter need a separately approved configuration to serve mutation endpoints in production; the current certified workspace is deliberately immutable_query_only. No configuration identity was changed to evade that boundary.
4. If original-document **blocks** or new OCR/image-model generation must be added to the immutable production identity, a separate approved staging/identity-bound certification and activation decision is required. Do not copy evaluation artifacts or modify protected storage in place. Existing bytes/analyses/text-QA already succeed; missing-generation creation is NOT required merely to repair those successful routes.

No next-stage/tool15 work, no Stage7 acceptance, no full Phase8.8 GO or signed certification is inferred from green local tests.

## Final applied repair and superseding exact-tree evidence — 2026-09-28

Earlier validation/deployment above is retained as an intermediate checkpoint, not the final source. A subsequent real HTTP FinalQA succeeded and replayed, but GET `/v2/notebooks/{notebook_id}/final-qa/{assistant_turn_id}/evidence` returned404 (correlation107ffd7c-7e68-4a06-ade9-a6a4dabf013f). Root cause: delivery read execution/snapshot records from the immutable corpus instead of the separately governed operational store used by FinalQA.

Added `test_final_qa_delivery_uses_separate_store_and_checks_actor_before_snapshot`: failed first with unsupported `execution_store`; corrected the core reader and all three server compositions to bind the existing operational store. The HTTP adapter passes the authenticated actor; ownership/notebook mismatch returns safe not-found **before** snapshot access. The old primary-store contract remains compatible for noncertified storage implementations; no production cross-store fallback is introduced. The two delivery test files passed21 tests. A temporary mypy command named a nonexistent plugin directory; corrected to the actual workspace member, then all291 source files passed. No failing gate is hidden.

Post-fix actual HTTP: 2026-09-28T04:48:46–04:49:02Z, **23 authenticated requests plus one missing-auth401** passed. FinalQA `citation_resolved`, one citation,16.10 seconds; identical replay same execution; evidence GET200 returned two persisted items for assistant turn43278262-b0c9-47a3-9912-28631886720e. No protected-corpus writes; expected operational execution/snapshot writes only.

**Superseding final validation:** 2,748 passed,18 skipped,nine warnings,90.31%,227.71 seconds; no xfails/XPASS. Expanded focused suite133 passed,one cache warning,39.10 seconds. Whole-tree Ruff lint/format, strict mypy291, compileall, lock171, three Python package builds, frontend format/lint/types/one test100%/build, three Compose configs and three actual Docker builds passed after the repair.

**Superseding final deployment:** forward restart2026-09-28T04:49:40.519Z, existing tunnel89408, parentcmd82088, venvPython86600, interpreter92140. Final full291-file product manifest **61aee75f5496d83387b533a3c383ea2fba6a6b1ea2e746e85378a8ce2b80f37b**. Real certified stdio all14 passed04:51:06–04:51:14Z, FinalQA2.74seconds/two citations. Real authenticated loopback SSE all14 passed04:51:40–04:51:45Z, FinalQA2.33seconds/two citations. Temporary SSE process90240/84048 and listener8059 were removed. Direct public dispatch/security/old-new fixture evidence is in the133-test matrix.

An initial tunnel health check during concurrent builds/model probes timed out. After probes finished and the temporary SSE service was removed, health and ready returned200 and control-plane poll1790571144 passed. No protected configuration or authentication changes were made. Health success is not authenticated external application evidence.

The final read-only protected checkpoint independently reproduced **every** database, sidecar and signed-artifact hash/size/mtime in the table above; production/WP16 remain sidecar-free; evaluation sidecars unchanged; exactly one unchanged ACTIVE generation. There is no separately connected Mnemo client in this Codex task; fresh public-tunnel application and public HTTP evidence remain the exact owner/external actions specified above, not fabricated local successes. Final Git inventory and document checks follow below.

Documentation gate:412 Markdown documents parsed,411 relative file targets checked,zero missing after excluding inline/fenced code (first-pass false positive was a quoted Python class declaration in a historical report). Heading-anchor resolution was not checked. `git diff --check` passed. main/origin/main remain5d2612fef6d26cc1e1b0547bb5bd3da6abf21187;34 modified tracked/19 untracked/0 staged. Complete cumulative intended/inherited inventory:

```text
 M .dockerignore
 M docs/README.md
 M docs/architecture/current/mnemo_architecture_v2.md
 M docs/architecture/current/mnemo_engineering_roadmap.md
 M docs/governance/README.md
 M docs/reports/README.md
 M mnemo-core/mnemo/delivery.py
 M mnemo-core/mnemo/engine.py
 M mnemo-core/mnemo/phase85/runtime.py
 M mnemo-core/mnemo/retrieval/advanced.py
 M mnemo-core/mnemo/retrieval/structured_datasets.py
 M mnemo-core/mnemo/storage/composite.py
 M mnemo-core/mnemo/storage/structured.py
 M mnemo-core/tests/unit/test_advanced_retrieval.py
 M mnemo-core/tests/unit/test_composite_storage.py
 M mnemo-core/tests/unit/test_delivery.py
 M mnemo-core/tests/unit/test_engine.py
 M mnemo-core/tests/unit/test_phase85_runtime.py
 M mnemo-server/mnemo_server/app.py
 M mnemo-server/mnemo_server/mcp/server.py
 M mnemo-server/mnemo_server/routers/delivery.py
 M mnemo-server/mnemo_server/schemas/retrieval_v2.py
 M mnemo-server/mnemo_server/schemas/structured_v2.py
 M mnemo-server/mnemo_server/services/capabilities_v2.py
 M mnemo-server/mnemo_server/services/delivery.py
 M mnemo-server/mnemo_server/services/production_storage_composition.py
 M mnemo-server/mnemo_server/services/structured_v2.py
 M mnemo-server/tests/test_capabilities_v2.py
 M mnemo-server/tests/test_mcp_immutable_schema_matrix.py
 M mnemo-server/tests/test_mcp_transport_contract_matrix.py
 M mnemo-server/tests/test_production_storage_composition.py
 M mnemo-server/tests/test_retrieval_v2.py
 M mnemo-server/tests/test_structured_schema_boundaries.py
 M mnemo-server/tests/test_structured_v2.py
?? docs/governance/active/phase_8_6_serving_promotion_gate.md
?? docs/reports/operations/mnemo-14-tool-external-acceptance-matrix.md
?? docs/reports/operations/mnemo-all-completed-stages-full-system-remediation.md
?? docs/reports/operations/mnemo-final-external-chatgpt-acceptance-prompt.md
?? docs/reports/operations/mnemo-final-four-transport-certification.md
?? docs/reports/operations/mnemo-http-endpoint-acceptance-matrix.md
?? docs/reports/operations/mnemo-http-test-manifest.json
?? docs/reports/operations/mnemo-module-8-8-10-local-implementation.md
?? docs/reports/operations/mnemo-module-8-8-11-local-implementation.md
?? docs/reports/operations/mnemo-stage-6-external-audit-remediation.md
?? docs/reports/operations/mnemo-stage-6-external-verification-preparation.md
?? docs/reports/operations/mnemo-stage-6-final-acceptance-gate-reconciliation.md
?? docs/reports/operations/mnemo-stage-6-final-contract-and-acceptance-gate-audit.md
?? docs/reports/operations/mnemo-stage-6-stage-7-external-chatgpt-verification-prompt.md
?? docs/reports/operations/mnemo-stage-7-forensic-audit-remediation-and-stage-6-closure.md
?? mnemo-server/tests/test_phase86_exposure_boundary.py
?? mnemo-server/tests/test_stage6_structured_forensic.py
?? scripts/verify_completed_stage_http.py
?? scripts/verify_completed_stage_mcp.py
```
