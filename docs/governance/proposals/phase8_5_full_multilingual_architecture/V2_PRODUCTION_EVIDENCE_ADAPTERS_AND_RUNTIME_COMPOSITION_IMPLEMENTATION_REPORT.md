# V2 Production Evidence Adapters and Runtime Composition Implementation Report

Status: BLOCKED BEFORE ADAPTER IMPLEMENTATION

## Requested scope

This phase authorized implementation of five production adapters while requiring server-derived PrincipalContextV1, CentralAuthorizationServiceV1 composition, a bounded V2 decision before enumeration, and an untrusted evaluator.

## Repository-grounded blocking conflict

The current production interfaces cannot carry the required authorization context without violating the approved contract.

1. FullMultilingualRetrievalApplicationV2.retrieve accepts actor_id: UUID, not PrincipalContextV1 or a server-issued authorization decision.

2. InternalFullMultilingualV2Evaluator.retrieve likewise accepts actor_id: UUID. It therefore allows the evaluator boundary to select the actor identity.

3. FullMultilingualAdvancedSourceV2 calls _actor_from_plan. That function converts RetrievalPlanV2.security_scope_identity into a UUID and supplies it as actor_id. This is evaluator/request data being reinterpreted as actor identity. The approved contract explicitly forbids this.

4. AuthorizedMultilingualDenseRetrievalV2 and AuthorizedMultilingualSparseRetrievalV2 call AuthorizedMultilingualSourceEnumeratorV2 with actor_id, scope, and position. The enumerator protocol has no V2RetrievalAuthorizationDecisionV1 input.

5. FullMultilingualRetrievalApplicationV2 invokes LanguageEvidenceAuthorizerV3 only after dense and sparse source enumeration and fusion. The current LanguageEvidenceAuthorizerV3 protocol returns AuthorizationScopeV1 or None and cannot produce or carry the newly governed bounded authorization decision.

6. The runtime composition dependency graph contains no CentralAuthorizationServiceV1 or trusted server principal boundary. An adapter cannot obtain a valid principal without inventing a mapping from evaluator actor_id to PrincipalContextV1.

Therefore a production implementation of the requested adapters would have to do at least one prohibited action: trust evaluator actor_id, derive a principal from it, authorize after enumeration, or add a private authorization interpretation.

## Required contract-alignment remediation

Before adapters can be safely implemented, an explicitly authorized compatibility change must:

- replace evaluator actor_id ingress with a server-owned request context or a server-issued bounded decision;
- make the application authorize once before dense/sparse enumeration;
- change the source enumerator protocol to consume only an allow V2RetrievalAuthorizationDecisionV1;
- change the V3 authorizer contract to create the bounded decision through CentralAuthorizationServiceV1;
- remove _actor_from_plan as an actor-identity derivation mechanism;
- establish the trusted factory/server composition boundary that derives PrincipalContextV1 from validated claims;
- bind candidate resolution and reranking to the same decision rather than a post-enumeration AuthorizationScopeV1 alone.

This is not a five-adapter-only change. It alters the retrieval application and protocol boundary that the adapters must implement against. It needs an explicit governed decision because it affects the existing internal application contract.

## Work not performed

No production adapter was implemented. No production source, test, corpus, model, database, V2 generation, alias, or index was modified. No retrieval, provider inference, benchmark, or evaluation was run.

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

## Exact next authorization required

Authorize a narrow V2 authorization-boundary remediation for the application, advanced source, dense/sparse enumerator protocol, candidate-builder authorization input, and composition factory. Only after that remediation is governed and implemented can the five adapters be implemented without inventing security semantics.
