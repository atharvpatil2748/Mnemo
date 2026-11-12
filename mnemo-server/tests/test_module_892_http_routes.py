"""Actual HTTP notebook dispatch with disposable ACL and notebook stores."""

import asyncio
import base64
import hashlib
import hmac
import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import mcp.types as mcp_types
import pytest
from httpx import ASGITransport, AsyncClient
from mnemo.cursors import CursorConflictError
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo.interfaces import NotFoundError
from mnemo.models import (
    Citation,
    FrozenMetadata,
    Note,
    Notebook,
    NoteOrigin,
    Session,
    Turn,
    TurnRole,
)
from mnemo.retrieval.scope import StorageDocumentScopeResolverV1, StorageSourceAssociationReaderV1
from mnemo.storage.sqlite import SQLiteStore
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig
from mnemo_server.mcp.tools import execute_mcp_tool
from mnemo_server.schemas.notes import CreateNoteRequest
from mnemo_server.schemas.query import QueryRequest
from mnemo_server.schemas.search import SearchRequest
from mnemo_server.schemas.sessions import CreateSessionRequest, CreateTurnRequest
from mnemo_server.services.notes import NoteService
from mnemo_server.services.query import QueryService
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority
from mnemo_server.services.search import SearchService
from mnemo_server.services.sessions import SessionService
from mnemo_server.services.trusted_actor import TrustedJWTActorMapper

_SECRET = "fixture-membership-jwt-secret-32-bytes"


