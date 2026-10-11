# Stage 6 final acceptance-gate reconciliation — 2026-09-27

## Decision and evidence boundary

**STAGE_6_ACCEPTANCE_RECONCILIATION_BLOCKED.** The accepted Stage 6 *local
forensic* closure remains intact, but this run cannot certify fresh
four-transport behavior: the current task has no authenticated public-tunnel
MCP client. The external ChatGPT observations supplied by the owner are
valuable independent client evidence, not calls executed by this run. FinalQA
V2 also remains legitimately not ready under its accepted runtime dependency
graph. This report does not change the signed Phase 8.5 certificate, award
Phase 8.8 acceptance, or claim Product Stage 7 implementation.

Authority: [current architecture](../../architecture/current/mnemo_architecture_v2.md)
§§21.3–21.10, especially §21.6's tool/availability distinction;
[canonical roadmap](../../architecture/current/mnemo_engineering_roadmap.md)
Modules 8.8.4, 8.8.6, 8.8.9–8.8.11 and its Phase 8.8 acceptance matrix;
[ADR-0073](../../adr/active/ADR-0073-mcp-native-retrieval-and-delivery-contracts.md)
for cursor/actor and typed terminal limitations;
[ADR-0076](../../adr/active/ADR-0076-project-owner-engineering-certification-standard.md),
[ADR-0077](../../adr/active/ADR-0077-governed-mutable-workspace-boundary.md),
and [ADR-0078](../../adr/active/ADR-0078-generation-aware-production-credential-lifecycle.md).
The [local forensic closure](mnemo-stage-7-forensic-audit-remediation-and-stage-6-closure.md)
is not an external certificate. The [final cursor audit](mnemo-stage-6-final-contract-and-acceptance-gate-audit.md)
records the actor-binding fix and final exact-tree CI-safe run.

At entry, `main` and `origin/main` were
`5d2612fef6d26cc1e1b0547bb5bd3da6abf21187`, with 24 modified tracked
files, ten intended untracked files and nothing staged. The tunnel listener
was 127.0.0.1:8080, PID 79448; its signed-launcher command child was 87168,
venv Python 87840 and interpreter 89340. The checkout imports through the
authorized editable venv. The sorted nine-product-file SHA-256 manifest
remained `6dafd086decdef5d046aedc85695400c342fbade99533951c47eb81e018127e1`.
That is an **operator-side content attestation**, not a public MCP revision.

## Requirement-to-acceptance matrix

“Required” below is qualified by scope: 8.8.4's valid behavior on an
authorized fixture, current certified-production readiness, Module 8.8.9
transport certification, and the complete Phase 8.8 gate are distinct.
The current architecture controls implementation status; ADR-0073's earlier
staged-rollout wording (“add only when ready”) is historical and does not
override §21.6's explicit 14-tool registration with truthful unavailability.

