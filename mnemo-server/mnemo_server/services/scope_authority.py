"""Persisted server-owned notebook grants, separate from corpus identity.

Existing notebooks are deliberately not auto-enrolled. An authenticated
operator/onboarding workflow must explicitly grant actors before serving them.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Protocol
from uuid import UUID


class NotebookScopeAuthority(Protocol):
    def permits(self, actor_id: UUID, notebook_id: UUID) -> bool: ...


class SQLiteNotebookScopeAuthority:
    """Small operational ACL store; no lookup grants access by default."""

    def __init__(self, path: Path) -> None:
        if not path.is_absolute():
            raise ValueError("scope authority path must be absolute")
        self.path = path.resolve(strict=False)

    def initialize(self) -> None:
        """Initialize only an explicitly selected operational store."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS notebook_grants("
                "actor_id TEXT NOT NULL, notebook_id TEXT NOT NULL, "
                "role TEXT NOT NULL CHECK(role IN ('owner','reader')), "
                "granted_by TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "PRIMARY KEY(actor_id,notebook_id))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS retired_notebook_ids("
                "notebook_id TEXT PRIMARY KEY, retired_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            connection.commit()
        finally:
            connection.close()

    def grant(
        self,
        *,
        actor_id: UUID,
        notebook_id: UUID,
        role: str,
        operator_id: UUID,
    ) -> None:
        """Persist an explicit operator-authorized grant; never infer one.

        Caller authorization is a separate server-only onboarding contract.
        This method must not be exposed directly as an HTTP/MCP operation.
        """
        if role not in {"owner", "reader"}:
            raise ValueError("unsupported notebook role")
        if not self.path.is_file():
            raise RuntimeError("scope authority has not been initialized")
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            if (
                connection.execute(
                    "SELECT 1 FROM retired_notebook_ids WHERE notebook_id=?", (str(notebook_id),)
                ).fetchone()
                is not None
            ):
                raise ValueError("retired notebook identity cannot receive grants")
            connection.execute(
                "INSERT INTO notebook_grants(actor_id,notebook_id,role,granted_by) VALUES(?,?,?,?)",
                (str(actor_id), str(notebook_id), role, str(operator_id)),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def retire_notebook(self, notebook_id: UUID) -> None:
        """Permanently invalidate grants for a deleted notebook identity.

        Call before deleting notebook storage: an interrupted deletion then
        fails closed rather than leaving usable stale grants.
        """
        if not self.path.is_file():
            raise RuntimeError("scope authority has not been initialized")
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT OR IGNORE INTO retired_notebook_ids(notebook_id) VALUES(?)",
                (str(notebook_id),),
            )
            connection.execute(
                "DELETE FROM notebook_grants WHERE notebook_id=?", (str(notebook_id),)
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def permits(self, actor_id: UUID, notebook_id: UUID) -> bool:
        if not self.path.is_file():
            return False
        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        try:
            if (
                connection.execute(
                    "SELECT 1 FROM retired_notebook_ids WHERE notebook_id=?", (str(notebook_id),)
                ).fetchone()
                is not None
            ):
                return False
            row = connection.execute(
                "SELECT 1 FROM notebook_grants WHERE actor_id=? AND notebook_id=?",
                (str(actor_id), str(notebook_id)),
            ).fetchone()
            return row is not None
        except sqlite3.DatabaseError:
            return False
        finally:
            connection.close()
