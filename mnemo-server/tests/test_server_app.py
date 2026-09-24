"""Unit tests for FastAPI app creation, lifespan, CORS, and health check."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from mnemo import MnemoConfig, __version__
from mnemo.engine import EngineInitializationError, EngineState, KnowledgeEngine
from mnemo.interfaces import ConflictError, ContractValidationError, NotFoundError
from mnemo.models import Notebook, Session, Turn, TurnRole
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig
from mnemo_server.dependencies import require_mutable_workspace
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


def _write_core_config(root: Path) -> MnemoConfig:
    config_path = root / "mnemo.toml"
    config_path.write_text(
        """
[storage.filesystem]
enabled = true
root = "certified/blobs"
[storage.sqlite]
enabled = true
path = "certified/corpus.db"
[storage.qdrant]
enabled = false
[storage.surrealdb]
enabled = false
[plugins]
directory = "plugins"
[llm.planner]
provider = "ollama"
model = "planner"
[llm.synthesizer]
provider = "ollama"
model = "synthesizer"
[llm.extractor]
provider = "ollama"
model = "extractor"
[llm.classifier]
provider = "ollama"
model = "classifier"
[embedding]
provider = "ollama"
model = "embedder"
dimensions = 8
[reranker]
provider = "v2-owned-pass-through"
model = "none"
""",
        encoding="utf-8",
    )
    return MnemoConfig.from_file(config_path)


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
async def test_app_lifespan_rejects_engine_that_does_not_reach_ready() -> None:
    """A completed initializer may not publish an engine in a non-READY state."""
    engine = _make_mock_engine()
    engine.initialize = AsyncMock()
    engine.state = EngineState.INITIALIZING
    app = create_app(engine=engine, provision_tokenizer_on_startup=False)
    with pytest.raises(RuntimeError, match="failed to reach READY"):
        async with app.router.lifespan_context(app):
            pass


@pytest.mark.anyio
async def test_production_without_workspace_is_read_only_for_mutation_routes() -> None:
    engine = _make_mock_engine()
    engine.config = MagicMock()
    engine.certified_read_only = True
    engine.storage.upsert_notebook = AsyncMock()
    api_key = "workspace-boundary-test-key"
    config = ServerConfig(
        production_mode=True,
        auth_mode="api-key",
        api_key=api_key,
        delivery_cursor_secret="w" * 32,
    )
    app = create_app(
        server_config=config,
        engine=engine,
        provision_tokenizer_on_startup=False,
    )

    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.post(
            "/v1/notebooks",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"title": "must not persist"},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "contract.dependency_unavailable"
    engine.storage.upsert_notebook.assert_not_awaited()


@pytest.mark.anyio
async def test_production_rejects_injected_writable_certified_engine() -> None:
    engine = _make_mock_engine()
    engine.config = MagicMock()
    engine.certified_read_only = False
    app = create_app(
        server_config=ServerConfig(
            production_mode=True,
            delivery_cursor_secret="w" * 32,
        ),
        engine=engine,
        provision_tokenizer_on_startup=False,
    )

    with pytest.raises(RuntimeError, match="UNSAFE_INJECTED_PRODUCTION_STORAGE"):
        async with app.router.lifespan_context(app):
            pass

    engine.initialize.assert_not_awaited()


@pytest.mark.anyio
async def test_rejected_workspace_startup_creates_no_storage_artifacts(tmp_path: Path) -> None:
    application = tmp_path / "application"
    application.mkdir()
    core_config = _write_core_config(application)
    engine = _make_mock_engine()
    engine.config = core_config
    engine.certified_read_only = True
    app = create_app(
        server_config=ServerConfig(
            production_mode=True,
            delivery_cursor_secret="w" * 32,
            mutable_workspace_root=core_config.storage.sqlite.path.parent,
        ),
        mnemo_config=core_config,
        engine=engine,
        provision_tokenizer_on_startup=False,
    )

    async with app.router.lifespan_context(app):
        assert app.state.mutable_workspace_decision.mutable is False

    governed = core_config.storage.sqlite.path.parent
    assert not governed.exists()
    assert not core_config.storage.sqlite.path.exists()
    assert not Path(f"{core_config.storage.sqlite.path}-wal").exists()
    assert not Path(f"{core_config.storage.sqlite.path}-shm").exists()
    assert not (governed / "embedding-cache.db").exists()


@pytest.mark.anyio
async def test_valid_production_workspace_binds_mutations_to_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = tmp_path / "application"
    application.mkdir()
    core_config = _write_core_config(application)
    core_config.storage.sqlite.path.parent.mkdir()
    core_config.storage.sqlite.path.write_bytes(b"synthetic-certified-http-database")
    core_config.storage.filesystem.root.mkdir(parents=True)
    certified_blob = core_config.storage.filesystem.root / "manifest.json"
    certified_blob.write_bytes(b"synthetic-certified-http-blob")
    database_hash = hashlib.sha256(core_config.storage.sqlite.path.read_bytes()).hexdigest()
    blob_hash = hashlib.sha256(certified_blob.read_bytes()).hexdigest()
    workspace = tmp_path / "operator-workspace"
    engine = _make_mock_engine()
    engine.storage.upsert_notebook = AsyncMock()
    engine_factory = MagicMock(return_value=engine)
    monkeypatch.setattr("mnemo_server.app.KnowledgeEngine", engine_factory)
    api_key = "workspace-boundary-test-key"
    config = ServerConfig(
        production_mode=True,
        auth_mode="api-key",
        api_key=api_key,
        delivery_cursor_secret="w" * 32,
        mutable_workspace_root=workspace,
    )
    app = create_app(
        server_config=config,
        mnemo_config=core_config,
        provision_tokenizer_on_startup=False,
    )

    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.post(
            "/v1/notebooks",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "title": "workspace notebook",
                "workspace_root": str(application / "certified"),
                "database_path": str(core_config.storage.sqlite.path),
                "storage_role": "CERTIFIED_CORPUS",
            },
        )

    runtime_config = engine_factory.call_args.args[0]
    assert runtime_config.storage.sqlite.path == workspace / "workspace.db"
    assert runtime_config.storage.filesystem.root == workspace / "blobs"
    assert engine_factory.call_args.kwargs["embedding_cache_path"] == (
        workspace / "caches" / "embedding-cache.db"
    )
    assert response.status_code == 201
    engine.storage.upsert_notebook.assert_awaited_once()
    assert hashlib.sha256(core_config.storage.sqlite.path.read_bytes()).hexdigest() == database_hash
    assert hashlib.sha256(certified_blob.read_bytes()).hexdigest() == blob_hash
    assert not Path(f"{core_config.storage.sqlite.path}-wal").exists()
    assert not Path(f"{core_config.storage.sqlite.path}-shm").exists()


def test_every_workspace_mutation_route_is_gated() -> None:
    from mnemo_server.routers import (
        notebooks_router,
        notes_router,
        sessions_router,
        sources_router,
    )

    expected = {
        ("POST", "/v1/notebooks"),
        ("PATCH", "/v1/notebooks/{notebook_id}"),
        ("DELETE", "/v1/notebooks/{notebook_id}"),
        ("POST", "/v1/notebooks/{notebook_id}/sources"),
        ("DELETE", "/v1/notebooks/{notebook_id}/sources/{source_id}"),
        ("POST", "/v1/notebooks/{notebook_id}/notes"),
        ("PATCH", "/v1/notebooks/{notebook_id}/notes/{note_id}"),
        ("DELETE", "/v1/notebooks/{notebook_id}/notes/{note_id}"),
        ("POST", "/v1/notebooks/{notebook_id}/sessions"),
        ("POST", "/v1/notebooks/{notebook_id}/sessions/{session_id}/turns"),
        ("DELETE", "/v1/notebooks/{notebook_id}/sessions/{session_id}"),
    }
    actual: set[tuple[str, str]] = set()
    for router in (notebooks_router, sources_router, notes_router, sessions_router):
        for route in router.routes:
            dependencies = getattr(route, "dependencies", ())
            if any(item.dependency is require_mutable_workspace for item in dependencies):
                actual.update((method, f"/v1{route.path}") for method in route.methods)
    assert actual == expected


@pytest.mark.anyio
async def test_app_lifespan_installs_and_closes_governed_v2_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The V2 application path publishes readiness, activation authority, and closes cleanly."""
    engine = _make_mock_engine()
    engine.config = MagicMock()
    engine.certified_read_only = True
    monkeypatch.setattr(
        "mnemo_server.services.production_runtime_binding.resolve_certified_production_binding",
        lambda **_kwargs: (engine.config, SimpleNamespace(binding_id="synthetic-test-binding")),
    )
    monkeypatch.setattr(
        "mnemo_server.services.production_runtime_binding.record_certified_transport_startup",
        lambda **_kwargs: tmp_path / "synthetic-observation.json",
    )
    readiness_evidence = object()
    readiness = object()
    installed = SimpleNamespace(
        exposure_snapshot=object(),
        close=AsyncMock(),
        reranker_activation=SimpleNamespace(activate=AsyncMock()),
    )
    authority = object()
    builder = MagicMock()
    builder.build = AsyncMock(return_value=(readiness_evidence, readiness))
    monkeypatch.setattr(
        "mnemo_server.services.production_store_readiness.ProductionV2ReadinessEvidenceBuilderV1",
        MagicMock(return_value=builder),
    )
    installer = AsyncMock(return_value=installed)
    monkeypatch.setattr(
        "mnemo_server.services.full_multilingual_v2_startup.install_production_full_multilingual_v2",
        installer,
    )
    restore = AsyncMock(return_value=authority)
    monkeypatch.setattr(
        "mnemo_server.services.durable_reranker_activation.restore_production_reranker_activation",
        restore,
    )
    config = ServerConfig(
        production_mode=True,
        auth_mode="api-key",
        api_key="test-key",
        delivery_cursor_secret="x" * 32,
        full_multilingual_v2_enabled=True,
        full_multilingual_v2_model_cache=tmp_path / "models",
        final_qa_operational_store_path=tmp_path / "operational.db",
        mcp_stdio_principal_subject="stdio",
    )
    app = create_app(
        server_config=config,
        engine=engine,
        provision_tokenizer_on_startup=False,
    )
    async with app.router.lifespan_context(app):
        assert app.state.full_multilingual_v2_runtime is installed
        assert app.state.full_multilingual_v2_readiness is readiness_evidence
        assert app.state.reranker_activation_authority is authority
    installed.close.assert_awaited_once()
    restore.assert_awaited_once()


