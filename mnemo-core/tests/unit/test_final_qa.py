"""Focused ADR-0046/ADR-0047 final-QA tests."""

from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from mnemo.interfaces import (
    ConflictError,
    ContractValidationError,
    FinalQAInterfaceV1,
    IntegrityError,
    StorageInterfaceV1,
    UnsupportedError,
)
from mnemo.models import (
    CitationResolutionResult,
    CitationResolutionStatus,
    ContextEmptyReason,
    DocType,
    DocumentContextLabel,
    FinalQARequest,
    FinalQAStatus,
    MetadataFilter,
    RetrievalPlan,
    Session,
    Turn,
    TurnRole,
    final_qa_request_fingerprint,
)
from mnemo.models.final_qa_execution import (
    FINAL_QA_EXECUTION_CONTRACT_VERSION,
    FinalQAExecution,
    FinalQAExecutionSnapshot,
    FinalQAExecutionSnapshotPhase,
    FinalQAExecutionState,
)
from mnemo.retrieval import FinalQAOrchestrator
from mnemo.retrieval.final_qa_snapshot import SNAPSHOT_SCHEMA_VERSION
from test_citation_engine import _answer, _chunks, _context, _no_context

pytestmark = pytest.mark.anyio

_SESSION = UUID("40000000-0000-4000-8000-000000000001")
_USER = UUID("40000000-0000-4000-8000-000000000002")
_ASSISTANT = UUID("40000000-0000-4000-8000-000000000003")
_NOW = datetime(2026, 8, 13, 18, tzinfo=UTC)


class _Clock:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> datetime:
        self.calls += 1
        return _NOW + timedelta(seconds=1)


class _Stage:
    def __init__(self, name: str, result: object, calls: list[str]) -> None:
        self.name, self.result, self.calls = name, result, calls
        self.arguments: tuple[tuple[object, ...], dict[str, object]] | None = None

    async def plan(self, *args: object, **kwargs: object) -> object:
        self.calls.append(self.name)
        self.arguments = args, kwargs
        return self.result

    async def execute(self, *args: object, **kwargs: object) -> object:
        self.calls.append(self.name)
        self.arguments = args, kwargs
        return self.result

    async def build(self, *args: object, **kwargs: object) -> object:
        self.calls.append(self.name)
        self.arguments = args, kwargs
        return self.result

    async def generate(self, *args: object, **kwargs: object) -> object:
        self.calls.append(self.name)
        self.arguments = args, kwargs
        return self.result


class _PersistedAnswerStage(_Stage):
    def __init__(
        self, result: object, calls: list[str], *, retry_result: object | None = None
    ) -> None:
        super().__init__("answer", result, calls)
        self.retry_result = retry_result if retry_result is not None else result

    def final_qa_execution_descriptor(self) -> tuple[str, str, dict[str, int | str], str]:
        return "test-provider", "test-model", {"temperature": "fixed"}, "test/tokenizer"

    async def regenerate_for_citation(self, *args: object, **kwargs: object) -> object:
        self.calls.append("retry")
        self.arguments = args, kwargs
        return self.retry_result


class _ExecutionStore:
    def __init__(self) -> None:
        self.executions: dict[UUID, FinalQAExecution] = {}
        self.snapshots: dict[
            tuple[UUID, FinalQAExecutionSnapshotPhase], FinalQAExecutionSnapshot
        ] = {}
        self.events: list[str] = []

    async def create_final_qa_execution(self, execution: FinalQAExecution) -> bool:
        self.events.append("claim")
        if execution.assistant_turn_id in self.executions:
            return False
        self.executions[execution.assistant_turn_id] = execution
        return True

    async def get_final_qa_execution(self, assistant_turn_id: UUID) -> FinalQAExecution | None:
        self.events.append("lookup")
        return self.executions.get(assistant_turn_id)

    async def put_final_qa_execution_snapshot(self, snapshot: FinalQAExecutionSnapshot) -> None:
        self.events.append(f"snapshot:{snapshot.phase}")
        key = snapshot.execution_id, snapshot.phase
        if key in self.snapshots:
            raise ConflictError("immutable execution snapshot already exists")
        self.snapshots[key] = snapshot

    async def get_final_qa_execution_snapshot(
        self, execution_id: UUID, phase: FinalQAExecutionSnapshotPhase
    ) -> FinalQAExecutionSnapshot | None:
        self.events.append(f"get_snapshot:{phase}")
        return self.snapshots.get((execution_id, phase))

    async def transition_final_qa_execution(
        self,
        execution_id: UUID,
        expected: FinalQAExecutionState,
        target: FinalQAExecutionState,
        *,
        retry_count: int | None = None,
        failure_classification: str | None = None,
    ) -> bool:
        self.events.append(f"transition:{expected}:{target}")
        assistant_id = next(
            key for key, value in self.executions.items() if value.execution_id == execution_id
        )
        current = self.executions[assistant_id]
        if current.state is not expected:
            return False
        self.executions[assistant_id] = FinalQAExecution(
            **{
                **{field: getattr(current, field) for field in current.__dataclass_fields__},
                "state": target,
                "retry_count": current.retry_count if retry_count is None else retry_count,
                "failure_classification": failure_classification,
                "updated_at": _NOW,
                "completed_at": _NOW
                if target
                in (
                    FinalQAExecutionState.PUBLISHED,
                    FinalQAExecutionState.REJECTED_CITATION_COMPLIANCE,
                )
                else None,
            }
        )
        return True


