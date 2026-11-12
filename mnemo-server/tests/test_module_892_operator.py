"""Explicit owner actions cannot use a forged or missing actor identity."""

import base64
import hashlib
import hmac
import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from mnemo.interfaces import NotFoundError
from mnemo.models import Notebook
from mnemo.storage.sqlite import SQLiteStore
from mnemo_server.auth import AuthError
from mnemo_server.services.membership_operator import MembershipOperatorService
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority
from mnemo_server.services.trusted_actor import TrustedJWTActorMapper


def _signed_token(subject: str, *, secret: str = "fixture-secret") -> str:
    def encoded(value: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

    claims: dict[str, object] = {
        "iss": "fixture-issuer",
        "aud": "fixture-audience",
        "sub": subject,
        "exp": int(time.time()) + 60,
        "actor_id": "forged-client-id",
    }
    signed = f"{encoded({'alg': 'HS256'})}.{encoded(claims)}"
    digest = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).digest()
    return f"{signed}.{base64.urlsafe_b64encode(digest).rstrip(b'=').decode()}"


@pytest.mark.anyio
async def test_owner_only_grant_revoke_and_legacy_quarantine(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "notebooks.db")
    await store.open()
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", "fixture-secret")
    service = MembershipOperatorService(store, authority, mapper)
    owner = mapper.from_token(_signed_token("owner")).actor_id
    reader = mapper.from_token(_signed_token("reader")).actor_id
    stranger = mapper.from_token(_signed_token("stranger")).actor_id
    notebook_id, legacy_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    try:
        for identity in (notebook_id, legacy_id):
            await store.upsert_notebook(
                Notebook(notebook_id=identity, title="fixture", created_at=now, updated_at=now)
            )
        authority.grant(actor_id=owner, notebook_id=notebook_id, role="owner", operator_id=owner)
        with pytest.raises(NotFoundError):
            await service.grant_reader(
                token=_signed_token("stranger"), notebook_id=notebook_id, reader_id=reader
            )
        with pytest.raises(NotFoundError):
            await service.grant_reader(
                token=_signed_token("owner"), notebook_id=legacy_id, reader_id=reader
            )
        with pytest.raises(NotFoundError):
            await service.grant_reader(
                token=_signed_token("stranger"), notebook_id=uuid4(), reader_id=reader
            )
        with pytest.raises(AuthError):
            await service.grant_reader(
                token=_signed_token("owner", secret="wrong"),
                notebook_id=notebook_id,
                reader_id=reader,
            )
        await service.grant_reader(
            token=_signed_token("owner"), notebook_id=notebook_id, reader_id=reader
        )
        assert authority.permits(reader, notebook_id)
        assert not authority.permits(reader, notebook_id, operation="write")
        with pytest.raises(NotFoundError):
            await service.grant_reader(
                token=_signed_token("reader"), notebook_id=notebook_id, reader_id=stranger
            )
        with pytest.raises(NotFoundError):
            await service.revoke_reader(
                token=_signed_token("stranger"), notebook_id=notebook_id, reader_id=reader
            )
        await service.revoke_reader(
            token=_signed_token("owner"), notebook_id=notebook_id, reader_id=reader
        )
        assert not authority.permits(reader, notebook_id)
        assert not authority.permits(stranger, notebook_id)
    finally:
        await store.close()


@pytest.mark.anyio
async def test_owner_revoked_after_precheck_cannot_commit_reader_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SQLiteStore(tmp_path / "notebooks.db")
    await store.open()
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", "fixture-secret")
    service = MembershipOperatorService(store, authority, mapper)
    owner = mapper.from_token(_signed_token("owner")).actor_id
    reader = mapper.from_token(_signed_token("reader")).actor_id
    notebook_id = uuid4()
    now = datetime.now(UTC)
    try:
        await store.upsert_notebook(
            Notebook(notebook_id=notebook_id, title="fixture", created_at=now, updated_at=now)
        )
        authority.grant(actor_id=owner, notebook_id=notebook_id, role="owner", operator_id=owner)
        original = authority.grant_reader_as_owner

        def revoke_before_write(**kwargs: Any) -> None:
            authority.revoke(actor_id=owner, notebook_id=notebook_id)
            original(**kwargs)

        monkeypatch.setattr(authority, "grant_reader_as_owner", revoke_before_write)
        with pytest.raises(NotFoundError):
            await service.grant_reader(
                token=_signed_token("owner"), notebook_id=notebook_id, reader_id=reader
            )
        assert authority.active_role(reader, notebook_id) is None
        assert authority.revision(notebook_id) == 2
    finally:
        await store.close()


