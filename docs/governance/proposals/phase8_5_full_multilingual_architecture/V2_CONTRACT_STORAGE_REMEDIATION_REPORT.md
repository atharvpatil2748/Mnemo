# V2 Contract/Storage Remediation Report

Status: COMPLETE — PREREQUISITES RESOLVED; FIVE PRODUCTION ADAPTERS NOT IMPLEMENTED
Date: 2026-09-02

## 1. Problem statement

The prior adapter attempt stopped because the downstream reranker/projection contracts discarded the bounded V2 authorization decision, no governed SHA-256 database identity was runtime-verifiable, and the runtime treated the vector-generation UUID as the embedding-row generation UUID. This remediation addressed only those three prerequisites. It did not implement or register the five production adapters, execute retrieval, evaluate the corpus, invoke a model, rebuild an index, or change an alias.

## 2. Original blockers and repository evidence

| Blocker | Repository evidence | Result |
|---|---|---|
| Bounded authorization lost downstream | `RerankerEvidenceResolverV1`, the shared builder, and the advanced projector previously accepted actor/legacy scope rather than `V2RetrievalAuthorizationDecisionV1`. | RESOLVED |
| Canonical database identity absent | The build row persists corpus/census/profile/vector/build/storage bindings, while the database manifest has a UUID and the live SQLite file also contains mutable activation state. | RESOLVED |
| Vector ID used as embedding-row ID | `index_generation_sources` records vector `2b26443e-bb99-5bf8-a4af-a01ba99af8ce` → embedding `62243160-bed5-5064-a664-815984232e31`; embedding rows are keyed by the latter. | RESOLVED |

## 3. Contract interpretation

The repository already establishes one bounded decision through the server-derived `PrincipalContextV1` and `CentralAuthorizationServiceV1`. The correct additive interpretation is to propagate that same immutable decision, not actor identity or `AuthorizationScopeV1`, across all downstream V2 boundaries.

The canonical database artifact cannot safely be the live SQLite byte stream: activation metadata and SQLite/WAL page layout are mutable after the READY build. The governed artifact is therefore the immutable logical database-build envelope already represented by build and generation records. Its deterministic SHA-256 identifies the build contents while excluding mutable alias/runtime state.

The vector and embedding generations are distinct. The canonical source relationship is the `index_generation_sources` row with `source_kind='generation'`; neither UUID ordering nor latest-generation selection is admissible.

## 4. Exact changes

### Authorization propagation

- `RerankerEvidenceResolverV1.resolve_reranker_evidence` now requires the source, exact bounded decision, retrieval paths, and fusion rank.
- `RerankerCandidateBuilderProtocolV1.build` and `RerankerCandidateBuilderV1.build` require that decision and reject notebook/source/document/version expansion.
- Candidate provenance binds `authorization_scope_digest` to `decision_fingerprint`.
- `MultilingualV2RetrievalCandidate` retains the exact immutable decision.
- `V2AdvancedCandidateProjector.project_advanced_candidate` receives that retained decision; advanced projection verifies its provenance fingerprint.
- `FullMultilingualRetrievalApplicationV2` no longer performs or accepts the obsolete post-enumeration legacy evidence-authorizer dependency.
- Raw actor identity, `RetrievalPlanV2.security_scope_identity`, and `AuthorizationScopeV1` were not reintroduced downstream.

### Canonical database identity

Added `mnemo.v2-database-artifact-identity/1` with canonical JSON serialization (`sort_keys=true`, compact separators, UTF-8) and SHA-256. Its fields are database UUID/path, build run, corpus/census/profile/vector/build/storage digests, and four capability-sorted generation envelopes with checksums, dependencies, provider/model/configuration/vector-space/dimension bindings.

The persisted governed sidecar is `V2_DATABASE_ARTIFACT_IDENTITY.json`; its Draft 2020-12 schema is `V2_DATABASE_ARTIFACT_IDENTITY.schema.json`. The canonical identity is:

`0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d`

`GovernedV2DatabaseIdentityVerifier` opens the approved SQLite artifact using read-only immutable mode and verifies the build row, all generation rows, generation dependencies, and persisted embedding vector space. It performs no write and does not hash mutable alias/WAL/page state.

### Vector → embedding resolution

The runtime factory now asks the database identity verifier for `V2VectorEmbeddingGenerationBindingV1`. Resolution requires exactly one manifest-backed vector source equal to the active embedding generation and validates active membership, model plus revision, checksums, dimensions, configuration digests, vector space, database identity, and build run. Dense retrieval receives the resolved embedding-generation UUID. The active vector-generation UUID remains separately retained and validated.

