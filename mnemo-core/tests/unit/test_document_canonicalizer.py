"""Tests for the pure Module 3.9 DocumentCanonicalizer."""

from types import MappingProxyType
from uuid import uuid4

import pytest
from mnemo.classifier import DocumentClassifier
from mnemo.cleaner import DocumentCleaner
from mnemo.ingestion import DocumentCanonicalizer
from mnemo.interfaces.errors import IntegrityError
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
from mnemo.models import (
    Asset,
    CodeBlock,
    DocType,
    DocumentMetadata,
    EquationBlock,
    FrozenMetadata,
    HeadingBlock,
    ImageBlock,
    TableBlock,
    TextBlock,
)


def _asset() -> Asset:
    return Asset(
        asset_id=uuid4(),
        mime_type="image/png",
        content_hash="b" * 64,
        storage_uri="blob://asset",
    )


def _result() -> ParseResult:
    metadata = FrozenMetadata({"layout.role": "body"})
    return ParseResult(
        blocks=(
            RawTextBlock(
                ordinal=0,
                text="text",
                page_number=1,
                bounding_box=(1.0, 2.0, 3.0, 4.0),
                language="en",
                metadata=metadata,
            ),
            RawHeadingBlock(
                ordinal=1,
                text="heading",
                level=2,
                page_number=1,
                language="en",
                metadata=metadata,
            ),
            RawListBlock(
                ordinal=2,
                items=("first", "second"),
                page_number=1,
                language="en",
                metadata=metadata,
            ),
            RawTableBlock(
                ordinal=3,
                rows=(("A", "B"), ("1", "2")),
                header_row_count=1,
                page_number=1,
                language="en",
                metadata=metadata,
            ),
            RawCodeBlock(
                ordinal=4,
                code="print('x')",
                code_language="python",
                page_number=1,
                language="en",
                metadata=metadata,
            ),
            RawMathBlock(
                ordinal=5,
                latex="x^2",
                display=True,
                page_number=1,
                language="en",
                metadata=metadata,
            ),
            RawImageBlock(
                ordinal=6,
                parser_local_id="image-1",
                alt_text="diagram",
                page_number=1,
                language="en",
                metadata=metadata,
            ),
        ),
        extracted_assets=(
            TransientAsset(
                parser_local_id="image-1",
                raw_bytes=b"image",
                mime_type="image/png",
                page_number=1,
            ),
        ),
        metadata=DocumentMetadata(
            content_hash="a" * 64,
            title="Document",
            page_count=1,
            metadata=FrozenMetadata({"parser.format": "test"}),
        ),
        language="en-US",
        doc_type=DocType.PAPER,
    )


def test_canonicalizer_converts_every_raw_block_and_preserves_fields() -> None:
    result = _result()
    asset = _asset()

    document = DocumentCanonicalizer().canonicalize(result, MappingProxyType({"image-1": asset}))

    assert tuple(type(block) for block in document.blocks) == (
        TextBlock,
        HeadingBlock,
        TextBlock,
        TableBlock,
        CodeBlock,
        EquationBlock,
        ImageBlock,
    )
    list_block = document.blocks[2]
    assert isinstance(list_block, TextBlock)
    assert list_block.text == "first\nsecond"
    assert document.blocks[0].ordinal == 0
    assert document.blocks[0].page_number == 1
    assert document.blocks[0].bounding_box == (1.0, 2.0, 3.0, 4.0)
    assert document.blocks[0].language == "en"
    assert document.blocks[0].metadata is result.blocks[0].metadata
    image = document.blocks[6]
    assert isinstance(image, ImageBlock)
    assert image.asset_id == asset.asset_id
    assert image.alt_text == "diagram"
    assert document.metadata is result.metadata
    assert document.language == result.language
    assert document.doc_type is DocType.PAPER


def test_canonicalizer_is_deterministic_and_accepts_empty_document() -> None:
    result = ParseResult(
        blocks=(),
        extracted_assets=(),
        metadata=DocumentMetadata(content_hash="a" * 64),
        language="und",
        doc_type=DocType.GENERIC,
    )
    canonicalizer = DocumentCanonicalizer()

    first = canonicalizer.canonicalize(result, MappingProxyType({}))
    second = canonicalizer.canonicalize(result, MappingProxyType({}))

    assert first == second
    assert first.blocks == ()


