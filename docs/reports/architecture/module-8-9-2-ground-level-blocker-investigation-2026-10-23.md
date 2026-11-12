# Module 8.9.2 ground-level blocker investigation — 2026-10-23

## 1. Executive assessment and boundary

**Finding: PARTIAL, not certified indexed multi-user serving.** An explicit
SQLite owner/reader authority, trusted JWT mapping, notebook/document scope
resolution, and several ACL-attached disposable serving paths exist. There is
no production composition that installs this authority; production selection
is `UNINDEXED`. Thirty-two of the 54 snapshotted HTTP routes and four of 15
MCP tools are deliberately unavailable when an ACL is attached. Some of the
remaining routes have positive fixture evidence, but the result is not a
single proven authorization boundary across every data-producing service.

Two problems are deeper than missing route tests: grant-operator authorization
is checked *before*, not in, the ACL write transaction; and a pending-create
intent cannot by itself reconstruct the exact notebook payload and retry token
after a real process loss. Conversely, the signed evidence, structured and
delivery cursor paths already have meaningful revision tests; calling all
cursors unbound would be inaccurate. The full-suite stdio initialization
timeout is a separate intermittent verification issue, not evidence of an ACL
failure or a proven root cause.

This is an **investigation and remediation design**, not an implementation or
approval to migrate production. No source, test, existing document, database,
receipt, credential or environment was edited. The only new repository file is
this report. No stage/commit/push or Module 8.9.3 work occurred.

## 2. Live repository and evidence status

- Root `C:/Users/athar/Desktop/Mnemo`, branch `main`. Initial `git status
  --short` had 54 modified/untracked entries and no staged diff; the
  pre-existing changes include the roadmap, ADR-0080, source, tests and an
  untracked membership dossier. `git diff --stat` showed 34 tracked files,
  2,156 insertions and 155 deletions. No tracked top-level `goldenDataset/`
  deletion appeared in this live status; this investigation did not restore
  or touch such files. No `AGENTS.md` was found by repository file search.
- `config/production/runtime-selection.json` reads `state: UNINDEXED`.
  No production database, ACL, credential or tunnel was opened for mutation.
- The 8.9.1 [surface snapshot](../../governance/contracts/phase8_9_1_current_surface.v1.json)
  is present but untracked. It enumerates 54 HTTP routes and 15 MCP tools.
  `app.py:397-412` independently shows which routers carry the blanket
  membership guard; `routers/streaming.py:194-202` registers two WebSocket
  aliases not represented in that HTTP snapshot. Registration plus the
  snapshot is not proof of execution semantics.
- The 2026-10-23 [membership dossier](module-8-9-2-membership-authority-design.md)
  contains chronological addenda. Its opening “design proposed; state
  migration not approved” line is historical and conflicts if read as its
  *current* status; later addenda record owner-approved disposable migration
  and partial integration. Earlier guarded-route tables are superseded by
  later rows; neither should be read without dates.
- Saved full-run JUnit: `scratch/phase892_stream_structured_final_20261023.xml`
  records 3,211 passed, one stdio initialization failure, six skipped;
  `scratch/phase892_stream_structured_repeat_20261023.xml` records 3,212
  passed, zero failures, six skipped. The prior task captured exit 1 then
  exit 0 respectively. The latter coverage XML has 37,041/39,955 lines and
  10,684/13,038 branches covered: 47,725/52,993 = **90.06% combined**.
  `pytest.ini` and `pyproject.toml` require branch coverage and at least 90%.
  These artifacts were inspected, **not rerun as a full suite here**.
- This investigation independently ran only disposable-focused tests with
  `.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider -o addopts=''
  mnemo-server/tests/test_module_892_lifecycle.py
  mnemo-server/tests/test_structured_v2.py::test_acl_structured_route_binds_reader_cursor_to_revision_and_actor
  mnemo-server/tests/test_server_streaming.py::test_acl_websocket_revocation_stops_subsequent_messages`
  (PowerShell set `PYTHONDONTWRITEBYTECODE=1`): **exit 0, 12 passed**, one
  Starlette/httpx deprecation warning. These tests use disposable `tmp_path`
  stores and do not satisfy the full coverage gate. `ruff check --no-cache .`
  exited 0, `ruff format --check .` exited 0 (604 files), and
  `git diff --check` exited 0. Strict mypy and compileall were **not rerun**
  because their established cached/bytecode workflows may write artifacts;
  the prior dossier reports a passing 322-file bounded mypy gate and source
  compilation, while an exploratory whole `test_structured_v2.py` mypy run
  reported 39 errors outside that gate. Their current results are not
  independently verified here.

## 3. Authority, architecture and requirements-to-code trace

| Authority / exact section | Requirement | Implemented code / evidence | Match and risk |
|---|---|---|---|
| [Roadmap](../../architecture/current/mnemo_engineering_roadmap.md) Module 8.9.2, lines 1630-38 | 2a real actor-to-notebook authority, threat model and approved migration; 2b principal-first discovery/exact document-version scope; 2c actor/scope/alias/policy invalidation and scoped metadata/capability | `services/scope_authority.py`, `authorized_scope.py`, `membership_lifecycle.py`; route tests listed below | Design and disposable implementation exist; operational recovery, every applicable disclosure and alias/policy binding are not established. |
| [ADR-0080](../../adr/active/ADR-0080-phase-8-9-unified-authorized-retrieval-plan.md) Decision / Consequences | Server derives principal/scope; IDs never grant; no private fan-out without authority; one shared future application boundary; frozen V1 | Current HTTP/MCP services have separate adapters and partial common helpers | Current ACL routes are partly safe/guarded. Do not invent independent planners to finish 8.9.2; 8.9.3 owns the shared boundary. |
| [ADR-0075](../../adr/active/ADR-0075-additive-document-scope-resolution.md) Decision / Security / Required tests | Exact source–notebook–document–version association, no existence oracle, reauthorize continuation | `mnemo-core/mnemo/retrieval/scope.py:35-89`, `services/authorization.py:55-111`, delivery/evidence/structured adapters | Core resolver explicitly discards `principal`; caller must establish membership first. Integrated paths do; this invariant is not encoded by its interface. |
| [ADR-0058](../../adr/active/ADR-0058-advanced-retrieval-completeness-and-result-sets.md) Decision / Security | Bounded ranked versus exhaustive traversal, signed scope-bound cursor, truthful completeness | `mnemo-core/mnemo/cursors.py`, V2 evidence/structured/delivery cursors | Some application routes bind ACL revision; full issuer/consumer inventory and concurrent mutation proof remain open. |
| [ADR-0073](../../adr/active/ADR-0073-mcp-native-retrieval-and-delivery-contracts.md) Continuation / Security | Actor, exact scope, snapshot, query/selector and budgets; page reauthorization; safe errors | MCP delivery handlers and `CursorCodecV2`; raw V1 notebook-list keyset cursor | Raw UUID inventory continuation re-resolves current scope but is not an ADR-0073-style signed revision cursor. Preserve V1 behavior pending explicit compatibility decision. |
| [Architecture v2](../../architecture/current/mnemo_architecture_v2.md) §5 Purpose, §5.1, §5.3-5.4, §11 | Server as thin adapter; target principal→membership→generation→evidence→answer; V1 socket is not certified V2 FinalQA transport | Server-side application services currently contain authorization/retrieval orchestration; FinalQA V1/V2 guarded under ACL | The literal “any business logic in mnemo-server is a bug” conflicts with the actual server application-service layer and ADR-0080's planned shared service. Clarify layer ownership before relocating security logic; do not move transport trust into core merely to satisfy old prose. |
| [Membership dossier](module-8-9-2-membership-authority-design.md) approved-design and latest route addenda | Owner/reader, no inferred legacy owner, fail-closed two-store ordering, partial current status | Disposable SQLite/ASGI tests; no production ACL installation found | Historical rows need date-aware reading; positive tests use partial engine doubles in several paths. |

