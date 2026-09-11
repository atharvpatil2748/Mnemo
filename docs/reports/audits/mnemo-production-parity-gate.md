# Mnemo Final Governance and Production-Parity Gate

**Date:** 2026-09-05  
**Final status:** `GOVERNANCE_BLOCKED`  
**Phase B:** not executed  
**BGE activation:** not attempted  
**V2 exposure:** not attempted

## 1. Executive decision

Phase A did not resolve all four mandatory gates:

```text
K50_GOVERNANCE_BLOCKED
BGE_EXECUTION_PROFILE_BLOCKED
V2_FINALQA_BRIDGE_BLOCKED
EXPOSURE_NOT_AUTHORIZED
```

The request requires Phase B to run only when all four outcomes are affirmative. It also states that “production finalization” is not implicit exposure authorization. No explicit `EXPOSURE_AUTHORIZED` decision is present, and the three prerequisite governance gates remain unresolved. The 44-document/256-token A/B, HTTP/MCP execution, and provider inference were therefore not launched.

## 2. A1 — production candidate K

**Decision:** `K50_GOVERNANCE_BLOCKED`

### Evidence assessed

- Corrected Phase 8.6 K=50 evaluation recovered six targets absent at K25 and improved pool coverage from 54/70 to 60/70. K100 recovered two more.
- Corrected Phase 8.5 Golden A/B used K50; 17/18 targets were present, while the remaining target appeared at K100 rank 96.
- Those experiments used the separate `forensic-v1` harness and the 67-document evaluation database, not the composed active 44-document V2 serving path.
- Public `EvidenceSearchRequest` defaults are `candidate_budget=100` and `evidence_budget=50`.
- The server cap is `max_advanced_candidate_budget=1000`.
- `RetrievalPlanV2` independently carries recall, fusion, rerank, and result limits; the rerank upper bound is 200.
- `FullMultilingualRetrievalApplicationV2` consumes those plan budgets. It does not define a production K50 invariant.

### Why evaluation evidence is insufficient to author a production contract

The phrase “candidate pool” is not a single current runtime field. K could mean dense/sparse recall depth, post-RRF fusion depth, pre-rerank depth, or returned evidence depth. Freezing “50” without selecting that stage and reconciling the other budgets would create policy rather than encode an existing one. The corrected evaluations also lack the required active-44-document/256-token serving parity.

### Minimum decision required

An accepted versioned budget contract must state:

1. `pre_rerank_candidate_pool = 50` (if that is the intended stage);
2. dense and sparse recall depths;
3. fusion depth and RRF policy;
4. result/evidence depth;
5. whether callers may reduce—but never increase—those values;
6. identical HTTP/MCP defaults and caps;
7. the configuration key and manifest fingerprint carrying the decision.

No runtime budget was changed.

## 3. A2 — BGE execution profile

**Decision:** `BGE_EXECUTION_PROFILE_BLOCKED`

### Current governed/code state

| Field | V2 candidate production profile | Corrected evaluation |
|---|---|---|
| Model | `BAAI/bge-reranker-v2-m3` | same |
| Revision | `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` | same |
| Certification | `candidate` | evaluation evidence |
| Device | hard-coded `cpu` | CUDA / RTX 4060 |
| Batch | 16 | 2 |
| Input ceiling | audited 256-token pair | model-native BGE 8,192 |
| Fallback | not a versioned profile field | no CPU fallback in evaluation |

The model-profile schema governs `max_batch` but not device, CUDA readiness, fallback behavior, memory limits, or OOM policy. Existing production code explicitly loads the CrossEncoder on CPU. The CUDA batch-2 evidence was obtained with much longer model-native pairs, so it demonstrates a safe evaluation configuration—not the complete production execution contract.

### Why neither CPU/16 nor CUDA/2 was silently selected

- Retaining CPU/16 would preserve current implementation but would not resolve the requested explicit governance or demonstrate operational latency/resource suitability.
- Selecting CUDA/2 would copy an evaluation deployment assumption into production and would alter profile/runtime identity without an accepted execution-profile contract.
- Recomputing profile fingerprints or generation bindings solely to accommodate either choice would affect the active governed runtime and is outside this pre-activation phase.

### Minimum decision required

A versioned execution profile must bind:

- device (`cpu` or required `cuda`);
- batch size;
- exact model snapshot/revision and offline cache;
- readiness probe and minimum device capability;
- no-fallback policy;
- CUDA OOM behavior if applicable;
- latency/memory acceptance limits;
- shutdown/resource release behavior;
- configuration and parity-evidence fingerprints.

No provider loader or model profile was changed.

## 4. A3 — V2 to FinalQA bridge

**Decision:** `V2_FINALQA_BRIDGE_BLOCKED`

This is not merely a missing result converter. The current contracts have an authorization-boundary mismatch.

### Current types and flow

