import pytest
from mnemo.cleaner.cleaner import DocumentCleaner
from mnemo.interfaces.parser_models import (
    ParseResult,
    RawCodeBlock,
    RawHeadingBlock,
    RawImageBlock,
    RawListBlock,
    RawMathBlock,
    RawTableBlock,
    RawTextBlock,
    TransientAsset,
)
from mnemo.models import DocType, DocumentMetadata


@pytest.fixture
def cleaner() -> DocumentCleaner:
    return DocumentCleaner()


@pytest.fixture
def empty_metadata() -> DocumentMetadata:
    return DocumentMetadata(
        title="Test Document",
        content_hash="a" * 64,
    )


def test_cleaner_normalizes_whitespace(
    cleaner: DocumentCleaner, empty_metadata: DocumentMetadata
) -> None:
    blocks = (
        RawTextBlock(
            ordinal=0,
            text="This   is  a\n\n\nvery    noisy   \t  string.",
            page_number=1,
            language="en",
        ),
    )
    result = ParseResult(
        blocks=blocks,
        extracted_assets=(),
        metadata=empty_metadata,
        language="en",
        doc_type=DocType.GENERIC,
    )

    cleaned = cleaner.clean(result)
    assert len(cleaned.blocks) == 1
    cleaned_block = cleaned.blocks[0]
    assert isinstance(cleaned_block, RawTextBlock)
    assert cleaned_block.text == "This is a very noisy string."


def test_cleaner_fixes_hyphenated_line_breaks(
    cleaner: DocumentCleaner, empty_metadata: DocumentMetadata
) -> None:
    blocks = (
        RawTextBlock(
            ordinal=0,
            text="The quick brown fox jumps over the lazy dog-\nand lands safely.",
            page_number=1,
            language="en",
        ),
    )
    result = ParseResult(
        blocks=blocks,
        extracted_assets=(),
        metadata=empty_metadata,
        language="en",
        doc_type=DocType.GENERIC,
    )

    cleaned = cleaner.clean(result)
    cleaned_block = cleaned.blocks[0]
    assert isinstance(cleaned_block, RawTextBlock)
    assert cleaned_block.text == "The quick brown fox jumps over the lazy dogand lands safely."


def test_cleaner_unicode_normalization(
    cleaner: DocumentCleaner, empty_metadata: DocumentMetadata
) -> None:
    # NFD vs NFC
    nfd_text = "e\u0301"  # e + acute accent
    nfc_text = "\u00e9"  # é
    blocks = (
        RawTextBlock(
            ordinal=0,
            text=f"R{nfd_text}sum{nfd_text}",
            page_number=1,
            language="en",
        ),
    )
    result = ParseResult(
        blocks=blocks,
        extracted_assets=(),
        metadata=empty_metadata,
        language="en",
        doc_type=DocType.GENERIC,
    )

    cleaned = cleaner.clean(result)
    cleaned_block = cleaned.blocks[0]
    assert isinstance(cleaned_block, RawTextBlock)
    assert cleaned_block.text == f"R{nfc_text}sum{nfc_text}"


def test_cleaner_removes_headers_footers(
    cleaner: DocumentCleaner, empty_metadata: DocumentMetadata
) -> None:
    blocks = [
        RawTextBlock(ordinal=0, text="Confidential - Page 1", page_number=1),
        RawTextBlock(ordinal=1, text="Content on page 1", page_number=1),
        RawTextBlock(
            ordinal=2, text="Confidential - Page 1", page_number=2
        ),  # same text on multiple pages
        RawTextBlock(ordinal=3, text="Content on page 2", page_number=2),
        RawTextBlock(ordinal=4, text="Confidential - Page 1", page_number=3),
        RawTextBlock(ordinal=5, text="Content on page 3", page_number=3),
    ]
    result = ParseResult(
        blocks=tuple(blocks),
        extracted_assets=(),
        metadata=empty_metadata,
        language="en",
        doc_type=DocType.GENERIC,
    )

    cleaned = cleaner.clean(result)

    # "Confidential - Page 1" appears on 3/3 pages -> should be removed
    assert len(cleaned.blocks) == 3
    b0 = cleaned.blocks[0]
    b1 = cleaned.blocks[1]
    b2 = cleaned.blocks[2]
    assert isinstance(b0, RawTextBlock)
    assert isinstance(b1, RawTextBlock)
    assert isinstance(b2, RawTextBlock)
    assert b0.text == "Content on page 1"
    assert b1.text == "Content on page 2"
    assert b2.text == "Content on page 3"

    # verify ordinals are reassigned
    assert b0.ordinal == 0
    assert b1.ordinal == 1
    assert b2.ordinal == 2


def test_cleaner_detects_language(
    cleaner: DocumentCleaner, empty_metadata: DocumentMetadata
) -> None:
    blocks = (RawTextBlock(ordinal=0, text="Bonjour, comment ça va aujourd'hui?"),)
    result = ParseResult(
        blocks=blocks,
        extracted_assets=(),
        metadata=empty_metadata,
        language="en",
        doc_type=DocType.GENERIC,
    )

    cleaned = cleaner.clean(result)
    assert cleaned.blocks[0].language == "fr"


