import pytest
from mnemo.classifier.classifier import DocumentClassifier
from mnemo.interfaces.parser_models import ParseResult, RawHeadingBlock, RawListBlock, RawTextBlock
from mnemo.models._shared import FrozenMetadata
from mnemo.models.documents import DocType, DocumentMetadata


@pytest.fixture
def classifier() -> DocumentClassifier:
    return DocumentClassifier()


def test_classifier_documentation_annotation(classifier: DocumentClassifier) -> None:
    blocks = (
        RawHeadingBlock(ordinal=0, text="API Reference", level=1),
        RawHeadingBlock(ordinal=1, text="Parameters", level=2),
        RawTextBlock(ordinal=2, text="some text"),
        RawHeadingBlock(ordinal=3, text="Table of Contents", level=1),
        RawListBlock(ordinal=4, items=("item 1",)),
        RawHeadingBlock(ordinal=5, text="Overview", level=1),
        RawTextBlock(ordinal=6, text="Note: this is a note"),
        RawTextBlock(ordinal=7, text="Warning: something bad"),
        RawTextBlock(ordinal=8, text="text without callout"),
        RawListBlock(
            ordinal=9,
            items=("step 1", "step 2"),
            metadata=FrozenMetadata({"parser.markdown.list": {"ordered": True}}),
        ),
        RawTextBlock(
            ordinal=10,
            text="text block with md source",
            metadata=FrozenMetadata({"parser.markdown.source": ":::tip\nDo this\n:::"}),
        ),
        RawTextBlock(
            ordinal=11,
            text="text block with md quote",
            metadata=FrozenMetadata({"parser.markdown.source": "> **Caution**\n> Careful"}),
        ),
    )
    result = ParseResult(
        blocks=blocks,
        extracted_assets=(),
        metadata=DocumentMetadata(content_hash="0" * 64, metadata=FrozenMetadata()),
        language="en",
        doc_type=DocType.GENERIC,
    )

    annotated = classifier.classify(result, filename=None)
    assert annotated.doc_type == DocType.DOCUMENTATION
    assert annotated.metadata.metadata.get("parser.documentation.schema_version") == 1

    blocks_dict = {b.ordinal: b for b in annotated.blocks}

    assert blocks_dict[0].metadata.get("parser.documentation.role") == "api_reference"
    assert blocks_dict[1].metadata.get("parser.documentation.role") == "api_reference"
    assert blocks_dict[2].metadata.get("parser.documentation.role") == "api_reference"

    assert blocks_dict[3].metadata.get("parser.documentation.role") == "toc"
    assert blocks_dict[4].metadata.get("parser.documentation.role") == "toc"

    assert blocks_dict[5].metadata.get("parser.documentation.role") is None

    assert blocks_dict[6].metadata.get("parser.documentation.role") == "callout"
    assert blocks_dict[6].metadata.get("parser.documentation.callout_type") == "note"

    assert blocks_dict[7].metadata.get("parser.documentation.role") == "callout"
    assert blocks_dict[7].metadata.get("parser.documentation.callout_type") == "warning"

    assert blocks_dict[8].metadata.get("parser.documentation.role") is None

    assert blocks_dict[9].metadata.get("parser.documentation.role") == "task_block"

    assert blocks_dict[10].metadata.get("parser.documentation.role") == "callout"
    assert blocks_dict[10].metadata.get("parser.documentation.callout_type") == "tip"

    assert blocks_dict[11].metadata.get("parser.documentation.role") == "callout"
    assert blocks_dict[11].metadata.get("parser.documentation.callout_type") == "caution"
