# Module 8.9.1 — contract inventory and migration authority

Date: 2026-10-20. Baseline: `7f405c7`, branch `main`, initially clean working
tree (including index); no pending tracked deletions. The earlier 15 source
deletions are committed history, not deletions introduced or restored here.
This is Module 8.9.1 work authorized by the owner, not production activation.
ADR-0080 was proposed at this baseline; its owner-approved design addendum
of 2026-10-21 is recorded below. No Module 8.9.2 implementation is included.

## Status and authority

| Task | Status | Evidence / remaining acceptance |
|---|---|---|
| 8.9.1a | PASS, repository inventory | Versioned registration/OpenAPI snapshot, source and consumer inventory below; unknown external consumers explicitly recorded |
| 8.9.1b | PASS for design review; public wire implementation deferred | Owner-approved ADR and versioned design schema/negative fixtures; shared runtime and transport mappings belong to later modules |
| 8.9.1c | PASS under owner-approved exit-gate amendment of 2026-10-21 | Versioned consumer inventory, reversible migration/deprecation plan, sign-off protocol and internal compatibility checks; actual per-consumer sign-offs remain mandatory at later cutover/deprecation |
| Module | COMPLETE for design and governance under the amended criteria | No external consumer sign-off, deployed parity, indexed serving or Phase 8.9 GO is claimed |

The authoritative scope is the [roadmap Module 8.9.1 and migration table](../../architecture/current/mnemo_engineering_roadmap.md).
The [architecture current-versus-target boundary](../../architecture/current/mnemo_architecture_v2.md)
and [ADR-0080](../../adr/active/ADR-0080-phase-8-9-unified-authorized-retrieval-plan.md)
do not authorize registration of proposed names. Accepted ADRs 0058, 0061–64,
0067–69, 0073–79 and 0081 retain their original scopes.

## Versioned inventory and reproducibility

The [current surface snapshot](../../governance/contracts/phase8_9_1_current_surface.v1.json)
records all **15 MCP tools**, **54 HTTP method/path operations over 42 paths**,
their actual handler symbols, immediate route dependencies, middleware, MCP
input/output schemas and full OpenAPI request/response schemas. This is
registration inspection, not live availability: production is UNINDEXED.
Default FastAPI documentation endpoints are not knowledge operations and are
not counted. The separate observation-only application registers
`/internal/pre-certification/observe` and MCP `observe_runtime`, not knowledge
tools (`app.create_app(pre_certification_observation=True)` and
`mcp.server.create_pre_certification_mcp_server`). No observation server was launched.

Reproduce without lifespan, storage, model initialization or operator secrets:

```powershell
.\.venv\Scripts\python.exe -m scripts.snapshot_public_contracts --output <new-snapshot.json> --review-output <new-review-schema.json>
```

The utility requires explicit `--replace` to overwrite any output. Review diffs,
do not refresh snapshots automatically to bless a breaking change. It uses
ephemeral constructor configuration, not certified configuration resolution;
its random in-memory signing key is neither persisted nor emitted. FastAPI's
included-router contexts must be traversed: inspecting only top-level
`APIRoute` instances misses this installed version's routes. The test asserts
a nonempty HTTP inventory and forbids SQLite connections during capture.

### Current operations and actual implementation boundaries

All MCP symbols below live in `mnemo-server/mnemo_server/mcp/tools.py`.
The exact complete route list and DTO fields/defaults are in the snapshot.

| Operations | Handler / service and HTTP counterpart | Meaning |
|---|---|---|
| `query_notebook` | `_handle_query_notebook`, `services/query.py:QueryService.execute_query`; `routers/query.py:query_endpoint`, POST `/v1/query` | Canonical bounded retrieval, context and optional synthesis |
| `search_all_notebooks` | `_handle_search_all_notebooks`, `services/search.py:SearchService.execute_search`; POST `/v1/search` | Canonical ranked discovery, not exhaustive or image discovery |
| `query_notebook_v2` | `_handle_automatic_query_v2`, `AutomaticQueryV2ApplicationService.execute`; POST `/v2/retrieval/automatic` | One unambiguous notebook, server-planned sources, no generated answer |
| `search_evidence` | `_handle_search_evidence`, `EvidenceRetrievalApplicationService.execute`; POST `/v2/retrieval/evidence` | Explicit representations and one notebook scope, including document partitions |
| `query_structured` | `_handle_query_structured`, `StructuredRetrievalApplicationService.execute`; POST `/v2/retrieval/structured` | Typed dataset/version predicates and aggregates, not automatic NL grammar |
| `run_final_qa_v2` | `_handle_final_qa_v2`, `services/final_qa_v2.py`; POST `/v2/notebooks/{notebook_id}/final-qa` | Persisted governed evidence-based answer/publication/replay, distinct from search |
| `get_capabilities` | `_handle_get_capabilities`; GET `/v2/capabilities` | Scoped state/bounds, not authorization or certification inferred from class presence |
| `get_document`, `get_document_chunk`, `get_asset`, `get_image_analysis` | `_execute_delivery_tool`, `services/delivery.py`, `routers/delivery.py` | Exact version/chunk/occurrence delivery and derivation inspection; HTTP additionally exposes original/expand/evidence routes |
| `list_notebooks` | `_handle_list_notebooks`; GET `/v1/notebooks` | Bounded discovery, not unified search |
| `get_notebook_summary` | `_handle_get_notebook_summary`; GET `/v1/notebooks/{notebook_id}/summary` | Ancillary metadata |
| `get_source_insights` | `_handle_get_source_insights`; notebook insights routes are not an identical operation | Source-scoped MCP metadata; no assumed 1:1 HTTP parity |
| `get_timeline` | `_handle_get_timeline`; GET `/v1/notebooks/{notebook_id}/timeline` | Bounded timeline metadata |

HTTP additionally registers system/config/jobs, notebook CRUD/graph, sources,
sessions, notes, insights generation, streaming preview and V1 FinalQA. These
are inventoried, not renamed or deprecated. MCP has no matching mutation
tools. The snapshot records aliases such as `/health` and `/v1/health`.

### Frozen V1 details and observed drift

Sources: `schemas/query.py`, `schemas/search.py`, `services/query.py`,
`services/search.py`, `mcp/contracts.py`, `mcp/tools.py`.

- HTTP query: required normalized question (1..10000), optional notebook,
  context budget 8000, dense+sparse modes, top-k 20 (1..100), synthesis enabled,
  role `synthesizer`, max response tokens 1000. Response: answer, chunk-based
  citations and retrieval metadata. MCP requires notebook, defaults top-k 10
  and synthesize true; adds retained completeness/coverage/next-action envelope.
- HTTP search: normalized query, optional notebook, limit 20, optional top_k,
  dense+sparse, reranking enabled. Explicit limit/top_k synchronize; conflicting
  values fail validation. MCP defaults to 10, accepts legacy limit but top_k
  takes precedence when both are supplied. Do not silently “fix” this drift.
