"""Independent disposable-store probes for the Stage 6 structured boundary."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import UUID

import anyio
import pytest
from disposable_index_admission import mcp_text
from httpx import ASGITransport, AsyncClient
from mcp.client.session import ClientSession
from mnemo.interfaces import PrincipalContextV1
from test_mcp_immutable_schema_matrix import _body, _fixture, create_app, create_mcp_server


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["older", "newer"])
async def test_scoped_structured_capability_requires_executable_projection(
    tmp_path: Path, legacy: bool
) -> None:
    engine, reader, config, identities = await _fixture(
        tmp_path, legacy=legacy, structured_ready=True, capability_ready=True
    )
    notebook_id, _, version_id, _, chunk = identities[0]
    await reader.close()
    with sqlite3.connect(tmp_path / "matrix.db") as db:
        db.execute("DELETE FROM chunks WHERE id=?", (chunk.id,))
        db.commit()
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.execute("PRAGMA journal_mode=DELETE")
    await reader.open()
    app = create_app(server_config=config, engine=engine, provision_tokenizer_on_startup=False)
    app.state.engine = engine
    app.state.server_config = config
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://fixture",
            headers={"X-API-Key": "fixture-only-not-production"},
        ) as http:
            response = await http.post(
                "/v2/retrieval/structured",
                json={
                    "operation": "describe",
                    "scope": {"notebook_id": str(notebook_id), "version_ids": [str(version_id)]},
                },
            )
            assert response.status_code == 503
            assert response.json()["error"]["category"] == "capability_unavailable"
            capability = await http.get(
                "/v2/capabilities", params={"notebook_id": str(notebook_id)}
            )
            assert capability.status_code == 200
            structured = next(
                item
                for item in capability.json()["capabilities"]
                if item["capability_id"] == "structured_retrieval"
            )
            assert structured["lifecycle"]["available_for_scope"] is False

        server = create_mcp_server(
            engine,
            config=config,
            principal_provider=lambda: PrincipalContextV1(UUID(int=99), True),
        )
        c2s_send, c2s_recv = anyio.create_memory_object_stream(20)
        s2c_send, s2c_recv = anyio.create_memory_object_stream(20)
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(server.run, c2s_recv, s2c_send, server.create_initialization_options())
            async with ClientSession(s2c_recv, c2s_send) as client:
                await client.initialize()
                result = await client.call_tool(
                    "query_structured",
                    {
                        "operation": "describe",
                        "scope": {
                            "notebook_id": str(notebook_id),
                            "version_ids": [str(version_id)],
                        },
                    },
                )
                assert result.isError
                assert json.loads(mcp_text(result))["error"]["category"] == (
                    "capability_unavailable"
                )
                result = await client.call_tool(
                    "get_capabilities", {"notebook_id": str(notebook_id)}
                )
                states = {
                    item["capability_id"]: item["lifecycle"]["available_for_scope"]
                    for item in _body(result)["capabilities"]
                }
                assert states["structured_retrieval"] is False
                tasks.cancel_scope.cancel()
    finally:
        await reader.close()
