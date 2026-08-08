"""Unit tests for the Phase 1 Module 1.3 plugin registry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import FrozenInstanceError, dataclass
from pathlib import Path
from unittest.mock import create_autospec

import pytest
from mnemo import (
    PLUGIN_INTERFACE_VERSION,
    CapabilityKind,
    PluginCompatibilityError,
    PluginDescriptor,
    PluginInterfaceV1,
    PluginLoadResult,
    PluginRegistry,
    PluginSource,
    PluginValidationError,
    RegistrationConflictError,
    RegistrationDescriptor,
    RegistryFrozenError,
    RegistryState,
)
from mnemo.interfaces import (
    ChunkerInterfaceV1,
    EmbeddingProviderV1,
    FileMetadata,
    LLMInterfaceV1,
    ParserCapabilities,
    RerankerInterfaceV1,
    RetrieverInterfaceV1,
    StorageInterfaceV1,
)
from mnemo.interfaces.parser_models import ParseResult, RawTextBlock
from mnemo.models import DocType, DocumentMetadata, FrozenMetadata


class ParserStub:
    """Minimal structural parser used only by registry tests."""

    @property
    def supported_formats(self) -> tuple[str, ...]:
        return (".pdf",)

    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            supported_formats=self.supported_formats,
            supports_tables=True,
            supports_images=True,
            supports_math=False,
            supports_ocr=False,
        )

    def parse(
        self,
        data: bytes,
        filename: str,
        metadata: FileMetadata,
    ) -> ParseResult:
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


@dataclass(slots=True)
class FakePlugin:
    """Configurable structural plugin used by acceptance tests."""

    name: str
    callback: Callable[[PluginRegistry], None]
    version: str = "1.0.0"
    core_version_range: str = ">=0.1.0,<1.0.0"
    advertised: tuple[str, ...] = ("parser",)

    def capabilities(self) -> tuple[str, ...]:
        return self.advertised

    def register(self, registry: PluginRegistry) -> None:
        self.callback(registry)


def parser_plugin(name: str, parser: ParserStub, priority: int) -> FakePlugin:
    """Create a fake plugin that registers one parser slot."""

    def register(registry: PluginRegistry) -> None:
        registry.register_parser(".pdf", parser, priority=priority, plugin_name=name)

    return FakePlugin(name=name, callback=register)


def test_descriptor_is_immutable_hashable_and_namespaced() -> None:
    """Plugin descriptors expose stable immutable discovery metadata."""
    descriptor = PluginDescriptor(
        name="example-plugin",
        version="1.2.3",
        core_version_range=">=0.1.0,<1.0.0",
        source=PluginSource.ENTRY_POINT,
        entry_point="example:plugin",
        capabilities=("parser",),
        metadata=FrozenMetadata({"plugin.example-plugin.mode": "local"}),
    )

    assert hash(descriptor)
    with pytest.raises(FrozenInstanceError):
        descriptor.version = "2.0.0"  # type: ignore[misc]


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "Invalid Name"},
        {"version": "1.0"},
        {"core_version_range": "not a range"},
        {"source": "builtin"},
        {"entry_point": " "},
        {"capabilities": ["parser"]},
        {"capabilities": ("parser", "parser")},
        {"metadata": FrozenMetadata({"plugin.other.key": True})},
    ],
)
def test_descriptor_validation(overrides: dict[str, object]) -> None:
    """Invalid identity, compatibility, and metadata are rejected."""
    values: dict[str, object] = {
        "name": "example",
        "version": "1.0.0",
        "core_version_range": ">=0.1.0",
    }
    values.update(overrides)
    with pytest.raises((TypeError, ValueError)):
        PluginDescriptor(**values)  # type: ignore[arg-type]


def test_priority_ordering_resolution_and_metadata() -> None:
    """Higher priority wins while lower candidates remain discoverable."""
    registry = PluginRegistry(core_version="0.2.0")
    low = ParserStub()
    high = ParserStub()

    registry.load_plugin(parser_plugin("low", low, 1))
    registry.load_plugin(parser_plugin("high", high, 10))

    assert registry.resolve_parser(".pdf") is high
    registrations = registry.list_registrations(CapabilityKind.PARSER)
    assert [item.priority for item in registrations] == [10, 1]
    assert [item.active for item in registrations] == [True, False]
    assert registry.list_plugins()[0].name == "high"
    assert registry.resolve(CapabilityKind.PARSER, ".missing") is None


def test_equal_priority_conflict_rolls_back_failed_plugin() -> None:
    """Equal priority is explicit conflict and failed registration is atomic."""
    registry = PluginRegistry(core_version="0.2.0")
    first = ParserStub()
    registry.load_plugin(parser_plugin("first", first, 5))

    with pytest.raises(PluginValidationError) as captured:
        registry.load_plugin(parser_plugin("second", ParserStub(), 5))

    assert isinstance(captured.value.__cause__, RegistrationConflictError)
    assert registry.resolve_parser(".pdf") is first
    assert [plugin.name for plugin in registry.list_plugins()] == ["first"]


def test_identical_registration_is_idempotent() -> None:
    """A plugin can repeat the identical provider registration safely."""
    registry = PluginRegistry(core_version="0.2.0")
    parser = ParserStub()

    def register(target: PluginRegistry) -> None:
        target.register_parser(".pdf", parser, priority=1, plugin_name="repeat")
        target.register_parser(".pdf", parser, priority=1, plugin_name="repeat")

    registry.load_plugin(FakePlugin(name="repeat", callback=register))
    assert len(registry.list_registrations()) == 1


def test_compatibility_validation_and_isolated_bulk_loading() -> None:
    """Incompatible and crashing plugins do not prevent healthy plugins."""
    registry = PluginRegistry(core_version="0.2.0")
    incompatible = FakePlugin(
        name="future",
        callback=lambda _: None,
        core_version_range=">=2.0.0",
    )
    broken = FakePlugin(
        name="broken",
        callback=lambda _: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    healthy = FakePlugin(name="healthy", callback=lambda _: None)

    with pytest.raises(PluginCompatibilityError):
        registry.load_plugin(incompatible)
    results = registry.load_plugins((broken, healthy))

    assert [result.loaded for result in results] == [False, True]
    assert results[0].error_code == "registry.invalid_plugin"
    assert registry.list_plugins() == (results[1].descriptor,)


def test_freeze_blocks_every_mutation() -> None:
    """Registry metadata becomes immutable after explicit initialization."""
    registry = PluginRegistry(core_version="0.2.0")
    registry.freeze()

    assert registry.state is RegistryState.FROZEN
    with pytest.raises(RegistryFrozenError):
        registry.load_plugin(FakePlugin(name="late", callback=lambda _: None))
    with pytest.raises(RegistryFrozenError):
        registry.register_parser(".pdf", ParserStub(), priority=1)


def test_all_registration_apis_validate_and_resolve_structural_contracts() -> None:
    """Every architecture slot has a typed registration and resolver path."""
    registry = PluginRegistry(core_version="0.2.0")
    parser = ParserStub()
    chunker = create_autospec(ChunkerInterfaceV1, instance=True)
    embedding = create_autospec(EmbeddingProviderV1, instance=True)
    retriever = create_autospec(RetrieverInterfaceV1, instance=True)
    reranker = create_autospec(RerankerInterfaceV1, instance=True)
    llm = create_autospec(LLMInterfaceV1, instance=True)
    storage = create_autospec(StorageInterfaceV1, instance=True)

    def register(target: PluginRegistry) -> None:
        target.register_parser(".pdf", parser, priority=1)
        target.register_chunker(DocType.PAPER, chunker, priority=1)
        target.register_embedding_provider("primary", embedding, priority=1)
        target.register_retriever("dense", retriever, priority=1)
        target.register_reranker("primary", reranker, priority=1)
        target.register_llm("planner", llm, priority=1)
        target.register_storage("primary", storage, priority=1)

    registry.load_plugin(FakePlugin(name="all-slots", callback=register))

    assert registry.resolve_parser(".pdf") is parser
    assert registry.resolve_chunker(DocType.PAPER) is chunker
    assert registry.resolve_embedding_provider("primary") is embedding
    assert registry.resolve_retriever("dense") is retriever
    assert registry.resolve_reranker("primary") is reranker
    assert registry.resolve_llm("planner") is llm
    assert registry.resolve_storage("primary") is storage


def test_entry_point_discovery_supports_plugin_objects_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Installed entry points load deterministically and isolate bad targets."""
    healthy = FakePlugin(name="entry-plugin", callback=lambda _: None)

    class Point:
        dist = None

        def __init__(self, name: str, value: str, loaded: object) -> None:
            self.name = name
            self.value = value
            self._loaded = loaded

        def load(self) -> object:
            return self._loaded

    points = (Point("good", "package:plugin", healthy), Point("bad", "bad:value", object()))
    monkeypatch.setattr("mnemo.registry.importlib.metadata.entry_points", lambda **_: points)

    results = PluginRegistry(core_version="0.2.0").discover_and_load_entry_points()
    assert [result.loaded for result in results] == [False, True]


