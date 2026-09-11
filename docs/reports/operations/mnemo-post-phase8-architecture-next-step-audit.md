# Mnemo Post-Phase-8 Architecture Next-Step Audit

**Audit status:** `DECISION_GRADE_AUDIT_COMPLETE`  
**Recommendation:** `RECOMMEND_MINIMAL_ARCHITECTURAL_PREPARATION_THEN_PHASE_9`  
**Date:** 2026-09-08  
**Method:** Read-only repository, ADR, roadmap, Git-history, configuration, database, test, and runtime inspection

## 1. Executive Verdict

Mnemo should **not implement full four-store persistence now**. Qdrant and SurrealDB are not Phase 9 dependencies, no accepted ADR mandates four-way replication, and enabling them would add synchronization, lifecycle, infrastructure, and recertification work without serving the Phase 9 browser workflow.

Mnemo is nevertheless not ready to connect the complete Phase 9 workflow directly to the current certified production profile without two bounded preparations:

1. resolve the conflict between the immutable, SHA-bound certified corpus and the existing writable notebook/upload endpoints; and
2. choose an authenticated certified chat transport, because the current WebSocket route is legacy V1, accepts before principal validation, and is not covered by the HTTP authentication middleware.

These are real Phase 9 boundary issues. They are **not** reasons to introduce Qdrant or SurrealDB. Once resolved, Phase 9 should proceed on the current filesystem + SQLite topology.

## 2. Current Certified State

### Facts verified directly

| Item | Current result | Evidence |
|---|---|---|
| Production DB | 44 documents, 44 versions, 44 memberships, 2,658 chunks; integrity `ok`; FK 0; WAL 0 | Immutable SQLite inspection |
| Production DB SHA | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | `Get-FileHash` |
| Production identity | `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d` | production manifest and signed certification |
| V2 exposure | true | `config/production/full_multilingual_v2.production.json` |
| Reranker | durable `BGE_V2_M3`, exact governed revision | durable activation record |
| Lifecycle | DECLARED through CERTIFIED all true | `WP17CertificationAuthorityV1` signed state |
| Phase 8.5 notebook | SHA `bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84`; 44/44/44/2,658; ready | notebook manifest and registry |
| Phase 8.6 notebook | SHA `9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2`; 24/24/24/5,843; ready, evaluation-only | notebook manifest and registry |
| Qdrant runtime | disabled; no process/listener observed | `mnemo.toml`, process/port inspection |
| SurrealDB runtime | disabled; no process/listener observed | `mnemo.toml`, process/port inspection |
| Tunnel client | process present | process inspection |
| Live Mnemo HTTP/MCP process | not attributable at audit instant | process/port inspection |

The persisted production exposure and certification are valid evidence of the certified state. They are not evidence that an HTTP/MCP server happened to be listening at the audit instant; this audit does not claim live availability.

### Project-stage determination

- Phases 0–8 are implemented and recorded complete.
- Phase 8.5 is actually complete and certified under accepted ADR-0076 and the signed WP-17 state.
- Phase 8.6 is a validated evaluation notebook, not a production phase or production corpus promotion.
- Phase 9 implementation is not underway beyond the original Vite/React scaffold. `mnemo-ui/package.json` has React/Vite/Vitest but not the planned React Router or TanStack Query dependencies, and the Phase 9 checklist remains unchecked.

The master roadmap line saying Phase 8.5 is “IMPLEMENTATION ACTIVE” with later work packages open is stale. Accepted ADR-0076, the signed certification record, current certification report, and executable manifest are newer and more authoritative.

## 3. Current Storage Topology

```text
content-addressed filesystem
  └─ original and derived asset bytes

immutable production SQLite corpus
  ├─ documents / versions / memberships
  ├─ chunks and provenance
  ├─ FTS5 projections
  ├─ multilingual BGE-M3 vector generations
  ├─ OCR / Vision / structured projections
  └─ authorization and evidence identities

separate mutable operational SQLite
  └─ FinalQA executions / snapshots / transitions / citations

Qdrant   = disabled, outside current V2
SurrealDB = disabled, outside current V2
```

