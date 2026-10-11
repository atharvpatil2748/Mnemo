"""Owner-scoped, finite-lived fixture composition and immutable persistence."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from mnemo_server.config import ServerConfig

MODULE = Path(__file__).resolve().parents[2] / "scripts/serve_ordered_text_fixture.py"
SPEC = importlib.util.spec_from_file_location("isolated_text_fixture", MODULE)
assert SPEC and SPEC.loader
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)


@pytest.mark.parametrize("relative", ["../outside", ".", "../evaluation_notebooks"])
def test_root_cannot_escape_owner_approved_directory(tmp_path, monkeypatch, relative):
    monkeypatch.setattr(fixture, "BASE", tmp_path / "approved")
    with pytest.raises(ValueError, match="dedicated approved"):
        fixture.approved_root(tmp_path / "approved" / relative)


@pytest.mark.anyio
async def test_persisted_unicode_fixture_readonly_and_authenticated(tmp_path, monkeypatch):
    monkeypatch.setattr(fixture, "BASE", tmp_path)
    root = tmp_path / "certification"
    manifest = await fixture.provision(root)
    assert manifest["text_sha256_utf8"] == (
        "70f933e57255937afc39612ac54a311f7653ab9c1c7d91c20106a4db12a83493"
    )
    assert datetime.fromisoformat(manifest["expires_utc"]) > datetime.now(UTC)
    with pytest.raises(ValueError, match="overwrite"):
        await fixture.provision(root)
    config = ServerConfig(
        auth_mode="api-key",
        api_key="disposable-not-production",
        delivery_cursor_secret="isolated-test-signing-material-32-bytes-minimum",
    )
    app = fixture.fixture_app(root, config)
    before = (root / "fixture.db").read_bytes()
    async with app.router.lifespan_context(app):
        reader = fixture.FixtureReader(root)
        await reader.open()
        await reader.blobs.open()
        try:
            parsed = await reader.get_parsed_document(UUID(manifest["version_id"]))
            assert len(parsed.blocks) == 12
            assert parsed.blocks[1].text == manifest["expected_blocks"][1]["text"]
        finally:
            await reader.blobs.close()
            await reader.close()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://fixture"
        ) as client:
            for headers in ({}, {"Authorization": "Bearer wrong"}):
                response = await client.get("/sse", headers=headers)
                assert response.status_code == 401
                assert response.json()["error"]["category"] == "unauthorized"
            response = await client.post(
                "/mcp/",
                headers={
                    "Authorization": "Bearer disposable-not-production",
                    "Accept": "application/json, text/event-stream",
                },
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            )
            assert response.status_code == 200
            tools = response.json()["result"]["tools"]
            assert {tool["name"] for tool in tools} == {
                "get_document",
                "get_capabilities",
                "list_notebooks",
            }
            document_tool = next(tool for tool in tools if tool["name"] == "get_document")
            assert set(document_tool["inputSchema"]["properties"]["mode"]["enum"]) == {
                "text",
                "blocks",
                "original",
            }
    assert (root / "fixture.db").read_bytes() == before
    assert not Path(str(root / "fixture.db") + "-wal").exists()
    assert not Path(str(root / "fixture.db") + "-shm").exists()
    with pytest.raises(ValueError, match="authentication"):
        fixture.fixture_app(root, ServerConfig(auth_mode="none"))
    (root / "fixture.db").write_bytes(before + b"tamper")
    with pytest.raises(ValueError, match="identity mismatch"):
        fixture.fixture_app(root, config)


@pytest.mark.anyio
async def test_expired_fixture_cannot_start(tmp_path, monkeypatch):
    monkeypatch.setattr(fixture, "BASE", tmp_path)
    root = tmp_path / "expired"
    manifest = await fixture.provision(root)
    manifest["expires_utc"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    (root / "fixture-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="expired"):
        fixture.fixture_app(
            root,
            ServerConfig(
                auth_mode="api-key",
                api_key="disposable",
                delivery_cursor_secret="isolated-test-signing-material-32-bytes-minimum",
            ),
        )
