# PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL
# P0 Contract Resolution and Implementation Readiness

## 1. Executive verdict

All eight contract-level P0 blockers recorded by `PRE_IMPLEMENTATION_ARCHITECTURE_AUDIT.md` are resolved in this proposal package. The package is **IMPLEMENTATION GO**, subject to human/governance approval. This is not production implementation, runtime readiness, activation, exposure, verification, or certification.

Resolved contract schemas:

- `LANGUAGE_EVIDENCE_REFERENCE_V3.proposed.json`
- `REPRESENTATION_TRANSFORMATION_MODEL.proposed.json`
- `RERANKER_CANDIDATE_CONTRACT.proposed.json`
- `MULTILINGUAL_EVALUATION_CONTRACT.proposed.json`
- `FAILURE_TAXONOMY.proposed.json`
- `EVIDENCE_REPRESENTATION_VOCABULARY.proposed.json`
- `V2_ACTIVATION_READINESS_CONTRACT.proposed.json`
- `LANGUAGE_CAPABILITY_MODEL.proposed.json`

## 2. P0-01 — Canonical evidence reference

**Current behavior/root cause:** the repository's `LanguageEvidenceReferenceV2` correctly uses string evidence/chunk identities and exact notebook/source/document/version lineage. Earlier proposal JSON duplicated it with incompatible UUID-only identities and kinds.

**Final decision/contract:** preserve V2 unchanged and introduce a properly versioned `LanguageEvidenceReferenceV3`. This choice is required because whole OCR occurrences and representation derivations cannot be represented losslessly by a wrapper whose source is restricted to a V2 kind. V3 supports canonical chunk, OCR occurrence, OCR region, Vision derivation, language derivation and representation derivation. It has strict kind-dependent chunk/occurrence/derivation/generation/parent rules and no path/URI fields. `lineage_origin` distinguishes a native V3 record from a lossless legacy V2 upgrade, so only the latter may carry a null parent digest for a legacy language derivation. V2 upgrades losslessly; V3-only kinds do not downcast.

**Production seam / implementation:** additive model plus V2→V3 adapter near `mnemo-core/mnemo/models/multilingual.py`; storage and delivery serializers adopt V3 only for V3 data.

**Tests:** schema/model round-trip for every kind; non-UUID chunk identity; prohibited sentinel IDs; invalid kind/lineage combinations; V2 upgrade; V3 downcast denial; cross-scope authorization.

**Security/migration/rollback:** mandatory scope identity is retained; possession grants no authorization. No V1/V2 row is rewritten. Rollback removes V3 exposure and leaves V2 intact.

**Lifecycle evidence:** READY requires typed references and lineage digest validation; ACTIVE requires complete generation rows bound to V3; EXPOSED requires response-schema/provenance/security validation.

## 3. P0-02 — Representation transformation

**Current behavior/root cause:** existing canonical/OCR/Vision/language evidence is useful, but the former proposal left hashes, authority, generation and authorization lineage loose or optional.

**Final decision/contract:** `RepresentationObservationV1`, `TransformationProfileV1`, `TextRepresentationReferenceV1`, `RepresentationTransformationV1`, typed provenance/scope, and `TransformationRegistryV1` are frozen in `REPRESENTATION_TRANSFORMATION_MODEL.proposed.json`. Language, script and representation are independent. Selection is by governed representation/profile compatibility, never filename, path, document, language, or script. Unknown/ambiguous/unavailable/failed transformations emit no output. Canonical text is immutable.

**Production seam / implementation:** additive representation models/interfaces/provider registry/builder and storage; consume canonical/OCR/Vision records as read-only inputs.

**Tests:** deterministic IDs/hashes; authority/calibration; allowed-source/target validation; authorization before observation/transformation; lineage inheritance; restart/idempotency/interruption; failure-with-no-output; canonical hash unchanged.

**Security/migration/rollback:** server-computed scope digest and exact source identity bind every derivation. V2 rows are side-by-side. Disable a profile/generation to roll back; retain failed rows for diagnosis.

**Lifecycle evidence:** READY requires configured compatible registry entries and complete coverage; ACTIVE requires the compatible representation generation in the atomic set; EXPOSED requires security and provenance validation.

## 4. P0-03 — Reranker V3

**Current behavior/root cause:** historical evaluators could send `title: <document>` directly to a private reranker runtime. Production/evaluation candidate construction was not structurally shared or auditable.

