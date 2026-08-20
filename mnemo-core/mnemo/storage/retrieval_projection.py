"""Internal derived metadata used only by retrieval indexes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from mnemo.models import DocType


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalMetadataProjection:
    """Version-aware metadata projected from canonical stores into vector payloads."""

    doc_type: DocType
    publication_date: date | None
    title: str | None = None
    source_ids: tuple[UUID, ...] = ()
    notebook_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.doc_type, DocType):
            raise TypeError("doc_type must be DocType")
        if self.publication_date is not None and not isinstance(self.publication_date, date):
            raise TypeError("publication_date must be date or None")
        if self.title is not None and (not isinstance(self.title, str) or not self.title.strip()):
            raise TypeError("title must be a non-empty string or None")
        if any(not isinstance(value, UUID) for value in self.source_ids):
            raise TypeError("source_ids must contain UUID values")
        if any(not isinstance(value, UUID) for value in self.notebook_ids):
            raise TypeError("notebook_ids must contain UUID values")
        if tuple(sorted(set(self.source_ids), key=str)) != self.source_ids:
            raise ValueError("source_ids must be sorted and unique")
        if tuple(sorted(set(self.notebook_ids), key=str)) != self.notebook_ids:
            raise ValueError("notebook_ids must be sorted and unique")

    def payload(self) -> dict[str, object]:
        """Return the Qdrant-neutral payload representation."""
        payload: dict[str, object] = {
            "doc_type": self.doc_type.value,
            "source_ids": [str(value) for value in self.source_ids],
            "notebook_ids": [str(value) for value in self.notebook_ids],
        }
        if self.publication_date is not None:
            payload["publication_date"] = self.publication_date.isoformat()
            payload["publication_date_ordinal"] = self.publication_date.toordinal()
        if self.title is not None:
            payload["document_title"] = self.title
        return payload
