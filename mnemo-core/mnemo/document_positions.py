"""Deterministic in-memory exact-version positional selection for WP-05."""

from __future__ import annotations

from dataclasses import dataclass

from mnemo.interfaces.errors import ConflictError, ContractValidationError
from mnemo.models.blocks import Block, HeadingBlock, TextBlock
from mnemo.models.chunks import Chunk
from mnemo.models.delivery import (
    AdjacentAnchorKind,
    AdjacentSelector,
    BlockRangeSelector,
    ChunkRangeSelector,
    DocumentSelectorV2,
    FromEndSelector,
    FromEndUnit,
    FullDocumentSelector,
    PageRangeSelector,
    SectionSelector,
    SheetRangeSelector,
    SlideRangeSelector,
)
from mnemo.models.documents import DocType, ParsedDocument


@dataclass(frozen=True, slots=True)
class ExactDocumentUnit:
    kind: str
    physical_index: int
    value: Block | Chunk
    heading_path: tuple[str, ...] = ()
    sheet_name: str | None = None


@dataclass(frozen=True, slots=True)
class ExactSelection:
    units: tuple[ExactDocumentUnit, ...]
    available: bool = True
    reason: str | None = None


class ExactDocumentPositionIndex:
    """Resolve selectors without semantic search, ranking, or fabricated positions."""

    def __init__(self, parsed: ParsedDocument, chunks: tuple[Chunk, ...]) -> None:
        self._parsed = parsed
        self._blocks = parsed.blocks
        self._chunks = tuple(
            sorted(
                chunks,
                key=lambda item: (
                    item.source_span.start_ordinal,
                    item.source_span.end_ordinal,
                    item.position.section_index,
                    item.position.chunk_index_in_section,
                    item.id,
                ),
            )
        )
        self._heading_paths = _heading_paths(self._blocks)
        self._sheet_names, self._sheet_by_ordinal = _sheet_index(parsed)

    @property
    def chunks(self) -> tuple[Chunk, ...]:
        return self._chunks

    def select(self, selector: DocumentSelectorV2) -> ExactSelection:
        if isinstance(selector, FullDocumentSelector):
            return ExactSelection(self._block_units(range(len(self._blocks))))
        if isinstance(selector, PageRangeSelector):
            return self._page_range(selector.start, selector.end, slides=False)
        if isinstance(selector, SlideRangeSelector):
            return self._page_range(selector.start, selector.end, slides=True)
        if isinstance(selector, SheetRangeSelector):
            return self._sheet_range(selector.start, selector.end)
        if isinstance(selector, BlockRangeSelector):
            _validate_range(selector.start, selector.end, len(self._blocks), "block")
            return ExactSelection(self._block_units(range(selector.start, selector.end + 1)))
        if isinstance(selector, ChunkRangeSelector):
            _validate_range(selector.start, selector.end, len(self._chunks), "chunk")
            return ExactSelection(self._chunk_units(range(selector.start, selector.end + 1)))
        if isinstance(selector, SectionSelector):
            return self._section(selector.heading_path)
        if isinstance(selector, FromEndSelector):
            return self._from_end(selector)
        if isinstance(selector, AdjacentSelector):
            return self._adjacent(selector)
        raise TypeError("unsupported DocumentSelectorV2")

    def overlapping_chunks(self, block_ordinal: int) -> tuple[str, ...]:
        return tuple(
            chunk.id
            for chunk in self._chunks
            if chunk.source_span.start_ordinal <= block_ordinal <= chunk.source_span.end_ordinal
        )

    def _page_range(self, start: int, end: int, *, slides: bool) -> ExactSelection:
        if slides and self._parsed.doc_type is not DocType.SLIDES:
            return ExactSelection((), available=False, reason="slide_positions_unavailable")
        pages = tuple(
            dict.fromkeys(
                block.page_number for block in self._blocks if block.page_number is not None
            )
        )
        if not pages:
            reason = "slide_positions_unavailable" if slides else "page_positions_unavailable"
            return ExactSelection((), available=False, reason=reason)
        declared = (
            self._parsed.metadata.metadata.get("slides_count")
            if slides
            else self._parsed.metadata.page_count
        )
        maximum = declared if isinstance(declared, int) else max(pages)
        if end > maximum:
            raise ContractValidationError(
                f"requested {'slide' if slides else 'page'} range exceeds exact document bounds"
            )
        indexes = (
            index
            for index, block in enumerate(self._blocks)
            if block.page_number is not None and start <= block.page_number <= end
        )
        return ExactSelection(self._block_units(indexes))

    def _sheet_range(self, start: int, end: int) -> ExactSelection:
        if not self._sheet_names:
            return ExactSelection((), available=False, reason="sheet_positions_unavailable")
        if end > len(self._sheet_names):
            raise ContractValidationError("requested sheet range exceeds exact document bounds")
        selected_names = frozenset(self._sheet_names[start - 1 : end])
        indexes = tuple(
            index
            for index in range(len(self._blocks))
            if self._sheet_by_ordinal.get(index) in selected_names
        )
        return ExactSelection(self._block_units(indexes))

    def _section(self, heading_path: tuple[str, ...]) -> ExactSelection:
        headings = [
            index
            for index, block in enumerate(self._blocks)
            if isinstance(block, HeadingBlock) and self._heading_paths[index] == heading_path
        ]
        if not any(isinstance(block, HeadingBlock) for block in self._blocks):
            return ExactSelection((), available=False, reason="section_hierarchy_unavailable")
        if not headings:
            return ExactSelection(())
        if len(headings) > 1:
            raise ConflictError("section heading path is ambiguous in the exact document version")
        start = headings[0]
        heading = self._blocks[start]
        assert isinstance(heading, HeadingBlock)
        end = len(self._blocks)
        for index in range(start + 1, len(self._blocks)):
            candidate = self._blocks[index]
            if isinstance(candidate, HeadingBlock) and candidate.level <= heading.level:
                end = index
                break
        return ExactSelection(self._block_units(range(start, end)))

    def _from_end(self, selector: FromEndSelector) -> ExactSelection:
        unit = selector.unit
        if unit in {FromEndUnit.PAGE, FromEndUnit.SLIDE}:
            if unit is FromEndUnit.SLIDE and self._parsed.doc_type is not DocType.SLIDES:
                return ExactSelection((), available=False, reason="slide_positions_unavailable")
            pages = tuple(
                dict.fromkeys(
                    block.page_number for block in self._blocks if block.page_number is not None
                )
            )
            if not pages:
                reason = (
                    "slide_positions_unavailable"
                    if unit is FromEndUnit.SLIDE
                    else "page_positions_unavailable"
                )
                return ExactSelection((), available=False, reason=reason)
            chosen = frozenset(pages[-selector.count :])
            return ExactSelection(
                self._block_units(
                    index for index, block in enumerate(self._blocks) if block.page_number in chosen
                )
            )
        if unit is FromEndUnit.SHEET:
            if not self._sheet_names:
                return ExactSelection((), available=False, reason="sheet_positions_unavailable")
            start = max(1, len(self._sheet_names) - selector.count + 1)
            return self._sheet_range(start, len(self._sheet_names))
        if unit is FromEndUnit.BLOCK:
            start = max(0, len(self._blocks) - selector.count)
            return ExactSelection(self._block_units(range(start, len(self._blocks))))
        if unit is FromEndUnit.CHUNK:
            start = max(0, len(self._chunks) - selector.count)
            return ExactSelection(self._chunk_units(range(start, len(self._chunks))))
        if unit is FromEndUnit.PARAGRAPH:
            indexes = [
                index for index, block in enumerate(self._blocks) if isinstance(block, TextBlock)
            ]
            return ExactSelection(self._block_units(indexes[-selector.count :]))
        headings = [
            index for index, block in enumerate(self._blocks) if isinstance(block, HeadingBlock)
        ]
        if not headings:
            return ExactSelection((), available=False, reason="section_hierarchy_unavailable")
        start = headings[max(0, len(headings) - selector.count)]
        return ExactSelection(self._block_units(range(start, len(self._blocks))))

    def _adjacent(self, selector: AdjacentSelector) -> ExactSelection:
        if selector.anchor_kind is AdjacentAnchorKind.BLOCK:
            assert selector.block_ordinal is not None
            anchor = selector.block_ordinal
            if anchor >= len(self._blocks):
                raise ContractValidationError("adjacent block anchor is outside document bounds")
            indexes = _adjacent_indexes(
                anchor, len(self._blocks), selector.before, selector.after, selector.include_anchor
            )
            return ExactSelection(self._block_units(indexes))
        assert selector.chunk_id is not None
        matches = [
            index for index, chunk in enumerate(self._chunks) if chunk.id == selector.chunk_id
        ]
        if not matches:
            raise ContractValidationError("adjacent chunk anchor is outside the exact version")
        indexes = _adjacent_indexes(
            matches[0], len(self._chunks), selector.before, selector.after, selector.include_anchor
        )
        return ExactSelection(self._chunk_units(indexes))

    def _block_units(self, indexes) -> tuple[ExactDocumentUnit, ...]:  # type: ignore[no-untyped-def]
        return tuple(
            ExactDocumentUnit(
                kind="block",
                physical_index=index,
                value=self._blocks[index],
                heading_path=self._heading_paths[index],
                sheet_name=self._sheet_by_ordinal.get(index),
            )
            for index in indexes
        )

    def _chunk_units(self, indexes) -> tuple[ExactDocumentUnit, ...]:  # type: ignore[no-untyped-def]
        return tuple(
            ExactDocumentUnit(kind="chunk", physical_index=index, value=self._chunks[index])
            for index in indexes
        )


