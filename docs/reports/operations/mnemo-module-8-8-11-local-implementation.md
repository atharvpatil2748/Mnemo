# Module 8.8.11 — local implementation and verification

Date: 2026-09-27. Scope: Phase 8.8 Stage 6, structured retrieval contract.
This is implementation evidence, **not** an independent forensic audit,
production activation, live-tunnel certification, or Stage 6 closure.

## Authority, baseline, and contract inventory

`main` and `origin/main` were both at
`5d2612fef6d26cc1e1b0547bb5bd3da6abf21187`; nothing was staged. The
existing eight modified and three untracked paths belonged to locally verified
Module 8.8.10 and were preserved. Current authority is `docs/README.md`,
architecture §§21.3–21.8 and the canonical execution order, roadmap Module
8.8.11, accepted ADR-0063/0076/0077/0078, and the Stage 6 batch acceptance
and GitHub closure reports. The Phase 8.6 serving-promotion gate remains
specified but inactive. The prior 8.8.10 report is local implementation
evidence, not independent acceptance.

The pre-existing public contract was `StructuredRetrievalRequest` and
`StructuredRetrievalResponse` (`mnemo.structured/v2`): typed `describe`,
`query`, `union`, and equality `join`; exact notebook/version scope; explicit
dataset IDs; typed filters, sort, aggregation, bounded rows/fields/groups,
signed snapshot-bound pagination, and row/cell provenance. Both
`query_structured` MCP and `POST /v2/retrieval/structured` use
`StructuredRetrievalApplicationService`. Discovery and execution use
`StructuredDatasetRuntimeService` and the persisted SQLite projection reader.
There is no arbitrary SQL or duplicate structured service.

Before this pass, `describe` could return `completeness=empty` when no READY
projection existed. The query path classified a non-ready selected generation
as invalid input. Scoped `get_capabilities` had no notebook-specific structured
readiness probe. Explicit source/document/version IDs were not checked before
projection discovery. The catalog's version join did not explicitly assert
document ancestry, and `page_size=true` was accepted as 1.

## Implementation traceability

| Requirement | Implementation | Regression evidence |
|---|---|---|
| 8.8.11a: authorized typed projection only | `structured_v2.py` authenticates and checks notebook, explicit sources and exact document/version associations before discovery; authorization is deadline-bound. A bounded canonical version-association lookup works even when no document ID is supplied. `storage/structured.py` binds projection version to its document. Existing typed executor and signed cursor remain unchanged. | `test_structured_v2.py`, `test_structured_schema_boundaries.py`, old/new public matrix and 14-tool transport matrix |
| 8.8.11b: truthful unavailability | No READY scoped projection and selected non-ready generation raise `DependencyUnavailableError`, mapped by the shared typed boundary to `capability_unavailable`/503. A ready projection with zero matches still returns a successful `empty` response. A bounded persisted notebook readiness probe drives scoped capability availability. | Missing/inactive generation and no-projection tests on both supported schemas, direct MCP and HTTP assertions |
| 8.8.11c: no automatic activation | No projection writer, production manifest, generation, model, allowlist, registration or startup activation was changed. Global tool registration remains distinct from notebook-scoped availability and certification. | Git diff inspection, capability assertions, protected-state checks |

Scope lists are limited to 100 IDs by the public DTO; a parameterized canonical
version-association lookup is scoped to the authorized notebook and does not
touch projection tables. Each returned association is rechecked by central
authorization before discovery. The work is further bounded by the configured
structured evidence ceiling and execution deadline. Unknown versions and
cross-notebook document/version pairs return the same safe `not_found` result
before a projection query. No filename, title or client path authorizes a result.
Request `page_size` is now strict integer, closing boolean coercion. An
explicit source set must also contain the source returned by exact
document/version authorization; independently valid but mismatched IDs cannot
select a projection.

## Disposable fixture and public matrix

`test_mcp_immutable_schema_matrix.py::_fixture` writes a disposable SQLite
corpus with two distinct notebooks, sources, documents and versions, then
reopens it through the immutable V2 reader. Both the older schema without
optional chunk page-position columns and the newer schema are exercised. A
persisted table projection is present only in the first notebook. The test
checks:

| State | Direct MCP / HTTP observation | Capability observation |
|---|---|---|
| Authorized READY projection | `describe` returns the same nonempty dataset descriptors; typed query with no matching CPI rows returns successful `empty` | `available_for_scope=true` |
| Authorized notebook without projection | Shared typed `capability_unavailable`, HTTP 503, safe MCP error | `available_for_scope=false` |
| Persisted generation deactivated | After closing, updating and checkpointing **only the disposable DB**, and reopening: typed unavailable | `available_for_scope=false` |
| Persisted generation missing | Same disposable reopen sequence: typed unavailable | `available_for_scope=false` |
| Cross-notebook document with an authorized notebook | `not_found` before projection discovery, no metadata in error | No foreign projection identity disclosed |
| Unknown version in an authorized notebook | `not_found` before projection discovery | No unknown projection identity disclosed |

The existing public transport suite compares all 14 tool families over a
common fixture through direct MCP, real local stdio, disposable loopback SSE
and actual HTTP counterparts. The structured family has direct MCP/stdio/SSE
nonempty, typed unavailable, unknown-resource and safe-invalid evidence;
this pass additionally compares direct MCP and HTTP ready, empty, unavailable
and cross-scope results. Those local
tests do not certify the live tunnel or replace Module 8.8.9.

