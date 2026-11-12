"""Disposable two-store crash windows; never use an operational notebook."""

import asyncio
import multiprocessing
import os
import sqlite3
import time
from datetime import UTC, datetime
from multiprocessing.process import BaseProcess
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from mnemo.models import Notebook
from mnemo.storage.sqlite import SQLiteStore
from mnemo_server.services.membership_lifecycle import MembershipNotebookLifecycle
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority


def _notebook() -> Notebook:
    now = datetime.now(UTC)
    return Notebook(notebook_id=uuid4(), title="fixture", created_at=now, updated_at=now)


def _open_new_store_in_process(store_path: str, ready_path: str, start_path: str) -> None:
    """Synchronize disposable first-open attempts across separate processes."""
    Path(ready_path).touch()
    deadline = time.monotonic() + 20
    while not Path(start_path).exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("first-open test barrier was not released")
        time.sleep(0.01)

    async def open_store() -> None:
        store = SQLiteStore(Path(store_path))
        await store.open()
        await store.close()

    asyncio.run(open_store())


def test_disposable_store_first_open_is_safe_across_processes(tmp_path: Path) -> None:
    store_path = (tmp_path / "first-open.db").resolve()
    start_path = (tmp_path / "start").resolve()
    context = multiprocessing.get_context("spawn")
    children = [
        context.Process(
            target=_open_new_store_in_process,
            args=(str(store_path), str(tmp_path / f"ready-{index}"), str(start_path)),
        )
        for index in range(2)
    ]
    for child in children:
        child.start()
    deadline = time.monotonic() + 20
    while not all((tmp_path / f"ready-{index}").exists() for index in range(2)):
        if time.monotonic() >= deadline:
            raise TimeoutError("first-open workers did not reach the barrier")
        time.sleep(0.01)
    start_path.touch()
    for child in children:
        _join_disposable_process(child, 0)
    with sqlite3.connect(store_path) as db:
        assert db.execute("SELECT MAX(version) FROM schema_versions").fetchone() == (17,)
        assert db.execute("SELECT name FROM sqlite_master WHERE name='notebooks'").fetchone()


def _grant_in_process(path: str, actor_id: UUID, notebook_id: UUID, operator_id: UUID) -> None:
    SQLiteNotebookScopeAuthority(Path(path)).grant(
        actor_id=actor_id, notebook_id=notebook_id, role="reader", operator_id=operator_id
    )


def _revoke_in_process(path: str, actor_id: UUID, notebook_id: UUID) -> None:
    SQLiteNotebookScopeAuthority(Path(path)).revoke(actor_id=actor_id, notebook_id=notebook_id)


def _revoke_after_ready_in_process(
    path: str, actor_id: UUID, notebook_id: UUID, ready_path: str
) -> None:
    Path(ready_path).touch()
    _revoke_in_process(path, actor_id, notebook_id)


def _recover_in_process(
    acl_path: str, store_path: str, notebook: Notebook, actor_id: UUID, token: UUID
) -> None:
    async def recover() -> None:
        store = SQLiteStore(Path(store_path))
        await store.open()
        try:
            await MembershipNotebookLifecycle(
                store, SQLiteNotebookScopeAuthority(Path(acl_path))
            ).recover_create(notebook, actor_id, token)
        finally:
            await store.close()

    asyncio.run(recover())


def _recover_from_journal_in_process(
    acl_path: str, store_path: str, notebook_id: UUID, actor_id: UUID
) -> None:
    async def recover() -> None:
        store = SQLiteStore(Path(store_path))
        await store.open()
        try:
            await MembershipNotebookLifecycle(
                store, SQLiteNotebookScopeAuthority(Path(acl_path))
            ).recover_pending_create(notebook_id, actor_id)
        finally:
            await store.close()

    asyncio.run(recover())


def _store_insert_then_exit(store_path: str, notebook: Notebook) -> None:
    async def insert() -> None:
        store = SQLiteStore(Path(store_path))
        await store.open()
        try:
            await store.insert_notebook_if_absent(notebook)
        finally:
            await store.close()

    asyncio.run(insert())
    os._exit(23)  # Only a disposable child: simulate interruption after its store commit.


