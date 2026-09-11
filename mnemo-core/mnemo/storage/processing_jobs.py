"""SQLite implementation helpers for ADR-0060 durable processing jobs."""

# SQL statements intentionally remain visually atomic.
# ruff: noqa: E501

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4, uuid5

import aiosqlite

from mnemo.interfaces.errors import (
    ConflictError,
    ContractValidationError,
    IntegrityError,
    StorageError,
)
from mnemo.models import FrozenMetadata, thaw_json
from mnemo.models.processing import (
    ProcessingAttempt,
    ProcessingAttemptState,
    ProcessingBudget,
    ProcessingCheckpoint,
    ProcessingClaim,
    ProcessingConsent,
    ProcessingCostStatus,
    ProcessingEstimate,
    ProcessingFailureClass,
    ProcessingJob,
    ProcessingJobState,
    ProcessingLedgerEntry,
    ProcessingManifest,
    ProcessingPolicyDecision,
    ProcessingProgressEvent,
    ProcessingProgressKind,
    ProcessingResult,
    ProcessingTrustClass,
    is_legal_processing_transition,
    processing_job_fingerprint,
    processing_job_id,
)

PROCESSING_SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS processing_jobs (
        job_id TEXT PRIMARY KEY,
        fingerprint TEXT NOT NULL UNIQUE,
        actor_id TEXT NOT NULL,
        notebook_id TEXT NOT NULL REFERENCES notebooks(notebook_id) ON DELETE RESTRICT,
        occurrence_id TEXT NOT NULL REFERENCES asset_occurrences(occurrence_id) ON DELETE RESTRICT,
        document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE RESTRICT,
        version_id TEXT NOT NULL REFERENCES document_versions(version_id) ON DELETE RESTRICT,
        operation TEXT NOT NULL,
        manifest_schema_version INTEGER NOT NULL CHECK(manifest_schema_version > 0),
        manifest TEXT NOT NULL,
        state TEXT NOT NULL,
        attempt_count INTEGER NOT NULL CHECK(attempt_count >= 0),
        lease_owner TEXT,
        lease_token TEXT,
        lease_expires_at TEXT,
        failure_classification TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT,
        CHECK ((lease_owner IS NULL) = (lease_token IS NULL)),
        CHECK ((lease_token IS NULL) = (lease_expires_at IS NULL))
    )""",
    """CREATE TABLE IF NOT EXISTS processing_attempts (
        attempt_id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL REFERENCES processing_jobs(job_id) ON DELETE CASCADE,
        attempt_number INTEGER NOT NULL CHECK(attempt_number > 0),
        worker_id TEXT NOT NULL,
        lease_token TEXT NOT NULL,
        state TEXT NOT NULL,
        provider_profile TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        failure_classification TEXT,
        UNIQUE(job_id, attempt_number)
    )""",
    """CREATE TABLE IF NOT EXISTS processing_checkpoints (
        checkpoint_id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL REFERENCES processing_jobs(job_id) ON DELETE CASCADE,
        attempt_id TEXT NOT NULL REFERENCES processing_attempts(attempt_id) ON DELETE CASCADE,
        sequence INTEGER NOT NULL CHECK(sequence >= 0),
        fingerprint TEXT NOT NULL,
        provider_profile TEXT NOT NULL,
        generation_id TEXT,
        schema_version INTEGER NOT NULL CHECK(schema_version > 0),
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(job_id, sequence)
    )""",
    """CREATE TABLE IF NOT EXISTS processing_results (
        result_id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL UNIQUE REFERENCES processing_jobs(job_id) ON DELETE CASCADE,
        attempt_id TEXT NOT NULL REFERENCES processing_attempts(attempt_id) ON DELETE RESTRICT,
        fingerprint TEXT NOT NULL,
        output_reference TEXT,
        schema_version INTEGER NOT NULL CHECK(schema_version > 0),
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS processing_cost_ledger (
        entry_id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL REFERENCES processing_jobs(job_id) ON DELETE CASCADE,
        attempt_id TEXT NOT NULL REFERENCES processing_attempts(attempt_id) ON DELETE CASCADE,
        status TEXT NOT NULL,
        provider_identity TEXT NOT NULL,
        model_identity TEXT NOT NULL,
        usage TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS processing_progress_events (
        event_id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL REFERENCES processing_jobs(job_id) ON DELETE CASCADE,
        sequence INTEGER NOT NULL CHECK(sequence > 0),
        kind TEXT NOT NULL,
        detail_code TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(job_id, sequence)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_processing_jobs_scope_state ON processing_jobs(actor_id, notebook_id, state, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_processing_jobs_lease ON processing_jobs(state, lease_expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_processing_attempts_job ON processing_attempts(job_id, attempt_number)",
    "CREATE INDEX IF NOT EXISTS idx_processing_checkpoints_job ON processing_checkpoints(job_id, sequence)",
    "CREATE INDEX IF NOT EXISTS idx_processing_ledger_job ON processing_cost_ledger(job_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_processing_progress_job ON processing_progress_events(job_id, sequence)",
)

_ATTEMPT_NAMESPACE = UUID("8e725a40-3f0d-5c75-b948-c054bfd35d04")


@asynccontextmanager
async def _transaction(db: aiosqlite.Connection):  # type: ignore[no-untyped-def]
    try:
        await db.execute("BEGIN IMMEDIATE")
    except aiosqlite.Error as error:
        raise StorageError("could not begin processing-job transaction") from error
    try:
        yield
        await db.commit()
    except BaseException as error:
        await db.rollback()
        if isinstance(error, aiosqlite.Error):
            raise StorageError("processing-job transaction failed") from error
        raise


def _manifest_json(manifest: ProcessingManifest) -> str:
    return json.dumps(
        manifest.canonical_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _manifest_from_json(value: str) -> ProcessingManifest:
    raw = json.loads(value)
    consent = raw["consent"]
    estimate = raw["estimate"]
    return ProcessingManifest(
        actor_id=raw["actor_id"],
        notebook_id=UUID(raw["notebook_id"]),
        operation=raw["operation"],
        occurrence_id=UUID(raw["occurrence_id"]),
        document_id=UUID(raw["document_id"]),
        version_id=UUID(raw["version_id"]),
        provider_profile=raw["provider_profile"],
        provider_identity=raw["provider_identity"],
        provider_trust=ProcessingTrustClass(raw["provider_trust"]),
        model_identity=raw["model_identity"],
        configuration=FrozenMetadata(raw["configuration"]),
        generation_id=None if raw["generation_id"] is None else UUID(raw["generation_id"]),
        language=raw["language"],
        output_schema=raw["output_schema"],
        policy_version=raw["policy_version"],
        consent=ProcessingConsent(
            decision=ProcessingPolicyDecision(consent["decision"]),
            policy_version=consent["policy_version"],
            decided_at=datetime.fromisoformat(consent["decided_at"]),
            reason_code=consent["reason_code"],
        ),
        estimate=ProcessingEstimate(
            status=ProcessingCostStatus(estimate["status"]),
            units=FrozenMetadata(estimate["units"]),
            uncertainty=estimate["uncertainty"],
        ),
        budget=ProcessingBudget(**raw["budget"]),
        max_retries=int(raw["max_retries"]),
        schema_version=int(raw["schema_version"]),
    )


def _job(row: Any) -> ProcessingJob:
    return ProcessingJob(
        job_id=UUID(row[0]),
        fingerprint=row[1],
        manifest=_manifest_from_json(row[2]),
        state=ProcessingJobState(row[3]),
        attempt_count=int(row[4]),
        lease_owner=row[5],
        lease_token=None if row[6] is None else UUID(row[6]),
        lease_expires_at=None if row[7] is None else datetime.fromisoformat(row[7]),
        failure_classification=None if row[8] is None else ProcessingFailureClass(row[8]),
        created_at=datetime.fromisoformat(row[9]),
        updated_at=datetime.fromisoformat(row[10]),
        completed_at=None if row[11] is None else datetime.fromisoformat(row[11]),
    )


_JOB_COLUMNS = "job_id, fingerprint, manifest, state, attempt_count, lease_owner, lease_token, lease_expires_at, failure_classification, created_at, updated_at, completed_at"


def _attempt(row: Any) -> ProcessingAttempt:
    return ProcessingAttempt(
        attempt_id=UUID(row[0]),
        job_id=UUID(row[1]),
        attempt_number=int(row[2]),
        worker_id=row[3],
        lease_token=UUID(row[4]),
        state=ProcessingAttemptState(row[5]),
        provider_profile=row[6],
        started_at=datetime.fromisoformat(row[7]),
        ended_at=None if row[8] is None else datetime.fromisoformat(row[8]),
        failure_classification=None if row[9] is None else ProcessingFailureClass(row[9]),
    )


class SQLiteProcessingJobMixin:
    """Additive SQLite methods mixed into the canonical store."""

    _processing_job_lock: asyncio.Lock

    def _require_open(self) -> aiosqlite.Connection:
        """Provided by the concrete SQLite store."""
        raise NotImplementedError

    @asynccontextmanager
    async def _processing_transaction(self, db: aiosqlite.Connection) -> AsyncIterator[None]:
        async with self._processing_job_lock, _transaction(db):
            yield

    async def submit_processing_job(
        self, manifest: ProcessingManifest, *, now: datetime
    ) -> tuple[ProcessingJob, bool]:
        fingerprint = processing_job_fingerprint(manifest)
        job_id = processing_job_id(fingerprint)
        db = self._require_open()
        async with self._processing_transaction(db):
            row = await (
                await db.execute(
                    """SELECT 1 FROM asset_occurrences o JOIN sources s ON s.document_id=o.document_id
                   WHERE o.occurrence_id=? AND o.document_id=? AND o.version_id=? AND s.notebook_id=?""",
                    (
                        str(manifest.occurrence_id),
                        str(manifest.document_id),
                        str(manifest.version_id),
                        str(manifest.notebook_id),
                    ),
                )
            ).fetchone()
            if row is None:
                raise IntegrityError(
                    "processing target is unavailable in the authorized notebook scope"
                )
            cursor = await db.execute(
                """INSERT INTO processing_jobs(job_id,fingerprint,actor_id,notebook_id,occurrence_id,document_id,version_id,operation,manifest_schema_version,manifest,state,attempt_count,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(fingerprint) DO NOTHING""",
                (
                    str(job_id),
                    fingerprint,
                    manifest.actor_id,
                    str(manifest.notebook_id),
                    str(manifest.occurrence_id),
                    str(manifest.document_id),
                    str(manifest.version_id),
                    manifest.operation,
                    manifest.schema_version,
                    _manifest_json(manifest),
                    ProcessingJobState.QUEUED.value,
                    0,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            created = cursor.rowcount == 1
            if created:
                asset_row = await (
                    await db.execute(
                        "SELECT asset_id FROM asset_occurrences WHERE occurrence_id=?",
                        (str(manifest.occurrence_id),),
                    )
                ).fetchone()
                if asset_row is None:
                    raise IntegrityError("processing occurrence lost its asset reference")
                await db.execute(
                    "INSERT OR IGNORE INTO asset_gc_references(asset_id,reference_kind,reference_id,created_at) VALUES(?,?,?,?)",
                    (asset_row[0], "processing_job", str(job_id), now.isoformat()),
                )
                await self._append_event(
                    db, job_id, ProcessingProgressKind.QUEUED, "submitted", now
                )
            stored = await self._select_job(db, job_id)
            if stored is None:
                raise IntegrityError("submitted processing job could not be read")
            return stored, created

    async def get_processing_job(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID
    ) -> ProcessingJob | None:
        db = self._require_open()
        row = await (
            await db.execute(
                f"SELECT {_JOB_COLUMNS} FROM processing_jobs WHERE job_id=? AND actor_id=? AND notebook_id=?",
                (str(job_id), actor_id, str(notebook_id)),
            )
        ).fetchone()
        return None if row is None else _job(row)

    async def list_processing_jobs(
        self, *, actor_id: str, notebook_id: UUID, limit: int
    ) -> tuple[ProcessingJob, ...]:
        if isinstance(limit, bool) or not 1 <= limit <= 1000:
            raise ContractValidationError("limit must be between 1 and 1000")
        rows = await (
            await self._require_open().execute(
                f"SELECT {_JOB_COLUMNS} FROM processing_jobs WHERE actor_id=? AND notebook_id=? ORDER BY created_at,job_id LIMIT ?",
                (actor_id, str(notebook_id), limit),
            )
        ).fetchall()
        return tuple(_job(row) for row in rows)

    async def claim_processing_job(
        self,
        *,
        actor_id: str,
        notebook_id: UUID,
        worker_id: str,
        lease_duration: timedelta,
        now: datetime,
    ) -> ProcessingClaim | None:
        if lease_duration <= timedelta(0):
            raise ContractValidationError("lease duration must be positive")
        db = self._require_open()
        async with self._processing_transaction(db):
            row = await (
                await db.execute(
                    f"SELECT {_JOB_COLUMNS} FROM processing_jobs WHERE actor_id=? AND notebook_id=? AND state=? ORDER BY created_at,job_id LIMIT 1",
                    (actor_id, str(notebook_id), ProcessingJobState.QUEUED.value),
                )
            ).fetchone()
            if row is None:
                return None
            current = _job(row)
            token = uuid4()
            count = current.attempt_count + 1
            cursor = await db.execute(
                "UPDATE processing_jobs SET state=?,attempt_count=?,lease_owner=?,lease_token=?,lease_expires_at=?,updated_at=? WHERE job_id=? AND state=?",
                (
                    ProcessingJobState.CLAIMED.value,
                    count,
                    worker_id,
                    str(token),
                    (now + lease_duration).isoformat(),
                    now.isoformat(),
                    str(current.job_id),
                    ProcessingJobState.QUEUED.value,
                ),
            )
            if cursor.rowcount != 1:
                return None
            attempt_id = uuid5(_ATTEMPT_NAMESPACE, f"{current.job_id}:{count}")
            await db.execute(
                "INSERT INTO processing_attempts(attempt_id,job_id,attempt_number,worker_id,lease_token,state,provider_profile,started_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    str(attempt_id),
                    str(current.job_id),
                    count,
                    worker_id,
                    str(token),
                    ProcessingAttemptState.CLAIMED.value,
                    current.manifest.provider_profile,
                    now.isoformat(),
                ),
            )
            await self._append_event(
                db, current.job_id, ProcessingProgressKind.CLAIMED, "lease_claimed", now
            )
            claimed = await self._select_job(db, current.job_id)
            return ProcessingClaim(
                job=cast(ProcessingJob, claimed),
                attempt=ProcessingAttempt(
                    attempt_id=attempt_id,
                    job_id=current.job_id,
                    attempt_number=count,
                    worker_id=worker_id,
                    lease_token=token,
                    state=ProcessingAttemptState.CLAIMED,
                    provider_profile=current.manifest.provider_profile,
                    started_at=now,
                    ended_at=None,
                ),
            )

    async def start_processing_attempt(
        self, *, job_id: UUID, lease_token: UUID, now: datetime
    ) -> ProcessingJob:
        return await self._lease_transition(
            job_id,
            lease_token,
            ProcessingJobState.CLAIMED,
            ProcessingJobState.RUNNING,
            ProcessingAttemptState.RUNNING,
            now,
        )

    async def renew_processing_lease(
        self,
        *,
        job_id: UUID,
        lease_token: UUID,
        lease_duration: timedelta,
        now: datetime,
    ) -> bool:
        if lease_duration <= timedelta(0):
            raise ContractValidationError("lease duration must be positive")
        db = self._require_open()
        async with self._processing_transaction(db):
            cursor = await db.execute(
                "UPDATE processing_jobs SET lease_expires_at=?,updated_at=? WHERE job_id=? AND lease_token=? AND state IN (?,?,?) AND lease_expires_at>?",
                (
                    (now + lease_duration).isoformat(),
                    now.isoformat(),
                    str(job_id),
                    str(lease_token),
                    ProcessingJobState.CLAIMED.value,
                    ProcessingJobState.RUNNING.value,
                    ProcessingJobState.CANCEL_REQUESTED.value,
                    now.isoformat(),
                ),
            )
            return cursor.rowcount == 1

    async def put_processing_checkpoint(
        self, checkpoint: ProcessingCheckpoint, *, lease_token: UUID
    ) -> bool:
        db = self._require_open()
        async with self._processing_transaction(db):
            job = await self._select_job(db, checkpoint.job_id)
            if (
                job is None
                or job.lease_token != lease_token
                or job.state
                not in {ProcessingJobState.RUNNING, ProcessingJobState.CANCEL_REQUESTED}
            ):
                raise ConflictError("checkpoint requires the active processing lease")
            if (
                checkpoint.fingerprint != job.fingerprint
                or checkpoint.provider_profile != job.manifest.provider_profile
                or checkpoint.generation_id != job.manifest.generation_id
            ):
                raise IntegrityError("checkpoint is incompatible with the processing manifest")
            attempt_row = await (
                await db.execute(
                    "SELECT attempt_id FROM processing_attempts WHERE job_id=? AND lease_token=?",
                    (str(job.job_id), str(lease_token)),
                )
            ).fetchone()
            if attempt_row is None or checkpoint.attempt_id != UUID(attempt_row[0]):
                raise IntegrityError("checkpoint does not belong to the active attempt")
            try:
                cursor = await db.execute(
                    "INSERT INTO processing_checkpoints(checkpoint_id,job_id,attempt_id,sequence,fingerprint,provider_profile,generation_id,schema_version,payload,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        str(checkpoint.checkpoint_id),
                        str(checkpoint.job_id),
                        str(checkpoint.attempt_id),
                        checkpoint.sequence,
                        checkpoint.fingerprint,
                        checkpoint.provider_profile,
                        None if checkpoint.generation_id is None else str(checkpoint.generation_id),
                        checkpoint.schema_version,
                        json.dumps(
                            thaw_json(checkpoint.payload), sort_keys=True, separators=(",", ":")
                        ),
                        checkpoint.created_at.isoformat(),
                    ),
                )
            except aiosqlite.IntegrityError as error:
                raise ConflictError("processing checkpoint is immutable") from error
            await self._append_event(
                db,
                job.job_id,
                ProcessingProgressKind.CHECKPOINT,
                "checkpoint_committed",
                checkpoint.created_at,
            )
            return cursor.rowcount == 1

    async def get_latest_processing_checkpoint(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID
    ) -> ProcessingCheckpoint | None:
        db = self._require_open()
        scoped = await self.get_processing_job(
            actor_id=actor_id, notebook_id=notebook_id, job_id=job_id
        )
        if scoped is None:
            return None
        row = await (
            await db.execute(
                "SELECT checkpoint_id,job_id,attempt_id,sequence,fingerprint,provider_profile,generation_id,schema_version,payload,created_at FROM processing_checkpoints WHERE job_id=? ORDER BY sequence DESC LIMIT 1",
                (str(job_id),),
            )
        ).fetchone()
        if row is None:
            return None
        checkpoint = ProcessingCheckpoint(
            checkpoint_id=UUID(row[0]),
            job_id=UUID(row[1]),
            attempt_id=UUID(row[2]),
            sequence=int(row[3]),
            fingerprint=row[4],
            provider_profile=row[5],
            generation_id=None if row[6] is None else UUID(row[6]),
            schema_version=int(row[7]),
            payload=FrozenMetadata(json.loads(row[8])),
            created_at=datetime.fromisoformat(row[9]),
        )
        if (
            checkpoint.fingerprint != scoped.fingerprint
            or checkpoint.provider_profile != scoped.manifest.provider_profile
            or checkpoint.generation_id != scoped.manifest.generation_id
        ):
            raise IntegrityError("stored processing checkpoint is incompatible")
        return checkpoint

    async def request_processing_cancellation(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID, now: datetime
    ) -> ProcessingJob:
        db = self._require_open()
        async with self._processing_transaction(db):
            job = await self._select_scoped_job(db, actor_id, notebook_id, job_id)
            if job is None:
                raise IntegrityError("processing job is unavailable in scope")
            if job.state is ProcessingJobState.QUEUED:
                await db.execute(
                    "UPDATE processing_jobs SET state=?,updated_at=?,completed_at=? WHERE job_id=?",
                    (
                        ProcessingJobState.CANCELLED.value,
                        now.isoformat(),
                        now.isoformat(),
                        str(job_id),
                    ),
                )
            elif job.state in {ProcessingJobState.CLAIMED, ProcessingJobState.RUNNING}:
                await db.execute(
                    "UPDATE processing_jobs SET state=?,updated_at=? WHERE job_id=?",
                    (ProcessingJobState.CANCEL_REQUESTED.value, now.isoformat(), str(job_id)),
                )
            elif job.state is not ProcessingJobState.CANCEL_REQUESTED:
                raise ConflictError("terminal processing job cannot be cancelled")
            await self._append_event(
                db, job_id, ProcessingProgressKind.CANCELLATION, "cancel_requested", now
            )
            return cast(ProcessingJob, await self._select_job(db, job_id))

    async def acknowledge_processing_cancellation(
        self, *, job_id: UUID, lease_token: UUID, now: datetime
    ) -> ProcessingJob:
        return await self._lease_transition(
            job_id,
            lease_token,
            ProcessingJobState.CANCEL_REQUESTED,
            ProcessingJobState.CANCELLED,
            ProcessingAttemptState.CANCELLED,
            now,
            terminal=True,
        )

    async def fail_processing_job(
        self,
        *,
        job_id: UUID,
        lease_token: UUID,
        classification: ProcessingFailureClass,
        retryable: bool,
        now: datetime,
    ) -> ProcessingJob:
        db = self._require_open()
        async with self._processing_transaction(db):
            job = await self._select_job(db, job_id)
            if (
                job is None
                or job.lease_token != lease_token
                or job.state not in {ProcessingJobState.CLAIMED, ProcessingJobState.RUNNING}
            ):
                raise ConflictError("failure requires the active processing lease")
            policy_block = classification is ProcessingFailureClass.BUDGET_POLICY
            can_retry = retryable and job.attempt_count <= job.manifest.max_retries
            target = (
                ProcessingJobState.BLOCKED_POLICY
                if policy_block
                else ProcessingJobState.FAILED_RETRYABLE
                if can_retry
                else ProcessingJobState.FAILED_FINAL
            )
            attempt_state = (
                ProcessingAttemptState.FAILED_RETRYABLE
                if can_retry and not policy_block
                else ProcessingAttemptState.FAILED_FINAL
            )
            await db.execute(
                "UPDATE processing_jobs SET state=?,lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,failure_classification=?,updated_at=?,completed_at=? WHERE job_id=? AND lease_token=?",
                (
                    target.value,
                    classification.value,
                    now.isoformat(),
                    None if can_retry and not policy_block else now.isoformat(),
                    str(job_id),
                    str(lease_token),
                ),
            )
            await db.execute(
                "UPDATE processing_attempts SET state=?,failure_classification=?,ended_at=? WHERE job_id=? AND lease_token=?",
                (
                    attempt_state.value,
                    classification.value,
                    now.isoformat(),
                    str(job_id),
                    str(lease_token),
                ),
            )
            await self._append_event(
                db,
                job_id,
                ProcessingProgressKind.RETRY
                if can_retry and not policy_block
                else ProcessingProgressKind.FAILED,
                classification.value,
                now,
            )
            return cast(ProcessingJob, await self._select_job(db, job_id))

    async def resume_processing_job(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID, now: datetime
    ) -> ProcessingJob:
        db = self._require_open()
        async with self._processing_transaction(db):
            job = await self._select_scoped_job(db, actor_id, notebook_id, job_id)
            if job is None:
                raise IntegrityError("processing job is unavailable in scope")
            if job.state is not ProcessingJobState.FAILED_RETRYABLE:
                raise ConflictError("only retryable processing failures may resume")
            if job.attempt_count > job.manifest.max_retries:
                raise ConflictError("processing retry policy is exhausted")
            await db.execute(
                "UPDATE processing_jobs SET state=?,failure_classification=NULL,updated_at=? WHERE job_id=? AND state=?",
                (
                    ProcessingJobState.QUEUED.value,
                    now.isoformat(),
                    str(job_id),
                    ProcessingJobState.FAILED_RETRYABLE.value,
                ),
            )
            await self._append_event(db, job_id, ProcessingProgressKind.RETRY, "resumed", now)
            return cast(ProcessingJob, await self._select_job(db, job_id))

    async def recover_expired_processing_leases(self, *, now: datetime) -> tuple[UUID, ...]:
        db = self._require_open()
        recovered = []
        async with self._processing_transaction(db):
            rows = await (
                await db.execute(
                    f"SELECT {_JOB_COLUMNS} FROM processing_jobs WHERE state IN (?,?,?) AND lease_expires_at<=? ORDER BY job_id",
                    (
                        ProcessingJobState.CLAIMED.value,
                        ProcessingJobState.RUNNING.value,
                        ProcessingJobState.CANCEL_REQUESTED.value,
                        now.isoformat(),
                    ),
                )
            ).fetchall()
            for row in rows:
                job = _job(row)
                target = (
                    ProcessingJobState.CANCELLED
                    if job.state is ProcessingJobState.CANCEL_REQUESTED
                    else (
                        ProcessingJobState.FAILED_RETRYABLE
                        if job.attempt_count <= job.manifest.max_retries
                        else ProcessingJobState.FAILED_FINAL
                    )
                )
                failure = (
                    None
                    if target is ProcessingJobState.CANCELLED
                    else ProcessingFailureClass.TRANSIENT.value
                )
                await db.execute(
                    "UPDATE processing_jobs SET state=?,lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,failure_classification=?,updated_at=?,completed_at=? WHERE job_id=? AND lease_token=?",
                    (
                        target.value,
                        failure,
                        now.isoformat(),
                        None if target is ProcessingJobState.FAILED_RETRYABLE else now.isoformat(),
                        str(job.job_id),
                        str(job.lease_token),
                    ),
                )
                await db.execute(
                    "UPDATE processing_attempts SET state=?,failure_classification=?,ended_at=? WHERE job_id=? AND lease_token=?",
                    (
                        ProcessingAttemptState.INTERRUPTED.value,
                        failure,
                        now.isoformat(),
                        str(job.job_id),
                        str(job.lease_token),
                    ),
                )
                await self._append_event(
                    db, job.job_id, ProcessingProgressKind.FAILED, "lease_expired", now
                )
                recovered.append(job.job_id)
        return tuple(recovered)

    async def complete_processing_job(
        self, *, result: ProcessingResult, lease_token: UUID, now: datetime
    ) -> ProcessingJob:
        db = self._require_open()
        async with self._processing_transaction(db):
            job = await self._select_job(db, result.job_id)
            if (
                job is None
                or job.lease_token != lease_token
                or job.state is not ProcessingJobState.RUNNING
            ):
                raise ConflictError("result publication requires the active running lease")
            if result.fingerprint != job.fingerprint:
                raise IntegrityError("processing result fingerprint mismatch")
            attempt_row = await (
                await db.execute(
                    "SELECT attempt_id FROM processing_attempts WHERE job_id=? AND lease_token=?",
                    (str(job.job_id), str(lease_token)),
                )
            ).fetchone()
            if attempt_row is None or result.attempt_id != UUID(attempt_row[0]):
                raise IntegrityError("processing result does not belong to the active attempt")
            try:
                await db.execute(
                    "INSERT INTO processing_results(result_id,job_id,attempt_id,fingerprint,output_reference,schema_version,payload,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        str(result.result_id),
                        str(result.job_id),
                        str(result.attempt_id),
                        result.fingerprint,
                        result.output_reference,
                        result.schema_version,
                        json.dumps(
                            thaw_json(result.payload), sort_keys=True, separators=(",", ":")
                        ),
                        result.created_at.isoformat(),
                    ),
                )
            except aiosqlite.IntegrityError as error:
                raise ConflictError("processing result publication is immutable") from error
            await db.execute(
                "UPDATE processing_jobs SET state=?,lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,updated_at=?,completed_at=? WHERE job_id=? AND lease_token=?",
                (
                    ProcessingJobState.SUCCEEDED.value,
                    now.isoformat(),
                    now.isoformat(),
                    str(result.job_id),
                    str(lease_token),
                ),
            )
            await db.execute(
                "UPDATE processing_attempts SET state=?,ended_at=? WHERE job_id=? AND lease_token=?",
                (
                    ProcessingAttemptState.SUCCEEDED.value,
                    now.isoformat(),
                    str(result.job_id),
                    str(lease_token),
                ),
            )
            await self._append_event(
                db, result.job_id, ProcessingProgressKind.COMPLETED, "result_published", now
            )
            return cast(ProcessingJob, await self._select_job(db, result.job_id))

    async def get_processing_result(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID
    ) -> ProcessingResult | None:
        if (
            await self.get_processing_job(actor_id=actor_id, notebook_id=notebook_id, job_id=job_id)
            is None
        ):
            return None
        row = await (
            await self._require_open().execute(
                "SELECT result_id,job_id,attempt_id,fingerprint,output_reference,schema_version,payload,created_at FROM processing_results WHERE job_id=?",
                (str(job_id),),
            )
        ).fetchone()
        return (
            None
            if row is None
            else ProcessingResult(
                result_id=UUID(row[0]),
                job_id=UUID(row[1]),
                attempt_id=UUID(row[2]),
                fingerprint=row[3],
                output_reference=row[4],
                schema_version=int(row[5]),
                payload=FrozenMetadata(json.loads(row[6])),
                created_at=datetime.fromisoformat(row[7]),
            )
        )

    async def list_processing_attempts(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID
    ) -> tuple[ProcessingAttempt, ...]:
        if (
            await self.get_processing_job(actor_id=actor_id, notebook_id=notebook_id, job_id=job_id)
            is None
        ):
            return ()
        rows = await (
            await self._require_open().execute(
                "SELECT attempt_id,job_id,attempt_number,worker_id,lease_token,state,provider_profile,started_at,ended_at,failure_classification FROM processing_attempts WHERE job_id=? ORDER BY attempt_number",
                (str(job_id),),
            )
        ).fetchall()
        return tuple(_attempt(row) for row in rows)

    async def append_processing_ledger(
        self, entry: ProcessingLedgerEntry, *, lease_token: UUID
    ) -> bool:
        db = self._require_open()
        async with self._processing_transaction(db):
            job = await self._select_job(db, entry.job_id)
            if job is None or job.lease_token != lease_token:
                raise ConflictError("ledger append requires the active processing lease")
            attempt_row = await (
                await db.execute(
                    "SELECT attempt_id FROM processing_attempts WHERE job_id=? AND lease_token=?",
                    (str(job.job_id), str(lease_token)),
                )
            ).fetchone()
            if attempt_row is None or entry.attempt_id != UUID(attempt_row[0]):
                raise IntegrityError("ledger entry does not belong to the active attempt")
            cursor = await db.execute(
                "INSERT OR IGNORE INTO processing_cost_ledger(entry_id,job_id,attempt_id,status,provider_identity,model_identity,usage,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    str(entry.entry_id),
                    str(entry.job_id),
                    str(entry.attempt_id),
                    entry.status.value,
                    entry.provider_identity,
                    entry.model_identity,
                    json.dumps(thaw_json(entry.usage), sort_keys=True, separators=(",", ":")),
                    entry.created_at.isoformat(),
                ),
            )
            return cursor.rowcount == 1

    async def list_processing_ledger(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID
    ) -> tuple[ProcessingLedgerEntry, ...]:
        if (
            await self.get_processing_job(actor_id=actor_id, notebook_id=notebook_id, job_id=job_id)
            is None
        ):
            return ()
        rows = await (
            await self._require_open().execute(
                "SELECT entry_id,job_id,attempt_id,status,provider_identity,model_identity,usage,created_at FROM processing_cost_ledger WHERE job_id=? ORDER BY created_at,entry_id",
                (str(job_id),),
            )
        ).fetchall()
        return tuple(
            ProcessingLedgerEntry(
                entry_id=UUID(r[0]),
                job_id=UUID(r[1]),
                attempt_id=UUID(r[2]),
                status=ProcessingCostStatus(r[3]),
                provider_identity=r[4],
                model_identity=r[5],
                usage=FrozenMetadata(json.loads(r[6])),
                created_at=datetime.fromisoformat(r[7]),
            )
            for r in rows
        )

    async def append_processing_progress(
        self, event: ProcessingProgressEvent, *, lease_token: UUID | None = None
    ) -> bool:
        db = self._require_open()
        async with self._processing_transaction(db):
            job = await self._select_job(db, event.job_id)
            if job is None:
                raise IntegrityError("processing job does not exist")
            if lease_token is not None and job.lease_token != lease_token:
                raise ConflictError("progress append requires the active lease")
            try:
                cursor = await db.execute(
                    "INSERT INTO processing_progress_events(event_id,job_id,sequence,kind,detail_code,created_at) VALUES(?,?,?,?,?,?)",
                    (
                        str(event.event_id),
                        str(event.job_id),
                        event.sequence,
                        event.kind.value,
                        event.detail_code,
                        event.created_at.isoformat(),
                    ),
                )
                return cursor.rowcount == 1
            except aiosqlite.IntegrityError as error:
                raise ConflictError("processing progress sequence is immutable") from error

    async def list_processing_progress(
        self,
        *,
        actor_id: str,
        notebook_id: UUID,
        job_id: UUID,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> tuple[ProcessingProgressEvent, ...]:
        if not 1 <= limit <= 1000 or after_sequence < 0:
            raise ContractValidationError("invalid progress bounds")
        if (
            await self.get_processing_job(actor_id=actor_id, notebook_id=notebook_id, job_id=job_id)
            is None
        ):
            return ()
        rows = await (
            await self._require_open().execute(
                "SELECT event_id,job_id,sequence,kind,detail_code,created_at FROM processing_progress_events WHERE job_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                (str(job_id), after_sequence, limit),
            )
        ).fetchall()
        return tuple(
            ProcessingProgressEvent(
                event_id=UUID(r[0]),
                job_id=UUID(r[1]),
                sequence=int(r[2]),
                kind=ProcessingProgressKind(r[3]),
                detail_code=r[4],
                created_at=datetime.fromisoformat(r[5]),
            )
            for r in rows
        )

    async def cleanup_processing_records(self, *, before: datetime, limit: int) -> tuple[UUID, ...]:
        if not 1 <= limit <= 1000:
            raise ContractValidationError("cleanup limit must be between 1 and 1000")
        db = self._require_open()
        deleted = []
        async with self._processing_transaction(db):
            rows = await (
                await db.execute(
                    "SELECT job_id FROM processing_jobs WHERE state IN (?,?,?,?) AND completed_at<? ORDER BY completed_at LIMIT ?",
                    (
                        ProcessingJobState.CANCELLED.value,
                        ProcessingJobState.SUCCEEDED.value,
                        ProcessingJobState.FAILED_FINAL.value,
                        ProcessingJobState.BLOCKED_POLICY.value,
                        before.isoformat(),
                        limit,
                    ),
                )
            ).fetchall()
            for (job_id,) in rows:
                await db.execute(
                    "DELETE FROM asset_gc_references WHERE reference_kind='processing_job' AND reference_id=?",
                    (job_id,),
                )
                await db.execute("DELETE FROM processing_jobs WHERE job_id=?", (job_id,))
                deleted.append(UUID(job_id))
        return tuple(deleted)

    async def _lease_transition(
        self,
        job_id: UUID,
        lease_token: UUID,
        source: ProcessingJobState,
        target: ProcessingJobState,
        attempt_state: ProcessingAttemptState,
        now: datetime,
        terminal: bool = False,
    ) -> ProcessingJob:
        if not is_legal_processing_transition(source, target):
            raise ContractValidationError("illegal processing state transition")
        db = self._require_open()
        async with self._processing_transaction(db):
            cursor = await db.execute(
                "UPDATE processing_jobs SET state=?,updated_at=?,completed_at=?,lease_owner=CASE WHEN ? THEN NULL ELSE lease_owner END,lease_token=CASE WHEN ? THEN NULL ELSE lease_token END,lease_expires_at=CASE WHEN ? THEN NULL ELSE lease_expires_at END WHERE job_id=? AND state=? AND lease_token=?",
                (
                    target.value,
                    now.isoformat(),
                    now.isoformat() if terminal else None,
                    terminal,
                    terminal,
                    terminal,
                    str(job_id),
                    source.value,
                    str(lease_token),
                ),
            )
            if cursor.rowcount != 1:
                raise ConflictError("processing lease or state changed")
            await db.execute(
                "UPDATE processing_attempts SET state=?,ended_at=? WHERE job_id=? AND lease_token=?",
                (
                    attempt_state.value,
                    now.isoformat() if terminal else None,
                    str(job_id),
                    str(lease_token),
                ),
            )
            if target is ProcessingJobState.RUNNING:
                await self._append_event(
                    db, job_id, ProcessingProgressKind.RUNNING, "provider_execution_started", now
                )
            elif target is ProcessingJobState.CANCELLED:
                await self._append_event(
                    db, job_id, ProcessingProgressKind.CANCELLATION, "cancelled", now
                )
            return cast(ProcessingJob, await self._select_job(db, job_id))

    async def _select_job(self, db: aiosqlite.Connection, job_id: UUID) -> ProcessingJob | None:
        row = await (
            await db.execute(
                f"SELECT {_JOB_COLUMNS} FROM processing_jobs WHERE job_id=?", (str(job_id),)
            )
        ).fetchone()
        return None if row is None else _job(row)

    async def _select_scoped_job(
        self, db: aiosqlite.Connection, actor_id: str, notebook_id: UUID, job_id: UUID
    ) -> ProcessingJob | None:
        row = await (
            await db.execute(
                f"SELECT {_JOB_COLUMNS} FROM processing_jobs WHERE job_id=? AND actor_id=? AND notebook_id=?",
                (str(job_id), actor_id, str(notebook_id)),
            )
        ).fetchone()
        return None if row is None else _job(row)

    async def _append_event(
        self,
        db: aiosqlite.Connection,
        job_id: UUID,
        kind: ProcessingProgressKind,
        detail: str,
        now: datetime,
    ) -> None:
        row = await (
            await db.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 FROM processing_progress_events WHERE job_id=?",
                (str(job_id),),
            )
        ).fetchone()
        if row is None:
            raise IntegrityError("processing progress sequence could not be allocated")
        await db.execute(
            "INSERT INTO processing_progress_events(event_id,job_id,sequence,kind,detail_code,created_at) VALUES(?,?,?,?,?,?)",
            (str(uuid4()), str(job_id), int(row[0]), kind.value, detail, now.isoformat()),
        )
