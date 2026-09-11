# Mnemo V2 Production Store Unification and Serving Readiness

**Date:** 2026-09-05  
**Scope:** Pre-exposure store unification only  
**Production store:** `PRODUCTION_STORE_UNIFIED`  
**Serving readiness:** `SERVING_READINESS_VALIDATED`  
**V2 exposed:** No  
**BGE activated:** No  
**Verified/certified:** No / No

## Executive summary

The repository's configured engine store now resolves to the existing governed
44-document Phase 8.5 V2 artifact. HTTP and MCP use one shared configuration resolver, and
the server-owned V2 assembler rejects composition unless the `KnowledgeEngine` SQLite path
equals the database path in the governed V2 identity manifest. This closes the former
44-document retrieval versus 67-document authorization split without copying or rebuilding
either database.

The generated pre-exposure readiness snapshot proves one governed logical database identity
for production corpus, retrieval, authorization, evidence resolution, HTTP, and MCP. It also
records `currently_exposed: false`. Consequently, this report establishes readiness for a
later controlled exposure; it is not evidence of a live HTTP/MCP V2 request and does not
advance EVALUATED, VERIFIED, or CERTIFIED.

## 1. Original store mismatch

Before this remediation, `mnemo.toml` selected
`data/canonical_production/mnemo_canonical.db` (67 documents) for the `KnowledgeEngine`.
`CentralAuthorizationServiceV1` authorizes notebook membership through
`KnowledgeEngine.storage`, while the server-owned Full Multilingual V2 assembler opens the
database selected by `V2_DATABASE_ARTIFACT_IDENTITY.json` (44 documents). That permitted an
invalid production composition in which authorization and V2 retrieval did not share a
corpus identity.

The 67-document database remains intact and evaluation-only. Its last independently verified
SHA-256 is `dc9e7fa2d1cb77f0e42ec3220377f74b1e2f98842acbfe487d1c7e6502fb2ada`.
It remained open by another process during this task, so it was not force-locked, copied,
or re-hashed.

## 2. Authoritative 44-document production store

| Property | Verified value |
|---|---|
| Path | `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db` |
| Physical SHA-256 | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` |
| Governed logical database identity | `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d` |
| Database ID | `b8b855c4-98b3-5f35-bc91-92cf693e507d` |
| Build run | `0b04f05c-a3d5-5879-b878-cd5f8e84ff2f` |
| Corpus digest | `e086e48dda72b9bc38f6cb4d4f68a60bc5af7dfa38b47b49659fc3312a2efd9b` |
| Census digest | `0cf872e3822494bb0fe9c4be7f0e2adb0009d3330ef96b2461a89c5192302446` |
| Active alias digest | `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` |
| Vector-space identity | `7dcba654e1c947145253ff65ef93e2b4ef1105cdf680b79218a446c79cc1a0d7` |
| Documents / versions / sources | 44 / 44 / 44 |
| Chunks | 2,658 |
| Integrity / foreign keys | `ok` / 0 violations |

The validator compared every `(document_id, version_id, content_hash)` tuple in the database
with the governed 44-document census. It also located and SHA-256 verified all 44 source
blobs through the configured content-addressed filesystem. A shared blob store may contain
additional immutable blobs, but only identities admitted by the 44-document SQLite source
memberships are production-visible.

## 3. Exact changes

### Production implementation

- `mnemo.toml` now selects the governed 44-document SQLite database and the
  `full_multilingual_v2_local_prebuild` profile document. The legacy top-level ms-marco
  configuration remains present because BGE activation is outside this task.
- `mnemo_server.runtime_config.resolve_mnemo_runtime_config` is the shared configuration
  resolution policy used by FastAPI, MCP stdio, and MCP SSE.
- `ProductionFullMultilingualV2ServerDependencyAssemblerV1` and the controlled startup helper
  now fail closed with `PRODUCTION_STORE_CONFIGURATION_MISMATCH` unless the engine database
  path equals the identity-manifest target.
- `production_store_readiness.py` validates the governed identity, build and generation
  relationships, active alias, document/version/source/chunk census, source blobs, profile,
  vector space, candidate policy, reranker policy, execution profile, and ContextBuilder
  contract without inference or writes.
- `scripts/mnemo_v2_serving_readiness.py` generates both readiness JSON artifacts from actual
  configuration, manifest, and read-only database state.

### Governance/configuration

- `config/production/full_multilingual_v2.production.json` records the pre-exposure production
  contract and explicitly records V2 transport exposure, BGE activation, verification, and
  certification as false.
- The full V2 profile document retains the governed `v1_only` and `disabled` selections so
  environment-driven reduced modes remain backward compatible.

### Evaluation-only artifacts

No retrieval-quality artifact was changed or rerun. The 67-document database remains named
only as a prohibited evaluation store in the production manifest and readiness validator.

## 4. Store authority and runtime graph

The configured and enforced pre-exposure graph is:

```text
HTTP FastAPI process ─┐
                     ├─ shared resolve_mnemo_runtime_config
MCP stdio/SSE process┘             │
                                   v
                      KnowledgeEngine (44-document DB)
                                   │
           server PrincipalContextV1 + CentralAuthorizationServiceV1
                                   │
                       CentralV2RetrievalAuthorizerV1
                                   │
                  governed read-only V2 store (same DB identity)
                    ┌──────────────┼────────────────┐
                    v              v                v
                 retrieval     enumeration     evidence resolution
                    └──────────────┼────────────────┘
                                   v
                         governed candidate path
                                   v
                       ContextBuilder -> FinalQA
