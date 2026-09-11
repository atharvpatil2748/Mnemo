# Mnemo Phase 8.5 Complete Implementation Plan

**Status:** Approved authoritative execution blueprint; WP-00 through WP-08 completed 2026-08-27  
**Prepared:** 2026-08-26  
**Baseline:** Mnemo 0.25.0 working tree and isolated Phase 8.5.11 evaluation state  
**Scope:** Close Phase 8.5 architecture, integration, delivery, and certification gaps without implementing Phase 11  
**Normative rule:** Accepted ADRs outrank living architecture/roadmap prose; current code establishes runtime fact; historical reports establish only what they actually tested.

## 1. Executive Summary

Phase 8.5 is not complete end to end. It contains substantial, generally well-designed foundations—asset provenance, bounded extraction, durable jobs, typed OCR/vision/multilingual/multimodal models, exhaustive and structured services, immutable V2 evidence, and bounded delivery—but many are library-level capabilities rather than operational product capabilities.

The central implementation defect is incomplete composition:

```text
typed models/services exist
  != provider adapters are composed
  != projections are populated and active
  != HTTP/MCP exposes the capability
  != an unfamiliar agent can discover and use it
  != evaluation proves the complete chain
```

The completion program therefore preserves the frozen Phase 0–8 plane and adds an operational Phase 8.5 capability plane with:

- one additive composition root for advanced, structured, multilingual, multimodal, and Final-QA V2 services;
- independently generated and atomically promoted OCR, vision-text, visual-vector, multilingual, and structured projections;
- honest capability/readiness/coverage reporting;
- explicit MCP contracts for evidence search, structured queries, positional document traversal, analysis discovery, and Final-QA V2;
- exact document selectors, retained signed cursors, and consistent completeness semantics;
- agent-usable image discovery separated from image delivery and image analysis;
- deterministic multi-document primitives without prematurely implementing Phase 11 planning;
- blind external-agent behavioral certification.

No canonical identities, `Chunk.text`, V1 retrieval, V1 Final-QA, the six V1 MCP tools, or Qdrant optionality should change. The expected production schema change is one additive generation-backed migration for searchable vision/language text projections; all other work should reuse existing schema v13 facilities where possible.

## 2. Scope

### In scope

- Reconcile ADR-0058–ADR-0072 with runtime behavior.
- Complete wiring, indexing, configuration, HTTP/MCP exposure, discoverability, security, and evaluation for Phase 8.5.
- Restore an additive storage-interface boundary after ADR-0072.
- Preserve existing direct delivery and V1 contracts.
- Create deterministic primitives Phase 11 can orchestrate.

### Out of scope

- General autonomous planning, query decomposition, evidence-gap replanning, or graph traversal.
- Phase 9 UI implementation.
- New model benchmarking unless a provider/profile changes.
- Re-ingestion or mutation of the frozen Golden Corpus.
- Mandatory Qdrant/SurrealDB/cloud providers.
- Corpus-specific heuristics, ranking weights, filenames, or queries.
- Release, version bump, commit, push, tag, or deployment in individual work packages.

## 3. Source/Document Authority Map

| Source | Classification | Authority and use | Current contradiction/action |
|---|---|---|---|
| `docs/adr/ADR-0001`–`ADR-0057` | AUTHORITATIVE, HISTORICAL DECISIONS | Frozen Phase 0–8 identities, storage, retrieval, citation, Final-QA, HTTP/MCP contracts | Preserve; ADR-0008 is superseded where ADR-0011 states; ADR-0057 narrowly supersedes ADR-0042 pair construction/order |
| `docs/adr/ADR-0058`–`ADR-0071` | AUTHORITATIVE, CURRENT DECISIONS | Normative Phase 8.5 architecture | Implementation-status headers overclaim operational completion; decisions remain valid |
| `docs/adr/ADR-0072...` | AUTHORITATIVE DECISION WITH CONTRACT DRIFT | Notebook identity propagation and safe auto-resolution behavior | Useful behavior, but extending frozen `StorageInterfaceV1` conflicts with ADR-0058–0071 additive rule; supersede mechanism, retain behavior |
| `docs/architecture/current/mnemo_architecture_v2.md` | AUTHORITATIVE LIVING ARCHITECTURE, subordinate to ADRs | Overall layering, engine boundary, V1 architecture, Phase 11 ownership | Current Phase 8.5 completion statement needs later correction |
| `docs/architecture/current/phase8.5_architecture.md` | AUTHORITATIVE BLUEPRINT, subordinate to ADRs | Original Phase 8.5 capability design | `[CODE]` and “implemented” labels drift from actual composition/index/runtime state |
| `docs/architecture/historical/mnemo_phase8_5_engineering_roadmap.md` | NORMATIVE EXECUTION PLAN | Workstreams, gates, dependencies, tests, security | Checked completion boxes contradict runtime and behavioral evidence |
| `docs/architecture/current/mnemo_engineering_roadmap.md` | CURRENT MASTER ROADMAP | Phase boundaries and Phase 11 ownership | Phase 8.5 completion should be reopened until closure gates pass |
| `README.md` and package READMEs | CURRENT PRODUCT DOCUMENTATION | User-facing capabilities and setup | Overstates operational advanced/multimodal/multilingual readiness |
| `docs/adr/README.md` | CURRENT ADR INDEX | Decision discovery and status summary | “Completely implemented” conflicts with active projections/MCP composition |
| `docs/changelog/*` | HISTORICAL | What was claimed/released at a time | Do not rewrite; add corrective entry later |
| `docs/governance/PHASE_8_5_1...10_GATE_EVIDENCE.md` | GOVERNANCE RECORD / IMPLEMENTATION EVIDENCE | Focused module-level evidence | Proves components, not necessarily operational composition |
| `PHASE_8_5_PRE_8_5_11_RECONCILIATION.md` | HISTORICAL GOVERNANCE RECORD | Earlier static reconciliation | Contradicted by ADR-0072, actual MCP names, empty projections, and post-client behavior |
| `PHASE_8_5_11_EVALUATION_REPORT.md` | EVALUATION ARTIFACT | Corpus/model/direct API evidence | Production gate and end-to-end claims exceed retained QA and MCP behavioral evidence |
| `MCP_SEARCH_TO_DOCUMENT_RETRIEVAL_PROPAGATION_AUDIT.md` | IMPLEMENTATION RECORD | Direct forced search-to-cursor traversal | Does not prove blind client tool selection; calls tool set “production-ready” too broadly |
| `POST_PHASE_8_5_MCP_ARCHITECTURAL_AUDIT.md` | CURRENT DIAGNOSTIC, not normative | Verified current external-client and composition gaps | Use as current-state evidence; reconcile with original ADR intent |
| Current source and tests | IMPLEMENTATION SOURCE OF TRUTH | What actually exists and what tests actually prove | Classes/tests alone do not establish runtime readiness |
| `mnemo.toml` | CURRENT LOCAL RUNTIME CONFIGURATION | Actual process configuration | Uses V1 nomic/MiniLM while also declaring Phase 8.5 models; selected profiles are not composed |
| `phase8_5_models.toml` references | CONTRADICTORY/MISSING ARTIFACT | Reports claim authoritative model profile file | File is absent from repository; resolve through an explicit profile registry/config contract |
| Evaluation DB and benchmark artifacts | EVALUATION ARTIFACT | Read-only operational census and retained results | 44/44/44, 2,658 canonical rows, 464 occurrences; derived projections/generations are inactive/empty |

### Authority conflict rule

1. Preserve immutable ADR history.
2. If code violates an accepted decision, fix code unless a newer accepted ADR explicitly supersedes it.
3. If a later ADR introduces a contradiction without naming supersession, create a successor ADR; do not reinterpret history silently.
4. Correct active docs only after implementation evidence exists.
5. Add post-certification corrections rather than rewriting historical gate/evaluation reports.

## 4. Original Phase 8.5 Intent

Phase 8.5 was intended to make ranked, exact, positional, exhaustive, structured, aggregate, cross-document, multilingual, asset, and multimodal evidence first-class before Phase 9 and Phase 11. The following capability map reconstructs that intent.

| Capability | Intended purpose / owner | Persistent data/index | Required surface and tests | Intended Phase 8.5 status |
|---|---|---|---|---|
| Canonical ingestion | Frozen ingestion pipeline | Documents, versions, sources, chunks, originals | V1 ingestion; regression corpus | Preserve |
| Identity/version/source | Frozen domain/storage | Canonical IDs and relationships | All evidence carries exact identities | Preserve |
| Chunking | Frozen parser/chunker plane | Canonical chunks | V1 APIs/MCP unchanged | Preserve |
| Canonical text retrieval | V1 retrieval | FTS/title and optional vectors | V1 query/search | Preserve |
| Dense retrieval/reranking | V1 plus additive profiles | Named vector generations | V1 unchanged; V2 profiles additive | Preserve/extend |
| Exact retrieval | Advanced retrieval | Exact normalized fields/positions | Typed exact operation | Complete in Phase 8.5 |
| Exhaustive retrieval | ADR-0058 | Stable snapshots/cursors | Explicit exhaustive HTTP/MCP | Complete in Phase 8.5 |
| Positional retrieval | ADR-0058/0065 | Parsed IR/position projection | Page/slide/section/range/from-end | Complete in Phase 8.5 |
| Structured retrieval | ADR-0063 | Versioned table projections | Typed query/filter/sort/group/aggregate | Complete in Phase 8.5 |
| Multilingual retrieval | ADR-0067 | Observations, transformations, vectors/analyzers | Same/cross-language V2 search | Complete per certified profile |
| Asset extraction/identity | ADR-0059 | Assets, binary refs, occurrences | Inventory and exact delivery | Complete |
| OCR | ADR-0061 | Regions, results, OCR FTS/vector generations | Governed jobs plus searchable evidence | Complete when profile active |
| Vision analysis | ADR-0062 | Immutable results and text projection | Governed jobs plus searchable evidence | Complete when profile active |
| Visual embeddings | ADR-0062 | Named visual-vector generation | Visual and cross-modal retrieval | Complete when profile active |
| Multimodal retrieval | ADR-0064 | Typed candidate/result snapshots | Search/fusion/context/Final-QA V2 | Complete in Phase 8.5 |
| Document delivery | ADR-0065 | Parsed IR/original reference | Bounded selectors/cursors | Complete in Phase 8.5 |
| Asset delivery | ADR-0065/0066 | Original bytes + occurrence auth | Native resource with provenance | Complete in Phase 8.5 |
| Provenance | All Phase 8.5 ADRs | Immutable identity chain | Every boundary and snapshot | Mandatory P0 |
| Authorization | ADR-0068 | Notebook/source/version/occurrence path | Reauthorize every search/delivery/replay | Mandatory P0 |
| Completeness | ADR-0058 | Snapshot and representation reports | Machine-readable on every V2 result | Mandatory P0 |
| Cursor/pagination | ADR-0058/0065 | Signed opaque state | Resumable, bound, expiring | Mandatory P0 |
| MCP exposure | ADR-0066 | None beyond service state | Four delivery tools, later stable multimodal discovery | Complete client capability |
| HTTP exposure | ADR-0069 | None beyond services | Advanced/structured/jobs/Final-QA V2/delivery | Complete Phase 8.5 adapter plane |
| Agent discoverability | ADR-0066/0070 implied by live-client gate | Tool metadata/schemas | Blind tool-choice tests | Required for MCP certification |
| Evaluation | ADR-0070 | Versioned manifests/results | Per-capability live and offline evidence | Complete/truthful |
| Security/isolation | ADR-0068 and threat matrix | Policy/audit records | Adversarial tests | Complete |
| Model/profile management | ADR-0062/0067/0070/0071 | Pinned profile + generation identity | Capability negotiation and runtime composition | Complete per profile |
| Configuration | ADR-0003 plus profiles | Immutable config snapshot | One authoritative precedence path | Complete |
| Governance | ADR-0070 | Evidence/docs | Truthful gates, historical preservation | Complete |
| Phase 11 compatibility | ADR-0058/0064 and master roadmap | Typed results/snapshots only | Deterministic primitives; no storage leakage | Complete handoff |

## 5. Current Architecture

### Current planes

```text
Phase 0–8 canonical plane
  ingestion -> chunks -> FTS/optional dense -> V1 retrieval -> V1 Final-QA

Phase 8.5 library plane
  assets/jobs/OCR/vision/advanced/structured/multimodal/multilingual/delivery

Current adapter plane
  HTTP V1 + /v2 delivery routes
  MCP six V1 tools + four direct delivery tools
```

The additive library plane is not represented by one composed runtime. `KnowledgeEngine` exposes storage, asset catalog, jobs, OCR store, and vision store, but it does not compose or expose advanced retrieval, structured retrieval, multilingual retrieval, multimodal retrieval, Final-QA V2, certified OCR/Vision/visual/multilingual providers, or projection builders. Server search/query remain V1.

### Current storage

- SQLite schema version 13 contains asset, job, OCR, vision, structured, multimodal, and multilingual tables.
- Filesystem remains authoritative for binary assets/IR.
- Qdrant and SurrealDB remain optional and disabled in the active local profile.
- The current isolated evaluation DB has 44 documents/versions/sources, 2,658 chunks/FTS/title rows, and 464 occurrences.
- It has persisted derivation samples but zero active index generations, zero OCR projection/FTS content, zero visual projection rows, zero multilingual embeddings, and zero structured table cells.

### Current transports

- HTTP `/v2` exposes capabilities, document blocks/original, exact chunk, asset inventory/content, analysis, and Final-QA evidence delivery.
- It does not expose advanced/exhaustive retrieval, structured retrieval, multilingual/multimodal retrieval, governed job submission, or Final-QA V2 execution.
- MCP exposes the six frozen V1 tools plus `get_document`, `get_document_chunk`, `get_asset`, and `get_image_analysis`.
- MCP inputs have no output schemas; descriptions do not establish negative guidance or tool chains.

## 6. Current Implementation State

| Capability | Code exists | Wired | Indexed/populated | HTTP | MCP | Discoverable/E2E | Status |
|---|---:|---:|---:|---:|---:|---:|---|
| Canonical ingestion/chunks/FTS/title | Yes | Yes | Yes | Yes | Yes | Yes | IMPLEMENTED |
| V1 dense/reranking | Yes | Yes | Deployment-dependent | Yes | Yes | Partial | IMPLEMENTED, bounded |
| Asset originals/occurrences | Yes | Yes | Yes | Yes | Direct IDs | Weak | IMPLEMENTED |
| Durable jobs/governance | Yes | Storage only | Job records exist | No complete Phase 8.5 API | No | No | PARTIAL |
| OCR derivations | Yes | Script/worker path | Samples; search projection empty | Delivery only | Direct derivation ID | No | PARTIAL |
| Vision derivations | Yes | Script/worker path | Samples; text projection absent | Delivery only | Direct derivation ID | No | PARTIAL |
| Visual embeddings | Yes | Script/worker path | Samples; active projection empty | No search | No search | No | PARTIAL |
| Advanced ranked/exhaustive | Yes | Not in engine/server | Canonical source only in tests | No | No | No | PARTIAL |
| Exact/positional | Partial models/store behavior | Not exposed | Canonical positions only | Forward blocks only | Forward blocks only | Weak | PARTIAL |
| Structured | Yes | Not in engine/server | Empty current projection | No | No | No | PARTIAL |
| Multimodal fusion/context | Yes | Not in engine/server | No active derived sources | No execution | No | No | PARTIAL |
| Final-QA V2 | Yes | Not normal composition | Snapshot tables exist | Evidence delivery only | No execution | No | PARTIAL |
| Multilingual | Yes | Not in engine/server | Empty current vectors/derivations | No | No | No | PARTIAL |
| Document delivery | Yes | Yes | Parsed IR available | Yes | Yes | Cursor workflow weak | IMPLEMENTED WITH API DEFECTS |
| Asset delivery | Yes | Yes | Yes | Yes | Yes | Discovery broken | IMPLEMENTED WITH API DEFECTS |
| Capability discovery | Delivery-only | Yes | Does not reflect generations/coverage | Yes | Resource only | Misleading | INCORRECT/INCOMPLETE |
| External-agent validation | Direct matrices | N/A | N/A | Partial | Preselected calls | Failed real behavior | MISSING |

