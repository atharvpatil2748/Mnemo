# PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL
# Mnemo Full Multilingual V2 — Pre-Implementation Architecture Audit

Audit date: 2026-08-30  
Repository root: `C:\Users\athar\Desktop\Mnemo`  
Scope: repository-grounded, read-only architecture audit. This file is the only artifact created by the audit.

## 1. Executive verdict

**NOT READY FOR IMPLEMENTATION.**

The Full Multilingual V2 direction is sound: it preserves immutable canonical evidence, separates language/script/representation, keeps BGE-M3 and the BGE reranker provider-specific, derives capability state from `Phase85RuntimeV1`, uses side-by-side generations, and makes evaluation stage-aware. The existing repository also contains strong reusable foundations: generic BCP-47 and ISO-15924 value types, authorization-safe `LanguageEvidenceReferenceV2`, exact vector-space identity, authorization-before-dense-enumeration, deterministic RRF, bounded provider adapters, immutable generation contracts, complete-only activation, atomic aliases, rollback, thin HTTP/MCP adapters, and strict completeness/provenance envelopes.

However, the ten proposal artifacts are not yet sufficiently concrete or mutually aligned to begin safe production coding. The audit found:

- **8 P0 blockers**: contract incompatibilities, an existing scoped-retrieval authorization defect, incomplete activation semantics, transport contradiction, and evaluation/reranker contract gaps.
- **14 P1 major items**: required generalization and operational correctness work whose target behavior is understood but whose exact contract or integration seam still needs approval.
- **7 P2 moderate items**: terminology, observability, and cleanup issues that should be resolved during implementation but do not independently block the architecture freeze.

This is a **proposal-readiness NO-GO**, not a rejection of the V2 architecture. Once the eight P0 decisions are amended in the proposal package and approved, implementation may start side-by-side without touching the current EN/HI/MR evaluation or frozen multimodal baseline.

### Protected-state verification at audit start

| Protected artifact | Read-only observation |
|---|---|
| Golden Dataset | 44 files; `manuscript.pdf` present, 164,240 bytes, SHA-256 `31ADDF387D13DE26E3B155E1FC6EE65D5F554CFDFB4281951C56E9482B6F8085`; Ramayana comparison PDF present, 3,602,997 bytes, SHA-256 `759F2ADBFD2FC1191FF8576401D1CBC34BBFEFAF79A573E8747C53D4C858AF75` |
| Frozen multimodal DB | `scratch/phase8_5_wp16/eval-20260828-01/mnemo.db`; 37,195,776 bytes; SHA-256 observed as `18835883DC3A01B588E4C43F44FBA1156941D0807D7C08C2A41FD11A802BF55D` |
| Frozen manifest | SHA-256 `17977EFC87D3D95BB1E2E6E6C8025E78B63A4C3A0A301F98869B44724FEF5A8F` |
| Current WP-10 evaluation DB | `scratch/phase8_5_wp10_stage2/eval-20260829-01/mnemo.db`; observed only by path/metadata because another process held the file; it was not opened or hashed |
| Repository state | Already substantially dirty before this audit. All pre-existing changes are treated as user-owned and were not altered. |

The historical hash supplied for the frozen DB differs from the hash observed at audit start. This audit did not cause or investigate that pre-existing difference; it treats the start-of-audit bytes as the protected baseline and does not claim the older digest remains current.

## 2. Current architecture inventory

### 2.1 Classification key

- **A — already language-agnostic**
- **B — EN/HI/MR-specific and must be generalized**
- **C — EN/HI/MR-specific and intentionally retained as a regression/provider plugin**
- **D — model/provider-specific**
- **E — governance/evaluation-specific**
- **F — unresolved and requiring an approved design decision**

### 2.2 Component inventory

| Classification | File / component | Actual behavior | V2 disposition |
|---|---|---|---|
| A | `mnemo-core/mnemo/models/multilingual.py`: `LanguageCode`, `ScriptCode` | Normalizes extensible BCP-47-like tags and ISO-15924 codes; does not enumerate EN/HI/MR | Reuse; strengthen validation tests rather than replace |
| A | Same file: `LanguageEvidenceReferenceV2` | Path-free notebook/source/document/version reference; typed canonical/OCR/Vision/language-derivation identity; validates provenance combinations | Keep stable; wrap or version for representation derivations rather than duplicating it in JSON schemas |
| B | Same file: `LanguageObservation` | Exactly one language and one script plus mixed booleans; cannot preserve multiple hypotheses or constituent scripts | Add a versioned observation/hypothesis contract |
| B | Same file: `LanguageProviderProfile`, `LanguageCapabilityState` | Static language/script tuples and a flat state unrelated to per-operation ADR-0074 evidence | Adapt into operation-scoped runtime-derived facts; retain old type for compatibility |
| B | Same file: `MultilingualCandidate`, `MultilingualRerankScoreV2` | Candidate lacks scored-text/truncation audit; score contains model/revision/preprocessing only | Add typed V3 candidate and input/output audit |
| A | `mnemo-core/mnemo/interfaces/multilingual.py` | Versioned detector, transformation, embedding, reranker, evidence-catalog, and store protocols | Extend additively; do not break V1/V2 protocols |
| B/C | `mnemo-core/mnemo/retrieval/multilingual.py` | Contains generic planner/service and fixed EN/HI/MR detector, Devanagari transliteration, two-script detector, fixed transliteration path | Retain conservative detector/transliterator as named regression plugins; generalize orchestration around registries |
| D | `mnemo-core/mnemo/retrieval/multilingual_providers.py` | Exact BGE-M3/BGE reranker adapters, offline local load, CPU device, 1024-d normalized cosine space, bounded batches | Retain provider adapters; accept typed candidate/audit and separate provider claims from runtime support |
| A/B | `mnemo-core/mnemo/retrieval/multilingual_advanced.py` | Shared advanced-source adapter, but constructor freezes `target_languages`; actor is recovered from server-owned security identity | Resolve targets from operation-scoped runtime view; keep server-owned actor binding |
| B | `mnemo-core/mnemo/phase85/multilingual.py` | Four hard-coded EN/HI/MR generation specs; transliterates only detected HI/MR Devanagari; embedding builder depends on caller-supplied language | Create generic generation inputs/coverage while retaining V1 plan for regression |
| A/B | `mnemo-core/mnemo/storage/multilingual.py` | Generic text fields and immutable payload hashes; single-language observation and one embedding per source/generation/vector-space | Add V2 observation/representation storage and remove the one-hypothesis uniqueness limitation in V2 tables |
| A/B | `mnemo-core/mnemo/storage/projection_generations.py` | Generic complete-only generation lifecycle; language-text projection contains language derivations only; multilingual-vector projection is a manifest over embedding rows | Reuse coordinator/aliases; add V2 coverage dimensions and canonical/derived representation policy |
| B | `mnemo-core/mnemo/storage/multimodal_search.py` | Projected multilingual FTS source gates on active `language_text`, but ignores source/document/version scope filters | Must be fixed/versioned before any V2 exposure |
| A | `mnemo-core/mnemo/phase85/projections.py` | Deterministic spec identity, source binding, checksum/coverage, complete-only READY, atomic promotion | Reuse unchanged in semantics |
| A/B | `mnemo-core/mnemo/phase85/runtime.py`, `phase85/models.py` | One lifecycle authority with correct implications, but aggregate capability granularity | Add a derived view; do not add an independent state machine |
| B | `mnemo-server/mnemo_server/services/capabilities_v2.py` | Runtime-derived aggregate state but static multilingual languages `("en", "hi", "mr")` | Project operation/language/script/representation facts from runtime/generations |
| B | `mnemo-server/mnemo_server/mcp/contracts.py` | Public `search_evidence` JSON schema omits `multilingual_text` although the Pydantic enum accepts it | Version-compatible schema correction is mandatory |
| A | `mnemo-server/mnemo_server/services/retrieval_v2.py` | Shared HTTP/MCP application boundary, server-owned principal, bounded requests/completeness | Preserve and route V2 through it |
| E | `scratch/run_wp10_stage2_operationalization.py`, `scratch/run_wp10_final_remediation_pipeline.py` | Direct provider calls, permissive authorizer, title-only reranker payload, document-title qrels | Historical diagnostic only; exclude from quality/certification evidence |
| E | `evaluation/phase8_5_wp16/behavioral_manifest.json` | Blind-client tool-routing cases; several multilingual prompts are generic or corpus-mismatched for semantic-quality scoring | Preserve historical manifest; create corrected versioned V2 behavioral/evaluation pack |
| E | `scripts/phase8_5_11_benchmark_models.py` | 18-query model-selection script with document aggregation and independent candidate rendering | Retain as model-selection history; do not use for V2 certification |

