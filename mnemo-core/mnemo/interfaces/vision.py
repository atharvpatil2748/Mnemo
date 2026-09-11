"""Additive Phase 8.5.5 vision and visual-embedding contracts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.models.vision import (
    VisionCapability,
    VisionRequest,
    VisionResult,
    VisualEmbedding,
    VisualEmbeddingCapability,
    VisualEmbeddingRequest,
)

VisionCancellationCheck = Callable[[], Awaitable[bool]]


@runtime_checkable
class VisionProviderV1(Protocol):  # pragma: no cover
    @property
    def provider_identity(self) -> str: ...

    async def capabilities(self) -> VisionCapability: ...

    async def analyze(
        self,
        request: VisionRequest,
        asset_bytes: bytes,
        cancelled: VisionCancellationCheck,
    ) -> VisionResult: ...


@runtime_checkable
class VisualEmbeddingProviderV1(Protocol):  # pragma: no cover
    @property
    def provider_identity(self) -> str: ...

    async def capabilities(self) -> VisualEmbeddingCapability: ...

    async def embed_image(
        self,
        request: VisualEmbeddingRequest,
        asset_bytes: bytes,
        cancelled: VisionCancellationCheck,
    ) -> VisualEmbedding: ...


# ADR-0062 uses this name; both names intentionally describe the same contract.
ImageEmbeddingProviderV1 = VisualEmbeddingProviderV1


@runtime_checkable
class VisionAssetReaderV1(Protocol):  # pragma: no cover
    async def get_asset(self, asset_id: UUID) -> bytes | None: ...


@runtime_checkable
class VisionStoreV1(Protocol):  # pragma: no cover
    async def put_vision_result(self, result: VisionResult) -> bool: ...

    async def get_authorized_vision_result(
        self, *, notebook_id: UUID, derivation_id: UUID
    ) -> VisionResult | None: ...

    async def get_authorized_vision_result_by_cache_key(
        self, *, notebook_id: UUID, cache_key: str
    ) -> VisionResult | None: ...

    async def put_visual_embedding(self, embedding: VisualEmbedding) -> bool: ...

    async def get_authorized_visual_embedding(
        self, *, notebook_id: UUID, derivation_id: UUID
    ) -> VisualEmbedding | None: ...

    async def get_authorized_visual_embedding_by_cache_key(
        self, *, notebook_id: UUID, cache_key: str
    ) -> VisualEmbedding | None: ...

    async def project_visual_embedding(
        self, *, generation_id: UUID, embedding: VisualEmbedding
    ) -> bool: ...

    async def list_visual_projection_derivations(
        self, *, generation_id: UUID
    ) -> tuple[UUID, ...]: ...
