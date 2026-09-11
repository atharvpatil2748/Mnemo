"""Focused WP-07 HTTP/MCP application-contract tests."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
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
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig
from mnemo_server.mcp.tools import execute_mcp_tool, get_mcp_tools, structured_content_for
from mnemo_server.schemas.retrieval_v2 import EvidenceSearchRequest
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


def test_http_contract_is_additive_and_strict() -> None:
    app = create_app(server_config=ServerConfig(), provision_tokenizer_on_startup=False)
    schema = app.openapi()["paths"]["/v2/retrieval/evidence"]["post"]
    assert schema["requestBody"]["required"] is True


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
