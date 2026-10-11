"""Disposable failure-path checks for rebuild diagnostics and child execution."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pytest
from mnemo_server.tools.isolated_rebuild import (
    _run_logged_command,
    assess_canary_coverage,
    verify_sources,
)


def _coverage_database(tmp_path: Path) -> Path:
    database = tmp_path / "canary.db"
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.executescript(
            """
            CREATE TABLE asset_catalog(asset_id TEXT, mime_type TEXT);
            CREATE TABLE asset_occurrences(occurrence_id TEXT, asset_id TEXT);
            CREATE TABLE ocr_results(occurrence_id TEXT);
            CREATE TABLE vision_results(occurrence_id TEXT);
            CREATE TABLE visual_embeddings(occurrence_id TEXT);
            CREATE TABLE ocr_projection_rows(occurrence_id TEXT);
            CREATE TABLE vision_text_projection_rows(occurrence_id TEXT);
            CREATE TABLE visual_vector_projection_rows(occurrence_id TEXT);
            CREATE TABLE chunks(chunk_id TEXT);
            CREATE TABLE multilingual_embeddings_v2(embedding_id TEXT);
            CREATE TABLE index_generations(generation_id TEXT, capability TEXT, state TEXT);
            CREATE TABLE active_index_generations(generation_id TEXT);
            INSERT INTO asset_catalog VALUES('raster', 'image/png');
            INSERT INTO asset_catalog VALUES('vector', 'image/svg+xml');
            INSERT INTO asset_occurrences VALUES('raster-occurrence', 'raster');
            INSERT INTO asset_occurrences VALUES('vector-occurrence', 'vector');
            INSERT INTO chunks VALUES('chunk');
            """
        )
    return database


def test_canary_coverage_reports_each_missing_projection_without_activation(tmp_path: Path) -> None:
    database = _coverage_database(tmp_path)
    report = assess_canary_coverage(database)
    assert report["expected_raster_occurrences"] == 1
    assert all(ids == ["raster-occurrence"] for ids in report["missing_occurrences"].values())
    assert "canonical_multilingual_embeddings" in report["blockers"]
    assert "ocr_vision_multilingual_embeddings" in report["blockers"]
    assert "governed_generations_absent" in report["blockers"]
    assert report["eligible_for_activation"] is False

    with closing(sqlite3.connect(database)) as connection, connection:
        for table in (
            "ocr_results",
            "vision_results",
            "visual_embeddings",
            "ocr_projection_rows",
            "vision_text_projection_rows",
            "visual_vector_projection_rows",
        ):
            connection.execute(f"INSERT INTO {table} VALUES('raster-occurrence')")
        for value in ("one", "two"):
            connection.execute("INSERT INTO multilingual_embeddings_v2 VALUES(?)", (value,))
        connection.execute("INSERT INTO index_generations VALUES('gen', 'language', 'building')")
    report = assess_canary_coverage(database)
    assert report["missing_occurrences"] == {name: [] for name in report["present_occurrences"]}
    assert report["generations"] == [
        {"capability": "language", "state": "building", "active": False}
    ]
    assert "generation_not_ready" in report["blockers"]
    assert report["eligible_for_activation"] is False

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("UPDATE index_generations SET state='ready'")
        connection.execute("INSERT INTO active_index_generations VALUES('gen')")
    report = assess_canary_coverage(database)
    assert report["structural_coverage_complete"] is True
    assert report["generations"][0]["active"] is True
    assert report["blockers"] == ["governed_activation_coordinator_not_integrated"]
    assert report["eligible_for_activation"] is False


@pytest.mark.parametrize("stage", ["ordinary", "paddleocr_inference"])
def test_logged_child_preserves_output_and_stage_scoped_environment(
    tmp_path: Path, stage: str
) -> None:
    result = _run_logged_command(
        [
            sys.executable,
            "-c",
            "import os; print(os.environ.get('MNEMO_REBUILD_LIVE_PROGRESS', 'unset'))",
        ],
        workspace=tmp_path,
        runtime=tmp_path,
        stage=stage,
        timeout_seconds=10,
        environment={},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ("1" if stage == "paddleocr_inference" else "unset")
    assert result.stdout.strip() in (tmp_path / "logs" / f"{stage}.log").read_text()


def test_logged_child_failure_and_timeout_are_not_reported_as_success(tmp_path: Path) -> None:
    failed = _run_logged_command(
        [sys.executable, "-c", "import sys; print('failure'); sys.exit(7)"],
        workspace=tmp_path,
        runtime=tmp_path,
        stage="failure",
        timeout_seconds=10,
        environment={},
    )
    assert failed.returncode == 7
    assert "failure" in failed.stdout
    with pytest.raises(RuntimeError, match="timed out"):
        _run_logged_command(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            workspace=tmp_path,
            runtime=tmp_path,
            stage="timeout",
            timeout_seconds=1,
            environment={},
        )
    assert "timeout=True" in (tmp_path / "logs" / "timeout.log").read_text()


def test_source_authority_refuses_missing_or_conflicting_selection(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "original.txt").write_bytes(b"original")
    with pytest.raises(ValueError, match="exactly one"):
        verify_sources(corpus=corpus, includes=("original.txt",))
    with pytest.raises(ValueError, match="exactly one"):
        verify_sources(
            corpus=corpus,
            includes=("original.txt",),
            source_database=tmp_path,
            source_manifest=tmp_path,
        )
    with pytest.raises(ValueError, match="nonempty"):
        verify_sources(corpus=corpus, includes=(), source_database=tmp_path)
