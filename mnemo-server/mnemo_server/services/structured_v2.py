"""Shared HTTP/MCP application service for exact structured retrieval."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from mnemo.cursors import CursorCodecV2, CursorSigningKeyV2
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import ContractValidationError, OperationTimeoutError
from mnemo.models import (
    AdvancedRetrievalMode,
    DeduplicationPolicy,
    EvidenceRepresentation,
    ExpansionPolicy,
    PositionalScopeV2,
    RankingPolicyV2,
    RetrievalBudgetsV2,
    RetrievalCompleteness,
    RetrievalPlanV2,
    RetrievalScopeV2,
    StructuredAggregation,
    StructuredAggregationOperation,
    StructuredBudgets,
    StructuredDatasetCatalog,
    StructuredDatasetDescriptor,
    StructuredDatasetReadiness,
    StructuredField,
    StructuredFilter,
    StructuredFilterOperator,
    StructuredNullOrder,
    StructuredQueryV1,
    StructuredRecord,
    StructuredResult,
    StructuredSort,
    StructuredSortDirection,
    StructuredValueStatus,
    thaw_metadata,
)

from mnemo_server.config import ServerConfig
from mnemo_server.schemas.structured_v2 import (
    PublicFilterOperator,
    StructuredOperation,
    StructuredRetrievalRequest,
    StructuredRetrievalResponse,
)
from mnemo_server.services.authorization import (
    AuthorizationOperationV1,
    CentralAuthorizationServiceV1,
    ServerPrincipalV1,
    principal_from_claims,
)

CONTRACT_VERSION = "mnemo.structured/v2"
_CURSOR_DOMAIN = "mnemo-structured-retrieval/v2"


class StructuredRetrievalApplicationService:
    def __init__(self, engine: KnowledgeEngine, config: ServerConfig) -> None:
        self._engine = engine
        self._config = config
        secret = config.delivery_cursor_secret.encode()
        if len(secret) < 32:
            secret = hashlib.sha256(secret).digest()
        self._cursor = CursorCodecV2(
            CursorSigningKeyV2(key_id=f"structured-{config.delivery_cursor_key_id}", secret=secret),
            verification_keys=tuple(
                CursorSigningKeyV2(key_id=f"structured-{key_id}", secret=value.encode())
                for key_id, value in config.delivery_cursor_rotation_keys
            ),
            ttl=timedelta(seconds=config.delivery_cursor_ttl_seconds),
        )

    async def execute(
        self, request: StructuredRetrievalRequest, principal: ServerPrincipalV1 | None = None
    ) -> StructuredRetrievalResponse:
        scope = RetrievalScopeV2(**request.scope.model_dump())
        principal = principal or principal_from_claims(None)
        try:
            if type(self._engine) is KnowledgeEngine:
                await CentralAuthorizationServiceV1(self._engine).authorize_notebook(
                    principal, scope.notebook_id, AuthorizationOperationV1.QUERY
                )
            async with asyncio.timeout(self._config.max_structured_elapsed_milliseconds / 1000):
                catalog = await self._engine.structured_retrieval.discover(
                    scope=scope,
                    schema_scan_limit=self._config.max_structured_rows_scanned,
                )
                if request.operation is StructuredOperation.DESCRIBE:
                    response = self._describe(request, catalog)
                elif request.operation is StructuredOperation.JOIN:
                    response = await self._join(request, catalog, principal)
                else:
                    response = await self._query(request, catalog, principal)
        except TimeoutError as error:
            raise OperationTimeoutError("structured retrieval deadline expired") from error
        if len(response.model_dump_json().encode()) > self._config.max_structured_response_bytes:
            raise ContractValidationError(
                "structured response exceeds the server byte ceiling; lower page_size"
            )
        return response

    def _describe(
        self, request: StructuredRetrievalRequest, catalog: StructuredDatasetCatalog
    ) -> StructuredRetrievalResponse:
        items = [_dataset_item(item) for item in catalog.datasets]
        completeness = (
            "partial" if catalog.unavailable_version_ids else "empty" if not items else "complete"
        )
        return self._response(
            request,
            catalog,
            items=items,
            completeness=completeness,
            next_cursor=None,
            omissions=[
                f"version:{version_id}:structured_generation_unavailable"
                for version_id in catalog.unavailable_version_ids
            ],
            structured={
                "dataset_ids": [str(item.dataset_id) for item in catalog.datasets],
                "matched_count": len(items),
                "returned_count": len(items),
                "ordering_policy": "document_version_block_dataset",
                "supported_operations": [
                    "describe",
                    "query",
                    "union_compatible",
                    "equality_join",
                ],
            },
        )

    async def _query(
        self,
        request: StructuredRetrievalRequest,
        catalog: StructuredDatasetCatalog,
        principal: ServerPrincipalV1,
    ) -> StructuredRetrievalResponse:
        selected = _selected(catalog, request.dataset_ids)
        query = _compile_query(request, selected, self._config)
        result = await self._engine.structured_retrieval.execute(
            query=query, catalog=catalog, dataset_ids=request.dataset_ids
        )
        request_fingerprint = _request_fingerprint(request, principal)
        offset = self._decode_offset(request, catalog, request_fingerprint)
        page_size = min(request.page_size, self._config.max_structured_page_size)
        aggregate_mode = bool(request.group_by or request.aggregations)
        all_items = (
            [_group_item(item) for item in result.groups]
            if aggregate_mode
            else [_record_item(item, request.select_fields) for item in result.records]
        )
        page = all_items[offset : offset + page_size]
        more = offset + len(page) < len(all_items)
        scan_incomplete = result.completeness in {
            RetrievalCompleteness.TRUNCATED,
            RetrievalCompleteness.PARTIAL,
            RetrievalCompleteness.UNKNOWN,
        }
        next_cursor = (
            self._encode_cursor(
                request,
                catalog,
                request_fingerprint,
                offset + len(page),
            )
            if more and not scan_incomplete
            else None
        )
        completeness = (
            "partial"
            if scan_incomplete or catalog.unavailable_version_ids
            else "truncated"
            if more
            else "empty"
            if not all_items
            else "complete"
        )
        omissions = list(result.diagnostics.truncation_reasons)
        omissions.extend(
            f"version:{item}:structured_generation_unavailable"
            for item in catalog.unavailable_version_ids
        )
        return self._response(
            request,
            catalog,
            items=page,
            completeness=completeness,
            next_cursor=next_cursor,
            omissions=omissions,
            structured={
                "dataset_ids": [str(item.dataset_id) for item in selected],
                "schema_identity": result.metadata.schema_generation,
                "generation_ids": [str(item.generation_id) for item in selected],
                "matched_count": result.matched_count,
                "returned_count": len(page),
                "aggregate_evidence": aggregate_mode,
                "ordering_policy": "typed_order_then_stable_record_identity",
                "null_policy": [item.model_dump(mode="json") for item in query.order_by],
                "predicate_summary": [item.model_dump(mode="json") for item in query.filters],
                "execution_bounds": query.budgets.model_dump(mode="json"),
            },
        )

    async def _join(
        self,
        request: StructuredRetrievalRequest,
        catalog: StructuredDatasetCatalog,
        principal: ServerPrincipalV1,
    ) -> StructuredRetrievalResponse:
        assert request.join is not None
        selected = _selected(catalog, (request.join.left_dataset_id, request.join.right_dataset_id))
        left, right = selected
        left_field = _field(left, request.join.left_field)
        right_field = _field(right, request.join.right_field)
        if (left_field.field_type, left_field.unit) != (
            right_field.field_type,
            right_field.unit,
        ):
            raise ContractValidationError("equality join fields have incompatible types")
        left_result = await self._execute_full_dataset(request, catalog, left)
        right_result = await self._execute_full_dataset(request, catalog, right)
        pairs: list[dict[str, Any]] = []
        for left_record in left_result.records:
            left_value = left_record.value_for(left_field.name)
            if left_value.status is not StructuredValueStatus.VALUE_PRESENT:
                continue
            for right_record in right_result.records:
                right_value = right_record.value_for(right_field.name)
                if right_value.status is not StructuredValueStatus.VALUE_PRESENT:
                    continue
                if left_value.value == right_value.value:
                    pairs.append(
                        {
                            "left": _record_item(left_record, request.select_fields),
                            "right": _record_item(right_record, request.select_fields),
                            "join_key": _json_value(left_value.value),
                            "provenance": {
                                "left_dataset_id": str(left.dataset_id),
                                "right_dataset_id": str(right.dataset_id),
                                "left_record_id": str(left_record.record_id),
                                "right_record_id": str(right_record.record_id),
                            },
                        }
                    )
                    if len(pairs) > self._config.max_structured_rows_returned:
                        break
            if len(pairs) > self._config.max_structured_rows_returned:
                break
        scan_incomplete = any(
            result.completeness is not RetrievalCompleteness.COMPLETE
            and result.completeness is not RetrievalCompleteness.EMPTY
            for result in (left_result, right_result)
        )
        offset = self._decode_offset(request, catalog, _request_fingerprint(request, principal))
        page_size = min(request.page_size, self._config.max_structured_page_size)
        page = pairs[offset : offset + page_size]
        more = offset + len(page) < len(pairs)
        next_cursor = (
            self._encode_cursor(
                request, catalog, _request_fingerprint(request, principal), offset + len(page)
            )
            if more and not scan_incomplete
            else None
        )
        completeness = (
            "partial"
            if scan_incomplete or len(pairs) > self._config.max_structured_rows_returned
            else "truncated"
            if more
            else "empty"
            if not pairs
            else "complete"
        )
        return self._response(
            request,
            catalog,
            items=page,
            completeness=completeness,
            next_cursor=next_cursor,
            omissions=(
                ["equality_join_output_bound"]
                if len(pairs) > self._config.max_structured_rows_returned
                else []
            ),
            structured={
                "dataset_ids": [str(left.dataset_id), str(right.dataset_id)],
                "generation_ids": [str(left.generation_id), str(right.generation_id)],
                "matched_count": len(pairs),
                "returned_count": len(page),
                "join": request.join.model_dump(mode="json"),
                "ordering_policy": "left_record_then_right_record",
                "null_policy": "null_keys_do_not_match",
                "execution_bounds": self._limits(request),
            },
        )

    async def _execute_full_dataset(
        self,
        request: StructuredRetrievalRequest,
        catalog: StructuredDatasetCatalog,
        dataset: StructuredDatasetDescriptor,
    ) -> StructuredResult:
        clone = request.model_copy(
            update={
                "operation": StructuredOperation.QUERY,
                "dataset_ids": (dataset.dataset_id,),
                "select_fields": (),
                "cursor": None,
                "join": None,
            }
        )
        query = _compile_query(clone, (dataset,), self._config)
        return await self._engine.structured_retrieval.execute(
            query=query, catalog=catalog, dataset_ids=(dataset.dataset_id,)
        )

    def _decode_offset(
        self,
        request: StructuredRetrievalRequest,
        catalog: StructuredDatasetCatalog,
        fingerprint: str,
    ) -> int:
        if request.cursor is None:
            return 0
        state = self._cursor.decode(
            request.cursor,
            expected_domain=_CURSOR_DOMAIN,
            expected_binding={
                "notebook_id": str(request.scope.notebook_id),
                "request_fingerprint": fingerprint,
                "dataset_ids": sorted(str(item) for item in _request_dataset_ids(request)),
            },
            expected_snapshot_identity=catalog.snapshot_identity,
            expected_limits=self._limits(request),
        )
        offset = state.position.get("offset")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ContractValidationError("structured cursor position is invalid")
        return offset

    def _encode_cursor(
        self,
        request: StructuredRetrievalRequest,
        catalog: StructuredDatasetCatalog,
        fingerprint: str,
        offset: int,
    ) -> str:
        return self._cursor.encode(
            domain=_CURSOR_DOMAIN,
            snapshot_identity=catalog.snapshot_identity,
            binding={
                "notebook_id": str(request.scope.notebook_id),
                "request_fingerprint": fingerprint,
                "dataset_ids": sorted(str(item) for item in _request_dataset_ids(request)),
            },
            position={"offset": offset},
            limits=self._limits(request),
        )

    def _limits(self, request: StructuredRetrievalRequest) -> dict[str, object]:
        return {
            "rows_scanned": self._config.max_structured_rows_scanned,
            "rows_returned": self._config.max_structured_rows_returned,
            "groups": self._config.max_structured_groups,
            "fields": self._config.max_structured_fields,
            "evidence": self._config.max_structured_evidence,
            "bytes": self._config.max_structured_response_bytes,
            "milliseconds": self._config.max_structured_elapsed_milliseconds,
            "page_size": min(request.page_size, self._config.max_structured_page_size),
        }

    def _response(
        self,
        request: StructuredRetrievalRequest,
        catalog: StructuredDatasetCatalog,
        *,
        items: list[dict[str, Any]],
        completeness: str,
        next_cursor: str | None,
        omissions: list[str],
        structured: dict[str, Any],
    ) -> StructuredRetrievalResponse:
        actions = []
        if next_cursor is not None:
            actions.append(
                {
                    "tool": "query_structured",
                    "reason": "Continue the unchanged exact structured query.",
                    "pass_cursor_unchanged": True,
                    "stop_condition": "next_cursor is null",
                }
            )
        return StructuredRetrievalResponse(
            contract_version=CONTRACT_VERSION,
            schema_version=CONTRACT_VERSION,
            operation=request.operation.value,
            request_id=uuid4(),
            snapshot_identity=catalog.snapshot_identity,
            scope=request.scope.model_dump(mode="json"),
            representations_requested=["structured_table"],
            representations_searched=(["structured_table"] if catalog.ready_version_ids else []),
            completeness=completeness,
            coverage={
                "requested_versions": [str(item) for item in catalog.requested_version_ids],
                "ready_versions": [str(item) for item in catalog.ready_version_ids],
                "unavailable_versions": [str(item) for item in catalog.unavailable_version_ids],
            },
            items=items,
            next_cursor=next_cursor,
            limits=self._limits(request),
            omissions=omissions,
            recommended_next_actions=actions,
            structured=structured,
        )


def _compile_query(
    request: StructuredRetrievalRequest,
    datasets: tuple[StructuredDatasetDescriptor, ...],
    config: ServerConfig,
) -> StructuredQueryV1:
    first = datasets[0]
    schema = {item.field.name.casefold(): item.field for item in first.fields}
    if len(schema) > config.max_structured_fields:
        raise ContractValidationError("structured schema exceeds the field ceiling")
    for dataset in datasets[1:]:
        other = {
            item.field.name.casefold(): (item.field.field_type, item.field.unit)
            for item in dataset.fields
        }
        if {name: (field.field_type, field.unit) for name, field in schema.items()} != other:
            raise ContractValidationError("union requires compatible field names and types")
    fields = tuple(schema.values())
    filters: list[StructuredFilter] = []
    mapping = {
        PublicFilterOperator.EQ: StructuredFilterOperator.EQ,
        PublicFilterOperator.NE: StructuredFilterOperator.NE,
        PublicFilterOperator.GT: StructuredFilterOperator.GT,
        PublicFilterOperator.GTE: StructuredFilterOperator.GTE,
        PublicFilterOperator.LT: StructuredFilterOperator.LT,
        PublicFilterOperator.LTE: StructuredFilterOperator.LTE,
        PublicFilterOperator.IN: StructuredFilterOperator.IN,
        PublicFilterOperator.IS_MISSING: StructuredFilterOperator.IS_MISSING,
        PublicFilterOperator.IS_PRESENT: StructuredFilterOperator.IS_PRESENT,
    }
    for item in request.filters:
        field = _schema_field(schema, item.field)
        if item.operator is PublicFilterOperator.BETWEEN:
            filters.extend(
                (
                    StructuredFilter(
                        field=field.name,
                        operator=StructuredFilterOperator.GTE,
                        value=item.value[0],
                    ),
                    StructuredFilter(
                        field=field.name,
                        operator=StructuredFilterOperator.LTE,
                        value=item.value[1],
                    ),
                )
            )
        else:
            value = tuple(item.value) if item.operator is PublicFilterOperator.IN else item.value
            filters.append(
                StructuredFilter(
                    field=field.name,
                    operator=mapping[item.operator],
                    value=value,
                )
            )
    group_by = tuple(_schema_field(schema, name).name for name in request.group_by)
    order_by = tuple(
        StructuredSort(
            field=_schema_field(schema, item.field).name,
            direction=StructuredSortDirection(item.direction),
            null_order=StructuredNullOrder(item.null_order),
        )
        for item in request.order_by
    )
    distinct = tuple(_schema_field(schema, name).name for name in request.distinct_fields)
    aggregations = tuple(
        StructuredAggregation(
            name=item.name,
            operation=StructuredAggregationOperation(item.operation),
            field=None if item.field is None else _schema_field(schema, item.field).name,
        )
        for item in request.aggregations
    )
    total_rows = sum(item.row_count for item in datasets)
    max_records = min(config.max_structured_rows_scanned, total_rows + 1)
    count = len(datasets)
    plan = RetrievalPlanV2(
        query="",
        mode=AdvancedRetrievalMode.EXHAUSTIVE,
        scope=RetrievalScopeV2(**request.scope.model_dump()),
        position=PositionalScopeV2(),
        representations=(EvidenceRepresentation.CANONICAL_TEXT,),
        budgets=RetrievalBudgetsV2(
            recall_limit=count,
            expansion_limit=0,
            fusion_limit=count,
            rerank_limit=count,
            result_limit=count,
            max_serialized_bytes=min(config.max_structured_response_bytes, 10_000_000),
            max_content_characters=min(config.max_structured_response_bytes, 2_000_000),
        ),
        expansion_policy=ExpansionPolicy.NONE,
        deduplication_policy=DeduplicationPolicy.AUTHORITATIVE_IDENTITY,
        ranking_policy=RankingPolicyV2.DETERMINISTIC_STORAGE_ORDER,
    )
    return StructuredQueryV1(
        retrieval_plan=plan,
        fields=fields,
        filters=tuple(filters),
        group_by=group_by,
        aggregations=aggregations,
        order_by=order_by,
        distinct_fields=distinct,
        offset=0,
        limit=max_records,
        budgets=StructuredBudgets(
            max_records=max_records,
            max_fields=config.max_structured_fields,
            max_groups=config.max_structured_groups,
            max_aggregation_rows=config.max_structured_rows_scanned,
            max_evidence_references=config.max_structured_evidence,
            max_output_bytes=config.max_structured_response_bytes,
            max_output_tokens=max(64, config.max_structured_response_bytes // 4),
            max_distinct_values=config.max_structured_rows_scanned,
        ),
    )


def _selected(
    catalog: StructuredDatasetCatalog, dataset_ids: tuple[UUID, ...]
) -> tuple[StructuredDatasetDescriptor, ...]:
    by_id = {item.dataset_id: item for item in catalog.datasets}
    if not dataset_ids or any(item not in by_id for item in dataset_ids):
        raise ContractValidationError(
            "one or more datasets are unavailable in the authorized scope"
        )
    selected = tuple(by_id[item] for item in dataset_ids)
    if any(item.readiness is not StructuredDatasetReadiness.READY for item in selected):
        raise ContractValidationError("one or more structured generations are unavailable")
    return selected


def _field(dataset: StructuredDatasetDescriptor, name: str) -> StructuredField:
    schema = {item.field.name.casefold(): item.field for item in dataset.fields}
    return _schema_field(schema, name)


def _schema_field(schema: dict[str, StructuredField], name: str) -> StructuredField:
    value = schema.get(name.casefold())
    if value is None:
        raise ContractValidationError("structured query references an unknown field")
    return value


def _dataset_item(item: StructuredDatasetDescriptor) -> dict[str, Any]:
    return {
        "dataset_id": str(item.dataset_id),
        "generation_id": str(item.generation_id),
        "schema_identity": item.schema_identity,
        "document_id": str(item.document_id),
        "version_id": str(item.version_id),
        "source_id": str(item.source_id),
        "block_ordinal": item.block_ordinal,
        "page_number": item.page_number,
        "row_count": item.row_count,
        "readiness": item.readiness.value,
        "fields": [
            {
                **field.field.model_dump(mode="json"),
                "confidence": field.confidence.value,
                "non_missing_count": field.non_missing_count,
            }
            for field in item.fields
        ],
        "supported_operations": [
            "eq",
            "ne",
            "gt",
            "gte",
            "lt",
            "lte",
            "between",
            "in",
            "sort",
            "group",
            "count",
            "avg",
            "sum",
            "min",
            "max",
        ],
        "provenance": {
            "notebook_id": str(item.notebook_id),
            "source_id": str(item.source_id),
            "document_id": str(item.document_id),
            "version_id": str(item.version_id),
            "block_ordinal": item.block_ordinal,
        },
    }


def _record_item(record: StructuredRecord, selected_fields: tuple[str, ...]) -> dict[str, Any]:
    selected = {item.casefold() for item in selected_fields}
    values = [item for item in record.values if not selected or item.field.casefold() in selected]
    return {
        "record_id": str(record.record_id),
        "row_ordinal": record.row_ordinal,
        "values": {
            item.field: {
                "type": item.field_type.value,
                "status": item.status.value,
                "value": _json_value(item.value),
                "unit": item.unit,
                "provenance": [_evidence_item(evidence) for evidence in item.evidence],
            }
            for item in values
        },
        "provenance": [_evidence_item(item) for item in record.evidence],
    }


def _group_item(group) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return {
        "group_id": group.group_id,
        "keys": {
            item.field: {"status": item.status.value, "value": _json_value(item.value)}
            for item in group.keys
        },
        "member_record_ids": [str(item) for item in group.member_record_ids],
        "aggregates": {
            item.name: {
                "operation": item.operation.value,
                "status": item.status.value,
                "value": _json_value(item.value),
                "evidence_truncated": item.evidence_truncated,
                "provenance": [_evidence_item(value) for value in item.evidence],
            }
            for item in group.aggregates
        },
        "provenance": [_evidence_item(item) for item in group.evidence],
        "evidence_truncated": group.evidence_truncated,
    }


def _evidence_item(item) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return {
        "candidate_id": str(item.candidate_id),
        "notebook_id": str(item.notebook_id),
        "source_id": str(item.source_id),
        "document_id": str(item.document_id),
        "version_id": str(item.version_id),
        "chunk_id": item.chunk_id,
        "locator": thaw_metadata(item.locator),
        "retrieval_paths": list(item.retrieval_paths),
        "extraction_method": item.extraction_method,
    }


def _json_value(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Decimal):
        return str(value)
    return value


def _request_dataset_ids(request: StructuredRetrievalRequest) -> tuple[UUID, ...]:
    if request.join is not None:
        return (request.join.left_dataset_id, request.join.right_dataset_id)
    return request.dataset_ids


def _request_fingerprint(
    request: StructuredRetrievalRequest, principal: ServerPrincipalV1 | None = None
) -> str:
    material = request.model_dump(mode="json", exclude={"cursor"})
    material["security_scope_identity"] = (
        "anonymous" if principal is None else str(principal.actor_id)
    )
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
