from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import UUID

import pytest
from mnemo.interfaces import IntegrityError
from mnemo.models import (
    AdvancedRetrievalMode,
    DeduplicationPolicy,
    EvidenceRepresentation,
    ExpansionPolicy,
    RankingPolicyV2,
    RetrievalBudgetsV2,
    RetrievalCompleteness,
    RetrievalPlanV2,
    RetrievalScopeV2,
)
from mnemo.retrieval import PartitionedRetrievalServiceV1, RetrievalCursorCodec

NOTEBOOK = UUID(int=1)
DOC_A = UUID(int=2)
DOC_B = UUID(int=3)


def _plan() -> RetrievalPlanV2:
    return RetrievalPlanV2(
        query="cpi",
        mode=AdvancedRetrievalMode.EXHAUSTIVE,
        scope=RetrievalScopeV2(notebook_id=NOTEBOOK, document_ids=(DOC_B, DOC_A)),
        representations=(EvidenceRepresentation.CANONICAL_TEXT,),
        budgets=RetrievalBudgetsV2(
            recall_limit=10,
            expansion_limit=0,
            fusion_limit=10,
            rerank_limit=10,
            result_limit=5,
            max_serialized_bytes=10_000,
            max_content_characters=10_000,
        ),
        expansion_policy=ExpansionPolicy.NONE,
        deduplication_policy=DeduplicationPolicy.AUTHORITATIVE_IDENTITY,
        ranking_policy=RankingPolicyV2.DETERMINISTIC_STORAGE_ORDER,
    )


class FakeRetrieval:
    profile_id = "test"

    def __init__(self) -> None:
        self.calls: list[UUID] = []

    async def execute(self, plan: RetrievalPlanV2, *, cursor: str | None = None):  # type: ignore[no-untyped-def]
        document_id = plan.scope.document_ids[0]
        self.calls.append(document_id)
        return SimpleNamespace(
            snapshot_identity=("a" if document_id == DOC_A else "b") * 64,
            completeness=RetrievalCompleteness.COMPLETE,
            next_cursor=None,
        )


def test_partitions_are_sorted_and_preserve_each_snapshot() -> None:
    retrieval = FakeRetrieval()
    result = asyncio.run(
        PartitionedRetrievalServiceV1(retrieval).execute(_plan(), document_ids=(DOC_B, DOC_A))
    )
    assert retrieval.calls == [DOC_A, DOC_B]
    assert [item.document_id for item in result.partitions] == [DOC_A, DOC_B]
    assert result.completeness is RetrievalCompleteness.COMPLETE
    assert result.next_cursors == {}


def test_partition_truncation_is_not_complete() -> None:
    retrieval = FakeRetrieval()
    original = retrieval.execute

    async def truncated(plan: RetrievalPlanV2, *, cursor: str | None = None):
        value = await original(plan, cursor=cursor)
        if plan.scope.document_ids == (DOC_A,):
            value.completeness = RetrievalCompleteness.TRUNCATED
            value.next_cursor = "opaque"
        return value

    retrieval.execute = truncated  # type: ignore[method-assign]
    codec = RetrievalCursorCodec(b"partition-test-key" * 3)
    result = asyncio.run(
        PartitionedRetrievalServiceV1(retrieval, codec).execute(
            _plan(), document_ids=(DOC_A, DOC_B)
        )
    )
    assert result.completeness is RetrievalCompleteness.TRUNCATED
    assert result.next_cursors == {DOC_A: "opaque"}
    assert result.next_cursor is not None


def test_partition_must_be_in_scope() -> None:
    with pytest.raises(ValueError, match="outside the authorized scope"):
        asyncio.run(
            PartitionedRetrievalServiceV1(FakeRetrieval()).execute(
                _plan(), document_ids=(UUID(int=99),)
            )
        )


def test_aggregate_cursor_binds_query() -> None:
    retrieval = FakeRetrieval()
    original = retrieval.execute

    async def truncated(plan: RetrievalPlanV2, *, cursor: str | None = None):
        value = await original(plan, cursor=cursor)
        value.completeness = RetrievalCompleteness.TRUNCATED
        value.next_cursor = "opaque"
        return value

    retrieval.execute = truncated  # type: ignore[method-assign]
    codec = RetrievalCursorCodec(b"partition-test-key" * 3)
    token = asyncio.run(
        PartitionedRetrievalServiceV1(retrieval, codec).execute(
            _plan(), document_ids=(DOC_A, DOC_B)
        )
    ).next_cursor
    assert token is not None
    changed = _plan().model_copy(update={"query": "different"})
    with pytest.raises(IntegrityError):
        asyncio.run(
            PartitionedRetrievalServiceV1(retrieval, codec).execute(
                changed, document_ids=(DOC_A, DOC_B), cursor=token
            )
        )
