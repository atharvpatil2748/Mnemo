"""Disposable HTTP evidence pagination through the real SQLite retrieval source."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import mcp.types as mcp_types
import pytest
from httpx import ASGITransport, AsyncClient
from mnemo.cursors import CursorConflictError
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo.interfaces import DeliveryCursorConflictError, NotFoundError
from mnemo.models import (
    Asset,
    AssetContainerKind,
    AssetExtractionProvenance,
    AssetLocator,
    AssetLocatorKind,
    AssetOccurrence,
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    DocType,
    Document,
    DocumentBinaryReference,
    DocumentBinaryRole,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    FrozenMetadata,
    Notebook,
    ParsedDocument,
    Source,
    TextBlock,
    asset_occurrence_id,
)
from mnemo.retrieval import AdvancedRetrievalService, RetrievalCursorCodec
from mnemo.retrieval.advanced_sources import CanonicalTextAdvancedSource
from mnemo.storage.sqlite import SQLiteStore
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig
from mnemo_server.mcp.tools import execute_mcp_tool
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority
from mnemo_server.services.trusted_actor import TrustedJWTActorMapper

_SECRET = "fixture-membership-jwt-secret-32-bytes"


class _IndexedFixtureEngine(KnowledgeEngine):
    """Typed view of explicitly attached disposable serving dependencies."""

    server_scope_authority: SQLiteNotebookScopeAuthority
    server_actor_mapper: TrustedJWTActorMapper
    _disposable_index_readiness_check: Callable[[], None]


class _ParsedSQLiteStore(SQLiteStore):
    """Real SQLite membership/chunks plus disposable parsed-block backing."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self._parsed: dict[UUID, ParsedDocument] = {}
        self._asset_bytes: dict[UUID, bytes] = {}

    async def put_parsed_document(self, version_id: UUID, document: ParsedDocument) -> None:
        self._parsed[version_id] = document

    async def get_parsed_document(self, version_id: UUID) -> ParsedDocument | None:
        return self._parsed.get(version_id)

    async def get_asset(self, asset_id: UUID) -> bytes | None:
        return self._asset_bytes.get(asset_id)


async def _seed_asset(store: _ParsedSQLiteStore, document_id: UUID, version_id: UUID) -> UUID:
    content = b"fixture-image-bytes"
    asset = Asset(
        asset_id=uuid4(),
        mime_type="image/png",
        content_hash=hashlib.sha256(content).hexdigest(),
        storage_uri="fixture://disposable",
        metadata=FrozenMetadata({"fixture": True}),
    )
    locator = AssetLocator(kind=AssetLocatorKind.PDF_PAGE, ordinal=0, page_number=1)
    occurrence = AssetOccurrence(
        occurrence_id=asset_occurrence_id(
            document_id=document_id,
            version_id=version_id,
            asset_id=asset.asset_id,
            locator=locator,
        ),
        asset_id=asset.asset_id,
        document_id=document_id,
        version_id=version_id,
        container_kind=AssetContainerKind.PDF,
        locator=locator,
        authored_alt_text="Fixture diagram",
        extraction_provenance=AssetExtractionProvenance(
            parser_id="fixture", parser_version="1", block_ordinal=0
        ),
        created_at=datetime.now(UTC),
    )
    await store.register_asset_ingestion(
        assets=(asset,),
        binary_reference=DocumentBinaryReference(
            document_id=document_id,
            version_id=version_id,
            asset_id=asset.asset_id,
            role=DocumentBinaryRole.ORIGINAL,
            media_type="image/png",
            byte_size=len(content),
            created_at=datetime.now(UTC),
        ),
        occurrences=(occurrence,),
    )
    store._asset_bytes[asset.asset_id] = content
    return occurrence.occurrence_id