```

At controlled exposure, HTTP retrieval and FinalQA routes and MCP `search_evidence` /
`run_final_qa_v2` tools use the same `KnowledgeEngine` application services. No separate MCP
retrieval implementation or database selector exists. Actual V2 transport registration was
deliberately not executed here.

## 5. Store-identity equality proof

The generated readiness artifact contains:

```ini
production_corpus = 0c6c73f9...9af8d
retrieval         = 0c6c73f9...9af8d
authorization     = 0c6c73f9...9af8d
evidence          = 0c6c73f9...9af8d
HTTP              = 0c6c73f9...9af8d
MCP               = 0c6c73f9...9af8d
```

This equality is not handwritten startup state: the validator loads `mnemo.toml`, parses the
governed identity manifest, verifies immutable build rows and generation dependencies,
resolves the active alias from the database, and verifies the census. The server assembler
independently enforces the same path equality before composition.

## 6. Generation and model contract

The active alias dynamically resolved four distinct generation identities:

- representation: `81f673bb-665d-591a-b12b-472ff3e39b7c`
- language text: `a7220adf-202c-536e-8e7c-c09d4d4c563f`
- embedding: `62243160-bed5-5064-a664-815984232e31`
- multilingual vector: `2b26443e-bb99-5bf8-a4af-a01ba99af8ce`

The production contract recorded by the manifest and checked from source is:

| Boundary | Contract |
|---|---|
| Semantic retrieval | BAAI/bge-m3 revision `5617a9f61b028005a4858fdac845db406aefb181`, 1,024 dimensions |
| Lexical retrieval | SQLite FTS5 `unicode61` |
| Fusion | reciprocal-rank fusion |
| Candidate K | 50 fused candidates entering reranking |
| Reranker | BAAI/bge-reranker-v2-m3 revision `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` |
| Pair/input contract | `bge-reranker-v2-m3-pair-256-contextual-v1`; `mnemo.reranker-input-audit/2` |
| Execution | CUDA, batch 2, no device/CPU fallback |
| ContextBuilder | ADR-0043: target 100, hard/provider max 120, fail-hard validation |
| Authorization | server principal, CentralAuthorizationServiceV1 plus CentralV2RetrievalAuthorizerV1 |
| Outer legacy reranker | disabled when V2 is installed, preventing ms-marco double reranking |

These values were validated but BGE was not loaded or activated.

## 7. HTTP and MCP composition evidence

- FastAPI application lifespan calls `resolve_mnemo_runtime_config`, constructs one
  `KnowledgeEngine`, and exposes it to all application services through `app.state.engine`.
- MCP stdio and SSE call the same resolver and construct the same engine type from the same
  frozen core configuration policy.
- Both transports use `EvidenceRetrievalApplicationService` for evidence retrieval and
  `FinalQAV2ApplicationService` for FinalQA. Production mode requires the principal-aware V2
  entry point; `RetrievalPlanV2.security_scope_identity` is not used as actor authority.
- The V2 assembler opens retrieval/enumeration/evidence reads from the manifest target and now
  refuses to compose if the engine backing central authorization names any other SQLite path.

This is composition/readiness proof. Since exposure remains unauthorized in this task, no
claim is made that a live external HTTP or MCP call traversed V2.

## 8. Tests and static validation

Focused same-store and transport composition tests cover:

- the real 44-document configuration and read-only census;
- rejection of the 67-document evaluation database as production;
- shared HTTP/MCP configuration resolution;
- dynamic active alias and four-generation binding;
- K=50, 256-token pair policy, CUDA/batch-2/no-fallback, and ContextBuilder 100/120;
- existing V2 production adapter composition, authorization, FinalQA, MCP security, and
  legacy model-profile reduced modes.

The final commands and results are recorded in the machine report. Ruff, targeted strict
mypy, compileall, JSON parsing, **164 focused tests**, and targeted `git diff --check` pass. The
repository-wide diff check retains the documented unrelated pre-existing whitespace issue at
`mnemo-core/mnemo/models/chunks.py:65`.

## 9. Protected-state verification

- Active database before/after SHA-256:
  `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`.
- Active DB WAL remained zero bytes; DB SHM hash remained
  `fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb`.
- Identity manifest SHA-256 remained
  `5ad46ad68b74f3fdff451ea0de2c128f5edffd762e6c3b843c2a2d288bb03dc9`.
- Active alias and generation IDs were read, not changed.
- No Golden Dataset, source blob, model artifact, 67-document database, embedding, FTS,
  generation, or index was modified.
- No provider inference, retrieval evaluation, alias activation, or exposure occurred.

`mnemo.toml` changed intentionally from SHA-256
`7d94649efe9540eac1abfc197769c0875f48161d4c9ec191b73560e97d499083`
to `122c79831a9cbe17142a5dfdaa7e8c908d4d33c069e7b27fdfb8562de9478588`
to bind the engine to the governed 44-document artifact and V2 profile.

## 10. Readiness and remaining gates

Generated evidence:

- `scratch/mnemo_v2_exposed_readiness.json`
- `scratch/mnemo-v2-production-store-unification.json`

The technical store-unification blocker is closed. Remaining controlled lifecycle gates are:

1. explicitly authorize V2 HTTP/MCP exposure;
2. start the authenticated production process with the governed local model cache;
3. execute real HTTP/MCP same-query parity and authorization checks;
4. perform controlled BGE activation and post-activation verification;
5. validate deterministic rollback to retained ms-marco artifacts;
6. only then consider EVALUATED, VERIFIED, and CERTIFIED.

## Final status

```text
PRODUCTION_STORE_UNIFIED
SERVING_READINESS_VALIDATED
```

These statuses mean ready for the next controlled exposure gate, not exposed or certified.
