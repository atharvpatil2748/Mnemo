# Mnemo V2 MCP Authentication, Exposure, and Certification

**Date:** 2026-09-05  
**Status:** `PRODUCTION_CERTIFICATION_BLOCKED`  
**Failed gate:** `PRODUCTION_STARTUP_EXPOSURE_BLOCKED`  
**Highest truthful lifecycle:** `ACTIVE`

## Executive summary

The authenticated MCP-principal blocker is resolved. Production V2 MCP stdio now
requires an explicit server-configured subject, and MCP SSE maps only claims already
validated by `AuthMiddleware`. Both feed the existing `PrincipalContextV1` mapping and
the common application/authorization path. Tool arguments cannot establish or replace
the transport principal. Anonymous fallback remains available only for historical
non-production/V1 calls; it is rejected whenever production V2 is enabled.

Certification stopped at the next gate. The repository still lacks a production-owned
source for the evidence needed to construct `V2ReadinessInputs`, and its only V2
installer initializes BGE as part of exposure. There is no separate governed reranker
activation/rollback authority. Exposing V2 would therefore activate BGE before the
required HTTP/MCP parity and production evaluation gates, contrary to the required
sequence. No readiness booleans or activation state were fabricated.

## MCP principal remediation

### Previous call chain

```text
MCP stdio/SSE
  -> create_mcp_server.call_tool
  -> execute_mcp_tool(..., principal=None)
  -> principal_from_claims(None)
  -> unauthenticated anonymous PrincipalContextV1
```

### Current production call chain

```text
stdio server-owned configured subject -----+
                                            +-> PrincipalContextV1
SSE AuthMiddleware-validated claims -------+   -> execute_mcp_tool
                                                -> shared application service
                                                -> CentralAuthorizationServiceV1
                                                -> CentralV2RetrievalAuthorizerV1
```

The stdio subject comes only from
`MNEMO_SERVER_MCP_STDIO_PRINCIPAL_SUBJECT`/`ServerConfig`; it is not a tool argument.
Production V2 configuration rejects a missing or blank stdio subject. SSE uses the
authenticated ASGI session scope populated by the existing API-key/JWT middleware.
Missing claims fail closed. A context-local binding prevents cross-session principal
state from being stored on the shared MCP server object.

The MCP CLI now starts from `ServerConfig.from_env()` instead of discarding production
settings when it constructs its transport configuration.

## Production startup/exposure blocker

### Missing production readiness evidence authority

`project_v2_readiness()` requires seven SHA-256 transport evidence values, verified
stdio and SSE flags, transport parity, shared-path verification, and a passed security
gate. The only repository construction of `V2ReadinessInputs` is in
`mnemo-core/tests/unit/test_full_multilingual_v2.py`. The existing serving-readiness
script validates store/configuration identity but intentionally emits a separate
pre-exposure artifact with `currently_exposed=false`.

There is consequently no governed production artifact or builder from which startup can
truthfully obtain the mandatory transport digests and verification decisions. Filling
those fields with convenient hashes or hard-coded `true` values would be synthetic
readiness evidence.

### Exposure currently collapses into BGE activation

`install_production_full_multilingual_v2()` constructs and initializes
`BGEMultilingualReranker` before calling
`KnowledgeEngine.install_exposed_full_multilingual_v2()`:

- construction: `full_multilingual_v2_startup.py:154`;
- model initialization: `full_multilingual_v2_startup.py:161`;
- exposure installation: `full_multilingual_v2_startup.py:199`.

The authoritative production manifest still records
`bge_reranker_activated=false`. Repository search found no separate reranker alias
activation or reranker rollback mechanism. The V2 generation alias controls the four
representation/index generations; it is not a reranker-model activation authority.

The mandated sequence requires exposure and transport parity before production BGE
activation. The current implementation cannot represent that sequence: the first real
exposure attempt would load and serve BGE. Treating initialization as “not activation”
would change lifecycle semantics rather than implement them.

## Gate results

| Gate | Result |
|---|---|
| MCP authenticated principal | PASS |
| Stdio principal propagation | PASS |
| SSE principal propagation | PASS |
| Principal non-overridability | PASS |
| Production startup readiness | `PRODUCTION_STARTUP_EXPOSURE_BLOCKED` |
| Controlled exposure | Not executed |
| HTTP E2E | Not executed |
| MCP stdio E2E | Not executed |
| MCP SSE E2E | Not executed |
| HTTP/MCP parity | Not executed |
| Production-parity Golden evaluation | Not executed |
| BGE activation | Not attempted |
| Post-activation verification | Not executed |
| Rollback verification | Not executed; no activation occurred |

## Validation

The focused matrix covered the new principal adapter plus existing MCP server, SSE,
WP-14 security, FinalQA transport, retrieval, structured retrieval, delivery, tool,
registration, and production-store readiness tests:

```text
84 passed, 0 failed
```

Ruff passed on the changed logic when the documented pre-existing E501 is excluded;
the existing overlong validation message in `mnemo-server/mnemo_server/mcp/tools.py`
remains. Strict mypy passed on all five touched production modules. Compileall passed.
The generated JSON parses. The repository-wide diff check retains the unrelated
pre-existing whitespace issue at `mnemo-core/mnemo/models/chunks.py:65`.

## Protected state

- Production store:
  `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db`
- Governed identity:
  `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d`
- Physical SHA-256 after remediation:
  `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`
- Store counts remain 44 documents, 44 versions, 44 sources, and 2,658 chunks.
- WAL remains zero bytes.
- The active generation alias is unchanged.
- The 67-document database remains evaluation-only.
- No model/provider was loaded, no evaluation ran, and no alias or corpus was changed.

## Smallest remaining corrective action

Two connected governance/storage-neutral additions are required before exposure:

1. define a versioned immutable transport-readiness evidence artifact and a
   production-owned builder that validates its actual schema/parity/security evidence;
2. define a distinct BGE reranker activation and rollback authority, or formally amend
   the sequence so that controlled V2 exposure is itself the governed BGE activation.

Startup can then consume those authorities and invoke the existing installer from HTTP,
stdio, and SSE composition. Certification must resume at production startup readiness;
none of the later gates may be inferred from the principal tests.

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

MCP authentication support is implemented. The system remains safely non-exposed and
BGE remains inactive. Rollback was not required.
