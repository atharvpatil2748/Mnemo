# Mnemo Production V2 Remediation and Serving-Parity Validation

**Date:** 2026-09-05  
**Scope:** gated remediation before activation/certification  
**Production corpus:** `PRODUCTION_CORPUS_44_CONFIRMED`  
**Remediation status:** `PRODUCTION_REMEDIATION_BLOCKED`  
**Serving-parity status:** `SERVING_PARITY_BLOCKED`

## 1. Executive summary

The unambiguous ContextBuilder drift was removed and ADR-0043 is restored: target 100 tokens, hard/provider maximum 120 tokens, and fail-hard propagation for registered-provider, malformed-output, and input-window failures. The focused ContextBuilder suite now passes 34/34; the combined V2, authorization, reranker-contract, ContextBuilder, HTTP/MCP contract, and security suite passes 87/87.

The remaining production changes cannot safely be made from current repository authority:

1. K=50 is evaluation evidence, not a governed production candidate contract.
2. The V2 model profile remains `certification = "candidate"`, declares batch 16, and has no execution-device field. The provider implementation hard-codes CPU; CUDA/batch-2 belongs to the evaluation environment. Choosing either as the production execution profile would invent governance.
3. The internal V2 runtime has a server-owned assembler and registration port, but application startup does not register it. Publicly routing to it while `EXPOSED` must remain false would be an exposure/activation change prohibited in this phase until the preceding gates pass.
4. The 44-document active V2 runtime returns governed retrieval candidates. The existing Final-QA service consumes the legacy `KnowledgeEngine.advanced_retrieval` result. No approved production bridge currently binds Full Multilingual V2 results to the ContextBuilder/answer pipeline.
5. The corrected A/B evaluations did not use the governed 256-token audited pair contract. A 44-document production-contract reranker validation remains mandatory.

Consequently, no HTTP/MCP route, active alias, production configuration, database, model, index, or corpus was changed. Genuine serving-parity execution would currently test an ungoverned hybrid, so it was not run.

## 2. Final runtime graph observed

### HTTP evidence retrieval

```text
POST /v2/retrieval/evidence
  -> routers/retrieval_v2.search_evidence
  -> EvidenceRetrievalApplicationService.execute
  -> server-derived ServerPrincipalV1
  -> CentralAuthorizationServiceV1.authorize_notebook(RETRIEVE)
  -> KnowledgeEngine.advanced_retrieval.execute
  -> currently composed canonical/projected retrieval sources
  -> EvidenceSearchResponse
```

The service still places the actor UUID in `RetrievalPlanV2.security_scope_identity`. The production Full Multilingual V2 application does not trust that value: its ranked entry point requires a server-owned `PrincipalContextV1` and obtains a bounded `V2RetrievalAuthorizationDecisionV1` before enumeration. The public service does not currently call that entry point.

### MCP evidence retrieval

```text
search_evidence
  -> mcp/tools._handle_search_evidence
  -> EvidenceRetrievalApplicationService.execute
  -> exactly the same service path as HTTP
```

HTTP and MCP share their current service, but that shared service is not the composed Full Multilingual V2 application.

### HTTP and MCP Final-QA

```text
POST /v2/notebooks/{notebook_id}/final-qa
run_final_qa_v2
  -> FinalQAV2ApplicationService
  -> CentralAuthorizationServiceV1(FINAL_QA)
  -> KnowledgeEngine.advanced_retrieval
  -> MultimodalContextBuilder
  -> LLMFinalQAV2Provider
```

Both transports share `FinalQAV2ApplicationService`. Its retrieval input is still the existing advanced-retrieval result rather than a typed result from `FullMultilingualRetrievalApplicationV2`.

### Internal Full Multilingual V2

```text
ServerOwnedFullMultilingualV2RegistrationV1
  -> ProductionFullMultilingualV2ServerDependencyAssemblerV1
  -> active V2 alias and database identity verification
  -> CentralV2RetrievalAuthorizerV1
  -> bounded V2 decision
  -> authorized dense/sparse sources
  -> authorized evidence resolution
  -> governed candidate builder/projector
  -> BGEMultilingualReranker
  -> FullMultilingualRetrievalApplicationV2
  -> FullMultilingualAdvancedSourceV2
```

