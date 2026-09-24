"""Server-owned ADR-0077 production storage composition."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from mnemo.config import MnemoConfig

from ..config import ServerConfig
from .mutable_workspace import (
    MutableWorkspaceBoundaryValidator,
    MutableWorkspaceDecision,
    ProtectedStorageInventory,
    ProtectedStorageLocation,
    StorageRole,
)

PRODUCTION_MANIFEST = Path("config/production/full_multilingual_v2.production.json")

_GOVERNED_ROOTS: tuple[tuple[str, Path, StorageRole], ...] = (
    ("canonical-production", Path("data/canonical_production"), StorageRole.EVALUATION_ARTIFACT),
    (
        "phase-8-5-production",
        Path("scratch/phase8_5_full_multilingual_v2"),
        StorageRole.CERTIFIED_CORPUS,
    ),
    ("phase-8-5-evaluation", Path("scratch/phase8_5_wp16"), StorageRole.EVALUATION_ARTIFACT),
    ("golden-datasets", Path("goldenDataset"), StorageRole.EVALUATION_ARTIFACT),
    ("evaluation-datasets", Path("evaluationDataset"), StorageRole.EVALUATION_ARTIFACT),
)


@dataclass(frozen=True, slots=True)
class ProductionStorageComposition:
    """One side-effect-free production role decision and its core bindings."""

    certified_config: MnemoConfig
    engine_config: MnemoConfig
    decision: MutableWorkspaceDecision
    inventory: ProtectedStorageInventory
    certified_read_only: bool
    embedding_cache_path: Path | None

    def materialize(self) -> ProductionStorageComposition:
        validator = MutableWorkspaceBoundaryValidator(self.inventory)
        decision = validator.materialize(self.decision)
        if not decision.mutable or decision.layout is None:
            return ProductionStorageComposition(
                certified_config=self.certified_config,
                engine_config=self.certified_config,
                decision=decision,
                inventory=self.inventory,
                certified_read_only=True,
                embedding_cache_path=None,
            )
        return _mutable_composition(self.certified_config, self.inventory, decision)


def preflight_production_storage(
    *,
    application_root: Path,
    mnemo_config: MnemoConfig,
    server_config: ServerConfig,
) -> ProductionStorageComposition:
    """Decide all storage roles without creating or opening any storage."""
    root = application_root.resolve(strict=False)
    inventory = build_protected_storage_inventory(
        application_root=root,
        mnemo_config=mnemo_config,
        server_config=server_config,
    )
    decision = MutableWorkspaceBoundaryValidator(inventory).evaluate(
        server_config.mutable_workspace_root
    )
    if not decision.mutable:
        return ProductionStorageComposition(
            certified_config=mnemo_config,
            engine_config=mnemo_config,
            decision=decision,
            inventory=inventory,
            certified_read_only=True,
            embedding_cache_path=None,
        )
    return _mutable_composition(mnemo_config, inventory, decision)


def build_protected_storage_inventory(
    *,
    application_root: Path,
    mnemo_config: MnemoConfig,
    server_config: ServerConfig,
) -> ProtectedStorageInventory:
    """Build the governed inventory from runtime configuration and manifest authority."""
    root = application_root.resolve(strict=False)
    values: list[ProtectedStorageLocation] = [
        ProtectedStorageLocation(
            "configured-certified-database",
            mnemo_config.storage.sqlite.path,
            StorageRole.CERTIFIED_CORPUS,
        ),
        ProtectedStorageLocation(
            "configured-certified-blobs",
            mnemo_config.storage.filesystem.root,
            StorageRole.CERTIFIED_CORPUS,
        ),
        *(
            ProtectedStorageLocation(label, root / relative, role)
            for label, relative, role in _GOVERNED_ROOTS
        ),
    ]
    for label, configured, role in (
        (
            "final-qa-operational",
            server_config.final_qa_operational_store_path,
            StorageRole.GOVERNED_OPERATIONAL,
        ),
        (
            "reranker-activation",
            server_config.reranker_activation_state_path,
            StorageRole.GOVERNED_OPERATIONAL,
        ),
        (
            "model-cache",
            server_config.full_multilingual_v2_model_cache,
            StorageRole.USER_CACHE,
        ),
    ):
        if configured is not None:
            path = configured if configured.is_absolute() else root / configured
            values.append(ProtectedStorageLocation(label, path, role))
    values.extend(_manifest_inventory(root))
    unique: dict[tuple[StorageRole, str], ProtectedStorageLocation] = {}
    for location in values:
        key = (location.role, str(location.path.resolve(strict=False)))
        unique.setdefault(key, location)
    return ProtectedStorageInventory(tuple(unique.values()))


def _mutable_composition(
    certified_config: MnemoConfig,
    inventory: ProtectedStorageInventory,
    decision: MutableWorkspaceDecision,
) -> ProductionStorageComposition:
    layout = decision.layout
    if layout is None:
        raise ValueError("mutable workspace decision has no layout")
    filesystem = certified_config.storage.filesystem.model_copy(update={"root": layout.blobs})
    sqlite = certified_config.storage.sqlite.model_copy(update={"path": layout.database})
    storage = certified_config.storage.model_copy(
        update={"filesystem": filesystem, "sqlite": sqlite}
    )
    engine_config = certified_config.model_copy(update={"storage": storage})
    return ProductionStorageComposition(
        certified_config=certified_config,
        engine_config=engine_config,
        decision=decision,
        inventory=inventory,
        certified_read_only=False,
        embedding_cache_path=layout.caches / "embedding-cache.db",
    )


def _manifest_inventory(root: Path) -> tuple[ProtectedStorageLocation, ...]:
    manifest = root / PRODUCTION_MANIFEST
    if not manifest.is_file():
        return ()
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return (
            ProtectedStorageLocation(
                "production-manifest", manifest, StorageRole.GOVERNED_OPERATIONAL
            ),
        )
    locations = [
        ProtectedStorageLocation("production-manifest", manifest, StorageRole.GOVERNED_OPERATIONAL)
    ]
    locations.extend(_walk_manifest_paths(root, document))
    return tuple(locations)


def _walk_manifest_paths(
    root: Path, value: object, *, prefix: str = "manifest"
) -> list[ProtectedStorageLocation]:
    locations: list[ProtectedStorageLocation] = []
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key)
            child_prefix = f"{prefix}.{key}"
            if isinstance(child, str) and _is_manifest_path_key(key):
                candidate = Path(child)
                path = candidate if candidate.is_absolute() else root / candidate
                locations.append(
                    ProtectedStorageLocation(
                        child_prefix,
                        path,
                        _manifest_role(child_prefix),
                    )
                )
            else:
                locations.extend(_walk_manifest_paths(root, child, prefix=child_prefix))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            locations.extend(_walk_manifest_paths(root, child, prefix=f"{prefix}[{index}]"))
    return locations


def _is_manifest_path_key(key: str) -> bool:
    return key.endswith(("_path", "_state", "_evidence", "_manifest")) or key in {
        "core_runtime",
        "model_profile",
    }


def _manifest_role(label: str) -> StorageRole:
    if "evaluation" in label:
        return StorageRole.EVALUATION_ARTIFACT
    if "corpus" in label or "database_path" in label:
        return StorageRole.CERTIFIED_CORPUS
    return StorageRole.GOVERNED_OPERATIONAL
