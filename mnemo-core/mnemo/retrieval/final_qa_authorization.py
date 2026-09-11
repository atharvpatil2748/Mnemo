"""Fail-closed evidence authorizer for Final-QA V2 composition."""

from __future__ import annotations

from uuid import UUID

from mnemo.interfaces import PrincipalContextV1, StorageInterfaceV1
from mnemo.interfaces.asset_catalog import AssetCatalogStoreV1
from mnemo.models.multimodal import EvidenceCandidateV2
from mnemo.retrieval.scope import (
    StorageDocumentScopeResolverV1,
    StorageSourceAssociationReaderV1,
)


class StorageEvidenceAuthorizerV2:
    """Authorize candidate provenance through canonical notebook membership."""

    def __init__(self, storage: StorageInterfaceV1) -> None:
        if not isinstance(storage, StorageInterfaceV1):
            raise TypeError("storage must implement StorageInterfaceV1")
        self._storage = storage
        self._resolver = StorageDocumentScopeResolverV1(
            storage, StorageSourceAssociationReaderV1(storage)
        )

    async def authorize_evidence(
        self, actor_id: UUID, notebook_id: UUID, candidate: EvidenceCandidateV2
    ) -> bool:
        if candidate.notebook_id != notebook_id:
            return False
        try:
            scope = await self._resolver.resolve_document_scope(
                PrincipalContextV1(actor_id, True),
                candidate.document_id,
                candidate.version_id,
                notebook_id,
            )
        except Exception:
            return False
        if candidate.source_id != scope.source_id:
            return False
        if candidate.occurrence_id is None and candidate.derivation_id is None:
            return True
        if not isinstance(self._storage, AssetCatalogStoreV1):
            return False
        if candidate.occurrence_id is None:
            return False
        occurrence = await self._storage.get_authorized_asset_occurrence(
            notebook_id=notebook_id, occurrence_id=candidate.occurrence_id
        )
        if occurrence is None or (
            occurrence.document_id != candidate.document_id
            or occurrence.version_id != candidate.version_id
        ):
            return False
        if candidate.derivation_id is not None:
            derivation = await self._storage.get_asset_derivation(candidate.derivation_id)
            if derivation is None or derivation.occurrence_id != occurrence.occurrence_id:
                return False
        return True

    async def generation_is_active(self, candidate: EvidenceCandidateV2) -> bool:
        if candidate.generation_id is None:
            return True
        # Derived generation activation is validated by WP-02 stores. A generic
        # authorizer must fail closed when no store-specific activation method exists.
        checker = getattr(self._storage, "generation_is_active", None)
        if not callable(checker):
            return False
        return bool(await checker(candidate.generation_id))
