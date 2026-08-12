"""Orchestrates bulk embedding of document chunks."""

from collections.abc import Sequence
from dataclasses import replace

import anyio

from mnemo.interfaces.embedding import EmbeddingProviderV1
from mnemo.models.chunks import Chunk


class EmbedderModule:
    """Pipelines parsed chunks through the configured embedding provider."""

    def __init__(self, provider: EmbeddingProviderV1, max_concurrency: int = 4) -> None:
        """Create the orchestrator with the given provider and concurrency limits."""
        self._provider = provider
        self._max_concurrency = max_concurrency

    async def embed_chunks(self, chunks: Sequence[Chunk]) -> tuple[Chunk, ...]:
        """Generate and attach embeddings to a sequence of chunks.

        Preserves the exact order of the input chunks. Returns new Chunk instances
        with the embedding field populated. Ignores chunks that already have an embedding.
        """
        if not chunks:
            return ()

        max_batch = self._provider.capabilities().max_batch

        # Separate chunks that need embedding
        needs_embedding: list[Chunk] = []
        indices: list[int] = []
        for i, chunk in enumerate(chunks):
            if chunk.embedding is None:
                needs_embedding.append(chunk)
                indices.append(i)

        if not needs_embedding:
            return tuple(chunks)

        # We need to process needs_embedding in batches
        batches: list[list[Chunk]] = []
        for i in range(0, len(needs_embedding), max_batch):
            batches.append(needs_embedding[i : i + max_batch])

        # Store results for the ones that need embedding
        new_embeddings: list[tuple[float, ...] | None] = [None] * len(needs_embedding)
        limiter = anyio.CapacityLimiter(self._max_concurrency)

        async def process_batch(batch_idx: int, batch_chunks: list[Chunk]) -> None:
            async with limiter:
                texts = tuple(c.text for c in batch_chunks)
                batch_result = await self._provider.embed_batch(texts)
                
                # Write back to new_embeddings at correct offsets
                offset = batch_idx * max_batch
                for j, vec in enumerate(batch_result.vectors):
                    new_embeddings[offset + j] = vec

        async with anyio.create_task_group() as tg:
            for batch_idx, batch_chunks in enumerate(batches):
                tg.start_soon(process_batch, batch_idx, batch_chunks)

        # Construct final tuple
        results = list(chunks)
        for i, idx in enumerate(indices):
            vec = new_embeddings[i]
            assert vec is not None
            results[idx] = replace(chunks[idx], embedding=vec)

        return tuple(results)
