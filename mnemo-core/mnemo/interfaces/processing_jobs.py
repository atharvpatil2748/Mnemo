"""Additive durable processing job and worker contracts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.models.processing import (
    ProcessingAttempt,
    ProcessingCheckpoint,
    ProcessingClaim,
    ProcessingFailureClass,
    ProcessingJob,
    ProcessingLedgerEntry,
    ProcessingManifest,
    ProcessingProgressEvent,
    ProcessingResult,
)


@runtime_checkable
class ProcessingJobStoreV1(Protocol):  # pragma: no cover
    async def submit_processing_job(
        self, manifest: ProcessingManifest, *, now: datetime
    ) -> tuple[ProcessingJob, bool]: ...

    async def get_processing_job(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID
    ) -> ProcessingJob | None: ...

    async def list_processing_jobs(
        self, *, actor_id: str, notebook_id: UUID, limit: int
    ) -> tuple[ProcessingJob, ...]: ...

    async def claim_processing_job(
        self,
        *,
        actor_id: str,
        notebook_id: UUID,
        worker_id: str,
        lease_duration: timedelta,
        now: datetime,
    ) -> ProcessingClaim | None: ...

    async def start_processing_attempt(
        self, *, job_id: UUID, lease_token: UUID, now: datetime
    ) -> ProcessingJob: ...

    async def renew_processing_lease(
        self,
        *,
        job_id: UUID,
        lease_token: UUID,
        lease_duration: timedelta,
        now: datetime,
    ) -> bool: ...

    async def put_processing_checkpoint(
        self, checkpoint: ProcessingCheckpoint, *, lease_token: UUID
    ) -> bool: ...

    async def get_latest_processing_checkpoint(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID
    ) -> ProcessingCheckpoint | None: ...

    async def request_processing_cancellation(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID, now: datetime
    ) -> ProcessingJob: ...

    async def acknowledge_processing_cancellation(
        self, *, job_id: UUID, lease_token: UUID, now: datetime
    ) -> ProcessingJob: ...

    async def fail_processing_job(
        self,
        *,
        job_id: UUID,
        lease_token: UUID,
        classification: ProcessingFailureClass,
        retryable: bool,
        now: datetime,
    ) -> ProcessingJob: ...

    async def resume_processing_job(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID, now: datetime
    ) -> ProcessingJob: ...

    async def recover_expired_processing_leases(self, *, now: datetime) -> tuple[UUID, ...]: ...

    async def complete_processing_job(
        self,
        *,
        result: ProcessingResult,
        lease_token: UUID,
        now: datetime,
    ) -> ProcessingJob: ...

    async def get_processing_result(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID
    ) -> ProcessingResult | None: ...

    async def list_processing_attempts(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID
    ) -> tuple[ProcessingAttempt, ...]: ...

    async def append_processing_ledger(
        self, entry: ProcessingLedgerEntry, *, lease_token: UUID
    ) -> bool: ...

    async def list_processing_ledger(
        self, *, actor_id: str, notebook_id: UUID, job_id: UUID
    ) -> tuple[ProcessingLedgerEntry, ...]: ...

    async def append_processing_progress(
        self, event: ProcessingProgressEvent, *, lease_token: UUID | None = None
    ) -> bool: ...

    async def list_processing_progress(
        self,
        *,
        actor_id: str,
        notebook_id: UUID,
        job_id: UUID,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> tuple[ProcessingProgressEvent, ...]: ...

    async def cleanup_processing_records(
        self, *, before: datetime, limit: int
    ) -> tuple[UUID, ...]: ...


type ProcessingOperation = Callable[
    [ProcessingJob, ProcessingCheckpoint | None, Callable[[], Awaitable[bool]]],
    Awaitable[ProcessingResult],
]


@runtime_checkable
class ProcessingWorkerV1(Protocol):  # pragma: no cover
    async def run_once(self, *, now: datetime | None = None) -> bool: ...

    async def run(self) -> None: ...

    async def stop(self) -> None: ...
