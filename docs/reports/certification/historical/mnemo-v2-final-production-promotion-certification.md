# Mnemo V2 final production promotion and certification gate

**Date:** 2026-09-06  
**Status:** `PRODUCTION_PROMOTION_BLOCKED`  
**First failed gate:** `PRE_PROMOTION_AUDIT`  
**Failure code:** `LIFECYCLE_CERTIFICATION_GATE_MISSING`

## Executive determination

The requested lasting BGE activation was **not executed**. The repository's
accepted governance does not permit the current 18-query production-parity run
to advance `EVALUATED`, `VERIFIED`, or `CERTIFIED`, and no superseding decision
or server-owned lifecycle-certification authority exists.

Failing closed before activation is required by the task: it explicitly says to
stop during the pre-promotion audit if any certification gate is missing.

There is a second independent blocker to a truthful lasting promotion. The
existing `RerankerActivationAuthorityV1` activates only the in-memory router
owned by one server process. Normal HTTP/MCP startup creates a fresh
`PASS_THROUGH` router, and neither normal startup nor the MCP CLI resolves a
durable governed activation intent/evidence record. Consequently, using the
authority now would prove another temporary activation, not establish a lasting
production state.

## A. Final promotion status

`PRODUCTION_PROMOTION_BLOCKED`

No activation was attempted. No aliases, JSON lifecycle fields, database flags,
or router internals were edited.

## B. Pre-promotion state

| Item | Observed value |
|---|---|
| V2 exposure | true |
| Reranker mode | `PASS_THROUGH` |
| BGE active | false |
| Production manifest BGE activation | false |
| Profile certification | `candidate` |
| Profile certification evidence | empty |
| Lifecycle | DECLARED through EXPOSED true; EVALUATED/VERIFIED/CERTIFIED false |
| Active alias-set digest | `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` |

## C. Post-promotion state

No promotion occurred. The state remains:

```text
V2_EXPOSED = TRUE
RERANKER_MODE = PASS_THROUGH
BGE_ACTIVE = FALSE
```

## D. Exact BGE contract retained

- Model: `BAAI/bge-reranker-v2-m3`
- Revision: `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`
- Pair policy: `bge-reranker-v2-m3-pair-256-contextual-v1`
- Device: CUDA
- Batch size: 2
- CPU fallback: false
- Internal fused reranker pool: 50

These values were not changed.

## E. Activation authority audit

`RerankerActivationAuthorityV1.activate` is a real, tested authority for one
composed runtime. It validates exposure, evaluation evidence, store identity,
candidate builder, model/revision, pair policy, CUDA, batch 2, and no fallback,
then installs a model into `GovernedV2RerankerRouterV1`.

It does **not** persist an activation decision. The router begins in
`PASS_THROUGH` in its constructor. Production startup constructs that fresh
router and only activates it when an optional in-memory
`reranker_activation_evidence` argument is supplied. The standard application
and MCP CLI do not own or resolve such durable evidence. Shutdown rolls the
router back while closing it.

Therefore the authority is sufficient for the already-completed controlled
activation/rollback verification, but not for the requested lasting promotion.

## F–J. Active-state transports and dynamic k

Not executed after the blocking pre-promotion gate:

| Gate | Result |
|---|---|
| HTTP active-state smoke | NOT EXECUTED |
| MCP stdio active-state smoke | NOT EXECUTED |
| MCP SSE active-state smoke | NOT EXECUTED |
| Active transport parity | NOT EXECUTED |
| Dynamic-k regression | NOT EXECUTED |

The earlier controlled activation report remains valid historical evidence; it
was not reused as proof of a new lasting active state.

## K. BGE CUDA/execution proof

The prior controlled activation/rollback artifact proves the exact BGE revision,
CUDA, batch 2, no CPU fallback, 50 scores, and no outer ms-marco for the tested
processes. No new inference was run because the pre-promotion audit failed.

## L. Authorization and evidence

No authorization or evidence boundary was changed. The authoritative path
remains server-derived principal to `CentralAuthorizationServiceV1` to
`CentralV2RetrievalAuthorizerV1`, with evidence resolved against the governed
44-document production store.

## M. FinalQA operational store

The operational-store separation was not changed. FinalQA execution state
remains separate from the immutable production corpus store.

## N. Production corpus before/after

No runtime mutation was attempted, so before and after are identical:

