"""Deterministic build, validation, promotion, and inspection for derived projections."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid5

from mnemo.interfaces.errors import (
    ConflictError,
    ContractValidationError,
    IntegrityError,
    OperationCancelledError,
)
from mnemo.interfaces.ocr import OCRStoreV1
from mnemo.interfaces.processing_jobs import ProcessingJobStoreV1
from mnemo.interfaces.projections import DerivedProjectionBuilderV1, DerivedProjectionStoreV1
from mnemo.interfaces.vision import VisionStoreV1
from mnemo.models import FrozenMetadata, IndexGeneration, IndexGenerationState, thaw_metadata
from mnemo.models.ocr import OCRResult
from mnemo.models.processing import (
    ProcessingCheckpoint,
    ProcessingJob,
    ProcessingManifest,
    ProcessingResult,
)
from mnemo.models.vision import VisualEmbedding

if TYPE_CHECKING:
    from mnemo.phase85.runtime import Phase85ServiceRegistration

_GENERATION_NAMESPACE = UUID("cb1ca4a6-bf5f-55ce-a465-2e74f09ea93a")
_CHECKPOINT_NAMESPACE = UUID("387bb4b7-acde-55cb-9f1e-c31abbf19d18")
_RESULT_NAMESPACE = UUID("66042542-fc95-5085-879e-14391de3a82f")
PROJECTION_BUILD_OPERATION = "derived_projection_build"


class ProjectionLifecycleState(StrEnum):
    """Truthful operational view over the persisted generation state machine."""

    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    STALE = "stale"
    FAILED = "failed"
    INVALID = "invalid"


class ProjectionCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectionGenerationSpec:
    """Exact source/profile/schema contract for one deterministic generation."""

    capability: str
    profile_id: str
    schema_version: int
    input_scope: str
    provider_identity: str | None
    model_identity: str | None
    model_revision: str | None
    configuration_fingerprint: str
    source_version_ids: tuple[UUID, ...] = ()
    source_generation_ids: tuple[UUID, ...] = ()
    dimensions: int | None = None
    required: bool = True

    def __post_init__(self) -> None:
        for value, name in (
            (self.capability, "capability"),
            (self.profile_id, "profile_id"),
            (self.input_scope, "input_scope"),
        ):
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if self.schema_version <= 0:
            raise ValueError("schema_version must be positive")
        if len(self.configuration_fingerprint) != 64:
            raise ValueError("configuration_fingerprint must be SHA-256")
        int(self.configuration_fingerprint, 16)
        if self.dimensions is not None and self.dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if len(set(self.source_version_ids)) != len(self.source_version_ids):
            raise ValueError("source_version_ids must be unique")
        if len(set(self.source_generation_ids)) != len(self.source_generation_ids):
            raise ValueError("source_generation_ids must be unique")

    def identity_payload(self) -> dict[str, object]:
        return {
            "capability": self.capability,
            "configuration_fingerprint": self.configuration_fingerprint,
            "dimensions": self.dimensions,
            "input_scope": self.input_scope,
            "model_identity": self.model_identity,
            "model_revision": self.model_revision,
            "profile_id": self.profile_id,
            "provider_identity": self.provider_identity,
            "schema_version": self.schema_version,
            "source_generation_ids": sorted(str(item) for item in self.source_generation_ids),
            "source_version_ids": sorted(str(item) for item in self.source_version_ids),
        }

    @property
    def contract_digest(self) -> str:
        payload = json.dumps(
            self.identity_payload(), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(payload).hexdigest()

    @property
    def generation_id(self) -> UUID:
        return uuid5(_GENERATION_NAMESPACE, self.contract_digest)

    @property
    def persisted_model_identity(self) -> str | None:
        if self.model_identity is None:
            return None
        if self.model_revision is None:
            return self.model_identity
        return f"{self.model_identity}@{self.model_revision}"

    def new_generation(self, now: datetime) -> IndexGeneration:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        return IndexGeneration(
            generation_id=self.generation_id,
            capability=self.capability,
            profile=self.profile_id,
            schema_version=self.schema_version,
            input_scope=self.input_scope,
            provider_identity=self.provider_identity,
            model_identity=self.persisted_model_identity,
            configuration_digest=self.contract_digest,
            dimensions=self.dimensions,
            state=IndexGenerationState.BUILDING,
            item_count=0,
            checksum=None,
            created_at=now.astimezone(UTC),
            updated_at=now.astimezone(UTC),
        )

    def compatible_with(self, generation: IndexGeneration) -> bool:
        return (
            generation.generation_id == self.generation_id
            and generation.capability == self.capability
            and generation.profile == self.profile_id
            and generation.schema_version == self.schema_version
            and generation.input_scope == self.input_scope
            and generation.provider_identity == self.provider_identity
            and generation.model_identity == self.persisted_model_identity
            and generation.configuration_digest == self.contract_digest
            and generation.dimensions == self.dimensions
        )

    def manifest_payload(self) -> dict[str, object]:
        return {**self.identity_payload(), "required": self.required}

    @classmethod
    def from_manifest_payload(cls, raw: Mapping[str, object]) -> ProjectionGenerationSpec:
        try:
            source_versions = raw["source_version_ids"]
            source_generations = raw["source_generation_ids"]
            if not isinstance(source_versions, list) or not isinstance(source_generations, list):
                raise TypeError
            return cls(
                capability=str(raw["capability"]),
                profile_id=str(raw["profile_id"]),
                schema_version=int(str(raw["schema_version"])),
                input_scope=str(raw["input_scope"]),
                provider_identity=(
                    None if raw.get("provider_identity") is None else str(raw["provider_identity"])
                ),
                model_identity=(
                    None if raw.get("model_identity") is None else str(raw["model_identity"])
                ),
                model_revision=(
                    None if raw.get("model_revision") is None else str(raw["model_revision"])
                ),
                configuration_fingerprint=str(raw["configuration_fingerprint"]),
                source_version_ids=tuple(UUID(str(item)) for item in source_versions),
                source_generation_ids=tuple(UUID(str(item)) for item in source_generations),
                dimensions=(None if raw.get("dimensions") is None else int(str(raw["dimensions"]))),
                required=bool(raw.get("required", True)),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ContractValidationError("projection build manifest is malformed") from error


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectionBuildResult:
    """Builder output prior to lifecycle validation and promotion."""

    expected_count: int
    succeeded_count: int
    failed_count: int
    skipped_count: int
    checksum: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.expected_count, "expected_count"),
            (self.succeeded_count, "succeeded_count"),
            (self.failed_count, "failed_count"),
            (self.skipped_count, "skipped_count"),
        ):
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.succeeded_count + self.failed_count + self.skipped_count != self.expected_count:
            raise ValueError("build counts must account for every expected item")
        if len(self.checksum) != 64:
            raise ValueError("checksum must be SHA-256")
        int(self.checksum, 16)

    @property
    def completeness(self) -> ProjectionCompleteness:
        if self.failed_count == 0 and self.skipped_count == 0:
            return ProjectionCompleteness.COMPLETE
        return ProjectionCompleteness.PARTIAL


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectionCoverage:
    generation_id: UUID
    expected_count: int
    succeeded_count: int
    failed_count: int
    skipped_count: int
    completeness: ProjectionCompleteness
    checksum: str
    failure_digest: str | None
    updated_at: datetime

    def __post_init__(self) -> None:
        ProjectionBuildResult(
            expected_count=self.expected_count,
            succeeded_count=self.succeeded_count,
            failed_count=self.failed_count,
            skipped_count=self.skipped_count,
            checksum=self.checksum,
        )
        expected = (
            ProjectionCompleteness.COMPLETE
            if self.failed_count == 0 and self.skipped_count == 0
            else ProjectionCompleteness.PARTIAL
        )
        if self.completeness is not expected:
            raise ValueError("completeness does not match generation counts")
        if self.failure_digest is not None:
            if len(self.failure_digest) != 64:
                raise ValueError("failure_digest must be SHA-256")
            int(self.failure_digest, 16)
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise ValueError("updated_at must be timezone-aware")

    @classmethod
    def from_result(
        cls,
        generation_id: UUID,
        result: ProjectionBuildResult,
        *,
        updated_at: datetime,
        failure_digest: str | None = None,
    ) -> ProjectionCoverage:
        return cls(
            generation_id=generation_id,
            expected_count=result.expected_count,
            succeeded_count=result.succeeded_count,
            failed_count=result.failed_count,
            skipped_count=result.skipped_count,
            completeness=result.completeness,
            checksum=result.checksum,
            failure_digest=failure_digest,
            updated_at=updated_at,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectionStatus:
    generation_id: UUID
    state: ProjectionLifecycleState
    active: bool
    compatible: bool
    coverage: ProjectionCoverage | None
    reason_code: str

    @property
    def eligible_for_activation(self) -> bool:
        return (
            self.state is ProjectionLifecycleState.READY
            and self.compatible
            and self.coverage is not None
            and self.coverage.completeness is ProjectionCompleteness.COMPLETE
        )


class DerivedProjectionCoordinator:
    """Coordinate one existing generation registry without owning another queue."""

    def __init__(
        self,
        store: DerivedProjectionStoreV1,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not isinstance(store, DerivedProjectionStoreV1):
            raise TypeError("store must implement DerivedProjectionStoreV1")
        self._store = store
        self._clock = clock
        self._locks: dict[UUID, asyncio.Lock] = {}

    async def inspect(self, spec: ProjectionGenerationSpec) -> ProjectionStatus:
        if not spec.required:
            return ProjectionStatus(
                generation_id=spec.generation_id,
                state=ProjectionLifecycleState.NOT_REQUIRED,
                active=False,
                compatible=True,
                coverage=None,
                reason_code="projection_not_required",
            )
        generation = await self._store.get_index_generation(spec.generation_id)
        active = await self._store.get_active_index_generation(spec.capability, spec.profile_id)
        if generation is None:
            return ProjectionStatus(
                generation_id=spec.generation_id,
                state=(
                    ProjectionLifecycleState.STALE
                    if active is not None
                    else ProjectionLifecycleState.PENDING
                ),
                active=False,
                compatible=False,
                coverage=None,
                reason_code=(
                    "active_generation_profile_mismatch"
                    if active is not None
                    else "generation_missing"
                ),
            )
        compatible = spec.compatible_with(generation)
        coverage = await self._store.get_index_generation_coverage(spec.generation_id)
        if not compatible:
            state = ProjectionLifecycleState.STALE
            reason = "generation_contract_mismatch"
        elif generation.state is IndexGenerationState.BUILDING:
            state = ProjectionLifecycleState.RUNNING
            reason = "generation_building"
        elif generation.state is IndexGenerationState.FAILED:
            state = (
                ProjectionLifecycleState.INVALID
                if coverage is not None
                and coverage.completeness is ProjectionCompleteness.PARTIAL
                and coverage.failure_digest is None
                else ProjectionLifecycleState.FAILED
            )
            reason = (
                "generation_partial"
                if state is ProjectionLifecycleState.INVALID
                else "generation_failed"
            )
        elif generation.state is not IndexGenerationState.READY:
            state = ProjectionLifecycleState.STALE
            reason = f"generation_{generation.state.value}"
        elif coverage is None:
            state = ProjectionLifecycleState.INVALID
            reason = "coverage_missing"
        elif coverage.completeness is not ProjectionCompleteness.COMPLETE:
            state = ProjectionLifecycleState.INVALID
            reason = "coverage_partial"
        elif (
            generation.item_count != coverage.succeeded_count
            or generation.checksum != coverage.checksum
        ):
            state = ProjectionLifecycleState.INVALID
            reason = "coverage_integrity_mismatch"
        else:
            state = ProjectionLifecycleState.READY
            reason = "generation_active" if active == generation else "generation_ready_not_active"
        return ProjectionStatus(
            generation_id=spec.generation_id,
            state=state,
            active=active == generation and state is ProjectionLifecycleState.READY,
            compatible=compatible,
            coverage=coverage,
            reason_code=reason,
        )

    async def build_and_activate(
        self,
        spec: ProjectionGenerationSpec,
        builder: DerivedProjectionBuilderV1,
        *,
        resume_building: bool = False,
        cancelled: Callable[[], Awaitable[bool]] | None = None,
    ) -> ProjectionStatus:
        if not spec.required:
            return await self.inspect(spec)
        if not isinstance(builder, DerivedProjectionBuilderV1):
            raise TypeError("builder must implement DerivedProjectionBuilderV1")
        lock = self._locks.setdefault(spec.generation_id, asyncio.Lock())
        async with lock:
            existing = await self.inspect(spec)
            if existing.active or existing.state in {
                ProjectionLifecycleState.FAILED,
                ProjectionLifecycleState.INVALID,
            }:
                return existing
            if existing.state is ProjectionLifecycleState.RUNNING and not resume_building:
                return existing
            if existing.state is ProjectionLifecycleState.READY:
                promoted = await self._store.promote_index_generation(spec.generation_id)
                if not promoted:
                    raise ConflictError("READY generation could not be promoted")
                return await self.inspect(spec)
            created = (
                existing.state is not ProjectionLifecycleState.RUNNING
                and await self._store.create_index_generation(spec.new_generation(self._clock()))
            )
            if existing.state is not ProjectionLifecycleState.RUNNING and not created:
                return await self.inspect(spec)
            try:
                await self._store.put_index_generation_sources(
                    generation_id=spec.generation_id,
                    source_generation_ids=spec.source_generation_ids,
                    source_version_ids=spec.source_version_ids,
                )
                if cancelled is not None and await cancelled():
                    raise OperationCancelledError("projection build cancelled before execution")
                result = await builder.build(spec.generation_id)
                if cancelled is not None and await cancelled():
                    raise OperationCancelledError("projection build cancelled before publication")
                coverage = ProjectionCoverage.from_result(
                    spec.generation_id, result, updated_at=self._clock()
                )
                await self._store.put_index_generation_coverage(coverage)
                if coverage.completeness is not ProjectionCompleteness.COMPLETE:
                    await self._store.transition_index_generation(
                        spec.generation_id,
                        IndexGenerationState.BUILDING,
                        IndexGenerationState.FAILED,
                        item_count=result.succeeded_count,
                    )
                    return await self.inspect(spec)
                transitioned = await self._store.transition_index_generation(
                    spec.generation_id,
                    IndexGenerationState.BUILDING,
                    IndexGenerationState.READY,
                    item_count=result.succeeded_count,
                    checksum=result.checksum,
                )
                if not transitioned:
                    raise ConflictError("generation lifecycle changed before READY publication")
                if not await self._store.promote_index_generation(spec.generation_id):
                    raise ConflictError("READY generation could not be promoted")
                return await self.inspect(spec)
            except BaseException as error:
                if isinstance(error, OperationCancelledError):
                    # Cancellation and lease loss must never publish, but they also
                    # must not poison the deterministic generation a new lease owner
                    # may already be resuming.
                    raise
                current = await self._store.get_index_generation(spec.generation_id)
                if current is not None and current.state is IndexGenerationState.BUILDING:
                    failure_result = ProjectionBuildResult(
                        expected_count=1,
                        succeeded_count=0,
                        failed_count=1,
                        skipped_count=0,
                        checksum=hashlib.sha256(b"").hexdigest(),
                    )
                    await self._store.put_index_generation_coverage(
                        ProjectionCoverage.from_result(
                            spec.generation_id,
                            failure_result,
                            updated_at=self._clock(),
                            failure_digest=hashlib.sha256(
                                type(error).__name__.encode()
                            ).hexdigest(),
                        )
                    )
                    await self._store.transition_index_generation(
                        spec.generation_id,
                        IndexGenerationState.BUILDING,
                        IndexGenerationState.FAILED,
                    )
                if isinstance(
                    error,
                    (ConflictError, ContractValidationError),
                ):
                    raise
                raise


def make_projection_processing_manifest(
    base: ProcessingManifest, spec: ProjectionGenerationSpec
) -> ProcessingManifest:
    """Bind one authorized processing scope to an immutable projection contract."""
    if not spec.required:
        raise ContractValidationError("a NOT_REQUIRED projection cannot be submitted")
    if not spec.source_version_ids or base.version_id not in spec.source_version_ids:
        raise ContractValidationError(
            "projection job version must be present in the immutable source scope"
        )
    model = spec.model_identity or "local-projection"
    if spec.model_revision is not None:
        model = f"{model}@{spec.model_revision}"
    return replace(
        base,
        operation=PROJECTION_BUILD_OPERATION,
        provider_profile=spec.profile_id,
        provider_identity=spec.provider_identity or "mnemo-local",
        model_identity=model,
        configuration=FrozenMetadata({"projection": spec.manifest_payload()}),
        generation_id=spec.generation_id,
        output_schema="derived-projection/v1",
    )


class ProjectionBuildProcessingOperation:
    """Governed, lease-aware adapter over the single projection coordinator."""

    def __init__(
        self,
        *,
        coordinator: DerivedProjectionCoordinator,
        job_store: ProcessingJobStoreV1,
        builders: Mapping[str, DerivedProjectionBuilderV1],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not isinstance(job_store, ProcessingJobStoreV1):
            raise TypeError("job_store must implement ProcessingJobStoreV1")
        for builder in builders.values():
            if not isinstance(builder, DerivedProjectionBuilderV1):
                raise TypeError("builders must implement DerivedProjectionBuilderV1")
        self._coordinator = coordinator
        self._jobs = job_store
        self._builders = dict(builders)
        self._clock = clock

    async def __call__(
        self,
        job: ProcessingJob,
        checkpoint: ProcessingCheckpoint | None,
        cancelled: Callable[[], Awaitable[bool]],
    ) -> ProcessingResult:
        spec = _projection_spec_from_job(job)
        if checkpoint is not None and checkpoint.generation_id != spec.generation_id:
            raise IntegrityError("projection checkpoint belongs to another generation")
        builder = self._builders.get(spec.capability)
        if builder is None:
            raise ContractValidationError("projection builder is not registered")
        status = await self._coordinator.build_and_activate(
            spec,
            builder,
            resume_building=True,
            cancelled=cancelled,
        )
        if not status.active or not status.eligible_for_activation or status.coverage is None:
            raise IntegrityError("projection generation did not reach active complete state")
        if await cancelled():
            raise OperationCancelledError("projection build cancelled before result publication")
        attempts = await self._jobs.list_processing_attempts(
            actor_id=job.manifest.actor_id,
            notebook_id=job.manifest.notebook_id,
            job_id=job.job_id,
        )
        if not attempts or job.lease_token is None:
            raise IntegrityError("projection job has no active attempt provenance")
        attempt = attempts[-1]
        now = self._clock()
        checkpoint_record = ProcessingCheckpoint(
            checkpoint_id=uuid5(
                _CHECKPOINT_NAMESPACE,
                f"{job.job_id}:{attempt.attempt_id}:{spec.generation_id}",
            ),
            job_id=job.job_id,
            attempt_id=attempt.attempt_id,
            sequence=0,
            fingerprint=job.fingerprint,
            provider_profile=job.manifest.provider_profile,
            generation_id=spec.generation_id,
            payload=FrozenMetadata(
                {
                    "state": status.state.value,
                    "coverage_checksum": status.coverage.checksum,
                    "succeeded_count": status.coverage.succeeded_count,
                }
            ),
            created_at=now,
        )
        await self._jobs.put_processing_checkpoint(checkpoint_record, lease_token=job.lease_token)
        return ProcessingResult(
            result_id=uuid5(_RESULT_NAMESPACE, f"{job.job_id}:{spec.generation_id}"),
            job_id=job.job_id,
            attempt_id=attempt.attempt_id,
            fingerprint=job.fingerprint,
            output_reference=f"index-generation:{spec.generation_id}",
            payload=FrozenMetadata(
                {
                    "capability": spec.capability,
                    "generation_id": str(spec.generation_id),
                    "coverage_checksum": status.coverage.checksum,
                    "item_count": status.coverage.succeeded_count,
                    "completeness": status.coverage.completeness.value,
                }
            ),
            created_at=now,
        )


def _projection_spec_from_job(job: ProcessingJob) -> ProjectionGenerationSpec:
    if job.manifest.operation != PROJECTION_BUILD_OPERATION:
        raise IntegrityError("processing job is not a projection build")
    raw = thaw_metadata(job.manifest.configuration).get("projection")
    if not isinstance(raw, dict):
        raise IntegrityError("projection job manifest configuration is unavailable")
    spec = ProjectionGenerationSpec.from_manifest_payload(raw)
    if job.manifest.generation_id != spec.generation_id:
        raise IntegrityError("projection job generation identity does not match its manifest")
    if (
        job.manifest.provider_profile != spec.profile_id
        or job.manifest.version_id not in spec.source_version_ids
    ):
        raise IntegrityError("projection job scope/profile does not match its contract")
    return spec


@dataclass(frozen=True, slots=True, kw_only=True)
class VisionTextProjectionBuilder:
    store: DerivedProjectionStoreV1
    source_generation_ids: tuple[UUID, ...]

    async def build(self, generation_id: UUID) -> ProjectionBuildResult:
        return await self.store.build_vision_text_projection(
            generation_id=generation_id,
            source_generation_ids=self.source_generation_ids,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class LanguageTextProjectionBuilder:
    store: DerivedProjectionStoreV1
    source_generation_ids: tuple[UUID, ...]

    async def build(self, generation_id: UUID) -> ProjectionBuildResult:
        return await self.store.build_language_text_projection(
            generation_id=generation_id,
            source_generation_ids=self.source_generation_ids,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualVectorProjectionBuilder:
    store: DerivedProjectionStoreV1
    source_generation_ids: tuple[UUID, ...]

    async def build(self, generation_id: UUID) -> ProjectionBuildResult:
        return await self.store.build_multilingual_vector_projection(
            generation_id=generation_id,
            source_generation_ids=self.source_generation_ids,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class OCRTextProjectionBuilder:
    store: OCRStoreV1
    results: tuple[OCRResult, ...]

    async def build(self, generation_id: UUID) -> ProjectionBuildResult:
        projected: list[str] = []
        failed = 0
        for result in self.results:
            try:
                await self.store.project_ocr_result(generation_id=generation_id, result=result)
                regions = await self.store.list_ocr_projection_regions(
                    generation_id=generation_id,
                    derivation_id=result.derivation_id,
                )
                projected.append(
                    f"{result.derivation_id}:{','.join(str(item) for item in regions)}"
                )
            except Exception:
                failed += 1
        return ProjectionBuildResult(
            expected_count=len(self.results),
            succeeded_count=len(projected),
            failed_count=failed,
            skipped_count=0,
            checksum=_projection_checksum((item,) for item in sorted(projected)),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class VisualVectorProjectionBuilder:
    store: VisionStoreV1
    embeddings: tuple[VisualEmbedding, ...]

    async def build(self, generation_id: UUID) -> ProjectionBuildResult:
        succeeded = 0
        failed = 0
        for embedding in self.embeddings:
            try:
                await self.store.project_visual_embedding(
                    generation_id=generation_id, embedding=embedding
                )
                succeeded += 1
            except Exception:
                failed += 1
        derivations = await self.store.list_visual_projection_derivations(
            generation_id=generation_id
        )
        return ProjectionBuildResult(
            expected_count=len(self.embeddings),
            succeeded_count=succeeded,
            failed_count=failed,
            skipped_count=0,
            checksum=_projection_checksum((str(item),) for item in derivations),
        )


def projection_service_registration(
    *,
    capability_id: str,
    service: object,
    status: ProjectionStatus,
    profile_fingerprint: str | None = None,
) -> Phase85ServiceRegistration:
    """Map validated projection state to the WP-01 runtime without duplicating lifecycle."""
    from mnemo.phase85.runtime import Phase85ServiceRegistration

    eligible = status.active and status.eligible_for_activation
    return Phase85ServiceRegistration(
        capability_id=capability_id,
        service=service,
        ready=eligible,
        activate=eligible,
        generation_id=str(status.generation_id),
        generation_active=eligible,
        profile_fingerprint=profile_fingerprint,
    )


def _projection_checksum(rows: Iterable[Iterable[object]]) -> str:
    material = "\n".join("\x1f".join(str(value) for value in row) for row in rows)
    return hashlib.sha256(material.encode()).hexdigest()
