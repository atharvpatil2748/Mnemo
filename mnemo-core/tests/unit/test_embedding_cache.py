"""Unit tests for the Module 5.2 Embedding Cache."""

from datetime import UTC, datetime
from pathlib import Path

import aiosqlite
import pytest
from mnemo.embeddings.cached import CachedEmbeddingProvider
from mnemo.interfaces.embedding import EmbeddingProviderV1
from mnemo.interfaces.errors import IntegrityError
from mnemo.interfaces.types import (
    EmbeddingBatch,
    EmbeddingCapabilities,
    EmbeddingVector,
    HealthStatus,
)
from mnemo.storage.cache import SQLiteEmbeddingCache


class MockEmbeddingProvider(EmbeddingProviderV1):
    def __init__(self, dimensions: int) -> None:
        self._dimensions = dimensions
        self.call_count = 0
        self.batch_call_count = 0

    @property
    def model_name(self) -> str:
        return "mock-model"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def max_tokens(self) -> int:
        return 512

    def capabilities(self) -> EmbeddingCapabilities:
        return EmbeddingCapabilities(
            dimensions=self.dimensions,
            supports_batch=True,
            max_batch=10,
            multilingual=True,
            supports_normalization=False,
        )

    async def health_check(self) -> HealthStatus:
        return HealthStatus(
            healthy=True, component="mock", checked_at=datetime.now(UTC)
        )

    async def embed(self, text: str) -> EmbeddingVector:
        self.call_count += 1
        # Create deterministic vector based on text length
        val = float(len(text))
        return tuple(val for _ in range(self.dimensions))

    async def embed_batch(self, texts: tuple[str, ...]) -> EmbeddingBatch:
        self.batch_call_count += 1
        results = []
        for text in texts:
            results.append(await self.embed(text))
        return EmbeddingBatch(
            vectors=tuple(results),
            model_name=self.model_name,
            dimensions=self.dimensions,
        )


@pytest.fixture
async def sqlite_cache(tmp_path: Path) -> SQLiteEmbeddingCache:
    db_path = tmp_path / "test_cache.db"
    cache = SQLiteEmbeddingCache(db_path)
    await cache.initialize()
    return cache


@pytest.mark.anyio
async def test_sqlite_cache_lifecycle(sqlite_cache: SQLiteEmbeddingCache) -> None:
    key = "test::model"
    vec = (1.0, 2.0, 3.0)

    assert await sqlite_cache.get(key) is None

    await sqlite_cache.put(key, vec)
    cached = await sqlite_cache.get(key)
    assert cached == vec

    assert await sqlite_cache.delete(key) is True
    assert await sqlite_cache.get(key) is None
    assert await sqlite_cache.delete(key) is False


@pytest.mark.anyio
async def test_sqlite_cache_ttl(sqlite_cache: SQLiteEmbeddingCache) -> None:
    # TTL tests are tricky without mocking time, but we can test -1 ttl to immediately expire
    await sqlite_cache.put("key", (1.0, 2.0), ttl_seconds=-1)
    assert await sqlite_cache.get("key") is None


@pytest.mark.anyio
async def test_sqlite_cache_namespace(sqlite_cache: SQLiteEmbeddingCache) -> None:
    await sqlite_cache.put("ns1::a", (1.0,))
    await sqlite_cache.put("ns1::b", (2.0,))
    await sqlite_cache.put("ns2::a", (3.0,))

    await sqlite_cache.clear_namespace("ns1::")

    assert await sqlite_cache.get("ns1::a") is None
    assert await sqlite_cache.get("ns1::b") is None
    assert await sqlite_cache.get("ns2::a") == (3.0,)


@pytest.mark.anyio
async def test_sqlite_cache_corrupted_blob(sqlite_cache: SQLiteEmbeddingCache) -> None:
    await sqlite_cache.put("key", (1.0, 2.0))
    # Mutate underlying DB to corrupt the blob length
    async with aiosqlite.connect(sqlite_cache._path) as db:
        await db.execute("UPDATE embedding_cache SET vector = ? WHERE key = ?", (b"bad", "key"))
        await db.commit()
    
    with pytest.raises(IntegrityError, match="Corrupted cache blob"):
        await sqlite_cache.get("key")


