from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from mnemo.interfaces.errors import ContractValidationError
from mnemo.models.advanced_retrieval import PositionalScopeV2, RetrievalScopeV2
from mnemo.models.multilingual import LanguageCode, multilingual_vector_space_identity
from mnemo.models.v2_retrieval_authorization import (
    V2ActiveRuntimeBindingV1,
    V2RetrievalAuthorizationDecisionV1,
)
from mnemo.phase85.full_multilingual_v2 import (
    MultilingualVectorGenerationBuilderV2,
    full_multilingual_v2_generation_plan,
)
from mnemo.phase85.profiles import ModelProfileDocument
from mnemo.phase85.v2_build_authorization import (
    V2BuildAuthorizationV1,
    validate_v2_build_authorization,
)
from mnemo.retrieval.multilingual_dense_v2 import (
    AuthorizedMultilingualDenseRetrievalV2,
    MultilingualDenseMatchV2,
    _cosine,
)
from mnemo.retrieval.multilingual_providers import BGEM3EmbeddingProvider

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "docs/governance/proposals/phase8_5_full_multilingual_architecture"
ZERO = "0" * 64


def _load(name: str) -> dict[str, object]:
    return json.loads((PACKAGE / name).read_text(encoding="utf-8"))


def _authorization() -> V2BuildAuthorizationV1:
    return V2BuildAuthorizationV1.from_mapping(_load("V2_INDEX_BUILD_AUTHORIZATION.json"))


def _validate(value: V2BuildAuthorizationV1 | None) -> Path:
    return validate_v2_build_authorization(
        value,
        storage_manifest=_load("V2_DISPOSABLE_DATABASE_MANIFEST.json"),
        build_manifest=_load("V2_BUILD_RECOVERY_ROLLBACK_MANIFEST.json"),
        workspace_root=ROOT,
        protected_database_paths=(
            ROOT / "scratch/phase8_5_wp16/eval-20260828-01/mnemo.db",
            ROOT / "scratch/phase8_5_wp10_stage2/eval-20260829-01/mnemo.db",
            ROOT / "scratch/phase8_5_11/eval-20260825-02/mnemo.db",
        ),
    )


def test_canonical_vector_space_is_deterministic_and_semantic() -> None:
    fields = {
        "provider": "sentence-transformers",
        "model": "BAAI/bge-m3",
        "revision": "5617a9f61b028005a4858fdac845db406aefb181",
        "dimension": 1024,
        "normalized": True,
        "distance_metric": "cosine",
        "preprocessing_digest": "41a8b2efb281c506065b05e5abe0ebf88df3847c017184733b2de180968a073e",
    }
    first = multilingual_vector_space_identity(**fields)
    assert first == multilingual_vector_space_identity(**dict(reversed(tuple(fields.items()))))
    assert first != multilingual_vector_space_identity(**{**fields, "dimension": 768})
    assert first != multilingual_vector_space_identity(**{**fields, "normalized": False})


def test_manifest_and_provider_use_the_same_vector_space_without_model_loading() -> None:
    build = _load("V2_BUILD_RECOVERY_ROLLBACK_MANIFEST.json")
    binding = _load("V2_MODEL_PROFILE_BINDING.json")
    raw = next(
        item
        for item in build["generation_specifications"]
        if item["capability"] == "multilingual_embedding_v2"
    )
    component = (
        ModelProfileDocument.from_file(
            ROOT / "config/model_profiles/full_multilingual_v2_profiles.toml"
        )
        .select("full_multilingual_v2_local_prebuild")
        .models["multilingual_embedding"]
    )
    provider = BGEM3EmbeddingProvider(
        component,
        generation_id=UUID(raw["generation_id"]),
        cache_folder=Path(r"D:\Mnemo\phase8.5.11-models\huggingface\hub"),
    )
    assert (
        asyncio.run(provider.profile()).vector_space
        == binding["embedding"]["vector_space_profile_identity"]
        == build["vector_space_profile_identity"]
    )


