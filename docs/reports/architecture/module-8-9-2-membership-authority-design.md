# Module 8.9.2 — membership authority approval dossier

Date: 2026-10-21. Status: **design proposed; state migration not approved**.
This is the 8.9.2a approval gate, not an indexed-serving or multi-user
certification. No production membership record, notebook, index, credential,
cursor, or runtime selection was changed by this dossier.

## Verified baseline and implementation boundary

The [roadmap](../../architecture/current/mnemo_engineering_roadmap.md) requires
8.9.2a authority choice and separately approved migration before writes;
8.9.2b principal-first exact scope depends on 8.9.2a; 8.9.2c cursor and
metadata disclosure depends on 8.9.2b. [ADR-0080](../../adr/active/ADR-0080-phase-8-9-unified-authorized-retrieval-plan.md)
rejects notebook existence or a client ID as authorization. ADR-0075 requires
an exact notebook/source/document/version association and safe ambiguity;
ADR-0058/0073 require signed, expiring, reauthorized continuation.

| Existing behavior | Source | Missing property / risk |
|---|---|---|
| HTTP JWT signature/time validation and API-key authentication populate claims; `principal_from_claims` hashes a nonblank `sub` into an actor UUID. API-key mode uses one `api-key` subject. | `mnemo-server/mnemo_server/auth.py:129`, `services/authorization.py:157` | JWT issuer/audience/mandatory subject are not validated here. API-key mode does not distinguish users. A multi-issuer or multi-user deployment cannot safely equate bare subjects or one API key with distinct owners. |
| An operational SQLite grant store has explicit `owner`/`reader` rows and retired notebook IDs; missing/malformed store denies. `grant` and `retire_notebook` are mutation helpers, not public routes. | `services/scope_authority.py:15-132`; `tests/test_scope_authority.py` | The grant protocol has only `permits(actor, notebook)`: no operation/role decision, per-notebook revision, actor listing, revocation of one share, or controlled onboarding transaction. Repository search found no production composition installing `engine.server_scope_authority`. Its existence is not live authority. |
| CentralAuthorizationService rejects unauthenticated principals and checks an installed grant authority before notebook lookup, then resolves exact document association. Without an installed authority it retains legacy existence-based fixture behavior. | `services/authorization.py:46-154`, `mnemo-core/mnemo/retrieval/scope.py:35-89` | The fallback is unacceptable for future indexed private multi-user serving. An exact document/source ID cannot stand in for membership. The core resolver itself deliberately does not decide actor ownership. |
| Automatic V2 query requires one unambiguous notebook and calls central authorization. Current V2 retrieval and structured/capability services have single-notebook authorization branches. | `services/automatic_query_v2.py:28-72`, `services/retrieval_v2.py:55-95`, `services/structured_v2.py:122-154`, `services/capabilities_v2.py:296-312` | None establishes all-authorized multi-notebook scope. No one-notebook guard may be lifted before the approved membership relation is installed and verified. |
| HTTP notebook CRUD/list/summary/timeline and retained MCP `list_notebooks` read storage directly; production mutation additionally requires an approved mutable workspace. | `routers/notebooks.py:60-210`, `mcp/tools.py:1624-1676`, `dependencies.py:56-72` | A future indexed multi-user route must authorize before listing, metadata, mutation or existence disclosure. Current UNINDEXED production refusal is a separate safety boundary, not evidence these routes are ready to serve private users. |
| `CursorCodecV2` signs/limits/expires caller-supplied binding and snapshot. Advanced retrieval binds plan fingerprint and notebook; structured retrieval binds notebook, request and dataset IDs. | `mnemo-core/mnemo/cursors.py:72-205`, `retrieval/advanced.py:72-190`, `services/structured_v2.py:420-463` | The codec can enforce a supplied membership revision, but no authoritative revision is persisted or threaded through all issuers/continuations. Some existing plan fingerprints include actor context; that is not a universal revocation guarantee. |
| Sources reference notebooks and documents; versions are global document records. | `mnemo-core/mnemo/storage/sqlite.py:107-122,189-205` | Shared document/version bytes must be authorized through the notebook-specific source association and exact version, not global document ownership or content hash. |

The 8.9.1 design record reports a passing 3,164-test coverage-enabled run
before this task. That historical run is not evidence that this proposed
membership migration is implemented. The production selector is UNINDEXED;
no indexed multi-user route is being enabled here.

## Authority choice for owner approval

**Recommended: extend the existing server-owned, persisted explicit-grant
authority**, not a new parallel authorization service. A trusted, validated
transport principal resolves to an actor; the operational membership store
decides notebook and operation access; central authorization binds sources,
documents and exact versions before retrieval or disclosure. This reuses the
existing grant-store and authorization seam but requires a separately
reviewed schema/lifecycle migration and all-route composition before serving.

| Option | Fit | Safety/cost |
|---|---|---|
| Persistent server-owned membership, extending the existing `notebook_grants`/retirement store | Existing code and disposable tests demonstrate explicit grants and no implicit enrollment. Local, auditable revocation is possible without an unavailable external service. | Separate ACL and notebook stores cannot be assumed atomically committed together. A revision/epoch, operation-specific role checks, controlled provisioning, consistent snapshots and recovery must be added and tested. |
| Trusted external membership resolver | Could share identity governance with a real external provider if one were configured and contractually trusted. | No such resolver, signed membership assertion, freshness/revocation contract, outage policy or deployment evidence exists in this repository. Inventing one would add an unreviewed trust boundary. It cannot be a silent fallback. |

**Proposed roles, subject to explicit approval:** `owner` may read and perform
governed notebook mutations and sharing; `reader` may read only. Sharing is an
explicit owner-authorized grant to a separately authenticated actor; there is
no public/all-users role or grant inferred from document hashes. The existing
schema already accepts owner/reader, but currently `permits` does not enforce
operation-specific roles. No new public sharing endpoint is proposed here.

**Principal trust:** use only transport-validated identity. For multi-user
serving, require a deployment-pinned issuer/audience and nonblank subject (or
an equivalently reviewed trusted principal contract) before mapping to an
actor. Preserve existing actor UUID mappings for any explicitly attested
legacy grants; do not silently re-key them when introducing issuer scoping.
Single API-key mode represents one server principal, never multiple users.
Missing, conflicting or untrusted claims, authority outage and stale
membership snapshots deny access without revealing notebook existence.

## Proposed lifecycle and state migration — not executed

1. Freeze the current UNINDEXED baseline. Inventory notebook IDs, existing
   grant/retirement rows if an operational ACL store is selected, trusted
   identity configuration, source associations and active consumers using
   read-only, WAL-aware inspection. Fingerprint both stores and take
   recoverable, consistent snapshots before any approved migration.
2. Approve a versioned additive operational ACL migration: per-notebook
   authorization revision (monotonic), actor/notebook role and status,
   retirement tombstone, auditable grant/revoke actor and policy version.
   Preserve existing grants only after provenance and actor mapping are
   attested; do not derive owners from notebook creator guesses, filenames,
   historical IDs, or a matching corpus. Existing notebooks lacking an
   attested owner remain unassigned/inaccessible to private serving.
3. On new notebook creation, bind a server-generated ID to the authenticated
   creator through a controlled two-store lifecycle. The notebook may be
   persisted before its grant, but no success/visibility is returned until
   the explicit owner grant commits; any crash window is **unassigned and
   fail-closed**, with operator reconciliation rather than implicit access.
   Retire ACL authority before storage deletion so interrupted deletion
   leaves an inaccessible notebook; never reuse a retired ID.
4. Sharing, role changes, individual revocation and deletion update the ACL
   revision atomically with the grant change. A current revision is required
   on every scope, cursor continuation and scoped metadata/capability read.
   No cross-request cached grant may outlive a revision; authority errors
   fail closed. Existing cursor keys/format remain; reauthorization and
   revised binding invalidate older continuations without silent restart.
5. Install the authority only after disposable migration, cross-user,
   shared-document, interruption/retry, role, cursor, HTTP/MCP and rollback
   tests pass. Keep the one-notebook guard and UNINDEXED production selection
   until separately authorized indexed-serving gates are met.

The required snapshot/recovery operation, schema migration and operational
grant writes are **not approved by the current general Module 8.9.2 mandate**.
The proposed two-store lifecycle is fail-closed, but its exact recovery
protocol and ordering require fixture proof before live use. Rollback before
cutover is no-op; after an approved migration, revert the integration to
UNINDEXED/one-notebook fail-closed behavior, preserve ACL/tombstones and
snapshots, and never restore stale grants or cursors merely to regain service.

## Threats, dependent tasks and test gate

| Threat | Required control and proof before indexed multi-user serving |
|---|---|
| Forged actor/notebook/store/generation ID or shared API key treated as owner | Transport-owned principal with reviewed issuer/subject trust; reject client authority fields; explicit operation grant; missing authority denies. |
| Cross-user enumeration, confused-deputy metadata, capability or error oracle | Principal-first authorized-notebook list; same safe response for unauthorized and nonexistent IDs; exact source/document/version membership before content, metadata, citation or provider disclosure. Exercise HTTP and MCP. |
| Shared global document/version leaks through another notebook | Resolve notebook-specific source association and exact version per actor, including after candidate retrieval and delivery. Test two notebooks and cross-scope source IDs. |
| Stale grants, cached capability, cursor replay after revoke/policy/alias change | Atomic ACL revision, no stale cache, reauthorize each page, bind actor/scope/revision/policy/aliases/representation/query/limits to existing signed cursor; tamper, expiry and replay tests. |
| Partial two-store mutation or ambiguous legacy owner | No implicit grant; interrupt/retry fixtures; snapshot restore evidence; manual reconciliation of unassigned records and preservation of unrelated notebooks. |

8.9.2b may implement principal-first discovery and exact authorized scope only
after this authority design/migration is separately approved. Existing
`StorageDocumentScopeResolverV1` can remain the exact association component;
central authorization must make the membership decision first. 8.9.2c then
extends the existing cursor bindings and scoped disclosure, not the signing
format. Current list/CRUD and cursor code are **not** certified for private
indexed multi-user service. Pure codec and disposable ACL fixtures can prove
seams but cannot substitute for authority integration.

## Exact approval requested before state writes

Approve or revise **(a)** server-owned persisted owner/reader grants with
explicit sharing and operation-specific permissions, **(b)** a versioned
operational ACL revision/tombstone migration, **(c)** trusted actor mapping
and treatment of any existing grants, and **(d)** the fail-closed two-store
create/delete/revoke and recovery sequence above. Approval must explicitly
state whether any pre-existing unassigned notebook receives a reviewed owner;
the safe default is **none**. Only then may code that writes the new membership
state, migrates legacy grants, installs production scope authority or enables
multi-notebook resolution be implemented. No approval is inferred here.

**Exit status:** 8.9.2a **PARTIAL** (proposed design and threat model; migration
approval pending); 8.9.2b **BLOCKED** before implementation by the 8.9.2a
approval gate; 8.9.2c **BLOCKED** before implementation by 8.9.2b and the
same authority/revision gate. Their existing seams were analyzed, not wired.
Module
8.9.2 **PARTIAL / NOT COMPLETE**. External tunnel/UI evidence remains
unavailable and is not represented by local tests.

## Pre-approval validation (2026-10-21)

The new `mnemo-server/tests/test_module_892_design_seams.py` uses only a
`tmp_path` ACL and the existing pure cursor codec. It proves that explicit
owner/reader rows do not authorize a stranger or another notebook, retirement
invalidates both grants, and a *supplied* actor/revision/policy/alias/
representation/query binding causes the existing signed codec to reject
context changes, tampering and expiry. It does **not** prove that production
currently stores a revision or passes it through retrieval.

With `MNEMO_CI=1`, the main-interpreter focused pytest command on this new
file, `test_scope_authority.py`, `test_production_runtime_selection.py`,
`test_mcp_principal.py`, `test_retrieval_v2.py` and core `test_cursors.py`
exited 0: **126 passed, 0 failed, 0 skipped**, two warnings (one SDK
deprecation and one local pytest-cache ACL warning), 12.09 seconds. JUnit:
`scratch/module892-preapproval-focused-junit.xml`. The command used
`-o addopts=''`, so it is a focused diagnostic run, not the full configured
coverage gate. No full suite or external transport was run for this task.
An independent main-interpreter diagnostic run of existing
`test_server_notebooks.py` and `test_mcp_route_contracts.py` exited 0 with
**49 passed, 0 failed, 0 skipped**, one local pytest-cache ACL warning;
JUnit: `scratch/module892-preapproval-notebook-routes-junit.xml`. This is
current-route compatibility evidence, not a private multi-user authorization
claim.
Focused Ruff lint, strict mypy on the new test, Python compileall and
git diff --check exited 0. Initial Ruff format check reported one line-wrap
difference; formatting that exact new test file corrected it. The final
repository-wide Ruff lint and format checks exited 0 (592 files formatted),
strict mypy on the new test exited 0, and 25 relative document links resolved.
No existing production source or operational ACL schema was edited.

Read-only post-test checks: 5/5 retired DB hashes and 5/5 recovery-snapshot
hashes match their receipts; both original-byte manifests verify 44/44 and
24/24. The production selector is UNINDEXED, runtime DB absent, credential
registry hash unchanged with no active generation, and a local process scan
found zero matching tunnel processes. The main .venv remains present, the
GPU-preflight venv absent, and no `goldenDataset/` changes are pending. No
file was staged or committed. These observations are local and point-in-time;
no indexed production or external transport check was attempted.

## Owner approval and isolated implementation addendum (2026-10-21)

