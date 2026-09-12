from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from mnemo.config import MnemoConfig
from mnemo.interfaces.errors import (
    ContractValidationError,
    DependencyUnavailableError,
    OperationTimeoutError,
    UnsupportedError,
)
from mnemo_server.config import ServerConfig
from mnemo_server.mcp.tools import execute_mcp_tool
from mnemo_server.schemas.search import QueryFilters
from mnemo_server.services.authorization import ServerPrincipalV1
from mnemo_server.services.final_qa_operational import (
    open_production_final_qa_operational_store,
)
from mnemo_server.services.final_qa_v2 import (
    FinalQAV2ApplicationService,
    _multimodal_result,
)
from mnemo_server.services.search import SearchService

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.anyio
async def test_open_production_final_qa_operational_store_branches(tmp_path: Path) -> None:
    corpus_db = tmp_path / "corpus.db"
    corpus_db.write_bytes(b"corpus")
    mnemo_config = MnemoConfig.from_file(ROOT / "mnemo.toml").model_copy(
        update={"storage": SimpleNamespace(sqlite=SimpleNamespace(path=corpus_db))}
    )

    # 1. Missing configuration raises FINAL_QA_OPERATIONAL_STORE_CONFIGURATION_MISSING
    server_no_store = ServerConfig(final_qa_operational_store_path=None)
    with pytest.raises(RuntimeError, match="FINAL_QA_OPERATIONAL_STORE_CONFIGURATION_MISSING"):
        await open_production_final_qa_operational_store(
            workspace_root=tmp_path,
            mnemo_config=mnemo_config,  # type: ignore[arg-type]
            server_config=server_no_store,
        )

    # 2. Path identical to corpus raises FINAL_QA_OPERATIONAL_STORE_MUST_DIFFER_FROM_CORPUS_STORE
    server_same_store = ServerConfig(final_qa_operational_store_path=corpus_db)
    with pytest.raises(
        RuntimeError, match="FINAL_QA_OPERATIONAL_STORE_MUST_DIFFER_FROM_CORPUS_STORE"
    ):
        await open_production_final_qa_operational_store(
            workspace_root=tmp_path,
            mnemo_config=mnemo_config,  # type: ignore[arg-type]
            server_config=server_same_store,
        )

    # 3. Valid distinct path opens successfully
    op_db = tmp_path / "operational.db"
    server_valid = ServerConfig(final_qa_operational_store_path=op_db)
    store = await open_production_final_qa_operational_store(
        workspace_root=tmp_path,
        mnemo_config=mnemo_config,  # type: ignore[arg-type]
        server_config=server_valid,
    )
    assert store is not None
    await store.close()


@pytest.mark.anyio
async def test_final_qa_v2_authorized_retrieval_branches(tmp_path: Path) -> None:
    server_config = ServerConfig(
        max_advanced_elapsed_milliseconds=5000,
        max_advanced_candidate_budget=10,
        max_advanced_evidence_budget=5,
        max_advanced_response_bytes=10000,
        max_advanced_content_characters=10000,
        production_rerank_candidate_limit=10,
    )
    unauth_principal = ServerPrincipalV1(uuid4(), False)
    auth_principal = ServerPrincipalV1(uuid4(), True)

    request = SimpleNamespace(
        to_plan=lambda **_kwargs: SimpleNamespace(),
        cursor=None,
    )

    # 1. Unauthenticated principal raises PermissionError
    service_unauth = FinalQAV2ApplicationService(
        engine=cast(Any, SimpleNamespace(advanced_retrieval=None)),
        server_config=server_config,
    )
    with pytest.raises(PermissionError, match="production FinalQA requires authentication"):
        await service_unauth._retrieval_result_authorized(
            question="test",
            request=cast(Any, request),
            principal=unauth_principal,
        )

    # 2. Non-principal-aware retrieval interface raises DependencyUnavailableError
    class DummyRetrieval:
        pass

    service_dummy = FinalQAV2ApplicationService(
        engine=cast(Any, SimpleNamespace(advanced_retrieval=DummyRetrieval())),
        server_config=server_config,
    )
    with pytest.raises(
        DependencyUnavailableError, match="lacks the principal-aware V2 entry point"
    ):
        await service_dummy._retrieval_result_authorized(
            question="test",
            request=cast(Any, request),
            principal=auth_principal,
        )

    # 3. Timeout error branch
    from mnemo.interfaces.advanced_retrieval import PrincipalAwareAdvancedRetrievalInterfaceV2

    class TimeoutRetrieval(PrincipalAwareAdvancedRetrievalInterfaceV2):
        async def execute_authorized(self, *args: Any, **kwargs: Any) -> Any:
            raise TimeoutError("timeout")

    service_timeout = FinalQAV2ApplicationService(
        engine=cast(Any, SimpleNamespace(advanced_retrieval=TimeoutRetrieval())),
        server_config=server_config,
    )
    with pytest.raises(
        OperationTimeoutError, match="Final-QA evidence retrieval exceeded deadline"
    ):
        await service_timeout._retrieval_result_authorized(
            question="test",
            request=cast(Any, request),
            principal=auth_principal,
        )