`ProductionFullMultilingualV2ServerDependencyAssemblerV1` validates the governed database and creates `SQLiteV2ReadOnlyRuntimeStore`. That class opens SQLite with `mode=ro&immutable=1` and `PRAGMA query_only=ON`. The assembler binds the same store as the authorized source enumerator, evidence resolver, embedding store, and text store.

`AuthorizedMultilingualDenseRetrievalV2` enumerates authorized vectors from SQLite and executes exact cosine scoring in process. `MultilingualSparseRetrieverV2` uses SQLite projection/FTS behavior. No Qdrant or SurrealDB object appears in this production V2 call path.

## 4. Four-Store Audit

| Store | Completeness | Current role | Authority | Lifecycle/rebuildability | Required by V2? | Future role |
|---|---|---|---|---|---|---|
| Filesystem | Complete | Content-addressed original/assets | Canonical bytes | Immutable content-hash identity | Yes | Continues unchanged |
| SQLite | Complete and extensive | Canonical relational state, chunks, FTS5, V2 vectors, multimodal provenance | Authoritative corpus | Additive schemas and governed generations; immutable in certified V2 | Yes | Remains authority even if indexes move |
| Qdrant | Functional V1 adapter | Disabled | Derived only | Historically rebuildable projection; no V2 generation authority | No | ANN scale/Phase 13 candidate |
| SurrealDB | Partial graph adapter | Disabled | Derived graph if enabled | No complete current derivation/generation lifecycle | No | Phase 10 insight decision and Phase 11 graph work |

### Qdrant

`QdrantStore` is real: it creates collections, upserts/searches/deletes vectors, and translates metadata filters. `CompositeStorage` historically wrote V1 chunks to SQLite and Qdrant with compensation and delegated V1 dense search to Qdrant. ADR-0038 states that Qdrant payload is derived, rebuildable, and never authoritative. Historical milestone evidence and commit `94e3487656599fbea30b7465d76586556a3b7138` prove a live Qdrant run.

Current V2 does not use that path. Enabling Qdrant for V2 would require a V2 generation projection builder, authorization-preserving dense source adapter, reconciliation/activation lifecycle, and new certification. That is optional future integration, not a missing Phase 9 prerequisite.

### SurrealDB

`SurrealDBStore` implements connection plus entity/edge upsert and graph query methods. Most ordinary storage methods are unsupported. Its tests use `MockSurreal`; no current live-service integration evidence was found. `CompositeStorage` routes graph operations there, but current ingestion does not build the production graph and current V2 retrieval does not query it.

ADR-0005 remains Proposed. ADR-0050 explicitly acknowledges a nodes-only graph API because the frozen interface cannot enumerate full relation-bearing edges. The roadmap puts entity extraction/graph edges in Phase 10 and actual graph persistence/retrieval in Phase 11.

## 5. ADR Consistency Audit

### Authority ordering used

1. Later accepted ADRs and signed current certification/activation state.
2. Current executable configuration and production composition.
3. Earlier accepted ADRs not superseded by later scope.
4. Living roadmaps and current architecture prose.
5. Historical reports and milestone descriptions.

### Relevant decisions