class _Citation:
    def __init__(self, status: CitationResolutionStatus, calls: list[str]) -> None:
        self.status, self.calls = status, calls
        self.arguments: tuple[object, object] | None = None
        self.result: CitationResolutionResult | None = None

    async def resolve_and_persist(
        self, answer: object, *, assistant_turn: object, document_labels: object
    ) -> CitationResolutionResult:
        self.calls.append("citation")
        self.arguments = assistant_turn, document_labels
        self.result = CitationResolutionResult(
            answer_result=answer,  # type: ignore[arg-type]
            assistant_turn=assistant_turn,  # type: ignore[arg-type]
            status=self.status,
            citations=(),
            persisted=False,
        )
        return self.result


def _request(**changes: object) -> FinalQARequest:
    values = {
        "query": "  What   is duty? ",
        "metadata_filter": MetadataFilter(),
        "global_limit": 10,
        "context_budget": 1000,
        "system_prompt": "Grounded context",
        "max_output_tokens": 100,
        "session_id": _SESSION,
        "user_turn_id": _USER,
        "assistant_turn_id": _ASSISTANT,
    }
    values.update(changes)
    return FinalQARequest(**values)  # type: ignore[arg-type]


def _session(*, assistant: Turn | None = None) -> Session:
    user = Turn(
        turn_id=_USER,
        session_id=_SESSION,
        sequence=0,
        role=TurnRole.USER,
        content="What is duty?",
        created_at=_NOW,
    )
    return Session(
        session_id=_SESSION,
        notebook_id=UUID("40000000-0000-4000-8000-000000000004"),
        created_at=_NOW,
        updated_at=assistant.created_at if assistant else _NOW,
        turns=(user,) if assistant is None else (user, assistant),
    )


def _storage(session: Session) -> Mock:
    storage = Mock(spec=StorageInterfaceV1)
    storage.get_session = AsyncMock(return_value=session)
    storage.append_turn = AsyncMock()
    return storage


def _orchestrator(
    *,
    answer_text: str = "Grounded [source:1]",
    citation_status: CitationResolutionStatus = CitationResolutionStatus.UNMARKED,
    empty: ContextEmptyReason | None = None,
    multi_hop: bool = False,
    storage: Mock | None = None,
    clock: _Clock | None = None,
) -> tuple[FinalQAOrchestrator, list[str], Mock, _Clock, _Citation]:
    calls: list[str] = []
    context = _context(_chunks(1)) if empty is None else _no_context(empty).context_result
    rerank = context.rerank_result
    plan = RetrievalPlan(
        intent=rerank.fusion_result.plan.intent,
        sub_queries=rerank.fusion_result.plan.sub_queries,
        requires_multi_hop=multi_hop,
        requires_multi_doc=False,
    )
    answer = _answer(answer_text, context=context) if empty is None else _no_context(empty)
    active_storage = storage or _storage(_session())
    active_clock = clock or _Clock()
    citation = _Citation(
        CitationResolutionStatus.NO_CONTEXT if empty is not None else citation_status,
        calls,
    )
    orchestrator = FinalQAOrchestrator(
        _Stage("planner", plan, calls),
        _Stage("fusion", rerank.fusion_result, calls),
        _Stage("reranker", rerank, calls),
        _Stage("context", context, calls),
        _Stage("answer", answer, calls),
        citation,
        active_storage,
        active_clock,
    )
    return orchestrator, calls, active_storage, active_clock, citation


