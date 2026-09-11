# Phase 8.5.3 Gate Evidence

**Workstream:** Durable processing and governance  
**Decision:** ADR-0060, with additive migration discipline from ADR-0071  
**Gate status:** PASS  
**Evidence date:** 2026-08-24

## Implementation summary

Phase 8.5.3 adds a provider-neutral durable processing subsystem without
widening `StorageInterfaceV1` or changing Phase 0–8 behavior. It comprises:

- immutable, versioned, secret-free processing manifests;
- canonical UTF-8 JSON/SHA-256 fingerprints and deterministic logical job IDs;
- `ProcessingJobStoreV1` and `ProcessingWorkerV1` additive protocols;
- actor/notebook/occurrence-scoped idempotent submission and lookup;
- atomic conditional SQLite claims, lease renewal, and stale-lease rejection;
- durable attempts, immutable checkpoints, immutable successful results,
  append-only cost/resource ledger entries, and ordered progress events;
- deterministic recovery of expired claims, bounded retry, cooperative
  cancellation, and prevention of stale-worker publication;
- explicit local/cloud trust, consent, budget, and deployment-profile resource
  admission checks;
- retention-aware, bounded, transactional cleanup of terminal jobs; and
- composition through `CompositeStorage` and the existing engine root.

No provider implementation, HTTP route, MCP tool, OCR, VLM, visual embedding,
multimodal retrieval, or Final-QA contract was introduced or changed.

## Interfaces and schema

- `ProcessingJobStoreV1`: submit/get/list, claim/renew, attempt start,
  checkpoint, cancellation, failure/resume/recovery, completion/result,
  attempt/ledger/progress inspection, and cleanup.
- `ProcessingWorkerV1`: bounded provider-neutral worker loop.
- SQLite schema version: **8**, upgraded transactionally from schema v7.
- New tables: `processing_jobs`, `processing_attempts`,
  `processing_checkpoints`, `processing_results`, `processing_cost_ledger`, and
  `processing_progress_events`, with scope/state/lease/provenance indexes and
  uniqueness constraints.

The durable job state machine is:

`QUEUED -> CLAIMED -> RUNNING`, with explicit terminal or recovery paths through
`CANCEL_REQUESTED`, `CANCELLED`, `FAILED_RETRYABLE`, `FAILED_FINAL`,
`BLOCKED_POLICY`, and `SUCCEEDED`. Illegal transitions raise typed contract or
conflict errors.

## Executed proof

### Idempotency and concurrency

- Semantically identical manifests produce one SHA-256 fingerprint and one
  deterministic logical job identity; volatile consent timestamps are excluded.
- Provider, model/profile, target, operation, and generation mutations change
  the fingerprint.
- Concurrent same-connection and independent-connection claims yield exactly
  one active lease.
- A 100-job concurrent queue saturation test loses no logical jobs and repeated
  submissions create no duplicates.
- Lease-bound writes reject stale tokens and mismatched attempt provenance.

### Crash recovery, checkpoint, cancellation, and retry

- Expired claimed/running attempts become interrupted and recoverable or final
  according to the bounded retry limit.
- Versioned checkpoints are immutable by `(job_id, sequence)` and are validated
  against fingerprint, provider profile, generation, and active attempt.
- A fault injected between result insertion and job completion rolls back the
  complete transaction; no result is published and the job remains running.
- Result publication is atomic, immutable, and requires the active running
  lease; completed jobs are replayed from the stored result and are not claimed
  again.
- Queued cancellation is terminal; running cancellation is cooperative and
  prevents later publication. Completed jobs reject retroactive cancellation.
- Transient failures retry only within the manifest limit; validation,
  authorization/policy, corrupted input, cancellation, and internal failures do
  not enter an unbounded retry loop.

### Consent, cost, resource, and security

- Non-allowed policy decisions fail closed.
- Cloud profiles require explicit egress consent or operator pre-authorization.
- Hard budget and deployment-profile admission ceilings are enforced before
  provider execution.
- Ledger records are append-only and contain typed usage metadata only.
- Manifest, checkpoint, result, and ledger metadata reject secret-bearing keys;
  worker logs contain identifiers/classifications rather than private payloads.
- Job access is actor/notebook scoped and submission verifies the authorized
  occurrence/document/version relationship.

### Observability and cleanup

- Ordered durable events cover queued, claimed, running, checkpoint, retry,
  cancellation, completion, and failure outcomes.
- The internal subscription helper replays ordered events and polls to a terminal
  state without changing existing HTTP/MCP contracts.
- Cleanup is bounded, transactional, idempotent, terminal-state-only, and
  preserves active/recoverable jobs and occurrence/asset records.

## Commands and results

```text
uv run pytest mnemo-core/tests/unit/test_processing_jobs.py -q --no-cov --durations=5
14 passed in 2.87s; 100-job queue saturation case completed in 0.26s

uv run pytest -q
1499 passed, 1 skipped, 8 warnings in 129.53s
Required test coverage of 90% reached. Total coverage: 90.11%

uv run ruff format --check .
276 files already formatted

uv run ruff check .
All checks passed

uv run mypy --strict mnemo-core/mnemo mnemo-server/mnemo_server plugins/email-ingestion/email_ingestion
Success: no issues found in 159 source files

uv build --package mnemo-core
uv build --package mnemo-server
uv build --package mnemo-email-ingestion
All three package builds succeeded

git diff --check
Passed
```

## Phase 0–8 and Golden Corpus regression

The complete repository regression suite passed. Existing HTTP V1 routes,
Final-QA V1, the six MCP tools, retrieval/reranking, canonical chunks, and
optional Qdrant behavior were not changed by this workstream.

The certified corpus was queried read-only after implementation:

```text
documents=15, versions=15, sources=15
chunks=1514, fts_rows=1514, title_rows=1514
orphan_chunks=0, duplicate_chunk_ids=0
sha256(concatenated ordered chunk id + text)=1997852deb381869d1ff72f511fa22b97bdea5287e5f6632ef1292405bbf4e66
database last-write UTC=2026-08-20T15:17:19.0379067Z
```

No purge, re-ingestion, corpus write, or Qdrant enablement was performed.

## Known limitations and rollback

Phase 8.5.3 intentionally provides the durable execution and governance
foundation only. Concrete OCR/VLM/visual-embedding/translation operations,
external transport adapters, UI controls, provider-specific monetary pricing,
and deployment-specific CPU/GPU discovery remain later workstreams. Resource
limits are explicit deployment-profile configuration rather than frozen global
constants.

Rollback is operational and non-destructive: stop workers and reject new
submissions while retaining schema-v8 records for inspection or later recovery.
Phase 0–8 and Phase 8.5.1/8.5.2 paths remain available.

## Verdict

**PHASE 8.5.3 GATE: PASS**
