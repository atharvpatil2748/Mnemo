"""Keep the staged evaluator wired to the current production startup API."""

from __future__ import annotations

import ast
import sqlite3
from contextlib import closing
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def test_wp17_evaluator_passes_governed_production_config_to_installer() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "scratch/run_mnemo_v2_production_parity_bge_evaluation.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "install_production_full_multilingual_v2"
    ]
    assert len(calls) == 1
    assert {keyword.arg for keyword in calls[0].keywords} >= {
        "engine",
        "production_config",
        "workspace_root",
        "model_cache",
        "readiness",
    }
    engines = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "KnowledgeEngine"
    ]
    assert len(engines) == 1
    read_only = next(
        keyword.value for keyword in engines[0].keywords if keyword.arg == "certified_read_only"
    )
    assert isinstance(read_only, ast.Name) and read_only.id == "staged"


def test_wp17_evaluator_immutable_database_probe_creates_no_sidecars(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    source_path = root / "scratch/run_mnemo_v2_production_parity_bge_evaluation.py"
    source = source_path.read_text(encoding="utf-8")
    assert source.count("?mode=ro&immutable=1") == 2
    spec = spec_from_file_location("wp17_evaluation_sidecar_regression", source_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    database = tmp_path / "corpus.db"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        for name in ("documents", "document_versions", "sources", "chunks"):
            connection.execute(f"CREATE TABLE {name} (id INTEGER)")
        connection.execute("CREATE TABLE notebooks (notebook_id TEXT)")
        connection.execute("INSERT INTO notebooks VALUES ('governed')")
        connection.commit()
    assert not database.with_name(database.name + "-wal").exists()
    before = database.read_bytes()
    result = module.database_state(database)
    assert result["notebook_id"] == "governed"
    assert database.read_bytes() == before
    assert not database.with_name(database.name + "-wal").exists()
    assert not database.with_name(database.name + "-shm").exists()
