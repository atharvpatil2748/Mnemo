"""A portable index admission check has no historical notebook prerequisite."""

import hashlib
import hmac
import json
import sqlite3
from pathlib import Path
from typing import Any, cast

import pytest
from mnemo.corpus_identity import CorpusDeploymentIdentityV1
from mnemo_server.services.portable_corpus_runtime import (
    INDEX_PUBLICATION_SCHEMA,
    inspect_portable_corpus_runtime,
)

_KEY = b"fixture-only-key-with-more-than-32-bytes"


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _write_fixture(root: Path) -> tuple[Path, CorpusDeploymentIdentityV1]:
    sources = root / "sources"
    sources.mkdir(parents=True)
    (sources / "a.txt").write_bytes(b"source")
    rows = [
        {
            "relative_path": "a.txt",
            "filename": "a.txt",
            "file_type": ".txt",
            "byte_size": 6,
            "sha256": hashlib.sha256(b"source").hexdigest(),
        }
    ]
    manifest = {
        "schema": "mnemo.rebuild-source-manifest/1",
        "expected_count": 1,
        "notebook_input_identity": _digest(rows),
        "sources": rows,
    }
    (root / "sources.json").write_text(json.dumps(manifest), encoding="utf-8")
    declaration = {
        "source_manifest": "sources.json",
        "source_root": "sources",
        "index_publication": "index.json",
        "database": "index.db",
        "identity": {
            "schema": "mnemo.corpus-deployment-identity/1",
            "deployment_key": "personal",
            "source_manifest_digest": _digest(rows),
            "profile_fingerprint": _digest("profile"),
            "parser_digest": _digest("parser"),
            "retrieval_policy_digest": _digest("retrieval"),
            "storage_schema_version": 16,
            "capability_digests": {"canonical": _digest("canonical")},
        },
    }
    path = root / "deployment.json"
    path.write_text(json.dumps(declaration), encoding="utf-8")
    identity = CorpusDeploymentIdentityV1.from_declaration(
        cast(dict[str, Any], declaration["identity"]), manifest
    )
    return path, identity


