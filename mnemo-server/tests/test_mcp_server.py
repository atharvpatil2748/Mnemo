"""Unit and protocol integration tests for Mnemo MCP Server Core (Module 8.1)."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import mcp.types as types
import pytest
from mcp.client.session import ClientSession
from mnemo import EngineState, KnowledgeEngine, MnemoConfig, __version__
from mnemo_server.config import ServerConfig
from mnemo_server.mcp.server import (
    _install_v2_if_enabled,
    configure_stderr_logging,
    create_mcp_server,
    run_stdio_server,
)


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
async def test_certified_stdio_rejects_fork_before_tool_exposure(tmp_path: Path) -> None:
    """A synthetic historical profile cannot reach the MCP protocol stream."""
    config = ServerConfig(
        production_mode=True,
        full_multilingual_v2_enabled=True,
        full_multilingual_v2_reranker_mode="BGE_V2_M3",
        full_multilingual_v2_model_cache=tmp_path / "models",
        reranker_activation_state_path=tmp_path / "activation.json",
        reranker_activation_operator_subject="operator",
        final_qa_operational_store_path=tmp_path / "finalqa.db",
        mcp_stdio_principal_subject="stdio",
        auth_mode="api-key",
        api_key="synthetic-key",
        delivery_cursor_secret="x" * 32,
    )
    with (
        patch("mnemo_server.mcp.server.stdio_server") as stream,
        pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"),
    ):
        await run_stdio_server(config=config, mnemo_config=_write_core_config(tmp_path))
    stream.assert_not_called()
    assert not (tmp_path / "activation.json").exists()
    assert not (tmp_path / "finalqa.db").exists()


@pytest.mark.anyio
async def test_certified_stdio_records_binding_only_after_transport_starts(
    tmp_path: Path,
) -> None:
    """The actual stdio startup path records its server-owned binding after readiness."""
    core_config = _write_core_config(tmp_path)
    config = ServerConfig(
        production_mode=True,
        full_multilingual_v2_enabled=True,
        full_multilingual_v2_reranker_mode="BGE_V2_M3",
        full_multilingual_v2_model_cache=tmp_path / "models",
        final_qa_operational_store_path=tmp_path / "operational.db",
        mcp_stdio_principal_subject="stdio",
        auth_mode="api-key",
        api_key="synthetic-key",
        delivery_cursor_secret="x" * 32,
    )
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    engine.certified_read_only = True
    engine.shutdown = AsyncMock()
    binding = SimpleNamespace(binding_id="synthetic-binding")
    installed = SimpleNamespace(close=AsyncMock())
    with (
        patch(
            "mnemo_server.services.production_runtime_binding.resolve_certified_production_binding",
            return_value=(core_config, binding),
        ),
        patch(
            "mnemo_server.services.production_runtime_binding.record_certified_transport_startup"
        ) as record,
        patch("mnemo_server.mcp.server._install_v2_if_enabled", new_callable=AsyncMock) as install,
        patch("mnemo_server.mcp.server.stdio_server") as stdio,
        patch("mnemo_server.mcp.server.Server.run", new_callable=AsyncMock),
    ):
        install.return_value = installed
        stdio.return_value.__aenter__.return_value = (MagicMock(), MagicMock())
        await run_stdio_server(config=config, mnemo_config=core_config, engine=engine)
    assert record.call_args.kwargs["binding"] is binding
    assert record.call_args.kwargs["transport"] == "mcp_stdio"
    installed.close.assert_awaited_once()


def test_create_mcp_server_metadata() -> None:
    """Server exposes canonical name and package version."""
    server = create_mcp_server()
    assert server.name == "mnemo-mcp"
    assert server.version == __version__

    options = server.create_initialization_options()
    assert options.capabilities.tools is not None
    assert (
        getattr(
            options.capabilities.tools,
            "list_changed",
            getattr(options.capabilities.tools, "listChanged", None),
        )
        is False
    )
    assert options.server_name == "mnemo-mcp"
    assert options.server_version == __version__

    configured = ServerConfig(max_delivery_response_bytes=3210)
    configured_server = create_mcp_server(config=configured)
    assert configured_server._config is configured


@pytest.mark.anyio
async def test_mcp_v2_installer_enforces_readiness_and_activation_authority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """MCP startup owns the same governed V2 installation boundary as HTTP startup."""
    engine = MagicMock(spec=KnowledgeEngine)
    engine.config.storage.sqlite.path = tmp_path / "production.db"
    core_config = MagicMock()
    assert await _install_v2_if_enabled(engine, ServerConfig(), core_config) is None

    config = ServerConfig(
        production_mode=True,
        auth_mode="api-key",
        api_key="key",
        delivery_cursor_secret="x" * 32,
        full_multilingual_v2_enabled=True,
        full_multilingual_v2_model_cache=tmp_path / "models",
        final_qa_operational_store_path=tmp_path / "operational.db",
        mcp_stdio_principal_subject="stdio",
    )
    builder = MagicMock()
    builder.build = AsyncMock(return_value=(object(), object()))
    monkeypatch.setattr(
        "mnemo_server.services.production_store_readiness.ProductionV2ReadinessEvidenceBuilderV1",
        MagicMock(return_value=builder),
    )
    installed = SimpleNamespace(
        close=AsyncMock(), reranker_activation=SimpleNamespace(activate=AsyncMock())
    )
    installer = AsyncMock(return_value=installed)
    monkeypatch.setattr(
        "mnemo_server.services.full_multilingual_v2_startup.install_production_full_multilingual_v2",
        installer,
    )
    restore = AsyncMock()
    monkeypatch.setattr(
        "mnemo_server.services.durable_reranker_activation.restore_production_reranker_activation",
        restore,
    )
    assert await _install_v2_if_enabled(engine, config, core_config) is installed
    installer.assert_awaited_once()
    restore.assert_awaited_once()
    conflicting = config.model_copy(
        update={"reranker_activation_state_path": tmp_path / "activation.json"}
    )
    with pytest.raises(RuntimeError, match="COMPETING"):
        await _install_v2_if_enabled(engine, conflicting, core_config, object())


@pytest.mark.anyio
async def test_mcp_server_protocol_handshake() -> None:
    """A real MCP ClientSession connects, initializes, and enumerates capabilities."""
    server = create_mcp_server()
    init_opts = server.create_initialization_options()

    client_to_server_send, client_to_server_recv = anyio.create_memory_object_stream(10)
    server_to_client_send, server_to_client_recv = anyio.create_memory_object_stream(10)

    async with anyio.create_task_group() as tg:

        async def run_server() -> None:
            await server.run(client_to_server_recv, server_to_client_send, init_opts)

        tg.start_soon(run_server)

        async with ClientSession(server_to_client_recv, client_to_server_send) as session:
            init_res = await session.initialize()
            info = getattr(init_res, "server_info", getattr(init_res, "serverInfo", None))
            assert info.name == "mnemo-mcp"
            assert info.version == __version__

            # The six frozen tools remain present beside four additive delivery tools.
            tools_res = await session.list_tools()
            assert len(tools_res.tools) == 14
            tool_names = [t.name for t in tools_res.tools]
            assert "query_notebook" in tool_names
            assert "search_all_notebooks" in tool_names
            assert "list_notebooks" in tool_names
            assert "get_notebook_summary" in tool_names
            assert "get_source_insights" in tool_names
            assert "get_timeline" in tool_names

            # Prompts and resources
            prompts_res = await session.list_prompts()
            assert prompts_res.prompts == []

            resources_res = await session.list_resources()
            assert [str(item.uri) for item in resources_res.resources] == ["mnemo://capabilities"]

            tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_mcp_server_call_unknown_tool_returns_error_result() -> None:
    """Tool invocation returns isError=True CallToolResult for unknown tools."""
    mock_engine = MagicMock(spec=KnowledgeEngine)
    mock_engine.state = EngineState.READY
    server = create_mcp_server(mock_engine)
    handler = server.request_handlers[types.CallToolRequest]
    assert handler is not None

    req = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name="non_existent_tool", arguments={}),
    )
    call_res = await handler(req)
    result = getattr(call_res, "root", call_res)
    assert isinstance(result, types.CallToolResult)
    is_err = getattr(result, "isError", getattr(result, "is_error", False))
    assert is_err is True
    assert len(result.content) == 1
    assert "Unknown MCP tool" in result.content[0].text


@pytest.mark.anyio
async def test_run_stdio_server_lifecycle(tmp_path: Path) -> None:
    """run_stdio_server initializes and shuts down engine cleanly."""
    mock_engine = MagicMock(spec=KnowledgeEngine)
    mock_engine.state = EngineState.UNINITIALIZED
    mock_engine.initialize = AsyncMock()
    mock_engine.shutdown = AsyncMock()

    config = ServerConfig(log_level="debug")

    with patch("mnemo_server.mcp.server.stdio_server") as mock_stdio:
        # Mock stdio_server context manager yielding dummy streams
        mock_read = MagicMock()
        mock_write = MagicMock()

        @patch("mnemo_server.mcp.server.Server.run", new_callable=AsyncMock)
        async def _run_test(mock_run: AsyncMock) -> None:
            mock_stdio.return_value.__aenter__.return_value = (mock_read, mock_write)
            mock_stdio.return_value.__aexit__.return_value = False

            # Set mock_engine state to READY after initialize
            async def _init() -> None:
                mock_engine.state = EngineState.READY

            mock_engine.initialize.side_effect = _init

            await run_stdio_server(
                config=config, engine=mock_engine, mnemo_config=_write_core_config(tmp_path)
            )

            assert mock_engine.initialize.called
            assert mock_run.called

        await _run_test()


@pytest.mark.anyio
async def test_production_stdio_binds_workspace_and_preserves_certified_artifacts(
    tmp_path: Path,
) -> None:
    application = tmp_path / "application"
    application.mkdir()
    core_config = _write_core_config(application)
    core_config.storage.sqlite.path.parent.mkdir()
    core_config.storage.sqlite.path.write_bytes(b"synthetic-certified-mcp-database")
    core_config.storage.filesystem.root.mkdir(parents=True)
    certified_blob = core_config.storage.filesystem.root / "manifest.json"
    certified_blob.write_bytes(b"synthetic-certified-mcp-blob")
    before_database = hashlib.sha256(core_config.storage.sqlite.path.read_bytes()).hexdigest()
    before_blob = hashlib.sha256(certified_blob.read_bytes()).hexdigest()
    workspace = tmp_path / "operator-workspace"
    config = ServerConfig(
        production_mode=True,
        delivery_cursor_secret="w" * 32,
        mutable_workspace_root=workspace,
    )
    mock_engine = MagicMock(spec=KnowledgeEngine)
    mock_engine.state = EngineState.UNINITIALIZED
    mock_engine.initialize = AsyncMock()
    mock_engine.shutdown = AsyncMock()

    async def initialize() -> None:
        mock_engine.state = EngineState.READY

    mock_engine.initialize.side_effect = initialize
    engine_factory = MagicMock(return_value=mock_engine)
    with (
        patch("mnemo_server.mcp.server.KnowledgeEngine", engine_factory),
        patch("mnemo_server.mcp.server.provision_tokenizer", return_value=Path("tokenizer")),
        patch("mnemo_server.mcp.server.stdio_server") as stdio,
        patch("mnemo_server.mcp.server.Server.run", new_callable=AsyncMock),
    ):
        stdio.return_value.__aenter__.return_value = (MagicMock(), MagicMock())
        stdio.return_value.__aexit__.return_value = False
        await run_stdio_server(config=config, mnemo_config=core_config)

    runtime_config = engine_factory.call_args.kwargs["config"]
    assert runtime_config.storage.sqlite.path == workspace / "workspace.db"
    assert runtime_config.storage.filesystem.root == workspace / "blobs"
    assert engine_factory.call_args.kwargs["embedding_cache_path"] == (
        workspace / "caches" / "embedding-cache.db"
    )
    assert (
        hashlib.sha256(core_config.storage.sqlite.path.read_bytes()).hexdigest() == before_database
    )
    assert hashlib.sha256(certified_blob.read_bytes()).hexdigest() == before_blob
    assert not Path(f"{core_config.storage.sqlite.path}-wal").exists()
    assert not Path(f"{core_config.storage.sqlite.path}-shm").exists()


@pytest.mark.anyio
async def test_run_stdio_server_owns_engine_cancellation(tmp_path: Path) -> None:
    """run_stdio_server handles Cancellation and shuts down owned engine."""
    config = ServerConfig(log_level="debug")

    mock_engine = MagicMock(spec=KnowledgeEngine)
    mock_engine.state = EngineState.UNINITIALIZED
    mock_engine.initialize = AsyncMock()
    mock_engine.shutdown = AsyncMock()

    async def _init() -> None:
        mock_engine.state = EngineState.READY

    mock_engine.initialize.side_effect = _init

    with (
        patch("mnemo_server.mcp.server.KnowledgeEngine", return_value=mock_engine),
        patch(
            "mnemo_server.mcp.server.provision_tokenizer", side_effect=RuntimeError("tokenizer err")
        ),
        patch("mnemo_server.mcp.server.stdio_server") as mock_stdio,
        patch("mnemo_server.mcp.server.Server.run", side_effect=asyncio.CancelledError),
    ):
        mock_stdio.return_value.__aenter__.return_value = (MagicMock(), MagicMock())
        mock_stdio.return_value.__aexit__.return_value = False

        await run_stdio_server(config=config, mnemo_config=_write_core_config(tmp_path))

        assert mock_engine.initialize.called
        assert mock_engine.shutdown.called


def test_create_mcp_server_engine_attr() -> None:
    """create_mcp_server records injected engine instance."""
    mock_engine = MagicMock(spec=KnowledgeEngine)
    server = create_mcp_server(engine=mock_engine)
    assert getattr(server, "_engine", None) is mock_engine


def test_configure_stderr_logging() -> None:
    """Logging is configured to emit to stderr."""
    configure_stderr_logging("DEBUG")
    import logging
    import sys

    root_logger = logging.getLogger()
    assert len(root_logger.handlers) == 1
    assert getattr(root_logger.handlers[0], "stream", None) is sys.stderr
