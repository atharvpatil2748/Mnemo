# Module 8.8.7 — local typed-error implementation

**Local verdict:** `MODULE_8_8_7_LOCALLY_VERIFIED` on 2026-09-26. This
uncommitted implementation has not been deployed or externally verified; it
does not complete Stage 6, deferred 8.8.2f, or Phase 8.8.

## Contract and scope

The current [architecture §21.8](../../architecture/current/mnemo_architecture_v2.md)
and [engineering roadmap Module 8.8.7](../../architecture/current/mnemo_engineering_roadmap.md)
require ten safe categories, an originating safe code and correlation ID, and
nonreflection of SQL, paths, secrets, and inaccessible identities. This extends
the existing ADR-0049 HTTP envelope without changing the accepted certified
composition or ADR-0076/0077/0078 authority boundaries.

`mnemo_server.typed_errors` is the one classifier. Its categories are
`invalid_input`, `unauthorized`, `not_found`, `capability_unavailable`,
`configuration_mismatch`, `schema_compatibility`, `retrieval_failure`,
`transport_failure`, `timeout`, and `server_failure`. Public fields are
`code`, `category`, static safe `message`, bounded allowlisted `details`,
`retryable`, `origin_code`, `layer`, `reason`, and `correlation_id`.
Only known interface codes and known physical-schema reasons survive wrapping.
Authorized FinalQA timeout/reconciliation errors retain a validated UUID
`execution_id`; arbitrary exception text and client input do not.

HTTP maps the shared classification into its retained `error` envelope and
`X-Mnemo-Correlation-ID` header. API-key/JWT middleware uses the same envelope
for authentication failures. MCP `tools/call` maps it to an `isError` result
with matching text and structured content; server-side argument checking
replaces SDK validation-message reflection. The same dispatcher covers local
stdio and SSE MCP sessions. Retained V1 query WebSocket/SSE events keep their
legacy event codes but use sanitized messages and a correlation detail.
Unexpected failures log class and safe classification, not raw exception text.

Governed production unknown and inaccessible resources remain the same public
not-found shape. The retained direct legacy delivery authorization contract
keeps a generic HTTP 403; its raw resource message is suppressed. No
authorization, runtime-binding, capability, or certified storage policy is
weakened. The original reader-specific 8.8.2f propagation and acceptance
matrix remain a separate follow-up after this infrastructure.

## Executed local evidence

- Public disposable older/newer-schema MCP tests cover wrong, absent, and
  denied resource identities, distinct correlations, and a nested
  `StorageError` → `PluginError` schema reason without `sq-2:sparse` leakage.
- A real disposable loopback SSE MCP session and a real project-local stdio
  subprocess both returned typed, sanitized tool errors. The SSE fixture used
  synthetic core configuration; its initial attempt with the default
  production-corpus path was correctly rejected by certified startup and
  did not touch the corpus.
- HTTP adapter, auth, FinalQA timeout, retained SSE, and taxonomy regressions
  cover safe details, legacy status, malformed input, and secret-like error text.
- Final CI-safe command: `CI=true MNEMO_CI=1 uv run pytest -q -p
  no:cacheprovider --tb=short`: 2,605 passed, 18 skipped, eight warnings,
  90.11% repository-wide coverage. The warnings are existing Starlette,
  openpyxl, Qdrant, FastAPI, and MCP deprecations/fixture warnings.
- `uv run ruff check .`, `uv run ruff format --check .`, strict mypy on the
  three configured packages (291 source files), compileall, `uv lock --check`,
  `git diff --check`, frontend format/lint/typecheck/test/build, and all three
  configured Python package builds passed.

New error regressions used disposable fixtures. The certified production and WP16
database hashes, sizes, UTC mtimes, and absence of SQLite sidecars matched
their established baselines before and after validation. The production
manifest, launcher, signed activation, certificate, final evidence, and
convergence hashes remained unchanged. No credential, generation, model,
tunnel, commit, or deployment operation was performed.