- Metadata filters: doc types, dates, source IDs. Inverted date interval is
  invalid. Modes are case-normalized dense/sparse/hybrid; unknown values fail.
  Parent/rerank configuration fields must not be confused with proof every
  implementation honors them: QueryService currently invokes reranking
  unconditionally, whereas SearchService checks enable_reranking.
- Shared V1 retrieval uses MultiSourceRetriever/RRF and optional provider
  reranking, canonical chunks and chunk citations, not OCR copied into V1 IR.
  Scores are existing fused/reranked values, not a new cross-modality scale.
  Persisted V1 models/interfaces and FinalQA marker/replay semantics are untouched.
- HTTP V1 adapters do not explicitly forward a principal to QueryService/
  SearchService; MCP forwards one when Full V2 is enabled. These services accept
  an optional principal; with one, they filter candidates before reranking and
  revalidate returned provenance. This is a real boundary difference, **not**
  proof of future indexed multi-user parity. UNINDEXED middleware blocks
  production before these paths. Do not expose the new contract via a legacy
  principal-optional helper.
- CentralAuthorizationService uses persistent grants when installed; legacy
  fixture callers may use existence/membership behavior without a grant
  authority. The proposed multi-notebook contract cannot inherit that fallback.

HTTP installs `AuthMiddleware`, CORS, production refusal middleware and
`errors.register_error_handlers`; dependencies include `get_engine`,
`get_server_config`, `get_token_counter` as captured per route.
HTTP UNINDEXED refusal is 503 with
`{"error":{"code":"PRODUCTION_CORPUS_UNINDEXED"}}`; other exceptions use
`ErrorEnvelope`/`TypedPublicError`, sanitized validation details and correlation
IDs. OpenAPI's auto-generated 422 schema is not proof of the custom runtime
error envelope. MCP dispatch uses `classify_public_error`, structured error
content and `isError`; direct tool execution raises to its caller.
`execute_mcp_tool` and `create_mcp_server` enforce production selection before
loading retrieval. Full-V2 dispatch rejects client policy overrides and
authorizes the declared scope. No guard was changed for this module.

## Consumer inventory and evidence grade

| Consumer / source | Operations/version | Evidence class | Migration sign-off |
|---|---|---|---|
| `scripts/verify_completed_stage_http.py` | V1 query, V2 retrieval/delivery/FinalQA | Repository HTTP harness; not rerun against deployment | Pending owner review |
| `scripts/verify_completed_stage_mcp.py` | V1 query, search_evidence, FinalQA/delivery | Repository MCP harness; no new live certification | Pending owner review |
| `mnemo-server/tests/test_mcp_transport_contract_matrix.py`, `mcp_contract_stdio_child.py`, `mcp_contract_sse_child.py` | Current tools over disposable transports | Test consumers, not independent external customers | Pending explicit sign-off; passing tests are not signatures |
| `test_server_query.py`, `test_server_search.py`, `test_mcp_tools.py`, `test_mcp_v1_v2_routing.py`, `test_mcp_immutable_schema_matrix.py` | V1 DTOs, retained tool schemas and routing | In-process/ASGI fixtures | Regression safeguards, no consumer approval inferred |
| `routers/retrieval_v2.py`, MCP handlers | Automatic/evidence V2 shared application services | Internal adapters | Retain pending versioned parity |
| `routers/structured_v2.py`, `routers/final_qa_v2.py` | Typed structured and FinalQA | Internal adapters | Retain pending parity |
| `mnemo-server/mnemo_server/cli.py`, `mcp/cli.py` | Server/transport entry points | Launchers, not independently observed search clients | No removal proposed |
| `mnemo-ui/src/App.tsx` | Existing frontend scaffold | No retrieval API call found in src scan | Future UI consumer, not migrated/certified |
| ADR-0076 controlled clients A/B | Historical HTTP+stdio / SSE harnesses | Exact retired-deployment evidence, explicitly not external organizations | Not sign-off for this new contract |
| External ChatGPT connection and unlisted third-party SDKs/clients | Unknown current version/use | Historical conversation is a lead, not fresh transport evidence | Unknown; owner must identify consumers before deprecation |

No independently maintained published SDK was identified from the inspected
entry points/client searches. This is a bounded repository observation, not
proof that no private consumer exists. The historical
[MCP audit](../operations/mnemo-mcp-failure-and-contract-audit.md) and
[retirement record](phase-8-9-runtime-cutover-execution.md) remain historical.
Unknown consumers block deprecation, not preservation of the current surface.

## Contract review package (historical proposal; accepted-design addendum below)

The [review schema](../../governance/proposals/phase8_9_1_scope_review.schema.json)
is generated from `schemas/scope_contract_review.py`; version
`mnemo.scope-review/1` is deliberately **not** a public operation/version.
It is not imported by serving adapters. Existing enums are reused rather
than redefining representation/status/completeness/error taxonomies.

| Requirement | Implemented review validation | Authority / remaining decision |
|---|---|---|
| Selected/all-authorized scope | Discriminated union; explicit nonempty unique notebook IDs; all-authorized forbids extra selection fields | Roadmap 8.9.1b/ADR-0080 proposal; authority resolver remains 8.9.2 |
| Exact document selection | Notebook/document/version tuples, unique, selected-notebook containment | ADR-0075 exact relationship principle; cross-store validation deferred |
| Hints omitted | None means automatic planning; explicit empty/duplicate/unknown representation rejected | ADR-0079 automatic behavior; source applicability/provider policy not implemented here |
| Limits/modes | Bounded strict integer limit, ranked/traversal, cursor length/nonblank checks | ADR-0058 bounds/completeness; numeric ceilings/defaults and mode spelling are review proposals, not an accepted public freeze |
| Source results | Reuse automatic statuses, searched-zero has a count; unsearched cannot masquerade as zero; applicable omissions require typed reason codes | ADR-0079 and 2026-10-21 accepted design |
| Ancestry | Notebook/source/document/version/generation/alias; discriminated chunk vs occurrence/asset/derivation vs dataset/row; locator/path/citation | ADR-0061–64, 0068, 0075; generic aggregate serialization remains a later implementation task |
| Coverage | Ranked cannot claim COMPLETE; terminal nonpartial traversal required for COMPLETE; returned <= examined | ADR-0058; runtime coverage correctness not established by a DTO |
| Errors | Existing ErrorCategory and correlation ID; no arbitrary echoed details | Existing typed_errors.py, ADR-0068/0073 safe disclosure |
| No authority injection | Extra fields rejected recursively by strict models | Accepted security boundary; parsing IDs never confers a grant |

The draft is intentionally incomplete as a serving contract. Missing/ambiguous
principal or unavailable membership authority must reject **before** resolution,
capability disclosure and retrieval; client IDs never substitute for authority.
The draft has no authorize/plan method and is never dispatched. Existing
production/scope rejection tests are rerun, not relabeled as future cross-notebook
authorization. A syntactically valid opaque cursor is not authenticated by the
schema. Later code must verify signature, expiry, replay/snapshot and bind
principal, effective scope, policy, representations, aliases, normalized query
and server limits, reauthorizing each page. Tampering/stale authority/context
must fail without silently restarting or widening scope.

