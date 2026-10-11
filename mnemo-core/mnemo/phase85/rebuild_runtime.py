"""One read-only authority for governed isolated rebuild runtime identity."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5


def resolve_governed_rebuild_runtime(
    *, workspace: Path, runtime: Path, notebook_id: UUID | None = None
) -> dict[str, Any]:
    """Bind either rebuild family to its status, owner, and persisted notebook."""
    root = workspace.resolve(strict=True)
    target = runtime.resolve(strict=True)
    if (
        runtime.is_symlink()
        or (hasattr(runtime, "is_junction") and runtime.is_junction())
        or target.name != runtime.name
    ):
        raise ValueError("rebuild runtime is linked or renamed")
    family = target.parent.name
    if (
        family not in {"isolated_rebuilds", "two_corpus_rebuilds"}
        or target.parent.parent != root / "scratch"
        or not target.name.isascii()
        or len(target.name) != 32
        or any(char not in "0123456789abcdef" for char in target.name)
    ):
        raise ValueError("target is not a governed isolated rebuild runtime")
    status_path = target / "rebuild-status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    identity_kind = (
        "evaluation-rebuild" if family == "two_corpus_rebuilds" else "isolated-rebuild-canary"
    )
    expected = uuid5(NAMESPACE_URL, f"mnemo:{identity_kind}:{target.name}")
    if (
        not isinstance(status, dict)
        or status.get("runtime") != str(target)
        or status.get("run_id") != target.name
        or status.get("notebook_id") != str(expected)
        or status.get("activation") != "inactive"
        or (notebook_id is not None and notebook_id != expected)
    ):
        raise ValueError("governed rebuild status identity is invalid")
    sources = status.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("governed rebuild has no source authority")
    expected_hashes: Counter[str] = Counter()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("governed rebuild source record is invalid")
        digest = source.get("sha256")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise ValueError("governed rebuild source digest is invalid")
        expected_hashes[digest] += 1
    owner_path = target / "rebuild-owner.json"
    if family == "two_corpus_rebuilds":
        owner = json.loads(owner_path.read_text(encoding="utf-8"))
        recorded_owner = status.get("rebuild_owner")
        if (
            not isinstance(owner, dict)
            or not isinstance(recorded_owner, dict)
            or owner.get("schema") != "mnemo.two-corpus-rebuild-owner/1"
            or owner.get("run_id") != target.name
            or owner.get("notebook_id") != str(expected)
            or owner.get("label") not in {"personal_44", "codex_downloaded_24"}
            or owner.get("pair_id") != recorded_owner.get("pair_id")
            or {key: owner.get(key) for key in ("pair_id", "label", "input_identity")}
            != recorded_owner
        ):
            raise ValueError("two-corpus rebuild owner does not match status")
        for key in ("pair_id", "input_identity"):
            value = owner[key]
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
            ):
                raise ValueError("two-corpus rebuild owner digest is invalid")
    elif owner_path.exists():
        raise ValueError("canary runtime has unexpected two-corpus ownership")
    database = target / "mnemo.db"
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute("SELECT notebook_id FROM notebooks").fetchall()
        if rows != [(str(expected),)]:
            raise ValueError("governed rebuild notebook identity or membership is invalid")
        actual_hashes = Counter(
            str(row[0])
            for row in connection.execute(
                "SELECT d.current_hash FROM sources s JOIN documents d "
                "ON d.document_id=s.document_id WHERE s.notebook_id=?",
                (str(expected),),
            )
        )
        if actual_hashes != expected_hashes:
            raise ValueError("governed rebuild source hashes differ from status")
    finally:
        connection.close()
    return status
