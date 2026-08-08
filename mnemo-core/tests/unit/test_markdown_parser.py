"""Unit tests for the MarkdownParser (Module 3.4)."""

import pytest
from mnemo.interfaces.parser_models import (
    ParseResult,
    RawCodeBlock,
    RawHeadingBlock,
    RawImageBlock,
    RawListBlock,
    RawTableBlock,
    RawTextBlock,
)
from mnemo.interfaces.types import FileMetadata
from mnemo.parsers.markdown import MarkdownParser

_SHA256 = "a" * 64


def _parse(parser: MarkdownParser, data: bytes, metadata: FileMetadata) -> ParseResult:
    return parser.parse(data, "test.md", metadata)


@pytest.fixture
def parser() -> MarkdownParser:
    """Provide a fresh MarkdownParser instance."""
    return MarkdownParser()


@pytest.fixture
def metadata() -> FileMetadata:
    """Provide valid FileMetadata for tests."""
    return FileMetadata(
        content_hash=_SHA256,
        size_bytes=1024,
        mime_type="text/markdown",
    )


# ── Empty / trivial inputs ─────────────────────────────────────────────────


def test_empty_bytes_returns_empty_result(parser: MarkdownParser, metadata: FileMetadata) -> None:
    """An empty byte stream produces an empty ParseResult."""
    result = _parse(parser, b"", metadata)
    assert isinstance(result, ParseResult)
    assert result.blocks == ()
    assert result.extracted_assets == ()


def test_whitespace_only_returns_empty_result(
    parser: MarkdownParser, metadata: FileMetadata
) -> None:
    """Whitespace-only input produces an empty ParseResult."""
    result = _parse(parser, b"   \n\t  ", metadata)
    assert result.blocks == ()
    assert result.extracted_assets == ()


def test_invalid_utf8_raises_contract_error(parser: MarkdownParser, metadata: FileMetadata) -> None:
    """Invalid UTF-8 raises ContractValidationError."""
    from mnemo.interfaces.errors import ContractValidationError

    with pytest.raises(ContractValidationError):
        _parse(parser, b"\xff\xfe invalid", metadata)


# ── Headings ───────────────────────────────────────────────────────────────


def test_heading_level_1(parser: MarkdownParser, metadata: FileMetadata) -> None:
    """ATX heading level 1 is extracted correctly."""
    result = _parse(parser, b"# Main Title\n", metadata)
    assert len(result.blocks) == 1
    h = result.blocks[0]
    assert isinstance(h, RawHeadingBlock)
    assert h.level == 1
    assert h.text == "Main Title"
    assert h.ordinal == 0


def test_heading_levels(parser: MarkdownParser, metadata: FileMetadata) -> None:
    """ATX headings of levels 1-3 are each extracted with correct level."""
    md = b"# H1\n\n## H2\n\n### H3\n"
    result = _parse(parser, md, metadata)
    assert len(result.blocks) == 3
    for i, level in enumerate([1, 2, 3]):
        assert isinstance(result.blocks[i], RawHeadingBlock)
        assert result.blocks[i].level == level


# ── Paragraphs / text ──────────────────────────────────────────────────────


def test_single_paragraph(parser: MarkdownParser, metadata: FileMetadata) -> None:
    """A single paragraph produces one RawTextBlock."""
    result = _parse(parser, b"Hello world.\n", metadata)
    assert len(result.blocks) == 1
    assert isinstance(result.blocks[0], RawTextBlock)
    assert result.blocks[0].text == "Hello world."


def test_multiple_paragraphs(parser: MarkdownParser, metadata: FileMetadata) -> None:
    """Two blank-line-separated paragraphs produce two RawTextBlocks."""
    md = b"First paragraph.\n\nSecond paragraph.\n"
    result = _parse(parser, md, metadata)
    assert len(result.blocks) == 2
    assert result.blocks[0].text == "First paragraph."  # type: ignore[union-attr]
    assert result.blocks[1].text == "Second paragraph."  # type: ignore[union-attr]


def test_heading_then_paragraph(parser: MarkdownParser, metadata: FileMetadata) -> None:
    """Heading followed by paragraph produces blocks in correct order."""
    md = b"# Title\n\nSome text.\n"
    result = _parse(parser, md, metadata)
    assert len(result.blocks) == 2
    assert isinstance(result.blocks[0], RawHeadingBlock)
    assert isinstance(result.blocks[1], RawTextBlock)
    assert result.blocks[0].ordinal == 0
    assert result.blocks[1].ordinal == 1


# ── Lists ──────────────────────────────────────────────────────────────────


def test_bullet_list(parser: MarkdownParser, metadata: FileMetadata) -> None:
    """A bullet list is extracted as a single RawListBlock with all items."""
    md = b"* Alpha\n* Beta\n* Gamma\n"
    result = _parse(parser, md, metadata)
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert isinstance(block, RawListBlock)
    assert block.items == ("Alpha", "Beta", "Gamma")
    assert block.ordinal == 0


def test_ordered_list(parser: MarkdownParser, metadata: FileMetadata) -> None:
    """An ordered list is extracted as a single RawListBlock."""
    md = b"1. First\n2. Second\n3. Third\n"
    result = _parse(parser, md, metadata)
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert isinstance(block, RawListBlock)
    assert block.items == ("First", "Second", "Third")


def test_nested_list_flattened_per_item(parser: MarkdownParser, metadata: FileMetadata) -> None:
    """Nested list items are merged into the parent item text."""
    md = b"* Item 1\n* Item 2\n  * Sub A\n"
    result = _parse(parser, md, metadata)
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert isinstance(block, RawListBlock)
    # "Item 1" and "Item 2\nSub A" — nested items appended with newline
    assert block.items[0] == "Item 1"
    assert "Item 2" in block.items[1]
    assert "Sub A" in block.items[1]


