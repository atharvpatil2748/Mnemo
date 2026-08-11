import uuid
from datetime import UTC, datetime

import pytest
from mnemo.chunkers.slides import SlidesChunker
from mnemo.interfaces import (
    ChunkerInterfaceV2,
    ChunkingContext,
    TokenCounterInterfaceV1,
    UnsupportedError,
)
from mnemo.interfaces.types import ChunkingOptions
from mnemo.models import (
    ChunkType,
    CodeBlock,
    DocType,
    DocumentMetadata,
    DocumentVersion,
    DocumentVersionStatus,
    FrozenMetadata,
    HeadingBlock,
    ImageBlock,
    ParsedDocument,
    TableBlock,
    TextBlock,
)


class DummyTokenCounter(TokenCounterInterfaceV1):
    @property
    def tokenizer_id(self) -> str:
        return "dummy"

    def count(self, text: str) -> int:
        return len(text.split())

    def split_to_limit(self, text: str, limit: int) -> tuple[str, str]:
        words = text.split()
        return " ".join(words[:limit]), " ".join(words[limit:])


@pytest.fixture
def chunker() -> SlidesChunker:
    return SlidesChunker()


@pytest.fixture
def context() -> ChunkingContext:
    options = ChunkingOptions(
        target_tokens=100,
        max_tokens=500,
        overlap_tokens=0,
    )
    return ChunkingContext(
        document_version=DocumentVersion(
            document_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            metadata=DocumentMetadata(
                content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            ),
            status=DocumentVersionStatus.CURRENT,
            created_at=datetime.now(UTC),
        ),
        options=options,
    )


@pytest.fixture
def token_counter() -> TokenCounterInterfaceV1:
    return DummyTokenCounter()


def test_slides_chunker_basic(
    chunker: SlidesChunker, context: ChunkingContext, token_counter: TokenCounterInterfaceV1
) -> None:
    # 2 slides
    blocks = (
        # Slide 1 (title slide)
        HeadingBlock(
            ordinal=0,
            text="Main Title",
            level=1,
            page_number=1,
            metadata=FrozenMetadata(
                {
                    "parser.slide.number": 1,
                    "parser.slide.is_title_slide": True,
                    "parser.slide.role": "title",
                }
            ),
        ),
        TextBlock(
            ordinal=1,
            text="Subtitle",
            page_number=1,
            metadata=FrozenMetadata(
                {
                    "parser.slide.number": 1,
                    "parser.slide.is_title_slide": True,
                    "parser.slide.role": "body",
                }
            ),
        ),
        TextBlock(
            ordinal=2,
            text="Welcome everyone.",
            page_number=1,
            metadata=FrozenMetadata(
                {
                    "parser.slide.number": 1,
                    "parser.slide.is_title_slide": True,
                    "parser.slide.role": "notes",
                }
            ),
        ),
        # Slide 2 (body slide)
        HeadingBlock(
            ordinal=3,
            text="Agenda",
            level=1,
            page_number=2,
            metadata=FrozenMetadata({"parser.slide.number": 2, "parser.slide.role": "title"}),
        ),
        TextBlock(
            ordinal=4,
            text="Point 1",
            page_number=2,
            metadata=FrozenMetadata({"parser.slide.number": 2, "parser.slide.role": "body"}),
        ),
        TextBlock(
            ordinal=5,
            text="Point 2",
            page_number=2,
            metadata=FrozenMetadata({"parser.slide.number": 2, "parser.slide.role": "body"}),
        ),
    )

    doc = ParsedDocument(
        blocks=blocks,
        metadata=DocumentMetadata(
            content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            metadata=FrozenMetadata({"parser.slide.schema_version": 1}),
        ),
        language="en",
        doc_type=DocType.SLIDES,
    )

    drafts = chunker.chunk(doc, context, token_counter)

    assert len(drafts) == 2

    # Draft 0 (Slide 1)
    assert drafts[0].chunk_type == ChunkType.SUMMARY
    assert drafts[0].position.section_index == 0
    assert drafts[0].position.chunk_index_in_section == 0
    assert drafts[0].heading_path == ("Main Title",)
    assert "Title: Main Title" in drafts[0].text
    assert "Subtitle" in drafts[0].text
    assert "Speaker Notes: Welcome everyone." in drafts[0].text
    assert drafts[0].source_span.start_ordinal == 0
    assert drafts[0].source_span.end_ordinal == 2

    # Draft 1 (Slide 2)
    assert drafts[1].chunk_type == ChunkType.PASSAGE
    assert drafts[1].position.section_index == 0
    assert drafts[1].position.chunk_index_in_section == 1
    assert drafts[1].heading_path == ("Agenda",)
    assert "Title: Agenda" in drafts[1].text
    assert "Point 1 Point 2" in drafts[1].text
    assert "Speaker Notes:" not in drafts[1].text
    assert drafts[1].source_span.start_ordinal == 3
    assert drafts[1].source_span.end_ordinal == 5


