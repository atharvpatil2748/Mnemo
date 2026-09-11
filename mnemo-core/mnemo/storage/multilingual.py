"""Immutable SQLite persistence for Phase 8.5.9 multilingual derivations."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

import aiosqlite

from mnemo.interfaces.errors import ConflictError, StorageError
from mnemo.models.multilingual import (
    LanguageDerivation,
    LanguageEvidenceReferenceV2,
    LanguageEvidenceReferenceV3,
    LanguageObservation,
    LanguageObservationV2,
    MultilingualEmbedding,
    ScriptObservationV1,
)
from mnemo.models.multilingual_embeddings import MultilingualEmbeddingV3
from mnemo.models.multilingual_generation import MultilingualCoverageManifestV2
from mnemo.models.multilingual_index import MultilingualTextProjectionRowV2
from mnemo.models.text_representations import (
    RepresentationObservationV1,
    RepresentationTransformationV1,
)
from mnemo.phase85.v2_activation_authorization import first_v2_deactivation_recovery_digest
from mnemo.retrieval.final_qa_snapshot import _decode, _encode

MULTILINGUAL_SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS language_observations (
        observation_id TEXT PRIMARY KEY,
        actor_id TEXT NOT NULL,
        notebook_id TEXT NOT NULL,
        document_id TEXT,
        version_id TEXT,
        target_scope TEXT NOT NULL,
        target_id TEXT NOT NULL,
        language TEXT NOT NULL,
        script TEXT NOT NULL,
        payload TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(notebook_id,target_scope,target_id,payload_hash)
    )""",
    """CREATE INDEX IF NOT EXISTS idx_language_observations_scope
       ON language_observations(actor_id,notebook_id,document_id,version_id)""",
    """CREATE TABLE IF NOT EXISTS language_derivations (
        derivation_id TEXT PRIMARY KEY,
        cache_key TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        notebook_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        version_id TEXT NOT NULL,
        source_evidence_id TEXT NOT NULL,
        source_language TEXT NOT NULL,
        target_language TEXT NOT NULL,
        kind TEXT NOT NULL,
        generation_id TEXT NOT NULL,
        payload TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(notebook_id,cache_key)
    )""",
    """CREATE INDEX IF NOT EXISTS idx_language_derivations_scope
       ON language_derivations(actor_id,notebook_id,document_id,version_id)""",
    """CREATE TABLE IF NOT EXISTS multilingual_embeddings (
        embedding_id TEXT PRIMARY KEY,
        notebook_id TEXT NOT NULL,
        source_evidence_id TEXT NOT NULL,
        language TEXT NOT NULL,
        generation_id TEXT NOT NULL,
        vector_space TEXT NOT NULL,
        payload TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(notebook_id,source_evidence_id,generation_id,vector_space)
    )""",
    """CREATE INDEX IF NOT EXISTS idx_multilingual_embeddings_generation
       ON multilingual_embeddings(notebook_id,generation_id,vector_space)""",
)

