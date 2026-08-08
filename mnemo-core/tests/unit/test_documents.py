"""Tests for parsed documents and document registry models."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from mnemo.models import (
    CaptionBlock,
    DocType,
    Document,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    ParsedDocument,
    TextBlock,
)


def _metadata(content_hash: str, *, page_count: int | None = 2) -> DocumentMetadata:
    return DocumentMetadata(
        content_hash=content_hash,
        title="Mnemo",
        authors=("Atharv Patil",),
        publication_date=date(2026, 8, 6),
        url="https://example.test/mnemo",
        doi="10.0000/mnemo",
        isbn="9780000000000",
        page_count=page_count,
    )


def test_document_metadata_and_parsed_document(content_hash: str) -> None:
    """Parser output preserves typed metadata, ordered blocks, and enums."""
    metadata = _metadata(content_hash)
    parsed = ParsedDocument(
        blocks=(
            TextBlock(ordinal=0, text="First", page_number=1),
            TextBlock(ordinal=1, text="Second", page_number=2),
        ),
        metadata=metadata,
        language="en",
        doc_type=DocType.DOCUMENTATION,
    )

    assert parsed.metadata == metadata
    assert hash(parsed) == hash(replace(parsed))
    assert DocType("documentation") is DocType.DOCUMENTATION
    assert {member.value for member in DocType} == {
        "book",
        "paper",
        "code",
        "email",
        "resume",
        "slides",
        "markdown",
        "documentation",
        "generic",
    }
    with pytest.raises(ValueError):
        DocType("unknown")
    with pytest.raises(FrozenInstanceError):
        metadata.title = "Changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "overrides",
    [
        {"content_hash": "BAD"},
        {"title": " "},
        {"authors": ("",)},
        {"authors": ["Author"]},
        {"publication_date": datetime(2026, 8, 6, tzinfo=UTC)},
        {"url": ""},
        {"doi": ""},
        {"isbn": ""},
        {"page_count": 0},
        {"metadata": {}},
    ],
)
def test_document_metadata_validation(content_hash: str, overrides: dict[str, object]) -> None:
    """Malformed metadata cannot enter the parsed IR."""
    values: dict[str, object] = {"content_hash": content_hash}
    values.update(overrides)
    with pytest.raises((TypeError, ValueError)):
        DocumentMetadata(**values)  # type: ignore[arg-type]


def test_parsed_document_validation(content_hash: str) -> None:
    """Parsed documents enforce local ordering, typing, and page bounds."""
    metadata = _metadata(content_hash, page_count=1)
    invalid_cases: tuple[Any, ...] = (
        {"blocks": (TextBlock(ordinal=1, text="x"),)},
        {"blocks": []},
        {"blocks": (object(),)},
        {"metadata": object()},
        {"language": " "},
        {"doc_type": "generic"},
        {"blocks": (TextBlock(ordinal=0, text="x", page_number=2),)},
        {"blocks": (CaptionBlock(ordinal=0, text="caption", target_ordinal=1),)},
    )
    base: dict[str, object] = {
        "blocks": (),
        "metadata": metadata,
        "language": "und",
        "doc_type": DocType.GENERIC,
    }
    for overrides in invalid_cases:
        values = base | overrides
        with pytest.raises((TypeError, ValueError)):
            ParsedDocument(**values)


def test_document_version_and_registry_identity(
    document_id: UUID, version_id: UUID, timestamp: datetime, content_hash: str
) -> None:
    """The registry separates stable document identity from version identity."""
    metadata = _metadata(content_hash)
    current = DocumentVersion(
        version_id=version_id,
        document_id=document_id,
        content_hash=content_hash,
        metadata=metadata,
        status=DocumentVersionStatus.CURRENT,
        created_at=timestamp,
    )
    same_identity = replace(current, status=DocumentVersionStatus.SUPERSEDED)
    document = Document(
        document_id=document_id,
        versions=(current,),
        current_version_id=version_id,
        current_hash=content_hash,
        status=DocumentStatus.INDEXED,
        created_at=timestamp,
        updated_at=timestamp,
    )
    other_snapshot = replace(document, status=DocumentStatus.ENRICHED)

    assert current == same_identity
    assert hash(current) == hash(same_identity)
    assert current != object()
    assert document == other_snapshot
    assert hash(document) == hash(other_snapshot)
    assert document != object()
    assert DocumentStatus("indexed") is DocumentStatus.INDEXED
    assert DocumentVersionStatus("current") is DocumentVersionStatus.CURRENT


def test_document_version_validation(
    document_id: UUID, version_id: UUID, timestamp: datetime, content_hash: str
) -> None:
    """Version identity, hashes, status, and timestamps are validated."""
    metadata = _metadata(content_hash)
    base: dict[str, object] = {
        "version_id": version_id,
        "document_id": document_id,
        "content_hash": content_hash,
        "metadata": metadata,
        "status": DocumentVersionStatus.CURRENT,
        "created_at": timestamp,
    }
    cases = (
        {"version_id": "bad"},
        {"document_id": "bad"},
        {"content_hash": "b" * 64},
        {"metadata": object()},
        {"status": "current"},
        {"created_at": datetime(2026, 8, 6)},
    )
    for overrides in cases:
        with pytest.raises((TypeError, ValueError)):
            DocumentVersion(**(base | overrides))  # type: ignore[arg-type]


def test_document_registry_validation(
    document_id: UUID, version_id: UUID, timestamp: datetime, content_hash: str
) -> None:
    """Registry aggregates reject inconsistent current-version state."""
    metadata = _metadata(content_hash)
    current = DocumentVersion(
        version_id=version_id,
        document_id=document_id,
        content_hash=content_hash,
        metadata=metadata,
        status=DocumentVersionStatus.CURRENT,
        created_at=timestamp,
    )
    base: dict[str, object] = {
        "document_id": document_id,
        "versions": (current,),
        "current_version_id": version_id,
        "current_hash": content_hash,
        "status": DocumentStatus.INDEXED,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    duplicate_version = replace(current, status=DocumentVersionStatus.SUPERSEDED)
    cases = (
        {"document_id": "bad"},
        {"versions": ()},
        {"versions": [current]},
        {"versions": (object(),)},
        {"versions": (replace(current, document_id=uuid4()),)},
        {"versions": (current, duplicate_version)},
        {"versions": (replace(current, status=DocumentVersionStatus.SUPERSEDED),)},
        {"current_version_id": uuid4()},
        {"current_hash": "b" * 64},
        {"status": "indexed"},
        {"updated_at": timestamp - timedelta(seconds=1)},
    )
    for overrides in cases:
        with pytest.raises((TypeError, ValueError)):
            Document(**(base | overrides))  # type: ignore[arg-type]
