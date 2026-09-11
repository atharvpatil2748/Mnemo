"""Canonical additive document-scope resolution and authorization."""

from __future__ import annotations

import inspect
from uuid import UUID

from mnemo.interfaces import ContractValidationError, NotFoundError
from mnemo.interfaces.scope import (
    DocumentScopeResolverV1,
    PrincipalContextV1,
    ResolvedDocumentScope,
    ScopeResolutionKind,
    SourceAssociationReaderV1,
)
from mnemo.interfaces.storage import StorageInterfaceV1
from mnemo.models import Source


class StorageSourceAssociationReaderV1:
    """Narrow compatibility adapter over concrete association helpers."""

    def __init__(self, storage: object) -> None:
        reader = getattr(storage, "list_sources_for_document", None)
        if not callable(reader):
            reader = getattr(storage, "_list_sources_for_document", None)
        if not callable(reader):
            sql = getattr(storage, "_sql", None)
            reader = getattr(sql, "_list_sources_for_document", None)
        if not callable(reader):
            raise TypeError("storage does not provide additive source association lookup")
        self._reader = reader

    async def list_sources_for_document(self, document_id: UUID) -> tuple[Source, ...]:
        return tuple(await self._reader(document_id))


class StorageDocumentScopeResolverV1(DocumentScopeResolverV1):
    """Resolve an exact authorized notebook/document/version association."""

    def __init__(
        self, storage: StorageInterfaceV1, associations: SourceAssociationReaderV1
    ) -> None:
        self._storage = storage
        self._associations = associations

    async def resolve_document_scope(
        self,
        principal: PrincipalContextV1,
        document_id: UUID,
        version_id: UUID,
        requested_notebook_id: UUID | None,
    ) -> ResolvedDocumentScope:
        del principal  # Actor ownership policy is intentionally not invented in WP-14.
        document_lookup = self._storage.get_document(document_id)
        canonical_lookup = inspect.isawaitable(document_lookup)
        document = await document_lookup if canonical_lookup else None
        if canonical_lookup and document is None:
            raise NotFoundError("authorized resource was not found")
        if document is not None and version_id not in {
            version.version_id for version in document.versions
        }:
            raise NotFoundError("authorized resource was not found")
        sources = await self._associations.list_sources_for_document(document_id)
        if not sources:
            raise NotFoundError("authorized resource was not found")
        if requested_notebook_id is not None:
            matches = tuple(s for s in sources if s.notebook_id == requested_notebook_id)
            if len(matches) != 1:
                raise NotFoundError("authorized resource was not found")
            source = matches[0]
            return ResolvedDocumentScope(
                requested_notebook_id,
                source.source_id,
                document_id,
                version_id,
                ScopeResolutionKind.EXPLICIT,
            )
        notebook_ids = {source.notebook_id for source in sources}
        if len(notebook_ids) != 1:
            raise ContractValidationError(
                "document belongs to multiple notebooks; supply notebook_id"
            )
        source = min(sources, key=lambda item: str(item.source_id))
        return ResolvedDocumentScope(
            source.notebook_id,
            source.source_id,
            document_id,
            version_id,
            ScopeResolutionKind.UNIQUE_ASSOCIATION,
        )