## 7. Gap Matrix

| ID | Original requirement | Actual | Gap class | Priority / owner |
|---|---|---|---|---|
| G-01 | Every Phase 8.5 capability is composed and capability-negotiated | Core classes are isolated | MISSING IMPLEMENTATION | P0 / composition |
| G-02 | Exact/positional/full retrieval is agent-usable | Forward block pagination only | PARTIAL + API DRIFT | P0 / delivery |
| G-03 | Exhaustive retrieval is explicit and truthful | Core-only, no adapter | MISSING EXPOSURE | P0 / retrieval-adapter |
| G-04 | Structured numeric guarantees | Core-only, no populated projection | MISSING INDEX + EXPOSURE | P0 / structured |
| G-05 | Image discovery through OCR/Vision/vector evidence | Direct-ID inventory/delivery only | MISSING PIPELINE | P0 / multimodal |
| G-06 | Derivation availability is discoverable | IDs required but not listed/resolved | INCORRECT API | P0 / delivery |
| G-07 | Native binary resources preserve provenance/completeness | MCP image drops envelope; partial bytes possible | INCORRECT IMPLEMENTATION | P0 / MCP delivery |
| G-08 | Derived indexes have atomic active generations | Tables exist, active generations zero | PARTIAL IMPLEMENTATION | P0 / projection lifecycle |
| G-09 | Multilingual selected profiles are operational | Config declared, service not composed, vectors zero | CONFIG/COMPOSITION DRIFT | P1 |
| G-10 | Multimodal/Final-QA V2 exposed | Library-only/evidence-read endpoint | MISSING EXPOSURE | P1 |
| G-11 | HTTP contract covers ADR-0069 | Only delivery subset exists | PARTIAL IMPLEMENTATION | P1 |
| G-12 | MCP teaches unfamiliar clients | Weak descriptions/no outputs/negative guidance | TEST/API GAP | P0 |
| G-13 | Capability discovery is truthful | Reports configured support, not active readiness/coverage | INCORRECT IMPLEMENTATION | P0 |
| G-14 | Delivery cursor is short-lived and scope-bound | Scope-bound HMAC, but no expiry and weak default secret | SECURITY/ADR DRIFT | P1 |
| G-15 | `StorageInterfaceV1` remains frozen | ADR-0072 added method | ARCHITECTURAL DRIFT | P1 |
| G-16 | Production profile artifact is authoritative | Referenced file absent; inline config ambiguous | DOCUMENTATION/CONFIG DRIFT | P1 |
| G-17 | Evaluation proves live E2E behavior | Direct IDs and scripts were used | TEST-COVERAGE GAP | P0 |
| G-18 | Phase 8.5 completion claims are truthful | Active docs declare complete | DOCUMENTATION DRIFT | P1 |
| G-19 | Multi-document deterministic primitives | Scope model exists; no adapter/partitioned contract | PARTIAL | P1 |
| G-20 | Historical evidence remains immutable | Some active ADR status prose embeds later claims | GOVERNANCE RISK | P2 |

## 8. Architectural Drift Analysis

### ADR-0072 conflict

ADR-0072 correctly requires notebook identity propagation and safe auto-resolution. Its implementation incorrectly extends frozen `StorageInterfaceV1`. The smallest coherent resolution is a successor ADR that:

1. retains `notebook_id` in search results;
2. retains fail-closed auto-resolution;
3. introduces additive `DocumentScopeResolverV1`/`DocumentSourceLookupV1`;
4. migrates delivery/search composition to that protocol;
5. removes the method from the frozen protocol while concrete stores may keep it as a compatibility method;
6. tests legacy storage doubles that implement only the frozen interface.

### Status-label drift

ADRs are authoritative for decisions, not implementation claims. “Complete” headers in ADRs and roadmap checkboxes must be treated as historical status annotations until the final gate is rerun. Future active status should be maintained in one capability matrix, not copied across every ADR.

### API drift

ADR-0069 calls for advanced/structured retrieval, job operations, and Final-QA V2 adapters. Current `/v2` routes implement only bounded delivery. ADR-0066's four delivery tools were implemented, but the architecture explicitly allowed `search_multimodal` after typed candidates stabilized; that stabilization now exists, so omission is no longer justified.

### Configuration drift

Selected profiles exist in defaults/`mnemo.toml`, while the engine composes only V1 providers. The missing `phase8_5_models.toml` makes the reported profile source non-reproducible. A profile registry and explicit active profile must replace implicit declaration without altering V1 defaults.

## 9. MCP Architectural Analysis

### Design rule

MCP is a client-facing semantic API. Tool metadata must allow a new LLM to distinguish discovery, traversal, enumeration, structured execution, analysis, and delivery without knowing Mnemo internals.

### Existing tools: required non-breaking metadata corrections

| Tool | Exact description requirement | Negative guidance | Output/continuation requirement |
|---|---|---|---|
| `search_all_notebooks` | “Ranked, bounded canonical text/title search used to discover relevant documents/chunks and IDs.” | “Not exhaustive; do not use alone for all/every/count/range/last/full/image-semantic requests.” | Output schema includes IDs, ranks, mode=`bounded`, and recommended next actions |
| `query_notebook` | “Bounded V1 text QA in one notebook.” | “Does not guarantee all matches, structured arithmetic, exact traversal, or multimodal analysis.” | Evidence/citation schema and bounded completeness |
| `get_document` | “Retrieve exact-version blocks/original bytes; use selectors or follow cursor until terminal completeness for exact/full/end requests.” | “Not semantic search.” | Typed selector, positions, snapshot, completeness, next cursor, omissions |
| `get_document_chunk` | “Retrieve one known canonical chunk and ancestry.” | “Not traversal or search.” | Exact attribution schema |
| `get_asset` | “List occurrences for a known exact version or deliver a known original occurrence.” | “Not semantic image search or analysis.” | Inventory includes analysis availability; binary uses resource metadata envelope |
| `get_image_analysis` | “Resolve/deliver authorized immutable OCR/Vision analyses for a known occurrence.” | “Not original pixels and not image discovery.” | Selector-based resolution; returns original/derived distinction and completeness |

### Additive tools

1. **`search_evidence`** — ranked or exhaustive typed retrieval across explicit representations and document scope. This is the sole semantic image/multimodal discovery tool; do not add a duplicate `search_images` initially.
2. **`query_structured`** — typed filters, comparisons, sorting, grouping, and aggregates over a named exact-version dataset.
3. **`run_final_qa_v2`** — persisted typed multimodal Final-QA V2 execution/replay, only after composed retrieval is certified.
4. **`get_capabilities`** — machine-readable active profile, generation, coverage, bounds, and reason states. Retain `mnemo://capabilities`; the tool exists because tool-centric clients may not inspect resources.

### Common output contract

Every V2 MCP result must include:

```json
{
  "contract_version": "...",
  "request_id": "opaque",
  "snapshot_identity": "sha256",
  "scope": {"notebook_id": "...", "document_ids": [], "version_ids": []},
  "representations_requested": [],
  "representations_searched": [],
  "completeness": "complete|partial|truncated|bounded|unknown|empty|unavailable|failed",
  "coverage": [{"representation": "...", "state": "...", "examined": 0, "reason": null}],
  "items": [],
  "next_cursor": null,
  "limits": {},
  "omissions": [],
  "recommended_next_actions": []
}
```

Tool results must use MCP structured content/output schemas when supported and a JSON `TextContent` compatibility representation otherwise. Binary content must be an `EmbeddedResource`/`ImageContent` paired with provenance metadata; never an anonymous partial image.

## 10. Document Retrieval Plan

Retain exact `document_id` and `version_id` as the immutable boundary. Add a selector union to `DeliveryRequestV2` while retaining the existing request as a compatibility adapter:

| Selector | Fields | Semantics |
|---|---|---|
| `full` | optional `item_kinds`, `include_assets` | Scan exact version in canonical physical order; cursor until terminal |
| `page_range` | `start`, `end` | Inclusive physical pages; unavailable page metadata is typed |
| `slide_range` | `start`, `end` | Inclusive slides |
| `sheet_range` | sheet names/indexes and optional cell range | Exact workbook positions |
| `block_range` | start/end ordinal | Inclusive parsed-block range |
| `chunk_range` | anchor chunk IDs or canonical positions | Exact contiguous chunk range |
| `section` | heading path/section index | Deterministic section boundary |
| `from_end` | unit=`page|slide|block|paragraph`, count | Resolve tail against the stable exact-version snapshot, return forward order |
| `adjacent` | anchor chunk/block, before, after | Bounded same-version adjacency |

Rules:

- exactly one selector;
- absent selector on legacy `get_document` maps to `full`;
- no semantic ranking after selector resolution;
- ambiguous anchors return typed alternatives;
- cursor binds notebook scope, exact version, parsed-IR digest, selector, representation options, policy limits, next stable key, issued/expiry times, and contract version;
- reauthorization occurs on every page;
- `complete` only at terminal cursor;
- “full” never implies one unbounded response;
- original-byte ranges use protocol range/resource semantics, not partially decoded `ImageContent`.

HTTP adds `POST /v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/expand` for typed selectors. Existing GET delivery remains as a legacy full-forward adapter.

## 11. Cursor/Completeness Plan

Create a shared semantic cursor envelope and codec utility with domain-separated codecs for retrieval, structured rows, document blocks, asset inventory, and binary ranges. Do not force identical internal position fields.

Mandatory envelope:

- contract/domain/version;
- request fingerprint;
- notebook/scope fingerprint;
- exact version and representation/index snapshot identities;
- stable last key or range offset;
- effective limits;
- issued and expiry timestamps;
- HMAC key identifier for rotation.

Migration behavior:

- keep existing delivery cursor decoder for a bounded compatibility window;
- issue only v2 cursors after rollout;
- old tokens expire rather than being translated;
- require a deployment secret outside test/local-only profiles; reject the built-in default in authenticated production mode.

Completeness uses a shared transport vocabulary mapped losslessly from domain enums. `bounded` is required for ranked results; `complete` requires every requested representation to be searched and exhausted on the bound snapshot; disabled/unavailable representations force `partial` or `unavailable`, never `empty`.

## 12. Asset/Multimodal Plan

Separate three operations:

1. **Discovery:** `search_evidence` returns `asset_occurrence`, OCR, vision, or visual-vector candidates from natural language.
2. **Delivery:** `get_asset` returns authorized original bytes for a selected occurrence.
3. **Analysis:** `get_image_analysis` returns immutable derived observations selected by modality/profile/generation.

Asset inventory must return:

- occurrence and asset IDs;
- exact notebook/source/document/version;
- typed locator and physical order;
- MIME/hash/size/dimensions;
- authored alt text;
- available OCR/Vision/visual-vector derivations with status/profile/generation/language/completeness;
- recommended next calls.

Do not authorize by `asset_id`, hash, derivation ID, or blob URI. Every retrieval candidate and cache hit must resolve through an authorized occurrence.

For images over the one-message limit, return a resource link/embedded resource range plus completeness/cursor metadata. Do not emit undecodable partial bytes as `ImageContent`. A complete image may use `ImageContent`; partial binary ranges must use a binary resource envelope.

## 13. OCR/VLM Plan

- Register certified OCR/Vision providers through the Phase 8.5 runtime profile, not evaluation scripts.
- Route every provider invocation through `ProcessingJobStoreV1`/`ProcessingWorkerV1`, authorization, consent, budget, and resource admission.
- Add authorized derivation-list/read interfaces; never scan private storage from MCP handlers.
- Populate OCR FTS/vector and Vision text FTS/vector projections through immutable generation builders.
- Treat OCR/VLM output as untrusted derived evidence; never mutate `Chunk.text`.
- Preserve partial per-page/occurrence outcomes and coverage counts.
- `get_image_analysis` accepts `analysis_selection`:
  - explicit immutable ID;
  - `latest_ready` for a named modality/profile/generation;
  - `all_ready` within bounds.
- Server resolves selection after occurrence authorization and returns exact selected IDs.

## 14. Exhaustive Retrieval Plan

Expose `AdvancedRetrievalService` through `search_evidence(mode="exhaustive")` and HTTP `POST /v2/retrieval/evidence`.

Required request fields:

- query or exact predicate;
- notebook and optional source/document/version scope;
- requested representations;
- deterministic ordering policy;
- page/result/byte/scan budgets;
- cursor;
- expansion policy.

Required behavior:

- cursor-based enumeration over a stable declared universe;
- maximum page size 100;
- no raw storage offsets in the public contract;
- representation reports distinguish searched/unavailable/omitted/failed;
- no completeness upgrade after reranking/parent promotion;
- exhaustive natural-language text matching must define its match predicate; semantic similarity alone is not an enumerable truth predicate;
- title/document enumeration uses exact metadata projections, not top-k search.

## 15. Structured Retrieval Plan

Use the existing `StructuredQueryV1` and `StructuredRetrievalService`; add the missing operational path:

1. project typed CSV/XLSX/document-table data from exact parsed IR;
2. atomically promote a validated structured generation;
3. expose dataset/schema discovery;
4. compile client input only into allowlisted typed IR;
5. parameterize all values;
6. return row/cell provenance, candidate universe, matched/returned counts, completeness, and cursor;
7. support multi-dataset operations only through an explicit deterministic dataset union/join contract.

Initial supported joins should be conservative: union compatible schemas and equality joins on explicitly selected normalized fields. Fuzzy/entity joins remain Phase 11. CPI comparisons, ranges, top-N, count, average, and grouping are Phase 8.5 responsibilities.

HTTP: `POST /v2/retrieval/structured`; MCP: `query_structured`. Schema discovery can use the same operation with `operation="describe"` or a typed subcommand.

## 16. Multilingual Retrieval Plan

Operationalize the existing models and services:

- language/script observations on canonical, OCR, and derived text;
- BGE-M3 generation in an independent named 1024-dimensional space;
- BGE reranker profile for supported language directions;
- original Unicode sparse path plus independently generated transliteration/translation sparse paths;
- query-language detection and capability-aware path selection;
- rank fusion across language paths; no raw cross-space score mixing;
- answer-language policy only in Final-QA V2.

Every result reports original language/script, query language, path, any translation/transliteration derivation, provider/profile, generation, and fallback. Model installed/configured/generated/indexed/exposed/certified are separate capability states.

## 17. Multi-Document Retrieval Plan

Phase 8.5 supplies deterministic primitives, not an autonomous planner:

- resolve a bounded or exhaustive document set with exact title/metadata or explicit IDs;
- partition retrieval results per document with per-partition completeness;
- apply per-document quotas before optional global fusion;
- expose stable document-set snapshot identity;
- support structured unions/equality joins where schemas are explicitly compatible;
- return cross-document coverage and omitted/failed partitions;
- allow callers to request `require_complete=true`, which fails closed if any required partition is unavailable/truncated.

General entity linking, fuzzy joins, graph hops, and iterative evidence-gap replanning remain Phase 11.

