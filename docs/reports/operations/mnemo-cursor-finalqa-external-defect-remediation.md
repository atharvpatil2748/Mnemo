# Cursor and FinalQA external defect remediation — 2026-09-28

## Decision and scope

**SPECIFIC_EXTERNAL_ACTION_REQUIRED.** The two externally observed product
defects are corrected and deployed forward. Authenticated application requests
through the public tunnel must still be executed by the owner's connected
Mnemo client against this new source. Local TCP, stdio and SSE evidence is not
that external evidence. No Stage 7 work or fifteenth tool was implemented.

Initial main/origin/main: `5d2612fef6d26cc1e1b0547bb5bd3da6abf21187`;
34 modified tracked files, 19 untracked files, zero staged. Existing work was
preserved. Initial full 291-file product manifest independently reproduced
`61aee75f5496d83387b533a3c383ea2fba6a6b1ea2e746e85378a8ce2b80f37b`.

Authority: current architecture's Phase 8.8 public contracts and exhaustive
page-budget rule; canonical roadmap's retained V1/V2 routes; ADR-0052/0056
publication/replay boundaries, ADR-0064 governed FinalQA V2 composition, and
ADR-0076/0077/0078 immutable corpus, operational-store and credential authority.
Citation compliance is necessary but not sufficient for generation completion.
Partial-evidence publication is not permission to publish unfinished answers.

## Confirmed defect 1: requested candidate budget was lost by normalization

Production candidate-pool policy raises requested candidate limits to 50.
Requests for 3 and 4 therefore produced identical effective plan budgets.
The signed cursor authenticated that normalized plan, omitting the original
requested limits. The same signature could legitimately decode under both
requests, violating the public immutable-continuation-argument contract.

Failed first: `test_cursor_rejects_candidate_budget_change_below_production_pool`
in `mnemo-server/tests/test_retrieval_v2.py` failed with **DID NOT RAISE
CursorConflictError**. It uses buildCodePrompt, candidate3, evidence1,
characters2000 and production pool50. Effective budgets remain identical.

Correction: `EvidenceSearchRequest.to_plan` hashes the exact client candidate,
evidence, character and serialized-byte limits before normalization into
`RetrievalPlanV2.requested_limits_fingerprint`. The existing signed plan
fingerprint includes this field. Pool size, ranking, cursor HMAC, actor, scope,
snapshot, expiry and representation binding are unchanged. Fresh cursors are
required after deployment; old request fingerprints are not silently accepted.

Post-fix: that regression passes. Eight parameterized cases separately reject
changed query, mode, notebook scope, representation, candidate budget, evidence
budget, characters and requested bytes even when server clamping makes the
effective budgets equal. Existing core tests cover actor replay, scope,
tampering, expiry, snapshot changes, stable multi-page traversal and oversized
complete items; old/new public transport fixtures remain green.

Real certified HTTP: unchanged two-page traversal200/200, changed candidate
budget409 with invalid_input/cursor.conflict, correlation
`73d2cad7-f100-4d48-bb4a-faa1c0b3faac` in the first live probe. That probe
initially stopped because the runner incorrectly expected422; the runner was
corrected to the existing HTTP409 contract, not the product to match the runner.
The subsequent full probe passed. The 80-character continuation still safely
returns422/contract.validation because the next complete item cannot fit;
correlation `00c0d2c5-d59d-47e3-a5af-187602cd006c`. No content slicing/skipping
or cursor-security relaxation was introduced.

## Confirmed defect 2: FinalQA discarded generation termination

Ollama nonstreaming completion already returned done_reason and eval_count.
The FinalQA adapter discarded them. The orchestrator checked only token counts
strictly greater than the budget; a length-terminated answer at the limit could
pass citation resolution. The public completeness field described retrieved
evidence, not generation termination, so unfinished cited text was published.

Failed first: `test_finalqa_preserves_length_termination_even_with_valid_citation`
failed because output_complete was absent. Its deterministic answer includes
`[source:1]` and ends `- **Code`; provider reason is length. Two stream tests
also failed with **DID NOT RAISE** when the terminal frame was missing or length.

Correction: generation results retain allowlisted termination reason and
output_complete. Length termination, interrupted/nonterminal completion,
unknown termination at the token limit, and obvious unclosed Markdown fail
completion. Stop-terminated, well-formed text remains eligible, including a
complete answer exactly at its limit. The checks do not guess or manufacture
missing prose. Ollama stream EOF without a terminal frame and length termination
raise a safe GenerationIncompleteError rather than successful stream completion.

