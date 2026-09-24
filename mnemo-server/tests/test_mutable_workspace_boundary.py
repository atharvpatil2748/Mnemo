"""CI-safe certification tests for the ADR-0077 path boundary."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from mnemo_server.services.mutable_workspace import (
    MutableWorkspaceBoundaryValidator,
    ProtectedStorageInventory,
    ProtectedStorageLocation,
    StorageRole,
    WorkspaceMode,
)


def _inventory(*locations: tuple[str, Path, StorageRole]) -> ProtectedStorageInventory:
    return ProtectedStorageInventory(
        tuple(ProtectedStorageLocation(label, path, role) for label, path, role in locations)
    )


def test_missing_and_relative_workspace_fail_closed_without_writes(tmp_path: Path) -> None:
    validator = MutableWorkspaceBoundaryValidator(ProtectedStorageInventory(()))

    missing = validator.evaluate(None)
    relative = validator.evaluate(Path("relative/workspace"))

    assert missing.mode is WorkspaceMode.READ_ONLY
    assert relative.mode is WorkspaceMode.READ_ONLY
    assert tuple(tmp_path.iterdir()) == ()


@pytest.mark.parametrize("relation", ["equal", "inside", "contains"])
def test_protected_path_overlap_fails_closed(tmp_path: Path, relation: str) -> None:
    protected = tmp_path / "governed" / "corpus.db"
    protected.parent.mkdir()
    protected.write_bytes(b"immutable")
    workspace = {
        "equal": protected,
        "inside": protected.parent / "workspace",
        "contains": tmp_path,
    }[relation]
    protected_location = protected.parent if relation == "inside" else protected
    validator = MutableWorkspaceBoundaryValidator(
        _inventory(("certified-corpus", protected_location, StorageRole.CERTIFIED_CORPUS))
    )

    decision = validator.evaluate(workspace)

    assert decision.mode is WorkspaceMode.READ_ONLY
    assert protected.read_bytes() == b"immutable"
    assert not (protected.parent / "workspace").exists()


def test_dot_dot_traversal_is_rejected_before_resolution(tmp_path: Path) -> None:
    candidate = tmp_path / "safe" / ".." / "workspace"
    decision = MutableWorkspaceBoundaryValidator(ProtectedStorageInventory(())).evaluate(candidate)

    assert decision.reason == "MUTABLE_WORKSPACE_TRAVERSAL_REJECTED"
    assert not (tmp_path / "workspace").exists()


def test_symlink_alias_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks are unavailable: {error}")

    decision = MutableWorkspaceBoundaryValidator(ProtectedStorageInventory(())).evaluate(alias)

    assert decision.reason == "MUTABLE_WORKSPACE_ALIAS_REJECTED"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction semantics")
def test_windows_junction_alias_is_rejected(tmp_path: Path) -> None:
    import subprocess

    target = tmp_path / "target"
    target.mkdir()
    junction = tmp_path / "junction"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"junction creation is unavailable: {result.stderr}")
    decision = MutableWorkspaceBoundaryValidator(ProtectedStorageInventory(())).evaluate(junction)
    assert decision.reason == "MUTABLE_WORKSPACE_ALIAS_REJECTED"


@pytest.mark.skipif(os.name != "nt", reason="Windows case-folding semantics")
def test_windows_case_alias_overlaps_protected_storage(tmp_path: Path) -> None:
    protected = tmp_path / "Governed"
    protected.mkdir()
    workspace = Path(str(protected).swapcase()) / "workspace"
    validator = MutableWorkspaceBoundaryValidator(
        _inventory(("governed", protected, StorageRole.GOVERNED_OPERATIONAL))
    )
    assert validator.evaluate(workspace).mode is WorkspaceMode.READ_ONLY


def test_valid_absolute_workspace_materializes_only_owned_topology(tmp_path: Path) -> None:
    governed = tmp_path / "governed"
    workspace = tmp_path / "mutable"
    governed.mkdir()
    validator = MutableWorkspaceBoundaryValidator(
        _inventory(("governed", governed, StorageRole.GOVERNED_OPERATIONAL))
    )

    decision = validator.evaluate(workspace)
    assert decision.mutable
    assert not workspace.exists()

    materialized = validator.materialize(decision)
    assert materialized.mutable
    assert materialized.layout is not None
    assert {path.name for path in workspace.iterdir()} == {
        "blobs",
        "parsed",
        "caches",
        "generated",
    }
    assert not materialized.layout.database.exists()


def test_failed_materialization_rolls_back_only_new_empty_directories(tmp_path: Path) -> None:
    workspace = tmp_path / "nested" / "mutable"
    workspace.mkdir(parents=True)
    blocker = workspace / "parsed"
    blocker.write_text("operator-owned", encoding="utf-8")
    validator = MutableWorkspaceBoundaryValidator(ProtectedStorageInventory(()))
    decision = validator.evaluate(workspace)

    materialized = validator.materialize(decision)

    assert materialized.mode is WorkspaceMode.READ_ONLY
    assert materialized.reason == "MUTABLE_WORKSPACE_INITIALIZATION_FAILED"
    assert blocker.read_text(encoding="utf-8") == "operator-owned"
    assert not (workspace / "blobs").exists()
    assert not (workspace / "caches").exists()
    assert not (workspace / "generated").exists()


def test_failed_new_workspace_materialization_leaves_no_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "nested" / "mutable"
    validator = MutableWorkspaceBoundaryValidator(ProtectedStorageInventory(()))
    decision = validator.evaluate(workspace)
    original_mkdir = Path.mkdir

    def fail_parsed(path: Path, *args: object, **kwargs: object) -> None:
        if path == workspace / "parsed":
            raise OSError("injected failure")
        original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_parsed)
    materialized = validator.materialize(decision)

    assert materialized.mode is WorkspaceMode.READ_ONLY
    assert not workspace.exists()
    assert not (tmp_path / "nested").exists()


def test_protected_inventory_rejects_mutable_role() -> None:
    with pytest.raises(ValueError, match="protected storage"):
        ProtectedStorageLocation("bad", Path("C:/bad"), StorageRole.MUTABLE_WORKSPACE)
