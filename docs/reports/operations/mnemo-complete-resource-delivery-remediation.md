# Complete resource delivery remediation — 2026-09-28

## Verdict and scope

RESOURCE_DELIVERY_REQUIRES_SPECIFIC_ACTION

Available implementation corrections and local binary reconstruction are complete. Complete persisted-block text delivery for the two protected production versions is unavailable because their parsed IR is absent; creating/activating that representation requires separately authorized governed staging and certification. Actual external ChatGPT byte materialization remains an independent client gate. Neither limitation is represented as success.

No Stage7, search_image/tool15, Git publication, credential change, evaluation promotion, protected-store modification or signed-artifact rewrite is authorized/performed here. Forward deployment uses the unchanged certified launcher and scheduled task, never old-code rollback.

## Authority and baseline

Final post-restart witnesses: real certified stdio executed all 14 tools in 25 calls at 10:10:01.709497–10:10:26.794345 UTC; authenticated loopback SSE executed all 14 in 25 calls at 10:13:31.406846–10:13:46.870317 UTC. Both include successful FinalQA/provider stop and immutable replay, structured positive/empty paths, unchanged exhaustive continuation, changed-budget conflict and tamper rejection. Actual arguments, schemas, request/correlation IDs and timings are preserved in [sanitized MCP observations](mnemo-resource-mcp-observations.json). Empty summary/timeline/insight results are recorded as empty, not fabricated nonempty successes.

Post-restart full-resource reconstruction independently passed again through both adapters: stdio 10:07:32.145990–10:08:24.509489 UTC, with indexed transfer manifest; SSE 10:13:51.475080–10:13:54 UTC, raw received range files and manifest at C:/Users/athar/AppData/Local/Temp/mnemo-reconstruction-g0y3ty7d/transfer-manifest.json. Each reproduced the 3,821,824-byte six-page PDF and 704,901-byte JPEG exactly. The temporary loopback SSE worker was stopped after testing; the existing production tunnel/Python process tree remains running. These are operator-local adapter observations, not authenticated external ChatGPT requests.

Read current docs/README, architecture/roadmap, governance, ADR-0065/0073 delivery contracts and ADR-0076/0077/0078 security/certification boundary; earlier full-system,14-tool/53HTTP/four-transport/cursor-FinalQA reports. The latest black-box findings are supplied in the owner's request; no separate checked-in black-box report was located. Prior reports are historical claims, not substitutes for this run.

Initial main and origin/main:5d2612fef6d26cc1e1b0547bb5bd3da6abf21187;49 modified tracked,21 untracked,zero staged.291-file product manifest reproduced8141d5090f25a26b742c8417d87dff7a3f1473a1f2b277792ba20f60c0504274. Existing intended uncommitted work preserved.

Final product manifest832fad3b4a3a26bf3f5bb3e3b124a067997b2d5c9fc580a4a9c3828cf5391d32: SHA256 over sorted ordinal POSIX relative path + space + per-file SHA256, newline-joined without trailing newline, all291 core/server/email-plugin Python files. Source—not Git HEAD—changed. Editable .venv resolves mnemo to workspace mnemo-core/mnemo and mnemo_server to workspace mnemo-server/mnemo_server. No package replacement is required for these editable modules; all three packages were built separately.

## Findings, reproductions and corrections

### D-01 — confirmed representation/error mismatch

Authorization finds the exact PDF and code versions; filesystem parsed IR read returns None. Both old expand_document and full-selector expand_document_v2 raised NotFoundError, laundering missing representation into unknown resource. Independent test_missing_parsed_representation_is_not_unknown_document failed first with NotFoundError. Now a nonretryable DependencyUnavailableError subclass emits allowlisted delivery.representation_unavailable, preserving safe category/correlation/authorization-before-discovery. Both views through real MCP return capability_unavailable, not invented parsed content.

Additive text view renders persisted block fields deterministically, reports parsed_text/v1, total_items and explicit separators; existing block responses identify parsed_blocks/v1/count where selected units are known. HTTP reuses the same service via existing GET document route ?mode=text. No new tool/endpoint, duplicate delivery implementation, query-dependent enumeration or protected generation.

