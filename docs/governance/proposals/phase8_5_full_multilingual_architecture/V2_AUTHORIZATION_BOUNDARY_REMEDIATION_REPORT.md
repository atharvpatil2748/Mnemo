# V2 Authorization Boundary Remediation Report

Status: COMPLETE — ADAPTER IMPLEMENTATION REMAINS DEFERRED

## Original conflict

The V2 application previously accepted evaluator actor_id input, the advanced source derived an actor from RetrievalPlanV2.security_scope_identity, and both dense and sparse sources accepted raw actor/scope data before any V2 decision existed.

## Implemented boundary

A new immutable V2ActiveRuntimeBindingV1 and V2RetrievalAuthorizationDecisionV1 are additive V2-only models. The decision binds principal actor identity, retrieval and positional scope, operation, active alias identity, four generations, profile, vector space, database, build run, admission policy, authorization policy, request fingerprint, issuance identity, and provenance obligations.

A new V2RetrievalAuthorizerV1 protocol is the sole application ingress for a bounded decision. Its later concrete implementation must compose the server-derived PrincipalContextV1 with CentralAuthorizationServiceV1 and the V2 policy; this phase intentionally does not implement that adapter.

## Application and source ordering

FullMultilingualRetrievalApplicationV2 now requires PrincipalContextV1. It rejects unauthenticated principals before invoking the retrieval authorizer. It receives a bounded V2 decision before dense or sparse work and passes that decision, rather than actor/scope fields, to each source.

The V2 dense and sparse enumerator interfaces now require V2RetrievalAuthorizationDecisionV1. Raw actor_id, RetrievalScopeV2, and PositionalScopeV2 inputs were removed from their enumeration boundary.

FullMultilingualAdvancedSourceV2 no longer derives identity from RetrievalPlanV2.security_scope_identity. Ranked V2 access through the unbound AdvancedRetrievalSourceV1 entry point fails closed; the new retrieve_authorized entry point requires an already server-owned PrincipalContextV1.

InternalFullMultilingualV2Evaluator no longer contains an actor_id retrieval entry point.

## Security semantics preserved

- PrincipalContextV1 remains server-derived.
- CentralAuthorizationServiceV1 remains the future base authorization authority.
- No actor-to-notebook ownership relation was added.
- No evaluator-specific authority exists.
- No V1 interface or public MCP transport was changed.
- No decision can be expanded by downstream source enumeration.

## Tests and validation

- Focused V2 boundary, runtime composition, full V2 contract, and contract-schema tests: PASS, 41 tests.
- Ruff: PASS.
- Strict mypy for affected source modules: PASS.
- Compileall: PASS.
- Git diff check: PASS.

The only test-environment messages were existing Windows pytest-cache cleanup warnings.

## Deferred work

The five concrete production adapters remain intentionally unimplemented:
- ActiveV2GenerationInspector
- LanguageEvidenceAuthorizerV3 implementation, including CentralAuthorizationServiceV1 composition
- AuthorizedMultilingualSourceEnumeratorV2 implementation
- RerankerEvidenceResolverV1 implementation
- V2AdvancedCandidateProjector implementation

They can now implement against a coherent, decision-before-enumeration boundary.

## Protected state

No corpus, PDF, database, generation, alias, V1 index, model snapshot, provider, benchmark, evaluation, or transport action occurred.

## Lifecycle

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

