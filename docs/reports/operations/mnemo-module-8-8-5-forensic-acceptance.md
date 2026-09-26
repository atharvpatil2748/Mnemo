# Module 8.8.5 — independent local forensic acceptance

**2026-09-26 follow-up:** The later [combined independent audit](mnemo-stage-6-combined-forensic-audit.md) found that partitioned evidence enriched top-level items but omitted `source_metadata` from `partitions[].items`. The resolver-reuse claim below did not cover that nested view. The original verdict and counts remain historical; see the [remediation acceptance](mnemo-stage-6-forensic-remediation-and-acceptance.md) for the correction and fresh evidence.

**Verdict:** `MODULE_8_8_5_FORENSICALLY_ACCEPTED` (2026-09-26, local edited checkout only).
This is not deployment, a new production certificate, external ChatGPT verification,
completion of Stage 6, or Phase 8.8 completion.

## Authority, baseline, and scope

The current [architecture §21.7](../../architecture/current/mnemo_architecture_v2.md)
requires authorized additive presentation metadata, stable canonical IDs, one
reusable resolver, nullable filename, and no filesystem paths. The current
[roadmap Module 8.8.5](../../architecture/current/mnemo_engineering_roadmap.md)
requires (a) one envelope, (b) bounded reuse across retrieval, delivery,
image and citations, and (c) identity semantics independent of names.
[ADR-0076](../../adr/active/ADR-0076-project-owner-engineering-certification-standard.md)
fixes certified corpus/model identity; [ADR-0077](../../adr/active/ADR-0077-governed-mutable-workspace-boundary.md)
separates storage roles; [ADR-0078](../../adr/active/ADR-0078-generation-aware-production-credential-lifecycle.md)
governs activation. These accepted decisions and historical signed evidence
were not changed. The earlier [MCP contract audit](mnemo-mcp-failure-and-contract-audit.md)
specifies the additive `source_metadata` presentation contract. The
[Stage 5 acceptance](mnemo-phase-8-8-stage-5-acceptance.md) is prior local
evidence, not a substitute for this audit.

Initial Git: `main...origin/main`, HEAD
`069ec468a675c37544a5a2591eac1204c3cb6888`, no staged changes;
13 modified tracked files and two untracked files, all in the Module 8.8.5
implementation/test surface. The complete tracked diff, both untracked files,
their call sites, public schemas, authorization layer, scope resolver, and
disposable older/newer SQLite fixture were reviewed. No existing dirty source
or test change was reset, discarded, or reformatted indiscriminately.

## Requirement → code → independent test

| Requirement | Actual implementation | Executed evidence and assessment |
|---|---|---|
| 8.8.5a: one nullable authorized envelope | `mnemo-server/mnemo_server/services/source_metadata.py`: `SourceMetadataEnvelopeV1`, `AuthorizedSourceMetadataResolverV1`; exact version hash and persisted metadata | `test_source_metadata.py` exercises populated, legacy `filename`, missing and path-like values; old/new public MCP and HTTP tests compare identities/hash; PASS |
| 8.8.5b: bounded shared resolver | `source_metadata.py` checks authenticated principal, max 200 raw references, deduplicates; checks notebook, document/version scope, source association; response-size checks in delivery/retrieval/structured adapters | New 0/200-unique/201 boundary test and existing duplicate/mismatch tests; 94-test focused regression; PASS for the documented reference ceiling |
| 8.8.5c: names never determine identity | UUID-bound source/document/version resolution and exact persisted `content_hash`; retrieval/delivery/citation adapters carry canonical IDs separately | Renamed-version and duplicate-name tests; old/new public MCP identity assertions and HTTP unknown/mismatch/absent-chunk denials; PASS |

The envelope's `display_name` is a version-specific presentation fallback:
persisted `display_name`, then exact-version title, then persisted filename.
It is not an independent source registry field. `original_filename`, title,
MIME and display remain null if unavailable or unsafe. The content hash is
the exact resolved `DocumentVersion.content_hash`, not a name-derived hash.
The surrounding result retains chunk/asset/occurrence IDs, locator,
representation and retrieval-path provenance; these are not overwritten by
the source-level presentation envelope.

