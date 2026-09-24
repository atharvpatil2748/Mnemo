"""ADR-0077 server-owned mutable-workspace boundary."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class StorageRole(StrEnum):
    """Governed, mutually exclusive storage roles."""

    CERTIFIED_CORPUS = "CERTIFIED_CORPUS"
    EVALUATION_ARTIFACT = "EVALUATION_ARTIFACT"
    GOVERNED_OPERATIONAL = "GOVERNED_OPERATIONAL"
    MUTABLE_WORKSPACE = "MUTABLE_WORKSPACE"
    USER_CACHE = "USER_CACHE"


class WorkspaceMode(StrEnum):
    """Effective production workspace behavior."""

    MUTABLE = "mutable"
    READ_ONLY = "read_only"


@dataclass(frozen=True, slots=True)
class ProtectedStorageLocation:
    """One server-owned protected path and its non-workspace role."""

    label: str
    path: Path
    role: StorageRole

    def __post_init__(self) -> None:
        if self.role is StorageRole.MUTABLE_WORKSPACE:
            raise ValueError("protected storage cannot have the mutable-workspace role")


@dataclass(frozen=True, slots=True)
class ProtectedStorageInventory:
    """Complete protected-path input to one boundary decision."""

    locations: tuple[ProtectedStorageLocation, ...]


@dataclass(frozen=True, slots=True)
class MutableWorkspaceLayout:
    """Server-owned paths derived only after accepting one workspace root."""

    root: Path
    database: Path
    blobs: Path
    parsed: Path
    caches: Path
    generated: Path

    @classmethod
    def from_root(cls, root: Path) -> MutableWorkspaceLayout:
        return cls(
            root=root,
            database=root / "workspace.db",
            blobs=root / "blobs",
            parsed=root / "parsed",
            caches=root / "caches",
            generated=root / "generated",
        )


@dataclass(frozen=True, slots=True)
class MutableWorkspaceDecision:
    """Side-effect-free result of validating the ADR-0077 boundary."""

    mode: WorkspaceMode
    reason: str
    layout: MutableWorkspaceLayout | None = None

    @property
    def mutable(self) -> bool:
        return self.mode is WorkspaceMode.MUTABLE and self.layout is not None


class MutableWorkspaceBoundaryValidator:
    """Validate a workspace root before any storage initialization occurs."""

    def __init__(self, inventory: ProtectedStorageInventory) -> None:
        self._inventory = inventory

    def evaluate(self, configured_root: Path | None) -> MutableWorkspaceDecision:
        """Return mutable only for an unambiguous absolute disjoint root."""
        if configured_root is None:
            return _read_only("MUTABLE_WORKSPACE_CONFIGURATION_MISSING")
        if not configured_root.is_absolute():
            return _read_only("MUTABLE_WORKSPACE_ROOT_MUST_BE_ABSOLUTE")
        if ".." in configured_root.parts:
            return _read_only("MUTABLE_WORKSPACE_TRAVERSAL_REJECTED")
        if configured_root.exists() and not configured_root.is_dir():
            return _read_only("MUTABLE_WORKSPACE_ROOT_IS_NOT_A_DIRECTORY")
        if _contains_existing_alias(configured_root):
            return _read_only("MUTABLE_WORKSPACE_ALIAS_REJECTED")

        try:
            root = configured_root.resolve(strict=False)
            root_key = _path_key(root)
        except (OSError, RuntimeError, ValueError):
            return _read_only("MUTABLE_WORKSPACE_ROOT_UNRESOLVED")

        existing_parent = _nearest_existing_parent(root)
        if existing_parent is None or not existing_parent.is_dir():
            return _read_only("MUTABLE_WORKSPACE_PARENT_UNAVAILABLE")
        if not os.access(existing_parent, os.W_OK):
            return _read_only("MUTABLE_WORKSPACE_PARENT_NOT_WRITABLE")

        for location in self._inventory.locations:
            if location.role is StorageRole.MUTABLE_WORKSPACE:
                return _read_only("MUTABLE_WORKSPACE_ROLE_COLLISION")
            try:
                protected = location.path.resolve(strict=False)
                protected_key = _path_key(protected)
            except (OSError, RuntimeError, ValueError):
                return _read_only(f"PROTECTED_PATH_UNRESOLVED:{location.label}")
            if _paths_overlap(root_key, protected_key):
                return _read_only(f"MUTABLE_WORKSPACE_OVERLAPS:{location.label}")

        return MutableWorkspaceDecision(
            mode=WorkspaceMode.MUTABLE,
            reason="MUTABLE_WORKSPACE_ACCEPTED",
            layout=MutableWorkspaceLayout.from_root(root),
        )

    def materialize(self, decision: MutableWorkspaceDecision) -> MutableWorkspaceDecision:
        """Create an already-approved layout, otherwise preserve read-only mode."""
        if not decision.mutable or decision.layout is None:
            return decision
        layout = decision.layout
        created: list[Path] = []
        try:
            missing_parents = _missing_path_chain(layout.root)
            created.extend(missing_parents)
            layout.root.mkdir(parents=True, exist_ok=True)
            for path in (layout.blobs, layout.parsed, layout.caches, layout.generated):
                existed = path.exists()
                path.mkdir(exist_ok=True)
                if not existed:
                    created.append(path)
        except OSError:
            _remove_empty_created_paths(created)
            return _read_only("MUTABLE_WORKSPACE_INITIALIZATION_FAILED")
        revalidated = self.evaluate(layout.root)
        if not revalidated.mutable:
            _remove_empty_created_paths(created)
            return _read_only("MUTABLE_WORKSPACE_POST_CREATE_VALIDATION_FAILED")
        return revalidated


def _read_only(reason: str) -> MutableWorkspaceDecision:
    return MutableWorkspaceDecision(mode=WorkspaceMode.READ_ONLY, reason=reason)


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(os.fspath(path)))


def _paths_overlap(left: str, right: str) -> bool:
    try:
        common = os.path.commonpath((left, right))
    except ValueError:
        return False
    return common in (left, right)


def _nearest_existing_parent(path: Path) -> Path | None:
    candidate = path
    while not candidate.exists():
        parent = candidate.parent
        if parent == candidate:
            return None
        candidate = parent
    return candidate


def _missing_path_chain(path: Path) -> list[Path]:
    """Return nonexistent ancestors in creation order, including the leaf."""
    missing: list[Path] = []
    candidate = path
    while not candidate.exists():
        missing.append(candidate)
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    missing.reverse()
    return missing


def _remove_empty_created_paths(paths: list[Path]) -> None:
    """Best-effort rollback limited to empty directories created by this call."""
    for path in reversed(paths):
        try:
            path.rmdir()
        except OSError:
            continue


def _contains_existing_alias(path: Path) -> bool:
    """Reject symlink/junction components, including aliases above the leaf."""
    candidate = path
    components: list[Path] = []
    while True:
        components.append(candidate)
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    is_junction = getattr(os.path, "isjunction", lambda _path: False)
    return any(item.is_symlink() or is_junction(item) for item in components)
