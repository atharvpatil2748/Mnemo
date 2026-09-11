# PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL
# Full Multilingual V2 Implementation Plan

## 1. Authorization boundary

This plan is not implementation authorization. Stage 0 may begin only after the current EN/HI/MR evaluation has stopped and its databases, raw rankings, reranker inputs, reports, transcripts, and capability snapshot are frozen. No stage may write to the Golden Dataset, frozen multimodal database/manifest, or current WP-10 evaluation database.

## 2. Invariants

- Canonical `Chunk.text`, source files, filenames, OCR/Vision/CLIP outputs and generation identities remain immutable.
- Language and script are independent. No script-only language assertion.
- Transformations are additive, exact-profile, authorized, provenance-preserving derivations.
- Authorization precedes enumeration, transformation, embedding, scoring, and result delivery; final provenance/scope is revalidated.
- V1, CLIP and each multilingual model revision remain separate vector spaces.
- Model/provider support never establishes Mnemo readiness, exposure, verification, or certification.
- Production and evaluation use the same typed reranker candidate builder.
- A retrieval miss cannot be classified as corpus absence without census proof.
- Generic/ungrounded prompts never enter semantic quality metrics.
- Existing HTTP/MCP tool names, V2 envelopes and CursorCodecV2 remain stable.

## 3. Staged implementation

### Stage 0 — Governance and evidence freeze

**Work:** freeze the current EN/HI/MR run and record its known defects; approve a new ADR or ADR amendments for representation transformation, per-language capability evidence, typed reranker inputs, and V2 evaluation stratification.

**Files later affected:** new ADR/profiles/evaluation manifest; no code.  
**Acceptance:** hashes and immutable locations for V1 DB, raw ranks, exact reranker input audits, qrels, reports, and capability document. The Marathi census and title-only reranker defect are recorded without rewriting historical evidence.  
**Rollback:** withdraw proposal; runtime unchanged.

### Stage 1 — Capability and identity records

**Work:** add `LanguageOperationCapabilityV2`, `ProviderLanguageClaimV1`, `GenerationLanguageCoverageV1`, and `LanguageCapabilityRegistryV1` as an adapter over `Phase85RuntimeV1`.

**Files:** `mnemo-core/mnemo/models/multilingual.py`, `interfaces/multilingual.py`, `phase85/models.py`, `phase85/runtime.py`; configuration/profile schema.  
**Tests:** arbitrary valid BCP-47/ISO-15924 values, operation-specific states, negative states, implication/property tests, no state inferred from model presence.  
**Acceptance:** new language metadata can be registered without modifying retrieval source; state cannot skip ADR-0074 evidence.  
**Rollback:** disable adapter and omit additive capability detail.

### Stage 2 — Generic language and script observation

**Work:** add `LanguageDetectorProviderV2` and `ScriptDetectorV1` registries. Preserve `ConservativeENHIMRDetector` as the frozen baseline plugin. Return multiple hypotheses/`und`, confidence semantics, detector/config identity, scope and source provenance.

**Files:** `retrieval/multilingual.py`; new `retrieval/language_detection.py`; models/interfaces; profile config.  
**Tests:** multiple scripts, same-script languages, mixed/unknown, metadata precedence, ambiguity, deterministic output, no Latin→English or Devanagari→Hindi/MR shortcut.  
**Acceptance:** core planner consumes capability records, not `if en/hi/mr` branches.  
**Rollback:** select baseline plugin and withdraw new language admissions.

### Stage 3 — Representation detection and transformation

**Work:** implement contracts in `REPRESENTATION_TRANSFORMATION_MODEL.proposed.json`: representation observations, immutable font/encoding profiles, transformer registry and additive derived outputs. Detection may use parser font/encoding metadata and text signatures but cannot infer language or mutate canonical content.

**Files:** new `models/text_representations.py`, `interfaces/text_representations.py`, `retrieval/representations.py`, `phase85/representations.py`, additive storage/projection support; parser adapters only if existing metadata is not surfaced.  
**Tests:** Unicode semantic text, generic legacy-font fixture, PDF encoding anomaly, unknown, mixed representations, deterministic transform, content hashes, authorization, idempotency, interrupted generation, no canonical mutation.  
**Acceptance:** a governed legacy-font fixture can produce Unicode semantic derived evidence with complete lineage; no document-name or Krutidev-only branch.  
**Rollback:** disable transform profile/generation and return `TRANSFORMATION_UNAVAILABLE` while canonical retrieval remains.