**Final decision/contract:** only `RerankerCandidateBuilderV1` may emit `MultilingualRerankCandidateV3`. It resolves actual semantic text from authorized evidence; callers cannot submit scored text. Blank/whitespace and title-only input fail before tokenization/provider invocation. Title is display metadata and excluded from provider input. `RerankerInputAuditV1` binds candidate/source/representation/provenance, provider/model/revision/configuration, preprocessing, tokenizer/revision, query/document/token counts and exact hashes.

The exact 256-token policy is: preprocess query/document separately; tokenize without special tokens or truncation; compute pair special-token count from the frozen tokenizer; content budget is `256-special`; retain at most 96 head query tokens while reserving at least one document token; allocate the remainder only to the document head; build the exact token pair; reject length/accounting mismatch; hash exact provider inputs; rank by score descending, then original ordinal, then lowercase candidate UUID. No unused document budget moves back to query above 96.

**Production seam / implementation:** new shared builder; existing multilingual provider and retrieval rerank call sites accept only V3/public interface.

**Tests:** actual text positive case; blank/title-only/caller bypass negatives; token accounting; deterministic truncation/hashes; candidate identity; stable ties; max 200 candidates/batch bounds; evaluation/production parity.

**Security/migration/rollback:** authorization precedes resolution; audits expose hashes/IDs, not text. Disable V3 rerank and return an explicitly degraded, non-reranked result if policy permits; never silently fall back to V1 reranking.

**Lifecycle evidence:** READY requires builder/provider/tokenizer identities and conformance; ACTIVE requires shared retrieval composition; EXPOSED requires redaction and transport-parity evidence.

## 5. P0-04 — Evaluation/production path parity

**Current behavior/root cause:** WP-10 scratch evaluators call providers/private runtime, use permissive authorization and build independent payloads. They are retained historical artifacts, not a repair target.

**Final decision/contract:** `RuntimeParityEvidenceV1` requires the same application, authorization, retrieval/fusion, candidate builder, preprocessing, tokenizer, public reranker adapter and provenance validator identities. Direct provider calls, private runtime access and caller-built reranker input are schema-invalid. Provider conformance tests are separate and never count as runtime/transport/behavioral evidence.

**Production seam / implementation:** create a governed V2 evaluator that invokes the shared public application path with a real principal/scope. Do not edit historical scripts.

**Tests:** negative direct/private/caller-build cases; identity/digest parity; real-scope denial; deterministic replay; raw rankings and audit retention.

**Security/migration/rollback:** no permissive authorizer; no invented lineage. A parity failure invalidates the evaluation run only and cannot advance assurance.

**Lifecycle evidence:** shared-path evidence is required for READY; retained runtime records for ACTIVE; HTTP/MCP parity for EXPOSED. Quality evidence is a later VERIFIED gate.

## 6. P0-05 — Evidence qrels and grounded evaluation

**Current behavior/root cause:** document-title qrels and generic prompts could be scored as semantic quality, and a miss could be mislabeled corpus absence.

**Final decision/contract:** `QueryRecordV2`, `EvidenceQrelV2`, `CorpusPresenceEvidenceV1`, `EvaluationStageRecordV2`, `EvaluationFailureRecordV2` and `EvaluationCaseRecordV2` are frozen. Semantic cases require `query_grounded`, a topic and evidence-level qrels with exact V3 identity, representation, language/script observations, authorization expectation, exact provenance and adjudication. Document-level cases are explicitly non-semantic. Ungrounded cases are excluded from ranking metrics. `CORPUS_ABSENT` requires retained immutable source and authorized-evidence censuses proving absence.

**Production seam / implementation:** new V2 manifest/qrel validators, evaluator, stage recorder and scorer. The expanded typed failure taxonomy prevents layer collapse.

**Tests:** invalid document-only qrel; ungrounded exclusion; multiple grades; wrong version/occurrence/derivation; corpus-present miss; absent predicate; failure-stage injection; metric fail-closed.

**Security/migration/rollback:** evidence qrels do not grant access and evaluator observes only authorized evidence. Reject/withdraw an invalid pack while retaining it as invalid historical evidence.

**Lifecycle evidence:** evaluation is not a runtime READY prerequisite. Approved raw rankings/qrels are required for EVALUATED/VERIFIED and never inferred from ACTIVE/EXPOSED.

