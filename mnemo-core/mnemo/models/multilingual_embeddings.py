"""Full Multilingual V2 embedding identities isolated from V1/CLIP vector spaces."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid5

from ._shared import require_non_empty, require_sha256, require_utc
from .multilingual import (
    LanguageCode,
    LanguageEvidenceReferenceV3,
    MultilingualEmbeddingProfile,
    multilingual_vector_hash,
)
from .text_representations import ObservationReferenceV1, TextRepresentationReferenceV1

_EMBEDDING_V3_NAMESPACE = UUID("e25aab89-8741-5e44-a513-324376d59264")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualEmbeddingInputV3:
    source: LanguageEvidenceReferenceV3
    representation: TextRepresentationReferenceV1
    text: str
    language: LanguageCode
    language_observation_references: tuple[ObservationReferenceV1, ...]
    script_observation_references: tuple[ObservationReferenceV1, ...]

    def __post_init__(self) -> None:
        require_non_empty(self.text, "text")
        if self.representation.evidence_reference != self.source:
            raise ValueError("embedding representation is bound to a different source")
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != (
            self.representation.content_hash
        ):
            raise ValueError("embedding input text conflicts with representation hash")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualEmbeddingV3:
    embedding_id: UUID
    source: LanguageEvidenceReferenceV3
    representation: TextRepresentationReferenceV1
    language: LanguageCode
    profile: MultilingualEmbeddingProfile
    vector: tuple[float, ...]
    vector_hash: str
    source_hash: str
    representation_hash: str
    language_observation_references: tuple[ObservationReferenceV1, ...]
    script_observation_references: tuple[ObservationReferenceV1, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        require_sha256(self.vector_hash, "vector_hash")
        require_sha256(self.source_hash, "source_hash")
        require_sha256(self.representation_hash, "representation_hash")
        require_utc(self.created_at, "created_at")
        if self.source_hash != self.source.source_content_hash:
            raise ValueError("embedding source hash mismatch")
        if self.representation_hash != self.representation.content_hash:
            raise ValueError("embedding representation hash mismatch")
        if self.representation.evidence_reference != self.source:
            raise ValueError("embedding source/representation identity mismatch")
        if len(self.vector) != self.profile.dimension:
            raise ValueError("embedding dimension differs from governed profile")
        if any(not math.isfinite(value) for value in self.vector):
            raise ValueError("embedding vector values must be finite")
        if multilingual_vector_hash(self.vector) != self.vector_hash:
            raise ValueError("embedding vector hash mismatch")
        if self.embedding_id != multilingual_embedding_v3_id(
            source=self.source,
            representation=self.representation,
            language=self.language,
            profile=self.profile,
        ):
            raise ValueError("multilingual embedding V3 identity mismatch")


def multilingual_embedding_v3_id(
    *,
    source: LanguageEvidenceReferenceV3,
    representation: TextRepresentationReferenceV1,
    language: LanguageCode,
    profile: MultilingualEmbeddingProfile,
) -> UUID:
    payload = {
        "source_reference_digest": source.identity_digest,
        "representation_reference_id": str(representation.reference_id),
        "representation_hash": representation.content_hash,
        "language": language.value,
        "provider": profile.provider,
        "model": profile.model,
        "revision": profile.revision,
        "generation_id": str(profile.generation_id),
        "vector_space": profile.vector_space,
        "preprocessing_digest": profile.preprocessing_digest,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return uuid5(_EMBEDDING_V3_NAMESPACE, digest)
