# Ordered document-text delivery remediation — 2026-09-28

## Verdict and evidence boundary

ORDERED_TEXT_REQUIRES_SPECIFIC_ACTION

Implementation, final-source local reconstruction, packaging and forward deployment are complete. External text certification is **not** complete: the owner's connector must fetch the current tool schema, and a separately authorized isolated persisted-block fixture must become accessible to that external principal. This task did not authorize modifying the protected production representations. The existing certified connection has no configured mutable workspace that could safely be used implicitly.

The owner's independently reported successful eight-part PDF and eleven-part JPEG reconstruction remains accepted external history. Fresh local reconstructions below are additional evidence, not invented new ChatGPT observations.

## Baseline and authority

Initial main and origin/main: 5d2612fef6d26cc1e1b0547bb5bd3da6abf21187; 53 modified tracked files, 30 untracked files, nothing staged. All inherited changes were preserved. Initial 291-product-Python-file manifest: 832fad3b4a3a26bf3f5bb3e3b124a067997b2d5c9fc580a4a9c3828cf5391d32.

Read current architecture delivery description, canonical roadmap, governance and the five earlier resource reports. ADR-0065/ADR-0073 govern typed selectors and authoritative structured MCP content; ADR-0077 governs immutable production versus explicit mutable workspace composition. Accepted decisions are unchanged. No new tool, endpoint, serving role, promotion, production representation or credential was introduced.

Final product-content digest: cdf4bc9b3140d5b0b8063766e7b0bdd7f4154df9190b42aa17fec77b63d2313d. Algorithm: ordinal-sort 291 repository-relative POSIX product .py paths in core/server/email plugin; join each path + space + SHA-256 using newline with no trailing newline; SHA-256 UTF-8 manifest. Tests, reports and scripts are excluded. This is operator-side content attestation, not an MCP-exposed source revision.

## Confirmed causes and applied corrections

| Observation | Finding | Correction/disposition |
| --- | --- | --- |
| External client rejects text enum before invocation | The checked-out canonical input enum and handler already accepted text before this task. Fresh real stdio/SSE tools/list advertises all three modes. The reported client schema is older than the server contract; the exact proprietary connector caching mechanism is not observable here. | Clarified explicit input/description/output schema, reconciled machine-readable governance contracts, permanently asserted advertised enum. Owner must refresh/reconnect and verify a fresh external invocation; no claim of external acceptance yet. |
| Binary fields not shown in structured content | Confirmed server-controlled omission: fields existed in native content metadata but structured_content_for copied only minimal identity/MIME fields. | Allowlist verified native fields into structured resource; additive typed output-schema properties. No private paths or byte payload copied. Failing-first regression raised KeyError rangeStart; post-fix regression passes. |
| Production blocks/text unavailable | PDF/code originals and chunks exist, but their exact versions have no persisted parsed representation. Search chunks do not establish complete ordered source text. | Retain capability_unavailable / delivery.representation_unavailable. No production IR generated. Separate plan below. |
| First full suite after metadata change failed | Legacy metadata-free binary response gained source_id:null and broke its existing exact-shape compatibility assertion. | Emit this alias only when verified sourceId metadata exists. Existing test was not weakened. Final full suite passes. |
| Concurrent certified workers failed startup | Real memory-allocation failure during parallel model-backed probes, not evidence of corrupt protected stores. | Stopped identified temporary workers, executed model-backed transports sequentially, then restarted the sole intended production tunnel forward. No security bypass or rollback. |

Changes in this task: mcp/tools.py structured metadata/input guidance; mcp/contracts.py tool guidance and additive resource outputSchema; test_mcp_delivery.py failing metadata/public-schema regressions; core test_delivery.py actor/limits/snapshot/expiry/empty/Unicode tests; new persisted mixed fixture and real-transport certification tests; optional ordered fixture flag in test-only stdio/SSE children; resource reconstruction probe asserts public schema and native/structured metadata parity; current docs/index/governance corrections and this report set. Historical reports were not rewritten.

## Ordered text and security

See [mixed-content certification](mnemo-ordered-text-certification.md) and [independent truth](mnemo-ordered-text-fixture-manifest.json). Twelve persisted supported blocks across twelve pages, older/newer disposable SQLite scopes, real stdio and authenticated SSE; page sizes 1 and 3 independently reconstruct identical blocks and text. UTF-8 text SHA-256: 70f933e57255937afc39612ac54a311f7653ab9c1c7d91c20106a4db12a83493.

This fixture explicitly persists supported IR through FilesystemBlobStore and reopens it. It is not claimed to be a PDF-parser end-to-end ingestion test, not a protected representation, and not externally authorized. Expected content is a separately declared literal sequence, not obtained by asking the delivery implementation for its expected answer.