## 7. P0-06 — Multilingual FTS scope leak

**Current behavior/root cause:** projected multilingual FTS in `mnemo-core/mnemo/storage/multimodal_search.py` does not apply every requested source/document/version/position constraint before enumeration.

**Final decision/contract:** V2 must apply principal/notebook authorization and requested source, document, version, positional, occurrence and derivation filters before FTS enumeration/scoring. The query and row reconstruction retain exact scope; final results undergo full provenance and scope revalidation. Any missing/unsupported/malformed scope fails closed and non-enumerating.

**Production seam / implementation:** the named storage module, its interface and retrieval source. **V2 MUST NOT be exposed while this scope defect remains unresolved.**

**Tests:** cross-notebook/source/document/version; position range/page; occurrence/derivation; forged and mismatched scope; unauthorized count/timing non-enumeration; post-retrieval lineage mismatch.

**Security/migration/rollback:** this is a pre-exposure WP-14 regression gate. Disable projected multilingual source/alias; V1 authorized paths remain unchanged.

**Lifecycle evidence:** scope/filter tests and authorization-compatibility digest are required for READY; scoped integration for ACTIVE; security verification for EXPOSED.

## 8. P0-07 — MCP representation contract

**Current behavior/root cause:** internal Pydantic accepts `multilingual_text`, while MCP JSON Schema omits it, allowing advertisement/callability disagreement.

**Final decision/contract:** `EVIDENCE_REPRESENTATION_VOCABULARY.proposed.json` is the canonical vocabulary. Internal Pydantic, HTTP schema, OpenAPI, MCP JSON Schema, structured content, canonical JSON fallback and capability discovery must be generated/mapped from its version/digest. Tool names remain unchanged. Existing values retain meaning; `multilingual_text` is additive and callable only when the runtime-derived capability is exposed.

**Production seam / implementation:** `mnemo-server/mnemo_server/mcp/contracts.py`, `schemas/retrieval_v2.py`, OpenAPI generation, capability service/schema and transport tests.

**Tests:** schema accepts every active value/rejects unknown or disabled value; normalized request equality; HTTP/stdio/SSE argument/result/error/completeness/provenance equality; structured/fallback canonical equality; capability/callability consistency.

**Security/migration/rollback:** clients cannot enable a representation; runtime state and authorization still govern. Rollback removes the V2 advertisement/mapping and retains stable tools/old vocabulary.

**Lifecycle evidence:** contract completeness and all transport digests/parity are required only for EXPOSED, after ACTIVE.

## 9. P0-08 — Combined activation/readiness

**Current behavior/root cause:** language-text availability could dominate engine/capability readiness even without compatible embedding/vector/provider dependencies.

**Final decision/contract:** `V2_ACTIVATION_READINESS_CONTRACT.proposed.json` is a deterministic snapshot/projection over the sole `Phase85RuntimeV1` authority. READY requires provider, detector/representation/transformation readiness; exact READY representation, sparse, embedding and vector generations; vector-space compatibility; complete language/script/representation coverage; valid checksums/provenance; authorization compatibility; and valid rollback metadata. ACTIVE requires READY plus one atomic alias-set promotion matching that generation set. EXPOSED requires ACTIVE plus shared application path, canonical representation vocabulary, HTTP/OpenAPI/MCP/structured/fallback/capability parity, stdio/SSE evidence and passed pre-exposure security gate.

Missing vector/sparse generation, incomplete embedding, stale generation, provider-revision/vector-space mismatch, incomplete language/representation coverage, missing transport contract or failed security proof produces the typed fail-closed reason in the schema. Activation compares prior alias-set digest and commits all aliases once; interruption commits none. Rollback restores one retained complete compatible set atomically.

**Production seam / implementation:** generation coordinator, `phase85/runtime.py`, engine composition and capability adapter; no second registry/state machine.

**Tests:** every false dependency; four-generation uniqueness; partial/stale/mismatch; concurrent promotion; interrupted commit; rollback; capability/runtime/callability parity.

**Security/migration/rollback:** authorization compatibility is a READY input and security verification is an EXPOSED input. V1/frozen aliases are not mutated; prior V2 set remains the rollback target.

## 10. Language-generic contract