The **formal roadmap** has a narrow 8.9.2 exit, while recent owner task prompts
and the dossier demand positive ACL serving across *all* retained adjacent
operations. The roadmap explicitly places a common service in 8.9.3,
multi-notebook fan-out in 8.9.4, exact delivery/capability adapter parity in
8.9.6c, and FinalQA grounding in 8.9.3c/8.9.7c. Thus a decision is needed:
either require each retained operation's existing behavior to work under ACL
in 8.9.2 (and revise dependencies/acceptance explicitly), or require 8.9.2
to prove the reusable scope/disclosure contract and safely gate not-yet-
integrated operations until their named downstream modules. Do **not** count
guard-only success as positive serving or silently lower the current owner
instruction. This scope/sequence mismatch is an architectural coordination
blocker, not a reason to remove protection.

## 4. Actual identity and request chains

```text
HTTP JWT -> AuthMiddleware.validate_jwt -> request.state.auth
         -> membership_http_principal rechecks bearer via TrustedJWTActorMapper
         -> AuthorizedNotebookScopeResolver -> SQLite ACL + notebook store
         -> route/service -> exact source/document/version association
         -> response ancestry + revision recheck -> HTTP serialization

MCP stdio: server-only configured subject -> TrustedJWTActorMapper
MCP SSE: AuthMiddleware claims + bearer recheck -> session ContextVar
         -> execute_mcp_tool whitelist + _authorize_mcp_call
         -> typed handler/service -> response; four tools remain guarded

WebSocket: no HTTP auth middleware -> signed bearer validated at handshake
           and before each query -> StreamingQueryService scope/candidate
           checks -> revision/document recheck before each protected event
           -> websocket.send_text
```

`trusted_actor.py:20-54` pins issuer, audience, HS256 secret and `exp`, maps
`iss\0sub` to a stable UUID; `membership_http.py:16-59` requires JWT config,
matching signing settings and validated middleware claims, then revalidates
the header. `mcp/principal.py` distinguishes configured stdio subject from SSE
session claims. API-key mode represents one subject, not distinct users.
`scope_authority.py:28-57` defines explicit owner/reader grants, unverified
status, tombstones, revisions and create intents. No runtime source assignment
to `engine.server_scope_authority` or `server_actor_mapper` was found under
`mnemo-server/mnemo_server`; only disposable tests attach them. The live
production selector remains `UNINDEXED`, so fixture successes are not a
production indexed-serving claim.

`AuthorizedNotebookScopeResolver.resolve` (`authorized_scope.py:30-58`)
checks ACL before notebook storage, returns captured revision, then rechecks
after the read. `revalidate` (60-78) checks membership/revision around another
notebook read. `CentralAuthorizationServiceV1.authorize_document`
(`authorization.py:100-111`) orders notebook authorization before the core
document-scope resolver. The latter (`mnemo-core/mnemo/retrieval/scope.py`)
verifies canonical version and source association but explicitly ignores its
principal; direct use is **not** actor authorization. In unaffiliated legacy
fixtures, `CentralAuthorizationServiceV1.authorize_notebook` retains an
existence-only fallback; JWT HTTP query/search routes reject missing authority,
but this is configuration-dependent compatibility, not a general private
serving guarantee.

Representative data/disclosure chains, verified from the named functions:

| Family | Actual chain and current result |
|---|---|
| V1 query/search | `routers/query.py:31` / `search.py:31` → trusted JWT → selected/all authorized scopes → `QueryService.execute_query` / `SearchService.execute_search` → `MultiSourceRetriever` → `CentralAuthorizationServiceV1.filter_fused_candidates` before rerank/snippet/synthesis → document/revision checks → route revalidation. HTTP and direct MCP positive/denial tests exist; some metadata enrichment runs only for `type(engine) is KnowledgeEngine`. |
| SSE/WS | `routers/streaming.py:63,210` → HTTP or WS bearer → `StreamingQueryService.stream_query:86` → authorized scope → fused-candidate filter → per-event document/revision recheck → generator yield/send. Revocation before a later token is tested; an already accepted send is not recalled. Both WS aliases call the same handler. |
| Structured | `routers/structured_v2.py:25` and MCP `_handle_query_structured:946` → same `StructuredRetrievalApplicationService.execute:95` → authorize exact scope and catalog dataset/source/document/version ancestry → execute typed operation → post-result revision recheck. Cursor request fingerprint includes principal and ACL revision (`structured_v2.py:853`), and signed codec checks snapshot/limits. One disposable HTTP+direct-MCP ACL test exists. |
| Evidence V2 | `routers/retrieval_v2.py:42` and MCP `_handle_search_evidence` → `EvidenceRetrievalApplicationService.execute:59` → scope/selector checks → `execute_authorized` retrieval → item ancestry + ACL revision recheck (`:195-262`). The canonical disposable route test issues and rejects revision-stale cursors; full representation/partition/provider matrix is not proven. |
| Automatic V2 | `routers/retrieval_v2.py:29` and MCP `query_notebook_v2` are ACL-guarded. If unguarded as-is, `AutomaticEvidencePlanner.plan:40-72` lists global notebooks before membership resolution and requires exactly one. This is not an all-authorized private scope resolver. |
| Exact delivery/assets | `routers/delivery.py:118-402` → ACL notebook/exact document check → `BoundedDocumentExpansionService.for_membership` binds actor/notebook/revision to cursor → result ancestry and revision recheck; original and asset bytes are rechecked inside a one-yield `StreamingResponse`. MCP uses `_mcp_delivery_membership`, shared delivery service and `_revalidate_mcp_delivery` (`mcp/tools.py:1020-1138`). The core `_authorize_version` is only notebook/source/version membership, not actor authority. Owner tests cover selected document/chunk/asset pages; all analysis/derivation and in-flight modes are not independently covered. |
| FinalQA | V1 `routers/final_qa.py:20` → `FinalQAService.execute` has no principal parameter, reads notebook/session/labels and invokes persisted engine FinalQA. V2 `routers/final_qa_v2.py:21` uses legacy `principal_from_claims`; `FinalQAV2ApplicationService._execute_once:103` checks notebook but selects non-production unqualified retrieval (`:135-140`) and persists/publishes without a final ACL revision recheck. Both execution routes and MCP `run_final_qa_v2` remain ACL-guarded. Exact *published evidence delivery* is a separate integrated route with actor, notebook, ancestry and revision checks. |
| Notebook/metadata/capability | `routers/notebooks.py` uses `_require_membership` and route-level revalidation for CRUD, list, summary, timeline and graph; owner write check exists. `capabilities_v2.py:28-62` requires selected notebook under ACL and revalidates before return. MCP inventory/summary/capability have similar specialized handlers. Positive fixtures do not demonstrate every timeline/graph/role case. |
| Adjacent data/system | `app.py:397-406` attaches `require_integrated_membership_route` to sources, sessions, notes, insights, both FinalQA routers and all system routes; automatic V2 has its own guard. This is safe denial under an attached ACL, not owner/reader functionality. Health aliases are also included in the system guard despite being auth-exempt in `auth.py`, an operational-policy mismatch to decide separately. |

## 5. Lifecycle state transitions and consistency model

```text
Create: ACL.reserve_create(intent, no grant) [commit]
        -> notebook.insert_if_absent [different store/commit]
        -> ACL.finish_create(owner grant + revision + completion) [one ACL commit]
Delete: ACL.retire_notebook(tombstone + remove grants/intents + revision) [commit]
        -> notebook.delete [different store/commit]
Share/revoke: owner check + notebook existence read
              -> ACL.grant/revoke [later ACL transaction]
```

`membership_lifecycle.py:32-100` and `scope_authority.py:161-256,274-390`
implement these steps. `BEGIN IMMEDIATE` serializes each ACL write across
SQLite processes. It does **not** make notebook-store and ACL-store writes
atomic. The pending-create window has no active grant, and tombstone-first
delete denies access before physical deletion. `recover_create` requires the
exact `Notebook`, actor and token and compares stored fields before activation.
`retire_notebook` is idempotent; retrying storage deletion is expected.

The lifecycle tests (`test_module_892_lifecycle.py:92-385`) cover partial
creates/deletes, collisions, mismatch, retries and separate-process SQLite
grant serialization and simultaneous recovery. The process-recovery fixture
*passes the notebook object and token from the parent into replacement
processes*. A real crash can lose those values: the durable intent table holds
only notebook ID, actor and token, not the full payload or an enumerated
reconciliation state. Therefore tested fail-closed access is stronger than
tested unattended recovery. There is no demonstrated consistent two-store
snapshot, power-loss durability proof, orphan inventory or production
operator runbook. An operator may leave a pending notebook quarantined; that
is safe but not complete recovery.

More importantly, `MembershipOperatorService._require_owner` (`:30-36`)
checks role and notebook existence *before* `grant_reader` calls
`scope_authority.grant` (`:38-44`). `grant` records `operator_id` but does not
verify its currently active owner role inside its `BEGIN IMMEDIATE`
transaction. Interleaving: owner check succeeds → another worker revokes that
owner → first worker inserts a reader grant. Tombstone-first deletion blocks
this race if the notebook is retired, but ordinary owner revocation does not.
This is a **code-established TOCTOU authorization defect**, not a demonstrated
remote exploit; no public grant endpoint is registered. The same ordering
affects `revoke_reader` decisions and any later operator API using this seam.

## 6. Reconstructed route and tool matrix

The following groups enumerate **all 54 snapshot HTTP routes, all 15 MCP
tools, and both WS aliases**. `I` is implementation of positive ACL serving;
`V` is positive owner/reader plus denial/revocation evidence. `FAIL` means a
required positive operation is deliberately guarded or a concrete defect is
shown, not that a guard leaks data. `NOT PROVEN` never means a leak is proven.
The `I`/`V` grade applies to the *whole listed family*; individual members
with stronger tests are named in the text above. `N/A` applies to cursor tests
for nonpaginated operations, not to authentication.