def _persisted_orchestrator(
    *,
    first: str = "Grounded [source:1]",
    retry: str | None = None,
    storage: Mock | None = None,
    execution_store: _ExecutionStore | None = None,
) -> tuple[FinalQAOrchestrator, list[str], Mock, _ExecutionStore, _Citation]:
    calls: list[str] = []
    context = _context(_chunks(1))
    plan = context.rerank_result.fusion_result.plan
    active_storage = storage or _storage(_session())
    store = execution_store or _ExecutionStore()
    citation = _Citation(CitationResolutionStatus.UNMARKED, calls)
    orchestrator = FinalQAOrchestrator(
        _Stage("planner", plan, calls),
        _Stage("fusion", context.rerank_result.fusion_result, calls),
        _Stage("reranker", context.rerank_result, calls),
        _Stage("context", context, calls),
        _PersistedAnswerStage(
            _answer(first, context=context),
            calls,
            retry_result=_answer(retry or first, context=context),
        ),
        citation,
        active_storage,
        _Clock(),
        execution_store=store,
    )
    return orchestrator, calls, active_storage, store, citation


def test_request_is_normalized_validated_and_immutable() -> None:
    request = _request()
    assert request.query == "What is duty?"
    assert isinstance(FinalQAOrchestrator.execute, object)
    with pytest.raises(FrozenInstanceError):
        request.query = "changed"  # type: ignore[misc]
    for name, value in (
        ("global_limit", 0),
        ("context_budget", 1_000_001),
        ("max_output_tokens", 0),
    ):
        with pytest.raises(ValueError):
            _request(**{name: value})
    with pytest.raises(TypeError):
        _request(metadata_filter=object())
    with pytest.raises(ValueError):
        _request(query="   ")


def test_request_rejects_invalid_collections_and_duplicate_labels() -> None:
    with pytest.raises(TypeError):
        _request(global_limit=True)
    with pytest.raises(TypeError):
        _request(table_of_contents=["chapter"])  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        _request(source_titles=("",))
    with pytest.raises(TypeError):
        _request(document_labels=(object(),))
    label = DocumentContextLabel(
        document_id=UUID("40000000-0000-4000-8000-000000000005"),
        version_id=UUID("40000000-0000-4000-8000-000000000006"),
        title="Title",
    )
    with pytest.raises(ValueError):
        _request(document_labels=(label, label))


async def test_exact_stage_order_turn_append_and_unmarked_result() -> None:
    orchestrator, calls, storage, clock, citation = _orchestrator()
    assert isinstance(orchestrator, FinalQAInterfaceV1)
    result = await orchestrator.execute(_request())
    assert calls == ["planner", "fusion", "reranker", "context", "answer", "citation"]
    assert result.status is FinalQAStatus.UNMARKED
    assert result.citation_result is citation.result
    assert result.answer == "Grounded [source:1]"
    storage.append_turn.assert_awaited_once()
    turn = storage.append_turn.await_args.args[1]
    assert (turn.turn_id, turn.sequence, turn.role, turn.created_at) == (
        _ASSISTANT,
        1,
        TurnRole.ASSISTANT,
        _NOW + timedelta(seconds=1),
    )
    assert citation.arguments is not None and citation.arguments[0] is turn
    assert clock.calls == 1


async def test_no_context_has_no_clock_or_write() -> None:
    orchestrator, calls, storage, clock, citation = _orchestrator(
        empty=ContextEmptyReason.NO_CANDIDATES
    )
    result = await orchestrator.execute(_request())
    assert result.status is FinalQAStatus.NO_CONTEXT and result.answer is None
    storage.append_turn.assert_not_awaited()
    assert clock.calls == 0 and citation.arguments == (None, ())
    assert calls[-1] == "citation"


async def test_multi_hop_rejects_before_downstream_side_effects() -> None:
    orchestrator, calls, storage, clock, _ = _orchestrator(multi_hop=True)
    with pytest.raises(UnsupportedError):
        await orchestrator.execute(_request())
    assert calls == ["planner"]
    storage.append_turn.assert_not_awaited()
    assert clock.calls == 0


