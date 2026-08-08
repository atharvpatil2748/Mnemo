"""Tests for immutable Module 1.2 contract value records."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest
from mnemo.interfaces import (
    ChunkerCapabilities,
    ChunkingOptions,
    CompletionResult,
    EmbeddingBatch,
    EmbeddingCapabilities,
    FileMetadata,
    HealthStatus,
    LLMCapabilities,
    Message,
    MessageRole,
    Page,
    ParserCapabilities,
    RerankerCapabilities,
    RetrieverCapabilities,
    StorageCapabilities,
)
from mnemo.models import DocType, FrozenMetadata


def test_file_metadata_is_an_immutable_hashable_value(content_hash: str) -> None:
    """File metadata validates, compares by value, and remains immutable."""
    timestamp = datetime(2026, 8, 7, tzinfo=UTC)
    value = FileMetadata(
        content_hash=content_hash,
        size_bytes=12,
        mime_type="text/plain",
        modified_at=timestamp,
        metadata=FrozenMetadata({"parser.source": "upload"}),
    )

    assert value == FileMetadata(
        content_hash=content_hash,
        size_bytes=12,
        mime_type="text/plain",
        modified_at=timestamp,
        metadata=FrozenMetadata({"parser.source": "upload"}),
    )
    assert hash(value)
    with pytest.raises(FrozenInstanceError):
        value.size_bytes = 13  # type: ignore[misc]


@pytest.mark.parametrize(
    "overrides",
    [
        {"content_hash": "invalid"},
        {"size_bytes": -1},
        {"mime_type": " "},
        {"modified_at": datetime(2026, 8, 7)},
        {"metadata": {}},
    ],
)
def test_file_metadata_rejects_invalid_fields(
    content_hash: str,
    overrides: dict[str, object],
) -> None:
    """Malformed caller-known file facts are rejected."""
    values: dict[str, object] = {"content_hash": content_hash, "size_bytes": 0}
    values.update(overrides)
    with pytest.raises((TypeError, ValueError)):
        FileMetadata(**values)  # type: ignore[arg-type]


def test_chunking_options_validate_limits_and_hash() -> None:
    """Chunking limits are immutable, ordered, and hashable."""
    options = ChunkingOptions(target_tokens=400, max_tokens=500, overlap_tokens=40)
    assert hash(options)

    for values in (
        {"target_tokens": 0, "max_tokens": 10},
        {"target_tokens": 11, "max_tokens": 10},
        {"target_tokens": 10, "max_tokens": 10, "overlap_tokens": 10},
        {"target_tokens": 10, "max_tokens": 10, "overlap_tokens": -1},
        {"target_tokens": 10, "max_tokens": 10, "metadata": {}},
    ):
        with pytest.raises((TypeError, ValueError)):
            ChunkingOptions(**values)


def test_embedding_batch_preserves_order_and_validates_vectors() -> None:
    """Embedding batches validate model identity, dimensions, and finiteness."""
    batch = EmbeddingBatch(
        vectors=((1.0, 2.0), (3.0, 4.0)),
        model_name="local/model",
        dimensions=2,
    )
    assert batch.vectors[1] == (3.0, 4.0)
    assert hash(batch)

    for values in (
        {"vectors": (), "model_name": "model", "dimensions": 2},
        {"vectors": ((1.0,),), "model_name": "model", "dimensions": 2},
        {"vectors": ((float("nan"),),), "model_name": "model", "dimensions": 1},
        {"vectors": [[1.0]], "model_name": "model", "dimensions": 1},
        {"vectors": ((1.0,),), "model_name": " ", "dimensions": 1},
        {"vectors": ((1.0,),), "model_name": "model", "dimensions": 0},
    ):
        with pytest.raises((TypeError, ValueError)):
            EmbeddingBatch(**values)  # type: ignore[arg-type]


def test_health_message_and_completion_records() -> None:
    """Provider-facing records remain transport-independent immutable values."""
    timestamp = datetime(2026, 8, 7, tzinfo=UTC)
    health = HealthStatus(
        healthy=True,
        component="embedding",
        checked_at=timestamp,
    )
    message = Message(role=MessageRole.USER, content="What is Mnemo?")
    text = CompletionResult(model="local", text="A knowledge engine.")
    structured = CompletionResult(
        model="local",
        structured=FrozenMetadata({"answer": "A knowledge engine."}),
    )
    structured_null = CompletionResult(model="local", structured=None)

    assert health.healthy
    assert message.role.value == "user"
    assert text.text == "A knowledge engine."
    assert structured.structured == FrozenMetadata({"answer": "A knowledge engine."})
    assert structured_null.structured is None
    assert hash(health) and hash(message) and hash(text) and hash(structured)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: HealthStatus(
            healthy=1,  # type: ignore[arg-type]
            component="x",
            checked_at=datetime(2026, 8, 7, tzinfo=UTC),
        ),
        lambda: HealthStatus(
            healthy=True,
            component=" ",
            checked_at=datetime(2026, 8, 7, tzinfo=UTC),
        ),
        lambda: HealthStatus(
            healthy=True,
            component="x",
            checked_at=datetime(2026, 8, 7),
        ),
        lambda: HealthStatus(
            healthy=True,
            component="x",
            checked_at=datetime(2026, 8, 7, tzinfo=UTC),
            detail=" ",
        ),
        lambda: HealthStatus(
            healthy=True,
            component="x",
            checked_at=datetime(2026, 8, 7, tzinfo=UTC),
            metadata={},  # type: ignore[arg-type]
        ),
        lambda: Message(role="user", content="x"),  # type: ignore[arg-type]
        lambda: Message(role=MessageRole.USER, content=" "),
        lambda: Message(
            role=MessageRole.USER,
            content="x",
            metadata={},  # type: ignore[arg-type]
        ),
        lambda: CompletionResult(model="model"),
        lambda: CompletionResult(model="model", text="x", structured=True),
        lambda: CompletionResult(model="model", text=" "),
        lambda: CompletionResult(model=" ", text="x"),
        lambda: CompletionResult(model="model", text="x", metadata={}),  # type: ignore[arg-type]
    ],
)
def test_provider_record_validation(factory: object) -> None:
    """Provider records reject malformed and ambiguous values."""
    with pytest.raises((TypeError, ValueError)):
        factory()  # type: ignore[operator]


def test_capability_records_are_typed_immutable_metadata() -> None:
    """Each Module 1.2 provider exposes a frozen capability record."""
    values = (
        ParserCapabilities(
            supported_formats=(".pdf",),
            supports_tables=True,
            supports_images=True,
            supports_math=True,
            supports_ocr=False,
        ),
        ChunkerCapabilities(
            supported_doc_types=(DocType.PAPER,),
            preserves_semantic_boundaries=True,
            supports_parent_child=True,
            supports_overlap=True,
        ),
        EmbeddingCapabilities(
            dimensions=768,
            supports_batch=True,
            max_batch=32,
            multilingual=True,
            supports_normalization=True,
        ),
        RetrieverCapabilities(
            supports_hybrid=False,
            supports_metadata_filters=True,
            supports_parent_child=False,
            supports_reranking=False,
        ),
        RerankerCapabilities(
            supports_cross_encoder=True,
            supports_batch=True,
            preserves_raw_scores=True,
        ),
        LLMCapabilities(
            supports_streaming=True,
            supports_json=True,
            supports_vision=False,
            supports_reasoning=False,
        ),
        StorageCapabilities(
            supports_blobs=True,
            supports_dense_search=True,
            supports_sparse_search=True,
            supports_metadata=True,
            supports_graph=True,
            supports_transactions=True,
            supports_health_checks=True,
        ),
    )

    assert all(hash(value) for value in values)
    with pytest.raises(FrozenInstanceError):
        values[0].supports_tables = False  # type: ignore[misc]  # type: ignore[misc]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ParserCapabilities(
            supported_formats=(),
            supports_tables=True,
            supports_images=True,
            supports_math=True,
            supports_ocr=True,
        ),
        lambda: ParserCapabilities(
            supported_formats=(".pdf", ".pdf"),
            supports_tables=True,
            supports_images=True,
            supports_math=True,
            supports_ocr=True,
        ),
        lambda: ParserCapabilities(
            supported_formats=(" ",),
            supports_tables=True,
            supports_images=True,
            supports_math=True,
            supports_ocr=True,
        ),
        lambda: ChunkerCapabilities(
            supported_doc_types=(),
            preserves_semantic_boundaries=True,
            supports_parent_child=True,
            supports_overlap=True,
        ),
        lambda: ChunkerCapabilities(
            supported_doc_types=(DocType.PAPER, DocType.PAPER),
            preserves_semantic_boundaries=True,
            supports_parent_child=True,
            supports_overlap=True,
        ),
        lambda: ChunkerCapabilities(
            supported_doc_types=("paper",),  # type: ignore[arg-type]
            preserves_semantic_boundaries=True,
            supports_parent_child=True,
            supports_overlap=True,
        ),
        lambda: EmbeddingCapabilities(
            dimensions=0,
            supports_batch=True,
            max_batch=1,
            multilingual=True,
            supports_normalization=True,
        ),
        lambda: EmbeddingCapabilities(
            dimensions=1,
            supports_batch=False,
            max_batch=2,
            multilingual=True,
            supports_normalization=True,
        ),
        lambda: RetrieverCapabilities(
            supports_hybrid=1,  # type: ignore[arg-type]
            supports_metadata_filters=True,
            supports_parent_child=True,
            supports_reranking=True,
        ),
        lambda: LLMCapabilities(
            supports_streaming=True,
            supports_json=True,
            supports_vision=True,
            supports_reasoning=True,
            metadata={},  # type: ignore[arg-type]
        ),
        lambda: ParserCapabilities(
            supported_formats=(".pdf",),
            supports_tables=True,
            supports_images=True,
            supports_math=True,
            supports_ocr=False,
            metadata=FrozenMetadata({"extension": True}),
        ),
    ],
)
def test_capability_validation(factory: object) -> None:
    """Capability descriptions reject mutable or malformed metadata."""
    with pytest.raises((TypeError, ValueError)):
        factory()  # type: ignore[operator]


def test_page_is_immutable_generic_and_validates_cursor() -> None:
    """Repository pages preserve immutable item order."""
    page = Page(items=("a", "b"), next_cursor="next")
    assert page.items == ("a", "b")
    assert hash(page)
    with pytest.raises(TypeError):
        Page(items=["a"])  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Page(items=(), next_cursor=" ")


def test_capability_extension_metadata_requires_namespace() -> None:
    """Namespaced extension keys remain immutable and collision-resistant."""
    capabilities = ParserCapabilities(
        supported_formats=(".pdf",),
        supports_tables=True,
        supports_images=True,
        supports_math=True,
        supports_ocr=False,
        metadata=FrozenMetadata({"plugin.example.accelerated": True}),
    )

    assert capabilities.metadata["plugin.example.accelerated"] is True