| ADR | Status | Effect |
|---|---|---|
| ADR-0003 | Accepted | Four independently enabled backend configuration sections; no all-four persistence invariant |
| ADR-0004 | Accepted | Composition root and capability-driven registrations |
| ADR-0005 | Proposed | Graph identity for SurrealDB; evidence of intent, not current mandate |
| ADR-0038 | Accepted | Qdrant is derived/rebuildable and never authoritative |
| ADR-0039 | Accepted | SQLite owns version-aware sparse/FTS projection |
| ADR-0050 | Accepted | Honest nodes-only graph API; frozen interface lacks relation-bearing edge listing |
| ADR-0059 | Accepted | Original bytes authoritative; OCR/Vision/embeddings derived |
| ADR-0060 | Accepted | SQLite baseline durable jobs; expressly supersedes a SurrealDB-only worker assumption |
| ADR-0062 | Accepted | SQLite visual-vector generations; does not require Qdrant |
| ADR-0069 | Accepted | Freezes Phase 9-facing capability/security contracts; UI pending |
| ADR-0071 | Accepted | Additive SQLite generations; optional backends are not enabled by migration |
| ADR-0074 | Accepted | Optional-backend/V1-V2 separation; require-every-backend startup rejected |
| ADR-0075 | Accepted | Preserve frozen V1 storage interface; add new capabilities through additive ports |
| ADR-0076 | Accepted | Certifies the exact filesystem/SQLite production deployment and says binding changes invalidate certification |

No accepted ADR mandates four-way storage. FS + SQLite is explicitly permitted. Qdrant is intentionally optional. SurrealDB's complete production graph use is deferred.

## 6. Architectural Roadmap Analysis

The architecture separates the React frontend from `mnemo-core`: `mnemo-ui` calls only the server API/WebSocket and has no knowledge of retrieval implementation. This is the correct dependency direction and means Phase 9 should not care whether dense retrieval is SQLite or Qdrant.

The architecture's “Four-Store Design” language describes specialized adapters and an earlier standard-stack target. It conflicts with current certified topology when presented without qualification. Later ADRs resolve the conflict in favor of optional backends and canonical filesystem/SQLite authority.

## 7. Engineering Roadmap Analysis

Phase 9 is **Web UI**, not storage completion:

- Module 9.1: design system, routing, HTTP client, WebSocket client.
- Module 9.2: dashboard and global search.
- Module 9.3: notebook, upload/progress, chat, notes, citations.
- Module 9.4: chat history, streaming, citation cards, retrieval metadata.
- Module 9.5: settings, plugins, storage health.

The explicit Phase 9 dependency is the certified Phase 8.5 capability API. ADR-0069 says Phase 9 may assume those certified contracts but not provider availability or unbounded asset access.

Qdrant appears later in Phase 13 production hardening for 20-million-chunk benchmarking, HNSW tuning, and memmap. SurrealDB appears in Phase 10 insight storage and Phase 11 graph persistence/retrieval. Neither is a Phase 9 dependency.

## 8. Phase 9 Dependency Analysis

```text
CURRENT
  Certified V2 API + filesystem/SQLite authority
        ↓
MINIMUM PREPARATION
  1. mutable workspace versus immutable certified corpus decision
  2. authenticated V2 chat/streaming decision
        ↓
PHASE 9
  browser UI, API client, notebook views, chat, citations, settings
        ↓
PHASE 10
  background enrichment, insights, memory, incremental indexing
        ↓
PHASE 11
  entity extraction, SurrealDB graph, graph retrieval
        ↓
PHASE 13
  scale benchmark and evidence-triggered Qdrant tuning
```

### Prerequisite 1: mutable data plane

This is a factual topology conflict:

- `mnemo.toml` points ordinary `engine.storage` SQLite at the certified DB.
- `SQLiteStore.open` uses a normal writable connection.
- notebook CRUD and source upload/delete routes mutate `engine.storage`.
- `IngestionService` parses, chunks, embeds, and calls `upsert_chunks`.
- ADR-0076 binds certification to the exact database hash and says binding changes invalidate certification.

The V2 retrieval connection is immutable, but that does not make the ordinary engine connection immutable. Therefore a literal Phase 9 “create notebook → upload” implementation against the certified profile can mutate the certified corpus and invalidate its evidence.

Before exposing mutation, Mnemo must either create a governed mutable user-workspace corpus separate from the certified snapshot or deliberately scope the first Phase 9 release to read-only interaction. This does not require Qdrant or SurrealDB; a separate SQLite workspace is consistent with current architecture.

