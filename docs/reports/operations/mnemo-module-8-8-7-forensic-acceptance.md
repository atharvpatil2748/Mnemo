# Module 8.8.7 — independent local forensic acceptance

**Verdict:** `MODULE_8_8_7_FORENSICALLY_ACCEPTED` (2026-09-26, edited local checkout only).
This is neither deployment nor external ChatGPT verification, Stage 6 closure,
deferred 8.8.2f acceptance, or Phase 8.8 certification.

## Authority, baseline, and scope

The [current architecture §21.8](../../architecture/current/mnemo_architecture_v2.md)
requires ten safe error categories, a stable machine code and correlation ID,
and no stack-trace or unauthorized-existence leakage. The
[roadmap Module 8.8.7](../../architecture/current/mnemo_engineering_roadmap.md)
requires (a) the taxonomy, (b) originating safe layer/reason propagation beyond
opaque `sq-2:sparse`, and (c) prevention of SQL, path, credential and identity
disclosure. [ADR-0076](../../adr/active/ADR-0076-project-owner-engineering-certification-standard.md),
[ADR-0077](../../adr/active/ADR-0077-governed-mutable-workspace-boundary.md), and
[ADR-0078](../../adr/active/ADR-0078-generation-aware-production-credential-lifecycle.md)
retain the certified composition and authorization boundaries. The
[Stage 5 acceptance](mnemo-phase-8-8-stage-5-acceptance.md),
[8.8.5 forensic acceptance](mnemo-module-8-8-5-forensic-acceptance.md),
[8.8.7 implementation report](mnemo-module-8-8-7-local-implementation.md),
and [historical MCP audit](mnemo-mcp-failure-and-contract-audit.md) were
cross-checked against current source rather than treated as current runtime
proof.

Initial Git was `main...origin/main` at
`069ec468a675c37544a5a2591eac1204c3cb6888`, with no staged files,
25 modified tracked files, and six untracked files belonging to the prior
8.8.5 and 8.8.7 local work. The complete tracked diff, untracked classifier,
tests and reports, request adapters, error-producing services, CLI and legacy
event handlers were inspected. No pre-existing work was reset, discarded,
committed or deployed.

## Requirement → code → independent evidence

| Requirement | Implementation inspected | Executed audit evidence |
|---|---|---|
| 8.8.7a: ten safe categories | `mnemo-server/mnemo_server/typed_errors.py`: `ErrorCategory`, `TypedPublicError`, `classify_public_error`; `errors.py` HTTP mapping | `test_typed_errors.py`, `test_server_errors.py`: input, unauthorized, not-found, unavailable, configuration, schema, retrieval, transport, timeout and server categories; HTTP 408/502 negative tests failed before correction and pass afterward |
| 8.8.7b: originating safe reason and correlation | Cause-chain traversal and vetted class codes in `typed_errors.py`; request correlation in `auth.py`, `errors.py`, MCP dispatcher and V1 stream adapter | Nested `StorageError` → `PluginError` preserves governed schema reason; nested timeout now remains timeout; repeated requests have distinct UUIDs; malformed supplied correlation is replaced |
| 8.8.7c: nonreflection and nondisclosure | Static public messages, exact allowlists for codes/details, generic governed not-found, sanitized HTTP/MCP/V1 errors; sanitized health/startup diagnostics | Forged instance code, token-shaped details, path/SQL/token exceptions, HTTP health failure and CLI stderr regressions; public older/newer-schema MCP/HTTP, auth, metadata, FinalQA, stdio and SSE tests pass |

The ten wire categories are `invalid_input`, `unauthorized`, `not_found`,
`capability_unavailable`, `configuration_mismatch`, `schema_compatibility`,
`retrieval_failure`, `transport_failure`, `timeout`, and `server_failure`.
`TypedPublicError.body()` emits code, category, static safe message, bounded
details, retryability, originating code, layer/reason and a server UUID.
The retained direct legacy delivery denial remains generic HTTP 403; governed
production unknown and inaccessible resources have the same not-found shape.
This audit does not claim actor-to-notebook ACL isolation beyond the existing
canonical membership model.

## Adversarial defects reproduced and corrected

1. A mutable exception-instance `code` and token-shaped `field`/`reason`
   details reached the public classifier; a non-UUID correlation value also
   appeared verbatim. Three new regressions failed before correction.
   `typed_errors.py` now uses vetted class declarations, exact detail-value
   allowlists and UUID type validation. Safe known subclass codes remain
   available; arbitrary exception messages and instance attributes do not.
2. `PluginError` wrapping `OperationTimeoutError` was labeled retrieval
   failure despite a safe timeout origin. A negative test failed before the
   classifier correction and now verifies timeout category, originating code
   and deadline reason. The existing governed storage-schema reason still
   survives a sparse retrieval wrapper.
3. Public `/v1/health` reflected a storage exception containing a private
   path, SQL and token-shaped text into JSON and logs. The public ASGI test
   failed before correction. Health still reports component and degraded
   state, but exception and provider diagnostic details are now static or
   null; logs retain exception class only. The same nonreflection rule was
   applied to MCP startup warning logs and nongoverned CLI stderr; governed
   startup keeps its existing fixed failure code.