### Independent contract-review remediation (2026-10-21)

This is review of an unregistered proposal, not acceptance of ADR-0080 or a
wire contract. The generated proposal was refreshed with the generator's
explicit review-only and replace flags. The current-surface snapshot was not
regenerated (SHA-256 remained
c6e9cee4982296a8692f6449b2da039d8b4761d7382b8f78244b15e6c1e0c83f).

| Reviewed rule | Classification | Schema / server-side disposition |
|---|---|---|
| Unique selected notebook IDs, unique representation hints | Structural | JSON Schema uniqueItems; existing Pydantic duplicate checks remain because schema parsing is not a serving boundary. |
| Nonblank bounded query and cursor | Structural | JSON Schema nonwhitespace pattern and lengths; runtime also normalizes the query. A shaped cursor is not authenticated. |
| Document/version belongs to selected notebook; duplicate document triples | Cross-field semantic | Request validator checks selected containment and duplicates. Persisted relationships and authorized membership require ADR-0075 resolution. |
| Cursor requires traversal; searched status iff matched count (including zero); returned <= examined | Cross-field semantic | Existing request, source, and coverage validators. Counts must also be verified against real execution. |
| Truncated iff continuation; cursor only in traversal; complete only terminal nonpartial traversal; empty returns zero; partial declares partial | Cross-field semantic | Coverage validator follows ADR-0058 and the existing result-set/transport cursor rules. DTO validation cannot prove exhaustion. |
| Returned count equals evidence count; unavailable/incomplete/failed/omitted source cannot coexist with complete or nonpartial coverage | Cross-field semantic | Response validator rejects these internally contradictory reports; applicability and mandatory-provider decisions still require runtime policy. |
| Principal/grants, source readiness, cursor signature/expiry/context, generation/citation integrity | Authorization/runtime | Requires authenticated context, policy/storage state, and existing cursor codec. A valid JSON document grants nothing. |

The proposed structured dataset-row variant requires complete
source/document/version/generation ancestry. That is supported specifically
for dataset-backed table rows: structured_table_projections references
document_versions and index_generations (mnemo-core/mnemo/storage/structured.py);
StructuredDatasetDescriptor carries notebook/source/document/version/generation
(mnemo-core/mnemo/models/structured_datasets.py). The structured V2 service
resolves and authorizes exact document/version scope before returning dataset
and row evidence (mnemo-server/mnemo_server/services/structured_v2.py).
Tests reject absent ancestry, but supplied IDs must still be checked against
persisted relationships. Generic StructuredResult records and groups have
candidate/evidence ancestry but no guaranteed single dataset or generation
per aggregate (mnemo-core/mnemo/models/structured_retrieval.py). Their public
aggregate/row identity contract remains unresolved. Never fabricate IDs.

Cursor validation has two gates. The proposal checks only token shape and
traversal mode. CursorCodecV2.decode (mnemo-core/mnemo/cursors.py) checks
signature, key, expiry, domain, binding, snapshot, and effective limits;
mnemo-core/tests/unit/test_cursors.py proves tamper, expiry, and binding
rejection. Existing mnemo-server/tests/test_retrieval_v2.py tests request
binding. Future unified continuation must bind principal, authorized scope,
query/selector, policy, representations, aliases, snapshot/generation, and
effective limits, and reauthorize every page. Invalid or stale cursors must
return safe typed invalid/expired/conflict outcomes without restarting or
widening scope. No unified multi-notebook runtime test exists yet because
that runtime is not implemented.

#### Canonical response versus transport field review

ADR-0073's envelope is a transport obligation, not a command to copy every
field into a new domain DTO. ADR-0058 RetrievalResultSetV1 and existing
EvidenceSearchResponse, CoverageResponseV2, and typed errors are the baseline.

| Field / semantic | Existing authority/model | Review representation and change | Owner / test / approval |
|---|---|---|---|
| Schema version, operation, opaque request ID | ADR-0073; EvidenceSearchResponse has all | Review has contract_version only; do not add dispatch identity | MCP/HTTP envelope; snapshot test; public naming/version approval pending |
| Items or typed singular resource | ADR-0073; EvidenceSearchResponse.items, DeliveryResponseBody | Review evidence is candidates, not an exact-delivery resource | Domain evidence to adapter items; delivery retained; parity pending |
| Authorized scope and source/document/version | ADR-0073/0075; resolver and item ancestry | Request selects scope; evidence has ancestry; no independently verified response scope summary | Shared service derives scope; existing single-notebook tests only |
| Provenance and citation | ADR-0080 proposal and accepted ancestry models | Typed identity, locator, retrieval path, citation; dataset-row variant narrow as above | Domain; review tests; aggregate format and persistence check pending |
| Completeness | ADR-0058 RetrievalResultSetV1; CoverageResponseV2 | Coverage rejects false terminal/cursor combinations, not false reported exhaustion | Domain truth and lossless adapter mapping; unified policy pending |
| Coverage, searched-zero, omissions | ADR-0058/0079; automatic decisions and EvidenceSearchResponse.coverage | Source status distinguishes searched-zero; typed omission reasons correspond exactly to applicable unavailable/incomplete/failed/budget-omitted source statuses | Domain reports to adapters; provider-specific readiness certification pending |
| Limits, query/snapshot identity | ADR-0058 result fingerprints; EvidenceSearchResponse.limits | Request limit and response counts; effective limits/snapshot not yet represented | Server-owned domain result, adapter exposure; wire review pending |
| Continuation cursor | ADR-0058/0073; CursorCodecV2, CoverageResponseV2 | Only truncated traversal may continue; token opaque | Domain continuation, transport passthrough; unified reauthorization pending |
| Recommended next actions | ADR-0073; existing V2 fields | Omitted, not fabricated | Adapter guidance using authorized identifiers only; vocabulary pending |
| Typed error envelope | ADR-0073; typed_errors.py and adapter handlers | SafeErrorReview has category/correlation, not full wire error | Separate transport response; parity review pending |

Ranked top-k is not exhaustive just because it has no cursor. Searched-zero
is not unavailable. Partial coverage must report applicable omissions or
unavailable sources honestly rather than claim COMPLETE. Neither MCP nor
HTTP mapping for this proposed unified contract is implemented or certified.

### Pre-acceptance approval analysis (historical, superseded by 2026-10-21 addendum)

No authoritative resolution superseding ADR-0080's proposed status was found.
The owner's implementation request explicitly preserves this approval gate.