This graph is buildable and tested internally. It is not constructed by `mnemo_server.app` lifespan, not reachable through HTTP/MCP, and not exposed.

## 3. Production corpus proof

The authoritative production artifact remains:

| Property | Value |
|---|---:|
| Path | `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db` |
| Documents / versions / sources | 44 / 44 / 44 |
| Canonical chunks / FTS rows | 2,658 / 2,658 |
| V2 language-text / embedding rows | 3,019 / 3,019 |
| Physical SHA-256 | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` |
| Governed logical DB identity | `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d` |
| Active alias digest | `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` |
| SQLite integrity / FK violations | `ok` / 0 |

The 67-document canonical evaluation database was not selected, copied, merged, or modified.

## 4. Candidate-pool governance

**Decision:** `K50_PRODUCTION_BLOCKED`

K=50 has positive corrected A/B evidence, but the repository has no accepted production contract freezing it. Current authority is inconsistent by design:

- public request default `candidate_budget = 100`;
- public request default `evidence_budget = 50`;
- server cap `max_advanced_candidate_budget = 1000`;
- `RetrievalPlanV2` carries caller-derived recall/fusion/rerank/result budgets and permits reranking up to 200;
- the corrected A/B `forensic-v1` harness uses K=50;
- the Full Multilingual V2 application consumes plan budgets rather than defining K=50.

The missing decision must specify whether K means recall depth, fused pre-rerank depth, rerank depth, or returned evidence depth, and freeze compatible defaults/caps for both transports. ContextBuilder does not define retrieval K.

## 5. Reranker input contract

The governed production contract is already explicit and implemented:

- policy `bge-reranker-v2-m3-pair-256-v2`;
- maximum complete pair length 256 tokens including special tokens;
- query content maximum 96 tokens;
- document receives the remaining pair content budget;
- deterministic prefix truncation;
- exact token IDs, masks, pair hash, model identity/revision, preprocessing identity, and provider-configuration digest are audited;
- semantic evidence is mandatory; filename/metadata-only candidates do not satisfy the V2 candidate contract;
- `predict_candidates` rebuilds and verifies the frozen pair before scoring and performs no second tokenizer truncation.

The corrected Phase 8.5/8.6 A/B harness used raw CrossEncoder scoring at model-native maxima (BGE 8,192; ms-marco 512). It therefore does not establish performance parity for this production contract.

**Required validation:** generate one frozen identity-bound candidate pool from the 44-document active V2 artifact, build both A/B inputs through an equivalent governed 256-token pair algorithm, assert candidate/input equality, and compare rerankers without changing retrieval. This must precede BGE activation.

## 6. BGE production runtime

| Field | Current V2 candidate profile/runtime | Validated evaluation |
|---|---|---|
| Model | `BAAI/bge-reranker-v2-m3` | same |
| Revision | `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` | same |
| Certification | `candidate` | evaluation evidence only |
| Device | hard-coded CPU in provider loader | CUDA, RTX 4060 |
| Batch | 16 | 2 |
| Pair contract | governed 256-token audited pair | native maximum |

The profile schema contains `max_batch` but no device or CUDA failure-policy field. Existing production implementation is CPU/batch-16; existing memory evidence is CUDA/batch-2 under a different input contract. The repository does not establish which is intended production authority.

Minimum governance needed: a versioned execution profile binding device, batch size, model cache, no-fallback policy, readiness probe, OOM behavior, and configuration fingerprint. Only then should the adapter stop hard-coding CPU and consume that profile.

## 7. ContextBuilder contract restoration

ADR-0043 is unsuperseded and authoritative:

- compression target: 100 tokens;
- hard/provider maximum: 120 tokens;
- one sequential call per eligible chunk;
- provider absence alone degrades gracefully;
- malformed output, provider failure, invalid token count, or input-window failure propagates with no partial result;
- a valid compression that does not fit is omitted while traversal continues.

The seven failures were implementation-contract drift, not test defects:

| Failure group | Expected | Drifted behavior | Correction |
|---|---|---|---|
| Provider output budget | 120 | 300 | restored 120 |
| Compression hard maximum | 120 | 200 | restored 120 |
| 121-token output | governed `IntegrityError` | downstream model `ValueError` | hard check now rejects first |
| Empty/non-string/surrogate output | propagate | swallowed and omitted | propagation restored |
| Extra/missing structured fields | propagate | swallowed and omitted | propagation restored |
| Extractor context window | propagate | swallowed and omitted | propagation restored |

The working file now matches the Git baseline exactly; no residual production source diff remains. Validation: 34 passed, 0 failed.

## 8. HTTP/MCP serving parity

Genuine V2 serving parity was **not executed**. Doing so now would require at least one prohibited or ungoverned action: exposing/registering V2 at startup, selecting K semantics, selecting a BGE execution profile, or inventing a bridge into Final-QA.

Existing tests prove HTTP and MCP share their legacy service and that V2 authorization/adapters are internally coherent. They do not prove that a real external request traverses the active V2 application. This distinction is retained; unit-contract parity is not reported as end-to-end serving parity.

## 9. Production-parity retrieval, multilingual, and multimodal tests

These were not run because their prerequisites failed:

- production-parity retrieval: blocked by K and 256-token A/B gates;
- English/Hindi/Marathi production smoke: blocked because the V2 application is not registered in startup;
- OCR/Vision/CLIP production smoke: blocked for the same serving-path reason and because the current internal Full Multilingual V2 application is a multilingual-text path, not an approved replacement for existing multimodal source composition;
- grounded answer parity: blocked by the missing typed V2-retrieval-to-Final-QA bridge.

No empty or fake results are reported as smoke-test success.

## 10. Authorization proof

The target V2 stack has the correct server-owned security boundary:

```text
PrincipalContextV1
 -> CentralAuthorizationServiceV1
 -> CentralV2RetrievalAuthorizerV1
 -> V2RetrievalAuthorizationDecisionV1
 -> authorized enumeration/resolution/candidate construction