Text is full-selector rendering of persisted blocks. Concatenate payload.text + payload.separator_after exactly. Block identity is exact version/snapshot/ordinal; no invented public block UUID. Heading level, code-language labels, layout and table-header annotations are intentionally absent from the text rendering; blocks retain structure. Missing blocks never trigger chunk stitching or generation.

Tests cover actor binding, exact requested limits even when effective limits clamp identically, mode/selector changes, tamper, expiry, snapshot change, repeated page determinism, terminal page, empty/single/oversized Unicode. Existing scope/version and binary-cursor regressions remain green. One oversized item returns a typed delivery limit; it is not skipped or split without a contract.

## Fresh actual integration results

| Gate | Actual final-source result |
| --- | --- |
| Focused core delivery/MCP delivery/retained contracts/ordered transports | 61 passed, 1 pytest-cache warning, 25.51 s |
| Mixed fixture real stdio/SSE older/newer separately | 4 passed, 1 cache warning, 38.53 s |
| Complete MNEMO_CI=1 suite | 2,790 passed, 18 existing skips, 9 warnings; 256.03 s; 90.31% coverage; no xfails/XPASS |
| Real disposable TCP contracts, final rerun | 256 passed, 4 warnings, 120.14 s; observed 53 of 53 manifest operations, zero differences |
| Certified stdio all 14 tools | Actual invocations succeeded, 11:06:14–11:06:29 UTC; summaries/insights/timeline legitimately empty, not asserted nonempty |
| Certified authenticated loopback SSE all 14 | Actual invocations succeeded, 11:08:27–11:08:36 UTC; positive delivery/structured/FinalQA and replay |
| PDF/JPEG actual MCP reconstructions | One-call + 8 PDF parts + 11 JPEG parts, both final transports; exact byte hashes, PDF6 pages/JPEG3576×2512, PDF embedded JPEG identical |
| Ruff lint/format | Pass; 529 formatted Python files |
| Strict mypy | Pass, 291 source files |
| Compileall / uv lock --check | Pass / 171 resolved packages |
| Python packages | Three 0.25.0 sdist/wheel builds passed; server rebuilt after final product correction |
| Frontend | Format/lint/typecheck/test/build pass; 1 test, reported 100% frontend coverage |
| Compose / Docker | Three applicable Compose configurations pass; core/UI/server actual builds passed; final server rebuilt after last correction |
| Documentation and diff | Relative-target checks and git diff --check executed; final results recorded below |

The first full diagnostic run had 1 failed, 2,789 passed, 18 skipped, 10 warnings, 90.24% coverage; compatibility fix above resolved it. An incorrectly specified Dockerfile path failed before build; corrected docker/server.Dockerfile build succeeded. These attempts are not counted as passes. The earlier unrestricted protected-manifest lifecycle assertion remains a disclosed historical failure outside MNEMO_CI policy; it was not repaired by changing a signed manifest, and no unrestricted-suite pass is claimed. The 18 existing local_database exclusions remain; no new skips or xfails were added.

Real TCP here means actual loopback uvicorn network serialization with disposable fixture backends/test doubles. It is not public REST acceptance or proof every production mutation is enabled. WebSocket TestClient paths remain in-process. The [53-operation manifest](mnemo-http-test-manifest.json) was exactly reconciled; no destructive production HTTP tests were run.

FinalQA stdio published one approved bounded operational answer and exact replay; SSE did the same. Both returned citation_resolved, complete, termination reason stop. These are permitted governed operational records, not mutations of the immutable protected databases or signed evidence.

## Final forward deployment

Reused approved scheduled task “Mnemo Tunnel” and unchanged certified launcher. Final restart at 2026-09-28T11:09:08.5270772Z after temporary workers were closed. Tunnel PID33680 → cmd22920 → .venv Python79880 → Python312 child54892. Last observed healthz live, readyz ready, main stdio channel probe ok. Unrelated codexpro tunnel was untouched.

The .venv uses editable imports from workspace mnemo-core/mnemo and mnemo-server/mnemo_server; mcp/tools.py resolves there. Python process command is certified-tunnel-stdio under the signed launcher and existing approved model cache. Wheel packages were built, but production does not use a stale independent installed wheel. No protected configuration or signed startup identity was changed. Final server Docker config digest: e9137dd8e40428c239b662bdf0730c67a63343ef81aab2ae7bd98c1f4af9b9ee; Docker is build evidence, not the deployed runtime.

Earlier controlled restarts were at 10:48:44Z and 10:53:05Z. A process-exit race on the latter required stopping the remaining identified wrapper and starting the existing task. Concurrent probe allocation failures were diagnosed before the final sequential restart. Process termination is recorded as controlled termination, not falsely as guaranteed application-level graceful shutdown. No old process/code restoration was attempted.

