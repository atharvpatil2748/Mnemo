"""Search orchestration service coordinating global and scoped full-text and vector search."""

from __future__ import annotations

import logging
import time
from uuid import UUID

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import (
    ContractValidationError,
    NotFoundError,
    PrincipalContextV1,
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
from mnemo_server.services.authorization import CentralAuthorizationServiceV1
from mnemo_server.services.source_metadata import (
    AuthorizedSourceMetadataResolverV1,
    SourceMetadataReferenceV1,
)

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

    async def execute_search(
        self, request: SearchRequest, principal: PrincipalContextV1 | None = None
    ) -> SearchResponse:
        """Execute global or notebook-scoped multi-mode search and return ranked results."""
        if principal is not None and not principal.authenticated:
            raise PermissionError("authenticated search principal is required")
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
        authorized_scopes: dict[tuple[UUID, UUID], UUID] = {}
        if principal is not None:
            fusion_result, authorized_scopes = await CentralAuthorizationServiceV1(
                self._engine
            ).filter_fused_candidates(principal, fusion_result, request.notebook_id)

        # 5. Optional Reranking
        rerank_result = None
        if request.enable_reranking:
            reranker = RerankingModule(self._engine.registry)
            rerank_result = await reranker.execute(request.query, fusion_result)

        # Resolve parent notebook IDs for all retrieved chunks
        candidate_chunks = (
            [r.fused_result.chunk for r in rerank_result.results]
            if rerank_result is not None
            else [r.chunk for r in fusion_result.results]
        )
        identities = {(c.document_id, c.version_id) for c in candidate_chunks}
        doc_to_notebook: dict[tuple[UUID, UUID], UUID | None] = dict(authorized_scopes)
        if principal is None:
            for doc_id, version_id in identities:
                try:
                    resolved = await self._engine.document_scope_resolver.resolve_document_scope(
                        PrincipalContextV1(UUID(int=0), False),
                        doc_id,
                        version_id,
                        request.notebook_id,
                    )
                    doc_to_notebook[(doc_id, version_id)] = resolved.notebook_id
                except Exception:
                    doc_to_notebook[(doc_id, version_id)] = None

        # 6. Result Assembly
        results: list[SearchResultItem] = []
        if rerank_result is not None:
            for reranked_item in rerank_result.results:
                chunk = reranked_item.fused_result.chunk
                identity = (chunk.document_id, chunk.version_id)
                if principal is not None and identity not in doc_to_notebook:
                    continue
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
                        notebook_id=doc_to_notebook.get(identity, request.notebook_id),
                        document_id=chunk.document_id,
                        version_id=chunk.version_id,
                        text=chunk.text,
                        score=round(score, 6),
                        rank=len(results) + 1
                        if principal is not None
                        else reranked_item.reranked_rank,
                        retrieval_mode=source_mode,
                        heading_path=list(chunk.heading_path),
                        page_number=chunk.position.page_number,
                        page_start=chunk.position.page_start,
                        page_end=chunk.position.page_end,
                        metadata=thaw_metadata(chunk.metadata),
                    )
                )
        else:
            for fused_item in fusion_result.results:
                chunk = fused_item.chunk
                identity = (chunk.document_id, chunk.version_id)
                if principal is not None and identity not in doc_to_notebook:
                    continue
                source_mode = (
                    fused_item.evidence[0].effective_mode.value if fused_item.evidence else "hybrid"
                )
                results.append(
                    SearchResultItem(
                        chunk_id=chunk.id,
                        notebook_id=doc_to_notebook.get(identity, request.notebook_id),
                        document_id=chunk.document_id,
                        version_id=chunk.version_id,
                        text=chunk.text,
                        score=round(fused_item.rrf_score, 6),
                        rank=len(results) + 1 if principal is not None else fused_item.global_rank,
                        retrieval_mode=source_mode,
                        heading_path=list(chunk.heading_path),
                        page_number=chunk.position.page_number,
                        page_start=chunk.position.page_start,
                        page_end=chunk.position.page_end,
                        metadata=thaw_metadata(chunk.metadata),
                    )
                )

        if principal is not None and results and type(self._engine) is KnowledgeEngine:
            references = tuple(
                SourceMetadataReferenceV1(
                    notebook_id=item.notebook_id,
                    document_id=item.document_id,
                    version_id=item.version_id,
                )
                for item in results
                if item.notebook_id is not None
            )
            envelopes = await AuthorizedSourceMetadataResolverV1(self._engine).resolve_many(
                principal, references
            )
            results = [
                item.model_copy(
                    update={
                        "source_metadata": envelopes[
                            SourceMetadataReferenceV1(
                                notebook_id=item.notebook_id,
                                document_id=item.document_id,
                                version_id=item.version_id,
                            )
                        ].model_dump(mode="json")
                    }
                )
                if item.notebook_id is not None
                else item
                for item in results
            ]

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
