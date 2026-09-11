# ADR-0071: Phase 8.5 Additive Migration and Index-Generation Lifecycle

- **Status:** Accepted
- **Implementation:** Implemented through WP-02 — schema v7 and generic SQLite generation
  lifecycle implemented/tested in 8.5.1; additive schema v8 durable processing
  records implemented/tested in 8.5.3; additive schema v9 immutable OCR results,
  regions, observations, failures, and independent OCR FTS projections
  implemented/tested in 8.5.4; additive schema v10 immutable vision results,
  visual embeddings, and independent visual-vector projection generations
  implemented/tested in 8.5.5; additive schema v13 language observations,
  immutable translation/transliteration derivations, and independently named
  multilingual vectors implemented/tested in 8.5.9; additive schema v14 now
  provides Vision/language text and multilingual-vector projection rows,
  immutable source/coverage manifests, governed resumable builds, validation,
  atomic promotion, and rollback. Production data generation and later
  behavioral certification remain pending operational gates.
- **Date:** 2026-08-24
- **Extends:** ADR-0002, ADR-0003, ADR-0018, ADR-0039, ADR-0053, ADR-0056
- **Supersedes:** Nothing

## Context

Phase 8.5 adds catalogs, jobs, derivations, structured/positional projections,
and multiple vector/index generations to deployments where optional backends
may be disabled.

## Problem

In-place mutation or implicit rebuild could damage certified Phase 0–8 data,
mix model spaces, or make rollback impossible.

## Decision

All Phase 8.5 schema changes are additive through the existing SQLite
`schema_versions` mechanism and transactional migration discipline. Derived
projections/indexes have immutable generation records binding schema,
canonical-input scope, provider/model/revision/config/preprocessing identity,
dimensions where applicable, build state, counts, checksums, timestamps, and
capability profile.

Builds occur side-by-side in `BUILDING`, validate to `READY`, and become active
only through an atomic alias/policy switch. Other states are `FAILED`,
`SUPERSEDED`, and `RETIRED`. Interrupted builds never serve. Rebuilds use
canonical records or retained exact original bytes; they never manually patch
individual derived rows. Optional backends are not enabled by migration.

Garbage collection is reference- and retention-aware and cannot delete an
active generation, immutable Final QA snapshot dependency, original evidence,
or live job output. Fresh, upgrade, idempotent, interrupted, rollback, and
mixed-capability deployment paths are required.

## Alternatives

- Mutate current indexes in place: rejected due to downtime and rollback risk.
- Re-ingest every corpus on upgrade: rejected because additive projections can
  rebuild independently and originals may be unavailable.
- One global generation: rejected because modalities/models migrate separately.

## Consequences

Temporary storage doubles during rebuild and operators need lifecycle tooling.
The active profile remains coherent and rollback is an alias switch.

## Compatibility

Canonical document/version/chunk/asset identities and existing FTS/vector
generations remain untouched. Qdrant/SurrealDB optionality is preserved.

## Migration

Each dependent ADR supplies an ordered migration with transactional schema
creation and resumable data build outside the schema transaction. Failed schema
migration leaves the prior version intact.

## Security implications

Generation builders enforce notebook scope, trusted inputs, cache isolation,
resource limits, and authorization on promotion/GC operations.

## Testing requirements

Test fresh/old databases, failure rollback, idempotency, crash at every state,
concurrent builders, checksum/count mismatch, alias atomicity, disabled
backends, snapshot references, and safe GC.

## Observability

Record generation/profile/state, scoped counts/checksums, build/promotion
latency, validation failures, storage use, and GC decisions without content.

## Rollback/recovery

Switch to the prior `READY` generation and stop builders. Schema additions may
remain dormant; canonical data is never rolled back destructively.

## Future-phase impact

Phases 9–13 can add UI, reasoning, plugin, and scale-specific generations using
the same lifecycle.

## Explicit non-goals

This ADR does not mandate a vector backend or permit destructive canonical-data
migrations.