### Prerequisite 2: authenticated V2 chat path

The roadmap says WebSocket chat. Current facts:

- `AuthMiddleware` subclasses `BaseHTTPMiddleware`, so it does not authenticate WebSocket scopes.
- `_handle_websocket_connection` accepts the socket without validating a principal.
- `StreamingQueryService` constructs the legacy V1 `MultiSourceRetriever` and `RerankingModule`.
- ADR-0069 keeps V1 streaming unchanged and expressly does not introduce persisted streaming FinalQA V2.

Binding Phase 9 chat to that route would leave the certified V2 path and violate ADR-0069's authentication/isolation requirement. The minimal choice is either authenticated HTTP V2 FinalQA for the first UI or a separately governed/authenticated V2 streaming contract.

## 9. Future Consistency Analysis

| Issue | Classification | Finding |
|---|---|---|
| Current 3,019-row vector universe | SAFE TO DEFER | Below the V2 fail-closed 10,000-vector envelope |
| Growth toward >10,000 authorized vectors | ARCHITECTURAL RISK | `MAX_ELIGIBLE_MULTILINGUAL_V2_VECTORS = 10_000`; retrieval fails closed above it |
| Qdrant V2 integration | SAFE TO DEFER | Add only on measured capacity/latency/horizontal-scaling evidence |
| SurrealDB graph integration | SAFE TO DEFER | Phase 9 has no graph dependency; Phase 10/11 consume it |
| Mutable UI writes to certified corpus | MUST FIX BEFORE PHASE 9 | Invalidates hash-bound certification |
| Unauthenticated V1 WebSocket chat | MUST FIX BEFORE PHASE 9 | Wrong authorization and retrieval path |
| Provenance authority outside optional indexes | NO ACTION REQUIRED | Correctly anchored in filesystem/SQLite |
| Versioning and rebuildability | NO ACTION REQUIRED NOW | Additive generations and immutable identities already exist |
| Horizontal scaling | SAFE TO DEFER | Current local owner-operated deployment has no evidence requiring it |
| Backup/recovery for optional stores | SAFE TO DEFER | Must be designed when those stores become active, not before |

## 10. Four-Store-Now Cost/Benefit

### Benefits

- Qdrant would provide ANN search and a path toward much larger vector collections.
- SurrealDB would provide a graph traversal substrate for later entity reasoning.
- Early integration could reveal adapter/lifecycle problems sooner.

### Costs and risks

- V2 vector projection synchronization and reconciliation.
- Cross-store partial failures without a distributed transaction.
- New authorization prefilter and evidence-provenance enforcement.
- Additional generation activation, rollback, migration, monitoring, and backup mechanisms.
- New live-service integration tests and full production recertification.
- Increased memory, disk, deployment, and operational requirements.
- A new architecture branch that Phase 9 would not consume.

Net result: **negative now**. Architectural completeness alone is not sufficient justification.

## 11. Phase-9-Now Cost/Benefit

### Benefits

- Delivers the roadmap's next user-visible capability.
- Exercises already certified capability, retrieval, evidence, and citation APIs.
- Keeps UI backend-neutral and avoids unnecessary infrastructure.

### Costs and risks

- The mutable corpus boundary and chat transport must be decided first.
- Browser authentication, CORS/CSRF posture, errors, accessibility, and end-to-end tests are required.
- The UI must render capability states rather than assume every provider/backend exists.

Net result: **positive after two bounded prerequisites**.

## 12. Architectural Seam Audit