def test_canonicalizer_preserves_markdown_list_semantics_without_interpreting_them() -> None:
    markdown_metadata = FrozenMetadata(
        {
            "parser.markdown.kind": "list",
            "parser.markdown.source": "- Parent\n  - Child\n",
            "parser.markdown.list": {
                "items": (
                    {"depth": 0, "marker": "-", "ordered": False, "start": None, "text": "Parent"},
                    {"depth": 1, "marker": "-", "ordered": False, "start": None, "text": "Child"},
                ),
                "marker": "-",
                "ordered": False,
                "start": None,
            },
        }
    )
    result = ParseResult(
        blocks=(
            RawListBlock(
                ordinal=0,
                items=("Parent\nChild",),
                metadata=markdown_metadata,
            ),
        ),
        extracted_assets=(),
        metadata=DocumentMetadata(content_hash="a" * 64),
        language="en",
        doc_type=DocType.MARKDOWN,
    )

    document = DocumentCanonicalizer().canonicalize(result, MappingProxyType({}))

    assert isinstance(document.blocks[0], TextBlock)
    assert document.blocks[0].metadata is markdown_metadata
    assert document.blocks[0].metadata["parser.markdown.kind"] == "list"


@pytest.mark.parametrize(
    "resolution",
    ({}, {"image-1": _asset(), "unexpected": _asset()}),
)
def test_canonicalizer_rejects_incomplete_or_extra_asset_mapping(
    resolution: dict[str, Asset],
) -> None:
    with pytest.raises(IntegrityError, match="does not exactly match"):
        DocumentCanonicalizer().canonicalize(_result(), MappingProxyType(resolution))


def test_parse_result_rejects_duplicate_and_invalid_asset_correlation() -> None:
    transient = TransientAsset(parser_local_id="image-1", raw_bytes=b"image", mime_type="image/png")
    metadata = DocumentMetadata(content_hash="a" * 64)

    with pytest.raises(ValueError, match="must be unique"):
        ParseResult(
            blocks=(RawImageBlock(ordinal=0, parser_local_id="image-1"),),
            extracted_assets=(transient, transient),
            metadata=metadata,
            language="und",
            doc_type=DocType.GENERIC,
        )


def test_canonicalizer_rejects_duplicate_image_correlations() -> None:
    metadata = DocumentMetadata(content_hash="a" * 64)
    transient = TransientAsset(parser_local_id="image-1", raw_bytes=b"image", mime_type="image/png")
    result = ParseResult(
        blocks=(
            RawImageBlock(ordinal=0, parser_local_id="image-1"),
            RawImageBlock(ordinal=1, parser_local_id="image-1"),
        ),
        extracted_assets=(transient,),
        metadata=metadata,
        language="und",
        doc_type=DocType.GENERIC,
    )

    with pytest.raises(IntegrityError, match="must be unique"):
        DocumentCanonicalizer().canonicalize(result, MappingProxyType({"image-1": _asset()}))
    with pytest.raises(ValueError, match="must correlate"):
        ParseResult(
            blocks=(RawImageBlock(ordinal=0, parser_local_id="image-1"),),
            extracted_assets=(
                TransientAsset(parser_local_id="other", raw_bytes=b"image", mime_type="image/png"),
            ),
            metadata=metadata,
            language="und",
            doc_type=DocType.GENERIC,
        )


@pytest.mark.parametrize(
    ("heading", "filename", "expected_type", "metadata_key"),
    (
        ("Experience", "profile.pdf", DocType.RESUME, "parser.resume.section"),
        ("Slide 1", "deck.pptx", DocType.SLIDES, "parser.slide.number"),
        (
            "API Reference",
            "reference.pdf",
            DocType.DOCUMENTATION,
            "parser.documentation.role",
        ),
    ),
)
def test_classifier_semantic_metadata_survives_phase_3_boundary(
    heading: str,
    filename: str,
    expected_type: DocType,
    metadata_key: str,
) -> None:
    """Classifier-owned semantic metadata reaches ParsedDocument unchanged."""
    parsed = ParseResult(
        blocks=(RawHeadingBlock(ordinal=0, text=heading, level=1, page_number=1),),
        extracted_assets=(),
        metadata=DocumentMetadata(content_hash="a" * 64),
        language="en",
        doc_type=DocType.GENERIC,
    )

    cleaned = DocumentCleaner().clean(parsed)
    classified = DocumentClassifier().classify(cleaned, filename=filename)
    document = DocumentCanonicalizer().canonicalize(classified, MappingProxyType({}))

    assert document.doc_type is expected_type
    assert document.metadata.metadata is classified.metadata.metadata
    assert document.blocks[0].metadata is classified.blocks[0].metadata
    assert metadata_key in document.blocks[0].metadata
