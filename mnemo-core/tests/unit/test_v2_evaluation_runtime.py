from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from mnemo.models.advanced_retrieval import EvidenceRepresentation
from mnemo.models.multilingual import LanguageCode
from mnemo.phase85.v2_database_identity import V2VectorEmbeddingGenerationBindingV1
from mnemo.phase85.v2_evaluation_runtime import (
    FullMultilingualV2EvaluationRuntimeFactory,
    InternalFullMultilingualV2Evaluator,
    V2RuntimeCompositionDependencies,
    V2RuntimeCompositionError,
    V2RuntimeIdentityV1,
)
from mnemo.phase85.v2_readiness import V2GenerationCapability, V2GenerationEvidence

_DIGEST = "a" * 64
_PROFILE = "full_multilingual_v2_local_prebuild"
_VECTOR = "b" * 64


class _ActiveStore:
    def __init__(self, ids: tuple[UUID, ...] | None) -> None:
        self.ids = ids

    async def resolve_active_multilingual_v2_generation_set(self) -> tuple[UUID, ...] | None:
        return self.ids


class _Inspector:
    def __init__(self, evidence: tuple[V2GenerationEvidence, ...]) -> None:
        self.evidence = evidence

    async def inspect_active_v2_generations(
        self, generation_ids: tuple[UUID, ...]
    ) -> tuple[V2GenerationEvidence, ...]:
        assert {item.generation_id for item in self.evidence} == set(generation_ids)
        return self.evidence


class _Enumerator:
    async def enumerate_authorized_multilingual_sources(self, **_: object) -> tuple[object, ...]:
        return ()


class _Store:
    async def list_authorized_multilingual_embeddings_v3(self, **_: object) -> tuple[object, ...]:
        return ()

    async def search_authorized_multilingual_text_v2(self, **_: object) -> tuple[object, ...]:
        return ()


class _Embedder:
    async def embed_query(self, **_: object) -> object:
        raise AssertionError("composition must not issue provider inference")


class _RetrievalAuthorizer:
    async def authorize_v2_retrieval(self, **_: object) -> object:
        raise AssertionError("composition must not authorize retrieval")


class _Builder:
    async def build(self, **_: object) -> object:
        raise AssertionError("composition must not construct candidates")


class _Reranker:
    async def score_candidates(self, **_: object) -> tuple[object, ...]:
        raise AssertionError("composition must not rerank")


class _Admission:
    def permits(self, *, language: LanguageCode, operation: str) -> bool:
        return language.value == "und" and bool(operation)


class _QueryResolver:
    async def resolve_query_language(self, **_: object) -> LanguageCode:
        return LanguageCode("und")


class _Projector:
    async def project_advanced_candidate(self, **_: object) -> object:
        raise AssertionError("composition must not project candidates")


class _Fallback:
    @property
    def representation(self) -> EvidenceRepresentation:
        return EvidenceRepresentation.MULTILINGUAL_TEXT

    async def retrieve(self, **_: object) -> object:
        raise AssertionError("composition must not retrieve")

    async def expand(self, **_: object) -> tuple[object, ...]:
        return ()


def _identity() -> V2RuntimeIdentityV1:
    return V2RuntimeIdentityV1(
        profile_id=_PROFILE,
        profile_fingerprint=_DIGEST,
        vector_space_identity=_VECTOR,
        build_run_id=uuid4(),
        database_identity="c" * 64,
        alias_set_digest="d" * 64,
        query_preprocessing_identity="bge-m3-query-v1",
        document_preprocessing_identity="bge-m3-document-v1",
        authorization_service_id="central-authorization-v3",
        provenance_validator_id="provenance-validator-v1",
        reranker_public_protocol_id="mnemo.multilingual-reranker-v3",
        provider_identity="sentence-transformers",
    )


