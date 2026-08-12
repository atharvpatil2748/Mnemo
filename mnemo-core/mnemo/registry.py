"""Transport-independent plugin discovery and registration infrastructure."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import inspect
import os
import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from packaging.requirements import Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from mnemo.interfaces import (
    CHUNKER_INTERFACE_V2_VERSION,
    CHUNKER_INTERFACE_VERSION,
    EMBEDDING_PROVIDER_INTERFACE_VERSION,
    LLM_INTERFACE_VERSION,
    PARSER_INTERFACE_VERSION,
    RERANKER_INTERFACE_VERSION,
    RETRIEVER_INTERFACE_VERSION,
    STORAGE_INTERFACE_VERSION,
    ChunkerInterfaceV1,
    ChunkerInterfaceV2,
    ConflictError,
    EmbeddingProviderV1,
    LifecycleError,
    LLMInterfaceV1,
    ParserInterfaceV1,
    PluginError,
    RerankerInterfaceV1,
    RetrieverInterfaceV1,
    StorageInterfaceV1,
)
from mnemo.models import DocType, FrozenMetadata
from mnemo.models._shared import require_non_empty, require_tuple, require_unique

PLUGIN_ENTRY_POINT_GROUP = "mnemo.plugins"
PLUGIN_INTERFACE_VERSION = "v1"
_PLUGIN_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
_SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


class CapabilityKind(StrEnum):
    """Registry capability families defined by the core architecture."""

    PARSER = "parser"
    CHUNKER = "chunker"
    EMBEDDING_PROVIDER = "embedding_provider"
    RETRIEVER = "retriever"
    RERANKER = "reranker"
    LLM = "llm"
    STORAGE = "storage"


class PluginSource(StrEnum):
    """Supported plugin discovery sources."""

    BUILTIN = "builtin"
    ENTRY_POINT = "entry_point"
    PATH = "path"


class RegistryState(StrEnum):
    """Plugin registry lifecycle states."""

    OPEN = "open"
    FROZEN = "frozen"


@dataclass(frozen=True, slots=True, kw_only=True)
class PluginDescriptor:
    """Immutable identity, compatibility, and discovery metadata for a plugin."""

    name: str
    version: str
    core_version_range: str
    source: PluginSource = PluginSource.BUILTIN
    entry_point: str | None = None
    capabilities: tuple[str, ...] = ()
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate stable plugin descriptor fields."""
        _validate_plugin_name(self.name)
        _validate_semver(self.version, "version")
        _validate_specifier(self.core_version_range)
        if not isinstance(self.source, PluginSource):
            raise TypeError("source must be PluginSource")
        if self.entry_point is not None:
            require_non_empty(self.entry_point, "entry_point")
        require_tuple(self.capabilities, "capabilities")
        for capability in self.capabilities:
            require_non_empty(capability, "capability")
        require_unique(self.capabilities, "capabilities")
        if not isinstance(self.metadata, FrozenMetadata):
            raise TypeError("metadata must be FrozenMetadata")
        prefix = f"plugin.{self.name}."
        if any(not key.startswith(prefix) for key in self.metadata):
            raise ValueError("plugin metadata keys must use the plugin's namespace")


