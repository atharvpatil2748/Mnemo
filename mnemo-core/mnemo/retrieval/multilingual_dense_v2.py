"""Bounded authorization-first exact-cosine retrieval for the isolated BGE-M3 space."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
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
MAX_PAGED_MULTILINGUAL_V2_VECTORS = 200_000
MULTILINGUAL_V2_PAGE_SIZE = 2_000
DenseRetrievalStageObserverV2 = Callable[
    [UUID, str, str, float | None, int | None, int | None, str | None], None
]


@runtime_checkable
class AuthorizedMultilingualSourceEnumeratorV2(Protocol):  # pragma: no cover
    async def enumerate_authorized_multilingual_sources(
        self,
        *,
        decision: V2RetrievalAuthorizationDecisionV1,
        limit: int,
    ) -> tuple[LanguageEvidenceReferenceV3, ...]: ...


@runtime_checkable
class PagedAuthorizedMultilingualSourceEnumeratorV2(Protocol):  # pragma: no cover
    async def enumerate_authorized_multilingual_sources_page(
        self,
        *,
        decision: V2RetrievalAuthorizationDecisionV1,
        offset: int,
        limit: int,
    ) -> tuple[LanguageEvidenceReferenceV3, ...]: ...


class RequestScopedAuthorizedSourcePagesV2:
    """Reuse validated source identities only within one authorization decision.

    Retain at most eight pages. Large searches fall back to re-reading evicted
    pages rather than creating a process-wide or unbounded authorization cache.
    """

    def __init__(
        self,
        *,
        enumerator: AuthorizedMultilingualSourceEnumeratorV2,
        decision: V2RetrievalAuthorizationDecisionV1,
    ) -> None:
        self.enumerator = enumerator
        self._fingerprint = decision.decision_fingerprint
        self._pages: dict[tuple[int, int], tuple[LanguageEvidenceReferenceV3, ...]] = {}

    async def page(
        self, *, decision: V2RetrievalAuthorizationDecisionV1, offset: int, limit: int
    ) -> tuple[LanguageEvidenceReferenceV3, ...]:
        if decision.decision_fingerprint != self._fingerprint:
            raise PermissionError("authorized source census belongs to another decision")
        if not isinstance(self.enumerator, PagedAuthorizedMultilingualSourceEnumeratorV2):
            raise TypeError("authorized source enumerator is not paged")
        key = (offset, limit)
        cached = self._pages.get(key)
        if cached is not None:
            return cached
        values = await self.enumerator.enumerate_authorized_multilingual_sources_page(
            decision=decision, offset=offset, limit=limit
        )
        if any(value.notebook_id != decision.retrieval_scope.notebook_id for value in values):
            raise PermissionError("authorized source census crossed notebook scope")
        if len({value.identity_digest for value in values}) != len(values):
            raise ValueError("authorized source census contains duplicate identities")
        if len(self._pages) == 8:
            self._pages.pop(next(iter(self._pages)))
        self._pages[key] = values
        return values

    async def all(
        self, *, decision: V2RetrievalAuthorizationDecisionV1, limit: int
    ) -> tuple[LanguageEvidenceReferenceV3, ...]:
        if decision.decision_fingerprint != self._fingerprint:
            raise PermissionError("authorized source census belongs to another decision")
        return await self.enumerator.enumerate_authorized_multilingual_sources(
            decision=decision, limit=limit
        )


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
        stage_observer: DenseRetrievalStageObserverV2 | None = None,
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
        self._stage_observer = stage_observer

    @property
    def source_enumerator(self) -> AuthorizedMultilingualSourceEnumeratorV2:
        return self._source_enumerator

    async def retrieve(
        self,
        *,
        decision: V2RetrievalAuthorizationDecisionV1,
        query: str,
        query_language: LanguageCode,
        limit: int,
        source_pages: RequestScopedAuthorizedSourcePagesV2 | None = None,
    ) -> tuple[MultilingualDenseMatchV2, ...]:
        if not 1 <= limit <= MAX_RETURNED_MULTILINGUAL_V2_CANDIDATES:
            raise ValueError("dense result limit is outside governed bounds")
        if source_pages is not None and source_pages.enumerator is not self._source_enumerator:
            raise PermissionError("authorized source census belongs to another enumerator")
        seen_sources: set[str] = set()
        paged_enumerator = (
            self._source_enumerator
            if isinstance(self._source_enumerator, PagedAuthorizedMultilingualSourceEnumeratorV2)
            else None
        )
        offsets: range | tuple[int, ...] = (
            range(0, MAX_PAGED_MULTILINGUAL_V2_VECTORS + 1, MULTILINGUAL_V2_PAGE_SIZE)
            if paged_enumerator is not None
            else (0,)
        )
        first_authorized = (
            await (
                source_pages.page(decision=decision, offset=0, limit=MULTILINGUAL_V2_PAGE_SIZE)
                if source_pages is not None
                else paged_enumerator.enumerate_authorized_multilingual_sources_page(
                    decision=decision, offset=0, limit=MULTILINGUAL_V2_PAGE_SIZE
                )
            )
            if paged_enumerator is not None
            else await (
                source_pages.all(decision=decision, limit=MAX_ELIGIBLE_MULTILINGUAL_V2_VECTORS + 1)
                if source_pages is not None
                else self._source_enumerator.enumerate_authorized_multilingual_sources(
                    decision=decision, limit=MAX_ELIGIBLE_MULTILINGUAL_V2_VECTORS + 1
                )
            )
        )
        if (
            paged_enumerator is None
            and len(first_authorized) > MAX_ELIGIBLE_MULTILINGUAL_V2_VECTORS
        ):
            raise ValueError("authorized multilingual vector universe exceeds 10000")
        if any(
            source.notebook_id != decision.retrieval_scope.notebook_id
            for source in first_authorized
        ):
            raise PermissionError("authorized source enumerator crossed notebook scope")
        query_embedding = await self._query_embedder.embed_query(
            query=query, language=query_language.value
        )
        if query_embedding.profile.vector_space != self._vector_space:
            raise ValueError("query embedding belongs to a different vector space")
        scored: list[tuple[float, MultilingualEmbeddingV3]] = []
        for offset in offsets:
            if offset == 0 or paged_enumerator is None:
                authorized = first_authorized
            else:
                authorized = await (
                    source_pages.page(
                        decision=decision, offset=offset, limit=MULTILINGUAL_V2_PAGE_SIZE
                    )
                    if source_pages is not None
                    else paged_enumerator.enumerate_authorized_multilingual_sources_page(
                        decision=decision, offset=offset, limit=MULTILINGUAL_V2_PAGE_SIZE
                    )
                )
            if (
                paged_enumerator is not None
                and offset == MAX_PAGED_MULTILINGUAL_V2_VECTORS
                and authorized
            ):
                raise ValueError("authorized multilingual vector universe exceeds 200000")
            if paged_enumerator is None and len(authorized) > MAX_ELIGIBLE_MULTILINGUAL_V2_VECTORS:
                raise ValueError("authorized multilingual vector universe exceeds 10000")
            if any(
                source.notebook_id != decision.retrieval_scope.notebook_id for source in authorized
            ):
                raise PermissionError("authorized source enumerator crossed notebook scope")
            if not authorized:
                break
            page_count = len(authorized)
            if any(source.identity_digest in seen_sources for source in authorized):
                raise ValueError("authorized V2 source pages overlap")
            seen_sources.update(source.identity_digest for source in authorized)
            embeddings = await self._store.list_authorized_multilingual_embeddings_v3(
                notebook_id=decision.retrieval_scope.notebook_id,
                generation_id=self._generation_id,
                vector_space=self._vector_space,
                authorized_sources=authorized,
            )
            authorized_digests = {item.identity_digest for item in authorized}
            if any(item.source.identity_digest not in authorized_digests for item in embeddings):
                raise PermissionError("embedding store returned unauthorized evidence")
            observer = self._stage_observer
            if observer is not None:
                scoring_started = time.perf_counter()
                observer(
                    decision.retrieval_scope.notebook_id,
                    "dense_cosine_scoring",
                    "started",
                    None,
                    len(embeddings),
                    None,
                    None,
                )
            try:
                page_scores = tuple(
                    (_cosine(query_embedding.vector, item.vector), item) for item in embeddings
                )
            except BaseException as error:
                if observer is not None:
                    observer(
                        decision.retrieval_scope.notebook_id,
                        "dense_cosine_scoring",
                        "failed",
                        time.perf_counter() - scoring_started,
                        len(embeddings),
                        None,
                        type(error).__name__,
                    )
                raise
            if observer is not None:
                observer(
                    decision.retrieval_scope.notebook_id,
                    "dense_cosine_scoring",
                    "completed",
                    time.perf_counter() - scoring_started,
                    len(embeddings),
                    len(page_scores),
                    None,
                )
                merge_started = time.perf_counter()
                observer(
                    decision.retrieval_scope.notebook_id,
                    "dense_candidate_merge_sort",
                    "started",
                    None,
                    len(scored) + len(page_scores),
                    None,
                    None,
                )
            scored.extend(page_scores)
            scored = sorted(
                scored,
                key=lambda value: (-value[0], str(value[1].embedding_id)),
            )[:limit]
            if observer is not None:
                observer(
                    decision.retrieval_scope.notebook_id,
                    "dense_candidate_merge_sort",
                    "completed",
                    time.perf_counter() - merge_started,
                    len(embeddings),
                    len(scored),
                    None,
                )
            if paged_enumerator is None or page_count < MULTILINGUAL_V2_PAGE_SIZE:
                break
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
