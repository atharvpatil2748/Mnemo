# Stage 6 external-verification preparation — forward-only continuation

## Latest superseding deployment — 2026-09-28 external-defect remediation

Final validation2775passed/18existing skips/9warnings/90.31%;162focused
passed, no new skips/xfails. All required local static/build gates passed.

Use the [current applied-fixes report](mnemo-cursor-finalqa-external-defect-remediation.md)
and [complete independent prompt](mnemo-final-external-chatgpt-acceptance-prompt.md).
Current source manifest8141d5090f25a26b742c8417d87dff7a3f1473a1f2b277792ba20f60c0504274;
forward restart06:55:01.8796870Z, tunnel96024, venvPython93940/interpreter96476.
Requested cursor limits are bound before normalization; incomplete generations
are terminal rejected, not published. Complete FinalQA snapshots/replay now
preserve termination metadata. All14 pass real local stdio/SSE and existing
positive production TCP reads/QA; protected identities are unchanged.
Authenticated external MCP application retest still requires the separate
owner-connected client. Neither this report nor health200 self-awards external
acceptance or full four-transport certification. Earlier sections remain history.

Current date: 2026-09-27. Current verdict:
**EXTERNAL_VERIFICATION_PREPARATION_BLOCKED**. The owner waived the
old-runtime rollback prerequisite, and the new working-tree code was started
through the existing tunnel. The remaining gate is an **authenticated MCP
request through the actual external ChatGPT/tunnel client**. Local tunnel
health and a separate certified stdio client are not that request. This report
keeps the earlier safety-stop checkpoint below as historical evidence.

## Forward-only deployment and code identity

Preflight again matched the four database SHA-256 hashes, sizes, UTC mtimes,
production/WP16 sidecar absence, pre-existing evaluation WAL/SHM hashes,
signed authority artifacts, and exactly one ACTIVE generation recorded below.
No protected identity mismatch was observed. `main` and `origin/main` remained
at `5d2612fef6d26cc1e1b0547bb5bd3da6abf21187`, with the prior dirty
Stage 6 work preserved; no file was staged.