def test_generation_fingerprints_and_ids_depend_on_vector_space() -> None:
    build = _load("V2_BUILD_RECOVERY_ROLLBACK_MANIFEST.json")
    raw = {item["capability"]: item for item in build["generation_specifications"]}
    common = {
        "profile_id": "profile",
        "profile_fingerprint": ZERO,
        "source_version_ids": (UUID("00000000-0000-0000-0000-000000000001"),),
        "representation_configuration_digest": "1" * 64,
        "detector_configuration_digest": "2" * 64,
        "authorization_policy_digest": "3" * 64,
        "embedding_provider_identity": "provider",
        "embedding_model_identity": "model",
        "embedding_model_revision": "revision",
        "embedding_preprocessing_digest": "4" * 64,
        "dimensions": 1024,
    }
    first = full_multilingual_v2_generation_plan(**common, vector_space_identity="5" * 64)
    same = full_multilingual_v2_generation_plan(**common, vector_space_identity="5" * 64)
    other = full_multilingual_v2_generation_plan(**common, vector_space_identity="6" * 64)
    assert first.multilingual_embedding.generation_id == same.multilingual_embedding.generation_id
    assert first.multilingual_vector.generation_id == same.multilingual_vector.generation_id
    assert first.multilingual_embedding.generation_id != other.multilingual_embedding.generation_id
    assert first.multilingual_vector.generation_id != other.multilingual_vector.generation_id
    assert raw["multilingual_embedding_v2"]["generation_id"] == (
        "62243160-bed5-5064-a664-815984232e31"
    )
    assert raw["multilingual_vector_v2"]["generation_id"] == (
        "2b26443e-bb99-5bf8-a4af-a01ba99af8ce"
    )


def test_build_authorization_is_required_and_bound_before_use() -> None:
    authorization = _authorization()
    assert _validate(authorization) == (ROOT / authorization.target_database_path).resolve(
        strict=False
    )
    with pytest.raises(ContractValidationError, match="required"):
        _validate(None)
    with pytest.raises(ContractValidationError, match="not authorized"):
        replace(authorization, authorized=False)
    with pytest.raises(ContractValidationError, match="target binding mismatch"):
        _validate(
            replace(
                authorization,
                target_database_path=("scratch/phase8_5_full_multilingual_v2/another-run/mnemo.db"),
            )
        )
    for name, value in (
        ("run_id", UUID("00000000-0000-0000-0000-000000000001")),
        ("profile_fingerprint", "1" * 64),
        ("vector_space_identity", "2" * 64),
    ):
        with pytest.raises(ContractValidationError, match="binding mismatch"):
            _validate(replace(authorization, **{name: value}))


def test_protected_or_unbounded_database_cannot_be_authorized() -> None:
    authorization = _authorization()
    for path in (
        "scratch/phase8_5_wp16/eval-20260828-01/mnemo.db",
        "../mnemo.db",
        r"C:\tmp\mnemo.db",
    ):
        with pytest.raises(ContractValidationError):
            replace(authorization, target_database_path=path)


def test_authorization_contract_is_v2_only_and_cannot_enable_runtime_exposure() -> None:
    payload = _authorization().identity_payload()
    assert payload["generation_namespace"] == "full_multilingual_v2"
    assert payload["authorization_scope"].endswith("build_generations_to_ready_only")
    assert not ({"active", "exposed", "v1"} & payload.keys())


def test_vector_generation_rejects_mismatched_vector_space() -> None:
    generation_id = UUID("00000000-0000-0000-0000-000000000010")
    source_generation_id = UUID("00000000-0000-0000-0000-000000000011")
    embedding = SimpleNamespace(
        embedding_id=UUID("00000000-0000-0000-0000-000000000012"),
        profile=SimpleNamespace(
            generation_id=source_generation_id,
            vector_space="wrong-vector-space",
        ),
    )
    builder = MultilingualVectorGenerationBuilderV2(
        generation_id=generation_id,
        source_embedding_generation_id=source_generation_id,
        vector_space_identity="governed-vector-space",
        embeddings=(embedding,),
    )
    with pytest.raises(ValueError, match="another vector space"):
        asyncio.run(builder.build(generation_id))


