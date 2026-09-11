# Full Multilingual V2 — Production Evidence Adapters and Runtime Composition Report

**Result:** EVALUATED remains false. The requested five production adapters are blocked by a missing operation-scoped authorization contract.

## Executive finding

This is not merely missing wiring. LanguageEvidenceAuthorizerV3 accepts only actor_id and a source reference. It does not receive the requested retrieval operation, RetrievalScopeV2, positional scope, active alias/generation set, V2 profile/vector-space identity, or admission decision. The required production checks cannot therefore be performed through that contract before enumeration.

The present server authority, CentralAuthorizationServiceV1, accepts PrincipalContextV1, notebook, and operation. Its documented Phase 8.5 policy explicitly states that persistence has no actor-to-notebook ownership relation; it enforces existence and canonical notebook/document association. It is not an implementation of LanguageEvidenceAuthorizerV3, and the V3 interface cannot pass the security context it requires.

Creating an evaluator-only adapter, converting an actor UUID into an implicitly authenticated principal, enumerating V2 evidence first, or adding private evaluator SQL would violate the requested invariants.

## Repository evidence

| Required seam | Current state | Blocking reason |
| --- | --- | --- |
| LanguageEvidenceAuthorizerV3 | Protocol only | Signature lacks operation, scope, and active-set context. |
| AuthorizedMultilingualSourceEnumeratorV2 | Protocol only | Must authorize before enumeration, but the V3 authorizer cannot assess requested scope. |
| RerankerEvidenceResolverV1 | Protocol only | Needs a prior authorized scope plus canonical V2 evidence-to-semantic-text/provenance resolution. |
| V2AdvancedCandidateProjector | Protocol only | Needs the same authorized semantic-evidence path. |
| ActiveV2GenerationInspector | Protocol only | Can be implemented from manifests, but cannot safely make the runtime composable alone. |

Existing V2 storage methods correctly require an already authorized set of evidence references before FTS/vector enumeration. They intentionally do not create that set. This preserves authorization-before-enumeration, but the central production service which creates the set was never specified.

## What was not done

No authorization behavior was invented. No evaluator-side SQLite lookup, direct provider call, candidate construction, corpus query, model inference, V2 alias change, generation change, or evaluation execution occurred.

## Required contract resolution

A governed, versioned V2 retrieval-authorization request must bind at least:

- actor principal;
- requested operation;
- RetrievalScopeV2 and PositionalScopeV2;
- active V2 alias-set identity and generation identities;
- profile fingerprint and vector-space identity;
- admission-policy identity.

The central authorization service must return a bounded authorization decision that can safely reach the V2 source enumerator. It must also define how server ownership derives the actor principal and applies the current notebook-membership policy.

A separate governed V2 evidence-resolver contract must identify actual semantic text, representation reference, observations, transformation lineage, and active-generation provenance for each LanguageEvidenceReferenceV3. This is necessary for the reranker resolver and candidate projector. Title metadata remains metadata; it can never become semantic evidence.

## Lifecycle

DECLARED: PASS
IMPLEMENTED: PASS
CONFIGURED: PASS
BUILDABLE: PASS
READY: PASS
ACTIVE: PASS

EXPOSED: FALSE
EVALUATED: FALSE (BLOCKED: operation-scoped V2 authorization and evidence-resolution contracts are absent)
VERIFIED: FALSE
CERTIFIED: FALSE

## Exact next action

Approve the versioned V2 retrieval-authorization and authorized-evidence-resolution contracts. Only then can the concrete adapters be implemented without weakening authorization or creating evaluator-specific behavior.

