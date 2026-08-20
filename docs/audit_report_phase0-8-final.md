# MNEMO PHASE 0–8 FINAL PRODUCTION CERTIFICATION

## Executive Summary

This report certifies the 2026-08-20 v0.25.0 release through ADR-0057 after a
fresh 15-document production ingestion. The audit found and fixed generic
lifecycle, parser, retrieval, transport, and serialization defects: derived
title cascade cleanup, production embedding-cache use, XLSX support, recursive
metadata serialization, bounded title-candidate selection, short root-level
code preservation, MCP SSE CLI option precedence, and PDF mixed/table-adjacent
span preservation. Every fix has focused regression coverage.

The local profile intentionally disables Qdrant. Its healthy operating mode is
SQLite/FTS sparse retrieval plus cross-encoder reranking; it must not be
described as vector-backed hybrid retrieval. The standard deployment enables
Qdrant for persisted 768-dimensional dense vectors.

## Golden Corpus

| Document | Parser | Chunks | Preservation | FTS/title | Retrieval | Final-QA | Verdict |
|---|---|---:|---|---|---|---|---|
| Bhagavad-gita-As-It-Is.pdf | PDF | 997 | early/middle/late chapters probed | synchronized | correct top document | grounded, resolved citations | PASS |
| server.js | PlainText/code | 152 | 99.4% meaningful-line character preservation; required symbols present | synchronized | symbol and semantic probes correct | grounded, resolved citations | PASS |
| Y24_CPI.csv | CSV/table | 31 | 1,174/1,174 data rows reconstructed | synchronized | beginning/middle/end rows correct | grounded | PASS |
| Coordinator Application 2026–27.pptx | PPTX | 21 | slide-aware structure retained | synchronized | title/slide probes correct | grounded | PASS |
| ME361 PPTX | PPTX | 23 | 23 physical slide chunks | synchronized | beginning/middle/end probes correct | grounded | PASS |
| ME333 LabReport_To_Submit.docx | DOCX | 6 | procedure/results/conclusion retained | synchronized | experiment probes correct | grounded | PASS |
| Atharv_Patil_RESUME_SDE.pdf | PDF | 5 | 7 blocks; education/projects/skills retained; 99.9% token preservation | synchronized | title/content probes rank Resume first | grounded, resolved citations | PASS |
| Panch Parmeshwar | PDF | 11 | all 8 physical pages represented | synchronized | title/content probe correct | retrieval validated | PASS |
| app.py | PlainText/code | 5 | byte-exact parse; module docstring/constants retained | synchronized | title/content probe correct | retrieval validated | PASS |
| ME381 lab days | XLSX | 4 | non-empty rows and headers retained | synchronized | title/content probe correct | retrieval validated | PASS |
| ME381 Lab group A1 | XLSX | 4 | non-empty rows and formulas retained | synchronized | title/content probe correct | grounded path validated | PASS |
| ME381 Lab group A2 | XLSX | 4 | non-empty rows retained | synchronized | title/content probe correct | retrieval validated | PASS |
| ME381 Lab group A3 | XLSX | 13 | non-empty rows retained | synchronized | title/content probe correct | retrieval validated | PASS |
| Research document | Markdown | 233 | 725 blocks and heading hierarchy retained | synchronized | title/content probe correct | retrieval validated | PASS |
| IITK transcript | PDF | 5 | all 3 physical pages represented | synchronized | title/content probe correct | retrieval validated | PASS |

Canonical counts are 15 documents, 15 versions, 15 sources, 1,514 chunks, 1,514
FTS rows, and 1,514 title-projection rows. SQLite integrity_check is ok;
duplicate chunk IDs and orphan version/chunk/FTS/title rows are zero. Runtime
sessions and Final-QA executions created through public lifecycle APIs are not
canonical corpus mutations and the local database is excluded from release.

## Previous Bug Fix Verification

Source-code parser routing, oversized declaration splitting, executable and
comment preservation, oversized table partitioning, short slide preservation,
Ollama think:false, repository configuration loading, MCP SSE ASGI ownership,
exact-version title projection and cascade cleanup, cached production embedding,
parent retrieval provenance, and title-aware reranking all have regression
coverage. Prompt routing is generic; production
code contains no Golden-Corpus filename, personal-name, document-ID, or
query-specific reranking rule. The live audit also found and fixed
a fusion deduplication defect: equal canonical chunks from distinct subqueries
could differ only in transient title provenance. Fusion now validates immutable
fields and deterministically merges those transient fields.

