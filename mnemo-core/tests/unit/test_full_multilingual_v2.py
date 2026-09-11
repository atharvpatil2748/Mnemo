from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from mnemo.interfaces.errors import ConflictError
from mnemo.interfaces.scope import PrincipalContextV1
from mnemo.models._shared import FrozenMetadata
from mnemo.models.advanced_retrieval import (
    AdvancedRetrievalCandidate,
    AdvancedRetrievalMode,
    EvidenceRepresentation,
    PositionalScopeV2,
    RankingPolicyV2,
    RetrievalBudgetsV2,
    RetrievalPathEvidenceV2,
    RetrievalPlanV2,
    RetrievalScopeV2,
    advanced_candidate_id,
)
from mnemo.models.assets import IndexGeneration, IndexGenerationState
from mnemo.models.multilingual import (
    EvidenceLineageOriginV3,
    LanguageCapabilityState,
    LanguageCode,
    LanguageEvidenceKindV2,
    LanguageEvidenceKindV3,
    LanguageEvidenceReferenceV2,
    LanguageEvidenceReferenceV3,
    LanguageObservationScope,
    MultilingualEmbeddingProfile,
    MultilingualRerankScoreV2,
    ScriptCode,
    multilingual_vector_hash,
)
from mnemo.models.multilingual_embeddings import (
    MultilingualEmbeddingV3,
    multilingual_embedding_v3_id,
)
from mnemo.models.multilingual_evaluation import (
    CorpusPresenceEvidenceV1,
    EvaluationFailureCodeV2,
    EvaluationFailureRecordV2,
    QueryClassV2,
    QueryGroundingState,
    QueryRecordV2,
)
from mnemo.models.multilingual_generation import MultilingualCoverageManifestV2
from mnemo.models.multilingual_index import (
    MultilingualEvidencePositionV1,
    MultilingualTextProjectionRowV2,
    multilingual_text_projection_row_v2_id,
)
from mnemo.models.multilingual_reranking import (
    AuthorizedRerankerEvidenceV1,
    CandidateProvenanceV1,
    MultilingualRerankCandidateV3,
)
from mnemo.models.text_representations import (
    AuthorizationScopeV1,
    RepresentationAuthority,
    RepresentationAuthorityClass,
    TextRepresentationReferenceV1,
    TextRepresentationType,
    TransformationProfileV1,
    TransformationRegistryEntryV1,
    content_hash,
    text_representation_reference_id,
)
from mnemo.models.v2_retrieval_authorization import (
    V2ActiveRuntimeBindingV1,
    V2RetrievalAuthorizationDecisionV1,
)
from mnemo.phase85.full_multilingual_v2 import (
    CoverageRecordingGenerationBuilderV2,
    MultilingualEmbeddingGenerationBuilderV3,
    MultilingualTextGenerationBuilderV2,
    MultilingualVectorGenerationBuilderV2,
    RepresentationGenerationInputV2,
    full_multilingual_v2_generation_plan,
)
from mnemo.phase85.language_capabilities import (
    LanguageCapabilityAdmissionV2,
    ProviderSupportState,
    provider_language_claims_from_profile,
)
from mnemo.phase85.profiles import ModelProfileDefinition, profile_snapshot
from mnemo.phase85.projections import (
    ProjectionBuildResult,
    ProjectionCompleteness,
    ProjectionCoverage,
)
from mnemo.phase85.v2_activation_authorization import first_v2_deactivation_recovery_digest
from mnemo.phase85.v2_readiness import (
    V2GenerationCapability,
    V2GenerationEvidence,
    V2ReadinessInputs,
    V2RollbackTarget,
    V2TransportEvidence,
    project_v2_readiness,
)
from mnemo.retrieval.full_multilingual_advanced_v2 import FullMultilingualAdvancedSourceV2
from mnemo.retrieval.full_multilingual_v2 import (
    FullMultilingualRetrievalApplicationV2,
    MultilingualSparseMatchV2,
)
from mnemo.retrieval.language_detection import (
    ConfiguredUnicodeScriptDetectorV1,
    DetectorRegistrationV1,
    LanguageDetectorRegistryV2,
    ScriptDetectorRegistryV1,
    UnknownLanguageDetectorV2,
    _source_scope,
)
from mnemo.retrieval.multilingual_providers import _BGERerankerTokenizer
from mnemo.retrieval.reranker_candidates import (
    RenderedRerankerPairV1,
    RerankerCandidateBuilderV1,
    V2TypedCandidateBuilderV1,
)
from mnemo.retrieval.text_representations import (
    ConfiguredRepresentationDetectorV1,
    DeterministicTransformationRegistryV1,
    GovernedMappingRepresentationTransformerV1,
    RepresentationDetectionResultV1,
    RepresentationPipelineV1,
)
from mnemo.storage.multilingual import (
    _decode_checked,
    _escape_like,
    _multilingual_fts_query_v2,
    _typed,
    multilingual_v2_generation_set_digest,
)
from mnemo.storage.sqlite import SQLiteStore

ZERO = "0" * 64


def test_multilingual_storage_helpers_fail_closed_and_escape_search_terms() -> None:
    """Persistence helpers verify payload integrity and preserve literal sparse-search intent."""
    generations = (UUID(int=1), UUID(int=2), UUID(int=3), UUID(int=4))
    digest = multilingual_v2_generation_set_digest(
        profile_fingerprint=ZERO,
        generation_ids=generations,
    )
    assert len(digest) == 64
    assert digest == multilingual_v2_generation_set_digest(
        profile_fingerprint=ZERO,
        generation_ids=tuple(reversed(generations)),
    )
    with pytest.raises(ValueError, match="lowercase SHA"):
        multilingual_v2_generation_set_digest(
            profile_fingerprint="A" * 64,
            generation_ids=generations,
        )
    with pytest.raises(ValueError, match="exactly four"):
        multilingual_v2_generation_set_digest(
            profile_fingerprint=ZERO,
            generation_ids=generations[:3],
        )
    assert _multilingual_fts_query_v2('Hello, "World"!') == '"hello" OR "world"'
    with pytest.raises(ValueError, match="no searchable"):
        _multilingual_fts_query_v2("---")
    assert _escape_like(r"100%_\\") == r"100\%\_\\\\"
    payload = '{"safe":true}'
    with pytest.raises(Exception, match="integrity"):
        _decode_checked((payload, "wrong"))
    assert _typed(None, dict, "payload") is None
    with pytest.raises(Exception, match="invalid persisted"):
        _typed([], dict, "payload")


class _Transformers5XLMRTokenizer:
    bos_token_id = 0
    sep_token_id = 2

    def num_special_tokens_to_add(self, *, pair: bool) -> int:
        assert pair
        return 4


def test_reranker_tokenizer_supports_frozen_xlmr_pair_layout_without_legacy_api() -> None:
    rendered = _BGERerankerTokenizer(_Transformers5XLMRTokenizer()).build_pair((10, 11), (20, 21))
    assert rendered.input_ids == (0, 10, 11, 2, 2, 20, 21, 2)
    assert rendered.attention_mask == (1,) * 8
    assert rendered.token_type_ids == (0,) * 8


def _source(text: str = "actual semantic evidence") -> LanguageEvidenceReferenceV3:
    return LanguageEvidenceReferenceV3(
        notebook_id=uuid4(),
        source_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        kind=LanguageEvidenceKindV3.CANONICAL_CHUNK,
        evidence_id="chunk:not-a-uuid",
        chunk_id="chunk:not-a-uuid",
        source_content_hash=content_hash(text),
    )


def _scope(source: LanguageEvidenceReferenceV3) -> AuthorizationScopeV1:
    return AuthorizationScopeV1(
        actor_scope_digest=ZERO,
        notebook_id=source.notebook_id,
        source_id=source.source_id,
        document_id=source.document_id,
        version_id=source.version_id,
        occurrence_id=source.occurrence_id,
        derivation_id=source.derivation_id,
        authorization_policy_id="central-authorization-v1",
        authorization_policy_revision="1",
    )


