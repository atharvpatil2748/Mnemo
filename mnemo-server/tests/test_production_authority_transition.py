"""Gate-0 authority transitions use synthetic signed generations only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from mnemo.config import MnemoConfig
from mnemo_server.config import ServerConfig
from mnemo_server.services.pre_certification_observation import (
    resolve_pre_certification_observation,
)
from mnemo_server.services.production_authority_transition import (
    commit_authority_transition,
    prepare_authority_transition,
)
from mnemo_server.services.production_runtime_binding import (
    resolve_certified_production_binding,
)
from test_pre_certification_admission import _staged
from test_production_credentials import FakeSecretStore

pytest_plugins = ("test_production_runtime_binding",)


def _prepared(
    canonical: tuple[Path, ServerConfig, MnemoConfig], monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, bytes, ServerConfig, MnemoConfig, FakeSecretStore]:
    root, _, core = canonical
    path = root / "config/production/full_multilingual_v2.production.json"
    legacy = json.loads(path.read_text(encoding="utf-8"))
    legacy["lifecycle"] = {
        "active_generation_alias": True,
        "v2_transport_exposed": True,
        "bge_reranker_activated": True,
        "evaluated": True,
        "verified": True,
        "certified": True,
    }
    legacy["reranker_activation"]["state_path"] = "operational/activation.json"
    legacy["reranker_activation"]["currently_activated"] = True
    original = (json.dumps(legacy) + "\n").encode("utf-8")
    path.write_bytes(original)
    _, config, _, _, store = _staged(canonical, monkeypatch)
    path.write_bytes(original)
    return root, path, original, config, core, store


def test_staged_registry_transition_is_atomic_and_not_certified(
    canonical: tuple[Path, ServerConfig, MnemoConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, path, original, config, core, store = _prepared(canonical, monkeypatch)
    historical = {
        name: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for name, relative in (
            ("activation", "operational/activation.json"),
            ("certificate", "operational/certification.json"),
            ("final", "operational/final-certification.json"),
        )
    }
    plan = prepare_authority_transition(root=root, secret_store=store)
    assert path.read_bytes() == original
    proposed = json.loads(plan.proposed_manifest)
    authority = proposed["configuration_authority"]
    assert authority["credential_registry"] == "operational/credentials.json"
    assert "durable_activation_state" not in authority
    assert "certified_lifecycle_state" not in authority
    assert "final_certification_evidence" not in authority
    assert proposed["lifecycle"]["certified"] is False
    assert proposed["reranker_activation"]["state_path"] == ("operational/staged-activation.json")
    assert commit_authority_transition(plan=plan, root=root, secret_store=store) == (
        hashlib.sha256(plan.proposed_manifest).hexdigest()
    )
    assert path.read_bytes() == plan.proposed_manifest
    assert resolve_pre_certification_observation(
        server_config=config, root=root, mnemo_config=core, secret_store=store
    )[1].credential_generation_id == str(plan.generation_id)
    with pytest.raises(RuntimeError, match="CERTIFIED_PRODUCTION_BINDING_REJECTED"):
        resolve_certified_production_binding(
            server_config=config,
            root=root,
            mnemo_config=core,
            environment={},
            credential_secret_store=store,
        )
    for name, relative in (
        ("activation", "operational/activation.json"),
        ("certificate", "operational/certification.json"),
        ("final", "operational/final-certification.json"),
    ):
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == historical[name]
    with pytest.raises(RuntimeError, match="TRANSITION_REJECTED"):
        prepare_authority_transition(root=root, secret_store=store)


def test_transition_rejects_missing_invalid_or_ambiguous_registry(
    canonical: tuple[Path, ServerConfig, MnemoConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, path, original, _, _, store = _prepared(canonical, monkeypatch)
    registry = root / "operational/credentials.json"
    contents = registry.read_bytes()
    registry.unlink()
    with pytest.raises(RuntimeError, match="TRANSITION_REJECTED"):
        prepare_authority_transition(root=root, secret_store=store)
    registry.write_text("{incomplete", encoding="utf-8")
    with pytest.raises(RuntimeError, match="TRANSITION_REJECTED"):
        prepare_authority_transition(root=root, secret_store=store)
    registry.write_bytes(contents)
    manifest = json.loads(original)
    manifest["configuration_authority"]["credential_registry"] = "client-selected.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="TRANSITION_REJECTED"):
        prepare_authority_transition(root=root, secret_store=store)
    manifest = json.loads(original)
    manifest["reranker_activation"]["state_path"] = "operational/other.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="TRANSITION_REJECTED"):
        prepare_authority_transition(root=root, secret_store=store)
    path.write_bytes(original)
    assert prepare_authority_transition(root=root, secret_store=store).registry_sha256


def test_transition_rejects_wrong_generation_or_changed_activation(
    canonical: tuple[Path, ServerConfig, MnemoConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, path, original, _, _, store = _prepared(canonical, monkeypatch)
    registry = root / "operational/credentials.json"
    document = json.loads(registry.read_text(encoding="utf-8"))
    original_registry = registry.read_bytes()
    document["generations"][0]["generation_id"] = str(uuid4())
    registry.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(RuntimeError, match="TRANSITION_REJECTED"):
        prepare_authority_transition(root=root, secret_store=store)
    registry.write_bytes(original_registry)
    plan = prepare_authority_transition(root=root, secret_store=store)
    activation = root / "operational/staged-activation.json"
    activation.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="TRANSITION_REJECTED"):
        commit_authority_transition(plan=plan, root=root, secret_store=store)
    assert path.read_bytes() == original


def test_interrupted_replace_preserves_manifest_and_allows_retry(
    canonical: tuple[Path, ServerConfig, MnemoConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, path, original, _, _, store = _prepared(canonical, monkeypatch)
    plan = prepare_authority_transition(root=root, secret_store=store)
    with (
        patch(
            "mnemo_server.services.production_authority_transition.os.replace",
            side_effect=OSError("synthetic interrupted write"),
        ),
        pytest.raises(OSError, match="synthetic interrupted write"),
    ):
        commit_authority_transition(plan=plan, root=root, secret_store=store)
    assert path.read_bytes() == original
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))
    assert not path.with_suffix(path.suffix + ".transition.lock").exists()
    assert commit_authority_transition(plan=plan, root=root, secret_store=store)


def test_stale_plan_and_exclusive_lock_leave_manifest_unchanged(
    canonical: tuple[Path, ServerConfig, MnemoConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, path, original, _, _, store = _prepared(canonical, monkeypatch)
    plan = prepare_authority_transition(root=root, secret_store=store)
    lock = path.with_suffix(path.suffix + ".transition.lock")
    lock.write_text("operator transition in progress", encoding="utf-8")
    with pytest.raises(RuntimeError, match="TRANSITION_LOCKED"):
        commit_authority_transition(plan=plan, root=root, secret_store=store)
    assert path.read_bytes() == original
    lock.unlink()
    altered = json.loads(original)
    altered["lifecycle"]["evaluated"] = False
    path.write_text(json.dumps(altered), encoding="utf-8")
    changed = path.read_bytes()
    with pytest.raises(RuntimeError, match="TRANSITION_CHANGED"):
        commit_authority_transition(plan=plan, root=root, secret_store=store)
    assert path.read_bytes() == changed
    assert not lock.exists()
    with pytest.raises(RuntimeError, match="TRANSITION_REJECTED"):
        commit_authority_transition(plan=plan, root=root.parent, secret_store=store)


def test_transition_rejects_incomplete_or_conflicting_staging(
    canonical: tuple[Path, ServerConfig, MnemoConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, path, original, _, _, store = _prepared(canonical, monkeypatch)
    registry = root / "operational/credentials.json"
    original_registry = registry.read_bytes()
    document = json.loads(original_registry)
    record = document["generations"][0]
    for change in (
        {"observation_campaign_id": None},
        {"secrets": [s for s in record["secrets"] if s["kind"] != "API_KEY"]},
    ):
        altered = json.loads(original_registry)
        altered["generations"][0].update(change)
        registry.write_text(json.dumps(altered), encoding="utf-8")
        with pytest.raises(RuntimeError, match="TRANSITION_REJECTED"):
            prepare_authority_transition(root=root, secret_store=store)
    altered = json.loads(original_registry)
    second = dict(altered["generations"][0])
    second["generation_id"] = str(uuid4())
    altered["generations"].append(second)
    registry.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(RuntimeError, match="TRANSITION_REJECTED"):
        prepare_authority_transition(root=root, secret_store=store)
    registry.write_bytes(original_registry)
    manifest = json.loads(original)
    manifest["configuration_authority"]["certified_lifecycle_state"] = "operational/activation.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="TRANSITION_REJECTED"):
        prepare_authority_transition(root=root, secret_store=store)
    manifest = json.loads(original)
    manifest["reranker"]["revision"] = "wrong-revision"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="TRANSITION_REJECTED"):
        prepare_authority_transition(root=root, secret_store=store)
