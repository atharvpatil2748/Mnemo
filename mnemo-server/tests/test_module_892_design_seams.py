"""Disposable feasibility checks for the approved 8.9.2 authority design.

These tests do not install membership authority or cursors in production.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from mnemo.cursors import (
    CursorCodecV2,
    CursorConflictError,
    CursorExpiredError,
    CursorInvalidError,
    CursorSigningKeyV2,
)
from mnemo_server.services.authorization import principal_from_claims
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority


def test_explicit_owner_and_reader_grants_are_isolated_and_retired(tmp_path: Path) -> None:
    authority = SQLiteNotebookScopeAuthority((tmp_path / "isolated-acl.db").resolve())
    authority.initialize()
    owner, reader, stranger, notebook, unrelated = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    assert not authority.permits(owner, notebook)
    authority.grant(actor_id=owner, notebook_id=notebook, role="owner", operator_id=owner)
    authority.grant(actor_id=reader, notebook_id=notebook, role="reader", operator_id=owner)
    assert authority.permits(owner, notebook)
    assert authority.permits(reader, notebook)
    assert not authority.permits(stranger, notebook)
    assert not authority.permits(reader, unrelated)
    authority.retire_notebook(notebook, operator_id=owner)
    assert not authority.permits(owner, notebook)
    assert not authority.permits(reader, notebook)


def test_existing_codec_can_reject_a_changed_membership_binding() -> None:
    now = datetime(2026, 10, 21, tzinfo=UTC)
    codec = CursorCodecV2(CursorSigningKeyV2("fixture", b"f" * 32), ttl=timedelta(minutes=5))
    actor = principal_from_claims({"sub": "fixture-actor"})
    other = principal_from_claims({"sub": "other-actor"})
    notebook = str(uuid4())
    binding = {
        "actor": str(actor.actor_id),
        "notebook": notebook,
        "membership_revision": 3,
        "policy": "fixture-policy-1",
        "alias": "fixture-alias",
        "representation": "canonical_text",
        "query": "fixture-query",
    }
    token = codec.encode(
        domain="fixture-only-membership",
        snapshot_identity="a" * 64,
        binding=binding,
        position={"offset": 1},
        limits={"page_size": 5},
        now=now,
    )

    def decode(expected: dict[str, object], *, at: datetime = now) -> None:
        codec.decode(
            token,
            expected_domain="fixture-only-membership",
            expected_binding=expected,
            expected_snapshot_identity="a" * 64,
            expected_limits={"page_size": 5},
            now=at,
        )

    decode(binding)
    for change in (
        {"actor": str(other.actor_id)},
        {"membership_revision": 4},
        {"policy": "fixture-policy-2"},
        {"alias": "other-alias"},
        {"representation": "vision_analysis"},
        {"query": "other-query"},
    ):
        with pytest.raises(CursorConflictError):
            decode(binding | change)
    with pytest.raises(CursorInvalidError):
        codec.decode(
            token + "x",
            expected_domain="fixture-only-membership",
            expected_binding=binding,
            now=now,
        )
    with pytest.raises(CursorExpiredError):
        decode(binding, at=now + timedelta(minutes=5))


def test_cursor_binding_rejects_actual_acl_revision_after_revocation(tmp_path: Path) -> None:
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    owner, reader, notebook = uuid4(), uuid4(), uuid4()
    authority.grant(actor_id=owner, notebook_id=notebook, role="owner", operator_id=owner)
    authority.grant(actor_id=reader, notebook_id=notebook, role="reader", operator_id=owner)
    codec = CursorCodecV2(CursorSigningKeyV2("fixture", b"f" * 32), ttl=timedelta(minutes=5))
    now = datetime(2026, 10, 21, tzinfo=UTC)
    binding = {
        "actor": str(reader),
        "notebook": str(notebook),
        "membership_revision": authority.revision(notebook),
    }
    token = codec.encode(
        domain="fixture-only-membership",
        snapshot_identity="a" * 64,
        binding=binding,
        position={"offset": 1},
        limits={"page_size": 5},
        now=now,
    )
    authority.revoke(actor_id=reader, notebook_id=notebook)
    assert not authority.permits(reader, notebook)
    with pytest.raises(CursorConflictError):
        codec.decode(
            token,
            expected_domain="fixture-only-membership",
            expected_binding=binding | {"membership_revision": authority.revision(notebook)},
            expected_snapshot_identity="a" * 64,
            expected_limits={"page_size": 5},
            now=now,
        )
