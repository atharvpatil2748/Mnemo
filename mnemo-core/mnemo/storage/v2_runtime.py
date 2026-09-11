"""Read-only governed storage for the active Full Multilingual V2 runtime."""

from __future__ import annotations

import hashlib
import json
from typing import cast
from uuid import UUID

import aiosqlite

from mnemo.interfaces.errors import StorageError
from mnemo.models.advanced_retrieval import RetrievalScopeV2
from mnemo.models.chunks import Chunk
from mnemo.models.multilingual import LanguageObservationV2, ScriptObservationV1
from mnemo.models.multilingual_generation import MultilingualCoverageManifestV2
from mnemo.models.multilingual_index import MultilingualTextProjectionRowV2
from mnemo.models.text_representations import (
    ObservationKind,
    ObservationReferenceV1,
    RepresentationObservationV1,
    RepresentationTransformationV1,
)
from mnemo.models.v2_retrieval_authorization import V2RetrievalAuthorizationDecisionV1
from mnemo.phase85.v2_readiness import V2GenerationCapability, V2GenerationEvidence
from mnemo.retrieval.final_qa_snapshot import _decode
from mnemo.storage.sqlite import SQLiteStore

MAX_AUTHORIZED_V2_SEMANTIC_ROWS = 10_000
MAX_AUTHORIZED_V2_SEMANTIC_OVERFLOW_PROBE = 10_001


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class SQLiteV2ReadOnlyRuntimeStore(SQLiteStore):
    """SQLiteStore read surface opened with immutable, query-only semantics."""

    async def open(self) -> None:
        if self._db is not None:
            return
        resolved = self._db_path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError("approved V2 runtime database does not exist")
        self._db = await aiosqlite.connect(
            f"file:{resolved.as_posix()}?mode=ro&immutable=1", uri=True
        )
        await self._db.execute("PRAGMA query_only=ON")
        await self._db.execute("PRAGMA foreign_keys=ON")

    async def resolve_active_multilingual_v2_alias_digest(self) -> str | None:
        row = await (
            await self._require_open().execute(
                "SELECT alias_set_digest FROM active_multilingual_v2_alias_set WHERE singleton=1"
            )
        ).fetchone()
        return None if row is None else str(row[0])

    async def inspect_active_v2_generations(
        self, generation_ids: tuple[UUID, ...]
    ) -> tuple[V2GenerationEvidence, ...]:
        if len(generation_ids) != 4 or len(set(generation_ids)) != 4:
            raise StorageError("ACTIVE_GENERATION_INVALID")
        encoded = json.dumps([str(value) for value in generation_ids], separators=(",", ":"))
        rows = tuple(
            await (
                await self._require_open().execute(
                    """SELECT g.generation_id,g.capability,g.profile,g.provider_identity,
                              g.model_identity,g.configuration_digest,g.dimensions,g.state,
                              g.item_count,g.checksum,c.completeness,c.expected_count,
                              c.failed_count,c.checksum,m.payload,m.payload_hash
                       FROM json_each(?) selected
                       JOIN index_generations g ON g.generation_id=selected.value
                       JOIN index_generation_coverage c ON c.generation_id=g.generation_id
                       JOIN multilingual_coverage_manifests_v2 m
                         ON m.generation_id=g.generation_id
                       ORDER BY CASE g.capability
                         WHEN 'representation_derivation_v2' THEN 1
                         WHEN 'language_text_v2' THEN 2
                         WHEN 'multilingual_embedding_v2' THEN 3
                         WHEN 'multilingual_vector_v2' THEN 4 END""",
                    (encoded,),
                )
            ).fetchall()
        )
        if len(rows) != 4:
            raise StorageError("ACTIVE_GENERATION_MISSING")
        source_rows = tuple(
            await (
                await self._require_open().execute(
                    """SELECT generation_id,source_id FROM index_generation_sources
                       WHERE source_kind='generation' AND generation_id IN
                         (SELECT value FROM json_each(?))
                       ORDER BY generation_id,source_id""",
                    (encoded,),
                )
            ).fetchall()
        )
        sources: dict[UUID, list[UUID]] = {}
        for generation_id, source_id in source_rows:
            sources.setdefault(UUID(str(generation_id)), []).append(UUID(str(source_id)))
        values: list[V2GenerationEvidence] = []
        for row in rows:
            manifest = _checked_payload(
                row[14:16], MultilingualCoverageManifestV2, "V2 coverage manifest"
            )
            generation_id = UUID(str(row[0]))
            capability = V2GenerationCapability(str(row[1]))
            if manifest.generation_id != generation_id or manifest.capability != capability.value:
                raise StorageError("ACTIVE_GENERATION_MANIFEST_MISMATCH")
            if not manifest.complete or int(row[12]) != 0:
                raise StorageError("GENERATION_NOT_READY")
            vector_space = (
                None
                if capability
                not in {
                    V2GenerationCapability.MULTILINGUAL_EMBEDDING,
                    V2GenerationCapability.MULTILINGUAL_VECTOR,
                }
                else await self._vector_space_for_generation(generation_id, capability)
            )
            values.append(
                V2GenerationEvidence(
                    capability=capability,
                    generation_id=generation_id,
                    profile_id=str(row[2]),
                    provider_identity=None if row[3] is None else str(row[3]),
                    model_identity=None if row[4] is None else str(row[4]),
                    configuration_digest=str(row[5]),
                    vector_space_identity=vector_space,
                    state=str(row[7]),
                    coverage_completeness=str(row[10]),
                    item_count=int(row[8]),
                    coverage_count=int(row[11]),
                    checksum=str(row[9]),
                    coverage_checksum=str(row[13]),
                    source_generation_ids=tuple(sources.get(generation_id, ())),
                    language_coverage_digest=_digest(manifest.language_tags),
                    script_coverage_digest=_digest(manifest.script_codes),
                    representation_coverage_digest=_digest(manifest.representation_types),
                    provenance_digest=_digest(
                        {
                            "dependency": manifest.dependency_digest,
                            "source_kinds": manifest.source_kinds,
                            "provenance_complete": manifest.provenance_complete,
                            "authorization_compatible": manifest.authorization_compatible,
                        }
                    ),
                )
            )
        return tuple(values)

    async def list_authorized_v2_semantic_rows(
        self,
        *,
        decision: V2RetrievalAuthorizationDecisionV1,
        generation_id: UUID,
        limit: int,
    ) -> tuple[MultilingualTextProjectionRowV2, ...]:
        _validate_decision_generation(decision, generation_id)
        if not 1 <= limit <= MAX_AUTHORIZED_V2_SEMANTIC_OVERFLOW_PROBE:
            raise ValueError("authorized V2 semantic enumeration limit is invalid")
        clauses, params = _scope_clauses(decision.retrieval_scope)
        clauses.extend(_position_clauses(decision, params))
        params.extend((str(generation_id), limit))
        rows = tuple(
            await (
                await self._require_open().execute(
                    f"""SELECT payload,payload_hash FROM language_text_projection_rows_v2
                        WHERE {" AND ".join(clauses)} AND generation_id=?
                        ORDER BY evidence_reference_digest,representation_reference_id LIMIT ?""",
                    tuple(params),
                )
            ).fetchall()
        )
        values = tuple(
            _checked_payload(row, MultilingualTextProjectionRowV2, "V2 semantic row")
            for row in rows
        )
        for value in values:
            _validate_projection_row(value, decision, generation_id)
            await self._validate_observations(value)
        return values

    async def get_authorized_v2_semantic_row(
        self,
        *,
        decision: V2RetrievalAuthorizationDecisionV1,
        generation_id: UUID,
        evidence_reference_digest: str,
        representation_reference_id: UUID,
    ) -> MultilingualTextProjectionRowV2 | None:
        _validate_decision_generation(decision, generation_id)
        clauses, params = _scope_clauses(decision.retrieval_scope)
        clauses.extend(
            ["generation_id=?", "evidence_reference_digest=?", "representation_reference_id=?"]
        )
        params.extend(
            (str(generation_id), evidence_reference_digest, str(representation_reference_id))
        )
        rows = tuple(
            await (
                await self._require_open().execute(
                    f"""SELECT payload,payload_hash FROM language_text_projection_rows_v2
                        WHERE {" AND ".join(clauses)} ORDER BY row_id LIMIT 2""",
                    tuple(params),
                )
            ).fetchall()
        )
        if len(rows) > 1:
            raise StorageError("AMBIGUOUS_V2_SEMANTIC_EVIDENCE")
        if not rows:
            return None
        value = _checked_payload(rows[0], MultilingualTextProjectionRowV2, "V2 semantic row")
        _validate_projection_row(value, decision, generation_id)
        await self._validate_observations(value)
        return value

    async def get_authorized_v2_transformation(
        self,
        *,
        decision: V2RetrievalAuthorizationDecisionV1,
        output_reference_id: UUID,
    ) -> RepresentationTransformationV1 | None:
        rows = tuple(
            await (
                await self._require_open().execute(
                    """SELECT payload,payload_hash FROM representation_transformations_v1
                       WHERE output_reference_id=? ORDER BY transformation_id LIMIT 2""",
                    (str(output_reference_id),),
                )
            ).fetchall()
        )
        if len(rows) > 1:
            raise StorageError("AMBIGUOUS_V2_TRANSFORMATION_LINEAGE")
        if not rows:
            return None
        value = _checked_payload(rows[0], RepresentationTransformationV1, "V2 transformation")
        _validate_source_scope(value.output_reference.evidence_reference, decision.retrieval_scope)
        return value

    async def get_authorized_v2_chunk(
        self,
        *,
        decision: V2RetrievalAuthorizationDecisionV1,
        chunk_id: str,
    ) -> Chunk | None:
        value = await self._get_governed_artifact_chunk(chunk_id)
        if value is None:
            return None
        if value.document_id not in _permitted_or_single(
            decision.retrieval_scope.document_ids, value.document_id
        ) or value.version_id not in _permitted_or_single(
            decision.retrieval_scope.version_ids, value.version_id
        ):
            raise PermissionError("EVIDENCE_SCOPE_MISMATCH")
        return value

    async def _get_governed_artifact_chunk(self, chunk_id: str) -> Chunk | None:
        """Read the immutable governed build schema without requiring later columns.

        The 44-document artifact predates additive ``position_page_start/end``
        columns. ``_chunk_from_row`` already canonically derives those values
        from ``position_page_number`` when absent, so the read-only V2 adapter
        selects only columns physically governed by that artifact.
        """
        row = await (
            await self._require_open().execute(
                """SELECT id,document_id,version_id,text,chunk_type,
                          position_section_index,position_chunk_index,
                          position_page_number,position_start_offset,position_end_offset,
                          source_start_ordinal,source_end_ordinal,heading_path,
                          parent_chunk_id,sibling_ids,metadata
                   FROM chunks WHERE id=?""",
                (chunk_id,),
            )
        ).fetchone()
        return None if row is None else self._chunk_from_row(row)

    async def _validate_observations(self, row: MultilingualTextProjectionRowV2) -> None:
        representation = cast(
            RepresentationObservationV1,
            await self._require_payload_by_id(
                "representation_observations_v1",
                "observation_id",
                row.representation.representation_observation_id,
                RepresentationObservationV1,
                "representation observation",
            ),
        )
        if (
            representation.source_reference != row.source
            or representation.language_observation_references != row.language_observation_references
            or representation.script_observation_references != row.script_observation_references
        ):
            raise StorageError("EVIDENCE_LINEAGE_INVALID")
        for reference in row.language_observation_references:
            language_observation = cast(
                LanguageObservationV2,
                await self._require_payload_by_id(
                    "language_observations_v2",
                    "observation_id",
                    reference.observation_id,
                    LanguageObservationV2,
                    "language observation",
                ),
            )
            _validate_observation_reference(reference, language_observation)
        for reference in row.script_observation_references:
            script_observation = cast(
                ScriptObservationV1,
                await self._require_payload_by_id(
                    "script_observations_v1",
                    "observation_id",
                    reference.observation_id,
                    ScriptObservationV1,
                    "script observation",
                ),
            )
            _validate_observation_reference(reference, script_observation)

    async def _require_payload_by_id(
        self, table: str, column: str, identity: object, expected: type[object], label: str
    ) -> object:
        allowed = {
            ("representation_observations_v1", "observation_id"),
            ("language_observations_v2", "observation_id"),
            ("script_observations_v1", "observation_id"),
        }
        if (table, column) not in allowed:
            raise ValueError("unsupported governed V2 evidence table")
        row = await (
            await self._require_open().execute(
                f"SELECT payload,payload_hash FROM {table} WHERE {column}=?",
                (str(identity),),
            )
        ).fetchone()
        if row is None:
            raise StorageError(f"missing {label}")
        return _checked_payload(row, expected, label)

    async def _vector_space_for_generation(
        self, generation_id: UUID, capability: V2GenerationCapability
    ) -> str:
        lookup_id = generation_id
        if capability is V2GenerationCapability.MULTILINGUAL_VECTOR:
            source_rows = tuple(
                await (
                    await self._require_open().execute(
                        """SELECT source_id FROM index_generation_sources
                           WHERE generation_id=? AND source_kind='generation' LIMIT 2""",
                        (str(generation_id),),
                    )
                ).fetchall()
            )
            if len(source_rows) != 1:
                raise StorageError("VECTOR_EMBEDDING_GENERATION_RELATIONSHIP_MISSING")
            lookup_id = UUID(str(source_rows[0][0]))
        rows = tuple(
            await (
                await self._require_open().execute(
                    """SELECT DISTINCT vector_space FROM multilingual_embeddings_v2
                       WHERE generation_id=? ORDER BY vector_space LIMIT 2""",
                    (str(lookup_id),),
                )
            ).fetchall()
        )
        if len(rows) != 1:
            raise StorageError("VECTOR_SPACE_MISMATCH")
        return str(rows[0][0])


