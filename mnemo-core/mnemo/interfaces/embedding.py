"""Embedding-provider contract."""

from typing import Protocol, runtime_checkable

from .types import (
    EmbeddingBatch,
    EmbeddingCapabilities,
    EmbeddingVector,
    HealthStatus,
)


@runtime_checkable
class EmbeddingProviderV1(Protocol):  # pragma: no cover
    """Generate vectors through one configured embedding model provider."""

    @property
    def model_name(self) -> str:
        """Return the stable provider and model identifier."""
        ...

    @property
    def dimensions(self) -> int:
        """Return the fixed vector dimension."""
        ...

    @property
    def max_tokens(self) -> int:
        """Return the maximum tokens accepted for one input."""
        ...

    def capabilities(self) -> EmbeddingCapabilities:
        """Return immutable descriptive provider capabilities."""
        ...

    async def embed(self, text: str) -> EmbeddingVector:
        """Embed one non-empty text value."""
        ...

    async def embed_batch(self, texts: tuple[str, ...]) -> EmbeddingBatch:
        """Embed a non-empty ordered text batch while preserving order."""
        ...

    async def health_check(self) -> HealthStatus:
        """Return a transport-independent provider health observation."""
        ...


EmbeddingProvider = EmbeddingProviderV1
