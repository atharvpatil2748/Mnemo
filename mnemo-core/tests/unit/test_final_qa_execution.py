"""Focused ADR-0056 request-fingerprint tests."""

from datetime import UTC, datetime
from uuid import uuid4

from mnemo.models import (
    CitationResolutionResult,
    CitationResolutionStatus,
    FinalQARequest,
    FinalQAResult,
    FinalQAStatus,
    MetadataFilter,
    Turn,
    TurnRole,
)
from mnemo.models.final_qa_execution import final_qa_request_fingerprint
from mnemo.retrieval.final_qa_snapshot import decode_published_snapshot, encode_published_snapshot
from test_citation_engine import _answer, _turn


def test_final_qa_fingerprint_is_deterministic_and_excludes_publication_slot() -> None:
    notebook_id, session_id, user_turn_id = uuid4(), uuid4(), uuid4()
    user = Turn(
        turn_id=user_turn_id,
        session_id=session_id,
        sequence=0,
        role=TurnRole.USER,
        content="What is the answer?",
        created_at=datetime.now(UTC),
    )
    common = dict(
        query=user.content,
        metadata_filter=MetadataFilter(notebook_id=notebook_id),
        global_limit=20,
        context_budget=8000,
        system_prompt="grounded",
        max_output_tokens=1000,
        session_id=session_id,
        user_turn_id=user_turn_id,
    )
    first = FinalQARequest(assistant_turn_id=uuid4(), **common)
    second = FinalQARequest(assistant_turn_id=uuid4(), **common)
    kwargs = dict(
        notebook_id=notebook_id,
        user_turn=user,
        provider="ollama",
        model="test",
        model_configuration={"max_context_tokens": 4096},
        tokenizer_id="test/tokenizer",
    )
    fingerprint = final_qa_request_fingerprint(first, **kwargs)
    assert fingerprint == final_qa_request_fingerprint(first, **kwargs)
    assert fingerprint == final_qa_request_fingerprint(second, **kwargs)
    changed = FinalQARequest(
        assistant_turn_id=uuid4(),
        **(common | {"global_limit": 21}),
    )
    assert fingerprint != final_qa_request_fingerprint(changed, **kwargs)


def test_published_snapshot_round_trip_preserves_nested_provenance_identity() -> None:
    answer = _answer("Grounded [source:1]")
    citation = CitationResolutionResult(
        answer_result=answer,
        assistant_turn=_turn(answer),
        status=CitationResolutionStatus.UNMARKED,
        citations=(),
        persisted=False,
    )
    original = FinalQAResult(citation_result=citation, status=FinalQAStatus.UNMARKED)
    decoded = decode_published_snapshot(encode_published_snapshot(original))
    assert decoded == original
    assert decoded.citation_result.answer_result.context_result.rerank_result is (
        decoded.citation_result.answer_result.context_result.rerank_result
    )