The actual Mnemo route is the existing `tunnel-client.exe run --config
.../mnemo.yaml` process listening on 127.0.0.1:8080. Its `main` channel is a
direct stdio MCP route to the signed `scripts/start_certified_mcp_tunnel.bat`
launcher, which invokes this checkout's `.venv/Scripts/python.exe -m
mnemo_server.mcp.cli certified-tunnel-stdio`. Both `mnemo_server` and `mnemo`
resolve through editable installations to this checkout, not another image or
site-packages copy. The batch launcher, manifest, model-cache setting,
authentication and tunnel endpoint were not edited. The other tunnel on
127.0.0.1:8081 remained untouched.

The new product-source identity is Git HEAD **plus** the seven modified
product Python files. Their deterministic sorted `relative-path SHA-256`
manifest digest is
`386e4ba3d61a0d933b7453c41a9128b86205801a77a29d627ddfd491350197eb`.
The forward fix's `mnemo-core/mnemo/storage/composite.py` SHA-256 is
`a71ab65784bb7c31637c4badebea2ed110c90c163ce792dbf9c85929167a255a`.
This local file/process evidence is stronger than the published Git SHA alone,
but public MCP currently exposes no verified code-content digest to an
external client; that client must say it cannot independently prove the
source revision from tool results alone.

| Event | UTC observation and result |
|---|---|
| First forward restart | Existing Mnemo process tree (tunnel PID 38596, child Python PID 49488) stopped; original scheduled task launched new tunnel at **2026-09-27T13:14:07.9339133Z**. Local readiness became healthy and control-plane polling followed. |
| Initial live-local diagnostic | A separate real certified stdio subprocess admitted binding `56b64e879eb64a251a45ab9beabaa5d9dfd8afee760bd5b8f18383a6df510a1d`; `tools/list` returned the exact 14-tool inventory; unscoped capabilities and `list_notebooks {limit:1}` succeeded. |
| Defect reproduction | On an authorized notebook, scoped structured capability returned `available_for_scope: null` although production used a composite store with a persisted SQLite readiness probe. An unrelated test call supplied HTTP-only search arguments and correctly returned `invalid_input` (correlation `80985cb1-d174-4517-8212-a3159312e6d2`); it was corrected in the client probe, not product code. |
| Failing-first regression | Both boolean variants of `test_scoped_structured_readiness_delegates_to_sqlite` failed with `AttributeError`: `CompositeStorage` lacked `structured_projection_ready_for_notebook`. |
| Small forward fix | Added read-only delegation to the canonical SQLite readiness probe in `mnemo-core/mnemo/storage/composite.py`; added false/true delegation assertions in `mnemo-core/tests/unit/test_composite_storage.py`. No new projection, activation or store fallback was introduced. |
| Corrected restart | Tunnel PID 70288 and its child were stopped at **2026-09-27T13:24:38.0502704Z**. Configuration doctor passed with port free. The unchanged scheduled task launched tunnel PID **75376** at **2026-09-27T13:24:58.1001831Z**; its new interpreter PID **52796** started at **13:24:59.7971360Z**. Tunnel `/healthz` and `/readyz` returned HTTP 200; control-plane polling became healthy. `/api/status` reported `main` channel `stdio`, direct route, probe `ok`, and the signed launcher command. |
| Post-fix local certified stdio | Authorized notebook list and scoped capabilities succeeded; `structured_retrieval.lifecycle.available_for_scope` changed from `null` to **`true`** for the probed notebook. Sparse retained search returned one authorized canonical chunk. `query_structured describe` for that particular returned version truthfully produced typed `capability_unavailable` / `contract.dependency_unavailable` (correlation `af33ab53-d84b-494a-97fd-80d251e9b767`); notebook-level readiness does not promise every version has a projection. No production projection was created. |

The exact process operations were native PowerShell `Stop-Process -Id
38596` and, after checking/removing any remaining identified child PIDs,
`Start-ScheduledTask -InputObject $t` where `$t` was the verified existing
`Mnemo Tunnel` task. The correction cycle used `Stop-Process -Id 70288`
and the same verified scheduled-task start. A `tunnel-client doctor --config
.../mnemo.yaml` validation exited zero with the listener free before each
start. The first stop-command script exited nonzero only because one child
PID had already exited by the time it was checked; the subsequent process
and port inventory confirmed the complete Mnemo tree was stopped. No
unrelated process was terminated. Initial post-start control-plane polling
was briefly pending and then became healthy without a configuration change.

The registered names observed from the real local certified MCP client were:
`list_notebooks`, `get_notebook_summary`, `get_timeline`,
`get_source_insights`, `search_all_notebooks`, `query_notebook`,
`search_evidence`, `get_capabilities`, `query_structured`, `get_document`,
`get_document_chunk`, `get_asset`, `get_image_analysis`, and
`run_final_qa_v2`. Local synthetic direct MCP/stdio/SSE/HTTP route tests
are separately covered by the focused and full suites; they are not live
external-tunnel calls. No production HTTP API or SSE listener was invented:
the current live tunnel bridges stdio. No bounded FinalQA call was issued
against the live model, so its live completion/deadline behavior remains
unverified here.

The unchanged local configuration binds the existing tunnel identity
`tunnel_6a85b493e6a48191b925e1f4d850c48c`; its public MCP URL was not
exposed by the local health/status surface and was not guessed. The local
status reported direct route mode and successful channel probing. No secret
runtime key or credential value is included here.

The browser/client automation runtimes each failed to initialize with
`failed to write kernel assets: The system cannot find the path specified`;
the browser inventory retry after reset failed the same way. This Codex task
has no connected Mnemo MCP tool. The tunnel's successful control-plane poll
proves outbound connectivity, and the local `/api/status` channel probe proves
local stdio reachability, but neither constitutes an authenticated tool call
from ChatGPT through the public route. No external request/correlation ID or
public endpoint response was obtained. This is the exact remaining blocker
to `PREPARED_FOR_EXTERNAL_CHATGPT_VERIFICATION` under the owner's criteria.

## Post-fix verification and release boundaries

| Check | Observed result |
|---|---|
| Failing-first regression | 2 failures before delegation; both passed after |
| Affected focused tests | 43 passed (composite, capability, independent structured forensic and exposure tests) |
| Expanded Stage 6/transport matrix | 120 passed (composite, older/newer public MCP, all-tool real local transport, F-1/F-2, structured and production composition) |
| Full `MNEMO_CI=1` repository suite | **2722 passed, 18 skipped, eight warnings, 90.30% coverage**, 0 xfail/XPASS, 248.76 seconds |
| Python static/packaging | Ruff lint and format passed (523 files); strict mypy passed (291 source files); compileall, `uv lock --check` (171 packages) and all three Python source/wheel builds passed |
| Frontend | format, lint, typecheck, one Vitest test with 100% reported frontend coverage, production build passed |
| Compose | Three configuration checks passed |
| Docker context security | Added `/scratch` and `/config/production` to `.dockerignore` before image builds; observed build contexts were 70.37 kB for Python and 738 B for UI, not the protected corpus. All three local core/server/UI image builds passed; no image was pushed or deployed. |
| Historical unrestricted local-database test | The established protected-manifest lifecycle assertion remains outside the CI-safe policy and is **not** claimed green; the 18 `local_database` exclusions remain disclosed. |

The changed-document relative-link check found **zero broken links** among
the reports index and the two handoff files; `git diff --check` passed.

## Closing protected and process checkpoint

At 2026-09-27T13:36:31Z the existing Mnemo tunnel PID 75376 remained
healthy: local health/ready HTTP 200, successful control-plane poll, `main`
channel stdio probe `ok`, and corrected Python interpreter PID 52796 still
running. The tunnel's public-side authenticated tool call was **not**
observed. The local status route reported a direct stdio MCP channel, not a
separate production HTTP or SSE listener.

After the final restart, test suite and Docker builds, all four protected
database SHA-256 hashes, byte sizes and UTC mtimes still matched the preflight
table below. Production and WP16 remained WAL/SHM/journal-free. Both
evaluation stores retained their original zero-byte WAL and 32768-byte SHM
files with unchanged hashes; no journal appeared. The six recorded manifest,
launcher and signed evidence hashes all still matched. The sole ACTIVE
credential generation remained
`fc85192e-f672-4cc0-9539-b4b063bb8f41`.

Final Git: `main...origin/main` at
`5d2612fef6d26cc1e1b0547bb5bd3da6abf21187`, **19 modified tracked,
eight untracked, zero staged**. This run changed
`mnemo-core/mnemo/storage/composite.py`,
`mnemo-core/tests/unit/test_composite_storage.py`, `.dockerignore`, the
reports index, and these two handoff documents; all other dirty work was
preserved. No commit, push, PR, new tunnel endpoint, credential rotation,
signed-artifact rewrite, production projection activation, Phase 8.6
promotion, or protected-store mutation occurred. The external ChatGPT
verification prompt is complete and copy-pasteable, but its independent
tool-call evidence is still pending. The owner may now run that separate
connected ChatGPT session; this engineer cannot award its verdict.

The forward correction did not alter public DTOs, protected identities,
certified store/model authority, Phase 8.6 serving roles or signed artifacts.
Product Stage 7 remains the future Ecosystem and Extensibility deliverables;
its Plugin SDK docs, official EPUB/browser-history plugins, published OpenAPI
spec, MCP specification-suite certification and Open WebUI integration are
not shown implemented or externally verified by this Stage 6 restart.

## Previous safety checkpoint (historical; superseded by owner authorization)

Date: 2026-09-27. Verdict: **EXTERNAL_VERIFICATION_PREPARATION_BLOCKED**.
This is a preparation checkpoint, not external ChatGPT acceptance, a
deployment certificate, or a change to the locally closed Stage 6 verdict.

## Authority and starting state

Reviewed the current documentation index, architecture and canonical roadmap,
ADR-0076/0077/0078, the inactive Phase 8.6 serving-promotion gate, Stage 6
forensic remediation and GitHub closure records, the 8.8.10 and 8.8.11 local
implementation reports, and the combined independent forensic audit and
applied-fixes report. Product Stage 7 is Ecosystem and Extensibility, not a
synonym for 8.8.10/8.8.11. Its Plugin SDK documentation, official EPUB and
browser-history plugins, published OpenAPI specification, MCP specification
suite certification and Open WebUI integration have not been established by
this preparation run. The locally closed Stage 6 work remains uncommitted and
unpublished; the older five-module GitHub closure does not publish it.

At the opening checkpoint, `main` and `origin/main` both resolved to
`5d2612fef6d26cc1e1b0547bb5bd3da6abf21187`. There were 17 modified
tracked files, six intended untracked files and no staged changes. The
untracked files comprised the inactive promotion gate, the 8.8.10/8.8.11
implementation reports, the combined forensic report, and two regression
files. No product file was changed in this preparation run. The exact-tree
source identity is **not** the Git SHA alone: it includes these uncommitted
changes, and no deployed process content digest is available.

## Protected preflight and closing checkpoint

All checks were read-only. Opening and closing observations matched the
authoritative hashes, sizes, UTC mtimes and existing sidecar state:

| Database | SHA-256 | Bytes | UTC mtime | Sidecars |
|---|---|---:|---|---|
| Certified production | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | 189804544 | 2026-09-01T11:09:20.1047581Z | none |
| WP16 | `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d` | 37195776 | 2026-08-29T13:37:31.2308106Z | none |
| Phase 8.5 evaluation | `bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84` | 45592576 | 2026-09-08T06:41:25.6366051Z | pre-existing WAL 0 bytes; SHM 32768 bytes |
| Phase 8.6 evaluation | `9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2` | 52600832 | 2026-09-08T08:14:51.7220651Z | pre-existing WAL 0 bytes; SHM 32768 bytes |

Both evaluation WAL hashes remained SHA-256
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`;
both SHM hashes remained
`fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb`.
The production manifest, certified batch launcher, signed activation,
certificate, final evidence and four-transport convergence artifact matched
their accepted SHA-256 baselines (`e579727c…`, `007ee235…`, `c17a7f55…`,
`1a69e957…`, `02551609…`, `b5ccccb9…`, respectively). The credential
registry contained exactly one `ACTIVE` generation, matching
`fc85192e-f672-4cc0-9539-b4b063bb8f41`. No credential value was read out
or reported. These observations do not prove what the already-running Python
process has in memory.

