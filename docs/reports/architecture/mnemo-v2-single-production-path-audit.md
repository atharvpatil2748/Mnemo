# Mnemo V2 single production path audit

**Status:** CURRENT — post-certification production authority

**Date:** 2026-09-06

**Certification:** `PRODUCTION_CERTIFICATION_PASS` under ADR-0076

## Executive result

Mnemo has one certified production serving path and one canonical declarative
configuration root. HTTP, MCP stdio, and MCP SSE differ only at their transport
and authenticated-principal adapters. They converge on the same installer,
application service, V2 retrieval application, 44-document store, authorization,
evidence resolver, ContextBuilder, FinalQA bridge, and operational store.

The only hidden alternate startup dependency found was the legacy outer
ms-marco cross-encoder in `mnemo.toml`. V2 already bypassed that reranker, but
core initialization still loaded it. The slot now uses a model-free
`v2-owned-pass-through` provider. V2's governed router remains the sole model
reranker and durable activation still selects the certified BGE revision.

## Canonical runtime graph

```text
HTTP create_app/lifespan ───────────────┐
MCP stdio run_server ──────────────────┼─> resolve_mnemo_runtime_config
MCP SSE create_sse_app/lifespan ───────┘
                                            ↓
                              authenticated server principal
                                            ↓
                         install_production_full_multilingual_v2
                                            ↓
                      production readiness + durable mode restore
                                            ↓
                         EvidenceRetrievalApplicationService
                                            ↓
                   CentralAuthorizationServiceV1 / V2 authorizer
                                            ↓
           44-document production store (retrieval = auth = evidence)
                                            ↓
                  FullMultilingualRetrievalApplicationV2
                                            ↓
                BGE-M3 dense + SQLite FTS5 sparse + RRF
                                            ↓
                exactly 50 fused candidates enter reranking
                                            ↓
          GovernedV2RerankerRouterV1 → BGE-reranker-v2-m3
                                            ↓
                    authorized evidence + ContextBuilder
                                            ↓
                          FinalQA / grounded response
                                            ↓
              separate mutable FinalQA operational SQLite store
```

## Entrypoint convergence proof

| Transport | Composition entrypoint | Shared resolver/installer |
|---|---|---|
| HTTP | `mnemo-server/mnemo_server/app.py:create_app` lifespan | `resolve_mnemo_runtime_config` + `install_production_full_multilingual_v2` |
| MCP stdio | `mnemo-server/mnemo_server/mcp/server.py:run_server` | same resolver + same installer |
| MCP SSE | `mnemo-server/mnemo_server/mcp/server.py:create_sse_app` lifespan | same resolver + same installer |

All three use `EvidenceRetrievalApplicationService`; none exposes a client model
selector. Server-derived principals reach `CentralAuthorizationServiceV1` and
`CentralV2RetrievalAuthorizerV1`. Evidence resolves against the identical store
identity.

## Canonical production configuration

The authoritative declarative root is
`config/production/full_multilingual_v2.production.json`. It references rather
than competes with:

- `mnemo.toml`: core runtime locations/providers and the inert outer slot;
- `config/model_profiles/full_multilingual_v2_profiles.toml`: pinned immutable
  production model/generation contracts;
- `scratch/phase8_5_full_multilingual_v2/operational/reranker_activation.json`:
  signed durable desired mode;
- `scratch/phase8_5_full_multilingual_v2/operational/certification.json`: signed
  WP-17 lifecycle state.

Environment values supply server secrets and authenticated capability inputs;
they cannot select a different reranker revision, pair policy, K, or corpus.
Evaluation profiles and the 67-document database are non-production.

## Certified identities and contracts

