"""Regression coverage for the certified V2-owned reranker boundary."""

from __future__ import annotations

import asyncio
from pathlib import Path

from mnemo.config import MnemoConfig
from mnemo.engine import (
    _V2OwnedOuterPassThroughReranker,
    _V2OwnedOuterPassThroughRerankerPlugin,
)
from mnemo.registry import PluginRegistry


def test_outer_pass_through_preserves_candidates_without_loading_a_model() -> None:
    reranker = _V2OwnedOuterPassThroughReranker()

    assert asyncio.run(reranker.rerank("governed query", (), 5)) == ()
    capabilities = reranker.capabilities()
    assert capabilities.supports_cross_encoder is False
    assert capabilities.supports_batch is False
    assert capabilities.preserves_raw_scores is True


def test_outer_pass_through_registers_the_required_core_slot() -> None:
    registry = PluginRegistry(core_version="0.1.0")

    registry.load_plugin(_V2OwnedOuterPassThroughRerankerPlugin())
    registry.freeze()

    provider = registry.resolve_reranker("primary")
    assert isinstance(provider, _V2OwnedOuterPassThroughReranker)


def test_repository_configuration_has_no_legacy_outer_model_dependency() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    config = MnemoConfig.from_file(repository_root / "mnemo.toml")

    assert config.reranker.provider == "v2-owned-pass-through"
    assert config.reranker.model == "no-outer-reranker"
