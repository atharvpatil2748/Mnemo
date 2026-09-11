"""WP-04 shared cursor integrity, expiry, rotation, and scope tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from mnemo.cursors import (
    CursorCodecV2,
    CursorConflictError,
    CursorExpiredError,
    CursorInvalidError,
    CursorKeyUnavailableError,
    CursorSigningKeyV2,
)

NOW = datetime(2026, 8, 27, 12, tzinfo=UTC)
SNAPSHOT = "a" * 64
KEY = CursorSigningKeyV2("cursor-current", b"c" * 32)


def _token(codec: CursorCodecV2, **changes: object) -> str:
    values: dict[str, object] = {
        "domain": "document.blocks",
        "snapshot_identity": SNAPSHOT,
        "binding": {"notebook_id": "n", "document_id": "d", "version_id": "v"},
        "position": {"offset": 10},
        "limits": {"max_items": 10, "max_bytes": 1000},
        "now": NOW,
    }
    values.update(changes)
    return codec.encode(**values)  # type: ignore[arg-type]


def _decode(codec: CursorCodecV2, token: str, **changes: object):  # type: ignore[no-untyped-def]
    values: dict[str, object] = {
        "expected_domain": "document.blocks",
        "expected_binding": {"notebook_id": "n", "document_id": "d", "version_id": "v"},
        "expected_snapshot_identity": SNAPSHOT,
        "expected_limits": {"max_items": 10, "max_bytes": 1000},
        "now": NOW,
    }
    values.update(changes)
    return codec.decode(token, **values)  # type: ignore[arg-type]


def test_v2_cursor_round_trip_is_deterministic_and_bound() -> None:
    codec = CursorCodecV2(KEY, ttl=timedelta(minutes=5))
    first = _token(codec)
    assert first == _token(codec)
    state = _decode(codec, first)
    assert state.key_id == "cursor-current"
    assert state.position == {"offset": 10}
    assert state.expires_at == NOW + timedelta(minutes=5)
    with pytest.raises(CursorConflictError):
        _decode(codec, first, expected_domain="asset.binary")
    with pytest.raises(CursorConflictError):
        _decode(codec, first, expected_binding={"notebook_id": "other"})
    with pytest.raises(CursorConflictError):
        _decode(codec, first, expected_snapshot_identity="b" * 64)
    with pytest.raises(CursorConflictError):
        _decode(codec, first, expected_limits={"max_items": 20, "max_bytes": 1000})


def test_cursor_tamper_malformed_expiry_and_future_issuance_fail_closed() -> None:
    codec = CursorCodecV2(KEY, ttl=timedelta(seconds=30))
    token = _token(codec)
    with pytest.raises(CursorInvalidError):
        _decode(codec, token + "x")
    with pytest.raises(CursorInvalidError):
        _decode(codec, "not-a-cursor")
    with pytest.raises(CursorExpiredError, match="restart"):
        _decode(codec, token, now=NOW + timedelta(seconds=30))
    future = _token(codec, now=NOW + timedelta(minutes=2))
    with pytest.raises(CursorInvalidError, match="issuance"):
        _decode(codec, future)


def test_key_rotation_accepts_overlap_key_and_rejects_retired_key() -> None:
    old = CursorSigningKeyV2("cursor-old", b"o" * 32)
    old_codec = CursorCodecV2(old)
    token = _token(old_codec)
    rotated = CursorCodecV2(KEY, verification_keys=(old,))
    assert _decode(rotated, token).key_id == "cursor-old"
    assert _token(rotated).split(".")[1] == "cursor-current"
    with pytest.raises(CursorKeyUnavailableError, match="restart"):
        _decode(CursorCodecV2(KEY), token)


@pytest.mark.parametrize(
    "key",
    [
        pytest.param(CursorSigningKeyV2("valid", b"x" * 32), id="valid"),
    ],
)
def test_cursor_configuration_validation(key: CursorSigningKeyV2) -> None:
    with pytest.raises(ValueError, match="unique"):
        CursorCodecV2(key, verification_keys=(key,))
    with pytest.raises(ValueError, match="positive"):
        CursorCodecV2(key, ttl=timedelta(0))
    with pytest.raises(ValueError, match="32 bytes"):
        CursorSigningKeyV2("short", b"short")
    with pytest.raises(ValueError, match="SHA-256"):
        _token(CursorCodecV2(key), snapshot_identity="bad")
