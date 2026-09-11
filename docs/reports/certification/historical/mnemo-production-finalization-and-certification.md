# Mnemo production finalization and certification

**Date:** 2026-09-05  
**Repository revision:** `31cdfb179a15fd96153071373641d24af0b815ed`  
**Decision:** `CERTIFICATION_BLOCKED`  
**BGE activated:** No

## Executive result

This pass reconciled the implementable production contracts but did not manufacture missing exposure evidence. The active 44-document V2 generation remains unchanged and unexposed. BGE remains the selected production candidate, not the active public reranker.

The exact blocker is a same-store/exposure prerequisite. The configured `mnemo.toml` engine uses `data/canonical_production/mnemo_canonical.db` (67 documents; notebooks `8585…` and `8686…`), while the active governed V2 runtime uses `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db` (44 documents; notebook `df9c…`). `CentralAuthorizationServiceV1` authorizes notebook existence through the engine store. Installing the V2 source into the currently configured engine would therefore deny every active-V2 request. Joining the stores or copying notebook membership would invent authorization semantics.

The repository also has no current `V2ReadinessSnapshot` with `v2_exposed=true` binding the active four-generation set to actual HTTP/MCP parity evidence. The new installation hook rejects activation-only or fabricated readiness.

## Reconciled contracts

| Contract | Final decision | Implementation |
|---|---|---|
| Production corpus | Existing 44-document Phase 8.5 V2 artifact | No corpus/database rebuild or mutation |
| Candidate K | 50 fused candidates entering reranking | `ServerConfig.production_rerank_candidate_limit`; `EvidenceSearchRequest.to_plan(max_rerank_candidates=...)` |
| Fusion | Existing reciprocal-rank fusion, k=60 | Unchanged |
| Reranker | BGE-reranker-v2-m3, revision `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` | Selected but not activated |
| Pair policy | `bge-reranker-v2-m3-pair-256-contextual-v1`; audited 256-token pair | Existing governed builder/runtime retained |
| Execution | CUDA, batch 2, no device fallback | Immutable `BGE_RERANKER_PRODUCTION_EXECUTION_V1` |
| ContextBuilder | ADR-0043: target 100, hard/provider max 120, fail hard | Unchanged; focused tests pass |
| Authorization | Server principal → central authorization → bounded V2 decision | Principal-aware retrieval interface added |
| FinalQA bridge | Principal preserved through retrieval before ContextBuilder/FinalQA | Production-mode branch implemented |
| Exposure | Requires authenticated production mode, explicit local cache, and `v2_exposed` readiness | Not activated because evidence is absent |

The profile's `max_batch=16` is the model capability ceiling bound into the active generation fingerprint. The production execution batch of 2 is a smaller runtime policy and does not change that identity.

## Implemented production boundaries

1. `PrincipalAwareAdvancedRetrievalSourceV2` and `PrincipalAwareAdvancedRetrievalInterfaceV2` carry `PrincipalContextV1` without reintroducing raw actor/scope authorization.
2. `AdvancedRetrievalService.execute_authorized` invokes `retrieve_authorized` for the governed V2 source. Its legacy `execute` path cannot successfully reach that source.
3. `EvidenceRetrievalApplicationService` requires authenticated principal-aware retrieval in `production_mode`; non-production/V1 compatibility is unchanged.
4. `FinalQAV2ApplicationService` has the same production-only principal-aware bridge before ContextBuilder and FinalQA.
5. `KnowledgeEngine.install_exposed_full_multilingual_v2` installs only a server-composed source accompanied by an actually exposed readiness snapshot. It recomposes the shared graph and disables legacy outer reranking so V2 results are not reranked twice.
6. `full_multilingual_v2_startup.py` dynamically resolves the alias, verifies database/profile/vector/generation bindings, initializes exact local providers, composes through the server-owned registration root, and requires supplied exposure evidence. It does not fabricate readiness.

## Intended final path (not active)

