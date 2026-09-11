"""Authorized readers over active OCR, Vision, visual, and asset projections."""

from __future__ import annotations

import hashlib
import json
import math
import re
from uuid import UUID

import aiosqlite

from mnemo.interfaces.advanced_retrieval import (
    MultilingualEvidencePage,
    MultilingualEvidenceRecord,
    MultimodalEvidencePage,
    MultimodalEvidenceRecord,
    VisualQueryVector,
    VisualVectorMetric,
)
from mnemo.interfaces.errors import ContractValidationError, IntegrityError
from mnemo.models.advanced_retrieval import (
    EvidenceRepresentation,
    PositionalScopeV2,
    RetrievalScopeV2,
)
from mnemo.storage.vision import _embedding_from_payload

_TERM = re.compile(r"[^\W_]+", re.UNICODE)
_GENERATED = {
    EvidenceRepresentation.OCR_TEXT: "ocr_text",
    EvidenceRepresentation.VISION_ANALYSIS: "vision_text",
    EvidenceRepresentation.VISUAL_VECTOR: "visual_vector",
}


class SQLiteMultimodalSearchMixin:
    """Read-only Phase 8.5 semantic occurrence discovery over schema-v14 data."""

    def _require_open(self) -> aiosqlite.Connection:
        raise NotImplementedError

    async def active_multimodal_generation_identity(
        self, representation: EvidenceRepresentation, *, profile_id: str | None = None
    ) -> str | None:
        if representation is EvidenceRepresentation.ASSET_METADATA:
            return "asset-catalog-v1"
        capability = _GENERATED.get(representation)
        if capability is None:
            return None
        where_profile = " AND g.profile=?" if profile_id is not None else ""
        params: tuple[object, ...] = (
            (capability, profile_id) if profile_id is not None else (capability,)
        )
        rows = await (
            await self._require_open().execute(
                """SELECT g.generation_id,g.profile,c.checksum FROM active_index_generations a
                   JOIN index_generations g ON g.generation_id=a.generation_id
                   JOIN index_generation_coverage c ON c.generation_id=g.generation_id
                   WHERE g.capability=? AND g.state='ready'
                     AND c.completeness='complete' AND c.failed_count=0"""
                + where_profile
                + " ORDER BY g.profile,g.generation_id",
                params,
            )
        ).fetchall()
        if not rows:
            return None
        return _digest(tuple(tuple(str(item) for item in row) for row in rows))

    async def active_multilingual_generation_identity(self) -> str | None:
        rows = await (
            await self._require_open().execute(
                """SELECT g.generation_id,g.profile,c.checksum
                   FROM active_index_generations a
                   JOIN index_generations g ON g.generation_id=a.generation_id
                   JOIN index_generation_coverage c ON c.generation_id=g.generation_id
                   WHERE g.capability='language_text' AND g.state='ready'
                     AND c.completeness='complete' AND c.failed_count=0
                   ORDER BY g.profile,g.generation_id"""
            )
        ).fetchall()
        return (
            None if not rows else _digest(tuple(tuple(str(item) for item in row) for row in rows))
        )

    async def retrieve_multilingual_evidence(
        self,
        *,
        scope: RetrievalScopeV2,
        position: PositionalScopeV2,
        query: str,
        offset: int,
        limit: int,
    ) -> MultilingualEvidencePage:
        if offset < 0 or limit < 1 or limit > 1000:
            raise ValueError("multilingual retrieval bounds are invalid")
        # The V1 language projection does not persist positional or occurrence
        # lineage in indexed columns.  Enumerating and filtering afterwards
        # would violate authorization-before-enumeration, so requests for such
        # scope fail closed until the additive V2 projection is active.
        if position != PositionalScopeV2():
            raise ContractValidationError(
                "active multilingual projection cannot enforce positional scope"
            )
        identity = await self.active_multilingual_generation_identity()
        if identity is None:
            raise ContractValidationError("active multilingual text generation is unavailable")
        match = _fts_query(query)
        scope_sql, scope_params = _scope_sql(scope, "f", "s")
        params: list[object] = list(scope_params)
        match_sql = ""
        if match is not None:
            match_sql = " AND f MATCH ?"
            params.append(match)
        sql = f"""SELECT f.derivation_id,f.notebook_id,f.document_id,f.version_id,
                          f.source_evidence_id,f.source_language,f.target_language,f.text,
                          bm25(f),MIN(s.source_id)
                   FROM language_text_fts f
                   JOIN sources s ON s.document_id=f.document_id
                   WHERE 1=1 {scope_sql} {match_sql}
                   GROUP BY f.derivation_id,f.notebook_id,f.document_id,f.version_id,
                            f.source_evidence_id,f.source_language,f.target_language,f.text
                   ORDER BY bm25(f),f.document_id,f.version_id,f.derivation_id
                   LIMIT 10001"""
        rows = tuple(await (await self._require_open().execute(sql, params)).fetchall())
        page = rows[offset : offset + limit + 1]
        records = tuple(
            MultilingualEvidenceRecord(
                notebook_id=scope.notebook_id,
                source_id=UUID(str(row[9])),
                document_id=UUID(str(row[2])),
                version_id=UUID(str(row[3])),
                derivation_id=UUID(str(row[0])),
                source_evidence_id=str(row[4]),
                source_language=str(row[5]),
                target_language=str(row[6]),
                content=str(row[7]),
                source_rank=offset + index,
                source_score=-float(str(row[8])),
            )
            for index, row in enumerate(page[:limit], 1)
        )
        if any(not _record_in_scope(item, scope) for item in records):
            raise IntegrityError("multilingual projection returned out-of-scope evidence")
        return MultilingualEvidencePage(
            snapshot_identity=identity,
            records=records,
            examined=min(len(rows), 10000),
            next_offset=offset + limit if len(page) > limit else None,
            exhausted=len(page) <= limit,
        )

    async def retrieve_multimodal_evidence(
        self,
        *,
        representation: EvidenceRepresentation,
        scope: RetrievalScopeV2,
        position: PositionalScopeV2,
        query: str,
        ranked: bool,
        offset: int,
        limit: int,
        query_vector: VisualQueryVector | None = None,
    ) -> MultimodalEvidencePage:
        if offset < 0 or limit < 1 or limit > 1000:
            raise ValueError("multimodal retrieval bounds are invalid")
        if representation is EvidenceRepresentation.ASSET_METADATA:
            return await self._asset_metadata(scope, position, query, ranked, offset, limit)
        if representation in {
            EvidenceRepresentation.OCR_TEXT,
            EvidenceRepresentation.VISION_ANALYSIS,
        }:
            return await self._derived_text(
                representation, scope, position, query, ranked, offset, limit
            )
        if representation is EvidenceRepresentation.VISUAL_VECTOR:
            if query_vector is None:
                raise ContractValidationError("visual-vector retrieval requires a query vector")
            return await self._visual_vectors(scope, position, query_vector, offset, limit)
        raise ContractValidationError("representation is not a multimodal search source")

    async def _derived_text(
        self,
        representation: EvidenceRepresentation,
        scope: RetrievalScopeV2,
        position: PositionalScopeV2,
        query: str,
        ranked: bool,
        offset: int,
        limit: int,
    ) -> MultimodalEvidencePage:
        capability = _GENERATED[representation]
        generation_identity = await self.active_multimodal_generation_identity(representation)
        if generation_identity is None:
            raise ContractValidationError(f"active {capability} generation is unavailable")
        table = (
            "ocr_fts" if representation is EvidenceRepresentation.OCR_TEXT else "vision_text_fts"
        )
        row_table = (
            "ocr_projection_rows"
            if representation is EvidenceRepresentation.OCR_TEXT
            else "vision_text_projection_rows"
        )
        id_column = (
            "region_id" if representation is EvidenceRepresentation.OCR_TEXT else "derivation_id"
        )
        scope_sql, scope_params = _scope_sql(scope, "p", "s")
        match = _fts_query(query)
        match_sql = f" AND {table} MATCH ?" if match is not None else ""
        params: list[object] = [capability, *scope_params]
        if match is not None:
            params.append(match)
        score = "f.rank" if match is not None and ranked else "0.0"
        content = (
            "GROUP_CONCAT(f.text, '\n')"
            if representation is EvidenceRepresentation.OCR_TEXT
            else "MIN(f.text)"
        )
        region_ids = (
            "GROUP_CONCAT(f.region_id)"
            if representation is EvidenceRepresentation.OCR_TEXT
            else "NULL"
        )
        sql = f"""SELECT p.derivation_id,p.occurrence_id,o.asset_id,p.document_id,p.version_id,
                          MIN(s.source_id),MIN(dv.metadata),MIN(o.locator),{content},
                          {region_ids},MIN({score}),MIN(g.profile),MIN(g.generation_id)
                   FROM {table} f JOIN {row_table} p
                     ON p.generation_id=f.generation_id AND p.{id_column}=f.{id_column}
                   JOIN active_index_generations a ON a.generation_id=p.generation_id
                   JOIN index_generations g ON g.generation_id=p.generation_id
                   JOIN index_generation_coverage cov ON cov.generation_id=g.generation_id
                   JOIN asset_occurrences o ON o.occurrence_id=p.occurrence_id
                   JOIN sources s ON s.document_id=p.document_id
                   JOIN document_versions dv ON dv.version_id=p.version_id
                   WHERE g.capability=? AND g.state='ready' AND cov.completeness='complete'
                     AND cov.failed_count=0 {scope_sql} {match_sql}
                   GROUP BY p.derivation_id,p.occurrence_id,o.asset_id,p.document_id,p.version_id
                   ORDER BY MIN({score}),p.document_id,p.version_id,p.occurrence_id,p.derivation_id
                   LIMIT 10001"""
        rows = tuple(await (await self._require_open().execute(sql, params)).fetchall())
        filtered = tuple(
            row for row in rows if _position_matches(json.loads(str(row[7])), position)
        )
        page = filtered[offset : offset + limit + 1]
        records = tuple(
            _text_record(representation, scope.notebook_id, tuple(row), offset + index)
            for index, row in enumerate(page[:limit], 1)
        )
        has_more = len(page) > limit or len(filtered) >= 10001
        return MultimodalEvidencePage(
            snapshot_identity=generation_identity,
            records=records,
            examined=min(len(filtered), 10000),
            next_offset=offset + limit if has_more else None,
            exhausted=not has_more,
        )

    async def _asset_metadata(
        self,
        scope: RetrievalScopeV2,
        position: PositionalScopeV2,
        query: str,
        ranked: bool,
        offset: int,
        limit: int,
    ) -> MultimodalEvidencePage:
        scope_sql, params = _scope_sql(scope, "o", "s")
        rows = tuple(
            await (
                await self._require_open().execute(
                    f"""SELECT o.occurrence_id,o.asset_id,o.document_id,o.version_id,
                               MIN(s.source_id),MIN(dv.metadata),o.locator,o.authored_alt_text,
                               a.mime_type,a.metadata,a.content_hash
                        FROM asset_occurrences o JOIN asset_catalog a ON a.asset_id=o.asset_id
                        JOIN sources s ON s.document_id=o.document_id
                        JOIN document_versions dv ON dv.version_id=o.version_id
                        WHERE 1=1 {scope_sql}
                        GROUP BY o.occurrence_id
                        ORDER BY o.document_id,o.version_id,
                                 json_extract(o.locator,'$.ordinal'),o.occurrence_id""",
                    params,
                )
            ).fetchall()
        )
        terms = tuple(term.casefold() for term in _TERM.findall(query))
        matched: list[tuple[float, tuple[object, ...]]] = []
        for row in rows:
            locator = json.loads(str(row[6]))
            if not _position_matches(locator, position):
                continue
            metadata = json.loads(str(row[9]))
            document_metadata = json.loads(str(row[5]))
            haystack = " ".join(
                str(item)
                for item in (
                    row[7] or "",
                    row[8],
                    metadata,
                    document_metadata.get("title", ""),
                    locator,
                )
            ).casefold()
            hits = sum(term in haystack for term in terms)
            if terms and hits == 0:
                continue
            score = hits / len(terms) if terms else 1.0
            matched.append((score, tuple(row)))
        if ranked:
            matched.sort(key=lambda item: (-item[0], str(item[1][0])))
        page = matched[offset : offset + limit + 1]
        records = tuple(
            _asset_record(scope.notebook_id, row, offset + index, score)
            for index, (score, row) in enumerate(page[:limit], 1)
        )
        snapshot = _digest(
            tuple((str(row[0]), str(row[10]), str(row[7]), str(row[6])) for row in rows)
        )
        has_more = len(page) > limit
        return MultimodalEvidencePage(
            snapshot_identity=snapshot,
            records=records,
            examined=len(rows),
            next_offset=offset + limit if has_more else None,
            exhausted=not has_more,
        )

    async def _visual_vectors(
        self,
        scope: RetrievalScopeV2,
        position: PositionalScopeV2,
        query_vector: VisualQueryVector,
        offset: int,
        limit: int,
    ) -> MultimodalEvidencePage:
        identity = await self.active_multimodal_generation_identity(
            EvidenceRepresentation.VISUAL_VECTOR, profile_id=query_vector.profile_id
        )
        if identity is None:
            raise ContractValidationError(
                "compatible active visual-vector generation is unavailable"
            )
        scope_sql, params = _scope_sql(scope, "p", "s")
        params = [query_vector.profile_id, *params]
        rows = tuple(
            await (
                await self._require_open().execute(
                    f"""SELECT e.derivation_id,e.occurrence_id,e.asset_id,e.document_id,
                               e.version_id,
                               MIN(s.source_id),MIN(dv.metadata),MIN(o.locator),e.payload,g.generation_id
                        FROM visual_vector_projection_rows p
                        JOIN visual_embeddings e ON e.derivation_id=p.derivation_id
                        JOIN active_index_generations a ON a.generation_id=p.generation_id
                        JOIN index_generations g ON g.generation_id=p.generation_id
                        JOIN index_generation_coverage cov ON cov.generation_id=g.generation_id
                        JOIN asset_occurrences o ON o.occurrence_id=p.occurrence_id
                        JOIN sources s ON s.document_id=p.document_id
                        JOIN document_versions dv ON dv.version_id=p.version_id
                        WHERE g.profile=? AND g.capability='visual_vector' AND g.state='ready'
                          AND cov.completeness='complete' AND cov.failed_count=0 {scope_sql}
                        GROUP BY e.derivation_id ORDER BY e.derivation_id LIMIT 10001""",
                    params,
                )
            ).fetchall()
        )
        scored: list[tuple[float, tuple[object, ...]]] = []
        for row in rows[:10000]:
            locator = json.loads(str(row[7]))
            if not _position_matches(locator, position):
                continue
            embedding = _embedding_from_payload(str(row[8]))
            if (
                embedding.dimensions != query_vector.dimensions
                or embedding.shared_space_id != query_vector.shared_space_id
                or embedding.metric.value != query_vector.metric.value
            ):
                raise IntegrityError("visual query vector is incompatible with active generation")
            score = _similarity(query_vector, embedding.vector)
            scored.append((score, tuple(row)))
        scored.sort(key=lambda item: (-item[0], str(item[1][0])))
        page = scored[offset : offset + limit + 1]
        records = tuple(
            _visual_record(scope.notebook_id, row, offset + index, score)
            for index, (score, row) in enumerate(page[:limit], 1)
        )
        has_more = len(page) > limit or len(rows) > 10000
        return MultimodalEvidencePage(
            snapshot_identity=identity,
            records=records,
            examined=min(len(rows), 10000),
            next_offset=offset + limit if has_more else None,
            exhausted=not has_more,
        )


