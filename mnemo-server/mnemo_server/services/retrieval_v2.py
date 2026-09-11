"""Shared HTTP/MCP application service for advanced evidence retrieval."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import timedelta
from typing import Any
from uuid import uuid4

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import ContractValidationError, OperationTimeoutError
from mnemo.interfaces.advanced_retrieval import PrincipalAwareAdvancedRetrievalInterfaceV2
from mnemo.models import RetrievalResultSetV1, RetrievalScopeV2, thaw_metadata
from mnemo.retrieval import RetrievalCursorCodec

from mnemo_server.config import ServerConfig
from mnemo_server.schemas.retrieval_v2 import EvidenceSearchRequest, EvidenceSearchResponse
from mnemo_server.services.authorization import (
    AuthorizationOperationV1,
    CentralAuthorizationServiceV1,
    ServerPrincipalV1,
    principal_from_claims,
)

CONTRACT_VERSION = "mnemo.mcp.contract/v2"


def build_retrieval_cursor_codec(config: ServerConfig) -> RetrievalCursorCodec:
    secret = config.delivery_cursor_secret.encode("utf-8")
    if len(secret) < 32:
        secret = hashlib.sha256(secret).digest()
    return RetrievalCursorCodec(
        secret,
        ttl=timedelta(seconds=config.delivery_cursor_ttl_seconds),
        key_id=f"retrieval-{config.delivery_cursor_key_id}",
        verification_keys=tuple(
            (f"retrieval-{key_id}", value.encode("utf-8"))
            for key_id, value in config.delivery_cursor_rotation_keys
        ),
    )


class EvidenceRetrievalApplicationService:
    def __init__(self, engine: KnowledgeEngine, config: ServerConfig) -> None:
        self._engine = engine
        self._config = config

    async def execute(
        self, request: EvidenceSearchRequest, principal: ServerPrincipalV1 | None = None
    ) -> EvidenceSearchResponse:
        principal = principal or principal_from_claims(None)
        plan = request.to_plan(
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
        )
        try:
            if type(self._engine) is KnowledgeEngine:
                await CentralAuthorizationServiceV1(self._engine).authorize_notebook(
                    principal, plan.scope.notebook_id, AuthorizationOperationV1.RETRIEVE
                )
            async with asyncio.timeout(self._config.max_advanced_elapsed_milliseconds / 1000):
                partition_ids = request.partition_document_ids
                if request.all_authorized_documents:
                    if partition_ids:
                        raise ContractValidationError(
                            "all_authorized_documents cannot be combined with "
                            "partition_document_ids"
                        )
                    partition_ids = await self._resolve_authorized_documents(
                        plan.scope.notebook_id, principal
                    )
                if partition_ids:
                    if not plan.scope.document_ids:
                        plan = plan.model_copy(
                            update={
                                "scope": RetrievalScopeV2(
                                    notebook_id=plan.scope.notebook_id,
                                    source_ids=plan.scope.source_ids,
                                    document_ids=partition_ids,
                                    version_ids=plan.scope.version_ids,
                                )
                            }
                        )
                    partitioned = await self._engine.partitioned_retrieval.execute(
                        plan,
                        document_ids=partition_ids,
                        cursors=request.partition_cursors,
                        cursor=request.cursor,
                    )
                    return _partitioned_response(
                        plan.mode.value,
                        plan.scope.model_dump(mode="json"),
                        plan.budgets,
                        partitioned,
                        max_elapsed_milliseconds=self._config.max_advanced_elapsed_milliseconds,
                        requested_k=request.evidence_budget,
                        internal_candidate_pool_k=plan.budgets.rerank_limit,
                    )
                retrieval = self._engine.advanced_retrieval
                if self._config.production_mode:
                    if not principal.authenticated:
                        raise PermissionError("production retrieval requires authentication")
                    if not isinstance(retrieval, PrincipalAwareAdvancedRetrievalInterfaceV2):
                        raise RuntimeError(
                            "production retrieval lacks the principal-aware V2 entry point"
                        )
                    result = await retrieval.execute_authorized(
                        principal=principal,
                        plan=plan,
                        cursor=request.cursor,
                    )
                else:
                    result = await retrieval.execute(plan, cursor=request.cursor)
        except TimeoutError as error:
            raise OperationTimeoutError("advanced retrieval deadline expired") from error
        response = _response(
            plan.mode.value,
            plan.scope.model_dump(mode="json"),
            plan.budgets,
            result,
            max_elapsed_milliseconds=self._config.max_advanced_elapsed_milliseconds,
            requested_k=request.evidence_budget,
            internal_candidate_pool_k=plan.budgets.rerank_limit,
        )
        if (
            len(response.model_dump_json().encode("utf-8"))
            > self._config.max_advanced_response_bytes
        ):
            raise ContractValidationError(
                "advanced retrieval response exceeds the server byte ceiling; "
                "lower evidence_budget or max_serialized_bytes"
            )
        return response

    async def _resolve_authorized_documents(
        self, notebook_id: Any, principal: ServerPrincipalV1
    ) -> tuple[Any, ...]:
        """Enumerate canonical documents and retain only notebook-authorized memberships."""
        documents: list[Any] = []
        cursor: str | None = None
        while len(documents) < 100:
            page = await self._engine.storage.list_documents(
                None, min(100, 100 - len(documents)), cursor
            )
            for document in page.items:
                try:
                    await self._engine.document_scope_resolver.resolve_document_scope(
                        principal,
                        document.document_id,
                        document.current_version_id,
                        notebook_id,
                    )
                except Exception:
                    continue
                else:
                    documents.append(document.document_id)
            if page.next_cursor is None:
                break
            if len(documents) >= 100:
                raise ContractValidationError(
                    "authorized document universe exceeds the bounded partition limit"
                )
            cursor = page.next_cursor
        return tuple(sorted(set(documents), key=str))


def _response(
    mode: str,
    scope: dict[str, Any],
    budgets: Any,
    result: RetrievalResultSetV1,
    *,
    max_elapsed_milliseconds: int,
    requested_k: int,
    internal_candidate_pool_k: int,
) -> EvidenceSearchResponse:
    reports = [
        {
            "representation": report.representation.value,
            "status": report.status.value,
            "examined": report.examined,
            "returned": report.returned,
            "exhausted": report.exhausted,
            "reason_code": report.reason_code,
        }
        for report in result.diagnostics.representation_reports
    ]
    omissions = [
        f"{report['representation']}:{report['reason_code']}"
        for report in reports
        if report["status"] != "searched"
    ]
    items = []
    for candidate in result.results:
        items.append(
            {
                "candidate_id": str(candidate.candidate_id),
                "notebook_id": str(candidate.notebook_id),
                "source_id": str(candidate.source_id),
                "document_id": str(candidate.document_id),
                "version_id": str(candidate.version_id),
                "chunk_id": None if candidate.chunk is None else candidate.chunk.id,
                "occurrence_id": (
                    None if candidate.occurrence_id is None else str(candidate.occurrence_id)
                ),
                "derivation_id": (
                    None if candidate.derivation_id is None else str(candidate.derivation_id)
                ),
                "representation": candidate.representation.value,
                "document_title": candidate.document_title,
                "content": candidate.content,
                "locator": thaw_metadata(candidate.locator),
                "retrieval_paths": [
                    {
                        "path": path.path,
                        "source_rank": path.source_rank,
                        "source_score": path.source_score,
                        "title_match": path.title_match,
                        "parent_promoted": path.parent_promoted,
                    }
                    for path in candidate.paths
                ],
                "fused_score": candidate.fused_score,
                "rank": candidate.final_rank,
            }
        )
    next_actions: list[dict[str, Any]] = []
    if result.next_cursor is not None:
        next_actions.append(
            {
                "tool": "search_evidence",
                "reason": "Continue the same exhaustive evidence traversal.",
                "arguments_from_result": ["next_cursor"],
                "pass_cursor_unchanged": True,
                "stop_condition": "next_cursor is null",
            }
        )
    for candidate in result.results:
        if candidate.occurrence_id is not None:
            next_actions.append(
                {
                    "tool": "get_asset",
                    "reason": "Retrieve the authorized original asset for this occurrence.",
                    "arguments_from_result": [
                        "notebook_id",
                        "document_id",
                        "version_id",
                        "occurrence_id",
                    ],
                }
            )
            if candidate.derivation_id is not None:
                next_actions.append(
                    {
                        "tool": "get_image_analysis",
                        "reason": (
                            "Retrieve the existing derived OCR/Vision interpretation; "
                            "it is not the original asset."
                        ),
                        "arguments_from_result": ["notebook_id", "occurrence_id", "derivation_id"],
                    }
                )
    return EvidenceSearchResponse(
        schema_version=CONTRACT_VERSION,
        operation="search_evidence",
        request_id=uuid4(),
        mode=mode,
        scope=scope,
        items=items,
        completeness=result.completeness.value,
        coverage={
            "exhaustive": mode == "exhaustive",
            "match_semantics": _match_semantics(mode, reports),
            "snapshot_identity": result.snapshot_identity,
            "examined": result.examined_count,
            "returned": result.returned_count,
            "representations": reports,
        },
        omissions=omissions,
        limits={
            **budgets.model_dump(mode="json"),
            "requested_k": requested_k,
            "internal_reranker_candidate_pool_k": internal_candidate_pool_k,
            "max_elapsed_milliseconds": max_elapsed_milliseconds,
        },
        next_cursor=result.next_cursor,
        recommended_next_actions=next_actions,
        diagnostics={
            "ordering_policy": result.ordering_policy.value,
            "query_fingerprint": result.query_fingerprint,
            "truncated": result.diagnostics.truncated,
            "truncation_reason": result.diagnostics.truncation_reason,
            "elapsed_milliseconds": result.diagnostics.elapsed_milliseconds,
        },
    )


def _partitioned_response(
    mode: str,
    scope: dict[str, Any],
    budgets: Any,
    result: Any,
    *,
    max_elapsed_milliseconds: int,
    requested_k: int,
    internal_candidate_pool_k: int,
) -> EvidenceSearchResponse:
    """Serialize partitioned results without flattening provenance."""
    partition_payload: list[dict[str, Any]] = []
    all_items: list[dict[str, Any]] = []
    for partition in result.partitions:
        child = _response(
            mode,
            {**scope, "document_ids": [str(partition.document_id)]},
            budgets,
            partition.result,
            max_elapsed_milliseconds=max_elapsed_milliseconds,
            requested_k=requested_k,
            internal_candidate_pool_k=internal_candidate_pool_k,
        )
        partition_payload.append(
            {
                "document_id": str(partition.document_id),
                "completeness": child.completeness,
                "coverage": child.coverage,
                "items": child.items,
                "next_cursor": child.next_cursor,
                "omissions": child.omissions,
            }
        )
        all_items.extend(child.items)
    next_actions = (
        [
            {
                "tool": "search_evidence",
                "reason": "Continue each incomplete document partition with its opaque cursor.",
                "arguments_from_result": ["partitions[].next_cursor"],
                "stop_condition": "all partition next_cursor values are null",
            }
        ]
        if result.next_cursors
        else []
    )
    return EvidenceSearchResponse(
        schema_version=CONTRACT_VERSION,
        operation="search_evidence",
        request_id=uuid4(),
        mode=mode,
        scope=scope,
        items=all_items,
        completeness=result.completeness.value,
        coverage={
            "exhaustive": mode == "exhaustive",
            "partitioned": True,
            "partitions": [str(p.document_id) for p in result.partitions],
            "evaluated_partitions": len(result.partitions),
            "snapshot_identity": result.snapshot_identity,
            "returned": len(all_items),
        },
        omissions=list(result.omissions),
        limits={
            **budgets.model_dump(mode="json"),
            "requested_k": requested_k,
            "internal_reranker_candidate_pool_k": internal_candidate_pool_k,
            "max_elapsed_milliseconds": max_elapsed_milliseconds,
        },
        next_cursor=result.next_cursor,
        recommended_next_actions=next_actions,
        diagnostics={"partition_cursors": {str(k): v for k, v in result.next_cursors.items()}},
        partitions=partition_payload,
    )


def _match_semantics(mode: str, reports: list[dict[str, Any]]) -> str:
    representations = {report["representation"] for report in reports}
    if "visual_vector" in representations:
        return "shared_visual_vector_similarity_with_representation_rank_fusion"
    if representations.intersection({"ocr_text", "vision_analysis", "asset_metadata"}):
        return "authorized_derived_text_and_asset_metadata_rank_fusion"
    return (
        "canonical_sqlite_fts_term_disjunction"
        if mode == "exhaustive"
        else "bounded_relevance_ranking"
    )
