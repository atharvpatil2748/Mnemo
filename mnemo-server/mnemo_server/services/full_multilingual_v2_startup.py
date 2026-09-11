"""Governed production startup for the active 44-document Full Multilingual V2 runtime."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces.advanced_retrieval import MultilingualAdvancedStoreV1
from mnemo.models.multilingual import LanguageCode
from mnemo.phase85.profiles import ModelProfileDocument, profile_snapshot
from mnemo.phase85.v2_database_identity import GovernedV2DatabaseIdentityVerifier
from mnemo.phase85.v2_evaluation_runtime import V2RuntimeIdentityV1
from mnemo.phase85.v2_production_adapters import GovernedActiveV2GenerationInspector
from mnemo.phase85.v2_readiness import V2ReadinessSnapshot
from mnemo.retrieval.full_multilingual_advanced_v2 import QueryLanguageResolverV2
from mnemo.retrieval.multilingual import ConservativeENHIMRDetector
from mnemo.retrieval.multilingual_providers import (
    BGE_M3_DOCUMENT_PREPROCESSING,
    BGE_M3_QUERY_PREPROCESSING,
    BGEM3EmbeddingProvider,
)
from mnemo.retrieval.multimodal_sources import ProjectedMultilingualAdvancedSource
from mnemo.retrieval.reranker_candidates import V2TypedCandidateBuilderV1
from mnemo.storage.v2_runtime import SQLiteV2ReadOnlyRuntimeStore

from .full_multilingual_v2_production import (
    ProductionFullMultilingualV2ServerDependencyAssemblerV1,
    V2ProductionRuntimeSupportV1,
)
from .full_multilingual_v2_registration import ServerOwnedFullMultilingualV2RegistrationV1
from .v2_reranker_lifecycle import (
    DurableRerankerActivationAuthorityV1,
    GovernedV2RerankerRouterV1,
    RerankerActivationAuthorityV1,
    V2ExposureAuthorityV1,
    V2RerankerMode,
)

PROFILE_PATH = Path("config/model_profiles/full_multilingual_v2_profiles.toml")
PROFILE_NAME = "full_multilingual_v2_local_prebuild"
IDENTITY_MANIFEST = Path(
    "docs/governance/proposals/phase8_5_full_multilingual_architecture/"
    "V2_DATABASE_ARTIFACT_IDENTITY.json"
)


class _ProfileClaimAdmissionV1:
    """Admit only operations and languages declared by the frozen model profile."""

    def __init__(self, *, embedding_languages: frozenset[str], reranker_languages: frozenset[str]):
        self._embedding = embedding_languages
        self._reranker = reranker_languages

    def permits(self, *, language: LanguageCode, operation: str) -> bool:
        if operation in {"dense_retrieval", "sparse_retrieval"}:
            return language.value in self._embedding
        if operation == "reranking":
            return language.value in self._reranker
        return False


class _GovernedQueryLanguageResolverV1:
    """Adapt the repository's frozen query detector without deriving authorization."""

    def __init__(self) -> None:
        self._detector = ConservativeENHIMRDetector()

    async def resolve_query_language(
        self, *, principal: object, notebook_id: UUID, query: str
    ) -> LanguageCode:
        actor_id = getattr(principal, "actor_id", None)
        if not isinstance(actor_id, UUID):
            raise PermissionError("server principal is missing")
        observation = await self._detector.detect(
            actor_id=actor_id,
            notebook_id=notebook_id,
            target_id=hashlib.sha256(query.encode("utf-8")).hexdigest(),
            text=query,
        )
        if observation.mixed_language or observation.language.value == "und":
            raise LookupError("query language is unresolved")
        return observation.language


@dataclass(slots=True)
class InstalledFullMultilingualV2RuntimeV1:
    assembler: ProductionFullMultilingualV2ServerDependencyAssemblerV1
    embedding: BGEM3EmbeddingProvider
    reranker: GovernedV2RerankerRouterV1
    reranker_activation: RerankerActivationAuthorityV1
    exposure_snapshot: V2ReadinessSnapshot
    durable_reranker_activation: DurableRerankerActivationAuthorityV1 | None = None

    async def close(self) -> None:
        if self.reranker.mode is V2RerankerMode.BGE_V2_M3:
            await self.reranker_activation.rollback()
        await self.assembler.close()
        await self.embedding.close()