The orchestrator records terminal `rejected_generation` before citation
validation/publication and raises originating code
`final_qa.generation_incomplete` (public retrieval_failure, provider_failure,
safe correlation). No validated/published snapshot is created. Exact replay of
this rejected execution returns the same failure without another inference;
changed replay arguments still conflict. Complete published snapshots retain
answer_complete and termination_reason. The public existing coverage envelope
adds answer_termination. Legacy immutable published snapshots without termination
evidence remain unchanged and report unknown answer completeness, not fabricated
retroactive completion. Citation retry, timeouts and operational-store separation
retain their existing semantics.

Post-fix deterministic matrix: stop-complete, long-within-bound, length,
interrupted, token-limit unknown, unclosed bold/fence, valid citations with
incomplete generation, no publication, one provider invocation across rejected
replay, and conflicting replay. Existing citation rejection/deadline/replay
regressions pass. `test_incomplete_generation_with_valid_citation_is_not_published_or_regenerated`
uses a real disposable SQLite operational store.

Bounded approved real provider: one fresh1024-token request per tested boundary,
followed by exact replay (no fresh inference). HTTP 06:53:27.386647–06:53:41.602153Z:
citation_resolved, one citation, answer_termination={complete:true,reason:stop};
replay through06:53:41.611159Z preserves state. Real stdio 06:54:18.051622–
06:54:23.096168Z and SSE 06:55:45.851318–06:55:48.174701Z each return two
resolved citations, stop/complete; identical replay preserves execution and
termination. No low-budget expensive inference loop was used to debug logic.

## V1 discrepancy: reproduced scope/budget difference, not a fallback defect

Retained V1 notebook-wide dense+sparse fusion applies global top_k before context
assembly/reranking. V2 tested only the codePrompt document. In real stdio,
V1 top_k1 evidence-only selected chunk
`0d393e1b564411b75cca380f7ca0d52714adece85e7c7332bbfcc6fe6bbdbf8e`,
not either codePrompt chunk. Top_k5 returned that chunk and both
`d67e4c0ded6419fd581495f8751669299538cf88d2353feb7ff590e689885297`
and `fb15963f2d567f17fd0972524d418f9362082f1a741686cba3291f5302bf69d4`.
Top1 synthesized answer had zero citation markers despite one supplied context
chunk. Evidence-only top1 had one citation; top5 had five. HTTP also exercised
top1, top5 and a source-filtered top5 request using the actual V2 source ID.
This is not lost context or V1-to-V2 substitution. The public V1 MCP schema has
no document filter; increasing top_k is the compatible client correction.
No ranking, requested-k semantics, synthesis thresholds or V1 route was changed.

## Applied file inventory for this correction pass

Product: core interfaces/errors.py, llms/ollama.py,
models/advanced_retrieval.py, models/final_qa_execution.py, models/multimodal.py,
retrieval/final_qa_provider.py, retrieval/multimodal.py, storage/multimodal.py;
server schemas/retrieval_v2.py, services/final_qa_v2.py, typed_errors.py.
Tests: core test_final_qa_provider_adapter.py, test_multimodal.py,
test_ollama_llm.py; server test_retrieval_v2.py, test_server_system.py;
test_final_qa_v2_transport.py and new opt-in tests/http_tcp_audit_plugin.py.
Both existing acceptance runners
were strengthened to assert expected safe failures and FinalQA termination/replay.
Current architecture, report index, the five requested acceptance reports and
external preparation record were reconciled. Other dirty files are inherited.

## HTTP and transport evidence

The53-operation OpenAPI inventory matches the existing machine-readable
[HTTP manifest](mnemo-http-test-manifest.json). New optional TCP fixture plugin
uses actual ephemeral uvicorn sockets, not ASGI serialization. Backends remain
disposable fixtures/test doubles; it is not evidence of public production writes.

-195 passed/3warnings over13 HTTP contract files;42 operation templates observed.
-28 passed/2warnings over streaming, forensic and14-tool fixtures; adds capability,
  exact chunk, streaming, evidence and V2FinalQA TCP operations.
-21 passed/1warning over system/legacy alias regressions; adds5system aliases and
  retained V1FinalQA malformed-input422. Union of these actual TCP requests covers
  all53 HTTP method/path registrations. This is **not53 positive production paths**:
  the retained V1FinalQA row is negative-input evidence; aliases include valid and
  not-found/invalid cases. Existing core retained-QA tests provide separate evidence.
-Certified immutable production TCP probe:27authenticated requests and missing-auth
  401, exit0, 06:53:25–06:53:41Z; delivery PDF/JPEG1024bytes, exact chunk, two persisted
  OCR/Vision derivations,31 structured descriptors, evidence pagination, FinalQA/replay.
