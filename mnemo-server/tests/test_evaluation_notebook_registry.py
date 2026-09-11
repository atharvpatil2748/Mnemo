from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from mnemo_server.evaluation.canonical_json import canonical_json_sha256_v1
from mnemo_server.evaluation.notebook_registry import (
    ServerOwnedEvaluationNotebookRegistryV1,
    resolve_evaluation_notebook_validation_candidate_v1,
)


def _digest(value: object) -> str:
    return canonical_json_sha256_v1(value)


def _write_registry(root: Path, *, store: str = "scratch/evaluation_notebooks/phase8_5") -> Path:
    target = root / "scratch/evaluation_notebooks/phase8_5"
    target.mkdir(parents=True)
    (target / "files").mkdir()
    database = target / "mnemo.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE proof(value TEXT)")
    connection.close()
    import hashlib

    database_sha = hashlib.sha256(database.read_bytes()).hexdigest()
    manifest: dict[str, object] = {
        "status": "READY",
        "notebook": {"id": "notebook-1", "store": store},
        "validation": {"database": {"sha256": database_sha}},
    }
    manifest["store_identity"] = _digest(manifest)
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    registry: dict[str, object] = {
        "selection_policy": "server-allowlisted-alias-only; no client paths",
        "notebooks": {
            "phase8_5": {
                "store": store,
                "notebook_id": "notebook-1",
                "store_identity": manifest["store_identity"],
                "manifest": "scratch/evaluation_notebooks/phase8_5/manifest.json",
            }
        },
    }
    registry["registry_digest"] = _digest(registry)
    path = root / "scratch/evaluation_notebooks/registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    return path


def test_registry_resolves_only_digest_bound_server_alias(tmp_path: Path) -> None:
    path = _write_registry(tmp_path)
    selection = ServerOwnedEvaluationNotebookRegistryV1(
        workspace_root=tmp_path, registry=path
    ).resolve("phase8_5")
    assert selection.alias == "phase8_5"
    assert (
        selection.database
        == (tmp_path / "scratch/evaluation_notebooks/phase8_5/mnemo.db").resolve()
    )


def test_registry_rejects_client_path_and_unknown_alias(tmp_path: Path) -> None:
    path = _write_registry(tmp_path)
    registry = ServerOwnedEvaluationNotebookRegistryV1(workspace_root=tmp_path, registry=path)
    with pytest.raises(PermissionError, match="server-authorized"):
        registry.resolve("../../production")


def test_registry_rejects_allowlisted_alias_redirect(tmp_path: Path) -> None:
    path = _write_registry(tmp_path, store="scratch/evaluation_notebooks/phase8_6")
    registry = ServerOwnedEvaluationNotebookRegistryV1(workspace_root=tmp_path, registry=path)
    with pytest.raises(ValueError, match="governed namespace"):
        registry.resolve("phase8_5")


def test_transport_validation_resolver_accepts_quarantine_without_serving_it(
    tmp_path: Path,
) -> None:
    path = _write_registry(tmp_path)
    manifest_path = tmp_path / "scratch/evaluation_notebooks/phase8_5/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "TRANSPORT_VALIDATION_FAILED"
    manifest.pop("store_identity")
    manifest["store_identity"] = _digest(manifest)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    registry_payload = json.loads(path.read_text(encoding="utf-8"))
    registry_payload["notebooks"] = {}
    registry_payload.pop("registry_digest")
    registry_payload["registry_digest"] = _digest(registry_payload)
    path.write_text(json.dumps(registry_payload), encoding="utf-8")

    selection = resolve_evaluation_notebook_validation_candidate_v1(
        workspace_root=tmp_path, alias="phase8_5"
    )
    assert selection.store_identity == manifest["store_identity"]
    with pytest.raises(LookupError, match="not READY"):
        ServerOwnedEvaluationNotebookRegistryV1(workspace_root=tmp_path, registry=path).resolve(
            "phase8_5"
        )
