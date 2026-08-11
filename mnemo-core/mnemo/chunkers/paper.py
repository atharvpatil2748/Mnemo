"""Deterministic canonical-section chunking for research papers."""

import re
from dataclasses import dataclass
from enum import StrEnum

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
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?\u3002\uff01\uff1f])\s+")
_WORD_WITH_SPACE = re.compile(r"\S+(?:\s+|$)")
_NUMBER_PREFIX = re.compile(r"^(?:(?:\d+(?:\.\d+)*)|(?:[ivxlcdm]+))[.)]?\s+", re.IGNORECASE)
_DECIMAL_PREFIX = re.compile(r"^(\d+(?:\.\d+)*)[.)]?\s+")
_SUMMARY_HEADING = re.compile(r"^(?:summary|executive summary)$", re.IGNORECASE)


class _PaperSection(StrEnum):
    ABSTRACT = "abstract"
    INTRODUCTION = "introduction"
    BACKGROUND = "background"
    METHODS = "methods"
    RESULTS = "results"
    DISCUSSION = "discussion"
    CONCLUSION = "conclusion"
    LIMITATIONS = "limitations"
    FUTURE_WORK = "future_work"
    ACKNOWLEDGEMENTS = "acknowledgements"
    REFERENCES = "references"
    OTHER = "other"


_SECTION_NAMES: dict[str, _PaperSection] = {
    "abstract": _PaperSection.ABSTRACT,
    "introduction": _PaperSection.INTRODUCTION,
    "background": _PaperSection.BACKGROUND,
    "related work": _PaperSection.BACKGROUND,
    "literature review": _PaperSection.BACKGROUND,
    "methods": _PaperSection.METHODS,
    "method": _PaperSection.METHODS,
    "methodology": _PaperSection.METHODS,
    "materials and methods": _PaperSection.METHODS,
    "experimental setup": _PaperSection.METHODS,
    "experiments": _PaperSection.METHODS,
    "results": _PaperSection.RESULTS,
    "findings": _PaperSection.RESULTS,
    "discussion": _PaperSection.DISCUSSION,
    "conclusion": _PaperSection.CONCLUSION,
    "conclusions": _PaperSection.CONCLUSION,
    "limitations": _PaperSection.LIMITATIONS,
    "future work": _PaperSection.FUTURE_WORK,
    "acknowledgement": _PaperSection.ACKNOWLEDGEMENTS,
    "acknowledgements": _PaperSection.ACKNOWLEDGEMENTS,
    "acknowledgment": _PaperSection.ACKNOWLEDGEMENTS,
    "acknowledgments": _PaperSection.ACKNOWLEDGEMENTS,
    "references": _PaperSection.REFERENCES,
    "bibliography": _PaperSection.REFERENCES,
}


@dataclass(frozen=True, slots=True)
class _Unit:
    text: str
    chunk_type: ChunkType
    source_span: BlockSpan
    heading_path: tuple[str, ...]
    section_index: int
    page_number: int | None
    separator: str
    content_kind: str
    mergeable: bool = True


