# V2 Authorized Evidence Resolution Contract

Status: GOVERNED PROPOSAL — IMPLEMENTATION-READY CONTRACT
Version: 1
Scope: resolving authorized V2 evidence into semantic text for shared reranker candidate construction.

## Purpose

This contract turns a governed LanguageEvidenceReferenceV3 into authorized, provenance-complete semantic evidence. It does not redefine LanguageEvidenceReferenceV3. It composes that canonical reference with a bounded V2 retrieval authorization decision.

## Governed storage request boundary

The request is expressed by the typed `V2AuthorizedEvidenceStoreV1` method boundary. It may be invoked only with an allow `V2RetrievalAuthorizationDecisionV1`, an explicit `V2GenerationSetBindingV1`, and an enumerated `V2AuthorizedEvidenceHandleV1`. It carries:

- the complete bounded authorization decision
- source_reference: LanguageEvidenceReferenceV3
- canonical_evidence_identity
- the active alias and the four distinct representation, language-text, embedding, and vector generation identities
- profile identity/fingerprint, model identity, vector-space identity, canonical database SHA-256, and build-run identity
- language_observation_reference
- script_observation_reference
- representation_observation_reference
- transformation_lineage when representation is derived
- request_fingerprint

No evaluator can invoke the store or construct/substitute the handle. No SQLite connection, SQL, table name, or private join is exposed by the port.

## AuthorizedV2EvidenceResolutionV1

A successful resolution contains:

- contract_version: mnemo.v2-authorized-evidence-resolution/1
- resolution_identity and request_fingerprint
- authorization_decision_fingerprint
- canonical evidence identity and source reference
- document, version, chunk, occurrence, and derivation identities where applicable
- active alias, generation, profile, vector-space, database and build-run bindings
- actual semantic_text and semantic_text_content_hash
- language, script and representation observation references
- representation state
- transformation lineage: profile identity, version, digest, source representation, target representation and derivation identity when applicable
- provenance digest
- resolution_fingerprint

Title metadata may be present only as metadata. It cannot be used as semantic_text. The semantic text must originate from the authorized canonical or governed derived evidence, be non-blank, and preserve its content hash and provenance.

## Conditional lineage rules

Canonical chunk evidence requires a chunk identity and canonical evidence identity. OCR occurrence or OCR region evidence requires occurrence or region lineage. Vision, language, or representation derivation evidence requires derivation identity, parent reference, source generation, and complete transformation lineage when transformed. The contract does not assume identifiers are UUIDs; it preserves the repository identity types already carried by LanguageEvidenceReferenceV3.

If the representation state requires a transformation, a missing, unresolved, ambiguous, unauthorized, or mismatched transformation lineage fails closed. The contract never rewrites canonical evidence and never performs filename, language, or script based transformation selection.

## Security invariants

Resolution fails closed for absent or stale authorization, outside-scope evidence, inactive or mismatched generation, V1 evidence, profile/vector-space mismatch, incomplete provenance, missing required lineage, ambiguous identity, unresolved representation, missing semantic text, blank semantic text, or title-only semantic text.

The additive `AuthorizedV2EvidenceResolverV1` revalidates the bounded decision before resolving text. `GovernedV2CandidateProjectorV1` accepts only `AuthorizedV2EvidenceResolutionV1`. The evaluator cannot directly query storage, resolve text, call providers, or build candidates. Legacy `AuthorizedRerankerEvidenceV1` and `RerankerEvidenceResolverV1` remain unchanged and are not the governed V2 evidence-resolution port.

## Language genericity and compatibility

Language, script, and representation remain independent evidence dimensions. The contract permits governed BCP-47 and ISO-15924 values without an EN/HI/MR enum, script-to-language inference, filename inference, or provider-marketing admission. It is additive to existing V1 and V3 models and does not change public MCP contracts.

## Bound authorization propagation

`AuthorizedV2EvidenceResolutionV1` contains `V2CandidateRuntimeSecurityBindingV1`, which retains the complete decision and exact four-generation runtime binding. The future authorized resolver and governed projector receive this object instead of reconstructing authorization. Raw actor and legacy scope parameters are forbidden.

Authorization metadata never replaces semantic evidence or evidence lineage. The decision fingerprint, evidence-reference digest, representation-reference identity, generation identity, and text content hash remain distinct fields with distinct meanings.

The machine-readable resolution and candidate-security schemas are `V2_AUTHORIZED_EVIDENCE_RESOLUTION_CONTRACT.schema.json` and `V2_CANDIDATE_RUNTIME_SECURITY_BINDING.schema.json`.
