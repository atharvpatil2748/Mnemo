# Stage 6 final contract and acceptance-gate audit — 2026-09-27

## Scope and baseline

This targeted forward-only audit follows the second independent external
ChatGPT verification. It is not a self-awarded external acceptance. The
initial branch was `main` at
`5d2612fef6d26cc1e1b0547bb5bd3da6abf21187`, equal to `origin/main`,
with 22 modified tracked and nine untracked intended files, none staged.
The existing tunnel tree was PID 65196 → 69648 → 86348 → Python 55896;
loopback health and readiness were 200. The editable environment imported
this checkout. The previous operator-side eight-product-file manifest was
`6ecb1158ddcef2e0d2380676840bfd2df42e1270ab0f4b86fff002441b70c55d`;
it was never an MCP-exposed revision.

Authority: [architecture](../../architecture/current/mnemo_architecture_v2.md)
§§5.2 and 21.3–21.10; [roadmap](../../architecture/current/mnemo_engineering_roadmap.md)
Modules 8.8.4, 8.8.6, 8.8.9–8.8.11; accepted
[ADR-0058](../../adr/active/ADR-0058-advanced-retrieval-completeness-and-result-sets.md),
[ADR-0073](../../adr/active/ADR-0073-mcp-native-retrieval-and-delivery-contracts.md),
[ADR-0076](../../adr/active/ADR-0076-project-owner-engineering-certification-standard.md),
[ADR-0077](../../adr/active/ADR-0077-governed-mutable-workspace-boundary.md), and
[ADR-0078](../../adr/active/ADR-0078-generation-aware-production-credential-lifecycle.md);
the [local forensic closure](mnemo-stage-7-forensic-audit-remediation-and-stage-6-closure.md),
[previous external remediation](mnemo-stage-6-external-audit-remediation.md),
and [preparation record](mnemo-stage-6-external-verification-preparation.md).

## Exhaustive cursor contract and findings

`RetrievalCursorCodec` signs the plan fingerprint, notebook identity, limits,
representation index, offset, snapshot and expiry. The plan includes query,
scope, representation and all budgets. The server reauthorizes each page.
`AdvancedRetrievalService._exhaustive` fetches deterministic source pages and
`_apply_output_bounds` accounts for complete candidate content per **page**;
it does not truncate item text or skip an oversized item. `result_limit=1`
can issue a valid cursor before the length of the next item is known. A cursor
thus preserves the next position; it guarantees neither that a future item
fits the unchanged limits nor that the source remains available. ADR-0073
expressly permits continuation until completion **or a typed terminal
limitation**. If the next item alone exceeds the effective content or byte
ceiling, `_apply_output_bounds` raises `ContractValidationError` instead of
issuing a non-progress cursor, skipping evidence, or fabricating an empty
page. The shared public classifier emits sanitized `invalid_input` /
`contract.validation`, HTTP 422 where applicable, with request-layer reason
and correlation ID. This is a valid, if generic, terminal input-budget
limitation; there is no authoritative requirement for a new budget-specific
public code. Changing the bound requires a **new** traversal because the
signed cursor binds it.

The second external client's 80-character page-one cursor/page-two
`contract.validation` and successful fresh 2,000-character two-page traversal
match the independently reproduced certified-stdio behavior in the
[previous remediation](mnemo-stage-6-external-audit-remediation.md). The
second item's actual content length was 1,148 characters. New exact-boundary
regression checks 81 characters (page two succeeds), 80 (terminal typed
limitation), zero matches, terminal cursor and ordered unique IDs. Existing
tests cover cursor tamper, expiry, query/scope/budget changes, older/newer
SQLite, direct MCP and local stdio/SSE/HTTP serialization; no exact external
opaque cursor bytes were supplied. The final independent client must report
the live 80-character limitation as such and restart at 2,000, never replaying
the 80-character cursor with a different budget.

### Confirmed security defect: actor binding

ADR-0073 requires actor binding. The plan had a
`security_scope_identity` field, but `execute_authorized` previously passed
the unbound plan to cursor encode/decode. A new regression first demonstrated
that actor B could reuse actor A's signed cursor within the same otherwise
authorized notebook. This did not bypass per-page notebook authorization or
prove cross-notebook disclosure, but violated actor-bound continuation.
`AdvancedRetrievalService.execute_authorized` now derives the plan identity
from the trusted `PrincipalContextV1.actor_id`, rejects any conflicting
pre-filled identity, and then uses the existing signed fingerprint. The same
actor continues; a different actor receives a cursor conflict. No client
principal field or new route was introduced. Old in-flight cursors may expire
or conflict after forward restart; clients restart traversal.

## Stage 6 service requirement matrix

