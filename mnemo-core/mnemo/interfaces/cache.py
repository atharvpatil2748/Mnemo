"""Cache provider contracts."""

from typing import Protocol, TypeVar, runtime_checkable

K = TypeVar("K", contravariant=True)
V = TypeVar("V")


@runtime_checkable
class CacheInterfaceV1(Protocol[K, V]):  # pragma: no cover
    """Generic typed cache parameterized by immutable key and value types."""

    async def get(self, key: K) -> V | None:
        """Return the cached value for a key, or None if absent or expired."""
        ...

    async def put(self, key: K, value: V, ttl_seconds: int | None = None) -> None:
        """Persist a key-value pair to the cache atomically."""
        ...

    async def delete(self, key: K) -> bool:
        """Remove a key from the cache, returning whether it existed."""
        ...

    async def clear_namespace(self, namespace: str) -> None:
        """Clear all keys under a specific namespace prefix."""
        ...


CacheInterface = CacheInterfaceV1
