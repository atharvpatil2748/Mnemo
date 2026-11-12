"""Offline probe invariants; no model, credentials, or original database required."""

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from mnemo.retrieval import advanced


@pytest.fixture
def bench(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("run_module_894_rank_benchmark")


def test_probes_forward_exact_results_and_denials_and_restore(bench) -> None:
    calls = []
    items = (object(),)

    async def retrieve(*, authorized: bool):
        calls.append(authorized)
        if not authorized:
            raise PermissionError("not granted")
        return items

    app = SimpleNamespace(
        _dense=SimpleNamespace(retrieve=retrieve),
        _sparse=SimpleNamespace(retrieve_authorized_multilingual_sparse=retrieve),
        _reranker=SimpleNamespace(score_candidates=retrieve),
        retrieve=retrieve,
    )
    original = advanced._rank_fuse
    assert asyncio.run(app._dense.retrieve(authorized=True)) is items
    with pytest.raises(PermissionError):
        asyncio.run(app._dense.retrieve(authorized=False))
    tracer = bench.RankTrace()
    with pytest.raises(PermissionError), tracer.observe(app):
        assert asyncio.run(app._dense.retrieve(authorized=True)) is items
        assert tracer.raw["dense"][2] is items
        asyncio.run(app._dense.retrieve(authorized=False))
    assert calls == [True, False, True, False]
    assert tracer.raw == {}
    assert app._dense.retrieve is retrieve and advanced._rank_fuse is original


def test_duplicate_views_do_not_receive_extra_positive_credit(bench) -> None:
    item = dict.fromkeys(bench.KEYS, "one")
    other = {**item, "notebook_id": "private"}
    metrics = bench.metrics([other, item, item], {bench.key(item)}, 10)
    assert metrics["recall"] == 1 and metrics["precision"] == 0.1 and metrics["rr"] == 0.5
    with pytest.raises(PermissionError):
        bench.checked_trace({"dense": [other]}, {bench.key(item)})


def test_equivalence_does_not_ignore_rank_or_scope(bench) -> None:
    item = {
        "representation": "multilingual_text",
        "rank": 1,
        "source_id": "original",
        "locator": {"authorization_decision_fingerprint": "aa" * 32, "generation_ids": ["a"]},
    }
    changed = {
        **item,
        "locator": {**item["locator"], "authorization_decision_fingerprint": "bb" * 32},
    }
    assert bench.stable_item(item) == bench.stable_item(changed)
    assert bench.stable_item(item) != bench.stable_item({**changed, "source_id": "foreign"})
    assert bench.stable_item(item) != bench.stable_item({**changed, "rank": 2})
    with pytest.raises(ValueError):
        bench.stable_item({**item, "locator": {"authorization_decision_fingerprint": "bad"}})


def test_manifest_predeclares_independent_hash_bound_targets_and_controls(bench) -> None:
    import json

    manifest = json.loads(bench.MANIFEST.read_bytes())
    frozen = json.loads(bench.MANIFEST.with_name("manifest.v1.json").read_bytes())["cases"][0]
    assert not manifest["human_adjudication_claimed"]
    assert manifest["cases"][0]["query"] == frozen["query"]
    assert manifest["cases"][0]["targets"][0]["evidence_id"] == frozen["evidence_id"]
    assert len({c["case_id"] for c in manifest["cases"]}) == len(manifest["cases"])
    assert len({t["document_id"] for c in manifest["cases"] for t in c["targets"]}) >= 4
    assert any(len(c["targets"]) > 1 for c in manifest["cases"])