@dataclass(frozen=True, slots=True, kw_only=True)
class RegistrationDescriptor:
    """Immutable public metadata for one registered slot candidate."""

    capability: CapabilityKind
    slot: str
    interface_version: str
    provider_name: str
    plugin_name: str
    priority: int
    active: bool
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate immutable registration metadata."""
        if not isinstance(self.capability, CapabilityKind):
            raise TypeError("capability must be CapabilityKind")
        require_non_empty(self.slot, "slot")
        require_non_empty(self.interface_version, "interface_version")
        require_non_empty(self.provider_name, "provider_name")
        _validate_plugin_name(self.plugin_name)
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise TypeError("priority must be an integer")
        if not isinstance(self.active, bool):
            raise TypeError("active must be a boolean")
        if not isinstance(self.metadata, FrozenMetadata):
            raise TypeError("metadata must be FrozenMetadata")


@dataclass(frozen=True, slots=True, kw_only=True)
class PluginLoadResult:
    """Immutable outcome of one isolated plugin load attempt."""

    descriptor: PluginDescriptor
    loaded: bool
    error_code: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        """Validate success and failure result consistency."""
        if not isinstance(self.descriptor, PluginDescriptor):
            raise TypeError("descriptor must be PluginDescriptor")
        if not isinstance(self.loaded, bool):
            raise TypeError("loaded must be a boolean")
        if self.loaded and (self.error_code is not None or self.error_message is not None):
            raise ValueError("successful load results cannot contain an error")
        if not self.loaded and (self.error_code is None or self.error_message is None):
            raise ValueError("failed load results require an error code and message")


class RegistryError(PluginError):
    """Base class for plugin registry failures."""

    code = "registry.error"


class RegistryFrozenError(RegistryError, LifecycleError):
    """The registry rejected mutation after freeze."""

    code = "registry.frozen"


class RegistrationConflictError(RegistryError, ConflictError):
    """Two distinct providers requested one slot at equal priority."""

    code = "registry.registration_conflict"


class PluginCompatibilityError(RegistryError):
    """A plugin does not support the running core version."""

    code = "registry.incompatible_plugin"


class PluginValidationError(RegistryError):
    """A discovered plugin does not satisfy the plugin contract."""

    code = "registry.invalid_plugin"


class PluginDiscoveryError(RegistryError):
    """A configured plugin source cannot be discovered or loaded."""

    code = "registry.discovery"


@runtime_checkable
class PluginInterfaceV1(Protocol):  # pragma: no cover
    """Version-one structural contract for a discoverable Mnemo plugin."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def core_version_range(self) -> str: ...

    def capabilities(self) -> tuple[str, ...]: ...

    def register(self, registry: PluginRegistry) -> None: ...


PluginInterface = PluginInterfaceV1


@dataclass(frozen=True, slots=True)
class _Registration:
    descriptor: RegistrationDescriptor
    implementation: object


@dataclass(frozen=True, slots=True)
class _FunctionPlugin:
    name: str
    version: str
    core_version_range: str
    callback: Callable[[PluginRegistry], None]

    def capabilities(self) -> tuple[str, ...]:
        return ()

    def register(self, registry: PluginRegistry) -> None:
        self.callback(registry)