def _representation(
    source: LanguageEvidenceReferenceV3, text: str
) -> TextRepresentationReferenceV1:
    observation_id = uuid4()
    reference_id = text_representation_reference_id(
        evidence_reference_digest=source.identity_digest,
        representation_type=TextRepresentationType.UNICODE_SEMANTIC_TEXT,
        authority=RepresentationAuthority.ORIGINAL,
        content_hash=content_hash(text),
        observation_id=observation_id,
        derivation_id=None,
        source_generation_ids=(),
    )
    return TextRepresentationReferenceV1(
        reference_id=reference_id,
        evidence_reference=source,
        representation_type=TextRepresentationType.UNICODE_SEMANTIC_TEXT,
        representation_authority=RepresentationAuthority.ORIGINAL,
        content_hash=content_hash(text),
        representation_observation_id=observation_id,
        representation_derivation_id=None,
        source_generation_ids=(),
        language_observation_references=(),
        script_observation_references=(),
    )


def test_v2_reference_upgrades_without_uuid_assumption() -> None:
    old = LanguageEvidenceReferenceV2(
        notebook_id=uuid4(),
        source_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        kind=LanguageEvidenceKindV2.CANONICAL_CHUNK,
        evidence_id="parser:block/17",
        chunk_id="parser:block/17",
        source_content_hash=ZERO,
    )
    upgraded = LanguageEvidenceReferenceV3.from_v2(old)
    assert upgraded.evidence_id == "parser:block/17"
    assert upgraded.lineage_origin is EvidenceLineageOriginV3.LEGACY_V2_UPGRADE
    assert upgraded.kind is LanguageEvidenceKindV3.CANONICAL_CHUNK


def test_language_and_script_are_independent_observations() -> None:
    assert LanguageCode("und").value == "und"
    assert ScriptCode("Deva").value == "Deva"
    assert ProviderSupportState.MODEL_SUPPORTED.value == "model_supported"
    assert TextRepresentationType.MIXED.value == "mixed"


def test_script_detector_never_infers_language() -> None:
    source = _source("मराठी")
    language = asyncio.run(
        UnknownLanguageDetectorV2().detect_languages(
            actor_id=uuid4(),
            notebook_id=source.notebook_id,
            target_id=source.evidence_id,
            text="मराठी",
            source=source,
        )
    )
    script = asyncio.run(
        ConfiguredUnicodeScriptDetectorV1({"Deva": ((0x0900, 0x097F),)}).detect_scripts(
            actor_id=uuid4(),
            notebook_id=source.notebook_id,
            target_id=source.evidence_id,
            text="मराठी",
            source=source,
        )
    )
    assert language.hypotheses[0].language == LanguageCode("und")
    assert script.hypotheses[0].script == ScriptCode("Deva")


class _Tokenizer:
    identity = "BAAI/bge-reranker-v2-m3"
    revision = "exact-revision"
    configuration_digest = ZERO

    def encode_without_special_tokens(self, text: str) -> tuple[int, ...]:
        return tuple(range(1, len(text.split()) + 1))

    def build_pair(
        self, query_ids: tuple[int, ...], document_ids: tuple[int, ...]
    ) -> RenderedRerankerPairV1:
        ids = (101, *query_ids, 102, *document_ids, 102)
        return RenderedRerankerPairV1(
            input_ids=ids,
            attention_mask=tuple(1 for _ in ids),
            token_type_ids=tuple(0 for _ in ids),
        )


class _Resolver:
    def __init__(self, source: LanguageEvidenceReferenceV3, text: str, title: str) -> None:
        representation = _representation(source, text)
        self.value = AuthorizedRerankerEvidenceV1(
            candidate_id=uuid4(),
            source_reference=source,
            representation_reference=representation,
            semantic_text=text,
            title_metadata=title,
            language_observation_references=(),
            script_observation_references=(),
            provenance=CandidateProvenanceV1(
                source_reference_digest=source.identity_digest,
                representation_reference_id=representation.reference_id,
                authorization_scope_digest=ZERO,
                retrieval_snapshot_identity=ZERO,
                retrieval_paths_digest=ZERO,
                fusion_policy_id="rrf-v1",
                fusion_rank=1,
                source_generation_ids=(),
            ),
        )
        self.last_decision: V2RetrievalAuthorizationDecisionV1 | None = None
        self.return_raw = False

    async def resolve_reranker_evidence(self, **kwargs: object) -> AuthorizedRerankerEvidenceV1:
        decision = kwargs["decision"]
        assert isinstance(decision, V2RetrievalAuthorizationDecisionV1)
        self.last_decision = decision
        if self.return_raw:
            return self.value
        return replace(
            self.value,
            provenance=replace(
                self.value.provenance,
                authorization_scope_digest=decision.decision_fingerprint,
            ),
        )


def _decision_for_source(
    source: LanguageEvidenceReferenceV3, *, version_id: UUID | None = None
) -> V2RetrievalAuthorizationDecisionV1:
    return V2RetrievalAuthorizationDecisionV1(
        decision_id=uuid4(),
        principal_actor_id=uuid4(),
        operation="retrieve",
        retrieval_scope=RetrievalScopeV2(
            notebook_id=source.notebook_id,
            source_ids=(source.source_id,),
            document_ids=(source.document_id,),
            version_ids=(version_id or source.version_id,),
        ),
        positional_scope=PositionalScopeV2(),
        runtime_binding=V2ActiveRuntimeBindingV1(
            alias_set_digest=ZERO,
            generation_ids=tuple(uuid4() for _ in range(4)),
            profile_fingerprint=ZERO,
            vector_space_identity=ZERO,
            database_identity=ZERO,
            build_run_id=uuid4(),
            admission_policy_identity="fixture-admission/1",
        ),
        authorization_policy_identity="fixture-v2/1",
        authorization_policy_revision="1",
        request_fingerprint=ZERO,
        issued_at="fixture",
        required_provenance_evidence=("language-evidence-reference-v3",),
    )


def test_typed_candidate_builder_enforces_scope_paths_and_resolver_provenance() -> None:
    text = "actual authorized semantic evidence"
    source = _source(text)
    decision = _decision_for_source(source)
    resolver = _Resolver(source, text, "Human title")
    builder = V2TypedCandidateBuilderV1(resolver=resolver)

    async def scenario() -> None:
        candidate = await builder.build(
            query="grounded query",
            source=source,
            decision=decision,
            input_ordinal=0,
            retrieval_paths=("sparse", "dense"),
        )
        assert candidate.semantic_text == text
        assert candidate.input_audit.query_hash == hashlib.sha256(b"grounded query").hexdigest()
        with pytest.raises(ValueError, match="query must not be blank"):
            await builder.build(
                query=" ",
                source=source,
                decision=decision,
                input_ordinal=0,
                retrieval_paths=("sparse",),
            )
        with pytest.raises(ValueError, match=r"\[0,199\]"):
            await builder.build(
                query="q",
                source=source,
                decision=decision,
                input_ordinal=200,
                retrieval_paths=("sparse",),
            )
        for scope_field, value, label in (
            ("source_ids", (uuid4(),), "source"),
            ("document_ids", (uuid4(),), "document"),
            ("version_ids", (uuid4(),), "version"),
        ):
            denied = replace(
                decision,
                retrieval_scope=decision.retrieval_scope.model_copy(update={scope_field: value}),
            )
            with pytest.raises(PermissionError, match=label):
                await builder.build(
                    query="q",
                    source=source,
                    decision=denied,
                    input_ordinal=0,
                    retrieval_paths=("sparse",),
                )
        other_notebook = replace(
            decision,
            retrieval_scope=decision.retrieval_scope.model_copy(update={"notebook_id": uuid4()}),
        )
        with pytest.raises(PermissionError, match="evidence notebook"):
            await builder.build(
                query="q",
                source=source,
                decision=other_notebook,
                input_ordinal=0,
                retrieval_paths=("sparse",),
            )
        for paths in ((), ("sparse", "sparse")):
            with pytest.raises(ValueError, match="non-empty and unique"):
                await builder.build(
                    query="q",
                    source=source,
                    decision=decision,
                    input_ordinal=0,
                    retrieval_paths=paths,
                )

        original = resolver.value
        wrong_source = replace(original)
        object.__setattr__(
            wrong_source,
            "source_reference",
            replace(source, evidence_id="x"),
        )
        resolver.value = wrong_source
        resolver.return_raw = True
        with pytest.raises(ValueError, match="different source"):
            await builder.build(
                query="q",
                source=source,
                decision=decision,
                input_ordinal=0,
                retrieval_paths=("sparse",),
            )
        blank_text = replace(
            original,
            provenance=replace(
                original.provenance,
                authorization_scope_digest=decision.decision_fingerprint,
            ),
        )
        object.__setattr__(blank_text, "semantic_text", " ")
        resolver.value = blank_text
        with pytest.raises(ValueError, match="semantic text cannot be blank"):
            await builder.build(
                query="q",
                source=source,
                decision=decision,
                input_ordinal=0,
                retrieval_paths=("sparse",),
            )

    asyncio.run(scenario())


