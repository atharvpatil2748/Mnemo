"""Central server-owned principal and Phase 8.5 scope authorization boundary."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import UUID, uuid5

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import (
    ContractValidationError,
    NotFoundError,
    PrincipalContextV1,
    ResolvedDocumentScope,
)
from mnemo.models import FusedChunkResult, RetrievalFusionResult
from mnemo.retrieval import StorageSourceAssociationReaderV1

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

    async def authorize_source(
        self,
        principal: PrincipalContextV1,
        source_id: UUID,
        operation: AuthorizationOperationV1,
    ) -> UUID:
        """Resolve a canonical source membership without disclosing unknown identities."""
        if not principal.authenticated:
            raise PermissionError("authenticated principal is required")
        source = await self._engine.storage.get_source(source_id)
        if source is None:
            raise NotFoundError("authorized resource was not found")
        await self.authorize_notebook(principal, source.notebook_id, operation)
        return source.notebook_id

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

    async def filter_fused_candidates(
        self,
        principal: PrincipalContextV1,
        fusion: RetrievalFusionResult,
        notebook_id: UUID | None,
    ) -> tuple[RetrievalFusionResult, dict[tuple[UUID, UUID], UUID]]:
        """Remove non-members before reranking, synthesis, counts, or snippets."""
        if not principal.authenticated:
            raise PermissionError("authenticated principal is required")
        permitted: list[FusedChunkResult] = []
        scopes: dict[tuple[UUID, UUID], UUID] = {}
        for result in fusion.results:
            chunk = result.chunk
            requested: tuple[UUID, ...] = () if notebook_id is None else (notebook_id,)
            if notebook_id is None:
                associations = await StorageSourceAssociationReaderV1(
                    self._engine.storage
                ).list_sources_for_document(chunk.document_id)
                requested = tuple(sorted({source.notebook_id for source in associations}))
            for candidate_notebook in requested:
                if candidate_notebook is None:
                    continue
                try:
                    resolved = await self._engine.document_scope_resolver.resolve_document_scope(
                        principal, chunk.document_id, chunk.version_id, candidate_notebook
                    )
                except (NotFoundError, ContractValidationError):
                    continue
                if (
                    resolved.document_id != chunk.document_id
                    or resolved.version_id != chunk.version_id
                    or resolved.notebook_id != candidate_notebook
                ):
                    continue
                scopes[(chunk.document_id, chunk.version_id)] = candidate_notebook
                permitted.append(replace(result, global_rank=len(permitted) + 1))
                break
        return replace(fusion, results=tuple(permitted)), scopes


def principal_from_claims(claims: dict[str, object] | None) -> ServerPrincipalV1:
    """Derive an opaque stable actor only from server-validated claims."""
    subject = None if claims is None else claims.get("sub")
    if isinstance(subject, str) and subject.strip():
        return ServerPrincipalV1(uuid5(_ACTOR_NAMESPACE, subject.strip()), True)
    return ServerPrincipalV1(uuid5(_ACTOR_NAMESPACE, "anonymous"), False)