def _heading_paths(blocks: tuple[Block, ...]) -> tuple[tuple[str, ...], ...]:
    stack: list[tuple[int, str]] = []
    result: list[tuple[str, ...]] = []
    for block in blocks:
        if isinstance(block, HeadingBlock):
            while stack and stack[-1][0] >= block.level:
                stack.pop()
            stack.append((block.level, block.text))
        result.append(tuple(value for _, value in stack))
    return tuple(result)


def _sheet_index(parsed: ParsedDocument) -> tuple[tuple[str, ...], dict[int, str]]:
    raw_names = parsed.metadata.metadata.get("sheet_names")
    if not isinstance(raw_names, (tuple, list)) or any(
        not isinstance(name, str) or not name for name in raw_names
    ):
        return (), {}
    names = tuple(name for name in raw_names if isinstance(name, str))
    heading_indexes: list[int] = []
    search_from = 0
    for name in names:
        match = None
        for index in range(search_from, len(parsed.blocks)):
            candidate = parsed.blocks[index]
            if (
                isinstance(candidate, HeadingBlock)
                and candidate.level == 1
                and candidate.text == name
            ):
                match = index
                break
        if match is None:
            return (), {}
        heading_indexes.append(match)
        search_from = match + 1
    mapping: dict[int, str] = {}
    for sheet_index, (name, start) in enumerate(zip(names, heading_indexes, strict=True)):
        end = (
            heading_indexes[sheet_index + 1] if sheet_index + 1 < len(names) else len(parsed.blocks)
        )
        for ordinal in range(start, end):
            mapping[ordinal] = name
    for ordinal, block in enumerate(parsed.blocks):
        metadata_name = block.metadata.get("parser.asset.sheet_name") or block.metadata.get(
            "sheet_name"
        )
        if isinstance(metadata_name, str) and metadata_name in names:
            mapping[ordinal] = metadata_name
    return names, mapping


def _validate_range(start: int, end: int, total: int, label: str) -> None:
    if start >= total or end >= total:
        raise ContractValidationError(f"requested {label} range exceeds exact document bounds")


def _adjacent_indexes(
    anchor: int, total: int, before: int, after: int, include_anchor: bool
) -> tuple[int, ...]:
    start = max(0, anchor - before)
    end = min(total, anchor + after + 1)
    return tuple(index for index in range(start, end) if include_anchor or index != anchor)