MULTILINGUAL_V2_SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS language_observations_v2 (
        observation_id TEXT PRIMARY KEY,
        actor_id TEXT NOT NULL,
        notebook_id TEXT NOT NULL,
        source_id TEXT,
        document_id TEXT,
        version_id TEXT,
        target_scope TEXT NOT NULL,
        target_id TEXT NOT NULL,
        payload TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS idx_language_observations_v2_scope
       ON language_observations_v2(actor_id,notebook_id,source_id,document_id,version_id)""",
    """CREATE TABLE IF NOT EXISTS script_observations_v1 (
        observation_id TEXT PRIMARY KEY,
        actor_id TEXT NOT NULL,
        notebook_id TEXT NOT NULL,
        source_id TEXT,
        document_id TEXT,
        version_id TEXT,
        target_scope TEXT NOT NULL,
        target_id TEXT NOT NULL,
        payload TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS idx_script_observations_v1_scope
       ON script_observations_v1(actor_id,notebook_id,source_id,document_id,version_id)""",
    """CREATE TABLE IF NOT EXISTS representation_observations_v1 (
        observation_id TEXT PRIMARY KEY,
        notebook_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        version_id TEXT NOT NULL,
        evidence_reference_digest TEXT NOT NULL,
        representation_type TEXT NOT NULL,
        input_content_hash TEXT NOT NULL,
        payload TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS idx_representation_observations_v1_scope
       ON representation_observations_v1(notebook_id,source_id,document_id,version_id)""",
    """CREATE TABLE IF NOT EXISTS representation_transformations_v1 (
        transformation_id TEXT PRIMARY KEY,
        notebook_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        version_id TEXT NOT NULL,
        source_reference_digest TEXT NOT NULL,
        source_representation_reference_id TEXT NOT NULL,
        output_reference_id TEXT NOT NULL,
        profile_id TEXT NOT NULL,
        generation_id TEXT NOT NULL,
        authorization_scope_digest TEXT NOT NULL,
        input_content_hash TEXT NOT NULL,
        output_content_hash TEXT NOT NULL,
        payload TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(source_representation_reference_id,profile_id,generation_id)
    )""",
    """CREATE INDEX IF NOT EXISTS idx_representation_transformations_v1_scope
       ON representation_transformations_v1(notebook_id,source_id,document_id,version_id)""",
    """CREATE TABLE IF NOT EXISTS multilingual_coverage_manifests_v2 (
        generation_id TEXT PRIMARY KEY,
        capability TEXT NOT NULL,
        profile_fingerprint TEXT NOT NULL,
        dependency_digest TEXT NOT NULL,
        coverage_digest TEXT NOT NULL,
        item_identity_digest TEXT NOT NULL,
        expected_count INTEGER NOT NULL CHECK(expected_count >= 0),
        succeeded_count INTEGER NOT NULL CHECK(succeeded_count >= 0),
        failed_count INTEGER NOT NULL CHECK(failed_count >= 0),
        skipped_count INTEGER NOT NULL CHECK(skipped_count >= 0),
        provenance_complete INTEGER NOT NULL CHECK(provenance_complete IN (0,1)),
        authorization_compatible INTEGER NOT NULL CHECK(authorization_compatible IN (0,1)),
        rollback_metadata_digest TEXT NOT NULL,
        payload TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        CHECK(expected_count = succeeded_count + failed_count + skipped_count)
    )""",
    """CREATE TABLE IF NOT EXISTS multilingual_embeddings_v2 (
        embedding_id TEXT PRIMARY KEY,
        notebook_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        version_id TEXT NOT NULL,
        occurrence_id TEXT,
        derivation_id TEXT,
        evidence_reference_digest TEXT NOT NULL,
        representation_reference_id TEXT NOT NULL,
        representation_type TEXT NOT NULL,
        language TEXT NOT NULL,
        generation_id TEXT NOT NULL,
        vector_space TEXT NOT NULL,
        vector_hash TEXT NOT NULL,
        payload TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(evidence_reference_digest,representation_reference_id,generation_id,vector_space)
    )""",
    """CREATE INDEX IF NOT EXISTS idx_multilingual_embeddings_v2_scope
       ON multilingual_embeddings_v2(notebook_id,source_id,document_id,version_id,
                                      generation_id,vector_space)""",
    """CREATE TABLE IF NOT EXISTS language_text_projection_rows_v2 (
        row_id TEXT PRIMARY KEY,
        notebook_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        version_id TEXT NOT NULL,
        occurrence_id TEXT,
        derivation_id TEXT,
        evidence_reference_digest TEXT NOT NULL,
        representation_reference_id TEXT NOT NULL,
        representation_type TEXT NOT NULL,
        language TEXT NOT NULL,
        page_number INTEGER,
        section_index INTEGER,
        heading_path TEXT NOT NULL,
        heading_path_key TEXT NOT NULL,
        generation_id TEXT NOT NULL,
        text_hash TEXT NOT NULL,
        payload TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(evidence_reference_digest,representation_reference_id,generation_id)
    )""",
    """CREATE INDEX IF NOT EXISTS idx_language_text_projection_v2_scope
       ON language_text_projection_rows_v2(notebook_id,source_id,document_id,version_id,
                                           occurrence_id,derivation_id,generation_id)""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS language_text_fts_v2 USING fts5(
        row_id UNINDEXED,
        text,
        tokenize='unicode61'
    )""",
    """CREATE TABLE IF NOT EXISTS multilingual_v2_alias_sets (
        alias_set_digest TEXT PRIMARY KEY,
        profile_fingerprint TEXT NOT NULL,
        generation_ids TEXT NOT NULL,
        rollback_alias_set_digest TEXT NOT NULL,
        rollback_generation_ids TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS active_multilingual_v2_alias_set (
        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
        alias_set_digest TEXT NOT NULL REFERENCES multilingual_v2_alias_sets(alias_set_digest),
        promoted_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS multilingual_v2_activation_records (
        alias_set_digest TEXT PRIMARY KEY REFERENCES multilingual_v2_alias_sets(alias_set_digest),
        activation_mode TEXT NOT NULL CHECK(
            activation_mode IN ('first_v2_activation','v2_upgrade')
        ),
        recovery_mode TEXT NOT NULL CHECK(
            recovery_mode IN ('deactivate_v2_alias_set','prior_v2_alias_set')
        ),
        authorization_id TEXT NOT NULL,
        authorization_digest TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
)


@asynccontextmanager
async def _transaction(db: aiosqlite.Connection) -> AsyncIterator[None]:
    try:
        await db.execute("BEGIN IMMEDIATE")
        yield
        await db.commit()
    except BaseException:
        await db.rollback()
        raise


class SQLiteMultilingualMixin:
    _multilingual_lock: asyncio.Lock

    def _require_open(self) -> aiosqlite.Connection:
        raise NotImplementedError

    async def put_language_observation_v2(self, observation: LanguageObservationV2) -> bool:
        source = observation.source_reference
        return await self._put_observation_v2(
            table="language_observations_v2",
            observation_id=observation.observation_id,
            actor_id=observation.actor_id,
            notebook_id=observation.notebook_id,
            source_id=None if source is None else source.source_id,
            document_id=None if source is None else source.document_id,
            version_id=None if source is None else source.version_id,
            target_scope=observation.target_scope.value,
            target_id=observation.target_id,
            created_at=observation.created_at.isoformat(),
            value=observation,
        )

    async def put_script_observation_v1(self, observation: ScriptObservationV1) -> bool:
        source = observation.source_reference
        return await self._put_observation_v2(
            table="script_observations_v1",
            observation_id=observation.observation_id,
            actor_id=observation.actor_id,
            notebook_id=observation.notebook_id,
            source_id=None if source is None else source.source_id,
            document_id=None if source is None else source.document_id,
            version_id=None if source is None else source.version_id,
            target_scope=observation.target_scope.value,
            target_id=observation.target_id,
            created_at=observation.created_at.isoformat(),
            value=observation,
        )

    async def put_representation_observation_v1(
        self, observation: RepresentationObservationV1
    ) -> bool:
        source = observation.source_reference
        payload, digest = _payload(observation)
        return await self._insert_immutable(
            table="representation_observations_v1",
            identity_column="observation_id",
            identity=observation.observation_id,
            payload_digest=digest,
            statement="""INSERT INTO representation_observations_v1(
                observation_id,notebook_id,source_id,document_id,version_id,
                evidence_reference_digest,representation_type,input_content_hash,
                payload,payload_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            parameters=(
                str(observation.observation_id),
                str(source.notebook_id),
                str(source.source_id),
                str(source.document_id),
                str(source.version_id),
                source.identity_digest,
                observation.representation_type.value,
                observation.input_content_hash,
                payload,
                digest,
                observation.created_at.isoformat(),
            ),
        )

    async def put_representation_observation(
        self, observation: RepresentationObservationV1
    ) -> bool:
        return await self.put_representation_observation_v1(observation)

    async def put_representation_transformation_v1(
        self, transformation: RepresentationTransformationV1
    ) -> bool:
        source = transformation.source_representation.evidence_reference
        payload, digest = _payload(transformation)
        return await self._insert_immutable(
            table="representation_transformations_v1",
            identity_column="transformation_id",
            identity=transformation.transformation_id,
            payload_digest=digest,
            statement="""INSERT INTO representation_transformations_v1(
                transformation_id,notebook_id,source_id,document_id,version_id,
                source_reference_digest,source_representation_reference_id,
                output_reference_id,profile_id,generation_id,authorization_scope_digest,
                input_content_hash,output_content_hash,payload,payload_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            parameters=(
                str(transformation.transformation_id),
                str(source.notebook_id),
                str(source.source_id),
                str(source.document_id),
                str(source.version_id),
                source.identity_digest,
                str(transformation.source_representation.reference_id),
                str(transformation.output_reference.reference_id),
                transformation.transformation_profile.profile_id,
                str(transformation.generation_id),
                transformation.authorization_scope.actor_scope_digest,
                transformation.input_content_hash,
                transformation.output_content_hash,
                payload,
                digest,
                transformation.created_at.isoformat(),
            ),
        )

    async def put_representation_transformation(
        self, transformation: RepresentationTransformationV1, *, output_text: str
    ) -> bool:
        if hashlib.sha256(output_text.encode("utf-8")).hexdigest() != (
            transformation.output_content_hash
        ):
            raise ValueError("representation transformation output hash mismatch")
        return await self.put_representation_transformation_v1(transformation)

    async def promote_multilingual_v2_alias_set(
        self,
        *,
        profile_fingerprint: str,
        generation_ids: tuple[UUID, ...],
        rollback_alias_set_digest: str,
        rollback_generation_ids: tuple[UUID, ...],
        expected_active_alias_set_digest: str | None,
        activation_mode: str = "v2_upgrade",
        recovery_mode: str = "prior_v2_alias_set",
        authorization_id: UUID | None = None,
        authorization_digest: str | None = None,
    ) -> str:
        """Atomically select a complete V2 generation set and retained rollback target."""
        _require_sha256_text(profile_fingerprint, "profile_fingerprint")
        _require_sha256_text(rollback_alias_set_digest, "rollback_alias_set_digest")
        if activation_mode not in {"first_v2_activation", "v2_upgrade"}:
            raise ValueError("unsupported V2 activation mode")
        if recovery_mode not in {"deactivate_v2_alias_set", "prior_v2_alias_set"}:
            raise ValueError("unsupported V2 recovery mode")
        if authorization_id is None or authorization_digest is None:
            raise ValueError("V2 activation requires typed authorization evidence")
        _require_sha256_text(authorization_digest, "authorization_digest")
        if expected_active_alias_set_digest is not None:
            _require_sha256_text(
                expected_active_alias_set_digest, "expected_active_alias_set_digest"
            )
        if len(generation_ids) != 4 or len(set(generation_ids)) != 4:
            raise ValueError("V2 activation requires exactly four unique generations")
        if activation_mode == "first_v2_activation":
            if recovery_mode != "deactivate_v2_alias_set" or rollback_generation_ids:
                raise ValueError("first V2 activation requires V2-deactivation recovery only")
            expected_rollback_digest = first_v2_deactivation_recovery_digest(
                profile_fingerprint=profile_fingerprint
            )
        else:
            if recovery_mode != "prior_v2_alias_set":
                raise ValueError("V2 upgrade requires a prior V2 rollback set")
            if len(rollback_generation_ids) != 4 or len(set(rollback_generation_ids)) != 4:
                raise ValueError("V2 upgrade requires exactly four rollback generations")
            expected_rollback_digest = multilingual_v2_generation_set_digest(
                profile_fingerprint=profile_fingerprint,
                generation_ids=rollback_generation_ids,
            )
        db = self._require_open()
        required = {
            "representation_derivation_v2",
            "language_text_v2",
            "multilingual_embedding_v2",
            "multilingual_vector_v2",
        }
        encoded = json.dumps(sorted(str(item) for item in generation_ids), separators=(",", ":"))
        rollback_encoded = json.dumps(
            sorted(str(item) for item in rollback_generation_ids), separators=(",", ":")
        )
        if rollback_alias_set_digest != expected_rollback_digest:
            raise ValueError("V2 rollback alias-set digest does not bind its generation set")
        alias_set_digest = hashlib.sha256(
            json.dumps(
                {
                    "profile_fingerprint": profile_fingerprint,
                    "generation_ids": sorted(str(item) for item in generation_ids),
                    "rollback_alias_set_digest": rollback_alias_set_digest,
                    "rollback_generation_ids": sorted(
                        str(item) for item in rollback_generation_ids
                    ),
                    "activation_mode": activation_mode,
                    "recovery_mode": recovery_mode,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        async with self._multilingual_lock, _transaction(db):
            rows = tuple(
                await (
                    await db.execute(
                        """SELECT g.generation_id,g.capability,g.state,c.completeness,
                              c.failed_count,c.checksum
                       ,v.profile_fingerprint,v.expected_count,v.succeeded_count,
                       v.failed_count,v.skipped_count,v.provenance_complete,
                       v.authorization_compatible,v.item_identity_digest
                       FROM index_generations g
                       JOIN index_generation_coverage c ON c.generation_id=g.generation_id
                       JOIN multilingual_coverage_manifests_v2 v
                         ON v.generation_id=g.generation_id AND v.capability=g.capability
                       JOIN json_each(?) selected ON selected.value=g.generation_id
                       ORDER BY g.capability""",
                        (encoded,),
                    )
                ).fetchall()
            )
            if len(rows) != 4 or {str(row[1]) for row in rows} != required:
                raise ConflictError("V2 generation dependency set is incomplete")
            if any(
                str(row[2]) != "ready"
                or str(row[3]) != "complete"
                or int(row[4]) != 0
                or len(str(row[5])) != 64
                or str(row[6]) != profile_fingerprint
                or int(row[7]) != int(row[8]) + int(row[9]) + int(row[10])
                or int(row[9]) != 0
                or int(row[11]) != 1
                or int(row[12]) != 1
                or str(row[13]) != str(row[5])
                for row in rows
            ):
                raise ConflictError("V2 generation dependency set is not ready and complete")
            if activation_mode == "v2_upgrade":
                rollback_rows = tuple(
                    await (
                        await db.execute(
                            """SELECT g.generation_id,g.state,c.completeness,c.failed_count
                           FROM index_generations g
                           JOIN index_generation_coverage c ON c.generation_id=g.generation_id
                           JOIN json_each(?) selected ON selected.value=g.generation_id""",
                            (rollback_encoded,),
                        )
                    ).fetchall()
                )
                if len(rollback_rows) != len(rollback_generation_ids) or any(
                    str(row[1]) != "ready" or str(row[2]) != "complete" or int(row[3]) != 0
                    for row in rollback_rows
                ):
                    raise ConflictError("V2 rollback generation set is not retained and valid")
            active = await (
                await db.execute(
                    "SELECT alias_set_digest FROM active_multilingual_v2_alias_set "
                    "WHERE singleton=1"
                )
            ).fetchone()
            actual = None if active is None else str(active[0])
            if actual != expected_active_alias_set_digest:
                raise ConflictError("V2 active alias set changed concurrently")
            if activation_mode == "first_v2_activation" and actual is not None:
                raise ConflictError("first V2 activation requires no prior V2 alias set")
            if activation_mode == "v2_upgrade" and actual is None:
                raise ConflictError("V2 upgrade requires an existing active V2 alias set")
            await db.execute(
                """INSERT INTO multilingual_v2_alias_sets(
                   alias_set_digest,profile_fingerprint,generation_ids,
                   rollback_alias_set_digest,rollback_generation_ids,created_at
                   ) VALUES(?,?,?,?,?,?)
                   ON CONFLICT(alias_set_digest) DO NOTHING""",
                (
                    alias_set_digest,
                    profile_fingerprint,
                    encoded,
                    rollback_alias_set_digest,
                    rollback_encoded,
                    datetime.now(UTC).isoformat(),
                ),
            )
            await db.execute(
                """INSERT INTO multilingual_v2_activation_records(
                       alias_set_digest,activation_mode,recovery_mode,authorization_id,
                       authorization_digest,created_at) VALUES(?,?,?,?,?,?)
                   ON CONFLICT(alias_set_digest) DO NOTHING""",
                (
                    alias_set_digest,
                    activation_mode,
                    recovery_mode,
                    str(authorization_id),
                    authorization_digest,
                    datetime.now(UTC).isoformat(),
                ),
            )
            await db.execute(
                """INSERT INTO active_multilingual_v2_alias_set(
                       singleton,alias_set_digest,promoted_at)
                   VALUES(1,?,?) ON CONFLICT(singleton) DO UPDATE SET
                   alias_set_digest=excluded.alias_set_digest,promoted_at=excluded.promoted_at""",
                (alias_set_digest, datetime.now(UTC).isoformat()),
            )
        return alias_set_digest

    async def deactivate_first_multilingual_v2_alias_set(
        self,
        *,
        expected_active_alias_set_digest: str,
        authorization_id: UUID,
        authorization_digest: str,
    ) -> bool:
        """Atomically disable a first V2 activation, preserving the independent V1 baseline."""
        _require_sha256_text(expected_active_alias_set_digest, "expected_active_alias_set_digest")
        _require_sha256_text(authorization_digest, "authorization_digest")
        db = self._require_open()
        async with self._multilingual_lock, _transaction(db):
            row = await (
                await db.execute(
                    """SELECT a.alias_set_digest,r.activation_mode,r.recovery_mode,
                              r.authorization_id,r.authorization_digest
                       FROM active_multilingual_v2_alias_set a
                       JOIN multilingual_v2_activation_records r USING(alias_set_digest)
                       WHERE a.singleton=1"""
                )
            ).fetchone()
            if row is None or str(row[0]) != expected_active_alias_set_digest:
                raise ConflictError("V2 active alias set changed concurrently")
            if tuple(str(value) for value in row[1:]) != (
                "first_v2_activation",
                "deactivate_v2_alias_set",
                str(authorization_id),
                authorization_digest,
            ):
                raise ConflictError("V2 first-activation recovery authorization mismatch")
            await db.execute("DELETE FROM active_multilingual_v2_alias_set WHERE singleton=1")
        return True

    async def resolve_active_multilingual_v2_generation_set(self) -> tuple[UUID, ...] | None:
        """Resolve only a complete, typed-authorized active V2 alias set."""
        db = self._require_open()
        row = await (
            await db.execute(
                """SELECT a.alias_set_digest,s.generation_ids,r.activation_mode,r.recovery_mode
                   FROM active_multilingual_v2_alias_set a
                   JOIN multilingual_v2_alias_sets s USING(alias_set_digest)
                   JOIN multilingual_v2_activation_records r USING(alias_set_digest)
                   WHERE a.singleton=1"""
            )
        ).fetchone()
        if row is None:
            return None
        try:
            unordered_ids = tuple(UUID(str(value)) for value in json.loads(str(row[1])))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise StorageError("active V2 alias set has malformed generation identities") from error
        if len(unordered_ids) != 4 or len(set(unordered_ids)) != 4:
            raise StorageError("active V2 alias set is incomplete")
        if str(row[2]) not in {"first_v2_activation", "v2_upgrade"} or str(row[3]) not in {
            "deactivate_v2_alias_set",
            "prior_v2_alias_set",
        }:
            raise StorageError("active V2 alias set has invalid lifecycle metadata")
        encoded = json.dumps([str(value) for value in unordered_ids], separators=(",", ":"))
        rows = tuple(
            await (
                await db.execute(
                    """SELECT capability,generation_id FROM index_generations
                   JOIN json_each(?) selected ON selected.value=generation_id
                   ORDER BY CASE capability
                       WHEN 'representation_derivation_v2' THEN 1
                       WHEN 'language_text_v2' THEN 2
                       WHEN 'multilingual_embedding_v2' THEN 3
                       WHEN 'multilingual_vector_v2' THEN 4 END""",
                    (encoded,),
                )
            ).fetchall()
        )
        if len(rows) != 4 or {str(row[0]) for row in rows} != {
            "representation_derivation_v2",
            "language_text_v2",
            "multilingual_embedding_v2",
            "multilingual_vector_v2",
        }:
            raise StorageError("active V2 alias set has invalid capability membership")
        return tuple(UUID(str(row[1])) for row in rows)

    async def put_multilingual_embedding_v3(self, embedding: MultilingualEmbeddingV3) -> bool:
        source = embedding.source
        payload, digest = _payload(embedding)
        return await self._insert_immutable(
            table="multilingual_embeddings_v2",
            identity_column="embedding_id",
            identity=embedding.embedding_id,
            payload_digest=digest,
            statement="""INSERT INTO multilingual_embeddings_v2(
                embedding_id,notebook_id,source_id,document_id,version_id,
                occurrence_id,derivation_id,evidence_reference_digest,
                representation_reference_id,representation_type,language,generation_id,
                vector_space,vector_hash,payload,payload_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            parameters=(
                str(embedding.embedding_id),
                str(source.notebook_id),
                str(source.source_id),
                str(source.document_id),
                str(source.version_id),
                None if source.occurrence_id is None else str(source.occurrence_id),
                None if source.derivation_id is None else str(source.derivation_id),
                source.identity_digest,
                str(embedding.representation.reference_id),
                embedding.representation.representation_type.value,
                embedding.language.value,
                str(embedding.profile.generation_id),
                embedding.profile.vector_space,
                embedding.vector_hash,
                payload,
                digest,
                embedding.created_at.isoformat(),
            ),
        )

    async def put_multilingual_coverage_manifest_v2(
        self, manifest: MultilingualCoverageManifestV2
    ) -> bool:
        payload, digest = _payload(manifest)
        return await self._insert_immutable(
            table="multilingual_coverage_manifests_v2",
            identity_column="generation_id",
            identity=manifest.generation_id,
            payload_digest=digest,
            statement="""INSERT INTO multilingual_coverage_manifests_v2(
                generation_id,capability,profile_fingerprint,dependency_digest,
                coverage_digest,item_identity_digest,expected_count,succeeded_count,
                failed_count,skipped_count,
                provenance_complete,authorization_compatible,rollback_metadata_digest,
                payload,payload_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            parameters=(
                str(manifest.generation_id),
                manifest.capability,
                manifest.profile_fingerprint,
                manifest.dependency_digest,
                manifest.coverage_digest,
                manifest.item_identity_digest,
                manifest.expected_count,
                manifest.succeeded_count,
                manifest.failed_count,
                manifest.skipped_count,
                int(manifest.provenance_complete),
                int(manifest.authorization_compatible),
                manifest.rollback_metadata_digest,
                payload,
                digest,
                manifest.created_at.isoformat(),
            ),
        )

    async def put_multilingual_text_projection_row_v2(
        self, row: MultilingualTextProjectionRowV2
    ) -> bool:
        """Persist one immutable sparse row and its FTS entry in one transaction."""
        source = row.source
        payload, digest = _payload(row)
        db = self._require_open()
        try:
            async with self._multilingual_lock, _transaction(db):
                existing = await _existing_hash(
                    db, "language_text_projection_rows_v2", "row_id", row.row_id
                )
                if existing is not None:
                    if existing != digest:
                        raise ConflictError("language text V2 row is immutable")
                    return False
                await db.execute(
                    """INSERT INTO language_text_projection_rows_v2(
                       row_id,notebook_id,source_id,document_id,version_id,
                       occurrence_id,derivation_id,evidence_reference_digest,
                       representation_reference_id,representation_type,language,
                       page_number,section_index,heading_path,heading_path_key,generation_id,
                       text_hash,payload,payload_hash,created_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        str(row.row_id),
                        str(source.notebook_id),
                        str(source.source_id),
                        str(source.document_id),
                        str(source.version_id),
                        None if source.occurrence_id is None else str(source.occurrence_id),
                        None if source.derivation_id is None else str(source.derivation_id),
                        source.identity_digest,
                        str(row.representation.reference_id),
                        row.representation.representation_type.value,
                        row.language.value,
                        row.position.page_number,
                        row.position.section_index,
                        json.dumps(row.position.heading_path, separators=(",", ":")),
                        "\x1f".join(row.position.heading_path),
                        str(row.generation_id),
                        row.text_hash,
                        payload,
                        digest,
                        row.created_at.isoformat(),
                    ),
                )
                await db.execute(
                    "INSERT INTO language_text_fts_v2(row_id,text) VALUES(?,?)",
                    (str(row.row_id), row.text),
                )
                return True
        except ConflictError:
            raise
        except aiosqlite.Error as error:
            raise StorageError("could not persist language text V2 row") from error

    async def search_authorized_multilingual_text_v2(
        self,
        *,
        notebook_id: UUID,
        generation_id: UUID,
        query: str,
        authorized_sources: tuple[LanguageEvidenceReferenceV3, ...],
        page_start: int | None,
        page_end: int | None,
        section_indexes: tuple[int, ...],
        heading_prefix: tuple[str, ...],
        limit: int,
    ) -> tuple[tuple[MultilingualTextProjectionRowV2, float], ...]:
        """Search only a caller-authorized identity set with SQL-level scope filters."""
        if not 1 <= limit <= 1000:
            raise ValueError("multilingual sparse result limit is outside governed bounds")
        if len(authorized_sources) > 10_000:
            raise ValueError("authorized multilingual sparse universe exceeds 10000")
        if not authorized_sources:
            return ()
        if any(source.notebook_id != notebook_id for source in authorized_sources):
            raise ValueError("authorized multilingual sparse sources cross notebook scope")
        by_digest = {source.identity_digest: source for source in authorized_sources}
        if len(by_digest) != len(authorized_sources):
            raise ValueError("authorized multilingual sparse sources must be unique")
        match = _multilingual_fts_query_v2(query)
        encoded = json.dumps(sorted(by_digest), separators=(",", ":"))
        clauses = [
            "r.notebook_id=?",
            "r.generation_id=?",
            "f.text MATCH ?",
        ]
        params: list[object] = [
            encoded,
            str(notebook_id),
            str(generation_id),
            match,
        ]
        if page_start is not None:
            clauses.append("r.page_number IS NOT NULL AND r.page_number>=?")
            params.append(page_start)
        if page_end is not None:
            clauses.append("r.page_number IS NOT NULL AND r.page_number<=?")
            params.append(page_end)
        if section_indexes:
            placeholders = ",".join("?" for _ in section_indexes)
            clauses.append(f"r.section_index IN ({placeholders})")
            params.extend(section_indexes)
        if heading_prefix:
            prefix = "\x1f".join(heading_prefix)
            clauses.append("(r.heading_path_key=? OR r.heading_path_key LIKE ? ESCAPE '\\')")
            params.extend((prefix, _escape_like(prefix) + "\x1f%"))
        rows = tuple(
            await (
                await self._require_open().execute(
                    f"""SELECT r.payload,r.payload_hash,bm25(language_text_fts_v2)
                        FROM json_each(?) authorized
                        JOIN language_text_projection_rows_v2 r
                          ON r.evidence_reference_digest=authorized.value
                        JOIN language_text_fts_v2 f ON f.row_id=r.row_id
                        WHERE {" AND ".join(clauses)}
                        ORDER BY bm25(language_text_fts_v2),r.evidence_reference_digest,r.row_id
                        LIMIT ?""",
                    (*params, limit),
                )
            ).fetchall()
        )
        values: list[tuple[MultilingualTextProjectionRowV2, float]] = []
        for row in rows:
            value = _typed(
                _decode_checked(row[:2]),
                MultilingualTextProjectionRowV2,
                "multilingual text projection V2",
            )
            assert value is not None
            if by_digest.get(value.source.identity_digest) != value.source:
                raise StorageError("multilingual sparse result failed authorization revalidation")
            values.append((value, -float(str(row[2]))))
        return tuple(values)

    async def list_authorized_multilingual_embeddings_v3(
        self,
        *,
        notebook_id: UUID,
        generation_id: UUID,
        vector_space: str,
        authorized_sources: tuple[LanguageEvidenceReferenceV3, ...],
    ) -> tuple[MultilingualEmbeddingV3, ...]:
        """Enumerate V2 vectors only after an explicit source authorization decision."""
        if len(authorized_sources) > 10_000:
            raise ValueError("authorized multilingual vector set exceeds 10000")
        if not authorized_sources:
            return ()
        if any(source.notebook_id != notebook_id for source in authorized_sources):
            raise ValueError("authorized multilingual sources cross notebook scope")
        by_digest = {source.identity_digest: source for source in authorized_sources}
        if len(by_digest) != len(authorized_sources):
            raise ValueError("authorized multilingual source identities must be unique")
        encoded = json.dumps(sorted(by_digest), separators=(",", ":"))
        rows = tuple(
            await (
                await self._require_open().execute(
                    """SELECT e.payload,e.payload_hash
                   FROM multilingual_embeddings_v2 e
                   JOIN json_each(?) authorized
                     ON authorized.value=e.evidence_reference_digest
                   WHERE e.notebook_id=? AND e.generation_id=? AND e.vector_space=?
                   ORDER BY e.evidence_reference_digest,e.embedding_id
                   LIMIT 10001""",
                    (encoded, str(notebook_id), str(generation_id), vector_space),
                )
            ).fetchall()
        )
        if len(rows) > 10_000:
            raise StorageError("authorized multilingual vector enumeration exceeds bound")
        values: list[MultilingualEmbeddingV3] = []
        for row in rows:
            value = _typed(
                _decode_checked(row), MultilingualEmbeddingV3, "multilingual embedding V3"
            )
            assert value is not None
            if by_digest.get(value.source.identity_digest) != value.source:
                raise StorageError("multilingual V3 embedding source authorization mismatch")
            if value.profile.vector_space != vector_space:
                raise StorageError("multilingual V3 embedding vector-space mismatch")
            values.append(value)
        return tuple(values)

    async def _put_observation_v2(
        self,
        *,
        table: str,
        observation_id: UUID,
        actor_id: UUID,
        notebook_id: UUID,
        source_id: UUID | None,
        document_id: UUID | None,
        version_id: UUID | None,
        target_scope: str,
        target_id: str,
        created_at: str,
        value: object,
    ) -> bool:
        if table not in {"language_observations_v2", "script_observations_v1"}:
            raise ValueError("unsupported V2 observation table")
        payload, digest = _payload(value)
        return await self._insert_immutable(
            table=table,
            identity_column="observation_id",
            identity=observation_id,
            payload_digest=digest,
            statement=f"""INSERT INTO {table}(
                observation_id,actor_id,notebook_id,source_id,document_id,version_id,
                target_scope,target_id,payload,payload_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            parameters=(
                str(observation_id),
                str(actor_id),
                str(notebook_id),
                None if source_id is None else str(source_id),
                None if document_id is None else str(document_id),
                None if version_id is None else str(version_id),
                target_scope,
                target_id,
                payload,
                digest,
                created_at,
            ),
        )

    async def _insert_immutable(
        self,
        *,
        table: str,
        identity_column: str,
        identity: object,
        payload_digest: str,
        statement: str,
        parameters: tuple[object, ...],
    ) -> bool:
        db = self._require_open()
        try:
            async with self._multilingual_lock, _transaction(db):
                existing = await _existing_hash(db, table, identity_column, identity)
                if existing is not None:
                    if existing != payload_digest:
                        raise ConflictError(f"{table} record is immutable")
                    return False
                await db.execute(statement, parameters)
                return True
        except ConflictError:
            raise
        except aiosqlite.Error as error:
            raise StorageError(f"could not persist {table} record") from error

    async def put_language_observation(self, observation: LanguageObservation) -> bool:
        payload, digest = _payload(observation)
        db = self._require_open()
        try:
            async with self._multilingual_lock, _transaction(db):
                existing = await _existing_hash(
                    db, "language_observations", "observation_id", observation.observation_id
                )
                if existing is not None:
                    if existing != digest:
                        raise ConflictError("language observation is immutable")
                    return False
                await db.execute(
                    """INSERT INTO language_observations(
                       observation_id,actor_id,notebook_id,document_id,version_id,target_scope,
                       target_id,language,script,payload,payload_hash,created_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        str(observation.observation_id),
                        str(observation.actor_id),
                        str(observation.notebook_id),
                        None if observation.document_id is None else str(observation.document_id),
                        None if observation.version_id is None else str(observation.version_id),
                        observation.target_scope.value,
                        observation.target_id,
                        observation.language.value,
                        observation.script.value,
                        payload,
                        digest,
                        observation.created_at.isoformat(),
                    ),
                )
                return True
        except ConflictError:
            raise
        except aiosqlite.Error as error:
            raise StorageError("could not persist language observation") from error

    async def get_authorized_language_observation(
        self, *, actor_id: UUID, notebook_id: UUID, observation_id: UUID
    ) -> LanguageObservation | None:
        value = await self._authorized_payload(
            table="language_observations",
            identity_column="observation_id",
            identity=observation_id,
            actor_id=actor_id,
            notebook_id=notebook_id,
        )
        return _typed(value, LanguageObservation, "language observation")

    async def put_language_derivation(self, derivation: LanguageDerivation) -> bool:
        payload, digest = _payload(derivation)
        db = self._require_open()
        try:
            async with self._multilingual_lock, _transaction(db):
                existing = await _existing_hash(
                    db, "language_derivations", "derivation_id", derivation.derivation_id
                )
                if existing is not None:
                    if existing != digest:
                        raise ConflictError("language derivation is immutable")
                    return False
                await db.execute(
                    """INSERT INTO language_derivations(
                       derivation_id,cache_key,actor_id,notebook_id,document_id,version_id,
                       source_evidence_id,source_language,target_language,kind,generation_id,
                       payload,payload_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        str(derivation.derivation_id),
                        derivation.cache_key,
                        str(derivation.actor_id),
                        str(derivation.notebook_id),
                        str(derivation.document_id),
                        str(derivation.version_id),
                        derivation.source_evidence_id,
                        derivation.source_language.value,
                        derivation.target_language.value,
                        derivation.kind.value,
                        str(derivation.generation_id),
                        payload,
                        digest,
                        derivation.created_at.isoformat(),
                    ),
                )
                return True
        except ConflictError:
            raise
        except aiosqlite.Error as error:
            raise StorageError("could not persist language derivation") from error

    async def get_authorized_language_derivation(
        self, *, actor_id: UUID, notebook_id: UUID, derivation_id: UUID
    ) -> LanguageDerivation | None:
        value = await self._authorized_payload(
            table="language_derivations",
            identity_column="derivation_id",
            identity=derivation_id,
            actor_id=actor_id,
            notebook_id=notebook_id,
        )
        return _typed(value, LanguageDerivation, "language derivation")

    async def get_authorized_language_derivation_by_cache_key(
        self, *, actor_id: UUID, notebook_id: UUID, cache_key: str
    ) -> LanguageDerivation | None:
        value = await self._authorized_payload(
            table="language_derivations",
            identity_column="cache_key",
            identity=cache_key,
            actor_id=actor_id,
            notebook_id=notebook_id,
        )
        return _typed(value, LanguageDerivation, "language derivation")

    async def put_multilingual_embedding(self, embedding: MultilingualEmbedding) -> bool:
        payload, digest = _payload(embedding)
        db = self._require_open()
        try:
            async with self._multilingual_lock, _transaction(db):
                existing = await _existing_hash(
                    db, "multilingual_embeddings", "embedding_id", embedding.embedding_id
                )
                if existing is not None:
                    if existing != digest:
                        raise ConflictError("multilingual embedding is immutable")
                    return False
                await db.execute(
                    """INSERT INTO multilingual_embeddings(
                       embedding_id,notebook_id,source_evidence_id,language,generation_id,
                       vector_space,payload,payload_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        str(embedding.embedding_id),
                        str(embedding.notebook_id),
                        embedding.source_evidence_id,
                        embedding.language.value,
                        str(embedding.profile.generation_id),
                        embedding.profile.vector_space,
                        payload,
                        digest,
                        embedding.created_at.isoformat(),
                    ),
                )
                return True
        except ConflictError:
            raise
        except aiosqlite.Error as error:
            raise StorageError("could not persist multilingual embedding") from error

    async def get_authorized_multilingual_embedding(
        self, *, notebook_id: UUID, embedding_id: UUID
    ) -> MultilingualEmbedding | None:
        db = self._require_open()
        async with db.execute(
            "SELECT payload,payload_hash FROM multilingual_embeddings "
            "WHERE notebook_id=? AND embedding_id=?",
            (str(notebook_id), str(embedding_id)),
        ) as cursor:
            row = await cursor.fetchone()
        return _typed(_decode_checked(row), MultilingualEmbedding, "multilingual embedding")

    async def list_authorized_multilingual_embeddings(
        self,
        *,
        notebook_id: UUID,
        generation_id: UUID,
        vector_space: str,
        authorized_sources: tuple[LanguageEvidenceReferenceV2, ...],
    ) -> tuple[MultilingualEmbedding, ...]:
        """Enumerate vectors only through an explicit pre-authorized evidence set."""
        if len(authorized_sources) > 10_000:
            raise ValueError("authorized multilingual vector set exceeds 10000")
        if not authorized_sources:
            return ()
        if any(source.notebook_id != notebook_id for source in authorized_sources):
            raise ValueError("authorized multilingual sources cross notebook scope")
        by_id = {source.evidence_id: source for source in authorized_sources}
        if len(by_id) != len(authorized_sources):
            raise ValueError("authorized multilingual source identities must be unique")
        db = self._require_open()
        encoded_ids = json.dumps(sorted(by_id), separators=(",", ":"))
        async with db.execute(
            """SELECT e.payload,e.payload_hash
               FROM multilingual_embeddings AS e
               JOIN json_each(?) AS authorized ON authorized.value=e.source_evidence_id
               WHERE e.notebook_id=? AND e.generation_id=? AND e.vector_space=?
               ORDER BY e.source_evidence_id,e.embedding_id""",
            (encoded_ids, str(notebook_id), str(generation_id), vector_space),
        ) as cursor:
            rows = await cursor.fetchall()
        values: list[MultilingualEmbedding] = []
        for row in rows:
            embedding = _typed(
                _decode_checked(row), MultilingualEmbedding, "multilingual embedding"
            )
            assert embedding is not None
            expected = by_id.get(embedding.source_evidence_id)
            if embedding.source_reference is None or expected != embedding.source_reference:
                raise StorageError("multilingual embedding source authorization mismatch")
            values.append(embedding)
        return tuple(values)

    async def _authorized_payload(
        self,
        *,
        table: str,
        identity_column: str,
        identity: object,
        actor_id: UUID,
        notebook_id: UUID,
    ) -> object | None:
        if table not in {"language_observations", "language_derivations"}:
            raise ValueError("unsupported multilingual table")
        if identity_column not in {"observation_id", "derivation_id", "cache_key"}:
            raise ValueError("unsupported multilingual identity column")
        db = self._require_open()
        query = (
            f"SELECT payload,payload_hash FROM {table} "
            f"WHERE actor_id=? AND notebook_id=? AND {identity_column}=?"
        )
        async with db.execute(query, (str(actor_id), str(notebook_id), str(identity))) as cursor:
            row = await cursor.fetchone()
        return _decode_checked(row)


async def _existing_hash(
    db: aiosqlite.Connection, table: str, identity_column: str, identity: object
) -> str | None:
    query = f"SELECT payload_hash FROM {table} WHERE {identity_column}=?"
    async with db.execute(query, (str(identity),)) as cursor:
        row = await cursor.fetchone()
    return None if row is None else str(row[0])


def _payload(value: object) -> tuple[str, str]:
    payload = _encode(value)
    return payload, hashlib.sha256(payload.encode()).hexdigest()


def multilingual_v2_generation_set_digest(
    *, profile_fingerprint: str, generation_ids: tuple[UUID, ...]
) -> str:
    """Bind an ordered-independent four-generation rollback/activation target."""
    _require_sha256_text(profile_fingerprint, "profile_fingerprint")
    if len(generation_ids) != 4 or len(set(generation_ids)) != 4:
        raise ValueError("V2 generation-set digest requires exactly four generations")
    return hashlib.sha256(
        json.dumps(
            {
                "profile_fingerprint": profile_fingerprint,
                "generation_ids": sorted(str(item) for item in generation_ids),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _require_sha256_text(value: str, name: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{name} must be lowercase SHA-256")


_FTS_TERM_V2 = re.compile(r"[^\W_]+", re.UNICODE)


def _multilingual_fts_query_v2(query: str) -> str:
    terms = _FTS_TERM_V2.findall(query.casefold())
    if not terms:
        raise ValueError("multilingual sparse query has no searchable terms")
    return " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms[:64])


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _decode_checked(row: Sequence[object] | None) -> object | None:
    if row is None:
        return None
    payload, digest = row
    if hashlib.sha256(str(payload).encode()).hexdigest() != str(digest):
        raise StorageError("multilingual record integrity check failed")
    value: object = _decode(str(payload))
    return value


def _typed[T](value: object | None, expected: type[T], name: str) -> T | None:
    if value is None:
        return None
    if not isinstance(value, expected):
        raise StorageError(f"invalid persisted {name}")
    return value
