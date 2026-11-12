"""Persistent explicit grants must not follow notebook existence implicitly."""

import hashlib
import sqlite3
from pathlib import Path
from typing import TypedDict
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import DependencyUnavailableError, NotFoundError, PrincipalContextV1
from mnemo_server.services.authorization import (
    AuthorizationOperationV1,
    CentralAuthorizationServiceV1,
)
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority


class _FinalQABindingClaim(TypedDict):
    assistant_turn_id: UUID
    actor_id: UUID
    notebook_id: UUID
    session_id: UUID
    user_turn_id: UUID
    acl_revision: int


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
    assert authority.authorized_notebook_ids(owner) == (notebook,)
    assert authority.authorized_notebook_ids(stranger) == ()
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
    with pytest.raises(NotFoundError, match="authorized resource was not found"):
        authority.retire_notebook(notebook)
    with pytest.raises(NotFoundError, match="authorized resource was not found"):
        authority.retire_notebook(notebook, operator_id=uuid4())
    assert authority.permits(actor, notebook)
    authority.retire_notebook(notebook, operator_id=actor)
    authority.retire_notebook(notebook)  # retry is idempotent
    reloaded = SQLiteNotebookScopeAuthority(authority.path)
    assert not reloaded.permits(actor, notebook)
    assert reloaded.permits(actor, unrelated)
    assert reloaded.authorized_notebook_ids(actor) == (unrelated,)
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


def test_missing_acl_store_cannot_grant_or_resume_membership(tmp_path: Path) -> None:
    """A missing operational store must never appear as an empty but writable ACL."""
    authority = SQLiteNotebookScopeAuthority((tmp_path / "absent-acl.db").resolve())
    owner, reader, notebook, token = uuid4(), uuid4(), uuid4(), uuid4()
    with pytest.raises(NotFoundError):
        authority.grant_reader_as_owner(operator_id=owner, notebook_id=notebook, reader_id=reader)
    with pytest.raises(NotFoundError):
        authority.revoke_reader_as_owner(operator_id=owner, notebook_id=notebook, reader_id=reader)
    with pytest.raises(RuntimeError, match="not been initialized"):
        authority.reserve_create(notebook_id=notebook, actor_id=owner, token=token)
    with pytest.raises(RuntimeError, match="not been initialized"):
        authority.finish_create(notebook_id=notebook, actor_id=owner, token=token)
    assert authority.pending_create(notebook) is None
    assert authority.pending_create_record(notebook) is None
    assert authority.authorized_notebook_ids(owner) == ()
    assert authority.active_role(owner, notebook) is None
    assert authority.revision(notebook) is None
    assert not authority.permits(owner, notebook)
    assert not authority.path.exists()


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


def test_explicit_legacy_migration_quarantines_grants_and_is_idempotent(tmp_path: Path) -> None:
    path = (tmp_path / "old-acl.db").resolve()
    actor, notebook, operator = uuid4(), uuid4(), uuid4()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE notebook_grants(actor_id TEXT NOT NULL, notebook_id TEXT NOT NULL, "
            "role TEXT NOT NULL, granted_by TEXT NOT NULL, "
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "PRIMARY KEY(actor_id, notebook_id))"
        )
        connection.execute(
            "CREATE TABLE retired_notebook_ids(notebook_id TEXT PRIMARY KEY, "
            "retired_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO notebook_grants(actor_id, notebook_id, role, granted_by) VALUES(?,?,?,?)",
            (str(actor), str(notebook), "owner", str(operator)),
        )
    authority = SQLiteNotebookScopeAuthority(path)
    assert not authority.permits(actor, notebook)
    authority.migrate_legacy_grants_unverified()
    authority.migrate_legacy_grants_unverified()
    assert not authority.permits(actor, notebook)
    assert authority.revision(notebook) == 1
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT status FROM notebook_grants WHERE notebook_id=?", (str(notebook),)
        ).fetchone() == ("unverified",)


def test_create_intent_payload_migration_does_not_infer_missing_record(tmp_path: Path) -> None:
    path = (tmp_path / "old-intents.db").resolve()
    owner, notebook, token = uuid4(), uuid4(), uuid4()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE notebook_create_intents("
            "notebook_id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, token TEXT NOT NULL UNIQUE)"
        )
        connection.execute(
            "INSERT INTO notebook_create_intents VALUES(?,?,?)",
            (str(notebook), str(owner), str(token)),
        )
    authority = SQLiteNotebookScopeAuthority(path)
    authority.initialize()
    assert authority.pending_create(notebook) == (owner, token)
    assert authority.pending_create_record(notebook) is None
    assert not authority.permits(owner, notebook)
    with sqlite3.connect(path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(notebook_create_intents)")
        }
        assert "payload" in columns
        assert connection.execute(
            "SELECT payload FROM notebook_create_intents WHERE notebook_id=?",
            (str(notebook),),
        ).fetchone() == (None,)


