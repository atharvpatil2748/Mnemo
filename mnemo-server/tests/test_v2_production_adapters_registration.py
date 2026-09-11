"""Production composition registration test; no query or provider inference is executed."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces.advanced_retrieval import AdvancedRetrievalSourceV1
from mnemo.interfaces.scope import PrincipalContextV1
from mnemo.models.advanced_retrieval import (
    AdvancedRetrievalMode,
    EvidenceRepresentation,
    RankingPolicyV2,
    RetrievalBudgetsV2,
    RetrievalPlanV2,
    RetrievalScopeV2,
)
from mnemo.models.multilingual import LanguageCode
from mnemo.phase85.v2_database_identity import GovernedV2DatabaseIdentityVerifier
from mnemo.phase85.v2_evaluation_runtime import V2RuntimeIdentityV1
from mnemo.retrieval.reranker_candidates import (
    RenderedRerankerPairV1,
    RerankerCandidateBuilderV1,
)
from mnemo_server.services.full_multilingual_v2_production import (
    CentralV2RetrievalAuthorizerV1,
    ProductionFullMultilingualV2ServerDependencyAssemblerV1,
    V2ProductionRuntimeSupportV1,
)
from mnemo_server.services.full_multilingual_v2_registration import (
    ServerOwnedFullMultilingualV2RegistrationV1,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (
    ROOT
    / "docs/governance/proposals/phase8_5_full_multilingual_architecture"
    / "V2_DATABASE_ARTIFACT_IDENTITY.json"
)


class _NoInferenceQueryEmbedder:
    async def embed_query(self, _: object) -> object:
        raise AssertionError("composition must not invoke the embedding provider")


class _NoInferenceReranker:
    async def score_candidates(self, _: object) -> tuple[object, ...]:
        raise AssertionError("composition must not invoke the reranker provider")


class _Admission:
    def permits(self, language: LanguageCode, operation: str) -> bool:
        return bool(language.value and operation)


class _QueryLanguageResolver:
    async def resolve_query_language(self, _: object) -> LanguageCode:
        raise AssertionError("composition must not execute a query")


class _Fallback:
    representation = EvidenceRepresentation.MULTILINGUAL_TEXT

    async def retrieve(self, _: object, __: object) -> object:
        raise AssertionError("composition must not retrieve")

    async def expand(self, _: object, __: object) -> tuple[object, ...]:
        raise AssertionError("composition must not retrieve")


class _Tokenizer:
    identity = "fixture-tokenizer"
    revision = "1"
    configuration_digest = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"

    def encode_without_special_tokens(self, text: str) -> tuple[int, ...]:
        return tuple(range(1, max(2, len(text.split())) + 1))

    def build_pair(
        self, query_ids: tuple[int, ...], document_ids: tuple[int, ...]
    ) -> RenderedRerankerPairV1:
        values = [101, *query_ids, 102, *document_ids, 102]
        return RenderedRerankerPairV1(
            input_ids=tuple(values),
            attention_mask=tuple(1 for _ in values),
            token_type_ids=None,
        )


def _builder(resolver: object) -> RerankerCandidateBuilderV1:
    return RerankerCandidateBuilderV1(
        resolver=cast(Any, resolver),
        tokenizer=_Tokenizer(),
        provider_id="sentence-transformers",
        model_id="BAAI/bge-reranker-v2-m3",
        model_revision="953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
        provider_configuration_digest="dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
        query_preprocessing_identity="query-preprocessing",
        document_preprocessing_identity="document-preprocessing",
        preprocess_query=lambda value: value,
        preprocess_document=lambda value: value,
    )


async def _compose() -> None:
    verifier = GovernedV2DatabaseIdentityVerifier(
        workspace_root=ROOT,
        identity_manifest=MANIFEST,
    )
    target = (ROOT / verifier.artifact.target_path).resolve()
    if not target.exists():
        pytest.skip("Governed V2 production database not present in environment")
    artifact = verifier.artifact
    identity = V2RuntimeIdentityV1(
        profile_id="full_multilingual_v2_local_prebuild",
        profile_fingerprint=artifact.profile_fingerprint,
        vector_space_identity=artifact.vector_space_identity,
        build_run_id=artifact.build_run_id,
        database_identity=artifact.database_identity,
        alias_set_digest="b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0",
        query_preprocessing_identity="query-preprocessing",
        document_preprocessing_identity="document-preprocessing",
        authorization_service_id="central-v1-plus-v2",
        provenance_validator_id="v2-provenance-validator/1",
        reranker_public_protocol_id="multilingual-reranker/3",
        provider_identity="sentence-transformers",
    )
    assembler = ProductionFullMultilingualV2ServerDependencyAssemblerV1(
        workspace_root=ROOT,
        identity_manifest=MANIFEST,
        identity=identity,
        support=V2ProductionRuntimeSupportV1(
            query_embedder=cast(Any, _NoInferenceQueryEmbedder()),
            candidate_builder_factory=_builder,
            reranker=cast(Any, _NoInferenceReranker()),
            admission=cast(Any, _Admission()),
            query_language_resolver=cast(Any, _QueryLanguageResolver()),
            exhaustive_fallback=cast(AdvancedRetrievalSourceV1, _Fallback()),
        ),
    )
    engine = cast(
        KnowledgeEngine,
        SimpleNamespace(
            config=SimpleNamespace(
                storage=SimpleNamespace(
                    sqlite=SimpleNamespace(path=(ROOT / verifier.artifact.target_path).resolve())
                )
            )
        ),
    )
    registration = ServerOwnedFullMultilingualV2RegistrationV1(
        engine=engine,
        identity=identity,
        assembler=assembler,
    )
    try:
        runtime = await registration.compose_internal_runtime()
        assert runtime.generation_ids == tuple(
            item.generation_id
            for item in sorted(
                artifact.generations,
                key=lambda item: {
                    "representation_derivation_v2": 1,
                    "language_text_v2": 2,
                    "multilingual_embedding_v2": 3,
                    "multilingual_vector_v2": 4,
                }[item.capability],
            )
        )
        assert runtime.identity.database_identity == artifact.database_identity
    finally:
        await assembler.close()


def test_server_owned_registration_composes_real_production_adapters() -> None:
    asyncio.run(_compose())


def test_production_assembler_rejects_cross_store_authorization_engine() -> None:
    async def reject() -> None:
        verifier = GovernedV2DatabaseIdentityVerifier(
            workspace_root=ROOT,
            identity_manifest=MANIFEST,
        )
        artifact = verifier.artifact
        identity = V2RuntimeIdentityV1(
            profile_id="full_multilingual_v2_local_prebuild",
            profile_fingerprint=artifact.profile_fingerprint,
            vector_space_identity=artifact.vector_space_identity,
            build_run_id=artifact.build_run_id,
            database_identity=artifact.database_identity,
            alias_set_digest="a" * 64,
            query_preprocessing_identity="query-preprocessing",
            document_preprocessing_identity="document-preprocessing",
            authorization_service_id="central-v1-plus-v2",
            provenance_validator_id="v2-provenance-validator/1",
            reranker_public_protocol_id="multilingual-reranker/3",
            provider_identity="sentence-transformers",
        )
        assembler = ProductionFullMultilingualV2ServerDependencyAssemblerV1(
            workspace_root=ROOT,
            identity_manifest=MANIFEST,
            identity=identity,
            support=V2ProductionRuntimeSupportV1(
                query_embedder=cast(Any, _NoInferenceQueryEmbedder()),
                candidate_builder_factory=_builder,
                reranker=cast(Any, _NoInferenceReranker()),
                admission=cast(Any, _Admission()),
                query_language_resolver=cast(Any, _QueryLanguageResolver()),
                exhaustive_fallback=cast(AdvancedRetrievalSourceV1, _Fallback()),
            ),
        )
        unsafe_engine = cast(
            KnowledgeEngine,
            SimpleNamespace(
                config=SimpleNamespace(
                    storage=SimpleNamespace(
                        sqlite=SimpleNamespace(
                            path=(ROOT / "data/canonical_production/mnemo_canonical.db").resolve()
                        )
                    )
                )
            ),
        )
        with pytest.raises(RuntimeError, match="PRODUCTION_STORE_CONFIGURATION_MISMATCH"):
            await assembler.assemble_v2_runtime_dependencies(
                engine=unsafe_engine,
                authorization=cast(Any, object()),
            )

    asyncio.run(reject())


class _Central:
    async def authorize_notebook(
        self, principal: Any, _: object, __: object, **___: object
    ) -> object:
        return SimpleNamespace(allowed=True, actor_id=principal.actor_id)


class _Active:
    def __init__(self, ids: tuple[object, ...]) -> None:
        self.ids = ids

    async def resolve_active_multilingual_v2_generation_set(self) -> tuple[object, ...]:
        return self.ids


class _Inspector:
    async def inspect_active_v2_generations(self, ids: tuple[object, ...]) -> tuple[()]:
        assert len(ids) == 4
        return ()


def _plan() -> RetrievalPlanV2:
    return RetrievalPlanV2(
        query="authorization-only",
        mode=AdvancedRetrievalMode.RANKED,
        scope=RetrievalScopeV2(notebook_id=uuid4()),
        representations=(EvidenceRepresentation.MULTILINGUAL_TEXT,),
        budgets=RetrievalBudgetsV2(
            recall_limit=1,
            expansion_limit=0,
            fusion_limit=1,
            rerank_limit=1,
            result_limit=1,
            max_serialized_bytes=1000,
            max_content_characters=100,
        ),
        ranking_policy=RankingPolicyV2.SOURCE_RANK_FUSION,
    )


def test_v2_authorizer_requires_server_principal_and_returns_bounded_decision() -> None:
    verifier = GovernedV2DatabaseIdentityVerifier(
        workspace_root=ROOT,
        identity_manifest=MANIFEST,
    )
    identity = V2RuntimeIdentityV1(
        profile_id="full_multilingual_v2_local_prebuild",
        profile_fingerprint=verifier.artifact.profile_fingerprint,
        vector_space_identity=verifier.artifact.vector_space_identity,
        build_run_id=verifier.artifact.build_run_id,
        database_identity=verifier.artifact.database_identity,
        alias_set_digest="b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0",
        query_preprocessing_identity="q",
        document_preprocessing_identity="d",
        authorization_service_id="a",
        provenance_validator_id="p",
        reranker_public_protocol_id="r",
        provider_identity="provider",
    )
    ids = tuple(
        item.generation_id
        for item in sorted(
            verifier.artifact.generations,
            key=lambda item: {
                "representation_derivation_v2": 1,
                "language_text_v2": 2,
                "multilingual_embedding_v2": 3,
                "multilingual_vector_v2": 4,
            }[item.capability],
        )
    )
    authorizer = CentralV2RetrievalAuthorizerV1(
        central=cast(Any, _Central()),
        store=cast(Any, _Active(ids)),
        inspector=cast(Any, _Inspector()),
        identity=identity,
        admission=cast(Any, _Admission()),
    )
    plan = _plan()
    principal = PrincipalContextV1(actor_id=uuid4(), authenticated=True)
    decision = asyncio.run(authorizer.authorize_v2_retrieval(principal=principal, plan=plan))
    assert decision.principal_actor_id == principal.actor_id
    assert decision.runtime_binding.generation_ids == ids
    with pytest.raises(PermissionError, match="PRINCIPAL_MISSING"):
        asyncio.run(
            authorizer.authorize_v2_retrieval(
                principal=PrincipalContextV1(actor_id=uuid4(), authenticated=False),
                plan=plan,
            )
        )
