"""Deterministic, bounded Phase 8.5.7 structured retrieval execution."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import cmp_to_key
from typing import cast
from uuid import UUID

from mnemo.interfaces.errors import ContractValidationError, IntegrityError
from mnemo.interfaces.structured_retrieval import (
    StructuredDatasetCatalogV1,
    StructuredEvidenceExtractorV1,
    StructuredIRReaderV1,
    StructuredProjectionStoreV1,
)
from mnemo.models import FrozenMetadata
from mnemo.models.advanced_retrieval import (
    AdvancedRetrievalCandidate,
    RetrievalCompleteness,
    RetrievalResultSetV1,
)
from mnemo.models.blocks import TableBlock
from mnemo.models.structured_retrieval import (
    ExtractedStructuredRecord,
    StructuredAggregateValue,
    StructuredAggregation,
    StructuredAggregationOperation,
    StructuredColumnObservation,
    StructuredEvidence,
    StructuredField,
    StructuredFieldType,
    StructuredFilter,
    StructuredFilterOperator,
    StructuredGroupResult,
    StructuredNullOrder,
    StructuredQueryV1,
    StructuredRecord,
    StructuredResult,
    StructuredResultMetadata,
    StructuredScalar,
    StructuredSchemaConfidence,
    StructuredSchemaObservation,
    StructuredSort,
    StructuredSortDirection,
    StructuredValue,
    StructuredValueStatus,
    structured_record_id,
    structured_schema_generation,
)

_DECIMAL = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")
_DURATION = re.compile(r"^PT(?P<seconds>\d+(?:\.\d+)?)S$")


class DelimitedTableEvidenceExtractor:
    """Extract rows from canonical tab-delimited table chunks without guessing prose."""

    async def extract(
        self,
        candidate: AdvancedRetrievalCandidate,
        fields: tuple[StructuredField, ...],
        *,
        limit: int,
    ) -> tuple[ExtractedStructuredRecord, ...]:
        content = candidate.content
        if content is None or "\t" not in content:
            return ()
        lines = tuple(line for line in content.splitlines() if line.strip())
        if len(lines) < 2:
            return ()
        headers = tuple(cell.strip() for cell in lines[0].split("\t"))
        if not headers or len(headers) != len(set(item.casefold() for item in headers)):
            return ()
        indexes = {name.casefold(): index for index, name in enumerate(headers)}
        requested: dict[str, int] = {}
        for structured_field in fields:
            source = (structured_field.source_name or structured_field.name).casefold()
            if source in indexes:
                requested[structured_field.name] = indexes[source]
        if not requested:
            return ()
        records: list[ExtractedStructuredRecord] = []
        for row_ordinal, line in enumerate(lines[1 : limit + 1], start=1):
            cells = tuple(cell.strip() for cell in line.split("\t"))
            values = {
                name: cells[index] if index < len(cells) else ""
                for name, index in requested.items()
            }
            locators = {
                name: {"row": row_ordinal, "column": index, "header": headers[index]}
                for name, index in requested.items()
            }
            records.append(
                ExtractedStructuredRecord(
                    candidate_id=candidate.candidate_id,
                    row_ordinal=row_ordinal,
                    values=FrozenMetadata(values),
                    cell_locators=FrozenMetadata(locators),
                    extraction_method="canonical_tabular_chunk/v1",
                )
            )
        return tuple(records)


class CanonicalTableEvidenceExtractor:
    """Reconstruct records only from exact-version canonical ``TableBlock`` IR."""

    def __init__(self, reader: StructuredIRReaderV1) -> None:
        self._reader = reader

    async def extract(
        self,
        candidate: AdvancedRetrievalCandidate,
        fields: tuple[StructuredField, ...],
        *,
        limit: int,
    ) -> tuple[ExtractedStructuredRecord, ...]:
        chunk = candidate.chunk
        if chunk is None or limit < 1:
            return ()
        parsed = await self._reader.get_parsed_document(candidate.version_id)
        if parsed is None:
            return ()
        matching = tuple(
            block
            for block in parsed.blocks[
                chunk.source_span.start_ordinal : chunk.source_span.end_ordinal + 1
            ]
            if isinstance(block, TableBlock)
        )
        if len(matching) != 1:
            return ()
        table = matching[0]
        if table.header_row_count < 1:
            return ()
        headers = tuple(
            " / ".join(
                row[column].strip()
                for row in table.rows[: table.header_row_count]
                if row[column].strip()
            )
            for column in range(len(table.rows[0]))
        )
        if any(not header for header in headers) or len(headers) != len(
            set(header.casefold() for header in headers)
        ):
            return ()
        indexes = {header.casefold(): index for index, header in enumerate(headers)}
        requested = {
            structured_field.name: indexes[source]
            for structured_field in fields
            if (source := (structured_field.source_name or structured_field.name).casefold())
            in indexes
        }
        if not requested:
            return ()
        records: list[ExtractedStructuredRecord] = []
        for row_index, row in enumerate(
            table.rows[table.header_row_count : table.header_row_count + limit],
            start=table.header_row_count,
        ):
            records.append(
                ExtractedStructuredRecord(
                    candidate_id=candidate.candidate_id,
                    row_ordinal=row_index,
                    values=FrozenMetadata({name: row[index] for name, index in requested.items()}),
                    cell_locators=FrozenMetadata(
                        {
                            name: {
                                "block_ordinal": table.ordinal,
                                "page": table.page_number,
                                "row": row_index,
                                "column": index,
                                "header": headers[index],
                            }
                            for name, index in requested.items()
                        }
                    ),
                    extraction_method="canonical_table_ir/v1",
                )
            )
        return tuple(records)


class ProjectedTableEvidenceExtractor:
    """Read immutable version-scoped table projections through an additive store."""

    def __init__(self, store: StructuredProjectionStoreV1) -> None:
        self._store = store

    async def extract(
        self,
        candidate: AdvancedRetrievalCandidate,
        fields: tuple[StructuredField, ...],
        *,
        limit: int,
    ) -> tuple[ExtractedStructuredRecord, ...]:
        return await self._store.extract_projected_structured_records(
            candidate, fields, limit=limit
        )


class StructuredDatasetEvidenceExtractor:
    """Read an explicit authorized dataset selection without semantic discovery."""

    def __init__(
        self,
        store: StructuredDatasetCatalogV1,
        dataset_by_candidate: Mapping[UUID, UUID],
    ) -> None:
        self._store = store
        self._datasets = dict(dataset_by_candidate)

    async def extract(
        self,
        candidate: AdvancedRetrievalCandidate,
        fields: tuple[StructuredField, ...],
        *,
        limit: int,
    ) -> tuple[ExtractedStructuredRecord, ...]:
        dataset_id = self._datasets.get(candidate.candidate_id)
        if dataset_id is None:
            raise IntegrityError("structured candidate has no authorized dataset binding")
        return await self._store.extract_structured_dataset_records(
            notebook_id=candidate.notebook_id,
            dataset_id=dataset_id,
            candidate_id=candidate.candidate_id,
            fields=fields,
            limit=limit,
        )


class StructuredRetrievalService:
    """Evaluate an allowlisted structured AST over an authorized V2 result set."""

    def __init__(self, extractor: StructuredEvidenceExtractorV1) -> None:
        self._extractor = extractor

    async def execute(
        self,
        query: StructuredQueryV1,
        retrieval: RetrievalResultSetV1,
    ) -> StructuredResult:
        if retrieval.query_fingerprint != query.retrieval_plan.fingerprint:
            raise ContractValidationError("structured query does not match retrieval result")
        started = time.perf_counter()
        stage: dict[str, int] = {}
        extraction_started = time.perf_counter()
        raw: list[tuple[AdvancedRetrievalCandidate, ExtractedStructuredRecord]] = []
        truncated_reasons: list[str] = []
        candidates = {candidate.candidate_id: candidate for candidate in retrieval.results}
        for candidate in retrieval.results:
            if len(raw) >= query.budgets.max_records:
                truncated_reasons.append("max_records")
                break
            self._authorize_candidate(query, candidate)
            remaining = query.budgets.max_records - len(raw)
            extracted = await self._extractor.extract(candidate, query.fields, limit=remaining)
            if len(extracted) > remaining:
                raise IntegrityError("structured extractor exceeded requested record limit")
            for item in extracted:
                if item.candidate_id != candidate.candidate_id:
                    raise IntegrityError("structured extractor changed candidate provenance")
                if len(raw) >= query.budgets.max_records:
                    truncated_reasons.append("max_records")
                    break
                raw.append((candidate, item))
            if len(extracted) == remaining:
                truncated_reasons.append("max_records")
            if truncated_reasons:
                break
        stage["extraction"] = _elapsed(extraction_started)

        normalization_started = time.perf_counter()
        if any(_json_depth(item.values) > query.budgets.max_nesting_depth for _, item in raw):
            raise ContractValidationError("structured value nesting budget exceeded")
        normalized = [self._record(candidate, item, query.fields) for candidate, item in raw]
        records = _deduplicate_records(normalized, query.budgets.max_evidence_references)
        stage["normalization"] = _elapsed(normalization_started)

        filtering_started = time.perf_counter()
        field_map = {item.name: item for item in query.fields}
        filtered = [
            record
            for record in records
            if all(_matches(record, predicate, field_map) for predicate in query.filters)
        ]
        if query.distinct_fields:
            filtered = _distinct_records(
                filtered,
                query.distinct_fields,
                query.budgets.max_evidence_references,
                query.budgets.max_distinct_values,
            )
        if query.order_by:
            filtered.sort(
                key=cmp_to_key(lambda left, right: _compare_records(left, right, query.order_by))
            )
        stage["filter_sort"] = _elapsed(filtering_started)

        aggregation_started = time.perf_counter()
        groups = self._groups(query, filtered)
        stage["aggregation"] = _elapsed(aggregation_started)

        matched_count = len(filtered)
        page = filtered[query.offset : query.offset + query.limit]
        next_offset = query.offset + len(page) if query.offset + len(page) < matched_count else None
        if next_offset is not None:
            truncated_reasons.append("page_limit")
        if len(page) > query.budgets.max_evidence_references:
            page = page[: query.budgets.max_evidence_references]
            next_offset = query.offset + len(page)
            truncated_reasons.append("max_evidence_references")
        evidence_count = sum(len(record.evidence) for record in page) + sum(
            len(group.evidence) for group in groups
        )
        output_bytes = _result_size(page, groups)
        output_limit = min(
            query.budgets.max_output_bytes,
            query.budgets.max_output_tokens * 4,
        )
        if _result_size([], groups) > output_limit:
            raise ContractValidationError("structured group output budget exceeded")
        if output_bytes > output_limit:
            page, output_bytes = _fit_output(page, groups, output_limit)
            next_offset = query.offset + len(page)
            truncated_reasons.append("max_output_size")

        incomplete_values = any(
            value.status
            in {
                StructuredValueStatus.VALUE_UNCERTAIN,
                StructuredValueStatus.VALUE_INVALID,
                StructuredValueStatus.VALUE_UNAVAILABLE,
            }
            or (
                value.status is StructuredValueStatus.VALUE_MISSING
                and field_map[value.field].required
            )
            for record in records
            for value in record.values
        )
        completeness = _structured_completeness(
            retrieval.completeness,
            bool(truncated_reasons),
            bool(page or groups),
            incomplete_values,
        )
        from mnemo.models.structured_retrieval import StructuredDiagnostics

        diagnostics = StructuredDiagnostics(
            candidates_examined=len(candidates),
            extracted_records=len(raw),
            deduplicated_records=len(records),
            filtered_records=matched_count,
            returned_records=len(page),
            group_count=len(groups),
            evidence_references=evidence_count,
            output_bytes=output_bytes,
            truncated=bool(truncated_reasons),
            truncation_reasons=tuple(dict.fromkeys(truncated_reasons)),
            stage_milliseconds=FrozenMetadata({**stage, "total": _elapsed(started)}),
        )
        return StructuredResult(
            query_fingerprint=query.fingerprint,
            retrieval_fingerprint=retrieval.query_fingerprint,
            retrieval_completeness=retrieval.completeness,
            completeness=completeness,
            records=tuple(page),
            groups=groups,
            matched_count=matched_count,
            returned_count=len(page),
            next_offset=next_offset,
            metadata=StructuredResultMetadata(
                schema_generation=structured_schema_generation(query.fields),
                retrieval_snapshot_identity=retrieval.snapshot_identity,
                candidate_universe_count=len(retrieval.results),
                extracted_row_universe_count=len(records),
                matched_count=matched_count,
                returned_count=len(page),
                operations=tuple(
                    ["extract", "normalize", "validate"]
                    + (["filter"] if query.filters else [])
                    + (["distinct"] if query.distinct_fields else [])
                    + (["sort"] if query.order_by else [])
                    + (["group"] if query.group_by else [])
                    + (["aggregate"] if query.aggregations else [])
                ),
                provenance_truncated=(
                    "max_evidence_references" in truncated_reasons
                    or any(group.evidence_truncated for group in groups)
                    or any(
                        aggregate.evidence_truncated
                        for group in groups
                        for aggregate in group.aggregates
                    )
                ),
            ),
            diagnostics=diagnostics,
        )

    @staticmethod
    def _authorize_candidate(
        query: StructuredQueryV1, candidate: AdvancedRetrievalCandidate
    ) -> None:
        scope = query.retrieval_plan.scope
        if candidate.notebook_id != scope.notebook_id:
            raise IntegrityError("structured evidence escaped notebook scope")
        checks = (
            (scope.source_ids, candidate.source_id, "source"),
            (scope.document_ids, candidate.document_id, "document"),
            (scope.version_ids, candidate.version_id, "version"),
        )
        for allowed, actual, label in checks:
            if allowed and actual not in allowed:
                raise IntegrityError(f"structured evidence escaped {label} scope")

    @staticmethod
    def _record(
        candidate: AdvancedRetrievalCandidate,
        extracted: ExtractedStructuredRecord,
        fields: tuple[StructuredField, ...],
    ) -> StructuredRecord:
        evidence = _evidence(candidate, extracted)
        values: list[StructuredValue] = []
        for structured_field in fields:
            raw: object = extracted.values.get(structured_field.name)
            if raw is None:
                raw = _provenance_raw(candidate, structured_field.source_name)
            locator = extracted.cell_locators.get(structured_field.name)
            field_evidence = evidence
            if isinstance(locator, FrozenMetadata):
                merged = dict(candidate.locator)
                merged.update(dict(locator))
                field_evidence = (replace(evidence[0], locator=FrozenMetadata(merged)),)
            values.append(_normalize(raw, structured_field, field_evidence))
        return StructuredRecord(
            record_id=structured_record_id(candidate.candidate_id, extracted.row_ordinal),
            candidate_id=candidate.candidate_id,
            row_ordinal=extracted.row_ordinal,
            values=tuple(values),
            evidence=evidence,
        )

    @staticmethod
    def _groups(
        query: StructuredQueryV1, records: list[StructuredRecord]
    ) -> tuple[StructuredGroupResult, ...]:
        if not query.group_by and not query.aggregations:
            return ()
        grouped: dict[tuple[object, ...], list[StructuredRecord]] = {}
        for record in records:
            group_key: tuple[object, ...] = tuple(
                _canonical_value(record.value_for(name)) for name in query.group_by
            )
            if group_key not in grouped and len(grouped) >= query.budgets.max_groups:
                raise ContractValidationError("structured group budget exceeded")
            grouped.setdefault(group_key, []).append(record)
        if not grouped and query.aggregations and not query.group_by:
            grouped[()] = []
        results: list[StructuredGroupResult] = []
        for group_key, members in sorted(grouped.items(), key=lambda item: repr(item[0])):
            if len(members) > query.budgets.max_aggregation_rows:
                raise ContractValidationError("aggregation row budget exceeded")
            evidence, evidence_truncated = _bounded_evidence(
                (evidence for member in members for evidence in member.evidence),
                query.budgets.max_evidence_references,
            )
            aggregates = tuple(
                _aggregate(item, members, query.budgets.max_evidence_references)
                for item in query.aggregations
            )
            key_values = (
                tuple(members[0].value_for(name) for name in query.group_by) if members else ()
            )
            group_id = _group_id(group_key)
            member_ids = tuple(
                member.record_id for member in members[: query.budgets.max_evidence_references]
            )
            evidence_truncated = evidence_truncated or len(member_ids) < len(members)
            results.append(
                StructuredGroupResult(
                    group_id=group_id,
                    keys=key_values,
                    member_record_ids=member_ids,
                    aggregates=aggregates,
                    evidence=evidence,
                    evidence_truncated=evidence_truncated,
                )
            )
        return tuple(results)


def compare_structured_values(
    left: StructuredValue,
    right: StructuredValue,
) -> int:
    """Compare compatible present typed values without implicit coercion."""
    if (
        left.status is not StructuredValueStatus.VALUE_PRESENT
        or right.status is not StructuredValueStatus.VALUE_PRESENT
    ):
        raise ContractValidationError("comparison requires present values")
    if left.field_type is not right.field_type:
        raise ContractValidationError("incompatible structured field types")
    if left.unit != right.unit:
        raise ContractValidationError("incompatible structured units")
    if left.field_type in {StructuredFieldType.LIST, StructuredFieldType.OBJECT}:
        raise ContractValidationError("complex structured values are not ordered")
    return _cmp(cast(StructuredScalar, left.value), cast(StructuredScalar, right.value))


def observe_table_schema(block: TableBlock) -> StructuredSchemaObservation:
    """Observe a table schema conservatively without changing canonical parser data."""
    if block.header_row_count < 1:
        raise ContractValidationError("structured schema discovery requires an explicit header")
    headers = tuple(
        " / ".join(
            row[index].strip() for row in block.rows[: block.header_row_count] if row[index].strip()
        )
        for index in range(len(block.rows[0]))
    )
    if not all(headers) or len(set(name.casefold() for name in headers)) != len(headers):
        raise ContractValidationError("structured schema headers are missing or ambiguous")
    rows = block.rows[block.header_row_count :]
    observations = tuple(
        _observe_column(name, index, tuple(row[index].strip() for row in rows))
        for index, name in enumerate(headers)
    )
    fields = tuple(
        StructuredField(name=item.name, field_type=item.observed_type) for item in observations
    )
    return StructuredSchemaObservation(
        generation=structured_schema_generation(fields),
        columns=observations,
        row_count=len(rows),
    )


def _observe_column(
    name: str, column_index: int, raw_values: tuple[str, ...]
) -> StructuredColumnObservation:
    values = tuple(value for value in raw_values if value)
    if not values:
        observed_type = StructuredFieldType.STRING
        confidence = StructuredSchemaConfidence.AMBIGUOUS
    else:
        observed_type = _observed_type(values)
        confidence = (
            StructuredSchemaConfidence.EXACT
            if len(values) == len(raw_values) and observed_type is not StructuredFieldType.STRING
            else StructuredSchemaConfidence.OBSERVED
        )
    return StructuredColumnObservation(
        name=name,
        column_index=column_index,
        observed_type=observed_type,
        confidence=confidence,
        non_missing_count=len(values),
    )


def _observed_type(values: tuple[str, ...]) -> StructuredFieldType:
    if all(value.casefold() in {"true", "false"} for value in values):
        return StructuredFieldType.BOOLEAN
    if all(re.fullmatch(r"[+-]?\d+", value) for value in values):
        return StructuredFieldType.INTEGER
    if all(_DECIMAL.fullmatch(value) for value in values):
        return StructuredFieldType.DECIMAL
    if all("T" in value and _is_iso_datetime(value) for value in values):
        return StructuredFieldType.DATETIME
    if all(_is_iso_date(value) for value in values):
        return StructuredFieldType.DATE
    return StructuredFieldType.STRING


def _is_iso_datetime(value: str) -> bool:
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _normalize(
    raw: object,
    structured_field: StructuredField,
    evidence: tuple[StructuredEvidence, ...],
) -> StructuredValue:
    if raw is None or raw == "":
        return _absent(
            structured_field, StructuredValueStatus.VALUE_MISSING, "source value missing"
        )
    if isinstance(raw, FrozenMetadata) and "status" in raw:
        status_raw = raw["status"]
        try:
            status = StructuredValueStatus(str(status_raw))
        except ValueError:
            return _absent(
                structured_field, StructuredValueStatus.VALUE_INVALID, "invalid extractor status"
            )
        if status is StructuredValueStatus.VALUE_PRESENT:
            raw = raw.get("value")
        else:
            return _absent(structured_field, status, str(raw.get("reason", status.value)))
    try:
        value = _coerce(raw, structured_field)
    except (ValueError, TypeError, InvalidOperation):
        return _absent(
            structured_field, StructuredValueStatus.VALUE_INVALID, "value does not match field type"
        )
    return StructuredValue(
        field=structured_field.name,
        field_type=structured_field.field_type,
        status=StructuredValueStatus.VALUE_PRESENT,
        value=value,
        unit=structured_field.unit,
        evidence=evidence,
    )


def _coerce(
    raw: object, structured_field: StructuredField
) -> StructuredScalar | tuple[object, ...] | FrozenMetadata:
    kind = structured_field.field_type
    if kind is StructuredFieldType.STRING:
        if not isinstance(raw, str):
            raise TypeError
        return raw.strip()
    if kind is StructuredFieldType.ENUM:
        if not isinstance(raw, str) or raw not in structured_field.enum_values:
            raise ValueError
        return raw
    if kind is StructuredFieldType.INTEGER:
        if isinstance(raw, bool):
            raise TypeError
        if isinstance(raw, int):
            return raw
        if not isinstance(raw, str) or re.fullmatch(r"[+-]?\d+", raw.strip()) is None:
            raise ValueError
        return int(raw)
    if kind is StructuredFieldType.DECIMAL:
        if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
            raise TypeError
        text = str(raw).strip()
        if structured_field.unit:
            suffix = structured_field.unit
            if text.casefold().endswith(suffix.casefold()):
                text = text[: -len(suffix)].strip()
        if not _DECIMAL.fullmatch(text):
            raise ValueError
        return Decimal(text)
    if kind is StructuredFieldType.BOOLEAN:
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str) and raw.casefold() in {"true", "false"}:
            return raw.casefold() == "true"
        raise ValueError
    if kind is StructuredFieldType.DATE:
        if not isinstance(raw, str):
            raise TypeError
        return date.fromisoformat(raw)
    if kind is StructuredFieldType.DATETIME:
        if not isinstance(raw, str):
            raise TypeError
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if kind is StructuredFieldType.DURATION:
        if not isinstance(raw, str) or (match := _DURATION.fullmatch(raw)) is None:
            raise ValueError
        return timedelta(seconds=float(match.group("seconds")))
    if kind is StructuredFieldType.LIST:
        if not isinstance(raw, tuple):
            raise TypeError
        return raw
    if kind is StructuredFieldType.OBJECT:
        if not isinstance(raw, FrozenMetadata):
            raise TypeError
        return raw
    raise ValueError


def _absent(
    structured_field: StructuredField, status: StructuredValueStatus, reason: str
) -> StructuredValue:
    return StructuredValue(
        field=structured_field.name,
        field_type=structured_field.field_type,
        status=status,
        value=None,
        unit=structured_field.unit,
        evidence=(),
        reason=reason,
    )


def _evidence(
    candidate: AdvancedRetrievalCandidate, extracted: ExtractedStructuredRecord
) -> tuple[StructuredEvidence, ...]:
    return (
        StructuredEvidence(
            candidate_id=candidate.candidate_id,
            notebook_id=candidate.notebook_id,
            source_id=candidate.source_id,
            document_id=candidate.document_id,
            version_id=candidate.version_id,
            chunk_id=None if candidate.chunk is None else candidate.chunk.id,
            occurrence_id=candidate.occurrence_id,
            derivation_id=candidate.derivation_id,
            locator=candidate.locator,
            retrieval_paths=tuple(item.path for item in candidate.paths),
            extraction_method=extracted.extraction_method,
        ),
    )


def _deduplicate_records(
    records: list[StructuredRecord], evidence_limit: int
) -> list[StructuredRecord]:
    unique: dict[object, StructuredRecord] = {}
    for record in records:
        current = unique.get(record.record_id)
        if current is None:
            unique[record.record_id] = record
            continue
        evidence, _ = _bounded_evidence((*current.evidence, *record.evidence), evidence_limit)
        values = tuple(
            replace(
                old,
                evidence=_bounded_evidence((*old.evidence, *new.evidence), evidence_limit)[0],
            )
            for old, new in zip(current.values, record.values, strict=True)
        )
        unique[record.record_id] = replace(current, evidence=evidence, values=values)
    return list(unique.values())


def _distinct_records(
    records: list[StructuredRecord],
    fields: tuple[str, ...],
    evidence_limit: int,
    distinct_limit: int,
) -> list[StructuredRecord]:
    unique: dict[tuple[object, ...], StructuredRecord] = {}
    for record in records:
        key = tuple(_canonical_value(record.value_for(name)) for name in fields)
        current = unique.get(key)
        if current is None:
            if len(unique) >= distinct_limit:
                raise ContractValidationError("structured distinct budget exceeded")
            unique[key] = record
            continue
        evidence, _ = _bounded_evidence((*current.evidence, *record.evidence), evidence_limit)
        values = tuple(
            replace(
                old,
                evidence=_bounded_evidence((*old.evidence, *new.evidence), evidence_limit)[0],
            )
            for old, new in zip(current.values, record.values, strict=True)
        )
        unique[key] = replace(current, evidence=evidence, values=values)
    return list(unique.values())


def _matches(
    record: StructuredRecord,
    predicate: StructuredFilter,
    field_map: Mapping[str, StructuredField],
) -> bool:
    value = record.value_for(predicate.field)
    if predicate.operator is StructuredFilterOperator.IS_MISSING:
        return value.status is StructuredValueStatus.VALUE_MISSING
    if predicate.operator is StructuredFilterOperator.IS_PRESENT:
        return value.status is StructuredValueStatus.VALUE_PRESENT
    if value.status is not StructuredValueStatus.VALUE_PRESENT:
        return False
    structured_field = field_map[predicate.field]
    if predicate.operator is StructuredFilterOperator.IN:
        assert isinstance(predicate.value, tuple)
        targets = tuple(_literal(item, structured_field) for item in predicate.value)
        return value.value in targets
    target = _literal(cast(object, predicate.value), structured_field)
    if predicate.operator is StructuredFilterOperator.CONTAINS:
        if isinstance(value.value, str) and isinstance(target, str):
            return target in value.value
        if isinstance(value.value, tuple):
            return target in value.value
        raise ContractValidationError("CONTAINS requires string or list field")
    comparison = _cmp(cast(StructuredScalar, value.value), cast(StructuredScalar, target))
    return {
        StructuredFilterOperator.EQ: comparison == 0,
        StructuredFilterOperator.NE: comparison != 0,
        StructuredFilterOperator.GT: comparison > 0,
        StructuredFilterOperator.GTE: comparison >= 0,
        StructuredFilterOperator.LT: comparison < 0,
        StructuredFilterOperator.LTE: comparison <= 0,
    }[predicate.operator]


def _literal(raw: object, structured_field: StructuredField) -> object:
    try:
        return _coerce(raw, structured_field)
    except (ValueError, TypeError, InvalidOperation) as error:
        raise ContractValidationError(
            f"filter value is incompatible with {structured_field.name}"
        ) from error


def _compare_records(
    left: StructuredRecord, right: StructuredRecord, ordering: tuple[StructuredSort, ...]
) -> int:
    for item in ordering:
        left_value = left.value_for(item.field)
        right_value = right.value_for(item.field)
        left_missing = left_value.status is not StructuredValueStatus.VALUE_PRESENT
        right_missing = right_value.status is not StructuredValueStatus.VALUE_PRESENT
        if left_missing != right_missing:
            result = -1 if left_missing else 1
            if item.null_order is StructuredNullOrder.LAST:
                result = -result
        elif not left_missing:
            result = compare_structured_values(left_value, right_value)
            if item.direction is StructuredSortDirection.DESC:
                result = -result
        else:
            result = 0
        if result:
            return result
    return _cmp(str(left.record_id), str(right.record_id))


def _aggregate(
    specification: StructuredAggregation,
    members: list[StructuredRecord],
    evidence_limit: int,
) -> StructuredAggregateValue:
    selected = (
        members
        if specification.field is None
        else [
            member
            for member in members
            if member.value_for(specification.field).status is StructuredValueStatus.VALUE_PRESENT
        ]
    )
    evidence, truncated = _bounded_evidence(
        (evidence for member in selected for evidence in member.evidence), evidence_limit
    )
    operation = specification.operation
    if operation is StructuredAggregationOperation.COUNT:
        value: object = len(selected)
    else:
        assert specification.field is not None
        values = [member.value_for(specification.field).value for member in selected]
        if not values:
            return StructuredAggregateValue(
                name=specification.name,
                operation=operation,
                status=StructuredValueStatus.VALUE_MISSING,
                value=None,
                evidence=(),
                evidence_truncated=False,
            )
        if operation is StructuredAggregationOperation.DISTINCT_COUNT:
            value = len({_canonical_raw(item) for item in values})
        elif operation in {StructuredAggregationOperation.SUM, StructuredAggregationOperation.AVG}:
            if any(
                isinstance(item, bool) or not isinstance(item, (int, Decimal)) for item in values
            ):
                raise ContractValidationError(f"{operation.value} requires numeric values")
            numeric_values = cast(list[int | Decimal], values)
            total = sum((Decimal(item) for item in numeric_values), Decimal(0))
            value = (
                total if operation is StructuredAggregationOperation.SUM else total / len(values)
            )
        elif operation is StructuredAggregationOperation.MIN:
            value = min(cast(list[StructuredScalar], values))
        elif operation is StructuredAggregationOperation.MAX:
            value = max(cast(list[StructuredScalar], values))
        else:  # pragma: no cover - exhaustive enum guard
            raise ContractValidationError("unsupported aggregation")
    return StructuredAggregateValue(
        name=specification.name,
        operation=operation,
        status=StructuredValueStatus.VALUE_PRESENT,
        value=cast(int | Decimal | StructuredScalar, value),
        evidence=evidence,
        evidence_truncated=truncated,
    )


def _bounded_evidence(
    evidence: Iterable[StructuredEvidence], limit: int
) -> tuple[tuple[StructuredEvidence, ...], bool]:
    unique: dict[tuple[object, ...], StructuredEvidence] = {}
    truncated = False
    for item in evidence:
        key = (
            item.candidate_id,
            item.chunk_id,
            item.occurrence_id,
            item.derivation_id,
            item.locator,
        )
        if key in unique:
            continue
        if len(unique) >= limit:
            truncated = True
            continue
        unique[key] = item
    return tuple(unique.values()), truncated


def _canonical_value(value: StructuredValue) -> tuple[object, ...]:
    return (value.field_type.value, value.status.value, value.unit, _canonical_raw(value.value))


def _canonical_raw(value: object) -> object:
    if isinstance(value, Decimal):
        return ("decimal", format(value.normalize(), "f"))
    if isinstance(value, (date, datetime)):
        return (type(value).__name__, value.isoformat())
    if isinstance(value, timedelta):
        return ("duration", value.total_seconds())
    if isinstance(value, FrozenMetadata):
        return ("object", repr(value))
    if isinstance(value, tuple):
        return ("list", tuple(_canonical_raw(item) for item in value))
    return value


def _cmp(left: object, right: object) -> int:
    if left == right:
        return 0
    try:
        return -1 if left < right else 1  # type: ignore[operator]
    except TypeError as error:
        raise ContractValidationError("incompatible structured values") from error


def _group_id(key: tuple[object, ...]) -> str:
    import hashlib

    return hashlib.sha256(repr(key).encode()).hexdigest()


def _structured_completeness(
    retrieval: RetrievalCompleteness,
    truncated: bool,
    has_results: bool,
    incomplete_values: bool,
) -> RetrievalCompleteness:
    if truncated:
        return RetrievalCompleteness.TRUNCATED
    if retrieval in {
        RetrievalCompleteness.PARTIAL,
        RetrievalCompleteness.TRUNCATED,
        RetrievalCompleteness.UNKNOWN,
    }:
        return retrieval
    if incomplete_values:
        return RetrievalCompleteness.PARTIAL
    return RetrievalCompleteness.COMPLETE if has_results else RetrievalCompleteness.EMPTY


def _result_size(records: list[StructuredRecord], groups: tuple[StructuredGroupResult, ...]) -> int:
    material = {
        "records": [
            {
                "id": str(record.record_id),
                "values": [(_canonical_value(value)) for value in record.values],
            }
            for record in records
        ],
        "groups": [
            {
                "id": group.group_id,
                "members": [str(item) for item in group.member_record_ids],
                "aggregates": [
                    (item.name, _canonical_raw(item.value)) for item in group.aggregates
                ],
            }
            for group in groups
        ],
    }
    return len(
        json.dumps(material, ensure_ascii=False, default=str, separators=(",", ":")).encode()
    )


def _fit_output(
    records: list[StructuredRecord],
    groups: tuple[StructuredGroupResult, ...],
    maximum: int,
) -> tuple[list[StructuredRecord], int]:
    fitted: list[StructuredRecord] = []
    size = _result_size(fitted, groups)
    for record in records:
        candidate = [*fitted, record]
        candidate_size = _result_size(candidate, groups)
        if candidate_size > maximum:
            break
        fitted.append(record)
        size = candidate_size
    return fitted, size


def _elapsed(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _provenance_raw(candidate: AdvancedRetrievalCandidate, source_name: str | None) -> object:
    if source_name is None or not source_name.startswith("$"):
        return None
    system = {
        "$notebook_id": str(candidate.notebook_id),
        "$source_id": str(candidate.source_id),
        "$document_id": str(candidate.document_id),
        "$version_id": str(candidate.version_id),
        "$document_title": candidate.document_title,
        "$page": candidate.locator.get("page"),
        "$slide": candidate.locator.get("slide"),
        "$sheet": candidate.locator.get("sheet"),
    }
    if source_name not in system:
        raise ContractValidationError("unknown structured provenance field")
    return system[source_name]


def _json_depth(value: object) -> int:
    if isinstance(value, FrozenMetadata):
        return 1 + max((_json_depth(item) for item in value.values()), default=0)
    if isinstance(value, tuple):
        return 1 + max((_json_depth(item) for item in value), default=0)
    return 0
