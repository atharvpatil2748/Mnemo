"""Principal-first notebook resolution for the approved disposable ACL model."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from mnemo.cursors import CursorCodecV2, CursorInvalidError, CursorSigningKeyV2
from mnemo.interfaces import NotFoundError, PrincipalContextV1
from mnemo.models import Notebook

from .scope_authority import SQLiteNotebookScopeAuthority


class NotebookReader(Protocol):
    async def get_notebook(self, notebook_id: UUID) -> Notebook | None: ...


@dataclass(frozen=True, slots=True)
class AuthorizedNotebookScope:
    notebook_id: UUID
    membership_revision: int


class AuthorizedNotebookScopeResolver:
    def __init__(self, reader: NotebookReader, authority: SQLiteNotebookScopeAuthority) -> None:
        self.reader = reader
        self.authority = authority

    async def resolve(
        self, principal: PrincipalContextV1, selected: tuple[UUID, ...] | None
    ) -> tuple[AuthorizedNotebookScope, ...]:
        """Authorize every selected ID before any notebook storage disclosure."""
        if not principal.authenticated:
            raise PermissionError("authenticated principal is required")
        notebook_ids = (
            self.authority.authorized_notebook_ids(principal.actor_id)
            if selected is None
            else selected
        )
        if len(notebook_ids) > 100 or len(set(notebook_ids)) != len(notebook_ids):
            raise ValueError("invalid notebook selection")
        for notebook_id in notebook_ids:
            if not self.authority.permits(principal.actor_id, notebook_id):
                raise NotFoundError("authorized resource was not found")
        resolved = []
        for notebook_id in notebook_ids:
            revision = self.authority.revision(notebook_id)
            if revision is None or await self.reader.get_notebook(notebook_id) is None:
                raise NotFoundError("authorized resource was not found")
            # Recheck after the store read; a concurrent revoke must deny.
            if not self.authority.permits(principal.actor_id, notebook_id):
                raise NotFoundError("authorized resource was not found")
            current_revision = self.authority.revision(notebook_id)
            if current_revision != revision:
                raise NotFoundError("authorized resource was not found")
            resolved.append(AuthorizedNotebookScope(notebook_id, revision))
        return tuple(resolved)

    async def revalidate(
        self, principal: PrincipalContextV1, scopes: tuple[AuthorizedNotebookScope, ...]
    ) -> None:
        """Refuse a response if a selected membership changed during its work."""
        if not principal.authenticated:
            raise PermissionError("authenticated principal is required")
        for scope in scopes:
            if not self.authority.permits(principal.actor_id, scope.notebook_id):
                raise NotFoundError("authorized resource was not found")
            if self.authority.revision(scope.notebook_id) != scope.membership_revision:
                raise NotFoundError("authorized resource was not found")
            if await self.reader.get_notebook(scope.notebook_id) is None:
                raise NotFoundError("authorized resource was not found")
            if not self.authority.permits(principal.actor_id, scope.notebook_id):
                raise NotFoundError("authorized resource was not found")
            if self.authority.revision(scope.notebook_id) != scope.membership_revision:
                raise NotFoundError("authorized resource was not found")


class AuthorizedNotebookPageCursor:
    """Signed metadata keyset cursor bound to the current ACL decision."""

    def __init__(self, secret: bytes) -> None:
        self._codec = CursorCodecV2(CursorSigningKeyV2("membership-page-v1", secret))

    @staticmethod
    def _context(
        domain: str,
        principal: PrincipalContextV1,
        scope: AuthorizedNotebookScope,
        selector: str | None,
    ) -> tuple[str, dict[str, object]]:
        binding: dict[str, object] = {
            "actor_id": str(principal.actor_id),
            "notebook_id": str(scope.notebook_id),
            "acl_revision": scope.membership_revision,
            "selector": selector,
        }
        snapshot = hashlib.sha256(
            f"{domain}:{scope.notebook_id}:{scope.membership_revision}".encode()
        ).hexdigest()
        return snapshot, binding

    def encode(
        self,
        position: str,
        *,
        domain: str,
        principal: PrincipalContextV1,
        scope: AuthorizedNotebookScope,
        limit: int,
        selector: str | None = None,
    ) -> str:
        snapshot, binding = self._context(domain, principal, scope, selector)
        return self._codec.encode(
            domain=domain,
            snapshot_identity=snapshot,
            binding=binding,
            position={"key": str(UUID(position))},
            limits={"limit": limit},
        )

    def decode(
        self,
        token: str,
        *,
        domain: str,
        principal: PrincipalContextV1,
        scope: AuthorizedNotebookScope,
        limit: int,
        selector: str | None = None,
    ) -> str:
        snapshot, binding = self._context(domain, principal, scope, selector)
        state = self._codec.decode(
            token,
            expected_domain=domain,
            expected_snapshot_identity=snapshot,
            expected_binding=binding,
            expected_limits={"limit": limit},
        )
        key = state.position.get("key")
        if len(state.position) != 1 or not isinstance(key, str):
            raise CursorInvalidError("cursor position is invalid")
        try:
            return str(UUID(key))
        except ValueError as error:
            raise CursorInvalidError("cursor position is invalid") from error


class AuthorizedNotebookInventoryCursor:
    """Bind notebook discovery pagination to the entire current ACL inventory."""

    def __init__(self, secret: bytes) -> None:
        self._codec = CursorCodecV2(CursorSigningKeyV2("membership-inventory-v1", secret))

    @staticmethod
    def _context(
        principal: PrincipalContextV1, scopes: tuple[AuthorizedNotebookScope, ...]
    ) -> tuple[str, dict[str, object]]:
        inventory = sorted((str(item.notebook_id), item.membership_revision) for item in scopes)
        snapshot = hashlib.sha256(json.dumps(inventory, separators=(",", ":")).encode()).hexdigest()
        return snapshot, {"actor_id": str(principal.actor_id), "inventory": inventory}

    def encode(
        self,
        position: str,
        *,
        principal: PrincipalContextV1,
        scopes: tuple[AuthorizedNotebookScope, ...],
        limit: int,
    ) -> str:
        snapshot, binding = self._context(principal, scopes)
        return self._codec.encode(
            domain="mnemo-notebook-inventory/v1",
            snapshot_identity=snapshot,
            binding=binding,
            position={"key": str(UUID(position))},
            limits={"limit": limit},
        )

    def decode(
        self,
        token: str,
        *,
        principal: PrincipalContextV1,
        scopes: tuple[AuthorizedNotebookScope, ...],
        limit: int,
    ) -> UUID:
        snapshot, binding = self._context(principal, scopes)
        state = self._codec.decode(
            token,
            expected_domain="mnemo-notebook-inventory/v1",
            expected_snapshot_identity=snapshot,
            expected_binding=binding,
            expected_limits={"limit": limit},
        )
        key = state.position.get("key")
        if len(state.position) != 1 or not isinstance(key, str):
            raise CursorInvalidError("cursor position is invalid")
        try:
            return UUID(key)
        except ValueError as error:
            raise CursorInvalidError("cursor position is invalid") from error