def _checked_payload[T](row: object, expected: type[T], label: str) -> T:
    if not isinstance(row, (tuple, list)) or len(row) != 2:
        raise StorageError(f"invalid persisted {label}")
    payload, payload_hash = str(row[0]), str(row[1])
    if hashlib.sha256(payload.encode()).hexdigest() != payload_hash:
        raise StorageError(f"{label} integrity mismatch")
    value = _decode(payload)
    if not isinstance(value, expected):
        raise StorageError(f"invalid persisted {label}")
    return value


def _scope_clauses(scope: RetrievalScopeV2) -> tuple[list[str], list[object]]:
    clauses = ["notebook_id=?"]
    params: list[object] = [str(scope.notebook_id)]
    for column, values in (
        ("source_id", scope.source_ids),
        ("document_id", scope.document_ids),
        ("version_id", scope.version_ids),
    ):
        if values:
            placeholders = ",".join("?" for _ in values)
            clauses.append(f"{column} IN ({placeholders})")
            params.extend(str(value) for value in values)
    return clauses, params


def _position_clauses(
    decision: V2RetrievalAuthorizationDecisionV1, params: list[object]
) -> list[str]:
    position = decision.positional_scope
    clauses: list[str] = []
    if position.page_start is not None:
        clauses.append("page_number IS NOT NULL AND page_number>=?")
        params.append(position.page_start)
    if position.page_end is not None:
        clauses.append("page_number IS NOT NULL AND page_number<=?")
        params.append(position.page_end)
    if position.section_indexes:
        placeholders = ",".join("?" for _ in position.section_indexes)
        clauses.append(f"section_index IN ({placeholders})")
        params.extend(position.section_indexes)
    if position.heading_prefix:
        prefix = "\x1f".join(position.heading_prefix)
        clauses.append("(heading_path_key=? OR heading_path_key LIKE ? ESCAPE '\\')")
        params.extend((prefix, prefix.replace("%", "\\%").replace("_", "\\_") + "\x1f%"))
    return clauses