def test_path_discovery_uses_environment_and_register_function(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured local modules support the architecture's register entry point."""
    module = tmp_path / "local_plugin.py"
    module.write_text(
        "PLUGIN_NAME = 'local-plugin'\n"
        "PLUGIN_VERSION = '1.0.0'\n"
        "MNEMO_CORE_VERSION = '>=0.1.0,<1.0.0'\n"
        "def register(registry):\n"
        "    return None\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MNEMO_PLUGINS", str(module))

    registry = PluginRegistry(core_version="0.2.0")
    results = registry.discover_and_load_paths()

    assert results[0].loaded
    assert registry.list_plugins()[0].source is PluginSource.PATH


@pytest.mark.parametrize(
    "factory",
    [
        lambda: PluginRegistry(core_version="1.0"),
        lambda: RegistrationDescriptor(
            capability="parser",  # type: ignore[arg-type]
            slot=".pdf",
            interface_version="v1",
            provider_name="Parser",
            plugin_name="plugin",
            priority=1,
            active=True,
        ),
        lambda: PluginLoadResult(
            descriptor=PluginDescriptor(
                name="plugin", version="1.0.0", core_version_range=">=0.0.0"
            ),
            loaded=True,
            error_code="error",
        ),
    ],
)
def test_registry_metadata_validation(factory: object) -> None:
    """Malformed registry metadata and lifecycle inputs are rejected."""
    with pytest.raises((TypeError, ValueError)):
        factory()  # type: ignore[operator]


def test_plugin_protocol_is_structural() -> None:
    """Plugins require no inheritance from Mnemo classes."""
    plugin = FakePlugin(name="structural", callback=lambda _: None)
    assert isinstance(plugin, PluginInterfaceV1)
    assert PLUGIN_INTERFACE_VERSION == "v1"