## Adversarial findings

- **Authorization and nondisclosure:** The resolver rejects an unauthenticated
  principal before lookup and rechecks notebook, document/version and optional
  source association. Missing and mismatched references use the same sanitized
  `authorized resource was not found` outcome. Public HTTP negative tests for
  unknown notebook, wrong document/version ancestry, and missing chunk exposed
  neither `source_metadata`, the fixture filename nor chunk text. The public
  MCP matrix also rejects mismatched and missing exact chunks and unknown
  notebook scope. This does not establish cross-user ACL isolation; the current
  authorization model is canonical notebook membership.
- **Bounds:** Empty input performs no document lookup. Exactly 200 distinct
  version references resolve under the ceiling without merging identities;
  201 fail before an additional document lookup. Repeated identical references
  resolve once. The resolver performs bounded per-reference scope/document
  lookups, not a single batch SQL query; this is a nonblocking performance
  consideration, not evidence of an unbounded number of requested references.
  The existing document aggregate may contain multiple versions; a future
  dedicated exact-version metadata projection could reduce read amplification
  without changing this contract.
- **Identity:** Two public fixture documents with the same original filename
  and title retain different source/document/version/chunk IDs. An old and
  current version of one document retain their own filename/title and version
  ID. Wrong source association fails closed. The pre-existing canonical scope
  resolver itself rejects ambiguous same-notebook duplicate source associations
  rather than assigning an arbitrary source; no filename-based disambiguation
  was introduced.
- **No path or secret publication:** The resolver suppresses slash/backslash,
  drive-prefix, control-character, empty and overlong display values, and
  validates MIME syntax. The reviewed additions contain no path-derived
  fallback, token, credential or SQL text in the envelope. The public negative
  tests assert absence of protected fixture strings, not merely an error code.
- **Read-only separation:** Public older/newer fixture tests use disposable
  SQLite databases and a genuine immutable read-only runtime reader. The
  protected production and WP16 databases were never opened writable, copied,
  migrated, reindexed or re-embedded for this audit.

No demonstrated Module 8.8.5 production-source defect was found. The new
audit tests are regression-evidence additions, not a policy or schema change.
The first 200-reference test fixture attempted duplicate version content
hashes, which the existing `Document` model correctly rejected; the fixture
was corrected to use distinct valid hashes and one current version. A first
focused run used repository-wide coverage enforcement on only 15 tests, so
pytest correctly rejected its 31% *focused-only* coverage. Focused runs were
then executed without a global coverage claim; the full CI-safe run enforced
the configured repository-wide 90% floor.

## Public route evidence and limits

| Route/path | Old/new schema evidence | Audit result |
|---|---|---|
| `get_notebook_summary`, `get_source_insights`, `get_timeline` | Real MCP `ClientSession` on both disposable schemas | Source/version metadata is authorized and attributable; PASS |
| `search_all_notebooks`, `query_notebook` | Real MCP session, scoped and global search/citations | Same-name sources stay distinct; scoped content and citation IDs preserved; PASS |
| `search_evidence` ranked/exhaustive | Real MCP session plus HTTP `/v2/retrieval/evidence` | Exact source/document/version/chunk, truthful old/new page positions, source envelope; PASS |
| `get_document` blocks and `get_document_chunk` | Real MCP session; exact HTTP chunk route | Authorized content/attribution; unknown and mismatched ancestors fail without metadata disclosure; PASS |
| Original document bytes | MCP dispatcher with mocked binary delivery; HTTP ASGI route with mocked binary delivery | MCP `_meta.sourceMetadata` carries authorized source identity. HTTP remains binary with documented identity/hash/range headers and no claimed JSON envelope; PASS at adapter level, not real production blob availability |
| `get_asset`, `get_image_analysis` | Dispatcher/bounded delivery service tests with mocked binary/analysis results | Shared resolver/attribution path inspected and tested; actual image generation/service availability is not asserted |
| `query_structured` | Service-level nested provenance test | Nested and dataset provenance share one authorized envelope; live public structured metadata remains an integration follow-up |
| `run_final_qa_v2` | Source inspection and full-suite FinalQA regressions | Citation metadata is resolved before persistence; no live FinalQA publication was performed in this read-only audit |

