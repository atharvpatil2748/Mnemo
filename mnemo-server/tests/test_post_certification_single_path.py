"""Post-certification regression checks for one production configuration/path."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from mnemo.config import MnemoConfig

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config/production/full_multilingual_v2.production.json"
ACTIVATION = ROOT / "scratch/phase8_5_full_multilingual_v2/operational/reranker_activation.json"
CERTIFICATION = ROOT / "scratch/phase8_5_full_multilingual_v2/operational/certification.json"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.mark.local_database
def test_historical_certification_cannot_reactivate_retired_production_state() -> None:
    if not (ACTIVATION.exists() and CERTIFICATION.exists()):
        pytest.skip("Operational certification artifacts not present in environment")
    manifest = _json(MANIFEST)
    activation = _json(ACTIVATION)
    certification = _json(CERTIFICATION)

    lifecycle = manifest["lifecycle"]
    assert isinstance(lifecycle, dict)
    assert lifecycle["evaluated"] is True  # retained historical evidence
    assert all(
        lifecycle[key] is False
        for key in (
            "active_generation_alias",
            "v2_transport_exposed",
            "bge_reranker_activated",
            "verified",
            "certified",
        )
    )
    assert activation["desired_mode"] == "BGE_V2_M3"
    assert certification["status"] == "PRODUCTION_CERTIFICATION_PASS"
    assert manifest["corpus"]["database_identity"] == certification["production_store_identity"]
    assert manifest["reranker"]["revision"] == certification["bge_revision"]
    assert manifest["reranker"]["pair_policy"] == certification["pair_policy"]
    selection = _json(ROOT / "config/production/runtime-selection.json")
    assert selection["state"] == "UNINDEXED"


def test_core_outer_slot_is_model_free_and_v2_owns_production_reranking() -> None:
    config = MnemoConfig.from_file(ROOT / "mnemo.toml")
    manifest = _json(MANIFEST)

    assert config.reranker.provider == "v2-owned-pass-through"
    assert config.reranker.model == "no-outer-reranker"
    assert manifest["retrieval"]["candidate_pool_k"] == 50
    assert manifest["reranker"]["model"] == "BAAI/bge-reranker-v2-m3"
    assert manifest["reranker"]["device"] == "cuda"
    assert manifest["reranker"]["batch_size"] == 2
    assert manifest["reranker"]["cpu_fallback"] is False
