"""Fail-closed identity and lineage tests for multilingual evidence models."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4, uuid5

import pytest
from mnemo.models._shared import FrozenMetadata
from mnemo.models.advanced_retrieval import (
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
)
from mnemo.models.multilingual import (
    AnswerLanguageMode,
    AnswerLanguagePolicy,
    EvidenceLineageOriginV3,
    LanguageCapabilityState,
    LanguageCode,
    LanguageConfidence,
    LanguageDerivation,
    LanguageDerivationKind,
    LanguageDetectionSource,
    LanguageEvidenceKindV2,
    LanguageEvidenceKindV3,
    LanguageEvidenceReferenceV2,
    LanguageEvidenceReferenceV3,
    LanguageHypothesisV2,
    LanguageObservation,
    LanguageObservationScope,
    LanguageObservationV2,
    LanguageProviderProfile,
    LanguageRegion,
    LanguageTransformationRequest,
    LanguageTransformationRequestV2,
    MultilingualCandidate,
    MultilingualEmbedding,
    MultilingualEmbeddingInputV2,
    MultilingualEmbeddingProfile,
    MultilingualFinalQARequest,
    MultilingualPathSelection,
    MultilingualProviderReadinessV2,
    MultilingualQueryEmbeddingV2,
    MultilingualRetrievalPath,
    MultilingualRetrievalPlan,
    MultilingualRetrievalResult,
    ObservationAuthorityClass,
    ScriptCode,
    ScriptHypothesisV1,
    ScriptObservationV1,
    language_observation_id,
    language_observation_payload,
    language_observation_v2_id,
    language_provider_profile_payload,
    multilingual_vector_hash,
    multilingual_vector_space_identity,
    script_observation_v1_id,
)
from mnemo.models.multimodal import (
    EvidenceAuthorityV2,
    EvidenceCandidateV2,
    EvidenceKindV2,
    FinalQARequestV2,
    evidence_candidate_v2_id,
)
from mnemo.models.processing import (
    ProcessingConsent,
    ProcessingPolicyDecision,
    ProcessingTrustClass,
)


def _v2(**overrides: object) -> LanguageEvidenceReferenceV2:
    values: dict[str, object] = {
        "notebook_id": uuid4(),
        "source_id": uuid4(),
        "document_id": uuid4(),
        "version_id": uuid4(),
        "kind": LanguageEvidenceKindV2.CANONICAL_CHUNK,
        "evidence_id": "chunk-1",
        "source_content_hash": "a" * 64,
        "chunk_id": "b" * 64,
    }
    values.update(overrides)
    return LanguageEvidenceReferenceV2(**values)  # type: ignore[arg-type]


def _v3(**overrides: object) -> LanguageEvidenceReferenceV3:
    values: dict[str, object] = {
        "notebook_id": uuid4(),
        "source_id": uuid4(),
        "document_id": uuid4(),
        "version_id": uuid4(),
        "kind": LanguageEvidenceKindV3.CANONICAL_CHUNK,
        "evidence_id": "chunk-1",
        "source_content_hash": "a" * 64,
        "chunk_id": "b" * 64,
    }
    values.update(overrides)
    return LanguageEvidenceReferenceV3(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ("", "e", "english!", "e1"))
def test_language_code_rejects_noncanonical_values(value: str) -> None:
    with pytest.raises(ValueError):
        LanguageCode(value)
    assert str(LanguageCode("en")) == "en"
    assert str(LanguageCode("EN-us")) == "en-US"


@pytest.mark.parametrize("value", ("", "Latin", "L4tn"))
def test_script_code_rejects_noncanonical_values(value: str) -> None:
    with pytest.raises(ValueError):
        ScriptCode(value)
    assert str(ScriptCode("Latn")) == "Latn"
    assert str(ScriptCode("LATN")) == "Latn"


def test_v2_reference_enforces_each_evidence_kind_lineage() -> None:
    canonical = _v2()
    assert canonical.identity_digest == replace(canonical).identity_digest
    with pytest.raises(ValueError, match="requires chunk_id"):
        _v2(chunk_id=None)
    for field in ("occurrence_id", "derivation_id", "source_generation_id"):
        with pytest.raises(ValueError, match="cannot claim derived provenance"):
            _v2(**{field: uuid4()})

    for kind in (LanguageEvidenceKindV2.OCR_REGION, LanguageEvidenceKindV2.VISION_DERIVATION):
        with pytest.raises(ValueError, match="occurrence and derivation"):
            _v2(kind=kind, chunk_id=None)
        with pytest.raises(ValueError, match="source generation"):
            _v2(kind=kind, chunk_id=None, occurrence_id=uuid4(), derivation_id=uuid4())
        with pytest.raises(ValueError, match="cannot claim a canonical chunk"):
            _v2(
                kind=kind,
                occurrence_id=uuid4(),
                derivation_id=uuid4(),
                source_generation_id=uuid4(),
            )
        value = _v2(
            kind=kind,
            chunk_id=None,
            occurrence_id=uuid4(),
            derivation_id=uuid4(),
            source_generation_id=uuid4(),
        )
        assert value.identity_payload()["kind"] == kind.value

    with pytest.raises(ValueError, match="requires derivation and generation"):
        _v2(kind=LanguageEvidenceKindV2.LANGUAGE_DERIVATION, chunk_id=None)
    with pytest.raises(ValueError, match="cannot claim a canonical chunk"):
        _v2(
            kind=LanguageEvidenceKindV2.LANGUAGE_DERIVATION,
            derivation_id=uuid4(),
            source_generation_id=uuid4(),
        )


def test_v3_reference_enforces_native_legacy_and_asset_lineage() -> None:
    with pytest.raises(ValueError, match="requires chunk_id"):
        _v3(chunk_id=None)
    for field in (
        "occurrence_id",
        "derivation_id",
        "source_generation_id",
        "parent_evidence_reference_digest",
    ):
        value: object = "c" * 64 if field == "parent_evidence_reference_digest" else uuid4()
        with pytest.raises(ValueError, match="cannot claim derived lineage"):
            _v3(**{field: value})

    for kind in (
        LanguageEvidenceKindV3.OCR_OCCURRENCE,
        LanguageEvidenceKindV3.OCR_REGION,
        LanguageEvidenceKindV3.VISION_DERIVATION,
    ):
        with pytest.raises(ValueError, match="requires occurrence, derivation, and generation"):
            _v3(kind=kind, chunk_id=None)
        with pytest.raises(ValueError, match="cannot claim a canonical chunk"):
            _v3(
                kind=kind,
                occurrence_id=uuid4(),
                derivation_id=uuid4(),
                source_generation_id=uuid4(),
            )
        with pytest.raises(ValueError, match="cannot claim a parent reference"):
            _v3(
                kind=kind,
                chunk_id=None,
                occurrence_id=uuid4(),
                derivation_id=uuid4(),
                source_generation_id=uuid4(),
                parent_evidence_reference_digest="c" * 64,
            )

    for kind in (
        LanguageEvidenceKindV3.LANGUAGE_DERIVATION,
        LanguageEvidenceKindV3.REPRESENTATION_DERIVATION,
    ):
        with pytest.raises(ValueError, match="requires derivation and generation"):
            _v3(kind=kind, chunk_id=None)
        with pytest.raises(ValueError, match="requires its parent"):
            _v3(
                kind=kind,
                chunk_id=None,
                derivation_id=uuid4(),
                source_generation_id=uuid4(),
            )
        derived = _v3(
            kind=kind,
            chunk_id=None,
            derivation_id=uuid4(),
            source_generation_id=uuid4(),
            parent_evidence_reference_digest="c" * 64,
        )
        assert derived.parent_evidence_reference_digest == "c" * 64

    legacy = _v2(
        kind=LanguageEvidenceKindV2.LANGUAGE_DERIVATION,
        chunk_id=None,
        derivation_id=uuid4(),
        source_generation_id=uuid4(),
    )
    upgraded = LanguageEvidenceReferenceV3.from_v2(legacy)
    assert upgraded.lineage_origin is EvidenceLineageOriginV3.LEGACY_V2_UPGRADE
    assert upgraded.parent_evidence_reference_digest is None
    with pytest.raises(ValueError, match="no V2 upgrade form"):
        _v3(
            kind=LanguageEvidenceKindV3.REPRESENTATION_DERIVATION,
            lineage_origin=EvidenceLineageOriginV3.LEGACY_V2_UPGRADE,
            chunk_id=None,
            derivation_id=uuid4(),
            source_generation_id=uuid4(),
            parent_evidence_reference_digest="c" * 64,
        )


def _provider_profile(**overrides: object) -> LanguageProviderProfile:
    values: dict[str, object] = {
        "provider": "test-provider",
        "model": "test-model",
        "revision": "test-rev",
        "profile": "test-prof",
        "configuration_digest": "a" * 64,
        "trust_class": ProcessingTrustClass.LOCAL,
        "supported_languages": (LanguageCode("en"), LanguageCode("fr")),
        "supported_scripts": (ScriptCode("Latn"),),
        "supported_directions": ("en->fr",),
        "state": LanguageCapabilityState.SUPPORTED,
    }
    values.update(overrides)
    return LanguageProviderProfile(**values)  # type: ignore[arg-type]


def _embedding_profile(**overrides: object) -> MultilingualEmbeddingProfile:
    values: dict[str, object] = {
        "provider": "test-provider",
        "model": "test-model",
        "revision": "test-rev",
        "profile": "test-prof",
        "generation_id": uuid4(),
        "dimension": 4,
        "normalized": True,
        "distance_metric": "cosine",
        "preprocessing_digest": "b" * 64,
        "languages": (LanguageCode("en"), LanguageCode("fr")),
        "scripts": (ScriptCode("Latn"),),
        "capability_state": LanguageCapabilityState.SUPPORTED,
    }
    values.update(overrides)
    return MultilingualEmbeddingProfile(**values)  # type: ignore[arg-type]


def _consent() -> ProcessingConsent:
    return ProcessingConsent(
        decision=ProcessingPolicyDecision.ALLOWED,
        policy_version="1.0",
        decided_at=datetime.now(UTC),
        reason_code="test-consent",
    )


def test_v3_reference_rejects_canonical_chunk_for_derived_kinds() -> None:
    with pytest.raises(ValueError, match="derived V3 evidence cannot claim a canonical chunk"):
        _v3(
            kind=LanguageEvidenceKindV3.LANGUAGE_DERIVATION,
            chunk_id="b" * 64,
            derivation_id=uuid4(),
            source_generation_id=uuid4(),
            parent_evidence_reference_digest="c" * 64,
        )


def test_language_observation_invariants_and_payload() -> None:
    notebook_id = uuid4()
    scope = LanguageObservationScope.DOCUMENT
    target_id = "target-1"
    detector = "lang-det"
    revision = "v1"
    config = "a" * 64
    input_hash = "b" * 64
    expected_id = language_observation_id(
        notebook_id=notebook_id,
        target_scope=scope,
        target_id=target_id,
        detector=detector,
        detector_revision=revision,
        configuration_digest=config,
        input_hash=input_hash,
    )
    with pytest.raises(ValueError, match="observation_id does not match detection provenance"):
        LanguageObservation(
            observation_id=uuid4(),
            actor_id=uuid4(),
            notebook_id=notebook_id,
            document_id=None,
            version_id=None,
            target_scope=scope,
            target_id=target_id,
            language=LanguageCode("en"),
            script=ScriptCode("Latn"),
            confidence=LanguageConfidence(value=0.95, calibrated=True),
            detection_source=LanguageDetectionSource.LIGHTWEIGHT_DETECTOR,
            detector=detector,
            detector_revision=revision,
            configuration_digest=config,
            input_hash=input_hash,
            mixed_language=False,
            mixed_script=False,
            region=None,
            created_at=datetime.now(UTC),
        )
    with pytest.raises(ValueError, match="document_id and version_id must be provided together"):
        LanguageObservation(
            observation_id=expected_id,
            actor_id=uuid4(),
            notebook_id=notebook_id,
            document_id=uuid4(),
            version_id=None,
            target_scope=scope,
            target_id=target_id,
            language=LanguageCode("en"),
            script=ScriptCode("Latn"),
            confidence=LanguageConfidence(value=0.95, calibrated=True),
            detection_source=LanguageDetectionSource.LIGHTWEIGHT_DETECTOR,
            detector=detector,
            detector_revision=revision,
            configuration_digest=config,
            input_hash=input_hash,
            mixed_language=False,
            mixed_script=False,
            region=None,
            created_at=datetime.now(UTC),
        )
    doc_id = uuid4()
    ver_id = uuid4()
    obs = LanguageObservation(
        observation_id=expected_id,
        actor_id=uuid4(),
        notebook_id=notebook_id,
        document_id=doc_id,
        version_id=ver_id,
        target_scope=scope,
        target_id=target_id,
        language=LanguageCode("en"),
        script=ScriptCode("Latn"),
        confidence=LanguageConfidence(value=0.95, calibrated=True),
        detection_source=LanguageDetectionSource.LIGHTWEIGHT_DETECTOR,
        detector=detector,
        detector_revision=revision,
        configuration_digest=config,
        input_hash=input_hash,
        mixed_language=False,
        mixed_script=False,
        region=LanguageRegion(order=1),
        created_at=datetime.now(UTC),
    )
    payload = language_observation_payload(obs)
    assert payload["observation_id"] == str(expected_id)
    assert payload["document_id"] == str(doc_id)
    assert payload["region"] == {"order": 1, "locator": {}}


def test_language_observation_v2_invariants() -> None:
    notebook_id = uuid4()
    scope = LanguageObservationScope.DOCUMENT
    target_id = "target-1"
    detector = "lang-det-v2"
    revision = "v2"
    config = "a" * 64
    input_hash = "b" * 64
    hyp1 = LanguageHypothesisV2(
        language=LanguageCode("en"),
        confidence=LanguageConfidence(value=0.9, calibrated=True),
        authority_class=ObservationAuthorityClass.GOVERNED_DETECTOR,
        evidence_digest="c" * 64,
    )
    base_kwargs: dict[str, object] = {
        "observation_id": uuid4(),
        "actor_id": uuid4(),
        "notebook_id": notebook_id,
        "target_scope": scope,
        "target_id": target_id,
        "hypotheses": (hyp1,),
        "detector": detector,
        "detector_revision": revision,
        "configuration_digest": config,
        "input_hash": input_hash,
        "mixed_language": False,
        "source_reference": None,
        "created_at": datetime.now(UTC),
    }
    with pytest.raises(ValueError, match="requires at least one hypothesis"):
        LanguageObservationV2(**(base_kwargs | {"hypotheses": ()}))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unique language codes"):
        LanguageObservationV2(**(base_kwargs | {"hypotheses": (hyp1, hyp1)}))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="mixed language requires multiple hypotheses"):
        LanguageObservationV2(
            **(base_kwargs | {"mixed_language": True, "hypotheses": (hyp1,)})  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="identity mismatch"):
        LanguageObservationV2(**base_kwargs)  # type: ignore[arg-type]

    src_ref = _v3(notebook_id=uuid4(), source_content_hash=input_hash)
    expected_with_ref = language_observation_v2_id(
        notebook_id=notebook_id,
        target_scope=scope,
        target_id=target_id,
        detector=detector,
        detector_revision=revision,
        configuration_digest=config,
        input_hash=input_hash,
        source_reference_digest=src_ref.identity_digest,
    )
    with pytest.raises(ValueError, match="conflicts with source evidence"):
        LanguageObservationV2(
            **(base_kwargs | {"observation_id": expected_with_ref, "source_reference": src_ref})  # type: ignore[arg-type]
        )


def test_script_observation_v1_invariants() -> None:
    notebook_id = uuid4()
    scope = LanguageObservationScope.DOCUMENT
    target_id = "target-1"
    detector = "script-det-v1"
    revision = "v1"
    config = "a" * 64
    input_hash = "b" * 64
    hyp1 = ScriptHypothesisV1(
        script=ScriptCode("Latn"),
        confidence=LanguageConfidence(value=0.9, calibrated=True),
        authority_class=ObservationAuthorityClass.GOVERNED_DETECTOR,
        evidence_digest="c" * 64,
    )
    base_kwargs: dict[str, object] = {
        "observation_id": uuid4(),
        "actor_id": uuid4(),
        "notebook_id": notebook_id,
        "target_scope": scope,
        "target_id": target_id,
        "hypotheses": (hyp1,),
        "detector": detector,
        "detector_revision": revision,
        "configuration_digest": config,
        "input_hash": input_hash,
        "mixed_script": False,
        "source_reference": None,
        "created_at": datetime.now(UTC),
    }
    with pytest.raises(ValueError, match="requires at least one hypothesis"):
        ScriptObservationV1(**(base_kwargs | {"hypotheses": ()}))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unique script codes"):
        ScriptObservationV1(**(base_kwargs | {"hypotheses": (hyp1, hyp1)}))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="mixed script requires multiple hypotheses"):
        ScriptObservationV1(
            **(base_kwargs | {"mixed_script": True, "hypotheses": (hyp1,)})  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="identity mismatch"):
        ScriptObservationV1(**base_kwargs)  # type: ignore[arg-type]

    src_ref = _v3(notebook_id=uuid4(), source_content_hash=input_hash)
    expected_with_ref = script_observation_v1_id(
        notebook_id=notebook_id,
        target_scope=scope,
        target_id=target_id,
        detector=detector,
        detector_revision=revision,
        configuration_digest=config,
        input_hash=input_hash,
        source_reference_digest=src_ref.identity_digest,
    )
    with pytest.raises(ValueError, match="conflicts with source evidence"):
        ScriptObservationV1(
            **(base_kwargs | {"observation_id": expected_with_ref, "source_reference": src_ref})  # type: ignore[arg-type]
        )


def test_language_transformation_and_derivation_invariants() -> None:
    profile = _provider_profile()
    payload = language_provider_profile_payload(profile)
    assert payload["provider"] == "test-provider"

    consent = _consent()
    with pytest.raises(ValueError, match="distinct source and target languages"):
        LanguageTransformationRequest(
            actor_id=uuid4(),
            notebook_id=uuid4(),
            document_id=uuid4(),
            version_id=uuid4(),
            occurrence_id=uuid4(),
            source_evidence_id="evidence-1",
            source_text="hello",
            source_language=LanguageCode("en"),
            target_language=LanguageCode("en"),
            kind=LanguageDerivationKind.TRANSLATION,
            provider_profile=profile,
            preprocessing_digest="a" * 64,
            generation_id=uuid4(),
            consent=consent,
        )

    source_ref = _v2(source_content_hash=hashlib.sha256(b"hello").hexdigest())
    with pytest.raises(ValueError, match="source text does not match source reference hash"):
        LanguageTransformationRequestV2(
            actor_id=uuid4(),
            source=source_ref,
            source_text="different text",
            source_language=LanguageCode("en"),
            target_language=LanguageCode("fr"),
            kind=LanguageDerivationKind.TRANSLATION,
            provider_profile=profile,
            preprocessing_digest="a" * 64,
            generation_id=uuid4(),
            consent=consent,
        )
    with pytest.raises(ValueError, match="distinct source and target languages"):
        LanguageTransformationRequestV2(
            actor_id=uuid4(),
            source=source_ref,
            source_text="hello",
            source_language=LanguageCode("en"),
            target_language=LanguageCode("en"),
            kind=LanguageDerivationKind.TRANSLATION,
            provider_profile=profile,
            preprocessing_digest="a" * 64,
            generation_id=uuid4(),
            consent=consent,
        )
    req_v2 = LanguageTransformationRequestV2(
        actor_id=uuid4(),
        source=source_ref,
        source_text="hello",
        source_language=LanguageCode("en"),
        target_language=LanguageCode("fr"),
        kind=LanguageDerivationKind.TRANSLATION,
        provider_profile=profile,
        preprocessing_digest="a" * 64,
        generation_id=uuid4(),
        consent=consent,
    )
    assert req_v2.source_hash == source_ref.source_content_hash

    cache_key = "a" * 64
    derivation_ns = UUID("37d10a60-b077-509b-aa64-5aa696a38f04")
    correct_derivation_id = uuid5(derivation_ns, cache_key)
    out_text = "bonjour"
    out_hash = hashlib.sha256(out_text.encode("utf-8")).hexdigest()
    with pytest.raises(ValueError, match="derivation_id does not match cache identity"):
        LanguageDerivation(
            derivation_id=uuid4(),
            cache_key=cache_key,
            actor_id=uuid4(),
            notebook_id=source_ref.notebook_id,
            document_id=source_ref.document_id,
            version_id=source_ref.version_id,
            source_evidence_id=source_ref.evidence_id,
            source_hash=source_ref.source_content_hash,
            source_language=LanguageCode("en"),
            target_language=LanguageCode("fr"),
            kind=LanguageDerivationKind.TRANSLATION,
            output_text=out_text,
            output_hash=out_hash,
            provider_profile=profile,
            preprocessing_digest="a" * 64,
            generation_id=uuid4(),
            created_at=datetime.now(UTC),
            source_reference=source_ref,
        )
    with pytest.raises(ValueError, match="conflicts with provenance"):
        LanguageDerivation(
            derivation_id=correct_derivation_id,
            cache_key=cache_key,
            actor_id=uuid4(),
            notebook_id=uuid4(),
            document_id=source_ref.document_id,
            version_id=source_ref.version_id,
            source_evidence_id=source_ref.evidence_id,
            source_hash=source_ref.source_content_hash,
            source_language=LanguageCode("en"),
            target_language=LanguageCode("fr"),
            kind=LanguageDerivationKind.TRANSLATION,
            output_text=out_text,
            output_hash=out_hash,
            provider_profile=profile,
            preprocessing_digest="a" * 64,
            generation_id=uuid4(),
            created_at=datetime.now(UTC),
            source_reference=source_ref,
        )


def test_multilingual_embedding_and_retrieval_models_invariants() -> None:
    with pytest.raises(TypeError, match="normalized must be a boolean"):
        multilingual_vector_space_identity(
            provider="p",
            model="m",
            revision="r",
            dimension=4,
            normalized="true",  # type: ignore[arg-type]
            distance_metric="cosine",
            preprocessing_digest="a" * 64,
        )

    ref = _v2(source_content_hash=hashlib.sha256(b"doc text").hexdigest())
    with pytest.raises(ValueError, match="embedding input text does not match source content hash"):
        MultilingualEmbeddingInputV2(
            source=ref,
            text="mismatched doc text",
            language=LanguageCode("en"),
        )

    emb_profile = _embedding_profile(dimension=4)
    vec = (0.5, 0.5, 0.5, 0.5)
    vec_hash = multilingual_vector_hash(vec)
    with pytest.raises(ValueError, match="dimension mismatch"):
        MultilingualQueryEmbeddingV2(
            query_hash="a" * 64,
            language=LanguageCode("en"),
            profile=emb_profile,
            vector=(0.5, 0.5),
            vector_hash="b" * 64,
        )
    with pytest.raises(ValueError, match="query vector hash does not match vector"):
        MultilingualQueryEmbeddingV2(
            query_hash="a" * 64,
            language=LanguageCode("en"),
            profile=emb_profile,
            vector=vec,
            vector_hash="0" * 64,
        )

    with pytest.raises(ValueError, match="initialized provider requires loadability"):
        MultilingualProviderReadinessV2(
            available_locally=True,
            loadable=False,
            initialized=True,
            exact_identity=True,
        )
    with pytest.raises(ValueError, match="initialized provider requires exact frozen identity"):
        MultilingualProviderReadinessV2(
            available_locally=True,
            loadable=True,
            initialized=True,
            exact_identity=False,
        )

    emb_ns = UUID("b79808fe-b486-57b7-a57e-8e3959fac79b")
    expected_emb_id = uuid5(
        emb_ns,
        f"{ref.notebook_id}:{ref.evidence_id}:{ref.source_content_hash}:en:{emb_profile.vector_space}",
    )
    with pytest.raises(ValueError, match="vector_hash does not match vector"):
        MultilingualEmbedding(
            embedding_id=expected_emb_id,
            notebook_id=ref.notebook_id,
            source_evidence_id=ref.evidence_id,
            source_hash=ref.source_content_hash,
            language=LanguageCode("en"),
            profile=emb_profile,
            vector=vec,
            vector_hash="0" * 64,
            created_at=datetime.now(UTC),
            source_reference=ref,
        )
    with pytest.raises(ValueError, match="embedding_id does not match vector provenance"):
        MultilingualEmbedding(
            embedding_id=uuid4(),
            notebook_id=ref.notebook_id,
            source_evidence_id=ref.evidence_id,
            source_hash=ref.source_content_hash,
            language=LanguageCode("en"),
            profile=emb_profile,
            vector=vec,
            vector_hash=vec_hash,
            created_at=datetime.now(UTC),
            source_reference=ref,
        )
    ref_other_nb = replace(ref, notebook_id=uuid4())
    with pytest.raises(ValueError, match="conflicts with vector provenance"):
        MultilingualEmbedding(
            embedding_id=expected_emb_id,
            notebook_id=ref.notebook_id,
            source_evidence_id=ref.evidence_id,
            source_hash=ref.source_content_hash,
            language=LanguageCode("en"),
            profile=emb_profile,
            vector=vec,
            vector_hash=vec_hash,
            created_at=datetime.now(UTC),
            source_reference=ref_other_nb,
        )

    base_plan = RetrievalPlanV2(
        query="test query",
        mode=AdvancedRetrievalMode.RANKED,
        scope=RetrievalScopeV2(notebook_id=ref.notebook_id),
        position=PositionalScopeV2(),
        representations=(EvidenceRepresentation.CANONICAL_TEXT,),
        budgets=RetrievalBudgetsV2(
            recall_limit=10,
            expansion_limit=0,
            fusion_limit=10,
            rerank_limit=5,
            result_limit=5,
            max_serialized_bytes=10_000,
            max_content_characters=5_000,
        ),
        expansion_policy=ExpansionPolicy.NONE,
        deduplication_policy=DeduplicationPolicy.AUTHORITATIVE_IDENTITY,
        ranking_policy=RankingPolicyV2.SOURCE_RANK_FUSION,
    )
    obs = LanguageObservation(
        observation_id=language_observation_id(
            notebook_id=ref.notebook_id,
            target_scope=LanguageObservationScope.QUERY,
            target_id="q1",
            detector="det",
            detector_revision="r1",
            configuration_digest="c" * 64,
            input_hash="d" * 64,
        ),
        actor_id=uuid4(),
        notebook_id=ref.notebook_id,
        document_id=None,
        version_id=None,
        target_scope=LanguageObservationScope.QUERY,
        target_id="q1",
        language=LanguageCode("en"),
        script=ScriptCode("Latn"),
        confidence=LanguageConfidence(value=0.9, calibrated=True),
        detection_source=LanguageDetectionSource.LIGHTWEIGHT_DETECTOR,
        detector="det",
        detector_revision="r1",
        configuration_digest="c" * 64,
        input_hash="d" * 64,
        mixed_language=False,
        mixed_script=False,
        region=None,
        created_at=datetime.now(UTC),
    )
    with pytest.raises(ValueError, match="base retrieval query must match multilingual query"):
        MultilingualRetrievalPlan(
            query="different query",
            query_observation=obs,
            base_plan=base_plan,
            target_languages=(LanguageCode("en"),),
            paths=(),
        )
    with pytest.raises(ValueError, match="target_languages must not be empty"):
        MultilingualRetrievalPlan(
            query="test query",
            query_observation=obs,
            base_plan=base_plan,
            target_languages=(),
            paths=(),
        )
    with pytest.raises(ValueError, match="target_languages must be unique"):
        MultilingualRetrievalPlan(
            query="test query",
            query_observation=obs,
            base_plan=base_plan,
            target_languages=(LanguageCode("en"), LanguageCode("en")),
            paths=(),
        )

    cand = EvidenceCandidateV2(
        candidate_id=evidence_candidate_v2_id(
            kind=EvidenceKindV2.CANONICAL_CHUNK,
            document_id=ref.document_id,
            version_id=ref.version_id,
            authoritative_id="c1",
        ),
        notebook_id=ref.notebook_id,
        source_id=ref.source_id,
        document_id=ref.document_id,
        version_id=ref.version_id,
        kind=EvidenceKindV2.CANONICAL_CHUNK,
        authority=EvidenceAuthorityV2.ORIGINAL,
        authoritative_id="c1",
        chunk_id=ref.chunk_id,
        content="chunk content",
    )
    path_sel = MultilingualPathSelection(
        path=MultilingualRetrievalPath.NATIVE_SPARSE,
        target_language=LanguageCode("en"),
        state=LanguageCapabilityState.SUPPORTED,
        profile="sparse-prof",
        reason="direct match",
    )
    with pytest.raises(ValueError, match="requires retrieval provenance"):
        MultilingualCandidate(
            candidate=cand,
            evidence_language=LanguageCode("en"),
            evidence_script=ScriptCode("Latn"),
            paths=(),
            source_ranks=FrozenMetadata({"rank": 1}),
            fused_score=0.9,
            final_rank=1,
        )
    with pytest.raises(ValueError, match="source ranks must be positive integers"):
        MultilingualCandidate(
            candidate=cand,
            evidence_language=LanguageCode("en"),
            evidence_script=ScriptCode("Latn"),
            paths=(path_sel,),
            source_ranks=FrozenMetadata({"rank": 0}),
            fused_score=0.9,
            final_rank=1,
        )
    valid_cand = MultilingualCandidate(
        candidate=cand,
        evidence_language=LanguageCode("en"),
        evidence_script=ScriptCode("Latn"),
        paths=(path_sel,),
        source_ranks=FrozenMetadata({"rank": 1}),
        fused_score=0.9,
        final_rank=1,
    )

    valid_plan = MultilingualRetrievalPlan(
        query="test query",
        query_observation=obs,
        base_plan=base_plan,
        target_languages=(LanguageCode("en"),),
        paths=(path_sel,),
    )
    invalid_rank_cand = replace(valid_cand, final_rank=2)
    with pytest.raises(ValueError, match="ranks must be contiguous"):
        MultilingualRetrievalResult(
            plan=valid_plan,
            candidates=(invalid_rank_cand,),
            completeness=RetrievalCompleteness.COMPLETE,
            unavailable_paths=(),
            diagnostics=FrozenMetadata(),
        )

    with pytest.raises(ValueError, match="explicit answer language mode requires a language"):
        AnswerLanguagePolicy(
            mode=AnswerLanguageMode.EXPLICIT,
            explicit_language=None,
            fallback_language=None,
            allow_fallback=False,
        )

    policy = AnswerLanguagePolicy(
        mode=AnswerLanguageMode.EXPLICIT,
        explicit_language=LanguageCode("en"),
        fallback_language=None,
        allow_fallback=False,
    )
    with pytest.raises(ValueError, match="evidence_languages must not be empty"):
        MultilingualFinalQARequest(
            request=cast(FinalQARequestV2, object()),
            query_observation=obs,
            evidence_languages=(),
            answer_policy=policy,
        )