def _tombstone_then_exit(acl_path: str, notebook_id: UUID, owner_id: UUID) -> None:
    SQLiteNotebookScopeAuthority(Path(acl_path)).retire_notebook(notebook_id, operator_id=owner_id)
    os._exit(24)  # Disposable child: interrupt before notebook-store deletion.


def _retry_delete_in_process(acl_path: str, store_path: str, notebook_id: UUID) -> None:
    async def retry() -> None:
        store = SQLiteStore(Path(store_path))
        await store.open()
        try:
            await MembershipNotebookLifecycle(
                store, SQLiteNotebookScopeAuthority(Path(acl_path))
            ).delete(notebook_id)
        finally:
            await store.close()

    asyncio.run(retry())


def _join_disposable_process(process: BaseProcess, expected: int) -> None:
    process.join(timeout=30)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
        pytest.fail("disposable lifecycle child did not exit")
    assert process.exitcode == expected


@pytest.mark.anyio
async def test_create_crash_retry_and_retire_first(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "notebooks.db")
    await store.open()
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    lifecycle = MembershipNotebookLifecycle(store, authority)
    owner, notebook = uuid4(), _notebook()
    try:
        token = uuid4()
        authority.reserve_create(notebook_id=notebook.notebook_id, actor_id=owner, token=token)
        assert not authority.permits(owner, notebook.notebook_id)
        await store.upsert_notebook(notebook)  # simulate crash before ACL activation
        assert not authority.permits(owner, notebook.notebook_id)
        await lifecycle.recover_create(notebook, owner, token)
        assert authority.permits(owner, notebook.notebook_id, operation="write")
        await lifecycle.recover_create(notebook, owner, token)
        assert authority.revision(notebook.notebook_id) == 1
        await lifecycle.delete(notebook.notebook_id, actor_id=owner)
        assert not authority.permits(owner, notebook.notebook_id)
        assert await store.get_notebook(notebook.notebook_id) is None
        await lifecycle.delete(notebook.notebook_id)
        assert authority.revision(notebook.notebook_id) == 2
        with pytest.raises(ValueError, match="not fresh"):
            authority.reserve_create(
                notebook_id=notebook.notebook_id, actor_id=owner, token=uuid4()
            )
    finally:
        await store.close()


@pytest.mark.anyio
async def test_inconsistent_stores_and_wrong_actor_cannot_recover(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "notebooks.db")
    await store.open()
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    lifecycle = MembershipNotebookLifecycle(store, authority)
    owner, notebook, token = uuid4(), _notebook(), uuid4()
    try:
        authority.reserve_create(notebook_id=notebook.notebook_id, actor_id=owner, token=token)
        with pytest.raises(ValueError, match="storage"):
            await lifecycle.recover_create(notebook, owner, token)
        await store.upsert_notebook(notebook)
        with pytest.raises(ValueError, match="intent"):
            await lifecycle.recover_create(notebook, uuid4(), token)
        assert not authority.permits(owner, notebook.notebook_id)
        await lifecycle.recover_create(notebook, owner, token)
        assert authority.permits(owner, notebook.notebook_id)
    finally:
        await store.close()


@pytest.mark.anyio
async def test_interrupted_delete_tombstones_before_storage_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SQLiteStore(tmp_path / "notebooks.db")
    await store.open()
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    lifecycle = MembershipNotebookLifecycle(store, authority)
    owner = uuid4()
    try:
        notebook = await lifecycle.create(title="fixture", actor_id=owner)
        assert authority.permits(owner, notebook.notebook_id)
        original_delete = store.delete_notebook
        monkeypatch.setattr(
            store, "delete_notebook", AsyncMock(side_effect=RuntimeError("interrupted"))
        )
        with pytest.raises(RuntimeError, match="interrupted"):
            await lifecycle.delete(notebook.notebook_id, actor_id=owner)
        assert await store.get_notebook(notebook.notebook_id) is not None
        assert not authority.permits(owner, notebook.notebook_id)
        monkeypatch.setattr(store, "delete_notebook", original_delete)
        await lifecycle.delete(notebook.notebook_id)
        assert await store.get_notebook(notebook.notebook_id) is None
        assert not authority.permits(owner, notebook.notebook_id)
    finally:
        await store.close()


