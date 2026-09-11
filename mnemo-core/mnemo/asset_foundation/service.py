"""Production ingestion integration for Phase 8.5.1 asset provenance."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.interfaces import AssetCatalogStoreV1, AssetRecordStoreV1, StorageInterfaceV1
from mnemo.interfaces.errors import ContractValidationError, IntegrityError
from mnemo.interfaces.parser_models import (
    AssetExtractionOmission,
    AssetExtractionOutcome,
    ParseResultV2,
)
from mnemo.interfaces.versions import PARSER_INTERFACE_VERSION
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
    FrozenMetadata,
    ImageBlock,
    ParsedDocument,
    asset_occurrence_id,
)
from mnemo.models._shared import require_positive, thaw_metadata

from .validation import sanitize_asset_filename, validate_asset_payload

_LOGGER = logging.getLogger(__name__)


@runtime_checkable
class _SafeAssetGarbageCollector(Protocol):  # pragma: no cover
    async def delete_unreferenced_asset(self, asset_id: UUID) -> bool: ...


@dataclass(frozen=True, slots=True)
class AssetRetentionResult:
    """Evidence returned after one exact-version catalog publication."""

    original_asset: Asset
    binary_reference: DocumentBinaryReference
    occurrences: tuple[AssetOccurrence, ...]
    deduplicated_blob: bool
    extraction_outcome: AssetExtractionOutcome
    omissions: tuple[AssetExtractionOmission, ...]


class AssetFoundationService:
    """Retain authoritative bytes and publish occurrence provenance additively."""

    def __init__(
        self,
        *,
        storage: StorageInterfaceV1,
        catalog: AssetCatalogStoreV1,
        asset_records: AssetRecordStoreV1,
        max_asset_bytes: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(catalog, AssetCatalogStoreV1):
            raise TypeError("catalog must implement AssetCatalogStoreV1")
        if not isinstance(asset_records, AssetRecordStoreV1):
            raise TypeError("asset_records must implement AssetRecordStoreV1")
        require_positive(max_asset_bytes, "max_asset_bytes")
        self._storage = storage
        self._catalog = catalog
        self._asset_records = asset_records
        self._max_asset_bytes = max_asset_bytes
        self._clock = clock or (lambda: datetime.now(UTC))

    async def retain_ingested_version(
        self,
        *,
        data: bytes,
        filename: str,
        declared_media_type: str,
        document: Document,
        parsed_document: ParsedDocument,
        extraction: ParseResultV2 | None = None,
        resolved_assets: Mapping[str, Asset] | None = None,
    ) -> AssetRetentionResult:
        """Store/reuse original bytes and atomically publish exact provenance."""
        safe_filename = sanitize_asset_filename(filename)
        validation = validate_asset_payload(
            data,
            declared_media_type,
            max_bytes=self._max_asset_bytes,
            filename=safe_filename,
        )
        version = next(
            (
                candidate
                for candidate in document.versions
                if candidate.version_id == document.current_version_id
            ),
            None,
        )
        if version is None:
            raise IntegrityError("document current version is unavailable")
        if validation.content_hash != version.content_hash:
            raise IntegrityError("original byte hash does not match exact document version")
        if parsed_document.metadata.content_hash != version.content_hash:
            raise IntegrityError("parsed document does not match exact document version")

        existing_blob = await self._storage.contains_hash(validation.content_hash)
        original = await self._storage.put_asset(
            data,
            validation.media_type,
            FrozenMetadata({"role": DocumentBinaryRole.ORIGINAL.value}),
        )
        if original.content_hash != validation.content_hash:
            raise IntegrityError("stored original asset hash does not match validated bytes")
        now = self._clock()
        reference = DocumentBinaryReference(
            document_id=document.document_id,
            version_id=version.version_id,
            asset_id=original.asset_id,
            role=DocumentBinaryRole.ORIGINAL,
            media_type=validation.media_type,
            byte_size=validation.byte_size,
            created_at=now,
        )
        occurrence_assets, occurrences = await self._occurrences(
            document=document,
            parsed_document=parsed_document,
            media_type=validation.media_type,
            created_at=now,
            extraction=extraction,
            resolved_assets=resolved_assets or {},
        )
        assets_by_id = {original.asset_id: original}
        assets_by_id.update({asset.asset_id: asset for asset in occurrence_assets})
        await self._catalog.register_asset_ingestion(
            assets=tuple(assets_by_id.values()),
            binary_reference=reference,
            occurrences=occurrences,
        )
        retained_reference = await self._catalog.get_document_binary_reference(version.version_id)
        if retained_reference is None:
            raise IntegrityError("registered original reference could not be reloaded")
        retained_occurrences = await self._catalog.list_asset_occurrences(version.version_id)
        _LOGGER.info(
            "asset retention completed asset_id=%s bytes=%d occurrences=%d omissions=%d "
            "outcome=%s deduplicated=%s",
            original.asset_id,
            validation.byte_size,
            len(retained_occurrences),
            0 if extraction is None else len(extraction.omissions),
            (
                AssetExtractionOutcome.UNSUPPORTED.value
                if extraction is None
                else extraction.outcome.value
            ),
            existing_blob,
        )
        return AssetRetentionResult(
            original_asset=original,
            binary_reference=retained_reference,
            occurrences=retained_occurrences,
            deduplicated_blob=existing_blob,
            extraction_outcome=(
                AssetExtractionOutcome.UNSUPPORTED if extraction is None else extraction.outcome
            ),
            omissions=() if extraction is None else extraction.omissions,
        )

    async def garbage_collect_unreferenced(self, asset_id: UUID) -> bool:
        """Use the reference-aware facade; never call frozen raw deletion."""
        if not isinstance(self._storage, _SafeAssetGarbageCollector):
            raise ContractValidationError("storage does not support reference-aware asset GC")
        return await self._storage.delete_unreferenced_asset(asset_id)

    async def _occurrences(
        self,
        *,
        document: Document,
        parsed_document: ParsedDocument,
        media_type: str,
        created_at: datetime,
        extraction: ParseResultV2 | None,
        resolved_assets: Mapping[str, Asset],
    ) -> tuple[tuple[Asset, ...], tuple[AssetOccurrence, ...]]:
        assets: dict[UUID, Asset] = {}
        occurrences: list[AssetOccurrence] = []
        container = _container_kind(media_type)
        if extraction is not None:
            for observation in extraction.asset_occurrences:
                asset = resolved_assets.get(observation.parser_local_id)
                if asset is None:
                    raise IntegrityError("parser occurrence references an unresolved asset")
                assets[asset.asset_id] = asset
                occurrences.append(
                    AssetOccurrence(
                        occurrence_id=asset_occurrence_id(
                            document_id=document.document_id,
                            version_id=document.current_version_id,
                            asset_id=asset.asset_id,
                            locator=observation.locator,
                        ),
                        asset_id=asset.asset_id,
                        document_id=document.document_id,
                        version_id=document.current_version_id,
                        container_kind=container,
                        locator=observation.locator,
                        authored_alt_text=observation.authored_alt_text,
                        extraction_provenance=observation.extraction_provenance,
                        created_at=created_at,
                    )
                )
            return tuple(assets.values()), tuple(occurrences)
        for block in parsed_document.blocks:
            if not isinstance(block, ImageBlock):
                continue
            asset = await self._asset_records.get_asset_record(block.asset_id)
            if asset is None:
                raise IntegrityError("parsed image block references missing asset metadata")
            assets[asset.asset_id] = asset
            locator = _locator_for_block(container, block)
            provenance = AssetExtractionProvenance(
                parser_id=f"mnemo.{container.value}",
                parser_version=PARSER_INTERFACE_VERSION,
                block_ordinal=block.ordinal,
                metadata=FrozenMetadata(
                    {
                        "geometry_available": block.bounding_box is not None,
                        "source_metadata": thaw_metadata(block.metadata),
                    }
                ),
            )
            occurrences.append(
                AssetOccurrence(
                    occurrence_id=asset_occurrence_id(
                        document_id=document.document_id,
                        version_id=document.current_version_id,
                        asset_id=asset.asset_id,
                        locator=locator,
                    ),
                    asset_id=asset.asset_id,
                    document_id=document.document_id,
                    version_id=document.current_version_id,
                    container_kind=container,
                    locator=locator,
                    authored_alt_text=block.alt_text,
                    extraction_provenance=provenance,
                    created_at=created_at,
                )
            )
        return tuple(assets.values()), tuple(occurrences)


def _container_kind(media_type: str) -> AssetContainerKind:
    mapping = {
        "application/pdf": AssetContainerKind.PDF,
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": (
            AssetContainerKind.PPTX
        ),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
            AssetContainerKind.DOCX
        ),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (
            AssetContainerKind.XLSX
        ),
        "text/markdown": AssetContainerKind.MARKDOWN,
        "text/html": AssetContainerKind.HTML,
    }
    if media_type.startswith("image/"):
        return AssetContainerKind.STANDALONE
    return mapping.get(media_type, AssetContainerKind.OTHER)


def _locator_for_block(container: AssetContainerKind, block: ImageBlock) -> AssetLocator:
    if container is AssetContainerKind.PDF and block.page_number is not None:
        return AssetLocator(
            kind=AssetLocatorKind.PDF_PAGE,
            ordinal=block.ordinal,
            page_number=block.page_number,
            geometry=block.bounding_box,
        )
    if container is AssetContainerKind.PPTX and block.page_number is not None:
        return AssetLocator(
            kind=AssetLocatorKind.PPTX_SLIDE,
            ordinal=block.ordinal,
            slide_number=block.page_number,
            geometry=block.bounding_box,
        )
    if container is AssetContainerKind.DOCX:
        return AssetLocator(
            kind=AssetLocatorKind.DOCX_POSITION,
            ordinal=block.ordinal,
            inline_position=block.ordinal,
            geometry=block.bounding_box,
        )
    if container is AssetContainerKind.XLSX:
        metadata = thaw_metadata(block.metadata)
        sheet_name = metadata.get("sheet_name")
        if isinstance(sheet_name, str) and sheet_name.strip():
            cell_reference = metadata.get("cell_reference")
            return AssetLocator(
                kind=AssetLocatorKind.XLSX_CELL,
                ordinal=block.ordinal,
                sheet_name=sheet_name,
                cell_reference=cell_reference if isinstance(cell_reference, str) else None,
                geometry=block.bounding_box,
            )
    if container is AssetContainerKind.STANDALONE:
        return AssetLocator(kind=AssetLocatorKind.STANDALONE, ordinal=block.ordinal)
    return AssetLocator(
        kind=AssetLocatorKind.DOCUMENT_POSITION,
        ordinal=block.ordinal,
        geometry=block.bounding_box,
    )
