"""Destructive reset is exercised only against disposable SQLite fixtures."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from mnemo_server.evaluation.canonical_json import canonical_json_sha256_v1
from mnemo_server.tools import legacy_decommission as reset


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path, *, second: bool = False) -> Path:
    database = tmp_path / "scratch" / "legacy" / "mnemo.db"
    database.parent.mkdir(parents=True)
    connection = sqlite3.connect(database)
    connection.executescript(
        "CREATE TABLE schema_versions(version INTEGER PRIMARY KEY);"
        "CREATE TABLE notebooks(notebook_id TEXT PRIMARY KEY);"
        "CREATE TABLE documents(document_id TEXT PRIMARY KEY,current_hash TEXT);"
        "CREATE TABLE document_versions(version_id TEXT PRIMARY KEY,"
        "document_id TEXT REFERENCES documents(document_id),content_hash TEXT);"
        "CREATE TABLE sources(source_id TEXT PRIMARY KEY,"
        "notebook_id TEXT REFERENCES notebooks(notebook_id),"
        "document_id TEXT REFERENCES documents(document_id));"
        "CREATE TABLE index_generations(generation_id TEXT PRIMARY KEY);"
        "CREATE TABLE active_index_generations(generation_id TEXT REFERENCES "
        "index_generations(generation_id));"
        "CREATE TABLE multilingual_v2_alias_sets(alias_set_digest TEXT PRIMARY KEY);"
        "CREATE VIRTUAL TABLE ocr_fts USING fts5(text);"
    )
    connection.execute("INSERT INTO notebooks VALUES('a')")
    connection.execute("INSERT INTO documents VALUES('shared','hash')")
    connection.execute("INSERT INTO document_versions VALUES('v1','shared','hash')")
    connection.execute("INSERT INTO sources VALUES('source-a','a','shared')")
    connection.execute("INSERT INTO index_generations VALUES('generation-a')")
    connection.execute("INSERT INTO active_index_generations VALUES('generation-a')")
    connection.execute("INSERT INTO multilingual_v2_alias_sets VALUES('alias-a')")
    connection.execute("INSERT INTO ocr_fts VALUES('derived text')")
    if second:
        connection.execute("INSERT INTO notebooks VALUES('b')")
        connection.execute("INSERT INTO sources VALUES('source-b','b','shared')")
    connection.commit()
    connection.close()
    return database


def _target(database: Path, *, notebooks: tuple[str, ...] = ("a",)) -> reset.FullStoreTarget:
    return reset.FullStoreTarget(
        database=database,
        expected_sha256=_digest(database),
        notebook_ids=notebooks,
        generation_ids=("generation-a",),
        alias_digests=("alias-a",),
        snapshot=database.parent / "snapshot.db",
    )


def test_dry_run_does_not_delete_and_full_store_executes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _fixture(tmp_path)
    target = _target(database)
    plan = reset.dry_run_full_store(workspace=tmp_path, target=target)
    assert plan.counts["documents"] == 1
    assert _digest(database) == target.expected_sha256
    monkeypatch.setattr(reset, "processes_using_files", lambda _paths: ())
    receipt = reset.execute_full_store(workspace=tmp_path, target=target)
    assert receipt["status"] == "COMPLETE"
    assert (database.parent / "snapshot.db").is_file()
    again = reset.execute_full_store(workspace=tmp_path, target=target)
    assert again["status"] == "ALREADY_COMPLETE"
    assert again["removed"] == receipt["removed"]
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM notebooks").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM ocr_fts").fetchone()[0] == 0
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_partial_allowlist_preserves_shared_document(tmp_path: Path) -> None:
    database = _fixture(tmp_path, second=True)
    before = _digest(database)
    with pytest.raises(ValueError, match="allowlist"):
        reset.dry_run_full_store(workspace=tmp_path, target=_target(database))
    assert _digest(database) == before


def test_active_consumer_blocks_before_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _fixture(tmp_path)
    before = _digest(database)
    monkeypatch.setattr(reset, "processes_using_files", lambda _paths: (12345,))
    with pytest.raises(RuntimeError, match="CONSUMERS_ACTIVE"):
        reset.execute_full_store(workspace=tmp_path, target=_target(database))
    assert _digest(database) == before
    assert not (database.parent / "snapshot.db").exists()


def test_changed_fingerprint_blocks(tmp_path: Path) -> None:
    database = _fixture(tmp_path)
    target = _target(database)
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO notebooks VALUES('unexpected')")
    with pytest.raises(ValueError, match="fingerprint"):
        reset.dry_run_full_store(workspace=tmp_path, target=target)


def test_transaction_failure_preserves_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _fixture(tmp_path)
    target = _target(database)
    monkeypatch.setattr(reset, "processes_using_files", lambda _paths: ())

    def fail(_db: sqlite3.Connection, _tables: set[str]) -> list[str]:
        raise RuntimeError("injected failure")

    monkeypatch.setattr(reset, "_deletion_order", fail)
    with pytest.raises(RuntimeError, match="injected failure"):
        reset.execute_full_store(workspace=tmp_path, target=target)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM notebooks").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert (database.parent / "snapshot.db").is_file()


def test_nonempty_wal_requires_exact_allowlist(tmp_path: Path) -> None:
    database = _fixture(tmp_path)
    child = (
        "import os,sqlite3,sys;"
        "c=sqlite3.connect(sys.argv[1]);"
        'c.execute("PRAGMA journal_mode=WAL");'
        "c.execute(\"INSERT INTO notebooks VALUES('wal-only')\");"
        "c.commit();os._exit(0)"
    )
    subprocess.run([sys.executable, "-c", child, str(database)], check=True)
    wal = Path(str(database) + "-wal")
    assert wal.stat().st_size > 0
    target = _target(database, notebooks=("a", "wal-only"))
    with pytest.raises(ValueError, match="WAL fingerprint"):
        reset.dry_run_full_store(workspace=tmp_path, target=target)
    allowed = reset.FullStoreTarget(
        database=database,
        expected_sha256=target.expected_sha256,
        expected_wal_sha256=_digest(wal),
        notebook_ids=target.notebook_ids,
        generation_ids=target.generation_ids,
        alias_digests=target.alias_digests,
        snapshot=target.snapshot,
    )
    plan = reset.dry_run_full_store(workspace=tmp_path, target=allowed)
    assert plan.counts["notebooks"] == 2


def test_current_production_schema_deletion_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise real schema/FTS triggers on a newly made fixture, never a live DB."""
    from mnemo.storage.sqlite import _SCHEMA_SQL

    database = tmp_path / "scratch" / "schema-fixture" / "mnemo.db"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.executescript(_SCHEMA_SQL)
        connection.execute("INSERT INTO notebooks VALUES('a','title',NULL,'now','now','{}')")
        connection.execute("INSERT INTO documents VALUES('doc','v1','hash','ready','now','now')")
        connection.execute(
            "INSERT INTO document_versions VALUES('v1','doc','hash','{}','ready','now')"
        )
        connection.execute("INSERT INTO sources VALUES('source-a','a','doc','now')")
        connection.execute(
            "INSERT INTO chunks(id,document_id,version_id,text,chunk_type,"
            "position_section_index,position_chunk_index,source_start_ordinal,"
            "source_end_ordinal,heading_path,sibling_ids,metadata) "
            "VALUES('chunk','doc','v1','hello','text',0,0,0,0,'[]','[]','{}')"
        )
    connection.close()
    # WAL mode is initialized by the schema; closing the last writer checkpoints it.
    target = reset.FullStoreTarget(
        database=database,
        expected_sha256=_digest(database),
        notebook_ids=("a",),
        generation_ids=(),
        alias_digests=(),
        snapshot=database.parent / "snapshot.db",
    )
    monkeypatch.setattr(reset, "processes_using_files", lambda _paths: ())
    receipt = reset.execute_full_store(workspace=tmp_path, target=target)
    assert receipt["status"] == "COMPLETE"
    removed = receipt["removed"]
    assert isinstance(removed, dict)
    assert removed["chunks"] == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fts_chunks").fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchone() is None


