# Mnemo V2 Final Production Certification

**Date:** 2026-09-05  
**Result:** `PRODUCTION_CERTIFICATION_BLOCKED`  
**Highest truthful lifecycle:** `ACTIVE`  
**Failed gate:** `EXPOSURE_BLOCKED`

## Executive result

The controlled exposure gate could not truthfully pass. No HTTP server, MCP server,
provider, evaluation, activation, or rollback operation was launched after the failure
was established.

The production store remains unified and healthy. The blocker is in the real transport
security/composition boundary:

1. the governed readiness projection requires stdio/SSE parity evidence before it can
   produce `v2_exposed=true`;
2. the engine refuses to install V2 unless that already-exposed snapshot is supplied;
3. no production code constructs such a snapshot or invokes the production installer;
4. the real MCP server invokes tools without a principal and substitutes an
   unauthenticated anonymous principal; and
5. SSE authentication claims are validated by middleware but are not propagated into
   MCP tool execution.

Setting the readiness booleans manually, manufacturing an MCP principal, or bypassing
the engine check would violate the task's fail-closed requirements. Certification
therefore stops at exposure.

## What was established before this task

- The 44-document Phase 8.5 store is the authoritative production store.
- Retrieval, authorization, evidence resolution, HTTP configuration, and MCP
  configuration resolve the same governed database identity.
- K=50 means the top 50 fused candidates entering reranking.
- The governed reranker contract is BGE v2-m3, contextual 256-token pairs, CUDA,
  batch 2, with no CPU fallback.
- ContextBuilder follows ADR-0043: target 100, maximum 120, fail-hard.
- The pre-exposure store-readiness artifact reports
  `SERVING_READINESS_VALIDATED`; it explicitly reports `currently_exposed=false`.

## Newly executed inspection

The actual HTTP/MCP startup, readiness projection, engine installation seam, principal
mapping, and MCP tool dispatch were traced from source. The current environment was
also inspected: production mode is off, V2 exposure is off, authentication defaults to
`none`, and no V2 model cache is configured in the process environment.

Focused security/readiness validation completed with **31 passed, 0 failed** using
`--no-cov`. The default coverage-enabled invocation also ran all 31 tests successfully,
but its process status failed because a focused subset covers 31.07%, below the
repository-wide 90% threshold. That is a coverage-command configuration result, not a
new assertion failure.

Targeted strict mypy and compileall passed. JSON validation passed. Ruff retains one
pre-existing line-length failure at `mnemo-server/mnemo_server/mcp/tools.py:1209`.
Repository-wide `git diff --check` retains the previously documented unrelated trailing
whitespace at `mnemo-core/mnemo/models/chunks.py:65`. Neither pre-existing issue was
modified for this certification audit.

## Failed gate evidence

### 1. Readiness and installation form an unsatisfied pre-exposure dependency

`V2ReadinessInputs` requires `transport_parity_verified` plus explicit stdio and SSE
evidence. `project_v2_readiness()` makes all three conditions mandatory before
`v2_exposed` becomes true in
`mnemo-core/mnemo/phase85/v2_readiness.py:217-226`.

`KnowledgeEngine.install_exposed_full_multilingual_v2()` then rejects any snapshot for
which `v2_exposed` is false in `mnemo-core/mnemo/engine.py:193-211`.

The only repository construction of `V2ReadinessInputs` is currently in a unit test.
The store-readiness generator creates a different pre-exposure artifact and explicitly
does not expose V2. No HTTP or MCP production startup calls
`install_production_full_multilingual_v2()`.

### 2. Real MCP dispatch has no authenticated principal propagation

`create_mcp_server()` dispatches tools as follows:

```text
execute_mcp_tool(server._engine, name, arguments, server._config)
```

No principal is supplied (`mnemo-server/mnemo_server/mcp/server.py:88-96`). The tool
boundary consequently executes:

```text
principal or principal_from_claims(None)
```

(`mnemo-server/mnemo_server/mcp/tools.py:617-632`). `principal_from_claims(None)` is
the stable unauthenticated principal, so governed V2 authorization cannot accept the
real stdio path.

For SSE, `AuthMiddleware` validates API-key/JWT authentication and stores claims in
`request.state.auth` (`mnemo-server/mnemo_server/auth.py:188,235`). The SSE MCP server
does not transfer those claims into `call_tool`, so its tool execution reaches the same
anonymous fallback. HTTP routers do consume `request.state.auth`; MCP does not.

The architecture text calls for a “server-created MCP principal,” but the repository
does not define the authenticated stdio session/credential source needed to create it.
Choosing a subject or treating process locality as authentication would add security
semantics not present in the governed implementation.

## Gate results

| Gate | Result | Evidence |
|---|---|---|
| Controlled authenticated exposure | `EXPOSURE_BLOCKED` | No truthful exposed snapshot; real MCP principal propagation absent |
| HTTP E2E | Not executed | Required prior gate failed |
| MCP stdio E2E | Not executed | Required prior gate failed |
| MCP SSE E2E | Not executed | Required prior gate failed |
| HTTP/MCP parity | Not executed | Required transports were not exposed |
| Production-parity evaluation | Not executed | Exposure/parity prerequisites failed |
| BGE activation | Not attempted | Evaluation gate did not run |
| Post-activation verification | Not executed | BGE was not activated |
| Rollback verification | Not executed | No activation occurred |

## Production store and protected state

| Item | Observed value |
|---|---|
| Path | `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db` |
| Governed identity | `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d` |
| Physical SHA-256 | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` |
| Size | 189,804,544 bytes |
| Documents / versions / sources | 44 / 44 / 44 |
| Chunks | 2,658 |
| Integrity / FK violations | `ok` / 0 |
| WAL | 0 bytes; empty-file SHA-256 |
| Active alias | `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` |

The production database SHA matches the required baseline. Read-only integrity and
foreign-key checks passed. No provider inference, indexing, retrieval evaluation,
alias mutation, activation, or corpus mutation occurred. The 67-document database
remains evaluation-only at `data/canonical_production/mnemo_canonical.db`; it was not
introduced into production composition.

## Contracts preserved

- Embedding: `BAAI/bge-m3` revision
  `5617a9f61b028005a4858fdac845db406aefb181`, 1,024 dimensions.
- Retrieval: SQLite FTS5 plus RRF.
- Candidate pool: top 50 fused candidates entering reranking.
- Reranker: `BAAI/bge-reranker-v2-m3` revision
  `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`.
- Pair contract: `bge-reranker-v2-m3-pair-256-contextual-v1`.
- Execution: CUDA, batch 2, no CPU fallback.
- ContextBuilder: 100-token target, 120-token maximum, fail-hard.
- Authorization: server-derived principal through the central V2 authorization path.

## Smallest corrective action

Before certification can resume, one governed transport/composition remediation is
required:

1. define the authenticated server-owned principal source for MCP stdio without using
   caller-supplied actor identity;
2. propagate AuthMiddleware-validated SSE claims into the MCP call context;
3. implement a production-owned readiness snapshot builder backed by actual immutable
   contract/security evidence; and
4. wire the existing production installer into both HTTP and MCP startup only when
   that snapshot truthfully projects `v2_exposed=true`.

After that focused remediation, resume at controlled exposure. The unexecuted E2E,
evaluation, activation, post-activation, and rollback gates must still run in order.

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

The system was left safely non-exposed and non-activated.
