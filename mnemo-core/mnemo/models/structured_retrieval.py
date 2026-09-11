"""Typed Phase 8.5.7 structured-retrieval and aggregation contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ._shared import FrozenMetadata, JSONPrimitive, require_non_empty, require_sha256
from .advanced_retrieval import RetrievalCompleteness, RetrievalPlanV2

STRUCTURED_QUERY_VERSION = "structured-query-v1/1"
_RECORD_NAMESPACE = UUID("fb8436da-9745-5dbb-b674-89c5a0c5d106")


class StructuredFieldType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    DURATION = "duration"
    ENUM = "enum"
    LIST = "list"
    OBJECT = "object"


class StructuredValueStatus(StrEnum):
    VALUE_PRESENT = "value_present"
    VALUE_MISSING = "value_missing"
    VALUE_UNCERTAIN = "value_uncertain"
    VALUE_INVALID = "value_invalid"
    VALUE_UNAVAILABLE = "value_unavailable"


class StructuredSchemaConfidence(StrEnum):
    """Confidence in a deterministic table-column type observation."""

    EXACT = "exact"
    OBSERVED = "observed"
    AMBIGUOUS = "ambiguous"


class StructuredFilterOperator(StrEnum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    CONTAINS = "contains"
    IS_MISSING = "is_missing"
    IS_PRESENT = "is_present"


class StructuredSortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class StructuredNullOrder(StrEnum):
    FIRST = "first"
    LAST = "last"


class StructuredAggregationOperation(StrEnum):
    COUNT = "count"
    DISTINCT_COUNT = "distinct_count"
    SUM = "sum"
    MIN = "min"
    MAX = "max"
    AVG = "avg"


class StructuredField(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    field_type: StructuredFieldType
    source_name: str | None = None
    unit: str | None = None
    enum_values: tuple[str, ...] = ()
    required: bool = False

    @field_validator("name", "source_name", "unit")
    @classmethod
    def _non_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("field strings must not be empty")
        return value

    @model_validator(mode="after")
    def _enum_contract(self) -> StructuredField:
        if self.field_type is StructuredFieldType.ENUM and not self.enum_values:
            raise ValueError("enum fields require enum_values")
        if self.field_type is not StructuredFieldType.ENUM and self.enum_values:
            raise ValueError("enum_values are only valid for enum fields")
        if len(self.enum_values) != len(set(self.enum_values)):
            raise ValueError("enum_values must be unique")
        return self


class StructuredFilter(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    operator: StructuredFilterOperator
    value: JSONPrimitive | tuple[JSONPrimitive, ...] = None

    @field_validator("field")
    @classmethod
    def _field_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("filter field must not be empty")
        return value

    @model_validator(mode="after")
    def _operator_value(self) -> StructuredFilter:
        unary = {
            StructuredFilterOperator.IS_MISSING,
            StructuredFilterOperator.IS_PRESENT,
        }
        if self.operator in unary and self.value is not None:
            raise ValueError("presence filters do not accept a value")
        if self.operator not in unary and self.value is None:
            raise ValueError("filter operator requires a value")
        if self.operator is StructuredFilterOperator.IN and not isinstance(self.value, tuple):
            raise ValueError("IN requires a tuple of values")
        return self


class StructuredSort(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    direction: StructuredSortDirection = StructuredSortDirection.ASC
    null_order: StructuredNullOrder = StructuredNullOrder.LAST

    @field_validator("field")
    @classmethod
    def _field_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("sort field must not be empty")
        return value


class StructuredAggregation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    operation: StructuredAggregationOperation
    field: str | None = None

    @field_validator("name", "field")
    @classmethod
    def _non_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("aggregation strings must not be empty")
        return value

    @model_validator(mode="after")
    def _field_required(self) -> StructuredAggregation:
        if self.operation is not StructuredAggregationOperation.COUNT and self.field is None:
            raise ValueError("aggregation requires a field")
        return self


class StructuredBudgets(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_records: int = Field(default=1000, strict=True, ge=1, le=100_000)
    max_fields: int = Field(default=64, strict=True, ge=1, le=256)
    max_groups: int = Field(default=1000, strict=True, ge=1, le=50_000)
    max_aggregation_rows: int = Field(default=100_000, strict=True, ge=1, le=1_000_000)
    max_evidence_references: int = Field(default=1000, strict=True, ge=1, le=100_000)
    max_output_bytes: int = Field(default=2_000_000, strict=True, ge=256, le=20_000_000)
    max_output_tokens: int = Field(default=500_000, strict=True, ge=64, le=5_000_000)
    max_nesting_depth: int = Field(default=8, strict=True, ge=1, le=32)
    max_distinct_values: int = Field(default=10_000, strict=True, ge=1, le=100_000)


class StructuredQueryV1(BaseModel):
    """Allowlisted structured AST evaluated over one V2 retrieval result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    retrieval_plan: RetrievalPlanV2
    fields: tuple[StructuredField, ...]
    filters: tuple[StructuredFilter, ...] = ()
    group_by: tuple[str, ...] = ()
    aggregations: tuple[StructuredAggregation, ...] = ()
    order_by: tuple[StructuredSort, ...] = ()
    distinct_fields: tuple[str, ...] = ()
    offset: int = Field(default=0, strict=True, ge=0)
    limit: int = Field(default=100, strict=True, ge=1, le=10_000)
    budgets: StructuredBudgets = StructuredBudgets()

    @model_validator(mode="after")
    def _validate_ast(self) -> StructuredQueryV1:
        names = tuple(field.name for field in self.fields)
        if not names or len(names) != len(set(names)):
            raise ValueError("fields must be non-empty and uniquely named")
        if len(names) > self.budgets.max_fields:
            raise ValueError("field count exceeds structured budget")
        allowed = set(names)
        referenced = (
            [item.field for item in self.filters]
            + list(self.group_by)
            + [item.field for item in self.order_by]
            + list(self.distinct_fields)
            + [item.field for item in self.aggregations if item.field is not None]
        )
        unknown = sorted(set(referenced) - allowed)
        if unknown:
            raise ValueError(f"structured query references unknown fields: {unknown}")
        aggregate_names = [item.name for item in self.aggregations]
        if len(aggregate_names) != len(set(aggregate_names)):
            raise ValueError("aggregation names must be unique")
        if set(aggregate_names) & allowed:
            raise ValueError("aggregation names must not shadow fields")
        if len(self.group_by) != len(set(self.group_by)):
            raise ValueError("group_by fields must be unique")
        return self

    @property
    def fingerprint(self) -> str:
        material = {"version": STRUCTURED_QUERY_VERSION, "query": self.model_dump(mode="json")}
        return hashlib.sha256(_canonical_json(material)).hexdigest()