## 3. Exact hard-coded language, script, and document assumptions

### 3.1 Production assumptions that must be generalized

1. `mnemo-core/mnemo/retrieval/multilingual.py:117-201` freezes detector identity and marker dictionaries to EN/HI/MR.
2. `detect_script` in that module recognizes only Devanagari and Latin; mixed or unknown collapses to `Zyyy`, losing constituent script hypotheses.
3. `UnicodeLanguageDetector` maps markerless Latin text to English with confidence 0.55. This is an implicit `Latn => en` claim and is unsuitable for the V2 generic path.
4. `MultilingualRetrievalPlanner` treats native sparse retrieval as `SUPPORTED` for every target, derives dense availability from static profile tuples, and chooses Devanagari transliteration for `Deva` or `Zyyy`. The latter lets common/unknown script select a Devanagari transform.
5. `mnemo-core/mnemo/phase85/multilingual.py:78-124` freezes detector, language derivation, language-text, and vector generation profiles around `unicode-en-hi-mr-conservative-v1`.
6. The builder in the same file transliterates only observations whose language is HI/MR and script is Devanagari. This is valid as a retained plugin, not as a universal derivation rule.
7. `config/model_profiles/phase8_5_profiles.toml` supplies static `en/hi/mr` and `Latn/Deva` claims for BGE-M3 and the reranker. These are configured claims, not discovered model metadata and not operational/certification evidence.
8. `mnemo-server/mnemo_server/services/capabilities_v2.py:139-147` advertises EN/HI/MR from static public semantics when the aggregate capability is active.
9. `mnemo-core/mnemo/retrieval/multilingual_advanced.py` requires a fixed non-empty tuple of target languages at composition time.

### 3.2 EN/HI/MR assumptions that should remain

- `ConservativeENHIMRDetector` and its frozen digest remain regression plugins for the existing baseline.
- Deterministic Devanagari transliteration remains a governed representation plugin with its existing regression tests; it must no longer be selected by a global language branch.
- The exact EN/HI/MR Decision-7 cohort remains immutable historical evidence, but not V2 certification evidence.
- Model profile snapshots used by the frozen baseline remain unchanged. V2 receives a new profile/generation identity.

### 3.3 Document-specific assumptions

- Production modules contain no Ramayana/manuscript filename branch in the multilingual provider or retrieval service.
- Document-specific assumptions exist in evaluation scripts and manifests. `scripts/phase8_5_11_benchmark_models.py` maps `manuscript.pdf` to MR. The two scratch WP-10 runners hard-code document titles as qrels. WP-16 P85-B-17 asks for “Marathi material about the Ramayana comparison,” which is not established by the manifest itself as a grounded relevant-evidence judgment.
- No future transformation may dispatch on filename, title, path, Ramayana, manuscript, Hindi, or Marathi. Dispatch must use an authorized representation observation and a governed transformation profile.

## 4. Language, script, and representation findings

The current model partially separates language and script at the type level but couples them operationally.

| Requirement | Current repository reality | Target |
|---|---|---|
| Arbitrary language tag | `LanguageCode` is generic | Preserve |
| Arbitrary script | `ScriptCode` is generic | Preserve |
| Multiple language hypotheses | Not representable in `LanguageObservation` | Versioned tuple of hypotheses with independent confidence/source |
| Multiple script hypotheses | Not representable; mixed becomes `Zyyy` | Versioned script observations retaining constituent scripts and ranges |
| Ambiguous/unknown | `und` and `Zyyy/Zzzz` exist | Preserve fail-closed semantics |
| Detection scope | Enum supports document/page/section/chunk/OCR/asset/query | Preserve; detector protocol must accept explicit scope/locator rather than infer only query/chunk |
| Detector provenance | ID, revision, config digest, input hash, calibrated flag exist | Preserve |
| Representation identity | No first-class persisted representation observation | Add V1 representation observation/derivation contracts |
| Legacy-font encoding | No detector/transform registry | Add governed plugin mechanism; no source rewrite |
| Mixed-language evidence | Boolean only | Add hypotheses/regions without forcing one language |

Authoritative parser/OCR/Vision metadata should remain higher precedence than heuristic detection only when its provenance and semantics are explicit. The current generation script can assign confidence 1.0 and `calibrated=true` to caller-supplied metadata; V2 must distinguish authoritative/adjudicated metadata from merely parser-supplied hints and must not automatically calibrate the latter.

## 5. Representation and legacy-font bottlenecks

