# Deterministic corpus runtime transition (pre-Phase-8.9 baseline)

This document retains earlier design and dry-run checkpoints below. They are
superseded by the [2026-10-10 reset execution](../../reports/architecture/phase-8-9-runtime-cutover-execution.md):
five exact legacy notebook/index stores were decommissioned, while production
remains offline and explicitly `UNINDEXED`. This is **not** a new indexed
production publication or Phase 8.9 GO. The retained 2026-08-31 signed
identity describes only its retired historical index; its active credential
generation was revoked on 2026-10-09.
Do not remove historical evidence or start a new serving mode by changing a
single path. The dependency audit is
[notebook-index-reset-decommission-audit.md](../../reports/architecture/notebook-index-reset-decommission-audit.md).

## Identity model

`mnemo.corpus-deployment-identity/1` is a domain-separated, canonical JSON
identity envelope. Its source inventory is the sorted, relative-path/size/SHA-256
entry list of `mnemo.rebuild-source-manifest/1`, not its absolute `corpus_root`
and not `notebook_input_identity` as a notebook designation. The latter is
verified as an existing source-list digest for compatibility with the current
rebuild manifests. Source bytes still require an independent hash preflight.

- **Corpus identity:** digest of the verified source-list digest. Identical
  source inventory has the same identity on different machines.
- **Deployment identity:** corpus identity plus explicit deployment key,
  profile fingerprint, parser digest, retrieval-policy digest, storage schema
  version, and sorted capability/profile digests. These are declarations from
  configuration, never read from a historical notebook or picked as “latest.”
- **Index identity:** deployment identity plus the exact sorted generation
  evidence digests for every configured capability. An index generation change
  changes the index identity; an absolute path move does not.
- **Physical storage integrity:** the actual database and immutable store
  artifacts need independent read-only hashes and a signed/otherwise
  authenticated serving publication. Logical identity is not a signature and
  must never be used alone as serving authority.

The pure identity computation and input validation are implemented in
[`corpus_identity.py`](../../../mnemo-core/mnemo/corpus_identity.py). It rejects
missing/incompatible source inventory and generation sets. This module does not
perform startup, index registration, certification, or authorization.
The read-only
[`portable_corpus_runtime.py`](../../../mnemo-server/mnemo_server/services/portable_corpus_runtime.py)
inspector can return `UNINDEXED` on a fresh workspace without a notebook row,
and admits a locally `READY` artifact only after checking original source
bytes, a signed publication, physical database SHA-256, exact generation
identity/checksum, and active generation rows. `READY` here is artifact
readiness, **not** permission to expose it to a principal or proof of
production certification. Current production MCP/HTTP startup instead checks
`config/production/runtime-selection.json` before loading a historical binding.
That selection is explicitly `UNINDEXED`, so both transports fail closed with
`PRODUCTION_CORPUS_UNINDEXED`. It is a quarantine, **not** a new indexed serving
path or a completed cutover to the portable inspector.

## Required serving and migration boundary

Future production startup must parse the declared corpus deployment, verify
source-manifest identity and actual indexed generation/storage evidence, and
fail with an explicit unavailable/incompatible state if the index is absent or
stale. The deployment key is an operator-selected stable name, not a hardcoded
UUID. A fresh empty workspace may load configuration and report an unindexed
corpus, but must not claim retrieval readiness or create an index implicitly.
Any compatibility UUID required by frozen V1 wire contracts must be derived
from the declared corpus identity and treated as an internal adapter token,
never as production serving or authorization authority. V1 remains canonical
only. MCP, HTTP, and future UI adapters must all call the same application
retrieval service. Sources, versions, occurrence/derivation chains, and typed
structured results must retain their real ancestry; a corpus identity cannot
replace document/source/version citations.

Notebook-based authorization cannot simply be deleted while V1/V2 requests
and `CentralAuthorizationServiceV1` still accept notebook scopes. Before a
production cutover, a server-owned corpus/scope authority must be implemented
and tested, including actor membership, cross-scope denial, exact-document
access, and post-read provenance checks. It must not infer membership from
filesystem paths or from the absence of a notebook registry. Evaluation
fixtures keep separate identities and never become production merely because
their source inventories match.
`SQLiteNotebookScopeAuthority` now persists explicit actor/notebook grants and
`CentralAuthorizationServiceV1` can enforce it before notebook and document
lookup. However, the authority is not yet installed on all production engines
or enforced by every notebook CRUD/transport path. Existing notebooks have not
been silently assigned owners. Thus this slice does not authorize serving
multi-user data after the current `UNINDEXED` guard is lifted.

The current certified V2 installer still verifies a path/build-run-bound
identity and active generation alias; the current code is **not yet using this
new identity to serve queries**. In particular,
[`v2_database_identity.py`](../../../mnemo-core/mnemo/phase85/v2_database_identity.py)
includes `target_path` and `build_run_id`, and
[`full_multilingual_v2_startup.py`](../../../mnemo-server/mnemo_server/services/full_multilingual_v2_startup.py)
loads that historical identity. Cutover requires a separately tested startup
branch, a new authenticated publication/retirement lifecycle, compatible
storage migration or adapter, and a rebuilt index. There is no implicit
fallback to the old notebook identity after retirement.

## Decommission preconditions

The old index cannot be removed while consumers may hold it open or while a
binding/registry alias can still select it. The identified tunnel processes
were stopped on 2026-10-09 and the credential registry's active generation was
revoked through its supported lifecycle, without deleting keys or historical
signed evidence. A further consumer/alias inventory and a consistent DB+WAL
recovery snapshot are still required immediately before any index cleanup.
Execute reference-aware cleanup only after disposable-fixture tests. Preserve
source bytes and manifests. A later rebuild is a separate operation; this
transition document does not authorize it.

[`legacy_reset_preflight.py`](../../../mnemo-server/mnemo_server/tools/legacy_reset_preflight.py)
is a read-only implementation slice: it checks an explicit store fingerprint
and notebook allowlist, detects shared documents, active generation/alias
state, core/production/evaluation configuration references, and nonempty WAL
or SHM sidecars. It always records unverified consumer quiescence as a blocker.
It does **not** execute deletion or certify a retirement receipt. A tested
retirement authority and transactional, reference-aware executor still need
implementation before any live reset.

`legacy_decommission.py` adds a fixture-tested full-store-only executor with
exact notebook/generation/alias allowlists, WAL-aware snapshots, consumer
checks, transactional deletion, FTS checks, and registry unpublication. It
refuses partial-store retirement and unclassified schemas; it is not a general
reference-aware notebook deletion API. The live historical stores have only
been dry-run inventoried and have **not** been mutated by this continuation.
`mnemo.toml` now points to an unindexed, relative `data/notebook_runtime/`
bootstrap location, while the historical signed production manifest remains
retained as historical evidence. No new database was created by that config
edit.

## Reset status update — 2026-10-10

The preceding dry-run-only statements describe an earlier checkpoint, not
the current persisted state. The exact four-store historical allowlist and
one separately verified partial-rebuild store were subsequently decommissioned
with the tested full-store executor. Their notebook/index-family tables and
retired evaluation registry aliases are empty; database schemas, recovery
snapshots, receipts, and historical signed evidence were retained. The
execution details and safety caveats are in
[`phase-8-9-runtime-cutover-execution.md`](../../reports/architecture/phase-8-9-runtime-cutover-execution.md).
Production remains `UNINDEXED`, offline, and fail-closed. This reset does not
constitute a new portable signed publication path, future multi-user serving
authorization certification, Phase 8.9 implementation, or production GO.
