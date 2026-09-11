"""Provider-neutral Phase 8.5.6 advanced retrieval contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.interfaces.scope import PrincipalContextV1
from mnemo.models import Chunk
from mnemo.models.advanced_retrieval import (
    AdvancedRetrievalCandidate,
    EvidenceRepresentation,
    PositionalScopeV2,
    RetrievalPlanV2,
    RetrievalResultSetV1,
    RetrievalScopeV2,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class AdvancedSourcePage:
    representation: EvidenceRepresentation
    snapshot_identity: str
    candidates: tuple[AdvancedRetrievalCandidate, ...]
    examined: int
    next_offset: int | None
    exhausted: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class CanonicalEvidenceRecord:
    notebook_id: UUID
    source_id: UUID
    document_title: str | None
    title_match: bool
    chunk: Chunk


@dataclass(frozen=True, slots=True, kw_only=True)
class MultimodalEvidenceRecord:
    """One authorized occurrence-scoped record from a named representation."""

    notebook_id: UUID
    source_id: UUID
    document_id: UUID
    version_id: UUID
    occurrence_id: UUID
    asset_id: UUID
    derivation_id: UUID | None
    generation_id: UUID | None
    document_title: str | None
    content: str | None
    locator: dict[str, object]
    language: str | None
    source_rank: int
    source_score: float | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MultimodalEvidencePage:
    snapshot_identity: str
    records: tuple[MultimodalEvidenceRecord, ...]
    examined: int
    next_offset: int | None
    exhausted: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualEvidenceRecord:
    notebook_id: UUID
    source_id: UUID
    document_id: UUID
    version_id: UUID
    derivation_id: UUID
    source_evidence_id: str
    source_language: str
    target_language: str
    content: str
    source_rank: int
    source_score: float | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualEvidencePage:
    snapshot_identity: str
    records: tuple[MultilingualEvidenceRecord, ...]
    examined: int
    next_offset: int | None
    exhausted: bool


class VisualVectorMetric(StrEnum):
    COSINE = "cosine"
    DOT = "dot"


@dataclass(frozen=True, slots=True, kw_only=True)
class VisualQueryVector:
    profile_id: str
    shared_space_id: str
    dimensions: int
    metric: VisualVectorMetric
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.profile_id.strip() or not self.shared_space_id.strip():
            raise ValueError("visual query profile and shared space must be non-empty")
        if self.dimensions < 1 or len(self.values) != self.dimensions:
            raise ValueError("visual query vector dimensions do not match values")
        if not all(math.isfinite(value) for value in self.values):
            raise ValueError("visual query vector values must be finite")


@runtime_checkable
class VisualQueryEmbeddingProviderV1(Protocol):  # pragma: no cover
    """Optional initialized text encoder for a certified shared visual space."""

    @property
    def profile_id(self) -> str: ...

    async def ready(self) -> bool: ...

    async def embed_text(self, query: str) -> VisualQueryVector: ...


@runtime_checkable
class MultimodalAdvancedStoreV1(Protocol):  # pragma: no cover
    """Authorized readers over active WP-02 multimodal projections."""

    async def active_multimodal_generation_identity(
        self, representation: EvidenceRepresentation, *, profile_id: str | None = None
    ) -> str | None: ...

    async def retrieve_multimodal_evidence(
        self,
        *,
        representation: EvidenceRepresentation,
        scope: RetrievalScopeV2,
        position: PositionalScopeV2,
        query: str,
        ranked: bool,
        offset: int,
        limit: int,
        query_vector: VisualQueryVector | None = None,
    ) -> MultimodalEvidencePage: ...


@runtime_checkable
class MultilingualAdvancedStoreV1(Protocol):  # pragma: no cover
    async def active_multilingual_generation_identity(self) -> str | None: ...

    async def retrieve_multilingual_evidence(
        self,
        *,
        scope: RetrievalScopeV2,
        position: PositionalScopeV2,
        query: str,
        offset: int,
        limit: int,
    ) -> MultilingualEvidencePage: ...


@runtime_checkable
class AdvancedCanonicalStoreV1(Protocol):  # pragma: no cover
    async def advanced_canonical_snapshot(
        self, *, scope: RetrievalScopeV2, position: PositionalScopeV2, query: str
    ) -> str: ...

    async def enumerate_advanced_canonical(
        self,
        *,
        scope: RetrievalScopeV2,
        position: PositionalScopeV2,
        query: str,
        offset: int,
        limit: int,
    ) -> tuple[CanonicalEvidenceRecord, ...]: ...

    async def get_advanced_canonical_records(
        self,
        *,
        scope: RetrievalScopeV2,
        position: PositionalScopeV2,
        chunk_ids: tuple[str, ...],
    ) -> tuple[CanonicalEvidenceRecord, ...]: ...

    async def expand_advanced_canonical(
        self,
        *,
        scope: RetrievalScopeV2,
        seed_chunk_ids: tuple[str, ...],
        include_parents: bool,
        limit: int,
    ) -> tuple[CanonicalEvidenceRecord, ...]: ...


@runtime_checkable
class AdvancedRetrievalSourceV1(Protocol):  # pragma: no cover
    @property
    def representation(self) -> EvidenceRepresentation: ...

    async def retrieve(
        self,
        plan: RetrievalPlanV2,
        *,
        offset: int,
        limit: int,
    ) -> AdvancedSourcePage: ...

    async def expand(
        self,
        plan: RetrievalPlanV2,
        seeds: tuple[AdvancedRetrievalCandidate, ...],
        *,
        limit: int,
    ) -> tuple[AdvancedRetrievalCandidate, ...]: ...


@runtime_checkable
class PrincipalAwareAdvancedRetrievalSourceV2(Protocol):  # pragma: no cover
    """Additive server-principal entry point for governed V2 sources."""

    @property
    def representation(self) -> EvidenceRepresentation: ...

    async def retrieve_authorized(
        self,
        *,
        principal: PrincipalContextV1,
        plan: RetrievalPlanV2,
        offset: int,
        limit: int,
    ) -> AdvancedSourcePage: ...


@runtime_checkable
class AdvancedCandidateRerankerV1(Protocol):  # pragma: no cover
    async def rerank(
        self,
        query: str,
        candidates: tuple[AdvancedRetrievalCandidate, ...],
    ) -> tuple[AdvancedRetrievalCandidate, ...]: ...


@runtime_checkable
class AdvancedRetrievalInterfaceV1(Protocol):  # pragma: no cover
    async def execute(
        self,
        plan: RetrievalPlanV2,
        *,
        cursor: str | None = None,
    ) -> RetrievalResultSetV1: ...
    @property
    def profile_id(self) -> str: ...


@runtime_checkable
class PrincipalAwareAdvancedRetrievalInterfaceV2(Protocol):  # pragma: no cover
    async def execute_authorized(
        self,
        *,
        principal: PrincipalContextV1,
        plan: RetrievalPlanV2,
        cursor: str | None = None,
    ) -> RetrievalResultSetV1: ...


@runtime_checkable
class DocumentSetResolverV1(Protocol):  # pragma: no cover
    """Resolve an explicit, already-authorized document set for partitioning."""

    async def resolve_document_set(
        self, *, scope: RetrievalScopeV2, document_ids: tuple[UUID, ...]
    ) -> tuple[UUID, ...]: ...
