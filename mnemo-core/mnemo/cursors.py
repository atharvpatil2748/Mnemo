"""Shared, versioned cursor integrity contract for Phase 8.5 traversals."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from mnemo.interfaces.errors import ConflictError, IntegrityError

_PREFIX = "mnc2"
_FORMAT_VERSION = 2


class CursorInvalidError(IntegrityError):
    """Cursor is malformed, unsigned, tampered, or structurally invalid."""

    code = "cursor.invalid"


class CursorExpiredError(ConflictError):
    """Cursor validity window ended; callers must restart the traversal."""

    code = "cursor.expired"


class CursorConflictError(ConflictError):
    """Cursor is valid but belongs to another traversal or snapshot."""

    code = "cursor.conflict"


class CursorKeyUnavailableError(ConflictError):
    """Cursor references a signing key outside the configured overlap window."""

    code = "cursor.key_unavailable"


@dataclass(frozen=True, slots=True)
class CursorSigningKeyV2:
    """Named HMAC-SHA256 cursor key."""

    key_id: str
    secret: bytes

    def __post_init__(self) -> None:
        if not self.key_id or len(self.key_id) > 64 or not self.key_id.replace("-", "").isalnum():
            raise ValueError("cursor key_id must be 1-64 alphanumeric/hyphen characters")
        if not isinstance(self.secret, bytes) or len(self.secret) < 32:
            raise ValueError("cursor signing secret must contain at least 32 bytes")


@dataclass(frozen=True, slots=True)
class DecodedCursorV2:
    """Validated continuation state; never construct directly from client data."""

    domain: str
    key_id: str
    issued_at: datetime
    expires_at: datetime
    snapshot_identity: str
    binding: dict[str, object]
    position: dict[str, object]
    limits: dict[str, object]


class CursorCodecV2:
    """Issue with one key and verify active/overlap keys without silent fallback."""

    def __init__(
        self,
        active_key: CursorSigningKeyV2,
        *,
        verification_keys: tuple[CursorSigningKeyV2, ...] = (),
        ttl: timedelta = timedelta(minutes=15),
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if ttl <= timedelta(0) or ttl > timedelta(days=1):
            raise ValueError("cursor ttl must be positive and at most one day")
        keys: dict[str, bytes] = {active_key.key_id: bytes(active_key.secret)}
        for key in verification_keys:
            if key.key_id in keys:
                raise ValueError("cursor key IDs must be unique")
            keys[key.key_id] = bytes(key.secret)
        self._active_key = active_key
        self._keys = keys
        self._ttl = ttl
        self._clock = clock

    @property
    def active_key_id(self) -> str:
        return self._active_key.key_id

    def encode(
        self,
        *,
        domain: str,
        snapshot_identity: str,
        binding: Mapping[str, object],
        position: Mapping[str, object],
        limits: Mapping[str, object],
        now: datetime | None = None,
    ) -> str:
        issued_at = _utc(now or self._clock())
        _validate_identity(domain, snapshot_identity)
        payload = {
            "format_version": _FORMAT_VERSION,
            "domain": domain,
            "key_id": self._active_key.key_id,
            "issued_at": int(issued_at.timestamp()),
            "expires_at": int((issued_at + self._ttl).timestamp()),
            "snapshot_identity": snapshot_identity,
            "binding": _json_object(binding, "binding"),
            "position": _json_object(position, "position"),
            "limits": _json_object(limits, "limits"),
        }
        encoded = _b64(_canonical_json(payload))
        signature = _b64(
            hmac.new(self._active_key.secret, encoded.encode("ascii"), hashlib.sha256).digest()
        )
        return f"{_PREFIX}.{self._active_key.key_id}.{encoded}.{signature}"

    def decode(
        self,
        token: str,
        *,
        expected_domain: str,
        expected_binding: Mapping[str, object],
        expected_snapshot_identity: str | None = None,
        expected_limits: Mapping[str, object] | None = None,
        now: datetime | None = None,
    ) -> DecodedCursorV2:
        try:
            prefix, outer_key_id, encoded, supplied = token.split(".")
            if prefix != _PREFIX:
                raise ValueError
        except (AttributeError, ValueError) as error:
            raise CursorInvalidError("cursor format is invalid") from error
        secret = self._keys.get(outer_key_id)
        if secret is None:
            raise CursorKeyUnavailableError(
                "cursor signing key is no longer available; restart the traversal"
            )
        expected = _b64(hmac.new(secret, encoded.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(supplied, expected):
            raise CursorInvalidError("cursor signature is invalid")
        try:
            payload = cast(dict[str, Any], json.loads(_unb64(encoded)))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise CursorInvalidError("cursor payload is invalid") from error
        required = {
            "format_version",
            "domain",
            "key_id",
            "issued_at",
            "expires_at",
            "snapshot_identity",
            "binding",
            "position",
            "limits",
        }
        if set(payload) != required or payload.get("format_version") != _FORMAT_VERSION:
            raise CursorInvalidError("cursor payload schema is invalid")
        if payload.get("key_id") != outer_key_id:
            raise CursorInvalidError("cursor key identity is invalid")
        issued = payload.get("issued_at")
        expires = payload.get("expires_at")
        if (
            isinstance(issued, bool)
            or not isinstance(issued, int)
            or isinstance(expires, bool)
            or not isinstance(expires, int)
            or expires <= issued
        ):
            raise CursorInvalidError("cursor validity window is invalid")
        current = _utc(now or self._clock())
        if int(current.timestamp()) >= expires:
            raise CursorExpiredError("cursor has expired; restart the traversal")
        if issued > int(current.timestamp()) + 30:
            raise CursorInvalidError("cursor issuance time is invalid")
        domain = payload.get("domain")
        snapshot = payload.get("snapshot_identity")
        binding = payload.get("binding")
        position = payload.get("position")
        limits = payload.get("limits")
        if (
            not isinstance(domain, str)
            or not isinstance(snapshot, str)
            or not isinstance(binding, dict)
            or not isinstance(position, dict)
            or not isinstance(limits, dict)
        ):
            raise CursorInvalidError("cursor state is invalid")
        try:
            _validate_identity(domain, snapshot)
        except ValueError as error:
            raise CursorInvalidError("cursor identity state is invalid") from error
        if domain != expected_domain or binding != _json_object(expected_binding, "binding"):
            raise CursorConflictError("cursor does not match the requested traversal")
        if expected_snapshot_identity is not None and snapshot != expected_snapshot_identity:
            raise CursorConflictError("cursor snapshot is stale; restart the traversal")
        if expected_limits is not None and limits != _json_object(expected_limits, "limits"):
            raise CursorConflictError("cursor bounds do not match the original traversal")
        return DecodedCursorV2(
            domain=domain,
            key_id=outer_key_id,
            issued_at=datetime.fromtimestamp(issued, UTC),
            expires_at=datetime.fromtimestamp(expires, UTC),
            snapshot_identity=snapshot,
            binding=cast(dict[str, object], binding),
            position=cast(dict[str, object], position),
            limits=cast(dict[str, object], limits),
        )


def _validate_identity(domain: str, snapshot_identity: str) -> None:
    if not domain or len(domain) > 128:
        raise ValueError("cursor domain must be non-empty and bounded")
    if len(snapshot_identity) != 64 or any(c not in "0123456789abcdef" for c in snapshot_identity):
        raise ValueError("cursor snapshot_identity must be a lowercase SHA-256 identity")


def _json_object(value: Mapping[str, object], name: str) -> dict[str, object]:
    try:
        normalized = cast(dict[str, object], json.loads(_canonical_json(dict(value))))
    except (TypeError, ValueError) as error:
        raise ValueError(f"cursor {name} must be JSON serializable") from error
    return normalized


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("cursor time must be timezone-aware")
    return value.astimezone(UTC)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