4. HTTP 408 and 502 were classified as input and server errors. Both
   parameterized public-adapter tests failed before the small HTTP mapping
   correction and pass as timeout and transport errors respectively.

The source corrections are confined to `typed_errors.py`, `errors.py`,
`services/system.py`, `mcp/server.py`, and `mcp/cli.py`. Regression additions
are in `test_typed_errors.py`, `test_server_errors.py`, `test_server_system.py`,
and `test_mcp_cli.py`. The prior 8.8.5 code, certified configuration and
accepted authorization checks were not changed.

## Public transport and regression evidence

| Surface | Independent exercised path | Result and boundary |
|---|---|---|
| HTTP | FastAPI ASGI requests to typed errors, authentication, health, delivery/metadata and V1 events | Static sanitized bodies, appropriate statuses and matching correlation headers; health diagnostics no longer reflect exception text |
| MCP dispatch | Real `ClientSession` against disposable older/newer-schema servers | Typed `isError` text/structured content; unknown/mismatched governed resources deny without metadata; nested sparse schema reason preserved |
| Stdio | Real project-local `mnemo-mcp` subprocess via MCP stdio client | Initialization, 14-tool list and sanitized invalid-tool result; disposable storage path, no live tunnel |
| SSE | Real loopback Uvicorn/SSE MCP client using synthetic core configuration and fixture credential | Authenticated initialization and sanitized invalid-tool result; no production-corpus configuration or endpoint |
| Retained V1 WebSocket/SSE | Streaming adapter regressions | Legacy event codes retained; static messages and server correlation detail, without raw exception text |
| FinalQA V2 | Timeout/reconciliation tests and source inspection | Authorized execution UUID is validated before public retention; raw reconciliation failure text is not published |

The initial unsafe SSE fixture configuration described in the local report was
not repeated. Current local transports use synthetic/disposable configuration.
These tests establish local wire behavior, not certified external-tunnel or
four-transport behavioral parity. Reader-specific `8.8.2f` acceptance remains
a separate task after this infrastructure; `8.8.4` and `8.8.8` are not claimed.

## Validation and protected state

Focused command using `uv run pytest -q -p no:cacheprovider -o addopts=''`
on typed-error, HTTP-error, system-health, MCP CLI/SSE/conformance tests:
95 passed, one Starlette warning. The public older/newer-schema, auth,
metadata and FinalQA cases were also included in the complete CI-safe suite.
Final command `CI=true MNEMO_CI=1 uv run pytest -q -p no:cacheprovider
--tb=short`: **2,613 passed, 18 skipped, eight warnings, 90.11%
repository-wide coverage** (configured 90% minimum). Warnings were existing
Starlette, openpyxl, Qdrant, FastAPI and MCP deprecation/fixture warnings.
An earlier diagnostic full run during active edits passed tests but measured
89.88%; it is not the final coverage evidence.

`uv run ruff check .`, `uv run ruff format --check .`, strict mypy on the
three configured packages (291 source files), `python -m compileall -q`,
`uv lock --check`, all three `uv build --package ...` jobs, `git diff --check`,
and frontend format/lint/typecheck/test/build all passed. Frontend Vitest:
one passed, 100% frontend coverage. No frontend source was changed. The
project environment emitted a non-fatal dangling temporary distribution-info
warning; no package installation or cleanup was performed.

The certified production DB remained SHA-256
`3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`,
189,804,544 bytes, UTC mtime `2026-09-01T11:09:20.1047581Z`;
WP16 remained SHA-256
`18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d`,
37,195,776 bytes, UTC mtime `2026-08-29T13:37:31.2308106Z`.
Neither had WAL, SHM or journal sidecars at either checkpoint. Production
manifest `e579727c8867c92d4ca7fe05256a35d74942077f86b86a6fad9938ff3b4fc566`
and certified launcher `007ee235783cb8f673a2f9c135bc38269ba2a355057c5cd119c0125e471fde22`
retained their SHA-256. Activation, certificate, final evidence and signed
pre-certification convergence retained, respectively,
`c17a7f5531cc75795fb63c6f53682d30eb6ed831127db95038d3d1741cd25525`,
`1a69e95796b98abcc1f4f6484692481058bff776b454a14e3a0b35d86f16312a`,
`0255160992fc1ed2fdc5b5c6bfb55bb442b55018655f511274d698569a06230c`,
and `b5ccccb9787773ef10f5a6364bbc80ed98324640ea5438da604ebfaf2b7c2b23`.
The registry still has exactly one active generation,
`fc85192e-f672-4cc0-9539-b4b063bb8f41`. This audit checked byte/hash
identity; it did not re-sign or regenerate historical certification evidence.

No production deployment, live tunnel restart, credential or manifest change,
protected-data mutation, commit or push occurred. The working tree remains
intentionally dirty. The next governed reader-specific step is deferred
8.8.2f; local forensic acceptance alone does not close Stage 6.
