"""Additive OCR provider and derived-projection contracts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.models.ocr import (
    OCRCapability,
    OCRRequest,
    OCRResult,
)

OCRCancellationCheck = Callable[[], Awaitable[bool]]


@runtime_checkable
class OCRProviderV1(Protocol):  # pragma: no cover
    """Stateless provider boundary; durable behavior belongs to the worker."""

    @property
    def provider_identity(self) -> str: ...

    async def capabilities(self) -> OCRCapability: ...

    async def recognize(
        self,
        request: OCRRequest,
        asset_bytes: bytes,
        cancelled: OCRCancellationCheck,
    ) -> OCRResult: ...


@runtime_checkable
class OCRAssetReaderV1(Protocol):  # pragma: no cover
    """Read immutable bytes by opaque asset identity."""

    async def get_asset(self, asset_id: UUID) -> bytes | None: ...


@runtime_checkable
class OCRStoreV1(Protocol):  # pragma: no cover
    """Persist immutable OCR results and independent index projections."""

    async def put_ocr_result(self, result: OCRResult) -> bool: ...

    async def get_authorized_ocr_result(
        self, *, notebook_id: UUID, derivation_id: UUID
    ) -> OCRResult | None: ...

    async def get_authorized_ocr_result_by_cache_key(
        self, *, notebook_id: UUID, cache_key: str
    ) -> OCRResult | None: ...

    async def project_ocr_result(self, *, generation_id: UUID, result: OCRResult) -> int: ...

    async def list_ocr_projection_regions(
        self, *, generation_id: UUID, derivation_id: UUID
    ) -> tuple[UUID, ...]: ...
