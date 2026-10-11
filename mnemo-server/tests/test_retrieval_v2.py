"""Focused WP-07 HTTP/MCP application-contract tests."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from mnemo import MnemoConfig, Phase85Runtime
from mnemo.cursors import CursorConflictError
from mnemo.engine import EngineState
from mnemo.interfaces import (
    AdvancedSourcePage,
    ConflictError,
    ContractValidationError,
    OperationTimeoutError,
    PrincipalContextV1,
)
from mnemo.models import (
    AdvancedRetrievalCandidate,
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    EvidenceRepresentation,
    FrozenMetadata,
    RetrievalPathEvidenceV2,
    advanced_candidate_id,
)
from mnemo.retrieval import AdvancedRetrievalService, RetrievalCursorCodec
from mnemo.retrieval.advanced import _diversify_occurrences
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig
from mnemo_server.mcp.tools import execute_mcp_tool, get_mcp_tools, structured_content_for
from mnemo_server.schemas.automatic_query_v2 import AutomaticQueryV2Request
from mnemo_server.schemas.retrieval_v2 import EvidenceSearchRequest
from mnemo_server.services.automatic_query_v2 import AutomaticQueryV2ApplicationService
from mnemo_server.services.retrieval_v2 import (
    EvidenceRetrievalApplicationService,
    _match_semantics,
    build_retrieval_cursor_codec,
)


def _candidate(notebook_id: UUID, index: int) -> AdvancedRetrievalCandidate:
    document_id, version_id, source_id = uuid4(), uuid4(), uuid4()
    chunk = Chunk(
        id=f"{index:064x}",
        document_id=document_id,
        version_id=version_id,
        text=f"target evidence {index}",
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(
            section_index=0, chunk_index_in_section=index, page_number=index + 1
        ),
        source_span=BlockSpan(start_ordinal=index, end_ordinal=index),
        heading_path=("Target",),
        metadata=FrozenMetadata(),
    )
    return AdvancedRetrievalCandidate(
        candidate_id=advanced_candidate_id(
            representation=EvidenceRepresentation.CANONICAL_TEXT,
            document_id=document_id,
            version_id=version_id,
            chunk_id=chunk.id,
            occurrence_id=None,
            derivation_id=None,
        ),
        notebook_id=notebook_id,
        source_id=source_id,
        document_id=document_id,
        version_id=version_id,
        representation=EvidenceRepresentation.CANONICAL_TEXT,
        chunk=chunk,
        occurrence_id=None,
        derivation_id=None,
        locator=FrozenMetadata({"page_number": index + 1}),
        document_title="Target Document",
        content=chunk.text,
        paths=(
            RetrievalPathEvidenceV2(
                path="sqlite-canonical-enumeration",
                source_rank=index + 1,
                source_score=None,
                title_match=index == 0,
            ),
        ),
    )


class _Source:
    representation = EvidenceRepresentation.CANONICAL_TEXT

    def __init__(self, candidates: tuple[AdvancedRetrievalCandidate, ...]) -> None:
        self._candidates = candidates

    async def retrieve(self, plan, *, offset: int, limit: int):  # type: ignore[no-untyped-def]
        del plan
        values = self._candidates[offset : offset + limit]
        next_offset = offset + len(values) if offset + len(values) < len(self._candidates) else None
        return AdvancedSourcePage(
            representation=self.representation,
            snapshot_identity="a" * 64,
            candidates=values,
            examined=len(values),
            next_offset=next_offset,
            exhausted=next_offset is None,
        )

    async def expand(self, plan, seeds, *, limit: int):  # type: ignore[no-untyped-def]
        del plan, seeds, limit
        return ()


def _engine(notebook_id: UUID) -> SimpleNamespace:
    service = AdvancedRetrievalService(
        sources=(_Source(tuple(_candidate(notebook_id, index) for index in range(3))),),
        cursor_codec=RetrievalCursorCodec(b"wp07-focused-test-signing-secret!"),
    )
    return SimpleNamespace(state=EngineState.READY, advanced_retrieval=service)


def _request(notebook_id: UUID, **changes: object) -> EvidenceSearchRequest:
    values: dict[str, object] = {
        "query": "target",
        "mode": "exhaustive",
        "scope": {"notebook_id": str(notebook_id)},
        "representations": ["canonical_text"],
        "candidate_budget": 10,
        "evidence_budget": 2,
    }
    values.update(changes)
    return EvidenceSearchRequest.model_validate(values)


def test_automatic_occurrence_diversity_preserves_alternate_evidence() -> None:
    notebook_id = uuid4()
    first, unrelated, alternate = (_candidate(notebook_id, index) for index in range(3))
    same_occurrence = uuid4()
    first_derivation = uuid4()
    first = replace(
        first,
        candidate_id=advanced_candidate_id(
            representation=EvidenceRepresentation.OCR_TEXT,
            document_id=first.document_id,
            version_id=first.version_id,
            chunk_id=None,
            occurrence_id=same_occurrence,
            derivation_id=first_derivation,
        ),
        representation=EvidenceRepresentation.OCR_TEXT,
        chunk=None,
        occurrence_id=same_occurrence,
        derivation_id=first_derivation,
    )
    alternate_derivation = uuid4()
    alternate = replace(
        alternate,
        candidate_id=advanced_candidate_id(
            representation=EvidenceRepresentation.VISION_ANALYSIS,
            document_id=first.document_id,
            version_id=first.version_id,
            chunk_id=None,
            occurrence_id=same_occurrence,
            derivation_id=alternate_derivation,
        ),
        representation=EvidenceRepresentation.VISION_ANALYSIS,
        document_id=first.document_id,
        version_id=first.version_id,
        chunk=None,
        occurrence_id=same_occurrence,
        derivation_id=alternate_derivation,
    )
    ordered = _diversify_occurrences((first, alternate, unrelated))
    # OCR and Vision are independently sourced views of the occurrence; the
    # diversity bound demotes repeats within one representation, not across it.
    assert ordered == (first, alternate, unrelated)


@pytest.mark.anyio
async def test_automatic_query_continues_after_canonical_zero() -> None:
    notebook_id = uuid4()
    source = _candidate(notebook_id, 0)
    occurrence_id, derivation_id = uuid4(), uuid4()
    ocr_candidate = replace(
        source,
        candidate_id=advanced_candidate_id(
            representation=EvidenceRepresentation.OCR_TEXT,
            document_id=source.document_id,
            version_id=source.version_id,
            chunk_id=None,
            occurrence_id=occurrence_id,
            derivation_id=derivation_id,
        ),
        representation=EvidenceRepresentation.OCR_TEXT,
        chunk=None,
        occurrence_id=occurrence_id,
        derivation_id=derivation_id,
    )

    class OCRSource(_Source):
        representation = EvidenceRepresentation.OCR_TEXT

    async def list_notebooks(*, limit: int, cursor: str | None):
        assert limit == 2 and cursor is None
        return SimpleNamespace(items=(SimpleNamespace(notebook_id=notebook_id),), next_cursor=None)

    async def get_notebook(identity: UUID):
        return object() if identity == notebook_id else None

    engine = SimpleNamespace(
        state=EngineState.READY,
        storage=SimpleNamespace(list_notebooks=list_notebooks, get_notebook=get_notebook),
        advanced_retrieval=AdvancedRetrievalService(
            sources=(_Source(()), OCRSource((ocr_candidate,))),
            cursor_codec=RetrievalCursorCodec(b"automatic-query-test-signing-key!"),
        ),
    )
    response = await AutomaticQueryV2ApplicationService(engine, ServerConfig()).execute(
        AutomaticQueryV2Request(query="angular momentum formula"),
        PrincipalContextV1(uuid4(), True),
    )
    assert response.evidence.items[0]["representation"] == "ocr_text"
    assert response.evidence.items[0]["occurrence_id"] == str(occurrence_id)
    assert response.answer_status == "not_generated"
    assert {item.representation: item.status for item in response.representation_decisions}[
        "ocr_text"
    ] == "searched"
    with pytest.raises(ContractValidationError, match="candidate_budget is too small"):
        await AutomaticQueryV2ApplicationService(engine, ServerConfig()).execute(
            AutomaticQueryV2Request(query="formula", candidate_budget=1),
            PrincipalContextV1(uuid4(), True),
        )
    mcp_content = await execute_mcp_tool(  # type: ignore[arg-type]
        engine,
        "query_notebook_v2",
        {"query": "angular momentum formula"},
        ServerConfig(),
        PrincipalContextV1(uuid4(), True),
    )
    assert json.loads(mcp_content[0].text)["evidence"]["items"][0]["representation"] == "ocr_text"


@pytest.mark.anyio
async def test_automatic_query_rejects_ambiguous_scope_without_revealing_generations() -> None:
    notebook_ids = (uuid4(), uuid4())

    async def list_notebooks(*, limit: int, cursor: str | None):
        return SimpleNamespace(
            items=tuple(SimpleNamespace(notebook_id=value) for value in notebook_ids),
            next_cursor=None,
        )

    engine = SimpleNamespace(storage=SimpleNamespace(list_notebooks=list_notebooks))
    with pytest.raises(Exception, match="unambiguous authorized notebook scope"):
        await AutomaticQueryV2ApplicationService(engine, ServerConfig()).execute(
            AutomaticQueryV2Request(query="formula"), PrincipalContextV1(uuid4(), True)
        )


@pytest.mark.anyio
async def test_automatic_query_cursor_binds_actor_and_public_budget() -> None:
    notebook_id = uuid4()

    async def list_notebooks(*, limit: int, cursor: str | None):
        return SimpleNamespace(items=(SimpleNamespace(notebook_id=notebook_id),), next_cursor=None)

    async def get_notebook(identity: UUID):
        return object() if identity == notebook_id else None

    engine = SimpleNamespace(
        storage=SimpleNamespace(list_notebooks=list_notebooks, get_notebook=get_notebook),
        advanced_retrieval=_engine(notebook_id).advanced_retrieval,
    )
    service = AutomaticQueryV2ApplicationService(engine, ServerConfig())
    actor = PrincipalContextV1(uuid4(), True)
    request = AutomaticQueryV2Request(
        query="target", mode="exhaustive", evidence_budget=1, candidate_budget=3
    )
    first = await service.execute(request, actor)
    assert first.evidence.next_cursor is not None
    continued = await service.execute(
        request.model_copy(update={"cursor": first.evidence.next_cursor}), actor
    )
    assert continued.evidence.items[0]["chunk_id"] != first.evidence.items[0]["chunk_id"]
    with pytest.raises(ConflictError):
        await service.execute(
            request.model_copy(update={"cursor": first.evidence.next_cursor}),
            PrincipalContextV1(uuid4(), True),
        )
    with pytest.raises(ConflictError):
        await service.execute(
            request.model_copy(
                update={"cursor": first.evidence.next_cursor, "candidate_budget": 4}
            ),
            actor,
        )
    engine.full_multilingual_v2_alias_digest = "a" * 64
    with pytest.raises(ConflictError):
        await service.execute(
            request.model_copy(update={"cursor": first.evidence.next_cursor}), actor
        )


@pytest.mark.parametrize(
    "field",
    ["candidate_budget", "evidence_budget", "max_content_characters", "max_serialized_bytes"],
)
@pytest.mark.parametrize("value", [True, 3.0, "3"])
def test_evidence_numeric_budgets_reject_coercible_nonintegers(field: str, value: object) -> None:
    from pydantic import ValidationError

    if field == "max_serialized_bytes" and not isinstance(value, bool):
        value = 512.0 if isinstance(value, float) else "512"
    with pytest.raises(ValidationError):
        _request(uuid4(), **{field: value})


def test_evidence_positional_numeric_fields_reject_boolean() -> None:
    from pydantic import ValidationError

    for position in ({"page_start": True}, {"page_end": True}, {"section_indexes": [True]}):
        with pytest.raises(ValidationError):
            _request(uuid4(), positional_scope=position)


def test_cursor_rejects_candidate_budget_change_below_production_pool() -> None:
    from datetime import UTC, datetime

    notebook_id = uuid4()
    codec = RetrievalCursorCodec(b"wp07-focused-test-signing-secret!")
    request = _request(
        notebook_id,
        query="buildCodePrompt",
        candidate_budget=3,
        evidence_budget=1,
        max_content_characters=2000,
    )
    options = dict(
        max_candidate_budget=100,
        max_evidence_budget=50,
        max_response_bytes=1_000_000,
        max_content_characters=200_000,
        production_candidate_pool_k=50,
        security_scope_identity=str(uuid4()),
    )
    plan = request.to_plan(**options)
    now = datetime.now(UTC)
    token = codec.encode(
        plan=plan, representation_index=0, offset=1, snapshots={"canonical_text": "a" * 64}, now=now
    )
    changed = request.model_copy(update={"candidate_budget": 4}).to_plan(**options)
    assert changed.budgets == plan.budgets  # Normalization is intentionally unchanged.
    with pytest.raises(CursorConflictError):
        codec.decode(token, plan=changed, now=now)


@pytest.mark.parametrize(
    "field,value",
    [
        ("query", "other"),
        ("mode", "ranked"),
        ("scope", {"notebook_id": str(UUID(int=90))}),
        ("representations", ["ocr_text"]),
        ("candidate_budget", 4),
        ("evidence_budget", 2),
        ("max_content_characters", 2001),
        ("max_serialized_bytes", 1_000_001),
    ],
)
def test_signed_cursor_binds_requested_parameters_before_normalization(field, value) -> None:  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime

    request = _request(uuid4(), candidate_budget=3, evidence_budget=1, max_content_characters=2000)
    options = dict(
        max_candidate_budget=100,
        max_evidence_budget=50,
        max_response_bytes=1_000_000,
        max_content_characters=200_000,
        production_candidate_pool_k=50,
    )
    plan = request.to_plan(**options)
    codec = RetrievalCursorCodec(b"wp07-focused-test-signing-secret!")
    now = datetime.now(UTC)
    token = codec.encode(
        plan=plan, representation_index=0, offset=1, snapshots={"canonical_text": "a" * 64}, now=now
    )
    assert codec.decode(token, plan=plan, now=now)["offset"] == 1
    values = request.model_dump(mode="json")
    values[field] = value
    changed = EvidenceSearchRequest.model_validate(values).to_plan(**options)
    with pytest.raises(CursorConflictError):
        codec.decode(token, plan=changed, now=now)


def test_http_contract_is_additive_and_strict() -> None:
    app = create_app(server_config=ServerConfig(), provision_tokenizer_on_startup=False)
    schema = app.openapi()["paths"]["/v2/retrieval/evidence"]["post"]
    assert schema["requestBody"]["required"] is True
    automatic = app.openapi()["paths"]["/v2/retrieval/automatic"]["post"]
    assert automatic["requestBody"]["required"] is True
    names = app.openapi()["components"]["schemas"]["AutomaticQueryV2Request"]["properties"]
    assert "query" in names
    assert not {"notebook_id", "actor_id", "representations", "generation_id"} & set(names)


def test_automatic_policy_version_is_signed_into_cursor_fingerprint() -> None:
    from datetime import UTC, datetime

    request = _request(uuid4())
    options = dict(
        max_candidate_budget=100,
        max_evidence_budget=50,
        max_response_bytes=1_000_000,
        max_content_characters=200_000,
    )
    plan = request.to_plan(**options, automatic_policy_version="automatic-evidence-plan/v1")
    changed = request.to_plan(**options, automatic_policy_version="automatic-evidence-plan/v2")
    codec = RetrievalCursorCodec(b"automatic-policy-cursor-signing-key!")
    now = datetime.now(UTC)
    token = codec.encode(
        plan=plan,
        representation_index=0,
        offset=1,
        snapshots={"canonical_text": "a" * 64},
        now=now,
    )
    assert codec.decode(token, plan=plan, now=now)["offset"] == 1
    with pytest.raises(CursorConflictError):
        codec.decode(token, plan=changed, now=now)


def test_production_candidate_stage_is_governed_at_fifty() -> None:
    notebook_id = uuid4()
    request = _request(notebook_id, mode="ranked", candidate_budget=100, evidence_budget=50)
    config = ServerConfig()
    plan = request.to_plan(
        max_candidate_budget=config.max_advanced_candidate_budget,
        max_evidence_budget=config.max_advanced_evidence_budget,
        max_response_bytes=config.max_advanced_response_bytes,
        max_content_characters=config.max_advanced_content_characters,
        max_rerank_candidates=config.production_rerank_candidate_limit,
    )
    assert config.production_rerank_candidate_limit == 50
    assert plan.budgets.rerank_limit == 50


@pytest.mark.parametrize("requested_k", [1, 5, 10, 50])
def test_requested_k_is_dynamic_and_distinct_from_internal_pool(requested_k: int) -> None:
    request = _request(uuid4(), mode="ranked", candidate_budget=3, evidence_budget=requested_k)
    plan = request.to_plan(
        max_candidate_budget=1000,
        max_evidence_budget=200,
        max_response_bytes=1_000_000,
        max_content_characters=200_000,
        max_rerank_candidates=50,
        production_candidate_pool_k=50,
    )
    assert plan.budgets.rerank_limit == 50
    assert plan.budgets.result_limit == requested_k


@pytest.mark.anyio
async def test_exhaustive_application_service_has_truthful_cursor_and_terminal_state() -> None:
    notebook_id = uuid4()
    app = EvidenceRetrievalApplicationService(  # type: ignore[arg-type]
        _engine(notebook_id), ServerConfig()
    )
    first = await app.execute(_request(notebook_id))
    assert first.completeness == "truncated"
    assert first.next_cursor is not None
    assert first.coverage["exhaustive"] is True
    assert [item["content"] for item in first.items] == ["target evidence 0", "target evidence 1"]

    final = await app.execute(_request(notebook_id, cursor=first.next_cursor))
    assert final.completeness == "complete"
    assert final.next_cursor is None
    assert [item["content"] for item in final.items] == ["target evidence 2"]


@pytest.mark.anyio
async def test_exhaustive_continuation_cannot_skip_an_item_exceeding_content_budget() -> None:
    """A valid signed cursor may reach an item too large for the original budget."""
    notebook_id = uuid4()
    candidates = (
        _candidate(notebook_id, 0),
        replace(_candidate(notebook_id, 1), content="x" * 81),
    )
    retrieval = AdvancedRetrievalService(
        sources=(_Source(candidates),),
        cursor_codec=RetrievalCursorCodec(b"wp07-focused-test-signing-secret!"),
    )
    app = EvidenceRetrievalApplicationService(  # type: ignore[arg-type]
        SimpleNamespace(state=EngineState.READY, advanced_retrieval=retrieval),
        ServerConfig(),
    )
    first = await app.execute(_request(notebook_id, evidence_budget=1, max_content_characters=80))
    assert first.completeness == "truncated" and first.next_cursor is not None
    with pytest.raises(ContractValidationError, match="cannot serialize one evidence item"):
        await app.execute(
            _request(
                notebook_id,
                evidence_budget=1,
                max_content_characters=80,
                cursor=first.next_cursor,
            )
        )
    with pytest.raises(CursorConflictError, match="cursor"):
        await app.execute(
            _request(
                notebook_id,
                evidence_budget=1,
                max_content_characters=2000,
                cursor=first.next_cursor,
            )
        )
    restarted = await app.execute(
        _request(notebook_id, evidence_budget=1, max_content_characters=2000)
    )
    completed = await app.execute(
        _request(
            notebook_id,
            evidence_budget=1,
            max_content_characters=2000,
            cursor=restarted.next_cursor,
        )
    )
    assert completed.completeness == "complete"
    assert completed.items[0]["content"] == "x" * 81


@pytest.mark.anyio
async def test_unconfigured_ocr_generation_does_not_disable_persisted_ocr_search() -> None:
    """Generation lifecycle and searching an existing OCR projection are separate facts."""
    root = Path(__file__).resolve().parents[2]
    runtime = Phase85Runtime(MnemoConfig.from_file(root / "mnemo.toml"), engine_ready=True)
    assert runtime.profile_status("ocr").reason_code == "profile_not_configured"

    class EmptyOCRSource(_Source):
        representation = EvidenceRepresentation.OCR_TEXT

    notebook_id = uuid4()
    retrieval = AdvancedRetrievalService(
        sources=(EmptyOCRSource(()),),
        cursor_codec=RetrievalCursorCodec(b"wp07-focused-test-signing-secret!"),
    )
    app = EvidenceRetrievalApplicationService(  # type: ignore[arg-type]
        SimpleNamespace(state=EngineState.READY, advanced_retrieval=retrieval),
        ServerConfig(),
    )
    result = await app.execute(_request(notebook_id, representations=["ocr_text"]))
    assert result.items == []
    assert result.completeness == "empty"
    assert result.coverage["representations"] == [
        {
            "representation": "ocr_text",
            "status": "searched",
            "examined": 0,
            "returned": 0,
            "exhausted": True,
            "reason_code": None,
        }
    ]


@pytest.mark.anyio
async def test_ranked_is_bounded_unknown_and_never_continuable() -> None:
    notebook_id = uuid4()
    app = EvidenceRetrievalApplicationService(  # type: ignore[arg-type]
        _engine(notebook_id), ServerConfig()
    )
    result = await app.execute(
        _request(notebook_id, mode="ranked", candidate_budget=3, evidence_budget=2)
    )
    assert result.completeness == "unknown"
    assert result.next_cursor is None
    assert result.coverage["exhaustive"] is False
    assert len(result.items) == 2


@pytest.mark.anyio
async def test_application_deadline_fails_typed() -> None:
    class SlowRetrieval:
        async def execute(self, plan, *, cursor=None):  # type: ignore[no-untyped-def]
            del plan, cursor
            await asyncio.sleep(0.05)

    engine = SimpleNamespace(
        state=EngineState.READY,
        advanced_retrieval=SlowRetrieval(),
    )
    app = EvidenceRetrievalApplicationService(  # type: ignore[arg-type]
        engine,
        ServerConfig(max_advanced_elapsed_milliseconds=1),
    )
    with pytest.raises(OperationTimeoutError):
        await app.execute(_request(uuid4()))


@pytest.mark.anyio
async def test_cursor_is_bound_to_scope_and_request() -> None:
    notebook_id = uuid4()
    app = EvidenceRetrievalApplicationService(  # type: ignore[arg-type]
        _engine(notebook_id), ServerConfig()
    )
    first = await app.execute(_request(notebook_id))
    with pytest.raises(ConflictError):
        await app.execute(_request(uuid4(), cursor=first.next_cursor))
    with pytest.raises(ConflictError):
        await app.execute(_request(notebook_id, query="different", cursor=first.next_cursor))


@pytest.mark.anyio
async def test_unavailable_representation_is_partial_not_no_match() -> None:
    notebook_id = uuid4()
    app = EvidenceRetrievalApplicationService(  # type: ignore[arg-type]
        _engine(notebook_id), ServerConfig()
    )
    result = await app.execute(
        _request(notebook_id, representations=["canonical_text", "ocr_text"])
    )
    assert result.completeness == "truncated"
    assert "ocr_text:representation_unavailable" in result.omissions

    terminal = await app.execute(
        _request(
            notebook_id,
            representations=["canonical_text", "ocr_text"],
            cursor=result.next_cursor,
        )
    )
    assert terminal.completeness == "partial"


@pytest.mark.anyio
async def test_mcp_search_evidence_contract_and_structured_json() -> None:
    notebook_id = uuid4()
    tools = {tool.name: tool for tool in get_mcp_tools()}
    tool = tools["search_evidence"]
    description = (tool.description or "").lower()
    assert "ranked" in description and "exhaustive" in description
    assert "next_cursor" in description and "structured arithmetic" in description
    assert tool.outputSchema is not None
    assert "empty" in tool.outputSchema["properties"]["completeness"]["enum"]

    content = await execute_mcp_tool(  # type: ignore[arg-type]
        _engine(notebook_id),
        "search_evidence",
        _request(notebook_id).model_dump(mode="json", exclude_none=True),
        ServerConfig(),
    )
    payload = json.loads(content[0].text)  # type: ignore[union-attr]
    assert payload["operation"] == "search_evidence"
    assert payload["completeness"] == "truncated"
    assert payload["recommended_next_actions"][0]["pass_cursor_unchanged"] is True
    assert structured_content_for("search_evidence", {}, content) == payload


@pytest.mark.anyio
async def test_ranked_mode_rejects_cursor_and_unknown_fields() -> None:
    notebook_id = uuid4()
    with pytest.raises(ValueError):
        EvidenceSearchRequest.model_validate(
            {
                **_request(notebook_id).model_dump(mode="json"),
                "unexpected": True,
            }
        )
    app = EvidenceRetrievalApplicationService(  # type: ignore[arg-type]
        _engine(notebook_id), ServerConfig()
    )
    with pytest.raises(ValueError, match="only valid for exhaustive"):
        await app.execute(_request(notebook_id, mode="ranked", cursor="opaque"))


def test_scope_and_budget_explosion_are_rejected() -> None:
    notebook_id = uuid4()
    with pytest.raises(ValueError):
        EvidenceSearchRequest.model_validate(
            {
                **_request(notebook_id).model_dump(mode="json"),
                "scope": {
                    "notebook_id": str(notebook_id),
                    "source_ids": [str(uuid4()) for _ in range(201)],
                },
            }
        )
    with pytest.raises(ValueError):
        _request(notebook_id, candidate_budget=1001)


@pytest.mark.anyio
async def test_all_authorized_documents_passes_partition_ids() -> None:
    notebook_id = uuid4()
    candidate = _candidate(notebook_id, 0)
    doc_id = candidate.document_id
    from mnemo.retrieval.partitioned import PartitionedRetrievalServiceV1

    service = AdvancedRetrievalService(
        sources=(_Source((candidate,)),),
        cursor_codec=RetrievalCursorCodec(b"wp07-focused-test-signing-secret!"),
    )
    engine = SimpleNamespace(
        state=EngineState.READY,
        advanced_retrieval=service,
        partitioned_retrieval=PartitionedRetrievalServiceV1(service),
    )
    app = EvidenceRetrievalApplicationService(engine, ServerConfig())  # type: ignore[arg-type]

    async def _mock_resolve(nid: UUID, p: object) -> tuple[UUID, ...]:
        del nid, p
        return (doc_id,)

    app._resolve_authorized_documents = _mock_resolve  # type: ignore[assignment]

    req = _request(notebook_id, all_authorized_documents=True)
    resp = await app.execute(req)
    assert resp.operation == "search_evidence"
    assert resp.completeness in {"complete", "truncated", "empty"}


@pytest.mark.anyio
async def test_production_retrieval_requires_principal_aware_authenticated_entrypoint() -> None:
    notebook_id = uuid4()
    config = ServerConfig(
        production_mode=True, delivery_cursor_secret="production-test-secret-value-32bytes"
    )
    engine = _engine(notebook_id)
    application = EvidenceRetrievalApplicationService(engine, config)  # type: ignore[arg-type]
    with pytest.raises(PermissionError, match="requires authentication"):
        await application.execute(_request(notebook_id))
    application = EvidenceRetrievalApplicationService(  # type: ignore[arg-type]
        SimpleNamespace(advanced_retrieval=object()), config
    )
    with pytest.raises(RuntimeError, match="principal-aware"):
        await application.execute(_request(notebook_id), PrincipalContextV1(uuid4(), True))

    class AuthorizedRetrieval:
        async def execute_authorized(self, *, principal, plan, cursor=None):  # type: ignore[no-untyped-def]
            assert principal.authenticated and cursor is None
            return await engine.advanced_retrieval.execute(plan, cursor=cursor)

    authorized_engine = SimpleNamespace(advanced_retrieval=AuthorizedRetrieval())
    response = await EvidenceRetrievalApplicationService(  # type: ignore[arg-type]
        authorized_engine, config
    ).execute(_request(notebook_id), PrincipalContextV1(uuid4(), True))
    assert response.limits["internal_reranker_candidate_pool_k"] == 50


@pytest.mark.anyio
async def test_partition_request_rejects_ambiguous_document_universe() -> None:
    notebook_id = uuid4()
    application = EvidenceRetrievalApplicationService(  # type: ignore[arg-type]
        _engine(notebook_id), ServerConfig()
    )
    with pytest.raises(ContractValidationError, match="cannot be combined"):
        await application.execute(
            _request(
                notebook_id,
                all_authorized_documents=True,
                partition_document_ids=[str(uuid4())],
            )
        )


@pytest.mark.anyio
async def test_authorized_document_enumeration_filters_denials_and_paginates() -> None:
    notebook_id = uuid4()
    allowed = uuid4()
    denied = uuid4()

    class Storage:
        calls = 0

        async def list_documents(self, *_args: object) -> object:
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(
                    items=(
                        SimpleNamespace(document_id=allowed, current_version_id=uuid4()),
                        SimpleNamespace(document_id=denied, current_version_id=uuid4()),
                    ),
                    next_cursor="next",
                )
            return SimpleNamespace(items=(), next_cursor=None)

    class Resolver:
        async def resolve_document_scope(
            self, _principal: object, document_id: UUID, *_args: object
        ) -> object:
            if document_id == denied:
                raise PermissionError("denied")
            return object()

    engine = SimpleNamespace(storage=Storage(), document_scope_resolver=Resolver())
    application = EvidenceRetrievalApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    assert await application._resolve_authorized_documents(
        notebook_id, PrincipalContextV1(uuid4(), True)
    ) == (allowed,)


def test_retrieval_cursor_key_derivation_and_match_semantics() -> None:
    short = build_retrieval_cursor_codec(ServerConfig(delivery_cursor_secret="sixteen-char-key"))
    long = build_retrieval_cursor_codec(ServerConfig(delivery_cursor_secret="x" * 40))
    assert short is not None and long is not None
    assert _match_semantics("ranked", [{"representation": "visual_vector"}]).startswith(
        "shared_visual"
    )
    assert "asset_metadata" in _match_semantics("ranked", [{"representation": "asset_metadata"}])
    assert _match_semantics("exhaustive", []) == "canonical_sqlite_fts_term_disjunction"
