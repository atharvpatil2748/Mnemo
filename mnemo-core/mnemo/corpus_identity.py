"""Portable corpus/index identity for a declared production deployment.

This module computes identities only. It does not publish an index, authorize a
principal, or replace the certified runtime binding.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

SOURCE_SCHEMA = "mnemo.rebuild-source-manifest/1"
DEPLOYMENT_SCHEMA = "mnemo.corpus-deployment-identity/1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _require_digest(value: str, name: str) -> None:
    if _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


def source_manifest_identity(raw: dict[str, Any]) -> str:
    """Verify the source-list digest without incorporating an absolute corpus path.

    Byte verification is a separate rebuild preflight responsibility. A caller
    must perform it before using this identity to admit an index.
    """
    if raw.get("schema") != SOURCE_SCHEMA:
        raise ValueError("unsupported source manifest schema")
    sources = raw.get("sources")
    expected = raw.get("expected_count")
    if not isinstance(sources, list) or not sources or type(expected) is not int:
        raise ValueError("source manifest is incomplete")
    if len(sources) != expected:
        raise ValueError("source count differs from manifest")
    paths: set[str] = set()
    for item in sources:
        if not isinstance(item, dict):
            raise ValueError("source entry is invalid")
        path = item.get("relative_path")
        if not isinstance(path, str) or not path:
            raise ValueError("source path is not relative")
        pure = PurePosixPath(path)
        if (
            pure.is_absolute()
            or pure.as_posix() != path
            or any(part in {".", ".."} for part in path.split("/"))
            or ":" in path
            or "\\" in path
            or path in paths
        ):
            raise ValueError("source paths must be unique and normalized")
        paths.add(path)
        content_hash = item.get("sha256")
        if not isinstance(content_hash, str):
            raise ValueError("source hash is missing")
        _require_digest(content_hash, "source hash")
        if type(item.get("byte_size")) is not int or item["byte_size"] < 0:
            raise ValueError("source byte size is invalid")
    if [item["relative_path"] for item in sources] != sorted(paths):
        raise ValueError("source ordering is not deterministic")
    identity = _digest(sources)
    if raw.get("notebook_input_identity") != identity:
        raise ValueError("source manifest identity differs from source entries")
    return identity


@dataclass(frozen=True, slots=True)
class CorpusDeploymentIdentityV1:
    """No machine path, notebook UUID, run UUID, or active alias in the envelope."""

    deployment_key: str
    source_manifest_digest: str
    profile_fingerprint: str
    parser_digest: str
    retrieval_policy_digest: str
    storage_schema_version: int
    capability_digests: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", self.deployment_key):
            raise ValueError("deployment key is invalid")
        for value, name in (
            (self.source_manifest_digest, "source_manifest_digest"),
            (self.profile_fingerprint, "profile_fingerprint"),
            (self.parser_digest, "parser_digest"),
            (self.retrieval_policy_digest, "retrieval_policy_digest"),
        ):
            _require_digest(value, name)
        if self.storage_schema_version < 1:
            raise ValueError("storage schema version must be positive")
        names = [name for name, _ in self.capability_digests]
        if not names or names != sorted(set(names)):
            raise ValueError("capability names must be unique and sorted")
        for name, digest in self.capability_digests:
            if not re.fullmatch(r"[a-z][a-z0-9_-]*", name):
                raise ValueError("capability name is invalid")
            _require_digest(digest, "capability digest")

    @classmethod
    def from_declaration(
        cls, declaration: dict[str, Any], source_manifest: dict[str, Any]
    ) -> CorpusDeploymentIdentityV1:
        if declaration.get("schema") != DEPLOYMENT_SCHEMA:
            raise ValueError("unsupported deployment identity schema")
        capability_raw = declaration.get("capability_digests")
        if not isinstance(capability_raw, dict):
            raise ValueError("capability digests are missing")
        source_identity = source_manifest_identity(source_manifest)
        if declaration.get("source_manifest_digest") != source_identity:
            raise ValueError("configured source manifest differs from verified inventory")
        return cls(
            deployment_key=str(declaration["deployment_key"]),
            source_manifest_digest=source_identity,
            profile_fingerprint=str(declaration["profile_fingerprint"]),
            parser_digest=str(declaration["parser_digest"]),
            retrieval_policy_digest=str(declaration["retrieval_policy_digest"]),
            storage_schema_version=int(declaration["storage_schema_version"]),
            capability_digests=tuple(sorted((str(k), str(v)) for k, v in capability_raw.items())),
        )

    @property
    def corpus_identity(self) -> str:
        return _digest(
            {"schema": DEPLOYMENT_SCHEMA, "source_manifest_digest": self.source_manifest_digest}
        )

    @property
    def deployment_identity(self) -> str:
        return _digest(
            {
                "schema": DEPLOYMENT_SCHEMA,
                "deployment_key": self.deployment_key,
                "corpus_identity": self.corpus_identity,
                "profile_fingerprint": self.profile_fingerprint,
                "parser_digest": self.parser_digest,
                "retrieval_policy_digest": self.retrieval_policy_digest,
                "storage_schema_version": self.storage_schema_version,
                "capability_digests": self.capability_digests,
            }
        )

    def index_identity(self, generation_digests: dict[str, str]) -> str:
        """Bind an index to exact generation evidence, independent of its path."""
        if not generation_digests:
            raise ValueError("index generation evidence is missing")
        for digest in generation_digests.values():
            _require_digest(digest, "generation digest")
        if set(generation_digests) != {name for name, _ in self.capability_digests}:
            raise ValueError("index generation capability set differs from deployment")
        return _digest(
            {
                "schema": DEPLOYMENT_SCHEMA,
                "deployment_identity": self.deployment_identity,
                "generation_digests": sorted(generation_digests.items()),
            }
        )

    @staticmethod
    def file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for part in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(part)
        return digest.hexdigest()