## Actual runtime topology and stop decision

The existing Mnemo `tunnel-client.exe` PID 38596 was started on September 25
as `run --config` with the existing roaming-profile YAML. It listens on
127.0.0.1:8080 and has a long-lived `cmd.exe`/Python stdio MCP child, whose
Python launch is `-m mnemo_server.mcp.cli certified-tunnel-stdio` through the
signed `scripts/start_certified_mcp_tunnel.bat`. The editable virtual
environment resolves `mnemo_server` and `mnemo` modules to this repository's
working-tree source directories. Therefore a fresh child would import the
uncommitted source, but that is **not** evidence that the child started on
September 25 currently runs it. The certified launcher and production
manifest were not changed. The existing `Mnemo Tunnel` Windows scheduled
task invokes a VBS wrapper that starts a detached `tunnel-client run`; the
task was `Ready`, not supervising the live process. An unrelated tunnel on
127.0.0.1:8081 was left untouched.

At approximately 2026-09-27T12:59:59Z, `tunnel-client health --port 8080
--pid 38596 --require-control-plane-poll --json` reported process running,
`/healthz` and `/readyz` HTTP 200, and a successful control-plane poll. This
is local tunnel health, **not** an authenticated external MCP request and not
proof of the newly accepted server code. No safe deployed-code revision or
content identity was exposed by that health result. Active in-flight request
state was also not established.