# ── Code blocks ────────────────────────────────────────────────────────────


def test_fenced_code_block_with_language(parser: MarkdownParser, metadata: FileMetadata) -> None:
    """Fenced code block is extracted with language in code_language field."""
    md = b"```python\nprint('hello')\n```\n"
    result = _parse(parser, md, metadata)
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert isinstance(block, RawCodeBlock)
    assert block.code_language == "python"
    assert "print" in block.code


def test_fenced_code_block_no_language(parser: MarkdownParser, metadata: FileMetadata) -> None:
    """Fenced code block without info string has code_language=None."""
    md = b"```\nsome code\n```\n"
    result = _parse(parser, md, metadata)
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert isinstance(block, RawCodeBlock)
    assert block.code_language is None
    assert block.code == "some code"


def test_code_block_ordinal_after_paragraph(parser: MarkdownParser, metadata: FileMetadata) -> None:
    """Code block following a paragraph has ordinal=1."""
    md = b"Text before.\n\n```python\nx = 1\n```\n"
    result = _parse(parser, md, metadata)
    assert len(result.blocks) == 2
    assert isinstance(result.blocks[0], RawTextBlock)
    assert isinstance(result.blocks[1], RawCodeBlock)
    assert result.blocks[1].ordinal == 1


# ── Tables ─────────────────────────────────────────────────────────────────


def test_table_header_and_data_rows(parser: MarkdownParser, metadata: FileMetadata) -> None:
    """A GFM table is extracted with header_row_count=1 and all rows."""
    md = b"| Name | Age |\n|---|---|\n| Alice | 30 |\n| Bob | 25 |\n"
    result = _parse(parser, md, metadata)
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert isinstance(block, RawTableBlock)
    assert block.header_row_count == 1
    assert block.rows == (
        ("Name", "Age"),
        ("Alice", "30"),
        ("Bob", "25"),
    )


# ── Images ─────────────────────────────────────────────────────────────────


def test_remote_image_produces_raw_image_block_no_asset(
    parser: MarkdownParser, metadata: FileMetadata
) -> None:
    """A remote image URL produces an RawImageBlock with no TransientAsset."""
    md = b"![Alt text](https://example.com/img.png)\n"
    result = _parse(parser, md, metadata)
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert isinstance(block, RawImageBlock)
    assert block.alt_text == "Alt text"
    assert block.parser_local_id == "image-0"
    assert result.extracted_assets == ()


def test_data_uri_image_produces_transient_asset(
    parser: MarkdownParser, metadata: FileMetadata
) -> None:
    """A data-URI image produces both a RawImageBlock and a TransientAsset."""
    # Minimal valid 1-byte PNG-like base64 payload for testing
    b64 = "iVBORw0KGgo="
    md = f"![Inline](data:image/png;base64,{b64})\n".encode()
    result = _parse(parser, md, metadata)
    assert len(result.blocks) == 1
    assert isinstance(result.blocks[0], RawImageBlock)
    assert result.blocks[0].parser_local_id == "image-0"
    assert len(result.extracted_assets) == 1
    asset = result.extracted_assets[0]
    assert asset.parser_local_id == "image-0"
    assert asset.mime_type == "image/png"


# ── Blockquotes ────────────────────────────────────────────────────────────


def test_blockquote_produces_text_block(parser: MarkdownParser, metadata: FileMetadata) -> None:
    """Blockquote lines are collapsed into a single RawTextBlock."""
    md = b"> First line.\n> Second line.\n"
    result = _parse(parser, md, metadata)
    assert len(result.blocks) == 1
    assert isinstance(result.blocks[0], RawTextBlock)
    text = result.blocks[0].text
    assert "First line." in text
    assert "Second line." in text


# ── ParseResult contract ───────────────────────────────────────────────────


def test_ordinals_are_contiguous(parser: MarkdownParser, metadata: FileMetadata) -> None:
    """Block ordinals must be contiguous starting from 0."""
    md = b"# H1\n\nParagraph.\n\n* A\n* B\n"
    result = _parse(parser, md, metadata)
    ordinals = [b.ordinal for b in result.blocks]
    assert ordinals == list(range(len(result.blocks)))


def test_blocks_and_assets_are_tuples(parser: MarkdownParser, metadata: FileMetadata) -> None:
    """ParseResult.blocks and .extracted_assets are tuples."""
    result = _parse(parser, b"Hello.\n", metadata)
    assert isinstance(result.blocks, tuple)
    assert isinstance(result.extracted_assets, tuple)


def test_metadata_content_hash_propagated(parser: MarkdownParser, metadata: FileMetadata) -> None:
    """DocumentMetadata.content_hash matches the input FileMetadata."""
    result = _parse(parser, b"# Test\n", metadata)
    assert result.metadata.content_hash == metadata.content_hash


def test_doc_type_is_generic(parser: MarkdownParser, metadata: FileMetadata) -> None:
    """ParseResult.doc_type is DocType.GENERIC for Markdown."""
    from mnemo.models import DocType

    result = _parse(parser, b"Hello.\n", metadata)
    assert result.doc_type == DocType.GENERIC


def test_language_is_en(parser: MarkdownParser, metadata: FileMetadata) -> None:
    """ParseResult.language is 'en' (default, no language detection)."""
    result = _parse(parser, b"Hello.\n", metadata)
    assert result.language == "en"