def _scope_sql(
    scope: RetrievalScopeV2, record_alias: str, source_alias: str
) -> tuple[str, list[object]]:
    sql = f" AND {source_alias}.notebook_id=?"
    params: list[object] = [str(scope.notebook_id)]
    for values, expression in (
        (scope.source_ids, f"{source_alias}.source_id"),
        (scope.document_ids, f"{record_alias}.document_id"),
        (scope.version_ids, f"{record_alias}.version_id"),
    ):
        if values:
            sql += f" AND {expression} IN ({','.join('?' for _ in values)})"
            params.extend(str(value) for value in values)
    return sql, params


def _record_in_scope(record: MultilingualEvidenceRecord, scope: RetrievalScopeV2) -> bool:
    return (
        record.notebook_id == scope.notebook_id
        and (not scope.source_ids or record.source_id in scope.source_ids)
        and (not scope.document_ids or record.document_id in scope.document_ids)
        and (not scope.version_ids or record.version_id in scope.version_ids)
    )


def _fts_query(query: str) -> str | None:
    terms = tuple(_TERM.findall(query))
    if not terms:
        return None
    return " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)


def _position_matches(locator: dict[str, object], position: PositionalScopeV2) -> bool:
    page = locator.get("page_number") or locator.get("slide_number")
    if position.page_start is not None and (
        not isinstance(page, int) or page < position.page_start
    ):
        return False
    if position.page_end is not None and (not isinstance(page, int) or page > position.page_end):
        return False
    section = locator.get("section_path")
    return not (
        position.heading_prefix
        and (
            not isinstance(section, list)
            or tuple(str(item) for item in section[: len(position.heading_prefix)])
            != position.heading_prefix
        )
    )


