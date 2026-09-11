"""Side-by-side Full Multilingual V2 sparse projection contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid5

from ._shared import require_non_empty, require_sha256, require_utc
from .multilingual import LanguageCode, LanguageEvidenceReferenceV3
from .text_representations import ObservationReferenceV1, TextRepresentationReferenceV1

_SPARSE_ROW_NAMESPACE = UUID("7bf61132-e47f-5aa9-9741-d91f424cd4c0")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualEvidencePositionV1:
    """Typed searchable location; absence remains explicit instead of fabricated."""

    page_number: int | None = None
    section_index: int | None = None
    heading_path: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.page_number is not None and self.page_number < 1:
            raise ValueError("page_number must be positive")
        if self.section_index is not None and self.section_index < 0:
            raise ValueError("section_index must be non-negative")
        if any(not item.strip() for item in self.heading_path):
            raise ValueError("heading_path entries must not be blank")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualTextProjectionRowV2:
    row_id: UUID
    source: LanguageEvidenceReferenceV3
    representation: TextRepresentationReferenceV1
    language: LanguageCode
    text: str
    text_hash: str
    position: MultilingualEvidencePositionV1
    language_observation_references: tuple[ObservationReferenceV1, ...]
    script_observation_references: tuple[ObservationReferenceV1, ...]
    generation_id: UUID
    source_generation_ids: tuple[UUID, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        require_non_empty(self.text, "text")
        require_sha256(self.text_hash, "text_hash")
        require_utc(self.created_at, "created_at")
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != self.text_hash:
            raise ValueError("sparse projection text hash mismatch")
        if self.representation.evidence_reference != self.source:
            raise ValueError("sparse projection source/representation mismatch")
        if self.representation.content_hash != self.text_hash:
            raise ValueError("sparse projection text differs from representation")
        if len(set(self.source_generation_ids)) != len(self.source_generation_ids):
            raise ValueError("source generation identities must be unique")
        if self.row_id != multilingual_text_projection_row_v2_id(
            source=self.source,
            representation=self.representation,
            language=self.language,
            generation_id=self.generation_id,
        ):
            raise ValueError("multilingual sparse row identity mismatch")


def multilingual_text_projection_row_v2_id(
    *,
    source: LanguageEvidenceReferenceV3,
    representation: TextRepresentationReferenceV1,
    language: LanguageCode,
    generation_id: UUID,
) -> UUID:
    payload = {
        "source_reference_digest": source.identity_digest,
        "representation_reference_id": str(representation.reference_id),
        "language": language.value,
        "generation_id": str(generation_id),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return uuid5(_SPARSE_ROW_NAMESPACE, digest)
