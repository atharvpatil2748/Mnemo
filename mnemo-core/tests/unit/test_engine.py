"""Unit tests for the Phase 1 Module 1.5 KnowledgeEngine composition root."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import cast
from unittest.mock import Mock, create_autospec

import pytest
from mnemo import (
    EmbeddingConfig,
    EngineInitializationError,
    EngineLifecycleError,
    EngineState,
    KnowledgeEngine,
    LLMConfig,
    LLMRoleConfig,
    MnemoConfig,
    PluginConfig,
    PluginRegistry,
    RerankerConfig,
    StorageConfig,
    __version__,
)
from mnemo.engine import (
    FinalQAComponents,
    _builtin_plugins,
    _embedding_capabilities,
    _llm_capabilities,
    _plugin_candidates,
    _require_llm,
    _reranker_capabilities,
    _ResolvedProviders,
    _storage_capabilities,
    _V2OwnedOuterPassThroughReranker,
)
from mnemo.interfaces import (
    DependencyUnavailableError,
    EmbeddingCapabilities,
    EmbeddingProviderV1,
    LLMCapabilities,
    LLMInterfaceV1,
    ParentPromotionInterfaceV1,
    RerankerCapabilities,
    RerankerInterfaceV1,
    RetrieverInterfaceV1,
    StorageCapabilities,
    StorageInterfaceV1,
)
from mnemo.interfaces.advanced_retrieval import AdvancedRetrievalSourceV1
from mnemo.models import EvidenceRepresentation
from mnemo.registry import PluginInterfaceV1, RegistryState
from mnemo.retrieval import RetrievalCursorCodec
from mnemo.tokenizers import O200K_BASE_TOKENIZER_ID


@dataclass(slots=True)
class RuntimePlugin:
    """Test plugin that delegates registration to one typed callback."""

    name: str
    callback: Callable[[PluginRegistry], None]
    capabilities_value: tuple[str, ...] = ("storage", "embedding_provider", "reranker", "llm")
    version: str = "1.0.0"
    core_version_range: str = ">=0.0.0"

    def capabilities(self) -> tuple[str, ...]:
        """Return advertised test capability families."""
        return self.capabilities_value

    def register(self, registry: PluginRegistry) -> None:
        """Register the configured test providers."""
        self.callback(registry)


@dataclass(frozen=True, slots=True)
class Providers:
    """References to protocol-shaped provider mocks used for assertions."""

    storage: StorageInterfaceV1
    embedding: EmbeddingProviderV1
    reranker: RerankerInterfaceV1
    llm: LLMInterfaceV1


def make_config(tmp_path: Path, *, dimensions: int = 3) -> MnemoConfig:
    """Build one frozen configuration without reading environment state."""
    role = LLMRoleConfig(provider="test", model="model", max_context_tokens=128)
    return MnemoConfig(
        storage=StorageConfig(),
        llm=LLMConfig(
            planner=role,
            synthesizer=role,
            extractor=role,
            classifier=role,
        ),
        embedding=EmbeddingConfig(provider="test", model="embedding", dimensions=dimensions),
        reranker=RerankerConfig(provider="test", model="reranker"),
        plugins=PluginConfig(directory=tmp_path / "plugins"),
    )


def make_providers(*, dimensions: int = 3) -> Providers:
    """Create structurally valid provider mocks with immutable capabilities."""
    storage_mock = create_autospec(StorageInterfaceV1, instance=True)
    storage_mock.capabilities.return_value = StorageCapabilities(
        supports_blobs=True,
        supports_dense_search=True,
        supports_sparse_search=True,
        supports_metadata=True,
        supports_graph=True,
        supports_transactions=True,
        supports_health_checks=True,
    )
    embedding_mock = create_autospec(EmbeddingProviderV1, instance=True)
    embedding_mock.dimensions = dimensions
    embedding_mock.capabilities.return_value = EmbeddingCapabilities(
        dimensions=dimensions,
        supports_batch=True,
        max_batch=8,
        multilingual=False,
        supports_normalization=True,
    )
    reranker_mock = create_autospec(RerankerInterfaceV1, instance=True)
    reranker_mock.capabilities.return_value = RerankerCapabilities(
        supports_cross_encoder=True,
        supports_batch=True,
        preserves_raw_scores=False,
    )
    llm_mock = create_autospec(LLMInterfaceV1, instance=True)
    llm_mock.provider = "test"
    llm_mock.model = "model"
    llm_mock.capabilities.return_value = LLMCapabilities(
        supports_streaming=False,
        supports_json=True,
        supports_vision=False,
        supports_reasoning=False,
    )
    return Providers(
        storage=cast(StorageInterfaceV1, storage_mock),
        embedding=cast(EmbeddingProviderV1, embedding_mock),
        reranker=cast(RerankerInterfaceV1, reranker_mock),
        llm=cast(LLMInterfaceV1, llm_mock),
    )


def runtime_plugin(providers: Providers, *, name: str = "runtime") -> RuntimePlugin:
    """Build a plugin that supplies every required Phase 1 slot."""

    def register(registry: PluginRegistry) -> None:
        registry.register_storage("primary", providers.storage, priority=10)
        registry.register_embedding_provider("primary", providers.embedding, priority=10)
        registry.register_reranker("primary", providers.reranker, priority=10)
        for role in ("planner", "synthesizer", "extractor", "classifier"):
            registry.register_llm(role, providers.llm, priority=10)

    return RuntimePlugin(name=name, callback=register)


def install_builtins(
    monkeypatch: pytest.MonkeyPatch,
    *plugins: PluginInterfaceV1,
) -> None:
    """Supply deterministic built-in candidates to the composition root."""
    monkeypatch.setattr("mnemo.engine._builtin_plugins", lambda config: plugins)
    monkeypatch.setattr(
        PluginRegistry,
        "discover_and_load_entry_points",
        lambda self: (),
    )


def test_construction_is_inert_and_public_metadata_is_read_only(tmp_path: Path) -> None:
    """Construction owns one registry but performs no discovery or resolution."""
    config = make_config(tmp_path)
    engine = KnowledgeEngine(config)

    assert engine.config is config
    assert engine.state is EngineState.UNINITIALIZED
    assert engine.registry.state is RegistryState.OPEN
    assert engine.version == __version__
    with pytest.raises(AttributeError):
        engine.state = EngineState.READY  # type: ignore[misc]
    with pytest.raises(EngineLifecycleError):
        _ = engine.storage
    with pytest.raises(EngineLifecycleError):
        _ = engine.phase85
    with pytest.raises(TypeError):
        KnowledgeEngine(object())  # type: ignore[arg-type]


def test_phase85_runtime_is_composed_by_knowledge_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    providers = make_providers()
    install_builtins(monkeypatch, runtime_plugin(providers))
    engine = KnowledgeEngine(make_config(tmp_path))

    asyncio.run(engine.initialize())

    assert engine.phase85.readiness().runtime_ready
    assert engine.phase85.capability_status("canonical_ingestion").state.active
    assert engine.phase85.capability_status("v1_retrieval").state.active
    discovery = engine.phase85.capability_status("capability_discovery")
    assert discovery.state.exposed
    assert not discovery.state.behaviorally_verified
    assert not discovery.state.certified
    assert engine.phase85.profile_status("vision").state.configured
    assert not engine.phase85.profile_status("vision").state.initialized

    asyncio.run(engine.shutdown())
    with pytest.raises(EngineLifecycleError):
        _ = engine.phase85


def test_builtin_parser_plugin_registers_all_frozen_phase3_formats(tmp_path: Path) -> None:
    """Built-in Phase 3 parsers are resolvable through the owned registry."""
    registry = PluginRegistry(core_version=__version__)
    config = make_config(tmp_path).model_copy(
        update={
            "embedding": EmbeddingConfig(
                provider="ollama",
                model="test-embedding",
                dimensions=3,
            )
        }
    )
    results = registry.load_plugins(_builtin_plugins(config))

    assert all(result.loaded for result in results)
    for slot in (
        ".pdf",
        "application/pdf",
        ".docx",
        ".md",
        ".html",
        ".txt",
        ".json",
        ".csv",
        ".xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        # Code file extensions — regression: previously unregistered, causing
        # server.js and similar files to fail with UnsupportedError in production.
        ".js",
        ".ts",
        ".py",
        ".java",
        ".go",
        ".rs",
        ".c",
        ".cpp",
        # MIME types detected by mimetypes/libmagic for code files
        "text/javascript",
        "text/x-python",
    ):
        assert registry.resolve_parser(slot) is not None, (
            f"No parser registered for slot {slot!r} "
            "— did you forget to add it to CoreParserPlugin in engine.py?"
        )
    from mnemo.models import DocType

    assert registry.resolve_chunker_v2(DocType.GENERIC) is not None
    assert registry.resolve_chunker_v2(DocType.BOOK) is not None
    assert registry.resolve_chunker_v2(DocType.PAPER) is not None
    assert registry.resolve_chunker_v2(DocType.MARKDOWN) is not None
    assert registry.resolve_chunker_v2(DocType.EMAIL) is not None
    assert registry.resolve_chunker_v2(DocType.RESUME) is not None
    assert registry.resolve_chunker_v2(DocType.SLIDES) is not None
    assert registry.resolve_chunker_v2(DocType.DOCUMENTATION) is not None
    for doc_type in DocType:
        assert registry.resolve_chunker(doc_type) is None

    from mnemo.embeddings.cached import CachedEmbeddingProvider

    assert isinstance(registry.resolve_embedding_provider("primary"), CachedEmbeddingProvider)


def test_builtin_parser_plugin_code_extensions_route_to_plain_text_parser(
    tmp_path: Path,
) -> None:
    """Regression: all code extensions in PlainTextParser._CODE_EXTENSIONS must be
    registered in the builtin plugin system so that source files (e.g. server.js)
    do not raise UnsupportedError in production.

    Previously .js (and other code extensions) were missing from engine.py
    CoreParserPlugin registration, causing golden-corpus ingestion to fail.
    """
    from mnemo.parsers.plain_text import _CODE_EXTENSIONS, PlainTextParser

    registry = PluginRegistry(core_version=__version__)
    registry.load_plugins(_builtin_plugins(make_config(tmp_path)))

    for ext in _CODE_EXTENSIONS:
        parser = registry.resolve_parser(ext)
        assert parser is not None, (
            f"Extension {ext!r} is in PlainTextParser._CODE_EXTENSIONS but not "
            f"registered in CoreParserPlugin — source files with this extension "
            f"will fail with UnsupportedError"
        )
        assert isinstance(parser, PlainTextParser), (
            f"Extension {ext!r} should resolve to PlainTextParser, got {type(parser).__name__}"
        )


def test_initialize_resolves_freezes_and_exposes_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Initialization publishes the complete runtime and immutable capabilities."""
    providers = make_providers()
    install_builtins(monkeypatch, runtime_plugin(providers))
    engine = KnowledgeEngine(make_config(tmp_path))

    asyncio.run(engine.initialize())

    assert engine.state is EngineState.READY
    assert engine.registry.state is RegistryState.FROZEN
    assert engine.storage is providers.storage
    assert engine.embedding_provider is providers.embedding
    assert engine.reranker is providers.reranker
    for role in ("planner", "synthesizer", "extractor", "classifier"):
        assert engine.llm(role) is providers.llm
    capabilities = engine.capabilities()
    assert isinstance(capabilities, MappingProxyType)
    assert tuple(capabilities) == (
        "storage",
        "embedding",
        "reranker",
        "planner",
        "synthesizer",
        "extractor",
        "classifier",
    )
    with pytest.raises(TypeError):
        capabilities["storage"] = capabilities["storage"]  # type: ignore[index]
    with pytest.raises(ValueError, match="unknown LLM role"):
        engine.llm("unknown")  # type: ignore[arg-type]
    with pytest.raises(DependencyUnavailableError):
        _ = engine.final_qa


