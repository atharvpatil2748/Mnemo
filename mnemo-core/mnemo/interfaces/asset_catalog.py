"""Additive Phase 8.5 asset catalog and generation contracts."""

from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.models import (
    Asset,
    AssetDerivation,
    AssetDerivationDescriptor,
    AssetDerivationStatus,
    AssetOccurrence,
    DocumentBinaryAvailability,
    DocumentBinaryReference,
    DocumentBinaryRole,
    IndexGeneration,
    IndexGenerationState,
)


@runtime_checkable
class AuthorizedAssetAnalysisCatalogV1(Protocol):  # pragma: no cover
    """Occurrence-authorized derivation discovery without bare-asset authority."""

    async def list_authorized_asset_derivations(
        self, *, notebook_id: UUID, occurrence_id: UUID
    ) -> tuple[AssetDerivationDescriptor, ...]: ...


@runtime_checkable
class AssetCatalogStoreV1(Protocol):  # pragma: no cover
    """Persist additive asset provenance without widening StorageInterfaceV1."""

    async def register_asset_ingestion(
        self,
        *,
        assets: tuple[Asset, ...],
        binary_reference: DocumentBinaryReference,
        occurrences: tuple[AssetOccurrence, ...],
    ) -> None:
        """Atomically register exact-version original and extracted occurrences."""
        ...

    async def get_document_binary_reference(
        self,
        version_id: UUID,
        role: DocumentBinaryRole = DocumentBinaryRole.ORIGINAL,
    ) -> DocumentBinaryReference | None:
        """Return one retained exact-version binary reference."""
        ...

    async def get_document_binary_availability(
        self,
        version_id: UUID,
        role: DocumentBinaryRole = DocumentBinaryRole.ORIGINAL,
    ) -> DocumentBinaryAvailability:
        """Report retained original availability without fabricating history."""
        ...

    async def get_asset_record(self, asset_id: UUID) -> Asset | None:
        """Return catalog metadata without exposing filesystem paths."""
        ...

    async def get_asset_occurrence(self, occurrence_id: UUID) -> AssetOccurrence | None:
        """Return an occurrence without authorizing disclosure."""
        ...

    async def list_asset_occurrences(self, version_id: UUID) -> tuple[AssetOccurrence, ...]:
        """Return deterministic exact-version occurrences."""
        ...

    async def get_authorized_asset_occurrence(
        self,
        *,
        notebook_id: UUID,
        occurrence_id: UUID,
    ) -> AssetOccurrence | None:
        """Resolve through notebook/source/document/version scope."""
        ...

    async def create_asset_derivation(self, derivation: AssetDerivation) -> bool:
        """Create one idempotent derivation identity."""
        ...

    async def get_asset_derivation(self, derivation_id: UUID) -> AssetDerivation | None:
        """Return one derivation lifecycle snapshot."""
        ...

    async def transition_asset_derivation(
        self,
        derivation_id: UUID,
        expected: AssetDerivationStatus,
        target: AssetDerivationStatus,
        *,
        output_asset_id: UUID | None = None,
        output_payload_json: str | None = None,
        confidence: float | None = None,
        language: str | None = None,
    ) -> bool:
        """Conditionally transition derivation state."""
        ...

    async def create_index_generation(self, generation: IndexGeneration) -> bool:
        """Create a BUILDING generation idempotently."""
        ...

    async def get_index_generation(self, generation_id: UUID) -> IndexGeneration | None:
        """Return one generation snapshot."""
        ...

    async def transition_index_generation(
        self,
        generation_id: UUID,
        expected: IndexGenerationState,
        target: IndexGenerationState,
        *,
        item_count: int | None = None,
        checksum: str | None = None,
    ) -> bool:
        """Conditionally transition a non-promotion generation state."""
        ...

    async def promote_index_generation(self, generation_id: UUID) -> bool:
        """Atomically activate one READY generation and supersede the prior one."""
        ...

    async def get_active_index_generation(
        self, capability: str, profile: str
    ) -> IndexGeneration | None:
        """Return only an atomically promoted READY generation."""
        ...

    async def add_asset_gc_reference(
        self, asset_id: UUID, reference_kind: str, reference_id: str
    ) -> None:
        """Register a future job/snapshot retention dependency."""
        ...

    async def remove_asset_gc_reference(
        self, asset_id: UUID, reference_kind: str, reference_id: str
    ) -> None:
        """Remove a retention dependency idempotently."""
        ...

    async def is_asset_referenced(self, asset_id: UUID) -> bool:
        """Return whether GC must retain one asset."""
        ...

    async def delete_asset_catalog_record(self, asset_id: UUID) -> bool:
        """Delete only an unreferenced catalog row."""
        ...


@runtime_checkable
class AssetRecordStoreV1(Protocol):  # pragma: no cover
    """Additive blob metadata lookup used by the asset foundation."""

    async def get_asset_record(self, asset_id: UUID) -> Asset | None:
        """Return immutable blob metadata without reading bytes."""
        ...
