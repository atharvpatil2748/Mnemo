"""Fail-closed cleanup of disposable two-corpus rebuild outputs only."""

from __future__ import annotations

import importlib
import json
import os
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import NAMESPACE_URL, uuid5


class _WindowsFileLock(Protocol):
    LK_NBLCK: int
    LK_UNLCK: int

    def locking(self, fd: int, mode: int, nbytes: int) -> None: ...


def _link_or_junction(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _output_root(workspace: Path) -> Path:
    workspace = workspace.resolve(strict=True)
    scratch = workspace / "scratch"
    root = scratch / "two_corpus_rebuilds"
    if _link_or_junction(scratch) or _link_or_junction(root):
        raise RuntimeError("rebuild output root may not be a link or junction")
    scratch.mkdir(exist_ok=True)
    root.mkdir(exist_ok=True)
    if root.resolve(strict=True) != workspace / "scratch" / "two_corpus_rebuilds":
        raise RuntimeError("rebuild output root escaped the workspace")
    return root


@contextmanager
def exclusive_rebuild_lock(workspace: Path) -> Iterator[None]:
    """Serialize destructive preflight and both notebook builds across processes."""
    root = _output_root(workspace)
    lock_path = root / ".rebuild.lock"
    if _link_or_junction(lock_path):
        raise RuntimeError("rebuild lock may not be a link or junction")
    with lock_path.open("a+b") as lock:
        lock.seek(0)
        lock.write(b"\0")
        lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                # The module is Windows-only; Linux type stubs omit its API.
                msvcrt = cast(_WindowsFileLock, importlib.import_module("msvcrt"))
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl = importlib.import_module("fcntl")
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError("another two-corpus rebuild is active") from error
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl = importlib.import_module("fcntl")
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _inspect_runtime(
    runtime: Path,
    *,
    root: Path,
    source_hashes: tuple[set[str], set[str]],
    pair_id: str,
    input_identities: dict[str, str],
) -> dict[str, Any]:
    """Require an owned notebook and exact in-scope source ancestry before deletion."""
    if (
        runtime.parent != root
        or len(runtime.name) != 32
        or any(char not in "0123456789abcdef" for char in runtime.name)
    ):
        raise RuntimeError(f"ambiguous rebuild directory: {runtime}")
    if _link_or_junction(runtime):
        raise RuntimeError(f"linked rebuild directory: {runtime}")
    if not runtime.is_dir() or runtime.resolve(strict=True) != root / runtime.name:
        raise RuntimeError(f"rebuild directory escaped its dedicated root: {runtime}")
    for current, directories, files in os.walk(runtime, followlinks=False):
        if any(_link_or_junction(Path(current) / name) for name in directories + files):
            raise RuntimeError(f"linked content in rebuild directory: {runtime}")
    expected_notebook = str(uuid5(NAMESPACE_URL, f"mnemo:evaluation-rebuild:{runtime.name}"))
    owner_path = runtime / "rebuild-owner.json"
    owner: dict[str, Any] | None = None
    if owner_path.exists():
        owner = json.loads(owner_path.read_text(encoding="utf-8"))
        label = owner.get("label") if isinstance(owner, dict) else None
        if not isinstance(label, str):
            raise RuntimeError(f"rebuild ownership label is invalid: {runtime}")
        if not isinstance(owner, dict) or owner != {
            "schema": "mnemo.two-corpus-rebuild-owner/1",
            "run_id": runtime.name,
            "notebook_id": expected_notebook,
            "pair_id": pair_id,
            "label": label,
            "input_identity": input_identities.get(label),
        }:
            raise RuntimeError(f"rebuild ownership does not match: {runtime}")
        if owner["label"] not in {"personal_44", "codex_downloaded_24"}:
            raise RuntimeError(f"rebuild label is not approved: {runtime}")
    database = runtime / "mnemo.db"
    hashes: set[str] = set()
    if database.exists():
        connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True)
        try:
            tables = {
                str(row[0])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "notebooks" in tables:
                notebooks = connection.execute("SELECT notebook_id,title FROM notebooks").fetchall()
                if notebooks != [(expected_notebook, f"Evaluation rebuild {runtime.name}")]:
                    raise RuntimeError(f"rebuild notebook identity differs: {runtime}")
            elif owner is None:
                raise RuntimeError(f"unidentified rebuild database: {runtime}")
            if "documents" in tables:
                hashes = {
                    str(row[0]) for row in connection.execute("SELECT current_hash FROM documents")
                }
        finally:
            connection.close()
        matches = [index for index, allowed in enumerate(source_hashes) if hashes <= allowed]
        if not matches:
            raise RuntimeError(f"rebuild contains out-of-scope documents: {runtime}")
        if (
            owner is not None
            and hashes
            and (
                (owner["label"] == "personal_44" and 0 not in matches)
                or (owner["label"] == "codex_downloaded_24" and 1 not in matches)
            )
        ):
            raise RuntimeError(f"rebuild source scope differs from owner: {runtime}")
    elif owner is None:
        raise RuntimeError(f"unidentified rebuild output without database: {runtime}")
    return {
        "runtime": str(runtime),
        "notebook_id": expected_notebook,
        "indexed_documents": len(hashes),
        "label": owner["label"] if owner is not None else "legacy_verified_rebuild",
    }


def inspect_previous_rebuilds(
    *,
    workspace: Path,
    manifests: tuple[dict[str, Any], dict[str, Any]],
    pair_id: str,
) -> list[dict[str, Any]]:
    """Preflight every disposable output without deleting it."""
    candidate_root = workspace.resolve(strict=True) / "scratch" / "two_corpus_rebuilds"
    if not candidate_root.exists():
        return []
    root = _output_root(workspace)
    source_hashes = (
        {str(item["sha256"]) for item in manifests[0]["sources"]},
        {str(item["sha256"]) for item in manifests[1]["sources"]},
    )
    input_identities = {
        str(manifest["label"]): str(manifest["notebook_input_identity"]) for manifest in manifests
    }
    if any(not hashes for hashes in source_hashes):
        raise RuntimeError("cannot clean rebuilds without complete source manifests")
    targets = sorted(path for path in root.iterdir() if path.name != ".rebuild.lock")
    return [
        _inspect_runtime(
            path,
            root=root,
            source_hashes=source_hashes,
            pair_id=pair_id,
            input_identities=input_identities,
        )
        for path in targets
    ]


def delete_previous_rebuilds(
    *,
    workspace: Path,
    manifests: tuple[dict[str, Any], dict[str, Any]],
    pair_id: str,
) -> list[dict[str, Any]]:
    """Remove only preflighted, two-corpus-derived runtimes."""
    inspected = inspect_previous_rebuilds(workspace=workspace, manifests=manifests, pair_id=pair_id)
    root = _output_root(workspace)
    for item in inspected:
        target = Path(item["runtime"])
        if target.parent != root or _link_or_junction(target) or not target.is_dir():
            raise RuntimeError(f"rebuild target changed before deletion: {target}")
    for item in inspected:
        shutil.rmtree(Path(item["runtime"]))
    return inspected
