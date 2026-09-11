"""Provider-neutral Phase 8.5.9 multilingual contracts."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.interfaces.scope import PrincipalContextV1
from mnemo.models.advanced_retrieval import RetrievalPlanV2
from mnemo.models.multilingual import (
    LanguageDerivation,
    LanguageEvidenceReferenceV2,
    LanguageEvidenceReferenceV3,
    LanguageObservation,
    LanguageObservationV2,
    LanguageProviderProfile,
    LanguageTransformationRequest,
    LanguageTransformationRequestV2,
    MultilingualCandidate,
    MultilingualEmbedding,
    MultilingualEmbeddingInputV2,
    MultilingualEmbeddingProfile,
    MultilingualFinalQARequest,
    MultilingualFinalQAResult,
    MultilingualProviderReadinessV2,
    MultilingualQueryEmbeddingV2,
    MultilingualRerankScoreV2,
    MultilingualRetrievalPath,
    MultilingualRetrievalPlan,
    MultilingualRetrievalResult,
    ScriptObservationV1,
)
from mnemo.models.multilingual_embeddings import (
    MultilingualEmbeddingInputV3,
    MultilingualEmbeddingV3,
)
from mnemo.models.multilingual_reranking import (
    AuthorizedRerankerEvidenceV1,
    MultilingualRerankCandidateV3,
)
from mnemo.models.multimodal import EvidenceCandidateV2
from mnemo.models.text_representations import AuthorizationScopeV1
from mnemo.models.v2_retrieval_authorization import V2RetrievalAuthorizationDecisionV1


@runtime_checkable
class LanguageDetectorV1(Protocol):  # pragma: no cover
    async def detect(
        self,
        *,
        actor_id: UUID,
        notebook_id: UUID,
        target_id: str,
        text: str,
        document_id: UUID | None = None,
        version_id: UUID | None = None,
    ) -> LanguageObservation: ...


@runtime_checkable
class LanguageDetectorProviderV2(Protocol):  # pragma: no cover
    @property
    def detector_id(self) -> str: ...

    @property
    def detector_revision(self) -> str: ...

    @property
    def configuration_digest(self) -> str: ...

    async def detect_languages(
        self,
        *,
        actor_id: UUID,
        notebook_id: UUID,
        target_id: str,
        text: str,
        source: LanguageEvidenceReferenceV3 | None = None,
    ) -> LanguageObservationV2: ...


@runtime_checkable
class ScriptDetectorV1(Protocol):  # pragma: no cover
    @property
    def detector_id(self) -> str: ...

    @property
    def detector_revision(self) -> str: ...

    @property
    def configuration_digest(self) -> str: ...

    async def detect_scripts(
        self,
        *,
        actor_id: UUID,
        notebook_id: UUID,
        target_id: str,
        text: str,
        source: LanguageEvidenceReferenceV3 | None = None,
    ) -> ScriptObservationV1: ...


@runtime_checkable
class LanguageEvidenceAuthorizerV2(Protocol):  # pragma: no cover
    async def authorize_language_evidence(
        self, actor_id: UUID, source: LanguageEvidenceReferenceV2
    ) -> bool: ...


@runtime_checkable
class RepresentationEvidenceAuthorizerV3(Protocol):  # pragma: no cover
    """Legacy-shaped representation-pipeline authorization; not V2 retrieval authority."""

    async def authorize_language_evidence_v3(
        self, actor_id: UUID, source: LanguageEvidenceReferenceV3
    ) -> AuthorizationScopeV1 | None: ...


# Backward-compatible public name. RepresentationPipelineV1 keeps its exact behavior.
LanguageEvidenceAuthorizerV3 = RepresentationEvidenceAuthorizerV3


@runtime_checkable
class V2RetrievalAuthorizerV1(Protocol):  # pragma: no cover
    """Distinct bounded V2 port: server principal in, immutable decision out."""

    async def authorize_v2_retrieval(
        self,
        *,
        principal: PrincipalContextV1,
        plan: RetrievalPlanV2,
    ) -> V2RetrievalAuthorizationDecisionV1: ...


@runtime_checkable
class LanguageEvidenceCatalogV2(Protocol):  # pragma: no cover
    """Returns only sources already authorized for the actor and scope."""

    async def authorized_language_sources(
        self, *, actor_id: UUID, notebook_id: UUID, limit: int
    ) -> tuple[LanguageEvidenceReferenceV2, ...]: ...

    async def resolve_language_evidence(
        self, *, actor_id: UUID, source: LanguageEvidenceReferenceV2
    ) -> EvidenceCandidateV2: ...


@runtime_checkable
class LanguageTransformationProviderV1(Protocol):  # pragma: no cover
    async def capabilities(self) -> LanguageProviderProfile: ...

    async def transform(self, request: LanguageTransformationRequest) -> LanguageDerivation: ...


@runtime_checkable
class LanguageTransformationProviderV2(Protocol):  # pragma: no cover
    async def initialize(self) -> None: ...

    async def close(self) -> None: ...

    async def readiness(self) -> MultilingualProviderReadinessV2: ...

    async def capabilities(self) -> LanguageProviderProfile: ...

    async def transform(self, request: LanguageTransformationRequestV2) -> LanguageDerivation: ...


@runtime_checkable
class MultilingualEmbeddingProviderV1(Protocol):  # pragma: no cover
    async def profile(self) -> MultilingualEmbeddingProfile: ...

    async def embed(
        self,
        *,
        notebook_id: UUID,
        source_evidence_id: str,
        text: str,
        language: str,
    ) -> MultilingualEmbedding: ...


@runtime_checkable
class MultilingualEmbeddingProviderV2(Protocol):  # pragma: no cover
    """Frozen query/document distinction and ordered batch contract."""

    async def initialize(self) -> None: ...

    async def close(self) -> None: ...

    async def readiness(self) -> MultilingualProviderReadinessV2: ...

    async def profile(self) -> MultilingualEmbeddingProfile: ...

    async def embed_query(self, *, query: str, language: str) -> MultilingualQueryEmbeddingV2: ...

    async def embed_documents(
        self, inputs: tuple[MultilingualEmbeddingInputV2, ...]
    ) -> tuple[MultilingualEmbedding, ...]: ...


@runtime_checkable
class MultilingualEmbeddingProviderV3(MultilingualEmbeddingProviderV2, Protocol):
    async def embed_documents_v3(
        self, inputs: tuple[MultilingualEmbeddingInputV3, ...]
    ) -> tuple[MultilingualEmbeddingV3, ...]: ...


@runtime_checkable
class MultilingualCandidateRerankerV1(Protocol):  # pragma: no cover
    async def profile(self) -> LanguageProviderProfile: ...

    async def rerank(
        self, query: str, candidates: tuple[MultilingualCandidate, ...]
    ) -> tuple[UUID, ...]: ...


@runtime_checkable
class MultilingualCandidateRerankerV2(Protocol):  # pragma: no cover
    async def initialize(self) -> None: ...

    async def close(self) -> None: ...

    async def readiness(self) -> MultilingualProviderReadinessV2: ...

    async def profile(self) -> LanguageProviderProfile: ...

    async def score(
        self, query: str, candidates: tuple[MultilingualCandidate, ...]
    ) -> tuple[MultilingualRerankScoreV2, ...]: ...


@runtime_checkable
class RerankerEvidenceResolverV1(Protocol):  # pragma: no cover
    async def resolve_reranker_evidence(
        self,
        *,
        source: LanguageEvidenceReferenceV3,
        decision: V2RetrievalAuthorizationDecisionV1,
        retrieval_paths: tuple[str, ...],
        fusion_rank: int,
    ) -> AuthorizedRerankerEvidenceV1: ...


@runtime_checkable
class RerankerCandidateBuilderProtocolV1(Protocol):  # pragma: no cover
    async def build(
        self,
        *,
        query: str,
        source: LanguageEvidenceReferenceV3,
        decision: V2RetrievalAuthorizationDecisionV1,
        input_ordinal: int,
        retrieval_paths: tuple[str, ...],
    ) -> MultilingualRerankCandidateV3: ...


@runtime_checkable
class MultilingualCandidateRerankerV3(Protocol):  # pragma: no cover
    async def score_candidates(
        self,
        *,
        query: str,
        candidates: tuple[MultilingualRerankCandidateV3, ...],
    ) -> tuple[MultilingualRerankScoreV2, ...]: ...


@runtime_checkable
class MultilingualStoreV2(Protocol):  # pragma: no cover
    async def put_language_observation_v2(self, observation: LanguageObservationV2) -> bool: ...

    async def put_script_observation_v1(self, observation: ScriptObservationV1) -> bool: ...

    async def put_multilingual_embedding_v3(self, embedding: MultilingualEmbeddingV3) -> bool: ...

    async def list_authorized_multilingual_embeddings_v3(
        self,
        *,
        notebook_id: UUID,
        generation_id: UUID,
        vector_space: str,
        authorized_sources: tuple[LanguageEvidenceReferenceV3, ...],
    ) -> tuple[MultilingualEmbeddingV3, ...]: ...


@runtime_checkable
class MultilingualRetrievalSourceV1(Protocol):  # pragma: no cover
    async def retrieve(
        self,
        plan: MultilingualRetrievalPlan,
        selection: MultilingualRetrievalPath,
        target_language: str,
        limit: int,
    ) -> tuple[MultilingualCandidate, ...]: ...


@runtime_checkable
class MultilingualRetrievalInterfaceV1(Protocol):  # pragma: no cover
    async def execute(self, plan: MultilingualRetrievalPlan) -> MultilingualRetrievalResult: ...


@runtime_checkable
class MultilingualStoreV1(Protocol):  # pragma: no cover
    async def put_language_observation(self, observation: LanguageObservation) -> bool: ...

    async def get_authorized_language_observation(
        self, *, actor_id: UUID, notebook_id: UUID, observation_id: UUID
    ) -> LanguageObservation | None: ...

    async def put_language_derivation(self, derivation: LanguageDerivation) -> bool: ...

    async def get_authorized_language_derivation(
        self, *, actor_id: UUID, notebook_id: UUID, derivation_id: UUID
    ) -> LanguageDerivation | None: ...

    async def get_authorized_language_derivation_by_cache_key(
        self, *, actor_id: UUID, notebook_id: UUID, cache_key: str
    ) -> LanguageDerivation | None: ...

    async def put_multilingual_embedding(self, embedding: MultilingualEmbedding) -> bool: ...

    async def get_authorized_multilingual_embedding(
        self, *, notebook_id: UUID, embedding_id: UUID
    ) -> MultilingualEmbedding | None: ...

    async def list_authorized_multilingual_embeddings(
        self,
        *,
        notebook_id: UUID,
        generation_id: UUID,
        vector_space: str,
        authorized_sources: tuple[LanguageEvidenceReferenceV2, ...],
    ) -> tuple[MultilingualEmbedding, ...]: ...


@runtime_checkable
class MultilingualFinalQAInterfaceV1(Protocol):  # pragma: no cover
    async def execute(self, request: MultilingualFinalQARequest) -> MultilingualFinalQAResult: ...