| Exact registered paths / tools | I | V | Why incomplete or established |
|---|---|---|---|
| `POST /v1/query`, `POST /v1/search`; MCP `query_notebook`, `search_all_notebooks` | PASS | PASS | Owner/reader, stranger, legacy-unassigned and pre-return revoke fixture tests; legacy no-ACL mode remains. |
| `POST /v1/query/stream`; WS `/ws/query`, `/v1/ws/query` | PASS | PASS | SSE and WS ACL fixture tests, including revocation before a subsequent message; no instantaneous send-cancellation claim. |
| `POST /v2/retrieval/structured`; MCP `query_structured` | PASS | PASS | Exact catalog ancestry, owner/reader, replay/revision denial in disposable test; provider/deployed parity not claimed. |
| `POST /v2/retrieval/evidence`; MCP `search_evidence` | PASS | NOT PROVEN | Canonical owner/denial and signed continuation tested; full representations/partitions and every alternate ancestry not exercised. |
| `POST /v2/retrieval/automatic`; MCP `query_notebook_v2` | FAIL | NOT PROVEN | Both guarded; planner still does global single-notebook discovery before ACL. |
| `GET /v2/capabilities`; MCP `get_capabilities` | PASS | NOT PROVEN | Scoped fixture cases exist; no complete ready/unavailable, cache/revision and transport-equivalence matrix. |
| `GET /v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}`, `POST /v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/expand`, `GET /v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/original`, `GET /v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/chunks/{chunk_id}`; MCP `get_document`, `get_document_chunk` | PASS | NOT PROVEN | Shared exact ancestry and bound cursors; selected owner/replay tests, not full reader/cross-source/revoke-in-send matrix for every variant. |
| `GET /v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/assets`, `GET /v2/notebooks/{notebook_id}/asset-occurrences/{occurrence_id}/content`, `GET /v2/notebooks/{notebook_id}/asset-occurrences/{occurrence_id}/analysis`; MCP `get_asset`, `get_image_analysis` | PASS | NOT PROVEN | Asset page/bytes fixture exists; OCR/Vision derivation selector and all analysis paths lack full ACL-attached positive/revocation proof. |
| `GET /v2/notebooks/{notebook_id}/final-qa/{assistant_turn_id}/evidence` | PASS | NOT PROVEN | Published-evidence actor/notebook binding and attribution recheck exist; no end-to-end ACL FinalQA production of that snapshot. |
| `POST /v1/notebooks/{notebook_id}/final-qa`, `POST /v2/notebooks/{notebook_id}/final-qa`; MCP `run_final_qa_v2` | FAIL | NOT PROVEN | Guarded; V1 lacks principal and V2 lacks ACL-aware non-production retrieval/final revision check. |
| `POST /v1/notebooks`, `GET /v1/notebooks`, `GET/PATCH/DELETE /v1/notebooks/{notebook_id}`, `GET /v1/notebooks/{notebook_id}/summary`, `GET /v1/notebooks/{notebook_id}/timeline`, `GET /v1/notebooks/{notebook_id}/graph`; MCP `list_notebooks`, `get_notebook_summary` | PASS | NOT PROVEN | Create/list/get/summary and owner-write denial tested; individual timeline/graph role/revoke and complete two-store lifecycle proof remain. Inventory cursor is raw UUID but re-filters each page. |
| `POST/GET /v1/notebooks/{notebook_id}/sources`, `GET/DELETE /v1/notebooks/{notebook_id}/sources/{source_id}`, `GET /v1/notebooks/{notebook_id}/sources/{source_id}/status` | FAIL | NOT PROVEN | All five ACL-guarded; source ancestry/mutation role policy not integrated. |
| `GET/POST /v1/notebooks/{notebook_id}/sessions`, `GET/DELETE /v1/notebooks/{notebook_id}/sessions/{session_id}`, `POST /v1/notebooks/{notebook_id}/sessions/{session_id}/turns` | FAIL | NOT PROVEN | All five guarded; session/turn ownership and reader write policy need a contract. |
| `GET/POST /v1/notebooks/{notebook_id}/notes`, `GET/PATCH/DELETE /v1/notebooks/{notebook_id}/notes/{note_id}` | FAIL | NOT PROVEN | All five guarded; note ancestry and role policy not integrated. |
| `GET /v1/notebooks/{notebook_id}/insights`, `POST /v1/notebooks/{notebook_id}/insights/generate`; MCP `get_source_insights` | FAIL | NOT PROVEN | HTTP pair and MCP tool guarded; derived insight ancestry and cache policy need proof. |
| MCP `get_timeline` | FAIL | NOT PROVEN | Guarded, despite related HTTP notebook timeline route being exposed; no parity evidence. |
| `GET /v1/health`, `GET /health`, `GET /v1/config`, `GET /config`, `GET /v1/config/models`, `GET /config/models`, `PATCH /v1/config`, `PATCH /config`, `GET /v1/jobs`, `GET /jobs`, `GET /v1/jobs/{job_id}`, `GET /jobs/{job_id}` | FAIL | NOT PROVEN | All 12 share the ACL blanket guard. Separate public-health vs privileged-config/job policy needed. |

For mutation roles, a reader is **not** expected to succeed at owner-only
PATCH/DELETE/grant/revoke; the relevant positive proof is owner success plus
reader denial. Where a family has no pagination, cursor binding is N/A.
The 11 MCP tools allowed by `execute_mcp_tool:863-877` and four guarded tools
match the versioned snapshot. HTTP system/sources/sessions/notes/insights/
FinalQA guards come from `app.py:397-406`, not each router file; removing a
router-level guard without tracing middleware and direct MCP is insufficient.

## 7. Cursor, cache and disclosure findings

`CursorCodecV2` (`mnemo-core/mnemo/cursors.py:72-208`) signs and validates
domain, binding, snapshot, limits, integrity and expiry. It does **not** fetch
ACL state itself. Evidence V2 threads `membership_revision` into the plan and
revalidates response (`services/retrieval_v2.py:59-262`); structured uses the
principal/revision request fingerprint (`structured_v2.py:485-528,853-867`);
delivery uses request-local `for_membership` and rejects unbound legacy cursors
under actor binding (`mnemo-core/mnemo/delivery.py:289-319,1014-1110`). The
disposable tests at `test_module_892_retrieval_routes.py:220-533` and
`test_structured_v2.py:259-384` exercise normal page and stale/replayed
cursors through real ASGI/direct MCP handlers.

Notebook inventory (`routers/notebooks.py:140-177`, MCP
`tools.py:1754-1835`) instead emits a raw UUID keyset cursor. It re-resolves
current authorized IDs on every page and revalidates before return, so a
stale cursor is not evidence of access restoration. It does **not** bind the
inventory snapshot or ACL revision, so continuation semantics can shift after
grants/revocations. ADR-0073's signed-cursor wording and frozen V1 list
compatibility need an explicit versioned decision rather than an incidental
format change. Policy/alias/generation change binding is not uniformly proven
for all cursor issuers; current ACL fixture tests mostly change grants.

No cross-request cached ACL decision was located in the inspected server
services; `source_metadata.py` has a request-local duplicate-reference cache.
This is **not** proof that every provider/index/job cache is ACL-independent.
FinalQA published snapshots and background job state are persistent derived
data and must be authorized at each retrieval/delivery. The current FinalQA
execution guard prevents ACL-attached writes but does not supply positive
functionality. The exact delivery routes revalidate before HTTP return; binary
stream generators revalidate again before their one content yield. SSE/WS
service revalidates before each protected event, then transport sends it.
There is an unavoidable window between that check and bytes accepted by
ASGI/WS; already sent bytes cannot be recalled. Tests demonstrate prevention
of *subsequent* messages after a detected revoke, not zero-latency recall or
cancellation of every in-flight transport send.

## 8. Blocker register (severity and dependency order)

Each item separates established behavior from an unproven scenario. “Close”
is the objective evidence required; none is closed by this report.

### B-01 — Operator grant TOCTOU (security-critical; code-established)

