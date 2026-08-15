"""Fusion-aware cross-encoder reranking contract."""

from typing import Protocol, runtime_checkable

from mnemo.models import RetrievalFusionResult, RetrievalRerankResult

from .types import FusionRerankerCapabilities


@runtime_checkable
class FusionRerankingInterfaceV1(Protocol):  # pragma: no cover
    """Rerank one complete ADR-0041 result without flattening provenance."""

    def capabilities(self) -> FusionRerankerCapabilities:
        """Return immutable fusion-reranker capability metadata."""
        ...

    async def rerank_fused(
        self,
        query: str,
        fusion_result: RetrievalFusionResult,
    ) -> RetrievalRerankResult:
        """Return the same bounded candidates in deterministic reranked order."""
        ...


FusionRerankingInterface = FusionRerankingInterfaceV1
