"""Retrieval result and metadata-filter domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from ._shared import require_finite, require_non_empty
from .chunks import Chunk
from .documents import DocType


class MetadataFilter(BaseModel):
    """Immutable validated hard constraints for retrieval."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    notebook_id: UUID | None = None
    doc_types: tuple[DocType, ...] = ()
    date_after: date | None = None
    date_before: date | None = None
    source_ids: tuple[UUID, ...] = ()

    @field_validator("doc_types")
    @classmethod
    def _require_unique_doc_types(cls, value: tuple[DocType, ...]) -> tuple[DocType, ...]:
        if len(set(value)) != len(value):
            raise ValueError("doc_types must contain unique values")
        return value

    @field_validator("source_ids")
    @classmethod
    def _require_unique_source_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(set(value)) != len(value):
            raise ValueError("source_ids must contain unique values")
        return value

    @model_validator(mode="after")
    def _require_ordered_dates(self) -> MetadataFilter:
        if (
            self.date_after is not None
            and self.date_before is not None
            and self.date_after > self.date_before
        ):
            raise ValueError("date_after cannot be later than date_before")
        return self


@dataclass(frozen=True, slots=True, kw_only=True)
class ScoredChunk:
    """A chunk paired with one ranking source's raw score and rank."""

    chunk: Chunk
    score: float
    source: str
    rank: int

    def __post_init__(self) -> None:
        """Validate the raw retrieval result fields."""
        if not isinstance(self.chunk, Chunk):
            raise TypeError("chunk must be Chunk")
        require_finite(self.score, "score")
        require_non_empty(self.source, "source")
        if isinstance(self.rank, bool) or not isinstance(self.rank, int):
            raise TypeError("rank must be an integer")
        if self.rank < 1:
            raise ValueError("rank must be positive")
