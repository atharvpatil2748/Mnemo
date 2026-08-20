"""Streaming query service executing retrieval, token streaming, and citation resolution."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import AsyncIterator
from uuid import NAMESPACE_URL, UUID, uuid5

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import (
    ContractValidationError,
    Message,
    MessageRole,
    NotFoundError,
    TokenCounterInterfaceV1,
    UnsupportedError,
)
from mnemo.models import (
    ContextBuildResult,
    DocType,
    MetadataFilter,
    RetrievalIntent,
    RetrievalMode,
    RetrievalPlan,
    SubQuery,
)
from mnemo.retrieval import (
    ContextBuilder,
    MultiSourceRetriever,
    RerankingModule,
)
from mnemo.retrieval.answer import (
    GROUNDED_ANSWER_SYSTEM_PROMPT,
    classify_prompt_template,
)

from mnemo_server.schemas.query import (
    CitationResponse,
    QueryFilters,
    QueryRequest,
    RetrievalMetadataResponse,
)
from mnemo_server.schemas.streaming import (
    ChunkRetrievedData,
    CitationsReadyData,
    DoneData,
    StreamEvent,
    StreamEventType,
    SynthesisTokenData,
)
from mnemo_server.services.query import _runtime_document_title

_LOGGER = logging.getLogger(__name__)
_MARKER = re.compile(r"\[source:([1-9][0-9]*)\]", flags=re.ASCII)

_MODE_MAP = {
    "dense": RetrievalMode.DENSE,
    "sparse": RetrievalMode.SPARSE,
    "hybrid": RetrievalMode.HYBRID,
}


class StreamingQueryService:
    """Orchestrates streaming retrieval, synthesis token forwarding, and citations."""

    def __init__(
        self,
        engine: KnowledgeEngine,
        token_counter: TokenCounterInterfaceV1,
    ) -> None:
        self._engine = engine
        self._token_counter = token_counter

    async def stream_query(self, request: QueryRequest) -> AsyncIterator[StreamEvent]:
        """Stream the 5-event protocol (retrieval_start, chunk, token, citations, done)."""
        start_time = time.perf_counter()

        # 1. Event: retrieval_start
        yield StreamEvent(event=StreamEventType.RETRIEVAL_START)

        # 2. Notebook Scope Validation
        if request.notebook_id is not None:
            notebook = await self._engine.storage.get_notebook(request.notebook_id)
            if notebook is None:
                raise NotFoundError(f"Notebook with id '{request.notebook_id}' not found")

        # 3. Metadata Filter Translation
        metadata_filter = self._build_metadata_filter(
            request.notebook_id, request.retrieval_config.filters
        )

        # 4. Assemble SubQueries and RetrievalPlan
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

        # 5. Multi-Source Retrieval & RRF Fusion
        retriever = MultiSourceRetriever(self._engine.registry, self._engine.embedding_provider)
        fusion_result = await retriever.execute(plan, global_limit=request.retrieval_config.top_k)

        # 6. Event: chunk_retrieved for each candidate
        for item in fusion_result.results:
            yield StreamEvent(
                event=StreamEventType.CHUNK_RETRIEVED,
                data=ChunkRetrievedData(
                    chunk_id=item.chunk.id,
                    score=item.rrf_score,
                    document_id=item.chunk.document_id,
                ),
            )

        # 7. Reranking
        reranker = RerankingModule(self._engine.registry)
        rerank_result = await reranker.execute(request.question, fusion_result)

        # 8. Context Construction
        base_system_prompt = request.synthesis.system_prompt or GROUNDED_ANSWER_SYSTEM_PROMPT
        context_builder = ContextBuilder(self._engine.registry, self._token_counter)
        context_result = await context_builder.build(
            rerank_result,
            context_budget=request.context_budget,
            system_prompt=base_system_prompt,
        )

        # 9. Grounded Answer Synthesis & Token Streaming
        citations_response: list[CitationResponse] = []
        answer_text: str | None = None

        if request.synthesis.enabled:
            synthesizer = self._engine.registry.resolve_llm("synthesizer")
            if synthesizer is not None and context_result.items:
                system_prompt = request.synthesis.system_prompt or classify_prompt_template(
                    request.question, context_result
                )
                messages = (
                    Message(role=MessageRole.USER, content=context_result.rendered_context),
                )

                accumulated_tokens: list[str] = []
                async for token in synthesizer.stream(
                    system=system_prompt,
                    messages=messages,
                    max_tokens=request.synthesis.max_response_tokens,
                ):
                    accumulated_tokens.append(token)
                    yield StreamEvent(
                        event=StreamEventType.SYNTHESIS_TOKEN,
                        data=SynthesisTokenData(token=token),
                    )

                answer_text = "".join(accumulated_tokens)

                # Extract and resolve citations from accumulated text
                if answer_text:
                    citations_response = await self._resolve_citations(answer_text, context_result)
            elif not context_result.items:
                no_context_msg = "The available context is insufficient to answer this question."
                for token in no_context_msg.split(" "):
                    yield StreamEvent(
                        event=StreamEventType.SYNTHESIS_TOKEN,
                        data=SynthesisTokenData(token=token + " "),
                    )
                answer_text = no_context_msg
        else:
            # Evidence-only mode: citations from context items
            citations_response = self._build_evidence_citations(context_result)

        # 10. Event: citations_ready
        yield StreamEvent(
            event=StreamEventType.CITATIONS_READY,
            data=CitationsReadyData(citations=citations_response),
        )

        # 11. Event: done
        latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))
        modes_used = sorted({sq.retrieval_mode.value for sq in plan.sub_queries})

        retrieval_metadata = RetrievalMetadataResponse(
            chunks_retrieved=len(fusion_result.results),
            chunks_used=len(context_result.items),
            retrieval_modes_used=modes_used,
            latency_ms=latency_ms,
        )

        yield StreamEvent(
            event=StreamEventType.DONE,
            data=DoneData(
                retrieval_metadata=retrieval_metadata,
                answer=answer_text,
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

    async def _resolve_citations(
        self,
        answer_text: str,
        context_result: ContextBuildResult,
    ) -> list[CitationResponse]:
        """Extract [source:N] citations and resolve document metadata."""
        marker_numbers = tuple(int(match.group(1)) for match in _MARKER.finditer(answer_text))
        seen_numbers: set[int] = set()
        unique_marker_numbers: list[int] = []
        for num in marker_numbers:
            if num not in seen_numbers:
                seen_numbers.add(num)
                unique_marker_numbers.append(num)

        items_by_source = {item.source_number: item for item in context_result.items}
        citations_response: list[CitationResponse] = []

        for num in unique_marker_numbers:
            item = items_by_source.get(num)
            if item is not None:
                chunk = item.reranked_result.fused_result.chunk
                doc_title = _runtime_document_title(chunk)
                if doc_title == str(chunk.document_id):
                    doc = await self._engine.storage.get_document(chunk.document_id)
                    if doc is not None:
                        exact = next(
                            (v for v in doc.versions if v.version_id == chunk.version_id), None
                        )
                        if exact is not None and exact.metadata.title:
                            doc_title = exact.metadata.title

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

        return citations_response

    def _build_evidence_citations(
        self, context_result: ContextBuildResult
    ) -> list[CitationResponse]:
        """Build citations for evidence-only retrieval queries."""
        citations_response: list[CitationResponse] = []
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
        return citations_response