[Full-text evidence/remaining production action](mnemo-full-document-text-certification.md): reopened disposable twelve-page IR reconstructs source truth exactly. Production original bytes and exact chunks remain available; full parsed/text representation remains unavailable. Existing staged ingestion/FilesystemBlobStore.put_parsed_document contract works on disposable storage, not silently promoted to protected production.

### D-02 — confirmed metadata insufficiency; server byte corruption not reproduced

Core ranges already deliver correct original bytes. Original-document MCP metadata lacked actual start/end/returned-byte count and canonical ancestry present on assets; page URI was reused across different payloads. Added rangeStart/rangeEnd (exclusive),rangeEndExclusive=true,returnedBytes,snapshotIdentity,originalMediaType,notebook/source/document/version ancestry, retaining totalBytes/hash/cursor/completeness. Native blob URIs identify the exact byte range. This improves unambiguous reconstruction; URI reuse causing connector corruption remains a hypothesis, not a proven causal attribution.

Real native-MCP byte reconstruction passed, not merely service metadata: one-call PDF3821824 bytes; eight524288-ceiling calls reproduce the same hash eb4fe330163f7d89535ca48f792204a16da042bb2e4895a6030102df20a63984, valid PDF/six pages. Separate received files reopened and concatenated. [Transfer manifest](mnemo-resource-transfer-manifest.json) records every range and actual hash.

### D-03 — fresh bytes correct; earlier attachment not linked

ImageContent, negotiated EmbeddedResource, eleven65536-ceiling ranges and JPEG extracted from reconstructed PDF page1 are byte-identical.704901 bytes, expected hash cab6378eeb056237af3b785d9421e8fb0c6c889b730b37e719dcea8247acb19a, decoded JPEG3576×2512. Earlier corrupt mounted file has no proven association with these fresh calls. Native optional binary_format:resource supports complete-image materialization without JSON-base64 transport or an unaudited download endpoint. Default image behavior retained; partial-image bytes remain application/octet-stream, with truthful original MIME.

### Additional confirmed security defect — delivery actor binding

test_binary_cursor_rejects_other_authorized_actor failed first DID NOT RAISE: two otherwise-authorized actors could reuse the same delivery cursor. Request-local for_actor copies the service, not shared mutation, binds actor to all delivery codec paths. MCP/HTTP derive it from authenticated server principal. Unknown/unbound legacy public cursors require restart, never silently acquire an actor. Original/asset and block/full-selector fingerprints also bind exact requested limits before server clamping, preserving snapshot/resource/scope/expiry/tamper checks. An old unit expectation changed an omitted byte ceiling to20 while effective cap remained4; now it explicitly asserts cursor conflict and resumes with unchanged arguments. This strengthens rather than weakens the accepted immutable-parameter contract.

## Applied file inventory (this task, inherited changes not discarded)

Product:
- mnemo-core/mnemo/delivery.py
- mnemo-core/mnemo/models/delivery.py
- mnemo-server/mnemo_server/mcp/tools.py
- mnemo-server/mnemo_server/routers/delivery.py
- mnemo-server/mnemo_server/schemas/delivery.py
- mnemo-server/mnemo_server/services/delivery.py
- mnemo-server/mnemo_server/typed_errors.py

Tests/probes:
- mnemo-core/tests/unit/test_delivery.py
- mnemo-server/tests/test_mcp_delivery.py
- mnemo-server/tests/test_mcp_transport_contract_matrix.py
- mnemo-server/tests/http_tcp_audit_plugin.py (opt-in machine-readable observed TCP manifest)
- scripts/verify_resource_reconstruction.py (new)
- scripts/verify_completed_stage_mcp.py (sanitized actual argument logging)

Current documentation: architecture delivery description, documentation/report indexes and this five-report set plus resource transfer/HTTP observed-operation JSON. Accepted ADR decisions and historical test results remain intact.

## Reconstruction and persisted analysis

Real certified stdio09:46:21.118913–09:46:57.895949Z; final-source real authenticated loopback SSE completed09:48:54.281498Z. PDF eight ranges/JPEG eleven; one-call blob/image equivalence; stable ancestry/count/hash/snapshot; no gaps/overlap/duplicates/missing terminal bytes.

Complete persisted OCR/Vision actual content saved privately: OCR one region2875 payload bytes, Vision five observations2835 bytes, complete; derivation/generation/occurrence/version identities in transfer manifest. Explicit per-record256-region/256-observation and response-byte bounds remain, with bounded+analysis_item_bounds_applied or typed delivery-limit failure. No large-record content cursor is promised; no provider activation occurred.

