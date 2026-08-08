"""Tests for chunks, scored results, and validated metadata filters."""

from dataclasses import FrozenInstanceError, replace
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from mnemo.models import (
    Chunk,
    ChunkPosition,
    ChunkType,
    DocType,
    MetadataFilter,
    ScoredChunk,
)
from pydantic import ValidationError


def _chunk(document_id: UUID, version_id: UUID) -> Chunk:
    return Chunk(
        id="c" * 64,
        text="Grounded evidence",
        document_id=document_id,
        version_id=version_id,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(
            page_number=2,
            section_index=1,
            chunk_index_in_section=0,
            start_offset=10,
            end_offset=27,
        ),
        heading_path=("Chapter 1",),
        parent_chunk_id="d" * 64,
        sibling_ids=("e" * 64,),
        embedding=(0.1, 0.2),
    )


def test_chunk_position_offsets_are_optional_navigation_data() -> None:
    """Canonical text offsets are paired, ordered, immutable navigation fields."""
    without_offsets = ChunkPosition(section_index=0, chunk_index_in_section=0)
    with_offsets = replace(without_offsets, start_offset=0, end_offset=5)

    assert without_offsets.start_offset is None
    assert hash(with_offsets) == hash(replace(with_offsets))
    with pytest.raises(FrozenInstanceError):
        with_offsets.start_offset = 1  # type: ignore[misc]

    for overrides in (
        {"section_index": -1},
        {"chunk_index_in_section": -1},
        {"page_number": 0},
        {"start_offset": 0},
        {"end_offset": 1},
        {"start_offset": -1, "end_offset": 1},
        {"start_offset": 2, "end_offset": 2},
    ):
        with pytest.raises((TypeError, ValueError)):
            ChunkPosition(
                section_index=0,
                chunk_index_in_section=0,
                **overrides,
            )


def test_chunk_construction_identity_and_enum(document_id: UUID, version_id: UUID) -> None:
    """Chunks are versioned, immutable, and compare by content-derived ID."""
    chunk = _chunk(document_id, version_id)
    renamed_heading = replace(chunk, heading_path=("Renamed",))

    assert chunk == renamed_heading
    assert hash(chunk) == hash(renamed_heading)
    assert chunk != object()
    assert ChunkType("passage") is ChunkType.PASSAGE
    assert {member.value for member in ChunkType} == {
        "passage",
        "summary",
        "verbatim",
        "question",
        "code",
        "caption",
        "equation",
    }
    with pytest.raises(ValueError):
        ChunkType("image")


def test_chunk_validation(document_id: UUID, version_id: UUID) -> None:
    """Malformed chunk identities, links, vectors, and types are rejected."""
    chunk = _chunk(document_id, version_id)
    cases: tuple[Any, ...] = (
        {"id": "bad"},
        {"text": " "},
        {"document_id": "bad"},
        {"version_id": "bad"},
        {"chunk_type": "passage"},
        {"position": object()},
        {"heading_path": ("",)},
        {"heading_path": ["Heading"]},
        {"parent_chunk_id": "bad"},
        {"parent_chunk_id": chunk.id},
        {"sibling_ids": ("bad",)},
        {"sibling_ids": ["e" * 64]},
        {"sibling_ids": (chunk.id,)},
        {"sibling_ids": ("e" * 64, "e" * 64)},
        {"metadata": {}},
        {"embedding": ()},
        {"embedding": [0.1]},
        {"embedding": (float("nan"),)},
    )
    for overrides in cases:
        with pytest.raises((TypeError, ValueError)):
            replace(chunk, **overrides)


def test_scored_chunk_preserves_raw_score(document_id: UUID, version_id: UUID) -> None:
    """Scored results expose raw score, source, and one-based rank."""
    chunk = _chunk(document_id, version_id)
    result = ScoredChunk(chunk=chunk, score=-3.5, source="sparse", rank=1)

    assert result.score == -3.5
    assert result == replace(result)
    assert hash(result) == hash(replace(result))
    for overrides in (
        {"chunk": object()},
        {"score": float("inf")},
        {"source": " "},
        {"rank": 0},
        {"rank": True},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(result, **overrides)


def test_metadata_filter_validation_and_json_serialization() -> None:
    """Pydantic validates, freezes, and serializes the approved filter schema."""
    source_id = uuid4()
    metadata_filter = MetadataFilter(
        notebook_id=uuid4(),
        doc_types=(DocType.BOOK, DocType.PAPER),
        date_after=date(2020, 1, 1),
        date_before=date(2026, 1, 1),
        source_ids=(source_id,),
    )
    payload = metadata_filter.model_dump(mode="json")

    assert payload["doc_types"] == ["book", "paper"]
    assert payload["source_ids"] == [str(source_id)]
    assert hash(metadata_filter) == hash(metadata_filter.model_copy())
    with pytest.raises(ValidationError):
        metadata_filter.rank = 2  # type: ignore[attr-defined]
    with pytest.raises(ValidationError):
        MetadataFilter(doc_types=(DocType.BOOK, DocType.BOOK))
    with pytest.raises(ValidationError):
        MetadataFilter(source_ids=(source_id, source_id))
    with pytest.raises(ValidationError):
        MetadataFilter(date_after=date(2026, 1, 2), date_before=date(2026, 1, 1))
    with pytest.raises(ValidationError):
        MetadataFilter(unknown=True)  # type: ignore[call-arg]