There is no production `RepresentationDetectorV1`, `RepresentationTransformerV1`, or `TransformationRegistryV1`. Existing `LanguageDerivation` admits translation/transliteration only, and the language-text projection consumes those derivations. OCR and Vision are separately modeled derivations; legacy-font/PDF-encoding anomalies are not.

The proposed representation layer is necessary, but `REPRESENTATION_TRANSFORMATION_MODEL.proposed.json` is not implementation-ready:

1. It embeds a second, incompatible definition of `LanguageEvidenceReferenceV2`: `source_id` and `chunk_id` are absent, every `evidence_id` is forced to UUID even though canonical chunk IDs are strings, and it introduces `ocr_result`/`representation_derivation` kinds that the current enum does not accept.
2. Top-level source/output hashes, representation observation, generation ID, and authorization-context digest are optional despite being needed for immutable lineage.
3. `provenance` is an unrestricted object, so complete source/transform lineage is not machine-enforceable.
4. Language and script observations are absent, even though the proposal requires them to remain independent from representation.
5. Conditional rules for canonical chunk, OCR occurrence/region, Vision derivation, language derivation, and representation derivation are not encoded.

**Required contract decision:** retain `LanguageEvidenceReferenceV2` unchanged and define a versioned `TextRepresentationReferenceV1` that wraps it, or define a fully versioned `LanguageEvidenceReferenceV3`. Do not maintain duplicated source-reference schemas. The selected contract must require deterministic observation/transformation IDs, source/output hashes, source generation, exact provider/profile/configuration, authorization-scope digest, language/script observation references, and typed lineage.

## 6. Reranker forensic audit

### 6.1 Actual call paths

1. V1 canonical retrieval uses `mnemo-core/mnemo/retrieval/reranker.py`, rendering `Document title: ...\n\n{chunk.text}`. It includes semantic chunk text and must remain unchanged.
2. Shared advanced retrieval uses `CanonicalAdvancedReranker` in `retrieval/advanced_sources.py`. It reranks only if every candidate has a canonical `Chunk`; if any candidate is derived/multilingual, it returns the fused order unchanged.
3. The internal multilingual service passes `MultilingualCandidate` directly to `BGEMultilingualReranker`, whose `score` path extracts `candidate.content`. It rejects `None` indirectly but does not reject blank or title-only substitutions and produces no input audit.
4. The two WP-10 scratch evaluators bypass both service and provider public interfaces. They invoke `reranker._runtime.predict` with `preprocess_bge_m3_document(f"title: {document_title}")`. This is the confirmed title-only defect.
5. `scripts/phase8_5_11_benchmark_models.py` and `phase8_5_11_final_qa.py` build independent document aggregates containing a title and truncated body. They are not title-only, but still diverge from production candidate construction.

### 6.2 V3 contract gaps

`RERANKER_CANDIDATE_CONTRACT.proposed.json` captures the right intent but cannot yet be implemented safely:

- It repeats the incompatible UUID-only evidence reference.
- It does not require source-generation identity or encode occurrence/derivation conditions.
- `provenance` is unstructured.
- The audit omits tokenizer identity/revision, provider/model/revision/configuration digest, query text/preprocessed hashes, query token count, pair allocation, retained range, and whether title metadata was included in the rendered input.
- It records token counts but does not freeze the tokenizer that defines those counts.
- It does not specify the exact deterministic pair truncation algorithm needed to enforce the 256-token policy outside the provider’s opaque internal truncation.
- The title-only prohibition is prose (`x-mnemo-invariants`), not enforceable through typed origin/provenance validation.

**Required target:** one `RerankerCandidateBuilderV1` must resolve already-authorized semantic evidence, validate nonblank actual text and lineage, apply the frozen query/document preprocessing and tokenizer-aware pair policy, construct a typed V3 candidate plus audit, and be the only input accepted by the multilingual reranker. Production, Decision-7/V2 evaluation, benchmarks, and behavioral verification must call this shared builder/application path. A direct `_runtime.predict` call is an evaluation harness error.

## 7. Provider capability audit

### 7.1 Configured providers

| Operation | Configured identity | Actual constraints in code |
|---|---|---|
| Dense embedding | `BAAI/bge-m3` revision `5617a9f61b028005a4858fdac845db406aefb181` | 1024 dimensions, cosine, L2 normalization, batch <=32, max context 8192, NFKC+whitespace preprocessing, no prefix, offline local snapshot, CPU |
| Reranking | `BAAI/bge-reranker-v2-m3` revision `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` | batch <=16, candidates <=200, runtime `max_length=256`, NFKC+whitespace, stable candidate-ID tie break, offline local snapshot, CPU |

Query and document BGE preprocessing have different governed identities but currently perform the same normalization. Model revision and profile fingerprint enter generation/vector-space identity. Vector dimensions, metric, normalization, preprocessing, model and revision are validated. V1, CLIP, and BGE vector spaces are separate.

### 7.2 Capability claim findings

- The repository profile advertises only EN/HI/MR and Latn/Deva. There is no repository-grounded exhaustive BGE-M3 language list.
- Claims are static profile metadata, not runtime-derived model introspection.
- Provider readiness verifies local snapshot structure and a probe, but the revision-named directory is not a content checksum. That is sufficient for the current frozen contract, not for a broader provider-claim registry unless governance approves the trust model.
- The adapters hard-code CPU. This is deterministic but should become a governed execution-profile field, not a language capability.
- Embedding runtime truncation is not surfaced in document provenance/audit.
- The reranker component reports max context 8192 in the model profile while runtime pair length is 256. Both may be valid at different layers, but the contract must name them separately (`model_context_ceiling` versus `reranker_pair_max_tokens`).

The V2 registry must consume a governed provider claim artifact and intersect it with implementation, configured detector/representation support, complete active generation coverage, transport exposure, and evaluation/governance evidence. No language becomes operational because a model vendor claims support.

## 8. Retrieval, generation, and indexing findings

### 8.1 Reusable foundations

- `SQLiteMultilingualDenseSource` obtains an authorized source set before listing/scoring embeddings, enforces 10,000 eligible and 1,000 returned limits, validates source provenance, requires exact vector-space equality, and uses stable ordering.
- `MultilingualRetrievalService` uses deterministic RRF and reauthorizes selected candidates.
- `ProjectionGenerationSpec`, `DerivedProjectionCoordinator`, and SQLite promotion/rollback enforce deterministic identities, registered source generations, complete coverage, checksum/item-count equality, READY-only activation, and atomic aliases.

### 8.2 Blocking defects and gaps

