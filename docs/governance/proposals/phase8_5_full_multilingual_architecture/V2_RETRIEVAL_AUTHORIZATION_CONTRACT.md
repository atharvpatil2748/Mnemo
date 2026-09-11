# V2 Retrieval Authorization Contract

Status: GOVERNED PROPOSAL — IMPLEMENTATION-READY CONTRACT
Version: 1
Scope: internal Full Multilingual V2 retrieval and evaluation composition only.

## Repository-grounded base semantics

CentralAuthorizationServiceV1 remains the sole base authorization authority. Its server boundary derives PrincipalContextV1 from authenticated claims through principal_from_claims. Its present persistence policy establishes notebook existence and document/version/source association; it does not establish actor-to-notebook ownership. This contract does not invent such an ownership relation.

An evaluator receives only a composed application service. It does not receive a principal, database handle, provider, generation selector, candidate builder, authorization service, or authorization decision.

## V2RetrievalAuthorizationRequestV1

A request is created at the trusted server or internal application boundary after principal derivation. It contains only:

- contract_version: mnemo.v2-retrieval-authorization-request/1
- request_id
- authenticated_principal: actor_id, authenticated=true, and principal_derivation_identity
- operation: the existing retrieval operation identifier
- requested_retrieval_scope: RetrievalScopeV2
- requested_positional_scope: PositionalScopeV2
- active_alias_set_identity
- active_generation_identities: exactly the canonical four V2 generations resolved by the server
- profile_fingerprint
- vector_space_identity
- database_identity
- build_run_identity
- admission_policy_identity
- request_fingerprint

The evaluator cannot supply generation, vector-space, profile, database, or alias overrides. The server resolves the active alias independently and rejects a request whose bound fields differ.

## V2RetrievalAuthorizationDecisionV1

A decision is produced by composition of CentralAuthorizationServiceV1 and the V2 retrieval policy. It is bounded and non-escalating. It contains:

- contract_version: mnemo.v2-retrieval-authorization-decision/1
- decision_id
- request_fingerprint
- allow
- denial_code when allow is false
- authorized_operation
- authorized_retrieval_scope
- authorized_positional_scope
- authorized_alias_set_identity
- authorized_generation_identities
- authorized_profile_fingerprint
- authorized_vector_space_identity
- authorized_database_identity
- authorized_build_run_identity
- authorization_policy_identity and revision
- required_provenance_evidence
- issued_at
- decision_fingerprint

An allow decision must bind every authorized field exactly to the trusted active runtime resolution. A denied decision has no enumerable scope. An enumerator consumes only an allow decision; it never consumes the original request.

Decisions have no invented time-to-live. They become stale immediately when any bound active-alias, generation, profile, vector-space, database, build-run, authorization-policy, or requested-scope identity no longer matches current authoritative state.

## Mandatory ordering invariant

Principal resolution
→ CentralAuthorizationServiceV1 operation authorization
→ retrieval and positional scope authorization
→ active V2 alias and four-generation validation
→ profile, database, build-run and vector-space validation
→ operation admission
→ bounded allow decision
→ sparse or dense evidence enumeration

No source, FTS row, vector row, candidate, semantic text, provider inference, or reranker input may be enumerated or constructed before an allow decision exists.

## Compatibility and non-goals

This contract extends V2 only. It does not alter V1 authorization, RetrievalScopeV2, PositionalScopeV2, CursorCodecV2, public transport names, actor ownership semantics, or language capability semantics. Language, script, and representation remain independent; no language allowlist or script-to-language inference is permitted.

## Failure behavior

The V2 policy fails closed using the governed taxonomy for missing principal, unauthorized operation, unauthorized retrieval scope, unauthorized positional scope, inactive alias, generation mismatch, profile mismatch, vector-space mismatch, stale decision, dependency missing, or admission rejection. A denied or stale decision cannot be broadened downstream.

## Legacy/V2 port separation

`LanguageEvidenceAuthorizerV3` is the historical representation-pipeline port. Its `actor_id -> AuthorizationScopeV1 | None` shape remains unchanged for `RepresentationPipelineV1`; it is not a V2 retrieval authority. The clearer source name `RepresentationEvidenceAuthorizerV3` is an additive alias for that same legacy protocol.

`V2RetrievalAuthorizerV1` is the distinct V2 port. It consumes a server-derived `PrincipalContextV1` and the server-bound retrieval plan and returns `V2RetrievalAuthorizationDecisionV1`. A raw actor identifier cannot satisfy this port. The future server adapter must implement this port by composing `CentralAuthorizationServiceV1` with the governed V2 narrowing policy.

## Downstream implementation obligations

The future V2 authorizer must implement `V2RetrievalAuthorizerV1`. The authorized evidence store must accept only its bounded allow decision and enumerate only within it. ActiveV2GenerationInspector remains the authoritative source of active generation bindings.

## Downstream propagation amendment

The exact `V2RetrievalAuthorizationDecisionV1` instance issued for the operation is mandatory input to source enumeration, evidence resolution, shared reranker-candidate construction, and advanced-candidate projection. Those layers may validate and narrow the decision; they may not reconstruct it, exchange it for `actor_id` or `AuthorizationScopeV1`, call `CentralAuthorizationServiceV1` again under different semantics, or omit it.

The candidate provenance field `authorization_scope_digest` is the decision fingerprint. `MultilingualV2RetrievalCandidate` retains the immutable decision so the advanced projector receives the same authorization object. Missing decisions fail at the typed boundary; scope or fingerprint mismatch fails closed before reranking or projection.
