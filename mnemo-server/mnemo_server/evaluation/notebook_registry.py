"""Server-owned allowlist for isolated evaluation notebook stores.

Clients select a stable alias.  They never submit a filesystem path, and every
serving selection is re-bound to the READY manifest and database digest created by
the reindex authority.  Post-publication validation uses a separate resolver that
can inspect a non-serving PUBLISHED or TRANSPORT_VALIDATION_FAILED candidate without
placing it in the serving registry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mnemo_server.evaluation.canonical_json import canonical_json_sha256_v1


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _digest(value: object) -> str:
    return canonical_json_sha256_v1(value)


@dataclass(frozen=True, slots=True)
class EvaluationNotebookSelectionV1:
    alias: str
    notebook_id: str
    store_identity: str
    database: Path
    blob_root: Path
    manifest: Path


class ServerOwnedEvaluationNotebookRegistryV1:
    """Resolve only reindex-authority aliases with complete integrity binding."""

    allowed_aliases = frozenset({"phase8_5", "phase8_6"})

    def __init__(self, *, workspace_root: Path, registry: Path) -> None:
        self._root = workspace_root.resolve()
        self._managed = (self._root / "scratch/evaluation_notebooks").resolve()
        self._registry = registry.resolve(strict=True)
        if self._registry != self._managed / "registry.json":
            raise ValueError("evaluation notebook registry is not server-owned")
        self._payload = self._load_object(self._registry)
        unsigned = {key: value for key, value in self._payload.items() if key != "registry_digest"}
        if self._payload.get("registry_digest") != _digest(unsigned):
            raise ValueError("evaluation notebook registry digest mismatch")
        if self._payload.get("selection_policy") != (
            "server-allowlisted-alias-only; no client paths"
        ):
            raise ValueError("evaluation notebook selection policy mismatch")

    @staticmethod
    def _load_object(path: Path) -> dict[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"{path.name} must contain a JSON object")
        return value

    def resolve(self, alias: str) -> EvaluationNotebookSelectionV1:
        if alias not in self.allowed_aliases:
            raise PermissionError("evaluation notebook alias is not server-authorized")
        raw = self._payload.get("notebooks")
        if not isinstance(raw, dict) or alias not in raw or not isinstance(raw[alias], dict):
            raise LookupError("evaluation notebook alias is not READY")
        entry = raw[alias]
        expected_store = (self._managed / alias).resolve()
        store = (self._root / str(entry["store"])).resolve()
        if store != expected_store:
            raise ValueError("evaluation notebook store escaped the governed namespace")
        manifest = (self._root / str(entry["manifest"])).resolve(strict=True)
        if manifest != expected_store / "manifest.json":
            raise ValueError("evaluation notebook manifest escaped the governed namespace")
        value = self._load_object(manifest)
        if value.get("status") != "READY":
            raise RuntimeError("evaluation notebook is not READY")
        unsigned = {key: item for key, item in value.items() if key != "store_identity"}
        if value.get("store_identity") != _digest(unsigned):
            raise ValueError("evaluation notebook store identity is invalid")
        if value.get("store_identity") != entry.get("store_identity"):
            raise ValueError("registry and notebook store identities differ")
        notebook = value.get("notebook")
        validation = value.get("validation")
        if not isinstance(notebook, dict) or not isinstance(validation, dict):
            raise ValueError("evaluation notebook manifest is incomplete")
        database_state = validation.get("database")
        if not isinstance(database_state, dict):
            raise ValueError("evaluation notebook database evidence is absent")
        database = (expected_store / "mnemo.db").resolve(strict=True)
        if _sha256(database) != database_state.get("sha256"):
            raise ValueError("evaluation notebook database digest mismatch")
        blob_root = (expected_store / "files").resolve(strict=True)
        return EvaluationNotebookSelectionV1(
            alias=alias,
            notebook_id=str(notebook["id"]),
            store_identity=str(value["store_identity"]),
            database=database,
            blob_root=blob_root,
            manifest=manifest,
        )


def resolve_evaluation_notebook_validation_candidate_v1(
    *, workspace_root: Path, alias: str
) -> EvaluationNotebookSelectionV1:
    """Resolve an allowlisted immutable candidate without exposing it for serving."""
    root = workspace_root.resolve()
    managed = (root / "scratch/evaluation_notebooks").resolve()
    if alias not in ServerOwnedEvaluationNotebookRegistryV1.allowed_aliases:
        raise PermissionError("evaluation notebook alias is not server-authorized")
    expected_store = (managed / alias).resolve(strict=True)
    manifest = (expected_store / "manifest.json").resolve(strict=True)
    value = ServerOwnedEvaluationNotebookRegistryV1._load_object(manifest)
    if value.get("status") not in {
        "PUBLISHED",
        "TRANSPORT_VALIDATION_FAILED",
        "READY",
    }:
        raise RuntimeError("evaluation notebook is not eligible for transport validation")
    unsigned = {key: item for key, item in value.items() if key != "store_identity"}
    if value.get("store_identity") != _digest(unsigned):
        raise ValueError("evaluation notebook store identity is invalid")
    notebook = value.get("notebook")
    validation = value.get("validation")
    if not isinstance(notebook, dict) or not isinstance(validation, dict):
        raise ValueError("evaluation notebook manifest is incomplete")
    if (root / str(notebook.get("store"))).resolve() != expected_store:
        raise ValueError("evaluation notebook store escaped the governed namespace")
    database_state = validation.get("database")
    if not isinstance(database_state, dict):
        raise ValueError("evaluation notebook database evidence is absent")
    database = (expected_store / "mnemo.db").resolve(strict=True)
    if _sha256(database) != database_state.get("sha256"):
        raise ValueError("evaluation notebook database digest mismatch")
    blob_root = (expected_store / "files").resolve(strict=True)
    return EvaluationNotebookSelectionV1(
        alias=alias,
        notebook_id=str(notebook["id"]),
        store_identity=str(value["store_identity"]),
        database=database,
        blob_root=blob_root,
        manifest=manifest,
    )
