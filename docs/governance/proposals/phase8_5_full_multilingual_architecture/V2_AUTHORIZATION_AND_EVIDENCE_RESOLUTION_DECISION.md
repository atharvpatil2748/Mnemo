# V2 Authorization and Evidence Resolution Decision

Status: GOVERNED DECISION — CONTRACT BINDING
Decision: V2 production evidence adapters must not be implemented until they consume the versioned authorization and evidence-resolution contracts.

The trusted server boundary derives PrincipalContextV1 from validated claims. CentralAuthorizationServiceV1 remains responsible for base notebook and document scope policy. The V2 layer only narrows that authority to the resolved active alias, exact four V2 generations, profile, vector space, build run, database, admission policy, and bounded retrieval and positional scope.

No actor-to-notebook ownership rule is added. No evaluator trust exception exists. No authorization after enumeration is permitted. The implementation phase must adapt existing server-side principal derivation and scope resolution rather than creating private SQL authorization.

A failed or stale decision permits no enumeration. A resolved evidence object must carry actual semantic text, not a title, and must retain provenance and transformation lineage.

The bounded decision is propagated unchanged through enumeration, evidence resolution, shared candidate construction, and advanced projection. No downstream V2 interface accepts `actor_id` or `AuthorizationScopeV1` as a substitute. Candidate provenance binds the decision fingerprint without conflating it with evidence, representation, or generation identity.

The legacy `LanguageEvidenceAuthorizerV3` remains the unchanged representation-pipeline authorization protocol and is not the V2 authority. V2 uses the distinct `V2RetrievalAuthorizerV1` port. Exact semantic storage reads are governed by `V2AuthorizedEvidenceStoreV1`; successful results are represented by `AuthorizedV2EvidenceResolutionV1` and carry `V2CandidateRuntimeSecurityBindingV1`.

Production registration is server-owned because `CentralAuthorizationServiceV1` is server-owned and the repository dependency direction is server to core. Core remains the owner of typed ports and application composition. No server import is introduced into core, no second authorization authority exists, and no public exposure is registered by this decision.
