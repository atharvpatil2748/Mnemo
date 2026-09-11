from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from mcp.types import CallToolResult, TextContent
from mnemo_server.evaluation.canonical_json import canonical_json_sha256_v1
from mnemo_server.tools import reindex_evaluation_notebooks as subject


def _digest(value: object) -> str:
    return canonical_json_sha256_v1(value)


def _candidate(root: Path) -> Path:
    target = root / "scratch/evaluation_notebooks/phase8_6"
    target.mkdir(parents=True)
    (target / "files").mkdir()
    database = target / "mnemo.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE proof(value TEXT)")
    connection.close()
    manifest: dict[str, object] = {
        "status": "PUBLISHED",
        "notebook": {
            "id": "notebook-1",
            "store": "scratch/evaluation_notebooks/phase8_6",
        },
        "validation": {"database": {"sha256": hashlib.sha256(database.read_bytes()).hexdigest()}},
    }
    manifest["store_identity"] = _digest(manifest)
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return target


def test_mcp_error_diagnostic_preserves_error_and_redacts_secrets() -> None:
    result = CallToolResult(
        isError=True,
        content=[
            TextContent(
                type="text",
                text='{"error_code":"ADVANCED_RETRIEVAL_MISSING",'
                '"message":"advanced retrieval is not configured",'
                '"api_key":"mnemo-evaluation-notebook-transport-key"}',
            )
        ],
        structuredContent={"credential": "do-not-retain", "safe": "value"},
    )

    diagnostic = subject._mcp_result_diagnostic(result)

    assert diagnostic["mcp_is_error"] is True
    assert diagnostic["mcp_error_code"] == "ADVANCED_RETRIEVAL_MISSING"
    assert diagnostic["mcp_error_message"] == "advanced retrieval is not configured"
    encoded = json.dumps(diagnostic)
    assert "mnemo-evaluation-notebook-transport-key" not in encoded
    assert "do-not-retain" not in encoded
    assert "[REDACTED]" in encoded


