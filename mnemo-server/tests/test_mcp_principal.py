"""Focused authenticated MCP principal propagation tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import mcp.types as types
import pytest
from mnemo import EngineState, KnowledgeEngine
from mnemo.interfaces import PrincipalContextV1
from mnemo_server.config import ServerConfig
from mnemo_server.mcp.principal import (
    bind_session_principal,
    session_principal,
    sse_principal_from_scope,
    stdio_principal,
)
from mnemo_server.mcp.server import create_mcp_server
from mnemo_server.mcp.tools import execute_mcp_tool


def production_config(**overrides: object) -> ServerConfig:
    values: dict[str, object] = {
        "production_mode": True,
        "full_multilingual_v2_enabled": True,
        "full_multilingual_v2_model_cache": "D:/models",
        "final_qa_operational_store_path": "scratch/test-final-qa-operational.db",
        "mcp_stdio_principal_subject": "mnemo-local-operator",
        "auth_mode": "api-key",
        "api_key": "secret",
        "delivery_cursor_secret": "c" * 32,
    }
    values.update(overrides)
    return ServerConfig.model_validate(values)


def test_stdio_principal_is_server_configured_and_authenticated() -> None:
    principal = stdio_principal(production_config())
    assert principal.authenticated is True
    assert principal == stdio_principal(production_config())


def test_v2_config_rejects_missing_stdio_principal() -> None:
    with pytest.raises(ValueError, match="stdio principal"):
        production_config(mcp_stdio_principal_subject=None)


def test_server_environment_carries_stdio_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MNEMO_SERVER_MCP_STDIO_PRINCIPAL_SUBJECT", "local-operator")
    assert ServerConfig.from_env().mcp_stdio_principal_subject == "local-operator"


def test_sse_principal_uses_only_validated_scope_claims() -> None:
    principal = sse_principal_from_scope({"state": {"auth": {"sub": "validated-user"}}})
    assert principal.authenticated is True
    with pytest.raises(PermissionError, match="claims"):
        sse_principal_from_scope({"state": {}})


def test_session_principal_binding_is_scoped() -> None:
    expected = PrincipalContextV1(uuid4(), True)
    with bind_session_principal(expected):
        assert session_principal() is expected
    with pytest.raises(PermissionError, match="authenticated"):
        session_principal()


@pytest.mark.anyio
async def test_mcp_server_passes_provider_principal_to_tool() -> None:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    expected = PrincipalContextV1(uuid4(), True)
    server = create_mcp_server(engine, principal_provider=lambda: expected)
    handler = server.request_handlers[types.CallToolRequest]
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name="get_capabilities", arguments={}),
    )
    with patch(
        "mnemo_server.mcp.server.execute_mcp_tool", new=AsyncMock(return_value=[])
    ) as execute:
        await handler(request)
    assert execute.await_args.args[4] is expected


@pytest.mark.anyio
async def test_authorized_mcp_tool_rejects_missing_principal() -> None:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    with pytest.raises(PermissionError, match="authenticated"):
        await execute_mcp_tool(engine, "search_evidence", {}, production_config())


@pytest.mark.anyio
async def test_tool_argument_cannot_override_transport_principal() -> None:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    principal = PrincipalContextV1(uuid4(), True)
    with pytest.raises(Exception, match="principal_id"):
        await execute_mcp_tool(
            engine,
            "search_evidence",
            {"query": "x", "principal_id": str(uuid4())},
            ServerConfig(),
            principal,
        )
