"""Cache wrapper for embedding providers."""

import hashlib

from mnemo.interfaces.cache import CacheInterfaceV1
from mnemo.interfaces.embedding import EmbeddingProviderV1
from mnemo.interfaces.errors import IntegrityError
from mnemo.interfaces.types import (
    EmbeddingBatch,
    EmbeddingCapabilities,
    EmbeddingVector,
    HealthStatus,
)


class CachedEmbeddingProvider(EmbeddingProviderV1):
    """Wrapper that intercepts embedding requests to leverage a local cache."""

    def __init__(
        self,
        provider: EmbeddingProviderV1,
        cache: CacheInterfaceV1[str, tuple[float, ...]],
    ) -> None:
        """Create a caching wrapper around an existing provider."""
        self._provider = provider
        self._cache = cache

    @property
    def model_name(self) -> str:
        """Return the underlying provider's model name."""
        return self._provider.model_name

    @property
    def dimensions(self) -> int:
        """Return the underlying provider's fixed vector dimension."""
        return self._provider.dimensions

    @property
    def max_tokens(self) -> int:
        """Return the underlying provider's maximum tokens."""
        return self._provider.max_tokens

    def capabilities(self) -> EmbeddingCapabilities:
        """Return the underlying provider's capabilities."""
        return self._provider.capabilities()

    async def health_check(self) -> HealthStatus:
        """Return the underlying provider's health status."""
        return await self._provider.health_check()

    def _compute_key(self, text: str) -> str:
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{text_hash}::{self.model_name}"

    def _validate_dimensions(self, vector: tuple[float, ...]) -> None:
        if len(vector) != self.dimensions:
            raise IntegrityError(
                f"Dimension mismatch: expected {self.dimensions}, got {len(vector)}"
            )

    async def embed(self, text: str) -> EmbeddingVector:
        """Embed one non-empty text value, checking cache first."""
        if not text:
            raise ValueError("text cannot be empty")

        key = self._compute_key(text)
        cached = await self._cache.get(key)
        if cached is not None:
            self._validate_dimensions(cached)
            return cached

        vector = await self._provider.embed(text)
        self._validate_dimensions(vector)
        await self._cache.put(key, vector)
        return vector

    async def embed_batch(self, texts: tuple[str, ...]) -> EmbeddingBatch:
        """Embed a non-empty ordered text batch, using cache where possible."""
        if not texts:
            raise ValueError("texts cannot be empty")

        keys = [self._compute_key(text) for text in texts]
        results: list[EmbeddingVector | None] = [None] * len(texts)
        miss_indices: list[int] = []
        miss_texts: list[str] = []

        # Check cache
        for i, key in enumerate(keys):
            cached = await self._cache.get(key)
            if cached is not None:
                self._validate_dimensions(cached)
                results[i] = cached
            else:
                miss_indices.append(i)
                miss_texts.append(texts[i])

        # Process misses
        if miss_texts:
            miss_vectors = await self._provider.embed_batch(tuple(miss_texts))
            for i, vector in zip(miss_indices, miss_vectors.vectors, strict=True):
                self._validate_dimensions(vector)
                await self._cache.put(keys[i], vector)
                results[i] = vector

        # Satisfy type checker that no Nones remain
        final_vectors = tuple(r for r in results if r is not None)
        return EmbeddingBatch(
            vectors=final_vectors,
            model_name=self.model_name,
            dimensions=self.dimensions,
        )