No schema enumerates EN/HI/MR as architectural limits. Language uses normalized BCP-47-compatible tags (including `und`), script is an independent ISO-15924 observation, and representation is a separate governed vocabulary. Provider claims, implementation, configuration, generation coverage, evaluation and assurance remain separate axes. Provider marketing does not produce operational support.

## 11. Proposal documents changed

Updated baseline documents: `FULL_MULTILINGUAL_ARCHITECTURE_FORENSIC_AUDIT.md`, `FULL_MULTILINGUAL_IMPLEMENTATION_PLAN.md`, `MIGRATION_AND_INDEX_LIFECYCLE_PLAN.md`, `LANGUAGE_CAPABILITY_MODEL.proposed.json`, `FAILURE_TAXONOMY.proposed.json`, `RERANKER_CANDIDATE_CONTRACT.proposed.json`, `REPRESENTATION_TRANSFORMATION_MODEL.proposed.json`, `MULTILINGUAL_EVALUATION_ARCHITECTURE.proposed.md`, `IMPLEMENTATION_TRACEABILITY_MATRIX.md`, and `FILE_IMPACT_MATRIX.md`.

Added necessary contracts: `LANGUAGE_EVIDENCE_REFERENCE_V3.proposed.json`, `EVIDENCE_REPRESENTATION_VOCABULARY.proposed.json`, `MULTILINGUAL_EVALUATION_CONTRACT.proposed.json`, and `V2_ACTIVATION_READINESS_CONTRACT.proposed.json`.

## 12. Remaining P1/P2 work

The audit's 14 P1 and 7 P2 items remain implementation/evidence work, not unresolved P0 contract ambiguity. P0 contracts concretize substantial parts of P1-12 (capability projection), P1-13 (failure taxonomy), and P1-14 (evaluation versioning), but production implementation/tests are still required. Other major work remains: versioned language hypotheses/mixed regions, baseline detectors as plugins, governed provider claims/artifact integrity, embedding representation lineage/uniqueness, explicit authorized embedding reads, generation source/coverage manifests, normal KnowledgeEngine composition, and mixed-representation reranking. P2 terminology, scope inference, authority/calibration, model-limit naming, vector-space/coverage policy, baseline naming and sanitized diagnostics remain required before verification/certification where applicable.

## 13. Validation and consistency

- JSON parsed and Draft 2020-12 meta-schema validation passed for all eight proposal JSON schemas.
- All eight `$id` values are unique and all internal/external `$ref` links resolve through the local proposal registry.
- Conditional lineage, grounded-query, corpus-presence, representation-authority, V3 candidate and READY/ACTIVE/EXPOSED contracts are machine-constrained; semantic cross-field hash equality remains an implementation validation responsibility explicitly required above.
- Cross-document vocabulary is consistent: V3 is additive over V2; historical evaluators remain untouched; canonical representation vocabulary is singular; Phase85RuntimeV1 is the sole lifecycle authority; V2 aliases activate atomically; tool names/CursorCodecV2/authorization are unchanged.

## 14. Protected-state proof

Only files under this proposal directory were written. Production code and tests were not modified. No model was loaded/downloaded, no benchmark/ingestion/generation/index/activation ran, and no database was opened for write.

Post-edit protected hashes:

- frozen multimodal DB: `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d`
- freeze manifest: `17977efc87d3d95bb1e2e6e6c8025e78b63a4c3a0a301f98869b44724fef5a8f`
- Golden `manuscript.pdf`: `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085`
- Golden Ramayana PDF: `759f2adbfd2fc1191ff8576401d1cbc34bbfefa79a573e8747c53d4c858af75`
- current WP-10 evaluation DB (read-only before/after this task): `8ffbb367b35a313c8866e89e21f499aeef92153d5ef6e57d362208f0c05bca0d`

These match the audit baseline. Evaluation databases and their WAL/SHM were not modified.

## 15. Final decision

```ini
P0 resolved = 8 / 8
P0 unresolved = 0
JSON schema validation = PASS
Cross-document consistency = PASS
IMPLEMENTATION = GO AFTER HUMAN/GOVERNANCE APPROVAL
```

GO authorizes implementation only. READY, ACTIVE, EXPOSED, EVALUATED, VERIFIED, SECURITY VERIFIED, BEHAVIORALLY VERIFIED and CERTIFIED require their later evidence and cannot be inferred from this proposal resolution.
