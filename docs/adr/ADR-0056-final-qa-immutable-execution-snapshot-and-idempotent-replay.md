# ADR-0056: Final-QA Immutable Execution Snapshot and Idempotent Replay

- **Status:** Accepted
- **Date:** 2026-08-20
- **Scope:** Persisted Final-QA execution and replay
- **Extends:** ADR-0044, ADR-0045, ADR-0046, ADR-0047, ADR-0049, ADR-0052, ADR-0054, ADR-0055

## Context

ADR-0046 gives the caller ownership of a stable `assistant_turn_id` and
requires compatible retries to converge. ADR-0054 correctly requires strict
citation compliance before a *new* assistant turn or citation is published.
Neither decision retained the immutable Phase-6 result chain needed to return
`FinalQAResult` when that assistant identity already exists. A `Turn` and its
`Citation` rows contain neither the request identity nor the exact
`ContextBuildResult`, `GroundedAnswerResult`, generation evidence, or retry
state. Reconstructing those objects from answer text, rendered context, chunks,
or citation rows would violate ADR-0044/0045 provenance rules.

## Options considered

### A. Versioned immutable execution snapshot and request fingerprint

Persist an execution header, immutable typed-provenance snapshots, and a
canonical logical-request fingerprint. A completed matching request replays the
stored final snapshot without a model call.

This preserves provenance, has deterministic conflict detection, supports
crash-safe publication recovery, and remains valid when provider/model behavior
changes. It adds an additive persistence model and migration, but does not
alter frozen Phase 0-6 models or storage interfaces.

### B. Transport-level turn/citation replay

Return a separate HTTP replay DTO from existing `Turn`/`Citation` rows. This
has low schema cost but cannot prove request compatibility or provide the
required `FinalQAResult` chain. It would create two incompatible Final-QA
semantics and loses provider/context provenance. Rejected.

### C. Deterministic regeneration for comparison

Regenerate and compare text or reconstructed evidence. Provider calls are not
deterministic across model/configuration changes, duplicate cost and side
effects, and violate ADR-0054's no-generation rule for an existing
publication. Rejected.

## Decision

Adopt option A. Persisted Final QA gains an additive, versioned immutable
execution-record facility. It is required only by the ADR-0055 persisted
endpoint. It is not a replacement provenance model: its payload serializes the
exact typed objects required to recreate the original immutable
`FinalQAResult`.

The future implementation introduces an additive `FinalQAExecutionStoreV1`
owned by the SQLite/Composite storage implementation. `StorageInterfaceV1`,
`FinalQARequest`, `FinalQAResult`, `CitationResolutionResult`, and all frozen
Phase 0-6 contracts remain unchanged. `KnowledgeEngine` supplies this facility
to the composed final-QA graph; the HTTP adapter remains a thin adapter.

### Request fingerprint

Before generation, construct a domain-separated SHA-256 digest of canonical
UTF-8 JSON with explicit serialization version. It includes the logical
execution inputs: notebook, session, and user-turn identifiers; the exact
persisted user-turn content and normalized query; hard and optional effective
filters; limits, context budget, table of contents, labels/source-title tuples;
the system-prompt identifier and bytes; tokenizer identity; planner/retrieval/
context policy versions; provider and model identity; relevant model
configuration; and ADR-0054 citation-contract and retry-policy versions.

`assistant_turn_id` is deliberately excluded: it is a single-use publication
slot, not a semantic request input. The row is instead uniquely keyed by that
slot. Secrets, API keys, bearer tokens, raw provider responses, and chain of
thought are never fingerprinted or persisted.

### Immutable snapshots and state

`final_qa_executions` is a small mutable state header. Immutable payloads are
stored in append-only `final_qa_execution_snapshots` rows. Payload schemas are
versioned and use canonical serialization/deserialization for the exact nested
typed results; they never derive provenance from rendered text or storage
lookups.

The header states are `RUNNING`, `VALIDATED`, `ASSISTANT_PUBLISHED`,
`PUBLISHED`, and terminal `REJECTED_CITATION_COMPLIANCE`. A `VALIDATED`
snapshot contains the exact strict `GroundedAnswerResult`, request fingerprint,
provider/prompt/contract descriptors, compliance result, and retry count. A
`PUBLISHED` snapshot contains the exact resulting `FinalQAResult`, including
the exact `CitationResolutionResult` and therefore the complete nested Phase-6
provenance. Each snapshot row is write-once; transitions are conditional and
record timestamps. Only compliant final-answer material is captured.

### Idempotency and publication order

