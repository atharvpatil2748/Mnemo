"""Logical Full V2 identity for a disposable, single-notebook rebuild.

The historical certified build verifier remains unchanged. This verifier binds
an isolated rebuild to its persisted notebook, four complete generations and
their exact coverage manifests without relying on mutable SQLite file bytes.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import UUID

from mnemo.phase85.rebuild_runtime import resolve_governed_rebuild_runtime
from mnemo.phase85.v2_database_identity import V2VectorEmbeddingGenerationBindingV1

_CAPABILITIES = (
    "representation_derivation_v2",
    "language_text_v2",
    "multilingual_embedding_v2",
    "multilingual_vector_v2",
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class IsolatedV2ArtifactIdentity:
    target_path: str
    notebook_id: UUID
    build_run_id: UUID
    profile_fingerprint: str
    vector_space_identity: str
    database_identity: str
    generation_ids: tuple[UUID, ...]


class IsolatedV2DatabaseIdentityVerifier:
    """Fail closed if an isolated rebuild's immutable generation evidence changes."""

    def __init__(self, *, workspace_root: Path, runtime: Path) -> None:
        root = workspace_root.resolve(strict=True)
        target = runtime.resolve(strict=True)
        status = resolve_governed_rebuild_runtime(workspace=root, runtime=target)
        self._database = target / "mnemo.db"
        self._notebook_id = UUID(status["notebook_id"])
        self._run_id = UUID(status["run_id"])
        self._source_hashes = tuple(
            sorted((str(item["relative_path"]), str(item["sha256"])) for item in status["sources"])
        )
        self._expected = self._read_identity()
        self.artifact = IsolatedV2ArtifactIdentity(
            target_path=self._database.relative_to(root).as_posix(),
            notebook_id=self._notebook_id,
            build_run_id=self._run_id,
            profile_fingerprint=cast(str, self._expected["profile_fingerprint"]),
            vector_space_identity=cast(str, self._expected["vector_space"]),
            database_identity=_digest(self._expected),
            generation_ids=tuple(
                UUID(cast(str, item["id"]))
                for item in cast(list[dict[str, object]], self._expected["generations"])
            ),
        )

    def _read_identity(self) -> dict[str, object]:
        connection = sqlite3.connect(
            f"file:{self._database.as_posix()}?mode=ro&immutable=1", uri=True
        )
        try:
            notebooks = connection.execute("SELECT notebook_id FROM notebooks").fetchall()
            if notebooks != [(str(self._notebook_id),)]:
                raise ValueError("isolated V2 notebook identity mismatch")
            rows = connection.execute(
                "SELECT g.capability,g.generation_id,g.profile,g.model_identity,"
                "g.configuration_digest,g.dimensions,g.state,g.item_count,g.checksum,"
                "c.completeness,c.expected_count,c.succeeded_count,c.failed_count,"
                "c.skipped_count,m.profile_fingerprint,m.payload,m.payload_hash "
                "FROM index_generations g JOIN index_generation_coverage c USING(generation_id) "
                "JOIN multilingual_coverage_manifests_v2 m USING(generation_id) "
                "WHERE g.capability IN (?,?,?,?) ORDER BY CASE g.capability "
                "WHEN 'representation_derivation_v2' THEN 1 WHEN 'language_text_v2' THEN 2 "
                "WHEN 'multilingual_embedding_v2' THEN 3 ELSE 4 END",
                _CAPABILITIES,
            ).fetchall()
            if len(rows) != 4 or tuple(row[0] for row in rows) != _CAPABILITIES:
                raise ValueError("isolated V2 generation set is incomplete")
            profiles = {str(row[14]) for row in rows}
            if len(profiles) != 1:
                raise ValueError("isolated V2 profile fingerprints differ")
            generations: list[dict[str, object]] = []
            for row in rows:
                if (
                    row[6] != "ready"
                    or row[9] != "complete"
                    or row[7] != row[10]
                    or row[10] != row[11]
                    or row[12] != 0
                    or row[13] != 0
                    or _digest(json.loads(row[15])) != row[16]
                ):
                    raise ValueError("isolated V2 generation is not complete")
                generations.append(
                    {
                        "capability": row[0],
                        "id": row[1],
                        "profile": row[2],
                        "model": row[3],
                        "configuration": row[4],
                        "dimensions": row[5],
                        "count": row[7],
                        "checksum": row[8],
                        "manifest_hash": row[16],
                    }
                )
            embedding, vector = rows[2], rows[3]
            if (
                embedding[3] != vector[3]
                or embedding[5] != vector[5]
                or embedding[5] != 1024
                or embedding[8] != vector[8]
            ):
                raise ValueError("isolated V2 vector/embedding pair is incompatible")
            spaces = connection.execute(
                "SELECT DISTINCT vector_space FROM multilingual_embeddings_v2 "
                "WHERE generation_id=?",
                (embedding[1],),
            ).fetchall()
            if len(spaces) != 1:
                raise ValueError("isolated V2 embedding space is missing or ambiguous")
            dependencies = connection.execute(
                "SELECT source_id FROM index_generation_sources WHERE generation_id=? "
                "AND source_kind='generation'",
                (vector[1],),
            ).fetchall()
            if dependencies != [(embedding[1],)]:
                raise ValueError("isolated V2 vector dependency is invalid")
            return {
                "schema": "mnemo.isolated-v2-serving-identity/1",
                "notebook_id": str(self._notebook_id),
                "run_id": str(self._run_id),
                "source_hashes": self._source_hashes,
                "profile_fingerprint": next(iter(profiles)),
                "vector_space": str(spaces[0][0]),
                "generations": generations,
            }
        finally:
            connection.close()

    def verify(self, *, expected_database_identity: str) -> None:
        if expected_database_identity != self.artifact.database_identity:
            raise ValueError("DATABASE_BINDING_MISMATCH")
        if self._read_identity() != self._expected:
            raise ValueError("ISOLATED_V2_BUILD_CHANGED")

    def resolve_vector_embedding_generation(
        self, *, active_generation_ids: tuple[UUID, ...], expected_database_identity: str
    ) -> V2VectorEmbeddingGenerationBindingV1:
        self.verify(expected_database_identity=expected_database_identity)
        if active_generation_ids != self.artifact.generation_ids:
            raise ValueError("ACTIVE_GENERATION_MISMATCH")
        embedding, vector = cast(list[dict[str, object]], self._expected["generations"])[2:4]
        return V2VectorEmbeddingGenerationBindingV1(
            vector_generation_id=UUID(cast(str, vector["id"])),
            embedding_generation_id=UUID(cast(str, embedding["id"])),
            model_identity=str(embedding["model"]),
            vector_space_identity=self.artifact.vector_space_identity,
            dimensions=cast(int, embedding["dimensions"]),
            embedding_configuration_digest=str(embedding["configuration"]),
            vector_configuration_digest=str(vector["configuration"]),
            database_identity=self.artifact.database_identity,
            build_run_id=self.artifact.build_run_id,
        )