| Decision | Recorded alternatives / impact | Required approval |
|---|---|---|
| Public operation names | Retained current names versus proposed search/POST /v2/search; structured split and optional image-discovery API | ADR-0080/schema review before registration (8.9.6) |
| Structured intent grammar | Existing exact typed operations versus later unambiguous NL translation; ambiguous intent must not guess | Contract review before 8.9.5b |
| Provider readiness policy | Existing ADR-0074 lifecycle/0079 compatible active sources versus yet-unreviewed unified mandatory/optional coverage policy | Review prior to unified planning |
| Dedup identity | Preserve membership and typed ancestry; do not blindly reuse single-notebook candidate identity for cross-notebook results | Review before fusion/traversal |
| Membership migration | Existing explicit grants are not approval for a multi-notebook state migration or an external resolver | Separate approval under 8.9.2a |
| Complete wire freeze | Review bounds, cursor wire semantics, typed aggregate evidence, safe errors and compatibility matrix | ADR-0080 acceptance and schema review; no invented sign-off |

#### Four ADR-0080 decisions prepared for architecture approval (historical)

These questions are not resolved by ADR-0079's authorization of the existing
single-notebook query_notebook_v2 operation. The owner/architecture ADR
acceptance process and reviewed versioned schema are required before a new
public operation or unresolved semantic policy is implemented. No sign-off is
inferred from repository tests.

1. **Public names — recommended, awaiting approval.** Question: which
   canonical MCP and HTTP names, if any, replace or supplement the retained
   single-notebook and exact-structured names? ADR-0073 requires additive,
   versioned transport contracts; ADR-0080 and roadmap 8.9.6 propose search
   and POST /v2/search plus optional structured discovery, while preserving
   V1 and existing V2. Current registry and HTTP snapshot contain none of
   those proposed names. Options: retain present names alone until parity,
   then add the proposed names; or approve a differently named additive
   version after consumer review. Recommendation: retain current names now,
   review the proposed additive pair only after shared-service semantics
   are frozen. A rename in place would break clients and could bypass
   authorization/coverage expectations. Required evidence: reviewed schema,
   MCP/HTTP parity, V1 snapshots, deployed transport traces, consumer
   inventory and explicit sign-offs. Approval: ADR-0080 design acceptance
   and public contract review before roadmap 8.9.6 registration.

2. **Structured intent grammar — recommended, awaiting approval.** Question:
   which natural-language requests may translate into exact typed
   structured predicates/joins/aggregates, and which must refuse as
   ambiguous? ADR-0073 retains query_structured as exact typed operation;
   ADR-0080 permits NL planning only with unambiguous exact semantics.
   Current structured V2 service executes explicit typed requests, not a
   unified NL grammar. Options: keep exact typed structured operations
   separately callable (recommended initial state), or later approve a
   strictly bounded grammar with ambiguity refusal and separately retained
   exact operations. Guessing filters would create fabricated rows or false
   completeness. Required evidence: grammar/negative fixtures, exact-value
   provenance, ambiguity rejection, structured-service parity, and client
   migration traces. Approval: ADR-0080 contract review before 8.9.5b.

3. **Provider readiness policy — unresolved.** Question: for each
   representation and query/scope, which sources are applicable and mandatory,
   and when is partial versus refusal required? ADR-0079 requires automatic
   applicable-source selection and honest per-source status; ADR-0058 forbids
   false completeness. Current automatic service maps searched, unavailable,
   failed and omitted decisions from its existing evidence service, with a
   distinct not-applicable state. Options supported by the architecture are
   fail-closed on unavailable mandatory sources, or return typed partial
   coverage where a source is optional; the mandatory/optional matrix is
   **not** accepted for unified multi-notebook search. Do not infer readiness
   from installed providers or treat unavailable as searched-zero. Required
   evidence: source applicability/readiness matrix by profile, fail/partial
   fixtures, coverage and latency budgets, authorization-before-disclosure
   tests, and external adapter parity. Approval: explicit ADR-0080 policy
   decision before unified planning; no recommendation on the unresolved
   mandatory/optional partition.

4. **Deduplication identity — unresolved.** Question: which stable evidence
   identity merges retrieval paths while preserving notebook membership,
   derivation/occurrence and dataset-row ancestry across notebooks?
   ADR-0080 requires membership survival; ADR-0058 requires deterministic
   result-set semantics. Current single-notebook advanced retrieval merges
   candidate_id only when authority keys match and raises on provenance
   collision (mnemo-core/mnemo/retrieval/advanced.py). Options: a scoped
   compound identity retaining all memberships, or separate per-notebook
   entries with shared underlying evidence and explicit association; blindly
   reusing candidate_id alone is unsafe. Both need a stable ordering/cursor
   story. Required evidence: shared-document and cross-notebook fixtures,
   authority-key collision, derivation/row variants, cursor stability,
   citation and grant revocation tests. Approval: ADR-0080 identity review
   before unified fusion/traversal; no accepted choice yet.

### Accepted design addendum (owner authorization 2026-10-21)

The preceding decision questions are preserved as their pre-approval review
history. ADR-0080 now accepts these four design answers; this addendum is the
current contract interpretation, not a record of external-client consent.

| Gate | Accepted choice and rationale | Compatibility/security boundary | Rejected alternative |
|---|---|---|---|
| Public names | Additive MCP search and HTTP POST /v2/search are intended for 8.9.6a, not registered here; exact structured/discovery names remain optional separate review | V1 and retained V2 names/defaults unchanged; no client identifier grants scope | In-place rename, early registration, mandatory search_images |
| Structured grammar | Existing strict typed describe/query/union/join AST only; no NL translation or guessed joins | Exact authorized dataset/version scope and server-owned authority; invalid shape or ambiguity fails safely | Free-form SQL, inferred exact predicates, semantic approximate arithmetic |
| Readiness | Authenticate first; searched-zero only after a real compatible active ready search; degraded applicable sources produce typed partial omissions; no searched source or required exact projection fails closed | Missing authority/identity never becomes partial success; evaluation readiness is not production evidence | Provider-installed-is-ready, unavailable-is-zero, false COMPLETE |
| Deduplication | Type-specific equivalence within a notebook/source/document/version/generation/alias and exact locator/citation; different notebook memberships remain distinct | All retrieval paths retained on later merge; payload/ancestry collision is integrity failure; citations remain notebook-qualified | Content similarity or candidate UUID as global authority |

The equivalence helper in the unregistered review model returns a key but
does not authorize, merge or deduplicate live candidates. Fixtures cover
canonical, derived and structured variants, same-text/different-source and
cross-notebook/version/generation distinctions. Structured grammar fixtures
exercise existing public typed DTO validation, not a new natural-language
planner. Source/readiness fixtures check honest searched-zero and omission
relationships; they do not certify any live provider.

The versioned design schema is frozen as the Module 8.9.1 review contract.
It is still stored under governance/proposals to preserve its generation
history and deliberately contains no registered operation. A later public
wire schema and MCP/HTTP mapping require the shared-service and adapter tasks.
Authorization, cursor signature/expiry/context and every continuation-page
reauthorization are server-runtime obligations, not guarantees of JSON Schema.
The field matrix above assigns domain versus adapter ownership without
claiming deployed parity.