The authorized restart has an explicit prerequisite: a validated rollback to
the pre-restart serving state. None was found. The scheduled task only starts
a detached process; the CLI exposes no verified reload/stop/rollback action.
The pre-restart Python child already has code loaded in memory, while the
on-disk editable checkout has newer uncommitted code. Restarting the same
launcher would load the new code, and restarting it again would **not**
restore the old in-memory state. Resetting this dirty checkout would discard
accepted work and is prohibited. A separate rollback checkout/runtime or
image has not been prepared and validated against the signed launcher and
certified configuration. Consequently the stop condition was met **before**
stopping either process. No restart, deployment, live external probe or
automatic product correction was attempted. No rollback was executed.

## Evidence and unverified gates

| Gate | Observation | Status |
|---|---|---|
| Local 8.8.10/8.8.11 exposure, forensic and production-composition regressions | `MNEMO_CI=1`, pytest with repository addopts disabled for three focused files: **20 passed in 8.34 s** | Passed on the working tree |
| Prior exact-tree full CI-safe suite | Independent report records **2720 passed, 18 skipped, eight warnings, 90.31% coverage** | Historical, not rerun here |
| Unrestricted historical manifest lifecycle assertion | Prior report records a failure; signed manifest was not modified | Still disclosed, not a green unrestricted suite |
| Existing tunnel local health | PID 38596 live, readiness HTTP 200, control-plane poll successful | Existing service healthy; new code identity unproved |
| New code loaded in production child | Child predates this working tree; no restart | **Not verified** |
| Authenticated external MCP, 14 tools, scoped capabilities, structured availability, F-1/F-2, FinalQA | No safe new-code deployment or authenticated external probe | **Not executed** |
| HTTP/stdio/SSE/tunnel parity after restart | No restart | **Not executed** |
| Four protected databases and signed artifacts | Matching read-only before/after checkpoint | Passed |

