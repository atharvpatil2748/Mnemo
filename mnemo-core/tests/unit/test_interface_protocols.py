"""Contract and conformance tests for Phase 1 Module 1.2 protocols."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import create_autospec
from uuid import UUID

import mnemo.interfaces as interfaces
from mnemo.interfaces import (
    CHUNKER_INTERFACE_VERSION,
    EMBEDDING_PROVIDER_INTERFACE_VERSION,
    LLM_INTERFACE_VERSION,
    PARSER_INTERFACE_VERSION,
    RERANKER_INTERFACE_VERSION,
    RETRIEVER_INTERFACE_VERSION,
    STORAGE_INTERFACE_VERSION,
    ChunkerCapabilities,
    ChunkerInterface,
    ChunkerInterfaceV1,
    ChunkingOptions,
    CompletionResult,
    EmbeddingBatch,
    EmbeddingCapabilities,
    EmbeddingProvider,
    EmbeddingProviderV1,
    FileMetadata,
    HealthStatus,
    LLMCapabilities,
    LLMInterface,
    LLMInterfaceV1,
    Message,
    ParserCapabilities,
    ParserInterface,
    ParserInterfaceV1,
    RerankerCapabilities,
    RerankerInterface,
    RerankerInterfaceV1,
    RetrieverCapabilities,
    RetrieverInterface,
    RetrieverInterfaceV1,
    StorageInterface,
    StorageInterfaceV1,
)
from mnemo.interfaces.parser_models import ParseResult
from mnemo.models import (
    Chunk,
    DocType,
    FrozenMetadata,
    JSONValue,
    MetadataFilter,
    ParsedDocument,
    ScoredChunk,
)


class ParserStub:
    """Trivial structural parser implementation for contract acceptance."""

    @property
    def supported_formats(self) -> tuple[str, ...]:
        """Return one supported format."""
        return (".txt",)

    def capabilities(self) -> ParserCapabilities:
        """Return parser capability metadata."""
        return ParserCapabilities(
            supported_formats=self.supported_formats,
            supports_tables=False,
            supports_images=False,
            supports_math=False,
            supports_ocr=False,
        )

    def parse(
        self,
        data: bytes,
        filename: str,
        metadata: FileMetadata,
    ) -> ParseResult:
        from mnemo.interfaces.parser_models import ParseResult, RawTextBlock
        from mnemo.models import DocType, DocumentMetadata

        return ParseResult(
            blocks=(RawTextBlock(ordinal=0, text="stub"),),
            extracted_assets=(),
            metadata=DocumentMetadata(
                content_hash="hash",
                title="Stub",
            ),
            language="en",
            doc_type=DocType.GENERIC,
        )


class ChunkerStub:
    """Trivial structural chunker implementation for contract acceptance."""

    @property
    def supported_doc_types(self) -> tuple[DocType, ...]:
        """Return one supported document type."""
        return (DocType.GENERIC,)

    def capabilities(self) -> ChunkerCapabilities:
        """Return chunker capability metadata."""
        return ChunkerCapabilities(
            supported_doc_types=self.supported_doc_types,
            preserves_semantic_boundaries=True,
            supports_parent_child=False,
            supports_overlap=True,
        )

    def chunk(
        self,
        document: ParsedDocument,
        version_id: UUID,
        options: ChunkingOptions,
    ) -> tuple[Chunk, ...]:
        """Return an empty acceptance-test result."""
        return ()


class EmbeddingStub:
    """Trivial structural embedding provider for contract acceptance."""

    @property
    def model_name(self) -> str:
        """Return a stable model identity."""
        return "test/model"

    @property
    def dimensions(self) -> int:
        """Return one output dimension."""
        return 1

    @property
    def max_tokens(self) -> int:
        """Return a test context limit."""
        return 32

    def capabilities(self) -> EmbeddingCapabilities:
        """Return provider capability metadata."""
        return EmbeddingCapabilities(
            dimensions=1,
            supports_batch=True,
            max_batch=2,
            multilingual=False,
            supports_normalization=False,
        )

    async def embed(self, text: str) -> tuple[float, ...]:
        """Return one deterministic test vector."""
        return (1.0,)

    async def embed_batch(self, texts: tuple[str, ...]) -> EmbeddingBatch:
        """Return one vector per input text."""
        return EmbeddingBatch(
            vectors=tuple((1.0,) for _ in texts),
            model_name=self.model_name,
            dimensions=self.dimensions,
        )

    async def health_check(self) -> HealthStatus:
        """The acceptance stub is always healthy."""
        raise NotImplementedError


class RetrieverStub:
    """Trivial structural retriever for contract acceptance."""

    @property
    def retrieval_mode(self) -> str:
        """Return a stable test retrieval mode."""
        return "test"

    def capabilities(self) -> RetrieverCapabilities:
        """Return retriever capability metadata."""
        return RetrieverCapabilities(
            supports_hybrid=False,
            supports_metadata_filters=True,
            supports_parent_child=False,
            supports_reranking=False,
        )

    async def retrieve(
        self,
        query: str,
        query_embedding: tuple[float, ...] | None,
        filters: MetadataFilter,
        top_k: int,
    ) -> tuple[ScoredChunk, ...]:
        """Return an empty acceptance-test result."""
        return ()


class RerankerStub:
    """Trivial structural reranker for contract acceptance."""

    def capabilities(self) -> RerankerCapabilities:
        """Return reranker capability metadata."""
        return RerankerCapabilities(
            supports_cross_encoder=False,
            supports_batch=True,
            preserves_raw_scores=True,
        )

    async def rerank(
        self,
        query: str,
        candidates: tuple[ScoredChunk, ...],
        top_k: int,
    ) -> tuple[ScoredChunk, ...]:
        """Return the bounded input candidates unchanged."""
        return candidates[:top_k]


class LLMStub:
    """Trivial structural language-model provider for contract acceptance."""

    @property
    def provider(self) -> str:
        """Return a stable provider identity."""
        return "test"

    @property
    def model(self) -> str:
        """Return a stable model identity."""
        return "model"

    @property
    def max_context_tokens(self) -> int:
        """Return a test context limit."""
        return 128

    def capabilities(self) -> LLMCapabilities:
        """Return language-model capability metadata."""
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
        structured_output: JSONValue = None,
        max_tokens: int = 1000,
    ) -> CompletionResult:
        """Return a deterministic completion."""
        return CompletionResult(model=self.model, text="complete")

    def stream(
        self,
        system: str,
        messages: tuple[Message, ...],
        max_tokens: int = 1000,
    ) -> AsyncIterator[str]:
        """Return a deterministic asynchronous text stream."""
        return self._stream()

    async def health_check(self) -> HealthStatus:
        """Return no concrete health behavior in the acceptance stub."""
        raise NotImplementedError

    async def _stream(self) -> AsyncIterator[str]:
        yield "complete"


def _accept_parser(value: ParserInterface) -> ParserInterface:
    return value


def _accept_chunker(value: ChunkerInterface) -> ChunkerInterface:
    return value


def _accept_embedding(value: EmbeddingProvider) -> EmbeddingProvider:
    return value


def _accept_retriever(value: RetrieverInterface) -> RetrieverInterface:
    return value


def _accept_reranker(value: RerankerInterface) -> RerankerInterface:
    return value


def _accept_llm(value: LLMInterface) -> LLMInterface:
    return value


def test_structural_protocol_conformance() -> None:
    """Trivial implementations satisfy contracts without inheritance."""
    implementations = (
        (_accept_parser(ParserStub()), ParserInterface),
        (_accept_chunker(ChunkerStub()), ChunkerInterface),
        (_accept_embedding(EmbeddingStub()), EmbeddingProvider),
        (_accept_retriever(RetrieverStub()), RetrieverInterface),
        (_accept_reranker(RerankerStub()), RerankerInterface),
        (_accept_llm(LLMStub()), LLMInterface),
    )

    assert all(isinstance(value, contract) for value, contract in implementations)
    assert not isinstance(object(), ParserInterface)


def test_storage_protocol_is_structural_and_complete() -> None:
    """The atomic facade exposes its complete structural method surface."""
    storage = create_autospec(StorageInterface, instance=True)
    required = {
        "open",
        "close",
        "capabilities",
        "put_asset",
        "upsert_document",
        "upsert_notebook",
        "upsert_session",
        "upsert_entity",
        "upsert_chunks",
        "search_dense",
        "search_sparse",
        "delete_document_cascade",
    }

    assert isinstance(storage, StorageInterface)
    assert required <= set(dir(storage))


def test_interface_versions_are_explicit_and_consistent() -> None:
    """Every implemented Module 1.2 contract publishes its V1 marker."""
    assert {
        PARSER_INTERFACE_VERSION,
        CHUNKER_INTERFACE_VERSION,
        EMBEDDING_PROVIDER_INTERFACE_VERSION,
        RETRIEVER_INTERFACE_VERSION,
        RERANKER_INTERFACE_VERSION,
        LLM_INTERFACE_VERSION,
        STORAGE_INTERFACE_VERSION,
    } == {"v1"}
    assert ParserInterface is ParserInterfaceV1
    assert ChunkerInterface is ChunkerInterfaceV1
    assert EmbeddingProvider is EmbeddingProviderV1
    assert RetrieverInterface is RetrieverInterfaceV1
    assert RerankerInterface is RerankerInterfaceV1
    assert LLMInterface is LLMInterfaceV1
    assert StorageInterface is StorageInterfaceV1


def test_later_roadmap_contracts_are_not_implemented() -> None:
    """Module 1.3 and later contract symbols remain specification-only."""
    forbidden = {
        "PluginRegistry",
        "EventBusInterface",
        "TaskQueueInterface",
        "ProgressReporter",
        "TelemetryInterface",
        "CacheInterface",
        "EmbedderInterface",
        "DenseRetriever",
        "SparseRetriever",
        "HybridRetriever",
        "GraphRetriever",
    }
    assert forbidden.isdisjoint(interfaces.__all__)


def test_interface_package_has_no_forbidden_infrastructure_dependencies() -> None:
    """Core contract source remains transport and infrastructure independent."""
    package_dir = Path(interfaces.__file__).parent
    source = "\n".join(path.read_text(encoding="utf-8") for path in package_dir.glob("*.py"))
    forbidden = ("fastapi", "starlette", "httpx", "qdrant", "surrealdb", "mcp", "docker")

    assert not any(name in source.lower() for name in forbidden)


def test_stub_methods_remain_callable_contract_examples() -> None:
    """Acceptance stubs demonstrate capability inspection without behavior."""
    assert ParserStub().capabilities().supported_formats == (".txt",)
    assert ChunkerStub().capabilities().supported_doc_types == (DocType.GENERIC,)
    assert EmbeddingStub().capabilities().dimensions == 1
    assert RetrieverStub().retrieval_mode == "test"
    assert RerankerStub().capabilities().preserves_raw_scores
    assert LLMStub().model == "model"
    assert FrozenMetadata() == FrozenMetadata()
