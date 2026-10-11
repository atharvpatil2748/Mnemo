"""Disposable admission tests for the isolated Full V2 runtime composer."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from mnemo.interfaces.advanced_retrieval import MultilingualAdvancedStoreV1
from mnemo.models.multilingual import LanguageCode
from mnemo.phase85.rebuild_language_capability import RebuildLanguageCapability
from mnemo_server.services import isolated_full_v2_serving as serving
from mnemo_server.tools import isolated_activation


@pytest.mark.anyio
async def test_isolated_query_admission_is_provider_scoped_not_three_language_scoped() -> None:
    capability = RebuildLanguageCapability(
        identity="a" * 64,
        scope="multilingual_unenumerated",
        operations=frozenset({"query_embedding", "document_embedding"}),
    )
    admission = serving._CommonSpaceAdmission(capability)
    resolver = serving._CommonSpaceQueryLanguageResolver()
    principal = SimpleNamespace(actor_id=uuid4())
    for query in ("Bonjour le monde entier", "こんにちは、これは日本語です", "مرحبا بالعالم"):
        language = await resolver.resolve_query_language(
            principal=principal, notebook_id=uuid4(), query=query
        )
        assert isinstance(language, LanguageCode)
        assert admission.permits(language=language, operation="dense_retrieval")
    assert not admission.permits(language=LanguageCode("fr"), operation="unknown")
    with pytest.raises(PermissionError):
        await resolver.resolve_query_language(
            principal=object(), notebook_id=uuid4(), query="Bonjour le monde entier"
        )


@pytest.mark.anyio
async def test_isolated_full_v2_installs_only_authorized_active_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "canary"
    runtime.mkdir()
    database = runtime / "mnemo.db"
    generations = tuple(uuid4() for _ in range(4))
    notebook = uuid4()
    alias = "a" * 64
    db_identity = "b" * 64
    auth_id = str(uuid4())
    auth_digest = "c" * 64
    text_space = "d" * 64
    fingerprint = "e" * 64
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE multilingual_v2_activation_records("
            "alias_set_digest TEXT,activation_mode TEXT,recovery_mode TEXT,"
            "authorization_id TEXT,authorization_digest TEXT)"
        )
        connection.execute(
            "INSERT INTO multilingual_v2_activation_records VALUES(?,?,?,?,?)",
            (alias, "first_v2_activation", "deactivate_v2_alias_set", auth_id, auth_digest),
        )
    report = {
        "state": "active_internal_only",
        "notebook_id": str(notebook),
        "database_identity": db_identity,
        "generation_ids": [str(item) for item in generations],
        "alias_set_digest": alias,
        "authorization_id": auth_id,
        "authorization_digest": auth_digest,
    }
    (runtime / "full-v2-serving.json").write_text(json.dumps(report), encoding="utf-8")
    artifact = SimpleNamespace(
        notebook_id=notebook,
        database_identity=db_identity,
        generation_ids=generations,
        vector_space_identity=text_space,
        profile_fingerprint=fingerprint,
        build_run_id=uuid4(),
    )
    binding = SimpleNamespace(
        model_identity="BAAI/bge-m3@revision",
        embedding_generation_id=generations[2],
        dimensions=1024,
    )

    class Verifier:
        artifact: object = None

        def __init__(self, **kwargs: object) -> None:
            pass

        def verify(self, **kwargs: object) -> None:
            assert kwargs["expected_database_identity"] == db_identity

        def resolve_vector_embedding_generation(self, **kwargs: object) -> object:
            assert kwargs["active_generation_ids"] == generations
            return binding

    Verifier.artifact = artifact
    monkeypatch.setattr(serving, "IsolatedV2DatabaseIdentityVerifier", Verifier)

    class RuntimeStore:
        def __init__(self, path: Path) -> None:
            assert path == database

        async def open(self) -> None:
            pass

        async def close(self) -> None:
            pass

        async def resolve_active_multilingual_v2_generation_set(self) -> object:
            return generations

        async def resolve_active_multilingual_v2_alias_digest(self) -> str:
            return alias

        async def inspect_active_v2_generations(self, active: object) -> object:
            assert active == generations
            return [SimpleNamespace(profile_id="profile") for _ in generations]

    monkeypatch.setattr(serving, "SQLiteV2ReadOnlyRuntimeStore", RuntimeStore)
    component = SimpleNamespace(
        model="BAAI/bge-m3",
        revision="revision",
        provider="sentence-transformers",
        language_claims=(),
    )
    monkeypatch.setattr(
        serving.ModelProfileDocument,
        "from_file",
        lambda _: SimpleNamespace(
            select=lambda _: SimpleNamespace(models={"multilingual_embedding": component})
        ),
    )

    class Embedding:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def initialize(self) -> None:
            pass

        async def profile(self) -> object:
            return SimpleNamespace(vector_space=text_space, dimension=1024)

        async def close(self) -> None:
            pass

    monkeypatch.setattr(serving, "BGEM3EmbeddingProvider", Embedding)
    capability = SimpleNamespace(
        identity="f" * 64, scope="multilingual_unenumerated", permits=lambda _: True
    )
    monkeypatch.setattr(serving, "load_rebuild_language_capability", lambda **_: capability)
    (runtime / "multilingual-stage.json").write_text(
        json.dumps(
            {
                "language_capability_identity": capability.identity,
                "profile_fingerprint": fingerprint,
                "execution_device": "cpu",
            }
        ),
        encoding="utf-8",
    )

    class Assembler:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["isolated_database"] == database

        async def close(self) -> None:
            pass

    class Registration:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def compose_internal_runtime(self) -> object:
            return SimpleNamespace(generation_ids=generations)

    monkeypatch.setattr(
        serving, "ProductionFullMultilingualV2ServerDependencyAssemblerV1", Assembler
    )
    monkeypatch.setattr(serving, "ServerOwnedFullMultilingualV2RegistrationV1", Registration)
    installed: list[object] = []

    async def install(*, runtime: object) -> None:
        installed.append(runtime)

    engine = SimpleNamespace(
        config=SimpleNamespace(storage=SimpleNamespace(sqlite=SimpleNamespace(path=database))),
        storage=MagicMock(spec=MultilingualAdvancedStoreV1),
        install_internal_full_multilingual_v2=install,
    )
    result = await serving.install_isolated_full_v2(
        engine=engine, workspace=tmp_path, runtime=runtime, model_cache=tmp_path
    )
    assert result.generation_ids == generations
    assert len(installed) == 1
    assert result.visual_status == "compatible_text_query_snapshot_not_supplied"
    await result.close()

    visual_generation = str(uuid4())
    with sqlite3.connect(database) as connection:
        connection.executescript(
            "CREATE TABLE visual_embeddings(derivation_id TEXT,payload TEXT);"
            "CREATE TABLE visual_vector_projection_rows(derivation_id TEXT,generation_id TEXT);"
            "CREATE TABLE active_index_generations(generation_id TEXT);"
            "CREATE TABLE index_generations(generation_id TEXT,state TEXT);"
        )
        connection.execute(
            "INSERT INTO visual_embeddings VALUES(?,?)",
            (
                "visual-derivation",
                json.dumps(
                    {
                        "provider": {
                            "profile_id": "clip-profile",
                            "model_identity": "openai/clip-vit-large-patch14",
                            "model_revision": "revision",
                        },
                        "shared_space_id": "openai/clip-vit-large-patch14@revision",
                        "dimensions": 768,
                        "metric": "cosine",
                    }
                ),
            ),
        )
        connection.execute(
            "INSERT INTO visual_vector_projection_rows VALUES(?,?)",
            ("visual-derivation", visual_generation),
        )
        connection.execute("INSERT INTO active_index_generations VALUES(?)", (visual_generation,))
        connection.execute("INSERT INTO index_generations VALUES(?,'ready')", (visual_generation,))
    clip_snapshot = tmp_path / "revision"
    clip_snapshot.mkdir()
    visual_installed: list[object] = []

    async def install_visual(*, provider: object) -> None:
        visual_installed.append(provider)

    engine.install_internal_visual_query_provider = install_visual
    monkeypatch.setattr(serving, "LocalCLIPTextQueryProvider", lambda **kwargs: kwargs)
    visual_result = await serving.install_isolated_full_v2(
        engine=engine,
        workspace=tmp_path,
        runtime=runtime,
        model_cache=tmp_path,
        clip_snapshot=clip_snapshot,
    )
    assert visual_result.visual_status == "active_matching_clip_text_query"
    assert visual_installed[0]["shared_space_id"] == "openai/clip-vit-large-patch14@revision"
    await visual_result.close()

    report["authorization_digest"] = "wrong"
    (runtime / "full-v2-serving.json").write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="authorization"):
        await serving.install_isolated_full_v2(
            engine=engine, workspace=tmp_path, runtime=runtime, model_cache=tmp_path
        )


@pytest.mark.anyio
async def test_full_v2_alias_first_activation_and_authorized_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "canary"
    runtime.mkdir()
    database = runtime / "mnemo.db"
    notebook, run = uuid4(), uuid4()
    generations = tuple(uuid4() for _ in range(4))
    artifact = SimpleNamespace(
        notebook_id=notebook,
        build_run_id=run,
        database_identity="a" * 64,
        profile_fingerprint="b" * 64,
        vector_space_identity="c" * 64,
        generation_ids=generations,
    )
    decision = {
        "notebook_id": str(notebook),
        "active": True,
        "generations": {
            capability: {"generation_id": str(identifier)}
            for capability, identifier in zip(
                (
                    "representation_derivation_v2",
                    "language_text_v2",
                    "multilingual_embedding_v2",
                    "multilingual_vector_v2",
                ),
                generations,
                strict=True,
            )
        },
    }
    (runtime / "activation-decision.json").write_text(json.dumps(decision), encoding="utf-8")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE multilingual_v2_activation_records("
            "alias_set_digest TEXT,activation_mode TEXT,recovery_mode TEXT,"
            "authorization_id TEXT,authorization_digest TEXT)"
        )

    class Verifier:
        artifact: object = None

        def __init__(self, **kwargs: object) -> None:
            pass

        def verify(self, **kwargs: object) -> None:
            assert kwargs["expected_database_identity"] == artifact.database_identity

    Verifier.artifact = artifact
    monkeypatch.setattr(isolated_activation, "IsolatedV2DatabaseIdentityVerifier", Verifier)
    state: dict[str, object] = {"active": None, "alias": None}

    class Store:
        def __init__(self, path: Path) -> None:
            assert path == database

        async def open(self) -> None:
            pass

        async def close(self) -> None:
            pass

        async def resolve_active_multilingual_v2_generation_set(self) -> object:
            return state["active"]

        async def resolve_active_multilingual_v2_alias_digest(self) -> object:
            return state["alias"]

        async def promote_multilingual_v2_alias_set(self, **kwargs: object) -> str:
            assert kwargs["generation_ids"] == generations
            assert kwargs["activation_mode"] == "first_v2_activation"
            alias = "d" * 64
            state.update(active=generations, alias=alias)
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "INSERT INTO multilingual_v2_activation_records VALUES(?,?,?,?,?)",
                    (
                        alias,
                        kwargs["activation_mode"],
                        kwargs["recovery_mode"],
                        str(kwargs["authorization_id"]),
                        kwargs["authorization_digest"],
                    ),
                )
            return alias

    monkeypatch.setattr(isolated_activation, "SQLiteStore", Store)
    first = await isolated_activation.compose_isolated_full_v2_alias(
        workspace=tmp_path, runtime=runtime
    )
    assert first["state"] == "active_internal_only"
    assert first["alias_set_digest"] == "d" * 64
    assert first["authorization_digest"]
    assert (runtime / "full-v2-serving.json").exists()
    repeated = await isolated_activation.compose_isolated_full_v2_alias(
        workspace=tmp_path, runtime=runtime
    )
    assert repeated == first
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE multilingual_v2_activation_records SET authorization_digest='wrong'"
        )
    with pytest.raises(ValueError, match="serving authorization"):
        await isolated_activation.compose_isolated_full_v2_alias(
            workspace=tmp_path, runtime=runtime
        )