The owner subsequently approved the server-owned owner/reader model and an
additive ACL revision/tombstone migration **only for disposable development
stores**. This approval supersedes the earlier pending-approval label above;
it does not authorize migration of an operational ACL or serving activation.

`services/scope_authority.py` now creates `notebook_acl_revisions` and
`notebook_create_intents` on a fresh explicitly initialized ACL store.
`migrate_legacy_grants_unverified()` is an explicit transaction, never a
startup migration. On an old grant table it adds `status` with the default
`unverified`, preserving actor/role rows but denying all of them until a
separate attestation process is approved. It initializes revisions without
granting access. Retired IDs remain tombstoned. Repeating migration does not
activate legacy rows. An incomplete legacy schema rolls back, including the
ALTER TABLE, in a disposable SQLite test. The intended operational procedure
still requires a read-only WAL-aware inventory, exact-store selection,
consistent snapshot/backup, review of legacy grant provenance and actor
mapping, a rollback drill, and separate production authorization. None was
performed here.

Explicit new grants and individual revocations advance a notebook revision
in the same ACL transaction; a duplicate grant or no-op revoke does not.
Retirement tombstones before deleting grants and advances the revision once.
Owner can request write permission; reader cannot. `authorized_notebook_ids`
returns active explicit memberships only. The isolated
`MembershipNotebookLifecycle` reserves a server-generated notebook ID and
actor in the ACL before writing notebook storage, then verifies the exact
stored record before activating its owner. A crash before activation leaves
an inaccessible pending intent that requires an explicit retry with the
durable token; a delete tombstones before storage deletion and may be retried.
These are **two stores without cross-store atomicity**. The fixture proves
the tested crash windows, not arbitrary concurrent create races or an
operational recovery drill. The coordinator is not installed in HTTP/MCP.

`TrustedJWTActorMapper` verifies a signed JWT and deployment-pinned issuer,
audience, nonblank subject and expiry; it never accepts client actor IDs as
grants. It is opt-in and not wired to the current auth middleware. Existing
subject-only actor IDs are neither re-keyed nor granted. The isolated
`AuthorizedNotebookScopeResolver` authorizes selection before notebook
storage reads, denies private and nonexistent IDs alike, and rechecks the ACL
revision after reads. Exact source/document/version enforcement still depends
on the existing central authorization and is not integrated with this new
resolver. The cursor fixture now binds an actual ACL revision and rejects a
token after revoke, but production cursor issuance/continuation does not yet
thread that revision or reauthorize every page. Notebook CRUD/list, MCP list,
and metadata/capability surfaces are **not** certified for indexed private
multi-user serving. Keep production UNINDEXED and the one-notebook guard.

**Status:** 8.9.2a PARTIAL (approved design, additive fixture migration and
core lifecycle implemented; production integration and full recovery evidence
outstanding); 8.9.2b PARTIAL (isolated principal-first scope, no route or exact
document integration); 8.9.2c PARTIAL (codec/revision fixture only, no complete
runtime cursor or disclosure binding). Module 8.9.2 is NOT COMPLETE. The next
safe work is to prove concurrent and failure recovery, integrate trusted
identity and ACL through the existing authorization boundary, then cover all
notebook, retrieval, metadata and cursor paths without relaxing UNINDEXED.
The low-level `grant`/`revoke` helpers accept an operator identifier but do
not authenticate or authorize that operator themselves; they must remain
server-internal until an owner/operator authorization workflow is integrated
and tested. `MembershipNotebookLifecycle` uses `upsert_notebook`, so concurrent
create collisions have not been proven safe for live use. Neither helper is
connected to a public route. These are explicit blockers, not production
capabilities certified by the isolated tests.
Any operation on a production membership store requires separate approval
with exact target, preconditions, backup, rollback and verification plan.

### Verification for this addendum

The main `.venv/Scripts/python.exe` ran the focused 8.9.2 fixture, existing
notebook-route, MCP-route/principal, V2 retrieval, production-selection and
core cursor suites with `pytest -q -o addopts=''`: **190 passed, zero failed,
zero skipped**, exit 0. This diagnostic override omits the repository's full
coverage gate; the full suite was not rerun. One existing MCP deprecation
warning and one local pytest-cache ACL warning were emitted. A first attempt
at the same group specified the wrong cursor-test path and collected no tests;
the corrected path was `mnemo-core/tests/unit/test_cursors.py`. Ruff lint and
format checks on nine affected Python files, strict mypy on those nine files,
compileall on the four changed service modules, and `git diff --check` all
exited 0. No deployed MCP/HTTP, production membership or external client test
was run.

Read-only post-run verification found the production selector `UNINDEXED`, no
`data/notebook_runtime/mnemo.db`, five retired DB hashes matching the five
post-reset receipts, and five recovery snapshot hashes matching those receipts.
`verify_source_manifest` rechecked original bytes: 44/44 and 24/24. The
non-secret credential registry had no active generation and one REVOKED
generation; a local process scan saw zero matching tunnel processes. The
main `.venv` existed and the GPU-preflight venv was absent. `git status`
reported no pending `goldenDataset/` changes, and the staged diff was empty.
These are point-in-time local checks, not certification of indexed serving.

## Continuation: operator and route-integration review (2026-10-21)

The subsequent continuation inspected the actual HTTP router registrations,
MCP tool dispatcher, advanced/structured/delivery cursor issuers and the
existing ACL and notebook stores. This matrix distinguishes working guards
from full membership integration; all ACL-attached route tests use disposable
stores. No operational ACL was migrated or installed.

| Entry point | Current identity source | ACL check/revision | Evidence or remaining gap |
|---|---|---|---|
| HTTP `/v1/notebooks` CRUD/list/summary/timeline/graph | JWT middleware plus deployment-pinned `TrustedJWTActorMapper` when an ACL is attached | Principal-first ACL selection; write requires owner. No response-wide revision snapshot. | New HTTP test proves owner/reader, legacy-unassigned, stranger/nonexistent denial, list filtering and delete. Legacy behavior remains when no ACL is attached. |
| MCP `list_notebooks` and `get_notebook_summary` | Transport-supplied principal | ACL filtering or central notebook check when ACL attached; no revision-bound metadata snapshot. | Direct MCP dispatch test proves positive and negative scopes. SSE/stdio transport-to-new-mapper binding is not established. |
| HTTP sources, notes, sessions, insights, V1 query/search/streaming/FinalQA, V2 retrieval/structured/delivery/capabilities | Existing middleware claims, with differing service checks | Explicit dependency guard refuses these routes when an ACL is attached; no indexed multi-user retrieval is enabled. | Fail-closed route test; full authorized route behavior is not implemented. |
| Other MCP retrieval, delivery, capability, timeline and source tools | Existing MCP principal | Explicit dispatcher guard refuses these tools when an ACL is attached. | No claim of feature parity or external transport evidence. |
| Advanced, structured and delivery cursors | Existing service-specific bindings and signed codecs | No universal authoritative ACL revision in issue/continue paths. ACL-attached public retrieval paths are disabled. | Earlier pure codec fixture rejects a changed revision, but application continuation remains unimplemented. |

`MembershipOperatorService` is server-only and requires a signed,
deployment-pinned JWT for each grant, revoke or recovery request. Only a
current explicit owner may grant or revoke a reader, and unassigned legacy
notebooks cannot be bootstrapped through it. The low-level store helpers are
still internal primitives, not safe public grant endpoints. The SQLite
notebook store gained insert-if-absent semantics for the isolated create
coordinator. A concurrent-create test initially exposed nested transactions
on one aiosqlite connection; a per-store notebook write lock corrected that
specific race. A concurrent-delete test later exposed the same issue; insert,
upsert and delete now share that lock, and concurrent delete/retry preserves
the tombstone revision. SQLite's unique notebook key rejects a collision
without overwriting the existing row. Durable create completion records make
exact-token retry idempotent; interrupted delete tombstones before storage
deletion. This does
not establish atomic commits across the two stores or prove every crash and
multi-process interleaving. The lock is per `SQLiteStore` instance, not a
cross-process or cross-store transaction. No cross-store rollback is claimed.

**Current assessment:** 8.9.2a PARTIAL (operator and isolated lifecycle
implemented, operational onboarding and exhaustive recovery not proven);
8.9.2b PARTIAL (HTTP notebook and two MCP routes scoped, other existing routes
disabled under ACL); 8.9.2c BLOCKED for end-to-end revision-bound
continuation and disclosure. Module 8.9.2 remains PARTIAL. The disabled
routes must not be counted as working private multi-user features. A later
public cutover still needs route-by-route authorization, cursor binding,
cache/metadata review and external transport evidence, and any production ACL
operation still requires separate target-specific authorization.

### Continuation verification and residual boundaries

The first full coverage run found nine regressions in this continuation:
the registration snapshot lacked the newly attached HTTP dependency, and
FastAPI could not inject a `Request` into that dependency on WebSocket routes.
The snapshot was regenerated with the repository's explicit `--replace`
workflow only after comparing registration names/defaults; the guard now
accepts `HTTPConnection` for HTTP and WebSocket. The formerly failing snapshot
and streaming group passed 15/15 in isolation. A new disposable WebSocket
test confirms an ACL-attached unintegrated route is denied with a typed 503
response; it passed independently. The first full run's 9 failures, 3,187
passes, 6 skips and 90.04% coverage are retained as diagnostic evidence at
`scratch/module892-current-full-junit.xml` and
`scratch/module892-current-full-coverage.xml`, not as a passing gate.

The intermediate corrected full coverage run exited 0 with 3,197 passed,
6 skipped, 9 warnings and 90.17% combined coverage; its JUnit/coverage
artifacts are `scratch/module892-final-full-junit.xml` and
`scratch/module892-final-full-coverage.xml`. A later concurrent-delete test
exposed a shared-connection transaction race, so the suite was repeated on
the final code snapshot. The final command was:

```powershell
$env:COVERAGE_FILE='scratch/.coverage-module892-final-current'
.venv\Scripts\python.exe -m pytest -q --junitxml=scratch/module892-final-current-junit.xml -o "addopts=--strict-config --strict-markers --cov=mnemo --cov=mnemo_server --cov=email_ingestion --cov-config=pyproject.toml --cov-branch --cov-report=term-missing --cov-report=xml:scratch/module892-final-current-coverage.xml --cov-fail-under=90"
```

It exited 0: **3,198 passed, 6 skipped, 0 failed, 9 warnings, 90.17%**
combined coverage against the 90% gate. Warnings include an existing
Starlette/httpx deprecation and local pytest cache write denial. Focused
final-tree scope/contract/streaming tests passed 95/95; SQLite storage plus
membership lifecycle/HTTP tests passed 47/47. Repository-wide Ruff lint
passed; Ruff format reported 602 files already formatted. Strict mypy passed
for 323 source/test files after adding explicit non-null assertions to
pre-existing streaming event tests. Compileall and `git diff --check` exited
0. The assertions strengthen type narrowing without changing server behavior
or event expectations. The intervening repeat started before the
concurrent-delete fix was stopped and is not counted as verification.

| Stage | Demonstrated | Unmet exit evidence |
|---|---|---|
| Grant operator | Server-only signed deployment JWT, explicit owner-only reader grant/revoke, legacy quarantine; disposable positive/negative tests. | No operational grant endpoint or authenticated owner assignment for legacy notebooks; production migration requires separate authorization. |
| Two-store lifecycle | Durable create intent/completion, exact retry, tombstone-before-delete, one-connection concurrent create/delete and collision tests. | No cross-store transaction, exhaustive process-interruption/multi-process proof or unavailable-store recovery demonstration. |
| Route integration | HTTP notebook routes and MCP notebook list/summary authorize principal first; HTTP/MCP/WS alternate paths fail closed under an ACL. | Retrieval, exact delivery, source/metadata/capability paths are disabled rather than fully authorized; response-publication revocation race is not excluded. |
| ACL revision continuation | An isolated signed-codec fixture rejects changed revision. | No public application cursor issuer/continuation binds authoritative ACL revision; no authorization-sensitive cache validation proof. |

These are development/test observations only. The installed production
selector remains `UNINDEXED`; no operational ACL migration, production
index or external transport was exercised. Consequently Module 8.9.2 remains
PARTIAL despite the passing final full-suite gate.

After the final suite, read-only checks matched all five retired database
SHA-256 values and five recovery snapshot values to the 2026-10-10 receipts.
Original-byte source-manifest verification passed 44/44 and 24/24. The
production selector was `UNINDEXED`, `data/notebook_runtime/mnemo.db` was
absent, the non-secret credential lifecycle view had no active generation
and all recorded generations were revoked, and the local process scan found
zero matching `certified-tunnel-stdio` processes. The main `.venv` exists,
`scratch/.venv-gpu-preflight` remains absent, nothing is staged, and the
current working tree has no pending `goldenDataset/` changes. These are
point-in-time checks, not external transport or production certification.


## Continuation route-by-route admission inventory (2026-10-21)

