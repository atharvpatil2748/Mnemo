"""Exact-version structured dataset catalogue contracts for Phase 8.5 WP-08."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from ._shared import require_sha256
from .advanced_retrieval import AdvancedRetrievalCandidate, RetrievalScopeV2
from .structured_retrieval import StructuredField, StructuredSchemaConfidence


class StructuredDatasetReadiness(StrEnum):
    READY = "ready"
    STALE = "stale"
    FAILED = "failed"
    INACTIVE = "inactive"


@dataclass(frozen=True, slots=True, kw_only=True)
class StructuredDatasetField:
    field: StructuredField
    confidence: StructuredSchemaConfidence
    non_missing_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class StructuredDatasetDescriptor:
    dataset_id: UUID
    generation_id: UUID
    schema_identity: str
    checksum: str
    notebook_id: UUID
    source_id: UUID
    document_id: UUID
    version_id: UUID
    block_ordinal: int
    page_number: int | None
    row_count: int
    fields: tuple[StructuredDatasetField, ...]
    readiness: StructuredDatasetReadiness
    candidate: AdvancedRetrievalCandidate

    def __post_init__(self) -> None:
        require_sha256(self.schema_identity, "schema_identity")
        require_sha256(self.checksum, "checksum")
        if self.row_count < 0 or self.block_ordinal < 0:
            raise ValueError("structured dataset positions and counts must be non-negative")
        if not self.fields:
            raise ValueError("structured dataset requires a non-empty schema")


@dataclass(frozen=True, slots=True, kw_only=True)
class StructuredDatasetCatalog:
    scope: RetrievalScopeV2
    snapshot_identity: str
    datasets: tuple[StructuredDatasetDescriptor, ...]
    requested_version_ids: tuple[UUID, ...]
    ready_version_ids: tuple[UUID, ...]
    unavailable_version_ids: tuple[UUID, ...]

    def __post_init__(self) -> None:
        require_sha256(self.snapshot_identity, "snapshot_identity")
        if set(self.ready_version_ids) & set(self.unavailable_version_ids):
            raise ValueError("structured version readiness sets must be disjoint")
