"""Additive contracts for deterministic Phase 8.5 derived projections."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID

from mnemo.interfaces.asset_catalog import AssetCatalogStoreV1

if TYPE_CHECKING:
    from mnemo.phase85.projections import ProjectionBuildResult, ProjectionCoverage


@runtime_checkable
class DerivedProjectionBuilderV1(Protocol):  # pragma: no cover
    """Build one immutable generation without promoting it."""

    async def build(self, generation_id: UUID) -> ProjectionBuildResult: ...


@runtime_checkable
class DerivedProjectionStoreV1(AssetCatalogStoreV1, Protocol):  # pragma: no cover
    """Persist generation coverage independently from canonical V1 records."""

    async def put_index_generation_coverage(self, coverage: ProjectionCoverage) -> bool: ...

    async def get_index_generation_coverage(
        self, generation_id: UUID
    ) -> ProjectionCoverage | None: ...

    async def put_index_generation_sources(
        self,
        *,
        generation_id: UUID,
        source_generation_ids: tuple[UUID, ...],
        source_version_ids: tuple[UUID, ...],
    ) -> bool: ...

    async def get_index_generation_sources(
        self, generation_id: UUID
    ) -> tuple[tuple[UUID, ...], tuple[UUID, ...]]: ...

    async def rollback_index_generation(self, generation_id: UUID) -> bool: ...

    async def build_vision_text_projection(
        self, *, generation_id: UUID, source_generation_ids: tuple[UUID, ...]
    ) -> ProjectionBuildResult: ...

    async def build_language_text_projection(
        self, *, generation_id: UUID, source_generation_ids: tuple[UUID, ...]
    ) -> ProjectionBuildResult: ...

    async def build_multilingual_vector_projection(
        self, *, generation_id: UUID, source_generation_ids: tuple[UUID, ...]
    ) -> ProjectionBuildResult: ...
