"""Deterministic Documentation semantic chunking strategy."""

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
_ROLES = frozenset({"toc", "api_reference", "task_block", "callout"})
_CALLOUT_TYPES = frozenset({"note", "warning", "tip", "caution", "important"})


@dataclass(frozen=True, slots=True)
class _Unit:
    text: str
    chunk_type: ChunkType
    source_span: BlockSpan
    heading_path: tuple[str, ...]
    section_index: int
    page_number: int | None
    role: str | None
    callout_type: str | None = None
    asset_ids: tuple[str, ...] = ()
    separator: str = "\n\n"
    mergeable: bool = True


class DocumentationChunker:
    """Chunk documentation at source-derived task and topic boundaries."""

    @property
    def supported_doc_types(self) -> tuple[DocType, ...]:
        """Return the sole classification owned by this strategy."""
        return (DocType.DOCUMENTATION,)

    def capabilities(self) -> ChunkerCapabilities:
        """Describe the strategy's implemented behavior."""
        return ChunkerCapabilities(
            supported_doc_types=self.supported_doc_types,
            preserves_semantic_boundaries=True,
            supports_parent_child=False,
            supports_overlap=False,
            metadata=FrozenMetadata({"chunker.documentation.version": "v1"}),
        )

    def chunk(
        self,
        document: ParsedDocument,
        context: ChunkingContext,
        token_counter: TokenCounterInterfaceV1,
    ) -> tuple[ChunkDraft, ...]:
        """Return ordered root drafts aligned with documentation boundaries."""
        if not isinstance(document, ParsedDocument):
            raise TypeError("document must be ParsedDocument")
        if not isinstance(context, ChunkingContext):
            raise TypeError("context must be ChunkingContext")
        if not isinstance(token_counter, TokenCounterInterfaceV1):
            raise TypeError("token_counter must satisfy TokenCounterInterfaceV1")
        if document.doc_type is not DocType.DOCUMENTATION:
            raise UnsupportedError("DocumentationChunker supports only DocType.DOCUMENTATION")
        if document.metadata.metadata.get("parser.documentation.schema_version") != 1:
            raise UnsupportedError(
                "DocumentationChunker requires parser.documentation.schema_version == 1"
            )

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
            metadata: dict[str, object] = {"chunker.documentation.strategy": "task-and-topic"}
            if unit.role is not None:
                metadata["chunker.documentation.role"] = unit.role
            if unit.callout_type is not None:
                metadata["chunker.documentation.callout_type"] = unit.callout_type
            if unit.asset_ids:
                metadata["chunker.documentation.asset_ids"] = unit.asset_ids
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
                    metadata=FrozenMetadata(metadata),
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
        section_index = 0
        for block in document.blocks:
            if isinstance(block, HeadingBlock):
                headings = headings[: block.level - 1]
                headings.append(block.text)
                section_index += 1
            result.extend(
                self._block_units(
                    block,
                    tuple(headings),
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
        heading_path: tuple[str, ...],
        section_index: int,
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit, ...]:
        role_value = block.metadata.get("parser.documentation.role")
        if role_value is not None and (not isinstance(role_value, str) or role_value not in _ROLES):
            raise UnsupportedError("parser.documentation.role is invalid")
        role = role_value if isinstance(role_value, str) else None
        callout_value = block.metadata.get("parser.documentation.callout_type")
        if role == "callout":
            if not isinstance(callout_value, str) or callout_value not in _CALLOUT_TYPES:
                raise UnsupportedError("documentation callout type is missing or invalid")
            callout_type = callout_value
        elif callout_value is not None:
            raise UnsupportedError("callout type requires parser.documentation.role=callout")
        else:
            callout_type = None

        span = BlockSpan(start_ordinal=block.ordinal, end_ordinal=block.ordinal)
        text, chunk_type, asset_ids, inherently_atomic = self._block_text(block)
        if not text:
            raise UnsupportedError(
                "documentation block has no source-authored textual representation"
            )
        atomic = inherently_atomic or role in {"task_block", "callout"}
        if atomic:
            if counter.count(text) > hard_max:
                raise UnsupportedError(
                    f"atomic documentation {role or type(block).__name__} exceeds token maximum"
                )
            return (
                _Unit(
                    text=text,
                    chunk_type=chunk_type,
                    source_span=span,
                    heading_path=heading_path,
                    section_index=section_index,
                    page_number=block.page_number,
                    role=role,
                    callout_type=callout_type,
                    asset_ids=asset_ids,
                    mergeable=False,
                ),
            )

        parts = self._text_parts(text, target, hard_max, counter)
        return tuple(
            _Unit(
                text=part,
                chunk_type=chunk_type,
                source_span=span,
                heading_path=heading_path,
                section_index=section_index,
                page_number=block.page_number,
                role=role,
                callout_type=callout_type,
                asset_ids=asset_ids,
                separator="\n\n" if index == 0 else " ",
            )
            for index, part in enumerate(parts)
        )

    @staticmethod
    def _block_text(block: Block) -> tuple[str, ChunkType, tuple[str, ...], bool]:
        if isinstance(block, TableBlock):
            return "\n".join("\t".join(row) for row in block.rows), ChunkType.PASSAGE, (), True
        if isinstance(block, EquationBlock):
            return block.latex, ChunkType.EQUATION, (), True
        if isinstance(block, ImageBlock):
            return block.alt_text or "", ChunkType.CAPTION, (str(block.asset_id),), True
        if isinstance(block, CodeBlock):
            return block.code, ChunkType.CODE, (), True
        if isinstance(block, (TextBlock, HeadingBlock, CaptionBlock)):
            return block.text, ChunkType.PASSAGE, (), False
        raise UnsupportedError(f"unsupported canonical documentation block: {type(block).__name__}")

    def _text_parts(
        self, text: str, target: int, hard_max: int, counter: TokenCounterInterfaceV1
    ) -> tuple[str, ...]:
        result: list[str] = []
        for paragraph in (part.strip() for part in _PARAGRAPH_BOUNDARY.split(text.strip())):
            if not paragraph:
                continue
            if counter.count(paragraph) <= target:
                result.append(paragraph)
                continue
            sentences = tuple(
                part.strip() for part in _SENTENCE_BOUNDARY.split(paragraph) if part.strip()
            )
            if len(sentences) > 1:
                for sentence in sentences:
                    if counter.count(sentence) <= hard_max:
                        result.append(sentence)
                    else:
                        result.extend(self._word_split(sentence, target, hard_max, counter))
            elif counter.count(paragraph) <= hard_max:
                result.append(paragraph)
            else:
                result.extend(self._word_split(paragraph, target, hard_max, counter))
        return tuple(result)

    @staticmethod
    def _word_split(
        text: str, target: int, hard_max: int, counter: TokenCounterInterfaceV1
    ) -> tuple[str, ...]:
        words = tuple(match.group(0) for match in _WORD_WITH_SPACE.finditer(text))
        if not words:
            raise UnsupportedError("documentation text has no safe word boundary")
        result: list[str] = []
        current = ""
        for word_with_space in words:
            word = word_with_space.rstrip()
            if counter.count(word) > hard_max:
                raise UnsupportedError("documentation word exceeds the effective token maximum")
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
            count = counter.count(candidate)
            if DocumentationChunker._can_merge(current, unit) and (
                count <= target or (counter.count(current.text) < 15 and count <= hard_max)
            ):
                current = DocumentationChunker._merge(current, unit, candidate)
            else:
                result.append(current)
                current = unit
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
            and left.role == right.role
            and left.callout_type == right.callout_type
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
            role=left.role,
            callout_type=left.callout_type,
            asset_ids=left.asset_ids + right.asset_ids,
            separator=left.separator,
        )