| Capability | Authority and applicable gate | Expected / actual certified production | Evidence after actor-bound change; external MCP reach | Disposition |
|---|---|---|---|---|
| Document delivery | Architecture §21.6; 8.8.4 authorized fixture; full 8.8 matrix | Tool `get_document` registered; broad family `service_not_registered`; missing persisted blocks/originals must be unavailable | Synthetic positive and safe-unavailable tests remain valid for service contract; latest external scoped capability reported unregistered, no production positive | No fabricated production representation or registration. Full-production positive remains unavailable; public capability can verify status. |
| Exact retrieval | §21.4/§21.6; 8.8.4 exact chunk | `get_document_chunk` can read an authorized persisted chunk despite broad exact family `service_not_registered` | Older/newer local exact-chunk tests; latest external family unregistered; public exact-chunk test requires discovered authorized ID | Per-operation success and broad family lifecycle are separate. No registration-only inference. |
| Asset delivery | §21.6; 8.8.4 fixture; 8.8.12 discovery later | `get_asset` registered; broad original-asset family `service_not_registered` | Persisted fixture success/negative evidence; no certified-production asset claim; external status observable | Preserve unavailability, no asset fabrication. |
| FinalQA V2 | §21.6; `mnemo-core/mnemo/phase85/runtime.py` `final_qa_v2` dependency tuple; 8.8.9c and Phase 8.8 FinalQA gate | Service registered/configured/buildable, not ready because `multimodal_retrieval` lacks active generation | `FinalQAV2ApplicationService` has a text evidence path, but accepted runtime readiness explicitly depends on multimodal retrieval, authorization and provenance; latest external status confirms not ready | **Mandatory full Phase 8.8 external FinalQA success remains blocked.** Narrowing dependency for text-only use would change accepted lifecycle policy; no bypass or uncertified activation. External MCP can inspect status, not prove a successful unavailable path. |
| Multimodal retrieval | §21.8, 8.8.6 lifecycle, 8.8.12 later | Active generation unavailable | Latest external scoped status; local fixture behavior remains separate | Explicitly unavailable; no generation created. |
| Positive structured retrieval | §21.6, 8.8.11a–c | Notebook READY; tested codePrompt.js version unavailable, but another authorized exact version has READY projection and covering chunk | Read-only immutable SQLite census: 105 projection rows, 104 READY+covering in authorized notebook. Fresh certified stdio describe/query/zero-match below. External client can test the discovered version if its principal is authorized. | Positive path is **available on a different existing production version**, not universally available. No projection created. |
| OCR generation | §21.8; 8.8.6/8.8.12 distinction | Profile not configured; persisted `ocr_text` search may be searched/empty | External scoped generation and search observations; local regressions | Optional generation state; no OCR model activation. |
| Exhaustive retrieval and signed pagination | ADR-0058/0073, §21.6; 8.8.4 | Exposed; actor/notebook/query/representation/budget/snapshot-bound cursor | Owner-supplied external 2000 traversal and expected 80 terminal limitation; current focused tests cover actor replay, tamper, expiry, old/new schemas; prior certified stdio exact live traversal | Correct per-page complete-item budget semantics. External single-principal session cannot certify cross-actor denial. |
| Production/evaluation isolation | §21.10, ADR-0076/0077, 8.8.10 | Certified store only; evaluation registry cannot become production federation | Independent local forensic fixtures, pre-open path tripwires, protected hashes; public identity match cannot prove absence of hidden evaluation I/O | Locally accepted, external internal-invariant proof not possible by MCP alone. |
| Cross-principal authorization/cursor isolation | §21.5, ADR-0073, 8.8.3 and actor fix | Trusted principal; per-page reauthorization; cursor actor bound | Fresh disposable two-actor regression, before-fix replay reproduced in prior audit; current focused result below. No second owner-authorized live credential | Local security proof only; never create live credential merely for certification. |
| Four-transport parity | Roadmap 8.8.9a–c; §21.3 | Same effective composition and semantic identities across HTTP, stdio, SSE, existing tunnel | Fresh current-tree direct/real-stdio/loopback-SSE/HTTP fixture matrix below; earlier signed startup-convergence artifact is configuration-bound; **no current-run authenticated external-tunnel request** | **Certification open.** Tunnel health and local probes are not external behavior. |
| Loaded-source and protected state | §21.3, ADR-0076/0078, 8.8.1 | Certified config/store/model/ACTIVE identity; immutable corpus | Local process/checkout digest and before/after hashes; public MCP reports configured identities but not source revision or independent file hash | Operator attestation valid locally; external MCP cannot independently establish loaded source or protected-file immutability. |

There is no code-level evidence that the broad document/exact/asset family
registrations were accidentally dropped by this task. `get_document`,
`get_document_chunk`, `get_asset` and `run_final_qa_v2` remain among the 14
registered tool routes; `mnemo-core/mnemo/phase85/runtime.py` and
`mnemo-server/mnemo_server/services/capabilities_v2.py` deliberately separate
those names from service lifecycle/readiness. The `KnowledgeEngine` registers
FinalQA V2 when composed; the current read-only operational store is separate.
No product change or deployment restart was justified in this reconciliation.

A fresh certified local stdio `get_capabilities` for the authorized notebook
returned scope-qualified snapshot
`08040f274d7200fa604a1912ae40287c3568a2aa51a1f64b6730fcaa371758a3`.
Document delivery, exact retrieval and asset delivery each reported
`declared`, `service_registered=false`, `available_for_scope=false`, reason
`service_not_registered`. Exhaustive retrieval and structured retrieval
reported `exposed`, registered/configured/ready and scope-available. FinalQA
V2 reported `buildable`, registered/configured but not ready or
scope-available, reason `dependency_unavailable:multimodal_retrieval`.
Multimodal retrieval reported `buildable` but not ready, reason
`active_generation_unavailable`. OCR generation reported `declared`,
unconfigured, reason `profile_not_configured`. These are actual local
certified-stdio capability observations, separate from the owner's external
client observations and from positive behavior tests.

## Fresh positive structured production probe

Using `sqlite3` URI `mode=ro&immutable=1`, discovery found a READY projection
with a canonical covering chunk in notebook
`df9c20cf-85fe-529c-902e-2e9e68193fbe`: source
`42a948fa-023f-48af-b660-85a0d70b349e`, document
`092b9610-05e6-54f4-bb3f-ea8b4544a25f`, exact version
`2190addb-b826-586f-b2be-65962e520068`. The public certified **local
stdio** `query_structured` describe returned 31 datasets, complete, request
`2fb5e663-df3e-4fda-a2f8-ccd421806e14`. A page-size-one query of dataset
`79b102a3-faa0-517a-a4fe-9bda3dc4fb51` returned one row and a signed
cursor (request `c934aeba-0b1c-4abb-80e8-a88d36a18485`); unchanged
continuation returned the next row (request
`c564d034-ebee-4f54-a81f-acaf07e6845b`). A type-correct `NAME eq`
sentinel returned **valid empty**, no cursor (request
`2352080d-405c-462c-8fc6-c7c223cd65f2`). An earlier numeric-column
string predicate correctly failed `invalid_input/contract.validation`;
that diagnostic was not counted as a zero-match success. No returned row
contents or private paths are reproduced here.

