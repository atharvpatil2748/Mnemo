"""Deterministic Markdown-aware semantic chunking strategy."""

import logging
import re
from dataclasses import dataclass
from itertools import pairwise

from mnemo.interfaces import (
    ChunkerCapabilities,
    ChunkingContext,
    TokenCounterInterfaceV1,
    UnsupportedError,
)
from mnemo.models import (
    Block,
    BlockSpan,
    ChunkDraft,
    ChunkPosition,
    ChunkType,
    CodeBlock,
    DocType,
    FrozenMetadata,
    HeadingBlock,
    ImageBlock,
    ParsedDocument,
    TableBlock,
    TextBlock,
)

from .atomic_structures import render_table_part, split_exact_text, split_table_row

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_WORD_WITH_SPACE = re.compile(r"\S+(?:\s+|$)")
_TEXT_KINDS = frozenset({"paragraph", "paragraph_fragment", "list", "blockquote", "thematic_break"})
_LIST_ITEM_LINE = re.compile(r"^(?P<indent>[ \t]*)(?:[-+*]|\d+[.)])[ \t]+")
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Unit:
    text: str
    chunk_type: ChunkType
    source_span: BlockSpan
    heading_path: tuple[str, ...]
    section_index: int
    page_number: int | None
    kinds: tuple[str, ...]
    sources: tuple[str, ...] = ()
    links: tuple[FrozenMetadata, ...] = ()
    heading_links: tuple[FrozenMetadata, ...] = ()
    list_structure: FrozenMetadata | None = None
    table_structure: FrozenMetadata | None = None
    code_language: str | None = None
    subdivision: FrozenMetadata | None = None
    separator: str = "\n\n"
    mergeable: bool = True