def test_ready_engine_optional_capabilities_fail_closed_when_not_composed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ready minimal engine must not imply optional V2/storage capabilities."""
    providers = make_providers()
    install_builtins(monkeypatch, runtime_plugin(providers))
    engine = KnowledgeEngine(make_config(tmp_path))

    asyncio.run(engine.initialize())

    unavailable = (
        lambda: engine.asset_catalog,
        lambda: engine.asset_records,
        lambda: engine.processing_jobs,
        lambda: engine.ocr_store,
        lambda: engine.vision_store,
        lambda: engine.final_qa_v2,
        lambda: engine.final_qa_v2_execution_store,
        lambda: engine.advanced_retrieval,
        lambda: engine.partitioned_retrieval,
        lambda: engine.comparison,
        lambda: engine.structured_retrieval,
    )
    for resolve in unavailable:
        with pytest.raises(DependencyUnavailableError):
            resolve()

    assert engine.language_capability_records == ()


def test_v2_outer_reranker_validates_inputs_and_preserves_order() -> None:
    """The V2-owned outer slot is strictly inert but still validates its contract."""
    reranker = _V2OwnedOuterPassThroughReranker()
    assert not reranker.capabilities().supports_cross_encoder

    async def scenario() -> None:
        assert await reranker.rerank("query", (), 2) == ()
        with pytest.raises(ValueError, match="non-empty"):
            await reranker.rerank(" ", (), 1)
        with pytest.raises(TypeError, match="tuple"):
            await reranker.rerank("query", [], 1)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="integer"):
            await reranker.rerank("query", (), True)
        with pytest.raises(ValueError, match="positive"):
            await reranker.rerank("query", (), 0)

    asyncio.run(scenario())


class _Counter:
    tokenizer_id = O200K_BASE_TOKENIZER_ID

    def count(self, text: str) -> int:
        return len(text)


def test_engine_composition_boundaries_reject_invalid_dependencies(tmp_path: Path) -> None:
    """Composition rejects malformed optional resources and provider capability reports."""
    with pytest.raises(TypeError, match="clock"):
        FinalQAComponents(_Counter(), object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="operational_store_v2"):
        FinalQAComponents(_Counter(), Mock(), object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="final_qa_components"):
        KnowledgeEngine(make_config(tmp_path), final_qa_components=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="FinalQAInterfaceV2"):
        KnowledgeEngine(make_config(tmp_path), final_qa_v2=object())  # type: ignore[arg-type]

    providers = make_providers()
    invalid_storage = create_autospec(StorageInterfaceV1, instance=True)
    invalid_storage.capabilities.return_value = object()
    with pytest.raises(EngineInitializationError, match="invalid capabilities"):
        _storage_capabilities(invalid_storage)

    invalid_embedding = create_autospec(EmbeddingProviderV1, instance=True)
    invalid_embedding.dimensions = 3
    invalid_embedding.capabilities.return_value = object()
    with pytest.raises(EngineInitializationError, match="invalid capabilities"):
        _embedding_capabilities(invalid_embedding, expected_dimensions=3)
    cast(Mock, providers.embedding).dimensions = 4
    with pytest.raises(EngineInitializationError, match="dimensions"):
        _embedding_capabilities(providers.embedding, expected_dimensions=3)

    invalid_reranker = create_autospec(RerankerInterfaceV1, instance=True)
    invalid_reranker.capabilities.return_value = object()
    with pytest.raises(EngineInitializationError, match="invalid capabilities"):
        _reranker_capabilities(invalid_reranker)

    invalid_llm = create_autospec(LLMInterfaceV1, instance=True)
    invalid_llm.provider = ""
    invalid_llm.model = "model"
    with pytest.raises(EngineInitializationError, match="provider"):
        _require_llm(invalid_llm, "planner")
    invalid_llm.provider = "test"
    invalid_llm.model = ""
    with pytest.raises(EngineInitializationError, match="model"):
        _require_llm(invalid_llm, "planner")
    invalid_llm.model = "model"
    invalid_llm.capabilities.return_value = object()
    with pytest.raises(EngineInitializationError, match="invalid capabilities"):
        _llm_capabilities(invalid_llm, "planner")

    missing = tmp_path / "missing-plugins"
    with pytest.raises(EngineInitializationError, match="unavailable"):
        _plugin_candidates(missing)


def _phase6_plugin(providers: Providers) -> RuntimePlugin:
    retriever = create_autospec(RetrieverInterfaceV1, instance=True)
    promoter = create_autospec(ParentPromotionInterfaceV1, instance=True)

    def register(registry: PluginRegistry) -> None:
        runtime_plugin(providers).register(registry)
        registry.register_retriever("dense", retriever, priority=10)
        registry.register_retriever("sparse", retriever, priority=10)
        registry.register_parent_promoter("default", promoter, priority=10)

    return RuntimePlugin(name="phase6-runtime", callback=register)


def test_final_qa_components_compose_and_shutdown_drop_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = make_providers()
    install_builtins(monkeypatch, _phase6_plugin(providers))
    clock = Mock()
    engine = KnowledgeEngine(
        make_config(tmp_path),
        final_qa_components=FinalQAComponents(_Counter(), clock),
    )

    asyncio.run(engine.initialize())
    graph = engine.final_qa
    assert graph is engine.final_qa
    clock.assert_not_called()
    asyncio.run(engine.shutdown())
    with pytest.raises(EngineLifecycleError):
        _ = engine.final_qa


def test_invalid_final_qa_counter_fails_initialization_without_clock_use(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = make_providers()
    install_builtins(monkeypatch, _phase6_plugin(providers))
    counter = _Counter()
    counter.tokenizer_id = "wrong"
    clock = Mock()
    engine = KnowledgeEngine(
        make_config(tmp_path),
        final_qa_components=FinalQAComponents(counter, clock),
    )
    with pytest.raises(EngineInitializationError, match="token counter"):
        asyncio.run(engine.initialize())
    assert engine.state is EngineState.FAILED
    clock.assert_not_called()


def test_initialize_and_shutdown_are_idempotent_and_restartable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ready initialization and stopped shutdown are no-ops; stopped can restart."""
    providers = make_providers()
    install_builtins(monkeypatch, runtime_plugin(providers))
    engine = KnowledgeEngine(make_config(tmp_path))

    async def scenario() -> None:
        await engine.shutdown()
        await engine.initialize()
        first_registry = engine.registry
        await engine.initialize()
        assert engine.registry is first_registry
        await engine.shutdown()
        assert engine.state is EngineState.STOPPED
        await engine.shutdown()
        await engine.initialize()
        assert engine.registry is not first_registry

    asyncio.run(scenario())
    assert engine.state is EngineState.READY


