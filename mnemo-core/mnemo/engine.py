"""Thin, transport-independent runtime composition for Mnemo core."""

from __future__ import annotations

import asyncio
import importlib
import logging
import warnings
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from mnemo._version import __version__
from mnemo.config import MnemoConfig
from mnemo.interfaces import (
    DependencyUnavailableError,
    EmbeddingCapabilities,
    EmbeddingProviderV1,
    FinalQAExecutionStoreV1,
    FinalQAInterfaceV1,
    LifecycleError,
    LLMCapabilities,
    LLMInterfaceV1,
    MnemoInterfaceError,
    RerankerCapabilities,
    RerankerInterfaceV1,
    StorageCapabilities,
    StorageInterfaceV1,
    TokenCounterInterfaceV1,
)
from mnemo.registry import PluginInterfaceV1, PluginLoadResult, PluginRegistry

_LOGGER = logging.getLogger(__name__)
_PRIMARY_SLOT = "primary"
_LLM_ROLES = ("planner", "synthesizer", "extractor", "classifier")
_REQUIRED_CAPABILITIES = frozenset({"storage", "embedding_provider", "reranker", "llm"})
type _LLMRole = Literal["planner", "synthesizer", "extractor", "classifier"]
type _ProviderCapability = (
    StorageCapabilities | EmbeddingCapabilities | RerankerCapabilities | LLMCapabilities
)


class EngineState(StrEnum):
    """Lifecycle states of one KnowledgeEngine runtime instance."""

    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    READY = "ready"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class KnowledgeEngineError(MnemoInterfaceError):
    """Base exception for KnowledgeEngine composition failures."""

    code = "engine.error"


class EngineLifecycleError(KnowledgeEngineError, LifecycleError):
    """An operation is invalid for the engine's current lifecycle state."""

    code = "engine.lifecycle"


class EngineInitializationError(KnowledgeEngineError, DependencyUnavailableError):
    """Runtime discovery, resolution, or structural validation failed."""

    code = "engine.initialization"


@dataclass(frozen=True, slots=True)
class _ResolvedProviders:
    storage: StorageInterfaceV1
    embedding: EmbeddingProviderV1
    reranker: RerankerInterfaceV1
    planner: LLMInterfaceV1
    synthesizer: LLMInterfaceV1
    extractor: LLMInterfaceV1
    classifier: LLMInterfaceV1
    capabilities: Mapping[str, _ProviderCapability]


@dataclass(frozen=True, slots=True)
class FinalQAComponents:
    """Explicit local resources required to compose ADR-0046."""

    token_counter: TokenCounterInterfaceV1
    clock: Callable[[], datetime]

    def __post_init__(self) -> None:
        if not isinstance(self.token_counter, TokenCounterInterfaceV1):
            raise TypeError("token_counter must implement TokenCounterInterfaceV1")
        if not callable(self.clock):
            raise TypeError("clock must be callable")


