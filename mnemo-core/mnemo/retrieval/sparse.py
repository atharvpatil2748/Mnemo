"""Storage-backed sparse retrieval for Phase 6 Module 6.3."""

from __future__ import annotations

from mnemo.interfaces import (
    EmbeddingVector,
    IntegrityError,
    RetrieverCapabilities,
    StorageInterfaceV1,
    UnsupportedError,
)
from mnemo.models import MetadataFilter, ScoredChunk


class SparseRetriever:
    """Execute one sparse search through the configured storage facade."""

    def __init__(self, storage: StorageInterfaceV1) -> None:
        if not isinstance(storage, StorageInterfaceV1):
            raise TypeError("storage must implement StorageInterfaceV1")
        if not storage.capabilities().supports_sparse_search:
            raise UnsupportedError("storage must support sparse search")
        self._storage = storage

    @property
    def retrieval_mode(self) -> str:
        return "sparse"

    def capabilities(self) -> RetrieverCapabilities:
        return RetrieverCapabilities(
            supports_hybrid=False,
            supports_metadata_filters=True,
            supports_parent_child=False,
            supports_reranking=False,
        )

    async def retrieve(
        self,
        query: str,
        query_embedding: EmbeddingVector | None,
        filters: MetadataFilter,
        top_k: int,
    ) -> tuple[ScoredChunk, ...]:
        del query_embedding
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        if not query.strip():
            raise ValueError("query must not be empty")
        if not isinstance(filters, MetadataFilter):
            raise TypeError("filters must be MetadataFilter")
        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise TypeError("top_k must be an integer")
        if top_k < 1:
            raise ValueError("top_k must be positive")

        results = await self._storage.search_sparse(query, filters, top_k)
        if not isinstance(results, tuple):
            raise IntegrityError("sparse storage returned a non-tuple result")
        if len(results) > top_k:
            raise IntegrityError("sparse storage returned more than top_k results")
        if any(not isinstance(result, ScoredChunk) for result in results):
            raise IntegrityError("sparse storage returned an invalid result")
        identities = tuple(result.chunk.id for result in results)
        if len(set(identities)) != len(identities):
            raise IntegrityError("sparse storage returned duplicate chunk identities")
        return tuple(
            ScoredChunk(
                chunk=result.chunk,
                score=result.score,
                source=self.retrieval_mode,
                rank=index,
            )
            for index, result in enumerate(results, start=1)
        )