1. `retrieve_multilingual_evidence` in `storage/multimodal_search.py` filters only `notebook_id`; it ignores requested `source_ids`, `document_ids`, `version_ids`, and positional scope. This can return evidence outside an explicitly narrower authorized/requested scope. V2 must not expose this adapter until scope predicates and tests are complete.
2. The MCP JSON schema omits `multilingual_text`, so a native client cannot request the representation even though Pydantic and internal enums accept it.
3. Engine composition adds a multilingual advanced source when any complete active `language_text` generation exists. It does not require compatible `multilingual_vector`, provider readiness, per-language coverage, representation availability, or the custom dense source’s complete dependency set.
4. `active_multilingual_generation_identity` represents only active language-text generations. There is no combined identity for text, vector, embedding model, representation transformations, and coverage.
5. Language-text projection contains only `language_derivations`; canonical Unicode semantic text is not projected directly. V2 must explicitly define which immutable canonical and derived representations enter sparse and dense projections.
6. Multilingual-vector generation contains no vector projection table; it validates/checksums embeddings by generation. That design can remain, but V2 needs a coverage manifest keyed by vector space, representation, language/script observations, and source kind.
7. The embedding uniqueness key allows one row per source/generation/vector-space, which cannot represent multiple independently governed hypotheses/representations for the same evidence without a V2 source-representation identity.
8. `get_authorized_multilingual_embedding` accepts notebook and embedding ID but no actor/scope; the safe dense path does not use it for enumeration, yet the interface is unsafe as a general authorized API and must not be exposed as such.
9. `CanonicalAdvancedReranker` skips reranking whenever one noncanonical representation appears. V2 needs explicit mixed-representation candidate building/reranking policy rather than silent bypass.

## 9. Runtime, capability, HTTP, and MCP findings

ADR-0074 mechanics in `phase85/models.py` and `runtime.py` are the correct single runtime authority. They correctly separate profile configuration/local availability/loadability/initialization from capability configured/buildable/ready/active/exposed/behavioral-security verification/certification.

The proposed `LanguageCapabilityRegistryV1` must therefore be a pure deterministic projection over:

1. governed provider claims;
2. implemented operation adapters;
3. active profile/configuration;
4. provider readiness;
5. compatible complete generation coverage;
6. active aliases;
7. HTTP/MCP exposure;
8. exact evaluation and governance evidence.

It must not own providers, generations, lifecycle transitions, authorization, or a second registry database.

`LANGUAGE_CAPABILITY_MODEL.proposed.json` correctly separates provider support, implementation, runtime lifecycle, assurance, availability, and effective state, but needs the following before coding:

- a normative projection algorithm and precedence table for `effective_state`;
- explicit mapping of independent `behaviorally_verified` and `security_verified` evidence (the proposed assurance enum currently collapses these);
- conditional required fields for profile/generation/transport/evaluation states;
- evidence references that cannot be empty when a positive state is claimed;
- normalized BCP-47 validation rather than `minLength: 2`;
- direction applicability rules by operation;
- per-generation coverage schema, not only booleans;
- deterministic record and document snapshot identity.

HTTP and MCP should continue to share `CapabilityDiscoveryService` and `CapabilityDocument`. A versioned additive capability-detail section is safer than replacing `mnemo.capabilities/1`. Existing tool names remain unchanged. `search_evidence` must expose `multilingual_text` consistently in Pydantic, OpenAPI, MCP JSON Schema, descriptions, capability guidance, structured content, and canonical JSON fallback.

## 10. Evaluation forensics

### 10.1 Confirmed defects

| Defect | Repository evidence | Consequence |
|---|---|---|
| Title-only reranker input | Both WP-10 scratch runners build `preprocess_bge_m3_document(f"title: {c[2]}")` and call private `reranker._runtime.predict` | Reranker metrics are invalid and cannot certify production behavior |
| Direct provider bypass | Same runners call embedding provider directly and private reranker runtime rather than shared application/candidate-builder path | No evaluator/runtime parity |
| Permissive authorization | Both define `_PermissiveLanguageAuthorizer` returning true | Cannot establish production authorization behavior |
| Document-title qrels | A candidate is relevant if `expected_document` is contained in its title | Does not establish relevant chunk/region/derivation, version, occurrence, or semantic grounding |
| Generic queries | WP-16 P85-B-18 and P85-B-19 ask only for “related English evidence” with no grounded subject | Valid at most as routing tests; invalid for semantic retrieval metrics |
| Corpus misdiagnosis | Historical conclusions treated an MR miss as corpus absence even though `manuscript.pdf` exists and is targeted by the scripts | Failure attribution was not evidence-gated |
| Representation blind spot | Legacy-font Hindi is scored as retrieval/language failure without a governed representation census/transform stage | Conflates source representation with language/model support |

The scratch outputs remain historical diagnostics. They must not be deleted or silently rewritten, but their retrieval/reranker quality claims must be marked invalid in the future V2 evidence chain.

### 10.2 Failure taxonomy readiness

The proposed taxonomy is directionally correct, and its rule that `CORPUS_ABSENT` requires both immutable-source and authorized-evidence census is essential. Most codes cannot currently be generated from retained stage evidence. Before implementation, add or freeze codes for:

- `PROVIDER_UNAVAILABLE` / `PROVIDER_IDENTITY_MISMATCH`;
- `GENERATION_MISSING`, `GENERATION_INCOMPLETE`, `GENERATION_STALE`;
- `VECTOR_SPACE_MISMATCH`;
- `SPARSE_RETRIEVAL_FAILED`;
- `FUSION_FAILED`;
- `TRANSPORT_FAILED` (distinct from evaluator harness failure);
- `REPRESENTATION_PRESENT_WRONG_TYPE` or equivalent adjudicated mismatch;
- `CAPABILITY_ADVERTISEMENT_INCONSISTENT`.

`preceding_stage_status` must be a typed array/map of stage verdicts with evidence digests, not an unrestricted object. Each failure code needs machine-checkable prerequisites. `AUTHORIZATION_FILTERED` must remain a safe outcome without exposing filtered identities.

### 10.3 Scalable evaluation

Do not construct a complete L×L matrix. Use:

- per-language same-language strata for every evaluated language;
- directed cross-language edges selected by script family, provider claim, deployment need, resource level, and risk;
- hub-language edges for broad cross-language behavior;
- same-script/different-language ambiguity cohorts;
- cross-script and transliteration cohorts;
- representation cohorts for Unicode, legacy font, OCR, Vision, mixed and unknown;
- negative/no-answer, authorization, provenance, and lifecycle cohorts;
- sentinel EN/HI/MR regressions retained from V1, but rebuilt with evidence-level qrels and shared production paths.

Engineering validation, language capability evaluation, cross-language evaluation, WP-16 blind-client behavior, and WP-17/final certification remain separate evidence layers.

