# Phase 8.8 Stage 5 — local implementation acceptance

**Result:** `STAGE_5_COMPLETE` for the local checkout on 2026-09-25
(uncommitted at acceptance time). This records executable prerequisite-branch acceptance, not a
production deployment, external ChatGPT verification of this checkout, all-tool
behavioral parity, complete Module 8.8.2, or Phase 8.8 certification.

## Authority and scope

The [current roadmap](../../architecture/current/mnemo_engineering_roadmap.md)
defines Stage 5 as 8.8.2a–e/g, 8.8.3a–d, and 8.8.6a–c. It explicitly defers
8.8.2f until 8.8.7 supplies typed errors. The [current architecture](../../architecture/current/mnemo_architecture_v2.md)
requires compatible certified-corpus reads, authorization before disclosure,
and truthful capability lifecycle and effective identity. ADR-0076 fixes the
protected corpus/model identity; ADR-0077 separates mutable workspace; ADR-0078
keeps generation and certification state server-owned. Module 8.8.1 certifies
startup identity convergence only, not the tool matrix tested here.

## 8.8.2e public MCP schema matrix

[`test_mcp_immutable_schema_matrix.py`](../../../mnemo-server/tests/test_mcp_immutable_schema_matrix.py)
opens real disposable SQLite stores, removes both optional page-range columns
for the older variant, then reopens each database through
`SQLiteV2ReadOnlyRuntimeStore` (`mode=ro&immutable=1`). A real MCP `ClientSession`
initializes against `create_mcp_server`, lists tools, and invokes the public
tool protocol. Sparse/FTS, canonical advanced retrieval, chunk hydration,
exact-document chunk listing, resource authorization, and result serialization
execute production code. The fixture supplies parsed blocks in memory because
SQLiteStore does not persist parsed documents; `get_document` with a
`block_range` selector still reads the exact chunk list from SQLite. The fixture
uses a deliberately empty dense adapter so the test isolates the real sparse
schema path; it does not claim production embedding or reranker execution.

| Public tool | Older certified-style schema | Newer schema |
|---|---|---|
| `search_all_notebooks` | Scoped and global FTS hits retain chunk/document/version/notebook identity; actual page number retained, absent range `null`; unrelated scoped content absent | Same identities and scope; persisted page range 3–5 retained |
| `query_notebook` | Evidence-only query returns the scoped persisted chunk citation and page 3 | Same |
| `search_evidence` | Ranked and exhaustive canonical text return the scoped persisted chunk and `null` range. Page-range constraint returns `partial`, zero items and `canonical_text:source_failure:UnsupportedError`; it does not broaden the search | Ranked and exhaustive return the same identity with persisted range 3–5; page-range constraint matches |
| `get_document` | `block_range` delivery uses the exact SQLite chunk list; returned block attribution and overlapping chunk ID agree | Same |
| `get_document_chunk` | Exact persisted chunk and source attribution returned; absent range stays `null`. Cross-document and nonexistent chunk requests fail without content disclosure | Same, with persisted range 3–5 |

Unknown notebook scope fails. Global search is not claimed to demonstrate
cross-user ACL isolation: Mnemo's current policy is canonical notebook
membership, not actor-to-notebook ACLs. The older-schema partial response is
the current explicit unavailability contract; preserving a more specific typed
originating reason through MCP remains task 8.8.2f after Module 8.8.7.

The actual certified production database was separately opened through the
immutable runtime reader. Scoped `CPI` sparse search returned two hits;
`get_chunk` and exact-version chunk listing agreed on the first chunk
(`09356b4a03754c4214c25bc379a66815b18753c7aceaaaffeea6cac86aa0b34a`;
31 exact-version chunks). Unconstrained canonical enumeration returned two
records. The physical schema has no page-range columns and the selected
chunk's page range remained unavailable. This was a read-only local check,
not a production MCP transport test.

## Other Stage 5 branches

- **8.8.2a–d/g:** Shared `ChunkReadModel`, truthful locators, compatible
  retained readers, older/newer storage tests, and protected corpus
  immutability remain in the checkout. The new public protocol matrix and
  focused storage tests passed. 8.8.2f is deliberately not accepted here.
- **8.8.3a–d:** Trusted MCP principal, centralized 14-tool authorization,
  non-disclosure, and forbidden override rejection remain implemented and
  regression-tested. Earlier live ChatGPT calls demonstrated authorized reads
  and an extra-argument rejection, but did not establish cross-user ACLs,
  invalid-credential rejection, or full four-transport behavioral parity.
- **8.8.6a–c:** Lifecycle states, effective server-owned identity and distinct
  image capability states remain implemented. Local capability and principal
  tests passed. At acceptance time, this capability change was uncommitted,
  undeployed, and not independently tested through ChatGPT.

## Executed validation and protected state

- Focused public matrix: **2 passed**.
- Consolidated storage/MCP/security/capability focused run: **129 passed**, one
  existing MCP resource deprecation warning.
- Full CI-safe pytest (`CI=true MNEMO_CI=1`, project `.venv`,
  `python -m pytest -q -p no:cacheprovider`): **2,556 passed, 18 skipped,
  8 warnings, 90.06% repository-wide coverage**.
- `uv run ruff check .`, `uv run ruff format --check .`, strict mypy on the
  configured production packages (289 source files), compileall,
  `uv lock --check`, and `git diff --check`: **PASS**.
- Production DB before/after: SHA-256
  `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`,
  189,804,544 bytes, UTC mtime `2026-09-01T11:09:20.1047581Z`, no
  WAL/SHM/journal sidecars.
- WP16 DB before/after: SHA-256
  `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d`,
  37,195,776 bytes, UTC mtime `2026-08-29T13:37:31.2308106Z`, no
  WAL/SHM/journal sidecars.
- Production manifest SHA-256
  `e579727c8867c92d4ca7fe05256a35d74942077f86b86a6fad9938ff3b4fc566`
  and certified launcher SHA-256
  `007ee235783cb8f673a2f9c135bc38269ba2a355057c5cd119c0125e471fde22`
  remained unchanged.

No production code, protected corpus, configuration, credential, tunnel,
active generation, or signed certification evidence was changed by this
8.8.2e task. No commit, push, deployment, migration, reindex, or embedding
regeneration occurred. The prior dirty 8.8.2/8.8.3/8.8.6 work was uncommitted
and preserved at acceptance time.

## Next canonical sequence

Stage 6 begins with Module 8.8.5 (authorized metadata envelope), then Module
8.8.7 (typed MCP errors), followed by the deferred 8.8.2f integration. Module
8.8.4 requires completed Modules 8.8.2 and 8.8.3; 8.8.8 follows 8.8.4.
Neither Stage 5 acceptance nor this report authorizes Phase 9.
