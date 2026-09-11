"""Shared authorized Full Multilingual V2 retrieval/fusion/reranking application path."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.interfaces.multilingual import (
    MultilingualCandidateRerankerV3,
    RerankerCandidateBuilderProtocolV1,
    V2RetrievalAuthorizerV1,
)
from mnemo.interfaces.scope import PrincipalContextV1
from mnemo.models.advanced_retrieval import RetrievalPlanV2
from mnemo.models.multilingual import (
    LanguageCode,
    LanguageEvidenceReferenceV3,
    MultilingualRerankScoreV2,
)
from mnemo.models.multilingual_reranking import MultilingualRerankCandidateV3
from mnemo.models.v2_retrieval_authorization import V2RetrievalAuthorizationDecisionV1
from mnemo.retrieval.multilingual_dense_v2 import MultilingualDenseMatchV2

RRF_K_V2 = 60
PASS_THROUGH_RERANKER_ID = "v2-pass-through-reranker-v1"


class PassThroughV2RerankerV1:
    """Explicit pre-activation mode; preserves fused ordering and loads no model."""

    reranker_id = PASS_THROUGH_RERANKER_ID
    mode = "PASS_THROUGH"

    async def score_candidates(
        self,
        *,
        query: str,
        candidates: tuple[MultilingualRerankCandidateV3, ...],
    ) -> tuple[MultilingualRerankScoreV2, ...]:
        del query
        return tuple(
            MultilingualRerankScoreV2(
                candidate_id=item.candidate_id,
                score=0.0,
                model=PASS_THROUGH_RERANKER_ID,
                revision="1",
                preprocessing="identity-preserve-fused-order",
            )
            for item in candidates
        )


@runtime_checkable
class AuthorizedMultilingualDenseSourceV2(Protocol):  # pragma: no cover
    async def retrieve(
        self,
        *,
        decision: V2RetrievalAuthorizationDecisionV1,
        query: str,
        query_language: LanguageCode,
        limit: int,
    ) -> tuple[MultilingualDenseMatchV2, ...]: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualSparseMatchV2:
    source: LanguageEvidenceReferenceV3
    score: float | None
    rank: int

    def __post_init__(self) -> None:
        if self.score is not None and not math.isfinite(self.score):
            raise ValueError("sparse score must be finite")
        if self.rank < 1 or self.rank > 1000:
            raise ValueError("sparse rank exceeds governed bounds")


@runtime_checkable
class AuthorizedMultilingualSparseSourceV2(Protocol):  # pragma: no cover
    async def retrieve_authorized_multilingual_sparse(
        self,
        *,
        decision: V2RetrievalAuthorizationDecisionV1,
        plan: RetrievalPlanV2,
        limit: int,
    ) -> tuple[MultilingualSparseMatchV2, ...]: ...


@runtime_checkable
class MultilingualOperationAdmissionV2(Protocol):  # pragma: no cover
    def permits(self, *, language: LanguageCode, operation: str) -> bool: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualV2RetrievalCandidate:
    candidate: MultilingualRerankCandidateV3
    fused_score: float
    reranker_score: float | None
    source_paths: tuple[str, ...]
    final_rank: int
    authorization_decision: V2RetrievalAuthorizationDecisionV1

    def __post_init__(self) -> None:
        if not math.isfinite(self.fused_score):
            raise ValueError("fused score must be finite")
        if self.reranker_score is not None and not math.isfinite(self.reranker_score):
            raise ValueError("reranker score must be finite")
        if not self.source_paths or len(set(self.source_paths)) != len(self.source_paths):
            raise ValueError("retrieval candidate requires unique source paths")
        if self.final_rank < 1 or self.final_rank > 200:
            raise ValueError("final rank exceeds governed bounds")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualV2ApplicationResult:
    candidates: tuple[MultilingualV2RetrievalCandidate, ...]
    completeness: str
    omissions: tuple[str, ...]
    dense_examined: int
    sparse_examined: int
    reranked_count: int

    def __post_init__(self) -> None:
        if self.completeness not in {"complete", "partial", "empty"}:
            raise ValueError("invalid multilingual V2 completeness")
        if self.completeness == "complete" and self.omissions:
            raise ValueError("complete V2 result cannot contain omissions")
        if min(self.dense_examined, self.sparse_examined, self.reranked_count) < 0:
            raise ValueError("retrieval diagnostic counts must be non-negative")


class FullMultilingualRetrievalApplicationV2:
    """One shared path for KnowledgeEngine, transports, and V2 evaluation."""

    application_service_id = "mnemo.full-multilingual-retrieval-application/2"

    def __init__(
        self,
        *,
        dense: AuthorizedMultilingualDenseSourceV2,
        sparse: AuthorizedMultilingualSparseSourceV2,
        retrieval_authorizer: V2RetrievalAuthorizerV1,
        candidate_builder: RerankerCandidateBuilderProtocolV1,
        reranker: MultilingualCandidateRerankerV3,
        admission: MultilingualOperationAdmissionV2,
    ) -> None:
        if not isinstance(dense, AuthorizedMultilingualDenseSourceV2):
            raise TypeError("dense source must be the authorized V2 implementation")
        if not isinstance(sparse, AuthorizedMultilingualSparseSourceV2):
            raise TypeError("sparse source must implement the authorized V2 protocol")
        if not isinstance(retrieval_authorizer, V2RetrievalAuthorizerV1):
            raise TypeError("retrieval authorizer must issue bounded V2 decisions")
        if not isinstance(candidate_builder, RerankerCandidateBuilderProtocolV1):
            raise TypeError("candidate builder must implement the governed shared contract")
        if not isinstance(reranker, MultilingualCandidateRerankerV3):
            raise TypeError("reranker must implement the public V3 protocol")
        if not isinstance(admission, MultilingualOperationAdmissionV2):
            raise TypeError("language admission must implement the operation-scoped contract")
        self._dense = dense
        self._sparse = sparse
        self._retrieval_authorizer = retrieval_authorizer
        self._candidate_builder = candidate_builder
        self._reranker = reranker
        self._admission = admission

    async def retrieve(
        self,
        *,
        principal: PrincipalContextV1,
        plan: RetrievalPlanV2,
        query_language: LanguageCode,
    ) -> MultilingualV2ApplicationResult:
        if not principal.authenticated:
            raise PermissionError("V2 retrieval requires a server-derived authenticated principal")
        decision = await self._retrieval_authorizer.authorize_v2_retrieval(
            principal=principal,
            plan=plan,
        )
        _validate_decision_for_plan(decision, principal, plan)
        for operation in ("dense_retrieval", "sparse_retrieval", "reranking"):
            if not self._admission.permits(language=query_language, operation=operation):
                raise LookupError(f"query language is not operationally admitted for {operation}")
        omissions: list[str] = []
        dense_matches: tuple[MultilingualDenseMatchV2, ...] = ()
        sparse_matches: tuple[MultilingualSparseMatchV2, ...] = ()
        try:
            dense_matches = await self._dense.retrieve(
                decision=decision,
                query=plan.query,
                query_language=query_language,
                limit=plan.budgets.recall_limit,
            )
        except (LookupError, RuntimeError, ValueError) as error:
            omissions.append(f"dense_unavailable:{type(error).__name__}")
        try:
            sparse_matches = await self._sparse.retrieve_authorized_multilingual_sparse(
                decision=decision,
                plan=plan,
                limit=plan.budgets.recall_limit,
            )
        except (LookupError, RuntimeError, ValueError) as error:
            omissions.append(f"sparse_unavailable:{type(error).__name__}")
        if not dense_matches and not sparse_matches and omissions:
            raise RuntimeError("all Full Multilingual V2 retrieval sources are unavailable")
        fused: dict[str, tuple[LanguageEvidenceReferenceV3, float, set[str]]] = {}
        for dense_item in dense_matches:
            _merge_fused(
                fused,
                source=dense_item.embedding.source,
                rank=dense_item.rank,
                path="dense",
            )
        for sparse_item in sparse_matches:
            _merge_fused(
                fused,
                source=sparse_item.source,
                rank=sparse_item.rank,
                path="sparse",
            )
        ordered = sorted(
            fused.values(),
            key=lambda value: (-value[1], value[0].identity_digest),
        )[: plan.budgets.fusion_limit]
        built: list[tuple[MultilingualRerankCandidateV3, float, tuple[str, ...]]] = []
        for ordinal, (source, fused_score, paths) in enumerate(
            ordered[: plan.budgets.rerank_limit]
        ):
            candidate = await self._candidate_builder.build(
                query=plan.query,
                source=source,
                decision=decision,
                input_ordinal=ordinal,
                retrieval_paths=tuple(sorted(paths)),
            )
            built.append((candidate, fused_score, tuple(sorted(paths))))
        scores_by_id: dict[UUID, float] = {}
        if built:
            try:
                scores = await self._reranker.score_candidates(
                    query=plan.query,
                    candidates=tuple(item[0] for item in built),
                )
                scores_by_id = {item.candidate_id: item.score for item in scores}
                if len(scores_by_id) != len(built):
                    raise RuntimeError("reranker returned incomplete candidate coverage")
            except (LookupError, RuntimeError, ValueError) as error:
                omissions.append(f"reranker_unavailable:{type(error).__name__}")
        if scores_by_id:
            built.sort(
                key=lambda item: (
                    -scores_by_id[item[0].candidate_id],
                    item[0].input_ordinal,
                    str(item[0].candidate_id),
                )
            )
        else:
            built.sort(
                key=lambda item: (
                    -item[1],
                    item[0].input_ordinal,
                    str(item[0].candidate_id),
                )
            )
        limited = built[: plan.budgets.result_limit]
        results = tuple(
            MultilingualV2RetrievalCandidate(
                candidate=candidate,
                fused_score=fused_score,
                reranker_score=scores_by_id.get(candidate.candidate_id),
                source_paths=paths,
                final_rank=index,
                authorization_decision=decision,
            )
            for index, (candidate, fused_score, paths) in enumerate(limited, 1)
        )
        return MultilingualV2ApplicationResult(
            candidates=results,
            completeness=("partial" if omissions else "complete") if results else "empty",
            omissions=tuple(sorted(omissions)),
            dense_examined=len(dense_matches),
            sparse_examined=len(sparse_matches),
            reranked_count=len(scores_by_id),
        )


def _merge_fused(
    fused: dict[str, tuple[LanguageEvidenceReferenceV3, float, set[str]]],
    *,
    source: LanguageEvidenceReferenceV3,
    rank: int,
    path: str,
) -> None:
    digest = source.identity_digest
    previous = fused.get(digest, (source, 0.0, set()))
    if previous[0] != source:
        raise RuntimeError("retrieval fusion identity collision")
    fused[digest] = (
        source,
        previous[1] + 1.0 / (RRF_K_V2 + rank),
        previous[2] | {path},
    )


def _validate_decision_for_plan(
    decision: V2RetrievalAuthorizationDecisionV1,
    principal: PrincipalContextV1,
    plan: RetrievalPlanV2,
) -> None:
    if decision.principal_actor_id != principal.actor_id:
        raise PermissionError("V2 authorization decision principal mismatch")
    decision.permits(
        scope=plan.scope,
        position=plan.position,
        runtime_binding=decision.runtime_binding,
    )
