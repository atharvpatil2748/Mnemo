"""Acceptance tests for Phase 4 Module 4.8 ResumeChunker."""

import re
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from mnemo.chunkers import ResumeChunker
from mnemo.interfaces import (
    ChunkerInterfaceV2,
    ChunkingContext,
    ChunkingOptions,
    UnsupportedError,
)
from mnemo.models import (
    Block,
    DocType,
    DocumentMetadata,
    DocumentVersion,
    DocumentVersionStatus,
    EquationBlock,
    FrozenMetadata,
    HeadingBlock,
    ParsedDocument,
    TextBlock,
)


class WordCounter:
    tokenizer_id = "tests/words;adapter=v1"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def count(self, text: str) -> int:
        self.calls.append(text)
        return len(re.findall(r"\S+", text))


def _document(
    *blocks: Block, doc_type: DocType = DocType.RESUME, schema_version: int = 1
) -> ParsedDocument:
    return ParsedDocument(
        blocks=blocks,
        metadata=DocumentMetadata(
            content_hash="a" * 64,
            metadata=FrozenMetadata({"parser.resume.schema_version": schema_version}),
        ),
        language="en",
        doc_type=doc_type,
    )


def _context(document: ParsedDocument, *, target: int = 20, maximum: int = 40) -> ChunkingContext:
    return ChunkingContext(
        document_version=DocumentVersion(
            version_id=uuid4(),
            document_id=uuid4(),
            content_hash=document.metadata.content_hash,
            metadata=document.metadata,
            status=DocumentVersionStatus.CURRENT,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        options=ChunkingOptions(target_tokens=target, max_tokens=maximum),
    )


def _words(count: int, prefix: str = "word") -> str:
    return " ".join(f"{prefix}{index}" for index in range(count))


def test_v2_contract_capabilities() -> None:
    chunker = ResumeChunker()
    assert isinstance(chunker, ChunkerInterfaceV2)
    assert chunker.supported_doc_types == (DocType.RESUME,)
    capabilities = chunker.capabilities()
    assert capabilities.supported_doc_types == (DocType.RESUME,)
    assert capabilities.preserves_semantic_boundaries
    assert not capabilities.supports_parent_child
    assert not capabilities.supports_overlap


def test_rejects_non_resume_doc_types() -> None:
    chunker = ResumeChunker()
    doc = _document(doc_type=DocType.GENERIC)
    with pytest.raises(UnsupportedError, match=r"ResumeChunker supports only DocType\.RESUME"):
        chunker.chunk(doc, _context(doc), WordCounter())


def test_rejects_missing_or_invalid_schema_version() -> None:
    chunker = ResumeChunker()
    doc = _document(schema_version=2)
    with pytest.raises(UnsupportedError, match=r"parser\.resume\.schema_version == 1"):
        chunker.chunk(doc, _context(doc), WordCounter())


def test_resume_all_canonical_sections() -> None:
    chunker = ResumeChunker()
    b1 = HeadingBlock(
        ordinal=0,
        text="Contact",
        level=1,
        metadata=FrozenMetadata({"parser.resume.section": "contact"}),
    )
    b2 = TextBlock(
        ordinal=1, text="John Doe", metadata=FrozenMetadata({"parser.resume.section": "contact"})
    )
    b3 = HeadingBlock(
        ordinal=2,
        text="Summary",
        level=1,
        metadata=FrozenMetadata({"parser.resume.section": "summary"}),
    )
    b4 = TextBlock(
        ordinal=3,
        text="Expert engineer",
        metadata=FrozenMetadata({"parser.resume.section": "summary"}),
    )
    b5 = HeadingBlock(
        ordinal=4,
        text="Experience",
        level=1,
        metadata=FrozenMetadata({"parser.resume.section": "experience"}),
    )
    b6 = HeadingBlock(
        ordinal=5,
        text="Role 1",
        level=2,
        metadata=FrozenMetadata(
            {"parser.resume.section": "experience", "parser.resume.role_local_id": "r1"}
        ),
    )
    b7 = TextBlock(
        ordinal=6,
        text="Did stuff",
        metadata=FrozenMetadata(
            {"parser.resume.section": "experience", "parser.resume.role_local_id": "r1"}
        ),
    )
    b8 = HeadingBlock(
        ordinal=7,
        text="Role 2",
        level=2,
        metadata=FrozenMetadata(
            {"parser.resume.section": "experience", "parser.resume.role_local_id": "r2"}
        ),
    )
    b9 = TextBlock(
        ordinal=8,
        text="Did more stuff",
        metadata=FrozenMetadata(
            {"parser.resume.section": "experience", "parser.resume.role_local_id": "r2"}
        ),
    )

    doc = _document(b1, b2, b3, b4, b5, b6, b7, b8, b9)
    drafts = chunker.chunk(doc, _context(doc), WordCounter())

    assert len(drafts) == 4

    assert drafts[0].metadata.get("chunker.resume.section") == "contact"
    assert drafts[0].metadata.get("chunker.resume.role_local_id") is None

    assert drafts[1].metadata.get("chunker.resume.section") == "summary"

    assert drafts[2].metadata.get("chunker.resume.section") == "experience"
    assert drafts[2].metadata.get("chunker.resume.role_local_id") == "r1"

    assert drafts[3].metadata.get("chunker.resume.section") == "experience"
    assert drafts[3].metadata.get("chunker.resume.role_local_id") == "r2"


def test_resume_content_before_first_recognized_section_preserved_as_unknown() -> None:
    chunker = ResumeChunker()
    b1 = TextBlock(ordinal=0, text="Unknown stuff", metadata=FrozenMetadata())
    b2 = HeadingBlock(
        ordinal=1,
        text="Experience",
        level=1,
        metadata=FrozenMetadata({"parser.resume.section": "experience"}),
    )
    b3 = TextBlock(
        ordinal=2, text="Job", metadata=FrozenMetadata({"parser.resume.section": "experience"})
    )

    doc = _document(b1, b2, b3)
    drafts = chunker.chunk(doc, _context(doc), WordCounter())

    assert len(drafts) == 2
    assert "Unknown" in drafts[0].text
    assert drafts[0].metadata.get("chunker.resume.section") == "unknown"
    assert drafts[0].metadata.get("chunker.resume.role_local_id") is None

    assert "Job" in drafts[1].text
    assert drafts[1].metadata.get("chunker.resume.section") == "experience"


def test_experience_without_role_local_id_fallback() -> None:
    chunker = ResumeChunker()
    b1 = HeadingBlock(
        ordinal=0,
        text="Experience",
        level=1,
        metadata=FrozenMetadata({"parser.resume.section": "experience"}),
    )
    b2 = TextBlock(
        ordinal=1,
        text="Just some text without role",
        metadata=FrozenMetadata({"parser.resume.section": "experience"}),
    )

    doc = _document(b1, b2)
    drafts = chunker.chunk(doc, _context(doc), WordCounter())

    assert len(drafts) == 1
    assert drafts[0].metadata.get("chunker.resume.section") == "experience"
    assert drafts[0].metadata.get("chunker.resume.role_local_id") is None


def test_oversized_prose_splitting() -> None:
    chunker = ResumeChunker()
    long_text = _words(50)
    b1 = TextBlock(
        ordinal=0, text=long_text, metadata=FrozenMetadata({"parser.resume.section": "summary"})
    )

    doc = _document(b1)
    drafts = chunker.chunk(doc, _context(doc, target=20, maximum=40), WordCounter())

    assert len(drafts) >= 2
    for draft in drafts:
        assert WordCounter().count(draft.text) <= 40
        assert draft.metadata.get("chunker.resume.section") == "summary"


def test_oversized_atomic_structure_fails() -> None:
    chunker = ResumeChunker()
    long_latex = _words(50)
    b1 = EquationBlock(
        ordinal=0, latex=long_latex, metadata=FrozenMetadata({"parser.resume.section": "projects"})
    )

    doc = _document(b1)
    with pytest.raises(UnsupportedError, match="exceeds the effective token maximum"):
        chunker.chunk(doc, _context(doc, target=20, maximum=40), WordCounter())


def test_malformed_role_outside_experience() -> None:
    chunker = ResumeChunker()
    b1 = TextBlock(
        ordinal=0,
        text="Education",
        metadata=FrozenMetadata(
            {"parser.resume.section": "education", "parser.resume.role_local_id": "r1"}
        ),
    )

    doc = _document(b1)
    with pytest.raises(
        UnsupportedError, match="role_local_id is only valid within 'experience' section"
    ):
        chunker.chunk(doc, _context(doc), WordCounter())


def test_empty_section_ignored() -> None:
    chunker = ResumeChunker()
    b1 = HeadingBlock(
        ordinal=0,
        text="Summary",
        level=1,
        metadata=FrozenMetadata({"parser.resume.section": "summary"}),
    )
    b2 = HeadingBlock(
        ordinal=1,
        text="Experience",
        level=1,
        metadata=FrozenMetadata({"parser.resume.section": "experience"}),
    )
    b3 = TextBlock(
        ordinal=2, text="Job", metadata=FrozenMetadata({"parser.resume.section": "experience"})
    )

    doc = _document(b1, b2, b3)
    drafts = chunker.chunk(doc, _context(doc), WordCounter())

    assert len(drafts) == 1
    assert drafts[0].metadata.get("chunker.resume.section") == "experience"
    assert "Summary" not in drafts[0].text


def test_unicode_content() -> None:
    chunker = ResumeChunker()
    b1 = TextBlock(
        ordinal=0,
        text="こんにちは世界",
        metadata=FrozenMetadata({"parser.resume.section": "summary"}),
    )

    doc = _document(b1)
    drafts = chunker.chunk(doc, _context(doc), WordCounter())
    assert len(drafts) == 1
    assert drafts[0].text == "こんにちは世界"


def test_contiguous_provenance() -> None:
    chunker = ResumeChunker()
    b1 = TextBlock(
        ordinal=0, text="T1", metadata=FrozenMetadata({"parser.resume.section": "summary"})
    )
    b2 = TextBlock(
        ordinal=1, text="T2", metadata=FrozenMetadata({"parser.resume.section": "summary"})
    )

    doc = _document(b1, b2)
    drafts = chunker.chunk(doc, _context(doc), WordCounter())
    assert len(drafts) == 1
    assert drafts[0].source_span.start_ordinal == 0
    assert drafts[0].source_span.end_ordinal == 1