def test_candidate_builder_uses_authorized_semantic_text_not_title() -> None:
    text = "actual semantic evidence from the governed source"
    source = _source(text)
    builder = RerankerCandidateBuilderV1(
        resolver=_Resolver(source, text, "manuscript.pdf"),
        tokenizer=_Tokenizer(),
        provider_id="sentence-transformers",
        model_id="BAAI/bge-reranker-v2-m3",
        model_revision="exact-revision",
        provider_configuration_digest=ZERO,
        query_preprocessing_identity="query-v1",
        document_preprocessing_identity="document-v1",
        preprocess_query=lambda value: value,
        preprocess_document=lambda value: value,
    )
    candidate = asyncio.run(
        builder.build(
            query="find governed evidence",
            source=source,
            decision=_decision_for_source(source),
            input_ordinal=0,
            retrieval_paths=("sparse",),
        )
    )
    assert candidate.semantic_text == text
    assert candidate.input_audit.title_metadata_included is False
    assert candidate.input_audit.retained_token_count <= 256


def test_candidate_builder_rejects_scope_mismatch_before_resolution() -> None:
    text = "authorized semantic evidence"
    source = _source(text)
    wrong_version_id = uuid4()
    builder = RerankerCandidateBuilderV1(
        resolver=_Resolver(source, text, "display title"),
        tokenizer=_Tokenizer(),
        provider_id="sentence-transformers",
        model_id="BAAI/bge-reranker-v2-m3",
        model_revision="exact-revision",
        provider_configuration_digest=ZERO,
        query_preprocessing_identity="query-v1",
        document_preprocessing_identity="document-v1",
        preprocess_query=lambda value: value,
        preprocess_document=lambda value: value,
    )
    with pytest.raises(PermissionError, match="excludes evidence version"):
        asyncio.run(
            builder.build(
                query="governed query",
                source=source,
                decision=_decision_for_source(source, version_id=wrong_version_id),
                input_ordinal=0,
                retrieval_paths=("sparse",),
            )
        )


def test_title_only_candidate_is_structurally_rejected() -> None:
    source = _source("manuscript.pdf")
    with pytest.raises(ValueError, match="title-only"):
        _Resolver(source, "manuscript.pdf", "manuscript.pdf")


def test_ungrounded_query_cannot_enter_ranking_metrics() -> None:
    query = "find related English evidence"
    with pytest.raises(ValueError, match="non-semantic"):
        QueryRecordV2(
            query_id="generic",
            query_text=query,
            query_hash=hashlib.sha256(query.encode()).hexdigest(),
            query_class=QueryClassV2.ROUTING_BEHAVIORAL,
            grounding_state=QueryGroundingState.UNGROUNDED,
            include_in_ranking_metrics=True,
        )


def test_corpus_absent_requires_census_proof() -> None:
    evidence = CorpusPresenceEvidenceV1(
        corpus_manifest_digest=ZERO,
        source_census_digest=ZERO,
        authorized_evidence_census_digest=ZERO,
        notebook_id=uuid4(),
        query_id="q1",
        presence_state="present",
        relevant_evidence_reference_digests=(ZERO,),
        census_algorithm_id="immutable-census-v1",
    )
    failure = EvaluationFailureRecordV2(
        case_id="case-1",
        failure_code=EvaluationFailureCodeV2.CORPUS_ABSENT,
        stage="corpus",
        evidence_refs=(),
        preceding_stage_status=(),
        recoverable=False,
    )
    assert evidence.presence_state == "present"
    assert failure.failure_code is EvaluationFailureCodeV2.CORPUS_ABSENT


def _generation(capability: V2GenerationCapability, vector: bool) -> V2GenerationEvidence:
    return V2GenerationEvidence(
        capability=capability,
        generation_id=uuid4(),
        profile_id="full-multilingual-v2",
        provider_identity="provider" if vector else None,
        model_identity="model" if vector else None,
        configuration_digest=ZERO,
        vector_space_identity=ZERO if vector else None,
        state="ready",
        coverage_completeness="complete",
        item_count=2,
        coverage_count=2,
        checksum=ZERO,
        coverage_checksum=ZERO,
        source_generation_ids=(),
        language_coverage_digest=ZERO,
        script_coverage_digest=ZERO,
        representation_coverage_digest=ZERO,
        provenance_digest=ZERO,
    )


def test_v2_readiness_is_derived_and_fails_closed() -> None:
    generations = tuple(
        _generation(
            capability,
            capability
            in {
                V2GenerationCapability.MULTILINGUAL_EMBEDDING,
                V2GenerationCapability.MULTILINGUAL_VECTOR,
            },
        )
        for capability in V2GenerationCapability
    )
    transport = V2TransportEvidence(
        representation_vocabulary_digest=ZERO,
        http_schema_digest=ZERO,
        openapi_digest=ZERO,
        mcp_schema_digest=ZERO,
        structured_content_schema_digest=ZERO,
        json_fallback_schema_digest=ZERO,
        capability_schema_digest=ZERO,
        stdio_verified=False,
        sse_verified=False,
    )
    snapshot = project_v2_readiness(
        V2ReadinessInputs(
            profile_fingerprint=ZERO,
            provider_dependencies_ready=False,
            detector_dependencies_ready=True,
            representation_dependencies_ready=True,
            transformation_dependencies_ready=True,
            vector_space_compatible=True,
            checksums_valid=True,
            provenance_complete=True,
            authorization_compatible=True,
            rollback_metadata_valid=True,
            active_alias_set_atomic=False,
            active_alias_matches_ready_set=False,
            transport_contract_complete=False,
            transport_parity_verified=False,
            shared_application_path_verified=False,
            pre_exposure_security_gate_passed=False,
            generation_set=generations,
            rollback_target=V2RollbackTarget(
                alias_set_digest=ZERO,
                generation_ids=(uuid4(),),
                complete=True,
                compatible=True,
                retained=True,
            ),
            transport_evidence=transport,
            runtime_activation_selected=False,
            runtime_exposure_selected=False,
        )
    )
    assert snapshot.v2_ready is False
    assert snapshot.v2_active is False
    assert snapshot.v2_exposed is False
    assert "provider_dependencies_not_ready" in snapshot.reason_codes


