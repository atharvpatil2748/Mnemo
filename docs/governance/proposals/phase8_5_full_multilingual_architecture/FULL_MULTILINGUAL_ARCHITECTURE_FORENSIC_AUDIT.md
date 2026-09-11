# PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL
# Mnemo Full Multilingual V2 Architecture — Revised Forensic Audit

**Revision date:** 2026-08-30  
**Scope:** document and architecture planning only.  
**Protected baseline:** Golden Dataset, canonical documents and filenames, frozen multimodal database/manifest, current WP-10 evaluation database and retained EN/HI/MR evidence.

## 1. Executive finding

Mnemo has a reusable language-neutral substrate, but it is not yet a generally multilingual system. BCP-47 `LanguageCode`, ISO-15924 `ScriptCode`, `LanguageEvidenceReferenceV2`, immutable derivations, generation aliases, vector-space isolation, authorization-before-enumeration, and stable HTTP/MCP retrieval contracts can remain. The limitations are concentrated in detector/script coverage, representation handling, generation coverage, runtime capability derivation, candidate construction, and evaluation diagnostics.

The future architecture shall be an additive internal V3 implementation behind stable V1/V2 public contracts. A language becomes usable through runtime-derived capability evidence—not through a hard-coded branch and not because a provider advertises it.

## 2. Newly established forensic facts and corrected diagnoses

### 2.1 Marathi was present; the diagnosis was wrong

The Golden Dataset's `manuscript.pdf` is genuine Marathi Unicode content:

- 5 pages and 10,683 extracted characters;
- 8,518 Devanagari Unicode characters (approximately 79.73%);
- no legacy/Krutidev encoding;
- 10 canonical chunks, of which 9 were detected as Marathi;
- 7 Marathi transliteration derivations;
- 17 multilingual embeddings;
- coverage in the active multilingual-vector index.

The earlier statement that Marathi target retrieval was unmeasured because the corpus had no Marathi document is therefore invalid. A retrieval miss can establish only that a governed query failed at some pipeline stage. It cannot establish `CORPUS_ABSENT` until a source census, authorized evidence census, language-observation census, generation coverage, and qrel check all agree.

### 2.2 Reranker input was invalid

The operational evaluation passed a title-only rendering equivalent to `title: manuscript.pdf` to the BGE reranker instead of the candidate's actual chunk semantic text. That invalidates conclusions attributed to the reranker for affected cases. The production adapter currently reads `item.candidate.content`, but evaluation code can construct independent candidate payloads; this duplicate construction seam is the defect.

V2 must have one typed `RerankerCandidateBuilderV1`, used by production and evaluation. It produces a `MultilingualRerankCandidateV3` with actual semantic text, identity, representation, language/script observations, provenance, and deterministic truncation audit. Title metadata is never a substitute for semantic content.

### 2.3 Generic queries were not semantic-quality evidence

Prompts equivalent to “Find related English evidence” contain no topic or entity. The current reports themselves classify WP-16 P85-B-18/P85-B-19 as generic or insufficiently specified. Such prompts may test tool routing or language-parameter acceptance, but must be excluded from retrieval-quality metrics. A retrieval miss from an ungrounded query is `QUERY_UNGROUNDED`, never evidence that the target language is missing or unsupported.

### 2.4 Hindi exposed a representation problem, not a corpus problem

`Valmiki Ramayana aur Ramakien Ek Tulnamatmak Adhyayan.pdf` contains legitimate Hindi whose canonical body is legacy-font encoded. The canonical text remains authoritative and immutable even when it is not Unicode semantic text. Replacing or rewriting the source is prohibited.

The generic fix is a representation layer: `RepresentationDetectorV1`, immutable `FontEncodingProfileV1`, `RepresentationTransformerV1`, and a runtime-derived transformation registry. Krutidev is one potential governed profile/fixture, not a language, not a hard-coded Ramayana path, and not permission to infer Hindi from a font or Devanagari script.

## 3. Existing strengths to preserve

| Existing component | Classification | Decision |
|---|---|---|
| `LanguageCode`, `ScriptCode` | Language-agnostic | Reuse unchanged. Language and script remain independent. |
| `LanguageEvidenceReferenceV2` | Language-agnostic provenance boundary | Reuse; add representation/transform references around it rather than sentinel IDs. |
| Language observations/derivations/embeddings stores | Generic payload storage | Extend with representation and coverage records; do not rewrite existing rows. |
| `ProjectionGenerationSpec` and atomic aliases | Generic lifecycle authority | Reuse for side-by-side V2 generations. |
| `LanguageEvidenceCatalogV2` | Authorization-safe enumeration | Preserve authorization before enumeration/scoring. |
| `SQLiteMultilingualDenseSource` | Bounded isolated vector search | Reuse with explicit capability and vector-space compatibility checks. |
| BGE-M3 and BGE reranker adapters | Provider-specific, appropriately isolated | Retain exact identities; expose provider declarations as `MODEL_SUPPORTED` only. |
| V2 retrieval DTOs and MCP tool names | Language-neutral public surface | Extend capability metadata additively; do not rename or duplicate tools. |
| CursorCodecV2 and WP-14 authorization | Frozen security contracts | No change. Reauthorize continuation and transformed evidence. |