- **Criterion/location:** 8.9.2a trusted owner-only grant/revoke;
  `membership_operator.py:30-50`, `scope_authority.py:117-159,274-291`.
- **Observed vs expected:** owner role checked before separate `BEGIN IMMEDIATE`
  grant transaction; `operator_id` is stored but not reauthorized in that
  transaction. Expected a currently authorized operator at commit.
- **Scenario/evidence:** owner check succeeds, concurrent worker revokes owner,
  first worker inserts reader grant; source ordering establishes the possible
  interleaving. No public grant route exists, so remote exploit is not shown.
- **Root/dependency:** operator policy and ACL mutation are split; transaction
  API accepts an already-resolved operator rather than proving current role.
- **Options/recommendation:** atomically check active owner/tombstone and apply
  reader mutation + revision in one ACL transaction (recommended); a notebook
  existence recheck can precede it but cannot replace atomic owner check.
  Alternative external serialized operator queue adds unnecessary state.
- **Risk/tests/close/future:** preserve exact retry/idempotency and reader
  semantics; interleave two SQLite processes with owner revocation and grant,
  assert no post-revoke grant or unchanged revision on rejected mutation;
  close only when this passes and audit attribution is correct. Otherwise any
  later sharing UI/API repeats the race.

### B-02 — Create-intent recovery lacks standalone payload (correctness-critical;
code-established)

- **Criterion/location:** 8.9.2a crash/restart reconciliation;
  `membership_lifecycle.py:32-90`, `scope_authority.py:161-272`.
- **Observed vs expected:** durable intent has notebook ID/actor/token, while
  `recover_create` also requires exact notebook title/metadata/timestamps.
  Fixture replacement processes receive object/token from the parent.
- **Scenario/evidence:** process crashes after notebook insert before owner
  activation; access safely remains denied, but an independent restarted
  worker cannot enumerate/reconstruct the full exact intent from ACL alone.
- **Root/dependency:** fail-closed write ordering was implemented without a
  complete recovery journal or operator discovery/reconciliation contract.
- **Options/recommendation:** persist a hash/serialized immutable create
  payload plus operation ID and recovery state in an operational journal, or
  explicitly choose manual quarantine with auditable orphan discovery and no
  automatic activation. Never infer owner from notebook contents. Do not
  mutate production before a versioned schema/recovery approval.
- **Risk/tests/close/future:** payload storage affects privacy/migration and
  rollback; kill a writer at each commit boundary, restart a process supplied
  only with durable stores, enumerate/reconcile idempotently, prove mismatches
  stay quarantined and tombstones persist. Phase 9 notebook creation otherwise
  inherits unrecoverable partial operations.

### B-03 — Two-store recovery proof stops at selected boundaries
(correctness/verification; partly code-established)

- **Criterion/location:** 8.9.2a lifecycle/revocation/rollback;
  `membership_lifecycle.py:91-100`, `scope_authority.py:274-390`,
  `test_module_892_lifecycle.py:92-385`.
- **Observed vs expected:** tombstone-first delete and ACL-local revision
  transactions are sound fail-closed ordering, but there is no cross-store
  atomic commit, consistent backup protocol, or power-loss proof. Existing
  tests cover separate processes and retries, not all durable recovery inputs.
- **Scenario/evidence:** notebook-store outage after tombstone leaves physical
  notebook orphaned and inaccessible; that is safe denial, but cleanup,
  audit, backup/restore ordering and operator retry remain operational work.
- **Root/dependency:** independent SQLite stores and no lifecycle journal/
  reconciliation inventory. This is not itself a demonstrated data leak.
- **Options/recommendation:** retain tombstone-first and fail-closed behavior;
  define durable reconciliation states and consistent snapshot/restore
  ordering. Alternative same-store transaction requires an approved topology
  migration and is not a small local fix.
- **Risk/tests/close/future:** do not restore stale ACL snapshots; test missing/
  corrupt store, restart, simultaneous retry, duplicate request and restored
  pre-revoke backup; close with a documented runbook and proven non-restoration.
  Future ingestion/deletion jobs depend on this model.

### B-04 — Automatic V2 is not principal-first under ACL (security-critical
*if enabled*; presently safely guarded)

- **Criterion/location:** 8.9.2b scope; `retrieval_v2.py:29-39`,
  `automatic_query_v2.py:40-72`, MCP `tools.py:863-877`.
- **Observed vs expected:** global `list_notebooks(limit=2)` precedes membership;
  one global notebook is required. ACL-attached HTTP/MCP automatic operation
  is blocked, so there is no demonstrated current cross-user disclosure.
- **Scenario/evidence:** removing the guard alone would make another user's
  notebook count influence readiness and could select a notebook from global
  storage; the code path establishes that risk.
- **Root/dependency:** legacy one-notebook planner has no authorized scope
  input; planned shared scope/service is in 8.9.3/8.9.4.
- **Options/recommendation:** replace global discovery with server-resolved
  authorized scope in the future shared application boundary; keep this route
  guarded until then. A narrow one-authorized-notebook adapter may preserve
  current V2 semantics, but must not imply multi-notebook fan-out.
- **Risk/tests/close/future:** preserve V2 response/defaults; test one private
  owner/reader, two global but one authorized, none authorized, stale grant,
  provider alias hidden before authorization; close with positive HTTP/MCP and
  denial tests. 8.9.4 otherwise builds fan-out atop unsafe discovery.

### B-05 — FinalQA lacks an ACL-safe execution/persistence boundary
(security/correctness-critical if enabled; guarded)

- **Criterion/location:** 8.9.2b/c protected retrieval and disclosure;
  `routers/final_qa.py:20`, `services/final_qa.py:21-88`,
  `routers/final_qa_v2.py:21-43`, `services/final_qa_v2.py:103-244`,
  `app.py:405-406`, MCP `tools.py:863-877`.
- **Observed vs expected:** V1 has no principal parameter. V2 notebook check
  uses old principal mapping and its non-production branch calls unqualified
  retrieval before persisted execution; no final ACL revision check is visible
  after publication. Both execution routes/tools are ACL-guarded.
- **Scenario/evidence:** merely lifting the guard can process/cite data from an
  unqualified source and persist an answer after membership changes; this is
  a conditional risk, not a leak while guard remains.
- **Root/dependency:** answer orchestration and persistence predate explicit
  membership context; 8.9.3c and 8.9.7c own the shared authorized evidence
  snapshot/publication contract.
