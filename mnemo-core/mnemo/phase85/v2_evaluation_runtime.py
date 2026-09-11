"""Internal-only composition of the active Full Multilingual V2 retrieval path.

This module deliberately does not register a public transport capability.  It
binds only the active V2 alias set and pre-constructed central dependencies for
controlled evaluation.  Callers cannot select generations or replace the
vector space through this interface.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.interfaces.multilingual import (
    MultilingualCandidateRerankerV3,
    RerankerCandidateBuilderProtocolV1,
    V2RetrievalAuthorizerV1,
)
from mnemo.models.multilingual_evaluation import RuntimeParityEvidenceV1
from mnemo.models.multilingual_reranking import V2_TYPED_CANDIDATE_BUILDER_ID
from mnemo.phase85.v2_database_identity import V2VectorEmbeddingGenerationBindingV1
from mnemo.phase85.v2_readiness import V2GenerationCapability, V2GenerationEvidence
from mnemo.retrieval.full_multilingual_advanced_v2 import (
    FullMultilingualAdvancedSourceV2,
    QueryLanguageResolverV2,
    V2AdvancedCandidateProjector,
)
from mnemo.retrieval.full_multilingual_v2 import (
    FullMultilingualRetrievalApplicationV2,
    MultilingualOperationAdmissionV2,
)
from mnemo.retrieval.multilingual_dense_v2 import (
    AuthorizedMultilingualDenseRetrievalV2,
    AuthorizedMultilingualSourceEnumeratorV2,
    MultilingualEmbeddingStoreV2,
    MultilingualQueryEmbedderV2,
)
from mnemo.retrieval.multilingual_sparse_v2 import (
    AuthorizedMultilingualSparseRetrievalV2,
    MultilingualTextProjectionStoreV2,
)


class V2RuntimeCompositionError(RuntimeError):
    """Fail-closed error raised before a V2 query can reach a provider."""


_CAPABILITY_ORDER = (
    V2GenerationCapability.REPRESENTATION_DERIVATION,
    V2GenerationCapability.LANGUAGE_TEXT,
    V2GenerationCapability.MULTILINGUAL_EMBEDDING,
    V2GenerationCapability.MULTILINGUAL_VECTOR,
)


@runtime_checkable
class ActiveV2GenerationSetStore(Protocol):  # pragma: no cover
    async def resolve_active_multilingual_v2_generation_set(self) -> tuple[UUID, ...] | None: ...


@runtime_checkable
class ActiveV2GenerationInspector(Protocol):  # pragma: no cover
    async def inspect_active_v2_generations(
        self, generation_ids: tuple[UUID, ...]
    ) -> tuple[V2GenerationEvidence, ...]: ...


@runtime_checkable
class V2DatabaseIdentityVerifier(Protocol):  # pragma: no cover
    def verify(self, *, expected_database_identity: str) -> None: ...

    def resolve_vector_embedding_generation(
        self, *, active_generation_ids: tuple[UUID, ...], expected_database_identity: str
    ) -> V2VectorEmbeddingGenerationBindingV1: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class V2RuntimeIdentityV1:
    """Governed identities shared by the profile, build, alias, and providers."""

    profile_id: str
    profile_fingerprint: str
    vector_space_identity: str
    build_run_id: UUID
    database_identity: str
    alias_set_digest: str
    query_preprocessing_identity: str
    document_preprocessing_identity: str
    authorization_service_id: str
    provenance_validator_id: str
    reranker_public_protocol_id: str
    provider_identity: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.profile_fingerprint, "profile_fingerprint"),
            (self.vector_space_identity, "vector_space_identity"),
            (self.database_identity, "database_identity"),
            (self.alias_set_digest, "alias_set_digest"),
        ):
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"{name} must be a SHA-256 digest")
        for value, name in (
            (self.profile_id, "profile_id"),
            (self.query_preprocessing_identity, "query_preprocessing_identity"),
            (self.document_preprocessing_identity, "document_preprocessing_identity"),
            (self.authorization_service_id, "authorization_service_id"),
            (self.provenance_validator_id, "provenance_validator_id"),
            (self.reranker_public_protocol_id, "reranker_public_protocol_id"),
            (self.provider_identity, "provider_identity"),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be blank")


@dataclass(frozen=True, slots=True, kw_only=True)
class V2RuntimeCompositionDependencies:
    """Central dependencies; evaluator code receives none of these directly."""

    active_store: ActiveV2GenerationSetStore
    generation_inspector: ActiveV2GenerationInspector
    database_identity_verifier: V2DatabaseIdentityVerifier
    source_enumerator: AuthorizedMultilingualSourceEnumeratorV2
    embedding_store: MultilingualEmbeddingStoreV2
    text_store: MultilingualTextProjectionStoreV2
    query_embedder: MultilingualQueryEmbedderV2
    retrieval_authorizer: V2RetrievalAuthorizerV1
    candidate_builder: RerankerCandidateBuilderProtocolV1
    reranker: MultilingualCandidateRerankerV3
    admission: MultilingualOperationAdmissionV2
    query_language_resolver: QueryLanguageResolverV2
    projector: V2AdvancedCandidateProjector
    exhaustive_fallback: object


@dataclass(frozen=True, slots=True, kw_only=True)
class ComposedFullMultilingualV2Runtime:
    """The only object an internal evaluator may receive."""

    application: FullMultilingualRetrievalApplicationV2
    advanced_source: FullMultilingualAdvancedSourceV2
    generation_ids: tuple[UUID, ...]
    identity: V2RuntimeIdentityV1
    parity: RuntimeParityEvidenceV1


class InternalFullMultilingualV2Evaluator:
    """Narrow evaluator boundary with no provider, store, or candidate inputs.

    Metric/qrel orchestration belongs to the later controlled evaluation phase.
    This entry point only guarantees that any future ranked execution uses the
    application already composed from the active V2 alias set.
    """

    evaluator_id = "mnemo.full-multilingual-v2-internal-evaluator/1"

    def __init__(self, runtime: ComposedFullMultilingualV2Runtime) -> None:
        self._runtime = runtime

    @property
    def runtime_parity(self) -> RuntimeParityEvidenceV1:
        return self._runtime.parity


class FullMultilingualV2EvaluationRuntimeFactory:
    """Compose a V2 evaluator path from the active alias set, never caller IDs."""

    def __init__(
        self,
        *,
        identity: V2RuntimeIdentityV1,
        dependencies: V2RuntimeCompositionDependencies,
    ) -> None:
        self._identity = identity
        self._dependencies = dependencies
        self._validate_dependency_protocols()

    async def compose(self) -> ComposedFullMultilingualV2Runtime:
        self._dependencies.database_identity_verifier.verify(
            expected_database_identity=self._identity.database_identity
        )
        generation_ids = await (
            self._dependencies.active_store.resolve_active_multilingual_v2_generation_set()
        )
        if generation_ids is None:
            raise V2RuntimeCompositionError("ACTIVE_ALIAS_MISSING")
        if len(generation_ids) != 4 or len(set(generation_ids)) != 4:
            raise V2RuntimeCompositionError("ACTIVE_GENERATION_INVALID")

        evidence = await self._dependencies.generation_inspector.inspect_active_v2_generations(
            generation_ids
        )
        ordered = _validate_generation_set(evidence, self._identity)
        if tuple(item.generation_id for item in ordered) != generation_ids:
            raise V2RuntimeCompositionError("ACTIVE_ALIAS_ORDER_OR_MEMBERSHIP_MISMATCH")
        vector_binding = (
            self._dependencies.database_identity_verifier.resolve_vector_embedding_generation(
                active_generation_ids=generation_ids,
                expected_database_identity=self._identity.database_identity,
            )
        )
        _validate_vector_embedding_binding(vector_binding, ordered, self._identity)

        dense = AuthorizedMultilingualDenseRetrievalV2(
            source_enumerator=self._dependencies.source_enumerator,
            store=self._dependencies.embedding_store,
            query_embedder=self._dependencies.query_embedder,
            generation_id=vector_binding.embedding_generation_id,
            vector_space=self._identity.vector_space_identity,
        )
        sparse = AuthorizedMultilingualSparseRetrievalV2(
            source_enumerator=self._dependencies.source_enumerator,
            store=self._dependencies.text_store,
            generation_id=_generation_id(ordered, V2GenerationCapability.LANGUAGE_TEXT),
        )
        application = FullMultilingualRetrievalApplicationV2(
            dense=dense,
            sparse=sparse,
            retrieval_authorizer=self._dependencies.retrieval_authorizer,
            candidate_builder=self._dependencies.candidate_builder,
            reranker=self._dependencies.reranker,
            admission=self._dependencies.admission,
        )
        advanced = FullMultilingualAdvancedSourceV2(
            application=application,
            query_language_resolver=self._dependencies.query_language_resolver,
            projector=self._dependencies.projector,
            exhaustive_fallback=self._dependencies.exhaustive_fallback,  # type: ignore[arg-type]
        )
        return ComposedFullMultilingualV2Runtime(
            application=application,
            advanced_source=advanced,
            generation_ids=generation_ids,
            identity=self._identity,
            parity=_parity(self._identity),
        )

    def _validate_dependency_protocols(self) -> None:
        values: tuple[tuple[object, type[object], str], ...] = (
            (
                self._dependencies.active_store,
                ActiveV2GenerationSetStore,
                "active generation store",
            ),
            (
                self._dependencies.generation_inspector,
                ActiveV2GenerationInspector,
                "generation inspector",
            ),
            (
                self._dependencies.database_identity_verifier,
                V2DatabaseIdentityVerifier,
                "database identity verifier",
            ),
            (
                self._dependencies.source_enumerator,
                AuthorizedMultilingualSourceEnumeratorV2,
                "authorized source enumerator",
            ),
            (self._dependencies.embedding_store, MultilingualEmbeddingStoreV2, "embedding store"),
            (
                self._dependencies.text_store,
                MultilingualTextProjectionStoreV2,
                "text projection store",
            ),
            (self._dependencies.query_embedder, MultilingualQueryEmbedderV2, "query embedder"),
            (
                self._dependencies.retrieval_authorizer,
                V2RetrievalAuthorizerV1,
                "bounded retrieval authorizer",
            ),
            (
                self._dependencies.candidate_builder,
                RerankerCandidateBuilderProtocolV1,
                "governed candidate builder",
            ),
            (self._dependencies.reranker, MultilingualCandidateRerankerV3, "public V3 reranker"),
            (self._dependencies.admission, MultilingualOperationAdmissionV2, "operation admission"),
            (
                self._dependencies.query_language_resolver,
                QueryLanguageResolverV2,
                "query language resolver",
            ),
            (self._dependencies.projector, V2AdvancedCandidateProjector, "candidate projector"),
        )
        for value, protocol, name in values:
            if not isinstance(value, protocol):
                raise TypeError(f"{name} does not implement its governed V2 protocol")


def _validate_generation_set(
    evidence: tuple[V2GenerationEvidence, ...], identity: V2RuntimeIdentityV1
) -> tuple[V2GenerationEvidence, ...]:
    expected = set(V2GenerationCapability)
    if len(evidence) != 4 or {item.capability for item in evidence} != expected:
        raise V2RuntimeCompositionError("ACTIVE_GENERATION_INVALID")
    if len({item.generation_id for item in evidence}) != 4:
        raise V2RuntimeCompositionError("ACTIVE_GENERATION_INVALID")
    for item in evidence:
        if item.profile_id != identity.profile_id:
            raise V2RuntimeCompositionError("PROFILE_MISMATCH")
        if item.state != "ready" or item.coverage_completeness != "complete":
            raise V2RuntimeCompositionError("GENERATION_INCOMPLETE")
        if item.coverage_count != item.item_count:
            raise V2RuntimeCompositionError("GENERATION_INCOMPLETE")
        if (
            item.capability
            in {
                V2GenerationCapability.MULTILINGUAL_EMBEDDING,
                V2GenerationCapability.MULTILINGUAL_VECTOR,
            }
            and item.vector_space_identity != identity.vector_space_identity
        ):
            raise V2RuntimeCompositionError("VECTOR_SPACE_MISMATCH")
    by_capability = {item.capability: item for item in evidence}
    return tuple(by_capability[item] for item in _CAPABILITY_ORDER)


def _generation_id(
    evidence: tuple[V2GenerationEvidence, ...], capability: V2GenerationCapability
) -> UUID:
    for item in evidence:
        if item.capability is capability:
            return item.generation_id
    raise V2RuntimeCompositionError("ACTIVE_GENERATION_INVALID")


def _validate_vector_embedding_binding(
    binding: V2VectorEmbeddingGenerationBindingV1,
    evidence: tuple[V2GenerationEvidence, ...],
    identity: V2RuntimeIdentityV1,
) -> None:
    if binding.database_identity != identity.database_identity:
        raise V2RuntimeCompositionError("DATABASE_BINDING_MISMATCH")
    if binding.build_run_id != identity.build_run_id:
        raise V2RuntimeCompositionError("BUILD_RUN_MISMATCH")
    if binding.vector_space_identity != identity.vector_space_identity:
        raise V2RuntimeCompositionError("VECTOR_SPACE_MISMATCH")
    if binding.vector_generation_id != _generation_id(
        evidence, V2GenerationCapability.MULTILINGUAL_VECTOR
    ) or binding.embedding_generation_id != _generation_id(
        evidence, V2GenerationCapability.MULTILINGUAL_EMBEDDING
    ):
        raise V2RuntimeCompositionError("ACTIVE_GENERATION_DEPENDENCY_MISMATCH")


def _parity(identity: V2RuntimeIdentityV1) -> RuntimeParityEvidenceV1:
    payload = {
        "application_service_id": FullMultilingualRetrievalApplicationV2.application_service_id,
        "authorization_service_id": identity.authorization_service_id,
        "retrieval_service_id": "mnemo.full-multilingual-v2-active-runtime/1",
        "candidate_builder_id": V2_TYPED_CANDIDATE_BUILDER_ID,
        "reranker_public_protocol_id": identity.reranker_public_protocol_id,
        "query_preprocessing_identity": identity.query_preprocessing_identity,
        "document_preprocessing_identity": identity.document_preprocessing_identity,
        "tokenizer_policy_id": "bge-reranker-v2-m3-pair-256-contextual-v1",
        "provenance_validator_id": identity.provenance_validator_id,
        "direct_provider_calls": False,
        "private_runtime_access": False,
        "caller_constructed_reranker_input": False,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return RuntimeParityEvidenceV1(
        application_service_id=FullMultilingualRetrievalApplicationV2.application_service_id,
        authorization_service_id=identity.authorization_service_id,
        retrieval_service_id="mnemo.full-multilingual-v2-active-runtime/1",
        candidate_builder_id=V2_TYPED_CANDIDATE_BUILDER_ID,
        reranker_public_protocol_id=identity.reranker_public_protocol_id,
        query_preprocessing_identity=identity.query_preprocessing_identity,
        document_preprocessing_identity=identity.document_preprocessing_identity,
        tokenizer_policy_id="bge-reranker-v2-m3-pair-256-contextual-v1",
        provenance_validator_id=identity.provenance_validator_id,
        direct_provider_calls=False,
        private_runtime_access=False,
        caller_constructed_reranker_input=False,
        parity_digest=digest,
    )