def _evidence(ids: tuple[UUID, ...], *, vector: str = _VECTOR) -> tuple[V2GenerationEvidence, ...]:
    values = (
        V2GenerationCapability.REPRESENTATION_DERIVATION,
        V2GenerationCapability.LANGUAGE_TEXT,
        V2GenerationCapability.MULTILINGUAL_EMBEDDING,
        V2GenerationCapability.MULTILINGUAL_VECTOR,
    )
    return tuple(
        V2GenerationEvidence(
            capability=capability,
            generation_id=generation_id,
            profile_id=_PROFILE,
            provider_identity="provider",
            model_identity="model",
            configuration_digest=_DIGEST,
            vector_space_identity=(
                vector
                if capability
                in {
                    V2GenerationCapability.MULTILINGUAL_EMBEDDING,
                    V2GenerationCapability.MULTILINGUAL_VECTOR,
                }
                else None
            ),
            state="ready",
            coverage_completeness="complete",
            item_count=1,
            coverage_count=1,
            checksum=_DIGEST,
            coverage_checksum=_DIGEST,
            source_generation_ids=(ids[2],) if capability == values[3] else (),
            language_coverage_digest=_DIGEST,
            script_coverage_digest=_DIGEST,
            representation_coverage_digest=_DIGEST,
            provenance_digest=_DIGEST,
        )
        for capability, generation_id in zip(values, ids, strict=True)
    )


class _DatabaseIdentityVerifier:
    def __init__(self, *, identity: V2RuntimeIdentityV1, ids: tuple[UUID, ...]) -> None:
        self._identity = identity
        self._ids = ids

    def verify(self, *, expected_database_identity: str) -> None:
        assert expected_database_identity == self._identity.database_identity

    def resolve_vector_embedding_generation(
        self,
        *,
        active_generation_ids: tuple[UUID, ...],
        expected_database_identity: str,
    ) -> V2VectorEmbeddingGenerationBindingV1:
        assert active_generation_ids == self._ids
        assert expected_database_identity == self._identity.database_identity
        return V2VectorEmbeddingGenerationBindingV1(
            vector_generation_id=self._ids[3],
            embedding_generation_id=self._ids[2],
            model_identity="model",
            vector_space_identity=self._identity.vector_space_identity,
            dimensions=1024,
            embedding_configuration_digest=_DIGEST,
            vector_configuration_digest=_DIGEST,
            database_identity=self._identity.database_identity,
            build_run_id=self._identity.build_run_id,
        )


def _factory(ids: tuple[UUID, ...] | None, evidence: tuple[V2GenerationEvidence, ...]):
    identity = _identity()
    verifier_ids = ids if ids is not None else tuple(value.generation_id for value in evidence)
    return FullMultilingualV2EvaluationRuntimeFactory(
        identity=identity,
        dependencies=V2RuntimeCompositionDependencies(
            active_store=_ActiveStore(ids),
            generation_inspector=_Inspector(evidence),
            database_identity_verifier=_DatabaseIdentityVerifier(
                identity=identity, ids=verifier_ids
            ),
            source_enumerator=_Enumerator(),
            embedding_store=_Store(),
            text_store=_Store(),
            query_embedder=_Embedder(),
            retrieval_authorizer=_RetrievalAuthorizer(),
            candidate_builder=_Builder(),
            reranker=_Reranker(),
            admission=_Admission(),
            query_language_resolver=_QueryResolver(),
            projector=_Projector(),
            exhaustive_fallback=_Fallback(),
        ),
    )


def test_factory_composes_only_active_alias_and_exposes_no_provider_handles() -> None:
    ids = tuple(uuid4() for _ in range(4))
    runtime = asyncio.run(_factory(ids, _evidence(ids)).compose())

    assert runtime.generation_ids == ids
    assert runtime.parity.direct_provider_calls is False
    assert runtime.parity.caller_constructed_reranker_input is False
    evaluator = InternalFullMultilingualV2Evaluator(runtime)
    assert evaluator.runtime_parity == runtime.parity
    assert not hasattr(evaluator, "provider")
    assert not hasattr(evaluator, "store")


def test_factory_rejects_missing_active_alias_before_any_provider_work() -> None:
    ids = tuple(uuid4() for _ in range(4))
    with pytest.raises(V2RuntimeCompositionError, match="ACTIVE_ALIAS_MISSING"):
        asyncio.run(_factory(None, _evidence(ids)).compose())


def test_factory_rejects_vector_space_mismatch_before_any_provider_work() -> None:
    ids = tuple(uuid4() for _ in range(4))
    with pytest.raises(V2RuntimeCompositionError, match="VECTOR_SPACE_MISMATCH"):
        asyncio.run(_factory(ids, _evidence(ids, vector="e" * 64)).compose())