## 18. Provenance/Security Plan

Every public candidate/item must retain:

```text
actor/request -> notebook -> source -> document -> exact version
  -> chunk OR asset occurrence
  -> derivation + generation/profile when derived
  -> retrieval path/rank/completeness
  -> delivery/context/citation/snapshot
```

Security invariants:

- reauthorize before recall, fusion, expansion, delivery, context, publication, and replay;
- shared hashes never widen access;
- no arbitrary paths, blob IDs, SQL, provider IDs, or cursor internals from clients;
- no content in logs;
- strict response, scan, pixel, token, row, page, asset, and time bounds;
- prompt/image/OCR/translation content is untrusted evidence;
- capability responses are scope-safe and do not leak resource existence;
- non-leaking not-found/forbidden mapping under authenticated profiles;
- cursor secrets are deployment-managed and rotatable.

## 19. MCP API Evolution Plan

### Compatibility

- Keep all ten existing tool names.
- Keep required legacy inputs and results accepted.
- Add optional selectors and enriched fields.
- Add four new tools only through a successor ADR and schema snapshots.
- Version V2 payloads; retain JSON text fallback for clients without structured-content support.

### Tool chain guidance

Tool descriptions must include positive and negative examples:

- “relevant information” -> ranked search;
- “all/every/how many” -> exhaustive or structured;
- “last/page/range/full” -> discover document then exact selector/traversal;
- “find image showing” -> multimodal evidence search;
- “show image” -> original asset delivery;
- “what does image contain” -> image analysis after occurrence discovery;
- “CPI > 8.9” -> structured query;
- “compare known documents” -> scoped multi-document retrieval;
- complex unknown joins -> return deterministic evidence for later Phase 11 planning.

Descriptions and schemas are necessary but not sufficient; blind behavioral tests are the acceptance criterion.

## 20. V1 Compatibility Strategy

- Freeze `RetrievalPlan`, `ScoredChunk`, V1 RRF/reranker/context/citations/Final-QA.
- Preserve `/v1/query`, `/v1/query/stream`, `/v1/search`, and six V1 MCP tools.
- New V2 services wrap V1 evidence; they never reinterpret V1 completeness as complete.
- Do not regenerate canonical chunks, FTS/title rows, or V1 embedding identities.
- Keep Qdrant optional and V1 sparse-only operation truthful.
- Restore the original `StorageInterfaceV1` surface via the ADR-0072 successor; concrete methods may remain for compatibility.
- Maintain old delivery cursor decoding only for its short compatibility window.
- Add schema snapshot and legacy-double tests before any adapter change.

## 21. Phase 11 Compatibility Strategy

Phase 11 receives only typed capabilities:

- `search_evidence` result sets with completeness/coverage;
- deterministic document-set resolution;
- positional expansion;
- structured result sets;
- multimodal candidates and provenance;
- immutable V2 evidence/snapshots;
- capability/readiness states;
- opaque continuation cursors.

Phase 11 must not receive SQLite table names, filesystem paths, raw model configuration, Qdrant collection names, or unsigned offsets. It may decompose and iterate, but it may not erase completeness, authority, derivation, or generation boundaries.

## 22. Work Package Breakdown

The packages below are independently reviewable but must follow the dependency graph in Section 32. “Files” are expected touch points, not permission for unrelated refactoring.

### WP-00 — Baseline, Authority, and Successor ADR Freeze

| Attribute | Plan |
|---|---|
| 1. Objective | Freeze corrected Phase 8.5 runtime/MCP contracts before code changes. |
| 2. Why required | Current ADR status prose, ADR-0072, runtime behavior, and certification claims conflict. |
| 3. Requirements | Authority map, frozen V1 boundary, tool/result contracts, Phase 11 boundary. |
| 4. Existing | ADR-0058–0072 and two reconciliation audits. |
| 5. Missing | Successor decisions and machine-readable capability contract. |
| 6. Files | New ADR-0073–0075; proposed API/MCP schemas under docs; no runtime initially. |
| 7. Interfaces | Define `Phase85RuntimeV1`, `DocumentScopeResolverV1`, V2 transport contracts. |
| 8. DB | None. |
| 9. Config | Define model-profile and cursor-secret precedence. |
| 10. MCP | Freeze retained ten plus four additive tools and output schemas. |
| 11. HTTP | Freeze advanced/structured/jobs/Final-QA V2 routes and positional expand route. |
| 12. Tests | Static schema/ADR contradiction checks. |
| 13. Security | Threat-model cursor, scope resolution, binary envelopes, capability leakage. |
| 14. Compatibility | Explicit V1/non-breaking matrix. |
| 15. Docs/ADR | ADR-0073 MCP-native capabilities; ADR-0074 runtime/profile activation; ADR-0075 supersedes ADR-0072 mechanism. |
| 16. Prior dependencies | None. |
| 17. Future dependencies | All work packages; Phase 11 consumes frozen result contracts. |
| 18. Definition of Done | Accepted contract set with no unresolved P0 ambiguity. |
| 19. Risks | Over-design or accidental Phase 11 scope. |
| 20. Complexity/independence | Medium; independently approvable and mandatory first. |

### WP-01 — Additive Phase 8.5 Runtime Composition

**Implementation status:** COMPLETE (2026-08-26). `Phase85RuntimeV1` is composed
once by `KnowledgeEngine`; later packages still own derived projection activation,
transport exposure, behavioral verification, and certification.

| Attribute | Plan |
|---|---|
| Objective/why | Compose existing services/providers once so server/scripts do not build divergent runtimes. |
| Requirements | Capability lifecycle, dependency injection, provider neutrality, optional backends. |
| Existing/missing | Stores and services exist; no unified engine-owned runtime or active provider adapters. |
| Files/modules | `mnemo-core/mnemo/engine.py`, new `mnemo/phase85/runtime.py`, provider registry/modules, engine tests. |
| Interfaces | `Phase85RuntimeV1`, service accessors, typed readiness snapshot. Do not widen `StorageInterfaceV1`. |
| DB/config | No schema; read explicit active profile and feature flags. |
| MCP/HTTP | Indirect dependency only; adapters consume runtime rather than instantiate services. |
| Tests | Composition with all capabilities, disabled dependencies, legacy storage doubles, startup/shutdown, no hidden provider calls. |
| Security | Provider trust/consent and authorization services mandatory dependencies. |
| Compatibility | V1 `_ResolvedProviders` and V1 engine paths unchanged. |
| Docs/ADR | ADR-0074 and composition diagram. |
| Dependencies | WP-00. |
| Future | Phase 10 workers/Phase 11 planner consume the same runtime. |
| DoD | A ready engine reports truthful operational services; disabled services remain typed unavailable. |
| Risks | Startup cost and mandatory model loading; mitigate lazy provider initialization. |
| Complexity/independence | High; can proceed independently after WP-00. |

### WP-02 — Derived Projection Build and Generation Activation

**Implementation status:** COMPLETE (2026-08-26). Schema v14 adds independent
Vision/language text projections, reusable multilingual-vector activation, immutable
coverage/source manifests, and the common build/validate/promote/rollback
lifecycle. Governed processing-job execution is implemented. No production or
evaluation-corpus projection was built by this work package; capability states
therefore remain inactive until an operator submits an exact configured build.

| Attribute | Plan |
|---|---|
| Objective/why | Turn persisted OCR/vision/vector/language/structured data into searchable active generations. |
| Requirements | ADR-0061–0063, 0067, 0071; side-by-side BUILDING→READY→active promotion. |
| Existing/missing | Tables/build primitives exist; current evaluation state has zero active/projection rows. |
| Files/modules | storage OCR/vision/multilingual/structured, new projection coordinator/builders, processing operations, migration tests. |
| Interfaces | `DerivedProjectionBuilderV1`, generation validator/promoter, coverage report. |
| DB | Add schema v14 only for `vision_text_projection_rows`/FTS and `language_text_projection_rows`/FTS if no equivalent exists; reuse OCR, visual, multilingual, structured tables. |
| Config | Per-capability enabled/profile/budgets and rebuild policy. |
| MCP/HTTP | Capability readiness consumes generation/coverage; no direct adapter in this WP. |
| Tests | Fresh/upgrade/repeat/rollback/interruption, checksum/count mismatch, inactive BUILDING, stale/rollback, optional Qdrant disabled. |
| Security | Notebook-scoped build inputs, no cross-tenant cache promotion. |
| Compatibility | No canonical rows or V1 collections changed. |
| Docs/ADR | ADR-0074/0071 implementation record; migration operator runbook. |
| Dependencies | WP-01. |
| Future | Supplies every derived retrieval source. |
| DoD | Each supported projection has a validated active generation and truthful coverage or explicit unavailable state. |
| Risks | Storage growth/partial generation; mitigate checksums, atomic aliases, resumable jobs. |
| Complexity/independence | High; parallelizable by modality after common lifecycle. |

### WP-03 — MCP Contract and Discoverability

**Implementation status:** COMPLETE (2026-08-26). The ten retained tools now
publish intent-oriented positive/negative guidance, additive structured output
schemas, completeness and continuation semantics, provenance-aware next actions,
and JSON text compatibility. The four additive definitions are frozen but are
not advertised before their WP-07/WP-08/WP-12/WP-13 services are callable.
External-client behavioral certification remains WP-16.

| Attribute | Plan |
|---|---|
| Objective/why | Make correct tool selection possible from tool metadata alone. |
| Requirements | Exact names/descriptions, negative guidance, output schemas, chains, typed errors. |
| Existing/missing | Ten inputs exist; descriptions are ambiguous and outputs unspecified. |
| Files/modules | `mnemo-server/mnemo_server/mcp/tools.py`, schema builders, conformance snapshots, MCP docs. |
| Interfaces | Transport-only DTOs mapped from domain results. |
| DB/config | None; expose configured limits. |
| MCP | Enrich ten existing definitions; register `search_evidence`, `query_structured`, `run_final_qa_v2`, `get_capabilities`. |
| HTTP | Keep schemas aligned with OpenAPI DTOs. |
| Tests | Exact schema snapshots, old-tool compatibility, descriptive lint rules, blind selection harness fixtures. |
| Security | Descriptions never encourage passing asset IDs as authority; errors sanitized. |
| Compatibility | Names/legacy required inputs unchanged; optional fields/output enrichment only. |
| Docs/ADR | ADR-0073 plus tool catalog/examples. |
| Dependencies | WP-00; final handlers depend on WP-05–WP-13. |
| Future | Phase 11 planner consumes semantic contracts, not implementation knowledge. |
| DoD | A tool-only evaluator selects the correct tool family for the canonical intent set. |
| Risks | Client schema support variation; provide structured content plus JSON fallback. |
| Complexity/independence | Medium; definition work independent, handler completion dependent. |

### WP-04 — Cursor and Completeness Unification

**Implementation status:** COMPLETE (2026-08-27). `CursorCodecV2` now provides
canonical domain-separated HMAC cursors with explicit format and key IDs, TTL,
active/overlap-key rotation, immutable snapshot and request/budget binding, and
typed invalid/expired/conflict failures. Advanced retrieval and bounded
document/original/asset/inventory/Final-QA delivery issue V2 cursors. Delivery
accepts V1 cursors only through a process-stable configured overlap deadline.
The shared transport coverage mapper cannot upgrade omissions or unavailable
paths to `complete`. Focused evidence is recorded in
`PHASE_8_5_WP_04_GATE_EVIDENCE.md`; external-agent certification remains WP-16.

| Attribute | Plan |
|---|---|
| Objective/why | Make continuation secure, expiring, consistent, and impossible to mistake for completeness. |
| Requirements | Signed opaque cursor, stable snapshot, expiry, bounds, representation coverage. |
| Existing/missing | Advanced cursor expires; delivery cursor does not; enums and envelopes differ. |
| Files/modules | new cursor utility/models, advanced retrieval, delivery, structured adapters, server error mapping/config. |
| Interfaces | Domain-separated `CursorCodecV2`, shared transport completeness/coverage DTO. |
| DB | None unless server-side snapshots are required; prefer immutable snapshot hashes. |
| Config | Secret/key ID, TTL, rotation overlap; production validation. |
| MCP/HTTP | Uniform cursor field descriptions and stale/expired/conflict errors. |
| Tests | Tamper, expiry, rotation, wrong scope/query/version/generation, resume, mutation, terminal completeness. |
| Security | Reject default secret in authenticated production; reauthorize every page. |
| Compatibility | Decode legacy delivery v1 tokens temporarily; issue v2 only. |
| Docs/ADR | ADR-0073/0065 implementation update. |
| Dependencies | WP-00; supports WP-05–WP-13. |
| Future | Phase 11 treats cursors as opaque resumable state. |
| DoD | No code path can emit complete before proven exhaustion or reuse a cursor across scope/snapshot. |
| Risks | Cursor invalidation during rollout; bounded dual decoder. |
| Complexity/independence | Medium-high; independent common foundation. |

### WP-05 — Exact and Positional Document Retrieval

**Implementation status:** COMPLETE (2026-08-27). See `PHASE_8_5_WP_05_GATE_EVIDENCE.md`.

| Attribute | Plan |
|---|---|
| Objective/why | Support full/page/range/section/tail/adjacency intents without semantic approximation. |
| Requirements | Exact version, typed selectors, canonical order, bounds, resume. |
| Existing/missing | Forward block expansion exists; selector union/from-end/page targeting absent. |
| Files/modules | delivery models/service/interface, parsed-IR readers, server schemas/routes, MCP handler. |
| Interfaces | Add `DocumentExpansionServiceV2`; adapt V1 delivery service. |
| DB | None initially; parsed IR and canonical positions suffice. Add projection only if measured performance requires it. |
| Config | Page/block/token/byte ceilings. |
| MCP/HTTP | Optional `selector` on `get_document`; new typed POST expand route; output positions and next actions. |
| Tests | Every selector, absent metadata, ambiguous anchor, end-of-document, interrupted resume, exact version conflict. |
| Security | Scope/selector/cursor bound, no full unbounded dump. |
| Compatibility | Existing GET and MCP no-selector behavior preserved. |
| Docs/ADR | ADR-0073 extends ADR-0065/0066. |
| Dependencies | WP-04, WP-14 scope resolver. |
| Future | Deterministic Phase 11 expansion primitive. |
| DoD | Blind agent succeeds on last/page/range/full requests with exact provenance/completeness. |
| Risks | Formats lack page semantics; return typed unavailable, never fabricate. |
| Complexity/independence | High; independent of derived models. |

### WP-06 — Asset Inventory, Derivation Discovery, and Binary Delivery

**Implementation status:** COMPLETE (2026-08-27). Authorized occurrence-scoped
derivation descriptors now enrich bounded asset inventory; explicit,
`latest_ready`, and `all` analysis selection resolve immutable IDs without
guessing. HTTP and MCP preserve binary provenance and range metadata, and MCP
emits `ImageContent` only for complete recognizable raster media. See
`PHASE_8_5_WP_06_GATE_EVIDENCE.md`.

