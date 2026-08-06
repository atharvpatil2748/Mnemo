"""Tests for immutable metadata and assets."""

from dataclasses import FrozenInstanceError
from uuid import UUID, uuid4

import pytest
from mnemo.models import Asset, FrozenMetadata


def test_frozen_metadata_recursively_freezes_and_hashes() -> None:
    """Metadata copies nested input into a deterministic immutable value."""
    original: dict[str, object] = {
        "parser.name": "basic",
        "plugin.demo.values": [1, {"enabled": True}],
    }
    metadata = FrozenMetadata(original)
    original["parser.name"] = "changed"

    assert metadata["parser.name"] == "basic"
    assert tuple(metadata) == ("parser.name", "plugin.demo.values")
    assert len(metadata) == 2
    assert hash(metadata) == hash(FrozenMetadata(dict(metadata)))
    assert "parser.name" in repr(metadata)
    with pytest.raises(KeyError):
        _ = metadata["missing"]


@pytest.mark.parametrize(
    ("values", "error"),
    [
        ({"": 1}, ValueError),
        ({"plugin.invalid": 1}, ValueError),
        ({"parser.score": float("nan")}, ValueError),
        ({"parser.object": object()}, TypeError),
        ({1: "invalid"}, TypeError),
        ([("parser.key", 1), ("parser.key", 2)], ValueError),
    ],
)
def test_frozen_metadata_rejects_invalid_values(values: object, error: type[Exception]) -> None:
    """Invalid keys, values, and duplicate entries are rejected."""
    with pytest.raises(error):
        FrozenMetadata(values)  # type: ignore[arg-type]


def test_asset_construction_identity_and_immutability(content_hash: str) -> None:
    """Assets are immutable and compare by stable asset identity."""
    asset_id = uuid4()
    first = Asset(
        asset_id=asset_id,
        mime_type="image/png",
        content_hash=content_hash,
        storage_uri="asset://sha256/example",
        width=640,
        height=480,
        metadata=FrozenMetadata({"vision.model": "local"}),
    )
    second = Asset(
        asset_id=asset_id,
        mime_type="image/jpeg",
        content_hash="b" * 64,
        storage_uri="asset://other",
    )

    assert first == second
    assert hash(first) == hash(second)
    assert first != object()
    with pytest.raises(FrozenInstanceError):
        first.width = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    "overrides",
    [
        {"asset_id": "not-uuid"},
        {"mime_type": " "},
        {"content_hash": "bad"},
        {"storage_uri": ""},
        {"width": 0},
        {"height": -1},
        {"metadata": {}},
    ],
)
def test_asset_validation(content_hash: str, overrides: dict[str, object]) -> None:
    """Asset field invariants reject malformed records."""
    values: dict[str, object] = {
        "asset_id": UUID("00000000-0000-4000-8000-000000000010"),
        "mime_type": "image/png",
        "content_hash": content_hash,
        "storage_uri": "asset://example",
    }
    values.update(overrides)
    with pytest.raises((TypeError, ValueError)):
        Asset(**values)  # type: ignore[arg-type]
