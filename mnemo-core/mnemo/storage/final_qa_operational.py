"""Dedicated mutable SQLite store for Final-QA V2 operational state."""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite

from mnemo.interfaces.errors import StorageError

from .multimodal import MULTIMODAL_SCHEMA_STATEMENTS, SQLiteMultimodalMixin


class SQLiteFinalQAOperationalStore(SQLiteMultimodalMixin):
    """Persist Final-QA executions without exposing corpus storage capabilities."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise TypeError("path must be a pathlib.Path")
        self._path = path.resolve()
        self._db: aiosqlite.Connection | None = None
        self._multimodal_lock = asyncio.Lock()

    @property
    def path(self) -> Path:
        return self._path

    async def open(self) -> None:
        if self._db is not None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            db = await aiosqlite.connect(self._path)
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute("PRAGMA journal_mode = WAL")
            for statement in MULTIMODAL_SCHEMA_STATEMENTS:
                await db.execute(statement)
            await db.commit()
        except aiosqlite.Error as error:
            raise StorageError("could not open Final-QA operational store") from error
        self._db = db

    async def close(self) -> None:
        db, self._db = self._db, None
        if db is not None:
            await db.close()

    def _require_open(self) -> aiosqlite.Connection:
        if self._db is None:
            raise StorageError("Final-QA operational store is not open")
        return self._db
