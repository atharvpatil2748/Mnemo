"""Governed Phase 8.5.5 vision-analysis and visual-embedding operations."""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid5

from mnemo.interfaces import (
    AssetCatalogStoreV1,
    ConflictError,
    IntegrityError,
    OperationCancelledError,
    ProcessingJobStoreV1,
    UnsupportedError,
)
from mnemo.interfaces.vision import (
    VisionAssetReaderV1,
    VisionCancellationCheck,
    VisionProviderV1,
    VisionStoreV1,
    VisualEmbeddingProviderV1,
)
from mnemo.models import (
    Asset,
    AssetDerivation,
    AssetDerivationStatus,
    FrozenMetadata,
    ProcessingBudget,
    ProcessingCheckpoint,
    ProcessingConsent,
    ProcessingCostStatus,
    ProcessingEstimate,
    ProcessingJob,
    ProcessingLedgerEntry,
    ProcessingManifest,
    ProcessingResult,
    ProcessingTrustClass,
    VisionCapability,
    VisionCompleteness,
    VisionProfile,
    VisionRequest,
    VisionResult,
    VisualDistanceMetric,
    VisualEmbedding,
    VisualEmbeddingCapability,
    VisualEmbeddingProfile,
    VisualEmbeddingRequest,
    VisualNormalization,
    thaw_metadata,
)

VISION_OPERATION = "vision_analysis"
VISUAL_EMBEDDING_OPERATION = "visual_embedding"
_RESULT_NAMESPACE = UUID("f571ee31-721a-5da4-9562-6dc69c1a8172")
_LEDGER_NAMESPACE = UUID("4e234c47-a74e-5633-93c0-bf8ff0963931")


def make_vision_processing_manifest(
    *,
    request: VisionRequest,
    trust: ProcessingTrustClass,
    consent: ProcessingConsent,
    estimate: ProcessingEstimate,
    budget: ProcessingBudget,
    max_retries: int,
) -> ProcessingManifest:
    profile = request.profile
    return ProcessingManifest(
        actor_id=request.actor_id,
        notebook_id=request.notebook_id,
        operation=VISION_OPERATION,
        occurrence_id=request.occurrence_id,
        document_id=request.document_id,
        version_id=request.version_id,
        provider_profile=profile.profile_id,
        provider_identity=profile.provider_identity,
        provider_trust=trust,
        model_identity=f"{profile.model_identity}@{profile.model_revision}",
        configuration=FrozenMetadata(
            {
                "vision": {
                    "asset_id": str(request.asset_id),
                    "asset_content_hash": request.asset_content_hash,
                    "media_type": request.media_type,
                    "profile_id": profile.profile_id,
                    "preprocessing": thaw_metadata(profile.preprocessing),
                    "analysis_schema_version": profile.analysis_schema_version,
                    "prompt_template_id": profile.prompt_template_id,
                    "prompt_hash": profile.prompt_hash,
                    "language_hints": list(profile.language_hints),
                    "max_pixels": profile.max_pixels,
                    "max_output_characters": profile.max_output_characters,
                    "max_observations": profile.max_observations,
                    "cache_key": request.cache_key,
                }
            }
        ),
        generation_id=profile.generation_id,
        language=profile.language_hints[0] if len(profile.language_hints) == 1 else None,
        output_schema=f"vision-result/v{profile.analysis_schema_version}",
        policy_version=consent.policy_version,
        consent=consent,
        estimate=estimate,
        budget=budget,
        max_retries=max_retries,
    )


