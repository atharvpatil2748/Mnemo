"""SentenceTransformers embedding provider for local multilingual models."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mnemo.config import EmbeddingConfig
from mnemo.interfaces.embedding import EmbeddingProviderV1
from mnemo.interfaces.types import (
    EmbeddingBatch,
    EmbeddingCapabilities,
    EmbeddingVector,
    HealthStatus,
)

_LOCAL_BGE_M3_SNAPSHOT = Path(
    "D:/Mnemo/phase8.5.11-models/huggingface/hub/models--BAAI--bge-m3/snapshots/5617a9f61b028005a4858fdac845db406aefb181"
)


class SentenceTransformersEmbedder(EmbeddingProviderV1):
    """Local embedding provider using sentence-transformers (e.g. BAAI/bge-m3)."""

    def __init__(self, config: EmbeddingConfig) -> None:
        self._model_name = config.model
        self._dimensions = config.dimensions or 1024
        self._model: Any = None
        self._executor: ThreadPoolExecutor | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def max_tokens(self) -> int:
        return 8192

    def capabilities(self) -> EmbeddingCapabilities:
        return EmbeddingCapabilities(
            dimensions=self.dimensions,
            supports_batch=True,
            max_batch=32,
            multilingual=True,
            supports_normalization=True,
        )

    async def initialize(self) -> None:
        if self._model is not None:
            return
        self._executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="sentence-transformers-embed"
        )
        loop = asyncio.get_running_loop()

        def _load() -> Any:
            import sentence_transformers

            target = (
                str(_LOCAL_BGE_M3_SNAPSHOT) if _LOCAL_BGE_M3_SNAPSHOT.exists() else self._model_name
            )
            model = sentence_transformers.SentenceTransformer(
                target,
                device="cpu",
                trust_remote_code=False,
                local_files_only=_LOCAL_BGE_M3_SNAPSHOT.exists(),
            )
            model.max_seq_length = self.max_tokens
            return model

        try:
            self._model = await loop.run_in_executor(self._executor, _load)
        except Exception as exc:
            raise RuntimeError(
                f"SentenceTransformers embedder initialization failed for {self._model_name}: {exc}"
            ) from exc

    async def health_check(self) -> HealthStatus:
        healthy = self._model is not None or _LOCAL_BGE_M3_SNAPSHOT.exists()
        return HealthStatus(
            healthy=healthy,
            component="SentenceTransformersEmbedder",
            checked_at=datetime.now(UTC),
            detail=None if healthy else f"Model snapshot {self._model_name} unavailable",
        )

    async def embed(self, text: str) -> EmbeddingVector:
        batch = await self.embed_batch((text,))
        return batch.vectors[0]

    async def embed_batch(self, texts: tuple[str, ...]) -> EmbeddingBatch:
        if not texts:
            raise ValueError("texts must not be empty")
        if self._model is None or self._executor is None:
            await self.initialize()

        loop = asyncio.get_running_loop()
        raw_vectors = await loop.run_in_executor(
            self._executor,
            lambda: self._model.encode(
                list(texts),
                batch_size=32,
                show_progress_bar=False,
                normalize_embeddings=True,
            ),
        )
        vectors = tuple(tuple(float(v) for v in row) for row in raw_vectors)
        return EmbeddingBatch(
            vectors=vectors,
            model_name=self._model_name,
            dimensions=self._dimensions,
        )
