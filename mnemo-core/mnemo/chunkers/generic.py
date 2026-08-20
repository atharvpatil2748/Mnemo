"""Deterministic generic semantic chunking strategy."""

import re
from dataclasses import dataclass

from mnemo.interfaces import (
    ChunkerCapabilities,
    ChunkingContext,
    TokenCounterInterfaceV1,
    UnsupportedError,
)
from mnemo.models import (
    Block,
    BlockSpan,
    CaptionBlock,
    ChunkDraft,
    ChunkPosition,
    ChunkType,
    CodeBlock,
    DocType,
    EquationBlock,
    FrozenMetadata,
    HeadingBlock,
    ImageBlock,
    ParsedDocument,
    TableBlock,
    TextBlock,
)

_PARAGRAPH_BOUNDARY = re.compile(r"\n[ \t]*\n+")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_WORD_WITH_SPACE = re.compile(r"\S+(?:\s+|$)")
_METADATA = FrozenMetadata({"chunker.generic.strategy": "recursive"})


@dataclass(frozen=True, slots=True)
class _Unit:
    text: str
    chunk_type: ChunkType
    source_span: BlockSpan
    heading_path: tuple[str, ...]
    section_index: int
    page_number: int | None
    separator: str
    mergeable: bool = True


class GenericChunker:
    """Chunk generic canonical documents at natural textual boundaries."""

    @property
    def supported_doc_types(self) -> tuple[DocType, ...]:
        """Return the sole classification owned by this strategy."""
        return (DocType.GENERIC,)

    def capabilities(self) -> ChunkerCapabilities:
        """Describe the strategy's implemented behavior."""
        return ChunkerCapabilities(
            supported_doc_types=self.supported_doc_types,
            preserves_semantic_boundaries=True,
            supports_parent_child=False,
            supports_overlap=False,
            metadata=FrozenMetadata({"chunker.generic.version": "v1"}),
        )

    def chunk(
        self,
        document: ParsedDocument,
        context: ChunkingContext,
        token_counter: TokenCounterInterfaceV1,
    ) -> tuple[ChunkDraft, ...]:
        """Return ordered root drafts without final identity or relationships."""
        if not isinstance(document, ParsedDocument):
            raise TypeError("document must be ParsedDocument")
        if not isinstance(context, ChunkingContext):
            raise TypeError("context must be ChunkingContext")
        if not isinstance(token_counter, TokenCounterInterfaceV1):
            raise TypeError("token_counter must satisfy TokenCounterInterfaceV1")
        if document.doc_type is not DocType.GENERIC:
            raise UnsupportedError("GenericChunker supports only DocType.GENERIC")

        units = self._units(
            document,
            context.options.target_tokens,
            context.effective_max_tokens,
            token_counter,
        )
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
                    metadata=_METADATA,
                )
            )
        return tuple(drafts)

    def _units(
        self,
        document: ParsedDocument,
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit, ...]:
        result: list[_Unit] = []
        headings: list[str] = []
        section_index = 0
        for block in document.blocks:
            if isinstance(block, HeadingBlock):
                headings = headings[: block.level - 1]
                headings.append(block.text)
                section_index += 1
                continue
            block_units = self._block_units(
                block, tuple(headings), section_index, target, hard_max, counter
            )
            result.extend(block_units)
        return tuple(result)

    def _block_units(
        self,
        block: Block,
        heading_path: tuple[str, ...],
        section_index: int,
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit, ...]:
        span = BlockSpan(start_ordinal=block.ordinal, end_ordinal=block.ordinal)
        if isinstance(block, TableBlock):
            return self._table_units(
                block, span, heading_path, section_index, target, hard_max, counter
            )
        if isinstance(block, EquationBlock):
            return self._atomic_unit(
                block.latex,
                ChunkType.EQUATION,
                span,
                heading_path,
                section_index,
                block,
                hard_max,
                counter,
            )
        if isinstance(block, ImageBlock):
            if block.alt_text is None:
                return ()
            return self._text_units(
                block.alt_text,
                ChunkType.CAPTION,
                span,
                heading_path,
                section_index,
                block.page_number,
                target,
                hard_max,
                counter,
            )
        if isinstance(block, TextBlock):
            text, chunk_type = block.text, ChunkType.PASSAGE
        elif isinstance(block, CodeBlock):
            text, chunk_type = block.code, ChunkType.CODE
        elif isinstance(block, CaptionBlock):
            text, chunk_type = block.text, ChunkType.CAPTION
        else:
            return ()
        return self._text_units(
            text,
            chunk_type,
            span,
            heading_path,
            section_index,
            block.page_number,
            target,
            hard_max,
            counter,
        )

    @staticmethod
    def _table_units(
        block: TableBlock,
        span: BlockSpan,
        heading_path: tuple[str, ...],
        section_index: int,
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit, ...]:
        """Partition oversized tables by complete rows, repeating header rows."""

        def render(rows: tuple[tuple[str, ...], ...]) -> str:
            return "\n".join("\t".join(row) for row in rows).strip()

        full_text = render(block.rows)
        if not full_text:
            return ()
        if counter.count(full_text) <= hard_max:
            return GenericChunker._atomic_unit(
                full_text,
                ChunkType.PASSAGE,
                span,
                heading_path,
                section_index,
                block,
                hard_max,
                counter,
            )

        headers = block.rows[: block.header_row_count]
        data_rows = block.rows[block.header_row_count :]
        if not data_rows:
            raise UnsupportedError("atomic TableBlock exceeds the effective token maximum")

        result: list[_Unit] = []
        batch: list[tuple[str, ...]] = []
        for row in data_rows:
            candidate = (*headers, *batch, row)
            candidate_text = render(candidate)
            if batch and counter.count(candidate_text) > target:
                emitted = render((*headers, *batch))
                result.append(
                    _Unit(
                        text=emitted,
                        chunk_type=ChunkType.PASSAGE,
                        source_span=span,
                        heading_path=heading_path,
                        section_index=section_index,
                        page_number=block.page_number,
                        separator="\n\n",
                        mergeable=False,
                    )
                )
                batch = []
                candidate_text = render((*headers, row))
            if counter.count(candidate_text) > hard_max:
                raise UnsupportedError("atomic table row exceeds the effective token maximum")
            batch.append(row)

        if batch:
            result.append(
                _Unit(
                    text=render((*headers, *batch)),
                    chunk_type=ChunkType.PASSAGE,
                    source_span=span,
                    heading_path=heading_path,
                    section_index=section_index,
                    page_number=block.page_number,
                    separator="\n\n",
                    mergeable=False,
                )
            )
        return tuple(result)

    @staticmethod
    def _atomic_unit(
        text: str,
        chunk_type: ChunkType,
        span: BlockSpan,
        heading_path: tuple[str, ...],
        section_index: int,
        block: Block,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit, ...]:
        if counter.count(text) > hard_max:
            raise UnsupportedError(
                f"atomic {type(block).__name__} exceeds the effective token maximum"
            )
        return (
            _Unit(
                text=text,
                chunk_type=chunk_type,
                source_span=span,
                heading_path=heading_path,
                section_index=section_index,
                page_number=block.page_number,
                separator="\n\n",
                mergeable=False,
            ),
        )

    def _text_units(
        self,
        text: str,
        chunk_type: ChunkType,
        span: BlockSpan,
        heading_path: tuple[str, ...],
        section_index: int,
        page_number: int | None,
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit, ...]:
        paragraphs = tuple(part.strip() for part in _PARAGRAPH_BOUNDARY.split(text.strip()))
        result: list[_Unit] = []
        for paragraph in paragraphs:
            if not paragraph:
                continue
            parts = self._reduce_text(paragraph, target, hard_max, counter)
            for index, part in enumerate(parts):
                result.append(
                    _Unit(
                        text=part,
                        chunk_type=chunk_type,
                        source_span=span,
                        heading_path=heading_path,
                        section_index=section_index,
                        page_number=page_number,
                        separator="\n\n" if index == 0 else " ",
                    )
                )
        return tuple(result)

    def _reduce_text(
        self, text: str, target: int, hard_max: int, counter: TokenCounterInterfaceV1
    ) -> tuple[str, ...]:
        text_count = counter.count(text)
        if text_count <= target:
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
        if text_count <= hard_max:
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
            raise UnsupportedError("generic textual unit has no safe word boundary")
        result: list[str] = []
        current = ""
        for word_with_space in words:
            word = word_with_space.rstrip()
            if counter.count(word) > hard_max:
                raise UnsupportedError("generic word exceeds the effective token maximum")
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
            candidate_count = counter.count(candidate)
            if GenericChunker._can_merge(current, unit) and (
                candidate_count <= target
                or (counter.count(current.text) < 15 and candidate_count <= hard_max)
            ):
                current = GenericChunker._merge(current, unit, candidate)
            else:
                result.append(current)
                current = unit
        if (
            counter.count(current.text) < 15
            and result
            and GenericChunker._can_merge(result[-1], current)
        ):
            candidate = result[-1].text + current.separator + current.text
            if counter.count(candidate) <= hard_max:
                current = GenericChunker._merge(result.pop(), current, candidate)
        result.append(current)
        return tuple(result)

    @staticmethod
    def _can_merge(left: _Unit, right: _Unit) -> bool:
        contiguous = right.source_span.start_ordinal <= left.source_span.end_ordinal + 1
        return (
            left.mergeable
            and right.mergeable
            and left.chunk_type is right.chunk_type
            and left.heading_path == right.heading_path
            and left.section_index == right.section_index
            and contiguous
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
            separator=left.separator,
        )