def _title(raw: object) -> str | None:
    metadata = json.loads(str(raw))
    value = metadata.get("title") if isinstance(metadata, dict) else None
    return value if isinstance(value, str) and value.strip() else None


def _text_record(
    representation: EvidenceRepresentation,
    notebook_id: UUID,
    row: tuple[object, ...],
    rank: int,
) -> MultimodalEvidenceRecord:
    locator = json.loads(str(row[7]))
    locator.update(
        {
            "asset_id": str(row[2]),
            "evidence_kind": "derived_ocr"
            if representation is EvidenceRepresentation.OCR_TEXT
            else "derived_vision",
            "region_ids": [] if row[9] is None else str(row[9]).split(","),
            "generation_profile": str(row[11]),
        }
    )
    return MultimodalEvidenceRecord(
        notebook_id=notebook_id,
        source_id=UUID(str(row[5])),
        document_id=UUID(str(row[3])),
        version_id=UUID(str(row[4])),
        occurrence_id=UUID(str(row[1])),
        asset_id=UUID(str(row[2])),
        derivation_id=UUID(str(row[0])),
        generation_id=UUID(str(row[12])),
        document_title=_title(row[6]),
        content=str(row[8]),
        locator=locator,
        language=None,
        source_rank=rank,
        source_score=None if row[10] is None else -float(str(row[10])),
    )


