"""Opt-in PaddleOCR 3 provider for governed, occurrence-scoped OCR jobs.

Model directories are mandatory: constructing this provider never asks PaddleOCR
to download weights implicitly. The processing worker owns authorization, byte
hash checks, wall-time limits, and immutable derivation publication.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import importlib.metadata
import io
import json
import math
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from mnemo.models._shared import FrozenMetadata
from mnemo.models.ocr import (
    OCRCapability,
    OCRCompleteness,
    OCRConfidence,
    OCRConfidenceBand,
    OCRLanguageObservation,
    OCRProfile,
    OCRProviderMetadata,
    OCRRegion,
    OCRRequest,
    OCRResult,
    ocr_region_id,
    ocr_result_content_hash,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class PaddleOCRConfiguration:
    """All inference-affecting values must also appear in ``OCRProfile`` identity."""

    package_version: str
    model_identity: str
    model_revision: str
    detection_model_dir: Path
    recognition_model_dir: Path
    detection_model_sha256: str
    recognition_model_sha256: str
    language: str
    detection_model_name: str | None = None
    recognition_model_name: str | None = None
    ocr_version: str = "PP-OCRv3"
    device: str = "cpu"
    use_doc_orientation_classify: bool = False
    use_doc_unwarping: bool = False
    use_textline_orientation: bool = False
    max_pixels: int = 40_000_000
    medium_confidence_threshold: float = 0.5
    high_confidence_threshold: float = 0.8
    external_rasterizer_identity: str | None = None

    def __post_init__(self) -> None:
        for value in (self.package_version, self.model_identity, self.model_revision):
            if not value.strip():
                raise ValueError("PaddleOCR package/model identity must be explicit")
        if self.package_version != "3.4.1":
            raise ValueError("PaddleOCR package version differs from the checked dependency")
        if self.language not in {"en", "hi", "mr"}:
            raise ValueError("PaddleOCR profile language is unsupported")
        allowed_versions = {"PP-OCRv5"} if self.language == "en" else {"PP-OCRv3", "PP-OCRv5"}
        if self.ocr_version not in allowed_versions:
            raise ValueError("PaddleOCR language/model series combination is unsupported")
        if self.device != "cpu" and not self.device.startswith("gpu:"):
            raise ValueError("PaddleOCR device must be explicit")
        if self.max_pixels < 1:
            raise ValueError("max_pixels must be positive")
        if not (0 <= self.medium_confidence_threshold < self.high_confidence_threshold <= 1):
            raise ValueError("PaddleOCR confidence thresholds are invalid")
        for digest in (self.detection_model_sha256, self.recognition_model_sha256):
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                raise ValueError("PaddleOCR model tree digest must be a SHA-256 hash")
        for name in (self.effective_detection_model_name, self.effective_recognition_model_name):
            if not name or any(char in name for char in ("/", "\\", ":")):
                raise ValueError("PaddleOCR model name is invalid")
        if (
            self.external_rasterizer_identity is not None
            and not self.external_rasterizer_identity.strip()
        ):
            raise ValueError("PaddleOCR rasterizer identity must be explicit")

    @property
    def effective_detection_model_name(self) -> str:
        return self.detection_model_name or self.detection_model_dir.name

    @property
    def effective_recognition_model_name(self) -> str:
        return self.recognition_model_name or self.recognition_model_dir.name

    @property
    def identity_metadata(self) -> dict[str, object]:
        """Copy this into ``OCRProfile.preprocessing`` when admitting jobs."""
        return {
            "paddleocr_package_version": self.package_version,
            "ocr_version": self.ocr_version,
            "language": self.language,
            "detection_model_sha256": self.detection_model_sha256,
            "recognition_model_sha256": self.recognition_model_sha256,
            "detection_model_name": self.effective_detection_model_name,
            "recognition_model_name": self.effective_recognition_model_name,
            "max_pixels": self.max_pixels,
            "medium_confidence_threshold": self.medium_confidence_threshold,
            "high_confidence_threshold": self.high_confidence_threshold,
            "region_order": "paddleocr_predict_output",
            "geometry": "axis_aligned_rec_boxes",
            "device": self.device,
            "use_doc_orientation_classify": self.use_doc_orientation_classify,
            "use_doc_unwarping": self.use_doc_unwarping,
            "use_textline_orientation": self.use_textline_orientation,
            "animated_image_frame_policy": "first_frame",
            "external_rasterizer_identity": self.external_rasterizer_identity,
        }


type PredictionRunner = Callable[[bytes], Sequence[Mapping[str, object]]]
_GENERATION_NAMESPACE = UUID("8bf890d3-b306-59a6-8b8d-871c78adb87d")


def paddle_ocr_generation_id(config: PaddleOCRConfiguration, *, scope_identity: str) -> UUID:
    """Change the derivation generation whenever model or preprocessing changes."""
    if not scope_identity.strip():
        raise ValueError("OCR generation requires a governed scope identity")
    material = {
        "scope": scope_identity,
        "model_identity": config.model_identity,
        "model_revision": config.model_revision,
        "configuration": config.identity_metadata,
    }
    digest = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return uuid5(_GENERATION_NAMESPACE, digest)


def paddle_ocr_profile(
    config: PaddleOCRConfiguration,
    *,
    profile_id: str,
    scope_identity: str,
    max_output_characters: int,
) -> OCRProfile:
    """Create a request profile that binds the exact approved model/configuration."""
    return OCRProfile(
        profile_id=profile_id,
        provider_identity="paddleocr-v3",
        model_identity=config.model_identity,
        model_revision=config.model_revision,
        preprocessing=FrozenMetadata(config.identity_metadata),
        language_hints=(config.language,),
        max_pages=1,
        max_pixels=config.max_pixels,
        max_output_characters=max_output_characters,
        generation_id=paddle_ocr_generation_id(config, scope_identity=scope_identity),
    )


class PaddleOCRProvider:
    """Normalize PaddleOCR 3 predictions into the immutable OCR V1 contract."""

    def __init__(
        self,
        config: PaddleOCRConfiguration,
        *,
        runner: PredictionRunner | None = None,
        external_rasterizer: Callable[[bytes], bytes] | None = None,
    ) -> None:
        self._config = config
        self._runner = runner
        self._external_rasterizer = external_rasterizer
        if (external_rasterizer is None) != (config.external_rasterizer_identity is None):
            raise ValueError("PaddleOCR rasterizer and its governed identity must agree")
        self.latencies: list[float] = []
        if runner is None:
            for directory, expected in (
                (config.detection_model_dir, config.detection_model_sha256),
                (config.recognition_model_dir, config.recognition_model_sha256),
            ):
                if not directory.is_dir():
                    raise RuntimeError("PaddleOCR model directory is not provisioned")
                if _model_tree_hash(directory) != expected:
                    raise RuntimeError("PaddleOCR model directory digest does not match profile")

    @property
    def provider_identity(self) -> str:
        return "paddleocr-v3"

    async def capabilities(self) -> OCRCapability:
        media_types: tuple[str, ...] = (
            "image/png",
            "image/jpeg",
            "image/tiff",
            "image/bmp",
            "image/gif",
        )
        if self._external_rasterizer is not None:
            media_types += ("image/vnd.ms-photo",)
        return OCRCapability(
            supported_media_types=media_types,
            supported_languages=(
                ("en", "hi", "mr") if self._config.language in {"hi", "mr"} else ("en",)
            ),
            supported_scripts=(
                ("Latn", "Deva") if self._config.language in {"hi", "mr"} else ("Latn",)
            ),
            max_pages=1,
            max_pixels=self._config.max_pixels,
            geometry=True,
            confidence=True,
            cancellation=True,
        )

    async def recognize(
        self,
        request: OCRRequest,
        asset_bytes: bytes,
        cancelled: Callable[[], Awaitable[bool]],
    ) -> OCRResult:
        if request.profile.provider_identity != self.provider_identity:
            raise ValueError("OCR profile provider mismatch")
        if (request.profile.model_identity, request.profile.model_revision) != (
            self._config.model_identity,
            self._config.model_revision,
        ):
            raise ValueError("OCR profile model mismatch")
        metadata = request.profile.preprocessing
        for key, value in self._config.identity_metadata.items():
            if metadata.get(key) != value:
                raise ValueError("OCR profile configuration identity mismatch")
        if request.page_numbers and len(request.page_numbers) != 1:
            raise ValueError("PaddleOCR provider accepts one page image per occurrence")
        if await cancelled():
            raise asyncio.CancelledError
        runner = self._runner or self._predict
        started = time.perf_counter()
        inference_bytes = asset_bytes
        if request.media_type == "image/vnd.ms-photo":
            if self._external_rasterizer is None:
                raise ValueError("PaddleOCR Windows Media Photo rasterizer is unavailable")
            inference_bytes = await asyncio.to_thread(self._external_rasterizer, asset_bytes)
        predictions = await asyncio.to_thread(runner, inference_bytes)
        self.latencies.append((time.perf_counter() - started) * 1000)
        if await cancelled():
            raise asyncio.CancelledError
        if len(predictions) != 1:
            raise RuntimeError("PaddleOCR returned an unexpected page count")
        payload = predictions[0]
        nested = payload.get("res")
        if isinstance(nested, Mapping):
            payload = nested
        regions = _normalize_regions(
            request,
            payload,
            config=self._config,
            page_number=request.page_numbers[0] if request.page_numbers else 1,
        )
        if sum(len(region.text) for region in regions) > request.profile.max_output_characters:
            raise ValueError("PaddleOCR output exceeds the governed character limit")
        languages = tuple(
            dict.fromkeys(region.language for region in regions if region.language is not None)
        )
        capability = await self.capabilities()
        return OCRResult(
            derivation_id=request.derivation_id,
            cache_key=request.cache_key,
            document_id=request.document_id,
            version_id=request.version_id,
            occurrence_id=request.occurrence_id,
            asset_id=request.asset_id,
            generation_id=request.profile.generation_id,
            provider=OCRProviderMetadata(
                provider_identity=self.provider_identity,
                model_identity=self._config.model_identity,
                model_revision=self._config.model_revision,
                profile_id=request.profile.profile_id,
                capability=capability,
            ),
            preprocessing_digest=request.profile.preprocessing_digest,
            completeness=OCRCompleteness.COMPLETE,
            regions=regions,
            languages=languages,
            failures=(),
            pages_submitted=1,
            pages_succeeded=1,
            content_hash=ocr_result_content_hash(regions, languages=languages),
            created_at=datetime.now(UTC),
        )

    def _predict(self, asset_bytes: bytes) -> Sequence[Mapping[str, object]]:
        try:
            installed = importlib.metadata.version("paddleocr")
        except importlib.metadata.PackageNotFoundError as error:
            raise RuntimeError("PaddleOCR dependency is not installed") from error
        if installed != self._config.package_version:
            raise RuntimeError("PaddleOCR package version differs from the governed profile")
        image_module = importlib.import_module("PIL.Image")
        numpy = importlib.import_module("numpy")
        with image_module.open(io.BytesIO(asset_bytes)) as image:
            if image.width * image.height > self._config.max_pixels:
                raise ValueError("OCR decoded image exceeds the governed pixel limit")
            array = numpy.asarray(image.convert("RGB"))
        paddleocr = importlib.import_module("paddleocr")
        pipeline: Any = paddleocr.PaddleOCR(
            lang=self._config.language,
            ocr_version=self._config.ocr_version,
            device=self._config.device,
            text_detection_model_name=self._config.effective_detection_model_name,
            text_detection_model_dir=str(self._config.detection_model_dir),
            text_recognition_model_name=self._config.effective_recognition_model_name,
            text_recognition_model_dir=str(self._config.recognition_model_dir),
            use_doc_orientation_classify=self._config.use_doc_orientation_classify,
            use_doc_unwarping=self._config.use_doc_unwarping,
            use_textline_orientation=self._config.use_textline_orientation,
        )
        return [item.json for item in pipeline.predict(array)]


def _normalize_regions(
    request: OCRRequest,
    payload: Mapping[str, object],
    *,
    config: PaddleOCRConfiguration,
    page_number: int,
) -> tuple[OCRRegion, ...]:
    texts = payload.get("rec_texts")
    scores = payload.get("rec_scores")
    boxes = payload.get("rec_boxes")
    if not isinstance(texts, Sequence) or isinstance(texts, (str, bytes)):
        raise ValueError("PaddleOCR response has no recognized-text sequence")
    if scores is None or boxes is None:
        raise ValueError("PaddleOCR region arrays are missing")
    try:
        score_items = list(scores)  # type: ignore[call-overload]
        box_items = list(boxes)  # type: ignore[call-overload]
    except TypeError as error:
        raise ValueError("PaddleOCR region arrays are invalid") from error
    if len(texts) != len(score_items) or len(texts) != len(box_items):
        raise ValueError("PaddleOCR region arrays have inconsistent lengths")
    output: list[OCRRegion] = []
    for text, score, box in zip(texts, score_items, box_items, strict=True):
        if not isinstance(text, str):
            raise ValueError("PaddleOCR region text is invalid")
        text = text.strip()
        if not text:
            continue
        confidence_value = float(score)
        if not math.isfinite(confidence_value) or not 0 <= confidence_value <= 1:
            raise ValueError("PaddleOCR confidence is invalid")
        try:
            bounds = tuple(float(value) for value in box)
        except (TypeError, ValueError) as error:
            raise ValueError("PaddleOCR bounding box is invalid") from error
        if len(bounds) != 4:
            raise ValueError("PaddleOCR bounding box is invalid")
        if any(not math.isfinite(value) or value < 0 for value in bounds):
            raise ValueError("PaddleOCR bounding box is invalid")
        x0, y0, x1, y1 = bounds
        if x0 > x1 or y0 > y1:
            raise ValueError("PaddleOCR bounding box is reversed")
        if confidence_value >= config.high_confidence_threshold:
            band = OCRConfidenceBand.HIGH
        elif confidence_value >= config.medium_confidence_threshold:
            band = OCRConfidenceBand.MEDIUM
        else:
            band = OCRConfidenceBand.LOW
        confidence = OCRConfidence(value=confidence_value, band=band)
        devanagari = any("\u0900" <= char <= "\u097f" for char in text)
        latin = any("a" <= char.casefold() <= "z" for char in text)
        language = OCRLanguageObservation(
            # PaddleOCR's line output does not identify Hindi versus Marathi.
            # Script is observable; language is left unknown for later detection.
            language_code=None,
            script="Deva" if devanagari else "Latn" if latin else None,
            confidence=OCRConfidence(value=None, band=OCRConfidenceBand.UNAVAILABLE),
            mixed=devanagari and latin,
        )
        index = len(output)
        bbox = (x0, y0, x1, y1)
        output.append(
            OCRRegion(
                region_id=ocr_region_id(
                    derivation_id=request.derivation_id,
                    page_number=page_number,
                    order_index=index,
                    text=text,
                    bounding_box=bbox,
                ),
                page_number=page_number,
                order_index=index,
                text=text,
                bounding_box=bbox,
                confidence=confidence,
                language=language,
            )
        )
    return tuple(output)


def _model_tree_hash(directory: Path) -> str:
    """Bind an approved local model tree, not a caller-chosen directory string."""
    digest = hashlib.sha256()
    files = sorted(path for path in directory.rglob("*") if path.is_file())
    if not files:
        raise RuntimeError("PaddleOCR model directory is empty")
    for path in files:
        if path.is_symlink():
            raise RuntimeError("PaddleOCR model directory contains a symlink")
        digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    return digest.hexdigest()