def test_generation_plan_is_language_generic_and_dependency_bound() -> None:
    plan = full_multilingual_v2_generation_plan(
        profile_id="full-multilingual-v2",
        profile_fingerprint=ZERO,
        source_version_ids=(uuid4(),),
        representation_configuration_digest=ZERO,
        detector_configuration_digest=ZERO,
        authorization_policy_digest=ZERO,
        embedding_provider_identity="sentence-transformers",
        embedding_model_identity="BAAI/bge-m3",
        embedding_model_revision="exact-revision",
        embedding_preprocessing_digest=ZERO,
        vector_space_identity=ZERO,
        dimensions=1024,
    )
    assert plan.language_text.source_generation_ids == (
        plan.representation_derivation.generation_id,
    )
    assert plan.multilingual_embedding.source_generation_ids == (
        plan.representation_derivation.generation_id,
    )
    assert plan.multilingual_vector.source_generation_ids == (
        plan.multilingual_embedding.generation_id,
    )
    payload = repr(plan)
    assert "en-hi-mr" not in payload


def test_coverage_wrapper_publishes_exact_build_identity() -> None:
    class Builder:
        async def build(self, generation_id: UUID) -> ProjectionBuildResult:
            del generation_id
            return ProjectionBuildResult(
                expected_count=2,
                succeeded_count=2,
                failed_count=0,
                skipped_count=0,
                checksum="1" * 64,
            )

    class Store:
        value: object | None = None

        async def put_multilingual_coverage_manifest_v2(
            self, manifest: MultilingualCoverageManifestV2
        ) -> bool:
            self.value = manifest
            return True

    generation_id = uuid4()
    store = Store()
    result = asyncio.run(
        CoverageRecordingGenerationBuilderV2(
            builder=Builder(),
            store=store,
            generation_id=generation_id,
            capability="multilingual_embedding_v2",
            profile_fingerprint=ZERO,
            dependency_digest=ZERO,
            rollback_metadata_digest=ZERO,
            language_tags=("fr",),
            script_codes=("Latn",),
            representation_types=("unicode_semantic_text",),
            source_kinds=("canonical_chunk",),
        ).build(generation_id)
    )
    assert result.checksum == "1" * 64
    assert store.value is not None
    assert store.value.item_identity_digest == result.checksum