- **Options/recommendation:** carry a trusted authorization context and exact
  evidence ancestry into a prepublication check and replay lookup; stage or
  abort persisted output on revocation. Keep guarded until positive path and
  idempotent rollback tests pass. Do not synthesize an empty answer as a fix.
- **Risk/tests/close/future:** citation/replay compatibility; test owner/reader
  policy, cross-user session/turn, revoked source, tampered evidence, revoke
  during generation/before commit/response, and replay. Close with persisted
  snapshot and final disclosure proven to same actor/scope/revision. Phase 9
  UI chat and 8.9.7 grounding depend on it.

### B-06 — Blanket guards mask missing adjacent operation policy
(architectural/functional; confirmed disabled, no leak shown)

- **Criterion/location:** scope and disclosure across retained routes;
  `app.py:397-406`, `dependencies.py:66-73`, sources/sessions/notes/insights/
  system routers, MCP `tools.py:863-877`.
- **Observed vs expected:** 32 HTTP paths and four MCP tools have no positive
  ACL-attached serving. Guard gives safe refusal, not owner/reader operation.
  Health is in the system guard although authentication exempts it.
- **Scenario/evidence:** an authorized reader cannot list their sources or
  session turns; broad guard removal would expose direct store calls in those
  routers. Exact HTTP inventory above and registration establish behavior.
- **Root/dependency:** mutation/read role policy and resource ancestry were
  not expressed in shared service interfaces; route registration is a coarse
  temporary switch.
- **Options/recommendation:** define operation classes (public health,
  notebook read, owner mutation, source/document read, session/turn/note
  ownership, operator config/job) and bind principal/scope before store reads;
  revalidate before disclosure. Keep individual paths guarded until their
  owner-success/reader-policy/denial tests pass. Do not move all operations
  into a new framework merely for symmetry.
- **Risk/tests/close/future:** V1 defaults, source ingestion and mutation
  semantics; each registered path needs disposable owner/read/deny/revoke
  integration plus alternate MCP parity where applicable. Future Phase 9
  dashboard/notebook/session pages cannot use a guard-only API.

### B-07 — Positive coverage differs from actual engine branch coverage
(verification-only with possible hidden integration defects)

- **Criterion/location:** 8.9.2b exact ancestry and 2c disclosure;
  `test_module_892_http_routes.py:50-270`,
  `test_module_892_retrieval_routes.py:220-533`,
  `services/retrieval_v2.py:96,112`, `routers/delivery.py:56`,
  `services/query.py:214`, `search.py:209`, `structured_v2.py:134`.
- **Observed vs expected:** several route tests attach ACL to
  `MagicMock(spec=KnowledgeEngine)`; application code gates metadata and some
  authorization paths with exact `type(engine) is KnowledgeEngine`, so those
  branches do not run in those positive tests. This is an evidence gap, not
  proof their real-engine branch leaks.
- **Scenario/evidence:** real engine enriches citations/source metadata or
  executes a different principal-aware path than fixture double; a bug in
  that branch would not fail the current test.
- **Root/dependency:** testability by concrete-type check and partial mock
  conflicts with the intended service contract.
- **Options/recommendation:** use a minimal real KnowledgeEngine composition
  over disposable storage/providers for one matrix, or introduce a narrow
  explicit capability/protocol check replacing type identity after contract
  review. Retain fast doubles for unit tests, but not as sole integration proof.
- **Risk/tests/close/future:** real composition may reveal missing providers;
  do not mock away the behavior. Close with actual engine owner/reader,
  shared-source, exact asset/analysis, metadata and revocation cases. Future
  adapters otherwise inherit false parity confidence.

### B-08 — Cursor and policy binding is not uniform (architectural/
verification; no replay leak demonstrated in tested V2 paths)

- **Criterion/location:** 8.9.2c actor/scope/alias/policy invalidation;
  `routers/notebooks.py:140-177`, MCP `tools.py:1754-1835`,
  `mnemo-core/mnemo/cursors.py:72-208`, evidence/structured/delivery paths.
- **Observed vs expected:** V2 ACL-attached cursors bind actor/revision in
  tested cases. V1 notebook inventory uses raw UUID, and alias/policy change
  invalidation is not uniformly tested. Cursor codec checks only the binding
  supplied by each caller.
- **Scenario/evidence:** an inventory page after membership mutation may
  reorder/skip/duplicate items, though it re-filters and has not been shown to
  reveal revoked data. A new issuer omitting ACL revision would accept a
  validly signed stale cursor.
- **Root/dependency:** no shared authorization-context-to-cursor contract or
  issuer inventory enforced at code review; V1 compatibility complicates
  format changes.
- **Options/recommendation:** define an authorization-context fingerprint
  builder consumed by all *new* signed cursor issuers, with server-derived
  actor, scope, ACL revision, policy/alias/representation and limits. Decide
  separately whether to version the V1 inventory cursor or retain its
  reauthorized keyset semantics under a documented exception.
- **Risk/tests/close/future:** cursor compatibility and migration; enumerate
  every issuer, test tamper/expiry/cross-principal/revoke/alias/policy/limit
  change, and ensure no silent restart. 8.9.4c traversals require this gate.

### B-09 — Stream cancellation boundary is narrower than instantaneous revoke
(verification/contract; tested future-message denial)

- **Criterion/location:** 8.9.2c disclosure; `streaming.py:86-260`,
  `routers/streaming.py:63-249`, `routers/delivery.py:170-287`.
- **Observed vs expected:** per-event revalidation and binary one-yield
  revalidation occur before yield/send. Tests revoke between tokens and reject
  a subsequent event. There is no proven cancellation of an already queued
  ASGI/WebSocket send or recall of bytes already accepted by transport.
- **Scenario/evidence:** revoke immediately after the final ACL read but
  before `send_text` completes; that event can still be delivered. This is
  an unavoidable asynchronous boundary absent transport-level synchronization.
- **Root/dependency:** ACL check and network send cannot be one SQLite
  transaction; the contract must state detection points and bounded exposure.
- **Options/recommendation:** keep per-message checks, cancel long-running
  work at checkpoint/revocation signal where feasible, and document that
  already accepted bytes are not recalled. Do not promise instantaneous
  revocation or increase timeouts to mask scheduling.
- **Risk/tests/close/future:** cancellation may affect V1 event ordering;
  test queued work, blocked sends, reconnect, multi-message reader/owner and
  tombstone changes. Close with a precise enforceable guarantee, not a zero-
  race claim. Future V2 streaming design must inherit it.

### B-10 — Identity/scope logic remains conditional and duplicated
(architectural; current production fail-closed)

