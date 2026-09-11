"""Provider-neutral Phase 8.5.7 structured-retrieval contracts."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.models.advanced_retrieval import (
    AdvancedRetrievalCandidate,
    RetrievalResultSetV1,
    RetrievalScopeV2,
)
from mnemo.models.documents import ParsedDocument
from mnemo.models.structured_datasets import StructuredDatasetCatalog
from mnemo.models.structured_retrieval import (
    ExtractedStructuredRecord,
    StructuredField,
    StructuredQueryV1,
    StructuredResult,
)


@runtime_checkable
class StructuredEvidenceExtractorV1(Protocol):  # pragma: no cover
    """Extract bounded raw records from one authorized retrieval candidate."""

    async def extract(
        self,
        candidate: AdvancedRetrievalCandidate,
        fields: tuple[StructuredField, ...],
        *,
        limit: int,
    ) -> tuple[ExtractedStructuredRecord, ...]: ...


@runtime_checkable
class StructuredIRReaderV1(Protocol):  # pragma: no cover
    """Read exact-version canonical IR without widening StorageInterfaceV1."""

    async def get_parsed_document(self, version_id: UUID) -> ParsedDocument | None: ...


@runtime_checkable
class StructuredProjectionStoreV1(Protocol):  # pragma: no cover
    async def project_structured_document(
        self, version_id: UUID, document: ParsedDocument
    ) -> bool: ...

    async def extract_projected_structured_records(
        self,
        candidate: AdvancedRetrievalCandidate,
        fields: tuple[StructuredField, ...],
        *,
        limit: int,
    ) -> tuple[ExtractedStructuredRecord, ...]: ...


@runtime_checkable
class StructuredDatasetCatalogV1(Protocol):  # pragma: no cover
    """Discover and read only active exact-version structured projections."""

    async def list_structured_datasets(
        self, *, scope: RetrievalScopeV2, schema_scan_limit: int
    ) -> StructuredDatasetCatalog: ...

    async def structured_projection_ready(self) -> bool: ...

    async def active_structured_generation_identity(self) -> str | None: ...

    async def extract_structured_dataset_records(
        self,
        *,
        notebook_id: UUID,
        dataset_id: UUID,
        candidate_id: UUID,
        fields: tuple[StructuredField, ...],
        limit: int,
    ) -> tuple[ExtractedStructuredRecord, ...]: ...


@runtime_checkable
class StructuredRetrievalInterfaceV1(Protocol):  # pragma: no cover
    async def execute(
        self,
        query: StructuredQueryV1,
        retrieval: RetrievalResultSetV1,
    ) -> StructuredResult: ...