Existing structured tests cover typed predicates, grouping, aggregate,
union, join, invalid fields, SQL-shaped input, signed cursor tampering and
scope binding, pagination, timeout and provenance. The old/new public matrix
and Stage 6 forensic regressions cover authorization, metadata, 8.8.2f typed
reader errors, capability lifecycle, 8.8.8 routing and 8.8.10 isolation.
No historical V1 or evaluation store was selected by the new route.

## Validation and protected-state result

Final focused structured, capability, old/new MCP and HTTP, transport-matrix
and 8.8.10 isolation tests: **105 passed**. The complete CI-safe repository
suite finished with **2,717 passed, 18 skipped, eight warnings, zero xfails,
90.30% repository-wide coverage** (284.57 seconds). The established
`MNEMO_CI=1` policy excludes 18 `local_database` tests; a prior unrestricted
diagnostic run encountered the protected-manifest lifecycle assertion and is
not used as the comparable CI-safe result. The protected manifest was not
altered to satisfy that historical assertion.

Ruff lint and format, strict mypy (291 source files), Python compileall,
`uv lock --check` (171 packages), three Python package builds, frontend
format/lint/typecheck/test/build (one Vitest test), three Compose configuration
checks and `git diff --check` passed. Docker daemon was available; core,
server and UI image builds all passed locally. The final core build took longer
because it downloaded pinned dependencies; it did not contact production.
Relative links in the six changed documentation files resolve. There is no
new xfail or skip.

At the pre-test checkpoint the production and WP16 databases matched hashes
`3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`
and `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d`
at 189,804,544 and 37,195,776 bytes, with their certified UTC mtimes and
no SQLite sidecars. Evaluation Phase 8.5 and 8.6 databases matched
`bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84`
and `9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2`.
Their pre-existing zero-byte WAL and 32,768-byte SHM sidecars were preserved.
Manifest, certified launcher, signed activation, certificate, final evidence
and convergence artifact hashes matched the 8.8.10 baselines. The registry
reported exactly one ACTIVE generation,
`fc85192e-f672-4cc0-9539-b4b063bb8f41`; no secret was printed.

## Closing checkpoint, changed files, limits and handoff

Post-test hashes, certified byte sizes and UTC mtimes for all four databases
matched the pre-test checkpoint. Production and WP16 remained sidecar-free;
the evaluation databases retained their pre-existing WAL/SHM sizes and hashes.
The protected manifest, launcher, signed activation, certificate, final
evidence and convergence hashes also matched the pre-test accepted identities.
Exactly one ACTIVE credential generation remained. No protected artifact was
repaired, migrated, reindexed or promoted.

This module changed `mnemo-core/mnemo/retrieval/structured_datasets.py`,
`mnemo-core/mnemo/storage/structured.py`,
`mnemo-core/mnemo/storage/composite.py`,
`mnemo-server/mnemo_server/schemas/structured_v2.py`,
`mnemo-server/mnemo_server/services/structured_v2.py`,
`mnemo-server/mnemo_server/services/capabilities_v2.py`,
`mnemo-server/tests/test_structured_v2.py`,
`mnemo-server/tests/test_structured_schema_boundaries.py`,
`mnemo-server/tests/test_mcp_immutable_schema_matrix.py`, and the pre-existing
8.8.10-modified `test_mcp_transport_contract_matrix.py`. Current-status
descriptions were updated in `docs/README.md`, the current architecture and
roadmap, `docs/governance/README.md`, and `docs/reports/README.md` to link this
report. The prior 8.8.10 source/test/report edits were not reset or staged.

No production projection was created, promoted, reindexed or activated.
Missing parsed-document representations in the certified corpus remain outside
this module. Scoped capability availability is evaluated at request time for
the authorized notebook; it is not a live-tunnel certification claim. Module
8.8.10 remains locally verified and independently unaudited. Stage 6 must
wait for the planned **independent combined 8.8.10/8.8.11 forensic audit** and
formal roadmap closure assessment. Phase 8.8 and Module 8.8.9 remain separate.

For that independent audit, reproduce the new tests in
`test_structured_v2.py`, `test_structured_schema_boundaries.py` and
`test_mcp_immutable_schema_matrix.py` against both disposable schemas; run
the unchanged `test_stage6_forensic_audit.py` and
`test_phase86_exposure_boundary.py`; compare `query_structured` and scoped
`get_capabilities` through direct MCP, local stdio/SSE and the existing HTTP
routes; challenge exact ancestry, missing/inactive generations, valid empty,
cursor replay, malformed input, evaluation-only and historical fallback.
Recompute all four database and signed-artifact identities before and after.

Subtask verdicts: `MODULE_8_8_11A_LOCALLY_VERIFIED`,
`MODULE_8_8_11B_LOCALLY_VERIFIED`, and
`MODULE_8_8_11C_LOCALLY_VERIFIED`. Module verdict:
`MODULE_8_8_11_LOCALLY_VERIFIED`.

No commit,
push, deployment, production restart, tunnel restart or protected-store write
was performed by this implementation run.
Final Git state: `main...origin/main` at
`5d2612fef6d26cc1e1b0547bb5bd3da6abf21187`, 17 modified tracked paths,
four untracked intended files (three inherited from 8.8.10 and this report),
and zero staged files.