| Seam | Assessment | Evidence/implication |
|---|---|---|
| Core storage | Adequate, legacy-wide | `CompositeStorage` isolates adapters; do not widen frozen `StorageInterfaceV1` |
| V2 retrieval | Good high-level seam | `AuthorizedMultilingualDenseSourceV2` and sparse equivalent can be replaced as whole sources |
| V2 embedding store | SQLite-oriented enumeration seam | `MultilingualEmbeddingStoreV2` returns authorized vectors; Qdrant ANN should implement a dense-source adapter rather than impersonate bulk enumeration |
| Derived indexes | Good foundation, incomplete optional integration | Generation/projection protocols exist; Qdrant synchronization/activation does not |
| Authorization | Backend-independent contract | Server-derived decision and authorized source identity precede retrieval |
| Provenance | Correct | Canonical filesystem/SQLite identities remain outside optional derived indexes |
| Graph identity | Adequate base | Entities/edges reference canonical document IDs; no document identity rewrite needed |
| Graph query API | Incomplete | Frozen V1 interface is nodes-only; use a new additive graph retrieval port later |
| Lifecycle | Reusable pattern | V2 generations and reranker activation demonstrate the pattern; optional stores still need their own evidence and rollback |
| UI/server | Correct layering | UI talks only to server; storage implementation must remain invisible |

The seams are sufficient to defer Qdrant and SurrealDB safely. Future integration is additive work, not a rewrite, provided canonical authority remains in filesystem/SQLite.

## 13. Real Technical Debt

### A. Blocking debt

1. Certified immutable corpus versus writable Phase 9 notebook/upload routes.
2. Unauthenticated legacy V1 WebSocket versus certified Phase 9 chat.

### B. Important but deferrable debt

- Exact-cosine V2 is bounded to 10,000 authorized vectors.
- No Qdrant V2 projection/source/activation/certification path.
- SurrealDB lacks end-to-end extraction, synchronization, retrieval, and live integration.
- Frozen graph interface lacks full edge enumeration.

### C. Documentation debt

- Phase 8.5 roadmap status is stale.
- Four-store wording is ambiguous about current topology.
- M2 language overstates SurrealDB completeness.
- Phase 9 streaming text does not distinguish V1 from certified V2.
- Phase 10 insight storage wording needs reconciliation with provider-neutral job/storage governance.

### D. Optional future capability

- Qdrant ANN/horizontal vector search.
- SurrealDB entity graph and multi-hop retrieval.
- Knowledge graph explorer.
- Phase 13 vector-index tuning.

### E. No action required

- Filesystem + SQLite authoritative topology.
- Separate FinalQA operational store.
- Current model/retrieval identities and certification.
- Dormant optional adapters while disabled.

## 14. Documentation Contradictions

1. The current architecture document presents a “Four-Store Design,” while later ADRs and current configuration define optional backends.
2. The engineering roadmap calls Phase 8.5 active/open, while ADR-0076 and WP-17 say certified.
3. M2 says all four stores are operational, but SurrealDB is only a graph subset with mocked tests and later roadmap work.
4. Phase 9 prescribes WebSocket chat, but ADR-0069 preserved V1 streaming and did not certify V2 streaming.
5. The roadmap says Phase 10 insights go to SurrealDB, while ADR-0060 moved the baseline durable job facility to SQLite/provider-neutral contracts.

These should be corrected before developers use the roadmap as an implementation specification.

## 15. Risk Register

| Risk | Likelihood | Impact | Trigger | Control |
|---|---|---|---|---|
| UI mutates certified DB | High if current routes are used | Critical | Create/upload/delete in certified profile | Separate mutable workspace or read-only UI |
| UI chat bypasses V2/auth | High if roadmap is literal | High | Connect to `/v1/ws/query` | HTTP V2 first or certified V2 streaming |
| Exact-cosine capacity exceeded | Low now; rises with uploads | High/fail-closed | Authorized vectors approach 10,000 | Capacity telemetry and Qdrant decision gate |
| Premature four-store destabilization | Medium if pursued | High | Enable optional stores without V2 lifecycle | Defer and recertify when justified |
| Graph implementation drift | Medium later | Medium/high | Phase 10/11 starts without additive graph contract | Graph ADR and live integration tests |
| Stale documentation drives wrong implementation | High | Medium | Phase 9 team follows old diagrams | Documentation reconciliation |
| No live server observed during audit | Current operational observation | Low for architecture, blocks live UI testing | Begin integration without server | Start through governed runbook during Phase 9 testing |

