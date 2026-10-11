# Phase 8.9 notebook-governance cutover: incomplete execution record

This record separates implemented code and fixture evidence from the live
decommission. It is **not** a production certification, a reset receipt, or
permission to reuse the historical signed binding for a new index. The
[decommission audit](notebook-index-reset-decommission-audit.md) remains the
initial inventory; all destructive targets require fresh verification.

## Implemented and tested

- `mnemo-core/mnemo/corpus_identity.py` computes path-independent corpus,
  deployment, and index identities from an explicit source inventory and
  capability generation evidence. It does not assign authorization.
- `mnemo-server/mnemo_server/services/portable_corpus_runtime.py` verifies
  original bytes, a signed publication, physical database hash, and active
  generation records in read-only mode. `READY` is local artifact readiness,
  not serving permission or certification.
- `mnemo-server/mnemo_server/tools/legacy_reset_preflight.py` inventories an
  exact allowlisted store and rejects fingerprint mismatch, unknown notebook
  membership, active authority, nonempty SQLite sidecars, and unproved
  consumer quiescence. It has no deletion operation.
- `CentralAuthorizationServiceV1.authorize_notebook` now rejects an
  unauthenticated principal before notebook lookup. It still cannot establish
  authenticated actor membership because current persistence has no
  actor-to-notebook ownership relation.
- Focused fixture and existing runtime/security tests: 161 passed, one
  pre-existing deprecation warning. Ruff and strict mypy on changed source
  modules passed. These checks do not establish a safe live cutover.

## Live state and blocked actions

The configured production entry points in `mnemo-server/mnemo_server/app.py`
and `mnemo-server/mnemo_server/mcp/server.py` still call
`resolve_certified_production_binding`, then install the historical Full V2
composition. `mnemo.toml` and the production manifest still select the
historical Phase 8.5 index. The generic V1/V2 application services still use
notebook-scoped authorization. HTTP notebook CRUD currently has no persisted
per-actor ownership mapping. Changing only the startup path would therefore
weaken user isolation or silently break V1 compatibility.

That was the state at the time of the first implementation slice. In the
subsequent authorized pre-Phase-8.9 maintenance operation on 2026-10-09,
the same process tree was re-identified: `cmd.exe` 22332 launched Mnemo's
`.venv` Python 22400, which launched Python 22504. Both Python processes
identified as `certified-tunnel-stdio`; PID 22504 held the final-QA operational
database and sidecars open. `CloseMainWindow()` returned `false` for both
headless Python processes. Targeted `Stop-Process` calls for PID 22504 and
then PID 22400 succeeded. A second process scan found zero matching tunnel
Python processes; the parent `cmd.exe` also exited. No unrelated process
was targeted, and the tunnel was not restarted.

After the tunnel was offline and the production DB/registry had no observed
open process handles, the supported `ProductionCredentialRegistry.revoke`
operation revoked active generation
`fc85192e-f672-4cc0-9539-b4b063bb8f41`. A fingerprinted pre-retirement
registry copy was retained under
`scratch/phase8_9_decommission/2026-10-09/`. The pre-retirement registry
SHA-256 was
`9911e0d8b6326fc6291c7c1b850249720dc858d0acebd74c1bfda29e678c6487`;
the post-retirement registry SHA-256 was
`860e3166812c9b859945c5a58a149153f4a1cfd77fb1bb05754c6a08c2863a71`.
The registry reports no active generation. A certified startup probe rejected
with `MNEMO_ACTIVE_CREDENTIAL_UNAVAILABLE`. No signing key, credential secret,
or historical signed evidence was removed. This is **serving-authority
retirement**, not production runtime decoupling or index deletion.

The WAL-bearing preflight was corrected to use SQLite `mode=ro` rather than
`immutable=1` for logical counts. A disposable WAL fixture confirmed committed
rows are visible while the nonempty WAL remains a mutation blocker.

No database, notebook, alias, source file, or index record was deleted. The old
production and evaluation indexes still exist and must not be described as
decommissioned. Their five checked DB/registry SHA-256 fingerprints matched
the earlier baseline; all 44/44 and 24/24 source hashes matched their manifests.
One read-only SQLite forensic connection to the production-configured index
created a 32,768-byte `mnemo.db-shm` coordination sidecar (last write
2026-10-09T16:29:06Z; SHA-256
`fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb`).
The main database fingerprint did not change. The sidecar was preserved, not
removed or treated as an index deletion. This is an observed filesystem
side effect and a further reason to stop destructive work until a WAL-aware
snapshot/cleanup procedure is tested.