-Real stdio and authenticated loopback SSE each invoke all14 tools successfully,
  plus negative cursor cases, structured query/continuation/empty and QA replay.
  Empty persisted summaries/insights are valid empty, not nonempty fixture claims.
-Direct public MCP old/new fixtures pass with actual persisted derivations;
  cross-principal security evidence is disposable, not live secondary credentials.
-Public external tunnel application: **not executed from this task**. No connected
  Mnemo client is available. Existing signed convergence is historical startup
  evidence, not a fresh certificate for these source changes. Public REST is not
  exposed by an MCP stdio tunnel. WebSocket TestClient tests remain in-process;
  they are not mislabeled as TCP WebSocket certification.

## Deployment and protected checkpoint

Full291-file manifest (sorted POSIX relative path + space + per-file SHA256,
newline joined without trailing newline):
`8141d5090f25a26b742c8417d87dff7a3f1473a1f2b277792ba20f60c0504274`.
Editable .venv imports core/server from this workspace. The existing signed
launcher and scheduled task were reused; no reinstall is needed for editable
source, but all three packages were built independently.

2026-09-28T06:55:01.8796870Z: verified old process tree and stopped exact IDs
89408/92140/86600/82088, then `Start-ScheduledTask -TaskName 'Mnemo Tunnel'`.
No CLI graceful-stop API exists; this was controlled process termination, not
a fabricated graceful endpoint. No rollback or unrelated tunnel stop occurred.
New tunnel96024, cmd94652, venvPython93940, interpreter96476; module locations
verified independently. Temporary SSE86448/interpreter13516/listener8059 was
removed after tests. Healthz/readyz200 after probes. This is health, not an
authenticated external application request. Production binding remains
56b64e879eb64a251a45ab9beabaa5d9dfd8afee760bd5b8f18383a6df510a1d.

| Protected DB | Before = after SHA256 | Bytes | UTC mtime unchanged |
|---|---|---:|---|
|Production|3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c|189804544|2026-09-01T11:09:20.1047581Z|
|WP16|18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d|37195776|2026-08-29T13:37:31.2308106Z|
|Phase8.5eval|bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84|45592576|2026-09-08T06:41:25.6366051Z|
|Phase8.6eval|9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2|52600832|2026-09-08T08:14:51.7220651Z|

Production/WP16 WAL/SHM/journal absent. Evaluation WAL0 SHA
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855;
SHM32768 SHA fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb.
Evaluation8.5 WAL/SHM mtimes08:29:44.8384566Z/11:45:09.0813968Z and8.6
08:30:27.2461167Z/13:52:55.1970116Z on2026-09-08 unchanged; journals absent.

Signed/authority before=after hashes: manifest
e579727c8867c92d4ca7fe05256a35d74942077f86b86a6fad9938ff3b4fc566;
launcher007ee235783cb8f673a2f9c135bc38269ba2a355057c5cd119c0125e471fde22;
activationc17a7f5531cc75795fb63c6f53682d30eb6ed831127db95038d3d1741cd25525;
certificate1a69e95796b98abcc1f4f6484692481058bff776b454a14e3a0b35d86f16312a;
finalevidence0255160992fc1ed2fdc5b5c6bfb55bb442b55018655f511274d698569a06230c;
convergenceb5ccccb9787773ef10f5a6364bbc80ed98324640ea5438da604ebfaf2b7c2b23.
Their respective size/mtime identities remain4069/2026-09-24T07:44:51.3412352Z,
290/15:23:23.8479641Z,1059/07:44:29.1073100Z,2448/15:21:40.4465551Z,
1415/15:21:40.4550622Z,3344/09:46:26.8983082Z (all dates2026-09-24).
Exactly one unchanged ACTIVE generationfc85192e-f672-4cc0-9539-b4b063bb8f41.
QA tests write only the separately governed operational execution/snapshot store.

## Validation and remaining actions

Focused final correction matrix97passed/1cache-warning. Initial full corrected
source run2768passed/18existing local_database exclusions/9warnings/90.31%.
The final rerun adds ordinary HTTP alias regressions; its exact result follows
below. No new xfails or skips. Strict mypy291sources passed; Ruff lint and526-file
format check passed; compileall, uv lock171packages, all3Python package builds,
frontend format/lint/typecheck/1test/100%coverage/build passed. All3Docker images
and all3Compose configurations actually built/validated successfully.

The unrestricted historical protected-manifest lifecycle assertion remains a
separately disclosed local_database test outside MNEMO_CI policy; no protected
manifest was changed and unrestricted suite success is not claimed. Dangling
old dist-info, cache permissions and dependency deprecations remain disclosed.

Final expanded focused command:

