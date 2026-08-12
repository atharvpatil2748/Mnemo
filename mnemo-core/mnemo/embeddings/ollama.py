import asyncio
import logging
from datetime import UTC, datetime

import httpx

from mnemo.config import EmbeddingConfig
from mnemo.interfaces.embedding import EmbeddingProviderV1
from mnemo.interfaces.types import (
    EmbeddingBatch,
    EmbeddingCapabilities,
    EmbeddingVector,
    HealthStatus,
)

_LOGGER = logging.getLogger(__name__)


class OllamaEmbedder(EmbeddingProviderV1):
    """Embedding provider for Ollama /api/embeddings."""

    def __init__(self, config: EmbeddingConfig) -> None:
        self._model = config.model
        self._configured_dimensions = config.dimensions
        self._api_base = (config.api_base or "http://127.0.0.1:11434").rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._api_base, timeout=httpx.Timeout(30.0))
        self._discovered_dimensions: int | None = None

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        if self._discovered_dimensions is None:
            raise RuntimeError("dimensions accessed before startup hook completed")
        return self._discovered_dimensions

    @property
    def max_tokens(self) -> int:
        # Default Ollama max context size is 8192
        return 8192

    def capabilities(self) -> EmbeddingCapabilities:
        return EmbeddingCapabilities(
            dimensions=self.dimensions,
            supports_batch=True,
            max_batch=50,
            multilingual=False,
            supports_normalization=False,
        )

    async def _post_with_retry(self, text: str) -> tuple[float, ...]:
        """Call Ollama /api/embeddings with exponential backoff on transient errors."""
        max_attempts = 3
        base_delay = 1.0

        for attempt in range(max_attempts):
            try:
                response = await self._client.post(
                    "/api/embeddings",
                    json={"model": self._model, "prompt": text},
                )
                response.raise_for_status()
                data = response.json()

                if not isinstance(data, dict) or "embedding" not in data:
                    raise ValueError(f"Malformed response from Ollama: {data}")

                embedding_data = data["embedding"]
                if not isinstance(embedding_data, list):
                    raise ValueError("Ollama response 'embedding' is not a list")

                vector = tuple(float(x) for x in embedding_data)
                return vector

            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as error:
                if attempt == max_attempts - 1:
                    _LOGGER.error(
                        "Ollama connection failed after %d attempts: %s", max_attempts, error
                    )
                    raise RuntimeError(f"Ollama connection error: {error}") from error
                await asyncio.sleep(base_delay * (2**attempt))
            except httpx.HTTPStatusError as error:
                status = error.response.status_code
                if status >= 500:
                    if attempt == max_attempts - 1:
                        _LOGGER.error(
                            "Ollama server error after %d attempts: %s", max_attempts, error
                        )
                        raise RuntimeError(f"Ollama server error {status}") from error
                    await asyncio.sleep(base_delay * (2**attempt))
                else:
                    # Deterministic error (e.g. 404 Model not found, 400 Bad Request)
                    raise ValueError(
                        f"Ollama provider error {status}: {error.response.text}"
                    ) from error

        raise RuntimeError("Unreachable")

    async def embed(self, text: str) -> EmbeddingVector:
        if not text:
            raise ValueError("text must not be empty")
        vector = await self._post_with_retry(text)
        if len(vector) != self.dimensions:
            raise ValueError(f"Dimension mismatch: expected {self.dimensions}, got {len(vector)}")
        return vector

    async def embed_batch(self, texts: tuple[str, ...]) -> EmbeddingBatch:
        if not texts:
            raise ValueError("texts must not be empty")

        # Bounded concurrency
        sem = asyncio.Semaphore(10)

        async def _embed_one(text: str) -> tuple[float, ...]:
            if not text:
                raise ValueError("batch texts must not contain empty strings")
            async with sem:
                vector = await self._post_with_retry(text)
                if len(vector) != self.dimensions:
                    raise ValueError(
                        f"Dimension mismatch: expected {self.dimensions}, got {len(vector)}"
                    )
                return vector

        vectors = await asyncio.gather(*[_embed_one(t) for t in texts])
        return EmbeddingBatch(
            vectors=tuple(vectors),
            model_name=self._model,
            dimensions=self.dimensions,
        )

    async def health_check(self) -> HealthStatus:
        """Ping Ollama to verify the model is accessible."""
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
            data = response.json()
            models = data.get("models", [])
            model_found = any(
                m.get("name") == self._model or m.get("name") == f"{self._model}:latest"
                for m in models
            )

            if model_found:
                return HealthStatus(
                    healthy=True,
                    component="OllamaEmbedder",
                    checked_at=datetime.now(UTC),
                )
            else:
                return HealthStatus(
                    healthy=False,
                    component="OllamaEmbedder",
                    checked_at=datetime.now(UTC),
                    detail=f"Model {self._model} not found in Ollama",
                )
        except Exception as e:
            return HealthStatus(
                healthy=False,
                component="OllamaEmbedder",
                checked_at=datetime.now(UTC),
                detail=str(e),
            )

    async def initialize(self) -> None:
        """Perform true asynchronous discovery of dimensions during startup."""
        status = await self.health_check()
        if not status.healthy:
            raise RuntimeError(f"Ollama initialization failed: {status.detail}")

        try:
            vector = await self._post_with_retry("initialization_probe")
            self._discovered_dimensions = len(vector)
        except Exception as error:
            raise RuntimeError("Ollama embedding discovery failed") from error

        if self._discovered_dimensions != self._configured_dimensions:
            raise ValueError(
                f"Dimension mismatch: Ollama returned {self._discovered_dimensions} dimensions, "
                f"but configured dimensions are {self._configured_dimensions}"
            )