| Property | Value |
|---|---|
| Path | `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db` |
| Governed identity | `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d` |
| SHA-256 | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` |
| Size | 189,804,544 bytes |
| Documents / versions / memberships / chunks | 44 / 44 / 44 / 2,658 |
| SQLite integrity | ok |
| Foreign-key violations | 0 |
| WAL | 0 bytes |

The 67-document database was not used.

## O. Protected state

The audit was read-only except for its new evidence/report files. It did not
touch the corpus, embeddings, FTS5, Golden Dataset, Phase 8.6 data, models,
aliases, ContextBuilder, pair policy, candidate construction, or public `k`.

## P. Lifecycle transitions performed

None.

The lifecycle implementation has no `EVALUATED` stage at all; its ordered enum
is `DECLARED → CONFIGURED → BUILDABLE → READY → ACTIVE → EXPOSED → VERIFIED →
CERTIFIED`. Runtime verification/certification is derived from typed service
registration evidence, while the production profile remains `candidate` with
an empty certification-evidence list. No persistence/approval authority was
found that could lawfully populate those fields for this deployment.

## Q. Current truthful lifecycle

```text
DECLARED:    PASS
IMPLEMENTED: PASS
CONFIGURED:  PASS
BUILDABLE:   PASS
READY:       PASS
ACTIVE:      PASS
EXPOSED:     PASS
EVALUATED:   FALSE
VERIFIED:    FALSE
CERTIFIED:   FALSE
```

## R. Exact blocker

### First blocker: `LIFECYCLE_CERTIFICATION_GATE_MISSING`

The accepted post-evaluation determination explicitly rules that the 18-query
cohort is a smoke/model-selection cohort and cannot establish lifecycle
`EVALUATED`. It identifies these missing prerequisites:

1. governed directional cohorts meeting the approved sample-size floor;
2. adjudicated evidence-level QRELs rather than document-title/document-level
   relevance alone;
3. formal threshold/governance approval;
4. WP-16 behavioral verification for the supported transports/clients;
5. WP-17 full quality, security, live-protocol, protected-state, and final
   approval evidence.

ADR-0074 additionally requires deterministic behavior **and security** evidence
for the exact deployment snapshot before VERIFIED, and ADR-0070 approval for
the exact profile, generation, hardware/trust scope, and corpus/evaluation
version before CERTIFIED.

### Secondary blocker: `DURABLE_BGE_ACTIVATION_AUTHORITY_MISSING`

The existing authority has process-local effects only. Standard production
restart returns to PASS_THROUGH. A governed, server-startup-owned durable
activation intent/evidence record and rollback binding are absent.

## S. Artifacts

- `scratch/mnemo-v2-final-production-promotion-certification.json`
- `scratch/mnemo-v2-final-production-pre-state.json`
- `scratch/mnemo-v2-final-production-active-state.json`
- `scratch/mnemo-v2-final-production-transport-parity.json`
- `scratch/mnemo-v2-final-production-lifecycle.json`
- `scratch/audit_final_production_promotion_gate.py`
- `docs/reports/certification/historical/mnemo-v2-final-production-promotion-certification.md`

## T. Recommended next action

Perform one governance remediation gate, not activation:

1. complete/approve the ADR-0070 and WP-16 behavioral/security evaluation
   evidence required by the accepted plan;
2. implement the WP-17 lifecycle-certification authority that binds those
   artifacts to the exact production snapshot; and
3. add a durable, startup-owned reranker activation intent/evidence record that
   `RerankerActivationAuthorityV1` validates on every HTTP/MCP process startup.

Only then retry lasting activation and active-state transport verification.

## Authoritative evidence used

- `docs/adr/active/ADR-0070-phase-8-5-evaluation-and-certification-governance.md`
- `docs/adr/active/ADR-0074-phase-8-5-runtime-and-profile-activation.md`
- `docs/governance/historical/PHASE_8_5_COMPLETE_IMPLEMENTATION_PLAN.md`
- `docs/governance/proposals/phase8_5_full_multilingual_architecture/V2_POST_EVALUATION_DETERMINATION_AUDIT.md`
- `config/model_profiles/full_multilingual_v2_profiles.toml`
- `config/production/full_multilingual_v2.production.json`
- `mnemo-core/mnemo/phase85/models.py`
- `mnemo-core/mnemo/phase85/runtime.py`
- `mnemo-server/mnemo_server/services/v2_reranker_lifecycle.py`
- `mnemo-server/mnemo_server/services/full_multilingual_v2_startup.py`
- `mnemo-server/mnemo_server/app.py`
- `mnemo-server/mnemo_server/mcp/cli.py`

