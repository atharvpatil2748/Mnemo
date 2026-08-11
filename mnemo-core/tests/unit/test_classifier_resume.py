"""Unit tests for Resume semantic boundaries in DocumentClassifier."""

import json
from typing import Any

import pytest
from mnemo.classifier import DocumentClassifier
from mnemo.cleaner import DocumentCleaner
from mnemo.ingestion.canonicalizer import DocumentCanonicalizer
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


@pytest.fixture
def cleaner() -> DocumentCleaner:
    return DocumentCleaner()


@pytest.fixture
def canonicalizer() -> DocumentCanonicalizer:
    return DocumentCanonicalizer()


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


def test_resume_canonical_sections(
    classifier: DocumentClassifier, empty_metadata: DocumentMetadata
) -> None:
    blocks = (
        RawHeadingBlock(ordinal=0, text="  eXPerience  ", level=2),
        RawTextBlock(ordinal=1, text="stuff"),
        RawHeadingBlock(ordinal=2, text="education", level=2),
        RawTextBlock(ordinal=3, text="stuff"),
        RawHeadingBlock(ordinal=4, text="SKILLS", level=2),
        RawHeadingBlock(ordinal=5, text="projects", level=2),
        RawHeadingBlock(ordinal=6, text="publications", level=2),
        RawHeadingBlock(ordinal=7, text="profile", level=2),
        RawHeadingBlock(ordinal=8, text="contact information", level=2),
    )
    result = build_result(blocks, empty_metadata)
    classified = classifier.classify(result)

    assert classified.doc_type == DocType.RESUME
    assert classified.blocks[0].metadata.get("parser.resume.section") == "experience"
    assert classified.blocks[1].metadata.get("parser.resume.section") == "experience"
    assert classified.blocks[2].metadata.get("parser.resume.section") == "education"
    assert classified.blocks[4].metadata.get("parser.resume.section") == "skills"
    assert classified.blocks[5].metadata.get("parser.resume.section") == "projects"
    assert classified.blocks[6].metadata.get("parser.resume.section") == "publications"
    assert classified.blocks[7].metadata.get("parser.resume.section") == "summary"
    assert classified.blocks[8].metadata.get("parser.resume.section") == "contact"


def test_resume_fail_closed_unknown_heading(
    classifier: DocumentClassifier, empty_metadata: DocumentMetadata
) -> None:
    blocks = (
        # Resume detected due to experience heading
        RawHeadingBlock(ordinal=0, text="Random Hobby", level=2),
        RawTextBlock(ordinal=1, text="I like fishing"),
        RawHeadingBlock(ordinal=2, text="Experience", level=2),
    )
    result = build_result(blocks, empty_metadata)
    classified = classifier.classify(result)

    assert classified.doc_type == DocType.RESUME
    assert "parser.resume.section" not in classified.blocks[0].metadata
    assert "parser.resume.section" not in classified.blocks[1].metadata
    assert classified.blocks[2].metadata.get("parser.resume.section") == "experience"


def test_resume_fail_closed_content_before_first_section(
    classifier: DocumentClassifier, empty_metadata: DocumentMetadata
) -> None:
    blocks = (
        RawTextBlock(ordinal=0, text="John Doe"),
        RawTextBlock(ordinal=1, text="123 Street"),
        RawHeadingBlock(ordinal=2, text="Experience", level=2),
    )
    result = build_result(blocks, empty_metadata)
    classified = classifier.classify(result)

    # Should not guess contact or summary for 0 and 1
    assert "parser.resume.section" not in classified.blocks[0].metadata
    assert "parser.resume.section" not in classified.blocks[1].metadata
    assert classified.blocks[2].metadata.get("parser.resume.section") == "experience"


