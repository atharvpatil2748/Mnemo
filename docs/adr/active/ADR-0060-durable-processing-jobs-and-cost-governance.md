# ADR-0060: Durable Processing Jobs and Cost Governance

- **Status:** Accepted
- **Implementation:** Complete — Phase 8.5.3 schema-v8 SQLite store,
  provider-neutral worker, leases, attempts, checkpoints, immutable results,
  bounded retry, cancellation, consent/budget policy, ledger, progress, and
  cleanup implemented/tested
- **Date:** 2026-08-24
- **Extends:** ADR-0002, ADR-0004, ADR-0009, ADR-0049
- **Supersedes:** The roadmap assumption that the first worker must be
  SurrealDB-specific; no accepted runtime ADR is superseded

## Context

OCR, VLM, translation, visual embedding, reprocessing, and model migration are
expensive and cannot safely execute as untracked synchronous HTTP work.

## Problem

Mnemo needs crash-safe claims, progress, cancellation, retry, consent, cost
limits, caching, and provenance while Qdrant and SurrealDB remain optional.

## Decision

Add provider-neutral `ProcessingJobStoreV1` and `ProcessingWorkerV1`. A job has
an immutable operation manifest and idempotency key, notebook/actor scope,
input identities, provider/model/config identities, requested operations,
consent record, estimates, hard budgets, and output cache keys.

States are `QUEUED`, `CLAIMED`, `RUNNING`, `CANCEL_REQUESTED`, `CANCELLED`,
`SUCCEEDED`, `FAILED_RETRYABLE`, `FAILED_FINAL`, and `BLOCKED_POLICY`.
Conditional transitions, expiring leases, monotonic attempt numbers, durable
checkpoints, and write-once result publications provide crash recovery.
Retries are bounded per operation policy and are distinct from provider-local
transient retries. Cancellation propagates where providers support it and
otherwise prevents publication after the safe boundary.

Cloud execution is disabled by default. Each manifest records explicit user
consent or an operator pre-authorization policy, estimated local/GPU/cloud
cost, and hard time/token/byte/currency ceilings. Cache hits are shown before
consent and do not create hidden provider calls.

## Alternatives

- Synchronous routes: rejected due to disconnect and duplicate-work hazards.
- SurrealDB-only queue: rejected because the core deployment permits it to be
  disabled.
- In-memory queue: rejected because it cannot recover after restart.

## Consequences

SQLite is the baseline durable implementation; other stores may implement the
same contract. Workers require lease, cleanup, and operator tooling.

## Compatibility

Existing ingestion and query paths remain synchronous and unchanged unless
explicitly adapted. The conceptual task/progress interfaces in ADR-0002 are
realized additively rather than redefined.

## Migration

Add job, attempt, checkpoint, consent, and cost-ledger tables transactionally.
No existing work is inferred as a job.

## Security implications

Claims are tenant-scoped; secrets are referenced by configured provider ID and
never stored in manifests. Cloud egress and budget changes are audited.

## Testing requirements

Test concurrent claims, lease expiry, crash windows, cancellation, bounded
retry, idempotent cache reuse, consent denial, budget exhaustion, poisoned
outputs, and migration rollback.

## Observability

Emit state transitions, queue/worker latency, attempts, resource use, estimates
versus actuals, cache outcome, and failure class without document contents.

## Rollback/recovery

Stop workers, reject new jobs, and retain state for later resume. Base Phase
0–8 operations remain available.

## Future-phase impact

Phase 9 consumes progress/cancel APIs; Phase 10 extends this common facility
instead of introducing an incompatible worker.

## Explicit non-goals

This ADR does not choose a cloud provider, scheduler product, or billing system.
