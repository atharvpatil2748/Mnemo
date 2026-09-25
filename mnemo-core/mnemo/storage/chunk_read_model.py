"""Physical chunk projection shared by immutable and current SQLite readers."""

from __future__ import annotations

from dataclasses import dataclass

import aiosqlite

from mnemo.interfaces.errors import StorageError, UnsupportedError

_COMMON_COLUMNS = (
    "id",
    "document_id",
    "version_id",
    "text",
    "chunk_type",
    "position_section_index",
    "position_chunk_index",
    "position_page_number",
    "position_start_offset",
    "position_end_offset",
    "source_start_ordinal",
    "source_end_ordinal",
    "heading_path",
    "parent_chunk_id",
    "sibling_ids",
    "metadata",
)
_PAGE_COLUMNS = ("position_page_start", "position_page_end")


@dataclass(frozen=True, slots=True)
class ChunkReadModel:
    """The verified physical schema, not a guessed page range from page_number."""

    has_page_range: bool

    @classmethod
    async def inspect(cls, db: aiosqlite.Connection) -> ChunkReadModel:
        async with db.execute("PRAGMA table_info(chunks)") as cursor:
            present = {str(row[1]) for row in await cursor.fetchall()}
        if not set(_COMMON_COLUMNS) <= present:
            raise StorageError("CHUNK_READ_SCHEMA_INCOMPATIBLE")
        page_count = sum(column in present for column in _PAGE_COLUMNS)
        if page_count == 1:
            raise StorageError("CHUNK_PAGE_RANGE_SCHEMA_INCOMPLETE")
        return cls(has_page_range=page_count == 2)

    def projection(self, alias: str = "") -> str:
        """Produce one fixed-order, explicit projection for either schema."""
        if alias not in ("", "c"):
            raise ValueError("unsupported chunk table alias")
        prefix = f"{alias}." if alias else ""
        columns = [f"{prefix}{column}" for column in _COMMON_COLUMNS]
        columns.extend(
            f"{prefix}{column}" if self.has_page_range else f"NULL AS {column}"
            for column in _PAGE_COLUMNS
        )
        return ",".join(columns)

    def require_page_filter(self, *, page_start: int | None, page_end: int | None) -> None:
        """A page number is not proof of a persisted page-range interval."""
        if (page_start is not None or page_end is not None) and not self.has_page_range:
            raise UnsupportedError("PAGE_RANGE_UNAVAILABLE_FOR_CHUNK_SCHEMA")
