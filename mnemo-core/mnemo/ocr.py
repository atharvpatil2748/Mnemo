"""OCR detection, governed job construction, and provider orchestration."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid5

from mnemo.interfaces import (
    AssetCatalogStoreV1,
    ConflictError,
    IntegrityError,
    OCRAssetReaderV1,
    OCRCancellationCheck,
    OCRProviderV1,
    OCRStoreV1,
    OperationCancelledError,
    ProcessingJobStoreV1,
    UnsupportedError,
)
from mnemo.models import (
    AssetDerivation,
    AssetDerivationStatus,
    FrozenMetadata,
    OCRCapability,
    OCRCompleteness,
    OCRDocumentDetection,
    OCRDocumentScanStatus,
    OCRPageDetection,
    OCRPageKind,
    OCRPageSignal,
    OCRProfile,
    OCRRequest,
    OCRResult,
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
    thaw_metadata,
)

_LOGGER = logging.getLogger(__name__)
OCR_OPERATION = "ocr"
OCR_DETECTOR_VERSION = "ocr-page-detector/v1"
_PROCESSING_RESULT_NAMESPACE = UUID("7a7de1cd-b137-5b6f-8559-6f664772bf64")
_LEDGER_NAMESPACE = UUID("804f9870-44c8-558c-85f4-00de6b7c89dc")


@dataclass(frozen=True, slots=True, kw_only=True)
class OCRDetectorProfile:
    minimum_native_text_characters: int = 32
    scanned_raster_coverage: float = 0.5
    document_scan_ratio: float = 0.8
    detector_version: str = OCR_DETECTOR_VERSION

    def __post_init__(self) -> None:
        if self.minimum_native_text_characters < 1:
            raise ValueError("minimum_native_text_characters must be positive")
        for name in ("scanned_raster_coverage", "document_scan_ratio"):
            value = getattr(self, name)
            if isinstance(value, bool) or not 0 < value <= 1:
                raise ValueError(f"{name} must be within (0, 1]")
        if not self.detector_version.strip():
            raise ValueError("detector_version must not be empty")


_DEFAULT_PROFILE = OCRDetectorProfile()


def detect_ocr_pages(
    signals: tuple[OCRPageSignal, ...],
    profile: OCRDetectorProfile = _DEFAULT_PROFILE,
) -> OCRDocumentDetection:
    """Classify explainable page signals without asserting text absence."""
    pages = tuple(_detect_page(signal, profile) for signal in signals)
    if not pages:
        status = OCRDocumentScanStatus.UNKNOWN
    elif any(signal.malformed for signal in signals):
        status = OCRDocumentScanStatus.DETECTION_FAILED
    else:
        meaningful = tuple(page for page in pages if page.kind is not OCRPageKind.BLANK)
        scanned = sum(page.kind is OCRPageKind.IMAGE_ONLY for page in meaningful)
        native = sum(page.kind is OCRPageKind.TEXT_NATIVE for page in meaningful)
        mixed = sum(page.kind is OCRPageKind.MIXED for page in meaningful)
        if meaningful and scanned / len(meaningful) >= profile.document_scan_ratio:
            status = OCRDocumentScanStatus.SCAN_LIKELY
        elif mixed or (scanned and native):
            status = OCRDocumentScanStatus.MIXED
        elif meaningful and native == len(meaningful):
            status = OCRDocumentScanStatus.DIGITAL
        else:
            status = OCRDocumentScanStatus.UNKNOWN
    return OCRDocumentDetection(
        status=status, pages=pages, detector_version=profile.detector_version
    )


def _detect_page(signal: OCRPageSignal, profile: OCRDetectorProfile) -> OCRPageDetection:
    if not signal.supported:
        kind, reason = OCRPageKind.UNSUPPORTED, "unsupported_page_representation"
    elif signal.malformed:
        kind, reason = OCRPageKind.UNKNOWN, "malformed_page_signal"
    elif (
        signal.normalized_text_characters == 0
        and (signal.raster_coverage in {None, 0.0})
        and not signal.dominant_page_image
    ):
        kind, reason = OCRPageKind.BLANK, "no_text_or_raster_evidence"
    else:
        raster_heavy = (
            signal.raster_coverage is not None
            and signal.raster_coverage >= profile.scanned_raster_coverage
        ) or signal.dominant_page_image
        usable_text = (
            signal.reliable_vector_text
            or signal.normalized_text_characters >= profile.minimum_native_text_characters
        )
        if raster_heavy and not usable_text:
            kind, reason = OCRPageKind.IMAGE_ONLY, "dominant_raster_without_reliable_text"
        elif raster_heavy and usable_text:
            kind, reason = OCRPageKind.MIXED, "raster_and_reliable_text"
        elif usable_text:
            kind, reason = OCRPageKind.TEXT_NATIVE, "reliable_text_layer"
        else:
            kind, reason = OCRPageKind.UNKNOWN, "insufficient_scan_evidence"
    return OCRPageDetection(
        page_number=signal.page_number,
        kind=kind,
        reason_code=reason,
        detector_version=profile.detector_version,
    )


def make_ocr_processing_manifest(
    *,
    request: OCRRequest,
    trust: ProcessingTrustClass,
    consent: ProcessingConsent,
    estimate: ProcessingEstimate,
    budget: ProcessingBudget,
    max_retries: int,
) -> ProcessingManifest:
    """Bind one deterministic OCR request into the ADR-0060 manifest."""
    profile = request.profile
    return ProcessingManifest(
        actor_id=request.actor_id,
        notebook_id=request.notebook_id,
        operation=OCR_OPERATION,
        occurrence_id=request.occurrence_id,
        document_id=request.document_id,
        version_id=request.version_id,
        provider_profile=profile.profile_id,
        provider_identity=profile.provider_identity,
        provider_trust=trust,
        model_identity=f"{profile.model_identity}@{profile.model_revision}",
        configuration=FrozenMetadata(
            {
                "ocr": {
                    "asset_id": str(request.asset_id),
                    "asset_content_hash": request.asset_content_hash,
                    "media_type": request.media_type,
                    "profile_id": profile.profile_id,
                    "model_revision": profile.model_revision,
                    "preprocessing": thaw_metadata(profile.preprocessing),
                    "language_hints": list(profile.language_hints),
                    "max_pages": profile.max_pages,
                    "max_pixels": profile.max_pixels,
                    "max_output_characters": profile.max_output_characters,
                    "page_numbers": list(request.page_numbers),
                    "cache_key": request.cache_key,
                }
            }
        ),
        generation_id=profile.generation_id,
        language=profile.language_hints[0] if len(profile.language_hints) == 1 else None,
        output_schema="ocr-result/v1",
        policy_version=consent.policy_version,
        consent=consent,
        estimate=estimate,
        budget=budget,
        max_retries=max_retries,
    )


class OCRProcessingOperation:
    """One governed OCR operation suitable for `ProcessingWorker`."""

    def __init__(
        self,
        *,
        catalog: AssetCatalogStoreV1,
        ocr_store: OCRStoreV1,
        job_store: ProcessingJobStoreV1,
        asset_reader: OCRAssetReaderV1,
        providers: dict[str, OCRProviderV1],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not isinstance(catalog, AssetCatalogStoreV1):
            raise TypeError("catalog must implement AssetCatalogStoreV1")
        if not isinstance(ocr_store, OCRStoreV1):
            raise TypeError("ocr_store must implement OCRStoreV1")
        if not isinstance(job_store, ProcessingJobStoreV1):
            raise TypeError("job_store must implement ProcessingJobStoreV1")
        if not isinstance(asset_reader, OCRAssetReaderV1):
            raise TypeError("asset_reader must implement OCRAssetReaderV1")
        self._catalog = catalog
        self._ocr_store = ocr_store
        self._job_store = job_store
        self._asset_reader = asset_reader
        self._providers = dict(providers)
        self._clock = clock

    async def __call__(
        self,
        job: ProcessingJob,
        _checkpoint: ProcessingCheckpoint | None,
        cancelled: OCRCancellationCheck,
    ) -> ProcessingResult:
        request = _request_from_job(job)
        occurrence = await self._catalog.get_authorized_asset_occurrence(
            notebook_id=job.manifest.notebook_id,
            occurrence_id=request.occurrence_id,
        )
        if occurrence is None:
            raise IntegrityError("OCR occurrence is unavailable in the authorized scope")
        if (
            occurrence.asset_id != request.asset_id
            or occurrence.document_id != request.document_id
            or occurrence.version_id != request.version_id
        ):
            raise IntegrityError("OCR occurrence provenance changed")
        asset = await self._catalog.get_asset_record(request.asset_id)
        if (
            asset is None
            or asset.content_hash != request.asset_content_hash
            or asset.mime_type != request.media_type
        ):
            raise IntegrityError("OCR asset identity is unavailable or changed")
        cached = await self._ocr_store.get_authorized_ocr_result_by_cache_key(
            notebook_id=request.notebook_id, cache_key=request.cache_key
        )
        if cached is not None:
            _raise_nonpublishable(cached)
            return await self._processing_result(job, cached, cache_hit=True)
        if request.media_type == "image/svg+xml":
            raise UnsupportedError("active SVG input is unavailable to OCR providers")
        provider = self._providers.get(request.profile.provider_identity)
        if provider is None or provider.provider_identity != request.profile.provider_identity:
            raise UnsupportedError("configured OCR provider is unavailable")
        capability = await provider.capabilities()
        if (
            capability.supported_media_types
            and request.media_type not in capability.supported_media_types
        ):
            raise UnsupportedError("OCR provider does not support the asset media type")
        unsupported_languages = set(request.profile.language_hints).difference(
            capability.supported_languages
        )
        if capability.supported_languages and unsupported_languages:
            raise UnsupportedError("OCR provider does not support requested languages")
        if request.page_numbers and len(request.page_numbers) > capability.max_pages:
            raise IntegrityError("OCR request exceeds provider page capability")
        if asset.width is not None and asset.height is not None:
            pixels = asset.width * asset.height
            if pixels > min(request.profile.max_pixels, capability.max_pixels):
                raise IntegrityError("OCR input exceeds decoded-pixel limit")
        raw = await self._asset_reader.get_asset(request.asset_id)
        if raw is None or hashlib.sha256(raw).hexdigest() != request.asset_content_hash:
            raise IntegrityError("OCR source bytes are unavailable or fail hash verification")
        if job.manifest.budget.max_bytes is not None and len(raw) > job.manifest.budget.max_bytes:
            raise IntegrityError("OCR source bytes exceed the governed byte limit")
        await self._ensure_derivation(job, request)
        if await cancelled():
            await self._cancel_derivation(request)
            raise OperationCancelledError("OCR cancelled before provider execution")
        started = time.perf_counter()
        try:
            provider_call = provider.recognize(request, raw, cancelled)
            if job.manifest.budget.max_wall_seconds is None:
                result = await provider_call
            else:
                result = await asyncio.wait_for(
                    provider_call, timeout=job.manifest.budget.max_wall_seconds
                )
        except OperationCancelledError:
            await self._cancel_derivation(request)
            raise
        except asyncio.CancelledError as error:
            await self._cancel_derivation(request)
            raise OperationCancelledError("OCR provider cancelled") from error
        _validate_provider_result(request, result, capability)
        if (
            sum(len(region.text) for region in result.regions)
            > request.profile.max_output_characters
        ):
            raise IntegrityError("OCR output exceeds the configured character limit")
        if await cancelled():
            await self._cancel_derivation(request)
            raise OperationCancelledError("OCR cancelled before derivation publication")
        await self._ocr_store.put_ocr_result(result)
        _raise_nonpublishable(result)
        return await self._processing_result(
            job,
            result,
            cache_hit=False,
            provider_wall_milliseconds=int((time.perf_counter() - started) * 1000),
        )

    async def _ensure_derivation(self, job: ProcessingJob, request: OCRRequest) -> None:
        now = self._clock()
        created = await self._catalog.create_asset_derivation(
            AssetDerivation(
                derivation_id=request.derivation_id,
                occurrence_id=request.occurrence_id,
                operation=OCR_OPERATION,
                provider_identity=request.profile.provider_identity,
                model_identity=f"{request.profile.model_identity}@{request.profile.model_revision}",
                configuration_digest=request.cache_key,
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
            existing = await self._catalog.get_asset_derivation(request.derivation_id)
            if existing is None or existing.configuration_digest != request.cache_key:
                raise ConflictError("OCR derivation identity conflicts")
            if existing.status in {AssetDerivationStatus.FAILED, AssetDerivationStatus.CANCELLED}:
                raise ConflictError("terminal OCR derivation cannot be resumed")
            if existing.status is AssetDerivationStatus.SUCCEEDED:
                raise IntegrityError("successful OCR derivation has no authorized cached result")
            if existing.status is AssetDerivationStatus.RUNNING:
                return
        transitioned = await self._catalog.transition_asset_derivation(
            request.derivation_id,
            AssetDerivationStatus.PENDING,
            AssetDerivationStatus.RUNNING,
        )
        if not transitioned:
            raise ConflictError("OCR derivation could not enter running state")

    async def _cancel_derivation(self, request: OCRRequest) -> None:
        derivation = await self._catalog.get_asset_derivation(request.derivation_id)
        if derivation is not None and derivation.status is AssetDerivationStatus.RUNNING:
            await self._catalog.transition_asset_derivation(
                request.derivation_id,
                AssetDerivationStatus.RUNNING,
                AssetDerivationStatus.CANCELLED,
            )

    async def _processing_result(
        self,
        job: ProcessingJob,
        result: OCRResult,
        *,
        cache_hit: bool,
        provider_wall_milliseconds: int = 0,
    ) -> ProcessingResult:
        attempts = await self._job_store.list_processing_attempts(
            actor_id=job.manifest.actor_id,
            notebook_id=job.manifest.notebook_id,
            job_id=job.job_id,
        )
        if not attempts or job.lease_token is None:
            raise IntegrityError("OCR job has no active attempt provenance")
        attempt = attempts[-1]
        now = self._clock()
        entry_id = uuid5(_LEDGER_NAMESPACE, f"{job.job_id}:{attempt.attempt_id}:ocr")
        await self._job_store.append_processing_ledger(
            ProcessingLedgerEntry(
                entry_id=entry_id,
                job_id=job.job_id,
                attempt_id=attempt.attempt_id,
                status=(ProcessingCostStatus.ACTUAL),
                provider_identity=result.provider.provider_identity,
                model_identity=(
                    f"{result.provider.model_identity}@{result.provider.model_revision}"
                ),
                usage=FrozenMetadata(
                    {
                        "cache_hit": cache_hit,
                        "pages_submitted": result.pages_submitted,
                        "pages_succeeded": result.pages_succeeded,
                        "pages_failed": len(
                            {
                                failure.page_number
                                for failure in result.failures
                                if failure.page_number is not None
                            }
                        ),
                        "regions": len(result.regions),
                        "provider_wall_milliseconds": provider_wall_milliseconds,
                        "attempt_number": attempt.attempt_number,
                        "completeness": result.completeness.value,
                        "languages": sorted(
                            {
                                language.language_code
                                for language in result.languages
                                if language.language_code is not None
                            }
                        ),
                        "scripts": sorted(
                            {
                                language.script
                                for language in result.languages
                                if language.script is not None
                            }
                        ),
                    }
                ),
                created_at=now,
            ),
            lease_token=job.lease_token,
        )
        return ProcessingResult(
            result_id=uuid5(_PROCESSING_RESULT_NAMESPACE, f"{job.job_id}:{result.derivation_id}"),
            job_id=job.job_id,
            attempt_id=attempt.attempt_id,
            fingerprint=job.fingerprint,
            output_reference=f"ocr-derivation:{result.derivation_id}",
            payload=FrozenMetadata(
                {
                    "derivation_id": str(result.derivation_id),
                    "content_hash": result.content_hash,
                    "completeness": result.completeness.value,
                    "cache_hit": cache_hit,
                    "evidence_kind": "derived_ocr",
                }
            ),
            created_at=now,
        )


def _request_from_job(job: ProcessingJob) -> OCRRequest:
    if job.manifest.operation != OCR_OPERATION or job.manifest.generation_id is None:
        raise IntegrityError("processing job is not a versioned OCR operation")
    raw = thaw_metadata(job.manifest.configuration).get("ocr")
    if not isinstance(raw, dict):
        raise IntegrityError("OCR job manifest configuration is unavailable")
    preprocessing = raw.get("preprocessing")
    language_hints = raw.get("language_hints")
    page_numbers = raw.get("page_numbers")
    max_pages = raw.get("max_pages")
    max_pixels = raw.get("max_pixels")
    max_output_characters = raw.get("max_output_characters")
    if (
        not isinstance(preprocessing, dict)
        or not isinstance(language_hints, list)
        or any(not isinstance(value, str) for value in language_hints)
        or not isinstance(page_numbers, list)
        or any(isinstance(value, bool) or not isinstance(value, int) for value in page_numbers)
        or isinstance(max_pages, bool)
        or not isinstance(max_pages, int)
        or isinstance(max_pixels, bool)
        or not isinstance(max_pixels, int)
        or isinstance(max_output_characters, bool)
        or not isinstance(max_output_characters, int)
    ):
        raise IntegrityError("OCR job manifest fields are malformed")
    model_identity, separator, revision = job.manifest.model_identity.rpartition("@")
    if not separator:
        raise IntegrityError("OCR model revision is missing")
    profile = OCRProfile(
        profile_id=str(raw["profile_id"]),
        provider_identity=job.manifest.provider_identity,
        model_identity=model_identity,
        model_revision=revision,
        preprocessing=FrozenMetadata(preprocessing),
        language_hints=tuple(cast(list[str], language_hints)),
        max_pages=max_pages,
        max_pixels=max_pixels,
        max_output_characters=max_output_characters,
        generation_id=job.manifest.generation_id,
    )
    request = OCRRequest(
        actor_id=job.manifest.actor_id,
        notebook_id=job.manifest.notebook_id,
        document_id=job.manifest.document_id,
        version_id=job.manifest.version_id,
        occurrence_id=job.manifest.occurrence_id,
        asset_id=UUID(str(raw["asset_id"])),
        asset_content_hash=str(raw["asset_content_hash"]),
        media_type=str(raw["media_type"]),
        profile=profile,
        page_numbers=tuple(cast(list[int], page_numbers)),
    )
    if raw.get("cache_key") != request.cache_key:
        raise IntegrityError("OCR job cache identity does not match its manifest")
    return request


def _validate_provider_result(
    request: OCRRequest, result: OCRResult, capability: OCRCapability
) -> None:
    if not isinstance(result, OCRResult):
        raise IntegrityError("OCR provider returned an invalid result type")
    if (
        result.derivation_id != request.derivation_id
        or result.cache_key != request.cache_key
        or result.document_id != request.document_id
        or result.version_id != request.version_id
        or result.occurrence_id != request.occurrence_id
        or result.asset_id != request.asset_id
        or result.generation_id != request.profile.generation_id
        or result.preprocessing_digest != request.profile.preprocessing_digest
    ):
        raise IntegrityError("OCR provider result provenance does not match its request")
    if (
        result.provider.provider_identity != request.profile.provider_identity
        or result.provider.model_identity != request.profile.model_identity
        or result.provider.model_revision != request.profile.model_revision
        or result.provider.capability != capability
    ):
        raise IntegrityError("OCR provider metadata does not match the selected profile")
    maximum_pages = min(request.profile.max_pages, capability.max_pages)
    if result.pages_submitted > maximum_pages or (
        request.page_numbers and result.pages_submitted != len(request.page_numbers)
    ):
        raise IntegrityError("OCR provider processed an invalid page count")
    requested_pages = frozenset(request.page_numbers)
    observed_pages = {
        *(region.page_number for region in result.regions),
        *(failure.page_number for failure in result.failures if failure.page_number is not None),
    }
    if requested_pages and not observed_pages.issubset(requested_pages):
        raise IntegrityError("OCR provider returned an unrequested page")
    if not capability.geometry and any(region.bounding_box for region in result.regions):
        raise IntegrityError("OCR provider returned unsupported geometry")
    if not capability.confidence and any(
        region.confidence.value is not None for region in result.regions
    ):
        raise IntegrityError("OCR provider returned unsupported confidence")


def _raise_nonpublishable(result: OCRResult) -> None:
    if result.completeness is OCRCompleteness.UNAVAILABLE:
        raise UnsupportedError("OCR provider reported the input unavailable")
    if result.completeness is OCRCompleteness.FAILED:
        raise IntegrityError("OCR provider reported a failed result")
