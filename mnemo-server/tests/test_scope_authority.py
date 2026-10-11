"""Persistent explicit grants must not follow notebook existence implicitly."""

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import NotFoundError, PrincipalContextV1
from mnemo_server.services.authorization import (
    AuthorizationOperationV1,
    CentralAuthorizationServiceV1,
)
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority


def _authority(tmp_path: Path) -> SQLiteNotebookScopeAuthority:
    authority = SQLiteNotebookScopeAuthority((tmp_path / "operational/acl.db").resolve())
    authority.initialize()
    return authority


def test_unknown_actor_and_cross_notebook_access_are_denied(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    owner, stranger, notebook, other = uuid4(), uuid4(), uuid4(), uuid4()
    assert not authority.permits(owner, notebook)
    authority.grant(actor_id=owner, notebook_id=notebook, role="owner", operator_id=uuid4())
    assert authority.permits(owner, notebook)
    assert not authority.permits(stranger, notebook)
    assert not authority.permits(owner, other)
    reloaded = SQLiteNotebookScopeAuthority(authority.path)
    assert reloaded.permits(owner, notebook)


def test_no_implicit_grant_or_unsupported_role(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    actor, notebook = uuid4(), uuid4()
    with pytest.raises(ValueError, match="role"):
        authority.grant(actor_id=actor, notebook_id=notebook, role="everyone", operator_id=uuid4())
    assert not authority.permits(actor, notebook)


def test_retired_notebook_cannot_reactivate_stale_grants(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    actor, notebook, unrelated = uuid4(), uuid4(), uuid4()
    authority.grant(actor_id=actor, notebook_id=notebook, role="owner", operator_id=uuid4())
    authority.grant(actor_id=actor, notebook_id=unrelated, role="owner", operator_id=uuid4())
    authority.retire_notebook(notebook)
    authority.retire_notebook(notebook)  # retry is idempotent
    reloaded = SQLiteNotebookScopeAuthority(authority.path)
    assert not reloaded.permits(actor, notebook)
    assert reloaded.permits(actor, unrelated)
    with pytest.raises(ValueError, match="retired notebook"):
        reloaded.grant(actor_id=actor, notebook_id=notebook, role="owner", operator_id=uuid4())


def test_scope_authority_fails_closed_when_missing_or_malformed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="path must be absolute"):
        SQLiteNotebookScopeAuthority(Path("relative-acl.db"))
    authority = SQLiteNotebookScopeAuthority((tmp_path / "missing.db").resolve())
    actor, notebook = uuid4(), uuid4()
    assert not authority.permits(actor, notebook)
    with pytest.raises(RuntimeError, match="not been initialized"):
        authority.grant(actor_id=actor, notebook_id=notebook, role="owner", operator_id=uuid4())
    with pytest.raises(RuntimeError, match="not been initialized"):
        authority.retire_notebook(notebook)
    with sqlite3.connect(authority.path) as connection:
        connection.execute("CREATE TABLE unrelated(id INTEGER)")
    assert not authority.permits(actor, notebook)


def test_duplicate_grant_rolls_back_without_changing_existing_owner(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    actor, notebook = uuid4(), uuid4()
    authority.grant(actor_id=actor, notebook_id=notebook, role="owner", operator_id=uuid4())
    with pytest.raises(sqlite3.IntegrityError):
        authority.grant(actor_id=actor, notebook_id=notebook, role="reader", operator_id=uuid4())
    with sqlite3.connect(authority.path) as connection:
        role = connection.execute(
            "SELECT role FROM notebook_grants WHERE actor_id=? AND notebook_id=?",
            (str(actor), str(notebook)),
        ).fetchone()
    assert role == ("owner",)


@pytest.mark.anyio
async def test_central_authorization_checks_grant_before_notebook_or_document(
    tmp_path: Path,
) -> None:
    authority = _authority(tmp_path)
    actor, stranger, notebook, document, version = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    engine = MagicMock(spec=KnowledgeEngine)
    engine.storage.get_notebook = AsyncMock(return_value=object())
    engine.document_scope_resolver.resolve_document_scope = AsyncMock(return_value=object())
    service = CentralAuthorizationServiceV1(engine, authority)
    with pytest.raises(NotFoundError, match="authorized resource"):
        await service.authorize_notebook(
            PrincipalContextV1(actor, True), notebook, AuthorizationOperationV1.QUERY
        )
    engine.storage.get_notebook.assert_not_called()
    with pytest.raises(NotFoundError, match="authorized resource"):
        await service.authorize_document(
            PrincipalContextV1(stranger, True),
            notebook,
            document,
            version,
            AuthorizationOperationV1.RETRIEVE,
        )
    engine.document_scope_resolver.resolve_document_scope.assert_not_called()
    authority.grant(actor_id=actor, notebook_id=notebook, role="owner", operator_id=uuid4())
    decision = await service.authorize_notebook(
        PrincipalContextV1(actor, True), notebook, AuthorizationOperationV1.QUERY
    )
    assert decision.allowed
    await service.authorize_document(
        PrincipalContextV1(actor, True),
        notebook,
        document,
        version,
        AuthorizationOperationV1.RETRIEVE,
    )
    engine.document_scope_resolver.resolve_document_scope.assert_awaited_once()
