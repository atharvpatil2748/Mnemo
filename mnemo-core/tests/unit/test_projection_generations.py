"""Focused WP-02 lifecycle, migration, projection, and runtime tests."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import aiosqlite
import pytest
from mnemo import EmbeddingConfig, LLMConfig, LLMRoleConfig, MnemoConfig, PluginConfig
from mnemo.config import RerankerConfig, StorageConfig
from mnemo.interfaces.errors import (
    ConflictError,
    ContractValidationError,
    OperationCancelledError,
)
from mnemo.models import (
    FrozenMetadata,
    LanguageCapabilityState,
    LanguageCode,
    LanguageDerivation,
    LanguageDerivationKind,
    LanguageProviderProfile,
    LanguageTransformationRequest,
    ProcessingBudget,
    ProcessingConsent,
    ProcessingCostStatus,
    ProcessingEstimate,
    ProcessingManifest,
    ProcessingPolicyDecision,
    ProcessingTrustClass,
    ScriptCode,
)
from mnemo.phase85 import (
    DerivedProjectionCoordinator,
    LanguageTextProjectionBuilder,
    MultilingualVectorProjectionBuilder,
    OCRTextProjectionBuilder,
    Phase85ProviderRegistration,
    Phase85Runtime,
    Phase85ServiceRegistration,
    ProjectionBuildProcessingOperation,
    ProjectionBuildResult,
    ProjectionCompleteness,
    ProjectionCoverage,
    ProjectionGenerationSpec,
    ProjectionLifecycleState,
    ProviderReadinessResult,
    VisionTextProjectionBuilder,
    VisualVectorProjectionBuilder,
    make_projection_processing_manifest,
    projection_service_registration,
)
from mnemo.processing import ProcessingAdmissionProfile, ProcessingWorker
from mnemo.storage.sqlite import SQLiteStore

NOW = datetime(2026, 8, 26, tzinfo=UTC)


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _spec(
    *,
    capability: str = "vision_text",
    profile: str = "production-v1",
    fingerprint: str = "a" * 64,
    version_id: UUID | None = None,
    source_generation_ids: tuple[UUID, ...] = (),
) -> ProjectionGenerationSpec:
    return ProjectionGenerationSpec(
        capability=capability,
        profile_id=profile,
        schema_version=1,
        input_scope="notebook:fixture",
        provider_identity="test-provider",
        model_identity="test-model",
        model_revision="revision-1",
        configuration_fingerprint=fingerprint,
        source_version_ids=() if version_id is None else (version_id,),
        source_generation_ids=source_generation_ids,
    )


@dataclass(slots=True)
class _Builder:
    result: ProjectionBuildResult | Exception
    calls: int = 0

    async def build(self, generation_id: UUID) -> ProjectionBuildResult:
        del generation_id
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        await asyncio.sleep(0)
        return self.result


@dataclass(slots=True)
class _Probe:
    async def probe(self, profile: object) -> ProviderReadinessResult:
        del profile
        return ProviderReadinessResult(
            available_locally=True,
            loadable=True,
            initialized=True,
        )


def _complete(count: int = 1) -> ProjectionBuildResult:
    return ProjectionBuildResult(
        expected_count=count,
        succeeded_count=count,
        failed_count=0,
        skipped_count=0,
        checksum=hashlib.sha256(f"complete:{count}".encode()).hexdigest(),
    )


def test_projection_contract_models_reject_ambiguous_lifecycle_evidence() -> None:
    """Projection identity, counts, and coverage remain deterministic and fail closed."""
    spec = _spec()
    assert spec.persisted_model_identity == "test-model@revision-1"
    assert replace(spec, model_revision=None).persisted_model_identity == "test-model"
    assert replace(spec, model_identity=None, model_revision=None).persisted_model_identity is None
    assert ProjectionGenerationSpec.from_manifest_payload(spec.manifest_payload()) == spec
    assert spec.new_generation(NOW).generation_id == spec.generation_id

    for changes, message in (
        ({"capability": " "}, "capability"),
        ({"profile_id": ""}, "profile_id"),
        ({"input_scope": ""}, "input_scope"),
        ({"schema_version": 0}, "schema_version"),
        ({"configuration_fingerprint": "short"}, "configuration_fingerprint"),
        ({"dimensions": 0}, "dimensions"),
        ({"source_version_ids": (uuid4(),) * 2}, "source_version_ids"),
        ({"source_generation_ids": (uuid4(),) * 2}, "source_generation_ids"),
    ):
        with pytest.raises(ValueError, match=message):
            replace(spec, **changes)
    with pytest.raises(ValueError):
        replace(spec, configuration_fingerprint="z" * 64)
    with pytest.raises(ValueError, match="timezone-aware"):
        spec.new_generation(datetime(2026, 1, 1))
    with pytest.raises(ContractValidationError, match="malformed"):
        ProjectionGenerationSpec.from_manifest_payload({})
    with pytest.raises(ContractValidationError, match="malformed"):
        ProjectionGenerationSpec.from_manifest_payload(
            {**spec.manifest_payload(), "source_version_ids": "not-a-list"}
        )

    complete = _complete(1)
    assert complete.completeness is ProjectionCompleteness.COMPLETE
    partial = ProjectionBuildResult(
        expected_count=2,
        succeeded_count=1,
        failed_count=1,
        skipped_count=0,
        checksum="a" * 64,
    )
    assert partial.completeness is ProjectionCompleteness.PARTIAL
    with pytest.raises(ValueError, match="non-negative"):
        replace(complete, failed_count=-1)
    with pytest.raises(ValueError, match="account"):
        replace(complete, expected_count=2)
    with pytest.raises(ValueError, match="SHA-256"):
        replace(complete, checksum="short")

    coverage = ProjectionCoverage.from_result(spec.generation_id, complete, updated_at=NOW)
    assert coverage.completeness is ProjectionCompleteness.COMPLETE
    with pytest.raises(ValueError, match="completeness"):
        replace(coverage, completeness=ProjectionCompleteness.PARTIAL)
    with pytest.raises(ValueError, match="failure_digest"):
        replace(coverage, failure_digest="short")
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(coverage, updated_at=datetime(2026, 1, 1))


def _config(tmp_path: Path) -> MnemoConfig:
    role = LLMRoleConfig(provider="test", model="gemma4:e4b", max_context_tokens=128)
    return MnemoConfig(
        storage=StorageConfig(),
        llm=LLMConfig(planner=role, synthesizer=role, extractor=role, classifier=role),
        embedding=EmbeddingConfig(provider="test", model="embedding", dimensions=3),
        reranker=RerankerConfig(provider="test", model="reranker"),
        plugins=PluginConfig(directory=tmp_path / "plugins"),
    )


def _processing_manifest(
    *, notebook_id: UUID, document_id: UUID, version_id: UUID, occurrence_id: UUID
) -> ProcessingManifest:
    return ProcessingManifest(
        actor_id="wp02-operator",
        notebook_id=notebook_id,
        operation="fixture",
        occurrence_id=occurrence_id,
        document_id=document_id,
        version_id=version_id,
        provider_profile="fixture",
        provider_identity="mnemo-local",
        provider_trust=ProcessingTrustClass.LOCAL,
        model_identity="local-projection",
        configuration=FrozenMetadata({"fixture": True}),
        generation_id=None,
        language=None,
        output_schema="fixture/v1",
        policy_version="wp02/v1",
        consent=ProcessingConsent(
            decision=ProcessingPolicyDecision.ALLOWED,
            policy_version="wp02/v1",
            decided_at=NOW,
            reason_code="local_processing",
        ),
        estimate=ProcessingEstimate(
            status=ProcessingCostStatus.ESTIMATED,
            units=FrozenMetadata({"operations": 1}),
            uncertainty=None,
        ),
        budget=ProcessingBudget(max_operations=1),
        max_retries=1,
    )


async def _processing_scope(store: SQLiteStore) -> tuple[UUID, UUID, UUID, UUID]:
    notebook_id, document_id, version_id, occurrence_id, asset_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    db = store._require_open()
    await db.execute(
        "INSERT INTO notebooks VALUES(?,?,?,?,?,?)",
        (str(notebook_id), "WP-02", None, NOW.isoformat(), NOW.isoformat(), "{}"),
    )
    await db.execute(
        "INSERT INTO documents VALUES(?,?,?,?,?,?)",
        (
            str(document_id),
            str(version_id),
            "a" * 64,
            "indexed",
            NOW.isoformat(),
            NOW.isoformat(),
        ),
    )
    await db.execute(
        "INSERT INTO document_versions VALUES(?,?,?,?,?,?)",
        (
            str(version_id),
            str(document_id),
            "a" * 64,
            json.dumps({}),
            "current",
            NOW.isoformat(),
        ),
    )
    await db.execute(
        "INSERT INTO sources VALUES(?,?,?,?)",
        (str(uuid4()), str(notebook_id), str(document_id), NOW.isoformat()),
    )
    await db.execute(
        "INSERT INTO asset_catalog VALUES(?,?,?,?,?,?,?,?)",
        (
            str(asset_id),
            "image/png",
            "b" * 64,
            f"sha256://{'b' * 64}",
            1,
            1,
            "{}",
            NOW.isoformat(),
        ),
    )
    await db.execute(
        "INSERT INTO asset_occurrences VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            str(occurrence_id),
            str(asset_id),
            str(document_id),
            str(version_id),
            "standalone",
            "standalone",
            "{}",
            None,
            "{}",
            NOW.isoformat(),
        ),
    )
    await db.commit()
    return notebook_id, document_id, version_id, occurrence_id


def test_generation_identity_tracks_source_and_profile_contract() -> None:
    version = uuid4()
    first = _spec(version_id=version)
    assert first.generation_id == _spec(version_id=version).generation_id
    assert first.generation_id != _spec(version_id=uuid4()).generation_id
    assert first.generation_id != _spec(version_id=version, fingerprint="b" * 64).generation_id
    assert first.generation_id != _spec(version_id=version, profile="production-v2").generation_id


def test_complete_build_is_atomic_active_and_idempotent(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = SQLiteStore(tmp_path / "complete.db")
        await store.open()
        coordinator = DerivedProjectionCoordinator(store, clock=lambda: NOW)
        builder = _Builder(_complete(2))
        spec = _spec()

        before = await coordinator.inspect(spec)
        first, second = await asyncio.gather(
            coordinator.build_and_activate(spec, builder),
            coordinator.build_and_activate(spec, builder),
        )

        assert before.state is ProjectionLifecycleState.PENDING
        assert first.active and second.active
        assert first.state is ProjectionLifecycleState.READY
        assert builder.calls == 1
        assert (
            await store.get_active_index_generation(spec.capability, spec.profile_id)
        ) is not None
        await store.close()

    _run(scenario())


def test_partial_and_failed_generations_never_activate(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = SQLiteStore(tmp_path / "failure.db")
        await store.open()
        coordinator = DerivedProjectionCoordinator(store, clock=lambda: NOW)
        partial = _Builder(
            ProjectionBuildResult(
                expected_count=2,
                succeeded_count=1,
                failed_count=1,
                skipped_count=0,
                checksum="c" * 64,
            )
        )
        partial_status = await coordinator.build_and_activate(_spec(), partial)
        failed_spec = _spec(capability="language_text")
        with pytest.raises(RuntimeError, match="private detail"):
            await coordinator.build_and_activate(
                failed_spec, _Builder(RuntimeError("private detail"))
            )
        failed_status = await coordinator.inspect(failed_spec)

        assert partial_status.state is ProjectionLifecycleState.INVALID
        assert partial_status.reason_code == "generation_partial"
        assert not partial_status.active
        assert failed_status.state is ProjectionLifecycleState.FAILED
        assert failed_status.coverage is not None
        assert failed_status.coverage.failure_digest is not None
        await store.close()

    _run(scenario())


def test_cancelled_projection_fails_closed_before_build(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = SQLiteStore(tmp_path / "cancelled.db")
        await store.open()
        spec = _spec(version_id=uuid4())
        builder = _Builder(_complete())

        async def cancelled() -> bool:
            return True

        with pytest.raises(OperationCancelledError):
            await DerivedProjectionCoordinator(store, clock=lambda: NOW).build_and_activate(
                spec,
                builder,
                resume_building=True,
                cancelled=cancelled,
            )
        status = await DerivedProjectionCoordinator(store, clock=lambda: NOW).inspect(spec)
        assert status.state is ProjectionLifecycleState.RUNNING
        assert not status.active
        assert builder.calls == 0
        resumed = await DerivedProjectionCoordinator(store, clock=lambda: NOW).build_and_activate(
            spec, builder, resume_building=True
        )
        assert resumed.active
        assert builder.calls == 1
        await store.close()

    _run(scenario())


def test_profile_change_marks_prior_active_generation_stale(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = SQLiteStore(tmp_path / "stale.db")
        await store.open()
        coordinator = DerivedProjectionCoordinator(store, clock=lambda: NOW)
        await coordinator.build_and_activate(_spec(), _Builder(_complete()))

        stale = await coordinator.inspect(_spec(fingerprint="d" * 64))

        assert stale.state is ProjectionLifecycleState.STALE
        assert stale.reason_code == "active_generation_profile_mismatch"
        assert not stale.active
        await store.close()

    _run(scenario())


def test_building_generation_resumes_and_prior_ready_generation_can_be_restored(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        store = SQLiteStore(tmp_path / "resume.db")
        await store.open()
        coordinator = DerivedProjectionCoordinator(store, clock=lambda: NOW)
        version = uuid4()
        first_spec = _spec(version_id=version)
        first = await coordinator.build_and_activate(first_spec, _Builder(_complete()))
        second_spec = _spec(version_id=version, fingerprint="2" * 64)
        assert await store.create_index_generation(second_spec.new_generation(NOW))
        assert await store.put_index_generation_sources(
            generation_id=second_spec.generation_id,
            source_generation_ids=second_spec.source_generation_ids,
            source_version_ids=second_spec.source_version_ids,
        )

        resumed = await coordinator.build_and_activate(
            second_spec, _Builder(_complete(2)), resume_building=True
        )
        assert resumed.active
        assert resumed.generation_id != first.generation_id
        assert await store.rollback_index_generation(first_spec.generation_id)
        restored = await coordinator.inspect(first_spec)
        assert restored.active
        await store.close()

    _run(scenario())


def test_projection_source_contract_and_coverage_integrity_fail_closed(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = SQLiteStore(tmp_path / "integrity.db")
        await store.open()
        source_generation, version = uuid4(), uuid4()
        spec = _spec(version_id=version, source_generation_ids=(source_generation,))
        coordinator = DerivedProjectionCoordinator(store, clock=lambda: NOW)
        status = await coordinator.build_and_activate(spec, _Builder(_complete()))
        assert status.active
        assert await store.get_index_generation_sources(spec.generation_id) == (
            (source_generation,),
            (version,),
        )
        db = store._require_open()
        await db.execute(
            "UPDATE index_generation_coverage SET checksum=? WHERE generation_id=?",
            ("f" * 64, str(spec.generation_id)),
        )
        await db.commit()
        invalid = await coordinator.inspect(spec)
        assert invalid.state is ProjectionLifecycleState.INVALID
        assert invalid.reason_code == "coverage_integrity_mismatch"
        assert not invalid.active
        await store.close()

    _run(scenario())


def test_projection_storage_lifecycle_rejects_conflicts_and_incomplete_rollback(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        store = SQLiteStore(tmp_path / "projection-boundaries.db")
        await store.open()
        missing = uuid4()
        coverage = ProjectionCoverage.from_result(missing, _complete(), updated_at=NOW)
        with pytest.raises(ConflictError, match="BUILDING"):
            await store.put_index_generation_coverage(coverage)
        with pytest.raises(ConflictError, match="BUILDING"):
            await store.put_index_generation_sources(
                generation_id=missing,
                source_generation_ids=(),
                source_version_ids=(),
            )
        assert not await store.rollback_index_generation(missing)

        spec = _spec(version_id=uuid4(), source_generation_ids=(uuid4(),))
        assert await store.create_index_generation(spec.new_generation(NOW))
        assert await store.put_index_generation_sources(
            generation_id=spec.generation_id,
            source_generation_ids=spec.source_generation_ids,
            source_version_ids=spec.source_version_ids,
        )
        assert not await store.put_index_generation_sources(
            generation_id=spec.generation_id,
            source_generation_ids=spec.source_generation_ids,
            source_version_ids=spec.source_version_ids,
        )
        with pytest.raises(ConflictError, match="source contract is immutable"):
            await store.put_index_generation_sources(
                generation_id=spec.generation_id,
                source_generation_ids=(uuid4(),),
                source_version_ids=spec.source_version_ids,
            )

        built = ProjectionCoverage.from_result(spec.generation_id, _complete(), updated_at=NOW)
        assert await store.put_index_generation_coverage(built)
        assert not await store.put_index_generation_coverage(built)
        with pytest.raises(ConflictError, match="coverage is immutable"):
            await store.put_index_generation_coverage(replace(built, checksum="e" * 64))
        assert await store.get_index_generation_coverage(spec.generation_id) == built
        assert await store.get_index_generation_coverage(uuid4()) is None

        db = store._require_open()
        await db.execute(
            "UPDATE index_generations SET state='superseded' WHERE generation_id=?",
            (str(spec.generation_id),),
        )
        await db.execute(
            "UPDATE index_generation_coverage SET completeness='partial' WHERE generation_id=?",
            (str(spec.generation_id),),
        )
        await db.commit()
        with pytest.raises(ConflictError, match="complete valid coverage"):
            await store.rollback_index_generation(spec.generation_id)
        await db.execute(
            "UPDATE index_generation_coverage SET completeness='complete' WHERE generation_id=?",
            (str(spec.generation_id),),
        )
        await db.execute(
            "UPDATE index_generations SET item_count=?,checksum=? WHERE generation_id=?",
            (built.succeeded_count, built.checksum, str(spec.generation_id)),
        )
        await db.commit()
        assert not await store.rollback_index_generation(spec.generation_id)
        await store.close()

    _run(scenario())


def test_governed_projection_job_is_idempotent_checkpointed_and_completes(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        store = SQLiteStore(tmp_path / "job.db")
        await store.open()
        notebook_id, document_id, version_id, occurrence_id = await _processing_scope(store)
        spec = _spec(version_id=version_id)
        manifest = make_projection_processing_manifest(
            _processing_manifest(
                notebook_id=notebook_id,
                document_id=document_id,
                version_id=version_id,
                occurrence_id=occurrence_id,
            ),
            spec,
        )
        first, created = await store.submit_processing_job(manifest, now=NOW)
        duplicate, duplicate_created = await store.submit_processing_job(manifest, now=NOW)
        assert created and not duplicate_created and duplicate.job_id == first.job_id
        builder = _Builder(_complete())
        operation = ProjectionBuildProcessingOperation(
            coordinator=DerivedProjectionCoordinator(store, clock=lambda: NOW),
            job_store=store,
            builders={spec.capability: builder},
            clock=lambda: NOW,
        )
        worker = ProcessingWorker(
            store=store,
            actor_id=manifest.actor_id,
            notebook_id=notebook_id,
            worker_id="wp02-worker",
            operations={manifest.operation: operation},
            admission_profile=ProcessingAdmissionProfile(max_active_workers=1),
        )
        assert await worker.run_once(now=NOW)
        result = await store.get_processing_result(
            actor_id=manifest.actor_id,
            notebook_id=notebook_id,
            job_id=first.job_id,
        )
        checkpoint = await store.get_latest_processing_checkpoint(
            actor_id=manifest.actor_id,
            notebook_id=notebook_id,
            job_id=first.job_id,
        )
        assert (
            result is not None
            and result.output_reference == f"index-generation:{spec.generation_id}"
        )
        assert checkpoint is not None and checkpoint.generation_id == spec.generation_id
        assert builder.calls == 1
        await store.close()

    _run(scenario())


def test_validated_projection_status_gates_runtime_activation(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = SQLiteStore(tmp_path / "runtime.db")
        await store.open()
        coordinator = DerivedProjectionCoordinator(store, clock=lambda: NOW)
        status = await coordinator.build_and_activate(_spec(), _Builder(_complete()))
        config = _config(tmp_path)
        profile_fingerprint = Phase85Runtime(config, engine_ready=False).active_profile.fingerprint
        registration = projection_service_registration(
            capability_id="vision",
            service=store,
            status=status,
            profile_fingerprint=profile_fingerprint,
        )
        runtime = Phase85Runtime(
            config,
            engine_ready=True,
            core_active_capabilities=frozenset(
                {"canonical_ingestion", "v1_retrieval", "authorization"}
            ),
            provider_registrations=(
                Phase85ProviderRegistration(profile_id="vision", probe=_Probe()),
            ),
            service_registrations=(
                Phase85ServiceRegistration(
                    capability_id="processing_jobs",
                    service=store,
                    ready=True,
                    activate=True,
                ),
                registration,
            ),
        )
        await runtime.initialize()

        vision = runtime.capability_status("vision")
        assert vision.state.active
        assert not vision.state.behaviorally_verified
        assert not vision.state.certified
        assert vision.generation_id == str(status.generation_id)
        await store.close()

    _run(scenario())


def test_generated_empty_projection_is_distinct_from_missing(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = SQLiteStore(tmp_path / "empty.db")
        await store.open()
        spec = _spec(capability="vision_text")
        coordinator = DerivedProjectionCoordinator(store, clock=lambda: NOW)
        assert (await coordinator.inspect(spec)).state is ProjectionLifecycleState.PENDING

        ready = await coordinator.build_and_activate(
            spec,
            VisionTextProjectionBuilder(store=store, source_generation_ids=()),
        )

        assert ready.active
        assert ready.coverage is not None
        assert ready.coverage.expected_count == 0
        await store.close()

    _run(scenario())


def test_language_text_projection_persists_derived_text_separately(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = SQLiteStore(tmp_path / "language.db")
        await store.open()
        source_generation = uuid4()
        provider = LanguageProviderProfile(
            provider="local-test",
            model="translation-test",
            revision="r1",
            profile="en-mr",
            configuration_digest="e" * 64,
            trust_class=ProcessingTrustClass.LOCAL,
            supported_languages=(LanguageCode("en"), LanguageCode("mr")),
            supported_scripts=(ScriptCode("Latn"), ScriptCode("Deva")),
            supported_directions=("en->mr",),
            state=LanguageCapabilityState.SUPPORTED,
        )
        request = LanguageTransformationRequest(
            actor_id=uuid4(),
            notebook_id=uuid4(),
            document_id=uuid4(),
            version_id=uuid4(),
            occurrence_id=uuid4(),
            source_evidence_id="chunk:fixture",
            source_text="source truth",
            source_language=LanguageCode("en"),
            target_language=LanguageCode("mr"),
            kind=LanguageDerivationKind.TRANSLATION,
            provider_profile=provider,
            preprocessing_digest="f" * 64,
            generation_id=source_generation,
            consent=ProcessingConsent(
                decision=ProcessingPolicyDecision.ALLOWED,
                policy_version="fixture/v1",
                decided_at=NOW,
                reason_code="local",
            ),
        )
        output = "स्रोत मजकूर"
        derivation = LanguageDerivation(
            derivation_id=request.derivation_id(),
            cache_key=request.cache_key(),
            actor_id=request.actor_id,
            notebook_id=request.notebook_id,
            document_id=request.document_id,
            version_id=request.version_id,
            source_evidence_id=request.source_evidence_id,
            source_hash=request.source_hash,
            source_language=request.source_language,
            target_language=request.target_language,
            kind=request.kind,
            output_text=output,
            output_hash=hashlib.sha256(output.encode()).hexdigest(),
            provider_profile=provider,
            preprocessing_digest=request.preprocessing_digest,
            generation_id=source_generation,
            created_at=NOW,
        )
        assert await store.put_language_derivation(derivation)
        spec = _spec(capability="language_text", source_generation_ids=(source_generation,))
        status = await DerivedProjectionCoordinator(store, clock=lambda: NOW).build_and_activate(
            spec,
            LanguageTextProjectionBuilder(store=store, source_generation_ids=(source_generation,)),
        )
        assert status.active
        await store.close()
        with sqlite3.connect(tmp_path / "language.db") as db:
            assert db.execute("SELECT COUNT(*) FROM language_text_projection_rows").fetchone() == (
                1,
            )
            assert db.execute("SELECT COUNT(*) FROM language_text_fts").fetchone() == (1,)

    _run(scenario())


def test_multilingual_vector_generation_reuses_existing_embedding_rows(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = SQLiteStore(tmp_path / "multilingual-vector.db")
        await store.open()
        source_generation = uuid4()
        db = store._require_open()
        await db.execute(
            """INSERT INTO multilingual_embeddings(
               embedding_id,notebook_id,source_evidence_id,language,generation_id,
               vector_space,payload,payload_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                str(uuid4()),
                str(uuid4()),
                "chunk:fixture",
                "mr",
                str(source_generation),
                "bge-m3@test",
                "immutable-payload",
                "9" * 64,
                NOW.isoformat(),
            ),
        )
        await db.commit()
        spec = _spec(
            capability="multilingual_vector",
            source_generation_ids=(source_generation,),
        )
        status = await DerivedProjectionCoordinator(store, clock=lambda: NOW).build_and_activate(
            spec,
            MultilingualVectorProjectionBuilder(
                store=store, source_generation_ids=(source_generation,)
            ),
        )
        assert status.active
        assert status.coverage is not None and status.coverage.succeeded_count == 1
        assert (
            await (
                await db.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE name='multilingual_vector_projection_rows'"
                )
            ).fetchone()
            is None
        )
        await store.close()

    _run(scenario())