| Attribute | Plan |
|---|---|
| Objective/why | Complete occurrence→original→analysis composition and fix binary envelopes. |
| Requirements | Occurrence auth, derivation listing/selection, original-vs-derived labels, safe ranges. |
| Existing/missing | Direct delivery works; inventory lacks derivations; MCP image drops metadata; partial image risk. |
| Files/modules | asset catalog additive interfaces/store, delivery models/service, HTTP/MCP adapters/tests. |
| Interfaces | `AuthorizedAssetAnalysisCatalogV1`; `AssetDeliveryV2`; selection by ID/profile/latest-ready. |
| DB | Reuse existing tables/indexes; add indexes only if query plan proves need. |
| Config | Image/aggregate bytes, assets, pixels, analysis item limits. |
| MCP/HTTP | Enrich inventory; safe analysis selector; provenance-bearing resource metadata. |
| Tests | Known/duplicate occurrence, shared hash isolation, partial binary, malformed MIME, no derivation/latest/all, stale generation. |
| Security | Never bare asset/derivation authorization; no storage URI/path leakage. |
| Compatibility | Keep legacy `get_asset` modes and explicit derivation IDs valid. |
| Docs/ADR | ADR-0073; clarify ADR-0066 behavior. |
| Dependencies | WP-04, WP-14. |
| Future | Phase 11 receives occurrence-addressed resources. |
| DoD | Inventory alone supplies all identifiers needed for authorized original and analysis delivery; partial media is never mislabeled complete. |
| Risks | Large inventories; cursor and aggregate bounds. |
| Complexity/independence | Medium-high; independent of semantic search. |

### WP-07 — Advanced Ranked/Exhaustive Retrieval Exposure

**Implementation status:** COMPLETE (2026-08-27). The production composition
root now binds the canonical advanced source, V1 sparse retriever/reranker,
scope-first SQLite enumeration, signed `CursorCodecV2` continuation, bounded
application DTO/service, `POST /v2/retrieval/evidence`, and MCP
`search_evidence`. Canonical text is active; unavailable requested derived
representations remain explicit and prevent false completeness. See
`PHASE_8_5_WP_07_GATE_EVIDENCE.md`.

| Attribute | Plan |
|---|---|
| Objective/why | Operationalize ADR-0058 and stop using top-k for “all.” |
| Requirements | Explicit mode/scope/representations/budgets/cursor/coverage. |
| Existing/missing | Core service/tests exist; only canonical source and no adapters/composition. |
| Files/modules | runtime composition, advanced sources, server service/schemas/routes, MCP handler. |
| Interfaces | Existing `AdvancedRetrievalInterfaceV1`; add application service/authorizer. |
| DB | Reuse advanced canonical store and active generations. |
| Config | Recall/scan/page/byte/time defaults and hard ceilings. |
| MCP/HTTP | `search_evidence`; `POST /v2/retrieval/evidence`. |
| Tests | Ranked bounded, exhaustive terminal, cursor resume, unavailable representations, exact title, multi-doc scope, explosion bounds. |
| Security | Scope before enumeration; constant-safe error mapping. |
| Compatibility | V1 search unchanged and explicitly bounded. |
| Docs/ADR | ADR-0073 implementation status. |
| Dependencies | WP-01, WP-02, WP-04, WP-14. |
| Future | Primary Phase 11 retrieval primitive. |
| DoD | “Every matching canonical item” is complete only after stable terminal traversal; unavailable derived sources are explicit. |
| Risks | Semantic exhaustive ambiguity; require typed predicate/declared match semantics. |
| Complexity/independence | High; can launch canonical-only before derived sources, but cannot advertise multimodal complete. |

### WP-08 — Structured Projection and Query Exposure

**Implementation status:** Complete 2026-08-27. Production composition, exact
authorized dataset/schema discovery, the strict transport compiler, conservative
union/equality join, bounded application service, HTTP/MCP adapters, and hard
scan/output/time limits are implemented. Runtime activation remains conditional
on a complete active structured generation; the currently configured evaluation
database has none and is truthfully inactive rather than reported as empty.

| Attribute | Plan |
|---|---|
| Objective/why | Make numeric/filter/group/aggregate queries exact and complete. |
| Requirements | Typed schema, exact-version datasets, safe compiler, row/cell provenance. |
| Existing/missing | Models/service/store/tests exist; current projection empty; no adapter. |
| Files/modules | structured projector/store/service, runtime, server DTO/service/route, MCP handler. |
| Interfaces | Existing `StructuredRetrievalInterfaceV1`; add dataset catalog/union interface. |
| DB | Reuse structured tables and generation lifecycle. |
| Config | Row/field/group/evidence/output/time budgets. |
| MCP/HTTP | `query_structured`; `/v2/retrieval/structured`. |
| Tests | CPI predicates/ranges/top-N/count/avg/group, null/type ambiguity, injection, cursor, compatible union/equality join. |
| Security | No SQL/expression injection; authorize every dataset/version/cell. |
| Compatibility | Canonical table chunks/FTS unchanged. |
| Docs/ADR | ADR-0063 implementation correction and API docs. |
| Dependencies | WP-01, WP-02, WP-04, WP-14. |
| Future | Phase 11 may choose datasets/joins but cannot execute raw SQL. |
| DoD | Known-truth structured fixture answers match exactly with complete provenance. |
| Risks | Ambiguous schemas; fail typed instead of guessing. |
| Complexity/independence | High; independent of visual/multilingual work. |

### WP-09 — OCR/Vision/Visual Multimodal Search

| Attribute | Plan |
|---|---|
| Objective/why | Make image descriptions, OCR text, and visual similarity discover occurrences naturally. |
| Requirements | Typed sources, named spaces, rank fusion, coverage, original occurrence auth. |
| Existing/missing | Derivation/provider/fusion models exist; WP-09 adds generation-gated semantic sources and runtime composition; active projection/provider state remains environment-dependent. |
| Files/modules | OCR/vision projection sources, multimodal fusion, runtime, `search_evidence` adapter, provider adapters. |
| Interfaces | Advanced sources for OCR text, vision text, visual vector; shared-space text→image provider only where certified. |
| DB | WP-02 v14 text projections; existing visual vectors/generations. |
| Config | Active OCR/Vision/visual profiles and capability-specific bounds. |
| MCP/HTTP | `search_evidence(representations=[...])`; direct delivery remains separate. |
| Tests | Standalone/embedded image search, repeated occurrences, OCR phrase, diagram description, incompatible spaces, partial coverage. |
| Security | Reauthorize before source recall and after fusion; prompt content never instructions. |
| Compatibility | No derived text in canonical FTS/chunks. |
| Docs/ADR | ADR-0061/0062/0064 operational status. |
| Dependencies | WP-02, WP-06, WP-07, WP-14. |
| Future | Phase 11 can reason across returned typed modalities. |
| DoD | Natural-language image query discovers correct authorized occurrence and composes to original/analysis delivery. |
| Risks | Sparse coverage/quality; capability reports exact coverage and never claims complete. |
| Complexity/independence | Very high; parallelize OCR text, vision text, and visual-vector sources. |

### WP-10 — Multilingual Retrieval Activation

| Attribute | Plan |
|---|---|
| Objective/why | Make EN/HI/MR same/cross-language retrieval operational through certified profiles. |
| Requirements | Detection, named vector/analyzer generations, reranking, provenance, fallback. |
| Existing/missing | Stage 1 (2026-08-29) supplies typed source provenance, offline exact-profile BGE-M3/reranker adapters, conservative detection, deterministic generation builders, bounded SQLite dense retrieval, and injection seams into the shared engine. No multilingual generation is active, so runtime exposure remains unavailable until Stage 2 evidence. |
| Files/modules | multilingual providers/store/service/runtime, profile registry, server DTO mapping. |
| Interfaces | Existing multilingual interfaces; source adapters into `search_evidence`. |
| DB | Reuse multilingual tables; WP-02 language FTS if accepted. |
| Config | Explicit active multilingual profile/revision/dimensions/language coverage. |
| MCP/HTTP | Query language/answer policy fields and language coverage in results/capabilities. |
| Tests | Six direction pairs, same-language, mixed script, transliteration, OCR path, unavailable/fallback, title provenance. |
| Security | Translation/OCR untrusted; governed cloud/local processing. |
| Compatibility | V1 embedding/reranker/index untouched. |
| Docs/ADR | ADR-0074 profile activation; ADR-0067 operational evidence. |
| Dependencies | WP-01, WP-02, WP-07, WP-14, WP-15 config. |
| Future | Phase 11 consumes language-labeled candidates. |
| DoD | Per-direction live MCP metrics meet separately governed pinned profile thresholds and report path/fallback truthfully. Stage 1 is BUILDABLE only; it cannot claim READY, ACTIVE, EXPOSED, VERIFIED, or CERTIFIED. |
| Risks | Hardware/model latency; lazy loading and bounded rerank sets. |
| Complexity/independence | High; independent after runtime/profile foundation. |

### WP-11 — Deterministic Multi-Document Retrieval

| Attribute | Plan |
|---|---|
| Objective/why | Support complete bounded comparisons without general agentic planning. |
| Requirements | Document-set resolution, partition quotas, per-partition completeness, deterministic union/join. |
| Existing/missing | Scope supports document IDs; WP-11 adds a public partitioned result contract over the existing retrieval service. |
| Files/modules | advanced models/service, document resolver, structured union/join, server DTOs. |
| Interfaces | `DocumentSetResolverV1`, `PartitionedRetrievalResultV1`. |
| DB | None beyond existing projections. |
| Config | Max documents/partitions/evidence/bytes/time. |
| MCP/HTTP | `search_evidence` scope and partition options; `query_structured` multi-dataset options. |
| Tests | Known docs, exhaustive title resolution, partial partition, quotas, all-doc enumeration, exact equality joins. |
| Security | Authorize every partition; do not reveal omitted unauthorized docs. |
| Compatibility | V1 global fusion unchanged. |
| Docs/ADR | ADR-0073; Phase 11 boundary. |
| Dependencies | WP-05, WP-07, WP-08, WP-14. |
| Future | Phase 11 supplies decomposition/replanning over this primitive. |
| DoD | Bounded and exhaustive comparisons expose per-document evidence/provenance/completeness. |
| Risks | Candidate explosion; hard partition budgets and cursor. |
| Complexity/independence | High; depends on retrieval surfaces. |
| Status | COMPLETE (focused implementation and regression evidence recorded in `PHASE_8_5_WP_11_GATE_EVIDENCE.md`; Phase 8.5 certification remains open). |

### WP-12 — Final-QA V2 Operational Composition

| Attribute | Plan |
|---|---|
| Objective/why | Expose the already-designed typed multimodal QA/publication/replay path. |
| Requirements | ADR-0054/0056 exact reuse, typed evidence, completeness policy, immutable replay. |
| Existing/missing | Orchestrator/store/tests exist; no normal engine/HTTP/MCP execution path. |
| Files/modules | runtime composition, multimodal retrieval/context/provider, server Final-QA V2 service/DTO/route/MCP. |
| Interfaces | Existing `FinalQAInterfaceV2`; capability negotiation and execution resolver. |
| DB | Reuse schema v12 multimodal snapshots. |
| Config | Active provider profile, evidence budgets, complete/partial publication policy. |
| MCP/HTTP | `run_final_qa_v2`; `POST /v2/notebooks/{id}/final-qa`; existing evidence GET retained. |
| Tests | Citation case, one retry, exhaustion/no publish, replay zero generation, conflict, crash, concurrent claim, unauthorized/stale evidence. |
| Security | Reauthorize snapshot/replay; untrusted derived evidence delimiters. |
| Compatibility | V1 Final-QA and citation grammar unchanged. |
| Docs/ADR | ADR-0064/0069 operational status. |
| Dependencies | WP-07–WP-11, WP-14. |
| Future | Phase 11 may supply a plan/result set, not bypass publication rules. |
| DoD | Live V2 execution publishes only compliant typed evidence and replays with zero provider calls. |
| Risks | Provider capability mismatch/context overflow; fail closed with typed partial/unavailable. |
| Complexity/independence | Very high; last functional package before adapter certification. |
| Status | COMPLETE (transport execution/replay, capability, completeness, citation, multimodal, multilingual, and zero-provider-call replay evidence recorded in `PHASE_8_5_WP_12_GATE_EVIDENCE.md`; Phase 8.5 certification remains open). |

### WP-13 — HTTP V2 and Capability Surface Completion

| Attribute | Plan |
|---|---|
| Objective/why | Fulfill ADR-0069 and ensure HTTP/MCP share application services and errors. |
| Requirements | Advanced/structured/jobs/Final-QA V2, capability/readiness, bounds, cancellation. |
| Existing/missing | Delivery routes only. |
| Files/modules | server routers/schemas/services/app/dependencies/error handlers/OpenAPI tests. |
| Interfaces | Thin adapters over `Phase85RuntimeV1`; no domain logic in routes. |
| DB | None. |
| Config | All public limits and feature flags exposed redacted. |
| MCP/HTTP | Complete routes plus common response/error schemas; MCP handlers reuse services. |
| Tests | OpenAPI snapshots, auth, invalid UUID, errors, streaming/disconnect where specified, job lifecycle. |
| Security | Authentication/authorization before work; safe errors/CORS/rate/bounds. |
| Compatibility | V1 routes and streaming byte-for-byte schema compatible. |
| Docs/ADR | ADR-0069 implementation correction. |
| Dependencies | WP-01–WP-12. |
| Future | Phase 9 consumes stable V2 DTOs. |
| DoD | Every capability claimed by ADR-0069 has a live adapter or truthful disabled/unavailable state. |
| Risks | Duplicated orchestration; enforce shared application services. |
| Complexity/independence | High; adapter work parallelizable after service contracts settle. |
| Status | COMPLETE (runtime-derived HTTP/MCP capability discovery, strict lifecycle/dependency/generation/profile metadata, deterministic parity, redaction, and blind-agent guidance evidence recorded in `PHASE_8_5_WP_13_GATE_EVIDENCE.md`; WP-14 security verification is complete, while WP-16/WP-17 remain pending). |

### WP-14 — Authorization, Scope Resolution, and Security Closure

**Implementation status:** COMPLETE (2026-08-28). ADR-0075 additive document
scope resolution now replaces the accidental frozen-storage-protocol widening;
server-owned principals flow through shared V2 application services, cursor
fingerprints bind actor scope, exact evidence/occurrence/derivation chains are
reauthorized, and the focused Section 28 threat matrix has no open P0/P1 issue.
Final behavioral and Phase 8.5 certification remain WP-16 and WP-17.

| Attribute | Plan |
|---|---|
| Objective/why | Preserve isolation across all new search/delivery/composition paths and repair ADR-0072 drift. |
| Requirements | Actor/notebook/source/version/occurrence/derivation chain, non-leaking errors. |
| Existing/missing | Occurrence authorizer exists; MCP lacks actor-level ownership model; resolver is on frozen storage protocol. |
| Files/modules | new scope resolver protocol/service, authorization services, storage/composite compatibility, middleware/context. |
| Interfaces | `DocumentScopeResolverV1`, `EvidenceAuthorizerV2`, request principal context. |
| DB | No schema unless future ownership exists; honor current notebook scope. |
| Config | Authenticated production requirements and cursor secret validation. |
| MCP/HTTP | Common authorizer/error mapping for every new call. |
| Tests | Cross-notebook/shared hash/cache/cursor/derivation, revoked access, enumeration leakage, symlink/path/MIME/bombs/injection. |
| Security | This WP owns the threat matrix and fail-closed review. |
| Compatibility | Restore frozen protocol; retain concrete lookup compatibility. |
| Docs/ADR | ADR-0075 supersedes ADR-0072 mechanism. |
| Dependencies | WP-00; consulted by every package. |
| Future | Phase 11 never bypasses authorization during iterative retrieval. |
| DoD | No candidate/resource/result crosses scope, and legacy storage doubles remain valid. |
| Risks | Current auth has no full principal ownership model; do not invent Phase 13 multi-user policy, but carry actor context consistently. |
| Complexity/independence | High; implement early and test continuously. |

