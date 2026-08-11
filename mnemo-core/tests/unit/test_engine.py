"""Unit tests for the Phase 1 Module 1.5 KnowledgeEngine composition root."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
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
from mnemo.engine import _builtin_plugins
from mnemo.interfaces import (
    EmbeddingCapabilities,
    EmbeddingProviderV1,
    LLMCapabilities,
    LLMInterfaceV1,
    RerankerCapabilities,
    RerankerInterfaceV1,
    StorageCapabilities,
    StorageInterfaceV1,
)
from mnemo.registry import PluginInterfaceV1, RegistryState


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
    with pytest.raises(TypeError):
        KnowledgeEngine(object())  # type: ignore[arg-type]


def test_builtin_parser_plugin_registers_all_frozen_phase3_formats(tmp_path: Path) -> None:
    """Built-in Phase 3 parsers are resolvable through the owned registry."""
    registry = PluginRegistry(core_version=__version__)
    results = registry.load_plugins(_builtin_plugins(make_config(tmp_path)))

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
    ):
        assert registry.resolve_parser(slot) is not None
    from mnemo.models import DocType

    assert registry.resolve_chunker_v2(DocType.GENERIC) is not None
    assert registry.resolve_chunker_v2(DocType.BOOK) is not None
    assert registry.resolve_chunker_v2(DocType.PAPER) is not None
    assert registry.resolve_chunker_v2(DocType.MARKDOWN) is not None


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
