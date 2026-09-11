"""Bounded, typed authorization path for first Full Multilingual V2 activation."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from mnemo.interfaces.errors import ContractValidationError, IntegrityError
from mnemo.phase85.v2_activation_authorization import (
    V2ActivationAuthorizationV1,
    first_v2_deactivation_recovery_digest,
)
from mnemo.storage.sqlite import SQLiteStore

_CAPABILITIES = (
    "representation_derivation_v2",
    "language_text_v2",
    "multilingual_embedding_v2",
    "multilingual_vector_v2",
)


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContractValidationError(f"activation artifact must be an object: {path.name}")
    return value


@dataclass(frozen=True, slots=True)
class V2ActivationPreflight:
    target: Path
    authorization: V2ActivationAuthorizationV1
    generation_ids: tuple[UUID, ...]


class FullMultilingualV2ActivationOperator:
    """Promote exactly one governed READY V2 set; no exposure or evaluation surface."""

    def __init__(self, *, workspace_root: Path, proposal_root: Path) -> None:
        self._root = workspace_root.resolve()
        self._proposal_root = proposal_root.resolve()

    def preflight(self) -> V2ActivationPreflight:
        authorization = V2ActivationAuthorizationV1.from_mapping(
            _load(self._proposal_root / "V2_INDEX_ACTIVATION_AUTHORIZATION.json")
        )
        storage = _load(self._proposal_root / "V2_DISPOSABLE_DATABASE_MANIFEST.json")
        build = _load(self._proposal_root / "V2_BUILD_RECOVERY_ROLLBACK_MANIFEST.json")
        target = (self._root / authorization.target_database_path).resolve(strict=False)
        protected = {
            (self._root / "scratch/phase8_5_wp16/eval-20260828-01/mnemo.db").resolve(),
            (self._root / "scratch/phase8_5_wp10/eval-20260828-01/mnemo.db").resolve(),
            (self._root / "scratch/phase8_5_11/eval-20260825-02/mnemo.db").resolve(),
        }
        if target in protected or not target.is_file():
            raise ContractValidationError("V2 activation target is absent or protected")
        bindings = (
            (str(storage.get("run_id")), str(authorization.run_id), "run"),
            (str(storage.get("target_path")), authorization.target_database_path, "target"),
            (str(storage.get("profile_fingerprint")), authorization.profile_fingerprint, "profile"),
            (str(storage.get("corpus_digest")), authorization.corpus_digest, "corpus"),
            (str(storage.get("census_digest")), authorization.census_digest, "census"),
            (
                str(storage.get("generation_namespace")),
                authorization.generation_namespace,
                "namespace",
            ),
            (
                str(storage.get("vector_space_profile_identity")),
                authorization.vector_space_identity,
                "vector space",
            ),
            (
                str(storage.get("artifact_digest")),
                authorization.storage_manifest_digest,
                "storage manifest",
            ),
            (
                str(build.get("artifact_digest")),
                authorization.build_manifest_digest,
                "build manifest",
            ),
        )
        mismatch = next((name for actual, expected, name in bindings if actual != expected), None)
        if mismatch is not None:
            raise ContractValidationError(
                f"V2 activation authorization {mismatch} binding mismatch"
            )
        if authorization.activation_mode != "first_v2_activation":
            raise ContractValidationError("this bounded operator supports first V2 activation only")
        self._validate_ready_database(target, authorization)
        return V2ActivationPreflight(target, authorization, authorization.generation_ids)

    async def execute(self) -> dict[str, object]:
        preflight = self.preflight()
        store = SQLiteStore(preflight.target)
        await store.open()
        try:
            alias_set_digest = await store.promote_multilingual_v2_alias_set(
                profile_fingerprint=preflight.authorization.profile_fingerprint,
                generation_ids=preflight.generation_ids,
                rollback_alias_set_digest=first_v2_deactivation_recovery_digest(
                    profile_fingerprint=preflight.authorization.profile_fingerprint
                ),
                rollback_generation_ids=(),
                expected_active_alias_set_digest=None,
                activation_mode=preflight.authorization.activation_mode,
                recovery_mode=preflight.authorization.recovery_mode,
                authorization_id=preflight.authorization.authorization_id,
                authorization_digest=preflight.authorization.artifact_digest,
            )
            self._validate_active_database(
                preflight.target, preflight.authorization, alias_set_digest
            )
            resolved_generation_ids = await store.resolve_active_multilingual_v2_generation_set()
            if resolved_generation_ids != preflight.generation_ids:
                raise IntegrityError(
                    "V2 runtime generation resolver disagrees with activation authorization"
                )
            return {
                "activation_authorization_id": str(preflight.authorization.authorization_id),
                "activation_alias_set_digest": alias_set_digest,
                "activation_mode": preflight.authorization.activation_mode,
                "recovery_mode": preflight.authorization.recovery_mode,
                "resolved_generation_ids": [str(value) for value in resolved_generation_ids],
                "target": preflight.authorization.target_database_path,
                "exposed": False,
            }
        finally:
            await store.close()

    @staticmethod
    def _validate_ready_database(target: Path, authorization: V2ActivationAuthorizationV1) -> None:
        connection = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
        try:
            run = connection.execute(
                """SELECT state,profile_fingerprint,vector_space_identity,
                          corpus_digest,census_digest
                   FROM v2_build_runs WHERE run_id=?""",
                (str(authorization.run_id),),
            ).fetchone()
            if run != (
                "ready",
                authorization.profile_fingerprint,
                authorization.vector_space_identity,
                authorization.corpus_digest,
                authorization.census_digest,
            ):
                raise IntegrityError("V2 build run is not the exact governed READY run")
            ids = json.dumps([str(value) for value in authorization.generation_ids])
            rows = connection.execute(
                """SELECT g.capability,g.generation_id,g.state,g.checksum,c.completeness,
                          c.failed_count,v.profile_fingerprint,v.provenance_complete,
                          v.authorization_compatible
                   FROM index_generations g
                   JOIN index_generation_coverage c USING(generation_id)
                   JOIN multilingual_coverage_manifests_v2 v USING(generation_id)
                   JOIN json_each(?) selected ON selected.value=g.generation_id
                   ORDER BY CASE g.capability
                       WHEN 'representation_derivation_v2' THEN 1
                       WHEN 'language_text_v2' THEN 2
                       WHEN 'multilingual_embedding_v2' THEN 3
                       WHEN 'multilingual_vector_v2' THEN 4 END""",
                (ids,),
            ).fetchall()
            expected = tuple(
                (capability, str(identifier), checksum)
                for capability, identifier, checksum in zip(
                    _CAPABILITIES,
                    authorization.generation_ids,
                    authorization.generation_checksums,
                    strict=True,
                )
            )
            actual = tuple((str(row[0]), str(row[1]), str(row[3])) for row in rows)
            if actual != expected or any(
                str(row[2]) != "ready"
                or str(row[4]) != "complete"
                or int(row[5]) != 0
                or str(row[6]) != authorization.profile_fingerprint
                or int(row[7]) != 1
                or int(row[8]) != 1
                for row in rows
            ):
                raise IntegrityError("V2 activation generation set is incomplete or incompatible")
            vector_spaces = connection.execute(
                """SELECT DISTINCT vector_space FROM multilingual_embeddings_v2
                   WHERE generation_id=?""",
                (str(authorization.generation_ids[2]),),
            ).fetchall()
            if vector_spaces != [(authorization.vector_space_identity,)]:
                raise IntegrityError("V2 activation embedding vector space mismatch")
            if connection.execute(
                "SELECT count(*) FROM active_multilingual_v2_alias_set"
            ).fetchone()[0]:
                raise IntegrityError("first V2 activation cannot replace an existing V2 alias")
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise IntegrityError("V2 activation target integrity check failed")
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise IntegrityError("V2 activation target foreign-key audit failed")
        finally:
            connection.close()

    @staticmethod
    def _validate_active_database(
        target: Path, authorization: V2ActivationAuthorizationV1, alias_set_digest: str
    ) -> None:
        connection = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
        try:
            active = connection.execute(
                "SELECT alias_set_digest FROM active_multilingual_v2_alias_set WHERE singleton=1"
            ).fetchone()
            record = connection.execute(
                """SELECT activation_mode,recovery_mode,authorization_id,authorization_digest
                   FROM multilingual_v2_activation_records WHERE alias_set_digest=?""",
                (alias_set_digest,),
            ).fetchone()
            expected = (
                "first_v2_activation",
                "deactivate_v2_alias_set",
                str(authorization.authorization_id),
                authorization.artifact_digest,
            )
            if active != (alias_set_digest,) or record != expected:
                raise IntegrityError("V2 active alias set does not match typed first activation")
        finally:
            connection.close()


def execute_v2_activation(*, workspace_root: Path, proposal_root: Path) -> dict[str, object]:
    return asyncio.run(
        FullMultilingualV2ActivationOperator(
            workspace_root=workspace_root, proposal_root=proposal_root
        ).execute()
    )
