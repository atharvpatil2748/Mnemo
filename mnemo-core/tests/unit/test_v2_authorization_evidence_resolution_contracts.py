"""Governed V2 authorization and evidence-resolution contract schema tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import jsonschema  # type: ignore[import-untyped]
import pytest

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "docs/governance/proposals/phase8_5_full_multilingual_architecture"
DIGEST = "a" * 64
UUID_1 = "11111111-1111-4111-8111-111111111111"
UUID_2 = "22222222-2222-4222-8222-222222222222"
UUID_3 = "33333333-3333-4333-8333-333333333333"
UUID_4 = "44444444-4444-4444-8444-444444444444"
UUID_5 = "55555555-5555-4555-8555-555555555555"
UUID_6 = "66666666-6666-4666-8666-666666666666"
UUID_7 = "77777777-7777-4777-8777-777777777777"


def _schema(name: str) -> dict[str, Any]:
    value = json.loads((PACKAGE / name).read_text(encoding="utf-8"))
    return cast(dict[str, Any], value)


def _binding() -> dict[str, object]:
    return {
        "active_alias_set_identity": DIGEST,
        "active_generation_identities": [UUID_1, UUID_2, UUID_3, UUID_4],
        "profile_fingerprint": DIGEST,
        "vector_space_identity": DIGEST,
        "database_identity": DIGEST,
        "build_run_identity": UUID_5,
        "admission_policy_identity": "mnemo.v2.admission/1",
    }


def _authorization_request() -> dict[str, object]:
    return {
        "record_type": "V2RetrievalAuthorizationRequestV1",
        "contract_version": "mnemo.v2-retrieval-authorization-request/1",
        "request_id": UUID_6,
        "authenticated_principal": {
            "actor_id": UUID_7,
            "authenticated": True,
            "principal_derivation_identity": "central-authorization-server-claims-v1",
        },
        "operation": "retrieve",
        "requested_retrieval_scope": {"notebook_id": UUID_1},
        "requested_positional_scope": {},
        "binding": _binding(),
        "request_fingerprint": DIGEST,
    }


def _authorization_decision() -> dict[str, object]:
    return {
        "record_type": "V2RetrievalAuthorizationDecisionV1",
        "contract_version": "mnemo.v2-retrieval-authorization-decision/1",
        "decision_id": UUID_6,
        "request_fingerprint": DIGEST,
        "allow": True,
        "authorized_operation": "retrieve",
        "authorized_retrieval_scope": {"notebook_id": UUID_1},
        "authorized_positional_scope": {},
        "binding": _binding(),
        "authorization_policy_identity": "central-authorization-v1-plus-v2-retrieval/1",
        "authorization_policy_revision": "1",
        "required_provenance_evidence": ["language-evidence-reference-v3"],
        "issued_at": "2026-09-01T00:00:00Z",
        "decision_fingerprint": DIGEST,
    }


def _runtime_binding() -> dict[str, object]:
    return {
        "active_alias_set_identity": DIGEST,
        "representation_generation_identity": UUID_1,
        "language_text_generation_identity": UUID_2,
        "embedding_generation_identity": UUID_3,
        "vector_generation_identity": UUID_4,
        "profile_identity": "full-multilingual-v2",
        "profile_fingerprint": DIGEST,
        "model_identity": "BAAI/bge-m3@governed-revision",
        "vector_space_identity": DIGEST,
        "database_identity": DIGEST,
        "build_run_identity": UUID_5,
    }


def _resolution() -> dict[str, object]:
    return {
        "record_type": "AuthorizedV2EvidenceResolutionV1",
        "contract_version": "mnemo.v2-authorized-evidence-resolution/1",
        "resolution_identity": UUID_7,
        "request_fingerprint": DIGEST,
        "authorization_decision_fingerprint": DIGEST,
        "source_reference": {
            "schema_version": "mnemo.language-evidence-reference/3",
            "lineage_origin": "native_v3",
            "notebook_id": UUID_1,
            "source_id": UUID_2,
            "document_id": UUID_3,
            "version_id": UUID_4,
            "evidence_kind": "canonical_chunk",
            "evidence_id": "canonical:chunk-1",
            "source_content_hash": DIGEST,
            "chunk_id": "chunk-1",
            "occurrence_id": None,
            "derivation_id": None,
            "source_generation_id": None,
            "parent_evidence_reference_digest": None,
        },
        "canonical_evidence_identity": DIGEST,
        "runtime_binding": _runtime_binding(),
        "lineage": {
            "representation_state": "canonical",
            "language_observation_references": [],
            "script_observation_references": [],
            "representation_observation_reference": UUID_6,
            "transformation": None,
        },
        "semantic_text": "actual governed semantic evidence",
        "semantic_text_content_hash": DIGEST,
        "title_metadata": None,
        "provenance_digest": DIGEST,
        "resolution_fingerprint": DIGEST,
    }


@pytest.mark.parametrize(
    "name",
    [
        "V2_RETRIEVAL_AUTHORIZATION_CONTRACT.schema.json",
        "V2_AUTHORIZED_EVIDENCE_RESOLUTION_CONTRACT.schema.json",
        "V2_CANDIDATE_RUNTIME_SECURITY_BINDING.schema.json",
        "FAILURE_TAXONOMY.proposed.json",
    ],
)
def test_contract_schemas_are_draft_2020_12_valid(name: str) -> None:
    jsonschema.Draft202012Validator.check_schema(_schema(name))


def test_authorization_request_and_bounded_allow_decision_validate() -> None:
    schema = _schema("V2_RETRIEVAL_AUTHORIZATION_CONTRACT.schema.json")
    jsonschema.Draft202012Validator(schema).validate(_authorization_request())
    jsonschema.Draft202012Validator(schema).validate(_authorization_decision())


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["authenticated_principal"].pop("actor_id"),
        lambda value: value["authenticated_principal"].update({"authenticated": False}),
        lambda value: value["binding"].update({"active_generation_identities": [UUID_1]}),
        lambda value: value.update({"request_fingerprint": "not-a-digest"}),
    ],
)
def test_authorization_request_rejects_missing_or_unbounded_security_context(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    value = _authorization_request()
    mutation(value)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(
            _schema("V2_RETRIEVAL_AUTHORIZATION_CONTRACT.schema.json")
        ).validate(value)


def test_denied_decision_requires_explicit_failure_code() -> None:
    value = _authorization_decision()
    value.update({"allow": False})
    for name in (
        "authorized_operation",
        "authorized_retrieval_scope",
        "authorized_positional_scope",
        "binding",
        "required_provenance_evidence",
    ):
        value.pop(name)
    value["denial_code"] = "unauthorized_operation"
    jsonschema.Draft202012Validator(
        _schema("V2_RETRIEVAL_AUTHORIZATION_CONTRACT.schema.json")
    ).validate(value)
    value.pop("denial_code")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(
            _schema("V2_RETRIEVAL_AUTHORIZATION_CONTRACT.schema.json")
        ).validate(value)


def test_evidence_resolution_requires_authorization_runtime_and_semantic_evidence() -> None:
    schema = _schema("V2_AUTHORIZED_EVIDENCE_RESOLUTION_CONTRACT.schema.json")
    validator = jsonschema.Draft202012Validator(schema)
    validator.validate(_resolution())


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.pop("authorization_decision_fingerprint"),
        lambda value: value["source_reference"].pop("document_id"),
        lambda value: value["runtime_binding"].pop("embedding_generation_identity"),
        lambda value: value.update({"semantic_text": "   "}),
        lambda value: value.update({"semantic_text": "title: manuscript.pdf"}),
        lambda value: value["lineage"].update({"representation_state": "derived"}),
    ],
)
def test_evidence_resolution_rejects_missing_security_provenance_or_semantic_text(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    value = _resolution()
    mutation(value)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(
            _schema("V2_AUTHORIZED_EVIDENCE_RESOLUTION_CONTRACT.schema.json")
        ).validate(value)


def test_derived_evidence_requires_typed_transformation_lineage() -> None:
    value = _resolution()
    value["lineage"] = {
        "representation_state": "derived",
        "language_observation_references": [],
        "script_observation_references": [],
        "representation_observation_reference": UUID_6,
        "transformation": {
            "profile_identity": "governed-transform/1",
            "version": "1",
            "digest": DIGEST,
            "source_representation": "legacy_font_encoded_text",
            "target_representation": "unicode_semantic_text",
            "derivation_identity": UUID_7,
            "source_reference_digest": DIGEST,
            "source_generation_ids": [UUID_1],
        },
    }
    jsonschema.Draft202012Validator(
        _schema("V2_AUTHORIZED_EVIDENCE_RESOLUTION_CONTRACT.schema.json")
    ).validate(value)