@pytest.mark.anyio
async def test_note_read_routes_authorize_and_revalidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SQLiteStore(tmp_path / "note-notebooks.db")
    await store.open()
    authority = SQLiteNotebookScopeAuthority((tmp_path / "note-acl.db").resolve())
    authority.initialize()
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", _SECRET)
    owner = mapper.from_token(_headers("alice")["Authorization"].split()[1])
    reader = mapper.from_token(_headers("carol")["Authorization"].split()[1])
    notebook_id, legacy_id, note_id = uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)
    await store.upsert_notebook(
        Notebook(notebook_id=notebook_id, title="private", created_at=now, updated_at=now)
    )
    await store.upsert_notebook(
        Notebook(notebook_id=legacy_id, title="unassigned", created_at=now, updated_at=now)
    )
    await store.upsert_note(
        Note(
            note_id=note_id,
            notebook_id=notebook_id,
            title="private note",
            content="private note body",
            origin=NoteOrigin.USER,
            created_at=now,
            updated_at=now,
            metadata=FrozenMetadata({}),
        )
    )
    await store.upsert_note(
        Note(
            note_id=uuid4(),
            notebook_id=notebook_id,
            title="second note",
            content="second private note body",
            origin=NoteOrigin.USER,
            created_at=now,
            updated_at=now,
        )
    )
    authority.grant(
        actor_id=owner.actor_id,
        notebook_id=notebook_id,
        role="owner",
        operator_id=owner.actor_id,
    )
    authority.grant(
        actor_id=reader.actor_id,
        notebook_id=notebook_id,
        role="reader",
        operator_id=owner.actor_id,
    )
    engine = MagicMock(spec=KnowledgeEngine)
    engine.storage = store
    engine.state = EngineState.READY
    engine.initialize = AsyncMock()
    engine.shutdown = AsyncMock()
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
    base = f"/v1/notebooks/{notebook_id}/notes"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for subject in ("alice", "carol"):
                listed = await client.get(base, headers=_headers(subject))
                assert listed.status_code == 200, listed.text
                assert any(
                    item["content"] == "private note body" for item in listed.json()["items"]
                )
                detail = await client.get(f"{base}/{note_id}", headers=_headers(subject))
                assert detail.status_code == 200, detail.text
                assert detail.json()["note_id"] == str(note_id)
            first = await client.get(base, params={"limit": 1}, headers=_headers("alice"))
            assert first.status_code == 200, first.text
            owner_cursor = first.json()["next_cursor"]
            assert isinstance(owner_cursor, str) and owner_cursor.startswith("mnc2.")
            continued = await client.get(
                base, params={"limit": 1, "cursor": owner_cursor}, headers=_headers("alice")
            )
            assert continued.status_code == 200, continued.text
            assert continued.json()["items"][0]["note_id"] != first.json()["items"][0]["note_id"]
            cross_actor = await client.get(
                base, params={"limit": 1, "cursor": owner_cursor}, headers=_headers("carol")
            )
            assert cross_actor.status_code != 200
            tampered = await client.get(
                base,
                params={"limit": 1, "cursor": owner_cursor[:-1] + "x"},
                headers=_headers("alice"),
            )
            assert tampered.status_code != 200
            wrong_limit = await client.get(
                base, params={"limit": 2, "cursor": owner_cursor}, headers=_headers("alice")
            )
            assert wrong_limit.status_code != 200
            reader_first = await client.get(base, params={"limit": 1}, headers=_headers("carol"))
            reader_cursor = reader_first.json()["next_cursor"]
            for target in (base, f"{base}/{note_id}"):
                denied = await client.get(target, headers=_headers("bob"))
                assert denied.status_code == 404
                assert "private note body" not in denied.text
                assert (await client.get(target)).status_code != 200
            assert (
                await client.get(f"/v1/notebooks/{legacy_id}/notes", headers=_headers("alice"))
            ).status_code == 404
            assert (
                await client.get(f"{base}/{uuid4()}", headers=_headers("alice"))
            ).status_code == 404
            created = await client.post(
                base, headers=_headers("alice"), json={"content": "new private note"}
            )
            assert created.status_code == 201, created.text
            created_id = created.json()["note_id"]
            assert (
                await client.get(f"{base}/{created_id}", headers=_headers("carol"))
            ).status_code == 200
            for subject in ("carol", "bob"):
                assert (
                    await client.post(
                        base, headers=_headers(subject), json={"content": "denied write"}
                    )
                ).status_code == 404
                assert (
                    await client.patch(
                        f"{base}/{note_id}", headers=_headers(subject), json={"content": "denied"}
                    )
                ).status_code == 404
                assert (
                    await client.delete(f"{base}/{note_id}", headers=_headers(subject))
                ).status_code == 404
            assert (
                await client.post(base, json={"content": "missing identity"})
            ).status_code == 401
            assert (
                await client.post(
                    f"/v1/notebooks/{legacy_id}/notes",
                    headers=_headers("alice"),
                    json={"content": "quarantined"},
                )
            ).status_code == 404
            updated = await client.patch(
                f"{base}/{note_id}",
                headers=_headers("alice"),
                json={"content": "owner update"},
            )
            assert updated.status_code == 200 and updated.json()["content"] == "owner update"
            assert (
                await client.delete(f"{base}/{created_id}", headers=_headers("alice"))
            ).status_code == 204
            assert (
                await client.get(f"{base}/{created_id}", headers=_headers("alice"))
            ).status_code == 404
            with pytest.raises(PermissionError):
                await NoteService(engine).create_note(
                    notebook_id, CreateNoteRequest(content="direct bypass")
                )
            with pytest.raises(PermissionError):
                await NoteService(engine).get_note(notebook_id, note_id)

            write_entered = asyncio.Event()
            release_write = asyncio.Event()
            revoke_finished = Event()
            original_upsert = store.upsert_note

            async def held_upsert(value: Note) -> None:
                write_entered.set()
                await release_write.wait()
                await original_upsert(value)

            def revoke_owner() -> None:
                authority.revoke(actor_id=owner.actor_id, notebook_id=notebook_id)
                revoke_finished.set()

            with monkeypatch.context() as patch:
                patch.setattr(store, "upsert_note", held_upsert)
                writing = asyncio.create_task(
                    client.post(
                        base, headers=_headers("alice"), json={"content": "held owner write"}
                    )
                )
                await asyncio.wait_for(write_entered.wait(), timeout=5)
                revoker = Thread(target=revoke_owner, daemon=True)
                revoker.start()
                try:
                    assert not revoke_finished.wait(0.05)
                finally:
                    release_write.set()
                written = await writing
                revoker.join(timeout=5)
                assert not revoker.is_alive() and revoke_finished.is_set()
            assert written.status_code == 201, written.text
            assert (await client.get(base, headers=_headers("alice"))).status_code == 404
            authority.grant(
                actor_id=owner.actor_id,
                notebook_id=notebook_id,
                role="owner",
                operator_id=owner.actor_id,
            )

            original_get_note = store.get_note

            async def revoke_after_read(selected: UUID) -> Note | None:
                result = await original_get_note(selected)
                authority.revoke(actor_id=reader.actor_id, notebook_id=notebook_id)
                return result

            monkeypatch.setattr(store, "get_note", revoke_after_read)
            revoked = await client.get(f"{base}/{note_id}", headers=_headers("carol"))
            assert revoked.status_code == 404
            assert "private note body" not in revoked.text
            authority.grant(
                actor_id=reader.actor_id,
                notebook_id=notebook_id,
                role="reader",
                operator_id=owner.actor_id,
            )
            stale = await client.get(
                base, params={"limit": 1, "cursor": reader_cursor}, headers=_headers("carol")
            )
            assert stale.status_code != 200
    finally:
        await store.close()


