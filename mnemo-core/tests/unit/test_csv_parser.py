"""Unit tests for the CSVParser (Module 3.6)."""

import pytest
from mnemo.interfaces.errors import ContractValidationError
from mnemo.interfaces.parser_models import ParseResult, RawTableBlock
from mnemo.interfaces.types import FileMetadata
from mnemo.parsers.csv_parser import CSVParser

_SHA256 = "a" * 64


@pytest.fixture
def parser() -> CSVParser:
    return CSVParser()


@pytest.fixture
def metadata() -> FileMetadata:
    return FileMetadata(
        content_hash=_SHA256,
        size_bytes=1024,
        mime_type="text/csv",
    )


def test_supported_formats(parser: CSVParser) -> None:
    assert ".csv" in parser.supported_formats
    assert ".tsv" in parser.supported_formats


def test_capabilities(parser: CSVParser) -> None:
    caps = parser.capabilities()
    assert caps.supports_images is False
    assert caps.supports_tables is True


def test_empty_bytes(parser: CSVParser, metadata: FileMetadata) -> None:
    result = parser.parse(b"", "empty.csv", metadata)
    assert isinstance(result, ParseResult)
    assert len(result.blocks) == 0


def test_whitespace_only(parser: CSVParser, metadata: FileMetadata) -> None:
    result = parser.parse(b"   \n\t  ", "empty.csv", metadata)
    assert len(result.blocks) == 0


def test_invalid_utf8(parser: CSVParser, metadata: FileMetadata) -> None:
    with pytest.raises(ContractValidationError, match="valid UTF-8"):
        parser.parse(b"\xff\xfe invalid", "test.csv", metadata)


def test_valid_csv(parser: CSVParser, metadata: FileMetadata) -> None:
    data = b"name,age\nAlice,30\nBob,25\nCharlie"
    result = parser.parse(data, "test.csv", metadata)

    assert len(result.blocks) == 1
    assert isinstance(result.blocks[0], RawTableBlock)

    block = result.blocks[0]
    assert block.header_row_count == 1
    # Check padding of the last row
    assert block.rows == (
        ("name", "age"),
        ("Alice", "30"),
        ("Bob", "25"),
        ("Charlie", ""),
    )


def test_valid_tsv(parser: CSVParser, metadata: FileMetadata) -> None:
    data = b"name\tage\nAlice\t30\nBob\t25"
    result = parser.parse(data, "test.tsv", metadata)

    assert len(result.blocks) == 1
    assert isinstance(result.blocks[0], RawTableBlock)

    block = result.blocks[0]
    assert block.header_row_count == 1
    assert block.rows == (
        ("name", "age"),
        ("Alice", "30"),
        ("Bob", "25"),
    )


def test_metadata_extraction(parser: CSVParser, metadata: FileMetadata) -> None:
    result = parser.parse(b"a,b\n1,2", "test.csv", metadata)
    assert result.metadata.title == "test.csv"
    assert result.metadata.content_hash == _SHA256