The remaining destructive phase is blocked by missing implementation, not by a test
failure: a persisted server-owned ownership/scope authority, a transport-shared
cutover, a replacement portable-index publication lifecycle, and a tested transactional
reference-aware cleanup executor (including contentless FTS and shared
document/version records) do not yet exist. The supported historical
credential revocation does not supply those missing contracts. No claim of
COMPLETE or Phase 8.9 GO is made.

## Protected-state check

The source manifests matched 44/44 and 24/24 original file sizes and SHA-256
hashes after this implementation slice. The five checked historical database
and registry SHA-256 fingerprints matched the preceding read-only baseline.
The 15 pre-existing top-level `goldenDataset/` tracked deletions were left
untouched. Other pre-existing working-tree modifications were preserved.

## Required continuation before any destructive operation

Implement and fixture-test ownership-aware authorization and user notebook
CRUD, replace the active HTTP/MCP startup through one shared application
service, then implement transactional reference-aware cleanup with WAL-aware
recovery. Recheck live consumers, fingerprints, source hashes, and exact
allowlists immediately before deleting any store. A new corpus rebuild and external
certification remain separate later phases.

## 2026-10-10 continuation — guarded startup and full-store cleanup slice

This section supersedes the earlier statement that HTTP/MCP startup still
*reaches* the historical binding. Both production transport entry points, the
certified config loader, and the binding resolver now check the explicit
`config/production/runtime-selection.json` first. Its only accepted current
state is `UNINDEXED`; production returns `PRODUCTION_CORPUS_UNINDEXED` before
opening the old index. The default `mnemo.toml` paths were changed to relative,
unindexed `data/notebook_runtime/` paths. The historical signed manifest and
credential evidence remain retained, but are not a fallback selection.
This is safe quarantine, not a new authenticated publication/serving cutover.

`SQLiteNotebookScopeAuthority` now persists explicit grants, and the central
authorization service can enforce them before notebook/document resolution.
It is not yet installed throughout all production routes or notebook CRUD;
existing notebook ownership has not been inferred or migrated. Multi-user
serving must remain blocked by the UNINDEXED gate until that gap is closed.

`legacy_decommission.py` implements an allowlisted, full-store-only executor.
It refuses partial notebook sets, unknown tables, unowned documents, user or
execution rows, changed DB/WAL/registry fingerprints, and active OS-reported
file consumers; it snapshots, unpublishes allowlisted evaluation aliases,
deletes inside an exclusive SQLite transaction, then checks FK, integrity,
and FTS state. A completed receipt makes repeat execution a verified no-op.
It deliberately does not provide partial-store or general
user-notebook deletion. A failed transaction leaves its snapshot for recovery.
No live executor invocation has occurred.

Fresh read-only inventory found no OS-reported consumers of the four known
DB files. Dry-run inventory accepted only their exact historical notebook
sets: production 1 notebook/44 documents/54 generations/1 alias (59,937
indexed rows); shared evaluation 2 notebooks/67 global documents/68 sources
(35,067 rows); registry phase8_5 1 notebook/44 documents (27,791 rows);
registry phase8_6 1 notebook/24 documents (29,285 rows). These aggregate row
counts include derived families and are *proposed*, not deleted counts.
The two evaluation stores also contain `evaluation_text_embeddings`, which
was classified from its chunk FK and included in the executor's known schema.
All four base-file SHA-256 values still matched the previous inventory:
production `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`,
shared evaluation `dc9e7fa2d1cb77f0e42ec3220377f74b1e2f98842acbfe487d1c7e6502fb2ada`,
phase8_5 `bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84`,
phase8_6 `9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2`.
SQLite read-only inspection may create SHM coordination sidecars; no WAL or
indexed row mutation is claimed from this inventory.

The original manifests were reverified against source bytes: 44/44 and 24/24,
with input identities `a915a7e4746841c6cd9c92b9b2a98abb46778928cd40387bbe4f9dac190abe85`
and `67feeac521afa836646de6b727c23413ddf2216fb77ed25b0024b3be09539eee`.
Disposable focused tests: 132 passed together (decommission, WAL, scope,
startup, binding, preflight, HTTP/MCP/storage) after
four historical production tests were updated to assert UNINDEXED refusal.
Ruff and strict mypy passed on affected source modules; compileall and
`git diff --check` completed without output. The repository-wide coverage
threshold was not established by these focused runs; an initial focused run
with default coverage settings passed four tests but failed the 90% global
coverage gate at 23.46%.

