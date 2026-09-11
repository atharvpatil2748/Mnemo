"""Server-owned registration of the production Full Multilingual V2 adapters."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid5

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces.multilingual import (
    MultilingualCandidateRerankerV3,
    RerankerCandidateBuilderProtocolV1,
    RerankerEvidenceResolverV1,
)
from mnemo.interfaces.scope import PrincipalContextV1
from mnemo.models.advanced_retrieval import RetrievalPlanV2
from mnemo.models.v2_evidence_resolution import V2GenerationSetBindingV1
from mnemo.models.v2_retrieval_authorization import (
    V2ActiveRuntimeBindingV1,
    V2RetrievalAuthorizationDecisionV1,
)
from mnemo.phase85.v2_database_identity import GovernedV2DatabaseIdentityVerifier
from mnemo.phase85.v2_evaluation_runtime import (
    V2RuntimeCompositionDependencies,
    V2RuntimeIdentityV1,
)
from mnemo.phase85.v2_production_adapters import (
    AuthorizedV2EvidenceResolver,
    AuthorizedV2SourceStorageEnumerator,
    GovernedActiveV2GenerationInspector,
    GovernedV2CandidateProjector,
)
from mnemo.phase85.v2_readiness import V2GenerationCapability
from mnemo.retrieval.full_multilingual_advanced_v2 import (
    QueryLanguageResolverV2,
)
from mnemo.retrieval.full_multilingual_v2 import MultilingualOperationAdmissionV2
from mnemo.retrieval.multilingual_dense_v2 import MultilingualQueryEmbedderV2
from mnemo.storage.v2_runtime import SQLiteV2ReadOnlyRuntimeStore

from .authorization import AuthorizationOperationV1, CentralAuthorizationServiceV1

_DECISION_NAMESPACE = UUID("96ee5a51-9eb7-548b-b042-ee2332561c44")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class CentralV2RetrievalAuthorizerV1:
    """Compose central notebook authorization with active V2 runtime constraints."""

    policy_identity = "mnemo.server.v2-retrieval-authorization-policy/1"
    policy_revision = "1.0.0"

    def __init__(
        self,
        *,
        central: CentralAuthorizationServiceV1,
        store: SQLiteV2ReadOnlyRuntimeStore,
        inspector: GovernedActiveV2GenerationInspector,
        identity: V2RuntimeIdentityV1,
        admission: MultilingualOperationAdmissionV2,
    ) -> None:
        self._central = central
        self._store = store
        self._inspector = inspector
        self._identity = identity
        self._admission = admission

    async def authorize_v2_retrieval(
        self, *, principal: PrincipalContextV1, plan: RetrievalPlanV2
    ) -> V2RetrievalAuthorizationDecisionV1:
        if not principal.authenticated:
            raise PermissionError("PRINCIPAL_MISSING")
        base = await self._central.authorize_notebook(
            principal,
            plan.scope.notebook_id,
            AuthorizationOperationV1.RETRIEVE,
            capability="multilingual_retrieval_v2",
        )
        if not base.allowed or base.actor_id != principal.actor_id:
            raise PermissionError("AUTHORIZATION_DENIED")
        generation_ids = await self._store.resolve_active_multilingual_v2_generation_set()
        if generation_ids is None:
            raise PermissionError("ACTIVE_ALIAS_MISSING")
        await self._inspector.inspect_active_v2_generations(generation_ids)
        admission_identity = (
            f"{type(self._admission).__module__}.{type(self._admission).__qualname__}"
        )
        runtime = V2ActiveRuntimeBindingV1(
            alias_set_digest=self._identity.alias_set_digest,
            generation_ids=generation_ids,
            profile_fingerprint=self._identity.profile_fingerprint,
            vector_space_identity=self._identity.vector_space_identity,
            database_identity=self._identity.database_identity,
            build_run_id=self._identity.build_run_id,
            admission_policy_identity=admission_identity,
        )
        issued_at = datetime.now(UTC).isoformat()
        request_fingerprint = _digest(
            {
                "principal_actor_id": str(principal.actor_id),
                "plan": plan.fingerprint,
                "runtime": {
                    "alias": runtime.alias_set_digest,
                    "generations": [str(item) for item in runtime.generation_ids],
                    "profile": runtime.profile_fingerprint,
                    "vector_space": runtime.vector_space_identity,
                    "database": runtime.database_identity,
                    "build_run": str(runtime.build_run_id),
                },
            }
        )
        return V2RetrievalAuthorizationDecisionV1(
            decision_id=uuid5(_DECISION_NAMESPACE, request_fingerprint + issued_at),
            principal_actor_id=principal.actor_id,
            operation="retrieve",
            retrieval_scope=plan.scope,
            positional_scope=plan.position,
            runtime_binding=runtime,
            authorization_policy_identity=self.policy_identity,
            authorization_policy_revision=self.policy_revision,
            request_fingerprint=request_fingerprint,
            issued_at=issued_at,
            required_provenance_evidence=(
                "source_document_chunk_identity",
                "active_generation_set",
                "representation_lineage",
                "canonical_database_identity",
            ),
        )


CandidateBuilderFactory = Callable[[RerankerEvidenceResolverV1], RerankerCandidateBuilderProtocolV1]


@dataclass(frozen=True, slots=True, kw_only=True)
class V2ProductionRuntimeSupportV1:
    """Provider-facing dependencies supplied by governed server configuration."""

    query_embedder: MultilingualQueryEmbedderV2
    candidate_builder_factory: CandidateBuilderFactory
    reranker: MultilingualCandidateRerankerV3
    admission: MultilingualOperationAdmissionV2
    query_language_resolver: QueryLanguageResolverV2
    exhaustive_fallback: object


class ProductionFullMultilingualV2ServerDependencyAssemblerV1:
    """Concrete server-owned composition root; composition performs no inference."""

    def __init__(
        self,
        *,
        workspace_root: Path,
        identity_manifest: Path,
        identity: V2RuntimeIdentityV1,
        support: V2ProductionRuntimeSupportV1,
    ) -> None:
        self._root = workspace_root
        self._manifest = identity_manifest
        self._identity = identity
        self._support = support
        self._store: SQLiteV2ReadOnlyRuntimeStore | None = None

    @property
    def identity(self) -> V2RuntimeIdentityV1:
        """Return the immutable runtime identity used by production composition."""
        return self._identity

    def for_nonactivating_evaluation(
        self, *, reranker: MultilingualCandidateRerankerV3
    ) -> ProductionFullMultilingualV2ServerDependencyAssemblerV1:
        """Clone the production composition with only its reranker dependency replaced.

        The clone opens its own read-only store connection and preserves every
        other production dependency.  It cannot mutate the installed router or
        perform an activation transition.
        """
        return ProductionFullMultilingualV2ServerDependencyAssemblerV1(
            workspace_root=self._root,
            identity_manifest=self._manifest,
            identity=self._identity,
            support=replace(self._support, reranker=reranker),
        )

    async def assemble_v2_runtime_dependencies(
        self,
        *,
        engine: KnowledgeEngine,
        authorization: CentralAuthorizationServiceV1,
    ) -> V2RuntimeCompositionDependencies:
        verifier = GovernedV2DatabaseIdentityVerifier(
            workspace_root=self._root, identity_manifest=self._manifest
        )
        artifact = verifier.artifact
        engine_database = engine.config.storage.sqlite.path.resolve()
        governed_database = (self._root / artifact.target_path).resolve()
        if engine_database != governed_database:
            raise RuntimeError("PRODUCTION_STORE_CONFIGURATION_MISMATCH")
        if (
            artifact.database_identity != self._identity.database_identity
            or artifact.profile_fingerprint != self._identity.profile_fingerprint
            or artifact.vector_space_identity != self._identity.vector_space_identity
            or artifact.build_run_id != self._identity.build_run_id
        ):
            raise RuntimeError("DATABASE_BINDING_MISMATCH")
        store = SQLiteV2ReadOnlyRuntimeStore(governed_database)
        await store.open()
        self._store = store
        inspector = GovernedActiveV2GenerationInspector(
            store=store, verifier=verifier, identity=self._identity
        )
        active = await store.resolve_active_multilingual_v2_generation_set()
        if active is None:
            raise RuntimeError("ACTIVE_ALIAS_MISSING")
        evidence = await inspector.inspect_active_v2_generations(active)
        by_capability = {item.capability: item for item in evidence}
        generations = V2GenerationSetBindingV1(
            representation_generation_id=by_capability[
                V2GenerationCapability.REPRESENTATION_DERIVATION
            ].generation_id,
            language_text_generation_id=by_capability[
                V2GenerationCapability.LANGUAGE_TEXT
            ].generation_id,
            embedding_generation_id=by_capability[
                V2GenerationCapability.MULTILINGUAL_EMBEDDING
            ].generation_id,
            vector_generation_id=by_capability[
                V2GenerationCapability.MULTILINGUAL_VECTOR
            ].generation_id,
        )
        vector_binding = verifier.resolve_vector_embedding_generation(
            active_generation_ids=active,
            expected_database_identity=self._identity.database_identity,
        )
        enumerator = AuthorizedV2SourceStorageEnumerator(
            store=store,
            generations=generations,
            identity=self._identity,
            model_identity=vector_binding.model_identity,
        )
        evidence_resolver = AuthorizedV2EvidenceResolver(store=store)
        projector = GovernedV2CandidateProjector(
            enumerator=enumerator, resolver=evidence_resolver, store=store
        )
        candidate_builder = self._support.candidate_builder_factory(projector)
        authorizer = CentralV2RetrievalAuthorizerV1(
            central=authorization,
            store=store,
            inspector=inspector,
            identity=self._identity,
            admission=self._support.admission,
        )
        return V2RuntimeCompositionDependencies(
            active_store=store,
            generation_inspector=inspector,
            database_identity_verifier=verifier,
            source_enumerator=enumerator,
            embedding_store=store,
            text_store=store,
            query_embedder=self._support.query_embedder,
            retrieval_authorizer=authorizer,
            candidate_builder=candidate_builder,
            reranker=self._support.reranker,
            admission=self._support.admission,
            query_language_resolver=self._support.query_language_resolver,
            projector=projector,
            exhaustive_fallback=self._support.exhaustive_fallback,
        )

    async def close(self) -> None:
        if self._store is not None:
            await self._store.close()
            self._store = None
