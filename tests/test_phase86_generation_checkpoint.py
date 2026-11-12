"""Disposable WAL visibility contract for the four-notebook generation input."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from scripts import run_phase86_four_notebooks as runner


def _database(path: Path, notebook_ids: tuple[UUID, ...]) -> sqlite3.Connection:
    database = path / "mnemo.db"
    writer = sqlite3.connect(database, isolation_level=None)
    assert writer.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
    writer.executescript(
        "CREATE TABLE sources(source_id TEXT PRIMARY KEY, notebook_id TEXT, document_id TEXT);"
        "CREATE TABLE documents(document_id TEXT PRIMARY KEY, current_version_id TEXT, "
        "current_hash TEXT, status TEXT);"
        "CREATE TABLE document_versions(version_id TEXT PRIMARY KEY, document_id TEXT, "
        "content_hash TEXT, status TEXT);"
        "CREATE TABLE chunks(id TEXT PRIMARY KEY, document_id TEXT, version_id TEXT, text TEXT);"
        "CREATE TABLE index_generations(generation_id TEXT PRIMARY KEY);"
    )
    for notebook_id in notebook_ids[:3]:
        _source(writer, notebook_id)
    assert writer.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone() == (0, 0, 0)
    _source(writer, notebook_ids[2])
    _source(writer, notebook_ids[3])
    return writer


def _source(writer: sqlite3.Connection, notebook_id: UUID) -> None:
    source_id, document_id, version_id = uuid4(), uuid4(), uuid4()
    content_hash = "a" * 64
    writer.execute(
        "INSERT INTO documents VALUES(?,?,?,?)",
        (str(document_id), str(version_id), content_hash, "indexed"),
    )
    writer.execute(
        "INSERT INTO document_versions VALUES(?,?,?,?)",
        (str(version_id), str(document_id), content_hash, "current"),
    )
    writer.execute(
        "INSERT INTO chunks VALUES(?,?,?,?)",
        (str(uuid4()), str(document_id), str(version_id), "evidence"),
    )
    writer.execute(
        "INSERT INTO sources VALUES(?,?,?)",
        (str(source_id), str(notebook_id), str(document_id)),
    )


def test_checkpoint_exposes_wal_only_marathi_and_english_memberships(tmp_path: Path) -> None:
    ids = tuple(uuid4() for _ in range(4))
    writer = _database(tmp_path, ids)
    database = tmp_path / "mnemo.db"
    try:
        live = runner.generation_membership_census(database, ids, immutable=False)
        assert [len(group) for group in live] == [1, 1, 2, 1]
        immutable_uri = database.resolve().as_uri() + "?mode=ro&immutable=1"
        with sqlite3.connect(immutable_uri, uri=True) as frozen:
            assert [
                frozen.execute(
                    "SELECT COUNT(*) FROM sources WHERE notebook_id=?", (str(notebook_id),)
                ).fetchone()[0]
                for notebook_id in ids
            ] == [1, 1, 1, 0]
        checked = runner.checkpoint_and_verify_generation_input(database, ids)
        assert checked == live
        assert runner.generation_membership_census(database, ids, immutable=True) == live
    finally:
        writer.close()


def test_busy_checkpoint_fails_closed(tmp_path: Path) -> None:
    ids = tuple(uuid4() for _ in range(4))
    writer = _database(tmp_path, ids)
    database = tmp_path / "mnemo.db"
    reader = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT COUNT(*) FROM sources").fetchone()
        _source(writer, ids[3])
        with pytest.raises(RuntimeError, match=r"checkpoint.*busy|checkpoint.*incomplete"):
            runner.checkpoint_and_verify_generation_input(database, ids)
    finally:
        reader.close()
        writer.close()


def test_checkpoint_error_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = tuple(uuid4() for _ in range(4))
    writer = _database(tmp_path, ids)
    try:

        def unavailable(*_args: object, **_kwargs: object) -> sqlite3.Connection:
            raise sqlite3.OperationalError("checkpoint storage unavailable")

        monkeypatch.setattr(runner.sqlite3, "connect", unavailable)
        with pytest.raises(RuntimeError, match=r"checkpoint.*failed"):
            runner.checkpoint_and_verify_generation_input(tmp_path / "mnemo.db", ids)
    finally:
        writer.close()


def test_census_identity_mismatch_fails_after_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = tuple(uuid4() for _ in range(4))
    writer = _database(tmp_path, ids)
    actual = runner.generation_membership_census

    def changed(database: Path, selected: tuple[UUID, ...], *, immutable: bool):
        groups = actual(database, selected, immutable=immutable)
        return (*groups[:-1], ()) if immutable else groups

    monkeypatch.setattr(runner, "generation_membership_census", changed)
    try:
        with pytest.raises(RuntimeError, match="census differs"):
            runner.checkpoint_and_verify_generation_input(tmp_path / "mnemo.db", ids)
    finally:
        writer.close()


def test_census_rejects_changed_source_identity_not_only_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = tuple(uuid4() for _ in range(4))
    writer = _database(tmp_path, ids)
    actual = runner.generation_membership_census

    def changed(database: Path, selected: tuple[UUID, ...], *, immutable: bool):
        groups = actual(database, selected, immutable=immutable)
        if not immutable:
            return groups
        return (*groups[:-1], ((*groups[-1][0][:-1], "wrong identity"),))

    monkeypatch.setattr(runner, "generation_membership_census", changed)
    try:
        with pytest.raises(RuntimeError, match="census differs"):
            runner.checkpoint_and_verify_generation_input(tmp_path / "mnemo.db", ids)
    finally:
        writer.close()


def test_generation_builder_is_not_called_for_invalid_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mnemo_server.services import scope_authority

    plan = json.loads(runner.PLAN.read_text(encoding="utf-8"))
    ids = (UUID(plan["existing_notebook"]["id"]), *runner.notebook_ids(plan).values())
    writer = _database(tmp_path, ids)
    authority = scope_authority.SQLiteNotebookScopeAuthority(tmp_path / "acl.db")
    authority.initialize()
    actor = UUID(plan["disposable_actor_id"])
    for notebook_id in ids:
        authority.grant(actor_id=actor, notebook_id=notebook_id, role="owner", operator_id=actor)
    monkeypatch.setattr(runner, "reconcile_legacy_schema", lambda _database: None)
    actual = runner.generation_membership_census

    def incomplete(database: Path, selected: tuple[UUID, ...], *, immutable: bool):
        rows = actual(database, selected, immutable=immutable)
        return (*rows[:-1], ()) if immutable else rows

    monkeypatch.setattr(runner, "generation_membership_census", incomplete)
    called = False

    async def builder(**_kwargs: object) -> dict[str, object]:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr("mnemo.phase85.isolated_multilingual.build_isolated_multilingual", builder)
    try:
        with pytest.raises(RuntimeError, match=r"census|notebook"):
            asyncio.run(
                runner.build_generations(
                    plan, tmp_path, tmp_path, runner.Log(tmp_path / "events.jsonl", "fixture")
                )
            )
        assert not called
        assert writer.execute("SELECT COUNT(*) FROM index_generations").fetchone() == (0,)
        assert not (tmp_path / "provider_results.json").exists()
    finally:
        writer.close()
