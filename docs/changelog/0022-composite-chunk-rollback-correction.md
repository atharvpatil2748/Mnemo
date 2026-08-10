# Changelog 0022: Composite Chunk Rollback Correction

## Summary

Corrected the Phase 2 composite chunk-write compensation path. Failed
replacement upserts now restore the exact SQLite rows and Qdrant points that
existed before the attempt and remove only identities introduced by that
attempt.

## Engineering changes

- Added private affected-key snapshot and restore operations to the SQLite and
  Qdrant adapters, including Qdrant vector preservation.
- Serialized composite chunk mutations while snapshots and compensation are in
  flight.
- Rejected duplicate chunk identities within one bulk request.
- Removed unsafe document/version-wide deletion from upsert compensation.
- Added replacement, partial-write, mixed existing/new, idempotency, empty
  batch, preservation, and retry regression coverage.

## Compatibility

No public interface or model changed. This clarification implements the
existing ADR-0002 logical all-or-nothing guarantee and affects only failure
semantics. Successful upsert behavior remains compatible.

Qdrant has no distributed transaction with SQLite. Returned write failures are
compensated, but catastrophic process interruption during mutation or
compensation may require later reconciliation. Compensation failure is surfaced
as a typed storage error and is never represented as a successful rollback.