@pytest.mark.anyio
async def test_session_read_routes_authorize_before_disclosure_and_revalidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SQLiteStore(tmp_path / "session-notebooks.db")
    await store.open()
    authority = SQLiteNotebookScopeAuthority((tmp_path / "session-acl.db").resolve())
    authority.initialize()
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", _SECRET)
    owner = mapper.from_token(_headers("alice")["Authorization"].split()[1])
    reader = mapper.from_token(_headers("carol")["Authorization"].split()[1])
    notebook_id, legacy_id, session_id = uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)
    await store.upsert_notebook(
        Notebook(notebook_id=notebook_id, title="private", created_at=now, updated_at=now)
    )
    await store.upsert_notebook(
        Notebook(notebook_id=legacy_id, title="unassigned", created_at=now, updated_at=now)
    )
    await store.upsert_session(
        Session(
            session_id=session_id,
            notebook_id=notebook_id,
            title="private session",
            created_at=now,
            updated_at=now,
            turns=(),
            metadata=FrozenMetadata({}),
        )
    )
    await store.upsert_session(
        Session(
            session_id=uuid4(),
            notebook_id=notebook_id,
            title="second private session",
            created_at=now,
            updated_at=now,
            turns=(),
        )
    )
    authority.grant(
        actor_id=owner.actor_id,
        notebook_id=notebook_id,
        role="owner",
        operator_id=owner.actor_id,
    )
    authority.grant(
        actor_id=reader.actor_id,
        notebook_id=notebook_id,
        role="reader",
        operator_id=owner.actor_id,
    )
    engine = MagicMock(spec=KnowledgeEngine)
    engine.storage = store
    engine.state = EngineState.READY
    engine.initialize = AsyncMock()
    engine.shutdown = AsyncMock()
    engine.server_scope_authority = authority
    engine.server_actor_mapper = mapper
    engine.document_scope_resolver = StorageDocumentScopeResolverV1(
        store, StorageSourceAssociationReaderV1(store)
    )
    config = ServerConfig(
        auth_mode="jwt",
        jwt_secret=_SECRET,
        delivery_cursor_secret="fixture-delivery-cursor-secret-32-bytes",
    )
    app = create_app(server_config=config, engine=engine, provision_tokenizer_on_startup=False)
    app.state.engine = engine
    app.state.server_config = config
    base = f"/v1/notebooks/{notebook_id}/sessions"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for subject in ("alice", "carol"):
                listed = await client.get(base, headers=_headers(subject))
                assert listed.status_code == 200, listed.text
                assert str(session_id) in [item["session_id"] for item in listed.json()["items"]]
                detail = await client.get(f"{base}/{session_id}", headers=_headers(subject))
                assert detail.status_code == 200, detail.text
                assert detail.json()["title"] == "private session"
            first = await client.get(base, params={"limit": 1}, headers=_headers("alice"))
            assert first.status_code == 200
            owner_cursor = first.json()["next_cursor"]
            assert isinstance(owner_cursor, str) and owner_cursor.startswith("mnc2.")
            continued = await client.get(
                base, params={"limit": 1, "cursor": owner_cursor}, headers=_headers("alice")
            )
            assert continued.status_code == 200, continued.text
            assert (
                continued.json()["items"][0]["session_id"] != first.json()["items"][0]["session_id"]
            )
            assert (
                await client.get(
                    base, params={"limit": 1, "cursor": owner_cursor}, headers=_headers("carol")
                )
            ).status_code != 200
            reader_first = await client.get(base, params={"limit": 1}, headers=_headers("carol"))
            reader_cursor = reader_first.json()["next_cursor"]
            for target in (base, f"{base}/{session_id}"):
                denied = await client.get(target, headers=_headers("bob"))
                assert denied.status_code == 404
                assert "private session" not in denied.text
                missing_identity = await client.get(target)
                assert missing_identity.status_code != 200
            assert (
                await client.get(f"/v1/notebooks/{legacy_id}/sessions", headers=_headers("alice"))
            ).status_code == 404
            assert (
                await client.get(f"{base}/{uuid4()}", headers=_headers("alice"))
            ).status_code == 404
            created = await client.post(base, headers=_headers("alice"), json={"title": "write"})
            assert created.status_code == 201, created.text
            created_id = created.json()["session_id"]
            appended = await client.post(
                f"{base}/{created_id}/turns",
                headers=_headers("alice"),
                json={"role": "user", "content": "private turn"},
            )
            assert appended.status_code == 201, appended.text
            detail = await client.get(f"{base}/{created_id}", headers=_headers("carol"))
            assert detail.status_code == 200, detail.text
            assert [turn["content"] for turn in detail.json()["turns"]] == ["private turn"]
            for subject in ("carol", "bob"):
                assert (
                    await client.post(base, headers=_headers(subject), json={"title": "denied"})
                ).status_code == 404
                assert (
                    await client.post(
                        f"{base}/{created_id}/turns",
                        headers=_headers(subject),
                        json={"role": "user", "content": "denied"},
                    )
                ).status_code == 404
                assert (
                    await client.delete(f"{base}/{created_id}", headers=_headers(subject))
                ).status_code == 404
            assert (await client.post(base, json={"title": "missing identity"})).status_code == 401
            assert (
                await client.post(
                    f"/v1/notebooks/{legacy_id}/sessions",
                    headers=_headers("alice"),
                    json={"title": "quarantined"},
                )
            ).status_code == 404
            assert (
                await client.delete(f"{base}/{created_id}", headers=_headers("alice"))
            ).status_code == 204
            assert (
                await client.get(f"{base}/{created_id}", headers=_headers("alice"))
            ).status_code == 404
            with pytest.raises(PermissionError):
                await SessionService(engine).create_session(
                    notebook_id, CreateSessionRequest(title="direct bypass")
                )
            with pytest.raises(PermissionError):
                await SessionService(engine).get_session(notebook_id, session_id)

            db = store._require_open()
            await db.execute(
                "CREATE TEMP TRIGGER reject_test_turn BEFORE INSERT ON turns "
                "WHEN NEW.content='blocked-turn' BEGIN SELECT RAISE(ABORT, 'injected'); END"
            )
            await db.commit()
            before_failed_append = await store.get_session(session_id)
            try:
                with pytest.raises(sqlite3.IntegrityError):
                    await SessionService(engine, principal=owner).append_turn(
                        notebook_id,
                        session_id,
                        CreateTurnRequest(role=TurnRole.USER, content="blocked-turn"),
                    )
            finally:
                await db.execute("DROP TRIGGER reject_test_turn")
                await db.commit()
            assert await store.get_session(session_id) == before_failed_append

            # A persisted citation without an authorized source relationship
            # must not be disclosed just because the session itself is in scope.
            turn_id = uuid4()
            await store.append_turn(
                session_id,
                Turn(
                    turn_id=turn_id,
                    session_id=session_id,
                    sequence=0,
                    role=TurnRole.ASSISTANT,
                    content="citation held pending scope validation",
                    created_at=now,
                ),
            )
            foreign = Citation(
                citation_id=uuid4(),
                turn_id=turn_id,
                source_number=1,
                chunk_id="a" * 64,
                document_id=uuid4(),
                version_id=uuid4(),
                document_title="other private document",
                verbatim_quote="other private evidence",
                created_at=now,
            )

            async def foreign_citations(_: UUID) -> tuple[Citation, ...]:
                return (foreign,)

            monkeypatch.setattr(store, "get_citations_for_turn", foreign_citations)
            foreign_citation = await client.get(f"{base}/{session_id}", headers=_headers("alice"))
            assert foreign_citation.status_code == 404
            assert "other private evidence" not in foreign_citation.text

            original_get_session = store.get_session

            async def revoke_after_read(selected: UUID) -> Session | None:
                result = await original_get_session(selected)
                authority.revoke(actor_id=reader.actor_id, notebook_id=notebook_id)
                return result

            monkeypatch.setattr(store, "get_session", revoke_after_read)
            revoked_in_flight = await client.get(f"{base}/{session_id}", headers=_headers("carol"))
            assert revoked_in_flight.status_code == 404
            assert "private session" not in revoked_in_flight.text
            authority.grant(
                actor_id=reader.actor_id,
                notebook_id=notebook_id,
                role="reader",
                operator_id=owner.actor_id,
            )
            assert (
                await client.get(
                    base,
                    params={"limit": 1, "cursor": reader_cursor},
                    headers=_headers("carol"),
                )
            ).status_code != 200
    finally:
        await store.close()


