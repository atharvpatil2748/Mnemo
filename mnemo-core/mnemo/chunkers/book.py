"""Deterministic source-structured chunking for books."""

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
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?\u3002\uff01\uff1f])\s+")
_WORD_WITH_SPACE = re.compile(r"\S+(?:\s+|$)")
_TOC_MARKER = re.compile(
    r"^(?:table\s+of\s+)?contents(?:\s+with\s+clickable\s+chapter\s+links?)?:?$",
    re.IGNORECASE,
)
_PAGE_SUFFIX = re.compile(r"(?:\.{2,}|\s{2,}|!)\s*(?:\d+|[ivxlcdm]+)\s*$", re.IGNORECASE)
_CARDINAL = (
    r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty"
)
_PART = re.compile(rf"^part\s+(?:[ivxlcdm]+|\d+|{_CARDINAL})\b", re.IGNORECASE)
_CHAPTER = re.compile(
    rf"^(?:chapter|book)\s+(?:[ivxlcdm]+|\d+|{_CARDINAL})\b",
    re.IGNORECASE,
)
_SECTION = re.compile(r"^section\b", re.IGNORECASE)
_SUBSECTION = re.compile(r"^subsection\b", re.IGNORECASE)
_DECIMAL = re.compile(r"^(\d+(?:\.\d+)*)(?:[.)\s:-]|$)")
_SUMMARY = re.compile(r"^(?:(?:chapter|section)\s+)?(?:summary|synopsis|overview)\b", re.IGNORECASE)
_MAJOR_MATTER = re.compile(
    r"^(?:preface|foreword|introduction|acknowledgements?|prologue|epilogue|"
    r"appendix(?:\s+[a-z0-9]+)?|notes|bibliography|index)$",
    re.IGNORECASE,
)
_VERBATIM_ROLES = frozenset(
    {"quote", "quotation", "blockquote", "definition", "claim", "key_definition", "key_claim"}
)
_VERBATIM_KEYS = (
    "parser.block_role",
    "parser.markdown.block_type",
    "layout.block_role",
    "chunker.source_role",
)


@dataclass(frozen=True, slots=True)
class _Toc:
    excluded_ordinals: frozenset[int]
    levels: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class _Unit:
    text: str
    chunk_type: ChunkType
    source_span: BlockSpan
    heading_path: tuple[str, ...]
    section_index: int
    chapter_index: int
    page_number: int | None
    separator: str
    mergeable: bool = True


