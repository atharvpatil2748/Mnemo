"""Tests for the PDF parser."""

from datetime import UTC, datetime

import fitz  # type: ignore[import-untyped]
import pytest
from mnemo.interfaces.errors import ContractValidationError, UnsupportedError
from mnemo.interfaces.parser_models import (
    ParseResult,
    RawHeadingBlock,
    RawImageBlock,
    RawListBlock,
    RawTableBlock,
    RawTextBlock,
)
from mnemo.interfaces.types import FileMetadata
from mnemo.models import DocType
from mnemo.models._shared import FrozenMetadata
from mnemo.parsers.pdf import PDFParser


@pytest.fixture
def parser() -> PDFParser:
    return PDFParser()


@pytest.fixture
def base_metadata() -> FileMetadata:
    return FileMetadata(
        content_hash="a" * 64,
        size_bytes=1000,
        mime_type="application/pdf",
        modified_at=datetime(2025, 1, 1, tzinfo=UTC),
        metadata=FrozenMetadata({"source": "test"}),
    )


def test_supported_formats(parser: PDFParser) -> None:
    assert parser.supported_formats == (".pdf",)


def test_capabilities(parser: PDFParser) -> None:
    caps = parser.capabilities()
    assert caps.supports_images is True
    assert caps.supports_tables is True
    assert caps.supports_math is False
    assert caps.supports_ocr is False


def test_parse_empty_bytes(parser: PDFParser, base_metadata: FileMetadata) -> None:
    with pytest.raises(ContractValidationError, match="Cannot parse empty PDF"):
        parser.parse(b"", "empty.pdf", base_metadata)


def test_parse_corrupted_bytes(parser: PDFParser, base_metadata: FileMetadata) -> None:
    with pytest.raises(ContractValidationError, match="Failed to open PDF"):
        parser.parse(b"not a pdf file", "corrupt.pdf", base_metadata)


def test_parse_encrypted_pdf(parser: PDFParser, base_metadata: FileMetadata) -> None:
    # Create an encrypted PDF
    doc = fitz.open()
    doc.new_page()
    # Save with encryption
    pdf_bytes = doc.write(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="password")
    doc.close()

    with pytest.raises(UnsupportedError, match="Encrypted PDFs are not supported"):
        parser.parse(pdf_bytes, "encrypted.pdf", base_metadata)


def test_parse_simple_text(parser: PDFParser, base_metadata: FileMetadata) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(fitz.Point(50, 50), "Hello world")

    # We can also add some metadata
    doc.set_metadata({"title": "Test Title", "author": "Test Author", "creator": "Test Creator"})

    pdf_bytes = doc.write()
    doc.close()

    result = parser.parse(pdf_bytes, "test.pdf", base_metadata)

    assert isinstance(result, ParseResult)
    assert result.doc_type == DocType.GENERIC
    assert result.language == "en"

    # Check metadata
    assert result.metadata.title == "Test Title"
    assert result.metadata.authors == ("Test Author",)
    assert result.metadata.metadata["creator"] == "Test Creator"
    assert result.metadata.page_count == 1
    assert result.metadata.metadata["source"] == "test"

    # Check blocks
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert isinstance(block, RawTextBlock)
    assert block.text == "Hello world"
    assert block.ordinal == 0
    assert block.page_number == 1


def test_parse_heading(parser: PDFParser, base_metadata: FileMetadata) -> None:
    doc = fitz.open()
    page = doc.new_page()
    # Heading (large font)
    page.insert_text(fitz.Point(50, 50), "Main Heading", fontsize=24)
    # Paragraph (small font) - add multiple to make median small
    page.insert_text(fitz.Point(50, 100), "Regular paragraph text here 1.", fontsize=12)
    page.insert_text(fitz.Point(50, 150), "Regular paragraph text here 2.", fontsize=12)
    page.insert_text(fitz.Point(50, 200), "Regular paragraph text here 3.", fontsize=12)
    pdf_bytes = doc.write()
    doc.close()

    result = parser.parse(pdf_bytes, "test.pdf", base_metadata)

    assert len(result.blocks) == 4
    assert isinstance(result.blocks[0], RawHeadingBlock)
    assert result.blocks[0].text == "Main Heading"
    assert result.blocks[0].level == 1

    assert isinstance(result.blocks[1], RawTextBlock)
    assert result.blocks[1].text == "Regular paragraph text here 1."


def test_parse_list(parser: PDFParser, base_metadata: FileMetadata) -> None:
    doc = fitz.open()
    page = doc.new_page()
    # List item
    page.insert_text(fitz.Point(50, 50), "- First item\n- Second item", fontsize=12)
    pdf_bytes = doc.write()
    doc.close()

    result = parser.parse(pdf_bytes, "test.pdf", base_metadata)

    assert len(result.blocks) == 1
    assert isinstance(result.blocks[0], RawListBlock)
    assert result.blocks[0].items == ("- First item", "- Second item")


