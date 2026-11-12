"""ACL automatic retrieval through the concrete indexed-fixture engine and adapters."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo.interfaces import DependencyUnavailableError, NotFoundError, Page
from mnemo.models import Insight, InsightType, Source
from mnemo.models.multimodal import FinalQARequestV2, FinalQAResultV2
from mnemo.retrieval.multimodal import FinalQAV2Orchestrator
from mnemo.storage.sqlite import SQLiteStore
from mnemo_server.app import create_app as create_direct_app
from mnemo_server.mcp.tools import execute_mcp_tool
from mnemo_server.services.delivery import build_delivery_service_for_storage
from mnemo_server.services.ingestion import IngestionService
from mnemo_server.services.insights import InsightService
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority
from mnemo_server.services.trusted_actor import TrustedJWTActorMapper
from test_mcp_immutable_schema_matrix import _fixture, create_app
from test_module_892_retrieval_routes import _SECRET, _headers


class _FixtureEngine(KnowledgeEngine):
    """Typed view of the bindings attached to this disposable engine."""

    server_scope_authority: SQLiteNotebookScopeAuthority
    server_actor_mapper: TrustedJWTActorMapper
    _disposable_index_readiness_check: Callable[[], None]


@pytest.mark.anyio
async def test_real_engine_insight_read_route_enforces_source_ancestry_and_acl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, reader, base_config, identities = await _fixture(tmp_path, legacy=False)
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", _SECRET)
    owner = mapper.from_token(_headers("alice")["Authorization"].split()[1])
    permitted_reader = mapper.from_token(_headers("carol")["Authorization"].split()[1])
    notebook_id, source_id = identities[0][0], identities[0][3]
    authority.grant(
        actor_id=owner.actor_id, notebook_id=notebook_id, role="owner", operator_id=owner.actor_id
    )
    authority.grant(
        actor_id=permitted_reader.actor_id,
        notebook_id=notebook_id,
        role="reader",
        operator_id=owner.actor_id,
    )
    fixture_engine = cast(_FixtureEngine, engine)
    fixture_engine.server_scope_authority = authority
    fixture_engine.server_actor_mapper = mapper
    config = base_config.model_copy(update={"auth_mode": "jwt", "jwt_secret": _SECRET})
    app = create_app(engine=engine, server_config=config, provision_tokenizer_on_startup=False)
    app.state.engine = engine
    app.state.server_config = config
    writer = SQLiteStore(tmp_path / "matrix.db")
    await writer.open()
    try:
        await writer.upsert_insight(
            Insight(
                insight_id=UUID(int=201),
                notebook_id=notebook_id,
                source_id=source_id,
                type=InsightType.KEY_FACT,
                content="private source insight",
                created_at=datetime.now(UTC),
            )
        )
    finally:
        await writer.close()
    await reader.close()
    await reader.open()
    path = f"/v1/notebooks/{notebook_id}/insights"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fixture") as http:
            for subject in ("alice", "carol"):
                served = await http.get(path, headers=_headers(subject))
                assert served.status_code == 200, served.text
                assert any(
                    item["content"] == "private source insight" for item in served.json()["items"]
                )
            first = await http.get(path, params={"limit": 1}, headers=_headers("alice"))
            assert first.status_code == 200
            owner_cursor = first.json()["next_cursor"]
            assert isinstance(owner_cursor, str) and owner_cursor.startswith("mnc2.")
            continued = await http.get(
                path, params={"limit": 1, "cursor": owner_cursor}, headers=_headers("alice")
            )
            assert continued.status_code == 200, continued.text
            assert (
                continued.json()["items"][0]["insight_id"] != first.json()["items"][0]["insight_id"]
            )
            assert (
                await http.get(
                    path, params={"limit": 1, "cursor": owner_cursor}, headers=_headers("carol")
                )
            ).status_code != 200
            assert (
                await http.get(
                    path,
                    params={"limit": 1, "cursor": owner_cursor, "type": "key_fact"},
                    headers=_headers("alice"),
                )
            ).status_code != 200
            reader_first = await http.get(path, params={"limit": 1}, headers=_headers("carol"))
            reader_cursor = reader_first.json()["next_cursor"]
            outsider = await http.get(path, headers=_headers("bob"))
            assert outsider.status_code == 404
            assert "private source insight" not in outsider.text
            assert (await http.get(path)).status_code != 200
            with pytest.raises(PermissionError):
                await InsightService(engine).list_insights(notebook_id, 50, None)

            original_list = reader.list_insights

            async def revoke_after_read(
                selected: UUID, limit: int, cursor: str | None
            ) -> Page[Insight]:
                page = await original_list(selected, limit=limit, cursor=cursor)
                authority.revoke(actor_id=permitted_reader.actor_id, notebook_id=notebook_id)
                return page

            monkeypatch.setattr(reader, "list_insights", revoke_after_read)
            revoked = await http.get(path, headers=_headers("carol"))
            assert revoked.status_code == 404
            assert "private source insight" not in revoked.text
            authority.grant(
                actor_id=permitted_reader.actor_id,
                notebook_id=notebook_id,
                role="reader",
                operator_id=owner.actor_id,
            )
            assert (
                await http.get(
                    path,
                    params={"limit": 1, "cursor": reader_cursor},
                    headers=_headers("carol"),
                )
            ).status_code != 200

            monkeypatch.undo()
            await reader.close()
            await writer.open()
            try:
                await writer.upsert_insight(
                    Insight(
                        insight_id=UUID(int=202),
                        notebook_id=notebook_id,
                        source_id=identities[1][3],
                        type=InsightType.CLAIM,
                        content="foreign source insight",
                        created_at=datetime.now(UTC),
                    )
                )
            finally:
                await writer.close()
            await reader.open()
            foreign = await http.get(path, headers=_headers("alice"))
            assert foreign.status_code == 404
            assert "foreign source insight" not in foreign.text
    finally:
        await reader.close()


@pytest.mark.anyio
async def test_real_engine_automatic_scope_is_membership_first(tmp_path: Path) -> None:
    engine, reader, base_config, identities = await _fixture(tmp_path, legacy=False)
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", _SECRET)
    owner = mapper.from_token(_headers("alice")["Authorization"].split()[1])
    stranger = mapper.from_token(_headers("bob")["Authorization"].split()[1])
    reader_actor = mapper.from_token(_headers("carol")["Authorization"].split()[1])
    notebook_id = identities[0][0]
    authority.grant(
        actor_id=owner.actor_id, notebook_id=notebook_id, role="owner", operator_id=owner.actor_id
    )
    authority.grant(
        actor_id=reader_actor.actor_id,
        notebook_id=notebook_id,
        role="reader",
        operator_id=owner.actor_id,
    )
    fixture_engine = cast(_FixtureEngine, engine)
    fixture_engine.server_scope_authority = authority
    fixture_engine.server_actor_mapper = mapper
    admission = fixture_engine._disposable_index_readiness_check
    config = base_config.model_copy(update={"auth_mode": "jwt", "jwt_secret": _SECRET})
    app = create_app(engine=engine, server_config=config, provision_tokenizer_on_startup=False)
    app.state.engine = engine
    app.state.server_config = config
    body = {"query": "schema evidence", "mode": "exhaustive", "evidence_budget": 1}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fixture") as http:
            served = await http.post(
                "/v2/retrieval/automatic", json=body, headers=_headers("alice")
            )
            assert served.status_code == 200, served.text
            assert served.json()["notebook_id"] == str(notebook_id)
            assert all(
                item["notebook_id"] == str(notebook_id)
                for item in served.json()["evidence"]["items"]
            )
            denied = await http.post("/v2/retrieval/automatic", json=body, headers=_headers("bob"))
            assert denied.status_code != 200
            assert "schema evidence" not in denied.text
            reader_result = await http.post(
                "/v2/retrieval/automatic", json=body, headers=_headers("carol")
            )
            assert reader_result.status_code == 200, reader_result.text
            assert reader_result.json()["notebook_id"] == str(notebook_id)
            authority.revoke(actor_id=reader_actor.actor_id, notebook_id=notebook_id)
            revoked = await http.post(
                "/v2/retrieval/automatic", json=body, headers=_headers("carol")
            )
            assert revoked.status_code != 200
            assert "schema evidence" not in revoked.text
        mcp = await execute_mcp_tool(
            engine,
            "query_notebook_v2",
            body,
            config,
            owner,
            indexed_fixture_readiness_check=admission,
        )
        assert mcp
        timeline = await execute_mcp_tool(
            engine,
            "get_timeline",
            {"notebook_id": str(notebook_id)},
            config,
            owner,
            indexed_fixture_readiness_check=admission,
        )
        assert timeline
        source_insights = await execute_mcp_tool(
            engine,
            "get_source_insights",
            {"source_id": str(identities[0][3])},
            config,
            owner,
            indexed_fixture_readiness_check=admission,
        )
        assert source_insights
        with pytest.raises(NotFoundError):
            await execute_mcp_tool(
                engine,
                "get_timeline",
                {"notebook_id": str(notebook_id)},
                config,
                stranger,
                indexed_fixture_readiness_check=admission,
            )
        with pytest.raises(NotFoundError):
            await execute_mcp_tool(
                engine,
                "get_source_insights",
                {"source_id": str(identities[0][3])},
                config,
                stranger,
                indexed_fixture_readiness_check=admission,
            )
        with pytest.raises(DependencyUnavailableError):
            await execute_mcp_tool(
                engine,
                "query_notebook_v2",
                body,
                config,
                stranger,
                indexed_fixture_readiness_check=admission,
            )
    finally:
        await reader.close()


@pytest.mark.anyio
async def test_real_engine_source_read_routes_are_scoped_and_writes_stay_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, reader, base_config, identities = await _fixture(tmp_path, legacy=False)
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", _SECRET)
    owner = mapper.from_token(_headers("alice")["Authorization"].split()[1])
    reader_actor = mapper.from_token(_headers("carol")["Authorization"].split()[1])
    notebook_id, source_id = identities[0][0], identities[0][3]
    authority.grant(
        actor_id=owner.actor_id, notebook_id=notebook_id, role="owner", operator_id=owner.actor_id
    )
    authority.grant(
        actor_id=reader_actor.actor_id,
        notebook_id=notebook_id,
        role="reader",
        operator_id=owner.actor_id,
    )
    fixture_engine = cast(_FixtureEngine, engine)
    fixture_engine.server_scope_authority = authority
    fixture_engine.server_actor_mapper = mapper
    config = base_config.model_copy(update={"auth_mode": "jwt", "jwt_secret": _SECRET})
    app = create_app(engine=engine, server_config=config, provision_tokenizer_on_startup=False)
    app.state.engine = engine
    app.state.server_config = config
    base = f"/v1/notebooks/{notebook_id}/sources"
    writer = SQLiteStore(tmp_path / "matrix.db")
    await reader.close()
    await writer.open()
    try:
        await writer.upsert_source(
            Source(
                source_id=UUID(int=203),
                notebook_id=notebook_id,
                document_id=identities[1][1],
                created_at=datetime.now(UTC),
            )
        )
    finally:
        await writer.close()
    await reader.open()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fixture") as http:
            for subject in ("alice", "carol"):
                listed = await http.get(base, headers=_headers(subject))
                assert listed.status_code == 200, listed.text
                assert {item["source_id"] for item in listed.json()["items"]} == {
                    str(source_id),
                    str(UUID(int=203)),
                }
                detail = await http.get(f"{base}/{source_id}", headers=_headers(subject))
                status = await http.get(f"{base}/{source_id}/status", headers=_headers(subject))
                assert detail.status_code == status.status_code == 200
                assert detail.json()["notebook_id"] == str(notebook_id)
                assert status.json()["notebook_id"] == str(notebook_id)
            first = await http.get(base, params={"limit": 1}, headers=_headers("alice"))
            assert first.status_code == 200, first.text
            owner_cursor = first.json()["next_cursor"]
            assert isinstance(owner_cursor, str) and owner_cursor.startswith("mnc2.")
            continued = await http.get(
                base, params={"limit": 1, "cursor": owner_cursor}, headers=_headers("alice")
            )
            assert continued.status_code == 200, continued.text
            assert (
                continued.json()["items"][0]["source_id"] != first.json()["items"][0]["source_id"]
            )
            assert (
                await http.get(
                    base, params={"limit": 1, "cursor": owner_cursor}, headers=_headers("carol")
                )
            ).status_code != 200
            assert (
                await http.get(
                    base, params={"limit": 2, "cursor": owner_cursor}, headers=_headers("alice")
                )
            ).status_code != 200
            assert (
                await http.get(
                    base,
                    params={"limit": 1, "cursor": owner_cursor + "x"},
                    headers=_headers("alice"),
                )
            ).status_code != 200
            reader_first = await http.get(base, params={"limit": 1}, headers=_headers("carol"))
            reader_cursor = reader_first.json()["next_cursor"]
            for url in (base, f"{base}/{source_id}", f"{base}/{source_id}/status"):
                hidden = await http.get(url, headers=_headers("bob"))
                assert hidden.status_code == 404
                assert str(source_id) not in hidden.text
                assert (await http.get(url)).status_code == 401
            assert (
                await http.delete(f"{base}/{source_id}", headers=_headers("alice"))
            ).status_code == 503
            original_list = SQLiteStore.list_sources

            async def list_then_revoke(
                self: SQLiteStore, notebook_id: UUID, limit: int, cursor: str | None
            ) -> Page[Source]:
                page = await original_list(self, notebook_id, limit, cursor)
                authority.revoke(actor_id=reader_actor.actor_id, notebook_id=notebook_id)
                return page

            with monkeypatch.context() as patch:
                patch.setattr(SQLiteStore, "list_sources", list_then_revoke)
                in_flight = await http.get(base, headers=_headers("carol"))
            assert in_flight.status_code == 404
            assert str(source_id) not in in_flight.text
            assert (await http.get(base, headers=_headers("carol"))).status_code == 404
            authority.grant(
                actor_id=reader_actor.actor_id,
                notebook_id=notebook_id,
                role="reader",
                operator_id=owner.actor_id,
            )
            assert (
                await http.get(
                    base, params={"limit": 1, "cursor": reader_cursor}, headers=_headers("carol")
                )
            ).status_code != 200
        service = IngestionService(engine, MagicMock())
        with pytest.raises(PermissionError):
            await service.get_source(notebook_id=notebook_id, source_id=source_id)
        with pytest.raises(PermissionError):
            await service.list_sources(notebook_id=notebook_id)
        with pytest.raises(PermissionError):
            await service.get_source_status(notebook_id=notebook_id, source_id=source_id)
        with pytest.raises(PermissionError):
            await service.delete_source(notebook_id=notebook_id, source_id=source_id)
        with pytest.raises(DependencyUnavailableError):
            await service.ingest_source(notebook_id=notebook_id, filename="denied.txt", data=b"no")
    finally:
        await reader.close()


@pytest.mark.anyio
async def test_disposable_source_delete_uses_owner_acl_and_store_transaction(
    tmp_path: Path,
) -> None:
    _, reader, base_config, identities = await _fixture(tmp_path, legacy=False)
    await reader.close()
    store = SQLiteStore(tmp_path / "matrix.db")
    await store.open()
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", _SECRET)
    owner = mapper.from_token(_headers("alice")["Authorization"].split()[1])
    reader_actor = mapper.from_token(_headers("carol")["Authorization"].split()[1])
    notebook_id, source_id = identities[0][0], identities[0][3]
    authority.grant(
        actor_id=owner.actor_id, notebook_id=notebook_id, role="owner", operator_id=owner.actor_id
    )
    authority.grant(
        actor_id=reader_actor.actor_id,
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
    config = base_config.model_copy(
        update={"auth_mode": "jwt", "jwt_secret": _SECRET, "production_mode": False}
    )
    app = create_direct_app(
        engine=engine, server_config=config, provision_tokenizer_on_startup=False
    )
    app.state.engine = engine
    app.state.server_config = config
    app.state.token_counter = MagicMock()
    target = f"/v1/notebooks/{notebook_id}/sources/{source_id}"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fixture") as http:
            for subject in ("carol", "bob"):
                denied = await http.delete(target, headers=_headers(subject))
                assert denied.status_code == 404
            assert (await http.delete(target)).status_code == 401
            authority.revoke(actor_id=owner.actor_id, notebook_id=notebook_id)
            assert (await http.delete(target, headers=_headers("alice"))).status_code == 404
            assert await store.get_source(source_id) is not None
            authority.grant(
                actor_id=owner.actor_id,
                notebook_id=notebook_id,
                role="owner",
                operator_id=owner.actor_id,
            )
            deleted = await http.delete(target, headers=_headers("alice"))
            assert deleted.status_code == 204, deleted.text
            assert await store.get_source(source_id) is None
            assert (await http.delete(target, headers=_headers("alice"))).status_code == 404
    finally:
        await store.close()


@pytest.mark.anyio
async def test_real_engine_final_qa_requires_owner_and_live_acl(tmp_path: Path) -> None:
    engine, reader, base_config, identities = await _fixture(
        tmp_path, legacy=False, final_qa_ready=True
    )
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", _SECRET)
    owner = mapper.from_token(_headers("alice")["Authorization"].split()[1])
    reader_actor = mapper.from_token(_headers("carol")["Authorization"].split()[1])
    notebook_id = identities[0][0]
    assert notebook_id == UUID(int=1)
    authority.grant(
        actor_id=owner.actor_id, notebook_id=notebook_id, role="owner", operator_id=owner.actor_id
    )
    authority.grant(
        actor_id=reader_actor.actor_id,
        notebook_id=notebook_id,
        role="reader",
        operator_id=owner.actor_id,
    )
    fixture_engine = cast(_FixtureEngine, engine)
    fixture_engine.server_scope_authority = authority
    fixture_engine.server_actor_mapper = mapper
    config = base_config.model_copy(update={"auth_mode": "jwt", "jwt_secret": _SECRET})
    engine._delivery_service = build_delivery_service_for_storage(
        reader, reader, config, execution_store=reader.qa_store
    )
    app = create_app(engine=engine, server_config=config, provision_tokenizer_on_startup=False)
    app.state.engine = engine
    app.state.server_config = config
    body = {
        "notebook_id": str(notebook_id),
        "session_id": str(UUID(int=2)),
        "user_turn_id": str(UUID(int=3)),
        "assistant_turn_id": str(UUID(int=4)),
        "question": "schema evidence",
        "provider_profile": "final_qa_v2:transport",
        "publication_policy": "allow_partial",
        "evidence_request_or_snapshot": {
            "query": "schema evidence",
            "mode": "ranked",
            "scope": {"notebook_id": str(notebook_id)},
            "representations": ["canonical_text"],
        },
    }
    path = f"/v2/notebooks/{notebook_id}/final-qa"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fixture") as http:
            denied_reader = await http.post(path, json=body, headers=_headers("carol"))
            assert denied_reader.status_code != 200
            denied_stranger = await http.post(path, json=body, headers=_headers("bob"))
            assert denied_stranger.status_code != 200
            served = await http.post(path, json=body, headers=_headers("alice"))
            assert served.status_code == 200, served.text
            assert served.json()["answer"]
            evidence_path = f"{path}/{body['assistant_turn_id']}/evidence"
            owner_evidence = await http.get(evidence_path, headers=_headers("alice"))
            assert owner_evidence.status_code == 200, owner_evidence.text
            assert owner_evidence.json()["items"]
            assert (await http.get(evidence_path, headers=_headers("carol"))).status_code == 404
            assert (await http.get(evidence_path, headers=_headers("bob"))).status_code == 404
            mcp = await execute_mcp_tool(
                engine,
                "run_final_qa_v2",
                body,
                config,
                owner,
                indexed_fixture_readiness_check=fixture_engine._disposable_index_readiness_check,
            )
            assert mcp
            with pytest.raises(NotFoundError):
                await execute_mcp_tool(
                    engine,
                    "run_final_qa_v2",
                    body,
                    config,
                    reader_actor,
                    indexed_fixture_readiness_check=fixture_engine._disposable_index_readiness_check,
                )
            authority.revoke(actor_id=owner.actor_id, notebook_id=notebook_id)
            revoked = await http.post(path, json=body, headers=_headers("alice"))
            assert revoked.status_code != 200
            assert (await http.get(evidence_path, headers=_headers("alice"))).status_code == 404
    finally:
        await reader.close()


@pytest.mark.anyio
async def test_real_engine_final_qa_revocation_before_disclosure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, reader, base_config, identities = await _fixture(
        tmp_path, legacy=False, final_qa_ready=True
    )
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", _SECRET)
    owner = mapper.from_token(_headers("alice")["Authorization"].split()[1])
    notebook_id = identities[0][0]
    authority.grant(
        actor_id=owner.actor_id, notebook_id=notebook_id, role="owner", operator_id=owner.actor_id
    )
    fixture_engine = cast(_FixtureEngine, engine)
    fixture_engine.server_scope_authority = authority
    fixture_engine.server_actor_mapper = mapper
    config = base_config.model_copy(update={"auth_mode": "jwt", "jwt_secret": _SECRET})
    app = create_app(engine=engine, server_config=config, provision_tokenizer_on_startup=False)
    app.state.engine = engine
    app.state.server_config = config
    original_execute = FinalQAV2Orchestrator.execute

    async def execute_then_revoke(
        self: FinalQAV2Orchestrator, request: FinalQARequestV2
    ) -> FinalQAResultV2:
        result = await original_execute(self, request)
        authority.revoke(actor_id=owner.actor_id, notebook_id=notebook_id)
        return result

    monkeypatch.setattr(FinalQAV2Orchestrator, "execute", execute_then_revoke)
    body = {
        "notebook_id": str(notebook_id),
        "session_id": str(UUID(int=2)),
        "user_turn_id": str(UUID(int=3)),
        "assistant_turn_id": str(UUID(int=99)),
        "question": "schema evidence",
        "provider_profile": "final_qa_v2:transport",
        "publication_policy": "allow_partial",
        "evidence_request_or_snapshot": {
            "query": "schema evidence",
            "mode": "ranked",
            "scope": {"notebook_id": str(notebook_id)},
            "representations": ["canonical_text"],
        },
    }
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fixture") as http:
            response = await http.post(
                f"/v2/notebooks/{notebook_id}/final-qa", json=body, headers=_headers("alice")
            )
            assert response.status_code != 200
            assert "Grounded" not in response.text
    finally:
        await reader.close()