### WP-15 — Configuration, Model Profiles, and V1 Migration Compatibility

**Implementation status:** COMPLETE (2026-08-28). The tracked strict profile
document, deterministic precedence, immutable runtime snapshot, exact
profile/generation binding, redacted capability exposure, and V1-only/disabled
startup paths are implemented and focused-tested. See
`PHASE_8_5_WP_15_GATE_EVIDENCE.md`. WP-16 behavioral validation and WP-17 final
certification remain pending.

| Attribute | Plan |
|---|---|
| Objective/why | Establish one reproducible active Phase 8.5 profile without changing V1 defaults. |
| Requirements | Provider/revision/dimension/trust/capability identity and explicit precedence. |
| Existing/missing | `ModelsConfig` and inline TOML exist; referenced standalone profile is missing; providers not composed. |
| Files/modules | core config/profile registry, sample/operator configs, engine composition, config endpoint/tests. |
| Interfaces | `ModelProfileRegistryV1`, immutable active profile snapshot. |
| DB | Generation metadata binds resolved profile; no canonical migration. |
| Config | Explicit profile file/name, inline legacy fallback, env overrides, paths via env—not hard-coded D:. |
| MCP/HTTP | Capability output includes resolved profile ID/revision/readiness, never secrets/paths. |
| Tests | Precedence, missing model, dimension mismatch, stale generation, redaction, V1-only profile. |
| Security | No credentials/paths in manifests or public capability payloads. |
| Compatibility | Current V1 embedding/reranker remain default for V1; Phase 8.5 profile applies only to V2. |
| Docs/ADR | ADR-0074; operator configuration guide. |
| Dependencies | WP-00, WP-01. |
| Future | Phase 12 plugin providers register against profile interface. |
| DoD | One command/config deterministically resolves every active Phase 8.5 provider and matching generation. |
| Risks | Model download/startup cost; validation is lazy and capability-specific. |
| Complexity/independence | Medium-high; independent of retrieval implementation after registry contract. |

### WP-16 — External-Agent Behavioral Validation

**Implementation status:** PARTIAL (2026-08-28). The strict 31-case manifest,
bounded public-MCP runner, independent deterministic oracle, failure taxonomy,
mutation tests, MCP session adapter, redacted summaries, and external-client
operator procedure are implemented. A checksum-pinned disposable evaluation
copy now has complete active structured (105 tables), OCR (14 rows), Vision-text
(26 rows), and visual-vector (16 rows) generations. The exact frozen BGE/CLIP
snapshots and Ollama artifacts were located in the operator-owned D: stores and
verified locally without substitution. Engine/runtime readiness and HTTP/MCP
capability discovery now succeed, and both real MCP transports advertise the
same 14 tools. Multilingual generations remain absent because the database has
no language-derivation/embedding source rows and the repository has no
production implementation/composition of the frozen multilingual provider
protocols. No safely controllable ChatGPT/Antigravity session produced a
transcript, so no case is labeled behaviorally verified from model, projection,
harness, transport, or direct API evidence alone.

| Attribute | Plan |
|---|---|
| Objective/why | Prove autonomous clients choose and compose tools from metadata alone. |
| Requirements | Blind requests, no preselected IDs/chains, exact/completeness/provenance oracles. |
| Existing/missing | Direct-call matrices exist; no blind behavior gate. |
| Files/modules | new evaluation harness/manifests, MCP stdio/SSE runner, recorded client transcripts/results. |
| Interfaces | Uses only public MCP schemas/resources. |
| DB | Isolated evaluation copy; Golden Corpus read-only. |
| Config | Deterministic client/provider profiles, run IDs, budgets. |
| MCP/HTTP | Both MCP transports; selected HTTP cross-checks. |
| Tests | Section 27 matrix plus negative/security cases. |
| Security | No secrets/content logs; redact opaque IDs in published summaries where needed. |
| Compatibility | Run six V1 and ten-tool legacy matrix alongside new tools. |
| Docs/ADR | ADR-0070 evaluation addendum; new post-fix behavioral report. |
| Dependencies | WP-03–WP-15. |
| Future | Baseline for Phase 11 planner comparison. |
| DoD | Required blind success thresholds and zero false-completeness/security failures. |
| Risks | Client nondeterminism; repeat bounded trials and separate API correctness from selection quality. |
| Complexity/independence | High; harness can be designed early, executed late. |

### WP-17 — Documentation, Governance, and Final Phase 8.5 Certification

| Attribute | Plan |
|---|---|
| Objective/why | Make implementation, docs, ADRs, reports, config, and claims agree. |
| Requirements | G0–G10 plus new behavioral closure; historical preservation. |
| Existing/missing | Many historical gates; current active claims overstate readiness. |
| Files/modules | README, architectures, roadmaps, ADR index/new ADRs, changelog, operator/API/MCP docs, new final certification. |
| Interfaces/DB/config | Document final frozen contracts/schema/profile; no new behavior. |
| MCP/HTTP | Publish exact schemas, examples, limitations, capability matrix. |
| Tests | Full suite once, coverage, Ruff, mypy, builds, diff/docs links, live protocol matrix, read-only Golden Corpus. |
| Security | Final independent threat closure and artifact sanitization. |
| Compatibility | Explicit Phase 0–8/V1 evidence. |
| ADR implications | Accept successors; never rewrite historical reports. |
| Dependencies | WP-00–WP-16. |
| Future | Formal Phase 11 entry gate. |
| DoD | Section 34 entirely green and a truthful final report approved. |
| Risks | Repeating unsupported claims; generate evidence from artifacts and mark unavailable honestly. |
| Complexity/independence | High validation cost; not independent and always last. |

## 23. Task-Level Implementation Plan

Each task row specifies goal; expected files/modules; inputs → outputs; dependencies; and acceptance/test method. Exact filenames may be refined within the named module, but architectural ownership may not move without ADR review.

### WP-00 tasks

| Task | Goal and files | Inputs → outputs | Dependencies | Acceptance/test |
|---|---|---|---|---|
| 00.1 | Freeze the authority matrix in new successor ADR rationale; `docs/adr/ADR-0073...0075`, ADR index | Existing ADRs/audits → explicit precedence and contradictions | None | Link/status/duplicate-number static check |
| 00.2 | Freeze MCP-native contracts in ADR-0073 | Existing ten tools + original architecture → retained/additive tool set, schemas, negative guidance | 00.1 | Contract review covers every intent in Section 27 |
| 00.3 | Freeze runtime/profile activation in ADR-0074 | Core services/config drift → `Phase85RuntimeV1` and profile lifecycle | 00.1 | No mandatory Qdrant/cloud/V1 change |
| 00.4 | Supersede ADR-0072 mechanism in ADR-0075 | Useful behavior + frozen-interface conflict → additive scope resolver | 00.1 | Legacy storage interface signature snapshot matches pre-0072 contract |
| 00.5 | Create machine-readable proposed capability matrix under test fixtures/docs | Requirements → capability, owner, dependency, exposure, readiness rules | 00.2–00.4 | Schema validation and no unsupported PASS states |
| 00.6 | Approve package dependency graph and non-goals | This plan → signed implementation boundary | 00.1–00.5 | Architecture review has no unresolved P0 decisions |

### WP-01 tasks

| Task | Goal and files | Inputs → outputs | Dependencies | Acceptance/test |
|---|---|---|---|---|
| 01.1 | Define `Phase85RuntimeV1`; new core interface/runtime module | Store/provider protocols → immutable service bundle | 00.3 | Protocol/unit typing tests |
| 01.2 | Add lazy provider/profile resolver | `MnemoConfig.models`/registry → resolved optional OCR/Vision/visual/multilingual providers | 15.1 contract | Missing provider yields typed unavailable and no startup failure for V1 |
| 01.3 | Compose authorizers, cursor codecs, sources, services | Storage/catalog/providers → advanced/structured/multilingual/multimodal services | 01.1, 14.1 | Composition unit test asserts exact dependencies |
| 01.4 | Expose runtime from `KnowledgeEngine` additively | Runtime bundle → `engine.phase85` or equivalent | 01.3 | V1 engine properties/tests unchanged |
| 01.5 | Add lifecycle/startup/shutdown hooks | Lazy providers → deterministic resource lifecycle | 01.2–01.4 | No model load until capability used; shutdown idempotent |
| 01.6 | Add disabled/partial capability composition | Feature flags/dependency state → typed readiness snapshot | 01.4 | Matrix tests for Qdrant off, no model, no generation |
| 01.7 | Migrate scripts to composition root where appropriate | Evaluation-only constructors → shared runtime calls | 01.4 | Script results use same profile/service IDs; no duplicate architecture |

### WP-02 tasks

| Task | Goal and files | Inputs → outputs | Dependencies | Acceptance/test |
|---|---|---|---|---|
| 02.1 | Inventory existing projection schemas/builders | Schema v13/services → exact reuse/missing-table record | 00.5 | Static matrix signed off before migration |
| 02.2 | Define `DerivedProjectionBuilderV1` and coverage DTO | Derivations/generation policy → build/validate/promote/report contract | 01.1 | Unit state-machine tests |
| 02.3 | Add schema v14 only for missing Vision/Language text projections | v13 DB → additive FTS rows/indexes and schema version | 02.1 | Fresh/v13 upgrade/repeat/failure rollback |
| 02.4 | Implement OCR projection builder | Ready OCR derivations → `ocr_projection_rows`/`ocr_fts` generation | 02.2 | Counts, checksums, region provenance, idempotency |
| 02.5 | Implement Vision text projection builder | Ready Vision results → independent text FTS generation | 02.3 | No canonical FTS mutation; invalid payload rejected |
| 02.6 | Implement visual-vector generation builder | Valid embeddings → named SQLite/Qdrant-optional projection | 02.2 | Dimension/NaN/space/generation tests |
| 02.7 | Implement multilingual text/vector builders | Observations/derivations/vectors → named active generations | 02.3 | Language/profile/cache/provenance tests |
| 02.8 | Operationalize structured projector | Exact parsed tables → structured projection generation | 02.2 | Known row/schema counts and cell provenance |
| 02.9 | Add processing-job operations for build/rebuild | Manifest → resumable checkpointed builds | 02.4–02.8 | Crash/cancel/retry/stale-worker tests |
| 02.10 | Add atomic validation/promotion/rollback and coverage | Built rows/checksums → READY active alias or FAILED | 02.9 | Interrupted BUILDING never served; rollback selects prior generation |

### WP-03 tasks

| Task | Goal and files | Inputs → outputs | Dependencies | Acceptance/test |
|---|---|---|---|---|
| 03.1 | Create reusable MCP input/output schema definitions | Domain DTOs → JSON Schemas with descriptions/examples | 00.2 | Schema validation and snapshot tests |
| 03.2 | Rewrite descriptions for ten retained tools | Intent taxonomy → positive/negative guidance | 03.1 | Description lint checks ranked/full/all/image distinctions |
| 03.3 | Add `outputSchema`/structured content with fallback | Response DTOs → typed MCP results + JSON text compatibility | 03.1 | Old client and structured client conformance |
| 03.4 | Define/register `search_evidence` | V2 retrieval request/result → MCP tool | 07.4 | Ranked/exhaustive schema and direct tests |
| 03.5 | Define/register `query_structured` | Structured query/result → MCP tool | 08.5 | Filter/aggregate schema/direct tests |
| 03.6 | Define/register `run_final_qa_v2` | V2 QA request/result/replay → MCP tool | 12.4 | Citation/replay direct tests |
| 03.7 | Define/register `get_capabilities` | Runtime readiness → MCP tool and resource parity | 13.2 | Tool/resource identical semantic snapshot |
| 03.8 | Add recommended next-action objects | Result state → safe next tool/required IDs/cursor | 03.3–03.7 | No recommendation can widen scope or hide incompleteness |
| 03.9 | Freeze all tool schema compatibility snapshots | Old/new definitions → versioned fixtures | 03.2–03.8 | Six V1 exact snapshots; four legacy delivery inputs accepted |

### WP-04 tasks

| Task | Goal and files | Inputs → outputs | Dependencies | Acceptance/test |
|---|---|---|---|---|
| 04.1 | Define shared cursor envelope and errors | Existing codecs/ADRs → domain-separated v2 contract | 00.2 | Canonical serialization/property tests |
| 04.2 | Implement HMAC codec with TTL/key ID/rotation | Secret policy + envelope → opaque signed cursor | 04.1 | Tamper, expiry, future issuance, wrong key tests |
| 04.3 | Adapt advanced retrieval cursor | Existing advanced state → v2 envelope | 04.2 | Existing exhaustive tests plus compatibility |
| 04.4 | Adapt delivery cursor with legacy decoder | Existing offset token → v2 stable-key token | 04.2 | Old cursor accepted during window; new cursor expires |
| 04.5 | Adapt structured/asset/binary cursors | Result offsets/ranges → domain-bound v2 cursors | 04.2 | Cross-domain replay rejection |
| 04.6 | Define completeness/coverage transport mapper | Domain enums/reports → lossless common DTO | 04.1 | Exhaustive matrix, unavailable!=empty, ranked=bounded |
| 04.7 | Enforce production secret configuration | Auth/profile config → startup validation | 15.2 | Authenticated server rejects built-in secret |

### WP-05 tasks

| Task | Goal and files | Inputs → outputs | Dependencies | Acceptance/test |
|---|---|---|---|---|
| 05.1 | Define selector union and `DocumentExpansionServiceV2` | ADR-0065 design → full/page/slide/sheet/block/chunk/section/from-end/adjacent models | 00.2 | Validation/serialization tests |
| 05.2 | Build exact-version parsed-block position index in memory | Parsed IR → deterministic physical positions | 05.1 | Format fixtures; no fabricated page data |
| 05.3 | Implement range and section selectors | Positions → bounded typed blocks | 05.2 | Inclusive boundary/empty/out-of-range tests |
| 05.4 | Implement from-end selector | Stable positions + kind filter → forward-ordered tail | 05.2 | Last page/paragraph/sentence fixture or typed unavailable |
| 05.5 | Implement adjacency selector | Exact anchor → same-version before/after items | 05.2 | Ambiguous/missing/cross-version rejection |
| 05.6 | Bind selectors to cursor/snapshot | Selector + IR digest → resumable response | 04.4, 05.3–05.5 | Interrupt/resume/version mutation/stale IR tests |
| 05.7 | Add HTTP typed expand route | Selector DTO → service response | 05.6 | OpenAPI/live route tests |
| 05.8 | Extend MCP `get_document` optionally | Legacy inputs + selector → same service | 05.6, 03.2 | Blind last/page/full behavior fixtures |
| 05.9 | Add output positions/overlapping chunks/assets | Parsed items → provenance-rich delivery items | 06.2 | Attribution and ordering tests |

### WP-06 tasks

| Task | Goal and files | Inputs → outputs | Dependencies | Acceptance/test |
|---|---|---|---|---|
| 06.1 | Add authorized derivation-list protocol/store query | Occurrence/modality/profile → ready/stale/failed derivation descriptors | 14.1 | Scope/version/status/generation tests |
| 06.2 | Enrich asset inventory | Occurrences + asset + derivations → complete inventory items | 06.1 | Repeated assets and physical ordering |
| 06.3 | Add analysis selector/resolver | Explicit/latest/all request → immutable authorized IDs | 06.1 | Deterministic tie and stale/unavailable tests |
| 06.4 | Create provenance-bearing binary resource DTO | `BinaryDelivery` → resource metadata + bytes/range | 04.5 | Hash/MIME/length/attribution round trip |
| 06.5 | Prevent partial `ImageContent` | Bounded binary → complete image or range resource, never invalid image | 06.4 | Oversized PNG/JPEG decoding regression |
| 06.6 | Update HTTP/MCP handlers | Enriched service → adapters | 06.2–06.5, 03.3 | Valid/invalid/missing/auth/error matrix |
| 06.7 | Add all-images bounded traversal | Document selector → occurrence pages and aggregate bounds | 06.2, 04.5 | Max count/bytes/cursor/omission tests |

