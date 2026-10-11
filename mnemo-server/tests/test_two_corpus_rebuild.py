"""No historical database is needed to validate or dispatch two source manifests."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest
from mnemo.ocr_paddle import _model_tree_hash
from mnemo_server.tools import two_corpus_rebuild
from mnemo_server.tools.rebuild_cleanup import delete_previous_rebuilds
from mnemo_server.tools.source_manifest import build_source_manifest

from scripts import phase8_5_11_derived_pipeline as derived_pipeline


def test_wmp_ocr_rasterization_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(derived_pipeline, "_to_raster_bytes", lambda _raw, _mime: b"not-png")
    with pytest.raises(RuntimeError, match="rasterization failed"):
        derived_pipeline._wmp_to_png_for_ocr(b"original-wmp")
    monkeypatch.setattr(
        derived_pipeline,
        "_to_raster_bytes",
        lambda _raw, _mime: b"\x89PNG\r\n\x1a\nconverted",
    )
    assert derived_pipeline._wmp_to_png_for_ocr(b"original-wmp").endswith(b"converted")


def test_two_corpus_preflight_and_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifests: list[Path] = []
    profiles: list[Path] = []
    for label, count in (("personal_44", 44), ("codex_downloaded_24", 24)):
        corpus = tmp_path / label
        corpus.mkdir()
        for index in range(count):
            (corpus / f"{index:02d}.txt").write_text(f"{label}:{index}", encoding="utf-8")
        manifest = tmp_path / f"{label}.json"
        manifest.write_text(
            json.dumps(build_source_manifest(corpus=corpus, label=label, expected_count=count)),
            encoding="utf-8",
        )
        manifests.append(manifest)
        detection = tmp_path / "PP-OCRv5_server_det"
        recognition = tmp_path / (
            "en_PP-OCRv5_mobile_rec" if label == "personal_44" else "devanagari_PP-OCRv5_mobile_rec"
        )
        for directory in (detection, recognition):
            directory.mkdir(exist_ok=True)
            (directory / "model.bin").write_bytes(directory.name.encode())
        profile = {
            "schema": "mnemo.rebuild-gpu-profile/1",
            "paddle_detection_dir": str(detection),
            "paddle_recognition_dir": str(recognition),
            "paddle_detection_sha256": _model_tree_hash(detection),
            "paddle_recognition_sha256": _model_tree_hash(recognition),
            "paddle_language": "en" if label == "personal_44" else "hi",
            "paddle_python": sys.executable,
            "vision_model": "vision",
            "vision_revision": "revision",
            "clip_snapshot": str(tmp_path),
            "visual_model": "clip",
            "visual_revision": "revision",
            "bge_cache": str(tmp_path),
            "paddle_device": "gpu:0",
            "visual_device": "cuda",
            "bge_device": "cuda",
        }
        profile_path = tmp_path / f"{label}.profile.json"
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        profiles.append(profile_path)
    source_hash = json.loads(manifests[0].read_text(encoding="utf-8"))["sources"][0]["sha256"]
    partial_root = tmp_path / "scratch" / "two_corpus_rebuilds"
    partial_root.mkdir(parents=True)
    old_partial = _partial_runtime(partial_root, "d" * 32, source_hash)
    checked = two_corpus_rebuild.validate_inputs(
        manifest_a=manifests[0],
        manifest_b=manifests[1],
        profile_a=profiles[0],
        profile_b=profiles[1],
    )
    assert len(two_corpus_rebuild.preview_cleanup(workspace=tmp_path, validated=checked)) == 1
    assert old_partial.exists()
    calls: list[dict[str, object]] = []

    def complete(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "activation": "complete_v2_build_ready",
            "notebook_id": str(len(calls)),
            "runtime": str(tmp_path),
        }

    monkeypatch.setattr(two_corpus_rebuild, "run_complete_canary", complete)
    monkeypatch.setattr(
        two_corpus_rebuild,
        "verify_rebuild_integrity",
        lambda **_: {"status": "pass"},
    )
    result = two_corpus_rebuild.run_two_corpus_rebuild(
        workspace=tmp_path,
        manifest_a=manifests[0],
        manifest_b=manifests[1],
        profile_a=profiles[0],
        profile_b=profiles[1],
    )
    assert result["build_complete"] is True
    assert result["complete"] is True
    assert result["ready_for_external_validation"] is True
    assert result["state"] == "complete"
    assert not old_partial.exists()
    assert len(result["deleted_prior_rebuilds"]) == 1
    assert len(calls) == 2
    assert "source_database" not in calls[0]
    assert calls[0]["source_manifest"] == manifests[0]
    assert len(calls[0]["includes"]) == 44
    assert calls[1]["source_manifest"] == manifests[1]
    assert len(calls[1]["includes"]) == 24
    assert calls[0]["paddle_device"] == "gpu:0"
    assert calls[0]["perform_v2_probe"] is False
    assert calls[0]["evaluation_rebuild"] is True
    assert calls[0]["rebuild_owner"]["label"] == "personal_44"
    assert len(list((tmp_path / "scratch" / "rebuild_runs").glob("*.json"))) == 1
    assert Path(result["report_path"]).is_file()


def test_pair_report_never_completes_after_first_notebook_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifests: list[Path] = []
    profiles: list[Path] = []
    for label, count in (("personal_44", 44), ("codex_downloaded_24", 24)):
        corpus = tmp_path / label
        corpus.mkdir()
        for index in range(count):
            (corpus / f"{index}.txt").write_text(f"{label}-{index}", encoding="utf-8")
        manifest = tmp_path / f"{label}.json"
        manifest.write_text(
            json.dumps(build_source_manifest(corpus=corpus, label=label, expected_count=count)),
            encoding="utf-8",
        )
        manifests.append(manifest)
        profile = tmp_path / f"{label}.profile.json"
        profile.write_text("{}", encoding="utf-8")
        profiles.append(profile)
    monkeypatch.setattr(
        two_corpus_rebuild,
        "validate_inputs",
        lambda **_: tuple(
            (
                json.loads(manifest.read_text(encoding="utf-8")),
                {
                    "paddle_detection_dir": str(tmp_path),
                    "paddle_recognition_dir": str(tmp_path),
                    "paddle_detection_sha256": "a" * 64,
                    "paddle_recognition_sha256": "b" * 64,
                    "paddle_language": "en",
                    "paddle_python": sys.executable,
                    "paddle_device": "gpu:0",
                    "vision_model": "vision",
                    "vision_revision": "revision",
                    "clip_snapshot": str(tmp_path),
                    "visual_model": "clip",
                    "visual_revision": "revision",
                    "visual_device": "cuda",
                    "bge_cache": str(tmp_path),
                    "bge_device": "cuda",
                },
            )
            for manifest in manifests
        ),
    )
    calls = 0

    def incomplete(**_: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"activation": "inactive", "notebook_id": "partial"}

    monkeypatch.setattr(two_corpus_rebuild, "run_complete_canary", incomplete)
    result = two_corpus_rebuild.run_two_corpus_rebuild(
        workspace=tmp_path,
        manifest_a=manifests[0],
        manifest_b=manifests[1],
        profile_a=profiles[0],
        profile_b=profiles[1],
    )
    assert calls == 1
    assert result["complete"] is False
    assert result["ready_for_external_validation"] is False
    assert result["state"] == "failed_partial"
    assert result["notebook_states"] == {
        "personal_44": "failed",
        "codex_downloaded_24": "skipped_due_to_pair_failure",
    }
    assert len(result["notebooks"]) == 1
    assert json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))["complete"] is False


def test_integrity_failure_prevents_second_notebook_and_pair_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifests: list[Path] = []
    for label, count in (("personal_44", 44), ("codex_downloaded_24", 24)):
        corpus = tmp_path / label
        corpus.mkdir()
        for index in range(count):
            (corpus / f"{index}.txt").write_text(f"{label}-{index}", encoding="utf-8")
        manifest = tmp_path / f"{label}.json"
        manifest.write_text(
            json.dumps(build_source_manifest(corpus=corpus, label=label, expected_count=count)),
            encoding="utf-8",
        )
        manifests.append(manifest)
    profile = {
        key: str(tmp_path)
        for key in (
            "paddle_detection_dir",
            "paddle_recognition_dir",
            "paddle_detection_sha256",
            "paddle_recognition_sha256",
            "paddle_language",
            "paddle_python",
            "paddle_device",
            "vision_model",
            "vision_revision",
            "clip_snapshot",
            "visual_model",
            "visual_revision",
            "visual_device",
            "bge_cache",
            "bge_device",
        )
    }
    monkeypatch.setattr(
        two_corpus_rebuild,
        "validate_inputs",
        lambda **_: tuple(
            (json.loads(manifest.read_text(encoding="utf-8")), profile) for manifest in manifests
        ),
    )
    calls = 0

    def built(**_: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {
            "activation": "complete_v2_build_ready",
            "notebook_id": "disposable",
            "runtime": str(tmp_path),
        }

    monkeypatch.setattr(two_corpus_rebuild, "run_complete_canary", built)
    monkeypatch.setattr(
        two_corpus_rebuild,
        "verify_rebuild_integrity",
        lambda **_: (_ for _ in ()).throw(ValueError("missing OCR projection")),
    )
    with pytest.raises(ValueError, match="missing OCR projection"):
        two_corpus_rebuild.run_two_corpus_rebuild(
            workspace=tmp_path,
            manifest_a=manifests[0],
            manifest_b=manifests[1],
            profile_a=tmp_path,
            profile_b=tmp_path,
        )
    assert calls == 1
    reports = list((tmp_path / "scratch" / "rebuild_runs").glob("*.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert report["complete"] is False
    assert report["notebook_states"] == {
        "personal_44": "failed",
        "codex_downloaded_24": "skipped_due_to_pair_failure",
    }


def test_profile_rejects_cpu_fallback(tmp_path: Path) -> None:
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"schema": "mnemo.rebuild-gpu-profile/1"}), encoding="utf-8")
    with pytest.raises(ValueError, match="incomplete"):
        two_corpus_rebuild._profile(profile)


def _partial_runtime(root: Path, run_id: str, source_hash: str) -> Path:
    runtime = root / run_id
    runtime.mkdir()
    notebook = str(uuid5(NAMESPACE_URL, f"mnemo:evaluation-rebuild:{run_id}"))
    connection = sqlite3.connect(runtime / "mnemo.db")
    try:
        connection.execute("CREATE TABLE notebooks(notebook_id TEXT,title TEXT)")
        connection.execute("CREATE TABLE documents(current_hash TEXT)")
        connection.execute(
            "INSERT INTO notebooks VALUES(?,?)", (notebook, f"Evaluation rebuild {run_id}")
        )
        connection.execute("INSERT INTO documents VALUES(?)", (source_hash,))
        connection.commit()
    finally:
        connection.close()
    (runtime / "partial.log").write_text("derived only", encoding="utf-8")
    return runtime


def test_destructive_rebuild_removes_only_verified_partial_outputs(tmp_path: Path) -> None:
    root = tmp_path / "scratch" / "two_corpus_rebuilds"
    root.mkdir(parents=True)
    source = tmp_path / "original.txt"
    source.write_text("immutable original", encoding="utf-8")
    first = _partial_runtime(root, "a" * 32, "1" * 64)
    second = _partial_runtime(root, "b" * 32, "2" * 64)
    manifests = (
        {"label": "personal_44", "notebook_input_identity": "a", "sources": [{"sha256": "1" * 64}]},
        {
            "label": "codex_downloaded_24",
            "notebook_input_identity": "b",
            "sources": [{"sha256": "2" * 64}],
        },
    )
    removed = delete_previous_rebuilds(workspace=tmp_path, manifests=manifests, pair_id="pair")
    assert {item["indexed_documents"] for item in removed} == {1}
    assert not first.exists() and not second.exists()
    assert source.read_text(encoding="utf-8") == "immutable original"


def test_destructive_rebuild_rejects_ambiguous_target_before_any_deletion(tmp_path: Path) -> None:
    root = tmp_path / "scratch" / "two_corpus_rebuilds"
    root.mkdir(parents=True)
    safe = _partial_runtime(root, "a" * 32, "1" * 64)
    foreign = _partial_runtime(root, "b" * 32, "9" * 64)
    manifests = (
        {"label": "personal_44", "notebook_input_identity": "a", "sources": [{"sha256": "1" * 64}]},
        {
            "label": "codex_downloaded_24",
            "notebook_input_identity": "b",
            "sources": [{"sha256": "2" * 64}],
        },
    )
    with pytest.raises(RuntimeError, match="out-of-scope"):
        delete_previous_rebuilds(workspace=tmp_path, manifests=manifests, pair_id="pair")
    assert safe.exists() and foreign.exists()


def test_owned_interrupted_rebuild_without_database_is_removable(tmp_path: Path) -> None:
    root = tmp_path / "scratch" / "two_corpus_rebuilds"
    runtime = root / ("c" * 32)
    runtime.mkdir(parents=True)
    notebook = str(uuid5(NAMESPACE_URL, f"mnemo:evaluation-rebuild:{runtime.name}"))
    (runtime / "rebuild-owner.json").write_text(
        json.dumps(
            {
                "schema": "mnemo.two-corpus-rebuild-owner/1",
                "run_id": runtime.name,
                "notebook_id": notebook,
                "pair_id": "pair",
                "label": "personal_44",
                "input_identity": "a",
            }
        ),
        encoding="utf-8",
    )
    manifests = (
        {"label": "personal_44", "notebook_input_identity": "a", "sources": [{"sha256": "1" * 64}]},
        {
            "label": "codex_downloaded_24",
            "notebook_input_identity": "b",
            "sources": [{"sha256": "2" * 64}],
        },
    )
    assert (
        len(delete_previous_rebuilds(workspace=tmp_path, manifests=manifests, pair_id="pair")) == 1
    )
    assert not runtime.exists()