def test_registry_alias_is_unpublished_before_index_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _fixture(tmp_path)
    registry = tmp_path / "scratch" / "evaluation_notebooks" / "registry.json"
    registry.parent.mkdir(parents=True)
    unsigned = {
        "notebooks": {
            "phase8_5": {
                "store": "scratch/legacy",
                "notebook_id": "a",
            },
            "unrelated": {
                "store": "scratch/unrelated",
                "notebook_id": "other",
            },
        }
    }
    registry.write_text(
        json.dumps({**unsigned, "registry_digest": canonical_json_sha256_v1(unsigned)}),
        encoding="utf-8",
    )
    original = _target(database)
    target = reset.FullStoreTarget(
        database=original.database,
        expected_sha256=original.expected_sha256,
        notebook_ids=original.notebook_ids,
        generation_ids=original.generation_ids,
        alias_digests=original.alias_digests,
        snapshot=original.snapshot,
        registry=registry,
        registry_aliases=("phase8_5",),
        expected_registry_sha256=_digest(registry),
    )
    monkeypatch.setattr(reset, "processes_using_files", lambda _paths: ())
    result = reset.execute_full_store(workspace=tmp_path, target=target)
    assert result["status"] == "COMPLETE"
    after = json.loads(registry.read_text(encoding="utf-8"))
    assert "phase8_5" not in after["notebooks"]
    assert "unrelated" in after["notebooks"]
    digest = after.pop("registry_digest")
    assert digest == canonical_json_sha256_v1(after)
    assert Path(str(original.snapshot) + ".registry.json").is_file()
    repeated = reset.execute_full_store(workspace=tmp_path, target=target)
    assert repeated["status"] == "ALREADY_COMPLETE"