## Fifteen-Document Retrieval Audit

The real sparse-only path was exercised through HTTP and MCP:

`planner -> SQLite FTS/title projection -> source-local parent promotion -> RRF
fusion -> title-aware cross-encoder -> context projection`.

All fifteen title/content probes returned the expected top document. The original
failure, `What skills are listed in the resume? -> ME361`, was traced to title
provenance loss and then to an ADR-0042 validator/order mismatch. ADR-0057
defines the generic repair: title metadata is transient reranker input and
exact title provenance is a deterministic ordering tier. Persisted Chunk.text
and all source/document/version/chunk identities remain unchanged.

## Final-QA Audit

The live persisted endpoint produced grounded, cited answers for Resume, Gita,
server.js, and Coordinator evidence. Each used canonical `[source:N]` markers
and resolved exact-version citations. Matching replays returned immutable
results with `execution=replay`; deterministic tests prove zero model,
assistant, or citation writes. A changed fingerprint returned typed HTTP 409.

ADR-0054 tests cover first-pass compliance, case-sensitive rejection of
`[Source:N]`/`[SOURCE:N]`, exactly one corrective call, unchanged context and
model configuration, token preflight, cancellation, retry success, and
`citation_compliance` exhaustion without publication.

ADR-0056 tests cover atomic claim, concurrent callers, RUNNING fail-closed,
VALIDATED and ASSISTANT_PUBLISHED resume, PUBLISHED exact replay, fingerprint
conflict, legacy replay-unavailable, rejected replay, immutable snapshot
round-trip, rollback, provenance reconstruction, and crash/cancellation
windows. A deliberately disconnected live request remains RUNNING, correctly
demonstrating fail-closed behavior rather than successful publication.

The expanded-corpus audit published grounded persisted answers for PDF,
source-code, and PPTX evidence, including exact replay. XLSX and other
deliberately non-compliant attempts exhausted the
single corrective retry and returned typed integrity failures with no
assistant/citation publication, directly validating the failure boundary.

## Embedding / Dense Retrieval

| Item | Active local value | Evidence |
|---|---|---|
| Provider | Ollama | mnemo.toml and live health |
| Model | nomic-embed-text | configuration |
| Dimensions | 768 | configuration/provider contract |
| Cache | content-addressed SQLite cache, SHA-256(text)+model | implementation/tests |
| Vector store | Qdrant disabled | storage.qdrant.enabled=false |
| Local retrieval | sparse FTS/title plus reranker | live queries |
| Production dense path | Qdrant exact-version metadata projection | storage tests/Docker configuration |

The canonical SQLite database intentionally has no embedding table; vectors
belong to the embedding cache and Qdrant backends. Every fresh chunk has a
content/model cache identity (1,514/1,514, dimension 768). Historical cache
entries are safe content-addressed reuse, not active index projections. No local
dense-retrieval PASS is claimed while Qdrant is disabled.

## HTTP Complete Matrix

The FastAPI OpenAPI registry is authoritative. Default local auth mode is none;
API-key and JWT success/failure/isolation behavior is exercised by the server
test suite.

