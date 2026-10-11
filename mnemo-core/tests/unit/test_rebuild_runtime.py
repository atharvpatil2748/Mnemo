"""Both rebuild families use the same guarded runtime authority."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest
from mnemo.phase85.rebuild_runtime import resolve_governed_rebuild_runtime


def _runtime(root: Path, family: str) -> tuple[Path, str]:
    run_id = "a" * 32
    runtime = root / "scratch" / family / run_id
    runtime.mkdir(parents=True)
    identity_kind = (
        "evaluation-rebuild" if family == "two_corpus_rebuilds" else "isolated-rebuild-canary"
    )
    notebook = str(uuid5(NAMESPACE_URL, f"mnemo:{identity_kind}:{run_id}"))
    owner = {
        "pair_id": "b" * 64,
        "label": "personal_44",
        "input_identity": "c" * 64,
    }
    status = {
        "runtime": str(runtime.resolve()),
        "run_id": run_id,
        "notebook_id": notebook,
        "activation": "inactive",
        "sources": [{"sha256": "d" * 64}],
    }
    if family == "two_corpus_rebuilds":
        status["rebuild_owner"] = owner
        (runtime / "rebuild-owner.json").write_text(
            json.dumps(
                {
                    "schema": "mnemo.two-corpus-rebuild-owner/1",
                    "run_id": run_id,
                    "notebook_id": notebook,
                    **owner,
                }
            ),
            encoding="utf-8",
        )
    (runtime / "rebuild-status.json").write_text(json.dumps(status), encoding="utf-8")
    connection = sqlite3.connect(runtime / "mnemo.db")
    try:
        connection.executescript(
            "CREATE TABLE notebooks(notebook_id TEXT);"
            "CREATE TABLE documents(document_id TEXT,current_hash TEXT);"
            "CREATE TABLE sources(notebook_id TEXT,document_id TEXT);"
        )
        connection.execute("INSERT INTO notebooks VALUES(?)", (notebook,))
        connection.execute("INSERT INTO documents VALUES(?,?)", ("document", "d" * 64))
        connection.execute("INSERT INTO sources VALUES(?,?)", (notebook, "document"))
        connection.commit()
    finally:
        connection.close()
    return runtime, notebook


@pytest.mark.parametrize("family", ["isolated_rebuilds", "two_corpus_rebuilds"])
def test_governed_runtime_accepts_exact_owned_notebook(tmp_path: Path, family: str) -> None:
    runtime, notebook = _runtime(tmp_path, family)
    status = resolve_governed_rebuild_runtime(workspace=tmp_path, runtime=runtime)
    assert status["notebook_id"] == notebook


def test_governed_runtime_rejects_changed_owner_and_source(tmp_path: Path) -> None:
    runtime, _ = _runtime(tmp_path, "two_corpus_rebuilds")
    owner_path = runtime / "rebuild-owner.json"
    owner = json.loads(owner_path.read_text(encoding="utf-8"))
    owner["pair_id"] = "e" * 64
    owner_path.write_text(json.dumps(owner), encoding="utf-8")
    with pytest.raises(ValueError, match="owner"):
        resolve_governed_rebuild_runtime(workspace=tmp_path, runtime=runtime)
    owner["pair_id"] = "b" * 64
    owner_path.write_text(json.dumps(owner), encoding="utf-8")
    connection = sqlite3.connect(runtime / "mnemo.db")
    try:
        connection.execute("UPDATE documents SET current_hash=?", ("f" * 64,))
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ValueError, match="source hashes"):
        resolve_governed_rebuild_runtime(workspace=tmp_path, runtime=runtime)