No current generation UUID, alias digest, run UUID, database path, or vector-space digest is hard-coded in runtime selection logic.

## 5. Files changed

Production/interface prerequisites:

- `mnemo-core/mnemo/interfaces/multilingual.py`
- `mnemo-core/mnemo/retrieval/reranker_candidates.py`
- `mnemo-core/mnemo/retrieval/full_multilingual_v2.py`
- `mnemo-core/mnemo/retrieval/full_multilingual_advanced_v2.py`
- `mnemo-core/mnemo/phase85/v2_evaluation_runtime.py`
- `mnemo-core/mnemo/phase85/v2_database_identity.py` (new)

Governance/contracts:

- `V2_RETRIEVAL_AUTHORIZATION_CONTRACT.md`
- `V2_AUTHORIZED_EVIDENCE_RESOLUTION_CONTRACT.md`
- `V2_AUTHORIZATION_AND_EVIDENCE_RESOLUTION_DECISION.md`
- `V2_DATABASE_ARTIFACT_IDENTITY_CONTRACT.md` (new)
- `V2_DATABASE_ARTIFACT_IDENTITY.json` (new)
- `V2_DATABASE_ARTIFACT_IDENTITY.schema.json` (new)
- this report

Focused tests:

- `test_full_multilingual_v2.py`
- `test_v2_authorization_boundary.py`
- `test_v2_evaluation_runtime.py`
- `test_v2_contract_remediation.py`
- `test_v2_contract_storage_remediation.py` (new)

## 6. Tests and validation

| Validation | Result |
|---|---|
| Focused + complete relevant V2 unit set | PASS — 60 tests |
| Exact decision reaches enumeration, resolution, builder, and projector | PASS |
| Missing/scope-incompatible decision | PASS — fail closed |
| Canonical identity deterministic and sidecar matches live governed build rows | PASS |
| Altered/unrelated database identity | PASS — rejected |
| Dynamic vector→embedding dependency | PASS |
| Missing dependency, wrong model/revision, inactive set | PASS — rejected |
| Ruff, affected files | PASS |
| Strict mypy, six affected production/interface modules | PASS |
| Compileall | PASS |
| JSON Schema Draft 2020-12 metaschema validation | PASS — seven schemas |
| `V2_DATABASE_ARTIFACT_IDENTITY.json` instance validation | PASS |
| `git diff --check` | PASS |
| Forbidden actor/generation/network pattern searches | PASS — no matches |

Pytest emitted only the pre-existing Windows cache-cleanup permission warning after all tests had passed.

## 7. Protected-state verification

| Artifact/state | Before | After | Result |
|---|---|---|---|
| Golden corpus | 44 files; governed prior composite `92f806fe1a06a1dfa4443ffebe04c2f9aadca1bcf72811ac3110da1c113dba45` | 44 files; anchor hashes unchanged | PASS |
| `manuscript.pdf` | `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085` | same | PASS |
| Ramayana PDF | `759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75` | same | PASS |
| Frozen multimodal DB | `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d` | same | PASS |
| Frozen manifest | `17977efc87d3d95bb1e2e6e6c8025e78b63a4c3a0a301f98869b44724fef5a8f` | same | PASS |
| WP-10 DB | `8ffbb367b35a313c8866e89e21f499aeef92153d5ef6e57d362208f0c05bca0d` | same | PASS |
| Existing V2 DB raw bytes | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | same | PASS |
| Active V2 alias | `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` | same | PASS |
| Active generation membership | governed four-generation set | same | PASS |

The configured V1 database was already modified in the pre-existing worktree before this remediation; no remediation command targeted it, no V1 interface semantics were changed, and its post-state SHA-256 is `03cb1a0428f4b112807ffcbd3e5f025f0ed154dad572d478d63740e760a5b517`. No model process, provider inference, network download, ingestion, embedding generation, index build, alias mutation, corpus retrieval, benchmark, or evaluation ran.

## 8. Remaining blockers

The three prerequisite conflicts are resolved. The five concrete production adapters remain deliberately unimplemented and unregistered, as required by this task:

1. `ActiveV2GenerationInspector` production implementation;
2. `LanguageEvidenceAuthorizerV3` production implementation;
3. authorized evidence/source storage enumerator;
4. authorized evidence resolver;
5. governed candidate projector.

The next separately authorized phase may implement those adapters against the now-coherent bounded-decision, database-identity, and vector→embedding-generation contracts. Evaluation remains unauthorized.

## 9. Lifecycle

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
