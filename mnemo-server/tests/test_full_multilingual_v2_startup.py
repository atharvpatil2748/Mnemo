"""Governed startup composition tests for the certified Full Multilingual V2 runtime."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from mnemo.models.multilingual import LanguageCode
from mnemo_server.services import full_multilingual_v2_startup as subject


def test_profile_claim_admission_is_operation_scoped() -> None:
    admission = subject._ProfileClaimAdmissionV1(
        embedding_languages=frozenset({"en", "hi"}),
        reranker_languages=frozenset({"en"}),
    )
    assert admission.permits(language=LanguageCode("hi"), operation="dense_retrieval")
    assert admission.permits(language=LanguageCode("en"), operation="sparse_retrieval")
    assert admission.permits(language=LanguageCode("en"), operation="reranking")
    assert not admission.permits(language=LanguageCode("hi"), operation="reranking")
    assert not admission.permits(language=LanguageCode("en"), operation="translation")


def test_governed_query_language_resolution_rejects_missing_and_ambiguous_principal() -> None:
    resolver = subject._GovernedQueryLanguageResolverV1()

    async def scenario() -> None:
        with pytest.raises(PermissionError, match="principal"):
            await resolver.resolve_query_language(
                principal=object(), notebook_id=uuid4(), query="the system and this"
            )
        principal = SimpleNamespace(actor_id=uuid4())
        resolved = await resolver.resolve_query_language(
            principal=principal, notebook_id=uuid4(), query="the system and this"
        )
        assert resolved == LanguageCode("en")
        with pytest.raises(LookupError, match="unresolved"):
            await resolver.resolve_query_language(
                principal=principal, notebook_id=uuid4(), query="कर्म धर्म"
            )

    asyncio.run(scenario())


def test_installed_runtime_close_rolls_back_only_active_reranker() -> None:
    events: list[str] = []

    class Reranker:
        mode = subject.V2RerankerMode.BGE_V2_M3

    class Activation:
        async def rollback(self) -> None:
            events.append("rollback")

    class Resource:
        def __init__(self, name: str) -> None:
            self.name = name

        async def close(self) -> None:
            events.append(self.name)

    runtime = subject.InstalledFullMultilingualV2RuntimeV1(
        assembler=Resource("assembler"),  # type: ignore[arg-type]
        embedding=Resource("embedding"),  # type: ignore[arg-type]
        reranker=Reranker(),  # type: ignore[arg-type]
        reranker_activation=Activation(),  # type: ignore[arg-type]
        exposure_snapshot=SimpleNamespace(),  # type: ignore[arg-type]
    )
    asyncio.run(runtime.close())
    assert events == ["rollback", "assembler", "embedding"]

    events.clear()
    Reranker.mode = subject.V2RerankerMode.PASS_THROUGH
    asyncio.run(runtime.close())
    assert events == ["assembler", "embedding"]


def test_install_production_runtime_binds_identity_and_exposure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    generation_ids = tuple(uuid4() for _ in range(4))
    target = Path("data/corpus.db")
    fingerprint = "a" * 64
    artifact = SimpleNamespace(
        target_path=target,
        profile_fingerprint=fingerprint,
        vector_space_identity="b" * 64,
        build_run_id=uuid4(),
        database_identity="c" * 64,
        generations=tuple(
            SimpleNamespace(
                generation_id=value,
                capability=("multilingual_embedding_v2" if index == 2 else f"capability-{index}"),
            )
            for index, value in enumerate(generation_ids)
        ),
    )

    class Verifier:
        def __init__(self, **_: object) -> None:
            self.artifact = artifact

    class ProfileDocument:
        @classmethod
        def from_file(cls, path: Path) -> ProfileDocument:
            assert path.name.endswith(".toml")
            return cls()

        def select(self, name: str) -> str:
            assert name == subject.PROFILE_NAME
            return "selected"

    claims = (SimpleNamespace(language="en", operations=("query_embedding", "reranking")),)
    components = {
        "multilingual_embedding": SimpleNamespace(language_claims=claims),
        "multilingual_reranker": SimpleNamespace(language_claims=claims),
    }
    snapshot = SimpleNamespace(profile_id="profile", fingerprint=fingerprint, components=components)

    class Store:
        def __init__(self, path: Path) -> None:
            assert path == (tmp_path / target)

        async def open(self) -> None:
            events.append("store-open")

        async def close(self) -> None:
            events.append("store-close")

        async def resolve_active_multilingual_v2_generation_set(self) -> tuple[UUID, ...]:
            return generation_ids

        async def resolve_active_multilingual_v2_alias_digest(self) -> str:
            return "d" * 64

    class Inspector:
        def __init__(self, **_: object) -> None:
            pass

        async def inspect_active_v2_generations(self, values: tuple[UUID, ...]) -> None:
            assert values == generation_ids
            events.append("inspected")

    class Embedding:
        def __init__(self, *_: object, generation_id: UUID, **__: object) -> None:
            assert generation_id == generation_ids[2]

        async def initialize(self) -> None:
            events.append("embedding-open")

        async def close(self) -> None:
            events.append("embedding-close")

    class Assembler:
        def __init__(self, **kwargs: object) -> None:
            self.support = kwargs["support"]

        async def close(self) -> None:
            events.append("assembler-close")

    advanced_source = SimpleNamespace(representation="multilingual_text")

    class Registration:
        def __init__(self, **kwargs: object) -> None:
            assert isinstance(kwargs["assembler"], Assembler)

        async def compose_internal_runtime(self) -> object:
            return SimpleNamespace(advanced_source=advanced_source)

    class Exposure:
        async def expose(self, **kwargs: object) -> object:
            assert kwargs["source"] is advanced_source
            events.append("exposed")
            return SimpleNamespace(v2_exposed=True)

    monkeypatch.setattr(subject, "GovernedV2DatabaseIdentityVerifier", Verifier)
    monkeypatch.setattr(subject, "ModelProfileDocument", ProfileDocument)
    monkeypatch.setattr(subject, "profile_snapshot", lambda _: snapshot)
    monkeypatch.setattr(subject, "SQLiteV2ReadOnlyRuntimeStore", Store)
    monkeypatch.setattr(subject, "GovernedActiveV2GenerationInspector", Inspector)
    monkeypatch.setattr(subject, "BGEM3EmbeddingProvider", Embedding)
    monkeypatch.setattr(subject, "MultilingualAdvancedStoreV1", object)
    monkeypatch.setattr(subject, "ProjectedMultilingualAdvancedSource", lambda _: advanced_source)
    monkeypatch.setattr(
        subject, "ProductionFullMultilingualV2ServerDependencyAssemblerV1", Assembler
    )
    monkeypatch.setattr(subject, "ServerOwnedFullMultilingualV2RegistrationV1", Registration)
    monkeypatch.setattr(subject, "V2ExposureAuthorityV1", Exposure)

    engine = SimpleNamespace(
        config=SimpleNamespace(
            storage=SimpleNamespace(sqlite=SimpleNamespace(path=tmp_path / target))
        ),
        storage=object(),
    )
    readiness = SimpleNamespace(
        inputs=SimpleNamespace(profile_fingerprint=fingerprint, generation_set=artifact.generations)
    )
    installed = asyncio.run(
        subject.install_production_full_multilingual_v2(
            engine=engine,  # type: ignore[arg-type]
            workspace_root=tmp_path,
            model_cache=tmp_path / "models",
            readiness=readiness,  # type: ignore[arg-type]
        )
    )
    assert installed.exposure_snapshot.v2_exposed
    assert events == ["store-open", "inspected", "store-close", "embedding-open", "exposed"]


def test_install_rejects_wrong_production_database_before_opening(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Verifier:
        def __init__(self, **_: object) -> None:
            self.artifact = SimpleNamespace(target_path=Path("governed.db"))

    monkeypatch.setattr(subject, "GovernedV2DatabaseIdentityVerifier", Verifier)
    engine = SimpleNamespace(
        config=SimpleNamespace(
            storage=SimpleNamespace(sqlite=SimpleNamespace(path=tmp_path / "other.db"))
        )
    )
    with pytest.raises(RuntimeError, match="PRODUCTION_STORE_CONFIGURATION_MISMATCH"):
        asyncio.run(
            subject.install_production_full_multilingual_v2(
                engine=engine,  # type: ignore[arg-type]
                workspace_root=tmp_path,
                model_cache=tmp_path,
                readiness=SimpleNamespace(),  # type: ignore[arg-type]
            )
        )
