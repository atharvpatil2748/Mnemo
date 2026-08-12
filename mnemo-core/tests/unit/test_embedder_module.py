"""Unit tests for the EmbedderModule."""

import uuid
from datetime import UTC, datetime

import anyio
import pytest
from mnemo.embeddings.embedder import EmbedderModule
from mnemo.interfaces.embedding import EmbeddingProviderV1
from mnemo.interfaces.types import (
    EmbeddingBatch,
    EmbeddingCapabilities,
    EmbeddingVector,
    HealthStatus,
)
from mnemo.models import FrozenMetadata
from mnemo.models.chunks import BlockSpan, Chunk, ChunkPosition, ChunkType


class MockBatchLimitingProvider(EmbeddingProviderV1):
    def __init__(self, dimensions: int, max_batch: int, delay: float = 0.01) -> None:
        self._dimensions = dimensions
        self._max_batch = max_batch
        self._delay = delay
        self.embed_batch_call_count = 0

    @property
    def model_name(self) -> str:
        return "mock-batch-model"

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
            max_batch=self._max_batch,
            multilingual=True,
            supports_normalization=False,
        )

    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=True, component="mock", checked_at=datetime.now(UTC))

    async def embed(self, text: str) -> EmbeddingVector:
        return (float(len(text)),) * self._dimensions

    async def embed_batch(self, texts: tuple[str, ...]) -> EmbeddingBatch:
        self.embed_batch_call_count += 1
        if len(texts) > self._max_batch:
            raise ValueError(f"Batch too large: {len(texts)} > {self._max_batch}")
        
        await anyio.sleep(self._delay)
        
        vectors = []
        for text in texts:
            vectors.append((float(len(text)),) * self._dimensions)
            
        return EmbeddingBatch(
            vectors=tuple(vectors),
            model_name=self.model_name,
            dimensions=self.dimensions,
        )


def _make_chunk(text: str, id_str: str, has_embedding: bool = False) -> Chunk:
    embedding = (1.0, 2.0) if has_embedding else None
    return Chunk(
        id=id_str,
        text=text,
        document_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0),
        source_span=BlockSpan(start_ordinal=0, end_ordinal=1),
        heading_path=("Header",),
        metadata=FrozenMetadata(),
        embedding=embedding,
    )


@pytest.mark.anyio
async def test_embedder_module_basic() -> None:
    provider = MockBatchLimitingProvider(dimensions=2, max_batch=2, delay=0.0)
    embedder = EmbedderModule(provider=provider, max_concurrency=2)
    
    # 5 chunks, max_batch=2 -> should result in 3 batches (2, 2, 1)
    chunks = [
        _make_chunk("a", "1" * 64),
        _make_chunk("bb", "2" * 64),
        _make_chunk("ccc", "3" * 64),
        _make_chunk("dddd", "4" * 64),
        _make_chunk("e", "5" * 64),
    ]
    
    results = await embedder.embed_chunks(chunks)
    assert len(results) == 5
    assert provider.embed_batch_call_count == 3
    
    # Check that embeddings are correct based on length
    assert results[0].embedding == (1.0, 1.0)
    assert results[1].embedding == (2.0, 2.0)
    assert results[2].embedding == (3.0, 3.0)
    assert results[3].embedding == (4.0, 4.0)
    assert results[4].embedding == (1.0, 1.0)


@pytest.mark.anyio
async def test_embedder_module_skips_existing() -> None:
    provider = MockBatchLimitingProvider(dimensions=2, max_batch=10, delay=0.0)
    embedder = EmbedderModule(provider=provider, max_concurrency=2)
    
    chunks = [
        _make_chunk("a", "1" * 64, has_embedding=True),
        _make_chunk("bb", "2" * 64, has_embedding=False),
        _make_chunk("ccc", "3" * 64, has_embedding=True),
    ]
    
    results = await embedder.embed_chunks(chunks)
    assert len(results) == 3
    
    # Only 1 chunk needs embedding, so 1 batch
    assert provider.embed_batch_call_count == 1
    
    # Pre-existing embeddings remain
    assert results[0].embedding == (1.0, 2.0)
    assert results[2].embedding == (1.0, 2.0)
    
    # Missing embedding was populated
    assert results[1].embedding == (2.0, 2.0)
    
    # Same IDs
    assert results[0].id == "1" * 64
    assert results[1].id == "2" * 64
    assert results[2].id == "3" * 64


@pytest.mark.anyio
async def test_embedder_module_concurrency() -> None:
    # 10 max_batch, 50 items -> 5 batches
    # Delay is 0.1s. With max_concurrency=5, it should take ~0.1s
    # If concurrency was 1, it would take ~0.5s
    provider = MockBatchLimitingProvider(dimensions=2, max_batch=10, delay=0.1)
    embedder = EmbedderModule(provider=provider, max_concurrency=5)
    
    chunks = [_make_chunk("a", "1" * 64) for _ in range(50)]
    
    start = anyio.current_time()
    results = await embedder.embed_chunks(chunks)
    end = anyio.current_time()
    
    assert len(results) == 50
    assert provider.embed_batch_call_count == 5
    
    # Should be well under 0.5s if concurrent
    assert end - start < 0.4


@pytest.mark.anyio
async def test_embedder_module_empty() -> None:
    provider = MockBatchLimitingProvider(dimensions=2, max_batch=10, delay=0.0)
    embedder = EmbedderModule(provider=provider, max_concurrency=5)
    
    results = await embedder.embed_chunks([])
    assert len(results) == 0
    assert provider.embed_batch_call_count == 0

@pytest.mark.anyio
async def test_embedder_module_all_existing() -> None:
    provider = MockBatchLimitingProvider(dimensions=2, max_batch=10, delay=0.0)
    embedder = EmbedderModule(provider=provider, max_concurrency=5)
    
    chunks = [
        _make_chunk("a", "1" * 64, has_embedding=True),
        _make_chunk("b", "2" * 64, has_embedding=True),
    ]
    
    results = await embedder.embed_chunks(chunks)
    assert len(results) == 2
    assert provider.embed_batch_call_count == 0
    assert results[0].embedding == (1.0, 2.0)