def test_v2_alias_promotion_requires_complete_bound_generation_sets(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = SQLiteStore(tmp_path / "v2-aliases.db")
        await store.open()
        try:
            now = datetime.now(UTC)
            capabilities = (
                "representation_derivation_v2",
                "language_text_v2",
                "multilingual_embedding_v2",
                "multilingual_vector_v2",
            )

            async def ready_generation(capability: str, with_manifest: bool) -> UUID:
                generation_id = uuid4()
                assert await store.create_index_generation(
                    IndexGeneration(
                        generation_id=generation_id,
                        capability=capability,
                        profile="full-multilingual-v2",
                        schema_version=1,
                        input_scope="isolated-v2-fixture",
                        provider_identity="fixture",
                        model_identity=None,
                        configuration_digest=ZERO,
                        dimensions=None,
                        state=IndexGenerationState.BUILDING,
                        item_count=0,
                        checksum=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
                coverage = ProjectionCoverage(
                    generation_id=generation_id,
                    expected_count=1,
                    succeeded_count=1,
                    failed_count=0,
                    skipped_count=0,
                    completeness=ProjectionCompleteness.COMPLETE,
                    checksum="1" * 64,
                    failure_digest=None,
                    updated_at=now,
                )
                assert await store.put_index_generation_coverage(coverage)
                assert await store.transition_index_generation(
                    generation_id,
                    IndexGenerationState.BUILDING,
                    IndexGenerationState.READY,
                    item_count=1,
                    checksum="1" * 64,
                )
                if with_manifest:
                    assert await store.put_multilingual_coverage_manifest_v2(
                        MultilingualCoverageManifestV2(
                            generation_id=generation_id,
                            capability=capability,
                            profile_fingerprint=ZERO,
                            dependency_digest=ZERO,
                            expected_count=1,
                            succeeded_count=1,
                            failed_count=0,
                            skipped_count=0,
                            language_tags=("fr",),
                            script_codes=("Latn",),
                            representation_types=("unicode_semantic_text",),
                            source_kinds=("canonical_chunk",),
                            provenance_complete=True,
                            authorization_compatible=True,
                            rollback_metadata_digest=ZERO,
                            item_identity_digest="1" * 64,
                            created_at=now,
                        )
                    )
                return generation_id

            current = tuple(
                [await ready_generation(capability, True) for capability in capabilities]
            )
            authorization_id = uuid4()
            authorization_digest = "2" * 64
            first = await store.promote_multilingual_v2_alias_set(
                profile_fingerprint=ZERO,
                generation_ids=current,
                rollback_alias_set_digest=first_v2_deactivation_recovery_digest(
                    profile_fingerprint=ZERO
                ),
                rollback_generation_ids=(),
                expected_active_alias_set_digest=None,
                activation_mode="first_v2_activation",
                recovery_mode="deactivate_v2_alias_set",
                authorization_id=authorization_id,
                authorization_digest=authorization_digest,
            )
            assert await store.resolve_active_multilingual_v2_generation_set() == current
            with pytest.raises(ConflictError, match="recovery authorization mismatch"):
                await store.deactivate_first_multilingual_v2_alias_set(
                    expected_active_alias_set_digest=first,
                    authorization_id=authorization_id,
                    authorization_digest="3" * 64,
                )
            assert await store.deactivate_first_multilingual_v2_alias_set(
                expected_active_alias_set_digest=first,
                authorization_id=authorization_id,
                authorization_digest=authorization_digest,
            )
            assert await store.resolve_active_multilingual_v2_generation_set() is None
            first = await store.promote_multilingual_v2_alias_set(
                profile_fingerprint=ZERO,
                generation_ids=current,
                rollback_alias_set_digest=first_v2_deactivation_recovery_digest(
                    profile_fingerprint=ZERO
                ),
                rollback_generation_ids=(),
                expected_active_alias_set_digest=None,
                activation_mode="first_v2_activation",
                recovery_mode="deactivate_v2_alias_set",
                authorization_id=authorization_id,
                authorization_digest=authorization_digest,
            )
            with pytest.raises(ValueError, match="first V2 activation"):
                await store.promote_multilingual_v2_alias_set(
                    profile_fingerprint=ZERO,
                    generation_ids=current,
                    rollback_alias_set_digest=first_v2_deactivation_recovery_digest(
                        profile_fingerprint=ZERO
                    ),
                    rollback_generation_ids=current,
                    expected_active_alias_set_digest=first,
                    activation_mode="first_v2_activation",
                    recovery_mode="deactivate_v2_alias_set",
                    authorization_id=authorization_id,
                    authorization_digest=authorization_digest,
                )
            rollback = current
            next_set = tuple(
                [await ready_generation(capability, True) for capability in capabilities]
            )
            rollback_digest = multilingual_v2_generation_set_digest(
                profile_fingerprint=ZERO, generation_ids=rollback
            )
            with pytest.raises(ValueError, match="does not bind"):
                await store.promote_multilingual_v2_alias_set(
                    profile_fingerprint=ZERO,
                    generation_ids=next_set,
                    rollback_alias_set_digest="2" * 64,
                    rollback_generation_ids=rollback,
                    expected_active_alias_set_digest=first,
                    authorization_id=authorization_id,
                    authorization_digest=authorization_digest,
                )
            alias = await store.promote_multilingual_v2_alias_set(
                profile_fingerprint=ZERO,
                generation_ids=next_set,
                rollback_alias_set_digest=rollback_digest,
                rollback_generation_ids=rollback,
                expected_active_alias_set_digest=first,
                authorization_id=authorization_id,
                authorization_digest=authorization_digest,
            )
            assert len(alias) == 64
        finally:
            await store.close()

    asyncio.run(scenario())


def test_provider_claims_do_not_admit_language_operation() -> None:
    admission = LanguageCapabilityAdmissionV2(())
    assert admission.permits(language=LanguageCode("mr"), operation="dense_retrieval") is False


def test_v2_generation_builders_validate_identity_and_empty_populations() -> None:
    """Empty governed populations are deterministic while cross-generation use fails closed."""
    generation = uuid4()

    class EmptyProvider:
        async def embed_documents_v3(self, values):  # type: ignore[no-untyped-def]
            return tuple(values)

    class Store:
        async def put_multilingual_embedding_v3(self, value: object) -> bool:
            del value
            return True

        async def put_multilingual_text_projection_row_v2(self, value: object) -> bool:
            del value
            return True

    with pytest.raises(ValueError, match="governed bound"):
        MultilingualEmbeddingGenerationBuilderV3(
            provider=EmptyProvider(),  # type: ignore[arg-type]
            store=Store(),  # type: ignore[arg-type]
            generation_id=generation,
            inputs=(),
            max_batch=0,
        )
    embedding = MultilingualEmbeddingGenerationBuilderV3(
        provider=EmptyProvider(),  # type: ignore[arg-type]
        store=Store(),  # type: ignore[arg-type]
        generation_id=generation,
        inputs=(),
    )
    text = MultilingualTextGenerationBuilderV2(
        store=Store(),  # type: ignore[arg-type]
        generation_id=generation,
        rows=(),
    )
    vector = MultilingualVectorGenerationBuilderV2(
        generation_id=generation,
        source_embedding_generation_id=uuid4(),
        vector_space_identity="a" * 64,
        embeddings=(),
    )

    async def scenario() -> None:
        for builder in (embedding, text, vector):
            result = await builder.build(generation)
            assert result.expected_count == result.succeeded_count == 0
            with pytest.raises(ValueError, match="generation identity mismatch"):
                await builder.build(uuid4())

    asyncio.run(scenario())


def test_representation_generation_input_binds_text_source_and_reference() -> None:
    source = _source("semantic text")
    representation = _representation(source, "semantic text")
    value = RepresentationGenerationInputV2(
        actor_id=uuid4(),
        source=source,
        text="semantic text",
        source_representation=representation,
    )
    assert value.source == source
    with pytest.raises(ValueError, match="must not be blank"):
        replace(value, text=" ")
    with pytest.raises(ValueError, match="source mismatch"):
        replace(value, source_representation=_representation(_source("other"), "other"))
    with pytest.raises(ValueError, match="source hash mismatch"):
        replace(value, text="different")


def test_detector_registries_select_ready_provider_and_reject_ambiguous_registration() -> None:
    language = UnknownLanguageDetectorV2()
    script = ConfiguredUnicodeScriptDetectorV1(
        {"Latn": ((0x0041, 0x007A),), "Deva": ((0x0900, 0x097F),)}
    )
    disabled_language = DetectorRegistrationV1(
        provider=language, priority=0, configured=False, ready=False, enabled=False
    )
    enabled_language = DetectorRegistrationV1(
        provider=language, priority=1, configured=True, ready=True, enabled=True
    )
    enabled_script = DetectorRegistrationV1(
        provider=script, priority=0, configured=True, ready=True, enabled=True
    )
    with pytest.raises(ValueError, match="non-negative"):
        replace(enabled_language, priority=-1)
    with pytest.raises(ValueError, match="configured and ready"):
        replace(enabled_language, ready=False)
    with pytest.raises(TypeError, match="invalid provider"):
        LanguageDetectorRegistryV2(
            (
                DetectorRegistrationV1(
                    provider=object(),
                    priority=0,
                    configured=False,
                    ready=False,
                    enabled=False,
                ),
            )
        )
    with pytest.raises(ValueError, match="duplicate"):
        LanguageDetectorRegistryV2((disabled_language, enabled_language))

    async def scenario() -> None:
        with pytest.raises(LookupError, match="no configured"):
            await LanguageDetectorRegistryV2((disabled_language,)).detect(
                actor_id=uuid4(), notebook_id=uuid4(), target_id="query", text="text"
            )
        observation = await LanguageDetectorRegistryV2((enabled_language,)).detect(
            actor_id=uuid4(), notebook_id=uuid4(), target_id="query", text="text"
        )
        assert observation.hypotheses[0].language == LanguageCode("und")
        scripts = await ScriptDetectorRegistryV1((enabled_script,)).detect(
            actor_id=uuid4(), notebook_id=uuid4(), target_id="mixed", text="abc नम"
        )
        assert scripts.mixed_script
        assert {item.script for item in scripts.hypotheses} == {
            ScriptCode("Latn"),
            ScriptCode("Deva"),
        }

    asyncio.run(scenario())


def test_configured_script_detector_handles_unknown_common_and_source_scopes() -> None:
    with pytest.raises(ValueError, match="invalid configured"):
        ConfiguredUnicodeScriptDetectorV1({"Latn": ((10, 1),)})
    detector = ConfiguredUnicodeScriptDetectorV1(
        {"Latn": ((0x0041, 0x007A),), "Zyyy": ((0x0030, 0x0039),)}
    )

    async def scenario() -> None:
        unknown = await detector.detect_scripts(
            actor_id=uuid4(), notebook_id=uuid4(), target_id="unknown", text="123"
        )
        assert unknown.hypotheses[0].script == ScriptCode("Zzzz")
        source = _source("abc")
        with pytest.raises(ValueError, match="conflicts with source"):
            await detector.detect_scripts(
                actor_id=uuid4(),
                notebook_id=source.notebook_id,
                target_id="bad",
                text="xyz",
                source=source,
            )
        with pytest.raises(ValueError, match="conflicts with source"):
            await UnknownLanguageDetectorV2().detect_languages(
                actor_id=uuid4(),
                notebook_id=source.notebook_id,
                target_id="bad",
                text="xyz",
                source=source,
            )

    asyncio.run(scenario())
    assert _source_scope(None) is LanguageObservationScope.QUERY
    assert _source_scope(_source()) is LanguageObservationScope.CHUNK
    assert (
        _source_scope(SimpleNamespace(kind=LanguageEvidenceKindV3.OCR_REGION))
        is LanguageObservationScope.OCR_REGION
    )
    assert (
        _source_scope(SimpleNamespace(kind=LanguageEvidenceKindV3.VISION_DERIVATION))
        is LanguageObservationScope.ASSET
    )
    assert (
        _source_scope(SimpleNamespace(kind=LanguageEvidenceKindV3.LANGUAGE_DERIVATION))
        is LanguageObservationScope.DOCUMENT
    )


def test_profile_claim_projection_ignores_legacy_language_arrays() -> None:
    snapshot = profile_snapshot(
        ModelProfileDefinition.model_validate(
            {
                "profile_id": "generic-v2",
                "version": "1",
                "mode": "phase8_5",
                "trust_class": "local_trusted",
                "certification": "candidate",
                "models": {
                    "multilingual_embedding": {
                        "provider": "test",
                        "model": "model",
                        "revision": "exact",
                        "license": "test",
                        "preprocessing": "document-v1",
                        "languages": ["legacy-not-evidence"],
                        "language_claims": [
                            {
                                "language": "fr",
                                "script": "Latn",
                                "operations": ["embedding"],
                                "claim_source_digest": ZERO,
                            }
                        ],
                    }
                },
            }
        )
    )
    claims = provider_language_claims_from_profile(snapshot)
    assert tuple(item.language.value for item in claims) == ("fr",)
    assert claims[0].operation.value == "embedding"


def test_v2_sparse_projection_is_authorization_and_position_scoped(tmp_path: Path) -> None:
    async def scenario() -> None:
        path = tmp_path / "full-multilingual-v2-sparse.db"
        store = SQLiteStore(path)
        await store.open()
        try:
            text = "governed semantic marathi evidence"
            source = _source(text)
            representation = _representation(source, text)
            generation_id = uuid4()
            row = MultilingualTextProjectionRowV2(
                row_id=multilingual_text_projection_row_v2_id(
                    source=source,
                    representation=representation,
                    language=LanguageCode("mr"),
                    generation_id=generation_id,
                ),
                source=source,
                representation=representation,
                language=LanguageCode("mr"),
                text=text,
                text_hash=content_hash(text),
                position=MultilingualEvidencePositionV1(
                    page_number=7,
                    section_index=2,
                    heading_path=("Appendix", "Marathi"),
                ),
                language_observation_references=(),
                script_observation_references=(),
                generation_id=generation_id,
                source_generation_ids=(),
                created_at=datetime.now(UTC),
            )
            assert await store.put_multilingual_text_projection_row_v2(row)
            found = await store.search_authorized_multilingual_text_v2(
                notebook_id=source.notebook_id,
                generation_id=generation_id,
                query="marathi evidence",
                authorized_sources=(source,),
                page_start=7,
                page_end=7,
                section_indexes=(2,),
                heading_prefix=("Appendix",),
                limit=10,
            )
            assert found[0][0] == row
            excluded = await store.search_authorized_multilingual_text_v2(
                notebook_id=source.notebook_id,
                generation_id=generation_id,
                query="marathi evidence",
                authorized_sources=(source,),
                page_start=8,
                page_end=None,
                section_indexes=(),
                heading_prefix=(),
                limit=10,
            )
            assert excluded == ()
            assert (
                await store.search_authorized_multilingual_text_v2(
                    notebook_id=source.notebook_id,
                    generation_id=generation_id,
                    query="marathi evidence",
                    authorized_sources=(),
                    page_start=None,
                    page_end=None,
                    section_indexes=(),
                    heading_prefix=(),
                    limit=10,
                )
                == ()
            )
        finally:
            await store.close()

    asyncio.run(scenario())


def test_v2_embedding_enumeration_is_authorization_and_vector_space_scoped(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        store = SQLiteStore(tmp_path / "v2-embedding-enumeration.db")
        await store.open()
        try:
            text = "governed multilingual vector"
            source = _source(text)
            representation = _representation(source, text)
            profile = MultilingualEmbeddingProfile(
                provider="test-provider",
                model="test-model",
                revision="immutable-revision",
                profile="test-profile",
                generation_id=uuid4(),
                dimension=2,
                normalized=True,
                distance_metric="cosine",
                preprocessing_digest="a" * 64,
                languages=(LanguageCode("mr"),),
                scripts=(ScriptCode("Deva"),),
                capability_state=LanguageCapabilityState.SUPPORTED,
            )
            vector = (1.0, 0.0)
            embedding = MultilingualEmbeddingV3(
                embedding_id=multilingual_embedding_v3_id(
                    source=source,
                    representation=representation,
                    language=LanguageCode("mr"),
                    profile=profile,
                ),
                source=source,
                representation=representation,
                language=LanguageCode("mr"),
                profile=profile,
                vector=vector,
                vector_hash=multilingual_vector_hash(vector),
                source_hash=source.source_content_hash,
                representation_hash=representation.content_hash,
                language_observation_references=(),
                script_observation_references=(),
                created_at=datetime.now(UTC),
            )
            assert await store.put_multilingual_embedding_v3(embedding)
            assert not await store.put_multilingual_embedding_v3(embedding)
            found = await store.list_authorized_multilingual_embeddings_v3(
                notebook_id=source.notebook_id,
                generation_id=profile.generation_id,
                vector_space=profile.vector_space,
                authorized_sources=(source,),
            )
            assert found == (embedding,)
            assert (
                await store.list_authorized_multilingual_embeddings_v3(
                    notebook_id=source.notebook_id,
                    generation_id=profile.generation_id,
                    vector_space=profile.vector_space,
                    authorized_sources=(),
                )
                == ()
            )
            with pytest.raises(ValueError, match="cross notebook"):
                await store.list_authorized_multilingual_embeddings_v3(
                    notebook_id=uuid4(),
                    generation_id=profile.generation_id,
                    vector_space=profile.vector_space,
                    authorized_sources=(source,),
                )
            with pytest.raises(ValueError, match="must be unique"):
                await store.list_authorized_multilingual_embeddings_v3(
                    notebook_id=source.notebook_id,
                    generation_id=profile.generation_id,
                    vector_space=profile.vector_space,
                    authorized_sources=(source, source),
                )
            with pytest.raises(ValueError, match="exceeds 10000"):
                await store.list_authorized_multilingual_embeddings_v3(
                    notebook_id=source.notebook_id,
                    generation_id=profile.generation_id,
                    vector_space=profile.vector_space,
                    authorized_sources=(source,) * 10_001,
                )
        finally:
            await store.close()

    asyncio.run(scenario())


class _UnavailableDense:
    async def retrieve(self, **_: object) -> object:
        raise LookupError("dense generation not active")


class _Sparse:
    def __init__(self, source: LanguageEvidenceReferenceV3) -> None:
        self.source = source
        self.last_decision: V2RetrievalAuthorizationDecisionV1 | None = None

    async def retrieve_authorized_multilingual_sparse(
        self, **kwargs: object
    ) -> tuple[MultilingualSparseMatchV2, ...]:
        decision = kwargs["decision"]
        assert isinstance(decision, V2RetrievalAuthorizationDecisionV1)
        self.last_decision = decision
        return (MultilingualSparseMatchV2(source=self.source, score=1.0, rank=1),)


class _Authorizer:
    async def authorize_language_evidence_v3(
        self, actor_id: UUID, source: LanguageEvidenceReferenceV3
    ) -> AuthorizationScopeV1:
        del actor_id
        return _scope(source)


class _RetrievalAuthorizer:
    def __init__(self) -> None:
        self.last_decision: V2RetrievalAuthorizationDecisionV1 | None = None

    async def authorize_v2_retrieval(
        self, *, principal: PrincipalContextV1, plan: RetrievalPlanV2
    ) -> V2RetrievalAuthorizationDecisionV1:
        self.last_decision = V2RetrievalAuthorizationDecisionV1(
            decision_id=uuid4(),
            principal_actor_id=principal.actor_id,
            operation="retrieve",
            retrieval_scope=plan.scope,
            positional_scope=plan.position,
            runtime_binding=V2ActiveRuntimeBindingV1(
                alias_set_digest=ZERO,
                generation_ids=tuple(uuid4() for _ in range(4)),
                profile_fingerprint=ZERO,
                vector_space_identity=ZERO,
                database_identity=ZERO,
                build_run_id=uuid4(),
                admission_policy_identity="fixture-admission/1",
            ),
            authorization_policy_identity="fixture-central-v2/1",
            authorization_policy_revision="1",
            request_fingerprint=ZERO,
            issued_at="fixture",
            required_provenance_evidence=("language-evidence-reference-v3",),
        )
        return self.last_decision


class _Reranker:
    async def score_candidates(
        self,
        *,
        query: str,
        candidates: tuple[MultilingualRerankCandidateV3, ...],
    ) -> tuple[MultilingualRerankScoreV2, ...]:
        del query
        candidate = candidates[0]
        return (
            MultilingualRerankScoreV2(
                candidate_id=candidate.candidate_id,
                score=0.9,
                model="BAAI/bge-reranker-v2-m3",
                revision="exact-revision",
                preprocessing="pair-256-v2",
            ),
        )


class _Admission:
    def permits(self, *, language: LanguageCode, operation: str) -> bool:
        return language == LanguageCode("mr") and operation in {
            "dense_retrieval",
            "sparse_retrieval",
            "reranking",
        }


class _ProjectionQueryResolver:
    async def resolve_query_language(self, **_: object) -> LanguageCode:
        return LanguageCode("mr")


class _ProjectionFallback:
    @property
    def representation(self) -> EvidenceRepresentation:
        return EvidenceRepresentation.MULTILINGUAL_TEXT

    async def retrieve(self, *_: object, **__: object) -> object:
        raise AssertionError("projection contract test does not retrieve")

    async def expand(self, *_: object, **__: object) -> tuple[object, ...]:
        return ()


class _DecisionProjector:
    def __init__(self) -> None:
        self.last_decision: V2RetrievalAuthorizationDecisionV1 | None = None

    async def project_advanced_candidate(
        self,
        *,
        value: object,
        decision: V2RetrievalAuthorizationDecisionV1,
    ) -> AdvancedRetrievalCandidate:
        assert hasattr(value, "candidate")
        self.last_decision = decision
        candidate = value.candidate
        source = candidate.source_reference
        occurrence_id = uuid4()
        return AdvancedRetrievalCandidate(
            candidate_id=advanced_candidate_id(
                representation=EvidenceRepresentation.MULTILINGUAL_TEXT,
                document_id=source.document_id,
                version_id=source.version_id,
                chunk_id=None,
                occurrence_id=occurrence_id,
                derivation_id=None,
            ),
            notebook_id=source.notebook_id,
            source_id=source.source_id,
            document_id=source.document_id,
            version_id=source.version_id,
            representation=EvidenceRepresentation.MULTILINGUAL_TEXT,
            chunk=None,
            occurrence_id=occurrence_id,
            derivation_id=None,
            locator=FrozenMetadata(
                {
                    "evidence_reference_digest": source.identity_digest,
                    "representation_reference_id": str(
                        candidate.representation_reference.reference_id
                    ),
                }
            ),
            document_title=None,
            content=candidate.semantic_text,
            paths=(RetrievalPathEvidenceV2(path="sparse", source_rank=1, source_score=1.0),),
        )


def test_shared_v2_path_uses_candidate_builder_and_reports_degradation() -> None:
    async def scenario() -> None:
        text = "actual sparse semantic evidence"
        source = _source(text)
        resolver = _Resolver(source, text, "title metadata")
        sparse = _Sparse(source)
        authorizer = _RetrievalAuthorizer()
        builder = RerankerCandidateBuilderV1(
            resolver=resolver,
            tokenizer=_Tokenizer(),
            provider_id="sentence-transformers",
            model_id="BAAI/bge-reranker-v2-m3",
            model_revision="exact-revision",
            provider_configuration_digest=ZERO,
            query_preprocessing_identity="query-v1",
            document_preprocessing_identity="document-v1",
            preprocess_query=lambda value: value,
            preprocess_document=lambda value: value,
        )
        app = FullMultilingualRetrievalApplicationV2(
            dense=_UnavailableDense(),
            sparse=sparse,
            retrieval_authorizer=authorizer,
            candidate_builder=builder,
            reranker=_Reranker(),
            admission=_Admission(),
        )
        plan = RetrievalPlanV2(
            query="semantic evidence",
            mode=AdvancedRetrievalMode.RANKED,
            scope=RetrievalScopeV2(notebook_id=source.notebook_id),
            representations=(EvidenceRepresentation.MULTILINGUAL_TEXT,),
            budgets=RetrievalBudgetsV2(
                recall_limit=10,
                expansion_limit=0,
                fusion_limit=10,
                rerank_limit=10,
                result_limit=5,
                max_serialized_bytes=100_000,
                max_content_characters=10_000,
            ),
            ranking_policy=RankingPolicyV2.SOURCE_RANK_FUSION,
        )
        result = await app.retrieve(
            principal=PrincipalContextV1(actor_id=uuid4(), authenticated=True),
            plan=plan,
            query_language=LanguageCode("mr"),
        )
        assert result.completeness == "partial"
        assert result.candidates[0].candidate.semantic_text == text
        assert result.candidates[0].reranker_score == 0.9
        assert result.omissions == ("dense_unavailable:LookupError",)
        decision = result.candidates[0].authorization_decision
        assert decision is authorizer.last_decision
        assert decision is sparse.last_decision
        assert decision is resolver.last_decision
        assert result.candidates[0].candidate.provenance.authorization_scope_digest == (
            decision.decision_fingerprint
        )
        projector = _DecisionProjector()
        advanced = FullMultilingualAdvancedSourceV2(
            application=app,
            query_language_resolver=_ProjectionQueryResolver(),
            projector=projector,
            exhaustive_fallback=_ProjectionFallback(),
        )
        assert advanced.representation is EvidenceRepresentation.MULTILINGUAL_TEXT
        projected = await advanced._project_and_validate(result.candidates[0])
        assert projector.last_decision is decision
        assert projected.content == text
        with pytest.raises(PermissionError, match="server-owned principal"):
            await advanced.retrieve(plan, offset=0, limit=1)
        with pytest.raises(ValueError, match="does not support offsets"):
            await advanced.retrieve_authorized(
                principal=PrincipalContextV1(actor_id=uuid4(), authenticated=True),
                plan=plan,
                offset=1,
                limit=1,
            )
        authorized_page = await advanced.retrieve_authorized(
            principal=PrincipalContextV1(actor_id=uuid4(), authenticated=True),
            plan=plan,
            offset=0,
            limit=1,
        )
        assert authorized_page.representation is EvidenceRepresentation.MULTILINGUAL_TEXT
        assert authorized_page.next_offset is None
        assert await advanced.expand(plan, (), limit=1) == ()

        for field in ("query_language_resolver", "projector"):
            kwargs = {
                "application": app,
                "query_language_resolver": _ProjectionQueryResolver(),
                "projector": _DecisionProjector(),
                "exhaustive_fallback": _ProjectionFallback(),
            }
            kwargs[field] = object()
            with pytest.raises(TypeError, match="does not implement"):
                FullMultilingualAdvancedSourceV2(**kwargs)  # type: ignore[arg-type]
        wrong_fallback = SimpleNamespace(representation=EvidenceRepresentation.CANONICAL_TEXT)
        with pytest.raises(ValueError, match="wrong representation"):
            FullMultilingualAdvancedSourceV2(
                application=app,
                query_language_resolver=_ProjectionQueryResolver(),
                projector=_DecisionProjector(),
                exhaustive_fallback=wrong_fallback,  # type: ignore[arg-type]
            )

    asyncio.run(scenario())


def test_generic_mapping_transformation_preserves_source_and_lineage() -> None:
    async def scenario() -> None:
        source_text = "ab"
        source = _source(source_text)
        observation_id = uuid4()
        source_representation = TextRepresentationReferenceV1(
            reference_id=text_representation_reference_id(
                evidence_reference_digest=source.identity_digest,
                representation_type=TextRepresentationType.LEGACY_FONT_ENCODED_TEXT,
                authority=RepresentationAuthority.ORIGINAL,
                content_hash=content_hash(source_text),
                observation_id=observation_id,
                derivation_id=None,
                source_generation_ids=(),
            ),
            evidence_reference=source,
            representation_type=TextRepresentationType.LEGACY_FONT_ENCODED_TEXT,
            representation_authority=RepresentationAuthority.ORIGINAL,
            content_hash=content_hash(source_text),
            representation_observation_id=observation_id,
            representation_derivation_id=None,
            source_generation_ids=(),
            language_observation_references=(),
            script_observation_references=(),
        )
        transformer = GovernedMappingRepresentationTransformerV1(
            mapping={"a": "अ", "b": "ब"},
            unmapped_policy="reject_unmapped",
        )
        await transformer.initialize()
        profile = TransformationProfileV1(
            profile_id="fixture-legacy-to-unicode-v1",
            provider_id="governed-mapping-transformer-v1",
            provider_revision="1",
            configuration_digest=transformer.configuration_digest,
            allowed_source_representations=(TextRepresentationType.LEGACY_FONT_ENCODED_TEXT,),
            target_representation=TextRepresentationType.UNICODE_SEMANTIC_TEXT,
        )
        detector = ConfiguredRepresentationDetectorV1(
            detector_id="fixture-representation-detector",
            detector_revision="1",
            configuration_digest=ZERO,
            classify=lambda _: RepresentationDetectionResultV1(
                representation_type=TextRepresentationType.LEGACY_FONT_ENCODED_TEXT,
                confidence=1.0,
                calibrated=False,
                authority_class=RepresentationAuthorityClass.GOVERNED_DETECTOR,
            ),
        )
        pipeline = RepresentationPipelineV1(
            detector=detector,
            authorizer=_Authorizer(),
            registry=DeterministicTransformationRegistryV1(
                (
                    (
                        TransformationRegistryEntryV1(
                            profile=profile,
                            implementation_id="governed-mapping-transformer-v1",
                            configured=True,
                            provider_ready=True,
                            enabled=True,
                            reason_code=None,
                        ),
                        transformer,
                    ),
                )
            ),
        )
        _, observation = await pipeline.observe(actor_id=uuid4(), source=source, text=source_text)
        output, transformation = await pipeline.transform(
            actor_id=uuid4(),
            source=source,
            source_text=source_text,
            source_representation=source_representation,
            observation=observation,
            generation_id=uuid4(),
            target_profile_id=profile.profile_id,
        )
        assert output == "अब"
        assert source_text == "ab"
        assert transformation.provenance.source_reference_digest == source.identity_digest
        parent_digest = (
            transformation.output_reference.evidence_reference.parent_evidence_reference_digest
        )
        assert parent_digest == source.identity_digest

    asyncio.run(scenario())


def test_representation_components_fail_closed_across_configuration_and_scope() -> None:
    source_text = "ab"
    source = _source(source_text)
    source_reference = _representation(source, source_text)
    unmapped_text = "a?"
    unmapped_reference = _representation(source, unmapped_text)
    observation = ConfiguredRepresentationDetectorV1(
        detector_id="detector",
        detector_revision="1",
        configuration_digest=ZERO,
        classify=lambda _: RepresentationDetectionResultV1(
            representation_type=TextRepresentationType.UNICODE_SEMANTIC_TEXT,
            confidence=1.0,
            calibrated=True,
            authority_class=RepresentationAuthorityClass.GOVERNED_DETECTOR,
        ),
    )
    with pytest.raises(TypeError, match="classifier"):
        ConfiguredRepresentationDetectorV1(
            detector_id="detector",
            detector_revision="1",
            configuration_digest=ZERO,
            classify=object(),
        )

    async def detector_contracts() -> None:
        with pytest.raises(PermissionError, match="scope conflicts"):
            await observation.observe(
                actor_id=uuid4(),
                source=source,
                text=source_text,
                authorization_scope=replace(_scope(source), notebook_id=uuid4()),
            )
        with pytest.raises(ValueError, match="text conflicts"):
            await observation.observe(
                actor_id=uuid4(),
                source=source,
                text="different",
                authorization_scope=_scope(source),
            )
        invalid = ConfiguredRepresentationDetectorV1(
            detector_id="detector",
            detector_revision="1",
            configuration_digest=ZERO,
            classify=lambda _: object(),
        )
        with pytest.raises(TypeError, match="invalid result"):
            await invalid.observe(
                actor_id=uuid4(),
                source=source,
                text=source_text,
                authorization_scope=_scope(source),
            )

    asyncio.run(detector_contracts())

    invalid_configurations = (
        ({}, "preserve_unmapped"),
        ({"": "x"}, "preserve_unmapped"),
        ({"a": ""}, "preserve_unmapped"),
        ({"a": "b"}, "unknown"),
    )
    for mapping, policy in invalid_configurations:
        with pytest.raises(ValueError):
            GovernedMappingRepresentationTransformerV1(mapping=mapping, unmapped_policy=policy)

    transformer = GovernedMappingRepresentationTransformerV1(
        mapping={"ab": "X", "a": "Y"}, unmapped_policy="reject_unmapped"
    )
    profile = TransformationProfileV1(
        profile_id="profile",
        provider_id="mapping",
        provider_revision="1",
        configuration_digest=transformer.configuration_digest,
        allowed_source_representations=(TextRepresentationType.UNICODE_SEMANTIC_TEXT,),
        target_representation=TextRepresentationType.NORMALIZED_UNICODE_TEXT,
    )
    entry = TransformationRegistryEntryV1(
        profile=profile,
        implementation_id="mapping",
        configured=True,
        provider_ready=True,
        enabled=True,
        reason_code=None,
    )
    registry = DeterministicTransformationRegistryV1(((entry, transformer),))
    assert registry.entries() == (entry,)
    assert registry.resolve(entry) is transformer
    with pytest.raises(ValueError, match="duplicate"):
        DeterministicTransformationRegistryV1(((entry, transformer), (entry, transformer)))
    with pytest.raises(TypeError, match="does not implement"):
        DeterministicTransformationRegistryV1(((entry, object()),))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not registered"):
        registry.resolve(replace(entry, enabled=False))
    assert (
        registry.select(
            observation=SimpleNamespace(representation_type=TextRepresentationType.MIXED)
        )
        is None
    )  # type: ignore[arg-type]
    assert (
        registry.select(
            observation=SimpleNamespace(
                representation_type=TextRepresentationType.UNICODE_SEMANTIC_TEXT
            ),
            target_profile_id="absent",
        )
        is None
    )  # type: ignore[arg-type]

    async def transformer_contracts() -> None:
        with pytest.raises(RuntimeError, match="not initialized"):
            await transformer.transform(
                actor_id=uuid4(),
                source=source_reference,
                source_text=source_text,
                observation=SimpleNamespace(),
                profile=profile,
                authorization_scope=_scope(source),  # type: ignore[arg-type]
            )
        await transformer.initialize()
        assert await transformer.ready()
        with pytest.raises(ValueError, match="configuration differs"):
            await transformer.transform(
                actor_id=uuid4(),
                source=source_reference,
                source_text=source_text,
                observation=SimpleNamespace(),
                profile=replace(profile, configuration_digest="f" * 64),
                authorization_scope=_scope(source),  # type: ignore[arg-type]
            )
        with pytest.raises(ValueError, match="not admitted"):
            await transformer.transform(
                actor_id=uuid4(),
                source=source_reference,
                source_text=source_text,
                observation=SimpleNamespace(),
                profile=replace(
                    profile,
                    allowed_source_representations=(TextRepresentationType.MIXED,),
                ),
                authorization_scope=_scope(source),  # type: ignore[arg-type]
            )
        with pytest.raises(ValueError, match="content hash mismatch"):
            await transformer.transform(
                actor_id=uuid4(),
                source=source_reference,
                source_text="different",
                observation=SimpleNamespace(),
                profile=profile,
                authorization_scope=_scope(source),  # type: ignore[arg-type]
            )
        assert (
            await transformer.transform(
                actor_id=uuid4(),
                source=source_reference,
                source_text=source_text,
                observation=SimpleNamespace(),
                profile=profile,
                authorization_scope=_scope(source),  # type: ignore[arg-type]
            )
            == "X"
        )
        with pytest.raises(ValueError, match="unmapped"):
            await transformer.transform(
                actor_id=uuid4(),
                source=unmapped_reference,
                source_text=unmapped_text,
                observation=SimpleNamespace(),
                profile=profile,
                authorization_scope=_scope(source),  # type: ignore[arg-type]
            )
        await transformer.close()
        assert not await transformer.ready()

    asyncio.run(transformer_contracts())