@pytest.mark.anyio
async def test_app_lifespan_swallows_shutdown_failure() -> None:
    """Shutdown errors are logged while the published engine reference is always cleared."""
    engine = _make_mock_engine(shutdown_side_effect=RuntimeError("shutdown failed"))
    app = create_app(engine=engine, provision_tokenizer_on_startup=False)
    async with app.router.lifespan_context(app):
        assert app.state.engine is engine
    assert app.state.engine is None


@pytest.mark.anyio
async def test_app_lifespan_loads_repository_toml_when_no_config_is_injected() -> None:
    """The executable ASGI application honors the repository configuration file."""
    from unittest.mock import patch

    mock_engine = _make_mock_engine()
    config_from_file = MagicMock()
    with (
        patch(
            "mnemo_server.app.resolve_mnemo_runtime_config",
            return_value=config_from_file,
        ) as loader,
        patch("mnemo_server.app.KnowledgeEngine", return_value=mock_engine) as engine_factory,
    ):
        app = create_app(provision_tokenizer_on_startup=False)
        async with app.router.lifespan_context(app):
            loader.assert_called_once_with(None)
        engine_factory.assert_called_once()
        assert engine_factory.call_args.args == (config_from_file,)
        assert engine_factory.call_args.kwargs["final_qa_components"] is None
        assert engine_factory.call_args.kwargs["advanced_retrieval_cursor_codec"] is not None


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