def test_startup_alias_warns_and_delegates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The deprecated startup alias preserves initialize semantics."""
    install_builtins(monkeypatch, runtime_plugin(make_providers()))
    engine = KnowledgeEngine(make_config(tmp_path))

    with pytest.warns(DeprecationWarning, match="initialize"):
        asyncio.run(engine.startup())
    assert engine.state is EngineState.READY


def test_missing_required_provider_rolls_back_to_fresh_registry_and_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partial composition is never published after startup failure."""
    install_builtins(monkeypatch)
    engine = KnowledgeEngine(make_config(tmp_path))
    attempted_registry = engine.registry

    with pytest.raises(EngineInitializationError, match="storage"):
        asyncio.run(engine.initialize())

    assert engine.state is EngineState.FAILED
    assert engine.registry is not attempted_registry
    assert engine.registry.state is RegistryState.OPEN
    with pytest.raises(EngineLifecycleError):
        asyncio.run(engine.initialize())
    asyncio.run(engine.shutdown())
    assert engine.state is EngineState.FAILED


def test_embedding_dimension_mismatch_fails_structural_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both provider and capability dimensions must match configuration."""
    install_builtins(monkeypatch, runtime_plugin(make_providers(dimensions=4)))
    engine = KnowledgeEngine(make_config(tmp_path, dimensions=3))

    with pytest.raises(EngineInitializationError, match="dimensions"):
        asyncio.run(engine.initialize())
    assert engine.state is EngineState.FAILED


@pytest.mark.parametrize("state", [EngineState.INITIALIZING, EngineState.STOPPING])
def test_transitional_states_reject_lifecycle_operations(
    tmp_path: Path,
    state: EngineState,
) -> None:
    """Explicit transitional states reject conflicting lifecycle operations."""
    engine = KnowledgeEngine(make_config(tmp_path))
    engine._state = state

    with pytest.raises(EngineLifecycleError):
        asyncio.run(engine.initialize())
    with pytest.raises(EngineLifecycleError):
        asyncio.run(engine.shutdown())


@pytest.mark.parametrize("family", ["storage", "embedding", "reranker"])
def test_invalid_typed_capabilities_fail_structural_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    family: str,
) -> None:
    """Required providers must return their approved immutable capability type."""
    providers = make_providers()
    cast(Mock, getattr(providers, family)).capabilities.return_value = object()
    install_builtins(monkeypatch, runtime_plugin(providers))
    engine = KnowledgeEngine(make_config(tmp_path))

    with pytest.raises(EngineInitializationError, match="invalid capabilities"):
        asyncio.run(engine.initialize())


def test_invalid_llm_identity_and_capabilities_fail_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLMs require non-empty identities and typed advertised capabilities."""
    providers = make_providers()
    llm_mock = cast(Mock, providers.llm)
    llm_mock.provider = " "
    install_builtins(monkeypatch, runtime_plugin(providers))
    engine = KnowledgeEngine(make_config(tmp_path))

    with pytest.raises(EngineInitializationError, match="declare a provider"):
        asyncio.run(engine.initialize())

    providers = make_providers()
    cast(Mock, providers.llm).capabilities.return_value = object()
    install_builtins(monkeypatch, runtime_plugin(providers))
    engine = KnowledgeEngine(make_config(tmp_path))
    with pytest.raises(EngineInitializationError, match="invalid capabilities"):
        asyncio.run(engine.initialize())

    providers = make_providers()
    cast(Mock, providers.llm).model = ""
    install_builtins(monkeypatch, runtime_plugin(providers))
    engine = KnowledgeEngine(make_config(tmp_path))
    with pytest.raises(EngineInitializationError, match="declare a model"):
        asyncio.run(engine.initialize())