- **Criterion/location:** 8.9.2b same scope across HTTP/MCP/services;
  `services/authorization.py:55-83,157-164`,
  `membership_http.py:16-59`, `mcp/principal.py`,
  `routers/query.py:31-61`, `search.py:31-60`, `retrieval_v2.py:34-53`.
- **Observed vs expected:** JWT+ACL routes use trusted mapper; legacy no-ACL
  paths retain existence-based or anonymous fixtures. `principal_from_claims`
  uses a different UUID namespace than `TrustedJWTActorMapper`. Some services
  accept optional principal and branch on concrete engine type.
- **Scenario/evidence:** reusing a legacy principal in an ACL operation fails
  membership; removing a route guard without passing trusted mapper/scope
  may select the fallback. Current JWT query/search explicitly reject missing
  authority, so no active production exploit is established.
- **Root/dependency:** no one explicit immutable authorization context
  contract at the application-service boundary; historical V1 compatibility
  exists beside the new ACL path.
- **Options/recommendation:** define a server-owned context (trusted actor,
  authorized notebook/document-version set, role, ACL revision, policy and
  alias identity) passed to protected application services; adapters only
  authenticate/translate. Preserve a clearly isolated legacy local mode and
  fail closed if indexed multi-user serving lacks context. This is a needed
  input to roadmap 8.9.3, not a parallel planner.
- **Risk/tests/close/future:** principal re-keying could strand grants;
  migration requires explicit attestation. Close with HTTP/direct MCP/real
  transport equivalence tests and negative missing-context tests. All later
  unified retrieval/adapters depend on stable semantics.

### B-11 — Intermittent stdio initialization timeout (verification-only;
root cause unknown)

- **Criterion/location:** repeatable configured acceptance gate;
  `test_ordered_text_certification.py:95-136` (15-second MCP request deadline),
  `mcp_contract_stdio_child.py`, saved JUnit reports.
- **Observed vs expected:** one full run took 855.76 s and failed at
  `client.initialize()`; unchanged repeat took 283.07 s and passed. Earlier
  isolated case passed. No deadline was raised. This investigation did not
  reproduce it and cannot attribute the cause to the ACL changes.
- **Scenario/evidence:** on a loaded run, child startup or response misses
  15 s. The timeout traceback and later green JUnit establish intermittent
  behavior; whether import, process scheduling or resource contention caused
  it is **unknown**.
- **Root/dependency/options:** unknown until timestamped parent/child startup
  observations. Add diagnostic timing outside protocol stdout and capture
  process resource context; then fix a measured bottleneck, not a timeout.
- **Risk/tests/close/future:** preserve stdio protocol framing and deadline;
  repeated full-suite and ordered-text runs under equivalent load with actual
  exit codes plus cause-specific timing evidence close it. 8.9.8 transport
  certification cannot treat one green local run as external parity.

### B-12 — Production authority installation is a separate operational gate
(approval/readiness; not permission granted here)

- **Criterion/location:** operational indexed multi-user readiness;
  `app.py`, `mcp/server.py`, `scope_authority.py`, production selector.
- **Observed vs expected:** tests inject `server_scope_authority` and
  `server_actor_mapper`; repository runtime composition does not install
  them, and production remains `UNINDEXED`. Existing legacy notebooks gain no
  inferred owner. This is correct for the protected baseline.
- **Scenario/evidence:** enabling an index without a separately approved ACL
  migration/composition would leave protected serving unavailable or fall into
  a legacy seam. No such operation was attempted.
- **Root/dependency/options:** explicit production inventory, owner/grant
  attestation, backups, rollback and authorization gate are still required.
  Keep production offline; do not use disposable fixture results as approval.
- **Risk/tests/close/future:** exact deployment readiness, credentials and
  external transport are Phase 8.9.8/8.9.9 gates; close only with separately
  authorized target-specific migration and signed acceptance evidence.

## 9. Systemic causes and where to repair them

| Cause evidenced in code | Affected current surface | Proper layer and future implication |
|---|---|---|
| ACL decision, role mutation and notebook storage span separate interfaces/transactions | Create/delete/recovery; grant/revoke | Make ACL mutation operator check atomic; versioned journal/reconciliation and rollback. Do not claim cross-store atomicity. |
| Principal and authorization context are optional or inferred differently | V1 services, V2 evidence/automatic, structured, FinalQA, MCP | Trusted identity remains transport-owned; one server application context should carry authorized scope/revision into 8.9.3 shared service. Core exact association remains actor-neutral but cannot be called as an authorization decision. |
| Route-specific guards are coarse, while similar operations have separate HTTP/MCP handlers | 32 HTTP + four MCP guarded paths; notebook/delivery variants | Replace each guard only with positive scope/role service integration and paired transport tests. Do not broad-remove dependencies. |
| Concrete-engine type checks change execution branches | Real-engine metadata/citation branches versus `MagicMock` fixtures | Prefer explicit interfaces/capabilities and at least one real-engine disposable matrix; static unit doubles remain useful but insufficient. |
| Cursor signing is caller-supplied and inventory retains V1 raw keyset | V2 evidence/structured/delivery, V1 notebook list, future fan-out | Standardize security-context binding for new cursors; version/exception decision for V1. |
| Documentation conflates target adapter purity with actual server application services | Architecture §5 versus 8.9.3 planned boundary | Clarify server adapters vs application orchestration ownership before moving logic. Moving JWT trust into core would create a new confused-deputy boundary. |
| Positive authorization fixture breadth lags route breadth | FinalQA, assets/analysis, adjacent data, real engine variants | Reusable owner/reader/shared-source/revoke fixture contract; each new protected route/tool must demonstrate success and denial, not just guard behavior. |

## 10. Downstream dependency and risk matrix