@pytest.mark.anyio
async def test_concurrent_create_and_storage_collision_fail_closed(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "notebooks.db")
    await store.open()
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    lifecycle = MembershipNotebookLifecycle(store, authority)
    owner = uuid4()
    try:
        notebooks = await asyncio.gather(
            *(lifecycle.create(title=f"fixture-{index}", actor_id=owner) for index in range(8))
        )
        assert len({item.notebook_id for item in notebooks}) == 8
        assert all(authority.permits(owner, item.notebook_id) for item in notebooks)
        collision = notebooks[0]
        with pytest.raises(sqlite3.IntegrityError):
            await store.insert_notebook_if_absent(collision)
        assert await store.get_notebook(collision.notebook_id) is not None
        assert authority.permits(owner, collision.notebook_id)
    finally:
        await store.close()


@pytest.mark.anyio
async def test_concurrent_delete_and_retry_keep_tombstone(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "notebooks.db")
    await store.open()
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    owner = uuid4()
    try:
        notebook = await MembershipNotebookLifecycle(store, authority).create(
            title="fixture", actor_id=owner
        )
        await MembershipNotebookLifecycle(store, authority).delete(
            notebook.notebook_id, actor_id=owner
        )
        await asyncio.gather(
            *(
                MembershipNotebookLifecycle(store, authority).delete(notebook.notebook_id)
                for _ in range(4)
            )
        )
        assert await store.get_notebook(notebook.notebook_id) is None
        assert not authority.permits(owner, notebook.notebook_id)
        assert authority.revision(notebook.notebook_id) == 2
        await MembershipNotebookLifecycle(store, authority).delete(notebook.notebook_id)
        assert authority.revision(notebook.notebook_id) == 2
    finally:
        await store.close()


@pytest.mark.anyio
async def test_create_activation_interruption_and_concurrent_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SQLiteStore(tmp_path / "notebooks.db")
    await store.open()
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    lifecycle = MembershipNotebookLifecycle(store, authority)
    owner, notebook, token = uuid4(), _notebook(), uuid4()
    try:
        authority.reserve_create(notebook_id=notebook.notebook_id, actor_id=owner, token=token)
        await store.insert_notebook_if_absent(notebook)
        original_finish = authority.finish_create

        def interrupt_activation(**_kwargs: object) -> None:
            raise RuntimeError("activation interrupted")

        monkeypatch.setattr(authority, "finish_create", interrupt_activation)
        with pytest.raises(RuntimeError, match="activation interrupted"):
            await lifecycle.recover_create(notebook, owner, token)
        assert not authority.permits(owner, notebook.notebook_id)
        monkeypatch.setattr(authority, "finish_create", original_finish)
        await asyncio.gather(*(lifecycle.recover_create(notebook, owner, token) for _ in range(4)))
        assert authority.permits(owner, notebook.notebook_id, operation="write")
        assert authority.revision(notebook.notebook_id) == 1
    finally:
        await store.close()


@pytest.mark.anyio
async def test_unavailable_notebook_store_after_tombstone_recovers_by_retry(
    tmp_path: Path,
) -> None:
    path = tmp_path / "notebooks.db"
    store = SQLiteStore(path)
    await store.open()
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    lifecycle = MembershipNotebookLifecycle(store, authority)
    owner = uuid4()
    notebook = await lifecycle.create(title="fixture", actor_id=owner)
    await store.close()
    with pytest.raises(RuntimeError):
        await lifecycle.delete(notebook.notebook_id, actor_id=owner)
    assert not authority.permits(owner, notebook.notebook_id)
    await store.open()
    try:
        await lifecycle.delete(notebook.notebook_id)
        assert await store.get_notebook(notebook.notebook_id) is None
        assert authority.revision(notebook.notebook_id) == 2
    finally:
        await store.close()