def make_visual_embedding_processing_manifest(
    *,
    request: VisualEmbeddingRequest,
    trust: ProcessingTrustClass,
    consent: ProcessingConsent,
    estimate: ProcessingEstimate,
    budget: ProcessingBudget,
    max_retries: int,
) -> ProcessingManifest:
    profile = request.profile
    return ProcessingManifest(
        actor_id=request.actor_id,
        notebook_id=request.notebook_id,
        operation=VISUAL_EMBEDDING_OPERATION,
        occurrence_id=request.occurrence_id,
        document_id=request.document_id,
        version_id=request.version_id,
        provider_profile=profile.profile_id,
        provider_identity=profile.provider_identity,
        provider_trust=trust,
        model_identity=f"{profile.model_identity}@{profile.model_revision}",
        configuration=FrozenMetadata(
            {
                "visual_embedding": {
                    "asset_id": str(request.asset_id),
                    "asset_content_hash": request.asset_content_hash,
                    "media_type": request.media_type,
                    "profile_id": profile.profile_id,
                    "preprocessing": thaw_metadata(profile.preprocessing),
                    "dimensions": profile.dimensions,
                    "metric": profile.metric.value,
                    "normalization": profile.normalization.value,
                    "shared_space_id": profile.shared_space_id,
                    "source_vision_derivation_id": (
                        None
                        if request.source_vision_derivation_id is None
                        else str(request.source_vision_derivation_id)
                    ),
                    "cache_key": request.cache_key,
                }
            }
        ),
        generation_id=profile.generation_id,
        language=None,
        output_schema="visual-embedding/v1",
        policy_version=consent.policy_version,
        consent=consent,
        estimate=estimate,
        budget=budget,
        max_retries=max_retries,
    )


