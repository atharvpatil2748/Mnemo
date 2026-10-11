# Stage 7 scope audit, Stage 6 forensic remediation and local closure

Date: 2026-09-27. This is an independent **local** source, disposable-fixture,
public-adapter and protected-state reassessment. It does not certify the running
tunnel, deploy this tree, publish these changes, promote Phase 8.6, or complete
Phase 8.8.

## Authority, scope and starting state

The checked-out `main` and `origin/main` were both
`5d2612fef6d26cc1e1b0547bb5bd3da6abf21187). Nothing was staged. There
were 17 modified tracked and four untracked intended 8.8.10/8.8.11 paths;
the complete inventory is visible in the closing Git status. These changes
were preserved. This audit changed only the scoped readiness probe, added one
independent regression file, and updated current documentation and this report.

Authority: [documentation hierarchy](../../README.md),
[current architecture](../../architecture/current/mnemo_architecture_v2.md)
§§21.3–21.10 and Product Stage 7,
[canonical roadmap](../../architecture/current/mnemo_engineering_roadmap.md)
Phase 8.8 steps 5–9 and Modules 8.8.10/8.8.11,
[governance index](../../governance/README.md),
accepted [ADR-0076](../../adr/active/ADR-0076-project-owner-engineering-certification-standard.md),
[ADR-0077](../../adr/active/ADR-0077-governed-mutable-workspace-boundary.md),
[ADR-0078](../../adr/active/ADR-0078-generation-aware-production-credential-lifecycle.md),
the [five-module forensic remediation](mnemo-stage-6-forensic-remediation-and-acceptance.md),
[prior GitHub batch closure](mnemo-stage-6-github-closure.md),
[8.8.10 local report](mnemo-module-8-8-10-local-implementation.md),
[8.8.11 local report](mnemo-module-8-8-11-local-implementation.md),
and the [inactive promotion gate](../../governance/active/phase_8_6_serving_promotion_gate.md).
The two local reports were treated as claims, not acceptance.

**Stage 7 naming:** the current architecture defines a future *Product Stage 7
— Ecosystem and Extensibility* (§19) and also uses “STAGE 7” for an ingestion
pipeline step (§12). A historical proposal uses that label for retrieval
planning. The canonical Phase 8.8 roadmap does **not** define a distinct
“Phase 8.8 Stage 7” scope or acceptance gate for this request. Product Stage 7
is not a synonym for Modules 8.8.10/8.8.11. The current architecture *does*
define Product Stage 7's five future deliverables, so its scope is resolved;
its implementation and certification are not. The Stage 7 forensic verdict
below applies to that authoritative Product Stage 7 only.

| Defined future Product Stage 7 item (§19) | Current implementation/evidence | Gate |
|---|---|---|
| Plugin SDK documentation | No scoped implementation/evidence supplied by this Stage 6 branch | Future product-stage review |
| Official EPUB and browser-history plugins | No scoped implementation/evidence supplied | Future product-stage review |
| Published OpenAPI specification | Existing HTTP schemas are not publication evidence | Future product-stage review |
| MCP specification-suite certification | Local MCP adapter tests are not specification certification | Future product-stage review |
| Open WebUI integration | No scoped integration evidence supplied | Future product-stage review |

## Requirement-to-code-to-independent-evidence ledger

| Requirement | Actual boundary | Independent observation and verdict |
|---|---|---|
| 8.8.10a, evaluation-only production selection | `production_storage_composition.py` canonical path preflight; certified runtime startup binding; central authorization | Inspected pre-I/O rejection and executed old/new `test_phase86_exposure_boundary.py`, path/symlink/relative and newly added Windows case-alias tests in `test_production_storage_composition.py`; evaluation registry tripwire never fired. Pass locally. |
| 8.8.10b, future promotion only | Inactive governance gate; no serving-role public selector | Compared gate's ten requirements with architecture §21.10 and source diff. No activation, allowlist or manifest edit. Pass locally. |
| 8.8.10c, isolation | Public MCP/HTTP and real local stdio/SSE tests; distinct disposable evaluation marker | Production notebook/search/delivery returned only production identity; unknown/evaluation IDs and client role/path/registry overrides denied safely. Pass locally. |
| 8.8.11a, authorized typed projection | `structured_v2.py` authorizes notebook and explicit source/document/version before `discover`; persisted reader joins exact version/document | Old/new public matrix, structured schema/engine tests, cursor/typed-input tests and 14-tool transport file passed. No arbitrary SQL or V1 fallback observed. Pass locally. |
| 8.8.11b, truthful scope-qualified availability | `structured_projection_ready_for_notebook`, catalog discovery, shared typed errors | New independent old/new fixture found and repaired a capability/query contradiction; failing-before and passing-after detail below. Pass after repair. |
| 8.8.11c, no activation | Existing route remains registered; lifecycle and production manifest untouched | Source diff, public capabilities and protected hash comparison show no projection creation, promotion or global activation. Pass locally. |
| Stage 6 earlier branch | F-1/F-2, 8.8.5/8.8.7/8.8.2f/8.8.4/8.8.8 | Re-executed the prior forensic file, immutable-schema matrix, all-tool direct/stdio/SSE/HTTP matrix and full CI-safe suite. Prior independent acceptance is not rewritten. |

## Finding S6-1: structured readiness contradiction

**Severity:** medium contract/capability truthfulness defect; no unauthorized
retrieval demonstrated. The new
`test_stage6_structured_forensic.py::test_scoped_structured_capability_requires_executable_projection`
creates a disposable persisted READY projection in both older and newer SQLite
schemas, closes the writer, removes its only canonical covering chunk from the
*disposable* DB, then reopens the immutable reader. Public HTTP
`POST /v2/retrieval/structured` correctly returned 503
`capability_unavailable`, because catalog discovery could not construct a
dataset candidate. Public scoped `GET /v2/capabilities` incorrectly returned
`structured_retrieval.available_for_scope=true`.

**Failed-first evidence:** with the new assertion in place and before the
product correction, both older and newer cases failed at
`assert True is False` (two failures). The focused-only invocation also
reported 28.01% repository coverage and failed the global 90% floor; that
coverage figure is *not* a full-suite result. Root cause: the readiness SQL
checked active READY generation and complete coverage, but not whether the
projection had a canonical covering chunk, whereas execution required one.

**Applied correction:** `mnemo-core/mnemo/storage/structured.py` now requires
a correlated, exact document/version/ordinal covering chunk in the bounded
`SELECT 1 ... LIMIT 1` notebook readiness probe. It does not load document
bodies, alter projection rows, broaden scope, change public DTOs or enable a
fallback. Both regressions then passed (2/2); the focused cross-module and
full CI-safe suites also passed. A malformed persisted schema or a concurrent
generation transition could still change availability between two separate
requests; the lifecycle response is a request-time observation, not an atomic
lease on future execution.

An additional independent Windows case-alias test uses an uppercase
`SCRATCH/EVALUATION_NOTEBOOKS/PHASE8_6/MNEMO.DB` selection against the
lowercase protected root. The production preflight denied it before any
evaluation-store open (3/3 relative/traversal/case variants passed). No
new product correction was required for this alias.

## Public, schema and transport matrix

| Path | Older schema | Newer schema | Evidence boundary |
|---|---|---|---|
| Direct MCP 14-tool dispatch | Pass | Pass | `test_mcp_immutable_schema_matrix.py`, `test_mcp_transport_contract_matrix.py`; canonical IDs, authorized success/error, empty and unavailable cases. |
| Real local stdio subprocess | Pass | Pass | `test_same_fixture_direct_and_real_stdio_contracts`; actual child and protocol codec, not a mocked handler. |
| Isolated loopback SSE | Pass | Pass | `test_same_fixture_direct_and_real_loopback_sse_contracts`; disposable authenticated process. |
| Existing HTTP counterparts | Pass | Pass | `test_same_fixture_http_and_public_mcp_v2_contracts` and public structured/production-isolation tests. No nonexistent HTTP endpoint was inferred. |
| New missing-covering-chunk probe | HTTP and direct MCP: typed unavailable / scoped capability false | Same | Independent reopened disposable fixture; real stdio/SSE separately exercise ordinary ready/unavailable structured contracts through the shared service, but not this exact corruption scenario. |
| Evaluation-only selection | Safe denial / no registry access | Safe denial / no registry access | Disposable production/evaluation markers, preflight aliases and registry tripwire; no live tunnel test. |

The common fixture exercises nonempty `list_notebooks`,
`get_notebook_summary`, `get_timeline`, `get_source_insights`,
`search_all_notebooks`, `query_notebook`, `search_evidence`,
`get_capabilities`, `query_structured`, `get_document`,
`get_document_chunk`, `get_asset`, `get_image_analysis`, and
`run_final_qa_v2` across direct MCP, real local stdio and loopback SSE.
Its HTTP comparison covers only existing counterpart routes. The fixture
reopens persisted OCR/Vision derivations, traverses signed structured/evidence
cursors, and distinguishes retained V1 synthesis from V2 FinalQA. It proves
local contract parity, not certified-model or external tunnel parity.

Authorization and ancestry checks were inspected through
`StructuredRetrievalApplicationService._authorize_scope`, the canonical
version-association reader, dataset catalog exact-version join, signed cursor
executor, and the earlier central authorization/partitioned F-1/F-2
regressions. Old/new fixtures distinguish authorized notebooks, document/
version mismatches, no projection, inactive/missing generation, READY empty
query and invalid typed requests. Capability probing occurs after notebook
authorization. The corrected readiness query remains notebook-scoped and
contains no evaluation registry reference. Unknown and unauthorized resources
do not acquire projection details. No protected database was opened writable.

## Executed verification and environmental limits

| Gate | Actual result |
|---|---|
| New independent regression, after fix | 2 passed, old/new |
| Focused cross-module run | 101 passed; selected files included structured, schema, immutable MCP, 8.8.10 exposure, prior forensic and real transport matrix |
| Expanded focused run | **130 passed** across the new forensic test, structured service/schema, older/newer public MCP, 8.8.10 exposure, prior Stage 6 forensic, all-tool transport, production-composition and capability files |
| Final exact-tree full `MNEMO_CI=1` pytest with unchanged >=90% enforcement | **2,720 passed, 18 skipped, eight warnings, 90.31% repository-wide coverage, 0 xfail/XPASS**, 539.94 s |
| Ruff lint / format | Passed; 523 Python files formatted |
| Strict mypy / compileall / `uv lock --check` | Passed; mypy 291 source files, lock 171 packages |
| Python package builds | Core, server and email-ingestion source/wheel builds passed |
| Frontend | format, lint, typecheck, one Vitest test and production build passed |
| Docker | three Compose configurations and core/server/UI image builds passed |
| Current-doc relative links / `git diff --check` | Passed at final checkpoint |

The existing `conftest.py` CI policy excludes 18 `local_database` cases.
The unrestricted historical
`test_post_certification_single_path.py::test_canonical_manifest_matches_signed_active_certified_state`
was executed separately **without** `MNEMO_CI=1` and failed at its
`all(lifecycle[key] is True ...)` assertion. It expects old manifest
lifecycle booleans inconsistent with the protected generation-aware manifest.
This unrestricted suite is **not** reported as passing. The manifest was not
changed; this historical local-database assertion needs a separately scoped
test/governance update, not a protected-artifact edit.

Representative exact commands (from the repository root unless noted):
`$env:MNEMO_CI='1'; .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --cov-report=term:skip-covered --tb=short`;
`.\.venv\Scripts\ruff.exe check .`;
`.\.venv\Scripts\ruff.exe format --check .`;
`.\.venv\Scripts\mypy.exe --strict mnemo-core/mnemo mnemo-server/mnemo_server plugins/email-ingestion/email_ingestion`;
`.\.venv\Scripts\python.exe -m compileall -q mnemo-core/mnemo mnemo-server/mnemo_server plugins/email-ingestion/email_ingestion`;
`uv lock --check`;
`uv build --package mnemo-core`, `uv build --package mnemo-server`,
`uv build --package mnemo-email-ingestion`;
`pnpm format:check`, `pnpm lint`, `pnpm typecheck`, `pnpm test`,
`pnpm build` in `mnemo-ui`;
`docker compose --file docker/docker-compose.yml config --quiet`,
`docker compose --file docker/docker-compose.dev.yml config --quiet`,
`docker compose --file docker/docker-compose.minimal.yml config --quiet`;
`docker build --file docker/core.Dockerfile --tag mnemo-core:stage7-forensic-local .`,
`docker build --file docker/server.Dockerfile --tag mnemo-server:stage7-forensic-local .`,
`docker build --file docker/ui.Dockerfile --tag mnemo-ui:stage7-forensic-local .`;
and `git diff --check`.

## Protected-state checkpoint

Read-only SHA-256, byte size and UTC mtime were recorded before and after.
All matched exactly:

| Database | SHA-256 | Bytes | UTC mtime | Sidecars |
|---|---|---:|---|---|
| Production | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | 189804544 | `2026-09-01T11:09:20.1047581Z` | none |
| WP16 | `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d` | 37195776 | `2026-08-29T13:37:31.2308106Z` | none |
| Evaluation 8.5 | `bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84` | 45592576 | `2026-09-08T06:41:25.6366051Z` | pre-existing 0-byte WAL, 32768-byte SHM |
| Evaluation 8.6 | `9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2` | 52600832 | `2026-09-08T08:14:51.7220651Z` | same |

Both evaluation WALs retained SHA-256
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`;
both SHMs retained
`fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb`.
Manifest, launcher, signed activation, certificate, final evidence and signed
convergence hashes remained, respectively,
`e579727c8867c92d4ca7fe05256a35d74942077f86b86a6fad9938ff3b4fc566`,
`007ee235783cb8f673a2f9c135bc38269ba2a355057c5cd119c0125e471fde22`,
`c17a7f5531cc75795fb63c6f53682d30eb6ed831127db95038d3d1741cd25525`,
`1a69e95796b98abcc1f4f6484692481058bff776b454a14e3a0b35d86f16312a`,
`0255160992fc1ed2fdc5b5c6bfb55bb442b55018655f511274d698569a06230c`,
and `b5ccccb9787773ef10f5a6364bbc80ed98324640ea5438da604ebfaf2b7c2b23`.
The non-secret registry view had exactly one ACTIVE generation:
`fc85192e-f672-4cc0-9539-b4b063bb8f41`. No secret value was read.