### WP-07 tasks

| Task | Goal and files | Inputs → outputs | Dependencies | Acceptance/test |
|---|---|---|---|---|
| 07.1 | Compose canonical advanced source/authorizer/reranker | V1 storage/retrieval → operational V2 source | 01.3, 14.2 | Title/parent/provenance regressions |
| 07.2 | Define application request/default budgets | Public DTO → validated `RetrievalPlanV2` | 04.6 | Oversized query/scope/budget rejection |
| 07.3 | Complete exact metadata/document enumeration paths | Titles/IDs/scoped records → deterministic candidates | 07.1 | Exact title/ID/all-doc fixtures |
| 07.4 | Implement shared advanced application service | Plan/cursor/principal → authorized result set | 07.1–07.3, 04.3 | Ranked/exhaustive/completeness tests |
| 07.5 | Add HTTP route | Request DTO → result DTO | 07.4 | OpenAPI/auth/cursor/error tests |
| 07.6 | Bind MCP `search_evidence` | MCP request → application service | 07.4, 03.4 | Direct stdio/SSE tests |
| 07.7 | Add failure/coverage diagnostics | Source outcomes → reports/omissions | 07.4 | Backend failure never becomes no-match/complete |

### WP-08 tasks

| Task | Goal and files | Inputs → outputs | Dependencies | Acceptance/test |
|---|---|---|---|---|
| 08.1 | Compose structured projection store/extractor/service | Active generation → runtime structured service | 01.3, 02.8 | Startup with ready/missing/stale generation |
| 08.2 | Add dataset/schema discovery | Version scope → authorized dataset/field catalog | 08.1 | CSV/XLSX/table fixtures |
| 08.3 | Add transport-to-IR compiler | Typed JSON → `StructuredQueryV1` only | 08.2 | Unknown/type/injection rejection |
| 08.4 | Add compatible union/equality join | Explicit dataset list/key → partitioned records | 08.1 | Complete/incompatible/duplicate/null cases |
| 08.5 | Implement application service and completeness | Query/principal/cursor → structured result DTO | 08.3–08.4, 04.5 | Known-truth numeric/aggregate matrix |
| 08.6 | Add HTTP/MCP adapters | DTO → service | 08.5, 03.5 | OpenAPI, stdio/SSE, typed errors |
| 08.7 | Add performance/scan bounds | Large rows/groups → cancel/truncate/continue | 08.5 | Saturation and deterministic resume |

### WP-09 tasks

| Task | Goal and files | Inputs → outputs | Dependencies | Acceptance/test |
|---|---|---|---|---|
| 09.1 | Implement OCR advanced source | Active OCR FTS/vector generation → typed OCR candidates | 02.4, 07.4 | Region/text/language/locator provenance |
| 09.2 | Implement Vision text source | Active Vision FTS/vector generation → typed Vision candidates | 02.5, 07.4 | Description/entity/region provenance |
| 09.3 | Implement visual-vector source | Query image/text shared-space embedding → typed occurrence candidates | 02.6, 15.3 | Dimension/space/capability validation |
| 09.4 | Add exact asset metadata source | MIME/locator/alt/title filters → occurrence candidates | 06.2, 07.4 | Standalone and embedded exact discovery |
| 09.5 | Compose multimodal rank fusion | Representation-local ranks → deduplicated typed candidates | 09.1–09.4 | No raw cross-space comparison; repeated occurrence retained |
| 09.6 | Add modality-aware rerank/fallback | Typed candidates + capabilities → final ranks/diagnostics | 09.5 | Missing reranker surfaces fallback; provenance retained |
| 09.7 | Expose through `search_evidence` | Modalities/query/scope → results and next-action IDs | 09.5–09.6 | Natural-language image query direct integration |
| 09.8 | Add end-to-end occurrence→delivery chain test | Search result → `get_asset`/analysis | 09.7, 06.6 | Correct pixels/analysis/provenance with no preknown occurrence |

### WP-10 tasks

| Task | Goal and files | Inputs → outputs | Dependencies | Acceptance/test |
|---|---|---|---|---|
| 10.1 | Implement certified embedding provider adapter | Active profile/model → validated 1024-d vectors | 15.1 | Dimension/revision/preprocess/lifecycle tests |
| 10.2 | Implement certified multilingual reranker adapter | Query/candidates → typed scores | 15.1 | Direction capability and bounded batch tests |
| 10.3 | Compose language detector/planner/service | Query/profile/readiness → selected paths | 01.3, 10.1–10.2 | Mixed/undetermined/unsupported path tests |
| 10.4 | Implement native sparse/transliteration/translation sources | Original/derived projections → labeled candidates | 02.7, 07.4 | Original text never replaced; cache auth tests |
| 10.5 | Build/activate multilingual generation | Authorized corpus scope → embeddings/index alias | 02.9, 10.1 | Counts/checksum/stale rollback |
| 10.6 | Integrate language paths into `search_evidence` | Query language/scope → fused results | 10.3–10.5 | Six directions plus fallback/completeness |
| 10.7 | Expose language metadata/capabilities | Runtime state → HTTP/MCP DTOs | 10.6, 13.2 | Installed!=active!=indexed state tests |
| 10.8 | Add OCR-language cross-modal test | Image OCR language → multilingual retrieval | 09.1, 10.6 | Marathi/Hindi OCR query and provenance |

### WP-11 tasks

| Task | Goal and files | Inputs → outputs | Dependencies | Acceptance/test |
|---|---|---|---|---|
| 11.1 | Define document-set selector/resolver | IDs/titles/exact metadata/exhaustive cursor → authorized stable document set | 07.3, 14.2 | Ambiguous/shared/missing/all-doc cases |
| 11.2 | Define partitioned result model | Per-document result sets → global result + per-partition completeness | 11.1 | Serialization/invariant tests |
| 11.3 | Implement per-document quotas and bounded fusion | Document set + plan → partitioned candidates | 11.2 | Fairness/explosion/deterministic ties |
| 11.4 | Add `require_complete` fail-closed mode | Partition reports → success or typed incomplete error | 11.3 | One failed/unavailable/truncated partition tests |
| 11.5 | Integrate structured union/join | Document datasets → exact multi-dataset result | 08.4, 11.1 | Known truth and provenance |
| 11.6 | Expose document-set scope in HTTP/MCP schemas | Public scope → resolver/partitioned result | 11.3–11.5 | Multi-document direct adapter tests |
| 11.7 | Add comparison-ready context partitioning | Typed per-doc evidence → bounded labeled bundle | 11.3 | Source quotas/provenance/omission tests; no synthesis planner |

### WP-12 tasks

| Task | Goal and files | Inputs → outputs | Dependencies | Acceptance/test |
|---|---|---|---|---|
| 12.1 | Compose multimodal context/citation/execution store | Runtime services → `FinalQAInterfaceV2` | 01.3, 09.6, 11.7 | Composition with supported/unsupported modalities |
| 12.2 | Add provider capability negotiation | Evidence modalities + profile → retained/omitted/fail-closed context | 12.1 | Unsupported/disabled/policy/budget cases |
| 12.3 | Bind completeness publication policy | Retrieval/context state → allowed/denied publication | 12.1 | Complete/partial/truncated/unavailable matrix |
| 12.4 | Implement shared Final-QA V2 application service | Request/fingerprint → claim/generate/validate/publish/replay | 12.1–12.3 | ADR-0054/0056 exact regression matrix |
| 12.5 | Add HTTP execution/replay route | V2 DTO → service | 12.4 | OpenAPI/live persistence tests |
| 12.6 | Bind MCP `run_final_qa_v2` | MCP request → service | 12.4, 03.6 | Direct stdio/SSE/replay tests |
| 12.7 | Add multimodal/multilingual QA cases | Typed evidence → grounded answer/citations | 09.8, 10.8, 12.4 | Original-vs-derived citations and language fidelity |

### WP-13 tasks

| Task | Goal and files | Inputs → outputs | Dependencies | Acceptance/test |
|---|---|---|---|---|
| 13.1 | Create shared Phase 8.5 application services | Principal + DTO → domain service/results | 01.4 | HTTP/MCP parity tests |
| 13.2 | Implement truthful capability registry | Provider + active generation + coverage + policy → capability snapshot | 01.6, 02.10, 15.3 | Every state/reason/coverage combination |
| 13.3 | Expand `/v2/capabilities` | Snapshot → redacted transport DTO | 13.2 | OpenAPI/security tests |
| 13.4 | Add processing estimate/submit/status/cancel routes | Manifest/principal → durable job operations | 01.4 | Consent/budget/cancel/retry/error tests |
| 13.5 | Register advanced/structured/Final-QA routes | Application services → routers | 07.5, 08.6, 12.5 | Full `/v2` route matrix |
| 13.6 | Unify HTTP/MCP error mapping | Domain errors → stable public error codes | 13.1 | No stack/path/content leakage |
| 13.7 | Add bounded streaming only where contract requires | Large resources/results/jobs → cancellable stream/events | 13.1 | Disconnect/timeout/max-size/partial state |
| 13.8 | Ensure MCP handlers use shared services | MCP calls → identical auth/bounds/results | 03.4–03.7, 13.1 | HTTP/MCP semantic parity fixtures |

### WP-14 tasks

| Task | Goal and files | Inputs → outputs | Dependencies | Acceptance/test |
|---|---|---|---|---|
| 14.1 | Define additive scope resolver | Document/source relations → scoped notebook alternatives/resolution | 00.4 | Zero/one/multiple notebook tests |
| 14.2 | Centralize principal/evidence authorization | Principal + scope/evidence → allow/non-leaking deny | 14.1 | Cross-notebook/cross-version/revocation tests |
| 14.3 | Migrate search/delivery off frozen protocol addition | `StorageInterfaceV1.list_sources_for_document` consumer → resolver | 14.1 | Legacy storage double composes |
| 14.4 | Restore frozen `StorageInterfaceV1` declaration | Current protocol → pre-0072 signature | 14.3 | Interface snapshot and mypy tests |
| 14.5 | Preserve concrete compatibility method | SQLite/Composite method → optional additive implementation | 14.3 | Existing direct callers continue |
| 14.6 | Apply authorization at every V2 stage | All services → repeated scoped checks | 14.2 | Candidate/fusion/context/replay/cache isolation |
| 14.7 | Execute binary/container/query threat tests | Adversarial fixtures → typed rejection/bounds | 06–13 handlers | Traversal/symlink/MIME/bomb/SQL/prompt/cursor tests |
| 14.8 | Audit observability/redaction | Logs/events/errors → safe metadata only | 14.6 | Capture tests show no content/secrets/paths |

### WP-15 tasks

| Task | Goal and files | Inputs → outputs | Dependencies | Acceptance/test |
|---|---|---|---|---|
| 15.1 | Define model profile registry/file schema | Selected evaluation profiles → versioned profile document | 00.3 | Schema/license/revision/dimension validation |
| 15.2 | Define configuration precedence | Profile file/name + inline legacy + env → one immutable snapshot | 15.1 | Precedence/property/error tests |
| 15.3 | Bind profile to capability/generation identity | Resolved profile + store state → readiness | 15.1, 02.10 | Mismatch/stale/missing model tests |
| 15.4 | Remove path ambiguity | Runtime model roots from env/operator config → provider paths | 15.2 | No personal D:/C: path in public/production code |
| 15.5 | Expose redacted active profile | Snapshot → config/capability response | 15.3, 13.2 | Secrets/paths absent |
| 15.6 | Add V1-only and fully disabled profiles | Configuration → truthful reduced capability | 15.2 | V1 starts with no Phase 8.5 models |
| 15.7 | Document migration from current inline config | Existing `mnemo.toml` → operator steps | 15.2 | Config round-trip and startup tests |

### WP-16 tasks

| Task | Goal and files | Inputs → outputs | Dependencies | Acceptance/test |
|---|---|---|---|---|
| 16.1 | Define blind-agent manifest schema | Natural-language prompt + oracle → versioned test case | 00.5 | Schema/mutation tests |
| 16.2 | Build tool-only evaluator | MCP discovery + prompt → transcript, calls, answer, costs | 03.9 | No hidden IDs/chains in evaluator input |
| 16.3 | Add deterministic API oracle evaluator | Transcript/results → correctness/completeness/provenance verdict | 16.1 | False-positive mutation tests |
| 16.4 | Execute document/exhaustive/structured cases | Section 27 cases 1–15 → artifacts | WP-05,07,08 | Required tool family and exact oracle pass |
| 16.5 | Execute multilingual/multimodal cases | Cases 16–27 → artifacts | WP-09,10 | Correct occurrence/language/derived provenance |
| 16.6 | Execute multi-document cases | Cases 28–31 → artifacts | WP-11 | Per-partition completeness and source coverage |
| 16.7 | Run stdio/SSE and at least two external clients | Same manifest → comparable behavioral metrics | 16.2–16.6 | Transport parity and bounded repeatability |
| 16.8 | Publish post-fix behavioral report | Artifacts → truthful scoped conclusions | 16.7 | No API-only result labeled agent success |

### WP-17 tasks

| Task | Goal and files | Inputs → outputs | Dependencies | Acceptance/test |
|---|---|---|---|---|
| 17.1 | Reconcile active architecture/roadmaps/README | Runtime evidence → truthful current docs | WP-00–16 | Status/link/claim audit |
| 17.2 | Update ADR index and successor implementation records | Accepted ADRs/evidence → current index | 17.1 | Immutable historical ADRs unchanged |
| 17.3 | Add corrective changelog and operator migration/rollback | Final diff/schema/config → instructions | 02,15 | Dry-run review on fresh/v13/V1-only profiles |
| 17.4 | Run focused gate matrix once per stabilized subsystem | Package artifacts → signed results | WP exits | All focused gates green |
| 17.5 | Run full quality gate once after freeze | Code/docs → pytest/coverage/Ruff/mypy/builds/diff | 17.4 | 0 failures, coverage ≥90%, all static/build checks pass |
| 17.6 | Run live HTTP/MCP/security matrix | Production process → protocol evidence | 17.5 | Both MCP transports and V1/V2 routes green |
| 17.7 | Verify Golden Corpus read-only and eval projections | Immutable DBs → counts/digests/readiness report | 17.6 | Golden 15/1,514 invariant; no writes |
| 17.8 | Produce final Phase 8.5 certification | All evidence → PASS/BLOCKED record | 17.1–17.7 | Section 34 fully satisfied; no unsupported claims |

## 24. Database/Projection Migration Plan

### Baseline

- Frozen Golden Corpus remains at schema v6 and is never migrated during development/certification; read-only verification only.
- Production implementation schema before WP-02 was v13; fresh and upgraded
  implementation databases now target additive schema v14.
- Current Phase 8.5 evaluation data demonstrates canonical ingestion but not active derived generations.

### Implemented schema v14

WP-02.1 confirmed no equivalent searchable Vision/language text projections.
Schema v14 therefore creates:

```text
vision_text_projection_rows
  generation_id, derivation_id, occurrence_id, document_id, version_id,
  language, script, normalized_text_hash, ordinal, payload_checksum

vision_text_fts (FTS5 external/content-linked projection)

language_text_projection_rows
  generation_id, derivation_id, source_kind/source_id, document_id, version_id,
  original_language, target_language, representation_kind,
  normalized_text_hash, ordinal, payload_checksum

language_text_fts

index_generation_coverage

index_generation_sources
```