def test_structured_mcp_failure_is_persisted_to_event_and_artifact(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "scratch/run"
    run_root.mkdir(parents=True)
    log = subject.RunLog(run_root / "events.jsonl", verbose=False)
    error = subject.TransportValidationFailure(
        "MCP_STDIO_SEARCH_FAILED",
        {
            "failure_code": "MCP_STDIO_SEARCH_FAILED",
            "mcp_is_error": True,
            "mcp_error_message": "advanced retrieval is not configured",
            "notebook_identity": "notebook-1",
            "store_identity": "store-1",
            "requested_k": 5,
        },
    )

    artifact = subject._persist_transport_failure(
        root=tmp_path,
        run_root=run_root,
        alias="phase8_6",
        transport="mcp-stdio",
        error=error,
        log=log,
    )

    saved = json.loads(artifact.read_text())
    event = json.loads((run_root / "events.jsonl").read_text())
    assert saved["mcp_error_message"] == "advanced retrieval is not configured"
    assert event["event"] == "mcp_stdio_search_failure"
    assert event["failure_code"] == "MCP_STDIO_SEARCH_FAILED"


def test_serving_registry_excludes_transport_failed_candidate(tmp_path: Path) -> None:
    target = _candidate(tmp_path)
    manifest = subject._set_notebook_status(
        target / "manifest.json",
        "TRANSPORT_VALIDATION_FAILED",
        transport_validation={"failure_code": "MCP_STDIO_SEARCH_FAILED"},
    )

    registry = subject._write_serving_registry(
        managed_root=target.parent, manifests={"phase8_6": manifest}
    )

    assert target.is_dir()
    assert (target / "mnemo.db").is_file()
    assert registry["notebooks"] == {}
    assert json.loads((target / "checkpoint.json").read_text())["status"] == (
        "TRANSPORT_VALIDATION_FAILED"
    )


def test_transport_retry_failure_is_diagnostic_and_non_destructive(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    target = _candidate(tmp_path)
    run_root = tmp_path / "scratch/evaluation_notebook_reindex/runs/retry"
    run_root.mkdir(parents=True)
    failure = subject.TransportValidationFailure(
        "MCP_STDIO_SEARCH_FAILED",
        {
            "failure_code": "MCP_STDIO_SEARCH_FAILED",
            "transport": "mcp_stdio",
            "notebook_alias": "phase8_6",
            "notebook_identity": "notebook-1",
            "mcp_error_message": "advanced retrieval is not configured",
        },
    )
    monkeypatch.setattr(subject, "_production_state", lambda _root: {"sha256": "safe"})
    monkeypatch.setattr(
        subject,
        "_validate_real_transports",
        lambda **_kwargs: (_ for _ in ()).throw(failure),
    )
    log = subject.RunLog(run_root / "events.jsonl", verbose=False)

    result = subject._validate_retained_notebook(
        root=tmp_path, alias="phase8_6", run_root=run_root, log=log
    )

    assert result == 1
    assert target.is_dir()
    assert json.loads((target / "manifest.json").read_text())["status"] == (
        "TRANSPORT_VALIDATION_FAILED"
    )
    registry = json.loads((target.parent / "registry.json").read_text())
    assert registry["notebooks"] == {}
    checkpoint = json.loads((run_root / "checkpoint.json").read_text())
    assert checkpoint["failure_classification"] == "MCP_STDIO_SEARCH_FAILED"
    assert checkpoint["underlying"]["mcp_error_message"] == ("advanced retrieval is not configured")
    event_text = (run_root / "events.jsonl").read_text()
    assert "retained immutable notebook" in event_text


def test_transport_retry_success_marks_ready_and_registers(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    target = _candidate(tmp_path)
    run_root = tmp_path / "scratch/evaluation_notebook_reindex/runs/retry"
    run_root.mkdir(parents=True)
    monkeypatch.setattr(subject, "_production_state", lambda _root: {"sha256": "safe"})
    monkeypatch.setattr(
        subject,
        "_validate_real_transports",
        lambda **_kwargs: {"status": "PASS", "semantic_identity_parity": "PASS"},
    )
    log = subject.RunLog(run_root / "events.jsonl", verbose=False)

    result = subject._validate_retained_notebook(
        root=tmp_path, alias="phase8_6", run_root=run_root, log=log
    )

    assert result == 0
    assert json.loads((target / "manifest.json").read_text())["status"] == "READY"
    registry = json.loads((target.parent / "registry.json").read_text())
    assert set(registry["notebooks"]) == {"phase8_6"}


def test_retained_manifest_repair_rebinds_unicode_without_database_mutation(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    managed = tmp_path / "scratch/evaluation_notebooks"
    target = managed / "phase8_5"
    target.mkdir(parents=True)
    database = target / "mnemo.db"
    database.write_bytes(b"retained-index-bytes")
    inventory = [
        {
            "relative_path": "Coordinator Application 2026\u201327.pptx",
            "sha256": "source-sha",
            "size_bytes": 42,
        }
    ]
    state = {
        "path": "old-staging/mnemo.db",
        "sha256": hashlib.sha256(database.read_bytes()).hexdigest(),
        "size_bytes": database.stat().st_size,
        "wal_size_bytes": 0,
        "shm_size_bytes": 0,
        "integrity_check": "ok",
        "foreign_key_violations": 0,
        "notebooks": 1,
        "documents": 1,
        "versions": 1,
        "memberships": 1,
        "chunks": 1,
        "fts_rows": 1,
        "image_assets": 0,
        "image_occurrences": 0,
        "processable_image_occurrences": 0,
        "policy_excluded_svg_occurrences": 0,
        "ocr": 0,
        "vision": 0,
        "clip": 0,
        "text_embeddings": 1,
        "duplicate_documents": 0,
        "duplicate_versions": 0,
        "duplicate_chunks": 0,
        "duplicate_memberships": 0,
        "orphan_asset_occurrences": 0,
        "orphan_ocr": 0,
        "orphan_vision": 0,
        "orphan_visual_embeddings": 0,
    }
    manifest: dict[str, object] = {
        "status": "VALIDATION_FAILED",
        "notebook": {
            "id": "notebook-1",
            "store": "scratch/evaluation_notebooks/phase8_5",
        },
        "source_corpus": "goldenDataset/Phase 8.5 Evaluation Corpus",
        "source_inventory": inventory,
        "source_inventory_digest": "legacy-digest",
        "validation": {"database": state},
    }
    manifest["store_identity"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(subject, "_inventory", lambda _source: inventory)
    monkeypatch.setattr(
        subject,
        "_database_state",
        lambda _database: {**state, "path": str(database)},
    )
    monkeypatch.setattr(
        subject,
        "_retained_embedding_audit",
        lambda _database: {"status": "PASS"},
    )
    run_root = tmp_path / "scratch/run"
    run_root.mkdir(parents=True)
    before = hashlib.sha256(database.read_bytes()).hexdigest()

    repaired, evidence = subject._repair_retained_manifest(
        root=tmp_path,
        managed_root=managed,
        alias="phase8_5",
        run_root=run_root,
        log=subject.RunLog(run_root / "events.jsonl", verbose=False),
    )

    unsigned = {key: value for key, value in repaired.items() if key != "store_identity"}
    assert repaired["status"] == "PUBLISHED"
    assert repaired["store_identity"] == canonical_json_sha256_v1(unsigned)
    assert evidence["unicode_present"] is True
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def _state_database(path: Path, *, embeddings: bool = True) -> None:
    """Create the smallest real schema consumed by the read-only state auditor."""
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        PRAGMA foreign_keys=ON;
        CREATE TABLE notebooks(id TEXT PRIMARY KEY);
        CREATE TABLE documents(id TEXT PRIMARY KEY, current_hash TEXT NOT NULL);
        CREATE TABLE document_versions(version_id TEXT PRIMARY KEY);
        CREATE TABLE sources(
            source_id TEXT PRIMARY KEY,
            notebook_id TEXT NOT NULL,
            document_id TEXT NOT NULL
        );
        CREATE TABLE chunks(id TEXT PRIMARY KEY, document_id TEXT, version_id TEXT);
        CREATE VIRTUAL TABLE fts_chunks USING fts5(text);
        CREATE TABLE asset_catalog(asset_id TEXT PRIMARY KEY, mime_type TEXT);
        CREATE TABLE asset_occurrences(
            occurrence_id TEXT PRIMARY KEY,
            asset_id TEXT,
            FOREIGN KEY(asset_id) REFERENCES asset_catalog(asset_id)
        );
        CREATE TABLE ocr_results(occurrence_id TEXT);
        CREATE TABLE vision_results(occurrence_id TEXT);
        CREATE TABLE visual_embeddings(occurrence_id TEXT);
        INSERT INTO notebooks VALUES('n');
        INSERT INTO documents VALUES('d','hash');
        INSERT INTO document_versions VALUES('v');
        INSERT INTO sources VALUES('s','n','d');
        INSERT INTO chunks VALUES('c','d','v');
        INSERT INTO fts_chunks VALUES('content');
        INSERT INTO asset_catalog VALUES('a','image/png');
        INSERT INTO asset_occurrences VALUES('o','a');
        INSERT INTO ocr_results VALUES('o');
        INSERT INTO vision_results VALUES('o');
        INSERT INTO visual_embeddings VALUES('o');
        """
    )
    if embeddings:
        connection.execute("CREATE TABLE evaluation_text_embeddings(chunk_id TEXT)")
        connection.execute("INSERT INTO evaluation_text_embeddings VALUES('c')")
    connection.commit()
    connection.close()


def test_database_state_audits_counts_integrity_and_optional_embeddings(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    _state_database(database)

    state = subject._database_state(database)

    assert state["integrity_check"] == "ok"
    assert state["foreign_key_violations"] == 0
    assert (state["documents"], state["chunks"], state["fts_rows"]) == (1, 1, 1)
    assert state["image_occurrences"] == state["processable_image_occurrences"] == 1
    assert state["policy_excluded_svg_occurrences"] == 0
    assert (state["ocr"], state["vision"], state["clip"], state["text_embeddings"]) == (
        1,
        1,
        1,
        1,
    )
    assert not any(
        state[key]
        for key in (
            "duplicate_documents",
            "duplicate_versions",
            "duplicate_chunks",
            "duplicate_memberships",
            "orphan_asset_occurrences",
            "orphan_ocr",
            "orphan_vision",
            "orphan_visual_embeddings",
        )
    )


def test_inventory_hashes_nested_unicode_files_deterministically(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested/Coordinator 2026\N{EN DASH}27.txt").write_text("हिंदी", encoding="utf-8")
    (tmp_path / "z.txt").write_text("z", encoding="utf-8")

    first = subject._inventory(tmp_path)
    second = subject._inventory(tmp_path)

    assert first == second
    assert [item["relative_path"] for item in first] == [
        "nested/Coordinator 2026\N{EN DASH}27.txt",
        "z.txt",
    ]
    assert all(len(str(item["sha256"])) == 64 for item in first)


@pytest.mark.parametrize(
    ("candidate", "accepted"),
    [
        ("phase8_5", True),
        ("phase8_6", True),
        ("other", False),
        ("phase8_5/child", False),
    ],
)
def test_safe_managed_path_is_exactly_allowlisted(
    tmp_path: Path, candidate: str, accepted: bool
) -> None:
    managed = tmp_path / "managed"
    managed.mkdir()
    target = managed / candidate
    if accepted:
        assert subject._safe_managed_path(target, managed) == target.resolve()
    else:
        with pytest.raises(RuntimeError, match="refusing destructive action"):
            subject._safe_managed_path(target, managed)


def test_safe_staging_path_rejects_escape_and_wrong_run(tmp_path: Path) -> None:
    managed = tmp_path / "managed"
    managed.mkdir()
    valid = managed / ".phase8_6.staging-run-1"
    assert subject._safe_staging_path(valid, managed, "phase8_6") == valid.resolve()
    with pytest.raises(RuntimeError, match="unexpected target"):
        subject._safe_staging_path(managed / ".phase8_5.staging-run-1", managed, "phase8_6")
    with pytest.raises(RuntimeError, match="outside"):
        subject._safe_staging_path(tmp_path / "outside", managed, "phase8_6")


def test_registry_load_status_and_delete_are_fail_closed(tmp_path: Path) -> None:
    managed = tmp_path / "managed"
    target = _candidate(tmp_path)
    managed = target.parent
    manifest = json.loads((target / "manifest.json").read_text())
    ready = subject._set_notebook_status(target / "manifest.json", "READY")
    assert ready["store_identity"] != manifest["store_identity"]
    assert set(subject._load_managed_manifests(managed)) == {"phase8_6"}
    subject._delete_managed(
        target, managed, subject.RunLog(tmp_path / "events.jsonl", verbose=False)
    )
    assert not target.exists()
    # Missing targets are an idempotent governed cleanup, not an error.
    subject._delete_managed(
        target, managed, subject.RunLog(tmp_path / "events-2.jsonl", verbose=False)
    )


def test_failure_checkpoint_preserves_typed_transport_details() -> None:
    error = subject.TransportValidationFailure(
        "MCP_SSE_FAILED",
        {
            "notebook_alias": "phase8_6",
            "notebook_identity": "n",
            "transport": "mcp_sse",
            "password": "secret",
        },
    )
    checkpoint = subject._failure_checkpoint(
        error=error,
        stage="transport-validation",
        publication_state="TRANSPORT_VALIDATION_FAILED",
        cleanup_decision="retain",
        artifact_paths=["failure.json"],
        production={"sha256": "prod"},
    )
    assert checkpoint["failure_classification"] == "MCP_SSE_FAILED"
    assert checkpoint["phase"] == "phase8_6"
    assert checkpoint["transport"] == "mcp_sse"
    assert checkpoint["underlying"]["password"] == "[REDACTED]"


def test_build_one_publishes_only_after_all_validations(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "corpus"
    source.mkdir()
    (source / "one.txt").write_text("evidence")
    managed = tmp_path / "scratch/evaluation_notebooks"
    managed.mkdir(parents=True)
    run_root = tmp_path / "run-1"
    run_root.mkdir()
    (tmp_path / "mnemo.toml").write_text("[mnemo]")
    profile = tmp_path / "config/model_profiles/full_multilingual_v2_profiles.toml"
    profile.parent.mkdir(parents=True)
    profile.write_text("[profiles]")
    calls: list[str] = []

    def ingest(**kwargs: object) -> None:
        calls.append("ingest")
        runtime = Path(str(kwargs["runtime"]))
        (runtime / "mnemo.db").write_bytes(b"database")

    monkeypatch.setattr(subject, "_ingest", ingest)
    monkeypatch.setattr(subject, "_multimodal", lambda **_kwargs: calls.append("multimodal"))
    monkeypatch.setattr(subject, "_embed", lambda **_kwargs: calls.append("embed") or {"count": 1})
    monkeypatch.setattr(
        subject,
        "_validate_store",
        lambda **_kwargs: {"database": {"documents": 1, "chunks": 1}},
    )
    spec = subject.NotebookSpec("phase8_6", "Phase 8.6", source)

    manifest = subject._build_one(
        root=tmp_path,
        managed_root=managed,
        spec=spec,
        run_root=run_root,
        log=subject.RunLog(run_root / "events.jsonl", verbose=False),
    )

    assert calls == ["ingest", "multimodal", "embed"]
    assert manifest["status"] == "PUBLISHED"
    assert manifest["source_inventory"][0]["relative_path"] == "one.txt"
    assert (managed / "phase8_6/manifest.json").is_file()
    assert not (managed / ".phase8_6.staging-run-1").exists()


def test_build_one_retains_failed_checkpoint_for_diagnosis(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "corpus"
    source.mkdir()
    managed = tmp_path / "managed"
    managed.mkdir()
    run_root = tmp_path / "run-2"
    run_root.mkdir()
    spec = subject.NotebookSpec("phase8_5", "Phase 8.5", source)
    monkeypatch.setattr(
        subject, "_ingest", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    with pytest.raises(RuntimeError, match="boom"):
        subject._build_one(
            root=tmp_path,
            managed_root=managed,
            spec=spec,
            run_root=run_root,
            log=subject.RunLog(run_root / "events.jsonl", verbose=False),
        )

    checkpoint = json.loads((managed / ".phase8_5.staging-run-2/checkpoint.json").read_text())
    assert checkpoint["status"] == "FAILED"
    assert checkpoint["error_type"] == "RuntimeError"


def test_main_repair_and_validate_modes_delegate_without_building(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(subject, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        subject,
        "_arguments",
        lambda: SimpleNamespace(
            full=False,
            phase85=True,
            phase86=False,
            validate_only=False,
            repair_retained=True,
            verbose=False,
        ),
    )
    observed: dict[str, object] = {}
    monkeypatch.setattr(
        subject,
        "_repair_retained_notebooks",
        lambda **kwargs: observed.update(kwargs) or 17,
    )
    assert subject.main() == 17
    assert observed["aliases"] == ["phase8_5"]

    monkeypatch.setattr(
        subject,
        "_arguments",
        lambda: SimpleNamespace(
            full=False,
            phase85=False,
            phase86=True,
            validate_only=True,
            repair_retained=False,
            verbose=False,
        ),
    )
    second_root = tmp_path / "second"
    second_root.mkdir()
    monkeypatch.setattr(subject, "_repo_root", lambda: second_root)
    monkeypatch.setattr(
        subject,
        "_validate_retained_notebook",
        lambda **kwargs: observed.update(kwargs) or 23,
    )
    assert subject.main() == 23
    assert observed["alias"] == "phase8_6"


def test_main_pipeline_publishes_validates_and_preserves_protected_state(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path
    managed = root / "scratch/evaluation_notebooks"
    root.joinpath("goldenDataset/Phase 8.5 Evaluation Corpus").mkdir(parents=True)
    root.joinpath(
        "evaluationDataset/Phase 8.6 Format-Diverse Multilingual Evaluation Corpus"
    ).mkdir(parents=True)
    monkeypatch.setattr(subject, "_repo_root", lambda: root)
    monkeypatch.setattr(
        subject,
        "_arguments",
        lambda: SimpleNamespace(
            full=False,
            phase85=True,
            phase86=False,
            validate_only=False,
            repair_retained=False,
            verbose=False,
        ),
    )
    protected = {"artifacts": {"config": {"sha256": "same"}}}
    monkeypatch.setattr(
        subject,
        "_preflight",
        lambda _root, _log: {
            "production": {"sha256": "prod"},
            "protected_contracts": protected,
        },
    )
    monkeypatch.setattr(subject, "_smoke", lambda *_args: {"status": "PASS"})
    monkeypatch.setattr(subject, "_production_state", lambda _root: {"sha256": "prod"})
    monkeypatch.setattr(subject, "_protected_contract_state", lambda _root: protected)

    def build(**kwargs: object) -> dict[str, object]:
        spec = kwargs["spec"]
        target = managed / spec.key  # type: ignore[attr-defined]
        target.mkdir(parents=True)
        (target / "mnemo.db").write_bytes(b"db")
        manifest: dict[str, object] = {
            "status": "PUBLISHED",
            "notebook": {"id": "n", "store": "scratch/evaluation_notebooks/phase8_5"},
            "validation": {
                "database": {
                    "documents": 1,
                    "chunks": 1,
                    "text_embeddings": 1,
                    "image_occurrences": 0,
                    "ocr": 0,
                    "vision": 0,
                    "clip": 0,
                }
            },
        }
        manifest["store_identity"] = _digest(manifest)
        (target / "manifest.json").write_text(json.dumps(manifest))
        return manifest

    monkeypatch.setattr(subject, "_build_one", build)
    selection = SimpleNamespace(
        database=managed / "phase8_5/mnemo.db",
        notebook_id="n",
        store_identity="store",
        manifest=managed / "phase8_5/manifest.json",
    )
    import mnemo_server.evaluation.notebook_registry as registry_module

    monkeypatch.setattr(
        registry_module,
        "resolve_evaluation_notebook_validation_candidate_v1",
        lambda **_kwargs: selection,
    )
    monkeypatch.setattr(
        subject,
        "_validate_real_transports",
        lambda **_kwargs: {"status": "PASS", "semantic_identity_parity": "PASS"},
    )

    assert subject.main() == 0
    result_files = list(root.glob("scratch/evaluation_notebook_reindex/runs/*/result.json"))
    result = json.loads(result_files[0].read_text())
    assert result["status"] == "PRODUCTION_PIPELINE_REINDEX_PASS"
    assert result["production_unchanged"] is True
    assert result["governed_exposure"]["phase8_5"]["status"] == "PASS"


def test_multimodal_skips_empty_and_executes_configured_pipeline(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    log = subject.RunLog(tmp_path / "events.jsonl", verbose=False)
    spec = subject.NotebookSpec("phase8_6", "Phase 8.6", tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setattr(
        subject, "_database_state", lambda _db: {"processable_image_occurrences": 0}
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(
        subject,
        "_run_process",
        lambda command, **_kwargs: calls.append(command),
    )
    subject._multimodal(root=tmp_path, runtime=runtime, spec=spec, log=log)
    assert calls == []
    monkeypatch.setattr(
        subject, "_database_state", lambda _db: {"processable_image_occurrences": 2}
    )
    subject._multimodal(root=tmp_path, runtime=runtime, spec=spec, log=log)
    assert "phase8_5_11_derived_pipeline.py" in calls[0][1]
    assert "--all-assets" in calls[0]
    assert "cuda" in calls[0]


def test_ingest_constructs_governed_command_with_optional_include(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    calls: list[tuple[list[str], str]] = []
    monkeypatch.setattr(
        subject,
        "_run_process",
        lambda command, **kwargs: calls.append((command, kwargs["stage"])),
    )
    spec = subject.NotebookSpec("phase8_5", "Golden", tmp_path / "source")
    subject._ingest(
        root=tmp_path,
        source=spec.source,
        runtime=tmp_path / "runtime",
        spec=spec,
        log=subject.RunLog(tmp_path / "events.jsonl", verbose=False),
        include="manuscript.pdf",
    )
    command, stage = calls[0]
    assert command[-2:] == ["--include", "manuscript.pdf"]
    assert "evaluation-notebook-reindex:phase8_5" in command
    assert stage == "phase8_5.ingestion"


def test_validate_store_enforces_all_coverage_invariants(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / "store.db"
    sqlite3.connect(database).close()
    state = {
        "documents": 1,
        "versions": 1,
        "memberships": 2,
        "chunks": 3,
        "fts_rows": 3,
        "text_embeddings": 3,
        "integrity_check": "ok",
        "foreign_key_violations": 0,
        "duplicate_documents": 0,
        "duplicate_versions": 0,
        "duplicate_chunks": 0,
        "duplicate_memberships": 0,
        "orphan_asset_occurrences": 0,
        "orphan_ocr": 0,
        "orphan_vision": 0,
        "orphan_visual_embeddings": 0,
        "processable_image_occurrences": 2,
        "ocr": 2,
        "vision": 2,
        "clip": 2,
    }
    monkeypatch.setattr(subject, "_database_state", lambda _db: state)
    monkeypatch.setattr(subject, "_retrieval_validation", lambda *_args: {"status": "PASS"})
    inventory = [{"sha256": "same"}, {"sha256": "same"}]
    embedding = {
        "revision": subject.BGE_REVISION,
        "dimensions": subject.BGE_DIMENSIONS,
        "semantic_probe": {},
    }
    result = subject._validate_store(database=database, inventory=inventory, embedding=embedding)
    assert all(result["checks"].values())
    assert result["checks"]["ocr_complete"] is True
    broken = dict(state)
    broken["fts_rows"] = 2
    monkeypatch.setattr(subject, "_database_state", lambda _db: broken)
    with pytest.raises(RuntimeError, match="fts_complete"):
        subject._validate_store(database=database, inventory=inventory, embedding=embedding)


def test_retrieval_validation_executes_fts_rrf_and_dynamic_k(tmp_path: Path) -> None:
    database = tmp_path / "retrieval.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE chunks(id TEXT PRIMARY KEY, text TEXT)")
    connection.execute(
        "CREATE VIRTUAL TABLE fts_chunks USING fts5(text, content='chunks', content_rowid='rowid')"
    )
    for index in range(12):
        connection.execute(
            "INSERT INTO chunks(id,text) VALUES(?,?)",
            (f"c{index:02}", f"semantic evidence token with enough source text number {index}"),
        )
    connection.execute("INSERT INTO fts_chunks(fts_chunks) VALUES('rebuild')")
    connection.commit()
    connection.close()
    semantic = {
        "query": "semantic evidence",
        "top_candidates": [
            {"chunk_id": f"c{index:02}", "cosine": 1.0 - index / 100} for index in range(12)
        ],
    }
    result = subject._retrieval_validation(database, semantic)
    assert result["rrf"] == "PASS"
    assert [item["returned"] for item in result["dynamic_k"]] == [1, 5, 10]
    semantic["top_candidates"][0]["cosine"] = float("nan")
    with pytest.raises(RuntimeError, match="SCORE_INVALID"):
        subject._retrieval_validation(database, semantic)


def test_transport_request_compaction_environment_and_free_port(tmp_path: Path) -> None:
    database = tmp_path / "transport.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE chunks(id TEXT, text TEXT)")
    connection.execute(
        "INSERT INTO chunks VALUES('c','one two three four five six seven eight nine')"
    )
    connection.commit()
    connection.close()
    request = subject._transport_request(database, "notebook", 5)
    assert request["scope"] == {"notebook_id": "notebook"}
    assert request["evidence_budget"] == 5
    compact = subject._compact_transport_payload(
        {
            "items": [{"document_id": "d", "version_id": "v", "chunk_id": "c"}],
            "limits": {"evidence": 1},
            "completeness": "complete",
        }
    )
    assert compact["item_count"] == 1 and compact["chunk_ids"] == ["c"]
    with pytest.raises(RuntimeError, match="ITEMS_INVALID"):
        subject._compact_transport_payload({"items": {}})
    environment = subject._transport_environment(tmp_path)
    assert str(tmp_path / "mnemo-core") in environment["PYTHONPATH"]
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert subject._free_port() > 0


def test_stop_transport_server_terminates_then_kills_on_timeout() -> None:
    events: list[object] = []

    class Process:
        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            events.append("terminate")

        def wait(self, timeout: int) -> None:
            events.append(("wait", timeout))
            if timeout == 20:
                raise subject.subprocess.TimeoutExpired("server", timeout)

        def kill(self) -> None:
            events.append("kill")

    class Output:
        def close(self) -> None:
            events.append("close")

    subject._stop_transport_server(Process(), Output())  # type: ignore[arg-type]
    assert events == ["terminate", ("wait", 20), "kill", ("wait", 10), "close"]


def test_validate_real_transports_proves_dynamic_k_and_semantic_parity(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / "db"
    database.write_bytes(b"db")
    payloads = {
        count: {
            "items": [
                {"document_id": f"d{i}", "version_id": f"v{i}", "chunk_id": f"c{i}"}
                for i in range(count)
            ],
            "limits": {},
            "completeness": "complete",
        }
        for count in (1, 5, 10)
    }

    class Response:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    import httpx

    monkeypatch.setattr(subject, "_free_port", iter((8001, 8002)).__next__)
    monkeypatch.setattr(
        subject, "_start_transport_server", lambda **_kwargs: (SimpleNamespace(), SimpleNamespace())
    )
    monkeypatch.setattr(subject, "_wait_for_health", lambda *_args: None)
    monkeypatch.setattr(subject, "_stop_transport_server", lambda *_args: None)
    monkeypatch.setattr(
        subject,
        "_transport_request",
        lambda _db, notebook, requested: {
            "query": "q",
            "scope": {"notebook_id": notebook},
            "evidence_budget": requested,
        },
    )
    monkeypatch.setattr(
        httpx,
        "post",
        lambda _url, **kwargs: Response(payloads[int(kwargs["json"]["evidence_budget"])]),
    )
    compact5 = subject._compact_transport_payload(payloads[5])

    async def stdio(*_args: object, **_kwargs: object) -> dict[str, object]:
        return compact5

    async def sse(*_args: object, **_kwargs: object) -> dict[str, object]:
        return compact5

    monkeypatch.setattr(subject, "_mcp_stdio_request", stdio)
    monkeypatch.setattr(subject, "_mcp_sse_request", sse)
    run_root = tmp_path / "run"
    run_root.mkdir()
    result = subject._validate_real_transports(
        root=tmp_path,
        alias="phase8_6",
        database=database,
        notebook_id="notebook",
        store_identity="store",
        run_root=run_root,
        log=subject.RunLog(run_root / "events.jsonl", verbose=False),
    )
    assert result["semantic_identity_parity"] == "PASS"
    assert set(result["http"]["dynamic_requested_k"]) == {"1", "5", "10"}
    assert (run_root / "phase8_6-transport-validation.json").is_file()


def _embedding_audit_database(path: Path, *, defect: str | None = None) -> None:
    vector = np.zeros(subject.BGE_DIMENSIONS, dtype=np.float32)
    vector[0] = 1.0
    blob = vector.tobytes()
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE chunks(id TEXT, document_id TEXT, version_id TEXT)")
    connection.execute(
        "CREATE TABLE evaluation_text_embeddings(chunk_id TEXT,document_id TEXT,version_id TEXT,"
        "model_identity TEXT,model_revision TEXT,dimensions INTEGER,vector_hash TEXT,"
        "vector BLOB,normalized INTEGER)"
    )
    connection.execute("INSERT INTO chunks VALUES('c','d','v')")
    values: list[object] = [
        "c",
        "d",
        "v",
        subject.BGE_MODEL,
        subject.BGE_REVISION,
        subject.BGE_DIMENSIONS,
        hashlib.sha256(blob).hexdigest(),
        blob,
        1,
    ]
    index = {"identity": 1, "model": 3, "dimensions": 5, "vector_hash": 6, "numeric": 8}
    if defect == "orphan":
        values[0] = "missing"
    elif defect in index:
        values[index[defect]] = 0 if defect == "numeric" else 1 if defect == "dimensions" else "bad"
    connection.execute("INSERT INTO evaluation_text_embeddings VALUES(?,?,?,?,?,?,?,?,?)", values)
    connection.commit()
    connection.close()


@pytest.mark.parametrize(
    ("defect", "reason"),
    [
        ("orphan", "orphan"),
        ("identity", "identity"),
        ("model", "model"),
        ("dimensions", "dimensions"),
        ("vector_hash", "vector_hash"),
        ("numeric", "numeric"),
    ],
)
def test_retained_embedding_audit_rejects_each_integrity_boundary(
    tmp_path: Path, defect: str, reason: str
) -> None:
    database = tmp_path / f"{defect}.db"
    _embedding_audit_database(database, defect=defect)
    with pytest.raises(RuntimeError, match=reason):
        subject._retained_embedding_audit(database)


def test_retained_embedding_audit_accepts_exact_finite_identity_bound_vector(
    tmp_path: Path,
) -> None:
    database = tmp_path / "valid.db"
    _embedding_audit_database(database)
    result = subject._retained_embedding_audit(database)
    assert result["status"] == "PASS"
    assert result["count"] == result["chunk_count"] == 1
    assert result["vector_hashes_valid"] is True


def test_preflight_enforces_environment_and_returns_bound_state(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    import httpx
    import torch

    monkeypatch.setattr(Path, "exists", lambda _path: True)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "get_device_name", lambda _index: "Test CUDA")
    monkeypatch.setenv("OLLAMA_MODELS", r"D:\Ollama\models")
    monkeypatch.setenv("OLLAMA_NUM_PARALLEL", "4")

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"models": [{"name": subject.VISION_MODEL, "digest": subject.VISION_REVISION}]}

    monkeypatch.setattr(httpx, "get", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(subject, "_production_state", lambda _root: {"sha256": "prod"})
    monkeypatch.setattr(subject, "_protected_contract_state", lambda _root: {"artifacts": {}})
    monkeypatch.setattr(subject, "_inventory", lambda _root: [{"relative_path": "one"}])
    result = subject._preflight(tmp_path, subject.RunLog(tmp_path / "events.jsonl", verbose=False))
    assert result["status"] == "PASS"
    assert result["cuda"]["device"] == "Test CUDA"
    assert result["qwen_vision"]["digest"] == subject.VISION_REVISION


@pytest.mark.parametrize(
    ("defect", "message"),
    [
        ("missing_path", "PREFLIGHT_REQUIRED_PATH_MISSING"),
        ("cuda", "PREFLIGHT_CUDA_UNAVAILABLE"),
        ("models_env", "PREFLIGHT_OLLAMA_MODELS_MISMATCH"),
        ("parallel_env", "PREFLIGHT_OLLAMA_NUM_PARALLEL_MISMATCH"),
        ("ollama", "PREFLIGHT_OLLAMA_UNAVAILABLE"),
        ("vision_missing", "PREFLIGHT_QWEN_VISION_MODEL_MISSING"),
        ("vision_revision", "PREFLIGHT_QWEN_VISION_REVISION_MISMATCH"),
    ],
)
def test_preflight_rejects_each_external_runtime_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str, message: str
) -> None:
    """Preflight reports each missing external prerequisite without starting a build."""
    import httpx
    import torch

    monkeypatch.setattr(Path, "exists", lambda _path: defect != "missing_path")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: defect != "cuda")
    monkeypatch.setenv("OLLAMA_MODELS", "wrong" if defect == "models_env" else r"D:\Ollama\models")
    monkeypatch.setenv("OLLAMA_NUM_PARALLEL", "1" if defect == "parallel_env" else "4")

    class Response:
        def raise_for_status(self) -> None:
            if defect == "ollama":
                raise httpx.HTTPError("offline")

        def json(self) -> dict[str, object]:
            if defect == "vision_missing":
                return {"models": []}
            digest = "wrong" if defect == "vision_revision" else subject.VISION_REVISION
            return {"models": [{"name": subject.VISION_MODEL, "digest": digest}]}

    monkeypatch.setattr(httpx, "get", lambda *_args, **_kwargs: Response())
    with pytest.raises(RuntimeError, match=message):
        subject._preflight(tmp_path, subject.RunLog(tmp_path / "events.jsonl", verbose=False))


def test_smoke_runs_all_stages_and_deletes_only_temporary_store(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "goldenDataset/Phase 8.5 Evaluation Corpus"
    source.mkdir(parents=True)
    (source / "manuscript.pdf").write_bytes(b"source")
    run_root = tmp_path / "run"
    run_root.mkdir()
    calls: list[str] = []

    def ingest(**kwargs: object) -> None:
        calls.append("ingest")
        runtime = Path(str(kwargs["runtime"]))
        runtime.mkdir()
        (runtime / "mnemo.db").write_bytes(b"db")

    monkeypatch.setattr(subject, "_ingest", ingest)
    monkeypatch.setattr(subject, "_multimodal", lambda **_kwargs: calls.append("multimodal"))
    monkeypatch.setattr(subject, "_embed", lambda **_kwargs: calls.append("embed") or {"count": 1})
    monkeypatch.setattr(
        subject, "_inventory", lambda _source: [{"relative_path": "manuscript.pdf"}]
    )
    monkeypatch.setattr(subject, "_validate_store", lambda **_kwargs: {"checks": {"all": True}})
    result = subject._smoke(
        tmp_path, run_root, subject.RunLog(run_root / "events.jsonl", verbose=False)
    )
    assert result["status"] == "PASS"
    assert calls == ["ingest", "multimodal", "embed"]
    assert not (run_root / "smoke").exists()
    assert (source / "manuscript.pdf").read_bytes() == b"source"


def test_repair_run_rebinds_all_aliases_without_data_regeneration(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    managed = tmp_path / "scratch/evaluation_notebooks"
    for alias in ("phase8_5", "phase8_6"):
        path = managed / alias
        path.mkdir(parents=True)
        (path / "mnemo.db").write_bytes(alias.encode())
    run_root = tmp_path / "run"
    run_root.mkdir()
    monkeypatch.setattr(subject, "_production_state", lambda _root: {"sha256": "prod"})

    def repair(**kwargs: object) -> tuple[dict[str, object], dict[str, object]]:
        alias = str(kwargs["alias"])
        return (
            {
                "status": "PUBLISHED",
                "notebook": {"store": alias, "id": alias},
                "store_identity": alias,
            },
            {"status": "PASS", "alias": alias},
        )

    monkeypatch.setattr(subject, "_repair_retained_manifest", repair)
    result = subject._repair_retained_notebooks(
        root=tmp_path,
        aliases=["phase8_5", "phase8_6"],
        run_root=run_root,
        log=subject.RunLog(run_root / "events.jsonl", verbose=False),
    )
    assert result == 0
    evidence = json.loads((run_root / "result.json").read_text())
    assert evidence["databases_unchanged"] is True
    assert not any(evidence["data_regeneration"].values())
    assert evidence["registry"]["notebooks"] == {}


def test_embed_persists_normalized_identity_bound_vectors_without_external_runtime(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / "mnemo.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE chunks(id TEXT PRIMARY KEY, document_id TEXT, version_id TEXT, text TEXT)"
    )
    connection.executemany(
        "INSERT INTO chunks VALUES(?,?,?,?)",
        (
            ("c1", "d1", "v1", "one meaningful semantic passage"),
            ("c2", "d2", "v2", "another meaningful semantic passage"),
        ),
    )
    connection.commit()
    connection.close()

    class FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return True

        @staticmethod
        def get_device_name(_index: int) -> str:
            return "test-cuda"

        @staticmethod
        def reset_peak_memory_stats() -> None:
            return None

        @staticmethod
        def max_memory_allocated() -> int:
            return 12

        @staticmethod
        def max_memory_reserved() -> int:
            return 34

        @staticmethod
        def empty_cache() -> None:
            return None

    class FakeModel:
        max_seq_length = 0

        def __init__(self, *_args: object, **kwargs: object) -> None:
            assert kwargs == {
                "device": "cuda",
                "trust_remote_code": False,
                "local_files_only": True,
            }

        def encode(self, texts, **kwargs):  # type: ignore[no-untyped-def]
            assert kwargs["normalize_embeddings"] is True
            vectors = np.zeros((len(texts), subject.BGE_DIMENSIONS), dtype=np.float32)
            vectors[:, 0] = 1.0
            return vectors

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=FakeCuda()))
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeModel),
    )
    monkeypatch.setattr(Path, "resolve", lambda self, strict=False: self)
    log = subject.RunLog(tmp_path / "events.jsonl", verbose=False)

    result = subject._embed(
        database=database,
        root=tmp_path,
        spec=subject.NotebookSpec("phase", "title", tmp_path),
        log=log,
    )

    assert result["count"] == 2
    assert result["device"] == "cuda"
    assert result["gpu"] == "test-cuda"
    assert result["semantic_probe"]["top_candidates"][0]["cosine"] == pytest.approx(1.0)
    connection = sqlite3.connect(database)
    rows = connection.execute(
        "SELECT chunk_id,dimensions,normalized,length(vector) "
        "FROM evaluation_text_embeddings ORDER BY chunk_id"
    ).fetchall()
    connection.close()
    assert rows == [("c1", 1024, 1, 4096), ("c2", 1024, 1, 4096)]


def test_embed_fails_closed_when_cuda_is_unavailable(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)),
    )
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=object),
    )
    with pytest.raises(RuntimeError, match="BGE_M3_CUDA_UNAVAILABLE"):
        subject._embed(
            database=tmp_path / "absent.db",
            root=tmp_path,
            spec=subject.NotebookSpec("phase", "title", tmp_path),
            log=subject.RunLog(tmp_path / "events.jsonl", verbose=False),
        )


def test_diagnostic_helpers_cover_plain_content_redaction_and_logging(
    tmp_path: Path, capsys
) -> None:  # type: ignore[no-untyped-def]
    assert subject._clock(3661.9) == "01:01:01"
    payload = tmp_path / "large.bin"
    payload.write_bytes(b"a" * (1024 * 1024 + 17))
    assert subject._sha256(payload) == hashlib.sha256(payload.read_bytes()).hexdigest()
    assert subject._json_digest({"b": 2, "a": 1}) == subject._json_digest({"a": 1, "b": 2})
    redacted = subject._redact_diagnostic(
        {
            "Authorization": "Bearer value",
            "nested": ("safe", "mnemo-evaluation-notebook-transport-key"),
            "count": 4,
        }
    )
    assert redacted == {
        "Authorization": "[REDACTED]",
        "nested": ["safe", "[REDACTED]"],
        "count": 4,
    }

    result = SimpleNamespace(
        content=[object(), SimpleNamespace(text="not-json")],
        isError=False,
        structuredContent=None,
        meta={"api-token": "secret"},
    )
    diagnostic = subject._mcp_result_diagnostic(result)
    assert diagnostic["mcp_error_code"] is None
    assert diagnostic["mcp_error_message"] == "not-json"
    assert diagnostic["mcp_content"][0]["value"].startswith("<object object")
    assert diagnostic["mcp_meta"] == {"api-token": "[REDACTED]"}

    log = subject.RunLog(tmp_path / "events.jsonl", verbose=True)
    log.event("stage", "message", value=1)
    log.process_output("child", "native output")
    records = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert [item["stage"] for item in records] == ["stage", "child"]
    assert "stage" in capsys.readouterr().out


def test_transport_helpers_cover_empty_query_process_and_health_paths(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / "empty.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE chunks(id TEXT, text TEXT)")
    connection.commit()
    connection.close()
    with pytest.raises(RuntimeError, match="NO_QUERY_TEXT"):
        subject._transport_request(database, "notebook", 1)

    created: dict[str, object] = {}

    class Popen:
        def __init__(self, command, **kwargs):  # type: ignore[no-untyped-def]
            created.update(command=command, **kwargs)

    monkeypatch.setattr(subject.subprocess, "Popen", Popen)
    run_root = tmp_path / "run"
    run_root.mkdir()
    process, output = subject._start_transport_server(
        root=tmp_path, alias="phase8_6", transport="http", port=8123, run_root=run_root
    )
    assert isinstance(process, Popen)
    assert "--validation-candidate" in created["command"]
    output.close()

    events: list[str] = []
    stopped = SimpleNamespace(poll=lambda: 0)
    subject._stop_transport_server(stopped, SimpleNamespace(close=lambda: events.append("close")))
    assert events == ["close"]

    class Exited:
        returncode = 7

        @staticmethod
        def poll() -> int:
            return 7

    with pytest.raises(RuntimeError, match="TRANSPORT_SERVER_EXITED:7"):
        subject._wait_for_health(Exited(), 8123)  # type: ignore[arg-type]

    import httpx

    response = SimpleNamespace(status_code=200)
    monkeypatch.setattr(httpx, "get", lambda *_args, **_kwargs: response)
    subject._wait_for_health(SimpleNamespace(poll=lambda: None), 8123)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "arguments",
    (
        ["command", "--validate-only"],
        ["command", "--validate-only", "--full"],
        ["command", "--repair-retained", "--validate-only", "--phase85"],
        ["command", "--repair-retained", "--full"],
    ),
)
def test_argument_contract_rejects_ambiguous_governed_operations(
    monkeypatch, arguments: list[str]
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(sys, "argv", arguments)
    with pytest.raises(SystemExit) as raised:
        subject._arguments()
    assert raised.value.code == 2


@pytest.mark.parametrize(
    ("arguments", "expected"),
    (
        (["command", "--full", "--verbose"], (True, False, False, True)),
        (["command", "--phase85"], (False, True, False, False)),
        (["command", "--phase86", "--validate-only"], (False, False, True, False)),
        (["command", "--repair-retained"], (False, False, False, False)),
    ),
)
def test_argument_contract_accepts_each_unambiguous_operation(
    monkeypatch, arguments: list[str], expected: tuple[bool, bool, bool, bool]
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(sys, "argv", arguments)
    parsed = subject._arguments()
    assert (parsed.full, parsed.phase85, parsed.phase86, parsed.verbose) == expected


@pytest.mark.parametrize(
    ("phase85", "phase86", "expected_aliases"),
    (
        (False, False, ["phase8_5", "phase8_6"]),
        (True, False, ["phase8_5"]),
        (False, True, ["phase8_6"]),
    ),
)
def test_main_routes_repair_retained_without_entering_ingestion(
    tmp_path: Path,
    monkeypatch,
    phase85: bool,
    phase86: bool,
    expected_aliases: list[str],
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(subject, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        subject,
        "_arguments",
        lambda: SimpleNamespace(
            repair_retained=True,
            validate_only=False,
            phase85=phase85,
            phase86=phase86,
            full=False,
            verbose=False,
        ),
    )
    observed: dict[str, object] = {}

    def repair(**kwargs: object) -> int:
        observed.update(kwargs)
        return 23

    monkeypatch.setattr(subject, "_repair_retained_notebooks", repair)
    assert subject.main() == 23
    assert observed["aliases"] == expected_aliases


def test_main_routes_validate_only_and_pipeline_failure_fail_closed(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    roots = iter((tmp_path / "validate", tmp_path / "failure"))
    monkeypatch.setattr(subject, "_repo_root", lambda: next(roots))
    modes = iter(
        (
            SimpleNamespace(
                repair_retained=False,
                validate_only=True,
                phase85=False,
                phase86=True,
                full=False,
                verbose=False,
            ),
            SimpleNamespace(
                repair_retained=False,
                validate_only=False,
                phase85=True,
                phase86=False,
                full=False,
                verbose=False,
            ),
        )
    )
    monkeypatch.setattr(subject, "_arguments", lambda: next(modes))
    monkeypatch.setattr(subject, "_validate_retained_notebook", lambda **_kwargs: 17)
    assert subject.main() == 17

    monkeypatch.setattr(
        subject,
        "_preflight",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    assert subject.main() == 1
    checkpoint = next((tmp_path / "failure").glob("scratch/**/checkpoint.json"))
    result = json.loads(checkpoint.read_text())
    assert result["failure_classification"] == "RuntimeError"
    assert result["cleanup_decision"] == "no published notebook required cleanup"


def test_main_completes_one_notebook_pipeline_with_mocked_expensive_stages(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    import mnemo_server.evaluation.notebook_registry as registry_module

    monkeypatch.setattr(subject, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        subject,
        "_arguments",
        lambda: SimpleNamespace(
            repair_retained=False,
            validate_only=False,
            phase85=True,
            phase86=False,
            full=False,
            verbose=False,
        ),
    )
    production = {"sha256": "production-sha"}
    protected = {"artifacts": {"golden": "unchanged"}}
    monkeypatch.setattr(
        subject,
        "_preflight",
        lambda *_args: {"production": production, "protected_contracts": protected},
    )
    monkeypatch.setattr(subject, "_smoke", lambda *_args: {"status": "PASS"})
    monkeypatch.setattr(subject, "_production_state", lambda _root: production)
    monkeypatch.setattr(subject, "_protected_contract_state", lambda _root: protected)
    monkeypatch.setattr(subject, "_delete_managed", lambda *_args: None)
    managed = tmp_path / "scratch/evaluation_notebooks"
    database = managed / "phase8_5/mnemo.db"
    manifest_path = database.parent / "manifest.json"

    validation = {
        "database": {
            "documents": 1,
            "chunks": 2,
            "text_embeddings": 2,
            "image_occurrences": 0,
            "ocr": 0,
            "vision": 0,
            "clip": 0,
        }
    }
    base_manifest = {
        "status": "PUBLISHED",
        "store_identity": "store-id",
        "validation": validation,
        "notebook": {"id": "notebook-id", "store": "phase8_5"},
    }

    def build(**_kwargs: object) -> dict[str, object]:
        database.parent.mkdir(parents=True, exist_ok=True)
        database.write_bytes(b"immutable notebook")
        manifest_path.write_text(json.dumps(base_manifest), encoding="utf-8")
        return dict(base_manifest)

    monkeypatch.setattr(subject, "_build_one", build)
    monkeypatch.setattr(
        registry_module,
        "resolve_evaluation_notebook_validation_candidate_v1",
        lambda **_kwargs: SimpleNamespace(
            database=database,
            notebook_id="notebook-id",
            store_identity="store-id",
            manifest=manifest_path,
        ),
    )
    transport = {"status": "PASS", "semantic_identity_parity": "PASS"}
    monkeypatch.setattr(subject, "_validate_real_transports", lambda **_kwargs: transport)

    def status(_path: Path, value: str, **_kwargs: object) -> dict[str, object]:
        return {**base_manifest, "status": value}

    monkeypatch.setattr(subject, "_set_notebook_status", status)
    monkeypatch.setattr(
        subject,
        "_write_serving_registry",
        lambda **kwargs: {"notebooks": sorted(kwargs["manifests"])},
    )
    assert subject.main() == 0
    result_path = next(tmp_path.glob("scratch/**/result.json"))
    result = json.loads(result_path.read_text())
    assert result["status"] == "PRODUCTION_PIPELINE_REINDEX_PASS"
    assert result["production_unchanged"] is True
    assert result["governed_exposure"]["phase8_5"]["status"] == "PASS"


class _AsyncContext:
    def __init__(
        self,
        value: object = (object(), object()),
        error: BaseException | None = None,
    ) -> None:
        self.value = value
        self.error = error

    async def __aenter__(self) -> object:
        if self.error is not None:
            raise self.error
        return self.value

    async def __aexit__(self, *_args: object) -> None:
        return None


@pytest.mark.anyio
async def test_mcp_stdio_request_covers_success_typed_error_empty_and_exception(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    import mcp
    import mcp.client.stdio as stdio_module

    state: dict[str, object] = {}

    class Session:
        def __init__(self, *_streams: object) -> None:
            pass

        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def initialize(self) -> None:
            state["initialized"] = True

        async def call_tool(self, name: str, request: dict[str, object]):  # type: ignore[no-untyped-def]
            assert name == "search_evidence" and request["query"] == "q"
            return state["result"]

    monkeypatch.setattr(mcp, "ClientSession", Session)
    monkeypatch.setattr(stdio_module, "stdio_client", lambda *_args, **_kwargs: _AsyncContext())
    request = {"query": "q"}
    diagnostic = {"notebook_alias": "phase8_6", "transport": "mcp_stdio"}
    stderr = tmp_path / "stdio.log"
    state["result"] = CallToolResult(
        content=[TextContent(type="text", text=json.dumps({"items": [], "limits": {}}))]
    )
    assert (
        await subject._mcp_stdio_request(
            tmp_path, "phase8_6", request, stderr_path=stderr, diagnostic_context=diagnostic
        )
    )["item_count"] == 0
    assert state["initialized"] is True

    state["result"] = CallToolResult(
        isError=True,
        content=[TextContent(type="text", text='{"code":"DENIED","message":"no"}')],
    )
    with pytest.raises(subject.TransportValidationFailure) as denied:
        await subject._mcp_stdio_request(
            tmp_path, "phase8_6", request, stderr_path=stderr, diagnostic_context=diagnostic
        )
    assert denied.value.diagnostics["mcp_error_code"] == "DENIED"

    state["result"] = CallToolResult(content=[])
    with pytest.raises(RuntimeError, match="EMPTY_RESPONSE"):
        await subject._mcp_stdio_request(
            tmp_path, "phase8_6", request, stderr_path=stderr, diagnostic_context=diagnostic
        )

    monkeypatch.setattr(
        stdio_module,
        "stdio_client",
        lambda *_args, **_kwargs: _AsyncContext(error=ConnectionError("offline token=secret")),
    )
    with pytest.raises(subject.TransportValidationFailure) as failed:
        await subject._mcp_stdio_request(
            tmp_path, "phase8_6", request, stderr_path=stderr, diagnostic_context=diagnostic
        )
    assert failed.value.failure_code == "MCP_STDIO_SEARCH_FAILED"
    assert failed.value.diagnostics["exception_type"] == "ConnectionError"


@pytest.mark.anyio
async def test_mcp_sse_request_covers_success_typed_error_empty_and_exception(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    import mcp
    import mcp.client.sse as sse_module

    state: dict[str, object] = {}

    class Session:
        def __init__(self, *_streams: object) -> None:
            pass

        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def initialize(self) -> None:
            return None

        async def call_tool(self, _name: str, _request: dict[str, object]):  # type: ignore[no-untyped-def]
            return state["result"]

    monkeypatch.setattr(mcp, "ClientSession", Session)
    monkeypatch.setattr(sse_module, "sse_client", lambda *_args, **_kwargs: _AsyncContext())
    request = {"query": "q"}
    diagnostic = {"notebook_alias": "phase8_6", "transport": "mcp_sse"}
    state["result"] = CallToolResult(
        content=[TextContent(type="text", text=json.dumps({"items": [], "limits": {}}))]
    )
    assert (await subject._mcp_sse_request(8123, request, diagnostic_context=diagnostic))[
        "item_count"
    ] == 0
    state["result"] = CallToolResult(
        isError=True,
        content=[TextContent(type="text", text='{"error_code":"DENIED"}')],
    )
    with pytest.raises(subject.TransportValidationFailure) as denied:
        await subject._mcp_sse_request(8123, request, diagnostic_context=diagnostic)
    assert denied.value.diagnostics["mcp_error_code"] == "DENIED"
    state["result"] = CallToolResult(content=[])
    with pytest.raises(RuntimeError, match="EMPTY_RESPONSE"):
        await subject._mcp_sse_request(8123, request, diagnostic_context=diagnostic)
    monkeypatch.setattr(
        sse_module,
        "sse_client",
        lambda *_args, **_kwargs: _AsyncContext(error=ConnectionError("offline")),
    )
    with pytest.raises(subject.TransportValidationFailure) as failed:
        await subject._mcp_sse_request(8123, request, diagnostic_context=diagnostic)
    assert failed.value.failure_code == "MCP_SSE_SEARCH_FAILED"


def test_production_state_rejects_each_identity_integrity_boundary(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    valid = {
        "sha256": subject.PRODUCTION_SHA256,
        "documents": 44,
        "versions": 44,
        "memberships": 44,
        "chunks": 2658,
        "integrity_check": "ok",
        "foreign_key_violations": 0,
    }
    state = dict(valid)
    monkeypatch.setattr(subject, "_database_state", lambda _path: dict(state))
    assert subject._production_state(tmp_path)["governed_identity"] == subject.PRODUCTION_IDENTITY
    for field, value, message in (
        ("sha256", "bad", "IDENTITY"),
        ("documents", 43, "COUNTS"),
        ("integrity_check", "corrupt", "INTEGRITY"),
        ("foreign_key_violations", 1, "INTEGRITY"),
    ):
        state.update(valid)
        state[field] = value
        with pytest.raises(RuntimeError, match=message):
            subject._production_state(tmp_path)


def test_protected_contract_state_is_hash_bound_and_certified(
    tmp_path: Path,
) -> None:
    paths = {
        "production_configuration": tmp_path / "mnemo.toml",
        "production_model_profile": tmp_path
        / "config/model_profiles/full_multilingual_v2_profiles.toml",
        "production_identity_manifest": tmp_path
        / "docs/governance/proposals/phase8_5_full_multilingual_architecture/"
        "V2_DATABASE_ARTIFACT_IDENTITY.json",
        "final_lifecycle": tmp_path / "scratch/mnemo-v2-final-lifecycle.json",
        "final_active_state": tmp_path / "scratch/mnemo-v2-final-active-state.json",
        "durable_reranker_state": tmp_path
        / "scratch/phase8_5_full_multilingual_v2/operational/reranker_activation.json",
    }
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    paths["final_lifecycle"].write_text(
        json.dumps({"lifecycle": {"evaluated": True, "verified": True, "certified": True}}),
        encoding="utf-8",
    )
    active = {"v2_exposed": True, "bge_active": True, "reranker_mode": "BGE_V2_M3"}
    paths["final_active_state"].write_text(json.dumps(active), encoding="utf-8")
    result = subject._protected_contract_state(tmp_path)
    assert set(result["artifacts"]) == set(paths)

    paths["final_lifecycle"].write_text(
        json.dumps({"lifecycle": {"certified": False}}), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="LIFECYCLE"):
        subject._protected_contract_state(tmp_path)
    paths["final_lifecycle"].write_text(
        json.dumps({"lifecycle": {"certified": True}}), encoding="utf-8"
    )
    paths["final_active_state"].write_text(
        json.dumps({**active, "bge_active": False}), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="RERANKER"):
        subject._protected_contract_state(tmp_path)
    paths["production_configuration"].unlink()
    with pytest.raises(RuntimeError, match="ARTIFACT_MISSING"):
        subject._protected_contract_state(tmp_path)


def test_run_process_streams_output_and_propagates_exit_status(
    tmp_path: Path, monkeypatch, capsys
) -> None:  # type: ignore[no-untyped-def]
    class Process:
        def __init__(self, code: int) -> None:
            self.stdout = iter(("first line\n", "\n", "second line\n"))
            self.code = code

        def wait(self) -> int:
            return self.code

    state = {"code": 0}
    monkeypatch.setattr(
        subject.subprocess,
        "Popen",
        lambda *_args, **_kwargs: Process(state["code"]),
    )
    log = subject.RunLog(tmp_path / "events.jsonl", verbose=False)
    subject._run_process(["safe", "command"], root=tmp_path, log=log, stage="child")
    assert "first line" in capsys.readouterr().out
    state["code"] = 9
    with pytest.raises(RuntimeError, match="exit code 9"):
        subject._run_process(["safe", "command"], root=tmp_path, log=log, stage="child")


def test_safe_managed_and_staging_path_validation(tmp_path: Path) -> None:
    managed_root = tmp_path / "managed"
    managed_root.mkdir()

    outside = tmp_path / "outside"
    with pytest.raises(RuntimeError, match="refusing destructive action outside"):
        subject._safe_managed_path(outside, managed_root)

    nested = managed_root / "phase8_5" / "sub"
    with pytest.raises(RuntimeError, match="refusing destructive action for unmanaged target"):
        subject._safe_managed_path(nested, managed_root)

    unmanaged = managed_root / "other"
    with pytest.raises(RuntimeError, match="refusing destructive action for unmanaged target"):
        subject._safe_managed_path(unmanaged, managed_root)

    p85 = managed_root / "phase8_5"
    assert subject._safe_managed_path(p85, managed_root) == p85.resolve()
    p86 = managed_root / "phase8_6"
    assert subject._safe_managed_path(p86, managed_root) == p86.resolve()

    with pytest.raises(RuntimeError, match="refusing staging cleanup outside"):
        subject._safe_staging_path(outside, managed_root, "phase8_5")
    with pytest.raises(RuntimeError, match="refusing staging cleanup for unexpected target"):
        subject._safe_staging_path(managed_root / "phase8_5" / "sub", managed_root, "phase8_5")
    with pytest.raises(RuntimeError, match="refusing staging cleanup for unexpected target"):
        subject._safe_staging_path(managed_root / ".other.staging-run-1", managed_root, "phase8_5")
    valid_staging = managed_root / ".phase8_5.staging-run-1"
    assert (
        subject._safe_staging_path(valid_staging, managed_root, "phase8_5")
        == valid_staging.resolve()
    )

    log = subject.RunLog(tmp_path / "events.jsonl", verbose=False)
    subject._delete_managed(p85, managed_root, log)
    p85.mkdir(parents=True)
    (p85 / "file.txt").write_text("hello", encoding="utf-8")
    assert p85.exists()
    subject._delete_managed(p85, managed_root, log)
    assert not p85.exists()


def test_set_notebook_status_and_serving_registry(tmp_path: Path) -> None:
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps(["not", "dict"]), encoding="utf-8")
    with pytest.raises(RuntimeError, match="PERSISTED_MANIFEST_INVALID"):
        subject._set_notebook_status(manifest_file, "READY")

    valid_manifest = {
        "status": "BUILDING",
        "notebook": {"id": "nb1", "store": "store1"},
    }
    manifest_file.write_text(json.dumps(valid_manifest), encoding="utf-8")
    updated = subject._set_notebook_status(
        manifest_file,
        "READY",
        transport_validation={"safe": "val", "token": "mnemo-evaluation-notebook-transport-key"},
    )
    assert updated["status"] == "READY"
    assert "store_identity" in updated
    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["status"] == "READY"
    assert checkpoint["transport_validation"]["token"] == "[REDACTED]"

    managed_root = tmp_path / "managed_nb"
    managed_root.mkdir()
    assert subject._load_managed_manifests(managed_root) == {}
    p85_dir = managed_root / "phase8_5"
    p85_dir.mkdir()
    (p85_dir / "manifest.json").write_text(json.dumps(updated), encoding="utf-8")
    loaded = subject._load_managed_manifests(managed_root)
    assert "phase8_5" in loaded
    assert loaded["phase8_5"]["status"] == "READY"

    manifests = {
        "phase8_5": updated,
        "phase8_6": {
            "status": "FAILED",
            "notebook": {"id": "nb2", "store": "s2"},
            "store_identity": "id2",
        },
    }
    reg = subject._write_serving_registry(managed_root=managed_root, manifests=manifests)
    assert "phase8_5" in reg["notebooks"]
    assert "phase8_6" not in reg["notebooks"]
    assert reg["notebooks"]["phase8_5"]["notebook_id"] == "nb1"
    assert (managed_root / "registry.json").exists()


def test_retained_embedding_audit_comprehensive(tmp_path: Path) -> None:
    db_path = tmp_path / "audit_test.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE chunks("
        "id TEXT PRIMARY KEY, document_id TEXT NOT NULL, "
        "version_id TEXT NOT NULL, text TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE evaluation_text_embeddings("
        "chunk_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, version_id TEXT NOT NULL, "
        "model_identity TEXT NOT NULL, model_revision TEXT NOT NULL, dimensions INTEGER NOT NULL, "
        "vector_hash TEXT NOT NULL, vector BLOB NOT NULL, normalized INTEGER NOT NULL)"
    )
    c1_id, doc_id, ver_id = "chunk-1", "doc-1", "ver-1"
    c2_id = "chunk-2"
    conn.execute(
        "INSERT INTO chunks VALUES(?, ?, ?, ?)", (c1_id, doc_id, ver_id, "Some chunk text")
    )
    conn.execute(
        "INSERT INTO chunks VALUES(?, ?, ?, ?)", (c2_id, doc_id, ver_id, "Another chunk text")
    )

    vec = np.zeros(subject.BGE_DIMENSIONS, dtype=np.float32)
    vec[0] = 1.0
    vec_blob = vec.tobytes(order="C")
    vec_hash = hashlib.sha256(vec_blob).hexdigest()

    conn.execute(
        "INSERT INTO evaluation_text_embeddings VALUES(?, ?, ?, ?, ?, ?, ?, ?, 1)",
        (
            c1_id,
            doc_id,
            ver_id,
            subject.BGE_MODEL,
            subject.BGE_REVISION,
            subject.BGE_DIMENSIONS,
            vec_hash,
            vec_blob,
        ),
    )
    conn.execute(
        "INSERT INTO evaluation_text_embeddings VALUES(?, ?, ?, ?, ?, ?, ?, ?, 1)",
        (
            c2_id,
            doc_id,
            ver_id,
            subject.BGE_MODEL,
            subject.BGE_REVISION,
            subject.BGE_DIMENSIONS,
            vec_hash,
            vec_blob,
        ),
    )
    conn.commit()
    conn.close()

    res = subject._retained_embedding_audit(db_path)
    assert res["status"] == "PASS"
    assert res["count"] == 2

    # Failure 1: orphan embedding
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM chunks WHERE id = ?", (c2_id,))
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="orphan:"):
        subject._retained_embedding_audit(db_path)

    # Restore chunk 2
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO chunks VALUES(?, ?, ?, ?)", (c2_id, doc_id, ver_id, "Another chunk text")
    )
    conn.commit()
    conn.close()

    # Failure 2: identity mismatch
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE evaluation_text_embeddings SET document_id = 'other' WHERE chunk_id = ?", (c1_id,)
    )
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="identity:"):
        subject._retained_embedding_audit(db_path)

    # Restore document_id
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE evaluation_text_embeddings SET document_id = ? WHERE chunk_id = ?", (doc_id, c1_id)
    )
    conn.commit()
    conn.close()

    # Failure 3: model mismatch
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE evaluation_text_embeddings SET model_identity = 'wrong' WHERE chunk_id = ?",
        (c1_id,),
    )
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="model:"):
        subject._retained_embedding_audit(db_path)

    # Restore model
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE evaluation_text_embeddings SET model_identity = ? WHERE chunk_id = ?",
        (subject.BGE_MODEL, c1_id),
    )
    conn.commit()
    conn.close()

    # Failure 4: dimensions mismatch
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE evaluation_text_embeddings SET dimensions = 512 WHERE chunk_id = ?", (c1_id,)
    )
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="dimensions:"):
        subject._retained_embedding_audit(db_path)

    # Restore dimensions
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE evaluation_text_embeddings SET dimensions = ? WHERE chunk_id = ?",
        (subject.BGE_DIMENSIONS, c1_id),
    )
    conn.commit()
    conn.close()

    # Failure 5: vector_hash mismatch
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE evaluation_text_embeddings SET vector_hash = 'invalid' WHERE chunk_id = ?", (c1_id,)
    )
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="vector_hash:"):
        subject._retained_embedding_audit(db_path)

    # Restore vector_hash
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE evaluation_text_embeddings SET vector_hash = ? WHERE chunk_id = ?",
        (vec_hash, c1_id),
    )
    conn.commit()
    conn.close()

    # Failure 6: numeric invalid
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE evaluation_text_embeddings SET normalized = 0 WHERE chunk_id = ?", (c1_id,)
    )
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="numeric:"):
        subject._retained_embedding_audit(db_path)

    # Restore normalized
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE evaluation_text_embeddings SET normalized = 1 WHERE chunk_id = ?", (c1_id,)
    )
    conn.commit()
    conn.close()

    # Failure 7: count mismatch
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO chunks VALUES('chunk-3', ?, ?, 'text 3')", (doc_id, ver_id))
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="coverage:2/3"):
        subject._retained_embedding_audit(db_path)


def test_retrieval_validation_comprehensive(tmp_path: Path) -> None:
    db_path = tmp_path / "retrieval_test.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE chunks(id TEXT PRIMARY KEY, text TEXT NOT NULL)")
    conn.execute(
        "CREATE VIRTUAL TABLE fts_chunks USING fts5(text, content=chunks, content_rowid=rowid)"
    )
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="RETRIEVAL_VALIDATION_NO_TEXT"):
        subject._retrieval_validation(db_path, {"top_candidates": []})

    conn = sqlite3.connect(db_path)
    long_single = " ".join(["a"] * 50)
    conn.execute("INSERT INTO chunks(rowid, id, text) VALUES(1, 'c1', ?)", (long_single,))
    conn.execute("INSERT INTO fts_chunks(rowid, text) VALUES(1, ?)", (long_single,))
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="RETRIEVAL_VALIDATION_NO_TOKEN"):
        subject._retrieval_validation(db_path, {"top_candidates": []})

    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM chunks")
    conn.execute("DELETE FROM fts_chunks")
    for i in range(1, 15):
        text = (
            f"word{i} unique keyword query testing phrase content "
            f"exceeding forty characters in length {i}"
        )
        conn.execute(
            "INSERT INTO chunks(rowid, id, text) VALUES(?, ?, ?)",
            (i, f"chunk-{i}", text),
        )
        conn.execute("INSERT INTO fts_chunks(rowid, text) VALUES(?, ?)", (i, text))
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="RETRIEVAL_VALIDATION_EMPTY_SOURCE"):
        subject._retrieval_validation(db_path, {"top_candidates": []})

    nan_candidates = [{"chunk_id": f"chunk-{i}", "cosine": float("nan")} for i in range(1, 11)]
    with pytest.raises(RuntimeError, match="SEMANTIC_RETRIEVAL_SCORE_INVALID"):
        subject._retrieval_validation(db_path, {"top_candidates": nan_candidates})

    db_short = tmp_path / "short.db"
    c_short = sqlite3.connect(db_short)
    c_short.execute("CREATE TABLE chunks(id TEXT PRIMARY KEY, text TEXT NOT NULL)")
    c_short.execute(
        "CREATE VIRTUAL TABLE fts_chunks USING fts5(text, content=chunks, content_rowid=rowid)"
    )
    long_msg = "long test sentence exceeding forty characters for validation"
    c_short.execute(
        "INSERT INTO chunks(rowid, id, text) VALUES(1, 'c1', ?)",
        (long_msg,),
    )
    c_short.execute(
        "INSERT INTO fts_chunks(rowid, text) VALUES(1, ?)",
        (long_msg,),
    )
    c_short.commit()
    c_short.close()
    with pytest.raises(RuntimeError, match="DYNAMIC_REQUESTED_K_REGRESSION"):
        subject._retrieval_validation(
            db_short, {"top_candidates": [{"chunk_id": "c1", "cosine": 0.9}]}
        )

    valid_candidates = [{"chunk_id": f"chunk-{i}", "cosine": 0.9 - i * 0.01} for i in range(1, 13)]
    res = subject._retrieval_validation(
        db_path, {"query": "probe query", "top_candidates": valid_candidates}
    )
    assert res["status"] == "PASS"
    assert res["semantic_candidates"] == 12
    assert res["semantic_query"] == "probe query"
    assert res["dynamic_k"] == [
        {"requested_k": 1, "returned": 1},
        {"requested_k": 5, "returned": 5},
        {"requested_k": 10, "returned": 10},
    ]


def test_embed_bge_m3_validation_and_failure_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = subject.RunLog(tmp_path / "events.jsonl", verbose=False)
    spec = subject.NotebookSpec(key="phase8_5", title="Phase 8.5", source=tmp_path)
    db_path = tmp_path / "embed_test.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE chunks(id TEXT PRIMARY KEY, document_id TEXT, version_id TEXT, text TEXT)"
    )
    conn.execute("INSERT INTO chunks VALUES('c1', 'd1', 'v1', 'sample text for embedding')")
    conn.commit()
    conn.close()

    # 1. CUDA unavailable
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match="BGE_M3_CUDA_UNAVAILABLE"):
        subject._embed(database=db_path, root=tmp_path, spec=spec, log=log)

    # 2. CUDA available, mock snapshot path and model
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "get_device_name", lambda _dev: "NVIDIA RTX Test")
    monkeypatch.setattr(torch.cuda, "reset_peak_memory_stats", lambda: None)
    monkeypatch.setattr(torch.cuda, "max_memory_allocated", lambda: 1024 * 1024)

    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    orig_resolve = Path.resolve

    def mock_resolve(self: Path, *args: object, **kwargs: object) -> Path:
        if "phase8.5.11-models" in str(self):
            return snapshot_dir
        return orig_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", mock_resolve)

    state = {"mode": "dim_mismatch"}

    class MockSentenceTransformer:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.max_seq_length = 0

        def encode(self, texts: list[str], **kwargs: object) -> np.ndarray:
            if state["mode"] == "dim_mismatch":
                return np.zeros((len(texts), 512), dtype=np.float32)
            if state["mode"] == "zero_vector":
                return np.zeros((len(texts), subject.BGE_DIMENSIONS), dtype=np.float32)
            if state["mode"] == "not_normalized":
                vec = np.zeros((len(texts), subject.BGE_DIMENSIONS), dtype=np.float32)
                vec[:, 0] = 2.0
                return vec
            vec = np.zeros((len(texts), subject.BGE_DIMENSIONS), dtype=np.float32)
            vec[:, 0] = 1.0
            return vec

    import sentence_transformers

    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", MockSentenceTransformer)

    state["mode"] = "dim_mismatch"
    with pytest.raises(RuntimeError, match="BGE_M3_DIMENSION_MISMATCH"):
        subject._embed(database=db_path, root=tmp_path, spec=spec, log=log)

    state["mode"] = "zero_vector"
    with pytest.raises(RuntimeError, match="BGE_M3_VECTOR_INVALID"):
        subject._embed(database=db_path, root=tmp_path, spec=spec, log=log)

    state["mode"] = "not_normalized"
    with pytest.raises(RuntimeError, match="BGE_M3_VECTOR_NOT_NORMALIZED"):
        subject._embed(database=db_path, root=tmp_path, spec=spec, log=log)

    state["mode"] = "valid"
    result = subject._embed(database=db_path, root=tmp_path, spec=spec, log=log)
    assert result["model"] == subject.BGE_MODEL
    assert result["dimensions"] == subject.BGE_DIMENSIONS
    assert result["device"] == "cuda"
