"""Deterministic Slides semantic chunking strategy."""

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

_ROLES = frozenset({"title", "body", "notes", "section_divider"})


class SlidesChunker:
    """Chunk Slides documents at atomic, source-ordered slide boundaries."""

    @property
    def supported_doc_types(self) -> tuple[DocType, ...]:
        """Return the sole classification owned by this strategy."""
        return (DocType.SLIDES,)

    def capabilities(self) -> ChunkerCapabilities:
        """Describe the strategy's implemented behavior."""
        return ChunkerCapabilities(
            supported_doc_types=self.supported_doc_types,
            preserves_semantic_boundaries=True,
            supports_parent_child=False,
            supports_overlap=False,
            metadata=FrozenMetadata({"chunker.slides.version": "v1"}),
        )

    def chunk(
        self,
        document: ParsedDocument,
        context: ChunkingContext,
        token_counter: TokenCounterInterfaceV1,
    ) -> tuple[ChunkDraft, ...]:
        """Return ordered root drafts aligned with atomic slide boundaries."""
        if not isinstance(document, ParsedDocument):
            raise TypeError("document must be ParsedDocument")
        if not isinstance(context, ChunkingContext):
            raise TypeError("context must be ChunkingContext")
        if not isinstance(token_counter, TokenCounterInterfaceV1):
            raise TypeError("token_counter must satisfy TokenCounterInterfaceV1")
        if document.doc_type is not DocType.SLIDES:
            raise UnsupportedError("SlidesChunker supports only DocType.SLIDES")
        if document.metadata.metadata.get("parser.slide.schema_version") != 1:
            raise UnsupportedError("SlidesChunker requires parser.slide.schema_version == 1")

        slides = self._group_slides(document)
        drafts: list[ChunkDraft] = []
        section_index = 0
        section_counts: dict[int, int] = {}

        for slide_index, (slide_number, blocks) in enumerate(slides):
            title_flags = tuple(
                block.metadata.get("parser.slide.is_title_slide", False) for block in blocks
            )
            if any(not isinstance(flag, bool) for flag in title_flags):
                raise UnsupportedError("parser.slide.is_title_slide must be a boolean")
            if len(set(title_flags)) != 1 or title_flags[0] != (slide_index == 0):
                raise UnsupportedError("Slides title-slide metadata is inconsistent")
            is_title_slide = title_flags[0]

            title_parts: list[str] = []
            body_parts: list[str] = []
            notes_parts: list[str] = []
            roles: list[str] = []
            asset_ids: list[str] = []
            is_section_divider = False

            for block in blocks:
                role = block.metadata.get("parser.slide.role")
                if not isinstance(role, str) or role not in _ROLES:
                    raise UnsupportedError("parser.slide.role is missing or invalid")
                roles.append(role)
                if role == "section_divider":
                    is_section_divider = True
                if isinstance(block, ImageBlock):
                    asset_ids.append(str(block.asset_id))

                text = self._extract_text(block)
                if not text:
                    continue
                if role in {"title", "section_divider"}:
                    title_parts.append(text)
                elif role == "notes":
                    notes_parts.append(text)
                else:
                    body_parts.append(text)

            if is_section_divider and not is_title_slide:
                section_index += 1
            chunk_index = section_counts.get(section_index, 0)
            section_counts[section_index] = chunk_index + 1

            text_parts: list[str] = []
            if title_parts:
                text_parts.append("Title: " + " ".join(title_parts))
            if body_parts:
                text_parts.append(" ".join(body_parts))
            if notes_parts:
                text_parts.append("Speaker Notes: " + " ".join(notes_parts))
            text = "\n\n".join(text_parts)
            if not text:
                raise UnsupportedError(
                    "slide has no source-authored textual representation for a ChunkDraft"
                )
            if token_counter.count(text) > context.effective_max_tokens:
                raise UnsupportedError("atomic slide exceeds the effective token maximum")

            metadata: dict[str, object] = {
                "chunker.slides.strategy": "atomic",
                "chunker.slides.slide_number": slide_number,
                "chunker.slides.is_title_slide": is_title_slide,
                "chunker.slides.roles": tuple(roles),
            }
            if asset_ids:
                metadata["chunker.slides.asset_ids"] = tuple(asset_ids)

            drafts.append(
                ChunkDraft(
                    text=text,
                    chunk_type=ChunkType.SUMMARY if is_title_slide else ChunkType.PASSAGE,
                    position=ChunkPosition(
                        section_index=section_index,
                        chunk_index_in_section=chunk_index,
                        page_number=blocks[0].page_number,
                    ),
                    heading_path=tuple(title_parts),
                    source_span=BlockSpan(
                        start_ordinal=blocks[0].ordinal,
                        end_ordinal=blocks[-1].ordinal,
                    ),
                    parent_index=None,
                    metadata=FrozenMetadata(metadata),
                )
            )

        return tuple(drafts)

    @staticmethod
    def _group_slides(document: ParsedDocument) -> tuple[tuple[int, tuple[Block, ...]], ...]:
        groups: list[tuple[int, tuple[Block, ...]]] = []
        current_number: int | None = None
        current_blocks: list[Block] = []
        seen: set[int] = set()

        for block in document.blocks:
            number = block.metadata.get("parser.slide.number")
            if isinstance(number, bool) or not isinstance(number, int) or number < 1:
                raise UnsupportedError("parser.slide.number must be a positive integer")
            if current_number is None:
                current_number = number
                seen.add(number)
            elif number != current_number:
                if number in seen or number != current_number + 1:
                    raise UnsupportedError(
                        "parser.slide.number values must form contiguous source-ordered groups"
                    )
                groups.append((current_number, tuple(current_blocks)))
                current_blocks = []
                current_number = number
                seen.add(number)
            current_blocks.append(block)

        if current_number is not None:
            groups.append((current_number, tuple(current_blocks)))
        return tuple(groups)

    @staticmethod
    def _extract_text(block: Block) -> str:
        if isinstance(block, TableBlock):
            return "\n".join("\t".join(row) for row in block.rows).strip()
        if isinstance(block, EquationBlock):
            return block.latex.strip()
        if isinstance(block, ImageBlock):
            return block.alt_text.strip() if block.alt_text is not None else ""
        if isinstance(block, (TextBlock, HeadingBlock, CaptionBlock)):
            return block.text.strip()
        if isinstance(block, CodeBlock):
            return block.code.strip()
        raise UnsupportedError(f"unsupported canonical slide block: {type(block).__name__}")
