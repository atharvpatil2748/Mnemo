"""Production composition tests for restart-safe governed reranker state."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

from mnemo.interfaces import PrincipalContextV1
from mnemo.phase85.profiles import ModelProfileComponent
from mnemo_server.config import ServerConfig
from mnemo_server.services.authorization import principal_from_claims
from mnemo_server.services.durable_reranker_activation import (
    restore_production_reranker_activation,
)
from mnemo_server.services.v2_reranker_lifecycle import (
    GovernedV2RerankerRouterV1,
    RerankerActivationAuthorityV1,
    RerankerActivationEvidenceV1,
    V2RerankerMode,
)

STORE_ID = "0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d"


class _FakeBGE:
    async def initialize(self) -> None: ...

    async def close(self) -> None: ...

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


def _installed() -> Any:
    router = GovernedV2RerankerRouterV1()
    authority = RerankerActivationAuthorityV1(
        router=router,
        component=_component(),
        model_cache=Path("unused"),
        reranker_factory=lambda: cast(Any, _FakeBGE()),
    )
    return cast(
        Any,
        type(
            "Installed",
            (),
            {
                "reranker": router,
                "reranker_activation": authority,
                "durable_reranker_activation": None,
            },
        )(),
    )


def _config(tmp_path: Path) -> ServerConfig:
    return ServerConfig(
        production_mode=True,
        auth_mode="api-key",
        api_key="test-key",
        delivery_cursor_secret="x" * 32,
        full_multilingual_v2_enabled=True,
        full_multilingual_v2_model_cache=Path("models"),
        final_qa_operational_store_path=tmp_path / "final-qa.db",
        mcp_stdio_principal_subject="stdio-server",
        reranker_activation_state_path=tmp_path / "reranker.json",
        reranker_activation_operator_subject="production-operator",
    )


def test_production_composition_restores_durable_state_after_restart(tmp_path: Path) -> None:
    config = _config(tmp_path)
    corpus = tmp_path / "mnemo.db"
    installed = _installed()
    authority = asyncio.run(
        restore_production_reranker_activation(
            installed=installed,
            config=config,
            workspace_root=tmp_path,
            production_store_path=corpus,
        )
    )
    assert authority is not None
    operator: PrincipalContextV1 = principal_from_claims({"sub": "production-operator"})
    asyncio.run(
        authority.activate(
            principal=operator,
            evidence=RerankerActivationEvidenceV1(
                v2_exposed=True,
                production_evaluation_passed=True,
                production_store_identity=STORE_ID,
                expected_production_store_identity=STORE_ID,
            ),
        )
    )

    restarted = _installed()
    restarted_authority = asyncio.run(
        restore_production_reranker_activation(
            installed=restarted,
            config=config,
            workspace_root=tmp_path,
            production_store_path=corpus,
        )
    )
    assert restarted_authority is not None
    assert restarted.reranker.mode is V2RerankerMode.BGE_V2_M3


def test_production_composition_rejects_state_in_operational_or_corpus_store(
    tmp_path: Path,
) -> None:
    base = _config(tmp_path)
    for prohibited in (tmp_path / "mnemo.db", tmp_path / "final-qa.db"):
        config = base.model_copy(update={"reranker_activation_state_path": prohibited})
        try:
            asyncio.run(
                restore_production_reranker_activation(
                    installed=_installed(),
                    config=config,
                    workspace_root=tmp_path,
                    production_store_path=tmp_path / "mnemo.db",
                )
            )
        except ValueError as error:
            assert "protected database" in str(error)
        else:  # pragma: no cover - fail-closed assertion
            raise AssertionError("protected database accepted as activation store")