def test_cleaner_is_idempotent(cleaner: DocumentCleaner, empty_metadata: DocumentMetadata) -> None:
    blocks = [
        RawTextBlock(ordinal=0, text="Header 123", page_number=1),
        RawTextBlock(ordinal=1, text="Actual content- \nthat is messy   ", page_number=1),
        RawTextBlock(ordinal=2, text="Header 123", page_number=2),
        RawTextBlock(ordinal=3, text="More content", page_number=2),
        RawTextBlock(ordinal=4, text="Header 123", page_number=3),
    ]
    result = ParseResult(
        blocks=tuple(blocks),
        extracted_assets=(),
        metadata=empty_metadata,
        language="en",
        doc_type=DocType.GENERIC,
    )

    cleaned_once = cleaner.clean(result)
    cleaned_twice = cleaner.clean(cleaned_once)

    assert cleaned_once == cleaned_twice
    assert len(cleaned_once.blocks) == 2


def test_cleaner_with_empty_or_malformed_blocks(
    cleaner: DocumentCleaner, empty_metadata: DocumentMetadata
) -> None:
    # langdetect might fail on pure numbers or special characters.
    # The cleaner should gracefully handle this and default to the block's existing language,
    # or leave it as None if it was None.
    blocks = (
        RawTextBlock(ordinal=0, text="1234567890"),
        RawTextBlock(ordinal=1, text="!@#$%^&*()"),
    )
    result = ParseResult(
        blocks=blocks,
        extracted_assets=(),
        metadata=empty_metadata,
        language="en",
        doc_type=DocType.GENERIC,
    )

    cleaned = cleaner.clean(result)
    assert len(cleaned.blocks) == 2
    b0 = cleaned.blocks[0]
    b1 = cleaned.blocks[1]
    assert isinstance(b0, RawTextBlock)
    assert isinstance(b1, RawTextBlock)
    assert b0.text == "1234567890"
    assert b1.text == "!@#$%^&*()"


def test_cleaner_preserves_other_block_types(
    cleaner: DocumentCleaner, empty_metadata: DocumentMetadata
) -> None:
    blocks = (
        RawImageBlock(ordinal=0, parser_local_id="img1", alt_text="An image"),
        RawTableBlock(ordinal=1, rows=(("A", "B"), ("C", "D"))),
    )
    result = ParseResult(
        blocks=blocks,
        extracted_assets=(
            TransientAsset(parser_local_id="img1", raw_bytes=b"image", mime_type="image/png"),
        ),
        metadata=empty_metadata,
        language="en",
        doc_type=DocType.GENERIC,
    )

    cleaned = cleaner.clean(result)
    assert len(cleaned.blocks) == 2
    assert isinstance(cleaned.blocks[0], RawImageBlock)
    assert isinstance(cleaned.blocks[1], RawTableBlock)


def test_cleaner_coverage_remaining(
    cleaner: DocumentCleaner, empty_metadata: DocumentMetadata
) -> None:
    blocks = (
        RawHeadingBlock(ordinal=0, text="Heading-\nbreak", level=1),
        RawCodeBlock(ordinal=1, code="print('e\u0301')"),  # e + acute
        RawMathBlock(ordinal=2, latex="e\u0301=mc^2"),
        RawImageBlock(ordinal=3, parser_local_id="img", alt_text="Alt-\ntext"),
        RawTextBlock(
            ordinal=4, text=" a ", language="en"
        ),  # short string for None language detection
        RawListBlock(ordinal=5, items=("a-\nb", "c")),
    )
    result = ParseResult(
        blocks=blocks,
        extracted_assets=(
            TransientAsset(parser_local_id="img", raw_bytes=b"image", mime_type="image/png"),
        ),
        metadata=empty_metadata,
        language="en",
        doc_type=DocType.GENERIC,
    )

    cleaned = cleaner.clean(result)
    assert len(cleaned.blocks) == 6

    b0 = cleaned.blocks[0]
    assert isinstance(b0, RawHeadingBlock)
    assert b0.text == "Headingbreak"

    b1 = cleaned.blocks[1]
    assert isinstance(b1, RawCodeBlock)
    assert b1.code == "print('\u00e9')"

    b2 = cleaned.blocks[2]
    assert isinstance(b2, RawMathBlock)
    assert b2.latex == "\u00e9=mc^2"

    b3 = cleaned.blocks[3]
    assert isinstance(b3, RawImageBlock)
    assert b3.alt_text == "Alttext"

    b4 = cleaned.blocks[4]
    assert isinstance(b4, RawTextBlock)
    assert b4.language == "en"  # Fallback from block / original

    b5 = cleaned.blocks[5]
    assert isinstance(b5, RawListBlock)
    assert b5.items == ("ab", "c")