type StructuredScalar = str | int | Decimal | bool | date | datetime | timedelta


@dataclass(frozen=True, slots=True, kw_only=True)
class StructuredColumnObservation:
    name: str
    column_index: int
    observed_type: StructuredFieldType
    confidence: StructuredSchemaConfidence
    non_missing_count: int

    def __post_init__(self) -> None:
        require_non_empty(self.name, "name")
        if isinstance(self.column_index, bool) or self.column_index < 0:
            raise ValueError("column_index must be non-negative")
        if isinstance(self.non_missing_count, bool) or self.non_missing_count < 0:
            raise ValueError("non_missing_count must be non-negative")


@dataclass(frozen=True, slots=True, kw_only=True)
class StructuredSchemaObservation:
    generation: str
    columns: tuple[StructuredColumnObservation, ...]
    row_count: int

    def __post_init__(self) -> None:
        require_sha256(self.generation, "generation")
        if isinstance(self.row_count, bool) or self.row_count < 0:
            raise ValueError("row_count must be non-negative")
        if not self.columns:
            raise ValueError("schema observation requires columns")


@dataclass(frozen=True, slots=True, kw_only=True)
class StructuredEvidence:
    candidate_id: UUID
    notebook_id: UUID
    source_id: UUID
    document_id: UUID
    version_id: UUID
    chunk_id: str | None
    occurrence_id: UUID | None
    derivation_id: UUID | None
    locator: FrozenMetadata
    retrieval_paths: tuple[str, ...]
    extraction_method: str

    def __post_init__(self) -> None:
        require_non_empty(self.extraction_method, "extraction_method")
        if not self.retrieval_paths:
            raise ValueError("structured evidence requires retrieval paths")