Consumer migration sign-off requires an identified owner and client/version,
the exact old/new operation and schema revision, representative authorized
request/response/error/continuation traces on each used transport, explicit
owner acceptance and rollback route. Internal repository scripts and fixtures
are regression consumers, not external signatories. The repository scan found
the HTTP/MCP verification scripts, in-process and transport test clients and
no current UI retrieval call; any external ChatGPT or third-party consumer
remains unknown. No sign-off record exists. Thus migration policy is
repository-complete but 8.9.1c's consumer-sign-off exit remains PARTIAL.

| 8.9.1 exit criterion | Design/implementation | Tests | Approval | Consumer sign-off | Status / blocker |
|---|---|---|---|---|---|
| 8.9.1a versioned current surface and frozen V1 defaults | Snapshot records 15 MCP/54 HTTP operations; no new names | Snapshot and V1 default assertions pass | Existing accepted V1 ADRs | External consumers unknown, no migration requested yet | PASS for repository inventory |
| 8.9.1b scope/evidence design, schema and compatibility matrix | Versioned review DTO/schema, typed provenance/omissions, result-set and cursor boundaries; runtime integration deferred | Focused contract/structured/cursor tests | ADR-0080 owner-accepted design 2026-10-21 | Not an exit requirement for design-only freeze | PASS for design freeze, not serving parity |
| 8.9.1c reversible migration/deprecation and sign-off | Policy and rollback documented; no deprecation performed | Registration snapshot safeguards pass | Owner-approved policy | No identified external owner sign-off; unknown clients not invented | PARTIAL: real consumer sign-off pending |
| Cross-cutting full-suite stability | No contract-related failure identified in the four transport timeouts | Latest final-file full run and transport-order reproduction recorded below | Not applicable | Not applicable | PARTIAL until a full run passes and timeout cause is established or corrected |

No Module 8.9.2a membership work or Phase 8.9 production serving follows
automatically from this accepted design. Next roadmap task remains 8.9.2a
only after the module's actual entry/exit and external-evidence gates are met.

## Compatibility matrix and reversible migration

| Surface | Current → proposed | Allowed now | Removal gate |
|---|---|---|---|
| V1 query/search and persisted IR | Frozen → unchanged | Snapshot and regression tests only | No semantic change authorized |
| query_notebook_v2 / automatic | Single notebook → shared authorized scope | Retain adapter and schema | Approved version/parity and actual consumer migration |
| search_evidence / evidence | Explicit expert query → shared semantics where compatible | Retain | Same |
| query_structured / structured | Exact typed query → optional search_structured/describe_datasets | Retain; no proposed registration | Exact-operation parity and consumer evidence |
| Exact delivery and metadata/capabilities | Retain recovery/discovery | Preserve names and authorized semantics | Separate approved change, not a search replacement |
| FinalQA V1/V2 | Retain → possible authorized snapshot consumption | Preserve deadline, replay, publication and citation controls | Grounding/parity/consumer evidence |

1. Preserve current schemas, handlers, adapters and UNINDEXED gate. Capture
   versioned inventory and independently rerunnable regressions (this change).
2. Preserve the owner-accepted ADR/design-schema decision; obtain later
   public adapter schema reviews and per-consumer sign-offs referencing exact
   schema revision, operations, owner, client version, date and transport traces.
   Empty/unknown sign-off means pending, never implied consent.
3. Implement subsequent roadmap modules in their existing order, using one
   shared service; shadow comparisons only on authorized disposable or separately
   approved data. No public names enabled by this record.
4. Introduce an approved additive version only after authorization, provenance,
   coverage/error and transport parity evidence. Keep old adapters available.
5. Offer documented opt-in migration and rollback to retained compatible
   adapters. Rollback never restores revoked credentials, retired indexes or an
   unsafe principal-optional production path.
6. Deprecation requires all known consumers migrated, unknown-consumer risk
   explicitly resolved, published guidance, owner approval and retained replay
   compatibility. No removal date is invented here.

Rollback triggers: changed frozen defaults/schema/IR, authorization or
provenance leak, cursor scope mismatch, mandatory-source omission, transport
divergence or missing sign-off. Disable only the new version, preserve data and
evidence, invalidate its continuations through the governed lifecycle, retain
UNINDEXED when no authorized serving state exists. No data migration or
deprecation is executed in this module.

## Validation and protected state

Tests use disposable fixtures or pure schemas; snapshot capture never enters
application lifespan.
No public registry, runtime selection, stored IR, data or credentials were
modified. The review schema does not implement Module 8.9.2 or 8.9.3.

**Verification completed 2026-10-21 (local Windows checkout):**

| Command/check | Result |
|---|---|
| `.venv/Scripts/python.exe -m pytest -q -o addopts='' mnemo-server/tests/test_module_891_contracts.py --junitxml=scratch/module891-schema-final.xml` | Exit 0, 45 passed, 1 `.pytest_cache` ACL warning. Diagnostic run disables the configured coverage options; not the coverage gate. |
| Focused Module 8.9.1/MCP/scope/production/error group, `-o addopts=''`, JUnit `scratch/module891-focused.xml` | Exit 0, 167 passed, 1 cache warning. The last added response case is included in the 45-test run above, not this earlier group. |
| `MNEMO_CI=1 .venv/Scripts/python.exe -m pytest -q --junitxml=scratch/module891-regression.xml --cov-report=xml:scratch/module891-coverage.xml` (environment variable set in PowerShell before invoking pytest) | Exit 0, **3,142 passed, 18 skipped, 0 failed**, 9 warnings; combined statement/branch coverage **90.21%** against 90%. The CI setting selects the repository's existing skip policy for local-database cases; it does not alter the production selector. The final extra response case was added after collection and passed in the separate 45-test run. |
| `.venv/Scripts/python.exe -m ruff check .`, `-m ruff format --check .` | Exit 0; 591 files already formatted. |
| `.venv/Scripts/python.exe -m mypy --strict --explicit-package-bases scripts/snapshot_public_contracts.py mnemo-server/mnemo_server/schemas/scope_contract_review.py mnemo-server/tests/test_module_891_contracts.py` | Exit 0; 3 source files. |
| `.venv/Scripts/python.exe -m mypy --strict mnemo-core/mnemo mnemo-server/mnemo_server plugins/email-ingestion/email_ingestion` | Exit 0; 314 source files. |
| `.venv/Scripts/python.exe -m compileall -q` on those three source packages and the two new Python files | Exit 0. |
| `git diff --check`, targeted relative-link scan, ADR number scan | Exit 0; 56 links checked, none broken; no duplicate ADR numbers. |

