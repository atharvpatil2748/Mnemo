"""Unit tests for the PlainTextParser (Module 3.6)."""

import pytest
from mnemo.interfaces.errors import ContractValidationError
from mnemo.interfaces.parser_models import ParseResult, RawTextBlock
from mnemo.interfaces.types import FileMetadata
from mnemo.parsers.plain_text import PlainTextParser

_SHA256 = "a" * 64


@pytest.fixture
def parser() -> PlainTextParser:
    return PlainTextParser()


@pytest.fixture
def metadata() -> FileMetadata:
    return FileMetadata(
        content_hash=_SHA256,
        size_bytes=1024,
        mime_type="text/plain",
    )


def test_supported_formats(parser: PlainTextParser) -> None:
    assert ".txt" in parser.supported_formats
    assert ".md" not in parser.supported_formats
    assert ".log" in parser.supported_formats


def test_capabilities(parser: PlainTextParser) -> None:
    caps = parser.capabilities()
    assert caps.supports_images is False
    assert caps.supports_tables is False


def test_empty_bytes(parser: PlainTextParser, metadata: FileMetadata) -> None:
    result = parser.parse(b"", "empty.txt", metadata)
    assert isinstance(result, ParseResult)
    assert len(result.blocks) == 0


def test_whitespace_only(parser: PlainTextParser, metadata: FileMetadata) -> None:
    result = parser.parse(b"   \n\t  ", "empty.txt", metadata)
    assert len(result.blocks) == 0


def test_invalid_utf8(parser: PlainTextParser, metadata: FileMetadata) -> None:
    with pytest.raises(ContractValidationError, match="valid UTF-8"):
        parser.parse(b"\xff\xfe invalid", "test.txt", metadata)


def test_single_paragraph(parser: PlainTextParser, metadata: FileMetadata) -> None:
    text = b"This is a single paragraph."
    result = parser.parse(text, "test.txt", metadata)

    assert len(result.blocks) == 1
    assert isinstance(result.blocks[0], RawTextBlock)
    assert result.blocks[0].text == "This is a single paragraph."


def test_multiple_paragraphs(parser: PlainTextParser, metadata: FileMetadata) -> None:
    text = b"First paragraph.\n\nSecond paragraph.\n\n\nThird paragraph."
    result = parser.parse(text, "test.txt", metadata)

    assert len(result.blocks) == 3
    b0 = result.blocks[0]
    b1 = result.blocks[1]
    b2 = result.blocks[2]
    assert isinstance(b0, RawTextBlock)
    assert isinstance(b1, RawTextBlock)
    assert isinstance(b2, RawTextBlock)
    assert b0.text == "First paragraph."
    assert b1.text == "Second paragraph."
    assert b2.text == "Third paragraph."


def test_metadata_extraction(parser: PlainTextParser, metadata: FileMetadata) -> None:
    result = parser.parse(b"Hello", "hello.txt", metadata)
    assert result.metadata.title == "hello.txt"
    assert result.metadata.content_hash == _SHA256
