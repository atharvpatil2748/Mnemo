"""Tests for the bounded Full Multilingual V2 activation operator."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from mnemo.interfaces.errors import ContractValidationError, IntegrityError
from mnemo.phase85 import v2_activation as subject
from mnemo.phase85.v2_activation import (
    FullMultilingualV2ActivationOperator,
    V2ActivationPreflight,
    _load,
)
from mnemo.phase85.v2_activation_authorization import (
    V2ActivationAuthorizationV1,
    first_v2_deactivation_recovery_digest,
)


def test_activation_artifact_loader_requires_json_object(tmp_path: Path) -> None:
    path = tmp_path / "activation.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ContractValidationError, match="must be an object"):
        _load(path)
    path.write_text(json.dumps({"kind": "activation"}), encoding="utf-8")
    assert _load(path) == {"kind": "activation"}


def test_activation_authorization_is_digest_bound_and_fail_closed() -> None:
    root = Path(__file__).resolve().parents[3]
    path = (
        root / "docs/governance/proposals/phase8_5_full_multilingual_architecture/"
        "V2_INDEX_ACTIVATION_AUTHORIZATION.json"
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    authorization = V2ActivationAuthorizationV1.from_mapping(raw)
    assert str(authorization.authorization_id) == raw["authorization_id"]
    assert authorization.artifact_digest == raw["artifact_digest"]
    assert (
        len(
            first_v2_deactivation_recovery_digest(
                profile_fingerprint=authorization.profile_fingerprint
            )
        )
        == 64
    )

    invalid_changes = (
        ({"target_database_path": "../mnemo.db"}, "bounded relative"),
        ({"target_database_path": "data/mnemo.db"}, "isolated namespace"),
        ({"profile_fingerprint": "short"}, "SHA-256"),
        ({"generation_ids": authorization.generation_ids[:3]}, "four unique"),
        ({"generation_ids": (authorization.generation_ids[0],) * 4}, "four unique"),
        ({"generation_checksums": authorization.generation_checksums[:3]}, "four generation"),
        ({"activation_mode": "unknown"}, "unsupported"),
        ({"recovery_mode": "prior_v2_alias_set"}, "incompatible"),
        ({"authorization_scope": "unbounded"}, "scope"),
        ({"authorized": False}, "not authorized"),
        ({"authority_class": "machine"}, "human governance"),
        ({"decision_reference": " "}, "human governance"),
    )
    for changes, message in invalid_changes:
        with pytest.raises(ContractValidationError, match=message):
            replace(authorization, **changes)

    for changes in (
        {"schema_version": "wrong"},
        {"generation_ids": "not-a-list"},
        {"authorization_id": str(uuid4())},
        {"artifact_digest": "0" * 64},
    ):
        with pytest.raises(ContractValidationError, match="malformed"):
            V2ActivationAuthorizationV1.from_mapping({**raw, **changes})
    with pytest.raises(ContractValidationError, match="SHA-256"):
        first_v2_deactivation_recovery_digest(profile_fingerprint="short")


def _preflight(tmp_path: Path) -> V2ActivationPreflight:
    generations = tuple(uuid4() for _ in range(4))
    authorization = SimpleNamespace(
        run_id=uuid4(),
        profile_fingerprint="a" * 64,
        generation_ids=generations,
        activation_mode="first_v2_activation",
        recovery_mode="deactivate_v2_alias_set",
        authorization_id=uuid4(),
        artifact_digest="b" * 64,
        target_database_path="target.db",
    )
    return V2ActivationPreflight(
        target=tmp_path / "target.db",
        authorization=authorization,  # type: ignore[arg-type]
        generation_ids=generations,
    )


def test_activation_execute_promotes_validates_resolves_and_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preflight = _preflight(tmp_path)
    events: list[str] = []

    class Store:
        def __init__(self, path: Path) -> None:
            assert path == preflight.target

        async def open(self) -> None:
            events.append("open")

        async def close(self) -> None:
            events.append("close")

        async def promote_multilingual_v2_alias_set(self, **kwargs: object) -> str:
            assert kwargs["generation_ids"] == preflight.generation_ids
            assert kwargs["expected_active_alias_set_digest"] is None
            events.append("promote")
            return "c" * 64

        async def resolve_active_multilingual_v2_generation_set(self):  # type: ignore[no-untyped-def]
            events.append("resolve")
            return preflight.generation_ids

    operator = object.__new__(FullMultilingualV2ActivationOperator)
    operator.preflight = lambda: preflight  # type: ignore[method-assign]
    operator._validate_active_database = (  # type: ignore[method-assign]
        lambda target, authorization, digest: events.append(f"validate:{digest[:1]}")
    )
    monkeypatch.setattr(subject, "SQLiteStore", Store)
    result = asyncio.run(operator.execute())
    assert result["resolved_generation_ids"] == [str(value) for value in preflight.generation_ids]
    assert result["exposed"] is False
    assert events == ["open", "promote", "validate:c", "resolve", "close"]


def test_activation_execute_rejects_resolver_mismatch_and_still_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preflight = _preflight(tmp_path)
    closed = False

    class Store:
        def __init__(self, _: Path) -> None:
            pass

        async def open(self) -> None:
            pass

        async def close(self) -> None:
            nonlocal closed
            closed = True

        async def promote_multilingual_v2_alias_set(self, **_: object) -> str:
            return "c" * 64

        async def resolve_active_multilingual_v2_generation_set(self):  # type: ignore[no-untyped-def]
            return tuple(reversed(preflight.generation_ids))

    operator = object.__new__(FullMultilingualV2ActivationOperator)
    operator.preflight = lambda: preflight  # type: ignore[method-assign]
    operator._validate_active_database = lambda *_: None  # type: ignore[method-assign]
    monkeypatch.setattr(subject, "SQLiteStore", Store)
    with pytest.raises(IntegrityError, match="resolver disagrees"):
        asyncio.run(operator.execute())
    assert closed


def test_ready_database_validation_covers_every_governed_integrity_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preflight = _preflight(tmp_path)
    authorization = preflight.authorization
    authorization.corpus_digest = "c" * 64
    authorization.census_digest = "d" * 64
    authorization.vector_space_identity = "vector-space"
    authorization.generation_checksums = tuple("e" * 64 for _ in range(4))
    state = {"defect": None}

    class Cursor:
        def __init__(self, value: object) -> None:
            self.value = value

        def fetchone(self):  # type: ignore[no-untyped-def]
            return self.value

        def fetchall(self):  # type: ignore[no-untyped-def]
            return self.value

    class Connection:
        def execute(self, query: str, _params=()):  # type: ignore[no-untyped-def]
            defect = state["defect"]
            if "FROM v2_build_runs" in query:
                value = (
                    "ready",
                    authorization.profile_fingerprint,
                    authorization.vector_space_identity,
                    authorization.corpus_digest,
                    authorization.census_digest,
                )
                return Cursor(("bad", *value[1:]) if defect == "run" else value)
            if "FROM index_generations" in query:
                rows = [
                    (
                        capability,
                        str(identifier),
                        "ready",
                        checksum,
                        "complete",
                        0,
                        authorization.profile_fingerprint,
                        1,
                        1,
                    )
                    for capability, identifier, checksum in zip(
                        subject._CAPABILITIES,
                        authorization.generation_ids,
                        authorization.generation_checksums,
                        strict=True,
                    )
                ]
                if defect == "generation":
                    rows[0] = (*rows[0][:2], "failed", *rows[0][3:])
                return Cursor(rows)
            if "DISTINCT vector_space" in query:
                rows = (
                    [("wrong",)] if defect == "vector" else [(authorization.vector_space_identity,)]
                )
                return Cursor(rows)
            if "active_multilingual_v2_alias_set" in query:
                return Cursor((1,) if defect == "active" else (0,))
            if "integrity_check" in query:
                return Cursor(("corrupt",) if defect == "integrity" else ("ok",))
            if "foreign_key_check" in query:
                return Cursor(("violation",) if defect == "foreign" else None)
            raise AssertionError(query)

        def close(self) -> None:
            state["closed"] = True

    monkeypatch.setattr(subject.sqlite3, "connect", lambda *_args, **_kwargs: Connection())
    FullMultilingualV2ActivationOperator._validate_ready_database(preflight.target, authorization)
    assert state["closed"] is True
    for defect, message in (
        ("run", "exact governed READY"),
        ("generation", "incomplete or incompatible"),
        ("vector", "vector space mismatch"),
        ("active", "cannot replace"),
        ("integrity", "integrity check failed"),
        ("foreign", "foreign-key audit failed"),
    ):
        state["defect"] = defect
        with pytest.raises(IntegrityError, match=message):
            FullMultilingualV2ActivationOperator._validate_ready_database(
                preflight.target, authorization
            )


def test_active_database_validation_requires_exact_alias_and_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preflight = _preflight(tmp_path)
    authorization = preflight.authorization
    digest = "f" * 64
    state = {"valid": True}

    class Cursor:
        def __init__(self, value: object) -> None:
            self.value = value

        def fetchone(self):  # type: ignore[no-untyped-def]
            return self.value

    class Connection:
        def execute(self, query: str, _params=()):  # type: ignore[no-untyped-def]
            if "active_multilingual" in query:
                return Cursor((digest,) if state["valid"] else ("wrong",))
            return Cursor(
                (
                    "first_v2_activation",
                    "deactivate_v2_alias_set",
                    str(authorization.authorization_id),
                    authorization.artifact_digest,
                )
            )

        def close(self) -> None:
            state["closed"] = True

    monkeypatch.setattr(subject.sqlite3, "connect", lambda *_args, **_kwargs: Connection())
    FullMultilingualV2ActivationOperator._validate_active_database(
        preflight.target, authorization, digest
    )
    state["valid"] = False
    with pytest.raises(IntegrityError, match="does not match"):
        FullMultilingualV2ActivationOperator._validate_active_database(
            preflight.target, authorization, digest
        )