| Capability | Authority / Stage 6 gate | Expected certified production state | Observed second external / local state | Disposition |
|---|---|---|---|---|
| Exhaustive retrieval | ADR-0058/0073; 8.8.4 public contract; 8.8.9 parity separate | Exposed, bounded, signed continuation | Exposed; 2,000-character terminal traversal passed externally | Test 80-character terminal limitation and actor binding; no source fallback. |
| Structured retrieval | Architecture §21.8; 8.8.11a–c | Existing authorized projection only; notebook readiness does not promise every version | Exposed/notebook-available; exact codePrompt.js version safely unavailable | No production projection creation; positive local disposable fixture remains distinct. |
| Document delivery | Architecture §21.8 and 8.8.4 | Tool registered; specific persisted representation determines scope availability | Broad family `service_not_registered` | Truthful limitation, not permission to synthesize blocks/original bytes. |
| Exact retrieval | Architecture §21.8 | Exact authorized chunk can be callable independently of broad family | Broad family unavailable | Preserve per-operation distinction. |
| Asset delivery | Architecture §21.8 and 8.8.4 | Tool registered; persisted authorized asset required | Broad family `service_not_registered` | No asset/occurrence fabrication or certification claim. |
| FinalQA V2 | Architecture §§5.2, 21.8; Phase85 runtime dependency definition | Registered/configured composition, but readiness requires governed dependencies and separately certified execution | `buildable`, not ready; multimodal dependency lacks active generation | The dependency on multimodal retrieval is explicit in `mnemo-core/mnemo/phase85/runtime.py`; narrowing it for text-only use would be an architectural/lifecycle change not authorized by this targeted audit. Do not bypass it. |
| Multimodal retrieval | Architecture §21.8 | Generation-backed state is truthful | Active generation unavailable | Not activated. |
| OCR generation | Architecture §21.8 | Distinct from persisted `ocr_text` search | Profile not configured, while OCR-index search can return truthful empty | No OCR model activation. |

The 14-tool inventory and synthetic authorized success matrix satisfy the
local 8.8.4 contract; §21.8 explicitly separates tool visibility from
production readiness. Module 8.8.9 requires a fresh four-transport semantic
matrix and long FinalQA diagnosis for its own certification. The older signed
four-transport startup convergence artifact binds configuration identity,
not this newly changed actor-bound cursor behavior; it is not counted as a
fresh behavioral certificate. An external MCP session also cannot prove
cross-user ACL isolation: the accepted Phase 8.5 schema lacks actor-to-
notebook ownership and enforces canonical notebook membership instead.

## Protected prechange checkpoint

All four databases were hashed read-only before editing:

| Database | SHA-256 | Bytes | UTC mtime | Sidecars |
|---|---|---:|---|---|
| Certified production | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | 189804544 | 2026-09-01T11:09:20.1047581Z | none |
| WP16 | `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d` | 37195776 | 2026-08-29T13:37:31.2308106Z | none |
| Evaluation 8.5 | `bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84` | 45592576 | 2026-09-08T06:41:25.6366051Z | existing zero-byte WAL SHA `e3b0c442…`, 32768-byte SHM SHA `fd4c9fda…` |
| Evaluation 8.6 | `9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2` | 52600832 | 2026-09-08T08:14:51.7220651Z | same accepted WAL/SHM state |

Manifest `e579727c…`, launcher `007ee235…`, signed activation `c17a7f55…`,
certificate `1a69e957…`, final evidence `02551609…` and signed convergence
`b5ccccb9…` matched the authoritative full hashes. Credential registry
metadata showed exactly one ACTIVE generation
`fc85192e-f672-4cc0-9539-b4b063bb8f41`; no secret was displayed.

## Final validation, deployment and decision

The final `MNEMO_CI=1` repository suite completed with **2,729 passed, 18
skipped, eight warnings, 90.31% coverage**, exit 0 (206.38 seconds). The
18 skips are the established CI-policy `local_database` exclusions, not new
xfails. The historical unrestricted protected-manifest lifecycle assertion
was not represented as passing. Two earlier diagnostic full runs failed
before the same-principal SSE/HTTP test fixture was aligned with the now
actor-bound cursor contract: the completed diagnostic had 2,727 passed,
18 skipped, eight warnings and two failed transport-matrix cases. Six
transport-matrix cases passed after that test-only fixture correction.

The focused actor-replay regression failed **before** the product fix (`DID
NOT RAISE`) and passed after it. The core/server retrieval focus passed 63
tests; the older/newer public immutable-schema traversal variants passed
all four cases after using a stable authenticated actor for each traversal.
The 14-tool real-local transport matrix, including SSE with the same actor
as direct MCP, passed six cases. The final full suite includes these tests.
No cursor signature, expiry, scope, snapshot or budget guard was weakened.

