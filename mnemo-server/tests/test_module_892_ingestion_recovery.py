"""Disposable multi-store source publication under an explicit ACL intent."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import fitz  # type: ignore[import-untyped]
import pytest
from httpx import ASGITransport, AsyncClient
from mnemo.interfaces import (
    DependencyUnavailableError,
    EmbeddingBatch,
    IntegrityError,
    NotFoundError,
    PrincipalContextV1,
    StorageError,
)
from mnemo.models import FrozenMetadata, Notebook, Source
from mnemo.storage.composite import CompositeStorage
from mnemo.storage.filesystem import FilesystemBlobStore
from mnemo.storage.qdrant import QdrantStore
from mnemo.storage.sqlite import SQLiteStore
from mnemo.storage.surrealdb import SurrealDBStore
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig
from mnemo_server.services.authorized_scope import AuthorizedNotebookScopeResolver
from mnemo_server.services.ingestion import IngestionService
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority
from mnemo_server.services.trusted_actor import TrustedJWTActorMapper
from test_module_892_v1_acl_routes import _SECRET, _headers
from test_server_sources import MockTokenCounter, _make_mock_engine, _make_test_document

from scripts import run_phase86_four_notebooks as phase86_runner


async def _fixture(
    tmp_path: Path,
) -> tuple[
    CompositeStorage,
    AsyncMock,
    SQLiteNotebookScopeAuthority,
    MagicMock,
    UUID,
    PrincipalContextV1,
    PrincipalContextV1,
]:
    sql = SQLiteStore(tmp_path / "canonical.db")
    filesystem = FilesystemBlobStore(tmp_path / "blobs")
    vectors = AsyncMock(spec=QdrantStore)
    vectors._snapshot_chunks_with_projection.return_value = ()
    graph = AsyncMock(spec=SurrealDBStore)
    storage = CompositeStorage(
        filesystem=filesystem,
        sqlite=sql,
        qdrant=cast(QdrantStore, vectors),
        surrealdb=cast(SurrealDBStore, graph),
    )
    await storage.open()
    notebook_id = uuid4()
    now = datetime.now(UTC)
    await storage.upsert_notebook(
        Notebook(notebook_id=notebook_id, title="disposable", created_at=now, updated_at=now)
    )
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", _SECRET)
    owner = mapper.from_token(_headers("alice")["Authorization"].split()[1])
    reader = mapper.from_token(_headers("bob")["Authorization"].split()[1])
    authority.grant(
        actor_id=owner.actor_id, notebook_id=notebook_id, role="owner", operator_id=owner.actor_id
    )
    authority.grant(
        actor_id=reader.actor_id,
        notebook_id=notebook_id,
        role="reader",
        operator_id=owner.actor_id,
    )
    engine = _make_mock_engine()
    engine.storage = storage
    engine.asset_catalog = storage
    engine.asset_records = storage
    engine.server_scope_authority = authority
    engine.server_actor_mapper = mapper
    engine.embedding_provider.embed_batch.side_effect = lambda texts: EmbeddingBatch(
        vectors=tuple((0.1, 0.2, 0.3, 0.4) for _ in texts),
        model_name="fixture-embedding",
        dimensions=4,
    )
    return storage, vectors, authority, engine, notebook_id, owner, reader


async def _phase86_recovery_fixture(
    tmp_path: Path,
    *,
    failed_hash: str | None = None,
    creation_token: UUID | None = None,
    creation_actor: UUID | None = None,
) -> tuple[
    CompositeStorage,
    SQLiteNotebookScopeAuthority,
    IngestionService,
    dict[str, object],
    dict[str, dict[str, object]],
    UUID,
    UUID,
]:
    storage, _, authority, engine, original_id, owner, _ = await _fixture(tmp_path)
    plan, records = phase86_runner.preflight()
    plan["disposable_actor_id"] = str(owner.actor_id)
    plan["existing_notebook"]["id"] = str(original_id)
    plan["created_at"] = datetime.now(UTC).isoformat()
    notebook_ids = phase86_runner.notebook_ids(plan)
    for language, notebook_id in notebook_ids.items():
        notebook = phase86_runner.planned_notebook(plan, language, notebook_id)
        creator = (
            creation_actor if language == "mr" and creation_actor is not None else owner.actor_id
        )
        token = (
            creation_token
            if language == "mr" and creation_token is not None
            else uuid5(NAMESPACE_URL, f"{plan['run_key']}:{language}:creation")
        )
        authority.reserve_create(
            notebook_id=notebook_id, actor_id=creator, token=token, notebook=notebook
        )
        await storage.upsert_notebook(notebook)
        authority.finish_create(notebook_id=notebook_id, actor_id=creator, token=token)
        if creator != owner.actor_id:
            authority.grant(
                actor_id=owner.actor_id,
                notebook_id=notebook_id,
                role="owner",
                operator_id=creator,
            )
    content_hash = failed_hash or records["mahades_economic_survey_ch1_marathi.pdf"]["sha256"]
    document = _make_test_document(content_hash=content_hash)
    await storage.upsert_document(document)
    await storage.upsert_source(
        Source(
            source_id=uuid4(),
            notebook_id=original_id,
            document_id=document.document_id,
            created_at=datetime.now(UTC),
        )
    )
    marathi_id = notebook_ids["mr"]
    with authority.source_ingestion_process_lock() as process_lease:
        token = uuid4()
        authority.reserve_source_ingestion(
            actor_id=owner.actor_id,
            notebook_id=marathi_id,
            content_hash=content_hash,
            token=token,
            document_preexisted=True,
            process_lease=process_lease,
        )
        authority.mark_source_ingestion_failed(
            notebook_id=marathi_id, content_hash=content_hash, token=token
        )
    return (
        storage,
        authority,
        IngestionService(engine, MockTokenCounter(), principal=owner),
        plan,
        records,
        marathi_id,
        owner.actor_id,
    )


@pytest.mark.anyio
async def test_phase86_marathi_failed_intent_recovers_before_notebook_resume(
    tmp_path: Path,
) -> None:
    storage, authority, service, plan, records, marathi_id, actor = await _phase86_recovery_fixture(
        tmp_path
    )
    original_id = UUID(plan["existing_notebook"]["id"])
    try:
        assert authority.active_role(actor, marathi_id) is None
        assert not authority.permits(actor, marathi_id, operation="write")
        assert authority.pending_create(marathi_id) is None
        assert authority.completed_create(marathi_id) is not None
        before = await storage.list_sources_for_document(
            (
                await storage.get_document_by_content_hash(
                    records["mahades_economic_survey_ch1_marathi.pdf"]["sha256"]
                )
            ).document_id
        )
        assert len(before) == 1 and before[0].notebook_id == original_id
        log = phase86_runner.Log(tmp_path / "events.jsonl", "fixture")
        await phase86_runner.reconcile_known_failed_sources(
            plan, records, storage, authority, service, tmp_path, log
        )
        assert authority.active_role(actor, marathi_id) == "owner"
        assert authority.permits(actor, marathi_id, operation="write")
        assert (
            authority.source_ingestion_state(
                marathi_id, records["mahades_economic_survey_ch1_marathi.pdf"]["sha256"]
            )
            == "recoverable"
        )
        assert len(json.loads((tmp_path / "source_recovery_receipts.json").read_text())) == 1
        await phase86_runner.create_notebooks(plan, tmp_path / "canonical.db", authority, log)
        assert len((await storage.list_notebooks(limit=20, cursor=None)).items) == 4
        assert await storage.list_sources_for_document(before[0].document_id) == before
        await phase86_runner.reconcile_known_failed_sources(
            plan, records, storage, authority, service, tmp_path, log
        )
        assert len(json.loads((tmp_path / "source_recovery_receipts.json").read_text())) == 1
        assert authority.active_role(actor, phase86_runner.notebook_ids(plan)["hi"]) == "owner"
        assert authority.active_role(actor, phase86_runner.notebook_ids(plan)["en"]) == "owner"
    finally:
        await storage.close()


@pytest.mark.anyio
@pytest.mark.parametrize("mismatch", ["token", "actor", "notebook", "hash"])
async def test_phase86_recovery_rejects_mismatched_frozen_identity(
    tmp_path: Path, mismatch: str
) -> None:
    kwargs: dict[str, object] = {}
    if mismatch == "token":
        kwargs["creation_token"] = uuid4()
    elif mismatch == "actor":
        kwargs["creation_actor"] = uuid4()
    elif mismatch == "hash":
        kwargs["failed_hash"] = hashlib.sha256(b"wrong source").hexdigest()
    storage, authority, service, plan, records, marathi_id, actor = await _phase86_recovery_fixture(
        tmp_path, **kwargs
    )
    if mismatch == "notebook":
        plan["run_key"] = "wrong-run-key"
    content_hash = (
        kwargs.get("failed_hash") or records["mahades_economic_survey_ch1_marathi.pdf"]["sha256"]
    )
    try:
        with pytest.raises(RuntimeError, match=r"unrecognized|outside|ownership evidence"):
            await phase86_runner.reconcile_known_failed_sources(
                plan,
                records,
                storage,
                authority,
                service,
                tmp_path,
                phase86_runner.Log(tmp_path / "events.jsonl", "fixture"),
            )
        assert authority.source_ingestion_state(marathi_id, content_hash) == "failed"
        assert authority.active_role(actor, marathi_id) is None
        assert not (tmp_path / "source_recovery_receipts.json").exists()
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_phase86_recovery_rejects_revoked_owner(tmp_path: Path) -> None:
    storage, authority, service, plan, records, marathi_id, actor = await _phase86_recovery_fixture(
        tmp_path
    )
    content_hash = records["mahades_economic_survey_ch1_marathi.pdf"]["sha256"]
    try:
        authority.revoke(actor_id=actor, notebook_id=marathi_id)
        with pytest.raises((RuntimeError, ValueError, DependencyUnavailableError, NotFoundError)):
            await phase86_runner.reconcile_known_failed_sources(
                plan,
                records,
                storage,
                authority,
                service,
                tmp_path,
                phase86_runner.Log(tmp_path / "events.jsonl", "fixture"),
            )
        assert authority.source_ingestion_state(marathi_id, content_hash) == "failed"
        assert authority.active_role(actor, marathi_id) is None
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_phase86_recovery_rejects_unknown_intent_before_known_one(tmp_path: Path) -> None:
    storage, authority, service, plan, records, marathi_id, actor = await _phase86_recovery_fixture(
        tmp_path
    )
    content_hash = records["mahades_economic_survey_ch1_marathi.pdf"]["sha256"]
    unknown_hash = hashlib.sha256(b"unlisted source").hexdigest()
    english_id = phase86_runner.notebook_ids(plan)["en"]
    try:
        with authority.source_ingestion_process_lock() as lease:
            token = uuid4()
            authority.reserve_source_ingestion(
                actor_id=actor,
                notebook_id=english_id,
                content_hash=unknown_hash,
                token=token,
                document_preexisted=True,
                process_lease=lease,
            )
            authority.mark_source_ingestion_failed(
                notebook_id=english_id, content_hash=unknown_hash, token=token
            )
        with pytest.raises(RuntimeError, match="outside the frozen partition"):
            await phase86_runner.reconcile_known_failed_sources(
                plan,
                records,
                storage,
                authority,
                service,
                tmp_path,
                phase86_runner.Log(tmp_path / "events.jsonl", "fixture"),
            )
        assert authority.source_ingestion_state(marathi_id, content_hash) == "failed"
    finally:
        await storage.close()


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["lease", "reconciliation"])
async def test_phase86_recovery_service_failure_stays_quarantined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    storage, authority, service, plan, records, marathi_id, actor = await _phase86_recovery_fixture(
        tmp_path
    )
    content_hash = records["mahades_economic_survey_ch1_marathi.pdf"]["sha256"]
    if failure == "lease":

        def fail_lease(*args: object, **kwargs: object) -> object:
            raise RuntimeError("recovery lease unavailable")

        monkeypatch.setattr(authority, "source_ingestion_recovery_lease", fail_lease)
    else:

        async def fail_reconcile(*args: object, **kwargs: object) -> object:
            raise StorageError("storage reconciliation unavailable")

        monkeypatch.setattr(storage, "reconcile_document_membership", fail_reconcile)
    try:
        with pytest.raises((RuntimeError, StorageError), match="unavailable"):
            await phase86_runner.reconcile_known_failed_sources(
                plan,
                records,
                storage,
                authority,
                service,
                tmp_path,
                phase86_runner.Log(tmp_path / "events.jsonl", "fixture"),
            )
        assert authority.source_ingestion_state(marathi_id, content_hash) == "failed"
        assert authority.active_role(actor, marathi_id) is None
        assert not (tmp_path / "source_recovery_receipts.json").exists()
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_hard_crash_releases_process_lock_and_reconciles_incomplete_intent(
    tmp_path: Path,
) -> None:
    storage, _, authority, engine, notebook_id, owner, _ = await _fixture(tmp_path)
    content_hash = hashlib.sha256(b"crash before artifact write").hexdigest()
    script = (
        "import os, sys; from uuid import UUID; "
        "from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority; "
        "from pathlib import Path; "
        "a=SQLiteNotebookScopeAuthority(Path(sys.argv[1])); "
        "lock=a.source_ingestion_process_lock(); lease=lock.__enter__(); "
        "a.reserve_source_ingestion(actor_id=UUID(sys.argv[2]), "
        "notebook_id=UUID(sys.argv[3]), content_hash=sys.argv[4], "
        "token=UUID(sys.argv[5]), process_lease=lease); os._exit(17)"
    )
    try:
        child = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                script,
                str(authority.path),
                str(owner.actor_id),
                str(notebook_id),
                content_hash,
                str(uuid4()),
            ],
            check=False,
            capture_output=True,
            timeout=10,
        )
        assert child.returncode == 17, child.stderr.decode(errors="replace")
        restarted = SQLiteNotebookScopeAuthority(authority.path)
        assert restarted.source_ingestion_state(notebook_id, content_hash) == "incomplete"
        assert not restarted.permits(owner.actor_id, notebook_id)
        await IngestionService(
            engine, MockTokenCounter(), principal=owner
        ).reconcile_failed_source_ingestion(notebook_id=notebook_id, content_hash=content_hash)
        assert restarted.source_ingestion_state(notebook_id, content_hash) == "recoverable"
        assert restarted.permits(owner.actor_id, notebook_id)
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_indexed_asset_occurrences_survive_cross_notebook_retry_after_partial_source_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage, _, authority, engine, first_notebook, owner, _ = await _fixture(tmp_path)
    second_notebook = uuid4()
    now = datetime.now(UTC)
    await storage.upsert_notebook(
        Notebook(notebook_id=second_notebook, title="second", created_at=now, updated_at=now)
    )
    authority.grant(
        actor_id=owner.actor_id,
        notebook_id=second_notebook,
        role="owner",
        operator_id=owner.actor_id,
    )
    pdf = fitz.open()
    image = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    for page_number in range(2):
        page = pdf.new_page()
        page.insert_text((50, 50), f"Retained asset page {page_number} with content.")
        page.insert_image(fitz.Rect(50, 70, 150, 170), stream=image)
    data = pdf.write()
    pdf.close()
    content_hash = hashlib.sha256(data).hexdigest()
    service = IngestionService(engine, MockTokenCounter(), principal=owner)
    try:
        first = await service.ingest_source(
            notebook_id=first_notebook, filename="asset.pdf", data=data
        )
        document = await storage.get_document(first.document_id)
        assert document is not None
        original_occurrences = await storage.list_asset_occurrences(document.current_version_id)
        assert original_occurrences
        original_upsert = storage.upsert_source

        async def interrupted_upsert(source: object) -> None:
            await original_upsert(source)
            raise StorageError("simulated crash after canonical source write")

        with monkeypatch.context() as patch:
            patch.setattr(storage, "upsert_source", interrupted_upsert)
            with pytest.raises(StorageError, match="after canonical source write"):
                await service.ingest_source(
                    notebook_id=second_notebook, filename="asset.pdf", data=data
                )
        assert authority.source_ingestion_state(second_notebook, content_hash) == "failed"
        assert any(
            source.notebook_id == second_notebook
            for source in await storage.list_sources_for_document(document.document_id)
        )
        await service.reconcile_failed_source_ingestion(
            notebook_id=second_notebook, content_hash=content_hash
        )
        assert authority.source_ingestion_state(second_notebook, content_hash) == "recoverable"
        retried = await service.ingest_source(
            notebook_id=second_notebook, filename="asset.pdf", data=data
        )
        assert retried.deduplicated is True
        assert authority.source_ingestion_state(second_notebook, content_hash) == "published"
        sources = await storage.list_sources_for_document(document.document_id)
        assert {source.notebook_id for source in sources} == {first_notebook, second_notebook}
        assert len(sources) == 2
        assert await storage.list_asset_occurrences(document.current_version_id) == (
            original_occurrences
        )
    finally:
        await storage.close()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("crash_after", "embedded_asset"),
    [
        ("put_parsed_document", False),
        ("upsert_document", False),
        ("put_asset", False),
        ("upsert_chunks", False),
        ("upsert_source", False),
        ("put_asset", True),
        ("asset_raw", True),
        ("upsert_chunks", True),
        ("parsed_temp", False),
    ],
)
async def test_real_ingestion_hard_crash_at_cross_store_boundary_recovers_and_retries(
    tmp_path: Path, crash_after: str, embedded_asset: bool
) -> None:
    storage, _, authority, engine, notebook_id, owner, _ = await _fixture(tmp_path)
    data = (
        b"Before ![pixel](data:image/png;base64,aQ==) after.\n"
        if embedded_asset
        else b"Crash at a material multi-store write boundary, then retry. " * 80
    )
    filename = "crash.md" if embedded_asset else "crash.txt"
    content_hash = hashlib.sha256(data).hexdigest()
    script = """
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID
from mnemo.interfaces import EmbeddingBatch, PrincipalContextV1
from mnemo.storage.composite import CompositeStorage
from mnemo.storage.filesystem import FilesystemBlobStore
import mnemo.storage.filesystem as filesystem_module
from mnemo.storage.qdrant import QdrantStore
from mnemo.storage.sqlite import SQLiteStore
from mnemo.storage.surrealdb import SurrealDBStore
from mnemo_server.services.ingestion import IngestionService
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority
sys.path.insert(0, str(Path.cwd() / 'mnemo-server/tests'))
from test_server_sources import MockTokenCounter, _make_mock_engine

