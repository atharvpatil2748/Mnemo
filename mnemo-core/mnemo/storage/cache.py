"""SQLite-backed content-addressable cache."""

import struct
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiosqlite

from mnemo.interfaces.cache import CacheInterfaceV1
from mnemo.interfaces.errors import IntegrityError

_SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS embedding_cache (
    key TEXT PRIMARY KEY,
    dimensions INTEGER NOT NULL,
    vector BLOB NOT NULL,
    expires_at TEXT
);
"""


class SQLiteEmbeddingCache(CacheInterfaceV1[str, tuple[float, ...]]):
    """Content-addressable vector cache stored in SQLite."""

    def __init__(self, path: Path) -> None:
        """Create the cache without executing I/O."""
        self._path = path

    async def initialize(self) -> None:
        """Create schema if it does not exist."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._path) as db:
            await db.executescript(_SCHEMA)

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    def _pack_vector(self, vector: tuple[float, ...]) -> bytes:
        return struct.pack(f"<{len(vector)}f", *vector)

    def _unpack_vector(self, blob: bytes, dimensions: int) -> tuple[float, ...]:
        expected_size = dimensions * 4
        if len(blob) != expected_size:
            raise IntegrityError(
                f"Corrupted cache blob: expected {expected_size} bytes, got {len(blob)}"
            )
        return struct.unpack(f"<{dimensions}f", blob)

    async def get(self, key: str) -> tuple[float, ...] | None:
        """Return the cached vector, or None if missing or expired."""
        now_iso = datetime.now(UTC).isoformat()
        query = "SELECT dimensions, vector, expires_at FROM embedding_cache WHERE key = ?"
        async with aiosqlite.connect(self._path) as db, db.execute(query, (key,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            dimensions, blob, expires_at = row
            if expires_at and expires_at < now_iso:
                # Expired
                return None
            return self._unpack_vector(blob, dimensions)

    async def put(self, key: str, value: tuple[float, ...], ttl_seconds: int | None = None) -> None:
        """Persist a vector to the cache atomically."""
        expires_at = None
        if ttl_seconds is not None:
            expires = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
            expires_at = expires.isoformat()

        blob = self._pack_vector(value)
        dimensions = len(value)
        query = """
        INSERT INTO embedding_cache (key, dimensions, vector, expires_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            dimensions = excluded.dimensions,
            vector = excluded.vector,
            expires_at = excluded.expires_at
        """
        async with self._transaction() as db:
            await db.execute(query, (key, dimensions, blob, expires_at))

    async def delete(self, key: str) -> bool:
        """Remove a key from the cache."""
        query = "DELETE FROM embedding_cache WHERE key = ?"
        async with self._transaction() as db:
            cursor = await db.execute(query, (key,))
            return cursor.rowcount > 0

    async def clear_namespace(self, namespace: str) -> None:
        """Clear all keys starting with the namespace prefix."""
        query = "DELETE FROM embedding_cache WHERE key LIKE ?"
        pattern = f"{namespace}%"
        async with self._transaction() as db:
            await db.execute(query, (pattern,))
