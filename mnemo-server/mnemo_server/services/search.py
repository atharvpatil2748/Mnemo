"""Search orchestration service coordinating global and scoped full-text and vector search."""

from __future__ import annotations

import logging
import time
from uuid import UUID

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import (
    ContractValidationError,
    NotFoundError,
    UnsupportedError,
)
from mnemo.models import (
    DocType,
    MetadataFilter,
    RetrievalIntent,
    RetrievalMode,
    RetrievalPlan,
    SubQuery,
    thaw_metadata,
)
from mnemo.retrieval import MultiSourceRetriever, RerankingModule

from mnemo_server.schemas.query import QueryFilters
from mnemo_server.schemas.search import SearchRequest, SearchResponse, SearchResultItem

_LOGGER = logging.getLogger(__name__)

_MODE_MAP = {
    "dense": RetrievalMode.DENSE,
    "sparse": RetrievalMode.SPARSE,
    "hybrid": RetrievalMode.HYBRID,
}


class SearchService:
    """Coordinates multi-mode full-text and dense vector search without LLM synthesis."""

    def __init__(self, engine: KnowledgeEngine) -> None:
        self._engine = engine

    async def execute_search(self, request: SearchRequest) -> SearchResponse:
        """Execute global or notebook-scoped multi-mode search and return ranked results."""
        start_time = time.perf_counter()

        # 1. Notebook Scope Validation (if specified)
        if request.notebook_id is not None:
            notebook = await self._engine.storage.get_notebook(request.notebook_id)
            if notebook is None:
                raise NotFoundError(f"Notebook with id '{request.notebook_id}' not found")

        # 2. Metadata Filter Translation
        metadata_filter = self._build_metadata_filter(request.notebook_id, request.filters)

        # 3. Assemble SubQueries and RetrievalPlan
        subqueries: list[SubQuery] = []
        for mode_str in request.modes:
            mode_enum = _MODE_MAP.get(mode_str.lower())
            if mode_enum is None:
                raise UnsupportedError(f"Unsupported retrieval mode: '{mode_str}'")
            subqueries.append(
                SubQuery(
                    query_text=request.query,
                    retrieval_mode=mode_enum,
                    filters=metadata_filter,
                    max_results=request.limit,
                )
            )

        plan = RetrievalPlan(
            intent=RetrievalIntent.FACTUAL,
            sub_queries=tuple(subqueries),
            requires_multi_hop=False,
            requires_multi_doc=False,
        )

        # 4. Multi-Source Retrieval & RRF Fusion
        retriever = MultiSourceRetriever(self._engine.registry, self._engine.embedding_provider)
        fusion_result = await retriever.execute(plan, global_limit=request.limit)

        # 5. Optional Reranking & Result Assembly
        results: list[SearchResultItem] = []
        if request.enable_reranking:
            reranker = RerankingModule(self._engine.registry)
            rerank_result = await reranker.execute(request.query, fusion_result)
            for reranked_item in rerank_result.results:
                chunk = reranked_item.fused_result.chunk
                source_mode = (
                    reranked_item.fused_result.evidence[0].effective_mode.value
                    if reranked_item.fused_result.evidence
                    else "hybrid"
                )
                score = (
                    reranked_item.rerank_evidence.relevance_score
                    if reranked_item.rerank_evidence is not None
                    else reranked_item.fused_result.rrf_score
                )
                results.append(
                    SearchResultItem(
                        chunk_id=chunk.id,
                        document_id=chunk.document_id,
                        version_id=chunk.version_id,
                        text=chunk.text,
                        score=round(score, 6),
                        rank=reranked_item.reranked_rank,
                        retrieval_mode=source_mode,
                        heading_path=list(chunk.heading_path),
                        page_number=chunk.position.page_number,
                        metadata=thaw_metadata(chunk.metadata),
                    )
                )
        else:
            for fused_item in fusion_result.results:
                chunk = fused_item.chunk
                source_mode = (
                    fused_item.evidence[0].effective_mode.value if fused_item.evidence else "hybrid"
                )
                results.append(
                    SearchResultItem(
                        chunk_id=chunk.id,
                        document_id=chunk.document_id,
                        version_id=chunk.version_id,
                        text=chunk.text,
                        score=round(fused_item.rrf_score, 6),
                        rank=fused_item.global_rank,
                        retrieval_mode=source_mode,
                        heading_path=list(chunk.heading_path),
                        page_number=chunk.position.page_number,
                        metadata=thaw_metadata(chunk.metadata),
                    )
                )

        latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))

        return SearchResponse(
            results=results,
            total=len(results),
            latency_ms=latency_ms,
        )

    def _build_metadata_filter(
        self,
        notebook_id: UUID | None,
        filters: QueryFilters | None,
    ) -> MetadataFilter:
        if filters is None:
            return MetadataFilter(notebook_id=notebook_id)

        doc_types: list[DocType] = []
        if filters.doc_type:
            for dt in filters.doc_type:
                try:
                    doc_types.append(DocType(dt.lower()))
                except ValueError as err:
                    raise ContractValidationError(f"Invalid doc_type filter '{dt}'") from err

        return MetadataFilter(
            notebook_id=notebook_id,
            doc_types=tuple(doc_types),
            date_after=filters.date_after,
            date_before=filters.date_before,
            source_ids=tuple(filters.source_ids or ()),
        )
