"""Fail-closed tests for the public structured-retrieval request language."""

from __future__ import annotations

from uuid import uuid4

import pytest
from mnemo_server.schemas.structured_v2 import (
    StructuredFilterRequest,
    StructuredJoinRequest,
    StructuredRetrievalRequest,
    StructuredScopeRequest,
)
from pydantic import ValidationError


def _scope() -> dict[str, object]:
    return {"notebook_id": uuid4(), "version_ids": [uuid4()]}


@pytest.mark.parametrize(
    "payload",
    (
        {"field": "x", "operator": "is_missing", "value": 1},
        {"field": "x", "operator": "is_present", "value": False},
        {"field": "x", "operator": "eq"},
        {"field": "x", "operator": "between", "value": [1]},
        {"field": "x", "operator": "between", "value": "1,2"},
        {"field": "x", "operator": "in", "value": []},
        {"field": "x", "operator": "in", "value": list(range(101))},
    ),
)
def test_structured_filter_value_shapes_are_operator_specific(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        StructuredFilterRequest.model_validate(payload)


def test_structured_scope_and_join_identities_are_unique() -> None:
    identity = uuid4()
    with pytest.raises(ValidationError, match="unique"):
        StructuredScopeRequest(
            notebook_id=uuid4(),
            source_ids=(identity, identity),
            version_ids=(uuid4(),),
        )
    with pytest.raises(ValidationError, match="distinct"):
        StructuredJoinRequest(
            left_dataset_id=identity,
            right_dataset_id=identity,
            left_field="id",
            right_field="id",
        )


@pytest.mark.parametrize(
    "payload",
    (
        {"operation": "describe", "cursor": "cursor"},
        {"operation": "describe", "filters": [{"field": "x", "operator": "eq", "value": 1}]},
        {"operation": "join"},
        {
            "operation": "join",
            "join": {
                "left_dataset_id": uuid4(),
                "right_dataset_id": uuid4(),
                "left_field": "id",
                "right_field": "id",
            },
            "dataset_ids": [uuid4()],
        },
        {
            "operation": "join",
            "join": {
                "left_dataset_id": uuid4(),
                "right_dataset_id": uuid4(),
                "left_field": "id",
                "right_field": "id",
            },
            "group_by": ["x"],
        },
        {"operation": "query"},
        {"operation": "query", "dataset_ids": [uuid4(), uuid4()]},
        {"operation": "union", "dataset_ids": [uuid4()]},
        {
            "operation": "query",
            "dataset_ids": [uuid4()],
            "join": {
                "left_dataset_id": uuid4(),
                "right_dataset_id": uuid4(),
                "left_field": "id",
                "right_field": "id",
            },
        },
        {"operation": "query", "dataset_ids": [uuid4()], "select_fields": ["x", "x"]},
    ),
)
def test_structured_operation_contract_rejects_ambiguous_requests(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        StructuredRetrievalRequest.model_validate({**payload, "scope": _scope()})


def test_structured_describe_query_union_and_join_have_distinct_valid_shapes() -> None:
    left, right = uuid4(), uuid4()
    assert (
        StructuredRetrievalRequest.model_validate(
            {"operation": "describe", "scope": _scope()}
        ).operation.value
        == "describe"
    )
    assert (
        StructuredRetrievalRequest.model_validate(
            {"operation": "query", "scope": _scope(), "dataset_ids": [left]}
        ).operation.value
        == "query"
    )
    assert (
        StructuredRetrievalRequest.model_validate(
            {"operation": "union", "scope": _scope(), "dataset_ids": [left, right]}
        ).operation.value
        == "union"
    )
    assert (
        StructuredRetrievalRequest.model_validate(
            {
                "operation": "join",
                "scope": _scope(),
                "dataset_ids": [left, right],
                "join": {
                    "left_dataset_id": left,
                    "right_dataset_id": right,
                    "left_field": "id",
                    "right_field": "id",
                },
            }
        ).operation.value
        == "join"
    )