## 11. Authorization and provenance audit

### Preserved strengths

- `LanguageEvidenceReferenceV2` is path-free and carries notebook/source/document/version identity.
- Language observation/derivation builders authorize before detection/transformation.
- Dense multilingual retrieval asks the catalog for authorized sources before SQLite enumeration/scoring and revalidates resolved provenance.
- Shared HTTP/MCP retrieval binds a server-owned actor identity.
- CursorCodecV2 scope/security binding is independent and requires no change.

### Required corrections

1. Fix the projected multilingual FTS scope bypass before V2 exposure.
2. Require authorization before representation detection/transform, embedding enumeration, candidate building, and scoring—not only before final delivery.
3. Derived representation rows must inherit exact notebook/source/document/version and occurrence/derivation lineage; they cannot widen scope.
4. Every candidate builder must resolve text from the authorized evidence record, never from caller-supplied title/text alone.
5. Final results must revalidate candidate identity/provenance after fusion and reranking.
6. Capability discovery remains metadata and must not disclose notebook IDs, paths, storage URIs, source text, model roots, secrets, or filtered identities.
7. OCR/Vision/representation transformations must stay labeled derived; no transform may convert them into canonical authority.

## 12. Proposal consistency audit

| Proposal artifact | Consistent strengths | Blocking or major inconsistency |
|---|---|---|
| `FULL_MULTILINGUAL_ARCHITECTURE_FORENSIC_AUDIT.md` | Corrects MR, reranker, query-grounding, and representation diagnoses | Does not freeze the exact observation, source-reference, candidate-rendering, or capability projection schemas |
| `FULL_MULTILINGUAL_IMPLEMENTATION_PLAN.md` | Good staged, additive, side-by-side sequence | Stage 1 starts before P0 contract mismatches are resolved; missing explicit scoped FTS and MCP schema fixes |
| `MIGRATION_AND_INDEX_LIFECYCLE_PLAN.md` | Protects baseline and uses side-by-side generations/rollback | Combined V2 readiness identity and precise disposable-state allowlist are not yet machine-readable |
| `LANGUAGE_CAPABILITY_MODEL.proposed.json` | Correct orthogonal state concept | Missing behavioral/security split, conditional evidence, projection algorithm, strict language validation |
| `FAILURE_TAXONOMY.proposed.json` | Correctly forbids inferring corpus absence from a miss | Missing provider/generation/vector/fusion/transport codes and typed stage evidence |
| `RERANKER_CANDIDATE_CONTRACT.proposed.json` | Correctly demands semantic text and audit | Incompatible evidence ID, untyped provenance, incomplete tokenizer/pair/render/provider audit |
| `REPRESENTATION_TRANSFORMATION_MODEL.proposed.json` | Correct additive immutable transformation model | Duplicates/incompatibly narrows source reference; critical lineage fields optional; no language/script links |
| `MULTILINGUAL_EVALUATION_ARCHITECTURE.proposed.md` | Correct layered gates and non-L×L direction | Needs executable stage record schema, qrel binding, production-path parity, and historical-invalidity policy |
| `IMPLEMENTATION_TRACEABILITY_MATRIX.md` | Useful defect-to-contract mapping | Omits existing projected FTS scope bypass, MCP representation mismatch, and combined activation gate |
| `FILE_IMPACT_MATRIX.md` | Correctly protects V1 and identifies core seams | Omits `storage/multimodal_search.py`, `mcp/contracts.py`, retrieval transport schema, and several security tests from mandatory changes |

The proposals refer to conceptual modules intentionally not present. That is acceptable only after their exact ownership is frozen. No proposal should require changing CursorCodecV2, canonical `Chunk.text`, V1 embedding/reranker semantics, existing OCR/Vision/CLIP rows, or current MCP tool names.

## 13. Prioritized issue register

### 13.1 P0 blockers (8)

| ID | Current behavior / root cause | Target behavior | Exact module/file | Required tests | Rollback |
|---|---|---|---|---|---|
| P0-01 | Proposal schemas duplicate and contradict `LanguageEvidenceReferenceV2` (UUID-only evidence IDs, missing source/chunk identity, different kinds) | One canonical versioned evidence-reference contract; representation wrapper or V3 with conditional lineage | Proposal JSONs; future `models/multilingual.py` or new representation model | Schema/model round-trip for canonical/OCR/Vision/language/representation evidence; V2 compatibility | Remove V3/wrapper; V2 untouched |
| P0-02 | Representation proposal leaves hashes/observation/generation/auth lineage optional and provenance untyped | Strict immutable representation observation/transformation contract with independent language/script refs | `REPRESENTATION_TRANSFORMATION_MODEL.proposed.json`; future representation models/interfaces | Deterministic IDs, content hashes, conditional lineage, canonical immutability, auth inheritance, idempotency | Disable V2 transforms; preserve rows/generation for diagnosis |
| P0-03 | Reranker V3 lacks exact tokenizer/pair/render/provider audit and enforceable title-only rejection | Freeze one typed builder and deterministic 256-token rendering/truncation contract used everywhere | `RERANKER_CANDIDATE_CONTRACT.proposed.json`; future `retrieval/reranker_candidates.py`; `multilingual_providers.py` | Semantic text, blank/title-only rejection, token/hash audit, identity/provenance preservation, production/eval parity | Disable V3 rerank; fall back only to explicitly governed non-reranked partial result, never V1 reranker |
| P0-04 | WP-10 evaluators use private provider calls, title-only payloads, permissive auth | Evaluator calls the same application/provider/candidate builder path and retains typed stage records/raw rankings | Future V2 evaluator; historical scratch scripts remain untouched | Direct-provider-call detector, builder parity, authorization, raw input hashes, deterministic replay | Invalidate evaluation run; no production rollback needed |
| P0-05 | Document-title qrels and ungrounded prompts permit false quality conclusions; failure codes lack executable predicates | Evidence-level adjudicated qrels, query grounding gate, immutable census, typed stage-failure evidence | Evaluation manifest/qrels/failure schemas and V2 evaluator | Qrel identity/version/occurrence, ungrounded exclusion, corpus-present miss classification, metric fail-closed | Reject manifest/run; retain artifacts as invalid evidence |
| P0-06 | Projected multilingual FTS ignores requested source/document/version scope | Apply authorized scope predicates before enumeration and preserve exact provenance | `mnemo-core/mnemo/storage/multimodal_search.py`; store interface/tests | Cross-notebook, source, document, version, partition and forged-scope denial; non-enumeration | Disable projected multilingual source/alias |
| P0-07 | MCP schema omits `multilingual_text`; capability and internal Pydantic types can claim it | One shared representation enum reflected identically in HTTP, MCP, structured content and fallback | `mnemo-server/.../mcp/contracts.py`, `schemas/retrieval_v2.py`, capabilities and contract tests | JSON Schema accepts active representation; rejects disabled; HTTP/MCP/stdio/SSE parity | Remove V2 representation advertisement, retain old tools |
| P0-08 | Engine/capability activation can gate on language-text alone; no combined compatible dependency identity | V2 readiness requires exact provider readiness, representation transforms, embeddings, sparse/vector generations, coverage, vector space and atomic aliases | `engine.py`, `phase85/runtime.py`, capability adapter, storage generation identity | Partial/stale/mismatched generation rejection, atomic activation/rollback, per-operation truthful exposure | Repoint aliases to frozen V1; disable V2 capability |

