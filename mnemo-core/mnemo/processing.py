"""Durable processing policy, admission, and worker orchestration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from mnemo.interfaces.errors import (
    ContractValidationError,
    IntegrityError,
    OperationCancelledError,
)
from mnemo.interfaces.processing_jobs import ProcessingJobStoreV1, ProcessingOperation
from mnemo.models import FrozenMetadata
from mnemo.models.processing import (
    ProcessingCostStatus,
    ProcessingFailureClass,
    ProcessingJob,
    ProcessingJobState,
    ProcessingLedgerEntry,
    ProcessingManifest,
    ProcessingPolicyDecision,
    ProcessingProgressEvent,
    ProcessingProgressKind,
    ProcessingTrustClass,
)

_LOGGER = logging.getLogger(__name__)


class ProcessingPolicyError(ContractValidationError):
    code = "processing.policy"


class ProcessingAdmissionError(ContractValidationError):
    code = "processing.admission"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessingAdmissionProfile:
    max_active_workers: int
    max_cpu_seconds: int | None = None
    max_gpu_seconds: int | None = None
    max_input_units: int | None = None
    max_output_units: int | None = None
    max_tokens: int | None = None
    max_bytes: int | None = None
    max_memory_bytes: int | None = None
    max_vram_bytes: int | None = None
    max_operations: int | None = None
    max_pages: int | None = None
    max_pixels: int | None = None
    max_images: int | None = None
    max_cloud_requests: int | None = None

    def __post_init__(self) -> None:
        if isinstance(self.max_active_workers, bool) or self.max_active_workers < 1:
            raise ValueError("max_active_workers must be positive")
        for name in (
            "max_cpu_seconds",
            "max_gpu_seconds",
            "max_input_units",
            "max_output_units",
            "max_tokens",
            "max_bytes",
            "max_memory_bytes",
            "max_vram_bytes",
            "max_operations",
            "max_pages",
            "max_pixels",
            "max_images",
            "max_cloud_requests",
        ):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or value < 0):
                raise ValueError(f"{name} must be non-negative")


def enforce_processing_policy(manifest: ProcessingManifest) -> None:
    """Fail closed for consent, cloud egress, and hard-estimate budget violations."""
    decision = manifest.consent.decision
    if decision is not ProcessingPolicyDecision.ALLOWED:
        raise ProcessingPolicyError(f"processing policy decision is {decision.value}")
    if (
        manifest.provider_trust is ProcessingTrustClass.CLOUD
        and manifest.consent.reason_code not in {"explicit_user_consent", "operator_pre_authorized"}
    ):
        raise ProcessingPolicyError("cloud processing requires explicit egress consent")
    units = manifest.estimate.units
    checks = (
        ("wall_seconds", manifest.budget.max_wall_seconds),
        ("cpu_seconds", manifest.budget.max_cpu_seconds),
        ("gpu_seconds", manifest.budget.max_gpu_seconds),
        ("input_units", manifest.budget.max_input_units),
        ("output_units", manifest.budget.max_output_units),
        ("tokens", manifest.budget.max_tokens),
        ("bytes", manifest.budget.max_bytes),
        ("memory_bytes", manifest.budget.max_memory_bytes),
        ("vram_bytes", manifest.budget.max_vram_bytes),
        ("operations", manifest.budget.max_operations),
        ("pages", manifest.budget.max_pages),
        ("pixels", manifest.budget.max_pixels),
        ("images", manifest.budget.max_images),
        ("cloud_requests", manifest.budget.max_cloud_requests),
        ("currency_micros", manifest.budget.max_currency_micros),
    )
    for key, ceiling in checks:
        estimated = units.get(key)
        if ceiling is not None and isinstance(estimated, (int, float)) and estimated > ceiling:
            raise ProcessingPolicyError(f"processing estimate exceeds {key} budget")


def enforce_resource_admission(
    manifest: ProcessingManifest,
    profile: ProcessingAdmissionProfile,
    *,
    active_workers: int,
) -> None:
    if active_workers >= profile.max_active_workers:
        raise ProcessingAdmissionError("processing worker capacity is saturated", retryable=True)
    units = manifest.estimate.units
    checks = (
        ("cpu_seconds", profile.max_cpu_seconds),
        ("gpu_seconds", profile.max_gpu_seconds),
        ("input_units", profile.max_input_units),
        ("output_units", profile.max_output_units),
        ("tokens", profile.max_tokens),
        ("bytes", profile.max_bytes),
        ("memory_bytes", profile.max_memory_bytes),
        ("vram_bytes", profile.max_vram_bytes),
        ("operations", profile.max_operations),
        ("pages", profile.max_pages),
        ("pixels", profile.max_pixels),
        ("images", profile.max_images),
        ("cloud_requests", profile.max_cloud_requests),
    )
    for key, ceiling in checks:
        value = units.get(key)
        if ceiling is not None and isinstance(value, (int, float)) and value > ceiling:
            raise ProcessingAdmissionError(f"processing request exceeds deployment {key} ceiling")


def classify_processing_failure(error: BaseException) -> tuple[ProcessingFailureClass, bool]:
    if isinstance(error, (OperationCancelledError, asyncio.CancelledError)):
        return ProcessingFailureClass.CANCELLATION, False
    if isinstance(error, ProcessingPolicyError):
        return ProcessingFailureClass.BUDGET_POLICY, False
    if isinstance(error, ProcessingAdmissionError):
        return ProcessingFailureClass.TRANSIENT, True
    if isinstance(error, ContractValidationError):
        return ProcessingFailureClass.VALIDATION, False
    if isinstance(error, IntegrityError):
        return ProcessingFailureClass.CORRUPTED_INPUT, False
    if isinstance(error, (TimeoutError, ConnectionError)):
        return ProcessingFailureClass.TRANSIENT, True
    return ProcessingFailureClass.INTERNAL, False


class ProcessingWorker:
    """One provider-neutral cooperative worker over a durable lease store."""

    def __init__(
        self,
        *,
        store: ProcessingJobStoreV1,
        actor_id: str,
        notebook_id: UUID,
        worker_id: str,
        operations: dict[str, ProcessingOperation],
        admission_profile: ProcessingAdmissionProfile,
        lease_duration: timedelta = timedelta(minutes=5),
        poll_interval: float = 0.25,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not isinstance(store, ProcessingJobStoreV1):
            raise TypeError("store must implement ProcessingJobStoreV1")
        if not actor_id.strip() or not worker_id.strip():
            raise ValueError("actor_id and worker_id must not be empty")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        self._store = store
        self._actor_id = actor_id
        self._notebook_id = notebook_id
        self._worker_id = worker_id
        self._operations = dict(operations)
        self._admission_profile = admission_profile
        self._lease_duration = lease_duration
        self._poll_interval = poll_interval
        self._clock = clock
        self._stopping = asyncio.Event()

    async def run_once(self, *, now: datetime | None = None) -> bool:
        current = self._clock() if now is None else now
        await self._store.recover_expired_processing_leases(now=current)
        claim = await self._store.claim_processing_job(
            actor_id=self._actor_id,
            notebook_id=self._notebook_id,
            worker_id=self._worker_id,
            lease_duration=self._lease_duration,
            now=current,
        )
        if claim is None:
            return False
        job, attempt = claim.job, claim.attempt
        token = attempt.lease_token
        try:
            enforce_processing_policy(job.manifest)
            enforce_resource_admission(job.manifest, self._admission_profile, active_workers=0)
            job = await self._store.start_processing_attempt(
                job_id=job.job_id, lease_token=token, now=current
            )
            operation = self._operations.get(job.manifest.operation)
            if operation is None:
                raise ContractValidationError("processing operation is not registered")
            checkpoint = await self._store.get_latest_processing_checkpoint(
                actor_id=self._actor_id,
                notebook_id=self._notebook_id,
                job_id=job.job_id,
            )
            lease_lost = asyncio.Event()
            heartbeat_stop = asyncio.Event()

            async def cancelled() -> bool:
                latest = await self._store.get_processing_job(
                    actor_id=self._actor_id,
                    notebook_id=self._notebook_id,
                    job_id=job.job_id,
                )
                return (
                    latest is None
                    or latest.lease_token != token
                    or latest.state is ProcessingJobState.CANCEL_REQUESTED
                )

            async def heartbeat() -> None:
                interval = max(self._lease_duration.total_seconds() / 3, 0.01)
                while not heartbeat_stop.is_set():
                    try:
                        await asyncio.wait_for(heartbeat_stop.wait(), timeout=interval)
                        return
                    except TimeoutError:
                        renewed = await self._store.renew_processing_lease(
                            job_id=job.job_id,
                            lease_token=token,
                            lease_duration=self._lease_duration,
                            now=self._clock(),
                        )
                        if not renewed:
                            lease_lost.set()
                            return

            if await cancelled():
                await self._store.acknowledge_processing_cancellation(
                    job_id=job.job_id, lease_token=token, now=self._clock()
                )
                return True
            heartbeat_task = asyncio.create_task(heartbeat())
            try:
                result = await operation(job, checkpoint, cancelled)
            finally:
                heartbeat_stop.set()
                await heartbeat_task
            if lease_lost.is_set():
                return True
            if result.job_id != job.job_id or result.fingerprint != job.fingerprint:
                raise IntegrityError("processing result provenance does not match the claimed job")
            if await cancelled():
                await self._store.acknowledge_processing_cancellation(
                    job_id=job.job_id, lease_token=token, now=self._clock()
                )
                return True
            await self._store.complete_processing_job(
                result=result, lease_token=token, now=self._clock()
            )
            return True
        except asyncio.CancelledError:
            try:
                await self._store.acknowledge_processing_cancellation(
                    job_id=job.job_id, lease_token=token, now=self._clock()
                )
            except Exception:
                _LOGGER.warning("processing cancellation acknowledgement failed", exc_info=True)
            raise
        except BaseException as error:
            latest = await self._store.get_processing_job(
                actor_id=self._actor_id,
                notebook_id=self._notebook_id,
                job_id=job.job_id,
            )
            if latest is None or latest.lease_token != token:
                _LOGGER.warning(
                    "processing worker lost lease before terminal transition",
                    extra={"job_id": str(job.job_id), "worker_id": self._worker_id},
                )
                return True
            classification, retryable = classify_processing_failure(error)
            if classification is ProcessingFailureClass.CANCELLATION:
                await self._store.acknowledge_processing_cancellation(
                    job_id=job.job_id, lease_token=token, now=self._clock()
                )
            else:
                failed = await self._store.fail_processing_job(
                    job_id=job.job_id,
                    lease_token=token,
                    classification=classification,
                    retryable=retryable,
                    now=self._clock(),
                )
                if failed.state is ProcessingJobState.FAILED_RETRYABLE:
                    await self._store.resume_processing_job(
                        actor_id=self._actor_id,
                        notebook_id=self._notebook_id,
                        job_id=job.job_id,
                        now=self._clock(),
                    )
            return True

    async def run(self) -> None:
        while not self._stopping.is_set():
            processed = await self.run_once()
            if not processed:
                with suppress(TimeoutError):
                    await asyncio.wait_for(self._stopping.wait(), timeout=self._poll_interval)

    async def stop(self) -> None:
        self._stopping.set()


def make_actual_ledger_entry(
    *, job: ProcessingJob, attempt_id: UUID, usage: FrozenMetadata, now: datetime
) -> ProcessingLedgerEntry:
    return ProcessingLedgerEntry(
        entry_id=uuid4(),
        job_id=job.job_id,
        attempt_id=attempt_id,
        status=ProcessingCostStatus.ACTUAL,
        provider_identity=job.manifest.provider_identity,
        model_identity=job.manifest.model_identity,
        usage=usage,
        created_at=now,
    )


def make_progress_event(
    *, job_id: UUID, sequence: int, kind: ProcessingProgressKind, detail_code: str, now: datetime
) -> ProcessingProgressEvent:
    return ProcessingProgressEvent(
        event_id=uuid4(),
        job_id=job_id,
        sequence=sequence,
        kind=kind,
        detail_code=detail_code,
        created_at=now,
    )


async def stream_processing_progress(
    *,
    store: ProcessingJobStoreV1,
    actor_id: str,
    notebook_id: UUID,
    job_id: UUID,
    after_sequence: int = 0,
    batch_limit: int = 100,
    poll_interval: float = 0.25,
) -> AsyncIterator[ProcessingProgressEvent]:
    """Replay ordered durable events, then poll until the scoped job is terminal."""
    if after_sequence < 0 or not 1 <= batch_limit <= 1000 or poll_interval <= 0:
        raise ContractValidationError("invalid processing progress subscription bounds")
    cursor = after_sequence
    terminal = {
        ProcessingJobState.CANCELLED,
        ProcessingJobState.SUCCEEDED,
        ProcessingJobState.FAILED_FINAL,
        ProcessingJobState.BLOCKED_POLICY,
    }
    while True:
        events = await store.list_processing_progress(
            actor_id=actor_id,
            notebook_id=notebook_id,
            job_id=job_id,
            after_sequence=cursor,
            limit=batch_limit,
        )
        for event in events:
            cursor = event.sequence
            yield event
        job = await store.get_processing_job(
            actor_id=actor_id, notebook_id=notebook_id, job_id=job_id
        )
        if job is None or (job.state in terminal and not events):
            return
        if not events:
            await asyncio.sleep(poll_interval)
