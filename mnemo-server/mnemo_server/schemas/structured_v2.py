"""Strict public DTOs for Phase 8.5 structured retrieval."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StructuredOperation(StrEnum):
    DESCRIBE = "describe"
    QUERY = "query"
    UNION = "union"
    JOIN = "join"


class PublicFilterOperator(StrEnum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    BETWEEN = "between"
    IN = "in"
    IS_MISSING = "is_missing"
    IS_PRESENT = "is_present"


class StructuredScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    notebook_id: UUID
    source_ids: tuple[UUID, ...] = Field(default=(), max_length=100)
    document_ids: tuple[UUID, ...] = Field(default=(), max_length=100)
    version_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100)

    @field_validator("source_ids", "document_ids", "version_ids")
    @classmethod
    def unique_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("scope identities must be unique")
        return value


class StructuredFilterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(min_length=1, max_length=256)
    operator: PublicFilterOperator
    value: Any = None

    @model_validator(mode="after")
    def validate_value_shape(self) -> StructuredFilterRequest:
        unary = {PublicFilterOperator.IS_MISSING, PublicFilterOperator.IS_PRESENT}
        if self.operator in unary and self.value is not None:
            raise ValueError("presence predicates do not accept values")
        if self.operator not in unary and self.value is None:
            raise ValueError("predicate requires a value")
        if self.operator is PublicFilterOperator.BETWEEN and (
            not isinstance(self.value, list) or len(self.value) != 2
        ):
            raise ValueError("between requires exactly two values")
        if self.operator is PublicFilterOperator.IN and (
            not isinstance(self.value, list) or not self.value or len(self.value) > 100
        ):
            raise ValueError("in requires one through 100 values")
        return self


class StructuredSortRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(min_length=1, max_length=256)
    direction: str = Field(default="asc", pattern="^(asc|desc)$")
    null_order: str = Field(default="last", pattern="^(first|last)$")


class StructuredAggregationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    operation: str = Field(pattern="^(count|distinct_count|sum|min|max|avg)$")
    field: str | None = Field(default=None, min_length=1, max_length=256)


class StructuredJoinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    left_dataset_id: UUID
    right_dataset_id: UUID
    left_field: str = Field(min_length=1, max_length=256)
    right_field: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def distinct_datasets(self) -> StructuredJoinRequest:
        if self.left_dataset_id == self.right_dataset_id:
            raise ValueError("join datasets must be distinct")
        return self


class StructuredRetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: StructuredOperation
    scope: StructuredScopeRequest
    dataset_ids: tuple[UUID, ...] = Field(default=(), max_length=16)
    select_fields: tuple[str, ...] = Field(default=(), max_length=64)
    filters: tuple[StructuredFilterRequest, ...] = Field(default=(), max_length=64)
    group_by: tuple[str, ...] = Field(default=(), max_length=16)
    aggregations: tuple[StructuredAggregationRequest, ...] = Field(default=(), max_length=16)
    order_by: tuple[StructuredSortRequest, ...] = Field(default=(), max_length=16)
    distinct_fields: tuple[str, ...] = Field(default=(), max_length=16)
    join: StructuredJoinRequest | None = None
    cursor: str | None = Field(default=None, max_length=8192)
    page_size: int = Field(default=100, ge=1, le=1000)

    @field_validator("dataset_ids", "select_fields", "group_by", "distinct_fields")
    @classmethod
    def unique_values(cls, value):  # type: ignore[no-untyped-def]
        if len(value) != len(set(value)):
            raise ValueError("structured request selections must be unique")
        return value

    @model_validator(mode="after")
    def operation_contract(self) -> StructuredRetrievalRequest:
        if self.operation is StructuredOperation.DESCRIBE:
            if self.cursor or self.join or self.filters or self.aggregations:
                raise ValueError("describe does not accept query execution fields")
        elif self.operation is StructuredOperation.JOIN:
            if self.join is None:
                raise ValueError("join operation requires join")
            if self.dataset_ids and set(self.dataset_ids) != {
                self.join.left_dataset_id,
                self.join.right_dataset_id,
            }:
                raise ValueError("dataset_ids must match the explicit join datasets")
            if self.filters or self.group_by or self.aggregations or self.distinct_fields:
                raise ValueError("WP-08 equality join does not accept query expressions")
        else:
            if self.join is not None:
                raise ValueError("join is valid only for the join operation")
            if not self.dataset_ids:
                raise ValueError("query and union operations require dataset_ids")
            if self.operation is StructuredOperation.QUERY and len(self.dataset_ids) != 1:
                raise ValueError("query operates on exactly one dataset; use union explicitly")
            if self.operation is StructuredOperation.UNION and len(self.dataset_ids) < 2:
                raise ValueError("union requires at least two datasets")
        return self


class StructuredRetrievalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str
    schema_version: str
    operation: str
    request_id: UUID
    snapshot_identity: str
    scope: dict[str, Any]
    representations_requested: list[str]
    representations_searched: list[str]
    completeness: str
    coverage: dict[str, Any]
    items: list[dict[str, Any]]
    next_cursor: str | None
    limits: dict[str, Any]
    omissions: list[str]
    recommended_next_actions: list[dict[str, Any]]
    structured: dict[str, Any]
