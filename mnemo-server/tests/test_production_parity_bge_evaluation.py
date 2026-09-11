"""Tests for the server-owned, non-activating BGE evaluation boundary."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from mnemo_server.evaluation import production_parity_bge as target
from mnemo_server.services.v2_reranker_lifecycle import V2RerankerMode


class _FakeBGE:
    def __init__(self, *_: object, **__: object) -> None:
        self.initialized = False
        self.closed = False

    async def initialize(self) -> None:
        self.initialized = True

    async def close(self) -> None:
        self.closed = True


class _FakeAssembler:
    identity = cast(Any, object())

    def __init__(self) -> None:
        self.clone: _FakeAssembler | None = None
        self.reranker: object | None = None
        self.closed = False

    def for_nonactivating_evaluation(self, *, reranker: object) -> _FakeAssembler:
        clone = _FakeAssembler()
        clone.reranker = reranker
        self.clone = clone
        return clone

    async def close(self) -> None:
        self.closed = True


class _FakeRegistration:
    def __init__(self, **_: object) -> None:
        pass

    async def compose_internal_runtime(self) -> object:
        return object()


def test_evaluation_lease_does_not_activate_installed_router(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_bge = _FakeBGE()
    monkeypatch.setattr(target, "BGEMultilingualReranker", lambda *a, **k: fake_bge)
    monkeypatch.setattr(target, "ServerOwnedFullMultilingualV2RegistrationV1", _FakeRegistration)
    monkeypatch.setattr(
        target.ModelProfileDocument,
        "from_file",
        lambda _: SimpleNamespace(
            select=lambda __: SimpleNamespace(components={"multilingual_reranker": object()})
        ),
    )
    monkeypatch.setattr(target, "profile_snapshot", lambda value: value)
    assembler = _FakeAssembler()
    router = SimpleNamespace(mode=V2RerankerMode.PASS_THROUGH, activation_record=None)
    installed = SimpleNamespace(reranker=router, assembler=assembler)
    lease = asyncio.run(
        target.ProductionParityBGEEvaluationLeaseV1.open(
            engine=cast(Any, object()),
            installed=cast(Any, installed),
            workspace_root=Path.cwd(),
            model_cache=Path("unused"),
        )
    )
    assert fake_bge.initialized is True
    assert assembler.clone is lease.assembler
    assert router.mode is V2RerankerMode.PASS_THROUGH
    assert router.activation_record is None
    asyncio.run(lease.close())
    assert fake_bge.closed is True
    assert router.mode is V2RerankerMode.PASS_THROUGH


def test_evaluation_lease_rejects_active_bge_before_model_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loads = 0

    def factory(*_: object, **__: object) -> _FakeBGE:
        nonlocal loads
        loads += 1
        return _FakeBGE()

    monkeypatch.setattr(target, "BGEMultilingualReranker", factory)
    installed = SimpleNamespace(
        reranker=SimpleNamespace(mode=V2RerankerMode.BGE_V2_M3, activation_record=object()),
        assembler=_FakeAssembler(),
    )
    with pytest.raises(RuntimeError, match="PRODUCTION_EVALUATION_REQUIRES_INACTIVE_BGE"):
        asyncio.run(
            target.ProductionParityBGEEvaluationLeaseV1.open(
                engine=cast(Any, object()),
                installed=cast(Any, installed),
                workspace_root=Path.cwd(),
                model_cache=Path("unused"),
            )
        )
    assert loads == 0