def _headers(subject: str) -> dict[str, str]:
    def encoded(value: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

    claims: dict[str, object] = {
        "iss": "fixture-issuer",
        "aud": "fixture-audience",
        "sub": subject,
        "exp": int(time.time()) + 60,
    }
    signed = f"{encoded({'alg': 'HS256'})}.{encoded(claims)}"
    digest = hmac.new(_SECRET.encode(), signed.encode(), hashlib.sha256).digest()
    token = f"{signed}.{base64.urlsafe_b64encode(digest).rstrip(b'=').decode()}"
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_http_notebook_membership_lifecycle_and_non_disclosure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SQLiteStore(tmp_path / "notebooks.db")
    await store.open()
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", _SECRET)
    engine = MagicMock(spec=KnowledgeEngine)
    engine.storage = store
    engine.state = EngineState.READY
    engine.initialize = AsyncMock()
    engine.shutdown = AsyncMock()
    engine.server_scope_authority = authority
    engine.server_actor_mapper = mapper
    engine.structured_retrieval = None
    config = ServerConfig(
        auth_mode="jwt",
        jwt_secret=_SECRET,
        delivery_cursor_secret="fixture-delivery-cursor-secret-32-bytes",
    )
    app = create_app(server_config=config, engine=engine, provision_tokenizer_on_startup=False)
    app.state.engine = engine
    app.state.server_config = config  # test client bypasses lifespan; explicit disposable fixture
    legacy_id = uuid4()
    now = datetime.now(UTC)
    await store.upsert_notebook(
        Notebook(notebook_id=legacy_id, title="unassigned", created_at=now, updated_at=now)
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post(
                "/v1/notebooks", headers=_headers("alice"), json={"title": "private"}
            )
            assert created.status_code == 201, created.text
            notebook_id = created.json()["notebook_id"]
            owner = mapper.from_token(_headers("alice")["Authorization"].split()[1]).actor_id
            reader = mapper.from_token(_headers("bob")["Authorization"].split()[1]).actor_id
            mcp_owner = await execute_mcp_tool(
                engine,
                "list_notebooks",
                {},
                server_config=config,
                principal=mapper.from_token(_headers("alice")["Authorization"].split()[1]),
            )
            mcp_stranger = await execute_mcp_tool(
                engine,
                "list_notebooks",
                {},
                server_config=config,
                principal=mapper.from_token(_headers("bob")["Authorization"].split()[1]),
            )
            assert isinstance(mcp_owner[0], mcp_types.TextContent)
            assert isinstance(mcp_stranger[0], mcp_types.TextContent)
            assert [item["notebook_id"] for item in json.loads(mcp_owner[0].text)["notebooks"]] == [
                notebook_id
            ]
            assert json.loads(mcp_stranger[0].text)["notebooks"] == []
            second = await client.post(
                "/v1/notebooks", headers=_headers("alice"), json={"title": "another private"}
            )
            assert second.status_code == 201, second.text
            second_id = UUID(second.json()["notebook_id"])
            first_page = await client.get(
                "/v1/notebooks", params={"limit": 1}, headers=_headers("alice")
            )
            assert first_page.status_code == 200, first_page.text
            http_cursor = first_page.json()["next_cursor"]
            assert isinstance(http_cursor, str) and http_cursor.startswith("mnc2.")
            next_page = await client.get(
                "/v1/notebooks",
                params={"limit": 1, "cursor": http_cursor},
                headers=_headers("alice"),
            )
            assert next_page.status_code == 200, next_page.text
            assert (
                next_page.json()["items"][0]["notebook_id"]
                != first_page.json()["items"][0]["notebook_id"]
            )
            assert (
                await client.get(
                    "/v1/notebooks",
                    params={"limit": 1, "cursor": http_cursor},
                    headers=_headers("bob"),
                )
            ).status_code != 200
            assert (
                await client.get(
                    "/v1/notebooks",
                    params={"limit": 2, "cursor": http_cursor},
                    headers=_headers("alice"),
                )
            ).status_code != 200
            mcp_first = await execute_mcp_tool(
                engine,
                "list_notebooks",
                {"limit": 1},
                server_config=config,
                principal=mapper.from_token(_headers("alice")["Authorization"].split()[1]),
            )
            assert isinstance(mcp_first[0], mcp_types.TextContent)
            mcp_cursor = json.loads(mcp_first[0].text)["next_cursor"]
            assert isinstance(mcp_cursor, str) and mcp_cursor.startswith("mnc2.")
            mcp_next = await execute_mcp_tool(
                engine,
                "list_notebooks",
                {"limit": 1, "cursor": mcp_cursor},
                server_config=config,
                principal=mapper.from_token(_headers("alice")["Authorization"].split()[1]),
            )
            assert isinstance(mcp_next[0], mcp_types.TextContent)
            assert len(json.loads(mcp_next[0].text)["notebooks"]) == 1
            with pytest.raises(CursorConflictError):
                await execute_mcp_tool(
                    engine,
                    "list_notebooks",
                    {"limit": 1, "cursor": mcp_cursor},
                    server_config=config,
                    principal=mapper.from_token(_headers("bob")["Authorization"].split()[1]),
                )
            authority.revoke(actor_id=owner, notebook_id=second_id)
            assert (
                await client.get(
                    "/v1/notebooks",
                    params={"limit": 1, "cursor": http_cursor},
                    headers=_headers("alice"),
                )
            ).status_code != 200
            with pytest.raises(CursorConflictError):
                await execute_mcp_tool(
                    engine,
                    "list_notebooks",
                    {"limit": 1, "cursor": mcp_cursor},
                    server_config=config,
                    principal=mapper.from_token(_headers("alice")["Authorization"].split()[1]),
                )
            authority.grant(actor_id=owner, notebook_id=second_id, role="owner", operator_id=owner)
            assert (
                await client.get(
                    "/v1/notebooks",
                    params={"limit": 1, "cursor": http_cursor},
                    headers=_headers("alice"),
                )
            ).status_code != 200
            with pytest.raises(NotFoundError):
                await execute_mcp_tool(
                    engine,
                    "query_notebook",
                    {"notebook_id": notebook_id, "question": "private"},
                    server_config=config,
                    principal=mapper.from_token(_headers("bob")["Authorization"].split()[1]),
                )
            with pytest.raises(NotFoundError):
                await execute_mcp_tool(
                    engine,
                    "search_all_notebooks",
                    {"query": "private"},
                    server_config=config,
                    principal=mapper.from_token(_headers("bob")["Authorization"].split()[1]),
                )
            summary = await execute_mcp_tool(
                engine,
                "get_notebook_summary",
                {"notebook_id": notebook_id},
                server_config=config,
                principal=mapper.from_token(_headers("alice")["Authorization"].split()[1]),
            )
            assert isinstance(summary[0], mcp_types.TextContent)
            assert json.loads(summary[0].text)["notebook_id"] == notebook_id
            with pytest.raises(NotFoundError):
                await execute_mcp_tool(
                    engine,
                    "get_notebook_summary",
                    {"notebook_id": notebook_id},
                    server_config=config,
                    principal=mapper.from_token(_headers("bob")["Authorization"].split()[1]),
                )
            assert authority.permits(owner, uuid4()) is False
            assert (
                await client.get(f"/v1/notebooks/{notebook_id}", headers=_headers("alice"))
            ).status_code == 200
            assert (
                await client.get(f"/v1/notebooks/{legacy_id}", headers=_headers("alice"))
            ).status_code == 404
            hidden = await client.get(f"/v1/notebooks/{notebook_id}", headers=_headers("bob"))
            missing = await client.get(f"/v1/notebooks/{uuid4()}", headers=_headers("bob"))
            assert hidden.status_code == missing.status_code == 404
            assert hidden.json()["error"]["code"] == missing.json()["error"]["code"]
            for path, body in (
                ("/v1/query", {"question": "private", "notebook_id": notebook_id}),
                ("/v1/search", {"query": "private", "notebook_id": notebook_id}),
            ):
                denied = await client.post(path, headers=_headers("bob"), json=body)
                nonexistent = await client.post(
                    path, headers=_headers("bob"), json={**body, "notebook_id": str(uuid4())}
                )
                unassigned = await client.post(
                    path, headers=_headers("alice"), json={**body, "notebook_id": str(legacy_id)}
                )
                assert (
                    denied.status_code == nonexistent.status_code == unassigned.status_code == 404
                )
                assert denied.json()["error"]["code"] == nonexistent.json()["error"]["code"]
                assert (await client.post(path, json=body)).status_code == 401
                engine.server_scope_authority = None
                try:
                    unavailable = await client.post(path, headers=_headers("alice"), json=body)
                    assert unavailable.status_code == 503
                finally:
                    engine.server_scope_authority = authority
            with pytest.raises(PermissionError):
                await QueryService(engine, MagicMock()).execute_query(
                    QueryRequest(question="private", notebook_id=UUID(notebook_id))
                )
            with pytest.raises(PermissionError):
                await SearchService(engine).execute_search(
                    SearchRequest(query="private", notebook_id=UUID(notebook_id))
                )
            # Source reads are now principal-first; other unadapted routes
            # still refuse serving under an attached ACL.
            hidden_source = await client.get(
                f"/v1/notebooks/{notebook_id}/sources", headers=_headers("bob")
            )
            assert hidden_source.status_code == 404
            assert (await client.get("/jobs", headers=_headers("bob"))).status_code == 503
            assert (await client.get("/config/models", headers=_headers("bob"))).status_code == 503
            assert (
                await client.get("/v2/capabilities", headers=_headers("bob"))
            ).status_code == 404
            hidden_capabilities = await client.get(
                "/v2/capabilities", headers=_headers("bob"), params={"notebook_id": notebook_id}
            )
            absent_capabilities = await client.get(
                "/v2/capabilities", headers=_headers("bob"), params={"notebook_id": str(uuid4())}
            )
            assert hidden_capabilities.status_code == absent_capabilities.status_code == 404
            assert (
                hidden_capabilities.json()["error"]["code"]
                == absent_capabilities.json()["error"]["code"]
            )
            assert (
                await client.get(
                    f"/v2/notebooks/{notebook_id}/documents/{uuid4()}/versions/{uuid4()}",
                    headers=_headers("bob"),
                )
            ).status_code == 404
            assert (
                await client.post(
                    "/v2/retrieval/evidence",
                    headers=_headers("bob"),
                    json={
                        "query": "private",
                        "mode": "exhaustive",
                        "scope": {"notebook_id": notebook_id},
                        "representations": ["canonical_text"],
                    },
                )
            ).status_code == 404
            assert (await client.get("/v1/notebooks", headers=_headers("bob"))).json()[
                "items"
            ] == []
            authority.grant(
                actor_id=reader,
                notebook_id=UUID(notebook_id),
                role="reader",
                operator_id=owner,
            )
            assert (
                await client.get(f"/v1/notebooks/{notebook_id}", headers=_headers("bob"))
            ).status_code == 200
            assert (
                await client.patch(
                    f"/v1/notebooks/{notebook_id}",
                    headers=_headers("bob"),
                    json={"title": "changed"},
                )
            ).status_code == 404
            original_list_insights = store.list_insights

            async def revoke_during_insights(*args: Any, **kwargs: Any) -> Any:
                authority.revoke(actor_id=reader, notebook_id=UUID(notebook_id))
                return await original_list_insights(*args, **kwargs)

            monkeypatch.setattr(store, "list_insights", revoke_during_insights)
            revoked_response = await client.get(
                f"/v1/notebooks/{notebook_id}/summary", headers=_headers("bob")
            )
            assert revoked_response.status_code == 404
            monkeypatch.setattr(store, "list_insights", original_list_insights)
            authority.grant(
                actor_id=reader,
                notebook_id=UUID(notebook_id),
                role="reader",
                operator_id=owner,
            )
            monkeypatch.setattr(store, "list_insights", revoke_during_insights)
            with pytest.raises(NotFoundError):
                await execute_mcp_tool(
                    engine,
                    "get_notebook_summary",
                    {"notebook_id": notebook_id},
                    server_config=config,
                    principal=mapper.from_token(_headers("bob")["Authorization"].split()[1]),
                )
            monkeypatch.setattr(store, "list_insights", original_list_insights)
            update_entered = asyncio.Event()
            release_update = asyncio.Event()
            revoke_finished = Event()
            original_upsert_notebook = store.upsert_notebook

            async def held_notebook_update(value: Notebook) -> None:
                update_entered.set()
                await release_update.wait()
                await original_upsert_notebook(value)

            def revoke_updating_owner() -> None:
                authority.revoke(actor_id=owner, notebook_id=UUID(notebook_id))
                revoke_finished.set()

            with monkeypatch.context() as patch:
                patch.setattr(store, "upsert_notebook", held_notebook_update)
                updating = asyncio.create_task(
                    client.patch(
                        f"/v1/notebooks/{notebook_id}",
                        headers=_headers("alice"),
                        json={"title": "held owner update"},
                    )
                )
                await asyncio.wait_for(update_entered.wait(), timeout=5)
                revoker = Thread(target=revoke_updating_owner, daemon=True)
                revoker.start()
                try:
                    assert not revoke_finished.wait(0.05)
                finally:
                    release_update.set()
                updated = await updating
                revoker.join(timeout=5)
                assert not revoker.is_alive() and revoke_finished.is_set()
            assert updated.status_code == 200, updated.text
            assert (
                await client.get(f"/v1/notebooks/{notebook_id}", headers=_headers("alice"))
            ).status_code == 404
            authority.grant(
                actor_id=owner, notebook_id=UUID(notebook_id), role="owner", operator_id=owner
            )
            original_retire = authority.retire_notebook

            def revoke_before_retire(selected: UUID, *, operator_id: UUID | None = None) -> None:
                authority.revoke(actor_id=owner, notebook_id=selected)
                original_retire(selected, operator_id=operator_id)

            monkeypatch.setattr(authority, "retire_notebook", revoke_before_retire)
            raced_delete = await client.delete(
                f"/v1/notebooks/{notebook_id}", headers=_headers("alice")
            )
            assert raced_delete.status_code == 404
            assert await store.get_notebook(UUID(notebook_id)) is not None
            assert authority.revision(UUID(notebook_id)) is not None
            monkeypatch.setattr(authority, "retire_notebook", original_retire)
            authority.grant(
                actor_id=owner, notebook_id=UUID(notebook_id), role="owner", operator_id=owner
            )
            assert (
                await client.delete(f"/v1/notebooks/{notebook_id}", headers=_headers("alice"))
            ).status_code == 204
            assert (
                await client.get(f"/v1/notebooks/{notebook_id}", headers=_headers("bob"))
            ).status_code == 404
    finally:
        await store.close()