def test_separate_process_grants_serialize_acl_revisions(tmp_path: Path) -> None:
    acl_path = (tmp_path / "acl.db").resolve()
    authority = SQLiteNotebookScopeAuthority(acl_path)
    authority.initialize()
    owner, notebook_id = uuid4(), uuid4()
    authority.grant(actor_id=owner, notebook_id=notebook_id, role="owner", operator_id=owner)
    actors = [uuid4() for _ in range(3)]
    context = multiprocessing.get_context("spawn")
    children = [
        context.Process(target=_grant_in_process, args=(str(acl_path), actor, notebook_id, owner))
        for actor in actors
    ]
    for child in children:
        child.start()
    for child in children:
        _join_disposable_process(child, 0)
    assert authority.revision(notebook_id) == 4
    assert all(authority.permits(actor, notebook_id) for actor in actors)
    replacements = [uuid4() for _ in range(3)]
    churn = [
        context.Process(target=_revoke_in_process, args=(str(acl_path), actor, notebook_id))
        for actor in actors
    ] + [
        context.Process(target=_grant_in_process, args=(str(acl_path), actor, notebook_id, owner))
        for actor in replacements
    ]
    for child in churn:
        child.start()
    for child in churn:
        _join_disposable_process(child, 0)
    assert authority.revision(notebook_id) == 10
    assert all(not authority.permits(actor, notebook_id) for actor in actors)
    assert all(authority.permits(actor, notebook_id) for actor in replacements)


def test_owner_write_lease_serializes_cross_process_revocation(tmp_path: Path) -> None:
    acl_path = (tmp_path / "acl.db").resolve()
    authority = SQLiteNotebookScopeAuthority(acl_path)
    authority.initialize()
    owner, notebook_id = uuid4(), uuid4()
    authority.grant(actor_id=owner, notebook_id=notebook_id, role="owner", operator_id=owner)
    ready_path = tmp_path / "revoke-ready"
    context = multiprocessing.get_context("spawn")
    child = context.Process(
        target=_revoke_after_ready_in_process,
        args=(str(acl_path), owner, notebook_id, str(ready_path)),
    )
    with authority.owner_write_lease(actor_id=owner, notebook_id=notebook_id):
        child.start()
        deadline = time.monotonic() + 20
        while not ready_path.exists():
            if time.monotonic() >= deadline:
                pytest.fail("revoke worker did not reach the ACL boundary")
            time.sleep(0.01)
        time.sleep(0.05)
        assert child.is_alive()
        assert authority.permits(owner, notebook_id)
    _join_disposable_process(child, 0)
    assert not authority.permits(owner, notebook_id)


@pytest.mark.anyio
async def test_separate_process_crash_and_simultaneous_create_recovery(tmp_path: Path) -> None:
    acl_path = (tmp_path / "acl.db").resolve()
    store_path = (tmp_path / "notebooks.db").resolve()
    authority = SQLiteNotebookScopeAuthority(acl_path)
    authority.initialize()
    owner, notebook, token = uuid4(), _notebook(), uuid4()
    authority.reserve_create(notebook_id=notebook.notebook_id, actor_id=owner, token=token)
    context = multiprocessing.get_context("spawn")
    crashed = context.Process(target=_store_insert_then_exit, args=(str(store_path), notebook))
    crashed.start()
    _join_disposable_process(crashed, 23)
    assert not authority.permits(owner, notebook.notebook_id)
    assert authority.pending_create(notebook.notebook_id) == (owner, token)
    children = [
        context.Process(
            target=_recover_in_process,
            args=(str(acl_path), str(store_path), notebook, owner, token),
        )
        for _ in range(2)
    ]
    for child in children:
        child.start()
    for child in children:
        _join_disposable_process(child, 0)
    assert authority.permits(owner, notebook.notebook_id, operation="write")
    assert authority.revision(notebook.notebook_id) == 1
    store = SQLiteStore(store_path)
    await store.open()
    try:
        await MembershipNotebookLifecycle(store, authority).delete(
            notebook.notebook_id, actor_id=owner
        )
        assert not authority.permits(owner, notebook.notebook_id)
        assert authority.revision(notebook.notebook_id) == 2
        assert await store.get_notebook(notebook.notebook_id) is None
    finally:
        await store.close()


