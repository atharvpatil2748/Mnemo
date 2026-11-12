"""Registration compatibility and unregistered scope review; no live storage."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]  # no bundled stubs
from mnemo.cursors import CursorCodecV2, CursorConflictError, CursorInvalidError, CursorSigningKeyV2
from mnemo_server.schemas.scope_contract_review import (
    CoverageReview,
    EvidenceAncestryReview,
    ScopeRequestReview,
    ScopeResponseReview,
    SourceStatusReview,
    evidence_equivalence_key,
)
from mnemo_server.schemas.structured_v2 import StructuredRetrievalRequest
from pydantic import ValidationError

from scripts.snapshot_public_contracts import capture_contracts

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "docs/governance/contracts/phase8_9_1_current_surface.v1.json"
N = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


def request(**updates: Any) -> dict[str, Any]:
    return {"query": " question ", "scope": {"kind": "selected", "notebook_ids": [N]}, **updates}


def test_current_surface_snapshot_without_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("registration inventory must not open SQLite")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    actual = capture_contracts()
    assert actual == json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert len(actual["http"]) >= len(actual["openapi"]["paths"]) > 0
    names = {entry["tool"]["name"] for entry in actual["mcp"]}
    assert len(names) == 15
    assert not names & {"search", "search_structured", "describe_datasets", "search_images"}
    assert "/v2/search" not in actual["openapi"]["paths"]
    assert actual["v1_defaults"]["query"]["retrieval_config"]["top_k"] == 20
    assert actual["v1_defaults"]["search"]["limit"] == 20
    for name in ("query_notebook", "search_all_notebooks"):
        tool = next(entry["tool"] for entry in actual["mcp"] if entry["tool"]["name"] == name)
        assert tool["inputSchema"]["properties"]["top_k"]["default"] == 10


def test_review_defaults_and_roundtrip() -> None:
    value = ScopeRequestReview.model_validate(request())
    assert value.query == "question"
    assert value.representations is None
    assert value.limit == 20
    assert value.mode == "ranked"
    assert ScopeRequestReview.model_validate_json(value.model_dump_json()) == value
    # Selection is syntax, never proof of ownership.
    assert value.scope.kind == "selected"
    assert (
        ScopeRequestReview.model_validate(request(scope={"kind": "all_authorized"})).scope.kind
        == "all_authorized"
    )


@pytest.mark.parametrize(
    "updates",
    [
        {"query": "   "},
        {"query": "x" * 4097},
        {"scope": {"kind": "selected", "notebook_ids": []}},
        {"scope": {"kind": "selected", "notebook_ids": [N, N]}},
        {"scope": {"kind": "selected", "notebook_ids": ["not-a-uuid"]}},
        {"scope": {"kind": "all_authorized", "notebook_ids": [N]}},
        {"scope": {"kind": "unknown"}},
        {"scope": None},
        {"documents": [{"notebook_id": OTHER, "document_id": N, "version_id": N}]},
        {"documents": [{"notebook_id": N, "document_id": N}]},
        {"documents": [{"notebook_id": N, "document_id": N, "version_id": N}] * 2},
        {"representations": []},
        {"representations": ["sql"]},
        {"representations": ["ocr_text", "ocr_text"]},
        {"limit": True},
        {"limit": "20"},
        {"limit": 0},
        {"limit": 201},
        {"mode": "sql"},
        {"cursor": "opaque"},
        {"mode": "traversal", "cursor": ""},
        {"mode": "traversal", "cursor": " "},
        {"mode": "traversal", "cursor": "x" * 8193},
    ],
)
def test_invalid_review_inputs(updates: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ScopeRequestReview.model_validate(request(**updates))


@pytest.mark.parametrize(
    "field",
    ["actor_id", "principal", "store", "generation_id", "policy", "model", "database_path"],
)
def test_authority_fields_rejected_at_both_levels(field: str) -> None:
    for payload in (
        request(**{field: N}),
        request(scope={"kind": "selected", "notebook_ids": [N], field: N}),
    ):
        with pytest.raises(ValidationError):
            ScopeRequestReview.model_validate(payload)


def test_valid_traversal_is_not_cursor_authentication() -> None:
    value = ScopeRequestReview.model_validate(
        request(mode="traversal", cursor="opaque-unverified", representations=["ocr_text"])
    )
    assert value.cursor == "opaque-unverified"
    # No method creates a plan or grants access; signature validation is deferred.
    assert not hasattr(value, "to_plan")
    assert not hasattr(value, "authorize")


def test_review_cursor_shape_does_not_authenticate_or_authorize() -> None:
    now = datetime(2026, 10, 21, tzinfo=UTC)
    codec = CursorCodecV2(CursorSigningKeyV2("fixture-only", b"f" * 32), ttl=timedelta(minutes=2))
    token = codec.encode(
        domain="review.fixture",
        snapshot_identity="a" * 64,
        binding={"principal": "actor-a", "notebook": N, "query": "question"},
        position={"offset": 1},
        limits={"limit": 2},
        now=now,
    )
    assert (
        ScopeRequestReview.model_validate(request(mode="traversal", cursor=token)).cursor == token
    )
    with pytest.raises(CursorInvalidError):
        codec.decode(
            token + "tampered", expected_domain="review.fixture", expected_binding={}, now=now
        )
    with pytest.raises(CursorConflictError):
        codec.decode(
            token,
            expected_domain="review.fixture",
            expected_binding={"principal": "actor-b", "notebook": N, "query": "question"},
            now=now,
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"query": " \t\n "},
        {"scope": {"kind": "selected", "notebook_ids": [N, N]}},
        {"representations": ["ocr_text", "ocr_text"]},
        {"mode": "traversal", "cursor": " \t "},
    ],
)
def test_structural_rejections_match_generated_schema(updates: dict[str, Any]) -> None:
    schema = ScopeRequestReview.model_json_schema()
    Draft202012Validator.check_schema(schema)
    assert list(Draft202012Validator(schema).iter_errors(request(**updates)))
    with pytest.raises(ValidationError):
        ScopeRequestReview.model_validate(request(**updates))


def test_cross_field_scope_rejected_by_runtime_even_when_shape_valid() -> None:
    payload = request(documents=[{"notebook_id": OTHER, "document_id": N, "version_id": N}])
    # Standalone JSON Schema cannot resolve authorized notebook membership or
    # dynamic relationships between selected notebook IDs and document tuples.
    assert not list(
        Draft202012Validator(ScopeRequestReview.model_json_schema()).iter_errors(payload)
    )
    with pytest.raises(ValidationError, match="selected notebooks"):
        ScopeRequestReview.model_validate(payload)


@pytest.mark.parametrize(
    "status", ["not_applicable", "unavailable", "incomplete", "failed", "omitted_by_budget"]
)
def test_unsearched_is_not_zero(status: str) -> None:
    args = {"notebook_id": N, "representation": "ocr_text", "status": status}
    assert SourceStatusReview.model_validate(args).matched is None
    with pytest.raises(ValidationError):
        SourceStatusReview.model_validate({**args, "matched": 0})


def test_source_status_relation_is_server_semantics_not_schema_shape() -> None:
    payload = {
        "notebook_id": N,
        "representation": "ocr_text",
        "status": "unavailable",
        "matched": 0,
    }
    assert not list(
        Draft202012Validator(SourceStatusReview.model_json_schema()).iter_errors(payload)
    )
    with pytest.raises(ValidationError, match="only searched"):
        SourceStatusReview.model_validate(payload)


def test_searched_zero_and_provenance_variants() -> None:
    assert (
        SourceStatusReview.model_validate(
            {"notebook_id": N, "representation": "ocr_text", "status": "searched", "matched": 0}
        ).matched
        == 0
    )
    for identity in (
        {"kind": "canonical", "chunk_id": "chunk"},
        {"kind": "derived", "occurrence_id": N, "asset_id": N, "derivation_id": N},
        {"kind": "structured", "dataset_id": N, "row_ids": ["row-1"]},
    ):
        value = EvidenceAncestryReview.model_validate(
            {
                "notebook_id": N,
                "source_id": N,
                "document_id": N,
                "version_id": N,
                "generation_id": N,
                "generation_alias": "fixture",
                "identity": identity,
                "locator": "page:1",
                "retrieval_path": ["fixture"],
                "citation": "fixture:1",
            }
        )
        assert value.version_id == UUID(N)
        with pytest.raises(ValidationError):
            EvidenceAncestryReview.model_validate(
                {**value.model_dump(), "identity": {"kind": identity["kind"]}}
            )


def test_dataset_row_review_requires_document_ancestry_without_fabrication() -> None:
    payload: dict[str, Any] = {
        "notebook_id": N,
        "source_id": N,
        "document_id": N,
        "version_id": N,
        "generation_id": N,
        "generation_alias": "fixture",
        "identity": {"kind": "structured", "dataset_id": N, "row_ids": ["row-1"]},
        "locator": "table:0:row:1",
        "retrieval_path": ["structured"],
        "citation": "fixture:row:1",
    }
    assert EvidenceAncestryReview.model_validate(payload).identity.kind == "structured"
    for missing in ("source_id", "document_id", "version_id", "generation_id"):
        with pytest.raises(ValidationError):
            EvidenceAncestryReview.model_validate(
                {key: value for key, value in payload.items() if key != missing}
            )


def test_approved_structured_intent_is_exact_typed_ast_only() -> None:
    scope = {"notebook_id": N, "version_ids": [N]}
    valid = {
        "operation": "query",
        "scope": scope,
        "dataset_ids": [N],
        "filters": [{"field": "amount", "operator": "gte", "value": 10}],
    }
    assert StructuredRetrievalRequest.model_validate(valid).operation.value == "query"
    for operation, datasets, join in (
        ("describe", [], None),
        ("union", [N, OTHER], None),
        (
            "join",
            [N, OTHER],
            {
                "left_dataset_id": N,
                "right_dataset_id": OTHER,
                "left_field": "key",
                "right_field": "key",
            },
        ),
    ):
        candidate: dict[str, Any] = {
            "operation": operation,
            "scope": scope,
            "dataset_ids": datasets,
        }
        if join is not None:
            candidate["join"] = join
        assert StructuredRetrievalRequest.model_validate(candidate).operation.value == operation
    exact_field = StructuredRetrievalRequest.model_validate(
        {**valid, "filters": [{"field": " Amount ", "operator": "eq", "value": 10}]}
    )
    assert exact_field.filters[0].field == " Amount "  # Dataset schema resolves exact identity.
    for change in (
        {"operation": "find rows above ten"},
        {"dataset_ids": [N, OTHER]},
        {"operation": "union"},
        {"operation": "join"},
        {"filters": [{"field": "amount", "operator": "between", "value": [10]}]},
        {"actor_id": N},
        {"generation_id": N},
        {"provider_ready": True},
    ):
        with pytest.raises(ValidationError):
            StructuredRetrievalRequest.model_validate({**valid, **change})


@pytest.mark.parametrize(
    "identity",
    [
        {"kind": "canonical", "chunk_id": "chunk-1"},
        {"kind": "derived", "occurrence_id": N, "asset_id": N, "derivation_id": N},
        {"kind": "structured", "dataset_id": N, "row_ids": ["row-1"]},
    ],
)
def test_approved_equivalence_preserves_scope_and_typed_ancestry(
    identity: dict[str, Any],
) -> None:
    payload = {
        "notebook_id": N,
        "source_id": N,
        "document_id": N,
        "version_id": N,
        "generation_id": N,
        "generation_alias": "fixture",
        "identity": identity,
        "locator": "page:1",
        "retrieval_path": ["canonical"],
        "citation": "fixture:1",
    }
    first = EvidenceAncestryReview.model_validate(payload)
    same_evidence_other_path = EvidenceAncestryReview.model_validate(
        {**payload, "retrieval_path": ["ocr"]}
    )
    assert evidence_equivalence_key(first) == evidence_equivalence_key(same_evidence_other_path)
    for field in ("notebook_id", "source_id", "document_id", "version_id", "generation_id"):
        distinct = EvidenceAncestryReview.model_validate({**payload, field: OTHER})
        assert evidence_equivalence_key(first) != evidence_equivalence_key(distinct)
    for change in ({"locator": "page:2"}, {"citation": "fixture:2"}):
        assert evidence_equivalence_key(first) != evidence_equivalence_key(
            EvidenceAncestryReview.model_validate({**payload, **change})
        )


def test_same_text_different_source_never_implies_equivalence() -> None:
    payload = {
        "notebook_id": N,
        "source_id": N,
        "document_id": N,
        "version_id": N,
        "generation_id": N,
        "generation_alias": "fixture",
        "identity": {"kind": "canonical", "chunk_id": "same-text-digest"},
        "locator": "page:1",
        "retrieval_path": ["text"],
        "citation": "fixture:1",
    }
    one = EvidenceAncestryReview.model_validate(payload)
    another = EvidenceAncestryReview.model_validate({**payload, "source_id": OTHER})
    assert evidence_equivalence_key(one) != evidence_equivalence_key(another)


@pytest.mark.parametrize(
    "updates",
    [
        {"mode": "ranked"},
        {"partial": True},
        {"next_cursor": "opaque"},
        {"returned": 2},
    ],
)
def test_false_completeness_rejected(updates: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        CoverageReview.model_validate(
            {
                "mode": "traversal",
                "completeness": "complete",
                "examined": 1,
                "returned": 1,
                "partial": False,
                **updates,
            }
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"completeness": "truncated"},
        {"completeness": "partial", "next_cursor": "opaque", "partial": True},
        {"completeness": "truncated", "next_cursor": "opaque", "mode": "ranked"},
        {"completeness": "partial", "partial": False},
        {"completeness": "empty", "returned": 1},
    ],
)
def test_review_coverage_rejects_inconsistent_outcomes(updates: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        CoverageReview.model_validate(
            {
                "mode": "traversal",
                "completeness": "partial",
                "examined": 1,
                "returned": 0,
                "partial": True,
                **updates,
            }
        )


def test_review_coverage_allows_terminal_zero_and_truncated_continuation() -> None:
    terminal = CoverageReview.model_validate(
        {
            "mode": "traversal",
            "completeness": "empty",
            "examined": 0,
            "returned": 0,
            "partial": False,
        }
    )
    continuing = CoverageReview.model_validate(
        {
            "mode": "traversal",
            "completeness": "truncated",
            "examined": 1,
            "returned": 1,
            "partial": False,
            "next_cursor": "opaque-not-authenticated",
        }
    )
    assert terminal.next_cursor is None
    assert continuing.next_cursor == "opaque-not-authenticated"


def test_review_schema_snapshot() -> None:
    path = ROOT / "docs/governance/proposals/phase8_9_1_scope_review.schema.json"
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert expected == {
        "request": ScopeRequestReview.model_json_schema(),
        "response": ScopeResponseReview.model_json_schema(),
    }


def test_terminal_review_response_and_safe_errors() -> None:
    payload: dict[str, Any] = {
        "evidence": [],
        "sources": [
            {
                "notebook_id": N,
                "representation": "canonical_text",
                "status": "searched",
                "matched": 0,
            }
        ],
        "coverage": {
            "mode": "traversal",
            "completeness": "complete",
            "examined": 0,
            "returned": 0,
            "partial": False,
        },
    }
    response = ScopeResponseReview.model_validate(payload)
    assert response.errors == ()
    assert response.coverage.next_cursor is None
    assert ScopeResponseReview.model_validate_json(response.model_dump_json()) == response
    with pytest.raises(ValidationError):
        ScopeResponseReview.model_validate(
            {
                **payload,
                "errors": [{"category": "unauthorized", "correlation_id": N, "actor_id": OTHER}],
            }
        )


def test_unavailable_source_cannot_be_reported_as_complete_or_nonpartial() -> None:
    payload: dict[str, Any] = {
        "evidence": [],
        "sources": [{"notebook_id": N, "representation": "ocr_text", "status": "unavailable"}],
        "omissions": [
            {
                "notebook_id": N,
                "representation": "ocr_text",
                "status": "unavailable",
                "reason_code": "projection_unavailable",
            }
        ],
        "coverage": {
            "mode": "traversal",
            "completeness": "complete",
            "examined": 0,
            "returned": 0,
            "partial": False,
        },
    }
    with pytest.raises(ValidationError, match="partial coverage"):
        ScopeResponseReview.model_validate(payload)
    payload["coverage"] = {**payload["coverage"], "completeness": "partial", "partial": True}
    assert ScopeResponseReview.model_validate(payload).coverage.partial
    with pytest.raises(ValidationError, match="returned count"):
        ScopeResponseReview.model_validate(
            {**payload, "coverage": {**payload["coverage"], "examined": 1, "returned": 1}}
        )
    with pytest.raises(ValidationError, match="omissions"):
        ScopeResponseReview.model_validate({**payload, "omissions": []})
    with pytest.raises(ValidationError, match="omissions"):
        ScopeResponseReview.model_validate(
            {**payload, "omissions": [*payload["omissions"], *payload["omissions"]]}
        )


def test_approved_readiness_distinguishes_searched_zero_from_no_search() -> None:
    searched_zero = {
        "notebook_id": N,
        "representation": "canonical_text",
        "status": "searched",
        "matched": 0,
    }
    not_applicable = {
        "notebook_id": N,
        "representation": "ocr_text",
        "status": "not_applicable",
    }
    terminal = {
        "mode": "traversal",
        "completeness": "empty",
        "examined": 0,
        "returned": 0,
        "partial": False,
    }
    assert (
        ScopeResponseReview.model_validate(
            {"evidence": [], "sources": [searched_zero, not_applicable], "coverage": terminal}
        ).coverage.completeness.value
        == "empty"
    )
    with pytest.raises(ValidationError, match="actually searched"):
        ScopeResponseReview.model_validate(
            {"evidence": [], "sources": [not_applicable], "coverage": terminal}
        )
    with pytest.raises(ValidationError, match="partial coverage"):
        ScopeResponseReview.model_validate(
            {
                "evidence": [],
                "sources": [{**not_applicable, "status": "failed"}],
                "omissions": [
                    {
                        "notebook_id": N,
                        "representation": "ocr_text",
                        "status": "failed",
                        "reason_code": "source_failed",
                    }
                ],
                "coverage": {**terminal, "partial": True},
            }
        )
