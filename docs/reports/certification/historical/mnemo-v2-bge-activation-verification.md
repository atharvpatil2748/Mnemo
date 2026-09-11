# Mnemo V2 Controlled BGE Activation Verification

**Date:** 2026-09-06  
**Status:** `BGE_ACTIVATION_AND_ROLLBACK_VERIFIED`  
**Final safe state:** `PASS_THROUGH`, `BGE_ACTIVE = FALSE`

## Scope and result

The already-evaluated production BGE configuration was activated through the existing server-owned `RerankerActivationAuthorityV1`, exercised through real HTTP, MCP stdio, and MCP SSE transports, and rolled back through `RerankerActivationAuthorityV1.rollback`.

This was activation verification, not another model-selection experiment. Candidate construction, RRF, internal K=50, public requested-k semantics, the 256-token pair policy, corpus content, and model revisions were not changed.

## Pre-activation state

- Reranker mode: `PASS_THROUGH`
- BGE active: false
- Production store governed identity: `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d`
- Production DB SHA-256: `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`
- Alias-set digest: `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0`
- Production configuration digest: `231459d96a047d91601c81fb63032f6b00c01e16faa427c972c74c32e81bd8da`
- Readiness evidence digest: `62869a0b2f8c33168793e9cf1b367d09a62d5e803df5ab0576f4044fe004c209`
- Production-evaluation evidence digest: `c489f49f9ba14df574653af7c68666e2b4a513f67643d5be3245bea038a3ea6d`

The activation evidence was accepted only after validating the completed production-parity evaluation, exposed V2 state, production-store identity, and unchanged production DB hash.

## Activation authority and contract

Activation used `RerankerActivationAuthorityV1.activate`; no alias, JSON state, database boolean, or router field was edited manually.

The recorded transition was:

- Previous mode: `PASS_THROUGH`
- Active mode: `BGE_V2_M3`
- Model: `BAAI/bge-reranker-v2-m3`
- Revision: `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`
- Candidate builder: `mnemo.v2-typed-candidate-builder/1`
- Pair policy: `bge-reranker-v2-m3-pair-256-contextual-v1`
- Device: `cuda`
- Batch size: 2
- CPU fallback: false

Each transport process invoked this same authority from the same immutable activation evidence. This is required because the router and loaded model are process-local; there was no second activation policy.

## Real transport results

The deterministic request was: “What does the Bhagavad Gita teach about duty and action?” Each transport completed persisted FinalQA using the separate operational store.

| Transport | Result | FinalQA latency | BGE scores | Device | Batch |
|---|---|---:|---:|---|---:|
| HTTP over TCP | PASS | 35.33 s | 50 | CUDA | 2 |
| MCP stdio client/server | PASS | 58.39 s | 50 | CUDA | 2 |
| MCP SSE over TCP | PASS | 21.83 s | 50 | CUDA | 2 |

For every transport, router execution evidence recorded:

- mode `BGE_V2_M3`;
- exact model and revision;
- 50 input candidates and 50 scores;
- a non-empty score digest;
- CUDA, batch 2, and no CPU fallback;
- a grounded FinalQA result with five authorized evidence candidates.

Legacy outer ms-marco and PASS_THROUGH execution were not used during the activated requests.

## Transport parity

HTTP, MCP stdio, and MCP SSE returned the same five document/version/chunk identities in the same order. Their common ordered candidate digest was:

`360fc7732bfd39b337dbfd0765f5a671167b7d6ad54c35462a85ad50a7f0a6d9`

All five results belong to document `f7a2cfb6-9742-56ab-9817-d20a5a7bce9d`, version `d16f586e-5a4d-5b5f-ae76-012b69263826`, in the authoritative 44-document store. Generated prose was not required to be byte-identical.

Transport parity: `PASS`.

## Dynamic requested-k

Real authenticated HTTP requests after activation verified that public requested-k remained dynamic while the internal reranker pool stayed at 50.

| requested_k | returned | internal reranker K |
|---:|---:|---:|
| 1 | 1 | 50 |
| 5 | 5 | 50 |
| 10 | 10 | 50 |
| 25 | 25 | 50 |
| 50 | 50 | 50 |

No public API field was fixed to 50.

## Rollback

Rollback used the real `RerankerActivationAuthorityV1.rollback` operation.

- Returned mode: `PASS_THROUGH`
- BGE active after rollback: false
- Activation record after rollback: absent
- Post-rollback HTTP status: 200
- Post-rollback returned results: 5
- Post-rollback router model: `v2-pass-through-reranker-v1`
- MCP stdio mode after shutdown rollback: `PASS_THROUGH`
- MCP SSE mode after shutdown rollback: `PASS_THROUGH`

The BGE delegates were closed during rollback. No manual state restoration was used.

## Production immutability

The production store was identical before and after activation, requests, and rollback.

- SHA-256 before/after: `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`
- Size: 189,804,544 bytes
- Documents: 44
- Versions: 44
- Source memberships: 44
- Chunks: 2,658
- Integrity check: `ok`
- Foreign-key violations: 0
- WAL before/after: 0 bytes

FinalQA wrote only to the governed operational store. The 67-document evaluation database did not enter production composition.

## Validation

- Real controlled activation/transport/rollback run: PASS (232.91 seconds)
- Focused and relevant tests: 92 passed
- Ruff: PASS
- Strict mypy: PASS
- Compileall: PASS
- Six machine-readable JSON artifacts: PASS
- Targeted `git diff --check`: PASS

Repository-wide `git diff --check` retains the previously documented unrelated trailing whitespace in `mnemo-core/mnemo/models/chunks.py:65`; this task did not modify that file.

## Lifecycle and remaining gate

Because this gate intentionally finished by rolling BGE back, the final state is:

- DECLARED through EXPOSED: PASS
- EVALUATED: FALSE
- VERIFIED: FALSE
- CERTIFIED: FALSE
- Reranker mode: `PASS_THROUGH`
- BGE active: false

The next single governed gate is final BGE production promotion/activation, followed by a final active-state smoke check and lifecycle certification under the existing governance rules.