| Methods and routes | Router | Live evidence | Failure evidence | Result |
|---|---|---|---|---|
| GET /health, /v1/health | system | 200 | degraded component detail when Qdrant disabled | PASS |
| GET/PATCH /config, /v1/config; GET /config/models, /v1/config/models | system | GET 200 | validation/auth tests; mutation not used on corpus profile | PASS |
| GET /jobs, /v1/jobs, /{job_id} aliases | system | list 200 | invalid/missing job typed | PASS |
| POST /v1/query/stream | streaming | real event stream | invalid/auth/error-event tests | PASS |
| POST/GET/PATCH/DELETE /v1/notebooks[/{notebook_id}] | notebooks | temporary CRUD 201/200/204 | UUID 422, missing 404 | PASS |
| GET notebook /summary, /timeline, /graph | notebooks | real corpus 200 | UUID/missing typed | PASS |
| POST/GET/DELETE notebook /sources; GET source and /status | sources | real list/get/status | upload size/malformed/missing/auth in tests | PASS |
| GET/POST/DELETE notebook /sessions; POST /turns | sessions | live Final-QA lifecycle | ordering, UUID, mismatch, missing typed | PASS |
| GET/POST/PATCH/DELETE notebook /notes | notes | temporary CRUD 201/200/204 | missing 404, validation/auth tests | PASS |
| GET notebook /insights; POST /insights/generate | insights | list 200 | generation is explicit typed 501 | PASS |
| POST /v1/search | search | real corpus 200 | empty 422 | PASS |
| POST /v1/query | query preview | sparse and synthesized 200 | invalid/empty typed | PASS |
| POST /v1/notebooks/{notebook_id}/final-qa | persisted Final-QA | new/replay/conflict live | UUID/missing/mismatch/citation errors typed | PASS |

OpenAPI registers 41 method/path operations. Every operation is accounted for
above; destructive source ingestion/deletion, live config mutation, and the
explicitly unimplemented insight-generation operation were validated with
isolated application tests rather than against the certified corpus.

## Streaming / SSE

Live /v1/query/stream produced ordered retrieval_start, chunks,
citations_ready, and terminal done events with canonical server.js
attribution. Validation, error, disconnect, and cleanup branches are covered by
the streaming suite. Streaming remains transient and creates no Final-QA
execution, assistant turn, or citation publication.

## MCP stdio / MCP SSE

Both real transports negotiated MCP 2025-11-25, advertised mnemo-mcp, and
discovered/exercised all six tools: list_notebooks, get_notebook_summary,
search_all_notebooks, query_notebook, get_timeline, and get_source_insights.
Real corpus calls preserved notebook/source/document/chunk attribution; invalid
UUIDs produced typed tool errors. The SSE adapter uses raw ASGI endpoints so
Starlette does not emit a duplicate response.

## Database Integrity

Schema v6 migrations are transactional and idempotent. Version-aware title
projection and Final-QA execution/snapshot tables are derived/additive. Tests
cover fresh, old-schema, rollback, idempotency, stale projection, deletion,
exact-version isolation, write-once snapshots, and conditional transitions.
All fifteen document versions are current; no document is indexing or failed.

## Phase 0–8 Matrix

| Phase | Contract | Implementation/tests/runtime | Verdict |
|---|---|---|---|
| 0 | reproducible tools, CI, Docker | exact workflow commands, frontend and 3 Docker images pass | PASS |
| 1 | typed models/interfaces/registry | strict mypy and contract suites | PASS |
| 2 | SQLite/Qdrant/SurrealDB/filesystem composition | backend, transaction, migration suites; SQLite live | PASS |
| 3 | parser through canonicalizer | heterogeneous formats live on corpus; regressions for routing/PPTX/CSV/XLSX | PASS |
| 4 | deterministic semantic chunking | all chunker suites plus corpus preservation probes | PASS |
| 5 | embeddings/cache/index lifecycle | provider/cache tests; local Qdrant limitation explicit | PASS (configured mode) |
| 6 | planning through grounded Final-QA | ADRs 0038–0048, 0052–0057; live retrieval/Final-QA | PASS |
| 7 | thin REST/auth/stream adapters | 41-operation inventory, tests and live matrix | PASS |
| 8 | stdio/SSE MCP, six tools | both transports and six tools live | PASS |

## ADR Matrix

| ADR group | Current implementation | Status |
|---|---|---|
| 0001–0006 | domain, interfaces, configuration, composition, identity/dedup | consistent; ADR-0005 remains historically Proposed |
| 0008, 0011–0018 | parse/clean/classify/canonicalize/chunk/embed boundaries | implemented and tested |
| 0036–0039 | slides/docs/version projections/sparse retrieval | implemented and corpus-validated |
| 0040–0043 | parent promotion, RRF fusion, reranking, context | implemented; ADR-0057 narrowly supersedes ADR-0042 pair/order |
| 0044–0047 | generation, citation, Final-QA, composition | implemented and live-validated |
| 0048 | generic diversity/prompt intent | corpus signatures removed; generic routing tested |
| 0049–0051 | server, notebook/graph, ingestion APIs | implemented/tested |
| 0052 | strict citation publication boundary | implemented/tested/live |
| 0053 | source-title sparse projection | schema v6, migration and live retrieval PASS |
| 0054 | one corrective citation retry | implemented/tested |
| 0055 | persisted Final-QA HTTP adapter | implemented/tested/live |
| 0056 | immutable execution snapshot/replay | implemented/tested/live |
| 0057 | title-aware cross-encoder reranking | implemented/tested/live |

