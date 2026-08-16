"""Unit and integration tests for Module 8.2 MCP Knowledge Tools."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import mcp.types as types
import pytest
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo.interfaces import (
    ContractValidationError,
    DependencyUnavailableError,
    NotFoundError,
    Page,
)
from mnemo.models import (
    Document,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    FrozenMetadata,
    Insight,
    InsightType,
    Note,
    Notebook,
    NoteOrigin,
    Session,
    Source,
)
from mnemo_server.mcp.server import create_mcp_server
from mnemo_server.mcp.tools import execute_mcp_tool, get_mcp_tools


def _make_mock_doc(doc_id: UUID, version_id: UUID, title: str) -> Document:
    """Construct a valid Document aggregate."""
    now = datetime.now(UTC)
    h = "a" * 64
    meta = DocumentMetadata(content_hash=h, title=title)
    version = DocumentVersion(
        version_id=version_id,
        document_id=doc_id,
        content_hash=h,
        metadata=meta,
        status=DocumentVersionStatus.CURRENT,
        created_at=now,
    )
    return Document(
        document_id=doc_id,
        versions=(version,),
        current_version_id=version_id,
        current_hash=h,
        status=DocumentStatus.INDEXED,
        created_at=now,
        updated_at=now,
    )


def _make_mock_engine() -> MagicMock:
    """Construct a mock KnowledgeEngine in READY state with mock storage."""
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    engine.storage = MagicMock()
    engine.registry = MagicMock()
    engine.embedding_provider = MagicMock()
    return engine


def test_mcp_tool_definitions() -> None:
    """Verify that get_mcp_tools returns the exact 6 authoritative MCP knowledge tools."""
    tools = get_mcp_tools()
    tool_names = [t.name for t in tools]

    expected_names = [
        "query_notebook",
        "search_all_notebooks",
        "list_notebooks",
        "get_notebook_summary",
        "get_source_insights",
        "get_timeline",
    ]

    assert tool_names == expected_names
    for tool in tools:
        assert tool.description
        schema = getattr(tool, "input_schema", getattr(tool, "inputSchema", None))
        assert schema
        assert schema.get("type") == "object"


@pytest.mark.anyio
async def test_mcp_tool_uninitialized_engine() -> None:
    """Verify that tool execution is rejected when engine is None or not READY."""
    with pytest.raises(DependencyUnavailableError):
        await execute_mcp_tool(None, "list_notebooks", {})

    unready_engine = MagicMock(spec=KnowledgeEngine)
    unready_engine.state = EngineState.UNINITIALIZED
    with pytest.raises(DependencyUnavailableError):
        await execute_mcp_tool(unready_engine, "list_notebooks", {})


@pytest.mark.anyio
async def test_mcp_unknown_tool() -> None:
    """Verify that unknown tool names raise ValueError."""
    engine = _make_mock_engine()
    with pytest.raises(ValueError, match="Unknown MCP tool"):
        await execute_mcp_tool(engine, "unsupported_tool", {})


@pytest.mark.anyio
async def test_mcp_list_notebooks() -> None:
    """Verify list_notebooks tool execution with source counts and pagination."""
    engine = _make_mock_engine()
    nb1_id = uuid4()
    nb2_id = uuid4()
    now = datetime.now(UTC)

    nb1 = Notebook(
        notebook_id=nb1_id,
        title="Research Notes",
        description="AI research",
        created_at=now,
        updated_at=now,
        metadata=FrozenMetadata({"tag": "ai"}),
    )
    nb2 = Notebook(
        notebook_id=nb2_id,
        title="Engineering Docs",
        description=None,
        created_at=now,
        updated_at=now,
        metadata=FrozenMetadata({}),
    )

    engine.storage.list_notebooks = AsyncMock(
        return_value=Page(items=(nb1, nb2), next_cursor="cursor_123")
    )
    engine.storage.list_sources = AsyncMock(
        side_effect=lambda notebook_id, limit, cursor: Page(
            items=(MagicMock(), MagicMock()) if notebook_id == nb1_id else (),
            next_cursor=None,
        )
    )

    contents = await execute_mcp_tool(engine, "list_notebooks", {"limit": 10})
    assert len(contents) == 1
    assert contents[0].type == "text"

    data = json.loads(contents[0].text)
    assert data["total"] == 2
    assert data["next_cursor"] == "cursor_123"
    assert len(data["notebooks"]) == 2
    assert data["notebooks"][0]["notebook_id"] == str(nb1_id)
    assert data["notebooks"][0]["source_count"] == 2
    assert data["notebooks"][0]["metadata"]["tag"] == "ai"
    assert data["notebooks"][1]["notebook_id"] == str(nb2_id)
    assert data["notebooks"][1]["source_count"] == 0

    # Test invalid limit
    with pytest.raises(ContractValidationError):
        await execute_mcp_tool(engine, "list_notebooks", {"limit": 200})


@pytest.mark.anyio
async def test_mcp_query_notebook_validation() -> None:
    """Verify input validation for query_notebook tool."""
    engine = _make_mock_engine()

    # Missing notebook_id
    with pytest.raises(ContractValidationError, match="notebook_id"):
        await execute_mcp_tool(engine, "query_notebook", {"question": "What is Mnemo?"})

    # Invalid UUID
    with pytest.raises(ContractValidationError, match="UUID"):
        await execute_mcp_tool(
            engine,
            "query_notebook",
            {"notebook_id": "invalid-uuid", "question": "What is Mnemo?"},
        )

    # Empty question
    with pytest.raises(ContractValidationError, match="question"):
        await execute_mcp_tool(
            engine,
            "query_notebook",
            {"notebook_id": str(uuid4()), "question": "   "},
        )

    # Invalid top_k
    with pytest.raises(ContractValidationError, match="top_k"):
        await execute_mcp_tool(
            engine,
            "query_notebook",
            {"notebook_id": str(uuid4()), "question": "test", "top_k": 0},
        )


@pytest.mark.anyio
async def test_mcp_query_notebook_execution() -> None:
    """Verify query_notebook happy path execution with grounded synthesis and citations."""
    engine = _make_mock_engine()
    nb_id = uuid4()
    chunk_id = uuid4()
    doc_id = uuid4()
    version_id = uuid4()

    mock_doc = _make_mock_doc(doc_id, version_id, "Architecture Doc")

    engine.storage.get_notebook = AsyncMock(
        return_value=Notebook(
            notebook_id=nb_id,
            title="Notebook 1",
            description=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            metadata=FrozenMetadata({}),
        )
    )
    engine.storage.get_document = AsyncMock(return_value=mock_doc)

    with (
        patch("mnemo_server.mcp.tools.QueryService") as mock_qs_cls,
        patch("mnemo_server.mcp.tools._get_token_counter"),
    ):
        mock_service = MagicMock()
        mock_qs_cls.return_value = mock_service

        from mnemo_server.schemas.query import (
            CitationResponse,
            QueryResponse,
            RetrievalMetadataResponse,
        )

        mock_service.execute_query = AsyncMock(
            return_value=QueryResponse(
                answer="Mnemo is a local-first knowledge engine [source:1].",
                citations=[
                    CitationResponse(
                        id=uuid4(),
                        chunk_id=str(chunk_id),
                        document_title="Architecture Doc",
                        page=1,
                        heading_path=["Introduction"],
                        quote="Mnemo is a local-first knowledge engine.",
                        confidence=1.0,
                    )
                ],
                retrieval_metadata=RetrievalMetadataResponse(
                    chunks_retrieved=5,
                    chunks_used=1,
                    retrieval_modes_used=["dense", "sparse"],
                    latency_ms=42,
                ),
            )
        )

        contents = await execute_mcp_tool(
            engine,
            "query_notebook",
            {
                "notebook_id": str(nb_id),
                "question": "What is Mnemo?",
                "top_k": 5,
                "synthesize": True,
            },
        )

        assert len(contents) == 1
        data = json.loads(contents[0].text)
        assert data["answer"] == "Mnemo is a local-first knowledge engine [source:1]."
        assert len(data["citations"]) == 1
        assert data["citations"][0]["chunk_id"] == str(chunk_id)
        assert data["citations"][0]["document_title"] == "Architecture Doc"
        assert data["retrieval_metadata"]["latency_ms"] == 42


@pytest.mark.anyio
async def test_mcp_search_all_notebooks() -> None:
    """Verify search_all_notebooks tool execution."""
    engine = _make_mock_engine()
    chunk_id = uuid4()
    doc_id = uuid4()
    version_id = uuid4()

    with patch("mnemo_server.mcp.tools.SearchService") as mock_ss_cls:
        mock_service = MagicMock()
        mock_ss_cls.return_value = mock_service

        from mnemo_server.schemas.search import SearchResponse, SearchResultItem

        mock_service.execute_search = AsyncMock(
            return_value=SearchResponse(
                results=[
                    SearchResultItem(
                        chunk_id=str(chunk_id),
                        document_id=str(doc_id),
                        version_id=str(version_id),
                        text="Search result content",
                        score=0.95,
                        rank=1,
                        retrieval_mode="hybrid",
                        heading_path=["Section 1"],
                        page_number=2,
                        metadata={"type": "spec"},
                    )
                ],
                total=1,
                latency_ms=15,
            )
        )

        contents = await execute_mcp_tool(
            engine,
            "search_all_notebooks",
            {"query": "knowledge graph", "top_k": 10},
        )

        assert len(contents) == 1
        data = json.loads(contents[0].text)
        assert data["total"] == 1
        assert data["latency_ms"] == 15
        assert len(data["results"]) == 1
        assert data["results"][0]["chunk_id"] == str(chunk_id)
        assert data["results"][0]["score"] == 0.95

    # Test validation error on empty query
    with pytest.raises(ContractValidationError, match="query"):
        await execute_mcp_tool(engine, "search_all_notebooks", {"query": ""})


@pytest.mark.anyio
async def test_mcp_get_notebook_summary() -> None:
    """Verify get_notebook_summary tool with populated and empty states."""
    engine = _make_mock_engine()
    nb_id = uuid4()
    ins_id = uuid4()
    src_id = uuid4()
    doc_id = uuid4()
    now = datetime.now(UTC)

    # 1. Populated state
    engine.storage.get_notebook = AsyncMock(
        return_value=Notebook(
            notebook_id=nb_id,
            title="Project Roadmap",
            description=None,
            created_at=now,
            updated_at=now,
            metadata=FrozenMetadata({}),
        )
    )

    summary_insight = Insight(
        insight_id=ins_id,
        notebook_id=nb_id,
        source_id=src_id,
        type=InsightType.SUMMARY,
        content="This notebook contains system architecture specifications.",
        confidence=1.0,
        created_at=now,
        metadata=FrozenMetadata({}),
    )

    source_obj = Source(
        source_id=src_id,
        notebook_id=nb_id,
        document_id=doc_id,
        created_at=now,
    )

    engine.storage.list_insights = AsyncMock(
        return_value=Page(items=(summary_insight,), next_cursor=None)
    )
    engine.storage.list_sources = AsyncMock(
        return_value=Page(items=(source_obj,), next_cursor=None)
    )

    doc_obj = _make_mock_doc(doc_id, uuid4(), "Spec.pdf")
    engine.storage.get_document = AsyncMock(return_value=doc_obj)

    contents = await execute_mcp_tool(engine, "get_notebook_summary", {"notebook_id": str(nb_id)})
    assert len(contents) == 1
    data = json.loads(contents[0].text)
    assert data["status"] == "ready"
    assert data["summary"] == "This notebook contains system architecture specifications."
    assert len(data["summaries"]) == 1
    assert len(data["sources"]) == 1
    assert data["sources"][0]["title"] == "Spec.pdf"

    # 2. Empty summaries state
    engine.storage.list_insights = AsyncMock(return_value=Page(items=(), next_cursor=None))
    contents_empty = await execute_mcp_tool(
        engine, "get_notebook_summary", {"notebook_id": str(nb_id)}
    )
    data_empty = json.loads(contents_empty[0].text)
    assert data_empty["status"] == "empty"
    assert data_empty["summary"] is None

    # 3. Not found notebook
    engine.storage.get_notebook = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await execute_mcp_tool(engine, "get_notebook_summary", {"notebook_id": str(nb_id)})


@pytest.mark.anyio
async def test_mcp_get_source_insights() -> None:
    """Verify get_source_insights tool with type filtering and missing source checks."""
    engine = _make_mock_engine()
    src_id = uuid4()
    nb_id = uuid4()
    doc_id = uuid4()
    ins1_id = uuid4()
    ins2_id = uuid4()
    now = datetime.now(UTC)

    source_obj = Source(
        source_id=src_id,
        notebook_id=nb_id,
        document_id=doc_id,
        created_at=now,
    )

    ins1 = Insight(
        insight_id=ins1_id,
        notebook_id=nb_id,
        source_id=src_id,
        type=InsightType.KEY_FACT,
        content="Mnemo uses SQLite for relational storage.",
        confidence=0.99,
        created_at=now,
        metadata=FrozenMetadata({"category": "storage"}),
    )

    ins2 = Insight(
        insight_id=ins2_id,
        notebook_id=nb_id,
        source_id=src_id,
        type=InsightType.CLAIM,
        content="Deploy Qdrant vector database.",
        confidence=0.95,
        created_at=now,
        metadata=FrozenMetadata({}),
    )

    engine.storage.get_source = AsyncMock(return_value=source_obj)
    engine.storage.list_insights = AsyncMock(
        return_value=Page(items=(ins1, ins2), next_cursor=None)
    )

    # 1. Fetch all insights for source
    contents = await execute_mcp_tool(engine, "get_source_insights", {"source_id": str(src_id)})
    assert len(contents) == 1
    data = json.loads(contents[0].text)
    assert data["source_id"] == str(src_id)
    assert data["total"] == 2
    assert data["insights"][0]["type"] == "key_fact"
    assert data["insights"][1]["type"] == "claim"

    # 2. Filter by insight_type = key_fact (or alias fact)
    contents_fact = await execute_mcp_tool(
        engine,
        "get_source_insights",
        {"source_id": str(src_id), "insight_type": "key_fact"},
    )
    data_fact = json.loads(contents_fact[0].text)
    assert data_fact["total"] == 1
    assert data_fact["insights"][0]["type"] == "key_fact"

    # 3. Invalid insight_type
    with pytest.raises(ContractValidationError, match="Invalid insight_type"):
        await execute_mcp_tool(
            engine,
            "get_source_insights",
            {"source_id": str(src_id), "insight_type": "invalid_type"},
        )

    # 4. Missing source
    engine.storage.get_source = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await execute_mcp_tool(engine, "get_source_insights", {"source_id": str(src_id)})


@pytest.mark.anyio
async def test_mcp_get_timeline() -> None:
    """Verify get_timeline tool returning chronologically sorted events."""
    engine = _make_mock_engine()
    nb_id = uuid4()
    src_id = uuid4()
    note_id = uuid4()
    sess_id = uuid4()
    doc_id = uuid4()

    t1 = datetime(2026, 8, 1, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 8, 1, 11, 0, 0, tzinfo=UTC)
    t3 = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)

    engine.storage.get_notebook = AsyncMock(
        return_value=Notebook(
            notebook_id=nb_id,
            title="Timeline Notebook",
            description=None,
            created_at=t1,
            updated_at=t3,
            metadata=FrozenMetadata({}),
        )
    )

    source_obj = Source(
        source_id=src_id,
        notebook_id=nb_id,
        document_id=doc_id,
        created_at=t1,
    )

    note_obj = Note(
        note_id=note_id,
        notebook_id=nb_id,
        title="Meeting Notes",
        content="Discussed Phase 8",
        origin=NoteOrigin.USER,
        created_at=t2,
        updated_at=t2,
        metadata=FrozenMetadata({}),
    )

    sess_obj = Session(
        session_id=sess_id,
        notebook_id=nb_id,
        title="Chat Session 1",
        created_at=t3,
        updated_at=t3,
        metadata=FrozenMetadata({}),
    )

    engine.storage.list_sources = AsyncMock(
        return_value=Page(items=(source_obj,), next_cursor=None)
    )
    engine.storage.list_notes = AsyncMock(return_value=Page(items=(note_obj,), next_cursor=None))
    engine.storage.list_sessions = AsyncMock(return_value=Page(items=(sess_obj,), next_cursor=None))

    contents = await execute_mcp_tool(engine, "get_timeline", {"notebook_id": str(nb_id)})
    assert len(contents) == 1
    data = json.loads(contents[0].text)
    assert data["notebook_id"] == str(nb_id)
    assert data["total"] == 3

    # Most recent first: session (t3), note (t2), source (t1)
    assert data["events"][0]["event_type"] == "session_started"
    assert data["events"][0]["event_id"] == str(sess_id)
    assert data["events"][1]["event_type"] == "note_created"
    assert data["events"][1]["event_id"] == str(note_id)
    assert data["events"][2]["event_type"] == "source_added"
    assert data["events"][2]["event_id"] == str(src_id)


@pytest.mark.anyio
async def test_mcp_server_tool_listing_and_dispatch() -> None:
    """Verify that create_mcp_server exposes the 6 tools and routes call_tool correctly."""
    engine = _make_mock_engine()
    server = create_mcp_server(engine)

    # 1. Test tool discovery
    list_tools_handler = server.request_handlers[types.ListToolsRequest]
    assert list_tools_handler is not None

    tools_res = await list_tools_handler(types.ListToolsRequest(method="tools/list"))
    tools_result = getattr(tools_res, "root", tools_res)
    assert len(tools_result.tools) == 6

    # 2. Test call_tool dispatch
    call_tool_handler = server.request_handlers[types.CallToolRequest]
    assert call_tool_handler is not None

    engine.storage.list_notebooks = AsyncMock(return_value=Page(items=(), next_cursor=None))

    call_req = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name="list_notebooks", arguments={"limit": 10}),
    )

    call_res = await call_tool_handler(call_req)
    call_result = getattr(call_res, "root", call_res)
    assert len(call_result.content) == 1
    first_content = call_result.content[0]
    assert isinstance(first_content, types.TextContent)
    data = json.loads(first_content.text)
    assert data["total"] == 0