def _validate_decision_generation(
    decision: V2RetrievalAuthorizationDecisionV1, generation_id: UUID
) -> None:
    if decision.operation != "retrieve":
        raise PermissionError("AUTHORIZATION_DENIED")
    if generation_id not in decision.runtime_binding.generation_ids:
        raise PermissionError("GENERATION_MISMATCH")


def _validate_projection_row(
    row: MultilingualTextProjectionRowV2,
    decision: V2RetrievalAuthorizationDecisionV1,
    generation_id: UUID,
) -> None:
    if row.generation_id != generation_id:
        raise StorageError("GENERATION_MISMATCH")
    _validate_source_scope(row.source, decision.retrieval_scope)
    if row.text_hash != hashlib.sha256(row.text.encode()).hexdigest():
        raise StorageError("SEMANTIC_TEXT_HASH_MISMATCH")


def _validate_source_scope(source: object, scope: RetrievalScopeV2) -> None:
    for name, allowed in (
        ("notebook_id", (scope.notebook_id,)),
        ("source_id", scope.source_ids),
        ("document_id", scope.document_ids),
        ("version_id", scope.version_ids),
    ):
        actual = getattr(source, name)
        if allowed and actual not in allowed:
            raise PermissionError("EVIDENCE_SCOPE_MISMATCH")


def _permitted_or_single(values: tuple[UUID, ...], actual: UUID) -> tuple[UUID, ...]:
    return values or (actual,)


def _validate_observation_reference(
    reference: ObservationReferenceV1,
    observation: LanguageObservationV2 | ScriptObservationV1,
) -> None:
    expected_kind = (
        ObservationKind.LANGUAGE
        if isinstance(observation, LanguageObservationV2)
        else ObservationKind.SCRIPT
    )
    expected_digest = _digest(
        {
            "observation_id": str(observation.observation_id),
            "configuration_digest": observation.configuration_digest,
            "input_hash": observation.input_hash,
            "source_reference_digest": (
                None
                if observation.source_reference is None
                else observation.source_reference.identity_digest
            ),
        }
    )
    if (
        reference.observation_kind is not expected_kind
        or reference.observation_id != observation.observation_id
        or reference.observation_digest != expected_digest
    ):
        raise StorageError("EVIDENCE_LINEAGE_INVALID")
