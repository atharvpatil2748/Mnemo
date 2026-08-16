"""Golden Corpus integration tests for Phase 8, Module 8.3 MCP Server."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from mnemo import __version__
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo.interfaces import (
    CompletionResult,
    ContractValidationError,
    EmbeddingProviderV1,
    LLMInterfaceV1,
    Message,
    NotFoundError,
    StorageInterfaceV1,
)
from mnemo.interfaces.types import (
    EmbeddingCapabilities,
    HealthStatus,
    LLMCapabilities,
    StorageCapabilities,
)
from mnemo.registry import PluginRegistry
from mnemo.retrieval import DenseRetriever, ParentRetriever, SparseRetriever
from mnemo.storage import (
    CompositeStorage,
    FilesystemBlobStore,
    QdrantStore,
    SQLiteStore,
    SurrealDBStore,
)
from mnemo_server.mcp.tools import execute_mcp_tool, get_mcp_tools

GOLDEN_DB_PATH = Path("data/manual-gita-qa/mnemo.db").resolve()
GOLDEN_FILES_PATH = Path("data/manual-gita-qa/files").resolve()
GOLDEN_NOTEBOOK_ID = UUID("d83b0c9e-5813-56ed-a03e-c7adc2f2241e")
GOLDEN_SOURCE_ID = UUID("682c406a-1f83-5187-a5ae-84878a5fb7c5")
GOLDEN_DOC_ID = UUID("d8ef0c53-8596-5b6d-b250-da5d91d3a20c")


class _GoldenRetrievalPlugin:
    name = "golden-retrieval-plugin"
    version = __version__
    core_version_range = ">=0.20.0"

    def __init__(self, storage: StorageInterfaceV1, synthesizer: LLMInterfaceV1) -> None:
        self._storage = storage
        self._synthesizer = synthesizer

    def capabilities(self) -> tuple[str, ...]:
        return ("retriever", "parent_promotion", "llm")

    def register(self, registry: PluginRegistry) -> None:
        registry.register_retriever("dense", DenseRetriever(self._storage), priority=0)
        registry.register_retriever("sparse", SparseRetriever(self._storage), priority=0)
        registry.register_parent_promoter("default", ParentRetriever(self._storage), priority=0)
        registry.register_llm("synthesizer", self._synthesizer, priority=0)


class _GoldenEmbedder(EmbeddingProviderV1):
    @property
    def model_name(self) -> str:
        return "mock-nomic-embed"

    @property
    def dimensions(self) -> int:
        return 768

    @property
    def max_tokens(self) -> int:
        return 2048

    def capabilities(self) -> EmbeddingCapabilities:
        return EmbeddingCapabilities(
            dimensions=768,
            supports_batch=True,
            max_batch=100,
            multilingual=False,
            supports_normalization=True,
        )

    async def embed(self, text: str) -> tuple[float, ...]:
        return (0.01,) * 768

    async def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple((0.01,) * 768 for _ in texts)

    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=True)


class _GoldenSynthesizer(LLMInterfaceV1):
    @property
    def provider(self) -> str:
        return "mock"

    @property
    def model(self) -> str:
        return "mock-gita-synthesizer"

    @property
    def max_context_tokens(self) -> int:
        return 8192

    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(
            supports_streaming=True,
            supports_json=True,
            supports_vision=False,
            supports_reasoning=False,
        )

    async def complete(
        self,
        system: str,
        messages: tuple[Message, ...],
        structured_output: object = None,
        max_tokens: int = 1000,
    ) -> CompletionResult:
        last_message = messages[-1].content if messages else ""
        if "quantum entanglement" in last_message.lower():
            return CompletionResult(
                model="mock-gita-synthesizer",
                text="The provided text does not contain information about quantum entanglement.",
            )
        return CompletionResult(
            model="mock-gita-synthesizer",
            text=(
                "According to the Bhagavad Gita Chapter 3, Karma-yoga is the performance of "
                "prescribed duties without attachment to the results [source:1]."
            ),
        )

    async def stream(
        self,
        system: str,
        messages: tuple[Message, ...],
        max_tokens: int = 1000,
    ) -> AsyncIterator[str]:
        yield (
            "According to the Bhagavad Gita Chapter 3, Karma-yoga is the performance of "
            "prescribed duties [source:1]."
        )

    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=True)


@asynccontextmanager
async def open_golden_engine() -> AsyncIterator[KnowledgeEngine]:
    """Context manager providing a KnowledgeEngine connected to the real Golden Corpus."""
    if not GOLDEN_DB_PATH.exists():
        pytest.skip(f"Golden Corpus database not found at {GOLDEN_DB_PATH}")

    fs = FilesystemBlobStore(GOLDEN_FILES_PATH)
    sql = SQLiteStore(GOLDEN_DB_PATH)

    empty_caps = StorageCapabilities(
        supports_blobs=False,
        supports_dense_search=True,
        supports_sparse_search=True,
        supports_metadata=True,
        supports_graph=False,
        supports_transactions=False,
        supports_health_checks=True,
    )

    qdr = MagicMock(spec=QdrantStore)
    qdr.open = AsyncMock()
    qdr.close = AsyncMock()
    qdr.search_dense = AsyncMock(return_value=())
    qdr.health_check = AsyncMock(return_value=())
    qdr.capabilities.return_value = empty_caps

    sur = MagicMock(spec=SurrealDBStore)
    sur.open = AsyncMock()
    sur.close = AsyncMock()
    sur.health_check = AsyncMock(return_value=())
    sur.capabilities.return_value = empty_caps

    composite = CompositeStorage(fs, sql, qdr, sur)
    await composite.open()

    synthesizer = _GoldenSynthesizer()
    registry = PluginRegistry(core_version=__version__)
    registry.load_plugin(_GoldenRetrievalPlugin(composite, synthesizer))
    registry.freeze()

    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    engine.storage = composite
    engine.registry = registry
    engine.embedding_provider = _GoldenEmbedder()
    engine.llm_synthesizer = synthesizer

    try:
        yield engine
    finally:
        await composite.close()


@pytest.mark.anyio
async def test_mcp_golden_corpus_list_notebooks() -> None:
    """Verify list_notebooks returns the real Golden Corpus notebook with correct metadata."""
    async with open_golden_engine() as golden_engine:
        contents = await execute_mcp_tool(golden_engine, "list_notebooks", {"limit": 10})
        assert len(contents) == 1
        data = json.loads(contents[0].text)

        assert data["total"] >= 1
        notebooks = data["notebooks"]
        assert any(nb["notebook_id"] == str(GOLDEN_NOTEBOOK_ID) for nb in notebooks)

        golden_nb = next(nb for nb in notebooks if nb["notebook_id"] == str(GOLDEN_NOTEBOOK_ID))
        assert golden_nb["title"] == "Experiment Notebook"
        assert golden_nb["source_count"] == 1


@pytest.mark.anyio
async def test_mcp_golden_corpus_get_notebook_summary() -> None:
    """Verify get_notebook_summary returns source inventory with correct Golden document title."""
    async with open_golden_engine() as golden_engine:
        contents = await execute_mcp_tool(
            golden_engine, "get_notebook_summary", {"notebook_id": str(GOLDEN_NOTEBOOK_ID)}
        )
        assert len(contents) == 1
        data = json.loads(contents[0].text)

        assert data["notebook_id"] == str(GOLDEN_NOTEBOOK_ID)
        assert len(data["sources"]) == 1
        source = data["sources"][0]
        assert source["source_id"] == str(GOLDEN_SOURCE_ID)
        assert source["document_id"] == str(GOLDEN_DOC_ID)
        assert source["title"] == "Bhagavad-gita As It Is with pics!"


@pytest.mark.anyio
async def test_mcp_golden_corpus_get_source_insights() -> None:
    """Verify get_source_insights for the Golden Corpus source."""
    async with open_golden_engine() as golden_engine:
        contents = await execute_mcp_tool(
            golden_engine,
            "get_source_insights",
            {"source_id": str(GOLDEN_SOURCE_ID), "limit": 10},
        )
        assert len(contents) == 1
        data = json.loads(contents[0].text)

        assert data["source_id"] == str(GOLDEN_SOURCE_ID)
        assert data["notebook_id"] == str(GOLDEN_NOTEBOOK_ID)
        assert isinstance(data["insights"], list)


@pytest.mark.anyio
async def test_mcp_golden_corpus_get_timeline() -> None:
    """Verify get_timeline reconstructs chronological events for the Golden Corpus notebook."""
    async with open_golden_engine() as golden_engine:
        contents = await execute_mcp_tool(
            golden_engine, "get_timeline", {"notebook_id": str(GOLDEN_NOTEBOOK_ID), "limit": 50}
        )
        assert len(contents) == 1
        data = json.loads(contents[0].text)

        assert data["notebook_id"] == str(GOLDEN_NOTEBOOK_ID)
        assert data["total"] >= 1
        events = data["events"]
        assert any(e["event_type"] == "source_added" for e in events)


@pytest.mark.anyio
async def test_mcp_golden_corpus_search_factual() -> None:
    """Verify search_all_notebooks finds exact Bhagavad Gita passages on Karma-yoga."""
    async with open_golden_engine() as golden_engine:
        contents = await execute_mcp_tool(
            golden_engine,
            "search_all_notebooks",
            {
                "query": "Karma yoga duty Arjuna",
                "notebook_id": str(GOLDEN_NOTEBOOK_ID),
                "top_k": 5,
            },
        )
        assert len(contents) == 1
        data = json.loads(contents[0].text)

        assert len(data["results"]) > 0
        top_result = data["results"][0]
        assert top_result["document_id"] == str(GOLDEN_DOC_ID)
        assert (
            "CHAPTER THREE" in top_result["heading_path"]
            or "Karma-yoga" in top_result["heading_path"]
        )
        assert top_result["score"] > 0


@pytest.mark.anyio
async def test_mcp_golden_corpus_search_shloka() -> None:
    """Verify search_all_notebooks retrieves specific shloka keywords (BG 3.8 / 2.47)."""
    async with open_golden_engine() as golden_engine:
        contents = await execute_mcp_tool(
            golden_engine,
            "search_all_notebooks",
            {
                "query": "niyataṁ kuru karma tvaṁ karma jyāyo hy akarmaṇaḥ",
                "top_k": 3,
            },
        )
        assert len(contents) == 1
        data = json.loads(contents[0].text)

        assert len(data["results"]) > 0
        match = any("karma" in r["text"].lower() for r in data["results"])
        assert match


@pytest.mark.anyio
async def test_mcp_golden_corpus_query_grounded_synthesis() -> None:
    """Verify query_notebook with synthesis produces grounded answer and valid citations."""
    async with open_golden_engine() as golden_engine:
        contents = await execute_mcp_tool(
            golden_engine,
            "query_notebook",
            {
                "notebook_id": str(GOLDEN_NOTEBOOK_ID),
                "question": "What does Krishna teach about Karma-yoga?",
                "top_k": 5,
                "synthesize": True,
            },
        )
        assert len(contents) == 1
        data = json.loads(contents[0].text)

        assert "Karma-yoga" in data["answer"]
        assert len(data["citations"]) > 0
        citation = data["citations"][0]
        assert citation["document_title"] == "Bhagavad-gita As It Is with pics!"
        assert citation["quote"] != ""
        assert data["retrieval_metadata"]["chunks_retrieved"] > 0


@pytest.mark.anyio
async def test_mcp_golden_corpus_query_no_synthesis() -> None:
    """Verify query_notebook with synthesize=False returns raw evidence without synthesis."""
    async with open_golden_engine() as golden_engine:
        contents = await execute_mcp_tool(
            golden_engine,
            "query_notebook",
            {
                "notebook_id": str(GOLDEN_NOTEBOOK_ID),
                "question": "What does Krishna teach about Karma-yoga?",
                "top_k": 5,
                "synthesize": False,
            },
        )
        assert len(contents) == 1
        data = json.loads(contents[0].text)

        assert data["answer"] is None
        assert len(data["citations"]) > 0
        assert data["retrieval_metadata"]["chunks_used"] > 0


@pytest.mark.anyio
async def test_mcp_golden_corpus_query_unanswerable_negative() -> None:
    """Verify query_notebook handles out-of-domain unanswerable questions without hallucinations."""
    async with open_golden_engine() as golden_engine:
        contents = await execute_mcp_tool(
            golden_engine,
            "query_notebook",
            {
                "notebook_id": str(GOLDEN_NOTEBOOK_ID),
                "question": "What is quantum entanglement in superconductors?",
                "top_k": 5,
                "synthesize": True,
            },
        )
        assert len(contents) == 1
        data = json.loads(contents[0].text)

        assert "does not contain" in data["answer"].lower()


@pytest.mark.anyio
async def test_mcp_golden_corpus_negative_boundaries() -> None:
    """Verify invalid parameters and non-existent IDs fail deterministically."""
    async with open_golden_engine() as golden_engine:
        # 1. Invalid UUID format
        with pytest.raises(ContractValidationError):
            await execute_mcp_tool(
                golden_engine,
                "query_notebook",
                {"notebook_id": "not-a-uuid", "question": "test"},
            )

        # 2. Non-existent notebook
        with pytest.raises(NotFoundError):
            await execute_mcp_tool(
                golden_engine,
                "get_notebook_summary",
                {"notebook_id": str(uuid4())},
            )

        # 3. Invalid limit range
        with pytest.raises(ContractValidationError):
            await execute_mcp_tool(
                golden_engine,
                "list_notebooks",
                {"limit": 0},
            )

        # 4. Unknown tool
        with pytest.raises(ValueError, match="Unknown MCP tool"):
            await execute_mcp_tool(
                golden_engine,
                "delete_database",
                {},
            )


@pytest.mark.anyio
async def test_mcp_golden_corpus_security_isolation() -> None:
    """Verify that only 6 read-only knowledge tools are discoverable and no mutations exist."""
    async with open_golden_engine() as golden_engine:
        tools = get_mcp_tools()
        tool_names = [t.name for t in tools]
        assert len(tool_names) == 6
        assert set(tool_names) == {
            "query_notebook",
            "search_all_notebooks",
            "list_notebooks",
            "get_notebook_summary",
            "get_source_insights",
            "get_timeline",
        }

        # Verify no mutation or execution tools exist
        disallowed = [
            "exec",
            "eval",
            "shell",
            "bash",
            "python",
            "delete_notebook",
            "create_notebook",
            "ingest_file",
            "write_file",
        ]
        for prohibited in disallowed:
            assert prohibited not in tool_names
            with pytest.raises(ValueError, match="Unknown MCP tool"):
                await execute_mcp_tool(golden_engine, prohibited, {})