### 13.2 P1 major items (14)

| ID | Required resolution |
|---|---|
| P1-01 | Version language observations to represent multiple hypotheses, mixed regions and constituent scripts with detector provenance. |
| P1-02 | Retain EN/HI/MR detector and Devanagari transliterator as plugins; remove them from global planner/generation branching. |
| P1-03 | Freeze a governed provider-claim artifact and its digest; do not treat static model profile arrays as Mnemo readiness. |
| P1-04 | Distinguish model snapshot revision naming from artifact integrity and freeze the approved local-artifact verification policy. |
| P1-05 | Add representation/script/preprocessing/truncation lineage to embedding inputs and persisted V2 embedding records. |
| P1-06 | Replace the V1 embedding uniqueness assumption with a V2 source-representation identity that supports multiple hypotheses/representations without vector mixing. |
| P1-07 | Remove or rename the actor-less `get_authorized_multilingual_embedding` seam; require explicit authorized scope for every public read. |
| P1-08 | Freeze which canonical and derived representations enter V2 sparse and dense generations; current language-text contains derivations only. |
| P1-09 | Add coverage manifests by operation/language/script/representation/vector-space/source kind while retaining existing coordinator authority. |
| P1-10 | Compose V2 providers/services through the standard `KnowledgeEngine` composition path, not optional test-only injection or BUILDABLE-only helpers. |
| P1-11 | Define mixed-representation reranking behavior; current advanced reranker silently skips noncanonical candidates. |
| P1-12 | Make capability projection operation-scoped and include provider/implementation/runtime/assurance/availability without creating a second authority. |
| P1-13 | Expand and machine-constrain the failure taxonomy with typed preceding-stage evidence and sanitized stable reason codes. |
| P1-14 | Version the evaluation/behavioral manifests: preserve historical WP-16, add grounded evidence-level V2 cases, and stratify rather than exhaust L×L. |

### 13.3 P2 moderate issues (7)

| ID | Required resolution |
|---|---|
| P2-01 | Stop using flat `SUPPORTED` wording as though it meant certified; one error currently says “not certified” based only on a profile state. |
| P2-02 | Correct observation scope inference for Vision and language derivations; the current builder defaults both to asset scope. |
| P2-03 | Do not assign `calibrated=true` merely because parser metadata was supplied; record authority class separately. |
| P2-04 | Name BGE model context 8192 and reranker pair limit 256 as separate governed bounds. |
| P2-05 | Decide whether language/script coverage belongs in vector-space identity or generation coverage; current inclusion causes a new space identity when coverage expands. |
| P2-06 | Standardize “V1 baseline,” “WP-10 Stage 2,” and “Full Multilingual V2” terminology to avoid migration/purge ambiguity. |
| P2-07 | Add sanitized stage latency/count/failure diagnostics without text, paths, secrets, or cross-scope identifiers. |

## 14. Test-gap matrix

| Area | Missing mandatory tests |
|---|---|
| Language | Arbitrary valid BCP-47; invalid tag; unknown; multiple hypotheses; mixed regions; metadata precedence; detector identity/config digest |
| Script | Arbitrary ISO-15924; unknown/common; mixed scripts retaining constituents; same-script different-language ambiguity; no script-to-language inference |
| Representation | Unicode, legacy-font, PDF anomaly, OCR, Vision, transliteration, normalization, unknown; language/script independence |
| Transformation | Registry selection without filename/language hacks; deterministic IDs/hashes; source/output lineage; authorization before transform; restart/idempotency; interrupted generation; canonical immutability |
| Embedding | Query/document preprocessing identity; offline exact revision; dimension/norm/metric; token truncation audit; source-representation identity; vector-space isolation; multi-hypothesis rows |
| Reranker | Actual semantic text; blank/title-only rejection; tokenizer/pair truncation; rendered/retained hashes; provider/model/config identity; stable ties; candidate/provenance preservation; no direct-provider bypass |
| Retrieval | Same/cross language; cross script; transformed representation; OCR/Vision; mixed language/script; sparse+dense fusion; deterministic RRF; unavailable/degraded semantics; exact scope filtering |
| Generation | Dependency-bound identity; representation/profile/vector coverage; partial/stale rejection; concurrent promotion; rollback; no alias on incomplete coverage |
| Capability | Provider claim does not imply ready; per-operation language state; unsupported/unverified fail closed; runtime consistency; no secret/path/source leakage |
| HTTP/MCP | `multilingual_text` schema; shared application path; structured/JSON equality; stdio/SSE parity; disabled capability not callable; unchanged tool names |
| Evaluation | Immutable corpus census; grounded query; evidence qrels; stage-specific failures; raw rankings; metric oracle; production/eval candidate-builder parity; historical invalid run exclusion |
| Security | Notebook/source/document/version/occurrence/derivation isolation; authorization before enumerate/transform/embed/score; final provenance revalidation; cursor scope unchanged |
| Regression | EN/HI/MR baseline; V1 retrieval/reranker; canonical `Chunk.text`; OCR/Vision/CLIP identities and outputs; multimodal benchmarks read-only; CursorCodecV2 |

## 15. File-by-file implementation order

The following order is contingent on P0 proposal amendments and approval.