```

Focused tests confirm principal binding, authorization-before-enumeration, active-generation/database/vector-space binding, and fail-closed behavior. The current HTTP/MCP evidence service authorizes centrally but then calls the legacy advanced-retrieval graph. Therefore it cannot yet be claimed that HTTP/MCP cannot bypass all four V2 adapters; route-level V2 proof remains a gate.

## 11. Evaluation-versus-production parity matrix

| Component | Evaluation state | Production state | Match? | Required action |
|---|---|---|---:|---|
| Corpus | corrected A/B used 67-document evaluation DB | governed 44-document active V2 | No | rerun parity validation on 44 only |
| Database identity | canonical evaluation DB | governed V2 identity `0c6c…` | No | bind validation to active V2 artifact |
| Embeddings | BGE-M3, 1,024 dimensions | BGE-M3 V2 generations | Model only | verify exact revision/generation through runtime |
| FTS5 | forensic candidate protocol | authorized V2 language-text generation | No | use production source path |
| Candidate generation | `forensic-v1` | V2 dense+sparse RRF | No | use composed application |
| RRF | harness implementation | V2 RRF k=60 | Not proven | assert stage parity |
| Candidate K | 50 | not frozen | No | governance decision |
| Reranker | BGE candidate evaluated | active config remains ms-marco; V2 profile BGE is candidate | No | contract-parity A/B then controlled activation |
| Pair contract | model-native 8,192/512 | audited 256, query max96 | No | rerun A/B through governed pair contract |
| Device/batch | CUDA/2 | CPU/16 | No | govern execution profile |
| ContextBuilder | outside paired reranker metric | ADR-0043 restored | N/A | run after serving path exists |
| Answer generation | not part of corrected A/B | FinalQAV2 LLM provider | N/A | end-to-end authorized smoke |
| Authorization | harness-only identity binding | bounded server-owned V2 decision | No | use real transport principal and V2 route |
| HTTP | not used | legacy shared service | No | authorized startup/service registration |
| MCP | not used | same legacy shared service | No | route through same approved V2 service |
| Multimodal | not evaluated | separate projected multimodal sources | Unknown | governed representative smoke |
| Production model alias | unchanged | ms-marco | Yes/safe | retain until activation gate |
| Configuration | scratch CLI | `mnemo.toml` plus candidate V2 profile | No | approved manifest after all gates |
| Manifests | evaluation artifacts | active V2 build/alias manifests | No | create production manifest only after validation |

## 12. Rollback readiness

- `mnemo.toml` still selects `cross-encoder/ms-marco-MiniLM-L6-v2`.
- No reranker alias changed.
- No model artifact was deleted.
- Historical A/B, active V2, and corpus evidence remains present.
- A future controlled activation must capture the exact pre-activation config and alias record, activate atomically, run post-activation transport/security smoke tests, and restore the captured state on any failure.

No rollback was executed because no activation occurred.

## 13. Protected-state verification

| Artifact/state | Evidence | Result |
|---|---|---|
| Active 44-document V2 DB | physical SHA-256 `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | unchanged |
| Governed V2 DB identity | `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d` | unchanged |
| Active V2 alias | digest `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` | unchanged |
| 67-document canonical DB | prior verified SHA-256 `dc9e7fa2d1cb77f0e42ec3220377f74b1e2f98842acbfe487d1c7e6502fb2ada`; current Windows handle prevented a direct re-hash and was not forced | not accessed or modified by this task |
| Phase 8.5 corpus | tree digest `77ba2eca242c8d7486e87e1c5f08b554494785c795d3c93abaa4c2c3aa282e5b` | unchanged |
| Phase 8.6 corpus | tree digest `137e14f24f99fa415fc36bc38d363ca2329a74c2fc9c92933d192f638d96e0d4` | unchanged |
| Production config | `mnemo.toml` SHA-256 `7d94649efe9540eac1abfc197769c0875f48161d4c9ec191b73560e97d499083` | unchanged |
| ContextBuilder | no diff from Git baseline after drift removal | restored |
| Models/indexes | no commands wrote, rebuilt, downloaded, or inferred | unchanged |

