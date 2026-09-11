# ADR-0076: Project-owner engineering certification standard for Mnemo V2

- **Status:** Accepted
- **Date:** 2026-09-06
- **Authority:** `PROJECT_OWNER_GOVERNANCE_APPROVAL`
- **Amends:** ADR-0070 for the exact production deployment bound below
- **Supersedes:** No historical evidence or general ADR-0070 requirement

## Context

ADR-0070's proposed broad multilingual research certification requires 75
answerable cases in each of nine directions, two independent language-qualified
reviewers, adjudication, and two independent external clients. Those controls
remain appropriate for claims of externally adjudicated multilingual quality,
but are not reproducible prerequisites for this owner-operated local Mnemo V2
deployment.

The project owner, acting as designated governance authority, explicitly
approved an engineering certification standard based only on machine-verifiable
evidence that this repository can reproduce. This amendment does not claim
independent human review or external organizational validation.

## Exact scope

This decision applies only to:

- production store identity
  `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d`;
- production database SHA-256
  `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`;
- `BAAI/bge-reranker-v2-m3` revision
  `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`;
- pair policy `bge-reranker-v2-m3-pair-256-contextual-v1`;
- CUDA, batch size 2, with CPU fallback forbidden;
- exactly 50 fused candidates entering reranking; and
- dynamic public result depths 1, 5, 10, 25, and 50.

Any binding change invalidates certification and requires a new decision.

## Superseded requirements for this scope

| Original proposed requirement | Reason scoped out | Replacement |
|---|---|---|
| 75 cases in each of nine language directions | The 44-document private production corpus does not provide a non-fabricated 675-case certification set | The frozen 18-query production identity-bound cohort, with 18/18 unique target resolution |
| Two independent reviewers and third-party adjudication | No independent reviewer program exists for this owner-operated deployment | Deterministic engineering QRELs bound to declared query target, manifest hash, document, version, source, and all eligible chunks |
| Post-hoc independently derived floors | No independent adjudicated pack exists | Fixed engineering acceptance floors recorded before the fresh certification run |
| Two external client organizations | The deployment is local and no external-client program exists | Two named controlled certification harnesses using different real transport paths; they are never represented as external organizations |

## Engineering QREL contract

QRELs express deterministic target identity, not human semantic judgment. A
QREL is valid only when the frozen query target resolves through the governed
corpus census and content hash to exactly one production document/version,
at least one production source, and at least one chunk. Filename/title/model
scores are never relevance predicates. All chunks belonging to the resolved
document/version are relevant for this document-level engineering evaluation.

## Fixed acceptance floors

The owner approves these minimum engineering criteria before the fresh run:

- Recall@1 >= 0.75 (at least 14 of 18);
- Recall@5 >= 0.85 (at least 16 of 18);
- Recall@10 >= 0.85 (at least 16 of 18);
- MRR >= 0.78; and
- nDCG@10 >= 0.80.

These floors encode the engineering requirement that at least three quarters of
targets rank first and at least sixteen of eighteen remain discoverable by rank
five/ten. They are not derived by rounding the observed BGE result. All
zero-tolerance security, identity, CUDA, policy, parity, and immutability gates
must also pass.

## Controlled WP-16 clients

- `CONTROLLED_CERTIFICATION_CLIENT_A`: authenticated HTTP plus MCP stdio.
- `CONTROLLED_CERTIFICATION_CLIENT_B`: authenticated MCP SSE plus negative
  authorization/configuration probes.

Both use real server transports and the same production composition. They are
controlled harnesses, not independent humans or companies. Their retained
traces must prove principal handling, store identity, evidence provenance,
dynamic requested-k, internal K=50, FinalQA storage separation, exact BGE
execution, and fail-closed policy behavior.

## WP-17 authority

Certification is a typed evidence-manifest decision. The authority must validate
digests and semantic bindings for this ADR, approval, QRELs, thresholds,
evaluation, WP-16, activation/restart, parity, security, rollback/reactivation,
and final active state. It writes a signed, atomic operational lifecycle record
outside both corpus and FinalQA stores. No transport or client can invoke it.

`EVALUATED`, `VERIFIED`, and `CERTIFIED` become true only together with their
respective validated evidence. A missing, malformed, mismatched, or failed
artifact fails closed.

## Safety and rollback

The production corpus remains byte-identical. Activation and rollback use only
the durable server-owned authority. A successful certification ends with BGE
active after a verified rollback, restart, reactivation, and second restart.

## Non-claims

This certification is not an independently adjudicated multilingual research
benchmark, external-client certification, or proof for the 67-document Phase
8.6 evaluation database.
