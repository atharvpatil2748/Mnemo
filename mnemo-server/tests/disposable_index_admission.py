"""In-process indexed admission for tests; never changes production selection."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

from mcp.types import CallToolResult, TextContent


def mcp_text(result: CallToolResult) -> str:
    """Require a textual MCP result before inspecting its JSON or error body."""
    assert result.content
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text


def disposable_index_admission(root: Path) -> Callable[[], None]:
    """Create a tiny explicit test identity, then verify it on every admission."""
    root = root.resolve()
    workspace = Path(__file__).resolve().parents[2]
    if root == workspace or workspace in root.parents:
        raise ValueError("DISPOSABLE_INDEX_MUST_BE_OUTSIDE_WORKSPACE")
    root.mkdir(parents=True, exist_ok=True)
    database = root / "indexed-test-identity.db"
    if database.exists() or database.is_symlink():
        raise ValueError("DISPOSABLE_INDEX_ALREADY_EXISTS")
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "CREATE TABLE test_index_identity(corpus TEXT NOT NULL, generation TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO test_index_identity VALUES ('disposable-corpus-v1', 'generation-v1')"
        )
        connection.commit()

    def admit() -> None:
        if database.is_symlink() or not database.is_file():
            raise RuntimeError("DISPOSABLE_INDEX_UNAVAILABLE")
        with closing(
            sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
        ) as connection:
            rows = connection.execute(
                "SELECT corpus, generation FROM test_index_identity"
            ).fetchall()
        if rows != [("disposable-corpus-v1", "generation-v1")]:
            raise RuntimeError("DISPOSABLE_INDEX_IDENTITY_MISMATCH")

    return admit