@dataclass(frozen=True, slots=True, kw_only=True)
class StructuredValue:
    field: str
    field_type: StructuredFieldType
    status: StructuredValueStatus
    value: StructuredScalar | tuple[object, ...] | FrozenMetadata | None
    unit: str | None
    evidence: tuple[StructuredEvidence, ...]
    reason: str | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.field, "field")
        if self.status is StructuredValueStatus.VALUE_PRESENT:
            if self.value is None or not self.evidence:
                raise ValueError("present structured value requires value and evidence")
        elif self.value is not None:
            raise ValueError("non-present structured value cannot carry a value")
        if self.reason is not None:
            require_non_empty(self.reason, "reason")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtractedStructuredRecord:
    candidate_id: UUID
    row_ordinal: int
    values: FrozenMetadata
    cell_locators: FrozenMetadata = field(default_factory=FrozenMetadata)
    extraction_method: str = "deterministic_table"

    def __post_init__(self) -> None:
        if isinstance(self.row_ordinal, bool) or self.row_ordinal < 0:
            raise ValueError("row_ordinal must be non-negative")
        require_non_empty(self.extraction_method, "extraction_method")


@dataclass(frozen=True, slots=True, kw_only=True)
class StructuredRecord:
    record_id: UUID
    candidate_id: UUID
    row_ordinal: int
    values: tuple[StructuredValue, ...]
    evidence: tuple[StructuredEvidence, ...]

    def value_for(self, name: str) -> StructuredValue:
        for value in self.values:
            if value.field == name:
                return value
        raise KeyError(name)


@dataclass(frozen=True, slots=True, kw_only=True)
class StructuredAggregateValue:
    name: str
    operation: StructuredAggregationOperation
    status: StructuredValueStatus
    value: int | Decimal | StructuredScalar | None
    evidence: tuple[StructuredEvidence, ...]
    evidence_truncated: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class StructuredGroupResult:
    group_id: str
    keys: tuple[StructuredValue, ...]
    member_record_ids: tuple[UUID, ...]
    aggregates: tuple[StructuredAggregateValue, ...]
    evidence: tuple[StructuredEvidence, ...]
    evidence_truncated: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class StructuredDiagnostics:
    candidates_examined: int
    extracted_records: int
    deduplicated_records: int
    filtered_records: int
    returned_records: int
    group_count: int
    evidence_references: int
    output_bytes: int
    truncated: bool
    truncation_reasons: tuple[str, ...]
    stage_milliseconds: FrozenMetadata


@dataclass(frozen=True, slots=True, kw_only=True)
class StructuredResultMetadata:
    schema_generation: str
    retrieval_snapshot_identity: str
    candidate_universe_count: int
    extracted_row_universe_count: int
    matched_count: int
    returned_count: int
    operations: tuple[str, ...]
    provenance_truncated: bool

    def __post_init__(self) -> None:
        require_sha256(self.schema_generation, "schema_generation")
        require_sha256(self.retrieval_snapshot_identity, "retrieval_snapshot_identity")
        if any(
            isinstance(value, bool) or value < 0
            for value in (
                self.candidate_universe_count,
                self.extracted_row_universe_count,
                self.matched_count,
                self.returned_count,
            )
        ):
            raise ValueError("structured result counts must be non-negative integers")


@dataclass(frozen=True, slots=True, kw_only=True)
class StructuredResult:
    query_fingerprint: str
    retrieval_fingerprint: str
    retrieval_completeness: RetrievalCompleteness
    completeness: RetrievalCompleteness
    records: tuple[StructuredRecord, ...]
    groups: tuple[StructuredGroupResult, ...]
    matched_count: int
    returned_count: int
    next_offset: int | None
    metadata: StructuredResultMetadata
    diagnostics: StructuredDiagnostics

    def __post_init__(self) -> None:
        require_sha256(self.query_fingerprint, "query_fingerprint")
        require_sha256(self.retrieval_fingerprint, "retrieval_fingerprint")
        if self.returned_count != len(self.records):
            raise ValueError("returned_count must match records")
        if (
            self.next_offset is not None
            and self.completeness is not RetrievalCompleteness.TRUNCATED
        ):
            raise ValueError("next_offset requires truncated completeness")


def structured_record_id(candidate_id: UUID, row_ordinal: int) -> UUID:
    if isinstance(row_ordinal, bool) or row_ordinal < 0:
        raise ValueError("row_ordinal must be non-negative")
    return uuid5(_RECORD_NAMESPACE, f"{candidate_id}:{row_ordinal}")


def structured_schema_generation(fields: tuple[StructuredField, ...]) -> str:
    material = {
        "version": STRUCTURED_QUERY_VERSION,
        "fields": [field.model_dump(mode="json") for field in fields],
    }
    return hashlib.sha256(_canonical_json(material)).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