class MarkdownChunker:
    """Chunk canonical Markdown using parser-preserved semantic metadata."""

    @property
    def supported_doc_types(self) -> tuple[DocType, ...]:
        """Return the sole document classification owned by this strategy."""
        return (DocType.MARKDOWN,)

    def capabilities(self) -> ChunkerCapabilities:
        """Describe the implemented Markdown strategy behavior."""
        return ChunkerCapabilities(
            supported_doc_types=self.supported_doc_types,
            preserves_semantic_boundaries=True,
            supports_parent_child=False,
            supports_overlap=False,
            metadata=FrozenMetadata({"chunker.markdown.version": "v1"}),
        )

    def chunk(
        self,
        document: ParsedDocument,
        context: ChunkingContext,
        token_counter: TokenCounterInterfaceV1,
    ) -> tuple[ChunkDraft, ...]:
        """Return ordered root drafts without reparsing Markdown source."""
        if not isinstance(document, ParsedDocument):
            raise TypeError("document must be ParsedDocument")
        if not isinstance(context, ChunkingContext):
            raise TypeError("context must be ChunkingContext")
        if not isinstance(token_counter, TokenCounterInterfaceV1):
            raise TypeError("token_counter must satisfy TokenCounterInterfaceV1")
        if document.doc_type is not DocType.MARKDOWN:
            raise UnsupportedError("MarkdownChunker supports only DocType.MARKDOWN")

        units = self._units(document, context, token_counter)
        packed = self._pack(
            units,
            context.options.target_tokens,
            context.effective_max_tokens,
            token_counter,
        )
        section_indexes: dict[int, int] = {}
        drafts: list[ChunkDraft] = []
        for unit in packed:
            chunk_index = section_indexes.get(unit.section_index, 0)
            section_indexes[unit.section_index] = chunk_index + 1
            drafts.append(
                ChunkDraft(
                    text=unit.text,
                    chunk_type=unit.chunk_type,
                    position=ChunkPosition(
                        section_index=unit.section_index,
                        chunk_index_in_section=chunk_index,
                        page_number=unit.page_number,
                    ),
                    heading_path=unit.heading_path,
                    source_span=unit.source_span,
                    parent_index=None,
                    metadata=self._draft_metadata(unit),
                )
            )
        return tuple(drafts)

    def _units(
        self,
        document: ParsedDocument,
        context: ChunkingContext,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit, ...]:
        result: list[_Unit] = []
        headings: list[str] = []
        heading_links: list[tuple[FrozenMetadata, ...]] = []
        section_index = 0
        for block in document.blocks:
            kind = self._kind(block)
            if isinstance(block, HeadingBlock):
                if kind != "heading":
                    raise UnsupportedError("Markdown heading metadata kind is inconsistent")
                self._source(block, required=True)
                headings = headings[: block.level - 1]
                heading_links = heading_links[: block.level - 1]
                headings.append(block.text)
                heading_links.append(self._links(block))
                section_index += 1
                continue
            if kind == "thematic_break":
                if not isinstance(block, TextBlock):
                    raise UnsupportedError("Markdown thematic break must be canonical text")
                self._source(block, required=True)
                section_index += 1
                continue
            result.extend(
                self._block_units(
                    block,
                    kind,
                    tuple(headings),
                    tuple(link for level_links in heading_links for link in level_links),
                    section_index,
                    context.options.target_tokens,
                    context.effective_max_tokens,
                    counter,
                )
            )
        return tuple(result)

    def _block_units(
        self,
        block: Block,
        kind: str,
        heading_path: tuple[str, ...],
        heading_links: tuple[FrozenMetadata, ...],
        section_index: int,
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit, ...]:
        span = BlockSpan(start_ordinal=block.ordinal, end_ordinal=block.ordinal)
        links = self._links(block)
        if isinstance(block, TableBlock):
            if kind != "table":
                raise UnsupportedError("Markdown table metadata kind is inconsistent")
            source = self._source(block, required=True)
            assert source is not None
            if counter.count(source) <= hard_max:
                return self._atomic(
                    source,
                    ChunkType.PASSAGE,
                    span,
                    heading_path,
                    section_index,
                    block,
                    kind,
                    counter,
                    hard_max,
                    sources=(source,),
                    links=links,
                    heading_links=heading_links,
                    table_structure=FrozenMetadata(
                        {"header_row_count": block.header_row_count, "rows": block.rows}
                    ),
                )
            return self._oversized_table_units(
                block,
                source,
                links,
                heading_links,
                span,
                heading_path,
                section_index,
                target,
                hard_max,
                counter,
            )
        if isinstance(block, CodeBlock):
            if kind != "code":
                raise UnsupportedError("Markdown code metadata kind is inconsistent")
            source = self._source(block, required=True)
            assert source is not None
            return self._atomic(
                block.code,
                ChunkType.CODE,
                span,
                heading_path,
                section_index,
                block,
                kind,
                counter,
                hard_max,
                sources=(source,),
                links=links,
                heading_links=heading_links,
                code_language=block.code_language,
            )
        if isinstance(block, ImageBlock):
            if kind != "inline_image":
                raise UnsupportedError("Markdown image metadata kind is inconsistent")
            if block.alt_text is None:
                return ()
            return self._atomic(
                block.alt_text,
                ChunkType.CAPTION,
                span,
                heading_path,
                section_index,
                block,
                kind,
                counter,
                hard_max,
                heading_links=heading_links,
            )
        if not isinstance(block, TextBlock) or kind not in _TEXT_KINDS:
            raise UnsupportedError(f"unsupported canonical Markdown block: {type(block).__name__}")
        if kind == "list":
            source = self._source(block, required=True)
            assert source is not None
            structure = self._list_structure(block)
            if counter.count(source) <= hard_max:
                return self._atomic(
                    source,
                    ChunkType.PASSAGE,
                    span,
                    heading_path,
                    section_index,
                    block,
                    kind,
                    counter,
                    hard_max,
                    sources=(source,),
                    links=links,
                    heading_links=heading_links,
                    list_structure=structure,
                )
            return self._oversized_list_units(
                block,
                source,
                structure,
                links,
                heading_links,
                span,
                heading_path,
                section_index,
                target,
                hard_max,
                counter,
            )
        if kind == "blockquote":
            source = self._source(block, required=True)
            assert source is not None
            return self._atomic(
                source,
                ChunkType.VERBATIM,
                span,
                heading_path,
                section_index,
                block,
                kind,
                counter,
                hard_max,
                sources=(source,),
                links=links,
                heading_links=heading_links,
            )
        if kind not in {"paragraph", "paragraph_fragment"}:
            raise UnsupportedError(f"unsupported Markdown text kind: {kind}")
        source = self._source(block, required=kind == "paragraph")
        return self._paragraph_units(
            block,
            kind,
            source,
            links,
            heading_links,
            span,
            heading_path,
            section_index,
            target,
            hard_max,
            counter,
        )

    def _oversized_list_units(
        self,
        block: TextBlock,
        source: str,
        structure: FrozenMetadata,
        links: tuple[FrozenMetadata, ...],
        heading_links: tuple[FrozenMetadata, ...],
        span: BlockSpan,
        heading_path: tuple[str, ...],
        section_index: int,
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit, ...]:
        source_items = _list_source_items(source)
        structure_items = structure["items"]
        assert isinstance(structure_items, tuple)
        item_groups = _list_structure_groups(structure_items)
        if len(source_items) != len(item_groups):
            raise UnsupportedError(
                "oversized Markdown list source and structured item boundaries disagree"
            )

        reserve = min(48, max(1, hard_max // 8))
        payload_target = max(1, target - reserve)
        payload_hard = max(1, hard_max - reserve)
        atomic_items: list[tuple[str, tuple[FrozenMetadata, ...], int, int]] = []
        for item_index, (item_source, item_structure) in enumerate(
            zip(source_items, item_groups, strict=True)
        ):
            pieces = split_exact_text(
                item_source,
                target=payload_target,
                hard_max=payload_hard,
                counter=counter,
                label="Markdown list item",
            )
            atomic_items.extend(
                (piece, item_structure, item_index, part_index)
                for part_index, piece in enumerate(pieces)
            )

        batches: list[tuple[str, tuple[FrozenMetadata, ...], int, int]] = []
        current_source = ""
        current_items: list[FrozenMetadata] = []
        current_start = 0
        current_end = 0
        for item_source, item_structure, item_index, _ in atomic_items:
            candidate = current_source + item_source
            if current_source and counter.count(candidate) > payload_target:
                batches.append((current_source, tuple(current_items), current_start, current_end))
                current_source = ""
                current_items = []
                current_start = item_index
            if not current_source:
                current_start = item_index
            current_source += item_source
            current_items.extend(item_structure)
            current_end = item_index
        if current_source:
            batches.append((current_source, tuple(current_items), current_start, current_end))
        if "".join(item[0] for item in batches) != source:
            raise AssertionError("Markdown list subdivision did not conserve exact source")

        _LOGGER.warning(
            "[CHUNKER] oversized atomic structure detected type=markdown_list "
            "block=%s tokens=%s limit=%s strategy=structure_aware_subdivision "
            "parts=%s content_conservation=PASS",
            block.ordinal,
            counter.count(source),
            hard_max,
            len(batches),
        )
        result: list[_Unit] = []
        for part_index, (body, items, start, end) in enumerate(batches):
            prefix = (
                f"Markdown list block {block.ordinal}, items {start + 1}-{end + 1}, "
                f"part {part_index + 1}/{len(batches)}\n"
            )
            text = prefix + body
            if counter.count(text) > hard_max:
                raise UnsupportedError(
                    "structure-aware Markdown list subdivision exceeds the token maximum"
                )
            list_values = dict(structure)
            list_values["items"] = items
            result.append(
                _Unit(
                    text=text,
                    chunk_type=ChunkType.PASSAGE,
                    source_span=span,
                    heading_path=heading_path,
                    section_index=section_index,
                    page_number=block.page_number,
                    kinds=("list",),
                    sources=(body,),
                    links=links,
                    heading_links=heading_links,
                    list_structure=FrozenMetadata(list_values),
                    mergeable=False,
                    subdivision=_subdivision_metadata(
                        "markdown_list", block.ordinal, part_index, len(batches)
                    ),
                )
            )
        return tuple(result)

    def _oversized_table_units(
        self,
        block: TableBlock,
        source: str,
        links: tuple[FrozenMetadata, ...],
        heading_links: tuple[FrozenMetadata, ...],
        span: BlockSpan,
        heading_path: tuple[str, ...],
        section_index: int,
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit, ...]:
        lines = source.splitlines(keepends=True)
        header_line_count = block.header_row_count + 1
        data_rows = block.rows[block.header_row_count :]
        if block.header_row_count < 1 or len(lines) != header_line_count + len(data_rows):
            raise UnsupportedError(
                "oversized Markdown table lacks deterministic row/source correspondence"
            )
        header_source = "".join(lines[:header_line_count])
        data_lines = tuple(lines[header_line_count:])
        reserve = min(48, max(1, hard_max // 8))
        payload_target = max(1, target - reserve)
        payload_hard = max(1, hard_max - reserve)

        batches: list[tuple[str, int, int]] = []
        current = ""
        current_start = 0
        for row_index, row_source in enumerate(data_lines):
            candidate = header_source + current + row_source
            if current and counter.count(candidate) > payload_target:
                batches.append((header_source + current, current_start, row_index - 1))
                current = ""
                current_start = row_index
                candidate = header_source + row_source
            if counter.count(candidate) > payload_hard:
                if current:
                    batches.append((header_source + current, current_start, row_index - 1))
                    current = ""
                parts = split_table_row(
                    block.rows[: block.header_row_count],
                    data_rows[row_index],
                    target=payload_target,
                    hard_max=payload_hard,
                    counter=counter,
                )
                batches.extend((render_table_part(part), row_index, row_index) for part in parts)
                current_start = row_index + 1
            else:
                current += row_source
        if current:
            batches.append((header_source + current, current_start, len(data_lines) - 1))

        _LOGGER.warning(
            "[CHUNKER] oversized atomic structure detected type=markdown_table "
            "block=%s tokens=%s limit=%s strategy=structure_aware_subdivision "
            "parts=%s content_conservation=PASS",
            block.ordinal,
            counter.count(source),
            hard_max,
            len(batches),
        )
        result: list[_Unit] = []
        for part_index, (body, start, end) in enumerate(batches):
            prefix = (
                f"Markdown table block {block.ordinal}, rows {start + 1}-{end + 1}, "
                f"part {part_index + 1}/{len(batches)}\n"
            )
            text = prefix + body
            if counter.count(text) > hard_max:
                raise UnsupportedError(
                    "structure-aware Markdown table subdivision exceeds the token maximum"
                )
            rows = (*block.rows[: block.header_row_count], *data_rows[start : end + 1])
            result.append(
                _Unit(
                    text=text,
                    chunk_type=ChunkType.PASSAGE,
                    source_span=span,
                    heading_path=heading_path,
                    section_index=section_index,
                    page_number=block.page_number,
                    kinds=("table",),
                    sources=(body,),
                    links=links,
                    heading_links=heading_links,
                    table_structure=FrozenMetadata(
                        {"header_row_count": block.header_row_count, "rows": rows}
                    ),
                    mergeable=False,
                    subdivision=_subdivision_metadata(
                        "markdown_table", block.ordinal, part_index, len(batches)
                    ),
                )
            )
        return tuple(result)

    def _paragraph_units(
        self,
        block: TextBlock,
        kind: str,
        source: str | None,
        links: tuple[FrozenMetadata, ...],
        heading_links: tuple[FrozenMetadata, ...],
        span: BlockSpan,
        heading_path: tuple[str, ...],
        section_index: int,
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit, ...]:
        formatted = bool(links) or (source is not None and source.strip() != block.text.strip())
        count = counter.count(block.text)
        if formatted and count > hard_max:
            raise UnsupportedError(
                "formatted Markdown paragraph exceeds the effective token maximum"
            )
        parts = (
            (block.text,) if formatted else self._reduce_text(block.text, target, hard_max, counter)
        )
        result: list[_Unit] = []
        for index, part in enumerate(parts):
            result.append(
                _Unit(
                    text=part,
                    chunk_type=ChunkType.PASSAGE,
                    source_span=span,
                    heading_path=heading_path,
                    section_index=section_index,
                    page_number=block.page_number,
                    kinds=(kind,),
                    sources=(source,) if source is not None and len(parts) == 1 else (),
                    links=links,
                    heading_links=heading_links,
                    separator="\n\n" if index == 0 else " ",
                )
            )
        return tuple(result)

    def _reduce_text(
        self,
        text: str,
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[str, ...]:
        count = counter.count(text)
        if count <= target:
            return (text,)
        sentences = tuple(part.strip() for part in _SENTENCE_BOUNDARY.split(text) if part.strip())
        if len(sentences) > 1:
            result: list[str] = []
            for sentence in sentences:
                if counter.count(sentence) <= hard_max:
                    result.append(sentence)
                else:
                    result.extend(self._word_split(sentence, target, hard_max, counter))
            return tuple(result)
        if count <= hard_max:
            return (text,)
        return self._word_split(text, target, hard_max, counter)

    @staticmethod
    def _word_split(
        text: str,
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[str, ...]:
        words = tuple(match.group(0) for match in _WORD_WITH_SPACE.finditer(text))
        if not words:
            raise UnsupportedError("Markdown prose has no safe word boundary")
        result: list[str] = []
        current = ""
        for word_with_space in words:
            word = word_with_space.rstrip()
            if counter.count(word) > hard_max:
                raise UnsupportedError("Markdown word exceeds the effective token maximum")
            candidate = (current + word_with_space).rstrip()
            if current and counter.count(candidate) > target:
                result.append(current.rstrip())
                current = word_with_space
            else:
                current += word_with_space
        if current.strip():
            result.append(current.rstrip())
        return tuple(result)

    @staticmethod
    def _atomic(
        text: str,
        chunk_type: ChunkType,
        span: BlockSpan,
        heading_path: tuple[str, ...],
        section_index: int,
        block: Block,
        kind: str,
        counter: TokenCounterInterfaceV1,
        hard_max: int,
        *,
        sources: tuple[str, ...] = (),
        links: tuple[FrozenMetadata, ...] = (),
        heading_links: tuple[FrozenMetadata, ...] = (),
        list_structure: FrozenMetadata | None = None,
        table_structure: FrozenMetadata | None = None,
        code_language: str | None = None,
    ) -> tuple[_Unit, ...]:
        if counter.count(text) > hard_max:
            raise UnsupportedError(f"atomic Markdown {kind} exceeds the effective token maximum")
        return (
            _Unit(
                text=text,
                chunk_type=chunk_type,
                source_span=span,
                heading_path=heading_path,
                section_index=section_index,
                page_number=block.page_number,
                kinds=(kind,),
                sources=sources,
                links=links,
                heading_links=heading_links,
                list_structure=list_structure,
                table_structure=table_structure,
                code_language=code_language,
                mergeable=False,
            ),
        )

    @staticmethod
    def _kind(block: Block) -> str:
        value = block.metadata.get("parser.markdown.kind")
        if not isinstance(value, str) or not value:
            raise UnsupportedError("canonical Markdown block is missing parser.markdown.kind")
        alias = block.metadata.get("parser.markdown.block_type")
        if alias is not None and alias != value:
            raise UnsupportedError("Markdown kind and compatibility alias disagree")
        return value

    @staticmethod
    def _source(block: Block, *, required: bool) -> str | None:
        value = block.metadata.get("parser.markdown.source")
        if value is None and not required:
            return None
        if not isinstance(value, str) or not value:
            raise UnsupportedError("Markdown block is missing exact source metadata")
        return value

    @staticmethod
    def _links(block: Block) -> tuple[FrozenMetadata, ...]:
        value = block.metadata.get("parser.markdown.links", ())
        if not isinstance(value, tuple):
            raise UnsupportedError("parser.markdown.links must be an immutable sequence")
        result: list[FrozenMetadata] = []
        for item in value:
            if not isinstance(item, FrozenMetadata):
                raise UnsupportedError("Markdown link metadata entry must be immutable")
            label = item.get("label")
            target = item.get("target")
            title = item.get("title")
            if (
                not isinstance(label, str)
                or not isinstance(target, str)
                or (title is not None and not isinstance(title, str))
            ):
                raise UnsupportedError("Markdown link metadata entry is malformed")
            result.append(item)
        return tuple(result)

    @staticmethod
    def _list_structure(block: Block) -> FrozenMetadata:
        value = block.metadata.get("parser.markdown.list")
        if not isinstance(value, FrozenMetadata):
            raise UnsupportedError("Markdown list is missing structured metadata")
        ordered = value.get("ordered")
        marker = value.get("marker")
        start = value.get("start")
        items = value.get("items")
        if (
            not isinstance(ordered, bool)
            or not isinstance(marker, str)
            or (start is not None and (isinstance(start, bool) or not isinstance(start, int)))
            or not isinstance(items, tuple)
            or not all(isinstance(item, FrozenMetadata) for item in items)
        ):
            raise UnsupportedError("Markdown list metadata is malformed")
        if not marker or not items:
            raise UnsupportedError("Markdown list metadata is incomplete")
        for item in items:
            assert isinstance(item, FrozenMetadata)
            depth = item.get("depth")
            item_ordered = item.get("ordered")
            item_marker = item.get("marker")
            item_start = item.get("start")
            text = item.get("text")
            if (
                isinstance(depth, bool)
                or not isinstance(depth, int)
                or depth < 0
                or not isinstance(item_ordered, bool)
                or not isinstance(item_marker, str)
                or not item_marker
                or (
                    item_start is not None
                    and (isinstance(item_start, bool) or not isinstance(item_start, int))
                )
                or not isinstance(text, str)
                or not text
            ):
                raise UnsupportedError("Markdown list item metadata is malformed")
        return value

    @staticmethod
    def _pack(
        units: tuple[_Unit, ...],
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit, ...]:
        if not units:
            return ()
        result: list[_Unit] = []
        current = units[0]
        for unit in units[1:]:
            candidate = current.text + unit.separator + unit.text
            count = counter.count(candidate)
            if MarkdownChunker._can_merge(current, unit) and (
                count <= target or (counter.count(current.text) < 15 and count <= hard_max)
            ):
                current = MarkdownChunker._merge(current, unit, candidate)
            else:
                result.append(current)
                current = unit
        if (
            counter.count(current.text) < 15
            and result
            and MarkdownChunker._can_merge(result[-1], current)
        ):
            candidate = result[-1].text + current.separator + current.text
            if counter.count(candidate) <= hard_max:
                current = MarkdownChunker._merge(result.pop(), current, candidate)
        result.append(current)
        return tuple(result)

    @staticmethod
    def _can_merge(left: _Unit, right: _Unit) -> bool:
        return (
            left.mergeable
            and right.mergeable
            and left.chunk_type is right.chunk_type
            and left.heading_path == right.heading_path
            and left.section_index == right.section_index
            and right.source_span.start_ordinal <= left.source_span.end_ordinal + 1
        )

    @staticmethod
    def _merge(left: _Unit, right: _Unit, text: str) -> _Unit:
        return _Unit(
            text=text,
            chunk_type=left.chunk_type,
            source_span=BlockSpan(
                start_ordinal=left.source_span.start_ordinal,
                end_ordinal=right.source_span.end_ordinal,
            ),
            heading_path=left.heading_path,
            section_index=left.section_index,
            page_number=left.page_number,
            kinds=left.kinds + right.kinds,
            sources=left.sources + right.sources,
            links=left.links + right.links,
            heading_links=left.heading_links,
            separator=left.separator,
        )

    @staticmethod
    def _draft_metadata(unit: _Unit) -> FrozenMetadata:
        values: dict[str, object] = {
            "chunker.markdown.source_kinds": unit.kinds,
            "chunker.markdown.strategy": "header_hierarchy",
        }
        if len(unit.kinds) == 1:
            values["chunker.markdown.kind"] = unit.kinds[0]
        if unit.sources:
            values["chunker.markdown.sources"] = unit.sources
        if unit.links:
            values["chunker.markdown.links"] = unit.links
        if unit.heading_links:
            values["chunker.markdown.heading_links"] = unit.heading_links
        if unit.list_structure is not None:
            values["chunker.markdown.list"] = unit.list_structure
        if unit.table_structure is not None:
            values["chunker.markdown.table"] = unit.table_structure
        if unit.code_language is not None:
            values["chunker.markdown.code_language"] = unit.code_language
        if unit.subdivision is not None:
            values["chunker.atomic.subdivision"] = unit.subdivision
            values["chunker.preserve_short"] = True
        return FrozenMetadata(values)


def _list_source_items(source: str) -> tuple[str, ...]:
    lines = source.splitlines(keepends=True)
    markers = [
        (index, len(match.group("indent").replace("\t", "    ")))
        for index, line in enumerate(lines)
        if (match := _LIST_ITEM_LINE.match(line)) is not None
    ]
    if not markers:
        raise UnsupportedError("oversized Markdown list has no source item boundaries")
    root_indent = min(indent for _, indent in markers)
    starts = [index for index, indent in markers if indent == root_indent]
    if not starts or starts[0] != 0:
        raise UnsupportedError("oversized Markdown list root boundary is malformed")
    starts.append(len(lines))
    return tuple("".join(lines[start:end]) for start, end in pairwise(starts))


def _list_structure_groups(
    items: tuple[object, ...],
) -> tuple[tuple[FrozenMetadata, ...], ...]:
    groups: list[list[FrozenMetadata]] = []
    for item in items:
        if not isinstance(item, FrozenMetadata):
            raise UnsupportedError("Markdown list item metadata is not immutable")
        if item.get("depth") == 0:
            groups.append([])
        if not groups:
            raise UnsupportedError("Markdown list metadata starts below the root")
        groups[-1].append(item)
    return tuple(tuple(group) for group in groups)


def _subdivision_metadata(
    kind: str, block_ordinal: int, part_index: int, total_parts: int
) -> FrozenMetadata:
    return FrozenMetadata(
        {
            "strategy": "structure_aware_subdivision",
            "type": kind,
            "parent_block_ordinal": block_ordinal,
            "part_index": part_index,
            "total_parts": total_parts,
            "content_conservation": "exact_source_or_structured_cells",
        }
    )
