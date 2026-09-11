# Mnemo V2 Governed Exposure / BGE Certification

**Date:** 2026-09-05

**Status:** `PRODUCTION_CERTIFICATION_BLOCKED`

**Highest truthful lifecycle:** `EXPOSED`

**Failed gate:** `HTTP_E2E_BLOCKED`

**Blocker:** `FINAL_QA_PROTECTED_STORE_WRITE_CONFLICT`

## Executive result

The missing pre-BGE contract is now implemented. Production V2 can be exposed in the
explicit `PASS_THROUGH` reranker mode using the model-independent typed candidate
builder, without loading or activating BGE-reranker and without invoking the legacy
ms-marco outer reranker. BGE activation and rollback are separate, gated authorities.

The actual production startup generated readiness and exposed V2 against the governed
44-document store. Real authenticated HTTP, MCP stdio, and MCP SSE retrieval requests
all succeeded. They returned the same five document, version, and chunk identities in
the same order.

Certification stopped at the full HTTP FinalQA gate. The real FinalQA V2 orchestrator
durably writes execution, snapshot, state-transition, and citation records through
`engine.storage`. Store unification binds that storage to the protected 44-document
database, whose physical SHA is required to remain exactly unchanged. The database has
zero existing FinalQA V2 executions and snapshots, so no read-only replay exists.
Issuing a new FinalQA request would violate protected state. No workaround was used.

BGE was not evaluated or activated, and rollback was not required.

## Governed pre-BGE exposure contract

| Contract | Governed value |
|---|---|
| Candidate builder | `mnemo.v2-typed-candidate-builder/1` |
| Reranker mode | `PASS_THROUGH` |
| Reranker identity | `v2-pass-through-reranker-v1` |
| Candidate behavior | Preserve fused order and evidence identity |
| Reranker model load | None |
| BGE invocation | None |
| ms-marco invocation | None |
| Authorization/evidence | Remain mandatory |

The generic candidate builder preserves semantic text, governed contextual fields,
provenance, generation lineage, database identity, and the bounded authorization
decision. The BGE adapter renders that same candidate representation into the governed
256-token contextual pair only when the separate activation authority installs BGE.

## Separate authorities

`V2ExposureAuthorityV1` accepts a production readiness snapshot only while the router
is explicitly in `PASS_THROUGH`; it projects the exposure transition and installs V2.
It has no model factory and cannot activate BGE.

`RerankerActivationAuthorityV1` requires all of the following before it creates or
initializes BGE:

- V2 already exposed;
- production-parity evaluation passed;
- matching governed production-store identity;
- the typed candidate-builder identity;
- exact model and revision;
- the governed pair policy;
- CUDA, batch 2, and no CPU fallback.

Rollback is explicitly `BGE_V2_M3 -> PASS_THROUGH`; it does not restore ms-marco. The
installed runtime also rolls back/closes an active BGE delegate during shutdown.

## Production-owned readiness and startup

`ProductionV2ReadinessEvidenceBuilderV1` is invoked by the real HTTP and MCP startup
composition. It resolves the active four-generation set dynamically, validates the
governed database identity, checks production/authentication configuration, derives
transport contract digests from repository sources, and creates a readiness snapshot
with `runtime_exposure_selected=false`.

The exposure authority alone changes that runtime snapshot to exposed. The 67-document
database does not enter this composition.

## Production store