## Gate-by-gate decisions

| Gate | Decision |
|---|---|
| 8.8.10a–c, evaluation isolation and inactive promotion | Local forensic acceptance: source, disposable path/store tripwires, public old/new, four local transports, hashes pass |
| 8.8.11a–c, typed authorized projection and truthful readiness | Local forensic acceptance after S6-1 failing-before/passing-after repair and full regression |
| Earlier Stage 6 8.8.5/8.8.7/8.8.2f/8.8.4/8.8.8 | Prior independent acceptance retained; F-1/F-2, all 14 tools, error/metadata/routes re-executed |
| Formal Stage 6 **local forensic** branch, roadmap steps 5–7 | Closed by this report. Step 8 image search, step 9 live tunnel parity and subsequent Phase 8.8 gates remain separate. |
| Product Stage 7 forensic acceptance | Blocked: the architecture defines five future deliverables, but none has implementation and acceptance evidence for this milestone. No distinct Phase 8.8 Stage 7 gate exists. |
| Repository/GitHub publication, live tunnel, external ChatGPT, production deployment | Not performed or inferred from local evidence. Earlier GitHub closure covers only the prior five-module batch. |

**MODULE_8_8_10_FORENSICALLY_ACCEPTED**

**MODULE_8_8_11_FORENSICALLY_ACCEPTED**