The PDF skill influenced verification by adding actual PDF decoding/page-count and read-only first-page rendering/visual inspection; no PDF authoring or protected file alteration.

## All14 MCP regression matrix

Same real certified production notebook, source/doc/version fixtures; commands:
- uv run --no-sync python scripts/verify_completed_stage_mcp.py --model-cache D:\Mnemo\phase8.5.11-models\huggingface\hub --final-qa
- same with --sse-url http://127.0.0.1:8059/sse --final-qa

| Tool | Fresh real stdio and authenticated loopback SSE evidence |
|---|---|
| get_capabilities | Global/scoped identities and truthful lifecycle |
| list_notebooks | Authorized production inventory |
| get_notebook_summary | Valid authorized result; genuine empty fields not fabricated |
| get_timeline | Bounded authorized timeline |
| get_source_insights | Authorized existing source; valid empty allowed |
| search_all_notebooks | Bounded V1 discovery |
| query_notebook | Retrieval/synthesis; top1/top5 scope/ranking retained |
| search_evidence | Ranked/partitioned metadata parity; exhaustive continuation;80-character limit; requested-budget/tamper rejection |
| query_structured | Existing READY authorized production projection describe/query |
| get_document | Original resource positive; full blocks/text honest unavailability on specified production versions |
| get_document_chunk | Exact canonical authorized chunk |
| get_asset | Occurrence inventory and actual original byte payload |
| get_image_analysis | Two complete persisted OCR/Vision records |
| run_final_qa_v2 | Approved bounded provider, citation-resolved stop/complete plus exact replay |

Final-source stdio all14 observed09:46:05–09:46:15Z; SSE09:48:54–09:49:06Z. New reconstruction runner independently verifies actual resource payloads. Old/new schema direct/real stdio/SSE/HTTP fixtures preserve prior F-1/F-2, structured, cursor and FinalQA regressions.

Post-restart actual stdio all14 completed10:10:01.709497–10:10:26.794345Z,
25 calls including safe cursor negatives and FinalQA replay. Exact sanitized
arguments, schemas, UTC intervals, IDs and outcomes are in the
[operator observation manifest](mnemo-resource-mcp-observations.json).
Post-restart actual byte reconstruction completed10:07:32.145990–10:08:24.509489Z;
the transfer manifest now includes per-range UTC intervals, MIME and exposed
request IDs (for example PDF multipart page1 be738d56-26ad-49c4-9d22-e96da8c03775).
This is still a separate local stdio client, not the external ChatGPT connection.

## HTTP operation accounting

Current manifest remains53 operations; text is an additive query on an existing route, not a new endpoint. Opt-in actual network fixture run231 passed/four warnings; machine comparison53 expected/53 observed/zero missing. [Observed operations](mnemo-resource-http-observed-operations.json) enumerates all methods/paths; [existing endpoint manifest](mnemo-http-test-manifest.json) supplies schemas. Backends include disposable fixtures/test doubles; this is real TCP serialization, not production mutation. Positive/invalid/ACL/mutation paths are exercised appropriately; seeing a route is not labeled positive in every mode.

Real certified TCP production probe passed09:44:49–09:45:01Z for delivery/analysis/structured/FinalQA/replay and missing-authentication401. Earlier raw output includes53-operation OpenAPI inventory and27 authenticated requests. No claim public REST is exposed by the stdio tunnel. The safe production corpus was not mutated.

## Validation and initial failures

Focused final delivery+MCP+old/new+Stage6 security set58 passed,one cache warning. Earlier78-test matrix passed; final focused assertions add native-blob negotiation and reopened IR. Complete release-run final result is recorded in the completion section below.

Intermediate full run1 failed2777 passed18 skipped10 warnings90.29%: test_mcp_delivery_uses_server_configured_bounds expected factory(engine,config), omitting newly required trusted actor. Fixed to explicitly assert principal_from_claims(None), not weaken security. Subsequent full run2778 passed18skips9warnings90.29%; a final added ordinary blob-negotiation regression is included in the final exact-tree run. No new skip/xfail and no threshold reduction.

