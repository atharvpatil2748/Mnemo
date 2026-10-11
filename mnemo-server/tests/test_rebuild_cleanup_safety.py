"""Disposable ownership checks for the two-corpus rebuild cleanup boundary."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest
from mnemo_server.tools.rebuild_cleanup import (
    _inspect_runtime,
    delete_previous_rebuilds,
    exclusive_rebuild_lock,
    inspect_previous_rebuilds,
)


def _owned_runtime(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    root = tmp_path / "scratch" / "two_corpus_rebuilds"
    root.mkdir(parents=True)
    runtime = root / ("a" * 32)
    runtime.mkdir()
    owner = {
        "schema": "mnemo.two-corpus-rebuild-owner/1",
        "run_id": runtime.name,
        "notebook_id": str(uuid5(NAMESPACE_URL, f"mnemo:evaluation-rebuild:{runtime.name}")),
        "pair_id": "pair",
        "label": "personal_44",
        "input_identity": "input-a",
    }
    (runtime / "rebuild-owner.json").write_text(json.dumps(owner), encoding="utf-8")
    with closing(sqlite3.connect(runtime / "mnemo.db")) as connection, connection:
        connection.execute("CREATE TABLE notebooks(notebook_id TEXT,title TEXT)")
        connection.execute("CREATE TABLE documents(current_hash TEXT)")
        connection.execute(
            "INSERT INTO notebooks VALUES(?,?)",
            (owner["notebook_id"], f"Evaluation rebuild {runtime.name}"),
        )
        connection.execute("INSERT INTO documents VALUES(?)", ("1" * 64,))
    return root, runtime, owner


def _inspect(root: Path, runtime: Path) -> dict[str, object]:
    return _inspect_runtime(
        runtime,
        root=root,
        source_hashes=({"1" * 64}, {"2" * 64}),
        pair_id="pair",
        input_identities={"personal_44": "input-a", "codex_downloaded_24": "input-b"},
    )


def test_owned_rebuild_is_inventoried_without_mutation(tmp_path: Path) -> None:
    root, runtime, owner = _owned_runtime(tmp_path)
    assert _inspect(root, runtime)["indexed_documents"] == 1
    manifests = (
        {
            "label": "personal_44",
            "notebook_input_identity": "input-a",
            "sources": [{"sha256": "1" * 64}],
        },
        {
            "label": "codex_downloaded_24",
            "notebook_input_identity": "input-b",
            "sources": [{"sha256": "2" * 64}],
        },
    )
    rows = inspect_previous_rebuilds(workspace=tmp_path, manifests=manifests, pair_id="pair")
    assert rows == [
        {
            "runtime": str(runtime),
            "notebook_id": owner["notebook_id"],
            "indexed_documents": 1,
            "label": "personal_44",
        }
    ]
    assert (runtime / "mnemo.db").is_file()


@pytest.mark.parametrize(
    ("defect", "message"),
    [
        ("run-name", "ambiguous rebuild directory"),
        ("owner-label", "ownership does not match"),
        ("owner-pair", "ownership does not match"),
        ("owner-scope", "source scope differs from owner"),
        ("notebook", "notebook identity differs"),
        ("hash", "out-of-scope documents"),
    ],
)
def test_cleanup_refuses_ambiguous_or_out_of_scope_disposable_runtime(
    tmp_path: Path, defect: str, message: str
) -> None:
    root, runtime, owner = _owned_runtime(tmp_path)
    if defect == "run-name":
        runtime = root / "not-an-approved-run"
    elif defect.startswith("owner-"):
        if defect == "owner-label":
            owner["label"] = "unapproved"
        elif defect == "owner-pair":
            owner["pair_id"] = "different"
        else:
            owner["label"] = "codex_downloaded_24"
            owner["input_identity"] = "input-b"
        (runtime / "rebuild-owner.json").write_text(json.dumps(owner), encoding="utf-8")
    else:
        with closing(sqlite3.connect(runtime / "mnemo.db")) as connection, connection:
            if defect == "notebook":
                connection.execute("UPDATE notebooks SET notebook_id='other'")
            else:
                connection.execute("UPDATE documents SET current_hash=?", ("3" * 64,))
    with pytest.raises(RuntimeError, match=message):
        _inspect(root, runtime)
    assert (root / ("a" * 32) / "mnemo.db").is_file()


def test_cleanup_refuses_linked_content_in_owned_runtime(tmp_path: Path) -> None:
    root, runtime, _ = _owned_runtime(tmp_path)
    alias = runtime / "outside-alias"
    try:
        alias.symlink_to(tmp_path, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("disposable symlinks unavailable")
    with pytest.raises(RuntimeError, match="linked content"):
        _inspect(root, runtime)


def test_cleanup_refuses_unidentified_or_malformed_disposable_output(tmp_path: Path) -> None:
    root, runtime, owner = _owned_runtime(tmp_path)
    (runtime / "rebuild-owner.json").unlink()
    with closing(sqlite3.connect(runtime / "mnemo.db")) as connection, connection:
        connection.execute("DROP TABLE notebooks")
    with pytest.raises(RuntimeError, match="unidentified rebuild database"):
        _inspect(root, runtime)
    (runtime / "rebuild-owner.json").write_text(json.dumps(owner), encoding="utf-8")
    assert _inspect(root, runtime)["indexed_documents"] == 1
    root, runtime, _ = _owned_runtime(tmp_path / "without-database")
    (runtime / "mnemo.db").unlink()
    assert _inspect(root, runtime)["indexed_documents"] == 0
    (runtime / "rebuild-owner.json").unlink()
    with pytest.raises(RuntimeError, match="unidentified rebuild output"):
        _inspect(root, runtime)


@pytest.mark.parametrize("invalid_label", [None, 42, ["personal_44"]])
def test_cleanup_refuses_owner_with_nonstring_label(tmp_path: Path, invalid_label: object) -> None:
    root, runtime, owner = _owned_runtime(tmp_path)
    invalid_owner: dict[str, object] = dict(owner)
    invalid_owner["label"] = invalid_label
    (runtime / "rebuild-owner.json").write_text(json.dumps(invalid_owner), encoding="utf-8")
    with pytest.raises(RuntimeError, match="ownership label is invalid"):
        _inspect(root, runtime)


def test_cleanup_requires_complete_manifests_and_exclusive_lock(tmp_path: Path) -> None:
    root, runtime, _ = _owned_runtime(tmp_path)
    manifests = (
        {"label": "personal_44", "notebook_input_identity": "input-a", "sources": []},
        {
            "label": "codex_downloaded_24",
            "notebook_input_identity": "input-b",
            "sources": [{"sha256": "2" * 64}],
        },
    )
    with pytest.raises(RuntimeError, match="complete source manifests"):
        inspect_previous_rebuilds(workspace=tmp_path, manifests=manifests, pair_id="pair")
    assert runtime.is_dir()
    with exclusive_rebuild_lock(tmp_path):
        assert (root / ".rebuild.lock").is_file()
        with (
            pytest.raises(RuntimeError, match="another two-corpus rebuild is active"),
            exclusive_rebuild_lock(tmp_path),
        ):
            pytest.fail("a second writer acquired the same rebuild lock")


def test_exact_owned_disposable_cleanup_is_idempotent_and_preserves_lock(tmp_path: Path) -> None:
    root, runtime, owner = _owned_runtime(tmp_path)
    manifests = (
        {
            "label": "personal_44",
            "notebook_input_identity": "input-a",
            "sources": [{"sha256": "1" * 64}],
        },
        {
            "label": "codex_downloaded_24",
            "notebook_input_identity": "input-b",
            "sources": [{"sha256": "2" * 64}],
        },
    )
    with exclusive_rebuild_lock(tmp_path):
        removed = delete_previous_rebuilds(workspace=tmp_path, manifests=manifests, pair_id="pair")
        assert removed[0]["notebook_id"] == owner["notebook_id"]
        assert not runtime.exists()
        assert (root / ".rebuild.lock").is_file()
        assert (
            delete_previous_rebuilds(workspace=tmp_path, manifests=manifests, pair_id="pair") == []
        )
