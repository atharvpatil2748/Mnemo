"""Unit tests for DocumentClassifier."""

from typing import Any

import pytest
from mnemo.classifier import DocumentClassifier
from mnemo.interfaces.parser_models import (
    ParseResult,
    RawCodeBlock,
    RawHeadingBlock,
    RawTextBlock,
)
from mnemo.models._shared import FrozenMetadata
from mnemo.models.documents import DocType, DocumentMetadata


@pytest.fixture
def classifier() -> DocumentClassifier:
    return DocumentClassifier()


@pytest.fixture
def empty_metadata() -> DocumentMetadata:
    return DocumentMetadata(
        content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        metadata=FrozenMetadata(),
    )


def build_result(blocks: tuple[Any, ...], metadata: DocumentMetadata) -> ParseResult:
    return ParseResult(
        blocks=blocks,
        extracted_assets=(),
        metadata=metadata,
        language="en",
        doc_type=DocType.GENERIC,
    )


def test_classify_by_extension_code(
    classifier: DocumentClassifier, empty_metadata: DocumentMetadata
) -> None:
    result = build_result((), empty_metadata)
    classified = classifier.classify(result, filename="script.py")
    assert classified.doc_type == DocType.CODE


def test_classify_by_extension_markdown(
    classifier: DocumentClassifier, empty_metadata: DocumentMetadata
) -> None:
    result = build_result((), empty_metadata)
    classified = classifier.classify(result, filename="README.md")
    assert classified.doc_type == DocType.MARKDOWN


def test_classify_by_heading_paper(
    classifier: DocumentClassifier, empty_metadata: DocumentMetadata
) -> None:
    blocks = (
        RawHeadingBlock(ordinal=0, text="Abstract", level=1),
        RawTextBlock(ordinal=1, text="This is a paper."),
    )
    result = build_result(blocks, empty_metadata)
    # Even with generic extension, heading should override
    classified = classifier.classify(result, filename="document.pdf")
    assert classified.doc_type == DocType.PAPER


def test_classify_by_heading_book(
    classifier: DocumentClassifier, empty_metadata: DocumentMetadata
) -> None:
    blocks = (
        RawHeadingBlock(ordinal=0, text="Chapter 1", level=1),
        RawTextBlock(ordinal=1, text="Once upon a time..."),
    )
    result = build_result(blocks, empty_metadata)
    classified = classifier.classify(result)
    assert classified.doc_type == DocType.BOOK


def test_classify_by_heading_resume(
    classifier: DocumentClassifier, empty_metadata: DocumentMetadata
) -> None:
    blocks = (
        RawTextBlock(ordinal=0, text="John Doe"),
        RawHeadingBlock(ordinal=1, text="Experience", level=2),
    )
    result = build_result(blocks, empty_metadata)
    classified = classifier.classify(result)
    assert classified.doc_type == DocType.RESUME


def test_classify_by_heading_documentation(
    classifier: DocumentClassifier, empty_metadata: DocumentMetadata
) -> None:
    blocks = (RawHeadingBlock(ordinal=0, text="Getting Started", level=1),)
    result = build_result(blocks, empty_metadata)
    classified = classifier.classify(result)
    assert classified.doc_type == DocType.DOCUMENTATION


def test_classify_structural_code(
    classifier: DocumentClassifier, empty_metadata: DocumentMetadata
) -> None:
    blocks = (
        RawCodeBlock(ordinal=0, code="def foo(): pass"),
        RawCodeBlock(ordinal=1, code="def bar(): pass"),
        RawTextBlock(ordinal=2, text="This is a small comment"),
        RawCodeBlock(ordinal=3, code="print('hello')"),
        RawCodeBlock(ordinal=4, code="print('world')"),
    )
    build_result(blocks, empty_metadata)
    # 4 code blocks out of 5 = 80%, condition is > 0.8, let's see...
    # Oh wait, > 0.8 means strictly greater. 4/5 = 0.8. So it won't be code.
    # Let's add one more code block.
    blocks2 = (*blocks, RawCodeBlock(ordinal=5, code="pass"))
    result2 = build_result(blocks2, empty_metadata)
    classified = classifier.classify(result2)
    assert classified.doc_type == DocType.CODE


def test_classify_fallback_generic(
    classifier: DocumentClassifier, empty_metadata: DocumentMetadata
) -> None:
    blocks = (
        RawTextBlock(ordinal=0, text="Just some generic text."),
        RawTextBlock(ordinal=1, text="Nothing special here."),
    )
    result = build_result(blocks, empty_metadata)
    classified = classifier.classify(result, filename="unknown.txt")
    assert classified.doc_type == DocType.GENERIC


def test_classify_preserves_attributes(
    classifier: DocumentClassifier, empty_metadata: DocumentMetadata
) -> None:
    blocks = (RawTextBlock(ordinal=0, text="Text"),)
    result = build_result(blocks, empty_metadata)
    classified = classifier.classify(result, filename="script.py")

    # Should update doc_type but preserve everything else
    assert classified.doc_type == DocType.CODE
    assert classified.blocks == result.blocks
    assert classified.metadata == result.metadata
    assert classified.extracted_assets == result.extracted_assets
    assert classified.language == result.language


def test_classify_returns_same_instance_if_unchanged(
    classifier: DocumentClassifier, empty_metadata: DocumentMetadata
) -> None:
    blocks = (RawTextBlock(ordinal=0, text="Text"),)
    result = build_result(blocks, empty_metadata)
    # It is already GENERIC, and no rules match so it stays GENERIC
    classified = classifier.classify(result, filename="unknown.xyz")
    assert classified is result