Development-only mistakes were corrected: temporary exception construction passed an unsupported code keyword (replaced by typed subclass); an asyncio marker incompatible with existing AnyIO policy (corrected to the repository mark); no test suppressed. A premature SSE client attempt failed before startup completed; an unnecessary second temporary worker then hit an occupied port and exited. Only the original isolated worker served the successful probe; temporary workers removed. One model-backed stdio probe emitted certified startup failure under concurrent heavyweight probes; precise cause was not exposed by the sanitized CLI. After stopping temporary probes, sequential final stdio passed. Resource contention is a bounded hypothesis, not a proven defect or bypass justification.

Ruff lint/format, strict mypy291, compileall,171-package lock check, three0.25.0 sdist/wheel builds, frontend format/lint/typecheck/one Vitest test100%/production build and three Compose configs pass. All three actual Docker builds pass; core initial registry502 was retried successfully. Server rebuilt against final source. No image-build pass inferred from Compose.

18 established local_database exclusions remain; known unrestricted historical signed-manifest lifecycle assertion is separately disclosed, not repaired by altering its authority or claimed green. Cache permissions, package dist-info/deprecations/Qdrant/openpyxl/coverage import warnings are disclosed. Documentation/diff final checks are in completion.

## Protected-state checkpoint

All values independently read before edits and repeated during tests; final post-deployment comparison is in completion. Read-only hashes do not open SQLite or create sidecars.

| DB | SHA256 | Bytes | UTC mtime |
|---|---|---:|---|
| Production |3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c|189804544|2026-09-01T11:09:20.1047581Z|
| WP16 |18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d|37195776|2026-08-29T13:37:31.2308106Z|
| Phase8.5 evaluation |bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84|45592576|2026-09-08T06:41:25.6366051Z|
| Phase8.6 evaluation |9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2|52600832|2026-09-08T08:14:51.7220651Z|

Production/WP16 WAL,SHM,journal absent. Both evaluation WAL0/e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855; SHM32768/fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb.8.5 WAL/SHM mtimes2026-09-08T08:29:44.8384566Z/11:45:09.0813968Z;8.6 WAL/SHM08:30:27.2461167Z/13:52:55.1970116Z. No journals; pre-existing sidecars preserved.

Signed/authority SHA:
- production manifest e579727c8867c92d4ca7fe05256a35d74942077f86b86a6fad9938ff3b4fc566 (4069 bytes;2026-09-24T07:44:51.3412352Z)
- certified launcher007ee235783cb8f673a2f9c135bc38269ba2a355057c5cd119c0125e471fde22 (290;15:23:23.8479641Z)
- activationc17a7f5531cc75795fb63c6f53682d30eb6ed831127db95038d3d1741cd25525 (1059;07:44:29.1073100Z)
- certificate1a69e95796b98abcc1f4f6484692481058bff776b454a14e3a0b35d86f16312a (2448;15:21:40.4465551Z)
- final evidence0255160992fc1ed2fdc5b5c6bfb55bb442b55018655f511274d698569a06230c (1415;15:21:40.4550622Z)
- signed convergenceb5ccccb9787773ef10f5a6364bbc80ed98324640ea5438da604ebfaf2b7c2b23 (3344;09:46:26.8983082Z).

Exactly one ACTIVE generationfc85192e-f672-4cc0-9539-b4b063bb8f41; credential values never printed or changed. Historical signed convergence is preserved, not retroactively used as final-source behavioral certification.

## Remaining precise actions

Final documentation validation:134 relative link targets checked,zero missing; git diff --check passes. Final Ruff lint and format check passes (527 Python files). The temporary SSE listener8059 is absent after cleanup; production process tree13044/89256/67256/5512 remains running.

Final post-probe checkpoint independently rehashed all four databases and evaluation sidecars, checked byte sizes/UTC mtimes, verified all six authority/artifact hashes and exactly one unchanged ACTIVE generation. No discrepancies. Source manifest remains832fad3b4a3a26bf3f5bb3e3b124a067997b2d5c9fc580a4a9c3828cf5391d32; final working tree53 modified tracked/30 untracked/zero staged. No Git publication occurred.

1. Owner-authorized governed staging/certification for missing production parsed IR, or supply an already authorized complete parsed-version fixture; this task cannot mutate protected corpus/manifests or promote evaluation data.
2. Owner-connected external ChatGPT must materialize fresh one-call/multipart PDF/JPEG and compute hashes. Operator stdio/SSE bytes, previews, mounted older attachments and tunnel health are not that evidence.
3. Actual authenticated public-tunnel application test remains unavailable to this engineering session; public REST is not established. No four-transport certificate or external acceptance self-awarded.

