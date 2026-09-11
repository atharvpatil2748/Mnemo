"""Canonical logical identity and read-only verification for a V2 database build artifact."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from mnemo.models._shared import require_non_empty, require_sha256

V2_DATABASE_ARTIFACT_IDENTITY_SCHEMA = "mnemo.v2-database-artifact-identity/1"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True, slots=True, kw_only=True)
class V2GenerationArtifactIdentityV1:
    capability: str
    generation_id: UUID
    checksum: str
    source_generation_ids: tuple[UUID, ...]
    provider_identity: str | None
    model_identity: str | None
    configuration_digest: str
    vector_space_identity: str | None
    dimensions: int | None

    def __post_init__(self) -> None:
        require_non_empty(self.capability, "capability")
        require_sha256(self.checksum, "checksum")
        require_sha256(self.configuration_digest, "configuration_digest")
        if self.vector_space_identity is not None:
            require_sha256(self.vector_space_identity, "vector_space_identity")
        if len(set(self.source_generation_ids)) != len(self.source_generation_ids):
            raise ValueError("source generation identities must be unique")
        if self.dimensions is not None and self.dimensions < 1:
            raise ValueError("generation dimensions must be positive")

    def payload(self) -> dict[str, object]:
        return {
            "capability": self.capability,
            "generation_id": str(self.generation_id),
            "checksum": self.checksum,
            "source_generation_ids": [str(value) for value in self.source_generation_ids],
            "provider_identity": self.provider_identity,
            "model_identity": self.model_identity,
            "configuration_digest": self.configuration_digest,
            "vector_space_identity": self.vector_space_identity,
            "dimensions": self.dimensions,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class V2DatabaseArtifactIdentityV1:
    """Identity of immutable build evidence, excluding mutable alias/runtime tables."""

    database_id: UUID
    target_path: str
    build_run_id: UUID
    corpus_digest: str
    census_digest: str
    profile_fingerprint: str
    vector_space_identity: str
    build_manifest_digest: str
    storage_manifest_digest: str
    generations: tuple[V2GenerationArtifactIdentityV1, ...]
    database_identity: str
    schema_version: str = V2_DATABASE_ARTIFACT_IDENTITY_SCHEMA

    def __post_init__(self) -> None:
        normalized = PurePosixPath(self.target_path).as_posix()
        if normalized != self.target_path or normalized.startswith("../"):
            raise ValueError("target_path must be a normalized repository-relative path")
        for value, name in (
            (self.corpus_digest, "corpus_digest"),
            (self.census_digest, "census_digest"),
            (self.profile_fingerprint, "profile_fingerprint"),
            (self.vector_space_identity, "vector_space_identity"),
            (self.build_manifest_digest, "build_manifest_digest"),
            (self.storage_manifest_digest, "storage_manifest_digest"),
            (self.database_identity, "database_identity"),
        ):
            require_sha256(value, name)
        capabilities = tuple(item.capability for item in self.generations)
        if capabilities != tuple(sorted(capabilities)) or len(set(capabilities)) != 4:
            raise ValueError("database artifact requires four capability-sorted generations")
        if self.database_identity != self.canonical_identity:
            raise ValueError("database identity does not match its canonical build envelope")

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "database_id": str(self.database_id),
            "target_path": self.target_path,
            "build_run_id": str(self.build_run_id),
            "corpus_digest": self.corpus_digest,
            "census_digest": self.census_digest,
            "profile_fingerprint": self.profile_fingerprint,
            "vector_space_identity": self.vector_space_identity,
            "build_manifest_digest": self.build_manifest_digest,
            "storage_manifest_digest": self.storage_manifest_digest,
            "generations": [item.payload() for item in self.generations],
        }

    @property
    def canonical_identity(self) -> str:
        return hashlib.sha256(_canonical(self.identity_payload())).hexdigest()

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> V2DatabaseArtifactIdentityV1:
        generation_values = raw.get("generations")
        if not isinstance(generation_values, list):
            raise ValueError("database identity generations must be an array")
        generations = tuple(
            V2GenerationArtifactIdentityV1(
                capability=str(value["capability"]),
                generation_id=UUID(str(value["generation_id"])),
                checksum=str(value["checksum"]),
                source_generation_ids=tuple(
                    UUID(str(item)) for item in value["source_generation_ids"]
                ),
                provider_identity=(
                    None
                    if value.get("provider_identity") is None
                    else str(value["provider_identity"])
                ),
                model_identity=(
                    None if value.get("model_identity") is None else str(value["model_identity"])
                ),
                configuration_digest=str(value["configuration_digest"]),
                vector_space_identity=(
                    None
                    if value.get("vector_space_identity") is None
                    else str(value["vector_space_identity"])
                ),
                dimensions=(None if value.get("dimensions") is None else int(value["dimensions"])),
            )
            for value in generation_values
            if isinstance(value, dict)
        )
        return cls(
            database_id=UUID(str(raw["database_id"])),
            target_path=str(raw["target_path"]),
            build_run_id=UUID(str(raw["build_run_id"])),
            corpus_digest=str(raw["corpus_digest"]),
            census_digest=str(raw["census_digest"]),
            profile_fingerprint=str(raw["profile_fingerprint"]),
            vector_space_identity=str(raw["vector_space_identity"]),
            build_manifest_digest=str(raw["build_manifest_digest"]),
            storage_manifest_digest=str(raw["storage_manifest_digest"]),
            generations=generations,
            database_identity=str(raw["database_identity"]),
            schema_version=str(raw["schema_version"]),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class V2VectorEmbeddingGenerationBindingV1:
    vector_generation_id: UUID
    embedding_generation_id: UUID
    model_identity: str
    vector_space_identity: str
    dimensions: int
    embedding_configuration_digest: str
    vector_configuration_digest: str
    database_identity: str
    build_run_id: UUID

    def __post_init__(self) -> None:
        require_non_empty(self.model_identity, "model_identity")
        for value, name in (
            (self.vector_space_identity, "vector_space_identity"),
            (self.embedding_configuration_digest, "embedding_configuration_digest"),
            (self.vector_configuration_digest, "vector_configuration_digest"),
            (self.database_identity, "database_identity"),
        ):
            require_sha256(value, name)
        if self.dimensions < 1 or self.vector_generation_id == self.embedding_generation_id:
            raise ValueError("vector and embedding generation binding is invalid")


class GovernedV2DatabaseIdentityVerifier:
    """Verify the logical artifact against immutable build/generation rows, read-only."""

    def __init__(self, *, workspace_root: Path, identity_manifest: Path) -> None:
        self._root = workspace_root.resolve()
        raw = json.loads(identity_manifest.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("database identity manifest must contain an object")
        self._artifact = V2DatabaseArtifactIdentityV1.from_json(raw)

    @property
    def artifact(self) -> V2DatabaseArtifactIdentityV1:
        return self._artifact

    def verify(self, *, expected_database_identity: str) -> None:
        if expected_database_identity != self._artifact.database_identity:
            raise ValueError("DATABASE_BINDING_MISMATCH")
        target = (self._root / self._artifact.target_path).resolve()
        try:
            target.relative_to(self._root)
        except ValueError as error:
            raise ValueError("database target escapes the workspace") from error
        connection = sqlite3.connect(f"file:{target.as_posix()}?mode=ro&immutable=1", uri=True)
        try:
            run = connection.execute(
                """SELECT corpus_digest,census_digest,profile_fingerprint,
                          vector_space_identity,build_manifest_digest,storage_manifest_digest,state
                   FROM v2_build_runs WHERE run_id=? AND target_database_path=?""",
                (str(self._artifact.build_run_id), self._artifact.target_path),
            ).fetchone()
            expected_run = (
                self._artifact.corpus_digest,
                self._artifact.census_digest,
                self._artifact.profile_fingerprint,
                self._artifact.vector_space_identity,
                self._artifact.build_manifest_digest,
                self._artifact.storage_manifest_digest,
                "ready",
            )
            if run is None or tuple(str(value) for value in run) != expected_run:
                raise ValueError("DATABASE_BUILD_BINDING_MISMATCH")
            for generation in self._artifact.generations:
                row = connection.execute(
                    """SELECT capability,checksum,provider_identity,model_identity,
                              configuration_digest,dimensions,state
                       FROM index_generations WHERE generation_id=?""",
                    (str(generation.generation_id),),
                ).fetchone()
                expected = (
                    generation.capability,
                    generation.checksum,
                    generation.provider_identity,
                    generation.model_identity,
                    generation.configuration_digest,
                    generation.dimensions,
                    "ready",
                )
                if row is None or tuple(row) != expected:
                    raise ValueError("DATABASE_GENERATION_BINDING_MISMATCH")
                sources = tuple(
                    UUID(str(value[0]))
                    for value in connection.execute(
                        """SELECT source_id FROM index_generation_sources
                           WHERE generation_id=? AND source_kind='generation'
                           ORDER BY source_id""",
                        (str(generation.generation_id),),
                    ).fetchall()
                )
                if sources != generation.source_generation_ids:
                    raise ValueError("DATABASE_GENERATION_DEPENDENCY_MISMATCH")
            embedding = next(
                value
                for value in self._artifact.generations
                if value.capability == "multilingual_embedding_v2"
            )
            persisted_vector_spaces = tuple(
                str(value[0])
                for value in connection.execute(
                    """SELECT DISTINCT vector_space FROM multilingual_embeddings_v2
                       WHERE generation_id=? ORDER BY vector_space""",
                    (str(embedding.generation_id),),
                ).fetchall()
            )
            if persisted_vector_spaces != (self._artifact.vector_space_identity,):
                raise ValueError("DATABASE_VECTOR_SPACE_BINDING_MISMATCH")
        finally:
            connection.close()

    def resolve_vector_embedding_generation(
        self, *, active_generation_ids: tuple[UUID, ...], expected_database_identity: str
    ) -> V2VectorEmbeddingGenerationBindingV1:
        self.verify(expected_database_identity=expected_database_identity)
        by_capability = {value.capability: value for value in self._artifact.generations}
        vector = by_capability.get("multilingual_vector_v2")
        embedding = by_capability.get("multilingual_embedding_v2")
        if vector is None or embedding is None:
            raise ValueError("ACTIVE_GENERATION_MISSING")
        if set(active_generation_ids) != {
            value.generation_id for value in self._artifact.generations
        }:
            raise ValueError("ACTIVE_GENERATION_MISMATCH")
        if vector.source_generation_ids != (embedding.generation_id,):
            raise ValueError("VECTOR_EMBEDDING_GENERATION_RELATIONSHIP_MISSING")
        if (
            vector.model_identity is None
            or embedding.model_identity != vector.model_identity
            or embedding.dimensions is None
            or vector.dimensions != embedding.dimensions
            or vector.checksum != embedding.checksum
            or vector.vector_space_identity != self._artifact.vector_space_identity
            or embedding.vector_space_identity != self._artifact.vector_space_identity
        ):
            raise ValueError("VECTOR_EMBEDDING_GENERATION_MISMATCH")
        return V2VectorEmbeddingGenerationBindingV1(
            vector_generation_id=vector.generation_id,
            embedding_generation_id=embedding.generation_id,
            model_identity=vector.model_identity,
            vector_space_identity=self._artifact.vector_space_identity,
            dimensions=embedding.dimensions,
            embedding_configuration_digest=embedding.configuration_digest,
            vector_configuration_digest=vector.configuration_digest,
            database_identity=self._artifact.database_identity,
            build_run_id=self._artifact.build_run_id,
        )
