"""V1 HTTP serving uses the real disposable ACL before and after retrieval."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from mcp.types import TextContent
from mnemo.interfaces import NotFoundError
from mnemo.models import Notebook
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig
from mnemo_server.mcp.tools import execute_mcp_tool
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority
from mnemo_server.services.trusted_actor import TrustedJWTActorMapper
from test_server_query import MockTokenCounter
from test_server_query import _make_mock_engine as query_engine
from test_server_search import _make_mock_engine as search_engine

_SECRET = "fixture-membership-jwt-secret-32-bytes"


def _headers(subject: str) -> dict[str, str]:
    def encode(value: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

    claims: dict[str, object] = {
        "iss": "fixture-issuer",
        "aud": "fixture-audience",
        "sub": subject,
        "exp": int(time.time()) + 120,
    }
    signed = f"{encode({'alg': 'HS256'})}.{encode(claims)}"
    signature = hmac.new(_SECRET.encode(), signed.encode(), hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return {"Authorization": f"Bearer {signed}.{encoded_signature}"}


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["query", "search"])
async def test_v1_acl_authorizes_and_revalidates_actual_http_service(
    tmp_path: Path, operation: str
) -> None:
    engine: MagicMock = query_engine() if operation == "query" else search_engine()
    notebook_id = uuid4()
    now = datetime.now(UTC)
    notebook = Notebook(notebook_id=notebook_id, title="private", created_at=now, updated_at=now)
    engine.storage.get_notebook = AsyncMock(return_value=notebook)
    scored = engine.storage.search_dense.return_value[0]
    chunk = scored.chunk
    engine.document_scope_resolver = MagicMock()
    engine.document_scope_resolver.resolve_document_scope = AsyncMock(
        return_value=SimpleNamespace(
            notebook_id=notebook_id,
            document_id=chunk.document_id,
            version_id=chunk.version_id,
        )
    )
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", _SECRET)
    owner = mapper.from_token(_headers("alice")["Authorization"].split()[1]).actor_id
    reader = mapper.from_token(_headers("bob")["Authorization"].split()[1]).actor_id
    authority.grant(actor_id=owner, notebook_id=notebook_id, role="owner", operator_id=owner)
    engine.server_scope_authority = authority
    engine.server_actor_mapper = mapper
    config = ServerConfig(
        auth_mode="jwt",
        jwt_secret=_SECRET,
        delivery_cursor_secret="fixture-delivery-cursor-secret-32-bytes",
    )
    app = create_app(server_config=config, engine=engine, provision_tokenizer_on_startup=False)
    app.state.engine = engine
    app.state.server_config = config
    app.state.token_counter = MockTokenCounter()
    body: dict[str, object] = (
        {
            "question": "private",
            "notebook_id": str(notebook_id),
            "retrieval_config": {"modes": ["dense"], "top_k": 1},
            "synthesis": {"enabled": False},
        }
        if operation == "query"
        else {
            "query": "private",
            "notebook_id": str(notebook_id),
            "modes": ["dense"],
            "enable_reranking": False,
        }
    )
    url = f"/v1/{operation}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(url, headers=_headers("bob"), json=body)
        absent = await client.post(
            url, headers=_headers("bob"), json={**body, "notebook_id": str(uuid4())}
        )
        assert denied.status_code == absent.status_code == 404
        assert denied.json()["error"]["code"] == absent.json()["error"]["code"]
        assert chunk.text not in denied.text
        assert engine.storage.search_dense.await_count == 0
        allowed = await client.post(url, headers=_headers("alice"), json=body)
        assert allowed.status_code == 200, allowed.text
        assert chunk.text in allowed.text
        mcp_name = "query_notebook" if operation == "query" else "search_all_notebooks"
        mcp_args = {
            "notebook_id": str(notebook_id),
            "question" if operation == "query" else "query": "private",
        }
        mcp_owner = await execute_mcp_tool(
            engine,
            mcp_name,
            mcp_args,
            server_config=config,
            principal=mapper.from_token(_headers("alice")["Authorization"].split()[1]),
        )
        assert isinstance(mcp_owner[0], TextContent)
        assert chunk.text in mcp_owner[0].text
        with pytest.raises(NotFoundError):
            await execute_mcp_tool(
                engine,
                mcp_name,
                mcp_args,
                server_config=config,
                principal=mapper.from_token(_headers("bob")["Authorization"].split()[1]),
            )
        authority.grant(actor_id=reader, notebook_id=notebook_id, role="reader", operator_id=owner)
        shared = await client.post(url, headers=_headers("bob"), json=body)
        assert shared.status_code == 200, shared.text
        mcp_reader = await execute_mcp_tool(
            engine,
            mcp_name,
            mcp_args,
            server_config=config,
            principal=mapper.from_token(_headers("bob")["Authorization"].split()[1]),
        )
        assert isinstance(mcp_reader[0], TextContent)
        assert chunk.text in mcp_reader[0].text
        authority.revoke(actor_id=reader, notebook_id=notebook_id)
        revoked = await client.post(url, headers=_headers("bob"), json=body)
        assert revoked.status_code == 404
        assert chunk.text not in revoked.text
        with pytest.raises(NotFoundError):
            await execute_mcp_tool(
                engine,
                mcp_name,
                mcp_args,
                server_config=config,
                principal=mapper.from_token(_headers("bob")["Authorization"].split()[1]),
            )
        original_resolution = engine.document_scope_resolver.resolve_document_scope.return_value
        resolution_count = 0

        async def remove_source_during_request(*args: object, **kwargs: object) -> object:
            nonlocal resolution_count
            resolution_count += 1
            if resolution_count > 1:
                raise NotFoundError("authorized resource was not found")
            return original_resolution

        engine.document_scope_resolver.resolve_document_scope.side_effect = (
            remove_source_during_request
        )
        source_revoked = await client.post(url, headers=_headers("alice"), json=body)
        assert source_revoked.status_code == 404
        assert chunk.text not in source_revoked.text
        engine.document_scope_resolver.resolve_document_scope.side_effect = None
        original_search = engine.storage.search_dense.side_effect

        async def revoke_during_search(*args: object, **kwargs: object) -> object:
            authority.revoke(actor_id=owner, notebook_id=notebook_id)
            if original_search is not None:
                return await original_search(*args, **kwargs)
            return engine.storage.search_dense.return_value

        engine.storage.search_dense.side_effect = revoke_during_search
        interrupted = await client.post(url, headers=_headers("alice"), json=body)
        assert interrupted.status_code == 404
        assert chunk.text not in interrupted.text