Snapshot-generation first failed because a production-like constructor required
a nondefault cursor signing secret. The utility now supplies an ephemeral,
unpublished value and never enters lifespan. Initial focused tests then had
2 failures because the snapshot had not been generated. After that fix, the
44-test focused run passed; the final 45-test run includes the added response
case. An initial changed-file mypy invocation hit a duplicate-module mapping;
the repository's `--explicit-package-bases` mode and both commands above
passed. These diagnostic failures were resolved before the broad run.

Initial read-only checks: five retired DB file hashes match their post-reset
receipts; registry has no active generation and state REVOKED; credential-file
SHA-256 `860e3166812c9b859945c5a58a149153f4a1cfd77fb1bb05754c6a08c2863a71`.
Production selector is UNINDEXED. No matching certified-tunnel-stdio process
was found; scratch GPU environment absent. These are local point-in-time
observations, not proof of every external launcher.

**Post-test read-only comparisons:** all five retired DB file hashes and all
five recovery-snapshot hashes equal their receipt `after_sha256` and
`snapshot_sha256` values. The registry file SHA-256 remains
`860e3166812c9b859945c5a58a149153f4a1cfd77fb1bb05754c6a08c2863a71`;
it has no active generation and reports REVOKED. `verify_source_manifest`
read original bytes and returned 44/44 and 24/24. The selector is UNINDEXED,
`data/notebook_runtime/mnemo.db` absent, zero matching tunnel processes in a
local scan, `.venv/Scripts/python.exe` present, scratch GPU venv absent.
Initial Git status was clean; final status lists only the eight files created
or modified by this task, with no staged changes. The previously committed
top-level `goldenDataset/` deletions were not restored. No external transport,
indexed-serving, Phase 8.9 certification or consumer sign-off was attempted.

### Contract-review remediation verification (2026-10-21)

The preceding results are historical. This follow-up began with the two
modified architecture/roadmap files and six untracked Module 8.9.1 artifacts.
It changed only the review model/test, generated review schema, snapshot
generator, this report, and roadmap. The architecture edit was preserved.
No file was staged or committed. The current public-surface snapshot was
not regenerated; its SHA-256 remained
c6e9cee4982296a8692f6449b2da039d8b4761d7382b8f78244b15e6c1e0c83f.

| Command/check | Actual result |
|---|---|
| .venv/Scripts/python.exe -m pytest -q -o addopts='' mnemo-server/tests/test_module_891_contracts.py | Baseline exit 0, 45 passed; final exit 0, 60 passed, 1 local pytest-cache ACL warning. |
| Main-interpreter pytest -q -o addopts='' on Module 8.9.1, retrieval V2, structured V2, scope authority, MCP routing/transport/tools, typed errors, core cursor and scope-authorization files | Exit 0, 193 passed, 1 local pytest-cache ACL warning on final files. |
| MNEMO_CI=1 .venv/Scripts/python.exe -m pytest -q --junitxml=scratch/module891-review-junit.xml --cov-report=xml:scratch/module891-review-coverage.xml | Exit 0, 3,156 passed, 18 skipped, 9 warnings, coverage 90.19% >= 90%; started before final response validator and two tests. |
| MNEMO_CI=1 .venv/Scripts/python.exe -m pytest -q --junitxml=scratch/module891-review-final-junit.xml --cov-report=xml:scratch/module891-review-final-coverage.xml | **Exit 1**, 3,154 passed, 4 failed, 18 skipped, 10 warnings; coverage 90.19% >= 90%. Four ordered-text real-transport cases (stdio and SSE, older/newer) timed out at transport initialization. No full-suite pass is claimed. |
| MNEMO_CI=1 .venv/Scripts/python.exe -m pytest -q -o addopts='' mnemo-server/tests/test_ordered_text_certification.py | Exit 0, the same 4 cases passed alone in 152.84s. Full-run timeout cause remains unresolved; no timeout or test assertion was weakened. |
| .venv/Scripts/python.exe -m ruff check .; .venv/Scripts/python.exe -m ruff format --check . | Both exit 0; 591 files formatted. |
| .venv/Scripts/python.exe -m mypy --strict --explicit-package-bases scripts/snapshot_public_contracts.py mnemo-server/mnemo_server/schemas/scope_contract_review.py mnemo-server/tests/test_module_891_contracts.py | Exit 0, 3 files. One narrow import-untyped annotation in the test for jsonschema's unavailable stubs; no global relaxation. |
| .venv/Scripts/python.exe -m mypy --strict mnemo-core/mnemo mnemo-server/mnemo_server plugins/email-ingestion/email_ingestion | Exit 0, 314 source files. |
| Main-interpreter compileall -q on those three packages, generator and review test; git diff --check | Both exit 0. |
| Relative-link check on this report and roadmap | Exit 0, 28 links, none broken. |

Generated-schema inspection confirms the nonwhitespace and uniqueItems
constraints; focused fixtures exercise schema/runtime agreement and semantic
validation that standalone schema cannot provide. The new review-only
generator flag preserved the explicit replacement safeguard without touching
the current public-surface inventory. No proposed operation was registered.

Post-run read-only checks: 5/5 retired database SHA-256 values match their
post-decommission receipts and 5/5 recovery snapshots match. The credential
registry SHA-256 remains
860e3166812c9b859945c5a58a149153f4a1cfd77fb1bb05754c6a08c2863a71,
with no active generation and the historical generation REVOKED. Source
verification returned 44/44 and 24/24. Selector remains UNINDEXED; runtime
database absent; main .venv present; scratch GPU preflight venv absent; local
split-token process scan found zero matching tunnel processes. These are
point-in-time observations, not proof about every external launcher.

**Exit:** 8.9.1a PASS (repository inventory); 8.9.1b PARTIAL (ADR-0080,
schema/public-contract approval and structured/provider/dedup choices still
pending); 8.9.1c PARTIAL (consumer sign-offs and external transport evidence
absent); Module 8.9.1 PARTIAL. The final full-suite transport timeouts are an
additional unresolved verification issue despite the isolated and earlier
broad passes. Module 8.9.2a and production activation were not started.

### Owner-approved design and transport follow-up (2026-10-21)

The preceding exit paragraph is the historical pre-approval result. The
owner's subsequent instruction authorized all four ADR-0080 design choices;
the accepted decision addendum and current exit table above supersede that
paragraph. No public operation was registered, and the versioned current
surface snapshot still has SHA-256
c6e9cee4982296a8692f6449b2da039d8b4761d7382b8f78244b15e6c1e0c83f.

The four full-run failures in the prior JUnit were ordered-text stdio/SSE
initialization timeouts, not retrieval assertions: stdio awaited initialization
for 15 seconds and SSE awaited its PORT announcement for 30 seconds. The
children constructed analysis, capability, structured, FinalQA and multilingual
fixtures before opening either transport, even for an ordered-text-only test.
The ordered mode now provisions only its required base and ordered fixtures;
the regular transport mode still provisions all prior optional fixtures.
No timeout, assertion, production path or authentication rule was changed.
This is a supported cause of startup latency, not a claim that timing can
never vary on another host.

