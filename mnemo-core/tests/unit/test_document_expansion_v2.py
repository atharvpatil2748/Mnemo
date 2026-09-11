"""Focused WP-05 exact and positional document expansion tests."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from mnemo.delivery import BoundedDocumentExpansionService
from mnemo.document_positions import ExactDocumentPositionIndex
from mnemo.interfaces import (
    AssetCatalogStoreV1,
    ConflictError,
    ContractValidationError,
    DeliveryCursorConflictError,
    DeliveryCursorError,
    Page,
    StorageInterfaceV1,
)
from mnemo.models import (
    AdjacentAnchorKind,
    AdjacentSelector,
    BlockRangeSelector,
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkRangeSelector,
    ChunkType,
    DeliveryCompleteness,
    DeliveryLimits,
    DocType,
    Document,
    DocumentExpansionRequestV2,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    FromEndSelector,
    FromEndUnit,
    FrozenMetadata,
    FullDocumentSelector,
    HeadingBlock,
    ImageBlock,
    Notebook,
    PageRangeSelector,
    ParsedDocument,
    SectionSelector,
    SheetRangeSelector,
    SlideRangeSelector,
    Source,
    TextBlock,
)


def _chunk(document_id, version_id, index: int, start: int, end: int) -> Chunk:  # type: ignore[no-untyped-def]
    return Chunk(
        id=hashlib.sha256(f"chunk-{index}".encode()).hexdigest(),
        text=f"chunk {index}",
        document_id=document_id,
        version_id=version_id,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=index),
        source_span=BlockSpan(start_ordinal=start, end_ordinal=end),
        heading_path=(),
    )


def _parsed(doc_type: DocType = DocType.GENERIC) -> ParsedDocument:
    digest = "a" * 64
    return ParsedDocument(
        blocks=(
            HeadingBlock(ordinal=0, text="Intro", level=1, page_number=1),
            TextBlock(ordinal=1, text="नमस्ते", page_number=1, language="hi"),
            HeadingBlock(ordinal=2, text="Details", level=1, page_number=2),
            TextBlock(ordinal=3, text="मराठी", page_number=2, language="mr"),
            ImageBlock(ordinal=4, asset_id=uuid4(), page_number=3, alt_text="diagram"),
        ),
        metadata=DocumentMetadata(content_hash=digest, title="Exact", page_count=3),
        language="mul",
        doc_type=doc_type,
    )


def test_selector_index_is_deterministic_and_positional() -> None:
    document_id, version_id = uuid4(), uuid4()
    chunks = (
        _chunk(document_id, version_id, 1, 2, 4),
        _chunk(document_id, version_id, 0, 0, 1),
    )
    index = ExactDocumentPositionIndex(_parsed(), chunks)

    assert [unit.physical_index for unit in index.select(FullDocumentSelector()).units] == list(
        range(5)
    )
    assert [
        unit.physical_index for unit in index.select(PageRangeSelector(start=2, end=3)).units
    ] == [
        2,
        3,
        4,
    ]
    assert [
        unit.physical_index for unit in index.select(BlockRangeSelector(start=1, end=3)).units
    ] == [1, 2, 3]
    assert [
        unit.physical_index for unit in index.select(ChunkRangeSelector(start=0, end=1)).units
    ] == [0, 1]
    assert [
        unit.physical_index
        for unit in index.select(SectionSelector(heading_path=("Details",))).units
    ] == [2, 3, 4]
    assert index.overlapping_chunks(3) == (chunks[0].id,)


def test_from_end_and_adjacent_obey_physical_boundaries() -> None:
    document_id, version_id = uuid4(), uuid4()
    chunks = tuple(_chunk(document_id, version_id, index, index, index) for index in range(5))
    index = ExactDocumentPositionIndex(_parsed(), chunks)

    final_page = index.select(FromEndSelector(unit=FromEndUnit.PAGE))
    assert [unit.physical_index for unit in final_page.units] == [4]
    final_paragraph = index.select(FromEndSelector(unit=FromEndUnit.PARAGRAPH))
    assert [unit.physical_index for unit in final_paragraph.units] == [3]
    first = index.select(
        AdjacentSelector(
            anchor_kind=AdjacentAnchorKind.BLOCK,
            block_ordinal=0,
            before=3,
            after=1,
        )
    )
    assert [unit.physical_index for unit in first.units] == [0, 1]
    last = index.select(
        AdjacentSelector(
            anchor_kind=AdjacentAnchorKind.CHUNK,
            chunk_id=chunks[-1].id,
            before=1,
            after=4,
        )
    )
    assert [unit.physical_index for unit in last.units] == [3, 4]


def test_unavailable_positions_are_not_fabricated() -> None:
    parsed = ParsedDocument(
        blocks=(TextBlock(ordinal=0, text="plain"),),
        metadata=DocumentMetadata(content_hash="b" * 64),
        language="en",
        doc_type=DocType.GENERIC,
    )
    index = ExactDocumentPositionIndex(parsed, ())
    assert index.select(PageRangeSelector(start=1, end=1)).available is False
    assert index.select(SlideRangeSelector(start=1, end=1)).available is False
    assert index.select(SheetRangeSelector(start=1, end=1)).available is False


def test_position_index_covers_exact_selector_boundaries_and_metadata() -> None:
    document_id, version_id = uuid4(), uuid4()
    chunks = tuple(_chunk(document_id, version_id, item, item, item) for item in range(5))

    slides = replace(
        _parsed(DocType.SLIDES),
        metadata=replace(_parsed().metadata, metadata=FrozenMetadata({"slides_count": 3})),
    )
    slide_index = ExactDocumentPositionIndex(slides, chunks)
    selected = slide_index.select(SlideRangeSelector(start=2, end=3))
    assert [unit.physical_index for unit in selected.units] == [2, 3, 4]
    with pytest.raises(ContractValidationError, match="slide range"):
        slide_index.select(SlideRangeSelector(start=1, end=4))
    with pytest.raises(ContractValidationError, match="page range"):
        slide_index.select(PageRangeSelector(start=1, end=4))
    with pytest.raises(ContractValidationError, match="block range"):
        slide_index.select(BlockRangeSelector(start=0, end=5))
    with pytest.raises(ContractValidationError, match="chunk range"):
        slide_index.select(ChunkRangeSelector(start=0, end=5))

    sheets = ParsedDocument(
        blocks=(
            HeadingBlock(ordinal=0, text="Sheet A", level=1),
            TextBlock(ordinal=1, text="one"),
            HeadingBlock(ordinal=2, text="Sheet B", level=1),
            TextBlock(
                ordinal=3,
                text="two",
                metadata=FrozenMetadata({"sheet_name": "Sheet A"}),
            ),
        ),
        metadata=DocumentMetadata(
            content_hash="c" * 64,
            metadata=FrozenMetadata({"sheet_names": ("Sheet A", "Sheet B")}),
        ),
        language="en",
        doc_type=DocType.GENERIC,
    )
    sheet_index = ExactDocumentPositionIndex(sheets, ())
    selection = sheet_index.select(SheetRangeSelector(start=1, end=1))
    assert [unit.physical_index for unit in selection.units] == [0, 1, 3]
    assert all(unit.sheet_name == "Sheet A" for unit in selection.units)
    final_sheet = sheet_index.select(FromEndSelector(unit=FromEndUnit.SHEET))
    assert [unit.physical_index for unit in final_sheet.units] == [2]
    with pytest.raises(ContractValidationError, match="sheet range"):
        sheet_index.select(SheetRangeSelector(start=1, end=3))

    expected = {
        FromEndUnit.SLIDE: (2, [2, 3, 4]),
        FromEndUnit.BLOCK: (2, [3, 4]),
        FromEndUnit.CHUNK: (2, [3, 4]),
        FromEndUnit.SECTION: (1, [2, 3, 4]),
    }
    for unit, (count, physical_indexes) in expected.items():
        selected = slide_index.select(FromEndSelector(unit=unit, count=count))
        assert [item.physical_index for item in selected.units] == physical_indexes

    without_anchor = slide_index.select(
        AdjacentSelector(
            anchor_kind=AdjacentAnchorKind.BLOCK,
            block_ordinal=2,
            before=1,
            after=1,
            include_anchor=False,
        )
    )
    assert [unit.physical_index for unit in without_anchor.units] == [1, 3]
    with pytest.raises(ContractValidationError, match="block anchor"):
        slide_index.select(AdjacentSelector(anchor_kind=AdjacentAnchorKind.BLOCK, block_ordinal=9))
    with pytest.raises(ContractValidationError, match="chunk anchor"):
        slide_index.select(
            AdjacentSelector(anchor_kind=AdjacentAnchorKind.CHUNK, chunk_id="f" * 64)
        )


def test_position_index_section_conflicts_and_invalid_sheet_metadata() -> None:
    duplicate = ParsedDocument(
        blocks=(
            HeadingBlock(ordinal=0, text="Same", level=1),
            TextBlock(ordinal=1, text="first"),
            HeadingBlock(ordinal=2, text="Same", level=1),
            TextBlock(ordinal=3, text="second"),
        ),
        metadata=DocumentMetadata(
            content_hash="d" * 64,
            metadata=FrozenMetadata({"sheet_names": ("missing",)}),
        ),
        language="en",
        doc_type=DocType.GENERIC,
    )
    index = ExactDocumentPositionIndex(duplicate, ())
    with pytest.raises(ConflictError, match="ambiguous"):
        index.select(SectionSelector(heading_path=("Same",)))
    assert index.select(SectionSelector(heading_path=("Absent",))).units == ()
    assert index.select(SheetRangeSelector(start=1, end=1)).reason == "sheet_positions_unavailable"
    with pytest.raises(TypeError, match="unsupported"):
        index.select(object())  # type: ignore[arg-type]


def _service_fixture():  # type: ignore[no-untyped-def]
    now = datetime(2026, 8, 27, tzinfo=UTC)
    notebook_id, document_id, version_id, source_id = uuid4(), uuid4(), uuid4(), uuid4()
    parsed = _parsed()
    digest = parsed.metadata.content_hash
    version = DocumentVersion(
        version_id=version_id,
        document_id=document_id,
        content_hash=digest,
        metadata=parsed.metadata,
        status=DocumentVersionStatus.CURRENT,
        created_at=now,
    )
    storage = MagicMock(spec=StorageInterfaceV1)
    storage.get_notebook = AsyncMock(
        return_value=Notebook(
            notebook_id=notebook_id,
            title="N",
            description=None,
            created_at=now,
            updated_at=now,
        )
    )
    storage.list_sources = AsyncMock(
        return_value=Page(
            items=(
                Source(
                    source_id=source_id,
                    notebook_id=notebook_id,
                    document_id=document_id,
                    created_at=now,
                ),
            ),
            next_cursor=None,
        )
    )
    storage.get_document = AsyncMock(
        return_value=Document(
            document_id=document_id,
            versions=(version,),
            current_version_id=version_id,
            current_hash=digest,
            status=DocumentStatus.INDEXED,
            created_at=now,
            updated_at=now,
        )
    )
    storage.get_parsed_document = AsyncMock(return_value=parsed)
    chunks = tuple(_chunk(document_id, version_id, index, index, index) for index in range(5))
    reader = MagicMock()
    reader.list_exact_document_chunks = AsyncMock(return_value=chunks)
    catalog = MagicMock(spec=AssetCatalogStoreV1)
    service = BoundedDocumentExpansionService(
        storage=storage,
        catalog=catalog,
        exact_reader=reader,
        limits=DeliveryLimits(max_items=2, max_response_bytes=100_000),
        cursor_secret=b"0123456789abcdef",
    )
    values = {
        "notebook_id": notebook_id,
        "document_id": document_id,
        "version_id": version_id,
        "storage": storage,
    }
    return service, values


@pytest.mark.anyio
async def test_full_selector_continues_to_terminal_complete() -> None:
    service, values = _service_fixture()
    request = DocumentExpansionRequestV2(
        notebook_id=values["notebook_id"],
        document_id=values["document_id"],
        version_id=values["version_id"],
        selector=FullDocumentSelector(),
        max_items=2,
    )
    first = await service.expand_document_v2(request)
    assert first.completeness is DeliveryCompleteness.TRUNCATED
    assert first.next_cursor is not None
    middle = await service.expand_document_v2(
        DocumentExpansionRequestV2(
            notebook_id=request.notebook_id,
            document_id=request.document_id,
            version_id=request.version_id,
            selector=request.selector,
            cursor=first.next_cursor,
            max_items=2,
        )
    )
    final = await service.expand_document_v2(
        DocumentExpansionRequestV2(
            notebook_id=request.notebook_id,
            document_id=request.document_id,
            version_id=request.version_id,
            selector=request.selector,
            cursor=middle.next_cursor,
            max_items=2,
        )
    )
    assert final.completeness is DeliveryCompleteness.COMPLETE
    assert final.next_cursor is None
    assert [item.index for item in first.items + middle.items + final.items] == list(range(5))


@pytest.mark.anyio
async def test_cursor_is_bound_to_selector_limits_scope_and_snapshot() -> None:
    service, values = _service_fixture()
    base = DocumentExpansionRequestV2(
        notebook_id=values["notebook_id"],
        document_id=values["document_id"],
        version_id=values["version_id"],
        selector=FullDocumentSelector(),
        max_items=2,
    )
    cursor = (await service.expand_document_v2(base)).next_cursor
    assert cursor is not None
    with pytest.raises(DeliveryCursorConflictError):
        await service.expand_document_v2(
            DocumentExpansionRequestV2(
                notebook_id=base.notebook_id,
                document_id=base.document_id,
                version_id=base.version_id,
                selector=BlockRangeSelector(start=0, end=4),
                cursor=cursor,
                max_items=2,
            )
        )
    with pytest.raises(DeliveryCursorConflictError):
        await service.expand_document_v2(
            DocumentExpansionRequestV2(
                notebook_id=base.notebook_id,
                document_id=base.document_id,
                version_id=base.version_id,
                selector=base.selector,
                cursor=cursor,
                max_items=1,
            )
        )
    with pytest.raises(DeliveryCursorError):
        await service.expand_document_v2(
            DocumentExpansionRequestV2(
                notebook_id=base.notebook_id,
                document_id=base.document_id,
                version_id=base.version_id,
                selector=base.selector,
                cursor=f"{cursor}x",
                max_items=2,
            )
        )

    values["storage"].get_parsed_document.return_value = ParsedDocument(
        blocks=(TextBlock(ordinal=0, text="mutated immutable snapshot"),),
        metadata=DocumentMetadata(content_hash="a" * 64),
        language="en",
        doc_type=DocType.GENERIC,
    )
    with pytest.raises(DeliveryCursorConflictError):
        await service.expand_document_v2(
            DocumentExpansionRequestV2(
                notebook_id=base.notebook_id,
                document_id=base.document_id,
                version_id=base.version_id,
                selector=base.selector,
                cursor=cursor,
                max_items=2,
            )
        )


@pytest.mark.anyio
async def test_empty_and_unavailable_are_distinct() -> None:
    service, values = _service_fixture()
    empty = await service.expand_document_v2(
        DocumentExpansionRequestV2(
            notebook_id=values["notebook_id"],
            document_id=values["document_id"],
            version_id=values["version_id"],
            selector=SectionSelector(heading_path=("Missing",)),
        )
    )
    assert empty.completeness is DeliveryCompleteness.EMPTY
    values["storage"].get_parsed_document.return_value = ParsedDocument(
        blocks=(TextBlock(ordinal=0, text="no physical page"),),
        metadata=DocumentMetadata(content_hash="a" * 64),
        language="en",
        doc_type=DocType.GENERIC,
    )
    unavailable = await service.expand_document_v2(
        DocumentExpansionRequestV2(
            notebook_id=values["notebook_id"],
            document_id=values["document_id"],
            version_id=values["version_id"],
            selector=PageRangeSelector(start=1, end=1),
        )
    )
    assert unavailable.completeness is DeliveryCompleteness.UNAVAILABLE


def test_selector_contract_rejects_invalid_ranges_and_anchors() -> None:
    with pytest.raises(ValueError):
        PageRangeSelector(start=2, end=1)
    with pytest.raises(ValueError):
        AdjacentSelector(
            anchor_kind=AdjacentAnchorKind.BLOCK,
            block_ordinal=None,
            chunk_id="a" * 64,
        )
    index = ExactDocumentPositionIndex(_parsed(), ())
    with pytest.raises(ContractValidationError):
        index.select(BlockRangeSelector(start=0, end=99))
