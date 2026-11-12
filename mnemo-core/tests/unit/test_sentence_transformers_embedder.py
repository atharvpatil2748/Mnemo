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
    embedder = subject.SentenceTransformersEmbedder(
        EmbeddingConfig(provider="sentence-transformers", model="broken", dimensions=3)
    )
    with pytest.raises(RuntimeError, match=r"initialization failed.*snapshot corrupt"):
        await embedder.initialize()
    assert embedder._executor is not None
    embedder._executor.shutdown(wait=True)


@pytest.mark.anyio
async def test_sentence_transformers_cuda_selection_fails_closed(monkeypatch, tmp_path) -> None:
    class Model:
        def __init__(self, target: str, *, device: str, **kwargs: object) -> None:
            self.device = device

        def encode(self, texts, **kwargs):  # type: ignore[no-untyped-def]
            return ((1.0, 0.0, 0.0),) * len(texts)

    monkeypatch.setitem(
        sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=Model)
    )
    config = EmbeddingConfig(
        provider="sentence-transformers", model="test-model", dimensions=3, device="cuda"
    )
    embedder = subject.SentenceTransformersEmbedder(config)
    assert embedder.execution_device is None
    assert await embedder.embed("probe") == (1.0, 0.0, 0.0)
    assert embedder._model.device == "cuda"
    assert embedder.execution_device == "cuda"
    assert embedder._executor is not None
    embedder._executor.shutdown(wait=True)

    class CpuModel(Model):
        def __init__(self, target: str, *, device: str, **kwargs: object) -> None:
            super().__init__(target, device="cpu", **kwargs)

    monkeypatch.setitem(
        sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=CpuModel)
    )
    rejected = subject.SentenceTransformersEmbedder(config)
    with pytest.raises(RuntimeError, match="did not load on CUDA"):
        await rejected.initialize()
    assert rejected._executor is not None
    rejected._executor.shutdown(wait=True)


@pytest.mark.anyio
async def test_sentence_transformers_configures_local_revision_prompts_and_batch(
    monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    model_dir = tmp_path / "qwen-model"
    model_dir.mkdir()
    calls: list[tuple[object, ...]] = []

    class Model:
        max_seq_length = 0
        device = "cpu"

        def __init__(self, target: str, **kwargs: object) -> None:
            calls.append(("load", target, kwargs))

        def encode(self, texts, **kwargs):  # type: ignore[no-untyped-def]
            calls.append(("encode", tuple(texts), kwargs))
            return ((1.0, 0.0, 0.0),) * len(texts)

    monkeypatch.setitem(
        sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=Model)
    )
    embedder = subject.SentenceTransformersEmbedder(
        EmbeddingConfig(
            provider="sentence-transformers",
            model="Qwen/Qwen3-Embedding-0.6B",
            model_path=model_dir,
            revision="pinned-revision",
            dimensions=3,
            max_tokens=4096,
            max_batch=4,
            query_prompt="query: ",
            document_prompt="passage: ",
        )
    )
    assert await embedder.embed("query") == (1.0, 0.0, 0.0)
    await embedder.embed_batch(("document 1", "document 2"))
    load = next(call for call in calls if call[0] == "load")
    assert load[1] == str(model_dir)
    assert load[2]["local_files_only"] is True
    encodes = [call for call in calls if call[0] == "encode"]
    assert encodes[0][2]["prompt"] == "query: "
    assert encodes[1][2]["prompt"] == "passage: "
    assert encodes[1][2]["batch_size"] == 4
    assert embedder.max_tokens == 4096
    assert embedder._executor is not None
    embedder._executor.shutdown(wait=True)
