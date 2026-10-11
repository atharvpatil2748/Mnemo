"""Two-manifest rebuild; discard verified prior outputs before fresh indexing."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from mnemo.ocr_paddle import PaddleOCRConfiguration, _model_tree_hash

from mnemo_server.tools.isolated_rebuild import run_complete_canary
from mnemo_server.tools.rebuild_cleanup import (
    delete_previous_rebuilds,
    exclusive_rebuild_lock,
    inspect_previous_rebuilds,
)
from mnemo_server.tools.rebuild_integrity import verify_rebuild_integrity
from mnemo_server.tools.source_manifest import verify_source_manifest


def _profile(path: Path) -> dict[str, Any]:
    profile = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(profile, dict) or profile.get("schema") != "mnemo.rebuild-gpu-profile/1":
        raise ValueError("unsupported rebuild GPU profile")
    required = {
        "paddle_detection_dir",
        "paddle_recognition_dir",
        "paddle_detection_sha256",
        "paddle_recognition_sha256",
        "paddle_language",
        "paddle_python",
        "vision_model",
        "vision_revision",
        "clip_snapshot",
        "visual_model",
        "visual_revision",
        "bge_cache",
        "paddle_device",
        "visual_device",
        "bge_device",
    }
    if set(profile) != required | {"schema"}:
        raise ValueError("rebuild GPU profile is incomplete or has unknown fields")
    if (
        profile["paddle_device"] != "gpu:0"
        or profile["visual_device"] != "cuda"
        or profile["bge_device"] != "cuda"
    ):
        raise ValueError("two-corpus rebuild requires explicit GPU execution")
    for name in ("paddle_detection_dir", "paddle_recognition_dir", "clip_snapshot", "bge_cache"):
        if not Path(profile[name]).resolve(strict=True).is_dir():
            raise ValueError("rebuild model or runtime path is unavailable")
    if not Path(profile["paddle_python"]).resolve(strict=True).is_file():
        raise ValueError("PaddleOCR GPU interpreter is unavailable")
    recognition = Path(profile["paddle_recognition_dir"]).resolve(strict=True)
    detection = Path(profile["paddle_detection_dir"]).resolve(strict=True)
    for directory, expected in (
        (detection, profile["paddle_detection_sha256"]),
        (recognition, profile["paddle_recognition_sha256"]),
    ):
        if _model_tree_hash(directory) != expected:
            raise ValueError("PaddleOCR model tree differs from the approved profile")
    language = profile["paddle_language"]
    if language == "en" and not recognition.name.startswith("en_PP-OCRv5"):
        raise ValueError("English corpus requires its approved OCR recognition model")
    if language in {"hi", "mr"} and not recognition.name.startswith("devanagari_PP-OCRv5"):
        raise ValueError("Hindi/Marathi corpus requires its approved Devanagari model")
    PaddleOCRConfiguration(
        package_version="3.4.1",
        model_identity=f"{detection.name}+{recognition.name}",
        model_revision=f"det-{profile['paddle_detection_sha256']}+rec-{profile['paddle_recognition_sha256']}",
        detection_model_dir=detection,
        recognition_model_dir=recognition,
        detection_model_sha256=profile["paddle_detection_sha256"],
        recognition_model_sha256=profile["paddle_recognition_sha256"],
        language=language,
        ocr_version="PP-OCRv5",
        device=profile["paddle_device"],
    )
    return profile


def validate_inputs(
    *,
    manifest_a: Path,
    manifest_b: Path,
    profile_a: Path,
    profile_b: Path,
) -> tuple[tuple[dict[str, Any], dict[str, Any]], ...]:
    """Validate exactly two distinct complete inputs before any notebook is created."""
    specifications = (
        (manifest_a, profile_a, "personal_44", 44),
        (manifest_b, profile_b, "codex_downloaded_24", 24),
    )
    validated: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for manifest_path, profile_path, label, count in specifications:
        recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(recorded, dict):
            raise ValueError("source manifest must be an object")
        manifest = verify_source_manifest(
            manifest=manifest_path, corpus=Path(recorded["corpus_root"])
        )
        if manifest["label"] != label or len(manifest["sources"]) != count:
            raise ValueError("two-corpus rebuild manifest identity or count mismatch")
        validated.append((manifest, _profile(profile_path)))
    if validated[0][0]["corpus_root"] == validated[1][0]["corpus_root"]:
        raise ValueError("two-corpus rebuild inputs must be isolated")
    return tuple(validated)


def rebuild_pair_id(validated: tuple[tuple[dict[str, Any], dict[str, Any]], ...]) -> str:
    material = json.dumps(
        [(item[0]["label"], item[0]["notebook_input_identity"]) for item in validated],
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def preview_cleanup(
    *, workspace: Path, validated: tuple[tuple[dict[str, Any], dict[str, Any]], ...]
) -> list[dict[str, Any]]:
    return inspect_previous_rebuilds(
        workspace=workspace,
        manifests=(validated[0][0], validated[1][0]),
        pair_id=rebuild_pair_id(validated),
    )


def run_two_corpus_rebuild(
    *,
    workspace: Path,
    manifest_a: Path,
    manifest_b: Path,
    profile_a: Path,
    profile_b: Path,
) -> dict[str, Any]:
    """Replace only verified disposable outputs, then build two new notebooks."""
    workspace = workspace.resolve(strict=True)
    print(
        "[rebuild] validating both immutable source manifests and model profiles",
        file=sys.stderr,
        flush=True,
    )
    validated = validate_inputs(
        manifest_a=manifest_a,
        manifest_b=manifest_b,
        profile_a=profile_a,
        profile_b=profile_b,
    )
    pair_id = rebuild_pair_id(validated)
    output_root = workspace / "scratch" / "two_corpus_rebuilds"
    for path in (
        manifest_a,
        manifest_b,
        profile_a,
        profile_b,
        *(Path(item[0]["corpus_root"]) for item in validated),
    ):
        if path.resolve(strict=True).is_relative_to(output_root):
            raise ValueError("rebuild input may not be inside the disposable output root")
    outputs: list[dict[str, Any]] = []
    report_root = workspace / "scratch" / "rebuild_runs"
    report_path = report_root / f"{uuid4().hex}.json"
    report: dict[str, Any] = {
        "schema": "mnemo.two-corpus-rebuild/1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "report_path": str(report_path),
        "pair_id": pair_id,
        "inputs": [item[0]["notebook_input_identity"] for item in validated],
        "deleted_prior_rebuilds": [],
        "notebooks": outputs,
        "notebook_states": {str(item[0]["label"]): "pending" for item in validated},
        "state": "preparing",
        "build_complete": False,
        "ready_for_external_validation": False,
        "complete": False,
    }

    def persist() -> None:
        report_root.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    with exclusive_rebuild_lock(workspace):
        removed = delete_previous_rebuilds(
            workspace=workspace,
            manifests=(validated[0][0], validated[1][0]),
            pair_id=pair_id,
        )
        report["deleted_prior_rebuilds"] = removed
        report["state"] = "building"
        persist()
        for item in removed:
            print(
                f"[rebuild] REMOVED prior derived notebook {item['notebook_id']} "
                f"({item['indexed_documents']} indexed documents); runtime={item['runtime']}",
                file=sys.stderr,
                flush=True,
            )
        try:
            current_label: str | None = None
            current_stage = "not_started"
            for (manifest, profile), manifest_path in zip(
                validated, (manifest_a, manifest_b), strict=True
            ):
                current_label = str(manifest["label"])
                current_stage = "production_build"
                print(
                    f"[rebuild] START {manifest['label']} ({len(manifest['sources'])} sources)",
                    file=sys.stderr,
                    flush=True,
                )
                report["notebook_states"][str(manifest["label"])] = "building"
                persist()
                result = run_complete_canary(
                    workspace=workspace,
                    corpus=Path(manifest["corpus_root"]),
                    source_manifest=manifest_path,
                    includes=tuple(item["relative_path"] for item in manifest["sources"]),
                    paddle_detection_dir=Path(profile["paddle_detection_dir"]),
                    paddle_recognition_dir=Path(profile["paddle_recognition_dir"]),
                    paddle_detection_sha256=profile["paddle_detection_sha256"],
                    paddle_recognition_sha256=profile["paddle_recognition_sha256"],
                    paddle_language=profile["paddle_language"],
                    paddle_python=Path(profile["paddle_python"]),
                    paddle_device=profile["paddle_device"],
                    vision_model=profile["vision_model"],
                    vision_revision=profile["vision_revision"],
                    clip_snapshot=Path(profile["clip_snapshot"]),
                    visual_model=profile["visual_model"],
                    visual_revision=profile["visual_revision"],
                    visual_device=profile["visual_device"],
                    bge_cache=Path(profile["bge_cache"]),
                    bge_device=profile["bge_device"],
                    probe_query="document",
                    require_ocr_probe_hit=False,
                    perform_v2_probe=False,
                    evaluation_rebuild=True,
                    rebuild_owner={
                        "pair_id": pair_id,
                        "label": str(manifest["label"]),
                        "input_identity": str(manifest["notebook_input_identity"]),
                    },
                )
                outputs.append(result)
                complete = result.get("activation") == "complete_v2_build_ready"
                if complete:
                    current_stage = "internal_build_integrity"
                    print(
                        f"[rebuild] START {manifest['label']} internal_build_integrity",
                        file=sys.stderr,
                        flush=True,
                    )
                    integrity = verify_rebuild_integrity(
                        workspace=workspace,
                        runtime=Path(result["runtime"]),
                        source_manifest=manifest_path,
                        expected_count=len(manifest["sources"]),
                    )
                    result["build_integrity"] = integrity
                    (Path(result["runtime"]) / "build-integrity.json").write_text(
                        json.dumps(integrity, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    complete = integrity["status"] == "pass"
                    print(
                        f"[rebuild] {'DONE' if complete else 'FAILED'} "
                        f"{manifest['label']} internal_build_integrity",
                        file=sys.stderr,
                        flush=True,
                    )
                print(
                    f"[rebuild] {'DONE' if complete else 'FAILED'} {manifest['label']}; "
                    f"notebook={result.get('notebook_id')}; runtime={result.get('runtime')}",
                    file=sys.stderr,
                    flush=True,
                )
                report["state"] = "building" if complete else "failed_partial"
                report["notebook_states"][str(manifest["label"])] = (
                    "complete" if complete else "failed"
                )
                if not complete:
                    report["failure_context"] = {
                        "corpus": current_label,
                        "notebook_id": result.get("notebook_id"),
                        "stage": "production_build",
                        "operation": "complete_isolated_rebuild",
                        "error": result.get("failure", "required rebuild stage incomplete"),
                    }
                    for label, state in report["notebook_states"].items():
                        if state == "pending":
                            report["notebook_states"][label] = "skipped_due_to_pair_failure"
                persist()
                if not complete:
                    break
        except Exception as error:
            report["state"] = "failed_partial"
            report["failure"] = f"{type(error).__name__}: {error}"[-3000:]
            report["failure_context"] = {
                "corpus": current_label,
                "notebook_id": outputs[-1].get("notebook_id") if outputs else None,
                "stage": current_stage,
                "operation": "complete_isolated_rebuild"
                if current_stage == "production_build"
                else "verify_build_integrity",
                "error": report["failure"],
            }
            for label, state in report["notebook_states"].items():
                if state == "building":
                    report["notebook_states"][label] = "failed"
                elif state == "pending":
                    report["notebook_states"][label] = "skipped_due_to_pair_failure"
            persist()
            print(
                f"[rebuild] FAILED; report={report_path}; error={type(error).__name__}: {error}",
                file=sys.stderr,
                flush=True,
            )
            raise
        report["build_complete"] = len(outputs) == 2 and all(
            item.get("activation") == "complete_v2_build_ready"
            and item.get("build_integrity", {}).get("status") == "pass"
            for item in outputs
        )
        report["complete"] = report["build_complete"]
        report["ready_for_external_validation"] = report["complete"]
        report["state"] = "complete" if report["complete"] else "failed_partial"
        persist()
    print(f"[rebuild] final report: {report_path}", file=sys.stderr, flush=True)
    return report
