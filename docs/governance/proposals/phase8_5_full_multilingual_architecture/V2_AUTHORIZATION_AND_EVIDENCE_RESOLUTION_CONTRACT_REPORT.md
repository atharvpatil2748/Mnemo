# V2 Authorization and Evidence Resolution Contract Resolution Report

Status: COMPLETE — CONTRACTS RESOLVED; ADAPTER IMPLEMENTATION DEFERRED

## Outcome

The missing operation-scoped authorization and authorized evidence-resolution seams are now governed as versioned Draft 2020-12 contracts. The next phase can implement the five production adapters without inventing principal, scope, provenance, generation, or vector-space semantics.

## Repository semantics reused

- PrincipalContextV1 is derived at the server boundary from authenticated claims by CentralAuthorizationServiceV1.principal_from_claims.
- CentralAuthorizationServiceV1 remains the base notebook and document authorization authority.
- StorageDocumentScopeResolverV1 remains the authority for document, version, source and requested-notebook association.
- RetrievalScopeV2 and PositionalScopeV2 remain the scope vocabulary.
- LanguageEvidenceReferenceV3 remains the canonical language evidence reference.
- AuthorizedRerankerEvidenceV1 remains the canonical nonblank, provenance-bound semantic evidence contract.
- Active V2 alias resolution and governed profile/vector-space identities remain server-resolved authorities.

## Semantics deliberately not invented

- No actor-to-notebook ownership mapping.
- No evaluator-trusted identity or permissive evaluator authorization.
- No ownership inference from actor_id.
- No private SQL authorization path.
- No time-to-live value for decisions; staleness is identity-based.
- No language allowlist, script-language inference, filename inference, generation override, database override, profile override, or vector-space override.

## Contracts created

- V2 Retrieval Authorization Contract and its request/decision schemas.
- V2 Authorized Evidence Resolution Contract and its request/resolution schemas.
- Binding decision documenting composition with CentralAuthorizationServiceV1.
- Failure taxonomy additions for principal, operation, scope, active-alias, profile, staleness, lineage, semantic-evidence, title-only, and V1-in-V2-path failures.

## Required next implementation work

The next phase may implement only against these contracts:
- LanguageEvidenceAuthorizerV3 as CentralAuthorizationServiceV1 plus V2 narrowing policy.
- ActiveV2GenerationInspector using active alias and governed manifests.
- AuthorizedMultilingualSourceEnumeratorV2 accepting an allow decision before enumeration.
- RerankerEvidenceResolverV1 resolving governed semantic text after revalidation.
- V2AdvancedCandidateProjector using the shared RerankerCandidateBuilderV1.

## Validation

- Draft 2020-12 schema validation: PASS for both contract schemas.
- Focused contract, V2 remediation, and runtime-composition tests: PASS, 27 tests.
- Ruff: PASS.
- Strict mypy for the added contract tests: PASS.
- Compileall for the added contract tests: PASS.
- Git diff check: PASS.

The test environment emitted only an existing Windows pytest-cache access warning. No adapter, provider, runtime-evaluation, corpus, database, alias, model, or protected-artifact operation was executed.

## Protected-state verification

The working-tree changes for this phase are confined to governed proposal documents, Draft 2020-12 schemas, and focused contract tests. No Golden Dataset, database, index, model snapshot, active V2 alias, or V2 generation content was written.

## Lifecycle

DECLARED, IMPLEMENTED, CONFIGURED, BUILDABLE, READY and ACTIVE remain unchanged. EXPOSED is FALSE. EVALUATED is FALSE. No retrieval, provider inference, benchmark, database mutation, alias mutation, or corpus mutation occurred in this contract-resolution phase.
