"""ADR-0055 thin adapter over the composed FinalQAInterfaceV1."""

from __future__ import annotations

from uuid import UUID

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import ConflictError, ContractValidationError, NotFoundError
from mnemo.models import DocumentContextLabel, FinalQARequest, MetadataFilter, TurnRole
from mnemo.retrieval.answer import GROUNDED_ANSWER_SYSTEM_PROMPT

from ..schemas.final_qa import FinalQARequestBody, FinalQAResponse
from ..schemas.query import QueryFilters
from ..schemas.sessions import CitationItemResponse


class FinalQAService:
    def __init__(self, engine: KnowledgeEngine) -> None:
        self._engine = engine

    async def execute(self, notebook_id: UUID, body: FinalQARequestBody) -> FinalQAResponse:
        notebook = await self._engine.storage.get_notebook(notebook_id)
        if notebook is None:
            raise NotFoundError(f"Notebook {notebook_id} not found")
        session = await self._engine.storage.get_session(body.session_id)
        if session is None:
            raise NotFoundError(f"Session {body.session_id} not found")
        if session.notebook_id != notebook_id:
            raise ConflictError("session does not belong to notebook")
        user = next((turn for turn in session.turns if turn.turn_id == body.user_turn_id), None)
        if user is None:
            raise NotFoundError(f"User turn {body.user_turn_id} not found")
        if user.role is not TurnRole.USER or not session.turns:
            raise ContractValidationError("user turn must be the final persisted query turn")
        tail = session.turns[user.sequence + 1 :]
        if tail and not (
            len(tail) == 1
            and tail[0].role is TurnRole.ASSISTANT
            and tail[0].turn_id == body.assistant_turn_id
        ):
            raise ContractValidationError("session contains turns after the requested query")
        labels, titles = await self._labels(notebook_id)
        execution_store = self._engine.storage
        previous = getattr(execution_store, "get_final_qa_execution", None)
        existing = await previous(body.assistant_turn_id) if callable(previous) else None
        result = await self._engine.final_qa.execute(
            FinalQARequest(
                query=user.content,
                metadata_filter=_filters(notebook_id, body.filters),
                global_limit=body.global_limit,
                context_budget=body.context_budget,
                system_prompt=GROUNDED_ANSWER_SYSTEM_PROMPT,
                max_output_tokens=body.max_output_tokens,
                session_id=body.session_id,
                user_turn_id=body.user_turn_id,
                assistant_turn_id=body.assistant_turn_id,
                table_of_contents=body.table_of_contents,
                source_titles=titles,
                document_labels=labels,
            )
        )
        return FinalQAResponse(
            status=result.status.value,
            execution="replay" if existing is not None else "new",
            answer=result.answer,
            citations=[
                CitationItemResponse(
                    citation_id=item.citation_id,
                    turn_id=item.turn_id,
                    source_number=item.source_number,
                    chunk_id=item.chunk_id,
                    document_id=item.document_id,
                    version_id=item.version_id,
                    document_title=item.document_title,
                    verbatim_quote=item.verbatim_quote,
                    page_number=item.page_number,
                    heading_path=list(item.heading_path),
                    created_at=item.created_at,
                )
                for item in result.citations
            ],
        )

    async def _labels(
        self, notebook_id: UUID
    ) -> tuple[tuple[DocumentContextLabel, ...], tuple[str, ...]]:
        sources = await self._engine.storage.list_sources(notebook_id, limit=100, cursor=None)
        labels: list[DocumentContextLabel] = []
        titles: list[str] = []
        for source in sources.items:
            document = await self._engine.storage.get_document(source.document_id)
            if document is None:
                raise NotFoundError(f"Document {source.document_id} not found")
            for version in document.versions:
                if version.metadata.title:
                    labels.append(
                        DocumentContextLabel(
                            document_id=document.document_id,
                            version_id=version.version_id,
                            title=version.metadata.title,
                        )
                    )
                    titles.append(version.metadata.title)
        return tuple(labels), tuple(dict.fromkeys(titles))


def _filters(notebook_id: UUID, filters: QueryFilters | None) -> MetadataFilter:
    if filters is None:
        return MetadataFilter(notebook_id=notebook_id)
    from mnemo.models import DocType

    try:
        doc_types = tuple(DocType(value.lower()) for value in filters.doc_type or ())
    except ValueError as error:
        raise ContractValidationError("invalid document type filter") from error
    return MetadataFilter(
        notebook_id=notebook_id,
        doc_types=doc_types,
        date_after=filters.date_after,
        date_before=filters.date_before,
        source_ids=tuple(filters.source_ids or ()),
    )