def test_multimodal_result_diagnostics_formatting() -> None:
    from mnemo.models import RetrievalCompleteness

    raw = SimpleNamespace(
        examined_count=5,
        diagnostics=SimpleNamespace(elapsed_milliseconds=42),
        query_fingerprint="0" * 64,
        snapshot_identity="1" * 64,
        completeness=RetrievalCompleteness.COMPLETE,
    )
    # Monkeypatch candidates_from_retrieval to return empty tuple
    from mnemo_server.services import final_qa_v2 as subject

    orig = subject.candidates_from_retrieval
    subject.candidates_from_retrieval = lambda _raw: ()  # type: ignore[assignment]
    try:
        result = _multimodal_result("test query", raw)
        assert result.query == "test query"
        assert result.diagnostics.recalled == 5
        assert result.diagnostics.elapsed_milliseconds == 42
    finally:
        subject.candidates_from_retrieval = orig  # type: ignore[assignment]


def test_search_service_metadata_filters() -> None:
    engine = SimpleNamespace()
    service = SearchService(engine=cast(Any, engine))

    # None filter returns empty MetadataFilter
    f_none = service._build_metadata_filter(None, None)
    assert f_none.notebook_id is None
    assert f_none.doc_types == ()

    # Valid doc_type filter
    f_valid = service._build_metadata_filter(
        UUID("00000000-0000-0000-0000-000000000001"),
        QueryFilters(doc_type=["slides", "markdown"]),
    )
    assert len(f_valid.doc_types) == 2

    # Invalid doc_type filter raises ContractValidationError
    with pytest.raises(ContractValidationError, match="Invalid doc_type filter"):
        service._build_metadata_filter(None, QueryFilters(doc_type=["not-a-valid-doc-type"]))


@pytest.mark.anyio
async def test_search_service_unsupported_mode() -> None:
    engine = SimpleNamespace()
    service = SearchService(engine=cast(Any, engine))
    req = SimpleNamespace(
        query="test query",
        modes=["invalid_retrieval_mode"],
        notebook_id=None,
        filters=None,
        limit=10,
    )
    with pytest.raises(UnsupportedError, match="Unsupported retrieval mode"):
        await service.execute_search(cast(Any, req))


@pytest.mark.anyio
async def test_search_service_notebook_not_found() -> None:
    from mnemo.interfaces import NotFoundError

    async def get_notebook(_id: Any) -> None:
        return None

    storage = SimpleNamespace(get_notebook=get_notebook)
    engine = SimpleNamespace(storage=storage)
    service = SearchService(engine=cast(Any, engine))
    req = SimpleNamespace(
        query="test query",
        modes=["dense"],
        notebook_id=UUID("00000000-0000-0000-0000-000000000099"),
        filters=None,
        limit=10,
    )
    with pytest.raises(NotFoundError, match=r"Notebook with id .* not found"):
        await service.execute_search(cast(Any, req))


