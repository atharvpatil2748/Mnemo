"""Unit tests for PPTXParser (Module 3.6 / ADR-0036)."""

import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from uuid import uuid4

import pytest
from mnemo.chunkers.slides import SlidesChunker
from mnemo.classifier import DocumentClassifier
from mnemo.cleaner import DocumentCleaner
from mnemo.ingestion import DocumentCanonicalizer
from mnemo.interfaces import (
    ChunkingContext,
    ChunkingOptions,
    ContractValidationError,
    FileMetadata,
)
from mnemo.interfaces.parser_models import ParseResult, RawHeadingBlock, RawTextBlock
from mnemo.models import DocType, DocumentVersion, DocumentVersionStatus
from mnemo.parsers.pptx import PPTXParser
from mnemo.tokenizers import O200KBaseTokenCounter
from mnemo_server.tokenizer_provisioning import provision_tokenizer

_SHA256 = "a" * 64


@pytest.fixture
def parser() -> PPTXParser:
    return PPTXParser()


@pytest.fixture
def metadata() -> FileMetadata:
    return FileMetadata(
        content_hash=_SHA256,
        size_bytes=1024,
        mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


def test_supported_formats(parser: PPTXParser) -> None:
    assert ".pptx" in parser.supported_formats
    assert ".ppt" not in parser.supported_formats  # Legacy binary format is unsupported


def test_capabilities(parser: PPTXParser) -> None:
    caps = parser.capabilities()
    assert caps.supports_images is False
    assert caps.supports_tables is True
    assert caps.supports_ocr is False


def test_empty_bytes_raises_validation_error(parser: PPTXParser, metadata: FileMetadata) -> None:
    with pytest.raises(ContractValidationError, match="Cannot parse empty PPTX"):
        parser.parse(b"", "empty.pptx", metadata)


def test_malformed_zip_raises_validation_error(parser: PPTXParser, metadata: FileMetadata) -> None:
    with pytest.raises(ContractValidationError, match="Failed to open PPTX archive"):
        parser.parse(b"not a valid zip", "corrupt.pptx", metadata)


def test_missing_slide_files_raises_validation_error(
    parser: PPTXParser, metadata: FileMetadata
) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types></Types>")
    with pytest.raises(ContractValidationError, match="PPTX contains no slide files"):
        parser.parse(buf.getvalue(), "no_slides.pptx", metadata)


def test_synthetic_pptx_slide_extraction(parser: PPTXParser, metadata: FileMetadata) -> None:
    buf = io.BytesIO()
    slide1_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
           xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
        <p:cSld>
            <p:spTree>
                <p:sp>
                    <p:nvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>
                    <p:txBody><a:p><a:r><a:t>Quarterly Review</a:t></a:r></a:p></p:txBody>
                </p:sp>
                <p:sp>
                    <p:txBody><a:p><a:r><a:t>Presenter: John Doe</a:t></a:r></a:p></p:txBody>
                </p:sp>
            </p:spTree>
        </p:cSld>
    </p:sld>"""

    slide2_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
           xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
        <p:cSld>
            <p:spTree>
                <p:sp>
                    <p:nvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>
                    <p:txBody><a:p><a:r><a:t>Key Metrics</a:t></a:r></a:p></p:txBody>
                </p:sp>
                <p:sp>
                    <p:txBody>
                        <a:p><a:r><a:t>Revenue grew by 20%</a:t></a:r></a:p>
                        <a:p><a:r><a:t>Active users exceeded 1M</a:t></a:r></a:p>
                    </p:txBody>
                </p:sp>
            </p:spTree>
        </p:cSld>
    </p:sld>"""

    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ppt/slides/slide1.xml", slide1_xml)
        z.writestr("ppt/slides/slide2.xml", slide2_xml)

    result = parser.parse(buf.getvalue(), "presentation.pptx", metadata)

    assert isinstance(result, ParseResult)
    assert result.doc_type == DocType.SLIDES
    assert len(result.blocks) == 5  # slide 1 title + body, slide 2 title + 2 body paragraphs

    b0 = result.blocks[0]
    assert isinstance(b0, RawHeadingBlock)
    assert b0.text == "Quarterly Review"
    assert b0.page_number == 1

    b1 = result.blocks[1]
    assert isinstance(b1, RawTextBlock)
    assert b1.text == "Presenter: John Doe"
    assert b1.page_number == 1

    b2 = result.blocks[2]
    assert isinstance(b2, RawHeadingBlock)
    assert b2.text == "Key Metrics"
    assert b2.page_number == 2

    b3 = result.blocks[3]
    assert isinstance(b3, RawTextBlock)
    assert "Revenue grew by 20%" in b3.text
    assert b3.page_number == 2


def test_golden_coordinator_pptx_pipeline(parser: PPTXParser) -> None:
    p = Path("goldenDataset/Coordinator Application 2026–27.pptx")  # noqa: RUF001
    if not p.exists():
        pytest.skip("Golden dataset PPTX file not found")

    data = p.read_bytes()
    meta = FileMetadata(
        content_hash=_SHA256,
        size_bytes=len(data),
        mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )

    result = parser.parse(data, p.name, meta)
    assert len(result.blocks) > 0

    cleaner = DocumentCleaner()
    cleaned = cleaner.clean(result)

    classifier = DocumentClassifier()
    classified = classifier.classify(cleaned, p.name)
    assert classified.doc_type == DocType.SLIDES
    assert classified.metadata.metadata.get("parser.slide.schema_version") == 1

    canonicalizer = DocumentCanonicalizer()
    canonical = canonicalizer.canonicalize(classified, MappingProxyType({}))

    tok = O200KBaseTokenCounter(provision_tokenizer())
    chunker = SlidesChunker()

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

    drafts = chunker.chunk(canonical, ctx, tok)
    assert len(drafts) == 21  # exactly 21 slides
    assert drafts[0].chunk_type.value == "summary"  # Title slide
    assert "Coordinator Application" in drafts[0].text