class PaperChunker:
    """Chunk canonical papers by source-defined research sections."""

    @property
    def supported_doc_types(self) -> tuple[DocType, ...]:
        """Return the sole classification owned by this strategy."""
        return (DocType.PAPER,)

    def capabilities(self) -> ChunkerCapabilities:
        """Describe the strategy's implemented behavior."""
        return ChunkerCapabilities(
            supported_doc_types=self.supported_doc_types,
            preserves_semantic_boundaries=True,
            supports_parent_child=False,
            supports_overlap=False,
            metadata=FrozenMetadata({"chunker.paper.version": "v1"}),
        )

    def chunk(
        self,
        document: ParsedDocument,
        context: ChunkingContext,
        token_counter: TokenCounterInterfaceV1,
    ) -> tuple[ChunkDraft, ...]:
        """Return ordered paper drafts without final identity or relationships."""
        if not isinstance(document, ParsedDocument):
            raise TypeError("document must be ParsedDocument")
        if not isinstance(context, ChunkingContext):
            raise TypeError("context must be ChunkingContext")
        if not isinstance(token_counter, TokenCounterInterfaceV1):
            raise TypeError("token_counter must satisfy TokenCounterInterfaceV1")
        if document.doc_type is not DocType.PAPER:
            raise UnsupportedError("PaperChunker supports only DocType.PAPER")

        units = self._units(document, context, token_counter)
        packed = self._pack(
            units,
            context.options.target_tokens,
            context.effective_max_tokens,
            token_counter,
        )
        section_counts: dict[int, int] = {}
        drafts: list[ChunkDraft] = []
        for unit in packed:
            chunk_index = section_counts.get(unit.section_index, 0)
            section_counts[unit.section_index] = chunk_index + 1
            section = self._canonical_section(unit.heading_path)
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
                    metadata=FrozenMetadata(
                        {
                            "chunker.paper.content_kind": unit.content_kind,
                            "chunker.paper.section": section.value,
                            "chunker.paper.strategy": "canonical-sections-v1",
                        }
                    ),
                )
            )
        return tuple(drafts)

    def _units(
        self,
        document: ParsedDocument,
        context: ChunkingContext,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit, ...]:
        informative_levels = (
            len({block.level for block in document.blocks if isinstance(block, HeadingBlock)}) > 1
        )
        result: list[_Unit] = []
        headings: list[str] = []
        section_index = 0
        major_source_level = 1
        current_section = _PaperSection.OTHER
        in_references = False
        index = 0
        while index < len(document.blocks):
            block = document.blocks[index]
            if isinstance(block, HeadingBlock):
                detected = self._section_for_heading(block.text)
                if in_references and (
                    detected not in (_PaperSection.OTHER, _PaperSection.REFERENCES)
                    or block.level == 1
                ):
                    in_references = False
                if detected is _PaperSection.REFERENCES:
                    in_references = True
                    current_section = detected
                    headings = [block.text]
                    section_index += 1
                    index += 1
                    continue
                if (
                    detected is not _PaperSection.OTHER
                    and detected is current_section
                    and headings
                    and block.level > major_source_level
                ):
                    level = self._relative_level(block, major_source_level, informative_levels)
                    headings = headings[: level - 1]
                    headings.append(block.text)
                elif detected is not _PaperSection.OTHER:
                    current_section = detected
                    headings = [block.text]
                    major_source_level = block.level
                else:
                    level = self._relative_level(block, major_source_level, informative_levels)
                    if level == 1:
                        headings = [block.text]
                        current_section = _PaperSection.OTHER
                        major_source_level = block.level
                    else:
                        headings = headings[: level - 1]
                        headings.append(block.text)
                section_index += 1
                if current_section is _PaperSection.ABSTRACT:
                    abstract, next_index = self._abstract_unit(
                        document,
                        index + 1,
                        tuple(headings),
                        section_index,
                        context.effective_max_tokens,
                        counter,
                    )
                    if abstract is not None:
                        result.append(abstract)
                    index = next_index
                    continue
                index += 1
                continue
            if in_references:
                index += 1
                continue
            result.extend(
                self._block_units(
                    block,
                    tuple(headings),
                    current_section,
                    section_index,
                    context.options.target_tokens,
                    context.effective_max_tokens,
                    counter,
                )
            )
            index += 1
        return tuple(result)

    def _abstract_unit(
        self,
        document: ParsedDocument,
        start: int,
        heading_path: tuple[str, ...],
        section_index: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit | None, int]:
        blocks: list[TextBlock] = []
        index = start
        while index < len(document.blocks) and not isinstance(document.blocks[index], HeadingBlock):
            block = document.blocks[index]
            if not isinstance(block, TextBlock):
                raise UnsupportedError("atomic abstract contains non-prose canonical content")
            blocks.append(block)
            index += 1
        if not blocks:
            return None, index
        text = "\n\n".join(block.text for block in blocks)
        if counter.count(text) > hard_max:
            raise UnsupportedError("atomic abstract exceeds the effective token maximum")
        return (
            _Unit(
                text=text,
                chunk_type=ChunkType.PASSAGE,
                source_span=BlockSpan(
                    start_ordinal=blocks[0].ordinal,
                    end_ordinal=blocks[-1].ordinal,
                ),
                heading_path=heading_path,
                section_index=section_index,
                page_number=blocks[0].page_number,
                separator="\n\n",
                content_kind="abstract",
                mergeable=False,
            ),
            index,
        )

    def _block_units(
        self,
        block: Block,
        heading_path: tuple[str, ...],
        section: _PaperSection,
        section_index: int,
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit, ...]:
        span = BlockSpan(start_ordinal=block.ordinal, end_ordinal=block.ordinal)
        if isinstance(block, EquationBlock):
            return self._atomic(
                block.latex,
                ChunkType.EQUATION,
                "equation",
                span,
                heading_path,
                section_index,
                block,
                hard_max,
                counter,
            )
        if isinstance(block, TableBlock):
            text = "\n".join("\t".join(row) for row in block.rows)
            return self._atomic(
                text,
                ChunkType.PASSAGE,
                "table",
                span,
                heading_path,
                section_index,
                block,
                hard_max,
                counter,
            )
        if isinstance(block, CodeBlock):
            return self._atomic(
                block.code,
                ChunkType.CODE,
                "code",
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
            text, chunk_type, kind = block.alt_text, ChunkType.CAPTION, "image_alt"
        elif isinstance(block, CaptionBlock):
            text, chunk_type, kind = block.text, ChunkType.CAPTION, "caption"
        elif isinstance(block, TextBlock):
            text, kind = block.text, "prose"
            chunk_type = (
                ChunkType.SUMMARY
                if heading_path and _SUMMARY_HEADING.fullmatch(self._strip_number(heading_path[-1]))
                else ChunkType.PASSAGE
            )
        else:
            return ()
        return self._text_units(
            text,
            chunk_type,
            kind,
            span,
            heading_path,
            section_index,
            block.page_number,
            target,
            hard_max,
            counter,
        )

    @staticmethod
    def _atomic(
        text: str,
        chunk_type: ChunkType,
        content_kind: str,
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
                text,
                chunk_type,
                span,
                heading_path,
                section_index,
                block.page_number,
                "\n\n",
                content_kind,
                False,
            ),
        )

    def _text_units(
        self,
        text: str,
        chunk_type: ChunkType,
        content_kind: str,
        span: BlockSpan,
        heading_path: tuple[str, ...],
        section_index: int,
        page_number: int | None,
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit, ...]:
        result: list[_Unit] = []
        paragraphs = (
            (text,)
            if _PARAGRAPH_BOUNDARY.search(text) is None
            else tuple(part.strip() for part in _PARAGRAPH_BOUNDARY.split(text))
        )
        for paragraph in paragraphs:
            if not paragraph.strip():
                continue
            parts = self._reduce_text(paragraph, target, hard_max, counter)
            for index, part in enumerate(parts):
                result.append(
                    _Unit(
                        part,
                        chunk_type,
                        span,
                        heading_path,
                        section_index,
                        page_number,
                        "\n\n" if index == 0 else " ",
                        content_kind,
                    )
                )
        return tuple(result)

    def _reduce_text(
        self, text: str, target: int, hard_max: int, counter: TokenCounterInterfaceV1
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
        text: str, target: int, hard_max: int, counter: TokenCounterInterfaceV1
    ) -> tuple[str, ...]:
        words = tuple(match.group(0) for match in _WORD_WITH_SPACE.finditer(text))
        if not words:
            raise UnsupportedError("paper textual unit has no safe word boundary")
        result: list[str] = []
        current = ""
        for word_with_space in words:
            word = word_with_space.rstrip()
            if counter.count(word) > hard_max:
                raise UnsupportedError("paper word exceeds the effective token maximum")
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
            if PaperChunker._can_merge(current, unit) and (
                candidate_count <= target
                or (counter.count(current.text) < 15 and candidate_count <= hard_max)
            ):
                current = PaperChunker._merge(current, unit, candidate)
            else:
                result.append(current)
                current = unit
        if (
            result
            and counter.count(current.text) < 15
            and PaperChunker._can_merge(result[-1], current)
        ):
            candidate = result[-1].text + current.separator + current.text
            if counter.count(candidate) <= hard_max:
                current = PaperChunker._merge(result.pop(), current, candidate)
        result.append(current)
        return tuple(result)

    @staticmethod
    def _can_merge(left: _Unit, right: _Unit) -> bool:
        return (
            left.mergeable
            and right.mergeable
            and left.chunk_type is right.chunk_type
            and left.content_kind == right.content_kind
            and left.heading_path == right.heading_path
            and left.section_index == right.section_index
            and right.source_span.start_ordinal <= left.source_span.end_ordinal + 1
        )

    @staticmethod
    def _merge(left: _Unit, right: _Unit, text: str) -> _Unit:
        return _Unit(
            text,
            left.chunk_type,
            BlockSpan(
                start_ordinal=left.source_span.start_ordinal,
                end_ordinal=right.source_span.end_ordinal,
            ),
            left.heading_path,
            left.section_index,
            left.page_number,
            left.separator,
            left.content_kind,
        )

    @classmethod
    def _section_for_heading(cls, text: str) -> _PaperSection:
        return _SECTION_NAMES.get(cls._strip_number(text), _PaperSection.OTHER)

    @classmethod
    def _canonical_section(cls, heading_path: tuple[str, ...]) -> _PaperSection:
        for heading in reversed(heading_path):
            section = cls._section_for_heading(heading)
            if section is not _PaperSection.OTHER:
                return section
        return _PaperSection.OTHER

    @classmethod
    def _relative_level(
        cls, heading: HeadingBlock, major_source_level: int, informative_levels: bool
    ) -> int:
        if informative_levels:
            return min(4, max(1, heading.level - major_source_level + 1))
        decimal = _DECIMAL_PREFIX.match(heading.text.strip())
        if decimal:
            return min(4, decimal.group(1).count(".") + 1)
        return min(4, heading.level)

    @staticmethod
    def _strip_number(text: str) -> str:
        return " ".join(_NUMBER_PREFIX.sub("", text.strip()).casefold().strip(" .:").split())
