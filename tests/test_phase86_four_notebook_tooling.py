"""Preparation-only safety tests; no notebook creation or ingestion."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest

from scripts import audit_phase86_four_notebooks as auditor
from scripts import evaluate_module_894_multimodal as multimodal_evaluator
from scripts import evaluate_phase86_four_notebooks as evaluator
from scripts import phase86_identity_qrels as identity_qrels
from scripts import run_phase86_four_notebooks as runner


def test_single_notebook_evaluator_flag_preserves_default_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[bool, bool, bool]] = []

    async def fake_evaluate(
        _qrels: Path,
        *,
        per_notebook_readers: bool = False,
        single_notebook_only: bool = False,
        compact_vector_sidecar: bool = False,
    ) -> dict[str, int]:
        calls.append((per_notebook_readers, single_notebook_only, compact_vector_sidecar))
        return {"case_count": 45}

    monkeypatch.setattr(evaluator, "evaluate", fake_evaluate)
    monkeypatch.setattr(
        sys,
        "argv",
        ["evaluate_phase86_four_notebooks.py", "run", "--qrels", str(tmp_path / "qrels.json")],
    )
    assert evaluator.main() == 0
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_phase86_four_notebooks.py",
            "run",
            "--qrels",
            str(tmp_path / "qrels.json"),
            "--single-notebook-only",
        ],
    )
    assert evaluator.main() == 0
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_phase86_four_notebooks.py",
            "run",
            "--qrels",
            str(tmp_path / "qrels.json"),
            "--compact-vector-sidecar",
        ],
    )
    assert evaluator.main() == 0
    assert calls == [(True, False, False), (True, True, False), (True, False, True)]
    assert capsys.readouterr().out.count('"cases": 45') == 3


def test_partial_evaluator_status_is_not_reported_as_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def partial_evaluate(*_: object, **__: object) -> dict[str, object]:
        return {"status": "PARTIAL", "case_count": 90}

    monkeypatch.setattr(evaluator, "evaluate", partial_evaluate)
    monkeypatch.setattr(
        sys,
        "argv",
        ["evaluate_phase86_four_notebooks.py", "run", "--qrels", str(tmp_path / "qrels.json")],
    )
    assert evaluator.main() == 2
    assert json.loads(capsys.readouterr().out) == {"status": "PARTIAL", "cases": 90}


def test_evaluator_case_subset_is_ordered_and_does_not_mutate_bound_cases() -> None:
    cases = [
        {"case_id": "Q01", "targets": [{"evidence_id": "a"}]},
        {"case_id": "Q02", "targets": [{"evidence_id": "b"}]},
        {"case_id": "Q03", "targets": [{"evidence_id": "c"}]},
    ]
    selected = evaluator._select_evaluation_cases(cases, ("Q03", "Q01"))
    assert [case["case_id"] for case in selected] == ["Q01", "Q03"]
    assert [case["case_id"] for case in cases] == ["Q01", "Q02", "Q03"]
    assert evaluator._select_evaluation_cases(cases, None) == cases


@pytest.mark.parametrize(
    ("case_ids", "message"),
    [
        ((), "non-empty"),
        (("Q01", "Q01"), "unique"),
        (("UNKNOWN",), "unknown IDs"),
    ],
)
def test_evaluator_case_subset_rejects_empty_duplicate_or_unbound_ids(
    case_ids: tuple[str, ...], message: str
) -> None:
    cases = [{"case_id": "Q01"}]
    with pytest.raises(ValueError, match=message):
        evaluator._select_evaluation_cases(cases, case_ids)


def test_evaluator_cli_can_run_bound_case_subset_in_one_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[dict[str, object]] = []

    async def fake_evaluate(_qrels: Path, **kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"status": "PASS", "case_count": 8}

    monkeypatch.setattr(evaluator, "evaluate", fake_evaluate)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_phase86_four_notebooks.py",
            "run",
            "--qrels",
            str(tmp_path / "qrels.json"),
            "--case-ids",
            "HI02-HI",
            "HI08-HI",
            "--retrieval-modes",
            "canonical_sparse_plus_bge_m3_full_v2",
        ],
    )
    assert evaluator.main() == 0
    assert calls == [
        {
            "per_notebook_readers": True,
            "single_notebook_only": False,
            "compact_vector_sidecar": False,
            "case_ids": ("HI02-HI", "HI08-HI"),
            "retrieval_modes": ("canonical_sparse_plus_bge_m3_full_v2",),
        }
    ]
    assert json.loads(capsys.readouterr().out) == {"status": "PASS", "cases": 8}


def test_timed_out_qrel_has_explicit_failed_record_without_metrics() -> None:
    case = {"case_id": "case-timeout"}
    notebooks = (UUID(int=11), UUID(int=12))
    result = evaluator._timed_out_case_result(case, notebooks)
    assert result["status"] == "TIMED_OUT"
    assert result["metrics"] is None
    assert result["ranked"] == []
    assert result["selected_notebooks"] == [str(value) for value in notebooks]


def test_failed_qrel_has_explicit_safe_record_without_metrics_or_error_text() -> None:
    case = {"case_id": "case-invalid-evidence"}
    notebooks = (UUID(int=21),)
    error = ValueError("sensitive source text must not be persisted")
    result = evaluator._failed_case_result(case, notebooks, error)
    assert result["status"] == "FAILED"
    assert result["exception_class"] == "ValueError"
    assert result["metrics"] is None
    assert result["ranked"] == []
    assert result["selected_notebooks"] == [str(value) for value in notebooks]
    assert "sensitive source text" not in json.dumps(result)


def test_compact_vector_evaluator_is_exact_authorized_and_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import benchmark_module_894_compact_vectors as compact_vectors

    plan, _ = runner.preflight()
    _run_id, runtime, _logs = runner.run_paths(plan)
    progress = evaluator.EvaluationProgress(tmp_path, "compact-sidecar-regression")
    store = evaluator.CompactVectorReadOnlyEvaluationStore(runtime / "mnemo.db", progress)
    before = compact_vectors.sha256(evaluator.COMPACT_VECTOR_DB)
    assert before == evaluator.COMPACT_VECTOR_DB_SHA256
    hash_calls: list[Path] = []
    original_sha256 = compact_vectors.sha256

    def count_sha256(path: Path) -> str:
        hash_calls.append(path)
        return original_sha256(path)

    monkeypatch.setattr(compact_vectors, "sha256", count_sha256)

    async def exercise() -> None:
        await store.open()
        try:
            assert store._compact_db is not None
            setting = await (await store._compact_db.execute("PRAGMA query_only")).fetchone()
            assert setting == (1,)
            async with store._compact_db.execute(
                "SELECT metadata_payload,vector_blob,record_hash "
                "FROM compact_multilingual_embeddings_v1 ORDER BY embedding_id LIMIT 1"
            ) as cursor:
                row = await cursor.fetchone()
            assert row is not None
            embedding = compact_vectors.restore(
                row[0], row[1], row[2], encoding=evaluator.COMPACT_VECTOR_ENCODING
            )
            values = await store.list_authorized_multilingual_embeddings_v3(
                notebook_id=embedding.source.notebook_id,
                generation_id=embedding.profile.generation_id,
                vector_space=embedding.profile.vector_space,
                authorized_sources=(embedding.source,),
            )
            assert values == (embedding,)
            assert (
                await store.list_authorized_multilingual_embeddings_v3(
                    notebook_id=embedding.source.notebook_id,
                    generation_id=embedding.profile.generation_id,
                    vector_space=embedding.profile.vector_space,
                    authorized_sources=(),
                )
                == ()
            )
            assert store.attestation is not None
            assert store.attestation.vector_count == evaluator.COMPACT_VECTOR_COUNT
            assert store.attestation.model_revision == evaluator.COMPACT_MODEL_REVISION
            assert store.attestation.vector_encoding == evaluator.COMPACT_VECTOR_ENCODING
            child = evaluator.CompactVectorReadOnlyEvaluationStore(
                runtime / "mnemo.db", progress, attestation=store.attestation
            )
            await child.open()
            try:
                assert child.attestation == store.attestation
                assert child._compact_db is not None
                assert await (await child._compact_db.execute("PRAGMA query_only")).fetchone() == (
                    1,
                )
            finally:
                await child.close()
            with pytest.raises(sqlite3.OperationalError):
                await store._compact_db.execute(
                    "DELETE FROM compact_multilingual_embeddings_v1 WHERE embedding_id=?",
                    (str(embedding.embedding_id),),
                )
        finally:
            await store.close()

    try:
        asyncio.run(exercise())
    finally:
        progress.close()
    assert hash_calls == [evaluator.COMPACT_VECTOR_DB]
    assert compact_vectors.sha256(evaluator.COMPACT_VECTOR_DB) == before


def test_multimodal_probe_receipt_is_append_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def fake_probe(**_: object) -> dict[str, object]:
        return {"scope": ["disposable"], "results": {"combined": {"outcome": "completed"}}}

    monkeypatch.setattr(multimodal_evaluator, "COPY", tmp_path)
    monkeypatch.setattr(multimodal_evaluator, "probe", fake_probe)
    monkeypatch.setattr(multimodal_evaluator, "uuid4", lambda: UUID(int=1))
    monkeypatch.setattr(sys, "argv", ["evaluate_module_894_multimodal.py", "--with-bge"])
    assert multimodal_evaluator.main() == 0
    output = json.loads(capsys.readouterr().out)
    artifact = Path(output["artifact"])
    assert artifact.parent == tmp_path
    assert json.loads(artifact.read_text(encoding="utf-8"))["results"]["combined"] == {
        "outcome": "completed"
    }
    with pytest.raises(FileExistsError):
        multimodal_evaluator.main()


def test_multimodal_single_notebook_filter_is_evaluation_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    observed: list[bool] = []

    async def fake_probe(**kwargs: object) -> dict[str, object]:
        observed.append(bool(kwargs["single_notebook_only"]))
        return {"evaluated_count": 10}

    monkeypatch.setattr(multimodal_evaluator, "COPY", tmp_path)
    monkeypatch.setattr(multimodal_evaluator, "probe", fake_probe)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_module_894_multimodal.py",
            "--with-bge",
            "--visual-qrels",
            "--unified-visual",
            "--single-notebook-only",
        ],
    )
    assert multimodal_evaluator.main() == 0
    assert observed == [True]
    assert json.loads(capsys.readouterr().out)["evaluated_count"] == 10


def test_quarantined_retry_preserves_failed_receipts_without_touching_originals(
    tmp_path: Path,
) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    runner.write_json(logs / "run_state.json", {"status": "QUARANTINED"})
    runner.write_json(logs / "ingestion_summary.json", {"status": "FAIL"})
    (logs / "events.jsonl").write_text("failed attempt\n", encoding="utf-8")
    original = {path.name: runner.digest(path) for path in logs.iterdir()}
    archived = runner.archive_quarantined_attempt(logs)
    assert archived == logs / "attempts" / "attempt-001"
    assert archived is not None
    assert json.loads((archived / "archive_manifest.json").read_text()) == original
    assert {path.name: runner.digest(path) for path in logs.iterdir() if path.is_file()} == original
    assert runner.archive_quarantined_attempt(logs) == logs / "attempts" / "attempt-002"
    runner.write_json(logs / "run_state.json", {"status": "SUCCEEDED"})
    assert runner.archive_quarantined_attempt(logs) is None


@pytest.fixture
def reused_document_store() -> Iterator[tuple[sqlite3.Connection, sqlite3.Connection, str, Path]]:
    plan, _ = runner.preflight()
    snapshot = runner.ROOT / plan["existing_notebook"]["snapshot"]
    original = sqlite3.connect(
        f"file:{snapshot.resolve().as_posix()}?mode=ro&immutable=1", uri=True
    )
    current = sqlite3.connect(":memory:")
    original.backup(current)
    source = original.execute(
        "SELECT d.current_hash FROM documents d JOIN asset_occurrences a "
        "ON a.document_id=d.document_id JOIN ocr_results o "
        "ON o.occurrence_id=a.occurrence_id JOIN ocr_regions r "
        "ON r.derivation_id=o.derivation_id LIMIT 1"
    ).fetchone()
    assert source is not None
    try:
        yield (
            original,
            current,
            str(source[0]),
            runner.ROOT / plan["existing_notebook"]["retained_files"],
        )
    finally:
        current.close()
        original.close()


def _validate(
    fixture: tuple[sqlite3.Connection, sqlite3.Connection, str, Path],
) -> dict[str, object]:
    original, current, content_hash, parsed_root = fixture
    return auditor.validate_reused_document(
        original,
        current,
        content_hash=content_hash,
        parsed_root=parsed_root,
        model_revision=runner.MODEL_REVISION,
    )


def test_complete_reused_document_passes_before_publication(
    reused_document_store: tuple[sqlite3.Connection, sqlite3.Connection, str, Path],
) -> None:
    assert _validate(reused_document_store)["status"] == "PASS"


def test_missing_chunk_blocks_reused_document_publication(
    reused_document_store: tuple[sqlite3.Connection, sqlite3.Connection, str, Path],
) -> None:
    _, current, content_hash, _ = reused_document_store
    current.execute(
        "DELETE FROM chunks WHERE id=(SELECT c.id FROM chunks c JOIN documents d "
        "ON d.document_id=c.document_id WHERE d.current_hash=? LIMIT 1)",
        (content_hash,),
    )
    assert _validate(reused_document_store)["status"] == "FAIL"


def test_changed_chunk_text_hash_blocks_publication(
    reused_document_store: tuple[sqlite3.Connection, sqlite3.Connection, str, Path],
) -> None:
    _, current, content_hash, _ = reused_document_store
    current.execute(
        "UPDATE chunks SET text='tampered' WHERE id=(SELECT c.id FROM chunks c "
        "JOIN documents d ON d.document_id=c.document_id "
        "WHERE d.current_hash=? LIMIT 1)",
        (content_hash,),
    )
    assert _validate(reused_document_store)["status"] == "FAIL"


def test_missing_modality_derivation_blocks_publication(
    reused_document_store: tuple[sqlite3.Connection, sqlite3.Connection, str, Path],
) -> None:
    _, current, content_hash, _ = reused_document_store
    current.execute(
        "DELETE FROM asset_derivations WHERE derivation_id=(SELECT a.derivation_id "
        "FROM asset_derivations a JOIN asset_occurrences o USING(occurrence_id) "
        "JOIN documents d ON d.document_id=o.document_id "
        "WHERE d.current_hash=? LIMIT 1)",
        (content_hash,),
    )
    assert _validate(reused_document_store)["status"] == "FAIL"


def test_missing_ocr_region_blocks_publication(
    reused_document_store: tuple[sqlite3.Connection, sqlite3.Connection, str, Path],
) -> None:
    _, current, content_hash, _ = reused_document_store
    current.execute(
        "DELETE FROM ocr_regions WHERE region_id=(SELECT r.region_id FROM ocr_regions r "
        "JOIN ocr_results o ON o.derivation_id=r.derivation_id "
        "JOIN documents d ON d.document_id=o.document_id "
        "WHERE d.current_hash=? LIMIT 1)",
        (content_hash,),
    )
    assert _validate(reused_document_store)["status"] == "FAIL"


def test_passing_audit_receipt_is_not_replaced(tmp_path: Path) -> None:
    runner.write_json(tmp_path / "provider_results.json", {"generation": "g1"})
    receipt = runner.commit_pre_activation_audit(tmp_path, {"status": "PASS", "errors": []})
    assert receipt == runner.digest(tmp_path / "pre_activation_audit.json")
    with pytest.raises(RuntimeError, match="differs"):
        runner.commit_pre_activation_audit(tmp_path, {"status": "PASS", "errors": ["changed"]})
    with pytest.raises(RuntimeError, match="failed"):
        runner.commit_pre_activation_audit(tmp_path, {"status": "FAIL"})


def test_unverified_disposable_alias_uses_exact_rollback_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mnemo.storage import sqlite as sqlite_module

    plan = json.loads(runner.PLAN.read_text(encoding="utf-8"))
    build = {
        "notebook_ids": [
            plan["existing_notebook"]["id"],
            *(str(value) for value in runner.notebook_ids(plan).values()),
        ],
        "generations": {key: str(i) for i, key in enumerate(runner.CAPABILITIES)},
        "profile_fingerprint": "fixture-profile",
    }
    runner.write_json(tmp_path / "provider_results.json", build)
    runner.write_json(tmp_path / "provider_activation.json", {"alias": "fixture"})
    calls: list[dict[str, object]] = []

    class FakeStore:
        def __init__(self, _path: Path) -> None:
            self.active: str | None = "fixture-alias"

        async def open(self) -> None:
            return None

        async def close(self) -> None:
            return None

        async def resolve_active_multilingual_v2_alias_digest(self) -> str | None:
            return self.active

        async def deactivate_first_multilingual_v2_alias_set(self, **kwargs: Any) -> bool:
            calls.append(kwargs)
            self.active = None
            return True

    monkeypatch.setattr(sqlite_module, "SQLiteStore", FakeStore)
    assert asyncio.run(runner.deactivate_unverified_alias(plan, tmp_path, tmp_path))
    assert calls[0]["expected_active_alias_set_digest"] == "fixture-alias"
    assert (
        calls[0]["authorization_digest"]
        == hashlib.sha256(
            json.dumps(
                {
                    "scope": "isolated-disposable-evaluation-only",
                    "run_key": plan["run_key"],
                    "actor_id": plan["disposable_actor_id"],
                    "notebook_ids": build["notebook_ids"],
                    "generations": build["generations"],
                    "profile_fingerprint": build["profile_fingerprint"],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    )
    assert not (tmp_path / "provider_activation.json").exists()
    assert len(list(tmp_path.glob("provider_activation.recovered.*.json"))) == 1


def test_audit_failure_prevents_alias_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = json.loads(runner.PLAN.read_text(encoding="utf-8"))
    runtime, logs = tmp_path / "runtime", tmp_path / "logs"
    runtime.mkdir()
    logs.mkdir()
    calls: list[str] = []

    def copy(_plan: Any, path: Path, _log: Any) -> None:
        with sqlite3.connect(path / "mnemo.db") as db:
            db.execute("CREATE TABLE active_multilingual_v2_alias_set(alias_set_digest TEXT)")

    async def create(*_args: Any) -> None:
        calls.append("create")

    async def link(*_args: Any) -> None:
        calls.append("link")

    async def build(_plan: Any, _runtime: Path, directory: Path, _log: Any) -> dict[str, Any]:
        runner.write_json(directory / "provider_results.json", {"generation": "g1"})
        calls.append("build")
        return {"generation": "g1"}

    async def promote(*_args: Any) -> None:
        calls.append("promote")

    def audit(*_args: Any, **_kwargs: Any) -> dict[str, object]:
        calls.append("audit")
        return {"status": "FAIL", "errors": ["incomplete source"]}

    monkeypatch.setattr(runner, "prepare_copy", copy)
    monkeypatch.setattr(runner, "create_notebooks", create)
    monkeypatch.setattr(runner, "link_sources", link)
    monkeypatch.setattr(runner, "build_generations", build)
    monkeypatch.setattr(runner, "promote_audited_alias", promote)
    monkeypatch.setattr(auditor, "audit", audit)
    with pytest.raises(RuntimeError, match="pre-activation audit failed"):
        asyncio.run(runner._execute_locked(plan, {}, "test", runtime, logs))
    assert calls == ["create", "link", "build", "audit"]
    assert not (logs / "pre_activation_audit.json").exists()
    assert json.loads((logs / "run_state.json").read_text())["status"] == "QUARANTINED"


@pytest.mark.parametrize("crash_after_promotion", [False, True])
def test_promotion_requires_frozen_audit_and_post_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_after_promotion: bool,
) -> None:
    plan = json.loads(runner.PLAN.read_text(encoding="utf-8"))
    records = runner.preflight()[1]
    runtime, logs = tmp_path / "runtime", tmp_path / "logs"
    runtime.mkdir()
    logs.mkdir()
    calls: list[str] = []

    def copy(_plan: Any, path: Path, _log: Any) -> None:
        if not (path / "mnemo.db").exists():
            with sqlite3.connect(path / "mnemo.db") as db:
                db.execute("CREATE TABLE active_multilingual_v2_alias_set(alias_set_digest TEXT)")

    async def noop(*_args: Any) -> None:
        return None

    async def build(_plan: Any, _runtime: Path, directory: Path, _log: Any) -> dict[str, Any]:
        runner.write_json(directory / "provider_results.json", {"generation": "g1"})
        return {"generation": "g1"}

    def audit(*_args: Any, require_active_alias: bool = True) -> dict[str, object]:
        calls.append("post_audit" if require_active_alias else "pre_audit")
        return (
            {"status": "PASS", "errors": []}
            if not require_active_alias
            else {
                "status": "FAIL"
                if not crash_after_promotion and calls.count("promote") == 1
                else "PASS",
                "errors": ["post-promotion mismatch"]
                if not crash_after_promotion and calls.count("promote") == 1
                else [],
            }
        )

    async def promote(
        _plan: Any, path: Path, directory: Path, _log: Any, _build: dict[str, Any], receipt: str
    ) -> None:
        assert runner.digest(directory / "pre_activation_audit.json") == receipt
        assert (
            json.loads((directory / "run_manifest.json").read_text())["pre_activation_audit_sha256"]
            == receipt
        )
        calls.append("promote")
        with sqlite3.connect(path / "mnemo.db") as db:
            if not db.execute("SELECT 1 FROM active_multilingual_v2_alias_set").fetchone():
                db.execute("INSERT INTO active_multilingual_v2_alias_set VALUES('fixture-alias')")
        if crash_after_promotion and calls.count("promote") == 1:
            raise RuntimeError("simulated post-promotion interruption")

    async def deactivate(_plan: Any, path: Path, _logs: Path) -> bool:
        calls.append("deactivate")
        if crash_after_promotion:
            raise RuntimeError("simulated recovery failure")
        with sqlite3.connect(path / "mnemo.db") as db:
            db.execute("DELETE FROM active_multilingual_v2_alias_set")
        return True

    def bind(*_args: Any) -> Path:
        calls.append("bind")
        destination = logs / identity_qrels.BOUND_NAME
        runner.write_json(destination, {"schema": "fixture-bound-qrels"})
        return destination

    monkeypatch.setattr(runner, "prepare_copy", copy)
    monkeypatch.setattr(runner, "create_notebooks", noop)
    monkeypatch.setattr(runner, "link_sources", noop)
    monkeypatch.setattr(runner, "build_generations", build)
    monkeypatch.setattr(runner, "promote_audited_alias", promote)
    monkeypatch.setattr(runner, "deactivate_unverified_alias", deactivate)
    monkeypatch.setattr(auditor, "audit", audit)
    monkeypatch.setattr(identity_qrels, "bind_qrels", bind)

    with pytest.raises(RuntimeError, match="post-promotion"):
        asyncio.run(runner._execute_locked(plan, records, "test", runtime, logs))
    assert calls[:2] == ["pre_audit", "promote"]
    assert "deactivate" in calls
    assert json.loads((logs / "run_state.json").read_text())["status"] == "QUARANTINED"
    assert json.loads((logs / "ingestion_summary.json").read_text())["status"] == "FAIL"
    if crash_after_promotion:
        assert asyncio.run(runner._execute_locked(plan, records, "test", runtime, logs)) == 0
        assert calls.count("pre_audit") == 1
        assert calls[-3:] == ["promote", "post_audit", "bind"]
        assert json.loads((logs / "run_state.json").read_text())["status"] == "SUCCEEDED"
    else:
        with sqlite3.connect(runtime / "mnemo.db") as db:
            assert db.execute(
                "SELECT COUNT(*) FROM active_multilingual_v2_alias_set"
            ).fetchone() == (0,)
        assert asyncio.run(runner._execute_locked(plan, records, "test", runtime, logs)) == 0
        assert calls.count("pre_audit") == 2
        assert json.loads((logs / "run_state.json").read_text())["status"] == "SUCCEEDED"


def test_preflight_identifies_retained_notebook_and_reviewed_partition() -> None:
    plan, records = runner.preflight()
    assert plan["existing_notebook"]["id"] == "81a3bea2-8b15-5c6f-944d-24634fbf835d"
    assert [len(plan["notebooks"][language]["files"]) for language in ("hi", "mr", "en")] == [
        5,
        6,
        9,
    ]
    assert len(records) == 24
    assert len(set(runner.notebook_ids(plan).values())) == 3
    _run_id, runtime, logs = runner.run_paths(plan)
    runner.verify_output_boundary(runtime, logs)


def test_historical_identity_blueprint_has_only_snapshot_verified_anchors() -> None:
    plan, records = runner.preflight()
    blueprint = identity_qrels.load_blueprint(plan, records)
    assert len(blueprint["cases"]) == 9
    assert {case["query_language"] for case in blueprint["cases"]} == {"en", "hi", "mr"}
    assert any(len(case["selected_partitions"]) == 4 for case in blueprint["cases"])
    assert blueprint["human_adjudication_claimed"] is False
    assert blueprint["semantic_relevance_adjudicated"] is False


def test_identity_blueprint_rejects_unhistorical_anchor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, records = runner.preflight()
    altered = json.loads(identity_qrels.BLUEPRINT.read_text(encoding="utf-8"))
    altered["cases"][0]["anchor_phrases"] = ["retrieval output said this was relevant"]
    path = tmp_path / "altered.json"
    path.write_text(json.dumps(altered), encoding="utf-8")
    monkeypatch.setattr(identity_qrels, "BLUEPRINT", path)
    with pytest.raises(ValueError, match="historically authored"):
        identity_qrels.load_blueprint(plan, records)


def test_identity_qrels_bind_only_actual_new_source_memberships(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, records = runner.preflight()
    blueprint = identity_qrels.load_blueprint(plan, records)
    runtime, logs = tmp_path / "runtime", tmp_path / "logs"
    runtime.mkdir()
    logs.mkdir()
    shutil.copy2(runner.ROOT / plan["existing_notebook"]["snapshot"], runtime / "mnemo.db")
    ids = runner.notebook_ids(plan)
    with sqlite3.connect(runtime / "mnemo.db") as db:
        for case in blueprint["cases"]:
            source_hash = case["target"]["source_file_sha256"]
            document_id = case["target"]["document_id"]
            for membership in case["target_memberships"]:
                if membership == "existing":
                    continue
                notebook_id = str(ids[membership])
                if db.execute(
                    "SELECT 1 FROM sources WHERE notebook_id=? AND document_id=?",
                    (notebook_id, document_id),
                ).fetchone():
                    continue
                source_id = str(uuid5(NAMESPACE_URL, f"fixture:{notebook_id}:{source_hash}"))
                db.execute(
                    "INSERT INTO sources(source_id,notebook_id,document_id,created_at) "
                    "VALUES(?,?,?,?)",
                    (source_id, notebook_id, document_id, "2026-11-08T00:00:00+00:00"),
                )
    bound = identity_qrels.bind_qrels(plan, records, runtime, logs, ids)
    assert bound == identity_qrels.bind_qrels(plan, records, runtime, logs, ids)
    parsed = evaluator.load_qrels(
        bound,
        runtime / "mnemo.db",
        {UUID(str(plan["existing_notebook"]["id"])), *ids.values()},
        {record["sha256"] for record in records.values()},
    )
    assert len(parsed["cases"]) == 9
    assert all(case["targets"] for case in parsed["cases"])
    changed = json.loads(bound.read_text(encoding="utf-8"))
    changed["cases"][0]["targets"][0]["version_id"] = str(UUID(int=0))
    invalid = logs / "invalid-qrels.json"
    invalid.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="unbound"):
        evaluator.load_qrels(
            invalid,
            runtime / "mnemo.db",
            {UUID(str(plan["existing_notebook"]["id"])), *ids.values()},
            {record["sha256"] for record in records.values()},
        )
    with sqlite3.connect(runtime / "mnemo.db") as db:
        db.execute(
            "DELETE FROM sources WHERE notebook_id=? AND document_id=?",
            (str(ids["hi"]), blueprint["cases"][2]["target"]["document_id"]),
        )
    with pytest.raises(ValueError, match="membership/ancestry"):
        identity_qrels.bind_qrels(plan, records, runtime, logs, ids)


def test_dry_run_does_not_create_runtime_or_logs() -> None:
    plan, _ = runner.preflight()
    _, runtime, logs = runner.run_paths(plan)

    def state() -> dict[str, tuple[int, int]]:
        return {
            str(path): (path.stat().st_size, path.stat().st_mtime_ns)
            for root in (runtime, logs)
            if root.exists()
            for path in root.iterdir()
            if path.is_file()
        }

    before = state()
    result = subprocess.run(
        [sys.executable, str(runner.ROOT / "scripts/run_phase86_four_notebooks.py"), "dry-run"],
        cwd=runner.ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "PREFLIGHT_PASS"
    assert state() == before


def test_swapped_language_assignment_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = json.loads(runner.PLAN.read_text(encoding="utf-8"))
    hi = plan["notebooks"]["hi"]["files"]
    mr = plan["notebooks"]["mr"]["files"]
    hi[0], mr[0] = mr[0], hi[0]
    altered = tmp_path / "altered.json"
    altered.write_text(json.dumps(plan), encoding="utf-8")
    monkeypatch.setattr(runner, "PLAN", altered)
    with pytest.raises(RuntimeError, match="reviewed partition"):
        runner.preflight()


def test_second_writer_is_rejected(tmp_path: Path) -> None:
    lock = tmp_path / "run.lock"
    with (
        runner.exclusive_run(lock),
        pytest.raises(RuntimeError, match="another process owns"),
        runner.exclusive_run(lock),
    ):
        pass
    with runner.exclusive_run(lock):
        pass


def test_output_path_cannot_escape_disposable_root(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="escaped"):
        runner.verify_output_boundary(tmp_path / "unexpected", tmp_path / "logs")


def test_audit_is_not_a_success_without_ingestion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        evaluator, "run_paths", lambda _plan: ("isolated", tmp_path / "runtime", tmp_path / "logs")
    )
    with pytest.raises(RuntimeError, match="ingestion and independent"):
        evaluator.preflight_evaluation()


def test_evaluation_store_cannot_write_or_migrate(tmp_path: Path) -> None:
    async def probe() -> None:
        database = tmp_path / "evaluation.db"
        writable = evaluator.SQLiteStore(database)
        await writable.open()
        await writable.close()
        before = hashlib.sha256(database.read_bytes()).hexdigest()

        readonly = evaluator.ReadOnlyEvaluationStore(database)
        await readonly.open()
        try:
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                await readonly._require_open().execute(
                    "INSERT INTO notebooks(notebook_id,title,created_at) VALUES('x','x','x')"
                )
            assert hashlib.sha256(database.read_bytes()).hexdigest() == before
        finally:
            await readonly.close()

    asyncio.run(probe())


def test_evaluation_store_sees_committed_wal_without_checkpoint(tmp_path: Path) -> None:
    async def probe() -> None:
        database = tmp_path / "evaluation.db"
        with sqlite3.connect(database) as setup:
            setup.execute("PRAGMA journal_mode=WAL")
            setup.execute("CREATE TABLE wal_probe(value TEXT)")
        writer = sqlite3.connect(database)
        try:
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute("INSERT INTO wal_probe VALUES('committed')")
            writer.commit()
            readonly = evaluator.ReadOnlyEvaluationStore(database)
            await readonly.open()
            try:
                row = await (
                    await readonly._require_open().execute("SELECT value FROM wal_probe")
                ).fetchone()
                assert row == ("committed",)
            finally:
                await readonly.close()
        finally:
            writer.close()

    asyncio.run(probe())


def test_evaluation_preflight_does_not_rewrite_audit_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, logs = tmp_path / "runtime", tmp_path / "logs"
    runtime.mkdir()
    logs.mkdir()
    (runtime / "mnemo.db").touch()
    (runtime / "acl.db").touch()
    bound = logs / identity_qrels.BOUND_NAME
    bound.write_text("{}", encoding="utf-8")
    bound_hash = evaluator.digest(bound)
    (logs / "ingestion_summary.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "pre_activation_audit_sha256": "audit",
                "bound_qrels_sha256": bound_hash,
            }
        ),
        encoding="utf-8",
    )
    (logs / "run_state.json").write_text(
        json.dumps(
            {
                "status": "SUCCEEDED",
                "pre_activation_audit_sha256": "audit",
                "bound_qrels_sha256": bound_hash,
            }
        ),
        encoding="utf-8",
    )
    plan = {"existing_notebook": {"id": str(UUID(int=1))}}
    monkeypatch.setattr(evaluator, "preflight", lambda: (plan, {}))
    monkeypatch.setattr(evaluator, "run_paths", lambda _plan: ("isolated", runtime, logs))
    monkeypatch.setattr(evaluator, "notebook_ids", lambda _plan: {})
    monkeypatch.setattr(evaluator, "load_qrels", lambda *_args: {})
    options: list[bool] = []

    def audit_probe(*_args: object, write_artifacts: bool = True) -> dict[str, str]:
        options.append(write_artifacts)
        return {"status": "PASS"}

    monkeypatch.setattr(auditor, "audit", audit_probe)
    evaluator.preflight_evaluation()
    assert options == [False]


def test_failed_provider_attempt_uses_new_generation_identity(tmp_path: Path) -> None:
    database = tmp_path / "isolated.db"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE index_generations(capability TEXT,state TEXT)")
    assert runner.next_provider_attempt(database, tmp_path) == 0
    assert runner.next_provider_attempt(database, tmp_path) == 0
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO index_generations VALUES('multilingual_embedding_v2','failed')")
    assert runner.next_provider_attempt(database, tmp_path) == 1
    assert runner.next_provider_attempt(database, tmp_path) == 1
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO index_generations VALUES('language_text_v2','failed')")
    assert runner.next_provider_attempt(database, tmp_path) == 2


def test_evaluation_requires_completed_ingestion_and_independent_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        evaluator, "run_paths", lambda _plan: ("isolated", tmp_path / "runtime", tmp_path / "logs")
    )
    with pytest.raises(RuntimeError, match="ingestion and independent"):
        evaluator.preflight_evaluation()
    qrels = tmp_path / "unjudged.json"
    qrels.write_text(
        json.dumps(
            {
                "schema": "mnemo.phase86-four-notebook-dere/1",
                "judgment_method": "DETERMINISTIC_ENGINEERING",
                "human_adjudication_claimed": False,
                "cases": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="independently declared"):
        evaluator.load_qrels(qrels, tmp_path / "absent.db", set(), set())


def test_evaluation_metrics_preserve_exact_membership_identity() -> None:
    original = {
        "notebook_id": "a",
        "source_id": "source-a",
        "document_id": "document",
        "version_id": "version",
        "evidence_id": "chunk",
    }
    same_chunk_other_membership = {**original, "notebook_id": "b", "source_id": "source-b"}
    measured = evaluator.metrics(
        [same_chunk_other_membership, original], {tuple(original.values())}, 10
    )
    assert measured["recall_at_1"] == 0
    assert measured["recall_at_5"] == measured["recall_at_10"] == 1
    assert measured["mrr"] == 0.5
    assert measured["precision_at_5"] == 0.2


def test_evaluation_reconciles_public_chunk_and_derived_evidence_identity() -> None:
    canonical = evaluator._ranked_identity({"chunk_id": "chunk-a", "locator": {}})
    derived = evaluator._ranked_identity({"chunk_id": None, "locator": {"evidence_id": "region-a"}})
    assert canonical["evidence_id"] == "chunk-a"
    assert derived["evidence_id"] == "region-a"
    with pytest.raises(ValueError, match="disagree"):
        evaluator._ranked_identity({"chunk_id": "chunk-a", "locator": {"evidence_id": "chunk-b"}})
    with pytest.raises(ValueError, match="missing"):
        evaluator._ranked_identity({"chunk_id": None, "locator": {}})


@pytest.mark.parametrize(
    ("failure", "outcome", "category"),
    [
        (None, "completed", None),
        ("timeout", "timed_out", "OperationTimeoutError"),
        ("unexpected", "failed", "ValueError"),
    ],
)
def test_evaluation_progress_records_request_without_content(
    tmp_path: Path, failure: str | None, outcome: str, category: str | None
) -> None:
    selected = (UUID(int=1), UUID(int=2))
    secret = "PRIVATE QUERY AND DOCUMENT TEXT"
    request = evaluator.ScopeRequestReview(
        query=secret,
        mode="ranked",
        limit=10,
        scope=evaluator.SelectedNotebooks(kind="selected", notebook_ids=selected),
    )
    principal = evaluator.PrincipalContextV1(UUID(int=3), True)
    seen: list[tuple[object, object]] = []

    class Service:
        async def execute_ranked(self, supplied: object, actor: object) -> object:
            seen.append((supplied, actor))
            if failure == "timeout":
                raise evaluator.OperationTimeoutError("deadline")
            if failure == "unexpected":
                raise ValueError("private provider detail")
            return SimpleNamespace(items=({"content": secret},))

    clock_values = iter(datetime(2026, 11, 9, 0, 0, second, tzinfo=UTC) for second in (0, 1, 4))
    timer_values = iter((10.0, 12.5))
    progress = evaluator.EvaluationProgress(
        tmp_path,
        "isolated-run",
        clock=lambda: next(clock_values),
        timer=lambda: next(timer_values),
    )

    async def run() -> None:
        if failure == "timeout":
            with pytest.raises(evaluator.OperationTimeoutError):
                await progress.execute(
                    Service(), request, principal, case_id="Q01", mode="sparse", selected=selected
                )
        elif failure == "unexpected":
            with pytest.raises(ValueError):
                await progress.execute(
                    Service(), request, principal, case_id="Q01", mode="sparse", selected=selected
                )
        else:
            result = await progress.execute(
                Service(), request, principal, case_id="Q01", mode="sparse", selected=selected
            )
            assert len(result.items) == 1

    try:
        asyncio.run(run())
    finally:
        progress.close()
    lines = progress.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    started, finished = map(json.loads, lines)
    assert started["outcome"] == "started"
    assert started["request_completed_at"] is None
    assert finished["outcome"] == outcome
    assert finished["exception_class"] == category
    assert finished["elapsed_seconds"] == 2.5
    assert finished["result_count"] == (1 if failure is None else None)
    assert finished["case_id"] == "Q01"
    assert finished["retrieval_mode"] == "sparse"
    assert finished["scope_count"] == 2
    assert seen == [(request, principal)]
    assert secret not in progress.path.read_text(encoding="utf-8")
    assert "private provider detail" not in progress.path.read_text(encoding="utf-8")
    assert evaluator.ServerConfig().max_advanced_elapsed_milliseconds == 30_000


def test_evaluation_progress_start_is_durable_and_writer_failure_stops_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    progress = evaluator.EvaluationProgress(tmp_path, "isolated-run")
    selected = (UUID(int=1),)
    progress.start(case_id="Q02", mode="dense", selected=selected)
    progress.close()
    rows = progress.path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0])["outcome"] == "started"

    second = evaluator.EvaluationProgress(tmp_path, "isolated-run")
    monkeypatch.setattr(
        second, "_append", lambda _record: (_ for _ in ()).throw(OSError("disk full"))
    )
    called = False

    class Service:
        async def execute_ranked(self, _request: object, _principal: object) -> object:
            nonlocal called
            called = True
            return SimpleNamespace(items=())

    async def run() -> None:
        with pytest.raises(OSError, match="disk full"):
            await second.execute(
                Service(),
                evaluator.ScopeRequestReview(
                    query="safe query",
                    mode="ranked",
                    limit=10,
                    scope=evaluator.SelectedNotebooks(kind="selected", notebook_ids=selected),
                ),
                evaluator.PrincipalContextV1(UUID(int=2), True),
                case_id="Q02",
                mode="dense",
                selected=selected,
            )

    try:
        asyncio.run(run())
    finally:
        second.close()
    assert not called


def test_evaluation_child_receipts_are_concurrent_content_free_and_cancellation_safe(
    tmp_path: Path,
) -> None:
    selected = (UUID(int=1), UUID(int=2), UUID(int=3), UUID(int=4))
    private = "PRIVATE QUERY AND DOCUMENT TEXT"
    request = evaluator.ScopeRequestReview(
        query=private,
        mode="ranked",
        limit=10,
        scope=evaluator.SelectedNotebooks(kind="selected", notebook_ids=selected),
    )
    progress = evaluator.EvaluationProgress(tmp_path, "isolated-run")

    class Service:
        async def execute_ranked(self, supplied: object, actor: object) -> object:
            assert supplied is request
            assert actor == evaluator.PrincipalContextV1(UUID(int=5), True)

            async def child(notebook: UUID) -> None:
                progress.observe_child(notebook, "child", "started", None, None)
                progress.observe_child(notebook, "canonical_sparse_source", "started", None, None)
                await asyncio.sleep(0)
                progress.observe_child(notebook, "canonical_sparse_source", "completed", 3, None)
                progress.observe_child(notebook, "child", "cancelled", None, "CancelledError")

            await asyncio.gather(*(child(notebook) for notebook in selected))
            raise evaluator.OperationTimeoutError(private)

    try:
        with pytest.raises(evaluator.OperationTimeoutError):
            asyncio.run(
                progress.execute(
                    Service(),
                    request,
                    evaluator.PrincipalContextV1(UUID(int=5), True),
                    case_id="Q21",
                    mode="bge",
                    selected=selected,
                )
            )
    finally:
        progress.close()
    rows = [json.loads(line) for line in progress.path.read_text(encoding="utf-8").splitlines()]
    child = [row for row in rows if row.get("stage") == "child"]
    assert len(child) == 8
    assert {row["notebook_id"] for row in child} == {str(value) for value in selected}
    assert {row["outcome"] for row in child} == {"started", "cancelled"}
    sparse = [row for row in rows if row.get("stage") == "canonical_sparse_source"]
    assert len(sparse) == 8
    assert {row["result_count"] for row in sparse if row["outcome"] == "completed"} == {3}
    assert all(row["case_id"] == "Q21" for row in rows)
    assert private not in progress.path.read_text(encoding="utf-8")
    assert evaluator.ServerConfig().max_advanced_elapsed_milliseconds == 30_000


def test_evaluation_child_started_receipt_survives_interruption(tmp_path: Path) -> None:
    progress = evaluator.EvaluationProgress(tmp_path, "isolated-run")
    token = progress._context.set(("Q21", "bge"))
    try:
        progress.observe_child(UUID(int=1), "full_v2_source", "started", None, None)
    finally:
        progress._context.reset(token)
        progress.close()
    rows = [json.loads(line) for line in progress.path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["outcome"] == "started"
    assert rows[0]["completed_at"] is None


def test_internal_stage_timing_preserves_result_and_cancellation(tmp_path: Path) -> None:
    progress = evaluator.EvaluationProgress(tmp_path, "isolated-run")
    notebook = UUID(int=7)
    token = progress._context.set(("Q21", "bge"))

    async def completed() -> tuple[int, ...]:
        return (3, 1, 2)

    async def cancelled() -> tuple[int, ...]:
        raise asyncio.CancelledError("PRIVATE DOCUMENT CONTENT")

    async def probe() -> None:
        assert await progress.measure_internal(
            notebook, "vector_row_loading", completed(), input_count=3
        ) == (3, 1, 2)
        with pytest.raises(asyncio.CancelledError):
            await progress.measure_internal(notebook, "bge_query_embedding", cancelled())
        assert await progress.measure_internal(None, "not_entered", completed()) == (3, 1, 2)

    try:
        asyncio.run(probe())
    finally:
        progress._context.reset(token)
        progress.close()
    rows = [json.loads(line) for line in progress.path.read_text(encoding="utf-8").splitlines()]
    assert [(row["stage"], row["outcome"]) for row in rows] == [
        ("vector_row_loading", "started"),
        ("vector_row_loading", "completed"),
        ("bge_query_embedding", "started"),
        ("bge_query_embedding", "cancelled"),
    ]
    assert rows[0]["input_count"] == 3
    assert rows[1]["result_count"] == 3
    assert rows[3]["exception_class"] == "CancelledError"
    assert "PRIVATE DOCUMENT CONTENT" not in progress.path.read_text(encoding="utf-8")


def test_profiled_store_is_query_only_and_does_not_checkpoint(tmp_path: Path) -> None:
    database = tmp_path / "evaluation.db"
    with sqlite3.connect(database) as setup:
        setup.execute("PRAGMA journal_mode=WAL")
        setup.execute("CREATE TABLE wal_probe(value TEXT)")
    writer = sqlite3.connect(database)
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute("INSERT INTO wal_probe VALUES('committed')")
    writer.commit()
    wal = database.with_name(database.name + "-wal")
    before = hashlib.sha256(wal.read_bytes()).hexdigest()
    progress = evaluator.EvaluationProgress(tmp_path, "isolated-run")

    async def probe() -> None:
        store = evaluator.ProfiledReadOnlyEvaluationStore(database, progress)
        await store.open()
        try:
            row = await (
                await store._require_open().execute("SELECT value FROM wal_probe")
            ).fetchone()
            assert row == ("committed",)
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                await store._require_open().execute("INSERT INTO wal_probe VALUES('no')")
        finally:
            await store.close()

    try:
        asyncio.run(probe())
        assert hashlib.sha256(wal.read_bytes()).hexdigest() == before
    finally:
        progress.close()
        writer.close()


def test_notebook_read_partition_dispatch_preserves_request_and_fails_closed() -> None:
    notebooks = tuple(uuid4() for _ in range(4))
    calls: list[tuple[UUID, object, int, int]] = []

    class Source:
        representation = evaluator.EvidenceRepresentation.MULTILINGUAL_TEXT

        def __init__(self, notebook_id: UUID) -> None:
            self.notebook_id = notebook_id

        async def retrieve_authorized(
            self, *, principal: object, plan: object, offset: int, limit: int
        ) -> object:
            calls.append((self.notebook_id, principal, offset, limit))
            return self.notebook_id

    sources = {notebook: Source(notebook) for notebook in notebooks}
    dispatch = evaluator.NotebookReadPartitionSource(cast(Any, sources))
    principal = object()
    plan = SimpleNamespace(scope=SimpleNamespace(notebook_id=notebooks[2]))
    result = asyncio.run(
        dispatch.retrieve_authorized(
            principal=cast(Any, principal), plan=cast(Any, plan), offset=0, limit=10
        )
    )
    assert result == notebooks[2]
    assert calls == [(notebooks[2], principal, 0, 10)]
    with pytest.raises(PermissionError, match="no authorized read partition"):
        dispatch._source(cast(Any, SimpleNamespace(scope=SimpleNamespace(notebook_id=uuid4()))))


def test_qrel_provenance_join_rejects_wrong_scope_and_version(tmp_path: Path) -> None:
    database = tmp_path / "provenance.db"
    with sqlite3.connect(database) as db:
        db.executescript(
            "CREATE TABLE sources(notebook_id TEXT,source_id TEXT,document_id TEXT);"
            "CREATE TABLE documents(document_id TEXT,current_hash TEXT);"
            "CREATE TABLE document_versions(document_id TEXT,version_id TEXT);"
            "CREATE TABLE chunks(document_id TEXT,version_id TEXT,id TEXT,text TEXT);"
        )
        db.execute("INSERT INTO sources VALUES('notebook-a','source-a','document-a')")
        db.execute("INSERT INTO documents VALUES('document-a','file-hash')")
        db.execute("INSERT INTO document_versions VALUES('document-a','version-a')")
        db.execute("INSERT INTO chunks VALUES('document-a','version-a','chunk-a','evidence')")
    valid = {
        "notebook_id": "notebook-a",
        "source_id": "source-a",
        "document_id": "document-a",
        "version_id": "version-a",
        "evidence_id": "chunk-a",
        "source_file_sha256": "file-hash",
        "evidence_content_sha256": hashlib.sha256(b"evidence").hexdigest(),
    }
    with sqlite3.connect(database) as db:
        evaluator._verify_chunk(db, valid)
        evaluator._verify_result_identity(db, valid)
        with pytest.raises(ValueError, match="unbound"):
            evaluator._verify_chunk(db, {**valid, "version_id": "version-b"})
        with pytest.raises(PermissionError, match="no authorized"):
            evaluator._verify_result_identity(db, {**valid, "notebook_id": "notebook-b"})
