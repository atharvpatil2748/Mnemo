# V2 Contract/Ownership Remediation Report

Status: PASS — CONTRACT AND OWNERSHIP PREREQUISITES RESOLVED; FIVE ADAPTERS NOT IMPLEMENTED  
Date: 2026-09-02

## 1. Original four blockers

| Blocker | Repository evidence | Result |
|---|---|---|
| Legacy-shaped authorizer name | `LanguageEvidenceAuthorizerV3` accepts `actor_id` and returns `AuthorizationScopeV1 | None`; `RepresentationPipelineV1` actively consumes it. | RESOLVED by additive separation; legacy behavior retained. |
| Missing V2 resolution model | `AuthorizedRerankerEvidenceV1` lacks the complete V2 runtime, database, generation, and transformation bindings. | RESOLVED by additive `AuthorizedV2EvidenceResolutionV1`. |
| Missing governed exact-evidence ports | No application-owned port expressed decision-bound enumeration and exact semantic resolution without exposing storage internals. | RESOLVED by opaque typed ports. |
| Production ownership ambiguous | `CentralAuthorizationServiceV1` is in server while the core runtime factory is in core. | RESOLVED by a server-owned registration port preserving server→core dependency direction. |

## 2. Repository and dependency evidence

`mnemo-core` defines domain models, protocols, retrieval applications, and the internal composition factory. It has no dependency on `mnemo-server`. `mnemo-server` depends on core, derives `PrincipalContextV1` through `principal_from_claims`, and owns `CentralAuthorizationServiceV1`. Existing server services construct security-sensitive application dependencies server-side.

Consequently, importing server authorization into core, moving it to core, or duplicating it would violate existing ownership. The governed split is: core owns ports/models/application composition; server owns authenticated production registration.

## 3. Legacy/V2 authorization separation

The unchanged legacy protocol now has the explicit source name `RepresentationEvidenceAuthorizerV3`. `LanguageEvidenceAuthorizerV3` remains a compatibility alias to the same object, so `RepresentationPipelineV1` retains the same method shape and semantics. The pipeline now names the explicit legacy port but performs no behavioral change.

The already-approved `V2RetrievalAuthorizerV1` remains separate. It accepts server-derived `PrincipalContextV1` and returns the complete `V2RetrievalAuthorizationDecisionV1`. It does not accept raw actor identity or return legacy scope. No new authorization implementation was added in this remediation; `CentralAuthorizationServiceV1` remains the sole future base authority.

## 4. AuthorizedV2EvidenceResolutionV1

Added immutable V2-only models in `mnemo.models.v2_evidence_resolution`:

- `V2GenerationSetBindingV1`: four explicit, distinct representation, language-text, embedding, and vector identities;
- `V2TransformationLineageV1`: deterministic transformation provenance;
- `V2CandidateRuntimeSecurityBindingV1`: the complete bounded decision plus alias, generation, profile/model, vector-space, canonical database, and build-run bindings;
- `V2AuthorizedEvidenceHandleV1`: an enumerated identity bound to that runtime;
- `V2SemanticEvidenceRecordV1`: exact semantic text/hash and representation lineage;
- `AuthorizedV2EvidenceResolutionV1`: final provenance-checked resolution.

The model rejects blank and title-only semantic text, representation/source mismatch, observation mismatch, missing derived lineage, generation substitution, and provenance-digest mismatch. It does not modify or replace `AuthorizedRerankerEvidenceV1`.

Draft 2020-12 schemas govern the resolution and candidate security binding:

- `V2_AUTHORIZED_EVIDENCE_RESOLUTION_CONTRACT.schema.json`
- `V2_CANDIDATE_RUNTIME_SECURITY_BINDING.schema.json`

## 5. Storage port boundary

Added `mnemo.interfaces.v2_evidence` with:

- `V2AuthorizedEvidenceStoreV1` for decision-bound enumeration and exact semantic resolution;
- `AuthorizedV2EvidenceResolverV1` for application-level revalidation and resolution;
- `GovernedV2CandidateProjectorV1` for projecting only a complete authorized resolution.

The ports carry the bounded decision, typed evidence handle, and explicit generation binding. They expose no connection, SQL, table name, filesystem path, or private join. A concrete storage implementation is deliberately deferred to the five-adapter phase.

## 6. Candidate runtime security binding

`V2CandidateRuntimeSecurityBindingV1` keeps authorization identity separate from evidence, representation, and generation identity. It retains the complete immutable decision and verifies that the explicit four-generation binding exactly equals the decision binding. Its deterministic digest and schema allow the future projector to reject detached or substituted evidence without reauthorizing.

## 7. Server-side production registration ownership

Added `FullMultilingualV2ServerDependencyAssemblerV1` and `ServerOwnedFullMultilingualV2RegistrationV1` under `mnemo-server`. The registration root constructs `CentralAuthorizationServiceV1` from the server-owned engine, supplies it to the future adapter assembler, and passes assembled dependencies to the existing core factory.

