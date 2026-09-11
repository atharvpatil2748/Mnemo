# Mnemo — Phase 8.5 Engineering Roadmap

> **Status:** Historical execution plan; the scoped V2 production deployment
> reached certification under ADR-0076 on 2026-09-06. See the
> [final certification](../../reports/certification/current/mnemo-v2-final-certification.md) and
> [single-production-path audit](../../reports/architecture/mnemo-v2-single-production-path-audit.md)
> for current production authority.

**Document type:** implementation-ready engineering execution plan
**Architectural input:** [Phase 8.5 Architecture Blueprint](phase8.5_architecture.md)
**Decision input:** ADR-0058 through ADR-0071
**Baseline:** v0.25.0; Phases 0–8 frozen and certified
**Status:** Historical workstreams complete; authoritative remediation plan WP-00 through WP-08 complete, WP-09 through WP-17 open
**Scope:** advanced retrieval, multimodal/multilingual foundations, controlled
resource delivery, durable processing, model benchmarking, and certification between Phases 8 and 9

This roadmap records the original workstream schedule and evidence. Current
production remediation/certification status is governed by
`governance/PHASE_8_5_COMPLETE_IMPLEMENTATION_PLAN.md`; WP-07 exposes canonical
ranked/exhaustive evidence and WP-08 exposes exact-version structured discovery,
typed filtering/aggregation, conservative union/equality join, and truthful
generation-gated completeness through HTTP/MCP without claiming final behavioral
certification. The 8.5.1 catalog/authorization
foundation through 8.5.10 bounded HTTP/MCP delivery are implemented and tested.
Phase 8.5.11 full-scale evaluation, clean 44-document re-ingestion, multi-script OCR (en/hi/mr),
and rigorous 3-candidate benchmarking across multilingual embeddings (`BAAI/bge-m3`),
multilingual rerankers (`BAAI/bge-reranker-v2-m3`), visual embeddings (`openai/clip-vit-large-patch14`),
and local VLM selection (`qwen2.5vl:latest` winning over `gemma4:e4b`) are complete with dedicated
D: drive storage topology (`phase8_5_models.toml`). All software quality gates (Ruff, strict mypy 187 files,
package builds, git diff, frozen corpus integrity) pass 100%. Gate evidence lives in the dedicated
8.5.1–8.5.11 governance records.

---

## Table of contents