def test_dense_retrieval_authorizes_before_embedding_and_rejects_vector_mismatch() -> None:
    events: list[str] = []

    class Enumerator:
        async def enumerate_authorized_multilingual_sources(self, **_: object) -> tuple[()]:
            events.append("authorized_enumeration")
            return ()

    class Store:
        async def list_authorized_multilingual_embeddings_v3(self, **_: object) -> tuple[()]:
            events.append("store_enumeration")
            return ()

    class Embedder:
        async def embed_query(self, **_: object) -> object:
            events.append("query_embedding")
            return SimpleNamespace(
                profile=SimpleNamespace(vector_space="wrong-vector-space"), vector=(1.0,)
            )

    service = AuthorizedMultilingualDenseRetrievalV2(
        source_enumerator=Enumerator(),
        store=Store(),
        query_embedder=Embedder(),
        generation_id=UUID("00000000-0000-0000-0000-000000000020"),
        vector_space="governed-vector-space",
    )
    actor_id = UUID("00000000-0000-0000-0000-000000000021")
    scope = RetrievalScopeV2(notebook_id=UUID("00000000-0000-0000-0000-000000000022"))
    decision = V2RetrievalAuthorizationDecisionV1(
        decision_id=UUID("00000000-0000-0000-0000-000000000023"),
        principal_actor_id=actor_id,
        operation="retrieve",
        retrieval_scope=scope,
        positional_scope=PositionalScopeV2(),
        runtime_binding=V2ActiveRuntimeBindingV1(
            alias_set_digest=ZERO,
            generation_ids=tuple(
                UUID(f"00000000-0000-0000-0000-{value:012d}") for value in range(30, 34)
            ),
            profile_fingerprint=ZERO,
            vector_space_identity=ZERO,
            database_identity=ZERO,
            build_run_id=UUID("00000000-0000-0000-0000-000000000034"),
            admission_policy_identity="fixture/1",
        ),
        authorization_policy_identity="fixture/1",
        authorization_policy_revision="1",
        request_fingerprint=ZERO,
        issued_at="fixture",
        required_provenance_evidence=("language-evidence-reference-v3",),
    )
    with pytest.raises(ValueError, match="different vector space"):
        asyncio.run(
            service.retrieve(
                decision=decision,
                query="bounded synthetic contract test",
                query_language=LanguageCode("und"),
                limit=1,
            )
        )
    assert events == ["authorized_enumeration", "query_embedding"]