class PluginRegistry:
    """Register and resolve versioned plugin capabilities deterministically."""

    def __init__(self, *, core_version: str) -> None:
        """Create an open registry for one semantic core version."""
        _validate_semver(core_version, "core_version")
        self._core_version = core_version
        self._state = RegistryState.OPEN
        self._slots: dict[tuple[CapabilityKind, str, str], list[_Registration]] = {}
        self._plugins: dict[str, PluginDescriptor] = {}
        self._loading_plugin: PluginDescriptor | None = None
        self._startup_hooks: list[Callable[[], Awaitable[None]]] = []

    @property
    def core_version(self) -> str:
        """Return the semantic core version used for compatibility checks."""
        return self._core_version

    @property
    def state(self) -> RegistryState:
        """Return the current registry lifecycle state."""
        return self._state

    def freeze(self) -> None:
        """Prevent all future registration and loading mutations."""
        self._state = RegistryState.FROZEN

    def register_startup_hook(self, hook: Callable[[], Awaitable[None]]) -> None:
        """Register an asynchronous callback to run before capability validation."""
        self._require_open()
        if not callable(hook):
            raise PluginValidationError("startup hook must be callable")
        self._startup_hooks.append(hook)

    async def execute_startup_hooks(self) -> None:
        """Execute all registered startup hooks sequentially."""
        for hook in self._startup_hooks:
            await hook()

    def load_plugin(
        self,
        plugin: PluginInterfaceV1,
        *,
        source: PluginSource = PluginSource.BUILTIN,
        entry_point: str | None = None,
    ) -> PluginDescriptor:
        """Validate and atomically register one plugin."""
        self._require_open()
        if not isinstance(plugin, PluginInterfaceV1):
            raise PluginValidationError("plugin does not satisfy PluginInterfaceV1")
        descriptor = PluginDescriptor(
            name=plugin.name,
            version=plugin.version,
            core_version_range=plugin.core_version_range,
            source=source,
            entry_point=entry_point,
            capabilities=plugin.capabilities(),
        )
        self._require_compatible(descriptor)
        existing = self._plugins.get(descriptor.name)
        if existing is not None:
            if existing == descriptor:
                return existing
            raise RegistrationConflictError("plugin name is already registered")

        snapshot = {key: list(values) for key, values in self._slots.items()}
        self._loading_plugin = descriptor
        try:
            plugin.register(self)
        except Exception as error:
            self._slots = snapshot
            raise PluginValidationError(
                f"plugin {descriptor.name} registration failed",
                details=FrozenMetadata({"plugin.error.type": type(error).__name__}),
            ) from error
        finally:
            self._loading_plugin = None
        self._plugins[descriptor.name] = descriptor
        return descriptor

    def load_plugins(
        self,
        plugins: Iterable[PluginInterfaceV1],
    ) -> tuple[PluginLoadResult, ...]:
        """Load plugins independently so one failure cannot disable others."""
        results: list[PluginLoadResult] = []
        for plugin in plugins:
            fallback = _safe_descriptor(plugin)
            try:
                descriptor = self.load_plugin(plugin)
                results.append(PluginLoadResult(descriptor=descriptor, loaded=True))
            except PluginError as error:
                results.append(
                    PluginLoadResult(
                        descriptor=fallback,
                        loaded=False,
                        error_code=error.code,
                        error_message=error.message,
                    )
                )
        return tuple(results)

    def discover_and_load_entry_points(
        self,
        *,
        group: str = PLUGIN_ENTRY_POINT_GROUP,
    ) -> tuple[PluginLoadResult, ...]:
        """Discover installed plugin objects through Python entry points."""
        self._require_open()
        results: list[PluginLoadResult] = []
        points = sorted(
            importlib.metadata.entry_points(group=group),
            key=lambda item: (item.name, item.value),
        )
        for point in points:
            fallback = PluginDescriptor(
                name=_normalize_plugin_name(point.name),
                version=_entry_point_version(point),
                core_version_range=_entry_point_core_range(point),
                source=PluginSource.ENTRY_POINT,
                entry_point=point.value,
            )
            try:
                loaded: object = point.load()
                plugin = _coerce_entry_point_plugin(loaded, fallback)
                descriptor = self.load_plugin(
                    plugin,
                    source=PluginSource.ENTRY_POINT,
                    entry_point=point.value,
                )
                results.append(PluginLoadResult(descriptor=descriptor, loaded=True))
            except Exception as error:
                code = error.code if isinstance(error, PluginError) else PluginDiscoveryError.code
                results.append(
                    PluginLoadResult(
                        descriptor=fallback,
                        loaded=False,
                        error_code=code,
                        error_message=str(error),
                    )
                )
        return tuple(results)

    def discover_and_load_paths(
        self,
        paths: tuple[Path, ...] | None = None,
    ) -> tuple[PluginLoadResult, ...]:
        """Load plugin objects from configured local module paths."""
        self._require_open()
        candidates = paths if paths is not None else _environment_plugin_paths()
        results: list[PluginLoadResult] = []
        for path in sorted(candidates, key=lambda item: str(item)):
            fallback = PluginDescriptor(
                name=_normalize_plugin_name(path.stem),
                version="0.0.0",
                core_version_range=">=0.0.0",
                source=PluginSource.PATH,
                entry_point=str(path),
            )
            try:
                plugin = _load_path_plugin(path)
                descriptor = self.load_plugin(
                    plugin,
                    source=PluginSource.PATH,
                    entry_point=str(path.resolve()),
                )
                results.append(PluginLoadResult(descriptor=descriptor, loaded=True))
            except Exception as error:
                code = error.code if isinstance(error, PluginError) else PluginDiscoveryError.code
                results.append(
                    PluginLoadResult(
                        descriptor=fallback,
                        loaded=False,
                        error_code=code,
                        error_message=str(error),
                    )
                )
        return tuple(results)

    def register_parser(
        self,
        slot: str,
        implementation: ParserInterfaceV1,
        *,
        priority: int,
        plugin_name: str | None = None,
    ) -> None:
        """Register a parser candidate."""
        self._register(
            CapabilityKind.PARSER,
            slot,
            implementation,
            priority,
            plugin_name,
            PARSER_INTERFACE_VERSION,
            ParserInterfaceV1,
        )

    def register_chunker(
        self,
        doc_type: DocType,
        implementation: ChunkerInterfaceV1,
        *,
        priority: int,
        plugin_name: str | None = None,
    ) -> None:
        """Register a chunker candidate."""
        if not isinstance(doc_type, DocType):
            raise PluginValidationError("doc_type must be DocType")
        self._register(
            CapabilityKind.CHUNKER,
            doc_type.value,
            implementation,
            priority,
            plugin_name,
            CHUNKER_INTERFACE_VERSION,
            ChunkerInterfaceV1,
        )

    def register_chunker_v2(
        self,
        doc_type: DocType,
        implementation: ChunkerInterfaceV2,
        *,
        priority: int,
        plugin_name: str | None = None,
    ) -> None:
        """Register a version-two chunker candidate independently from V1."""
        if not isinstance(doc_type, DocType):
            raise PluginValidationError("doc_type must be DocType")
        self._register(
            CapabilityKind.CHUNKER,
            doc_type.value,
            implementation,
            priority,
            plugin_name,
            CHUNKER_INTERFACE_V2_VERSION,
            ChunkerInterfaceV2,
        )

    def register_embedding_provider(
        self,
        slot: str,
        implementation: EmbeddingProviderV1,
        *,
        priority: int,
        plugin_name: str | None = None,
    ) -> None:
        """Register an embedding-provider candidate."""
        self._register(
            CapabilityKind.EMBEDDING_PROVIDER,
            slot,
            implementation,
            priority,
            plugin_name,
            EMBEDDING_PROVIDER_INTERFACE_VERSION,
            EmbeddingProviderV1,
        )

    def register_retriever(
        self,
        slot: str,
        implementation: RetrieverInterfaceV1,
        *,
        priority: int,
        plugin_name: str | None = None,
    ) -> None:
        """Register a retriever candidate."""
        self._register(
            CapabilityKind.RETRIEVER,
            slot,
            implementation,
            priority,
            plugin_name,
            RETRIEVER_INTERFACE_VERSION,
            RetrieverInterfaceV1,
        )

    def register_reranker(
        self,
        slot: str,
        implementation: RerankerInterfaceV1,
        *,
        priority: int,
        plugin_name: str | None = None,
    ) -> None:
        """Register a reranker candidate."""
        self._register(
            CapabilityKind.RERANKER,
            slot,
            implementation,
            priority,
            plugin_name,
            RERANKER_INTERFACE_VERSION,
            RerankerInterfaceV1,
        )

    def register_llm(
        self,
        slot: str,
        implementation: LLMInterfaceV1,
        *,
        priority: int,
        plugin_name: str | None = None,
    ) -> None:
        """Register a language-model candidate."""
        self._register(
            CapabilityKind.LLM,
            slot,
            implementation,
            priority,
            plugin_name,
            LLM_INTERFACE_VERSION,
            LLMInterfaceV1,
        )

    def register_storage(
        self,
        slot: str,
        implementation: StorageInterfaceV1,
        *,
        priority: int,
        plugin_name: str | None = None,
    ) -> None:
        """Register a storage-facade candidate."""
        self._register(
            CapabilityKind.STORAGE,
            slot,
            implementation,
            priority,
            plugin_name,
            STORAGE_INTERFACE_VERSION,
            StorageInterfaceV1,
        )

    def resolve(self, capability: CapabilityKind, slot: str) -> object | None:
        """Resolve the active implementation for a capability slot."""
        require_non_empty(slot, "slot")
        registrations = self._slots.get((capability, slot, _interface_version(capability)))
        return None if not registrations else registrations[0].implementation

    def resolve_parser(self, slot: str) -> ParserInterfaceV1 | None:
        """Resolve the active parser for a format slot."""
        return cast(ParserInterfaceV1 | None, self.resolve(CapabilityKind.PARSER, slot))

    def resolve_chunker(self, doc_type: DocType) -> ChunkerInterfaceV1 | None:
        """Resolve the active chunker for a document type."""
        return cast(ChunkerInterfaceV1 | None, self.resolve(CapabilityKind.CHUNKER, doc_type.value))

    def resolve_chunker_v2(self, doc_type: DocType) -> ChunkerInterfaceV2 | None:
        """Resolve the active V2 chunker without consulting V1 registrations."""
        if not isinstance(doc_type, DocType):
            raise TypeError("doc_type must be DocType")
        registrations = self._slots.get(
            (CapabilityKind.CHUNKER, doc_type.value, CHUNKER_INTERFACE_V2_VERSION)
        )
        return cast(
            ChunkerInterfaceV2 | None,
            None if not registrations else registrations[0].implementation,
        )

    def resolve_embedding_provider(self, slot: str) -> EmbeddingProviderV1 | None:
        """Resolve the active embedding provider for a slot."""
        return cast(
            EmbeddingProviderV1 | None, self.resolve(CapabilityKind.EMBEDDING_PROVIDER, slot)
        )

    def resolve_retriever(self, slot: str) -> RetrieverInterfaceV1 | None:
        """Resolve the active retriever for a mode slot."""
        return cast(RetrieverInterfaceV1 | None, self.resolve(CapabilityKind.RETRIEVER, slot))

    def resolve_reranker(self, slot: str) -> RerankerInterfaceV1 | None:
        """Resolve the active reranker for a slot."""
        return cast(RerankerInterfaceV1 | None, self.resolve(CapabilityKind.RERANKER, slot))

    def resolve_llm(self, slot: str) -> LLMInterfaceV1 | None:
        """Resolve the active language model for a role slot."""
        return cast(LLMInterfaceV1 | None, self.resolve(CapabilityKind.LLM, slot))

    def resolve_storage(self, slot: str) -> StorageInterfaceV1 | None:
        """Resolve the active storage facade for a capability slot."""
        return cast(StorageInterfaceV1 | None, self.resolve(CapabilityKind.STORAGE, slot))

    def list_registrations(
        self, capability: CapabilityKind | None = None
    ) -> tuple[RegistrationDescriptor, ...]:
        """Return immutable, deterministic registry metadata."""
        result: list[RegistrationDescriptor] = []
        for (kind, _, _), registrations in self._slots.items():
            if capability is None or capability is kind:
                result.extend(item.descriptor for item in registrations)
        return tuple(
            sorted(
                result,
                key=lambda item: (
                    item.capability,
                    item.slot,
                    item.interface_version,
                    -item.priority,
                    item.provider_name,
                    item.plugin_name,
                ),
            )
        )

    def list_plugins(self) -> tuple[PluginDescriptor, ...]:
        """Return loaded plugin descriptors in deterministic name order."""
        return tuple(self._plugins[name] for name in sorted(self._plugins))

    def _register(
        self,
        capability: CapabilityKind,
        slot: str,
        implementation: object,
        priority: int,
        plugin_name: str | None,
        interface_version: str,
        contract: type[object],
    ) -> None:
        self._require_open()
        require_non_empty(slot, "slot")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise PluginValidationError("priority must be an integer")
        if not isinstance(implementation, contract):
            raise PluginValidationError(f"implementation does not satisfy {contract.__name__}")
        descriptor = self._require_loading_plugin(plugin_name)
        key = (capability, slot, interface_version)
        registrations = self._slots.setdefault(key, [])
        for existing in registrations:
            if (
                existing.implementation is implementation
                and existing.descriptor.plugin_name == descriptor.name
            ):
                return
            if existing.descriptor.priority == priority:
                raise RegistrationConflictError(
                    f"equal-priority conflict for {capability.value}:{slot}"
                )
        public = RegistrationDescriptor(
            capability=capability,
            slot=slot,
            interface_version=interface_version,
            provider_name=type(implementation).__qualname__,
            plugin_name=descriptor.name,
            priority=priority,
            active=False,
        )
        registrations.append(_Registration(public, implementation))
        registrations.sort(key=lambda item: item.descriptor.priority, reverse=True)
        self._slots[key] = [
            _Registration(replace(item.descriptor, active=index == 0), item.implementation)
            for index, item in enumerate(registrations)
        ]

    def _require_loading_plugin(self, plugin_name: str | None) -> PluginDescriptor:
        descriptor = self._loading_plugin
        if descriptor is None:
            raise PluginValidationError("registration must occur during plugin loading")
        if plugin_name is not None and plugin_name != descriptor.name:
            raise PluginValidationError("registration plugin_name does not match loading plugin")
        return descriptor

    def _require_open(self) -> None:
        if self._state is not RegistryState.OPEN:
            raise RegistryFrozenError("registry is frozen")

    def _require_compatible(self, descriptor: PluginDescriptor) -> None:
        if Version(self._core_version) not in SpecifierSet(descriptor.core_version_range):
            raise PluginCompatibilityError(
                f"plugin {descriptor.name} does not support mnemo-core {self._core_version}"
            )