async def test_legacy_assistant_turn_cannot_be_replayed_without_snapshot() -> None:
    assistant = Turn(
        turn_id=_ASSISTANT,
        session_id=_SESSION,
        sequence=1,
        role=TurnRole.ASSISTANT,
        content="Grounded [source:1]",
        created_at=_NOW + timedelta(seconds=1),
    )
    storage = _storage(_session(assistant=assistant))
    orchestrator, calls, _, clock, citation = _orchestrator(storage=storage)
    with pytest.raises(ConflictError, match=r"final_qa\.replay_unavailable"):
        await orchestrator.execute(_request())
    storage.append_turn.assert_not_awaited()
    assert clock.calls == 0 and citation.arguments is None and calls == []


async def test_filter_projection_intersects_hard_constraints() -> None:
    orchestrator, _, _, _, _ = _orchestrator()
    hard = MetadataFilter(
        doc_types=(DocType.BOOK, DocType.PAPER),
        date_after=date(2020, 1, 1),
    )
    fusion_stage = orchestrator._fusion
    await orchestrator.execute(_request(metadata_filter=hard))
    assert fusion_stage.arguments is not None
    effective = fusion_stage.arguments[0][0]
    assert effective.sub_queries[0].filters.doc_types == hard.doc_types
    assert effective.sub_queries[0].filters.date_after == hard.date_after


async def test_filter_projection_rejects_empty_intersection_and_dates() -> None:
    orchestrator, *_ = _orchestrator()
    planner = orchestrator._planner
    base = planner.result
    planned_subquery = base.sub_queries[0].model_copy(
        update={"filters": MetadataFilter(doc_types=(DocType.BOOK,))}
    )
    planner.result = base.model_copy(update={"sub_queries": (planned_subquery,)})
    with pytest.raises(ContractValidationError, match="intersection"):
        await orchestrator.execute(
            _request(metadata_filter=MetadataFilter(doc_types=(DocType.PAPER,)))
        )

    planned_subquery = base.sub_queries[0].model_copy(
        update={"filters": MetadataFilter(date_before=date(2019, 1, 1))}
    )
    planner.result = base.model_copy(update={"sub_queries": (planned_subquery,)})
    with pytest.raises(ContractValidationError, match="date"):
        await orchestrator.execute(
            _request(metadata_filter=MetadataFilter(date_after=date(2020, 1, 1)))
        )


async def test_invalid_clock_fails_before_append() -> None:
    storage = _storage(_session())
    orchestrator, *_ = _orchestrator(storage=storage, clock=lambda: datetime.now())
    with pytest.raises(ContractValidationError, match="UTC"):
        await orchestrator.execute(_request())
    storage.append_turn.assert_not_awaited()


async def test_citation_failure_leaves_assistant_durable_and_lock_releases() -> None:
    storage = _storage(_session())
    orchestrator, *_ = _orchestrator(storage=storage)
    orchestrator._citation.resolve_and_persist = AsyncMock(side_effect=RuntimeError("citation"))
    with pytest.raises(RuntimeError, match="citation"):
        await orchestrator.execute(_request())
    storage.append_turn.assert_awaited_once()
    assert not orchestrator._locks[_SESSION].locked()


async def test_user_turn_precondition_and_cancellation_propagate() -> None:
    bad = _session()
    bad_user = Turn(
        turn_id=_USER,
        session_id=_SESSION,
        sequence=0,
        role=TurnRole.USER,
        content="different",
        created_at=_NOW,
    )
    bad = Session(
        session_id=bad.session_id,
        notebook_id=bad.notebook_id,
        created_at=_NOW,
        updated_at=_NOW,
        turns=(bad_user,),
    )
    orchestrator, *_ = _orchestrator(storage=_storage(bad))
    with pytest.raises(ContractValidationError):
        await orchestrator.execute(_request())

    cancelled, *_ = _orchestrator()
    cancelled._planner.plan = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await cancelled.execute(_request())


async def test_persisted_execution_publishes_then_replays_without_stage_or_write_calls() -> None:
    orchestrator, calls, storage, store, citation = _persisted_orchestrator()
    first = await orchestrator.execute(_request())
    first_calls = tuple(calls)
    assert first.status is FinalQAStatus.UNMARKED
    assert store.executions[_ASSISTANT].state is FinalQAExecutionState.PUBLISHED
    assert storage.append_turn.await_count == 1 and citation.arguments is not None

    replay = await orchestrator.execute(_request())
    assert replay == first
    assert tuple(calls) == first_calls
    assert storage.append_turn.await_count == 1
    assert store.events.count("claim") == 1