The immutable older schema has no page-range columns: persisted page number
survives, absent range stays null, and a constrained unsupported page-range
search returns explicit partial/unavailable behavior. The newer schema retains
its persisted page range. This audit did not repeat production CUDA scoring,
external tunnel requests, or full four-transport behavioral parity.

## Executed validation

- `CI=true MNEMO_CI=1 uv run pytest -q -p no:cacheprovider -o addopts=''`
  over the two metadata/public-schema files: **18 passed**.
- The same focused command over metadata, public schema, WP14 security,
  retrieval V2, delivery boundaries/MCP, and core scope/reader tests:
  **94 passed**, one local-Qdrant warning.
- `CI=true MNEMO_CI=1 uv run pytest -q -p no:cacheprovider`:
  **2,572 passed, 18 skipped, 8 warnings, 90.08% repository-wide coverage**;
  configured 90% floor passed. The three-test increase over the earlier
  implementation report is one boundary test plus two schema-parameterized
  HTTP binary tests.
- `uv run ruff check .`: pass. `uv run ruff format --check .`: 515 files
  formatted. `uv run mypy --strict mnemo-core/mnemo mnemo-server/mnemo_server
  plugins/email-ingestion/email_ingestion`: no issues in 290 source files.
  `uv run python -m compileall -q` on those three source roots: pass.
  `uv lock --check`: resolved 171 packages. `git diff --check`: pass.
- Frontend CI commands `pnpm format:check`, `pnpm lint`, `pnpm typecheck`,
  `pnpm test`, `pnpm build`: all passed; Vitest 1 passed. No frontend source
  was changed. The environment emitted a non-fatal warning about a dangling
  temporary `.venv` distribution-info directory; no global package change
  or cleanup was made.

## Protected-state checkpoint and disposition

Before and after testing, the certified production database remained SHA-256
`3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`,
189,804,544 bytes, UTC mtime `2026-09-01T11:09:20.1047581Z`; WP16 remained
SHA-256 `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d`,
37,195,776 bytes, UTC mtime `2026-08-29T13:37:31.2308106Z`.
Neither had `-wal`, `-shm` or `-journal` sidecars at either checkpoint.
The production manifest hash remained `e579727c8867c92d4ca7fe05256a35d74942077f86b86a6fad9938ff3b4fc566`;
the certified launcher hash remained `007ee235783cb8f673a2f9c135bc38269ba2a355057c5cd119c0125e471fde22`.
Activation, certificate, final evidence and signed convergence hashes remained,
respectively, `c17a7f5531cc75795fb63c6f53682d30eb6ed831127db95038d3d1741cd25525`,
`1a69e95796b98abcc1f4f6484692481058bff776b454a14e3a0b35d86f16312a`,
`0255160992fc1ed2fdc5b5c6bfb55bb442b55018655f511274d698569a06230c`,
and `b5ccccb9787773ef10f5a6364bbc80ed98324640ea5438da604ebfaf2b7c2b23`.
The registry still records exactly one `ACTIVE` generation,
`fc85192e-f672-4cc0-9539-b4b063bb8f41`; registry bytes and tunnel process
were not modified by this audit.

Additional audit changes are confined to
`mnemo-server/tests/test_source_metadata.py`,
`mnemo-server/tests/test_mcp_immutable_schema_matrix.py`, this report, and
the report index. No production source, credential, manifest, model, protected
artifact or certified runtime identity was changed. No commit, push, PR,
deployment or tunnel restart occurred. Module 8.8.7 and other downstream
Stage 6 tasks remain open. The running production server has not loaded this
locally edited 8.8.5 implementation, and no fresh external ChatGPT 8.8.5
verification has occurred.