def _validate_plugin_name(value: str) -> None:
    if _PLUGIN_NAME_PATTERN.fullmatch(value) is None:
        raise ValueError("plugin name must be lowercase ASCII with digits, underscores, or hyphens")


def _interface_version(capability: CapabilityKind) -> str:
    """Return the released version used by the generic compatibility lookup."""
    return {
        CapabilityKind.PARSER: PARSER_INTERFACE_VERSION,
        CapabilityKind.CHUNKER: CHUNKER_INTERFACE_VERSION,
        CapabilityKind.EMBEDDING_PROVIDER: EMBEDDING_PROVIDER_INTERFACE_VERSION,
        CapabilityKind.RETRIEVER: RETRIEVER_INTERFACE_VERSION,
        CapabilityKind.RERANKER: RERANKER_INTERFACE_VERSION,
        CapabilityKind.LLM: LLM_INTERFACE_VERSION,
        CapabilityKind.STORAGE: STORAGE_INTERFACE_VERSION,
    }[capability]


def _normalize_plugin_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-")
    return normalized or "unknown-plugin"


def _validate_semver(value: str, field_name: str) -> None:
    if _SEMVER_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a semantic version")
    try:
        Version(value)
    except InvalidVersion as error:  # pragma: no cover - regex is stricter
        raise ValueError(f"{field_name} must be a semantic version") from error