@pytest.mark.anyio
async def test_mcp_search_all_notebooks_with_notebook_id() -> None:
    from mnemo.engine import EngineState

    class MockSearchService:
        def __init__(self, engine: Any) -> None:
            pass

        async def execute_search(self, request: Any) -> Any:
            assert request.notebook_id == UUID("00000000-0000-0000-0000-000000000042")
            return SimpleNamespace(
                results=[
                    SimpleNamespace(
                        chunk_id="chunk-1",
                        notebook_id=request.notebook_id,
                        document_id="doc-1",
                        version_id="ver-1",
                        text="matching chunk content",
                        score=0.95,
                        rank=1,
                        retrieval_mode="dense",
                        heading_path=["Title", "Section"],
                        page_number=1,
                        page_start=1,
                        page_end=2,
                        metadata={},
                    )
                ],
                total=1,
                latency_ms=12.5,
            )

    from mnemo_server.mcp import tools as subject

    orig = subject.SearchService
    subject.SearchService = MockSearchService  # type: ignore[misc]
    engine = SimpleNamespace(state=EngineState.READY)
    try:
        content = await execute_mcp_tool(
            engine=cast(Any, engine),
            name="search_all_notebooks",
            arguments={
                "query": "test query",
                "notebook_id": "00000000-0000-0000-0000-000000000042",
                "top_k": 5,
            },
        )
        assert len(content) == 1
        assert "matching chunk" in content[0].text
    finally:
        subject.SearchService = orig  # type: ignore[misc]


@pytest.mark.anyio
async def test_mcp_tool_contract_validation_branches() -> None:
    from mnemo.engine import EngineState

    engine = SimpleNamespace(state=EngineState.READY)

    # 1. Unknown tool
    with pytest.raises(ValueError, match="Unknown MCP tool: 'nonexistent'"):
        await execute_mcp_tool(engine=cast(Any, engine), name="nonexistent", arguments={})

    # 2. search_all_notebooks empty query
    with pytest.raises(
        ContractValidationError, match="Parameter 'query' must be a non-empty string"
    ):
        await execute_mcp_tool(
            engine=cast(Any, engine),
            name="search_all_notebooks",
            arguments={"query": "   "},
        )

    # 3. search_all_notebooks invalid top_k
    with pytest.raises(
        ContractValidationError, match=r"Parameter 'top_k' .* must be an integer between 1 and 100"
    ):
        await execute_mcp_tool(
            engine=cast(Any, engine),
            name="search_all_notebooks",
            arguments={"query": "valid query", "top_k": 500},
        )

    # 4. query_notebook empty question
    with pytest.raises(
        ContractValidationError, match="Parameter 'question' must be a non-empty string"
    ):
        await execute_mcp_tool(
            engine=cast(Any, engine),
            name="query_notebook",
            arguments={"notebook_id": "00000000-0000-0000-0000-000000000001", "question": ""},
        )

    # 5. query_notebook invalid synthesize
    with pytest.raises(ContractValidationError, match="Parameter 'synthesize' must be a boolean"):
        await execute_mcp_tool(
            engine=cast(Any, engine),
            name="query_notebook",
            arguments={
                "notebook_id": "00000000-0000-0000-0000-000000000001",
                "question": "What?",
                "synthesize": "not-a-bool",
            },
        )

    # 6. get_timeline invalid limit
    with pytest.raises(
        ContractValidationError, match="Parameter 'limit' must be an integer between 1 and 100"
    ):
        await execute_mcp_tool(
            engine=cast(Any, engine),
            name="get_timeline",
            arguments={"notebook_id": "00000000-0000-0000-0000-000000000001", "limit": 0},
        )
