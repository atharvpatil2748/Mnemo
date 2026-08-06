"""Public Phase 1 Module 1.2 interface contracts."""

from .chunker import ChunkerInterface
from .embedding import EmbeddingProvider
from .llm import LLMInterface
from .parser import ParserInterface
from .reranker import RerankerInterface
from .retriever import RetrieverInterface
from .storage import StorageInterface
from .types import (
    ChunkerCapabilities,
    ChunkingOptions,
    CompletionResult,
    EmbeddingBatch,
    EmbeddingCapabilities,
    EmbeddingVector,
    FileMetadata,
    HealthStatus,
    LLMCapabilities,
    Message,
    MessageRole,
    Page,
    ParserCapabilities,
    RerankerCapabilities,
    RetrieverCapabilities,
    StorageCapabilities,
)
from .versions import (
    CHUNKER_INTERFACE_VERSION,
    EMBEDDING_PROVIDER_INTERFACE_VERSION,
    LLM_INTERFACE_VERSION,
    PARSER_INTERFACE_VERSION,
    RERANKER_INTERFACE_VERSION,
    RETRIEVER_INTERFACE_VERSION,
    STORAGE_INTERFACE_VERSION,
)

__all__ = [
    "CHUNKER_INTERFACE_VERSION",
    "EMBEDDING_PROVIDER_INTERFACE_VERSION",
    "LLM_INTERFACE_VERSION",
    "PARSER_INTERFACE_VERSION",
    "RERANKER_INTERFACE_VERSION",
    "RETRIEVER_INTERFACE_VERSION",
    "STORAGE_INTERFACE_VERSION",
    "ChunkerCapabilities",
    "ChunkerInterface",
    "ChunkingOptions",
    "CompletionResult",
    "EmbeddingBatch",
    "EmbeddingCapabilities",
    "EmbeddingProvider",
    "EmbeddingVector",
    "FileMetadata",
    "HealthStatus",
    "LLMCapabilities",
    "LLMInterface",
    "Message",
    "MessageRole",
    "Page",
    "ParserCapabilities",
    "ParserInterface",
    "RerankerCapabilities",
    "RerankerInterface",
    "RetrieverCapabilities",
    "RetrieverInterface",
    "StorageCapabilities",
    "StorageInterface",
]
