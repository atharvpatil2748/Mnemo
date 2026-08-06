"""Candidate reranking contract."""

from typing import Protocol, runtime_checkable

from mnemo.models import ScoredChunk

from .types import RerankerCapabilities


@runtime_checkable
class RerankerInterfaceV1(Protocol):  # pragma: no cover
    """Reorder retrieval candidates without losing chunk provenance."""

    def capabilities(self) -> RerankerCapabilities:
        """Return immutable descriptive reranker capabilities."""
        ...

    async def rerank(
        self,
        query: str,
        candidates: tuple[ScoredChunk, ...],
        top_k: int,
    ) -> tuple[ScoredChunk, ...]:
        """Return at most top_k candidates in descending reranker order."""
        ...


RerankerInterface = RerankerInterfaceV1
