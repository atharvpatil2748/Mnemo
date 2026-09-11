"""Bounded authorization-first exact-cosine retrieval for the isolated BGE-M3 space."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.models.multilingual import (
    LanguageCode,
    LanguageEvidenceReferenceV3,
    MultilingualQueryEmbeddingV2,
)
from mnemo.models.multilingual_embeddings import MultilingualEmbeddingV3
from mnemo.models.v2_retrieval_authorization import V2RetrievalAuthorizationDecisionV1

MAX_ELIGIBLE_MULTILINGUAL_V2_VECTORS = 10_000
MAX_RETURNED_MULTILINGUAL_V2_CANDIDATES = 1_000


@runtime_checkable
class AuthorizedMultilingualSourceEnumeratorV2(Protocol):  # pragma: no cover
    async def enumerate_authorized_multilingual_sources(
        self,
        *,
        decision: V2RetrievalAuthorizationDecisionV1,
        limit: int,
    ) -> tuple[LanguageEvidenceReferenceV3, ...]: ...


@runtime_checkable
class MultilingualEmbeddingStoreV2(Protocol):  # pragma: no cover
    async def list_authorized_multilingual_embeddings_v3(
        self,
        *,
        notebook_id: UUID,
        generation_id: UUID,
        vector_space: str,
        authorized_sources: tuple[LanguageEvidenceReferenceV3, ...],
    ) -> tuple[MultilingualEmbeddingV3, ...]: ...


@runtime_checkable
class MultilingualQueryEmbedderV2(Protocol):  # pragma: no cover
    async def embed_query(self, *, query: str, language: str) -> MultilingualQueryEmbeddingV2: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualDenseMatchV2:
    embedding: MultilingualEmbeddingV3
    score: float
    rank: int

    def __post_init__(self) -> None:
        if not math.isfinite(self.score):
            raise ValueError("dense score must be finite")
        if self.rank < 1 or self.rank > MAX_RETURNED_MULTILINGUAL_V2_CANDIDATES:
            raise ValueError("dense rank exceeds governed bounds")


class AuthorizedMultilingualDenseRetrievalV2:
    """Apply authorization and scope before vector enumeration/scoring."""

    def __init__(
        self,
        *,
        source_enumerator: AuthorizedMultilingualSourceEnumeratorV2,
        store: MultilingualEmbeddingStoreV2,
        query_embedder: MultilingualQueryEmbedderV2,
        generation_id: UUID,
        vector_space: str,
    ) -> None:
        if not isinstance(source_enumerator, AuthorizedMultilingualSourceEnumeratorV2):
            raise TypeError("source enumerator does not implement V2 authorization contract")
        if not isinstance(store, MultilingualEmbeddingStoreV2):
            raise TypeError("store does not implement multilingual embedding V2 contract")
        if not isinstance(query_embedder, MultilingualQueryEmbedderV2):
            raise TypeError("query embedder does not implement multilingual V2 contract")
        if not vector_space.strip():
            raise ValueError("vector_space must be non-empty")
        self._source_enumerator = source_enumerator
        self._store = store
        self._query_embedder = query_embedder
        self._generation_id = generation_id
        self._vector_space = vector_space

    async def retrieve(
        self,
        *,
        decision: V2RetrievalAuthorizationDecisionV1,
        query: str,
        query_language: LanguageCode,
        limit: int,
    ) -> tuple[MultilingualDenseMatchV2, ...]:
        if not 1 <= limit <= MAX_RETURNED_MULTILINGUAL_V2_CANDIDATES:
            raise ValueError("dense result limit is outside governed bounds")
        authorized = await self._source_enumerator.enumerate_authorized_multilingual_sources(
            decision=decision,
            limit=MAX_ELIGIBLE_MULTILINGUAL_V2_VECTORS + 1,
        )
        if len(authorized) > MAX_ELIGIBLE_MULTILINGUAL_V2_VECTORS:
            raise ValueError("authorized multilingual vector universe exceeds 10000")
        if any(source.notebook_id != decision.retrieval_scope.notebook_id for source in authorized):
            raise PermissionError("authorized source enumerator crossed notebook scope")
        query_embedding = await self._query_embedder.embed_query(
            query=query, language=query_language.value
        )
        if query_embedding.profile.vector_space != self._vector_space:
            raise ValueError("query embedding belongs to a different vector space")
        embeddings = await self._store.list_authorized_multilingual_embeddings_v3(
            notebook_id=decision.retrieval_scope.notebook_id,
            generation_id=self._generation_id,
            vector_space=self._vector_space,
            authorized_sources=authorized,
        )
        authorized_digests = {item.identity_digest for item in authorized}
        if any(item.source.identity_digest not in authorized_digests for item in embeddings):
            raise PermissionError("embedding store returned unauthorized evidence")
        scored = sorted(
            ((_cosine(query_embedding.vector, item.vector), item) for item in embeddings),
            key=lambda value: (-value[0], str(value[1].embedding_id)),
        )[:limit]
        return tuple(
            MultilingualDenseMatchV2(embedding=item, score=score, rank=index)
            for index, (score, item) in enumerate(scored, 1)
        )


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("cannot compare incompatible multilingual vector dimensions")
    left_norm = math.sqrt(math.fsum(value * value for value in left))
    right_norm = math.sqrt(math.fsum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        raise ValueError("cannot compare zero-norm multilingual vector")
    return math.fsum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