### Stage 4 — Central reranker candidate contract

**Work:** implement `MultilingualRerankCandidateV3`, `RerankerCandidateBuilderV1`, and `RerankerInputAuditV1`. Route production, model benchmarks, Decision-7/V2 evaluation and behavioral harnesses through it. Provider adapter receives only typed candidates.

**Files:** `models/multilingual.py`, `interfaces/multilingual.py`, new `retrieval/reranker_candidates.py`, `retrieval/multilingual_providers.py`, `retrieval/multilingual.py`, and a new governed V2 evaluator. Historical benchmark/scratch evaluators remain unchanged and cannot provide V2 parity evidence.  
**Tests:** empty/title-only rejection, actual chunk/region/derived text reaches provider, title remains metadata, source/rendered hashes, exact candidate identity/provenance, query/document preprocessing agreement, deterministic 256-token policy and truncation audit, stable ties.  
**Acceptance:** no call site can send an ad-hoc string; retained audit proves exact text representation scored.  
**Rollback:** disable V2 reranker path; deterministic RRF degraded result only where existing policy permits, never silent V1 reranker substitution.

### Stage 5 — Provider metadata generalization

**Work:** retain exact BGE adapters but expose provider-declared language/script/model/revision/vector/preprocessing capabilities as claims. Validate configured admission against detector, transform, generation and evaluation requirements.

**Files:** `retrieval/multilingual_providers.py`, model-profile interfaces/schema/config.  
**Tests:** offline-only exact revision, vector dimension/normalization, readiness and close, claim-vs-operational state, unavailable provider.  
**Acceptance:** adding an approved provider-language claim requires profile data, not core retrieval changes.  
**Rollback:** remove/disable claim/profile; affected capability becomes unavailable.

### Stage 6 — Generic generation and storage coverage

**Work:** extend the current generation chain with representation observations/transformations and explicit coverage manifests. Keep existing language observations, derivations, embeddings, `language_text`, `multilingual_vector` and aliases; never reinterpret old IDs.

**Files:** `phase85/multilingual.py`, new `phase85/representations.py`, `storage/multilingual.py`, `storage/projection_generations.py`.  
**Tests:** deterministic identity includes detector/transform/provider/preprocessing/vector-space and source generations; resume/idempotency; complete checksum/count; stale/partial rejection; atomic alias/rollback; arbitrary language/script coexistence.  
**Acceptance:** active coverage can be proven per source representation/language/operation.  
**Rollback:** move isolated V2 alias to prior READY generation; preserve failed manifest.

### Stage 7 — Retrieval planning, fusion and reranking

**Work:** planner chooses paths through capability facts, not fixed languages. Authorized evidence may contribute canonical, OCR, Vision, normalized, transformed, or transliterated representations. Dense/sparse candidates retain representation lineage; typed candidate builder feeds reranker.

**Files:** `retrieval/multilingual.py`, `multilingual_advanced.py`, advanced-source integration and engine composition.  
**Tests:** same/cross-language, mixed-script/language, transformed representation, OCR/Vision, bounded search, RRF, rerank limits, vector-space separation, authorization and version isolation, truthful partial/degraded states.  
**Acceptance:** an unsupported/unready path fails closed with a typed reason; no fallback is reported as multilingual success.  
**Rollback:** capability disabled; canonical/V1 paths continue.

### Stage 8 — Runtime, capability and transport exposure

**Work:** compose providers/registries once in `Phase85RuntimeV1`; derive HTTP/MCP capability details and guidance from exact runtime state. Preserve shared application services and schemas with additive/versioned detail.

**Files:** runtime/engine, `mnemo-server/.../services/capabilities_v2.py`, schemas, retrieval service, MCP contracts/tools and HTTP router only if additive fields are required.  
**Tests:** lifecycle implication, runtime/capability consistency, HTTP/MCP semantic parity, stdio/SSE parity, no secret/path leakage, arbitrary language request validation, forged language/principal cannot widen scope.  
**Acceptance:** static `("en","hi","mr")` is no longer the operational truth; provider-only languages are visible as unavailable/unvalidated rather than callable.  
**Rollback:** stop V2 exposure while retaining V1/V2 stable fields.

### Stage 9 — Evaluation architecture and observability

**Work:** implement `MULTILINGUAL_EVALUATION_ARCHITECTURE.proposed.md`, failure taxonomy, topic-grounded qrels, and retained stage traces. Evaluator consumes production candidate builder/application boundary.