Use [complete reconstruction prompt](mnemo-external-resource-reconstruction-prompt.md). The locally repaired system can be retested without confusing truthful unavailable text with operational text delivery.

## Final completion checkpoint

Final exact-product-source CI-safe run: **2779 passed,18 skipped,nine warnings,90.29% coverage,403.03 seconds**; no xfails/XPASS. Final focused set58 passed/one warning; final aggregate disposable TCP set231 passed/four warnings,53/53 observed operations/zero missing. Ruff lint/format527 files, strict mypy291, compileall, lock check171, all three Python builds, frontend gates/one test100%, three Compose configs and three actual Docker builds pass. Documentation link check120 relative targets/zero missing; diff check passes. The unrestricted historical manifest assertion is not rerun or described as passing.

Forward deployment **2026-09-28T09:59:54.5668825Z**, unchanged scheduled task Mnemo Tunnel/signed batch. Stopped verified old interpreter96476,venv93940,cmd94652,tunnel96024; no graceful CLI control was exposed, so controlled process termination is recorded accurately rather than called a graceful API shutdown. Unrelated tunnel20956 was not stopped. New tunnel13044,cmd89256,venvPython67256,interpreter5512; editable workspace module paths verified. Product manifest remains **832fad3b4a3a26bf3f5bb3e3b124a067997b2d5c9fc580a4a9c3828cf5391d32**. No old-code restoration, endpoint/authentication alteration or serving-role change. Fresh packages built; editable loading did not require reinstall.

Healthz200/readyz200 at09:59:56.7679109/7756988Z; subsequent API status main enabled/external/stdio/probe ok, control_plane route direct/proxy none. Server-owned config production true/api-key, same ACTIVE generation. These are local process/control-plane facts, NOT authenticated external application calls. Final-source authenticated local stdio/SSE positive applications and byte reconstruction were repeated after the forward restart on the identical source, as indexed above; no product-source change follows them.

After final restart/tests all four DB SHA/size/UTC mtimes match the before table exactly; production/WP16 sidecars absent; evaluation WAL/SHM hashes,bytes,mtimes unchanged; no journals. Manifest,launcher,activation,certificate,final-evidence,convergence SHA/size/mtimes match accepted before values exactly. Exactly one unchanged ACTIVEfc85192e-f672-4cc0-9539-b4b063bb8f41. No credential value exposed.

Final Git main/origin main remain5d2612fef6d26cc1e1b0547bb5bd3da6abf21187; **53 modified tracked files,30 untracked,zero staged**. This includes inherited intended work, not53 new changes in this task. No git add,commit,push,PR,merge or release. No protected-store writes/migration/reindexing,credential rotation,signed-artifact rewrite or Phase8.6 promotion. Complete prompt is in the indexed handoff.

