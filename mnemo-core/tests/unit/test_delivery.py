"""Phase 8.5.10 bounded delivery, provenance, and security tests."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from mnemo.cursors import CursorCodecV2, CursorSigningKeyV2
from mnemo.delivery import BoundedDocumentExpansionService
from mnemo.interfaces import (
    AssetCatalogStoreV1,
    ContractValidationError,
    DeliveryAuthorizationError,
    DeliveryCursorError,
    DeliveryCursorExpiredError,
    DeliveryLimitExceededError,
    IntegrityError,
    NotFoundError,
    Page,
    StorageInterfaceV1,
)
from mnemo.models import (
    Asset,
    AssetAnalysisModality,
    AssetAnalysisSelection,
    AssetAnalysisSelector,
    AssetContainerKind,
    AssetDerivationDescriptor,
    AssetExtractionProvenance,
    AssetLocator,
    AssetLocatorKind,
    AssetOccurrence,
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    DeliveryCompleteness,
    DeliveryLimits,
    DeliveryRequest,
    DeliveryView,
    DocType,
    Document,
    DocumentBinaryReference,
    DocumentBinaryRole,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    Notebook,
    ParsedDocument,
    Source,
    TextBlock,
    asset_occurrence_id,
)


@dataclass(frozen=True)
class _DerivedResult:
    occurrence_id: UUID
    generation_id: UUID
    regions: tuple[dict[str, object], ...] = ({"text": "derived"},)
    completeness: str = "complete"


@dataclass(frozen=True)
class _VisionDerivedResult:
    occurrence_id: UUID
    generation_id: UUID
    observations: tuple[dict[str, object], ...] = ({"kind": "chart"},)
    completeness: str = "complete"


@dataclass(frozen=True)
class _Kind:
    value: str


@dataclass(frozen=True)
class _Candidate:
    candidate_id: UUID
    notebook_id: UUID
    source_id: UUID
    document_id: UUID
    version_id: UUID
    kind: _Kind
    authority: _Kind
    asset_id: UUID | None = None
    occurrence_id: UUID | None = None
    derivation_id: UUID | None = None
    generation_id: UUID | None = None


@dataclass(frozen=True)
class _ContextItem:
    source_number: int
    candidate: _Candidate


@dataclass(frozen=True)
class _ContextResult:
    items: tuple[_ContextItem, ...]
    completeness: _Kind


@dataclass(frozen=True)
class _Citation:
    source_number: int


@dataclass(frozen=True)
class _Published:
    context_result: _ContextResult
    citations: tuple[_Citation, ...]


def _fixture() -> tuple[BoundedDocumentExpansionService, MagicMock, MagicMock, dict[str, object]]:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    notebook_id, document_id, version_id, source_id = uuid4(), uuid4(), uuid4(), uuid4()
    raw = b"0123456789"
    digest = hashlib.sha256(raw).hexdigest()
    version = DocumentVersion(
        version_id=version_id,
        document_id=document_id,
        content_hash=digest,
        metadata=DocumentMetadata(content_hash=digest, title="Bounded document"),
        status=DocumentVersionStatus.CURRENT,
        created_at=now,
    )
    document = Document(
        document_id=document_id,
        versions=(version,),
        current_version_id=version_id,
        current_hash=digest,
        status=DocumentStatus.INDEXED,
        created_at=now,
        updated_at=now,
    )
    notebook = Notebook(
        notebook_id=notebook_id,
        title="N",
        description=None,
        created_at=now,
        updated_at=now,
    )
    source = Source(
        source_id=source_id,
        notebook_id=notebook_id,
        document_id=document_id,
        created_at=now,
    )
    parsed = ParsedDocument(
        blocks=(
            TextBlock(ordinal=0, text="first", page_number=1),
            TextBlock(ordinal=1, text="second", page_number=2),
        ),
        metadata=version.metadata,
        language="en",
        doc_type=DocType.GENERIC,
    )
    original = Asset(
        asset_id=uuid4(),
        mime_type="application/pdf",
        content_hash=digest,
        storage_uri="blob://opaque",
    )
    reference = DocumentBinaryReference(
        document_id=document_id,
        version_id=version_id,
        asset_id=original.asset_id,
        role=DocumentBinaryRole.ORIGINAL,
        media_type=original.mime_type,
        byte_size=len(raw),
        created_at=now,
    )
    image_raw = b"\x89PNG\r\n\x1a\nimage"
    image = Asset(
        asset_id=uuid4(),
        mime_type="image/png",
        content_hash=hashlib.sha256(image_raw).hexdigest(),
        storage_uri="blob://image",
        width=2,
        height=3,
    )
    locator = AssetLocator(kind=AssetLocatorKind.PDF_PAGE, ordinal=0, page_number=1)
    occurrence = AssetOccurrence(
        occurrence_id=asset_occurrence_id(
            document_id=document_id,
            version_id=version_id,
            asset_id=image.asset_id,
            locator=locator,
        ),
        asset_id=image.asset_id,
        document_id=document_id,
        version_id=version_id,
        container_kind=AssetContainerKind.PDF,
        locator=locator,
        authored_alt_text="Chart",
        extraction_provenance=AssetExtractionProvenance(parser_id="test.pdf", parser_version="1"),
        created_at=now,
    )
    chunk = Chunk(
        id="c" * 64,
        text="canonical text",
        document_id=document_id,
        version_id=version_id,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0, page_number=1),
        source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
        heading_path=(),
    )

    storage = MagicMock(spec=StorageInterfaceV1)
    storage.get_notebook = AsyncMock(return_value=notebook)
    storage.list_sources = AsyncMock(return_value=Page(items=(source,), next_cursor=None))
    storage.get_document = AsyncMock(return_value=document)
    storage.get_parsed_document = AsyncMock(return_value=parsed)
    storage.get_chunk = AsyncMock(return_value=chunk)
    storage.get_asset = AsyncMock(
        side_effect=lambda asset_id: raw if asset_id == original.asset_id else image_raw
    )
    catalog = MagicMock(spec=AssetCatalogStoreV1)
    catalog.get_document_binary_reference = AsyncMock(return_value=reference)
    catalog.get_asset_record = AsyncMock(
        side_effect=lambda asset_id: original if asset_id == original.asset_id else image
    )
    catalog.list_asset_occurrences = AsyncMock(return_value=(occurrence,))
    catalog.get_authorized_asset_occurrence = AsyncMock(return_value=occurrence)
    service = BoundedDocumentExpansionService(
        storage=storage,
        catalog=catalog,
        limits=DeliveryLimits(
            max_document_bytes=4,
            max_asset_bytes=1024,
            max_assets=1,
            max_response_bytes=4096,
            max_items=1,
        ),
        cursor_secret=b"0123456789abcdef",
    )
    return (
        service,
        storage,
        catalog,
        {
            "notebook_id": notebook_id,
            "document_id": document_id,
            "version_id": version_id,
            "occurrence": occurrence,
            "chunk": chunk,
            "raw": raw,
        },
    )


@pytest.mark.anyio
async def test_bounded_document_cursor_and_original_integrity() -> None:
    service, storage, catalog, values = _fixture()
    request = DeliveryRequest(
        notebook_id=values["notebook_id"],
        document_id=values["document_id"],
        version_id=values["version_id"],
        max_items=1,
    )
    first = await service.expand_document(request)
    assert first.completeness is DeliveryCompleteness.TRUNCATED
    assert first.items[0].payload["text"] == "first"
    second = await service.expand_document(
        DeliveryRequest(
            notebook_id=request.notebook_id,
            document_id=request.document_id,
            version_id=request.version_id,
            cursor=first.next_cursor,
            max_items=1,
        )
    )
    assert second.completeness is DeliveryCompleteness.COMPLETE
    assert second.items[0].payload["text"] == "second"
    storage.get_parsed_document.return_value = ParsedDocument(
        blocks=(
            TextBlock(ordinal=0, text="changed", page_number=1),
            TextBlock(ordinal=1, text="second", page_number=2),
        ),
        metadata=storage.get_parsed_document.return_value.metadata,
        language="en",
        doc_type=DocType.GENERIC,
    )
    with pytest.raises(DeliveryCursorError):
        await service.expand_document(
            DeliveryRequest(
                notebook_id=request.notebook_id,
                document_id=request.document_id,
                version_id=request.version_id,
                cursor=first.next_cursor,
                max_items=1,
            )
        )
    with pytest.raises(DeliveryCursorError):
        await service.expand_document(
            DeliveryRequest(
                notebook_id=request.notebook_id,
                document_id=request.document_id,
                version_id=request.version_id,
                cursor=f"{first.next_cursor}x",
            )
        )

    original = await service.get_original_document(
        DeliveryRequest(
            notebook_id=request.notebook_id,
            document_id=request.document_id,
            version_id=request.version_id,
            view=DeliveryView.ORIGINAL,
        )
    )
    assert original.content == b"0123"
    assert original.next_cursor is not None
    remainder = await service.get_original_document(
        DeliveryRequest(
            notebook_id=request.notebook_id,
            document_id=request.document_id,
            version_id=request.version_id,
            view=DeliveryView.ORIGINAL,
            cursor=original.next_cursor,
            max_bytes=20,
        )
    )
    assert remainder.content == b"4567"
    assert remainder.completeness is DeliveryCompleteness.TRUNCATED
    catalog.get_asset_record.side_effect = None
    catalog.get_asset_record.return_value = None
    with pytest.raises(NotFoundError):
        await service.get_original_document(
            DeliveryRequest(
                notebook_id=request.notebook_id,
                document_id=request.document_id,
                version_id=request.version_id,
                view=DeliveryView.ORIGINAL,
            )
        )


@pytest.mark.anyio
async def test_delivery_cursor_expiry_scope_bounds_and_legacy_overlap() -> None:
    _, storage, catalog, values = _fixture()
    current = [datetime(2026, 8, 27, tzinfo=UTC)]

    def clock() -> datetime:
        return current[0]

    codec = CursorCodecV2(
        CursorSigningKeyV2("delivery-current", b"d" * 32),
        ttl=timedelta(seconds=30),
        clock=clock,
    )
    service = BoundedDocumentExpansionService(
        storage=storage,
        catalog=catalog,
        limits=DeliveryLimits(max_items=1, max_response_bytes=4096),
        cursor_secret=b"0123456789abcdef",
        cursor_codec=codec,
        legacy_cursor_overlap=timedelta(seconds=60),
        clock=clock,
    )
    request = DeliveryRequest(
        notebook_id=values["notebook_id"],
        document_id=values["document_id"],
        version_id=values["version_id"],
        max_items=1,
    )
    first = await service.expand_document(request)
    assert first.next_cursor is not None and first.next_cursor.startswith("mnc2.")
    first_encoded = first.next_cursor.split(".")[2]
    first_payload = json.loads(
        base64.urlsafe_b64decode(first_encoded + "=" * (-len(first_encoded) % 4))
    )
    for invalid_offset in (2, 3):
        terminal_cursor = codec.encode(
            domain="mnemo-delivery-cursor/v2",
            snapshot_identity=first_payload["snapshot_identity"],
            binding=first_payload["binding"],
            position={"offset": invalid_offset},
            limits={},
            now=current[0],
        )
        with pytest.raises(DeliveryCursorError, match="completion"):
            await service.expand_document(replace(request, cursor=terminal_cursor))
    with pytest.raises(DeliveryCursorError, match="conflicts"):
        await service.expand_document(replace(request, cursor=first.next_cursor, max_bytes=100))
    current[0] += timedelta(seconds=30)
    with pytest.raises(DeliveryCursorExpiredError, match="restart"):
        await service.expand_document(replace(request, cursor=first.next_cursor))

    current[0] -= timedelta(seconds=30)
    encoded = first.next_cursor.split(".")[2]
    v2_payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    snapshot = v2_payload["snapshot_identity"]
    # A v1 cursor remains decodable only during the explicit deployment overlap.
    fingerprint = v2_payload["binding"]["request_fingerprint"]
    payload = json.dumps(
        {"v": 1, "snapshot": snapshot, "request": fingerprint, "offset": 1},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(b"0123456789abcdef", payload, hashlib.sha256).digest()
    legacy = base64.urlsafe_b64encode(payload + signature).decode().rstrip("=")
    assert (
        await service.expand_document(replace(request, cursor=legacy))
    ).completeness is DeliveryCompleteness.COMPLETE
    current[0] += timedelta(seconds=60)
    with pytest.raises(DeliveryCursorExpiredError, match="legacy"):
        await service.expand_document(replace(request, cursor=legacy))


@pytest.mark.anyio
@pytest.mark.parametrize("blocks", [(), (TextBlock(ordinal=0, text="only", page_number=1),)])
async def test_document_boundary_empty_and_single_block_are_complete(blocks) -> None:  # type: ignore[no-untyped-def]
    service, storage, _, values = _fixture()
    parsed = await storage.get_parsed_document(values["version_id"])
    storage.get_parsed_document.return_value = replace(parsed, blocks=blocks)
    result = await service.expand_document(
        DeliveryRequest(
            notebook_id=values["notebook_id"],
            document_id=values["document_id"],
            version_id=values["version_id"],
        )
    )
    assert result.completeness is DeliveryCompleteness.COMPLETE
    assert result.next_cursor is None
    assert len(result.items) == len(blocks)


@pytest.mark.anyio
async def test_asset_inventory_binary_chunk_and_cross_scope() -> None:
    service, storage, catalog, values = _fixture()
    inventory = await service.list_assets(
        notebook_id=values["notebook_id"],
        document_id=values["document_id"],
        version_id=values["version_id"],
    )
    occurrence = values["occurrence"]
    assert inventory.items[0].attribution.occurrence_id == occurrence.occurrence_id
    assert inventory.items[0].payload["asset"]["mime_type"] == "image/png"
    binary = await service.get_asset(
        notebook_id=values["notebook_id"], occurrence_id=occurrence.occurrence_id
    )
    assert binary.content.startswith(b"\x89PNG")
    assert binary.attribution.document_id == values["document_id"]
    bounded_binary = await service.get_asset(
        notebook_id=values["notebook_id"],
        occurrence_id=occurrence.occurrence_id,
        max_bytes=4,
    )
    assert bounded_binary.completeness is DeliveryCompleteness.TRUNCATED
    assert bounded_binary.next_cursor is not None
    with pytest.raises(DeliveryCursorError):
        await service.get_asset(
            notebook_id=values["notebook_id"],
            occurrence_id=occurrence.occurrence_id,
            cursor=bounded_binary.next_cursor,
            max_bytes=5,
        )
    chunk = await service.get_document_chunk(
        notebook_id=values["notebook_id"],
        document_id=values["document_id"],
        version_id=values["version_id"],
        chunk_id=values["chunk"].id,
    )
    assert chunk.items[0].payload["text"] == "canonical text"

    catalog.get_authorized_asset_occurrence.return_value = None
    with pytest.raises(DeliveryAuthorizationError):
        await service.get_asset(notebook_id=uuid4(), occurrence_id=occurrence.occurrence_id)
    storage.list_sources.return_value = Page(items=(), next_cursor=None)
    with pytest.raises(DeliveryAuthorizationError):
        await service.expand_document(
            DeliveryRequest(
                notebook_id=values["notebook_id"],
                document_id=values["document_id"],
                version_id=values["version_id"],
            )
        )


@pytest.mark.anyio
async def test_shared_asset_occurrences_traverse_with_count_bound_and_cursor() -> None:
    service, _, catalog, values = _fixture()
    first = values["occurrence"]
    second_locator = AssetLocator(kind=AssetLocatorKind.PDF_PAGE, ordinal=1, page_number=2)
    second = replace(
        first,
        occurrence_id=asset_occurrence_id(
            document_id=first.document_id,
            version_id=first.version_id,
            asset_id=first.asset_id,
            locator=second_locator,
        ),
        locator=second_locator,
    )
    catalog.list_asset_occurrences.return_value = (first, second)
    first_page = await service.list_assets(
        notebook_id=values["notebook_id"],
        document_id=values["document_id"],
        version_id=values["version_id"],
    )
    assert first_page.completeness is DeliveryCompleteness.TRUNCATED
    assert first_page.omissions == ("asset_count_bound",)
    assert first_page.items[0].attribution.asset_id == first.asset_id
    assert first_page.items[0].attribution.occurrence_id == first.occurrence_id
    second_page = await service.list_assets(
        notebook_id=values["notebook_id"],
        document_id=values["document_id"],
        version_id=values["version_id"],
        cursor=first_page.next_cursor,
    )
    assert second_page.completeness is DeliveryCompleteness.COMPLETE
    assert second_page.next_cursor is None
    assert second_page.items[0].attribution.asset_id == first.asset_id
    assert second_page.items[0].attribution.occurrence_id == second.occurrence_id


@pytest.mark.anyio
async def test_analysis_is_derived_bounded_and_occurrence_authorized() -> None:
    service, storage, catalog, values = _fixture()
    occurrence = values["occurrence"]
    derivation_id = uuid4()
    for name in (
        "put_ocr_result",
        "get_authorized_ocr_result_by_cache_key",
        "project_ocr_result",
        "list_ocr_projection_regions",
    ):
        setattr(storage, name, AsyncMock())
    storage.get_authorized_ocr_result = AsyncMock(
        return_value=_DerivedResult(occurrence_id=occurrence.occurrence_id, generation_id=uuid4())
    )
    result = await service.get_image_analysis(
        notebook_id=values["notebook_id"],
        occurrence_id=occurrence.occurrence_id,
        ocr_derivation_id=derivation_id,
    )
    assert result.items[0].kind == "derived_ocr"
    assert result.items[0].attribution.authority == "derived_ocr"
    assert result.items[0].attribution.derivation_id == derivation_id
    storage.get_authorized_ocr_result.return_value = _DerivedResult(
        occurrence_id=occurrence.occurrence_id,
        generation_id=uuid4(),
        completeness="partial",
    )
    partial = await service.get_image_analysis(
        notebook_id=values["notebook_id"],
        occurrence_id=occurrence.occurrence_id,
        ocr_derivation_id=derivation_id,
    )
    assert partial.completeness is DeliveryCompleteness.PARTIAL
    storage.get_authorized_ocr_result.return_value = _DerivedResult(
        occurrence_id=occurrence.occurrence_id,
        generation_id=uuid4(),
        regions=({"text": "one"}, {"text": "two"}),
    )
    bounded_service = BoundedDocumentExpansionService(
        storage=storage,
        catalog=catalog,
        limits=DeliveryLimits(max_ocr_regions=1),
    )
    bounded = await bounded_service.get_image_analysis(
        notebook_id=values["notebook_id"],
        occurrence_id=occurrence.occurrence_id,
        ocr_derivation_id=derivation_id,
    )
    assert bounded.completeness is DeliveryCompleteness.BOUNDED
    assert bounded.omissions == ("analysis_item_bounds_applied",)
    assert len(bounded.items[0].payload["regions"]) == 1
    storage.get_authorized_ocr_result.return_value = _DerivedResult(
        occurrence_id=uuid4(), generation_id=uuid4()
    )
    with pytest.raises(DeliveryAuthorizationError):
        await service.get_image_analysis(
            notebook_id=values["notebook_id"],
            occurrence_id=occurrence.occurrence_id,
            ocr_derivation_id=derivation_id,
        )


def test_capability_advertisement_and_model_invariants() -> None:
    service, _, _, _ = _fixture()
    capabilities = {item.name: item.state.value for item in service.capabilities()}
    assert capabilities["original_document_delivery"] == "supported"
    assert capabilities["binary_resources"] == "supported"
    assert capabilities["visual_embeddings"] == "unvalidated"
    with pytest.raises(ValueError):
        DeliveryLimits(max_document_bytes=0)
    with pytest.raises(ValueError, match="non-analysis"):
        AssetAnalysisSelector(
            selection=AssetAnalysisSelection.ALL,
            modalities=(AssetAnalysisModality.OTHER,),
        )
    with pytest.raises(ValueError):
        BoundedDocumentExpansionService(
            storage=MagicMock(spec=StorageInterfaceV1),
            catalog=MagicMock(spec=AssetCatalogStoreV1),
            cursor_secret=b"short",
        )


@pytest.mark.anyio
async def test_final_qa_v2_delivery_replays_immutable_snapshot_without_generation() -> None:
    service, storage, _, values = _fixture()
    execution_id, assistant_turn_id = uuid4(), uuid4()
    execution = MagicMock(
        execution_id=execution_id,
        notebook_id=values["notebook_id"],
    )
    payload = "immutable-published-payload"
    snapshot = MagicMock(
        payload=payload,
        payload_hash=hashlib.sha256(payload.encode()).hexdigest(),
    )
    for name in (
        "create_final_qa_v2_execution",
        "put_final_qa_v2_snapshot",
        "transition_final_qa_v2_execution",
        "put_final_qa_v2_citations",
    ):
        setattr(storage, name, AsyncMock())
    storage.get_final_qa_v2_execution = AsyncMock(return_value=execution)
    storage.get_final_qa_v2_snapshot = AsyncMock(return_value=snapshot)
    candidate = _Candidate(
        candidate_id=uuid4(),
        notebook_id=values["notebook_id"],
        source_id=uuid4(),
        document_id=values["document_id"],
        version_id=values["version_id"],
        kind=_Kind("ocr_region"),
        authority=_Kind("derived"),
        occurrence_id=values["occurrence"].occurrence_id,
        derivation_id=uuid4(),
    )
    published = _Published(
        context_result=_ContextResult(
            items=(_ContextItem(source_number=1, candidate=candidate),),
            completeness=_Kind("complete"),
        ),
        citations=(_Citation(source_number=1),),
    )
    with patch("mnemo.delivery.decode_published_v2_snapshot", return_value=published):
        result = await service.get_final_qa_evidence(
            notebook_id=values["notebook_id"], assistant_turn_id=assistant_turn_id
        )
    assert result.items[0].kind == "ocr_region"
    assert result.items[0].attribution.authority == "derived"
    assert result.items[0].payload["citation"]["source_number"] == 1
    storage.get_final_qa_v2_execution.assert_awaited_once_with(assistant_turn_id)
    assert not hasattr(storage, "generate")

    partial_published = _Published(
        context_result=_ContextResult(
            items=(_ContextItem(source_number=1, candidate=candidate),),
            completeness=_Kind("partial"),
        ),
        citations=(_Citation(source_number=1),),
    )
    with patch("mnemo.delivery.decode_published_v2_snapshot", return_value=partial_published):
        partial = await service.get_final_qa_evidence(
            notebook_id=values["notebook_id"], assistant_turn_id=assistant_turn_id
        )
    assert partial.completeness is DeliveryCompleteness.PARTIAL

    execution.notebook_id = uuid4()
    with pytest.raises(DeliveryAuthorizationError):
        await service.get_final_qa_evidence(
            notebook_id=values["notebook_id"], assistant_turn_id=assistant_turn_id
        )


@pytest.mark.anyio
async def test_delivery_fail_closed_integrity_and_missing_resource_boundaries() -> None:
    service, storage, catalog, values = _fixture()
    request = DeliveryRequest(
        notebook_id=values["notebook_id"],
        document_id=values["document_id"],
        version_id=values["version_id"],
    )
    with pytest.raises(TypeError):
        BoundedDocumentExpansionService(storage=object(), catalog=catalog)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        BoundedDocumentExpansionService(storage=storage, catalog=object())  # type: ignore[arg-type]
    with pytest.raises(ContractValidationError):
        await service.expand_document(
            DeliveryRequest(
                notebook_id=request.notebook_id,
                document_id=request.document_id,
                version_id=request.version_id,
                view=DeliveryView.ORIGINAL,
            )
        )
    parsed = await storage.get_parsed_document(request.version_id)
    storage.get_parsed_document.return_value = None
    with pytest.raises(NotFoundError):
        await service.expand_document(request)
    storage.get_parsed_document.return_value = parsed
    tiny = BoundedDocumentExpansionService(
        storage=storage,
        catalog=catalog,
        limits=DeliveryLimits(max_response_bytes=1),
    )
    with pytest.raises(DeliveryLimitExceededError):
        await tiny.expand_document(request)
    with pytest.raises(ContractValidationError):
        await service.get_original_document(request)

    reference = await catalog.get_document_binary_reference(request.version_id)
    catalog.get_document_binary_reference.side_effect = None
    catalog.get_document_binary_reference.return_value = None
    with pytest.raises(NotFoundError):
        await service.get_original_document(
            DeliveryRequest(
                notebook_id=request.notebook_id,
                document_id=request.document_id,
                version_id=request.version_id,
                view=DeliveryView.ORIGINAL,
            )
        )
    catalog.get_document_binary_reference.return_value = reference
    original_asset = await catalog.get_asset_record(reference.asset_id)
    catalog.get_asset_record.side_effect = None
    catalog.get_asset_record.return_value = original_asset
    storage.get_asset.return_value = b"tampered"
    storage.get_asset.side_effect = None
    with pytest.raises(IntegrityError):
        await service.get_original_document(
            DeliveryRequest(
                notebook_id=request.notebook_id,
                document_id=request.document_id,
                version_id=request.version_id,
                view=DeliveryView.ORIGINAL,
            )
        )

    storage.get_chunk.return_value = None
    storage.get_chunk.side_effect = None
    with pytest.raises(NotFoundError):
        await service.get_document_chunk(
            notebook_id=request.notebook_id,
            document_id=request.document_id,
            version_id=request.version_id,
            chunk_id="f" * 64,
        )
    occurrence = values["occurrence"]
    catalog.list_asset_occurrences.return_value = (
        occurrence,
        AssetOccurrence(
            occurrence_id=occurrence.occurrence_id,
            asset_id=occurrence.asset_id,
            document_id=uuid4(),
            version_id=occurrence.version_id,
            container_kind=occurrence.container_kind,
            locator=occurrence.locator,
            authored_alt_text=occurrence.authored_alt_text,
            extraction_provenance=occurrence.extraction_provenance,
            created_at=occurrence.created_at,
        ),
    )
    with pytest.raises(IntegrityError):
        await service.list_assets(
            notebook_id=request.notebook_id,
            document_id=request.document_id,
            version_id=request.version_id,
        )
    catalog.get_authorized_asset_occurrence.return_value = occurrence
    catalog.get_asset_record.return_value = None
    storage.get_asset.return_value = None
    with pytest.raises(NotFoundError):
        await service.get_asset(
            notebook_id=request.notebook_id, occurrence_id=occurrence.occurrence_id
        )
    with pytest.raises(ContractValidationError):
        await service.get_image_analysis(
            notebook_id=request.notebook_id, occurrence_id=occurrence.occurrence_id
        )


@pytest.mark.anyio
async def test_vision_delivery_and_authorization_lookup_failures() -> None:
    service, storage, catalog, values = _fixture()
    occurrence = values["occurrence"]
    for name in (
        "put_vision_result",
        "get_authorized_vision_result_by_cache_key",
        "put_visual_embedding",
        "get_authorized_visual_embedding",
        "get_authorized_visual_embedding_by_cache_key",
        "project_visual_embedding",
        "list_visual_projection_derivations",
    ):
        setattr(storage, name, AsyncMock())
    derivation_id = uuid4()
    storage.get_authorized_vision_result = AsyncMock(
        return_value=_VisionDerivedResult(
            occurrence_id=occurrence.occurrence_id, generation_id=uuid4()
        )
    )
    result = await service.get_image_analysis(
        notebook_id=values["notebook_id"],
        occurrence_id=occurrence.occurrence_id,
        vision_derivation_id=derivation_id,
    )
    assert result.items[0].kind == "derived_vision"
    assert result.items[0].payload["observations"] == [{"kind": "chart"}]

    storage.get_notebook.return_value = None
    with pytest.raises(NotFoundError):
        await service.expand_document(
            DeliveryRequest(
                notebook_id=values["notebook_id"],
                document_id=values["document_id"],
                version_id=values["version_id"],
            )
        )
    storage.get_notebook.return_value = MagicMock()
    storage.list_sources.return_value = Page(items=(), next_cursor=None)
    with pytest.raises(DeliveryAuthorizationError):
        await service.expand_document(
            DeliveryRequest(
                notebook_id=values["notebook_id"],
                document_id=values["document_id"],
                version_id=values["version_id"],
            )
        )
    catalog.get_authorized_asset_occurrence.return_value = None
    with pytest.raises(DeliveryAuthorizationError):
        await service.get_image_analysis(
            notebook_id=values["notebook_id"],
            occurrence_id=occurrence.occurrence_id,
            vision_derivation_id=derivation_id,
        )


@pytest.mark.anyio
async def test_derivation_aware_inventory_and_latest_ready_analysis() -> None:
    service, storage, catalog, values = _fixture()
    occurrence = values["occurrence"]
    now = datetime(2026, 8, 27, tzinfo=UTC)
    older_id, latest_id, failed_id = uuid4(), uuid4(), uuid4()

    def descriptor(derivation_id, *, status="succeeded", result=True, minute=0):  # type: ignore[no-untyped-def]
        return AssetDerivationDescriptor(
            derivation_id=derivation_id,
            occurrence_id=occurrence.occurrence_id,
            modality=AssetAnalysisModality.OCR,
            operation="ocr",
            provider_identity="test",
            model_identity="ocr-v1",
            configuration_digest="d" * 64,
            status=status,
            generation_id=uuid4(),
            generation_profile="default",
            generation_state="ready" if status == "succeeded" else "failed",
            result_available=result,
            confidence=0.9,
            language="hi",
            created_at=now + timedelta(minutes=minute),
            updated_at=now + timedelta(minutes=minute),
        )

    descriptors = (
        descriptor(older_id),
        descriptor(latest_id, minute=1),
        descriptor(failed_id, status="failed", result=False, minute=2),
    )
    catalog.list_authorized_asset_derivations = AsyncMock(return_value=descriptors)
    inventory = await service.list_assets(
        notebook_id=values["notebook_id"],
        document_id=values["document_id"],
        version_id=values["version_id"],
    )
    assert [item["derivation_id"] for item in inventory.items[0].payload["derivations"]] == [
        str(older_id),
        str(latest_id),
        str(failed_id),
    ]
    assert inventory.items[0].payload["derivations"][0]["language"] == "hi"
    assert inventory.items[0].payload["derivations"][0]["availability"] == "ready"
    assert inventory.items[0].payload["derivations"][2]["availability"] == "failed"

    for name in (
        "put_ocr_result",
        "get_authorized_ocr_result_by_cache_key",
        "project_ocr_result",
        "list_ocr_projection_regions",
    ):
        setattr(storage, name, AsyncMock())
    storage.get_authorized_ocr_result = AsyncMock(
        return_value=_DerivedResult(occurrence_id=occurrence.occurrence_id, generation_id=uuid4())
    )
    analysis = await service.get_image_analysis_v2(
        notebook_id=values["notebook_id"],
        occurrence_id=occurrence.occurrence_id,
        selector=AssetAnalysisSelector(
            selection=AssetAnalysisSelection.LATEST_READY,
            modalities=(AssetAnalysisModality.OCR, AssetAnalysisModality.VISION),
        ),
    )
    assert analysis.completeness is DeliveryCompleteness.PARTIAL
    assert analysis.omissions == ("analysis_modality_unavailable:vision",)
    assert analysis.items[0].attribution.derivation_id == latest_id
    storage.get_authorized_ocr_result.assert_awaited_once_with(
        notebook_id=values["notebook_id"], derivation_id=latest_id
    )


@pytest.mark.anyio
async def test_analysis_selection_reports_stale_or_missing_as_unavailable() -> None:
    service, _, catalog, values = _fixture()
    occurrence = values["occurrence"]
    now = datetime(2026, 8, 27, tzinfo=UTC)
    catalog.list_authorized_asset_derivations = AsyncMock(
        return_value=(
            AssetDerivationDescriptor(
                derivation_id=uuid4(),
                occurrence_id=occurrence.occurrence_id,
                modality=AssetAnalysisModality.VISION,
                operation="vision_analysis",
                provider_identity="test",
                model_identity="vision-v1",
                configuration_digest="e" * 64,
                status="succeeded",
                generation_id=uuid4(),
                generation_profile="default",
                generation_state="superseded",
                result_available=True,
                confidence=None,
                language="mr",
                created_at=now,
                updated_at=now,
            ),
        )
    )
    result = await service.get_image_analysis_v2(
        notebook_id=values["notebook_id"],
        occurrence_id=occurrence.occurrence_id,
        selector=AssetAnalysisSelector(
            selection=AssetAnalysisSelection.ALL,
            modalities=(AssetAnalysisModality.VISION,),
        ),
    )
    assert result.completeness is DeliveryCompleteness.UNAVAILABLE
    assert result.omissions == ("ready_analysis_unavailable",)
    assert catalog.list_authorized_asset_derivations.return_value[0].availability == "stale"


@pytest.mark.anyio
async def test_analysis_all_and_explicit_selection_are_authorized_and_deterministic() -> None:
    service, storage, catalog, values = _fixture()
    occurrence = values["occurrence"]
    now = datetime(2026, 8, 27, tzinfo=UTC)
    ocr_id, vision_id = uuid4(), uuid4()
    descriptors = tuple(
        AssetDerivationDescriptor(
            derivation_id=derivation_id,
            occurrence_id=occurrence.occurrence_id,
            modality=modality,
            operation=operation,
            provider_identity="test",
            model_identity=model,
            configuration_digest=digest * 64,
            status="succeeded",
            generation_id=uuid4(),
            generation_profile="production",
            generation_state="ready",
            result_available=True,
            confidence=0.8,
            language="en",
            created_at=now,
            updated_at=now,
        )
        for derivation_id, modality, operation, model, digest in (
            (ocr_id, AssetAnalysisModality.OCR, "ocr", "ocr-v1", "1"),
            (vision_id, AssetAnalysisModality.VISION, "vision_analysis", "vlm-v1", "2"),
        )
    )
    catalog.list_authorized_asset_derivations = AsyncMock(return_value=descriptors)
    for name in (
        "put_ocr_result",
        "get_authorized_ocr_result_by_cache_key",
        "project_ocr_result",
        "list_ocr_projection_regions",
        "put_vision_result",
        "get_authorized_vision_result_by_cache_key",
        "put_visual_embedding",
        "get_authorized_visual_embedding",
        "get_authorized_visual_embedding_by_cache_key",
        "project_visual_embedding",
        "list_visual_projection_derivations",
    ):
        setattr(storage, name, AsyncMock())
    storage.get_authorized_ocr_result = AsyncMock(
        return_value=_DerivedResult(occurrence_id=occurrence.occurrence_id, generation_id=uuid4())
    )
    storage.get_authorized_vision_result = AsyncMock(
        return_value=_VisionDerivedResult(
            occurrence_id=occurrence.occurrence_id, generation_id=uuid4()
        )
    )
    result = await service.get_image_analysis_v2(
        notebook_id=values["notebook_id"],
        occurrence_id=occurrence.occurrence_id,
        selector=AssetAnalysisSelector(
            selection=AssetAnalysisSelection.ALL,
            profile="production",
        ),
    )
    assert [item.attribution.derivation_id for item in result.items] == [ocr_id, vision_id]
    with pytest.raises(DeliveryAuthorizationError):
        await service.get_image_analysis_v2(
            notebook_id=values["notebook_id"],
            occurrence_id=occurrence.occurrence_id,
            selector=AssetAnalysisSelector(
                selection=AssetAnalysisSelection.EXPLICIT,
                derivation_ids=(uuid4(),),
            ),
        )


@pytest.mark.anyio
async def test_parent_ancestry_and_missing_final_qa_snapshot_paths() -> None:
    service, storage, _, values = _fixture()
    original = values["chunk"]
    parent = Chunk(
        id="f" * 64,
        text="parent text",
        document_id=values["document_id"],
        version_id=values["version_id"],
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0),
        source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
        heading_path=(),
    )
    child = Chunk(
        id="e" * 64,
        text=original.text,
        document_id=original.document_id,
        version_id=original.version_id,
        chunk_type=original.chunk_type,
        position=original.position,
        source_span=original.source_span,
        heading_path=original.heading_path,
        parent_chunk_id=parent.id,
    )
    storage.get_chunk.side_effect = lambda chunk_id: child if chunk_id == child.id else parent
    result = await service.get_document_chunk(
        notebook_id=values["notebook_id"],
        document_id=values["document_id"],
        version_id=values["version_id"],
        chunk_id=child.id,
    )
    assert result.items[0].payload["ancestry"] == [parent.id]

    for name in (
        "create_final_qa_v2_execution",
        "put_final_qa_v2_snapshot",
        "transition_final_qa_v2_execution",
        "put_final_qa_v2_citations",
    ):
        setattr(storage, name, AsyncMock())
    storage.get_final_qa_v2_execution = AsyncMock(return_value=None)
    storage.get_final_qa_v2_snapshot = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.get_final_qa_evidence(
            notebook_id=values["notebook_id"], assistant_turn_id=uuid4()
        )
    storage.get_final_qa_v2_execution.return_value = MagicMock(
        execution_id=uuid4(), notebook_id=values["notebook_id"]
    )
    with pytest.raises(NotFoundError):
        await service.get_final_qa_evidence(
            notebook_id=values["notebook_id"], assistant_turn_id=uuid4()
        )