def _validate_specifier(value: str) -> None:
    require_non_empty(value, "core_version_range")
    try:
        SpecifierSet(value)
    except InvalidSpecifier as error:
        raise ValueError("core_version_range must be a valid version range") from error


def _safe_descriptor(plugin: object) -> PluginDescriptor:
    try:
        if isinstance(plugin, PluginInterfaceV1):
            return PluginDescriptor(
                name=plugin.name,
                version=plugin.version,
                core_version_range=plugin.core_version_range,
                capabilities=plugin.capabilities(),
            )
    except (TypeError, ValueError):
        pass
    return PluginDescriptor(name="invalid-plugin", version="0.0.0", core_version_range=">=0.0.0")


def _environment_plugin_paths() -> tuple[Path, ...]:
    value = os.environ.get("MNEMO_PLUGINS", "")
    if not value:
        return ()
    return tuple(Path(item) for item in value.split(os.pathsep) if item)


def _load_path_plugin(path: Path) -> PluginInterfaceV1:
    resolved = path.resolve(strict=True)
    module_file = resolved / "__init__.py" if resolved.is_dir() else resolved
    if module_file.suffix != ".py" or not module_file.is_file():
        raise PluginDiscoveryError(f"plugin path is not a Python module: {path}")
    module_name = f"_mnemo_plugin_{abs(hash(str(resolved)))}"
    spec = importlib.util.spec_from_file_location(module_name, module_file)
    if spec is None or spec.loader is None:
        raise PluginDiscoveryError(f"cannot create module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plugin: object = getattr(module, "plugin", None)
    if isinstance(plugin, PluginInterfaceV1):
        return plugin
    callback: object = getattr(module, "register", None)
    descriptor = PluginDescriptor(
        name=str(getattr(module, "PLUGIN_NAME", _normalize_plugin_name(path.stem))),
        version=str(getattr(module, "PLUGIN_VERSION", "0.0.0")),
        core_version_range=str(getattr(module, "MNEMO_CORE_VERSION", ">=0.0.0")),
        source=PluginSource.PATH,
        entry_point=str(path),
    )
    return _coerce_entry_point_plugin(callback, descriptor)


def _coerce_entry_point_plugin(
    loaded: object,
    descriptor: PluginDescriptor,
) -> PluginInterfaceV1:
    if isinstance(loaded, PluginInterfaceV1):
        return loaded
    if callable(loaded) and len(inspect.signature(loaded).parameters) == 1:
        callback = cast(Callable[[PluginRegistry], None], loaded)
        return _FunctionPlugin(
            descriptor.name,
            descriptor.version,
            descriptor.core_version_range,
            callback,
        )
    raise PluginValidationError(
        "plugin entry point must expose a plugin object or register function"
    )


def _entry_point_version(point: importlib.metadata.EntryPoint) -> str:
    distribution = point.dist
    value = "0.0.0" if distribution is None else distribution.version
    return value if _SEMVER_PATTERN.fullmatch(value) else "0.0.0"


def _entry_point_core_range(point: importlib.metadata.EntryPoint) -> str:
    distribution = point.dist
    if distribution is None or distribution.requires is None:
        return ">=0.0.0"
    for requirement_text in distribution.requires:
        requirement = Requirement(requirement_text)
        if requirement.name.lower().replace("_", "-") == "mnemo-core":
            return str(requirement.specifier) or ">=0.0.0"
    return ">=0.0.0"