def test_required_plugin_conflict_fails_but_optional_failure_is_isolated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Advertised required failures are fatal while optional failures are logged."""
    providers = make_providers()
    healthy = runtime_plugin(providers, name="healthy")

    def conflict(registry: PluginRegistry) -> None:
        registry.register_storage("primary", providers.storage, priority=10)

    required_conflict = RuntimePlugin(name="conflict", callback=conflict)
    install_builtins(monkeypatch, healthy, required_conflict)
    engine = KnowledgeEngine(make_config(tmp_path))
    with pytest.raises(EngineInitializationError, match="required capabilities"):
        asyncio.run(engine.initialize())

    optional_failure = RuntimePlugin(
        name="optional",
        callback=lambda _: (_ for _ in ()).throw(RuntimeError("broken optional plugin")),
        capabilities_value=("parser",),
    )
    install_builtins(monkeypatch, healthy, optional_failure)
    engine = KnowledgeEngine(make_config(tmp_path))
    asyncio.run(engine.initialize())
    assert engine.state is EngineState.READY


def test_plugin_directory_enumerates_only_immediate_python_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local discovery ignores hidden, nested, and non-Python children."""
    providers = make_providers()
    install_builtins(monkeypatch, runtime_plugin(providers))
    directory = make_config(tmp_path).plugins.directory
    visible_package = directory / "visible"
    visible_package.mkdir()
    (visible_package / "__init__.py").touch()
    (directory / "plugin.py").touch()
    (directory / ".hidden.py").touch()
    (directory / "notes.txt").touch()
    nested = directory / "container" / "nested"
    nested.mkdir(parents=True)
    (nested / "__init__.py").touch()
    observed: list[tuple[Path, ...]] = []

    def discover(registry: PluginRegistry, paths: tuple[Path, ...]) -> tuple[()]:
        observed.append(paths)
        return ()

    monkeypatch.setattr(PluginRegistry, "discover_and_load_paths", discover)
    engine = KnowledgeEngine(make_config(tmp_path))
    asyncio.run(engine.initialize())

    assert observed == [(directory / "plugin.py", visible_package)]