@pytest.mark.anyio
async def test_owner_revoked_after_precheck_cannot_revoke_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SQLiteStore(tmp_path / "notebooks.db")
    await store.open()
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", "fixture-secret")
    service = MembershipOperatorService(store, authority, mapper)
    owner = mapper.from_token(_signed_token("owner")).actor_id
    reader = mapper.from_token(_signed_token("reader")).actor_id
    notebook_id = uuid4()
    now = datetime.now(UTC)
    try:
        await store.upsert_notebook(
            Notebook(notebook_id=notebook_id, title="fixture", created_at=now, updated_at=now)
        )
        authority.grant(actor_id=owner, notebook_id=notebook_id, role="owner", operator_id=owner)
        authority.grant(actor_id=reader, notebook_id=notebook_id, role="reader", operator_id=owner)
        original = authority.revoke_reader_as_owner

        def revoke_before_write(**kwargs: Any) -> None:
            authority.revoke(actor_id=owner, notebook_id=notebook_id)
            original(**kwargs)

        monkeypatch.setattr(authority, "revoke_reader_as_owner", revoke_before_write)
        with pytest.raises(NotFoundError):
            await service.revoke_reader(
                token=_signed_token("owner"), notebook_id=notebook_id, reader_id=reader
            )
        assert authority.active_role(reader, notebook_id) == "reader"
        assert authority.revision(notebook_id) == 3
    finally:
        await store.close()


@pytest.mark.anyio
async def test_grant_write_failure_rolls_back_revision_and_membership(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "notebooks.db")
    await store.open()
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", "fixture-secret")
    service = MembershipOperatorService(store, authority, mapper)
    owner = mapper.from_token(_signed_token("owner")).actor_id
    reader = mapper.from_token(_signed_token("reader")).actor_id
    notebook_id = uuid4()
    now = datetime.now(UTC)
    try:
        await store.upsert_notebook(
            Notebook(notebook_id=notebook_id, title="fixture", created_at=now, updated_at=now)
        )
        authority.grant(actor_id=owner, notebook_id=notebook_id, role="owner", operator_id=owner)
        with sqlite3.connect(authority.path) as connection:
            connection.execute(
                "CREATE TRIGGER fail_reader BEFORE INSERT ON notebook_grants "
                "WHEN NEW.role='reader' BEGIN SELECT RAISE(ABORT, 'fixture failure'); END"
            )
        with pytest.raises(sqlite3.IntegrityError, match="fixture failure"):
            await service.grant_reader(
                token=_signed_token("owner"), notebook_id=notebook_id, reader_id=reader
            )
        assert authority.active_role(reader, notebook_id) is None
        assert authority.revision(notebook_id) == 1
    finally:
        await store.close()


@pytest.mark.anyio
async def test_only_intent_actor_can_resume_durable_create(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "notebooks.db")
    await store.open()
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", "fixture-secret")
    service = MembershipOperatorService(store, authority, mapper)
    owner = mapper.from_token(_signed_token("owner")).actor_id
    notebook_id, token = uuid4(), uuid4()
    now = datetime.now(UTC)
    notebook = Notebook(notebook_id=notebook_id, title="pending", created_at=now, updated_at=now)
    try:
        authority.reserve_create(
            notebook_id=notebook_id, actor_id=owner, token=token, notebook=notebook
        )
        with pytest.raises(NotFoundError):
            await service.recover_own_pending_create(
                token=_signed_token("stranger"), notebook_id=notebook_id
            )
        assert not authority.permits(owner, notebook_id)
        result = await service.recover_own_pending_create(
            token=_signed_token("owner"), notebook_id=notebook_id
        )
        assert result == notebook
        assert authority.permits(owner, notebook_id, operation="write")
    finally:
        await store.close()