def test_dense_retrieval_enforces_scope_bounds_authorization_and_vector_math() -> None:
    notebook_id = UUID("00000000-0000-0000-0000-000000000040")
    generation_id = UUID("00000000-0000-0000-0000-000000000041")
    decision = V2RetrievalAuthorizationDecisionV1(
        decision_id=UUID("00000000-0000-0000-0000-000000000042"),
        principal_actor_id=UUID("00000000-0000-0000-0000-000000000043"),
        operation="retrieve",
        retrieval_scope=RetrievalScopeV2(notebook_id=notebook_id),
        positional_scope=PositionalScopeV2(),
        runtime_binding=V2ActiveRuntimeBindingV1(
            alias_set_digest=ZERO,
            generation_ids=tuple(
                UUID(f"00000000-0000-0000-0000-{value:012d}") for value in range(44, 48)
            ),
            profile_fingerprint=ZERO,
            vector_space_identity=ZERO,
            database_identity=ZERO,
            build_run_id=UUID("00000000-0000-0000-0000-000000000048"),
            admission_policy_identity="fixture/1",
        ),
        authorization_policy_identity="fixture/1",
        authorization_policy_revision="1",
        request_fingerprint=ZERO,
        issued_at="fixture",
        required_provenance_evidence=("language-evidence-reference-v3",),
    )

    class Enumerator:
        sources: tuple[object, ...] = ()

        async def enumerate_authorized_multilingual_sources(
            self, **_: object
        ) -> tuple[object, ...]:
            return self.sources

    class Store:
        embeddings: tuple[object, ...] = ()

        async def list_authorized_multilingual_embeddings_v3(
            self, **_: object
        ) -> tuple[object, ...]:
            return self.embeddings

    class Embedder:
        vector = (1.0, 0.0)

        async def embed_query(self, **_: object) -> object:
            return SimpleNamespace(
                profile=SimpleNamespace(vector_space="space"), vector=self.vector
            )

    enumerator, store, embedder = Enumerator(), Store(), Embedder()
    service = AuthorizedMultilingualDenseRetrievalV2(
        source_enumerator=enumerator,  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        query_embedder=embedder,  # type: ignore[arg-type]
        generation_id=generation_id,
        vector_space="space",
    )
    for invalid in (0, 1001):
        with pytest.raises(ValueError, match="result limit"):
            asyncio.run(
                service.retrieve(
                    decision=decision,
                    query="query",
                    query_language=LanguageCode("en"),
                    limit=invalid,
                )
            )

    enumerator.sources = tuple(
        SimpleNamespace(notebook_id=notebook_id, identity_digest=str(index))
        for index in range(10_001)
    )
    with pytest.raises(ValueError, match="universe exceeds"):
        asyncio.run(
            service.retrieve(
                decision=decision,
                query="query",
                query_language=LanguageCode("en"),
                limit=1,
            )
        )

    authorized = SimpleNamespace(notebook_id=notebook_id, identity_digest="authorized")
    enumerator.sources = (
        SimpleNamespace(notebook_id=UUID(int=999), identity_digest="wrong-scope"),
    )
    with pytest.raises(PermissionError, match="crossed notebook"):
        asyncio.run(
            service.retrieve(
                decision=decision,
                query="query",
                query_language=LanguageCode("en"),
                limit=1,
            )
        )

    enumerator.sources = (authorized,)
    store.embeddings = (
        SimpleNamespace(
            source=SimpleNamespace(identity_digest="unauthorized"),
            vector=(1.0, 0.0),
            embedding_id=UUID(int=2),
        ),
    )
    with pytest.raises(PermissionError, match="unauthorized evidence"):
        asyncio.run(
            service.retrieve(
                decision=decision,
                query="query",
                query_language=LanguageCode("en"),
                limit=1,
            )
        )

    store.embeddings = tuple(
        SimpleNamespace(
            source=authorized,
            vector=vector,
            embedding_id=UUID(int=identity),
        )
        for identity, vector in ((2, (0.0, 1.0)), (1, (1.0, 0.0)))
    )
    result = asyncio.run(
        service.retrieve(
            decision=decision,
            query="query",
            query_language=LanguageCode("en"),
            limit=2,
        )
    )
    assert [(item.embedding.embedding_id.int, item.score, item.rank) for item in result] == [
        (1, 1.0, 1),
        (2, 0.0, 2),
    ]

    for invalid_component in (object(),):
        with pytest.raises(TypeError):
            AuthorizedMultilingualDenseRetrievalV2(
                source_enumerator=invalid_component,  # type: ignore[arg-type]
                store=store,  # type: ignore[arg-type]
                query_embedder=embedder,  # type: ignore[arg-type]
                generation_id=generation_id,
                vector_space="space",
            )
        with pytest.raises(TypeError):
            AuthorizedMultilingualDenseRetrievalV2(
                source_enumerator=enumerator,  # type: ignore[arg-type]
                store=invalid_component,  # type: ignore[arg-type]
                query_embedder=embedder,  # type: ignore[arg-type]
                generation_id=generation_id,
                vector_space="space",
            )
        with pytest.raises(TypeError):
            AuthorizedMultilingualDenseRetrievalV2(
                source_enumerator=enumerator,  # type: ignore[arg-type]
                store=store,  # type: ignore[arg-type]
                query_embedder=invalid_component,  # type: ignore[arg-type]
                generation_id=generation_id,
                vector_space="space",
            )
    with pytest.raises(ValueError, match="non-empty"):
        AuthorizedMultilingualDenseRetrievalV2(
            source_enumerator=enumerator,  # type: ignore[arg-type]
            store=store,  # type: ignore[arg-type]
            query_embedder=embedder,  # type: ignore[arg-type]
            generation_id=generation_id,
            vector_space=" ",
        )
    with pytest.raises(ValueError, match="finite"):
        MultilingualDenseMatchV2(embedding=object(), score=float("nan"), rank=1)  # type: ignore[arg-type]
    for rank in (0, 1001):
        with pytest.raises(ValueError, match="rank"):
            MultilingualDenseMatchV2(embedding=object(), score=0.0, rank=rank)  # type: ignore[arg-type]
    assert _cosine((1.0, 0.0), (1.0, 0.0)) == 1.0
    with pytest.raises(ValueError, match="dimensions"):
        _cosine((), ())
    with pytest.raises(ValueError, match="dimensions"):
        _cosine((1.0,), (1.0, 2.0))
    with pytest.raises(ValueError, match="zero-norm"):
        _cosine((0.0,), (1.0,))
