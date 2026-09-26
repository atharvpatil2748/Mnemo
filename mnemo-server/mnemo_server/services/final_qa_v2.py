"""Shared Final-QA V2 application service for HTTP and MCP."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import (
    ContractValidationError,
    DependencyUnavailableError,
    FinalQAExecutionStoreV2,
    IntegrityError,
    NotFoundError,
    OperationTimeoutError,
    StorageError,
)
from mnemo.interfaces.advanced_retrieval import PrincipalAwareAdvancedRetrievalInterfaceV2
from mnemo.models import FrozenMetadata
from mnemo.models.advanced_retrieval import RetrievalCompleteness
from mnemo.models.final_qa_execution import FinalQAExecutionSnapshotPhase, FinalQAExecutionState
from mnemo.models.multimodal import (
    FinalQARequestV2,
    MultimodalRetrievalDiagnosticsV2,
    MultimodalRetrievalResultV2,
    final_qa_v2_execution_id,
)
from mnemo.retrieval import candidates_from_retrieval

from ..schemas.final_qa_v2 import (
    FinalQAPublicationPolicyV2,
    FinalQAV2CitationResponse,
    FinalQAV2RequestBody,
    FinalQAV2Response,
)
from ..schemas.retrieval_v2 import EvidenceSearchRequest
from .authorization import (
    AuthorizationOperationV1,
    CentralAuthorizationServiceV1,
    ServerPrincipalV1,
)
from .source_metadata import (
    AuthorizedSourceMetadataResolverV1,
    SourceMetadataReferenceV1,
)


@dataclass(slots=True)
class _ExecutionProgress:
    authorized: bool = False
    store: FinalQAExecutionStoreV2 | None = None


_TIMEOUT_RECONCILIATION_SECONDS = 5.0


class FinalQAV2ApplicationService:
    """Compile, authorize, retrieve, and delegate to the canonical V2 orchestrator."""

    def __init__(self, engine: KnowledgeEngine, server_config: Any) -> None:
        self._engine = engine
        self._config = server_config

    async def execute(
        self,
        notebook_id: UUID,
        body: FinalQAV2RequestBody,
        principal: ServerPrincipalV1,
    ) -> FinalQAV2Response:
        if self._config.production_mode and not principal.authenticated:
            raise PermissionError("authenticated Final-QA V2 principal is required")
        progress = _ExecutionProgress()
        try:
            async with asyncio.timeout(self._config.max_final_qa_elapsed_milliseconds / 1000):
                return await self._execute_once(notebook_id, body, principal, progress)
        except (TimeoutError, OperationTimeoutError) as error:
            details = (
                FrozenMetadata(
                    {"execution_id": str(final_qa_v2_execution_id(body.assistant_turn_id))}
                )
                if progress.authorized
                else FrozenMetadata()
            )
            if progress.authorized:
                try:
                    async with asyncio.timeout(_TIMEOUT_RECONCILIATION_SECONDS):
                        await self._record_timeout(body, principal, progress.store)
                except (
                    TimeoutError,
                    StorageError,
                    DependencyUnavailableError,
                ) as reconciliation_error:
                    raise DependencyUnavailableError(
                        "Final-QA V2 timeout state could not be confirmed",
                        details=details,
                    ) from reconciliation_error
            raise OperationTimeoutError(
                "Final-QA V2 operation exceeded deadline", details=details
            ) from error

    async def _execute_once(
        self,
        notebook_id: UUID,
        body: FinalQAV2RequestBody,
        principal: ServerPrincipalV1,
        progress: _ExecutionProgress,
    ) -> FinalQAV2Response:
        if body.notebook_id != notebook_id:
            raise ContractValidationError("request notebook does not match transport scope")
        if body.evidence_request_or_snapshot.scope.notebook_id != notebook_id:
            raise ContractValidationError("evidence scope notebook does not match path")
        authorization = CentralAuthorizationServiceV1(self._engine)
        await authorization.authorize_notebook(
            principal, notebook_id, AuthorizationOperationV1.FINAL_QA
        )
        progress.authorized = True
        store = (
            self._engine.final_qa_v2_execution_store
            if self._config.production_mode or type(self._engine) is KnowledgeEngine
            else self._engine.storage
        )
        if not isinstance(store, FinalQAExecutionStoreV2):
            raise DependencyUnavailableError("Final-QA V2 execution persistence is unavailable")
        if self._config.production_mode and cast(object, store) is cast(
            object, self._engine.storage
        ):
            raise DependencyUnavailableError(
                "production Final-QA operational persistence must be separate from corpus storage"
            )
        progress.store = store
        profile = getattr(self._engine.final_qa_v2, "capabilities", None)
        if not callable(profile):
            raise DependencyUnavailableError("Final-QA V2 provider capabilities are unavailable")
        capabilities = profile()
        if body.provider_profile != capabilities.profile:
            raise ContractValidationError("requested Final-QA provider profile is unavailable")
        result = (
            await self._retrieval_result_authorized(
                body.question, body.evidence_request_or_snapshot, principal
            )
            if self._config.production_mode
            else await self._retrieval_result(body.question, body.evidence_request_or_snapshot)
        )
        unavailable = tuple(
            item.kind.value
            for item in result.candidates
            if capabilities.state_for(item.kind).value != "supported"
        )
        if unavailable:
            raise DependencyUnavailableError(
                "requested Final-QA evidence modalities are unavailable: "
                + ", ".join(sorted(set(unavailable)))
            )
        if (
            body.publication_policy is FinalQAPublicationPolicyV2.REQUIRE_COMPLETE
            and result.completeness
            not in {RetrievalCompleteness.COMPLETE, RetrievalCompleteness.EMPTY}
        ):
            raise ContractValidationError("complete evidence is required before publication")
        # Resolve presentation metadata before any persisted Final-QA execution.
        # A missing/mismatched association therefore fails without a partial publication.
        citation_metadata: dict[UUID, dict[str, Any]] = {}
        if self._config.production_mode and type(self._engine) is KnowledgeEngine:
            references = tuple(
                SourceMetadataReferenceV1(
                    notebook_id=item.notebook_id,
                    source_id=item.source_id,
                    document_id=item.document_id,
                    version_id=item.version_id,
                )
                for item in result.candidates
            )
            resolved = await AuthorizedSourceMetadataResolverV1(self._engine).resolve_many(
                principal, references
            )
            citation_metadata = {
                item.candidate_id: resolved[reference].model_dump(mode="json")
                for item, reference in zip(result.candidates, references, strict=True)
            }
        request = FinalQARequestV2(
            actor_id=principal.actor_id,
            notebook_id=notebook_id,
            session_id=body.session_id,
            user_turn_id=body.user_turn_id,
            assistant_turn_id=body.assistant_turn_id,
            query=body.question,
            retrieval_result=result,
            context_budgets=body.context_budgets,
            system_prompt=(
                "Answer using only the supplied evidence and cite sources as "
                "[source:1], [source:2]."
            ),
            max_output_tokens=body.max_output_tokens,
        )
        existing = await store.get_final_qa_v2_execution(body.assistant_turn_id)
        if existing is not None:
            await authorization.authorize_notebook(
                principal, notebook_id, AuthorizationOperationV1.REPLAY
            )
        try:
            final = await self._engine.final_qa_v2.execute(request)
        except IntegrityError as error:
            if self._config.production_mode and error.message in {
                "multimodal evidence authorization denied",
                "multimodal evidence notebook scope mismatch",
                "Final-QA V2 replay authorization scope changed",
            }:
                raise NotFoundError("authorized resource was not found") from error
            raise
        snapshot = await store.get_final_qa_v2_snapshot(
            final.execution_id, FinalQAExecutionSnapshotPhase.PUBLISHED
        )
        return FinalQAV2Response(
            contract_version="mnemo.final-qa-v2/1",
            execution_id=final.execution_id,
            replayed=existing is not None and existing.state is FinalQAExecutionState.PUBLISHED,
            status=final.status.value,
            answer=final.answer,
            citations=tuple(
                _citation(item, citation_metadata.get(item.candidate.candidate_id))
                for item in final.citations
            ),
            completeness=final.context_result.completeness.value,
            coverage={
                "items": len(final.context_result.items),
                "snapshot_identity": result.snapshot_identity,
            },
            publication_status="published" if final.answer is not None else "no_context",
            snapshot_identity=None if snapshot is None else snapshot.payload_hash,
            omissions=tuple(item.reason.value for item in final.context_result.omissions),
            recommended_next_actions=(),
        )

    @staticmethod
    async def _record_timeout(
        body: FinalQAV2RequestBody,
        principal: ServerPrincipalV1,
        store: FinalQAExecutionStoreV2 | None,
    ) -> None:
        if store is None:
            return
        execution = await store.get_final_qa_v2_execution(body.assistant_turn_id)
        if execution is None or (
            execution.actor_id != principal.actor_id or execution.notebook_id != body.notebook_id
        ):
            return
        if execution.state in {
            FinalQAExecutionState.PUBLISHED,
            FinalQAExecutionState.REJECTED_CITATION_COMPLIANCE,
            FinalQAExecutionState.TIMED_OUT,
        }:
            return
        if execution.state is FinalQAExecutionState.ASSISTANT_PUBLISHED:
            published = await store.get_final_qa_v2_snapshot(
                execution.execution_id, FinalQAExecutionSnapshotPhase.PUBLISHED
            )
            if published is not None:
                transitioned = await store.transition_final_qa_v2_execution(
                    execution.execution_id,
                    FinalQAExecutionState.ASSISTANT_PUBLISHED,
                    FinalQAExecutionState.PUBLISHED,
                )
                if transitioned:
                    return
        transitioned = await store.transition_final_qa_v2_execution(
            execution.execution_id,
            execution.state,
            FinalQAExecutionState.TIMED_OUT,
            failure_classification="operation_timeout",
        )
        if not transitioned:
            current = await store.get_final_qa_v2_execution(body.assistant_turn_id)
            if current is None or current.state not in {
                FinalQAExecutionState.PUBLISHED,
                FinalQAExecutionState.REJECTED_CITATION_COMPLIANCE,
                FinalQAExecutionState.TIMED_OUT,
            }:
                raise DependencyUnavailableError("Final-QA V2 timeout state could not be confirmed")

    async def _retrieval_result(
        self, question: str, request: EvidenceSearchRequest
    ) -> MultimodalRetrievalResultV2:
        try:
            async with asyncio.timeout(self._config.max_advanced_elapsed_milliseconds / 1000):
                raw = await self._engine.advanced_retrieval.execute(
                    request.to_plan(
                        max_candidate_budget=self._config.max_advanced_candidate_budget,
                        max_evidence_budget=self._config.max_advanced_evidence_budget,
                        max_response_bytes=self._config.max_advanced_response_bytes,
                        max_content_characters=self._config.max_advanced_content_characters,
                        max_rerank_candidates=self._config.production_rerank_candidate_limit,
                        production_candidate_pool_k=(
                            self._config.production_rerank_candidate_limit
                            if self._config.production_mode
                            else None
                        ),
                    ),
                    cursor=request.cursor,
                )
        except TimeoutError as error:
            raise OperationTimeoutError("Final-QA evidence retrieval exceeded deadline") from error
        return _multimodal_result(question, raw)

    async def _retrieval_result_authorized(
        self,
        question: str,
        request: EvidenceSearchRequest,
        principal: ServerPrincipalV1,
    ) -> MultimodalRetrievalResultV2:
        if not principal.authenticated:
            raise PermissionError("production FinalQA requires authentication")
        retrieval = self._engine.advanced_retrieval
        if not isinstance(retrieval, PrincipalAwareAdvancedRetrievalInterfaceV2):
            raise DependencyUnavailableError(
                "production retrieval lacks the principal-aware V2 entry point"
            )
        try:
            async with asyncio.timeout(self._config.max_advanced_elapsed_milliseconds / 1000):
                raw = await retrieval.execute_authorized(
                    principal=principal,
                    plan=request.to_plan(
                        max_candidate_budget=self._config.max_advanced_candidate_budget,
                        max_evidence_budget=self._config.max_advanced_evidence_budget,
                        max_response_bytes=self._config.max_advanced_response_bytes,
                        max_content_characters=self._config.max_advanced_content_characters,
                        max_rerank_candidates=self._config.production_rerank_candidate_limit,
                        production_candidate_pool_k=self._config.production_rerank_candidate_limit,
                    ),
                    cursor=request.cursor,
                )
        except TimeoutError as error:
            raise OperationTimeoutError("Final-QA evidence retrieval exceeded deadline") from error
        return _multimodal_result(question, raw)


def _multimodal_result(question: str, raw: Any) -> MultimodalRetrievalResultV2:
    candidates = candidates_from_retrieval(raw)
    counts = {item.kind.value: 0 for item in candidates}
    for item in candidates:
        counts[item.kind.value] += 1
    diagnostics = MultimodalRetrievalDiagnosticsV2(
        recalled=raw.examined_count,
        deduplicated=len(candidates),
        fused=len(candidates),
        reranked=len(candidates),
        returned=len(candidates),
        modality_counts=FrozenMetadata(counts),
        omitted_reasons=FrozenMetadata(),
        elapsed_milliseconds=raw.diagnostics.elapsed_milliseconds,
    )
    return MultimodalRetrievalResultV2(
        query=question,
        query_fingerprint=raw.query_fingerprint,
        snapshot_identity=raw.snapshot_identity,
        completeness=raw.completeness,
        candidates=candidates,
        diagnostics=diagnostics,
    )


def _citation(
    item: Any, source_metadata: dict[str, Any] | None = None
) -> FinalQAV2CitationResponse:
    candidate = item.candidate
    return FinalQAV2CitationResponse(
        citation_id=item.citation_id,
        source_number=item.source_number,
        notebook_id=candidate.notebook_id,
        source_id=candidate.source_id,
        document_id=candidate.document_id,
        version_id=candidate.version_id,
        chunk_id=candidate.chunk_id,
        occurrence_id=candidate.occurrence_id,
        derivation_id=candidate.derivation_id,
        generation_id=candidate.generation_id,
        kind=candidate.kind.value,
        authority=candidate.authority.value,
        document_title=(
            source_metadata["document_title"]
            if source_metadata is not None
            else item.document_title
        ),
        source_metadata=source_metadata,
    )
