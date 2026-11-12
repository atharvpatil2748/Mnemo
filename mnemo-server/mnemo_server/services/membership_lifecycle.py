"""Opt-in two-store notebook lifecycle for isolated membership testing.

No cross-store transaction is claimed. A pending create has no grant; delete
retires authority before touching notebook storage. This is not installed in
the current production routes.
"""

from __future__ import annotations

import sqlite3
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from mnemo.models import FrozenMetadata, Notebook

from .scope_authority import SQLiteNotebookScopeAuthority


class NotebookLifecycleStore(Protocol):
    async def get_notebook(self, notebook_id: UUID) -> Notebook | None: ...

    async def insert_notebook_if_absent(self, notebook: Notebook) -> None: ...

    async def delete_notebook(self, notebook_id: UUID) -> bool: ...


class MembershipNotebookLifecycle:
    def __init__(self, store: NotebookLifecycleStore, authority: SQLiteNotebookScopeAuthority):
        self.store = store
        self.authority = authority

    async def create(
        self,
        *,
        title: str,
        actor_id: UUID,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Notebook:
        """Create with a server-generated ID; return only after owner activation."""
        now = datetime.now(UTC)
        notebook = Notebook(
            notebook_id=uuid4(),
            title=title,
            description=description,
            created_at=now,
            updated_at=now,
            metadata=FrozenMetadata(metadata or {}),
        )
        if await self.store.get_notebook(notebook.notebook_id) is not None:
            raise ValueError("notebook identity is not fresh")
        token = uuid4()
        self.authority.reserve_create(
            notebook_id=notebook.notebook_id, actor_id=actor_id, token=token, notebook=notebook
        )
        await self.store.insert_notebook_if_absent(notebook)
        await self.recover_create(notebook, actor_id, token)
        return notebook

    async def recover_create(self, notebook: Notebook, actor_id: UUID, token: UUID) -> None:
        """Explicit retry with durable intent and exact stored record evidence."""
        identity = (actor_id, token)
        pending = self.authority.pending_create(notebook.notebook_id) == identity
        completed = self.authority.completed_create(notebook.notebook_id) == identity
        if not pending and not completed:
            raise ValueError("notebook creation intent is unavailable or mismatched")
        record = self.authority.pending_create_record(notebook.notebook_id)
        if record is not None and (
            record[0] != actor_id
            or record[1] != token
            or not self._same_notebook(record[2], notebook)
        ):
            raise ValueError("notebook payload does not match durable creation intent")
        if completed and not self.authority.permits(
            actor_id, notebook.notebook_id, operation="write"
        ):
            raise ValueError("completed notebook owner is no longer active")
        existing = await self.store.get_notebook(notebook.notebook_id)
        if existing is None or not self._same_notebook(existing, notebook):
            raise ValueError("notebook storage does not match creation intent")
        if pending:
            self.authority.finish_create(
                notebook_id=notebook.notebook_id, actor_id=actor_id, token=token
            )

    @staticmethod
    def _same_notebook(left: Notebook, right: Notebook) -> bool:
        return (
            left.notebook_id,
            left.title,
            left.description,
            left.created_at,
            left.updated_at,
            left.metadata,
        ) == (
            right.notebook_id,
            right.title,
            right.description,
            right.created_at,
            right.updated_at,
            right.metadata,
        )

    async def recover_pending_create(self, notebook_id: UUID, actor_id: UUID) -> Notebook:
        """Resume a journaled create after restart; incomplete intents remain quarantined."""
        record = self.authority.pending_create_record(notebook_id)
        if record is None:
            completed = self.authority.completed_create(notebook_id)
            existing = await self.store.get_notebook(notebook_id)
            if (
                completed is not None
                and completed[0] == actor_id
                and existing is not None
                and self.authority.permits(actor_id, notebook_id, operation="write")
            ):
                return existing
            raise ValueError("complete notebook creation intent is unavailable")
        if record[0] != actor_id:
            raise ValueError("complete notebook creation intent is unavailable")
        _, token, notebook = record
        existing = await self.store.get_notebook(notebook_id)
        if existing is None:
            # A concurrent worker may have inserted the same record.
            with suppress(sqlite3.IntegrityError):
                await self.store.insert_notebook_if_absent(notebook)
        await self.recover_create(notebook, actor_id, token)
        return notebook

    async def delete(self, notebook_id: UUID, *, actor_id: UUID | None = None) -> None:
        """Tombstone before deletion; first use requires the trusted owner.

        Actor-less retry is allowed only after the ACL tombstone has committed.
        This does not make the notebook and ACL stores atomic.
        """
        self.authority.retire_notebook(notebook_id, operator_id=actor_id)
        await self.store.delete_notebook(notebook_id)
