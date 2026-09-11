"""Contract-only coverage for the V2 ownership remediation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import jsonschema  # type: ignore[import-untyped]
import pytest
from mnemo.interfaces import (
    AuthorizedV2EvidenceResolverV1,
    GovernedV2CandidateProjectorV1,
    LanguageEvidenceAuthorizerV3,
    RepresentationEvidenceAuthorizerV3,
    V2AuthorizedEvidenceStoreV1,
    V2RetrievalAuthorizerV1,
)
from mnemo.interfaces.scope import PrincipalContextV1
from mnemo.models.advanced_retrieval import PositionalScopeV2, RetrievalScopeV2
from mnemo.models.multilingual import LanguageEvidenceKindV3, LanguageEvidenceReferenceV3
from mnemo.models.text_representations import (
    RepresentationAuthority,
    TextRepresentationReferenceV1,
    TextRepresentationType,
    text_representation_reference_id,
)
from mnemo.models.v2_evidence_resolution import (
    AuthorizedV2EvidenceResolutionV1,
    V2AuthorizedEvidenceHandleV1,
    V2CandidateRuntimeSecurityBindingV1,
    V2GenerationSetBindingV1,
    V2RepresentationResolutionState,
    V2SemanticEvidenceRecordV1,
)
from mnemo.models.v2_retrieval_authorization import (
    V2ActiveRuntimeBindingV1,
    V2RetrievalAuthorizationDecisionV1,
)

DIGEST = "a" * 64
ROOT = Path(__file__).resolve().parents[3]


def _decision() -> V2RetrievalAuthorizationDecisionV1:
    notebook_id = uuid4()
    return V2RetrievalAuthorizationDecisionV1(
        decision_id=uuid4(),
        principal_actor_id=uuid4(),
        operation="retrieve",
        retrieval_scope=RetrievalScopeV2(notebook_id=notebook_id),
        positional_scope=PositionalScopeV2(),
        runtime_binding=V2ActiveRuntimeBindingV1(
            alias_set_digest=DIGEST,
            generation_ids=tuple(uuid4() for _ in range(4)),
            profile_fingerprint=DIGEST,
            vector_space_identity=DIGEST,
            database_identity=DIGEST,
            build_run_id=uuid4(),
            admission_policy_identity="v2-admission/1",
        ),
        authorization_policy_identity="central-authorization-plus-v2/1",
        authorization_policy_revision="1",
        request_fingerprint=DIGEST,
        issued_at="2026-09-02T00:00:00Z",
        required_provenance_evidence=("language-evidence-reference-v3",),
    )


def _resolution(text: str = "actual semantic evidence") -> AuthorizedV2EvidenceResolutionV1:
    decision = _decision()
    generations = V2GenerationSetBindingV1(
        representation_generation_id=decision.runtime_binding.generation_ids[0],
        language_text_generation_id=decision.runtime_binding.generation_ids[1],
        embedding_generation_id=decision.runtime_binding.generation_ids[2],
        vector_generation_id=decision.runtime_binding.generation_ids[3],
    )
    security = V2CandidateRuntimeSecurityBindingV1(
        authorization_decision=decision,
        generations=generations,
        profile_id="full-multilingual-v2",
        model_identity="BAAI/bge-m3@governed-revision",
    )
    text_hash = hashlib.sha256(text.encode()).hexdigest()
    source = LanguageEvidenceReferenceV3(
        notebook_id=decision.retrieval_scope.notebook_id,
        source_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        kind=LanguageEvidenceKindV3.CANONICAL_CHUNK,
        evidence_id="chunk:1",
        chunk_id="chunk:1",
        source_content_hash=text_hash,
    )
    observation_id = uuid4()
    representation = TextRepresentationReferenceV1(
        reference_id=text_representation_reference_id(
            evidence_reference_digest=source.identity_digest,
            representation_type=TextRepresentationType.UNICODE_SEMANTIC_TEXT,
            authority=RepresentationAuthority.ORIGINAL,
            content_hash=text_hash,
            observation_id=observation_id,
            derivation_id=None,
            source_generation_ids=(),
        ),
        evidence_reference=source,
        representation_type=TextRepresentationType.UNICODE_SEMANTIC_TEXT,
        representation_authority=RepresentationAuthority.ORIGINAL,
        content_hash=text_hash,
        representation_observation_id=observation_id,
        representation_derivation_id=None,
        source_generation_ids=(),
        language_observation_references=(),
        script_observation_references=(),
    )
    handle = V2AuthorizedEvidenceHandleV1(
        source_reference=source,
        representation_reference=representation,
        language_observation_references=(),
        script_observation_references=(),
        semantic_generation_id=generations.language_text_generation_id,
        runtime_security=security,
    )
    record = V2SemanticEvidenceRecordV1(
        handle=handle,
        semantic_text=text,
        semantic_text_content_hash=text_hash,
        representation_state=V2RepresentationResolutionState.CANONICAL,
        representation_observation_reference=observation_id,
        transformation_lineage=None,
        title_metadata="document title",
    )
    return AuthorizedV2EvidenceResolutionV1.create(
        resolution_identity=uuid4(), request_fingerprint=DIGEST, record=record
    )


def test_legacy_authorizer_is_preserved_and_v2_authorizer_is_distinct() -> None:
    assert LanguageEvidenceAuthorizerV3 is RepresentationEvidenceAuthorizerV3
    assert V2RetrievalAuthorizerV1 is not RepresentationEvidenceAuthorizerV3


def test_authorized_resolution_preserves_semantic_security_and_generation_bindings() -> None:
    resolution = _resolution()
    payload = resolution.to_contract_payload()
    assert resolution.semantic_text == "actual semantic evidence"
    assert payload["authorization_decision_fingerprint"] == (
        resolution.runtime_security.authorization_decision_fingerprint
    )
    runtime = payload["runtime_binding"]
    assert isinstance(runtime, dict)
    assert runtime["embedding_generation_identity"] != runtime["vector_generation_identity"]
    assert runtime["database_identity"] == DIGEST
    schema = json.loads(
        (
            ROOT
            / "docs/governance/proposals/phase8_5_full_multilingual_architecture"
            / "V2_AUTHORIZED_EVIDENCE_RESOLUTION_CONTRACT.schema.json"
        ).read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(payload)
    security_schema = json.loads(
        (
            ROOT
            / "docs/governance/proposals/phase8_5_full_multilingual_architecture"
            / "V2_CANDIDATE_RUNTIME_SECURITY_BINDING.schema.json"
        ).read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(security_schema).validate(
        resolution.runtime_security.to_contract_payload()
    )


@pytest.mark.parametrize("text", ["", "   ", "title: manuscript.pdf"])
def test_semantic_resolution_fails_closed_for_missing_or_title_only_text(text: str) -> None:
    with pytest.raises(ValueError):
        _resolution(text)


def test_runtime_security_rejects_generation_substitution() -> None:
    decision = _decision()
    with pytest.raises(PermissionError, match="generation set"):
        V2CandidateRuntimeSecurityBindingV1(
            authorization_decision=decision,
            generations=V2GenerationSetBindingV1(
                representation_generation_id=uuid4(),
                language_text_generation_id=uuid4(),
                embedding_generation_id=uuid4(),
                vector_generation_id=uuid4(),
            ),
            profile_id="full-multilingual-v2",
            model_identity="BAAI/bge-m3@governed-revision",
        )


class _StorePort:
    async def enumerate_authorized_v2_evidence(self, **_: object) -> tuple[object, ...]:
        return ()

    async def resolve_authorized_v2_semantic_evidence(self, **_: object) -> None:
        return None


class _ResolverPort:
    async def resolve_v2_evidence(self, **_: object) -> AuthorizedV2EvidenceResolutionV1:
        return _resolution()


class _ProjectorPort:
    async def project_authorized_v2_evidence(self, **_: object) -> object:
        raise NotImplementedError


def test_storage_resolution_and_projector_ports_are_explicit_and_database_opaque() -> None:
    assert isinstance(_StorePort(), V2AuthorizedEvidenceStoreV1)
    assert isinstance(_ResolverPort(), AuthorizedV2EvidenceResolverV1)
    assert isinstance(_ProjectorPort(), GovernedV2CandidateProjectorV1)
    assert "sqlite" not in V2AuthorizedEvidenceStoreV1.__dict__


def test_v2_authorizer_port_requires_principal_not_actor_id() -> None:
    annotations = V2RetrievalAuthorizerV1.authorize_v2_retrieval.__annotations__
    assert annotations["principal"] == "PrincipalContextV1"
    assert "actor_id" not in annotations
    assert PrincipalContextV1 is not None