Tunnel health/control-plane admission is not an authenticated external ChatGPT application call. Codex has no connected owner Mnemo client here. Fresh external mode=text and public structured metadata visibility remain unverified until the owner uses the [prompt](mnemo-final-external-text-certification-prompt.md).

## Protected before/after

[Exact checkpoint](mnemo-ordered-text-protected-checkpoint.json) records all hashes, bytes, UTC mtimes and sidecar states. Independently captured before edits and after final deployment: all match.

| Database | Bytes | UTC mtime | SHA-256, before = after |
| --- | ---: | --- | --- |
| Production | 189804544 | 2026-09-01T11:09:20.1047581Z | 3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c |
| WP16 | 37195776 | 2026-08-29T13:37:31.2308106Z | 18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d |
| Phase8.5 evaluation | 45592576 | 2026-09-08T06:41:25.6366051Z | bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84 |
| Phase8.6 evaluation | 52600832 | 2026-09-08T08:14:51.7220651Z | 9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2 |

Production/WP16 remain WAL/SHM/journal-free. Evaluation WAL0/SHM32768 and their hashes/mtimes are unchanged; no sidecars deleted. Manifest, certified launcher, activation, certificate, final evidence and signed convergence artifact match exact accepted baseline hashes in the checkpoint. Sole ACTIVE generation remains fc85192e-f672-4cc0-9539-b4b063bb8f41. No secret values printed.

## Separate representation-staging / external-fixture plan — NOT EXECUTED

Affected protected versions:
- PDF135b4fd5-15cd-5a22-89db-096dcc9b55bc / d49eb763-3bf3-54d1-aec4-bfd66ca43fe8.
- Code8abc6c73-7d1c-5248-8c28-4157de5ca51a / 7882f1db-a197-5c84-9b10-66b1fe2d3689.
Both lack persisted parsed blocks/text; original bytes and selected canonical chunks remain available.

Proposed workflow: independently hash copied original bytes, run existing PDFParser for PDF and approved PlainTextParser/code handling for the JS source under explicitly recorded parser/dependency/asset-extraction profile; persist supported ParsedDocument IR via the governed ingestion/blob API. Profile must be selected and recorded during separately approved staging, not invented as already certified. Stage outside all protected/evaluation/operational/cache roots in a server-owned absolute workspace approved under ADR-0077. Expected outputs are ordered persisted parsed blocks and their parsed_text/v1 rendering; preserve exact source/document/version ancestry and original-content identity.

Protected-state changes during staging: NONE. Copy/read protected originals only. Promotion of new representation roots or changed certified read composition/allowlists/lifecycle bindings requires separate owner authorization and fresh identity/provenance/ACL/transport certification and signed activation through existing governance. No ad-hoc write into immutable production blob roots is authorized by this task.

Integrity/rollback strategy for the staging operation only: checkpoint originals and draft content-addressed IR; quarantine/discard failed drafts, retain original certified read binding until separately approved activation, never overwrite existing content. This is not preparation to restore old in-memory Python code.

For external certification without production promotion: owner must authorize a separate isolated test connection, server-owned nonprotected store/blob roots, narrow notebook allowlist and membership for the existing intended external principal, plus required startup certification. Instantiate the already tested twelve-block truth through the existing governed persistence workflow, verify independent hashes, then supply actual deployed fixture IDs and connection identity. No broad access, implicit evaluation registry federation, protected-notebook insertion, or exposed test-harness shortcut. Existing test-only child bypasses are not an approved production composition.

Exact owner actions:
1. Refresh/reconnect existing Mnemo tool definitions; a new client must show original|blocks|text and actually invoke text.
2. Authorize/provide the isolated external fixture serving composition and scoped access above (or separately approve staging/certification of the two protected versions).
3. Run the independent external prompt using actual resulting identities and independently supplied truth.

Until step2, local UUIDs in the truth manifest must NOT be submitted as production fixtures. No external fixture availability is fabricated. Product Stage7, tool15 and external acceptance remain out of scope.

## Reproducible commands and evidence