@pytest.mark.anyio
async def test_separate_process_delete_crash_and_simultaneous_retry(tmp_path: Path) -> None:
    acl_path = (tmp_path / "acl.db").resolve()
    store_path = (tmp_path / "notebooks.db").resolve()
    authority = SQLiteNotebookScopeAuthority(acl_path)
    authority.initialize()
    store = SQLiteStore(store_path)
    await store.open()
    owner = uuid4()
    try:
        notebook = await MembershipNotebookLifecycle(store, authority).create(
            title="fixture", actor_id=owner
        )
        assert authority.permits(owner, notebook.notebook_id)
    finally:
        await store.close()
    context = multiprocessing.get_context("spawn")
    crashed = context.Process(
        target=_tombstone_then_exit, args=(str(acl_path), notebook.notebook_id, owner)
    )
    crashed.start()
    _join_disposable_process(crashed, 24)
    assert not authority.permits(owner, notebook.notebook_id)
    assert authority.revision(notebook.notebook_id) == 2
    readers = [
        context.Process(
            target=_retry_delete_in_process,
            args=(str(acl_path), str(store_path), notebook.notebook_id),
        )
        for _ in range(2)
    ]
    for reader in readers:
        reader.start()
    for reader in readers:
        _join_disposable_process(reader, 0)
    assert authority.revision(notebook.notebook_id) == 2
    assert not authority.permits(owner, notebook.notebook_id)
    check = SQLiteStore(store_path)
    await check.open()
    try:
        assert await check.get_notebook(notebook.notebook_id) is None
    finally:
        await check.close()


@pytest.mark.anyio
async def test_durable_create_intent_recovers_after_restart_without_caller_payload(
    tmp_path: Path,
) -> None:
    acl_path = (tmp_path / "acl.db").resolve()
    store_path = (tmp_path / "notebooks.db").resolve()
    authority = SQLiteNotebookScopeAuthority(acl_path)
    authority.initialize()
    owner, notebook, token = uuid4(), _notebook(), uuid4()
    authority.reserve_create(
        notebook_id=notebook.notebook_id, actor_id=owner, token=token, notebook=notebook
    )
    assert not authority.permits(owner, notebook.notebook_id)
    initial_store = SQLiteStore(store_path)
    await initial_store.open()
    await initial_store.close()
    context = multiprocessing.get_context("spawn")
    children = [
        context.Process(
            target=_recover_from_journal_in_process,
            args=(str(acl_path), str(store_path), notebook.notebook_id, owner),
        )
        for _ in range(2)
    ]
    for child in children:
        child.start()
    for child in children:
        _join_disposable_process(child, 0)
    assert authority.revision(notebook.notebook_id) == 1
    assert authority.permits(owner, notebook.notebook_id, operation="write")
    store = SQLiteStore(store_path)
    await store.open()
    try:
        assert await store.get_notebook(notebook.notebook_id) == notebook
    finally:
        await store.close()


@pytest.mark.anyio
async def test_incomplete_or_mismatched_create_journal_stays_quarantined(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "notebooks.db")
    await store.open()
    authority = SQLiteNotebookScopeAuthority((tmp_path / "acl.db").resolve())
    authority.initialize()
    owner, notebook, token = uuid4(), _notebook(), uuid4()
    lifecycle = MembershipNotebookLifecycle(store, authority)
    try:
        authority.reserve_create(notebook_id=notebook.notebook_id, actor_id=owner, token=token)
        with pytest.raises(ValueError, match="complete notebook creation intent"):
            await lifecycle.recover_pending_create(notebook.notebook_id, owner)
        assert not authority.permits(owner, notebook.notebook_id)
        second = _notebook()
        authority.reserve_create(
            notebook_id=second.notebook_id, actor_id=owner, token=uuid4(), notebook=second
        )
        with pytest.raises(ValueError, match="complete notebook creation intent"):
            await lifecycle.recover_pending_create(second.notebook_id, uuid4())
        await store.upsert_notebook(
            Notebook(
                notebook_id=second.notebook_id,
                title="conflicting",
                created_at=second.created_at,
                updated_at=second.updated_at,
            )
        )
        with pytest.raises(ValueError, match="storage does not match"):
            await lifecycle.recover_pending_create(second.notebook_id, owner)
        assert not authority.permits(owner, second.notebook_id)
    finally:
        await store.close()