async def test_persisted_execution_retries_once_before_any_publication() -> None:
    orchestrator, calls, storage, store, _ = _persisted_orchestrator(
        first="Wrong [Source:1]", retry="Correct [source:1]"
    )
    result = await orchestrator.execute(_request())
    assert result.answer == "Correct [source:1]"
    assert calls == ["planner", "fusion", "reranker", "context", "answer", "retry", "citation"]
    assert store.executions[_ASSISTANT].retry_count == 1
    assert storage.append_turn.await_count == 1


@pytest.mark.parametrize("text", ("No source", "Wrong [Source:1]", "Bad [source:99]"))
async def test_persisted_execution_rejection_never_publishes(text: str) -> None:
    orchestrator, calls, storage, store, citation = _persisted_orchestrator(first=text, retry=text)
    with pytest.raises(IntegrityError, match="citation_compliance"):
        await orchestrator.execute(_request())
    assert calls == ["planner", "fusion", "reranker", "context", "answer", "retry"]
    assert store.executions[_ASSISTANT].state is FinalQAExecutionState.REJECTED_CITATION_COMPLIANCE
    storage.append_turn.assert_not_awaited()
    assert citation.arguments is None
    with pytest.raises(IntegrityError, match="citation_compliance"):
        await orchestrator.execute(_request())
    assert calls == ["planner", "fusion", "reranker", "context", "answer", "retry"]


async def test_persisted_execution_conflict_and_running_slot_do_not_generate() -> None:
    orchestrator, calls, _, _, _ = _persisted_orchestrator()
    await orchestrator.execute(_request())
    with pytest.raises(ConflictError):
        await orchestrator.execute(_request(global_limit=11))
    assert calls.count("answer") == 1

    running, running_calls, _, running_store, _ = _persisted_orchestrator()
    request = _request()
    now = _NOW
    await running_store.create_final_qa_execution(
        FinalQAExecution(
            execution_id=UUID("40000000-0000-4000-8000-000000000099"),
            assistant_turn_id=request.assistant_turn_id,
            request_fingerprint="will-not-match",
            notebook_id=_session().notebook_id,
            session_id=request.session_id,
            user_turn_id=request.user_turn_id,
            contract_version=FINAL_QA_EXECUTION_CONTRACT_VERSION,
            payload_schema_version=SNAPSHOT_SCHEMA_VERSION,
            provider="test-provider",
            model="test-model",
            model_configuration='{"temperature":"fixed"}',
            state=FinalQAExecutionState.RUNNING,
            retry_count=0,
            failure_classification=None,
            created_at=now,
            updated_at=now,
        )
    )
    with pytest.raises(ConflictError):
        await running.execute(request)
    assert running_calls == []