**Live decommission remains blocked.** The persistent scope authority is not
yet enforced for all notebook CRUD and transport paths, and the portable
signed-publication runtime is not installed as a usable replacement. The
full-store executor still lacks automatic recovery from interruption between
snapshot creation and final receipt, and has not been validated against every
populated derived family.
Consequently no live notebook, document/hash, generation, projection, or
registry row was deleted. The tunnel remains intentionally offline; the
revoked credential was not reactivated. No Phase 8.9 feature or new index was
started.

## 2026-10-10 final pre-Phase-8.9 reset execution

This section supersedes the preceding *live decommission remains blocked*
statement. The approved reset was executed after exact-identity, source-hash,
consumer, WAL, SQLite-integrity, and disposable-fixture checks. Production is
deliberately `UNINDEXED`; no replacement index or Phase 8.9 capability was
created. HTTP request dispatch, MCP dispatch, and direct MCP tool execution
now reject the unindexed production selection before touching historical
retrieval bindings, including paths that bypass application lifespan startup.
The persistent explicit-grant scope authority remains a separate requirement
for any future indexed multi-user serving; this reset does not certify that
future serving path or infer notebook owners.

The exact allowlists are in `config/decommission/pre_phase_8_9_targets.json`
and `config/decommission/partial_c976b97b_target.json`. The execution and
recovery evidence is in `scratch/phase8_9_decommission/2026-10-10/`:
`full-store-dry-run.json`, `full-store-execution.json`,
`partial-rebuild-dry-run.json`, `partial-rebuild-execution.json`, and
`snapshots/`. The four previously identified stores and the specifically
owned partial rebuild `c976b97b35cf4c319c4af3e28c136c97` were
transactionally emptied of notebook/index-family rows. Preflight counted
59,937, 35,067, 27,791, 29,285, and 29,322 indexed rows respectively;
post-checks found zero. These totals are effective pre/post row deltas,
including cascades and contentless FTS, rather than a sum of direct SQL
rowcounts. The evaluation registry aliases for the retired notebooks were
unpublished. Each store retains its empty schema, auditable receipt, and
recoverable snapshot; no database file was broadly deleted. All five stores
passed SQLite integrity and foreign-key checks and FTS probes returned zero.
Across the five stores, that is 181,402 indexed rows in the recorded inventory,
including 6 notebook memberships, 224 source rows, 223 document/version/hash
rows, 17,843 chunks, 35,686 chunk FTS rows, 8,501 evaluation text embeddings,
3,019 V2 multilingual embeddings, 2,169 OCR results, 2,018 Vision results,
1,990 visual embeddings, 105 structured table projections, 54 generations,
47 active-generation pointers, and one Full V2 alias set. The shared
evaluation document was removed only after both approved notebook memberships
were retired in the same store; no unrelated surviving notebook was found.

The 44- and 24-document source manifests were reverified against the original
bytes; credentials, keys, historical signed evidence, source manifests,
rebuild inputs, unrelated user/operational data, and the 15 pre-existing
top-level `goldenDataset/` deletions were preserved. The tunnel remained
offline and the revoked credential remained revoked. Other scratch databases
were **not** treated as part of this exact allowlist and remain unmodified;
this report does not claim a workspace-wide scratch purge or production
certification. The production baseline is offline, unindexed, and fail-closed.

## Decoupling closure and reference disposition

The historical certified index was bound to a notebook UUID, scratch build
path, database hash, credential generation, and alias. None is a portable
production selector. Current `config/production/runtime-selection.json`
admits only `UNINDEXED`. `ServerConfig.from_env`, HTTP lifespan and request
dispatch, MCP startup and dispatch, and direct MCP tool execution check this
selection before historical binding resolution. `mnemo.toml` uses relative
unindexed bootstrap paths. The retained signed manifest is historical
exact-identity evidence, not a fallback or current setup instruction.

Reference scan disposition:

| Reference family | Remaining location/class | Treatment |
|---|---|---|
| Retired notebook IDs, generations and DB fingerprints | `config/decommission/*.json`, `scratch/phase8_9_decommission/2026-10-10/` | Exact allowlists, receipts, recovery evidence; retain |
| Former Full V2 path and signed identity | `config/production/full_multilingual_v2.production.json`, historical binding/certification modules | Exact-identity historical verifier; current `UNINDEXED` startup cannot select it |
| Old evaluation database/path | `production_store_readiness.py`, evaluation/reindex scripts and fixtures | Negative selection guard or isolated fixture; not a production selector |
| Retired IDs in verification scripts and older ADRs/reports | Historical tests, scripts and evidence | Retain for reproducibility; not current production setup |
| Original source hashes and manifests | `config/rebuild/*.sources.json`, source files | Preserve as byte-integrity and rebuild input |

The active runtime scan found no retired notebook UUID in
`mnemo-core/mnemo` or normal production selection code. Historical hash
constants in `v2_certification.py` and its dependent verifiers remain
exact-identity historical certification code, not portable publication. The
old readiness script now rejects `UNINDEXED` before writing an artifact. A
source-inventory match is never an authorization grant.

The operational scope store persists explicit actor/notebook grants without
auto-enrollment. A notebook identity can now be retired to revoke its grants
and prevent later regrant under the same ID. This is a tested lifecycle
primitive, **not** proof that current CRUD or every future indexed HTTP/MCP
route enforces it. Under the present `UNINDEXED` gate all production
notebook-scoped reads and mutations remain blocked. Development/isolated
fixtures retain their existing notebook behavior. Indexed publication,
ownership-aware notebook onboarding, and all-route grant enforcement require
separate implementation and verification before the gate can be lifted.

[ADR-0081](../../adr/active/ADR-0081-pre-phase-8-9-unindexed-production-baseline.md)
records the lasting decision. ADR-0080 remains proposed and Phase 8.9 has
**not** started. The 181,402-row figure is an aggregate indexed-table delta,
not a count of unique logical documents. Detailed pre/post fingerprints and
WAL-aware recovery artifacts remain in the machine-readable receipts.

## 2026-10-10 final audit and documentation reconciliation

The current live checks reverified 44/44 and 24/24 source-manifest hashes,
`UNINDEXED` production selection, a revoked historical credential, zero
matching tunnel processes, and zero notebook/document rows in each of the five
retired stores. Their current base-file SHA-256 values match the post-reset
receipts; each has `integrity_check=ok` and no foreign-key violations. The
evaluation registry remains empty. No new `data/notebook_runtime/mnemo.db`
exists. Fifteen pre-existing top-level `goldenDataset/` tracked deletions
remain untouched. The audit did not rerun cleanup or alter source bytes.

This closure added a grant-store retirement/tombstone primitive and regression
test, and gated the old readiness-artifact script against `UNINDEXED`. It
updated `README.md`, `docs/README.md`, the current architecture and roadmap,
the architecture navigation, the transition document, the ADR index, this
report, and new ADR-0081. Historical signed artifacts and prior ADRs were not
rewritten. Relative-link checking of these documentation entry points found
zero broken links. A reference scan found retained retired IDs/hashes in
exact allowlists, receipts, historical certification/evaluation verifiers,
fixtures and old reports; no normal production startup selector uses one.

Focused security/decommission/identity tests: 34 passed in the final combined
run (the preceding narrower run passed 32). HTTP notebook,
source, note, session and core-scope fixture tests: 78 passed. A prior focused
post-reset run passed 123 tests. Ruff, affected-module strict mypy,
compileall and `git diff --check` passed. The repository-wide run was **not
green**: 2,911 passed, 49 failed, 5 skipped. A representative failure in
`test_v2_contract_storage_remediation.py` expects the now-retired database's
governed build row; `test_stage6_forensic_audit.py` expects a production-mode
fixture to pass the deliberately blocking `UNINDEXED` MCP guard. The
production-selection module passes 9/9 when run independently; its failures
in the complete run require test-order/fixture investigation. Do not interpret
the full-suite failures as production certification or hide them by changing
historical tests to claim the retired store remains active. The full suite's
`.pytest_cache` write also emits an access-denied warning. The historical
Phase 8.5 certification remains valid only for its retired exact identity.

Unimplemented indexed production serving and actor-to-notebook onboarding are
real limits, not completed work. The current safe outcome is the pre-Phase-8.9
offline, unindexed, fail-closed baseline; neither Phase 8.9 nor Phase 9 has
started.