| Check | Actual result |
|---|---|
| Baseline contract test, before this follow-up: main-interpreter pytest -q -o addopts='' on test_module_891_contracts.py | Exit 0, 60 passed; local pytest-cache ACL warning. |
| Final contract test after schema/decision fixtures | Exit 0, 66 passed; same cache warning. |
| Focused contract, retrieval V2, structured V2, MCP, scope, error and cursor tests | Exit 0, 199 passed; JUnit scratch/module891-accepted-focused-junit.xml. |
| Paired MCP transport matrix and ordered-text tests after child fixture scoping | Exit 0, 10 passed in 118.41 seconds; JUnit scratch/module891-transport-order-after-junit.xml. All four ordered-text stdio/SSE older/newer cases passed. |
| MNEMO_CI=1 with main interpreter: pytest -q --junitxml=scratch/module891-accepted-full-junit.xml --cov-report=xml:scratch/module891-accepted-full-coverage.xml | **Exit 0, 3,164 passed, 18 skipped, 0 failed, 9 warnings, 90.21% combined coverage against 90% minimum**, 626.35 seconds. JUnit reports 3,182 collected, zero failures/errors. The four previously failing cases passed in 16.303, 17.301, 18.793 and 27.145 seconds. |
| Main-interpreter ruff check . and ruff format --check . | Exit 0; all lint checks passed, 591 files already formatted. |
| Main-interpreter mypy --strict on mnemo-core/mnemo, mnemo-server/mnemo_server and plugins/email-ingestion/email_ingestion | Exit 0; 314 source files. |
| Main-interpreter mypy --strict --explicit-package-bases on the snapshot generator, review model/test and both transport children | Exit 0; 5 files. |
| Main-interpreter compileall -q on the three source packages and changed Python files; git diff --check | Both exit 0. |

The nine warnings include third-party deprecations, fixture warnings and one
local pytest-cache ACL warning; no test failure is hidden. The full-suite
result replaces, but does not erase, the earlier failed run. Local transport
tests are not deployed external-client parity evidence.

Post-run read-only checks: the five retired DB hashes and their five recovery
snapshot hashes still match the 2026-10-10 receipts. Original-byte source
manifest verification returned 44/44 and 24/24. Production selection remains
UNINDEXED, the runtime DB is absent, the credential-registry SHA-256 is still
860e3166812c9b859945c5a58a149153f4a1cfd77fb1bb05754c6a08c2863a71,
its active generation is null and one historical generation is REVOKED. A
local process scan found zero matching tunnel processes. The main .venv is
present and the former GPU-preflight venv absent. These are point-in-time
local observations; no protected store was opened for mutation.

**Pre-amendment exit:** 8.9.1a PASS (versioned repository inventory); 8.9.1b PASS
for approved design/schema/negative fixtures, with runtime implementation
deliberately assigned to later roadmap modules; 8.9.1c PARTIAL because no
external consumer sign-off or deployed parity evidence exists. Module 8.9.1
is PARTIAL. The next roadmap task remains 8.9.2a; it was not started. Neither
the green full suite nor design approval certifies indexed production serving.

### Internal-verification boundary and proposed formal-exit clarification (2026-10-21; pre-amendment record)

The project owner confirmed that the ChatGPT MCP tunnel is intentionally
disconnected and that the consumer UI build is unavailable. This instruction
authorizes local protocol and server-client verification; it does **not** amend
the roadmap's required evidence. The exact Module 8.9.1 exit is a reviewed,
versioned search/scope/evidence/error contract with inventoried consumer
migration. Its task table requires, for 8.9.1c, **consumer sign-off and a
reversible migration plan**. ADR-0080 accepts design choices but explicitly
does not supply external-client sign-off. ADR-0080's deployed HTTP/external MCP
gate belongs to Phase 8.9 GO, not an additional 8.9.1 local-test requirement.

| Formal criterion | Current evidence | Internal result | Formal status / limitation |
|---|---|---|---|
| 8.9.1a: live MCP registry, FastAPI routes, defaults, external-consumer inventory, frozen V1; versioned snapshots | The unchanged current-surface snapshot has 15 MCP and 54 HTTP method/path operations; inventory names actual repository scripts, test clients and adapters. V1 MCP top_k=10 versus HTTP top_k=20 is retained. External clients are explicitly unknown, not invented. | Snapshot and retained-operation/default regressions passed in the 181-test local run. | **PASS for bounded repository-evidenced inventory.** It does not assert exhaustive discovery of private external clients. |
| 8.9.1b: approved versioned V2 scope/evidence/error design, schema review, compatibility matrix and invalid fixtures | Owner-accepted ADR-0080 addendum, review DTO/schema, field-by-field matrix, structural and semantic negative cases, cursor syntax versus signed-runtime boundary. | Contract/structured/cursor fixtures passed locally; no public name was registered. | **PASS for design freeze.** Later shared-service/adapters and production certification are not claimed. |
| 8.9.1c: retain existing names, govern reversible migration/deprecation; consumer sign-off plus plan | Current-to-target table, rollback/deprecation gates, exact sign-off requirements, identified repository consumers and unknown external consumers. | Registration and protocol compatibility tests passed; no old operation removed. | **PARTIAL.** Plan passes; no actual consumer migration or sign-off exists. The formal required-evidence column remains unsatisfied. |
| Cross-cutting local transport stability | Prior failed full JUnit had four stdio/SSE initialization timeouts. Ordered-only children no longer provision unrelated optional fixtures before transport readiness. Subsequent coverage-enabled full JUnit has those four passing; direct protocol matrix passes again below. | Local HTTP test-client, direct MCP, real loopback stdio and SSE cases pass. | **PASS for current local behavior only.** No deployed ChatGPT tunnel or UI parity is inferred. |