class KnowledgeEngine:
    """Compose and validate one Mnemo core runtime from frozen configuration."""

    def __init__(
        self,
        config: MnemoConfig,
        *,
        final_qa_components: FinalQAComponents | None = None,
    ) -> None:
        """Create an uninitialized runtime without performing discovery or I/O."""
        if not isinstance(config, MnemoConfig):
            raise TypeError("config must be MnemoConfig")
        if final_qa_components is not None and not isinstance(
            final_qa_components, FinalQAComponents
        ):
            raise TypeError("final_qa_components must be FinalQAComponents or None")
        self._config = config
        self._final_qa_components = final_qa_components
        self._final_qa: FinalQAInterfaceV1 | None = None
        self._registry = self._new_registry()
        self._state = EngineState.UNINITIALIZED
        self._providers: _ResolvedProviders | None = None
        self._lifecycle_lock = asyncio.Lock()

    @property
    def config(self) -> MnemoConfig:
        """Return the exact frozen runtime configuration."""
        return self._config

    @property
    def registry(self) -> PluginRegistry:
        """Return the current registry owned by this engine."""
        return self._registry

    @property
    def state(self) -> EngineState:
        """Return the current lifecycle state."""
        return self._state

    @property
    def version(self) -> str:
        """Return the Mnemo package version."""
        return __version__

    @property
    def storage(self) -> StorageInterfaceV1:
        """Return the resolved primary storage façade while ready."""
        return self._require_ready().storage

    @property
    def embedding_provider(self) -> EmbeddingProviderV1:
        """Return the resolved primary embedding provider while ready."""
        return self._require_ready().embedding

    @property
    def reranker(self) -> RerankerInterfaceV1:
        """Return the resolved primary reranker while ready."""
        return self._require_ready().reranker

    @property
    def final_qa(self) -> FinalQAInterfaceV1:
        """Return the configured final-QA graph while ready."""
        self._require_ready()
        if self._final_qa is None:
            raise DependencyUnavailableError("final QA components were not supplied")
        return self._final_qa

    def llm(self, role: _LLMRole) -> LLMInterfaceV1:
        """Return the resolved language model for one fixed role while ready."""
        providers = self._require_ready()
        match role:
            case "planner":
                return providers.planner
            case "synthesizer":
                return providers.synthesizer
            case "extractor":
                return providers.extractor
            case "classifier":
                return providers.classifier
            case _:
                raise ValueError(f"unknown LLM role: {role}")

    def capabilities(self) -> Mapping[str, _ProviderCapability]:
        """Return immutable capabilities advertised by resolved providers."""
        return self._require_ready().capabilities

    async def initialize(self) -> None:
        """Discover and atomically validate the configured runtime."""
        async with self._lifecycle_lock:
            if self._state is EngineState.READY:
                return
            if self._state is EngineState.FAILED:
                raise EngineLifecycleError("a failed KnowledgeEngine cannot be initialized")
            if self._state in (EngineState.INITIALIZING, EngineState.STOPPING):
                raise EngineLifecycleError(f"cannot initialize while engine is {self._state.value}")
            if self._state is EngineState.STOPPED:
                self._registry = self._new_registry()
            self._state = EngineState.INITIALIZING
            try:
                self._compose_runtime()
                await self._registry.execute_startup_hooks()
                self._registry.freeze()
                providers = self._resolve_providers()
                final_qa = self._compose_final_qa(providers)
            except Exception as error:
                with suppress(Exception):
                    await self._registry.execute_shutdown_hooks()
                self._providers = None
                self._final_qa = None
                self._registry = self._new_registry()
                self._state = EngineState.FAILED
                if isinstance(error, EngineInitializationError):
                    raise
                raise EngineInitializationError(
                    "KnowledgeEngine initialization failed",
                ) from error
            self._providers = providers
            self._final_qa = final_qa
            self._state = EngineState.READY

    async def startup(self) -> None:
        """Deprecated alias for initialize()."""
        warnings.warn(
            "KnowledgeEngine.startup() is deprecated; use initialize()",
            DeprecationWarning,
            stacklevel=2,
        )
        await self.initialize()

    async def shutdown(self) -> None:
        """Apply Phase 1 lifecycle shutdown without contacting providers."""
        async with self._lifecycle_lock:
            if self._state in (EngineState.UNINITIALIZED, EngineState.STOPPED):
                return
            if self._state is EngineState.FAILED:
                self._providers = None
                self._final_qa = None
                return
            if self._state in (EngineState.INITIALIZING, EngineState.STOPPING):
                raise EngineLifecycleError(f"cannot shut down while engine is {self._state.value}")
            self._state = EngineState.STOPPING
            try:
                await self._registry.execute_shutdown_hooks()
            finally:
                self._providers = None
                self._final_qa = None
                self._state = EngineState.STOPPED

    def _compose_runtime(self) -> None:
        results: list[PluginLoadResult] = []
        builtins = self._registry.load_plugins(_builtin_plugins(self._config))
        self._log_failures("built-in", builtins)
        results.extend(builtins)
        entry_points = self._registry.discover_and_load_entry_points()
        self._log_failures("entry-point", entry_points)
        results.extend(entry_points)
        candidates = _plugin_candidates(self._config.plugins.directory)
        paths = self._registry.discover_and_load_paths(candidates)
        self._log_failures("path", paths)
        results.extend(paths)
        _reject_required_plugin_failures(tuple(results))

    def _compose_final_qa(self, providers: _ResolvedProviders) -> FinalQAInterfaceV1 | None:
        components = self._final_qa_components
        if components is None:
            return None
        counter = components.token_counter
        tokenizer_id = importlib.import_module("mnemo.tokenizers").O200K_BASE_TOKENIZER_ID
        if counter.tokenizer_id != tokenizer_id or counter.count("") != 0:
            raise EngineInitializationError("canonical final-QA token counter is unavailable")
        for slot in ("dense", "sparse"):
            if self._registry.resolve_retriever(slot) is None:
                raise EngineInitializationError(f"required retriever '{slot}' is unavailable")
        if self._registry.resolve_parent_promoter("default") is None:
            raise EngineInitializationError("required parent promoter 'default' is unavailable")
        from mnemo.retrieval import (
            CitationEngine,
            ContextBuilder,
            FinalQAOrchestrator,
            GroundedAnswerGenerator,
            MultiSourceRetriever,
            QueryPlanner,
            RerankingModule,
        )

        planner = QueryPlanner(providers.planner, providers.embedding)
        fusion = MultiSourceRetriever(self._registry, providers.embedding)
        reranker = RerankingModule(self._registry)
        context = ContextBuilder(self._registry, counter)
        answer = GroundedAnswerGenerator(self._registry, counter)
        citation = CitationEngine(providers.storage, components.clock)
        return FinalQAOrchestrator(
            planner,
            fusion,
            reranker,
            context,
            answer,
            citation,
            providers.storage,
            components.clock,
            (providers.storage if isinstance(providers.storage, FinalQAExecutionStoreV1) else None),
        )

    def _resolve_providers(self) -> _ResolvedProviders:
        storage = self._registry.resolve_storage(_PRIMARY_SLOT)
        embedding = self._registry.resolve_embedding_provider(_PRIMARY_SLOT)
        reranker = self._registry.resolve_reranker(_PRIMARY_SLOT)
        llms = {role: self._registry.resolve_llm(role) for role in _LLM_ROLES}

        if storage is None:
            raise EngineInitializationError("required storage provider 'primary' is unavailable")
        if embedding is None:
            raise EngineInitializationError("required embedding provider 'primary' is unavailable")
        if reranker is None:
            raise EngineInitializationError("required reranker 'primary' is unavailable")
        missing_roles = tuple(role for role, provider in llms.items() if provider is None)
        if missing_roles:
            raise EngineInitializationError(
                f"required LLM providers are unavailable: {', '.join(missing_roles)}"
            )

        planner = _require_llm(llms["planner"], "planner")
        synthesizer = _require_llm(llms["synthesizer"], "synthesizer")
        extractor = _require_llm(llms["extractor"], "extractor")
        classifier = _require_llm(llms["classifier"], "classifier")
        capabilities: dict[str, _ProviderCapability] = {
            "storage": _storage_capabilities(storage),
            "embedding": _embedding_capabilities(
                embedding,
                expected_dimensions=self._config.embedding.dimensions,
            ),
            "reranker": _reranker_capabilities(reranker),
            "planner": _llm_capabilities(planner, "planner"),
            "synthesizer": _llm_capabilities(synthesizer, "synthesizer"),
            "extractor": _llm_capabilities(extractor, "extractor"),
            "classifier": _llm_capabilities(classifier, "classifier"),
        }
        return _ResolvedProviders(
            storage=storage,
            embedding=embedding,
            reranker=reranker,
            planner=planner,
            synthesizer=synthesizer,
            extractor=extractor,
            classifier=classifier,
            capabilities=MappingProxyType(capabilities),
        )

    def _require_ready(self) -> _ResolvedProviders:
        if self._state is not EngineState.READY or self._providers is None:
            raise EngineLifecycleError("resolved providers are available only while READY")
        return self._providers

    def _new_registry(self) -> PluginRegistry:
        return PluginRegistry(core_version=self.version)

    @staticmethod
    def _log_failures(source: str, results: tuple[PluginLoadResult, ...]) -> None:
        for result in results:
            if not result.loaded:
                _LOGGER.warning(
                    "%s plugin %s failed discovery: %s (%s)",
                    source,
                    result.descriptor.name,
                    result.error_message,
                    result.error_code,
                )