**Files:** `evaluation/`, `mnemo-server/mnemo_server/evaluation/`, future evaluation scripts and schemas.  
**Tests:** each failure code predicate; query grounding; source census; reranker input audit; qrel validation; metric calculation; redaction; harness/runtime parity.  
**Acceptance:** each case identifies its failing layer; `CORPUS_ABSENT` and `UNSUPPORTED` cannot be inferred from a miss.  
**Rollback:** evaluator changes only; historical evidence remains immutable.

### Stage 10 — Regression before data work

Run focused generic suites plus retained EN/HI/MR, V1, OCR/Vision/CLIP, WP-14 authorization, CursorCodecV2, HTTP/MCP contract, Final-QA and capability regression. No existing baseline expectation is rewritten to hide historical defects.

### Stage 11 — Isolated V2 index construction

Create a disposable V2 database from an approved immutable source snapshot. Build only approved observations, representations, transforms, embeddings and projections. Verify source hashes before/after. Never write the frozen multimodal or current WP-10 database.

### Stage 12 — V2 evaluation, verification and certification

Run same-language admission cohorts and a stratified cross-language graph; retain raw candidates, inputs, scores and environment identity. Advance each operation/language/direction only with exact evidence. WP-16 behavioral verification and WP-17 certification remain distinct later gates.

## 4. Implementation traceability

`IMPLEMENTATION_TRACEABILITY_MATRIX.md` maps each forensic defect to contract, module, test and rollback evidence. No abstraction should be added unless it closes a mapped defect or an ADR-0067/0070/0074 lifecycle requirement.

## 5. Go/no-go

**CONTRACT-READY GO for implementation after human/governance approval of this resolved package.** The earlier NO-GO applied while the eight P0 contracts were open. The existing EN/HI/MR evaluation and protected baselines must still be frozen before any V2 data construction. Production work remains additive and cannot claim READY, ACTIVE or EXPOSED until the evidence in `V2_ACTIVATION_READINESS_CONTRACT.proposed.json` exists.
## 6. P0-gated implementation sequence

The first production implementation pass, after approval, is ordered and gated as follows:

1. Implement V3 evidence references as an additive type and a lossless V2 adapter. Do not replace V2 call sites wholesale.
2. Implement typed representation observations, profiles, registry lookup and derivations. Authorization precedes observation/transformation; canonical text is immutable.
3. Implement `RerankerCandidateBuilderV1` and require both production and evaluation to consume it through the public reranker interface.
4. Replace V2 evaluation construction with `MULTILINGUAL_EVALUATION_CONTRACT`; historical scratch evaluators remain immutable evidence and are never reused as the V2 harness.
5. Repair projected multilingual FTS scoping in `mnemo-core/mnemo/storage/multimodal_search.py` before any V2 exposure. Apply notebook authorization plus requested source, document, version, positional, occurrence and derivation scope before enumeration; revalidate returned lineage.
6. Generate every request/response representation enum from the canonical vocabulary and prove HTTP/OpenAPI/MCP/structured/fallback/capability semantic parity.
7. Compose the four-generation V2 readiness set in `Phase85RuntimeV1`; validate fingerprints, coverage, checksums, lineage, vector space, authorization, transport and rollback metadata.
8. Promote the alias set atomically only after READY. On any failure, retain or restore the prior complete compatible alias set; never partially promote.

### Exposure prohibition

`multilingual_retrieval_v2` MUST NOT become READY, ACTIVE or EXPOSED while any P0 implementation test is absent or failing. In particular, route/tool existence, provider marketing claims and a language-text alias are insufficient.

### Exact projected-FTS scope semantics

The server first resolves the principal's authorized notebook/source/document/version universe. Each nonempty client-requested `source_ids`, `document_ids`, and `version_ids` set is intersected with that universe and all resulting predicates are combined with AND. An empty requested set means no additional restriction inside the authorized universe; an empty intersection returns zero rows without revealing which identifier failed. Page/block/chunk positional selectors are converted to the existing canonical version-bound bounds and applied in the SQL predicate. Occurrence and derivation selectors must match the row's real lineage and authorized source generation. No candidate count, row identity, score, snippet, timing distinction, or continuation state is produced before these filters. Reconstructed results are validated again against principal, notebook, source, document, version, position, occurrence, derivation and generation before delivery. Missing, malformed, contradictory or unsupported scope fails closed.