def _headers(subject: str) -> dict[str, str]:
    def encoded(value: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

    claims: dict[str, object] = {
        "iss": "fixture-issuer",
        "aud": "fixture-audience",
        "sub": subject,
        "exp": int(time.time()) + 120,
    }
    signed = f"{encoded({'alg': 'HS256'})}.{encoded(claims)}"
    digest = hmac.new(_SECRET.encode(), signed.encode(), hashlib.sha256).digest()
    return {
        "Authorization": f"Bearer {signed}.{base64.urlsafe_b64encode(digest).rstrip(b'=').decode()}"
    }


class _UnusedSparseRetriever:
    retrieval_mode = "sparse"

    def capabilities(self) -> object:
        raise AssertionError("ranked retrieval is not used by this exhaustive fixture")

    async def retrieve(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("ranked retrieval is not used by this exhaustive fixture")


async def _seed_document(store: SQLiteStore, notebook_id: UUID, index: int) -> UUID:
    now = datetime.now(UTC)
    document_id, version_id, source_id = uuid4(), uuid4(), uuid4()
    content_hash = f"{index + 1:064x}"
    version = DocumentVersion(
        version_id=version_id,
        document_id=document_id,
        content_hash=content_hash,
        metadata=DocumentMetadata(content_hash=content_hash, title=f"Fixture {index}"),
        status=DocumentVersionStatus.CURRENT,
        created_at=now,
    )
    await store.upsert_document(
        Document(
            document_id=document_id,
            versions=(version,),
            current_version_id=version_id,
            current_hash=content_hash,
            status=DocumentStatus.INDEXED,
            created_at=now,
            updated_at=now,
        )
    )
    await store.upsert_source(
        Source(
            source_id=source_id, notebook_id=notebook_id, document_id=document_id, created_at=now
        )
    )
    await store.upsert_chunks(
        (
            Chunk(
                id=f"{index + 1:064x}",
                document_id=document_id,
                version_id=version_id,
                text=f"target evidence {index}",
                chunk_type=ChunkType.PASSAGE,
                position=ChunkPosition(section_index=0, chunk_index_in_section=index),
                source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
                heading_path=(),
            ),
        )
    )
    await store.put_parsed_document(
        version_id,
        ParsedDocument(
            blocks=(
                TextBlock(ordinal=0, text=f"target block {index} a"),
                TextBlock(ordinal=1, text=f"target block {index} b"),
            ),
            metadata=version.metadata,
            language="en",
            doc_type=DocType.GENERIC,
        ),
    )
    return document_id


def _request(notebook_id: UUID, *, cursor: str | None = None) -> dict[str, object]:
    body: dict[str, object] = {
        "query": "target",
        "mode": "exhaustive",
        "scope": {"notebook_id": str(notebook_id)},
        "representations": ["canonical_text"],
        "evidence_budget": 1,
    }
    if cursor is not None:
        body["cursor"] = cursor
    return body


@pytest.mark.anyio
async def test_http_acl_revision_binds_real_evidence_cursor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _ParsedSQLiteStore(tmp_path / "indexed-fixture.db")
    await store.open()
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", _SECRET)
    owner = mapper.from_token(_headers("alice")["Authorization"].split()[1]).actor_id
    outsider = mapper.from_token(_headers("bob")["Authorization"].split()[1]).actor_id
    notebook_id, other_id, legacy_id = uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)
    for identity in (notebook_id, other_id, legacy_id):
        await store.upsert_notebook(
            Notebook(notebook_id=identity, title="Fixture", created_at=now, updated_at=now)
        )
    first_document_id = await _seed_document(store, notebook_id, 0)
    await _seed_document(store, notebook_id, 1)
    other_document_id = await _seed_document(store, other_id, 2)
    authority.grant(actor_id=owner, notebook_id=notebook_id, role="owner", operator_id=owner)
    authority.grant(actor_id=outsider, notebook_id=other_id, role="owner", operator_id=outsider)
    source = CanonicalTextAdvancedSource(
        store=store,
        ranked_retriever=_UnusedSparseRetriever(),  # type: ignore[arg-type]
    )
    retrieval = AdvancedRetrievalService(
        sources=(source,),
        cursor_codec=RetrievalCursorCodec(b"fixture-retrieval-signing-secret-32-bytes"),
    )
    engine = MagicMock(spec=KnowledgeEngine)
    engine.storage = store
    engine.asset_catalog = store
    engine.delivery_service = None
    engine.state = EngineState.READY
    engine.initialize = AsyncMock()
    engine.shutdown = AsyncMock()
    engine.advanced_retrieval = retrieval
    engine.full_multilingual_v2_alias_digest = None
    fixture_engine = cast(_IndexedFixtureEngine, engine)
    fixture_engine.server_scope_authority = authority
    fixture_engine.server_actor_mapper = mapper
    config = ServerConfig(
        auth_mode="jwt",
        jwt_secret=_SECRET,
        delivery_cursor_secret="fixture-delivery-cursor-secret-32-bytes",
    )
    app = create_app(server_config=config, engine=engine, provision_tokenizer_on_startup=False)
    app.state.engine = engine
    app.state.server_config = config
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            stored = await store.get_document(first_document_id)
            assert stored is not None
            occurrence_id = await _seed_asset(store, first_document_id, stored.current_version_id)
            asset_url = f"/v2/notebooks/{notebook_id}/asset-occurrences/{occurrence_id}/content"
            first_asset = await client.get(
                asset_url, headers=_headers("alice"), params={"max_bytes": 8}
            )
            assert first_asset.status_code == 206, first_asset.text
            assert first_asset.content == b"fixture-"
            asset_cursor = first_asset.headers["x-mnemo-next-cursor"]
            assert asset_cursor
            second_asset = await client.get(
                asset_url,
                headers=_headers("alice"),
                params={"max_bytes": 8, "cursor": asset_cursor},
            )
            assert second_asset.status_code == 206, second_asset.text
            assert second_asset.content == b"image-by"
            assert (await client.get(asset_url, headers=_headers("bob"))).status_code == 404
            assert (await client.get(asset_url, headers={})).status_code == 401
            chunk_url = (
                f"/v2/notebooks/{notebook_id}/documents/{first_document_id}"
                f"/versions/{stored.current_version_id}/chunks/{1:064x}"
            )
            exact = await client.get(chunk_url, headers=_headers("alice"))
            assert exact.status_code == 200, exact.text
            assert exact.json()["items"][0]["payload"]["text"] == "target evidence 0"
            alice_principal = mapper.from_token(_headers("alice")["Authorization"].split()[1])
            bob_principal = mapper.from_token(_headers("bob")["Authorization"].split()[1])
            timeline = await execute_mcp_tool(
                engine,
                "get_timeline",
                {"notebook_id": str(notebook_id)},
                server_config=config,
                principal=alice_principal,
            )
            assert isinstance(timeline[0], mcp_types.TextContent)
            assert json.loads(timeline[0].text)["notebook_id"] == str(notebook_id)
            with pytest.raises(NotFoundError):
                await execute_mcp_tool(
                    engine,
                    "get_timeline",
                    {"notebook_id": str(notebook_id)},
                    server_config=config,
                    principal=bob_principal,
                )
            first_source = (await store.list_sources_for_document(first_document_id))[0]
            insights = await execute_mcp_tool(
                engine,
                "get_source_insights",
                {"source_id": str(first_source.source_id)},
                server_config=config,
                principal=alice_principal,
            )
            assert isinstance(insights[0], mcp_types.TextContent)
            assert json.loads(insights[0].text)["source_id"] == str(first_source.source_id)
            with pytest.raises(NotFoundError):
                await execute_mcp_tool(
                    engine,
                    "get_source_insights",
                    {"source_id": str(first_source.source_id)},
                    server_config=config,
                    principal=bob_principal,
                )
            exact_args = {
                "notebook_id": str(notebook_id),
                "document_id": str(first_document_id),
                "version_id": str(stored.current_version_id),
            }
            mcp_chunk = await execute_mcp_tool(
                engine,
                "get_document_chunk",
                {**exact_args, "chunk_id": f"{1:064x}"},
                server_config=config,
                principal=alice_principal,
            )
            assert isinstance(mcp_chunk[0], mcp_types.TextContent)
            assert (
                json.loads(mcp_chunk[0].text)["items"][0]["payload"]["text"] == "target evidence 0"
            )
            with pytest.raises(NotFoundError):
                await execute_mcp_tool(
                    engine,
                    "get_document_chunk",
                    {**exact_args, "chunk_id": f"{1:064x}"},
                    server_config=config,
                    principal=bob_principal,
                )
            mcp_asset = await execute_mcp_tool(
                engine,
                "get_asset",
                {"notebook_id": str(notebook_id), "occurrence_id": str(occurrence_id)},
                server_config=config,
                principal=alice_principal,
            )
            assert mcp_asset
            with pytest.raises(NotFoundError):
                await execute_mcp_tool(
                    engine,
                    "get_asset",
                    {"notebook_id": str(notebook_id), "occurrence_id": str(occurrence_id)},
                    server_config=config,
                    principal=bob_principal,
                )
            mcp_delivery = await execute_mcp_tool(
                engine,
                "get_document",
                {**exact_args, "max_items": 1},
                server_config=config,
                principal=alice_principal,
            )
            assert isinstance(mcp_delivery[0], mcp_types.TextContent)
            mcp_delivery_cursor = json.loads(mcp_delivery[0].text)["next_cursor"]
            assert isinstance(mcp_delivery_cursor, str)
            assert (await client.get(chunk_url, headers=_headers("bob"))).status_code == 404
            assert (await client.get(chunk_url, headers={})).status_code == 401
            other_source = (await store.list_sources_for_document(other_document_id))[0]
            foreign_filter = _request(notebook_id)
            foreign_filter["scope"] = {
                "notebook_id": str(notebook_id),
                "source_ids": [str(other_source.source_id)],
            }
            assert (
                await client.post(
                    "/v2/retrieval/evidence",
                    headers=_headers("alice"),
                    json=foreign_filter,
                )
            ).status_code == 404
            document_url = chunk_url.rsplit("/chunks/", 1)[0]
            first_delivery = await client.get(
                document_url, headers=_headers("alice"), params={"max_items": 1}
            )
            assert first_delivery.status_code == 200, first_delivery.text
            delivery_cursor = first_delivery.json()["next_cursor"]
            assert isinstance(delivery_cursor, str)
            next_delivery = await client.get(
                document_url,
                headers=_headers("alice"),
                params={"max_items": 1, "cursor": delivery_cursor},
            )
            assert next_delivery.status_code == 200, next_delivery.text
            assert next_delivery.json()["next_cursor"] is None
            first = await client.post(
                "/v2/retrieval/evidence", headers=_headers("alice"), json=_request(notebook_id)
            )
            assert first.status_code == 200, first.text
            assert len(first.json()["items"]) == 1
            cursor = first.json()["next_cursor"]
            assert isinstance(cursor, str)
            automatic_request = {"query": "target", "mode": "exhaustive", "evidence_budget": 1}
            automatic = await client.post(
                "/v2/retrieval/automatic", headers=_headers("alice"), json=automatic_request
            )
            assert automatic.status_code == 200, automatic.text
            assert automatic.json()["evidence"]["items"][0]["notebook_id"] == str(notebook_id)
            automatic_cursor = automatic.json()["evidence"]["next_cursor"]
            assert isinstance(automatic_cursor, str)
            automatic_mcp = await execute_mcp_tool(
                engine,
                "query_notebook_v2",
                automatic_request,
                server_config=config,
                principal=alice_principal,
            )
            assert isinstance(automatic_mcp[0], mcp_types.TextContent)
            assert json.loads(automatic_mcp[0].text)["evidence"]["items"][0]["notebook_id"] == str(
                notebook_id
            )
            assert (
                await client.post(
                    "/v2/retrieval/automatic", headers=_headers("bob"), json=automatic_request
                )
            ).json()["notebook_id"] == str(other_id)
            mcp_first = await execute_mcp_tool(
                engine,
                "search_evidence",
                _request(notebook_id),
                server_config=config,
                principal=mapper.from_token(_headers("alice")["Authorization"].split()[1]),
            )
            assert isinstance(mcp_first[0], mcp_types.TextContent)
            mcp_payload = json.loads(mcp_first[0].text)
            assert mcp_payload["items"][0]["notebook_id"] == str(notebook_id)
            with pytest.raises(NotFoundError):
                await execute_mcp_tool(
                    engine,
                    "search_evidence",
                    _request(notebook_id),
                    server_config=config,
                    principal=mapper.from_token(_headers("bob")["Authorization"].split()[1]),
                )
            second = await client.post(
                "/v2/retrieval/evidence",
                headers=_headers("alice"),
                json=_request(notebook_id, cursor=cursor),
            )
            assert second.status_code == 200, second.text
            assert (
                second.json()["items"][0]["document_id"] != first.json()["items"][0]["document_id"]
            )
            assert second.json()["next_cursor"] is None
            denied = await client.post(
                "/v2/retrieval/evidence", headers=_headers("bob"), json=_request(notebook_id)
            )
            missing = await client.post(
                "/v2/retrieval/evidence", headers=_headers("bob"), json=_request(uuid4())
            )
            legacy = await client.post(
                "/v2/retrieval/evidence", headers=_headers("alice"), json=_request(legacy_id)
            )
            assert denied.status_code == missing.status_code == legacy.status_code == 404
            assert denied.json()["error"]["code"] == missing.json()["error"]["code"]
            authority.grant(
                actor_id=outsider, notebook_id=notebook_id, role="reader", operator_id=owner
            )
            stale = await client.post(
                "/v2/retrieval/evidence",
                headers=_headers("alice"),
                json=_request(notebook_id, cursor=cursor),
            )
            assert stale.status_code == 409
            stale_automatic = await client.post(
                "/v2/retrieval/automatic",
                headers=_headers("alice"),
                json={**automatic_request, "cursor": automatic_cursor},
            )
            assert stale_automatic.status_code == 409
            with pytest.raises(CursorConflictError):
                await execute_mcp_tool(
                    engine,
                    "search_evidence",
                    _request(notebook_id, cursor=mcp_payload["next_cursor"]),
                    server_config=config,
                    principal=mapper.from_token(_headers("alice")["Authorization"].split()[1]),
                )
            stale_delivery = await client.get(
                document_url,
                headers=_headers("alice"),
                params={"max_items": 1, "cursor": delivery_cursor},
            )
            assert stale_delivery.status_code == 409
            stale_asset = await client.get(
                asset_url,
                headers=_headers("alice"),
                params={"max_bytes": 8, "cursor": asset_cursor},
            )
            assert stale_asset.status_code == 409
            with pytest.raises(DeliveryCursorConflictError):
                await execute_mcp_tool(
                    engine,
                    "get_asset",
                    {
                        "notebook_id": str(notebook_id),
                        "occurrence_id": str(occurrence_id),
                        "max_bytes": 8,
                        "cursor": asset_cursor,
                    },
                    server_config=config,
                    principal=alice_principal,
                )
            with pytest.raises(DeliveryCursorConflictError):
                await execute_mcp_tool(
                    engine,
                    "get_document",
                    {**exact_args, "max_items": 1, "cursor": mcp_delivery_cursor},
                    server_config=config,
                    principal=alice_principal,
                )
            replay = await client.post(
                "/v2/retrieval/evidence",
                headers=_headers("bob"),
                json=_request(notebook_id, cursor=cursor),
            )
            assert replay.status_code == 409
            same_revision = await client.post(
                "/v2/retrieval/evidence", headers=_headers("alice"), json=_request(notebook_id)
            )
            assert same_revision.status_code == 200
            wrong_principal = await client.post(
                "/v2/retrieval/evidence",
                headers=_headers("bob"),
                json=_request(notebook_id, cursor=same_revision.json()["next_cursor"]),
            )
            assert wrong_principal.status_code == 409
            authority.revoke(actor_id=outsider, notebook_id=notebook_id)
            revoked = await client.post(
                "/v2/retrieval/evidence", headers=_headers("bob"), json=_request(notebook_id)
            )
            assert revoked.status_code == 404
            fresh = await client.post(
                "/v2/retrieval/evidence", headers=_headers("alice"), json=_request(notebook_id)
            )
            assert fresh.status_code == 200
            cross_principal = await client.post(
                "/v2/retrieval/evidence",
                headers=_headers("bob"),
                json=_request(notebook_id, cursor=fresh.json()["next_cursor"]),
            )
            assert cross_principal.status_code == 404
            tampered = await client.post(
                "/v2/retrieval/evidence",
                headers=_headers("alice"),
                json=_request(notebook_id, cursor=fresh.json()["next_cursor"] + "x"),
            )
            assert tampered.status_code in {409, 422}

            original_revision = authority.revision

            def missing_revision(notebook: UUID) -> None:
                del notebook
                return None

            monkeypatch.setattr(authority, "revision", missing_revision)
            unavailable = await client.post(
                "/v2/retrieval/evidence", headers=_headers("alice"), json=_request(notebook_id)
            )
            assert unavailable.status_code == 404
            monkeypatch.setattr(authority, "revision", original_revision)

            original_enumerate = store.enumerate_advanced_canonical

            async def revoke_during_retrieval(*args: Any, **kwargs: Any) -> Any:
                authority.revoke(actor_id=owner, notebook_id=notebook_id)
                return await original_enumerate(*args, **kwargs)

            monkeypatch.setattr(store, "enumerate_advanced_canonical", revoke_during_retrieval)
            interrupted = await client.post(
                "/v2/retrieval/evidence", headers=_headers("alice"), json=_request(notebook_id)
            )
            assert interrupted.status_code == 404
    finally:
        await store.close()


@pytest.mark.anyio
async def test_acl_image_analysis_http_and_mcp_revalidate_real_ancestry(
    tmp_path: Path,
) -> None:
    """Persisted OCR delivery is notebook-bound across both serving adapters."""
    from test_mcp_immutable_schema_matrix import _fixture
    from test_mcp_immutable_schema_matrix import create_app as create_indexed_app

    engine, store, fixture_config, identities = await _fixture(
        tmp_path, legacy=False, analysis=True
    )
    notebook_id = identities[0][0]
    other_notebook = identities[1][0]
    occurrence_id = store.analysis_ids["occurrence"]
    derivation_id = store.analysis_ids["ocr_0"]
    assert (
        await store.get_authorized_ocr_result(notebook_id=notebook_id, derivation_id=derivation_id)
        is not None
    )
    authority = SQLiteNotebookScopeAuthority((tmp_path / "analysis-acl.db").resolve())
    authority.initialize()
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", _SECRET)
    owner = mapper.from_token(_headers("alice")["Authorization"].split()[1])
    reader = mapper.from_token(_headers("bob")["Authorization"].split()[1])
    outsider = mapper.from_token(_headers("charlie")["Authorization"].split()[1])
    authority.grant(
        actor_id=owner.actor_id, notebook_id=notebook_id, role="owner", operator_id=owner.actor_id
    )
    authority.grant(
        actor_id=reader.actor_id,
        notebook_id=notebook_id,
        role="reader",
        operator_id=owner.actor_id,
    )
    authority.grant(
        actor_id=outsider.actor_id,
        notebook_id=other_notebook,
        role="owner",
        operator_id=outsider.actor_id,
    )
    fixture_engine = cast(_IndexedFixtureEngine, engine)
    fixture_engine.server_scope_authority = authority
    fixture_engine.server_actor_mapper = mapper
    config = ServerConfig.model_validate(
        {
            **fixture_config.model_dump(),
            "auth_mode": "jwt",
            "jwt_secret": _SECRET,
            "api_key": None,
        }
    )
    app = create_indexed_app(
        engine=engine, server_config=config, provision_tokenizer_on_startup=False
    )
    app.state.engine = engine
    app.state.server_config = config
    url = f"/v2/notebooks/{notebook_id}/asset-occurrences/{occurrence_id}/analysis"
    params = {"ocr_derivation_id": str(derivation_id)}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for subject in ("alice", "bob"):
                response = await client.get(url, headers=_headers(subject), params=params)
                assert response.status_code == 200, response.text
                assert response.json()["items"][0]["attribution"]["notebook_id"] == str(notebook_id)
            denied = await client.get(url, headers=_headers("charlie"), params=params)
            missing = await client.get(
                f"/v2/notebooks/{uuid4()}/asset-occurrences/{occurrence_id}/analysis",
                headers=_headers("charlie"),
                params=params,
            )
            assert denied.status_code == missing.status_code == 404
            assert denied.json()["error"]["code"] == missing.json()["error"]["code"]
            assert (await client.get(url, params=params)).status_code == 401
            mcp_args = {
                "notebook_id": str(notebook_id),
                "occurrence_id": str(occurrence_id),
                "ocr_derivation_id": str(derivation_id),
            }
            admission = fixture_engine._disposable_index_readiness_check
            delivered = await execute_mcp_tool(
                engine,
                "get_image_analysis",
                mcp_args,
                server_config=config,
                principal=owner,
                indexed_fixture_readiness_check=admission,
            )
            assert isinstance(delivered[0], mcp_types.TextContent)
            assert "derived_ocr" in delivered[0].text
            with pytest.raises(NotFoundError):
                await execute_mcp_tool(
                    engine,
                    "get_image_analysis",
                    mcp_args,
                    server_config=config,
                    principal=outsider,
                    indexed_fixture_readiness_check=admission,
                )
            authority.revoke(actor_id=reader.actor_id, notebook_id=notebook_id)
            assert (
                await client.get(url, headers=_headers("bob"), params=params)
            ).status_code == 404
            with pytest.raises(NotFoundError):
                await execute_mcp_tool(
                    engine,
                    "get_image_analysis",
                    mcp_args,
                    server_config=config,
                    principal=reader,
                    indexed_fixture_readiness_check=admission,
                )
    finally:
        await store.close()