| Component | Certified value |
|---|---|
| Production store | `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d` |
| Production DB SHA-256 | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` |
| Dense embedding | `BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`, 1,024 dimensions |
| Lexical/fusion | SQLite FTS5 / RRF |
| Internal reranker pool | exactly 50 fused candidates |
| Reranker | `BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` |
| Pair policy | `bge-reranker-v2-m3-pair-256-contextual-v1` |
| Execution | CUDA, batch 2, CPU fallback false |
| Public result depth | dynamic `requested_k` (1, 5, 10, 25, 50 validated) |
| ContextBuilder | ADR-0043: target 100, maximum 120, fail hard |
| FinalQA persistence | separate `final_qa_v2.db` operational store |

## Alternate path classification

| Alternate | Classification | Production reachable? | Disposition |
|---|---|---:|---|
| Core `CrossEncoderReranker` and ADR-0042 ms-marco behavior | historical V1 / tests / offline evaluation | No in certified V2 | source/evidence retained |
| Phase 8.5/8.6 identity-bound harnesses | evaluation-only | No | retained |
| PASS_THROUGH V2 router mode | governed rollback state | only via authenticated durable rollback | retained |
| 67-document canonical database | evaluation-only | rejected by same-store readiness | retained, never promoted |
| `scripts/manual_gita_qa.py` ms-marco constant | historical manual script | No | retained |

Clients cannot choose the outer provider, reranker model, revision, pair policy,
or internal K. The model-free outer slot exists only because the legacy core
interface still requires a registered provider; exposed V2 never invokes it.

## Model cleanup

The complete machine-readable inventory is
`scratch/mnemo-model-inventory.json`. The project-owned ms-marco snapshot under
`D:/Mnemo/phase8.5.11-models` was the sole eligible artifact after startup no
longer referenced it. Shared user Hugging Face caches were retained because
their ownership is not Mnemo-exclusive. BGE-M3, BGE-reranker-v2-m3, CLIP,
Tesseract resources, and every Ollama model were retained.

The retired directory contained revision
`233902d25c440f23af6f7d6e94d2946bac0bee0a`; its pre-deletion tree digest was
`d1cdae2f2a0341e83edfb742264742ed4f3101f41de16e396f6e6f30d0b15af8`.
Deletion reclaimed 843,821,056 physical bytes. The shared user Hugging Face
copies were not removed because their ownership is not project-exclusive.

The retained Ollama inventory is `qwen2.5vl:latest`, `gemma4:e4b`,
`nomic-embed-text:latest`, `mistral:7b-instruct`, `phi3:mini`, and
`llama3:latest`.

No Ollama command that mutates state was run. `OLLAMA_MODELS` and
`OLLAMA_NUM_PARALLEL` were not changed.

## Documentation organization

Historical evidence was not moved or rewritten. `docs/README.md`,
`docs/reports/README.md`, and `docs/changelog/README.md` now provide current
authority and logical categories at stable paths. The ADR index and root README
now point to ADR-0076 and the certified production state. The documentation
inventory records the classification and confirms zero moved historical files.

## Certification preservation

This cleanup does not change retrieval scores, candidate construction, RRF,
internal K, public `requested_k`, pair rendering, ContextBuilder, corpus,
embeddings, model revisions, activation state, or lifecycle state. The startup
change removes a bypassed model load; it does not alter the certified V2 request
path. Validation and before/after hashes are recorded in
`scratch/mnemo-v2-single-production-path-audit.json`.

### Integrity and validation evidence

| Check | Result |
|---|---|
| Production DB SHA before/after | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` / identical |
| Counts / SQLite | 44 documents, 44 versions, 44 memberships, 2,658 chunks; integrity `ok`; FK violations 0; WAL 0 |
| Signed activation state | unchanged, SHA-256 `b4aa8088c143418432bc228f7130d413c62908e706aa109f5ff75d3100b3fb09` |
| Signed certification state | unchanged, SHA-256 `777c1a4f1d352a9ba219293b6afbb230778b97801b764c10fccd1afe5993fb15` |
| Model profile | unchanged, SHA-256 `b50bb864f21068b2661281aa2f547afd577f218c8c7229f5a47126541ad879fe` |
| Certified contract digest | unchanged, `57b1812a0713b18746e02a60b46e742d196909500d31eb423ec5ee392eb40e42` |
| `mnemo.toml` file digest | `64a5082b…` → `62f0fa3c…` (model-free outer slot) |
| Production manifest file digest | `5822d222…` → `4aaedbc2…` (truthful active/certified declaration) |
| Focused tests | 83 passed |
| Real production startup | passed both before and after model retirement; BGE active, outer slot model-free |
| Ruff / strict mypy / compileall / JSON | pass |
| Documentation links | 359 Markdown files checked; zero broken internal links |
| Targeted whitespace/diff check | pass |

The file-level configuration digests changed because this audit deliberately
removed the hidden startup load and reconciled the stale declarative manifest.
The resolved certified contract digest, signed activation/lifecycle state,
production DB, pinned profiles, and serving behavior are unchanged.

## Final status

`POST_CERTIFICATION_SINGLE_PATH_AUDIT_PASS`
