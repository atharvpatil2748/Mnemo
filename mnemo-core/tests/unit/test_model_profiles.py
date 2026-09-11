"""Focused WP-15 model-profile registry, precedence, and readiness tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import jsonschema
import pytest
from mnemo import (
    EmbeddingConfig,
    LLMConfig,
    LLMRoleConfig,
    MnemoConfig,
    ModelProfileComponent,
    ModelProfileDocument,
    Phase85Runtime,
    Phase85ServiceRegistration,
    RerankerConfig,
    StorageConfig,
)
from pydantic import ValidationError


def _required_v1() -> str:
    return """
[llm.planner]
provider = "test"
model = "planner"
[llm.synthesizer]
provider = "test"
model = "synthesizer"
[llm.extractor]
provider = "test"
model = "extractor"
[llm.classifier]
provider = "test"
model = "classifier"
[embedding]
provider = "test"
model = "v1-embedding"
dimensions = 3
[reranker]
provider = "test"
model = "v1-reranker"
"""


def _profile_document(path: Path) -> Path:
    path.write_text(
        """
schema_version = "mnemo.model-profiles/1"
[profiles.selected]
profile_id = "selected"
version = "1"
mode = "phase8_5"
trust_class = "local_sandboxed"
certification = "candidate"
capabilities = ["multilingual_embedding", "vision"]
[profiles.selected.models.vision]
provider = "profile-provider"
model = "profile-vision"
revision = "vision-revision"
license = "apache-2.0"
preprocessing = "vision-v1"
modalities = ["image"]
[profiles.selected.models.multilingual_embedding]
provider = "profile-provider"
model = "profile-embedding"
revision = "embedding-revision"
license = "mit"
dimensions = 4
metric = "cosine"
normalization = "l2"
preprocessing = "embedding-v1"
languages = ["en", "hi", "mr"]
""",
        encoding="utf-8",
    )
    return path


def test_tracked_profile_document_and_schema_are_valid() -> None:
    root = Path(__file__).resolve().parents[3]
    path = root / "config/model_profiles/phase8_5_profiles.toml"
    schema = json.loads(
        (root / "config/model_profiles/model_profile.schema.json").read_text(encoding="utf-8")
    )
    document = ModelProfileDocument.from_file(path)
    jsonschema.validate(document.model_dump(mode="json", exclude_none=True), schema)
    selected = document.select("phase8_5_local_v1")
    assert selected.models["multilingual_embedding"].dimensions == 1024
    assert selected.certification.value == "candidate"
    assert document.select("v1_only").models == {}
    assert document.select("disabled").models == {}


def test_profile_schema_rejects_unpinned_invalid_and_fake_certified_models() -> None:
    component = {
        "provider": "test",
        "model": "model",
        "license": "mit",
        "preprocessing": "v1",
    }
    with pytest.raises(ValidationError, match="revision"):
        ModelProfileDocument.model_validate(
            {
                "schema_version": "mnemo.model-profiles/1",
                "profiles": {
                    "bad": {
                        "profile_id": "bad",
                        "version": "1",
                        "mode": "phase8_5",
                        "trust_class": "local_trusted",
                        "certification": "candidate",
                        "models": {"vision": component},
                    }
                },
            }
        )
    with pytest.raises(ValidationError, match="certification evidence"):
        ModelProfileDocument.model_validate(
            {
                "schema_version": "mnemo.model-profiles/1",
                "profiles": {
                    "bad": {
                        "profile_id": "bad",
                        "version": "1",
                        "mode": "phase8_5",
                        "trust_class": "local_trusted",
                        "certification": "certified",
                        "models": {"vision": {**component, "revision": "pinned"}},
                    }
                },
            }
        )


def test_provider_language_claims_are_governed_metadata_not_legacy_allowlists() -> None:
    component = ModelProfileComponent(
        provider="test",
        model="generic-multilingual-model",
        revision="exact-revision",
        license="test-only",
        preprocessing="document-v1",
        languages=("legacy-regression-only",),
        language_claims=(
            {
                "language": "fr",
                "script": "Latn",
                "operations": ("dense_retrieval", "embedding"),
                "claim_source_digest": "0" * 64,
            },
        ),
    )
    assert component.language_claims[0].language == "fr"
    assert component.language_claims[0].operations == ("dense_retrieval", "embedding")
    with pytest.raises(ValidationError, match="sorted, unique"):
        ModelProfileComponent(
            provider="test",
            model="generic-multilingual-model",
            revision="exact-revision",
            license="test-only",
            preprocessing="document-v1",
            language_claims=(
                {
                    "language": "fr",
                    "operations": ("embedding", "embedding"),
                    "claim_source_digest": "0" * 64,
                },
            ),
        )


def test_inline_enabled_profile_requires_an_immutable_revision() -> None:
    with pytest.raises(ValidationError, match="provider, model, and revision"):
        MnemoConfig.model_validate(
            {
                "llm": LLMConfig(
                    planner=LLMRoleConfig(provider="test", model="planner", max_context_tokens=16),
                    synthesizer=LLMRoleConfig(
                        provider="test", model="synthesizer", max_context_tokens=16
                    ),
                    extractor=LLMRoleConfig(
                        provider="test", model="extractor", max_context_tokens=16
                    ),
                    classifier=LLMRoleConfig(
                        provider="test", model="classifier", max_context_tokens=16
                    ),
                ),
                "embedding": EmbeddingConfig(provider="test", model="v1", dimensions=3),
                "reranker": RerankerConfig(provider="test", model="v1"),
                "models": {
                    "vision": {"provider": "test", "model": "vision"},
                },
            }
        )


def test_profile_precedence_is_environment_then_inline_then_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _profile_document(tmp_path / "profiles.toml")
    config_file = tmp_path / "mnemo.toml"
    config_file.write_text(
        _required_v1()
        + f"""
