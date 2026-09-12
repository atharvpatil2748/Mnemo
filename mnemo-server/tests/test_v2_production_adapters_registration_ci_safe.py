from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces.advanced_retrieval import AdvancedRetrievalSourceV1
from mnemo.models.advanced_retrieval import EvidenceRepresentation
from mnemo.models.multilingual import LanguageCode
from mnemo.phase85.v2_database_identity import GovernedV2DatabaseIdentityVerifier
from mnemo.phase85.v2_evaluation_runtime import V2RuntimeIdentityV1
from mnemo.retrieval.reranker_candidates import (
    RenderedRerankerPairV1,
    RerankerCandidateBuilderV1,
)
from mnemo_server.services.full_multilingual_v2_production import (
    ProductionFullMultilingualV2ServerDependencyAssemblerV1,
    V2ProductionRuntimeSupportV1,
)
from mnemo_server.services.full_multilingual_v2_registration import (
    ServerOwnedFullMultilingualV2RegistrationV1,
)

from tests.v2_test_fixtures import create_synthetic_v2_db

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
ORIGINAL_MANIFEST = (
    WORKSPACE_ROOT
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


def _prepare_isolated_environment(tmp_path: Path) -> tuple[Path, Path, V2RuntimeIdentityV1]:
    # 1. Create a modified manifest with target_path="synthetic_v2.db"
    raw = json.loads(ORIGINAL_MANIFEST.read_text(encoding="utf-8"))
    raw["target_path"] = "synthetic_v2.db"
    payload = {k: v for k, v in raw.items() if k != "database_identity"}
    new_db_identity = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    raw["database_identity"] = new_db_identity

    manifest_path = tmp_path / "identity.json"
    manifest_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    # 2. Create the synthetic database
    db_path = tmp_path / "synthetic_v2.db"
    create_synthetic_v2_db(db_path, manifest_path)

    # 3. Build the identity matching the new manifest
    verifier = GovernedV2DatabaseIdentityVerifier(
        workspace_root=tmp_path,
        identity_manifest=manifest_path,
    )
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
    return manifest_path, db_path, identity


@pytest.mark.anyio
async def test_ci_safe_server_owned_registration_composes_adapters(tmp_path: Path) -> None:
    manifest_path, db_path, identity = _prepare_isolated_environment(tmp_path)

    assembler = ProductionFullMultilingualV2ServerDependencyAssemblerV1(
        workspace_root=tmp_path,
        identity_manifest=manifest_path,
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
                storage=SimpleNamespace(sqlite=SimpleNamespace(path=db_path.resolve()))
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
        assert runtime.identity.database_identity == identity.database_identity
        assert len(runtime.generation_ids) == 4
    finally:
        await assembler.close()


@pytest.mark.anyio
async def test_ci_safe_registration_error_branches(tmp_path: Path) -> None:
    manifest_path, db_path, identity = _prepare_isolated_environment(tmp_path)

    # Error branch: assembler type check
    with pytest.raises(TypeError, match="port"):
        ServerOwnedFullMultilingualV2RegistrationV1(
            engine=cast(Any, SimpleNamespace()),
            identity=identity,
            assembler=cast(Any, object()),
        )

    assembler = ProductionFullMultilingualV2ServerDependencyAssemblerV1(
        workspace_root=tmp_path,
        identity_manifest=manifest_path,
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

    # Error branch: store configuration mismatch
    mismatched_engine = cast(
        KnowledgeEngine,
        SimpleNamespace(
            config=SimpleNamespace(
                storage=SimpleNamespace(
                    sqlite=SimpleNamespace(path=(tmp_path / "other.db").resolve())
                )
            )
        ),
    )
    with pytest.raises(RuntimeError, match="PRODUCTION_STORE_CONFIGURATION_MISMATCH"):
        await assembler.assemble_v2_runtime_dependencies(
            engine=mismatched_engine,
            authorization=cast(Any, object()),
        )

    # Error branch: database binding mismatch
    mismatched_identity = identity.__class__(
        profile_id=identity.profile_id,
        profile_fingerprint=identity.profile_fingerprint,
        vector_space_identity=identity.vector_space_identity,
        build_run_id=identity.build_run_id,
        database_identity="0" * 64,
        alias_set_digest=identity.alias_set_digest,
        query_preprocessing_identity=identity.query_preprocessing_identity,
        document_preprocessing_identity=identity.document_preprocessing_identity,
        authorization_service_id=identity.authorization_service_id,
        provenance_validator_id=identity.provenance_validator_id,
        reranker_public_protocol_id=identity.reranker_public_protocol_id,
        provider_identity=identity.provider_identity,
    )
    mismatched_assembler = ProductionFullMultilingualV2ServerDependencyAssemblerV1(
        workspace_root=tmp_path,
        identity_manifest=manifest_path,
        identity=mismatched_identity,
        support=V2ProductionRuntimeSupportV1(
            query_embedder=cast(Any, _NoInferenceQueryEmbedder()),
            candidate_builder_factory=_builder,
            reranker=cast(Any, _NoInferenceReranker()),
            admission=cast(Any, _Admission()),
            query_language_resolver=cast(Any, _QueryLanguageResolver()),
            exhaustive_fallback=cast(AdvancedRetrievalSourceV1, _Fallback()),
        ),
    )
    matching_engine = cast(
        KnowledgeEngine,
        SimpleNamespace(
            config=SimpleNamespace(
                storage=SimpleNamespace(sqlite=SimpleNamespace(path=db_path.resolve()))
            )
        ),
    )
    with pytest.raises(RuntimeError, match="DATABASE_BINDING_MISMATCH"):
        await mismatched_assembler.assemble_v2_runtime_dependencies(
            engine=matching_engine,
            authorization=cast(Any, object()),
        )