## 4. Bottlenecks and root causes

| Blocker | Root cause | Required architectural correction |
|---|---|---|
| False “no Marathi document” conclusion | Pipeline failure was collapsed into corpus absence; no mandatory layered diagnostic | Layered evaluation trace plus typed failure taxonomy; `CORPUS_ABSENT` requires census proof. |
| Title-only reranking | Evaluation independently constructed reranker inputs | Central typed candidate builder; semantic-text and provenance invariants; retained input audit. |
| Misleading generic-query results | Capability prompts were scored as semantic retrieval queries | Separate capability/routing and topic-grounded quality cohorts. |
| Legacy Hindi text not semantically indexable | Canonical representation differs from Unicode semantic representation | Generic immutable representation detection/transformation generation. |
| EN/HI/MR detector ceiling | `ConservativeENHIMRDetector`, marker resources, and planner branches encode current scope | Provider/plugin detector registry with evidence, ambiguity, version, and `und` results. Retain baseline plugin. |
| Script conflated with language risk | Current `detect_script` covers only Latin/Devanagari and detector policy can use script as a strong clue | Independent ISO-15924 script observations; no script-only language assertion. |
| Model claims exposed as support | Static profile language arrays and static capability semantics | Per-operation language capability facts derived from providers, generations, runtime, evaluation, and governance. |
| Transform routing specialized | Devanagari transliteration is selected directly | Transformation registry keyed by source/target representation, script/language constraints, policy, and exact profile. |
| Coverage hidden in aggregate lifecycle | ADR-0074 state is currently aggregate capability/profile | Derived records per language/script/representation/operation/profile/generation and, for evaluation, direction. |
| Evaluation does not isolate failing layer | Corpus, detector, index, retrieval, reranker, authorization, qrel, and metric failures collapse together | Mandatory stage trace and independently passable gates. |

## 5. Required V2 abstractions (minimal and defect-driven)

### `LanguageCapabilityRegistryV1`

An adapter over `Phase85RuntimeV1`, model profiles, provider readiness, active generation coverage, and governed evaluation evidence. It is not a second runtime or provider registry. Its key is:

`(language, operation, representation, script?, profile_id?, generation_id?, direction?)`.

It records provider-declared model support separately from Mnemo implementation, readiness, exposure, evaluation, verification, and certification.

### `LanguageDetectorProviderV2` and `ScriptDetectorV1`

Detector plugins return ordered language hypotheses with confidence semantics, detector identity/version/configuration digest, source level (document/chunk/region/query), and `und` when unsupported or ambiguous. Script detection returns independent ISO-15924 observations, including mixed/unknown. Neither may infer the other.

### Representation transformation contracts

`TextRepresentationReferenceV1` identifies source evidence plus representation type and content hash. `RepresentationDetectorV1` identifies Unicode semantic text, legacy-font encoding, PDF encoding anomaly, OCR text, Vision text, normalized text, transliteration, or unknown. `RepresentationTransformerV1` produces immutable derived text with exact source/target representation and transformation identity. `TransformationRegistryV1` admits only configured, authorized, compatible transforms.

### Typed reranker candidate construction

`MultilingualRerankCandidateV3` and `RerankerCandidateBuilderV1` centralize query/candidate preprocessing. The candidate carries semantic text—not a display title—and retains a `RerankerInputAuditV1` containing source hash, rendered-input hash, preprocessing identities, token counts, truncation policy, retained range/hash, and provider identity.

## 6. Generic retrieval and authorization order

```text
server-owned principal and notebook/version scope
  → authorize candidate universe before enumeration/scoring
  → query language, script and representation observations
  → policy-authorized query transformations
  → embedding in one exact vector space
  → bounded dense and applicable sparse retrieval
  → deterministic fusion/RRF
  → shared typed reranker candidate builder
  → bounded reranking
  → authorization/provenance revalidation
  → stable ranked evidence envelope
```

Authorization occurs before enumeration, as required by ADR-0067 and WP-14. Post-rerank revalidation is defense in depth; it does not replace the early gate. Transformations inherit scope and can never widen it.

## 7. Capability semantics

Do not publish one boolean `supported_language`. Distinguish these operation facets:

- language detection;
- script detection;
- representation detection;
- representation transformation/normalization/transliteration/optional translation;
- embedding and vector indexing;
- sparse retrieval;
- dense retrieval;
- reranking;
- OCR language and Vision language;
- answer-language generation.

