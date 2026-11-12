"""Principal-first scope and safe denial, using only disposable stores."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from mnemo.interfaces import NotFoundError, PrincipalContextV1
from mnemo.models import Notebook
from mnemo.storage.sqlite import SQLiteStore
from mnemo_server.services.authorized_scope import AuthorizedNotebookScopeResolver
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority


@pytest.mark.anyio
async def test_scope_discovery_and_private_id_denial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SQLiteStore(tmp_path / "notebooks.db")
    await store.open()
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    resolver = AuthorizedNotebookScopeResolver(store, authority)
    alice, bob, private, shared = uuid4(), uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)
    try:
        for notebook_id in (private, shared):
            await store.upsert_notebook(
                Notebook(notebook_id=notebook_id, title="private", created_at=now, updated_at=now)
            )
        authority.grant(actor_id=alice, notebook_id=private, role="owner", operator_id=alice)
        authority.grant(actor_id=alice, notebook_id=shared, role="owner", operator_id=alice)
        authority.grant(actor_id=bob, notebook_id=shared, role="reader", operator_id=alice)
        bob_principal = PrincipalContextV1(bob, True)
        bob_scopes = await resolver.resolve(bob_principal, None)
        assert tuple(scope.notebook_id for scope in bob_scopes) == (shared,)
        await resolver.revalidate(bob_principal, bob_scopes)
        authority.grant(actor_id=uuid4(), notebook_id=shared, role="reader", operator_id=alice)
        with pytest.raises(NotFoundError, match="authorized resource was not found"):
            await resolver.revalidate(bob_principal, bob_scopes)
        fresh_scopes = await resolver.resolve(bob_principal, None)
        await resolver.revalidate(bob_principal, fresh_scopes)
        monkeypatch.setattr(authority, "revision", lambda _notebook_id: None)
        with pytest.raises(NotFoundError, match="authorized resource was not found"):
            await resolver.revalidate(bob_principal, fresh_scopes)
        monkeypatch.undo()
        for hidden in (private, uuid4()):
            with pytest.raises(NotFoundError, match="authorized resource was not found"):
                await resolver.resolve(bob_principal, (hidden,))
        with pytest.raises(PermissionError):
            await resolver.resolve(PrincipalContextV1(bob, False), None)
        assert (await resolver.resolve(PrincipalContextV1(alice, True), (private,)))[
            0
        ].membership_revision == 1
        authority.revoke(actor_id=bob, notebook_id=shared)
        assert await resolver.resolve(bob_principal, None) == ()
    finally:
        await store.close()