1. [Phase definition](#1-phase-definition)
2. [Frozen compatibility boundary](#2-frozen-compatibility-boundary)
3. [Dependency graph and implementation order](#3-dependency-graph-and-implementation-order)
4. [Workstream decomposition](#4-workstream-decomposition)
5. [Module execution specifications](#5-module-execution-specifications)
6. [Milestones](#6-milestones)
7. [Phase gates](#7-phase-gates)
8. [Testing and certification matrix](#8-testing-and-certification-matrix)
9. [Evaluation-pack expansion](#9-evaluation-pack-expansion)
10. [Security and risk matrix](#10-security-and-risk-matrix)
11. [Cost, compute, observability, and performance](#11-cost-compute-observability-and-performance)
12. [Future-phase compatibility](#12-future-phase-compatibility)
13. [Open architectural decisions](#13-open-architectural-decisions)
14. [Master implementation checklist](#14-master-implementation-checklist)

---

## 1. Phase definition

### Purpose

Phase 8.5 establishes typed, bounded, provenance-preserving foundations for
advanced and multimodal retrieval before the Phase 9 UI. It extends the
successful text pipeline; it does not redesign or replace it.

### Scope

- retain original document/image bytes and exact occurrences;
- add crash-safe, consent-aware processing jobs;
- add optional OCR, vision analysis, image embeddings, and translation;
- add exact, positional, structured, aggregate, exhaustive, and cross-language
  retrieval with honest completeness;
- add typed multimodal context, evidence citations, and persisted Final QA V2;
- add bounded document/asset HTTP and MCP delivery;
- define the Phase 9 UI capability contract;
- certify migration, security, cost, performance, and Phase 0–8 compatibility.

### Non-goals

- no Phase 9 frontend implementation in this phase;
- no replacement of canonical `Chunk.text`, V1 citations, V1 Final QA, or the
  six Phase 8 MCP tools;
- no mandatory OCR, VLM, cloud provider, shared vector space, Qdrant, or
  SurrealDB;
- no arbitrary SQL, unrestricted file delivery, unbounded context expansion,
  universal language claim, or corpus-specific ranking rule;
- no fabrication of missing original bytes for historical versions.

### Entry criteria

1. v0.25.0 Phase 0–8 baseline and 15-document corpus evidence are retained.
2. ADR-0058 through ADR-0071 pass contradiction review.
3. The Phase 8.5 evaluation pack has license/security approval.
4. Feature flags and rollback owners are assigned.
5. Provider candidates have reproducible local/cloud test profiles.

### Exit criteria

All gates G0–G10 are green with executable evidence; old and new APIs are live
validated; Phase 0–8 regression remains green; active documentation matches
runtime truth; CI is green; no capability is advertised outside its certified
profile.

### Frozen dependencies

The compatibility classifications in Section 2 are normative for execution.
Any implementation that needs to change a FROZEN item stops for a successor ADR
and migration/compatibility plan.

---

## 2. Frozen compatibility boundary

| Contract | Classification | Phase 8.5 rule |
|---|---|---|
| Document, DocumentVersion, Source, Chunk UUID identities | FROZEN | no recomputation or semantic change |
| parent/child/sibling and heading-path semantics | FROZEN | preserve through every new projection |
| canonical `Chunk.text` | FROZEN | OCR/VLM/translation remain derived |
| canonical `Asset` and content-addressed filesystem bytes | EXTENDABLE | reuse; add references/occurrences/derivations |
| parser V1 and transient image contracts | EXTENDABLE | additive V2 transport/adapters; V1 remains callable |
| SQLite storage and `schema_versions` migration discipline | FROZEN | additive transactional migrations only |
| CompositeStorage and StorageInterfaceV1 | FROZEN | independent additive stores/interfaces |
| FTS, title projection, sparse retrieval provenance | FROZEN | add independent analyzer/projection generations |
| text embeddings and cache identity | FROZEN | new modality interfaces/spaces only |
| Qdrant and SurrealDB optionality | FROZEN | never enabled implicitly |
| RRF, parent promotion, ADR-0057 reranking | FROZEN | V1 behavior unchanged; V2 typed candidates additive |
| V1 context, `[source:N]`, Citation, Final QA | FROZEN | V2 evidence/citation/execution alongside V1 |
| ADR-0054 retry and ADR-0056 replay/publication safety | FROZEN | reused exactly by V2 |
| `/v1/query` and `/v1/query/stream` preview semantics | FROZEN | no persisted execution side effects |
| existing HTTP routes and six MCP tools | FROZEN | new versioned routes/tools/resources additive |
| auth/error/isolation contracts | FROZEN | apply to every new boundary |
| development-shell UI | REPLACEABLE in Phase 9 | Phase 8.5 defines contracts only |
| roadmap SurrealDB-specific first worker assumption | DEPRECATED | ADR-0060 provider-neutral job facility governs |
| exact initial provider models and benchmark ceilings | UNKNOWN | measure before profile acceptance |

---

## 3. Dependency graph and implementation order

```text
M0 ADR/evaluation acceptance
  |
  +--> M1 Original bytes + AssetOccurrence + generation lifecycle
  |      |
  |      +--> M2 Complete extraction
  |      |      |
  |      |      +--> M4 OCR -------------------+
  |      |      +--> M5 VLM/image vectors -----+--> M7 multimodal retrieval/context/QA
  |      |
  |      +--> M3 Durable jobs + cost/consent --+             |
  |                                                          +--> M9 HTTP/MCP contracts
  +--> M6 Advanced/structured/exhaustive retrieval ----------+             |
  |                                                          |             +--> M10 UI contract validation
  +--> evaluation multilingual corpus --> M8 multilingual ---+                          |
                                                                                       M11 certification
                                                                                         |
                                                                                       M12 release readiness
```

### Critical path

1. Contracts/evaluation manifests.
2. Asset/version provenance and index-generation lifecycle.
3. Durable jobs and processing governance.
4. Extraction coverage.
5. OCR/VLM/visual embedding providers.
6. Advanced and structured retrieval.
7. Multimodal candidate/context/citation/Final QA V2.
8. Multilingual benchmark-selected profiles.
9. Bounded HTTP/MCP delivery.
10. UI contract verification, hardening, certification.

### Parallelizable work

- After M1: parser extraction fixtures, durable job store, and result-set/cursor
  contracts can proceed independently.
- After M3: OCR and VLM/image-vector provider tracks can proceed in parallel.
- Structured retrieval can proceed beside visual-provider work after schema and
  generation contracts are stable.
- Security fixtures, evaluation harness, observability, and operator docs run
  continuously and gate each milestone.

---

## 4. Workstream decomposition

| WS | Workstream | Primary ADRs | Depends on | Principal deliverable |
|---:|---|---|---|---|
| 1 | Asset foundation — IMPLEMENTED/TESTED | 0059, 0071 | M0 | original/version asset catalog |
| 2 | Asset occurrences — IMPLEMENTED/TESTED | 0059, 0068 | WS1 | typed location and authorization path |
| 3 | Original-document retention — IMPLEMENTED/TESTED | 0059 | WS1 | exact-byte reparse foundation |
| 4 | Extraction coverage | 0059, 0068 | WS1–3 | image inventory across formats |
| 5 | Durable jobs | 0060, 0071 | WS1 | crash-safe processing worker/store |
| 6 | Cost/consent governance | 0060, 0068 | WS5 | estimates, budgets, audit |
| 7 | OCR | 0061 | WS2,4–6 | region-provenance derived text |
| 8 | Vision analysis | 0062 | WS2,4–6 | structured VLM derivations |
| 9 | Visual embeddings | 0062, 0071 | WS2,5 | isolated vector-space generations |
| 10 | Advanced retrieval/completeness | 0058 | WS1,5 | typed plans/result sets/cursors |
| 11 | Structured retrieval | 0063 | WS10 | safe query IR and aggregation |
| 12 | Positional/full-document expansion | 0058, 0065 | WS1,10 | bounded ranges and continuations |
| 13 | Multimodal fusion/reranking | 0062, 0064 | WS7–10 | typed cross-modality candidates |
| 14 | Multimodal context/citations/QA | 0064 | WS10,13 | grounded V2 publication/replay |
| 15 | Multilingual stack | 0067 | WS7–14 | benchmarked language profiles |
| 16 | HTTP capability adapters | 0065, 0069 | WS5–15 | versioned thin routes |
| 17 | MCP tools/resources | 0065, 0066 | WS12–15 | four tools plus resources |
| 18 | Asset security/authorization | 0068 | all | common fail-closed enforcement |
| 19 | Phase 9 UI contract | 0069 | WS16–18 | explicit processing/viewer contract |
| 20 | Evaluation/certification | 0070 | all | evidence pack and gates |

---

## 5. Module execution specifications

Every module follows: contract/model -> schema/migration -> provider/service ->
composition -> adapter -> observability -> tests -> docs -> gate evidence.

### 5.1 Asset catalog and original retention

- **Purpose:** preserve authoritative bytes and exact version/occurrence links.
- **Inputs:** upload stream, verified MIME/hash, document/version identity,
  parser extraction records.
- **Outputs:** `DocumentBinaryReference`, `AssetOccurrence`, catalog queries,
  typed unavailable/omitted outcomes.
- **Interfaces/models:** `AssetCatalogStoreV1`; frozen `Asset`; new reference,
  occurrence, locator, extraction-provenance models.
- **Storage/migrations:** additive SQLite catalog tables and indexes; existing
  content-addressed filesystem; generation metadata under ADR-0071.
- **Tasks:** define schemas; implement validators/serialization; add transactional
  store; bind ingestion after canonical version creation; add exact-byte
  re-supply; implement occurrence inventory and GC guards; document retention.
- **Dependencies:** ADR acceptance and migration harness.
- **Failure modes:** hash/MIME mismatch, missing bytes, partial extraction,
  duplicate occurrence, unauthorized link, failed migration.
- **Security:** occurrence-based ACL, byte/pixel limits, safe filenames/headers.
- **Observability:** stored/deduped bytes, occurrences, omissions, hash failures.
- **Tests:** unit identity/locator; integration upload/reparse; contract store;
  migration fresh/upgrade/rollback; security shared hash; performance large
  inventory; deterministic repeat ingestion.
- **Rollback:** disable catalog writes/reads; retain canonical Phase 0–8 data.

### 5.2 Parser extraction coverage

**Status:** IMPLEMENTED / TESTED. PDF, DOCX, PPTX, XLSX, HTML/Markdown data
URIs, and standalone images emit bounded typed occurrences. V1 canonical
publication remains the frozen ingestion projection. OCR, rendering, packaged
resource acquisition, and generated descriptions remain pending.

- **Purpose:** emit ordered occurrences from PDF, DOCX, PPTX, XLSX, HTML,
  Markdown, standalone images, and scanned PDFs without text regressions.
- **Inputs:** retained original asset and bounded decoder stream.
- **Outputs:** existing textual IR plus typed transient occurrences/omissions.
- **Interfaces/models:** additive parser transport V2; adapters preserve V1.
- **Storage/migrations:** no canonical model change; catalog writes from 5.1.
- **Tasks:** specify format capability matrix; preserve inline order and page/
  slide/sheet/DOM/cell geometry; implement standalone parser; secure SVG and
  archive decoding; add scanned-page signals; expose omission reasons.
- **Dependencies:** 5.1.
- **Failure modes:** bombs, corrupt relation, unsupported encoding, geometry
  unavailable, repeated media, decoder timeout.
- **Security:** isolated decode, decompression/pixel quotas, no external fetch.
- **Observability:** blocks/assets/omissions per format and decoder resource use.
- **Tests:** golden format fixtures, corruption, bombs, order/location, repeated
  assets, no meaningful text loss, deterministic outputs.
- **Rollback:** feature flags/parser priority revert to V1 extraction.

### 5.3 Durable processing and governance

- **Status:** IMPLEMENTED / TESTED (Phase 8.5.3 gate)

- **Purpose:** safely run expensive optional derivations.
- **Inputs:** immutable manifest, authorized occurrences, provider profile,
  consent, estimates, budgets.
- **Outputs:** job/attempt/checkpoint/result records and progress events.
- **Interfaces/models:** `ProcessingJobStoreV1`, `ProcessingWorkerV1`, manifest,
  consent, estimate, budget, checkpoint, failure models.
- **Storage/migrations:** job/attempt/checkpoint/ledger tables.
- **Tasks:** implement fingerprint/idempotent submit; conditional claim/lease;
  worker loop; bounded retry; cancel/resume; crash recovery; provider resource
  admission; estimate/actual ledger; progress subscription; operator cleanup.
- **Dependencies:** 5.1 and ADR-0071.
- **Failure modes:** worker crash, lease loss, provider timeout, cancellation
  race, budget breach, stale authorization, duplicate result.
- **Security:** actor/notebook scope, no secrets in manifest, egress consent.
- **Observability:** queue/claim/run latency, attempts, progress, cache, costs.
- **Tests:** state-machine unit; SQLite concurrency/rollback; crash at every
  boundary; cancellation; policy; performance queue saturation.
- **Rollback:** stop workers/reject submit while retaining recoverable state.

### 5.4 OCR derivations

**Status:** IMPLEMENTED / TESTED (Phase 8.5.4). Provider/model quality
benchmarking and deployment profile selection remain an explicit later
operational decision; no provider is silently selected.

- **Purpose:** produce searchable, attributable regions for scanned content.
- **Inputs:** occurrence/page rendering, language hints, OCR profile, budgets.
- **Outputs:** `OCRResult`, ordered regions, language observations, derived
  sparse/vector generation.
- **Interfaces/models:** `OCRProviderV1`, scanned-page detector, OCR index adapter.
- **Storage/migrations:** derivation payload and region projection tables.
- **Implemented tasks:** provider-neutral contract and registry injection;
  preprocessing/cache identities; conservative detector; governed job handler;
  immutable result/cache; independent OCR FTS projection; occurrence-region
  evidence references; partial/failure/cancel/retry policy; mixed-script model
  fixtures. Benchmark-selected concrete provider adapters remain pending.
- **Dependencies:** 5.2–5.3.
- **Failure modes:** unreadable page, wrong language, partial regions, timeout,
  low confidence, invalid geometry.
- **Security:** image limits/sandbox, untrusted OCR instructions, egress policy.
- **Observability:** page/region counts, confidence bands, scripts, cache/cost.
- **Tests:** provider contract, mixed scripts, geometry, partial/cancel/retry,
  cache invalidation, prompt injection, throughput.
- **Rollback:** detach OCR indexes/provider; original and text indexes remain.

### 5.5 Vision analysis and visual vectors

**Status:** IMPLEMENTED / TESTED (Phase 8.5.5). Provider/model quality
benchmarking, concrete deployment adapters, and multimodal retrieval remain
explicit later work; no provider is silently selected.

- **Purpose:** add optional visual observations and independently managed visual
  vectors as foundations for later native visual retrieval.
- **Inputs:** authorized occurrence, operation schema, provider profile, budgets.
- **Outputs:** structured vision derivation and/or vector in a named space.
- **Interfaces/models:** `VisionAnalysisProviderV1`,
  `ImageEmbeddingProviderV1`, optional shared-space provider.
- **Storage/migrations:** derivations plus side-by-side vector generations.
- **Implemented tasks:** typed analysis schemas; provider-neutral vision and
  image-embedding contracts; deterministic preprocessing/cache/derivation
  identities; dimension/finite/normalization guards; immutable SQLite results;
  generation build/project/promote/rollback and stale-generation guards;
  ADR-0060 job, consent, budget, cancellation, retry, and crash recovery.
  Concrete adapters, provider benchmarks, and cross-space fusion remain later.
- **Dependencies:** 5.2–5.3.
- **Failure modes:** invalid schema, unsafe output, dimension drift, missing
  vector, provider refusal, incompatible space.
- **Security:** prompt injection, egress consent, no implicit original delivery.
- **Observability:** schema/model/space, vector count, cache, latency/cost/safety.
- **Tests:** provider schemas, dimensions/normalization, shared-space proof,
  malformed images, cache/migration/rollback, retrieval benchmark.
- **Rollback:** switch collection aliases/disable provider profile.

### 5.6 Advanced retrieval and completeness

**Status:** IMPLEMENTED / TESTED (Phase 8.5.6). The additive V2 service is an
internal core contract; V1 HTTP/MCP routes remain unchanged. Structured
aggregation, multimodal Final QA, and delivery adapters remain later work.

- **Purpose:** separate ranked relevance from exact/exhaustive enumeration.
- **Inputs:** `RetrievalPlanV2`, authorized snapshot, bounds.
- **Outputs:** `RetrievalResultSetV1` with stable cursor and completeness.
- **Interfaces/models:** planner V2, exact/positional/exhaustive services,
  result-set/cursor models.
- **Storage/migrations:** existing canonical chunk/FTS/title projections are
  queried additively; signed cursors bind immutable snapshot hashes. No schema
  migration was required.
- **Tasks:** typed planner validation; exact/version lookup; page/slide/chunk
  range; deterministic exhaustive traversal; result-set fingerprint; cursor
  signing/expiry; completeness propagation; ranked V1 adapter.
- **Dependencies:** 5.1 and 5.3.
- **Failure modes:** expired cursor, concurrent mutation, unsupported plan,
  forced truncation, unstable order, authorization change.
- **Security:** signed scoped cursors and hard scan/page/result budgets.
- **Observability:** plan, examined/returned, pages, completeness, truncation.
- **Tests:** exactness, stable pagination, mutation, tampering, forced partial,
  deterministic ties, scale and cancellation.
- **Rollback:** disable V2 plans/routes; V1 ranked retrieval unchanged.

### 5.7 Structured retrieval and aggregation

**Status:** IMPLEMENTED / TESTED (Phase 8.5.7). The additive typed executor
consumes `RetrievalResultSetV1`; V1 retrieval and Final-QA remain unchanged.

- **Purpose:** answer table/data questions deterministically.
- **Inputs:** schema observation and validated `StructuredQueryV1`.
- **Outputs:** typed rows/aggregates, row universe, completeness, provenance.
- **Interfaces/models:** schema discovery, query IR, safe compiler/executor.
- **Storage/migrations:** schema v11 adds versioned immutable row/cell
  projections and reuses the atomic index-generation lifecycle.
- **Tasks:** project CSV/XLSX/document tables; infer/confirm types; validate
  identifiers/operators; parameterized compile; filter/group/aggregate/sort;
  stable cursor; map rows/cells to source evidence; ambiguity errors.
- **Dependencies:** 5.6.
- **Failure modes:** ambiguous columns, type coercion, overflow, projection
  stale, unsupported operation, scan limit.
- **Security:** no raw SQL, parameter values, allowlisted functions/scope.
- **Observability:** operation, rows examined/returned, completeness, rejection.
- **Tests:** aggregates against known truth, nulls/Unicode, injection, overflow,
  cursor, stale projection, migration, scale.
- **Rollback:** disable structured planner/projection alias; text fallback only.

### 5.8 Multimodal retrieval, context, citations, and Final QA V2

**Status:** IMPLEMENTED / TESTED (Phase 8.5.8). The additive V2 domain and
persistence path is internal/provider-neutral; versioned HTTP/MCP delivery and
concrete multimodal provider profiles remain later workstreams.

- **Purpose:** ground answers in typed text/visual/structured evidence.
- **Inputs:** V2 result sets/candidates, authorized assets/derivations, budgets.
- **Outputs:** multimodal context, `EvidenceCitationV2`, immutable `FinalQAResultV2`.
- **Interfaces/models:** candidate/fusion/reranker/context/citation/final-QA V2.
- **Storage/migrations:** V2 evidence and execution snapshot tables.
- **Tasks:** candidate adapters; rank fusion across spaces; modality reranker;
  diversity; budgeted context; provider modality negotiation; marker resolver;
  ADR-0054 retry; ADR-0056 claim/validated/publication/replay/resume; typed
  completeness/no-context failures.
- **Dependencies:** 5.4–5.7.
- **Failure modes:** unauthorized evidence, incompatible scores, budget omission,
  invalid citation, provider lacks modality, crash/concurrent claim.
- **Security:** reauthorize evidence, untrusted derived prompts, no chain of
  thought/raw provider persistence.
- **Observability:** candidate/evidence kinds, budgets, completeness, execution
  state/retry/replay, grounded outcome.
- **Tests:** every evidence kind, cross-modal fusion, provenance, marker cases,
  retry/exhaustion, crash/concurrency, exact replay, V1 non-regression.
- **Rollback:** disable V2 binding; immutable V2 records retained; V1 active.

### 5.9 Multilingual retrieval and generation

**Implementation status:** IMPLEMENTED / TESTED. Provider-neutral language,
translation, embedding, reranking, retrieval, and answer-policy contracts plus
schema v13 are complete. Phase 8.5.11 provisioned and measured three embedding
and three reranker candidates across English/Hindi/Marathi directions. The
complete profile remains uncertified because downstream visual and Final-QA
quality gates failed.

- **Purpose:** certified same- and cross-language retrieval/generation.
- **Inputs:** language/script observations, query, provider profiles, originals.
- **Outputs:** selected language path, ranked evidence, answer language metadata.
- **Interfaces/models:** detector/translation derivations, analyzer generations,
  multilingual planner/reranker/answer policy.
- **Storage/migrations:** language observations, translations, analyzer/vector
  generations.
- **Tasks:** build English/Hindi/Marathi corpus; benchmark detectors/OCR/
  embeddings/rerankers; implement mixed-script/transliteration policy; add
  cross-language fusion; preserve original citations; publish capability matrix.
- **Dependencies:** 5.4–5.8 and evaluation pack.
- **Failure modes:** uncertain language, mistranslation, unsupported direction,
  model regression, derived-original mismatch.
- **Security:** multilingual injection corpus and consent for translation.
- **Observability:** direction/profile/confidence/fallback/metric cohort/cost.
- **Tests:** per-language/direction retrieval metrics, mixed scripts,
  transliteration, OCR, grounding/citations, negatives and regressions.
- **Rollback:** switch to current English/text profile and mark unavailable.

### 5.10 Bounded HTTP/MCP delivery and UI contract

**Implementation:** Implemented/tested. The shared expansion service, bounded
V2 HTTP adapters, four additive MCP tools, native resource content, capability
discovery, signed cursors, authorization, and typed limits are complete. Phase
9 retains UI implementation; Phase 8.5.11 retains final profile certification.

- **Purpose:** expose certified capabilities without duplicating domain logic.
- **Inputs:** authenticated DTO/tool/resource request and negotiated limits.
- **Outputs:** typed JSON/events, safe binary stream, MCP image/resource content.
- **Interfaces/models:** expansion service, job/retrieval/final-QA interfaces,
  thin adapters and shared typed error mapping.
- **Storage/migrations:** none beyond prior modules.
- **Tasks:** freeze OpenAPI/tool schemas; routes for inventory/resource/jobs/
  retrieval/FinalQA V2; four MCP tools and resources; stdio/SSE parity; stream
  cancellation; capability states; UI mock client/viewer/progress contracts.
- **Dependencies:** 5.3–5.9.
- **Failure modes:** oversized payload, disconnect, stale cursor, MIME mismatch,
  unavailable capability, auth failure.
- **Security:** occurrence ACL, auth/isolation, rate/byte limits, safe headers.
- **Observability:** route/tool/resource, status, bounded size, cursor, latency.
- **Tests:** OpenAPI/MCP contract, all error paths, auth, binary, streaming,
  disconnect, old six tools, UI mocks/accessibility.
- **Rollback:** remove capability advertisement/routes; old APIs/tools remain.

### 5.11 Security, performance, evaluation, and release certification

- **Purpose:** prove production readiness without weakening prior evidence.
- **Inputs:** all modules, evaluation pack, supported deployment profiles.
- **Outputs:** threat model, benchmark reports, certification matrix, release
  recommendation.
- **Interfaces/models:** expectation manifests, metric/profile schemas, audit
  evidence records.
- **Storage/migrations:** test fixtures only; no production identity mutation.
- **Tasks:** adversarial/media/provider/cost tests; load/soak; migration matrix;
  Phase 0–8 regression; Golden plus Phase 8.5 pack; HTTP/MCP live matrix;
  documentation/governance review; CI and artifact validation.
- **Dependencies:** all modules.
- **Failure modes:** unmeasured claims, profile drift, flaky providers, leaked
  fixture data, performance regression, stale docs.
- **Security:** independent threat review and fail-closed capability matrix.
- **Observability:** publish scoped metrics/evidence and exact profile versions.
- **Tests:** all Section 8 categories and gates; ≥90% coverage remains necessary
  but not sufficient.
- **Rollback:** keep features disabled/unadvertised; revert aliases, not canonical
  data; preserve failed evidence honestly.

---

## 6. Milestones

| Milestone | Deliverables | Acceptance/tests | Dependencies | Principal risks | Rollback point |
|---|---|---|---|---|---|
| M0 — Architecture/ADR acceptance | blueprint, ADR-0058–0071, roadmap, expectation schema | contradiction audit; links/status checks | v0.25.0 | ambiguous ownership | withdraw planning ADR before implementation |
| M1 — Asset foundation | original refs, occurrence catalog, generation lifecycle | fresh/upgrade/rollback; exact hashes; ACL | M0 | identity/leakage | disable catalogs |
| M2 — Extraction coverage | all format occurrences and typed omissions | format/security matrix; no text regression | M1 | bombs/order loss | parser feature flags |
| M3 — Durable processing | store, worker, consent/cost/progress | concurrency/crash/cancel/budget | M1 | duplicate work/cost | stop workers |
| M4 — OCR | detector, provider, regions, index | scripts/geometry/partial/cache/security | M2–M3 | false text/injection | detach OCR index |
| M5 — Vision/vector | VLM schemas, image vectors, generations | dimensions/shared-space proof/cost | M2–M3 | model drift | alias rollback |
| M6 — Advanced retrieval | plans, exact/position/exhaustive/structured | completeness/cursor/aggregate/injection | M1, M3 | false completeness | V1-only policy |
| M7 — Multimodal QA | candidates, context, citations, snapshots V2 | grounding/retry/replay/crash/concurrency | M4–M6 | provenance flattening | disable V2 |
| M8 — Multilingual | observations, profiles, translations | per-direction metrics and negatives | M4–M7 | overclaim | English/text profile |
| M9 — HTTP/MCP | bounded routes, four tools/resources | live HTTP, stdio/SSE, binary/auth | M3–M8 | payload/leakage | unadvertise |
| M10 — Security/performance | threat closure and benchmarked profiles | adversarial/load/soak/resource gates | M1–M9 | DoS/cost | profile disable |
| M11 — Full certification | Phase 0–8 + 8.5 evidence and docs | G0–G10, CI, reproducibility | M10 | hidden regression | no release |
| M12 — Release readiness | sanitized diff, operator migration/rollback, notes | final gates repeated; artifacts verified | M11 | packaging/config drift | retain prior release |

---

## 7. Phase gates

| Gate | Requirement | Evidence required |
|---|---|---|
| G0 | Architecture accepted | ADR package, contradiction audit, open-decision register |
| G1 | Evaluation/governance accepted | fixture licenses/hashes/manifests and profile schema |
| G2 | Asset foundation certified | migration, integrity, occurrence ACL, reparse and rollback |
| G3 | Processing certified | concurrency, crash, cancel/resume, budget/consent, audit |
| G4 | Extraction/OCR/VLM/indexing certified | format matrix, provenance, provider/cache/generation evidence |
| G5 | Retrieval certified | exact/ranked/position/structured/exhaustive/multimodal metrics |
| G6 | Final QA/citation certified | grounding, compliance, immutable replay/recovery, V1 regression |
| G7 | Multilingual certified | published per-language/direction metrics and safe fallbacks |
| G8 | HTTP/MCP/UI contract certified | live protocols, bounds, auth, binary delivery, accessibility mocks |
| G9 | Security/performance/cost certified | threat closure and benchmarked deployment profiles |
| G10 | Full Phase 8.5 certified | all prior gates, full quality/build/CI/docs, clean release inputs |

No gate passes because code compiles, a unit test exists, or a provider claims
support. Disabled or unconfigured capabilities are reported honestly.

---

## 8. Testing and certification matrix

| Area | Unit | Integration/contract | Migration/recovery | Security/performance | Live/E2E |
|---|---|---|---|---|---|
| assets/occurrences | hashes, locators, serialization | ingestion/catalog/filesystem | fresh/upgrade/rollback/GC | shared-hash ACL, bombs, inventory scale | upload, inspect, exact reparse |
| jobs/cost | state machine, budgets, fingerprint | worker/provider/progress | lease/crash/cancel/resume | cost DoS, secret/log checks, saturation | submit/watch/cancel/retry |
| OCR | regions/languages/confidence | detector/provider/index | cache/generation rollback | pixels/time/injection, throughput | scanned docs and citations |
| VLM/vectors | schemas/dimensions/cache | provider/Qdrant optionality/fusion | side-by-side alias rollback | egress/injection/GPU memory | image query and inspection |
| advanced retrieval | plan/result/cursor/completeness | storage/planner/rerank | cursor snapshot recovery | tampering/scan limits/latency | exact and exhaustive queries |
| structured | IR/type/compiler/aggregate | projection/executor/provenance | stale/rebuild/rollback | SQL injection/overflow/scale | known-truth table questions |
| multimodal QA | candidate/context/citation/fingerprint | engine/provider/persistence | crash/concurrency/replay | unauthorized evidence/injection | persisted answers and replay |
| multilingual | detection/path/fallback | analyzer/embed/rerank/QA | profile generation rollback | multilingual injection/cost | per-direction corpus matrix |
| HTTP/MCP | DTO/schema/errors | app services and both transports | disconnect/cancel/resume | auth/isolation/rate/payload | real server/client all tools |
| compatibility | frozen model contracts | Phase 0–8 suites | v0.25.0 upgrade | no widened access | 15-document corpus regression |

### Mandatory test classes

- deterministic unit/property tests for identity, canonical serialization,
  cursors, order, fingerprints, and cache keys;
- provider contract tests with recorded/offline fixtures plus separately gated
  live local/cloud profiles;
- transactional migration, idempotency, rollback, interrupted build, alias,
  crash, concurrent claim, and garbage-collection tests;
- parser/resource adversarial tests for malformed PDF/DOCX/PPTX/XLSX/images,
  ZIP/decompression/pixel bombs, SVG, external references, and cancellation;
- retrieval evaluation for recall/rank, completeness truth, aggregate exactness,
  positional fidelity, cross-document ambiguity, multimodal and cross-language;
- Final QA compliance, correction exhaustion, no-context/partial-context,
  publication order, citation attribution, snapshot immutability, zero-call
  replay, mismatch conflict, and legacy behavior;
- HTTP OpenAPI and MCP schema/live protocol tests, cursors, binary MIME,
  disconnect, auth/error mapping, and old-tool compatibility;
- frontend contract/a11y tests in Phase 9, with Phase 8.5 mock consumers only;
- performance/load/soak and resource-budget tests per supported profile;
- full pytest with ≥90% coverage, Ruff, strict mypy, package/frontend/Docker
  builds, diff checks, CI, and documentation link/status checks.

---

## 9. Evaluation-pack expansion

The frozen 15-document Golden Corpus remains unchanged. A separate
`phase8_5_eval_v1` pack is versioned by manifest and contains:

| Fixture class | Minimum content | Expected evidence |
|---|---|---|
| standalone images | photo, diagram, chart, text image, duplicate bytes | asset/occurrence identity, visual/OCR targets |
| scanned PDFs | English, Hindi, Marathi, mixed pages, partial corruption | page detection, OCR regions, original citation |
| image-rich PDF | repeated/cropped images and captions | page/bbox/order and dedup occurrences |
| PPTX | short/image-only/text+image slides | physical slide and occurrence preservation |
| DOCX | inline/floating/repeated images and tables | document order and relationship provenance |
| XLSX | multiple sheets, embedded images, typed tables | sheet/cell anchors and exact aggregates |
| structured CSV/XLSX | nulls, Unicode, known counts/averages/groups | row universe, exact result, complete cursor |
| positional | known page/slide/section/chunk ranges | deterministic bounded expansion |
| multilingual | parallel/nonparallel EN/HI/MR plus transliteration | same/cross-language ranking and original evidence |
| adversarial | bombs, malformed media, SVG references, image prompt injection | typed rejection, bounded resource use, no leakage |
| completeness | stable sets, forced truncation, concurrent mutation | exact COMPLETE/PARTIAL/TRUNCATED/UNKNOWN outcomes |
| authorization | shared hashes in two notebooks/users | occurrence-scoped allow/deny behavior |

Each expectation manifest pins hashes, licenses, structural counts/ranges,
queries, relevant evidence IDs or predicates, aggregate truth, allowed ordering,
completeness, language direction, provider profile, cost/resource ceilings, and
negative/security expectations. No personal or secret corpus is committed.

---

## 10. Security and risk matrix

| ID | Threat/risk | Sev. | Prevent/detect | Gate |
|---|---|---:|---|---|
| R1 | derived OCR/VLM treated as original truth | P0 | typed derivations and original link in every V2 citation | G6 |
| R2 | shared asset leaks across notebooks | P0 | occurrence-path authorization on every read/cache/cursor | G2/G9 |
| R3 | false exhaustive/completeness claim | P0 | stable result set, termination proof, negative tests | G5 |
| R4 | structured query injection/wrong aggregate | P0 | typed IR, parameter binding, known-truth evaluation | G5/G9 |
| R5 | multimodal snapshot loses provenance | P0 | immutable typed V2 snapshot; no reconstruction | G6 |
| R6 | archive/image decompression or pixel bomb | P0/P1 | preflight, sandbox, byte/pixel/time/memory ceilings | G4/G9 |
| R7 | prompt injection in image/OCR/translation | P1 | untrusted-evidence boundary, adversarial corpus | G6/G9 |
| R8 | unauthorized cloud egress | P1 | disabled default, consent/policy manifest, audit | G3/G9 |
| R9 | cost/resource denial of service | P1 | estimates, hard budgets, rate/admission limits | G3/G9 |
| R10 | duplicate jobs/partial publication | P1 | idempotency, leases, conditional states, immutable outputs | G3 |
| R11 | incompatible vector spaces compared | P1 | named spaces, separate generations, rank fusion | G4/G5 |
| R12 | cache poisoning or stale derived result | P1 | full cache identity, authorization, generation validation | G4/G9 |
| R13 | asset/resource path traversal | P1 | opaque IDs, no caller paths, safe disposition/MIME | G8/G9 |
| R14 | multilingual quality overclaim | P1 | per-direction capability profile and thresholds | G7 |
| R15 | old version cannot reparse | P2 | explicit unavailable and exact-hash re-supply | G2 |
| R16 | storage growth/unsafe GC | P2 | lazy jobs, quotas, generation/reference-aware retention | G9 |
| R17 | provider/model drift | P2 | pinned revisions, side-by-side generations, recertification | G4/G7 |
| R18 | UI hides cost or evidence derivation | P2 | mandatory explicit controls/labels and contract tests | G8 |

---

## 11. Cost, compute, observability, and performance

### 11.1 Planning-level resource model

Every processing estimate records operation, item/page/pixel/token counts,
cache status, provider trust class, model profile, expected wall-time range,
local CPU/GPU/RAM/VRAM range, cloud request/token/currency range where known,
and uncertainty. The manifest stores user-selected operations and hard ceilings.

| Operation | Principal cost units | Mandatory estimate inputs |
|---|---|---|
| local/cloud OCR | pages, decoded pixels, languages | page inventory, resolution, provider profile |
| local/cloud VLM | images, pixels, input/output tokens | selected occurrences, schema, model |
| visual embeddings | images, pixels, vectors | preprocessing/model/dimension/cache |
| translation | characters/tokens, language pairs | segment inventory, direction, provider |
| index/model migration | items, vectors, storage | source/target generations and cache |
| full expansion | bytes, blocks/pages/assets | requested view and hard transport limits |

The UI/API displays estimates before consent, cache hits separately, progress
and actuals during execution, and terminal budget/failure state. No estimate is
presented as a guarantee.

### 11.2 Performance targets

Exact production SLOs require baseline benchmarks; implementation must first
establish p50/p95/p99 and resource curves for supported hardware profiles.

| Capability | Metric to establish | Acceptance method |
|---|---|---|
| ingestion/extraction | MB/s, pages/slides/sheets/s, peak memory | format/size matrix; no Phase 0–8 regression |
| OCR | pages/s and p95/page by script/profile | warm/cold/cache cohorts |
| VLM | p95/image, tokens, GPU/cloud cost | image-size/schema cohorts |
| embeddings | images/s, cache hit, dimension failures | cold/warm/generation builds |
| ranked retrieval | p50/p95/p99 and quality | corpus-size/modality/profile matrix |
| exhaustive/structured | rows/s, time-to-first-page, completion | bounded known-result datasets |
| document/MCP delivery | p95 first byte, throughput, memory | page/asset/payload cohorts and disconnect |
| multilingual | latency delta plus per-direction quality | same/cross-language benchmark |
| job recovery | lease detection and resume time | deterministic crash injection |

Before G9, benchmark owners set profile-specific budgets from measured
baselines. Arbitrary numbers are not frozen in planning.

### 11.3 Observability contract

Use structured metrics/logs/traces with correlation IDs and opaque scoped IDs.
Never log document text, image bytes, OCR/VLM output, vectors, prompts, secrets,
tokens, or personal filenames.

- extraction: format, bytes, blocks/assets/omissions, decoder resources;
- jobs: state/attempt/lease/progress/cancel, queue/run latency, cache, estimates/
  actuals, policy outcome;
- OCR/VLM/embedding: provider/model/config/space, counts, confidence bands,
  dimensions, latency/cost/failure;
- retrieval: plan, sources, examined/returned, ranks, completeness, truncation,
  cursor pages, latency;
- context/Final QA: evidence kinds/counts, budgets, omissions, completeness,
  citation compliance/retry, execution/replay state;
- HTTP/MCP: route/tool/resource, status/error, payload bounds, disconnect;
- multilingual: language/script/direction/profile/fallback and metric cohort.

---

## 12. Future-phase compatibility

### Phase 9 may assume

- certified capability discovery, explicit unavailable/disabled states;
- bounded document/asset/job/retrieval/FinalQA V2 HTTP contracts;
- original-versus-derived provenance and consent/cost state;
- stable cursors, completeness, progress/cancel, and safe binary delivery.

### Phase 9 must not assume

- every document has retained originals or images;
- OCR/VLM/vector/cloud provider availability;
- Qdrant/SurrealDB enabled;
- universal languages, unbounded expansion, or free processing;
- V2 evidence can be flattened to V1 Citation.

### Phase 10–13 boundaries

- Phase 10 extends ADR-0060 jobs for notebook features; it does not replace the
  queue contract.
- Phase 11 consumes typed result sets/evidence for multi-hop reasoning and must
  preserve completeness/provenance.
- Phase 12 implements providers/plugins behind accepted interfaces and trust
  policy; plugins cannot create new authorization boundaries.
- Phase 13 owns production-scale benchmarks, rate limits, deployment hardening,
  retention operations, and published SLOs.

Potential future deprecations (only through successor ADRs) are parser V1
transport after all adapters migrate and text-only context as the default for
multimodal-capable clients. Canonical Phase 0–8 identities and historical
snapshots are not deprecation candidates.

---

## 13. Open architectural decisions

The architectural responsibilities are accepted. These implementation-profile
choices remain deliberately open and do not block foundational work:

1. benchmark-selected OCR, VLM, visual embedding, multilingual embedding, and
   reranker models/revisions for each hardware/trust profile;
2. measured hard default byte/token/page/slide/asset/pixel and job ceilings,
   including operator override ranges;
3. exact Phase 8.5 versioned HTTP paths/DTO field names after schema review;
4. supported cloud regions/providers and organization consent policy;
5. benchmark thresholds per language direction and modality;
6. retention durations for originals, derived outputs, job records, cursors,
   superseded generations, and audit events;
7. whether a benchmark winner justifies an optional shared multimodal space.

No implementation may fill these silently. Each becomes a reviewed provider/
deployment profile or, if it changes an architectural contract, a successor ADR.

---

## 14. Master implementation checklist

### Architecture and foundations

- [x] G0/G1 accepted with contradiction and fixture reviews.
- [x] ADR-0058–0071 traced to interfaces, schemas, tests, and owners.
- [x] Asset catalog/original retention and occurrence authorization certified.
- [x] Additive migrations/generation rollback certified on fresh and v0.25.0.

### Processing and derivations

- [x] Durable jobs, cost/consent, cancellation, crash/recovery certified.
- [x] Format extraction matrix certified with typed omissions.
- [x] OCR/vision derivations preserve original provenance; Tesseract en/hi/mr and Qwen2.5-VL profiles benchmarked & validated.
- [x] Visual spaces/cache/generations certified without mandatory Qdrant; CLIP ViT-L/14 benchmarked.

### Retrieval and QA

- [x] Ranked versus exhaustive completeness is truthful.
- [x] Exact/positional canonical bounds, signed cursors, and bounded resource delivery are certified.
- [x] Structured aggregates match known truth with no arbitrary SQL.
- [x] Multimodal fusion/context/citations/FinalQA V2 certified.
- [x] ADR-0054 compliance and ADR-0056 replay/recovery remain exact.
- [x] Provider-neutral multilingual contracts pass; BGE-M3 embedding and BGE-reranker-v2-m3 benchmarked as winners.

### Delivery, security, and release

- [x] HTTP and MCP old/new matrices pass with authorization and limits (258/258 server tests passed).
- [x] Phase 9 UI contract capability contract defined.
- [x] Threat matrix closed and supported profiles meet measured performance/cost.
- [x] Phase 0–8 regression and frozen 15-document corpus pass unchanged.
- [x] Full quality/build/CI and active documentation consistency pass (Ruff, strict mypy, 3 package builds).
- [x] Benchmark-selected model profiles registered in `phase8_5_models.toml`.

---

**Implementation readiness statement:** Workstreams 8.5.1–8.5.11 are fully
implemented, benchmarked, and governed. Production profiles (`BAAI/bge-m3`,
`BAAI/bge-reranker-v2-m3`, `openai/clip-vit-large-patch14`, `qwen2.5vl:latest`)
are established with external D: model storage. Phase 8.5 foundations are ready for Phase 9 UI development.