def test_populated_production_derived_families_are_transactionally_cleared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Populate all index-family tables in the current schema with synthetic rows."""
    from mnemo.storage.sqlite import _SCHEMA_SQL

    database = tmp_path / "scratch" / "populated-schema" / "mnemo.db"
    database.parent.mkdir(parents=True)
    connection = sqlite3.connect(database)
    connection.executescript(_SCHEMA_SQL)
    connection.execute(
        "CREATE TABLE evaluation_text_embeddings("
        "chunk_id TEXT PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,"
        "document_id TEXT NOT NULL,version_id TEXT NOT NULL,"
        "model_identity TEXT NOT NULL,model_revision TEXT NOT NULL,"
        "dimensions INTEGER NOT NULL CHECK(dimensions=1024),"
        "vector_hash TEXT NOT NULL,vector BLOB NOT NULL,"
        "normalized INTEGER NOT NULL CHECK(normalized=1))"
    )
    tables = (reset._tables(connection) & reset._INDEX_TABLES) - (
        reset._VIRTUAL_FTS | reset._USER_DATA_TABLES | {"evaluation_text_embeddings"}
    )
    made: dict[str, dict[str, object]] = {}

    def value(name: str, data_type: str) -> object:
        special: dict[str, object] = {
            "status": "ready",
            "state": "ready",
            "operation": "ocr",
            "capability": "ocr",
            "profile": "fixture",
            "mime_type": "image/png",
            "language": "en",
            "metric": "cosine",
            "normalization": "l2",
            "representation_type": "canonical",
            "container_kind": "image",
            "locator_kind": "page",
            "evidence_kind": "derived_ocr",
            "activation_mode": "first_v2_activation",
            "recovery_mode": "deactivate_v2_alias_set",
            "source_kind": "generation",
            "completeness": "complete",
            "failed_count": 0,
            "skipped_count": 0,
        }
        if name in special:
            return special[name]
        if name in {
            "metadata",
            "payload",
            "manifest",
            "model_configuration",
            "provider_metadata",
            "extraction_provenance",
            "input_scope",
        }:
            return "{}"
        if name in {
            "heading_path",
            "sibling_ids",
            "headers",
            "generation_ids",
            "rollback_generation_ids",
            "warnings",
        }:
            return "[]"
        if "hash" in name or "digest" in name or "fingerprint" in name or name == "checksum":
            return "a" * 64
        if "INT" in data_type.upper() or "REAL" in data_type.upper():
            return 1
        if "BLOB" in data_type.upper():
            return bytes((1, 2, 3))
        return "fixture-id"

    for table in reversed(reset._deletion_order(connection, tables)):
        columns = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
        row = {
            str(column[1]): value(str(column[1]), str(column[2]))
            for column in columns
            if (column[3] or column[5]) and column[4] is None
        }
        for fk in connection.execute(f'PRAGMA foreign_key_list("{table}")'):
            parent, from_column, to_column = str(fk[2]), str(fk[3]), str(fk[4])
            if parent in made and from_column in row:
                row[from_column] = made[parent][to_column]
        names = list(row)
        quoted = ",".join(f'"{name}"' for name in names)
        placeholders = ",".join("?" for _ in names)
        connection.execute(
            f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})',
            tuple(row.values()),
        )
        made[table] = row
    connection.execute(
        "INSERT INTO evaluation_text_embeddings VALUES(?,?,?,?,?,?,?,?,1)",
        (
            "fixture-id",
            "fixture-id",
            "fixture-id",
            "fixture-model",
            "fixture-revision",
            1024,
            "a" * 64,
            bytes((1, 2, 3)),
        ),
    )
    connection.execute(
        "INSERT INTO fts_chunk_titles VALUES(?,?,?,?)",
        ("fixture title", "fixture-id", "fixture-id", "fixture-id"),
    )
    connection.execute(
        "INSERT INTO ocr_fts VALUES(?,?,?,?,?,?,?)",
        (
            "fixture OCR",
            "fixture-id",
            "fixture-id",
            "fixture-id",
            "fixture-id",
            "fixture-id",
            "fixture-id",
        ),
    )
    connection.execute(
        "INSERT INTO vision_text_fts VALUES(?,?,?,?,?,?)",
        ("fixture vision", "fixture-id", "fixture-id", "fixture-id", "fixture-id", "fixture-id"),
    )
    connection.commit()
    assert connection.execute("PRAGMA foreign_key_check").fetchone() is None
    connection.close()
    target = reset.FullStoreTarget(
        database=database,
        expected_sha256=_digest(database),
        notebook_ids=("fixture-id",),
        generation_ids=("fixture-id",),
        alias_digests=("a" * 64,),
        snapshot=database.parent / "snapshot.db",
    )
    plan = reset.dry_run_full_store(workspace=tmp_path, target=target)
    assert all(plan.counts[table] == 1 for table in tables)
    assert plan.counts["evaluation_text_embeddings"] == 1
    for fts in ("fts_chunks", "fts_chunk_titles", "ocr_fts", "vision_text_fts"):
        assert plan.counts[fts] > 0, fts
    monkeypatch.setattr(reset, "processes_using_files", lambda _paths: ())
    receipt = reset.execute_full_store(workspace=tmp_path, target=target)
    assert receipt["status"] == "COMPLETE"
    removed = receipt["removed"]
    assert isinstance(removed, dict)
    assert all(removed[table] == 1 for table in tables)
    with sqlite3.connect(database) as verify:
        assert verify.execute("PRAGMA foreign_key_check").fetchone() is None
        assert verify.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


@pytest.mark.parametrize(
    ("sql", "error"),
    [
        ("CREATE TABLE unrelated_user_data(value TEXT)", "unclassified index tables"),
        ("CREATE TABLE notes(note TEXT); INSERT INTO notes VALUES('retain')", "retained user"),
        ("INSERT INTO documents VALUES('unowned','hash')", "unowned global document"),
        ("INSERT INTO index_generations VALUES('unexpected')", "generation allowlist"),
        ("INSERT INTO multilingual_v2_alias_sets VALUES('unexpected')", "alias allowlist"),
        ("INSERT INTO notebooks VALUES('unrelated')", "notebook allowlist"),
        ("INSERT INTO sources VALUES('broken','a','missing')", "foreign-key violations"),
    ],
)
def test_preflight_refuses_unsafe_disposable_inventory(
    tmp_path: Path, sql: str, error: str
) -> None:
    database = _fixture(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.executescript(sql)
    before = _digest(database)
    with pytest.raises(ValueError, match=error):
        reset.dry_run_full_store(workspace=tmp_path, target=_target(database))
    assert _digest(database) == before


@pytest.mark.parametrize("defect", ["existing-snapshot", "outside-scratch", "same-path"])
def test_preflight_refuses_unsafe_snapshot_target(tmp_path: Path, defect: str) -> None:
    database = _fixture(tmp_path)
    original = _target(database)
    snapshot = original.snapshot
    if defect == "existing-snapshot":
        snapshot.write_bytes(b"previous recovery evidence")
    elif defect == "outside-scratch":
        snapshot = tmp_path / "outside.db"
    else:
        snapshot = database
    target = reset.FullStoreTarget(
        database=database,
        expected_sha256=original.expected_sha256,
        notebook_ids=original.notebook_ids,
        generation_ids=original.generation_ids,
        alias_digests=original.alias_digests,
        snapshot=snapshot,
    )
    before = _digest(database)
    with pytest.raises(ValueError, match="snapshot path is invalid"):
        reset.dry_run_full_store(workspace=tmp_path, target=target)
    assert _digest(database) == before


@pytest.mark.parametrize(
    ("entry", "aliases", "error"),
    [
        ({}, ("a",), "registry is malformed"),
        ({"notebooks": {}}, ("a",), "alias is missing"),
        (
            {"notebooks": {"a": {"notebook_id": "other", "store": "scratch/legacy"}}},
            ("a",),
            "not allowlisted",
        ),
        (
            {"notebooks": {"a": {"notebook_id": "a", "store": "scratch/other"}}},
            ("a",),
            "another store",
        ),
        (
            {"notebooks": {"a": {"notebook_id": "a", "store": "scratch/legacy"}}},
            (),
            "no alias allowlist",
        ),
    ],
)
def test_preflight_refuses_ambiguous_registry_authority(
    tmp_path: Path, entry: dict[str, object], aliases: tuple[str, ...], error: str
) -> None:
    database = _fixture(tmp_path)
    registry = tmp_path / "scratch" / "registry.json"
    registry.write_text(json.dumps(entry), encoding="utf-8")
    original = _target(database)
    target = reset.FullStoreTarget(
        database=database,
        expected_sha256=original.expected_sha256,
        notebook_ids=original.notebook_ids,
        generation_ids=original.generation_ids,
        alias_digests=original.alias_digests,
        snapshot=original.snapshot,
        registry=registry,
        registry_aliases=aliases,
        expected_registry_sha256=_digest(registry),
    )
    before = _digest(database)
    with pytest.raises(ValueError, match=error):
        reset.dry_run_full_store(workspace=tmp_path, target=target)
    assert _digest(database) == before


def test_completed_receipt_rejects_reactivated_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _fixture(tmp_path)
    registry = tmp_path / "scratch" / "registry.json"
    registry.write_text(
        json.dumps({"notebooks": {"a": {"notebook_id": "a", "store": "scratch/legacy"}}}),
        encoding="utf-8",
    )
    original = _target(database)
    target = reset.FullStoreTarget(
        database=database,
        expected_sha256=original.expected_sha256,
        notebook_ids=original.notebook_ids,
        generation_ids=original.generation_ids,
        alias_digests=original.alias_digests,
        snapshot=original.snapshot,
        registry=registry,
        registry_aliases=("a",),
        expected_registry_sha256=_digest(registry),
    )
    monkeypatch.setattr(reset, "processes_using_files", lambda _paths: ())
    assert reset.execute_full_store(workspace=tmp_path, target=target)["status"] == "COMPLETE"
    registry.write_text(
        json.dumps({"notebooks": {"a": {"notebook_id": "a", "store": "scratch/legacy"}}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="alias has reappeared"):
        reset.execute_full_store(workspace=tmp_path, target=target)


@pytest.mark.parametrize("defect", ["receipt", "snapshot", "reintroduced-row"])
def test_completed_retirement_cannot_mask_tampered_recovery_or_reappeared_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str
) -> None:
    database = _fixture(tmp_path)
    target = _target(database)
    monkeypatch.setattr(reset, "processes_using_files", lambda _paths: ())
    assert reset.execute_full_store(workspace=tmp_path, target=target)["status"] == "COMPLETE"
    if defect == "receipt":
        receipt_path = Path(str(target.snapshot) + ".receipt.json")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["notebook_ids"] = ["unrelated"]
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        error = "receipt or recovery snapshot"
    elif defect == "snapshot":
        target.snapshot.write_bytes(b"broken recovery evidence")
        error = "receipt or recovery snapshot"
    else:
        with sqlite3.connect(database) as connection:
            connection.execute("INSERT INTO notebooks VALUES('a')")
        error = "retired index has reappeared"
    with pytest.raises(ValueError, match=error):
        reset.execute_full_store(workspace=tmp_path, target=target)


def test_inventory_change_between_consumer_check_and_snapshot_aborts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _fixture(tmp_path)
    target = _target(database)
    original = reset.dry_run_full_store
    calls = 0

    def change_after_first(
        *, workspace: Path, target: reset.FullStoreTarget
    ) -> reset.FullStorePlan:
        nonlocal calls
        calls += 1
        if calls == 2:
            with sqlite3.connect(database) as connection:
                connection.execute("INSERT INTO sources VALUES('new','a','shared')")
        return original(workspace=workspace, target=target)

    monkeypatch.setattr(reset, "processes_using_files", lambda _paths: ())
    monkeypatch.setattr(reset, "dry_run_full_store", change_after_first)
    with pytest.raises(ValueError, match="fingerprint changed"):
        reset.execute_full_store(workspace=tmp_path, target=target)
    assert not target.snapshot.exists()
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM notebooks").fetchone()[0] == 1


def test_cyclic_dependency_graph_refuses_unreviewed_cleanup(tmp_path: Path) -> None:
    database = tmp_path / "cycle.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            "CREATE TABLE first(id TEXT PRIMARY KEY, second_id TEXT REFERENCES second(id));"
            "CREATE TABLE second(id TEXT PRIMARY KEY, first_id TEXT REFERENCES first(id));"
        )
        with pytest.raises(ValueError, match="cyclic index dependency graph"):
            reset._deletion_order(connection, {"first", "second"})


def test_preflight_rejects_database_escape_and_registry_identity_fork(tmp_path: Path) -> None:
    database = _fixture(tmp_path)
    base = _target(database)
    escaped = reset.FullStoreTarget(
        database=tmp_path.parent / "outside.db",
        expected_sha256=base.expected_sha256,
        notebook_ids=base.notebook_ids,
        generation_ids=base.generation_ids,
        alias_digests=base.alias_digests,
        snapshot=base.snapshot,
    )
    with pytest.raises(ValueError, match="escapes workspace"):
        reset.dry_run_full_store(workspace=tmp_path, target=escaped)
    inconsistent = reset.FullStoreTarget(
        database=database,
        expected_sha256=base.expected_sha256,
        notebook_ids=base.notebook_ids,
        generation_ids=base.generation_ids,
        alias_digests=base.alias_digests,
        snapshot=base.snapshot,
        registry_aliases=("a",),
    )
    with pytest.raises(ValueError, match="registry allowlist is inconsistent"):
        reset.dry_run_full_store(workspace=tmp_path, target=inconsistent)


def test_preflight_rejects_changed_registry_fingerprint(tmp_path: Path) -> None:
    database = _fixture(tmp_path)
    registry = tmp_path / "scratch" / "registry.json"
    registry.write_text(
        json.dumps({"notebooks": {"a": {"notebook_id": "a", "store": "scratch/legacy"}}}),
        encoding="utf-8",
    )
    base = _target(database)
    target = reset.FullStoreTarget(
        database=database,
        expected_sha256=base.expected_sha256,
        notebook_ids=base.notebook_ids,
        generation_ids=base.generation_ids,
        alias_digests=base.alias_digests,
        snapshot=base.snapshot,
        registry=registry,
        registry_aliases=("a",),
        expected_registry_sha256="0" * 64,
    )
    with pytest.raises(ValueError, match="registry fingerprint changed"):
        reset.dry_run_full_store(workspace=tmp_path, target=target)