- uv run --no-sync --extra dev pytest -q --no-cov mnemo-core/tests/unit/test_delivery.py mnemo-server/tests/test_mcp_delivery.py mnemo-server/tests/test_mcp_wp03_contracts.py mnemo-server/tests/test_ordered_text_certification.py
- MNEMO_CI=1 uv run --no-sync --extra dev pytest -q --cov=mnemo --cov=mnemo_server --cov-report=term --cov-report=xml
- PYTHONPATH=mnemo-server/tests MNEMO_CI=1 pytest -p http_tcp_audit_plugin --no-cov over the server delivery/notebook/source/session/note/query/search/insight/system/retrieval/structured/FinalQA/capability/transport/streaming/schema-boundary files.
- scripts/verify_completed_stage_mcp.py --model-cache D:/Mnemo/phase8.5.11-models/huggingface/hub --final-qa; repeat with --sse-url http://127.0.0.1:8059/sse.
- scripts/verify_resource_reconstruction.py with the same two transport configurations.
- uv run --extra dev ruff check .; ruff format --check .; strict mypy core/server/email source roots; compileall same roots; uv lock --check; uv build each package.
- docker build -f docker/server.Dockerfile -t mnemo-server:local-ordered-text-final . (plus core/UI builds and Compose checks performed).
- Start-ScheduledTask -TaskName 'Mnemo Tunnel' reused existing approved supervisor; temporary SSE worker used existing certified verifier on8059 and was stopped afterward.

[Transfer evidence](mnemo-ordered-text-binary-transfer-manifest.json) retains per-page ranges/counts/hashes/IDs/timestamps for final stdio/SSE; actual individual .bin receipts remain in local temporary reconstruction directories x56zw3j6 and zje1hj7t. Do not publish those byte artifacts/private content automatically.

Final exact Git inventory and documentation-check output follow. Nothing staged, committed, pushed, merged or published; no production representation mutation, credential rotation, signed rewrite or evaluation promotion.

## Final documentation and Git checkpoint

135 relative Markdown targets checked, zero missing. git diff --check passes. Final status: main and origin/main at 5d2612fef6d26cc1e1b0547bb5bd3da6abf21187; 58 modified tracked files, 40 untracked files, 0 staged. Full cumulative inventory (includes preserved earlier work):

Final post-TCP/post-deployment rehash at 2026-09-28T11:18:36.9394191Z compared all22 database/sidecar/artifact checkpoint entries: zero differences. The ACTIVE-generation recheck found exactly one unchanged ID. A first comparison incorrectly let PowerShell deserialize ISO timestamps to DateTime before string comparison and flagged every timestamp; rerunning with ConvertFrom-Json -DateKind String eliminated that diagnostic artifact. Hashes and sizes never differed. No protected file was repaired. The final suite also emitted two coverage pre-import notices (mnemo/mnemo_server); the pytest summary's9 warnings and actual90.31% threshold result are reported separately, not suppressed.

```text
 M .dockerignore
 M docs/README.md
 M docs/architecture/current/mnemo_architecture_v2.md
 M docs/architecture/current/mnemo_engineering_roadmap.md
 M docs/governance/README.md
 M docs/governance/contracts/phase8_5_capability_matrix.json
 M docs/governance/contracts/phase8_5_mcp_contracts.json
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
 M mnemo-server/mnemo_server/mcp/contracts.py
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
 M mnemo-server/tests/mcp_contract_sse_child.py
 M mnemo-server/tests/mcp_contract_stdio_child.py
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
?? docs/reports/operations/mnemo-binary-metadata-exposure.md
?? docs/reports/operations/mnemo-complete-resource-delivery-remediation.md
?? docs/reports/operations/mnemo-cursor-finalqa-external-defect-remediation.md
?? docs/reports/operations/mnemo-direct-image-integrity-certification.md
?? docs/reports/operations/mnemo-external-resource-reconstruction-prompt.md
?? docs/reports/operations/mnemo-final-external-chatgpt-acceptance-prompt.md
?? docs/reports/operations/mnemo-final-external-text-certification-prompt.md
?? docs/reports/operations/mnemo-final-four-transport-certification.md
?? docs/reports/operations/mnemo-full-document-text-certification.md
?? docs/reports/operations/mnemo-http-endpoint-acceptance-matrix.md
?? docs/reports/operations/mnemo-http-test-manifest.json
?? docs/reports/operations/mnemo-module-8-8-10-local-implementation.md
?? docs/reports/operations/mnemo-module-8-8-11-local-implementation.md
?? docs/reports/operations/mnemo-multipart-binary-certification.md
?? docs/reports/operations/mnemo-ordered-text-binary-transfer-manifest.json
?? docs/reports/operations/mnemo-ordered-text-certification.md
?? docs/reports/operations/mnemo-ordered-text-delivery-remediation.md
?? docs/reports/operations/mnemo-ordered-text-fixture-manifest.json
?? docs/reports/operations/mnemo-ordered-text-protected-checkpoint.json
?? docs/reports/operations/mnemo-public-mcp-schema-verification.md
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
?? mnemo-server/tests/ordered_text_fixture.py
?? mnemo-server/tests/test_ordered_text_certification.py
?? mnemo-server/tests/test_phase86_exposure_boundary.py
?? mnemo-server/tests/test_stage6_structured_forensic.py
?? scripts/verify_completed_stage_http.py
?? scripts/verify_completed_stage_mcp.py
?? scripts/verify_resource_reconstruction.py
```