| Property | Observed value |
|---|---|
| Path | `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db` |
| Governed identity | `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d` |
| Physical SHA-256 after shutdown | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` |
| Size | 189,804,544 bytes |
| Documents / versions / sources / chunks | 44 / 44 / 44 / 2,658 |
| Integrity | `ok` |
| Foreign-key violations | 0 |
| WAL / SHM | 0 / 32,768 bytes |

The physical SHA exactly matches the protected baseline after all real transport
requests and clean server shutdown.

## Authentication evidence

- HTTP and SSE use claims validated by `AuthMiddleware`; API-key authentication derives
  the opaque actor `0ed17cd0-06f2-5345-8938-fa45ed29201e`.
- MCP stdio uses the server-only configured subject `mnemo-production-stdio`, deriving
  actor `b6dc0bff-e77a-5136-9481-3a62fd8ae470`.
- Both map into the same typed `PrincipalContextV1`/`ServerPrincipalV1` abstraction.
- Production MCP rejects missing/anonymous principals, and tool arguments cannot
  replace the transport principal.

The actor identifiers correctly differ across independently authenticated transport
subjects; parity is authorization semantics and serving output, not identity
impersonation.

## Real transport evidence

The query was:

> What does the Bhagavad Gita teach about duty and action?

The authorized notebook was `df9c20cf-85fe-529c-902e-2e9e68193fbe`. Each real
transport returned five items from document
`f7a2cfb6-9742-56ab-9817-d20a5a7bce9d`, version
`d16f586e-5a4d-5b5f-ae76-012b69263826`, with this exact ordered chunk list:

1. `1726297a77e16a9f8f21794d728510f1c14a4f5b340a42f36a22e51502bb45a1`
2. `9e0af11db52d1e700447e2c1bec743c772bc1f3630cb2959f7aa097fd12e8ffb`
3. `93783e79c3f7eaa2ca15beec79fa82193896d354b70365a2cdecebdeeedcbb22`
4. `0c2fb057bc0af9ce788a3c01cddc1437cd9689a7efb0e30b17c894427b8d67fc`
5. `3f192c1760d13d1a2ca13f821f4b7d2b79818891c59321a034c604f69caaa42b`

| Actual transport | Result | Evidence |
|---|---|---|
| HTTP POST `/v2/retrieval/evidence` | PASS, HTTP 200 | `scratch/http-e2e-result.json` |
| MCP stdio `search_evidence` | PASS, real client/server dispatch | `scratch/mcp-stdio-e2e-result.json` |
| MCP SSE `search_evidence` | PASS, authenticated GET/messages | `scratch/mcp-sse-e2e-result.json` |
| Ordered retrieval identity parity | PASS | All three artifacts are identical on document/version/chunk order |

This proves actual retrieval/authorization/evidence transport parity in pass-through
mode. It does not claim FinalQA parity.

## Failed FinalQA gate

The HTTP/MCP E2E requirement extends through ContextBuilder and FinalQA. That operation
could not safely be executed:

1. `FinalQAV2ApplicationService` requires `engine.storage` to implement
   `FinalQAExecutionStoreV2`.
2. `FinalQAV2Orchestrator` creates a durable execution before generation.
3. It writes validation/published snapshots, state transitions, and citations to that
   store.
4. Production store unification makes this the same protected corpus/index SQLite
   artifact.
5. The protected-state contract requires that artifact's SHA remain exactly
   `3157ff...458c`.
6. The existing execution and snapshot tables both contain zero rows, so no replay can
   satisfy the E2E gate without writes.

Calling FinalQA, using a copied database, bypassing persistence, or restoring bytes
afterward would each falsify either production-path or protected-state evidence.

The smallest safe remediation is to govern an operational FinalQA execution-persistence
store whose mutable identity is separate from the immutable 44-document corpus/index
artifact. Retrieval, authorization, and evidence must remain bound to the governed
44-document store. Once that ownership split is governed, resume at the real HTTP
FinalQA request and repeat it through MCP stdio/SSE.

## Gate results

| Gate | Result |
|---|---|
| Pre-BGE candidate/reranker contract | PASS |
| Production readiness builder | PASS |
| Controlled V2 exposure | PASS |
| BGE remains inactive | PASS |
| Real HTTP retrieval | PASS |
| Real MCP stdio retrieval | PASS |
| Real MCP SSE retrieval | PASS |
| Retrieval identity parity | PASS |
| Real HTTP through FinalQA | **BLOCKED — not executed** |
| MCP FinalQA E2E | Not executed |
| Full HTTP/MCP FinalQA parity | Not executed |
| Production Golden BGE evaluation | Not executed |
| BGE activation | Not executed |
| Post-activation verification | Not executed |
| Rollback | Not required; not executed |
| Final activation/certification | Not executed |

## Validation

- Focused V2, readiness, exposure, activation, rollback, MCP principal/SSE, server,
  retrieval, and FinalQA contract tests: **80 passed**.
- Authoritative ContextBuilder tests: **34 passed**.
- A broader multimodal module run produced **52 passed, 1 failed**. The failure is an
  unrelated stale migration assertion expecting schema version 14 while the current
  repository migrates to version 16 (`test_schema_12_migration_is_idempotent_and_rollback_safe`).
  It was not changed or hidden.
- Ruff on touched implementation/tests/probes: **PASS**.
- Strict mypy on 14 touched source files: **PASS**.
- Compileall: **PASS**.
- JSON parse validation: **PASS**.
- Repository-wide `git diff --check`: the sole failure remains the unrelated,
  pre-existing trailing whitespace at `mnemo-core/mnemo/models/chunks.py:65`.
  A targeted whitespace check of this task's new artifacts passed.
- A first focused pytest invocation also showed all 80 tests passing but returned nonzero
  only because the repository-wide 90% coverage threshold is inappropriate for a
  focused subset; the validation rerun with repository `addopts` cleared passed.
- Final diff check result is recorded in the machine-readable artifact after report
  generation.

## Protected state

- Production DB bytes and required SHA are unchanged.
- Integrity is `ok`; FK violations are zero.
- Corpus counts remain 44/44/44/2,658.
- Golden Dataset was not modified; current deterministic 44-file tree digest is
  `b1afd0785b98e1a7fe642c510117ed3148d35af6d97d735de032ecabe86c4d0b`.
- Phase 8.6 data and the 67-document evaluation DB were not modified or used in
  production composition.
- Embedding/model artifacts and active generation alias were not modified.
- No BGE-reranker inference occurred.

## Lifecycle

```text
DECLARED: PASS
IMPLEMENTED: PASS
CONFIGURED: PASS
BUILDABLE: PASS
READY: PASS
ACTIVE: PASS
EXPOSED: PASS
EVALUATED: FALSE
VERIFIED: FALSE
CERTIFIED: FALSE
```

V2 is governed and empirically exposed in the valid pre-BGE state. BGE remains
inactive. Certification truthfully stops before evaluation and activation.