Use existing `index_generations`/`active_index_generations`, OCR, visual, multilingual-vector, structured, asset, and processing tables. Do not introduce a duplicate global result table unless a measured stable-snapshot requirement cannot be met from immutable generation identities.

### Migration phases

1. Transactionally create additive tables/indexes and record v14.
2. Do not build data inside the schema transaction.
3. Submit governed projection jobs per capability/scope/profile.
4. Build in `BUILDING`; checkpoint by stable derivation/source key.
5. Validate authorization scope, input/output count, checksum, model/profile/generation, and orphan constraints.
6. Transition to `READY` only after validation.
7. Atomically promote the capability/profile alias.
8. Retain the prior READY generation for rollback.
9. Capability discovery reports active coverage; unbuilt data remains unavailable/partial.
10. GC only after retention checks prove no snapshot/job/reference dependency.

### Required migration tests

- fresh DB creation;
- v13→v14 upgrade;
- repeated/idempotent migration;
- injected DDL failure rollback;
- interrupted build after every lifecycle boundary;
- concurrent builders and promotion race;
- checksum/count mismatch;
- active alias rollback;
- optional Qdrant disabled;
- legacy v6 read-only corpus unaffected;
- zero mutation of documents/versions/sources/chunks/FTS/title/V1 embeddings.

## 25. Configuration Plan

### Authoritative model profile

Introduce a versioned tracked profile, for example `config/model_profiles/phase8_5_local_v1.toml`, with:

- profile ID/version/trust class;
- provider, model, revision, dimensions, metric, normalization, preprocessing;
- supported media/languages/scripts/modalities;
- capability state and certification evidence reference;
- resource/batch/context ceilings;
- local/cloud policy requirements;
- no credentials, machine paths, or secrets.

`MnemoConfig` gains an additive optional profile reference. Precedence is frozen as:

1. explicit environment leaf override;
2. explicit inline component override;
3. selected profile document;
4. existing V1 defaults.

The resolved immutable snapshot is fingerprinted and bound to derivations/generations. V1 `embedding` and `reranker` remain separate and continue to control V1. `models.*` controls only Phase 8.5 V2 services.

### Feature/readiness configuration

Add independent flags/profile choices for:

- advanced canonical retrieval;
- structured projection/retrieval;
- OCR processing/search;
- Vision processing/text search;
- visual-vector search;
- multilingual sparse/vector/reranking;
- multimodal fusion/Final-QA V2;
- HTTP/MCP advertisement.

Advertisement is computed, not configured directly: `enabled && provider_ready && active_generation_valid && authorized_policy`. A configured model with no active generation is `UNAVAILABLE` or `UNVALIDATED`, never `SUPPORTED`.

### Cursor and bounds configuration

Add cursor secret/key ID/TTL/rotation overlap and request/response/scan/page/row/token/pixel/asset/time ceilings. Authenticated production startup rejects the local development cursor secret. Public capability responses show numeric effective limits but never secrets or filesystem/model-cache paths.

## 26. Test Strategy

### Hierarchy

| Level | Purpose | When |
|---|---|---|
| L0 — static inspection | Interfaces, schemas, dependencies, docs/ADR drift | Before coding and each contract review |
| L1 — unit | Models, cursors, identities, selectors, compilers, mappers | After each coherent subsystem edit |
| L2 — service | Store/service composition, authorization, generation lifecycle | At each WP functional exit |
| L3 — MCP/HTTP contract | Schema snapshots, error mapping, backward compatibility | After adapter changes |
| L4 — isolated integration | Temporary DB/blob store, projection builds, real parsers, local fake providers | After WP-02 and each retrieval family |
| L5 — external-agent behavior | Blind tool selection and composition | Only after public contracts stabilize |
| L6 — security/performance bounds | Adversarial media/query/cursor/scope/saturation | Per affected WP, consolidated before final |
| L7 — full regression | Full pytest/coverage/static/build/live compatibility | Once at final stabilization; rerun only if later code changes |

### Package-to-test mapping

| WP | Required levels |
|---|---|
| 00 | L0 |
| 01 | L1–L2 |
| 02 | L1–L4, L6 migration/resource |
| 03 | L1, L3; L5 harness dry run |
| 04 | L1–L3, L6 cursor |
| 05 | L1–L5 document cases |
| 06 | L1–L5 asset cases, L6 binary/security |
| 07 | L1–L5 exhaustive cases, L6 explosion |
| 08 | L1–L5 structured cases, L6 injection/scale |
| 09 | L1–L5 multimodal cases, L6 media/prompt |
| 10 | L1–L5 multilingual cases, L6 policy/resource |
| 11 | L1–L5 multi-document, L6 partition bounds |
| 12 | L1–L5 QA/replay, L6 snapshot/prompt/auth |
| 13 | L2–L4 protocol/stream/job tests |
| 14 | L1–L6 authorization/security |
| 15 | L1–L4 configuration/profile |
| 16 | L5 plus selected L6 |
| 17 | L7 and live release-candidate matrix |

### Efficiency rules

- Use deterministic fake providers for correctness/security.
- Reuse the 44-document evaluation state; rebuild only affected derived projections.
- Never re-ingest the 15-document Golden Corpus.
- Run model/provider benchmarks only if a selected profile or preprocessing contract changes.
- Run the smallest failing test first and batch related fixes.
- Do not rerun a passing full suite until a later code change invalidates it.

## 27. External-Agent Behavioral Test Matrix

The table records the oracle chain for evaluation design. The external agent receives only the natural-language request and discovered MCP metadata—never the chain, IDs, expected tool, or answer.

| # | Natural-language request | Oracle tool chain / intermediate IDs | Required completeness/provenance | Expected answer oracle | Failure conditions |
|---:|---|---|---|---|---|
| 1 | Tell me the last paragraph of manuscript.pdf. | ranked/exact discovery → document/version/notebook → `get_document(from_end paragraph=1)` | Complete exact-version block; source/document/version/ordinal/page | Exact terminal paragraph from manifest (current fixture ends with the certified Marathi paragraph) | Search-only answer, wrong version, nonterminal block, bounded called complete |
| 2 | What is on page 5? | discovery → `get_document(page_range 5..5)` | Complete page scope and physical page attribution | All bounded page-5 blocks or typed unavailable | Semantic chunk substitution or invented page |
| 3 | Give me the complete manuscript. | discovery → `get_document(full)` → cursors to null | Terminal complete snapshot; all block ordinals once | Exact ordered block digest/manifest | Stops on truncated page, duplicates/skips blocks |
| 4 | Find the paragraph discussing X. | ranked anchor → exact document selector/adjacency if needed | Bounded anchor search plus exact paragraph provenance | Manifest paragraph containing X | Claims full document searched when top-k only |
| 5 | What is the final sentence? | discovery → from-end paragraph/block → deterministic sentence boundary | Complete tail scope; exact block/version | Manifest final sentence | Uses most semantically relevant sentence |
| 6 | Read pages 3 through 5. | discovery → page range → cursor if bounded | Complete range or explicit truncation/continuation | Ordered content digest for pages 3–5 | Reads outside range, omits without disclosure |
| 7 | Find all students with CPI greater than 8.9. | dataset discovery → `query_structured(GT 8.9)` → cursor | Complete dataset generation, row/cell provenance | Exact expectation-manifest row set | Semantic top-k, numeric string comparison, incomplete set |
| 8 | Give me every student with CPI above 8. | structured `GT 8` → cursor | Complete and exact matched count | Manifest row set | Result cap without continuation |
| 9 | How many students satisfy this condition? | structured COUNT with predicate | Complete row universe and aggregate cell evidence | Manifest count | LLM counts sampled chunks |
| 10 | Compare all students in branches X and Y. | structured filter IN + grouping/sort | Complete dataset or per-partition completeness | Manifest grouped rows/statistics | Missing branch/rows hidden |
| 11 | Filter students whose CPI is between 8 and 9. | GTE 8 + LTE 9 | Complete typed decimal predicate | Manifest rows | Lexical range semantics |
| 12 | Sort all students by CPI descending. | structured order DESC + cursor | Complete stable ordering/null policy | Manifest order | Ranked relevance order |
| 13 | What is the average CPI? | structured AVG | Complete row universe, invalid/missing handling named | Manifest decimal/rounding policy | Sample-derived or invented average |
| 14 | Compare Atharv's CPI with another named student. | structured exact-name rows → deterministic comparison | Complete name match alternatives; cell provenance | Manifest comparison | Fuzzy wrong person or semantic inference |
| 15 | Group students by branch and count them. | structured GROUP BY + COUNT | Complete groups and exact evidence universe | Manifest group counts | LLM grouping over excerpts |
| 16 | English query targeting Hindi content | `search_evidence` multilingual paths | Bounded ranked; query/source languages and path | Expected document in top-k threshold | V1 English-only path advertised multilingual |
| 17 | English query targeting Marathi content | multilingual search | Same as #16 | Manifest Marathi target | Translation replaces original source text |
| 18 | Hindi query targeting English content | multilingual search/rerank | Original Hindi query, English evidence, derivation labels | Manifest English target | Language mislabeled or wrong profile |
| 19 | Marathi query targeting English content | multilingual search/rerank | Cross-language path and fallback explicit | Manifest English target | Silent English fallback called cross-language success |
| 20 | Retrieve Marathi/Hindi text visible only in an image. | multimodal search OCR representation → occurrence → analysis/original | OCR generation coverage; original occurrence + OCR region derivation | Manifest recognized text/target | Canonical search only, OCR text cited as original |
| 21 | Find the image showing X. | `search_evidence` visual/Vision/OCR sources | Ranked bounded; occurrence IDs/locators/paths | Manifest target image in threshold | Calls `get_asset` without discovering occurrence |
| 22 | Which image contains Y? | OCR/Vision text search → candidates | Requested representations and coverage | Manifest occurrence(s) | Searches only document chunks |
| 23 | What is written in this image? | occurrence discovery/context → `get_asset` + `get_image_analysis(OCR latest_ready)` | Original plus OCR derivation, language/geometry/confidence | Manifest OCR text with uncertainty | Derivation ID guessed or OCR shown as authored text |
| 24 | What does the diagram show? | visual/Vision search → original + Vision analysis | Original/derived separation, provider/profile | Manifest grounded description criteria | Analysis without original occurrence or hallucinated unsupported details |
| 25 | Find images matching this description. | visual shared-space/Vision text search → exhaustive/ranked as requested | Named vector space, coverage and boundedness | Manifest Recall@k set | Raw incompatible scores fused directly |
| 26 | Find the last image in the document. | document discovery → asset inventory/positional selector tail | Complete occurrence inventory and physical order | Manifest terminal occurrence | Highest-ranked or last-created asset |
| 27 | Compare the two figures. | discover exact two occurrences → deliver originals/analyses → typed bounded context | Both occurrence/version/derivation chains | Manifest comparison facts with per-figure attribution | One figure omitted or provenance merged |
| 28 | Compare information across these documents. | exact document-set resolver → partitioned retrieval → bounded context | Per-document completeness and evidence quotas | Manifest comparison across every named doc | Global top-k suppresses a document |
| 29 | Find every document containing X. | exhaustive exact/canonical predicate over document set → cursor | Complete document universe and match field | Manifest document IDs/titles | top-k list called every |
| 30 | Which document has the highest value? | structured datasets → compatible union/join → MAX/order | Complete participating dataset partitions | Manifest winning document/value/cells | Semantic ranking or incomplete documents |
| 31 | Compare all relevant documents. | ranked discovery to define relevance + explicit bounded status, or exhaustive declared predicate | Must distinguish “relevant top-k” from “all satisfying predicate” | Evidence-backed comparison with scope disclaimer | Unbounded/all claim from ranked discovery |

### Behavioral scoring

Score separately:

- correct first tool family;
- correct follow-up chain;
- identifier propagation;
- cursor completion;
- answer correctness;
- provenance correctness;
- completeness honesty;
- bounds/cost;
- security/error behavior.