def test_slides_chunker_section_divider(
    chunker: SlidesChunker, context: ChunkingContext, token_counter: TokenCounterInterfaceV1
) -> None:
    blocks = (
        # Slide 1 (title slide)
        HeadingBlock(
            ordinal=0,
            text="Main Title",
            level=1,
            page_number=1,
            metadata=FrozenMetadata(
                {
                    "parser.slide.number": 1,
                    "parser.slide.is_title_slide": True,
                    "parser.slide.role": "title",
                }
            ),
        ),
        # Slide 2 (section divider)
        HeadingBlock(
            ordinal=1,
            text="Part 1",
            level=1,
            page_number=2,
            metadata=FrozenMetadata(
                {"parser.slide.number": 2, "parser.slide.role": "section_divider"}
            ),
        ),
        # Slide 3 (body slide in section)
        TextBlock(
            ordinal=2,
            text="Content",
            page_number=3,
            metadata=FrozenMetadata({"parser.slide.number": 3, "parser.slide.role": "body"}),
        ),
    )

    doc = ParsedDocument(
        blocks=blocks,
        metadata=DocumentMetadata(
            content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            metadata=FrozenMetadata({"parser.slide.schema_version": 1}),
        ),
        language="en",
        doc_type=DocType.SLIDES,
    )

    drafts = chunker.chunk(doc, context, token_counter)

    assert len(drafts) == 3

    assert drafts[0].position.section_index == 0
    assert drafts[0].position.chunk_index_in_section == 0

    assert drafts[1].position.section_index == 1
    assert drafts[1].position.chunk_index_in_section == 0

    assert drafts[2].position.section_index == 1
    assert drafts[2].position.chunk_index_in_section == 1


def test_slides_chunker_hard_max_exceeded(
    chunker: SlidesChunker, context: ChunkingContext, token_counter: TokenCounterInterfaceV1
) -> None:
    # A single slide that exceeds 500 words
    long_text = "word " * 600
    blocks = (
        TextBlock(
            ordinal=0,
            text=long_text,
            page_number=1,
            metadata=FrozenMetadata(
                {
                    "parser.slide.number": 1,
                    "parser.slide.is_title_slide": True,
                    "parser.slide.role": "body",
                }
            ),
        ),
    )
    doc = ParsedDocument(
        blocks=blocks,
        metadata=DocumentMetadata(
            content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            metadata=FrozenMetadata({"parser.slide.schema_version": 1}),
        ),
        language="en",
        doc_type=DocType.SLIDES,
    )

    with pytest.raises(UnsupportedError, match="exceeds the effective token maximum"):
        chunker.chunk(doc, context, token_counter)


def test_slides_preserves_canonical_image_reference(
    chunker: SlidesChunker, context: ChunkingContext, token_counter: TokenCounterInterfaceV1
) -> None:
    asset_id = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    blocks = (
        HeadingBlock(
            ordinal=0,
            text="Architecture",
            level=1,
            page_number=1,
            metadata=FrozenMetadata(
                {
                    "parser.slide.number": 1,
                    "parser.slide.is_title_slide": True,
                    "parser.slide.role": "title",
                }
            ),
        ),
        ImageBlock(
            ordinal=1,
            asset_id=asset_id,
            alt_text="System architecture diagram",
            page_number=1,
            metadata=FrozenMetadata(
                {
                    "parser.slide.number": 1,
                    "parser.slide.is_title_slide": True,
                    "parser.slide.role": "body",
                }
            ),
        ),
    )
    document = ParsedDocument(
        blocks=blocks,
        metadata=DocumentMetadata(
            content_hash=context.document_version.content_hash,
            metadata=FrozenMetadata({"parser.slide.schema_version": 1}),
        ),
        language="en",
        doc_type=DocType.SLIDES,
    )

    draft = chunker.chunk(document, context, token_counter)[0]

    assert "System architecture diagram" in draft.text
    assert draft.metadata["chunker.slides.asset_ids"] == (str(asset_id),)