async def test_matching_running_execution_is_retryable_without_competing_generation() -> None:
    """ADR-0056 fails closed while another caller owns the generation slot."""
    orchestrator, calls, _, store, _ = _persisted_orchestrator()
    request = _request()
    descriptor = orchestrator._answer.final_qa_execution_descriptor()
    fingerprint = final_qa_request_fingerprint(
        request,
        notebook_id=_session().notebook_id,
        user_turn=_session().turns[0],
        provider=descriptor[0],
        model=descriptor[1],
        model_configuration=descriptor[2],
        tokenizer_id=descriptor[3],
    )
    await store.create_final_qa_execution(
        FinalQAExecution(
            execution_id=UUID("40000000-0000-4000-8000-000000000098"),
            assistant_turn_id=request.assistant_turn_id,
            request_fingerprint=fingerprint,
            notebook_id=_session().notebook_id,
            session_id=request.session_id,
            user_turn_id=request.user_turn_id,
            contract_version=FINAL_QA_EXECUTION_CONTRACT_VERSION,
            payload_schema_version=SNAPSHOT_SCHEMA_VERSION,
            provider=descriptor[0],
            model=descriptor[1],
            model_configuration='{"temperature":"fixed"}',
            state=FinalQAExecutionState.RUNNING,
            retry_count=0,
            failure_classification=None,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    with pytest.raises(ConflictError, match="execution_in_progress") as error:
        await orchestrator.execute(request)
    assert error.value.retryable is True
    assert calls == []


async def test_validated_and_assistant_published_resume_without_generation() -> None:
    original, _, storage, store, _ = _persisted_orchestrator()
    await original.execute(_request())
    execution = store.executions[_ASSISTANT]
    storage.get_session.return_value = _session(assistant=storage.append_turn.await_args.args[1])
    published = store.snapshots[(execution.execution_id, FinalQAExecutionSnapshotPhase.PUBLISHED)]
    validated = store.snapshots[(execution.execution_id, FinalQAExecutionSnapshotPhase.VALIDATED)]
    del store.snapshots[(execution.execution_id, FinalQAExecutionSnapshotPhase.PUBLISHED)]
    store.executions[_ASSISTANT] = FinalQAExecution(
        **{
            **{field: getattr(execution, field) for field in execution.__dataclass_fields__},
            "state": FinalQAExecutionState.VALIDATED,
        }
    )
    resume, calls, _, _, _ = _persisted_orchestrator(storage=storage, execution_store=store)
    result = await resume.execute(_request())
    assert result.answer == "Grounded [source:1]"
    assert calls == ["citation"]
    assert (execution.execution_id, FinalQAExecutionSnapshotPhase.PUBLISHED) in store.snapshots

    del store.snapshots[(execution.execution_id, FinalQAExecutionSnapshotPhase.PUBLISHED)]
    store.executions[_ASSISTANT] = FinalQAExecution(
        **{
            **{
                field: getattr(store.executions[_ASSISTANT], field)
                for field in execution.__dataclass_fields__
            },
            "state": FinalQAExecutionState.ASSISTANT_PUBLISHED,
        }
    )
    resumed_again, again_calls, _, _, _ = _persisted_orchestrator(
        storage=storage, execution_store=store
    )
    assert (await resumed_again.execute(_request())).answer == "Grounded [source:1]"
    assert again_calls == ["citation"]
    assert validated.phase is FinalQAExecutionSnapshotPhase.VALIDATED
    assert published.phase is FinalQAExecutionSnapshotPhase.PUBLISHED


async def test_assistant_published_with_durable_result_snapshot_finishes_without_citation() -> None:
    original, _, storage, store, _ = _persisted_orchestrator()
    first = await original.execute(_request())
    execution = store.executions[_ASSISTANT]
    store.executions[_ASSISTANT] = FinalQAExecution(
        **{
            **{field: getattr(execution, field) for field in execution.__dataclass_fields__},
            "state": FinalQAExecutionState.ASSISTANT_PUBLISHED,
        }
    )
    resumed, calls, _, _, _ = _persisted_orchestrator(storage=storage, execution_store=store)
    assert await resumed.execute(_request()) == first
    assert calls == []
    assert store.executions[_ASSISTANT].state is FinalQAExecutionState.PUBLISHED


async def test_concurrent_matching_claim_allows_only_one_generation() -> None:
    orchestrator, calls, storage, store, citation = _persisted_orchestrator()
    entered = asyncio.Event()
    release = asyncio.Event()
    original_generate = orchestrator._answer.generate

    async def slow_generate(*args: object, **kwargs: object) -> object:
        entered.set()
        await release.wait()
        return await original_generate(*args, **kwargs)

    orchestrator._answer.generate = slow_generate
    owner = asyncio.create_task(orchestrator.execute(_request()))
    await entered.wait()
    with pytest.raises(ConflictError, match="execution_in_progress") as competing:
        await orchestrator.execute(_request())
    assert competing.value.retryable is True
    release.set()
    result = await owner

    assert result.answer == "Grounded [source:1]"
    assert calls.count("answer") == 1
    assert storage.append_turn.await_count == 1
    assert citation.arguments is not None
    assert store.events.count("claim") == 1


async def test_cancelled_persisted_generation_fails_closed_in_running_state() -> None:
    orchestrator, calls, storage, store, citation = _persisted_orchestrator()
    orchestrator._answer.generate = AsyncMock(side_effect=asyncio.CancelledError())

    with pytest.raises(asyncio.CancelledError):
        await orchestrator.execute(_request())

    execution = store.executions[_ASSISTANT]
    assert execution.state is FinalQAExecutionState.RUNNING
    assert store.snapshots == {}
    storage.append_turn.assert_not_awaited()
    assert citation.arguments is None
    assert calls == ["planner", "fusion", "reranker", "context"]