def test_shutdown_does_not_contact_providers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 1 lifecycle never opens, closes, or health-checks providers."""
    providers = make_providers()
    install_builtins(monkeypatch, runtime_plugin(providers))
    engine = KnowledgeEngine(make_config(tmp_path))

    asyncio.run(engine.initialize())
    asyncio.run(engine.shutdown())

    storage = cast(Mock, providers.storage)
    embedding = cast(Mock, providers.embedding)
    assert storage.open.call_count == 0
    assert storage.close.call_count == 0
    assert storage.health_check.call_count == 0
    assert embedding.health_check.call_count == 0
    with pytest.raises(EngineLifecycleError):
        engine.capabilities()


def test_unavailable_plugin_directory_and_raw_discovery_error_are_wrapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discovery failures rollback without exposing an internal exception type."""
    providers = make_providers()
    install_builtins(monkeypatch, runtime_plugin(providers))
    config = make_config(tmp_path)
    config.plugins.directory.rmdir()
    engine = KnowledgeEngine(config)
    with pytest.raises(EngineInitializationError, match="plugin directory is unavailable"):
        asyncio.run(engine.initialize())

    config = make_config(tmp_path)
    engine = KnowledgeEngine(config)

    def fail_discovery(registry: PluginRegistry) -> tuple[()]:
        raise RuntimeError("private discovery detail")

    monkeypatch.setattr(PluginRegistry, "discover_and_load_entry_points", fail_discovery)
    with pytest.raises(EngineInitializationError, match="initialization failed") as captured:
        asyncio.run(engine.initialize())
    assert isinstance(captured.value.__cause__, RuntimeError)