```text
HTTP/MCP server principal
  -> EvidenceRetrievalApplicationService / FinalQAV2ApplicationService
  -> AdvancedRetrievalInterfaceV1.execute(plan)
  -> AdvancedRetrievalSourceV1.retrieve(plan, offset, limit)
  -> RetrievalResultSetV1
  -> candidates_from_retrieval
  -> MultimodalRetrievalResultV2
  -> FinalQARequestV2
  -> MultimodalContextBuilder
  -> grounded answer
```

`AdvancedRetrievalInterfaceV1.execute` and `AdvancedRetrievalSourceV1.retrieve` do not accept `PrincipalContextV1`.

The governed V2 path is intentionally different:

```text
PrincipalContextV1
  -> FullMultilingualRetrievalApplicationV2.retrieve
  -> V2RetrievalAuthorizationDecisionV1
  -> authorized enumeration/resolution/candidate construction
  -> MultilingualV2ApplicationResult
```

`FullMultilingualAdvancedSourceV2.retrieve` refuses ranked retrieval through the principal-less interface. Its ranked entry point is explicitly `retrieve_authorized(principal=..., plan=...)`. This protects the server-owned principal and authorization-before-enumeration invariant.

`FinalQAV2ApplicationService._retrieval_result` currently calls `KnowledgeEngine.advanced_retrieval.execute(plan)` without carrying the authenticated server principal into source retrieval. Merely registering `FullMultilingualAdvancedSourceV2` in that graph would therefore either fail or tempt a prohibited reconstruction from `RetrievalPlanV2.security_scope_identity`.

### Provenance and ContextBuilder requirements

The V2 candidate retains semantic text, source/document/version/evidence identity, authorization binding, generation lineage, representation lineage, vector-space identity, and database identity. FinalQA consumes `MultimodalRetrievalResultV2`; its candidate conversion must preserve all required fields and must not downgrade the bounded V2 authorization decision to a raw actor/scope string.

No existing approved bridge defines:

- a principal-aware shared retrieval service callable by both evidence retrieval and FinalQA;
- conversion of V2 candidates to the FinalQA multimodal evidence model;
- coexistence/deduplication between V2 multilingual text and existing OCR/Vision/CLIP candidates;
- completeness/omission mapping;
- transport-safe error behavior;
- snapshot identity covering the authorization/runtime binding.

### Minimum remediation required

Approve an additive principal-aware application interface owned by the server, conceptually:

```text
execute_authorized(principal, plan) -> RetrievalResultSetV2 (or approved existing type)
```

Both HTTP evidence retrieval and FinalQA must call this same service. It must invoke the composed V2 application directly, preserve the bounded decision/provenance, merge any approved non-text modalities under one deterministic policy, and hand only verified evidence to ContextBuilder. V1 interfaces and behavior must remain unchanged.

No bridge code was added because its result and modality semantics are not currently governed.

## 5. A4 — exposure authorization

**Decision:** `EXPOSURE_NOT_AUTHORIZED`

The request specifies this sequence:

```text
K governed
 + BGE execution profile governed
 + V2->FinalQA bridge governed
 -> explicit exposure authorization
 -> startup registration
 -> serving-parity test
```

It further states that production-finalization wording is not implicit permission. This task contains no explicit `EXPOSURE_AUTHORIZED` directive. In addition, A1–A3 did not pass. Server startup and transport routing remain unchanged.

## 6. Actual production runtime graph

### HTTP evidence

```text
POST /v2/retrieval/evidence
 -> retrieval_v2 router
 -> EvidenceRetrievalApplicationService
 -> CentralAuthorizationServiceV1
 -> KnowledgeEngine.advanced_retrieval
 -> current canonical/projected sources
 -> response
```

### MCP evidence

```text
search_evidence
 -> MCP tool handler
 -> same EvidenceRetrievalApplicationService
 -> same current advanced-retrieval graph
```

### HTTP/MCP FinalQA

```text
POST /v2/notebooks/{id}/final-qa / run_final_qa_v2
 -> FinalQAV2ApplicationService
 -> CentralAuthorizationServiceV1(FINAL_QA)
 -> KnowledgeEngine.advanced_retrieval
 -> MultimodalRetrievalResultV2
 -> MultimodalContextBuilder
 -> LLMFinalQAV2Provider
```

### Internal V2

The server-owned assembler and registration objects can compose the active alias, database verifier, V2 authorizer, authorized stores, candidate builder/projector, BGE reranker, application, and advanced source. `mnemo_server.app` does not instantiate that registration, so the graph remains internal and unexposed.

## 7. Production corpus verification

The selected artifact remains the active 44-document Phase 8.5 V2 database:

| Property | Value |
|---|---:|
| Documents / versions / sources | 44 / 44 / 44 |
| Chunks / FTS rows | 2,658 / 2,658 |
| Physical SHA-256 | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` |
| Governed DB identity | `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d` |
| Active alias digest | `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` |

The 67-document evaluation database was not selected, merged, rebuilt, or modified.

## 8. Governed 256-token reranker contract

The existing V2 builder/provider path enforces:

- 256 total pair tokens, including special tokens;
- maximum 96 query content tokens;
- deterministic query prefix followed by document prefix within the remaining budget;
- actual semantic evidence, not filename/title-only text;
- frozen input IDs/masks and an input hash;
- query/model/revision/preprocessing/provider-configuration audit;
- provider-side reconstruction and hash equality before scoring;
- no second tokenizer truncation.

Focused contract tests pass. The production-parity A/B under this contract was **not** run because Phase A failed.

## 9. Production BGE execution verification

Not run. Running BGE now would require selecting an ungoverned execution profile. No CPU or CUDA provider inference occurred.

## 10. HTTP end-to-end evidence

No V2 HTTP end-to-end request was run. The current endpoint does not reach the internal V2 application, and exposure was not authorized.

## 11. MCP end-to-end evidence

No V2 MCP end-to-end request was run for the same reason. Existing HTTP/MCP service-sharing tests are not mislabeled as V2 serving-parity evidence.

## 12. HTTP/MCP parity

Current transports share `EvidenceRetrievalApplicationService` and `FinalQAV2ApplicationService`, but both share the legacy advanced-retrieval implementation rather than the composed V2 path. Semantic V2 parity therefore remains unproven.

## 13. Authorization validation

Existing focused tests establish the internal V2 invariants:

- server-owned principal required;
- CentralAuthorizationServiceV1 composed with the V2 policy;
- bounded V2 decision precedes enumeration;
- alias/generation/profile/vector-space/database scope is non-expandable;
- missing or mismatched authorization fails closed.

The unresolved bridge is precisely why this evidence cannot yet be extended to the external FinalQA path.

## 14. ContextBuilder validation

ADR-0043 remains restored and unchanged:

```text
target = 100
hard/provider maximum = 120
registered-provider validation failures = fail hard
provider absence alone = graceful omission
```

Results retained from the immediately preceding remediation:

- ContextBuilder: 34 passed, 0 failed;
- combined focused V2/server/security suite: 87 passed, 0 failed;
- Ruff, strict mypy, compileall, JSON validation, and targeted diff check: PASS.

The unrelated pre-existing whitespace finding at `mnemo-core/mnemo/models/chunks.py:65` was not modified.

## 15. Protected-state validation

No production source/configuration, database, alias, model, corpus, index, or historical evaluation artifact was changed.

| State | Evidence/result |
|---|---|
| Active V2 DB | SHA-256 `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`; unchanged |
| Governed DB identity | `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d`; unchanged |
| Active alias | `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0`; unchanged |
| 67-document DB | prior verified SHA-256 `dc9e7fa2d1cb77f0e42ec3220377f74b1e2f98842acbfe487d1c7e6502fb2ada`; not used |
| Phase 8.5 corpus tree | `77ba2eca242c8d7486e87e1c5f08b554494785c795d3c93abaa4c2c3aa282e5b`; unchanged |
| Phase 8.6 corpus tree | `137e14f24f99fa415fc36bc38d363ca2329a74c2fc9c92933d192f638d96e0d4`; unchanged |
| `mnemo.toml` | SHA-256 `7d94649efe9540eac1abfc197769c0875f48161d4c9ec191b73560e97d499083`; unchanged |
| Provider inference/evaluation | not run |
| Exposure/activation | not attempted |

## 16. Rollback readiness

- `mnemo.toml` retains `cross-encoder/ms-marco-MiniLM-L6-v2`.
- ms-marco and BGE model evidence was not deleted or changed.
- historical Phase 8.5/8.6 A/B artifacts remain intact.
- no activation occurred, so no rollback execution was required.

A future activation plan must snapshot the exact production configuration and alias, perform an atomic controlled activation, run post-activation HTTP/MCP/security tests, and restore the snapshot on failure.

## 17. Remaining certification blockers

1. Accepted production budget/K contract.
2. Accepted BGE execution profile.
3. Accepted principal-aware shared V2 retrieval/FinalQA bridge.
4. Explicit exposure authorization.
5. Active-44-document, identity-bound, 256-token production-contract A/B.
6. Actual HTTP/MCP candidate, score, evidence, ContextBuilder, and answer parity.
7. Production multilingual and governed multimodal smoke tests.
8. Controlled BGE activation and post-activation verification.
9. Rollback execution proof.
10. Separate final certification decision.

## 18. Final status

```text
GOVERNANCE_BLOCKED
```

This is a required fail-closed stop. It does not reverse the successful ContextBuilder remediation or the existing internal V2 adapter validation. It prevents ungoverned K/device/bridge choices and unauthorized exposure from being presented as production parity.