Exact final working-tree inventory:
```text
M .dockerignore
 M docs/README.md
 M docs/architecture/current/mnemo_architecture_v2.md
 M docs/architecture/current/mnemo_engineering_roadmap.md
 M docs/governance/README.md
 M docs/reports/README.md
 M mnemo-core/mnemo/delivery.py
 M mnemo-core/mnemo/engine.py
 M mnemo-core/mnemo/interfaces/errors.py
 M mnemo-core/mnemo/llms/ollama.py
 M mnemo-core/mnemo/models/advanced_retrieval.py
 M mnemo-core/mnemo/models/delivery.py
 M mnemo-core/mnemo/models/final_qa_execution.py
 M mnemo-core/mnemo/models/multimodal.py
 M mnemo-core/mnemo/phase85/runtime.py
 M mnemo-core/mnemo/retrieval/advanced.py
 M mnemo-core/mnemo/retrieval/final_qa_provider.py
 M mnemo-core/mnemo/retrieval/multimodal.py
 M mnemo-core/mnemo/retrieval/structured_datasets.py
 M mnemo-core/mnemo/storage/composite.py
 M mnemo-core/mnemo/storage/multimodal.py
 M mnemo-core/mnemo/storage/structured.py
 M mnemo-core/tests/unit/test_advanced_retrieval.py
 M mnemo-core/tests/unit/test_composite_storage.py
 M mnemo-core/tests/unit/test_delivery.py
 M mnemo-core/tests/unit/test_engine.py
 M mnemo-core/tests/unit/test_final_qa_provider_adapter.py
 M mnemo-core/tests/unit/test_multimodal.py
 M mnemo-core/tests/unit/test_ollama_llm.py
 M mnemo-core/tests/unit/test_phase85_runtime.py
 M mnemo-server/mnemo_server/app.py
 M mnemo-server/mnemo_server/mcp/server.py
 M mnemo-server/mnemo_server/mcp/tools.py
 M mnemo-server/mnemo_server/routers/delivery.py
 M mnemo-server/mnemo_server/schemas/delivery.py
 M mnemo-server/mnemo_server/schemas/retrieval_v2.py
 M mnemo-server/mnemo_server/schemas/structured_v2.py
 M mnemo-server/mnemo_server/services/capabilities_v2.py
 M mnemo-server/mnemo_server/services/delivery.py
 M mnemo-server/mnemo_server/services/final_qa_v2.py
 M mnemo-server/mnemo_server/services/production_storage_composition.py
 M mnemo-server/mnemo_server/services/structured_v2.py
 M mnemo-server/mnemo_server/typed_errors.py
 M mnemo-server/tests/test_capabilities_v2.py
 M mnemo-server/tests/test_final_qa_v2_transport.py
 M mnemo-server/tests/test_mcp_delivery.py
 M mnemo-server/tests/test_mcp_immutable_schema_matrix.py
 M mnemo-server/tests/test_mcp_transport_contract_matrix.py
 M mnemo-server/tests/test_production_storage_composition.py
 M mnemo-server/tests/test_retrieval_v2.py
 M mnemo-server/tests/test_server_system.py
 M mnemo-server/tests/test_structured_schema_boundaries.py
 M mnemo-server/tests/test_structured_v2.py
?? docs/governance/active/phase_8_6_serving_promotion_gate.md
?? docs/reports/operations/mnemo-14-tool-external-acceptance-matrix.md
?? docs/reports/operations/mnemo-all-completed-stages-full-system-remediation.md
?? docs/reports/operations/mnemo-complete-resource-delivery-remediation.md
?? docs/reports/operations/mnemo-cursor-finalqa-external-defect-remediation.md
?? docs/reports/operations/mnemo-direct-image-integrity-certification.md
?? docs/reports/operations/mnemo-external-resource-reconstruction-prompt.md
?? docs/reports/operations/mnemo-final-external-chatgpt-acceptance-prompt.md
?? docs/reports/operations/mnemo-final-four-transport-certification.md
?? docs/reports/operations/mnemo-full-document-text-certification.md
?? docs/reports/operations/mnemo-http-endpoint-acceptance-matrix.md
?? docs/reports/operations/mnemo-http-test-manifest.json
?? docs/reports/operations/mnemo-module-8-8-10-local-implementation.md
?? docs/reports/operations/mnemo-module-8-8-11-local-implementation.md
?? docs/reports/operations/mnemo-multipart-binary-certification.md
?? docs/reports/operations/mnemo-resource-http-observed-operations.json
?? docs/reports/operations/mnemo-resource-mcp-observations.json
?? docs/reports/operations/mnemo-resource-transfer-manifest.json
?? docs/reports/operations/mnemo-stage-6-external-audit-remediation.md
?? docs/reports/operations/mnemo-stage-6-external-verification-preparation.md
?? docs/reports/operations/mnemo-stage-6-final-acceptance-gate-reconciliation.md
?? docs/reports/operations/mnemo-stage-6-final-contract-and-acceptance-gate-audit.md
?? docs/reports/operations/mnemo-stage-6-stage-7-external-chatgpt-verification-prompt.md
?? docs/reports/operations/mnemo-stage-7-forensic-audit-remediation-and-stage-6-closure.md
?? mnemo-server/tests/http_tcp_audit_plugin.py
?? mnemo-server/tests/test_phase86_exposure_boundary.py
?? mnemo-server/tests/test_stage6_structured_forensic.py
?? scripts/verify_completed_stage_http.py
?? scripts/verify_completed_stage_mcp.py
?? scripts/verify_resource_reconstruction.py
```
