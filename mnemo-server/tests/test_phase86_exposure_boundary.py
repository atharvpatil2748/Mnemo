"""Disposable public regressions for the Phase 8.6 evaluation-only boundary."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import UUID

import anyio
import pytest
from httpx import ASGITransport, AsyncClient
from mcp.client.session import ClientSession
from mcp.types import CallToolResult, TextContent
from mnemo import MnemoConfig
from mnemo.interfaces import PrincipalContextV1
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig
from mnemo_server.evaluation.notebook_registry import ServerOwnedEvaluationNotebookRegistryV1
from test_mcp_immutable_schema_matrix import (
    _fixture,
)
from test_mcp_immutable_schema_matrix import (
    create_app as create_disposable_app,
)
from test_mcp_immutable_schema_matrix import (
    create_mcp_server as create_disposable_mcp_server,
)
from test_production_storage_composition import _config


def _text(result: CallToolResult) -> str:
    assert result.content
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text


@pytest.mark.anyio
async def test_http_production_startup_rejects_evaluation_store_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = tmp_path / "application"
    base: MnemoConfig = _config(tmp_path)
    evaluation = application / "scratch/evaluation_notebooks/phase8_6"
    sqlite = base.storage.sqlite.model_copy(update={"path": evaluation / "mnemo.db"})
    storage = base.storage.model_copy(update={"sqlite": sqlite})
    selected = base.model_copy(update={"storage": storage})
    server = ServerConfig(
        production_mode=True,
        delivery_cursor_secret="disposable-test-cursor-key-000000000000",
    )
    monkeypatch.chdir(application)
    app = create_app(server, selected, provision_tokenizer_on_startup=False)

    with pytest.raises(RuntimeError, match="PRODUCTION_CORPUS_UNINDEXED"):
        async with app.router.lifespan_context(app):
            pass
    assert not evaluation.exists()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["older", "newer"])
async def test_public_production_fixture_never_federates_evaluation_store(
    tmp_path: Path, legacy: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    production = tmp_path / "production"
    production.mkdir()
    engine, reader, config, identities = await _fixture(
        production, legacy=legacy, capability_ready=True
    )
    notebook_id, document_id, version_id, _source_id, chunk = identities[0]
    evaluation_id = UUID(int=9001)
    evaluation = tmp_path / "evaluation" / "mnemo.db"
    evaluation.parent.mkdir()
    with sqlite3.connect(evaluation) as connection:
        connection.execute("CREATE TABLE private_identity (notebook_id TEXT, content TEXT)")
        connection.execute(
            "INSERT INTO private_identity VALUES (?, ?)",
            (str(evaluation_id), "evaluation-only-marker"),
        )

    def forbidden_registry_lookup(self: object, alias: str) -> None:
        raise AssertionError(f"production reached evaluation registry: {alias}")

    monkeypatch.setattr(
        ServerOwnedEvaluationNotebookRegistryV1, "resolve", forbidden_registry_lookup
    )
    server = create_disposable_mcp_server(
        engine,
        config=config,
        principal_provider=lambda: PrincipalContextV1(UUID(int=99), True),
    )
    c2s_send, c2s_recv = anyio.create_memory_object_stream(20)
    s2c_send, s2c_recv = anyio.create_memory_object_stream(20)
    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(server.run, c2s_recv, s2c_send, server.create_initialization_options())
            async with ClientSession(s2c_recv, c2s_send) as client:
                await client.initialize()
                listing = await client.call_tool("list_notebooks", {"limit": 10})
                assert not listing.isError
                assert str(notebook_id) in _text(listing)
                assert str(evaluation_id) not in _text(listing)

                search = await client.call_tool(
                    "search_all_notebooks", {"query": "schema", "top_k": 2}
                )
                assert not search.isError
                assert chunk.id in _text(search)
                assert "evaluation-only-marker" not in _text(search)

                capabilities = await client.call_tool("get_capabilities", {})
                assert not capabilities.isError
                assert str(evaluation_id) not in _text(capabilities)
                assert "evaluation_notebooks" not in _text(capabilities)

                for forbidden in (
                    {"limit": 1, "serving_role": "evaluation"},
                    {"limit": 1, "registry_alias": "phase8_6"},
                    {"limit": 1, "db_path": str(evaluation)},
                ):
                    invalid = await client.call_tool("list_notebooks", forbidden)
                    assert invalid.isError
                    assert json.loads(_text(invalid))["error"]["category"] == ("invalid_input")
                    assert str(evaluation) not in _text(invalid)

                for name, arguments in (
                    (
                        "query_notebook",
                        {"notebook_id": str(evaluation_id), "question": "schema"},
                    ),
                    (
                        "search_evidence",
                        {
                            "query": "schema",
                            "mode": "ranked",
                            "scope": {"notebook_id": str(evaluation_id)},
                            "representations": ["canonical_text"],
                            "evidence_budget": 1,
                        },
                    ),
                ):
                    inaccessible = await client.call_tool(name, arguments)
                    assert inaccessible.isError
                    assert str(evaluation_id) not in _text(inaccessible)
                    assert "evaluation-only-marker" not in _text(inaccessible)

                denied = await client.call_tool(
                    "get_document_chunk",
                    {
                        "notebook_id": str(evaluation_id),
                        "document_id": str(document_id),
                        "version_id": str(version_id),
                        "chunk_id": chunk.id,
                    },
                )
                assert denied.isError
                payload = json.loads(_text(denied))
                assert payload["error"]["category"] in {"not_found", "unauthorized"}
                assert str(evaluation_id) not in _text(denied)
                assert "evaluation-only-marker" not in _text(denied)

                mixed = await client.call_tool(
                    "search_evidence",
                    {
                        "query": "schema",
                        "mode": "ranked",
                        "scope": {
                            "notebook_id": str(notebook_id),
                            "document_ids": [str(document_id), str(UUID(int=9002))],
                        },
                        "representations": ["canonical_text"],
                        "evidence_budget": 2,
                    },
                )
                assert not mixed.isError
                mixed_payload = json.loads(_text(mixed))
                assert mixed_payload["items"]
                assert all(
                    item["document_id"] == str(document_id) for item in mixed_payload["items"]
                )
                assert "evaluation-only-marker" not in _text(mixed)
                tasks.cancel_scope.cancel()

        app = create_disposable_app(
            server_config=config, engine=engine, provision_tokenizer_on_startup=False
        )
        app.state.engine = engine
        app.state.server_config = config
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://fixture",
            headers={"X-API-Key": "fixture-only-not-production"},
        ) as http:
            available = await http.get(
                f"/v2/notebooks/{notebook_id}/documents/{document_id}/"
                f"versions/{version_id}/chunks/{chunk.id}"
            )
            assert available.status_code == 200
            assert chunk.id in json.dumps(available.json())
            unavailable = await http.get(
                f"/v2/notebooks/{evaluation_id}/documents/{document_id}/"
                f"versions/{version_id}/chunks/{chunk.id}"
            )
            assert unavailable.status_code in {400, 404}
            assert str(evaluation_id) not in unavailable.text
            assert "evaluation-only-marker" not in unavailable.text
    finally:
        await reader.close()
