"""Bounded, authorized presentation metadata for canonical source identities.

The source association and document version remain the authority.  This module
never interprets a filename or title as an identity or a storage locator.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import NotFoundError, PrincipalContextV1
from mnemo.models import thaw_metadata
from pydantic import BaseModel, ConfigDict

from mnemo_server.services.authorization import (
    AuthorizationOperationV1,
    CentralAuthorizationServiceV1,
)


class SourceMetadataEnvelopeV1(BaseModel):
    """Additive, nullable source presentation contract (version 1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "mnemo.source-metadata/1"
    notebook_id: UUID
    source_id: UUID
    document_id: UUID
    version_id: UUID
    display_name: str | None
    original_filename: str | None
    document_title: str | None
    mime_type: str | None
    content_hash: str


@dataclass(frozen=True, slots=True)
class SourceMetadataReferenceV1:
    notebook_id: UUID
    document_id: UUID
    version_id: UUID | None = None
    source_id: UUID | None = None


def _safe_text(value: object, *, mime: bool = False) -> str | None:
    """Suppress internal paths and malformed persisted display values."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > 256 or any(ord(char) < 32 for char in value):
        return None
    if ("/" in value or "\\" in value) and not mime:
        return None
    if len(value) >= 2 and value[1] == ":" and value[0].isalpha():
        return None
    if mime and re.fullmatch(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", value) is None:
        return None
    return value


class AuthorizedSourceMetadataResolverV1:
    """Resolve at most 200 requested identities; no unbounded lookup or body scan.

    The existing canonical scope resolver performs the membership check.  A
    document snapshot contains version metadata, not parsed bodies or binaries.
    Duplicate references share one resolution in this request-local cache.
    """

    MAX_REFERENCES = 200

    def __init__(self, engine: KnowledgeEngine) -> None:
        self._engine = engine

    async def resolve_many(
        self,
        principal: PrincipalContextV1,
        references: tuple[SourceMetadataReferenceV1, ...],
    ) -> dict[SourceMetadataReferenceV1, SourceMetadataEnvelopeV1]:
        if not principal.authenticated:
            raise PermissionError("authenticated principal is required")
        if len(references) > self.MAX_REFERENCES:
            raise ValueError("source metadata lookup exceeds the bounded limit")
        resolved: dict[SourceMetadataReferenceV1, SourceMetadataEnvelopeV1] = {}
        for reference in dict.fromkeys(references):
            await CentralAuthorizationServiceV1(self._engine).authorize_notebook(
                principal, reference.notebook_id, AuthorizationOperationV1.RETRIEVE
            )
            document = None
            version_id = reference.version_id
            if version_id is None:
                document = await self._engine.storage.get_document(reference.document_id)
                if document is None:
                    raise NotFoundError("authorized resource was not found")
                version_id = document.current_version_id
            scope = await self._engine.document_scope_resolver.resolve_document_scope(
                principal,
                reference.document_id,
                version_id,
                reference.notebook_id,
            )
            if (
                scope.notebook_id != reference.notebook_id
                or scope.document_id != reference.document_id
                or scope.version_id != version_id
            ):
                raise NotFoundError("authorized resource was not found")
            if reference.source_id is not None and scope.source_id != reference.source_id:
                raise NotFoundError("authorized resource was not found")
            if document is None:
                document = await self._engine.storage.get_document(reference.document_id)
            if document is None:
                raise NotFoundError("authorized resource was not found")
            version = next(
                (item for item in document.versions if item.version_id == version_id),
                None,
            )
            if version is None:
                raise NotFoundError("authorized resource was not found")
            optional = thaw_metadata(version.metadata.metadata)
            filename = _safe_text(optional.get("original_filename", optional.get("filename")))
            title = _safe_text(version.metadata.title)
            display = _safe_text(optional.get("display_name")) or title or filename
            resolved[reference] = SourceMetadataEnvelopeV1(
                notebook_id=scope.notebook_id,
                source_id=scope.source_id,
                document_id=scope.document_id,
                version_id=scope.version_id,
                display_name=display,
                original_filename=filename,
                document_title=title,
                mime_type=_safe_text(
                    optional.get("mime_type", optional.get("media_type")), mime=True
                ),
                content_hash=version.content_hash,
            )
        return resolved

    async def resolve(
        self, principal: PrincipalContextV1, reference: SourceMetadataReferenceV1
    ) -> SourceMetadataEnvelopeV1:
        return (await self.resolve_many(principal, (reference,)))[reference]