def test_ocr_and_visual_projection_builders_account_for_each_input() -> None:
    class Store:
        def __init__(self) -> None:
            self.ocr_calls = 0
            self.visual_calls = 0

        async def project_ocr_result(self, **values: object) -> None:
            self.ocr_calls += 1
            if getattr(values["result"], "fail", False):
                raise RuntimeError("projection rejected")

        async def list_ocr_projection_regions(self, **_: object) -> tuple[UUID, ...]:
            return (UUID(int=self.ocr_calls),)

        async def project_visual_embedding(self, **values: object) -> None:
            self.visual_calls += 1
            if getattr(values["embedding"], "fail", False):
                raise RuntimeError("projection rejected")

        async def list_visual_projection_derivations(self, **_: object) -> tuple[UUID, ...]:
            return (UUID(int=1),)

    store = Store()
    ocr_results = (
        type("OCR", (), {"derivation_id": uuid4(), "fail": False})(),
        type("OCR", (), {"derivation_id": uuid4(), "fail": True})(),
    )
    ocr = _run(
        OCRTextProjectionBuilder(store=store, results=ocr_results).build(uuid4())  # type: ignore[arg-type]
    )
    assert (ocr.expected_count, ocr.succeeded_count, ocr.failed_count) == (2, 1, 1)

    embeddings = (
        type("Visual", (), {"fail": False})(),
        type("Visual", (), {"fail": True})(),
    )
    visual = _run(
        VisualVectorProjectionBuilder(store=store, embeddings=embeddings).build(  # type: ignore[arg-type]
            uuid4()
        )
    )
    assert (visual.expected_count, visual.succeeded_count, visual.failed_count) == (2, 1, 1)
    assert len(visual.checksum) == 64