def test_resume_roles_strict_hierarchy(
    classifier: DocumentClassifier, empty_metadata: DocumentMetadata
) -> None:
    blocks = (
        RawHeadingBlock(ordinal=0, text="Experience", level=2),
        RawHeadingBlock(ordinal=1, text="Software Engineer", level=3),  # Valid role
        RawTextBlock(ordinal=2, text="Did things"),
        RawTextBlock(ordinal=3, text="Date: 2020-2021"),
        RawHeadingBlock(ordinal=4, text="Data Scientist", level=3),  # Valid role
        RawHeadingBlock(
            ordinal=5, text="Projects inside Data Scientist", level=4
        ),  # Nested heading
        RawHeadingBlock(ordinal=6, text="Education", level=2),  # Resets section
    )
    result = build_result(blocks, empty_metadata)
    classified = classifier.classify(result)

    assert classified.doc_type == DocType.RESUME

    # Block 1 (role 1)
    assert classified.blocks[1].metadata.get("parser.resume.role_local_id") == "role-000001"
    assert classified.blocks[2].metadata.get("parser.resume.role_local_id") == "role-000001"
    assert classified.blocks[3].metadata.get("parser.resume.role_local_id") == "role-000001"

    # Block 4 (role 2)
    assert classified.blocks[4].metadata.get("parser.resume.role_local_id") == "role-000002"
    # Block 5 (nested heading inside role 2)
    assert classified.blocks[5].metadata.get("parser.resume.role_local_id") == "role-000002"

    # Block 6 (Education)
    assert classified.blocks[6].metadata.get("parser.resume.section") == "education"
    assert "parser.resume.role_local_id" not in classified.blocks[6].metadata


def test_resume_roles_fail_closed_ambiguous(
    classifier: DocumentClassifier, empty_metadata: DocumentMetadata
) -> None:
    blocks = (
        RawHeadingBlock(ordinal=0, text="Experience", level=2),
        RawTextBlock(ordinal=1, text="**Software Engineer** at Acme"),  # Not a heading!
        RawTextBlock(ordinal=2, text="Did things"),
    )
    result = build_result(blocks, empty_metadata)
    classified = classifier.classify(result)

    assert classified.blocks[0].metadata.get("parser.resume.section") == "experience"
    # Should not invent a role
    assert "parser.resume.role_local_id" not in classified.blocks[1].metadata
    assert classified.blocks[1].metadata.get("parser.resume.section") == "experience"


def test_resume_roles_malformed(
    classifier: DocumentClassifier, empty_metadata: DocumentMetadata
) -> None:
    blocks = (
        RawHeadingBlock(ordinal=0, text="Experience", level=2),
        # A heading at the same level as Experience is NOT a role child
        RawHeadingBlock(ordinal=1, text="Software Engineer", level=2),
    )
    result = build_result(blocks, empty_metadata)
    classified = classifier.classify(result)

    # Not deeper, so it shouldn't be a role.
    # Wait, in our logic, if it's level 2, it is not > current_section_level (2).
    # But it will be checked against canonical sections. It won't match, so it's
    # ignored as a canonical section,
    # and since it's not > 2, it's NOT a role. So it stays experience, no role.
    assert "parser.resume.role_local_id" not in classified.blocks[1].metadata


def test_resume_metadata_immutability_and_json(
    classifier: DocumentClassifier, empty_metadata: DocumentMetadata
) -> None:
    blocks = (RawHeadingBlock(ordinal=0, text="Experience", level=2),)
    result = build_result(blocks, empty_metadata)
    classified = classifier.classify(result)

    # Should be immutable
    with pytest.raises(TypeError):
        classified.blocks[0].metadata["parser.resume.section"] = "foo"  # type: ignore

    # Should be JSON serializable
    json.dumps(dict(classified.blocks[0].metadata))
    json.dumps(dict(classified.metadata.metadata))


def test_resume_pipeline_preservation(
    cleaner: DocumentCleaner,
    classifier: DocumentClassifier,
    canonicalizer: DocumentCanonicalizer,
    empty_metadata: DocumentMetadata,
) -> None:
    blocks = (
        RawHeadingBlock(ordinal=0, text="Experience", level=2),
        RawHeadingBlock(ordinal=1, text="Role", level=3),
    )
    result = build_result(blocks, empty_metadata)

    cleaned = cleaner.clean(result)
    classified = classifier.classify(cleaned)
    parsed_doc = canonicalizer.canonicalize(classified, {})

    assert parsed_doc.metadata.metadata.get("parser.resume.schema_version") == 1

    block_0_meta = parsed_doc.blocks[0].metadata
    assert block_0_meta.get("parser.resume.section") == "experience"

    block_1_meta = parsed_doc.blocks[1].metadata
    assert block_1_meta.get("parser.resume.section") == "experience"
    assert block_1_meta.get("parser.resume.role_local_id") == "role-000001"