| Order | File(s) | Change | Dependencies |
|---:|---|---|---|
| 1 | Proposal contracts only | Resolve P0-01/02/03/05/07/08 and traceability/file matrix | Human/governance approval |
| 2 | `mnemo-core/mnemo/models/multilingual.py`; new `models/text_representations.py` | Add versioned hypotheses, representation observations/derivations, typed candidate/audit without breaking V1/V2 | Frozen schemas |
| 3 | `mnemo-core/mnemo/interfaces/multilingual.py`; new `interfaces/text_representations.py` | Add detector/script/representation/transform/candidate-builder/capability-view protocols | Models |
| 4 | New `mnemo-core/mnemo/retrieval/reranker_candidates.py` | Central authorized semantic candidate builder and deterministic audit | Models/interfaces/tokenizer policy |
| 5 | `retrieval/multilingual_providers.py` | Accept typed V3 candidates; expose provider claims; audit truncation; retain exact BGE identities | Candidate builder |
| 6 | `retrieval/multilingual.py`; new `retrieval/text_representations.py` | Registry-driven detector/script/transform planning; keep old plugins | Interfaces/provider claims |
| 7 | `storage/multilingual.py`; additive SQLite migration; `projection_generations.py` | V2 observations/representation derivations/embeddings/coverage; no V1 table rewrite | Frozen persistence models |
| 8 | `storage/multimodal_search.py`, multilingual store interfaces | Correct exact scope filtering and add V2 sources | Security tests first |
| 9 | `phase85/multilingual.py`, `phase85/runtime.py`, `phase85/models.py`; new capability projection module | Generic generation specs and operation-scoped derived capability records | Storage/providers/generations |
| 10 | `retrieval/multilingual_advanced.py`, `advanced_sources.py`, `advanced.py`, `engine.py` | Compose V2 retrieval/fusion/reranking and combined activation gate | Runtime/storage/provider readiness |
| 11 | `mnemo-server/.../schemas/retrieval_v2.py`, `mcp/contracts.py`, capability schemas/service | Additive transport/capability exposure; shared enum/document | Active runtime semantics |
| 12 | New versioned V2 evaluation module and manifests; tests | Shared application/candidate-builder path, typed stages/qrels/raw rankings | Production path complete |
| 13 | Isolated V2 generation/index runbook | Build only on disposable copy; validate coverage; no activation until gates pass | Regression/security/static validation |

## 16. Dependency graph

```text
approved source-reference + observation + representation schemas
        |
        +--> detector/script providers ----+
        |                                  |
authorized immutable evidence --> representation registry/transformations
        |                                  |
        +-----------------------+----------+
                                v
                    V2 source-representation identities
                                |
                  +-------------+-------------+
                  v                           v
            sparse generation          BGE-M3 embeddings
                  |                           |
                  +-------------+-------------+
                                v
                 authorization-before-enumeration retrieval
                                |
                     deterministic fusion / RRF
                                |
              authorized RerankerCandidateBuilderV1 + audit
                                |
                      BGE multilingual reranker
                                |
                provenance revalidation + completeness
                                |
              Phase85RuntimeV1-derived capability projection
                                |
                     shared HTTP / MCP application path
                                |
                 V2 evaluator using the identical path
```

Activation depends on the complete compatible branch, not merely on the existence of one language-text alias.

## 17. Files that MUST NOT change

- `goldenDataset/Phase 8.5 Evaluation Corpus/**`, including every byte/name of `manuscript.pdf` and the Ramayana comparison PDF.
- `scratch/phase8_5_wp16/eval-20260828-01/mnemo.db`, its WAL/SHM if present, and `multimodal_freeze_manifest.json`.
- The currently running/current WP-10 evaluation DB and its WAL/SHM.
- Retained V1/WP-10 evaluation outputs and transcripts; annotate through new evidence, never rewrite history.
- Canonical `Chunk.text` semantics and stored canonical source content.
- Existing OCR, Vision, and CLIP derivation bytes, generation identities, active aliases, and vector spaces.
- Existing V1 text embedding/reranker vector space and behavior.
- `mnemo-core/mnemo/cursors.py` / CursorCodecV2 semantics.
- Central authorization meaning, scope boundaries, or principal derivation.
- Existing MCP tool names and canonical structured-content/JSON fallback equivalence.
- Frozen model artifacts and revisions.

Some composition files such as `engine.py` and `storage/sqlite.py` may receive additive V2 code, but the protected semantics and existing rows listed above must remain unchanged.

## 18. Files that MAY change after approval

### Mandatory production seams

- `mnemo-core/mnemo/models/multilingual.py`
- `mnemo-core/mnemo/interfaces/multilingual.py`
- `mnemo-core/mnemo/retrieval/multilingual.py`
- `mnemo-core/mnemo/retrieval/multilingual_providers.py`
- `mnemo-core/mnemo/retrieval/multilingual_advanced.py`
- `mnemo-core/mnemo/retrieval/advanced_sources.py`
- `mnemo-core/mnemo/retrieval/advanced.py`
- `mnemo-core/mnemo/phase85/multilingual.py`
- `mnemo-core/mnemo/phase85/models.py`
- `mnemo-core/mnemo/phase85/runtime.py`
- `mnemo-core/mnemo/storage/multilingual.py`
- `mnemo-core/mnemo/storage/multimodal_search.py`
- `mnemo-core/mnemo/storage/projection_generations.py`
- `mnemo-core/mnemo/storage/sqlite.py` (additive schema migration only)
- `mnemo-core/mnemo/storage/composite.py`
- `mnemo-core/mnemo/engine.py`
- `mnemo-core/mnemo/config.py` and a new versioned model-profile/config section
- `mnemo-server/mnemo_server/schemas/retrieval_v2.py`
- `mnemo-server/mnemo_server/schemas/capabilities_v2.py`
- `mnemo-server/mnemo_server/services/capabilities_v2.py`
- `mnemo-server/mnemo_server/mcp/contracts.py`
- `mnemo-server/mnemo_server/mcp/tools.py` only as needed to preserve the shared application path

### Mandatory tests/evaluation seams

- New focused core/server tests plus parameterized successors to `test_multilingual.py` and `test_multilingual_stage1.py`
- Versioned V2 evaluation manifest/qrels/stage schemas and evaluator
- WP-16 V2 behavioral cases only as a versioned manifest; the existing 31-case manifest remains historical

### Historical scripts

Do not silently edit the two invalid scratch runners. A new V2 evaluator should supersede them. `scripts/phase8_5_11_benchmark_models.py` may later receive a compatibility adapter for reproducibility, but historical outputs and model-selection meaning remain unchanged.

## 19. New modules recommended

Names are proposed and require approval; ownership is more important than spelling.

1. `mnemo-core/mnemo/models/text_representations.py` — strict observation/transformation/source-representation models.
2. `mnemo-core/mnemo/interfaces/text_representations.py` — detector, transformer, and registry protocols.
3. `mnemo-core/mnemo/retrieval/reranker_candidates.py` — sole V3 candidate builder and input audit.
4. `mnemo-core/mnemo/phase85/language_capabilities.py` — read-only operation-scoped projection over runtime/profile/generation/evaluation authority.
5. `mnemo-core/mnemo/retrieval/text_representations.py` — generic registry-driven representation planning; provider plugins live separately.
6. A versioned V2 evaluation module under `mnemo-server/mnemo_server/evaluation/` plus governed schemas/manifests outside scratch after approval.