The requested effective progression is `MODEL_SUPPORTED → IMPLEMENTED → BUILDABLE → READY → ACTIVE → EXPOSED → EVALUATED → VERIFIED → CERTIFIED`, scoped to the exact record. To remain consistent with ADR-0074, it is derived from orthogonal axes: provider support, implementation, ADR-0074 runtime lifecycle (`DECLARED → CONFIGURED → BUILDABLE → READY → ACTIVE → EXPOSED`), assurance (`UNVALIDATED/EVALUATED/VERIFIED/CERTIFIED`), and availability. Negative outcomes include `UNSUPPORTED`, `UNAVAILABLE`, `DISABLED`, and `POLICY_DENIED`. `MODEL_SUPPORTED` is provider metadata only. Missing detector support does not erase explicitly authoritative language metadata; it limits detection claims.

## 8. Evaluation architecture and failure attribution

Every run must independently retain and gate:

1. corpus/source census;
2. language observations;
3. script observations;
4. representation observations;
5. transformations and validation;
6. embeddings/generation coverage;
7. dense and sparse candidate lists;
8. fused ranks;
9. typed reranker candidates and exact rendered inputs;
10. authorization/provenance outcomes;
11. HTTP/MCP envelopes;
12. qrels and metric computation.

Quality cases require source language, target language, topic/entity, expected document/version/evidence identity, relevance grade, and provenance expectation. Capability-only/generic prompts are reported separately and cannot enter Recall/MRR/nDCG.

The mandatory failure taxonomy is defined in `FAILURE_TAXONOMY.proposed.json`. A failed retrieval is not `UNSUPPORTED` or `CORPUS_ABSENT` unless its required evidence predicates are proven.

## 9. Scale without an L×L explosion

- Same-language admission cohort for every exposed language.
- Selected cross-language edges stratified by script family, same-script confusion risk, provider claim, deployment demand, and anchor languages.
- Mandatory representation cohorts for every admitted non-Unicode or transformed source class.
- OCR/Vision, mixed-language/script, no-answer, authorization, provenance, and reranker-pairwise cohorts.
- Rotate low-risk cross-language edges while retaining stable anchors; unmeasured edges remain `UNVALIDATED`.
- EN/HI/MR nine-direction results remain a frozen baseline and regression cohort, including documented defects rather than rewritten history.

## 10. Compatibility and governance conclusion

The safest strategy is an additive internal V3 implementation behind stable public V2 contracts. Extend schemas only with optional/versioned capability detail. Preserve V1 retrieval, existing notebooks, canonical `Chunk.text`, V1 text vectors, CLIP vectors, OCR/Vision derivations, MCP tool names, CursorCodecV2, authorization, and citation semantics.

The V2 architecture can consume immutable canonical/OCR/Vision evidence and create separate derived representation/language/vector generations in an isolated database. It requires no corpus replacement and no changes to the frozen multimodal state.

## 11. Forensic evidence limitations

The supplied Marathi census and reranker-input discovery are accepted as the newly established investigation baseline. Before V2 certification, their raw census/query/input artifacts and digests must be retained in the governed evaluation pack. This proposal does not infer additional provider language coverage, does not certify any language, and does not repair historical reports.
## 12. P0 contract resolution freeze

The pre-implementation P0 findings are resolved by the following normative proposal contracts. These supersede incompatible prose in this proposal package; they do not alter the repository's V1 contracts.

| Concern | Frozen proposal decision | Normative contract |
|---|---|---|
| Evidence identity | Preserve `LanguageEvidenceReferenceV2`; add the versioned, losslessly upgradable `LanguageEvidenceReferenceV3`. Strings remain valid evidence identities; no fake UUIDs. | `LANGUAGE_EVIDENCE_REFERENCE_V3.proposed.json` |
| Representation lineage | Language, script and representation remain independent. Authorized evidence is observed, transformed under a registered profile, and emitted as an immutable derived representation; canonical text is never rewritten. | `REPRESENTATION_TRANSFORMATION_MODEL.proposed.json` |
| Reranker input | Only server-resolved semantic evidence may produce `MultilingualRerankCandidateV3`; blank, title-only and caller-invented text are invalid. | `RERANKER_CANDIDATE_CONTRACT.proposed.json` |
| Evaluation | Semantic cases require evidence-level qrels and use the shared authorized application path. Ungrounded queries are routing-only. | `MULTILINGUAL_EVALUATION_CONTRACT.proposed.json` |
| FTS scope | V2 exposure is prohibited until projected FTS applies source/document/version/position/occurrence/derivation scope before enumeration and revalidates lineage after retrieval. | implementation plan and traceability matrix P0-06 |
| Transport vocabulary | `EVIDENCE_REPRESENTATION_VOCABULARY.proposed.json` is the single representation vocabulary for internal, HTTP, OpenAPI, MCP, structured content, JSON fallback and capability discovery contracts. | vocabulary schema |
| Runtime gate | READY, ACTIVE and EXPOSED are derived from the one `Phase85RuntimeV1` authority using the combined generation/readiness snapshot and atomic alias set. | `V2_ACTIVATION_READINESS_CONTRACT.proposed.json` |

EN/HI/MR remain regression cohorts only. No core lifecycle, storage or retrieval rule may enumerate languages or infer a language from a script.
