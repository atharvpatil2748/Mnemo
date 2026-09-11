"""SQLite persistence for immutable vision and visual-vector derivations."""

# SQL remains deliberately explicit for migration review.
# ruff: noqa: E501

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import cast
from uuid import UUID

import aiosqlite

from mnemo.interfaces.errors import ConflictError, IntegrityError, StorageError
from mnemo.models import AssetDerivationStatus, FrozenMetadata
from mnemo.models.vision import (
    VisionCapability,
    VisionCaption,
    VisionCompleteness,
    VisionConfidence,
    VisionEntity,
    VisionFailure,
    VisionFailureClass,
    VisionLanguageObservation,
    VisionObservation,
    VisionProviderMetadata,
    VisionRegion,
    VisionRelation,
    VisionResult,
    VisualDistanceMetric,
    VisualEmbedding,
    VisualEmbeddingCapability,
    VisualEmbeddingProfile,
    VisualEmbeddingProviderMetadata,
    VisualNormalization,
)

VISION_SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS vision_results (
        derivation_id TEXT PRIMARY KEY REFERENCES asset_derivations(derivation_id) ON DELETE RESTRICT,
        cache_key TEXT NOT NULL UNIQUE,
        document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE RESTRICT,
        version_id TEXT NOT NULL REFERENCES document_versions(version_id) ON DELETE RESTRICT,
        occurrence_id TEXT NOT NULL REFERENCES asset_occurrences(occurrence_id) ON DELETE RESTRICT,
        asset_id TEXT NOT NULL REFERENCES asset_catalog(asset_id) ON DELETE RESTRICT,
        generation_id TEXT NOT NULL,
        preprocessing_digest TEXT NOT NULL,
        completeness TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS visual_embeddings (
        derivation_id TEXT PRIMARY KEY REFERENCES asset_derivations(derivation_id) ON DELETE RESTRICT,
        cache_key TEXT NOT NULL UNIQUE,
        document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE RESTRICT,
        version_id TEXT NOT NULL REFERENCES document_versions(version_id) ON DELETE RESTRICT,
        occurrence_id TEXT NOT NULL REFERENCES asset_occurrences(occurrence_id) ON DELETE RESTRICT,
        asset_id TEXT NOT NULL REFERENCES asset_catalog(asset_id) ON DELETE RESTRICT,
        generation_id TEXT NOT NULL,
        source_vision_derivation_id TEXT,
        preprocessing_digest TEXT NOT NULL,
        dimensions INTEGER NOT NULL CHECK(dimensions > 0),
        metric TEXT NOT NULL,
        normalization TEXT NOT NULL,
        shared_space_id TEXT,
        vector_hash TEXT NOT NULL,
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS visual_vector_projection_rows (
        generation_id TEXT NOT NULL REFERENCES index_generations(generation_id) ON DELETE RESTRICT,
        derivation_id TEXT NOT NULL REFERENCES visual_embeddings(derivation_id) ON DELETE RESTRICT,
        occurrence_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        version_id TEXT NOT NULL,
        vector_hash TEXT NOT NULL,
        PRIMARY KEY(generation_id, derivation_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_vision_results_scope ON vision_results(document_id, version_id, occurrence_id)",
    "CREATE INDEX IF NOT EXISTS idx_vision_results_generation ON vision_results(generation_id, completeness)",
    "CREATE INDEX IF NOT EXISTS idx_visual_embeddings_scope ON visual_embeddings(document_id, version_id, occurrence_id)",
    "CREATE INDEX IF NOT EXISTS idx_visual_embeddings_generation ON visual_embeddings(generation_id, dimensions, metric, normalization)",
    "CREATE INDEX IF NOT EXISTS idx_visual_projection_generation ON visual_vector_projection_rows(generation_id, document_id, version_id)",
)


@asynccontextmanager
async def _transaction(db: aiosqlite.Connection) -> AsyncIterator[None]:
    try:
        await db.execute("BEGIN IMMEDIATE")
        yield
        await db.commit()
    except BaseException as error:
        await db.rollback()
        if isinstance(error, aiosqlite.Error):
            raise StorageError("vision transaction failed") from error
        raise


class SQLiteVisionMixin:
    """Additive immutable vision persistence mixed into SQLiteStore."""

    _vision_lock: asyncio.Lock

    def _require_open(self) -> aiosqlite.Connection:
        raise NotImplementedError

    @asynccontextmanager
    async def _vision_transaction(self, db: aiosqlite.Connection) -> AsyncIterator[None]:
        async with self._vision_lock, _transaction(db):
            yield

    async def put_vision_result(self, result: VisionResult) -> bool:
        db = self._require_open()
        async with self._vision_transaction(db):
            await _verify_provenance(
                db,
                result.derivation_id,
                result.occurrence_id,
                result.asset_id,
                result.document_id,
                result.version_id,
            )
            existing = await (
                await db.execute(
                    "SELECT content_hash,cache_key FROM vision_results WHERE derivation_id=?",
                    (str(result.derivation_id),),
                )
            ).fetchone()
            if existing is not None:
                if existing != (result.content_hash, result.cache_key):
                    raise ConflictError("vision derivation result is immutable")
                return False
            await db.execute(
                """INSERT INTO vision_results(
                    derivation_id,cache_key,document_id,version_id,occurrence_id,asset_id,
                    generation_id,preprocessing_digest,completeness,content_hash,payload,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(result.derivation_id),
                    result.cache_key,
                    str(result.document_id),
                    str(result.version_id),
                    str(result.occurrence_id),
                    str(result.asset_id),
                    str(result.generation_id),
                    result.preprocessing_digest,
                    result.completeness.value,
                    result.content_hash,
                    _vision_payload(result),
                    result.created_at.isoformat(),
                ),
            )
            status = (
                AssetDerivationStatus.FAILED
                if result.completeness
                in {VisionCompleteness.FAILED, VisionCompleteness.UNAVAILABLE}
                else AssetDerivationStatus.SUCCEEDED
            )
            cursor = await db.execute(
                """UPDATE asset_derivations SET status=?,output_payload=?,updated_at=?
                   WHERE derivation_id=? AND status IN (?,?)""",
                (
                    status.value,
                    json.dumps(
                        {
                            "content_hash": result.content_hash,
                            "completeness": result.completeness.value,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    result.created_at.isoformat(),
                    str(result.derivation_id),
                    AssetDerivationStatus.PENDING.value,
                    AssetDerivationStatus.RUNNING.value,
                ),
            )
            if cursor.rowcount != 1:
                raise ConflictError("vision derivation lifecycle changed before publication")
            return True

    async def get_authorized_vision_result(
        self, *, notebook_id: UUID, derivation_id: UUID
    ) -> VisionResult | None:
        row = await (
            await self._require_open().execute(
                """SELECT r.payload FROM vision_results r JOIN sources s ON s.document_id=r.document_id
               WHERE r.derivation_id=? AND s.notebook_id=?""",
                (str(derivation_id), str(notebook_id)),
            )
        ).fetchone()
        return None if row is None else _vision_from_payload(row[0])

    async def get_authorized_vision_result_by_cache_key(
        self, *, notebook_id: UUID, cache_key: str
    ) -> VisionResult | None:
        row = await (
            await self._require_open().execute(
                """SELECT r.payload FROM vision_results r JOIN sources s ON s.document_id=r.document_id
               WHERE r.cache_key=? AND s.notebook_id=?""",
                (cache_key, str(notebook_id)),
            )
        ).fetchone()
        return None if row is None else _vision_from_payload(row[0])

    async def put_visual_embedding(self, embedding: VisualEmbedding) -> bool:
        db = self._require_open()
        async with self._vision_transaction(db):
            await _verify_provenance(
                db,
                embedding.derivation_id,
                embedding.occurrence_id,
                embedding.asset_id,
                embedding.document_id,
                embedding.version_id,
            )
            existing = await (
                await db.execute(
                    "SELECT vector_hash,cache_key FROM visual_embeddings WHERE derivation_id=?",
                    (str(embedding.derivation_id),),
                )
            ).fetchone()
            if existing is not None:
                if existing != (embedding.vector_hash, embedding.cache_key):
                    raise ConflictError("visual embedding derivation is immutable")
                return False
            if embedding.source_vision_derivation_id is not None:
                parent = await (
                    await db.execute(
                        "SELECT occurrence_id FROM vision_results WHERE derivation_id=?",
                        (str(embedding.source_vision_derivation_id),),
                    )
                ).fetchone()
                if parent is None or parent[0] != str(embedding.occurrence_id):
                    raise IntegrityError("visual embedding parent vision derivation is unavailable")
            await db.execute(
                """INSERT INTO visual_embeddings(
                    derivation_id,cache_key,document_id,version_id,occurrence_id,asset_id,
                    generation_id,source_vision_derivation_id,preprocessing_digest,dimensions,
                    metric,normalization,shared_space_id,vector_hash,payload,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(embedding.derivation_id),
                    embedding.cache_key,
                    str(embedding.document_id),
                    str(embedding.version_id),
                    str(embedding.occurrence_id),
                    str(embedding.asset_id),
                    str(embedding.generation_id),
                    None
                    if embedding.source_vision_derivation_id is None
                    else str(embedding.source_vision_derivation_id),
                    embedding.preprocessing_digest,
                    embedding.dimensions,
                    embedding.metric.value,
                    embedding.normalization.value,
                    embedding.shared_space_id,
                    embedding.vector_hash,
                    _embedding_payload(embedding),
                    embedding.created_at.isoformat(),
                ),
            )
            cursor = await db.execute(
                """UPDATE asset_derivations SET status=?,output_payload=?,updated_at=?
                   WHERE derivation_id=? AND status IN (?,?)""",
                (
                    AssetDerivationStatus.SUCCEEDED.value,
                    json.dumps(
                        {"vector_hash": embedding.vector_hash, "dimensions": embedding.dimensions},
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    embedding.created_at.isoformat(),
                    str(embedding.derivation_id),
                    AssetDerivationStatus.PENDING.value,
                    AssetDerivationStatus.RUNNING.value,
                ),
            )
            if cursor.rowcount != 1:
                raise ConflictError("visual embedding lifecycle changed before publication")
            return True

    async def get_authorized_visual_embedding(
        self, *, notebook_id: UUID, derivation_id: UUID
    ) -> VisualEmbedding | None:
        row = await (
            await self._require_open().execute(
                """SELECT e.payload FROM visual_embeddings e JOIN sources s ON s.document_id=e.document_id
               WHERE e.derivation_id=? AND s.notebook_id=?""",
                (str(derivation_id), str(notebook_id)),
            )
        ).fetchone()
        return None if row is None else _embedding_from_payload(row[0])

    async def get_authorized_visual_embedding_by_cache_key(
        self, *, notebook_id: UUID, cache_key: str
    ) -> VisualEmbedding | None:
        row = await (
            await self._require_open().execute(
                """SELECT e.payload FROM visual_embeddings e JOIN sources s ON s.document_id=e.document_id
               WHERE e.cache_key=? AND s.notebook_id=?""",
                (cache_key, str(notebook_id)),
            )
        ).fetchone()
        return None if row is None else _embedding_from_payload(row[0])

    async def project_visual_embedding(
        self, *, generation_id: UUID, embedding: VisualEmbedding
    ) -> bool:
        db = self._require_open()
        async with self._vision_transaction(db):
            stored = await (
                await db.execute(
                    "SELECT vector_hash FROM visual_embeddings WHERE derivation_id=?",
                    (str(embedding.derivation_id),),
                )
            ).fetchone()
            if stored is None or stored[0] != embedding.vector_hash:
                raise IntegrityError("visual projection requires the immutable stored embedding")
            generation = await (
                await db.execute(
                    """SELECT capability,profile,state,configuration_digest,dimensions,
                          provider_identity,model_identity FROM index_generations WHERE generation_id=?""",
                    (str(generation_id),),
                )
            ).fetchone()
            if (
                generation is None
                or generation[0] != "visual_vector"
                or generation[2] != "building"
            ):
                raise ConflictError(
                    "visual projection requires a BUILDING visual_vector generation"
                )
            expected_config = _embedding_generation_digest(embedding)
            if (
                generation[1] != embedding.provider.profile_id
                or generation[3] != expected_config
                or generation[4] != embedding.dimensions
                or generation[5] != embedding.provider.provider_identity
                or generation[6]
                != f"{embedding.provider.model_identity}@{embedding.provider.model_revision}"
            ):
                raise IntegrityError("visual embedding does not match its generation contract")
            source = await (
                await db.execute(
                    """SELECT 1 FROM index_generation_sources
                       WHERE generation_id=? AND source_kind='generation' AND source_id=?""",
                    (str(generation_id), str(embedding.generation_id)),
                )
            ).fetchone()
            if source is None:
                raise IntegrityError("visual embedding is outside the projection source contract")
            cursor = await db.execute(
                """INSERT OR IGNORE INTO visual_vector_projection_rows(
                    generation_id,derivation_id,occurrence_id,document_id,version_id,vector_hash
                ) VALUES(?,?,?,?,?,?)""",
                (
                    str(generation_id),
                    str(embedding.derivation_id),
                    str(embedding.occurrence_id),
                    str(embedding.document_id),
                    str(embedding.version_id),
                    embedding.vector_hash,
                ),
            )
            return cursor.rowcount == 1

    async def list_visual_projection_derivations(self, *, generation_id: UUID) -> tuple[UUID, ...]:
        rows = await (
            await self._require_open().execute(
                "SELECT derivation_id FROM visual_vector_projection_rows WHERE generation_id=? ORDER BY derivation_id",
                (str(generation_id),),
            )
        ).fetchall()
        return tuple(UUID(row[0]) for row in rows)


async def _verify_provenance(
    db: aiosqlite.Connection,
    derivation_id: UUID,
    occurrence_id: UUID,
    asset_id: UUID,
    document_id: UUID,
    version_id: UUID,
) -> None:
    row = await (
        await db.execute(
            """SELECT 1 FROM asset_occurrences o JOIN asset_derivations d ON d.occurrence_id=o.occurrence_id
           WHERE d.derivation_id=? AND o.occurrence_id=? AND o.asset_id=? AND o.document_id=? AND o.version_id=?""",
            (
                str(derivation_id),
                str(occurrence_id),
                str(asset_id),
                str(document_id),
                str(version_id),
            ),
        )
    ).fetchone()
    if row is None:
        raise IntegrityError("derived vision provenance does not match its derivation")


def visual_generation_configuration_digest(profile: VisualEmbeddingProfile) -> str:
    """Public deterministic generation contract used by builders/tests."""
    return _visual_generation_contract_digest(
        preprocessing_digest=profile.preprocessing_digest,
        metric=profile.metric,
        normalization=profile.normalization,
        shared_space_id=profile.shared_space_id,
        dimensions=profile.dimensions,
    )


def _visual_generation_contract_digest(
    *,
    preprocessing_digest: str,
    metric: VisualDistanceMetric,
    normalization: VisualNormalization,
    shared_space_id: str | None,
    dimensions: int,
) -> str:
    material = json.dumps(
        {
            "preprocessing_digest": preprocessing_digest,
            "metric": metric.value,
            "normalization": normalization.value,
            "shared_space_id": shared_space_id,
            "dimensions": dimensions,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode()).hexdigest()


def _embedding_generation_digest(embedding: VisualEmbedding) -> str:
    return _visual_generation_contract_digest(
        preprocessing_digest=embedding.preprocessing_digest,
        metric=embedding.metric,
        normalization=embedding.normalization,
        shared_space_id=embedding.shared_space_id,
        dimensions=embedding.dimensions,
    )


def _confidence_payload(value: VisionConfidence) -> float | None:
    return value.value


def _language_payload(value: VisionLanguageObservation) -> dict[str, object]:
    return {
        "language_code": value.language_code,
        "script": value.script,
        "confidence": value.confidence.value,
        "mixed": value.mixed,
    }


def _language(raw: dict[str, object]) -> VisionLanguageObservation:
    confidence = cast(float | None, raw["confidence"])
    return VisionLanguageObservation(
        language_code=None if raw["language_code"] is None else str(raw["language_code"]),
        script=None if raw["script"] is None else str(raw["script"]),
        confidence=VisionConfidence(value=confidence),
        mixed=bool(raw["mixed"]),
    )


def _vision_payload(result: VisionResult) -> str:
    provider = result.provider
    capability = provider.capability
    value = {
        "derivation_id": str(result.derivation_id),
        "cache_key": result.cache_key,
        "document_id": str(result.document_id),
        "version_id": str(result.version_id),
        "occurrence_id": str(result.occurrence_id),
        "asset_id": str(result.asset_id),
        "generation_id": str(result.generation_id),
        "preprocessing_digest": result.preprocessing_digest,
        "completeness": result.completeness.value,
        "inputs_submitted": result.inputs_submitted,
        "inputs_succeeded": result.inputs_succeeded,
        "content_hash": result.content_hash,
        "created_at": result.created_at.isoformat(),
        "warnings": result.warnings,
        "provider": {
            "provider_identity": provider.provider_identity,
            "model_identity": provider.model_identity,
            "model_revision": provider.model_revision,
            "profile_id": provider.profile_id,
            "capability": {
                "supported_media_types": capability.supported_media_types,
                "supported_languages": capability.supported_languages,
                "max_width": capability.max_width,
                "max_height": capability.max_height,
                "max_pixels": capability.max_pixels,
                "max_response_bytes": capability.max_response_bytes,
                "max_captions": capability.max_captions,
                "max_entities": capability.max_entities,
                "max_regions": capability.max_regions,
                "max_relations": capability.max_relations,
                "geometry": capability.geometry,
                "confidence": capability.confidence,
                "cancellation": capability.cancellation,
            },
        },
        "captions": [
            {
                "text": x.text,
                "confidence": x.confidence.value,
                "language": None if x.language is None else _language_payload(x.language),
            }
            for x in result.captions
        ],
        "regions": [
            {
                "region_id": str(x.region_id),
                "order_index": x.order_index,
                "bounding_box": x.bounding_box,
            }
            for x in result.regions
        ],
        "entities": [
            {
                "entity_id": str(x.entity_id),
                "order_index": x.order_index,
                "label": x.label,
                "attributes": dict(x.attributes),
                "region_id": None if x.region_id is None else str(x.region_id),
                "confidence": x.confidence.value,
            }
            for x in result.entities
        ],
        "relations": [
            {
                "source": str(x.source_entity_id),
                "target": str(x.target_entity_id),
                "relation": x.relation,
                "confidence": x.confidence.value,
            }
            for x in result.relations
        ],
        "observations": [
            {
                "order_index": x.order_index,
                "kind": x.kind,
                "value": x.value,
                "region_id": None if x.region_id is None else str(x.region_id),
                "confidence": x.confidence.value,
            }
            for x in result.observations
        ],
        "languages": [_language_payload(x) for x in result.languages],
        "failures": [
            {
                "input_index": x.input_index,
                "classification": x.classification.value,
                "reason_code": x.reason_code,
                "retryable": x.retryable,
            }
            for x in result.failures
        ],
    }
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _vision_from_payload(value: str) -> VisionResult:
    raw = json.loads(value)
    p, c = raw["provider"], raw["provider"]["capability"]
    provider = VisionProviderMetadata(
        provider_identity=p["provider_identity"],
        model_identity=p["model_identity"],
        model_revision=p["model_revision"],
        profile_id=p["profile_id"],
        capability=VisionCapability(
            supported_media_types=tuple(c["supported_media_types"]),
            supported_languages=tuple(c["supported_languages"]),
            max_width=c["max_width"],
            max_height=c["max_height"],
            max_pixels=c["max_pixels"],
            max_response_bytes=c["max_response_bytes"],
            max_captions=c["max_captions"],
            max_entities=c["max_entities"],
            max_regions=c["max_regions"],
            max_relations=c["max_relations"],
            geometry=c["geometry"],
            confidence=c["confidence"],
            cancellation=c["cancellation"],
        ),
    )
    captions = tuple(
        VisionCaption(
            text=x["text"],
            confidence=VisionConfidence(value=x["confidence"]),
            language=None if x["language"] is None else _language(x["language"]),
        )
        for x in raw["captions"]
    )
    regions = tuple(
        VisionRegion(
            region_id=UUID(x["region_id"]),
            order_index=x["order_index"],
            bounding_box=None if x["bounding_box"] is None else tuple(x["bounding_box"]),
        )
        for x in raw["regions"]
    )
    entities = tuple(
        VisionEntity(
            entity_id=UUID(x["entity_id"]),
            order_index=x["order_index"],
            label=x["label"],
            attributes=FrozenMetadata(x["attributes"]),
            region_id=None if x["region_id"] is None else UUID(x["region_id"]),
            confidence=VisionConfidence(value=x["confidence"]),
        )
        for x in raw["entities"]
    )
    relations = tuple(
        VisionRelation(
            source_entity_id=UUID(x["source"]),
            target_entity_id=UUID(x["target"]),
            relation=x["relation"],
            confidence=VisionConfidence(value=x["confidence"]),
        )
        for x in raw["relations"]
    )
    observations = tuple(
        VisionObservation(
            order_index=x["order_index"],
            kind=x["kind"],
            value=x["value"],
            region_id=None if x["region_id"] is None else UUID(x["region_id"]),
            confidence=VisionConfidence(value=x["confidence"]),
        )
        for x in raw["observations"]
    )
    failures = tuple(
        VisionFailure(
            input_index=x["input_index"],
            classification=VisionFailureClass(x["classification"]),
            reason_code=x["reason_code"],
            retryable=x["retryable"],
        )
        for x in raw["failures"]
    )
    return VisionResult(
        derivation_id=UUID(raw["derivation_id"]),
        cache_key=raw["cache_key"],
        document_id=UUID(raw["document_id"]),
        version_id=UUID(raw["version_id"]),
        occurrence_id=UUID(raw["occurrence_id"]),
        asset_id=UUID(raw["asset_id"]),
        generation_id=UUID(raw["generation_id"]),
        provider=provider,
        preprocessing_digest=raw["preprocessing_digest"],
        completeness=VisionCompleteness(raw["completeness"]),
        captions=captions,
        observations=observations,
        regions=regions,
        entities=entities,
        relations=relations,
        languages=tuple(_language(x) for x in raw["languages"]),
        failures=failures,
        inputs_submitted=raw["inputs_submitted"],
        inputs_succeeded=raw["inputs_succeeded"],
        content_hash=raw["content_hash"],
        created_at=datetime.fromisoformat(raw["created_at"]),
        warnings=tuple(raw["warnings"]),
    )


def _embedding_payload(value: VisualEmbedding) -> str:
    provider, capability = value.provider, value.provider.capability
    raw = {
        "derivation_id": str(value.derivation_id),
        "cache_key": value.cache_key,
        "document_id": str(value.document_id),
        "version_id": str(value.version_id),
        "occurrence_id": str(value.occurrence_id),
        "asset_id": str(value.asset_id),
        "generation_id": str(value.generation_id),
        "source_vision_derivation_id": None
        if value.source_vision_derivation_id is None
        else str(value.source_vision_derivation_id),
        "preprocessing_digest": value.preprocessing_digest,
        "dimensions": value.dimensions,
        "metric": value.metric.value,
        "normalization": value.normalization.value,
        "shared_space_id": value.shared_space_id,
        "vector": value.vector,
        "vector_hash": value.vector_hash,
        "created_at": value.created_at.isoformat(),
        "provider": {
            "provider_identity": provider.provider_identity,
            "model_identity": provider.model_identity,
            "model_revision": provider.model_revision,
            "profile_id": provider.profile_id,
            "capability": {
                "supported_media_types": capability.supported_media_types,
                "dimensions": capability.dimensions,
                "metric": capability.metric.value,
                "normalization": capability.normalization.value,
                "shared_space_id": capability.shared_space_id,
                "max_width": capability.max_width,
                "max_height": capability.max_height,
                "max_pixels": capability.max_pixels,
                "max_bytes": capability.max_bytes,
                "cancellation": capability.cancellation,
            },
        },
    }
    return json.dumps(raw, sort_keys=True, separators=(",", ":"))


def _embedding_from_payload(value: str) -> VisualEmbedding:
    raw = json.loads(value)
    p, c = raw["provider"], raw["provider"]["capability"]
    capability = VisualEmbeddingCapability(
        supported_media_types=tuple(c["supported_media_types"]),
        dimensions=c["dimensions"],
        metric=VisualDistanceMetric(c["metric"]),
        normalization=VisualNormalization(c["normalization"]),
        shared_space_id=c["shared_space_id"],
        max_width=c["max_width"],
        max_height=c["max_height"],
        max_pixels=c["max_pixels"],
        max_bytes=c["max_bytes"],
        cancellation=c["cancellation"],
    )
    provider = VisualEmbeddingProviderMetadata(
        provider_identity=p["provider_identity"],
        model_identity=p["model_identity"],
        model_revision=p["model_revision"],
        profile_id=p["profile_id"],
        capability=capability,
    )
    return VisualEmbedding(
        derivation_id=UUID(raw["derivation_id"]),
        cache_key=raw["cache_key"],
        document_id=UUID(raw["document_id"]),
        version_id=UUID(raw["version_id"]),
        occurrence_id=UUID(raw["occurrence_id"]),
        asset_id=UUID(raw["asset_id"]),
        generation_id=UUID(raw["generation_id"]),
        source_vision_derivation_id=None
        if raw["source_vision_derivation_id"] is None
        else UUID(raw["source_vision_derivation_id"]),
        provider=provider,
        preprocessing_digest=raw["preprocessing_digest"],
        dimensions=raw["dimensions"],
        metric=VisualDistanceMetric(raw["metric"]),
        normalization=VisualNormalization(raw["normalization"]),
        shared_space_id=raw["shared_space_id"],
        vector=tuple(raw["vector"]),
        vector_hash=raw["vector_hash"],
        created_at=datetime.fromisoformat(raw["created_at"]),
    )
