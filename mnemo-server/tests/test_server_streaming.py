"""Integration and contract tests for WebSocket and SSE streaming endpoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from mnemo import __version__
from mnemo.config import MnemoConfig
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo.interfaces import (
    CompletionResult,
    EmbeddingBatch,
    EmbeddingCapabilities,
    EmbeddingProviderV1,
    LLMCapabilities,
    LLMInterfaceV1,
    StorageCapabilities,
    StorageInterfaceV1,
    TokenCounterInterfaceV1,
)
from mnemo.models import (
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    Document,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    FrozenMetadata,
    Notebook,
    ScoredChunk,
)
from mnemo.registry import PluginRegistry
from mnemo.retrieval import DenseRetriever, ParentRetriever, SparseRetriever
from mnemo_server.app import create_app
from mnemo_server.schemas.streaming import StreamEventType
from starlette.testclient import TestClient


def _make_mock_chunk(doc_id: UUID, index: int = 0) -> Chunk:
    chunk_id = "a" * 63 + str(index)
    version_id = uuid4()
    return Chunk(
        id=chunk_id,
        document_id=doc_id,
        version_id=version_id,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=index, page_number=1),
        source_span=BlockSpan(start_ordinal=0, end_ordinal=1),
        text=f"Sample evidence paragraph from document for testing chunk index {index}. [source:1]",
        heading_path=("Overview", "Introduction"),
        metadata=FrozenMetadata({"author": "Researcher"}),
    )


def _make_mock_engine(*, config: MnemoConfig | None = None) -> tuple[MagicMock, UUID, Chunk]:
    mock_engine = MagicMock(spec=KnowledgeEngine)
    mock_engine.state = EngineState.READY
    mock_engine.version = "0.24.0"
    mock_engine.initialize = AsyncMock()
    mock_engine.shutdown = AsyncMock()

    notebook_id = uuid4()
    doc_id = uuid4()
    chunk = _make_mock_chunk(doc_id, 0)

    # Core config
    if config is None:
        mock_engine.config = MnemoConfig.model_validate(
            {
                "llm": {
                    "planner": {"provider": "ollama", "model": "qwen2.5:7b-instruct"},
                    "synthesizer": {"provider": "ollama", "model": "qwen2.5:7b-instruct"},
                    "extractor": {"provider": "ollama", "model": "qwen2.5:7b-instruct"},
                    "classifier": {"provider": "ollama", "model": "qwen2.5:7b-instruct"},
                },
                "embedding": {
                    "provider": "ollama",
                    "model": "nomic-embed-text",
                    "dimensions": 768,
                },
                "reranker": {
                    "provider": "cross-encoder",
                    "model": "ms-marco-MiniLM-L-6-v2",
                },
            }
        )
    else:
        mock_engine.config = config

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

    now = datetime.now(UTC)

    async def _get_notebook(nid: UUID) -> Notebook | None:
        if nid == notebook_id:
            return Notebook(
                notebook_id=notebook_id,
                title="Test Notebook",
                created_at=now,
                updated_at=now,
            )
        return None

    storage_mock.get_notebook = AsyncMock(side_effect=_get_notebook)

    async def _get_doc(did: UUID) -> Document | None:
        if did == doc_id:
            now = datetime.now(UTC)
            dummy_hash = "0" * 64
            doc_version = DocumentVersion(
                version_id=chunk.version_id,
                document_id=doc_id,
                content_hash=dummy_hash,
                metadata=DocumentMetadata(content_hash=dummy_hash, title="Sample Research Paper"),
                status=DocumentVersionStatus.CURRENT,
                created_at=now,
            )
            return Document(
                document_id=doc_id,
                versions=(doc_version,),
                current_version_id=chunk.version_id,
                current_hash=dummy_hash,
                status=DocumentStatus.INDEXED,
                created_at=now,
                updated_at=now,
            )
        return None

    storage_mock.get_document = AsyncMock(side_effect=_get_doc)

    scored_chunk = ScoredChunk(chunk=chunk, score=0.92, source="dense", rank=1)
    storage_mock.search_dense = AsyncMock(return_value=(scored_chunk,))
    storage_mock.search_sparse = AsyncMock(return_value=(scored_chunk,))
    storage_mock.search_chunks = AsyncMock(return_value=(scored_chunk,))
    mock_engine.storage = storage_mock

    # Embedding provider mock
    emb_mock = MagicMock(spec=EmbeddingProviderV1)
    emb_mock.dimensions = 768
    emb_mock.capabilities.return_value = EmbeddingCapabilities(
        dimensions=768,
        supports_batch=True,
        max_batch=32,
        multilingual=False,
        supports_normalization=True,
    )
    emb_mock.embed = AsyncMock(return_value=tuple([0.1] * 768))
    emb_mock.embed_batch = AsyncMock(
        side_effect=lambda texts: EmbeddingBatch(
            vectors=tuple(tuple([0.1] * 768) for _ in texts),
            model_name="nomic-embed-text",
            dimensions=768,
        )
    )
    mock_engine.embedding_provider = emb_mock

    # LLM synthesizer mock with stream
    synthesizer_mock = MagicMock(spec=LLMInterfaceV1)
    synthesizer_mock.provider = "ollama"
    synthesizer_mock.model = "qwen2.5:7b-instruct"
    synthesizer_mock.model_name = "qwen2.5:7b-instruct"
    synthesizer_mock.max_context_tokens = 4096
    synthesizer_mock.capabilities.return_value = LLMCapabilities(
        supports_streaming=True,
        supports_json=True,
        supports_vision=False,
        supports_reasoning=False,
    )
    synthesizer_mock.complete = AsyncMock(
        return_value=CompletionResult(
            model="qwen2.5:7b-instruct",
            text=(
                "According to the research, quantum computing enables faster simulation [source:1]."
            ),
        )
    )

    async def _mock_stream(*args: Any, **kwargs: Any) -> Any:
        tokens = [
            "According ",
            "to ",
            "the ",
            "research, ",
            "quantum ",
            "computing ",
            "enables ",
            "faster ",
            "simulation ",
            "[source:1].",
        ]
        for t in tokens:
            yield t

    synthesizer_mock.stream = _mock_stream

    # Real frozen PluginRegistry
    class MockPlugin:
        name = "mock-streaming-plugin"
        version = __version__
        core_version_range = f">={__version__}"

        def capabilities(self) -> tuple[str, ...]:
            return ("storage", "embedding", "llm", "retriever", "parent_promoter")

        def register(self, target: PluginRegistry) -> None:
            target.register_storage("primary", storage_mock, priority=0)
            target.register_embedding_provider("primary", emb_mock, priority=0)
            target.register_retriever("dense", DenseRetriever(storage_mock), priority=0)
            target.register_retriever("sparse", SparseRetriever(storage_mock), priority=0)
            target.register_parent_promoter("default", ParentRetriever(storage_mock), priority=0)
            for role in ("planner", "synthesizer", "extractor", "classifier"):
                target.register_llm(role, synthesizer_mock, priority=0)

    registry = PluginRegistry(core_version=__version__)
    registry.load_plugins((MockPlugin(),))
    registry.freeze()

    mock_engine.registry = registry

    return mock_engine, notebook_id, chunk


def _make_mock_token_counter() -> MagicMock:
    tc = MagicMock(spec=TokenCounterInterfaceV1)
    tc.tokenizer_id = "o200k_base"
    tc.count = MagicMock(side_effect=lambda text: max(1, len(text.split())))
    return tc


@pytest.fixture
def streaming_setup() -> tuple[Any, UUID, Chunk]:
    engine, notebook_id, chunk = _make_mock_engine()
    tc = _make_mock_token_counter()
    app = create_app(engine=engine, provision_tokenizer_on_startup=False)
    app.state.engine = engine
    app.state.token_counter = tc
    return app, notebook_id, chunk


def test_websocket_streaming_query_happy_path(streaming_setup: tuple[Any, UUID, Chunk]) -> None:
    app, notebook_id, _chunk = streaming_setup
    client = TestClient(app)

    with client.websocket_connect("/ws/query") as websocket:
        query_payload = {
            "notebook_id": str(notebook_id),
            "question": "What does quantum computing enable?",
            "context_budget": 4000,
            "retrieval_config": {
                "modes": ["dense"],
                "top_k": 5,
            },
            "synthesis": {
                "enabled": True,
                "max_response_tokens": 500,
            },
        }
        websocket.send_text(json.dumps(query_payload))

        events: list[dict[str, Any]] = []
        # Receive all 5 events
        while True:
            msg = websocket.receive_text()
            event_obj = json.loads(msg)
            events.append(event_obj)
            if event_obj["event"] == StreamEventType.DONE:
                break

        event_names = [e["event"] for e in events]
        assert StreamEventType.RETRIEVAL_START in event_names
        assert StreamEventType.CHUNK_RETRIEVED in event_names
        assert StreamEventType.SYNTHESIS_TOKEN in event_names
        assert StreamEventType.CITATIONS_READY in event_names
        assert StreamEventType.DONE in event_names

        # Verify tokens
        tokens = [
            e["data"]["token"] for e in events if e["event"] == StreamEventType.SYNTHESIS_TOKEN
        ]
        full_text = "".join(tokens)
        assert "[source:1]" in full_text

        # Verify citations
        citations_event = next(e for e in events if e["event"] == StreamEventType.CITATIONS_READY)
        assert len(citations_event["data"]["citations"]) >= 1
        cit = citations_event["data"]["citations"][0]
        assert cit["document_title"] == "Sample Research Paper"

        # Verify done
        done_event = next(e for e in events if e["event"] == StreamEventType.DONE)
        assert done_event["data"]["retrieval_metadata"]["chunks_retrieved"] >= 1


def test_websocket_v1_alias_and_heartbeat(streaming_setup: tuple[Any, UUID, Chunk]) -> None:
    app, _notebook_id, _chunk = streaming_setup
    client = TestClient(app)

    with client.websocket_connect("/v1/ws/query") as websocket:
        # Send raw string ping
        websocket.send_text("ping")
        resp1 = json.loads(websocket.receive_text())
        assert resp1["event"] == StreamEventType.PONG

        # Send JSON object ping
        websocket.send_text(json.dumps({"type": "ping"}))
        resp2 = json.loads(websocket.receive_text())
        assert resp2["event"] == StreamEventType.PONG


def test_websocket_invalid_json(streaming_setup: tuple[Any, UUID, Chunk]) -> None:
    app, _notebook_id, _chunk = streaming_setup
    client = TestClient(app)

    with client.websocket_connect("/ws/query") as websocket:
        websocket.send_text("{bad json")
        resp = json.loads(websocket.receive_text())
        assert resp["event"] == StreamEventType.ERROR
        assert resp["data"]["code"] == "bad_request"


def test_websocket_validation_error(streaming_setup: tuple[Any, UUID, Chunk]) -> None:
    app, _notebook_id, _chunk = streaming_setup
    client = TestClient(app)

    with client.websocket_connect("/ws/query") as websocket:
        websocket.send_text(json.dumps({"unknown_field": 123}))
        resp = json.loads(websocket.receive_text())
        assert resp["event"] == StreamEventType.ERROR
        assert resp["data"]["code"] == "validation_error"


def test_websocket_notebook_not_found(streaming_setup: tuple[Any, UUID, Chunk]) -> None:
    app, _notebook_id, _chunk = streaming_setup
    client = TestClient(app)
    missing_id = uuid4()

    with client.websocket_connect("/ws/query") as websocket:
        websocket.send_text(
            json.dumps(
                {
                    "notebook_id": str(missing_id),
                    "question": "What is quantum computing?",
                }
            )
        )
        # First event is retrieval_start, then error is raised
        resp1 = json.loads(websocket.receive_text())
        assert resp1["event"] == StreamEventType.RETRIEVAL_START
        resp2 = json.loads(websocket.receive_text())
        assert resp2["event"] == StreamEventType.ERROR
        assert resp2["data"]["code"] == "not_found"


def test_websocket_engine_not_ready() -> None:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.UNINITIALIZED
    app = create_app(engine=engine, provision_tokenizer_on_startup=False)
    app.state.engine = engine

    client = TestClient(app)
    with client.websocket_connect("/ws/query") as websocket:
        resp = json.loads(websocket.receive_text())
        assert resp["event"] == StreamEventType.ERROR
        assert resp["data"]["code"] == "dependency_unavailable"


@pytest.mark.anyio
async def test_sse_query_stream_happy_path(streaming_setup: tuple[Any, UUID, Chunk]) -> None:
    app, notebook_id, _chunk = streaming_setup
    query_payload = {
        "notebook_id": str(notebook_id),
        "question": "What does quantum computing enable?",
        "context_budget": 4000,
        "retrieval_config": {
            "modes": ["dense"],
            "top_k": 5,
        },
        "synthesis": {
            "enabled": True,
            "max_response_tokens": 500,
        },
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/query/stream", json=query_payload)

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    text = resp.text
    assert "event: retrieval_start" in text
    assert "event: chunk_retrieved" in text
    assert "event: synthesis_token" in text
    assert "event: citations_ready" in text
    assert "event: done" in text


@pytest.mark.anyio
async def test_sse_query_stream_notebook_not_found(
    streaming_setup: tuple[Any, UUID, Chunk],
) -> None:
    app, _notebook_id, _chunk = streaming_setup
    missing_id = uuid4()
    query_payload = {
        "notebook_id": str(missing_id),
        "question": "What is quantum computing?",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/query/stream", json=query_payload)

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "event: error" in resp.text
    assert "not_found" in resp.text


def test_websocket_evidence_only_query(streaming_setup: tuple[Any, UUID, Chunk]) -> None:
    app, notebook_id, _chunk = streaming_setup
    client = TestClient(app)

    with client.websocket_connect("/ws/query") as websocket:
        query_payload = {
            "notebook_id": str(notebook_id),
            "question": "Retrieve evidence only",
            "synthesis": {
                "enabled": False,
            },
        }
        websocket.send_text(json.dumps(query_payload))

        events: list[dict[str, Any]] = []
        while True:
            msg = websocket.receive_text()
            event_obj = json.loads(msg)
            events.append(event_obj)
            if event_obj["event"] == StreamEventType.DONE:
                break

        event_names = [e["event"] for e in events]
        assert StreamEventType.RETRIEVAL_START in event_names
        assert StreamEventType.CHUNK_RETRIEVED in event_names
        assert StreamEventType.SYNTHESIS_TOKEN not in event_names
        assert StreamEventType.CITATIONS_READY in event_names
        assert StreamEventType.DONE in event_names


def test_websocket_invalid_doc_type_contract_error(
    streaming_setup: tuple[Any, UUID, Chunk],
) -> None:
    app, notebook_id, _chunk = streaming_setup
    client = TestClient(app)

    with client.websocket_connect("/ws/query") as websocket:
        query_payload = {
            "notebook_id": str(notebook_id),
            "question": "Testing invalid filter",
            "retrieval_config": {
                "filters": {
                    "doc_type": ["nonexistent_doc_type"],
                },
            },
        }
        websocket.send_text(json.dumps(query_payload))

        resp1 = json.loads(websocket.receive_text())
        assert resp1["event"] == StreamEventType.RETRIEVAL_START
        resp2 = json.loads(websocket.receive_text())
        assert resp2["event"] == StreamEventType.ERROR
        assert resp2["data"]["code"] == "contract_validation_error"


def test_stream_event_models() -> None:
    from mnemo_server.schemas.query import RetrievalMetadataResponse
    from mnemo_server.schemas.streaming import (
        ChunkRetrievedData,
        CitationsReadyData,
        DoneData,
        StreamErrorData,
        StreamEvent,
        StreamEventType,
        SynthesisTokenData,
    )

    ev_start = StreamEvent(event=StreamEventType.RETRIEVAL_START)
    assert ev_start.event == StreamEventType.RETRIEVAL_START
    assert json.loads(ev_start.model_dump_json())["event"] == "retrieval_start"

    ev_chunk = StreamEvent(
        event=StreamEventType.CHUNK_RETRIEVED,
        data=ChunkRetrievedData(chunk_id="chunk-123", score=0.95),
    )
    assert ev_chunk.data.chunk_id == "chunk-123"

    ev_token = StreamEvent(
        event=StreamEventType.SYNTHESIS_TOKEN,
        data=SynthesisTokenData(token="hello"),
    )
    assert ev_token.data.token == "hello"

    ev_cit = StreamEvent(
        event=StreamEventType.CITATIONS_READY,
        data=CitationsReadyData(citations=[]),
    )
    assert len(ev_cit.data.citations) == 0

    ev_done = StreamEvent(
        event=StreamEventType.DONE,
        data=DoneData(
            retrieval_metadata=RetrievalMetadataResponse(
                chunks_retrieved=1,
                chunks_used=1,
                retrieval_modes_used=["dense"],
                latency_ms=10,
            ),
            answer="Done answer",
        ),
    )
    assert ev_done.data.answer == "Done answer"

    ev_err = StreamEvent(
        event=StreamEventType.ERROR,
        data=StreamErrorData(code="test_err", message="Something broke"),
    )
    assert ev_err.data.code == "test_err"


@pytest.mark.anyio
async def test_streaming_service_invalid_mode(streaming_setup: tuple[Any, UUID, Chunk]) -> None:
    app, notebook_id, _chunk = streaming_setup
    query_payload = {
        "notebook_id": str(notebook_id),
        "question": "Testing invalid mode",
        "retrieval_config": {
            "modes": ["unsupported_mode"],
        },
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/query/stream", json=query_payload)

    assert resp.status_code == 422
