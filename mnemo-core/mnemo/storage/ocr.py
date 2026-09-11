"""SQLite persistence for immutable OCR derivations and projections."""

# SQL remains deliberately explicit for migration review.
# ruff: noqa: E501

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import cast
from uuid import UUID

import aiosqlite

from mnemo.interfaces.errors import ConflictError, IntegrityError, StorageError
from mnemo.models import AssetDerivationStatus
from mnemo.models.ocr import (
    OCRCapability,
    OCRCompleteness,
    OCRConfidence,
    OCRConfidenceBand,
    OCRFailure,
    OCRFailureClass,
    OCRLanguageObservation,
    OCRProviderMetadata,
    OCRRegion,
    OCRResult,
)

OCR_SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS ocr_results (
        derivation_id TEXT PRIMARY KEY REFERENCES asset_derivations(derivation_id) ON DELETE RESTRICT,
        cache_key TEXT NOT NULL UNIQUE,
        document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE RESTRICT,
        version_id TEXT NOT NULL REFERENCES document_versions(version_id) ON DELETE RESTRICT,
        occurrence_id TEXT NOT NULL REFERENCES asset_occurrences(occurrence_id) ON DELETE RESTRICT,
        asset_id TEXT NOT NULL REFERENCES asset_catalog(asset_id) ON DELETE RESTRICT,
        generation_id TEXT NOT NULL,
        provider_metadata TEXT NOT NULL,
        preprocessing_digest TEXT NOT NULL,
        completeness TEXT NOT NULL,
        pages_submitted INTEGER NOT NULL CHECK(pages_submitted >= 0),
        pages_succeeded INTEGER NOT NULL CHECK(pages_succeeded >= 0),
        content_hash TEXT NOT NULL,
        warnings TEXT NOT NULL,
        schema_version INTEGER NOT NULL CHECK(schema_version > 0),
        created_at TEXT NOT NULL,
        CHECK(pages_succeeded <= pages_submitted)
    )""",
    """CREATE TABLE IF NOT EXISTS ocr_regions (
        region_id TEXT PRIMARY KEY,
        derivation_id TEXT NOT NULL REFERENCES ocr_results(derivation_id) ON DELETE CASCADE,
        page_number INTEGER NOT NULL CHECK(page_number > 0),
        order_index INTEGER NOT NULL CHECK(order_index >= 0),
        text TEXT NOT NULL,
        bounding_box TEXT,
        confidence_value REAL,
        confidence_band TEXT NOT NULL,
        language_code TEXT,
        script TEXT,
        language_confidence_value REAL,
        language_confidence_band TEXT,
        language_mixed INTEGER,
        evidence_kind TEXT NOT NULL CHECK(evidence_kind = 'derived_ocr'),
        UNIQUE(derivation_id, page_number, order_index)
    )""",
    """CREATE TABLE IF NOT EXISTS ocr_language_observations (
        derivation_id TEXT NOT NULL REFERENCES ocr_results(derivation_id) ON DELETE CASCADE,
        observation_index INTEGER NOT NULL CHECK(observation_index >= 0),
        language_code TEXT,
        script TEXT,
        confidence_value REAL,
        confidence_band TEXT NOT NULL,
        mixed INTEGER NOT NULL,
        PRIMARY KEY(derivation_id, observation_index)
    )""",
    """CREATE TABLE IF NOT EXISTS ocr_failures (
        derivation_id TEXT NOT NULL REFERENCES ocr_results(derivation_id) ON DELETE CASCADE,
        failure_index INTEGER NOT NULL CHECK(failure_index >= 0),
        page_number INTEGER,
        classification TEXT NOT NULL,
        reason_code TEXT NOT NULL,
        retryable INTEGER NOT NULL,
        PRIMARY KEY(derivation_id, failure_index)
    )""",
    """CREATE TABLE IF NOT EXISTS ocr_projection_rows (
        generation_id TEXT NOT NULL REFERENCES index_generations(generation_id) ON DELETE RESTRICT,
        region_id TEXT NOT NULL REFERENCES ocr_regions(region_id) ON DELETE RESTRICT,
        derivation_id TEXT NOT NULL REFERENCES ocr_results(derivation_id) ON DELETE RESTRICT,
        occurrence_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        version_id TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        PRIMARY KEY(generation_id, region_id)
    )""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS ocr_fts USING fts5(
        text,
        generation_id UNINDEXED,
        region_id UNINDEXED,
        derivation_id UNINDEXED,
        occurrence_id UNINDEXED,
        document_id UNINDEXED,
        version_id UNINDEXED,
        tokenize='unicode61'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_ocr_results_scope ON ocr_results(document_id, version_id, occurrence_id)",
    "CREATE INDEX IF NOT EXISTS idx_ocr_results_generation ON ocr_results(generation_id, completeness)",
    "CREATE INDEX IF NOT EXISTS idx_ocr_regions_derivation ON ocr_regions(derivation_id, page_number, order_index)",
    "CREATE INDEX IF NOT EXISTS idx_ocr_projection_derivation ON ocr_projection_rows(generation_id, derivation_id)",
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
            raise StorageError("OCR transaction failed") from error
        raise


def _confidence(value: float | None, band: str | None) -> OCRConfidence:
    return OCRConfidence(
        value=value,
        band=OCRConfidenceBand.UNAVAILABLE if band is None else OCRConfidenceBand(band),
    )


def _provider_payload(provider: OCRProviderMetadata) -> str:
    capability = provider.capability
    return json.dumps(
        {
            "provider_identity": provider.provider_identity,
            "model_identity": provider.model_identity,
            "model_revision": provider.model_revision,
            "profile_id": provider.profile_id,
            "capability": {
                "supported_media_types": capability.supported_media_types,
                "supported_languages": capability.supported_languages,
                "supported_scripts": capability.supported_scripts,
                "max_pages": capability.max_pages,
                "max_pixels": capability.max_pixels,
                "geometry": capability.geometry,
                "confidence": capability.confidence,
                "cancellation": capability.cancellation,
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _provider(value: str) -> OCRProviderMetadata:
    raw = json.loads(value)
    capability = raw["capability"]
    return OCRProviderMetadata(
        provider_identity=raw["provider_identity"],
        model_identity=raw["model_identity"],
        model_revision=raw["model_revision"],
        profile_id=raw["profile_id"],
        capability=OCRCapability(
            supported_media_types=tuple(capability.get("supported_media_types", ())),
            supported_languages=tuple(capability["supported_languages"]),
            supported_scripts=tuple(capability["supported_scripts"]),
            max_pages=int(capability["max_pages"]),
            max_pixels=int(capability["max_pixels"]),
            geometry=bool(capability["geometry"]),
            confidence=bool(capability["confidence"]),
            cancellation=bool(capability["cancellation"]),
        ),
    )


class SQLiteOCRMixin:
    """Additive OCR persistence mixed into the canonical SQLite store."""

    _ocr_lock: asyncio.Lock

    def _require_open(self) -> aiosqlite.Connection:
        raise NotImplementedError

    @asynccontextmanager
    async def _ocr_transaction(self, db: aiosqlite.Connection) -> AsyncIterator[None]:
        async with self._ocr_lock, _transaction(db):
            yield

    async def put_ocr_result(self, result: OCRResult) -> bool:
        db = self._require_open()
        async with self._ocr_transaction(db):
            provenance = await (
                await db.execute(
                    """SELECT 1 FROM asset_occurrences o
                       JOIN asset_derivations d ON d.occurrence_id=o.occurrence_id
                       WHERE d.derivation_id=? AND o.occurrence_id=? AND o.asset_id=?
                         AND o.document_id=? AND o.version_id=?""",
                    (
                        str(result.derivation_id),
                        str(result.occurrence_id),
                        str(result.asset_id),
                        str(result.document_id),
                        str(result.version_id),
                    ),
                )
            ).fetchone()
            if provenance is None:
                raise IntegrityError("OCR result provenance does not match its derivation")
            existing = await (
                await db.execute(
                    "SELECT content_hash,cache_key FROM ocr_results WHERE derivation_id=?",
                    (str(result.derivation_id),),
                )
            ).fetchone()
            if existing is not None:
                if existing != (result.content_hash, result.cache_key):
                    raise ConflictError("OCR derivation result is immutable")
                return False
            await db.execute(
                """INSERT INTO ocr_results(
                    derivation_id,cache_key,document_id,version_id,occurrence_id,asset_id,
                    generation_id,provider_metadata,preprocessing_digest,completeness,
                    pages_submitted,pages_succeeded,content_hash,warnings,schema_version,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(result.derivation_id),
                    result.cache_key,
                    str(result.document_id),
                    str(result.version_id),
                    str(result.occurrence_id),
                    str(result.asset_id),
                    str(result.generation_id),
                    _provider_payload(result.provider),
                    result.preprocessing_digest,
                    result.completeness.value,
                    result.pages_submitted,
                    result.pages_succeeded,
                    result.content_hash,
                    json.dumps(result.warnings, ensure_ascii=False),
                    result.schema_version,
                    result.created_at.isoformat(),
                ),
            )
            for region in result.regions:
                language = region.language
                await db.execute(
                    """INSERT INTO ocr_regions(
                        region_id,derivation_id,page_number,order_index,text,bounding_box,
                        confidence_value,confidence_band,language_code,script,
                        language_confidence_value,language_confidence_band,language_mixed,evidence_kind
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        str(region.region_id),
                        str(result.derivation_id),
                        region.page_number,
                        region.order_index,
                        region.text,
                        None if region.bounding_box is None else json.dumps(region.bounding_box),
                        region.confidence.value,
                        region.confidence.band.value,
                        None if language is None else language.language_code,
                        None if language is None else language.script,
                        None if language is None else language.confidence.value,
                        None if language is None else language.confidence.band.value,
                        None if language is None else int(language.mixed),
                        region.evidence_kind,
                    ),
                )
            for index, language in enumerate(result.languages):
                await db.execute(
                    """INSERT INTO ocr_language_observations(
                        derivation_id,observation_index,language_code,script,
                        confidence_value,confidence_band,mixed
                    ) VALUES(?,?,?,?,?,?,?)""",
                    (
                        str(result.derivation_id),
                        index,
                        language.language_code,
                        language.script,
                        language.confidence.value,
                        language.confidence.band.value,
                        int(language.mixed),
                    ),
                )
            for index, failure in enumerate(result.failures):
                await db.execute(
                    """INSERT INTO ocr_failures(
                        derivation_id,failure_index,page_number,classification,reason_code,retryable
                    ) VALUES(?,?,?,?,?,?)""",
                    (
                        str(result.derivation_id),
                        index,
                        failure.page_number,
                        failure.classification.value,
                        failure.reason_code,
                        int(failure.retryable),
                    ),
                )
            status = (
                AssetDerivationStatus.SUCCEEDED
                if result.completeness in {OCRCompleteness.COMPLETE, OCRCompleteness.PARTIAL}
                else AssetDerivationStatus.FAILED
            )
            summary = json.dumps(
                {
                    "schema_version": result.schema_version,
                    "evidence_kind": "derived_ocr",
                    "content_hash": result.content_hash,
                    "completeness": result.completeness.value,
                    "pages_submitted": result.pages_submitted,
                    "pages_succeeded": result.pages_succeeded,
                    "region_count": len(result.regions),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            cursor = await db.execute(
                """UPDATE asset_derivations
                   SET status=?,output_payload=?,confidence=?,language=?,updated_at=?
                   WHERE derivation_id=? AND status IN (?,?)""",
                (
                    status.value,
                    summary,
                    _mean_confidence(result.regions),
                    result.languages[0].language_code if result.languages else None,
                    result.created_at.isoformat(),
                    str(result.derivation_id),
                    AssetDerivationStatus.PENDING.value,
                    AssetDerivationStatus.RUNNING.value,
                ),
            )
            if cursor.rowcount != 1:
                raise ConflictError("OCR derivation lifecycle changed before publication")
            return True

    async def get_authorized_ocr_result(
        self, *, notebook_id: UUID, derivation_id: UUID
    ) -> OCRResult | None:
        row = await (
            await self._require_open().execute(
                """SELECT r.derivation_id,r.cache_key,r.document_id,r.version_id,
                          r.occurrence_id,r.asset_id,r.generation_id,r.provider_metadata,
                          r.preprocessing_digest,r.completeness,r.pages_submitted,
                          r.pages_succeeded,r.content_hash,r.warnings,r.schema_version,r.created_at
                   FROM ocr_results r JOIN sources s ON s.document_id=r.document_id
                   WHERE r.derivation_id=? AND s.notebook_id=?""",
                (str(derivation_id), str(notebook_id)),
            )
        ).fetchone()
        return None if row is None else await self._load_result(row)

    async def get_authorized_ocr_result_by_cache_key(
        self, *, notebook_id: UUID, cache_key: str
    ) -> OCRResult | None:
        row = await (
            await self._require_open().execute(
                """SELECT r.derivation_id,r.cache_key,r.document_id,r.version_id,
                          r.occurrence_id,r.asset_id,r.generation_id,r.provider_metadata,
                          r.preprocessing_digest,r.completeness,r.pages_submitted,
                          r.pages_succeeded,r.content_hash,r.warnings,r.schema_version,r.created_at
                   FROM ocr_results r JOIN sources s ON s.document_id=r.document_id
                   WHERE r.cache_key=? AND s.notebook_id=?""",
                (cache_key, str(notebook_id)),
            )
        ).fetchone()
        return None if row is None else await self._load_result(row)

    async def project_ocr_result(self, *, generation_id: UUID, result: OCRResult) -> int:
        db = self._require_open()
        async with self._ocr_transaction(db):
            if result.completeness not in {
                OCRCompleteness.COMPLETE,
                OCRCompleteness.PARTIAL,
            }:
                raise ConflictError("non-publishable OCR results cannot enter an index")
            stored = await (
                await db.execute(
                    "SELECT content_hash FROM ocr_results WHERE derivation_id=?",
                    (str(result.derivation_id),),
                )
            ).fetchone()
            if stored is None or stored[0] != result.content_hash:
                raise IntegrityError("OCR projection requires the immutable stored result")
            generation = await (
                await db.execute(
                    "SELECT capability,profile,state,configuration_digest FROM index_generations WHERE generation_id=?",
                    (str(generation_id),),
                )
            ).fetchone()
            if generation is None or generation[0] != "ocr_text" or generation[2] != "building":
                raise ConflictError("OCR projection requires a BUILDING ocr_text generation")
            if (
                generation[1] != result.provider.profile_id
                or generation[3] != result.preprocessing_digest
            ):
                raise IntegrityError("OCR projection profile does not match its generation")
            source = await (
                await db.execute(
                    """SELECT 1 FROM index_generation_sources
                       WHERE generation_id=? AND source_kind='generation' AND source_id=?""",
                    (str(generation_id), str(result.generation_id)),
                )
            ).fetchone()
            if source is None:
                raise IntegrityError("OCR result is outside the projection source contract")
            count = 0
            for region in result.regions:
                cursor = await db.execute(
                    """INSERT OR IGNORE INTO ocr_projection_rows(
                        generation_id,region_id,derivation_id,occurrence_id,document_id,version_id,content_hash
                    ) VALUES(?,?,?,?,?,?,?)""",
                    (
                        str(generation_id),
                        str(region.region_id),
                        str(result.derivation_id),
                        str(result.occurrence_id),
                        str(result.document_id),
                        str(result.version_id),
                        result.content_hash,
                    ),
                )
                if cursor.rowcount == 1:
                    await db.execute(
                        "INSERT INTO ocr_fts(text,generation_id,region_id,derivation_id,occurrence_id,document_id,version_id) VALUES(?,?,?,?,?,?,?)",
                        (
                            region.text,
                            str(generation_id),
                            str(region.region_id),
                            str(result.derivation_id),
                            str(result.occurrence_id),
                            str(result.document_id),
                            str(result.version_id),
                        ),
                    )
                    count += 1
            return count

    async def list_ocr_projection_regions(
        self, *, generation_id: UUID, derivation_id: UUID
    ) -> tuple[UUID, ...]:
        rows = await (
            await self._require_open().execute(
                """SELECT region_id FROM ocr_projection_rows
                   WHERE generation_id=? AND derivation_id=? ORDER BY region_id""",
                (str(generation_id), str(derivation_id)),
            )
        ).fetchall()
        return tuple(UUID(row[0]) for row in rows)

    async def _load_result(self, row: object) -> OCRResult:
        values = cast(tuple[object, ...], row)
        derivation_id = UUID(cast(str, values[0]))
        db = self._require_open()
        region_rows = await (
            await db.execute(
                """SELECT region_id,page_number,order_index,text,bounding_box,
                          confidence_value,confidence_band,language_code,script,
                          language_confidence_value,language_confidence_band,language_mixed,evidence_kind
                   FROM ocr_regions WHERE derivation_id=? ORDER BY page_number,order_index""",
                (str(derivation_id),),
            )
        ).fetchall()
        regions = tuple(_region(value) for value in region_rows)
        language_rows = await (
            await db.execute(
                """SELECT language_code,script,confidence_value,confidence_band,mixed
                   FROM ocr_language_observations WHERE derivation_id=? ORDER BY observation_index""",
                (str(derivation_id),),
            )
        ).fetchall()
        failure_rows = await (
            await db.execute(
                """SELECT page_number,classification,reason_code,retryable
                   FROM ocr_failures WHERE derivation_id=? ORDER BY failure_index""",
                (str(derivation_id),),
            )
        ).fetchall()
        return OCRResult(
            derivation_id=derivation_id,
            cache_key=cast(str, values[1]),
            document_id=UUID(cast(str, values[2])),
            version_id=UUID(cast(str, values[3])),
            occurrence_id=UUID(cast(str, values[4])),
            asset_id=UUID(cast(str, values[5])),
            generation_id=UUID(cast(str, values[6])),
            provider=_provider(cast(str, values[7])),
            preprocessing_digest=cast(str, values[8]),
            completeness=OCRCompleteness(cast(str, values[9])),
            pages_submitted=int(cast(int, values[10])),
            pages_succeeded=int(cast(int, values[11])),
            content_hash=cast(str, values[12]),
            warnings=tuple(json.loads(cast(str, values[13]))),
            schema_version=int(cast(int, values[14])),
            created_at=datetime.fromisoformat(cast(str, values[15])),
            regions=regions,
            languages=tuple(
                OCRLanguageObservation(
                    language_code=value[0],
                    script=value[1],
                    confidence=_confidence(value[2], value[3]),
                    mixed=bool(value[4]),
                )
                for value in language_rows
            ),
            failures=tuple(
                OCRFailure(
                    page_number=value[0],
                    classification=OCRFailureClass(value[1]),
                    reason_code=value[2],
                    retryable=bool(value[3]),
                )
                for value in failure_rows
            ),
        )


def _region(row: object) -> OCRRegion:
    value = cast(tuple[object, ...], row)
    language = None
    if value[7] is not None or value[8] is not None:
        language = OCRLanguageObservation(
            language_code=cast(str | None, value[7]),
            script=cast(str | None, value[8]),
            confidence=_confidence(cast(float | None, value[9]), cast(str | None, value[10])),
            mixed=bool(value[11]),
        )
    box = None if value[4] is None else tuple(json.loads(cast(str, value[4])))
    return OCRRegion(
        region_id=UUID(cast(str, value[0])),
        page_number=int(cast(int, value[1])),
        order_index=int(cast(int, value[2])),
        text=cast(str, value[3]),
        bounding_box=cast(tuple[float, float, float, float] | None, box),
        confidence=_confidence(cast(float | None, value[5]), cast(str, value[6])),
        language=language,
        evidence_kind=cast(str, value[12]),
    )


def _mean_confidence(regions: tuple[OCRRegion, ...]) -> float | None:
    values = [region.confidence.value for region in regions if region.confidence.value is not None]
    return None if not values else sum(values) / len(values)
