"""Phase 8.5.3 durable processing domain and SQLite lifecycle tests."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import aiosqlite
import pytest
from mnemo.interfaces import (
    ConflictError,
    ContractValidationError,
    IntegrityError,
    OperationCancelledError,
    ProcessingJobStoreV1,
    StorageError,
)
from mnemo.models import (
    Asset,
    AssetContainerKind,
    AssetExtractionProvenance,
    AssetLocator,
    AssetLocatorKind,
    AssetOccurrence,
    Document,
    DocumentBinaryReference,
    DocumentBinaryRole,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    FrozenMetadata,
    Notebook,
    ProcessingAttemptState,
    ProcessingBudget,
    ProcessingCheckpoint,
    ProcessingConsent,
    ProcessingCostStatus,
    ProcessingEstimate,
    ProcessingFailureClass,
    ProcessingJobState,
    ProcessingLedgerEntry,
    ProcessingManifest,
    ProcessingPolicyDecision,
    ProcessingProgressEvent,
    ProcessingProgressKind,
    ProcessingResult,
    ProcessingTrustClass,
    Source,
    asset_occurrence_id,
    is_legal_processing_transition,
    processing_job_fingerprint,
    processing_job_id,
)
from mnemo.processing import (
    ProcessingAdmissionError,
    ProcessingAdmissionProfile,
    ProcessingPolicyError,
    ProcessingWorker,
    classify_processing_failure,
    enforce_processing_policy,
    enforce_resource_admission,
    make_actual_ledger_entry,
    make_progress_event,
    stream_processing_progress,
)
from mnemo.storage.composite import CompositeStorage
from mnemo.storage.sqlite import SQLiteStore

NOW = datetime(2026, 8, 24, 12, tzinfo=UTC)


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _manifest(
    *,
    actor_id: str,
    notebook_id: UUID,
    occurrence: AssetOccurrence,
    operation: str = "ocr",
    provider: str = "local-ocr",
    trust: ProcessingTrustClass = ProcessingTrustClass.LOCAL,
    consent_reason: str = "local_processing",
    max_retries: int = 1,
) -> ProcessingManifest:
    return ProcessingManifest(
        actor_id=actor_id,
        notebook_id=notebook_id,
        operation=operation,
        occurrence_id=occurrence.occurrence_id,
        document_id=occurrence.document_id,
        version_id=occurrence.version_id,
        provider_profile="baseline",
        provider_identity=provider,
        provider_trust=trust,
        model_identity="model-v1",
        configuration=FrozenMetadata({"language": "en", "quality": "balanced"}),
        generation_id=None,
        language="en",
        output_schema="ocr-regions/v1",
        policy_version="policy/v1",
        consent=ProcessingConsent(
            decision=ProcessingPolicyDecision.ALLOWED,
            policy_version="policy/v1",
            decided_at=NOW,
            reason_code=consent_reason,
        ),
        estimate=ProcessingEstimate(
            status=ProcessingCostStatus.ESTIMATED,
            units=FrozenMetadata({"input_units": 1, "bytes": 128, "cloud_requests": 0}),
            uncertainty="bounded",
        ),
        budget=ProcessingBudget(
            max_wall_seconds=60,
            max_input_units=4,
            max_output_units=1000,
            max_bytes=1024,
            max_cloud_requests=0,
        ),
        max_retries=max_retries,
    )


async def _catalog(store: SQLiteStore) -> tuple[UUID, AssetOccurrence]:
    document_id, version_id, notebook_id = uuid4(), uuid4(), uuid4()
    metadata = DocumentMetadata(content_hash="a" * 64)
    version = DocumentVersion(
        version_id=version_id,
        document_id=document_id,
        content_hash=metadata.content_hash,
        metadata=metadata,
        status=DocumentVersionStatus.CURRENT,
        created_at=NOW,
    )
    await store.upsert_document(
        Document(
            document_id=document_id,
            versions=(version,),
            current_version_id=version_id,
            current_hash=metadata.content_hash,
            status=DocumentStatus.INDEXED,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    await store.upsert_notebook(
        Notebook(
            notebook_id=notebook_id,
            title="Processing",
            description=None,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    await store.upsert_source(
        Source(
            source_id=uuid4(),
            notebook_id=notebook_id,
            document_id=document_id,
            created_at=NOW,
        )
    )
    asset = Asset(
        asset_id=uuid4(),
        mime_type="image/png",
        content_hash="b" * 64,
        storage_uri="blob://opaque",
    )
    locator = AssetLocator(kind=AssetLocatorKind.PDF_PAGE, ordinal=0, page_number=1)
    occurrence = AssetOccurrence(
        occurrence_id=asset_occurrence_id(
            document_id=document_id,
            version_id=version_id,
            asset_id=asset.asset_id,
            locator=locator,
        ),
        asset_id=asset.asset_id,
        document_id=document_id,
        version_id=version_id,
        container_kind=AssetContainerKind.PDF,
        locator=locator,
        authored_alt_text=None,
        extraction_provenance=AssetExtractionProvenance(
            parser_id="test", parser_version="v2", block_ordinal=0
        ),
        created_at=NOW,
    )
    await store.register_asset_ingestion(
        assets=(asset,),
        binary_reference=DocumentBinaryReference(
            document_id=document_id,
            version_id=version_id,
            asset_id=asset.asset_id,
            role=DocumentBinaryRole.ORIGINAL,
            media_type="application/pdf",
            byte_size=128,
            created_at=NOW,
        ),
        occurrences=(occurrence,),
    )
    return notebook_id, occurrence


async def _ready_store(path: Path) -> tuple[SQLiteStore, UUID, AssetOccurrence, ProcessingManifest]:
    store = SQLiteStore(path)
    await store.open()
    notebook_id, occurrence = await _catalog(store)
    return (
        store,
        notebook_id,
        occurrence,
        _manifest(actor_id="actor-a", notebook_id=notebook_id, occurrence=occurrence),
    )


def test_explicit_document_and_notebook_deletion_remove_processing_dependents(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        store, notebook_id, occurrence, manifest = await _ready_store(tmp_path / "delete.db")
        job, created = await store.submit_processing_job(manifest, now=NOW)
        assert created

        assert await store.delete_document(
            occurrence.document_id, expected_version_id=occurrence.version_id
        )
        assert (
            await store.get_processing_job(
                actor_id="actor-a", notebook_id=notebook_id, job_id=job.job_id
            )
            is None
        )
        assert await store.delete_notebook(notebook_id)
        await store.close()

    _run(scenario())


def test_fingerprint_state_machine_and_sensitive_manifest_validation() -> None:
    notebook_id = uuid4()
    occurrence = AssetOccurrence(
        occurrence_id=uuid4(),
        asset_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        container_kind=AssetContainerKind.STANDALONE,
        locator=AssetLocator(kind=AssetLocatorKind.STANDALONE, ordinal=0),
        authored_alt_text=None,
        extraction_provenance=AssetExtractionProvenance(
            parser_id="test", parser_version="v2", block_ordinal=0
        ),
        created_at=NOW,
    )
    manifest = _manifest(actor_id="actor-a", notebook_id=notebook_id, occurrence=occurrence)
    fingerprint = processing_job_fingerprint(manifest)
    assert fingerprint == processing_job_fingerprint(manifest)
    assert fingerprint == processing_job_fingerprint(
        replace(
            manifest,
            consent=replace(manifest.consent, decided_at=NOW + timedelta(seconds=1)),
        )
    )
    assert processing_job_id(fingerprint) == processing_job_id(fingerprint)
    for field, changed in (
        ("operation", replace(manifest, operation="vlm")),
        ("provider", replace(manifest, provider_identity="cloud")),
        ("model", replace(manifest, model_identity="model-v2")),
        ("target", replace(manifest, occurrence_id=uuid4())),
        ("generation", replace(manifest, generation_id=uuid4())),
    ):
        assert processing_job_fingerprint(changed) != fingerprint, field
    assert is_legal_processing_transition(ProcessingJobState.QUEUED, ProcessingJobState.CLAIMED)
    assert not is_legal_processing_transition(
        ProcessingJobState.SUCCEEDED, ProcessingJobState.QUEUED
    )
    with pytest.raises(ValueError, match="sensitive"):
        replace(manifest, configuration=FrozenMetadata({"api_key": "do-not-store"}))


def test_submit_claim_checkpoint_ledger_complete_and_replay(tmp_path: Path) -> None:
    async def scenario() -> None:
        store, notebook_id, _, manifest = await _ready_store(tmp_path / "jobs.db")
        job, created = await store.submit_processing_job(manifest, now=NOW)
        replay, replay_created = await store.submit_processing_job(
            replace(manifest, consent=replace(manifest.consent, decided_at=NOW)), now=NOW
        )
        assert created and not replay_created and replay == job
        assert (
            await store.get_processing_job(
                actor_id="other", notebook_id=notebook_id, job_id=job.job_id
            )
            is None
        )
        claim = await store.claim_processing_job(
            actor_id="actor-a",
            notebook_id=notebook_id,
            worker_id="worker-1",
            lease_duration=timedelta(minutes=1),
            now=NOW,
        )
        assert claim is not None and claim.job.state is ProcessingJobState.CLAIMED
        assert (
            await store.claim_processing_job(
                actor_id="actor-a",
                notebook_id=notebook_id,
                worker_id="worker-2",
                lease_duration=timedelta(minutes=1),
                now=NOW,
            )
            is None
        )
        running = await store.start_processing_attempt(
            job_id=job.job_id, lease_token=claim.attempt.lease_token, now=NOW
        )
        assert running.state is ProcessingJobState.RUNNING
        assert await store.renew_processing_lease(
            job_id=job.job_id,
            lease_token=claim.attempt.lease_token,
            lease_duration=timedelta(minutes=2),
            now=NOW,
        )
        checkpoint = ProcessingCheckpoint(
            checkpoint_id=uuid4(),
            job_id=job.job_id,
            attempt_id=claim.attempt.attempt_id,
            sequence=0,
            fingerprint=job.fingerprint,
            provider_profile=manifest.provider_profile,
            generation_id=None,
            payload=FrozenMetadata({"page": 1}),
            created_at=NOW,
        )
        assert await store.put_processing_checkpoint(
            checkpoint, lease_token=claim.attempt.lease_token
        )
        assert (
            await store.get_latest_processing_checkpoint(
                actor_id="actor-a", notebook_id=notebook_id, job_id=job.job_id
            )
            == checkpoint
        )
        with pytest.raises(ConflictError, match="immutable"):
            await store.put_processing_checkpoint(
                replace(checkpoint, checkpoint_id=uuid4()),
                lease_token=claim.attempt.lease_token,
            )
        ledger = ProcessingLedgerEntry(
            entry_id=uuid4(),
            job_id=job.job_id,
            attempt_id=claim.attempt.attempt_id,
            status=ProcessingCostStatus.ACTUAL,
            provider_identity=manifest.provider_identity,
            model_identity=manifest.model_identity,
            usage=FrozenMetadata({"wall_ms": 12, "cache": "miss"}),
            created_at=NOW,
        )
        assert await store.append_processing_ledger(ledger, lease_token=claim.attempt.lease_token)
        result = ProcessingResult(
            result_id=uuid4(),
            job_id=job.job_id,
            attempt_id=claim.attempt.attempt_id,
            fingerprint=job.fingerprint,
            output_reference="derivation://opaque",
            payload=FrozenMetadata({"regions": 1}),
            created_at=NOW,
        )
        completed = await store.complete_processing_job(
            result=result, lease_token=claim.attempt.lease_token, now=NOW
        )
        assert completed.state is ProcessingJobState.SUCCEEDED
        assert (
            await store.get_processing_result(
                actor_id="actor-a", notebook_id=notebook_id, job_id=job.job_id
            )
            == result
        )
        assert await store.list_processing_ledger(
            actor_id="actor-a", notebook_id=notebook_id, job_id=job.job_id
        ) == (ledger,)
        attempts = await store.list_processing_attempts(
            actor_id="actor-a", notebook_id=notebook_id, job_id=job.job_id
        )
        assert attempts[0].state is ProcessingAttemptState.SUCCEEDED
        progress = await store.list_processing_progress(
            actor_id="actor-a", notebook_id=notebook_id, job_id=job.job_id
        )
        assert [event.sequence for event in progress] == list(range(1, len(progress) + 1))
        assert progress[-1].kind is ProcessingProgressKind.COMPLETED
        with pytest.raises(ConflictError):
            await store.complete_processing_job(
                result=replace(result, result_id=uuid4()),
                lease_token=claim.attempt.lease_token,
                now=NOW,
            )
        await store.close()

    _run(scenario())


def test_retry_expiry_resume_and_exhaustion(tmp_path: Path) -> None:
    async def scenario() -> None:
        store, notebook_id, _, manifest = await _ready_store(tmp_path / "recovery.db")
        job, _ = await store.submit_processing_job(manifest, now=NOW)
        first = await store.claim_processing_job(
            actor_id="actor-a",
            notebook_id=notebook_id,
            worker_id="crashed",
            lease_duration=timedelta(seconds=1),
            now=NOW,
        )
        assert first is not None
        await store.start_processing_attempt(
            job_id=job.job_id, lease_token=first.attempt.lease_token, now=NOW
        )
        checkpoint = ProcessingCheckpoint(
            checkpoint_id=uuid4(),
            job_id=job.job_id,
            attempt_id=first.attempt.attempt_id,
            sequence=0,
            fingerprint=job.fingerprint,
            provider_profile=manifest.provider_profile,
            generation_id=None,
            payload=FrozenMetadata({"completed_units": 1}),
            created_at=NOW,
        )
        await store.put_processing_checkpoint(checkpoint, lease_token=first.attempt.lease_token)
        recovered = await store.recover_expired_processing_leases(now=NOW + timedelta(seconds=2))
        assert recovered == (job.job_id,)
        failed = await store.get_processing_job(
            actor_id="actor-a", notebook_id=notebook_id, job_id=job.job_id
        )
        assert failed is not None and failed.state is ProcessingJobState.FAILED_RETRYABLE
        queued = await store.resume_processing_job(
            actor_id="actor-a",
            notebook_id=notebook_id,
            job_id=job.job_id,
            now=NOW + timedelta(seconds=3),
        )
        assert queued.state is ProcessingJobState.QUEUED
        second = await store.claim_processing_job(
            actor_id="actor-a",
            notebook_id=notebook_id,
            worker_id="worker-2",
            lease_duration=timedelta(seconds=1),
            now=NOW + timedelta(seconds=3),
        )
        assert second is not None
        assert (
            await store.get_latest_processing_checkpoint(
                actor_id="actor-a", notebook_id=notebook_id, job_id=job.job_id
            )
            == checkpoint
        )
        await store.start_processing_attempt(
            job_id=job.job_id,
            lease_token=second.attempt.lease_token,
            now=NOW + timedelta(seconds=3),
        )
        terminal = await store.fail_processing_job(
            job_id=job.job_id,
            lease_token=second.attempt.lease_token,
            classification=ProcessingFailureClass.TRANSIENT,
            retryable=True,
            now=NOW + timedelta(seconds=4),
        )
        assert terminal.state is ProcessingJobState.FAILED_FINAL
        with pytest.raises(ConflictError):
            await store.resume_processing_job(
                actor_id="actor-a",
                notebook_id=notebook_id,
                job_id=job.job_id,
                now=NOW + timedelta(seconds=5),
            )
        attempts = await store.list_processing_attempts(
            actor_id="actor-a", notebook_id=notebook_id, job_id=job.job_id
        )
        assert [attempt.state for attempt in attempts] == [
            ProcessingAttemptState.INTERRUPTED,
            ProcessingAttemptState.FAILED_FINAL,
        ]
        await store.close()

    _run(scenario())


def test_cancellation_scope_progress_and_cleanup(tmp_path: Path) -> None:
    async def scenario() -> None:
        store, notebook_id, occurrence, manifest = await _ready_store(tmp_path / "cancel.db")
        queued, _ = await store.submit_processing_job(manifest, now=NOW)
        cancelled = await store.request_processing_cancellation(
            actor_id="actor-a", notebook_id=notebook_id, job_id=queued.job_id, now=NOW
        )
        assert cancelled.state is ProcessingJobState.CANCELLED
        with pytest.raises(ConflictError):
            await store.request_processing_cancellation(
                actor_id="actor-a", notebook_id=notebook_id, job_id=queued.job_id, now=NOW
            )
        other_manifest = _manifest(
            actor_id="actor-a",
            notebook_id=notebook_id,
            occurrence=occurrence,
            operation="vlm",
        )
        running, _ = await store.submit_processing_job(other_manifest, now=NOW)
        claim = await store.claim_processing_job(
            actor_id="actor-a",
            notebook_id=notebook_id,
            worker_id="worker",
            lease_duration=timedelta(minutes=1),
            now=NOW,
        )
        assert claim is not None and claim.job.job_id == running.job_id
        await store.start_processing_attempt(
            job_id=running.job_id, lease_token=claim.attempt.lease_token, now=NOW
        )
        requested = await store.request_processing_cancellation(
            actor_id="actor-a", notebook_id=notebook_id, job_id=running.job_id, now=NOW
        )
        assert requested.state is ProcessingJobState.CANCEL_REQUESTED
        acknowledged = await store.acknowledge_processing_cancellation(
            job_id=running.job_id, lease_token=claim.attempt.lease_token, now=NOW
        )
        assert acknowledged.state is ProcessingJobState.CANCELLED
        custom = ProcessingProgressEvent(
            event_id=uuid4(),
            job_id=running.job_id,
            sequence=99,
            kind=ProcessingProgressKind.FAILED,
            detail_code="operator-note",
            created_at=NOW,
        )
        assert await store.append_processing_progress(custom)
        with pytest.raises(ConflictError):
            await store.append_processing_progress(replace(custom, event_id=uuid4()))
        removed = await store.cleanup_processing_records(
            before=NOW + timedelta(seconds=1), limit=10
        )
        assert set(removed) == {queued.job_id, running.job_id}
        assert await store.get_asset_occurrence(occurrence.occurrence_id) == occurrence
        await store.close()

    _run(scenario())


def test_sqlite_concurrent_claim_has_one_winner(tmp_path: Path) -> None:
    async def scenario() -> None:
        path = tmp_path / "concurrent.db"
        first, notebook_id, _, manifest = await _ready_store(path)
        job, _ = await first.submit_processing_job(manifest, now=NOW)
        second = SQLiteStore(path)
        await second.open()

        async def claim(store: SQLiteStore, worker: str):
            return await store.claim_processing_job(
                actor_id="actor-a",
                notebook_id=notebook_id,
                worker_id=worker,
                lease_duration=timedelta(minutes=1),
                now=NOW,
            )

        results = await asyncio.gather(claim(first, "one"), claim(second, "two"))
        assert sum(result is not None for result in results) == 1
        attempts = await first.list_processing_attempts(
            actor_id="actor-a", notebook_id=notebook_id, job_id=job.job_id
        )
        assert len(attempts) == 1
        second_job, _ = await first.submit_processing_job(
            replace(manifest, operation="vlm"), now=NOW
        )
        same_connection = await asyncio.gather(claim(first, "three"), claim(first, "four"))
        assert sum(result is not None for result in same_connection) == 1
        assert (
            len(
                await first.list_processing_attempts(
                    actor_id="actor-a", notebook_id=notebook_id, job_id=second_job.job_id
                )
            )
            == 1
        )
        await second.close()
        await first.close()

    _run(scenario())


def test_policy_admission_and_failure_classification() -> None:
    occurrence = AssetOccurrence(
        occurrence_id=uuid4(),
        asset_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        container_kind=AssetContainerKind.STANDALONE,
        locator=AssetLocator(kind=AssetLocatorKind.STANDALONE, ordinal=0),
        authored_alt_text=None,
        extraction_provenance=AssetExtractionProvenance(
            parser_id="test", parser_version="v2", block_ordinal=0
        ),
        created_at=NOW,
    )
    manifest = _manifest(actor_id="actor", notebook_id=uuid4(), occurrence=occurrence)
    enforce_processing_policy(manifest)
    enforce_resource_admission(
        manifest, ProcessingAdmissionProfile(max_active_workers=1, max_bytes=512), active_workers=0
    )
    with pytest.raises(ProcessingAdmissionError, match="saturated"):
        enforce_resource_admission(
            manifest, ProcessingAdmissionProfile(max_active_workers=1), active_workers=1
        )
    denied = replace(
        manifest,
        consent=replace(manifest.consent, decision=ProcessingPolicyDecision.DENIED),
    )
    with pytest.raises(ProcessingPolicyError):
        enforce_processing_policy(denied)
    cloud = replace(manifest, provider_trust=ProcessingTrustClass.CLOUD)
    with pytest.raises(ProcessingPolicyError, match="egress"):
        enforce_processing_policy(cloud)
    assert classify_processing_failure(TimeoutError()) == (
        ProcessingFailureClass.TRANSIENT,
        True,
    )
    assert classify_processing_failure(ContractValidationError("bad")) == (
        ProcessingFailureClass.VALIDATION,
        False,
    )
    assert classify_processing_failure(IntegrityError("corrupt")) == (
        ProcessingFailureClass.CORRUPTED_INPUT,
        False,
    )
    assert classify_processing_failure(ProcessingPolicyError("denied")) == (
        ProcessingFailureClass.BUDGET_POLICY,
        False,
    )
    assert classify_processing_failure(ProcessingAdmissionError("busy")) == (
        ProcessingFailureClass.TRANSIENT,
        True,
    )
    assert classify_processing_failure(RuntimeError("unexpected")) == (
        ProcessingFailureClass.INTERNAL,
        False,
    )
    for invalid in (0, True):
        with pytest.raises(ValueError):
            ProcessingAdmissionProfile(max_active_workers=invalid)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ProcessingAdmissionProfile(max_active_workers=1, max_bytes=-1)
    with pytest.raises(ProcessingAdmissionError, match="deployment bytes"):
        enforce_resource_admission(
            manifest,
            ProcessingAdmissionProfile(max_active_workers=1, max_bytes=1),
            active_workers=0,
        )
    over_budget = replace(
        manifest,
        estimate=replace(
            manifest.estimate, units=FrozenMetadata({"bytes": 2048, "input_units": 1})
        ),
    )
    with pytest.raises(ProcessingPolicyError, match="bytes budget"):
        enforce_processing_policy(over_budget)
    governed_units = {
        "cpu_seconds": "max_cpu_seconds",
        "gpu_seconds": "max_gpu_seconds",
        "tokens": "max_tokens",
        "memory_bytes": "max_memory_bytes",
        "vram_bytes": "max_vram_bytes",
        "operations": "max_operations",
        "pages": "max_pages",
        "pixels": "max_pixels",
        "images": "max_images",
    }
    for unit, ceiling_name in governed_units.items():
        estimated = replace(
            manifest,
            estimate=replace(manifest.estimate, units=FrozenMetadata({unit: 2})),
        )
        with pytest.raises(ProcessingPolicyError, match=f"{unit} budget"):
            enforce_processing_policy(
                replace(estimated, budget=ProcessingBudget(**{ceiling_name: 1}))
            )
        with pytest.raises(ProcessingAdmissionError, match=f"deployment {unit}"):
            enforce_resource_admission(
                estimated,
                ProcessingAdmissionProfile(max_active_workers=1, **{ceiling_name: 1}),
                active_workers=0,
            )


def test_worker_success_and_failure_are_durable(tmp_path: Path) -> None:
    async def scenario() -> None:
        store, notebook_id, occurrence, manifest = await _ready_store(tmp_path / "worker.db")
        job, _ = await store.submit_processing_job(manifest, now=NOW)
        calls = 0

        async def operation(current, checkpoint, cancelled):  # type: ignore[no-untyped-def]
            nonlocal calls
            calls += 1
            assert checkpoint is None and not await cancelled()
            attempts = await store.list_processing_attempts(
                actor_id="actor-a", notebook_id=notebook_id, job_id=current.job_id
            )
            return ProcessingResult(
                result_id=uuid4(),
                job_id=current.job_id,
                attempt_id=attempts[-1].attempt_id,
                fingerprint=current.fingerprint,
                output_reference=None,
                payload=FrozenMetadata({"ok": True}),
                created_at=NOW,
            )

        worker = ProcessingWorker(
            store=store,
            actor_id="actor-a",
            notebook_id=notebook_id,
            worker_id="worker",
            operations={"ocr": operation},
            admission_profile=ProcessingAdmissionProfile(max_active_workers=1),
            clock=lambda: NOW,
        )
        assert await worker.run_once(now=NOW)
        assert calls == 1
        assert not await worker.run_once(now=NOW)
        assert (
            await store.get_processing_result(
                actor_id="actor-a", notebook_id=notebook_id, job_id=job.job_id
            )
            is not None
        )
        invalid_manifest = _manifest(
            actor_id="actor-a",
            notebook_id=notebook_id,
            occurrence=occurrence,
            operation="missing",
            max_retries=0,
        )
        invalid, _ = await store.submit_processing_job(invalid_manifest, now=NOW)
        assert await worker.run_once(now=NOW)
        stored = await store.get_processing_job(
            actor_id="actor-a", notebook_id=notebook_id, job_id=invalid.job_id
        )
        assert stored is not None and stored.state is ProcessingJobState.FAILED_FINAL
        await store.close()

    _run(scenario())


def test_worker_bounded_retry_policy_block_and_cooperative_cancel(tmp_path: Path) -> None:
    async def scenario() -> None:
        store, notebook_id, occurrence, manifest = await _ready_store(tmp_path / "worker-races.db")
        retrying, _ = await store.submit_processing_job(manifest, now=NOW)
        calls = 0

        async def flaky(current, checkpoint, cancelled):  # type: ignore[no-untyped-def]
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError("provider temporarily unavailable")
            attempts = await store.list_processing_attempts(
                actor_id="actor-a", notebook_id=notebook_id, job_id=current.job_id
            )
            return ProcessingResult(
                result_id=uuid4(),
                job_id=current.job_id,
                attempt_id=attempts[-1].attempt_id,
                fingerprint=current.fingerprint,
                output_reference=None,
                payload=FrozenMetadata({"attempt": calls}),
                created_at=NOW,
            )

        worker = ProcessingWorker(
            store=store,
            actor_id="actor-a",
            notebook_id=notebook_id,
            worker_id="worker",
            operations={"ocr": flaky},
            admission_profile=ProcessingAdmissionProfile(max_active_workers=1),
            lease_duration=timedelta(seconds=1),
            clock=lambda: NOW,
        )
        assert await worker.run_once(now=NOW)
        queued = await store.get_processing_job(
            actor_id="actor-a", notebook_id=notebook_id, job_id=retrying.job_id
        )
        assert queued is not None and queued.state is ProcessingJobState.QUEUED
        assert await worker.run_once(now=NOW)
        assert calls == 2

        denied_manifest = replace(
            _manifest(
                actor_id="actor-a",
                notebook_id=notebook_id,
                occurrence=occurrence,
                operation="denied",
            ),
            consent=ProcessingConsent(
                decision=ProcessingPolicyDecision.DENIED,
                policy_version="policy/v1",
                decided_at=NOW,
                reason_code="operator_denied",
            ),
        )
        denied, _ = await store.submit_processing_job(denied_manifest, now=NOW)
        denied_worker = ProcessingWorker(
            store=store,
            actor_id="actor-a",
            notebook_id=notebook_id,
            worker_id="worker",
            operations={},
            admission_profile=ProcessingAdmissionProfile(max_active_workers=1),
            clock=lambda: NOW,
        )
        assert await denied_worker.run_once(now=NOW)
        blocked = await store.get_processing_job(
            actor_id="actor-a", notebook_id=notebook_id, job_id=denied.job_id
        )
        assert blocked is not None and blocked.state is ProcessingJobState.BLOCKED_POLICY

        cancel_manifest = _manifest(
            actor_id="actor-a",
            notebook_id=notebook_id,
            occurrence=occurrence,
            operation="cancel",
        )
        cancelling, _ = await store.submit_processing_job(cancel_manifest, now=NOW)

        async def cancel_operation(current, checkpoint, cancelled):  # type: ignore[no-untyped-def]
            await store.request_processing_cancellation(
                actor_id="actor-a",
                notebook_id=notebook_id,
                job_id=current.job_id,
                now=NOW,
            )
            assert await cancelled()
            raise OperationCancelledError("cooperative provider cancellation")

        cancel_worker = ProcessingWorker(
            store=store,
            actor_id="actor-a",
            notebook_id=notebook_id,
            worker_id="worker",
            operations={"cancel": cancel_operation},
            admission_profile=ProcessingAdmissionProfile(max_active_workers=1),
            clock=lambda: NOW,
        )
        assert await cancel_worker.run_once(now=NOW)
        cancelled = await store.get_processing_job(
            actor_id="actor-a", notebook_id=notebook_id, job_id=cancelling.job_id
        )
        assert cancelled is not None and cancelled.state is ProcessingJobState.CANCELLED
        await store.close()

    _run(scenario())


def test_store_rejects_stale_provenance_and_invalid_bounds(tmp_path: Path) -> None:
    async def scenario() -> None:
        store, notebook_id, occurrence, manifest = await _ready_store(tmp_path / "invalid-jobs.db")
        with pytest.raises(IntegrityError, match="authorized notebook"):
            await store.submit_processing_job(replace(manifest, occurrence_id=uuid4()), now=NOW)
        for invalid in (0, 1001, True):
            with pytest.raises(ContractValidationError):
                await store.list_processing_jobs(
                    actor_id="actor-a", notebook_id=notebook_id, limit=invalid
                )
        job, _ = await store.submit_processing_job(manifest, now=NOW)
        with pytest.raises(ContractValidationError):
            await store.claim_processing_job(
                actor_id="actor-a",
                notebook_id=notebook_id,
                worker_id="worker",
                lease_duration=timedelta(0),
                now=NOW,
            )
        claim = await store.claim_processing_job(
            actor_id="actor-a",
            notebook_id=notebook_id,
            worker_id="worker",
            lease_duration=timedelta(minutes=1),
            now=NOW,
        )
        assert claim is not None
        with pytest.raises(ConflictError):
            await store.start_processing_attempt(job_id=job.job_id, lease_token=uuid4(), now=NOW)
        await store.start_processing_attempt(
            job_id=job.job_id, lease_token=claim.attempt.lease_token, now=NOW
        )
        assert not await store.renew_processing_lease(
            job_id=job.job_id,
            lease_token=uuid4(),
            lease_duration=timedelta(minutes=1),
            now=NOW,
        )
        with pytest.raises(ContractValidationError):
            await store.renew_processing_lease(
                job_id=job.job_id,
                lease_token=claim.attempt.lease_token,
                lease_duration=timedelta(0),
                now=NOW,
            )
        checkpoint = ProcessingCheckpoint(
            checkpoint_id=uuid4(),
            job_id=job.job_id,
            attempt_id=uuid4(),
            sequence=0,
            fingerprint=job.fingerprint,
            provider_profile=manifest.provider_profile,
            generation_id=None,
            payload=FrozenMetadata(),
            created_at=NOW,
        )
        with pytest.raises(IntegrityError, match="active attempt"):
            await store.put_processing_checkpoint(checkpoint, lease_token=claim.attempt.lease_token)
        with pytest.raises(IntegrityError, match="incompatible"):
            await store.put_processing_checkpoint(
                replace(
                    checkpoint,
                    attempt_id=claim.attempt.attempt_id,
                    fingerprint="f" * 64,
                ),
                lease_token=claim.attempt.lease_token,
            )
        result = ProcessingResult(
            result_id=uuid4(),
            job_id=job.job_id,
            attempt_id=claim.attempt.attempt_id,
            fingerprint="f" * 64,
            output_reference=None,
            payload=FrozenMetadata(),
            created_at=NOW,
        )
        with pytest.raises(IntegrityError, match="fingerprint"):
            await store.complete_processing_job(
                result=result, lease_token=claim.attempt.lease_token, now=NOW
            )
        with pytest.raises(IntegrityError, match="active attempt"):
            await store.complete_processing_job(
                result=replace(result, fingerprint=job.fingerprint, attempt_id=uuid4()),
                lease_token=claim.attempt.lease_token,
                now=NOW,
            )
        ledger = ProcessingLedgerEntry(
            entry_id=uuid4(),
            job_id=job.job_id,
            attempt_id=uuid4(),
            status=ProcessingCostStatus.ACTUAL,
            provider_identity=manifest.provider_identity,
            model_identity=manifest.model_identity,
            usage=FrozenMetadata(),
            created_at=NOW,
        )
        with pytest.raises(IntegrityError, match="active attempt"):
            await store.append_processing_ledger(ledger, lease_token=claim.attempt.lease_token)
        with pytest.raises(ConflictError, match="active processing lease"):
            await store.append_processing_ledger(ledger, lease_token=uuid4())
        missing_event = ProcessingProgressEvent(
            event_id=uuid4(),
            job_id=uuid4(),
            sequence=1,
            kind=ProcessingProgressKind.RUNNING,
            detail_code="safe",
            created_at=NOW,
        )
        with pytest.raises(IntegrityError, match="does not exist"):
            await store.append_processing_progress(missing_event)
        event = replace(missing_event, job_id=job.job_id)
        with pytest.raises(ConflictError, match="active lease"):
            await store.append_processing_progress(event, lease_token=uuid4())
        for kwargs in ({"limit": 0}, {"after_sequence": -1}):
            with pytest.raises(ContractValidationError):
                await store.list_processing_progress(
                    actor_id="actor-a",
                    notebook_id=notebook_id,
                    job_id=job.job_id,
                    **kwargs,
                )
        with pytest.raises(ContractValidationError):
            await store.cleanup_processing_records(before=NOW, limit=0)
        assert (
            await store.get_latest_processing_checkpoint(
                actor_id="other", notebook_id=notebook_id, job_id=job.job_id
            )
            is None
        )
        assert (
            await store.get_processing_result(
                actor_id="other", notebook_id=notebook_id, job_id=job.job_id
            )
            is None
        )
        assert (
            await store.list_processing_attempts(
                actor_id="other", notebook_id=notebook_id, job_id=job.job_id
            )
            == ()
        )
        assert (
            await store.list_processing_ledger(
                actor_id="other", notebook_id=notebook_id, job_id=job.job_id
            )
            == ()
        )
        assert (
            await store.list_processing_progress(
                actor_id="other", notebook_id=notebook_id, job_id=job.job_id
            )
            == ()
        )
        with pytest.raises(IntegrityError, match="unavailable in scope"):
            await store.request_processing_cancellation(
                actor_id="other", notebook_id=notebook_id, job_id=job.job_id, now=NOW
            )
        with pytest.raises(IntegrityError, match="unavailable in scope"):
            await store.resume_processing_job(
                actor_id="other", notebook_id=notebook_id, job_id=job.job_id, now=NOW
            )
        with pytest.raises(ConflictError, match="active processing lease"):
            await store.fail_processing_job(
                job_id=job.job_id,
                lease_token=uuid4(),
                classification=ProcessingFailureClass.INTERNAL,
                retryable=False,
                now=NOW,
            )
        assert await store.get_asset_occurrence(occurrence.occurrence_id) == occurrence
        await store.close()

    _run(scenario())


def test_result_publication_rolls_back_at_crash_boundary(tmp_path: Path) -> None:
    async def scenario() -> None:
        store, notebook_id, _, manifest = await _ready_store(tmp_path / "publication-crash.db")
        job, _ = await store.submit_processing_job(manifest, now=NOW)
        claim = await store.claim_processing_job(
            actor_id="actor-a",
            notebook_id=notebook_id,
            worker_id="worker",
            lease_duration=timedelta(minutes=1),
            now=NOW,
        )
        assert claim is not None
        await store.start_processing_attempt(
            job_id=job.job_id, lease_token=claim.attempt.lease_token, now=NOW
        )
        db = store._require_open()
        await db.execute(
            """CREATE TRIGGER reject_processing_completion
               BEFORE UPDATE OF state ON processing_jobs
               WHEN NEW.state = 'succeeded'
               BEGIN SELECT RAISE(ABORT, 'injected crash'); END"""
        )
        await db.commit()
        result = ProcessingResult(
            result_id=uuid4(),
            job_id=job.job_id,
            attempt_id=claim.attempt.attempt_id,
            fingerprint=job.fingerprint,
            output_reference=None,
            payload=FrozenMetadata({"safe": True}),
            created_at=NOW,
        )
        with pytest.raises(StorageError, match="transaction failed"):
            await store.complete_processing_job(
                result=result, lease_token=claim.attempt.lease_token, now=NOW
            )
        assert (
            await store.get_processing_result(
                actor_id="actor-a", notebook_id=notebook_id, job_id=job.job_id
            )
            is None
        )
        still_running = await store.get_processing_job(
            actor_id="actor-a", notebook_id=notebook_id, job_id=job.job_id
        )
        assert still_running is not None and still_running.state is ProcessingJobState.RUNNING
        await store.close()

    _run(scenario())


def test_worker_heartbeat_run_loop_and_helpers(tmp_path: Path) -> None:
    async def scenario() -> None:
        store, notebook_id, _, manifest = await _ready_store(tmp_path / "heartbeat.db")
        job, _ = await store.submit_processing_job(manifest, now=datetime.now(UTC))

        async def slow(current, checkpoint, cancelled):  # type: ignore[no-untyped-def]
            await asyncio.sleep(0.4)
            attempts = await store.list_processing_attempts(
                actor_id="actor-a", notebook_id=notebook_id, job_id=current.job_id
            )
            return ProcessingResult(
                result_id=uuid4(),
                job_id=current.job_id,
                attempt_id=attempts[-1].attempt_id,
                fingerprint=current.fingerprint,
                output_reference=None,
                payload=FrozenMetadata({"slow": True}),
                created_at=datetime.now(UTC),
            )

        worker = ProcessingWorker(
            store=store,
            actor_id="actor-a",
            notebook_id=notebook_id,
            worker_id="heartbeat",
            operations={"ocr": slow},
            admission_profile=ProcessingAdmissionProfile(max_active_workers=1),
            lease_duration=timedelta(milliseconds=300),
            poll_interval=0.01,
        )
        assert await worker.run_once()
        attempts = await store.list_processing_attempts(
            actor_id="actor-a", notebook_id=notebook_id, job_id=job.job_id
        )
        ledger = make_actual_ledger_entry(
            job=job,
            attempt_id=attempts[0].attempt_id,
            usage=FrozenMetadata({"wall_ms": 40}),
            now=NOW,
        )
        event = make_progress_event(
            job_id=job.job_id,
            sequence=100,
            kind=ProcessingProgressKind.COMPLETED,
            detail_code="helper",
            now=NOW,
        )
        assert ledger.job_id == job.job_id and event.sequence == 100
        streamed = [
            item
            async for item in stream_processing_progress(
                store=store,
                actor_id="actor-a",
                notebook_id=notebook_id,
                job_id=job.job_id,
                poll_interval=0.01,
            )
        ]
        assert streamed and streamed[-1].kind is ProcessingProgressKind.COMPLETED

        idle = ProcessingWorker(
            store=store,
            actor_id="actor-a",
            notebook_id=notebook_id,
            worker_id="idle",
            operations={},
            admission_profile=ProcessingAdmissionProfile(max_active_workers=1),
            poll_interval=0.01,
        )
        task = asyncio.create_task(idle.run())
        await asyncio.sleep(0.02)
        await idle.stop()
        await task
        await store.close()

    _run(scenario())

    with pytest.raises(TypeError):
        ProcessingWorker(  # type: ignore[arg-type]
            store=object(),
            actor_id="a",
            notebook_id=uuid4(),
            worker_id="w",
            operations={},
            admission_profile=ProcessingAdmissionProfile(max_active_workers=1),
        )

    async def invalid_stream() -> None:
        with pytest.raises(ContractValidationError):
            async for _ in stream_processing_progress(
                store=object(),  # type: ignore[arg-type]
                actor_id="a",
                notebook_id=uuid4(),
                job_id=uuid4(),
                poll_interval=0,
            ):
                pass

    _run(invalid_stream())


def test_schema_8_upgrade_idempotency_and_rollback(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "v7.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE schema_versions(version INTEGER PRIMARY KEY, applied_at TEXT)")
        db.execute("INSERT INTO schema_versions VALUES(7, ?)", (NOW.isoformat(),))
    store = SQLiteStore(path)
    _run(store.open())
    _run(store.close())
    _run(store.open())
    _run(store.close())
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT MAX(version) FROM schema_versions").fetchone() == (16,)
        assert db.execute(
            "SELECT name FROM sqlite_master WHERE name='processing_jobs'"
        ).fetchone() == ("processing_jobs",)

    import mnemo.storage.sqlite as sqlite_module

    broken = tmp_path / "broken.db"
    with sqlite3.connect(broken) as db:
        db.execute("CREATE TABLE schema_versions(version INTEGER PRIMARY KEY, applied_at TEXT)")
        db.execute("INSERT INTO schema_versions VALUES(7, ?)", (NOW.isoformat(),))
    original = sqlite_module.PROCESSING_SCHEMA_STATEMENTS
    monkeypatch.setattr(
        sqlite_module,
        "PROCESSING_SCHEMA_STATEMENTS",
        ("CREATE TABLE processing_probe(value INTEGER)", "INVALID SQL"),
    )
    with pytest.raises(aiosqlite.OperationalError):
        _run(SQLiteStore(broken).open())
    with sqlite3.connect(broken) as db:
        assert db.execute("SELECT MAX(version) FROM schema_versions").fetchone() == (7,)
        assert (
            db.execute("SELECT name FROM sqlite_master WHERE name='processing_probe'").fetchone()
            is None
        )
    monkeypatch.setattr(sqlite_module, "PROCESSING_SCHEMA_STATEMENTS", original)


def test_queue_saturation_preserves_every_logical_job(tmp_path: Path) -> None:
    async def scenario() -> None:
        store, notebook_id, _, manifest = await _ready_store(tmp_path / "queue.db")
        manifests = tuple(replace(manifest, operation=f"operation-{index}") for index in range(100))
        submitted = await asyncio.gather(
            *(store.submit_processing_job(item, now=NOW) for item in manifests)
        )
        assert len({job.job_id for job, created in submitted if created}) == 100
        replayed = await asyncio.gather(
            *(store.submit_processing_job(item, now=NOW) for item in manifests)
        )
        assert not any(created for _, created in replayed)
        jobs = await store.list_processing_jobs(
            actor_id="actor-a", notebook_id=notebook_id, limit=100
        )
        assert len(jobs) == 100
        await store.close()

    _run(scenario())


def test_composite_exposes_additive_processing_store_without_widening_v1() -> None:
    async def scenario() -> None:
        method_names = (
            "submit_processing_job",
            "get_processing_job",
            "list_processing_jobs",
            "claim_processing_job",
            "start_processing_attempt",
            "renew_processing_lease",
            "put_processing_checkpoint",
            "get_latest_processing_checkpoint",
            "request_processing_cancellation",
            "acknowledge_processing_cancellation",
            "fail_processing_job",
            "resume_processing_job",
            "recover_expired_processing_leases",
            "complete_processing_job",
            "get_processing_result",
            "list_processing_attempts",
            "append_processing_ledger",
            "list_processing_ledger",
            "append_processing_progress",
            "list_processing_progress",
            "cleanup_processing_records",
        )
        backend = SimpleNamespace(**{name: AsyncMock(return_value=None) for name in method_names})
        composite = object.__new__(CompositeStorage)
        composite._sql = backend  # type: ignore[assignment]
        notebook_id, job_id, token = uuid4(), uuid4(), uuid4()
        occurrence = AssetOccurrence(
            occurrence_id=uuid4(),
            asset_id=uuid4(),
            document_id=uuid4(),
            version_id=uuid4(),
            container_kind=AssetContainerKind.STANDALONE,
            locator=AssetLocator(kind=AssetLocatorKind.STANDALONE, ordinal=0),
            authored_alt_text=None,
            extraction_provenance=AssetExtractionProvenance(
                parser_id="test", parser_version="v2", block_ordinal=0
            ),
            created_at=NOW,
        )
        manifest = _manifest(actor_id="actor", notebook_id=notebook_id, occurrence=occurrence)
        await composite.submit_processing_job(manifest, now=NOW)
        await composite.get_processing_job(actor_id="actor", notebook_id=notebook_id, job_id=job_id)
        await composite.list_processing_jobs(actor_id="actor", notebook_id=notebook_id, limit=1)
        await composite.claim_processing_job(
            actor_id="actor",
            notebook_id=notebook_id,
            worker_id="worker",
            lease_duration=timedelta(seconds=1),
            now=NOW,
        )
        await composite.start_processing_attempt(job_id=job_id, lease_token=token, now=NOW)
        await composite.renew_processing_lease(
            job_id=job_id,
            lease_token=token,
            lease_duration=timedelta(seconds=1),
            now=NOW,
        )
        await composite.put_processing_checkpoint(None, lease_token=token)  # type: ignore[arg-type]
        await composite.get_latest_processing_checkpoint(
            actor_id="actor", notebook_id=notebook_id, job_id=job_id
        )
        await composite.request_processing_cancellation(
            actor_id="actor", notebook_id=notebook_id, job_id=job_id, now=NOW
        )
        await composite.acknowledge_processing_cancellation(
            job_id=job_id, lease_token=token, now=NOW
        )
        await composite.fail_processing_job(
            job_id=job_id,
            lease_token=token,
            classification=ProcessingFailureClass.INTERNAL,
            retryable=False,
            now=NOW,
        )
        await composite.resume_processing_job(
            actor_id="actor", notebook_id=notebook_id, job_id=job_id, now=NOW
        )
        await composite.recover_expired_processing_leases(now=NOW)
        await composite.complete_processing_job(result=None, lease_token=token, now=NOW)  # type: ignore[arg-type]
        await composite.get_processing_result(
            actor_id="actor", notebook_id=notebook_id, job_id=job_id
        )
        await composite.list_processing_attempts(
            actor_id="actor", notebook_id=notebook_id, job_id=job_id
        )
        await composite.append_processing_ledger(None, lease_token=token)  # type: ignore[arg-type]
        await composite.list_processing_ledger(
            actor_id="actor", notebook_id=notebook_id, job_id=job_id
        )
        await composite.append_processing_progress(None, lease_token=token)  # type: ignore[arg-type]
        await composite.list_processing_progress(
            actor_id="actor", notebook_id=notebook_id, job_id=job_id
        )
        await composite.cleanup_processing_records(before=NOW, limit=1)
        assert all(getattr(backend, name).await_count == 1 for name in method_names)
        assert isinstance(composite, ProcessingJobStoreV1)

    _run(scenario())
