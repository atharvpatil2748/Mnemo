"""Additive authorization and document-scope contracts for Phase 8.5."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.models import Source


class ScopeResolutionKind(StrEnum):
    EXPLICIT = "explicit"
    UNIQUE_ASSOCIATION = "unique_association"


class ScopeResolutionError(StrEnum):
    NOT_FOUND = "not_found"
    FORBIDDEN = "forbidden"
    AMBIGUOUS = "ambiguous"
    VERSION_MISMATCH = "version_mismatch"


@dataclass(frozen=True, slots=True)
class PrincipalContextV1:
    """Server-owned actor identity carried through every V2 boundary."""

    actor_id: UUID
    authenticated: bool


@dataclass(frozen=True, slots=True)
class ResolvedDocumentScope:
    notebook_id: UUID
    source_id: UUID
    document_id: UUID
    version_id: UUID
    resolution: ScopeResolutionKind


@runtime_checkable
class SourceAssociationReaderV1(Protocol):  # pragma: no cover
    async def list_sources_for_document(self, document_id: UUID) -> tuple[Source, ...]: ...


@runtime_checkable
class DocumentScopeResolverV1(Protocol):  # pragma: no cover
    async def resolve_document_scope(
        self,
        principal: PrincipalContextV1,
        document_id: UUID,
        version_id: UUID,
        requested_notebook_id: UUID | None,
    ) -> ResolvedDocumentScope: ...
