# Mnemo V2 Exposure / BGE Separation Certification

**Date:** 2026-09-05  
**Status:** `PRODUCTION_CERTIFICATION_BLOCKED`  
**Failed gate:** `PRODUCTION_STARTUP_EXPOSURE_BLOCKED`  
**Blocker:** `V2_EXPOSURE_RERANKER_CONTRACT_UNDEFINED`  
**Highest truthful lifecycle:** `ACTIVE`

## Executive finding

The requested intermediate state—V2 exposed while BGE remains inactive—cannot be
implemented from the current governed contracts without defining new ranking and
activation semantics.

This is not merely an installer refactor. `FullMultilingualRetrievalApplicationV2`
requires both a governed candidate builder and a V3 reranker. The only production
candidate-builder implementation is created by the BGE provider and is bound to its
tokenizer, model revision, preprocessing, and 256-token input audit. The only production
installer initializes that BGE provider before exposing V2. When V2 is exposed, the
engine deliberately disables its outer legacy ms-marco reranker.

The repository contains no inactive/pass-through V2 reranker contract, no alternative
pre-BGE candidate-builder contract, and no reranker-model alias/activation/rollback
state. Choosing any of those behaviors here would invent precisely the lifecycle and
ranking semantics this task says not to fabricate.

No exposure, model load, evaluation, alias operation, or rollback was attempted.

## Installer audit

| Question | Repository result |
|---|---|
| What installs V2? | `install_production_full_multilingual_v2()` |
| What loads BGE? | The same installer constructs BGE at line 154 and initializes it at line 161 |
| What activates BGE? | No distinct operation exists |
| What changes V2 generation aliases? | The existing four-generation activation path; it governs representation/language/embedding/vector generations, not the reranker |
| What exposes V2? | `KnowledgeEngine.install_exposed_full_multilingual_v2()` |
| What rolls back the reranker? | No distinct operation exists |

The production manifest independently represents `v2_transport_exposed=false` and
`bge_reranker_activated=false`, but the runtime has no authority implementing the latter
state transition.

## Why a simple provider split is insufficient

The V2 application constructor requires:

```text
RerankerCandidateBuilderProtocolV1
MultilingualCandidateRerankerV3
```

It admits `reranking` as an operation, builds governed candidates, and invokes
`score_candidates()`. If scoring fails, the implementation can retain fused ordering
and mark the result partial; however, even reaching that fallback requires a candidate
builder. The production candidate builder is provided by
`BGEMultilingualReranker.candidate_builder()` and freezes BGE-specific tokenizer/model
identity into every input audit.

Creating a generic builder or a reranker that intentionally raises `LookupError` would
define a new exposed-production ranking contract. Neither behavior is present in the
manifest or an ADR. Reusing the outer ms-marco path is also prohibited: the engine
explicitly passes no `CanonicalAdvancedReranker` when V2 is exposed
(`mnemo-core/mnemo/engine.py:708`).

## Production-owned readiness finding

The same audit reconfirmed that production has no builder for `V2ReadinessInputs`.
The only construction is in a unit test. The governed readiness type requires concrete
transport-schema digests, stdio/SSE verification, parity verification, shared-path
verification, and a security-gate decision. Existing store readiness proves the common
44-document identity but does not define the authoritative artifact behind each
transport evidence value.

Hard-coding those values or hashing convenient files would fabricate readiness rather
than derive it.

## Unsafe approaches rejected

- Calling BGE model initialization during exposure and labelling it “inactive.”
- Introducing an undocumented fusion-only/pass-through production reranker.
- Re-enabling the legacy outer ms-marco reranker under exposed V2.
- Binding reranker activation to the unrelated four-generation index alias.
- Treating unit-test booleans as production transport evidence.
- Loading the 67-document evaluation database.

## Gate state

| Gate | Result |
|---|---|
| 44-document store authority | PASS |
| Authenticated MCP principal | PASS (prior remediation, 84 focused tests) |
| Production readiness builder | BLOCKED: transport evidence authority absent |
| V2 exposure/BGE separation | BLOCKED: pre-BGE reranker contract absent |
| V2 exposure | Not executed |
| HTTP E2E | Not executed |
| MCP stdio E2E | Not executed |
| MCP SSE E2E | Not executed |
| HTTP/MCP parity | Not executed |
| Production Golden evaluation | Not executed |
| BGE activation | Not executed |
| Post-activation verification | Not executed |
| Reranker rollback | Not executed |

## Protected state

- Production DB: `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db`
- Governed identity:
  `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d`
- Physical SHA-256:
  `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`
- Counts: 44 documents, 44 versions, 44 sources, 2,658 chunks.
- WAL: 0 bytes; SHM: 32,768 bytes.
- V2 transport remains unexposed.
- BGE remains inactive and unloaded.
- Active V2 index-generation alias remains unchanged.
- The 67-document database remains evaluation-only.
- Golden and Phase 8.6 data were not accessed or modified by this audit.

## Minimum decision required

One focused governance decision must specify all of the following before code can safely
implement the separation:

1. the exact reranking behavior for exposed V2 before BGE activation;
2. its candidate-builder, tokenizer, preprocessing, pair, and input-audit identity;
3. whether fused-order fallback is an acceptable production state and how completeness
   is reported;
4. a versioned reranker activation record/alias independent of index generations;
5. the previous-state snapshot and deterministic rollback transition; and
6. the immutable artifacts that provide each transport-readiness digest and verification
   decision.

Once accepted, the smallest implementation is an atomic reranker slot owned by the
server composition root, plus a production readiness-evidence loader. Exposure can then
install the explicitly governed pre-activation slot without loading BGE; activation can
swap that slot only after evaluation and retain its prior state for rollback.

## Final lifecycle

```text
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
```

The system remains in its highest verified safe state. No rollback was required.