This is the registered public surface from the versioned snapshot plus both WebSocket aliases; it is not a claim of implemented indexed serving. In the table, **J** means the HTTP membership principal is reverified from a deployment-pinned signed JWT; **T** means an MCP server principal is supplied by the transport (the new trusted mapper's end-to-end SSE/stdio binding remains unverified); **ACL** means principal-first notebook resolution; **R2** means ACL permission and revision are checked again after data assembly but before handler return. R2 is *not* an atomic guarantee through ASGI serialization, network transmission, or concurrent writes. **S** routes are the system router, **U** routes are unintegrated, and both fail closed when an ACL is attached. H1 is `test_module_892_http_routes.py`; H2 is `test_server_streaming.py`; M1 is direct `execute_mcp_tool` in H1; C is registration/guard inspection only. A representative guard test does not prove every route's positive behavior. An absent ACL retains frozen legacy fixture behavior, while production remains `UNINDEXED` and does not serve the retired index. Internal service calls can still bypass transport dependencies; they are not certified as a new multi-user public boundary.

| Entry point | Exposure | Trusted identity | Authorization/scope | Document/version | ACL revision | Cache/stream | Evidence/gap |
|---|---|---|---|---|---|---|---|
| HTTP GET `/v1/health` | health/provider state | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | H1 representative; aliases C |
| HTTP GET `/health` | health/provider state | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | H1 representative; aliases C |
| HTTP GET `/v1/config` | runtime config | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | H1 representative; aliases C |
| HTTP GET `/config` | runtime config | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | H1 representative; aliases C |
| HTTP GET `/v1/config/models` | model config | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | H1 representative; aliases C |
| HTTP GET `/config/models` | model config | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | H1 representative; aliases C |
| HTTP PATCH `/v1/config` | runtime config | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | H1 representative; aliases C |
| HTTP PATCH `/config` | runtime config | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | H1 representative; aliases C |
| HTTP GET `/v1/jobs` | job state | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | H1 representative; aliases C |
| HTTP GET `/jobs` | job state | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | H1 representative; aliases C |
| HTTP GET `/v1/jobs/{job_id}` | job state | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | H1 representative; aliases C |
| HTTP GET `/jobs/{job_id}` | job state | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | H1 representative; aliases C |
| HTTP POST `/v1/query/stream` | retrieval/evidence | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | H2 SSE not ACL-positive |
| HTTP POST `/v1/notebooks` | notebook metadata | J | ACL notebook | No document filter; source relations not rechecked | R2, not atomic send | Raw keyset (list); no response cache | H1 |
| HTTP GET `/v1/notebooks` | notebook metadata | J | ACL notebook | No document filter; source relations not rechecked | R2, not atomic send | Raw keyset (list); no response cache | H1 |
| HTTP GET `/v1/notebooks/{notebook_id}` | notebook metadata | J | ACL notebook | No document filter; source relations not rechecked | R2, not atomic send | Raw keyset (list); no response cache | H1 |
| HTTP PATCH `/v1/notebooks/{notebook_id}` | notebook metadata | J | ACL notebook | No document filter; source relations not rechecked | R2, not atomic send | Raw keyset (list); no response cache | H1 |
| HTTP DELETE `/v1/notebooks/{notebook_id}` | notebook mutation | J | Owner ACL before tombstone/delete | No document filter; source relations not rechecked | Tombstone before store delete; no R2 after deletion | No stream/cache use | H1; concurrent revoke/write race not excluded |
| HTTP GET `/v1/notebooks/{notebook_id}/summary` | summary/source refs | J | ACL notebook | No document filter; source relations not rechecked | R2, not atomic send | Raw keyset (list); no response cache | H1 |
| HTTP GET `/v1/notebooks/{notebook_id}/timeline` | events/source refs | J | ACL notebook | No document filter; source relations not rechecked | R2, not atomic send | Raw keyset (list); no response cache | C; ACL route denial untested |
| HTTP GET `/v1/notebooks/{notebook_id}/graph` | entity graph | J | ACL notebook | No document filter; source relations not rechecked | R2, not atomic send | Raw keyset (list); no response cache | C; ACL route denial untested |
| HTTP POST `/v1/notebooks/{notebook_id}/sources` | source metadata/ingest | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP GET `/v1/notebooks/{notebook_id}/sources` | source metadata/ingest | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP GET `/v1/notebooks/{notebook_id}/sources/{source_id}` | source metadata/ingest | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP DELETE `/v1/notebooks/{notebook_id}/sources/{source_id}` | source metadata/ingest | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP GET `/v1/notebooks/{notebook_id}/sources/{source_id}/status` | source metadata/ingest | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP GET `/v1/notebooks/{notebook_id}/sessions` | session/turns | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP POST `/v1/notebooks/{notebook_id}/sessions` | session/turns | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP GET `/v1/notebooks/{notebook_id}/sessions/{session_id}` | session/turns | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP POST `/v1/notebooks/{notebook_id}/sessions/{session_id}/turns` | session/turns | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP DELETE `/v1/notebooks/{notebook_id}/sessions/{session_id}` | session/turns | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP GET `/v1/notebooks/{notebook_id}/notes` | notes | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP POST `/v1/notebooks/{notebook_id}/notes` | notes | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP GET `/v1/notebooks/{notebook_id}/notes/{note_id}` | notes | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP PATCH `/v1/notebooks/{notebook_id}/notes/{note_id}` | notes | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP DELETE `/v1/notebooks/{notebook_id}/notes/{note_id}` | notes | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP GET `/v1/notebooks/{notebook_id}/insights` | insights | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP POST `/v1/notebooks/{notebook_id}/insights/generate` | insights | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP POST `/v1/notebooks/{notebook_id}/final-qa` | QA/evidence | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP POST `/v2/notebooks/{notebook_id}/final-qa` | QA/evidence | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP GET `/v2/capabilities` | provider capabilities | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP POST `/v1/query` | retrieval/evidence | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP POST `/v1/search` | retrieval/evidence | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP GET `/v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}` | document/version evidence | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP POST `/v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/expand` | document/version evidence | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP GET `/v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/original` | document/version evidence | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP GET `/v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/chunks/{chunk_id}` | document/version evidence | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP GET `/v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/assets` | document/version evidence | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP GET `/v2/notebooks/{notebook_id}/asset-occurrences/{occurrence_id}/content` | asset bytes/analysis | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP GET `/v2/notebooks/{notebook_id}/asset-occurrences/{occurrence_id}/analysis` | asset bytes/analysis | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP GET `/v2/notebooks/{notebook_id}/final-qa/{assistant_turn_id}/evidence` | QA/evidence | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP POST `/v2/retrieval/automatic` | retrieval/evidence | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP POST `/v2/retrieval/evidence` | retrieval/evidence | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| HTTP POST `/v2/retrieval/structured` | dataset/rows | — (blocked) | 503 before handler | Not reached | None issued | No stream/cache use | C; H1 representative denial |
| MCP `get_asset` | exact evidence/bytes | — (blocked) | unavailable before handler | Not reached | None issued | No stream/cache use | M1 representative denial; others C |
| MCP `get_capabilities` | provider capability | — (blocked) | unavailable before handler | Not reached | None issued | No stream/cache use | M1 representative denial; others C |
| MCP `get_document` | exact evidence/bytes | — (blocked) | unavailable before handler | Not reached | None issued | No stream/cache use | M1 representative denial; others C |
| MCP `get_document_chunk` | exact evidence/bytes | — (blocked) | unavailable before handler | Not reached | None issued | No stream/cache use | M1 representative denial; others C |
| MCP `get_image_analysis` | notebook inventory | — (blocked) | unavailable before handler | Not reached | None issued | No stream/cache use | M1 representative denial; others C |
| MCP `get_notebook_summary` | summary/source refs | T | ACL notebook | No exact document filter | R2, not atomic transport | No cursor | M1 direct execution |
| MCP `get_source_insights` | insights | — (blocked) | unavailable before handler | Not reached | None issued | No stream/cache use | M1 representative denial; others C |
| MCP `get_timeline` | events | — (blocked) | unavailable before handler | Not reached | None issued | No stream/cache use | M1 representative denial; others C |
| MCP `list_notebooks` | notebook inventory | T | ACL notebook | No exact document filter | R2, not atomic transport | Raw keyset; reauth each page | M1 direct execution |
| MCP `query_notebook` | retrieval/evidence | — (blocked) | unavailable before handler | Not reached | None issued | No stream/cache use | M1 representative denial; others C |
| MCP `query_notebook_v2` | retrieval/evidence | — (blocked) | unavailable before handler | Not reached | None issued | No stream/cache use | M1 representative denial; others C |
| MCP `query_structured` | retrieval/evidence | — (blocked) | unavailable before handler | Not reached | None issued | No stream/cache use | M1 representative denial; others C |
| MCP `run_final_qa_v2` | QA/evidence | — (blocked) | unavailable before handler | Not reached | None issued | No stream/cache use | M1 representative denial; others C |
| MCP `search_all_notebooks` | retrieval/evidence | — (blocked) | unavailable before handler | Not reached | None issued | No stream/cache use | M1 representative denial; others C |
| MCP `search_evidence` | retrieval/evidence | — (blocked) | unavailable before handler | Not reached | None issued | No stream/cache use | M1 representative denial; others C |
| WS `/ws/query` | streamed retrieval | — (blocked) | 503 handshake denial | Not reached | None issued | No session opened | H2 representative; alias C |
| WS `/v1/ws/query` | streamed retrieval | — (blocked) | 503 handshake denial | Not reached | None issued | No session opened | H2 representative; alias C |

The indexed V2 evidence, exact-delivery and capability operations above remain U: no cursor is issued under an attached ACL, so there is no working end-to-end revision-bound continuation to certify. The V1 notebook-list keyset cursor is an unsigned UUID but each page re-resolves current memberships; it cannot widen access, yet it does not invalidate on every ACL revision. Notebook response checks narrow the pre-return revocation window; they cannot guarantee instantaneous cancellation of bytes already being sent. System job/config routes were added to the U guard because job detail and provider configuration can disclose authorization-sensitive state.

The added in-flight HTTP and direct-MCP summary fixtures revoke a disposable
reader grant while `list_insights` is running. Both handlers reject before
returning the assembled summary. Additional route-level assertions reject
system jobs/configuration, V2 capabilities, exact-version delivery, and V2
evidence search under an attached ACL. These tests demonstrate a pre-return
barrier, **not** an atomic response-publication transaction or a running
WebSocket/session cancellation guarantee. HTTP lifespan and external MCP
transport trust are not established by the direct test-client calls.

The lifecycle fixtures also exercise interrupted create after notebook-store
insertion, concurrent exact-token recovery retries, tombstone-first deletion
with a temporarily unavailable notebook store, and stable revision on retry.
This is single-process disposable evidence; cross-store atomicity,
multi-process serialization, and exhaustive power-loss recovery are not
established. Unknown legacy ownership remains quarantined; no production ACL
state was migrated.

### Verification of this continuation

The focused contract/ACL/HTTP/lifecycle/streaming run passed 90 tests with
two warnings. The separate HTTP route test passed after adding explicit
capability, exact-version and V2 evidence denial assertions. The full run
used the project interpreter with strict pytest settings and branch coverage:

```powershell
$env:COVERAGE_FILE='scratch/.coverage-module892-continuation'
.venv\Scripts\python.exe -m pytest -q --junitxml=scratch/module892-continuation-junit.xml -o "addopts=--strict-config --strict-markers --cov=mnemo --cov=mnemo_server --cov=email_ingestion --cov-config=pyproject.toml --cov-branch --cov-report=term-missing --cov-report=xml:scratch/module892-continuation-coverage.xml --cov-fail-under=90"
```

It exited 0: **3,200 passed, 6 skipped, 9 warnings; 90.17% combined
coverage**, above the 90% gate. The warnings were deprecation, intentionally
malformed XLSX dependency, local Qdrant index, and pytest-cache access
warnings, not test failures. JUnit and coverage XML are under `scratch/` at
the paths in the command. Ruff lint passed; Ruff format passed (602 files);
strict mypy passed on 322 source/test files; compileall and `git diff --check`
passed. These results do not establish the unimplemented end-to-end cursor
binding or live indexed delivery.

## Disposable indexed-serving continuation (2026-10-22)

This addendum supersedes the earlier route-inventory statements above **only**
for the routes named here. The public operation names and production selector
did not change. The versioned public-surface snapshot was refreshed only for
the removed blanket ACL dependency on the now-integrated HTTP routes; it does
not attest to deployed-client behavior. An attached ACL now permits HTTP
`POST /v2/retrieval/evidence` and direct MCP `search_evidence`. The existing
HTTP V2 exact document/version/chunk/asset handlers now enter their ACL checks
instead of the blanket guard; only document/chunk positive paths have current
route-level fixture evidence. The other guarded routes remain unavailable under
an attached ACL; an unavailable route is not evidence of authorized serving.

| Path | Identity and authorization | Exact scope / continuation | Evidence and limit |
| --- | --- | --- | --- |
| HTTP V2 evidence | Signed server-validated JWT mapped to stable actor; ACL notebook membership before retrieval | SQLite source and document/version association; principal-aware retrieval; signed plan fingerprint binds ACL revision; post-result ancestry and revision check | `test_module_892_retrieval_routes.py` uses a disposable SQLite store and actual ASGI path; partitioned and all alternate representation/provider cases are not certified |
| Direct MCP `search_evidence` | Explicit server principal; dispatcher and shared application service check ACL | Same retrieval service and revision-bound signed cursor | Allowed, denied and stale-cursor direct-tool assertions; disconnected SSE/stdio consumer integration is unverified |
| HTTP V2 exact delivery | Same trusted HTTP identity; ACL notebook check before document/version or occurrence lookup | Canonical association for requested and returned items; signed delivery cursor binds actor/notebook/revision; post-assembly revision check; binary stream rechecks immediately before its single chunk | ASGI exact chunk and two-page document tests; asset and FinalQA route variants need additional positive ACL fixtures |
| MCP exact delivery, capabilities, structured/V1 retrieval, WebSocket and alternate HTTP routes | Guarded/disabled when an ACL is attached | No ACL cursor issued | No positive authorized-serving claim; remains an 8.9.2b/2c gap |

Revocation is detected at the request start and again after assembling the
result. A disposable test revokes membership during SQLite evidence enumeration
and observes denial rather than a returned response. For binary HTTP delivery,
the generator checks again before yielding its one bounded chunk. These checks
cannot retract bytes already handed to ASGI or guarantee an atomic boundary
between the final check and transport delivery. Existing WebSocket routes remain
disabled under an attached ACL; live-session revocation is not demonstrated.

The two-store notebook/ACL lifecycle remains a tombstone-first, retryable
protocol, not a cross-store transaction. The earlier single-process crash and
concurrency fixtures do not prove multi-process serialization or power-loss
recovery. Legacy-unassigned notebooks remain quarantined. No production ACL
migration, indexed deployment, credential activation or tunnel startup occurred.

**Exit assessment:** 8.9.2a PARTIAL (multi-process/recovery assurance remains
open); 8.9.2b PARTIAL (some positive HTTP/MCP paths now work, but guarded
alternate serving paths remain); 8.9.2c PARTIAL (real evidence and exact
delivery cursors are revision-bound, but not every applicable continuation or
capability path is integrated). Module 8.9.2 is **NOT COMPLETE**. The tests
above are internal disposable evidence, not external-client acceptance or
production certification.

### 2026-10-22 gap-driven continuation (supersedes guarded-route rows above)

The route-by-route inventory above still enumerates the registered HTTP, MCP,
and WebSocket surface, but its guarded-route cells are a 2026-10-21 snapshot.
The following delta is the current implementation state; routes not listed
here retain the guarded or limited status shown in that inventory. A guarded
route is a safe rejection, **not** positive authorized-serving evidence.

| Registered entry point | Identity and pre-disclosure scope | Exact resource / revision / delivery | Positive and negative evidence; remaining limit |
|---|---|---|---|
| HTTP `POST /v2/retrieval/evidence`; MCP `search_evidence` | Signed server-validated HTTP JWT or supplied trusted MCP transport principal; explicit notebook ACL resolution | Source/document/version association; signed actor/notebook/ACL-revision cursor; reauthorize at continuation and after assembly | Disposable ASGI and direct-tool two-page, foreign-source, revoked and stale-cursor tests; deployed transport unverified |
| HTTP V2 document, expand, chunk and original; MCP `get_document`, `get_document_chunk` | Same principal-first notebook authority | Exact document/version association before and after service; signed delivery cursor; binary generator checks before its bounded yield | Real SQLite ASGI chunk/two-page document and direct MCP chunk/document allow/deny/stale-cursor tests; original-byte and expand variants lack positive ACL fixtures |
| HTTP V2 document-assets, occurrence content and analysis; MCP `get_asset`, `get_image_analysis` | Same ACL, explicit notebook; occurrence resolved within notebook | Returned attribution rechecked against exact source/document/version and current ACL revision; asset byte cursor bound to actor/notebook/revision; binary yield rechecks | Disposable real-SQLite asset catalog plus bounded-byte ASGI pagination and direct MCP asset allow/deny; stale asset cursor rejected. Analysis and inventory variants still lack positive ACL fixture coverage |
| HTTP V2 FinalQA evidence delivery | Same notebook authority | Returned evidence ancestry and revision rechecked; signed delivery cursor | Implementation is integrated, but no positive ACL execution-store fixture or in-flight revocation test; the separate HTTP `POST /v1` and `/v2` FinalQA operations remain guarded |
| HTTP `GET /v2/capabilities`; MCP `get_capabilities` | Scoped request only; trusted principal and ACL notebook resolution before provider discovery | Capability document uses authorized notebook; authoritative revision rechecked before return; unscoped ACL requests rejected | Real Phase85Runtime ASGI and direct MCP scoped allow/deny, foreign/nonexistent parity, and revoke-during-assembly test; provider readiness is not production certification |
| V1 query/search, V2 automatic/structured, MCP V1/V2 query and structured tools, `run_final_qa_v2`, insight/session/source/note routes, system routes, SSE and both WebSocket aliases | Attached-ACL guard rejects before handler | No protected data or ACL cursor delivered | Guard/registration tests only; positive authorized serving and active-session revocation remain unsatisfied |

The MCP exact-delivery handlers now independently authorize at their direct
tool boundary; they do not rely on the dispatch allowlist alone. Capability
discovery likewise rejects unscoped ACL requests and rechecks the revision
after assembly. The public-surface snapshot changed only by removing the
HTTP capability route's blanket dependency; no new public name or route was
registered. The older table's 503 expectations for newly integrated routes
must be read as historical, not as present behavior.

Disposable spawned-process tests demonstrate SQLite ACL revision
serialization under concurrent grants and revokes, crash after notebook-store
insert followed by simultaneous create recovery, and crash after ACL
tombstoning followed by simultaneous delete retries. They do not establish
cross-store atomicity, durable power-loss behavior on every platform, or a
general automatically convergent reconciler. Tombstone-first deletion denies
access during the partial-failure window. In-flight response checks narrow
revocation exposure; bytes already accepted by ASGI/MCP cannot be recalled.

**Exit assessment remains PARTIAL:** 8.9.2a lacks exhaustive crash-boundary
and operational recovery evidence; 8.9.2b lacks positive authorization for
V1/structured/FinalQA operations, other delivery variants and streaming;
8.9.2c lacks end-to-end revision binding for those guarded paths and
active-session revocation tests. Production remains `UNINDEXED`. No production
membership migration or indexed activation follows from this work.

### 2026-10-22 verification result

The focused changed-route command
`.venv\Scripts\python.exe -m pytest -q -o addopts='' mnemo-server/tests/test_module_892_retrieval_routes.py mnemo-server/tests/test_module_892_http_routes.py mnemo-server/tests/test_module_892_trusted_actor.py`
passed **10 tests** (one pytest-cache access warning). The current-surface
snapshot comparison passed independently after refreshing only the reviewed
HTTP dependency entries. The first full run started before that refresh and
therefore failed exactly that snapshot comparison: 3,201 passed, 1 failed,
6 skipped, 90.06% coverage; it is not a green run. The fresh final command was:

```powershell
.venv\Scripts\python.exe -m pytest -q --junitxml=scratch/module892-final-20261022.xml --cov-report=xml:scratch/module892-final-coverage-20261022.xml
```

It exited 0: **3,202 passed, 6 skipped, 0 failed, 9 warnings; 90.09%
combined statement/branch coverage**, meeting the configured 90% threshold.
The warnings concern Starlette/FastAPI deprecations, malformed-XLSX fixture
data, local Qdrant payload indexes, and pytest-cache write access. Ruff lint
and format (603 files), strict mypy (319 source files plus the two changed
route-test files), compileall for the three source packages, and
`git diff --check` all exited 0. The reviewed public-surface snapshot matches
the reviewed generated candidate byte-for-byte.

Post-run read-only checks: five retired DB hashes and five recovery-snapshot
hashes match the 2026-10-10 receipts; both original-byte source manifests
verify 44/44 and 24/24. Production selection remains `UNINDEXED`, the runtime
DB is absent, the credential registry has no active generation and records the
historical generation as `REVOKED`, and a local process scan found zero
`certified-tunnel-stdio` processes. `.venv` remains available;
`scratch/.venv-gpu-preflight` remains absent. Nothing is staged. The working
tree remains dirty with pre-existing work preserved; the previously discussed
top-level `goldenDataset/` deletions are not pending in the current Git status.
These observations do not certify production indexed serving or an external
transport.

### 2026-10-22 final gap-pass verification and remaining gate

The final disposable fixture checks cover scoped HTTP and direct MCP
capability discovery, MCP document/chunk/asset delivery, real SQLite asset
byte pagination, stale HTTP/MCP asset cursors, concurrent separate-process
grant/revoke revisions, and separate-process create/delete crash recovery.
The affected route/delivery/lifecycle focused command passed **54 tests**
before the final delete-crash fixture and asset assertions; the subsequently
run separate-process command passed **3 tests**, and the exact asset route
test passed **1 test**. These overlap and are not additive counts.

The first full configured run (`.venv\Scripts\python.exe -m pytest -q
--junitxml=scratch/phase892_gap_final_20261022.xml`) failed two ordered-text
stdio transport cases: 3,203 passed, 2 failed, 6 skipped, 90.08% coverage.
Both failed at approximately the 15-second client read deadline with MCP
`BrokenResourceError` during teardown. They passed independently and after
the immediately preceding workspace-boundary tests. A complete rerun then
passed 3,206 tests, 6 skipped, 90.08% coverage. The exact-final code and
test snapshot was verified by:

```powershell
.venv\Scripts\python.exe -m pytest -q --junitxml=scratch/phase892_gap_exact_final_20261022.xml --cov-report=xml:scratch/phase892_gap_exact_final_coverage_20261022.xml --cov-report=term:skip-covered
```

This exited **0**, with **3,206 passed, 6 skipped, 0 failed, 9 warnings**,
and **90.08% combined statement/branch coverage** against the unchanged 90%
gate. All four ordered-text stdio/SSE cases passed, but their elapsed times
remained variable (the stdio cases took 22.6 and 36.8 seconds in total). The
earlier failure is retained as an intermittent-transport risk; no timeout,
assertion, skip, or coverage setting was changed to conceal it. The warnings
concern existing Starlette/FastAPI deprecations, malformed-XLSX fixtures,
local Qdrant payload indexes, and pytest-cache write access.

Repository-wide Ruff lint and format checks exited 0 (603 Python files
formatted); strict mypy exited 0 on the established 319 source files plus
four focused Module 8.9.2 test files (323 files total); compileall and
`git diff --check` exited 0. An exploratory expansion of strict mypy to the
legacy `test_mcp_delivery.py` file reports 23 errors in that file, including
untyped pre-existing helpers and optional MCP resource metadata. This is not
part of the established source typing gate and was not suppressed.
The generated public-surface candidate and reviewed snapshot are byte-equal;
the snapshot contract test passed. It records only removal of the capability
route's blanket guard, not registration of a new operation.

Post-run read-only checks matched the `after_sha256` receipt for all five
retired database files and the recorded SHA-256 for all five recovery
snapshots. Source verification passed 44/44 and 24/24 original bytes, and
both manifest-file hashes match the execution receipt. The production
selector is `UNINDEXED`, the historical generation is `REVOKED` with no
active credential, no matching local tunnel process was found, and
`data/notebook_runtime/mnemo.db` is absent. `.venv` exists and the retired
GPU preflight environment remains absent. Nothing is staged. These checks
did not open the retired databases or mutate production membership state.

**Module 8.9.2 remains PARTIAL.** The remaining acceptance work is not a
test-count problem: V1 query/search, structured retrieval, FinalQA execution,
source/session/note/insight paths, and SSE/WebSocket serving still require
principal-first authorized integration or an approved narrower scope. FinalQA
evidence delivery and image analysis need positive ACL fixture and in-flight
revocation evidence. The current bounded binary generator checks before its
yield, but active multi-message stream termination after revocation is not
demonstrated. The two-store tests do not prove every crash boundary,
power-loss durability, or cross-store atomicity. This dossier does not
authorize any production migration, indexed activation, or later module.

### 2026-10-23 V1 ACL continuation and current verification

The prior assistant's uncommitted `/v1/query` and `/v1/search` route edits
resolved an ACL scope and passed a principal into the service, but also fell
back to the unscoped service when the authority was absent. The path-based
exemption in `require_integrated_membership_route` effectively bypassed the
router dependency. This continuation replaced that exemption with explicit
router registration and a fail-closed JWT-membership dependency check. The
legacy no-ACL V1 fixture remains supported; the real production `UNINDEXED`
guard remains separate and mandatory. Services now resolve membership before
notebook storage or retrieval, reject an empty ACL scope, and recheck every
returned document/version association and the ACL revision before return.
The direct MCP `query_notebook` and `search_all_notebooks` handlers now take
the same verified principal when an ACL is attached. Their names, request
defaults, and output contracts remain unchanged. The reviewed public-surface
snapshot changed only by removing the generic dependency from the two HTTP
routes; a generated candidate was compared byte-for-byte.

| Surface | ACL-enabled positive evidence | Denial/revalidation evidence | Remaining limit |
|---|---|---|---|
| HTTP `/v1/query`, `/v1/search` | Disposable owner and reader route tests invoke the real service with a scoped mock retriever | Cross-user/nonexistent denial before retrieval; revoke and source-scope loss before delivery deny | Mock retriever is not indexed-production certification; global V1 fan-out remains bounded/filtered, not exhaustive |
| MCP `query_notebook`, `search_all_notebooks` | Direct tool tests for owner and reader through registered dispatch | Cross-user and revoked grants rejected | Deployed ChatGPT transport unavailable |
| HTTP V2 evidence, exact delivery, assets, capabilities; MCP equivalents | Earlier disposable SQLite fixtures in this dossier | Earlier ACL-revision cursor and non-disclosure tests | No external deployment claim |
| Structured, FinalQA, source/session/note/insight, SSE/WebSocket and other guarded routes | None for ACL-enabled positive serving in this continuation | Generic ACL guard retains fail-closed behavior | Required integration and stream-revocation evidence still missing |

The focused V1/MCP/contract command with coverage addopts disabled for
diagnosis passed **101 tests**; the two disposable indexed contract-matrix
cases passed independently, and the public-surface snapshot test passed.
The first configured full run produced `scratch/phase892_v1_acl_20261022.xml`
and its coverage XML: **3,203 passed, 5 failed, 6 skipped, 90.08%** (exit 1).
Two failures were caused by an over-broad production-mode fallback check and
one by the expected snapshot delta; both were corrected and their focused
tests passed. The other two were ordered-text stdio initialization failures.
The corrected configured full run produced
`scratch/phase892_v1_acl_final_20261022.xml` and its coverage XML:
**3,207 passed, 1 failed, 6 skipped, 90.08%** (exit 1). The sole failure was
`test_persisted_mixed_document_real_transports[asyncio-stdio-older]`.
The 90% coverage minimum was met, but the full test gate did **not** pass.

An isolated coverage diagnostic reproduced the other stdio variant failing
at `client.initialize()` with the MCP client's 15-second read deadline. The
MCP library's teardown `BrokenResourceError` obscures that nested timeout in
the ordinary failure summary. Temporary child timing (removed after the
diagnostic) measured roughly 9.8 seconds importing the large shared test
fixture and 10.4-13.4 seconds to readiness under instrumentation. This is a
test-harness startup bottleneck, not evidence that the V1 ACL route change
caused the failure. No timeout, assertion, skip, or coverage setting was
weakened. A targeted fixture-startup improvement and a passing configured
full run are still required for the verification gate.

Repository-wide Ruff lint and format checks passed (610 Python files),
strict mypy passed on 321 source/focused-test files, compileall passed for
the three source packages, the reviewed snapshot matched its generated
candidate, and `git diff --check` passed. The broader legacy
`test_mcp_delivery.py` strict-mypy debt previously recorded here was not
silently treated as part of that gate or repaired in this continuation.

Post-run read-only checks: five retired database hashes and five recovery
snapshot hashes match their exact receipts; `verify_source_manifest` passed
44/44 and 24/24 original bytes. The selector remains `UNINDEXED`, the
credential registry records no active generation and the historical
generation `REVOKED`, and a local process scan excluding the inspection
shell found zero matching tunnel processes. The runtime database is absent,
`.venv` exists, and the retired GPU preflight environment remains absent.
No protected store, credential, source corpus or production membership state
was changed. This is point-in-time local evidence only.

**Exit assessment remains PARTIAL:** 8.9.2a still lacks exhaustive
cross-store crash/restart assurance; 8.9.2b still has guarded structured,
FinalQA, adjacent notebook data and streaming paths; 8.9.2c lacks active
multi-message stream revocation proof and exhaustive continuation coverage.
The configured full suite is red due to the stdio initialization timeout.
Module 8.9.2 is **NOT COMPLETE** and Module 8.9.3 remains unstarted.

#### 2026-10-23 verification follow-up: stdio fixture startup

The stdio deadline failure was reproduced under coverage instrumentation at
MCP `client.initialize()`. Import profiling identified eager application import
through the package export and the shared transport test fixture as substantial
startup costs. The package now lazily exports `create_app`, and the fixture
imports the HTTP app only for its HTTP case. The public package export identity
and `UNINDEXED` admission tests passed (2/2); both ordered-text stdio variants
passed a focused coverage-instrumented diagnostic without changing their
15-second deadline (2/2). The prior failing runs above remain historical
evidence, not the final gate result.

The subsequent configured full-suite command was
`.venv\Scripts\python.exe -m pytest -q --junitxml=scratch/phase892_v1_acl_lazy_final_20261023.xml --cov-report=xml:scratch/phase892_v1_acl_lazy_final_coverage_20261023.xml`.
Its completed JUnit records **3,209 passed, 0 failed, 6 skipped**; the coverage
XML records 36,950/39,847 statements and 10,647/12,988 branches, or **90.086%**
combined, above the configured 90% minimum. The command runner's terminal exit
code was not retained across the session boundary, so the JUnit and coverage
artifacts—not a claimed observed exit code—are the evidence here. Repository-wide
Ruff lint and format passed, strict mypy passed on 321 source/focused-test files,
compileall for the three source packages passed, and `git diff --check` passed.

This resolves the observed stdio test-harness instability in this run. It does
not resolve the guarded ACL serving surfaces or exhaustive lifecycle/stream
recovery criteria listed above. **8.9.2a, 8.9.2b, 8.9.2c and Module 8.9.2 remain
PARTIAL**; no indexed production activation or later-module work occurred.

### 2026-10-23 route completion matrix and further integration

The following is an ACL-attached **development-fixture** matrix. `PASS` means
the named property was exercised by a focused test or already cited test in
this dossier; a route guard alone is `NOT PROVEN` for positive serving. Columns:
`G` = guard, `S` = service/data-access enforcement, `O/R` = owner/reader
success, `D` = denial of unauthorized/nonexistent/revoked access, `C` = ACL
revision or continuation, `X` = alternate-path equivalence, `T` = executed
tests. `N/A` means the operation has no continuation, not a passing cursor
claim.

| Surface | G | S | O/R | D | C | X | T | Remaining limitation |
|---|---|---|---|---|---|---|---|---|
| V1 HTTP query/search; direct MCP equivalents | PASS | PASS | PASS | PASS | N/A | PASS | PASS | Mock retriever fixture, not indexed deployment certification |
| V2 evidence search and exact document/chunk delivery | PASS | PASS | PASS | PASS | PASS | PASS | PASS | Existing disposable tests; external transport unavailable |
| Asset content and image-analysis delivery | PASS | NOT PROVEN | NOT PROVEN | PASS | NOT PROVEN | NOT PROVEN | NOT PROVEN | Some earlier fixture tests exist, but end-to-end owner/reader and in-flight revocation are not exhaustive |
| V2 structured HTTP and direct MCP | PASS | PASS | PASS | PASS | PASS | PASS | PASS | New disposable route test; deployed provider readiness not certified |
| V1 SSE and both WebSocket aliases | PASS | PASS | PASS | PASS | N/A | PASS | PASS | Multi-message revocation stops later protected events; already-sent bytes cannot be recalled |
| Automatic V2 retrieval | PASS | NOT PROVEN | NOT PROVEN | PASS | NOT PROVEN | NOT PROVEN | NOT PROVEN | Still guarded under ACL |
| FinalQA V1/V2 execution | PASS | NOT PROVEN | NOT PROVEN | PASS | NOT PROVEN | NOT PROVEN | NOT PROVEN | Still guarded; execution persistence and ancestry need ACL integration |
| Source/session/note/insight HTTP and equivalent MCP storage tools | PASS | NOT PROVEN | NOT PROVEN | PASS | NOT PROVEN | NOT PROVEN | NOT PROVEN | Still guarded; mutations need role-specific policy |
| Notebook discovery and metadata/capabilities | PASS | PASS | PASS | PASS | NOT PROVEN | PASS | PASS | Raw notebook-inventory cursor and cache/revision equivalence require review |
| Two-store create/delete and ACL grant/revoke recovery | PASS | PASS | PASS | PASS | N/A | PASS | PASS | SQLite serializes ACL commits; no cross-store atomicity or power-loss proof |

The following inventory expands that matrix to every route in the reviewed
HTTP surface snapshot and every registered MCP tool. Paths on one row share
the same implementation/policy; a grouped row is **not** evidence that every
member has an individual positive ACL test. `Integrated` denotes positive
authorized serving plus denial evidence in disposable fixtures; `guarded`
means fail-closed under an attached ACL but no positive serving proof;
`mixed` requires the specific limitations in the matrix above. Aliases are
listed explicitly. WebSocket aliases are registered outside the HTTP snapshot.

| Registered entry points | ACL status | Remaining evidence |
|---|---|---|
| `POST /v1/query`, `POST /v1/search` | Integrated | V1 fixture-backed HTTP/direct MCP tests; no deployment certification |
| `POST /v1/query/stream`, `WS /ws/query`, `WS /v1/ws/query` | Integrated | Owner/reader, denial, and revocation between messages tested; bytes already sent cannot be recalled |
| `POST /v2/retrieval/structured` | Integrated | HTTP/direct MCP, ancestry, revision-bound signed cursor and denial tests |
| `POST /v2/retrieval/evidence` | Integrated | Existing disposable evidence continuation tests; full alternate-path audit remains |
| `POST /v2/retrieval/automatic` | Guarded | Positive ACL serving and continuation not established |
| `GET /v2/capabilities` | Mixed | Scope-tested fixture; authorization-sensitive cache/revision equivalence not exhaustive |
| `GET /v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}`, `POST /v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/expand`, `GET /v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/original`, `GET /v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/chunks/{chunk_id}` | Mixed | Document/chunk delivery fixtures; each alternate exact-delivery path needs separate revocation proof |
| `GET /v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/assets`, `GET /v2/notebooks/{notebook_id}/asset-occurrences/{occurrence_id}/content`, `GET /v2/notebooks/{notebook_id}/asset-occurrences/{occurrence_id}/analysis` | Mixed | Asset ancestry, authorized positive access and revocation not exhaustive |
| `GET /v2/notebooks/{notebook_id}/final-qa/{assistant_turn_id}/evidence` | Mixed | Exact evidence route covered in fixtures; execution ancestry remains blocked |
| `POST /v1/notebooks/{notebook_id}/final-qa`, `POST /v2/notebooks/{notebook_id}/final-qa` | Guarded | Principal-bearing execution, persistence and final disclosure not integrated |
| `POST /v1/notebooks`, `GET /v1/notebooks`, `GET/PATCH/DELETE /v1/notebooks/{notebook_id}` | Mixed | Lifecycle/discovery fixture coverage; operation-by-operation role policy not exhaustive |
| `GET /v1/notebooks/{notebook_id}/summary`, `GET /v1/notebooks/{notebook_id}/timeline`, `GET /v1/notebooks/{notebook_id}/graph` | Mixed | Summary/scope fixtures; timeline/graph authorization and revocation not exhaustive |
| `POST/GET /v1/notebooks/{notebook_id}/sources`, `GET/DELETE /v1/notebooks/{notebook_id}/sources/{source_id}`, `GET /v1/notebooks/{notebook_id}/sources/{source_id}/status` | Guarded | Reader/owner mutation policy and source ancestry not positively integrated |
| `GET/POST /v1/notebooks/{notebook_id}/sessions`, `GET/DELETE /v1/notebooks/{notebook_id}/sessions/{session_id}`, `POST /v1/notebooks/{notebook_id}/sessions/{session_id}/turns` | Guarded | Principal/scope and mutation policy not positively integrated |
| `GET/POST /v1/notebooks/{notebook_id}/notes`, `GET/PATCH/DELETE /v1/notebooks/{notebook_id}/notes/{note_id}` | Guarded | Principal/scope and mutation policy not positively integrated |
| `GET /v1/notebooks/{notebook_id}/insights`, `POST /v1/notebooks/{notebook_id}/insights/generate` | Guarded | Derived-output ancestry and disclosure not positively integrated |
| `GET /v1/health`, `GET /health`, `GET /v1/config`, `GET /config`, `GET /v1/config/models`, `GET /config/models`, `PATCH /v1/config`, `PATCH /config`, `GET /v1/jobs`, `GET /jobs`, `GET /v1/jobs/{job_id}`, `GET /jobs/{job_id}` | Guarded/mixed | System/config/job disclosure and operator policy need separate ACL-attached proof |
| MCP `query_notebook`, `search_all_notebooks`, `query_structured`, `search_evidence` | Integrated | Direct tool fixture tests; no disconnected external transport claim |
| MCP `get_document`, `get_document_chunk`, `get_asset`, `get_image_analysis` | Mixed | Shared delivery path exists; asset/image analysis and every alternate path need full positive/revocation matrix |
| MCP `list_notebooks`, `get_notebook_summary`, `get_capabilities` | Mixed | Authorized discovery/capability fixtures; raw inventory cursor and revision-sensitive disclosure not exhaustive |
| MCP `query_notebook_v2`, `run_final_qa_v2`, `get_timeline`, `get_source_insights` | Guarded | No positive ACL-attached serving proof |

The reviewed snapshot supplies registered names and paths, not an ACL proof.
No row marked guarded or mixed is counted as Module 8.9.2 completion.

For the new streaming integration, the service requires a trusted principal
when an ACL is attached, resolves scope before its first event, filters fused
document/version candidates before emitting identifiers, and revalidates the
authoritative revision and document membership before every protected chunk,
token, citation, and completion event. SSE uses the verified HTTP bearer;
WebSocket validates its signed bearer directly because HTTP middleware does
not run on WebSocket scopes. Missing identity is denied at the handshake.
The paused WebSocket test revokes a reader between tokens and verifies an
error rather than a second protected token, followed by denial on the same
session. This does not promise cancellation before an already-started
transport send or recall of delivered bytes.

Structured HTTP and direct MCP now use the same ACL-aware application service.
It validates scope and each discovered dataset ancestry before execution and
again before response, and includes the authoritative ACL revision in the
existing signed cursor's server-derived request fingerprint. A reader cursor
continues under the same revision; cross-principal replay and a grant-induced
revision change reject it. The former blanket guard was removed only for
this integrated route and for the streaming router. The reviewed public
surface snapshot records those two dependency removals without changing V1
defaults or registering new operations.

The configured full-suite baseline **before these further edits** exited 0:
`3,209 passed, 6 skipped, 90.09%` combined coverage, using
`.venv\Scripts\python.exe -m pytest -q --junitxml=scratch/phase892_baseline_20261023.xml --cov-report=xml:scratch/phase892_baseline_coverage_20261023.xml`.
The focused streaming suite initially found two direct-test signature
regressions, then passed after adapting those test callers; the ACL stream
tests passed 2/2. The structured/schema suites passed 36/36 before the ACL
test; the new ACL structured test passed. The first snapshot check caught a
mistargeted dependency edit in the reviewed JSON; it was corrected, and the
snapshot test and byte comparison with the generated candidate passed.
These intermediate failures are retained here for traceability. The final
post-edit full-suite result is recorded below.

#### Post-edit configured verification (2026-10-23)

The first complete post-edit run used the project interpreter and configured
coverage gate:
`.venv\Scripts\python.exe -m pytest -q --junitxml=scratch/phase892_stream_structured_final_20261023.xml --cov-report=xml:scratch/phase892_stream_structured_final_coverage_20261023.xml`.
Its **observed exit code was 1**: 3,211 passed, 1 failed, 6 skipped,
10 warnings, and 90.06% combined coverage (90% required). The sole failure
was `test_persisted_mixed_document_real_transports[asyncio-stdio-older]` at
MCP `client.initialize()`: no child response within the unchanged 15-second
deadline. The same case passed independently with `-o addopts=''` (exit 0,
1 passed in 6.16 seconds). This is evidence of a full-run startup/timing
failure, **not** proof of its root cause or a green acceptance gate. No
timeout, assertion, or coverage threshold was relaxed. A second configured
full run completed separately. The unchanged configured command with
`--junitxml=scratch/phase892_stream_structured_repeat_20261023.xml` and
`--cov-report=xml:scratch/phase892_stream_structured_repeat_coverage_20261023.xml`
had **observed exit 0: 3,212 passed, 6 skipped, 9 warnings, 90.06%**
combined coverage in 283.07 seconds. This demonstrates one passing complete
run, but not a proven cure for the intermittent stdio initialization failure.
The first run took 855.76 seconds and timed out at initialization; the repeat
and isolated pass do not establish why startup exceeded 15 seconds once.

Repository-wide Ruff lint and format checks, strict mypy on the established
322-file source/focused-test scope, compileall of the three source packages,
and `git diff --check` passed after these edits. An exploratory strict-mypy
run on the entire legacy `test_structured_v2.py` file failed with 39 test-file
typing errors; it is outside that established gate, and this result is not
represented as a passing broader test-file type check. The accepted public
surface snapshot test and generated-candidate byte comparison passed after
the initially mistargeted JSON edit was corrected. Module status remains
**PARTIAL** because the route and recovery gaps above are still unresolved.

Final focused command (normal pytest addopts deliberately disabled for this
diagnostic, not a substitute for the full coverage gate):
`.venv\Scripts\python.exe -m pytest -q -o addopts='' mnemo-server/tests/test_server_streaming.py mnemo-server/tests/test_structured_v2.py mnemo-server/tests/test_structured_schema_boundaries.py mnemo-server/tests/test_module_892_lifecycle.py mnemo-server/tests/test_module_892_http_routes.py mnemo-server/tests/test_module_892_retrieval_routes.py mnemo-server/tests/test_mcp_immutable_schema_matrix.py`
exited 0, **117 passed**, with Starlette test-client deprecation and Windows
`.pytest_cache` access warnings. The final static commands all exited 0:
`ruff check .`, `ruff format --check .` (604 files), strict mypy on the three
source packages plus three focused typed test files (322 source files),
`compileall -q` on the source packages, and `git diff --check`.

After the repeat run, read-only receipt checks found **5/5 retired database
SHA-256 hashes and 5/5 recovery snapshot hashes unchanged**. Both source
manifests verified original source bytes (**44/44 and 24/24**, exit 0).
`config/production/runtime-selection.json` is `UNINDEXED`; the non-secret
credential-registry view has no active generation and one `REVOKED` generation;
the local `certified-tunnel-stdio` process scan returned zero matches.
`.venv/Scripts/python.exe` exists, the retired GPU preflight environment and
`data/notebook_runtime/mnemo.db` are absent, and the Git index has no staged
files. This task did not stage, commit, push, migrate production membership,
or start Module 8.9.3. The current Git status shows no top-level tracked
`goldenDataset/` deletions; none were restored or modified by this work.

### 2026-10-26 autonomous implementation continuation (development only)

This addendum supersedes the earlier statement that automatic V2, MCP
timeline/source insight and FinalQA V2 are uniformly guarded. It does **not**
supersede the module's PARTIAL status or certify any production serving path.

| Area | Current implementation and direct evidence | Remaining limit |
|---|---|---|
| Owner grant/revoke | `scope_authority.py` now checks live ownership and mutates a reader grant in the same `BEGIN IMMEDIATE` ACL transaction. `membership_operator.py` uses these methods. Operator tests cover revoked-owner, reader, and rollback cases. | This is one-store ACL serialization, not cross-store atomicity or deployed grant-operator evidence. |
| Interrupted create | New additive intent payload retains the exact notebook record; `recover_pending_create` reconstructs it from the journal after process restart. Separate-process recovery and malformed/legacy-intent quarantine tests pass. | Concurrent *first opening* of an entirely new `SQLiteStore` can race during `schema_versions` initialization; recovery fixtures preinitialize the disposable notebook DB before spawning workers. Old intents without payload stay quarantined. |
| Automatic V2 | HTTP `/v2/retrieval/automatic` and MCP `query_notebook_v2` select an ACL-authorized notebook before provider discovery, use the principal-aware retrieval service and revalidate before return. A concrete disposable `KnowledgeEngine` test proves owner and reader success and stranger/revoked denial. | This does not establish deployed transport or multi-notebook automatic planning; the selected scope is the single authorized notebook. |
| MCP metadata | `get_timeline` and `get_source_insights` now check ACL scope and revalidate before return; real-engine tests prove owner success and stranger denial. | Other MCP data tools retain their existing individual policies/guards; no universal MCP certification follows from these two tools. |
| Source metadata reads | HTTP list/detail/status now resolve a trusted JWT principal before notebook or source reads, reject mismatched source ancestry, and revalidate the authoritative ACL revision before return. A real SQLite indexed-fixture route test proves owner/reader success, stranger denial and revocation between list retrieval and disclosure. | Source ingestion/deletion remain guarded under ACL, including direct service calls; their cross-store/index mutation contract is not yet complete. |
| FinalQA V2 | HTTP `/v2/notebooks/{id}/final-qa` and direct MCP `run_final_qa_v2` use trusted principal, ACL notebook/document/version checks, principal-aware retrieval and post-generation revision revalidation. Owner-only publication is deliberate because the operation persists execution state; reader and stranger are denied. Concrete-engine tests prove owner answer, MCP execution and denial, and revocation during generation preventing HTTP answer disclosure. | Revocation after generation may leave already-persisted operational state; already-transmitted bytes cannot be recalled. V1 FinalQA remains guarded under ACL. V2 session/turn ownership and all cache/alternate-delivery cases require further contract review. |
| Contract compatibility | The reviewed public-surface snapshot records only removal of generic guard dependencies from the automatic, FinalQA V2 and three source-read HTTP routes; V1 defaults and operation names are unchanged. Snapshot test passes. | A snapshot is registration evidence, not external-client acceptance. |

The first configured run after these changes had 3,221 passing tests and
6 skips, but failed the 90% coverage gate at 89.98%; an initial shell
pipeline printed the status of its last command rather than pytest's status.
This was **not** a passing gate. The added missing-ACL-store regression checks
meaningful fail-closed paths; coverage is re-evaluated by a second configured
run, not assumed from test count. Focused operator/lifecycle/authority/route/
snapshot tests passed 32/32; the concrete-engine group passed 3/3.
Repository-wide Ruff lint, strict mypy on 323 source and focused test files,
and compile/diff checks passed in this continuation. `ruff format --check .`
passed after correcting the test layout; all 605 checked files were formatted.

The module remains **PARTIAL**: V1 FinalQA and source mutations plus the guarded
session, note, insight and system HTTP families do not have positive
ACL-attached serving evidence; broader MCP alternate-path equivalence, universal cursor
and cache invalidation, and complete cross-store startup/recovery guarantees
are not established. Passing tests cannot close those acceptance gaps.

**Further 2026-10-27 scope note:** The V1 FinalQA HTTP route remains guarded,
and its in-process `FinalQAService.execute` now rejects attached-ACL calls
before storage access. This prevents a direct service bypass, but is not
positive authorized V1 FinalQA integration. Its core fusion/answer pipeline
does not receive an authenticated principal, so safely enabling it requires
an evidence-scope boundary inside the core execution path. Source read routes
are positively integrated as above; their write operations remain blocked.
The prior 3,223-test coverage gate predates these further changes and must
not be cited as post-change verification.

#### Configured gate and protected-state receipt (2026-10-26)

The final complete command used the main interpreter, branch coverage, and
the unchanged 90% threshold:
`.venv\Scripts\python.exe -m pytest -q --junitxml=scratch/phase892_autonomous_20261026_gate2_junit.xml -o 'addopts=--strict-config --strict-markers --cov=mnemo --cov=mnemo_server --cov=email_ingestion --cov-config=pyproject.toml --cov-branch --cov-report=term-missing --cov-report=xml:scratch/phase892_autonomous_20261026_gate2_coverage.xml --cov-fail-under=90'`.
Direct process exit **0**; **3,223 passed, 6 skipped, 9 warnings**, combined
coverage **90.05%**. The complete output is retained at
`scratch/phase892_autonomous_20261026_gate2_pytest.log`; the JUnit and
coverage XML are separate files. The warnings include the existing Starlette
deprecations and `.pytest_cache` write denial. A prior coverage-enabled run
had 3,221 passed and 6 skipped but failed its gate at 89.98%; its shell
pipeline's printed zero was not pytest's exit and is not cited as success.

Focused tests exited 0 (32 passed), including operator, lifecycle, ACL
authority, real-engine routes and snapshot compatibility. The real-engine
group separately exited 0 (3 passed). Repository-wide `ruff check .` and
`ruff format --check .` exited 0; strict mypy on the three source packages
and four focused test files reported 323 source files with no issues;
`compileall -q` on the three source packages and `git diff --check` exited 0.

After the test run, read-only SHA-256 comparison matched the five exact
retired databases and five recovery snapshots to their receipts; both
source manifests verified original bytes (44/44 and 24/24). The credential
registry hash matched its post-revocation receipt, with no active generation
and only `REVOKED` recorded. The selector is `UNINDEXED`, the local runtime
database remains absent, and a local process scan found zero matching tunnel
processes. The main `.venv` remains and the retired GPU environment is
absent. The Git index is empty; no tracked top-level `goldenDataset/`
deletions existed in this current checkout, and none were changed. These
point-in-time checks do not prove external transport or future startup.

#### Post-change verification (2026-10-27)

The main-interpreter command
`.venv\Scripts\python.exe -m pytest -q --junitxml=scratch/phase892_autonomous_20261027_junit.xml -o 'addopts=--strict-config --strict-markers --cov=mnemo --cov=mnemo_server --cov=email_ingestion --cov-config=pyproject.toml --cov-branch --cov-report=term-missing --cov-report=xml:scratch/phase892_autonomous_20261027_coverage.xml --cov-fail-under=90'`
exited **0**: **3,225 passed, 6 skipped, 9 warnings**, combined coverage
**90.05%** against 90%. The complete redirected output and explicit pytest
exit are retained in `scratch/phase892_autonomous_20261027_pytest.log`;
the XML coverage and JUnit reports are distinct artifacts. This run includes
the V1 FinalQA direct-service fail-closed test and real-engine HTTP source
read/revocation test added since the 2026-10-26 gate. The warnings are the
existing Starlette deprecations and Windows `.pytest_cache` write warning.

Post-change commands `ruff check .` (605 files), `ruff format --check .`
(605 files), `mypy --strict` on the three source packages and four focused
typed test files (323 files), `compileall -q` on the three source packages,
and `git diff --check` each exited **0**. Read-only post-run checks matched
**5/5 retired DB hashes and 5/5 recovery-snapshot hashes** to the
decommission receipts; source manifests verified **44/44 and 24/24** files.
The credential-registry hash matched its post-revocation receipt with no
active generation, the selector remained `UNINDEXED`, the production runtime
DB was absent, and the local tunnel process scan found zero matches. The
main `.venv` remained present, the retired GPU environment absent, and the
Git index had no staged files. These point-in-time checks do not certify
deployed transport or unknown external launchers.

**Exit assessment remains PARTIAL.** The source-read route now has positive
owner/reader data flow and a revocation-before-delivery denial, while source
mutation and V1 FinalQA remain fail-closed under attached ACLs. Guarded
session/note/insight/system routes, full alternate MCP and streaming
equivalence, and concurrent first-open/multi-store lifecycle guarantees
still lack the positive implementation and evidence required by the formal
8.9.2 criteria. A passing aggregate gate does not establish those properties.

#### Concurrent first-open recovery follow-up (2026-10-27)

A new separate-process test reproduced `sqlite3.OperationalError: database is
locked` at `SQLiteStore.open()` during simultaneous `PRAGMA journal_mode=WAL`
on a fresh disposable DB. First-open schema creation also previously placed
the version marker outside the schema script transaction. `SQLiteStore` now
sets its busy timeout before the WAL transition, retries only SQLite's
transient `SQLITE_BUSY` during that transition with a short bounded wait,
and executes schema creation plus the version marker within one explicit
exclusive SQLite transaction. A failed schema script rolls back completely.
The separate-process first-open test passed **10/10 repeated runs** after
the fix (it failed in 2/5 runs before the WAL coordination fix); the new
failure-injection rollback test passed. The SQLiteStore and 8.9.2 lifecycle
focused suites passed **54/54** before the rollback test was added. These
tests establish fresh-store initialization safety for the exercised Windows
processes, not cross-store atomicity, every crash boundary or deployed
multi-worker certification. The 3,225-test coverage gate above **predates**
this SQLite change and must be rerun before it can be cited as current.

The post-SQLite configured gate then exited **0** with **3,227 passed,
6 skipped, 9 warnings, 90.05% combined coverage**. Its command used the
same pytest options as the preceding gate with distinct
`scratch/phase892_autonomous_20261027_post_sqlite_{junit.xml,coverage.xml,pytest.log}`
artifacts; `PYTEST_EXIT=0` is retained in the log. This result predates the
session-read integration below.

#### Session-read integration (2026-10-27)

HTTP session list/detail now derive a trusted JWT principal, authorize the
notebook before reading, verify each returned session's notebook identity,
check cited document/version ancestry where citations exist, and revalidate
the ACL revision before disclosure. The service denies direct attached-ACL
calls without the principal. Disposable SQLite route tests prove owner and
reader success, cross-user and unassigned-legacy denial, foreign-citation
denial, and revocation between storage read and response. Session writes
remain guarded at HTTP and direct service boundaries under an attached ACL;
no owner-write behavior is claimed. The public-surface snapshot records only
the two GET dependency removals, leaving write guards and V1 defaults intact.
The focused session/legacy/contract group exited **0** with **15 passed**.
Repository-wide Ruff lint/format, established strict mypy (323 files), and
`git diff --check` exited 0 after this change. A new full coverage gate is
required for post-session verification. Module 8.9.2 remains **PARTIAL**.

The post-session configured gate then exited **0** with **3,228 passed,
6 skipped, 9 warnings, 90.04% combined coverage**. Its JUnit, coverage and
complete output are
`scratch/phase892_autonomous_20261027_post_sessions_{junit.xml,coverage.xml,pytest.log}`.
The recorded `PYTEST_EXIT=0` is the pytest process result, not a shell
pipeline's trailing command. This result predates the note/insight changes.

#### Note and insight read integration (2026-10-27)

HTTP note list/detail and insight list now resolve a trusted principal and
notebook ACL before storage disclosure and revalidate its authoritative
revision before return. Note detail verifies notebook ownership; insight
list verifies each insight's notebook and its source's notebook. A concrete
indexed SQLite fixture proves owner/reader insight results and rejection of
a persisted cross-notebook source association; disposable note-route tests
prove owner/reader results, cross-user and unassigned-legacy denial, and
in-flight revocation denial. Direct services without a trusted principal
fail closed under attached ACLs. Note writes and the formally deferred
insight-generation operation remain guarded at HTTP and direct-service
boundaries; no ACL-aware mutation or generation success is claimed. The
public-surface snapshot records only three GET dependency removals. The
affected note and insight groups exited **0** (16 and 13 tests respectively),
and repository-wide Ruff lint/format plus strict mypy on changed source/test
files exited 0. A post-change full coverage run is still required. Module
8.9.2 remains **PARTIAL** because mutation, V1 FinalQA, universal cursor and
streaming equivalence, and broader lifecycle gates remain unmet.

#### ACL-bound metadata continuation follow-up (2026-10-27)

The newly authorized HTTP source, session, note, and insight list routes now
use the existing signed `CursorCodecV2` through a shared metadata keyset
adapter when an ACL is attached. The cursor binds the server-validated actor,
notebook, authoritative ACL revision, list domain, effective page limit, and
the insight-type selector where applicable. Each continuation first resolves
the notebook ACL, then verifies the signed cursor before the storage read;
each response revalidates the ACL before issuing a next cursor. Legacy
non-ACL keyset behavior remains separate. The source OpenAPI cursor parameter
now admits an opaque string rather than UUID-only syntax; the registration
snapshot was regenerated after verifying that this was its sole difference.

Disposable HTTP tests demonstrate owner/reader pagination and denial of
cross-principal, changed-limit, selector-mismatched, tampered, and stale
post-revoke/regrant cursors across the affected list families. The focused
source/note/session/insight/legacy-contract group exited **0** with **126
passed**; strict mypy exited **0** on the three source packages plus five
focused test files (**324 files**). Repository-wide Ruff lint and format,
source compilation, and `git diff --check` exited **0**. Keyset pagination
still does not promise an immutable result-set snapshot across concurrent
data writes; the signed snapshot identity here is an ACL-revision binding,
not a frozen database view. Other cursor, cache, and streaming paths require
their own evidence. **Module 8.9.2 remains PARTIAL.**

HTTP `list_notebooks` and MCP `_handle_list_notebooks` were then updated to
use a distinct signed inventory cursor. Its context includes the trusted
actor and the full sorted authorized notebook/revision set, not a synthetic
single-notebook scope. The focused disposable HTTP/MCP test exited **0** and
demonstrates positive two-page traversal, cross-principal and changed-limit
denial, and stale cursor denial after owner revocation and re-grant. The
source snapshot changed only the HTTP notebook-list cursor parameter from
UUID syntax to opaque-string syntax; legacy no-ACL requests retain UUID
validation and its `http.validation` error envelope. The focused
HTTP/MCP/legacy/contract group exited **0** with **131 passed**. The fresh
post-inventory configured full gate then exited **0** with **3,230 passed,
6 skipped, 0 failed, 9 warnings, and 90.02% combined coverage** against
the unchanged 90% minimum. Its output, JUnit, and coverage XML are
`scratch/phase892_autonomous_20261027_post_inventory_{pytest.log,junit.xml,coverage.xml}`.
Repository-wide Ruff lint and format, strict mypy on 324 source/test files,
compilation and `git diff --check` exited **0**. This closes the tested
notebook-inventory cursor gap, not the other 8.9.2 acceptance gaps.

The post-cursor configured full suite exited **0**: **3,230 passed, 6
skipped, 0 failed, 9 warnings, 90.02% combined coverage** against the
unchanged 90% minimum. The complete output, JUnit, and coverage XML are
retained at
`scratch/phase892_autonomous_20261027_post_cursors_{pytest.log,junit.xml,coverage.xml}`.
This verifies the current aggregate regression gate, not the unresolved
per-path security and lifecycle acceptance criteria above.

#### Governed notebook-data mutations and deletion recovery (2026-10-27)

This continuation adds an ACL writer lease over the disposable SQLite ACL
store's `BEGIN IMMEDIATE` transaction. The lease verifies the live owner and
revision before and after a notebook-store write. It serializes that write
with ACL grant, revoke and retirement across processes; it **does not** make
the two stores atomic or recall a response already handed to a transport.

| Actual path under an attached ACL | Authorized behavior and evidence | Remaining limit |
|---|---|---|
| HTTP note POST/PATCH/DELETE and direct `NoteService` | Owner writes succeed under the ACL lease; reader, stranger, missing-principal and unassigned-legacy writes fail. A paused SQLite write held the lease until completion; concurrent revocation completed afterward and subsequent reads were denied. | No claim of instantaneous revocation after response serialization. |
| HTTP session POST/turn POST/DELETE and direct `SessionService` | Owner writes succeed, reader and stranger writes fail. Turn append and session update use one SQLite transaction; an injected turn-insert failure left the previous session/turn state intact. | Other storage backends remain unavailable for ACL-governed writes. |
| HTTP source-association DELETE and direct `SourceService` | Disposable mutable SQLite fixture proves owner deletion and reader/stranger/revoked/missing-principal denial, including absence of the persisted association after deletion. | Multi-artifact source ingestion remains guarded; its parse/asset/document/chunk/embedding writes are not covered by this single-store protocol. |
| HTTP notebook metadata PATCH | Owner read/modify/write is held under the same ACL lease. A concurrent owner revoke cannot commit until the update releases it; the next request is denied. | Bytes already serialized cannot be recalled. |
| HTTP notebook DELETE and `MembershipNotebookLifecycle` | First tombstone requires the trusted live owner *inside* the ACL write transaction, closing the route-check/retirement race. Actor-less retries are accepted only after a durable tombstone. A route test revokes ownership between the initial check and retirement: deletion returns the same safe 404 and leaves the notebook present. Existing separate-process crash/retry tests and the new owner-lease/revoke test pass. | Tombstone-before-store-delete is a fail-closed saga, not cross-store atomicity. Recovery requires the isolated, privileged lifecycle path; no production migration or operator run was performed. |

The complete focused authority/lifecycle/design-seam/HTTP group exited **0**
with **31 passed**. The source/notes/sessions/real-engine/contract focused
group exited **0** with **145 passed** before the final deletion-API change;
the final full run below includes both changes. The public-surface snapshot
was refreshed only for removal of the reviewed note, session and source-delete
HTTP guard dependencies; operation names, payloads and V1 defaults were not
changed. A previous intermediate configured run exited 0 with 3,232 passed,
6 skipped and 90.01% coverage; it predates the final actor-less retirement
restriction and must not be cited as its acceptance result.

The **final configured full gate** used `.venv\Scripts\python.exe -m pytest -q`
with `pytest.ini`'s strict markers/config, three package coverage targets,
branch measurement and the unchanged `--cov-fail-under=90`; only the JUnit
and coverage XML output paths were made unique. It exited **0** with **3,232
passed, 6 skipped, 0 failed, 9 warnings, 90.02% combined coverage**.
Artifacts: `scratch/phase892_autonomous_20261027_post_recovery_{pytest.log,junit.xml,coverage.xml}`;
the process exit was captured as `PYTEST_EXIT=0`. Repository-wide Ruff lint
and format exited 0; strict mypy on the three source packages plus six
focused test files exited 0 (**325 source files**); source compilation and
`git diff --check` exited 0. Warnings include the existing pytest cache
write-permission warning; no timeout or coverage setting was relaxed.

Post-run read-only checks matched **5/5** retired-store receipt hashes and
**5/5** recovery snapshot hashes, verified both source manifests (**44/44**
and **24/24**), and found production selection `UNINDEXED`, no local runtime
database, a registry hash matching the revoked/no-active-generation receipt,
no matching tunnel process at inspection time, the main `.venv` present and
the retired GPU preflight environment absent. No file under the top-level
`goldenDataset/` was changed in this continuation; current Git status has no
tracked deletion there, so historical deletion counts are not asserted as
current working-tree state. The worktree remains dirty with unrelated work;
nothing was staged or committed.

**Remaining acceptance gaps are not closed by this green aggregate run.**
HTTP V1 FinalQA is still guarded and `FinalQAService` rejects direct ACL
execution. Its core fusion can process candidates before principal/ancestry
filtering, and persisted V1 replay lacks an actor/ACL-revision binding;
route-only authorization would not secure replay or publication. Source
ingestion remains guarded under ACL because its multi-artifact protocol lacks
the governed write/recovery boundary proved for note/session/source-association
writes. Insight generation is explicitly deferred to Phase 10 and currently
returns 501 without an ACL; its attached-ACL route remains guarded, but no
implemented generation write path is claimed. The guarded
system/config/job family and any alternate route that discloses
authorization-sensitive state still need an explicit operation policy.
SSE/WebSocket tests prove revalidation before each protected event and stop
future messages after observed revocation, but do not prove recall of bytes
already accepted by transport; OCR/Vision provider caches are notebook-keyed
and require a trusted upstream authorization decision before reuse.
V1 persisted replay and any unreviewed alternate continuation/cache path
require separate positive and adversarial route evidence. **8.9.2a,
8.9.2b, 8.9.2c and Module 8.9.2 remain PARTIAL.** No Module 8.9.3 or
production activation follows from this result.

#### V1 FinalQA replay and source-ingestion boundary (2026-10-28)

This continuation enables **HTTP V1 FinalQA** under an attached disposable
SQLite ACL. The route resolves a server-validated principal before notebook
or session reads. The service requires the current owner because V1 FinalQA
persists an execution and may publish an assistant turn. Its authorized core
path filters fusion by exact notebook/document/version ancestry before
reranking or answer generation, checks that subsequent stages retain that
filtered ancestry, and rechecks authorization before publication and final
disclosure. A durable binding of assistant turn, principal, notebook,
session, user turn, ACL revision and exact document/version set rejects
pre-ACL persisted executions, cross-actor replay, changed revisions, and
replay after a source association disappears. Publication is serialized with
ACL changes by the existing owner write lease; it is not a cross-store
transaction and cannot recall bytes already sent.

The disposable ASGI test
`test_module_892_final_qa_v1.py::test_v1_final_qa_route_persisted_replay_is_acl_bound`
exercises the actual HTTP route, core orchestrator, SQLite execution store,
and citation engine with deterministic planner/retrieval/generation stages.
It covers owner generation and citation delivery, no-context publication,
restart/replay, unbound legacy replay denial, reader and stranger denial,
source-association loss, ACL revision change, and owner revocation during
generation. Core tests separately reject a reranker that restores filtered
evidence. There is no registered V1 FinalQA MCP operation to migrate.

Source **read and association-delete** paths retain their prior ACL evidence.
Multi-artifact source **ingestion** remains deliberately guarded under an
attached ACL. Its actual write sequence includes extracted/canonical assets
and parsed IR in filesystem storage, SQLite document and chunk records,
original-file retention, vector projection, then the notebook source
association. `CompositeStorage.upsert_source` compensates projection errors
only while its process remains alive; a crash after canonical SQL write and
before projection refresh is not atomic. Orphan assets can precede even the
first document status record. The new dedup check refuses to associate a
document whose status is `INDEXING` or `FAILED`, but an `INDEXED` status alone
does not prove that every original, vector membership, or source-association
write completed. An ACL-enabled positive ingestion path would therefore
need a durable per-ingestion intent/journal, idempotent artifact validation
and retry/reconciliation across these stores, a quarantine state for
ambiguous partial writes, and a governed owner lease that prevents revocation
between admission and source publication. None is claimed here; the guard
remains an **8.9.2a/8.9.2b acceptance blocker**. The disposable dedup
regression tests confirm the `INDEXING`/`FAILED` fail-closed behavior.

The other tested continuation families retain their earlier principal,
scope and ACL-revision checks. This pass did not establish exhaustive
positive authorized serving and revocation evidence for every alternate
cache, streaming, and replay path, nor production/external transport
certification. **8.9.2a, 8.9.2b, 8.9.2c and Module 8.9.2 remain PARTIAL.**

The current configured full-suite/branch-coverage gate exited **0** with
**3,244 passed, 6 skipped, 0 failed, 9 warnings, and 90.01% combined
coverage** against the unchanged 90% minimum. The complete output, JUnit
and coverage XML are
`scratch/phase892_20261028_finalqa_replay_integrity_{pytest.log,junit.xml,coverage.xml}`.
An earlier intermediate run failed the public-surface snapshot (updated to
reflect the V1 route integration); a second run passed all tests but measured
89.99%, which was not treated as coverage success even though pytest returned
zero. Additional malformed/missing persisted-binding tests closed that real
gap and the final run met the gate. Focused replay-integrity tests passed
6/6. Repository-wide Ruff lint/format, strict mypy on the three source
packages plus the two changed FinalQA/authority test files (**321 files**),
source compilation and `git diff --check` exited 0. The warnings include
pytest's local cache write-permission warning; no assertion, timeout or
coverage threshold was relaxed.

After the full run, read-only checks matched **5/5** retired database hashes
and **5/5** recovery-snapshot hashes to receipts and verified both source
inventories (**44/44**, **24/24**). Production remained `UNINDEXED`, no local
production runtime database existed, the credential-registry hash matched the
revoked/no-active-generation receipt, and a narrowed local process check
found no matching tunnel. The main `.venv` remained present and the retired
GPU preflight venv absent. These are local point-in-time observations, not
production migration, external-client, or indexed-serving certification.

#### Source-ingestion quarantine and metadata-disclosure follow-up (2026-10-29)

Development-only source ingestion now reserves a durable SQLite ACL intent
and advances the notebook revision *before* writing filesystem assets,
canonical/structured SQL rows or vector projections. While the intent is
`incomplete` or `failed`, notebook discovery, reads and continuations fail
closed. A short ACL writer lease publishes the source association only after
the composite source write returns; this is **not** a transaction across the
filesystem, SQLite and Qdrant. Failed projection or interrupted publication
leaves the notebook quarantined.

For an **observed failed** intent, an authenticated owner can invoke the
internal `IngestionService.reconcile_failed_source_ingestion` operation on an
isolated composite store. Under an ACL writer lock it removes any partial
notebook source association, reprojects vector membership from canonical
source rows, verifies the link is absent and only then marks the intent
`recoverable`, advancing the ACL revision. A repeated reconciliation is a
no-op; a reader, revoked owner, failed projection or missing reconciliation
proof cannot release quarantine. Orphaned, non-notebook-linked artifacts
remain for separate investigation. This does not make a `FAILED` canonical
document reingestable, nor does it prove exact cleanup of every filesystem,
SQL and vector artifact. A hard process death leaves an `incomplete` intent:
automatic recovery cannot distinguish an abandoned writer from a still
running writer, so it deliberately remains quarantined. Supervised
writer-quiescence and artifact reconciliation are still required.

The HTTP source-ingestion route remains guarded under an attached ACL, and
composite-store source DELETE remains guarded by its current write-store
contract. Direct-service positive ingestion and failure-injection tests are
development evidence, **not** positive authorized HTTP serving acceptance.
The source metadata resolver now reauthorizes each resolved document after
batch assembly, preventing its request-local presentation cache from being
returned after a detected grant change. Other alternate caches, streaming
adapters and continuation families still need per-path acceptance evidence.
Consequently **8.9.2a, 8.9.2b, 8.9.2c and Module 8.9.2 remain PARTIAL**.

The first complete follow-up run had **3,252 passed, 6 skipped**, but its
coverage was **89.98%** and failed the 90% requirement. A second run had
**3,255 passed, 6 skipped**, but unrounded combined coverage was below 90%
despite the display rounding to 90.00% and pytest returning 0; it was also
not accepted as a coverage pass. Focused tests then exercised the meaningful
reconciled-intent retry and old-token rejection branch. The final configured
run used `.venv\Scripts\python.exe -m pytest -q
--junitxml=scratch/phase892_ingestion_followup3_20261029_junit.xml -o
'addopts=--strict-config --strict-markers --cov=mnemo
--cov=mnemo_server --cov=email_ingestion --cov-config=pyproject.toml
--cov-branch --cov-report=term-missing
--cov-report=xml:scratch/phase892_ingestion_followup3_20261029_coverage.xml
--cov-fail-under=90'` and exited **0**: **3,256 passed, 6 skipped, 0
failures, 9 warnings**. The XML records 37,829/40,826 covered lines and
11,005/13,432 covered branches: **90.00332% combined**, above the unchanged
90% minimum. Its full output is
`scratch/phase892_ingestion_followup3_20261029_pytest.log`. The warnings
include the existing Windows pytest-cache write denial.

Repository-wide Ruff lint and format checks exited 0; strict mypy on the
three source packages plus `test_module_892_ingestion_recovery.py` and
`test_scope_authority.py` passed **321 files**. Compilation of the three
source packages and `git diff --check` exited 0. A separate exploratory
strict-mypy run including legacy `test_source_metadata.py` found 26 errors
in that legacy file; the new test lines were adjusted so they add no
reported errors, but the legacy file is **not** part of the established
strict test-file gate and is not claimed clean.

After this run, read-only checks matched **5/5** retired database hashes and
**5/5** recovery-snapshot hashes to their receipts. Both original-byte
source manifests verified **44/44** and **24/24** files. Production remained
`UNINDEXED`; the local runtime DB was absent. The credential-registry hash
still matched its revoked receipt, with no active generation and one
`REVOKED` generation. A local process scan found no matching tunnel;
the main `.venv` remained present and the retired GPU preflight environment
absent. No files were staged or committed and no top-level `goldenDataset/`
path changed in this continuation. These are point-in-time local checks,
not indexed-serving or external-client certification.

#### Governed source lifecycle and authorized-disclosure completion pass (2026-10-31)

This addendum supersedes only the *current-status* conclusions in the dated
follow-ups above; their test results remain historical. The development/test
implementation now records an ACL ingestion intent before multi-store writes,
plus whether the document existed before reservation and each exact asset
hash/media-type candidate before its write. `incomplete` and `failed` intents
quarantine notebook reads; an owner-held recovery lease and a SQLite-backed
process writer lock establish quiescence before reconciling a crashed writer.
Recovery removes only an unassociated document created by that attempt and
new, unreferenced, identity-consistent asset candidates. It clears a source
association and reprojects membership before releasing quarantine. A
`recoverable` intent permits a same-content retry; successful publication
transitions it to `published`. Ambiguous document, catalog, asset-byte or
source identity remains quarantined for owner-supervised reconciliation.
Target-qualified filesystem temp cleanup is limited to governed recovery,
not ordinary IR deletion. The ACL and canonical, filesystem and vector
stores are **not** one atomic transaction.

The HTTP source POST and composite source DELETE paths now invoke the same
trusted-owner, writer-lease and durable-intent protocol as the service. The
disposable tests in `test_module_892_ingestion_recovery.py` exercise actual
HTTP owner publication/reader denial, duplicate requests, deletion and stale
source cursors; hard process exits at parsed-file, asset, SQL, vector and
source-association boundaries; restart, idempotent recovery, exact orphan
cleanup, same-content retry, pre-existing/shared-resource preservation,
corrupt-artifact quarantine, and partial-delete disagreement. They do not
authorize production migration or prove coordination with out-of-band writers
that bypass this protocol.

| Notebook-scoped surface | ACL-positive and denial evidence in disposable fixtures | Continuation / disclosure boundary |
|---|---|---|
| Notebook lifecycle/discovery; grants | `test_module_892_http_routes.py`, `test_module_892_operator.py`, `test_module_892_lifecycle.py` | Trusted actor, owner-only mutation, tombstones and revision; legacy-unassigned records stay quarantined. |
| V1 HTTP/direct MCP query and search | `test_module_892_v1_acl_routes.py` | Service receives resolved principal/scope; post-retrieval revalidation. Frozen V1 defaults remain unchanged. |
| V2 automatic/structured/evidence retrieval | `test_module_892_real_engine.py`, `test_structured_v2.py`, `test_module_892_retrieval_routes.py` | Principal-first notebook/document ancestry and ACL-revision-bound evidence cursor. |
| Exact document/chunk/original/asset/image delivery; HTTP and MCP | `test_module_892_retrieval_routes.py`, `test_mcp_delivery.py` | Version/occurrence ancestry, bounded signed continuation and revalidation before HTTP binary emission; image-analysis route/tool tests include reader, stranger and revocation. |
| V1 persisted FinalQA replay and V2 FinalQA/evidence replay | `test_module_892_final_qa_v1.py`, `test_module_892_real_engine.py` | ACL binding before fusion/persistence and before replay/delivery; no cross-principal or revoked replay. |
| Sources, notes, sessions, insight reads, metadata and capabilities | `test_module_892_ingestion_recovery.py`, `test_module_892_http_routes.py`, `test_module_892_real_engine.py`, `test_source_metadata.py`, `test_capabilities_v2.py` | Resource-scoped reads and supported source/note/session writes, post-assembly revalidation and revision-bound list cursors. `insights/generate` remains an unimplemented later-phase operation, not a newly enabled serving path. |
| SSE and both WebSocket query aliases | `test_server_streaming.py` | Trusted session actor and per-message scope revalidation; revocation prevents subsequent protected messages. Already-delivered bytes cannot be recalled. |

The system-level health/configuration/job router remains guarded when an ACL
is attached: it has no notebook-scoped owner/reader policy and is not counted
as authorized notebook serving. Local HTTP clients and MCP protocol tests are
not deployed UI/ChatGPT-tunnel certification. This pass made no production
selector, source-corpus, credential, tunnel or indexed-serving change.

#### Module 8.9.2 internal exit verification (2026-11-04)

The completed, coverage-enabled command was `.venv\Scripts\python.exe -m
pytest -q --junitxml=scratch/phase892_completion9_20261104_junit.xml -o
'addopts=--strict-config --strict-markers --cov=mnemo --cov=mnemo_server
--cov=email_ingestion --cov-config=pyproject.toml --cov-branch
--cov-report=term-missing
--cov-report=xml:scratch/phase892_completion9_20261104_coverage.xml
--cov-fail-under=90'`. The shell exit marker in the full log is **0**;
**3,295 passed, 6 skipped, 0 failed**, 9 warnings. Coverage JSON reports
38,094/41,113 lines and 11,121/13,560 branches, **90.0170102244252%
combined**, above the unchanged 90% gate. The JUnit XML, coverage XML/JSON,
and full log are retained under `scratch/phase892_completion9_20261104_*`.
The 2026-10-31 run also reported 3,295 passed and 90.01518%, but its shell
exit marker was not retained; it is supporting evidence, not the final exit
proof. Earlier below-threshold runs remain recorded as failures.

| Formal criterion | Implementation and acceptance evidence | Internal status |
|---|---|---|
| 8.9.2a real actor-to-notebook authority, lifecycle, migration and revocation | Owner-approved disposable-state design; trusted JWT mapping, explicit owner/reader grants, legacy-unassigned quarantine, revision/tombstone and multi-process create/delete/grant/revoke tests in `test_module_892_operator.py`, `test_module_892_lifecycle.py` and `test_module_892_ingestion_recovery.py`. Crash recovery is idempotent under the governed process lock; ambiguous artifacts remain quarantined. No cross-store atomicity is claimed. | COMPLETE for development/test implementation |
| 8.9.2b principal-first authorized scope, non-disclosing denial and document/version membership | Positive owner/reader and negative cross-user/nonexistent/revoked route tests for V1 HTTP/MCP, V2 retrieval, source POST/DELETE, notebook, note, session, insight-read, FinalQA and exact delivery in the route files listed above. Source publication uses durable intent and owner write lease; an unavailable authority under the attached ACL cannot fall back to unscoped serving. | COMPLETE for internal route scope |
| 8.9.2c signed continuation and protected disclosure | Actual evidence/document/source cursors reauthenticate, reauthorize and check current ACL revision; stale/cross-principal continuations and revoked replay are rejected. `test_module_892_retrieval_routes.py`, `test_module_892_final_qa_v1.py`, `test_module_892_real_engine.py`, `test_source_metadata.py`, `test_capabilities_v2.py` and `test_server_streaming.py` cover HTTP/MCP, metadata/capability and SSE/WebSocket disclosure boundaries. Future protected messages stop after detected revocation; sent bytes cannot be recalled. | COMPLETE for internal route scope |

Repository-wide `ruff check .` and `ruff format --check .` exited 0 (607
Python files formatted). Strict mypy exited 0 on the three source packages
plus three changed focused test files (**322 files**). Source compilation,
the 66-test Module 8.9.1 public-contract snapshot group and `git diff
--check` exited 0. The 9 full-suite warnings include the existing local
pytest-cache write-permission warning; no test, deadline, coverage setting or
security assertion was relaxed.

Post-run read-only checks matched **5/5** retired database hashes and **5/5**
recovery-snapshot hashes to the exact receipts, and verified original bytes
for both source manifests (**44/44** and **24/24**). The production selector
was `UNINDEXED`, the local production runtime DB absent, the credential
registry hash unchanged with `REVOKED` and no active generation, and the
local matching tunnel-process count zero. `.venv` remained present,
`scratch/.venv-gpu-preflight` absent, no path was staged, and Git showed no
new `goldenDataset/` change. These are point-in-time local observations.

**Module 8.9.2 is COMPLETE for the approved internal development/test exit
criteria.** This does not approve a production membership migration, indexed
runtime activation, external ChatGPT tunnel/UI acceptance, or Module 8.9.3.
The guarded system health/config/job endpoints require a separate system
operator policy; `insights/generate` is explicitly deferred to Phase 10.
Neither guard is counted as positive notebook authorized-serving evidence.
Arbitrary writers that bypass the governed ingestion protocol remain outside
its coordination guarantee; uncertain state stays quarantined, not published.
