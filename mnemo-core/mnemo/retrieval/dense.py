"""Storage-backed dense retrieval for Phase 6 Module 6.2."""

from __future__ import annotations

import math

from mnemo.interfaces import (
    EmbeddingVector,
    IntegrityError,
    RetrieverCapabilities,
    StorageInterfaceV1,
    UnsupportedError,
)
from mnemo.models import MetadataFilter, ScoredChunk


class DenseRetriever:
    """Execute one dense search through the configured storage facade."""

    def __init__(self, storage: StorageInterfaceV1) -> None:
        """Bind a storage facade that advertises dense-search support."""
        if not isinstance(storage, StorageInterfaceV1):
            raise TypeError("storage must implement StorageInterfaceV1")
        if not storage.capabilities().supports_dense_search:
            raise UnsupportedError("storage must support dense search")
        self._storage = storage

    @property
    def retrieval_mode(self) -> str:
        """Return the stable built-in registry slot and score source."""
        return "dense"

    def capabilities(self) -> RetrieverCapabilities:
        """Describe the behavior implemented by this retrieval strategy."""
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
        """Return raw-scored dense matches without embedding or reranking."""
        _validate_query(query)
        embedding = _validate_embedding(query_embedding)
        if not isinstance(filters, MetadataFilter):
            raise TypeError("filters must be MetadataFilter")
        _validate_top_k(top_k)

        results = await self._storage.search_dense(embedding, filters, top_k)
        if not isinstance(results, tuple):
            raise IntegrityError("dense storage returned a non-tuple result")
        if len(results) > top_k:
            raise IntegrityError("dense storage returned more than top_k results")
        if any(not isinstance(result, ScoredChunk) for result in results):
            raise IntegrityError("dense storage returned an invalid result")
        identities = tuple(result.chunk.id for result in results)
        if len(set(identities)) != len(identities):
            raise IntegrityError("dense storage returned duplicate chunk identities")

        return tuple(
            ScoredChunk(
                chunk=result.chunk,
                score=result.score,
                source=self.retrieval_mode,
                rank=index,
            )
            for index, result in enumerate(results, start=1)
        )


def _validate_query(query: str) -> None:
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    if not query.strip():
        raise ValueError("query must not be empty")


def _validate_embedding(embedding: EmbeddingVector | None) -> EmbeddingVector:
    if embedding is None:
        raise ValueError("query_embedding is required for dense retrieval")
    if not isinstance(embedding, tuple):
        raise TypeError("query_embedding must be a tuple")
    if not embedding:
        raise ValueError("query_embedding must not be empty")
    if any(
        isinstance(component, bool)
        or not isinstance(component, (int, float))
        or not math.isfinite(component)
        for component in embedding
    ):
        raise ValueError("query_embedding must contain only finite numbers")
    return embedding


def _validate_top_k(top_k: int) -> None:
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise TypeError("top_k must be an integer")
    if top_k < 1:
        raise ValueError("top_k must be positive")
