"""Shared bounded document/asset expansion used by HTTP and MCP adapters."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from typing import Any, cast
from uuid import UUID

from mnemo.cursors import (
    CursorCodecV2,
    CursorConflictError,
    CursorExpiredError,
    CursorInvalidError,
    CursorKeyUnavailableError,
    CursorSigningKeyV2,
)
from mnemo.document_positions import ExactDocumentPositionIndex
from mnemo.interfaces import (
    AssetCatalogStoreV1,
    AuthorizedAssetAnalysisCatalogV1,
    ContractValidationError,
    DeliveryAuthorizationError,
    DeliveryCursorConflictError,
    DeliveryCursorError,
    DeliveryCursorExpiredError,
    DeliveryLimitExceededError,
    DocumentExpansionServiceV1,
    ExactDocumentReaderV1,
    FinalQAExecutionStoreV2,
    IntegrityError,
    NotFoundError,
    OCRStoreV1,
    StorageInterfaceV1,
    VisionStoreV1,
)
from mnemo.models import (
    Asset,
    AssetAnalysisModality,
    AssetAnalysisSelection,
    AssetAnalysisSelector,
    AssetDerivationDescriptor,
    AssetOccurrence,
    DeliveryAttribution,
    DeliveryCapability,
    DeliveryCapabilityState,
    DeliveryCompleteness,
    DeliveryItem,
    DeliveryLimits,
    DeliveryRequest,
    DeliveryResourceKind,
    DeliveryResponse,
    DeliveryUsage,
    DeliveryView,
    DocumentBinaryRole,
    DocumentExpansionRequestV2,
    FinalQAExecutionSnapshotPhase,
    FrozenMetadata,
    ImageBlock,
)
from mnemo.models.delivery import BinaryDelivery
from mnemo.retrieval.multimodal_snapshot import decode_published_v2_snapshot


@dataclass(frozen=True, slots=True)
class _AuthorizedVersion:
    source_id: UUID
    content_hash: str


class BoundedDocumentExpansionService(DocumentExpansionServiceV1):
    """One fail-closed policy boundary for all Phase 8.5 delivery transports."""

    def __init__(
        self,
        *,
        storage: StorageInterfaceV1,
        catalog: AssetCatalogStoreV1,
        limits: DeliveryLimits | None = None,
        cursor_secret: bytes = b"mnemo-local-delivery-v1",
        cursor_codec: CursorCodecV2 | None = None,
        exact_reader: ExactDocumentReaderV1 | None = None,
        legacy_cursor_overlap: timedelta = timedelta(minutes=15),
        legacy_cursor_accept_until: datetime | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not isinstance(storage, StorageInterfaceV1):
            raise TypeError("storage must implement StorageInterfaceV1")
        if not isinstance(catalog, AssetCatalogStoreV1):
            raise TypeError("catalog must implement AssetCatalogStoreV1")
        if not isinstance(cursor_secret, bytes) or len(cursor_secret) < 16:
            raise ValueError("cursor_secret must contain at least 16 bytes")
        self._storage = storage
        self._exact_reader = exact_reader
        self._catalog = catalog
        self._limits = limits or DeliveryLimits()
        self._cursor_secret = cursor_secret
        self._clock = clock
        if legacy_cursor_overlap < timedelta(0):
            raise ValueError("legacy cursor overlap must be non-negative")
        self._legacy_cursor_deadline = legacy_cursor_accept_until or (
            clock() + legacy_cursor_overlap
        )
        self._cursor_codec = cursor_codec or CursorCodecV2(
            CursorSigningKeyV2(
                key_id="delivery-v2",
                secret=hashlib.sha256(b"mnemo-delivery-v2\0" + cursor_secret).digest(),
            ),
            clock=clock,
        )

    async def expand_document_v2(self, request: DocumentExpansionRequestV2) -> DeliveryResponse:
        """Resolve one exact selector and page its immutable physical result."""
        authorized = await self._authorize_version(
            DeliveryRequest(
                notebook_id=request.notebook_id,
                document_id=request.document_id,
                version_id=request.version_id,
            )
        )
        parsed = await self._storage.get_parsed_document(request.version_id)
        if parsed is None:
            raise NotFoundError("parsed document representation was not found")
        reader = self._exact_reader
        if reader is None and isinstance(self._storage, ExactDocumentReaderV1):
            reader = self._storage
        if reader is None:
            return DeliveryResponse(
                resource_kind=DeliveryResourceKind.DOCUMENT,
                snapshot_identity=_snapshot(
                    "document-selector-unavailable", request.document_id, request.version_id
                ),
                completeness=DeliveryCompleteness.UNAVAILABLE,
                items=(),
                usage=DeliveryUsage(items=0, bytes=0),
                omissions=("exact_chunk_reader_unavailable",),
            )
        chunks = await reader.list_exact_document_chunks(
            document_id=request.document_id, version_id=request.version_id
        )
        if any(
            chunk.document_id != request.document_id or chunk.version_id != request.version_id
            for chunk in chunks
        ):
            raise IntegrityError("exact chunk reader escaped requested document version")
        index = ExactDocumentPositionIndex(parsed, chunks)
        selection = index.select(request.selector)
        selector_value = _json_value(request.selector)
        snapshot = _snapshot(
            "document-selector-v2",
            request.notebook_id,
            request.document_id,
            request.version_id,
            authorized.content_hash,
            _canonical_digest(parsed.blocks),
            _canonical_digest(chunks),
        )
        if not selection.available:
            return DeliveryResponse(
                resource_kind=DeliveryResourceKind.DOCUMENT,
                snapshot_identity=snapshot,
                completeness=DeliveryCompleteness.UNAVAILABLE,
                items=(),
                usage=DeliveryUsage(items=0, bytes=0),
                omissions=(selection.reason or "requested_representation_unavailable",),
            )
        if not selection.units:
            return DeliveryResponse(
                resource_kind=DeliveryResourceKind.DOCUMENT,
                snapshot_identity=snapshot,
                completeness=DeliveryCompleteness.EMPTY,
                items=(),
                usage=DeliveryUsage(items=0, bytes=0),
            )
        max_items = min(request.max_items or self._limits.max_items, self._limits.max_items)
        max_bytes = min(
            request.max_bytes or self._limits.max_response_bytes,
            self._limits.max_response_bytes,
        )
        binding = {
            "notebook_id": str(request.notebook_id),
            "document_id": str(request.document_id),
            "version_id": str(request.version_id),
            "selector": selector_value,
        }
        limits: dict[str, object] = {"max_items": max_items, "max_bytes": max_bytes}
        offset = self._decode_bound_cursor(
            request.cursor,
            domain="mnemo-document-expansion/v2",
            snapshot=snapshot,
            binding=binding,
            limits=limits,
        )
        _validate_cursor_offset(offset, len(selection.units), request.cursor)
        items: list[DeliveryItem] = []
        used = 0
        for selected_index in range(offset, min(len(selection.units), offset + max_items)):
            unit = selection.units[selected_index]
            payload = _json_value(unit.value)
            assert isinstance(payload, dict)
            payload["exact_position"] = {
                "kind": unit.kind,
                "physical_index": unit.physical_index,
                "heading_path": list(unit.heading_path),
                "sheet_name": unit.sheet_name,
                "asset_ids": (
                    [str(unit.value.asset_id)] if isinstance(unit.value, ImageBlock) else []
                ),
                "overlapping_chunk_ids": (
                    list(index.overlapping_chunks(unit.physical_index))
                    if unit.kind == "block"
                    else []
                ),
            }
            size = len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
            if items and used + size > max_bytes:
                break
            if size > max_bytes:
                raise DeliveryLimitExceededError(
                    "one selected document unit exceeds the response byte limit"
                )
            items.append(
                DeliveryItem(
                    index=unit.physical_index,
                    kind=f"canonical_{unit.kind}",
                    attribution=DeliveryAttribution(
                        notebook_id=request.notebook_id,
                        source_id=authorized.source_id,
                        document_id=request.document_id,
                        version_id=request.version_id,
                        modality=("image" if type(unit.value).__name__ == "ImageBlock" else "text"),
                    ),
                    payload=payload,
                    byte_size=size,
                )
            )
            used += size
        next_offset = offset + len(items)
        truncated = next_offset < len(selection.units)
        return DeliveryResponse(
            resource_kind=DeliveryResourceKind.DOCUMENT,
            snapshot_identity=snapshot,
            completeness=(
                DeliveryCompleteness.TRUNCATED if truncated else DeliveryCompleteness.COMPLETE
            ),
            items=tuple(items),
            usage=DeliveryUsage(items=len(items), bytes=used),
            omissions=("selector_bounds_applied",) if truncated else (),
            next_cursor=(
                self._encode_bound_cursor(
                    domain="mnemo-document-expansion/v2",
                    snapshot=snapshot,
                    binding=binding,
                    position=next_offset,
                    limits=limits,
                )
                if truncated
                else None
            ),
        )

    def capabilities(self) -> tuple[DeliveryCapability, ...]:
        ocr = isinstance(self._storage, OCRStoreV1)
        vision = isinstance(self._storage, VisionStoreV1)
        return (
            _cap("original_document_delivery", True),
            _cap("image_delivery", True),
            _cap("ocr", ocr),
            _cap("vision", vision),
            DeliveryCapability(name="visual_embeddings", state=DeliveryCapabilityState.UNVALIDATED),
            _cap(
                "multilingual_retrieval",
                hasattr(self._storage, "get_authorized_language_observation"),
            ),
            _cap("multimodal_final_qa", hasattr(self._storage, "get_final_qa_v2_execution")),
            _cap("structured_retrieval", hasattr(self._storage, "get_structured_projection")),
            _cap("streaming", True),
            _cap("binary_resources", True),
        )

    async def expand_document(self, request: DeliveryRequest) -> DeliveryResponse:
        if request.view is not DeliveryView.BLOCKS:
            raise ContractValidationError("expand_document requires the blocks view")
        authorized = await self._authorize_version(request)
        parsed = await self._storage.get_parsed_document(request.version_id)
        if parsed is None:
            raise NotFoundError("parsed document representation was not found")
        snapshot = _snapshot(
            "document-blocks",
            request.notebook_id,
            request.document_id,
            request.version_id,
            authorized.content_hash,
            _canonical_digest(parsed.blocks),
        )
        max_items = min(request.max_items or self._limits.max_items, self._limits.max_items)
        max_bytes = min(
            request.max_bytes or self._limits.max_response_bytes,
            self._limits.max_response_bytes,
        )
        fingerprint = _fingerprint(
            "document-blocks",
            request.notebook_id,
            request.document_id,
            request.version_id,
            max_items,
            max_bytes,
        )
        offset = self._decode_cursor(request.cursor, snapshot, fingerprint)
        items: list[DeliveryItem] = []
        used = 0
        blocks = parsed.blocks
        _validate_cursor_offset(offset, len(blocks), request.cursor)
        for index in range(offset, min(len(blocks), offset + max_items)):
            block = blocks[index]
            payload = _json_value(block)
            assert isinstance(payload, dict)
            size = len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
            if items and used + size > max_bytes:
                break
            if size > max_bytes:
                raise DeliveryLimitExceededError(
                    "one document block exceeds the response byte limit"
                )
            items.append(
                DeliveryItem(
                    index=index,
                    kind=type(block).__name__,
                    attribution=DeliveryAttribution(
                        notebook_id=request.notebook_id,
                        source_id=authorized.source_id,
                        document_id=request.document_id,
                        version_id=request.version_id,
                        modality="image" if type(block).__name__ == "ImageBlock" else "text",
                    ),
                    payload=payload,
                    byte_size=size,
                )
            )
            used += size
        next_offset = offset + len(items)
        truncated = next_offset < len(blocks)
        return DeliveryResponse(
            resource_kind=DeliveryResourceKind.DOCUMENT,
            snapshot_identity=snapshot,
            completeness=(
                DeliveryCompleteness.TRUNCATED if truncated else DeliveryCompleteness.COMPLETE
            ),
            items=tuple(items),
            usage=DeliveryUsage(items=len(items), bytes=used),
            omissions=("document_bounds_applied",) if truncated else (),
            next_cursor=self._encode_cursor(snapshot, fingerprint, next_offset)
            if truncated
            else None,
        )

    async def get_original_document(self, request: DeliveryRequest) -> BinaryDelivery:
        if request.view is not DeliveryView.ORIGINAL:
            raise ContractValidationError("original delivery requires the original view")
        authorized = await self._authorize_version(request)
        reference = await self._catalog.get_document_binary_reference(
            request.version_id, DocumentBinaryRole.ORIGINAL
        )
        if reference is None or reference.document_id != request.document_id:
            raise NotFoundError("authoritative original bytes are unavailable")
        asset = await self._catalog.get_asset_record(reference.asset_id)
        content = await self._storage.get_asset(reference.asset_id)
        if asset is None or content is None:
            raise NotFoundError("authoritative original asset was not found")
        _verify_asset(
            content, asset.content_hash, reference.byte_size, reference.media_type, asset.mime_type
        )
        snapshot = _snapshot("document-original", request.version_id, asset.content_hash)
        max_bytes = min(
            request.max_bytes or self._limits.max_document_bytes,
            self._limits.max_document_bytes,
            self._limits.max_response_bytes,
        )
        fingerprint = _fingerprint(
            "document-original",
            request.notebook_id,
            request.document_id,
            request.version_id,
            max_bytes,
        )
        offset = self._decode_cursor(request.cursor, snapshot, fingerprint)
        _validate_cursor_offset(offset, len(content), request.cursor)
        part = content[offset : offset + max_bytes]
        end = offset + len(part)
        truncated = end < len(content)
        return BinaryDelivery(
            resource_kind=DeliveryResourceKind.DOCUMENT,
            attribution=DeliveryAttribution(
                notebook_id=request.notebook_id,
                source_id=authorized.source_id,
                document_id=request.document_id,
                version_id=request.version_id,
                asset_id=reference.asset_id,
            ),
            snapshot_identity=snapshot,
            content=part,
            media_type=reference.media_type,
            content_hash=asset.content_hash,
            total_byte_size=len(content),
            range_start=offset,
            completeness=(
                DeliveryCompleteness.TRUNCATED if truncated else DeliveryCompleteness.COMPLETE
            ),
            next_cursor=self._encode_cursor(snapshot, fingerprint, end) if truncated else None,
        )

    async def get_document_chunk(
        self, *, notebook_id: UUID, document_id: UUID, version_id: UUID, chunk_id: str
    ) -> DeliveryResponse:
        request = DeliveryRequest(
            notebook_id=notebook_id, document_id=document_id, version_id=version_id
        )
        authorized = await self._authorize_version(request)
        chunk = await self._storage.get_chunk(chunk_id)
        if chunk is None or chunk.document_id != document_id or chunk.version_id != version_id:
            raise NotFoundError("authorized chunk was not found")
        ancestry = []
        parent_id = chunk.parent_chunk_id
        if parent_id is not None:
            parent = await self._storage.get_chunk(parent_id)
            if (
                parent is not None
                and parent.document_id == document_id
                and parent.version_id == version_id
            ):
                ancestry.append(parent.id)
        payload = _json_value(chunk)
        assert isinstance(payload, dict)
        payload["ancestry"] = ancestry
        size = len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
        if size > self._limits.max_response_bytes:
            raise DeliveryLimitExceededError("chunk exceeds the response byte limit")
        snapshot = _snapshot("chunk", notebook_id, version_id, chunk.id)
        return DeliveryResponse(
            resource_kind=DeliveryResourceKind.CHUNK,
            snapshot_identity=snapshot,
            completeness=DeliveryCompleteness.COMPLETE,
            items=(
                DeliveryItem(
                    index=0,
                    kind="canonical_chunk",
                    attribution=DeliveryAttribution(
                        notebook_id=notebook_id,
                        source_id=authorized.source_id,
                        document_id=document_id,
                        version_id=version_id,
                        modality="text",
                    ),
                    payload=payload,
                    byte_size=size,
                ),
            ),
            usage=DeliveryUsage(items=1, bytes=size),
        )

    async def list_assets(
        self,
        *,
        notebook_id: UUID,
        document_id: UUID,
        version_id: UUID,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> DeliveryResponse:
        request = DeliveryRequest(
            notebook_id=notebook_id, document_id=document_id, version_id=version_id
        )
        authorized = await self._authorize_version(request)
        occurrences = await self._catalog.list_asset_occurrences(version_id)
        if any(item.document_id != document_id for item in occurrences):
            raise IntegrityError("asset occurrence escaped exact-version scope")
        derivations_by_occurrence: dict[UUID, tuple[AssetDerivationDescriptor, ...]] = {}
        if isinstance(self._catalog, AuthorizedAssetAnalysisCatalogV1):
            for occurrence in occurrences:
                derivations_by_occurrence[
                    occurrence.occurrence_id
                ] = await self._catalog.list_authorized_asset_derivations(
                    notebook_id=notebook_id, occurrence_id=occurrence.occurrence_id
                )
        snapshot = _snapshot(
            "asset-inventory",
            notebook_id,
            document_id,
            version_id,
            *(str(item.occurrence_id) for item in occurrences),
            _canonical_digest(derivations_by_occurrence),
        )
        page_limit = min(limit or self._limits.max_assets, self._limits.max_assets)
        fingerprint = _fingerprint(
            "asset-inventory", notebook_id, document_id, version_id, page_limit
        )
        offset = self._decode_cursor(cursor, snapshot, fingerprint)
        _validate_cursor_offset(offset, len(occurrences), cursor)
        selected = occurrences[offset : offset + page_limit]
        items: list[DeliveryItem] = []
        used = 0
        for index, occurrence in enumerate(selected, start=offset):
            asset = await self._catalog.get_asset_record(occurrence.asset_id)
            if asset is None:
                raise IntegrityError("asset occurrence references missing asset metadata")
            payload = _occurrence_payload(occurrence, asset)
            payload["derivations"] = [
                {
                    **_json_value(descriptor),
                    "availability": descriptor.availability,
                    "ready": descriptor.ready,
                }
                for descriptor in derivations_by_occurrence.get(occurrence.occurrence_id, ())
            ]
            size = len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
            used += size
            if used > self._limits.max_response_bytes:
                raise DeliveryLimitExceededError("asset inventory exceeds response byte limit")
            items.append(
                DeliveryItem(
                    index=index,
                    kind="asset_occurrence",
                    attribution=DeliveryAttribution(
                        notebook_id=notebook_id,
                        source_id=authorized.source_id,
                        document_id=document_id,
                        version_id=version_id,
                        asset_id=occurrence.asset_id,
                        occurrence_id=occurrence.occurrence_id,
                        modality="image" if asset.mime_type.startswith("image/") else "asset",
                    ),
                    payload=payload,
                    byte_size=size,
                )
            )
        next_offset = offset + len(items)
        truncated = next_offset < len(occurrences)
        return DeliveryResponse(
            resource_kind=DeliveryResourceKind.ASSET_INVENTORY,
            snapshot_identity=snapshot,
            completeness=(
                DeliveryCompleteness.TRUNCATED if truncated else DeliveryCompleteness.COMPLETE
            ),
            items=tuple(items),
            usage=DeliveryUsage(items=len(items), bytes=used, assets=len(items)),
            omissions=("asset_count_bound",) if truncated else (),
            next_cursor=self._encode_cursor(snapshot, fingerprint, next_offset)
            if truncated
            else None,
        )

    async def get_image_analysis_v2(
        self, *, notebook_id: UUID, occurrence_id: UUID, selector: AssetAnalysisSelector
    ) -> DeliveryResponse:
        """Resolve authorized immutable OCR/Vision results without guessed IDs."""
        occurrence = await self._catalog.get_authorized_asset_occurrence(
            notebook_id=notebook_id, occurrence_id=occurrence_id
        )
        if occurrence is None:
            raise DeliveryAuthorizationError("asset occurrence is not available in notebook scope")
        if not isinstance(self._catalog, AuthorizedAssetAnalysisCatalogV1):
            return _unavailable_analysis(
                notebook_id, occurrence_id, "derivation_catalog_unavailable"
            )
        descriptors = await self._catalog.list_authorized_asset_derivations(
            notebook_id=notebook_id, occurrence_id=occurrence_id
        )
        requested = tuple(
            item
            for item in descriptors
            if item.modality in selector.modalities
            and (selector.profile is None or item.generation_profile == selector.profile)
        )
        missing_modalities: tuple[AssetAnalysisModality, ...] = ()
        if selector.selection is AssetAnalysisSelection.EXPLICIT:
            by_id = {item.derivation_id: item for item in requested}
            if any(item not in by_id for item in selector.derivation_ids):
                raise DeliveryAuthorizationError(
                    "analysis derivation is not authorized for occurrence"
                )
            chosen = tuple(by_id[item] for item in selector.derivation_ids)
        elif selector.selection is AssetAnalysisSelection.LATEST_READY:
            selected = []
            missing = []
            for modality in selector.modalities:
                ready = [item for item in requested if item.modality is modality and item.ready]
                if ready:
                    selected.append(
                        max(ready, key=lambda item: (item.updated_at, str(item.derivation_id)))
                    )
                else:
                    missing.append(modality)
            chosen = tuple(selected)
            missing_modalities = tuple(missing)
        else:
            chosen = tuple(item for item in requested if item.ready)
            missing_modalities = tuple(
                modality
                for modality in selector.modalities
                if not any(item.modality is modality and item.ready for item in requested)
            )
        if not chosen or any(not item.ready for item in chosen):
            return _unavailable_analysis(notebook_id, occurrence_id, "ready_analysis_unavailable")

        responses = []
        for descriptor in chosen:
            responses.append(
                await self.get_image_analysis(
                    notebook_id=notebook_id,
                    occurrence_id=occurrence_id,
                    ocr_derivation_id=(
                        descriptor.derivation_id
                        if descriptor.modality is AssetAnalysisModality.OCR
                        else None
                    ),
                    vision_derivation_id=(
                        descriptor.derivation_id
                        if descriptor.modality is AssetAnalysisModality.VISION
                        else None
                    ),
                )
            )
        items = tuple(item for response in responses for item in response.items)
        used = sum(item.byte_size for item in items)
        if used > self._limits.max_response_bytes:
            raise DeliveryLimitExceededError("analysis response exceeds delivery limit")
        completeness = _aggregate_delivery_completeness(responses)
        if missing_modalities:
            completeness = DeliveryCompleteness.PARTIAL
        return DeliveryResponse(
            resource_kind=DeliveryResourceKind.ANALYSIS,
            snapshot_identity=_snapshot(
                "analysis-selection-v2",
                notebook_id,
                occurrence_id,
                selector.selection,
                *(str(item.derivation_id) for item in chosen),
            ),
            completeness=completeness,
            items=items,
            usage=DeliveryUsage(items=len(items), bytes=used),
            omissions=tuple(omission for response in responses for omission in response.omissions)
            + tuple(
                f"analysis_modality_unavailable:{modality.value}" for modality in missing_modalities
            ),
        )

    async def get_asset(
        self,
        *,
        notebook_id: UUID,
        occurrence_id: UUID,
        cursor: str | None = None,
        max_bytes: int | None = None,
    ) -> BinaryDelivery:
        if max_bytes is not None and max_bytes <= 0:
            raise ContractValidationError("max_bytes must be positive")
        occurrence = await self._catalog.get_authorized_asset_occurrence(
            notebook_id=notebook_id, occurrence_id=occurrence_id
        )
        if occurrence is None:
            raise DeliveryAuthorizationError("asset occurrence is not available in notebook scope")
        authorized = await self._authorize_version(
            DeliveryRequest(
                notebook_id=notebook_id,
                document_id=occurrence.document_id,
                version_id=occurrence.version_id,
            )
        )
        asset = await self._catalog.get_asset_record(occurrence.asset_id)
        content = await self._storage.get_asset(occurrence.asset_id)
        if asset is None or content is None:
            raise NotFoundError("asset bytes were not found")
        _verify_asset(content, asset.content_hash, len(content), asset.mime_type, asset.mime_type)
        snapshot = _snapshot("asset", occurrence_id, asset.content_hash)
        effective_max_bytes = min(
            max_bytes or self._limits.max_asset_bytes,
            self._limits.max_asset_bytes,
            self._limits.max_response_bytes,
        )
        fingerprint = _fingerprint("asset", notebook_id, occurrence_id, effective_max_bytes)
        offset = self._decode_cursor(cursor, snapshot, fingerprint)
        _validate_cursor_offset(offset, len(content), cursor)
        part = content[offset : offset + effective_max_bytes]
        end = offset + len(part)
        truncated = end < len(content)
        return BinaryDelivery(
            resource_kind=DeliveryResourceKind.ASSET,
            attribution=DeliveryAttribution(
                notebook_id=notebook_id,
                source_id=authorized.source_id,
                document_id=occurrence.document_id,
                version_id=occurrence.version_id,
                asset_id=occurrence.asset_id,
                occurrence_id=occurrence_id,
                modality="image" if asset.mime_type.startswith("image/") else "asset",
            ),
            snapshot_identity=snapshot,
            content=part,
            media_type=asset.mime_type,
            content_hash=asset.content_hash,
            total_byte_size=len(content),
            range_start=offset,
            completeness=(
                DeliveryCompleteness.TRUNCATED if truncated else DeliveryCompleteness.COMPLETE
            ),
            next_cursor=self._encode_cursor(snapshot, fingerprint, end) if truncated else None,
        )

    async def get_image_analysis(
        self,
        *,
        notebook_id: UUID,
        occurrence_id: UUID,
        ocr_derivation_id: UUID | None = None,
        vision_derivation_id: UUID | None = None,
    ) -> DeliveryResponse:
        occurrence = await self._catalog.get_authorized_asset_occurrence(
            notebook_id=notebook_id, occurrence_id=occurrence_id
        )
        if occurrence is None:
            raise DeliveryAuthorizationError("asset occurrence is not available in notebook scope")
        authorized = await self._authorize_version(
            DeliveryRequest(
                notebook_id=notebook_id,
                document_id=occurrence.document_id,
                version_id=occurrence.version_id,
            )
        )
        if ocr_derivation_id is None and vision_derivation_id is None:
            raise ContractValidationError("at least one analysis derivation ID is required")
        results: list[tuple[str, UUID, object]] = []
        if ocr_derivation_id is not None:
            if not isinstance(self._storage, OCRStoreV1):
                raise NotFoundError("OCR delivery is unavailable")
            ocr_result = await self._storage.get_authorized_ocr_result(
                notebook_id=notebook_id, derivation_id=ocr_derivation_id
            )
            if ocr_result is None or ocr_result.occurrence_id != occurrence_id:
                raise DeliveryAuthorizationError("OCR derivation is not authorized for occurrence")
            results.append(("derived_ocr", ocr_derivation_id, ocr_result))
        if vision_derivation_id is not None:
            if not isinstance(self._storage, VisionStoreV1):
                raise NotFoundError("vision delivery is unavailable")
            vision_result = await self._storage.get_authorized_vision_result(
                notebook_id=notebook_id, derivation_id=vision_derivation_id
            )
            if vision_result is None or vision_result.occurrence_id != occurrence_id:
                raise DeliveryAuthorizationError(
                    "vision derivation is not authorized for occurrence"
                )
            results.append(("derived_vision", vision_derivation_id, vision_result))
        items: list[DeliveryItem] = []
        used = 0
        analysis_bounded = False
        for index, (kind, derivation_id, result) in enumerate(results):
            payload, item_bounded = _bounded_analysis_payload(result, self._limits)
            analysis_bounded = analysis_bounded or item_bounded
            size = len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
            if used + size > self._limits.max_response_bytes:
                raise DeliveryLimitExceededError("analysis response exceeds delivery limit")
            used += size
            items.append(
                DeliveryItem(
                    index=index,
                    kind=kind,
                    attribution=DeliveryAttribution(
                        notebook_id=notebook_id,
                        source_id=authorized.source_id,
                        document_id=occurrence.document_id,
                        version_id=occurrence.version_id,
                        asset_id=occurrence.asset_id,
                        occurrence_id=occurrence_id,
                        derivation_id=derivation_id,
                        modality="ocr" if kind == "derived_ocr" else "vision",
                        authority=kind,
                        generation_id=getattr(result, "generation_id", None),
                    ),
                    payload=payload,
                    byte_size=size,
                )
            )
        snapshot = _snapshot(
            "analysis", notebook_id, occurrence_id, *(str(item[1]) for item in results)
        )
        completeness = _aggregate_delivery_completeness(item[2] for item in results)
        if analysis_bounded and completeness is DeliveryCompleteness.COMPLETE:
            completeness = DeliveryCompleteness.BOUNDED
        return DeliveryResponse(
            resource_kind=DeliveryResourceKind.ANALYSIS,
            snapshot_identity=snapshot,
            completeness=completeness,
            items=tuple(items),
            usage=DeliveryUsage(items=len(items), bytes=used),
            omissions=("analysis_item_bounds_applied",) if analysis_bounded else (),
        )

    async def get_final_qa_evidence(
        self,
        *,
        notebook_id: UUID,
        assistant_turn_id: UUID,
        cursor: str | None = None,
    ) -> DeliveryResponse:
        """Deliver an immutable published V2 result without invoking retrieval or a model."""
        if not isinstance(self._storage, FinalQAExecutionStoreV2):
            raise NotFoundError("Final-QA V2 delivery is unavailable")
        execution = await self._storage.get_final_qa_v2_execution(assistant_turn_id)
        if execution is None:
            raise NotFoundError("Final-QA V2 execution was not found")
        if execution.notebook_id != notebook_id:
            raise DeliveryAuthorizationError("Final-QA V2 execution is outside notebook scope")
        snapshot = await self._storage.get_final_qa_v2_snapshot(
            execution.execution_id, FinalQAExecutionSnapshotPhase.PUBLISHED
        )
        if snapshot is None:
            raise NotFoundError("published Final-QA V2 snapshot was not found")
        published = decode_published_v2_snapshot(snapshot.payload)
        snapshot_identity = _snapshot("final-qa-v2", execution.execution_id, snapshot.payload_hash)
        fingerprint = _fingerprint(
            "final-qa-v2",
            notebook_id,
            assistant_turn_id,
            self._limits.max_items,
            self._limits.max_response_bytes,
        )
        offset = self._decode_cursor(cursor, snapshot_identity, fingerprint)
        source_by_number = {citation.source_number: citation for citation in published.citations}
        context_items = published.context_result.items
        _validate_cursor_offset(offset, len(context_items), cursor)
        selected = context_items[offset : offset + self._limits.max_items]
        items: list[DeliveryItem] = []
        used = 0
        for index, context_item in enumerate(selected, start=offset):
            candidate = context_item.candidate
            if candidate.notebook_id != notebook_id:
                raise IntegrityError("published evidence escaped execution notebook scope")
            citation = source_by_number.get(context_item.source_number)
            payload = {
                "source_number": context_item.source_number,
                "candidate": _json_value(candidate),
                "citation": None if citation is None else _json_value(citation),
                "completeness": published.context_result.completeness.value,
            }
            size = len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
            if items and used + size > self._limits.max_response_bytes:
                break
            if size > self._limits.max_response_bytes:
                raise DeliveryLimitExceededError("one evidence item exceeds response byte limit")
            items.append(
                DeliveryItem(
                    index=index,
                    kind=candidate.kind.value,
                    attribution=DeliveryAttribution(
                        notebook_id=notebook_id,
                        source_id=candidate.source_id,
                        document_id=candidate.document_id,
                        version_id=candidate.version_id,
                        asset_id=candidate.asset_id,
                        occurrence_id=candidate.occurrence_id,
                        derivation_id=candidate.derivation_id,
                        generation_id=candidate.generation_id,
                        modality=candidate.kind.value,
                        authority=candidate.authority.value,
                    ),
                    payload=payload,
                    byte_size=size,
                )
            )
            used += size
        next_offset = offset + len(items)
        truncated = next_offset < len(context_items)
        delivered_completeness = (
            DeliveryCompleteness.TRUNCATED
            if truncated
            else _delivery_completeness(published.context_result.completeness)
        )
        return DeliveryResponse(
            resource_kind=DeliveryResourceKind.MULTIMODAL_EVIDENCE,
            snapshot_identity=snapshot_identity,
            completeness=delivered_completeness,
            items=tuple(items),
            usage=DeliveryUsage(items=len(items), bytes=used),
            omissions=("evidence_delivery_bound",) if truncated else (),
            next_cursor=(
                self._encode_cursor(snapshot_identity, fingerprint, next_offset)
                if truncated
                else None
            ),
        )

    async def _authorize_version(self, request: DeliveryRequest) -> _AuthorizedVersion:
        if await self._storage.get_notebook(request.notebook_id) is None:
            raise NotFoundError("notebook was not found")
        source_id: UUID | None = None
        cursor: str | None = None
        while True:
            page = await self._storage.list_sources(request.notebook_id, 100, cursor)
            for source in page.items:
                if source.document_id == request.document_id:
                    source_id = source.source_id
                    break
            if source_id is not None or page.next_cursor is None:
                break
            cursor = page.next_cursor
        if source_id is None:
            raise DeliveryAuthorizationError("document is not available in notebook scope")
        document = await self._storage.get_document(request.document_id)
        if document is None:
            raise NotFoundError("document was not found")
        version = next(
            (item for item in document.versions if item.version_id == request.version_id), None
        )
        if version is None:
            raise NotFoundError("exact document version was not found")
        return _AuthorizedVersion(source_id=source_id, content_hash=version.content_hash)

    def _encode_cursor(self, snapshot: str, fingerprint: str, offset: int) -> str:
        return self._encode_bound_cursor(
            domain="mnemo-delivery-cursor/v2",
            snapshot=snapshot,
            binding={"request_fingerprint": fingerprint},
            position=offset,
            limits={},
        )

    def _encode_bound_cursor(
        self,
        *,
        domain: str,
        snapshot: str,
        binding: dict[str, object],
        position: int,
        limits: dict[str, object],
    ) -> str:
        return self._cursor_codec.encode(
            domain=domain,
            snapshot_identity=snapshot,
            binding=binding,
            position={"offset": position},
            limits=limits,
        )

    def _decode_bound_cursor(
        self,
        cursor: str | None,
        *,
        domain: str,
        snapshot: str,
        binding: dict[str, object],
        limits: dict[str, object],
    ) -> int:
        if cursor is None:
            return 0
        try:
            state = self._cursor_codec.decode(
                cursor,
                expected_domain=domain,
                expected_binding=binding,
                expected_snapshot_identity=snapshot,
                expected_limits=limits,
            )
            offset = state.position.get("offset")
            if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
                raise CursorInvalidError("cursor offset is invalid")
            return offset
        except CursorExpiredError as error:
            raise DeliveryCursorExpiredError(
                "continuation cursor expired; restart the traversal"
            ) from error
        except (CursorConflictError, CursorKeyUnavailableError) as error:
            raise DeliveryCursorConflictError(
                "continuation cursor conflicts with this traversal; restart it"
            ) from error
        except CursorInvalidError as error:
            raise DeliveryCursorError("continuation cursor is invalid") from error

    def _decode_cursor(self, cursor: str | None, snapshot: str, fingerprint: str) -> int:
        if cursor is None:
            return 0
        if cursor.startswith("mnc2."):
            try:
                state = self._cursor_codec.decode(
                    cursor,
                    expected_domain="mnemo-delivery-cursor/v2",
                    expected_binding={"request_fingerprint": fingerprint},
                    expected_snapshot_identity=snapshot,
                    expected_limits={},
                )
                offset = state.position.get("offset")
                if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
                    raise CursorInvalidError("cursor offset is invalid")
                return offset
            except CursorExpiredError as error:
                raise DeliveryCursorExpiredError(
                    "continuation cursor expired; restart the traversal"
                ) from error
            except (CursorConflictError, CursorKeyUnavailableError) as error:
                raise DeliveryCursorConflictError(
                    "continuation cursor conflicts with this traversal; restart it"
                ) from error
            except CursorInvalidError as error:
                raise DeliveryCursorError("continuation cursor is invalid") from error
        if self._clock() >= self._legacy_cursor_deadline:
            raise DeliveryCursorExpiredError(
                "legacy continuation cursor overlap ended; restart the traversal"
            )
        try:
            raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            payload, signature = raw[:-32], raw[-32:]
            expected = hmac.new(self._cursor_secret, payload, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("signature")
            value = json.loads(payload)
            if value != {
                "v": 1,
                "snapshot": snapshot,
                "request": fingerprint,
                "offset": value.get("offset"),
            }:
                raise ValueError("scope")
            offset = value["offset"]
            if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
                raise ValueError("offset")
            return cast(int, offset)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            raise DeliveryCursorError("continuation cursor is invalid or stale") from error


def _cap(name: str, available: bool) -> DeliveryCapability:
    return DeliveryCapability(
        name=name,
        state=(
            DeliveryCapabilityState.SUPPORTED if available else DeliveryCapabilityState.UNAVAILABLE
        ),
    )


def _unavailable_analysis(notebook_id: UUID, occurrence_id: UUID, reason: str) -> DeliveryResponse:
    return DeliveryResponse(
        resource_kind=DeliveryResourceKind.ANALYSIS,
        snapshot_identity=_snapshot("analysis-unavailable", notebook_id, occurrence_id, reason),
        completeness=DeliveryCompleteness.UNAVAILABLE,
        items=(),
        usage=DeliveryUsage(items=0, bytes=0),
        omissions=(reason,),
    )


def _snapshot(domain: str, *values: object) -> str:
    return hashlib.sha256(
        json.dumps([domain, *(str(value) for value in values)], separators=(",", ":")).encode()
    ).hexdigest()


def _fingerprint(domain: str, *values: object) -> str:
    return _snapshot(f"request:{domain}", *values)


def _validate_cursor_offset(offset: int, total: int, cursor: str | None) -> None:
    if cursor is not None and offset >= total:
        raise DeliveryCursorConflictError(
            "continuation cursor is at or beyond traversal completion; restart the traversal"
        )


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            _json_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def _verify_asset(
    content: bytes, expected_hash: str, expected_size: int, expected_mime: str, actual_mime: str
) -> None:
    if len(content) != expected_size:
        raise IntegrityError("asset byte length does not match retained metadata")
    if hashlib.sha256(content).hexdigest() != expected_hash:
        raise IntegrityError("asset SHA-256 verification failed")
    if expected_mime != actual_mime:
        raise IntegrityError("asset MIME metadata does not match retained reference")


def _occurrence_payload(occurrence: AssetOccurrence, asset: Asset) -> dict[str, object]:
    value = _json_value(occurrence)
    assert isinstance(value, dict)
    value["asset"] = {
        "asset_id": str(asset.asset_id),
        "mime_type": asset.mime_type,
        "content_hash": asset.content_hash,
        "width": asset.width,
        "height": asset.height,
    }
    return value


def _delivery_completeness(value: object) -> DeliveryCompleteness:
    raw = getattr(value, "value", value)
    try:
        return DeliveryCompleteness(str(raw))
    except ValueError:
        return DeliveryCompleteness.UNKNOWN


def _aggregate_delivery_completeness(results: Iterable[object]) -> DeliveryCompleteness:
    states = {
        _delivery_completeness(getattr(result, "completeness", "unknown")) for result in results
    }
    for state in (
        DeliveryCompleteness.FAILED,
        DeliveryCompleteness.UNAVAILABLE,
        DeliveryCompleteness.PARTIAL,
        DeliveryCompleteness.BOUNDED,
        DeliveryCompleteness.UNKNOWN,
    ):
        if state in states:
            return state
    return DeliveryCompleteness.COMPLETE


def _bounded_analysis_payload(
    result: object, limits: DeliveryLimits
) -> tuple[dict[str, object], bool]:
    value = _json_value(result)
    assert isinstance(value, dict)
    bounded = False
    if "regions" in value and isinstance(value["regions"], list):
        bounded = bounded or len(value["regions"]) > limits.max_ocr_regions
        value["regions"] = value["regions"][: limits.max_ocr_regions]
    if "observations" in value and isinstance(value["observations"], list):
        bounded = bounded or len(value["observations"]) > limits.max_vision_observations
        value["observations"] = value["observations"][: limits.max_vision_observations]
    return value, bounded


def _json_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, FrozenMetadata):
        return {str(key): _json_value(item) for key, item in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, bytes):
        raise TypeError("binary bytes cannot be embedded in JSON delivery")
    return value