No UTC request/correlation IDs are available because no authenticated MCP
request was issued in this run. The public endpoint name was deliberately not
asserted from the local health port. The separate independent ChatGPT session
has **not** run and no external acceptance verdict is claimed.

## Required recovery and owner handoff

Before another engineer restarts Mnemo, establish a recoverable, tested
snapshot of the currently serving code/environment or an approved known-good
release, preserving the signed launcher, certified manifest, store/model and
active generation. Document a supervisor-controlled graceful stop/start,
in-flight request drain, exact process/port checks, and the reverse action.
Validate the candidate runtime against certified startup identity without
altering protected artifacts, then perform the authorized restart and prove
the child and external MCP endpoint load that exact candidate. Recheck all
protected identities afterward. Only then perform the bounded live matrix
and give the owner the independent ChatGPT prompt in
[the companion handoff](mnemo-stage-6-stage-7-external-chatgpt-verification-prompt.md).
The prompt itself requires this deployed-code precondition and cannot turn
the current healthy **old** tunnel into new-code verification.

Product Stage 7 remains separate and not forensically accepted. This report
does not change local Stage 6 forensic closure, and it does not complete
Phase 8.8 four-transport certification. No Git staging, commit, push, PR,
deployment, production or tunnel restart, credential change, evaluation
promotion, signed-artifact change or protected-store mutation occurred.

## 2026-09-27 external-audit remediation and second handoff

This dated section supersedes the older rollback-blocked checkpoint above;
it does not erase its historical observations. The owner authorized a
forward-only restart. The first independent external client connected and
matched certified production DB SHA-256 `3157ff…`, governed identity
`0c6c73…`, runtime binding `56b64e…`, the 14 visible tool names and the
historically named 44-source certified notebook. It withheld Stage 6 external
acceptance after an exhaustive cursor continuation failed and reported OCR
and capability ambiguities. The full [remediation record](mnemo-stage-6-external-audit-remediation.md)
separates the actual defect from budget and lifecycle semantics.

The only new product correction in this pass is same-startup FinalQA V2
capability registration in `mnemo-core/mnemo/engine.py`. The regression failed
first with `service_not_registered` despite a composed service and passed
after the fix. It does not bypass multimodal dependency or certification
gates. Exact certified-stdio replay of the external exhaustive request
returned page 1 then `ContractValidationError` on page 2 at the unchanged
80-character content budget; a new 2,000-character traversal completed in
two pages, with content lengths 37 and 1,148 respectively. No cursor-signing
logic was changed. OCR generation-profile unavailability and successful empty
search of an accessible persisted representation are separate facts.

At 2026-09-27T15:43:06Z the identified old tunnel PID 75376 was stopped and
the existing `Mnemo Tunnel` scheduled task started the same signed launcher.
The old orphaned Python descendants were identified by PID/command ancestry
and stopped; no unrelated tunnel was touched. The new tunnel PID is 65196,
its command child 69648, virtual-environment Python 86348 and interpreter
child 55896 (start 15:43:08Z). The listener remains 127.0.0.1:8080.
`/healthz` and `/readyz` returned HTTP 200, and `/api/status` showed the
`main` stdio channel enabled with probe `ok`. The same externally governed
tunnel identity and public endpoint configuration were retained. This local
control-plane result is **not** an authenticated public-side MCP call.

