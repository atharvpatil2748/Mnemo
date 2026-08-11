"""Tests for the deterministic Documentation chunking strategy."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from mnemo.chunkers.documentation import DocumentationChunker
from mnemo.interfaces import (
    ChunkerInterfaceV2,
    ChunkingContext,
    ChunkingOptions,
    TokenCounterInterfaceV1,
)
from mnemo.interfaces.errors import UnsupportedError
from mnemo.models import (
    Block,
    BlockSpan,
    CaptionBlock,
    ChunkType,
    CodeBlock,
    DocType,
    DocumentMetadata,
    DocumentVersion,
    DocumentVersionStatus,
    EquationBlock,
    FrozenMetadata,
    HeadingBlock,
    ImageBlock,
    ParsedDocument,
    TableBlock,
    TextBlock,
)

_HASH = "0" * 64


class WordCounter(TokenCounterInterfaceV1):
    """Deterministic test counter with explicit word boundaries."""

    @property
    def tokenizer_id(self) -> str:
        return "word-counter-v1"

    def count(self, text: str) -> int:
        return len(text.split())

    def split_to_limit(self, text: str, limit: int) -> tuple[str, str]:
        words = text.split()
        return " ".join(words[:limit]), " ".join(words[limit:])


def _context(*, target: int = 500, maximum: int = 1000) -> ChunkingContext:
    return ChunkingContext(
        document_version=DocumentVersion(
            version_id=UUID("11111111-1111-4111-8111-111111111111"),
            document_id=UUID("22222222-2222-4222-8222-222222222222"),
            content_hash=_HASH,
            metadata=DocumentMetadata(content_hash=_HASH),
            status=DocumentVersionStatus.CURRENT,
            created_at=datetime(2026, 8, 12, tzinfo=UTC),
        ),
        options=ChunkingOptions(target_tokens=target, max_tokens=maximum),
    )


def _document(*blocks: Block) -> ParsedDocument:
    return ParsedDocument(
        blocks=blocks,
        metadata=DocumentMetadata(
            content_hash=_HASH,
            metadata=FrozenMetadata({"parser.documentation.schema_version": 1}),
        ),
        language="en",
        doc_type=DocType.DOCUMENTATION,
    )


def test_documentation_topics_api_callouts_and_tasks_remain_isolated() -> None:
    document = _document(
        HeadingBlock(ordinal=0, text="Introduction", level=1),
        TextBlock(ordinal=1, text="This is intro text."),
        HeadingBlock(
            ordinal=2,
            text="API Reference",
            level=1,
            metadata=FrozenMetadata({"parser.documentation.role": "api_reference"}),
        ),
        TextBlock(
            ordinal=3,
            text="Here is the API.",
            metadata=FrozenMetadata({"parser.documentation.role": "api_reference"}),
        ),
        TextBlock(
            ordinal=4,
            text="Some warning text",
            metadata=FrozenMetadata(
                {
                    "parser.documentation.role": "callout",
                    "parser.documentation.callout_type": "warning",
                }
            ),
        ),
        TextBlock(ordinal=5, text="Ordinary follow-up prose."),
        TextBlock(
            ordinal=6,
            text="step 1\nstep 2",
            metadata=FrozenMetadata({"parser.documentation.role": "task_block"}),
        ),
    )

    drafts = DocumentationChunker().chunk(document, _context(), WordCounter())

    assert tuple(draft.text for draft in drafts) == (
        "Introduction\n\nThis is intro text.",
        "API Reference\n\nHere is the API.",
        "Some warning text",
        "Ordinary follow-up prose.",
        "step 1\nstep 2",
    )
    assert drafts[2].metadata["chunker.documentation.role"] == "callout"
    assert drafts[2].metadata["chunker.documentation.callout_type"] == "warning"
    assert drafts[4].metadata["chunker.documentation.role"] == "task_block"
    assert drafts[0].heading_path == ("Introduction",)
    assert drafts[1].heading_path == ("API Reference",)


def test_documentation_long_prose_splits_at_safe_words_with_shared_provenance() -> None:
    text = " ".join(f"word{index}" for index in range(45))
    document = _document(TextBlock(ordinal=0, text=text))

    drafts = DocumentationChunker().chunk(document, _context(target=15, maximum=20), WordCounter())

    assert len(drafts) == 3
    assert all(WordCounter().count(draft.text) <= 20 for draft in drafts)
    assert all(draft.source_span == BlockSpan(start_ordinal=0, end_ordinal=0) for draft in drafts)
    assert " ".join(draft.text for draft in drafts) == text


def test_documentation_oversized_atomic_task_fails_closed() -> None:
    block = TextBlock(
        ordinal=0,
        text=" ".join("step" for _ in range(21)),
        metadata=FrozenMetadata({"parser.documentation.role": "task_block"}),
    )

    with pytest.raises(UnsupportedError, match="atomic documentation task_block"):
        DocumentationChunker().chunk(
            _document(block), _context(target=15, maximum=20), WordCounter()
        )


def test_documentation_image_reference_is_preserved() -> None:
    asset_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    document = _document(ImageBlock(ordinal=0, asset_id=asset_id, alt_text="Configuration diagram"))

    draft = DocumentationChunker().chunk(document, _context(), WordCounter())[0]

    assert draft.text == "Configuration diagram"
    assert draft.metadata["chunker.documentation.asset_ids"] == (str(asset_id),)


def test_documentation_rejects_missing_image_text_and_malformed_metadata() -> None:
    image = ImageBlock(
        ordinal=0,
        asset_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
    )
    with pytest.raises(UnsupportedError, match="no source-authored textual representation"):
        DocumentationChunker().chunk(_document(image), _context(), WordCounter())

    malformed = TextBlock(
        ordinal=0,
        text="content",
        metadata=FrozenMetadata({"parser.documentation.role": "unknown"}),
    )
    with pytest.raises(UnsupportedError, match="role is invalid"):
        DocumentationChunker().chunk(_document(malformed), _context(), WordCounter())


def test_documentation_output_is_immutable_and_deterministic() -> None:
    document = _document(TextBlock(ordinal=0, text="Stable documentation content."))
    chunker = DocumentationChunker()

    first = chunker.chunk(document, _context(), WordCounter())
    second = chunker.chunk(document, _context(), WordCounter())

    assert first == second
    assert isinstance(first, tuple)


def test_documentation_v2_contract_and_capabilities() -> None:
    chunker = DocumentationChunker()

    assert isinstance(chunker, ChunkerInterfaceV2)
    assert chunker.supported_doc_types == (DocType.DOCUMENTATION,)
    assert chunker.capabilities().preserves_semantic_boundaries is True
    assert chunker.capabilities().supports_parent_child is False

    generic = ParsedDocument(
        blocks=(),
        metadata=DocumentMetadata(content_hash=_HASH),
        language="en",
        doc_type=DocType.GENERIC,
    )
    with pytest.raises(UnsupportedError, match=r"supports only DocType\.DOCUMENTATION"):
        chunker.chunk(generic, _context(), WordCounter())

    missing_schema = ParsedDocument(
        blocks=(),
        metadata=DocumentMetadata(content_hash=_HASH),
        language="en",
        doc_type=DocType.DOCUMENTATION,
    )
    with pytest.raises(UnsupportedError, match="schema_version == 1"):
        chunker.chunk(missing_schema, _context(), WordCounter())


def test_documentation_preserves_canonical_special_blocks() -> None:
    document = _document(
        TableBlock(ordinal=0, rows=(("name", "value"), ("mode", "safe"))),
        EquationBlock(ordinal=1, latex="x^2 + y^2"),
        CodeBlock(ordinal=2, code="mnemo start", code_language="shell"),
        CaptionBlock(ordinal=3, text="Configuration output"),
    )

    drafts = DocumentationChunker().chunk(document, _context(), WordCounter())

    assert tuple(draft.chunk_type for draft in drafts) == (
        ChunkType.PASSAGE,
        ChunkType.EQUATION,
        ChunkType.CODE,
        ChunkType.PASSAGE,
    )
    assert tuple(draft.text for draft in drafts) == (
        "name\tvalue\nmode\tsafe",
        "x^2 + y^2",
        "mnemo start",
        "Configuration output",
    )


def test_documentation_oversized_paragraph_prefers_sentence_boundaries() -> None:
    first = " ".join(("First",) + ("alpha",) * 13 + ("ends.",))
    second = " ".join(("Second",) + ("beta",) * 13 + ("ends.",))
    document = _document(TextBlock(ordinal=0, text=f"{first} {second}"))

    drafts = DocumentationChunker().chunk(document, _context(target=15, maximum=30), WordCounter())

    assert tuple(draft.text for draft in drafts) == (first, second)
    assert all(draft.source_span == BlockSpan(start_ordinal=0, end_ordinal=0) for draft in drafts)