async def run():
    root = Path(sys.argv[1])
    sql = SQLiteStore(root / 'canonical.db')
    vectors = AsyncMock(spec=QdrantStore)
    vectors._snapshot_chunks_with_projection.return_value = ()
    graph = AsyncMock(spec=SurrealDBStore)
    storage = CompositeStorage(
        filesystem=FilesystemBlobStore(root / 'blobs'), sqlite=sql,
        qdrant=vectors, surrealdb=graph,
    )
    await storage.open()
    engine = _make_mock_engine()
    engine.storage = storage
    engine.asset_catalog = storage
    engine.asset_records = storage
    engine.server_scope_authority = SQLiteNotebookScopeAuthority(root / 'acl.db')
    engine.embedding_provider.embed_batch.side_effect = lambda texts: EmbeddingBatch(
        vectors=tuple((0.1, 0.2, 0.3, 0.4) for _ in texts),
        model_name='fixture-embedding', dimensions=4,
    )
    point = sys.argv[4]
    if point in {'asset_raw', 'parsed_temp'}:
        original_atomic = filesystem_module._atomic_write
        def crash_at_target(path, data):
            if point == 'parsed_temp' and path.name.endswith('.ir.json'):
                path.parent.mkdir(parents=True, exist_ok=True)
                (path.parent / f'.tmp_{path.name}_interrupted').write_bytes(b'partial IR')
                os._exit(29)
            original_atomic(path, data)
            if point == 'asset_raw' and path.name.startswith('raw'):
                os._exit(29)
        filesystem_module._atomic_write = crash_at_target
    else:
        original = getattr(storage, point)
        async def crash_after_write(*args, **kwargs):
            result = await original(*args, **kwargs)
            os._exit(29)
            return result
        setattr(storage, point, crash_after_write)
    principal = PrincipalContextV1(actor_id=UUID(sys.argv[3]), authenticated=True)
    await IngestionService(engine, MockTokenCounter(), principal=principal).ingest_source(
        notebook_id=UUID(sys.argv[2]), filename=sys.argv[6],
        data=sys.argv[5].encode('utf-8'),
    )

