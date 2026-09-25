"""Focused authenticated MCP principal propagation tests."""

from __future__ import annotations

from types import SimpleNamespace
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
from mnemo_server.mcp.tools import execute_mcp_tool, get_mcp_tools
from mnemo_server.services.authorization import (
    AuthorizationOperationV1,
    CentralAuthorizationServiceV1,
)


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
async def test_production_tool_discovery_requires_trusted_principal() -> None:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    server = create_mcp_server(engine, config=production_config())
    handler = server.request_handlers[types.ListToolsRequest]
    request = types.ListToolsRequest(method="tools/list")
    with pytest.raises(PermissionError, match="authenticated"):
        await handler(request)


@pytest.mark.anyio
async def test_production_resource_discovery_requires_trusted_principal() -> None:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    server = create_mcp_server(engine, config=production_config())
    list_handler = server.request_handlers[types.ListResourcesRequest]
    read_handler = server.request_handlers[types.ReadResourceRequest]
    with pytest.raises(PermissionError, match="authenticated"):
        await list_handler(types.ListResourcesRequest(method="resources/list"))
    with pytest.raises(PermissionError, match="authenticated"):
        await read_handler(
            types.ReadResourceRequest(
                method="resources/read",
                params=types.ReadResourceRequestParams(uri="mnemo://capabilities"),
            )
        )


@pytest.mark.anyio
async def test_authenticated_production_discovery_has_only_safe_resource() -> None:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    principal = PrincipalContextV1(uuid4(), True)
    server = create_mcp_server(
        engine, config=production_config(), principal_provider=lambda: principal
    )
    resources = await server.request_handlers[types.ListResourcesRequest](
        types.ListResourcesRequest(method="resources/list")
    )
    assert isinstance(resources.root, types.ListResourcesResult)
    assert [str(resource.uri) for resource in resources.root.resources] == ["mnemo://capabilities"]


@pytest.mark.anyio
async def test_authenticated_production_resource_read_is_limited_to_capabilities() -> None:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    server = create_mcp_server(
        engine,
        config=production_config(),
        principal_provider=lambda: PrincipalContextV1(uuid4(), True),
    )
    handler = server.request_handlers[types.ReadResourceRequest]
    with pytest.raises(ValueError, match="Unknown Mnemo resource"):
        await handler(
            types.ReadResourceRequest(
                method="resources/read",
                params=types.ReadResourceRequestParams(uri="mnemo://private"),
            )
        )
    document = MagicMock()
    document.model_dump.return_value = {"capability": "runtime", "notebook_ids": []}
    with patch(
        "mnemo_server.services.capabilities_v2.CapabilityDiscoveryService.document_for_principal",
        new_callable=AsyncMock,
        return_value=document,
    ) as scoped_document:
        result = await handler(
            types.ReadResourceRequest(
                method="resources/read",
                params=types.ReadResourceRequestParams(uri="mnemo://capabilities"),
            )
        )
    assert scoped_document.await_args.args[1].authenticated
    assert "notebook_ids" in str(result.root)
    assert "private" not in str(result.root)


@pytest.mark.anyio
async def test_authorized_mcp_tool_rejects_missing_principal() -> None:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    with pytest.raises(PermissionError, match="authenticated"):
        await execute_mcp_tool(engine, "search_evidence", {}, production_config())


@pytest.mark.anyio
@pytest.mark.parametrize("tool_name", [tool.name for tool in get_mcp_tools()])
async def test_every_production_tool_requires_transport_principal(tool_name: str) -> None:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    with pytest.raises(PermissionError, match="authenticated"):
        await execute_mcp_tool(engine, tool_name, {}, production_config())


