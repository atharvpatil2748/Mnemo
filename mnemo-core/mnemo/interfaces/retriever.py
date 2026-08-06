"""Retrieval strategy contract."""

from typing import Protocol, runtime_checkable

from mnemo.models import MetadataFilter, ScoredChunk

from .types import EmbeddingVector, RetrieverCapabilities


@runtime_checkable
class RetrieverInterface(Protocol):  # pragma: no cover
    """Retrieve bounded raw-scored chunks through one search strategy."""

    @property
    def retrieval_mode(self) -> str:
        """Return the stable retrieval strategy identifier."""
        ...

    def capabilities(self) -> RetrieverCapabilities:
        """Return immutable descriptive retriever capabilities."""
        ...

    async def retrieve(
        self,
        query: str,
        query_embedding: EmbeddingVector | None,
        filters: MetadataFilter,
        top_k: int,
    ) -> tuple[ScoredChunk, ...]:
        """Return at most top_k unique chunks in descending score order."""
        ...