def test_schema_v15_upgrade_repeat_and_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mnemo.storage.sqlite as sqlite_module

    path = tmp_path / "v13.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE schema_versions(version INTEGER PRIMARY KEY,applied_at TEXT)")
        db.execute("INSERT INTO schema_versions VALUES(13,'2026-08-25T00:00:00+00:00')")
        # v14 foreign-key dependencies already existed at schema v13.
        db.executescript(";".join(sqlite_module._ASSET_CATALOG_SCHEMA_STATEMENTS))
        from mnemo.storage.multilingual import MULTILINGUAL_SCHEMA_STATEMENTS
        from mnemo.storage.vision import VISION_SCHEMA_STATEMENTS

        db.executescript(";".join(VISION_SCHEMA_STATEMENTS))
        db.executescript(";".join(MULTILINGUAL_SCHEMA_STATEMENTS))
    original = sqlite_module.PROJECTION_GENERATION_SCHEMA_STATEMENTS
    monkeypatch.setattr(
        sqlite_module,
        "PROJECTION_GENERATION_SCHEMA_STATEMENTS",
        ("CREATE TABLE wp02_probe(value INTEGER)", "NOT VALID SQL"),
    )
    with pytest.raises(aiosqlite.OperationalError):
        _run(SQLiteStore(path).open())
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT MAX(version) FROM schema_versions").fetchone() == (13,)
        assert (
            db.execute("SELECT name FROM sqlite_master WHERE name='wp02_probe'").fetchone() is None
        )
    monkeypatch.setattr(sqlite_module, "PROJECTION_GENERATION_SCHEMA_STATEMENTS", original)
    store = SQLiteStore(path)
    _run(store.open())
    _run(store.close())
    _run(store.open())
    _run(store.close())
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT MAX(version) FROM schema_versions").fetchone() == (16,)
        for table in (
            "index_generation_sources",
            "index_generation_coverage",
            "vision_text_projection_rows",
            "language_text_projection_rows",
        ):
            assert db.execute(
                "SELECT name FROM sqlite_master WHERE name=?", (table,)
            ).fetchone() == (table,)