def _publish(root: Path, identity: CorpusDeploymentIdentityV1) -> None:
    database = root / "index.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        "CREATE TABLE index_generations(generation_id TEXT,capability TEXT,"
        "checksum TEXT,state TEXT);"
        "CREATE TABLE active_index_generations(generation_id TEXT);"
    )
    checksum = _digest("generation")
    connection.execute(
        "INSERT INTO index_generations VALUES(?,?,?,?)",
        ("generation-1", "canonical", checksum, "ready"),
    )
    connection.execute("INSERT INTO active_index_generations VALUES(?)", ("generation-1",))
    connection.commit()
    connection.close()
    generation = {
        "capability": "canonical",
        "generation_id": "generation-1",
        "checksum": checksum,
    }
    publication = {
        "schema": INDEX_PUBLICATION_SCHEMA,
        "deployment_identity": identity.deployment_identity,
        "index_identity": identity.index_identity({"canonical": _digest(generation)}),
        "database_sha256": hashlib.sha256(database.read_bytes()).hexdigest(),
        "generations": [generation],
    }
    signature = hmac.new(
        _KEY,
        b"mnemo.portable-corpus-publication/1\0"
        + json.dumps(
            publication, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode(),
        hashlib.sha256,
    ).hexdigest()
    publication["signature"] = signature
    (root / "index.json").write_text(json.dumps(publication), encoding="utf-8")


def _resign_publication(root: Path, publication: dict[str, Any]) -> None:
    """Sign only disposable fixture evidence after deliberately changing it."""
    unsigned = {key: value for key, value in publication.items() if key != "signature"}
    publication["signature"] = hmac.new(
        _KEY,
        b"mnemo.portable-corpus-publication/1\0"
        + json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(),
        hashlib.sha256,
    ).hexdigest()
    (root / "index.json").write_text(json.dumps(publication), encoding="utf-8")


def test_empty_workspace_is_unindexed_without_notebook(tmp_path: Path) -> None:
    declaration, identity = _write_fixture(tmp_path)
    status = inspect_portable_corpus_runtime(
        workspace=tmp_path, declaration_path=declaration, signing_key=_KEY
    )
    assert status.status == "UNINDEXED"
    assert status.corpus_identity == identity.corpus_identity
    assert not (tmp_path / "index.db").exists()


def test_signed_index_is_ready_without_notebook(tmp_path: Path) -> None:
    declaration, identity = _write_fixture(tmp_path)
    _publish(tmp_path, identity)
    status = inspect_portable_corpus_runtime(
        workspace=tmp_path, declaration_path=declaration, signing_key=_KEY
    )
    assert status.status == "READY"
    assert status.index_identity == identity.index_identity(
        {
            "canonical": _digest(
                {
                    "capability": "canonical",
                    "generation_id": "generation-1",
                    "checksum": _digest("generation"),
                }
            )
        }
    )


def test_same_inputs_have_same_identity_in_distinct_workspaces(tmp_path: Path) -> None:
    inspections = []
    for name in ("machine-a", "machine-b"):
        root = tmp_path / name
        root.mkdir()
        declaration, identity = _write_fixture(root)
        _publish(root, identity)
        inspections.append(
            inspect_portable_corpus_runtime(
                workspace=root, declaration_path=declaration, signing_key=_KEY
            )
        )
    assert inspections[0].status == inspections[1].status == "READY"
    assert inspections[0].corpus_identity == inspections[1].corpus_identity
    assert inspections[0].deployment_identity == inspections[1].deployment_identity
    assert inspections[0].index_identity == inspections[1].index_identity


def test_changed_source_or_tampered_publication_rejected(tmp_path: Path) -> None:
    declaration, identity = _write_fixture(tmp_path)
    _publish(tmp_path, identity)
    (tmp_path / "sources" / "a.txt").write_bytes(b"other!")
    with pytest.raises(ValueError, match="source content hash"):
        inspect_portable_corpus_runtime(
            workspace=tmp_path, declaration_path=declaration, signing_key=_KEY
        )
    (tmp_path / "sources" / "a.txt").write_bytes(b"source")
    published = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    published["database_sha256"] = "0" * 64
    (tmp_path / "index.json").write_text(json.dumps(published), encoding="utf-8")
    with pytest.raises(ValueError, match="signature"):
        inspect_portable_corpus_runtime(
            workspace=tmp_path, declaration_path=declaration, signing_key=_KEY
        )


def test_inactive_generation_is_not_ready(tmp_path: Path) -> None:
    declaration, identity = _write_fixture(tmp_path)
    _publish(tmp_path, identity)
    database = tmp_path / "index.db"
    connection = sqlite3.connect(database)
    connection.execute("DELETE FROM active_index_generations")
    connection.commit()
    connection.close()
    # The physical hash is checked before activation state; the stale signed
    # publication must be rejected rather than silently serving the old index.
    with pytest.raises(ValueError, match="database hash"):
        inspect_portable_corpus_runtime(
            workspace=tmp_path, declaration_path=declaration, signing_key=_KEY
        )


@pytest.mark.parametrize("present", ["publication", "database"])
def test_partial_publication_is_incompatible(tmp_path: Path, present: str) -> None:
    declaration, identity = _write_fixture(tmp_path)
    _publish(tmp_path, identity)
    (tmp_path / ("index.db" if present == "publication" else "index.json")).unlink()
    result = inspect_portable_corpus_runtime(
        workspace=tmp_path, declaration_path=declaration, signing_key=_KEY
    )
    assert result.status == "INCOMPATIBLE"
    assert result.index_identity is None
    assert result.reason == "index publication and database disagree"


def test_runtime_rejects_short_key_and_missing_source(tmp_path: Path) -> None:
    declaration, _ = _write_fixture(tmp_path)
    with pytest.raises(ValueError, match="signing key is too short"):
        inspect_portable_corpus_runtime(
            workspace=tmp_path, declaration_path=declaration, signing_key=b"short"
        )
    (tmp_path / "sources" / "a.txt").unlink()
    with pytest.raises(ValueError, match="source bytes are unavailable"):
        inspect_portable_corpus_runtime(
            workspace=tmp_path, declaration_path=declaration, signing_key=_KEY
        )


@pytest.mark.parametrize(
    ("field", "replacement", "error"),
    [
        ("schema", "unknown", "signature"),
        ("deployment_identity", "0" * 64, "deployment identity"),
        ("generations", [], "generations are missing"),
        ("index_identity", "0" * 64, "index identity"),
        ("database_sha256", "0" * 64, "database hash"),
    ],
)
def test_signed_publication_rejects_incompatible_evidence(
    tmp_path: Path, field: str, replacement: object, error: str
) -> None:
    declaration, identity = _write_fixture(tmp_path)
    _publish(tmp_path, identity)
    publication = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    publication[field] = replacement
    _resign_publication(tmp_path, publication)
    with pytest.raises(ValueError, match=error):
        inspect_portable_corpus_runtime(
            workspace=tmp_path, declaration_path=declaration, signing_key=_KEY
        )


@pytest.mark.parametrize("defect", ["malformed", "duplicate-capability", "duplicate-id"])
def test_signed_publication_rejects_bad_generation_inventory(tmp_path: Path, defect: str) -> None:
    declaration, identity = _write_fixture(tmp_path)
    _publish(tmp_path, identity)
    publication = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    generation = publication["generations"][0]
    if defect == "malformed":
        publication["generations"] = ["not-a-generation"]
        error = "generation is malformed"
    else:
        duplicate = dict(generation)
        if defect == "duplicate-capability":
            duplicate["generation_id"] = "generation-2"
        else:
            duplicate["capability"] = "ocr"
        publication["generations"].append(duplicate)
        error = "generations are duplicated"
    _resign_publication(tmp_path, publication)
    with pytest.raises(ValueError, match=error):
        inspect_portable_corpus_runtime(
            workspace=tmp_path, declaration_path=declaration, signing_key=_KEY
        )


@pytest.mark.parametrize("stored_change", ["inactive", "not-ready", "checksum"])
def test_published_generation_must_match_active_ready_storage(
    tmp_path: Path, stored_change: str
) -> None:
    declaration, identity = _write_fixture(tmp_path)
    _publish(tmp_path, identity)
    database = tmp_path / "index.db"
    with sqlite3.connect(database) as connection:
        if stored_change == "inactive":
            connection.execute("DELETE FROM active_index_generations")
        elif stored_change == "not-ready":
            connection.execute("UPDATE index_generations SET state='building'")
        else:
            connection.execute("UPDATE index_generations SET checksum='changed'")
    publication = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    publication["database_sha256"] = hashlib.sha256(database.read_bytes()).hexdigest()
    _resign_publication(tmp_path, publication)
    error = "not active" if stored_change == "inactive" else "READY state"
    with pytest.raises(ValueError, match=error):
        inspect_portable_corpus_runtime(
            workspace=tmp_path, declaration_path=declaration, signing_key=_KEY
        )


def test_published_database_with_unverified_sidecar_is_rejected(tmp_path: Path) -> None:
    declaration, identity = _write_fixture(tmp_path)
    _publish(tmp_path, identity)
    (tmp_path / "index.db-wal").write_bytes(b"unverified fixture sidecar")
    with pytest.raises(ValueError, match="unverified SQLite sidecar"):
        inspect_portable_corpus_runtime(
            workspace=tmp_path, declaration_path=declaration, signing_key=_KEY
        )


def test_declaration_cannot_escape_workspace_or_be_non_object(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside, _ = _write_fixture(tmp_path)
    with pytest.raises(ValueError, match="declaration escapes"):
        inspect_portable_corpus_runtime(
            workspace=workspace, declaration_path=outside, signing_key=_KEY
        )
    declaration = workspace / "deployment.json"
    declaration.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be an object"):
        inspect_portable_corpus_runtime(
            workspace=workspace, declaration_path=declaration, signing_key=_KEY
        )


def test_declaration_cannot_select_source_manifest_outside_workspace(tmp_path: Path) -> None:
    declaration, _ = _write_fixture(tmp_path)
    payload = json.loads(declaration.read_text(encoding="utf-8"))
    payload["source_manifest"] = "../outside.json"
    declaration.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="path escapes"):
        inspect_portable_corpus_runtime(
            workspace=tmp_path, declaration_path=declaration, signing_key=_KEY
        )


def test_changed_source_size_is_rejected_before_index_admission(tmp_path: Path) -> None:
    declaration, _ = _write_fixture(tmp_path)
    (tmp_path / "sources" / "a.txt").write_bytes(b"longer source")
    with pytest.raises(ValueError, match="source bytes are unavailable or changed"):
        inspect_portable_corpus_runtime(
            workspace=tmp_path, declaration_path=declaration, signing_key=_KEY
        )