## 16. Recommended Decision

`RECOMMEND_MINIMAL_ARCHITECTURAL_PREPARATION_THEN_PHASE_9`

Reject full four-store implementation now. Complete the mutable-data-plane and authenticated-chat decisions, enforce them with focused tests, reconcile documentation, and then proceed to Phase 9 on filesystem + SQLite.

## 17. Recommended Immediate Actions

1. Record that Qdrant and SurrealDB are not Phase 9 prerequisites.
2. Decide whether Phase 9 is initially read-only or uses a separate governed mutable SQLite workspace.
3. Select authenticated HTTP V2 FinalQA or define/certify V2 streaming; do not use the current V1 WebSocket for production chat.
4. Correct Phase 8.5 status, four-store wording, and V1/V2 streaming language.
5. Add pre-Phase-9 contract tests for corpus immutability, mutation routing, WebSocket authentication, and certified V2 selection.

## 18. Recommended Phase 9 Scope

- Build the UI against server contracts only.
- Use `/v2/capabilities` to render availability and disabled states.
- Implement dashboard/search/read-only source and evidence views first.
- Enable notebook creation/upload only after mutable-store routing is governed.
- Use the selected authenticated V2 FinalQA path for chat and citations.
- Add browser tests for auth, isolation, citations/provenance, dynamic requested-k, errors, capability gating, and reconnect behavior.
- Do not add graph UI until Phase 11 graph retrieval exists.

## 19. Deferred Qdrant Plan

Trigger Qdrant work when one of these becomes true:

- authorized vector count approaches the 10,000 V2 envelope;
- exact-cosine latency violates an approved SLO;
- a deployment requires horizontal vector search;
- Phase 13's 20-million-chunk benchmark begins.

Then implement an authorization-preserving V2 dense-source adapter, rebuildable projection generation, reconciliation, activation/rollback, and parity certification. Qdrant must remain derived; it must not acquire document/provenance authority.

## 20. Deferred SurrealDB/Graph Plan

Before Phase 10 Module 10.3, decide whether insight records truly require SurrealDB or remain in the provider-neutral/SQLite facility. For Phase 11, define an additive graph contract with relation-bearing edges, derivation provenance, source/version identity, authorization, rebuildability, and generation lifecycle. Then add live SurrealDB integration tests and an optional `GraphRetriever`.

Do not widen the frozen `StorageInterfaceV1`; ADR-0075's additive-port pattern is the correct seam.

## 21. Future Migration/Expansion Conditions

- Preserve filesystem/SQLite as canonical authority.
- Treat vector and graph systems as rebuildable derived projections.
- Bind every optional index generation to corpus, model, configuration, and authorization identity.
- Require coverage validation and atomic activation before serving.
- Keep source/version/chunk identities stable across adapters.
- Benchmark before selecting infrastructure.
- Recertify any production topology change.

## 22. Final Go/No-Go Decision

CURRENT STATE:
Mnemo has a certified, internally consistent V2 retrieval/FinalQA production snapshot using content-addressed filesystem storage, immutable SQLite corpus/projections, and a separate operational SQLite store. Qdrant and SurrealDB are disabled optional adapters. Phase 8.5 is certified despite stale roadmap text; Phase 8.6 remains evaluation-only. The complete Phase 9 workflow has two boundary gaps: mutable upload routing and authenticated certified chat transport.

SHOULD WE IMPLEMENT FULL FOUR-STORE STORAGE NOW?
NO
Reason:
No accepted ADR or Phase 9 dependency requires it. Qdrant and SurrealDB would not be consumed by Phase 9, while enabling them would create synchronization, authorization, lifecycle, operational, and recertification cost. Qdrant is an evidence-triggered scale option; SurrealDB belongs to later graph work.

