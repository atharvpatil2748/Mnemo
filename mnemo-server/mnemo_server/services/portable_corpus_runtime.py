"""Read-only admission of a declared, notebook-independent corpus artifact.

This is an index admission boundary, not a retrieval/authorization service. A
READY result is local artifact readiness, never production certification.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from mnemo.corpus_identity import CorpusDeploymentIdentityV1

INDEX_PUBLICATION_SCHEMA = "mnemo.portable-corpus-index-publication/1"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def _inside(root: Path, raw: str) -> Path:
    path = Path(raw)
    unresolved = path if path.is_absolute() else root / path
    if any(
        part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction())
        for part in (unresolved, *unresolved.parents)
        if part == root or part.is_relative_to(root)
    ):
        raise ValueError("corpus runtime path contains a link or junction")
    candidate = unresolved.resolve(strict=False)
    if not candidate.is_relative_to(root):
        raise ValueError("corpus runtime path escapes its workspace")
    return candidate


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("corpus runtime document must be an object")
    return value


@dataclass(frozen=True, slots=True)
class PortableCorpusInspectionV1:
    status: Literal["UNINDEXED", "READY", "INCOMPATIBLE"]
    corpus_identity: str
    deployment_identity: str
    index_identity: str | None
    reason: str | None


def _verify_source_bytes(manifest: dict[str, Any], root: Path) -> None:
    for item in manifest["sources"]:
        relative = str(item["relative_path"])
        path = _inside(root, relative)
        if not path.is_file() or path.stat().st_size != item["byte_size"]:
            raise ValueError("source bytes are unavailable or changed")
        if _sha256(path) != item["sha256"]:
            raise ValueError("source content hash differs from manifest")


def inspect_portable_corpus_runtime(
    *, workspace: Path, declaration_path: Path, signing_key: bytes
) -> PortableCorpusInspectionV1:
    """Verify explicit sources and signed index publication without a notebook.

    The signing key is supplied by a server-owned authority, never read from
    this declaration. A missing index is an honest UNINDEXED state; malformed
    or stale published index evidence fails closed as INCOMPATIBLE.
    """
    if len(signing_key) < 32:
        raise ValueError("corpus publication signing key is too short")
    root = workspace.resolve(strict=True)
    resolved_declaration = declaration_path.resolve(strict=True)
    if not resolved_declaration.is_relative_to(root):
        raise ValueError("corpus declaration escapes its workspace")
    declaration = _json_object(resolved_declaration)
    source_manifest_path = _inside(root, str(declaration["source_manifest"])).resolve(strict=True)
    source_manifest = _json_object(source_manifest_path)
    identity = CorpusDeploymentIdentityV1.from_declaration(declaration["identity"], source_manifest)
    source_root = _inside(root, str(declaration["source_root"])).resolve(strict=True)
    _verify_source_bytes(source_manifest, source_root)
    index_path = _inside(root, str(declaration["index_publication"]))
    database = _inside(root, str(declaration["database"]))
    if not index_path.is_file() and not database.exists():
        return PortableCorpusInspectionV1(
            status="UNINDEXED",
            corpus_identity=identity.corpus_identity,
            deployment_identity=identity.deployment_identity,
            index_identity=None,
            reason="index publication and database are absent",
        )
    if not index_path.is_file() or not database.is_file():
        return PortableCorpusInspectionV1(
            status="INCOMPATIBLE",
            corpus_identity=identity.corpus_identity,
            deployment_identity=identity.deployment_identity,
            index_identity=None,
            reason="index publication and database disagree",
        )
    publication = _json_object(index_path)
    signature = publication.get("signature")
    unsigned = {key: value for key, value in publication.items() if key != "signature"}
    expected_signature = hmac.new(
        signing_key,
        b"mnemo.portable-corpus-publication/1\0" + _canonical(unsigned),
        hashlib.sha256,
    ).hexdigest()
    if (
        publication.get("schema") != INDEX_PUBLICATION_SCHEMA
        or not isinstance(signature, str)
        or not hmac.compare_digest(signature, expected_signature)
    ):
        raise ValueError("corpus index publication signature is invalid")
    if publication.get("deployment_identity") != identity.deployment_identity:
        raise ValueError("corpus deployment identity is incompatible")
    generations = publication.get("generations")
    if not isinstance(generations, list) or not generations:
        raise ValueError("published generations are missing")
    generation_digests: dict[str, str] = {}
    generation_ids: set[str] = set()
    for item in generations:
        if not isinstance(item, dict):
            raise ValueError("published generation is malformed")
        capability = str(item["capability"])
        generation_id = str(item["generation_id"])
        if capability in generation_digests or generation_id in generation_ids:
            raise ValueError("published generations are duplicated")
        generation_digests[capability] = _digest(item)
        generation_ids.add(generation_id)
    index_identity = identity.index_identity(generation_digests)
    if publication.get("index_identity") != index_identity:
        raise ValueError("published index identity is incompatible")
    if _sha256(database) != publication.get("database_sha256"):
        raise ValueError("published database hash is incompatible")
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(database) + suffix)
        if sidecar.exists() and sidecar.stat().st_size:
            raise ValueError("published database has an unverified SQLite sidecar")
    connection = sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        for item in generations:
            row = connection.execute(
                "SELECT capability,checksum,state FROM index_generations WHERE generation_id=?",
                (str(item["generation_id"]),),
            ).fetchone()
            if row != (str(item["capability"]), str(item["checksum"]), "ready"):
                raise ValueError("published generation does not match stored READY state")
            active = connection.execute(
                "SELECT 1 FROM active_index_generations WHERE generation_id=?",
                (str(item["generation_id"]),),
            ).fetchone()
            if active is None:
                raise ValueError("published generation is not active")
    finally:
        connection.close()
    return PortableCorpusInspectionV1(
        status="READY",
        corpus_identity=identity.corpus_identity,
        deployment_identity=identity.deployment_identity,
        index_identity=index_identity,
        reason=None,
    )