Do not create an independent capability registry database, provider registry, authorization system, cursor, retrieval engine, or runtime state machine.

## 20. Migration and index lifecycle

1. **Phase A — finish current evaluation:** do not interfere with Antigravity or current EN/HI/MR artifacts.
2. **Phase B — freeze baseline:** retain DB/hash, manifest, queries, qrels, raw outputs, environment, model/profile and known-invalidity statement.
3. **Phase C — identify disposable state:** create an explicit digest-based allowlist of only V2 disposable derived/index artifacts. Do not purge source, frozen multimodal, V1, or evidence.
4. **Phase D — implement side-by-side:** new code/contracts and additive schema only; old aliases remain active.
5. **Phase E — build isolated V2:** copy immutable corpus/evidence into a disposable evaluation DB or consume authorized immutable references; create new V2 representation, sparse and BGE generation identities.
6. **Phase F — validate before activation:** exact provider/profile/vector identity, complete coverage, checksums, authorization/provenance, regression and transport tests.
7. **Phase G — atomic canary activation:** V2 alias changes only after all READY evidence exists; no replacement of V1 rows.
8. **Phase H — evaluate:** production-path evaluator, retained raw rankings/audits, stratified language/representation cohorts.
9. **Rollback:** atomically restore the retained V1 alias and disable V2 exposure. Keep failed V2 generations immutable for diagnosis; never repair source evidence in place.

Nothing is purged now. Later purge is limited to explicitly disposable, inactive V2 derived/index state after identity/path verification and governance approval. V1 evidence, Golden Dataset, frozen multimodal artifacts, governance records and model identities are never purge targets.

## 21. Risk register

| Risk | Likelihood | Impact | Mitigation | Verification |
|---|---|---:|---|---|
| Language detector false claim | High | High | Multiple hypotheses, authoritative metadata precedence, `und`, calibrated flag | Same-script ambiguity/adjudicated detector tests |
| Script treated as language | Medium | High | Independent typed observations and no inference rule | Deva HI/MR/unknown and Latn non-English tests |
| Unsupported language exposed | High | Critical | Runtime-derived operation-scoped intersection | Capability implication/negative tests |
| Legacy-font false transform | Medium | Critical | Representation detector + governed profile + confidence/fail closed | Positive/negative Krutidev fixtures without filename branches |
| Canonical text mutation | Low | Critical | Additive immutable derived rows only | Before/after hashes and zero-tolerance gate |
| Title-only reranking | High (current evaluator) | Critical | Sole typed builder and direct-call prohibition | Title-only mutation and evaluator/runtime parity tests |
| Vector-space mixing | Low | Critical | Exact vector identity and separate aliases/tables | V1/CLIP/BGE mismatch rejection |
| Scope leakage in projected FTS | High (current code) | Critical | Fix predicates before exposure | Source/document/version isolation tests |
| Provenance loss through transform/fusion | Medium | Critical | Typed lineage and final revalidation | Mutation/property tests |
| Partial/stale activation | Low | Critical | Existing coordinator plus combined V2 dependency identity | Interrupted/stale/concurrent activation tests |
| Provider claim mistaken for readiness | High | High | Orthogonal capability axes | Model-supported-but-unavailable fixtures |
| Index growth | Medium | Medium | Representation allowlist, coverage budgeting, dedup identities | Size/cardinality/resource tests |
| Evaluation L×L explosion | High | Medium | Risk/script-family/hub stratification | Manifest coverage audit |
| EN/HI/MR regression | Medium | High | Frozen regression plugins/fixtures and side-by-side alias | Baseline regression suite |
| MCP contract drift | Medium | High | Shared schemas/service and stdio/SSE parity | Contract digest/parity tests |
| Lifecycle misreporting | Medium | Critical | One runtime authority and deterministic projection | State implication and drift tests |

## 22. Exact implementation sequence after approval

1. Amend and approve all eight P0 proposal contracts; validate the JSON Schemas and traceability matrix.
2. Implement only versioned identity/observation/representation/reranker models and protocols; run property and compatibility tests.
3. Implement the central authorized reranker candidate builder and convert the BGE reranker public interface to the typed V3 path; retain old adapters behind compatibility boundaries.
4. Add V2 representation/observation/embedding storage and coverage through additive schema migrations; prove canonical/V1/multimodal immutability.
5. Correct scoped multilingual retrieval and build the operation-scoped runtime capability projection.
6. Generalize detector/script/transformation orchestration with EN/HI/MR retained as plugins.
7. Compose V2 sparse/dense/fusion/reranking through `KnowledgeEngine` with complete dependency gating.
8. Align HTTP/MCP contracts and prove `multilingual_text` schema plus stdio/SSE parity.
9. Implement the versioned stage-aware evaluator using the production path; no direct providers or synthetic title qrels.
10. Run full focused regression/security/static validation before creating any V2 data.
11. Build disposable isolated V2 generations, validate, canary-activate, evaluate and only then seek verification/certification.

## 23. Implementation GO / NO-GO

**IMPLEMENTATION NO-GO**

- **P0 blockers:** 8
- **P1 blockers/major work items:** 14
- **P2 issues:** 7

### Exact prerequisites before implementation

1. Freeze one compatible source/representation evidence-reference schema.
2. Freeze enforceable representation transformation lineage and authorization rules.
3. Freeze the exact reranker rendering/tokenizer/truncation/audit contract.
4. Freeze evaluator stage records, grounded qrels, and expanded failure prerequisites.
5. Add the scoped multilingual FTS defect, MCP representation mismatch, and combined activation gate to the proposal traceability/file-impact package.
6. Approve the operation-scoped capability projection algorithm and behavioral/security assurance mapping.
7. Record the current WP-10 evaluation as ongoing/historical and explicitly exclude known-invalid title-only outputs from V2 quality claims.

### First five implementation steps once approved

1. Add versioned source/observation/representation/candidate models and strict tests.
2. Add representation/detector/transform/candidate-builder protocols and the central reranker builder.
3. Add side-by-side V2 persistence and generation coverage with no data build or activation.
4. Fix exact source/document/version scope enforcement in multilingual retrieval and prove authorization-before-enumeration.
5. Generalize provider/runtime capability composition, then align HTTP/MCP schemas before any exposure.

The target design can become genuinely language-agnostic, but it is not yet so: hidden EN/HI/MR assumptions remain in detector selection, generation identities, planner paths, static profile/capability metadata, evaluation queries/qrels, and transport schemas. The proposal package must close the eight P0 contract/seam gaps before production implementation begins.

