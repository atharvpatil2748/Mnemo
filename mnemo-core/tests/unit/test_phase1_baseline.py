"""Regression tests for the audited Phase 1 package and dependency baseline."""

from __future__ import annotations

import ast
import json
import tomllib
from pathlib import Path

import mnemo
import mnemo_server

_ROOT = Path(__file__).resolve().parents[3]
_CORE = _ROOT / "mnemo-core" / "mnemo"


def test_release_versions_are_synchronized() -> None:
    """Every distributable project reports the audited release version."""
    root_project = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    core_project = tomllib.loads(
        (_ROOT / "mnemo-core" / "pyproject.toml").read_text(encoding="utf-8")
    )
    server_project = tomllib.loads(
        (_ROOT / "mnemo-server" / "pyproject.toml").read_text(encoding="utf-8")
    )
    ui_project = json.loads((_ROOT / "mnemo-ui" / "package.json").read_text(encoding="utf-8"))

    versions = {
        root_project["project"]["version"],
        core_project["project"]["version"],
        server_project["project"]["version"],
        ui_project["version"],
        mnemo.__version__,
        mnemo_server.__version__,
    }
    assert versions == {"0.11.0"}


def test_top_level_core_exports_are_intentional() -> None:
    """The composition package exposes only its frozen Phase 1 convenience API."""
    assert set(mnemo.__all__) == {
        "PLUGIN_ENTRY_POINT_GROUP",
        "PLUGIN_INTERFACE_VERSION",
        "CapabilityKind",
        "EmbeddingConfig",
        "EngineInitializationError",
        "EngineLifecycleError",
        "EngineState",
        "FilesystemStorageConfig",
        "KnowledgeEngine",
        "KnowledgeEngineError",
        "LLMConfig",
        "LLMRoleConfig",
        "MnemoConfig",
        "PluginCompatibilityError",
        "PluginConfig",
        "PluginDescriptor",
        "PluginDiscoveryError",
        "PluginInterface",
        "PluginInterfaceV1",
        "PluginLoadResult",
        "PluginRegistry",
        "PluginSource",
        "PluginValidationError",
        "QdrantStorageConfig",
        "RegistrationConflictError",
        "RegistrationDescriptor",
        "RegistryError",
        "RegistryFrozenError",
        "RegistryState",
        "RerankerConfig",
        "SQLiteStorageConfig",
        "StorageConfig",
        "SurrealDBStorageConfig",
        "__version__",
    }


def test_core_has_no_infrastructure_or_reverse_layer_imports() -> None:
    """Static imports preserve the Phase 1 dependency direction and pure core."""
    forbidden_roots = {
        "fastapi",
        "httpx",
        "mnemo_server",
        "requests",
        "starlette",
    }
    for source in _CORE.rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        imported_roots = {
            name.split(".", maxsplit=1)[0]
            for node in ast.walk(tree)
            for name in _imported_modules(node)
        }
        assert forbidden_roots.isdisjoint(imported_roots), source

    assert _internal_imports(_CORE / "registry.py") <= {"mnemo.interfaces", "mnemo.models"}
    assert _internal_imports(_CORE / "config.py") == set()
    assert _internal_imports(_CORE / "engine.py") <= {
        "mnemo._version",
        "mnemo.config",
        "mnemo.interfaces",
        "mnemo.parsers",
        "mnemo.registry",
        "mnemo.storage",
    }


def _imported_modules(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    if isinstance(node, ast.ImportFrom) and node.module is not None:
        return (node.module,)
    return ()


def _internal_imports(source: Path) -> set[str]:
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    return {
        ".".join(module.split(".")[:2])
        for node in ast.walk(tree)
        for module in _imported_modules(node)
        if module == "mnemo" or module.startswith("mnemo.")
    }
