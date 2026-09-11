from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from mnemo.config import EmbeddingConfig
from mnemo.embeddings import sentence_transformers as subject


@pytest.mark.anyio
async def test_sentence_transformers_embedder_lifecycle_batch_and_health(
    monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    calls: list[tuple[object, ...]] = []

    class Model:
        max_seq_length = 0

        def __init__(self, target: str, **kwargs: object) -> None:
            calls.append((target, kwargs))

        def encode(self, texts, **kwargs):  # type: ignore[no-untyped-def]
            calls.append((tuple(texts), kwargs))
            return ((1.0, 0.0, 0.0),) * len(texts)

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=Model),
    )
    monkeypatch.setattr(subject, "_LOCAL_BGE_M3_SNAPSHOT", tmp_path / "absent")
    embedder = subject.SentenceTransformersEmbedder(
        EmbeddingConfig(provider="sentence-transformers", model="test-model", dimensions=3)
    )
    assert embedder.model_name == "test-model"
    assert embedder.dimensions == 3
    assert embedder.max_tokens == 8192
    assert embedder.capabilities().max_batch == 32
    assert not (await embedder.health_check()).healthy
    with pytest.raises(ValueError, match="must not be empty"):
        await embedder.embed_batch(())

    vector = await embedder.embed("hello")
    assert vector == (1.0, 0.0, 0.0)
    batch = await embedder.embed_batch(("one", "two"))
    assert batch.vectors == ((1.0, 0.0, 0.0), (1.0, 0.0, 0.0))
    assert batch.model_name == "test-model"
    assert (await embedder.health_check()).healthy
    await embedder.initialize()
    assert len([call for call in calls if call[0] == "test-model"]) == 1
    assert embedder._executor is not None
    embedder._executor.shutdown(wait=True)


@pytest.mark.anyio
async def test_sentence_transformers_embedder_initialization_error_is_typed(
    monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    class BrokenModel:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise OSError("snapshot corrupt")

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=BrokenModel),
    )
    monkeypatch.setattr(subject, "_LOCAL_BGE_M3_SNAPSHOT", tmp_path / "absent")
    embedder = subject.SentenceTransformersEmbedder(
        EmbeddingConfig(provider="sentence-transformers", model="broken", dimensions=3)
    )
    with pytest.raises(RuntimeError, match=r"initialization failed.*snapshot corrupt"):
        await embedder.initialize()
    assert embedder._executor is not None
    embedder._executor.shutdown(wait=True)