@pytest.mark.anyio
async def test_cached_provider_embed(sqlite_cache: SQLiteEmbeddingCache) -> None:
    provider = MockEmbeddingProvider(dimensions=3)
    wrapper = CachedEmbeddingProvider(provider, sqlite_cache)

    assert wrapper.model_name == "mock-model"
    assert wrapper.dimensions == 3

    # Miss
    vec1 = await wrapper.embed("hello")
    assert provider.call_count == 1
    assert vec1 == (5.0, 5.0, 5.0)

    # Hit
    vec2 = await wrapper.embed("hello")
    assert provider.call_count == 1
    assert vec2 == vec1


@pytest.mark.anyio
async def test_cached_provider_embed_batch(sqlite_cache: SQLiteEmbeddingCache) -> None:
    provider = MockEmbeddingProvider(dimensions=2)
    wrapper = CachedEmbeddingProvider(provider, sqlite_cache)

    # Miss all
    res1 = await wrapper.embed_batch(("a", "bb"))
    assert provider.batch_call_count == 1
    assert res1.vectors == ((1.0, 1.0), (2.0, 2.0))

    # Hit all
    res2 = await wrapper.embed_batch(("a", "bb"))
    assert provider.batch_call_count == 1
    assert res2.vectors == res1.vectors

    # Partial hit
    res3 = await wrapper.embed_batch(("a", "ccc", "bb"))
    assert provider.batch_call_count == 2
    assert res3.vectors == ((1.0, 1.0), (3.0, 3.0), (2.0, 2.0))
    # We should have missed only "ccc"
    # Actually the mock provider embed_batch calls embed for each missed text
    # so call_count should have incremented by 1 (since "a" and "bb" were skipped).
    assert provider.call_count == 2 + 1  # 2 initially, 1 more for "ccc"


@pytest.mark.anyio
async def test_cached_provider_dimension_mismatch(sqlite_cache: SQLiteEmbeddingCache) -> None:
    provider = MockEmbeddingProvider(dimensions=2)
    wrapper = CachedEmbeddingProvider(provider, sqlite_cache)

    # Insert a 3D vector manually matching the key
    key = wrapper._compute_key("hello")
    await sqlite_cache.put(key, (1.0, 2.0, 3.0))

    with pytest.raises(IntegrityError, match="Dimension mismatch"):
        await wrapper.embed("hello")

    with pytest.raises(IntegrityError, match="Dimension mismatch"):
        await wrapper.embed_batch(("hello",))

@pytest.mark.anyio
async def test_cached_provider_bad_underlying_dimension(sqlite_cache: SQLiteEmbeddingCache) -> None:
    # If the provider itself returns wrong dimensions
    class BadProvider(MockEmbeddingProvider):
        async def embed(self, text: str) -> EmbeddingVector:
            return (1.0,) # Only 1D, but claims 2D

    bad_provider = BadProvider(dimensions=2)
    wrapper = CachedEmbeddingProvider(bad_provider, sqlite_cache)
    
    with pytest.raises(IntegrityError, match="Dimension mismatch"):
        await wrapper.embed("hello")

@pytest.mark.anyio
async def test_cached_provider_duplicate_batch_inputs(sqlite_cache: SQLiteEmbeddingCache) -> None:
    provider = MockEmbeddingProvider(dimensions=2)
    wrapper = CachedEmbeddingProvider(provider, sqlite_cache)

    res = await wrapper.embed_batch(("hello", "hello", "planet", "hello"))
    assert provider.batch_call_count == 1
    assert len(res.vectors) == 4
    assert res.vectors[0] == res.vectors[1]
    assert res.vectors[0] == res.vectors[3]
    assert res.vectors[2] != res.vectors[0]

@pytest.mark.anyio
async def test_sqlite_cache_concurrency(sqlite_cache: SQLiteEmbeddingCache) -> None:
    import anyio
    
    async def write_cache(idx: int) -> None:
        await sqlite_cache.put(f"key_{idx}", (float(idx),))

    # Spawn 50 concurrent writes
    async with anyio.create_task_group() as tg:
        for i in range(50):
            tg.start_soon(write_cache, i)
            
    # Verify all were written safely without locking each other
    for i in range(50):
        val = await sqlite_cache.get(f"key_{i}")
        assert val == (float(i),)
