"""Unit tests for diversity-aware cross-encoder reranking."""

from __future__ import annotations

from uuid import UUID
import pytest
from mnemo.models import (
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    FrozenMetadata,
    FusedChunkResult,
    FusionEvidence,
    RetrievalMode,
    ScoredChunk,
)
from mnemo.retrieval.reranker import _apply_diversity_ordering

_DOC_A = UUID("10000000-0000-4000-8000-000000000001")
_DOC_B = UUID("10000000-0000-4000-8000-000000000002")
_VERSION_ID = UUID("20000000-0000-4000-8000-000000000001")


def _make_chunk(index: int, doc_name: str, text: str = "sample text", doc_id: UUID = _DOC_A) -> Chunk:
    return Chunk(
        id=f"{index:064x}",
        text=text,
        document_id=doc_id,
        version_id=_VERSION_ID,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=index),
        source_span=BlockSpan(start_ordinal=index, end_ordinal=index),
        heading_path=(doc_name,),
        metadata=FrozenMetadata({"source_name": doc_name, "structural_ref": f"{doc_name} > Section"}),
    )


def _make_fused_result(chunk: Chunk, rank: int, score: float = 0.5) -> FusedChunkResult:
    scored = ScoredChunk(chunk=chunk, score=score, source="dense", rank=rank)
    evidence = (
        FusionEvidence(
            invocation_id="sq-1:dense",
            subquery_index=1,
            declared_mode=RetrievalMode.DENSE,
            effective_mode=RetrievalMode.DENSE,
            result=scored,
            identity_introduced_by_parent_promotion=False,
        ),
    )
    return FusedChunkResult(
        chunk=chunk,
        rrf_score=score,
        global_rank=rank,
        evidence=evidence,
    )


def test_diversity_single_document_query():
    """When query targets a single document, standard score ordering is preserved."""
    c1 = _make_chunk(1, "docA", "Gita Chapter 2 Text 47")
    c2 = _make_chunk(2, "docA", "Gita Chapter 2 Text 48")
    c3 = _make_chunk(3, "docA", "Gita Chapter 2 Text 49")
    
    fused_items = [
        _make_fused_result(c1, 1),
        _make_fused_result(c2, 2),
        _make_fused_result(c3, 3),
    ]
    scores_by_id = {c1.id: 0.9, c2.id: 0.8, c3.id: 0.7}
    
    ordered = _apply_diversity_ordering(
        query="Tell me Bhagavad Gita 2.47",
        fused_items=fused_items,
        scores_by_id=scores_by_id,
    )
    
    assert [item.chunk.id for item in ordered] == [c1.id, c2.id, c3.id]


def test_diversity_multi_document_preserves_top_from_each_relevant_source():
    """On multi-document query, ensures top chunk from each relevant source is guaranteed."""
    c_resume1 = _make_chunk(1, "Atharv_Patil_RESUME_SDE.pdf", "Education CPI: 8.9", doc_id=_DOC_A)
    c_csv1 = _make_chunk(2, "Y24_CPI.csv", "Roll 240740 CPI: 9.0", doc_id=_DOC_B)
    c_csv2 = _make_chunk(3, "Y24_CPI.csv", "Roll 240741 CPI: 8.5", doc_id=_DOC_B)
    c_csv3 = _make_chunk(4, "Y24_CPI.csv", "Roll 240742 CPI: 7.9", doc_id=_DOC_B)
    
    fused_items = [
        _make_fused_result(c_csv1, 1),
        _make_fused_result(c_csv2, 2),
        _make_fused_result(c_csv3, 3),
        _make_fused_result(c_resume1, 4),
    ]
    # Suppose CrossEncoder scored CSV chunks higher than Resume
    scores_by_id = {
        c_csv1.id: 0.95,
        c_csv2.id: 0.90,
        c_csv3.id: 0.85,
        c_resume1.id: 0.75,
    }
    
    query = "Compare Atharv's CPI in his resume with Y24 CPI dataset for roll 240740"
    ordered = _apply_diversity_ordering(
        query=query,
        fused_items=fused_items,
        scores_by_id=scores_by_id,
    )
    
    top_2_sources = [item.chunk.metadata["source_name"] for item in ordered[:2]]
    assert "Y24_CPI.csv" in top_2_sources
    assert "Atharv_Patil_RESUME_SDE.pdf" in top_2_sources
    assert ordered[0].chunk.id == c_csv1.id
    assert ordered[1].chunk.id == c_resume1.id


def test_diversity_does_not_force_irrelevant_documents():
    """An irrelevant document with low score is NOT forced into top positions."""
    c_gita1 = _make_chunk(1, "Bhagavad-gita-As-It-Is.pdf", "Karma yoga text 47", doc_id=_DOC_A)
    c_gita2 = _make_chunk(2, "Bhagavad-gita-As-It-Is.pdf", "Karma yoga text 48", doc_id=_DOC_A)
    c_irrelevant = _make_chunk(3, "Unrelated_Receipt.pdf", "Total amount $50", doc_id=_DOC_B)
    
    fused_items = [
        _make_fused_result(c_gita1, 1),
        _make_fused_result(c_gita2, 2),
        _make_fused_result(c_irrelevant, 3),
    ]
    scores_by_id = {
        c_gita1.id: 0.92,
        c_gita2.id: 0.88,
        c_irrelevant.id: 0.10,  # Below relevance threshold
    }
    
    query = "What does Bhagavad Gita say about duty?"
    ordered = _apply_diversity_ordering(
        query=query,
        fused_items=fused_items,
        scores_by_id=scores_by_id,
    )
    
    assert ordered[-1].chunk.id == c_irrelevant.id
    assert [item.chunk.id for item in ordered[:2]] == [c_gita1.id, c_gita2.id]


def test_diversity_deterministic_tie_breaking():
    """Ties are broken deterministically by global_rank and chunk.id."""
    c1 = _make_chunk(1, "docA", "content 1")
    c2 = _make_chunk(2, "docA", "content 2")
    
    fused_items = [
        _make_fused_result(c1, 1),
        _make_fused_result(c2, 2),
    ]
    scores_by_id = {c1.id: 0.85, c2.id: 0.85}
    
    ordered = _apply_diversity_ordering(
        query="test query",
        fused_items=fused_items,
        scores_by_id=scores_by_id,
    )
    
    assert ordered[0].chunk.id == c1.id
    assert ordered[1].chunk.id == c2.id