```text
HTTP / MCP
  -> server-derived authenticated PrincipalContextV1
  -> shared retrieval / FinalQA application services
  -> AdvancedRetrievalService.execute_authorized
  -> FullMultilingualAdvancedSourceV2.retrieve_authorized
  -> CentralV2RetrievalAuthorizerV1
  -> active four-generation V2 set (44-document store)
  -> BGE-M3 + FTS5 -> RRF(k=60)
  -> K=50 governed candidate stage
  -> audited 256-token contextual BGE reranker (CUDA, batch 2, no fallback)
  -> authorized evidence -> ContextBuilder -> FinalQA
```

This path is buildable, but it is not registered in `app.py` because the required same-store production configuration and truthful exposure snapshot do not yet exist.

## Model identities and rollback

- Embedding: `BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`, 1024 dimensions.
- Candidate reranker: `BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`.
- ms-marco artifacts/configuration remain intact as rollback evidence. No rollback execution was needed because activation did not occur.
- The multimodal stack was not changed.

## Evaluation evidence

Historical corrected identity-bound evidence remains unchanged:

| Dataset | Reranker | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---|---:|---:|---:|---:|---:|
| Phase 8.5, N=18 | ms-marco | 0.389 | 0.611 | 0.722 | 0.501 | 0.546 |
| Phase 8.5, N=18 | BGE | 0.944 | 0.944 | 0.944 | 0.944 | 0.944 |
| Phase 8.6, N=70 | ms-marco | 0.243 | 0.400 | 0.657 | 0.349 | 0.410 |
| Phase 8.6, N=70 | BGE | 0.329 | 0.600 | 0.714 | 0.448 | 0.505 |

No production-parity A/B was run because it would not traverse a valid same-store exposed path. The eight Phase 8.6 regressions (`DQ16`, `DQ22`, `DQ23`, `DQ37`, `DQ39`, `DQ51`, `DQ56`, `DQ64`) remain historical evidence with no newly established causal explanation.

## Validation

- Focused production/security/retrieval/ContextBuilder/transport suite: **128 passed**.
- Ruff on all touched production/test files: **PASS**.
- Strict mypy on the new startup and principal-aware server bridges: **PASS**.
- Compileall for core/server: **PASS**.
- Targeted `git diff --check`: **PASS**.
- Repository-wide strict mypy reports three unrelated pre-existing errors in `reranker_candidates.py`, `v2_production_adapters.py`, and `engine.py` provider-union inference.
- Repository-wide diff retains the documented unrelated whitespace issue in `mnemo-core/mnemo/models/chunks.py:65`.

## Protected state

- `mnemo.toml` unchanged: SHA-256 `7d94649efe9540eac1abfc197769c0875f48161d4c9ec191b73560e97d499083`.
- Active V2 DB unchanged: SHA-256 `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`; integrity `ok`; foreign-key violations 0.
- Active counts unchanged: 1 notebook, 44 documents, 44 versions, 44 sources, 2,658 chunks.
- Active alias unchanged: `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0`.
- Database identity manifest unchanged: SHA-256 `5ad46ad68b74f3fdff451ea0de2c128f5edffd762e6c3b843c2a2d288bb03dc9`.
- The locked canonical 67-document DB was queried read-only for notebook identity and not modified.
- No corpus, generation, alias, embedding, FTS, model, relevance label, or historical evaluation artifact was changed. No inference or benchmark was run.

## Exact blocker and next gate

Certification may resume only after a governed production configuration makes the engine authorization store the active 44-document store without copying identities, and a truthful pre-exposure `V2ReadinessSnapshot` is generated for that same composition. Then startup may install the source and run actual authenticated HTTP/MCP parity, production-contract A/B, multilingual/multimodal/FinalQA smoke tests, BGE activation, and rollback verification.

## Lifecycle

```text
DECLARED:    PASS
IMPLEMENTED: PASS
CONFIGURED:  PASS
BUILDABLE:   PASS
READY:       PASS
ACTIVE:      PASS
EXPOSED:     FALSE
EVALUATED:   FALSE
VERIFIED:    FALSE
CERTIFIED:   FALSE
```

## Final decision

`CERTIFICATION_BLOCKED`