asyncio.run(run())
"""
    try:
        child = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                script,
                str(tmp_path),
                str(notebook_id),
                str(owner.actor_id),
                crash_after,
                data.decode("utf-8"),
                filename,
            ],
            check=False,
            capture_output=True,
            timeout=20,
        )
        assert child.returncode == 29, child.stderr.decode(errors="replace")
        restarted = SQLiteNotebookScopeAuthority(authority.path)
        assert restarted.source_ingestion_state(notebook_id, content_hash) == "incomplete"
        assert not restarted.permits(owner.actor_id, notebook_id)
        if embedded_asset:
            inline_hash = hashlib.sha256(b"i").hexdigest()
            assert (inline_hash, "image/png", False) in restarted.source_ingestion_asset_candidates(
                actor_id=owner.actor_id,
                notebook_id=notebook_id,
                content_hash=content_hash,
            )
            asset_id = FilesystemBlobStore.asset_id_for_hash(inline_hash)
            if crash_after == "asset_raw":
                assert await storage.get_asset_record(asset_id) is None
            else:
                assert await storage.get_asset_record(asset_id) is not None
            blob_path = storage._fs._blob_path(inline_hash, "image/png")
            index_path = storage._fs._asset_index_path(asset_id)
            blob_temp = blob_path.parent / f".tmp_{blob_path.name}_interrupted"
            index_temp = index_path.parent / f".tmp_{index_path.name}_interrupted"
            unrelated_temp = blob_path.parent / ".tmp_unrelated"
            blob_temp.write_bytes(b"incomplete candidate bytes")
            index_temp.write_bytes(b"incomplete index bytes")
            unrelated_temp.write_bytes(b"not this candidate")
        if crash_after == "parsed_temp":
            version_id = uuid5(NAMESPACE_URL, f"mnemo-version:{content_hash}")
            ir_path = storage._fs._ir_path(version_id)
            ir_temp = ir_path.parent / f".tmp_{ir_path.name}_interrupted"
            assert ir_temp.exists()
        service = IngestionService(engine, MockTokenCounter(), principal=owner)
        await service.reconcile_failed_source_ingestion(
            notebook_id=notebook_id, content_hash=content_hash
        )
        assert restarted.source_ingestion_state(notebook_id, content_hash) == "recoverable"
        assert await storage.get_document_by_content_hash(content_hash) is None
        if crash_after == "parsed_temp":
            assert not ir_temp.exists()
        if embedded_asset:
            assert await storage.get_asset_record(asset_id) is None
            assert not blob_temp.exists()
            assert not index_temp.exists()
            assert unrelated_temp.read_bytes() == b"not this candidate"
            assert (
                restarted.source_ingestion_asset_candidates(
                    actor_id=owner.actor_id,
                    notebook_id=notebook_id,
                    content_hash=content_hash,
                )
                == ()
            )
        retried = await service.ingest_source(notebook_id=notebook_id, filename=filename, data=data)
        assert retried.status == "indexed"
        assert restarted.source_ingestion_state(notebook_id, content_hash) == "published"
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_recovery_preserves_preexisting_content_addressed_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage, _, authority, engine, notebook_id, owner, _ = await _fixture(tmp_path)
    data = b"Before ![pixel](data:image/png;base64,aQ==) after.\n"
    existing = await storage.put_asset(b"i", "image/png", FrozenMetadata())
    original_upsert = storage.upsert_source

    async def fail_source(_source: object) -> None:
        raise StorageError("injected source publication failure")

    monkeypatch.setattr(storage, "upsert_source", fail_source)
    try:
        service = IngestionService(engine, MockTokenCounter(), principal=owner)
        with pytest.raises(StorageError, match="injected source publication failure"):
            await service.ingest_source(notebook_id=notebook_id, filename="shared.md", data=data)
        content_hash = hashlib.sha256(data).hexdigest()
        assert authority.source_ingestion_state(notebook_id, content_hash) == "failed"
        assert (
            hashlib.sha256(b"i").hexdigest(),
            "image/png",
            True,
        ) in authority.source_ingestion_asset_candidates(
            actor_id=owner.actor_id, notebook_id=notebook_id, content_hash=content_hash
        )
        monkeypatch.setattr(storage, "upsert_source", original_upsert)
        await service.reconcile_failed_source_ingestion(
            notebook_id=notebook_id, content_hash=content_hash
        )
        assert await storage.get_asset(existing.asset_id) == b"i"
        retried = await service.ingest_source(
            notebook_id=notebook_id, filename="shared.md", data=data
        )
        assert retried.status == "indexed"
        assert await storage.get_asset(existing.asset_id) == b"i"
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_recovery_does_not_delete_preexisting_unassociated_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage, _, authority, engine, notebook_id, owner, _ = await _fixture(tmp_path)
    data = b"A previously indexed document must survive an interrupted new association. " * 20
    service = IngestionService(engine, MockTokenCounter(), principal=owner)
    try:
        first = await service.ingest_source(notebook_id=notebook_id, filename="old.txt", data=data)
        await service.delete_source(notebook_id=notebook_id, source_id=first.source_id)
        document = await storage.get_document_by_content_hash(first.content_hash)
        assert document is not None
        assert not await storage.list_sources_for_document(document.document_id)
        original_upsert = storage.upsert_source

        async def fail_source(_source: object) -> None:
            raise StorageError("injected reassociation failure")

        monkeypatch.setattr(storage, "upsert_source", fail_source)
        with pytest.raises(StorageError, match="injected reassociation failure"):
            await service.ingest_source(notebook_id=notebook_id, filename="again.txt", data=data)
        assert authority.source_ingestion_state(notebook_id, first.content_hash) == "failed"
        monkeypatch.setattr(storage, "upsert_source", original_upsert)
        await service.reconcile_failed_source_ingestion(
            notebook_id=notebook_id, content_hash=first.content_hash
        )
        assert await storage.get_document_by_content_hash(first.content_hash) == document
        retried = await service.ingest_source(
            notebook_id=notebook_id, filename="again.txt", data=data
        )
        assert retried.deduplicated is True
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_inconsistent_orphan_asset_is_quarantined_instead_of_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage, _, authority, engine, notebook_id, owner, _ = await _fixture(tmp_path)
    data = b"Before ![pixel](data:image/png;base64,aQ==) after.\n"
    original_upsert = storage.upsert_source

    async def fail_source(_source: object) -> None:
        raise StorageError("injected source publication failure")

    monkeypatch.setattr(storage, "upsert_source", fail_source)
    try:
        service = IngestionService(engine, MockTokenCounter(), principal=owner)
        with pytest.raises(StorageError):
            await service.ingest_source(notebook_id=notebook_id, filename="bad.md", data=data)
        monkeypatch.setattr(storage, "upsert_source", original_upsert)
        content_hash = hashlib.sha256(data).hexdigest()
        inline_hash = hashlib.sha256(b"i").hexdigest()
        asset_id = FilesystemBlobStore.asset_id_for_hash(inline_hash)
        index_path = storage._fs._asset_index_path(asset_id)
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["mime_type"] = "image/jpeg"
        index_path.write_text(json.dumps(index), encoding="utf-8")
        with pytest.raises(IntegrityError, match="inconsistent"):
            await service.reconcile_failed_source_ingestion(
                notebook_id=notebook_id, content_hash=content_hash
            )
        assert authority.source_ingestion_state(notebook_id, content_hash) == "failed"
        assert not authority.permits(owner.actor_id, notebook_id)
        assert index_path.exists()
    finally:
        await storage.close()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "corruption",
    ["index_json", "index_identity", "index_asset_id", "index_media_type", "blob_bytes"],
)
async def test_orphan_asset_recovery_rejects_ambiguous_artifacts_without_deleting_them(
    tmp_path: Path, corruption: str
) -> None:
    """Recovery must not guess which side of a corrupt index/blob is authoritative."""
    filesystem = FilesystemBlobStore(tmp_path / "blobs")
    await filesystem.open()
    try:
        data = b"disposable candidate"
        content_hash = hashlib.sha256(data).hexdigest()
        asset = await filesystem.put_asset(data, "image/png", FrozenMetadata())
        index_path = filesystem._asset_index_path(asset.asset_id)
        blob_path = filesystem._blob_path(content_hash, "image/png")
        if corruption == "index_json":
            index_path.write_text("{broken", encoding="utf-8")
            expected: type[Exception] = StorageError
        elif corruption == "index_identity":
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index["content_hash"] = hashlib.sha256(b"other").hexdigest()
            index_path.write_text(json.dumps(index), encoding="utf-8")
            expected = IntegrityError
        elif corruption == "index_asset_id":
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index["asset_id"] = str(uuid4())
            index_path.write_text(json.dumps(index), encoding="utf-8")
            expected = IntegrityError
        elif corruption == "index_media_type":
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index["mime_type"] = "image/jpeg"
            index_path.write_text(json.dumps(index), encoding="utf-8")
            expected = IntegrityError
        else:
            blob_path.write_bytes(b"corrupted candidate bytes")
            expected = IntegrityError
        with pytest.raises(expected):
            await filesystem.reconcile_orphan_asset_candidate(content_hash, ("image/png",))
        assert index_path.exists()
        assert blob_path.exists()
    finally:
        await filesystem.close()


@pytest.mark.anyio
async def test_recovery_rejects_invalid_candidate_identity_before_cleanup(tmp_path: Path) -> None:
    filesystem = FilesystemBlobStore(tmp_path / "blobs")
    await filesystem.open()
    try:
        data = b"candidate that must remain"
        content_hash = hashlib.sha256(data).hexdigest()
        asset = await filesystem.put_asset(data, "image/png", FrozenMetadata())
        index_path = filesystem._asset_index_path(asset.asset_id)
        blob_path = filesystem._blob_path(content_hash, "image/png")
        with pytest.raises(ValueError, match="media types"):
            await filesystem.reconcile_orphan_asset_candidate(content_hash, ())
        with pytest.raises(ValueError, match="SHA-256"):
            await filesystem.reconcile_orphan_asset_candidate("invalid", ("image/png",))
        with pytest.raises(ValueError, match="media types"):
            await filesystem.reconcile_orphan_asset_candidate(content_hash, ("",))
        assert index_path.exists() and blob_path.exists()
    finally:
        await filesystem.close()


@pytest.mark.anyio
async def test_source_recovery_rejects_invalid_identity_and_unavailable_authority(
    tmp_path: Path,
) -> None:
    storage, _, authority, engine, notebook_id, owner, _ = await _fixture(tmp_path)
    valid_hash = hashlib.sha256(b"not an ingestion").hexdigest()
    try:
        service = IngestionService(engine, MockTokenCounter(), principal=owner)
        with pytest.raises(ValueError, match="lowercase SHA-256"):
            await service.reconcile_failed_source_ingestion(
                notebook_id=notebook_id, content_hash="NOT-A-HASH"
            )
        engine.server_scope_authority = None
        with pytest.raises(DependencyUnavailableError, match="unavailable"):
            await service.reconcile_failed_source_ingestion(
                notebook_id=notebook_id, content_hash=valid_hash
            )
        engine.server_scope_authority = authority
        unauthenticated = IngestionService(engine, MockTokenCounter())
        with pytest.raises(DependencyUnavailableError, match="unavailable"):
            await unauthenticated.reconcile_failed_source_ingestion(
                notebook_id=notebook_id, content_hash=valid_hash
            )
        assert authority.source_ingestion_state(notebook_id, valid_hash) is None
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_orphan_recovery_is_exact_idempotent_and_cleans_only_its_own_temps(
    tmp_path: Path,
) -> None:
    filesystem = FilesystemBlobStore(tmp_path / "blobs")
    await filesystem.open()
    try:
        data = b"interrupted candidate"
        content_hash = hashlib.sha256(data).hexdigest()
        asset = await filesystem.put_asset(data, "image/png", FrozenMetadata())
        index_path = filesystem._asset_index_path(asset.asset_id)
        blob_path = filesystem._blob_path(content_hash, "image/png")
        own_index_temp = index_path.with_name(f".tmp_{index_path.name}_crash")
        own_blob_temp = blob_path.with_name(f".tmp_{blob_path.name}_crash")
        other_temp = index_path.with_name(".tmp_unrelated.json_crash")
        for path in (own_index_temp, own_blob_temp, other_temp):
            path.write_bytes(b"incomplete")
        assert await filesystem.reconcile_orphan_asset_candidate(content_hash, ("image/png",))
        assert not index_path.exists()
        assert not blob_path.exists()
        assert not own_index_temp.exists()
        assert not own_blob_temp.exists()
        assert other_temp.exists()
        assert not await filesystem.reconcile_orphan_asset_candidate(content_hash, ("image/png",))
    finally:
        await filesystem.close()


@pytest.mark.anyio
@pytest.mark.parametrize("remaining_side", ["raw", "index"])
async def test_orphan_recovery_handles_each_single_artifact_crash_state(
    tmp_path: Path, remaining_side: str
) -> None:
    filesystem = FilesystemBlobStore(tmp_path / "blobs")
    await filesystem.open()
    try:
        data = b"single-side crash artifact"
        content_hash = hashlib.sha256(data).hexdigest()
        asset = await filesystem.put_asset(data, "image/png", FrozenMetadata())
        index_path = filesystem._asset_index_path(asset.asset_id)
        blob_path = filesystem._blob_path(content_hash, "image/png")
        if remaining_side == "raw":
            index_path.unlink()
        else:
            blob_path.unlink()
        assert await filesystem.reconcile_orphan_asset_candidate(content_hash, ("image/png",))
        assert not index_path.exists()
        assert not blob_path.exists()
        assert not await filesystem.reconcile_orphan_asset_candidate(content_hash, ("image/png",))
    finally:
        await filesystem.close()


@pytest.mark.anyio
async def test_ordinary_ir_delete_does_not_remove_another_writer_temp(
    tmp_path: Path,
) -> None:
    filesystem = FilesystemBlobStore(tmp_path / "blobs")
    await filesystem.open()
    try:
        version_id = uuid4()
        ir_path = filesystem._ir_path(version_id)
        ir_path.parent.mkdir(parents=True)
        temp_path = ir_path.with_name(f".tmp_{ir_path.name}_writer")
        temp_path.write_bytes(b"in flight")
        assert not await filesystem.delete_parsed_document(version_id)
        assert temp_path.exists()
        await filesystem.reconcile_parsed_document_candidate(version_id)
        assert not temp_path.exists()
    finally:
        await filesystem.close()


@pytest.mark.anyio
async def test_live_source_writer_prevents_recovery_but_not_acl_revocation(tmp_path: Path) -> None:
    storage, _, authority, engine, notebook_id, owner, _ = await _fixture(tmp_path)
    content_hash = hashlib.sha256(b"live writer").hexdigest()
    try:
        with authority.source_ingestion_process_lock() as lease:
            authority.reserve_source_ingestion(
                actor_id=owner.actor_id,
                notebook_id=notebook_id,
                content_hash=content_hash,
                token=uuid4(),
                process_lease=lease,
            )
            with pytest.raises(DependencyUnavailableError):
                await IngestionService(
                    engine, MockTokenCounter(), principal=owner
                ).reconcile_failed_source_ingestion(
                    notebook_id=notebook_id, content_hash=content_hash
                )
            authority.revoke(actor_id=owner.actor_id, notebook_id=notebook_id)
            assert not authority.permits(owner.actor_id, notebook_id)
        assert authority.source_ingestion_state(notebook_id, content_hash) == "incomplete"
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_acl_source_ingestion_publishes_only_after_real_artifact_writes(
    tmp_path: Path,
) -> None:
    storage, vectors, authority, engine, notebook_id, owner, reader = await _fixture(tmp_path)
    data = b"A disposable private source with enough words for embedding and chunking. " * 80
    content_hash = hashlib.sha256(data).hexdigest()
    try:
        with pytest.raises(NotFoundError):
            await IngestionService(engine, MockTokenCounter(), principal=reader).ingest_source(
                notebook_id=notebook_id, filename="private.txt", data=data
            )
        result = await IngestionService(engine, MockTokenCounter(), principal=owner).ingest_source(
            notebook_id=notebook_id, filename="private.txt", data=data
        )
        assert result.status == "indexed"
        assert authority.source_ingestion_state(notebook_id, content_hash) == "published"
        assert authority.permits(reader.actor_id, notebook_id)
        assert await storage.get_source(result.source_id) is not None
        document = await storage.get_document(result.document_id)
        assert document is not None
        assert await storage.get_parsed_document(document.current_version_id) is not None
        assert vectors._upsert_chunks_with_projection.await_count == 1
        assert vectors._set_document_membership.await_count == 1
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_acl_source_ingestion_http_owner_success_reader_denial(
    tmp_path: Path,
) -> None:
    storage, vectors, authority, engine, notebook_id, owner, _ = await _fixture(tmp_path)
    config = ServerConfig(
        auth_mode="jwt",
        jwt_secret=_SECRET,
        delivery_cursor_secret="disposable-source-delivery-cursor-secret-32-bytes",
    )
    app = create_app(server_config=config, engine=engine, provision_tokenizer_on_startup=False)
    app.state.engine = engine
    app.state.server_config = config
    app.state.token_counter = MockTokenCounter()
    path = f"/v1/notebooks/{notebook_id}/sources"
    data = b"A governed source served only to its authorized notebook members. " * 80
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            missing_identity = await client.post(
                path, files={"file": ("missing.txt", data, "text/plain")}
            )
            assert missing_identity.status_code == 401
            denied = await client.post(
                path,
                headers=_headers("bob"),
                files={"file": ("guarded.txt", data, "text/plain")},
            )
            assert denied.status_code == 404
            stranger = await client.post(
                path,
                headers=_headers("charlie"),
                files={"file": ("unknown.txt", data, "text/plain")},
            )
            assert stranger.status_code == 404
            nonexistent = await client.post(
                f"/v1/notebooks/{uuid4()}/sources",
                headers=_headers("alice"),
                files={"file": ("unknown.txt", data, "text/plain")},
            )
            assert nonexistent.status_code == 404
            assert vectors._set_document_membership.await_count == 0
            created = await client.post(
                path,
                headers=_headers("alice"),
                files={"file": ("governed.txt", data, "text/plain")},
            )
            assert created.status_code == 201, created.text
            assert (
                authority.source_ingestion_state(notebook_id, hashlib.sha256(data).hexdigest())
                == "published"
            )
            assert vectors._set_document_membership.await_count == 1
            duplicate = await client.post(
                path,
                headers=_headers("alice"),
                files={"file": ("duplicate.txt", data, "text/plain")},
            )
            assert duplicate.status_code == 409
            second_data = b"A separate governed source for cursor invalidation. " * 80
            second = await client.post(
                path,
                headers=_headers("alice"),
                files={"file": ("second.txt", second_data, "text/plain")},
            )
            assert second.status_code == 201, second.text
            first_page = await client.get(path, params={"limit": 1}, headers=_headers("bob"))
            assert first_page.status_code == 200, first_page.text
            cursor = first_page.json()["next_cursor"]
            assert isinstance(cursor, str)
            source_id = created.json()["source_id"]
            denied_delete = await client.delete(f"{path}/{source_id}", headers=_headers("bob"))
            assert denied_delete.status_code == 404
            unknown_delete = await client.delete(f"{path}/{uuid4()}", headers=_headers("alice"))
            assert unknown_delete.status_code == 404
            removed = await client.delete(f"{path}/{source_id}", headers=_headers("alice"))
            assert removed.status_code == 204, removed.text
            assert await storage.get_source(UUID(source_id)) is None
            assert authority.permits(owner.actor_id, notebook_id)
            stale = await client.get(
                path, params={"limit": 1, "cursor": cursor}, headers=_headers("bob")
            )
            assert stale.status_code != 200
            remaining = await client.get(path, headers=_headers("bob"))
            assert remaining.status_code == 200
            assert {item["source_id"] for item in remaining.json()["items"]} == {
                second.json()["source_id"]
            }
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_composite_source_delete_failure_quarantines_until_owner_recovery(
    tmp_path: Path,
) -> None:
    storage, vectors, authority, engine, notebook_id, owner, reader = await _fixture(tmp_path)
    service = IngestionService(engine, MockTokenCounter(), principal=owner)
    try:
        created = await service.ingest_source(
            notebook_id=notebook_id,
            filename="delete.txt",
            data=b"A private source to delete safely. " * 80,
        )
        vectors._set_document_membership.side_effect = RuntimeError("projection unavailable")
        with pytest.raises(StorageError):
            await service.delete_source(notebook_id=notebook_id, source_id=created.source_id)
        restarted = SQLiteNotebookScopeAuthority(authority.path)
        assert not restarted.permits(owner.actor_id, notebook_id)
        assert not restarted.permits(reader.actor_id, notebook_id)
        assert restarted.revision(notebook_id) is None
        with pytest.raises(NotFoundError):
            await IngestionService(
                engine, MockTokenCounter(), principal=reader
            ).reconcile_failed_source_deletion(notebook_id=notebook_id, source_id=created.source_id)
        vectors._set_document_membership.side_effect = None
        await service.reconcile_failed_source_deletion(
            notebook_id=notebook_id, source_id=created.source_id
        )
        assert await storage.get_source(created.source_id) is None
        assert restarted.permits(reader.actor_id, notebook_id)
        assert restarted.revision(notebook_id) is not None
        revision = restarted.revision(notebook_id)
        projections = vectors._set_document_membership.await_count
        await service.reconcile_failed_source_deletion(
            notebook_id=notebook_id, source_id=created.source_id
        )
        assert restarted.revision(notebook_id) == revision
        assert vectors._set_document_membership.await_count == projections
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_source_delete_requires_persisted_absence_before_releasing_quarantine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage, _, authority, engine, notebook_id, owner, reader = await _fixture(tmp_path)
    service = IngestionService(engine, MockTokenCounter(), principal=owner)
    try:
        created = await service.ingest_source(
            notebook_id=notebook_id,
            filename="still-present.txt",
            data=b"A deletion must actually persist before the ACL reopens. " * 80,
        )
        original_delete = storage.delete_source

        async def no_op_delete(_source_id: UUID) -> bool:
            return True

        monkeypatch.setattr(storage, "delete_source", no_op_delete)
        with pytest.raises(DependencyUnavailableError, match="not persisted"):
            await service.delete_source(notebook_id=notebook_id, source_id=created.source_id)
        assert await storage.get_source(created.source_id) is not None
        assert not authority.permits(owner.actor_id, notebook_id)
        assert not authority.permits(reader.actor_id, notebook_id)
        monkeypatch.setattr(storage, "delete_source", original_delete)
        await service.reconcile_failed_source_deletion(
            notebook_id=notebook_id, source_id=created.source_id
        )
        assert await storage.get_source(created.source_id) is None
        assert authority.permits(reader.actor_id, notebook_id)
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_source_delete_quarantines_resource_identity_change_after_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage, _, authority, engine, notebook_id, owner, _ = await _fixture(tmp_path)
    service = IngestionService(engine, MockTokenCounter(), principal=owner)
    try:
        created = await service.ingest_source(
            notebook_id=notebook_id,
            filename="identity.txt",
            data=b"A resource identity change cannot pass a reserved deletion. " * 80,
        )
        original_get = storage.get_source
        lookups = 0

        async def changed_after_reservation(source_id: UUID) -> object:
            nonlocal lookups
            lookups += 1
            source = await original_get(source_id)
            if lookups == 2 and source is not None:
                return replace(source, notebook_id=uuid4())
            return source

        monkeypatch.setattr(storage, "get_source", changed_after_reservation)
        with pytest.raises(DependencyUnavailableError, match="inconsistent"):
            await service.delete_source(notebook_id=notebook_id, source_id=created.source_id)
        assert not authority.permits(owner.actor_id, notebook_id)
        monkeypatch.setattr(storage, "get_source", original_get)
        await service.reconcile_failed_source_deletion(
            notebook_id=notebook_id, source_id=created.source_id
        )
        assert await storage.get_source(created.source_id) is None
        assert authority.permits(owner.actor_id, notebook_id)
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_recovery_cannot_delete_a_published_document_or_referenced_asset(
    tmp_path: Path,
) -> None:
    storage, _, authority, engine, notebook_id, owner, reader = await _fixture(tmp_path)
    data = b"Before ![pixel](data:image/png;base64,aQ==) after.\n"
    try:
        created = await IngestionService(engine, MockTokenCounter(), principal=owner).ingest_source(
            notebook_id=notebook_id, filename="published.md", data=data
        )
        document = await storage.get_document(created.document_id)
        assert document is not None
        with pytest.raises(IntegrityError, match="cannot be reconciled safely"):
            await storage.reconcile_unpublished_document(
                document_id=document.document_id,
                version_id=document.current_version_id,
                content_hash=created.content_hash,
            )
        assert await storage.get_source(created.source_id) is not None
        # The retained original is catalogued by the real ingestion path.
        asset_id = FilesystemBlobStore.asset_id_for_hash(created.content_hash)
        original = await storage.get_asset_record(asset_id)
        assert original is not None
        assert await storage._sql.is_asset_referenced(asset_id)
        assert not await storage.reconcile_orphan_asset_candidate(
            created.content_hash, (original.mime_type,)
        )
        assert await storage.get_asset(asset_id) == data
        assert authority.permits(reader.actor_id, notebook_id)
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_recovery_cleans_unreferenced_catalog_and_blob_after_sql_cascade(
    tmp_path: Path,
) -> None:
    storage, _, _, engine, notebook_id, owner, _ = await _fixture(tmp_path)
    data = b"An original file whose catalogue survives a SQL cascade. " * 20
    try:
        created = await IngestionService(engine, MockTokenCounter(), principal=owner).ingest_source(
            notebook_id=notebook_id, filename="orphan.txt", data=data
        )
        asset_id = FilesystemBlobStore.asset_id_for_hash(created.content_hash)
        original = await storage.get_asset_record(asset_id)
        assert original is not None
        assert await storage._sql.is_asset_referenced(asset_id)
        await storage.delete_source(created.source_id)
        await storage._sql.delete_document_cascade(created.document_id)
        assert not await storage._sql.is_asset_referenced(asset_id)
        assert await storage.get_asset_record(asset_id) is not None
        assert await storage.reconcile_orphan_asset_candidate(
            created.content_hash, (original.mime_type,)
        )
        assert await storage.get_asset_record(asset_id) is None
        assert await storage.get_asset(asset_id) is None
        assert not await storage.reconcile_orphan_asset_candidate(
            created.content_hash, (original.mime_type,)
        )
    finally:
        await storage.close()


@pytest.mark.anyio
@pytest.mark.parametrize("fault", ["catalog_mismatch", "catalog_delete_refused"])
async def test_recovery_quarantines_catalog_disagreement_before_blob_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    storage, _, _, engine, notebook_id, owner, _ = await _fixture(tmp_path)
    data = b"A separately persisted catalog must not be assumed consistent. " * 20
    try:
        created = await IngestionService(engine, MockTokenCounter(), principal=owner).ingest_source(
            notebook_id=notebook_id, filename="catalog.txt", data=data
        )
        asset_id = FilesystemBlobStore.asset_id_for_hash(created.content_hash)
        original = await storage.get_asset_record(asset_id)
        assert original is not None
        await storage.delete_source(created.source_id)
        await storage._sql.delete_document_cascade(created.document_id)
        assert not await storage._sql.is_asset_referenced(asset_id)
        if fault == "catalog_mismatch":
            db = storage._sql._require_open()
            await db.execute(
                "UPDATE asset_catalog SET mime_type=? WHERE asset_id=?",
                ("application/x-corrupt", str(asset_id)),
            )
            await db.commit()
            expected = "identity is inconsistent"
        else:

            async def refuse_delete(_asset_id: UUID) -> bool:
                return False

            monkeypatch.setattr(storage._sql, "delete_asset_catalog_record", refuse_delete)
            expected = "remained after reconciliation"
        with pytest.raises(IntegrityError, match=expected):
            await storage.reconcile_orphan_asset_candidate(
                created.content_hash, (original.mime_type,)
            )
        assert await storage.get_asset(asset_id) == data
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_source_delete_hard_crash_after_sql_write_recovers_after_restart(
    tmp_path: Path,
) -> None:
    storage, vectors, authority, engine, notebook_id, owner, reader = await _fixture(tmp_path)
    service = IngestionService(engine, MockTokenCounter(), principal=owner)
    script = (
        "import os, sqlite3, sys; from pathlib import Path; from uuid import UUID; "
        "from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority; "
        "a=SQLiteNotebookScopeAuthority(Path(sys.argv[1])); "
        "lock=a.source_ingestion_process_lock(); lease=lock.__enter__(); "
        "a.reserve_source_deletion(actor_id=UUID(sys.argv[3]), "
        "notebook_id=UUID(sys.argv[4]), source_id=UUID(sys.argv[5]), "
        "document_id=UUID(sys.argv[6]), token=UUID(sys.argv[7]), process_lease=lease); "
        "db=sqlite3.connect(sys.argv[2]); "
        "db.execute('DELETE FROM sources WHERE source_id=?', (sys.argv[5],)); "
        "db.commit(); os._exit(19)"
    )
    try:
        created = await service.ingest_source(
            notebook_id=notebook_id,
            filename="crash-delete.txt",
            data=b"A disposable source interrupted after canonical deletion. " * 80,
        )
        child = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                script,
                str(authority.path),
                str(tmp_path / "canonical.db"),
                str(owner.actor_id),
                str(notebook_id),
                str(created.source_id),
                str(created.document_id),
                str(uuid4()),
            ],
            check=False,
            capture_output=True,
            timeout=10,
        )
        assert child.returncode == 19, child.stderr.decode(errors="replace")
        restarted = SQLiteNotebookScopeAuthority(authority.path)
        assert not restarted.permits(reader.actor_id, notebook_id)
        assert await storage.get_source(created.source_id) is None
        before = vectors._set_document_membership.await_count
        await service.reconcile_failed_source_deletion(
            notebook_id=notebook_id, source_id=created.source_id
        )
        assert vectors._set_document_membership.await_count == before + 1
        assert restarted.permits(reader.actor_id, notebook_id)
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_deleting_one_notebook_source_preserves_shared_document_and_asset(
    tmp_path: Path,
) -> None:
    storage, _, authority, engine, notebook_id, owner, reader = await _fixture(tmp_path)
    second_notebook = uuid4()
    now = datetime.now(UTC)
    await storage.upsert_notebook(
        Notebook(notebook_id=second_notebook, title="shared", created_at=now, updated_at=now)
    )
    authority.grant(
        actor_id=owner.actor_id,
        notebook_id=second_notebook,
        role="owner",
        operator_id=owner.actor_id,
    )
    authority.grant(
        actor_id=reader.actor_id,
        notebook_id=second_notebook,
        role="reader",
        operator_id=owner.actor_id,
    )
    service = IngestionService(engine, MockTokenCounter(), principal=owner)
    data = b"The same exact source belongs to two authorized notebooks. " * 80
    try:
        first = await service.ingest_source(
            notebook_id=notebook_id, filename="shared.txt", data=data
        )
        second = await service.ingest_source(
            notebook_id=second_notebook, filename="shared.txt", data=data
        )
        assert second.deduplicated
        assert first.document_id == second.document_id
        await service.delete_source(notebook_id=notebook_id, source_id=first.source_id)
        assert await storage.get_source(first.source_id) is None
        assert await storage.get_source(second.source_id) is not None
        document = await storage.get_document(first.document_id)
        assert document is not None
        assert await storage.get_parsed_document(document.current_version_id) is not None
        assert authority.permits(reader.actor_id, second_notebook)
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_reserved_source_delete_recovers_after_interruption_before_sql_write(
    tmp_path: Path,
) -> None:
    storage, vectors, authority, engine, notebook_id, owner, reader = await _fixture(tmp_path)
    service = IngestionService(engine, MockTokenCounter(), principal=owner)
    try:
        created = await service.ingest_source(
            notebook_id=notebook_id,
            filename="reserved.txt",
            data=b"A source interrupted after its deletion reservation. " * 80,
        )
        with authority.source_ingestion_process_lock() as lease:
            authority.reserve_source_deletion(
                actor_id=owner.actor_id,
                notebook_id=notebook_id,
                source_id=created.source_id,
                document_id=created.document_id,
                token=uuid4(),
                process_lease=lease,
            )
        assert await storage.get_source(created.source_id) is not None
        assert not authority.permits(reader.actor_id, notebook_id)
        with pytest.raises(NotFoundError):
            await service.delete_source(notebook_id=notebook_id, source_id=created.source_id)
        await service.reconcile_failed_source_deletion(
            notebook_id=notebook_id, source_id=created.source_id
        )
        assert await storage.get_source(created.source_id) is None
        assert authority.permits(reader.actor_id, notebook_id)
        assert vectors._set_document_membership.await_count >= 2
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_source_delete_recovery_fails_closed_after_owner_revocation(tmp_path: Path) -> None:
    storage, _, authority, engine, notebook_id, owner, reader = await _fixture(tmp_path)
    service = IngestionService(engine, MockTokenCounter(), principal=owner)
    try:
        created = await service.ingest_source(
            notebook_id=notebook_id,
            filename="revoked.txt",
            data=b"The owner loses authority before deletion recovery. " * 80,
        )
        with authority.source_ingestion_process_lock() as lease:
            authority.reserve_source_deletion(
                actor_id=owner.actor_id,
                notebook_id=notebook_id,
                source_id=created.source_id,
                document_id=created.document_id,
                token=uuid4(),
                process_lease=lease,
            )
        authority.revoke(actor_id=owner.actor_id, notebook_id=notebook_id)
        with pytest.raises(NotFoundError):
            await service.reconcile_failed_source_deletion(
                notebook_id=notebook_id, source_id=created.source_id
            )
        assert await storage.get_source(created.source_id) is not None
        assert not authority.permits(reader.actor_id, notebook_id)
        assert authority.revision(notebook_id) is None
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_composite_delete_requires_trusted_principal_and_membership_authority(
    tmp_path: Path,
) -> None:
    storage, _, authority, engine, notebook_id, owner, _ = await _fixture(tmp_path)
    service = IngestionService(engine, MockTokenCounter(), principal=owner)
    try:
        created = await service.ingest_source(
            notebook_id=notebook_id,
            filename="identity.txt",
            data=b"Deletion must require a trusted identity and ACL authority. " * 80,
        )
        with pytest.raises(DependencyUnavailableError):
            await IngestionService(engine, MockTokenCounter()).delete_source(
                notebook_id=notebook_id, source_id=created.source_id
            )
        engine.server_scope_authority = object()
        with pytest.raises(DependencyUnavailableError):
            await service.delete_source(notebook_id=notebook_id, source_id=created.source_id)
        assert await storage.get_source(created.source_id) is not None
        engine.server_scope_authority = authority
        await service.delete_source(notebook_id=notebook_id, source_id=created.source_id)
        assert await storage.get_source(created.source_id) is None
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_acl_ingestion_vector_failure_quarantines_partial_artifacts(tmp_path: Path) -> None:
    storage, vectors, authority, engine, notebook_id, owner, reader = await _fixture(tmp_path)
    data = b"A private source requiring vector projection. " * 80
    content_hash = hashlib.sha256(data).hexdigest()
    vectors._set_document_membership.side_effect = RuntimeError("vector unavailable")
    try:
        with pytest.raises(StorageError):
            await IngestionService(engine, MockTokenCounter(), principal=owner).ingest_source(
                notebook_id=notebook_id, filename="failed.txt", data=data
            )
        restarted = SQLiteNotebookScopeAuthority(authority.path)
        assert restarted.source_ingestion_state(notebook_id, content_hash) == "failed"
        assert not restarted.permits(owner.actor_id, notebook_id)
        assert not restarted.permits(reader.actor_id, notebook_id)
        assert restarted.authorized_notebook_ids(owner.actor_id) == ()
        with pytest.raises(NotFoundError):
            await AuthorizedNotebookScopeResolver(storage, restarted).resolve(
                reader, (notebook_id,)
            )
        with pytest.raises(NotFoundError):
            await IngestionService(engine, MockTokenCounter(), principal=owner).ingest_source(
                notebook_id=notebook_id, filename="retry.txt", data=data
            )
        vectors._set_document_membership.side_effect = None
        await IngestionService(
            engine, MockTokenCounter(), principal=owner
        ).reconcile_failed_source_ingestion(notebook_id=notebook_id, content_hash=content_hash)
        assert restarted.source_ingestion_state(notebook_id, content_hash) == "recoverable"
        assert restarted.permits(reader.actor_id, notebook_id)
        retried = await IngestionService(engine, MockTokenCounter(), principal=owner).ingest_source(
            notebook_id=notebook_id, filename="retried.txt", data=data
        )
        assert retried.status == "indexed"
        assert restarted.source_ingestion_state(notebook_id, content_hash) == "published"
        assert await storage.get_source(retried.source_id) is not None
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_recovery_retries_after_sql_cascade_but_before_ir_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage, vectors, authority, engine, notebook_id, owner, _ = await _fixture(tmp_path)
    data = b"Interrupted cleanup must preserve the journal quarantine. " * 80
    content_hash = hashlib.sha256(data).hexdigest()
    service = IngestionService(engine, MockTokenCounter(), principal=owner)
    vectors._set_document_membership.side_effect = RuntimeError("projection unavailable")
    try:
        with pytest.raises(StorageError):
            await service.ingest_source(notebook_id=notebook_id, filename="cleanup.txt", data=data)
        vectors._set_document_membership.side_effect = None
        original_delete = FilesystemBlobStore.delete_parsed_document

        async def interrupted_delete(self: FilesystemBlobStore, version_id: UUID) -> bool:
            raise StorageError("filesystem unavailable after canonical cascade")

        with monkeypatch.context() as patch:
            patch.setattr(FilesystemBlobStore, "delete_parsed_document", interrupted_delete)
            with pytest.raises(StorageError, match="filesystem unavailable"):
                await service.reconcile_failed_source_ingestion(
                    notebook_id=notebook_id, content_hash=content_hash
                )
        assert FilesystemBlobStore.delete_parsed_document is original_delete
        assert await storage.get_document_by_content_hash(content_hash) is None
        assert authority.source_ingestion_state(notebook_id, content_hash) == "failed"
        assert not authority.permits(owner.actor_id, notebook_id)
        await service.reconcile_failed_source_ingestion(
            notebook_id=notebook_id, content_hash=content_hash
        )
        assert authority.source_ingestion_state(notebook_id, content_hash) == "recoverable"
        retried = await service.ingest_source(
            notebook_id=notebook_id, filename="cleanup.txt", data=data
        )
        assert retried.status == "indexed"
        assert authority.source_ingestion_state(notebook_id, content_hash) == "published"
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_acl_ingestion_interrupted_after_source_write_stays_quarantined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage, vectors, authority, engine, notebook_id, owner, reader = await _fixture(tmp_path)
    data = b"A private source interrupted after canonical association. " * 80
    content_hash = hashlib.sha256(data).hexdigest()
    original_lease = authority.source_ingestion_write_lease

    @contextmanager
    def interrupted_lease(
        *,
        actor_id: UUID,
        notebook_id: UUID,
        content_hash: str,
        token: UUID,
        reserved_revision: int,
        process_lease: object | None = None,
    ) -> Iterator[Callable[[UUID], None]]:
        with original_lease(
            actor_id=actor_id,
            notebook_id=notebook_id,
            content_hash=content_hash,
            token=token,
            reserved_revision=reserved_revision,
            process_lease=process_lease,
        ) as publish:
            yield publish
            raise RuntimeError("simulated interruption before journal publication")

    monkeypatch.setattr(authority, "source_ingestion_write_lease", interrupted_lease)
    try:
        with pytest.raises(RuntimeError, match="simulated interruption"):
            await IngestionService(engine, MockTokenCounter(), principal=owner).ingest_source(
                notebook_id=notebook_id, filename="interrupted.txt", data=data
            )
        assert vectors._set_document_membership.await_count == 1
        restarted = SQLiteNotebookScopeAuthority(authority.path)
        assert restarted.source_ingestion_state(notebook_id, content_hash) == "failed"
        assert restarted.authorized_notebook_ids(reader.actor_id) == ()
        with pytest.raises(NotFoundError):
            await AuthorizedNotebookScopeResolver(storage, restarted).resolve(owner, (notebook_id,))
        document = await storage.get_document_by_content_hash(content_hash)
        assert document is not None
        source = await IngestionService(
            engine, MockTokenCounter(), principal=owner
        )._find_source_in_notebook(notebook_id, document.document_id)
        assert source is not None
        await IngestionService(
            engine, MockTokenCounter(), principal=owner
        ).reconcile_failed_source_ingestion(notebook_id=notebook_id, content_hash=content_hash)
        assert await storage.get_source(source.source_id) is None
        assert restarted.source_ingestion_state(notebook_id, content_hash) == "recoverable"
        assert restarted.permits(reader.actor_id, notebook_id)
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_acl_source_recovery_requires_owner_and_successful_reprojection(
    tmp_path: Path,
) -> None:
    storage, vectors, authority, engine, notebook_id, owner, reader = await _fixture(tmp_path)
    data = b"A source whose projection fails until a safe rollback. " * 80
    content_hash = hashlib.sha256(data).hexdigest()
    vectors._set_document_membership.side_effect = RuntimeError("projection unavailable")
    try:
        with pytest.raises(StorageError):
            await IngestionService(engine, MockTokenCounter(), principal=owner).ingest_source(
                notebook_id=notebook_id, filename="private.txt", data=data
            )
        assert authority.source_ingestion_state(notebook_id, content_hash) == "failed"
        with pytest.raises(NotFoundError):
            await IngestionService(
                engine, MockTokenCounter(), principal=reader
            ).reconcile_failed_source_ingestion(notebook_id=notebook_id, content_hash=content_hash)
        with pytest.raises(RuntimeError, match="projection unavailable"):
            await IngestionService(
                engine, MockTokenCounter(), principal=owner
            ).reconcile_failed_source_ingestion(notebook_id=notebook_id, content_hash=content_hash)
        assert authority.source_ingestion_state(notebook_id, content_hash) == "failed"
        assert not authority.permits(reader.actor_id, notebook_id)
        vectors._set_document_membership.side_effect = None
        await IngestionService(
            engine, MockTokenCounter(), principal=owner
        ).reconcile_failed_source_ingestion(notebook_id=notebook_id, content_hash=content_hash)
        assert authority.source_ingestion_state(notebook_id, content_hash) == "recoverable"
        assert authority.permits(reader.actor_id, notebook_id)
        revision = authority.revision(notebook_id)
        projections = vectors._set_document_membership.await_count
        await IngestionService(
            engine, MockTokenCounter(), principal=owner
        ).reconcile_failed_source_ingestion(notebook_id=notebook_id, content_hash=content_hash)
        assert authority.revision(notebook_id) == revision
        assert vectors._set_document_membership.await_count == projections
    finally:
        await storage.close()