SHOULD WE PROCEED TO PHASE 9?
YES
Reason:
The certified Phase 8.5 capability API—the roadmap's declared dependency—is complete. Proceed after the two bounded prerequisites below; UI scaffolding and read-only contract work can begin immediately, but the full create/upload/chat milestone must not ship before they pass.

MUST WE DO ANY ARCHITECTURAL WORK BEFORE PHASE 9?
YES
If yes:
Define and enforce (1) a mutable workspace boundary that cannot mutate the certified corpus, or a read-only first-release scope, and (2) an authenticated certified V2 chat transport rather than the existing unauthenticated legacy V1 WebSocket. Also reconcile the roadmap/documentation so these constraints are explicit.

RECOMMENDED NEXT 5 ACTIONS:
1. Record the no-four-store-now decision and optional-backend triggers.
2. Decide and govern the Phase 9 mutable workspace versus read-only topology.
3. Decide and govern HTTP V2 versus authenticated V2 streaming for chat.
4. Correct stale Phase 8.5, four-store, and streaming roadmap language.
5. Begin Phase 9 Modules 9.1–9.2 with capability-driven API contract tests.

DEFER UNTIL LATER:
- Qdrant: Until capacity/SLO evidence or Phase 13 hardening requires ANN infrastructure.
- SurrealDB / Graph: Design boundary before Phase 10 insights; implement production graph persistence/retrieval in Phase 11.
- Other: Horizontal scaling, optional-store backup/recovery, and graph UI until a consuming phase and measured requirement exist.

ARCHITECTURAL CONFIDENCE:
HIGH

FINAL STATUS:
MINIMAL_ARCHITECTURAL_PREPARATION_REQUIRED_THEN_PHASE_9_GO

## Evidence Index

Primary evidence includes:

- `config/production/full_multilingual_v2.production.json`
- `scratch/phase8_5_full_multilingual_v2/operational/reranker_activation.json`
- `scratch/phase8_5_full_multilingual_v2/operational/certification.json`
- `scratch/evaluation_notebooks/registry.json`
- `docs/reports/certification/current/mnemo-v2-final-certification.md`
- `docs/architecture/current/mnemo_engineering_roadmap.md`
- `docs/architecture/current/mnemo_architecture_v2.md`
- ADR-0003, ADR-0004, ADR-0005, ADR-0038, ADR-0039, ADR-0050, ADR-0059, ADR-0060, ADR-0062, ADR-0069, ADR-0071, ADR-0074, ADR-0075, and ADR-0076
- `mnemo-core/mnemo/storage/{filesystem,sqlite,qdrant,surrealdb,composite,v2_runtime}.py`
- `mnemo-core/mnemo/retrieval/{multilingual_dense_v2,multilingual_sparse_v2,full_multilingual_v2}.py`
- `mnemo-server/mnemo_server/services/full_multilingual_v2_production.py`
- `mnemo-server/mnemo_server/routers/{sources,streaming}.py`
- `mnemo-server/mnemo_server/services/{ingestion,streaming}.py`
- `mnemo-server/mnemo_server/auth.py`
- relevant Qdrant, SurrealDB, CompositeStorage, V2 production, authorization, transport, and streaming tests
- Git commits `3f01684a334baf6ac55d629045dd5c372c241e7e`, `2055b38f1dc5e078fe67a8d9fd2563fd58f45f98`, `b51d1d1791bec99ff443a3247090f52216c26cb8`, `94e3487656599fbea30b7465d76586556a3b7138`, `e2041cd0b392805a0a6f6e52e5ba2aae5856e91e`, and `a96059d9f9e61271dec96e0fc066d094dc4a6554`

No source, test, configuration, database, model, registry, activation state, certification state, process, service, corpus, or Git history was modified during this audit.