@pytest.mark.anyio
@pytest.mark.parametrize("tool_name", [tool.name for tool in get_mcp_tools()])
async def test_every_production_tool_rejects_client_storage_override(tool_name: str) -> None:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    with pytest.raises(Exception, match="Unsupported MCP tool argument"):
        await execute_mcp_tool(
            engine,
            tool_name,
            {"db_path": "C:/untrusted/alternate.db"},
            production_config(),
            PrincipalContextV1(uuid4(), True),
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "tool_name,field",
    [
        ("query_notebook", "notebook_id"),
        ("search_all_notebooks", "notebook_id"),
        ("get_notebook_summary", "notebook_id"),
        ("get_timeline", "notebook_id"),
        ("get_asset", "notebook_id"),
        ("get_image_analysis", "notebook_id"),
        ("get_document", "notebook_id"),
        ("get_document_chunk", "notebook_id"),
        ("get_source_insights", "source_id"),
    ],
)
async def test_production_scope_rejects_unknown_resource_before_tool_execution(
    tool_name: str, field: str
) -> None:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    engine.storage.get_notebook = AsyncMock(return_value=None)
    engine.storage.get_source = AsyncMock(return_value=None)
    guessed_id = uuid4()
    with pytest.raises(Exception, match="authorized resource was not found") as error:
        await execute_mcp_tool(
            engine,
            tool_name,
            {field: str(guessed_id)},
            production_config(),
            PrincipalContextV1(uuid4(), True),
        )
    assert str(guessed_id) not in str(error.value)


@pytest.mark.anyio
async def test_nested_production_policy_override_is_rejected() -> None:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    with pytest.raises(Exception, match="Client production policy override is forbidden"):
        await execute_mcp_tool(
            engine,
            "search_evidence",
            {"scope": {"notebook_id": str(uuid4()), "generation_id": "forged"}},
            production_config(),
            PrincipalContextV1(uuid4(), True),
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "selector",
    [
        {"scope": {"manifest_path": "C:/private/manifest.json"}},
        {"scope": {"filters": [{"reranker_revision": "latest"}]}},
        {"scope": {"workspace_root": "../escape"}},
    ],
)
async def test_recursive_server_owned_policy_override_is_rejected(selector: dict) -> None:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    with pytest.raises(Exception, match="Client production policy override is forbidden"):
        await execute_mcp_tool(
            engine,
            "search_evidence",
            selector,
            production_config(),
            PrincipalContextV1(uuid4(), True),
        )


@pytest.mark.anyio
async def test_timeline_source_must_belong_to_requested_notebook() -> None:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    engine.storage.get_notebook = AsyncMock(return_value=object())
    engine.storage.get_source = AsyncMock(return_value=SimpleNamespace(notebook_id=uuid4()))
    requested_notebook = uuid4()
    with pytest.raises(Exception, match="authorized resource was not found"):
        await execute_mcp_tool(
            engine,
            "get_timeline",
            {"notebook_id": str(requested_notebook), "source_id": str(uuid4())},
            production_config(),
            PrincipalContextV1(uuid4(), True),
        )
    engine.storage.list_sources.assert_not_called()


@pytest.mark.anyio
async def test_central_source_scope_requires_authentication_and_canonical_membership() -> None:
    engine = MagicMock(spec=KnowledgeEngine)
    notebook_id, source_id = uuid4(), uuid4()
    engine.storage.get_source = AsyncMock(return_value=SimpleNamespace(notebook_id=notebook_id))
    engine.storage.get_notebook = AsyncMock(return_value=object())
    authority = CentralAuthorizationServiceV1(engine)
    authenticated = PrincipalContextV1(uuid4(), True)
    assert (
        await authority.authorize_source(
            authenticated, source_id, AuthorizationOperationV1.RETRIEVE
        )
        == notebook_id
    )
    with pytest.raises(PermissionError, match="authenticated"):
        await authority.authorize_source(
            PrincipalContextV1(uuid4(), False), source_id, AuthorizationOperationV1.RETRIEVE
        )
    engine.storage.get_source = AsyncMock(return_value=None)
    with pytest.raises(Exception, match="authorized resource was not found") as error:
        await authority.authorize_source(
            authenticated, source_id, AuthorizationOperationV1.RETRIEVE
        )
    assert str(source_id) not in str(error.value)


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
