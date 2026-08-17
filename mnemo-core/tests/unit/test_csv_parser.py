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


def test_large_csv_partitions_with_header_preservation(
    parser: CSVParser, metadata: FileMetadata
) -> None:
    # 120 data rows with 4 columns
    header = "id,col_a,col_b,col_c\n"
    rows = [f"{i},value_a_{i},value_b_{i},value_c_{i}" for i in range(1, 121)]
    csv_text = header + "\n".join(rows)

    result = parser.parse(csv_text.encode("utf-8"), "large.csv", metadata)

    assert len(result.blocks) > 1
    assert all(isinstance(b, RawTableBlock) for b in result.blocks)

    # Every block must have the exact header as row 0 and header_row_count=1
    expected_header = ("id", "col_a", "col_b", "col_c")
    for idx, block in enumerate(result.blocks):
        assert isinstance(block, RawTableBlock)
        assert block.ordinal == idx
        assert block.header_row_count == 1
        assert block.rows[0] == expected_header
        assert len(block.rows) > 1

    # Reconstructed data rows must match exactly without missing or duplicated rows
    reconstructed_data_rows = []
    for block in result.blocks:
        assert isinstance(block, RawTableBlock)
        reconstructed_data_rows.extend(block.rows[1:])

    expected_data_rows = [
        (str(i), f"value_a_{i}", f"value_b_{i}", f"value_c_{i}") for i in range(1, 121)
    ]
    assert reconstructed_data_rows == expected_data_rows
    assert len(reconstructed_data_rows) == 120


def test_golden_y24_cpi_csv_partitions_and_fits_token_limit(
    parser: CSVParser, metadata: FileMetadata
) -> None:
    from datetime import UTC, datetime
    from pathlib import Path
    from types import MappingProxyType
    from uuid import uuid4

    from mnemo.chunkers.generic import GenericChunker
    from mnemo.classifier import DocumentClassifier
    from mnemo.cleaner import DocumentCleaner
    from mnemo.ingestion import DocumentCanonicalizer
    from mnemo.interfaces import ChunkingContext, ChunkingOptions
    from mnemo.models import DocumentVersion, DocumentVersionStatus
    from mnemo.tokenizers import O200KBaseTokenCounter
    from mnemo_server.tokenizer_provisioning import provision_tokenizer

    y24_path = Path("goldenDataset/Y24_CPI.csv")
    if not y24_path.exists():
        pytest.skip("goldenDataset/Y24_CPI.csv not found")

    data = y24_path.read_bytes()
    meta = FileMetadata(
        content_hash=_SHA256,
        size_bytes=len(data),
        mime_type="text/csv",
    )

    result = parser.parse(data, "Y24_CPI.csv", meta)
    assert len(result.blocks) > 1

    cleaner = DocumentCleaner()
    cleaned = cleaner.clean(result)

    classifier = DocumentClassifier()
    classified = classifier.classify(cleaned, "Y24_CPI.csv")

    canonicalizer = DocumentCanonicalizer()
    canonical = canonicalizer.canonicalize(classified, MappingProxyType({}))

    tok = O200KBaseTokenCounter(provision_tokenizer())
    chunker = GenericChunker()

    doc_ver = DocumentVersion(
        version_id=uuid4(),
        document_id=uuid4(),
        content_hash=_SHA256,
        metadata=canonical.metadata,
        status=DocumentVersionStatus.CURRENT,
        created_at=datetime.now(UTC),
    )
    ctx = ChunkingContext(
        document_version=doc_ver,
        options=ChunkingOptions(target_tokens=512, max_tokens=1024, overlap_tokens=64),
    )

    # Must successfully chunk without raising token maximum errors
    drafts = chunker.chunk(canonical, ctx, tok)
    assert len(drafts) == len(result.blocks)
    for draft in drafts:
        assert tok.count(draft.text) <= ctx.effective_max_tokens
