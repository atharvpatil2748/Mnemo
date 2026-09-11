"""Authorization-first sparse retrieval over the isolated multilingual V2 projection."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.models.advanced_retrieval import RetrievalPlanV2
from mnemo.models.multilingual import LanguageEvidenceReferenceV3
from mnemo.models.multilingual_index import MultilingualTextProjectionRowV2
from mnemo.models.v2_retrieval_authorization import V2RetrievalAuthorizationDecisionV1
from mnemo.retrieval.full_multilingual_v2 import MultilingualSparseMatchV2
from mnemo.retrieval.multilingual_dense_v2 import AuthorizedMultilingualSourceEnumeratorV2


@runtime_checkable
class MultilingualTextProjectionStoreV2(Protocol):  # pragma: no cover
    async def search_authorized_multilingual_text_v2(
        self,
        *,
        notebook_id: UUID,
        generation_id: UUID,
        query: str,
        authorized_sources: tuple[LanguageEvidenceReferenceV3, ...],
        page_start: int | None,
        page_end: int | None,
        section_indexes: tuple[int, ...],
        heading_prefix: tuple[str, ...],
        limit: int,
    ) -> tuple[tuple[MultilingualTextProjectionRowV2, float], ...]: ...


class AuthorizedMultilingualSparseRetrievalV2:
    """Enumerate authorized identities before any FTS match or rank operation."""

    def __init__(
        self,
        *,
        source_enumerator: AuthorizedMultilingualSourceEnumeratorV2,
        store: MultilingualTextProjectionStoreV2,
        generation_id: UUID,
    ) -> None:
        if not isinstance(source_enumerator, AuthorizedMultilingualSourceEnumeratorV2):
            raise TypeError("source enumerator does not implement V2 authorization contract")
        if not isinstance(store, MultilingualTextProjectionStoreV2):
            raise TypeError("store does not implement multilingual sparse V2 contract")
        self._source_enumerator = source_enumerator
        self._store = store
        self._generation_id = generation_id

    async def retrieve_authorized_multilingual_sparse(
        self,
        *,
        decision: V2RetrievalAuthorizationDecisionV1,
        plan: RetrievalPlanV2,
        limit: int,
    ) -> tuple[MultilingualSparseMatchV2, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("multilingual sparse result limit is outside governed bounds")
        authorized = await self._source_enumerator.enumerate_authorized_multilingual_sources(
            decision=decision,
            limit=10_001,
        )
        if len(authorized) > 10_000:
            raise ValueError("authorized multilingual sparse universe exceeds 10000")
        rows = await self._store.search_authorized_multilingual_text_v2(
            notebook_id=decision.retrieval_scope.notebook_id,
            generation_id=self._generation_id,
            query=plan.query,
            authorized_sources=authorized,
            page_start=plan.position.page_start,
            page_end=plan.position.page_end,
            section_indexes=plan.position.section_indexes,
            heading_prefix=plan.position.heading_prefix,
            limit=limit,
        )
        authorized_digests = {item.identity_digest for item in authorized}
        if any(row.source.identity_digest not in authorized_digests for row, _ in rows):
            raise PermissionError("multilingual sparse store returned unauthorized evidence")
        return tuple(
            MultilingualSparseMatchV2(source=row.source, score=score, rank=index)
            for index, (row, score) in enumerate(rows, 1)
        )