The new targeted command was run from the repository root with the main
interpreter and MNEMO_CI=1:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -o addopts='' mnemo-server/tests/test_module_891_contracts.py mnemo-server/tests/test_production_runtime_selection.py mnemo-server/tests/test_mcp_principal.py mnemo-server/tests/test_mcp_route_contracts.py mnemo-server/tests/test_mcp_v1_v2_routing.py mnemo-server/tests/test_mcp_transport_contract_matrix.py mnemo-server/tests/test_server_query.py mnemo-server/tests/test_server_search.py --junitxml=scratch/module891-internal-boundary-junit.xml
```

Exit 0: **181 passed, 0 failed, 0 skipped**, two warnings (one SDK
deprecation and one local pytest-cache ACL warning), 101.55 seconds. The JUnit
records the actual HTTP request and MCP dispatch rejection of an injected
legacy engine, two HTTP/public-MCP V2 fixture cases, four direct/stdio cases,
and four loopback SSE cases. The explicit addopts override makes this a
focused diagnostic run, not a coverage-gate substitute. The earlier
coverage-enabled full run on this implementation was exit 0, 3,164 passed,
18 skipped, 90.21% combined coverage; its JUnit and coverage XML paths are
recorded immediately above. No full suite was rerun for this clarification.

| External check | State | Prerequisites for later verification |
|---|---|---|
| External ChatGPT MCP connection against the eventual indexed deployment | **DEFERRED — ENVIRONMENT UNAVAILABLE** | Separately authorized tunnel restart, valid non-revoked deployment authority, an approved indexed runtime, authenticated client, exact schema/version and request/error traces. None is created here. |
| Consumer UI against deployed HTTP endpoints | **DEFERRED — ENVIRONMENT UNAVAILABLE** | Available UI build and deployment, authenticated client, approved indexed runtime and exact request/error traces. In-process HTTP tests cannot substitute for this. |
| Actual migration/sign-off by any identified external consumer | **DEFERRED — ENVIRONMENT UNAVAILABLE** | Identify the consumer owner and client/version, publish and implement the approved new operation in its later module, obtain migration/rollback traces and dated explicit sign-off. The new operation is not registered today, so no consumer can yet migrate to it. |

**Proposed governance clarification for explicit owner review, not an enacted
roadmap change:** revise only 8.9.1c's required-evidence cell from
“Consumer sign-off and reversible migration plan” to “Versioned repository
consumer inventory, owner-reviewed reversible migration/deprecation plan and
per-consumer sign-off protocol; actual consumer migration/sign-offs gate
public cutover or deprecation in 8.9.6/8.9.8 and remain mandatory before
removing an old operation.” Also clarify 8.9.1a's external-consumer inventory
as “identified consumers plus explicitly unknown external consumers and a
discovery action,” since an unavailable private client cannot be enumerated
from this repository. This would allow an internally complete contract module
without waiving later external parity, consumer acceptance or Phase 8.9 GO.
Until the owner explicitly approves that formal roadmap amendment, the
existing sign-off criterion stands and Module 8.9.1 remains **PARTIAL**.

Final read-only comparisons after the focused run: all 5/5 retired database
hashes and 5/5 recovery snapshots still match their execution receipts;
source-manifest verification again returned 44/44 and 24/24. The selector is
UNINDEXED, runtime database absent, credential-registry hash unchanged with
null active generation and one REVOKED generation, and a local process scan
found no matching tunnel process. The main .venv remains present and the
GPU-preflight venv absent. Repository-wide Ruff lint and format, strict mypy
on 314 source files, and git diff --check exited 0; this report's seven
relative links resolve. No file was staged or committed. These checks do
not establish that an unknown external launcher cannot exist.

### Formal owner-approved sign-off milestone amendment (2026-10-21)

The project owner explicitly approved the preceding proposed **milestone
change**, not an exception to consumer acceptance. The authoritative roadmap
8.9.1c required-evidence cell previously read: “Consumer sign-off and
reversible migration plan.” It now requires: “Versioned consumer inventory,
reviewed reversible migration/deprecation plan and sign-off protocol, plus
internal contract/compatibility verification. Actual per-consumer migration
sign-offs gate later public cutover/deprecation, not this design-stage exit.”
The roadmap also keeps approved public names unregistered at this stage and
adds a mandatory future public cutover/deprecation gate under 8.9.6.

That later gate requires identification of affected consumers to the approved
scope, testing each actual integration, recorded consumer-owner sign-offs or
a specific formally approved governance exception, compatibility and rollback,
and deployment-specific evidence. Unknown consumers have **no blanket
exception**; existing operations remain compatible until their applicable
discovery and deprecation requirements pass. Local schema, HTTP test-client
and MCP protocol tests are not a substitute for consumer acceptance or the
independent transport evidence of 8.9.8.

| Amended Module 8.9.1 criterion | Status | Evidence and limit |
|---|---|---|
| 8.9.1a — versioned current MCP/HTTP/default/V1 surface and bounded consumer inventory | **PASS** | Current-surface snapshot records 15 MCP and 54 HTTP method/path operations; V1 MCP top_k=10 and HTTP top_k=20 remain distinct; repository scripts, test clients and adapters are identified, while private external clients are expressly unknown. Snapshot and compatibility fixtures passed in the 181-test local run. |
| 8.9.1b — owner-approved versioned scope/evidence/error contract design, schema/compatibility review and invalid-input fixtures | **PASS for design** | ADR-0080's four accepted choices, review schema/DTO, field matrix and contract fixtures; the focused 66-test contract run, 181-test internal boundary run and earlier green full suite include the relevant checks. Shared runtime and public adapter implementation are later modules, not silently credited here. |
| 8.9.1c — inventory, reversible plan, compatibility/deprecation and sign-off protocol, internal verification | **PASS under amended criterion** | Consumer table and migration sequence above; rollback triggers and no-removal rules; owner-approved roadmap gate; unchanged public surface and local HTTP/MCP protocol tests. Actual per-consumer sign-offs are later-gate requirements, not waived or represented as obtained. |
| Module exit — reviewed versioned contract with inventoried consumer migration | **COMPLETE for Module 8.9.1 design/governance only** | All amended mandatory 8.9.1a–c criteria above pass. This is neither Phase 8.9 GO nor indexed-serving, deployed transport or consumer-migration certification. |

This documentation-only amendment reran the contract, production-selection,
V1/V2 routing and MCP route fixtures with the main interpreter and
MNEMO_CI=1: pytest -q -o addopts='' on test_module_891_contracts.py,
test_production_runtime_selection.py, test_mcp_v1_v2_routing.py and
test_mcp_route_contracts.py, with JUnit
scratch/module891-governance-amendment-junit.xml. **Exit 0, 97 passed,
0 failed, 0 skipped, one local pytest-cache ACL warning** in 5.75 seconds.
The addopts override makes this a focused diagnostic run, not the configured
coverage gate. The 181-pass internal transport/client run above is earlier
evidence, not a new execution in this amendment task. No Python implementation
or test file changed here. The earlier coverage-enabled full run (3,164
passed, 18 skipped, 90.21%) remains historical evidence and was **not rerun**
for these documentation-only edits. The disconnected ChatGPT MCP tunnel,
unavailable deployed HTTP UI and actual per-consumer acceptance dependent on
them remain **DEFERRED — ENVIRONMENT UNAVAILABLE**, with prerequisites in the
preceding table. Completion here does not authorize starting 8.9.2a.

Amendment-task final checks: Ruff lint exited 0 (“All checks passed!”), Ruff
format check exited 0 (“591 files already formatted”), git diff --check
exited 0, and 29 relative links in the roadmap and this report resolved.
Read-only protected-state checks found 5/5 retired DB and 5/5 recovery
snapshot hashes matching the receipts, source manifests verifying 44/44 and
24/24 original files, UNINDEXED selection, absent runtime DB, unchanged
credential-registry hash with no active generation and one REVOKED generation,
zero matching local tunnel processes, main .venv present and the former GPU
venv absent. No runtime or source asset was modified for this amendment; no
file was staged, committed or pushed.
