"""Governed PASS_THROUGH exposure and distinct BGE activation tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from mnemo.interfaces import PrincipalContextV1
from mnemo.models.multilingual_reranking import V2_TYPED_CANDIDATE_BUILDER_ID
from mnemo.phase85.profiles import ModelProfileComponent
from mnemo.retrieval.full_multilingual_v2 import PassThroughV2RerankerV1
from mnemo_server.services.v2_reranker_lifecycle import (
    DurableRerankerActivationAuthorityV1,
    DurableRerankerActivationStateV1,
    DurableRerankerActivationStoreV1,
    GovernedV2RerankerRouterV1,
    RerankerActivationAuthorityV1,
    RerankerActivationEvidenceV1,
    V2ExposureAuthorityV1,
    V2RerankerMode,
)

STORE_ID = "0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d"


class _FakeBGE:
    def __init__(self) -> None:
        self.initialized = False
        self.closed = False

    async def initialize(self) -> None:
        self.initialized = True

    async def close(self) -> None:
        self.closed = True

    async def score_candidates(self, **_: object) -> tuple[object, ...]:
        return ()


def _component() -> ModelProfileComponent:
    return ModelProfileComponent.model_validate(
        {
            "provider": "sentence-transformers",
            "model": "BAAI/bge-reranker-v2-m3",
            "revision": "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
            "license": "apache-2.0",
            "preprocessing": "pair-256-contextual-v1",
            "languages": ["en"],
            "scripts": ["Latn"],
        }
    )


def _evidence(**updates: object) -> RerankerActivationEvidenceV1:
    values: dict[str, object] = {
        "v2_exposed": True,
        "production_evaluation_passed": True,
        "production_store_identity": STORE_ID,
        "expected_production_store_identity": STORE_ID,
    }
    values.update(updates)
    return RerankerActivationEvidenceV1(**values)  # type: ignore[arg-type]


def test_pass_through_is_explicit_and_preserves_candidate_order_without_model() -> None:
    reranker = PassThroughV2RerankerV1()
    candidates = tuple(
        cast(Any, SimpleNamespace(candidate_id=uuid4(), input_ordinal=index)) for index in range(3)
    )
    scores = asyncio.run(reranker.score_candidates(query="q", candidates=candidates))
    assert reranker.mode == "PASS_THROUGH"
    assert [item.candidate_id for item in scores] == [item.candidate_id for item in candidates]
    assert {item.model for item in scores} == {"v2-pass-through-reranker-v1"}
    assert {item.score for item in scores} == {0.0}


def test_activation_is_distinct_auditable_and_rolls_back_to_pass_through() -> None:
    fake = _FakeBGE()
    router = GovernedV2RerankerRouterV1()
    authority = RerankerActivationAuthorityV1(
        router=router,
        component=_component(),
        model_cache=Path("unused"),
        reranker_factory=lambda: cast(Any, fake),
    )
    record = asyncio.run(authority.activate(_evidence()))
    assert fake.initialized is True
    assert record.previous_mode is V2RerankerMode.PASS_THROUGH
    assert record.active_mode is V2RerankerMode.BGE_V2_M3
    assert record.candidate_builder_id == V2_TYPED_CANDIDATE_BUILDER_ID
    assert router.mode is V2RerankerMode.BGE_V2_M3
    asyncio.run(router.score_candidates(query="q", candidates=()))
    assert router.last_execution is not None
    assert router.last_execution.mode is V2RerankerMode.BGE_V2_M3
    assert router.last_execution.model == "BAAI/bge-reranker-v2-m3"
    assert router.last_execution.device == "cuda"
    assert router.last_execution.batch_size == 2
    assert router.last_execution.cpu_fallback is False
    assert asyncio.run(authority.rollback()) is V2RerankerMode.PASS_THROUGH
    assert fake.closed is True


@pytest.mark.parametrize(
    ("change", "value"),
    (
        ("v2_exposed", False),
        ("production_evaluation_passed", False),
        ("production_store_identity", "wrong"),
        ("candidate_builder_id", "wrong"),
        ("model", "wrong"),
        ("revision", "wrong"),
        ("pair_policy", "wrong"),
        ("device", "cpu"),
        ("batch_size", 16),
        ("cpu_fallback", True),
    ),
)
def test_activation_fails_closed_before_model_load(change: str, value: object) -> None:
    loads = 0

    def factory() -> Any:
        nonlocal loads
        loads += 1
        return _FakeBGE()

    authority = RerankerActivationAuthorityV1(
        router=GovernedV2RerankerRouterV1(),
        component=_component(),
        model_cache=Path("unused"),
        reranker_factory=factory,
    )
    with pytest.raises(RuntimeError, match="BGE_ACTIVATION_EVIDENCE_INVALID"):
        asyncio.run(authority.activate(_evidence(**{change: value})))
    assert loads == 0


def _durable_authority(
    *, path: Path, fake: _FakeBGE, actor_id: UUID
) -> tuple[DurableRerankerActivationAuthorityV1, GovernedV2RerankerRouterV1]:
    router = GovernedV2RerankerRouterV1()
    runtime = RerankerActivationAuthorityV1(
        router=router,
        component=_component(),
        model_cache=Path("unused"),
        reranker_factory=lambda: cast(Any, fake),
    )
    store = DurableRerankerActivationStoreV1(
        path=path,
        signing_key=b"a" * 32,
        prohibited_paths=(),
    )
    return (
        DurableRerankerActivationAuthorityV1(
            runtime_authority=runtime,
            router=router,
            store=store,
            authorized_operator_actor_id=actor_id,
        ),
        router,
    )


def test_durable_activation_survives_restart_and_rollback_survives_restart(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "reranker-activation.json"
    actor_id = uuid4()
    principal = PrincipalContextV1(actor_id=actor_id, authenticated=True)

    first, first_router = _durable_authority(path=state_path, fake=_FakeBGE(), actor_id=actor_id)
    asyncio.run(first.activate(principal=principal, evidence=_evidence()))
    assert first_router.mode is V2RerankerMode.BGE_V2_M3

    restarted, _restarted_router = _durable_authority(
        path=state_path, fake=_FakeBGE(), actor_id=actor_id
    )
    assert asyncio.run(restarted.restore()) is V2RerankerMode.BGE_V2_M3
    assert asyncio.run(restarted.rollback(principal=principal)) is V2RerankerMode.PASS_THROUGH

    rolled_back, rolled_back_router = _durable_authority(
        path=state_path, fake=_FakeBGE(), actor_id=actor_id
    )
    assert asyncio.run(rolled_back.restore()) is V2RerankerMode.PASS_THROUGH
    assert rolled_back_router.mode is V2RerankerMode.PASS_THROUGH
    asyncio.run(rolled_back.activate(principal=principal, evidence=_evidence()))

    reactivated, reactivated_router = _durable_authority(
        path=state_path, fake=_FakeBGE(), actor_id=actor_id
    )
    assert asyncio.run(reactivated.restore()) is V2RerankerMode.BGE_V2_M3
    assert reactivated_router.mode is V2RerankerMode.BGE_V2_M3


def test_durable_activation_rejects_unauthorized_and_tampered_state(tmp_path: Path) -> None:
    state_path = tmp_path / "reranker-activation.json"
    actor_id = uuid4()
    authority, router = _durable_authority(path=state_path, fake=_FakeBGE(), actor_id=actor_id)
    with pytest.raises(PermissionError, match="authorized server operator"):
        asyncio.run(
            authority.activate(
                principal=PrincipalContextV1(actor_id=uuid4(), authenticated=True),
                evidence=_evidence(),
            )
        )
    with pytest.raises(PermissionError, match="authorized server operator"):
        asyncio.run(
            authority.activate(
                principal=PrincipalContextV1(actor_id=actor_id, authenticated=False),
                evidence=_evidence(),
            )
        )
    assert router.mode is V2RerankerMode.PASS_THROUGH
    principal = PrincipalContextV1(actor_id=actor_id, authenticated=True)
    asyncio.run(authority.activate(principal=principal, evidence=_evidence()))
    asyncio.run(authority.rollback(principal=principal))
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload["desired_mode"] = "BGE_V2_M3"
    state_path.write_text(json.dumps(payload), encoding="utf-8")
    restarted, _ = _durable_authority(path=state_path, fake=_FakeBGE(), actor_id=actor_id)
    with pytest.raises(RuntimeError, match="SIGNATURE_INVALID"):
        asyncio.run(restarted.restore())


def test_durable_activation_store_rejects_protected_database_path(tmp_path: Path) -> None:
    protected = tmp_path / "mnemo.db"
    with pytest.raises(ValueError, match="protected database"):
        DurableRerankerActivationStoreV1(
            path=protected,
            signing_key=b"a" * 32,
            prohibited_paths=(protected,),
        )


def test_durable_state_and_store_reject_malformed_or_inconsistent_records(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        DurableRerankerActivationStateV1(
            sequence=-1,
            desired_mode=V2RerankerMode.PASS_THROUGH,
            updated_at="now",
            updated_by_actor_id=None,
            activation_evidence=None,
            signature="",
        )
    with pytest.raises(ValueError, match="must agree"):
        DurableRerankerActivationStateV1(
            sequence=1,
            desired_mode=V2RerankerMode.BGE_V2_M3,
            updated_at="now",
            updated_by_actor_id=None,
            activation_evidence=None,
            signature="",
        )
    with pytest.raises(ValueError, match="32 bytes"):
        DurableRerankerActivationStoreV1(
            path=tmp_path / "short.json",
            signing_key=b"short",
            prohibited_paths=(),
        )

    path = tmp_path / "state.json"
    store = DurableRerankerActivationStoreV1(
        path=path,
        signing_key=b"a" * 32,
        prohibited_paths=(),
    )
    assert store.path == path.resolve()
    assert store.load().sequence == 0
    for payload, error in (
        ("not-json", "MALFORMED"),
        (json.dumps([]), "MALFORMED"),
        (json.dumps({"schema_version": "wrong"}), "MALFORMED"),
    ):
        path.write_text(payload, encoding="utf-8")
        with pytest.raises(RuntimeError, match=error):
            store.load()

    unsigned = {
        "schema_version": "mnemo.v2-reranker-activation-state/1",
        "sequence": "not-an-int",
        "desired_mode": "PASS_THROUGH",
        "updated_at": "now",
        "updated_by_actor_id": None,
        "activation_evidence": None,
    }
    path.write_text(
        json.dumps({**unsigned, "signature": store._sign(unsigned)}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="MALFORMED"):
        store.load()


def test_router_and_runtime_authority_fail_closed_on_invalid_transitions() -> None:
    router = GovernedV2RerankerRouterV1()
    with pytest.raises(RuntimeError, match="NOT_ACTIVE"):
        router._restore_pass_through()

    first = _FakeBGE()
    authority = RerankerActivationAuthorityV1(
        router=router,
        component=_component(),
        model_cache=Path("unused"),
        reranker_factory=lambda: cast(Any, first),
    )
    asyncio.run(authority.activate(_evidence()))
    second = _FakeBGE()
    competing = RerankerActivationAuthorityV1(
        router=router,
        component=_component(),
        model_cache=Path("unused"),
        reranker_factory=lambda: cast(Any, second),
    )
    with pytest.raises(RuntimeError, match="ALREADY_ACTIVE"):
        asyncio.run(competing.activate(_evidence()))
    assert second.initialized and second.closed

    router._delegate = cast(Any, object())
    with pytest.raises(RuntimeError, match="ROLLBACK_CLOSE_MISSING"):
        asyncio.run(authority.rollback())


def test_v2_exposure_authority_guard_boundaries() -> None:
    authority = V2ExposureAuthorityV1()
    router = GovernedV2RerankerRouterV1()

    # 1. readiness.v2_active is False
    readiness_inactive = SimpleNamespace(v2_active=False, v2_exposed=False)
    with pytest.raises(RuntimeError, match="V2_EXPOSURE_READINESS_INCOMPLETE"):
        asyncio.run(
            authority.expose(
                engine=cast(Any, None),
                source=cast(Any, None),
                readiness=cast(Any, readiness_inactive),
                reranker=router,
            )
        )

    # 2. readiness.v2_exposed is True
    readiness_already_exposed = SimpleNamespace(v2_active=True, v2_exposed=True)
    with pytest.raises(RuntimeError, match="V2_EXPOSURE_READINESS_INCOMPLETE"):
        asyncio.run(
            authority.expose(
                engine=cast(Any, None),
                source=cast(Any, None),
                readiness=cast(Any, readiness_already_exposed),
                reranker=router,
            )
        )

    # 3. reranker.mode != PASS_THROUGH
    router._mode = V2RerankerMode.BGE_V2_M3
    readiness_valid = SimpleNamespace(v2_active=True, v2_exposed=False)
    with pytest.raises(RuntimeError, match="V2_EXPOSURE_REQUIRES_PASS_THROUGH"):
        asyncio.run(
            authority.expose(
                engine=cast(Any, None),
                source=cast(Any, None),
                readiness=cast(Any, readiness_valid),
                reranker=router,
            )
        )

    # 4. reranker.activation_record is not None
    router._mode = V2RerankerMode.PASS_THROUGH
    router._activation = cast(Any, SimpleNamespace())
    with pytest.raises(RuntimeError, match="V2_EXPOSURE_CANNOT_ACTIVATE_BGE"):
        asyncio.run(
            authority.expose(
                engine=cast(Any, None),
                source=cast(Any, None),
                readiness=cast(Any, readiness_valid),
                reranker=router,
            )
        )


def test_durable_authority_state_path_desired_state_and_failure_modes(tmp_path: Path) -> None:
    state_path = tmp_path / "reranker-activation.json"
    actor_id = uuid4()
    principal = PrincipalContextV1(actor_id=actor_id, authenticated=True)
    authority, router = _durable_authority(path=state_path, fake=_FakeBGE(), actor_id=actor_id)

    # state_path property
    assert authority.state_path == state_path

    # router activation_record property
    assert router.activation_record is None

    # desired_state()
    initial_state = authority.desired_state()
    assert initial_state.desired_mode == V2RerankerMode.PASS_THROUGH

    # restore when desired_mode is PASS_THROUGH but router._mode is BGE_V2_M3
    router._mode = V2RerankerMode.BGE_V2_M3
    with pytest.raises(RuntimeError, match="DURABLE_BGE_RESTORE_RUNTIME_NOT_PASS_THROUGH"):
        asyncio.run(authority.restore())
    router._mode = V2RerankerMode.PASS_THROUGH

    # restore when desired_mode is BGE_V2_M3 but activation_evidence is None
    authority._store.load = lambda: cast(  # type: ignore[method-assign]
        Any, SimpleNamespace(desired_mode=V2RerankerMode.BGE_V2_M3, activation_evidence=None)
    )
    with pytest.raises(RuntimeError, match="DURABLE_BGE_ACTIVATION_STATE_MALFORMED"):
        asyncio.run(authority.restore())

    # activate failure on commit rolls back runtime
    def failing_commit(**kwargs: object) -> None:
        raise OSError("disk write failed")

    authority._store.commit = failing_commit  # type: ignore[method-assign]
    with pytest.raises(OSError, match="disk write failed"):
        asyncio.run(authority.activate(principal=principal, evidence=_evidence()))
    assert router.mode == V2RerankerMode.PASS_THROUGH

    # rollback failure on commit raises DURABLE_BGE_ROLLBACK_STATE_COMMIT_FAILED
    router._mode = V2RerankerMode.BGE_V2_M3
    router._delegate = _FakeBGE()
    with pytest.raises(RuntimeError, match="DURABLE_BGE_ROLLBACK_STATE_COMMIT_FAILED"):
        asyncio.run(authority.rollback(principal=principal))
