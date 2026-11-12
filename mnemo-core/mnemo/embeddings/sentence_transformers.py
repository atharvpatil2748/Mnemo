"""SentenceTransformers embedding provider for local multilingual models."""

from __future__ import annotations

import asyncio
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from mnemo.config import EmbeddingConfig
from mnemo.interfaces.embedding import EmbeddingProviderV1
from mnemo.interfaces.types import (
    EmbeddingBatch,
    EmbeddingCapabilities,
    EmbeddingVector,
    HealthStatus,
)


class SentenceTransformersEmbedder(EmbeddingProviderV1):
    """Local embedding provider using sentence-transformers (e.g. BAAI/bge-m3)."""

    def __init__(self, config: EmbeddingConfig) -> None:
        self._model_name = config.model
        self._dimensions = config.dimensions
        self._device = config.device
        self._model_path = config.model_path
        self._revision = config.revision
        self._max_tokens = config.max_tokens
        self._max_batch = config.max_batch
        self._normalize_embeddings = config.normalize_embeddings
        self._query_prompt = config.query_prompt
        self._document_prompt = config.document_prompt
        self._model: Any = None
        self._executor: ThreadPoolExecutor | None = None

    @property
    def execution_device(self) -> str | None:
        """Return the loaded model's actual device for build attestation."""
        return None if self._model is None else str(self._model.device)

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    def capabilities(self) -> EmbeddingCapabilities:
        return EmbeddingCapabilities(
            dimensions=self.dimensions,
            supports_batch=True,
            max_batch=self._max_batch,
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

            target = str(self._model_path) if self._model_path is not None else self._model_name
            if self._model_path is not None and not self._model_path.is_dir():
                raise FileNotFoundError(
                    f"configured local embedding model path is missing: {target}"
                )
            model = sentence_transformers.SentenceTransformer(
                target,
                device=self._device,
                trust_remote_code=False,
                revision=self._revision if self._model_path is None else None,
                local_files_only=True,
            )
            model.max_seq_length = self._max_tokens
            if self._device == "cuda" and not str(model.device).startswith("cuda"):
                raise RuntimeError("canonical embedding model did not load on CUDA")
            return model

        try:
            self._model = await loop.run_in_executor(self._executor, _load)
        except Exception as exc:
            raise RuntimeError(
                f"SentenceTransformers embedder initialization failed for {self._model_name}: {exc}"
            ) from exc

    async def health_check(self) -> HealthStatus:
        healthy = self._model is not None or (
            self._model_path is not None and self._model_path.is_dir()
        )
        return HealthStatus(
            healthy=healthy,
            component="SentenceTransformersEmbedder",
            checked_at=datetime.now(UTC),
            detail=None if healthy else f"Local model snapshot {self._model_name} unavailable",
        )

    async def embed(self, text: str) -> EmbeddingVector:
        batch = await self._encode((text,), prompt=self._query_prompt)
        return batch.vectors[0]

    async def embed_batch(self, texts: tuple[str, ...]) -> EmbeddingBatch:
        """Encode document-side texts with the configured document prompt."""
        return await self._encode(texts, prompt=self._document_prompt)

    async def _encode(self, texts: tuple[str, ...], *, prompt: str | None) -> EmbeddingBatch:
        if not texts:
            raise ValueError("texts must not be empty")
        if self._model is None or self._executor is None:
            await self.initialize()

        loop = asyncio.get_running_loop()

        def _encode_batch() -> Any:
            kwargs: dict[str, object] = {
                "batch_size": self._max_batch,
                "show_progress_bar": False,
                "normalize_embeddings": self._normalize_embeddings,
            }
            if prompt is not None:
                kwargs["prompt"] = prompt
            return self._model.encode(list(texts), **kwargs)

        raw_vectors = await loop.run_in_executor(self._executor, _encode_batch)
        vectors = tuple(tuple(float(v) for v in row) for row in raw_vectors)
        if any(len(vector) != self._dimensions for vector in vectors):
            raise ValueError("embedding provider output dimension differs from configuration")
        if any(not math.isfinite(value) for vector in vectors for value in vector):
            raise ValueError("embedding provider returned a non-finite value")
        return EmbeddingBatch(
            vectors=vectors,
            model_name=self._model_name,
            dimensions=self._dimensions,
        )
