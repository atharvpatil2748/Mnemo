# ADR-0081: Explicit unindexed production baseline after legacy retirement

- **Status:** Accepted for the pre-Phase-8.9 baseline; not a Phase 8.9 GO
- **Date:** 2026-10-10
- **Scope:** Production selection, retirement, and notebook identity separation
- **Related:** ADR-0077, ADR-0078, ADR-0080

## Context

The historical certified Full V2 index was bound to a development-era notebook,
scratch build, database fingerprint and credential generation. Those exact
artifacts were valid for their past certification, but cannot become the
default identity of every future deployment or user notebook. Five allowlisted
legacy stores were decommissioned with retained receipts and recovery
snapshots; their source corpora and original hashes were preserved.

## Decision

Production configuration declares `UNINDEXED` explicitly. HTTP, MCP and
direct tool dispatch fail closed before historical binding resolution. A
historical signed manifest or source-inventory match is never a fallback,
authorization grant, or new production publication. Logical deployment and
corpus identity, physical database integrity, generation compatibility,
notebook ownership, and serving authorization remain separate checks.

Notebook IDs remain user-facing collection identities, not deployment
identities. The persistent grant store grants no access merely because a
notebook exists. A retired notebook identity cannot regain an old grant.
Original sources, manifests, credentials, signing keys, signed historical
evidence, and unrelated user data survive the reset.

The explicit unindexed baseline is intentionally not an indexed production
runtime. Indexed publication, all-route persistent-grant integration,
multi-user lifecycle certification, and Phase 8.9 unified retrieval require
separate evidence before serving is enabled.

## Rejected alternatives

- Select the latest or matching historical index: stale or evaluation data
  could silently become production authority.
- Treat a caller-supplied notebook ID as authorization: it permits scope
  guessing and cross-user disclosure.
- Delete whole scratch trees or shared databases: ownership and retained
  evidence are not established by path names.
- Reactivate the revoked credential or rewrite historical signatures:
  historical certification cannot certify a different index.

## Evidence

The [execution record](../../reports/architecture/phase-8-9-runtime-cutover-execution.md)
and its linked machine-readable receipts record the exact five-store reset,
source checks, post-reset integrity, and remaining limitations. This ADR
records the boundary; it does not retroactively change older ADR decisions.