One HTTP 200 or one successful tool call is never a pass. P0 cases (#1–3, #7–9, #20–27, #29–30) require zero false-completeness and zero authorization/provenance failures. Selection rates are reported per client/model, not collapsed into API correctness.

## 28. Security Test Matrix

All tests use isolated stores and deterministic providers. Denial occurs before bytes, derived text, vectors, row values, or existence-sensitive metadata are returned.

| Threat/boundary | Test and expected control | Required result |
|---|---|---|
| Cross-notebook evidence | Request another notebook's chunk/document; authorize at recall and delivery | Typed forbidden; no title/content leakage |
| Shared content asset | Reuse the same SHA-256 across notebooks; authorize the occurrence chain, never the hash | Authorized occurrence succeeds; sibling remains hidden |
| Revoked access | Revoke after search but before delivery/replay; reauthorize every boundary | Fail closed without cached leakage |
| Derivation isolation | Guess OCR/Vision/translation derivation ID; resolve through exact authorized occurrence/version | Forbidden/not found; no provider output |
| Cursor tampering | Alter scope, selector, budget, snapshot, signature, or expiry | Typed invalid/expired cursor; no execution |
| Cursor cross-scope replay | Reuse a valid cursor as another actor/notebook | Cursor scope binding rejects it |
| Stale snapshot/generation | Continue after active version/generation changes | Stable immutable snapshot or typed stale conflict |
| Pagination/query explosion | Extreme limits, fan-out, wildcard scope | Server ceilings; bounded/TRUNCATED, never false COMPLETE |
| Structured/SQL injection | Malicious column/operator/literal/sort | Typed AST, allow-list, parameterized SQL; invalid request |
| Binary traversal/symlink | Path, traversal, arbitrary blob, symlink target | Opaque-ID resolution; rejection; no path disclosure |
| Binary integrity | Stored length/hash/MIME mismatch | Typed malformed resource; no corrupted bytes |
| Partial image | Response bound cuts an encoded image | Atomic delivery or explicit byte range; never label prefix complete |
| Malicious media/archive | Bomb, active SVG, OOXML traversal/external target | Existing bounded extraction and safe delivery policy reject/quarantine |
| OCR/Vision prompt injection | Derived content instructs tools/secret disclosure | Quoted untrusted evidence; no policy or tool mutation |
| Provider/profile spoofing | Result claims unregistered provider/model/generation | Registry/identity validation rejects projection |
| Vector-space confusion | Fuse incompatible model/dimension spaces | Named-space compatibility; omit/fail, never raw-score fusion |
| Capability probing | Unauthorized capability/resource query | Scope-aware response without resource/provider leakage |
| Error/log leakage | Malformed IDs and injected store/provider errors | Stable mapper; no stack, SQL, paths, content, vectors, prompts, secrets |
| Snapshot tampering/replay | Change evidence/fingerprint or replay after revocation | ADR-0056 conflict/authorization failure; zero generation |
| Job-governance bypass | Invoke costly provider outside governed job path | Typed policy failure; no hidden cloud/paid call |
| Stale worker publication | Expired lease publishes result/generation | Lease ownership and atomic promotion reject stale writer |
| Denial enumeration | Compare missing and inaccessible opaque IDs | Repository-standard non-enumerating response |

Exit requires unit/service tests for every control, public HTTP/MCP mapping tests, and one targeted adversarial integration run. Neither certified corpus is reprocessed.

## 29. ADR Plan

### Proposed decisions

| ADR | Decision | Reason and compatibility |
|---|---|---|
| ADR-0073 — MCP-native retrieval and delivery contracts | Freeze semantic tool families, intent guidance, completeness/provenance, selectors/cursors, capability discovery, and evolution rules | Client-facing composition is architecture, not copywriting. Retain the ten current tool names/defaults; add optional fields and additive tools; snapshot old schemas. |
| ADR-0074 — Phase 8.5 runtime/profile activation | Define one composition root and registry for advanced, structured, OCR, Vision, visual, multilingual, multimodal, and Final-QA V2 services; distinguish declared/buildable/ready/active/disabled/unavailable/certified | Classes and declarations alone are not operational features. V1 providers remain independent; defaults are non-certified until evaluation pins them. |
| ADR-0075 — Additive document scope resolution | Supersede ADR-0072's mechanism, not its notebook-propagation outcome: introduce `DocumentScopeResolverV1` and prohibit additions to frozen `StorageInterfaceV1` | Concrete stores may retain the compatibility method temporarily; consumers migrate to the resolver before protocol cleanup. |

ADR-0058–0071 remain accepted. ADR-0067 governs additive delivery and ADR-0073 specializes its agent-facing contract. ADR-0054/0056 are reused unchanged. ADR-0072 remains historical and becomes **superseded by ADR-0075** only after migration tests pass. Schema-v14 mechanics remain under ADR-0071 unless implementation discovers a new persistence semantic. Each new ADR includes alternatives, frozen-contract impact, security, rollback, migration, and conformance tests and is accepted during WP-00.

## 30. Documentation/Governance Update Plan

Updates follow implementation truth. Historical reports remain immutable and may receive only a dated successor reference.

| Artifact | Classification | Required update |
|---|---|---|
| `docs/architecture/current/phase8.5_architecture.md` | Authoritative | Add accepted MCP semantics, runtime/profile state, scope resolver, selectors, and projection ownership |
| Phase 8.5 engineering roadmap | Authoritative/current | Reopen operationally incomplete gates and track WP exits rather than class existence |
| Master engineering roadmap | Authoritative/current | Clarify Phase 8.5 deterministic primitives versus Phase 11 planning; update status at WP-17 |
| `docs/architecture/current/mnemo_architecture_v2.md` | Current architecture | Reconcile composition/data-flow diagrams and public capability table |
| ADR-0073–0075 and ADR index | Normative | Add decisions/status/links before dependent implementation |
| `README.md` | Current user-facing | Publish truthful active capabilities, configuration, tools, bounds, and limitations after validation |
| MCP/API documentation | Current contract | Exact schemas, use/do-not-use guidance, selectors, cursor loop, completeness, errors, examples |
| Capability matrix | Derived current record | Record configured/buildable/ready/active/exposed/verified state per capability |
| Test plan | Current verification | Add L0–L7 mapping, blind-agent protocol, security matrix, manifests, pass thresholds |
| Changelog | Historical ledger | Append actual implemented changes; do not revise earlier claims retroactively |
| 8.5.1–8.5.10 gate evidence | Historical governance | Preserve point-in-time records; link from final successor certification |
| 8.5.11 evaluation report | Evaluation artifact | Preserve; successor report distinguishes direct API success from autonomous-agent behavior |
| Post-8.5 MCP audit | Diagnostic artifact | Preserve and close findings in final remediation matrix |
| This plan | Approved blueprint | Record approval/deviations/WP links without erasing original findings |
| Final Phase 8.5 certification | New governance record | Evidence-backed architecture/API/MCP/security/corpus/quality verdict |

The final documentation audit checks links, route/tool counts, schema version, projection names, model status, phase numbers, test counts, and capability claims against runtime inventories.

## 31. Prioritization Matrix

| WP | Priority/timing | Rationale |
|---|---|---|
| 00 Baseline/decisions | P0 / NOW | Prevent implementation against contradictory contracts |
| 01 Runtime composition | P0 / NOW | Features are not real until wired through one authorized root |
| 02 Projections/generations | P0 / NOW | Empty/inactive projections prevent OCR/Vision/visual/multilingual/structured retrieval |
| 03 MCP contracts | P0 / NOW contract; adapter after services | Agents currently choose reasonable but wrong chains |
| 04 Cursor/completeness | P0 / NOW | Opaque continuation or false completeness invalidates exact/exhaustive behavior |
| 05 Exact documents | P0 / NOW | Page/range/tail/full access is committed Phase 8.5 behavior |
| 06 Asset/derivation/binary | P0 / NOW | Image discovery and usable delivery are disconnected |
| 07 Advanced/exhaustive | P0 / NOW | All/every/count must never be top-k |
| 08 Structured | P0 / NOW | Numeric filters/aggregates require typed complete execution |
| 09 Multimodal | P0 / NOW | Existing derived records are not an agent-usable search path |
| 10 Multilingual | P1 / AFTER WP-02/07 | Required, dependent on shared projection/retrieval infrastructure |
| 11 Multi-document | P1 / AFTER WP-07/08 | Required deterministic comparisons, not Phase 11 planning |
| 12 Final-QA V2 | P1 / AFTER retrieval families | Must consume truthful typed evidence/completeness |
| 13 HTTP V2/jobs | P1 / AFTER services | Completes accepted adapter surface |
| 14 Security/scope | P0 / CONTINUOUS | Release blocker across all WPs |
| 15 Configuration/profiles | P0 / NOW | Prevents declared-but-unused or accidentally certified models |
| 16 Behavioral validation | P0 / AFTER schemas stabilize | Proof of external-agent usability |
| 17 Final certification | P0 / LAST | Closes Phase 8.5 truthfully |

P2/optional: ergonomic aliases, richer continuation helpers, client-specific examples, and measured performance tuning. P3/Phase 11: adaptive decomposition, evidence-gap replanning, generalized multi-hop, learned routing, and open-ended joins.

## 32. Dependency Graph

```text
WP-00
  ├─ WP-01 ─┬─ WP-02 ─┬─ WP-07
  │         │         ├─ WP-08
  │         │         ├─ WP-09
  │         │         └─ WP-10
  │         └─ WP-15 ─────────┘
  ├─ WP-03 contract design
  └─ WP-04 ─┬─ WP-05
            ├─ WP-06
            ├─ WP-07
            └─ WP-11

WP-05..WP-10 → WP-11 → WP-12
WP-03 + WP-05..WP-12 → WP-13
WP-14 constrains WP-01..WP-13 and closes after adapters.
WP-16 depends on WP-03..WP-15; WP-17 depends on all prior exits.
```

After WP-00, contract/cursor work, runtime/configuration, and projection planning may run in parallel. Shared storage, composition-root, and public-schema edits require explicit ownership.

## 33. Canonical Implementation Sequence

1. **WP-00:** freeze inventories; approve ADR-0073–0075; L0 checks. Exit: no unresolved P0 contradiction.
2. **WP-15 contract half, then WP-01:** establish authoritative profile states and compose additive services/resolver; unit/composition/legacy-double tests. Exit: deterministic active/disabled/unavailable resolution.
3. **WP-02:** build/promote projections in an isolated clone; schema v14 only if required; migration/idempotency/crash/rollback tests. Exit: active projections with coverage manifests.
4. **WP-04:** implement semantic cursor/completeness envelope; property/security/protocol tests. Exit: every collection/range has truthful terminal semantics.
5. **WP-05:** exact selectors/traversal; six document behavioral fixtures. Exit: page/range/tail/full works without semantic substitution.
6. **WP-06:** occurrence inventories, derivation selection, atomic binaries; asset/security/format tests. Exit: discovery reaches an authorized decodable original and analysis.
7. **WP-07:** ranked/exhaustive retrieval; completeness/dedup/unavailable/cursor/explosion tests. Exit: all/every is evidence-backed.
8. **WP-08:** structured projection/compiler/filter/aggregate; numeric/null/group/order/injection tests. Exit: no numeric guarantee uses semantic top-k.
9. **WP-09:** OCR/Vision/visual search and safe fusion; modality/provenance tests. Exit: image descriptions discover occurrences.
10. **WP-10:** language detection/projection/embedding/reranking/fallback; cross-language and OCR-language tests. Exit: paths report model/index/coverage truthfully.
11. **WP-11:** explicit document sets, per-partition retrieval, bounded joins/comparisons. Exit: no named partition is silently omitted.
12. **WP-12:** Final-QA V2 with ADR-0054/0056; citation/retry/claim/crash/snapshot/replay/auth tests. Exit: compliant immutable publication and zero-generation replay.
13. **WP-03 adapter half plus WP-13:** publish final MCP and HTTP V2/jobs/streaming adapters; schema/live/error/cancellation/V1 tests. Exit: surfaces match ADR-0073.
14. **WP-14:** close Section 28 and remediate findings. Exit: no P0/P1 security issue.
15. **WP-16:** blind-agent matrix per supported client/model; adjust contracts only, never corpus-specific ranking. Exit: critical cases meet thresholds without false completeness/security errors.
16. **WP-17:** run final global gates once; read-only corpus audits; reconcile docs; issue certification. Exit: Section 34 is evidenced.

Every WP follows prerequisites/ADR check → coherent implementation → focused tests → security/compatibility → current docs → evidence. Compilation alone is not an exit.

## 34. Phase 8.5 Definition of Done

### Architecture/runtime

- Every original requirement maps to one implemented owner, public contract, test, and evidence record; no undocumented drift remains.
- Additive services are production-composed; capability state distinguishes code-present, configured, indexed, active, exposed, and verified.
- `StorageInterfaceV1` is restored as frozen through ADR-0075 with compatibility during resolver migration.
- Phase 11 consumes typed capabilities without SQLite, blob-path, projection-table, cursor-payload, or model-internal knowledge.

### Retrieval/documents/assets

- Ranked, exhaustive, structured, multilingual, multimodal, and bounded multi-document retrieval pass focused and blind-agent tests.
- Exact version, page/slide/sheet where available, block/range/adjacent/from-end/final/full traversal is bounded and resumable.
- Cursors bind scope/query/selector/snapshot/budgets, expire, reject tampering, and terminate with null continuation and truthful completeness.
- Standalone/embedded assets are discoverable by language and position with distinct asset/occurrence identities.
- Original binary delivery is authorized, verified, bounded, and decodable; OCR/Vision/visual/language/structured projections are independently active and provenance-labeled.
- Derivation inventories and deterministic latest-ready selection require no hidden IDs.

### Provenance/security/completeness

- Notebook/source/document/version and applicable chunk/asset/occurrence/derivation/generation/modality/language/path survive every boundary.
- Authorization is rechecked at recall, expansion, fusion, context, delivery, snapshot, and replay; a shared hash never confers access.
- Results declare searched/unavailable/disabled/failed/omitted/truncated paths and coverage/budgets. Top-k and infrastructure failure never become COMPLETE/NO_MATCH.
- Section 28 passes; logs/errors contain no private content, binary, vectors, paths, secrets, or provider payloads.

### MCP/HTTP/quality/governance

- Existing ten MCP tools, V1 routes, V1 retrieval, and V1 Final-QA remain compatible.
- Accepted additive surfaces expose exact traversal, exhaustive/structured/multimodal/multilingual retrieval, capability state, and Final-QA V2.
- Tool contracts include use/do-not-use guidance, chains, continuation, completeness, bounds, examples, and negative guidance; blind agents receive no oracle and pass all P0 cases.
- One production profile authority pins provider/model/revision/dimension/generation and labels non-certified defaults; no hidden cloud fallback exists.
- ADRs, active architecture/roadmaps, README, API/MCP docs, changelog, capability matrix, tests, and governance agree with runtime inventory.
- Final pytest has zero failures and at least 90% coverage; Ruff format/check, strict mypy, three package builds, and `git diff --check` pass.
- The certified 15-document corpus remains byte/identity/digest/count unchanged. The 44-document state is rebuilt only for affected derived projections and its integrity is recorded.
- No unresolved P0/P1 defect, contradiction, security finding, false claim, or false-completeness case remains.

## 35. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| More tools worsen selection | Four semantic additions only; negative guidance, examples, blind-agent tests |
| Strict clients break on schema evolution | Snapshot old schemas; preserve ten tools/defaults; additive fields and version only when required |
| Projection rebuild fails or costs too much | BUILDING generations, checkpoints/budgets, atomic promotion, rollback |
| Model/config ambiguity | Authoritative registry and exact revision/dimension manifests; explicit candidate/certified labels |
| False completeness | Central completeness algebra, coverage manifests, terminal cursor proofs, fail closed |
| Cross-notebook dedup leakage | Occurrence-scoped authorization at every boundary and isolation tests |
| Metadata loss in fusion/promotion | Immutable typed envelopes and boundary regression tests |
| Binary truncation breaks images | Atomic item bounds or standards-based ranges with hash/length metadata |
| Ambiguous structured schema | Typed validation and uncertainty/failure; no LLM-only numeric guarantees |
| Incompatible vector spaces | Named profiles/generations and calibrated fusion; never raw-score mixing |
| Multilingual fallback hides gaps | Explicit path diagnostics and original-language preservation |
| Global top-k starves documents | Explicit document set, per-partition quotas/completeness, deterministic merge |
| Final-QA publishes stale evidence | ADR-0054/0056, immutable snapshots, reauthorization, claim/conflict tests |
| Resolver migration breaks doubles | Compatibility adapter and legacy composition tests |
| External-agent variance | Per-client metrics; deterministic service gates; critical cases across supported clients |
| Scope expands into rewrite | Additive contracts, reused stores/services, justified schema, non-goal review at every exit |

## 36. Explicit Non-Goals

- This plan makes no production code, configuration, database, model, corpus, tunnel, or deployed MCP change.
- No V1 identity, canonical text/FTS/embedding/retrieval/citation/Final-QA/HTTP/streaming semantic redesign.
- No signed-cursor replacement, unbounded delivery/search/context, or corpus-specific rule.
- No derived OCR/Vision/translation content in canonical chunks or canonical FTS.
- No Qdrant enablement merely to claim support; capability reporting remains truthful.
- No automatic cloud/paid call, hidden provider fallback, or uncertified model presented as certified.
- No general agent planner, adaptive decomposition, evidence-gap replanning, recursive multi-hop, learned router, or open-ended joins; these remain Phase 11.
- No Phase 9 UI or later provider/release work beyond interfaces needed for Phase 8.5.
- No rewriting historical ADRs, gate evidence, evaluation reports, or changelogs.
- No purge, re-ingestion, or mutation of the certified 15-document Golden Corpus.

## 37. Final Recommendation

Approve this document as the single execution blueprint and begin with **WP-00**, not isolated MCP wording changes. The smallest coherent remediation is additive: settle MCP/runtime/scope decisions, wire existing services, populate and atomically activate independent projections, then expose exact, exhaustive, structured, multimodal, multilingual, and multi-document primitives through truthful bounded contracts.

```text
contract freeze
→ authoritative composition/configuration
→ projection readiness
→ cursor/completeness
→ exact document and asset access
→ exhaustive/structured/multimodal/multilingual retrieval
→ multi-document primitives
→ Final-QA V2
→ HTTP/MCP adapters
→ security and blind-agent validation
→ final reconciliation/certification
```

Do not defer present MCP discoverability, exact traversal, image discovery, exhaustive, or structured defects to Phase 11. Do not pull Phase 11's adaptive planner into Phase 8.5. The deterministic capability layer above makes external LLM use explicit now and gives Phase 11 a typed, model-neutral foundation later.

Implement one approved WP at a time. Any discovery that changes a frozen identity, V1 semantic, authorization model, or persistence invariant returns to ADR review; ordinary implementation detail remains governed by this plan.
