"""Unit tests for FastAPI app creation, lifespan, CORS, and health check."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from mnemo import __version__
from mnemo.engine import EngineInitializationError, EngineState, KnowledgeEngine
from mnemo.interfaces import ConflictError, ContractValidationError, NotFoundError
from mnemo.models import Notebook, Session, Turn, TurnRole
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig
from mnemo_server.schemas.final_qa import FinalQARequestBody
from mnemo_server.schemas.query import QueryFilters
from mnemo_server.services.final_qa import FinalQAService, _filters


def _make_mock_engine(
    *,
    initialize_side_effect: Exception | None = None,
    shutdown_side_effect: Exception | None = None,
) -> MagicMock:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.UNINITIALIZED
    engine.version = __version__

    storage_mock = MagicMock()
    storage_mock.health_check = AsyncMock(return_value=())
    engine.storage = storage_mock

    emb_mock = MagicMock()
    emb_mock.health_check = AsyncMock(
        return_value=MagicMock(
            component="emb", healthy=True, checked_at=datetime.now(UTC), detail=None
        )
    )
    engine.embedding_provider = emb_mock

    llm_mock = MagicMock()
    llm_mock.health_check = AsyncMock(
        return_value=MagicMock(
            component="llm", healthy=True, checked_at=datetime.now(UTC), detail=None
        )
    )
    engine.llm = MagicMock(return_value=llm_mock)

    async def mock_initialize() -> None:
        if initialize_side_effect:
            engine.state = EngineState.FAILED
            raise initialize_side_effect
        engine.state = EngineState.READY

    async def mock_shutdown() -> None:
        if shutdown_side_effect:
            raise shutdown_side_effect
        engine.state = EngineState.STOPPED

    engine.initialize = AsyncMock(side_effect=mock_initialize)
    engine.shutdown = AsyncMock(side_effect=mock_shutdown)
    return engine


@pytest.mark.anyio
async def test_app_lifespan_success() -> None:
    mock_engine = _make_mock_engine()
    config = ServerConfig(cors_origins=("https://app.mnemo.local",))
    app = create_app(
        server_config=config,
        engine=mock_engine,
        provision_tokenizer_on_startup=False,
    )

    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        # Verify engine was initialized
        mock_engine.initialize.assert_awaited_once()
        assert app.state.engine is mock_engine
        assert app.state.engine.state is EngineState.READY
        assert app.state.server_config is config

        # Test /health and /v1/health
        resp1 = await client.get("/health")
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["status"] == "ok"
        assert data1["version"] == __version__
        assert data1["engine_state"] == "ready"

        resp2 = await client.get("/v1/health")
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "ok"

    # After lifespan exit, engine shutdown must be called and state cleared
    mock_engine.shutdown.assert_awaited_once()
    assert getattr(app.state, "engine", None) is None


@pytest.mark.anyio
async def test_app_lifespan_initialization_failure() -> None:
    mock_engine = _make_mock_engine(
        initialize_side_effect=EngineInitializationError("Backend unavailable")
    )
    app = create_app(engine=mock_engine, provision_tokenizer_on_startup=False)

    with pytest.raises(EngineInitializationError):
        async with app.router.lifespan_context(app):
            pass

    assert getattr(app.state, "engine", None) is None


@pytest.mark.anyio
async def test_app_lifespan_loads_repository_toml_when_no_config_is_injected() -> None:
    """The executable ASGI application honors the repository configuration file."""
    from unittest.mock import patch

    mock_engine = _make_mock_engine()
    config_from_file = MagicMock()
    with (
        patch("mnemo_server.app.os.path.exists", return_value=True),
        patch("mnemo_server.app.MnemoConfig.from_file", return_value=config_from_file) as loader,
        patch("mnemo_server.app.KnowledgeEngine", return_value=mock_engine) as engine_factory,
    ):
        app = create_app(provision_tokenizer_on_startup=False)
        async with app.router.lifespan_context(app):
            loader.assert_called_once_with("mnemo.toml")
            engine_factory.assert_called_once_with(config_from_file, final_qa_components=None)


@pytest.mark.anyio
async def test_app_cors_headers() -> None:
    mock_engine = _make_mock_engine()
    config = ServerConfig(cors_origins=("https://allowed.example.com",))
    app = create_app(
        server_config=config,
        engine=mock_engine,
        provision_tokenizer_on_startup=False,
    )

    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        # Request with Origin header
        resp = await client.get(
            "/health",
            headers={"Origin": "https://allowed.example.com"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "https://allowed.example.com"
        assert resp.headers.get("access-control-allow-credentials") == "true"

        # Preflight OPTIONS request
        options_resp = await client.options(
            "/health",
            headers={
                "Origin": "https://allowed.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert options_resp.status_code == 200
        assert (
            options_resp.headers.get("access-control-allow-origin") == "https://allowed.example.com"
        )


def test_main_run() -> None:
    from unittest.mock import patch

    from mnemo_server import main

    with patch("uvicorn.run") as mock_uvicorn_run:
        main.run()
        mock_uvicorn_run.assert_called_once_with(
            "mnemo_server.main:app",
            host="127.0.0.1",
            port=8000,
            log_level="info",
            reload=False,
            workers=1,
        )


@pytest.mark.anyio
async def test_final_qa_service_is_a_thin_adapter_and_marks_new_then_replay() -> None:
    notebook_id, session_id, user_turn_id, assistant_turn_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    now = datetime.now(UTC)
    notebook = Notebook(
        notebook_id=notebook_id,
        title="Test",
        created_at=now,
        updated_at=now,
    )
    user = Turn(
        turn_id=user_turn_id,
        session_id=session_id,
        sequence=0,
        role=TurnRole.USER,
        content="What is duty?",
        created_at=now,
    )
    session = Session(
        session_id=session_id,
        notebook_id=notebook_id,
        created_at=now,
        updated_at=now,
        turns=(user,),
    )
    engine = _make_mock_engine()
    engine.storage.get_notebook = AsyncMock(return_value=notebook)
    engine.storage.get_session = AsyncMock(return_value=session)
    engine.storage.list_sources = AsyncMock(return_value=MagicMock(items=()))
    engine.storage.get_final_qa_execution = AsyncMock(return_value=None)
    engine.final_qa.execute = AsyncMock(
        return_value=MagicMock(status=MagicMock(value="no_context"), answer=None, citations=())
    )
    body = FinalQARequestBody(
        session_id=session_id,
        user_turn_id=user_turn_id,
        assistant_turn_id=assistant_turn_id,
    )
    first = await FinalQAService(engine).execute(notebook_id, body)
    assert first.execution == "new" and first.answer is None
    request = engine.final_qa.execute.await_args.args[0]
    assert request.query == user.content and request.metadata_filter.notebook_id == notebook_id
    engine.storage.get_final_qa_execution.return_value = MagicMock()
    replay = await FinalQAService(engine).execute(notebook_id, body)
    assert replay.execution == "replay"

    assistant = Turn(
        turn_id=assistant_turn_id,
        session_id=session_id,
        sequence=1,
        role=TurnRole.ASSISTANT,
        content="Persisted answer [source:1]",
        created_at=now,
    )
    engine.storage.get_session.return_value = Session(
        session_id=session_id,
        notebook_id=notebook_id,
        created_at=now,
        updated_at=now,
        turns=(user, assistant),
    )
    replay_with_persisted_tail = await FinalQAService(engine).execute(notebook_id, body)
    assert replay_with_persisted_tail.execution == "replay"


@pytest.mark.anyio
async def test_final_qa_service_rejects_missing_and_incompatible_persisted_state() -> None:
    """The ADR-0055 adapter validates persisted server-owned identities before delegation."""
    notebook_id, session_id, user_turn_id, assistant_turn_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    body = FinalQARequestBody(
        session_id=session_id,
        user_turn_id=user_turn_id,
        assistant_turn_id=assistant_turn_id,
    )
    engine = _make_mock_engine()
    service = FinalQAService(engine)
    engine.storage.get_notebook = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError, match="Notebook"):
        await service.execute(notebook_id, body)

    now = datetime.now(UTC)
    notebook = Notebook(notebook_id=notebook_id, title="Test", created_at=now, updated_at=now)
    engine.storage.get_notebook = AsyncMock(return_value=notebook)
    engine.storage.get_session = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError, match="Session"):
        await service.execute(notebook_id, body)

    foreign = Session(
        session_id=session_id,
        notebook_id=uuid4(),
        created_at=now,
        updated_at=now,
        turns=(),
    )
    engine.storage.get_session = AsyncMock(return_value=foreign)
    with pytest.raises(ConflictError, match="does not belong"):
        await service.execute(notebook_id, body)

    session = Session(
        session_id=session_id,
        notebook_id=notebook_id,
        created_at=now,
        updated_at=now,
        turns=(),
    )
    engine.storage.get_session = AsyncMock(return_value=session)
    with pytest.raises(NotFoundError, match="User turn"):
        await service.execute(notebook_id, body)
    engine.final_qa.execute.assert_not_called()


@pytest.mark.anyio
async def test_final_qa_service_requires_final_user_turn_and_valid_filters() -> None:
    notebook_id, session_id, user_turn_id, assistant_turn_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    now = datetime.now(UTC)
    notebook = Notebook(notebook_id=notebook_id, title="Test", created_at=now, updated_at=now)
    assistant = Turn(
        turn_id=user_turn_id,
        session_id=session_id,
        sequence=0,
        role=TurnRole.ASSISTANT,
        content="not a query",
        created_at=now,
    )
    session = Session(
        session_id=session_id,
        notebook_id=notebook_id,
        created_at=now,
        updated_at=now,
        turns=(assistant,),
    )
    engine = _make_mock_engine()
    engine.storage.get_notebook = AsyncMock(return_value=notebook)
    engine.storage.get_session = AsyncMock(return_value=session)
    service = FinalQAService(engine)
    body = FinalQARequestBody(
        session_id=session_id,
        user_turn_id=user_turn_id,
        assistant_turn_id=assistant_turn_id,
    )
    with pytest.raises(ContractValidationError, match="final persisted"):
        await service.execute(notebook_id, body)

    user = Turn(
        turn_id=user_turn_id,
        session_id=session_id,
        sequence=0,
        role=TurnRole.USER,
        content="Question",
        created_at=now,
    )
    engine.storage.get_session = AsyncMock(
        return_value=Session(
            session_id=session_id,
            notebook_id=notebook_id,
            created_at=now,
            updated_at=now,
            turns=(user,),
        )
    )
    with pytest.raises(ContractValidationError, match="document type"):
        _filters(notebook_id, QueryFilters.model_construct(doc_type=["not-a-document-type"]))
    engine.final_qa.execute.assert_not_called()


@pytest.mark.anyio
async def test_final_qa_service_derives_version_labels_and_reports_missing_documents() -> None:
    """Titles are derived only from canonical document-version metadata."""
    notebook_id, document_id, version_id = uuid4(), uuid4(), uuid4()
    engine = _make_mock_engine()
    source = MagicMock(document_id=document_id)
    engine.storage.list_sources = AsyncMock(return_value=MagicMock(items=(source,)))
    titled_version = MagicMock(version_id=version_id, metadata=MagicMock(title="A generic title"))
    untitled_version = MagicMock(version_id=uuid4(), metadata=MagicMock(title=None))
    engine.storage.get_document = AsyncMock(
        return_value=MagicMock(document_id=document_id, versions=(titled_version, untitled_version))
    )
    labels, titles = await FinalQAService(engine)._labels(notebook_id)
    assert [(label.document_id, label.version_id, label.title) for label in labels] == [
        (document_id, version_id, "A generic title")
    ]
    assert titles == ("A generic title",)
    engine.storage.get_document = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError, match="Document"):
        await FinalQAService(engine)._labels(notebook_id)