This positive does not contradict the external safe unavailability for a
different exact version. A new external verifier can use these identities
only after live authorization/inventory confirms them.

## Four-transport and security result

The fresh `MNEMO_CI=1` focused command selected
`test_mcp_transport_contract_matrix.py`,
`test_mcp_immutable_schema_matrix.py` and
`mnemo-core/tests/unit/test_advanced_retrieval.py`: **96 test cases
passed** on the current tree. Its first invocation exited 1 solely because
the repository's 90% *whole-repository* coverage threshold was applied to
the selected subset (38.40% partial coverage); the same focused cases were
rerun with `--no-cov`: **96 passed, exit 0 in 72.82 seconds**. The most recent
complete exact-source CI-safe run (before this documentation-only pass) was
**2,729 passed, 18 established skips, eight warnings, 90.31% coverage**.
No product source changed afterward. This run does **not** re-label that
earlier full-suite execution as a fresh four-transport certificate.

| Boundary | Fresh current-run evidence | What it does not establish |
|---|---|---|
| Direct public MCP | Disposable old/new schema matrix and signed cursor/security cases | Live public-tunnel behavior |
| Real local stdio | Same-fixture subprocess matrix plus separate certified production structured probe | Remote authenticated client identity |
| Loopback SSE | Same-fixture authenticated loopback matrix; direct comparison uses the same derived actor | Existing external tunnel |
| HTTP adapter | Same-fixture applicable V2 endpoint tests | HTTP deployment through the stdio tunnel |
| Existing tunnel | Running process and loopback health/control-plane poll can be inspected | No genuine authenticated public MCP call from this task; 8.8.9a–c not certified |

The signed startup convergence artifact remains applicable to the exact
certified configuration and generation identity it signed. It does not
certify the new actor-bound cursor behavior. The task has no connected
Mnemo external MCP tool; the computer-use path cannot automate the
ChatGPT desktop client. No credential was printed, minted or rotated.

## Protected-state checkpoint

| Protected object | Entry identity | Exit disposition |
|---|---|---|
| Production DB | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`; 189804544 bytes; 2026-09-01T11:09:20.1047581Z; no sidecars | Hash, bytes, UTC mtime and absence of WAL/SHM/journal matched |
| WP16 DB | `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d`; 37195776 bytes; 2026-08-29T13:37:31.2308106Z; no sidecars | Hash, bytes, UTC mtime and absence of WAL/SHM/journal matched |
| Evaluation 8.5 | `bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84`; 45592576 bytes; 2026-09-08T06:41:25.6366051Z | DB identity matched; existing zero-byte WAL SHA `e3b0c442…` and 32768-byte SHM SHA `fd4c9fda…` retained their sizes, hashes and UTC mtimes |
| Evaluation 8.6 | `9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2`; 52600832 bytes; 2026-09-08T08:14:51.7220651Z | DB identity and pre-existing WAL/SHM hashes, sizes, mtimes matched |

Manifest `e579727c…`, launcher `007ee235…`, signed activation `c17a7f55…`,
certificate `1a69e957…`, final evidence `02551609…`, and signed convergence
`b5ccccb9…` matched accepted full hashes at entry. Registry metadata had
exactly one ACTIVE generation
`fc85192e-f672-4cc0-9539-b4b063bb8f41`. No secret values were read out.
All six artifact hashes and the sole ACTIVE generation matched again after
the test run. The tunnel still reported HTTP 200 health/readiness and a
successful control-plane poll; no forward restart was required because no
product source or runtime configuration was changed in this pass.

## Remaining gate and handoff

Module 8.8.9 still requires a fresh authenticated external-tunnel leg of
the same semantic matrix and correlated long FinalQA diagnosis. Full Phase
8.8 acceptance additionally requires authorized image discovery and
certified FinalQA success; an absent multimodal generation cannot be
declared ready by changing a capability flag. Local Stage 6 forensic
closure remains a different, already accepted scope. The updated
[external ChatGPT prompt](mnemo-stage-6-stage-7-external-chatgpt-verification-prompt.md)
requests bounded fresh public observations and keeps these internal gates
separate. Product Stage 7's Plugin SDK, official EPUB/browser-history
plugins, published OpenAPI, MCP specification-suite certification and Open
WebUI integration are not implemented by this reconciliation.

Final Git status: `main`/`origin/main` remain at
`5d2612fef6d26cc1e1b0547bb5bd3da6abf21187`, **24 modified tracked,
11 intended untracked, zero staged**. This pass added this report, updated
the reports index, preparation record, external prompt, and corrected one
stale roadmap deployment sentence; it made **no product-code edit**.
Changed-document relative links (eight documents) and `git diff --check`
passed. There was no commit, push, PR, deployment, tunnel restart,
credential change, protected-store write or evaluation promotion in this
reconciliation run. The previous owner-authorized forward restart and its
operator attestation are historical evidence, not newly executed here.