class BookChunker:
    """Chunk canonical books without crossing source chapter boundaries."""

    @property
    def supported_doc_types(self) -> tuple[DocType, ...]:
        """Return the sole classification owned by this strategy."""
        return (DocType.BOOK,)

    def capabilities(self) -> ChunkerCapabilities:
        """Describe the strategy's implemented behavior."""
        return ChunkerCapabilities(
            supported_doc_types=self.supported_doc_types,
            preserves_semantic_boundaries=True,
            supports_parent_child=False,
            supports_overlap=False,
            metadata=FrozenMetadata({"chunker.book.version": "v1"}),
        )

    def chunk(
        self,
        document: ParsedDocument,
        context: ChunkingContext,
        token_counter: TokenCounterInterfaceV1,
    ) -> tuple[ChunkDraft, ...]:
        """Return ordered source-derived book drafts for dispatcher finalization."""
        if not isinstance(document, ParsedDocument):
            raise TypeError("document must be ParsedDocument")
        if not isinstance(context, ChunkingContext):
            raise TypeError("context must be ChunkingContext")
        if not isinstance(token_counter, TokenCounterInterfaceV1):
            raise TypeError("token_counter must satisfy TokenCounterInterfaceV1")
        if document.doc_type is not DocType.BOOK:
            raise UnsupportedError("BookChunker supports only DocType.BOOK")

        toc = self._detect_toc(document)
        units = self._units(document, toc, context, token_counter)
        packed = self._pack(
            units,
            context.options.target_tokens,
            context.effective_max_tokens,
            token_counter,
        )
        metadata = FrozenMetadata(
            {
                "chunker.book.hierarchy_source": "toc" if toc.excluded_ordinals else "headings",
                "chunker.book.strategy": "three-level-v1",
            }
        )
        section_counts: dict[int, int] = {}
        drafts: list[ChunkDraft] = []
        for unit in packed:
            chunk_index = section_counts.get(unit.section_index, 0)
            section_counts[unit.section_index] = chunk_index + 1
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
                    metadata=metadata,
                )
            )
        return tuple(drafts)

    def _units(
        self,
        document: ParsedDocument,
        toc: _Toc,
        context: ChunkingContext,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit, ...]:
        result: list[_Unit] = []
        title = () if document.metadata.title is None else (document.metadata.title,)
        headings: list[str] = []
        section_index = 0
        chapter_index = 0
        part_active = False
        pending_chapter_title_page: int | None = None
        pending_chapter_title_level: int | None = None
        pending_chapter_title_parts: list[str] = []
        level_map = dict(toc.levels)
        canonical_levels_informative = (
            len(
                {
                    block.level
                    for block in document.blocks
                    if isinstance(block, HeadingBlock)
                    and block.ordinal not in toc.excluded_ordinals
                }
            )
            > 1
        )
        for block in document.blocks:
            if block.ordinal in toc.excluded_ordinals:
                continue
            if isinstance(block, HeadingBlock):
                if title and self._normalize(block.text) == self._normalize(title[0]):
                    headings.clear()
                    continue
                level = self._heading_level(block, level_map, canonical_levels_informative)
                kind = self._heading_kind(block.text)
                if (
                    kind == "other"
                    and _DECIMAL.match(block.text.strip()) is None
                    and pending_chapter_title_level is not None
                    and block.page_number == pending_chapter_title_page
                ):
                    # Real PDFs often split a visual chapter title into multiple
                    # same-font text blocks. Treat those adjacent source headings as
                    # one deeper title without inventing or discarding any text.
                    pending_chapter_title_parts.append(block.text)
                    level = pending_chapter_title_level
                    headings = headings[: level - 1]
                    headings.append(" ".join(pending_chapter_title_parts))
                    section_index += 1
                    continue
                if kind == "part":
                    part_active = True
                    chapter_index += 1
                    pending_chapter_title_page = None
                    pending_chapter_title_level = None
                    pending_chapter_title_parts.clear()
                elif kind == "chapter":
                    # A chapter is the top authored level unless a Part is active.
                    # Font-only PDF parsers commonly emit every display heading at
                    # canonical level 1, so preserving a previous front-matter
                    # heading here would create a false parent for the chapter.
                    level = 2 if part_active else 1
                    chapter_index += 1
                    pending_chapter_title_page = block.page_number
                    pending_chapter_title_level = min(4, level + 1)
                    pending_chapter_title_parts.clear()
                elif kind == "matter" or block.level == 1 or (part_active and block.level == 2):
                    chapter_index += 1
                    pending_chapter_title_page = None
                    pending_chapter_title_level = None
                    pending_chapter_title_parts.clear()

                headings = headings[: level - 1]
                headings.append(block.text)
                section_index += 1
                continue
            # Decorative PDF images can occur between the chapter label and its
            # visual title. An image without authored alt text emits no unit, so
            # it must not terminate the pending chapter-title sequence.
            if not (isinstance(block, ImageBlock) and block.alt_text is None):
                pending_chapter_title_page = None
                pending_chapter_title_level = None
                pending_chapter_title_parts.clear()
            heading_path = title + tuple(headings)
            result.extend(
                self._block_units(
                    block,
                    heading_path,
                    section_index,
                    chapter_index,
                    context.options.target_tokens,
                    context.effective_max_tokens,
                    counter,
                )
            )
        return tuple(result)

    def _block_units(
        self,
        block: Block,
        heading_path: tuple[str, ...],
        section_index: int,
        chapter_index: int,
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit, ...]:
        span = BlockSpan(start_ordinal=block.ordinal, end_ordinal=block.ordinal)
        if isinstance(block, TableBlock):
            text = "\n".join("\t".join(row) for row in block.rows).strip()
            return (
                self._atomic(
                    text,
                    ChunkType.PASSAGE,
                    span,
                    heading_path,
                    section_index,
                    chapter_index,
                    block,
                    hard_max,
                    counter,
                )
                if text
                else ()
            )
        if isinstance(block, EquationBlock):
            return self._atomic(
                block.latex,
                ChunkType.EQUATION,
                span,
                heading_path,
                section_index,
                chapter_index,
                block,
                hard_max,
                counter,
            )
        if isinstance(block, CodeBlock):
            return self._atomic(
                block.code,
                ChunkType.CODE,
                span,
                heading_path,
                section_index,
                chapter_index,
                block,
                hard_max,
                counter,
            )
        if isinstance(block, ImageBlock):
            if block.alt_text is None:
                return ()
            text, chunk_type = block.alt_text, ChunkType.CAPTION
        elif isinstance(block, CaptionBlock):
            text, chunk_type = block.text, ChunkType.CAPTION
        elif isinstance(block, TextBlock):
            text = block.text
            if heading_path and _SUMMARY.match(heading_path[-1]):
                chunk_type = ChunkType.SUMMARY
            elif self._is_verbatim(block):
                chunk_type = ChunkType.VERBATIM
            else:
                chunk_type = ChunkType.PASSAGE
        else:
            return ()
        role_target = min(target, 150) if chunk_type is ChunkType.VERBATIM else target
        return self._text_units(
            text,
            chunk_type,
            span,
            heading_path,
            section_index,
            chapter_index,
            block.page_number,
            role_target,
            hard_max,
            counter,
        )

    @staticmethod
    def _atomic(
        text: str,
        chunk_type: ChunkType,
        span: BlockSpan,
        heading_path: tuple[str, ...],
        section_index: int,
        chapter_index: int,
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
                chapter_index,
                block.page_number,
                "\n\n",
                False,
            ),
        )

    def _text_units(
        self,
        text: str,
        chunk_type: ChunkType,
        span: BlockSpan,
        heading_path: tuple[str, ...],
        section_index: int,
        chapter_index: int,
        page_number: int | None,
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit, ...]:
        result: list[_Unit] = []
        for paragraph in (part.strip() for part in _PARAGRAPH_BOUNDARY.split(text.strip())):
            if not paragraph:
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
                        chapter_index,
                        page_number,
                        "\n\n" if index == 0 else " ",
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
            raise UnsupportedError("book textual unit has no safe word boundary")
        result: list[str] = []
        current = ""
        for word_with_space in words:
            word = word_with_space.rstrip()
            if counter.count(word) > hard_max:
                raise UnsupportedError("book word exceeds the effective token maximum")
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
            if BookChunker._can_merge(current, unit) and (
                candidate_count <= target
                or (counter.count(current.text) < 15 and candidate_count <= hard_max)
            ):
                current = BookChunker._merge(current, unit, candidate)
            else:
                result.append(current)
                current = unit
        if (
            result
            and counter.count(current.text) < 15
            and BookChunker._can_merge(result[-1], current)
        ):
            candidate = result[-1].text + current.separator + current.text
            if counter.count(candidate) <= hard_max:
                current = BookChunker._merge(result.pop(), current, candidate)
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
            and left.chapter_index == right.chapter_index
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
            left.chapter_index,
            left.page_number,
            left.separator,
        )

    @classmethod
    def _detect_toc(cls, document: ParsedDocument) -> _Toc:
        for index, block in enumerate(document.blocks):
            lines = cls._lines(block)
            if not lines or not _TOC_MARKER.fullmatch(lines[0].strip()):
                continue
            candidate_lines = list(lines[1:])
            candidate_ordinals = {block.ordinal}
            for following in document.blocks[index + 1 : index + 21]:
                if isinstance(following, HeadingBlock):
                    break
                following_lines = cls._lines(following)
                if not following_lines:
                    continue
                if cls._entry_density(following_lines) < 0.6:
                    break
                candidate_lines.extend(following_lines)
                candidate_ordinals.add(following.ordinal)
            entries = tuple(entry for line in candidate_lines if (entry := cls._toc_entry(line)))
            strong = sum(1 for line in candidate_lines if cls._strong_toc_line(line))
            density = 0.0 if not candidate_lines else len(entries) / len(candidate_lines)
            if len(entries) >= 3 and density >= 0.7 and (strong >= 2 or len(entries) >= 4):
                levels = tuple((cls._normalize(title), level) for title, level in entries)
                return _Toc(frozenset(candidate_ordinals), levels)
        return _Toc(frozenset(), ())

    @classmethod
    def _toc_entry(cls, line: str) -> tuple[str, int] | None:
        text = _PAGE_SUFFIX.sub("", line.strip()).strip(" .\t")
        if not text or len(text.split()) > 16 or text.endswith((".", "!", "?")):
            return None
        if _PART.match(text):
            return text, 1
        if _CHAPTER.match(text):
            return text, 2
        if _SUBSECTION.match(text):
            return text, 4
        if _SECTION.match(text):
            return text, 3
        decimal = _DECIMAL.match(text)
        if decimal:
            return text, min(4, decimal.group(1).count(".") + 2)
        return text, 2

    @classmethod
    def _strong_toc_line(cls, line: str) -> bool:
        stripped = line.strip()
        return bool(
            _PAGE_SUFFIX.search(stripped)
            or _PART.match(stripped)
            or _CHAPTER.match(stripped)
            or _SECTION.match(stripped)
            or _SUBSECTION.match(stripped)
            or _DECIMAL.match(stripped)
        )

    @classmethod
    def _entry_density(cls, lines: tuple[str, ...]) -> float:
        return sum(cls._toc_entry(line) is not None for line in lines) / len(lines)

    @staticmethod
    def _lines(block: Block) -> tuple[str, ...]:
        if isinstance(block, (HeadingBlock, TextBlock, CaptionBlock)):
            text = block.text
        elif isinstance(block, TableBlock):
            text = "\n".join("  ".join(row) for row in block.rows)
        else:
            return ()
        return tuple(line for line in text.splitlines() if line.strip())

    @classmethod
    def _heading_level(
        cls,
        heading: HeadingBlock,
        toc_levels: dict[str, int],
        canonical_levels_informative: bool,
    ) -> int:
        if canonical_levels_informative:
            return min(4, heading.level)
        normalized = cls._normalize(heading.text)
        if normalized in toc_levels:
            return toc_levels[normalized]
        kind = cls._heading_kind(heading.text)
        if kind == "part":
            return 1
        if kind == "chapter":
            return 2
        decimal = _DECIMAL.match(heading.text.strip())
        if decimal:
            return min(4, decimal.group(1).count(".") + 2)
        return min(4, heading.level)

    @staticmethod
    def _heading_kind(text: str) -> str:
        stripped = text.strip()
        if _PART.match(stripped):
            return "part"
        if _CHAPTER.match(stripped):
            return "chapter"
        if _MAJOR_MATTER.match(stripped):
            return "matter"
        return "other"

    @staticmethod
    def _normalize(text: str) -> str:
        without_page = _PAGE_SUFFIX.sub("", text.strip())
        return " ".join(without_page.casefold().strip(" .:\t").split())

    @staticmethod
    def _is_verbatim(block: TextBlock) -> bool:
        for key in _VERBATIM_KEYS:
            value = block.metadata.get(key)
            if isinstance(value, str) and value.casefold() in _VERBATIM_ROLES:
                return True
        return False
