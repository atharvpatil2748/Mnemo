"""Server-only grant operations backed by authenticated actor identity.

No public endpoint is registered here. A signed, deployment-pinned token is
required for each operation; a caller-supplied actor ID is never the operator.
"""

from __future__ import annotations

from uuid import UUID

from mnemo.interfaces import NotFoundError
from mnemo.models import Notebook

from .membership_lifecycle import MembershipNotebookLifecycle, NotebookLifecycleStore
from .scope_authority import SQLiteNotebookScopeAuthority
from .trusted_actor import TrustedJWTActorMapper


class MembershipOperatorService:
    def __init__(
        self,
        store: NotebookLifecycleStore,
        authority: SQLiteNotebookScopeAuthority,
        actors: TrustedJWTActorMapper,
    ) -> None:
        self._store = store
        self._authority = authority
        self._actors = actors

    async def _require_owner(self, token: str, notebook_id: UUID) -> UUID:
        operator = self._actors.from_token(token).actor_id
        if self._authority.active_role(operator, notebook_id) != "owner":
            raise NotFoundError("authorized resource was not found")
        if await self._store.get_notebook(notebook_id) is None:
            raise NotFoundError("authorized resource was not found")
        return operator

    async def grant_reader(self, *, token: str, notebook_id: UUID, reader_id: UUID) -> None:
        operator = await self._require_owner(token, notebook_id)
        if reader_id == operator:
            raise ValueError("owner cannot grant a second role to self")
        self._authority.grant_reader_as_owner(
            reader_id=reader_id, notebook_id=notebook_id, operator_id=operator
        )

    async def revoke_reader(self, *, token: str, notebook_id: UUID, reader_id: UUID) -> None:
        operator = await self._require_owner(token, notebook_id)
        self._authority.revoke_reader_as_owner(
            operator_id=operator, notebook_id=notebook_id, reader_id=reader_id
        )

    async def recover_own_create(self, *, token: str, notebook: Notebook, intent: UUID) -> None:
        operator = self._actors.from_token(token).actor_id
        identity = (operator, intent)
        if self._authority.pending_create(notebook.notebook_id) != identity and (
            self._authority.completed_create(notebook.notebook_id) != identity
        ):
            raise NotFoundError("authorized resource was not found")
        await MembershipNotebookLifecycle(self._store, self._authority).recover_create(
            notebook, operator, intent
        )

    async def recover_own_pending_create(self, *, token: str, notebook_id: UUID) -> Notebook:
        """Resume only an intent whose durable actor matches the authenticated actor."""
        operator = self._actors.from_token(token).actor_id
        record = self._authority.pending_create_record(notebook_id)
        if record is None or record[0] != operator:
            raise NotFoundError("authorized resource was not found")
        return await MembershipNotebookLifecycle(
            self._store, self._authority
        ).recover_pending_create(notebook_id, operator)
