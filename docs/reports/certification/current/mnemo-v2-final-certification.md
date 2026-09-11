# Mnemo V2 final production certification

**Date:** 2026-09-06

**Status:** `PRODUCTION_CERTIFICATION_PASS`
**Decision:** ADR-0076, accepted under `PROJECT_OWNER_GOVERNANCE_APPROVAL`

## Executive result

Mnemo V2 passed the amended, machine-verifiable engineering certification standard. The final durable production state is:

```text
V2_EXPOSED = TRUE
BGE_ACTIVE = TRUE
RERANKER_MODE = BGE_V2_M3
EVALUATED = TRUE
VERIFIED = TRUE
CERTIFIED = TRUE
```

The certification is scoped to the exact owner-operated 44-document production snapshot and governed model contract below. It does not claim independent human QREL adjudication, external organizational certification, Phase 8.6 production fitness, or identity equivalence to the historical 94.4% benchmark.

## Governance amendment

ADR-0076 additively amends ADR-0070 for this exact production snapshot while preserving the historical document. It replaces the unavailable 675-case research cohort, two independent human reviewers, and two external organizations with a frozen 18-query identity-bound engineering cohort, deterministic evidence-grounded identity QRELs, thresholds fixed before the fresh run, and two controlled clients exercising real HTTP/MCP transports and negative policy paths.

The amendment is bound to:

- store identity `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d`;
- store SHA-256 `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`;
- BGE revision `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`;
- pair policy `bge-reranker-v2-m3-pair-256-contextual-v1`;
- CUDA, batch 2, no CPU fallback, internal K=50; and
- the signed WP-17 evidence manifest.

## QREL policy and validation

The QREL pack is explicitly an engineering-certification artifact, not claimed human adjudication. Every query maps uniquely through manifest content hash to canonical document, version, source, and member chunk identities. It does not use filename/title equality, lexical similarity, embeddings, or reranker scores as the relevance rule.

Result: 18 total, 18 resolved, 0 ambiguous, 0 unresolved. QREL digest: `5891d37bd0fd8c757df5295501b18a4893f008c4865dd2b52d68c31e7c5c4833`.

## Fixed threshold contract

The project owner approved these floors before the fresh certification run:

| Metric | Floor | Observed | Result |
|---|---:|---:|---|
| R@1 | 0.7500 | 0.8333 | PASS |
| R@5 | 0.8500 | 0.8889 | PASS |
| R@10 | 0.8500 | 0.8889 | PASS |
| MRR | 0.7800 | 0.8474 | PASS |
| nDCG@10 | 0.8000 | 0.8548 | PASS |

The observed 83.3% result was not used to derive the floors. The historical 94.4% run was not used because it is not identity-equivalent.

## Fresh production-parity evaluation

- 18/18 targets uniquely resolved.
- 900 candidate/input pairs audited.
- Candidate coverage at K50: 17/18.
- Actual production V2 candidate builder and 44-document store used.
- Maximum governed pair length: 256 tokens with deterministic truncation.
- GPU: NVIDIA GeForce RTX 4060 Laptop GPU.
- PyTorch/CUDA: 2.13.0+cu130 / 13.0.
- Batch: 2; CPU fallback: disabled; OOM retries: 0.
- Peak allocated/reserved: 2,302,887,936 / 2,336,227,328 bytes.
- Historical ms-marco comparison: `BASELINE_NOT_IDENTITY_EQUIVALENT`; no superiority claim is made from it.

## Durable activation and restart

The server-owned durable authority uses authenticated operator access, an HMAC-authenticated record, atomic persistence, exact store/model/policy validation, and rejects corpus/FinalQA database paths. The executed sequence proved:

1. governed BGE activation;
2. restart reconstruction into `BGE_V2_M3`;
3. governed rollback;
4. restart reconstruction into `PASS_THROUGH`;
5. governed reactivation; and
6. final restart reconstruction into `BGE_V2_M3`.

The final durable desired state is BGE active.

## Active serving verification

Real HTTP FinalQA, MCP stdio, and MCP SSE calls all passed. All three produced the same ordered candidate identity digest: `058ec7361c965a5c5dfd7faafc5ca6deae2c384dcc85eaffef07c4c1975f1eee`.

Each transport proved BGE execution with the exact revision, CUDA, batch 2, 50 candidate scores, no CPU fallback, no PASS_THROUGH execution, and no outer ms-marco reranking. The final score digest is `ed3314d3cfb3d04b4c87c6bd330569bb770fffc1a0b4401aa9088bee55dd452a`.

Dynamic public `requested_k` remained separate from internal reranker K=50:

| requested_k | returned | internal K |
|---:|---:|---:|
| 1 | 1 | 50 |
| 5 | 5 | 50 |
| 10 | 10 | 50 |
| 25 | 25 | 50 |
| 50 | 50 | 50 |

## WP-16 security and behavior

Controlled Certification Client A exercised real HTTP and MCP stdio. Controlled Certification Client B exercised real MCP SSE and the negative-policy suite. They are controlled harnesses, not represented as external organizations.

Authenticated operator/principal propagation, anonymous HTTP rejection, invalid SSE authentication rejection, client override rejection, exact store/model/policy enforcement, no client activation surface, authorization/evidence provenance, operational-store separation, transport parity, dynamic-k, durable rollback, and lifecycle fail-closed behavior passed.

## Corpus and protected state

The production DB remained byte-identical before and after evaluation, activation, serving, rollback, reactivation, and certification:

- SHA-256: `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`
- size: 189,804,544 bytes
- 44 documents, 44 versions, 44 active source memberships, 2,658 chunks
- SQLite integrity: `ok`
- foreign-key violations: 0
- WAL: 0 bytes

The 67-document database remains evaluation-only. Golden and Phase 8.6 material, embeddings, FTS5, model snapshots, RRF, candidate construction, ContextBuilder 100/120 fail-hard contract, Gemma GPU configuration, and public dynamic-k behavior were not modified by the certification workflow. Mutable FinalQA state remained in its dedicated operational store.

## Lifecycle authority

`WP17CertificationAuthorityV1` consumed and digest-bound the amendment, owner approval, fresh evaluation, QREL pack, fixed thresholds, WP-16 evidence, activation, active-state proof, transport parity, security evidence, and rollback evidence. It produced signed certification state with signature:

`72d38e076b2980c8d5939490d87511a7a6c29e9de61cca3157ac3255bbdb5cf9`

Transitions actually performed: `EVALUATED`, `VERIFIED`, `CERTIFIED`.

## Validation

- Focused certification/security/activation/transport tests: 48 passed.
- Ruff: PASS.
- strict mypy: PASS.
- compileall: PASS.
- JSON validation: PASS.
- targeted diff check: PASS.

## Final status

`PRODUCTION_CERTIFICATION_PASS`

There are no remaining certification blockers under ADR-0076. Mnemo should remain on the governed durable BGE active state; operational monitoring and backup of the signed activation/certification records are the next routine actions, not another retrieval experiment.
