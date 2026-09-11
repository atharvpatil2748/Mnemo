"""Occurrence-scoped advanced retrieval sources over active WP-02 projections."""

from __future__ import annotations

from mnemo.interfaces.advanced_retrieval import (
    AdvancedSourcePage,
    MultilingualAdvancedStoreV1,
    MultilingualEvidenceRecord,
    MultimodalAdvancedStoreV1,
    MultimodalEvidenceRecord,
    VisualQueryEmbeddingProviderV1,
)
from mnemo.models import FrozenMetadata
from mnemo.models.advanced_retrieval import (
    AdvancedRetrievalCandidate,
    AdvancedRetrievalMode,
    EvidenceRepresentation,
    RetrievalPathEvidenceV2,
    RetrievalPlanV2,
    advanced_candidate_id,
)


class ProjectedMultimodalAdvancedSource:
    """Adapt one authorized named multimodal representation to rank fusion."""

    def __init__(
        self,
        *,
        store: MultimodalAdvancedStoreV1,
        representation: EvidenceRepresentation,
        visual_query_provider: VisualQueryEmbeddingProviderV1 | None = None,
    ) -> None:
        if representation not in {
            EvidenceRepresentation.OCR_TEXT,
            EvidenceRepresentation.VISION_ANALYSIS,
            EvidenceRepresentation.VISUAL_VECTOR,
            EvidenceRepresentation.ASSET_METADATA,
        }:
            raise ValueError("unsupported multimodal representation")
        if representation is EvidenceRepresentation.VISUAL_VECTOR and visual_query_provider is None:
            raise ValueError("visual-vector source requires a text-query embedding provider")
        if representation is not EvidenceRepresentation.VISUAL_VECTOR and visual_query_provider:
            raise ValueError("visual query provider is only valid for visual-vector retrieval")
        self._store = store
        self._representation = representation
        self._visual_query_provider = visual_query_provider

    @property
    def representation(self) -> EvidenceRepresentation:
        return self._representation

    async def retrieve(
        self, plan: RetrievalPlanV2, *, offset: int, limit: int
    ) -> AdvancedSourcePage:
        query_vector = None
        if self._visual_query_provider is not None:
            query_vector = await self._visual_query_provider.embed_text(plan.query)
        page = await self._store.retrieve_multimodal_evidence(
            representation=self._representation,
            scope=plan.scope,
            position=plan.position,
            query=plan.query,
            ranked=plan.mode is AdvancedRetrievalMode.RANKED,
            offset=offset,
            limit=limit,
            query_vector=query_vector,
        )
        return AdvancedSourcePage(
            representation=self._representation,
            snapshot_identity=page.snapshot_identity,
            candidates=tuple(_candidate(self._representation, item) for item in page.records),
            examined=page.examined,
            next_offset=page.next_offset,
            exhausted=page.exhausted,
        )

    async def expand(
        self,
        plan: RetrievalPlanV2,
        seeds: tuple[AdvancedRetrievalCandidate, ...],
        *,
        limit: int,
    ) -> tuple[AdvancedRetrievalCandidate, ...]:
        del plan, seeds, limit
        return ()


class ProjectedMultilingualAdvancedSource:
    """Expose active derived language text as an advanced evidence source."""

    def __init__(self, store: MultilingualAdvancedStoreV1) -> None:
        self._store = store

    @property
    def representation(self) -> EvidenceRepresentation:
        return EvidenceRepresentation.MULTILINGUAL_TEXT

    async def retrieve(
        self, plan: RetrievalPlanV2, *, offset: int, limit: int
    ) -> AdvancedSourcePage:
        page = await self._store.retrieve_multilingual_evidence(
            scope=plan.scope,
            position=plan.position,
            query=plan.query,
            offset=offset,
            limit=limit,
        )
        return AdvancedSourcePage(
            representation=self.representation,
            snapshot_identity=page.snapshot_identity,
            candidates=tuple(_language_candidate(item) for item in page.records),
            examined=page.examined,
            next_offset=page.next_offset,
            exhausted=page.exhausted,
        )

    async def expand(
        self,
        plan: RetrievalPlanV2,
        seeds: tuple[AdvancedRetrievalCandidate, ...],
        *,
        limit: int,
    ) -> tuple[AdvancedRetrievalCandidate, ...]:
        del plan, seeds, limit
        return ()


def _candidate(
    representation: EvidenceRepresentation, record: MultimodalEvidenceRecord
) -> AdvancedRetrievalCandidate:
    locator = dict(record.locator)
    locator["asset_id"] = str(record.asset_id)
    if record.language is not None:
        locator["language"] = record.language
    if record.generation_id is not None:
        locator["generation_id"] = str(record.generation_id)
    path = {
        EvidenceRepresentation.OCR_TEXT: "active-ocr-projection",
        EvidenceRepresentation.VISION_ANALYSIS: "active-vision-text-projection",
        EvidenceRepresentation.VISUAL_VECTOR: "active-visual-shared-space",
        EvidenceRepresentation.ASSET_METADATA: "authorized-asset-metadata",
    }[representation]
    return AdvancedRetrievalCandidate(
        candidate_id=advanced_candidate_id(
            representation=representation,
            document_id=record.document_id,
            version_id=record.version_id,
            chunk_id=None,
            occurrence_id=record.occurrence_id,
            derivation_id=record.derivation_id,
        ),
        notebook_id=record.notebook_id,
        source_id=record.source_id,
        document_id=record.document_id,
        version_id=record.version_id,
        representation=representation,
        chunk=None,
        occurrence_id=record.occurrence_id,
        derivation_id=record.derivation_id,
        locator=FrozenMetadata(locator),
        document_title=record.document_title,
        content=record.content,
        paths=(
            RetrievalPathEvidenceV2(
                path=path,
                source_rank=record.source_rank,
                source_score=record.source_score,
            ),
        ),
    )


def _language_candidate(
    record: MultilingualEvidenceRecord,
) -> AdvancedRetrievalCandidate:
    return AdvancedRetrievalCandidate(
        candidate_id=advanced_candidate_id(
            representation=EvidenceRepresentation.MULTILINGUAL_TEXT,
            document_id=record.document_id,
            version_id=record.version_id,
            chunk_id=None,
            occurrence_id=None,
            derivation_id=record.derivation_id,
        ),
        notebook_id=record.notebook_id,
        source_id=record.source_id,
        document_id=record.document_id,
        version_id=record.version_id,
        representation=EvidenceRepresentation.MULTILINGUAL_TEXT,
        chunk=None,
        occurrence_id=None,
        derivation_id=record.derivation_id,
        locator=FrozenMetadata(
            {
                "source_evidence_id": record.source_evidence_id,
                "source_language": record.source_language,
                "target_language": record.target_language,
                "evidence_kind": "derived_multilingual_text",
            }
        ),
        document_title=None,
        content=record.content,
        paths=(
            RetrievalPathEvidenceV2(
                path="active-multilingual-text-projection",
                source_rank=record.source_rank,
                source_score=record.source_score,
            ),
        ),
    )