The venv imports `mnemo`/`mnemo_server` from this checkout. The edited
`engine.py` SHA-256 is
`44f537e353909655cbf5fc9d9dc56653a2cf6ae269bf8a42333dc4c046101b19`;
its file mtime predates the new interpreter's start. The deterministic
SHA-256 of newline-joined, sorted `relative-path SHA-256` entries for the
eight modified product Python files is
`6ecb1158ddcef2e0d2380676840bfd2df42e1270ab0f4b86fff002441b70c55d`.
This is operator-side content/process attestation, **not** a digest exposed
by public MCP. The public client cannot independently prove the source
revision from capabilities alone.

Post-restart separate certified stdio returned 14 registered tools, binding
`56b64e…`, structured capability `exposed` and notebook-available, and
FinalQA V2 `buildable` rather than the previous `service_not_registered`;
it remains not scope-callable. Broader document/exact/asset families remain
truthfully unregistered under architecture §21.8. Exact bounded evidence
continuation completed in two pages (request IDs
`ff16f374-616a-4d5b-8797-3fbc9180120d` and
`d9d01509-ac99-407d-9371-ac752ca62667`). These are **local stdio**
observations, not externally authenticated tunnel tool results.

The corrected-tree CI-safe suite passed **2,727**, skipped **18**, warned
**9** times and reached **90.31%** repository-wide coverage. Ruff lint and
format, strict mypy, compileall, lock check, three Python package builds,
frontend format/lint/typecheck/test/build, three Compose checks, all three
Docker builds, changed-document relative-link validation and `git diff
--check` passed. The historical unrestricted protected-manifest assertion
remains separately unresolved; no signed manifest was changed. All four
protected DB SHA-256/size/mtime/sidecar states and six signed/configuration
hashes matched before and after. The registry still has exactly one ACTIVE
generation `fc85192e-f672-4cc0-9539-b4b063bb8f41`.

The [second independent ChatGPT prompt](mnemo-stage-6-stage-7-external-chatgpt-verification-prompt.md)
must now be run in a new connected session. Stage 6 external acceptance is
still pending that independent call sequence. Product Stage 7 remains
separate future ecosystem work, not accepted by these observations. No Git
stage/commit/push, credential rotation, protected-store mutation, serving-role
promotion or public endpoint change occurred.

## 2026-09-27 final contract audit and forward retest preparation

This section supersedes only the earlier deployment status, not its dated
evidence. The second external ChatGPT session confirmed certified production
identities and a complete 2,000-character exhaustive traversal, but found
the 80-character continuation rejected with `invalid_input` /
`contract.validation`. [The final contract audit](mnemo-stage-6-final-contract-and-acceptance-gate-audit.md)
traces complete-item, per-page content accounting: the next item is larger
than 80 characters, so the signed cursor is valid but cannot make that page
fit. It also records a separate confirmed actor-replay defect in authorized
cursor issuance. The actor is now bound from the trusted principal; a
failing-before security regression and final 2,729-pass CI-safe suite verify
the correction. The prior eight-product-file digest `6ecb1158…` is historical.

The owner-authorized forward restart stopped tunnel PID 65196 and its
identified child chain, then started the existing `Mnemo Tunnel` task at
approximately 2026-09-27T17:16:48Z. Tunnel PID **79448** and interpreter
PID **89340** run the unchanged signed launcher; the venv imports this
checkout. The nine-product-file content digest is
`6dafd086decdef5d046aedc85695400c342fbade99533951c47eb81e018127e1`.
Health and readiness returned HTTP 200, control-plane polling became
healthy and the `main` stdio channel probe was `ok`. This is operator-side
source/process attestation, not a public MCP revision field.

A separate certified local stdio session listed **14 tools**. The exact
authorized 80-character first page returned one item and a cursor, and its
unchanged continuation returned the expected safe terminal limitation
(request IDs `f73f9f90-a29e-4241-8f6c-827a479fe79e` and correlation
`55866908-bbb7-4bf3-b082-5b94cba92cd1`). A **new** 2,000-character
traversal completed in two pages (requests
`9af6df74-2d4e-4799-be67-f6ed250e8e85` and
`c250a505-c1fa-4081-abd1-ebf8b3504d53`). No authenticated external
ChatGPT call was made in this preparation run.