def test_wp02_uses_isolated_storage_and_does_not_modify_evaluation_corpus(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    golden_root = root / "goldenDataset"
    evaluation_root = golden_root / "Phase 8.5 Evaluation Corpus"
    eval_files = (
        [path for path in sorted(evaluation_root.rglob("*")) if path.is_file()]
        if evaluation_root.exists()
        else []
    )
    golden_files = (
        [path for path in sorted(golden_root.iterdir()) if path.is_file()]
        if golden_root.exists()
        else []
    )
    if eval_files and golden_files:
        sources = (eval_files[0], golden_files[0])
    else:
        corpus_dir = tmp_path / "reference_corpus"
        corpus_dir.mkdir(parents=True, exist_ok=True)
        file1 = corpus_dir / "sample1.txt"
        file1.write_text("corpus data 1", encoding="utf-8")
        file2 = corpus_dir / "sample2.txt"
        file2.write_text("corpus data 2", encoding="utf-8")
        sources = (file1, file2)
    before = {source: hashlib.sha256(source.read_bytes()).hexdigest() for source in sources}

    async def scenario() -> None:
        store = SQLiteStore(tmp_path / "isolated.db")
        await store.open()
        await DerivedProjectionCoordinator(store, clock=lambda: NOW).build_and_activate(
            _spec(), _Builder(_complete())
        )
        await store.close()

    _run(scenario())
    assert {source: hashlib.sha256(source.read_bytes()).hexdigest() for source in sources} == before