def test_revision_revoke_roles_and_retirement_are_fail_closed(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    owner, reader, notebook = uuid4(), uuid4(), uuid4()
    authority.grant(actor_id=owner, notebook_id=notebook, role="owner", operator_id=owner)
    first_revision = authority.revision(notebook)
    assert first_revision == 1
    authority.grant(actor_id=reader, notebook_id=notebook, role="reader", operator_id=owner)
    assert authority.revision(notebook) == 2
    assert authority.permits(reader, notebook)
    assert not authority.permits(reader, notebook, operation="write")
    assert authority.permits(owner, notebook, operation="write")
    authority.revoke(actor_id=reader, notebook_id=notebook)
    assert authority.revision(notebook) == 3
    assert not authority.permits(reader, notebook)
    authority.revoke(actor_id=reader, notebook_id=notebook)
    assert authority.revision(notebook) == 3
    authority.retire_notebook(notebook, operator_id=owner)
    assert authority.revision(notebook) == 4
    authority.retire_notebook(notebook)
    assert authority.revision(notebook) == 4
    assert not authority.permits(owner, notebook)


def test_v1_final_qa_binding_is_owner_and_revision_scoped(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    owner, reader, notebook, session, user_turn, assistant_turn = (uuid4() for _ in range(6))
    authority.grant(actor_id=owner, notebook_id=notebook, role="owner", operator_id=owner)
    revision = authority.revision(notebook)
    assert revision == 1
    claim: _FinalQABindingClaim = dict(
        assistant_turn_id=assistant_turn,
        actor_id=owner,
        notebook_id=notebook,
        session_id=session,
        user_turn_id=user_turn,
        acl_revision=revision,
    )
    with pytest.raises(NotFoundError):
        authority.verify_final_qa_v1_execution(**claim)
    authority.bind_final_qa_v1_execution(**claim)
    authority.bind_final_qa_v1_execution(**claim)  # exact retry is idempotent
    authority.verify_final_qa_v1_execution(**claim)
    document, version = uuid4(), uuid4()
    documents = ((document, version),)
    with pytest.raises(NotFoundError):
        authority.verify_final_qa_v1_execution(**claim, require_documents=True)
    authority.bind_final_qa_v1_documents(**claim, documents=documents)
    authority.bind_final_qa_v1_documents(**claim, documents=documents)
    assert authority.verify_final_qa_v1_execution(**claim, require_documents=True) == documents
    with pytest.raises(ValueError):
        authority.bind_final_qa_v1_documents(**claim, documents=documents + documents)
    with pytest.raises(NotFoundError):
        authority.bind_final_qa_v1_documents(**claim, documents=())
    other_actor = claim.copy()
    other_actor["actor_id"] = reader
    with pytest.raises(NotFoundError):
        authority.bind_final_qa_v1_execution(**other_actor)
    other_session = claim.copy()
    other_session["session_id"] = uuid4()
    with pytest.raises(NotFoundError):
        authority.verify_final_qa_v1_execution(**other_session)
    authority.grant(actor_id=reader, notebook_id=notebook, role="reader", operator_id=owner)
    with pytest.raises(NotFoundError):
        authority.verify_final_qa_v1_execution(**claim)
    with pytest.raises(NotFoundError):
        authority.bind_final_qa_v1_execution(**claim)
    authority.revoke(actor_id=owner, notebook_id=notebook)
    with pytest.raises(NotFoundError):
        authority.verify_final_qa_v1_execution(**claim)


@pytest.mark.parametrize(
    "corrupted_binding",
    (
        "not-json",
        "{}",
        '[["not-a-document-id", "not-a-version-id"]]',
        '[["00000000-0000-0000-0000-000000000001", '
        '"00000000-0000-0000-0000-000000000002"], '
        '["00000000-0000-0000-0000-000000000001", '
        '"00000000-0000-0000-0000-000000000002"]]',
    ),
)
def test_v1_final_qa_corrupted_document_binding_fails_closed(
    tmp_path: Path, corrupted_binding: str
) -> None:
    """Persisted replay must never trust malformed or duplicated ancestry."""
    authority = _authority(tmp_path)
    owner, notebook, session, user_turn, assistant_turn = (uuid4() for _ in range(5))
    authority.grant(actor_id=owner, notebook_id=notebook, role="owner", operator_id=owner)
    revision = authority.revision(notebook)
    assert revision is not None
    claim: _FinalQABindingClaim = dict(
        assistant_turn_id=assistant_turn,
        actor_id=owner,
        notebook_id=notebook,
        session_id=session,
        user_turn_id=user_turn,
        acl_revision=revision,
    )
    authority.bind_final_qa_v1_execution(**claim)
    with sqlite3.connect(authority.path) as connection:
        connection.execute(
            "UPDATE final_qa_v1_acl_bindings SET document_scopes=? WHERE assistant_turn_id=?",
            (corrupted_binding, str(assistant_turn)),
        )
    with pytest.raises(DependencyUnavailableError):
        authority.verify_final_qa_v1_execution(**claim, require_documents=True)


def test_v1_final_qa_missing_authority_store_cannot_validate_replay(tmp_path: Path) -> None:
    authority = SQLiteNotebookScopeAuthority((tmp_path / "missing-acl.db").resolve())
    with pytest.raises(DependencyUnavailableError):
        authority.verify_final_qa_v1_execution(
            assistant_turn_id=uuid4(),
            actor_id=uuid4(),
            notebook_id=uuid4(),
            session_id=uuid4(),
            user_turn_id=uuid4(),
            acl_revision=1,
            require_documents=True,
        )


def test_source_ingestion_intent_quarantines_until_published_across_restarts(
    tmp_path: Path,
) -> None:
    authority = _authority(tmp_path)
    owner, reader, notebook, token, source = (uuid4() for _ in range(5))
    content_hash = hashlib.sha256(b"isolated source").hexdigest()
    authority.grant(actor_id=owner, notebook_id=notebook, role="owner", operator_id=owner)
    authority.grant(actor_id=reader, notebook_id=notebook, role="reader", operator_id=owner)
    old_revision = authority.revision(notebook)
    assert old_revision is not None
    reserved_revision = authority.reserve_source_ingestion(
        actor_id=owner, notebook_id=notebook, content_hash=content_hash, token=token
    )
    restarted = SQLiteNotebookScopeAuthority(authority.path)
    assert reserved_revision > old_revision
    assert restarted.source_ingestion_state(notebook, content_hash) == "incomplete"
    assert restarted.revision(notebook) is None
    assert not restarted.permits(owner, notebook)
    assert not restarted.permits(reader, notebook)
    assert restarted.authorized_notebook_ids(owner) == ()
    assert restarted.active_role(owner, notebook) is None
    with pytest.raises(DependencyUnavailableError):
        restarted.reserve_source_ingestion(
            actor_id=owner, notebook_id=notebook, content_hash=content_hash, token=token
        )
    with (
        pytest.raises(NotFoundError),
        restarted.owner_write_lease(actor_id=owner, notebook_id=notebook),
    ):
        pytest.fail("a quarantined notebook must not admit another write")
    with restarted.source_ingestion_write_lease(
        actor_id=owner,
        notebook_id=notebook,
        content_hash=content_hash,
        token=token,
        reserved_revision=reserved_revision,
    ) as publish:
        assert restarted.source_ingestion_state(notebook, content_hash) == "incomplete"
        publish(source)
    assert restarted.source_ingestion_state(notebook, content_hash) == "published"
    assert restarted.permits(owner, notebook, operation="write")
    assert restarted.permits(reader, notebook)
    assert restarted.revision(notebook) != reserved_revision


def test_source_ingestion_interruption_and_revocation_remain_quarantined(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    owner, reader, notebook, token = (uuid4() for _ in range(4))
    content_hash = hashlib.sha256(b"interrupted source").hexdigest()
    authority.grant(actor_id=owner, notebook_id=notebook, role="owner", operator_id=owner)
    authority.grant(actor_id=reader, notebook_id=notebook, role="reader", operator_id=owner)
    with pytest.raises(NotFoundError):
        authority.reserve_source_ingestion(
            actor_id=reader, notebook_id=notebook, content_hash=content_hash, token=token
        )
    revision = authority.reserve_source_ingestion(
        actor_id=owner, notebook_id=notebook, content_hash=content_hash, token=token
    )
    with (
        pytest.raises(RuntimeError, match="simulated process interruption"),
        authority.source_ingestion_write_lease(
            actor_id=owner,
            notebook_id=notebook,
            content_hash=content_hash,
            token=token,
            reserved_revision=revision,
        ) as publish,
    ):
        publish(uuid4())
        raise RuntimeError("simulated process interruption")
    assert authority.source_ingestion_state(notebook, content_hash) == "incomplete"
    assert not authority.permits(owner, notebook)
    authority.revoke(actor_id=owner, notebook_id=notebook)
    with (
        pytest.raises(NotFoundError),
        authority.source_ingestion_write_lease(
            actor_id=owner,
            notebook_id=notebook,
            content_hash=content_hash,
            token=token,
            reserved_revision=revision,
        ),
    ):
        pytest.fail("revocation must prevent publication")
    assert (
        SQLiteNotebookScopeAuthority(authority.path).source_ingestion_state(notebook, content_hash)
        == "incomplete"
    )


def test_source_recovery_needs_proof_and_cannot_follow_revocation(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    owner, reader, notebook, token = (uuid4() for _ in range(4))
    content_hash = hashlib.sha256(b"recovery proof").hexdigest()
    authority.grant(actor_id=owner, notebook_id=notebook, role="owner", operator_id=owner)
    authority.grant(actor_id=reader, notebook_id=notebook, role="reader", operator_id=owner)
    authority.reserve_source_ingestion(
        actor_id=owner, notebook_id=notebook, content_hash=content_hash, token=token
    )
    authority.mark_source_ingestion_failed(
        notebook_id=notebook, content_hash=content_hash, token=token
    )
    with (
        pytest.raises(DependencyUnavailableError, match="not verified"),
        authority.source_ingestion_recovery_lease(
            actor_id=owner, notebook_id=notebook, content_hash=content_hash
        ),
    ):
        pass
    assert authority.source_ingestion_state(notebook, content_hash) == "failed"
    assert not authority.permits(reader, notebook)
    with (
        pytest.raises(NotFoundError),
        authority.source_ingestion_recovery_lease(
            actor_id=reader, notebook_id=notebook, content_hash=content_hash
        ),
    ):
        pytest.fail("reader must not reconcile protected artifacts")
    authority.revoke(actor_id=owner, notebook_id=notebook)
    with (
        pytest.raises(NotFoundError),
        authority.source_ingestion_recovery_lease(
            actor_id=owner, notebook_id=notebook, content_hash=content_hash
        ),
    ):
        pytest.fail("revoked owner must not release quarantine")
    assert authority.source_ingestion_state(notebook, content_hash) == "failed"


def test_abandoned_ingestion_intent_blocks_parallel_notebooks_and_recovery(
    tmp_path: Path,
) -> None:
    authority = _authority(tmp_path)
    owner, notebook, other_notebook = (uuid4() for _ in range(3))
    content_hash = hashlib.sha256(b"same source in two notebooks").hexdigest()
    other_hash = hashlib.sha256(b"different source in same notebook").hexdigest()
    authority.grant(actor_id=owner, notebook_id=notebook, role="owner", operator_id=owner)
    authority.grant(actor_id=owner, notebook_id=other_notebook, role="owner", operator_id=owner)
    authority.reserve_source_ingestion(
        actor_id=owner, notebook_id=notebook, content_hash=content_hash, token=uuid4()
    )
    restarted = SQLiteNotebookScopeAuthority(authority.path)
    assert restarted.source_ingestion_state(notebook, content_hash) == "incomplete"
    with pytest.raises(DependencyUnavailableError, match="reconciliation"):
        restarted.reserve_source_ingestion(
            actor_id=owner, notebook_id=other_notebook, content_hash=content_hash, token=uuid4()
        )
    with pytest.raises(DependencyUnavailableError, match="reconciliation"):
        restarted.reserve_source_ingestion(
            actor_id=owner, notebook_id=notebook, content_hash=other_hash, token=uuid4()
        )
    with (
        pytest.raises(NotFoundError),
        restarted.source_ingestion_recovery_lease(
            actor_id=owner, notebook_id=notebook, content_hash=content_hash
        ),
    ):
        pytest.fail("an active-or-abandoned intent needs a separate writer-quiescence proof")
    assert restarted.source_ingestion_state(notebook, content_hash) == "incomplete"


def test_source_publication_rejects_invalid_hash_token_revision_and_missing_association(
    tmp_path: Path,
) -> None:
    missing = SQLiteNotebookScopeAuthority((tmp_path / "absent.db").resolve())
    with pytest.raises(DependencyUnavailableError):
        missing.source_ingestion_state(uuid4(), "0" * 64)
    owner, notebook, token = (uuid4() for _ in range(3))
    authority = _authority(tmp_path)
    authority.grant(actor_id=owner, notebook_id=notebook, role="owner", operator_id=owner)
    with pytest.raises(ValueError, match="SHA-256"):
        authority.reserve_source_ingestion(
            actor_id=owner, notebook_id=notebook, content_hash="ABC", token=token
        )
    content_hash = hashlib.sha256(b"publication boundary").hexdigest()
    revision = authority.reserve_source_ingestion(
        actor_id=owner, notebook_id=notebook, content_hash=content_hash, token=token
    )
    with (
        pytest.raises(NotFoundError),
        authority.source_ingestion_write_lease(
            actor_id=owner,
            notebook_id=notebook,
            content_hash=content_hash,
            token=uuid4(),
            reserved_revision=revision,
        ),
    ):
        pytest.fail("wrong token cannot publish")
    with (
        pytest.raises(NotFoundError),
        authority.source_ingestion_write_lease(
            actor_id=owner,
            notebook_id=notebook,
            content_hash=content_hash,
            token=token,
            reserved_revision=revision + 1,
        ),
    ):
        pytest.fail("stale or invented ACL revision cannot publish")
    with (
        pytest.raises(DependencyUnavailableError, match="not published"),
        authority.source_ingestion_write_lease(
            actor_id=owner,
            notebook_id=notebook,
            content_hash=content_hash,
            token=token,
            reserved_revision=revision,
        ),
    ):
        pass
    authority.mark_source_ingestion_failed(
        notebook_id=notebook, content_hash=content_hash, token=uuid4()
    )
    assert authority.source_ingestion_state(notebook, content_hash) == "incomplete"
    authority.mark_source_ingestion_failed(
        notebook_id=notebook, content_hash=content_hash, token=token
    )
    assert authority.source_ingestion_state(notebook, content_hash) == "failed"
    assert not authority.permits(owner, notebook)


def test_reconciled_source_intent_can_be_reserved_again_without_reusing_old_token(
    tmp_path: Path,
) -> None:
    authority = _authority(tmp_path)
    owner, notebook, first_token, next_token = (uuid4() for _ in range(4))
    content_hash = hashlib.sha256(b"retryable source").hexdigest()
    authority.grant(actor_id=owner, notebook_id=notebook, role="owner", operator_id=owner)
    first_revision = authority.reserve_source_ingestion(
        actor_id=owner, notebook_id=notebook, content_hash=content_hash, token=first_token
    )
    authority.mark_source_ingestion_failed(
        notebook_id=notebook, content_hash=content_hash, token=first_token
    )
    with authority.source_ingestion_recovery_lease(
        actor_id=owner, notebook_id=notebook, content_hash=content_hash
    ) as (needs_reconciliation, record_reconciled):
        assert needs_reconciliation
        record_reconciled()
    assert authority.source_ingestion_state(notebook, content_hash) == "recoverable"
    with authority.source_ingestion_recovery_lease(
        actor_id=owner, notebook_id=notebook, content_hash=content_hash
    ) as (needs_reconciliation, _):
        assert not needs_reconciliation
    next_revision = authority.reserve_source_ingestion(
        actor_id=owner, notebook_id=notebook, content_hash=content_hash, token=next_token
    )
    assert next_revision > first_revision
    assert not authority.permits(owner, notebook)
    with (
        pytest.raises(NotFoundError),
        authority.source_ingestion_write_lease(
            actor_id=owner,
            notebook_id=notebook,
            content_hash=content_hash,
            token=first_token,
            reserved_revision=first_revision,
        ),
    ):
        pytest.fail("a prior attempt cannot publish after reconciliation and retry")


def test_migration_rolls_back_when_legacy_schema_is_incomplete(tmp_path: Path) -> None:
    path = (tmp_path / "incomplete-acl.db").resolve()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE notebook_grants(actor_id TEXT, notebook_id TEXT, role TEXT, "
            "granted_by TEXT)"
        )
    authority = SQLiteNotebookScopeAuthority(path)
    with pytest.raises(sqlite3.DatabaseError):
        authority.migrate_legacy_grants_unverified()
    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(notebook_grants)")}
        assert "status" not in columns
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)


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
