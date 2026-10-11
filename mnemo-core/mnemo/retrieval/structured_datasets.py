"""Operational exact-dataset orchestration for Phase 8.5 WP-08."""

from __future__ import annotations

from dataclasses import replace
from typing import cast
from uuid import UUID

from mnemo.interfaces import (
    ContractValidationError,
    DependencyUnavailableError,
    IntegrityError,
    StructuredDatasetCatalogV1,
)
from mnemo.models import (
    AdvancedRetrievalMode,
    EvidenceRepresentation,
    RankingPolicyV2,
    RepresentationReportV2,
    RepresentationSearchStatus,
    RetrievalCompleteness,
    RetrievalDiagnosticsV2,
    RetrievalResultSetV1,
    RetrievalScopeV2,
    StructuredDatasetCatalog,
    StructuredDatasetDescriptor,
    StructuredDatasetReadiness,
    StructuredQueryV1,
    StructuredResult,
)

from .structured import StructuredDatasetEvidenceExtractor, StructuredRetrievalService


class StructuredDatasetRuntimeService:
    """Compose catalog, projection reader, and the frozen typed execution engine."""

    def __init__(self, store: StructuredDatasetCatalogV1) -> None:
        if not isinstance(store, StructuredDatasetCatalogV1):
            raise TypeError("store must implement StructuredDatasetCatalogV1")
        self._store = store

    async def discover(
        self, *, scope: RetrievalScopeV2, schema_scan_limit: int
    ) -> StructuredDatasetCatalog:
        return await self._store.list_structured_datasets(
            scope=scope, schema_scan_limit=schema_scan_limit
        )

    async def ready(self) -> bool:
        return await self._store.structured_projection_ready()

    async def ready_for_notebook(self, notebook_id: UUID) -> bool | None:
        """Return scoped readiness when the store has a bounded readiness probe."""
        probe = getattr(self._store, "structured_projection_ready_for_notebook", None)
        return await probe(notebook_id) if callable(probe) else None

    async def resolve_version_associations(
        self, notebook_id: UUID, version_ids: tuple[UUID, ...]
    ) -> tuple[tuple[UUID, UUID, UUID], ...]:
        """Fail closed when the store cannot prove a version's canonical scope."""
        probe = getattr(self._store, "resolve_structured_version_associations", None)
        if not callable(probe):
            raise DependencyUnavailableError("structured version scope reader is unavailable")
        return cast(tuple[tuple[UUID, UUID, UUID], ...], await probe(notebook_id, version_ids))

    async def active_generation_identity(self) -> str | None:
        return await self._store.active_structured_generation_identity()

    async def execute(
        self,
        *,
        query: StructuredQueryV1,
        catalog: StructuredDatasetCatalog,
        dataset_ids: tuple[UUID, ...],
    ) -> StructuredResult:
        selected = _select_ready(catalog, dataset_ids)
        if query.retrieval_plan.scope != catalog.scope:
            raise ContractValidationError("structured query scope does not match dataset catalog")
        _validate_compatible_schema(selected, query)
        candidates = tuple(
            replace(item.candidate, final_rank=index) for index, item in enumerate(selected, 1)
        )
        if len({item.candidate_id for item in candidates}) != len(candidates):
            raise ContractValidationError(
                "selected datasets do not have distinct canonical evidence anchors"
            )
        retrieval = RetrievalResultSetV1(
            query_fingerprint=query.retrieval_plan.fingerprint,
            snapshot_identity=catalog.snapshot_identity,
            ordering_policy=RankingPolicyV2.DETERMINISTIC_STORAGE_ORDER,
            completeness=RetrievalCompleteness.COMPLETE,
            results=candidates,
            examined_count=len(candidates),
            returned_count=len(candidates),
            next_cursor=None,
            diagnostics=RetrievalDiagnosticsV2(
                mode=AdvancedRetrievalMode.EXHAUSTIVE,
                recalled=len(candidates),
                expanded=0,
                deduplicated=0,
                fused=len(candidates),
                reranked=0,
                returned=len(candidates),
                serialized_bytes=0,
                content_characters=0,
                truncated=False,
                truncation_reason=None,
                elapsed_milliseconds=0,
                representation_reports=(
                    RepresentationReportV2(
                        representation=EvidenceRepresentation.CANONICAL_TEXT,
                        status=RepresentationSearchStatus.SEARCHED,
                        examined=len(candidates),
                        returned=len(candidates),
                        exhausted=True,
                    ),
                ),
            ),
        )
        extractor = StructuredDatasetEvidenceExtractor(
            self._store,
            {item.candidate.candidate_id: item.dataset_id for item in selected},
        )
        result = await StructuredRetrievalService(extractor).execute(query, retrieval)
        if result.metadata.retrieval_snapshot_identity != catalog.snapshot_identity:
            raise IntegrityError("structured execution changed the dataset snapshot")
        return result


def _select_ready(
    catalog: StructuredDatasetCatalog, dataset_ids: tuple[UUID, ...]
) -> tuple[StructuredDatasetDescriptor, ...]:
    if not dataset_ids or len(set(dataset_ids)) != len(dataset_ids):
        raise ContractValidationError("dataset_ids must be non-empty and unique")
    by_id = {item.dataset_id: item for item in catalog.datasets}
    if any(dataset_id not in by_id for dataset_id in dataset_ids):
        # Do not disclose whether an unknown identity exists outside this scope.
        raise ContractValidationError(
            "one or more datasets are unavailable in the authorized scope"
        )
    selected = tuple(by_id[item] for item in dataset_ids)
    if any(item.readiness is not StructuredDatasetReadiness.READY for item in selected):
        raise DependencyUnavailableError(
            "structured generation is unavailable in the authorized scope"
        )
    return selected


def _validate_compatible_schema(
    datasets: tuple[StructuredDatasetDescriptor, ...], query: StructuredQueryV1
) -> None:
    requested = tuple(
        (field.name.casefold(), field.field_type.value, field.unit) for field in query.fields
    )
    for dataset in datasets:
        available = {
            item.field.name.casefold(): (item.field.field_type.value, item.field.unit)
            for item in dataset.fields
        }
        for name, field_type, unit in requested:
            if available.get(name) != (field_type, unit):
                raise ContractValidationError("selected datasets have incompatible schemas")
