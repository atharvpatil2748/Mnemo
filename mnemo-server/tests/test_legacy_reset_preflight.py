"""Reset preflight must never turn a shared store into a deletion guess."""

import hashlib
import json
import sqlite3
from pathlib import Path
from uuid import UUID

import pytest
from mnemo_server.tools.legacy_reset_preflight import (
    LegacyResetTarget,
    inspect_legacy_reset_target,
)

_A = UUID("85858585-8585-8585-8585-858585858585")
_B = UUID("86868686-8686-8686-8686-868686868686")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> Path:
    database = tmp_path / "data" / "index.db"
    database.parent.mkdir()
    connection = sqlite3.connect(database)
    connection.executescript(
        "CREATE TABLE notebooks(notebook_id TEXT PRIMARY KEY);"
        "CREATE TABLE sources(source_id TEXT PRIMARY KEY,notebook_id TEXT,document_id TEXT);"
        "CREATE TABLE documents(document_id TEXT PRIMARY KEY,current_hash TEXT);"
        "CREATE TABLE document_versions(version_id TEXT PRIMARY KEY,"
        "document_id TEXT,content_hash TEXT);"
        "CREATE TABLE active_index_generations(generation_id TEXT);"
    )
    connection.executemany("INSERT INTO notebooks VALUES(?)", [(str(_A),), (str(_B),)])
    connection.execute("INSERT INTO documents VALUES('shared',?)", ("a" * 64,))
    connection.execute("INSERT INTO document_versions VALUES('v1','shared',?)", ("a" * 64,))
    connection.executemany(
        "INSERT INTO sources VALUES(?,?,?)",
        [("source-a", str(_A), "shared"), ("source-b", str(_B), "shared")],
    )
    connection.commit()
    connection.close()
    return database


def test_shared_document_is_reported_without_writing(tmp_path: Path) -> None:
    database = _fixture(tmp_path)
    digest = _sha256(database)
    target = LegacyResetTarget(
        database=Path("data/index.db"), notebook_ids=(_A, _B), expected_sha256=digest
    )
    report = inspect_legacy_reset_target(workspace=tmp_path, target=target)
    assert report.cross_target_shared_documents == 1
    assert report.counts["documents"] == 1
    assert report.counts["sources"] == 2
    assert report.blockers == ("live_consumer_quiescence_not_established",)
    assert _sha256(database) == digest
    assert not Path(str(database) + "-wal").exists()
    assert not Path(str(database) + "-shm").exists()


def test_partial_allowlist_and_active_state_fail_closed(tmp_path: Path) -> None:
    database = _fixture(tmp_path)
    connection = sqlite3.connect(database)
    connection.execute("INSERT INTO active_index_generations VALUES('generation')")
    connection.commit()
    connection.close()
    report = inspect_legacy_reset_target(
        workspace=tmp_path,
        target=LegacyResetTarget(
            database=Path("data/index.db"), notebook_ids=(_A,), expected_sha256=_sha256(database)
        ),
    )
    assert "notebook_allowlist_does_not_cover_store" in report.blockers
    assert "retained_or_active:active_index_generations" in report.blockers


def test_registered_authority_and_changed_fingerprint_block(tmp_path: Path) -> None:
    _fixture(tmp_path)
    config = tmp_path / "config" / "production"
    config.mkdir(parents=True)
    (config / "full_multilingual_v2.production.json").write_text(
        json.dumps({"corpus": {"database_path": "data/index.db"}}), encoding="utf-8"
    )
    (tmp_path / "mnemo.toml").write_text(
        '[storage.sqlite]\npath = "data/index.db"\n', encoding="utf-8"
    )
    report = inspect_legacy_reset_target(
        workspace=tmp_path,
        target=LegacyResetTarget(
            database=Path("data/index.db"), notebook_ids=(_A, _B), expected_sha256="0" * 64
        ),
    )
    assert "database_fingerprint_changed" in report.blockers
    assert "production_manifest" in report.blockers
    assert "core_runtime_config" in report.blockers


def test_outside_workspace_rejected(tmp_path: Path) -> None:
    database = _fixture(tmp_path)
    with pytest.raises(ValueError):
        inspect_legacy_reset_target(
            workspace=tmp_path / "data",
            target=LegacyResetTarget(
                database=database, notebook_ids=(_A, _B), expected_sha256=_sha256(database)
            ),
        )


def test_wal_inventory_reads_committed_logical_rows_without_cleanup(tmp_path: Path) -> None:
    database = _fixture(tmp_path)
    connection = sqlite3.connect(database)
    assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    connection.execute("INSERT INTO documents VALUES('from-wal',?)", ("b" * 64,))
    connection.execute("INSERT INTO document_versions VALUES('v2','from-wal',?)", ("b" * 64,))
    connection.execute("INSERT INTO sources VALUES('source-wal',?,?)", (str(_A), "from-wal"))
    connection.commit()
    assert Path(str(database) + "-wal").stat().st_size > 0
    digest = _sha256(database)
    report = inspect_legacy_reset_target(
        workspace=tmp_path,
        target=LegacyResetTarget(
            database=Path("data/index.db"),
            notebook_ids=(_A, _B),
            expected_sha256=digest,
        ),
    )
    assert report.counts["documents"] == 2
    assert report.counts["sources"] == 3
    assert "nonempty_wal" in report.blockers
    assert _sha256(database) == digest
    connection.close()
