"""Server-owned Full V2 composition for a governed disposable rebuild."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from langdetect import DetectorFactory, LangDetectException, detect  # type: ignore[import-untyped]
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces.advanced_retrieval import MultilingualAdvancedStoreV1
from mnemo.models.multilingual import LanguageCode
from mnemo.phase85.isolated_v2_identity import IsolatedV2DatabaseIdentityVerifier
from mnemo.phase85.profiles import ModelProfileDocument
from mnemo.phase85.rebuild_language_capability import (
    RebuildLanguageCapability,
    load_rebuild_language_capability,
)
from mnemo.phase85.v2_evaluation_runtime import V2RuntimeIdentityV1
from mnemo.retrieval.clip_text_query import LocalCLIPTextQueryProvider
from mnemo.retrieval.full_multilingual_v2 import PassThroughV2RerankerV1
from mnemo.retrieval.multilingual_providers import (
    BGE_M3_DOCUMENT_PREPROCESSING,
    BGE_M3_QUERY_PREPROCESSING,
    BGEM3EmbeddingProvider,
)
from mnemo.retrieval.multimodal_sources import ProjectedMultilingualAdvancedSource
from mnemo.retrieval.reranker_candidates import V2TypedCandidateBuilderV1
from mnemo.storage.v2_runtime import SQLiteV2ReadOnlyRuntimeStore

from mnemo_server.services.full_multilingual_v2_production import (
    ProductionFullMultilingualV2ServerDependencyAssemblerV1,
    V2ProductionRuntimeSupportV1,
)
from mnemo_server.services.full_multilingual_v2_registration import (
    ServerOwnedFullMultilingualV2RegistrationV1,
)


class _CommonSpaceQueryLanguageResolver:
    """Language observation for V2; undecidable text stays und, never guessed."""

    async def resolve_query_language(
        self, *, principal: object, notebook_id: UUID, query: str
    ) -> LanguageCode:
        del notebook_id
        if not isinstance(getattr(principal, "actor_id", None), UUID):
            raise PermissionError("server principal is missing")
        if not any(char.isalpha() for char in query):
            raise LookupError("query has no language-bearing text")
        DetectorFactory.seed = 0
        try:
            return LanguageCode(detect(query))
        except (LangDetectException, ValueError):
            return LanguageCode("und")


class _CommonSpaceAdmission:
    """Apply model-scoped capability, not a corpus-observed language allowlist."""

    def __init__(self, capability: RebuildLanguageCapability) -> None:
        self._capability = capability

    def permits(self, *, language: LanguageCode, operation: str) -> bool:
        del language
        if operation in {"dense_retrieval", "sparse_retrieval"}:
            return self._capability.permits("query_embedding")
        # The isolated runtime uses a bounded pass-through reranker.
        return operation == "reranking" and self._capability.permits("query_embedding")


@dataclass(slots=True)
class InstalledIsolatedFullV2:
    assembler: ProductionFullMultilingualV2ServerDependencyAssemblerV1
    embedding: BGEM3EmbeddingProvider
    identity: V2RuntimeIdentityV1
    generation_ids: tuple[UUID, ...]
    visual_status: str

    async def close(self) -> None:
        await self.assembler.close()
        await self.embedding.close()


async def install_isolated_full_v2(
    *,
    engine: KnowledgeEngine,
    workspace: Path,
    runtime: Path,
    model_cache: Path,
    clip_snapshot: Path | None = None,
) -> InstalledIsolatedFullV2:
    """Resolve only the active canary alias, then reuse the production V2 factory."""
    verifier = IsolatedV2DatabaseIdentityVerifier(workspace_root=workspace, runtime=runtime)
    artifact = verifier.artifact
    if engine.config.storage.sqlite.path.resolve() != (runtime / "mnemo.db").resolve():
        raise ValueError("isolated V2 engine database mismatch")
    report = json.loads((runtime / "full-v2-serving.json").read_text(encoding="utf-8"))
    if (
        report.get("state") != "active_internal_only"
        or report.get("database_identity") != artifact.database_identity
        or report.get("notebook_id") != str(artifact.notebook_id)
        or report.get("generation_ids") != [str(item) for item in artifact.generation_ids]
    ):
        raise ValueError("isolated Full V2 serving report does not bind the rebuild")
    verifier.verify(expected_database_identity=artifact.database_identity)
    with sqlite3.connect(
        f"file:{(runtime / 'mnemo.db').as_posix()}?mode=ro&immutable=1", uri=True
    ) as db:
        activation = db.execute(
            "SELECT activation_mode,recovery_mode,authorization_id,authorization_digest "
            "FROM multilingual_v2_activation_records WHERE alias_set_digest=?",
            (report.get("alias_set_digest"),),
        ).fetchone()
    if activation != (
        "first_v2_activation",
        "deactivate_v2_alias_set",
        report.get("authorization_id"),
        report.get("authorization_digest"),
    ):
        raise ValueError("isolated Full V2 serving authorization is not active")
    store = SQLiteV2ReadOnlyRuntimeStore(runtime / "mnemo.db")
    await store.open()
    try:
        active = await store.resolve_active_multilingual_v2_generation_set()
        alias_digest = await store.resolve_active_multilingual_v2_alias_digest()
        if active != artifact.generation_ids or alias_digest != report.get("alias_set_digest"):
            raise ValueError("isolated Full V2 active alias changed")
        if alias_digest is None:
            raise ValueError("isolated Full V2 active alias is missing")
        evidence = await store.inspect_active_v2_generations(active)
        profile_id = evidence[0].profile_id
        if any(item.profile_id != profile_id for item in evidence):
            raise ValueError("isolated Full V2 profile identities differ")
        binding = verifier.resolve_vector_embedding_generation(
            active_generation_ids=active,
            expected_database_identity=artifact.database_identity,
        )
    finally:
        await store.close()
    component = (
        ModelProfileDocument.from_file(
            workspace / "config/model_profiles/full_multilingual_v2_profiles.toml"
        )
        .select("full_multilingual_v2_local_prebuild")
        .models["multilingual_embedding"]
    )
    if f"{component.model}@{component.revision}" != binding.model_identity:
        raise ValueError("isolated V2 serving model differs from built embeddings")
    capability = load_rebuild_language_capability(
        path=workspace / "config/rebuild/multilingual_embedding_capability.json",
        component=component,
    )
    multilingual_stage = json.loads(
        (runtime / "multilingual-stage.json").read_text(encoding="utf-8")
    )
    if (
        multilingual_stage.get("language_capability_identity") != capability.identity
        or multilingual_stage.get("profile_fingerprint") != artifact.profile_fingerprint
    ):
        raise ValueError("isolated V2 serving language capability differs from built generation")
    execution_device = multilingual_stage.get("execution_device")
    if execution_device not in {"cpu", "cuda"}:
        raise ValueError("isolated V2 query encoder device is not recorded")
    if runtime.parent.name == "two_corpus_rebuilds" and execution_device != "cuda":
        raise ValueError("two-corpus BGE-M3 query serving requires CUDA")
    embedding = BGEM3EmbeddingProvider(
        component,
        generation_id=binding.embedding_generation_id,
        cache_folder=model_cache,
        device=execution_device,
    )
    await embedding.initialize()
    try:
        provider_profile = await embedding.profile()
        if (
            provider_profile.vector_space != artifact.vector_space_identity
            or provider_profile.dimension != binding.dimensions
        ):
            raise ValueError("isolated V2 query encoder is incompatible")
        storage = engine.storage
        if not isinstance(storage, MultilingualAdvancedStoreV1):
            raise ValueError("isolated V2 engine storage lacks multilingual projections")
        identity = V2RuntimeIdentityV1(
            profile_id=profile_id,
            profile_fingerprint=artifact.profile_fingerprint,
            vector_space_identity=artifact.vector_space_identity,
            build_run_id=artifact.build_run_id,
            database_identity=artifact.database_identity,
            alias_set_digest=alias_digest,
            query_preprocessing_identity=BGE_M3_QUERY_PREPROCESSING,
            document_preprocessing_identity=BGE_M3_DOCUMENT_PREPROCESSING,
            authorization_service_id="mnemo.server.v2-retrieval-authorization-policy/1",
            provenance_validator_id="mnemo.v2-provenance-validator/1",
            reranker_public_protocol_id="multilingual-reranker/3",
            provider_identity=component.provider,
        )
        admission = _CommonSpaceAdmission(capability)
        assembler = ProductionFullMultilingualV2ServerDependencyAssemblerV1(
            workspace_root=workspace,
            identity_manifest=runtime / "full-v2-serving.json",
            identity=identity,
            support=V2ProductionRuntimeSupportV1(
                query_embedder=embedding,
                candidate_builder_factory=lambda resolver: V2TypedCandidateBuilderV1(
                    resolver=resolver
                ),
                reranker=PassThroughV2RerankerV1(),
                admission=admission,
                query_language_resolver=_CommonSpaceQueryLanguageResolver(),
                exhaustive_fallback=ProjectedMultilingualAdvancedSource(storage),
            ),
            isolated_verifier=verifier,
            isolated_database=runtime / "mnemo.db",
        )
        registration = ServerOwnedFullMultilingualV2RegistrationV1(
            engine=engine, identity=identity, assembler=assembler
        )
        composed = await registration.compose_internal_runtime()
        await engine.install_internal_full_multilingual_v2(runtime=composed)
        visual_status = "compatible_text_query_snapshot_not_supplied"
        if clip_snapshot is not None:
            connection = sqlite3.connect(
                f"file:{(runtime / 'mnemo.db').as_posix()}?mode=ro&immutable=1", uri=True
            )
            try:
                rows = connection.execute(
                    "SELECT e.payload FROM visual_embeddings e "
                    "JOIN visual_vector_projection_rows p USING(derivation_id) "
                    "JOIN active_index_generations a ON a.generation_id=p.generation_id "
                    "JOIN index_generations g ON g.generation_id=p.generation_id "
                    "WHERE g.state='ready'"
                ).fetchall()
            finally:
                connection.close()
            if not rows:
                visual_status = "active_visual_generation_missing"
            else:
                metadata = [json.loads(row[0]) for row in rows]
                profiles = {
                    (
                        value["provider"]["profile_id"],
                        value["provider"]["model_identity"],
                        value["provider"]["model_revision"],
                        value["shared_space_id"],
                        value["dimensions"],
                        value["metric"],
                    )
                    for value in metadata
                }
                if len(profiles) != 1:
                    raise ValueError("active visual projections have incompatible profiles")
                profile_id, model, revision, shared_space, dimensions, metric = next(iter(profiles))
                if (
                    model != "openai/clip-vit-large-patch14"
                    or clip_snapshot.resolve(strict=True).name != revision
                    or shared_space != f"{model}@{revision}"
                    or dimensions != 768
                    or metric != "cosine"
                ):
                    raise ValueError("CLIP text snapshot differs from active visual generation")
                provider = LocalCLIPTextQueryProvider(
                    snapshot=clip_snapshot,
                    profile_id=profile_id,
                    shared_space_id=shared_space,
                    dimensions=dimensions,
                )
                await engine.install_internal_visual_query_provider(provider=provider)
                visual_status = "active_matching_clip_text_query"
        return InstalledIsolatedFullV2(
            assembler=assembler,
            embedding=embedding,
            identity=identity,
            generation_ids=composed.generation_ids,
            visual_status=visual_status,
        )
    except BaseException:
        await embedding.close()
        raise