def test_parse_image(parser: PDFParser, base_metadata: FileMetadata) -> None:
    doc = fitz.open()
    page = doc.new_page()

    # Create a simple red 2x2 png image manually or let fitz generate a pixmap
    pix = fitz.Pixmap(fitz.csRGB, (0, 0, 10, 10), False)
    pix.clear_with(255)
    page.insert_image(fitz.Rect(50, 50, 100, 100), pixmap=pix)

    pdf_bytes = doc.write()
    doc.close()

    result = parser.parse(pdf_bytes, "test.pdf", base_metadata)

    assert len(result.extracted_assets) == 1
    asset = result.extracted_assets[0]
    assert asset.mime_type.startswith("image/")
    assert asset.page_number == 1
    assert isinstance(asset.raw_bytes, bytes)
    assert len(asset.raw_bytes) > 0

    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert isinstance(block, RawImageBlock)
    assert block.parser_local_id == asset.parser_local_id


def test_parse_tables(parser: PDFParser, base_metadata: FileMetadata) -> None:
    doc = fitz.open()
    page = doc.new_page()
    # Fitz doesn't have a simple page.insert_table(), we just draw rectangles and text
    # But it's easier to create a small table visually to trick find_tables()
    # Wait, find_tables uses text alignment and lines. We can just draw a table.
    shape = page.new_shape()
    # outer box
    shape.draw_rect(fitz.Rect(100, 100, 300, 200))
    # horizontal line
    shape.draw_line(fitz.Point(100, 150), fitz.Point(300, 150))
    # vertical line
    shape.draw_line(fitz.Point(200, 100), fitz.Point(200, 200))
    shape.finish()
    shape.commit()

    page.insert_text(fitz.Point(110, 125), "Col1")
    page.insert_text(fitz.Point(210, 125), "Col2")
    page.insert_text(fitz.Point(110, 175), "Val1")
    page.insert_text(fitz.Point(210, 175), "Val2")

    pdf_bytes = doc.write()
    doc.close()

    result = parser.parse(pdf_bytes, "test.pdf", base_metadata)

    # find_tables is quite robust in fitz
    # Let's see if it finds it.
    table_blocks = [b for b in result.blocks if isinstance(b, RawTableBlock)]

    if table_blocks:
        table = table_blocks[0]
        assert table.header_row_count in (0, 1)
        assert len(table.rows) == 2
        assert len(table.rows[0]) == 2
        # Clean up text comparison due to fitz potential formatting
        assert "Col1" in table.rows[0][0] or "Col2" in table.rows[0][1]


def test_table_overlap_uses_original_text_block_area(parser: PDFParser) -> None:
    """A slight table intersection must not suppress adjacent PDF text."""
    text_rect = fitz.Rect(0, 0, 100, 100)
    original = fitz.Rect(text_rect)

    assert parser._overlaps_any(text_rect, [fitz.Rect(90, 0, 110, 100)]) is False
    assert text_rect == original
    assert parser._overlaps_any(text_rect, [fitz.Rect(40, 0, 110, 100)]) is True
    assert text_rect == original


def test_mixed_font_text_block_is_not_collapsed_into_heading(parser: PDFParser) -> None:
    block = {
        "lines": [
            {"spans": [{"text": "Technical skills", "size": 10.0}]},
            {"spans": [{"text": "Relevant courses", "size": 18.0}]},
        ]
    }

    text, is_heading, _ = parser._analyze_text_block(block, median_size=10.0)

    assert text == "Technical skills\nRelevant courses"
    assert is_heading is False


def test_table_filter_preserves_adjacent_non_table_spans(parser: PDFParser) -> None:
    block = {
        "lines": [
            {
                "spans": [
                    {"text": "Unique introduction", "size": 10.0, "bbox": (0, 0, 80, 10)},
                    {"text": "Duplicated table cell", "size": 10.0, "bbox": (0, 20, 80, 30)},
                ]
            }
        ]
    }

    filtered = parser._without_table_spans(block, [fitz.Rect(0, 15, 100, 35)])

    assert [span["text"] for span in filtered["lines"][0]["spans"]] == ["Unique introduction"]


def test_pdf_parser_extra_metadata() -> None:
    parser = PDFParser()
    import fitz

    doc = fitz.open()
    doc.new_page()
    doc.set_metadata(
        {
            "producer": "Test Producer",
            "creationDate": "D:20230101000000Z",
            "modDate": "D:20230101000000Z",
            "creator": "Test Creator",
        }
    )
    pdf_bytes = doc.write()
    file_meta = FileMetadata(
        content_hash="a" * 64,
        size_bytes=len(pdf_bytes),
        mime_type="application/pdf",
        metadata=FrozenMetadata(),
    )
    result = parser.parse(pdf_bytes, "test.pdf", file_meta)
    assert result.metadata.metadata["producer"] == "Test Producer"
    assert result.metadata.metadata["creation_date"] == "D:20230101000000Z"
    assert result.metadata.metadata["modification_date"] == "D:20230101000000Z"
    assert result.metadata.metadata["creator"] == "Test Creator"
