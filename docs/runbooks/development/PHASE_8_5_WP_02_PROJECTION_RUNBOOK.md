# Phase 8.5 WP-02 Projection Operator Runbook

**Status:** Internal application-service runbook. No WP-03 HTTP/MCP or WP-15
production-profile command is implied.

## Preconditions

1. Work on an isolated database/blob clone. Never migrate the certified
   Phase 0–8 Golden Corpus.
2. Resolve one exact runtime profile and its provider/model revision,
   preprocessing/configuration digest, source versions, and source derivation
   generations.
3. Confirm the processing principal is authorized for the manifest occurrence,
   document, version, and notebook. A shared content hash is not authority.
4. Keep optional Qdrant disabled unless the selected deployment profile already
   enables it; SQLite generation state remains authoritative.

## Build

1. Construct `ProjectionGenerationSpec`. Its UUIDv5 identity covers capability,
   profile, schema, input scope, provider/model/revision, dimensions,
   configuration fingerprint, source versions, and source generations.
2. Bind the spec to an authorized `ProcessingManifest` with
   `make_projection_processing_manifest` and submit it through
   `ProcessingJobStoreV1`. Duplicate manifests converge on the existing job.
3. Register `ProjectionBuildProcessingOperation` with the existing
   `ProcessingWorker`; do not create another queue.
4. The coordinator creates a `BUILDING` generation and immutable
   `index_generation_sources`, builds only the independent derived projection,
   and stores `index_generation_coverage`.
5. A complete count/checksum transitions to `READY` and atomically updates the
   active alias. Partial, failed, invalid, cancelled, or interrupted work is not
   served.

Supported internal builders are OCR text, Vision text, visual vectors, language
text, and multilingual vectors. The structured canonical-IR projector uses the
same generation/coverage/active-alias tables with a per-version profile.

## Resume and diagnosis

- `PENDING`: no generation record exists.
- `RUNNING`: a `BUILDING` record exists. A leased retry may resume it; duplicate
  direct builders do not race it. Cancellation or lease loss leaves it unserved
  in this recoverable state rather than poisoning the shared generation.
- `READY`: coverage is complete and count/checksum match. `active=false` means
  the alias has not selected it.
- `STALE`: the active generation does not match the exact requested contract,
  or the generation was superseded/retired.
- `FAILED`: execution failed; `failure_digest` identifies only the exception
  class and never contains private content.
- `INVALID`: partial coverage, missing coverage, or count/checksum mismatch.
- A complete zero-row generation is valid and distinct from a missing one:
  coverage records `expected_count=0` and a deterministic empty checksum.

Crash recovery reuses immutable source links and idempotent rows. A retry may
resume a retained `BUILDING` generation. Lease/cancellation checks occur before
execution and before promotion, so a stale worker cannot publish an alias.

## Rollback

Call `rollback_index_generation` only for a retained `SUPERSEDED` generation.
The store verifies complete coverage and matching count/checksum, demotes the
current READY generation, restores the target to READY, and switches the alias
in one transaction. Schema v14 remains installed and canonical data is not
rolled back.

## Invariants

- Never write OCR, Vision, or translated text to canonical chunks or canonical
  FTS.
- Never use provider/class/table presence as activation evidence.
- `ACTIVE` does not imply behavioral verification or certification.
- Never delete source documents, original assets, or retained audit/job records
  to repair a projection.
- Production/evaluation projection generation remains an explicit later
  operator/profile action; WP-02 did not mutate either corpus.
