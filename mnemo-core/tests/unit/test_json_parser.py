"""Unit tests for the JSONParser (Module 3.6)."""

import pytest
from mnemo.interfaces.errors import ContractValidationError
from mnemo.interfaces.parser_models import ParseResult, RawTextBlock
from mnemo.interfaces.types import FileMetadata
from mnemo.parsers.json_parser import JSONParser

_SHA256 = "a" * 64


@pytest.fixture
def parser() -> JSONParser:
    return JSONParser()


@pytest.fixture
def metadata() -> FileMetadata:
    return FileMetadata(
        content_hash=_SHA256,
        size_bytes=1024,
        mime_type="application/json",
    )


def test_supported_formats(parser: JSONParser) -> None:
    assert ".json" in parser.supported_formats


def test_capabilities(parser: JSONParser) -> None:
    caps = parser.capabilities()
    assert caps.supports_images is False
    assert caps.supports_tables is False


def test_empty_bytes(parser: JSONParser, metadata: FileMetadata) -> None:
    result = parser.parse(b"", "empty.json", metadata)
    assert isinstance(result, ParseResult)
    assert len(result.blocks) == 0


def test_whitespace_only(parser: JSONParser, metadata: FileMetadata) -> None:
    result = parser.parse(b"   \n\t  ", "empty.json", metadata)
    assert len(result.blocks) == 0


def test_invalid_utf8(parser: JSONParser, metadata: FileMetadata) -> None:
    with pytest.raises(ContractValidationError, match="valid UTF-8"):
        parser.parse(b"\xff\xfe invalid", "test.json", metadata)


def test_invalid_json(parser: JSONParser, metadata: FileMetadata) -> None:
    with pytest.raises(ContractValidationError, match="not valid JSON"):
        parser.parse(b"{ invalid json }", "test.json", metadata)


def test_flatten_object(parser: JSONParser, metadata: FileMetadata) -> None:
    data = b'{"a": 1, "b": {"c": "hello"}}'
    result = parser.parse(data, "test.json", metadata)

    assert len(result.blocks) == 2
    b0 = result.blocks[0]
    b1 = result.blocks[1]
    assert isinstance(b0, RawTextBlock)
    assert isinstance(b1, RawTextBlock)
    assert b0.text == "a: 1"
    assert b1.text == "b.c: hello"


def test_flatten_array(parser: JSONParser, metadata: FileMetadata) -> None:
    data = b'[1, "hello", {"a": 2}]'
    result = parser.parse(data, "test.json", metadata)

    assert len(result.blocks) == 3
    b0 = result.blocks[0]
    b1 = result.blocks[1]
    b2 = result.blocks[2]
    assert isinstance(b0, RawTextBlock)
    assert isinstance(b1, RawTextBlock)
    assert isinstance(b2, RawTextBlock)
    assert b0.text == "[0]: 1"
    assert b1.text == "[1]: hello"
    assert b2.text == "[2].a: 2"


def test_metadata_extraction(parser: JSONParser, metadata: FileMetadata) -> None:
    result = parser.parse(b"{}", "test.json", metadata)
    assert result.metadata.title == "test.json"
    assert result.metadata.content_hash == _SHA256