class VisionProcessingOperation:
    def __init__(
        self,
        *,
        catalog: AssetCatalogStoreV1,
        vision_store: VisionStoreV1,
        job_store: ProcessingJobStoreV1,
        asset_reader: VisionAssetReaderV1,
        providers: dict[str, VisionProviderV1],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not isinstance(catalog, AssetCatalogStoreV1):
            raise TypeError("catalog must implement AssetCatalogStoreV1")
        if not isinstance(vision_store, VisionStoreV1):
            raise TypeError("vision_store must implement VisionStoreV1")
        if not isinstance(job_store, ProcessingJobStoreV1):
            raise TypeError("job_store must implement ProcessingJobStoreV1")
        if not isinstance(asset_reader, VisionAssetReaderV1):
            raise TypeError("asset_reader must implement VisionAssetReaderV1")
        self._catalog = catalog
        self._store = vision_store
        self._jobs = job_store
        self._reader = asset_reader
        self._providers = dict(providers)
        self._clock = clock

    async def __call__(
        self,
        job: ProcessingJob,
        _checkpoint: ProcessingCheckpoint | None,
        cancelled: VisionCancellationCheck,
    ) -> ProcessingResult:
        request = _vision_request_from_job(job)
        asset = await _authorized_asset(self._catalog, request, job)
        cached = await self._store.get_authorized_vision_result_by_cache_key(
            notebook_id=request.notebook_id, cache_key=request.cache_key
        )
        if cached is not None:
            _raise_nonpublishable_vision(cached)
            return await _processing_result(
                jobs=self._jobs,
                job=job,
                derivation_id=cached.derivation_id,
                content_hash=cached.content_hash,
                kind=VISION_OPERATION,
                cache_hit=True,
                usage={
                    "completeness": cached.completeness.value,
                    "captions": len(cached.captions),
                    "entities": len(cached.entities),
                    "regions": len(cached.regions),
                    "relations": len(cached.relations),
                },
                clock=self._clock,
            )
        provider = self._providers.get(request.profile.provider_identity)
        if provider is None or provider.provider_identity != request.profile.provider_identity:
            raise UnsupportedError("configured vision provider is unavailable")
        capability = await provider.capabilities()
        _validate_input_capability(
            request,
            asset,
            capability.supported_media_types,
            capability.max_width,
            capability.max_height,
            min(request.profile.max_pixels, capability.max_pixels),
        )
        if capability.supported_languages and set(request.profile.language_hints).difference(
            capability.supported_languages
        ):
            raise UnsupportedError("vision provider does not support requested languages")
        raw = await _authorized_bytes(
            self._reader, request.asset_id, request.asset_content_hash, job
        )
        await _ensure_derivation(
            self._catalog,
            request.derivation_id,
            request.occurrence_id,
            VISION_OPERATION,
            request.profile.provider_identity,
            f"{request.profile.model_identity}@{request.profile.model_revision}",
            request.cache_key,
            self._clock(),
        )
        if await cancelled():
            await _cancel_derivation(self._catalog, request.derivation_id)
            raise OperationCancelledError("vision analysis cancelled before provider execution")
        started = time.perf_counter()
        try:
            call = provider.analyze(request, raw, cancelled)
            result = (
                await call
                if job.manifest.budget.max_wall_seconds is None
                else await asyncio.wait_for(call, timeout=job.manifest.budget.max_wall_seconds)
            )
        except asyncio.CancelledError as error:
            await _cancel_derivation(self._catalog, request.derivation_id)
            raise OperationCancelledError("vision provider cancelled") from error
        except OperationCancelledError:
            await _cancel_derivation(self._catalog, request.derivation_id)
            raise
        _validate_vision_result(request, result, capability)
        if await cancelled():
            await _cancel_derivation(self._catalog, request.derivation_id)
            raise OperationCancelledError("vision analysis cancelled before publication")
        await self._store.put_vision_result(result)
        _raise_nonpublishable_vision(result)
        return await _processing_result(
            jobs=self._jobs,
            job=job,
            derivation_id=result.derivation_id,
            content_hash=result.content_hash,
            kind=VISION_OPERATION,
            cache_hit=False,
            usage={
                "completeness": result.completeness.value,
                "captions": len(result.captions),
                "entities": len(result.entities),
                "regions": len(result.regions),
                "relations": len(result.relations),
                "provider_wall_milliseconds": int((time.perf_counter() - started) * 1000),
            },
            clock=self._clock,
        )


class VisualEmbeddingProcessingOperation:
    def __init__(
        self,
        *,
        catalog: AssetCatalogStoreV1,
        vision_store: VisionStoreV1,
        job_store: ProcessingJobStoreV1,
        asset_reader: VisionAssetReaderV1,
        providers: dict[str, VisualEmbeddingProviderV1],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not isinstance(catalog, AssetCatalogStoreV1):
            raise TypeError("catalog must implement AssetCatalogStoreV1")
        if not isinstance(vision_store, VisionStoreV1):
            raise TypeError("vision_store must implement VisionStoreV1")
        if not isinstance(job_store, ProcessingJobStoreV1):
            raise TypeError("job_store must implement ProcessingJobStoreV1")
        if not isinstance(asset_reader, VisionAssetReaderV1):
            raise TypeError("asset_reader must implement VisionAssetReaderV1")
        self._catalog = catalog
        self._store = vision_store
        self._jobs = job_store
        self._reader = asset_reader
        self._providers = dict(providers)
        self._clock = clock

    async def __call__(
        self,
        job: ProcessingJob,
        _checkpoint: ProcessingCheckpoint | None,
        cancelled: VisionCancellationCheck,
    ) -> ProcessingResult:
        request = _embedding_request_from_job(job)
        asset = await _authorized_asset(self._catalog, request, job)
        cached = await self._store.get_authorized_visual_embedding_by_cache_key(
            notebook_id=request.notebook_id, cache_key=request.cache_key
        )
        if cached is not None:
            return await _processing_result(
                jobs=self._jobs,
                job=job,
                derivation_id=cached.derivation_id,
                content_hash=cached.vector_hash,
                kind=VISUAL_EMBEDDING_OPERATION,
                cache_hit=True,
                usage={
                    "dimensions": cached.dimensions,
                    "metric": cached.metric.value,
                    "normalization": cached.normalization.value,
                    "generation_id": str(cached.generation_id),
                },
                clock=self._clock,
            )
        provider = self._providers.get(request.profile.provider_identity)
        if provider is None or provider.provider_identity != request.profile.provider_identity:
            raise UnsupportedError("configured visual embedding provider is unavailable")
        capability = await provider.capabilities()
        _validate_input_capability(
            request,
            asset,
            capability.supported_media_types,
            capability.max_width,
            capability.max_height,
            capability.max_pixels,
        )
        if (
            request.profile.dimensions != capability.dimensions
            or request.profile.metric != capability.metric
            or request.profile.normalization != capability.normalization
            or request.profile.shared_space_id != capability.shared_space_id
        ):
            raise IntegrityError("visual embedding profile does not match provider space")
        raw = await _authorized_bytes(
            self._reader, request.asset_id, request.asset_content_hash, job
        )
        if len(raw) > capability.max_bytes:
            raise IntegrityError("visual embedding input exceeds provider byte limit")
        await _ensure_derivation(
            self._catalog,
            request.derivation_id,
            request.occurrence_id,
            VISUAL_EMBEDDING_OPERATION,
            request.profile.provider_identity,
            f"{request.profile.model_identity}@{request.profile.model_revision}",
            request.cache_key,
            self._clock(),
        )
        if await cancelled():
            await _cancel_derivation(self._catalog, request.derivation_id)
            raise OperationCancelledError("visual embedding cancelled before provider execution")
        started = time.perf_counter()
        try:
            call = provider.embed_image(request, raw, cancelled)
            embedding = (
                await call
                if job.manifest.budget.max_wall_seconds is None
                else await asyncio.wait_for(call, timeout=job.manifest.budget.max_wall_seconds)
            )
        except asyncio.CancelledError as error:
            await _cancel_derivation(self._catalog, request.derivation_id)
            raise OperationCancelledError("visual embedding provider cancelled") from error
        except OperationCancelledError:
            await _cancel_derivation(self._catalog, request.derivation_id)
            raise
        _validate_embedding_result(request, embedding, capability)
        if await cancelled():
            await _cancel_derivation(self._catalog, request.derivation_id)
            raise OperationCancelledError("visual embedding cancelled before publication")
        await self._store.put_visual_embedding(embedding)
        return await _processing_result(
            jobs=self._jobs,
            job=job,
            derivation_id=embedding.derivation_id,
            content_hash=embedding.vector_hash,
            kind=VISUAL_EMBEDDING_OPERATION,
            cache_hit=False,
            usage={
                "dimensions": embedding.dimensions,
                "metric": embedding.metric.value,
                "normalization": embedding.normalization.value,
                "generation_id": str(embedding.generation_id),
                "provider_wall_milliseconds": int((time.perf_counter() - started) * 1000),
            },
            clock=self._clock,
        )


async def _authorized_asset(
    catalog: AssetCatalogStoreV1,
    request: VisionRequest | VisualEmbeddingRequest,
    job: ProcessingJob,
) -> Asset:
    occurrence = await catalog.get_authorized_asset_occurrence(
        notebook_id=job.manifest.notebook_id, occurrence_id=request.occurrence_id
    )
    if occurrence is None:
        raise IntegrityError("visual occurrence is unavailable in the authorized scope")
    if (
        occurrence.asset_id != request.asset_id
        or occurrence.document_id != request.document_id
        or occurrence.version_id != request.version_id
    ):
        raise IntegrityError("visual occurrence provenance changed")
    asset = await catalog.get_asset_record(request.asset_id)
    if (
        asset is None
        or asset.content_hash != request.asset_content_hash
        or asset.mime_type != request.media_type
    ):
        raise IntegrityError("visual asset identity is unavailable or changed")
    if request.media_type == "image/svg+xml":
        raise UnsupportedError("active SVG input is unavailable to vision providers")
    return asset


async def _authorized_bytes(
    reader: VisionAssetReaderV1, asset_id: UUID, content_hash: str, job: ProcessingJob
) -> bytes:
    raw = await reader.get_asset(asset_id)
    if raw is None or hashlib.sha256(raw).hexdigest() != content_hash:
        raise IntegrityError("visual source bytes are unavailable or fail hash verification")
    if job.manifest.budget.max_bytes is not None and len(raw) > job.manifest.budget.max_bytes:
        raise IntegrityError("visual source bytes exceed the governed byte limit")
    return raw


def _validate_input_capability(
    request: VisionRequest | VisualEmbeddingRequest,
    asset: Asset,
    media_types: tuple[str, ...],
    max_width: int,
    max_height: int,
    max_pixels: int,
) -> None:
    if media_types and request.media_type not in media_types:
        raise UnsupportedError("provider does not support the visual media type")
    if (
        asset.width is not None
        and asset.height is not None
        and (
            asset.width > max_width
            or asset.height > max_height
            or asset.width * asset.height > max_pixels
        )
    ):
        raise IntegrityError("visual input exceeds provider dimension or pixel limits")


async def _ensure_derivation(
    catalog: AssetCatalogStoreV1,
    derivation_id: UUID,
    occurrence_id: UUID,
    operation: str,
    provider_identity: str,
    model_identity: str,
    cache_key: str,
    now: datetime,
) -> None:
    created = await catalog.create_asset_derivation(
        AssetDerivation(
            derivation_id=derivation_id,
            occurrence_id=occurrence_id,
            operation=operation,
            provider_identity=provider_identity,
            model_identity=model_identity,
            configuration_digest=cache_key,
            output_asset_id=None,
            output_payload=FrozenMetadata(),
            status=AssetDerivationStatus.PENDING,
            confidence=None,
            language=None,
            created_at=now,
            updated_at=now,
        )
    )
    if not created:
        existing = await catalog.get_asset_derivation(derivation_id)
        if existing is None or existing.configuration_digest != cache_key:
            raise ConflictError("derived visual identity conflicts")
        if existing.status in {AssetDerivationStatus.FAILED, AssetDerivationStatus.CANCELLED}:
            raise ConflictError("terminal visual derivation cannot be resumed")
        if existing.status is AssetDerivationStatus.SUCCEEDED:
            raise IntegrityError("successful visual derivation has no authorized cached result")
        if existing.status is AssetDerivationStatus.RUNNING:
            return
    if not await catalog.transition_asset_derivation(
        derivation_id, AssetDerivationStatus.PENDING, AssetDerivationStatus.RUNNING
    ):
        raise ConflictError("visual derivation could not enter running state")


async def _cancel_derivation(catalog: AssetCatalogStoreV1, derivation_id: UUID) -> None:
    derivation = await catalog.get_asset_derivation(derivation_id)
    if derivation is not None and derivation.status is AssetDerivationStatus.RUNNING:
        await catalog.transition_asset_derivation(
            derivation_id, AssetDerivationStatus.RUNNING, AssetDerivationStatus.CANCELLED
        )


async def _processing_result(
    *,
    jobs: ProcessingJobStoreV1,
    job: ProcessingJob,
    derivation_id: UUID,
    content_hash: str,
    kind: str,
    cache_hit: bool,
    usage: dict[str, object],
    clock: Callable[[], datetime],
) -> ProcessingResult:
    attempts = await jobs.list_processing_attempts(
        actor_id=job.manifest.actor_id, notebook_id=job.manifest.notebook_id, job_id=job.job_id
    )
    if not attempts or job.lease_token is None:
        raise IntegrityError("visual job has no active attempt provenance")
    attempt, now = attempts[-1], clock()
    safe_usage = {**usage, "cache_hit": cache_hit, "attempt_number": attempt.attempt_number}
    await jobs.append_processing_ledger(
        ProcessingLedgerEntry(
            entry_id=uuid5(_LEDGER_NAMESPACE, f"{job.job_id}:{attempt.attempt_id}:{kind}"),
            job_id=job.job_id,
            attempt_id=attempt.attempt_id,
            status=ProcessingCostStatus.ACTUAL,
            provider_identity=job.manifest.provider_identity,
            model_identity=job.manifest.model_identity,
            usage=FrozenMetadata(safe_usage),
            created_at=now,
        ),
        lease_token=job.lease_token,
    )
    return ProcessingResult(
        result_id=uuid5(_RESULT_NAMESPACE, f"{job.job_id}:{derivation_id}"),
        job_id=job.job_id,
        attempt_id=attempt.attempt_id,
        fingerprint=job.fingerprint,
        output_reference=f"{kind}-derivation:{derivation_id}",
        payload=FrozenMetadata(
            {
                "derivation_id": str(derivation_id),
                "content_hash": content_hash,
                "cache_hit": cache_hit,
                "evidence_kind": "derived_visual",
            }
        ),
        created_at=now,
    )


def _vision_request_from_job(job: ProcessingJob) -> VisionRequest:
    if job.manifest.operation != VISION_OPERATION or job.manifest.generation_id is None:
        raise IntegrityError("processing job is not a versioned vision operation")
    raw = thaw_metadata(job.manifest.configuration).get("vision")
    if not isinstance(raw, dict):
        raise IntegrityError("vision job manifest configuration is unavailable")
    model, separator, revision = job.manifest.model_identity.rpartition("@")
    if not separator:
        raise IntegrityError("vision model revision is missing")
    try:
        languages = raw["language_hints"]
        if not isinstance(languages, list) or any(
            not isinstance(value, str) for value in languages
        ):
            raise TypeError
        request = VisionRequest(
            actor_id=job.manifest.actor_id,
            notebook_id=job.manifest.notebook_id,
            document_id=job.manifest.document_id,
            version_id=job.manifest.version_id,
            occurrence_id=job.manifest.occurrence_id,
            asset_id=UUID(str(raw["asset_id"])),
            asset_content_hash=str(raw["asset_content_hash"]),
            media_type=str(raw["media_type"]),
            profile=VisionProfile(
                profile_id=str(raw["profile_id"]),
                provider_identity=job.manifest.provider_identity,
                model_identity=model,
                model_revision=revision,
                preprocessing=FrozenMetadata(cast(dict[str, object], raw["preprocessing"])),
                analysis_schema_version=_required_int(raw["analysis_schema_version"]),
                prompt_template_id=str(raw["prompt_template_id"]),
                prompt_hash=str(raw["prompt_hash"]),
                language_hints=tuple(cast(list[str], languages)),
                max_pixels=_required_int(raw["max_pixels"]),
                max_output_characters=_required_int(raw["max_output_characters"]),
                max_observations=_required_int(raw["max_observations"]),
                generation_id=job.manifest.generation_id,
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise IntegrityError("vision job manifest fields are malformed") from error
    if raw.get("cache_key") != request.cache_key:
        raise IntegrityError("vision job cache identity does not match its manifest")
    return request


def _embedding_request_from_job(job: ProcessingJob) -> VisualEmbeddingRequest:
    if job.manifest.operation != VISUAL_EMBEDDING_OPERATION or job.manifest.generation_id is None:
        raise IntegrityError("processing job is not a versioned visual embedding operation")
    raw = thaw_metadata(job.manifest.configuration).get("visual_embedding")
    if not isinstance(raw, dict):
        raise IntegrityError("visual embedding manifest configuration is unavailable")
    model, separator, revision = job.manifest.model_identity.rpartition("@")
    if not separator:
        raise IntegrityError("visual embedding model revision is missing")
    try:
        request = VisualEmbeddingRequest(
            actor_id=job.manifest.actor_id,
            notebook_id=job.manifest.notebook_id,
            document_id=job.manifest.document_id,
            version_id=job.manifest.version_id,
            occurrence_id=job.manifest.occurrence_id,
            asset_id=UUID(str(raw["asset_id"])),
            asset_content_hash=str(raw["asset_content_hash"]),
            media_type=str(raw["media_type"]),
            source_vision_derivation_id=None
            if raw["source_vision_derivation_id"] is None
            else UUID(str(raw["source_vision_derivation_id"])),
            profile=VisualEmbeddingProfile(
                profile_id=str(raw["profile_id"]),
                provider_identity=job.manifest.provider_identity,
                model_identity=model,
                model_revision=revision,
                preprocessing=FrozenMetadata(cast(dict[str, object], raw["preprocessing"])),
                dimensions=_required_int(raw["dimensions"]),
                metric=VisualDistanceMetric(str(raw["metric"])),
                normalization=VisualNormalization(str(raw["normalization"])),
                shared_space_id=None
                if raw["shared_space_id"] is None
                else str(raw["shared_space_id"]),
                generation_id=job.manifest.generation_id,
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise IntegrityError("visual embedding manifest fields are malformed") from error
    if raw.get("cache_key") != request.cache_key:
        raise IntegrityError("visual embedding cache identity does not match its manifest")
    return request


def _validate_vision_result(
    request: VisionRequest, result: VisionResult, capability: VisionCapability
) -> None:
    if not isinstance(result, VisionResult):
        raise IntegrityError("vision provider returned an invalid result type")
    if (
        result.derivation_id,
        result.cache_key,
        result.document_id,
        result.version_id,
        result.occurrence_id,
        result.asset_id,
        result.generation_id,
        result.preprocessing_digest,
    ) != (
        request.derivation_id,
        request.cache_key,
        request.document_id,
        request.version_id,
        request.occurrence_id,
        request.asset_id,
        request.profile.generation_id,
        request.profile.preprocessing_digest,
    ):
        raise IntegrityError("vision provider result provenance does not match its request")
    if (
        result.provider.capability != capability
        or result.provider.provider_identity != request.profile.provider_identity
        or result.provider.model_identity != request.profile.model_identity
        or result.provider.model_revision != request.profile.model_revision
    ):
        raise IntegrityError("vision provider metadata does not match its profile")
    if (
        len(result.captions) > capability.max_captions
        or len(result.entities) > capability.max_entities
        or len(result.regions) > capability.max_regions
        or len(result.relations) > capability.max_relations
        or len(result.observations) > request.profile.max_observations
    ):
        raise IntegrityError("vision provider result exceeds structured output limits")
    characters = (
        sum(len(value.text) for value in result.captions)
        + sum(len(value.value) for value in result.observations)
        + sum(len(value.label) for value in result.entities)
    )
    response_bytes = sum(len(value.text.encode("utf-8")) for value in result.captions) + sum(
        len(value.encode("utf-8"))
        for value in (
            *(item.value for item in result.observations),
            *(item.label for item in result.entities),
        )
    )
    if (
        characters > request.profile.max_output_characters
        or response_bytes > capability.max_response_bytes
    ):
        raise IntegrityError("vision provider result exceeds output size limit")
    if not capability.geometry and any(value.bounding_box is not None for value in result.regions):
        raise IntegrityError("vision provider returned unsupported geometry")
    if not capability.confidence and (
        any(value.confidence.value is not None for value in result.captions)
        or any(value.confidence.value is not None for value in result.observations)
        or any(value.confidence.value is not None for value in result.entities)
        or any(value.confidence.value is not None for value in result.relations)
    ):
        raise IntegrityError("vision provider returned unsupported confidence")


def _validate_embedding_result(
    request: VisualEmbeddingRequest,
    result: VisualEmbedding,
    capability: VisualEmbeddingCapability,
) -> None:
    if not isinstance(result, VisualEmbedding):
        raise IntegrityError("visual embedding provider returned an invalid result type")
    if (
        result.derivation_id,
        result.cache_key,
        result.document_id,
        result.version_id,
        result.occurrence_id,
        result.asset_id,
        result.generation_id,
        result.source_vision_derivation_id,
        result.preprocessing_digest,
    ) != (
        request.derivation_id,
        request.cache_key,
        request.document_id,
        request.version_id,
        request.occurrence_id,
        request.asset_id,
        request.profile.generation_id,
        request.source_vision_derivation_id,
        request.profile.preprocessing_digest,
    ):
        raise IntegrityError("visual embedding provenance does not match its request")
    if (
        result.provider.capability != capability
        or result.provider.provider_identity != request.profile.provider_identity
        or result.provider.model_identity != request.profile.model_identity
        or result.provider.model_revision != request.profile.model_revision
    ):
        raise IntegrityError("visual embedding provider metadata does not match its profile")


def _raise_nonpublishable_vision(result: VisionResult) -> None:
    if result.completeness is VisionCompleteness.UNAVAILABLE:
        raise UnsupportedError("vision provider reported the input unavailable")
    if result.completeness is VisionCompleteness.FAILED:
        raise IntegrityError("vision provider reported a failed result")


def _required_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("manifest integer field is malformed")
    return value
