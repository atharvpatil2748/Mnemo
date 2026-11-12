"""ADR-0055 thin adapter over the composed FinalQAInterfaceV1."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import (
    ConflictError,
    ContractValidationError,
    DependencyUnavailableError,
    NotFoundError,
    PrincipalContextV1,
)
from mnemo.models import (
    DocumentContextLabel,
    FinalQARequest,
    MetadataFilter,
    RetrievalFusionResult,
    TurnRole,
)
from mnemo.retrieval.answer import GROUNDED_ANSWER_SYSTEM_PROMPT
from mnemo.retrieval.final_qa import FinalQAOrchestrator

from ..schemas.final_qa import FinalQARequestBody, FinalQAResponse
from ..schemas.query import QueryFilters
from ..schemas.sessions import CitationItemResponse
from .authorization import AuthorizationOperationV1, CentralAuthorizationServiceV1
from .authorized_scope import AuthorizedNotebookScope, AuthorizedNotebookScopeResolver
from .scope_authority import SQLiteNotebookScopeAuthority


class _ACLFinalQAPolicy:
    def __init__(
        self,
        engine: KnowledgeEngine,
        principal: PrincipalContextV1,
        authority: SQLiteNotebookScopeAuthority,
        scope: AuthorizedNotebookScope,
        body: FinalQARequestBody,
        *,
        replay_admitted: bool,
    ) -> None:
        self.engine = engine
        self.principal = principal
        self.authority = authority
        self.scope = scope
        self.body = body
        self.replay_admitted = replay_admitted
        self.documents: dict[tuple[UUID, UUID], UUID] = {}

    async def check(self) -> None:
        self.authority.verify_final_qa_v1_execution(
            assistant_turn_id=self.body.assistant_turn_id,
            actor_id=self.principal.actor_id,
            notebook_id=self.scope.notebook_id,
            session_id=self.body.session_id,
            user_turn_id=self.body.user_turn_id,
            acl_revision=self.scope.membership_revision,
        )
        await AuthorizedNotebookScopeResolver(self.engine.storage, self.authority).revalidate(
            self.principal, (self.scope,)
        )
        for (document_id, version_id), notebook_id in self.documents.items():
            await CentralAuthorizationServiceV1(self.engine).authorize_document(
                self.principal,
                notebook_id,
                document_id,
                version_id,
                AuthorizationOperationV1.FINAL_QA,
            )

    async def check_replay(self) -> None:
        if not self.replay_admitted:
            raise NotFoundError("authorized resource was not found")
        documents = self.authority.verify_final_qa_v1_execution(
            assistant_turn_id=self.body.assistant_turn_id,
            actor_id=self.principal.actor_id,
            notebook_id=self.scope.notebook_id,
            session_id=self.body.session_id,
            user_turn_id=self.body.user_turn_id,
            acl_revision=self.scope.membership_revision,
            require_documents=True,
        )
        if documents is None:
            raise NotFoundError("authorized resource was not found")
        self.documents = {identity: self.scope.notebook_id for identity in documents}
        await self.check()

    async def filter_fusion(self, fusion: RetrievalFusionResult) -> RetrievalFusionResult:
        permitted, self.documents = await CentralAuthorizationServiceV1(
            self.engine
        ).filter_fused_candidates(self.principal, fusion, self.scope.notebook_id)
        await self.check()
        self.authority.bind_final_qa_v1_documents(
            assistant_turn_id=self.body.assistant_turn_id,
            actor_id=self.principal.actor_id,
            notebook_id=self.scope.notebook_id,
            session_id=self.body.session_id,
            user_turn_id=self.body.user_turn_id,
            acl_revision=self.scope.membership_revision,
            documents=tuple(sorted(self.documents)),
        )
        return permitted

    @contextmanager
    def publication_lease(self) -> Iterator[int]:
        with self.authority.owner_write_lease(
            actor_id=self.principal.actor_id, notebook_id=self.scope.notebook_id
        ) as revision:
            if revision != self.scope.membership_revision:
                raise NotFoundError("authorized resource was not found")
            yield revision


class FinalQAService:
    def __init__(self, engine: KnowledgeEngine) -> None:
        self._engine = engine

    async def execute(
        self,
        notebook_id: UUID,
        body: FinalQARequestBody,
        principal: PrincipalContextV1 | None = None,
    ) -> FinalQAResponse:
        authority = getattr(self._engine, "server_scope_authority", None)
        policy: _ACLFinalQAPolicy | None = None
        if authority is not None:
            if not isinstance(authority, SQLiteNotebookScopeAuthority):
                raise DependencyUnavailableError(
                    "FinalQA V1 lacks a principal-aware execution boundary"
                )
            if principal is None or not principal.authenticated:
                raise PermissionError("trusted membership identity is unavailable")
            if not isinstance(self._engine.final_qa, FinalQAOrchestrator):
                raise DependencyUnavailableError("authorized Final-QA V1 execution is unavailable")
            scope = (
                await AuthorizedNotebookScopeResolver(self._engine.storage, authority).resolve(
                    principal, (notebook_id,)
                )
            )[0]
            if not authority.permits(principal.actor_id, notebook_id, operation="write"):
                raise NotFoundError("authorized resource was not found")
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
        labels, titles = await self._labels(notebook_id, principal)
        execution_store = self._engine.storage
        previous = getattr(execution_store, "get_final_qa_execution", None)
        existing = await previous(body.assistant_turn_id) if callable(previous) else None
        if authority is not None:
            if not isinstance(authority, SQLiteNotebookScopeAuthority) or principal is None:
                raise PermissionError("trusted membership identity is unavailable")
            if existing is None:
                authority.bind_final_qa_v1_execution(
                    assistant_turn_id=body.assistant_turn_id,
                    actor_id=principal.actor_id,
                    notebook_id=notebook_id,
                    session_id=body.session_id,
                    user_turn_id=body.user_turn_id,
                    acl_revision=scope.membership_revision,
                )
            policy = _ACLFinalQAPolicy(
                self._engine,
                principal,
                authority,
                scope,
                body,
                replay_admitted=existing is not None,
            )
            await policy.check()
        final_request = FinalQARequest(
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
        result = (
            await self._engine.final_qa.execute_authorized(final_request, policy)
            if policy is not None and isinstance(self._engine.final_qa, FinalQAOrchestrator)
            else await self._engine.final_qa.execute(final_request)
        )
        if policy is not None:
            for citation in result.citations:
                await CentralAuthorizationServiceV1(self._engine).authorize_document(
                    policy.principal,
                    notebook_id,
                    citation.document_id,
                    citation.version_id,
                    AuthorizationOperationV1.FINAL_QA,
                )
            await policy.check()
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
        self, notebook_id: UUID, principal: PrincipalContextV1 | None = None
    ) -> tuple[tuple[DocumentContextLabel, ...], tuple[str, ...]]:
        sources = await self._engine.storage.list_sources(notebook_id, limit=100, cursor=None)
        labels: list[DocumentContextLabel] = []
        titles: list[str] = []
        for source in sources.items:
            if principal is not None and source.notebook_id != notebook_id:
                raise NotFoundError("authorized resource was not found")
            document = await self._engine.storage.get_document(source.document_id)
            if document is None:
                raise NotFoundError(f"Document {source.document_id} not found")
            for version in document.versions:
                if principal is not None:
                    await CentralAuthorizationServiceV1(self._engine).authorize_document(
                        principal,
                        notebook_id,
                        document.document_id,
                        version.version_id,
                        AuthorizationOperationV1.FINAL_QA,
                    )
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