The locked canonical DB was not copied, killed, or force-opened. No ingestion, embedding generation, indexing, provider inference, benchmark, alias promotion, or exposure occurred.

## 14. Validation

Focused command:

```text
.venv/Scripts/python.exe -m pytest -q --no-cov
  mnemo-core/tests/unit/test_v2_production_adapters.py
  mnemo-core/tests/unit/test_v2_authorization_boundary.py
  mnemo-core/tests/unit/test_contextual_reranker_contract.py
  mnemo-core/tests/unit/test_context_builder.py
  mnemo-server/tests/test_v2_production_adapters_registration.py
  mnemo-server/tests/test_v2_production_registration_contract.py
  mnemo-server/tests/test_retrieval_v2.py
  mnemo-server/tests/test_final_qa_v2_transport.py
  mnemo-server/tests/test_mcp_wp03_contracts.py
  mnemo-server/tests/test_wp14_security.py
```

Result: **87 passed, 0 failed**. ContextBuilder subset: **34 passed, 0 failed**.

Additional checks: focused Ruff PASS, strict mypy PASS, compileall PASS, JSON parse/assertions PASS, and `git diff --check` PASS for the files in this remediation. The repository-wide `git diff --check` still reports one pre-existing trailing-whitespace finding at `mnemo-core/mnemo/models/chunks.py:65`; that unrelated user-owned change was not modified.

No end-to-end V2 serving execution was attempted because it could not satisfy the unresolved production invariants.

## 15. Remaining gates

1. Approve a production budget contract, explicitly defining K at every retrieval stage.
2. Govern the BGE execution profile (device, batch, no-fallback/OOM policy, cache, fingerprint).
3. Run corrected paired reranker validation on the active 44-document V2 artifact through the exact audited 256-token pair contract.
4. Approve startup registration/exposure of the composed V2 runtime behind the existing shared HTTP/MCP service.
5. Define and test the typed bridge from V2 retrieval candidates into FinalQAV2 ContextBuilder input.
6. Run actual HTTP/MCP equality, authorization-negative, English/Hindi/Marathi, OCR/Vision/CLIP, ContextBuilder, and grounded-answer tests.
7. Create the authoritative production manifest from measured values, not assumptions.
8. Prepare and test controlled activation/rollback in a separate authorized phase.
9. Perform post-activation verification and only then make a separate certification decision.

## 16. Exact lifecycle

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

## 17. Decision

```text
PRODUCTION_REMEDIATION_BLOCKED
SERVING_PARITY_BLOCKED
```

The block is fail-closed, not a test failure: the unambiguous ContextBuilder defect is resolved, but the remaining changes require explicit governance and production-parity evidence that this task did not authorize us to invent.
