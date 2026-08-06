"""Shared immutable value types and validation helpers for domain models."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import date, datetime
from uuid import UUID

type JSONPrimitive = str | int | float | bool | None
type JSONValue = JSONPrimitive | tuple[JSONValue, ...] | FrozenMetadata
type BoundingBox = tuple[float, float, float, float]

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_PLUGIN_KEY_PATTERN = re.compile(r"^plugin\.[a-z0-9_-]+\..+$")


class FrozenMetadata(Mapping[str, JSONValue]):
    """An immutable, hashable, recursively frozen JSON object."""

    __slots__ = ("_items",)

    def __init__(
        self,
        values: Mapping[str, object] | Iterable[tuple[str, object]] = (),
    ) -> None:
        """Copy and recursively freeze metadata values."""
        source = values.items() if isinstance(values, Mapping) else values
        frozen: dict[str, JSONValue] = {}
        for key, value in source:
            _validate_metadata_key(key)
            if key in frozen:
                raise ValueError(f"duplicate metadata key: {key}")
            frozen[key] = _freeze_json(value)
        self._items = tuple(sorted(frozen.items()))

    def __getitem__(self, key: str) -> JSONValue:
        """Return the value for a metadata key."""
        for item_key, value in self._items:
            if item_key == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        """Iterate over keys in canonical sorted order."""
        return (key for key, _ in self._items)

    def __len__(self) -> int:
        """Return the number of metadata entries."""
        return len(self._items)

    def __hash__(self) -> int:
        """Hash the canonical recursively immutable item sequence."""
        return hash(self._items)

    def __repr__(self) -> str:
        """Return a deterministic developer representation."""
        content = ", ".join(f"{key!r}: {value!r}" for key, value in self._items)
        return f"FrozenMetadata({{{content}}})"


def _freeze_json(value: object) -> JSONValue:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        require_finite(value, "metadata number")
        return value
    if isinstance(value, Mapping):
        items: list[tuple[str, object]] = []
        for key, nested in value.items():
            if not isinstance(key, str):
                raise TypeError("metadata object keys must be strings")
            items.append((key, nested))
        return FrozenMetadata(items)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_freeze_json(item) for item in value)
    raise TypeError(f"unsupported metadata value type: {type(value).__name__}")


def _validate_metadata_key(key: str) -> None:
    require_non_empty(key, "metadata key")
    if key.startswith("plugin.") and _PLUGIN_KEY_PATTERN.fullmatch(key) is None:
        raise ValueError("plugin metadata keys must use plugin.<plugin_name>.<key> namespace")


def require_uuid(value: UUID, field_name: str) -> None:
    """Require a UUID instance."""
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")


def require_sha256(value: str, field_name: str) -> None:
    """Require a lowercase hexadecimal SHA-256 digest."""
    if _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def require_non_empty(value: str, field_name: str) -> None:
    """Require a non-empty, non-whitespace string."""
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def require_optional_non_empty(value: str | None, field_name: str) -> None:
    """Require an optional string to be non-empty when present."""
    if value is not None:
        require_non_empty(value, field_name)


def require_int(value: int, field_name: str) -> None:
    """Require an integer that is not a boolean."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")


def require_non_negative(value: int, field_name: str) -> None:
    """Require a non-negative integer."""
    require_int(value, field_name)
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def require_positive(value: int, field_name: str) -> None:
    """Require a positive integer."""
    require_int(value, field_name)
    if value < 1:
        raise ValueError(f"{field_name} must be positive")


def require_finite(value: float, field_name: str) -> None:
    """Require a finite real number that is not a boolean."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a number")
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")


def require_unit_interval(value: float, field_name: str) -> None:
    """Require a finite number in the inclusive unit interval."""
    require_finite(value, field_name)
    if not 0 <= value <= 1:
        raise ValueError(f"{field_name} must be between 0 and 1")


def require_utc(value: datetime, field_name: str) -> None:
    """Require a timezone-aware UTC timestamp."""
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    offset = value.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{field_name} must be timezone-aware UTC")


def require_date(value: date, field_name: str) -> None:
    """Require a calendar date rather than a datetime."""
    if isinstance(value, datetime) or not isinstance(value, date):
        raise TypeError(f"{field_name} must be a date")


def require_enum[T](value: object, enum_type: type[T], field_name: str) -> None:
    """Require an instance of a specific enum type."""
    if not isinstance(value, enum_type):
        raise TypeError(f"{field_name} must be a {enum_type.__name__}")


def require_unique(values: Sequence[object], field_name: str) -> None:
    """Require values to be unique while preserving order."""
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must contain unique values")


def require_tuple(value: object, field_name: str) -> None:
    """Require an immutable tuple collection."""
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be a tuple")


def identity_equal(
    left: object,
    right: object,
    model_type: type[object],
    left_id: object,
    right_id: object,
) -> bool:
    """Compare two identity records without accepting sibling model types."""
    if not isinstance(right, model_type):
        return False
    return left_id == right_id