| Actual future module/phase | Roadmap dependency | Unresolved prerequisite | Risk if started first | Required contract / acceptance gate |
|---|---|---|---|---|
| 8.9.3 shared search application contract | Entry 8.9.1b; consumes 8.9.2 authority in architecture target | Explicit trusted authorization context and exact association interface | Parallel HTTP/MCP policy drift | Versioned context/schema, real-engine and direct-tool tests; no second planner. |
| 8.9.4 scoped automatic hybrid retrieval | 8.9.2b + 8.9.3b; traversal also 8.9.2c | Principal-first authorized selection, alias/policy cursor binding | Cross-user fan-out or stale page access | Selected/all authorized scopes, per-source coverage, revoke/alias replay matrix. |
| 8.9.5 structured knowledge access | 8.9.2b + 8.9.3b for discovery | Dataset/source/document/version ancestry contract | Row or schema existence disclosure | Typed dataset/row scope and unavailable-generation tests. |
| 8.9.6 MCP/HTTP adapters and compatibility | 8.9.1c, 8.9.3b, 8.9.4b; 8.9.6c also 8.9.2c | Exact delivery/capability route parity and V1 cursor decision | Registered tools with inconsistent authorization | Paired HTTP/MCP fixture, V1 defaults and sign-off/deprecation gate. |
| 8.9.7 provenance/errors/FinalQA | 8.9.4/5 evidence, 8.9.3c | Authorized evidence snapshot and prepublication recheck | False citations or stale persisted answer | Resolvable ancestry, revoked-source, replay/timeout and safe-error tests. |
| 8.9.8 real transport parity | 8.9.6/7 | Stable internal semantics and stdio startup diagnosis | False certification from direct handler/ASGI-only tests | Deployed HTTP and MCP stdio/SSE/external observations; timing traces. |
| 8.9.9 integrated GO/NO-GO and Phase 9 UI | All mandatory 8.9 tasks; Phase 9 needs exact GO | Operational authority migration, protected-state, external evidence | UI built on guarded/nonfunctional APIs or uncertified index | Exact deployment identity, source hashes, consumer acceptance, signed GO. |

The roadmap already contains the main dependency order. Recommended **future
roadmap clarification** (not made here): state whether 8.9.2 exit demands
positive ACL serving for *every existing ancillary operation* or only a
certified reusable authority/scope/disclosure seam with nonintegrated routes
held closed until 8.9.3/8.9.6. Add an explicit positive-and-negative test
gate per route when it becomes available. No new module number is proposed.

## 11. Recommended remediation sequence and precise acceptance

1. **Decide the 8.9.2 scope boundary (owner/architecture review).** Reconcile
   the formal 8.9.2 table with the broad later completion instructions, ADR-
   0080 compatibility and 8.9.3/8.9.6 ownership. Record whether guarded
   retained routes may remain disabled at 8.9.2 exit and which existing V1
   operations must positively work. Until decided, keep PARTIAL and guards.
2. **Fix ACL mutation authority before new sharing exposure.** Make operator
   role/tombstone check and grant/revoke/revision one SQLite transaction;
   prove concurrent owner revocation versus grant in separate processes.
   Preserve no inferred legacy owners.
3. **Choose a durable recovery contract.** Prefer a versioned operation journal
   or explicitly approved manual quarantine/reconciliation protocol, then
   test restart using *only* durable stores, duplicate retries, backup/restore
   ordering, and tombstone non-restoration. Keep production migration separate.
4. **Freeze one server-owned authorization-context seam for protected
   application services.** Include actor, selected notebooks, exact source/
   document/version associations, role, ACL revision and policy/alias identity.
   Transport adapters authenticate; core resolver checks physical association.
   Preserve local V1 mode explicitly, but require context in ACL mode. This
   makes 8.9.3 possible without rewriting each transport's planner.
5. **Integrate positive paths in dependency order.** First automatic V2's
   one-authorized-notebook compatibility case, then source/session/note/
   insight policy as approved, then FinalQA evidence→generation→persistence→
   disclosure. Keep each guarded until real-engine disposable owner/reader,
   cross-user, nonexistent, unassigned and in-flight revocation cases pass.
   Decide whether FinalQA integration belongs to 8.9.2 or 8.9.3c/8.9.7c
   rather than duplicating that later application boundary.
6. **Inventory/standardize continuations and caches.** Bind all new signed
   cursors to the shared context; retain or version raw V1 notebook keyset
   after explicit compatibility review. Test each issuer and consumer,
   including alias/policy/revision changes, not just codec syntax. Test
   queued streaming and delivery boundaries with a precise future-message
   guarantee, never a recall promise.
7. **Run the acceptance matrix and diagnose stdio separately.** Require
   focused isolated/real-engine paths, HTTP/direct MCP, separate-process
   lifecycle, full configured 90% coverage suite with observed exit, Ruff,
   established strict mypy, compile and diff checks. Investigate intermittent
   stdio with measured startup traces; do not alter the 15-second deadline
   without a justified contract decision.

**8.9.2a closes** only with approved authority/migration design, transactional
owner-only grants, durable fail-closed create/delete/revoke reconciliation,
cross-process crash/restart/restore tests and an operator rollback runbook.
This does not itself authorize production migration.

**8.9.2b closes** only when principal-first selection and exact resource
association work for the agreed set of required existing operations, with
owner/reader positive behavior, mutation-role denial, unknown-owner quarantine,
cross-user/nonexistent equivalence and pre-disclosure revalidation through
real application paths. Any remaining guarded operation must be explicitly
assigned to a later accepted gate rather than counted as passing.

**8.9.2c closes** only when every applicable issuer/continuation in the
agreed scope checks current authoritative ACL, actor, scope, policy/alias,
query and limits; stale/tampered/cross-actor pages reject; metadata/capability
and streaming are revalidated at the declared delivery checkpoints. V1 raw
keyset treatment must be explicit. Already-sent bytes are outside revocation.

## 12. Decisions and unknowns

Project-owner/architecture decisions needed before implementation: (1) exact
8.9.2 versus 8.9.3/8.9.6/8.9.7 positive-serving exit scope; (2) journaled
automatic recovery versus auditable manual quarantine for interrupted create;
(3) operation-specific reader/owner semantics for source/session/note/insight
and FinalQA persistence; (4) versioned V1 inventory cursor versus documented
reauthorized-keyset exception; (5) any target-specific *production* ACL
migration/owner attestation, separately from development authorization.

Unknown or not proven: all provider/representation variants under a real
KnowledgeEngine ACL composition; cross-store power-loss durability; exact
root cause of the 15-second stdio miss; deployed MCP/UI consumer acceptance;
future production owner mapping; every protected path's in-flight transport
race; and the absence of authorization-sensitive state in uninspected provider
caches. No unknown is silently counted as PASS.

## 13. Preservation check

The investigation ran no live decommission, production test, migration,
indexing, credential operation or tunnel startup. Focused tests used disposable
`tmp_path` stores, disabled pytest cache and bytecode writing. `UNINDEXED`
was read before and after. Existing tracked/untracked work was not edited,
staged or committed. Module 8.9.3 remains unstarted. Any production ACL
operation would require an exact target, inventory, backup/rollback and a
separate authorization; this report grants none.