The final `MNEMO_CI=1` suite passed **2,729**, skipped **18**, warned
**eight** times and reached **90.31%** coverage. Ruff, strict mypy,
compileall, lock check, three package builds, frontend checks/build, three
Compose checks, three Docker builds and diff/link checks passed. The
historical unrestricted protected-manifest assertion is not claimed green.
All four protected DB hashes/sizes/UTC mtimes/sidecars, six protected
artifact hashes and the sole ACTIVE generation matched before and after.
No Git stage/commit/push, protected write or serving-role change occurred.

The [narrow final external prompt](mnemo-stage-6-stage-7-external-chatgpt-verification-prompt.md)
is ready for a **new independent connected ChatGPT session**. Its calls
must be reported separately from operator-side deployment evidence,
existing local forensic acceptance and the older signed startup
convergence artifact. Product Stage 7 remains future ecosystem work.

## 2026-09-27 final acceptance-gate reconciliation

The [fresh gate reconciliation](mnemo-stage-6-final-acceptance-gate-reconciliation.md)
qualifies the previous “ready for retest” handoff. The owner's later
independent ChatGPT observations confirmed the 2,000-character completion,
the expected 80-character terminal budget limitation, signed tamper/budget
replay denial and scoped metadata/OCR/structured behavior. They did **not**
provide a fresh four-transport behavioral certificate or a ready FinalQA V2
execution. The current architecture keeps broad document/exact/asset family
registration separate from the 14 tool names and from persisted
representation availability.

This pass found a real positive certified-production structured fixture by
read-only discovery. A separate certified local stdio session returned 31
READY datasets for one authorized exact version, then one-row signed
pagination and a valid no-match result. The earlier unavailable
codePrompt.js version remains truthfully unavailable; availability is
exact-version-qualified. The current-tree focused direct/real-stdio/SSE/HTTP
and old/new schema matrix passed 96 cases when run with `--no-cov`; a first
focused invocation also passed all cases but correctly failed the
repository-wide 90% coverage gate when applied only to that subset. The
previous complete exact-source CI-safe run remains 2,729 passed, 18 skipped,
eight warnings and 90.31% coverage. No product code or runtime configuration
was changed during this pass, so no new forward restart was needed.

The public tunnel still has no authenticated external MCP automation
available to this task. The existing local listener/process and earlier
external client observations are distinct evidence. The signed startup
convergence certificate remains configuration-bound and does not certify
the newer actor-bound cursor behavior. Accordingly, **fresh Module 8.8.9
four-transport behavioral certification remains blocked**, and a ready
FinalQA V2 tunnel success required by the full Phase 8.8 gate remains
unavailable without its governed multimodal generation. No generation,
projection, credential or serving role was created or changed. The
[updated external handoff](mnemo-stage-6-stage-7-external-chatgpt-verification-prompt.md)
asks for genuine fresh connected-tool checks without treating them as
proof of internal protected-state or four-transport parity.

## Superseding full-system integration — 2026-09-28

The preceding unavailable-generation/service conclusions are historical, not current. The [master applied-remediation record](mnemo-all-completed-stages-full-system-remediation.md) records actual service registration, ADR-0064 text-FinalQA dependencies, binding of existing persisted multimodal generations, strict numeric HTTP validation and separately governed FinalQA evidence delivery with actor ownership. No generation/profile/credential/serving role or signed artifact was changed.

Final product manifest61aee75f5496d83387b533a3c383ea2fba6a6b1ea2e746e85378a8ce2b80f37b; forward restart2026-09-28T04:49:40.519Z; tunnel89408/venvPython86600/interpreter92140. All14 passed real local stdio and authenticated loopback SSE, including original bytes, exact chunk, asset bytes, two persisted analyses, positive structured pagination and cited FinalQA. Actual HTTP FinalQA execution/replay/evidence now all200. Full suite2748passed/18skipped/9warnings/90.31%;133focused passed. All protected identities unchanged; sole ACTIVE generation unchanged. An initial tunnel health timeout was recorded; final health/ready200 and current control-plane poll pass after probes ended.

Use the [complete final 14-tool prompt](mnemo-final-external-chatgpt-acceptance-prompt.md), which supersedes the earlier narrow retest. Fresh authenticated external application and public HTTP evidence are still pending; local health polling is not external acceptance or fresh four-transport certification.
