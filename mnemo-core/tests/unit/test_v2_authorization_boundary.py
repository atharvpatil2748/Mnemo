"""Narrow V2 authorization-boundary ordering tests."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from mnemo.interfaces.scope import PrincipalContextV1
from mnemo.models.advanced_retrieval import (
    AdvancedRetrievalMode,
    EvidenceRepresentation,
    RankingPolicyV2,
    RetrievalBudgetsV2,
    RetrievalPlanV2,
    RetrievalScopeV2,
)
from mnemo.models.multilingual import LanguageCode
from mnemo.models.v2_retrieval_authorization import (
    V2ActiveRuntimeBindingV1,
    V2RetrievalAuthorizationDecisionV1,
)
from mnemo.retrieval.full_multilingual_v2 import FullMultilingualRetrievalApplicationV2

DIGEST = "a" * 64


def _plan(notebook_id: UUID) -> RetrievalPlanV2:
    return RetrievalPlanV2(
        query="governed query",
        mode=AdvancedRetrievalMode.RANKED,
        scope=RetrievalScopeV2(notebook_id=notebook_id),
        representations=(EvidenceRepresentation.MULTILINGUAL_TEXT,),
        budgets=RetrievalBudgetsV2(
            recall_limit=10,
            expansion_limit=0,
            fusion_limit=10,
            rerank_limit=10,
            result_limit=5,
            max_serialized_bytes=10000,
            max_content_characters=1000,
        ),
        ranking_policy=RankingPolicyV2.SOURCE_RANK_FUSION,
    )


def _decision(
    principal: PrincipalContextV1, plan: RetrievalPlanV2
) -> V2RetrievalAuthorizationDecisionV1:
    return V2RetrievalAuthorizationDecisionV1(
        decision_id=uuid4(),
        principal_actor_id=principal.actor_id,
        operation="retrieve",
        retrieval_scope=plan.scope,
        positional_scope=plan.position,
        runtime_binding=V2ActiveRuntimeBindingV1(
            alias_set_digest=DIGEST,
            generation_ids=tuple(uuid4() for _ in range(4)),
            profile_fingerprint=DIGEST,
            vector_space_identity=DIGEST,
            database_identity=DIGEST,
            build_run_id=uuid4(),
            admission_policy_identity="fixture-admission/1",
        ),
        authorization_policy_identity="central-authorization-v1-plus-v2/1",
        authorization_policy_revision="1",
        request_fingerprint=DIGEST,
        issued_at="2026-09-01T00:00:00Z",
        required_provenance_evidence=("language-evidence-reference-v3",),
    )


class _DeniedRetrievalAuthorizer:
    def __init__(self) -> None:
        self.called = 0

    async def authorize_v2_retrieval(self, **_: object) -> V2RetrievalAuthorizationDecisionV1:
        self.called += 1
        raise PermissionError("OPERATION_UNAUTHORIZED")


class _SourceSpy:
    def __init__(self) -> None:
        self.calls = 0

    async def retrieve(self, **_: object) -> tuple[object, ...]:
        self.calls += 1
        return ()

    async def retrieve_authorized_multilingual_sparse(self, **_: object) -> tuple[object, ...]:
        self.calls += 1
        return ()


class _EvidenceAuthorizer:
    async def authorize_language_evidence_v3(self, **_: object) -> object:
        raise AssertionError("evidence authorization must not follow a denied operation")


class _Builder:
    async def build(self, **_: object) -> object:
        raise AssertionError("candidate construction must not follow a denied operation")


class _Reranker:
    async def score_candidates(self, **_: object) -> tuple[object, ...]:
        raise AssertionError("reranking must not follow a denied operation")


class _Admission:
    def permits(self, *, language: LanguageCode, operation: str) -> bool:
        return bool(language.value and operation)


def _application(
    *, retrieval_authorizer: _DeniedRetrievalAuthorizer, dense: _SourceSpy, sparse: _SourceSpy
) -> FullMultilingualRetrievalApplicationV2:
    return FullMultilingualRetrievalApplicationV2(
        dense=dense,
        sparse=sparse,
        retrieval_authorizer=retrieval_authorizer,
        candidate_builder=_Builder(),
        reranker=_Reranker(),
        admission=_Admission(),
    )


def test_denied_operation_prevents_dense_sparse_candidate_and_reranker_work() -> None:
    principal = PrincipalContextV1(actor_id=uuid4(), authenticated=True)
    plan = _plan(uuid4())
    authorizer = _DeniedRetrievalAuthorizer()
    dense = _SourceSpy()
    sparse = _SourceSpy()

    with pytest.raises(PermissionError, match="OPERATION_UNAUTHORIZED"):
        asyncio.run(
            _application(
                retrieval_authorizer=authorizer,
                dense=dense,
                sparse=sparse,
            ).retrieve(
                principal=principal,
                plan=plan,
                query_language=LanguageCode("und"),
            )
        )

    assert authorizer.called == 1
    assert dense.calls == 0
    assert sparse.calls == 0


def test_unauthenticated_principal_fails_before_authorization_or_enumeration() -> None:
    principal = PrincipalContextV1(actor_id=uuid4(), authenticated=False)
    plan = _plan(uuid4())
    authorizer = _DeniedRetrievalAuthorizer()
    dense = _SourceSpy()
    sparse = _SourceSpy()

    with pytest.raises(PermissionError, match="server-derived authenticated principal"):
        asyncio.run(
            _application(
                retrieval_authorizer=authorizer,
                dense=dense,
                sparse=sparse,
            ).retrieve(
                principal=principal,
                plan=plan,
                query_language=LanguageCode("und"),
            )
        )

    assert authorizer.called == 0
    assert dense.calls == 0
    assert sparse.calls == 0


def test_v2_authorization_decision_is_immutable_and_rejects_scope_expansion() -> None:
    principal = PrincipalContextV1(actor_id=uuid4(), authenticated=True)
    plan = _plan(uuid4())
    decision = _decision(principal, plan)

    with pytest.raises(PermissionError, match="scope mismatch"):
        decision.permits(
            scope=RetrievalScopeV2(notebook_id=plan.scope.notebook_id, source_ids=(uuid4(),)),
            position=plan.position,
            runtime_binding=decision.runtime_binding,
        )