**STAGE_7_FORENSIC_BLOCKED**

**STAGE_6_FORMALLY_CLOSED** — local forensic scope only; not GitHub, live
transport, deployment or Phase 8.8 closure.

## Changed-file and release boundary

The inherited unstaged implementation inventory at entry comprised five
current docs (`docs/README.md`, current architecture and roadmap,
`docs/governance/README.md`, `docs/reports/README.md`); core structured
retrieval/storage files; server structured schema, capability, composition and
service files; five existing server test files; plus the new promotion gate,
8.8.10/8.8.11 reports and exposure test. This audit's product diff is only
`mnemo-core/mnemo/storage/structured.py`; its test changes are the new
`mnemo-server/tests/test_stage6_structured_forensic.py` and a case-alias
variant in `test_production_storage_composition.py`. Current-status
documentation and the reports index link this new report. No files were
staged, committed or pushed. The production server/tunnel was not restarted;
no protected corpus, credential, signed artifact, serving role or promotion
state was modified.

The next authorized workflow is a separate publication/CI review of the
8.8.10/8.8.11 working tree and this report. Phase 8.8 still requires
`search_images` (8.8.12), live four-transport certification (8.8.9),
provenance completion (8.8.13) and the final 8.8.14d GO/NO-GO gate. A
future Product Stage 7 needs implementation and a defined acceptance protocol
before forensic acceptance can be awarded. No Phase 8.8 “Stage 7” is inferred.

## Closing checkpoint

The expanded focused command used `MNEMO_CI=1`,
`python -m pytest -q -p no:cacheprovider -o addopts=` and the nine test
files named in the table, exiting 0 with **130 passed in 69.12 s**. The
final current-document relative-link check and `git diff --check` passed.
The final working tree is `main...origin/main` at
`5d2612fef6d26cc1e1b0547bb5bd3da6abf21187`, with **17 modified
tracked files, six untracked intended files and zero staged files**.
The six untracked files are the 8.8.10 promotion gate, the 8.8.10 report,
the 8.8.11 report, the 8.8.10 exposure test, the new forensic regression
test, and this report. No commit, push, deployment, production restart,
tunnel restart, protected-store mutation or external ChatGPT verification
occurred.