def _asset_record(
    notebook_id: UUID, row: tuple[object, ...], rank: int, score: float
) -> MultimodalEvidenceRecord:
    locator = json.loads(str(row[6]))
    locator.update(
        {
            "mime_type": str(row[8]),
            "asset_id": str(row[1]),
            "evidence_kind": "original_asset_metadata",
        }
    )
    return MultimodalEvidenceRecord(
        notebook_id=notebook_id,
        source_id=UUID(str(row[4])),
        document_id=UUID(str(row[2])),
        version_id=UUID(str(row[3])),
        occurrence_id=UUID(str(row[0])),
        asset_id=UUID(str(row[1])),
        derivation_id=None,
        generation_id=None,
        document_title=_title(row[5]),
        content=None if row[7] is None else str(row[7]),
        locator=locator,
        language=None,
        source_rank=rank,
        source_score=score,
    )


def _visual_record(
    notebook_id: UUID, row: tuple[object, ...], rank: int, score: float
) -> MultimodalEvidenceRecord:
    locator = json.loads(str(row[7]))
    locator.update({"asset_id": str(row[2]), "evidence_kind": "visual_vector_match"})
    return MultimodalEvidenceRecord(
        notebook_id=notebook_id,
        source_id=UUID(str(row[5])),
        document_id=UUID(str(row[3])),
        version_id=UUID(str(row[4])),
        occurrence_id=UUID(str(row[1])),
        asset_id=UUID(str(row[2])),
        derivation_id=UUID(str(row[0])),
        generation_id=UUID(str(row[9])),
        document_title=_title(row[6]),
        content=None,
        locator=locator,
        language=None,
        source_rank=rank,
        source_score=score,
    )


def _similarity(query: VisualQueryVector, vector: tuple[float, ...]) -> float:
    dot = sum(left * right for left, right in zip(query.values, vector, strict=True))
    if query.metric is VisualVectorMetric.DOT:
        return dot
    query_norm = math.sqrt(sum(value * value for value in query.values))
    vector_norm = math.sqrt(sum(value * value for value in vector))
    if query_norm == 0 or vector_norm == 0:
        raise IntegrityError("visual vector has zero magnitude")
    return dot / (query_norm * vector_norm)


def _digest(rows: tuple[tuple[str, ...], ...]) -> str:
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
