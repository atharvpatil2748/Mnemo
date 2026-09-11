"""Central server-owned principal and Phase 8.5 scope authorization boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid5

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import NotFoundError, PrincipalContextV1, ResolvedDocumentScope

_ACTOR_NAMESPACE = UUID("f3d4e4e3-b4d4-52e8-89f1-e6e8d5a32472")


class AuthorizationOperationV1(StrEnum):
    RETRIEVE = "retrieve"
    DELIVER = "deliver"
    QUERY = "query"
    FINAL_QA = "final_qa"
    REPLAY = "replay"


ServerPrincipalV1 = PrincipalContextV1


@dataclass(frozen=True, slots=True)
class AuthorizationDecisionV1:
    allowed: bool
    operation: AuthorizationOperationV1
    actor_id: UUID
    notebook_id: UUID
    capability: str
    request_id: UUID | None
    reason_code: str


class CentralAuthorizationServiceV1:
    """Apply the current notebook isolation policy without existence leakage."""

    def __init__(self, engine: KnowledgeEngine) -> None:
        self._engine = engine

    async def authorize_notebook(
        self,
        principal: PrincipalContextV1,
        notebook_id: UUID,
        operation: AuthorizationOperationV1,
        *,
        capability: str | None = None,
        request_id: UUID | None = None,
    ) -> AuthorizationDecisionV1:
        # Current Phase 8.5 persistence has no actor-to-notebook ownership relation.
        # Carry the actor consistently and enforce canonical notebook membership.
        if await self._engine.storage.get_notebook(notebook_id) is None:
            raise NotFoundError("authorized resource was not found")
        return AuthorizationDecisionV1(
            True,
            operation,
            principal.actor_id,
            notebook_id,
            capability or operation.value,
            request_id,
            "authorized_scope",
        )

    async def authorize_document(
        self,
        principal: PrincipalContextV1,
        notebook_id: UUID,
        document_id: UUID,
        version_id: UUID,
        operation: AuthorizationOperationV1,
    ) -> ResolvedDocumentScope:
        await self.authorize_notebook(principal, notebook_id, operation)
        return await self._engine.document_scope_resolver.resolve_document_scope(
            principal, document_id, version_id, notebook_id
        )


def principal_from_claims(claims: dict[str, object] | None) -> ServerPrincipalV1:
    """Derive an opaque stable actor only from server-validated claims."""
    subject = None if claims is None else claims.get("sub")
    if isinstance(subject, str) and subject.strip():
        return ServerPrincipalV1(uuid5(_ACTOR_NAMESPACE, subject.strip()), True)
    return ServerPrincipalV1(uuid5(_ACTOR_NAMESPACE, "anonymous"), False)
