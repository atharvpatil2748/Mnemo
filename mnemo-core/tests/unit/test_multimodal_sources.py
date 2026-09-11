from uuid import uuid4

import pytest
from mnemo.interfaces.advanced_retrieval import (
    MultilingualEvidencePage,
    MultilingualEvidenceRecord,
    MultimodalEvidencePage,
    MultimodalEvidenceRecord,
    VisualQueryVector,
    VisualVectorMetric,
)
from mnemo.models.advanced_retrieval import (
    AdvancedRetrievalMode,
    EvidenceRepresentation,
    ExpansionPolicy,
    RankingPolicyV2,
    RetrievalPlanV2,
    RetrievalScopeV2,
)
from mnemo.retrieval.multimodal_sources import (
    ProjectedMultilingualAdvancedSource,
    ProjectedMultimodalAdvancedSource,
)


class _Store:
    def __init__(self, representation: EvidenceRepresentation) -> None:
        self.representation = representation
        self.calls = []

    async def active_multimodal_generation_identity(self, representation, *, profile_id=None):
        return "generation"

    async def retrieve_multimodal_evidence(self, **kwargs):
        self.calls.append(kwargs)
        notebook = kwargs["scope"].notebook_id
        document = uuid4()
        occurrence = uuid4()
        record = MultimodalEvidenceRecord(
            notebook_id=notebook,
            source_id=uuid4(),
            document_id=document,
            version_id=uuid4(),
            occurrence_id=occurrence,
            asset_id=uuid4(),
            derivation_id=uuid4(),
            generation_id=uuid4(),
            document_title="चित्र",
            content="Krishna अर्जुन",
            locator={"page_number": 2},
            language="mr",
            source_rank=1,
            source_score=0.8,
        )
        return MultimodalEvidencePage(
            snapshot_identity="a" * 64,
            records=(record,),
            examined=1,
            next_offset=None,
            exhausted=True,
        )


class _LanguageStore:
    async def retrieve_multilingual_evidence(self, **kwargs):
        scope = kwargs["scope"]
        value = MultilingualEvidenceRecord(
            notebook_id=scope.notebook_id,
            source_id=uuid4(),
            document_id=uuid4(),
            version_id=uuid4(),
            derivation_id=uuid4(),
            source_evidence_id="chunk-1",
            source_language="mr",
            target_language="en",
            content="मराठी मजकूर",
            source_rank=1,
            source_score=0.9,
        )
        return MultilingualEvidencePage(
            snapshot_identity="b" * 64,
            records=(value,),
            examined=1,
            next_offset=None,
            exhausted=True,
        )


@pytest.mark.anyio
async def test_projected_source_preserves_occurrence_and_language() -> None:
    notebook = uuid4()
    store = _Store(EvidenceRepresentation.VISION_ANALYSIS)
    source = ProjectedMultimodalAdvancedSource(
        store=store, representation=EvidenceRepresentation.VISION_ANALYSIS
    )
    plan = RetrievalPlanV2(
        mode=AdvancedRetrievalMode.RANKED,
        query="चित्र",
        scope=RetrievalScopeV2(notebook_id=notebook),
        representations=(EvidenceRepresentation.VISION_ANALYSIS,),
        ranking_policy=RankingPolicyV2.SOURCE_RANK_FUSION,
        expansion_policy=ExpansionPolicy.NONE,
        budgets={
            "recall_limit": 10,
            "fusion_limit": 10,
            "rerank_limit": 10,
            "expansion_limit": 10,
            "result_limit": 10,
            "max_serialized_bytes": 10000,
            "max_content_characters": 1000,
        },
    )
    page = await source.retrieve(plan, offset=0, limit=5)
    candidate = page.candidates[0]
    assert candidate.occurrence_id is not None
    assert candidate.derivation_id is not None
    assert candidate.locator["language"] == "mr"
    assert candidate.locator["asset_id"]
    assert candidate.paths[0].path == "active-vision-text-projection"


def test_visual_query_vector_rejects_dimension_mismatch() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        VisualQueryVector(
            profile_id="p",
            shared_space_id="s",
            dimensions=2,
            metric=VisualVectorMetric.COSINE,
            values=(1.0,),
        )


@pytest.mark.anyio
async def test_multilingual_source_preserves_language_provenance() -> None:
    notebook = uuid4()
    source = ProjectedMultilingualAdvancedSource(_LanguageStore())
    plan = RetrievalPlanV2(
        mode=AdvancedRetrievalMode.RANKED,
        query="मराठी",
        scope=RetrievalScopeV2(notebook_id=notebook),
        representations=(EvidenceRepresentation.MULTILINGUAL_TEXT,),
        ranking_policy=RankingPolicyV2.SOURCE_RANK_FUSION,
        expansion_policy=ExpansionPolicy.NONE,
        budgets={
            "recall_limit": 10,
            "fusion_limit": 10,
            "rerank_limit": 10,
            "expansion_limit": 10,
            "result_limit": 10,
            "max_serialized_bytes": 10000,
            "max_content_characters": 1000,
        },
    )
    page = await source.retrieve(plan, offset=0, limit=5)
    assert page.candidates[0].locator["source_language"] == "mr"
    assert page.candidates[0].content == "मराठी मजकूर"
