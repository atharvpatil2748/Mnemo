"""Integration, contract, validation, and error tests for POST /v1/search."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from mnemo import __version__
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo.interfaces import (
    DependencyUnavailableError,
    EmbeddingBatch,
    EmbeddingCapabilities,
    EmbeddingProviderV1,
    LLMCapabilities,
    LLMInterfaceV1,
    StorageCapabilities,
    StorageError,
    StorageInterfaceV1,
    TokenCounterInterfaceV1,
)
from mnemo.models import (
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    FrozenMetadata,
    Notebook,
    ScoredChunk,
)
from mnemo.registry import PluginRegistry
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig


class MockTokenCounter(TokenCounterInterfaceV1):
    @property
    def tokenizer_id(self) -> str:
        return "mock-tokenizer"

    def count(self, text: str) -> int:
        return max(1, len(text.split()))


def _make_mock_chunk(
    *,
    chunk_id: str | None = None,
    text: str = "This is a search result chunk describing economic indicators.",
    document_id: UUID | None = None,
) -> Chunk:
    doc_id = document_id or uuid4()
    cid = chunk_id or ("b" * 64)
    return Chunk(
        id=cid,
        document_id=doc_id,
        version_id=uuid4(),
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=0, page_number=15),
        source_span=BlockSpan(start_ordinal=0, end_ordinal=1),
        text=text,
        heading_path=("Chapter 1", "Macroeconomics"),
        metadata=FrozenMetadata({"topic": "economics"}),
    )


def _make_mock_engine() -> MagicMock:
    from mnemo.retrieval import DenseRetriever, ParentRetriever, SparseRetriever

    # Storage mock
    storage_mock = MagicMock(spec=StorageInterfaceV1)
    storage_mock.capabilities.return_value = StorageCapabilities(
        supports_blobs=True,
        supports_dense_search=True,
        supports_sparse_search=True,
        supports_metadata=True,
        supports_graph=False,
        supports_transactions=True,
        supports_health_checks=True,
    )
    storage_mock.get_notebook = AsyncMock()
    storage_mock.get_document = AsyncMock(return_value=None)
    chunk = _make_mock_chunk()
    scored_chunk = ScoredChunk(chunk=chunk, score=0.88, source="dense", rank=1)
    storage_mock.search_dense = AsyncMock(return_value=(scored_chunk,))
    storage_mock.search_sparse = AsyncMock(return_value=(scored_chunk,))
    storage_mock.upsert_citation = AsyncMock()

    # Embedding provider mock
    embedding_mock = MagicMock(spec=EmbeddingProviderV1)
    embedding_mock.dimensions = 4
    embedding_mock.capabilities.return_value = EmbeddingCapabilities(
        dimensions=4,
        supports_batch=True,
        max_batch=32,
        multilingual=False,
        supports_normalization=True,
    )
    embedding_mock.embed = AsyncMock(return_value=(0.1, 0.2, 0.3, 0.4))
    embedding_mock.embed_batch = AsyncMock(
        side_effect=lambda texts: EmbeddingBatch(
            vectors=tuple((0.1, 0.2, 0.3, 0.4) for _ in texts),
            model_name="test-embed",
            dimensions=4,
        )
    )

    # LLM mock
    llm_mock = MagicMock(spec=LLMInterfaceV1)
    llm_mock.model = "test-model"
    llm_mock.model_name = "test-model"
    llm_mock.provider = "ollama"
    llm_mock.max_context_tokens = 8192
    llm_mock.capabilities.return_value = LLMCapabilities(
        supports_streaming=True,
        supports_json=True,
        supports_vision=False,
        supports_reasoning=False,
    )
    llm_mock.complete = AsyncMock()

    # Registry setup
    class MockPlugin:
        name = "mock-server-plugin"
        version = __version__
        core_version_range = f">={__version__}"

        def capabilities(self) -> tuple[str, ...]:
            return ("storage", "embedding", "llm", "retriever", "parent_promoter")

        def register(self, target: PluginRegistry) -> None:
            target.register_storage("primary", storage_mock, priority=0)
            target.register_embedding_provider("primary", embedding_mock, priority=0)
            target.register_retriever("dense", DenseRetriever(storage_mock), priority=0)
            target.register_retriever("sparse", SparseRetriever(storage_mock), priority=0)
            target.register_parent_promoter("default", ParentRetriever(storage_mock), priority=0)
            for role in ("planner", "synthesizer", "extractor", "classifier"):
                target.register_llm(role, llm_mock, priority=0)

    registry = PluginRegistry(core_version=__version__)
    registry.load_plugins((MockPlugin(),))
    registry.freeze()

    mock_engine = MagicMock(spec=KnowledgeEngine)
    mock_engine.state = EngineState.READY
    mock_engine.registry = registry
    mock_engine.embedding_provider = embedding_mock
    mock_engine.llm.return_value = llm_mock
    mock_engine.storage = storage_mock

    return mock_engine


@pytest.fixture
def mock_engine() -> MagicMock:
    return _make_mock_engine()


@pytest.fixture
def mock_token_counter() -> TokenCounterInterfaceV1:
    return MockTokenCounter()


@pytest.fixture
def test_notebook() -> Notebook:
    now = datetime.now(UTC)
    return Notebook(
        notebook_id=uuid4(),
        title="Economics Research",
        description="Workspace for monetary policy study",
        created_at=now,
        updated_at=now,
        metadata=FrozenMetadata({"category": "macroeconomics"}),
    )


@pytest.fixture
async def client(
    mock_engine: MagicMock,
    mock_token_counter: TokenCounterInterfaceV1,
) -> AsyncClient:
    server_config = ServerConfig()
    app = create_app(
        server_config=server_config,
        engine=mock_engine,
        provision_tokenizer_on_startup=False,
    )
    app.state.engine = mock_engine
    app.state.token_counter = mock_token_counter
    app.state.server_config = server_config
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# =============================================================================
# 1. POST /v1/search Tests
# =============================================================================


@pytest.mark.anyio
async def test_search_global_success(
    client: AsyncClient,
    mock_engine: MagicMock,
) -> None:
    """POST /v1/search returns ranked search results across all notebooks."""
    payload = {
        "query": "interest rates inflation",
        "notebook_id": None,
        "limit": 10,
        "modes": ["dense", "sparse"],
        "enable_reranking": True,
    }

    resp = await client.post("/v1/search", json=payload)
    assert resp.status_code == 200
    body = resp.json()

    assert "results" in body
    assert body["total"] >= 1
    assert body["latency_ms"] >= 1
    item = body["results"][0]
    assert item["chunk_id"] == "b" * 64
    assert "score" in item
    assert "rank" in item
    assert item["page_number"] == 15
    assert item["heading_path"] == ["Chapter 1", "Macroeconomics"]
    assert item["metadata"]["topic"] == "economics"

    # Verify that LLM complete was NOT called (pure search, no synthesis)
    mock_engine.llm().complete.assert_not_called()


@pytest.mark.anyio
async def test_search_scoped_to_notebook_success(
    client: AsyncClient,
    mock_engine: MagicMock,
    test_notebook: Notebook,
) -> None:
    """POST /v1/search scoped to an existing notebook succeeds."""
    mock_engine.storage.get_notebook.return_value = test_notebook

    payload = {
        "query": "unemployment metrics",
        "notebook_id": str(test_notebook.notebook_id),
        "limit": 5,
    }

    resp = await client.post("/v1/search", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    mock_engine.storage.get_notebook.assert_awaited_once_with(test_notebook.notebook_id)


@pytest.mark.anyio
async def test_search_missing_notebook_returns_404(
    client: AsyncClient,
    mock_engine: MagicMock,
) -> None:
    """POST /v1/search with a non-existent notebook_id returns 404 Not Found."""
    missing_id = uuid4()
    mock_engine.storage.get_notebook.return_value = None

    payload = {
        "query": "search query",
        "notebook_id": str(missing_id),
    }

    resp = await client.post("/v1/search", json=payload)
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "contract.not_found"


@pytest.mark.anyio
async def test_search_without_reranking_uses_rrf(
    client: AsyncClient,
    mock_engine: MagicMock,
) -> None:
    """POST /v1/search with enable_reranking: false returns fused RRF results."""
    payload = {
        "query": "market equilibrium",
        "enable_reranking": False,
        "limit": 5,
    }

    resp = await client.post("/v1/search", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["results"]) >= 1


@pytest.mark.anyio
async def test_search_validation_empty_query_returns_422(
    client: AsyncClient,
) -> None:
    """POST /v1/search with empty query returns 422 Unprocessable Content."""
    payload = {
        "query": "   ",
    }
    resp = await client.post("/v1/search", json=payload)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_search_validation_invalid_limit_returns_422(
    client: AsyncClient,
) -> None:
    """POST /v1/search with limit out of bounds (e.g. 0 or 200) returns 422."""
    resp = await client.post("/v1/search", json={"query": "test", "limit": 0})
    assert resp.status_code == 422

    resp2 = await client.post("/v1/search", json={"query": "test", "limit": 200})
    assert resp2.status_code == 422


@pytest.mark.anyio
async def test_search_validation_invalid_mode_returns_422(
    client: AsyncClient,
) -> None:
    """POST /v1/search with unsupported retrieval mode returns 422."""
    payload = {
        "query": "test",
        "modes": ["unsupported_mode"],
    }
    resp = await client.post("/v1/search", json=payload)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_search_storage_failure_returns_503(
    client: AsyncClient,
    mock_engine: MagicMock,
) -> None:
    """When storage search fails with StorageError, endpoint returns retryable 503."""
    mock_engine.storage.search_dense.side_effect = StorageError(
        "Qdrant connection lost", retryable=True
    )

    payload = {
        "query": "search query",
    }
    resp = await client.post("/v1/search", json=payload)
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "contract.storage"
    assert body["error"]["retryable"] is True


@pytest.mark.anyio
async def test_search_embedding_failure_returns_503(
    client: AsyncClient,
    mock_engine: MagicMock,
) -> None:
    """When embedding provider fails, endpoint returns retryable 503."""
    mock_engine.embedding_provider.embed.side_effect = DependencyUnavailableError(
        "Ollama service unavailable", retryable=True
    )

    payload = {
        "query": "search query",
    }
    resp = await client.post("/v1/search", json=payload)
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "contract.dependency_unavailable"
    assert body["error"]["retryable"] is True
