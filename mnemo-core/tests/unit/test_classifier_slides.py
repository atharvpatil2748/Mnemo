import pytest
from mnemo.classifier.classifier import DocumentClassifier
from mnemo.interfaces.parser_models import (
    ParseResult,
    RawHeadingBlock,
    RawTextBlock,
)
from mnemo.models._shared import FrozenMetadata
from mnemo.models.documents import DocType, DocumentMetadata


@pytest.fixture
def classifier() -> DocumentClassifier:
    return DocumentClassifier()


def test_slides_classification_by_extension(classifier: DocumentClassifier) -> None:
    result = ParseResult(
        blocks=(RawTextBlock(ordinal=0, text="content"),),
        extracted_assets=(),
        metadata=DocumentMetadata(
            content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            metadata=FrozenMetadata(),
        ),
        language="en",
        doc_type=DocType.GENERIC,
    )

    classified = classifier.classify(result, filename="presentation.pptx")
    assert classified.doc_type == DocType.SLIDES
    assert classified.metadata.metadata["parser.slide.schema_version"] == 1
    assert classified.blocks[0].metadata["parser.slide.number"] == 1
    assert classified.blocks[0].metadata["parser.slide.is_title_slide"] is True


def test_slides_classification_by_heading(classifier: DocumentClassifier) -> None:
    result = ParseResult(
        blocks=(RawHeadingBlock(ordinal=0, text="Slide 1", level=1),),
        extracted_assets=(),
        metadata=DocumentMetadata(
            content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            metadata=FrozenMetadata(),
        ),
        language="en",
        doc_type=DocType.GENERIC,
    )

    classified = classifier.classify(result)
    assert classified.doc_type == DocType.SLIDES
    assert classified.blocks[0].metadata["parser.slide.role"] == "title"


def test_slides_metadata_annotation(classifier: DocumentClassifier) -> None:
    result = ParseResult(
        blocks=(
            RawHeadingBlock(ordinal=0, text="Presentation Title", level=1, page_number=1),
            RawTextBlock(ordinal=1, text="Title subtitle", page_number=1),
            RawHeadingBlock(ordinal=2, text="Slide 2 Title", level=1, page_number=2),
            RawTextBlock(ordinal=3, text="Bullet 1", page_number=2),
            RawTextBlock(
                ordinal=4,
                text="Bullet 2",
                page_number=2,
                metadata=FrozenMetadata({"parser.slide.role": "notes"}),
            ),
            RawTextBlock(ordinal=5, text="No page number text", page_number=None),
        ),
        extracted_assets=(),
        metadata=DocumentMetadata(
            content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            metadata=FrozenMetadata(),
        ),
        language="en",
        doc_type=DocType.GENERIC,
    )

    classified = classifier.classify(result, filename="test.ppt")
    assert classified.doc_type == DocType.SLIDES

    blocks = classified.blocks
    assert len(blocks) == 6

    # Slide 1
    assert blocks[0].metadata["parser.slide.number"] == 1
    assert blocks[0].metadata["parser.slide.is_title_slide"] is True
    assert blocks[0].metadata["parser.slide.role"] == "title"

    assert blocks[1].metadata["parser.slide.number"] == 1
    assert blocks[1].metadata["parser.slide.is_title_slide"] is True
    assert blocks[1].metadata["parser.slide.role"] == "body"

    # Slide 2
    assert blocks[2].metadata["parser.slide.number"] == 2
    assert blocks[2].metadata.get("parser.slide.is_title_slide") is None
    assert blocks[2].metadata["parser.slide.role"] == "title"

    assert blocks[3].metadata["parser.slide.number"] == 2
    assert blocks[3].metadata["parser.slide.role"] == "body"

    # Preserved explicit notes
    assert blocks[4].metadata["parser.slide.number"] == 2
    assert blocks[4].metadata["parser.slide.role"] == "notes"

    # Fallback for page_number=None
    assert blocks[5].metadata["parser.slide.number"] == 3
    assert blocks[5].metadata["parser.slide.role"] == "body"