For a new assistant slot, atomically claim `UNIQUE(assistant_turn_id)` under
the session-local single-writer policy, then generate, validate, and perform at
most ADR-0054's one corrective retry. On compliance, write the `VALIDATED`
snapshot before any assistant publication. Then append the assistant turn and
invoke ADR-0045 `CitationEngine`; write the `PUBLISHED` snapshot only after its
normal deterministic citation persistence succeeds.

For an existing assistant slot with the same fingerprint:

- `PUBLISHED` returns the exact persisted `FinalQAResult`; it performs zero
  generation, retry, assistant, or citation writes.
- `VALIDATED` resumes assistant/citation publication from the stored typed
  snapshot, without generation.
- `ASSISTANT_PUBLISHED` resumes ADR-0045 citation persistence from the stored
  typed snapshot. Its existing idempotent citation upserts make a durable
  citation prefix safe; no provenance is reconstructed from that prefix.
- `RUNNING` is reported as a typed retryable execution-in-progress outcome;
  no concurrent generation is started.
- `REJECTED_CITATION_COMPLIANCE` replays the classified integrity failure with
  zero model calls and no publication.

An existing slot with any different fingerprint raises `ConflictError` before
generation. Thus an existing assistant publication never causes citation
validation of a hypothetical new answer to outrank ADR-0046 idempotency.

### Crash recovery

Provider calls cannot be made exactly-once across a process crash. Therefore a
crash in `RUNNING` (before a validated snapshot) is fail-closed: it cannot be
reported successful or replayed. A liveness/lease recovery path may mark it
interrupted and permit a *new execution attempt* using the same logical
fingerprint; that is not an ADR-0054 corrective retry and is observable. It
must never publish an unvalidated answer. A concurrent caller receives the
typed retryable in-progress outcome rather than causing a duplicate call.

A crash after `VALIDATED` resumes from that snapshot with no model call. A
crash after assistant publication but before citations resumes `CitationEngine`
from that same snapshot; assistant and any deterministic citation prefix remain
durable. A crash after `PUBLISHED` is a pure persisted replay. No status may
claim `PUBLISHED` until citation compliance and ADR-0045 persistence completed.

### Legacy records

Assistant turns created before this contract have no execution row and are not
safe Final-QA replays. A request using such an assistant UUID fails closed with
a typed `final_qa.replay_unavailable` conflict; it is not regenerated,
backfilled from text, or silently treated as a compatible execution. Historical
turns and citations remain readable through their existing APIs.

## Schema and migration

The SQLite implementation follows the existing `schema_versions` migration
convention, in one transaction:

`final_qa_executions` contains `execution_id`, `assistant_turn_id`,
`request_fingerprint`, session/user-turn/notebook identifiers, contract and
payload-schema versions, provider/model descriptors, status, retry count,
failure classification, and created/updated/completed timestamps. It has
`UNIQUE(assistant_turn_id)`, an index on `(status, updated_at)`, and an index
on `(session_id, user_turn_id)`.

`final_qa_execution_snapshots` contains `execution_id`, snapshot phase,
payload schema version, canonical immutable payload, and timestamp, with
`UNIQUE(execution_id, phase)`. It references the execution header. The
assistant UUID is intentionally not a foreign key because `VALIDATED` must be
durable before the assistant turn exists. Migration failure rolls back both
schema/version changes; it is idempotent and requires no corpus re-ingestion.

## API and observability

ADR-0055's `POST /v1/notebooks/{notebook_id}/final-qa` remains the endpoint.
Its successful DTO adds only `execution: "new" | "replay"` metadata. A
fingerprint mismatch is ADR-0055's `409` conflict; `RUNNING` and legacy replay
unavailability use distinct typed, retryable/non-retryable ADR-0049 error
codes. `/v1/query` and `/v1/query/stream` remain transient preview APIs and
create no execution record, assistant turn, or citation.

Structured events record execution ID, status transition, attempt, and error
classification only. They never include answer text, context, credentials, or
raw provider output. Cancellation propagates unchanged; no timeout, fallback,
model switching, or unbounded retry is introduced.

## Compatibility and required tests

ADR-0044's first-pass prompt/output rules remain intact. ADR-0045 continues to
own resolution and citation persistence. ADR-0046 owns session sequencing and
conflicts, now backed by a durable identity/provenance record. ADR-0047 retains
engine lifecycle ownership. ADR-0049 maps the new typed errors. ADR-0052 and
ADR-0054 remain strict publication/compliance rules; ADR-0055 remains the
transport adapter. This ADR supersedes only the previously unspecified
idempotent replay detail of ADR-0046/0055.

Implementation tests must cover new first-pass success, corrective success and
exhaustion, matching replay and conflicting fingerprint with zero model calls,
legacy replay unavailability, all crash points, concurrent claims,
provider/prompt/model/citation-policy changes, no-context, snapshot integrity,
and proof that `/v1/query` is non-persistent.