No historical ADR was rewritten to hide a conflict. ADR-0057 is the explicit
successor for the only frozen-contract mismatch found during live validation.

## Architecture / Documentation / Governance Consistency

The active architecture and roadmap distinguish transient /v1/query from
persisted Final-QA, sparse-only local operation from Qdrant-backed production
hybrid retrieval, and implemented successor ADRs from their historical design
state. README format support includes PPTX, XLSX, CSV, and source code. Historical
changelog and Phase-8 governance files remain immutable historical evidence;
their earlier corpus counts are not current certification claims. This report
is the current authority for the rebuilt fifteen-document corpus.

## Security Audit

| Area | Evidence/result | Severity |
|---|---|---|
| Auth/authz | none/API-key/JWT modes; notebook/session identity checked server-side | PASS |
| UUID/error mapping | malformed IDs 422; missing 404; conflicts 409; no unexpected live 500 | PASS |
| SQL/FTS | parameterized SQL and escaped terms; migration rollback tested | PASS |
| Files/uploads | bounded upload size, content hashes, controlled storage root | PASS |
| XML/ZIP/PDF | malformed/encrypted inputs typed; parser resource hardening remains Phase-13 work | P3 residual risk |
| Prompt injection | context explicitly treated as untrusted evidence | PASS |
| Persistence | no publication before citation compliance; replay/concurrency tests | PASS |
| MCP/SSE | validated arguments, read-only MCP tools, clean transport ownership; unexpected stream errors sanitized | PASS |

No credentials, bearer tokens, machine paths, personal IDs, or corpus-specific
rules are introduced by production changes.

## Production Code Audit

The changed paths are typed, deterministic, cancellation-aware, and tested.
SQLite transitions use conditional transactions; snapshots are immutable;
replay does not regenerate; title metadata remains derived; canonical chunks
are unchanged. Broad exceptions at backend/transport boundaries translate or
log failures and are not silent retrieval fallbacks. The ASGI SSE fix has one
response owner. No duplicated Final-QA orchestration exists in the HTTP layer.

## Frontend / Docker / Local CI

- Python: 1,411 passed, 1 skipped; coverage 90.20%.
- Ruff format/check: PASS.
- strict mypy over all three production packages: PASS (148 files).
- package builds: core/server/email-ingestion PASS.
- frontend frozen install, format, lint, typecheck, test, build: PASS.
- Docker core/server/UI builds and all three Compose config checks: PASS.
- git diff --check: PASS.

## GitHub Actions

The v0.25.0 release requires the complete `.github/workflows/ci.yml` run on the
release commit to be green before the tag and GitHub Release are published.
Local commands reproduce and pass all Python, frontend, and Docker jobs.

## Version / Commit / Tag / GitHub Release

- Release version: 0.25.0.
- Commit: the immutable commit referenced by tag `v0.25.0`.
- Tag: `v0.25.0`.
- GitHub Release: published only after the release-commit Actions run is green;
  main, tag, and release resolve to that same commit.

## Remaining Risks

- **P3 — Sparse-only semantic aliases:** with Qdrant intentionally disabled, exact canonical-title queries are reliable, but an untitled synonym such as `CV` for a document titled `Resume` is not guaranteed to receive title-match provenance. Vector-backed deployments remain the documented path for semantic alias recall.

- P3: adversarial archive/decompression resource limits are deferred production
  hardening; the current 50 MiB upload bound and malformed-file handling reduce
  but do not eliminate decompression-bomb risk.
- P3: the local certified profile does not exercise a live Qdrant service;
  Qdrant behavior is covered by backend tests and Docker build/config gates.