def test_slides_rejects_noncontiguous_source_order(
    chunker: SlidesChunker, context: ChunkingContext, token_counter: TokenCounterInterfaceV1
) -> None:
    blocks = tuple(
        TextBlock(
            ordinal=index,
            text=f"slide {number}",
            metadata=FrozenMetadata(
                {
                    "parser.slide.number": number,
                    "parser.slide.is_title_slide": index == 0,
                    "parser.slide.role": "body",
                }
            ),
        )
        for index, number in enumerate((1, 2, 1))
    )
    document = ParsedDocument(
        blocks=blocks,
        metadata=DocumentMetadata(
            content_hash=context.document_version.content_hash,
            metadata=FrozenMetadata({"parser.slide.schema_version": 1}),
        ),
        language="en",
        doc_type=DocType.SLIDES,
    )

    with pytest.raises(UnsupportedError, match="contiguous source-ordered groups"):
        chunker.chunk(document, context, token_counter)


def test_slides_rejects_image_only_slide_without_source_text(
    chunker: SlidesChunker, context: ChunkingContext, token_counter: TokenCounterInterfaceV1
) -> None:
    block = ImageBlock(
        ordinal=0,
        asset_id=uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        metadata=FrozenMetadata(
            {
                "parser.slide.number": 1,
                "parser.slide.is_title_slide": True,
                "parser.slide.role": "body",
            }
        ),
    )
    document = ParsedDocument(
        blocks=(block,),
        metadata=DocumentMetadata(
            content_hash=context.document_version.content_hash,
            metadata=FrozenMetadata({"parser.slide.schema_version": 1}),
        ),
        language="en",
        doc_type=DocType.SLIDES,
    )

    with pytest.raises(UnsupportedError, match="no source-authored textual representation"):
        chunker.chunk(document, context, token_counter)


def test_slides_v2_contract_capabilities_and_schema_validation(
    chunker: SlidesChunker,
    context: ChunkingContext,
    token_counter: TokenCounterInterfaceV1,
) -> None:
    assert isinstance(chunker, ChunkerInterfaceV2)
    assert chunker.supported_doc_types == (DocType.SLIDES,)
    assert chunker.capabilities().preserves_semantic_boundaries is True
    assert chunker.capabilities().supports_parent_child is False

    generic = ParsedDocument(
        blocks=(),
        metadata=DocumentMetadata(content_hash=context.document_version.content_hash),
        language="en",
        doc_type=DocType.GENERIC,
    )
    with pytest.raises(UnsupportedError, match=r"supports only DocType\.SLIDES"):
        chunker.chunk(generic, context, token_counter)

    missing_schema = ParsedDocument(
        blocks=(),
        metadata=DocumentMetadata(content_hash=context.document_version.content_hash),
        language="en",
        doc_type=DocType.SLIDES,
    )
    with pytest.raises(UnsupportedError, match="schema_version == 1"):
        chunker.chunk(missing_schema, context, token_counter)


def test_slides_preserves_canonical_table_and_code_text(
    chunker: SlidesChunker,
    context: ChunkingContext,
    token_counter: TokenCounterInterfaceV1,
) -> None:
    common = FrozenMetadata(
        {
            "parser.slide.number": 1,
            "parser.slide.is_title_slide": True,
            "parser.slide.role": "body",
        }
    )
    document = ParsedDocument(
        blocks=(
            TableBlock(ordinal=0, rows=(("Metric", "Value"), ("Recall", "0.9")), metadata=common),
            CodeBlock(ordinal=1, code="mnemo query", code_language="shell", metadata=common),
        ),
        metadata=DocumentMetadata(
            content_hash=context.document_version.content_hash,
            metadata=FrozenMetadata({"parser.slide.schema_version": 1}),
        ),
        language="en",
        doc_type=DocType.SLIDES,
    )

    draft = chunker.chunk(document, context, token_counter)[0]

    assert "Metric\tValue\nRecall\t0.9" in draft.text
    assert "mnemo query" in draft.text