```powershell
$env:MNEMO_CI='1'
uv run --no-sync pytest -q --no-cov mnemo-core/tests/unit/test_advanced_retrieval.py mnemo-core/tests/unit/test_final_qa_provider_adapter.py mnemo-core/tests/unit/test_multimodal.py mnemo-core/tests/unit/test_ollama_llm.py mnemo-server/tests/test_retrieval_v2.py mnemo-server/tests/test_final_qa_v2_transport.py mnemo-server/tests/test_mcp_transport_contract_matrix.py mnemo-server/tests/test_stage6_forensic_audit.py mnemo-server/tests/test_stage6_structured_forensic.py mnemo-server/tests/test_phase86_exposure_boundary.py
```

**162passed/1cache-warning/34.67seconds**, zero skips/xfails. The new HTTP
incomplete-generation regression also passed through the opt-in actual TCP
plugin (1passed/12deselected/1cache-warning); both requests500 safe originating
error, correlation UUIDs, no unfinished-answer disclosure, one provider call.

Exact full-suite command uses MNEMO_CI=1:
`uv run --no-sync --extra dev pytest -q --cov=mnemo --cov=mnemo_server --cov-report=term --cov-report=xml`.
Static commands: `uv run --no-sync ruff check .`, `uv run --no-sync ruff format --check .`,
`uv run --no-sync mypy --strict mnemo-core/mnemo mnemo-server/mnemo_server plugins/email-ingestion/email_ingestion`,
`uv run --no-sync python -m compileall -q` over those three source roots,
`uv lock --check`, and `uv build --package` for mnemo-core/mnemo-server/mnemo-email-ingestion.
Frontend uses the actual package scripts format:check/lint/typecheck/test/build.
Docker executed each docker/core.Dockerfile/server.Dockerfile/ui.Dockerfile
with local tags; each build returned0. Compose dev/default/minimal config--quiet
returned0. Documentation scan412Markdown files/392relative links/zero missing
(fenced/inline code excluded; external URLs and anchors not network-tested),
and final git diff--check passed.

Exact remaining action: owner runs the [updated independent14-tool prompt](mnemo-final-external-chatgpt-acceptance-prompt.md)
against the connected public tunnel, especially candidate3→4 and FinalQA
stop/completeness/replay. Authenticated public application evidence must join
fresh direct/stdio/SSE before full four-transport certification. Public HTTP
requires a separately authorized public REST endpoint/client, not a guessed
MCP tunnel URL. No new model, credential, corpus mutation or serving promotion
is needed for the successful existing read-only paths.

No stage/commit/push/PR/merge/release, credential change, protected-store mutation,
signed-artifact rewrite, evaluation federation or product Stage7 implementation.

## Final Git inventory

main/origin/main remain5d2612fef6d26cc1e1b0547bb5bd3da6abf21187;
Final release-validation rerun: **2775passed,18existing skips,9warnings,
90.31%coverage,208.10seconds**, exit0. No expected failures/unexpected passes
were introduced. All18 excluded tests are existing local_database cases under
root conftest.py's MNEMO_CI policy; unrestricted manifest lifecycle remains a
separate historical failure. Coverage also emitted the existing previously-
imported-module diagnostic; the enforced repository threshold passed.

49 modified tracked,21 untracked,zero staged. This is the cumulative preserved
worktree, not a claim all changes originated in this remediation pass.

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
 M mnemo-server/mnemo_server/routers/delivery.py
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
 M mnemo-server/tests/test_mcp_immutable_schema_matrix.py
 M mnemo-server/tests/test_mcp_transport_contract_matrix.py
 M mnemo-server/tests/test_production_storage_composition.py
 M mnemo-server/tests/test_retrieval_v2.py
 M mnemo-server/tests/test_server_system.py
 M mnemo-server/tests/test_structured_schema_boundaries.py
 M mnemo-server/tests/test_structured_v2.py
?? .coverage.MSI.pid88528.XtfEj4Dx.HNQIp837rWOh
?? .coverage.MSI.pid93584.X2557u6x.HYZNd4nhrzoh
?? .coverage.MSI.pid93584.XPE86vLx.HNQIp837rWOh
?? docs/governance/active/phase_8_6_serving_promotion_gate.md
?? docs/reports/operations/mnemo-14-tool-external-acceptance-matrix.md
?? docs/reports/operations/mnemo-all-completed-stages-full-system-remediation.md
?? docs/reports/operations/mnemo-cursor-finalqa-external-defect-remediation.md
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
?? mnemo-server/tests/http_tcp_audit_plugin.py
?? mnemo-server/tests/test_phase86_exposure_boundary.py
?? mnemo-server/tests/test_stage6_structured_forensic.py
?? scripts/verify_completed_stage_http.py
?? scripts/verify_completed_stage_mcp.py
```