[phase85]
profile_file = "{profile.name}"
profile_name = "selected"
[models.multilingual_embedding]
provider = "inline-provider"
model = "inline-embedding"
revision = "inline-revision"
dimensions = 7
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("MNEMO_MODELS_MULTILINGUAL_EMBEDDING_MODEL", "environment-embedding")
    config = MnemoConfig.from_file(config_file)
    assert config.models.vision.model == "profile-vision"
    assert config.models.multilingual_embedding.provider == "inline-provider"
    assert config.models.multilingual_embedding.model == "environment-embedding"
    assert config.models.multilingual_embedding.dimensions == 7
    assert config.embedding.model == "v1-embedding"


def test_missing_profile_and_operator_model_root_fail_or_resolve_deterministically(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.toml"
    config_file = tmp_path / "mnemo.toml"
    config_file.write_text(
        _required_v1()
        + f"""
[phase85]
profile_file = "{missing.name}"
profile_name = "selected"
""",
        encoding="utf-8",
    )
    with pytest.raises(FileNotFoundError, match="profile document"):
        MnemoConfig.from_file(config_file)

    profile = _profile_document(tmp_path / "profiles.toml")
    config_file.write_text(
        _required_v1()
        + f"""
[phase85]
profile_file = "{profile.name}"
profile_name = "selected"
model_root = "./operator-model-cache"
""",
        encoding="utf-8",
    )
    config = MnemoConfig.from_file(config_file)
    assert config.phase85.model_root == tmp_path / "operator-model-cache"
    assert "operator-model-cache" not in json.dumps(
        Phase85Runtime(config, engine_ready=False).active_profile.public_metadata()
    )


@pytest.mark.parametrize("profile_name,mode", [("v1_only", "v1_only"), ("disabled", "disabled")])
def test_reduced_profiles_keep_v1_ready_and_phase85_truthfully_disabled(
    profile_name: str, mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv("MNEMO_PHASE85_PROFILE_NAME", profile_name)
    config = MnemoConfig.from_file(root / "mnemo.toml")
    runtime = Phase85Runtime(
        config,
        engine_ready=True,
        active_v1_profiles=frozenset({"v1.embedding", "v1.reranker"}),
        core_active_capabilities=frozenset(
            {"canonical_ingestion", "v1_retrieval", "capability_discovery"}
        ),
    )
    asyncio.run(runtime.initialize())
    assert runtime.active_profile.mode.value == mode
    assert runtime.readiness().runtime_ready
    assert runtime.capability_status("v1_retrieval").state.active
    assert runtime.capability_status("capability_discovery").reason_code == "profile_disabled"
    assert not runtime.profile_status("vision").state.configured


def test_generation_profile_mismatch_fails_readiness(tmp_path: Path) -> None:
    role = LLMRoleConfig(provider="test", model="local", max_context_tokens=16)
    config = MnemoConfig(
        storage=StorageConfig(),
        llm=LLMConfig(planner=role, synthesizer=role, extractor=role, classifier=role),
        embedding=EmbeddingConfig(provider="test", model="v1", dimensions=3),
        reranker=RerankerConfig(provider="test", model="v1"),
    )
    runtime = Phase85Runtime(
        config,
        engine_ready=True,
        service_registrations=(
            Phase85ServiceRegistration(
                capability_id="structured_retrieval",
                service=object(),
                ready=True,
                activate=True,
                generation_id="generation",
                generation_active=True,
                profile_fingerprint="0" * 64,
            ),
        ),
    )
    asyncio.run(runtime.initialize())
    status = runtime.capability_status("structured_retrieval")
    assert not status.state.ready
    assert status.reason_code == "profile_generation_mismatch"


def test_dimension_override_changes_generation_profile_identity(tmp_path: Path) -> None:
    profile = _profile_document(tmp_path / "profiles.toml")
    base_file = tmp_path / "base.toml"
    changed_file = tmp_path / "changed.toml"
    selection = f'\n[phase85]\nprofile_file = "{profile.name}"\nprofile_name = "selected"\n'
    base_file.write_text(_required_v1() + selection, encoding="utf-8")
    changed_file.write_text(
        _required_v1()
        + selection
        + """
[models.multilingual_embedding]
dimensions = 5
""",
        encoding="utf-8",
    )

    base = Phase85Runtime(MnemoConfig.from_file(base_file), engine_ready=False)
    changed = Phase85Runtime(MnemoConfig.from_file(changed_file), engine_ready=False)
    assert base.active_profile.components["multilingual_embedding"].dimensions == 4
    assert changed.active_profile.components["multilingual_embedding"].dimensions == 5
    assert base.active_profile.fingerprint != changed.active_profile.fingerprint


def test_runtime_profile_fingerprint_is_deterministic_and_path_free() -> None:
    root = Path(__file__).resolve().parents[3]
    first = Phase85Runtime(MnemoConfig.from_file(root / "mnemo.toml"), engine_ready=False)
    second = Phase85Runtime(MnemoConfig.from_file(root / "mnemo.toml"), engine_ready=False)
    assert first.active_profile == second.active_profile
    assert first.configuration_fingerprint == second.configuration_fingerprint
    public = json.dumps(first.active_profile.public_metadata(), sort_keys=True)
    assert "C:\\" not in public and "file://" not in public
    assert "phase8_5_profiles.toml" not in public