There is intentionally no production assembler implementation yet. The registration is not referenced by routers, MCP, HTTP, SSE, stdio, or capability discovery. `EXPOSED` remains false.

## 8. Exact changes

Production contracts/models:

- `mnemo-core/mnemo/interfaces/multilingual.py`
- `mnemo-core/mnemo/interfaces/v2_evidence.py` (new)
- `mnemo-core/mnemo/interfaces/__init__.py`
- `mnemo-core/mnemo/models/v2_evidence_resolution.py` (new)
- `mnemo-core/mnemo/models/__init__.py`
- `mnemo-core/mnemo/retrieval/text_representations.py`
- `mnemo-server/mnemo_server/services/full_multilingual_v2_registration.py` (new)
- `mnemo-server/mnemo_server/services/__init__.py`

Governance:

- `V2_RETRIEVAL_AUTHORIZATION_CONTRACT.md`
- `V2_AUTHORIZED_EVIDENCE_RESOLUTION_CONTRACT.md`
- `V2_AUTHORIZATION_AND_EVIDENCE_RESOLUTION_DECISION.md`
- `V2_AUTHORIZED_EVIDENCE_RESOLUTION_CONTRACT.schema.json`
- `V2_CANDIDATE_RUNTIME_SECURITY_BINDING.schema.json` (new)
- `V2_PRODUCTION_REGISTRATION_OWNERSHIP_CONTRACT.md` (new)
- this report

Tests:

- `test_v2_contract_ownership_remediation.py` (new)
- `test_v2_authorization_evidence_resolution_contracts.py`
- `test_v2_production_registration_contract.py` (new)

## 9. Validation

| Check | Result |
|---|---|
| Complete relevant V2 unit set plus full multilingual and registration tests | PASS — 71 tests |
| Focused ownership/schema/storage tests | PASS — 35 tests |
| RepresentationPipeline/V2 authorization focused regression | PASS |
| Ruff on affected files | PASS |
| Strict mypy on five affected production modules | PASS |
| Compileall for core and server packages | PASS |
| Draft 2020-12 metaschema validation | PASS — 8 schemas |
| Resolution and candidate-security instance validation | PASS |
| `git diff --check` | PASS |
| Static search: raw actor/legacy scope/SQLite in new V2 ports and model | PASS — none |
| Static search: public server registration/exposure | PASS — none |

Pytest emitted only the existing Windows cache-cleanup permission warning after tests passed. No test invoked a provider or corpus retrieval.

## 10. Protected-state verification

| Artifact/state | Before | After | Result |
|---|---|---|---|
| Golden evaluation corpus | 44 files; governed prior composite `92f806fe1a06a1dfa4443ffebe04c2f9aadca1bcf72811ac3110da1c113dba45` | 44 files; anchor hashes unchanged | PASS |
| `manuscript.pdf` | `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085` | same | PASS |
| Ramayana PDF | `759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75` | same | PASS |
| Frozen multimodal DB | `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d` | unchanged by repository evidence | PASS |
| Frozen manifest | `17977efc87d3d95bb1e2e6e6c8025e78b63a4c3a0a301f98869b44724fef5a8f` | unchanged by repository evidence | PASS |
| WP-10 DB | `8ffbb367b35a313c8866e89e21f499aeef92153d5ef6e57d362208f0c05bca0d` | unchanged by repository evidence | PASS |
| V2 DB raw bytes | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | same | PASS |
| Canonical logical V2 DB identity | `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d` | same, verifier PASS | PASS |
| Active alias digest | `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` | unchanged; V2 DB byte hash unchanged | PASS |
| Four generation identities | governed set | same, verifier PASS | PASS |
| V1 DB/index/aliases | pre-existing dirty state; no task command targeted them | unchanged by this task | PASS |
| Model artifacts | no model path write or provider process | unchanged | PASS |

No inference, ingestion, embedding generation, indexing, evaluation, network download, alias mutation, database write, or public exposure occurred.

## 11. Remaining blockers before the five adapters

The four contract/ownership blockers are resolved. The five production adapters remain deliberately unimplemented:

1. active V2 generation inspector implementation;
2. V2 retrieval authorizer implementation;
3. authorized source/storage enumerator implementation;
4. authorized evidence resolver implementation;
5. governed candidate projector implementation.

The server-side dependency assembler is intentionally unimplemented and therefore production runtime composition remains fail-closed. The next separately authorized phase may implement these adapters against the frozen ports and register them through the server-owned assembler. Evaluation and exposure remain unauthorized.

## 12. Lifecycle

DECLARED: PASS  
IMPLEMENTED: PASS  
CONFIGURED: PASS  
BUILDABLE: PASS  
READY: PASS  
ACTIVE: PASS  
EXPOSED: FALSE  
EVALUATED: FALSE  
VERIFIED: FALSE  
CERTIFIED: FALSE
