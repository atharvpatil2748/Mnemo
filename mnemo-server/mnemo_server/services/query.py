"""Query orchestration service coordinating multi-mode retrieval and synthesis."""

from __future__ import annotations

import logging
import re
import time
from uuid import NAMESPACE_URL, UUID, uuid5

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import (
    ContractValidationError,
    NotFoundError,
    TokenCounterInterfaceV1,
    UnsupportedError,
)
from mnemo.models import (
    Chunk,
    DocType,
    MetadataFilter,
    RetrievalIntent,
    RetrievalMode,
    RetrievalPlan,
    SubQuery,
)
from mnemo.retrieval import (
    ContextBuilder,
    GroundedAnswerGenerator,
    MultiSourceRetriever,
    RerankingModule,
)
from mnemo.retrieval.answer import GROUNDED_ANSWER_SYSTEM_PROMPT

from mnemo_server.schemas.query import (
    CitationResponse,
    QueryFilters,
    QueryRequest,
    QueryResponse,
    RetrievalMetadataResponse,
)

_LOGGER = logging.getLogger(__name__)
_MARKER = re.compile(r"\[source:([1-9][0-9]*)\]", flags=re.ASCII)

_MODE_MAP = {
    "dense": RetrievalMode.DENSE,
    "sparse": RetrievalMode.SPARSE,
    "hybrid": RetrievalMode.HYBRID,
}


class QueryService:
    """Coordinates retrieval, reranking, context assembly, and synthesis for queries."""

    def __init__(
        self,
        engine: KnowledgeEngine,
        token_counter: TokenCounterInterfaceV1,
    ) -> None:
        self._engine = engine
        self._token_counter = token_counter

    async def execute_query(self, request: QueryRequest) -> QueryResponse:
        """Execute evidence retrieval and optional grounded answer synthesis."""
        start_time = time.perf_counter()

        # 1. Notebook Scope Validation
        if request.notebook_id is not None:
            notebook = await self._engine.storage.get_notebook(request.notebook_id)
            if notebook is None:
                raise NotFoundError(f"Notebook with id '{request.notebook_id}' not found")

        # 2. Metadata Filter Translation
        metadata_filter = self._build_metadata_filter(
            request.notebook_id, request.retrieval_config.filters
        )

        # 3. Assemble SubQueries and RetrievalPlan
        subqueries: list[SubQuery] = []
        for mode_str in request.retrieval_config.modes:
            mode_enum = _MODE_MAP.get(mode_str.lower())
            if mode_enum is None:
                raise UnsupportedError(f"Unsupported retrieval mode: '{mode_str}'")
            subqueries.append(
                SubQuery(
                    query_text=request.question,
                    retrieval_mode=mode_enum,
                    filters=metadata_filter,
                    max_results=request.retrieval_config.top_k,
                )
            )

        plan = RetrievalPlan(
            intent=RetrievalIntent.SYNTHESIS,
            sub_queries=tuple(subqueries),
            requires_multi_hop=False,
            requires_multi_doc=False,
        )

        # 4. Multi-Source Retrieval & RRF Fusion
        retriever = MultiSourceRetriever(self._engine.registry, self._engine.embedding_provider)
        fusion_result = await retriever.execute(plan, global_limit=request.retrieval_config.top_k)

        # 5. Reranking (Cross-Encoder / RRF Fallback)
        reranker = RerankingModule(self._engine.registry)
        rerank_result = await reranker.execute(request.question, fusion_result)

        # 6. Context Construction
        system_prompt = request.synthesis.system_prompt or GROUNDED_ANSWER_SYSTEM_PROMPT
        context_builder = ContextBuilder(self._engine.registry, self._token_counter)
        context_result = await context_builder.build(
            rerank_result,
            context_budget=request.context_budget,
            system_prompt=system_prompt,
        )

        # 7. Grounded Answer Synthesis & Citations
        citations_response: list[CitationResponse] = []
        answer_text: str | None = None

        if request.synthesis.enabled:
            answer_generator = GroundedAnswerGenerator(self._engine.registry, self._token_counter)
            answer_result = await answer_generator.generate(
                context_result,
                max_output_tokens=request.synthesis.max_response_tokens,
            )
            answer_text = answer_result.answer

            if answer_text:
                marker_numbers = tuple(
                    int(match.group(1)) for match in _MARKER.finditer(answer_text)
                )
                seen_numbers: set[int] = set()
                unique_marker_numbers: list[int] = []
                for num in marker_numbers:
                    if num not in seen_numbers:
                        seen_numbers.add(num)
                        unique_marker_numbers.append(num)

                items_by_source = {item.source_number: item for item in context_result.items}
                for num in unique_marker_numbers:
                    item = items_by_source.get(num)
                    if item is not None:
                        chunk = item.reranked_result.fused_result.chunk
                        doc_title = _runtime_document_title(chunk)

                        citations_response.append(
                            CitationResponse(
                                id=uuid5(NAMESPACE_URL, f"mnemo-citation:{chunk.id}:{num}"),
                                chunk_id=chunk.id,
                                document_title=doc_title,
                                page=chunk.position.page_number,
                                heading_path=list(chunk.heading_path),
                                quote=item.content,
                                confidence=1.0,
                            )
                        )
        else:
            # Evidence-only mode: build citations from retrieved context items
            for item in context_result.items:
                chunk = item.reranked_result.fused_result.chunk
                evidence_score = (
                    item.reranked_result.rerank_evidence.relevance_score
                    if item.reranked_result.rerank_evidence is not None
                    else item.reranked_result.fused_result.rrf_score
                )
                citations_response.append(
                    CitationResponse(
                        id=uuid5(NAMESPACE_URL, f"mnemo-evidence:{chunk.id}"),
                        chunk_id=chunk.id,
                        document_title=_runtime_document_title(chunk),
                        page=chunk.position.page_number,
                        heading_path=list(chunk.heading_path),
                        quote=item.content,
                        confidence=round(evidence_score, 6),
                    )
                )

        latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))
        modes_used = sorted({sq.retrieval_mode.value for sq in plan.sub_queries})

        return QueryResponse(
            answer=answer_text,
            citations=citations_response,
            retrieval_metadata=RetrievalMetadataResponse(
                chunks_retrieved=len(fusion_result.results),
                chunks_used=len(context_result.items),
                retrieval_modes_used=modes_used,
                latency_ms=latency_ms,
            ),
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


def _runtime_document_title(chunk: Chunk) -> str:
    """Return exact-version retrieval title without another storage lookup."""
    title = chunk.metadata.get("document_title")
    return title if isinstance(title, str) and title.strip() else str(chunk.document_id)