def test_advanced_retrieval_composition_covers_optional_projection_paths(
    tmp_path: Path,
) -> None:
    """Composition includes only active derived projections and validates V2 ownership."""

    class AdvancedStore:
        async def advanced_canonical_snapshot(self, **_kwargs):  # type: ignore[no-untyped-def]
            return "snapshot"

        async def enumerate_advanced_canonical(self, **_kwargs):  # type: ignore[no-untyped-def]
            return ()

        async def get_advanced_canonical_records(self, **_kwargs):  # type: ignore[no-untyped-def]
            return ()

        async def expand_advanced_canonical(self, **_kwargs):  # type: ignore[no-untyped-def]
            return ()

        async def active_multimodal_generation_identity(
            self,
            representation,
            *,
            profile_id=None,  # type: ignore[no-untyped-def]
        ):
            if representation is EvidenceRepresentation.VISUAL_VECTOR:
                return "visual-generation" if profile_id == "visual-profile" else None
            return f"{representation.value}-generation"

        async def retrieve_multimodal_evidence(self, **_kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("composition must not retrieve")

        async def active_multilingual_generation_identity(self) -> str:
            return "multilingual-generation"

        async def retrieve_multilingual_evidence(self, **_kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("composition must not retrieve")

    class VisualProvider:
        profile_id = "visual-profile"

        async def ready(self) -> bool:
            return True

    class AdvancedSource:
        def __init__(self, representation: EvidenceRepresentation) -> None:
            self.representation = representation

        async def retrieve(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("composition must not retrieve")

        async def expand(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            return ()

    providers = make_providers()
    resolved = _ResolvedProviders(
        storage=AdvancedStore(),  # type: ignore[arg-type]
        embedding=providers.embedding,
        reranker=providers.reranker,
        planner=providers.llm,
        synthesizer=providers.llm,
        extractor=providers.llm,
        classifier=providers.llm,
        capabilities=MappingProxyType({}),
    )
    engine = KnowledgeEngine(make_config(tmp_path))
    assert asyncio.run(engine._compose_advanced_retrieval(resolved)) is None

    engine = KnowledgeEngine(
        make_config(tmp_path),
        advanced_retrieval_cursor_codec=RetrievalCursorCodec(b"x" * 32),
        visual_query_embedding_provider=VisualProvider(),  # type: ignore[arg-type]
    )
    with pytest.raises(EngineInitializationError, match="sparse retriever"):
        asyncio.run(engine._compose_advanced_retrieval(resolved))
    sparse = create_autospec(RetrieverInterfaceV1, instance=True)
    sparse.retrieval_mode = "sparse"
    engine.registry.resolve_retriever = (  # type: ignore[method-assign]
        lambda name: sparse if name == "sparse" else None
    )
    composed = asyncio.run(engine._compose_advanced_retrieval(resolved))
    assert composed is not None
    assert len(composed._sources) == 6  # type: ignore[attr-defined]

    engine._full_multilingual_v2_readiness = SimpleNamespace(v2_exposed=True)
    engine._full_multilingual_v2_source = object()
    with pytest.raises(EngineInitializationError, match="shared retrieval"):
        asyncio.run(engine._compose_advanced_retrieval(resolved))
    engine._full_multilingual_v2_source = AdvancedSource(EvidenceRepresentation.CANONICAL_TEXT)
    with pytest.raises(EngineInitializationError, match="wrong representation"):
        asyncio.run(engine._compose_advanced_retrieval(resolved))
    engine._full_multilingual_v2_source = AdvancedSource(EvidenceRepresentation.MULTILINGUAL_TEXT)
    exposed = asyncio.run(engine._compose_advanced_retrieval(resolved))
    assert exposed is not None
    assert exposed._reranker is None  # type: ignore[attr-defined]


def test_engine_properties_fail_closed_when_dependencies_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    providers = make_providers()
    providers.storage.list_sources_for_document = Mock(return_value=[])  # type: ignore[attr-defined]
    install_builtins(monkeypatch, runtime_plugin(providers))
    engine = KnowledgeEngine(make_config(tmp_path))
    asyncio.run(engine.initialize())

    with pytest.raises(DependencyUnavailableError, match="asset catalog"):
        _ = engine.asset_catalog
    with pytest.raises(DependencyUnavailableError, match="asset metadata lookup"):
        _ = engine.asset_records
    with pytest.raises(DependencyUnavailableError, match="durable processing jobs"):
        _ = engine.processing_jobs
    with pytest.raises(DependencyUnavailableError, match="OCR derivations"):
        _ = engine.ocr_store
    with pytest.raises(DependencyUnavailableError, match="vision derivations"):
        _ = engine.vision_store

    with pytest.raises(DependencyUnavailableError, match="final QA components were not supplied"):
        _ = engine.final_qa
    with pytest.raises(DependencyUnavailableError, match="Final-QA V2 is not composed"):
        _ = engine.final_qa_v2
    with pytest.raises(
        DependencyUnavailableError,
        match="Final-QA V2 operational persistence is unavailable",
    ):
        _ = engine.final_qa_v2_execution_store
    with pytest.raises(DependencyUnavailableError, match="advanced retrieval is not configured"):
        _ = engine.advanced_retrieval
    with pytest.raises(DependencyUnavailableError, match="partitioned retrieval is not configured"):
        _ = engine.partitioned_retrieval
    with pytest.raises(
        DependencyUnavailableError, match="comparison primitives are not configured"
    ):
        _ = engine.comparison
    with pytest.raises(DependencyUnavailableError, match="structured retrieval is not configured"):
        _ = engine.structured_retrieval

    with pytest.raises(ValueError, match="unknown LLM role"):
        engine.llm("invalid_role")  # type: ignore[arg-type]

    assert engine.document_scope_resolver is not None
    assert isinstance(engine.language_capability_records, tuple)
    assert engine.version == __version__
    assert engine.capabilities() is not None

    engine._phase85 = None
    with pytest.raises(DependencyUnavailableError, match=r"Phase 8\.5 runtime is unavailable"):
        _ = engine.phase85


def test_engine_install_full_multilingual_v2_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class MockMultilingualSource(AdvancedRetrievalSourceV1):
        def __init__(self, rep: EvidenceRepresentation) -> None:
            self._rep = rep

        @property
        def representation(self) -> EvidenceRepresentation:
            return self._rep

        async def retrieve(self, *_args: object, **_kwargs: object) -> tuple[object, ...]:
            return ()

        async def expand(self, *_args: object, **_kwargs: object) -> tuple[object, ...]:
            return ()

    providers = make_providers()
    install_builtins(monkeypatch, runtime_plugin(providers))
    engine = KnowledgeEngine(make_config(tmp_path))
    asyncio.run(engine.initialize())

    with pytest.raises(EngineInitializationError, match="requires EXPOSED readiness"):
        asyncio.run(
            engine.install_exposed_full_multilingual_v2(
                source=MockMultilingualSource(EvidenceRepresentation.MULTILINGUAL_TEXT),
                readiness=SimpleNamespace(v2_exposed=False),  # type: ignore[arg-type]
            )
        )

    with pytest.raises(EngineInitializationError, match="does not implement shared retrieval"):
        asyncio.run(
            engine.install_exposed_full_multilingual_v2(
                source=object(),  # type: ignore[arg-type]
                readiness=SimpleNamespace(v2_exposed=True),  # type: ignore[arg-type]
            )
        )

    with pytest.raises(EngineInitializationError, match="wrong representation"):
        asyncio.run(
            engine.install_exposed_full_multilingual_v2(
                source=MockMultilingualSource(EvidenceRepresentation.CANONICAL_TEXT),
                readiness=SimpleNamespace(v2_exposed=True),  # type: ignore[arg-type]
            )
        )

    valid_source = MockMultilingualSource(EvidenceRepresentation.MULTILINGUAL_TEXT)
    valid_readiness = SimpleNamespace(v2_exposed=True)
    asyncio.run(
        engine.install_exposed_full_multilingual_v2(
            source=valid_source,
            readiness=valid_readiness,  # type: ignore[arg-type]
        )
    )
    assert engine._full_multilingual_v2_source is valid_source
    assert engine._full_multilingual_v2_readiness is valid_readiness


def test_engine_lifecycle_state_machine_and_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    providers = make_providers()
    install_builtins(monkeypatch, runtime_plugin(providers))
    engine = KnowledgeEngine(make_config(tmp_path))

    unready_phase85 = Mock()

    async def _mock_initialize() -> None:
        pass

    async def _mock_shutdown() -> None:
        pass

    unready_phase85.initialize = _mock_initialize
    unready_phase85.shutdown = _mock_shutdown
    unready_phase85.readiness.return_value = SimpleNamespace(runtime_ready=False)

    monkeypatch.setattr(engine, "_compose_phase85_runtime", lambda *args, **kwargs: unready_phase85)

    with pytest.raises(
        EngineInitializationError, match=r"Phase 8\.5 runtime capabilities are unavailable"
    ):
        asyncio.run(engine.initialize())

    assert engine.state is EngineState.FAILED

    with pytest.raises(EngineLifecycleError, match="failed KnowledgeEngine cannot be initialized"):
        asyncio.run(engine.initialize())

    asyncio.run(engine.shutdown())
    assert engine.state is EngineState.FAILED

    fresh_engine = KnowledgeEngine(make_config(tmp_path))
    with pytest.deprecated_call():
        asyncio.run(fresh_engine.startup())
    assert fresh_engine.state is EngineState.READY

    fresh_engine._state = EngineState.STOPPING
    with pytest.raises(EngineLifecycleError, match="cannot shut down"):
        asyncio.run(fresh_engine.shutdown())


def test_engine_provider_and_plugin_helpers(tmp_path: Path) -> None:
    with pytest.raises(EngineInitializationError, match="plugin directory is unavailable"):
        _plugin_candidates(tmp_path / "non_existent_dir")

    with pytest.raises(EngineInitializationError, match="does not implement StorageInterfaceV1"):
        _storage_capabilities(object())  # type: ignore[arg-type]
    bad_storage = Mock(spec=StorageInterfaceV1)
    bad_storage.capabilities.return_value = object()
    with pytest.raises(EngineInitializationError, match="invalid capabilities"):
        _storage_capabilities(bad_storage)

    with pytest.raises(EngineInitializationError, match="does not implement EmbeddingProviderV1"):
        _embedding_capabilities(object(), expected_dimensions=3)  # type: ignore[arg-type]
    bad_embedder = Mock(spec=EmbeddingProviderV1)
    bad_embedder.capabilities.return_value = object()
    with pytest.raises(EngineInitializationError, match="invalid capabilities"):
        _embedding_capabilities(bad_embedder, expected_dimensions=3)
    dim_mismatch = Mock(spec=EmbeddingProviderV1)
    dim_mismatch.dimensions = 4
    dim_mismatch.capabilities.return_value = EmbeddingCapabilities(
        dimensions=4,
        supports_batch=True,
        max_batch=8,
        multilingual=False,
        supports_normalization=True,
    )
    with pytest.raises(EngineInitializationError, match="embedding dimensions do not match"):
        _embedding_capabilities(dim_mismatch, expected_dimensions=3)

    with pytest.raises(EngineInitializationError, match="does not implement RerankerInterfaceV1"):
        _reranker_capabilities(object())  # type: ignore[arg-type]
    bad_reranker = Mock(spec=RerankerInterfaceV1)
    bad_reranker.capabilities.return_value = object()
    with pytest.raises(EngineInitializationError, match="invalid capabilities"):
        _reranker_capabilities(bad_reranker)

    with pytest.raises(EngineInitializationError, match="does not implement LLMInterfaceV1"):
        _require_llm(None, "planner")
    bad_llm = Mock(spec=LLMInterfaceV1)
    bad_llm.provider = ""
    with pytest.raises(EngineInitializationError, match="does not declare a provider"):
        _require_llm(bad_llm, "planner")
    bad_llm.provider = "test"
    bad_llm.model = ""
    with pytest.raises(EngineInitializationError, match="does not declare a model"):
        _require_llm(bad_llm, "planner")

    config_v2 = MnemoConfig(
        storage=StorageConfig(),
        llm=LLMConfig(
            planner=LLMRoleConfig(provider="test", model="m", max_context_tokens=128),
            synthesizer=LLMRoleConfig(provider="test", model="m", max_context_tokens=128),
            extractor=LLMRoleConfig(provider="test", model="m", max_context_tokens=128),
            classifier=LLMRoleConfig(provider="test", model="m", max_context_tokens=128),
        ),
        embedding=EmbeddingConfig(provider="test", model="m", dimensions=3),
        reranker=RerankerConfig(provider="v2-owned-pass-through", model="none"),
        plugins=PluginConfig(directory=tmp_path),
    )
    plugins_v2 = _builtin_plugins(config_v2)
    assert any("v2-owned" in p.name.lower() or "_V2Owned" in type(p).__name__ for p in plugins_v2)


def test_engine_compose_phase85_runtime_full_registrations(tmp_path: Path) -> None:
    from mnemo.interfaces import (
        AdvancedRetrievalInterfaceV1,
        AssetCatalogStoreV1,
        MultimodalAdvancedStoreV1,
    )
    from mnemo.retrieval.structured_datasets import StructuredDatasetRuntimeService

    class AdvancedMockStorage(StorageInterfaceV1, AssetCatalogStoreV1, MultimodalAdvancedStoreV1):
        pass

    storage = create_autospec(AdvancedMockStorage, instance=True)
    storage.capabilities.return_value = StorageCapabilities(
        supports_blobs=True,
        supports_dense_search=True,
        supports_sparse_search=True,
        supports_metadata=True,
        supports_graph=True,
        supports_transactions=True,
        supports_health_checks=True,
    )
    providers = make_providers()
    resolved = _ResolvedProviders(
        storage=storage,
        embedding=providers.embedding,
        reranker=providers.reranker,
        planner=providers.llm,
        synthesizer=providers.llm,
        extractor=providers.llm,
        classifier=providers.llm,
        capabilities=MappingProxyType({}),
    )
    engine = KnowledgeEngine(make_config(tmp_path))
    engine._final_qa_v2 = Mock()
    advanced_retrieval = create_autospec(AdvancedRetrievalInterfaceV1, instance=True)
    structured_retrieval = create_autospec(StructuredDatasetRuntimeService, instance=True)

    runtime = engine._compose_phase85_runtime(
        providers=resolved,
        advanced_retrieval=advanced_retrieval,
        structured_retrieval=structured_retrieval,
        structured_ready=True,
        structured_generation_id="gen-123",
    )
    assert runtime is not None
    caps = set(runtime._service_registrations)
    assert "capability_discovery" in caps
    assert "asset_discovery" in caps
    assert "exhaustive_retrieval" in caps
    assert "multimodal_retrieval" in caps
    assert "structured_retrieval" in caps
    assert "final_qa_v2" in caps


def test_engine_compose_final_qa_and_provider_resolution_failures(tmp_path: Path) -> None:
    providers = make_providers()
    engine = KnowledgeEngine(make_config(tmp_path))

    # _resolve_providers failures
    engine.registry.resolve_storage = lambda name: None  # type: ignore[method-assign]
    with pytest.raises(EngineInitializationError, match="required storage provider"):
        engine._resolve_providers()

    engine.registry.resolve_storage = lambda name: providers.storage  # type: ignore[method-assign]
    engine.registry.resolve_embedding_provider = lambda name: None  # type: ignore[method-assign]
    with pytest.raises(EngineInitializationError, match="required embedding provider"):
        engine._resolve_providers()

    engine.registry.resolve_embedding_provider = lambda name: providers.embedding  # type: ignore[method-assign]
    engine.registry.resolve_reranker = lambda name: None  # type: ignore[method-assign]
    with pytest.raises(EngineInitializationError, match="required reranker"):
        engine._resolve_providers()

    engine.registry.resolve_reranker = lambda name: providers.reranker  # type: ignore[method-assign]
    engine.registry.resolve_llm = lambda role: None  # type: ignore[method-assign]
    with pytest.raises(EngineInitializationError, match="required LLM providers are unavailable"):
        engine._resolve_providers()

    engine.registry.resolve_llm = lambda role: providers.llm  # type: ignore[method-assign]
    resolved = engine._resolve_providers()
    assert resolved is not None

    # _compose_final_qa failures
    token_counter = Mock()
    token_counter.tokenizer_id = O200K_BASE_TOKENIZER_ID
    token_counter.count = Mock(return_value=0)
    engine._final_qa_components = FinalQAComponents(
        token_counter=token_counter,
        clock=Mock(),
        operational_store_v2=None,
    )

    engine.registry.resolve_retriever = lambda name: None  # type: ignore[method-assign]
    with pytest.raises(
        EngineInitializationError, match="required retriever 'dense' is unavailable"
    ):
        engine._compose_final_qa(resolved)

    dense_mock = create_autospec(RetrieverInterfaceV1, instance=True)
    sparse_mock = create_autospec(RetrieverInterfaceV1, instance=True)
    engine.registry.resolve_retriever = (  # type: ignore[method-assign]
        lambda name: dense_mock if name == "dense" else sparse_mock
    )

    engine.registry.resolve_parent_promoter = lambda name: None  # type: ignore[method-assign]
    with pytest.raises(
        EngineInitializationError, match="required parent promoter 'default' is unavailable"
    ):
        engine._compose_final_qa(resolved)

    parent_promoter = create_autospec(ParentPromotionInterfaceV1, instance=True)
    engine.registry.resolve_parent_promoter = lambda name: parent_promoter  # type: ignore[method-assign]

    engine.registry.freeze()
    composed_qa = engine._compose_final_qa(resolved)
    assert composed_qa is not None

    # _compose_final_qa_v2 with storage implementing FinalQAExecutionStoreV2
    from mnemo.interfaces import FinalQAExecutionStoreV2

    class StorageWithV2(StorageInterfaceV1, FinalQAExecutionStoreV2):
        pass

    storage_v2 = create_autospec(StorageWithV2, instance=True)
    storage_v2.list_sources_for_document = Mock(return_value=[])  # type: ignore[attr-defined]
    resolved_v2 = _ResolvedProviders(
        storage=storage_v2,
        embedding=providers.embedding,
        reranker=providers.reranker,
        planner=providers.llm,
        synthesizer=providers.llm,
        extractor=providers.llm,
        classifier=providers.llm,
        capabilities=MappingProxyType({}),
    )
    qa_v2 = engine._compose_final_qa_v2(resolved_v2)
    assert qa_v2 is not None
