"""No production transport may select a retired index as a fallback."""

import json
import runpy
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import mcp.types as mcp_types
import pytest
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig
from mnemo_server.mcp.server import create_mcp_server, create_sse_app, run_stdio_server
from mnemo_server.services.production_runtime_selection import (
    require_production_index,
    resolve_production_runtime_selection,
)


def _selection(root: Path) -> Path:
    path = root / "config/production/runtime-selection.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema": "mnemo.production-runtime-selection/1",
                "deployment_key": "mnemo",
                "state": "UNINDEXED",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_fresh_workspace_is_explicitly_unindexed_without_notebook(tmp_path: Path) -> None:
    _selection(tmp_path)
    first = resolve_production_runtime_selection(tmp_path)
    assert first.deployment_key == "mnemo"
    assert first.state == "UNINDEXED"
    with pytest.raises(RuntimeError, match="PRODUCTION_CORPUS_UNINDEXED"):
        require_production_index(tmp_path)


def test_selection_is_path_independent(tmp_path: Path) -> None:
    left, right = tmp_path / "left", tmp_path / "right"
    left.mkdir()
    right.mkdir()
    _selection(left)
    _selection(right)
    assert resolve_production_runtime_selection(left) == resolve_production_runtime_selection(right)


def test_historical_index_or_evaluation_registry_cannot_be_selected(tmp_path: Path) -> None:
    _selection(tmp_path)
    legacy = tmp_path / "scratch/evaluation_notebooks/registry.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"notebooks": {"phase8_5": {}}}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="PRODUCTION_CORPUS_UNINDEXED"):
        require_production_index(tmp_path)


def test_missing_or_ambiguous_selection_never_falls_back(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="PRODUCTION_RUNTIME_SELECTION_UNAVAILABLE"):
        require_production_index(tmp_path)
    path = _selection(tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["state"] = "LEGACY_CERTIFIED"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RuntimeError, match="PRODUCTION_RUNTIME_SELECTION_INVALID"):
        require_production_index(tmp_path)


def _production_config() -> ServerConfig:
    return ServerConfig(
        production_mode=True,
        auth_mode="api-key",
        api_key="fixture-secret",
        delivery_cursor_secret="fixture-cursor-signing-secret-32bytes",
    )


@pytest.mark.anyio
async def test_http_and_mcp_startup_refuse_legacy_fallback() -> None:
    config = _production_config()
    http = create_app(config, provision_tokenizer_on_startup=False)
    with pytest.raises(RuntimeError, match="PRODUCTION_CORPUS_UNINDEXED"):
        async with http.router.lifespan_context(http):
            pass
    with pytest.raises(RuntimeError, match="PRODUCTION_CORPUS_UNINDEXED"):
        await run_stdio_server(config=config)
    sse = create_sse_app(config=config)
    with pytest.raises(RuntimeError, match="PRODUCTION_CORPUS_UNINDEXED"):
        async with sse.router.lifespan_context(sse):
            pass


def test_certified_environment_loader_refuses_revoked_legacy_path() -> None:
    with pytest.raises(RuntimeError, match="PRODUCTION_CORPUS_UNINDEXED"):
        ServerConfig.from_env(certified_production=True)


@pytest.mark.anyio
async def test_historical_readiness_script_cannot_publish_unindexed_artifact(
    tmp_path: Path,
) -> None:
    _selection(tmp_path)
    module = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "scripts/mnemo_v2_serving_readiness.py")
    )
    args = type("Args", (), {"workspace_root": tmp_path})()
    with pytest.raises(RuntimeError, match="PRODUCTION_CORPUS_UNINDEXED"):
        await module["_run"](args)
    assert not (tmp_path / "scratch/mnemo_v2_exposed_readiness.json").exists()


@pytest.mark.anyio
async def test_http_request_dispatch_rejects_injected_legacy_engine() -> None:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    app = create_app(_production_config(), engine=engine, provision_tokenizer_on_startup=False)
    app.state.engine = engine
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for path in ("/v1/notebooks", "/v1/search", "/v2/capabilities"):
            response = await client.get(path)
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "PRODUCTION_CORPUS_UNINDEXED"
    engine.storage.get_notebook.assert_not_called()


@pytest.mark.anyio
async def test_mcp_dispatch_rejects_injected_legacy_engine() -> None:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    server = create_mcp_server(engine=engine, config=_production_config())
    handler = server.request_handlers[mcp_types.CallToolRequest]
    request = mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(name="list_notebooks", arguments={}),
    )
    response = await handler(request)
    assert response.root.isError
    assert response.root.content[0].text == "PRODUCTION_CORPUS_UNINDEXED"
    engine.storage.list_notebooks.assert_not_called()