def _builtin_plugins(config: MnemoConfig) -> tuple[PluginInterfaceV1, ...]:
    """Return built-in candidates supplied by their designated roadmap modules."""
    primary_storage: StorageInterfaceV1 | None = None

    class CoreStoragePlugin:
        name = "mnemo-core-storage"
        version = __version__
        core_version_range = ">=0.0.0"

        def capabilities(self) -> tuple[str, ...]:
            return ("storage",)

        def register(self, registry: PluginRegistry) -> None:
            nonlocal primary_storage
            from mnemo.storage import (
                CompositeStorage,
                FilesystemBlobStore,
                QdrantStore,
                SQLiteStore,
                SurrealDBStore,
            )

            filesystem = FilesystemBlobStore(config.storage.filesystem.root)
            sqlite = SQLiteStore(config.storage.sqlite.path)
            qdrant = QdrantStore(
                config.storage.qdrant,
                vector_dimensions=config.embedding.dimensions,
            )
            surrealdb = SurrealDBStore(config.storage.surrealdb)

            composite = CompositeStorage(
                filesystem=filesystem,
                sqlite=sqlite,
                qdrant=qdrant,
                surrealdb=surrealdb,
            )
            primary_storage = composite

            # Core priority permits an explicitly higher-priority provider override.
            registry.register_storage("primary", composite, priority=0)

            async def open_when_active() -> None:
                if registry.resolve_storage("primary") is composite:
                    await composite.open()

            async def close_when_active() -> None:
                if registry.resolve_storage("primary") is composite:
                    await composite.close()

            registry.register_startup_hook(open_when_active)
            registry.register_shutdown_hook(close_when_active)

    class CoreRetrievalPlugin:
        name = "mnemo-core-retrieval"
        version = __version__
        core_version_range = ">=0.0.0"

        def capabilities(self) -> tuple[str, ...]:
            return ("retriever", "parent_promotion")

        def register(self, registry: PluginRegistry) -> None:
            from mnemo.retrieval import DenseRetriever, ParentRetriever, SparseRetriever

            if primary_storage is None:
                raise EngineInitializationError("primary storage must register before retrieval")
            registry.register_retriever("dense", DenseRetriever(primary_storage), priority=0)
            registry.register_retriever("sparse", SparseRetriever(primary_storage), priority=0)
            registry.register_parent_promoter(
                "default", ParentRetriever(primary_storage), priority=0
            )

    class CoreParserPlugin:
        name = "mnemo-core-parsers"
        version = __version__
        core_version_range = ">=0.0.0"

        def capabilities(self) -> tuple[str, ...]:
            return ("parser",)

        def register(self, registry: PluginRegistry) -> None:
            from mnemo.parsers import (
                CSVParser,
                DOCXParser,
                HTMLParser,
                JSONParser,
                MarkdownParser,
                PDFParser,
                PlainTextParser,
                PPTXParser,
                XLSXParser,
            )

            plain_text_parser = PlainTextParser()
            parsers = (
                (PDFParser(), (".pdf", "application/pdf")),
                (
                    DOCXParser(),
                    (
                        ".docx",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ),
                ),
                (
                    PPTXParser(),
                    (
                        ".pptx",
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    ),
                ),
                (MarkdownParser(), (".md", ".markdown", "text/markdown", "text/x-markdown")),
                (HTMLParser(), (".html", ".htm", "text/html")),
                (
                    plain_text_parser,
                    (
                        ".txt",
                        ".log",
                        "text/plain",
                        # Code file extensions — parsed as RawCodeBlock by PlainTextParser
                        ".c",
                        ".cc",
                        ".cpp",
                        ".cxx",
                        ".go",
                        ".h",
                        ".hpp",
                        ".java",
                        ".js",
                        ".jsx",
                        ".py",
                        ".rs",
                        ".ts",
                        ".tsx",
                        # MIME types that mimetypes / libmagic detect for code files
                        "text/javascript",
                        "text/x-python",
                        "text/x-c",
                        "text/x-c++",
                        "text/x-java",
                        "text/x-go",
                        "text/x-rust",
                    ),
                ),
                (JSONParser(), (".json", "application/json")),
                (CSVParser(), (".csv", ".tsv", "text/csv", "text/tab-separated-values")),
                (
                    XLSXParser(),
                    (
                        ".xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ),
                ),
            )
            for parser, slots in parsers:
                for slot in slots:
                    registry.register_parser(slot, parser, priority=0)

    class CoreChunkerPlugin:
        name = "mnemo-core-chunkers"
        version = __version__
        core_version_range = ">=0.0.0"

        def capabilities(self) -> tuple[str, ...]:
            return ("chunker",)

        def register(self, registry: PluginRegistry) -> None:
            from mnemo.chunkers import (
                BookChunker,
                CodeChunker,
                DocumentationChunker,
                EmailChunker,
                GenericChunker,
                MarkdownChunker,
                PaperChunker,
                ResumeChunker,
                SlidesChunker,
            )
            from mnemo.models import DocType

            registry.register_chunker_v2(DocType.GENERIC, GenericChunker(), priority=0)
            registry.register_chunker_v2(DocType.BOOK, BookChunker(), priority=0)
            registry.register_chunker_v2(DocType.PAPER, PaperChunker(), priority=0)
            registry.register_chunker_v2(DocType.CODE, CodeChunker(), priority=0)
            registry.register_chunker_v2(DocType.MARKDOWN, MarkdownChunker(), priority=0)
            registry.register_chunker_v2(DocType.EMAIL, EmailChunker(), priority=0)
            registry.register_chunker_v2(DocType.RESUME, ResumeChunker(), priority=0)
            registry.register_chunker_v2(DocType.SLIDES, SlidesChunker(), priority=0)
            registry.register_chunker_v2(DocType.DOCUMENTATION, DocumentationChunker(), priority=0)

    class CoreEmbeddingPlugin:
        name = "mnemo-core-embedding"
        version = __version__
        core_version_range = ">=0.0.0"

        def capabilities(self) -> tuple[str, ...]:
            return ("embedding",)

        def register(self, registry: PluginRegistry) -> None:
            from mnemo.embeddings.cached import CachedEmbeddingProvider
            from mnemo.embeddings.ollama import OllamaEmbedder
            from mnemo.storage.cache import SQLiteEmbeddingCache

            ollama = OllamaEmbedder(config.embedding)
            cache = SQLiteEmbeddingCache(config.storage.sqlite.path.parent / "embedding-cache.db")
            cached = CachedEmbeddingProvider(ollama, cache)
            registry.register_embedding_provider("primary", cached, priority=0)
            registry.register_startup_hook(cache.initialize)
            registry.register_startup_hook(ollama.initialize)

    class CoreLLMPlugin:
        name = "mnemo-core-llm"
        version = __version__
        core_version_range = ">=0.0.0"

        def capabilities(self) -> tuple[str, ...]:
            return ("llm",)

        def register(self, registry: PluginRegistry) -> None:
            from mnemo.llms import OllamaLLM

            for role in _LLM_ROLES:
                role_config = getattr(config.llm, role)
                if role_config.provider != "ollama":
                    continue
                provider = OllamaLLM(role_config)
                registry.register_llm(role, provider, priority=0)
                registry.register_startup_hook(provider.initialize)
                registry.register_shutdown_hook(provider.close)

    plugins: list[PluginInterfaceV1] = [
        CoreStoragePlugin(),
        CoreRetrievalPlugin(),
        CoreParserPlugin(),
        CoreChunkerPlugin(),
        CoreEmbeddingPlugin(),
        CoreLLMPlugin(),
    ]
    if config.reranker.provider == "sentence-transformers":
        from mnemo.retrieval.reranker import CrossEncoderReranker, CrossEncoderRerankerPlugin

        plugins.append(CrossEncoderRerankerPlugin(CrossEncoderReranker(config.reranker)))
    return tuple(plugins)


def _plugin_candidates(directory: Path) -> tuple[Path, ...]:
    """Return deterministic immediate Python plugin candidates."""
    if not directory.is_dir():
        raise EngineInitializationError(f"plugin directory is unavailable: {directory}")
    try:
        children = tuple(directory.iterdir())
    except OSError as error:
        raise EngineInitializationError(f"plugin directory cannot be read: {directory}") from error
    candidates = (
        child
        for child in children
        if not child.name.startswith(".")
        and (child.suffix == ".py" or (child.is_dir() and (child / "__init__.py").is_file()))
    )
    return tuple(sorted(candidates, key=lambda path: str(path)))


def _reject_required_plugin_failures(results: tuple[PluginLoadResult, ...]) -> None:
    """Reject failed plugins that advertise a Phase 1 required capability."""
    failed = tuple(
        result.descriptor.name
        for result in results
        if not result.loaded
        and not _REQUIRED_CAPABILITIES.isdisjoint(result.descriptor.capabilities)
    )
    if failed:
        raise EngineInitializationError(
            f"plugins providing required capabilities failed: {', '.join(failed)}"
        )


def _storage_capabilities(provider: StorageInterfaceV1) -> StorageCapabilities:
    if not isinstance(provider, StorageInterfaceV1):
        raise EngineInitializationError("primary storage does not implement StorageInterfaceV1")
    capabilities = provider.capabilities()
    if not isinstance(capabilities, StorageCapabilities):
        raise EngineInitializationError("primary storage returned invalid capabilities")
    return capabilities


def _embedding_capabilities(
    provider: EmbeddingProviderV1,
    *,
    expected_dimensions: int,
) -> EmbeddingCapabilities:
    if not isinstance(provider, EmbeddingProviderV1):
        raise EngineInitializationError(
            "primary embedding provider does not implement EmbeddingProviderV1"
        )
    capabilities = provider.capabilities()
    if not isinstance(capabilities, EmbeddingCapabilities):
        raise EngineInitializationError("primary embedding provider returned invalid capabilities")
    if provider.dimensions != expected_dimensions or capabilities.dimensions != expected_dimensions:
        raise EngineInitializationError("embedding dimensions do not match configuration")
    return capabilities


def _reranker_capabilities(provider: RerankerInterfaceV1) -> RerankerCapabilities:
    if not isinstance(provider, RerankerInterfaceV1):
        raise EngineInitializationError("primary reranker does not implement RerankerInterfaceV1")
    capabilities = provider.capabilities()
    if not isinstance(capabilities, RerankerCapabilities):
        raise EngineInitializationError("primary reranker returned invalid capabilities")
    return capabilities


def _require_llm(provider: LLMInterfaceV1 | None, role: str) -> LLMInterfaceV1:
    if provider is None or not isinstance(provider, LLMInterfaceV1):
        raise EngineInitializationError(f"{role} does not implement LLMInterfaceV1")
    if not isinstance(provider.provider, str) or not provider.provider.strip():
        raise EngineInitializationError(f"{role} LLM does not declare a provider")
    if not isinstance(provider.model, str) or not provider.model.strip():
        raise EngineInitializationError(f"{role} LLM does not declare a model")
    return provider


def _llm_capabilities(provider: LLMInterfaceV1, role: str) -> LLMCapabilities:
    capabilities = provider.capabilities()
    if not isinstance(capabilities, LLMCapabilities):
        raise EngineInitializationError(f"{role} LLM returned invalid capabilities")
    return capabilities