Final checks passed: `ruff check .`, `ruff format --check .` (523 files),
strict mypy over all three Python packages (291 source files), `compileall`,
`uv lock --check` (171 packages), three Python package builds, frontend
format/lint/typecheck/test/build (one UI test), three Compose configurations,
and all three available local Docker image builds. `git diff --check`
passed. Changed-document relative links were checked. One initial Ruff
attempt named a nonexistent directory; the actual repository-wide commands
passed and that diagnostic invocation is not counted as a gate.

### Forward-only restart and local live evidence

At approximately 2026-09-27T17:16:48Z, the previously identified tunnel
PID 65196 was stopped. Its exact orphaned child chain (cmd 69648, venv
Python 86348, interpreter 55896) was identified and stopped. The existing
`Mnemo Tunnel` scheduled task restarted the unchanged launcher/configuration.
New tunnel PID 79448, cmd child 87168, venv Python 87840 and interpreter
89340 began at approximately 17:16:48–51Z. The tunnel is again bound only
to 127.0.0.1:8080; health and readiness returned HTTP 200. An early health
probe had no completed control-plane poll, while the later probe returned
`result: ok` with a successful poll. `/api/status` reported the `main` stdio
channel enabled and probe `ok` through the existing direct control-plane
route. No public endpoint, credential or signed launcher changed.

The interpreter started after the edited `advanced.py` file mtime; the
authorized venv imports `mnemo` and `mnemo_server` from this checkout. The
operator-side SHA-256 of newline-joined, sorted `relative-path SHA-256`
entries for nine changed product Python files is
`6dafd086decdef5d046aedc85695400c342fbade99533951c47eb81e018127e1`.
That digest is not exposed by MCP, so external clients cannot independently
verify loaded-source identity using tool results alone.

At approximately 17:18:14Z, a separate certified **local stdio** session
listed 14 tools and repeated the exact authorized `buildCodePrompt` request.
At budget 80: page one returned one item, `truncated`, cursor present,
request `f73f9f90-a29e-4241-8f6c-827a479fe79e`; unchanged-cursor page
two returned safe `invalid_input` / `contract.validation`, layer `request`,
correlation `55866908-bbb7-4bf3-b082-5b94cba92cd1`. A fresh budget-2000
traversal returned one item and a cursor (request
`9af6df74-2d4e-4799-be67-f6ed250e8e85`), then one terminal item with
`complete` and no cursor (request
`c250a505-c1fa-4081-abd1-ebf8b3504d53`). No opaque cursor or item
content was logged. This is a real local stdio boundary, **not** an
authenticated independent external ChatGPT call. Direct MCP, SSE, HTTP and
older/newer disposable-schema boundaries passed in the CI-safe suite; a
fresh four-way signed behavioral certification remains Module 8.8.9 work.

### Protected postcheck and remaining gates

After the restart and local probe, the four protected database hashes, byte
sizes, UTC mtimes and sidecar states matched the prechange table exactly.
Production and WP16 remain sidecar-free; the evaluation WAL/SHM sidecars
retain their accepted hashes, sizes and mtimes. Manifest, launcher, signed
activation, certificate, final evidence and convergence hashes match their
accepted identities. The credential registry still contains exactly one
ACTIVE generation `fc85192e-f672-4cc0-9539-b4b063bb8f41`.

The final external retest still must establish fresh connected-client
observations of the 80-character terminal limitation, 2,000-character
completion, truthful scope-qualified capabilities and applicable authorized
tools. It cannot itself prove internal protected-state immutability,
cross-user ACL behavior, source-code revision or four-transport parity.
Production FinalQA remains buildable but not ready because the certified
multimodal generation is unavailable; broad document/exact/asset family
availability remains truthful and must not be fabricated. The existing
signed convergence artifact is configuration-bound, not a certificate for
the new actor-bound cursor behavior. Product Stage 7 remains outside this
Stage 6 retest.

**Decision: READY_FOR_FINAL_STAGE_6_EXTERNAL_RETEST.** This is preparation
for independent external verification, not Stage 6 external acceptance.
No Git staging, commit, push, PR, merge, serving-role promotion, credential
rotation or protected-store mutation occurred.
Final Git state: `main` at
`5d2612fef6d26cc1e1b0547bb5bd3da6abf21187`, with **24 modified
tracked files, 10 intended untracked files and zero staged files**. The
existing 8.8.10/8.8.11 changes were preserved; this run changed only the
actor-bound cursor path, its regressions/transport fixtures and current
documentation/evidence. The live public endpoint was not changed. The
independent external ChatGPT retest has **not** yet occurred.

The [narrow final external prompt](mnemo-stage-6-stage-7-external-chatgpt-verification-prompt.md)
requires fresh connected-tool evidence. Product Stage 7's Plugin SDK,
official EPUB/browser-history plugins, published OpenAPI, MCP specification
suite and Open WebUI integration remain separate and unverified here.