async def install_production_full_multilingual_v2(
    *,
    engine: KnowledgeEngine,
    workspace_root: Path,
    model_cache: Path,
    readiness: V2ReadinessSnapshot,
) -> InstalledFullMultilingualV2RuntimeV1:
    """Resolve, compose, and install the active V2 runtime; never select latest IDs."""
    root = workspace_root.resolve()
    manifest = (root / IDENTITY_MANIFEST).resolve()
    verifier = GovernedV2DatabaseIdentityVerifier(workspace_root=root, identity_manifest=manifest)
    artifact = verifier.artifact
    if engine.config.storage.sqlite.path.resolve() != (root / artifact.target_path).resolve():
        raise RuntimeError("PRODUCTION_STORE_CONFIGURATION_MISMATCH")
    profile_document = ModelProfileDocument.from_file(root / PROFILE_PATH)
    snapshot = profile_snapshot(profile_document.select(PROFILE_NAME))
    if snapshot.fingerprint != artifact.profile_fingerprint:
        raise RuntimeError("PROFILE_MISMATCH")

    active_store = SQLiteV2ReadOnlyRuntimeStore(root / artifact.target_path)
    await active_store.open()
    try:
        generation_ids = await active_store.resolve_active_multilingual_v2_generation_set()
        alias_digest = await active_store.resolve_active_multilingual_v2_alias_digest()
        if generation_ids is None or alias_digest is None:
            raise RuntimeError("ACTIVE_ALIAS_MISSING")
        identity = V2RuntimeIdentityV1(
            profile_id=snapshot.profile_id,
            profile_fingerprint=snapshot.fingerprint,
            vector_space_identity=artifact.vector_space_identity,
            build_run_id=artifact.build_run_id,
            database_identity=artifact.database_identity,
            alias_set_digest=alias_digest,
            query_preprocessing_identity=BGE_M3_QUERY_PREPROCESSING,
            document_preprocessing_identity=BGE_M3_DOCUMENT_PREPROCESSING,
            authorization_service_id="mnemo.server.v2-retrieval-authorization-policy/1",
            provenance_validator_id="mnemo.v2-provenance-validator/1",
            reranker_public_protocol_id="multilingual-reranker/3",
            provider_identity="sentence-transformers",
        )
        inspector = GovernedActiveV2GenerationInspector(
            store=active_store, verifier=verifier, identity=identity
        )
        await inspector.inspect_active_v2_generations(generation_ids)
    finally:
        await active_store.close()

    embedding_component = snapshot.components["multilingual_embedding"]
    reranker_component = snapshot.components["multilingual_reranker"]
    embedding_generation = next(
        item.generation_id
        for item in artifact.generations
        if item.capability == "multilingual_embedding_v2"
    )
    embedding = BGEM3EmbeddingProvider(
        embedding_component,
        generation_id=embedding_generation,
        cache_folder=model_cache,
    )
    reranker = GovernedV2RerankerRouterV1()
    await embedding.initialize()
    try:
        storage = engine.storage
        if not isinstance(storage, MultilingualAdvancedStoreV1):
            raise RuntimeError("PRODUCTION_MULTILINGUAL_STORAGE_CONTRACT_MISSING")
        fallback = ProjectedMultilingualAdvancedSource(storage)
        admission = _ProfileClaimAdmissionV1(
            embedding_languages=frozenset(
                claim.language
                for claim in embedding_component.language_claims
                if "query_embedding" in claim.operations
            ),
            reranker_languages=frozenset(
                claim.language
                for claim in reranker_component.language_claims
                if "reranking" in claim.operations
            ),
        )
        resolver = _GovernedQueryLanguageResolverV1()
        if not isinstance(resolver, QueryLanguageResolverV2):
            raise TypeError("query language resolver contract mismatch")
        assembler = ProductionFullMultilingualV2ServerDependencyAssemblerV1(
            workspace_root=root,
            identity_manifest=manifest,
            identity=identity,
            support=V2ProductionRuntimeSupportV1(
                query_embedder=embedding,
                candidate_builder_factory=lambda evidence_resolver: V2TypedCandidateBuilderV1(
                    resolver=evidence_resolver
                ),
                reranker=reranker,
                admission=admission,
                query_language_resolver=resolver,
                exhaustive_fallback=fallback,
            ),
        )
        registration = ServerOwnedFullMultilingualV2RegistrationV1(
            engine=engine, identity=identity, assembler=assembler
        )
        runtime = await registration.compose_internal_runtime()
        if readiness.inputs.profile_fingerprint != identity.profile_fingerprint:
            raise RuntimeError("READINESS_PROFILE_MISMATCH")
        if tuple(item.generation_id for item in readiness.inputs.generation_set) != generation_ids:
            raise RuntimeError("READINESS_GENERATION_MISMATCH")
        exposure_snapshot = await V2ExposureAuthorityV1().expose(
            engine=engine,
            source=runtime.advanced_source,
            readiness=readiness,
            reranker=reranker,
        )
        return InstalledFullMultilingualV2RuntimeV1(
            assembler=assembler,
            embedding=embedding,
            reranker=reranker,
            reranker_activation=RerankerActivationAuthorityV1(
                router=reranker,
                component=reranker_component,
                model_cache=model_cache,
            ),
            exposure_snapshot=exposure_snapshot,
        )
    except BaseException:
        await embedding.close()
        raise
